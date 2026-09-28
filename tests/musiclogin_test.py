r"""音乐平台登录 Cookie + 网易云扫码登录自检（④）。

全程离线：requests 整个换掉假模块，绝不碰网易云的服务器；cfg / log_mgr 都换成内存替身，
不写 config.json、不写运行日志。HTTP 断言直接调视图函数（本机进程还是旧代码）。

反向验证在两处：
  F 段把「必需键」表 temporarily 放宽，证明 803 那条失败分支真是这道闸门挡的；
  G 段把平台 Cookie 清空，证明订阅扫描里那串 Cookie 真是从这条链上来的。

跑法：`python tests/musiclogin_test.py`
"""
from __future__ import annotations

import json
import sys
import time as _real_time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []
CLOCK = [1_700_000_000.0]
SECRET = "MUSIC_U=super-secret-value-8f31"

UNIQ = "https://music.163.com/api/login/qrcode/unikey"
POLL = "https://music.163.com/api/login/qrcode/client/login"


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def last_log():
    return LOGS[-1] if LOGS else ""


# ---------------------------------------------------------------- 假组件
class FakeCfg:
    def __init__(self, **kw):
        d = dict(S.ConfigManager.DEFAULTS)
        d.update(kw)
        self.data = d
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeLogMgr:
    def log(self, msg, lv="info"):
        LOGS.append(str(msg))


class FakeTime:
    def time(self):
        return CLOCK[0]

    def strftime(self, fmt):
        return _real_time.strftime(fmt)


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeCookie:
    def __init__(self, name, value):
        self.name, self.value = name, value


class FakeSession:
    """一个会话一份剧本：{url: (payload, 要往 jar 里加的 cookie 名值)}；payload 是 Exception 就抛。"""

    instances: list = []

    def __init__(self, script=None):
        self.script = dict(script or {})
        self.cookies: list = []
        self.calls: list = []
        self.headers = {}
        FakeSession.instances.append(self)

    def add_cookie(self, name, value):
        self.cookies = [c for c in self.cookies if c.name != name] + [FakeCookie(name, value)]

    def post(self, url, data=None, timeout=None, **_kw):
        self.calls.append((url, dict(data or {}), timeout))
        payload, jar = self.script.get(url, ({"code": 500, "message": "脚本没写这条"}, []))
        if isinstance(payload, Exception):
            raise payload
        for name, value in (jar or []):
            self.add_cookie(name, value)
        return FakeResp(payload)


class FakeRequestsModule:
    """只替 Session：扫码这条链只用会话，别的接口在本测试里不碰网络。"""

    def __init__(self, script=None):
        self.script = dict(script or {})

    def Session(self):
        return FakeSession(self.script)


ORIG = {"cfg": S.cfg, "log_mgr": S.log_mgr, "time": S.time, "requests": S.requests}


def reset(**cfgkw):
    FakeSession.instances = []
    S.cfg = FakeCfg(**cfgkw)
    S.log_mgr = FakeLogMgr()
    S.time = FakeTime()
    LOGS.clear()
    CLOCK[0] = 1_700_000_000.0


def restore():
    S.cfg, S.log_mgr, S.time, S.requests = ORIG["cfg"], ORIG["log_mgr"], ORIG["time"], ORIG["requests"]


def http_error(view, *a, **kw):
    """调视图函数，把 HTTPException 翻成 (status, detail)，别的异常照样炸出来。"""
    try:
        return 200, view(*a, **kw)
    except S.HTTPException as e:
        return e.status_code, e.detail


# ---------------------------------------------------------------- 1. Cookie 文本解析
print("=== A. 粘贴进来的 Cookie 什么写法都有，都得认 ===")
reset()
p = S._parse_cookie_pairs("MUSIC_U=abc; NMTID=xyz")
ck("A1 标准请求头写法", p == {"MUSIC_U": "abc", "NMTID": "xyz"}, p)
ck("A2 键名大小写原样保留（MUSIC_U 不能变成小写）", "MUSIC_U" in p, p)
ck("A3 带引号的值会剥掉引号", S._parse_cookie_pairs('a="1"; b=2') == {"a": "1", "b": "2"})
ck("A4 整行连着 Cookie: 头名一起粘也要认", S._parse_cookie_pairs("Cookie: MUSIC_U=abc; NMTID=xyz") == {"MUSIC_U": "abc", "NMTID": "xyz"},
   S._parse_cookie_pairs("Cookie: MUSIC_U=abc; NMTID=xyz"))
ck("A5 小写 cookie: 前缀同样认", S._parse_cookie_pairs("cookie: MUSIC_U=abc") == {"MUSIC_U": "abc"})
netscape = ("# Netscape HTTP Cookie File\n"
            ".music.163.com\tTRUE\t/\tTRUE\t1900000000\tMUSIC_U\tns-value\n"
            ".music.163.com\tTRUE\t/\tFALSE\t0\tNMTID\tns-nmtid\n")
ck("A6 Netscape 文件写法也认", S._parse_cookie_pairs(netscape) == {"MUSIC_U": "ns-value", "NMTID": "ns-nmtid"},
   S._parse_cookie_pairs(netscape))
ck("A7 注释行不当 Cookie", "#" not in " ".join(S._parse_cookie_pairs(netscape)))
ck("A8 带空格的怪值走兜底切分", S._parse_cookie_pairs("MUSIC_U=abc def") == {"MUSIC_U": "abc def"},
   S._parse_cookie_pairs("MUSIC_U=abc def"))
ck("A9 没有等号的垃圾不产出键", S._parse_cookie_pairs("随手粘的一段网页文字") == {})
ck("A10 空串与 None 都是空", S._parse_cookie_pairs("") == {} and S._parse_cookie_pairs(None) == {})
ck("A11 带连字符的键名保留", S._parse_cookie_pairs("KUGOU-API-MID=x; token=t") == {"KUGOU-API-MID": "x", "token": "t"})
ck("A12 邮箱这类带 @ 的值不误伤", S._parse_cookie_pairs("m=s@163.com; MUSIC_U=abc") == {"m": "s@163.com", "MUSIC_U": "abc"})

# ---------------------------------------------------------------- 2. 必需键判定
print("=== B. 缺哪个键就不能算登录上（键名照抄 musicdl 各源） ===")
ck("B1 网易云只要有 MUSIC_U", S.music_cookie_missing("netease", {"MUSIC_U": "x"}) == [])
ck("B2 网易云缺 MUSIC_U 要说出来", S.music_cookie_missing("netease", {"NMTID": "x"}) == ["MUSIC_U"])
ck("B3 QQ 音乐两个键都要", S.music_cookie_missing("qq", {"qqmusic_key": "k", "uin": "1"}) == [])
ck("B4 QQ 音乐认 musickey/musicid 这组别名", S.music_cookie_missing("qq", {"musickey": "k", "musicid": "1"}) == [])
ck("B5 QQ 音乐只有一半时报缺的那半", S.music_cookie_missing("qq", {"qqmusic_key": "k"}) == ["uin 或 musicid"],
   S.music_cookie_missing("qq", {"qqmusic_key": "k"}))
ck("B6 酷狗要 token + userid", S.music_cookie_missing("kugou", {"token": "t"}) == ["userid"]
   and S.music_cookie_missing("kugou", {"token": "t", "userid": "9"}) == [])
ck("B7 没登记的平台不报错", S.music_cookie_missing("unknown", {}) == [])
ck("B8 三个平台都登记了 musicdl 源名", [i["musicdl_source"] for i in S.music_cookie_status()]
   == ["NeteaseMusicClient", "QQMusicClient", "KugouMusicClient"], S.music_cookie_status())

# ---------------------------------------------------------------- 3. 合并成一条
print("=== C. 合成一条给 musicdl：常备的不会被临时粘贴顶掉 ===")
reset(musicdl_cookies="OLD=a1; SHARED=from-global",
      music_platform_cookies={"netease": {"cookie": "MUSIC_U=ns1; SHARED=from-netease"},
                              "qq": {"cookie": "qqmusic_key=q1; uin=123"},
                              "kugou": {"cookie": "token=k1; userid=9"}})
m = S._parse_cookie_pairs(S.music_cookie_string())
ck("C1 全局 + 三个平台的键都在一条里",
   {"OLD", "SHARED", "MUSIC_U", "qqmusic_key", "uin", "token", "userid"} <= set(m), sorted(m))
ck("C2 同名键后写的平台盖过全局", m["SHARED"] == "from-netease", m.get("SHARED"))
ck("C3 临时粘的只盖同名键，别的键留着",
   S._parse_cookie_pairs(S.music_cookie_string("SHARED=ad-hoc"))["SHARED"] == "ad-hoc"
   and "MUSIC_U" in S._parse_cookie_pairs(S.music_cookie_string("SHARED=ad-hoc")),
   S.music_cookie_string("SHARED=ad-hoc")[:80])
ck("C4 一条里能同时带上三家登录（三源并行时谁都不掉）",
   all(k in m for k in ("MUSIC_U", "qqmusic_key", "token")), sorted(m))
reset()
ck("C5 什么都没配时是空串", S.music_cookie_string() == "", repr(S.music_cookie_string()))
reset(musicdl_cookies="OLD=a1")
ck("C6 清空平台格子后这条里就没有 MUSIC_U，全局那条还在（反向）",
   "MUSIC_U" not in S.music_cookie_string() and "OLD=a1" in S.music_cookie_string(),
   S.music_cookie_string())

# ---------------------------------------------------------------- 4. 存 / 状态 / 日志
print("=== D. 保存：值只进配置，日志与状态都不带值 ===")
reset()
got = S.set_music_cookie("netease", SECRET + "; NMTID=zz", via="扫码登录")
ck("D1 保存回执说键齐了", got["configured"] is True and got["missing"] == [], got)
ck("D2 落进内存配置的是三段结构",
   set(S.cfg.data["music_platform_cookies"]["netease"]) == {"cookie", "via", "at"},
   sorted(S.cfg.data["music_platform_cookies"]["netease"]))
ck("D3 记下了来源与时间", S.cfg.data["music_platform_cookies"]["netease"]["via"] == "扫码登录"
   and len(S.cfg.data["music_platform_cookies"]["netease"]["at"]) == 16,
   S.cfg.data["music_platform_cookies"]["netease"]["at"])
ck("D4 保存真的调了 cfg.save", S.cfg.saves == 1, S.cfg.saves)
st = {i["platform"]: i for i in S.music_cookie_status()}
ck("D5 状态里网易云是已配置、键名排序回显", st["netease"]["configured"] and st["netease"]["keys"] == ["MUSIC_U", "NMTID"], st["netease"])
ck("D6 状态里绝不含 Cookie 值", "super-secret-value-8f31" not in json.dumps(st, ensure_ascii=False),
   json.dumps(st, ensure_ascii=False)[:120])
ck("D7 运行日志绝不写 Cookie 值", all("super-secret-value-8f31" not in x for x in LOGS), LOGS)
ck("D8 日志讲清了是哪个平台、几个键", "网易云音乐" in last_log() and "2 个键" in last_log(), last_log())
S.set_music_cookie("qq", "qm_keyst=x;uin=1")
st = {i["platform"]: i for i in S.music_cookie_status()}
ck("D9 粘了但缺关键字段：算已配置、缺项写明白", st["qq"]["configured"] and st["qq"]["missing"] == ["qqmusic_key 或 musickey"], st["qq"])
ck("D10 粘贴来源默认记为「粘贴」", st["qq"]["via"] == "粘贴", st["qq"])
S.set_music_cookie("qq", "")
ck("D11 传空即清除", "qq" not in (S.cfg.data["music_platform_cookies"] or {}), S.cfg.data["music_platform_cookies"])
ck("D12 清除的日志不假装保存了", "清除QQ 音乐" in last_log(), last_log())
S.set_music_cookie("kugou", "完全不像 Cookie 的一句话")
ck("D13 解析不出键值时不留下半条脏数据", "kugou" not in (S.cfg.data["music_platform_cookies"] or {}),
   S.cfg.data["music_platform_cookies"])

# ---------------------------------------------------------------- 5. 接口口径
print("=== E. /api/music/cookies：只回状态，绝不回值 ===")
reset()
code, data = http_error(S.api_music_cookies_get)
ck("E1 GET 返回三行", code == 200 and len(data["items"]) == 3, code)
ck("E2 每行都带界面名与取 Cookie 的说明",
   all(i["label"] and i["how"] for i in data["items"]), [i["label"] for i in data["items"]])
ck("E3 未配置时三家都是未配置", all(not i["configured"] for i in data["items"]))
code, got = http_error(S.api_music_cookies_set, S.MusicCookieBody(platform="tidal", cookie="a=b"))
ck("E4 没登记的平台 400", code == 400 and "未知" in str(got), (code, got))
code, got = http_error(S.api_music_cookies_set, S.MusicCookieBody(platform="netease", cookie="随便一句话"))
ck("E5 认不出键值的粘贴当场拦住", code == 400 and "没从这段内容" in str(got), (code, got))
code, got = http_error(S.api_music_cookies_set, S.MusicCookieBody(platform="netease", cookie=SECRET))
ck("E6 存进去的键名与缺失项一并回执", code == 200 and got["keys"] == ["MUSIC_U"] and got["missing"] == [], got)
ck("E7 回执里不含 Cookie 值", "super-secret-value-8f31" not in json.dumps(got, ensure_ascii=False))
ck("E8 回执带整份状态供界面直接刷新", len(got["items"]) == 3 and got["items"][0]["configured"], got["items"][0])
code, got = http_error(S.api_music_cookies_set, S.MusicCookieBody(platform="netease", cookie="  "))
ck("E9 空内容是清除不是报错", code == 200 and got["configured"] is False, got)
ck("E10 /api/music/status 的 Cookie 读数跟合并结果一致",
   S.api_music_status()["saved_cookies"] is False, S.api_music_status()["saved_cookies"])
S.set_music_cookie("kugou", "token=t1; userid=9")
ck("E11 存了平台 Cookie 后 status 认账", S.api_music_status()["saved_cookies"] is True)

# ---------------------------------------------------------------- 6. 网易云扫码
print("=== F. 网易云扫码登录（全程假 requests，不碰真服务器） ===")
reset()
S.requests = FakeRequestsModule({UNIQ: ({"code": 200, "unikey": "key-1"}, [("NMTID", "n1")])})
code, g = http_error(S.api_netease_qr_generate)
ck("F1 生成成功回二维码链接与 key", code == 200 and g["qrcode_key"] == "key-1"
   and g["url"] == "https://music.163.com/login?codekey=key-1", g.get("url") if code == 200 else g)
ck("F2 二维码图片由本地生成（不引第三方在线服务）", g["qr_image"].startswith("data:image/png;base64,"), g["qr_image"][:24])
sess = FakeSession.instances[0]
ck("F3 请求打的是网易云自家取 key 的接口，没夹带凭据",
   sess.calls[0][0] == UNIQ and sess.calls[0][1] == {"type": "1"}, sess.calls[0])
ck("F4 会话按 key 暂存，轮询要沿用同一个会话", "key-1" in S._NETEASE_QR_SESSIONS
   and S._NETEASE_QR_SESSIONS["key-1"][0] is sess, list(S._NETEASE_QR_SESSIONS))
S._NETEASE_QR_SESSIONS.clear()
S.requests = FakeRequestsModule({UNIQ: ({"code": 500, "message": "系统繁忙"}, [])})
code, g = http_error(S.api_netease_qr_generate)
ck("F5 上游说不给就不给，报错带上它的原话", code == 400 and "系统繁忙" in str(g), (code, g))
S._NETEASE_QR_SESSIONS.clear()
S.requests = FakeRequestsModule({UNIQ: (ConnectionError("连不上"), [])})
code, g = http_error(S.api_netease_qr_generate)
ck("F6 网络断了翻成人话（500 且写明是取二维码失败）", code == 500 and "取二维码" in str(g), (code, g))
S._NETEASE_QR_SESSIONS.clear()

# —— 轮询状态机
sess = FakeSession()
sess.script = {POLL: ({"code": 801, "message": "等待扫描"}, [])}
S._NETEASE_QR_SESSIONS["k801"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k801"))
ck("F7 没扫：等待扫码，还在 pending", r["status"] == "pending" and r["message"] == "等待扫码", r)
ck("F8 没扫时不会写任何 Cookie", "netease" not in (S.cfg.data["music_platform_cookies"] or {}), S.cfg.data["music_platform_cookies"])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="   "))
ck("F9 缺 key 直接 400", code == 400, (code, r))
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="never-seen"))
ck("F10 没见过的 key 判过期，不往网易云发请求", r["status"] == "expired" and "重新获取" in r["message"], r)

S._NETEASE_QR_SESSIONS.clear()
sess = FakeSession()
sess.script = {POLL: ({"code": 802}, [])}
S._NETEASE_QR_SESSIONS["k802"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k802"))
ck("F11 扫了没确认：提示在手机确认",
   r["status"] == "pending" and r["message"] == "已扫码，请在手机上确认", r)

S._NETEASE_QR_SESSIONS.clear()
sess = FakeSession()
sess.script = {POLL: ({"code": 803}, [("MUSIC_U", "the-scanned-value"), ("NMTID", "n2")])}
S._NETEASE_QR_SESSIONS["k803"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k803"))
ck("F12 确认成功：ok 且回登录成功", r["ok"] is True and r["status"] == "success", r)
ck("F13 轮询用的是同一个会话（带着 NMTID 那套）", sess.calls[-1][0] == POLL and len(sess.calls) == 1, sess.calls)
ck("F14 拿到的 Cookie 真落进网易云那一格",
   S.cfg.data["music_platform_cookies"]["netease"]["cookie"] == "MUSIC_U=the-scanned-value; NMTID=n2",
   S.cfg.data["music_platform_cookies"]["netease"])
ck("F15 来源记成扫码登录", S.cfg.data["music_platform_cookies"]["netease"]["via"] == "扫码登录")
ck("F16 成功即把会话丢掉，同一 key 再问就是过期", "k803" not in S._NETEASE_QR_SESSIONS
   and http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k803"))[1]["status"] == "expired",
   list(S._NETEASE_QR_SESSIONS))
ck("F17 回执带整份状态且不含 Cookie 值", len(r["items"]) == 3 and "the-scanned-value" not in json.dumps(r, ensure_ascii=False),
   json.dumps(r)[:120])
ck("F18 日志里也没有 Cookie 值", all("the-scanned-value" not in x for x in LOGS), LOGS)

# 803 但没给凭证
reset()
S._NETEASE_QR_SESSIONS.clear()
sess = FakeSession()
sess.script = {POLL: ({"code": 803}, [("NMTID", "only")])}
S._NETEASE_QR_SESSIONS["k803x"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k803x"))
ck("F19 说成功但没给 MUSIC_U：当场认栽，不假装登录上了",
   r["ok"] is False and r["status"] == "failed" and "MUSIC_U" in r["message"], r)
ck("F20 这种半截结果不会写进配置", "netease" not in (S.cfg.data["music_platform_cookies"] or {}),
   S.cfg.data["music_platform_cookies"])
# 反向：把必需键表放宽，同一条响应就必须变成成功 —— 证明拦它的确实是那道闸门
_orig_platforms = S.MUSIC_COOKIE_PLATFORMS
S.MUSIC_COOKIE_PLATFORMS = [("netease", "网易云音乐", "NeteaseMusicClient", [["NMTID"]], "")]
try:
    S._NETEASE_QR_SESSIONS.clear()
    sess = FakeSession()
    sess.script = {POLL: ({"code": 803}, [("NMTID", "only")])}
    S._NETEASE_QR_SESSIONS["k803y"] = (sess, CLOCK[0])
    code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k803y"))
    ck("F21 反向验证：闸门一放宽同一条响应就判成功", r["ok"] is True, r)
finally:
    S.MUSIC_COOKIE_PLATFORMS = _orig_platforms
    S._NETEASE_QR_SESSIONS.clear()

# 网络抖动不该把二维码判死
reset()
sess = FakeSession()
sess.script = {POLL: (ConnectionError("超时"), [])}
S._NETEASE_QR_SESSIONS["kretry"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="kretry"))
ck("F22 问不到结果时报「没问到」，不判过期", r["status"] == "pending" and "没问到" in r["message"], r)
sess.script = {POLL: ({"code": 803}, [("MUSIC_U", "late-ok")])}
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="kretry"))
ck("F23 抖完 key 还在，再点一次就能拿到登录（会话没被丢）", r["ok"] is True, r)

reset()
sess = FakeSession()
sess.script = {POLL: ({"code": 800}, [])}
S._NETEASE_QR_SESSIONS["k800"] = (sess, CLOCK[0])
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="k800"))
ck("F24 网易云判过期时同步丢掉会话", r["status"] == "expired" and "k800" not in S._NETEASE_QR_SESSIONS, (r, list(S._NETEASE_QR_SESSIONS)))
sess = FakeSession()
S._NETEASE_QR_SESSIONS["kold"] = (sess, CLOCK[0])
S._NETEASE_QR_SESSIONS["kfresh"] = (FakeSession(), CLOCK[0] + S._NETEASE_QR_TTL + 1)
CLOCK[0] += S._NETEASE_QR_TTL + 1
code, r = http_error(S.api_netease_qr_poll, S.NeteaseQrPollBody(qrcode_key="kold"))
ck("F25 超过二维码有效期就不再拿它问人", r["status"] == "expired" and not sess.calls, sess.calls)
ck("F26 过期清理只清过期的（顺带清掉新生成的陈旧项）", "kold" not in S._NETEASE_QR_SESSIONS, list(S._NETEASE_QR_SESSIONS))
S._NETEASE_QR_SESSIONS.clear()

# ---------------------------------------------------------------- 7. 接到真实链路
print("=== G. 存的 Cookie 真会带进搜索 / 歌单订阅 ===")
reset(music_platform_cookies={"netease": {"cookie": SECRET}})
CALLS: dict = {}


def fake_search_music(keyword, **kw):
    CALLS["search"] = kw
    return []


import music_search as MS  # noqa: E402

ORIG["search"] = MS.search_music
MS.search_music = fake_search_music
try:
    st_code, _ = http_error(S.api_music_search, {"keyword": "夜航船", "sources": []})
    ck("G1 搜索接口把合并后的 Cookie 交给 musicdl", st_code == 200 and SECRET in CALLS["search"].get("cookies", ""),
       str(CALLS["search"].get("cookies"))[:60])
    http_error(S.api_music_search, {"keyword": "夜航船", "sources": [], "cookies": "EXTRA=1"})
    ck("G2 请求里临时粘的只加键，不冲掉网易云登录",
       SECRET in CALLS["search"]["cookies"] and "EXTRA=1" in CALLS["search"]["cookies"],
       CALLS["search"]["cookies"][:80])
finally:
    MS.search_music = ORIG["search"]

ORIG["parse"] = MS.parse_playlist


def fake_parse(url, **kw):
    CALLS["parse"] = kw
    return [{"id": "c1", "title": "夜航船", "artists": "某某", "duration_s": 240, "url": "https://x/1"}]


def fake_get_info(url, cfg):
    raise AssertionError("音乐订阅不该走 yt-dlp 那条读取分支")


class MemSubs(S.SubscriptionManager):
    def load(self):
        self.subs = []

    def save(self):
        pass


ORIG["proxy"] = S.music_proxy
try:
    MS.parse_playlist = fake_parse
    S.music_proxy = lambda *a, **kw: ""
    engine = type("E", (), {"get_info": staticmethod(fake_get_info)})()
    mgr = MemSubs(engine, S.cfg, type("Q", (), {"add_urls": lambda self, u, o: []})(),
                  type("T", (), {"notify_sub": lambda self, *a: None})(), lambda m, lv="info": LOGS.append(m))
    sub = {"id": "s1", "url": "https://music.163.com/playlist?id=1", "title": "", "last_ids": [], "rules": {}}
    entries, _t, err = mgr._music_sub_entries(sub) if hasattr(mgr, "_music_sub_entries") else S._music_sub_entries(sub)
    ck("G3 歌单订阅扫描带着网易云登录 Cookie（追新才够得到无损）",
       SECRET in CALLS["parse"].get("cookies", ""), str(CALLS["parse"].get("cookies"))[:60])
    ck("G4 扫描确实读到了曲目", bool(entries) and not err, err)
    reset()
    entries, _t, err = S._music_sub_entries({"id": "s2", "url": "https://music.163.com/playlist?id=1", "rules": {}})
    ck("G5 反向验证：清空平台 Cookie 后这条链路上就没有 MUSIC_U（闸门真的在起作用）",
       "MUSIC_U" not in CALLS["parse"]["cookies"], CALLS["parse"]["cookies"][:60])
finally:
    MS.parse_playlist = ORIG["parse"]
    S.music_proxy = ORIG["proxy"]

S._NETEASE_QR_SESSIONS.clear()
restore()
ck("Z1 探针没碰过真配置", S.cfg is ORIG["cfg"] and isinstance(S.cfg, S.ConfigManager), type(S.cfg).__name__)

print()
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
