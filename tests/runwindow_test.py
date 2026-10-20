r"""队列定时窗自检（#206②）。

全部内存跑：假的 engine / cfg，`_run` 换成记账函数，不联网、不碰 config.json、不起真下载。
`_pump` 的闸只验「该不该开新任务、压住的排在哪」。时段用当下时钟推出来的 CLOSED_WIN / OPEN_WIN，
所以断言不随跑的时刻变。

跑法：`python tests/runwindow_test.py`
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED: list[str] = []
TMP = Path(__file__).resolve().parent / "_runwindow_tmp"


def ck(name: str, cond, extra: str = ""):
    if not bool(cond):
        FAILED.append(name)
        print(f"FAIL {name} {extra}")
    else:
        print(f"PASS {name}")


def _hhmm_min(m: int) -> str:
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


_NOW = datetime.now()
_NOWMIN = _NOW.hour * 60 + _NOW.minute
# 起点在 6 小时以后、宽一小时：分钟漂移与跨零点都碰不到它，判「关」是稳的
CLOSED_WIN = f"{_hhmm_min(_NOWMIN + 360)}-{_hhmm_min(_NOWMIN + 420)}"
OPEN_WIN = "00:00-23:59"


class FakeCfg:
    def __init__(self, data):
        self.data = data


class FakeEngine:
    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def log(self, msg, level="info"):
        self.lines.append((str(msg), str(level)))


def make_queue(cfg_data=None):
    d = {"concurrent": 3, "max_per_host": 0, "adaptive_throttle": False,
         "run_window": "", "queue_windows": {}, "named_queues": ["default", "night"],
         "download_dir": str(TMP)}
    d.update(cfg_data or {})
    q = S.TaskQueue(FakeEngine(), FakeCfg(d), None, None)
    started: list[str] = []
    q._run = lambda task: started.append(task.id)   # 实例属性盖掉真下载
    q._started = started
    return q


def add_task(q, tid, queue_name="default"):
    t = S.DownloadTask(id=tid, url=f"https://example.com/{tid}", queue_name=queue_name)
    q.tasks[tid] = t
    q.pending.append(tid)
    return t


def settle(q, want):
    """_run 在子线程里记账，等数量到位再断言（多出来的也一起收）。"""
    for _ in range(60):
        if len(q._started) >= want:
            time.sleep(0.03)
            return
        time.sleep(0.03)
    time.sleep(0.05)


def cancel(q):
    if q._window_timer:
        q._window_timer.cancel()
        q._window_timer = None


print("=== A. parse_run_windows ===")
ck("A1 空=没有时段也没有错", S.parse_run_windows("") == ([], []), str(S.parse_run_windows("")))
ck("A2 一行一条", S.parse_run_windows("09:00-12:00\n22:00-06:00") == ([("09:00", "12:00"), ("22:00", "06:00")], []))
ck("A3 井号与双斜杠是注释、空行跳过",
   S.parse_run_windows("# 说明\n// 也是注释\n\n01:00-02:00")[0] == [("01:00", "02:00")])
ck("A4 中文冒号能认", S.parse_run_windows("22：00-06：00")[0] == [("22:00", "06:00")])
ck("A5 照抄限速那栏（带 -> 2M）只取前半",
   S.parse_run_windows("09:00-12:00 -> 2M") == ([("09:00", "12:00")], []),
   str(S.parse_run_windows("09:00-12:00 -> 2M")))
ck("A6 不足两位补零", S.parse_run_windows("9:05-12:00")[0] == [("09:05", "12:00")])
_, e7 = S.parse_run_windows("12:00-12:00")
ck("A7 起==止 顶回去（整圈/零圈说不清）", len(e7) == 1 and "整圈" in e7[0], str(e7))
_, e8 = S.parse_run_windows("24:00-06:00")
ck("A8 不存在的钟点顶回去", len(e8) == 1 and "钟点" in e8[0], str(e8))
_, e9 = S.parse_run_windows("晚上十点-早上六点")
ck("A9 认不出的行点名到第几行", len(e9) == 1 and e9[0].startswith("第 1 行"), str(e9))
rows10, errs10 = S.parse_run_windows("09:00-12:00\n垃圾")
ck("A10 坏行不拖累好行，但自己进了错单",
   rows10 == [("09:00", "12:00")] and len(errs10) == 1 and errs10[0].startswith("第 2 行"), f"{rows10} {errs10}")
ck("A11 跨零点原样保留，不擅自拆成两段", S.parse_run_windows("22:00-06:00")[0] == [("22:00", "06:00")])

print("=== B. window_hit / window_open ===")
ck("B0 基准：当下这套窗确实一个开一个关",
   S.window_open(OPEN_WIN)[0] is True and S.window_open(CLOSED_WIN)[0] is False,
   f"{OPEN_WIN} {CLOSED_WIN}")
ck("B1 当天内", S.window_hit("09:00", "12:00", "10:00") and not S.window_hit("09:00", "12:00", "13:00"))
ck("B2 跨零点两头都算", S.window_hit("22:00", "06:00", "23:30") and S.window_hit("22:00", "06:00", "02:00"))
ck("B3 跨零点的中间是关的", not S.window_hit("22:00", "06:00", "12:00"))
ck("B4 边界含等号", S.window_hit("09:00", "12:00", "09:00") and S.window_hit("09:00", "12:00", "12:00"))


def tnow(hhmm):
    return _NOW.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:5]), second=0, microsecond=0)


ck("B5 没填=永远能跑（升级上来没配过的默认行为）", S.window_open("", tnow("03:00"))[0] is True)
ck("B5b None 也当没填", S.window_open(None, tnow("03:00"))[0] is True)
o6, n6, r6, w6 = S.window_open("22:00-06:00", tnow("12:00"))
ck("B6 关着时给出下一次开门钟点与剩余分钟",
   o6 is False and r6 == "22:00" and w6 == 600, f"{o6} {r6} {w6}")
ck("B7 关着的说明把两段钟点都写出来", "22:00" in n6 and "06:00" in n6 and "不在运行时段" in n6, n6)
o8, _n8, r8, w8 = S.window_open("09:00-12:00\n22:00-06:00", tnow("13:00"))
ck("B8 多段取最近的一个起点", o8 is False and r8 == "22:00" and w8 == 540, f"{r8} {w8}")
ck("B9 命中任一段就开门", S.window_open("09:00-12:00\n22:00-06:00", tnow("09:30"))[0] is True)
_o, note10, _r, _w = S.window_open("垃圾行\n09:00-12:00", tnow("10:00"))
ck("B10 有认不出的行时开门照旧，但说明里点名", _o is True and "没认出来的行" in note10, note10)
_gc, note11, _r11, _w11 = S.window_open("垃圾行", tnow("10:00"))
ck("B11 整栏都没认出来：开门照旧 + 说明里点名（不让手改坏的配置静默生效）",
   _gc is True and "没认出来的行" in note11, note11)
ck("B12 剩余分钟恒为非负（起点已过就绕一圈）", S._hm_until("01:00", "23:00") == 120)

print("=== C. _pump 上的两道闸 ===")
q = make_queue({"run_window": CLOSED_WIN})
add_task(q, "a")
add_task(q, "b")
q._pump()
settle(q, 0)
ck("C1 全局窗外：一条新任务都不开", q._started == [] and q.running == 0, str(q._started))
ck("C2 队列原样留在 pending，没被丢掉", q.pending == ["a", "b"], str(q.pending))
ck("C3 排了到点自醒的闹钟", q._window_timer is not None and q._window_timer.is_alive())
ck("C4 闹钟走的是自己的通道，不是 900 秒上限那条", q._wake_timer is None and q._window_timer is not None)
ck("C5 为窗关着记了一行日志", len([x for x in q.engine.lines if "队列定时窗" in x[0]]) == 1, str(q.engine.lines))
q._pump()
ck("C6 再泵一次不多刷日志", len([x for x in q.engine.lines if "队列定时窗" in x[0]]) == 1)
cancel(q)

q13 = make_queue({"run_window": CLOSED_WIN})
add_task(q13, "c1")
q13._arm_window_wake(CLOSED_WIN.split("-")[0])
first = q13._window_timer
q13._arm_window_wake(_hhmm_min(_NOWMIN + 600))   # 更晚的闹钟不该把更早的换掉
ck("C7 已有更早的闹钟就留着（多个窗同时关着时按最近那个开门）",
   q13._window_timer is first and first.is_alive())
cancel(q13)

q2 = make_queue({"queue_windows": {"night": CLOSED_WIN}})
q2.cfg.data["concurrent"] = 5
add_task(q2, "n1", "night")
add_task(q2, "n2", "night")
add_task(q2, "d1", "default")
q2._pump()
settle(q2, 1)
ck("C8 队列级窗：只压住那条队列，别的照常开", q2._started == ["d1"], str(q2._started))
ck("C9 压住的排回队首（开窗那一刻先跑它们）", q2.pending == ["n1", "n2"], str(q2.pending))
ck("C10 队列级窗也排了闹钟", q2._window_timer is not None)
qlog = make_queue({"queue_windows": {"night": CLOSED_WIN}})
qlog.cfg.data["concurrent"] = 5
add_task(qlog, "m1", "night")
add_task(qlog, "m2", "night")
add_task(qlog, "m3", "night")
qlog._pump()
settle(qlog, 0)
lines = [x[0] for x in qlog.engine.lines if "定时窗" in x[0]]
ck("C13 队列级窗也记一行（谁被压住、几点开）", len(lines) == 1 and "night" in lines[0]
   and CLOSED_WIN.split("-")[0] in lines[0], str(lines))
qlog._pump()
ck("C14 三个任务同队列只记一行，不跟着排队数刷屏",
   len([x for x in qlog.engine.lines if "定时窗" in x[0]]) == 1, str(qlog.engine.lines))
cancel(qlog)
cancel(q2)

q3 = make_queue({"run_window": CLOSED_WIN})
q3.running = 1
add_task(q3, "x")
q3._pump()
settle(q3, 0)
ck("C11 窗外不动已经在跑的那些（running 不减、线程不停）", q3.running == 1 and q3._started == [])
cancel(q3)

q4 = make_queue({"queue_windows": {"night": CLOSED_WIN}})
q4.cfg.data["concurrent"] = 1
add_task(q4, "hold1", "night")
add_task(q4, "hold2", "night")
add_task(q4, "d2", "default")
add_task(q4, "d3", "default")
q4._pump()
settle(q4, 1)
ck("C12 并发只有 1 时：压住的与没排上的各归各位，顺序稳定",
   q4._started == ["d2"] and q4.pending == ["hold1", "hold2", "d3"], f"{q4._started} {q4.pending}")
cancel(q4)

print("=== D. 开窗就放行 ===")
q5 = make_queue({"run_window": CLOSED_WIN})
add_task(q5, "f1")
q5._pump()
settle(q5, 0)
ck("D1 关着时确实压着", q5._started == [] and q5.pending == ["f1"])
q5.cfg.data["run_window"] = OPEN_WIN
q5._pump()          # 保存设置那一步就是直接调这个
settle(q5, 1)
ck("D2 改窗后立刻重泵就放行，不用等下一条事件", q5._started == ["f1"], str(q5._started))
cancel(q5)

q6 = make_queue({"run_window": ""})
add_task(q6, "k1")
add_task(q6, "k2")
q6._pump()
settle(q6, 2)
ck("D3 没设窗=与从前一字不差，全部放行", sorted(q6._started) == ["k1", "k2"], str(q6._started))
cancel(q6)

print("=== E. window_status ===")
q7 = make_queue({"run_window": "", "queue_windows": {"night": CLOSED_WIN}})
add_task(q7, "g1", "subscribe")
st = q7.window_status()
ck("E1 顶层字段齐全",
   set(st) >= {"open", "note", "resume_at", "wait_minutes", "global_window", "held", "queues"}, str(sorted(st)))
names = [r["name"] for r in st["queues"]]
ck("E2 队列行按 named_queues ∪ 后端自用名 ∪ 任务实际用过的名 列全",
   {"default", "night", "subscribe", "music"} <= set(names), str(names))
row = {r["name"]: r for r in st["queues"]}
ck("E3 没填窗的队列也列出来、标成开着（设置页要按这张表逐行给输入框）",
   row["default"]["windows"] == "" and row["default"]["open"] is True, str(row["default"]))
ck("E4 填了窗的队列带自己的窗文", row["night"]["windows"] == CLOSED_WIN, str(row["night"]))
ck("E5 全局没设窗时 open=True、held=0", st["open"] is True and st["held"] == 0, str(st))
ck("E6 关着的队列 held 数得出来", row["night"]["open"] is False and row["night"]["held"] == 0, str(row["night"]))
q8 = make_queue({"run_window": CLOSED_WIN, "queue_windows": {"night": CLOSED_WIN}})
add_task(q8, "h1", "night")
add_task(q8, "h2", "night")
add_task(q8, "h3", "default")
q8.pending = ["h1", "h2", "h3"]
st2 = q8.window_status()
qr = {r["name"]: r for r in st2["queues"]}
ck("E7 全局关着时 held 就是排队的条数", st2["open"] is False and st2["held"] == 3, str(st2))
ck("E8 队列行给得出各自压住的条数", qr["night"]["held"] == 2, str(qr["night"]))
ck("E9 界面要的字段一行不缺",
   set(qr["night"]) >= {"name", "open", "windows", "note", "resume_at", "wait_minutes", "held"})
ck("E10 队列行也报下一次开门钟点", qr["night"]["resume_at"] == CLOSED_WIN.split("-")[0], str(qr["night"]))
cancel(q8)

print("=== F. SSE 签名 ===")
base = {"tasks": [], "running": 0, "paused": False, "pending": 0,
        "window": {"open": False, "resume_at": "22:00", "held": 3, "wait_minutes": 100,
                   "queues": [{"name": "night", "open": False, "held": 1}]}}
flip = json.loads(json.dumps(base))
flip["window"]["open"] = True
ck("F1 开没开门算结构变化，要推", S._sse_state_sig(base) != S._sse_state_sig(flip))
drain = json.loads(json.dumps(base))
drain["window"]["wait_minutes"] = 99
ck("F2 还剩几分钟不算结构变化（界面自己倒数，别为此整张任务表）",
   S._sse_state_sig(base) == S._sse_state_sig(drain))
held = json.loads(json.dumps(base))
held["window"]["held"] = 2
ck("F3 压住的条数变了要推", S._sse_state_sig(base) != S._sse_state_sig(held))
qheld = json.loads(json.dumps(base))
qheld["window"]["queues"][0]["held"] = 0
ck("F4 队列各自的条数变了要推", S._sse_state_sig(base) != S._sse_state_sig(qheld))
ck("F5 没带 window 的老形状不会炸",
   isinstance(S._sse_state_sig({"tasks": [], "running": 0, "paused": False, "pending": 0}), str))
st3 = q7.window_status()
ck("F6 真状态喂给签名也走得通", isinstance(S._sse_state_sig(
    {"tasks": [], "running": 0, "paused": False, "pending": 0, "window": st3}), str))

print("=== G. 接线（源码级） ===")
APP = Path(__file__).resolve().parent.parent
srv = (APP / "server.py").read_text(encoding="utf-8")
idx = (APP / "static" / "index.html").read_text(encoding="utf-8")
# 卡片标题搬进词表后，idx 里只剩 :label="tr('…')"：位置要比键，中文原话去词表里核对
import re as _re  # noqa: E402
_i18n = (APP / "static" / "i18n.js").read_text(encoding="utf-8")
_zh = _i18n[_i18n.find("    zh: {"):_i18n.find("\n    en: {")]
ZH = dict(_re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh))
ck("G1 配置默认值两条都在", '"run_window": ""' in srv and '"queue_windows": {}' in srv)
ck("G2 ConfigBody 收得到这两个键（漏了就是设置存了不生效）",
   "run_window: Optional[str] = None" in srv and "queue_windows: Optional[dict] = None" in srv)
ck("G3 保存后立刻重泵", "queue._pump()" in srv.split('if "run_window" in data or "queue_windows" in data')[1][:200])
ck("G4 存坏语法当场顶回去", 'raise HTTPException(400, "队列定时窗存不下："' in srv)
ck("G5 认不出的队列名当场顶回去", "没有这条命名队列" in srv)
ck("G6 体检路由挂着", '@app.post("/api/config/run_window/check")' in srv)
ck("G7 /api/tasks 与 SSE 都带 window", srv.count('"window": queue.window_status()') >= 2,
   str(srv.count('"window": queue.window_status()')))
ck("G8 _pump 里全局闸在 paused 之后、并发数之前",
   srv.index("g_open, g_note, g_next") < srv.index('self.max_concurrent = int(self.cfg.data.get("concurrent", 3) or 3)'))
ck("G9 队列级闸在取出任务之后、同域上限之前",
   srv.index("qtext = str(qwins.get(") < srv.index("host = self._task_host(task.url)"))
ck("G10 界面：设置默认值与回填", "run_window: ''" in idx
   and "settings.value.run_window = data.run_window" in idx
   and "settings.value.queue_windows = Object.assign" in idx)
ck("G11 界面：定时窗那一卡片排在限速时段之后",
   idx.index("""<el-form-item :label="tr('settings.runWindowLabel')" class="queue-item">""")
   > idx.index("""<el-form-item :label="tr('settings.speedWindowsLabel')" class="net-span2">""")
   and ZH.get("settings.runWindowLabel") == "队列定时窗"
   and ZH.get("settings.speedWindowsLabel") == "限速时段",
   f"{ZH.get('settings.runWindowLabel')} @ {idx.index(chr(39) + 'settings.runWindowLabel')} "
   f"> 限速时段 @ {idx.index(chr(39) + 'settings.speedWindowsLabel')}")
ck("G12 界面：每队列一行 + 检查格式 + 横幅都在",
   'v-for="q in queueRows"' in idx and 'v-if="windowHeld"' in idx and "checkRunWindows()" in idx)
ck("G13 界面：SSE 与轮询两条路都喂 queueWindow",
   "if (d.window) queueWindow.value = d.window;" in idx
   and "if (data.window) queueWindow.value = data.window;" in idx)
ck("G14 界面：新状态都在 setup 的 return 里",
   "windowHeld, queueRows, queueLabel, runWinStat, checkRunWindows" in idx)
ck("G15 界面：保存后拉一次活体状态", "await refreshRunWindow();" in idx)
ck("G16 界面：体检路由认到一个动作键，词表 zh 那句仍是「检查队列定时窗格式」",
   "'/api/config/run_window/check': 'act.config.run_window.check'" in idx
   and ZH.get("act.config.run_window.check") == "检查队列定时窗格式",
   str(ZH.get("act.config.run_window.check")))
ck("G17 界面：内置队列名按词表显示，自定义名照原样",
   '{{ queueLabel(q.name) }}' in idx
   and all(ZH.get(k) for k in ("settings.queueNameDefault", "settings.queueNameNight",
                               "settings.queueNameSubscribe", "settings.queueNameSniff",
                               "settings.queueNameMusic")))

print("=== H. 收尾 ===")
timers = [t for t in threading.enumerate() if isinstance(t, threading.Timer)]
ck("H1 没留下非守护的定时线程", all(t.daemon for t in timers), str([t.name for t in timers if not t.daemon]))

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
