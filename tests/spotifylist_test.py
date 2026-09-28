r"""Spotify 大歌单「只列曲目 + 下载时按曲名匹配」的离线自检。

全程不联网：pathfinder 的返回用真结构的手写样本，搜索取址打桩，只读写 %TEMP%。
验的是三件事 —— 解析阶段一行音频地址都不取、匹配只认「同一首歌」、
以及 download_songs 的返回值必须和 cache_ids 一一对应（对不上就会把歌词安到别人的歌上）。

跑法：`python tests/spotifylist_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import copy
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
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


# ---------------------------------------------------------------- 样本
def track_row(name, artists, ms, typename="Track", pid="abc123", album="Best"):
    """照 pathfinder 的真结构造一行曲目（itemV2.data）。"""
    return {
        "id": pid,
        "song_link": f"https://open.spotify.com/track/{pid}",
        "itemV2": {"data": {
            "__typename": typename,
            "name": name,
            "uri": f"spotify:track:{pid}",
            "artists": {"items": [{"profile": {"name": a}} for a in artists]},
            "trackDuration": {"totalMilliseconds": ms},
            "albumOfTrack": {
                "name": album,
                "coverArt": {"sources": [
                    {"width": 64, "url": "https://i.scdn.co/small"},
                    {"width": 640, "url": "https://i.scdn.co/big"},
                ]},
            },
        }},
    }


# ---------------------------------------------------------------- 1. 时长口径
print("=== A. 时长换算：搜索结果的字符串和接口的毫秒要能放在一起比 ===")
ck("A1 纯秒数/浮点", M._dur_seconds(202) == 202 and M._dur_seconds("202.4") == 202)
ck("A2 分:秒", M._dur_seconds("3:22") == 202, M._dur_seconds("3:22"))
ck("A3 时:分:秒", M._dur_seconds("1:02:03") == 3723, M._dur_seconds("1:02:03"))
ck("A4 没时长一律 0（不参与比较）",
   M._dur_seconds("") == 0 and M._dur_seconds(None) == 0 and M._dur_seconds("-:-:-") == 0
   and M._dur_seconds("垃圾") == 0)
ck("A5 毫秒显示串", M._hms(202460) == "3:22" and M._hms(3723000) == "1:02:03", M._hms(202460))
ck("A6 0/坏值不显示 0:00", M._hms(0) == "" and M._hms(None) == "" and M._hms("x") == "")

# ---------------------------------------------------------------- 2. 只列曲目
print("=== B. 只列曲目：链接认得出、非歌条目不收 ===")
ck("B1 普通歌单链接", M._spotify_playlist_id("https://open.spotify.com/playlist/37i9dQZF1") == "37i9dQZF1")
ck("B2 区域前缀链接（intl-ja）",
   M._spotify_playlist_id("https://open.spotify.com/intl-ja/playlist/4uy6p1/track") == "4uy6p1")
ck("B3 单曲/专辑页不当歌单",
   M._spotify_playlist_id("https://open.spotify.com/track/xyz") == ""
   and M._spotify_playlist_id("https://open.spotify.com/album/xyz") == "")
d = M._spotify_track_fields(track_row("Bass Persuades", ["Miley Cyrus"], 202460))
ck("B4 曲名/歌手/专辑/时长都齐",
   d["title"] == "Bass Persuades" and d["artists"] == "Miley Cyrus"
   and d["album"] == "Best" and d["duration"] == "3:22" and d["duration_s"] == 202, d)
ck("B5 封面取最大那张", d["cover"] == "https://i.scdn.co/big", d["cover"])
ck("B6 不收任何音频地址（解析阶段不取址）",
   d["url"] == "" and d["can_musicdl_download"] is False and d["needs_match"] is True, d)
ck("B7 网页地址留在 page_url 备用", d["page_url"].endswith("/track/abc123"), d)
_no_link = track_row("Bass Persuades", ["Miley Cyrus"], 202460)
_no_link.pop("song_link")
ck("B7b 真接口没有 song_link 时从 uri 拼出单曲页",
   M._spotify_track_fields(_no_link)["page_url"] == "https://open.spotify.com/track/abc123",
   M._spotify_track_fields(_no_link)["page_url"])
_no_link["itemV2"]["data"].pop("uri")
ck("B7c 拼不出地址就留空，不编坏链接",
   M._spotify_track_fields(_no_link)["page_url"] == "")
ck("B8 播客单集/有声书不收", M._spotify_track_fields(
    track_row("Ep.1", ["某主播"], 9000, typename="Episode")) == {})
ck("B9 没名字的条目不收", M._spotify_track_fields({"itemV2": {"data": {"__typename": "Track"}}}) == {})
multi = M._spotify_track_fields(track_row("Song", ["A", "", "B"], 60000))
ck("B10 多歌手按顺序拼、空名丢掉", multi["artists"] == "A, B", multi)

# ---------------------------------------------------------------- 3. 按曲名匹配
print("=== C. 匹配：宁可不下也别下错歌 ===")
want = {"title": "不打扰", "artists": "周杰伦", "duration_s": 262, "source": "Spotify"}


def cand(title, artists, dur, src="Netease"):
    return {"id": f"c-{title}-{src}", "title": title, "artists": artists,
            "duration_s": dur, "source": src}


ck("C1 曲名+歌手+时长都对上", M._pick_track_match(want, [
    cand("别的歌", "别人", 100), cand("不打扰", "周杰伦", 260)])["title"] == "不打扰")
ck("C2 时长在容差内算同一首（262s ↔ 240s）", bool(M._pick_track_match(want, [cand("不打扰", "周杰伦", 240)])))
ck("C3 时长差太多（Live/伴奏版）不算", M._pick_track_match(want, [cand("不打扰", "周杰伦", 500)]) == {})
ck("C4 歌手不同、只差 5 秒以内才算同名歌",
   bool(M._pick_track_match(want, [cand("不打扰", "林俊杰", 265)]))
   and M._pick_track_match(want, [cand("不打扰", "林俊杰", 300)]) == {})
ck("C5 结果里一条都不对上就是没匹配到", M._pick_track_match(want, [cand("晴天", "孙燕姿", 262)]) == {})
ck("C6 空结果不炸", M._pick_track_match(want, []) == {} and M._pick_track_match(want, None) == {})
ck("C7 字符串时长也参与比较（搜索源常只给 '4:22'）",
   bool(M._pick_track_match(want, [{"id": "x", "title": "不打扰", "artists": "林俊杰",
                                    "duration": "4:22"}]))
   and M._pick_track_match(want, [{"id": "y", "title": "不打扰", "artists": "林俊杰",
                                   "duration": "9:22"}]) == {})
ck("C8 版本后缀清洗后才对上（Live/官方版）",
   bool(M._pick_track_match({"title": "不打扰 (Live)", "artists": "周杰伦", "duration_s": 262},
                            [cand("不打扰【官方Live】", "周杰伦", 262)])))
ck("C9 容差按比例：短曲差 60s 拒（262s↔202s），长曲差 55s 收（600s↔545s，绝对上限内）",
   M._pick_track_match(want, [cand("不打扰", "周杰伦", 202)]) == {}
   and bool(M._pick_track_match({"title": "交响前奏曲", "artists": "周杰伦", "duration_s": 600},
                                [cand("交响前奏曲", "周杰伦", 545)])))
_n: list = []
ck("C10 被拒原因写得出来：超容差 / 同名不同人",
   M._pick_track_match(want, [cand("不打扰", "周杰伦", 202)], _n) == {}
   and any("超出容差" in x and "60s" in x for x in _n)
   and M._pick_track_match(want, [cand("不打扰", "林俊杰", 400)], _n) == {}
   and any("歌手不同" in x for x in _n), _n)
ck("C11 反向验证：不传 notes 时行为一致、不炸",
   M._pick_track_match(want, [cand("不打扰", "周杰伦", 240)]) != {}
   and M._pick_track_match(want, [cand("不打扰", "周杰伦", 202)]) == {})

# ---------------------------------------------------------------- 4. 归档顺序
print("=== D. 归档：返回值必须跟调用方给的清单一一对应 ===")
ROOT = Path(tempfile.mkdtemp(prefix="md_spot_list_test_"))


def promo(files, cache_root, final_dir):
    return M.collect_and_promote_downloads(str(cache_root), str(final_dir), log=log,
                                           since=0, only=files)


c1 = ROOT / "cache1"
f1 = ROOT / "final1"
c1.mkdir(parents=True)
(c1 / "a.mp3").write_bytes(b"11111")
(c1 / "b.mp3").write_bytes(b"222222")
r = promo([str(c1 / "b.mp3"), "", str(c1 / "a.mp3"), str(c1 / "missing.mp3")], c1, f1)
ck("D1 按给定顺序搬，缺的位置留空串",
   [Path(p).name if p else "" for p in r] == ["b.mp3", "", "a.mp3", ""], r)
ck("D2 长度与清单一致（下标才对得回 cache id）", len(r) == 4, r)
ck("D3 文件真搬到目标目录了", (f1 / "a.mp3").is_file() and (f1 / "b.mp3").is_file())
r2 = promo([str(c1 / "a.mp3")], c1, f1)
ck("D4 源文件已不在时不报假路径", r2 == [""], r2)
# 同名同大小 → 视为重复，仍要指回第一首的最终路径
c2 = ROOT / "cache2"
f2 = ROOT / "final2"
c2.mkdir()
(c2 / "x.mp3").write_bytes(b"same")
(c2 / "sub").mkdir()
(c2 / "sub" / "x.mp3").write_bytes(b"same")
r3 = promo([str(c2 / "x.mp3"), str(c2 / "sub" / "x.mp3")], c2, f2)
ck("D5 重复的那首指到同一份成品，不返回空", r3[0] == r3[1] and r3[1], r3)
# 不带 only 的旧模式（按 mtime 扫）行为不变
c3 = ROOT / "cache3"
f3 = ROOT / "final3"
c3.mkdir()
(c3 / "old.mp3").write_bytes(b"9999999")
time.sleep(1.1)
(c3 / "new.mp3").write_bytes(b"8888888")
r4 = M.collect_and_promote_downloads(str(c3), str(f3), log=log, since=time.time() - 0.5)
ck("D6 旧扫描模式只收本次新写的", [Path(p).name for p in r4] == ["new.mp3"], r4)
shutil.rmtree(ROOT, ignore_errors=True)

# ---------------------------------------------------------------- 5. download_songs 接线
print("=== E. 下载：占位条目先匹配，没匹配到的跳过且不碰下载 ===")
OUT = Path(tempfile.mkdtemp(prefix="md_spot_dl_test_"))
DL = OUT / "dl"
DL.mkdir(parents=True)
CACHE = DL / "_musicdl_cache"
CACHE.mkdir(parents=True)


class FakeSong:
    def __init__(self, name, artists, source, sub):
        self.song_name, self.singers, self.source = name, artists, source
        # 真 musicdl 在搜索阶段就把"计划路径"填进 save_path，同名歌还会排成 "xxx (1).flac"；
        # 落盘的却是它内部副本重算出来的名字 —— 两个字符串不一样，实测少一步就对不上。
        self.save_path = str(CACHE / name / f"{name} (1).mp3")
        self._sub = sub
        self.lyric = ""
        self.cover_url = ""


class FakeClient:
    def __init__(self):
        self.given = []

    def download(self, song_infos=None):
        self.given = list(song_infos or [])
        ok = []
        for s in self.given:
            if s._sub == "skip":       # 假装这一首取址失败
                continue
            d = CACHE / s.song_name    # musicdl 给每首歌单开一个目录
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{s.song_name}.mp3"
            p.write_bytes(b"audio-" + s.song_name.encode("utf-8"))
            cp = copy.copy(s)          # 落盘改的是副本，传进去那份保持过时路径
            cp.save_path = str(p)
            ok.append(cp)
        return ok


FAKE = FakeClient()
SEARCHED: list[str] = []
_real = (M.musicdl_available, M._build_client, M._search_one_source,
         M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover, M.musicdl_cache_dir)
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: FAKE
M.musicdl_cache_dir = lambda base="": str(CACHE)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}


def fake_search(src, keyword, **kw):
    SEARCHED.append(f"{src}|{keyword}")
    if "命中" in keyword:
        s = FakeSong("命中", "某歌手", src, "ok")
        return [{"id": M._cache_song(s), "title": "命中", "artists": "某歌手",
                 "duration_s": 200}], []
    if "取址失败" in keyword:
        s = FakeSong("取址失败", "某歌手", src, "skip")
        return [{"id": M._cache_song(s), "title": "取址失败", "artists": "某歌手",
                 "duration_s": 200}], []
    return [], []


M._search_one_source = fake_search


def ph(title, dur=200):
    it = {"id": "", "title": title, "artists": "某歌手", "duration_s": dur,
          "duration": "3:20", "source": "Spotify", "url": "", "needs_match": True}
    it["id"] = M._cache_song(it)
    return it


e1 = ph("命中")
e2 = ph("查无此歌")
e3 = ph("取址失败")
hit_id, miss_id, skip_id = e1["id"], e2["id"], e3["id"]
paths = M.download_songs([hit_id, miss_id, skip_id], work_dir=str(DL), log=log)
ck("E1 返回与 ids 等长且按位对齐", len(paths) == 3, paths)
ck("E2 匹配到的那首落在自己的位置上",
   Path(paths[0]).name == "命中.mp3", paths)
ck("E2b 用的是真正落盘的名字，不是搜索时那份带 ' (1)' 的计划路径",
   Path(FAKE.given[0].save_path).name == "命中 (1).mp3", FAKE.given[0].save_path)
ck("E3 没匹配到的既不下载也不占位", paths[1] == "", paths)
ck("E4 匹配到但取址失败的位置留空", paths[2] == "", paths)
ck("E5 只把匹配成功的歌交给 musicdl",
   [s.song_name for s in FAKE.given] == ["命中", "取址失败"], [s.song_name for s in FAKE.given])
ck("E6 占位条目已原地换成真 SongInfo（调用方的 id 不用换）",
   isinstance(M.get_cached_song(hit_id), FakeSong), type(M.get_cached_song(hit_id)).__name__)
ck("E7 没匹配上的仍是占位 dict（下回还能再试）",
   isinstance(M.get_cached_song(miss_id), dict) and M.get_cached_song(miss_id).get("needs_match"))
ck("E8 按「歌手 + 曲名」搜，且命中即停不再搜下一个源",
   any(x.endswith("某歌手 命中") for x in SEARCHED) and
   sum(1 for x in SEARCHED if "命中" in x) == 1, SEARCHED)
ck("E9 汇总里列出没匹配到的曲名，不静默丢",
   any("查无此歌" in m for m in LOGS), [m for m in LOGS if "没找到" in m])
ck("E10 用户勾了源就按勾的匹配",
   M.download_songs([miss_id], work_dir=str(DL), log=log,
                    match_sources=["QQMusicClient"]) == [""]
   and any(x.startswith("QQMusicClient|") for x in SEARCHED[-1:]), SEARCHED[-3:])
SEARCHED.clear()
ck("E11 纯网易云/QQ 的正常条目不受影响（不做任何匹配搜索）",
   M.download_songs([hit_id], work_dir=str(DL), log=log) != [] and not SEARCHED, SEARCHED)
M.musicdl_available, M._build_client, M._search_one_source, M.fetch_lyric_fallback_cn, \
    M.save_lyrics_and_cover, M.musicdl_cache_dir = _real
shutil.rmtree(OUT, ignore_errors=True)

# ---------------------------------------------------------------- 6. 分片推进下载
print("=== F. 分片下载：每片下完就归档、逐首回报，不用等整批 ===")
OUT2 = Path(tempfile.mkdtemp(prefix="md_spot_chunk_test_"))
DL2 = OUT2 / "dl"
DL2.mkdir()
CACHE2 = DL2 / "_musicdl_cache"
CACHE2.mkdir()
CALLS: list[list] = []      # 每次 client.download 收到的曲名
PROMOTES: list[int] = []    # 每次归档收到的文件数


class ChunkClient:
    def download(self, song_infos=None):
        infos = list(song_infos or [])
        CALLS.append([s.song_name for s in infos])
        ok = []
        for s in infos:
            d = CACHE2 / s.song_name
            d.mkdir(exist_ok=True)
            p = d / f"{s.song_name}.mp3"
            p.write_bytes(b"x" * (1000 + len(s.song_name)))
            cp = copy.copy(s)
            cp.save_path = str(p)      # 落盘的是副本的名字，跟计划路径无关
            ok.append(cp)
        return ok


_real2 = (M.musicdl_available, M._build_client, M.collect_and_promote_downloads,
          M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover, M.musicdl_cache_dir)
_promote = M.collect_and_promote_downloads


def spy_promote(cache_root, final_dir, **kw):
    PROMOTES.append(len([p for p in (kw.get("only") or []) if p]))
    return _promote(cache_root, final_dir, **kw)


M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: ChunkClient()
M.musicdl_cache_dir = lambda base="": str(CACHE2)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}
M.collect_and_promote_downloads = spy_promote

ids5 = []
for n in ["aa", "bb", "cc", "dd", "ee"]:
    s = FakeSong(n, "某歌手", "NeteaseMusicClient", "ok")
    s.save_path = str(CACHE2 / n / f"{n}.mp3")
    ids5.append(M._cache_song(s))
EVENTS: list = []
paths5 = M.download_songs(ids5, work_dir=str(DL2), log=log, chunk=2,
                          on_result=lambda i, p: EVENTS.append(
                              (i, Path(p).name if p else "")))
ck("F1 按 chunk 首一片调用 musicdl（2+2+1）", [len(c) for c in CALLS] == [2, 2, 1], CALLS)
ck("F2 每片各归档一次（不是整批结束才搬）", PROMOTES == [2, 2, 1], PROMOTES)
ck("F3 逐首回报，下标与曲名都对位",
   EVENTS == [(0, "aa.mp3"), (1, "bb.mp3"), (2, "cc.mp3"), (3, "dd.mp3"), (4, "ee.mp3")],
   EVENTS)
ck("F4 返回值仍与 ids 等长", len(paths5) == 5 and all(paths5), paths5)
ck("F5 每片结束写一条进度",
   any("下载进度 2/5" in m for m in LOGS) and any("下载进度 5/5" in m for m in LOGS),
   [m for m in LOGS if "下载进度" in m])
ck("F6 开始时就说清每片归档一次",
   any("每 2 首一片" in m and "不用等整批" in m for m in LOGS),
   [m for m in LOGS if "开始下载" in m])
CALLS.clear()
PROMOTES.clear()
LOGS.clear()
M.download_songs(ids5, work_dir=str(DL2), log=log, chunk=0)
ck("F7 chunk<=0 退回整批一次下完",
   [len(c) for c in CALLS] == [5] and PROMOTES == [5]
   and not any("下载进度" in m for m in LOGS), (CALLS, PROMOTES))

# ---------------------------------------------------------------- 7. 匹配源回落要报原因
print("=== G. 匹配源：回落可以，静默不行 ===")
M._search_one_source = fake_search
LOGS.clear()
SEARCHED.clear()
M.resolve_placeholders([("cid_sp", {"title": "命中", "artists": "某歌手", "duration_s": 200})],
                       sources=["SpotifyMusicClient"], work_dir=str(DL2), log=log)
ck("G1 勾了 Spotify 就真去 Spotify 匹配（第三方转链能取到地址，不再被剔除）",
   SEARCHED and all(x.startswith("SpotifyMusicClient|") for x in SEARCHED)
   and not any("回落到默认匹配源" in m for m in LOGS), (LOGS, SEARCHED))
ck("G2 用这类源时要提示取址慢（经第三方转链）",
   any("第三方转链" in m for m in LOGS), LOGS)
LOGS.clear()
SEARCHED.clear()
M.resolve_placeholders([("cid_none", {"title": "命中", "artists": "某歌手", "duration_s": 200})],
                       sources=[], work_dir=str(DL2), log=log)
ck("G3 没指定匹配源时写「没指定」而不是「勾选的源没用」",
   any("没指定匹配源" in m for m in LOGS) and not any("勾选的源" in m for m in LOGS), LOGS)
LOGS.clear()
SEARCHED.clear()
M.resolve_placeholders([("cid_qq", {"title": "命中", "artists": "某歌手", "duration_s": 200})],
                       sources=["QQMusicClient"], work_dir=str(DL2), log=log)
ck("G4 指定了可用源就不回落、也不写警告",
   not any("回落" in m for m in LOGS)
   and SEARCHED and all(x.startswith("QQMusicClient|") for x in SEARCHED), (LOGS, SEARCHED))
M.musicdl_available, M._build_client, M.collect_and_promote_downloads, \
    M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover, M.musicdl_cache_dir = _real2
shutil.rmtree(OUT2, ignore_errors=True)

# ---------------------------------------------------------------- H. 进度条不许炸下载
# 线上实测：50 首一批里第 2/3/4 片报 "'gbk' codec can't encode character '\u2838' in position 0"。
# 那是 rich 的 SpinnerColumn —— Progress 退出时还要把最后一帧转圈符写进 stdout，而服务的 stdout
# 重定向到文件后按 GBK 编码。异常发生在文件已下完、还没归档时，整片成品就烂在缓存里。
# 只能在子进程里验：得让 stdout 真的是一股 GBK 文件流。
CHILD = r'''
import sys
sys.path.insert(0, sys.argv[1])
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
if sys.argv[2] == "1":
    import music_search
    music_search._harden_console_encoding()
print("INFO enc=%s errors=%s" % (sys.stdout.encoding, sys.stdout.errors))
try:
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(bar_width=None)) as p:
        a = p.add_task("song A", total=1)
        p.advance(a, 1)
        p.add_task("song B", total=1)          # 退出时仍在转圈
    print("RESULT OK")
except UnicodeEncodeError as e:
    print("RESULT BOOM %s" % e)
    sys.exit(3)
'''
ROOT = str(Path(__file__).resolve().parent.parent)
_child_py = Path(tempfile.mkdtemp(prefix="md_rich_")) / "child.py"
_child_py.write_text(CHILD, encoding="utf-8")

def run_child(harden: bool):
    out = _child_py.parent / ("out_%d.txt" % int(harden))
    with open(out, "wb") as fp:
        rc = subprocess.call([sys.executable, str(_child_py), ROOT, "1" if harden else "0"],
                             stdout=fp, stderr=subprocess.STDOUT)
    return rc, out.read_text(encoding="utf-8", errors="replace")

rc_h, t_h = run_child(True)
ck("H1 加固后进度条收尾不再中断下载", rc_h == 0 and "RESULT OK" in t_h, (rc_h, t_h.strip()[:160]))
rc_p, t_p = run_child(False)
_info = [l for l in t_p.splitlines() if l.startswith("INFO")]
_lenient = "errors=replace" in (_info[0] if _info else "") or "enc=utf-8" in (_info[0] if _info else "")
if _lenient:
    print(f"SKIP H2 本机 stdout 本来就容错（{_info}），反向验证不适用")
else:
    ck("H2 反向验证：不加固确实复现线上报错", rc_p == 3 and "RESULT BOOM" in t_p, (rc_p, t_p.strip()[:160]))
# _build_client 是搜索/解析歌单/下载三条路径共同的入口，加固必须挂在那里，不能只挂在下载
ck("H3 加固挂在 _build_client 上（三条 musicdl 路径共用）",
   "_harden_console_encoding(log)" in Path(ROOT, "music_search.py").read_text(encoding="utf-8"), "")
shutil.rmtree(str(_child_py.parent), ignore_errors=True)

# ---------------------------------------------------------------- I. 分片中断不吞成品
print("=== I. 分片中断：文件已经落盘就不能整片丢 ===")
OUT3 = Path(tempfile.mkdtemp(prefix="md_spot_boom_test_"))
DL3 = OUT3 / "dl"
DL3.mkdir()
CACHE3 = DL3 / "_musicdl_cache"
CACHE3.mkdir()
BOOM_CALLS: list[int] = []
WRITE_FILES = [True]          # 关掉时：抛错前一个文件都不写
ALWAYS_BOOM = [False]         # 打开时：逐首重试也照抛，缓存里始终空空


class BoomClient:
    """第一片：撞上坏路径就抛，抛之前只写下同片里没炸的那几首（线上真是这样——
    musicdl 用线程池，一首先炸、其余有的下完有的没轮到）；第二片正常返回。"""

    def __init__(self):
        self.n = 0

    def download(self, song_infos=None):
        infos = list(song_infos or [])
        self.n += 1
        BOOM_CALLS.append(len(infos))
        if ALWAYS_BOOM[0] or self.n == 1:
            if WRITE_FILES[0]:
                for s in infos[1:]:
                    d = CACHE3 / s.song_name
                    d.mkdir(exist_ok=True)
                    (d / f"{s.song_name}.mp3").write_bytes(b"y" * 900)
            raise OSError(2, "系统找不到指定的文件。", "\\\\?\\H:/")
        ok = []
        for s in infos:
            d = CACHE3 / s.song_name
            d.mkdir(exist_ok=True)
            p = d / f"{s.song_name}.mp3"
            p.write_bytes(b"y" * 900)
            cp = copy.copy(s)
            cp.save_path = str(p)
            ok.append(cp)
        return ok


_real5 = (M.musicdl_available, M._build_client, M.fetch_lyric_fallback_cn,
          M.save_lyrics_and_cover, M.musicdl_cache_dir)
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: BoomClient()
M.musicdl_cache_dir = lambda base="": str(CACHE3)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}
ids4 = []
for n in ["aa", "bb", "cc", "dd"]:
    s = FakeSong(n, "某歌手", "NeteaseMusicClient", "ok")
    # 计划路径指向一个从未被写过的文件名，逼兜底按 work_dir + 曲名去认成品
    s.save_path = str(CACHE3 / n / f"{n} (1).mp3")
    ids4.append(M._cache_song(s))
LOGS.clear()
paths4 = M.download_songs(ids4, work_dir=str(DL3), log=log, chunk=2)
M.musicdl_available, M._build_client, M.fetch_lyric_fallback_cn, \
    M.save_lyrics_and_cover, M.musicdl_cache_dir = _real5
ck("I1 中断那一片的成品照样归档，返回值与 ids 等长",
   len(paths4) == 4 and all(paths4), paths4)
ck("I2 归档后的文件真在最终目录里",
   all((DL3 / f"{n}.mp3").is_file() for n in ["aa", "bb", "cc", "dd"]),
   sorted(p.name for p in DL3.iterdir()))
ck("I3 报错带上调用栈尾，并说明改从缓存找",
   any("片下载中断" in m and "栈尾" in m and "File " in m and "改从缓存里找" in m for m in LOGS),
   [m for m in LOGS if "中断" in m])
ck("I4 写明这一片救回几首", any("中断后从缓存救回 2/2 首" in m for m in LOGS),
   [m for m in LOGS if "救回" in m])
ck("I5 中断不影响后面的片", BOOM_CALLS == [2, 1, 2]
   and any("下载进度 4/4 首（成功 4 首" in m for m in LOGS), (BOOM_CALLS, LOGS[-3:]))
ck("I8 整片抛错时没落盘的那首被逐首重试补回（不再跟着坏路径一起丢）",
   any("逐首重试补回 1 首" in m for m in LOGS) and (DL3 / "aa.mp3").is_file(),
   [m for m in LOGS if "重试" in m])
# 反向验证：缓存里什么都没有时，救回计数必须是 0，不能白报成功
DL4 = OUT3 / "dl4"
DL4.mkdir()
CACHE4 = DL4 / "_musicdl_cache"
CACHE4.mkdir()
WRITE_FILES[0] = False
ALWAYS_BOOM[0] = True         # 逐首重试也照样抛：这条才测得出救回计数会不会虚报
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: BoomClient()
M.musicdl_cache_dir = lambda base="": str(CACHE4)
ids2 = [M._cache_song(FakeSong(n, "某歌手", "NeteaseMusicClient", "ok")) for n in ["ee", "ff"]]
LOGS.clear()
paths2 = M.download_songs(ids2, work_dir=str(DL4), log=log, chunk=2)
WRITE_FILES[0] = True
ALWAYS_BOOM[0] = False
M.musicdl_available, M._build_client, M.fetch_lyric_fallback_cn, \
    M.save_lyrics_and_cover, M.musicdl_cache_dir = _real5
ck("I6 反向验证：一首都没落盘时如实报救回 0/2，位置留空",
   paths2 == ["", ""] and any("中断后从缓存救回 0/2 首" in m for m in LOGS),
   (paths2, [m for m in LOGS if "救回" in m]))
ck("I7 反向验证：此时最终目录里没有多出文件",
   not any(p.suffix == ".mp3" for p in DL4.iterdir()), sorted(p.name for p in DL4.iterdir()))
ck("I9 反向验证：一首都没补回来时不许写「逐首重试补回」",
   not any("逐首重试补回" in m for m in LOGS), [m for m in LOGS if "重试" in m])

# ---------------------------------------------------------------- J. 超时未搜 ≠ 没找到
print("=== J. 匹配预算用尽：没轮到搜的不能说成没找到 ===")
_real6 = (M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_WORKERS, M._search_one_source)
SLOW = ["慢A", "慢B", "慢C", "慢D", "慢E", "慢F"]


def j_search(src, keyword, **kw):
    if any(t in keyword for t in SLOW):
        # 真实搜索是秒级的。打桩瞬间返回的话，预算到期时几首早就搜完了，
        # 「本轮没轮到搜」那条分支根本跑不到 —— 必须让它们还排在队列里。
        time.sleep(0.5)
        return [], []
    return fake_search(src, keyword, **kw)


M._search_one_source = j_search
M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_WORKERS = 0.2, 1   # 只有没开跑的能被取消
LOGS.clear()
M.resolve_placeholders([("c_hit", {"title": "命中", "artists": "某歌手", "duration_s": 200})]
                       + [(f"c_slow{i}", {"title": t, "artists": "某歌手", "duration_s": 200})
                          for i, t in enumerate(SLOW)],
                       sources=["NeteaseMusicClient"], work_dir=str(DL3), log=log)
M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_WORKERS, M._search_one_source = _real6

ran = {t for t in SLOW if any(f"：{t} → 没找到" in m for m in LOGS)}
lazy = {t for t in SLOW if any(f"：{t} → 本轮没轮到搜" in m for m in LOGS)}
lazy_line = next((m for m in LOGS if "本轮没轮到搜" in m and "不是没找到" in m), "")
_miss_i = next((i for i, m in enumerate(LOGS) if "按曲名没找到" in m), -1)
MISS_BLOCK = "｜".join(LOGS[_miss_i + 1:_miss_i + 9]) if _miss_i >= 0 else ""
ck("J1 超预算没搜的单独汇总一条，写明不是没找到", bool(lazy_line),
   [m for m in LOGS if "没轮到" in m])
ck("J2 每首慢歌都被归进「搜过没找到」或「没轮到搜」之一，不重不漏",
   ran | lazy == set(SLOW) and not (ran & lazy), (sorted(ran), sorted(lazy)))
ck("J3 6 首慢歌里至少 3 首算「没轮到搜」（超时时在跑的至多 2 首）", len(lazy) >= 3, sorted(lazy))
ck("J4 「按曲名没找到」那条里不能出现没轮到搜的歌",
   _miss_i >= 0 and all(t not in MISS_BLOCK for t in lazy), MISS_BLOCK)
ck("J5 预算到期前搜到的那首照常算命中",
   any("命中" in m and "Netease" in m for m in LOGS), [m for m in LOGS if "命中" in m])
LOGS.clear()
M.resolve_placeholders([("c_miss", {"title": "没这种歌", "artists": "某歌手", "duration_s": 200})],
                       sources=["NeteaseMusicClient"], work_dir=str(DL3), log=log)
j6_i = next((i for i, m in enumerate(LOGS) if "按曲名没找到" in m), -1)
ck("J6 反向验证：正常搜过没命中的仍然说没找到",
   j6_i >= 0 and "没这种歌" in "｜".join(LOGS[j6_i + 1:j6_i + 5]), LOGS)

# ---------------------------------------------------------------- K. 栈尾要指得出调用方
print("=== K. 报错的栈尾：不能三帧都在 os 里转圈 ===")
import os as _k_os
import traceback as _k_tb


def k_tail():
    try:
        # 线上就是这种带子目录的深路径：makedirs 先递归建父目录（几帧全在 <frozen os>），
        # 最后在最上层那截炸掉，所以只截最后三帧根本看不到调用方。
        _k_os.makedirs("\\\\?\\H:/" + "md_tb_probe/_musicdl_cache/xxx")
    except Exception:
        raw = [ln.strip() for ln in _k_tb.format_exc().splitlines()
               if ln.strip().startswith("File ")]
        return M._tb_tail(), " <- ".join(raw[-3:])
    return "", ""


k_new, k_raw = k_tail()
ck("K1 栈尾剔掉标准库帧，剩下真正调 makedirs 的一方",
   "<frozen" not in k_new and "spotifylist_test.py" in k_new and "in k_tail" in k_new, k_new)
ck("K2 反向验证：不剔噪时最后三帧全在 <frozen os> 里，指不到调用方",
   k_raw.count("<frozen os>") == 3 and "spotifylist_test" not in k_raw, k_raw)

# ---------------------------------------------------------------- 结果
print("\n=== 结果 ===")
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
