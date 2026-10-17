r"""公开优先的 Cookie 策略（匿名先试、失败才升）离线自检。

钉的是六件事：
1. 开关关着时这条路一字不差：一次解析、带配置里那份 Cookie，不产生任何判定。
2. 匿名那次真的没带 Cookie：三条入口（全局来源、逐平台、请求头里那串）都得清干净，
   少清一条这次「匿名」就是假的，日志与缓存都会照着它编。
3. 只有「带 Cookie 才可能有救」的失败才重跑：429、连不上、内容不存在一律不重跑 ——
   多打一次平台接口只会把冷却加长。YouTube 那一支多认一种形状：活体读数里匿名打开公开视频
   回的是「一条流都不给」，带 Cookie 那份却有 43 条流到 2160p，那句按风控分类落在 UNKNOWN，
   只照话术认登录墙就会把整条链接判死。
4. 匿名那份「成功但被裁」的 YouTube 清单不能当答案（这正是 1.3.2 修掉的静默降质）：
   只有独立视频轨（DASH）才算完整，否则照样带 Cookie 再打一次。
5. 判定是同一个出口：解析、下载、直链请求头三处都问 `cookie_off`，不各自读开关；
   Cookie 这一层被改过（保存设置 / 平台 Cookie / 上传 / CookieCloud 拉来新内容 / 单条重试）判定作废。
6. 接线：ConfigBody 得真声明这个键（没声明的键会在 model_dump 那一步静默丢掉，本项目的 G2 那类 bug），
   界面有开关、有话说清「默认关」与「哪几种失败不会重跑」。

跑法：PYTHONIOENCODING=utf-8 python tests/cookiefirst_test.py
"""
import re
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import server as S  # noqa: E402

SRC = Path(S.__file__).read_text(encoding="utf-8")
HTML = (APP / "static" / "index.html").read_text(encoding="utf-8")
# 界面文案搬进词表后，这里判的「说没说清」要看词表的中文那一份：键名留在 HTML 里，字在 i18n.js 里
I18N = (APP / "static" / "i18n.js").read_text(encoding="utf-8")
_zh_blob = I18N[I18N.find("    zh: {"):I18N.find("\n    en: {")]
ZH = dict(re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh_blob))
FAILED = []
TOTAL = 0
TMP = Path(tempfile.mkdtemp(prefix="md_cookiefirst_"))
CKFILE = TMP / "cookies.txt"
CKFILE.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

RAW_YT = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
YT = S.normalize_url(RAW_YT)
OK_CFG = {"cookie_source": "file", "cookie_file": str(CKFILE), "cookie_public_first": True}
DASH = [{"format_id": "137", "vcodec": "vp09.00.10.08", "acodec": "none", "height": 2160},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "height": None}]
MUXED = [{"format_id": "22", "vcodec": "avc1.4d001f", "acodec": "mp4a.40.2", "height": 1080}]
LOWMUX = [{"format_id": "18", "vcodec": "avc1.42001e", "acodec": "mp4a.40.2", "height": 720}]


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{str(extra)[:260]}]")


print("== A. 哪些失败值得带 Cookie 再打一次 ==")
ck("A1 登录墙 / 会员 / 年龄限制：值得",
   all(S.cookie_might_help(x) for x in (
       "ERROR: [youtube] abc1234: Requested format is not available. Sign in to confirm you're not a bot",
       "ERROR: [bilibili] 请先登录", "ERROR: [youtube] 此视频仅限会员观看",
       "ERROR: age-restricted content, sign in to confirm your age",
       "ERROR: [somei] login required")),
   [x for x in ("Sign in to confirm you're not a bot", "请先登录", "仅限会员",
                "age-restricted", "login required") if not S.cookie_might_help(x)])
ck("A2 429 限流：不许重跑（多打一次只会加长冷却）",
   not S.cookie_might_help("ERROR: HTTP Error 429: Too Many Requests")
   and not S.cookie_might_help("429 访问过于频繁，请稍后再试"), S.cookie_might_help("HTTP Error 429"))
ck("A2b 429 那句里同时提到「登录才能继续」（风控校验页就这么写）：仍不许重跑",
   not S.cookie_might_help("ERROR: [youtube] abc1234: HTTP Error 429: Too Many Requests. "
                           "Sign in to confirm you're not a bot"),
   S.cookie_might_help("ERROR: HTTP Error 429: Too Many Requests. Sign in to confirm you're not a bot"))
ck("A2c 限流那类一律先按「不值得重跑」处理，落到正则之前",
   "risk_control.RATE_LIMITED" in SRC[SRC.index("def cookie_might_help"):SRC.index("def cfg_without_cookie")], "")
ck("A3 连不上 / 超时：不许重跑（网络层就没通，带不带 Cookie 一个样）",
   not S.cookie_might_help("ERROR: [youtube] getaddrinfo failed")
   and not S.cookie_might_help("ERROR: The read operation timed out"), "")
ck("A4 内容不存在 / 已删除：不许重跑",
   not S.cookie_might_help("ERROR: [youtube] Video unavailable")
   and not S.cookie_might_help("ERROR: 作品不存在或已删除"), "")
ck("A5 空报错、None 都不算「值得」，也不抛",
   not S.cookie_might_help("") and not S.cookie_might_help(None) and not S.cookie_might_help("   "), "")
ck("A6 站点拒绝（403 / 地区限制）值得再试一次（会员与地区墙靠 Cookie）",
   S.cookie_might_help("ERROR: Unable to download JSON metadata: HTTP Error 403: Forbidden"), "")
ck("A7 认不出来的原始报错在别的平台上不硬编成「值得」：宁可少打一次",
   not S.cookie_might_help("ERROR: something we have never seen before")
   and not S.cookie_might_help("ERROR: something odd", "https://www.bilibili.com/video/BV1xx"), "")
ck("A8 YouTube 那句「一条流都不给」（活体读数 V1 的原话）值得带 Cookie 再打一次",
   S.cookie_might_help("ERROR: [youtube] aqz-KE-bpKQ: No video formats found;", YT) is True
   and S.cookie_might_help("提取失败: No video formats found", YT) is True, "")
ck("A8b 同样这句挂在 B 站就不重跑（那句话本身没说要被登录）",
   S.cookie_might_help("ERROR: [BiliBili] BV1xx: No video formats found;",
                       "https://www.bilibili.com/video/BV1xx") is False, "")
ck("A8c YouTube 上就算是 429 也不重跑：新增那条不许盖掉明确的排除",
   S.cookie_might_help("ERROR: [youtube] aqz: HTTP Error 429: Too Many Requests. "
                       "No video formats found", YT) is False,
   S.cookie_might_help("ERROR: HTTP Error 429 Too Many Requests. No video formats found", YT))
ck("A9 分类走的是既有 risk_control，YouTube 那条只是补在它够不着的形状上",
   "risk_control.classify_failure_text(raw)" in SRC
   and SRC.index("detect_platform(url or \"\") == \"youtube\"") < SRC.index("def cfg_without_cookie"), "")

print("== B. cfg_without_cookie：三条入口都关掉 ==")
full = {"cookie_source": "browser", "cookie_browser": "edge", "cookie_file": str(CKFILE),
        "platform_cookies": {"youtube": {"source": "file", "file": str(CKFILE)}},
        "cookie": "SESSDATA=abc", "http_headers": {"Cookie": "a=b", "Referer": "https://x"},
        "cookie_public_first": True, "proxy": "http://127.0.0.1:7890", "concurrent": 3}
bare = S.cfg_without_cookie(full)
ck("B1 全局来源 / 浏览器 / 文件三条都归零",
   bare["cookie_source"] == "none" and bare["cookie_browser"] == "" and bare["cookie_file"] == "", bare)
ck("B2 逐平台覆写整表清空（只清全局会漏：平台那一条优先级更高）",
   bare["platform_cookies"] == {}, bare["platform_cookies"])
ck("B3 手工粘的请求头 Cookie 也去掉，但同一字典里的其它头留着",
   "Cookie" not in bare["http_headers"] and bare["http_headers"].get("Referer") == "https://x",
   bare["http_headers"])
ck("B4 小写的 cookie 头一样去得掉（HTTP 头不分大小写，留着就是带了）",
   "Cookie" not in S.cfg_without_cookie({"http_headers": {"cookie": "a=b"}})["http_headers"], "")
ck("B5 与 Cookie 无关的设置一个字都不动（代理、并发不能跟着被清）",
   bare["proxy"] == "http://127.0.0.1:7890" and bare["concurrent"] == 3
   and bare["cookie_public_first"] is True, bare)
ck("B6 传进来的原字典不被改（配置副本不能写回真配置）",
   full["cookie_source"] == "browser" and full["platform_cookies"], full["cookie_source"])
ck("B7 空 / None 也不炸，回一份能用的字典",
   isinstance(S.cfg_without_cookie(None), dict) and S.cfg_without_cookie(None)["cookie_source"] == "none", "")

print("== C. 判定本身：记、取、过期、开关 ==")
E = S.engine
E.drop_cookie_pref()
ck("C0 normalize 是幂等的（后面三段都拿这一个 key 说话，不幂等就会各判各的）",
   S.normalize_url(YT) == YT and YT, (RAW_YT, YT))
ck("C1 没判过的回空串（空串 = 与从前同一条路）",
   E.cookie_pref_state(OK_CFG, YT) == "" and E.cookie_off(OK_CFG, YT) is False, "")
E.note_cookie_pref(YT, False)
ck("C2 记「匿名就能开」之后 cookie_off 为真",
   E.cookie_pref_state(OK_CFG, YT) == "anon" and E.cookie_off(OK_CFG, YT) is True, "")
E.note_cookie_pref(YT, True)
ck("C3 记「得带 Cookie」时不算 cookie_off（下载该照常带）",
   E.cookie_pref_state(OK_CFG, YT) == "cookie" and E.cookie_off(OK_CFG, YT) is False, "")
E.note_cookie_pref(YT, False)
ck("C4 开关一关，判定立刻不当数：现有行为一字不变",
   E.cookie_pref_state({"cookie_source": "file", "cookie_file": str(CKFILE)}, YT) == ""
   and E.cookie_off({"cookie_source": "file"}, YT) is False, "")
ck("C5 没有 url 时不猜（空串，绝不能回 anon 把 Cookie 关掉）",
   E.cookie_pref_state(OK_CFG, "") == "" and E.cookie_off(OK_CFG, "") is False
   and E.cookie_off(OK_CFG) is False, "")
E._cookie_pref[YT] = (time.time() - E._COOKIE_PREF_TTL - 5, False)
ck("C6 过期之后判定自己清掉，回空串重新判",
   E.cookie_pref_state(OK_CFG, YT) == "" and YT not in E._cookie_pref, list(E._cookie_pref))
E.note_cookie_pref(YT, False)
E.drop_cookie_pref(YT)
ck("C7 单条作废只动那一条",
   YT not in E._cookie_pref, "")
E.note_cookie_pref("https://a", False)
E.note_cookie_pref("https://b", True)
E.drop_cookie_pref()
ck("C8 不带参数 = 全清（Cookie 这一层改过之后要用它）",
   E._cookie_pref == {}, E._cookie_pref)
ck("C9 TTL 比解析缓存长：缓存过期后重新解析时，判定还在，不会又白打一次匿名",
   E._COOKIE_PREF_TTL > E._INFO_CACHE_TTL, [E._COOKIE_PREF_TTL, E._INFO_CACHE_TTL])
ck("C10 判定表是引擎上的（解析与下载读同一份），且初值为空",
   isinstance(E._cookie_pref, dict) and len(E._cookie_pref) == 0, E._cookie_pref)
ck("C11 作废一条时把用户输入那条与规范化那条一起丢掉（两张 key 都记过）",
   "for k in {url, normalize_url(url)}" in SRC, "")

print("== D. _cookie_source：判定是唯一出口 ==")
E.drop_cookie_pref()
ck("D1 开关关着：有 Cookie 就给 Cookie（与 1.3.1 一字不差）",
   E._cookie_source({"cookie_source": "file", "cookie_file": str(CKFILE)}, YT) == ("file", str(CKFILE)), "")
ck("D2 开关开着但没判过：照样给 Cookie（判过才收，第一次的判定来自解析本身）",
   E._cookie_source(OK_CFG, YT) == ("file", str(CKFILE)), "")
E.note_cookie_pref(YT, False)
ck("D3 判过「匿名就能开」：三条出口里最要紧的这条给 None",
   E._cookie_source(OK_CFG, YT) == (None, None), E._cookie_source(OK_CFG, YT))
E.note_cookie_pref(YT, True)
ck("D4 判过「得带 Cookie」：恢复给 Cookie",
   E._cookie_source(OK_CFG, YT) == ("file", str(CKFILE)), "")
E.note_cookie_pref(YT, False)
ck("D5 浏览器来源也一样被收（不只文件那条路）",
   E._cookie_source({"cookie_source": "browser", "cookie_browser": "chrome",
                     "cookie_public_first": True}, YT) == (None, None), "")
ck("D6 逐平台覆写的 Cookie 也收：判定问的是这条 URL 实际会用的那份",
   E._cookie_source({"cookie_source": "none", "cookie_public_first": True,
                     "platform_cookies": {"youtube": {"source": "file", "file": str(CKFILE)}}}, YT)
   == (None, None), "")
E.drop_cookie_pref()

print("== E. get_info 那条路：打几次、每次带的哪份配置 ==")
LOGS = []
CALLS = []
real_once = S.DownloaderEngine._get_info_once
ORIG_LOG = E.__dict__.get("log")   # log 是实例上的（构造函数里 self.log = log_cb），不是类方法


def install(script):
    """script: 每次 _get_info_once 依次返回的 (info, err)。

    替身按真实现的规矩写缓存位（成功才写），否则后面「缓存里留的是哪一份」几条断言就是空的。
    """
    del CALLS[:], LOGS[:]
    box = {"i": 0, "script": script}

    def fake(self, url, cfg, cache_key, now):
        item = box["script"][box["i"]] if box["i"] < len(box["script"]) else (None, "script exhausted")
        box["i"] += 1
        CALLS.append({"url": url, "cookie": bool(self._cookie_source(cfg, url)[0]),
                      "cache_key": cache_key})
        if item[0] is not None:
            self._info_cache[cache_key] = (now, item[0])
        return item

    S.DownloaderEngine._get_info_once = fake
    E.log = lambda m, level="info": LOGS.append(str(m))
    E._info_cache.pop(YT, None)
    E.drop_cookie_pref()


def parse(cfg, url=YT):
    return S.DownloaderEngine.get_info(E, url, cfg)


NOCK = {"cookie_source": "none"}
PREF0 = dict(E._cookie_pref)
CACHE0 = dict(E._info_cache)
try:
    # E1 开关关着：一次、带 Cookie、结果照原样回
    install([(None, "script exhausted")])
    ck("E1 开关关着 → 只打一次，且带的就是配置里那份 Cookie（老路一字不变）",
       parse({"cookie_source": "file", "cookie_file": str(CKFILE)}) is None
       and len(CALLS) == 1 and CALLS[0]["cookie"] is True, CALLS)
    ck("E2 开关关着时不产生任何判定（不然后果是「顺手记了一条没人看的结论」）",
       E._cookie_pref == {}, E._cookie_pref)

    # E3 没配 Cookie：也没必要两次
    install([(None, "script exhausted")])
    parse({"cookie_source": "none", "cookie_public_first": True})
    ck("E3 开着开关但这条本来就没 Cookie → 一次到底（不该假装「匿名先试」再打第二次）",
       len(CALLS) == 1 and CALLS[0]["cookie"] is False, CALLS)

    # E4 匿名解析开了，清单完整 → 就它了
    install([({"id": YT, "formats": DASH}, "")])
    got = parse(OK_CFG)
    ck("E4 匿名就解析开且清单没被裁 → 一次就收，不带 Cookie",
       len(CALLS) == 1 and CALLS[0]["cookie"] is False and got is not None, CALLS)
    ck("E5 记下「这条匿名就能开」，下载那侧跟着不带",
       E.cookie_off(OK_CFG, YT) is True, E._cookie_pref)
    ck("E6 日志说的是这条的真读数（几条流），不是从设置里读出来的期望",
       any("没带 Cookie 就解析开" in m and "2 条流" in m for m in LOGS), LOGS)
    ck("E7 匿名那份进了缓存位（第二次直接命中，不再打接口）",
       E._info_cache.get(YT, (None, None))[1] is got, list(E._info_cache)[:3])

    # E8 匿名成功但清单被裁（只有渐进流）→ 必须带 Cookie 再打
    install([({"id": YT, "formats": MUXED}, ""), ({"id": YT, "formats": DASH}, "")])
    got = parse(OK_CFG)
    ck("E8 匿名那份只有影音同条 → 不收，带 Cookie 再打一次（1.3.2 那个静默降质不能从后门回来）",
       len(CALLS) == 2 and CALLS[0]["cookie"] is False and CALLS[1]["cookie"] is True
       and got["formats"] is DASH, CALLS)
    ck("E9 这种情形记的是「得带 Cookie」，不是「匿名够用」",
       E.cookie_pref_state(OK_CFG, YT) == "cookie", E._cookie_pref)
    ck("E10 日志说清是哪一次的问题（「清单被裁」与「被挡」两支不能混）",
       any("匿名那份清单被裁" in m for m in LOGS), LOGS)
    ck("E11 缓存位最后留的是带 Cookie 那份完整清单（不是匿名那份低清）",
       E._info_cache[YT][1] is got and got["formats"] is DASH, "")

    # E12 匿名失败 + 登录墙 → 重跑
    install([(None, "ERROR: 请先登录后再观看"), ({"id": YT, "formats": DASH}, "")])
    got = parse(OK_CFG)
    ck("E12 匿名被登录墙挡 → 带 Cookie 再打一次，收下第二次的结果",
       len(CALLS) == 2 and CALLS[1]["cookie"] is True and got is not None, CALLS)
    ck("E13 被挡那支的话术是「匿名那一次被挡」，不是「清单被裁」",
       any("匿名那一次被挡" in m for m in LOGS) and not any("清单被裁" in m for m in LOGS), LOGS)

    # E14 匿名失败 + 429 → 不许重跑
    install([(None, "ERROR: HTTP Error 429: Too Many Requests")])
    ck("E14 匿名那次是 429 → 一次就收手，绝不带 Cookie 重跑",
       parse(OK_CFG) is None and len(CALLS) == 1, CALLS)
    ck("E15 这种失败不记判定（记了就等于把一次限流钉成 15 分钟的结论）",
       E._cookie_pref == {}, E._cookie_pref)
    ck("E16 日志说的是「不为此带 Cookie 重跑」，让人知道为什么没有第二次",
       any("不是登录墙" in m for m in LOGS), LOGS)

    # E17 匿名失败 + 网络错 → 同样不许重跑
    install([(None, "ERROR: [youtube] Unable to download API page: getaddrinfo failed")])
    parse(OK_CFG)
    ck("E17 网络错也只打一次", len(CALLS) == 1, CALLS)

    # E17b 活体读数 V1/V2 那对：匿名「一条流都不给」，带 Cookie 却有 43 条流到 2160p
    install([(None, "ERROR: [youtube] aqz-KE-bpKQ: No video formats found; please report"),
             ({"id": YT, "formats": DASH}, "")])
    got = parse(OK_CFG)
    ck("E17b YouTube 匿名回「No video formats found」→ 带 Cookie 再打一次，收下那份有流的",
       len(CALLS) == 2 and CALLS[1]["cookie"] is True and got is not None
       and got["formats"] is DASH, CALLS)
    ck("E17c 这条记下的是「得带 Cookie」（下次直接从带 Cookie 那次开始）",
       E.cookie_pref_state(OK_CFG, YT) == "cookie", E._cookie_pref)

    # E18 带 Cookie 那次反而没解析开 → 先吃已经拿到的匿名那份
    install([({"id": YT, "formats": MUXED}, ""), (None, "ERROR: HTTP Error 429: Too Many Requests")])
    got = parse(OK_CFG)
    ck("E18 带 Cookie 那次失败（活体读数里就是那次的 429）→ 先用已经拿到的匿名那份，别把能下的机会扔掉",
       len(CALLS) == 2 and got is not None and got["formats"] is MUXED, CALLS)
    ck("E19 判定仍留「得带 Cookie」：这份匿名清单是被裁的，钉成「匿名就够了」就是 15 分钟的静默降质",
       E.cookie_pref_state(OK_CFG, YT) == "cookie" and E.cookie_off(OK_CFG, YT) is False,
       E._cookie_pref)
    ck("E20 那次没解析开的原因与「下次还带 Cookie」都写进日志（不只写「用匿名那份」）",
       any("带 Cookie 那次没解析开" in m and "429" in m and "下次解析还带 Cookie" in m for m in LOGS), LOGS)

    # E21 两条都解析开，但带 Cookie 那份反而更低 → 用匿名那份，缓存位一起改回来
    install([({"id": YT, "formats": MUXED}, ""), ({"id": YT, "formats": LOWMUX}, "")])
    got = parse(OK_CFG)
    ck("E21 带 Cookie 那份最高只有 720、匿名那份 1080 → 收匿名那份（不是「带了就一定好」）",
       got is not None and got["formats"] is MUXED, CALLS)
    ck("E22 缓存位跟着结论改回匿名那份（否则 180 秒内点 1080 还是拿到被缓存的 720）",
       E._info_cache[YT][1]["formats"] is MUXED, E._info_cache[YT][1]["formats"])
    ck("E23 这条说的是「反而更低」，不是含糊的「用了另一份」",
       any("带 Cookie 那份反而更低" in m for m in LOGS), LOGS)

    # E24 判定命中「cookie」时不再重跑匿名
    install([(None, ""), ({"id": YT, "formats": DASH}, "")])
    E.drop_cookie_pref()
    E.note_cookie_pref(YT, True)
    parse(OK_CFG)
    ck("E24 判过「这条得带 Cookie」→ 直接带 Cookie 打，不再浪费一次匿名",
       len(CALLS) == 1 and CALLS[0]["cookie"] is True, CALLS)

    # E25 判定命中「anon」时走的是老路，但那次确实不带 Cookie
    install([({"id": YT, "formats": DASH}, "")])
    E.drop_cookie_pref()
    E.note_cookie_pref(YT, False)
    parse(OK_CFG)
    ck("E25 判过「匿名就能开」→ 一次到底且那次真不带 Cookie（下载沿用同一次判定）",
       len(CALLS) == 1 and CALLS[0]["cookie"] is False, CALLS)

    # E26 缓存命中时连接口都不必打
    install([({"id": YT, "formats": DASH}, "")])
    parse(OK_CFG)
    CALLS.clear()
    again = parse(OK_CFG)
    ck("E26 解析缓存内同一条直接命中，不再打第二次", len(CALLS) == 0 and again is not None, CALLS)

    # E27 短链展开过的那条：两张 key 都要记，否则下载侧读用户输入那条读不到判定
    E._cookie_pref.clear()
    install([({"id": "x", "title": "合集", "_type": "playlist", "entries": [{"id": 1}]}, "")])
    parse(OK_CFG, url="https://www.bilibili.com/video/BV1xx")
    ck("E27 播放列表那种没有 formats 的结果不被误判成「被裁」（一次就收）",
       len(CALLS) == 1 and E.cookie_off(OK_CFG, "https://www.bilibili.com/video/BV1xx") is True, CALLS)
finally:
    S.DownloaderEngine._get_info_once = real_once
    if ORIG_LOG is None:
        try:
            del E.log
        except Exception:
            pass
    else:
        E.log = ORIG_LOG
    E._cookie_pref.clear()
    E._cookie_pref.update(PREF0)
    E._info_cache.clear()
    E._info_cache.update(CACHE0)
    ck("E28 替身、日志钩子、判定表与缓存位都还原成进这段之前那样（引擎是全局单例，留着会串到后面的自检）",
       S.DownloaderEngine._get_info_once is real_once and E._cookie_pref == PREF0
       and E._info_cache == CACHE0 and E.__dict__.get("log") is ORIG_LOG,
       [E.__dict__.get("log"), len(E._cookie_pref), len(E._info_cache)])

print("== F. _anon_list_clipped：什么才算「匿名那份也能用」 ==")
ck("F1 YouTube：有独立视频轨（DASH）才算完整",
   S._anon_list_clipped({"formats": DASH}, YT) is False, "")
ck("F2 YouTube：只有影音同条 = 被裁（这份不能当答案）",
   S._anon_list_clipped({"formats": MUXED}, YT) is True, "")
ck("F3 YouTube：formats 空表也算被裁（没清单就没得下）",
   S._anon_list_clipped({"formats": []}, YT) is True and S._anon_list_clipped({"id": "x"}, YT) is True, "")
ck("F4 播放列表没有 formats，不参与这个判断（别把合集误判成被裁）",
   S._anon_list_clipped({"_type": "playlist", "entries": [{"id": 1}]}, YT) is False
   and S._anon_list_clipped({"entries": []}, YT) is False, "")
ck("F5 非 YouTube 不做这个判断（那边带不带 Cookie 是同一条客户端链）",
   S._anon_list_clipped({"formats": MUXED}, "https://www.bilibili.com/video/BV1xx") is False
   and S._anon_list_clipped({"formats": MUXED}, "https://v.douyin.com/xxx") is False, "")
ck("F6 None / 空 / 非字典都算被裁（保守：宁可再打一次也别收下没清单的结果）",
   S._anon_list_clipped(None, YT) is True and S._anon_list_clipped({}, YT) is True
   and S._anon_list_clipped("x", YT) is True, "")
ck("F7 youtu.be 短链也在 YouTube 判断里",
   S._anon_list_clipped({"formats": MUXED}, "https://youtu.be/abc") is True, "")
ck("F8 被裁判据用的是「有没有独立视频轨」，与分辨率高低无关（4K 渐进流照样是被裁）",
   S._anon_list_clipped({"formats": [{"vcodec": "avc1", "acodec": "mp4a", "height": 2160}]}, YT) is True, "")

print("== G. Cookie 这一层被改过：判定作废 ==")
ck("G1 作废函数存在且不带参数就清全表",
   "def drop_all_cookie_prefs():" in SRC and "engine.drop_cookie_pref()" in SRC, "")
for k in S.COOKIE_LAYER_KEYS:
    ck(f"G2 「{k}」在 Cookie 层键表里（保存设置改到它就该重判）", k in S.COOKIE_LAYER_KEYS, "")
ck("G3 保存设置那条闸门按键表判断，不是写死一两个键名",
   "if any(k in data for k in COOKIE_LAYER_KEYS):" in SRC, "")
_ap = SRC[SRC.index("def _apply_config("):SRC.index('@app.post("/api/config/reset")')]
ck("G4 作废发生在落盘之后（否则读到的还是旧配置，白判）",
   _ap.index("cfg.save()") < _ap.index("drop_all_cookie_prefs()"), "")
ck("G5 平台 Cookie 三个写入口都作废（设置条目 / 上传文件 / 粘贴文本）",
   SRC.count("drop_all_cookie_prefs()") >= 6, SRC.count("drop_all_cookie_prefs()"))
ck("G6 CookieCloud 只在真写了文件时作废（内容一样不该把全表清掉）",
   'changed = [w for w in written if w["changed"]]' in SRC
   and SRC.index('changed = [w for w in written if w["changed"]]')
   < SRC.index("drop_all_cookie_prefs()", SRC.index('changed = [w for w in written')), "")
ck("G7 扫码登录拿到 Cookie 也作废（那条原本可能被判「匿名就被挡」）",
   "drop_all_cookie_prefs()" in SRC[max(0, SRC.index("登录成功，Cookie 已保存") - 500):
                                    SRC.index("登录成功，Cookie 已保存")], "")
ck("G8 单条重试带了 Cookie 相关参数时只作废那一条（别把别人的判定一起清）",
   "self.engine.drop_cookie_pref(t.url)" in SRC, "")
ck("G9 键表也含 cookie_public_first：开关本身一拧就重判（关掉就该马上恢复带 Cookie）",
   "cookie_public_first" in S.COOKIE_LAYER_KEYS, S.COOKIE_LAYER_KEYS)
ck("G10 直播聊天那一支照旧按配置直接带 Cookie（会员直播的聊天没有匿名退路，不归本开关管）",
   SRC.index('pc = (cfg.data.get("platform_cookies") or {}).get("youtube") or {}')
   < SRC.index("class DownloaderEngine"), "")

print("== H. 下载侧沿用同一次判定 ==")
_run_start = SRC.index("    def _run(self, task: DownloadTask):")
_run = SRC[_run_start:_run_start + 40 + re.search(r"\n    def ", SRC[_run_start + 40:]).end()]
ck("H1 直链那支的请求头 Cookie 也跟着判定（判定说不带就不能只在那一支偷偷带）",
   'hdrs.pop("Cookie", None)' in _run and "cookie_off(cfg" in _run, "")
ck("H2 两处 URL 都问（短链展开过一次，用户输入那条与真地址那条都得拦）",
   _run.count("cookie_off(cfg") >= 2, _run.count("cookie_off(cfg"))
ck("H3 `_cookie_source` 是唯一出口：客户端链、opts、直链头都从它走，不各写一套",
   "if self.cookie_off(cfg, url):\n            return None, None" in SRC
   and SRC.count("cookie_off(") >= 5, SRC.count("cookie_off("))
ck("H4 `_ydl_opts` 里手工那串 Cookie 也问 cookie_off（cfg.cookie 是第四条入口）",
   "and not self.cookie_off(cfg, url)" in SRC, "")
ck("H5 判定表与 TTL 挂在引擎上（不是函数里的局部，否则下载侧读不到）",
   "_cookie_pref: Dict[str, tuple] = {}" in SRC and "_COOKIE_PREF_TTL = 900" in SRC, "")
ck("H6 客户端链也跟着同一判定（带 Cookie 时 yt-dlp 会跳过 android/ios，两次尝试本就不是同一份清单）",
   "if self._cookie_source(cfg, url)[0]:" in SRC, "")

print("== K. 真的 opts 字典：_ydl_opts 那一侧收不收 ==")


def _opts(cfg, note=None):
    E.drop_cookie_pref()
    if note is not None:
        E.note_cookie_pref(YT, note)
    o = E._ydl_opts(cfg, for_info=True, url=YT)
    E.drop_cookie_pref()
    return o


_ck_start = SRC.index("        ck_kind, ck_val = self._cookie_source(cfg, url)")
_ck_end = SRC.index('        elif ck_kind == "file":', _ck_start)
_ck_block = SRC[_ck_start:_ck_end + 90]
ck("K0 _ydl_opts 离线可调用（这一支不打网络，只拼字典）",
   isinstance(_opts(NOCK), dict) and "cookiefile" not in _opts(NOCK), "")
ck("K1 有 Cookie 时 opts 真带 cookiefile（判定说不带时才没有，靠的是 _cookie_source 那一条）",
   _opts(OK_CFG).get("cookiefile") == str(CKFILE), _opts(OK_CFG).get("cookiefile"))
ck("K2 判过「匿名就能开」之后 cookiefile 与 cookiesfrombrowser 都没有",
   "cookiefile" not in _opts(OK_CFG, note=False)
   and "cookiesfrombrowser" not in _opts(OK_CFG, note=False), _opts(OK_CFG, note=False))
ck("K3 判过「得带 Cookie」时照旧带上（判定不是「一律不带」的开关）",
   _opts(OK_CFG, note=True).get("cookiefile") == str(CKFILE), "")
ck("K4 Cookie 交给 yt-dlp 是两条不同的口：文件走 cookiefile，浏览器走 cookiesfrombrowser",
   'opts["cookiesfrombrowser"] = (ck_val' in _ck_block and 'opts["cookiefile"] = ck_val' in _ck_block,
   _ck_block[-140:])
ck("K5 全文件里这两处赋值各只有一处（直播聊天那支用的是另一份 yopts，不从这里绕）",
   len(re.findall(r'\bopts\["cookiefile"\]', SRC)) == 1
   and len(re.findall(r'\bopts\["cookiesfrombrowser"\]', SRC)) == 1,
   [len(re.findall(r'\bopts\["cookiefile"\]', SRC)), len(re.findall(r'\bopts\["cookiesfrombrowser"\]', SRC))])
ck("K6 客户端链也按这条 URL 问判定（_yt_player_chain 收到 url，不是只看全局配置）",
   "self._yt_player_chain(cfg, url)" in SRC, "")
ck("K7 手工粘的那串 Cookie 走请求头，也被同一条判定拦下（第四条入口不在 _cookie_source 里）",
   'if cfg.get("cookie") and "Cookie" not in hdrs and not self.cookie_off(cfg, url):' in SRC, "")
E.note_cookie_pref(YT, False)
ck("K8 浏览器来源那条也被收：它走的是 cookiesfrombrowser，同样由 _cookie_source 决定",
   E._cookie_source({"cookie_source": "browser", "cookie_browser": "chrome",
                     "cookie_public_first": True}, YT) == (None, None), "")
E.drop_cookie_pref()

print("== I. 接线：默认值 → ConfigBody → 界面 ==")
ck("I0 锚点都在（改动挪走了就先报这一条，别让整段崩）",
   '"cookie_public_first": False' in SRC and "cookie_public_first: Optional[bool] = None" in SRC
   and "tr('settings.publicHintP1')" in HTML, "")
ck("I1 默认关（「现有行为一字不变」这条要靠默认值兑现）",
   S.cfg.DEFAULTS["cookie_public_first"] is False, S.cfg.DEFAULTS.get("cookie_public_first"))
ck("I2 ConfigBody 真声明了这个键（没声明的键会在 model_dump 那步静默丢掉 —— G2 那类 bug）",
   "cookie_public_first" in S.ConfigBody.model_fields, sorted(S.ConfigBody.model_fields)[:4])
_fields = set(S.ConfigBody.model_fields)
_vm = set(re.findall(r'v-model="settings\.([a-z0-9_]+)"', HTML))
ck("I3 界面这个键后端收得下、默认表里有名字（三处一致）",
   "cookie_public_first" in _fields and "cookie_public_first" in S.cfg.DEFAULTS
   and "cookie_public_first" in _vm, sorted(_vm - _fields)[:6])
ck("I4 人话名表也叫得出这个键（「恢复默认」那栏才点得动它）",
   '"cookie_public_first": \'settings.cfg.cookie_public_first\'' in HTML
   and re.search(r'const CFG_KEYS = \{(.*?)\n        \};', HTML, re.S) is not None, "")
ck("I5 界面有开关本体（不是只有一句说明）",
   'v-model="settings.cookie_public_first"' in HTML, "")
ck("I6 loadConfig 把这个键读回来（!! 转真布尔，后端没给也不算打开）",
   "settings.value.cookie_public_first = !!data.cookie_public_first;" in HTML, "")
ck("I7 界面默认值表里也有这条（没这条第一次渲染就是 undefined，保存时会写进真配置）",
   "cookie_public_first: false," in HTML, "")
ck("I8 说明里写清了默认关与「哪三种失败不重跑」（不然用户以为每次都会打两遍）",
   "tr('settings.publicHintB5')" in HTML
   and "默认关" in ZH.get("settings.publicHintP1", "")
   and "429 限流、连不上、内容不存在" in ZH.get("settings.publicHintB5", ""), "")
ck("I9 说明里点明连下载也不带（这一条决定的是整趟，不只是解析）",
   "tr('settings.publicHintB4')" in HTML and "连下载也不带" in ZH.get("settings.publicHintB4", ""), "")
ck("I10 逐平台 Cookie 的优先级没被这条改动（开关只决定第一次带不带）",
   "tr('settings.publicHintP8')" in HTML
   and "逐平台" in ZH.get("settings.publicHintP8", "")
   and "只决定「第一次要不要带」" in ZH.get("settings.publicHintP8", ""), "")
ck("I11 get_info 拆成两层：公开优先在门面，原解析本体一字未改地留在 _get_info_once",
   "def get_info(self, url: str, cfg: dict) -> Optional[Dict]:" in SRC
   and "def _get_info_once(self, url: str, cfg: dict, cache_key: str, now: float)" in SRC, "")
ck("I12 匿名那次用的确实是清干净的配置（这一句是全开关的心脏）",
   "self._get_info_once(url, cfg_without_cookie(cfg), cache_key, now)" in SRC, "")
ck("I13 失败那份原始报错真的接住了（回 (info, err) 而不是丢掉，否则判定无从下手）",
   "anon, anon_err = self._get_info_once" in SRC and "return None, last_err" in SRC, "")
ck("I14 匿名失败且不值得重跑时立刻收手（这条 if 必须在第二次调用之前）",
   SRC.index("if anon is None and not cookie_might_help(anon_err, url):")
   < SRC.index("got, got_err = self._get_info_once"), "")
ck("I14b 判定收的是这条 URL（不传 url 就认不了 YouTube 那种「一条流都不给」）",
   "cookie_might_help(anon_err, url)" in SRC, "")
ck("I15 风控分类走的是既有 risk_control，没有另起一套判定",
   "risk_control.classify_failure_text(raw)" in SRC, "")

print("== J. 真文件：不碰本机那份 Cookie 与配置 ==")
ck("J1 自检写的全在临时目录（本机 cookies/ 一个字节都不该被改）",
   str(CKFILE).startswith(str(TMP)) and TMP.exists(), CKFILE)
ck("J2 引擎那份判定表跑完是空的（判定不外泄到真下载）",
   S.engine._cookie_pref == {}, S.engine._cookie_pref)
ck("J3 缓存位也没被这段留东西（替身写进去的已清）",
   YT not in S.engine._info_cache, list(S.engine._info_cache)[:4])
ck("J4 真配置没被这段改过（cookie 相关三项原样）",
   S.cfg.data.get("cookie_public_first") in (False, None)
   and S.cfg.data.get("cookie_source") in ("none", "file", "browser"), S.cfg.data.get("cookie_source"))

print(f"\nTOTAL {TOTAL}  FAILED: {len(FAILED)}")
for f in FAILED:
    print(" - " + f)
sys.exit(1 if FAILED else 0)
