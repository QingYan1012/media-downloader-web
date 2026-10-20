r"""抖音风控判定的离线自检：一次 HTTP 往来 / 一句原始报错 / 一段下到的字节，各判得准不准。

全程不联网、不起服务、不碰 config.json。判定用的两份真实材料都在 fixtures 里：
- dy_challenge_head.html：2026-09-23 本机无 Cookie 打开 www.douyin.com/search/<关键词> 回页的前 4 KB
  （完整页 72915 字节，含 _$jsvmprt / byted_acrawler / __ac_signature，没有 _ROUTER_DATA、没有 aweme_id）；
- 登录墙那份 JSON 很短，直接抄在下面（实测 status_code=2483）。

反向验证也做了：真拿到结果 / 正常空结果 / 正常媒体文件头时，一条风控都不能报，
否则「被挡了」这句话只是常驻背景音。

跑法：`python tests/douyinrisk_test.py`
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import risk_control as R  # noqa: E402

CHALLENGE_HEAD = (HERE / "fixtures" / "dy_challenge_head.html").read_bytes()
FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# 实测：无 Cookie 请求两个搜索接口都是 HTTP 200 + 这个体
LOGIN_WALL_JSON = {"has_more": True, "data": [], "status_code": 2483,
                   "status_msg": "请先登录，再继续搜索吧", "log_pb": {"impr_id": "20260923123456ABC"}}


# ---------------------------------------------------------------- 1. classify_http
print("== A. 一次 HTTP 往来的分类 ==")
d = R.classify_http(status=200, content_type="application/json", json_data=LOGIN_WALL_JSON,
                    text=json.dumps(LOGIN_WALL_JSON))
ck("A1 返回码 2483 判成「要登录」", d["kind"] == R.LOGIN_REQUIRED, d["kind"])
ck("A2 判词带着返回码与站点原话", "2483" in R.describe(d) and "请先登录" in R.describe(d), R.describe(d))
ck("A3 登录墙不该触发降速（降速对「没登录」没用）", d["throttle"] is False)
ck("A4 动作里点名去哪配 Cookie", "多平台 Cookie" in d["action"], d["action"])

head_text = CHALLENGE_HEAD.decode("utf-8", "ignore")
d = R.classify_http(status=200, content_type="text/html", text=head_text,
                    cookie_names=["__ac_nonce", "ttwid"])
ck("A5 真实校验页判成「被当成脚本访问」", d["kind"] == R.BOT_CHALLENGE, d["kind"])
ck("A6 校验页要触发降速", d["throttle"] is True)
ck("A7 依据里写着命中的标记", "_$jsvmprt" in d["evidence"] and "__ac_nonce" in d["evidence"],
   str(d["evidence"]))
d = R.classify_http(status=200, content_type="text/html", text=head_text, cookie_names=["ttwid"])
ck("A8 只凭正文标记也认得出（没有 Set-Cookie 也算）", d["kind"] == R.BOT_CHALLENGE, d["kind"])
d = R.classify_http(status=429, text="", retry_after=120)
ck("A9 HTTP 429 判成限流并带 Retry-After", d["kind"] == R.RATE_LIMITED and d["throttle"]
   and "120" in "、".join(d["evidence"]), str(d))
d = R.classify_http(status=200, json_data={"status_code": 8, "status_msg": "哎呀，过于频繁了"},
                    text="")
ck("A10 站点用 200 包装的「太频繁」也算限流", d["kind"] == R.RATE_LIMITED and d["throttle"], d["kind"])
d = R.classify_http(status=200, json_data={"code": 1101, "message": "abc"}, text="")
ck("A11 没见过的非 0 返回码转述原话，不编结论",
   d["kind"] == R.API_REJECT and "abc" in (d["server_msg"] + d["human"]), str(d))
ck("A11b 返回码换了字段名（B 站那种 code/message）也认得，依据写着字段名",
   "code=1101" in d["evidence"], str(d["evidence"]))
d = R.classify_http(status=404, text="")
ck("A12 404 判成内容不存在", d["kind"] == R.NOT_FOUND, d["kind"])
d = R.classify_http(status=403, text="")
ck("A13 403 判成拒绝访问", d["kind"] == R.DENIED, d["kind"])

print("== B. 反向验证：正常回答不得判成风控 ==")
ok_json = {"status_code": 0, "data": None, "aweme_list": [{"aweme_id": "7412345678901234567"}]}
d = R.classify_http(status=200, content_type="application/json", json_data=ok_json,
                    text=json.dumps(ok_json), cookie_names=["ttwid"])
ck("B1 有 status_code=0 的正常回答不是风控", d["kind"] == R.EMPTY, d["kind"])
d = R.classify_http(status=200, content_type="application/json", json_data=ok_json,
                    text=json.dumps(ok_json) + " byted_acrawler __ac_signature",
                    cookie_names=["__ac_nonce"])
ck("B2 正文里顺带出现这些字样、但确实拿到 JSON 结果时不误判", d["kind"] != R.BOT_CHALLENGE, d["kind"])
d = R.classify_http(status=200, json_data={"status_code": 0, "data": "", "aweme_list": []}, text="")
ck("B3 正常空结果是「确实没有条目」，不是被挡", d["kind"] == R.EMPTY and d["throttle"] is False, str(d))
d = R.classify_http(status=200, text=head_text, json_data={}, json_seen=True,
                    cookie_names=["__ac_nonce"])
ck("B4 真的解析出了 JSON（哪怕是空对象）时不判成校验页", d["kind"] != R.BOT_CHALLENGE, d["kind"])
d = R.classify_http(status=200, text=head_text, json_data={}, json_seen=False,
                    cookie_names=["__ac_nonce"])
ck("B5 一个字段都没解析出来、正文又是标记 → 仍是校验页", d["kind"] == R.BOT_CHALLENGE, d["kind"])


# ---------------------------------------------------------------- 2. classify_failure_text
print("== C. 一句原始报错的分类 ==")
cases = [
    ("ERROR: [Douyin] abc: Fresh cookies (not necessarily valid ones) are needed", R.LOGIN_REQUIRED),
    ("HTTP Error 429: Too Many Requests", R.RATE_LIMITED),
    ("站点回了 __ac_nonce 校验页", R.BOT_CHALLENGE),
    ("视频不存在或已删除", R.NOT_FOUND),
    ("HTTP Error 403: Forbidden", R.DENIED),
    ("<urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING>", R.NETWORK),
    ("某种没见过的说法", R.UNKNOWN),
]
for raw, want in cases:
    got = R.classify_failure_text(raw)
    ck(f"C 分类 {want} ← {raw[:26]}", got["kind"] == want, got["kind"])
ck("C8 限流类才允许触发降速",
   R.classify_failure_text("HTTP Error 429")["throttle"] is True
   and R.classify_failure_text(cases[0][0])["throttle"] is False)
ck("C9 报错里的技术事实没被说法吃掉",
   "Fresh cookies" in R.classify_failure_text(cases[0][0])["human"])
ck("C10 brief 只给原因、不重复原话",
   "Fresh cookies" not in R.classify_failure_text(cases[0][0])["brief"],
   R.classify_failure_text(cases[0][0])["brief"])


# ---------------------------------------------------------------- 3. 下到的字节
print("== D. 「下载成功但下到的不是媒体」点名 ==")
s = R.describe_downloaded_bytes(CHALLENGE_HEAD)
ck("D1 真实校验页点名成 JS 校验页", "校验页" in s and "_$jsvmprt" in s, s[:100])
s = R.describe_downloaded_bytes(
    b'<?xml version="1.0"?><Error><Code>AccessDenied</Code><Message>Access denied by bucket policy</Message></Error>')
ck("D2 CDN 的 XML 报错把 Code/Message 抄上屏",
   "XML" in s and "AccessDenied" in s and "bucket policy" in s, s[:120])
s = R.describe_downloaded_bytes(b"<!DOCTYPE html><html><head><title>\xe7\x99\xbb\xe5\xbd\x95</title></head><body>x</body></html>")
ck("D3 普通登录页说成网页，不冒充校验页", "网页" in s and "校验页" not in s, s[:80])
ck("D4 反向验证：正常 mp4 文件头不报任何事",
   R.describe_downloaded_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x1f" + b"\x00" * 4080) == "")
ck("D5 反向验证：随包 ffmpeg 那种二进制开头也不报",
   R.describe_downloaded_bytes(b"\x1aE\xdf\xa3\x01\x00\x00\x00\x00\x00\x00\x1f\x83m\x86\x86" + b"\x7f" * 4080) == "")
ck("D6 challenge_bytes 也认这份真实头", R.challenge_bytes(CHALLENGE_HEAD) == "_$jsvmprt",
   R.challenge_bytes(CHALLENGE_HEAD))


# ---------------------------------------------------------------- 4. 接线到 server
print("== E. 接进 server 的降速与任务报错 ==")
import server as S  # noqa: E402

LOGS: list = []
FakeLogMgr = type("L", (), {"log": staticmethod(
    lambda m, lvl="info", k="", kv=None: LOGS.append((lvl, m)))})()


class FakeCfg:
    """只暴露 .data —— 和真的 ConfigManager 一模一样。

    这里曾经多一个 .get()，于是 server 里 `cfg.get(...)` 的误用离线全绿、
    真机上一句 AttributeError 被外层 try 吞掉，降速和请求间隔双双静默失效。
    """

    def __init__(self, d):
        self.data = d


class FakeThrottle:
    """和真的 HostThrottle 同形：hit 的 cooldown/wait 是关键字参数，peek 只读不改状态。"""

    def __init__(self, cooldown_left: float = 0.0):
        self.hits = []
        self.cooldown_left = cooldown_left
        self.peeks = []

    def hit(self, url, *, cooldown=60.0, wait=0.0, max_cooldown=900.0):
        self.hits.append(url)
        return {"host": "www.douyin.com", "cooldown": float(cooldown), "strikes": len(self.hits)}

    def peek(self, url):
        self.peeks.append(url)
        if not self.cooldown_left:
            return {}
        return {"host": "www.douyin.com", "strikes": 3, "cooldown": 240.0,
                "left": self.cooldown_left}


_real = (S.cfg, S.log_mgr, S.HOST_THROTTLE)
try:
    S.cfg = FakeCfg({"adaptive_throttle": True, "risk_cooldown_429": 90})
    S.log_mgr = FakeLogMgr
    ft = FakeThrottle()
    S.HOST_THROTTLE = ft

    note = S.risk_note_for_failure("站点回了 byted_acrawler 校验页", "https://www.douyin.com/video/1", "t-1234")
    ck("E1 校验页类失败会补一句原因并真的降速",
       note.startswith("原因：") and "多平台 Cookie" in note and ft.hits == ["https://www.douyin.com/video/1"], note)
    ck("E2 降速写进日志（不能只有界面知道）",
       any(lvl == "warning" and "按失败原因降速" in m for lvl, m in LOGS), str(LOGS[-1:]))

    before = len(ft.hits)
    note429 = S.risk_note_for_failure("HTTP Error 429: Too Many Requests", "https://x/2", "t-2")
    ck("E3 429 只补说法、不再叠一次 strike（下载循环里已经打过）",
       "限流" in note429 and len(ft.hits) == before and "已自动降速" not in note429, note429)

    ck("E4 认不出的报错不编原因，原样回空串",
       S.risk_note_for_failure("某种没见过的说法", "https://x/3", "t-3") == "")

    S.cfg = FakeCfg({"adaptive_throttle": False, "risk_cooldown_429": 90})
    n = len(ft.hits)
    note_off = S.risk_note_for_failure("站点回了 byted_acrawler 校验页", "https://x/4", "t-4")
    ck("E5 关掉「自动降速」开关后确实不打点", len(ft.hits) == n and "原因：" in note_off)
    S.cfg = FakeCfg({"adaptive_throttle": True, "risk_cooldown_429": 90})

    # ---- /api/search 的 notes 透传
    body = S.SearchBody(query="测试词", platform="douyin", content_type="video", limit=10, sort="relevance")
    _real_dy = S.api_douyin_search
    try:
        S.api_douyin_search = lambda q, n=12: {
            "results": [], "count": 0, "note": "无结果：…", "has_cookie": False,
            "risk": {"kind": R.LOGIN_REQUIRED, "code": "2483", "server_msg": "请先登录，再继续搜索吧",
                     "human": "这一平台的接口要求先登录才回答（返回码 2483：请先登录，再继续搜索吧）",
                     "action": "去「设置 → 多平台 Cookie」配抖音", "evidence": ["status_code=2483"], "via": "api1"},
            "throttle": {"host": "www.douyin.com", "cooldown": 90.0},
            "attempts": [{"via": "api1", "kind": R.LOGIN_REQUIRED, "code": "2483"}],
        }
        out = S.api_search(body)
        ck("E6 聚合搜索把分类结论放进 notes 带回前端",
           len(out["notes"]) == 1 and out["notes"][0]["platform"] == "douyin"
           and "2483" in out["notes"][0]["text"] and out["notes"][0]["kind"] == R.LOGIN_REQUIRED,
           str(out["notes"]))
        ck("E7 降速事实写在同一条原因里", "已自动降速" in out["notes"][0]["text"], out["notes"][0]["text"])
        S.api_douyin_search = lambda q, n=12: (_ for _ in ()).throw(
            RuntimeError("ERROR: [Douyin] abc: Fresh cookies (not necessarily valid ones) are needed"))
        out = S.api_search(body)
        ck("E8 搜索整条抛异常时也分类，不只留一句「抖音搜索失败」",
           out["notes"] and out["notes"][0]["kind"] == R.LOGIN_REQUIRED
           and "Fresh cookies" in out["notes"][0]["text"], str(out["notes"]))

        S.api_douyin_search = lambda q, n=12: {
            "results": [{"platform": "douyin", "id": "7412345678901234567", "title": "有结果",
                         "url": "https://www.douyin.com/video/7412345678901234567", "content_type": "video"}],
            "count": 1, "note": "ok", "has_cookie": True, "risk": {}, "throttle": {}, "attempts": []}
        out = S.api_search(body)
        ck("E9 反向验证：抖音真的返回了条目时不写任何「被挡」原因", out["notes"] == [], str(out["notes"]))
    finally:
        S.api_douyin_search = _real_dy
finally:
    S.cfg, S.log_mgr, S.HOST_THROTTLE = _real

print("== F. 校验链真的用上分类（verify_media_file） ==")
_real_v = (S.cfg, S._ffprobe_bin)
with tempfile.TemporaryDirectory(prefix="md_dy_risk_") as td:
    try:
        tmp = Path(td) / "probe.mp4"
        tmp.write_bytes(CHALLENGE_HEAD)
        S._ffprobe_bin = lambda: ""           # 不依赖本机 ffmpeg，只看「读到的是网页」这一步
        msg = S.verify_media_file(tmp)
        ck("F1 把校验页存成 mp4 时报错会点名是 JS 校验页", "校验页" in msg and "_$jsvmprt" in msg, msg[:120])
        ck("F2 「文件没下下来」这种含糊说法不再出现", "多半是被站点拦下" not in msg, msg[:80])
    finally:
        S.cfg, S._ffprobe_bin = _real_v

print("== G. /api/douyin/search 绑在哪个函数上 ==")
# 装饰器曾贴在 _load_netscape_cookies 上：这条路由既不搜东西（缺 q 直接 422），
# 又会把 ?path= 指向的 Cookie 文件解析成 {名字: 值} 原样回给调用方。
_dy_routes = [rt for rt in S.app.routes if getattr(rt, "path", "") == "/api/douyin/search"]
_ep = getattr(_dy_routes[0], "endpoint", None) if len(_dy_routes) == 1 else None
_ep_name = getattr(_ep, "__name__", "")
ck("G1 这条路由只有一条、且指向 api_douyin_search",
   len(_dy_routes) == 1 and _ep_name == "api_douyin_search",
   f"{len(_dy_routes)} 条 / {_ep_name}")
ck("G2 反向验证：路由不再绑到 Cookie 文件加载函数上", _ep_name != "_load_netscape_cookies", _ep_name)

print("== H. 整条 api_douyin_search 真跑一遍（打桩 requests，不联网） ==")
# E 段把 api_douyin_search 换成了 lambda，接口节奏和 _note_attempt 里的降速打点从来没被跑过；
# 真机上 cfg.get 的 AttributeError 就是这么躲过自检的。这一段用假 responses 走真函数。
class _Cookie:
    def __init__(self, n):
        self.name = n


class FakeResp:
    def __init__(self, body="", json_body=None, ct="application/json; charset=utf-8", cookies=()):
        self.status_code = 200
        self.text = body
        self.headers = {"content-type": ct}
        self._j = json_body
        self.cookies = [_Cookie(c) for c in cookies]

    def json(self):
        if self._j is None:
            raise ValueError("not json")
        return self._j


OK_JSON = {"status_code": 0, "data": [{"aweme_info": {
    "aweme_id": "7412345678901234567", "desc": "正常条目", "create_time": 1700000000,
    "author": {"nickname": "某人"}, "statistics": {"play_count": "123"}}}]}


def _make_get(kind, calls):
    def _get(url, **kw):
        calls.append(url)
        if "/search/" in url and "aweme/v1" not in url:
            if kind == "ok":
                return FakeResp("<html>aweme_id\":\"7412345678901234567\"</html>", ct="text/html")
            return FakeResp(CHALLENGE_HEAD.decode("utf-8", "replace"), ct="text/html",
                            cookies=["__ac_nonce"])
        if kind == "ok":
            return FakeResp(json_body=OK_JSON, body=json.dumps(OK_JSON))
        return FakeResp(json_body=LOGIN_WALL_JSON, body=json.dumps(LOGIN_WALL_JSON))
    return _get


SLEEPS: list = []
_real_h = (S.cfg, S.log_mgr, S.HOST_THROTTLE, S.requests.get, S._douyin_cookies,
           S.requests_proxies, S.time.sleep)
try:
    S.time.sleep = lambda s: SLEEPS.append(s)
    S._douyin_cookies = lambda *a, **k: {"sessionid": "stub"}
    S.requests_proxies = lambda *a, **k: {}

    S.cfg = FakeCfg({"adaptive_throttle": True, "risk_cooldown_429": 90, "risk_delay_sec": 0.3})
    S.log_mgr = FakeLogMgr
    ft = FakeThrottle()
    S.HOST_THROTTLE = ft
    calls: list = []
    S.requests.get = _make_get("blocked", calls)
    LOGS.clear()
    out = S.api_douyin_search("测试词", 5)
    _kinds = [(a["via"], a["kind"]) for a in out["attempts"]]
    ck("H1 四次接口 + 一次 HTML 都被分类，没有一条是吞掉的「请求没走通」",
       len(out["attempts"]) == 5 and not any(a["kind"] == R.NETWORK for a in out["attempts"]), str(_kinds))
    ck("H2 结论取最狠的那条：反爬挑战", out["risk"]["kind"] == R.BOT_CHALLENGE
       and "__ac_nonce" in (out["risk"]["evidence"] or []), out["risk"]["kind"])
    ck("H3 按「风控冷却」设置真的打了降速点（90s 来自配置，不是默认 60）",
       ft.hits == ["https://www.douyin.com/"] and out["throttle"].get("cooldown") == 90.0, str(out["throttle"]))
    ck("H4 无结果原因里带上已降速", "已自动降速" in out["note"] and "90s" in out["note"], out["note"][-70:])
    ck("H5 日志里既有点名依据也有降速",
       any("抖音搜索无结果" in m and "已降速 www.douyin.com" in m for _l, m in LOGS), str(LOGS[-1:])[:160])
    ck("H6 按「请求间隔」设置真的排队，不是一次刷完接口",
       len(SLEEPS) == 4 and all(abs(s - 0.3) < 1e-9 for s in SLEEPS), str(SLEEPS))

    SLEEPS.clear()
    S.cfg = FakeCfg({"adaptive_throttle": True, "risk_cooldown_429": 90, "risk_delay_sec": 0})
    ft2 = FakeThrottle()
    S.HOST_THROTTLE = ft2
    calls2: list = []
    S.requests.get = _make_get("ok", calls2)
    LOGS.clear()
    out_ok = S.api_douyin_search("测试词", 5)
    ck("H7 反向验证：正常拿到条目时不降速、不写原因、也不空等间隔",
       out_ok["count"] == 1 and out_ok["throttle"] == {} and out_ok["note"] == "ok"
       and not ft2.hits and not SLEEPS and not any(l == "warning" for l, _m in LOGS),
       f"{out_ok['count']} 条 / {out_ok['note']}")
finally:
    (S.cfg, S.log_mgr, S.HOST_THROTTLE, S.requests.get, S._douyin_cookies,
     S.requests_proxies, S.time.sleep) = _real_h

print("== I. 冷却期内不再重复敲门（入口先查 HOST_THROTTLE） ==")
_BLOCKED_CACHE = {"kind": R.BOT_CHALLENGE, "code": "", "server_msg": "",
                  "human": "站点把这个请求当成脚本访问了", "describe": "回的是要执行 JS 才能继续的校验页",
                  "action": "带上一份有效登录 Cookie 再试", "evidence": ["_$jsvmprt"], "via": "html"}
_real_i = (S.cfg, S.log_mgr, S.HOST_THROTTLE, S.requests.get, S._douyin_cookies,
           S.requests_proxies, S.time.sleep, dict(S._DY_LAST_BLOCK))
try:
    S.time.sleep = lambda s: None
    S._douyin_cookies = lambda *a, **k: {"sessionid": "stub"}
    S.requests_proxies = lambda *a, **k: {}
    S.log_mgr = FakeLogMgr
    S.cfg = FakeCfg({"adaptive_throttle": True, "risk_cooldown_429": 120, "risk_delay_sec": 0})

    # ① 冷却中 + 有上次判定 → 复述，不发请求、不再叠 strike
    ft = FakeThrottle(cooldown_left=90.0)
    S.HOST_THROTTLE = ft
    S._DY_LAST_BLOCK.clear(); S._DY_LAST_BLOCK.update(_BLOCKED_CACHE)
    calls_i: list = []
    S.requests.get = _make_get("blocked", calls_i)
    LOGS.clear()
    out = S.api_douyin_search("测试词", 5)
    ck("I1 冷却期内一条请求都不发", calls_i == [] and out["attempts"] == [] and out["skipped"] is True,
       f"{len(calls_i)} 次请求 / {len(out['attempts'])} 条 attempts")
    ck("I2 复述的是上次判定，并写明「本次没有再发请求」与剩余秒数",
       out["risk"]["kind"] == R.BOT_CHALLENGE and "还剩 90s" in out["risk"]["human"]
       and "本次没有再向它发请求" in out["note"], out["risk"]["human"])
    ck("I3 只读不问罪：peek 过、hit 一次都没打（否则越点越长）",
       ft.peeks == ["https://www.douyin.com/"] and ft.hits == [], f"peeks={ft.peeks} hits={ft.hits}")
    ck("I4 日志写明这是跳过、不是搜过了",
       any("抖音搜索跳过" in m and "上次判定 bot_challenge" in m for _l, m in LOGS), str(LOGS[-1:])[:150])
    ck("I5 冷却事实照样带回前端", out["throttle"].get("left") == 90.0, str(out["throttle"]))

    # ② 反向：冷却中但没有可复述的判定 —— 不能因此把用户的搜索吞掉
    ft2 = FakeThrottle(cooldown_left=90.0)
    S.HOST_THROTTLE = ft2
    S._DY_LAST_BLOCK.clear()
    calls_2: list = []
    S.requests.get = _make_get("blocked", calls_2)
    out2 = S.api_douyin_search("测试词", 5)
    ck("I6 反向验证：光有冷却、没存过判定 → 照搜不误",
       len(calls_2) == 5 and "skipped" not in out2, f"{len(calls_2)} 次请求")
    ck("I7 被挡的这一次确实把判定存下了（下一次才会被复述）",
       S._DY_LAST_BLOCK.get("kind") == R.BOT_CHALLENGE
       and S._DY_LAST_BLOCK.get("describe") == out2["risk"]["human"], str(S._DY_LAST_BLOCK.get("kind")))

    # ③ 反向：有判定但没在冷却里 —— 也要真去搜，不能拿旧结论糊弄
    ft3 = FakeThrottle(cooldown_left=0.0)
    S.HOST_THROTTLE = ft3
    calls_3: list = []
    S.requests.get = _make_get("blocked", calls_3)
    out3 = S.api_douyin_search("测试词", 5)
    ck("I8 反向验证：冷却已过期 → 重新真搜，不复述旧判定",
       len(calls_3) == 5 and "本次没有再向它发请求" not in out3["note"],
       f"{len(calls_3)} 次请求 / hit {len(ft3.hits)} 次")
    ck("I9 真搜过的那一次会打点（复述的那一次不会）", len(ft3.hits) == 1 and not ft.hits, f"{ft3.hits}")

    # ④ 聚合搜索里也要看得出是跳过的
    body = S.SearchBody(query="测试词", platform="douyin", content_type="all", limit=10, sort="relevance")
    ft4 = FakeThrottle(cooldown_left=45.0)
    S.HOST_THROTTLE = ft4
    calls_4: list = []
    S.requests.get = _make_get("blocked", calls_4)
    out4 = S.api_search(body)
    ck("I10 聚合搜索的原因里写明「本次没有再向它发请求」",
       calls_4 == [] and out4["notes"] and "本次没有再向它发请求" in out4["notes"][0]["text"],
       str(out4["notes"])[:170])
    ck("I11 跳过的原因不会再说「已自动降速」（那次什么都没发）",
       out4["notes"] and "已自动降速" not in out4["notes"][0]["text"], str(out4["notes"])[:170])

    # ⑤ 反向：冷却已过的真搜被挡 → 「已自动降速」必须还在，否则上一条会退化成永远成立
    S.HOST_THROTTLE = FakeThrottle(cooldown_left=0.0)
    calls_5: list = []
    S.requests.get = _make_get("blocked", calls_5)
    out5 = S.api_search(body)
    ck("I12 反向验证：真搜过并被挡时，聚合原因照样写「已自动降速」",
       len(calls_5) == 5 and any("已自动降速" in n["text"] for n in out5["notes"] or []),
       str(out5["notes"])[:170])
finally:
    (S.cfg, S.log_mgr, S.HOST_THROTTLE, S.requests.get, S._douyin_cookies,
     S.requests_proxies, S.time.sleep) = _real_i[:7]
    S._DY_LAST_BLOCK.clear()
    S._DY_LAST_BLOCK.update(_real_i[7])

print()
print("FAILED:", ", ".join(FAILED) if FAILED else "none")
sys.exit(1 if FAILED else 0)
