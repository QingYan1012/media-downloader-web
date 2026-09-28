r"""Telegram 频道当订阅源 + 订阅日期窗的离线自检。

全程不联网、不碰用户的 subscriptions.json：假 engine（被调用就直接炸，证明真的走了
Telegram 分支）、假 queue、save() 空转，爬虫和会话对象都打桩。

跑法：`python tests/subtg_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402
import telegram_channel as TC  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# ---------------------------------------------------------------- 桩
class BoomEngine:
    def get_info(self, url, cfg):
        raise AssertionError(f"Telegram 订阅不该去问 yt-dlp engine: {url}")


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


class FakeSession:
    def __init__(self, rows=None, diag=None, status=None):
        self.rows = rows or []
        self.diag = diag or {"title": "内部频道", "stopped": "已到数量上限 30 条"}
        self._status = status or {"logged_in": True, "configured": True}
        self.calls: list[dict] = []

    def status(self):
        return self._status

    def list_media(self, entity, **kw):
        self.calls.append({"entity": entity, **kw})
        return list(self.rows), dict(self.diag)


def new_mgr(**cfgkw):
    q = FakeQueue()
    mgr = MemSubs(BoomEngine(), FakeCfg(**cfgkw), q, FakeTG(),
                  lambda m, lv="info": LOGS.append(m))
    return mgr, q


def anon_row(pid, ch="europa_press", typ="video", downloadable=True, date="2026-09-10"):
    return {"id": f"{ch}-{pid}", "channel": ch, "post_id": str(pid),
            "url": f"https://t.me/{ch}/{pid}", "date": date, "datetime": f"{date}T08:00:00",
            "type": typ, "title": f"帖子 {pid}", "duration_sec": 120, "duration": "2:00",
            "filename": "", "downloadable": downloadable, "note": ""}


def mt_row(mid, idx=0, peer="-1001234567890", typ="document", name="book.epub",
           date="2026-09-11"):
    return {"id": f"{peer}-{mid}-{idx}", "peer": peer, "post_id": mid, "media_index": idx,
            "url": f"https://t.me/c/1234567890/{mid}", "mt_url": f"tgmt://{peer}/{mid}?idx={idx}",
            "date": date, "datetime": f"{date}T09:00:00", "type": typ, "title": name,
            "duration_sec": 0, "filename": name, "downloadable": True,
            "protected": False, "note": ""}


print("=== A. 订阅链是不是 Telegram 频道 ===")
ck("A1 公开频道链 → 匿名", S._tg_sub_ref("https://t.me/s/europa_press") == ("anon", "europa_press"))
ck("A2 帖子链也能认出频道", S._tg_sub_ref("https://t.me/europa_press/18446") == ("anon", "europa_press"))
ck("A3 私有 c/ 链 → 会话", S._tg_sub_ref("https://t.me/c/1234567890/77") == ("mt", "-1001234567890"))
ck("A4 裸 -100 id → 会话", S._tg_sub_ref("-1001234567890") == ("mt", "-1001234567890"))
ck("A5 @名字 → 匿名", S._tg_sub_ref("@europa_press") == ("anon", "europa_press"))
ck("A6 mode=mt 时公开名也走会话", S._tg_sub_ref("https://t.me/europa_press", "mt") == ("mt", "europa_press"))
ck("A7 YouTube 普通链不是 Telegram", S._tg_sub_ref("https://www.youtube.com/@ffmpeg") == ("", ""))
ck("A8 YouTube 频道 handle 不误判成 Telegram 频道",
   S._tg_sub_ref("https://youtube.com/@some_channel") == ("", ""))
ck("A9 B 站空间不误判", S._tg_sub_ref("https://space.bilibili.com/123456") == ("", ""))
ck("A10 空输入不炸", S._tg_sub_ref("") == ("", "") and S._tg_sub_ref(None) == ("", ""))

print("=== B. 条目形状换算 ===")
rows = [anon_row(1), anon_row(2, typ="document", downloadable=False),
        anon_row(3, typ="photo", downloadable=False)]
out = S._tg_sub_entries(rows, False)
ck("B1 匿名只留下 yt-dlp 真能下的", [e["id"] for e in out] == ["tgs:europa_press-1"], [e["id"] for e in out])
ck("B2 匿名用 t.me 帖子链", out[0]["url"] == "https://t.me/europa_press/1")
ck("B3 会话用 tgmt:// 且带 idx", S._tg_sub_entries([mt_row(9, 2)], True)[0]["url"] == "tgmt://-1001234567890/9?idx=2")
ck("B4 会话保留可下但受限的条目", len(S._tg_sub_entries([mt_row(9)], True)) == 1)
ck("B5 匿名与会话的 id 不撞（换模式不会被当成同一条）",
   S._tg_sub_entries([anon_row(1)], False)[0]["id"] != S._tg_sub_entries([anon_row(1)], True)[0]["id"])
kinds = {t: S._tg_sub_entries([mt_row(1, typ=t)], True)[0]["kind"]
         for t in ("video", "audio", "voice", "document", "photo")}
ck("B6 类型映射到订阅认识的桶",
   kinds == {"video": "video", "audio": "audio", "voice": "audio",
             "document": "file", "photo": "photo"}, kinds)
ck("B7 缺 id 或缺链接的行直接丢",
   S._tg_sub_entries([{"id": "", "url": "x"}, {"id": "a"}], False) == [])

print("=== C. 日期窗清洗与逐条判定 ===")
ck("C1 斜杠点号都收成 -", S._norm_sub_rules({"since": "2026/09/01", "until": "2026.09.20"})
   == {"since": "2026-09-01", "until": "2026-09-20", "max_per_scan": 20},
   S._norm_sub_rules({"since": "2026/09/01", "until": "2026.09.20"}))
ck("C2 填反了对调而不是丢弃", S._norm_sub_rules({"since": "2026-09-20", "until": "2026-09-01"})
   == {"since": "2026-09-01", "until": "2026-09-20", "max_per_scan": 20})
ck("C3 垃圾日期不落盘", "since" not in S._norm_sub_rules({"since": "最近"})
   and "until" not in S._norm_sub_rules({"until": "9月"}))
ck("C4 单边窗口能存", S._norm_sub_rules({"since": "2026-09-01"})["since"] == "2026-09-01")
rwin = S._norm_sub_rules({"since": "2026-09-01", "until": "2026-09-10"})
e_in = {"id": "a", "url": "u", "title": "t", "date": "2026-09-05"}
e_old = {"id": "b", "url": "u", "title": "t", "date": "2026-08-31"}
e_new = {"id": "c", "url": "u", "title": "t", "date": "2026-09-11"}
e_none = {"id": "d", "url": "u", "title": "t"}
ck("C5 窗口内放行", S._sub_rule_match(e_in, rwin)[0])
ck("C6 早于窗口挡掉并说清", S._sub_rule_match(e_old, rwin) == (False, "2026-08-31 早于日期窗"))
ck("C7 晚于窗口挡掉", S._sub_rule_match(e_new, rwin) == (False, "2026-09-11 晚于日期窗"))
ck("C8 条目没日期时不瞎挡", S._sub_rule_match(e_none, rwin)[0])
ck("C9 yt-dlp 的 upload_date 也认", S._sub_date({"upload_date": "20260901"}) == "2026-09-01")
ck("C10 带时刻的日期取到日", S._sub_date({"datetime": "2026-09-01T12:00:00"}) == "2026-09-01")
ck("C11 规则摘要里看得见窗口", "只下 2026-09-01~2026-09-10" in S._sub_rules_text(rwin), S._sub_rules_text(rwin))
ck("C12 显式 kind 优先于按 url 猜", S._sub_entry_kind({"kind": "file", "url": "tgmt://x/1"}) == "file")
ck("C13 不认识的 kind 回落到猜", S._sub_entry_kind({"kind": "bogus", "url": "https://x/shorts/1"}) == "video"
   or S._sub_entry_kind({"kind": "bogus", "url": "https://x/shorts/1"}) == "short")

print("=== D. 匿名订阅：首次只记 ID，二次只入队新增 ===")
pages = [[anon_row(3), anon_row(2)], [anon_row(1)]]
calls: list[dict] = []
orig_hist, orig_decide = TC.list_channel_history, S.proxy_decision
TC.list_channel_history = lambda ch, **kw: (calls.append({"ch": ch, **kw}) or
                                            (pages.pop(0) if pages else [], {"stopped": "已到数量上限", "errors": {}}))
S.proxy_decision = lambda *a, **k: ("proxy", "http://127.0.0.1:7897")
try:
    mgr, q = new_mgr(sub_first_download_n=0, sub_auto_download=True)
    sub = mgr.add("https://t.me/s/europa_press")
    ck("D1 Telegram 频道能当订阅源加进来", bool(sub.get("id")) and sub["mode"] == "")
    n1 = mgr.scan_one(sub, auto_download=False)
    ck("D2 首次扫描只记 ID 不下", n1 == 0 and len(sub["last_ids"]) == 2 and q.batches == [], sub["last_ids"])
    ck("D3 标题取到频道名", sub["title"] == "europa_press", sub["title"])
    ck("D4 代理按平台决策后真的传下去", calls[-1]["proxy"] == "http://127.0.0.1:7897", calls[-1].get("proxy"))
    ck("D5 没设类型时不只看视频（全类型都翻）", set(calls[-1]["types"]) == set(TC.ALL_TYPES), calls[-1]["types"])
    pages.insert(0, [anon_row(4), anon_row(3), anon_row(2)])
    n2 = mgr.scan_one(sub, auto_download=True)
    ck("D6 新增一条就入队一条", n2 == 1 and q.all_urls() == ["https://t.me/europa_press/4"], q.all_urls())
    ck("D7 老条目不再重复推", all("europa_press/3" not in u and "europa_press/2" not in u for u in q.all_urls()))
    ck("D8 报错清空了", sub.get("last_error") == "")
finally:
    TC.list_channel_history, S.proxy_decision = orig_hist, orig_decide

print("=== E. 会话订阅：入队的是 tgmt:// ===")
sess = FakeSession(rows=[mt_row(9, 1), mt_row(8)])
orig_sess = S.tg_session
S.tg_session = sess
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://t.me/c/1234567890", mode="mt")
    ck("E0 首次扫描只记 ID，不把整频道历史推一遍",
       mgr.scan_one(sub, auto_download=False) == 0 and q.batches == [], sub["last_ids"])
    sess.rows = [mt_row(10), mt_row(9, 1), mt_row(8)]
    n = mgr.scan_one(sub, auto_download=True)
    ck("E1 会话源新增入队的是 tgmt:// 且带 media 序号",
       q.all_urls() == ["tgmt://-1001234567890/10?idx=0"], q.all_urls())
    ck("E1b 老帖子（含多媒体的那条）不重复推", n == 1, n)
    ck("E2 翻历史条数按单次上限折算", sess.calls[-1]["limit"] == 60, sess.calls[-1])
    ck("E3 频道标题来自会话诊断", sub["title"] == "内部频道", sub["title"])
    ck("E4 日期窗空时不传垃圾", not sess.calls[-1]["since"] and not sess.calls[-1]["until"])
finally:
    S.tg_session = orig_sess

print("=== F. 读不到要说清，且不能当成「没有新增」 ===")
S.tg_session = FakeSession(rows=[], diag={"title": "", "stopped": "私有频道：这个账号没加入它（或被踢了），读不到历史",
                                          "errors": {"读不到": "ChannelPrivateError"}})
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://t.me/c/999000111", mode="mt")
    n = mgr.scan_one(sub, auto_download=True)
    ck("F1 会话读不到 → 返回 0 且记 last_error", n == 0 and "私有频道" in sub["last_error"], sub["last_error"])
    ck("F3 失败不写 last_ids（下次还会重试）", sub["last_ids"] == [], sub["last_ids"])
    ck("F4 失败不入队", q.batches == [])
finally:
    S.tg_session = orig_sess

S.tg_session = FakeSession(rows=[], diag={"title": "", "stopped": "已翻到最早一条", "errors": {}})
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://t.me/c/555", mode="mt")
    n = mgr.scan_one(sub, auto_download=True)
    ck("F5 频道真的没可读东西时不算故障（不报错、不刷屏）",
       n == 0 and sub.get("last_error") == "", sub.get("last_error"))
finally:
    S.tg_session = orig_sess

S.tg_session = FakeSession(status={"logged_in": False, "configured": True})
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://t.me/c/555", mode="mt")
    mgr.scan_one(sub, auto_download=True)
    ck("F6 没登录 → 提示去登录，而不是静默 0 条", "登录" in sub["last_error"], sub["last_error"])
    S.tg_session = FakeSession(status={"logged_in": False, "configured": False})
    sub2 = mgr.add("https://t.me/c/556", mode="mt")
    mgr.scan_one(sub2, auto_download=True)
    ck("F7 连凭据都没有时把缺的也说清", "api_id" in sub2["last_error"], sub2["last_error"])
finally:
    S.tg_session = orig_sess

print("=== G. 规则的日期窗透传给爬虫 ===")
calls.clear()
orig_hist = TC.list_channel_history
TC.list_channel_history = lambda ch, **kw: (calls.append(kw) or
                                            ([], {"stopped": "已翻到 2026-09-01 之前，按日期收工", "errors": {}}))
S.proxy_decision = lambda *a, **k: ("direct", "")
try:
    mgr, q = new_mgr()
    sub = mgr.add("https://t.me/s/europa_press")
    sub["rules"] = {"since": "2026-09-01", "until": "2026-09-10", "types": ["audio"], "max_per_scan": 5}
    n = mgr.scan_one(sub, auto_download=True)
    ck("G1 窗口原样传给爬虫", calls[-1]["since"] == "2026-09-01" and calls[-1]["until"] == "2026-09-10", calls[-1])
    ck("G2 规则类型翻成 telegram 的桶（音频含语音）",
       set(calls[-1]["types"]) == {"audio", "voice"}, calls[-1]["types"])
    ck("G3 窗口内 0 条不算故障", n == 0 and sub.get("last_error") == "", sub.get("last_error"))
    ck("G4 强制直连用哨兵而不是空串", calls[-1]["proxy"] == TC.PROXY_DIRECT, calls[-1]["proxy"])
    sub["rules"] = {"types": ["file"], "max_per_scan": 5}
    mgr.scan_one(sub, auto_download=True)
    ck("G5 只要文件 → 翻成 document", set(calls[-1]["types"]) == {"document"}, calls[-1]["types"])
    sub["rules"] = {"types": ["video", "short"], "max_per_scan": 5}
    mgr.scan_one(sub, auto_download=True)
    ck("G6 长视频+短视频都归到 video，不重复", set(calls[-1]["types"]) == {"video"}, calls[-1]["types"])
finally:
    TC.list_channel_history, S.proxy_decision = orig_hist, orig_decide

print("=== H. 订阅项的 mode 口径 ===")
ck("H1 普通 http 链不受影响（mode 存在且为空）", mgr.add("https://www.youtube.com/@x")["mode"] == "")
try:
    mgr.add("not a url at all")
    ck("H2 垃圾输入仍然拒绝", False)
except ValueError as e:
    ck("H2 垃圾输入仍然拒绝并说清能收什么", "http" in str(e) and "Telegram" in str(e), str(e)[:60])
mgr2, _q = new_mgr()
s2 = mgr2.add("https://t.me/s/x")
ck("H3 同链同 mode 不重复加", mgr2.add("https://t.me/s/x")["id"] == s2["id"])
mgr2.set_rules(s2["id"], {}, "mt")
ck("H4 规则接口能改读取方式", s2["mode"] == "mt", s2["mode"])
try:
    mgr2.set_rules(s2["id"], {}, "weibo")
    ck("H5 非法 mode 拒绝", False)
except ValueError as e:
    ck("H5 非法 mode 拒绝", "会话" in str(e), str(e)[:40])
mgr2.set_rules(s2["id"], {}, "")
ck("H6 传空串能改回自动", s2["mode"] == "")

print(f"\nFAILED: {FAILED if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
