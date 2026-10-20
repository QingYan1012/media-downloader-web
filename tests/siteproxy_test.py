r"""站点识别表 → 代理归属 → 界面行：一条链的离线自检。

为什么要单独一套：10-13 对着 qiaomu-download 那份平台清单盘 ours 时发现，
`PROXY_NEEDED_PLATFORMS` 里早就写了 facebook / twitch / reddit，可 `PLATFORM_RULES`
根本没有这三个键 —— `detect_platform` 对它们的 URL 永远回 "default"，集合里那三项
等于死代码：既判不到「要走代理」，用户在「网络策略」里也看不到这几行，没法单独指定。
vimeo / soundcloud / linkedin / 微博 / AcFun 则是整站落在 inherit（跟随系统）档，
代理一抖就跟着抖，而它们本来该有明确归属。

这一套钉的是「表与集合不许再脱节」：集合里写了键，就必须有 URL 能识别出那个键。
I 段管的是这条链的最后一环 —— 「清空并重置网络」回给界面的那份清空项名单：
项名原来是写死的中文（英文界面直接印出来），现在改回语言中立的 key，中文原话只留给日志。
全程只读，不联网、不起服务、不写 config.json（判 override 用临时 dict 喂 _decide_by_key，
C 段的判定同样喂临时 dict 并把 system_proxy 钉成空 —— 这一轮它吃过真 config 里那台机器的代理
地址，机器上代理一关就有 12 条红，而那张表一个字都没动）。

跑法：PYTHONIOENCODING=utf-8 python tests/siteproxy_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED = []
TOTAL = 0


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{str(extra)[:300]}]")


# 本轮补的 8 个站点：一个代表 URL + 它该走的那一档
NEW_PLATS = [
    ("facebook", "https://www.facebook.com/watch/?v=101059", "proxy"),
    ("twitch", "https://www.twitch.tv/videos/187294", "proxy"),
    ("reddit", "https://www.reddit.com/r/all/comments/abc/", "proxy"),
    ("vimeo", "https://vimeo.com/76979871", "proxy"),
    ("soundcloud", "https://soundcloud.com/artist/track", "proxy"),
    ("linkedin", "https://www.linkedin.com/posts/x_activity", "proxy"),
    ("weibo", "https://weibo.com/tv/show/1034:5000", "direct"),
    ("acfun", "https://www.acfun.cn/v/ac4000000", "direct"),
]
# 原来就在表里的站点：改动不能把它们挪位
OLD_PLATS = [
    ("youtube", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "proxy"),
    ("bilibili", "https://www.bilibili.com/video/BV1xx411c7mD", "direct"),
    ("douyin", "https://v.douyin.com/ijkl/", "direct"),
    ("xiaohongshu", "https://www.xiaohongshu.com/explore/abc", "direct"),
    ("instagram", "https://www.instagram.com/reel/Cabc/", "proxy"),
    ("twitter", "https://x.com/vista8/status/2100589909136523770", "proxy"),
    ("pinterest", "https://pin.it/abcdef", "proxy"),
    ("weixin", "https://weixin.qq.com/sph/Abc123", "direct"),
    ("telegram", "https://t.me/somechannel/123", "proxy"),
    ("xinpianchang", "https://www.xinpianchang.com/a123456", "direct"),
]

print("== A. 识别：新补的 8 个站点要认得出键 ==")
rules_keys = {k for k, _ in S.PLATFORM_RULES}
for key, url, _want in NEW_PLATS:
    ck(f"A {key} 在 PLATFORM_RULES 里有键", key in rules_keys, sorted(rules_keys))
    ck(f"A {key} 的 URL 认成 {key}", S.detect_platform(url) == key, S.detect_platform(url))
    ck(f"A {key} 在 PLATFORM_LABELS 里有中文名", key in S.PLATFORM_LABELS, S.PLATFORM_LABELS.get(key))

print("== B. 归属：集合里的键必须有 URL 能识别到（否则就是死代码） ==")
reachable = {k for k, _ in S.PLATFORM_RULES} | {S.PROXY_TIKTOK_HINT}
dead = sorted((S.PROXY_NEEDED_PLATFORMS | S.PROXY_DIRECT_PLATFORMS) - reachable)
ck("B1 PROXY_NEEDED/DIRECT 里没有识别不到的键", not dead, dead)
ck("B2 facebook/twitch/reddit 不再只是集合里的摆设",
   all(k in rules_keys for k in ("facebook", "twitch", "reddit")), sorted(rules_keys))
ck("B3 两套集合互斥（同一站既直连又代理=判不出来）",
   not (S.PROXY_NEEDED_PLATFORMS & S.PROXY_DIRECT_PLATFORMS),
   S.PROXY_NEEDED_PLATFORMS & S.PROXY_DIRECT_PLATFORMS)
ck("B4 表与标签不脱节：PLATFORM_RULES 的键都有标签",
   not (rules_keys - set(S.PLATFORM_LABELS)), sorted(rules_keys - set(S.PLATFORM_LABELS)))
ck("B5 反向：标签里除 default 外都在表里（Cookie 列表不会多出认不出的行）",
   not (set(S.PLATFORM_LABELS) - rules_keys - {"default"}),
   sorted(set(S.PLATFORM_LABELS) - rules_keys - {"default"}))

print("== C. 判定：新站走代理，国内站直连，认不出的仍交回系统 ==")
# 这一段以前吃的是真 config 里那台机器的代理地址：机器上代理一关，12 条「该走代理」一起变红，
# 而这张表一个字都没动。判定要看的是表与档的对应关系，所以这里自带一份 cfg，系统代理也钉成没有。
_C_PROXY = {"proxy": "http://127.0.0.1:9999", "proxy_mode": "auto", "proxy_by_platform": {}}
_C_NONE = {"proxy": "", "proxy_mode": "auto", "proxy_by_platform": {}}
_REAL_SYS_PROXY = S.system_proxy
S.system_proxy = lambda *a, **k: ""          # 钉死「机器上此刻没有系统代理」，读数与 VPN 开关脱钩
try:
    for key, url, want in NEW_PLATS + OLD_PLATS:
        got = S.proxy_decision(url, cfg_data=_C_PROXY)
        ck(f"C {key} 判成 {want}", got[0] == want, got)
    ck("C 认不出的站还是 inherit（别把能下的东西判死）",
       S.proxy_decision("https://example.com/media.mp4", cfg_data=_C_NONE) == ("inherit", ""),
       S.proxy_decision("https://example.com/media.mp4", cfg_data=_C_NONE))
    ck("C 认不出的站但用户手填了代理：照用手填的，不把系统代理硬塞给它",
       S.proxy_decision("https://example.com/media.mp4", cfg_data=_C_PROXY)
       == ("proxy", "http://127.0.0.1:9999"),
       S.proxy_decision("https://example.com/media.mp4", cfg_data=_C_PROXY))
    ck("C TikTok 从抖音键里拆出来单独走代理（这轮没动它，钉住别再并回去）",
       S.proxy_platform_key("https://www.tiktok.com/@u/video/1") == "tiktok"
       and S.proxy_decision("https://www.tiktok.com/@u/video/1", cfg_data=_C_PROXY)[0] == "proxy"
       and S.proxy_decision("https://v.douyin.com/ijkl/", cfg_data=_C_PROXY)[0] == "direct",
       S.proxy_platform_key("https://www.tiktok.com/@u/video/1"))
finally:
    S.system_proxy = _REAL_SYS_PROXY

print("== D. 手动指定压过默认：新键也能单独改 ==")
d_proxy = {"proxy": "http://127.0.0.1:9999", "proxy_mode": "auto", "proxy_by_platform": {"vimeo": False}}
ck("D1 用户把 Vimeo 指成直连 → direct（不再只有老十站能单独指定）",
   S._decide_by_key("vimeo", d_proxy) == ("direct", ""), S._decide_by_key("vimeo", d_proxy))
d_direct = {"proxy": "http://127.0.0.1:9999", "proxy_mode": "auto", "proxy_by_platform": {"weibo": True}}
ck("D2 用户把微博指成走代理 → proxy 且带上填的地址",
   S._decide_by_key("weibo", d_direct) == ("proxy", "http://127.0.0.1:9999"),
   S._decide_by_key("weibo", d_direct))
ck("D3 「全部跟随系统」时新键也不插手",
   S._decide_by_key("facebook", {"proxy_mode": "none", "proxy": "http://127.0.0.1:9999"}) == ("inherit", ""),
   S._decide_by_key("facebook", {"proxy_mode": "none", "proxy": "http://127.0.0.1:9999"}))
ck("D4 「始终走代理」时国内站也出去",
   S._decide_by_key("bilibili", {"proxy_mode": "always", "proxy": "http://127.0.0.1:9999"})
   == ("proxy", "http://127.0.0.1:9999"))
# 这台机器真有系统代理，所以不能钉死返回哪一档，只能钉「没票时不会被判成 direct」
d_none = S._decide_by_key("vimeo", {"proxy_mode": "auto", "proxy": ""})
ck("D5 没填代理时新站不会被判成强制直连（那是杀 YouTube 的老毛病）",
   d_none[0] != "direct", d_none)

print("== E. 界面行：「网络策略」表要把新站列出来 ==")
rows = {r["key"]: r for r in S.net_policy_rows(
    {"proxy": "http://127.0.0.1:9999", "proxy_mode": "auto", "platform_cookies": {}})}
for key, _url, want in NEW_PLATS:
    r = rows.get(key) or {}
    ck(f"E {key} 在「网络策略」里有行且判成 {want}",
       r.get("verdict") == want and bool(r.get("label")), r)
ck("E1 出国档的 needs_by_default 为真（界面那列的勾要对）",
   all(rows[k]["needs_by_default"] for k, _u, w in NEW_PLATS if w == "proxy"),
   {k: rows.get(k, {}).get("needs_by_default") for k, _u, _w in NEW_PLATS})
ck("E2 default 行仍在（认不出的站要能看见自己走的是哪档）", "default" in rows, sorted(rows))
ck("E3 tiktok 单独一行，不跟抖音共用标签",
   rows.get("tiktok", {}).get("label") == "TikTok" and rows.get("douyin", {}).get("label") != "TikTok",
   [rows.get("tiktok"), rows.get("douyin")])
ck("E4 行数 = 表里的站点 + tiktok + default + 音乐源（没有漏项也没有重复）",
   len(S.net_policy_rows({"proxy_mode": "auto"})) == len(S.PLATFORM_RULES) + 2 + len(S.NET_MUSIC_SOURCES),
   len(S.net_policy_rows({"proxy_mode": "auto"})))

print("== F. Cookie 归属：多出的键不能凭空要吃票 ==")
fake = {"cookie_source": "browser", "cookie_browser": "chrome", "platform_cookies": {}}
ck("F1 新站没单独配 Cookie 时，仍跟随全局设置（不会因为表里多了键就没票）",
   S.engine._cookie_source(fake, "https://vimeo.com/76979871") == ("browser", "chrome"),
   S.engine._cookie_source(fake, "https://vimeo.com/76979871"))
# 「选了来源但文件不存在」按定义算没有 Cookie，所以这里喂一个必然存在的路径
real = str(Path(S.__file__))
fake2 = {"cookie_source": "none", "platform_cookies": {"facebook": {"source": "file", "file": real}}}
ck("F2 新站单独配了文件时按自己那份走",
   S.engine._cookie_source(fake2, "https://www.facebook.com/watch/?v=1") == ("file", real),
   S.engine._cookie_source(fake2, "https://www.facebook.com/watch/?v=1"))
fake3 = {"cookie_source": "browser", "cookie_browser": "edge",
         "platform_cookies": {"vimeo": {"source": "file", "file": str(Path(S.__file__).parent / "siteproxy_no_such.txt")}}}
ck("F3 反向：新站配了个不存在的文件时不会退回全局，是「没有 Cookie」",
   S.engine._cookie_source(fake3, "https://vimeo.com/76979871") == (None, None),
   S.engine._cookie_source(fake3, "https://vimeo.com/76979871"))

print("== G. 顺序与误认：URL 里顺带出现别的站点名 ==")
ck("G1 抖音分享链接里带着 vimeo.com 也只认前面的 douyin（表的顺序=优先级）",
   S.detect_platform("https://www.douyin.com/user/x?u=https://vimeo.com/1") == "douyin",
   S.detect_platform("https://www.douyin.com/user/x?u=https://vimeo.com/1"))
ck("G2 b23.tv 仍归 B 站", S.detect_platform("https://b23.tv/abcdef") == "bilibili")
ck("G3 空串/None 不炸且落 default",
   S.detect_platform("") == "default" and S.detect_platform(None) == "default")
ck("G4 fb.watch 短链归 Facebook（新加的三条域名里最容易被忽略的一条）",
   S.detect_platform("https://fb.watch/zz9") == "facebook", S.detect_platform("https://fb.watch/zz9"))

print("== H. 接线（静态钉住，改漏就红） ==")
src = Path(S.__file__).read_text(encoding="utf-8")
for key in ("facebook", "twitch", "reddit", "vimeo", "soundcloud", "linkedin", "weibo", "acfun"):
    ck(f"H {key} 在 PLATFORM_RULES 段落里（不是只在集合里）",
       f'("{key}", (' in src, key)

print("== I. 网络重置的回话（#92：界面按 key 取词表，中文原话只留给日志） ==")
import re as _re  # noqa: E402
_CJK = _re.compile(r"[\u4e00-\u9fff]")
FAKE_PROXY = "http://proxy.invalid:1"


class FakeCfgI:
    def __init__(self, data):
        self.data = dict(data)
        self.saved = 0

    def save(self):
        self.saved += 1          # 只计数，绝不落盘（这套件的承诺是不写 config.json）


class FakeLogI:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info", k="", kv=None):
        self.rows.append((level, str(msg), k, kv or {}))
        return True


class _Sniffer:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail

    def clear(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("profile 被占用")


_REAL_I = (S.cfg, S.log_mgr, S.browser_sniffer, S.net_info_payload)
try:
    S.log_mgr = FakeLogI()
    S.net_info_payload = lambda: {"ok": True, "platforms": []}   # 别去探本机系统代理

    sn = _Sniffer()
    S.browser_sniffer = sn
    S.cfg = FakeCfgI({"proxy": FAKE_PROXY, "proxy_mode": "custom",
                      "proxy_by_platform": {"youtube": FAKE_PROXY}})
    r = S.api_net_reset()
    ck("I1 三项都清了：界面拿到的 cleared_keys 是语言中立的项名",
       r["cleared_keys"] == ["proxy", "proxy_by_platform", "sniffed_list"], str(r)[:220])
    ck("I2 cleared_keys 里一个汉字都不许有（英文界面直接 join 它）",
       not any(_CJK.search(x) for x in r["cleared_keys"]), str(r["cleared_keys"]))
    ck("I3 两份一一对应，次序一致（对不上就有一条回落成中文原话）",
       len(r["cleared"]) == len(r["cleared_keys"]),
       f"{r['cleared']} / {r['cleared_keys']}")
    ck("I4 中文原话照旧回着（日志和老调用方还要用）",
       r["cleared"] == ["代理地址", "按平台代理策略", "嗅探到的资源列表"], str(r["cleared"]))
    ck("I5 真清了：代理与按平台策略回默认、档位回 auto、profile 清了一次",
       S.cfg.data["proxy"] == "" and S.cfg.data["proxy_by_platform"] == {}
       and S.cfg.data["proxy_mode"] == "auto" and sn.calls == 1 and S.cfg.saved == 1,
       str(S.cfg.data)[:200])
    ck("I6 日志那句写的还是中文原话，不是键名",
       any("代理地址" in m and "proxy_by_platform" not in m for _, m, _, _ in S.log_mgr.rows),
       str(S.log_mgr.rows)[:220])

    S.cfg = FakeCfgI({"proxy": "", "proxy_mode": "auto", "proxy_by_platform": {}})
    sn = _Sniffer()
    S.browser_sniffer = sn
    r2 = S.api_net_reset()
    ck("I7 本来就没东西：只报嗅探列表这一项，不谎报清了三样",
       r2["cleared_keys"] == ["sniffed_list"] and r2["cleared"] == ["嗅探到的资源列表"],
       str(r2)[:220])

    S.browser_sniffer = _Sniffer(fail=True)
    S.cfg = FakeCfgI({"proxy": FAKE_PROXY, "proxy_mode": "custom", "proxy_by_platform": {}})
    r3 = S.api_net_reset()
    ck("I8 profile 清不掉时不把它写进两份名单（英文不会多出「list of sniffed resources」）",
       r3["cleared"] == ["代理地址"] and r3["cleared_keys"] == ["proxy"], str(r3)[:220])
    ck("I9 清不掉那次的告警仍进日志（带 srv 键）",
       any("profile" in m for _, m, _, _ in S.log_mgr.rows[-2:]), str(S.log_mgr.rows[-2:])[:220])
finally:
    S.cfg, S.log_mgr, S.browser_sniffer, S.net_info_payload = _REAL_I

print(f"\nTOTAL {TOTAL} FAILED: {', '.join(FAILED) if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
