r"""成品回读：下完之后核对「实得高度 vs 用户点的档位」，离线自检。

为什么要加这一环：10-13 之前，任务的「成功」= 进程退出码 0 + ffprobe 说文件能播。
那次 YouTube 4K 静默降成 1080p 就是从这道缝里漏过去的 —— 卡片写着成功、文件确实能播，
唯一下到的其实是清单末尾那条 1080p 渐进流，而界面上没有任何地方说这件事。
回读要说清「是谁的问题」，所以四种话术分开钉：本地选择/合并的偏差、上游就给到这儿、
清单过期判不出、以及上限没拦住。

D 段是真的端到端：用随包 ffmpeg 造一个 1280x720 的小片子，让 tier_readback 自己 ffprobe 回读，
不桩、不猜。没有 ffmpeg 时那几条会红，因为「桩过了但真机读不出」正是要防的那种假绿。

跑法：PYTHONIOENCODING=utf-8 python tests/readback_test.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import server as S  # noqa: E402

SRC = Path(S.__file__).read_text(encoding="utf-8")
HTML = (APP / "static" / "index.html").read_text(encoding="utf-8")
FAILED = []
TOTAL = 0
TMP = Path(tempfile.mkdtemp(prefix="md_readback_"))


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{str(extra)[:300]}]")


print("== A. 档位口径只有一个来源 ==")
ck("A1 4K=2160 / 1080p=1080 这些数字来自同一张表",
   S.quality_height_cap("4K") == 2160 and S.quality_height_cap("1080p") == 1080
   and S.quality_height_cap("360p") == 360, S.VIDEO_QUALITY_HEIGHTS)
ck("A2 best / 空 / 认不出的写法都是「没有上限」=0",
   S.quality_height_cap("best") == 0 and S.quality_height_cap("") == 0
   and S.quality_height_cap(None) == 0 and S.quality_height_cap("8K") == 0)
ck("A3 大小写与空格不影响（界面传 '4k' 之类不至于当成无上限）",
   S.quality_height_cap(" 1080p ") == 1080)
ck("A4 _resolve_format 里不再手抄第二份高度表",
   "height_map" not in SRC,
   [l for l in SRC.splitlines() if "height_map" in l][:3])
ck("A5 解析页的体积估算跟着这张表派生（原来那句「抄自 _resolve_format」就是漂移源头）",
   dict(S._VIDEO_TIERS[1:]) == S.VIDEO_QUALITY_HEIGHTS, S._VIDEO_TIERS)
ck("A6 顺序仍是从高到低（界面档位下拉靠它排）",
   [h for _n, h in S._VIDEO_TIERS] == [0, 2160, 1440, 1080, 720, 480, 360],
   [h for _n, h in S._VIDEO_TIERS])
ck("A7 换了来源，格式串的行为没变：4K 仍是 height<=2160",
   "[height<=2160]" in S.engine._resolve_format([], "4K", "best", False),
   S.engine._resolve_format([], "4K", "best", False)[:160])
ck("A8 换来源后 best 仍然不设上限（和原来 None 的 falsy 口径一致）",
   "height<=" not in S.engine._resolve_format([], "best", "best", False).replace("bv*", ""),
   S.engine._resolve_format([], "best", "best", False)[:160])

print("== B. 四种话术各归各（桩 ffprobe，只验措辞判定） ==")
_real_probe = S._ffprobe_info


def probe_h(h):
    S._ffprobe_info = lambda p: {"height": h, "width": max(1, int(h * 16 / 9)), "duration": 12.0}


fake = TMP / "fake.mp4"
fake.write_bytes(b"\x00" * 4096)
try:
    probe_h(1080)
    ck("B1 清单里有 4K 却只下成 1080p → 点明是选择/合并的偏差",
       "清单里明明有 2160p" in S.tier_readback(fake, "4K", 2160)
       and "不是上游不给" in S.tier_readback(fake, "4K", 2160), S.tier_readback(fake, "4K", 2160))
    ck("B2 清单最高就到 1080p → 点明上游给不了这一档，不赖本地",
       "上游清单最高就到这儿" in S.tier_readback(fake, "4K", 1080), S.tier_readback(fake, "4K", 1080))
    ck("B3 清单读不到 → 只报实得并说明判不出",
       "解析清单已过期" in S.tier_readback(fake, "4K", 0), S.tier_readback(fake, "4K", 0))
    ck("B4 清单比实得高但仍低于所选 → 两句都说，不含糊",
       "没下满" in S.tier_readback(fake, "4K", 1440), S.tier_readback(fake, "4K", 1440))
    ck("B5 正好是所选那一档 → 一句话都不多说", S.tier_readback(fake, "1080p", 2160) == "",
       S.tier_readback(fake, "1080p", 2160))

    probe_h(2176)
    ck("B6 编码按 16 对齐多出的那几行不算偏差（否则天天误报）",
       S.tier_readback(fake, "4K", 2160) == "", S.tier_readback(fake, "4K", 2160))

    probe_h(2160)
    ck("B7 点了 1080p 却下成 4K → 说清是上限没拦住，体积会比预期大",
       "高度上限没拦住" in S.tier_readback(fake, "1080p", 2160), S.tier_readback(fake, "1080p", 2160))

    probe_h(1080)
    ck("B8 音频任务不比分辨率（没有高度概念）", S.tier_readback(fake, "4K", 2160, True) == "")
    ck("B9 选 best 时不判：没有目标上限", S.tier_readback(fake, "best", 2160) == "")

    probe_h(0)
    ck("B10 读不到高度就闭嘴（没 ffprobe / 成品其实是音频）", S.tier_readback(fake, "4K", 2160) == "")

    def boom(p):
        raise OSError("ffprobe 挂了")

    S._ffprobe_info = boom
    ck("B11 回读自身出问题不牵连任务：抛出来的是空串不是异常", S.tier_readback(fake, "4K", 2160) == "")
    ck("B12 路径为空也不炸", S.tier_readback("", "4K", 2160) == "" and S.tier_readback(None, "4K") == "")
finally:
    S._ffprobe_info = _real_probe

print("== C. 清单上限怎么交到收尾 ==")
ck("C1 引擎记的是「本次任务」的清单上限，不是全局变量",
   "self._listed_max[task_id] = max(" in SRC, [l for l in SRC.splitlines() if "_listed_max" in l][:4])
ck("C2 补试 all 那轮的清单不会被前一轮覆盖掉（取的是最大值）",
   "int(self._listed_max.get(task_id) or 0), max_listed" in SRC)
eng = S.engine
eng._listed_max["t-peek"] = 2160
ck("C3 pop 一次给值，再来就是 0（不留残值给下一个任务）",
   eng.pop_listed_max("t-peek") == 2160 and "t-peek" not in eng._listed_max
   and eng.pop_listed_max("t-peek") == 0)
ck("C4 没记过的任务（直播、磁力、解析失败）pop 出 0 而不是 KeyError", eng.pop_listed_max("没有这个 id") == 0)
ck("C5 收尾在写状态之前先取走清单上限", "listed_max = self.engine.pop_listed_max(task.id)" in SRC)
ck("C6 回读只在「文件能用」之后做，文件本来就坏时不重复报错",
   SRC.count("task.verify_note = tier_readback(") == 1 and "elif not task.is_live:" in SRC
   and SRC.index("bad = verify_media_file(path)") < SRC.index("task.verify_note = tier_readback("))
ck("C7 直播确实豁免：下载那侧对直播恒用 best，画质档位根本不参与",
   'format_sel = "best/bestvideo+bestaudio/best"' in SRC)
ck("C8 回读的档位取的是这条任务的画质，不是全局设置",
   'opts.get("video_quality", cfg.get("video_quality", "best"))' in SRC)
ck("C9 异常吞掉只记日志：回读是附加信息，不该把成功任务判失败",
   "成品回读异常（跳过）" in SRC)

print("== D. 真·端到端：随包 ffmpeg 造一条 720p，让回读自己 ffprobe ==")
ff = (S.ffmpeg_mgr.find() if hasattr(S, "ffmpeg_mgr") else "") or ""
probe = S._ffprobe_bin()
if probe and ff and Path(ff).exists():
    clip = TMP / "clip720.mp4"
    r = subprocess.run(
        [ff, "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=15:duration=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-shortest", "-c:v", "libx264", "-c:a", "aac", str(clip)],
        capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    ck("D0 造得出 720p 参照片", clip.is_file() and clip.stat().st_size > 1024, (r.stderr or "")[-240:])
    meta = _real_probe(clip)
    ck("D1 真 ffprobe 读出 720（回读用的就是这条链，桩不算）", int(meta.get("height") or 0) == 720, meta)
    note = S.tier_readback(clip, "4K", 2160)
    ck("D2 实得 720p + 清单有 4K → 说的是本地偏差", "成品只有 720p" in note and "清单里明明有 2160p" in note, note)
    ck("D3 同一文件按 720p 档来判就闭嘴", S.tier_readback(clip, "720p", 2160) == "",
       S.tier_readback(clip, "720p", 2160))
    ck("D4 清单只到 480p 时改成怪上游", "上游清单最高就到这儿" in S.tier_readback(clip, "4K", 480),
       S.tier_readback(clip, "4K", 480))
else:
    ck("D0 本机没有 ffprobe（这一段的判定只能靠 B 段桩测）", False, S._ffprobe_bin())

print("== E. 入库与上屏接线 ==")
t = S.DownloadTask(id="t-verify", url="https://example.com/v")
ck("E1 任务字段默认空串（没偏差时界面上不出现这一行）", t.verify_note == "")
d = t.to_dict()
ck("E2 to_dict 带着它出接口（asdict 自动，前端拿得到）", "verify_note" in d, sorted(k for k in d if "note" in k))
ck("E3 历史入库写这一句", '"verify_note": task.verify_note' in SRC)
ck("E4 运行日志也留一句，事后能从日志追", '成品回读：{task.verify_note}' in SRC)
ck("E5 卡片两张模板都上屏（队列卡与种子卡同一口径）",
   HTML.count("t.verify_note") >= 2, HTML.count("t.verify_note"))
ck("E6 历史那行挂在状态标的悬浮提示里（不给表格加一列）", "row.verify_note" in HTML)
ck("E7 SSE 不用改：完成态走整份任务字典，不经进度增量",
   "verify_note" not in SRC.split("def _sse_prog")[1].split("def _sse_elapsed")[0])

print(f"\nTOTAL {TOTAL} FAILED: {', '.join(FAILED) if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
