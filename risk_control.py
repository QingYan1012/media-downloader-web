r"""把「站点回了什么」翻成「现在被挡在哪一步、该做什么」。

只依赖标准库，判定用的标记串全部来自本机实测（见每条注释里的来源），
没实测过的写法一律标 inferred，宁可回 unknown 也不假装知道。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Sequence

# 判定结果
LOGIN_REQUIRED = "login_required"    # 要登录（Cookie 缺失或已失效）
BOT_CHALLENGE = "bot_challenge"      # 被当成脚本访问，回了要执行 JS 的校验页
RATE_LIMITED = "rate_limited"        # 明显限流
API_REJECT = "api_reject"            # 接口主动拒绝，但原因不在上面三类
NOT_FOUND = "not_found"              # 内容不存在 / 已删除
DENIED = "denied"                    # 403/私有/地区限制
EMPTY = "empty"                      # 接口正常返回，只是这次确实没有结果
NETWORK = "network"                  # 压根没连上
UNKNOWN = "unknown"

# 2026-09-23 本机实测：无 Cookie 请求 /aweme/v1/web/general/search/single/ 与
# /aweme/v1/web/search/item/ 都是 HTTP 200 + {"log_pb","status_code","status_msg"}，
# status_code=2483、status_msg=「请先登录，再继续搜索吧」。其它码值未实测，走 API_REJECT 原样转述。
LOGIN_STATUS_CODES = {2483}

# 实测：无 Cookie 打开 https://www.douyin.com/search/<关键词> 回 72914 字节的 JS 挑战页，
# 响应 Set-Cookie 里有 __ac_nonce，正文含 _$jsvmprt(×2)、byted_acrawler(×2)、__ac_signature(×3)，
# 且整页没有 _ROUTER_DATA / aweme_id —— 也就是说程序化访问根本拿不到结果。
AC_MARKERS = ("_$jsvmprt", "byted_acrawler", "__ac_signature", "__ac_stub", "sse_split_data")
VERIFY_MARKERS = ("verify_center", "tcaptcha", "secsdk-captcha", "rmcify", "risk_captcha",
                  "滑块", "安全验证", "拖动下方滑块")  # inferred：常见写法，本机未触发过

_FREQ_MSGS = ("操作太频繁", "请稍后再试", "访问过于频繁", "请求过于频繁", "过于频繁", "太频繁",
              "too many requests", "rate limit", "try again later")
_LOGIN_MSGS = ("请先登录", "请登录", "登录后", "需要登录", "login required", "sign in", "not logged in")
_NOTFOUND_MSGS = ("视频不存在", "已删除", "作品已删除", "作品不存在", "video unavailable",
                  "item not found")


def _norm(v: Any) -> str:
    return str(v or "")


def _hit_any(text: str, needles: Sequence[str]) -> str:
    low = (text or "").lower()
    for n in needles:
        if n.lower() in low:
            return n
    return ""


def _result(kind: str, *, code: str = "", server_msg: str = "", human: str,
            throttle: bool = False, action: str = "", evidence: Sequence[str] = (),
            brief: str = "") -> Dict:
    return {
        "kind": kind,
        "code": code,
        "server_msg": server_msg[:200],
        "human": human,
        "brief": brief,
        "throttle": throttle,
        "action": action,
        "evidence": [e for e in evidence if e][:6],
    }


def classify_http(*, status: int = 0, content_type: str = "", text: str = "",
                  json_data: Optional[dict] = None, cookie_names: Iterable[str] = (),
                  retry_after: float = 0.0, json_seen: Optional[bool] = None) -> Dict:
    """判一次 HTTP 响应。status 为 0 表示调用方没给状态码。

    顺序是有意的：先认「这压根不是数据」（挑战页 / 限流），再认登录墙，
    最后才允许下「没有结果」的结论 —— 反过来越序就会把风控说成没结果。
    """
    names = {str(c).lower() for c in (cookie_names or ())}
    body = text or ""
    cj = json_data if isinstance(json_data, dict) else {}
    has_json = bool(cj) if json_seen is None else bool(json_seen)
    ev = []

    has_ac_cookie = bool(names & {"__ac_nonce", "ac_nonce"})
    ac_marker = _hit_any(body, AC_MARKERS)
    if has_ac_cookie or ac_marker:
        if ac_marker:
            ev.append(ac_marker)
        if has_ac_cookie:
            ev.append("__ac_nonce")
        # 挑战页不是 JSON 数据；调用方确实解析出了 JSON 时不因这两个标记误判
        if not has_json:
            v = _hit_any(body, VERIFY_MARKERS)
            if v:
                ev.append(v)
            return _result(
                BOT_CHALLENGE, throttle=True, evidence=ev,
                human=("站点把这个请求当成脚本访问了：回的是要执行 JS 才能继续的校验页，"
                       "里面没有任何结果数据"),
                action=("带上一份有效登录 Cookie 再试（「设置 → 多平台 Cookie」里的「抖音/TikTok」，"
                        "选「浏览器」挑已登录的浏览器，或选「文件」填 Netscape 格式文件）；"
                        "这个拦截图鉴码框不出来，程序也不会去执行它的 JS"),
            )

    if int(status or 0) == 429 or _norm(retry_after) not in ("", "0", "0.0"):
        return _result(
            RATE_LIMITED, code=str(status or 429), throttle=True,
            human="站点限流（HTTP 429），这段时间再发也只会被拒",
            action="等冷却过去再试；想更稳就把「设置 → 风控与加速」的预设调到「安全」或「极端安全」",
            evidence=[f"http={status}"] + ([f"retry_after={retry_after}"] if float(retry_after or 0) else []),
        )

    # 各家字段名不一样：抖音 status_code/status_msg，B 站 code/message，也有 msg/errno
    code = next((cj[k] for k in ("status_code", "code", "errno") if cj.get(k) not in (None, "")), None)
    code_key = next((k for k in ("status_code", "code", "errno") if cj.get(k) not in (None, "")), "")
    msg = _norm(cj.get("status_msg") or cj.get("message") or cj.get("msg") or "")
    if code is not None:
        ev.append(f"{code_key}={code}")
    if msg:
        ev.append(f"status_msg={msg[:80]}" if cj.get("status_msg") else f"message={msg[:80]}")

    f = _hit_any(msg, _FREQ_MSGS)
    if f or _hit_any(body, _FREQ_MSGS):
        return _result(
            RATE_LIMITED, code=_norm(code), server_msg=msg, throttle=True, evidence=ev,
            human=f"站点提示访问过快（{msg or '操作太频繁'}）",
            action="先停一会儿再搜；反复重试只会把冷却拉长（本站已按命中次数自动降速）",
        )

    if _norm(code) in {str(c) for c in LOGIN_STATUS_CODES} or _hit_any(msg, _LOGIN_MSGS):
        return _result(
            LOGIN_REQUIRED, code=_norm(code), server_msg=msg, evidence=ev,
            human=("这一平台的接口要求先登录才回答"
                   + (f"（返回码 {code}：{msg}）" if msg else "")),
            action=("去「设置 → 多平台 Cookie」把这一平台的块配好：选「浏览器」直接读已登录的浏览器，"
                    "或选「文件」填一份 Netscape 格式 Cookie；不登录的话这条路径拿不到任何结果"),
        )

    nf = _hit_any(msg, _NOTFOUND_MSGS)
    if nf:
        return _result(NOT_FOUND, code=_norm(code), server_msg=msg, evidence=ev,
                       human=f"内容取不到：{msg}", action="在浏览器里打开这条链接确认它是否还存在")

    if int(status or 0) in (403, 451):
        return _result(
            DENIED, code=str(status), server_msg=msg, evidence=ev,
            human=f"站点拒绝访问（HTTP {status}）",
            action="通常是 Cookie 失效或该链接有登录/地区门槛，先在浏览器里确认能正常打开",
        )
    if int(status or 0) == 404:
        return _result(NOT_FOUND, code="404", server_msg=msg, evidence=ev,
                       human="地址在该站点上不存在（HTTP 404）",
                       action="确认链接抄全了，或改用页面里的分享链接")

    if code not in (None, 0, "0", ""):
        return _result(
            API_REJECT, code=_norm(code), server_msg=msg, evidence=ev,
            human=("接口明确回了一个非 0 的返回码，这不是「没有结果」"
                   + (f"：{msg}" if msg else "")),
            action="把这条原因连着链接一起看：多半是 Cookie、参数或该接口的门槛变了",
        )

    if int(status or 0) == 0 and not body and not cj:
        return _result(NETWORK, human="没有收到任何响应", action="检查网络与代理（设置 → 网络与并发）")

    return _result(EMPTY, code=_norm(code), server_msg=msg, evidence=ev,
                   human="接口正常回答，但这一次确实没有给出条目",
                   action="换个更具体的关键词，或缩小平台范围再搜")


_ERR_RULES = (
    (BOT_CHALLENGE, r"__ac_nonce|byted_acrawler|_\$jsvmprt|__ac_signature|acrawler",
     True, "站点把这个请求当成脚本访问了（回的是要执行 JS 的校验页），里面没有媒体数据"),
    (RATE_LIMITED, r"\b429\b|too many requests|rate ?limit|过于频繁|太频繁|访问过于频繁|请稍后再试",
     True, "命中站点限流"),
    (LOGIN_REQUIRED, r"请先登录|请登录后|需要登录|fresh cookies?.*(needed|are needed)|login required|"
                     r"log in to (continue|download)|status_code['\"= ]{0,3}2483",
     False, "该平台接口要求登录：没有有效 Cookie 时它一条结果都不会给"),
    (NOT_FOUND, r"video unavailable|item not found|作品不存在|视频不存在|已删除|removed by the uploader",
     False, "内容已经不存在（被删除、下架或地址抄错）"),
    (DENIED, r"\bhttp error 403\b|forbidden|access denied|not available in your country",
     False, "站点拒绝访问（私有、会员或地区限制）"),
)


def classify_failure_text(raw: Any) -> Dict:
    """下载 / 解析失败时那句原始报错属于哪一类。认不出来回 UNKNOWN，不硬编。"""
    s = _norm(raw)
    if not s:
        return _result(UNKNOWN, human="没有可用的失败原因", action="看运行日志里这条任务前后的行")
    for kind, pat, thr, brief in _ERR_RULES:
        if re.search(pat, s, re.I):
            thr_flag = thr and bool(re.search(
                r"__ac_nonce|byted_acrawler|_\$jsvmprt|\b429\b|too many requests|rate ?limit|"
                r"过于频繁|太频繁|请稍后再试", s, re.I))
            return _result(
                kind, throttle=thr_flag, evidence=[_norm(re.search(pat, s, re.I).group(0))],
                human=brief + f"：{s[:160]}", action=_action_for(kind), brief=brief,
            )
    if re.search(r"getaddrinfo|connection|timed out|timeout|econnreset|ssl", s, re.I):
        return _result(NETWORK, human="网络层就没通：连不上或连上被断",
                       action="检查代理与网络（设置 → 网络与并发）",
                       brief="网络层就没通（连不上或被断开）")
    return _result(UNKNOWN, human="", action="", evidence=[s[:160]])


def _action_for(kind: str) -> str:
    return {
        BOT_CHALLENGE: "带上一份有效登录 Cookie 再试（「设置 → 多平台 Cookie」里的「抖音/TikTok」）；"
                       "这张校验页要靠浏览器执行 JS 才过得去，程序不模拟它",
        RATE_LIMITED: "先停一会儿再试；把「设置 → 风控与加速」的预设调低一档，反复重试只会拉长冷却",
        LOGIN_REQUIRED: "到「设置 → 多平台 Cookie」配这一平台的 Cookie（浏览器或文件两种方式都行）",
        NOT_FOUND: "在浏览器里打开这条链接确认它是否还在",
        DENIED: "确认这条链接在浏览器里能正常打开（是否要登录 / 会员 / 对应地区网络）",
    }.get(kind, "")


def challenge_bytes(head: bytes) -> str:
    """下载到的文件开头像不像「站点拦下的页面 / 挑战页」。命中返回标记，否则空串。"""
    t = (head or b"")[:4096].decode("latin-1", "ignore").lower()
    for m in AC_MARKERS:
        if m.lower() in t:
            return m
    for m in ("<!doctype html", "<html", "<?xml", "<error>"):
        if m in t[:300]:
            return m
    return ""


_XML_ERR_TAG = re.compile(r"<(Code|Message|RequestId|HostId)>\s*(.{0,120}?)\s*</\1>", re.I | re.S)


def describe_downloaded_bytes(head: bytes) -> str:
    """「工具说下载成功了，但下到的不是媒体」时，点名它到底是什么；看着像正常数据就回空串。

    校验页那句话直接复用 classify_http，免得这里和搜索路径两套说法。
    """
    text = (head or b"")[:4096].decode("utf-8", "ignore")
    low = text.lower()
    if _hit_any(text, AC_MARKERS) or "_ROUTER_DATA" not in text and _hit_any(text, ("<html", "<!doctype html")):
        d = classify_http(status=200, text=text)
        if d["kind"] == BOT_CHALLENGE:
            return (d["human"] + "；下到的文件就是这张页面，不是媒体数据"
                    + (f"（依据 {'、'.join(d['evidence'])}）" if d["evidence"] else ""))
    if low.lstrip().startswith("<?xml") or "<error>" in low[:300]:
        kv = [f"{k}={v}" for k, v in _XML_ERR_TAG.findall(text)]
        return ("下到的是一份 XML 报错而不是媒体"
                + (f"：{'，'.join(kv[:4])}" if kv else "（里面没有可读的 Code/Message）"))
    if _hit_any(text, VERIFY_MARKERS):
        return ("下到的是一张人机验证页面（含「" + _hit_any(text, VERIFY_MARKERS) + "」），不是媒体数据；"
                "这类页面需要人在浏览器里过验证")
    if "<head" in low[:300] or "<html" in low[:300]:
        return "下到的是一份网页而不是媒体（多半是登录墙或跳转页被当成文件存了下来）"
    return ""


def describe(d: Dict) -> str:
    """拼成一条能直接进日志 / 上屏的话（带返回码与平台原话，不丢技术事实）。"""
    if not d:
        return ""
    parts = [d.get("human") or ""]
    if d.get("code"):
        parts.append(f"返回码 {d['code']}")
    if d.get("server_msg") and d["server_msg"] not in (d.get("human") or ""):
        parts.append(f"站点原话「{d['server_msg']}」")
    return "，".join(p for p in parts if p)
