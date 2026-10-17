r"""通知 outbox 自检（#27 落库 + 递增间隔重试，重启不丢）。

全内存跑：把 outbox 文件指到临时目录、把三个通道的发送函数换成记账假函数，
不联网、不发真通知、不写 config.json。断言的是「这条事件该发给谁、谁没送到、
下次什么时候再试、重启后还剩什么」。

跑法：`python tests/outbox_test.py`
"""
from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(__file__).resolve().parent / "_outbox_tmp_state"
FAILED: list[str] = []
TOTAL = 0
CFG_KEYS = ("telegram_enabled", "telegram_bot_token", "telegram_chat_id",
            "telegram_notify_done", "telegram_notify_fail", "telegram_notify_sub",
            "serverchan_sendkey", "wecom_enabled",
            "wecom_notify_done", "wecom_notify_fail", "wecom_notify_sub")
saved_cfg = {k: S.cfg.data.get(k) for k in CFG_KEYS}
saved_file = S.NOTIFY_OUTBOX_FILE
saved_state = json.loads(json.dumps(S._outbox_state))
saved_thread = S._notify_outbox_thread
LOGS: list[tuple[str, str]] = []
orig_log = S.log_mgr.log
orig_send_channel = S._notify_send_channel
orig_tg_send = S.tg_notifier.send_detail
orig_tg_sc = S.tg_notifier.send_serverchan_detail
orig_wecom = S.wecom_send_detail
orig_requests = S.requests


def ck(name: str, cond, extra: str = ""):
    global TOTAL
    TOTAL += 1
    if not bool(cond):
        FAILED.append(name)
        print(f"FAIL {name} {extra}")
    else:
        print(f"PASS {name}")


@contextlib.contextmanager
def cfg(**kw):
    """只在内存里改通知相关的设置，出作用域原样还回去。"""
    saved = {k: S.cfg.data.get(k) for k in kw}
    S.cfg.data.update(kw)
    try:
        yield
    finally:
        for k, v in saved.items():
            S.cfg.data[k] = v


@contextlib.contextmanager
def quiet_log():
    S.log_mgr.log = lambda m, level="info": LOGS.append((level, m))
    try:
        yield
    finally:
        S.log_mgr.log = orig_log


def reset(*, tg=False, token="", chat="", sc="", wecom=False):
    """把 outbox 表与文件清干净，设置回到「什么都没配」。"""
    S._outbox_state["seq"] = 0
    S._outbox_state["records"] = []
    S.cfg.data.update({
        "telegram_enabled": tg, "telegram_bot_token": token, "telegram_chat_id": chat,
        "telegram_notify_done": True, "telegram_notify_fail": True, "telegram_notify_sub": True,
        "serverchan_sendkey": sc, "wecom_enabled": wecom,
        "wecom_notify_done": True, "wecom_notify_fail": True, "wecom_notify_sub": False,
    })


TGON = dict(tg=True, token="123:ABC", chat="999")


class Sender:
    """假发送：按通道记流水，结果可由脚本决定（值 = 恒为该结果，列表 = 这个通道的第 N 次尝试）。"""

    def __init__(self, results=None):
        self.calls: list[tuple[str, str, str]] = []
        self.results = results or {}

    def __call__(self, ch, title, text):
        self.calls.append((ch, title, text))
        r = self.results.get(ch, True)
        if isinstance(r, list):
            k = sum(1 for c, _, _ in self.calls if c == ch)
            r = r[min(k - 1, len(r) - 1)]
        if r is True:
            return True, ""
        if r is False:
            return False, f"{ch} 假装失败"
        return (False, str(r)) if isinstance(r, str) else r

    def channels(self):
        return [c for c, _, _ in self.calls]

    @property
    def n(self):
        return len(self.calls)


@contextlib.contextmanager
def sender(results=None):
    fake = Sender(results)
    S._notify_send_channel = fake
    try:
        yield fake
    finally:
        S._notify_send_channel = orig_send_channel


@contextlib.contextmanager
def tmpdir():
    TMP.mkdir(parents=True, exist_ok=True)
    for p in TMP.glob("*"):
        p.unlink()
    S.NOTIFY_OUTBOX_FILE = TMP / "notify_outbox.json"
    try:
        yield S.NOTIFY_OUTBOX_FILE
    finally:
        S.NOTIFY_OUTBOX_FILE = saved_file
        with contextlib.suppress(Exception):
            for p in TMP.glob("*"):
                p.unlink()
        with contextlib.suppress(Exception):
            TMP.rmdir()


def recs():
    return S._outbox_state["records"]


def one():
    return recs()[-1]


# ============ A. 这个事件该发给谁（沿用各通道自己的开关，不新增设置项） ============
print("== A 通道判定 ==")
with quiet_log(), tmpdir():
    reset()
    ck("A1 什么都没配 → 没有通道", S._notify_targets("done") == [])
    ck("A2 什么都没配 → 事件不写盘", S._notify_enqueue("done", "下载完成", "x") is False and recs() == [])
    reset(**TGON)
    ck("A3 Telegram 开了就算一个通道", S._notify_targets("done") == ["telegram"])
    ck("A4 完成事件默认开", "telegram" in S._notify_targets("done"))
    S.cfg.data["telegram_notify_done"] = False
    ck("A5 勾选关掉后完成事件不再发 Telegram", S._notify_targets("done") == [])
    ck("A6 但失败事件仍按自己的开关走", S._notify_targets("fail") == ["telegram"])
    S.cfg.data.update({"telegram_notify_done": True, "telegram_notify_sub": False})
    ck("A7 订阅关掉、直播那类不受订阅开关影响",
       S._notify_targets("sub") == [] and S._notify_targets("live") == ["telegram"])
    reset(sc="SCT999")
    ck("A8 只填 Server酱：只有完成事件走它",
       S._notify_targets("done") == ["serverchan"] and S._notify_targets("fail") == [])
    reset(wecom=True)
    ck("A9 企业微信：完成/失败按各自开关", S._notify_targets("done") == ["wecom"])
    ck("A10 企业微信的订阅默认是关的（DEFAULTS 里就是 False）", S._notify_targets("sub") == [])
    with cfg(wecom_notify_sub=True):
        ck("A11 勾上订阅开关后才有它", S._notify_targets("sub") == ["wecom"])
    ck("A12 直播开播不发给企业微信与 Server酱", S._notify_targets("live") == [])
    reset(**TGON, sc="SCT999", wecom=True)
    ck("A13 三个通道同时开着时按 telegram→serverchan→wecom 排",
       S._notify_targets("done") == ["telegram", "serverchan", "wecom"])
    reset(tg=True)  # 开了但 Token 空 = 没配好，和过去一样不发
    ck("A14 开关开了但 Token/Chat 为空 → 不算通道", S._notify_targets("done") == [])

# ============ B. 文案与改造前逐字一致 ============
print("== B 文案 ==")
with quiet_log(), tmpdir(), sender():
    reset(**TGON)
    S.tg_notifier.notify_done("某视频", "https://a/b", "D:/Downloads/某视频.mp4")
    ck("B1 完成文案没变", one()["text"] == "✅ 下载完成\n某视频\nD:/Downloads/某视频.mp4", one()["text"])
    ck("B2 完成标题给 Server酱用", one()["title"] == "下载完成")
    S.tg_notifier.notify_done("", "https://only/url", "")
    ck("B3 没标题时回落到 URL（同过去）", one()["text"] == "✅ 下载完成\nhttps://only/url\nhttps://only/url")
    S.tg_notifier.notify_fail("坏掉", "https://a/b", "HTTP 403")
    ck("B4 失败文案没变", one()["text"] == "❌ 下载失败\n坏掉\nHTTP 403", one()["text"])
    S.tg_notifier.notify_fail("坏掉", "https://a/b", "")   # 过去这里 err[:200] 会炸在 None 上
    ck("B5 错误为空也不炸", one()["text"] == "❌ 下载失败\n坏掉\n")
    S.tg_notifier.notify_fail("坏掉", "https://a/b", "E" * 500)
    ck("B6 错误仍然只截 200 字", len(one()["text"].split("\n")[-1]) == 200)
    S.tg_notifier.notify_sub("某个订阅", 3, ["一", "二", "三", "四", "五", "六"])
    ck("B7 订阅文案没变（样本仍是最多 5 条）",
       one()["text"] == "📢 订阅更新: 某个订阅\n新增 3 条\n· 一\n· 二\n· 三\n· 四\n· 五", one()["text"])
    S.tg_notifier.notify_sub("某个订阅", 1, None)
    ck("B8 没有样本时不会因为 None 炸", "新增 1 条" in one()["text"])
    ck("B9 通道记账在记录里", one()["channels"] == ["telegram"])

# ============ C. 进队 ============
print("== C 进队 ==")
with quiet_log(), tmpdir(), sender():
    reset(**TGON, sc="SCT999", wecom=True)
    ck("C1 进队返回 True", S._notify_enqueue("done", "下载完成", "abc") is True)
    r = one()
    ck("C2 记录带 id/kind/状态", r["id"] == 1 and r["kind"] == "done" and r["status"] == "pending")
    ck("C3 通道来自判定", r["channels"] == ["telegram", "serverchan", "wecom"])
    ck("C4 第一次不等间隔：next_try 就是当下", r["next_try"] <= time.time() + 0.5)
    ck("C5 还没试过", r["attempts"] == 0 and r["last_error"] == "")
    S._notify_enqueue("done", "下载完成", "again")
    ck("C6 第二条 id 递增", one()["id"] == 2 and len(recs()) == 2)
    ck("C7 进队把后台线程踢一下", S._notify_outbox_kick.is_set())
    S._notify_outbox_kick.clear()
    S.tg_notifier.notify_fail("坏掉", "u", "e")
    ck("C8 三个通道都关着的订阅事件也会落盘（有通道就落）", len(recs()) == 3)
    for i in range(80):
        S._notify_enqueue("done", "下载完成", f"t{i}")
    ck("C9 表被裁到上限", len(recs()) <= S._OUTBOX_KEEP)
    ck("C10 裁的是已经了结/最老的，最新的还在", one()["text"] == "t79")

# ============ D. 投递记账（补发不重发） ============
print("== D 投递记账 ==")
with quiet_log(), tmpdir(), sender({"telegram": True, "serverchan": False, "wecom": False}) as f:
    reset(**TGON, sc="SCT999", wecom=True)
    S._notify_enqueue("done", "下载完成", "hello")
    n = S._outbox_tick()
    ck("D1 一次 tick 处理一条到期记录", n == 1)
    r = one()
    ck("D2 送成功的通道被划掉", r["channels"] == ["serverchan", "wecom"], r["channels"])
    ck("D3 还没送完的仍是待补发", r["status"] == "pending")
    ck("D4 失败原因写进记录", "serverchan" in r["last_error"] and "wecom" in r["last_error"])
    ck("D5 每个通道各试一次，不重复", f.channels() == ["telegram", "serverchan", "wecom"])
    S._notify_send_channel = orig_send_channel
    with sender({"serverchan": True, "wecom": True}) as f2:
        r["next_try"] = time.time() - 1
        S._outbox_tick()
    ck("D6 补发只碰还欠着的那两个", f2.channels() == ["serverchan", "wecom"], f2.channels())
    ck("D7 补发成功就变成已送出", one()["status"] == "sent" and one()["channels"] == [])
    ck("D8 已送出的记录把错误清空", one()["last_error"] == "")
    ck("D9 补发成功要在日志里说一声",
       any("通知补发成功" in m and "第 2 次" in m for _, m in LOGS), [m for _, m in LOGS][-3:])
    ck("D10 Telegram 那条不会被再发一遍", f2.n == 2)

with quiet_log(), tmpdir(), sender({"telegram": False}) as f:
    reset(**TGON)
    S._notify_enqueue("fail", "下载失败", "boom")
    S._outbox_tick()
    ck("D11 一次成功都没有时保持待补发", one()["status"] == "pending" and one()["attempts"] == 1)
    ck("D12 失败原因留着给界面看", "telegram 假装失败" in one()["last_error"], one()["last_error"])
    S.cfg.data["telegram_enabled"] = False     # 用户在这期间把通道关了
    recs()[0]["next_try"] = time.time() - 1
    S._outbox_tick()
    ck("D13 通道关了就整条作废，不再无限重试",
       one()["status"] == "dropped" and "都关了" in one()["last_error"], one())
    ck("D14 关掉之后不会再碰网络", f.n == 1, f.n)

# ============ E. 重试节奏 ============
print("== E 递增间隔 ==")
ck("E1 间隔表就是 30s→2min→10min→30min→1h", S.NOTIFY_RETRY_DELAYS == (30, 120, 600, 1800, 3600))
with quiet_log(), tmpdir(), sender({"telegram": False}):
    reset(**TGON)
    S._notify_enqueue("done", "下载完成", "x")
    seen = []
    for _ in range(8):
        S._outbox_tick()
        r = one()
        if r["status"] != "pending":
            seen.append((r["attempts"], 0))
            break
        seen.append((r["attempts"], round(r["next_try"] - time.time())))
        r["next_try"] = time.time() - 1     # 把时钟快进，免得自检真等一小时
    ck("E2 第 1 次失败后等 30 秒", seen[0] == (1, 30), seen)
    ck("E3 第 2 次失败后等 120 秒", seen[1] == (2, 120), seen)
    ck("E4 第 3 次失败后等 600 秒", seen[2] == (3, 600), seen)
    ck("E5 第 4 次失败后等 1800 秒", seen[3] == (4, 1800), seen)
    ck("E6 第 5 次失败后等 3600 秒", seen[4] == (5, 3600), seen)
    ck("E7 一共试 6 次（首发 + 5 次补发）后停", seen[5] == (6, 0), seen)
    ck("E8 用尽后状态是已丢弃", one()["status"] == "dropped")
    ck("E9 丢弃要在日志里点名是哪条消息",
       any("仍没送出去，丢弃" in m and "下载完成" in m for _, m in LOGS), [m for _, m in LOGS][-2:])
    ck("E10 已丢弃的不会被下一轮再碰", S._outbox_tick() == 0 and one()["attempts"] == 6)
    ck("E11 间隔表最后一档之后不会倒回去（越试越疏）",
       list(S.NOTIFY_RETRY_DELAYS) == sorted(S.NOTIFY_RETRY_DELAYS))

with quiet_log(), tmpdir(), sender({"telegram": [False, False, True]}):
    reset(**TGON)
    S._notify_enqueue("done", "下载完成", "flaky")
    for _ in range(3):
        one()["next_try"] = time.time() - 1
        S._outbox_tick()
    ck("E12 网络抖两下再通：第 3 次就送出", one()["status"] == "sent" and one()["attempts"] == 3)

# ============ F. 落盘与读回 ============
print("== F 落盘 ==")
with quiet_log(), tmpdir() as path, sender():
    reset(**TGON, sc="SCT999")
    S._notify_enqueue("done", "下载完成", "written")
    ck("F1 进队就写盘（不是等发成功才写）", path.exists())
    disk = json.loads(path.read_text(encoding="utf-8"))
    ck("F2 盘上是 seq + records", disk["seq"] == 1 and len(disk["records"]) == 1)
    ck("F3 盘上的记录带通道与次数",
       disk["records"][0]["channels"] == ["telegram", "serverchan"] and disk["records"][0]["attempts"] == 0)
    ck("F4 中文没被转义成 \\uXXXX", "下载完成" in path.read_text(encoding="utf-8"))
    ck("F5 没有留临时文件（写盘是替换式的）", list(TMP.glob("*.tmp")) == [])
    ck("F6 表里改了状态也会落盘",
       (lambda: (S._outbox_state["records"][0].update(status="sent", channels=[]),
                 S._outbox_save(),
                 json.loads(path.read_text(encoding="utf-8"))["records"][0]["status"] == "sent"))())
with tmpdir() as path:
    path.write_text("{ 这不是 JSON", encoding="utf-8")
    with quiet_log():
        ck("F7 文件坏了也能起来：读回 0 条并说一声",
           S._outbox_load() == 0 and any("读取失败" in m for _, m in LOGS))
with tmpdir() as path:
    path.write_text(json.dumps({"seq": 9, "records": [
        {"id": 8, "kind": "done", "title": "下载完成", "text": "old", "status": "pending",
         "channels": ["telegram"], "attempts": 2, "next_try": time.time(),
         "created_at": time.time() - 30 * 86400},
        {"id": 9, "kind": "fail", "title": "下载失败", "text": "weird", "status": "pending",
         "channels": ["pigeon", "telegram"], "attempts": 1, "next_try": time.time(),
         "created_at": time.time()},
        {"id": 10, "kind": "done", "title": "没有正文", "text": "", "status": "pending",
         "channels": ["telegram"], "attempts": 0, "next_try": time.time(), "created_at": time.time()},
        {"id": "坏掉的一条", "kind": "done"},
    ]}), encoding="utf-8")
    with quiet_log():
        got = S._outbox_load()
    ck("F8 一个月前的旧事件不再补发", all(r["id"] != 8 for r in recs()))
    ck("F9 不认识的通道名被丢掉（pigeon 不发给任何东西）",
       one()["channels"] == ["telegram"] if recs() else False, recs())
    ck("F10 没正文/缺字段的条目直接忽略", all(isinstance(r.get("id"), int) and r.get("text") for r in recs()))
    ck("F11 读回后 seq 接着上游走的号", S._outbox_state["seq"] == 9)
    ck("F12 读回的待发条数报给启动日志", got == 1, got)
with tmpdir() as path:
    path.write_text(json.dumps({"seq": 1, "records": [
        {"id": 1, "kind": "done", "title": "下载完成", "text": "no channel", "status": "pending",
         "channels": [], "attempts": 0, "next_try": time.time(), "created_at": time.time()}]}),
        encoding="utf-8")
    with quiet_log():
        S._outbox_load()
    ck("F13 通道为空又没到期的：读回时就标成丢弃，不占着待发", recs()[0]["status"] == "dropped")

# ============ G. 重启不丢 ============
print("== G 重启不丢 ==")
with quiet_log(), tmpdir(), sender({"telegram": False, "serverchan": False}):
    reset(**TGON, sc="SCT999")
    S._notify_enqueue("done", "下载完成", "keepme")
    S._outbox_tick()                       # 试一次，失败，排到 30 秒后
    ck("G1 失败后备发计划已落盘", one()["attempts"] == 1 and one()["status"] == "pending")
    # 装作进程重启：内存表清空，只留盘上那份
    S._outbox_state["seq"] = 0
    S._outbox_state["records"] = []
    n = S._outbox_load()
    ck("G2 重启后读回 1 条待补发", n == 1 and len(recs()) == 1)
    ck("G3 欠谁的（Server酱 + Telegram）还在", set(one()["channels"]) == {"telegram", "serverchan"},
       one()["channels"])
    ck("G4 已经试过的次数不会被清零（不会又从头猛发）", one()["attempts"] == 1)
    ck("G5 补发文案还是原来那条", one()["text"] == "keepme")
    with sender({"telegram": True, "serverchan": True}):
        one()["next_try"] = time.time() - 1
        S._outbox_tick()
    ck("G6 重启后接着补，这次真的送出去了", one()["status"] == "sent" and one()["channels"] == [])

# ============ H. tick / 后台线程 ============
print("== H tick ==")
with quiet_log(), tmpdir(), sender() as f:
    reset(**TGON)
    S._notify_enqueue("done", "下载完成", "future")
    one()["next_try"] = time.time() + 600
    ck("H1 没到期的不碰", S._outbox_tick() == 0)
    ck("H2 没到期时发送函数一次也没被调", f.n == 0)
    S._outbox_state["records"] = []
    ck("H3 空表 tick 直接返回 0", S._outbox_tick() == 0)
    S._notify_enqueue("done", "下载完成", "boom")

    def bad(ch, title, text):
        raise RuntimeError("发送函数炸了")
    S._notify_send_channel = bad
    with quiet_log():
        got = S._outbox_tick()
    ck("H4 发送函数炸了也不会把 tick 整个带崩", got == 1)
    S._notify_send_channel = orig_send_channel
    ck("H5 炸掉的那条记着原因并排到 30 秒后",
       "发送函数炸了" in recs()[0]["last_error"] and 0 <= recs()[0]["next_try"] - time.time() <= 31,
       recs()[0])
    ck("H6 tick 会把结果落盘", S.NOTIFY_OUTBOX_FILE.exists())
    # 后台线程：新事件被踢一脚就该立刻送出去，不用等下一个 tick
    S._notify_send_channel = Sender({"telegram": True})
    S.start_notify_outbox()          # 这里会把盘上那条「还没送出去的」读回来，正是重启后该发生的事
    S._notify_enqueue("done", "下载完成", "thread")
    deadline = time.time() + 5
    while time.time() < deadline and (not recs() or recs()[-1]["text"] != "thread"
                                      or recs()[-1]["status"] == "pending"):
        time.sleep(0.1)
    ck("H7 后台线程真的会把新事件发出去（不用等 tick）",
       recs()[-1]["status"] == "sent", recs()[-1])
    S._notify_outbox_stop.set()
    with contextlib.suppress(Exception):
        S._notify_outbox_thread.join(timeout=8)
    ck("H8 线程能停干净", not S._notify_outbox_thread.is_alive())
    S._notify_send_channel = orig_send_channel

# ============ I. 界面读数与接口 ============
print("== I 读数 ==")
with quiet_log(), tmpdir(), sender({"telegram": False, "serverchan": False}):
    reset(**TGON, sc="SCT999")
    p = S._outbox_payload()
    ck("I1 空表读数三项计数都在", p["counts"] == {"pending": 0, "sent": 0, "dropped": 0})
    ck("I2 读数带间隔表，界面照它写文案", p["retry_delays"] == list(S.NOTIFY_RETRY_DELAYS))
    ck("I3 读数带上限与文件名", p["keep"] == S._OUTBOX_KEEP and p["file"].endswith("notify_outbox.json"))
    S._notify_enqueue("done", "下载完成", "one more")
    S._outbox_tick()
    p = S._outbox_payload()
    ck("I4 待发计数对得上", p["counts"]["pending"] == 1)
    r = p["records"][0]
    ck("I5 记录有中文类别名（订阅/完成/失败/开播）", r["kind_label"] == "下载完成")
    ck("I6 通道给的是人话名字", r["channels"] == ["Telegram", "Server酱"], r["channels"])
    ck("I7 待发的会报下次隔几秒", 0 <= r["next_in"] <= 30, r["next_in"])
    ck("I8 正文只带前 300 字（界面不指望看全文）", len(r["text"]) <= 300)
    ck("I9 读数是新的在前", p["records"][0]["id"] >= p["records"][-1]["id"])
    q = S.api_notify_outbox_retry()
    ck("I10 「立即重试」报告排队了几条", q["queued"] == 1)
    ck("I11 「立即重试」把 next_try 推到当下", recs()[0]["next_try"] <= time.time() + 0.5)
    ck("I12 「立即重试」自己不动网络（发送交给后台线程）", isinstance(q.get("records"), list))
    c = S.api_notify_outbox_clear()
    ck("I13 清空报告抹掉几条", c["removed"] == 1 and recs() == [])
    ck("I14 清空也落盘（重启不会又冒出来）",
       json.loads(S.NOTIFY_OUTBOX_FILE.read_text(encoding="utf-8"))["records"] == [])
    ck("I15 清空后再读是空的", S._outbox_payload()["counts"]["pending"] == 0)

paths = {getattr(r, "path", "") for r in S.app.routes}
GETS = {(m, p) for r in S.app.routes for m in getattr(r, "methods", set()) for p in [getattr(r, "path", "")]}
ck("I16 GET /api/notify/outbox 注册了", ("GET", "/api/notify/outbox") in GETS, str(sorted(paths)[:0]))
ck("I17 POST /api/notify/outbox/retry 注册了", ("POST", "/api/notify/outbox/retry") in GETS)
ck("I18 POST /api/notify/outbox/clear 注册了", ("POST", "/api/notify/outbox/clear") in GETS)

# ============ J. 接线核对 ============
print("== J 接线 ==")
srv = (ROOT / "server.py").read_text(encoding="utf-8")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
# 那张卡的文案搬进了词表（#55）：index.html 里只剩 tr('notify.*' / 'settings.outbox*')，字在 static/i18n.js 里。
# 所以 J14/J17/J18/J20 判两件事：界面上按这个键取词，词表中文那一份仍带着那句话。
import re as _re  # noqa: E402
_i18n = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
_zh = _i18n[_i18n.find("    zh: {"):_i18n.find("\n    en: {")]
ZH = dict(_re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh))
ck("J1 文件常量在 STATE_DIR 里（跟 config/history 同一个地方）",
   'NOTIFY_OUTBOX_FILE = STATE_DIR / "notify_outbox.json"' in srv)
ck("J2 三个通知方法都改成进队",
   srv.count('_notify_enqueue("done"') == 1 and srv.count('_notify_enqueue("fail"') >= 1
   and srv.count('_notify_enqueue("sub"') == 1)
# fail 这一档现在有两处调用：下载失败，以及 #28 的登录锁定告警 —— 复用同一开关，不为此新增配置键
ck("J2b 登录保护的告警复用 fail 这一档（没有新通道开关）",
   srv.count('_notify_enqueue("fail"') == 2 and 'def _auth_notify' in srv
   and "web_auth_notify" not in srv)
ck("J3 企业微信那三个猴子补丁包装已经删掉",
   "_notify_done_with_wecom" not in srv and "TelegramNotifier.notify_done =" not in srv)
ck("J4 通道判定里企业微信用的是自己的开关", 'd.get(f"wecom_notify_{kind}", True)' in srv)
ck("J5 Server酱仍只跟着完成事件（老行为）", 'if kind == "done" and (d.get("serverchan_sendkey")' in srv)
ck("J6 发送原语各自返回原因（界面要说得清）",
   "def send_detail(self" in srv and "def send_serverchan_detail(self" in srv
   and "def wecom_send_detail(text" in srv)
ck("J7 老接口名还在（别的地方调着）", "def send(self, text" in srv
   and "def send_serverchan(self, title" in srv and "def wecom_send(text" in srv)
ck("J8 token 过期时把缓存清掉，别让每次重试都撞同一张废票",
   "40014, 42001, 41001" in srv and '_wecom_token_cache["token"], _wecom_token_cache["expires"] = "", 0' in srv)
ck("J9 测试按钮仍走直发（测试消息不该进补发队列）",
   "ok = self.send(" in srv and 'ok = wecom_send("🔔' in srv)
ck("J10 队列写盘用临时文件替换（半截文件不该让下次读不回）",
   'Path(str(NOTIFY_OUTBOX_FILE) + ".tmp")' in srv and "os.replace(tmp, NOTIFY_OUTBOX_FILE)" in srv)
ck("J11 投递不就地改共享记录（界面读数不会看到改一半）",
   "def _outbox_replace(rec: dict)" in srv and "_outbox_state[\"records\"][i] = rec" in srv)
ck("J12 启动时开线程并读回上次没送完的",
   "start_notify_outbox()" in srv[srv.index("def main():"):] and "pending = _outbox_load()" in srv)
ck("J13 直播开播通知也进队列（原来是直发）", '_notify_enqueue("live"' in srv)
ck("J14 界面有那张卡",
   """<div class="section-title">{{ tr('notify.outboxTitle') }}</div>""" in html
   and ZH.get("notify.outboxTitle") == "通知补发队列" and "notify_outbox.json" in html)
ck("J15 界面把间隔表读出来而不是写死", "{{ (outbox.retry_delays || []).join(' → ') }}" in html)
ck("J16 界面三个动作各绑各的接口",
   "api('/api/notify/outbox', { noLog: true })" in html
   and "api('/api/notify/outbox/retry'" in html and "api('/api/notify/outbox/clear'" in html)
ck("J17 补发状态在界面上分得清三种",
   """{{ r.status === 'sent' ? tr('notify.stSent') : (r.status === 'pending' ? tr('notify.stPending') : tr('notify.stDropped')) }}""" in html
   and ZH.get("notify.stPending") == "待补发" and ZH.get("notify.stSent") == "已送出"
   and ZH.get("notify.stDropped") == "已丢弃")
ck("J18 界面显示还欠哪个通道与下次几点再试",
   """{{ tr('notify.stillOwes') }} {{ r.channels.join(tr('settings.fieldSep')) }}""" in html
   and "还欠" in ZH.get("notify.stillOwes", "") and ZH.get("settings.fieldSep") == "、"
   and "fmtWait(r.next_in)" in html)
ck("J19 进设置页才拉一次（不在首页白跑）",
   "if (p === 'settings' && !(outbox.value.records || []).length) loadOutbox()" in html)
ck("J20 清空前会先问一句", """tr('settings.outboxClearBody')""" in html
   and "清空后待补发的通知不会再重试" in ZH.get("settings.outboxClearBody", ""))
ck("J21 新增的设置项一个都没有（不碰 ConfigBody）",
   "notify_outbox_enabled" not in srv and "outbox" not in srv[srv.index("class ConfigBody"):
                                                             srv.index("class ConfigBody") + 4000])
ck("J22 DEFAULTS 没被塞进 outbox 相关的键",
   all("outbox" not in k.lower() for k in S.ConfigManager.DEFAULTS))
pack = (ROOT / "pack_release.py").read_text(encoding="utf-8")
ck("J23 打包排除清单里排掉了它（这台机器下过什么不能跟着包走）",
   'notify_outbox\\.json' in pack, pack.count("notify_outbox"))
ck("J24 试跑后清理与出包前的泄漏检查都认它", pack.count('"notify_outbox.json"') >= 2)

# ============ K. 还原 ============
print("== K 还原 ==")
for k, v in saved_cfg.items():
    S.cfg.data[k] = v
S.NOTIFY_OUTBOX_FILE = saved_file
S._outbox_state.clear()
S._outbox_state.update(saved_state)
S._notify_send_channel = orig_send_channel
S.tg_notifier.send_detail = orig_tg_send
S.tg_notifier.send_serverchan_detail = orig_tg_sc
S.wecom_send_detail = orig_wecom
S.requests = orig_requests
S.log_mgr.log = orig_log
S._notify_outbox_thread = saved_thread
S._notify_outbox_stop.clear()
S._notify_outbox_kick.clear()
ck("K1 设置原样还回去", all(S.cfg.data.get(k) == saved_cfg[k] for k in CFG_KEYS))
ck("K2 outbox 文件指回真的那个", S.NOTIFY_OUTBOX_FILE == saved_file)
ck("K3 内存表恢复成进来时的样子", S._outbox_state == saved_state)
ck("K4 发送原语是原本那几个", S._notify_send_channel is orig_send_channel
   and S.tg_notifier.send_detail is orig_tg_send and S.wecom_send_detail is orig_wecom)
ck("K5 日志函数没被留在假的那一个", S.log_mgr.log is orig_log)
ck("K6 临时目录已经清掉", not TMP.exists())

print(f"\n合计 {TOTAL} 项，失败 {len(FAILED)} 项")
if FAILED:
    print("FAILED:", "; ".join(FAILED))
    sys.exit(1)
sys.exit(0)
