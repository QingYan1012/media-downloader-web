#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直播「录满 X 分钟自动保存」离线自检。

为什么要有这个文件：最长录制时长这个功能本来已经存在，但只对「监控房间自动开录」的那几场生效
—— 手动点「开始录制」的直播没有任何房间设置可挂，永远录下去，直到人回来手动收尾。
更要紧的是 `start_live_monitor_scheduler` 的循环把 `_live_recording_tick()` 写在 `if items:` 里面：
一个监控房间都没有时收尾检查根本不跑，所以「给手动录制补一个时长」不能只加判定，还得把这一轮挪出来。

全程不起服务、不写 config、不碰下载目录，也不真的结束任务（结束动作会杀子进程、收尾文件）。
跑法：PYTHONIOENCODING=utf-8 python tests/liveduration_test.py
"""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

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


SRC = Path(S.__file__).read_text(encoding="utf-8")
INDEX = (Path(S.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

REAL_CFG = S.cfg
REAL_QUEUE = S.queue
REAL_LOAD_MON = S._load_live_monitors
REAL_PATCH = S._patch_live_monitor


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)
        self.saved = 0

    def save(self):
        self.saved += 1


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))
        return True


class FakeQueue:
    """只关心「录满了有没有去收尾」，结束动作本身（杀进程/收 .part/摘弹幕）不在这一档测。"""

    def __init__(self, tasks):
        self.tasks = tasks
        self.ended = []

    def end_live_tasks(self, ids=None, reason="用户结束录制"):
        self.ended.append((list(ids or []), reason))
        return len(ids or [])


def mk_task(tid, url, *, live=True, status=S.TaskStatus.DOWNLOADING.value,
            started_ago_min=None, limit=None, title=""):
    t = S.DownloadTask(id=tid, url=url, title=title or ("直播间 " + tid))
    t.is_live = live
    t.status = status
    if started_ago_min is None:
        t.started_at = ""
    else:
        t.started_at = (datetime.now() - timedelta(minutes=started_ago_min)).isoformat(timespec="seconds")
    t._opts = {} if limit is None else {"live_max_minutes": limit}
    return t


def run_tick(monitors, tasks, global_min):
    """把 tick 需要的四样全局换成假的，跑一次，返回 (结束调用, 日志)"""
    q = FakeQueue(tasks)
    S.queue = q
    S.cfg = FakeCfg({"live_max_minutes": global_min, "download_dir": tempfile.mkdtemp(prefix="md_live_")})
    S.log_mgr = FakeLog()
    S._load_live_monitors = lambda: monitors
    patched = []
    S._patch_live_monitor = lambda mid, **f: patched.append((mid, f)) or True
    try:
        S._live_recording_tick()
    finally:
        S.queue = REAL_QUEUE
        S.cfg = REAL_CFG
        S._load_live_monitors = REAL_LOAD_MON
        S._patch_live_monitor = REAL_PATCH
    return q.ended, patched


# ---------- A 判定口径：谁说了算 ----------
ck("A1 任务自己设了时长就按任务", S._live_effective_minutes(90, 30) == 90)
ck("A2 任务没设（0/None）才退回全局默认", S._live_effective_minutes(0, 30) == 30)
ck("A3 两边都没设 = 不限时长", S._live_effective_minutes(None, 0) == 0)
ck("A4 负数按不限处理，不能变成「立刻收掉」", S._live_effective_minutes(-5, -1) == 0)
ck("A5 超过上限的截到 1440", S._live_effective_minutes(99999) == 1440, S._live_effective_minutes(99999))
ck("A6 脏值（字符串、空）不能让收尾崩", S._live_effective_minutes("abc", None) == 0)
ck("A7 数字字符串照样认（设置里存的是文本框时）", S._live_effective_minutes("45") == 45)

# ---------- B 手动录制：录满就收 ----------
t1 = mk_task("m1", "https://live.bilibili.com/1", started_ago_min=61, limit=60)
ended, patched = run_tick([], {"m1": t1}, 0)
ck("B1 手动录满 60 分钟被结束", ended and ended[0][0] == ["m1"], ended)
ck("B2 结束原因写的是「录满自动保存」，界面那行才不是说谎的",
   bool(ended) and "录满 60 分钟" in ended[0][1] and "自动结束并保存" in ended[0][1], ended)
ck("B3 手动录制不去改监控状态（它没有监控）", patched == [], patched)

t2 = mk_task("m2", "https://live.bilibili.com/2", started_ago_min=10, limit=60)
ended, _ = run_tick([], {"m2": t2}, 0)
ck("B4 没录满不动它", ended == [], ended)

t3 = mk_task("m3", "https://live.bilibili.com/3", started_ago_min=None, limit=60)
ended, _ = run_tick([], {"m3": t3}, 0)
ck("B5 还没开跑（没有 started_at）不能被一入队就收掉", ended == [], ended)

t4 = mk_task("m4", "https://live.bilibili.com/4", started_ago_min=9999, limit=0)
t5 = mk_task("m5", "https://live.bilibili.com/5", started_ago_min=9999, limit=None)
ended, _ = run_tick([], {"m4": t4, "m5": t5}, 0)
ck("B6 时长为 0 / 没传 = 不限，全局也是 0 时永远不收", ended == [], ended)

t6 = mk_task("m6", "https://live.bilibili.com/6", started_ago_min=121, limit=None)
ended, _ = run_tick([], {"m6": t6}, 120)
ck("B7 任务没设时长时吃全局默认（120 分钟）", ended and "120" in ended[0][1], ended)

t7 = mk_task("m7", "https://live.bilibili.com/7", started_ago_min=5, limit=10)
ended, _ = run_tick([], {"m7": t7}, 120)
ck("B8 任务设的短时长优先于全局默认", ended == [], ended)

# ---------- C 监控房间：原有语义不能坏 ----------
mon = [{"id": "r1", "url": "https://live.bilibili.com/8", "rec_task": "t8", "max_minutes": 30}]
t8 = mk_task("t8", "https://live.bilibili.com/8", started_ago_min=31, limit=30)
ended, patched = run_tick(mon, {"t8": t8}, 120)
ck("C1 房间录满照样收，且用的是房间的 30 分钟而不是全局 120",
   ended and ended[0][0] == ["t8"] and "30" in ended[0][1], ended)
ck("C2 房间收完要把自己置成「已录满并自动停止」，否则下播前会每 30 秒重开一场",
   bool(patched) and patched[0][0] == "r1" and patched[0][1].get("paused") is True, patched)

mon2 = [{"id": "r2", "url": "https://live.bilibili.com/9", "rec_task": "t9", "max_minutes": 45}]
t9 = mk_task("t9", "https://live.bilibili.com/9", started_ago_min=46, limit=0)
ended, patched = run_tick(mon2, {"t9": t9}, 0)
ck("C3 全局 0（不限）时房间的 45 分钟仍然生效",
   ended and ended[0][0] == ["t9"], ended)

mon3 = [{"id": "r3", "url": "https://live.bilibili.com/10", "rec_task": "t10", "max_minutes": 0}]
t10 = mk_task("t10", "https://live.bilibili.com/10", started_ago_min=200, limit=0)
t11 = mk_task("t11", "https://other.example/live", started_ago_min=200, limit=0)
ended, _ = run_tick(mon3, {"t10": t10, "t11": t11}, 180)
ck("C4 房间没设时长 → 吃全局 180，监控任务与手动任务一起收",
   sorted(x[0][0] for x in ended) == ["t10", "t11"], ended)

t12 = mk_task("t12", "https://live.bilibili.com/11", live=False, started_ago_min=9999, limit=1)
ended, _ = run_tick([], {"t12": t12}, 1)
ck("C5 普通下载任务绝不能被这套收尾误杀", ended == [], ended)

t13 = mk_task("t13", "https://live.bilibili.com/12", started_ago_min=9999, limit=1,
              status=S.TaskStatus.FINISHED.value)
ended, _ = run_tick([], {"t13": t13}, 0)
ck("C6 已经结束的直播不再重复结束", ended == [], ended)

# ---------- D 界面上的倒计时从哪来 ----------
S.cfg = FakeCfg({"live_max_minutes": 40})
try:
    td = mk_task("d1", "https://live.bilibili.com/13", started_ago_min=1, limit=90)
    d = td.to_dict()
    ck("D1 直播任务把生效时长带进 to_dict，界面才知道还剩几分钟", d.get("live_limit_min") == 90, d.get("live_limit_min"))
    td2 = mk_task("d2", "https://live.bilibili.com/14", started_ago_min=1, limit=None)
    ck("D2 任务没设时 to_dict 里是全局默认", td2.to_dict().get("live_limit_min") == 40)
    tn = mk_task("d3", "https://example.com/v", live=False, started_ago_min=1)
    ck("D3 非直播任务不带这个字段", "live_limit_min" not in tn.to_dict())
finally:
    S.cfg = REAL_CFG

# ---------- E 入队时的取值范围 ----------
ck("E1 设置接口把时长夹进 0–1440",
   "live_max_minutes" in S.ConfigBody.model_fields
   and 'data["live_max_minutes"] = max(0, min(_LIVE_MAX_MINUTES' in SRC)
ck("E2 入队接口对单场时长做同样的夹取",
   'opts["live_max_minutes"] = max(0, min(_LIVE_MAX_MINUTES, lm))' in SRC)
ck("E3 默认值是 0（不限），升级后不该凭空把人家的直播截断",
   S.ConfigManager.DEFAULTS.get("live_max_minutes") == 0, S.ConfigManager.DEFAULTS.get("live_max_minutes"))
ck("E4 手动入队会把这一场设的分钟数带进任务",
   S.AddUrlsBody.model_fields["live_max_minutes"].default is None)

# ---------- F 接线：这条轮询以前只在「有监控房间」时跑 ----------
seg = SRC[SRC.index("def start_live_monitor_scheduler"):SRC.index("def start_telegram_command_poller")]
between = seg[seg.index("api_live_monitor_scan()"):seg.index("_live_recording_tick()")]
ck("F1 收尾检查挪出了「有监控才扫」的分支：一个监控房间都没有时也要跑",
   "\n                try:" in between, repr(between))
ck("F2 监控开录时把房间时长写进任务，房间列表与任务卡显示同一口径",
   '"live_max_minutes": int(m.get("max_minutes") or 0)' in SRC)
ck("F3 自动结束的原因文案会落到任务卡上（error_msg 用传入的 reason，不是写死的「用户结束录制」）",
   "t.error_msg = reason" in SRC and "def end_live_tasks(self, ids: List[str] = None, reason" in SRC)
ck("F4 结束直播的公开接口不传 reason 时仍是「用户结束录制」",
   'reason: str = "用户结束录制"' in SRC)

# ---------- G 前端接线 ----------
_BIND = 'v-model="settings.live_max_minutes"'
ck("G1 直播页有时长选择框，且直接绑设置里那一格（页面级影子已在 #36 删掉）",
   INDEX.count(_BIND) >= 2 and "liveRecordMinutes" not in INDEX,
   f"bind={INDEX.count(_BIND)} shadow={'liveRecordMinutes' in INDEX}")
ck("G2 「开始录制」把时长发给后端", "live_max_minutes: mm," in INDEX)
ck("G3 任务卡显示倒计时", "liveAutoSaveText(t)" in INDEX and "live_limit_min" in INDEX)
ck("G4 设置页有默认时长项，且与房间设置同用 0 = 跟随这一口径",
   'v-model="settings.live_max_minutes"' in INDEX
   and "0 = 跟随「设置」里的默认最长录制时长" in INDEX)
ck("G5 新增的名字都在 setup 返回清单里（漏了就是界面空白，且没有任何报错）",
   all(n in INDEX[INDEX.rindex("return {"):] for n in
       ["liveDefaultMinutesText", "liveAutoSaveText"]))
ck("G6 提示里的「当前默认」不是写死的字符串", "liveDefaultMinutesText" in INDEX)

print(f"\nTOTAL {TOTAL}  FAILED {len(FAILED)}"
      + ("" if not FAILED else "  ==> " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
