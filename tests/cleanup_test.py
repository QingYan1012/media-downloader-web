#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按龄清理（#31）离线自检：天数口径、四组名单、护住占用、干跑无副作用、名单指纹、
   回收目录一轮（挪出去 → 到期真删 → 放回原位）、自动那一趟的范围、闹钟排期、界面静态断言。

只写 %TEMP%，不碰真实下载目录、config.json 与 library_cache.json。
跑法：PYTHONIOENCODING=utf-8 python tests/cleanup_test.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

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


class FakeCfg:
    def __init__(self, data):
        self.data = data
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))

    def texts(self):
        return [m for _l, m in self.rows]

    def count(self, needle):
        return sum(1 for m in self.texts() if needle in m)


class FakeQueue:
    """只用到 tasks 这一面：护住哪些路径全靠它。"""

    def __init__(self, tasks=None):
        self.tasks = tasks or {}

    def add(self, tid, status="downloading", filepath="", result_dir="", seeding=False):
        self.tasks[tid] = SimpleNamespace(id=tid, status=status, filepath=filepath,
                                          result_dir=result_dir, seeding=seeding)


TMP = Path(tempfile.mkdtemp(prefix="md_cleanup_"))
DL = TMP / "downloads"
APP = TMP / "app"
STATE = TMP / "app"          # 常态：状态目录就是程序目录，两个根会数到同一批文件
COOK = APP / "cookies"
for d in (DL, APP, COOK):
    d.mkdir(parents=True, exist_ok=True)

BASE_CFG = {
    "download_dir": str(DL),
    "cleanup_enabled": False,
    "cleanup_log_days": 7,
    "cleanup_backup_days": 0,
    "cleanup_download_days": 0,
    "cleanup_trash_days": 30,
}

_REAL = (S.cfg, S.log_mgr, S.queue, S.CLEANUP_STATE_FILE, S.LIBRARY_CACHE,
         S.APP_DIR, S.STATE_DIR, S.COOKIES_DIR, S.DEFAULT_DOWNLOAD_DIR, S.LOG_FILE)
CFG = FakeCfg(dict(BASE_CFG))
LOGS = FakeLog()


def touch(path: Path, days_ago: float = 0.0, content: str = "x", mtime_abs: float = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts = mtime_abs if mtime_abs is not None else (time.time() - days_ago * 86400.0)
    os.utime(path, (ts, ts))
    return path


def age_of(path: Path) -> float:
    return round((time.time() - path.stat().st_mtime) / 86400.0, 1)


def reset_tree():
    """把两棵树清干净重来，别让上一段的文件混进下一段的名单。"""
    for d in (DL, APP):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    (COOK).mkdir(parents=True, exist_ok=True)
    CFG.data = dict(BASE_CFG)
    LOGS.rows.clear()
    S.queue = FakeQueue()


def plan():
    return S._cl_plan()


def group_rows(p, g):
    return p["groups"][g]["rows"]


try:
    S.cfg = CFG
    S.log_mgr = LOGS
    S.queue = FakeQueue()
    S.CLEANUP_STATE_FILE = TMP / "cleanup_state.json"
    S.LIBRARY_CACHE = TMP / "library_cache.json"
    S.APP_DIR = APP
    S.STATE_DIR = STATE
    S.COOKIES_DIR = COOK
    S.DEFAULT_DOWNLOAD_DIR = DL
    S.LOG_FILE = APP / "app.log"

    # ---------------- A 默认值：这一路默认全关
    src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    d = S.ConfigManager.DEFAULTS
    ck("A1 按龄清理默认关", d.get("cleanup_enabled") is False, str(d.get("cleanup_enabled")))
    ck("A2 日志归档默认 7 天（沿用原来那个写死的值）", d.get("cleanup_log_days") == 7, str(d.get("cleanup_log_days")))
    ck("A3 编辑备份默认不碰", d.get("cleanup_backup_days") == 0, str(d.get("cleanup_backup_days")))
    ck("A4 下载成品默认不碰 —— 这一档只有人点过才动", d.get("cleanup_download_days") == 0, str(d.get("cleanup_download_days")))
    ck("A5 回收目录默认待 30 天再真删", d.get("cleanup_trash_days") == 30, str(d.get("cleanup_trash_days")))
    ck("A6 五键都在 DEFAULTS 里（不在的话配置根本存不住）",
       all(k in d for k in ("cleanup_enabled", "cleanup_log_days", "cleanup_backup_days",
                            "cleanup_download_days", "cleanup_trash_days")))
    ck("A7 状态文件落在状态目录，不跟着包走", "CLEANUP_STATE_FILE = STATE_DIR / \"cleanup_state.json\"" in src)

    pack = (Path(__file__).resolve().parents[1] / "pack_release.py").read_text(encoding="utf8", errors="ignore")
    ck("A8 排除正则里有它（转义写法，字面量计数抓不到）", r"cleanup_state\.json" in pack)
    ck("A9 排除规则 + 试跑后清理 + 出包泄漏自检三处都在", pack.count("cleanup_state") >= 3, str(pack.count("cleanup_state")))

    # A10~A12 是**语义**断言，不是「名字在不在表里」：分段拼正则时多打一个 `|` 会造出一个空分支，
    # 空分支匹配任意字符串 —— 排除表当场反变成「全排除」，包里的 static/ 变空目录，界面整个不见了，
    # 而上面那种字面量计数一条条全绿。这一轮真就是这么出过一次包，靠解压核对才发现。
    import pack_release as PK
    _must_in = ("index.html", "server.py", "README.md", "README.en.md", "CHANGELOG.md", "CHANGELOG.en.md",
                "详细功能介绍.md", "music_search.py", "favicon.svg")
    ck("A10 随包文件一个都不许被排除表判掉（判掉就等于包里没界面）",
       not [n for n in _must_in if PK.EXCLUDE_FILE_RE.search(n)],
       str([n for n in _must_in if PK.EXCLUDE_FILE_RE.search(n)]))
    _must_out = ("config.json", "history.json", "notify_outbox.json", "login_state.json",
                 "cookiecloud_state.json", "app.log", "config.json.bak-1712345678",
                 "mcp_calls.log", "pack_release.py", "x.pyc")
    ck("A11 该挡的还挡着（本机状态 / 带时间的密钥备份 / 日志 / 打包脚本自己）",
       not [n for n in _must_out if not PK.EXCLUDE_FILE_RE.search(n)],
       str([n for n in _must_out if not PK.EXCLUDE_FILE_RE.search(n)]))
    ck("A12 出包前有「必进包文件在场」自检，缺文件直接中止不许压成 zip",
       "def check_present" in pack and "check_present(dst)" in pack)

    # ---------------- B 天数口径：0 就是不碰，越界收到合理区间
    p = plan()
    ck("B1 天数填 0 的组一句「这一档不碰」，且不去翻盘",
       p["groups"]["backups"]["note"].startswith("这一档天数填的 0") and p["groups"]["backups"]["scanned"] == 0,
       p["groups"]["backups"]["note"])
    ck("B2 关着的时候也照样能算名单（关的是自动，不是手工那一路）", p["enabled"] is False and "hash" in p)
    CFG.data["cleanup_log_days"] = 99999
    ck("B3 天数越界被收进 0–3650", S._cl_cfg()["log_days"] == 3650, str(S._cl_cfg()["log_days"]))
    CFG.data["cleanup_log_days"] = -5
    ck("B4 负数收成 0（就是不碰，而不是删光）", S._cl_cfg()["log_days"] == 0, str(S._cl_cfg()["log_days"]))
    CFG.data["cleanup_log_days"] = "abc"
    ck("B5 填了非数字退回默认 7，不抛", S._cl_cfg()["log_days"] == 7, str(S._cl_cfg()["log_days"]))
    CFG.data.update(BASE_CFG)

    # ---------------- C 四组各按各的名字取文件
    reset_tree()
    old_log = touch(APP / "app-2026-01-01.log", 40, "日志\n" * 5)
    new_log = touch(APP / "app-2026-10-10.log", 1, "日志\n")
    today_log = touch(APP / "app.log", 40, "正在写的这份不能动\n")
    cfg_backup = touch(COOK / "cookies.txt.bak-20260101-030303", 40, "cookie 备份")
    app_backup = touch(DL / "sub.srt.bak-20260101000000", 40, "字幕备份")
    fresh_backup = touch(DL / "new.srt.bak-20261010000000", 1, "昨天的备份")
    old_mp4 = touch(DL / "视频A.mp4", 40, "m" * 10)
    new_mp4 = touch(DL / "视频B.mp4", 1, "n" * 10)
    old_srt = touch(DL / "视频A.srt", 40, "字幕")
    part_file = touch(DL / "视频C.mp4.part", 40, "半成品")
    dot_file = touch(DL / ".hidden.txt", 40, "点开头")
    old_txt = touch(DL / "说明.txt", 40, "不是成品")
    CFG.data.update({"cleanup_log_days": 7, "cleanup_backup_days": 7, "cleanup_download_days": 7})
    p = plan()
    lg = [r["name"] for r in group_rows(p, "logs")]
    ck("C1 日志组只认 app-日期.log 这种归档", lg == ["app-2026-01-01.log"], str(lg))
    ck("C2 正在写的 app.log 不在名单里", "app.log" not in lg)
    ck("C3 归档的 rel 带着文件名，标签是「日志归档」",
       p["groups"]["logs"]["label"] == "日志归档" and group_rows(p, "logs")[0]["hard"] is True)
    bk = sorted(r["name"] for r in group_rows(p, "backups"))
    ck("C4 备份组认 .bak-<时间>，跨下载目录与 cookies 目录都收",
       bk == ["cookies.txt.bak-20260101-030303", "sub.srt.bak-20260101000000"], str(bk))
    ck("C5 刚留的备份（1 天）不算过期", "new.srt.bak-20261010000000" not in bk)
    dl = sorted(r["name"] for r in group_rows(p, "downloads"))
    ck("C6 下载组成品按扩展名认（视频与字幕同侧）", dl == ["视频A.mp4", "视频A.srt"], str(dl))
    ck("C7 .part 半成品不进名单（那是 /api/cleanup-parts 的活）", "视频C.mp4.part" not in dl)
    ck("C8 点开头的文件不列", ".hidden.txt" not in [r["name"] for r in group_rows(p, "downloads")])
    ck("C9 非媒体扩展名不列（说明.txt 是用户自己的东西）", "说明.txt" not in dl)
    ck("C10 年龄按 mtime 算：40 天前的文件报 40 上下",
       abs(group_rows(p, "downloads")[0]["age_days"] - 40) <= 0.2, str(group_rows(p, "downloads")[0]["age_days"]))
    ck("C11 名单里的下载成品给的是相对路径（界面上看得清在哪一层）",
       all("\\" not in r["rel"].rstrip("\\") or r["rel"].count("\\") < 3 for r in group_rows(p, "downloads")),
       str([r["rel"] for r in group_rows(p, "downloads")]))
    ck("C12 下载那组标的是「挪进回收目录」，不是直接删",
       group_rows(p, "downloads")[0]["hard"] is False and p["groups"]["downloads"]["hard"] is False)
    ck("C13 干跑一个文件都没动", old_log.exists() and cfg_backup.exists() and old_mp4.exists())
    ck("C14 每个文件都有 12 位 id（删除与还原都靠它点名）",
       len({r["id"] for r in group_rows(p, "downloads")}) == len(group_rows(p, "downloads"))
       and len(group_rows(p, "downloads")[0]["id"]) == 12)

    # ---------------- D 护住正在下、排队、暂停、稍后与做种
    reset_tree()
    dl_target = DL / "正在下.mp4"          # 下面 t1 那条占的就是它，连它的 .part 一起
    busy_new = touch(dl_target, 40, "downloading")
    seed_part = touch(DL / "另一集.mkv.part", 40, "part")
    seeding_dir = touch(DL / "种子目录" / "老片.mkv", 40, "seeding")
    idle_old = touch(DL / "早就下完.mp4", 40, "idle")
    q = S.queue = FakeQueue()
    q.add("t1", status=S.TaskStatus.DOWNLOADING.value, filepath=str(busy_new))
    q.add("t2", status=S.TaskStatus.QUEUED.value, filepath=str(DL / "排队中.mp4"))
    q.add("t3", status=S.TaskStatus.PAUSED.value, filepath=str(DL / "暂停中.mp4"))
    q.add("t4", status=S.TaskStatus.LATER.value, filepath=str(DL / "稍后再下.mp4"))
    q.add("t5", status=S.TaskStatus.FINISHED.value, filepath="", result_dir=str(DL / "种子目录"), seeding=True)
    q.add("t6", status=S.TaskStatus.FINISHED.value, filepath=str(DL / "早就下完.mp4"), seeding=False)
    CFG.data["cleanup_download_days"] = 7
    p = plan()
    names = sorted(r["name"] for r in group_rows(p, "downloads"))
    ck("D1 正在下的那条被护住", "正在下.mp4" not in names, str(names))
    ck("D2 做种中那一整个目录都被护住", "老片.mkv" not in names, str(names))
    ck("D3 护住的个数会上屏（不是悄悄少掉）", p["groups"]["downloads"]["busy_skipped"] == 2,
       str(p["groups"]["downloads"]["busy_skipped"]))
    ck("D4 下完且不做种的老文件照常列", "早就下完.mp4" in names, str(names))
    exact, prefixes = S._cl_busy()
    ck("D5 占用判定不看大小写与斜杠方向",
       S._cl_blocked(Path(str(busy_new).upper()), exact, prefixes)
       and S._cl_blocked(Path(str(seeding_dir).replace("\\", "/")), exact, prefixes))
    ck("D6 半成品名（正在下的那条 + .part）也在保护名单里：续传时它归同一任务",
       S._cl_norm(str(dl_target) + ".part") in exact, str(dl_target)[-30:])
    ck("D6b 与占用路径无关的 .part 不误护（那是 cleanup-parts 的活）",
       not S._cl_blocked(seed_part, exact, prefixes))
    class BrokenQueue:
        @property
        def tasks(self):
            raise RuntimeError("队列自己坏了")
    S.queue = BrokenQueue()
    ex7, pre7 = S._cl_busy()
    ck("D7 队列读不出来时不炸（宁可少护，也不能让整页 500）", ex7 == set() and pre7 == set(), str((ex7, pre7))[:60])
    S.queue = q

    # ---------------- E 干跑没有副作用
    reset_tree()
    touch(DL / "视频A.mp4", 40, "a")
    touch(APP / "app-2026-01-01.log", 40, "l")
    CFG.data["cleanup_download_days"] = 7
    CFG.data["cleanup_log_days"] = 7
    before = sorted(str(x.relative_to(TMP)) for x in TMP.rglob("*"))
    p1 = plan()
    p2 = plan()
    after = sorted(str(x.relative_to(TMP)) for x in TMP.rglob("*"))
    ck("E1 连看两次名单：磁盘上一个文件没动", before == after)
    ck("E2 同一份盘面上的指纹稳定（两次算出来一样）", p1["hash"] == p2["hash"], f"{p1['hash']} vs {p2['hash']}")
    ck("E3 干跑不写状态文件", not S.CLEANUP_STATE_FILE.exists())
    ck("E4 干跑也不写媒体库缓存", not S.LIBRARY_CACHE.exists())
    ck("E5 指纹 10 分钟有效（口径写死在后端常量里）", p1["ttl"] == S.CL_PLAN_TTL == 600, str(p1["ttl"]))

    # ---------------- F 删除必须先看过名单：三道拦阻
    reset_tree()
    touch(DL / "视频A.mp4", 40, "a")
    CFG.data["cleanup_download_days"] = 7
    try:
        S._cl_apply(["downloads"])
        ck("F1 没带指纹就拒绝", False, "居然放过去了")
    except S.HTTPException as e:
        ck("F1 没带指纹就拒绝（400 + 教他先点哪一下）", e.status_code == 400 and "先看名单" in str(e.detail), str(e.detail)[:60])
    try:
        S._cl_apply(["downloads"], expect_hash="deadbeefdeadbeef")
        ck("F2 指纹对不上就拒绝（409）", False, "居然放过去了")
    except S.HTTPException as e:
        ck("F2 指纹对不上就拒绝（409）", e.status_code == 409 and "对不上" in str(e.detail), str(e.detail)[:60])
    pr = plan()
    S._CL_PLAN["at"] = time.time() - (S.CL_PLAN_TTL + 5)
    try:
        S._cl_apply(["downloads"], expect_hash=pr["hash"])
        ck("F3 名单拖过 10 分钟就作废", False, "居然放过去了")
    except S.HTTPException as e:
        ck("F3 名单拖过 10 分钟就作废（409 里带分钟数）",
           e.status_code == 409 and "10 分钟" in str(e.detail), str(e.detail)[:60])
    S._CL_PLAN["at"] = time.time()
    pr4 = plan()
    try:
        S._cl_apply(["logs"], expect_hash=pr4["hash"])
        ck("F4 认识的组名不误伤（这一组空名单也走得通）", True)
    except S.HTTPException as e:
        ck("F4 认识的组名不误伤（这一组空名单也走得通）", False, str(e.detail)[:60])
    try:
        S._cl_apply(["nothing"], expect_hash=pr["hash"])
        ck("F5 组名瞎写要报错", False)
    except S.HTTPException as e:
        ck("F5 组名瞎写要报错（400 点名是哪个）", e.status_code == 400 and "nothing" in str(e.detail), str(e.detail)[:60])
    try:
        S._cl_apply([], expect_hash=pr["hash"])
        ck("F6 空组名等于没说", False)
    except S.HTTPException as e:
        ck("F6 空组名等于没说（400）", e.status_code == 400, str(e.detail)[:60])
    ck("F7 指纹不匹配时文件确实还在", (DL / "视频A.mp4").exists())

    # ---------------- G 回收目录一轮：挪出去、记账、媒体库忘掉它
    reset_tree()
    v1 = touch(DL / "剧集" / "老片.mp4", 40, "old")
    v2 = touch(DL / "老片2.mkv", 60, "older")
    side = touch(DL / "剧集" / "老片.srt", 40, "sub")
    S.LIBRARY_CACHE.write_text(json.dumps([
        {"path": str(v1), "name": "老片.mp4"},
        {"path": str(v2), "name": "老片2.mkv"},
        {"path": str(DL / "新片.mp4"), "name": "新片.mp4"},
    ]), encoding="utf-8")
    CFG.data["cleanup_download_days"] = 7
    pr = plan()
    r = S._cl_apply(["downloads"], expect_hash=pr["hash"])
    ck("G1 三个过期成品都挪走了", r["count"] == 3, f"{r['count']} / {r['errors']}")
    ck("G2 原位已经没有它们", not v1.exists() and not v2.exists() and not side.exists())
    trash = DL / S.CL_TRASH_DIRNAME
    ck("G3 回收目录建在下载目录里", trash.is_dir(), str(trash))
    ck("G4 回收目录保住相对路径（放回时看得出原来在哪一层）",
       (trash / "剧集" / "老片.mp4").is_file(), str(sorted(x.name for x in trash.rglob("*") if x.is_file())))
    ck("G5 账本单独一份，且不当成成品列",
       (trash / "manifest.json").is_file()
       and "manifest.json" not in [x["name"] for x in plan()["groups"]["trash"]["rows"]])
    man = json.loads((trash / "manifest.json").read_text(encoding="utf-8"))["entries"]
    ck("G6 账本每条记着原位置、进目录的时间与大小",
       all({"orig", "moved", "moved_at", "bytes", "id", "group"} <= set(x) for x in man), str(man[:1]))
    ck("G7 三条都记上了", len(man) == 3, str(len(man)))
    ck("G8 进目录用的是「挪走那一刻」的时间，不是文件原本的 mtime",
       all(x["moved_at"] > time.time() - 120 for x in man))
    cached = json.loads(S.LIBRARY_CACHE.read_text(encoding="utf-8"))
    ck("G9 媒体库缓存把挪走的三条摘掉", len(cached) == 1 and cached[0]["name"] == "新片.mp4", str(cached))
    ck("G10 日志里记了这一趟（多少体积、去了哪儿）",
       LOGS.count("[清理]") >= 1 and any("回收目录" in m for m in LOGS.texts()), str(LOGS.texts()[-1:])[:120])
    ck("G11 回执里说清了每个文件挪去哪、原位置",
       all({"orig", "moved", "name", "bytes"} <= set(x) for x in r["moved"]), str(r["moved"][:1]))
    st = S._cl_state()
    ck("G12 状态落盘：上次手动时间与条数在",
       st.get("last_manual", {}).get("moved") == 3 and str(st["last_manual"]["at"]).startswith("20"),
       str(st.get("last_manual")))
    ck("G13 自动那一趟的时间没被顺手写（这轮是手点的）", "last_auto" not in st or not st["last_auto"])
    # 再放一份同名老片，回收目录里不能把旧的那条盖掉
    touch(DL / "剧集" / "老片.mp4", 40, "brand new old")
    pr = plan()
    r2 = S._cl_apply(["downloads"], expect_hash=pr["hash"])
    ck("G14 回收目录里重名时往后加序号，不盖掉已经收着的那条",
       r2["count"] == 1 and len(list(trash.rglob("老片.mp4*"))) == 2,
       str([x.name for x in trash.rglob("老片*")]))
    ck("G15 名单里现在能看到回收目录这一组（0 天不会列，因为还没到期）",
       plan()["groups"]["trash"]["count"] == 0, str(plan()["groups"]["trash"]["count"]))

    # ---------------- H 到期真删：回收目录按进目录的天数走
    CFG.data["cleanup_trash_days"] = 30
    man = json.loads((trash / "manifest.json").read_text(encoding="utf-8"))["entries"]
    aged = [x for x in man if x["name"] == "老片.mp4"][0]
    aged["moved_at"] = time.time() - 45 * 86400.0
    (trash / "manifest.json").write_text(json.dumps({"entries": man}), encoding="utf-8", newline="\n")
    p = plan()
    tr = p["groups"]["trash"]
    ck("H1 待够 30 天的那条被列出来（按账本里挪进来的时间算）",
       tr["count"] == 1 and tr["rows"][0]["name"] == "老片.mp4", str([r["name"] for r in tr["rows"]]))
    ck("H2 这一组写的是「直接删」（它已经在回收目录里了）", tr["hard"] is True and tr["rows"][0]["hard"] is True)
    ck("H3 名单给的是进回收目录的时间，不是文件原本的 mtime",
       tr["rows"][0]["age_days"] >= 44.9 and abs(tr["rows"][0]["age_days"] - 45) < 0.3, str(tr["rows"][0]["age_days"]))
    ck("H4 没到期的那些还躺着", len([x for x in p["groups"]["trash"]["rows"]]) == 1)
    r = S._cl_apply(["trash"], expect_hash=p["hash"])
    ck("H5 真删掉了那一条", r["deleted"] and r["count"] == 1, str(r["count"]))
    ck("H6 账本跟着缩一条", len(S._cl_manifest()) == len(man) - 1)
    ck("H7 删完把空壳目录收掉", all(d.is_dir() and list(d.iterdir())
                                   for d in trash.rglob("*") if d.is_dir()), "留了空目录")
    # 没账的文件（手工丢进回收目录的）按 mtime 兜底，还原时老实说不知道原位置
    orphan = touch(trash / "手工丢的.mp4", 45, "orphan")
    p = plan()
    ck("H8 回收目录里没有账的文件也按 mtime 列出来",
       any(r["name"] == "手工丢的.mp4" for r in p["groups"]["trash"]["rows"]))
    row = [r for r in p["groups"]["trash"]["rows"] if r["name"] == "手工丢的.mp4"][0]
    ck("H9 没有账就不假装知道原位置", "orig" not in row or not row.get("orig"), str(row))

    # ---------------- I 还原
    reset_tree()
    back = touch(DL / "剧集" / "要还原.mp4", 40, "content")
    CFG.data["cleanup_download_days"] = 7
    pr = plan()
    S._cl_apply(["downloads"], expect_hash=pr["hash"])
    ent = S._cl_manifest()[0]
    ck("I1 回收目录里能列出可还原的条目（带原位置）",
       len(S._cl_restore_trash()) == 1 and S._cl_restore_trash()[0]["orig"] == str(back), str(S._cl_restore_trash()[:1]))
    rr = S._cl_restore([ent["id"]])
    ck("I2 放回原位了", back.exists() and back.read_text(encoding="utf-8") == "content", str(rr["count"]))
    ck("I3 放回后账本清空", S._cl_manifest() == [])
    ck("I4 回收目录里那个文件不在了", not (DL / S.CL_TRASH_DIRNAME / "剧集" / "要还原.mp4").exists())
    ck("I5 回执一句话讲清放回了几个", "放回原位 1 个" in rr["message"], rr["message"][:60])
    os.utime(back, None)   # 放回去的这份算「刚动过」，别让它带着 40 天的旧 mtime 混进下面的名单
    # 原位置被占：不覆盖
    touch(DL / "冲突.mp4", 40, "old")
    pr = plan()
    S._cl_apply(["downloads"], expect_hash=pr["hash"])
    ent = S._cl_manifest()[0]
    (DL / "冲突.mp4").write_text("别人新下的一份", encoding="utf-8")
    rr = S._cl_restore([ent["id"]])
    ck("I6 原位置已经有同名文件就不覆盖", (DL / "冲突.mp4").read_text(encoding="utf-8") == "别人新下的一份")
    ck("I7 被拒的那条要说清原因，并留在回收目录里",
       bool(rr["refused"]) and "没覆盖" in rr["refused"][0]["why"] and bool(S._cl_manifest()),
       json.dumps(rr, ensure_ascii=False)[:200])
    touch(DL / "整层没了" / "深层.mp4", 40, "deep")
    pr = plan()
    S._cl_apply(["downloads"], expect_hash=pr["hash"])
    shutil.rmtree(DL / "整层没了", ignore_errors=True)
    ent3 = [x for x in S._cl_manifest() if x["name"] == "深层.mp4"][0]
    rr = S._cl_restore([ent3["id"]])
    ck("I8 原位置整层目录没了就说清，不硬造一条路径去写",
       bool(rr["refused"]) and "目录已经不存在" in rr["refused"][0]["why"] and not rr["restored"],
       json.dumps(rr, ensure_ascii=False)[:160])
    (DL / "整层没了").mkdir(parents=True)
    rr = S._cl_restore([ent3["id"]])
    ck("I9 拒过的那条账还在，腾开位置后还能放回去",
       rr["count"] == 1 and (DL / "整层没了" / "深层.mp4").is_file(), json.dumps(rr, ensure_ascii=False)[:160])
    try:
        S._cl_restore([])
        ck("I10 空 ids 要报错", False)
    except S.HTTPException as e:
        ck("I10 空 ids 要报错（400）", e.status_code == 400, str(e.detail)[:40])
    ck("I11 瞎写的 id 不会误伤别人（一条都没还原）",
       S._cl_restore(["ffffffffffff"])["count"] == 0)
    # 账本里指向一个已经不在回收目录里的文件
    man = S._cl_manifest()
    if man:
        man.append({"id": "ghostghost01", "orig": str(DL / "没了.mp4"), "moved": "没了.mp4",
                    "moved_at": time.time(), "bytes": 1, "name": "没了.mp4", "group": "downloads"})
        (trash / "manifest.json").parent.mkdir(parents=True, exist_ok=True)
        S._cl_manifest_save(man)
        ck("I12 账本里指向不存在文件的条目不会被列成可还原",
           all(x["id"] != "ghostghost01" for x in S._cl_restore_trash()))

    # ---------------- J 自动那一趟的范围
    reset_tree()
    ck("J1 自动清单里没有下载成品这一组", "downloads" not in S.CL_AUTO_GROUPS, str(S.CL_AUTO_GROUPS))
    ck("J2 自动清单只有日志/备份/回收目录",
       set(S.CL_AUTO_GROUPS) == {"logs", "backups", "trash"}, str(S.CL_AUTO_GROUPS))
    old_dl = touch(DL / "自动也别碰我.mp4", 400, "keep")
    old_log = touch(APP / "app-2025-01-01.log", 400, "gone")
    old_bak = touch(DL / "字幕.srt.bak-20250101000000", 400, "gone")
    CFG.data.update({"cleanup_enabled": False, "cleanup_log_days": 7,
                     "cleanup_backup_days": 7, "cleanup_download_days": 7})
    r = S._cl_auto_pass()
    ck("J3 开关没开：自动这一趟直接跳过，一个文件不动",
       r.get("count") == 0 and old_log.exists() and old_dl.exists(), str(r))
    CFG.data["cleanup_enabled"] = True
    r = S._cl_auto_pass()
    ck("J4 开着之后日志归档与备份被清掉", not old_log.exists() and not old_bak.exists(), str(r)[:120])
    ck("J5 下载目录里的成品一个都没被自动碰", old_dl.exists())
    ck("J6 自动这一趟不看名单指纹，清的哪几组由服务端圈（绝不含 downloads）",
       r["count"] == 2 and set(r["groups"]) == {"logs", "backups", "trash"}
       and "downloads" not in r["groups"], json.dumps(r, ensure_ascii=False)[:140])
    ck("J7 状态里记的是 last_auto（界面要分开显示两件事）",
       bool(S._cl_state().get("last_auto")) and S._cl_state()["last_auto"]["by"] == "auto", str(S._cl_state())[:120])
    ck("J8 日志里点名这是自动那一趟", any("自动一趟" in m for m in LOGS.texts()), str(LOGS.texts()[-1:])[:100])
    CFG.data.update({"cleanup_log_days": 0, "cleanup_backup_days": 0, "cleanup_trash_days": 0})
    r = S._cl_auto_pass()
    ck("J9 三档天数都填 0：自动这趟什么都不做", r.get("count") == 0 and "0" in str(r.get("skipped")), str(r))
    keep = touch(DL / "开着也别删我.mp4", 400, "keep")
    CFG.data["cleanup_download_days"] = 1
    S._cl_auto_pass()
    ck("J10 就算下载那一档填了天数，自动这趟也不碰它", keep.exists())
    # 自动这趟挪走的备份也要从媒体库缓存里摘掉，否则媒体库继续显示一份不存在的
    reset_tree()
    b1 = touch(DL / "字幕.srt.bak-20250101000000", 400, "bk")
    S.LIBRARY_CACHE.write_text(json.dumps([{"path": str(b1), "name": b1.name},
                                           {"path": str(DL / "别的.mp4"), "name": "别的.mp4"}]),
                               encoding="utf-8")
    CFG.data.update({"cleanup_enabled": True, "cleanup_log_days": 0, "cleanup_backup_days": 7,
                     "cleanup_download_days": 0, "cleanup_trash_days": 0})
    S._cl_auto_pass()
    left = json.loads(S.LIBRARY_CACHE.read_text(encoding="utf-8"))
    ck("J11 自动这趟挪走的备份也从媒体库缓存里摘掉（不出现幽灵行）",
       len(left) == 1 and left[0]["name"] == "别的.mp4", json.dumps(left, ensure_ascii=False)[:120])
    ck("J12 挪去的是回收目录，不是直接没了", (DL / S.CL_TRASH_DIRNAME / b1.name).is_file())
    ck("J13 状态里自动那趟记的组名没有 downloads",
       "downloads" not in (S._cl_state().get("last_auto") or {}).get("groups", []),
       str((S._cl_state().get("last_auto") or {}).get("groups")))

    # ---------------- K 启动时那趟日志归档跟着设置走
    reset_tree()
    a400 = touch(APP / "app-2025-01-01.log", 400, "x")
    a20 = touch(APP / "app-2025-06-01.log", 20, "x")
    a3 = touch(APP / "app-2026-10-10.log", 3, "x")
    CFG.data.update({"cleanup_enabled": False})
    ck("K1 关着时仍按原来的 7 天：20 天前那份照删（老行为不变）",
       S._prune_old_logs() == 2 and a3.exists(), str(a3.exists()))
    reset_tree()
    a400 = touch(APP / "app-2025-01-01.log", 400, "x")
    a20 = touch(APP / "app-2025-06-01.log", 20, "x")
    a3 = touch(APP / "app-2026-10-10.log", 3, "x")
    touch(APP / "app.log", 400, "正在写的")
    CFG.data.update({"cleanup_enabled": True, "cleanup_log_days": 30})
    ck("K2 开着就按填的 30 天：20 天前那份留着", S._prune_old_logs() == 1 and a20.exists(), str(a20.exists()))
    CFG.data["cleanup_log_days"] = 0
    a400b = touch(APP / "app-2025-01-02.log", 400, "x")
    ck("K3 天数填 0 = 这一档不碰，启动时也不删", S._prune_old_logs() == 0 and a400b.exists())
    CFG.data["cleanup_enabled"] = False
    ck("K4 关掉之后退回默认口径（写死的 7 天，跟这台机器以前的行为一致）",
       S._prune_old_logs() >= 1 and not a400b.exists(), str(a400b.exists()))
    ck("K5 正在写的 app.log 永远不在归档口径里", (APP / "app.log").exists())

    # ---------------- L 闹钟与补跑
    now = time.time()
    nxt = S._cl_next_wake_ts(now)
    ck("L1 闹钟排的是下一个每天那个点（一定在将来）", nxt > now, str(round(nxt - now, 1)))
    ck("L2 距今不超过 24 小时", nxt - now <= 86400 + 2, str(round(nxt - now, 1)))
    lt = time.localtime(nxt)
    ck("L3 落在那一天的 03:05", (lt.tm_hour, lt.tm_min) == (S.CL_AUTO_HOUR, S.CL_AUTO_MIN), f"{lt.tm_hour}:{lt.tm_min}")
    one = S._cl_next_wake_ts(nxt + 1)
    ck("L4 刚响过就顺延到明天同一个点", round((one - nxt) / 3600) == 24, str(round((one - nxt) / 3600, 2)))
    CFG.data.update({"cleanup_enabled": True, "cleanup_log_days": 7, "cleanup_backup_days": 0,
                     "cleanup_trash_days": 30, "cleanup_download_days": 0})
    S._cl_state_save({})
    if S.CLEANUP_STATE_FILE.exists():
        S.CLEANUP_STATE_FILE.unlink()
    past_target_hint = "（现在几点决定该不该补）"
    if S.CLEANUP_STATE_FILE.exists():
        S.CLEANUP_STATE_FILE.unlink()
    due_now = S._cl_auto_due()
    ltn = time.localtime(now)
    should = now >= time.mktime((ltn.tm_year, ltn.tm_mon, ltn.tm_mday,
                                 S.CL_AUTO_HOUR, S.CL_AUTO_MIN, 0, 0, 0, -1))
    ck("L5 到点了且今天没跑过才补，还没到点就不补" + past_target_hint,
       due_now == should, f"due={due_now} 现在={ltn.tm_hour}:{ltn.tm_min:02d} 该到={should}")
    st = S._cl_state()
    st["auto_date"] = time.strftime("%Y-%m-%d")
    S.CLEANUP_STATE_FILE.write_text(json.dumps(st), encoding="utf-8")
    ck("L6 今天已经跑过就不补", S._cl_auto_due() is False, str(S._cl_state())[:80])
    st = S._cl_state()
    st.pop("auto_date", None)
    st["last_auto"] = {"at": time.strftime("%Y-%m-%d 03:05:00")}
    S.CLEANUP_STATE_FILE.write_text(json.dumps(st), encoding="utf-8")
    ck("L7 状态里今天的时间戳也算跑过", S._cl_auto_due() is False)
    CFG.data["cleanup_enabled"] = False
    ck("L8 关着的时候永远不补", S._cl_auto_due() is False)
    ck("L9 闹钟本身不受开关影响（开着再关也不用重排逻辑）",
       S._CL_TIMER["timer"] is None or S._CL_TIMER["timer"].is_alive())

    # ---------------- M 界面静态断言：文案要说清三条口径
    html = (Path(__file__).resolve().parents[1] / "static" / "index.html").read_text(encoding="utf-8")
    # 这一张卡的文案搬进了词表（#55）：index.html 里只剩 tr('settings.cl*')，字在 static/i18n.js 里。
    # 所以每条都判两件事：界面上按这个键取词，词表中文那一份仍带着那句话。
    import re as _re  # noqa: E402
    _i18n = (Path(__file__).resolve().parents[1] / "static" / "i18n.js").read_text(encoding="utf-8")
    _zh = _i18n[_i18n.find("    zh: {"):_i18n.find("\n    en: {")]
    ZH = dict(_re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh))
    ck("M1 设置页有「按龄清理」这一张卡",
       """<div class="section-title">{{ tr('settings.cleanupTitle') }}</div>""" in html
       and ZH.get("settings.cleanupTitle") == "按龄清理")
    ck("M2 四个天数输入框都在（0 就是不碰）",
       html.count('v-model="cl.log_days"') == 1 and html.count('v-model="cl.download_days"') == 1
       and html.count('v-model="cl.backup_days"') == 1 and html.count('v-model="cl.trash_days"') == 1)
    ck("M3 开关那句写明了自动只碰哪三样", """{{ tr('settings.clOnBold') }}""" in html
       and "日志归档、编辑备份、回收目录里到期的" in ZH.get("settings.clOnBold", ""))
    ck("M4 明确写了年龄按 mtime", """<b>{{ tr('settings.clMtimeWord') }}</b>{{ tr('settings.clRule1Tail') }}""" in html
       and ZH.get("settings.clMtimeWord") == "mtime"
       and "最后一次被动过的时间" in ZH.get("settings.clRule1Tail", ""))
    ck("M5 有「先看名单」与「按名单删除」两个按钮（顺序就是口径）",
       html.index("""@click="previewCleanup">{{ tr('settings.clPreviewBtn') }}""")
       < html.index("""@click="runCleanup">{{ tr('settings.clRunBtn') }}""")
       and ZH.get("settings.clPreviewBtn") == "先看名单"
       and ZH.get("settings.clRunBtn") == "按名单删除",
       "按钮文案在词表里，界面上按键取词")
    ck("M6 「按名单删除」在没有名单或名单过期时是灰的",
       ':disabled="!clPlan || clPlanStale"' in html)
    ck("M7 有「看回收目录」与放回原位的入口",
       """@click="loadCleanupTrash">{{ tr('settings.clTrashBtn') }}""" in html
       and """@click="restoreAllTrash">{{ tr('settings.clRestoreAllBtn') }}""" in html
       and ZH.get("settings.clTrashBtn") == "看回收目录"
       and "放回原位" in ZH.get("settings.clRestoreAllBtn", ""))
    ck("M8 名单里每组都标了是直接删还是挪进回收目录",
       """{{ g.hard ? tr('settings.clHardDelete') : tr('settings.clMoveToTrash') }}""" in html
       and ZH.get("settings.clHardDelete") == "直接删"
       and ZH.get("settings.clMoveToTrash") == "挪进回收目录")
    ck("M9 没逐条列出的那部分是报数，不是不说", """{{ tr('settings.clHiddenNote'""" in html
       and "没逐条列出来" in ZH.get("settings.clHiddenNote", ""))
    ck("M10 护住进行中任务这件事上屏了", """{{ tr('settings.clProtectHint') }}""" in html
       and "正在下载、排队、暂停/稍后，以及还在做种" in ZH.get("settings.clProtectHint", ""))
    ck("M11 半成品仍归原来那个按钮，文案不抢活",
       "清理临时文件" in html or "cleanup-parts" in html)
    ck("M12 四个写接口都有中文动作名（日志里不说裸路径）",
       all(k in html for k in ("/api/cleanup/account'", "/api/cleanup/preview'", "/api/cleanup/run'", "/api/cleanup/restore'")))
    ck("M13 前端把 ttl 交给后端（不自己另写一个 600）",
       "clPlanTimer = setTimeout" in html and "Number(d.ttl) || 600" in html)
    ck("M14 设置页进来就读这张卡的读数", "loadCleanup()" in html)
    ck("M15 读接口是 GET（切页面不该往日志里堆行）",
       "await api('/api/cleanup')" in html and "await api('/api/cleanup/trash')" in html)

    # ---------------- N 端点层：参数口径与令牌边界
    reset_tree()
    touch(DL / "端点.mp4", 40, "e")
    CFG.data["cleanup_download_days"] = 7
    out = S.api_cleanup_get()
    ck("N1 GET 给的是当前设置 + 目录 + 上次跑的时间",
       set({"enabled", "log_days", "backup_days", "download_days", "trash_days",
            "download_dir", "trash_dir", "trash_count", "last_auto", "last_manual",
            "auto_groups", "labels"}) <= set(out), str(sorted(out))[:160])
    ck("N2 GET 里绝不出现任何令牌/口令", "token" not in out and "secret" not in out)
    body = S.CleanupAccountBody(enabled=True, log_days=14, backup_days=3, download_days=7, trash_days=45)
    got = S.api_cleanup_account(body, request=None)
    ck("N3 四项天数各归各的键",
       got["log_days"] == 14 and got["backup_days"] == 3 and got["download_days"] == 7 and got["trash_days"] == 45,
       str(got["log_days"]))
    ck("N4 存盘了（不是只改内存）", CFG.saves >= 1 and CFG.data["cleanup_log_days"] == 14, str(CFG.saves))
    ck("N5 改完把闹钟重排了一次", S._CL_TIMER["timer"] is not None)
    try:
        S.api_cleanup_account(S.CleanupAccountBody(log_days=-1), request=None)
        ck("N6 负天数被拒", False)
    except S.HTTPException as e:
        ck("N6 负天数被拒（400 带上范围）", e.status_code == 400 and "0–3650" in str(e.detail), str(e.detail)[:60])
    try:
        S.api_cleanup_account(S.CleanupAccountBody(), request=None)
        ck("N7 什么都没改时报出来，不假装成功", False)
    except S.HTTPException as e:
        ck("N7 什么都没改时报出来，不假装成功（400）", e.status_code == 400, str(e.detail)[:60])

    class Req:
        headers = {}
        cookies = {}

        def __init__(self, token_only=True):
            self.url = SimpleNamespace(path="/api/cleanup/account")

    real_gate = S._auth_token_only
    S._auth_token_only = lambda r: True
    try:
        try:
            S.api_cleanup_account(S.CleanupAccountBody(enabled=True), request=Req())
            ck("N8 机器令牌改不动清理开关", False, "居然让它改了")
        except S.HTTPException as e:
            ck("N8 机器令牌改不动清理开关（403 说明为什么）",
               e.status_code == 403 and "机器令牌" in str(e.detail), str(e.detail)[:60])
    finally:
        S._auth_token_only = real_gate

    pv = S.api_cleanup_preview()
    ck("N9 preview 返回四组与指纹", set(S.CL_GROUPS) <= set(pv["groups"]) and pv["hash"], str(sorted(pv))[:120])
    ck("N10 preview 真的不动盘（端点层也验一遍）", (DL / "端点.mp4").exists())
    run_out = S.api_cleanup_run(S.CleanupRunBody(hash=pv["hash"], groups=["downloads"]))
    ck("N11 run 按组名干活并回执", run_out["count"] == 1 and run_out["groups"] == ["downloads"], str(run_out)[:120])
    try:
        S.api_cleanup_run(S.CleanupRunBody(hash="", groups=["logs"]))
        ck("N12 run 缺指纹时端点层也挡住", False)
    except S.HTTPException as e:
        ck("N12 run 缺指纹时端点层也挡住（400）", e.status_code == 400, str(e.detail)[:60])
    th = S.api_cleanup_trash()
    ck("N13 trash 读数带着目录与条数",
       th["trash_dir"] == str(DL / S.CL_TRASH_DIRNAME) and th["count"] == 1, str(th)[:120])
    rs = S.api_cleanup_restore(S.CleanupRestoreBody(ids=[th["rows"][0]["id"]]))
    ck("N14 restore 端点把文件放回原位", (DL / "端点.mp4").exists() and rs["count"] == 1, str(rs)[:120])
    try:
        S.api_cleanup_restore(S.CleanupRestoreBody(ids=[]))
        ck("N15 restore 空 ids 被拒", False)
    except S.HTTPException as e:
        ck("N15 restore 空 ids 被拒（400）", e.status_code == 400, str(e.detail)[:60])

    # 回收目录计数不能把账本自己数成一个文件：空目录要报 0，不是 1
    S._cl_manifest_save([{"id": "aaaaaaaaaaaa", "orig": str(DL / "假的.mp4"), "moved": "假的.mp4",
                          "moved_at": time.time(), "bytes": 1, "name": "假的.mp4", "group": "downloads"}])
    ck("N16 只剩账本时读数报 0 个文件（manifest 不算成品，也不列成可还原）",
       S.api_cleanup_get()["trash_count"] == 0 and S.api_cleanup_trash()["count"] == 0,
       str(S.api_cleanup_get()["trash_count"]))
    touch(DL / S.CL_TRASH_DIRNAME / "真的.mp4", 40, "t")
    ck("N17 真躺着一个文件时才报 1", S.api_cleanup_get()["trash_count"] == 1,
       str(S.api_cleanup_get()["trash_count"]))
    S._cl_manifest_save([])

    # 还原那行日志要跟着状态走：只放回一个时不该拖个空逗号，
    # 一个都没放回（原位置被占）时也不能一声不响 —— 界面看得见，走 Telegram 只看日志的人看不见
    _re_rows = lambda: [m for m in LOGS.texts() if m.startswith("[清理] 还原")]
    ck("N18 还原日志按实际条数写，尾巴上没有多余的逗号",
       _re_rows() and _re_rows()[-1] == "[清理] 还原：1 个回到原位", str(_re_rows()[-1:])[:140])

    (DL / "占位.mp4").write_bytes(b"x")
    touch(DL / S.CL_TRASH_DIRNAME / "占位.mp4", 40, "r")
    S._cl_manifest_save([{"id": "bbbbbbbbbbbb", "name": "占位.mp4", "moved": "占位.mp4",
                          "moved_at": time.time(), "bytes": 1, "group": "downloads",
                          "orig": str(DL / "占位.mp4")}])
    _n0 = len(_re_rows())
    rf = S.api_cleanup_restore(S.CleanupRestoreBody(ids=["bbbbbbbbbbbb"]))
    _re_rows()
    ck("N19 原位置被占、一个都没放回时也有日志（不是「没事发生」）",
       rf["count"] == 0 and len(_re_rows()) == _n0 + 1
       and "1 个原位置被占" in _re_rows()[-1], str(_re_rows()[-1:])[:140])
    ck("N20 被占的那条留在账本里，回收目录那份也没跟着丢",
       any(r["id"] == "bbbbbbbbbbbb" for r in S._cl_manifest())
       and (DL / S.CL_TRASH_DIRNAME / "占位.mp4").is_file()
       and (DL / "占位.mp4").read_bytes() == b"x",
       f'{S._cl_manifest()} {(DL / "占位.mp4").stat().st_size}')

    # ---------------- O 边界：符号链接、空目录、目录不存在
    reset_tree()
    CFG.data["cleanup_download_days"] = 7
    gone_root = TMP / "已经不存在的下载目录"
    CFG.data["download_dir"] = str(gone_root)
    p = plan()
    ck("O1 下载目录整个不存在时不炸，名单是空的",
       p["groups"]["downloads"]["count"] == 0 and p["total_count"] == 0, str(p["total_count"]))
    ck("O2 回收目录读数也是空的", S.api_cleanup_trash()["count"] == 0)
    CFG.data["download_dir"] = str(DL)
    touch(DL / "只有目录没有文件" / ".keep.txt", 400, "k")
    p = plan()
    ck("O3 空目录本身不会被当成待删条目",
       all(not r["path"].endswith("只有目录没有文件") for r in p["groups"]["downloads"]["rows"]))
    inside = touch(DL / "子层" / "深处.mp4", 40, "deep")
    p = plan()
    ck("O4 子目录里的成品按相对路径列出来",
       any(r["rel"] == os.path.join("子层", "深处.mp4") for r in p["groups"]["downloads"]["rows"]),
       str([r["rel"] for r in p["groups"]["downloads"]["rows"]]))
    if hasattr(os, "symlink"):
        link = DL / "链接到外面.mp4"
        try:
            os.symlink(inside, link)
            p = plan()
            ck("O5 符号链接不跟着删（不然会把盘外东西带走）",
               not any(r["name"] == "链接到外面.mp4" for r in p["groups"]["downloads"]["rows"]),
               str([r["name"] for r in p["groups"]["downloads"]["rows"]]))
            ck("O6 链接指向的真文件仍在名单里（清的是那一份，不是两份）",
               any(r["name"] == "深处.mp4" for r in p["groups"]["downloads"]["rows"]))
        except (OSError, NotImplementedError):
            ck("O5 这台机器不让建符号链接（跳过，不算失败）", True)
            ck("O6 同上", True)
    else:
        ck("O5 平台不支持符号链接", True)
        ck("O6 平台不支持符号链接", True)
    ck("O7 名单上限是按体积从大到小排（先列最占地方那些）",
       [r["bytes"] for r in plan()["groups"]["downloads"]["rows"]]
       == sorted([r["bytes"] for r in plan()["groups"]["downloads"]["rows"]], reverse=True))
    ck("O8 逐条列的上限是 200（其余只报数）", S.CL_LIST_CAP == 200)

    # ---------------- P 媒体库扫描不把回收目录里的东西当成品
    reset_tree()
    real_ffb, real_ffi = S._ffprobe_bin, S._ffprobe_info
    S._ffprobe_bin = lambda path=None: "ffprobe-fake"
    S._ffprobe_info = lambda path: {"duration": 1, "width": 64, "height": 64,
                                    "vcodec": "h264", "acodec": "aac"}
    try:
        touch(DL / "在库.mp4", 1, "real")
        touch(DL / S.CL_TRASH_DIRNAME / "挪走.mp4", 40, "trash")
        touch(DL / S.CL_TRASH_DIRNAME / "子层" / "深处.mp4", 40, "deep")
        names = sorted(x["name"] for x in S.scan_library(DL))
    finally:
        S._ffprobe_bin, S._ffprobe_info = real_ffb, real_ffi
    ck("P1 媒体库只认原位那份，回收目录里的不算成品", names == ["在库.mp4"], str(names))
    ck("P2 回收目录连同它的子目录一起跳过（不是只挡一层）",
       "挪走.mp4" not in names and "深处.mp4" not in names, str(names))

finally:
    (S.cfg, S.log_mgr, S.queue, S.CLEANUP_STATE_FILE, S.LIBRARY_CACHE,
     S.APP_DIR, S.STATE_DIR, S.COOKIES_DIR, S.DEFAULT_DOWNLOAD_DIR, S.LOG_FILE) = _REAL
    S._CL_PLAN.update({"hash": "", "at": 0.0, "days": {}})
    if S._CL_TIMER["timer"] is not None:
        S._CL_TIMER["timer"].cancel()
        S._CL_TIMER["timer"] = None
        S._CL_TIMER["wake_at"] = 0.0
    shutil.rmtree(TMP, ignore_errors=True)

print(f"== 汇总 ==\n共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    for f in FAILED:
        print("FAIL " + f)
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
