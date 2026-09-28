r"""成品音频来源诚实（①）+ 搬运版守门（②）的离线自检。

不联网、不碰下载目录：audio_origin 用构造的 SongInfo 直接判；守门那一段把 download_songs
外围的 musicdl 客户端、归档、歌词补全全部换成替身，只让它跑真实的分支逻辑。
跑法：`python tests/origin_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def song(**kw):
    base = dict(source="NeteaseMusicClient", song_name="", singers="", duration="",
                duration_s=0, album="", download_url="", raw_data={})
    base.update(kw)
    return SimpleNamespace(**base)


def sp_raw(name="歸期", artists=("錢潤玉",), ms=279000):
    """照 musicdl 各家转链站的形状：search 是 Spotify 那半边，download 是站子给的那半边。"""
    return {"search": {"item": {"data": {"name": name, "artists": [{"name": a} for a in artists],
                                        "duration_ms": ms}}},
            "download": {"url": "https://spotisaver.net/dl/x1",
                         "youtubeUrl": "https://www.youtube.com/watch?v=abc123"}}


# 用户在 Spotify 歌单里点开的那一行（繁體、279s），和从转链站取回的成品（简体、280s）
WANT = {"title": "歸期", "artists": "錢潤玉", "dur": 279}
RELAY = song(source="SpotifyMusicClient", song_name="归期", singers="钱润玉",
             duration="4:40", duration_s=280, raw_data=sp_raw(),
             download_url="https://spotisaver.net/dl/x1")
NETEASE = song(source="NeteaseMusicClient", song_name="归期", singers="钱润玉",
               duration="4:39", duration_s=279,
               download_url="https://music.163.com/song/media/outer/url?id=1.mp3")

# ---- 1) 来源判定 ----
o = M.audio_origin(NETEASE)
ck("O1 国内平台命中时来源就是它自己，不标转链",
   o["official"] and not o["unofficial"] and o["label"] == "Netease" and not o["reasons"],
   repr({k: o[k] for k in ("official", "label", "reasons")}))

o = M.audio_origin(RELAY, WANT)
ck("O2 Spotify 那行的来源链写清是转链站 + YouTube",
   o["unofficial"] and not o["official"] and o["label"] == "Spotify → YouTube"
   and o["via"] == "spotisaver",
   repr({k: o[k] for k in ("label", "via", "youtube")}))
ck("O3 理由里点名「Spotify 不给音频」和 YouTube 直链",
   any("不给出音频" in r for r in o["reasons"])
   and any("youtube.com/watch?v=abc123" in r for r in o["reasons"]),
   repr(o["reasons"]))
ck("O4 繁體标注与简体成品经繁简归一后算同一首歌，时长差 1s 在容差内 —— 不算搬运版",
   not o["reupload"] and not o["mismatch"], repr(o["mismatch"]))

ck("O5 want 缺失时退回 raw_data 里 Spotify 自标的元数据（搜索路径也判得了）",
   M.audio_origin(RELAY)["label"] == "Spotify → YouTube"
   and not M.audio_origin(RELAY)["reupload"])

LIVE = song(source="SpotifyMusicClient", song_name="归期 (Live)", singers="钱润玉",
            duration="6:12", duration_s=372, raw_data=sp_raw(),
            download_url="https://spotisaver.net/dl/x1")
o = M.audio_origin(LIVE, WANT)
ck("O6 现场版顶了原唱的名：时长差 93s 判为搬运版",
   o["reupload"] and any(r.startswith("时长差") for r in o["mismatch"]), repr(o["mismatch"]))

COVER = song(source="SpotifyMusicClient", song_name="归期", singers="某个翻唱号",
             duration="4:39", duration_s=279, raw_data=sp_raw(),
             download_url="https://spotisaver.net/dl/x1")
o = M.audio_origin(COVER, WANT)
ck("O7 歌手对不上判为搬运版（曲名、时长都对得上也不能放行）",
   o["reupload"] and any(r.startswith("歌手对不上") for r in o["mismatch"]), repr(o["mismatch"]))

ck("O8 搬运版理由不混进来源说明：reasons 是全部，mismatch 只有对不上的那几条",
   len(o["reasons"]) > len(o["mismatch"])
   and all(any(r in m for r in o["reasons"]) for m in o["mismatch"]),
   repr(o["reasons"]))


def with_tol(tol):
    saved = M.REUPLOAD_DUR_TOL_S
    M.REUPLOAD_DUR_TOL_S = tol
    try:
        return M.audio_origin(LIVE, WANT)["reupload"]
    finally:
        M.REUPLOAD_DUR_TOL_S = saved


ck("O9 反向验证：把时长容差放到 200s，现场版就不再被判为搬运版（判定确实只看这条容差）",
   with_tol(200) is False and with_tol(3) is True)

# ---- 2) 落到搜索行 ----
row_sp = M._songinfo_to_dict(RELAY, "SpotifyMusicClient")
ck("R1 Spotify 转链行带上 real_source / unofficial，界面来源列才有的可显示",
   row_sp["real_source"] == "Spotify → YouTube" and row_sp["unofficial"] is True,
   repr({k: row_sp.get(k) for k in ("source", "real_source", "unofficial")}))
row_ne = M._songinfo_to_dict(NETEASE, "NeteaseMusicClient")
ck("R2 网易云那行不被误标（来源列不出现转链）",
   row_ne["real_source"] == "Netease" and row_ne["unofficial"] is False
   and row_ne["reupload_suspect"] is False,
   repr({k: row_ne.get(k) for k in ("source", "real_source", "unofficial")}))
row_bad = M._songinfo_to_dict(LIVE, "SpotifyMusicClient")
ck("R3 现场版那行 reupload_suspect 为真，且 origin_reasons 带得出对不上的理由",
   row_bad["reupload_suspect"] is True and any("时长差" in r for r in row_bad["origin_reasons"]),
   repr(row_bad["origin_reasons"]))
ck("R4 老字段一个没少（来源列只是多标一件事，不改动原有行结构）",
   all(k in row_sp for k in ("id", "title", "artists", "duration", "duration_s", "album",
                             "source", "musicdl_source", "url", "quality", "cover",
                             "can_musicdl_download")))

# ---- 3) download_songs 的守门 ----
# 替身只覆盖外围（musicdl 客户端、归档、歌词），download_songs 自己的分支一行都不改。
def run_batch(with_gate: bool, tmp: str, force_reupload: bool = False):
    logs: list[str] = []
    seen: list[list] = []
    files: dict[str, str] = {}

    def _log(msg, level="info"):
        logs.append(f"[{level}] {msg}")

    good = song(source="SpotifyMusicClient", song_name="归期", singers="钱润玉",
                duration="4:40", duration_s=280, raw_data=sp_raw(),
                download_url="https://spotisaver.net/dl/x1")
    live = song(source="SpotifyMusicClient", song_name="归期 (Live)", singers="钱润玉",
                duration="6:12", duration_s=372, raw_data=sp_raw(),
                download_url="https://spotisaver.net/dl/x2")
    plain = song(source="NeteaseMusicClient", song_name="别的歌", singers="某人",
                 duration="3:00", duration_s=180)
    by_cid = {"c_good": good, "c_live": live, "c_plain": plain}
    # 占位（用户点开的歌单行）匹配前就存在，守门的基准从这里来
    placeholders = {"c_good": {"title": "歸期", "artists": "錢潤玉", "duration_s": 279},
                    "c_live": {"title": "歸期", "artists": "錢潤玉", "duration_s": 279},
                    "c_plain": {"title": "别的歌", "artists": "某人", "duration_s": 180}}

    class FakeClient:
        def download(self, song_infos=None):
            got = list(song_infos or [])
            seen.append([id(x) for x in got])
            for s in got:
                p = Path(tmp) / f"{s.song_name}.mp3"
                p.write_bytes(b"x")
                s.save_path = str(p)
                files[id(s)] = str(p)
            return got

    saved = {k: getattr(M, k) for k in
             ("musicdl_available", "get_cached_song", "_build_client", "_guard_song_paths",
              "collect_and_promote_downloads", "musicdl_cache_dir", "fetch_lyric_fallback_cn",
              "save_lyrics_and_cover", "audio_origin")}
    real_origin = saved["audio_origin"]
    if force_reupload:
        def _origin(song, want=None):
            o = dict(real_origin(song, want))
            o["reupload"] = True
            o["mismatch"] = ["（自检注入：恒定判为对不上）"]
            return o
        M.audio_origin = _origin
    try:
        M.musicdl_available = lambda: True
        M.get_cached_song = lambda cid: by_cid.get(cid) or placeholders.get(cid)
        M._build_client = lambda *a, **k: FakeClient()
        M._guard_song_paths = lambda items, out_dir, log=None: 0
        M.musicdl_cache_dir = lambda base: tmp
        M.collect_and_promote_downloads = (
            lambda cache, out_dir, log=None, since=None, only=None: list(only or []))
        M.fetch_lyric_fallback_cn = lambda *a, **k: ""
        M.save_lyrics_and_cover = lambda *a, **k: None
        paths = M.download_songs(["c_good", "c_live", "c_plain"], work_dir=tmp, log=_log,
                                 chunk=0, block_reupload=with_gate)
    finally:
        for k, v in saved.items():
            setattr(M, k, v)
    return paths, logs, seen, by_cid


with tempfile.TemporaryDirectory() as tmp:
    paths, logs, seen, by_cid = run_batch(False, tmp)
    flat = "\n".join(logs)
    ck("D1 开关关着时三首照旧全下（守门默认不影响现有行为）",
       len(seen[0]) == 3 and all(paths), repr(paths))
    ck("D2 关着也会把真实来源写进下载日志",
       "音频来源 Spotify → YouTube" in flat,
       repr([ln for ln in logs if "已下载" in ln]))

    paths, logs, seen, by_cid = run_batch(True, tmp)
    ck("D3 开关打开后现场版不进下载队列",
       len(seen[0]) == 2 and id(by_cid["c_live"]) not in seen[0], repr(seen))
    ck("D4 被拦的那首在返回列表里占位为空（下标仍然对得上）",
       paths[0] and not paths[1] and paths[2], repr(paths))
    flat = "\n".join(logs)
    ck("D5 拦下时当场说明为什么拦",
       "疑似搬运版，按开关不下" in flat and "时长差 93s" in flat,
       repr([ln for ln in logs if "搬运版" in ln]))
    tail = flat.split("本次未下载：")[1] if "本次未下载：" in flat else ""
    ck("D6 结束后完整列出被拦曲目清单（曲名 + 理由都在）",
       "以下 1 首被判为搬运版" in flat and "归期 (Live)" in tail and "时长差 93s" in tail,
       repr(tail[:160]))
    ck("D7 网易云那首不被牵连（来源正当的歌一行都不标）",
       "音频来源" not in [ln for ln in logs if "别的歌" in ln][0],
       repr([ln for ln in logs if "别的歌" in ln]))

    # 反向验证：判定恒定报"对不上"时，守门必须真能把整批拦空
    paths, logs, seen, _ = run_batch(True, tmp, force_reupload=True)
    flat = "\n".join(logs)
    ck("D8 反向验证：判定全部不通过时三首都不交给 musicdl，报错点名是开关拦的",
       not seen and not any(paths) and "3 首被搬运版开关拦下" in flat,
       repr([paths, [ln for ln in logs if "没有有效曲目" in ln]]))

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
