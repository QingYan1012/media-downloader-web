r"""音乐搜索源去重 + 每源预算上限自检。

只查两件事，全在内存里跑：不 import server、不读 config、不联网。
  A) canonical_sources：同一个平台的两种写法（Spotify / SpotifyMusicClient）只能算一个源
  B) 每源预算的默认值和上限
  C) _run_source_searches 真的只为一个源开一条线程（把 _search_one_source 换成假的）

跑法：`python tests/music_sources_test.py`
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []


def ck(name: str, cond, extra: str = ""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


print("== A. 源归一化去重 ==")
ck("A1 短名补成 MusicClient", M.canonical_sources(["Spotify"]) == ["SpotifyMusicClient"])
ck("A2 两种写法算一个源",
   M.canonical_sources(["Spotify", "SpotifyMusicClient"]) == ["SpotifyMusicClient"],
   str(M.canonical_sources(["Spotify", "SpotifyMusicClient"])))
ck("A3 大小写/空格也认", M.canonical_sources([" spotify ", "Spotify"]) == ["SpotifyMusicClient"])
got = M.canonical_sources(["Migu", "NeteaseMusicClient", "QQ", "qqmusic", "migu"])
ck("A4 保持首次出现的顺序", got == ["MiguMusicClient", "NeteaseMusicClient", "QQMusicClient"], str(got))
ck("A5 空值丢掉", M.canonical_sources(["", None, "  ", "Apple"]) == ["AppleMusicClient"])
ck("A6 空输入不炸", M.canonical_sources([]) == [] and M.canonical_sources(None) == [])
once = M.canonical_sources(["Spotify", "SpotifyMusicClient", "apple", "AppleMusicClient"])
ck("A7 再洗一遍结果不变", M.canonical_sources(once) == once, str(once))

print("== B. 每源预算 ==")
ck("B1 默认值放宽到 300s", M.PARALLEL_STRATEGY_DEFAULT["per_source_budget"] == 300)
ck("B2 上限 1800s", M._merge_strategy({"per_source_budget": 99999})["per_source_budget"] == 1800)
ck("B3 中间值原样吃下", M._merge_strategy({"per_source_budget": 900})["per_source_budget"] == 900)
ck("B4 0 表示不限，不被当成缺省", M._merge_strategy({"per_source_budget": 0})["per_source_budget"] == 0)
ck("B5 脏值退回默认", M._merge_strategy({"per_source_budget": "abc"})["per_source_budget"] == 300)

print("== C. 分发时真的只搜一次 ==")
calls: list[str] = []
lock = threading.Lock()


def fake_one_source(src, keyword, **kw):
    with lock:
        calls.append(src)
    return ([{"musicname": f"{keyword}-{src}", "musicauthor": "某人", "musicsource": src}], [])


_orig = M._search_one_source
M._search_one_source = fake_one_source
try:
    st = M._merge_strategy({"per_source_budget": 5, "mode": "parallel"})
    songs, stats, errs, elapsed = M._run_source_searches(
        ["Spotify", "SpotifyMusicClient", "Apple"], "晴天",
        st=st, work_dir="", cookies="", proxy="", log=lambda *a, **k: None,
        proxy_for=None,
    )
    ck("C1 每个源只起一次", sorted(calls) == ["AppleMusicClient", "SpotifyMusicClient"], str(calls))
    ck("C2 结果不再翻倍", len(songs) == 2, f"{len(songs)} 条")
    ck("C3 计数表用日志里的短名", set(stats) == {"Spotify", "Apple"}, str(stats))
    ck("C4 没有报错", not errs, str(errs))
finally:
    M._search_one_source = _orig

print("== D. 源少时预算放宽 + 回写 ==")
M._search_one_source = fake_one_source
try:
    logs: list[str] = []
    st1 = M._merge_strategy({"per_source_budget": 180})
    M._run_source_searches(["Spotify"], "晴天", st=st1, work_dir="", cookies="",
                           proxy="", log=lambda m, *a, **k: logs.append(str(m)), proxy_for=None)
    ck("D1 单源时 180 → 300", st1["per_source_budget"] == 300, str(st1["per_source_budget"]))
    ck("D2 放宽动作上了日志", any("300s" in l and "每源预算" in l for l in logs), str(logs))

    logs2: list[str] = []
    st2 = M._merge_strategy({"per_source_budget": 600})
    M._run_source_searches(["Spotify"], "晴天", st=st2, work_dir="", cookies="",
                           proxy="", log=lambda m, *a, **k: logs2.append(str(m)), proxy_for=None)
    ck("D3 已够大就不改", st2["per_source_budget"] == 600 and not any("→" in l for l in logs2), str(logs2))

    st3 = M._merge_strategy({"per_source_budget": 180})
    M._run_source_searches(["Spotify", "Apple", "Migu"], "晴天", st=st3, work_dir="", cookies="",
                           proxy="", log=lambda m, *a, **k: None, proxy_for=None)
    ck("D4 三个源以上不放宽", st3["per_source_budget"] == 180, str(st3["per_source_budget"]))
finally:
    M._search_one_source = _orig

print(f"\nFAILED: {FAILED if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
