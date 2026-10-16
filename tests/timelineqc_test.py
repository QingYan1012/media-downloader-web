#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""字幕时间轴三维质检（覆盖率 / 最大间隙 / 字符速率 + 语气词与复读名单）离线自检。

只写 %TEMP%，不碰真实下载目录与 config.json。
跑法：PYTHONIOENCODING=utf-8 python tests/timelineqc_test.py
"""
import os
import sys
import shutil
import tempfile
from pathlib import Path

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

    def save(self):
        raise AssertionError("时间轴质检不该写 config.json")


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))

    def texts(self):
        return [m for _l, m in self.rows]


TMP = Path(tempfile.mkdtemp(prefix="md_timelineqc_"))
DL = TMP / "downloads"
DL.mkdir(parents=True)

BASE_CFG = {
    "download_dir": str(DL),
    "subtitle_target_lang": "zh",
    "subtitle_wrap": True,
    "subtitle_wrap_width": 16,
    "subtitle_wrap_lines": 3,
    "subtitle_qc": True,
    "subtitle_qc_reflect": False,
    "subtitle_export_set": "single",
    "subtitle_glossary": "",
    "translate_auto_fallback": False,
    "subtitle_translate_provider": "openai",
    "openai_api_key": "sk-fake",
}

_REAL = (S.cfg, S.log_mgr, S._ffprobe_bin, S._ffprobe_info)
LOGS = FakeLog()
S.cfg = FakeCfg(dict(BASE_CFG))
S.log_mgr = LOGS

FFDUR = {}  # 媒体文件 → 时长（秒）；空表示读不出来


def install_ffprobe(durations):
    """把 ffprobe 换成读 durations 表：路径按 resolve 后的字符串比对。"""
    FFDUR.clear()
    for k, v in durations.items():
        FFDUR[str(Path(k).resolve())] = v
    S._ffprobe_bin = lambda: "ffprobe-fake"
    S._ffprobe_info = lambda p: {"duration": FFDUR.get(str(Path(p).resolve()), 0)}


def cues(*rows):
    return [{"start": float(a), "end": float(b), "text": t} for a, b, t in rows]


def run(srt_rows, media_seconds=0.0, lang="zh", why=""):
    return S.qc_timeline(srt_rows, media_seconds=media_seconds, target_lang=lang, why_no_media=why)


try:
    # ---------------- A 覆盖率
    tl = run(cues((0, 20, "甲"), (20, 40, "乙")), media_seconds=100)
    ck("A1 覆盖率 = 字幕并集 / 媒体时长", tl["coverage"]["available"] and tl["coverage"]["ratio"] == 0.4, str(tl["coverage"]))
    ck("A2 覆盖率低于 0.35 才标 low（0.4 只算偏低不报警）", tl["coverage"]["level"] == "ok", tl["coverage"]["level"])
    low = run(cues((0, 10, "甲"), (10, 30, "乙")), media_seconds=100)
    ck("A3 覆盖率 0.3 判为 low", low["coverage"]["ratio"] == 0.3 and low["coverage"]["level"] == "low", str(low["coverage"]))
    ov = run(cues((0, 50, "甲"), (10, 60, "乙")), media_seconds=100)
    ck("A4 两条互相压住时按并集算（50+50 不能算成 110%）", ov["coverage"]["spoken"] == 60.0, str(ov["coverage"]["spoken"]))
    cap = run(cues((0, 80, "甲"), (5, 200, "乙")), media_seconds=100)
    ck("A5 字幕比媒体还长时比例封顶 100%，不报出 1.x", cap["coverage"]["ratio"] == 1.0, str(cap["coverage"]["ratio"]))
    zero = run(cues((5, 5, "止点等于起点的一条"), (6, 9, "正常句")), media_seconds=30)
    ck("A6 零长度的一条不进覆盖率分子", abs(zero["coverage"]["spoken"] - 3.0) < 1e-6, str(zero["coverage"]["spoken"]))
    ck("A7 覆盖率说明里写清「低本身不是错」", "器乐" in zero["coverage"]["note"], zero["coverage"]["note"][:60])

    # ---------------- B 最大间隙与片尾容忍带
    tl = run(cues((1, 4, "甲"), (40, 44, "乙")), media_seconds=100)
    ck("B1 空了 36 秒：最大间隙与「第几句之前」都对", tl["gaps"]["max"] == 36.0 and tl["gaps"]["before"] == 2, str(tl["gaps"]))
    ck("B2 超过 30 秒的空档计入 count_over 并列出", tl["gaps"]["count_over"] == 1 and tl["gaps"]["over"][0]["seconds"] == 36.0, str(tl["gaps"]["over"]))
    ck("B3 空档条目带 start，界面点它才跳得过去", tl["gaps"]["over"][0]["start"] == 40.0 and "at" in tl["gaps"]["over"][0], str(tl["gaps"]["over"][0]))
    shuffled = run(cues((40, 44, "乙"), (1, 4, "甲")), media_seconds=100)
    ck("B4 字幕本身乱序也不影响（按起点排完再算，句序仍按传入的行序报）",
       shuffled["gaps"]["max"] == 36.0 and shuffled["gaps"]["before"] == 1, str(shuffled["gaps"]))
    small = run(cues((1, 4, "甲"), (9, 12, "乙"), (14, 20, "丙")), media_seconds=100)
    ck("B5 5 秒的小空档不记为「超 30 秒」但仍是最大间隙", small["gaps"]["max"] == 5.0 and small["gaps"]["count_over"] == 0, str(small["gaps"]))
    band100 = S._qc_tail_band(100)
    ck("B6 片尾容忍带按 8% 给：100 秒的片子给 10 秒（下限）", band100 == 10.0, str(band100))
    ck("B7 片尾容忍带上限 90 秒：4000 秒的片子不再给到 320", S._qc_tail_band(4000) == 90.0 and S._qc_tail_band(300) == 24.0,
       f"{S._qc_tail_band(4000)}/{S._qc_tail_band(300)}")
    tail = run(cues((1, 89, "甲"), (90, 92, "乙"), (124, 126, "丙")), media_seconds=100)
    ck("B8 落在片尾容忍带里的空档不计入最大间隙", tail["gaps"]["max"] == 1.0 and tail["gaps"]["count_over"] == 1,
       f"{tail['gaps']['max']}/{tail['gaps']['count_over']}")
    ck("B8b 带内那条仍然列得出来，只带一个「在片尾容忍带里」的标记",
       tail["gaps"]["over"][0]["in_tail_band"] is True and tail["gaps"]["over"][0]["seconds"] == 32.0, str(tail["gaps"]["over"]))
    tail9 = run(cues((1, 4, "甲"), (90, 95, "乙")), media_seconds=100)
    ck("B9 末句之后 5 秒算片尾空档且明确「不计入」", tail9["gaps"]["tail"]["available"] and tail9["gaps"]["tail"]["seconds"] == 5.0
       and tail9["gaps"]["tail"]["tolerated"], str(tail9["gaps"]["tail"]))
    lead = run(cues((60, 64, "第一句就来晚了"), (65, 69, "第二句")), media_seconds=100)
    ck("B10 第一条之前的片头空档也算一条并计入最大间隙",
       lead["gaps"]["leading"] == 60.0 and lead["gaps"]["max"] == 60.0 and lead["gaps"]["before"] == 1, str(lead["gaps"]))
    ck("B10b 片头那条带 leading 标记，界面才说得出「第一条之前」",
       lead["gaps"]["over"][0].get("leading") is True and lead["gaps"]["count_over"] == 1, str(lead["gaps"]["over"]))
    ck("B10c 从头就有字幕时片头空档是 0，不会凭空冒出一条",
       run(cues((0, 4, "甲"), (5, 9, "乙")), media_seconds=30)["gaps"]["leading"] == 0.0
       and len(run(cues((0, 4, "甲"), (5, 9, "乙")), media_seconds=30)["gaps"]["over"]) == 0, "")
    ck("B10d 说明里写明片头空档也算一条", "片头空档也算一条" in lead["gaps"]["note"], lead["gaps"]["note"][:60])
    ck("B10e 最大的那一段其实是片头时，日志与界面标题改口说「片头空了」",
       "片头空了 60 秒" in S.qc_timeline_text(lead) and "片头空了 60 秒" in lead["message"], S.qc_timeline_text(lead))
    mixed = run(cues((60, 64, "第一条"), (130, 134, "第二条")), media_seconds=200)
    ck("B10f 句间空档比片头更大时仍按「第 N 句之前」报",
       "最大间隙 66 秒（第 2 句之前）" in S.qc_timeline_text(mixed) and mixed["gaps"]["max"] == 66.0, S.qc_timeline_text(mixed))
    ovl = run(cues((0, 10, "甲"), (8, 16, "乙")), media_seconds=100)
    ck("B11 两条压在一起算重叠，不算空档", ovl["gaps"]["max"] == 0.0 and ovl["gaps"]["overlaps"] == 1 and ovl["gaps"]["overlap_secs"] == 2.0,
       str({k: ovl["gaps"][k] for k in ("overlaps", "overlap_secs", "max")}))
    ck("B12 说明里点明重叠不当问题（滚动式字幕本来就这样）", "滚动式" in ovl["gaps"]["note"], ovl["gaps"]["note"][:50])

    # ---------------- C 字符速率
    fast = run(cues((0, 1, "这句特别长所以要挤进一秒里读完而且真的很长")), media_seconds=60)
    ck("C1 21 个字挤在 1 秒里 → 超上限，cps 报得出来", fast["speed"]["over_count"] == 1 and fast["speed"]["over"][0]["cps"] == 21.0,
       str(fast["speed"]["over"]))
    ck("C2 目标语言是中文时上限 9 字每秒", fast["speed"]["limit"] == 9.0, str(fast["speed"]["limit"]))
    latin = run(cues((0, 1, "abcdefghij klmnopqrst")), media_seconds=60, lang="en")
    ck("C3 拉丁语字幕换算后上限 14，10 个字母每秒不该报", latin["speed"]["limit"] == 14.0 and latin["speed"]["over_count"] == 0,
       f"{latin['speed']['limit']}/{latin['speed']['over_count']}")
    tagged = S.qc_timeline([{"start": 0, "end": 1.0, "text": "<00:00:00.000 --><c.xxx>字字字字字字字字</c>"},
                            {"start": 2, "end": 4.0, "text": "&nbsp;正常一句&nbsp;"}], media_seconds=10)
    ck("C4 VTT 的内联时间戳与 <c> 标记先剥掉再算字数（不然一条 8 字的会被标记撑成超限）",
       tagged["speed"]["over_count"] == 0 and tagged["speed"]["over"] == [], str(tagged["speed"]))
    raw_only = S.qc_timeline([{"start": 0, "end": 1.0, "text": "<00:00:00.000 --><c.xxx>字字字字字字字字</c>"}], media_seconds=10)
    ck("C4b 剥标记后这句正好 8 个字每秒（贴着 9 的上限内）", raw_only["speed"]["median_cps"] == 8.0, str(raw_only["speed"]["median_cps"]))
    vv = S._qc_plain("<c.white>甲<b>乙</b></c>丙丁<00:00:01.000>")
    ck("C5 剥标记的函数对嵌套与时间戳都有效", vv == "甲乙丙丁", repr(vv))
    flash = run(cues((0, 2, "正常句"), (3, 3.01, "闪光条"), (4, 6, "又一句")), media_seconds=30)
    ck("C6 0.01 秒的闪光条不参与读速，只单列一笔", flash["speed"]["flash_count"] == 1 and flash["speed"]["over_count"] == 0
       and flash["speed"]["flash"][0]["i"] == 2, str(flash["speed"]["flash"]))
    ck("C7 中位读速不受闪光条影响（没被 3300 字每秒那种假数带跑）", flash["speed"]["median_cps"] <= 2.0, str(flash["speed"]["median_cps"]))
    shortc = run(cues((0, 0.3, "字")), media_seconds=30)
    ck("C8 显示不足 0.4 秒的句子进「太短」名单", shortc["speed"]["short_count"] == 1 and shortc["speed"]["over_count"] == 0,
       str(shortc["speed"]["short"]))
    both = run(cues((0, 0.3, "字字字字字字字字字字字字")), media_seconds=30)
    ck("C8b 又快又短的一句按「超限」报，不在两处各记一遍", both["speed"]["over_count"] == 1 and both["speed"]["short_count"] == 0,
       f"{both['speed']['over_count']}/{both['speed']['short_count']}")
    rev = run(cues((0, 2, "甲"), (20, 19, "止点比起点还早"), (30, 32, "乙")), media_seconds=60)
    ck("C9 时间轴倒挂单独成列并计数", rev["speed"]["reversed_count"] == 1 and rev["speed"]["reversed"][0]["i"] == 2, str(rev["speed"]["reversed"]))
    ck("C10 倒挂的那句不参与读速统计", rev["speed"]["over_count"] == 0 and rev["speed"]["short_count"] == 0, str(rev["speed"]))
    many = run(cues(*[(i, i + 0.5, "字字字字字字字字字字字字字字字字字") for i in range(0, 20, 1)]), media_seconds=60)
    ck("C11 超上限 20 句时名单只留 8 条、计数按全部", many["speed"]["over_count"] == 20 and len(many["speed"]["over"]) == 8,
       f"{many['speed']['over_count']}/{len(many['speed']['over'])}")
    ck("C12 名单被截断时计数还是全量，界面据此能说「其余 N 句」", many["speed"]["over_count"] > len(many["speed"]["over"]),
       str(many["speed"]["over_count"]))
    ck("C13 读速说明里写明剥标记与 0.1 秒闪光条这两件事", "剥掉" in many["speed"]["note"] and "0.1" in many["speed"]["note"], many["speed"]["note"][:60])

    # ---------------- D 语气词与复读（只列名单，一个字节都不动）
    fill = run(cues((0, 2, "正常的一句话"), (3, 4, "嗯"), (5, 6, "啊"), (7, 8, "这个嘛")), media_seconds=30)
    ck("D1 整句只有语气词的单列出来", fill["noise"]["filler_count"] == 2 and [f["i"] for f in fill["noise"]["fillers"]] == [2, 3],
       str(fill["noise"]["fillers"]))
    ck("D2 语气词不参与读速统计", fill["speed"]["over_count"] == 0 and fill["speed"]["short_count"] == 0, str(fill["speed"]))
    hal = run(cues((0, 2, "甲"), (3, 5, "同一句话"), (6, 8, "同一句话"), (9, 11, "同一句话"), (12, 14, "乙")), media_seconds=30)
    ck("D3 同一句连读三遍起报疑似幻觉，给出范围", hal["noise"]["halluc_count"] == 3 and hal["noise"]["halluc"][0]["from"] == 2
       and hal["noise"]["halluc"][0]["to"] == 4, str(hal["noise"]["halluc"]))
    twice = run(cues((0, 2, "同一句话"), (3, 5, "同一句话")), media_seconds=30)
    ck("D4 只读两遍不报（副歌本来就会重复）", twice["noise"]["halluc"] == [], str(twice["noise"]["halluc"]))
    taghal = S.qc_timeline([{"start": 0, "end": 2.0, "text": "<c.a>同一句</c>"},
                            {"start": 3, "end": 5.0, "text": "同一句"},
                            {"start": 6, "end": 8.0, "text": "<00:00:06.000>同 一 句</0>"}], media_seconds=20)
    ck("D5 复读判定先剥标记再归一，VTT 排布不会漏报", taghal["noise"]["halluc_count"] == 3, str(taghal["noise"]["halluc"]))
    ck("D6 drop 名单把语气词与复读句并起来，句序升序", fill["noise"]["drop"] == [2, 3] and hal["noise"]["drop"] == [2, 3, 4],
       f"{fill['noise']['drop']}/{hal['noise']['drop']}")
    ck("D7 名单说明写死「程序没有替你删」", "没有替你删" in hal["noise"]["note"], hal["noise"]["note"][:40])
    src = DL / "keepme.srt"
    original = "1\n00:00:01,000 --> 00:00:03,000\n同一句话\n\n2\n00:00:04,000 --> 00:00:06,000\n同一句话\n\n3\n00:00:07,000 --> 00:00:09,000\n同一句话\n"
    src.write_text(original, encoding="utf-8")
    before_stat = src.stat()
    got = S.qc_timeline_of_file(src)
    ck("D8 从文件算时间轴照样能读出复读", got["noise"]["halluc_count"] == 3, str(got["noise"]))
    ck("D9 算完之后文件内容一个字节都没变", src.read_text(encoding="utf-8") == original, "内容被改过")
    ck("D10 连 mtime 都没动（质检不碰文件）", src.stat().st_mtime == before_stat.st_mtime, str(src.stat().st_mtime))

    # ---------------- E 缺输入 ≠ 用户关闭质检
    nomedia = run(cues((1, 4, "甲"), (40, 44, "乙")), media_seconds=0.0, why="demo.srt 旁边找不到配对的媒体文件")
    ck("E1 没有媒体时长时覆盖率如实报「没算」", nomedia["coverage"]["available"] is False and nomedia["coverage"]["ratio"] is None,
       str(nomedia["coverage"]))
    ck("E2 说明里写「是缺输入，不是质检被关着」", "不是质检被关着" in nomedia["coverage"]["note"], nomedia["coverage"]["note"])
    ck("E3 原因把缺什么写在前面（找不到配对媒体）", "旁边找不到配对的媒体文件" in nomedia["coverage"]["note"], nomedia["coverage"]["note"])
    ck("E4 缺媒体时段尾那项也报 available=False，不装作量出来是 0 秒",
       nomedia["gaps"]["tail"]["available"] is False and nomedia["gaps"]["tail"]["seconds"] is None
       and nomedia["gaps"]["tail"]["tolerated"] is False, str(nomedia["gaps"]["tail"]))
    ck("E5 缺媒体时说明改成「末句之后那段没算」，不再出现「片尾 N 秒以内」",
       "拿不到媒体时长" in nomedia["gaps"]["note"] and "片尾 0 秒以内" not in nomedia["gaps"]["note"], nomedia["gaps"]["note"][:70])
    ck("E6 日志句里不写「片尾空档」这一节（没量出来的东西不上日志）",
       "片尾空档" not in S.qc_timeline_text(nomedia), S.qc_timeline_text(nomedia))
    ck("E7 日志句把缺的原因带出来", "覆盖率没算" in S.qc_timeline_text(nomedia) and "找不到配对的媒体文件" in S.qc_timeline_text(nomedia),
       S.qc_timeline_text(nomedia))
    ck("E8 缺媒体不影响另两维照常算", nomedia["gaps"]["available"] and nomedia["speed"]["available"] and nomedia["gaps"]["max"] == 36.0,
       str(nomedia["gaps"]["max"]))
    m = DL / "demo.mp4"
    m.write_bytes(b"fake")
    srt = DL / "demo.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\n甲\n", encoding="utf-8")
    install_ffprobe({})
    secs, mp, why = S._qc_media_seconds(srt, "")
    ck("E9 本机没有可用的 ffprobe 时长时如实报读不出", secs == 0.0 and "时长" in why, f"{secs}/{why}")
    tl = run(cues((1, 3, "甲")), media_seconds=0.0, why=why)
    ck("E10 「读不出时长」这句原因也会原样写进界面的没算说明", why.split("（")[0] in tl["coverage"]["note"], tl["coverage"]["note"])
    S._ffprobe_bin = lambda: ""
    secs2, _mp2, why2 = S._qc_media_seconds(srt, "")
    ck("E11 压根没有 ffprobe 时报「本机没有 ffprobe」", secs2 == 0.0 and "没有 ffprobe" in why2, why2)
    install_ffprobe({m: 12.5})
    secs3, mp3, why3 = S._qc_media_seconds(srt, "")
    ck("E12 ffprobe 探得到时返回秒数与媒体路径", secs3 == 12.5 and mp3.endswith("demo.mp4") and why3 == "", f"{secs3}/{mp3}")

    # ---------------- F 配对与命名：字幕名带语言后缀也找得回媒体
    for nm, stem in (("MV.zh-Hans.vtt", "MV"), ("MV_zh.srt", "MV"), ("MV.bi.ass", "MV"), ("MV.ai.srt", "MV")):
        p = DL / "keep" / nm
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("1\n00:00:01,000 --> 00:00:02,000\n甲\n", encoding="utf-8")
        stems = S._qc_media_stems(p)
        ck(f"F1 剥后缀：{nm} 找回主干 {stem}", stems[0] == nm.rsplit(".", 1)[0] and stem in stems, str(stems))
    p2 = DL / "keep" / "House.part1.srt"
    p2.write_text("1\n00:00:01,000 --> 00:00:02,000\n甲\n", encoding="utf-8")
    ck("F2 不像语言码的尾巴不乱剥（part1 保持原样）", S._qc_media_stems(p2)[0] == "House.part1", str(S._qc_media_stems(p2)))
    mv = DL / "keep" / "MV.mp4"
    mv.write_bytes(b"fake")
    install_ffprobe({mv: 60.0})
    secs4, mp4, why4 = S._qc_media_seconds(DL / "keep" / "MV.zh-Hans.vtt", "")
    ck("F3 带语言后缀的字幕能顺回同目录那份媒体", secs4 == 60.0 and mp4.endswith("MV.mp4"), f"{secs4}/{mp4}/{why4}")

    # ---------------- G 流水线里的日志（translate_srt_file）
    def fake_translate(texts, target, source, lg):
        # 最后那句译成一大坨，让「读速超限」这一维在流水线日志里也真的亮一次
        return ["这句长得离谱所以要挤在半秒里读完而且真的读不完" if "挤进" in t else "译译" + t[:1] for t in texts]

    _orig_fn = S._translate_batch_openai
    S._translate_batch_openai = fake_translate
    srcg = DL / "pipe.srt"
    srcg.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\n第一句话\n\n2\n00:00:04,000 --> 00:00:05,000\n嗯\n\n"
        "3\n00:00:40,000 --> 00:00:42,000\n同一句话\n\n4\n00:00:43,000 --> 00:00:45,000\n同一句话\n\n"
        "5\n00:00:46,000 --> 00:00:48,000\n同一句话\n\n6\n00:00:49,000 --> 00:00:50,000\n这句特别长所以要挤进一秒里读完而且真的很长\n",
        encoding="utf-8")
    pipe_media = DL / "pipe.mp4"
    pipe_media.write_bytes(b"fake")
    install_ffprobe({pipe_media: 60.0})
    lg = FakeLog()
    out = S.translate_srt_file(str(srcg), provider="openai", target_lang="zh", log=lg.log)
    txts = lg.texts()
    ck("G1 流水线日志里出现「字幕时间轴」一行", any("字幕时间轴:" in t for t in txts), str([t for t in txts if "时间轴" in t][:1]))
    ck("G2 覆盖率按配对的媒体算出来了（那份 60 秒的 mp4）", any("字幕时间轴:" in t and "覆盖率 " in t and "媒体 60 秒" in t for t in txts),
       str([t for t in txts if t.startswith("字幕时间轴")][:1]))
    ck("G3 大空档单独一行并点名第几句之前", any("句之前空了" in t for t in txts), str([t for t in txts if "空了" in t][:1]))
    ck("G4 读速超上限单独一行，字每秒与字数都在", any("读速" in t and "个字挤在" in t for t in txts), str([t for t in txts if "读速" in t][:1]))
    ck("G5 复读三遍那处点名了范围", any("连着复读" in t for t in txts), str([t for t in txts if "复读" in t][:1]))
    ck("G6 语气词与复读只报名单、写明没替用户删", any("没有替你删" in t for t in txts), str([t for t in txts if "没有替你删" in t][:1]))
    ck("G7 机翻产物照常写出，时间轴这步没改正文", Path(out).is_file() and "译译" in Path(out).read_text(encoding="utf-8"), out)
    n_before = len(lg.texts())
    S.cfg.data["subtitle_qc"] = False
    lg2 = FakeLog()
    S.translate_srt_file(str(srcg), provider="openai", target_lang="zh", log=lg2.log)
    t2 = lg2.texts()
    ck("G8 质检关闭时明确写「字幕质检没开」", any("字幕质检没开" in t for t in t2), str([t for t in t2 if "质检" in t][:1]))
    ck("G9 关闭时把「看不到质检行不等于查过且没问题」一起写出来",
       any("不等于" in t and "查过且没问题" in t for t in t2), str([t for t in t2 if "不等于" in t][:1]))
    ck("G10 关闭时既没有逐句对照行也没有时间轴行",
       not any("字幕质检:" in t for t in t2) and not any("字幕时间轴:" in t for t in t2), str(len(t2)))
    S.cfg.data["subtitle_qc"] = True
    lg3 = FakeLog()
    S.translate_srt_file(str(srcg), provider="openai", target_lang="zh", log=lg3.log)
    ck("G11 重新打开后时间轴行又回来了（开关只认配置，不会被上一次结果粘住）",
       any("字幕时间轴:" in t for t in lg3.texts()), str(len(lg3.texts())))
    ck("G12 开着跑的日志行数多于关掉跑的", n_before > 0 and len(lg3.texts()) > len(t2), f"{len(lg3.texts())}/{len(t2)}")

    # ---------------- H 转写产物顺手自检（_qc_report_written）
    tr = DL / "transcribed.srt"
    tr.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\n同一句话\n\n2\n00:00:04,000 --> 00:00:06,000\n同一句话\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\n同一句话\n\n4\n00:00:10,000 --> 00:00:11,000\n嗯\n",
        encoding="utf-8")
    tr_media = DL / "transcribed.mp4"
    tr_media.write_bytes(b"fake")
    install_ffprobe({tr_media: 20.0})
    lg4 = FakeLog()
    S._qc_report_written([str(tr), str(tr_media), str(DL / "不存在.srt")], tr_media, "zh", log=lg4.log)
    t4 = lg4.texts()
    ck("H1 刚转写出来的字幕也报一遍时间轴三维", any("字幕时间轴:" in t for t in t4), str(t4[:1]))
    ck("H2 媒体没配对的（不存在那份）不会崩，只是不写行", len([t for t in t4 if "字幕时间轴" in t]) == 1, str(t4))
    ck("H3 非字幕文件（那份 mp4）不参与统计", all("transcribed.mp4" not in t for t in t4), str(t4))
    ck("H4 转写产物的名单说明点明 Whisper 在静音与片尾背景乐上最容易复读", any("Whisper" in t and "没有替你删" in t for t in t4), str([t for t in t4 if "Whisper" in t][:1]))
    ck("H5 这一路同样没改动字幕文件", tr.read_text(encoding="utf-8").count("同一句话") == 3, "复读句被删了")
    before = tr.stat().st_mtime_ns
    S._qc_report_written([str(tr)], tr_media, "zh", log=FakeLog().log)
    ck("H6 反复自检也不写盘", tr.stat().st_mtime_ns == before, str(tr.stat().st_mtime_ns))

    # ---------------- I 端点：/api/subtitle/qc 带回时间轴
    with_sib = DL / "ep.srt"
    with_sib.write_text("1\n00:00:01,000 --> 00:00:03,000\n第一句\n\n2\n00:00:30,000 --> 00:00:32,000\n第二句\n", encoding="utf-8")
    ep_media = DL / "ep.mp4"
    ep_media.write_bytes(b"fake")
    install_ffprobe({ep_media: 40.0})

    def http_error(fn, *a, **kw):
        from fastapi import HTTPException
        try:
            return (200, fn(*a, **kw))
        except HTTPException as e:
            return (e.status_code, e.detail)

    code, r = http_error(S.api_subtitle_qc, {"path": str(with_sib)})
    ck("I1 端点 200 且回 timeline / timeline_text / media / media_seconds 四样",
       code == 200 and all(k in r for k in ("timeline", "timeline_text", "media", "media_seconds")), str(sorted(r)[:6]))
    ck("I2 媒体时长确实带回来了（40 秒那份）", r["media_seconds"] == 40.0 and r["media"].endswith("ep.mp4"), str(r["media_seconds"]))
    ck("I3 三维都在结构里", all(k in r["timeline"] for k in ("coverage", "gaps", "speed", "noise")), str(sorted(r["timeline"])))
    ck("I4 阈值随结构一起回，界面不用自己抄一遍数字", r["timeline"]["thresholds"]["gap"] == 30.0
       and r["timeline"]["thresholds"]["cps"] == 9.0, str(r["timeline"]["thresholds"]))
    ck("I5 覆盖率这一项算出来了（单语、没有另一路也照算）", r["timeline"]["coverage"]["available"] and r["paired"] is False,
       f"{r['timeline']['coverage']['ratio']}/{r['paired']}")
    ck("I6 大空档进了间隙名单（27 秒的那段没到 30 所以不计）", r["timeline"]["gaps"]["max"] == 27.0
       and r["timeline"]["gaps"]["count_over"] == 0, str(r["timeline"]["gaps"]["max"]))
    ck("I7 timeline_text 是给日志用的一句人话", r["timeline_text"].startswith("字幕时间轴: ") and " · " in r["timeline_text"], r["timeline_text"][:60])
    ck("I8 片尾 8 秒的空档报了但标明不计入", abs(r["timeline"]["gaps"]["tail"]["seconds"] - 8.0) < 0.01
       and r["timeline"]["gaps"]["tail"]["tolerated"], str(r["timeline"]["gaps"]["tail"]))

    orphan = DL / "lonely.srt"
    orphan.write_text("1\n00:00:01,000 --> 00:00:03,000\n孤零零的一份字幕\n", encoding="utf-8")
    code2, r2 = http_error(S.api_subtitle_qc, {"path": str(orphan)})
    ck("I9 旁边没有媒体：端点不报错，覆盖率改口说没算", code2 == 200 and r2["timeline"]["coverage"]["available"] is False, str(code2))
    ck("I10 界面上拿得到的那句原话：是缺输入，不是质检被关着", "不是质检被关着" in r2["timeline"]["coverage"]["note"], r2["timeline"]["coverage"]["note"])
    ck("I11 缺媒体时 media 字段回空串（界面据此才显示「没找到配对媒体」那行）", r2["media"] == "" and r2["media_seconds"] == 0.0, str(r2["media"]))

    # ---------------- J 界面（静态断言：这一块必须在没有可疑句时也渲染）
    html = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")
    # 界面文案搬到 static/i18n.js 的词表里了：模板只留键名，所以每条都两头查 ——
    # 键在这个模板里被用到，而且那句中文原话仍然在词表里（缺任一条，界面就印键名或印回中文）
    lex = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")

    def ui(key: str, phrase: str = "") -> bool:
        # 键名后面那个单引号要一起当锚：带占位符的调用写成 tr('k', {n: ...})，
        # 只认 tr('k') 会把这一类全判成没用到；带了引号又不会误配 tr('kk')
        return "tr('%s'" % key in html and (not phrase or phrase in lex)

    ck("J1 界面上有「时间轴三维」这一块", ui("files.tlTitle", "时间轴三维"), "")
    ck("J2 这一块只看 timeline 在不在，不看可疑行数（没可疑句也要显示三维）",
       'v-if="srtQc.timeline"' in html and html.index('v-if="srtQc.timeline"') > html.index("srtQc.rows.length"), "")
    ck("J3 缺媒体时的原话写进界面：是缺输入，不是质检没开", ui("files.tlNoMedia", "是缺输入，不是质检没开"), "")
    ck("J4 三维各自有「这一项没算」的兜底",
       html.count("tr('files.notComputed')") >= 2 and "这一项没算" in lex, str(html.count("tr('files.notComputed')")))
    ck("J5 片尾那项按 available 条件渲染，缺媒体时不显示 0 秒", 'srtQc.timeline.gaps.tail.available' in html
       and ui("files.tailUnknown", "片尾那一段没分出来"), "")
    ck("J6 名单截断要在界面上说清楚「其余 N 句没列在这里」",
       html.count("tr('files.gapsRest'") + html.count("tr('files.speedRest'") >= 2 and "没列在这里" in lex, "")
    ck("J7 删名单的按钮走 qcDropNoise，且先弹确认", "qcDropNoise" in html and ui("files.tDropNoiseTitle", "按名单删句"), "")
    ck("J8 删完只改界面上的行、不写盘（提示里带「还没写盘」）", ui("files.tNoiseDropped", "还没写盘"), "")
    ck("J9 空档与读速两处都挂 qcJumpTo，且跳转支持空档用的 before 句序",
       "q.i || q.before" in html and html.count('@click="qcJumpTo(q)"') >= 2, str(html.count('@click="qcJumpTo(q)"')))
    ck("J9b 片头空档在界面上说成「第一条之前」而不是「第 1 句之前」",
       ui("files.beforeFirstShort", "第一条之前") and ui("files.gapHead", "片头"), "")
    ck("J9c 最大的那段是片头时，界面那行不说「第 1 句之前」", ui("files.beforeFirst", "第一条字幕之前"), "")
    ck("J10 退出校对或重跑质检会清掉上一份的时间轴结果", "srtQc.timeline = null" in html and "srtQc.media = ''" in html, "")
    ck("J11 语气词与复读都写明只列名单不代删", ui("files.noiseNote", "只列名单、没有替你删"), "")
finally:
    S.cfg, S.log_mgr, S._ffprobe_bin, S._ffprobe_info = _REAL
    shutil.rmtree(TMP, ignore_errors=True)

print("\n== 汇总 ==")
print(f"共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
