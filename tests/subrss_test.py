r"""RSS 并进订阅 + 单订阅按日期回填 的离线自检。

全程不联网、不碰 subscriptions.json / rss_feeds.json（RSS 文件测试指向 Temp 副本）：
假 engine（被调用就直接炸，证明 RSS 源真的没去问 yt-dlp）、假 queue、save() 空转。

跑法：`python tests/subrss_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


class BoomEngine:
    def get_info(self, url, cfg):
        raise AssertionError(f"RSS / Telegram 订阅不该去问 yt-dlp engine: {url}")


class FakeCfg:
    def __init__(self, **kw):
        d = dict(S.ConfigManager.DEFAULTS)
        d.update(kw)
        self.data = d


class FakeQueue:
    def __init__(self):
        self.batches = []

    def add_urls(self, urls, options):
        self.batches.append((list(urls), dict(options or {})))
        return [str(i) for i in range(len(urls))]

    def all_urls(self):
        return [u for b in self.batches for u in b[0]]


class FakeTG:
    def notify_sub(self, title, n, samples):
        LOGS.append(f"notify {title} +{n}")


class MemSubs(S.SubscriptionManager):
    def load(self):
        self.subs = []

    def save(self):
        self.saved = getattr(self, "saved", 0) + 1


def new_mgr(**cfgkw):
    q = FakeQueue()
    return MemSubs(BoomEngine(), FakeCfg(**cfgkw), q, FakeTG(),
                   lambda m, lv="info": LOGS.append(m)), q


def feed_entry(pid, link=None, typ="video", pub="Tue, 09 Sep 2025 08:00:00 GMT"):
    return {"id": f"tag:example.com,2025:{pid}", "title": f"条目 {pid}",
            "link": link or f"https://example.com/watch?v={pid}",
            "published": pub,
            "enclosure": f"https://cdn.example.com/e{pid}.mp3" if typ == "audio" else ""}


print("=== A. 订阅走哪条读取分支 ===")
ck("A1 .xml 链认成 RSS", S._sub_kind_of({"url": "https://a.com/feed.xml"}) == "rss")
ck("A2 /feed 路径认成 RSS", S._sub_kind_of({"url": "https://a.com/blog/feed"}) == "rss")
ck("A3 YouTube 频道链仍是 yt-dlp", S._sub_kind_of({"url": "https://www.youtube.com/@ffmpeg"}) == "")
ck("A4 B 站空间不误判成 RSS", S._sub_kind_of({"url": "https://space.bilibili.com/123"}) == "")
ck("A5 Telegram 频道认成 tg", S._sub_kind_of({"url": "https://t.me/s/europa_press"}) == "tg")
ck("A6 显式 kind 优先（搬家时写死的不会被猜跑）",
   S._sub_kind_of({"url": "https://a.com/feed.xml", "kind": "rss"}) == "rss"
   and S._sub_kind_of({"url": "https://a.com/x", "kind": "rss"}) == "rss")
ck("A7 未知 kind 回落到按链接猜", S._sub_kind_of({"url": "https://a.com/f.atom", "kind": "bogus"}) == "rss")
ck("A8 RSS 源必须是完整 http 链", S._looks_like_feed("feed://x") and not S._looks_like_feed("@name"))

print("=== B. 条目日期归一 ===")
ck("B1 RFC822 pubDate 取到日", S._rss_pub_date("Tue, 09 Sep 2025 08:00:00 GMT") == "2025-09-09")
ck("B2 ISO 日期照收", S._rss_pub_date("2025-09-09T08:00:00+08:00") == "2025-09-09")
ck("B3 垃圾日期留空而不是瞎猜", S._rss_pub_date("最近") == "" and S._rss_pub_date("") == "")

print("=== C. RSS 条目换算 ===")
orig_parse, orig_decide = S.parse_rss_feed, S.proxy_decision
S.proxy_decision = lambda *a, **k: ("proxy", "http://127.0.0.1:7897")
S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
    feed_entry(1), feed_entry(2, typ="audio"),
    feed_entry(3, link="mailto:nobody@example.com"),
    {"id": "", "title": "没链接", "link": "", "published": "", "enclosure": ""},
]}
try:
    mgr, q = new_mgr()
    rows, ftitle, err = S._rss_sub_entries("https://a.com/feed.xml")
    ck("C1 源标题回传", ftitle == "示例源" and err == "", ftitle)
    ck("C2 非 http 的条目丢掉", [r["id"] for r in rows] == [
        "tag:example.com,2025:1", "tag:example.com,2025:2"], [r["id"] for r in rows])
    ck("C3 enclosure 优先当下载链", rows[1]["url"] == "https://cdn.example.com/e2.mp3")
    ck("C4 音频扩展名认成 audio", rows[1]["kind"] == "audio" and rows[0]["kind"] == "video")
    ck("C5 日期已归一，日期窗能用", rows[0]["date"] == "2025-09-09", rows[0]["date"])
finally:
    S.parse_rss_feed = orig_parse

S.parse_rss_feed = lambda url, proxy="": (_ for _ in ()).throw(ValueError("boom"))
try:
    rows, t, err = S._rss_sub_entries("https://a.com/feed.xml")
    ck("C6 读失败要说清原因，不能当 0 条", rows == [] and "boom" in err, err)
finally:
    S.parse_rss_feed = orig_parse

S.parse_rss_feed = lambda url, proxy="": {"title": "空源", "entries": [
    {"id": "x", "title": "只有文字", "link": "", "published": "", "enclosure": ""}]}
try:
    rows, t, err = S._rss_sub_entries("https://a.com/feed.xml")
    ck("C7 源里没有可下载条目时也报错", rows == [] and "没有可下载" in err, err)
finally:
    S.parse_rss_feed = orig_parse
S.proxy_decision = orig_decide

print("=== D. RSS 订阅：首次只记游标，二次只推新增 ===")
calls: list[dict] = []
S.proxy_decision = lambda *a, **k: ("direct", "")
S.parse_rss_feed = lambda url, proxy="": (calls.append({"url": url, "proxy": proxy}) or
                                          {"title": "示例源", "entries": [feed_entry(2), feed_entry(1)]})
try:
    mgr, q = new_mgr(sub_first_download_n=0, sub_auto_download=True)
    sub = mgr.add("https://a.com/feed.xml", kind="rss")
    ck("D1 加进来就标成 rss 分支", sub["kind"] == "rss")
    ck("D2 单条订阅默认开自动下载", sub["auto_download"] is True)
    n = mgr.scan_one(sub, auto_download=False)
    ck("D3 首次扫描只记 ID 不下", n == 0 and len(sub["last_ids"]) == 2 and q.batches == [])
    ck("D4 标题取到源标题", sub["title"] == "示例源", sub["title"])
    calls.clear()
    S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
        feed_entry(3), feed_entry(2), feed_entry(1)]}
    n2 = mgr.scan_one(sub, auto_download=True)
    ck("D5 新增一条就入队一条", n2 == 1 and q.all_urls() == ["https://example.com/watch?v=3"], q.all_urls())
    ck("D6 老条目不重复推", all("v=1" not in u and "v=2" not in u for u in q.all_urls()))
    ck("D7 游标不留重复 id（重复会把上限填满，老条目会被当成未读重下）",
       len(sub["last_ids"]) == len(set(sub["last_ids"])), sub["last_ids"])
finally:
    S.parse_rss_feed = orig_parse
    S.proxy_decision = orig_decide

print("=== E. 单条订阅关掉自动下载：只列新增不入队 ===")
S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [feed_entry(9), feed_entry(1)]}
try:
    mgr, q = new_mgr(sub_auto_download=True)
    sub = mgr.add("https://a.com/feed.xml", kind="rss")
    mgr.scan_one(sub, auto_download=False)
    mgr.set_rules(sub["id"], sub["rules"], None, False)
    ck("E1 规则接口能改自动下载开关", sub["auto_download"] is False)
    S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
        feed_entry(10), feed_entry(9), feed_entry(1)]}
    n = mgr.scan_one(sub, auto_download=True)
    ck("E2 这条自己关了 → 即使调用方要自动下也不入队", n == 1 and q.batches == [], n)
    ck("E3 新增数仍累计（列表要看得见有几个新的）", sub["new_count"] == 1, sub["new_count"])
    ck("E4 关掉时新增也算见过", "tag:example.com,2025:10" in sub["last_ids"], sub["last_ids"])
    mgr.set_rules(sub["id"], sub["rules"], None, True)
    n2 = mgr.scan_one(sub, auto_download=True)
    ck("E5 重新打开不会把之前只列未下的补炸一遍", n2 == 0 and q.batches == [], n2)
    S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
        feed_entry(11), feed_entry(10), feed_entry(9), feed_entry(1)]}
    mgr.scan_one(sub, auto_download=True)
    ck("E6 打开后的新条目照常入队", q.all_urls() == ["https://example.com/watch?v=11"], q.all_urls())
    again = mgr.add("https://a.com/feed.xml", kind="rss", auto_download=False)
    ck("E6b 重复导入不新建订阅，只按这次的勾选改开关",
       again["id"] == sub["id"] and len(mgr.list()) == 1 and sub["auto_download"] is False,
       [len(mgr.list()), sub["auto_download"]])
    mgr2, q2 = new_mgr(sub_auto_download=False)
    s2 = mgr2.add("https://a.com/feed2.xml", kind="rss")
    mgr2.scan_one(s2, auto_download=False)
    S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
        feed_entry(12), feed_entry(9), feed_entry(1)]}
    n3 = mgr2.scan_one(s2, auto_download=True)
    ck("E7 全局总开关关掉时一律不入队（但仍报新增）", n3 == 1 and q2.batches == [], n3)
finally:
    S.parse_rss_feed = orig_parse

print("=== F. 按日期窗回填历史 ===")
S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
    feed_entry(5, pub="2025-09-05"), feed_entry(4, pub="2025-09-04"),
    feed_entry(3, pub="2025-08-20"), feed_entry(2, pub="2025-08-01")]}
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://a.com/feed.xml", kind="rss")
    mgr.scan_one(sub, auto_download=False)
    ck("F1 首次把整源记成已见", len(sub["last_ids"]) == 4, sub["last_ids"])
    n = mgr.scan_one(sub, auto_download=True)
    ck("F2 追新此时没有新增", n == 0 and q.batches == [])
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "2025-09-01", "until": "2025-09-30"})
    ck("F3 回填不看游标：窗口内 2 条入队", n == 2 and q.all_urls() == [
        "https://example.com/watch?v=5", "https://example.com/watch?v=4"], q.all_urls())
    ck("F4 只把回填下掉的标成已见", set(sub["last_ids"]) >= {
        "tag:example.com,2025:5", "tag:example.com,2025:4"}, sub["last_ids"])
    ck("F5 窗口外的条目没被吞（游标仍是原来的 4 条以内）", len(sub["last_ids"]) == 4, sub["last_ids"])
    q.batches.clear()
    n2 = mgr.scan_one(sub, auto_download=True)
    ck("F6 回填不污染追新口径（下次追新仍 0 新增）", n2 == 0, n2)
    sub["auto_download"] = False
    q.batches.clear()
    n3 = mgr.scan_one(sub, auto_download=True, backfill={"since": "2025-08-01", "until": "2025-08-31"})
    ck("F7 回填是明确点击：这条没开自动下载也照下（只有追新才看开关）",
       n3 == 2 and len(q.all_urls()) == 2, q.all_urls())
finally:
    S.parse_rss_feed = orig_parse

print("=== G. 回填受规则约束 + 单次上限截断要说清 ===")
S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [
    feed_entry(i, pub=f"2025-09-{i:02d}") for i in (9, 8, 7, 6)]}
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://a.com/feed.xml", kind="rss")
    mgr.set_rules(sub["id"], {"only_kw": "条目 8", "max_per_scan": 20})
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "2025-09-01", "until": "2025-09-30"})
    ck("G1 关键词规则在回填里照样生效", n == 1 and q.all_urls() == [
        "https://example.com/watch?v=8"], q.all_urls())
    q.batches.clear()
    mgr.set_rules(sub["id"], {"max_per_scan": 2})
    n = mgr.scan_one(sub, auto_download=True, backfill={"since": "2025-09-01", "until": "2025-09-30"})
    ck("G2 单次上限截断，且不把截断的标成已见", n == 2 and len(sub["last_ids"]) == 2, sub["last_ids"])
    ck("G3 截断提示写进日志", any("再点一次回填" in m for m in LOGS), [m for m in LOGS if "回填" in m][-1:])
finally:
    S.parse_rss_feed = orig_parse

print("=== H. 同一订阅不并发扫描 ===")
class BusyMgr(MemSubs):
    pass

S.parse_rss_feed = lambda url, proxy="": {"title": "示例源", "entries": [feed_entry(1)]}
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://a.com/feed.xml", kind="rss")
    mgr._busy.add(str(sub["id"]))
    ck("H1 上一轮没扫完时这次直接跳过", mgr.scan_one(sub, auto_download=True) == 0 and q.batches == [])
    mgr._busy.discard(str(sub["id"]))
    ck("H2 锁释放后能正常扫", mgr.scan_one(sub, auto_download=False) == 0)
finally:
    S.parse_rss_feed = orig_parse

print("=== I. 每条订阅独立目录 ===")
r = S._norm_sub_rules({"download_dir": r"D:\Media\RSS 源"})
ck("I1 目录能落规则", r["download_dir"] == r"D:\Media\RSS 源", r)
ck("I2 摘要只显示末段，不铺绝对路径", "RSS 源" in S._sub_rules_text(r) and "D:" not in S._sub_rules_text(r),
   S._sub_rules_text(r))
ck("I3 空目录不落盘", "download_dir" not in S._norm_sub_rules({"download_dir": "   "}))
mgr, q = new_mgr()
opts = mgr._rule_opts(r)
ck("I4 入队选项带上该订阅的目录", opts.get("download_dir") == r"D:\Media\RSS 源", opts)
opts2 = mgr._rule_opts(S._norm_sub_rules({}))
ck("I5 没设目录时不塞空值（仍走全局）", "download_dir" not in opts2, list(opts2))

print("=== J. 旧 RSS 文件搬家 ===")
tmp = Path(tempfile.mkdtemp(prefix="mdsubrss_"))
old_file = tmp / "rss_feeds.json"
old_file.write_text(__import__("json").dumps([
    {"id": "a1", "url": "https://a.com/feed.xml", "title": "老源", "auto_download": True,
     "seen_ids": ["tag:1", "tag:2"], "last_scan": "2025-09-01 10:00:00"},
    {"id": "b2", "url": "https://b.com/feed", "title": "另一个", "auto_download": False,
     "seen_ids": [], "last_scan": ""},
], ensure_ascii=False), encoding="utf-8")
orig_rss_file, orig_mgr_global, orig_log = S.RSS_FILE, S.sub_mgr, S.log_mgr
S.RSS_FILE = old_file
S.log_mgr = type("SilentLog", (), {"log": staticmethod(lambda m, lv="info": LOGS.append(m))})()
S.sub_mgr, _q = new_mgr()
try:
    moved = S.migrate_rss_to_subs()
    by_url = {s["url"]: s for s in S.sub_mgr.list()}
    subs = list(S.sub_mgr.list())
    ck("J1 两个源都并进订阅", moved == 2 and len(subs) == 2, moved)
    ck("J2 搬过来标成 rss 分支", all(s["kind"] == "rss" for s in subs))
    a = by_url.get("https://a.com/feed.xml") or {}
    b = by_url.get("https://b.com/feed") or {}
    ck("J3 已见记录当游标带过去", a.get("last_ids") == ["tag:1", "tag:2"], a.get("last_ids"))
    ck("J4 原来的自动下载开关保留", a.get("auto_download") is True and b.get("auto_download") is False)
    ck("J5 上次扫描时间不丢", a.get("last_check") == "2025-09-01 10:00:00", a.get("last_check"))
    ck("J6 旧文件改名保留而不是删掉", (tmp / "rss_feeds.json.migrated").exists() and not old_file.exists())
    ck("J7 再搬一次是空操作（重启幂等）", S.migrate_rss_to_subs() == 0 and len(S.sub_mgr.list()) == 2)
finally:
    S.RSS_FILE, S.sub_mgr, S.log_mgr = orig_rss_file, orig_mgr_global, orig_log

print()
print("FAILURES:", FAILED or "none")
sys.exit(1 if FAILED else 0)
