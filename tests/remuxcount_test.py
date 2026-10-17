r"""转封装之后，工具报回来的名字找不到成品：计数与「文件不可用」都是从这个名字来的。

起因（实测）：目标容器=mkv 时，整批下合集那一趟先打「列表 1 条，本次在下载目录写出 0 个文件」，
再打「下载完成但文件不可用：工具报告成功，但目标文件不存在（文件已保留，未转存网盘）」，
而 .mkv 确实在盘上、能播。根因是 download() 只认 yt-dlp 写回分集 info 的 filepath：
挂了 FFmpegVideoRemuxer / FFmpegExtractAudio 之后，那个名字仍是换容器前的（.webm / .mp4），
成品躺在旁边换了后缀。单视频那一支早就有一段「按同名换扩展找回来」的代码，分集那支没有，
所以只有整批这一路会被说成「一个文件都没写出来」。用户自己那台 history 里 12 条 B 站分集的
「下载完成但文件不可用」就是这个形状。

跑法：`python tests/remuxcount_test.py`（不起 server，不联网，产物落在 %TEMP%\md_remuxcount_test\<时刻>\）。
A 组测 resolve_written_file 自己的行为，B 组测它接在 download() 的哪一步；
端到端那一路在自起沙箱实例里用真容器跑（见提交说明），这里不假装能替它。
"""
from __future__ import annotations

import inspect
import os
import pathlib
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_remuxcount_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


def touch(p: pathlib.Path, mark: str = "x") -> pathlib.Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(mark.encode("utf-8") * 8)
    return p


# ---------------------------------------------------------------- A. helper 自己的行为
print("== A. 报回来的名字不在场时按同名换扩展找回：只在真不在时才找，找不回就原样还 ==")

d1 = SHARD / "a1"
mkv = touch(d1 / "Blender Conference 2026 Recap [sO_lhW8av3U].mkv")
got1 = S.resolve_written_file(str(d1 / "Blender Conference 2026 Recap [sO_lhW8av3U].webm"), ("mkv",))
ck("A1 分集 filepath 是换容器前的 .webm，成品是 .mkv：找回 mkv（这就是那 12 条的形状）",
   got1 == str(mkv), pathlib.Path(got1).name)

got2 = S.resolve_written_file(str(mkv), ("webm",))
ck("A2 给的名字本来就在场：原样还，不去动旁边任何文件", got2 == str(mkv), pathlib.Path(got2).name)

got3 = S.resolve_written_file("", ("mkv",))
ck("A3 空串进去空串出来（别把「不知道名字」变成「找回了个路径」）", got3 == "", repr(got3))

d4 = SHARD / "a4"
m4a = touch(d4 / "稻香 - 周杰伦.m4a")
got4 = S.resolve_written_file(str(d4 / "稻香 - 周杰伦.mp4"), ("m4a",))
ck("A4 抽音频那一支同理：报 .mp4、成品 .m4a", got4 == str(m4a), pathlib.Path(got4).name)

d5 = SHARD / "a5"
old_mp4 = touch(d5 / "Both [x].mp4")     # 上一次目标容器选 mp4 留下的
new_mkv = touch(d5 / "Both [x].mkv")     # 这一次选 mkv 写出来的
ck("A5 旁边既躺着旧 .mp4 又躺着新 .mkv：按这一趟要的目标容器先找，不认领旧文件",
   S.resolve_written_file(str(d5 / "Both [x].webm"), ("mkv",)) == str(new_mkv)
   and S.resolve_written_file(str(d5 / "Both [x].webm"), ("mp4",)) == str(old_mp4))

ghost = str(d5 / "谁都不在 [z].webm")
ck("A6 换哪个扩展都不在场：原样还，让调用方照实说「文件不存在」（这里不替工具撒谎）",
   S.resolve_written_file(ghost, ("mkv",)) == ghost, pathlib.Path(ghost).name)

d7 = SHARD / "a7"
dotted = touch(d7 / "视频 1.5 分钟 [id].mkv")
ck("A7 标题里带点不被切错基名（with_suffix 只切最后一段）",
   S.resolve_written_file(str(d7 / "视频 1.5 分钟 [id].webm"), ("mkv",)) == str(dotted),
   pathlib.Path(d7 / "视频 1.5 分钟 [id].webm").with_suffix("").name)

d8 = SHARD / "a8"
mkv8 = touch(d8 / "n8.mkv")
ck("A8 prefer 写不带点的「mkv」也一样认；不传 prefer 退回默认名单",
   S.resolve_written_file(str(d8 / "n8.webm"), ("mkv",)) == str(mkv8)
   and S.resolve_written_file(str(d8 / "n8.webm")) == str(mkv8))

d9 = SHARD / "a9" / "没有这一层目录"
ck("A9 父目录都不在也不炸（返回原路，判「不在场」是调用方的事）",
   S.resolve_written_file(str(d9 / "n.mkv"), ("mkv",)) == str(d9 / "n.mkv"))

d10 = SHARD / "a10"
touch(d10 / "n10.ts")
ck("A10 名单外的小写容器不当成品（只认列出来那几种，别把 .ts/.part 当完成）",
   S.resolve_written_file(str(d10 / "n10.webm"), ("mkv",)) == str(d10 / "n10.webm"),
   str(S.REMUX_FALLBACK_EXTS))

# ---------------------------------------------------------------- B. 接线
print("== B. 接在 download() 的哪一步：分集与单条共用同一份逻辑，且排在返回之前 ==")
SVC = pathlib.Path(pathlib.Path(__file__).resolve().parent.parent / "server.py").read_text(encoding="utf-8")
dl = inspect.getsource(S.DownloaderEngine.download)

ck("B1 分集那支每条都先过 resolve_written_file 再判在场（以前这里裸判 filepath，换容器就全判丢）",
   "pth = resolve_written_file(pth, want_ext)" in dl
   and dl.index("pth = resolve_written_file(pth, want_ext)") < dl.index("pl_files.append(pth)"))
ck("B2 单条那一支也换成同一个 helper（两处共用一份名单，不再各抄各的）",
   "filepath = resolve_written_file(filepath, want_ext)" in dl
   and 'for ext in (".mp4", ".mkv", ".webm"' not in dl)
ck("B3 目标容器取的是这一趟算出来的 merge_output_format / fmt，不是设置里那份（选了 mkv 就该先找 mkv）",
   'want_ext = (str(opts.get("merge_output_format") or fmt or ""),)' in dl)
ck("B4 找回之后仍按「真在场」入账（不是「拼出来一个名字就算写好了」）",
   "if pth and Path(pth).exists():" in dl and 'if not Path(filepath).exists() and _already_recorded():' in dl)
ck("B5 helper 的判定排在 return 之前（排在后面等于调用方照旧拿到换容器前的名字）",
   dl.index("filepath = resolve_written_file(filepath, want_ext)") < dl.index('return ok, (filepath if ok else "")'))
ck("B6 这份成品容器名单与「同名换扩展」那段只有一份（别处那几组 .mp4/.mkv 是「是不是媒体」的判据，另一种概念）",
   SVC.count('REMUX_FALLBACK_EXTS = (".mp4", ".mkv", ".webm", ".mp3", ".m4a", ".flac", ".wav")') == 1
   and SVC.count("cand = Path(base + ext)") == 1
   and SVC.count("resolve_written_file(") == 3,      # 定义 + download() 里两处调用
   "名单 %d 份 / 换扩展 %d 处 / 调用 %d 处" % (
       SVC.count("REMUX_FALLBACK_EXTS = ("), SVC.count("cand = Path(base + ext)"),
       SVC.count("resolve_written_file(")))
ck("B7 名字对不上的来源确实存在：目标容器 mp4/mkv/webm 那一支会挂无损 remuxer",
   '"key": "FFmpegVideoRemuxer"' in dl and 'elif fmt in ("mp4", "mkv", "webm"):' in dl)
ck("B8 命中下载记录那两条说法没被这次改动碰掉（那是另一种「没有文件」，不能混成一回事）",
   "本次没有重新下载" in dl and "已在下载记录里" in dl)

shutil.rmtree(SHARD, ignore_errors=True)
print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
