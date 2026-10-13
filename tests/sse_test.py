r"""SSE 实时推送（GET /api/events）自检。

两段：
  1) 纯内存：SSEHub 的订阅/投递/丢帧，快照签名（只有会改变表格结构的字段才算变），
     日志 seq 游标。
  2) 起一个自己的 uvicorn（默认 127.0.0.1:8899，不碰 8765 的开发服务），把 server 里的
     queue / log_mgr / HOST_THROTTLE / HARDSUB_JOBS 换成假的，用真的 SSE 帧逐条读：
     结构变化 → state，进度变化 → prog，日志 → logs，烧录 → hardsub，没事就别吭。
     日志写到 %TEMP%\md_sse_selftest\run.log，不写 config.json、不下载、不联网。

跑法：`python tests/sse_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import json
import os
import queue as stdq
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests  # noqa: E402
import uvicorn  # noqa: E402

KEEP = "--keep" in sys.argv
TMP = Path(tempfile.gettempdir()) / "md_sse_selftest"
TMP.mkdir(parents=True, exist_ok=True)
PORT = int(os.environ.get("MD_SSE_TEST_PORT") or 8899)
BASE = f"http://127.0.0.1:{PORT}"
FAILED: list[str] = []


def ck(name: str, cond, extra: str = ""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# ---------------------------------------------------------------- 假组件
class FakeTask:
    def __init__(self, tid, **kw):
        self.id = tid
        self.url = kw.get("url", f"https://example.com/{tid}")
        self.title = kw.get("title", f"任务 {tid}")
        self.status = kw.get("status", "queued")
        self.progress = kw.get("progress", 0.0)
        self.speed = kw.get("speed", "")
        self.eta = kw.get("eta", "")
        self.elapsed_sec = kw.get("elapsed_sec", 0)
        self.started_at = kw.get("started_at", "")
        self.error_msg = ""
        self.filepath = ""
        self.pinned = False
        self.priority = 0
        self.queue_name = "default"
        self.created_at = kw.get("created_at", "2026-01-01T00:00:00")
        self.res_label = kw.get("res_label", "")
        self.total_bytes = kw.get("total_bytes", 0)
        self.done_bytes = kw.get("done_bytes", 0)
        self.thumbnail = kw.get("thumbnail", "")

    def to_dict(self):
        return {
            "id": self.id, "url": self.url, "title": self.title, "status": self.status,
            "progress": self.progress, "speed": self.speed, "eta": self.eta,
            "error_msg": self.error_msg, "filepath": self.filepath, "pinned": self.pinned,
            "priority": self.priority, "queue_name": self.queue_name,
            "created_at": self.created_at, "elapsed_sec": self.elapsed_sec,
        }


class FakeQueue:
    def __init__(self):
        self.tasks = {}
        self.pending = []
        self.running = 0
        self.paused = False

    def list_tasks(self, sort_by="queue"):
        return [t.to_dict() for t in self.tasks.values()]


class FakeThrottle:
    def __init__(self):
        self.left = 120

    def snapshot(self):
        # 剩余冷却秒数每拍都在掉，正好用来验「只带不签」
        self.left -= 1
        return [{"host": "i.example.com", "strikes": 2, "left": self.left, "cooldown": 60.0}]


# ---------------------------------------------------------------- 帧读取
class SSEClient:
    """后台线程逐帧解析 SSE，主线程按超时取帧 —— 才能断言「该来的来了、不该来的没来」。"""

    def __init__(self):
        self.frames: stdq.Queue = stdq.Queue()
        self.error = None
        self._resp = None
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._resp = requests.get(BASE + "/api/events", stream=True, timeout=60)
        self._resp.raise_for_status()
        self._t.start()
        return self

    def __exit__(self, *_a):
        self._stop.set()
        try:
            self._resp.close()
        except Exception:
            pass
        self._t.join(timeout=3)

    def _run(self):
        topic = None
        try:
            for raw in self._resp.iter_lines(decode_unicode=False):
                if self._stop.is_set():
                    break
                line = (raw or b"").decode("utf-8", "replace")
                if line.startswith("event: "):
                    topic = line[7:].strip()
                elif line.startswith("data: "):
                    try:
                        self.frames.put((topic, json.loads(line[6:])))
                    except Exception as e:
                        self.error = repr(e)
                elif line.startswith(":"):
                    self.frames.put(("ping", None))
        except Exception as e:
            if not self._stop.is_set():
                self.error = repr(e)

    def next(self, timeout=3.0):
        try:
            return self.frames.get(timeout=timeout)
        except stdq.Empty:
            return (None, None)

    def until(self, topic, timeout=4.0):
        """取到某个主题的帧为止，返回 (命中帧, 之前路过的帧主题)。"""
        return self.until_pred(topic, lambda _p: True, timeout)

    def until_pred(self, topic, pred, timeout=5.0):
        """连上后服务端会先补一帧当前状态，所以按内容等，而不是按「下一帧」等。"""
        passed, end = [], time.time() + timeout
        while time.time() < end:
            t, p = self.next(max(0.05, end - time.time()))
            if t is None:
                return (None, passed)
            if t == topic and pred(p):
                return ((t, p), passed)
            passed.append(t)
        return (None, passed)

    def drain(self, seconds):
        out, end = [], time.time() + seconds
        while time.time() < end:
            t, p = self.next(max(0.05, end - time.time()))
            if t is None:
                break
            out.append((t, p))
        return out


# ---------------------------------------------------------------- 开跑
print("== 导入 server ==")
import server as S  # noqa: E402

ORIG_LOG_FILE = str(S.LOG_FILE)
S.LOG_FILE = str(TMP / "run.log")  # LogManager.log 追加写的就是这个
S.log_mgr = S.LogManager()
S.queue = FakeQueue()
S.HOST_THROTTLE = FakeThrottle()
S.HARDSUB_JOBS = {}

print("== A. SSEHub ==")
hub = S.SSEHub(maxsize=3)
ck("A1 初始无客户端", hub.clients() == 0)
c1, c2 = hub.subscribe(), hub.subscribe()
ck("A2 两个订阅者", hub.clients() == 2)
hub.publish("state", {"a": 1})
ck("A3 消息投给客户端", c1.get_nowait() == ("state", {"a": 1}))
ck("A4 第二个客户端也收到", c2.get_nowait()[0] == "state")
for _ in range(10):
    hub.publish("prog", {"i": 1})
ck("A5 慢客户端溢出只丢帧不抛异常", hub.dropped >= 7, f"dropped={hub.dropped}")
ck("A6 队列仍是活的", c1.qsize() <= 3)
hub.unsubscribe(c1)
ck("A7 取消订阅", hub.clients() == 1)
hub.unsubscribe(c1)
ck("A8 重复取消不报错", hub.clients() == 1)
before = c2.qsize()
hub.publish("", {"x": 1})
ck("A9 空主题直接忽略", c2.qsize() == before)

print("== B. 帧编码 ==")
frame = S._sse_pack("state", {"msg": "队列已暂停", "n": 2})
ck("B1 event/data 双行 + 空行结尾", frame.startswith("event: state\ndata: ") and frame.endswith("\n\n"))
ck("B2 中文不转义", "队列已暂停" in frame)
ck("B3 一帧只有一个 data 行", frame.count("\n") == 3)

print("== C. 快照签名 ==")
q = S.queue
q.tasks = {"t1": FakeTask("t1", status="downloading"), "t2": FakeTask("t2", status="queued")}
q.running, q.pending, q.paused = 1, ["t2"], False
base_state = S._sse_state()
base_sig = S._sse_state_sig(base_state)
ck("C1 state 带 throttle", isinstance(base_state.get("throttle"), list))
t1 = q.tasks["t1"]
t1.progress, t1.speed, t1.eta, t1.elapsed_sec = 66.6, "3.2MiB/s", "00:12", 40
ck("C2 进度/速度/耗时的变化不算结构变化", S._sse_state_sig(S._sse_state()) == base_sig)
t1.status = "finished"
ck("C3 状态变化要重推", S._sse_state_sig(S._sse_state()) != base_sig)
t1.status = "downloading"
ck("C4 改回去签名也回去", S._sse_state_sig(S._sse_state()) == base_sig)
t1.title = "改了名"
ck("C5 标题变化要重推", S._sse_state_sig(S._sse_state()) != base_sig)
t1.title = "任务 t1"
q.paused = True
ck("C6 暂停标志变化要重推", S._sse_state_sig(S._sse_state()) != base_sig)
q.paused = False
q.running = 2
ck("C7 并发数变化要重推", S._sse_state_sig(S._sse_state()) != base_sig)
q.running = 1
q.tasks["t3"] = FakeTask("t3", pinned=True)
ck("C8 加任务要重推", S._sse_state_sig(S._sse_state()) != base_sig)
del q.tasks["t3"]
ck("C9 全部还原后签名回到基线", S._sse_state_sig(S._sse_state()) == base_sig)
ck("C10 冷却剩余秒数每拍都在掉，但不进签名",
   S._sse_state_sig(S._sse_state()) == S._sse_state_sig(S._sse_state()) == base_sig)
pr = S._sse_prog()
ck("C11 prog 只收下载中的任务", set(pr["rows"]) == {"t1"})
ck("C12 prog 带四件套", set(pr["rows"]["t1"]) == {"progress", "speed", "eta", "elapsed_sec"})
ck("C13 prog 带 running/pending", pr["running"] == 1 and pr["pending"] == 1)
q.tasks["t1"].started_at = (datetime.now() - timedelta(seconds=90)).isoformat(timespec="seconds")
ck("C14 prog 的耗时按 started_at 现算", S._sse_prog()["rows"]["t1"]["elapsed_sec"] in (90, 91))
q.tasks["t1"].started_at = "不像时间"
ck("C15 started_at 脏了就当 0，不抛异常", S._sse_prog()["rows"]["t1"]["elapsed_sec"] == 0)
q.tasks["t1"].started_at = ""
# 卡片上的清晰度 / 字节数 / 封面：只在有值时进包，前端靠这个就地合并、不能整行覆盖
q.tasks["t1"].res_label = "1080p · MP4"
q.tasks["t1"].total_bytes = 4096
q.tasks["t1"].done_bytes = 2048
q.tasks["t1"].thumbnail = "https://example.com/cover.jpg"
pr2 = S._sse_prog()["rows"]["t1"]
ck("C16 prog 带上卡片要用的清晰度、字节数与封面",
   pr2["res_label"] == "1080p · MP4" and pr2["total_bytes"] == 4096
   and pr2["done_bytes"] == 2048 and pr2["thumbnail"].endswith("cover.jpg"), pr2)
q.tasks["t1"].res_label = ""
q.tasks["t1"].total_bytes = 0
q.tasks["t1"].thumbnail = ""
ck("C17 没量到的那几项不进包，prog 回到四件套",
   set(S._sse_prog()["rows"]["t1"]) == {"progress", "speed", "eta", "elapsed_sec"},
   S._sse_prog()["rows"]["t1"])

print("== D. 日志游标 ==")
S.log_mgr.log("第一行")
S.log_mgr.log("第二行", "warning")
fresh = S._sse_logs_after(0)
ck("D1 从 0 起能拿到全部", [e["message"] for e in fresh] == ["第一行", "第二行"])
ck("D2 每行都有 seq", all(int(e.get("seq") or 0) > 0 for e in fresh))
ck("D3 seq 递增", fresh[0]["seq"] < fresh[1]["seq"])
ck("D4 游标只放行新行", S._sse_logs_after(fresh[1]["seq"]) == [])
S.log_mgr.log("第三行")
ck("D5 新行能被游标捞出", [e["message"] for e in S._sse_logs_after(fresh[1]["seq"])] == ["第三行"])
S.log_mgr.clear()
ck("D6 clear 后没有残留", S._sse_logs_after(0) == [])
S.log_mgr.log("清空之后的一行")
ck("D7 clear 不重置 seq（游标不会倒回去）",
   [e["message"] for e in S._sse_logs_after(fresh[-1]["seq"])] == ["清空之后的一行"])

print("== E. 起测试服务 ==")
cfg = uvicorn.Config(S.app, host="127.0.0.1", port=PORT, log_level="error")
srv = uvicorn.Server(cfg)
threading.Thread(target=srv.run, daemon=True).start()
for _ in range(200):
    if srv.started:
        break
    time.sleep(0.05)
ck("E0 测试服务已启动", srv.started, BASE)

with SSEClient() as cli:
    t, p = cli.next(5)
    ck("E1 连上就先收到 hello", t == "hello", f"topic={t}")
    t, p = cli.next(5)
    ck("E2 紧跟一份完整 state", t == "state" and isinstance(p.get("tasks"), list))
    ck("E3 首帧 state 就是当前队列", {x["id"] for x in p["tasks"]} == {"t1", "t2"})
    ck("E4 首帧带 running/paused/pending",
       p["running"] == 1 and p["paused"] is False and p["pending"] == 1)
    ck("E5 首帧任务含 progress 字段", "progress" in (p["tasks"][0] or {}))
    st = requests.get(BASE + "/api/events/stats", timeout=5).json()
    ck("E6 连接计数为 1", st["clients"] == 1, json.dumps(st, ensure_ascii=False))

    q.tasks["t9"] = FakeTask("t9", title="新来的", status="downloading")
    hit, passed = cli.until_pred("state", lambda d: {x["id"] for x in d["tasks"]} == {"t1", "t2", "t9"})
    ck("E7 加任务后 5 秒内推来 state", hit is not None, f"passed={passed}")
    ck("E8 推送内容是加完之后的表",
       bool(hit) and {x["id"] for x in hit[1]["tasks"]} == {"t1", "t2", "t9"})
    q.tasks["t9"].progress = 12.5
    q.tasks["t9"].speed = "1.1MiB/s"
    hit, passed = cli.until_pred("prog", lambda d: d["rows"].get("t9", {}).get("progress") == 12.5)
    ck("E9 进度变化推 prog", hit is not None, f"passed={passed}")
    ck("E10 prog 里是新进度和速度",
       bool(hit) and hit[1]["rows"]["t9"]["speed"] == "1.1MiB/s")
    ck("E11 进度变化不带动整张表重推", hit is not None and "state" not in passed, f"passed={passed}")
    t, p = cli.next(2)
    ck("E12 进度不再变就不推帧", t is None, f"got={t}")

    S.log_mgr.log("SSE 自检：日志帧")
    hit, passed = cli.until_pred("logs", lambda l: [e["message"] for e in l] == ["SSE 自检：日志帧"])
    ck("E13 日志有变化推 logs", hit is not None, f"passed={passed}")
    ck("E14 logs 是增量（只含新行）",
       bool(hit) and [e["message"] for e in hit[1]] == ["SSE 自检：日志帧"])
    S.log_mgr.log("SSE 自检：第二行日志")
    hit, _ = cli.until_pred("logs", lambda l: "SSE 自检：第二行日志" in [e["message"] for e in l])
    ck("E15 第二帧只带第二行", bool(hit) and [e["message"] for e in hit[1]] == ["SSE 自检：第二行日志"])

    with S.HARDSUB_LOCK:
        S.HARDSUB_JOBS["m1"] = {"media": "m1.mp4", "status": "running", "elapsed": "00:01",
                                "total": 30.0, "proc": object()}
    hit, passed = cli.until_pred("hardsub", lambda l: any(j.get("media") == "m1.mp4" for j in l))
    ck("E16 烧字幕任务变化推 hardsub", hit is not None, f"passed={passed}")
    ck("E17 hardsub 带得上任务、剔掉 proc",
       bool(hit) and len(hit[1]) == 1 and "proc" not in hit[1][0] and hit[1][0]["total"] == 30.0)

    got = cli.drain(6.5)  # 什么都不改：只有保活注释，没有数据帧
    ck("E18 全静默时不刷帧", [t for t, _ in got if t != "ping"] == [], str([t for t, _ in got]))
    ck("E19 空闲 5 秒后有 ping 保活", sum(1 for t, _ in got if t == "ping") >= 1,
       str(sum(1 for t, _ in got if t == "ping")))

    api = requests.get(BASE + "/api/tasks", timeout=5).json()
    ck("E20 /api/tasks 与 state 口径一致",
       {x["id"] for x in api["tasks"]} == {x["id"] for x in S._sse_state()["tasks"]})

with SSEClient() as cli2:
    st = requests.get(BASE + "/api/events/stats", timeout=5).json()
    ck("E21 旧连接关掉后计数不涨", st["clients"] == 1, json.dumps(st, ensure_ascii=False))
    t, p = cli2.next(5)
    ck("E22 新连接照常收到 hello", t == "hello")
    t, p = cli2.next(5)
    ck("E23 新连接拿到的是当前表（含中途加的任务）",
       t == "state" and {x["id"] for x in p["tasks"]} == {"t1", "t2", "t9"})
    q.tasks["t8"] = FakeTask("t8", title="第二个客户端看这个")
    hit, _ = cli2.until_pred("state", lambda d: any(x["id"] == "t8" for x in d["tasks"]), timeout=5)
    ck("E24 后来者也能收到结构变化", hit is not None)

for _ in range(60):
    sc = requests.get(BASE + "/api/events/stats", timeout=5).json()
    if sc["clients"] == 0:
        break
    time.sleep(0.1)
ck("E25 客户端断开后服务端退订", sc["clients"] == 0, json.dumps(sc, ensure_ascii=False))
ck("E26 读取线程没报错", cli2.error is None, str(cli2.error))

print("== 收尾 ==")
try:
    n = len((TMP / "run.log").read_text(encoding="utf-8").splitlines())
except Exception:
    n = 0
ck("F1 测试日志只落在 Temp", n >= 4, f"{TMP / 'run.log'} lines={n}")
ck("F2 没往项目的 " + ORIG_LOG_FILE + " 里写东西", str(S.LOG_FILE) != ORIG_LOG_FILE)
srv.should_exit = True
time.sleep(0.5)
if not KEEP:
    shutil.rmtree(TMP, ignore_errors=True)
print(f"\nFAILED: {FAILED if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
