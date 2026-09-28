r"""本地音频元数据：读文件自带标签，而不是猜文件名；读过不重复解析。

起因：本地音乐与资源库以前只按「歌手 - 歌名」的文件名拆字段，时长/品质恒为空，
无损成品到底是不是无损看不见（#127 缺判据），每次扫描还把整目录重解析一遍。

跑法：`python tests/localmeta_test.py`（不需要先起 server）。
全部产物落在 %TEMP%\md_localmeta_test\<时刻>\，绝不碰真实下载目录 / config / 索引。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

APP = pathlib.Path(__file__).resolve().parent.parent
FFMPEG = APP / "tools" / "ffmpeg.exe"
if not FFMPEG.is_file():
    FFMPEG = pathlib.Path(shutil.which("ffmpeg") or "ffmpeg")

ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_localmeta_test"
SHARD = ROOT / time.strftime("%H%M%S")
SUB = SHARD / "周杰伦"          # 模板归档的真实形状：歌手动子目录
# 索引已搬到程序目录（web_app/local_index），测试必须把它拐进 Temp，绝不写真目录
INDEX_DIR = SHARD / "index_dir"
M._LOCAL_INDEX_DIR = INDEX_DIR
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


def run(args):
    return subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"] + args,
                          capture_output=True, text=True, timeout=120,
                          encoding="utf-8", errors="replace")


def ffprobe_of(p):
    exe = M.find_ffprobe()
    assert exe, "随包 ffprobe 应当在，否则下面的断言没有意义"
    r = subprocess.run([exe, "-v", "quiet", "-print_format", "json", "-show_streams", str(p)],
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace")
    return r.stdout or ""


# ── 造素材：ffmpeg 真写出来的标签，不是我们自己的写入器 ──────────────
SUB.mkdir(parents=True)
PPM = SHARD / "cover.ppm"
PPM.write_bytes(b"P6\n8 8\n255\n" + bytes(range(192)))

TAGGED = SUB / "文件名是猜的 - 文件名歌手.mp3"     # 标签与文件名故意对不上
r1 = run(["-f", "lavfi", "-i", "sine=frequency=440:duration=3",
          "-i", str(PPM), "-map", "0:a", "-map", "1:v",
          "-disposition:v:0", "attached_pic", "-id3v2_version", "3",
          "-b:a", "192k",
          "-metadata", "title=晴天", "-metadata", "artist=周杰伦",
          "-metadata", "album=八度空间",
          "-metadata", "lyrics=[00:01.00]第一行歌词\n[00:02.00]第二行歌词",
          str(TAGGED)])

LOSSY = SHARD / "plain.mp3"                        # 无标签 + 同名 jpg/lrc 兜底
r2 = run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-b:a", "192k", str(LOSSY)])

FLAC = SHARD / "lossless.flac"                     # 48kHz / 24bit 无损
r3 = run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2",
          "-ar", "48000", "-sample_fmt", "s32", str(FLAC)])

CLIP = SHARD / "clip.mp4"                           # 真视频：验音频口径没把它带偏
r4 = run(["-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=10", str(CLIP)])

ck("T0 四个素材都由 ffmpeg 造出来了",
   all(x.returncode == 0 for x in (r1, r2, r3, r4)),
   "|".join((x.stderr or "")[:60] for x in (r1, r2, r3, r4)))
if FAILED:
    print("素材都没造出来，后面全部作废")
    sys.exit(1)
FLAC_PROBE = ffprobe_of(FLAC).replace(" ", "").replace("\n", "")
ck("T0b 素材本身确实是 24bit/48kHz（ffprobe 独立佐证，不是我们自说自话）",
   '"bits_per_raw_sample":"24"' in FLAC_PROBE or '"bits_per_sample":"24"' in FLAC_PROBE,
   FLAC_PROBE[:200])
LOSSY.with_suffix(".jpg").write_bytes(b"\xff\xd8\xff\xe0junk")   # 同名封面兜底
LOSSY.with_suffix(".lrc").write_text("[00:00.50]同名歌词\n", encoding="utf-8")
BROKEN = SHARD / "broken.flac"                     # 坏文件：不许炸
BROKEN.write_bytes(b"not-real-media")
(SHARD / ".hidden.mp3").write_bytes(b"x")           # 隐藏文件：不许收
NOTAUDIO = SHARD / "notes.txt"
NOTAUDIO.write_text("x", encoding="utf-8")
UNT = SUB / "无标签.mp3"                             # 歌手目录下、没标签：专辑该回落成目录名
UNT.write_bytes(LOSSY.read_bytes())

CACHE_BEFORE = dict(M._LOCAL_META_CACHE)


def count_parses():
    """数 mutagen 真正被调用了几次 —— 缓存生效的唯一硬判据。"""
    import mutagen
    real = mutagen.File
    box = {"n": 0}

    def spy(*a, **kw):
        box["n"] += 1
        return real(*a, **kw)
    return real, box, spy


try:
    # ── A. 单文件读取：标签优先、字段齐全 ────────────────────────
    print("=== A. audio_file_meta 读的是文件自带的东西 ===")
    m = M.audio_file_meta(str(TAGGED), use_cache=False)
    ck("A1 标题/歌手/专辑来自标签，不是文件名",
       (m["title"], m["artists"], m["album"]) == ("晴天", "周杰伦", "八度空间"), str(m)[:200])
    ck("A2 时长是真读出来的 3 秒", m["duration_s"] == 3 and m["duration"] == "0:03",
       f"{m['duration_s']}/{m['duration']}")
    ck("A3 有损按码率标品质", m["quality"] == "192k" and m["bitrate_kbps"] == 192, m["quality"])
    ck("A4 内嵌封面与内嵌歌词都被认出来", m["has_cover"] and m["has_lyrics"],
       f"cover={m['has_cover']} lyrics={m['has_lyrics']}")
    ck("A5 读到的读者记进 reader（便于事后定位是谁给的）", "mutagen" in m["reader"], m["reader"])
    fm = M.audio_file_meta(str(FLAC), use_cache=False)
    ck("A6 无损：48kHz 采样率读出来了", fm["sample_rate"] == 48000, f"{fm['sample_rate']}")
    ck("A7 无损：位深不再是空的（#127 的判据）", fm["bit_depth"] in (16, 24), f"{fm['bit_depth']}")
    ck("A8 无损：lossless 标记 + 品质写成 flac 24bit",
       fm["lossless"] and fm["quality"].startswith("flac"), f"{fm['lossless']}/{fm['quality']}")
    lm = M.audio_file_meta(str(LOSSY), use_cache=False)
    ck("A9 无标签文件不报错，标签字段就是空", lm["title"] == "" and lm["has_cover"] is False)
    bm = M.audio_file_meta(str(BROKEN), use_cache=False)
    ck("A10 坏文件降级：字段空、不抛异常", bm["duration_s"] == 0 and bm["title"] == "", str(bm)[:160])
    ck("A11 不存在的文件也不抛", isinstance(M.audio_file_meta(str(SHARD / "nope.mp3")), dict))
    ck("A12 内嵌歌词文本能取出来", "第一行歌词" in M.audio_embedded_lyrics(str(TAGGED)),
       repr(M.audio_embedded_lyrics(str(TAGGED))[:40]))
    ck("A13 没内嵌歌词的文件取出空串", M.audio_embedded_lyrics(str(LOSSY)) == "")
    cdata, cmime = M.audio_embedded_cover(str(TAGGED))
    ck("A14 内嵌封面取出字节 + image mime", cdata[:2] == b"\xff\xd8" or len(cdata) > 0,
       f"{len(cdata)} {cmime}")
    ck("A15 无内嵌封面的回 ('', '')", M.audio_embedded_cover(str(LOSSY)) == ("", ""))

    # ── B. 目录扫描：兜底、附属文件、字段透出 ───────────────────
    print("=== B. scan_local_music 的行内容 ===")
    M._LOCAL_META_CACHE.clear()
    rows = {pathlib.Path(r["path"]).name: r for r in M.scan_local_music(str(SHARD))}
    ck("B1 只收音频，隐藏文件与 .txt 不进",
       set(rows) == {"文件名是猜的 - 文件名歌手.mp3", "plain.mp3", "lossless.flac", "broken.flac", "无标签.mp3"},
       str(sorted(rows)))
    t = rows.get("文件名是猜的 - 文件名歌手.mp3", {})
    ck("B2 行上的标题走标签，专辑取标签",
       t.get("title") == "晴天" and t.get("album") == "八度空间", f"{t.get('title')}/{t.get('album')}")
    ck("B3 时长/品质不再是空的", t.get("duration") == "0:03" and t.get("quality") == "192k",
       f"{t.get('duration')}/{t.get('quality')}")
    ck("B4 内嵌封面 → 封面地址指向 local_cover 接口",
       str(t.get("cover_url", "")).startswith("/api/music/local_cover?path="), t.get("cover_url"))
    p = rows.get("plain.mp3", {})
    ck("B5 没标签才回落到文件名猜测",
       p.get("title") == "plain" and p.get("artists") == "", f"{p.get('title')}/{p.get('artists')}")
    ck("B6 同名图片当封面：走文件流接口", str(p.get("cover_url", "")).startswith("/api/files/stream?path="),
       p.get("cover_url"))
    ck("B7 同名歌词文件路径给出", str(p.get("lyrics_path", "")).endswith("plain.lrc"), p.get("lyrics_path"))
    f = rows.get("lossless.flac", {})
    ck("B8 无损行带位深/采样率/无损标记",
       f.get("bit_depth") in (16, 24) and f.get("sample_rate") == 48000 and f.get("lossless") is True,
       f"{f.get('bit_depth')}/{f.get('sample_rate')}/{f.get('lossless')}")
    u = rows.get("无标签.mp3", {})
    ck("B9 标签没有专辑时回落到歌手目录名",
       u.get("album") == "周杰伦" and u.get("title") == "无标签", f"{u.get('album')}/{u.get('title')}")
    ck("B9b 既无内嵌也无同名图片 → 没有封面地址", u.get("cover_url") == "", u.get("cover_url"))
    ck("B10 每行都带缓存键要用的 path/size/mtime",
       all(r.get("size") and r.get("mtime") and r.get("path") for r in rows.values()))

    # ── C. 缓存：同一份文件不重复解析 ──────────────────────────
    print("=== C. 按「路径+大小+修改时间」缓存 ===")
    real, box, spy = count_parses()
    import mutagen
    mutagen.File = spy
    try:
        M._LOCAL_META_CACHE.clear()
        M.scan_local_music(str(SHARD))
        first = box["n"]
        box["n"] = 0
        M.scan_local_music(str(SHARD))
        ck("C1 第二次扫描完全不碰解析器（全命中缓存）", first >= 4 and box["n"] == 0,
           f"首次 {first} 次，二次 {box['n']} 次")
        saved = M.save_local_index(str(SHARD), M.scan_local_music(str(SHARD)))
        ck("C2 索引落在程序目录（这里拐到 Temp），不再写进被扫描目录",
           saved.is_file() and INDEX_DIR in saved.parents
           and not list(SHARD.glob("local_music_index*.json")), str(saved))
        box["n"] = 0
        M._LOCAL_META_CACHE.clear()                       # 模拟重启：内存缓存没了
        rows2 = M.scan_local_music(str(SHARD))
        ck("C3 重启后靠索引回填，仍不重复解析", box["n"] == 0, f"实际解析 {box['n']} 次")
        ck("C4 回填出来的字段跟原来一致",
           {r["path"]: (r["duration"], r["quality"], r.get("bit_depth")) for r in rows2}
           == {r["path"]: (r["duration"], r["quality"], r.get("bit_depth")) for r in rows.values()})
        box["n"] = 0
        FLAC.write_bytes(FLAC.read_bytes() + b"\n")        # 改一个文件（字节数一定变，键必然不同）
        M.scan_local_music(str(SHARD))
        ck("C5 只重解析动过的那一个", box["n"] == 1, f"实际解析 {box['n']} 次")
        box["n"] = 0
        os.utime(FLAC, (time.time() + 30, time.time() + 30))   # 只改修改时间
        M.scan_local_music(str(SHARD))
        ck("C6 光改 mtime 也算变动（缓存不会吃掉改动）", box["n"] == 1, f"实际解析 {box['n']} 次")
    finally:
        mutagen.File = real

    print("=== C7 反向验证：把索引回填这条路掐掉，缓存优势必须消失 ===")
    real_load = M.load_local_index
    M._LOCAL_META_CACHE.clear()
    M.load_local_index = lambda root: []
    import mutagen
    real, box, spy = count_parses()
    mutagen.File = spy
    try:
        M.scan_local_music(str(SHARD))
        ck("C7 没有索引回填时确实整目录重解析（C3 的 0 次不是巧合）", box["n"] >= 4, f"{box['n']} 次")
    finally:
        mutagen.File = real
        M.load_local_index = real_load

    # ── D. ffprobe 不可用时降级 ────────────────────────────────
    print("=== D. ffprobe 缺席 ===")
    real_probe = M.find_ffprobe
    M.find_ffprobe = lambda: ""
    try:
        M._LOCAL_META_CACHE.clear()
        d = M.audio_file_meta(str(FLAC), use_cache=False)
        ck("D1 没有 ffprobe 也不报错，mutagen 那部分照给",
           d["sample_rate"] == 48000 and d["duration_s"] == 2, str(d)[:160])
        ck("D2 无损标记仍成立（不靠 ffprobe）", d["lossless"] is True)
        b = M.audio_file_meta(str(BROKEN), use_cache=False)
        ck("D3 坏文件 + 无 ffprobe：仍是空字段而非异常", b["duration_s"] == 0)
    finally:
        M.find_ffprobe = real_probe

    # ── E. 关键词搜索吃到真标签 ────────────────────────────────
    print("=== E. 本地搜索口径 ===")
    M._LOCAL_META_CACHE.clear()
    hits = M.search_local_music("晴天", str(SHARD))
    ck("E1 按标签里的歌名能搜到（文件名里根本没有这两个字）",
       len(hits) == 1 and hits[0]["title"] == "晴天", f"{len(hits)} 条")
    ck("E2 搜不到时返回空，不瞎凑", M.search_local_music("根本没有这首歌", str(SHARD)) == [])

    # ── F. 资源库共用同一份读取（#127 判据） ───────────────────
    print("=== F. server.scan_library 的音频行 ===")
    try:
        import server as S
    except Exception as e:                                      # 起不来就跳过，不算失败
        print(f"SKIP F（server 导入失败：{e}）")
    else:
        real_cache = S.LIBRARY_CACHE
        S.LIBRARY_CACHE = SHARD / "_lib_cache.json"
        try:
            lib = {pathlib.Path(i["path"]).name: i for i in S.scan_library(root=str(SHARD))}
            lf = lib.get("lossless.flac", {})
            ck("F1 资源库的无损行看得见位深与采样率",
               lf.get("bit_depth") in (16, 24) and lf.get("sample_rate") == 48000,
               f"{lf.get('bit_depth')}/{lf.get('sample_rate')}")
            ck("F2 资源库的无损行标了 lossless", lf.get("lossless") is True, str(lf.get("lossless")))
            ck("F3 时长来自标签（原来只有 ffprobe 一条路）", int(lf.get("duration") or 0) == 2,
               str(lf.get("duration")))
            ck("F4 资源库不吞坏文件也不崩", "broken.flac" in lib)
            ck("F5 视频行不受影响（没有音质字段）",
               all("bit_depth" not in lib[n] for n in lib if lib[n]["kind"] == "video"))
        finally:
            S.LIBRARY_CACHE = real_cache
finally:
    M._LOCAL_META_CACHE.clear()
    M._LOCAL_META_CACHE.update(CACHE_BEFORE)
    shutil.rmtree(SHARD, ignore_errors=True)

print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
