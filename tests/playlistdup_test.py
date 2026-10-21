r"""歌单里同一首歌排了两遍：列表要合并成一行，下载只能下一遍。

线上症状：Spotify 歌单「中文歌单」139 首里同一首被加过多次，界面出现两行、
下载清单也排了两遍 —— 一首歌占两次取址、两份成品。全程不联网，只读写 %TEMP%。

三段各有反向验证：没重复时不许写合并日志、判不了重的行不许被丢掉。
跑法：`python tests/playlistdup_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def log(m, lv="info"):
    LOGS.append(f"[{lv}] {m}")


def row(title, artists="某歌手", dur_s=None, duration="", **kw):
    it = {"title": title, "artists": artists, "duration_s": dur_s or 0,
          "duration": duration, "source": "Spotify", "url": ""}
    it.update(kw)
    it["id"] = M._cache_song(it)
    return it


# ---------------------------------------------------------------- A. 判重键
print("=== A. 判重键：只抹平大小写和空白，版本词一个都不许剥 ===")
ck("A1 大小写与多余空格抹平（同一首歌常有两种写法）",
   M._track_key(row("Hello World")) == M._track_key(row("  hello   world  ")),
   M._track_key(row("Hello World")))
ck("A2 歌手写法/顺序不同算同一首",
   M._track_key(row("因為愛情", "Eason Chan, Faye Wong"))
   == M._track_key(row("因為愛情", "faye  wong、eason chan")))
ck("A3 反向验证：括注和 Live/现场 不剥，录音室版与现场版不同键",
   M._track_key(row("晴天 (Live)")) != M._track_key(row("晴天"))
   and M._track_key(row("晴天 现场版")) != M._track_key(row("晴天")))
ck("A4 歌手不同就是两首歌",
   M._track_key(row("晴天", "周杰伦")) != M._track_key(row("晴天", "孙燕姿")))
ck("A5 没曲名的行不参与合并（各自成组）",
   M._track_key(row("")) == "" and M._track_key(row("  ")) == ""
   and M._track_key(None) == "" and M._track_key({}) == "")
ck("A6 歌手字段给 list 也能对上（musicdl 的 singers 是列表）",
   M._track_key({"song_name": "晴天", "singers": ["周杰伦"]})
   == M._track_key(row("晴天", "周杰伦")))
ck("A7 真 SongInfo（对象、字段名不同）与占位 dict 同键",
   M._track_key(types.SimpleNamespace(song_name="晴天", singers=["周杰伦"]))
   == M._track_key(row("晴天", "周杰伦")))
ck("A8 时长：duration_s 数字、秒串、mm:ss 都认",
   M._track_dur_s(row("x", dur_s=202)) == 202
   and M._track_dur_s(row("x", duration="3:22")) == 202
   and M._track_dur_s({"song_name": "x", "duration_s": "202.4"}) == 202
   and M._track_dur_s(row("x")) == 0)

# ---------------------------------------------------------------- B. 分组
print("=== B. 分组口径：曲名+歌手相同还要时长对得上 ===")
g1 = [row("稻香", dur_s=223), row("稻香", dur_s=225), row("七里香", dur_s=300)]
ck("B1 同名同时长合一组，保留行是第一次出现那行",
   M._track_clusters(g1) == [[0, 1], [2]], M._track_clusters(g1))
g2 = [row("藍二乗", dur_s=265), row("藍二乗", dur_s=265 + 90)]
ck("B2 同名差 90s（现场/重制版）不算一首",
   M._track_clusters(g2) == [[0], [1]], M._track_clusters(g2))
g3 = [row("和平", dur_s=0), row("和平", dur_s=240)]
ck("B3 一侧没时长时仍与同名合并（列表里常有只给歌名的行）",
   M._track_clusters(g3) == [[0, 1]], M._track_clusters(g3))
g4 = [row(""), row("")]
ck("B4 反向验证：两行都没曲名也不许合并",
   M._track_clusters(g4) == [[0], [1]], M._track_clusters(g4))
g5 = [row("A", dur_s=100), row("B", dur_s=100), row("A", dur_s=100)]
ck("B5 组的先后按首次出现，插入顺序不改变分组",
   M._track_clusters(g5) == [[0, 2], [1]], M._track_clusters(g5))
ck("B6 空清单/None 不炸",
   M._track_clusters([]) == [] and M._track_clusters(None) == [])

# ---------------------------------------------------------------- C. 列表合并
print("=== C. merge_duplicate_tracks：合并成一行并标 ×N ===")
c_in = [row("晴天", dur_s=265), row("稻香", dur_s=223), row("晴天", dur_s=265),
        row("晴天", dur_s=265), row("七里香", dur_s=300)]
LOGS.clear()
c_out = M.merge_duplicate_tracks(c_in, log=log)
ck("C1 行数按重复数量减少，顺序保持首次出现",
   [r["title"] for r in c_out] == ["晴天", "稻香", "七里香"], [r["title"] for r in c_out])
ck("C2 重复行标 dup_count，没重复的行不带这个键",
   c_out[0].get("dup_count") == 3 and "dup_count" not in c_out[1], c_out[0])
ck("C3 日志写明合并了几首、并说下载只下一遍（只写一条）",
   LOGS == ["[info] 歌单里有 2 首与前面的重复（同一首歌被加过多次），已合并成一行，下载只下一遍"],
   LOGS)
ck("C4 保留行的 cache id 不变（勾选/下载仍指同一首）",
   c_out[0]["id"] == c_in[0]["id"] and c_out[1]["id"] == c_in[1]["id"])
ck("C5 反向验证：一首都不重复时按位返回同一批条目、一行日志都不写",
   M.merge_duplicate_tracks([r1 := row("甲"), r2 := row("乙")], log=log) == [r1, r2]
   and len(LOGS) == 1, LOGS)
ck("C6 空清单/None 不炸也不写日志",
   M.merge_duplicate_tracks([], log=log) == [] and M.merge_duplicate_tracks(None, log=log) == []
   and len(LOGS) == 1, LOGS)

# ---------------------------------------------------------------- D. 下载入口
print("=== D. drop_duplicate_tracks：给出保留下标，让调用方对齐回 cache id ===")
d_in = [row("晴天", dur_s=265), row("晴天", dur_s=265), row("稻香", dur_s=223)]
keep, skipped = M.drop_duplicate_tracks(d_in)
ck("D1 保留的是首次出现那两个下标", keep == {0, 2}, keep)
ck("D2 被跳过的点名曲名和排了几遍",
   skipped == [{"title": "晴天", "count": 2}], skipped)
ck("D3 缓存查不到的条目（None）一定留在保留集合里",
   M.drop_duplicate_tracks([None, None, row("晴天")])[0] == {0, 1, 2},
   M.drop_duplicate_tracks([None, None, row("晴天")]))
ck("D4 没重复时 skipped 为空、每行都保留",
   M.drop_duplicate_tracks([row("甲"), row("乙")]) == ({0, 1}, []))

# ---------------------------------------------------------------- E. parse_playlist 收尾
print("=== E. 解析收尾：列表返回前就合并，并把合并数量写进 diag ===")
SP_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
_real_e = (M.list_spotify_playlist, M._unreachable_reason, M.musicdl_available)


def stub_list(url, *, proxy="", log=print, **kw):
    return ([row("十年", dur_s=207), row("十年", dur_s=207), row("好久不見", dur_s=250),
             row("好久不見", dur_s=250), row("好久不見", dur_s=250)],
            "中文歌单", "")


M.list_spotify_playlist = stub_list
M._unreachable_reason = lambda *a, **k: ""
M.musicdl_available = lambda: True
try:
    LOGS.clear()
    got = M.parse_playlist(SP_URL, log=log, prefer="fast")
    diag = dict(M._LAST_PLAYLIST_DIAG)
    ck("E1 返回的是合并后的三首里的两首",
       [r["title"] for r in got] == ["十年", "好久不見"], [r["title"] for r in got])
    ck("E2 diag 报出合并掉的首数（界面据此写「已合并 N 首重复」）",
       diag.get("dup_merged") == 3, diag.get("dup_merged"))
    ck("E3 合并日志写了，且那句「歌单解析: N 首」报的是合并后的数",
       any("已合并成一行" in m for m in LOGS)
       and any("歌单解析: 2 首" in m for m in LOGS), LOGS)
    ck("E4 每行带着 ×N 与自己的 cache id",
       [r.get("dup_count") for r in got] == [2, 3] and all(r.get("id") for r in got),
       [r.get("dup_count") for r in got])

    def stub_nodup(url, *, proxy="", log=print, **kw):
        return [row("甲", dur_s=100), row("乙", dur_s=200)], "无重复歌单", ""

    M.list_spotify_playlist = stub_nodup
    LOGS.clear()
    got2 = M.parse_playlist(SP_URL, log=log, prefer="fast")
    diag2 = dict(M._LAST_PLAYLIST_DIAG)
    ck("E5 反向验证：没重复时 dup_merged 为 0、不写合并日志",
       len(got2) == 2 and diag2.get("dup_merged") == 0
       and not any("重复" in m for m in LOGS), (diag2.get("dup_merged"), LOGS))

    M._unreachable_reason = lambda *a, **k: "直连不通且没配代理"
    LOGS.clear()
    got3 = M.parse_playlist(SP_URL, log=log, prefer="fast")
    ck("E6 反向验证：解析在半路失败时不写 dup_merged（不把 0 首说成合并过）",
       got3 == [] and "dup_merged" not in M._LAST_PLAYLIST_DIAG, list(M._LAST_PLAYLIST_DIAG))

    # 反向对照：把收尾那次合并关掉，重复必须原样冒出来 —— 否则上面几条等于在验桩子
    M._unreachable_reason = lambda *a, **k: ""
    M.list_spotify_playlist = stub_list
    _real_merge = M.merge_duplicate_tracks
    M.merge_duplicate_tracks = lambda items, log=None: list(items)
    try:
        LOGS.clear()
        got4 = M.parse_playlist(SP_URL, log=log, prefer="fast")
        ck("E7 反向对照：合并一关掉，五首里就留着三首重复、diag 也不报数量",
           len(got4) == 5 and dict(M._LAST_PLAYLIST_DIAG).get("dup_merged") == 0
           and not any("重复" in m for m in LOGS),
           (len(got4), dict(M._LAST_PLAYLIST_DIAG).get("dup_merged")))
    finally:
        M.merge_duplicate_tracks = _real_merge
finally:
    (M.list_spotify_playlist, M._unreachable_reason, M.musicdl_available) = _real_e

# ---------------------------------------------------------------- F. 下载入口端点
print("=== F. /api/music/download：清单里的重复在开跑前就去掉 ===")
import server as S  # noqa: E402

OUT_F = pathlib.Path(tempfile.mkdtemp(prefix="md_dup_dl_test_"))
# 判重要读本地索引快照，那套逻辑会落盘；不拐进临时目录就往程序目录的 local_index 里漏水
M._LOCAL_INDEX_DIR = OUT_F / "local_index"


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)
        self.saves = 0

    def save(self):
        self.saves += 1


class InlineThread:
    """让后台线程当场跑完，断言才不用等 sleep。"""

    def __init__(self, target=None, **kw):
        self._t = target

    def start(self):
        self._t()


captured: dict = {}


def fake_download_songs(cache_ids, **kw):
    captured["ids"] = list(cache_ids)
    return [""] * len(cache_ids)


_ORIG = {k: getattr(S, k, None) for k in ("cfg", "log_mgr", "music_proxy_resolver",
                                          "threading", "_MUSIC_JOB")}
_ORIG_DL = M.download_songs
SLOTS: list = []


class FakeLog:
    @staticmethod
    def log(m, lv="info", k="", kv=None):   # k/kv 是 #55 后端运行日志的键，桩不收
        SLOTS.append(f"[{lv}] {m}")


try:
    S.cfg = FakeCfg({"download_dir": str(OUT_F), "music_filename_template":
                     "{artist}/{name} - {artist}"})
    S.log_mgr = FakeLog()
    S.music_proxy_resolver = lambda p: (lambda s: "")
    S.threading = types.SimpleNamespace(Thread=InlineThread)
    S._MUSIC_JOB = {}
    M.download_songs = fake_download_songs

    f_ids = [row("晴天", "周杰伦", dur_s=265)["id"], row("晴天", "周杰伦", dur_s=265)["id"],
             row("稻香", "周杰伦", dur_s=223)["id"], "不在缓存里的旧id"]
    LOGS.clear()
    SLOTS.clear()
    out = S.api_music_download({"ids": list(f_ids)})
    ck("F1 交给下载的清单去掉了第二遍，判不了重的旧 id 原样保留",
       captured["ids"] == [f_ids[0], f_ids[2], f_ids[3]], captured["ids"])
    ck("F2 进度总数按去重后算（不会永远差一首播不动）",
       S._MUSIC_JOB.get("total") == 3, S._MUSIC_JOB.get("total"))
    ck("F3 被跳过的重复单独记账，不与「没取到地址」的失败混在一起",
       S._MUSIC_JOB.get("dup_skipped") == 1, S._MUSIC_JOB.get("dup_skipped"))
    ck("F4 日志点名是哪一首排了两遍",
       any("下载清单里有 1 首重复" in m and "晴天" in m and "×2" in m for m in SLOTS), SLOTS)
    ck("F5 返回给界面的话也说了跳过几首",
       "已跳过 1 首重复" in (out.get("message") or ""), out.get("message"))
    st = S.api_music_download_status()
    ck("F6 状态接口里 skipped 只剩失败数（3 首里全没下成），重复另算",
       st.get("skipped") == 3 and st.get("dup_skipped") == 1,
       {k: st.get(k) for k in ("total", "ok", "skipped", "dup_skipped")})

    captured.clear()
    SLOTS.clear()
    S._MUSIC_JOB = {}
    S.api_music_download({"ids": [f_ids[0], f_ids[2]]})
    ck("F7 反向验证：清单没重复时一首不少地交下去、dup_skipped 归零",
       captured["ids"] == [f_ids[0], f_ids[2]] and S._MUSIC_JOB.get("dup_skipped") == 0,
       (captured.get("ids"), S._MUSIC_JOB.get("dup_skipped")))
    ck("F8 反向验证：没重复时不许出现「重复」字样",
       not any("重复" in m for m in SLOTS), SLOTS)
    captured.clear()
    SLOTS.clear()
    S._MUSIC_JOB = {}
    S.api_music_download({"ids": [f_ids[0], f_ids[0]]})
    ck("F9 同一个 cache id 被点两次也只下一遍",
       captured["ids"] == [f_ids[0]] and S._MUSIC_JOB.get("total") == 1,
       (captured.get("ids"), S._MUSIC_JOB.get("total")))
finally:
    M.download_songs = _ORIG_DL
    for k, v in _ORIG.items():
        if v is None:
            if hasattr(S, k):
                delattr(S, k)
        else:
            setattr(S, k, v)
    shutil.rmtree(OUT_F, ignore_errors=True)

# ---------------------------------------------------------------- 结果
print("\n=== 结果 ===")
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
