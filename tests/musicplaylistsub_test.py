r"""音乐歌单订阅追新自检（③）。

全程离线：歌单解析与音乐下载入口都用桩顶掉，subscriptions.json 只在内存里动。
不打本机 server —— 本机进程还是改动前的代码，HTTP 断言只会假红。

反向验证在 G 段与 H 段：故意把游标改成「每次现铸的缓存 id」，整张歌单必须被反复重下，
断言要炸得出来，否则这条保护等于没写。
H 段管快列模式（yt-dlp 只列曲目）的行：行里没有缓存 id、歌手与时长都空着，
只靠曲名认歌会把同名不同曲并成一条，也没有音频地址可下。

跑法：`python tests/musicplaylistsub_test.py`
"""
from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as MS  # noqa: E402
import server as S  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []
CALLS: dict = {"parse": [], "dl": []}
SUBS_SNAPSHOT = S.SUBS_FILE.read_bytes() if S.SUBS_FILE.exists() else None
ORIG = {"parse": MS.parse_playlist, "log_mgr": S.log_mgr, "proxy": S.music_proxy,
        "dl": S.api_music_download, "eid": S._music_entry_id,
        "setcs": MS.set_cached_song}


def ck(name: str, cond, extra: str = ""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def restore():
    MS.parse_playlist = ORIG["parse"]
    S.log_mgr = ORIG["log_mgr"]
    S.music_proxy = ORIG["proxy"]
    S.api_music_download = ORIG["dl"]
    S._music_entry_id = ORIG["eid"]
    MS.set_cached_song = ORIG["setcs"]
    S._MUSIC_JOB.pop("running", None)


# ---------------------------------------------------------------- 假组件
class FakeCfg:
    def __init__(self, **kw):
        d = dict(S.ConfigManager.DEFAULTS)
        d.update(kw)
        self.data = d


class FakeEngine:
    def get_info(self, url, cfg):
        raise AssertionError("音乐订阅不该走 yt-dlp 那条读取分支")


class FakeQueue:
    def __init__(self):
        self.batches = []

    def add_urls(self, urls, options):
        self.batches.append((list(urls), dict(options or {})))
        return [str(i) for i in range(len(urls))]


class FakeTG:
    def __init__(self):
        self.notices = []

    def notify_sub(self, title, n, samples):
        self.notices.append((title, n, list(samples or [])))


class FakeLogMgr:
    def log(self, msg, level="info"):
        LOGS.append(f"[{level}] {msg}")


class MemSubs(S.SubscriptionManager):
    """只在内存里跑 —— 探针不许碰用户的 subscriptions.json。"""

    def load(self):
        self.subs = []

    def save(self):
        self.saved = getattr(self, "saved", 0) + 1


def new_mgr(**cfgkw):
    cfgkw.setdefault("sub_auto_download", True)
    q, tg = FakeQueue(), FakeTG()
    mgr = MemSubs(FakeEngine(), FakeCfg(**cfgkw), q, tg, lambda m, lv="info": LOGS.append(m))
    return mgr, q, tg


# ---------------------------------------------------------------- 桩：歌单解析
ROWS: list = []      # [(曲名, 歌手, 时长, 链接?)]，每轮现铸缓存 id，跟真 _cache_song 一样
DIAG: dict = {}


def row(title, artists, dur, url=""):
    return {"id": uuid.uuid4().hex[:8], "title": title, "artists": artists,
            "duration_s": dur, "url": url, "source": "NeteaseMusicClient", "album": "深夜歌单"}


def stub_parse():
    def _f(u, **kw):
        CALLS["parse"].append((u, dict(kw)))
        MS._LAST_PLAYLIST_DIAG.clear()
        MS._LAST_PLAYLIST_DIAG.update(DIAG)
        return [row(*r) for r in ROWS]
    return _f


def stub_parse_raise(exc):
    def _f(u, **kw):
        raise exc
    return _f


def fake_dl(already=0, message="musicdl 下载中"):
    def _f(body):
        CALLS["dl"].append(dict(body))
        ids = body.get("ids") or []
        return {"ok": True, "mode": "musicdl" if ids else "queue",
                "count": len(body.get("urls") or []), "already": already if ids else 0,
                "message": message}
    return _f


def msub(**kw):
    sub = {"id": "m1", "url": NETEASE, "kind": "music", "title": "", "last_ids": [],
           "last_error": "", "new_count": 0, "enabled": True, "auto_download": True, "rules": {}}
    sub.update(kw)
    return sub


NETEASE = "https://music.163.com/#/playlist?id=99887766"
QQ = "https://y.qq.com/n/ryqq/playlist/889977665"
SPOTIFY = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
APPLE = "https://music.apple.com/us/playlist/night-xpl.al.1.b"
DY_VIDEO = "https://www.douyin.com/video/7512345678901234567"
DY_LIST = "https://www.douyin.com/playlist/7512345678901234568"
YT = "https://www.youtube.com/watch?v=abcdefghijk"


def ids_of(sub):
    return set(sub.get("last_ids") or [])


def last():
    return LOGS[-1] if LOGS else ""


try:
    # ============================================================ A. 链接归谁管
    print("=== A. 域名表：哪些链接算音乐歌单 ===")
    ck("A1 网易云歌单归 Netease", MS.playlist_owner(NETEASE) == "NeteaseMusicClient",
       MS.playlist_owner(NETEASE))
    ck("A2 QQ 音乐歌单归 QQ", MS.playlist_owner(QQ) == "QQMusicClient", MS.playlist_owner(QQ))
    ck("A3 Spotify 歌单归 Spotify", MS.playlist_owner(SPOTIFY) == "SpotifyMusicClient", "")
    ck("A4 Apple 歌单归 Apple", MS.playlist_owner(APPLE) == "AppleMusicClient", "")
    ck("A5 抖音单视频不算歌单", MS.playlist_owner(DY_VIDEO) == "", MS.playlist_owner(DY_VIDEO))
    ck("A6 抖音歌单页算歌单", MS.playlist_owner(DY_LIST) == "SodaMusicClient", MS.playlist_owner(DY_LIST))
    ck("A7 YouTube 链接不算音乐歌单（仍走 yt-dlp）", MS.playlist_owner(YT) == "", "")
    ck("A8 B 站歌单不在音乐域名表里", MS.playlist_owner("https://space.bilibili.com/1/favlist") == "", "")
    ck("A9 空值/脏值不抛异常",
       all(MS.playlist_owner(x) == "" for x in ("", None, "歌单", "ftp://x", "://")))
    ck("A10 后端判定与域名表同源", S._is_music_playlist(NETEASE) and not S._is_music_playlist(DY_VIDEO))
    hosts = MS.music_playlist_hosts()
    ck("A11 域名表能下发给界面", "music.163.com" in hosts and "open.spotify.com" in hosts
       and hosts == sorted(hosts), hosts[:4])
    ck("A12 订阅类型：网易云歌单 → music", S._sub_kind_of({"url": NETEASE}) == "music", "")
    ck("A13 订阅类型：老数据没 kind 也按链接认", S._sub_kind_of({"url": QQ}) == "music", "")
    ck("A14 订阅类型：抖音单视频退回 yt-dlp", S._sub_kind_of({"url": DY_VIDEO}) == "", "")
    ck("A15 订阅类型：tg/rss 不被音乐抢走",
       S._sub_kind_of({"url": "https://t.me/s/naiveblue"}) == "tg"
       and S._sub_kind_of({"url": "https://example.com/feed.xml"}) == "rss", "")

    # ============================================================ B. add 的归类
    print("=== B. 添加订阅：落到哪条分支由后端定，不信界面预览 ===")
    mgr, _q, _t = new_mgr()
    s1 = mgr.add(NETEASE, kind="music")
    ck("B1 音乐歌单存成 music", s1.get("kind") == "music", s1.get("kind"))
    s2 = mgr.add(QQ)
    ck("B2 不传 kind 也按链接推成 music", s2.get("kind") == "music", s2.get("kind"))
    s3 = mgr.add(DY_VIDEO, kind="music")
    ck("B3 界面谎报 music 的抖音单视频被退回", s3.get("kind") == "", s3.get("kind"))
    s4 = mgr.add(YT, kind="bogus")
    ck("B4 乱写的 kind 当作没写", s4.get("kind") == "", s4.get("kind"))
    s5 = mgr.add(NETEASE, kind="music")
    ck("B5 同一条歌单不会建出两条订阅", len(mgr.subs) == 4 and s5.get("id") == s1.get("id"), len(mgr.subs))
    try:
        mgr.add("music.163.com/#/playlist?id=1", kind="music")
        ck("B6 少了协议头要报错", False)
    except ValueError as e:
        ck("B6 少了协议头要报错", "http" in str(e), e)
    ck("B7 音乐订阅不看 engine（没碰 yt-dlp）", True)

    # ============================================================ C. 游标口径
    print("=== C. 追新游标：认歌，不认每次现铸的缓存 id ===")
    a = S._music_entry_id("  夜航船  ", "陈奕迅 / 王菲", 245)
    b = S._music_entry_id("夜航船", "陈奕迅 / 王菲", 245)
    ck("C1 前后空白与多余空格都归一", a == b, (a, b))
    ck("C2 游标带 mus: 前缀，日志里可读", a.startswith("mus:") and "夜航船" in a, a)
    ck("C3 时长不同算两首歌", S._music_entry_id("夜航船", "陈", 245) != S._music_entry_id("夜航船", "陈", 246))
    ck("C4 曲名不同算两首歌", S._music_entry_id("现场版", "陈", 245) != S._music_entry_id("录音室", "陈", 245))
    ck("C5 超长曲名截到 124 内", len(S._music_entry_id("歌" * 300, "x", 1)) <= 124, "")
    ck("C6 音乐窗口与游标同为 300（窗口不会被游标截断）", S._sub_window("music") == (300, 300),
       S._sub_window("music"))
    ck("C7 视频订阅窗口不宽于游标", S._sub_window("")[0] <= S._sub_window("")[1], S._sub_window(""))

    # ============================================================ D. 读一次歌单
    print("=== D. 读歌单：条目形状与报错 ===")
    S.log_mgr = FakeLogMgr()
    S.music_proxy = lambda *a, **k: ""
    MS.parse_playlist = stub_parse()
    ROWS[:] = [("夜航船", "陈奕迅", 245), ("孤勇者", "陈奕迅", 177, "https://music.163.com/song/1.mp3"),
               ("", "佚名", "3:22"), ("没有时长的歌", "某人", 0)]
    DIAG.clear(); DIAG.update({"name": "深夜歌单 Vol.1", "route": "musicdl"})
    LOGS.clear(); CALLS["parse"].clear()
    entries, name, err = S._music_sub_entries(msub())
    ck("D1 条目数与歌单一致且无报错", len(entries) == 4 and err == "", (len(entries), err))
    ck("D2 歌单名从诊断里带出来", name == "深夜歌单 Vol.1", name)
    e0 = entries[0]
    ck("D3 条目带 mus: 游标", e0["id"].startswith("mus:"), e0["id"])
    ck("D4 条目一律标成音频且无日期", e0["kind"] == "audio" and e0["date"] == "", e0)
    ck("D5 缓存 id 透传成 sid（下载要用）", len(e0["sid"]) == 8, e0["sid"])
    ck("D6 直链原样留着（没有 sid 时兜底用）", entries[1]["url"].startswith("http"), entries[1]["url"])
    ck("D7 字符串时长会换算成秒", entries[2]["duration"] == 202, entries[2]["duration"])
    ck("D8 没时长的条目记 0，不因时长被挡", entries[3]["duration"] == 0, entries[3]["duration"])
    ck("D9 缺曲名有兜底标题", entries[2]["title"] == "（无曲名）", entries[2]["title"])
    ck("D10 按订阅链接与全局源设置调用解析", CALLS["parse"][0][0] == NETEASE
       and {"sources", "work_dir", "cookies", "proxy", "prefer"} <= set(CALLS["parse"][0][1]),
       sorted(CALLS["parse"][0][1]))
    ROWS[:] = []
    DIAG.clear(); DIAG.update({"hint": "这张歌单需要登录才能看"})
    _e, _n, err2 = S._music_sub_entries(msub())
    ck("D11 空结果要把平台的提示当报错上屏", err2 == "这张歌单需要登录才能看" and _e == [], err2)
    DIAG.clear()
    _e, _n, err3 = S._music_sub_entries(msub())
    ck("D12 平台没给提示也要有兜底报错", "没读到任何曲目" in err3, err3)
    MS.parse_playlist = stub_parse_raise(RuntimeError("解析炸了"))
    _e, _n, err4 = S._music_sub_entries(msub())
    ck("D13 解析异常翻成人话且不上抛", "歌单读取失败" in err4 and "解析炸了" in err4, err4)
    ck("D14 读失败时不返回半成品条目", _e == [], _e)

    # ============================================================ E. 追新全流程
    print("=== E. 定时扫描：只下新歌，读不到不动游标 ===")
    MS.parse_playlist = stub_parse()
    S.api_music_download = fake_dl()
    ROWS[:] = [("夜航船", "陈奕迅", 245), ("孤勇者", "陈奕迅", 177)]
    DIAG.clear(); DIAG.update({"name": "深夜歌单"})

    mgr, q, tg = new_mgr(sub_first_download_n=0)
    sub = mgr.add(NETEASE, kind="music")
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E1 首轮只记游标不下载", n == 0 and not CALLS["dl"] and len(ids_of(sub)) == 2, (n, CALLS["dl"]))
    ck("E2 标题取歌单名", sub["title"] == "深夜歌单", sub["title"])
    ck("E3 日志说明跳过首次下载", any("记录 2 条" in m and "跳过首次下载" in m for m in LOGS), last())

    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E4 内容没变 → 0 新增、不重复下（缓存 id 每轮都换）", n == 0 and not CALLS["dl"], (n, CALLS["dl"]))

    ROWS[:] += [("起风了", "买辣椒也用券", 321), ("夜航船 (Live)", "陈奕迅", 260)]
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E5 新增两首 → 一次入队两首", n == 2 and len(CALLS["dl"]) == 1 and len(CALLS["dl"][0]["ids"]) == 2,
       (n, CALLS["dl"]))
    ck("E6 入队带的是这一轮的缓存 id，且要求跳过目录已有的",
       CALLS["dl"][0].get("skip_downloaded") is True and all(len(i) == 8 for i in CALLS["dl"][0]["ids"]),
       CALLS["dl"][0])
    ck("E7 日志写明新增/入队与生效规则", any("新增 2 条" in m and "入队 2 条" in m and "每次最多 20 条" in m
                                        for m in LOGS), last())
    ck("E8 通知只推真正的新歌样本", tg.notices and tg.notices[-1][1] == 2
       and any("起风了" in x for x in tg.notices[-1][2]), tg.notices[-1] if tg.notices else None)

    S._MUSIC_JOB["running"] = True
    ROWS[:] += [("平凡之路", "朴树", 300)]
    before_ids, before_new = ids_of(sub), sub["new_count"]
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    S._MUSIC_JOB.pop("running", None)
    ck("E9 上一批没跑完 → 这轮不下载也不记新增", n == 0 and not CALLS["dl"] and ids_of(sub) == before_ids,
       (n, CALLS["dl"]))
    ck("E10 挡板话术点名在等什么", any("上一批音乐下载还没结束" in m and "不记录新增" in m for m in LOGS), last())
    ck("E11 累计新增数也没被虚增", sub["new_count"] == before_new, (sub["new_count"], before_new))
    CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E12 上一批跑完后，被推迟的那首补上了", n == 1 and len(CALLS["dl"][0]["ids"]) == 1, (n, CALLS["dl"]))

    sub["rules"] = {"skip_kw": "Live", "max_per_scan": 1}
    ROWS[:] += [("补录 (Live)", "某人", 190), ("晚风", "某人", 200), ("长风", "某人", 210)]
    before_ids = ids_of(sub)
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E13 三首新增里只下 1 首（规则挡一首、超上限留一首）",
       n == 3 and len(CALLS["dl"][0]["ids"]) == 1, (n, CALLS["dl"]))
    ck("E14 超上限那首不算已读，下次还会补", "mus:长风|某人|210" not in ids_of(sub)
       and "mus:晚风|某人|200" in ids_of(sub), sorted(ids_of(sub) - before_ids))
    ck("E15 被规则挡掉的记成已读（改规则不回头补，要补用回填）",
       "mus:补录 (Live)|某人|190" in ids_of(sub), sorted(ids_of(sub) - before_ids))
    ck("E16 日志报了挡掉的原因与留到下次的条数",
       any("命中排除词「Live」" in m and "留到下次扫描" in m for m in LOGS), last())
    CALLS["dl"].clear()
    n = mgr.scan_one(sub)
    ck("E17 下次扫描只补超限制那一首", n == 1 and CALLS["dl"][0]["ids"]
       and len(CALLS["dl"][0]["ids"]) == 1, (n, CALLS["dl"]))

    S.api_music_download = fake_dl(already=1)
    sub2 = msub(id="m2", rules={}, last_ids=["mus:旧歌|某人|100"])
    ROWS[:] = [("夜航船", "陈奕迅", 245), ("新歌", "某人", 180)]
    LOGS.clear(); CALLS["dl"].clear()
    mgr.scan_one(sub2)
    ck("E18 目录里已有的不计进「入队 N 条」", any("入队 1 条" in m and "新增 2 条" in m for m in LOGS), LOGS)
    ck("E19 下载回复里的 message 会转进订阅日志",
       any("订阅「深夜歌单」→ musicdl 下载中" in m for m in LOGS), last())
    ck("E20 游标是拼接不是覆盖：窗口外的旧 id 仍留着", ids_of(sub2) == {"mus:旧歌|某人|100",
       S._music_entry_id("夜航船", "陈奕迅", 245), S._music_entry_id("新歌", "某人", 180)},
       sorted(ids_of(sub2)))
    before_ids = ids_of(sub2)
    ROWS[:] = []
    DIAG.clear(); DIAG.update({"hint": "Cookie 过期"})
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub2)
    ck("E21 读失败不动游标、不下载", n == 0 and not CALLS["dl"] and ids_of(sub2) == before_ids,
       (n, sorted(sub2["last_ids"])))
    ck("E22 报错挂到订阅上并写日志", sub2["last_error"] == "Cookie 过期"
       and any("读不到：Cookie 过期" in m for m in LOGS), (sub2["last_error"], LOGS[-1] if LOGS else ""))
    ck("E23 探针没写过 subscriptions.json",
       (S.SUBS_FILE.read_bytes() if S.SUBS_FILE.exists() else None) == SUBS_SNAPSHOT)

    # ============================================================ F. 整张歌单回填
    print("=== F. 回填：不看游标，按规则补下整张歌单 ===")
    DIAG.clear(); DIAG.update({"name": "深夜歌单"})
    S.api_music_download = fake_dl()
    mgr, q, tg = new_mgr(sub_first_download_n=0)
    sub = msub(id="m3", last_ids=[], rules={"max_per_scan": 0})
    ROWS[:] = [("歌 A", "甲", 200), ("歌 B", "乙", 210), ("歌 C", "丙", 220)]
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "", "until": ""})
    ck("F1 音乐回填不要求日期窗", n == 3 and len(CALLS["dl"][0]["ids"]) == 3, (n, CALLS["dl"]))
    ck("F2 日志写「回填 整张歌单」而不是日期区间",
       any("回填 整张歌单" in m and "入选 3 条" in m for m in LOGS), last())
    ck("F3 入选的都记成已读", len(ids_of(sub)) == 3, sorted(ids_of(sub)))
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "", "until": ""})
    ck("F4 回填不看游标：再点一次仍按整张歌单重来", n == 3 and len(CALLS["dl"]) == 1, n)
    ck("F5 重复回填靠下载层 skip_downloaded 兜底（不会另存副本）",
       CALLS["dl"][0].get("skip_downloaded") is True, CALLS["dl"][0])
    sub["rules"] = {"skip_kw": "歌 B", "max_per_scan": 2}
    sub["last_ids"] = []
    LOGS.clear(); CALLS["dl"].clear()
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "", "until": ""})
    ck("F6 回填同样受本订阅规则与上限管", n == 2 and len(CALLS["dl"][0]["ids"]) == 2, (n, CALLS["dl"]))
    ck("F7 回填日志说明挡掉几条", any("另有 1 条被规则挡掉" in m and "入选 2 条" in m for m in LOGS), last())
    ck("F8 回填只把入选的记成已读，被规则挡掉的不吞掉",
       "mus:歌 B|乙|210" not in ids_of(sub) and "mus:歌 A|甲|200" in ids_of(sub), sorted(ids_of(sub)))
    mgr5, q5, _t5 = new_mgr()
    LOGS.clear(); CALLS["dl"].clear()
    vsub = {"id": "v1", "url": YT, "kind": "", "title": "视频频道", "last_ids": [], "rules": {}}
    mgr5._backfill(vsub, [{"id": "vid1", "title": "一期节目", "url": "https://u/1", "duration": 900}],
                   S._norm_sub_rules({"since": "2026-01-01", "until": "2026-02-01"}), "2026-09-24 00:00:00")
    ck("F9 非音乐订阅的回填仍按日期说、按条说",
       any("按日期回填 2026-01-01~2026-02-01" in m and "入选 1 条" in m for m in LOGS), last())
    ck("F10 视频回填走 yt-dlp 队列而不是音乐下载", q5.batches and not CALLS["dl"], q5.batches)

    # ============================================================ G. 反向验证
    print("=== G. 反向验证：把游标改成每次现铸的 id，整张歌单必须被反复重下 ===")
    real_id = S._music_entry_id
    S._music_entry_id = lambda *a, **k: "mus:" + uuid.uuid4().hex
    ROWS[:] = [("夜航船", "陈奕迅", 245)]
    mgr3, _q3, _t3 = new_mgr(sub_first_download_n=0)
    S.api_music_download = fake_dl()
    sub3 = msub(id="m9", last_ids=[])
    CALLS["dl"].clear()
    mgr3.scan_one(sub3)
    first = set(sub3["last_ids"])
    CALLS["dl"].clear()
    n2 = mgr3.scan_one(sub3)
    second = set(sub3["last_ids"])
    S._music_entry_id = real_id
    ck("G1 游标若用现铸 id：第二轮又算成新歌并再次入队", n2 == 1 and len(CALLS["dl"]) == 1
       and len(CALLS["dl"][0]["ids"]) == 1, (n2, CALLS["dl"]))
    ck("G2 坏口径下游标越滚越长：一首歌的单子攒出了两个 id", len(first) == 1 and len(second) == 2,
       (sorted(first), sorted(second)))

    ROWS[:] = [("夜航船", "陈奕迅", 245), ("新加的歌", "某人", 180)]
    mgr4, _q4, _t4 = new_mgr(sub_first_download_n=0)
    sub4 = msub(id="m8", last_ids=[S._music_entry_id("夜航船", "陈奕迅", 245)], auto_download=True)
    S.api_music_download = fake_dl()
    CALLS["dl"].clear()
    n = mgr4.scan_one(sub4)
    ck("G3 正确口径下只下那一首新歌", n == 1 and len(CALLS["dl"][0]["ids"]) == 1, (n, CALLS["dl"]))
    ROWS[:] += [("又加一首", "某人", 190)]
    S._MUSIC_JOB["running"] = True
    before_ids = set(sub4["last_ids"])
    CALLS["dl"].clear()
    n = mgr4.scan_one(sub4)
    S._MUSIC_JOB.pop("running", None)
    ck("G4 挡板生效：有新歌但上一批在跑 → 不入队也不记新增",
       n == 0 and set(sub4["last_ids"]) == before_ids and not CALLS["dl"], (n, sorted(sub4["last_ids"])))
    CALLS["dl"].clear()
    ck("G5 撤掉挡板后同一首立刻能下（说明只是延后不是丢掉）",
       mgr4.scan_one(sub4) == 1 and len(CALLS["dl"][0]["ids"]) == 1, (sorted(sub4["last_ids"]), CALLS["dl"]))

    # ============================================================ H. 快列模式的行
    print("=== H. 快列模式：行里只有曲名（无缓存 id、歌手与时长都空） ===")
    SONG_URL = "https://music.163.com/#/song?id=111"
    SONG_URL_2 = "https://music.163.com/#/song?id=222"

    def stub_parse_noid(*rows):
        def _f(u, **kw):
            CALLS["parse"].append((u, dict(kw)))
            MS._LAST_PLAYLIST_DIAG.clear()
            MS._LAST_PLAYLIST_DIAG.update(DIAG)
            return [{"id": x[4] if len(x) > 4 else "", "title": x[0], "artists": x[1],
                     "duration_s": x[2], "url": x[3], "source": "NeteaseMusicClient"}
                    for x in rows]
        return _f

    def n_match(ids):
        """照 server.py 里下载首轮那段判定重算一遍：有几首要走「按曲名匹配」。"""
        from music_search import get_cached_song
        return sum(1 for i in ids
                   if isinstance(get_cached_song(i), dict) and get_cached_song(i).get("needs_match"))

    # H1~H2 游标加了链接判别段
    ROWS[:] = [("夜航船", "", 0, SONG_URL)]
    LOGS.clear(); CALLS["dl"].clear()
    k_nolink = S._music_entry_id("夜航船", "", 0)
    k_a = S._music_entry_id("夜航船", "", 0, SONG_URL)
    k_b = S._music_entry_id("夜航船", "", 0, SONG_URL_2)
    ck("H1 只有曲名的行：游标尾部带链接哈希，两首同名不同曲不再并成一条",
       k_a != k_b and k_a.startswith("mus:夜航船||0#") and k_b.startswith("mus:夜航船||0#"), (k_a, k_b))
    ck("H2 歌手或时长任一还在时键的形状不动（老订阅不用重下）",
       S._music_entry_id("夜航船", "陈奕迅", 245) == "mus:夜航船|陈奕迅|245"
       and S._music_entry_id("夜航船", "", 245) == "mus:夜航船||245"
       and S._music_entry_id("夜航船", "陈奕迅", 0) == "mus:夜航船|陈奕迅|0", k_a)
    ck("H2b 没传链接就不加哈希（收藏清单那个主键的形状一分不改）", k_nolink == "mus:夜航船||0", k_nolink)
    k_long = S._music_entry_id("歌" * 300, "", 0, SONG_URL)
    ck("H2c 超长曲名也不会把链接哈希挤出 124 之外（截的是曲名，不是尾巴）",
       len(k_long) <= 124 and re.match(r"^mus:歌{80}\|\|0#[0-9a-f]{12}$", k_long), k_long[-20:])

    # H3~H6b 占位条目：让这批行走「按曲名匹配」那一轮
    MS.parse_playlist = stub_parse_noid(("夜航船", "", 0, SONG_URL), ("夜航船", "", 0, SONG_URL_2))
    DIAG.clear(); DIAG.update({"name": "深夜歌单 Vol.1", "route": "yt-dlp"})
    S.api_music_download = fake_dl()
    LOGS.clear(); CALLS["dl"].clear()
    rowsA, _nA, _eA = S._music_sub_entries(msub())
    keysA = [e["id"] for e in rowsA]
    sidsA = [e["sid"] for e in rowsA]
    ck("H3 没有缓存 id 的行当场铸一个 sid（不再拿歌页链接丢通用队列）",
       all(len(s) == 36 and s.count("-") == 4 for s in sidsA) and len(set(sidsA)) == 2, sidsA)
    ck("H4 铸出来的槽位是真占位：只有曲名、标着 needs_match",
       all(isinstance(MS.get_cached_song(s), dict) and MS.get_cached_song(s).get("needs_match")
           and MS.get_cached_song(s).get("title") == "夜航船" for s in sidsA),
       MS.get_cached_song(sidsA[0]))
    ck("H5 下行首轮能认出这批有几首要匹配（与 server.py 里的判定同式）", n_match(sidsA) == 2, sidsA)
    ck("H6 同名不同曲的两行拿到两条不同游标，各自记已读",
       len(set(keysA)) == 2 and all("#" in k for k in keysA), keysA)
    keysB = [e["id"] for e in S._music_sub_entries(msub())[0]]
    ck("H6b 重解析一次游标不变（每轮另铸的 uuid 不会串进键里）", keysB == keysA, (keysA, keysB))

    mgr6, q6, _t6 = new_mgr(sub_first_download_n=0)
    sub6 = msub(id="h7", last_ids=[], auto_download=True)
    LOGS.clear(); CALLS["dl"].clear()
    n0 = mgr6.scan_one(sub6)
    ck("H7 首轮是订阅初始化：只把两条游标记下来，一首都不下",
       n0 == 0 and not CALLS["dl"] and sorted(sub6["last_ids"]) == sorted(keysA), (n0, last()))
    # 歌单里又来了一首同名的另一个版本 —— 老口径会认成「已读过」，永远下不到
    MS.parse_playlist = stub_parse_noid(("夜航船", "", 0, SONG_URL), ("夜航船", "", 0, SONG_URL_2),
                                        ("夜航船", "", 0, "https://music.163.com/#/song?id=333"))
    CALLS["dl"].clear()
    n = mgr6.scan_one(sub6)
    ck("H8 同名不同曲的第三首被认成新增并进音乐流程（走 ids，不落通用队列）",
       n == 1 and len(CALLS["dl"]) == 1 and set(CALLS["dl"][0]) == {"ids", "skip_downloaded"}
       and len(CALLS["dl"][0]["ids"]) == 1 and not q6.batches, (n, CALLS["dl"], q6.batches))
    ck("H8b 送下去的是 uuid 形状的缓存槽、且标着待匹配（不是歌页链接）",
       len(CALLS["dl"][0]["ids"][0]) == 36
       and isinstance(MS.get_cached_song(CALLS["dl"][0]["ids"][0]), dict)
       and MS.get_cached_song(CALLS["dl"][0]["ids"][0]).get("needs_match"), CALLS["dl"][0]["ids"])
    CALLS["dl"].clear()
    n2 = mgr6.scan_one(sub6)
    ck("H9 第二轮同一张歌单没有新增（游标稳定，不会整张重下）",
       n2 == 0 and not CALLS["dl"] and len(sub6["last_ids"]) == 3, (n2, sorted(sub6["last_ids"])))

    # H10~H13 反向验证
    mgr7, _q7, _t7 = new_mgr(sub_first_download_n=0)
    MS.set_cached_song = lambda *a, **k: None      # 只铸 uuid、不落缓存
    sub7 = msub(id="h10", last_ids=[S._music_entry_id("已知歌", "甲", 100)])
    S.api_music_download = fake_dl()
    MS.parse_playlist = stub_parse_noid(("已知歌", "甲", 100, "https://music.163.com/#/song?id=9", "abc12345"),
                                        ("夜航船", "", 0, SONG_URL))
    LOGS.clear(); CALLS["dl"].clear()
    n3 = mgr7.scan_one(sub7)
    ck("H10 反向验一：不写缓存就不可能被匹配轮认到（H4/H5 靠的就是那次写入）",
       n3 == 1 and len(CALLS["dl"][0]["ids"]) == 1 and len(CALLS["dl"][0]["ids"][0]) == 36
       and n_match(CALLS["dl"][0]["ids"]) == 0, (n3, CALLS["dl"]))
    MS.set_cached_song = ORIG["setcs"]
    rowsE = {e["title"]: e for e in S._music_sub_entries(msub())[0]}
    ck("H11 换回真 set_cached_song 立刻认得到（桩不许比真函数窄）",
       len(rowsE["夜航船"]["sid"]) == 36 and n_match([rowsE["夜航船"]["sid"]]) == 1,
       rowsE["夜航船"]["sid"])
    ck("H11b 行上本来就带缓存 id 的不另铸槽、原样透传",
       rowsE["已知歌"]["sid"] == "abc12345" and n_match([rowsE["已知歌"]["sid"]]) == 0,
       rowsE["已知歌"]["sid"])
    LOGS.clear(); CALLS["dl"].clear()
    cnt, _sa = mgr7._enqueue_music(msub(id="h12", title="深夜歌单"),
                                   [{"id": "mus:x||0", "sid": "", "url": SONG_URL, "title": "夜航船"}])
    ck("H12 反向验二：真没有 sid 的行仍退回通用队列兜底（不是直接丢）",
       cnt == 1 and CALLS["dl"][0].get("urls") == [SONG_URL] and "ids" not in CALLS["dl"][0],
       (cnt, CALLS["dl"]))
    LOGS.clear(); CALLS["dl"].clear()
    cnt, _s = mgr7._enqueue_music(msub(id="h13", title="深夜歌单"),
                                  [{"id": "mus:  ||0", "sid": "", "url": "", "title": "（无曲名）"}])
    ck("H13 反向验三：既无 sid 又无直链 → 当场报「一条都没法下」，不静默吞",
       cnt == 0 and not CALLS["dl"] and any("一条都没法下" in m for m in LOGS), (cnt, last()))

    # H14 收藏清单那头的真实调用点：整行 id 不掺链接哈希
    fav = S._music_fav_row({"name": "夜航船", "id": "", "duration": ""})
    ck("H14 收藏清单条目仍用旧形状 id（那是存盘的清单主键）",
       fav.get("id") == "mus:夜航船||0", fav.get("id"))

finally:
    restore()

print()
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
