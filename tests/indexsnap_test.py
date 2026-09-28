# -*- coding: utf-8 -*-
r"""本地索引快照：TTL 内不重扫、过期先给旧的那份再后台重扫，索引文件不落被扫描目录。

起因：每次搜索都把整目录重解析一遍，上千首不可能秒开；#134 的按 path+size+mtime 缓存
只省了「解析」，目录遍历和读盘仍然每次都付。这里加「扫描快照 + TTL + 后台刷新」。

跑法：`python tests/indexsnap_test.py`（不需要起 server，也不需要 ffmpeg）。
全部产物落在 %TEMP%\md_indexsnap_test\<时刻>\，绝不碰真实下载目录 / 程序目录的 local_index。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_indexsnap_test"
SHARD = ROOT / time.strftime("%H%M%S")
LIB = SHARD / "lib"               # 被扫描的"下载目录"
IDX = SHARD / "index_dir"         # 索引该落在这里（程序目录的替身）
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


# 真实代码把索引目录读成模块全局，测试把它拐进 Temp
M._LOCAL_INDEX_DIR = IDX
ORIG_JOIN = M._LOCAL_SCAN_JOIN_S
ORIG_SCAN = M.scan_local_music
BOX = {"n": 0, "roots": []}
LOCK = threading.Lock()


def counting_scan(root, log=print):
    with LOCK:
        BOX["n"] += 1
        BOX["roots"].append(str(root))
    return ORIG_SCAN(root, log=log)


def slow_scan(root, log=print, delay=0.6):
    with LOCK:
        BOX["n"] += 1
        BOX["roots"].append(str(root))
    time.sleep(delay)
    return ORIG_SCAN(root, log=log)


M.scan_local_music = counting_scan


def reset_state():
    """回到「进程刚起来」的样子：内存快照和单飞表都清空。"""
    with M._LOCAL_SNAP_LOCK:
        M._LOCAL_SNAP.clear()
        M._LOCAL_SCANNING.clear()
    M._LOCAL_META_CACHE.clear()


def add_song(name, base=LIB):
    base.mkdir(parents=True, exist_ok=True)
    (base / name).write_bytes(b"fake-mp3-bytes")
    return base / name


def drop_scanned_at(secs_ago: float, root=None):
    """把磁盘上那份快照的扫描时刻改老，模拟「索引过期了」。"""
    p = M.local_index_path(str(root if root is not None else LIB))
    data = json.loads(p.read_text(encoding="utf-8"))
    data["scanned_at"] = time.time() - secs_ago
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def wait_fresh(timeout=8.0, root=None):
    """等后台重扫真跑完：内存那份的扫描时刻得变成"刚刚"，光是有内容不算。"""
    key = M._index_key(str(root if root is not None else LIB))
    end = time.time() + timeout
    while time.time() < end:
        with M._LOCAL_SNAP_LOCK:
            snap = M._LOCAL_SNAP.get(key)
        if snap and time.time() - float(snap.get("ts") or 0) < 60:
            return True
        time.sleep(0.05)
    return False


def wait_scanning(timeout=5.0, root=None):
    """等后台那一次扫描真的起来并登记上 —— 不等到就无法证明 force 是「并进去等」。"""
    key = M._index_key(str(root if root is not None else LIB))
    end = time.time() + timeout
    while time.time() < end:
        with M._LOCAL_SNAP_LOCK:
            if key in M._LOCAL_SCANNING:
                return True
        time.sleep(0.01)
    return False


LIB.mkdir(parents=True)
SNAP_FILE = M.local_index_path(str(LIB))

# ── A. 首扫 / TTL 命中 ────────────────────────────────────────
print("=== A. 第一次当场扫，TTL 内一次都不重扫 ===")
add_song("歌A.mp3")
reset_state()
BOX["n"] = 0
rows = M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("A1 没有快照时当场扫一遍，拿到 1 首", BOX["n"] == 1 and len(rows) == 1, f"{BOX['n']} 扫/{len(rows)} 首")
ck("A2 索引写进程序目录（此处为 Temp 替身）", SNAP_FILE.is_file() and IDX in SNAP_FILE.parents, str(SNAP_FILE))
BOX["n"] = 0
for _ in range(5):
    M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("A3 TTL 内连查 5 次 = 0 次重扫（秒开就靠这个）", BOX["n"] == 0, f"{BOX['n']} 次")
b = BOX["n"]
M.search_local_music("歌A", str(LIB), log=lambda *a: None)
M.search_local_music("歌A", str(LIB), log=lambda *a: None)
M.search_local_music("没有这首歌", str(LIB), log=lambda *a: None)
ck("A4 搜索走同一份快照：查 3 次仍不重扫", BOX["n"] == b, f"{BOX['n'] - b} 次")
reset_state()
SNAP_FILE.unlink(missing_ok=True)
BOX["n"] = 0
M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("A5 反面对照：内存和磁盘快照都没了就必须重扫（A3 的 0 不是巧合）",
   BOX["n"] == 1, f"{BOX['n']} 次")

# ── B. 重启后靠磁盘快照，不重扫也不重解析 ─────────────────────
print("=== B. 模拟重启：内存空，磁盘那份还在 ===")
add_song("歌B.mp3")           # 目录里已经变了，但 TTL 内按设计不重扫
reset_state()
BOX["n"] = 0
rows = M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("B1 重启后第一次查不扫目录（从磁盘快照灌回内存）",
   BOX["n"] == 0 and len(rows) == 1, f"{BOX['n']} 扫/{len(rows)} 首")
ck("B2 灌回内存的字段没丢（有 path/size/mtime）",
   all(r.get("path") and r.get("size") and r.get("mtime") for r in rows))
reset_state()
read_box = {"n": 0}
_orig_read = M._read_snapshot


def spy_read(root):
    read_box["n"] += 1
    return _orig_read(root)


M._read_snapshot = spy_read
try:
    rows = M.local_music_snapshot(str(LIB), log=lambda *a: None)
    first = read_box["n"]
    rows = M.local_music_snapshot(str(LIB), log=lambda *a: None)
    ck("B3 第二次查连磁盘快照都不用读（纯内存命中）",
       first == 1 and read_box["n"] == 1 and len(rows) == 1, f"读盘 {read_box['n']} 次")
finally:
    M._read_snapshot = _orig_read

# ── C. 过期：先给旧的那份 + 后台重扫 ─────────────────────────
print("=== C. 快照过期：当场返回上次结果，重扫丢后台 ===")
add_song("歌C.mp3")           # 新成品，旧快照里没有
drop_scanned_at(9999)         # 磁盘那份变陈旧
reset_state()
BOX["n"] = 0
t0 = time.time()
rows = M.local_music_snapshot(str(LIB), log=lambda *a: None)
took = time.time() - t0
ck("C1 过期时当场就把上次那份返回（不等重扫）", took < 0.5, f"{took:.3f}s")
ck("C2 返回的是旧内容：只认得过期前那 1 首", len(rows) == 1, f"{len(rows)} 首")
ck("C3 后台重扫真跑了，跑完再查有 3 首",
   wait_fresh() and len(M.local_music_snapshot(str(LIB), log=lambda *a: None)) == 3)
ck("C4 重扫把新内容落回磁盘",
   json.loads(SNAP_FILE.read_text(encoding="utf-8")).get("count") == 3)
add_song("歌D.mp3")
drop_scanned_at(9999)
reset_state()
old = M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("C5 再过期一次：仍然当场返回旧的 3 首，不卡界面", len(old) == 3, f"{len(old)} 首")
ck("C6 后台补上第 4 首（新落盘的歌最终会被看见）",
   wait_fresh() and len(M.local_music_snapshot(str(LIB), log=lambda *a: None)) == 4)
BOX["n"] = 0
M.local_music_snapshot(str(LIB), log=lambda *a: None)
M.local_music_snapshot(str(LIB), log=lambda *a: None)
ck("C7 反面对照：刷新成新鲜快照后不再起后台线程（C6 的 4 首是真扫出来的）",
   BOX["n"] == 0, f"{BOX['n']} 次")

# ── D. 判重口径 ttl=0：刚下完的那首必须当场看得见 ────────────
print("=== D. ttl=0（判重用）：绝不吃旧快照 ===")
add_song("歌E.mp3")
M.save_local_index(str(LIB), [])        # 故意把快照写成"一首都没有"
reset_state()
rows = M.local_music_snapshot(str(LIB), ttl=0, log=lambda *a: None)
ck("D1 ttl=0 当场重扫，刚落盘的那首看得见", len(rows) == 5, f"{len(rows)} 首")
ck("D2 扫完顺手刷新快照（下次查就免费）",
   json.loads(SNAP_FILE.read_text(encoding="utf-8")).get("count") == 5)
BOX["n"] = 0
ck("D3 反面对照：同一时刻按默认 TTL 查就是 0 次扫描（D1 的 5 首确实是 ttl=0 换来的）",
   len(M.local_music_snapshot(str(LIB), log=lambda *a: None)) == 5 and BOX["n"] == 0, f"{BOX['n']} 次")
BOX["n"] = 0
ck("D4 force=True（「扫描本地库」按钮）也绕开新鲜快照",
   len(M.local_music_snapshot(str(LIB), force=True, log=lambda *a: None)) == 5 and BOX["n"] == 1,
   f"{BOX['n']} 次")

# ── E. 同一个目录并发：只扫一次 ──────────────────────────────
print("=== E. 单飞：并发请求不许把目录扫 N 遍 ===")
M.scan_local_music = slow_scan
drop_scanned_at(9999)
reset_state()
BOX["n"] = 0
out = []


def caller():
    out.append(len(M.local_music_snapshot(str(LIB), log=lambda *a: None)))


ths = [threading.Thread(target=caller) for _ in range(6)]
for t in ths:
    t.start()
time.sleep(0.15)                      # 让其余 5 个撞进"正在扫"的窗口
for t in ths:
    t.join(timeout=10)
ck("E1 6 个并发只起 1 次扫描", BOX["n"] == 1, f"{BOX['n']} 次")
ck("E2 每个调用者都当场拿到东西（没有谁被卡住返回空）",
   len(out) == 6 and all(x >= 1 for x in out), str(out))
wait_fresh()                            # E1 那一轮后台扫描收尾，别污染 E3 的计数

LIB2 = SHARD / "lib2"
LIB2.mkdir(parents=True)
(LIB2 / "另一目录.mp3").write_bytes(b"fake")
reset_state()
BOX["n"] = 0
BOX["roots"].clear()
t0 = time.time()
ts = [threading.Thread(target=lambda r=r: M.local_music_snapshot(r, force=True, log=lambda *a: None))
      for r in (str(LIB), str(LIB2))]
for t in ts:
    t.start()
for t in ts:
    t.join(timeout=10)
wall = time.time() - t0
ck("E3 对照：两个不同目录各扫各的，而且是并行（E1 的 1 次不是全局串行的假象）",
   BOX["n"] == 2 and len(set(BOX["roots"])) == 2 and wall < 1.1,
   f"{BOX['n']} 次 / {wall:.2f}s（串行要 ≥1.2s）{BOX['roots']}")
wait_fresh()                            # 等 E 里后台那扫收尾，别和 F 交叠

# ── F. 老索引搬家：留在下载目录里的那份要搬走并继续能用 ──────
print("=== F. 老版本索引在被扫描目录里 → 搬进程序目录 ===")
M.scan_local_music = counting_scan
LEG = LIB / "local_music_index.json"
M._LOCAL_META_CACHE.clear()
real_rows = ORIG_SCAN(str(LIB), log=lambda *a: None)      # 真扫一遍，字段/缓存键都是真的
LEG.write_text(json.dumps(real_rows, ensure_ascii=False), encoding="utf-8")   # 老格式：裸数组
SNAP_FILE.unlink(missing_ok=True)
reset_state()
rows = M.load_local_index(str(LIB))
ck("F1 老格式（裸数组）仍读得出来", len(rows) == len(real_rows), f"{len(rows)}/{len(real_rows)} 首")
ck("F2 已经搬出被扫描目录，原件删掉不留垃圾",
   not LEG.exists() and SNAP_FILE.is_file(), f"legacy={LEG.exists()} snap={SNAP_FILE.exists()}")

warm_box = {"n": 0}
import mutagen
_orig_mut_file = mutagen.File


def spy_mut(*a, **kw):
    warm_box["n"] += 1
    return _orig_mut_file(*a, **kw)


mutagen.File = spy_mut
try:
    names = sorted(p.stem for p in LIB.glob("*.mp3"))
    reset_state()                       # 内存缓存也没了 = 刚重启
    M.scan_local_music(str(LIB), log=lambda *a: None)
    ck("F3 搬家后的老索引照样能回填元数据缓存（整目录零真解析）",
       warm_box["n"] == 0 and len(names) >= 3, f"解析 {warm_box['n']}/{len(names)} 首：{names}")
    warm_box["n"] = 0
    M._LOCAL_META_CACHE.clear()
    M.save_local_index(str(LIB), [])    # 掐掉回填这条路：快照里什么都没有
    reset_state()
    M.scan_local_music(str(LIB), log=lambda *a: None)
    ck("F4 反面对照：没有索引回填时整目录重解析（F3 的 0 不是巧合）",
       warm_box["n"] == len(names), f"解析 {warm_box['n']}/{len(names)}")
finally:
    mutagen.File = _orig_mut_file

# ── G. 被扫描目录保持干净（这才是搬家真正要买的东西）──────────
print("=== G. 目录快照 diff：下载目录里除了歌什么都没多出来 ===")
extra = [p.name for p in LIB.rglob("*") if p.is_file() and p.suffix.lower() not in M.LOCAL_AUDIO_EXTS]
ck("G1 被扫描目录里没有索引/临时文件", not extra, str(extra))
ck("G2 索引文件全在程序目录（Temp 替身）下",
   len(list(IDX.glob("local_music_index_*.json"))) >= 1
   and not list(SHARD.glob("local_music_index*")))

# ── H. 搬家要把旧文件的时间一起带过来（首轮实测就是这个漏的）────
print("=== H. 老索引搬家后仍然「是旧的」：秒回旧内容 + 后台重扫 ===")
LIB_H = SHARD / "lib_h"
LIB_H.mkdir(parents=True)
SNAP_H = M.local_index_path(str(LIB_H))
add_song("旧歌.mp3", LIB_H)
LEG_H = LIB_H / "local_music_index.json"
LEG_H.write_text(json.dumps(ORIG_SCAN(str(LIB_H), log=lambda *a: None),
                            ensure_ascii=False), encoding="utf-8")      # 老格式：裸数组，1 首
STAMP = time.time() - 7200
os.utime(LEG_H, (STAMP, STAMP))            # 那份索引是两小时前扫出来的
add_song("新歌.mp3", LIB_H)                # 目录里现在有两首，旧索引只认得一首
SNAP_H.unlink(missing_ok=True)
reset_state()
M._migrate_legacy_index(str(LIB_H), SNAP_H)
ck("H1 搬家把旧文件的修改时间一起带过去（否则 TTL 再也判不出它旧）",
   abs(SNAP_H.stat().st_mtime - STAMP) < 2.0 and not LEG_H.exists(),
   f"标为 {time.time() - SNAP_H.stat().st_mtime:.0f}s 前")
reset_state()
BOX["n"] = 0
t0 = time.time()
rows = M.local_music_snapshot(str(LIB_H), log=lambda *a: None)
ck("H2 过期的搬家索引当场就返回上次那份（两小时前的 1 首），不等重扫",
   len(rows) == 1 and time.time() - t0 < 0.5, f"{len(rows)} 首 / {time.time() - t0:.3f}s")
new_disk = None
end = time.time() + 8.0
while time.time() < end:
    if SNAP_H.is_file():
        try:
            d = json.loads(SNAP_H.read_text(encoding="utf-8"))
        except Exception:
            d = None
        if isinstance(d, dict) and d.get("count") == 2:
            new_disk = d
            break
    time.sleep(0.05)
ck("H3 后台重扫真跑了：新落盘的那首被看见，磁盘也换成新格式",
   new_disk is not None, f"{BOX['n']} 次扫描 / {type(new_disk).__name__}")
SNAP_H2 = M.local_index_path(str(LIB_H))
_its = json.loads(SNAP_H2.read_text(encoding="utf-8"))["items"]
SNAP_H2.write_text(json.dumps(_its, ensure_ascii=False), encoding="utf-8")   # 裸数组 + 现在的 mtime
add_song("第三首.mp3", LIB_H)
reset_state()
BOX["n"] = 0
rows = M.local_music_snapshot(str(LIB_H), log=lambda *a: None)
ck("H4 反面对照：扫描时刻变成「现在」就被判成新鲜，一次都不重扫（H3 那次后台扫描确实是保留旧时间换来的）",
   BOX["n"] == 0 and len(rows) == 2, f"{BOX['n']} 次 / {len(rows)} 首")

# ── I. 按「扫描本地库」时也要清掉下载目录里的老索引 ────────────
print("=== I. force 扫描顺手清掉被扫描目录里的老索引 ===")
# 真扫描自己会经 load_local_index 搬家，用它就量不到 _scan_and_save 这一手；这里只列文件、绝不读旧索引
def bare_scan(root, log=print):
    with LOCK:
        BOX["n"] += 1
        BOX["roots"].append(str(root))
    return [{"path": str(p), "title": p.stem, "size": 1, "mtime": 1}
            for p in sorted(pathlib.Path(root).glob("*.mp3"))]


M.scan_local_music = bare_scan
LIB_I = SHARD / "lib_i"
LIB_I.mkdir(parents=True)
add_song("我1.mp3", LIB_I)
LEG_I = LIB_I / "local_music_index.json"
LEG_I.write_text(json.dumps(ORIG_SCAN(str(LIB_I), log=lambda *a: None),
                            ensure_ascii=False), encoding="utf-8")
add_song("我2.mp3", LIB_I)
M.local_index_path(str(LIB_I)).unlink(missing_ok=True)
reset_state()
BOX["n"] = 0
rows = M.local_music_snapshot(str(LIB_I), force=True, log=lambda *a: None)
ck("I1 force 当场扫：目录里有几首回几首", BOX["n"] == 1 and len(rows) == 2,
   f"{BOX['n']} 次 / {len(rows)} 首")
ck("I2 老索引不再留在下载目录里（扫描本身不搬家，靠的是 _scan_and_save 这一手）", not LEG_I.exists())
ck("I3 落的是新格式（带 scanned_at/count），界面据此才判得了新旧",
   json.loads(M.local_index_path(str(LIB_I)).read_text(encoding="utf-8")).get("count") == 2)
b = BOX["n"]
M.local_music_snapshot(str(LIB_I), log=lambda *a: None)
ck("I4 反面对照：那一轮没半路失败 —— 紧接着查是纯内存命中，不再扫（I1 的 2 首真落盘了）",
   BOX["n"] == b, f"{BOX['n'] - b} 次")
M.scan_local_music = counting_scan

# ── J. 后台正在重扫时按「扫描本地库」：等那一次，不退回旧索引 ──
print("=== J. force 撞上进行中的后台重扫：join 那一次，只扫一次 ===")
M.scan_local_music = slow_scan
LIB_J = SHARD / "lib_j"
LIB_J.mkdir(parents=True)
add_song("等1.mp3", LIB_J)
M.save_local_index(str(LIB_J), ORIG_SCAN(str(LIB_J), log=lambda *a: None))
add_song("等2.mp3", LIB_J)
add_song("等3.mp3", LIB_J)
drop_scanned_at(9999, LIB_J)
reset_state()
BOX["n"] = 0
stale = M.local_music_snapshot(str(LIB_J), log=lambda *a: None)      # 起一次后台重扫
started = wait_scanning(root=LIB_J)
t0 = time.time()
rows = M.local_music_snapshot(str(LIB_J), force=True, log=lambda *a: None)
waited = time.time() - t0
ck("J0 后台那一次扫描真的在跑（否则下面的「并进去等」无从谈起）", started)
ck("J1 旧的那份先返回（界面不卡），随后 force 拿到重扫后的 3 首而不是旧的 1 首",
   len(stale) == 1 and len(rows) == 3, f"{len(stale)} 旧 / {len(rows)} 新")
ck("J2 全程只扫一次（force 是并进去等的，不是自己又扫一遍）", BOX["n"] == 1, f"{BOX['n']} 次")
ck("J3 确实等到了那一次扫描（0.6s 的桩），不是秒回旧内容", waited >= 0.3, f"{waited:.2f}s")

drop_scanned_at(9999, LIB_J)
reset_state()
BOX["n"] = 0
M.local_music_snapshot(str(LIB_J), log=lambda *a: None)              # 再起一次后台重扫
wait_scanning(root=LIB_J)
t0 = time.time()
rows = M.local_music_snapshot(str(LIB_J), ttl=0, log=lambda *a: None)  # 判重那条路：不排队
ck("J4 反面对照：同一时刻普通读/ttl=0 绝不排在后台那一次后面（界面永远不等扫描），扫描数仍是 1",
   BOX["n"] == 1 and time.time() - t0 < 0.3 and len(rows) >= 1, f"{BOX['n']} 次 / {time.time() - t0:.2f}s")
wait_fresh(root=LIB_J)

M.scan_local_music = lambda root, log=print: slow_scan(root, log, delay=1.5)
M._LOCAL_SCAN_JOIN_S = 0.3
drop_scanned_at(9999, LIB_J)
reset_state()
BOX["n"] = 0
M.local_music_snapshot(str(LIB_J), log=lambda *a: None)
wait_scanning(root=LIB_J)
t0 = time.time()
rows = M.local_music_snapshot(str(LIB_J), force=True, log=lambda *a: None)
ck("J5 等待有上限：那次扫描迟迟不结束，force 也按时退回来，不会把请求线程吊死",
   time.time() - t0 < 1.2 and len(rows) >= 1, f"{time.time() - t0:.2f}s / {len(rows)} 首")
M._LOCAL_SCAN_JOIN_S = ORIG_JOIN
wait_fresh(root=LIB_J, timeout=12.0)
M.scan_local_music = counting_scan
ck("J6 目录始终干净：三个新目录里除了歌没多东西",
   not [p for r in (LIB_H, LIB_I, LIB_J) for p in pathlib.Path(r).rglob("*")
        if p.is_file() and p.suffix.lower() not in M.LOCAL_AUDIO_EXTS])

print()
if FAILED:
    print(f"FAILED {len(FAILED)}: " + " | ".join(FAILED))
    sys.exit(1)
print("ALL PASS")
shutil.rmtree(str(SHARD), ignore_errors=True)
