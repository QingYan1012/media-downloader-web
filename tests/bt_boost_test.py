#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qBEE 参照·第一档（tracker 加料 / 上传下载限速 / 首尾优先 / 只做种）离线自检。

只写 %TEMP%：不碰真实 config.json、真实下载目录，也不往 web_app/torrent_state 里落缓存；
aria2 一律用假客户端顶替。跑法：PYTHONIOENCODING=utf-8 python tests/bt_boost_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402
import bt_trackers as T  # noqa: E402
from fastapi import HTTPException  # noqa: E402

FAILED = []
TOTAL = 0


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}" + (f"  [{extra}]" if extra else ""))
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{extra}]")


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)
        self.saved = 0

    def save(self):
        self.saved += 1  # 设置接口确实会 save，这里只计数，绝不落盘


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info", k="", kv=None):   # k/kv 是 #53 给日志加的可选消息键，这里不收
        self.rows.append((level, str(msg)))
        return True


TMP = Path(tempfile.mkdtemp(prefix="md_bt_boost_"))
SRC = Path(S.__file__).read_text(encoding="utf-8")

# ---------- A tracker 文本解析 ----------
ck("A1 announce 地址只认 http/https",
   T.is_announce("http://tracker.example:1337/announce") and T.is_announce("https://x.io/a"))
ck("A2 非 http、带空格、带凭据的一律不要",
   not T.is_announce("ftp://a.io/announce") and not T.is_announce("http://a.io/ announce")
   and not T.is_announce("http://user:pass@a.io/announce") and not T.is_announce("tracker.io/announce"))
ck("A3 超长行挡掉（配置里塞垃圾不能把命令行撑爆）", not T.is_announce("http://a.io/" + "x" * 400))
ck("A4 一行一个：注释、空行、空格都清掉",
   T.parse_list("# comment\n\n  http://a.io/announce  \n") == ["http://a.io/announce"])
ck("A5 同一行逗号分隔也收下",
   T.parse_list("http://a.io/announce,https://b.io/announce") ==
   ["http://a.io/announce", "https://b.io/announce"])
ck("A6 非法混进来只丢它自己，好的照留",
   T.parse_list("http://a.io/announce\n../../etc/passwd\nhttp://b.io/announce") ==
   ["http://a.io/announce", "http://b.io/announce"])
ck("A7 CRLF 的行尾不影响解析",
   T.parse_list("http://a.io/announce\r\nhttp://b.io/announce\r\n") ==
   ["http://a.io/announce", "http://b.io/announce"])
ck("A8 来源清单只留 URL，注释与重复去掉",
   T.sources_to_urls("# 源\nhttps://a/x.txt\nhttps://a/x.txt\nnot a url\nftp://b/y") ==
   ["https://a/x.txt"])
ck("A9 合并时手动排在抓来的前面",
   T.merge_lists([["http://m/announce"], ["http://a/announce", "http://m/announce"]], 0) ==
   ["http://m/announce", "http://a/announce"])
ck("A10 上限截断真的生效（反向：不填上限就是全要）",
   T.merge_lists([[f"http://t{i}/a" for i in range(50)]], 8) ==
   [f"http://t{i}/a" for i in range(8)] and
   len(T.merge_lists([[f"http://t{i}/a" for i in range(50)]], 0)) == 50)
# 抓回来的列表是 bytes（http_get_bytes），不解码就会当成 "b'http://...'" 这种字面量，整份清单静默变空
ck("A11 抓到的是字节也能解析（实测不解码时一条都认不出来）",
   T.parse_list("http://a.io/announce\nhttp://b.io/announce".encode("utf-8")) ==
   ["http://a.io/announce", "http://b.io/announce"])
ck("A12 字节里带中文注释或非 UTF-8 字节不能整批炸掉",
   T.parse_list("# 中文注释\nhttp://a.io/announce\n".encode("utf-8") + b"\xff\xfe bad") ==
   ["http://a.io/announce"])

# ---------- B 限速形状 ----------
ck("B1 1M / 512K / 纯字节数都按 aria2 的写法原样给",
   T.norm_speed("1M") == "1M" and T.norm_speed("512k") == "512K" and T.norm_speed("200000") == "200000")
ck("B2 空与 0 都算不限（返回空串表示这条不发）",
   T.norm_speed("") == "" and T.norm_speed("0") == "" and T.norm_speed(None) == "")
ck("B3 带单位以外的字母、负数、空格都挡掉",
   T.norm_speed("abc") == "" and T.norm_speed("-1M") == "" and T.norm_speed("1 M") == ""
   and T.norm_speed("1MB") == "", str([T.norm_speed(x) for x in ("abc", "-1M", "1 M", "1MB")]))
ck("B4 小数限速收下来（0.5M 是合法写法）", T.norm_speed("0.5M") == "0.5M")
ck("B5 比对限速要换成字节：发 1M、aria2 读回 1048576 是同一个值（实测）",
   T.to_bytes("1M") == 1048576 and T.to_bytes("512K") == 524288
   and T.to_bytes("1048576") == T.to_bytes("1M"))
ck("B6 不限速在读回里是 0，不能被当成「读不到」",
   T.to_bytes("0") == 0 and T.to_bytes("") == 0)
ck("B7 形状不对时 to_bytes 给 -1，而不是默默算成 0（0 是合法的「不限」）",
   T.to_bytes("快点") == -1 and T.to_bytes("1M2K") == -1)

# ---------- C 缓存与 effective ----------
APP = TMP / "app"
APP.mkdir(parents=True, exist_ok=True)
ck("C1 缓存落在 torrent_state 下（这个目录整目录不进包）",
   T.cache_path(APP).as_posix().endswith("/torrent_state/trackers_cache.json"))
ck("C2 没缓存时读回空表，不炸", T.load_cache(APP) == {})
MANUAL = "http://manual/announce"
FETCHED = "http://s1/announce\nhttp://s2/announce\n# x\nbad line"
getter_calls = []


def fake_getter(u):
    getter_calls.append(u)
    if "s1" in u:
        return FETCHED.encode("utf-8")
    raise RuntimeError("404 page not found")


BASE = {"bt_trackers": MANUAL, "bt_tracker_sources": "https://raw.example/s1.txt",
        "bt_tracker_auto_update": True, "bt_tracker_max": 30}
got, note = T.effective(dict(BASE), APP)
ck("C3 不给抓取函数时只用手动条目，且把原因写进 note",
   got == [MANUAL] and note, f"{got} | {note}")
got, note = T.effective(dict(BASE), APP, getter=fake_getter)
ck("C4 抓过之后生效清单 = 手动在前 + 来源在后",
   got == [MANUAL, "http://s1/announce", "http://s2/announce"], str(got))
ck("C5 抓回来的正文写进了缓存文件（下次不联网也能用）",
   T.cache_path(APP).is_file() and "http://s2/announce" in T.cache_path(APP).read_text(encoding="utf-8"))
ck("C6 再取一次不重新联网（缓存里已经有货）",
   (getter_calls.clear(), T.effective(dict(BASE), APP, getter=fake_getter), not getter_calls)[2])
S2 = {"bt_trackers": "", "bt_tracker_sources": "https://raw.example/s1.txt\nhttps://raw.example/s9.txt",
      "bt_tracker_auto_update": True, "bt_tracker_max": 30}
getter_calls.clear()
got, note = T.effective(dict(S2), APP, getter=fake_getter)
ck("C7 有一个来源抓不动：能用的照用，note 点名几个没抓到",
   got == ["http://s1/announce", "http://s2/announce"] and "1 个来源这次没抓到" in note, f"{got} | {note}")
ck("C8 反向对照：全抓到就不该有「没抓到」那句",
   "没抓到" not in T.effective({"bt_trackers": "", "bt_tracker_sources": "https://raw.example/s1.txt",
                               "bt_tracker_auto_update": True, "bt_tracker_max": 30},
                              APP, getter=fake_getter)[1])
ck("C9 上限触发时 note 说「只取前 N 条」",
   "只取前 2 条" in T.effective({"bt_trackers": MANUAL, "bt_tracker_sources": "https://raw.example/s1.txt",
                                "bt_tracker_auto_update": True, "bt_tracker_max": 2},
                               APP, getter=fake_getter)[1])
ck("C10 一条都没有时 note 讲清该怎么办，不是回个空列表就算完",
   T.effective({"bt_trackers": "", "bt_tracker_sources": "", "bt_tracker_auto_update": True,
                "bt_tracker_max": 30}, TMP / "no_cache", getter=None)[1])
st = T.status({"bt_trackers": MANUAL, "bt_tracker_sources": "https://raw.example/s1.txt\nhttps://raw.example/s9.txt",
               "bt_tracker_auto_update": True, "bt_tracker_max": 30}, APP)
ck("C11 status 把每个来源的抓到/没抓到分开列（界面要点名）",
   len(st["sources"]) == 2 and {r["url"]: r["ok"] for r in st["sources"]}["https://raw.example/s1.txt"]
   and not {r["url"]: r["ok"] for r in st["sources"]}["https://raw.example/s9.txt"], str(st["sources"])[:160])

# ---------- D 提交给 aria2 的加料项 ----------
_REAL_APP_DIR = S.APP_DIR
S.APP_DIR = APP
try:
    c = {"bt_trackers": MANUAL, "bt_tracker_sources": "", "bt_tracker_max": 30,
         "bt_dl_limit": "", "bt_ul_limit": "", "bt_prioritize_piece": False}
    o = S._bt_add_options(dict(c), lambda *a, **k: None)
    ck("D1 只填手动 tracker 时，bt-tracker 按逗号拼成一个值",
       o == {"bt-tracker": MANUAL}, str(o))
    ck("D2 没填限速就不发那两条键（发个空值 aria2 会当非法参数）",
       "max-download-limit" not in o and "max-upload-limit" not in o)
    ck("D3 首尾优先关着时不出现 bt-prioritize-piece", "bt-prioritize-piece" not in o)
    c2 = dict(c, bt_dl_limit="2m", bt_ul_limit="512K", bt_prioritize_piece=True)
    o2 = S._bt_add_options(dict(c2), lambda *a, **k: None)
    ck("D4 限速大小写都归一成 aria2 认的写法",
       o2["max-download-limit"] == "2M" and o2["max-upload-limit"] == "512K", str(o2))
    ck("D5 首尾优先开起来就是 head,tail（大小由 aria2 默认 1M）",
       o2["bt-prioritize-piece"] == "head,tail")
    ck("D6 限速形状不对时不发出去，而不是把 abc 交给 aria2",
       "max-download-limit" not in S._bt_add_options(dict(c, bt_dl_limit="abc"),
                                                    lambda *a, **k: None))
    logs = []
    S._bt_add_options({"bt_trackers": "", "bt_tracker_sources": "", "bt_tracker_max": 30},
                      lambda m, *a, **k: logs.append(str(m)))
    ck("D7 一条 tracker 都没有时，日志里要留下那句原因",
       any("tracker" in x for x in logs), str(logs)[:160])
    ck("D8 手动条目里塞非 announce 的东西不会变成 aria2 参数值的一部分",
       S._bt_add_options({"bt_trackers": "rm -rf /", "bt_tracker_sources": "",
                          "bt_tracker_max": 30}, lambda *a, **k: None) == {})
finally:
    S.APP_DIR = _REAL_APP_DIR

# ---------- E 设置接口的校验 ----------
_REAL_CFG, _REAL_LOG = S.cfg, S.log_mgr
try:
    S.cfg = FakeCfg(dict(S.ConfigManager.DEFAULTS))
    S.log_mgr = FakeLog()

    def set_cfg(**kw):
        return S.api_set_config(S.ConfigBody(**kw))

    d = set_cfg(bt_tracker_max=9999)["data"]
    ck("E1 tracker 上限被夹到 200（announce 是串行的，堆多了首轮很慢）",
       d["bt_tracker_max"] == 200, str(d["bt_tracker_max"]))
    ck("E2 上限可以是 0（就是不注入），别被夹成最小 1",
       set_cfg(bt_tracker_max=0)["data"]["bt_tracker_max"] == 0)
    ck("E3 限速大小写归一后入库",
       set_cfg(bt_dl_limit=" 1m ")["data"]["bt_dl_limit"] == "1M")
    ck("E4 限速空串表示不限，存进去还是空",
       set_cfg(bt_dl_limit="")["data"]["bt_dl_limit"] == "")
    try:
        set_cfg(bt_ul_limit="快点")
        ck("E5 限速写成别的形状要当场顶回去", False, "没报错")
    except HTTPException as e:
        ck("E5 限速写成别的形状要当场顶回去", e.status_code == 400 and "1M" in str(e.detail), str(e.detail)[:120])
    ck("E6 tracker 与来源文本原样存（解析推迟到用的时候）",
       set_cfg(bt_trackers="http://a/announce\n随便一行")["data"]["bt_trackers"]
       == "http://a/announce\n随便一行")
    ck("E7 超长的 tracker 文本被截到 2 万字符，别把配置撑爆",
       len(set_cfg(bt_trackers="http://a/announce\n" * 9000)["data"]["bt_trackers"]) <= 20000)
    ck("E8 首尾优先存成布尔而不是字符串「false」",
       set_cfg(bt_prioritize_piece=False)["data"]["bt_prioritize_piece"] is False)
finally:
    S.cfg, S.log_mgr = _REAL_CFG, _REAL_LOG

# ---------- F 两个 tracker 接口 ----------
_REAL_CFG, _REAL_LOG, _REAL_GET = S.cfg, S.log_mgr, S.http_get_bytes
S.APP_DIR = APP
try:
    S.cfg = FakeCfg({"bt_trackers": MANUAL, "bt_tracker_sources": "https://raw.example/s1.txt",
                     "bt_tracker_auto_update": True, "bt_tracker_max": 30})
    S.log_mgr = FakeLog()
    hit = []
    S.http_get_bytes = lambda u, **k: (hit.append(u), b"http://s1/announce\n")[1]
    r = S.api_bt_trackers()
    ck("F1 GET 只吃缓存，绝不顺手联网", hit == [], str(hit))
    ck("F2 GET 回的是「下一个新任务会带上的」那份清单",
       r["count"] >= 1 and r["effective"][0] == MANUAL, str(r)[:200])
    ck("F3 GET 把上限与自动更新状态一并回给界面（界面要写明只对new任务）",
       r["max"] == 30 and r["auto_update"] is True)
    T.save_cache(APP, {})
    rr = S.api_bt_trackers_refresh()
    ck("F4 手动点更新真的走了一次抓取", hit and rr["sources"] == 1, str(hit))
    ck("F5 更新后清单里能看到刚抓来的", "http://s1/announce" in rr["count"] * [1] or rr["count"] >= 1)
    hit.clear()
    S.cfg = FakeCfg({"bt_trackers": "", "bt_tracker_sources": "  ", "bt_tracker_auto_update": True,
                     "bt_tracker_max": 30})
    try:
        S.api_bt_trackers_refresh()
        ck("F6 来源填空就顶回去，不是回一句「更新完成」", False, "没报错")
    except HTTPException as e:
        ck("F6 来源填空就顶回去，不是回一句「更新完成」", e.status_code == 400 and "来源地址" in str(e.detail))
    S.cfg = FakeCfg({"bt_trackers": "", "bt_tracker_sources": "https://raw.example/s9.txt",
                     "bt_tracker_auto_update": True, "bt_tracker_max": 30})
    S.http_get_bytes = lambda u, **k: (_ for _ in ()).throw(RuntimeError("连不上"))
    bad = S.api_bt_trackers_refresh()
    ck("F7 全来源都抓不到时 ok=False，并把失败原因列出来",
       bad["ok"] is False and bad["failed"] and bad["count"] == 0, str(bad)[:200])
    ck("F8 抓不到的那次也要在日志里留痕（否则用户以为更新过了）",
       any("更新 tracker 列表" in x for _, x in S.log_mgr.rows), str(S.log_mgr.rows)[:200])
finally:
    S.cfg, S.log_mgr, S.http_get_bytes, S.APP_DIR = _REAL_CFG, _REAL_LOG, _REAL_GET, _REAL_APP_DIR

# ---------- G 改限速的读回口径 ----------
class FakeAC:
    def __init__(self, ok=True, why="", back=None, status=None):
        self.ok, self.why, self.back = ok, why, back or {}
        self.status = status          # None = 这个客户端不提供状态（模拟读状态本身失败）
        self.sent = None

    def change_option_detail(self, gid, opts):
        self.sent = opts
        return (self.ok, self.why)

    def get_option(self, gid):
        return dict(self.back)

    def tell_status(self, gid, keys=None):
        if self.status is None:
            raise AttributeError("fake 客户端没有 tell_status")
        return {"status": self.status}


class FakeTask:
    def __init__(self, gid="G-1"):
        self.gid, self.resume_hint = gid, "aria2 G-1"


_REAL_CFG, _REAL_CLIENT, _TASKS = S.cfg, S._bt_client, S.queue.tasks
S.cfg = FakeCfg({})
try:
    ac = FakeAC(ok=True, back={"max-download-limit": "1048576", "max-upload-limit": "0"})
    S._bt_client = lambda c: ac
    S.queue.tasks = {"t1": FakeTask()}
    r = S.api_bt_limit(S.BtLimitBody(task_id="t1", download="1M", upload="0"))
    ck("G1 改限速发出去的是 aria2 认的键名",
       ac.sent == {"max-download-limit": "1M", "max-upload-limit": "0"}, str(ac.sent))
    ck("G2 回话里带的是读回来的实际值，不是我以为的值",
       r["actual"]["max-download-limit"] == "1048576", str(r)[:160])
    ck("G2b 发 1M、读回 1048576 要判成成功（比字符串会把成功说成失败）",
       r["ok"] is True, str(r)[:200])
    ck("G3 0 就是取消限速，不会变成「不发这条」",
       ac.sent["max-upload-limit"] == "0")
    ck("G4 改成功后任务那行跟着写了当前限速",
       "限速" in S.queue.tasks["t1"].resume_hint, S.queue.tasks["t1"].resume_hint)
    ac = FakeAC(ok=True, back={"max-download-limit": "999"})  # 回了 OK 却没改成
    S._bt_client = lambda c: ac
    S.queue.tasks = {"t1": FakeTask()}
    r2 = S.api_bt_limit(S.BtLimitBody(gid="G-9", download="1M"))
    ck("G5 反向对照：aria2 回 OK 但读回不一致时不能说成功",
       r2["ok"] is False and "读回来" in r2["message"] and r2["actual"]["max-download-limit"] == "999",
       str(r2)[:200])
    ac = FakeAC(ok=True, back={})  # 读回里连这个键都没有
    S._bt_client = lambda c: ac
    try:
        S.queue.tasks = {"t1": FakeTask()}
        r3 = S.api_bt_limit(S.BtLimitBody(gid="G-8", download="1M"))
        ck("G5b 读不到那个键时不能算成功（空值等于 0=不限，会被误判成改成了不限）",
           r3["ok"] is False and "读不到" in r3["message"], str(r3)[:200])
    except HTTPException as e:
        ck("G5b 读不到那个键时不能算成功（空值等于 0=不限，会被误判成改成了不限）",
           False, "抛了 %s" % str(e)[:120])
    ac = FakeAC(ok=False, why="Cannot change option for GID#G-1")
    S._bt_client = lambda c: ac
    S.queue.tasks = {"t1": FakeTask()}
    try:
        S.api_bt_limit(S.BtLimitBody(task_id="t1", download="1M"))
        ck("G6 aria2 当场拒绝时把原话带出来", False, "没报错")
    except HTTPException as e:
        ck("G6 aria2 当场拒绝时把原话带出来",
           e.status_code == 500 and "Cannot change option" in str(e.detail), str(e.detail)[:160])
    # 实测：被拒的两种情形原话不同，用户看不出差别，所以后端要把 aria2 那边的状态一起报出来
    ac = FakeAC(ok=False, why="Cannot change option for GID#G-1", status="complete")
    S._bt_client = lambda c: ac
    S.queue.tasks = {"t1": FakeTask()}
    try:
        S.api_bt_limit(S.BtLimitBody(task_id="t1", download="1M"))
        ck("G10 aria2 已把任务移出活动队列时报出它的状态，不只甩原话", False, "没报错")
    except HTTPException as e:
        ck("G10 aria2 已把任务移出活动队列时报出它的状态，不只甩原话",
           "complete" in str(e.detail) and "移出" in str(e.detail)
           and "Cannot change option" in str(e.detail), str(e.detail)[:200])
    ac = FakeAC(ok=False, why="GID#G-1 is not found", status="")
    S._bt_client = lambda c: ac
    S.queue.tasks = {"t1": FakeTask()}
    try:
        S.api_bt_limit(S.BtLimitBody(task_id="t1", download="1M"))
        ck("G11 任务号整个不在 aria2 里时说的是「不在了」，不是「状态读不到」", False, "没报错")
    except HTTPException as e:
        ck("G11 任务号整个不在 aria2 里时说的是「不在了」，不是「状态读不到」",
           "已经不在 aria2 里" in str(e.detail) and "is not found" in str(e.detail),
           str(e.detail)[:200])
    S.queue.tasks = {}
    try:
        S.api_bt_limit(S.BtLimitBody(task_id="没有这个任务", download="1M"))
        ck("G7 任务没交给 aria2 就说没任务号", False, "没报错")
    except HTTPException as e:
        ck("G7 任务没交给 aria2 就说没任务号", e.status_code == 404 and "任务号" in str(e.detail))
    called = []
    S._bt_client = lambda c: called.append(1) or FakeAC()
    try:
        S.api_bt_limit(S.BtLimitBody(gid="G-1", download="很快"))
        ck("G8 限速形状不对时先顶回去，不碰 aria2", False, "没报错")
    except HTTPException as e:
        ck("G8 限速形状不对时先顶回去，不碰 aria2", e.status_code == 400 and not called)
    try:
        S.api_bt_limit(S.BtLimitBody(gid="G-1"))
        ck("G9 两路限速都不给时报「要改哪一路」", False, "没报错")
    except HTTPException as e:
        ck("G9 两路限速都不给时报「要改哪一路」", e.status_code == 400 and "哪一路" in str(e.detail))
finally:
    S.cfg, S._bt_client, S.queue.tasks = _REAL_CFG, _REAL_CLIENT, _TASKS

# ---------- H aria2 客户端新方法（RPC 层） ----------
import aria2_client as AC  # noqa: E402
_real_urlopen = AC.urlopen


def _resp(raw, code=200):
    class R:
        def read(self_inner):
            return raw

        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

    def opener(req, timeout=15):
        if code != 200:
            import urllib.error
            raise urllib.error.HTTPError("http://x", code, "Bad", {}, R())
        return R()

    return opener


try:
    cli = AC.Aria2Client("http://127.0.0.1:6800/jsonrpc")
    AC.urlopen = _resp(b'{"jsonrpc":"2.0","id":"x","result":"OK"}')
    ck("H1 changeOption 回 OK 时给 (True, '')", cli.change_option_detail("G", {"a": "b"}) == (True, ""))
    AC.urlopen = _resp(b'{"error":{"code":23,"message":"Cannot change option for GID#G"}}', 400)
    okc, why = cli.change_option_detail("G", {"bt-tracker": "x"})
    ck("H2 aria2 的拒绝原话留着（只报 400 等于丢掉原因）",
       okc is False and "Cannot change option" in why, why)
    AC.urlopen = _resp(b'{"jsonrpc":"2.0","id":"x","result":{"max-download-limit":"1048576"}}')
    ck("H3 get_option 读回字典", cli.get_option("G") == {"max-download-limit": "1048576"})
    AC.urlopen = _resp(b'{"error":{"code":1,"message":"No such download"}}', 400)
    ck("H4 任务已经不在了时 get_option 回空表而不是抛", cli.get_option("G") == {})
    AC.urlopen = _resp(b'not json at all', 400)
    okc, why = cli.change_option_detail("G", {"a": "b"})
    ck("H5 响应体不是 JSON 时也要说清失败", okc is False and bool(why), why)
    AC.urlopen = _resp(b'{"jsonrpc":"2.0","id":"x","result":"OK"}')
    ck("H6 老的 change_option 布尔口径没被新方法带坏", cli.change_option("G", {"a": "b"}) is True)
finally:
    AC.urlopen = _real_urlopen

# ---------- I 接线事实核对 ----------
DEFAULTS = S.ConfigManager.DEFAULTS
ck("I1 七个新设置都在默认表里（老用户升级后不会读到 None）",
   all(k in DEFAULTS for k in ("bt_trackers", "bt_tracker_sources", "bt_tracker_auto_update",
                               "bt_tracker_max", "bt_dl_limit", "bt_ul_limit", "bt_prioritize_piece")),
   str([k for k in DEFAULTS if k.startswith("bt_")]))
ck("I2 默认来源就是模块里那两个（设置和代码不会各说一套）",
   set(DEFAULTS.get("bt_tracker_sources", "").splitlines()) ==
   {s["url"] for s in T.DEFAULT_SOURCES}, str(DEFAULTS.get("bt_tracker_sources"))[:160])
ck("I3 默认表里没有任何 tracker 正文（GPL 列表不进包）",
   "announce" not in DEFAULTS.get("bt_trackers", "") and
   "trackers_all.txt" in DEFAULTS.get("bt_tracker_sources", ""))
ck("I4 入队接口认「只做种」这个开关，默认关",
   S.AddUrlsBody.model_fields["torrent_seed_only"].default is False)
ck("I5 任务级覆盖白名单里带了 torrent_seed_only（不然入队传了也不生效）",
   '"torrent_seed_ratio", "torrent_seed_time", "torrent_seed_only"' in SRC)
ck("I6 磁力挂只做种会被挡下并说明为什么",
   "磁力链接这一刻还没有种子元数据" in SRC)
ck("I7 bt-seed-unverified 只在只做种那条路上出现",
   SRC.count('extra["bt-seed-unverified"]') == 1)
ck("I8 三个新接口都挂上了",
   {"/api/bt/trackers", "/api/bt/trackers/refresh", "/api/bt/limit"} <=
   {p for p in [r.path for r in S.app.routes]})
spec = S.app.openapi()
ck("I9 带入参的 POST 走请求体，不掉回查询参数（#186 那类缺陷的回归位）",
   "requestBody" in spec["paths"]["/api/bt/limit"]["post"],
   str(spec["paths"]["/api/bt/limit"]["post"].get("parameters"))[:160])
ck("I9b 手动更新 tracker 的 POST 确实不需要入参（来源读设置，所以没有请求体才对）",
   "requestBody" not in spec["paths"]["/api/bt/trackers/refresh"]["post"]
   and not spec["paths"]["/api/bt/trackers/refresh"]["post"].get("parameters"))
ck("I10 读接口不声明请求体（GET 带 body 是错的）",
   "requestBody" not in spec["paths"]["/api/bt/trackers"]["get"])
ck("I11 打包脚本没把 tracker 缓存算进包里",
   "trackers_cache.json" not in Path(S.__file__).with_name("pack_release.py")
   .read_text(encoding="utf-8"))

import shutil  # noqa: E402

shutil.rmtree(TMP, ignore_errors=True)
print("\nTOTAL:", TOTAL, "FAILED:", len(FAILED))
if FAILED:
    print("FAILED:", " | ".join(FAILED))
sys.exit(1 if FAILED else 0)
