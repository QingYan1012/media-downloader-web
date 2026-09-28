"""资源库扫描口径：音频扩展名必须跟下载链真正产出的那一份保持一致。

起因：批量下载有一首落成 .flac（无损源），文件按模板归位在磁盘上，资源库里却始终看不见 ——
scan_library 自己写死了一份窄口径（.mp3/.m4a/.aac/.wav/.ogg），比 music_search 的
MUSIC_AUDIO_EXTS 少 .flac/.opus，kind 判定又是另一份写死的字面量，两份都会漏。

只验代码路径 —— root 传临时目录，LIBRARY_CACHE 顶到 Temp，绝不写真实 library_cache.json。
"""
import os
import pathlib
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import music_search  # noqa: E402
import server as S  # noqa: E402

FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_library_scan_test"
SHARD = ROOT / time.strftime("%H%M%S")
DL = SHARD / "告五人"          # 模板归档的真实形状：歌手动子目录
DL.mkdir(parents=True)

AUDIO = (".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".opus")   # = MUSIC_AUDIO_EXTS 去掉 .webm
VIDEO = (".mkv", ".mp4", ".webm", ".flv", ".ts", ".mov", ".avi")
NOISE = (".lrc", ".jpg", ".txt", ".json")

for ext in AUDIO + VIDEO:
    (SHARD / f"probe{ext}").write_bytes(b"not-real-media")
flac_in_folder = DL / "爱人错过 - 告五人.flac"
flac_in_folder.write_bytes(b"not-real-media")
for ext in NOISE:
    (SHARD / f"probe{ext}").write_bytes(b"x")
(SHARD / ".hidden.mp3").write_bytes(b"x")

REAL_CACHE = S.LIBRARY_CACHE
CACHE_MTIME_BEFORE = REAL_CACHE.stat().st_mtime_ns if REAL_CACHE.exists() else None
TMP_CACHE = SHARD / "_cache.json"
S.LIBRARY_CACHE = TMP_CACHE

try:
    items = S.scan_library(root=str(SHARD))
    by_name = {pathlib.Path(i["path"]).name: i for i in items}

    print("=== A. 下载链能产出的音频，全部要进资源库且标成 audio ===")
    miss = [e for e in AUDIO if f"probe{e}" not in by_name]
    ck("A1 七种音频扩展名都被扫到", not miss, f"缺 {miss}")
    badkind = [n for n, i in by_name.items()
               if i["ext"] in {e.lstrip('.') for e in AUDIO} and i["kind"] != "audio"]
    ck("A2 音频条目的 kind 都是 audio", not badkind, f"错标 {badkind[:5]}")
    ck("A3 子目录里的 .flac 也扫到（模板归档的歌手的无损成品）",
       flac_in_folder.name in by_name and by_name[flac_in_folder.name]["kind"] == "audio",
       f"kind={by_name.get(flac_in_folder.name, {}).get('kind')}")
    ck("A4 rel 是相对下载目录的路径（前端按它显示层级）",
       by_name.get(flac_in_folder.name, {}).get("rel") == "告五人\\爱人错过 - 告五人.flac",
       f"rel={by_name.get(flac_in_folder.name, {}).get('rel')}")

    print("=== B. 视频口径不能被音频改动带偏 ===")
    vbad = [n for n, i in by_name.items()
            if i["ext"] in {e.lstrip('.') for e in VIDEO} and i["kind"] != "video"]
    ck("B1 七种视频扩展名都在且标 video", all(f"probe{e}" in by_name for e in VIDEO) and not vbad,
       f"缺 {[e for e in VIDEO if f'probe{e}' not in by_name]} 错标 {vbad[:5]}")
    ck("B2 .webm 仍然算视频（音频常量里有它，这里必须排除）",
       by_name.get("probe.webm", {}).get("kind") == "video")

    print("=== C. 附属文件不许混进来 ===")
    ck("C1 歌词/封面/文本不进资源库", not any(f"probe{e}" in by_name for e in NOISE))
    ck("C2 点开头的隐藏文件不进", ".hidden.mp3" not in by_name)

    print("=== D. 反向验证：把口径退回窄常量，无损成品当场看不见 ===")
    real_exts = music_search.MUSIC_AUDIO_EXTS
    music_search.MUSIC_AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg")  # 修复前那份写死的字面量
    try:
        narrow = S.scan_library(root=str(SHARD))
        nset = {pathlib.Path(i["path"]).name for i in narrow}
        lost = {pathlib.Path(i["path"]).name for i in items} - nset
        ck("D1 窄口径下 .flac/.opus 从资源库消失（线上丢无损成品就是这个原因）",
           lost == {"probe.flac", "probe.opus", "爱人错过 - 告五人.flac"}, f"少的是 {sorted(lost)}")
        ck("D2 窄口径仍然收得到 .mp3（不是整段音频被关掉）", "probe.mp3" in nset)
    finally:
        music_search.MUSIC_AUDIO_EXTS = real_exts
    back = S.scan_library(root=str(SHARD))
    ck("D3 恢复常量后无损成品又回来了（结论来自那份常量，不是巧合）",
       {pathlib.Path(i["path"]).name for i in back} == {pathlib.Path(i["path"]).name for i in items}
       and "probe.flac" in {pathlib.Path(i["path"]).name for i in back})
    ck("D4 修复没有另起一份字面量：音频集合就是 MUSIC_AUDIO_EXTS 去掉 webm",
       {e for e in AUDIO} == {e for e in music_search.MUSIC_AUDIO_EXTS if e != ".webm"})

    print("=== E. 收尾卫生 ===")
    ck("E1 缓存写到了 Temp 顶替路径", TMP_CACHE.is_file())
    ck("E2 真实 library_cache.json 没被这次扫描改过",
       (REAL_CACHE.stat().st_mtime_ns if REAL_CACHE.exists() else None) == CACHE_MTIME_BEFORE,
       f"before={CACHE_MTIME_BEFORE} after={REAL_CACHE.stat().st_mtime_ns if REAL_CACHE.exists() else None}")
finally:
    S.LIBRARY_CACHE = REAL_CACHE
    shutil.rmtree(SHARD, ignore_errors=True)

print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
