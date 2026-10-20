#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐句字幕校对台（/api/ai/srt 读、/api/ai/srt/save 写回）离线自检。

只写 %TEMP%，不碰真实下载目录与 config.json。
跑法：PYTHONIOENCODING=utf-8 python tests/srtedit_test.py
"""
import os
import re
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

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
        raise AssertionError("校对台不该写 config.json")


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info", k="", kv=None):
        self.rows.append((level, str(msg)))


TMP = Path(tempfile.mkdtemp(prefix="md_srtedit_"))
DL = TMP / "downloads"
DL.mkdir(parents=True)

_REAL = (S.cfg, S.log_mgr)
LOGS = FakeLog()
S.cfg = FakeCfg({"download_dir": str(DL)})
S.log_mgr = LOGS

SRT_OK = """1
00:00:01,000 --> 00:00:03,000
[说话人1] 第一句

2
00:00:05,000 --> 00:00:07,500
[说话人2] 第二句

3
00:00:09,000 --> 00:00:11,000
第三句没有说话人
"""


def http_error(fn, *a, **kw):
    """调 FastAPI 处理函数，把 HTTPException 变成返回值，便于断言状态码与文案。"""
    from fastapi import HTTPException
    try:
        return (200, fn(*a, **kw))
    except HTTPException as e:
        return (e.status_code, e.detail)


try:
    # ---------------- A 读取
    f = DL / "demo.srt"
    f.write_text(SRT_OK, encoding="utf-8")
    code, r = http_error(S.api_ai_srt_read, str(f))
    ck("A1 读取返回 200 且是 3 句", code == 200 and len(r["cues"]) == 3, f"{code}/{len(r.get('cues', []))}")
    c0 = r["cues"][0]
    ck("A2 每句给到 start/end/speaker/text", c0["start"] == 1.0 and c0["end"] == 3.0
       and c0["speaker"] == "1" and c0["text"] == "第一句", str(c0))
    ck("A3 正文里没有说话人的那行 speaker 为空", r["cues"][2]["speaker"] == ""
       and r["cues"][2]["text"] == "第三句没有说话人", str(r["cues"][2]))
    ck("A4 序号从 1 连续", [c["idx"] for c in r["cues"]] == [1, 2, 3], str([c["idx"] for c in r["cues"]]))
    ck("A5 给了 mtime_ts 与 mtime 供界面显示", isinstance(r["mtime_ts"], float)
       and len(r["mtime"]) == 19, f"{r['mtime_ts']}/{r['mtime']}")
    ck("A6 返回的是相对下载目录的路径，不是绝对路径", r["srt"] == "demo.srt" and "TEMP" not in r["srt"].upper(), r["srt"])
    ck("A7 format 标出这是 srt", r["format"] == "srt", r["format"])

    # 媒体路径也能进：demo.mp4 → 同名 demo.srt
    (DL / "demo.mp4").write_bytes(b"fake")
    code, r2 = http_error(S.api_ai_srt_read, str(DL / "demo.mp4"))
    ck("A8 传媒体文件也能找回它那份字幕", code == 200 and len(r2["cues"]) == 3 and r2["srt"] == "demo.srt", str(code))

    (DL / "solo.mp4").write_bytes(b"fake")
    code, r3 = http_error(S.api_ai_srt_read, str(DL / "solo.mp4"))
    ck("A9 没有字幕的媒体：报错点名让用户先转写", code == 400 and "还没有字幕" in str(r3), f"{code}/{r3}")

    code, r4 = http_error(S.api_ai_srt_read, "")
    ck("A10 空 path 直接 400", code == 400 and "缺少 path" in str(r4), f"{code}/{r4}")

    code, r5 = http_error(S.api_ai_srt_read, str(DL / "不存在.srt"))
    ck("A11 不存在的路径被拒（不越界读文件）", code == 400 and "无效文件路径" in str(r5), f"{code}/{r5}")

    # 毫秒位为零填充时不能被当成两位小数（,040 = 40ms，不是 400ms）
    msf = DL / "ms.srt"
    msf.write_text("1\n00:00:10,040 --> 00:00:10,900\n毫秒\n", encoding="utf-8")
    code, rms = http_error(S.api_ai_srt_read, str(msf))
    ck("A12 毫秒按位数换算：,040 读成 0.04 秒", code == 200
       and abs(rms["cues"][0]["start"] - 10.04) < 1e-6 and abs(rms["cues"][0]["end"] - 10.9) < 1e-6,
       str(rms["cues"][0] if code == 200 else rms))
    ck("A13 只给一位/两位小数时仍按十分位补全",
       S._srt_ts_to_ms("00:00:01,5") == 1500 and S._srt_ts_to_ms("00:00:01,25") == 1250
       and S._srt_ts_to_ms("00:00:01.040") == 1040, str(S._srt_ts_to_ms("00:00:01,5")))

    # ---------------- B 写回：备份 + 覆盖
    before = f.read_text(encoding="utf-8")
    cues = [{k: c[k] for k in ("start", "end", "speaker", "text")} for c in r["cues"]]
    cues[0]["text"] = "第一句改过了"
    cues[1]["start"] = 5.5
    code, s = http_error(S.api_ai_srt_save, {"path": str(f), "cues": cues})
    ck("B1 保存返回 200 并报告写入句数", code == 200 and s["count"] == 3, f"{code}/{s}")
    ck("B2 备份文件真的生成了", (DL / Path(s["backup"]).name).is_file()
       and s["backup"].startswith("demo.srt.bak-"), s["backup"])
    bak_txt = (DL / Path(s["backup"]).name).read_text(encoding="utf-8")
    ck("B3 备份内容与改之前完全一致（不是改之后的）", bak_txt == before, f"{len(bak_txt)}/{len(before)}")
    ck("B4 原文件名还在，没被改名或搬走", f.is_file(), str(f))
    code, after = http_error(S.api_ai_srt_read, str(f))
    ck("B5 改过的正文读回来了", after["cues"][0]["text"] == "第一句改过了", after["cues"][0]["text"])
    ck("B6 改过的时间读回来了（5.0 → 5.5）", abs(after["cues"][1]["start"] - 5.5) < 0.001, str(after["cues"][1]["start"]))
    ck("B7 说话人标记没被弄丢：剥掉写回后仍在正文里", after["cues"][0]["speaker"] == "1"
       and after["cues"][1]["speaker"] == "2" and after["cues"][2]["speaker"] == "",
       str([(c["speaker"], c["text"]) for c in after["cues"]]))
    ck("B8 未改动的第三句原样保留", after["cues"][2]["text"] == "第三句没有说话人", after["cues"][2]["text"])
    ck("B9 行数与列结构合法（序号连续 1..3）", [c["idx"] for c in after["cues"]] == [1, 2, 3])
    ck("B10 日志写了改了几句、备份叫什么", any("逐句校对字幕" in m and "demo.srt" in m and "备份" in m for _, m in LOGS.rows),
       str(LOGS.rows[-1] if LOGS.rows else ""))
    ck("B11 日志里没有 Cookie、令牌那类字样", all(
        not any(w in m.lower() for w in ("cookie", "token", "api_hash", "secret")) for _, m in LOGS.rows))

    # ---------------- C 边界与拒绝
    n_before = len(list(DL.glob("demo.srt")))
    mid = f.read_text(encoding="utf-8")
    code, s2 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": []})
    ck("C1 空表被拒", code == 400 and "没有要写入" in str(s2), f"{code}/{s2}")
    code, s3 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [{"start": 1, "end": 2, "text": "  "}]})
    ck("C2 全是空正文被拒", code == 400 and "正文都是空的" in str(s3), f"{code}/{s3}")
    code, s4 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": "不是列表"})
    ck("C3 cues 不是列表被拒", code == 400, f"{code}/{s4}")
    code, s5 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [{"start": "abc", "end": 2, "text": "有正文"}]})
    ck("C4 时间不是数字被拒且点名第几句", code == 400 and "第 1 句" in str(s5) and "不是数字" in str(s5), f"{code}/{s5}")
    ck("C5 反向验证：这几次被拒都没动过原文件", n_before == 1 and f.read_text(encoding="utf-8") == mid)
    code, s6 = http_error(S.api_ai_srt_save, {"path": str(DL / "solo.mp4"), "cues": [{"start": 1, "end": 2, "text": "x"}]})
    ck("C6 没有字幕的媒体存不进去", code == 400, f"{code}/{s6}")
    code, s7 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [{"start": 1, "end": 2, "text": "x"}] * 20001})
    ck("C7 行数超上限被拒", code == 400 and "超出单份字幕上限" in str(s7), f"{code}/{s7}")

    # ---------------- D 止点早于起点 / 空行跳过 / 备份不撞名
    code, s8 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [
        {"start": 10.0, "end": 9.0, "text": "止比起早"},
        {"start": 20.0, "end": 21.0, "text": ""},
        {"start": -5.0, "end": 2.0, "text": "起点是负的"},
    ]})
    ck("D1 保存成功且跳掉空正文那行", code == 200 and s8["count"] == 2 and s8["dropped"] == 1, str(s8))
    code, after2 = http_error(S.api_ai_srt_read, str(f))
    ck("D2 止比起早的那句被兜到至少 40ms 而不是写负时长",
       abs(after2["cues"][0]["end"] - after2["cues"][0]["start"] - 0.04) < 0.001,
       str(after2["cues"][0]))
    ck("D3 负起点夹到 0", after2["cues"][1]["start"] == 0.0, str(after2["cues"][1]["start"]))
    baks = sorted(p.name for p in DL.glob("demo.srt.bak-*"))
    code, s9 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [
        {"start": 1.0, "end": 2.0, "text": "再改一次"}]})
    baks2 = sorted(p.name for p in DL.glob("demo.srt.bak-*"))
    ck("D4 一秒内连续保存不会互相覆盖备份", len(baks2) == len(baks) + 1 and s9["backup"] not in baks,
       f"{len(baks)}→{len(baks2)}")

    # ---------------- E mtime 闸门
    code, rd = http_error(S.api_ai_srt_read, str(f))
    stale = rd["mtime_ts"] - 5.0
    code, s10 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [
        {"start": 1, "end": 2, "text": "带闸门的一改"}], "base_mtime": stale})
    ck("E1 读完之后文件被改过 → 409 且不写入", code == 409 and "又被改写" in str(s10), f"{code}/{s10}")
    ck("E2 被闸门拦下时正文还是上一版", "带闸门的一改" not in f.read_text(encoding="utf-8"))
    code, s11 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [
        {"start": 1, "end": 2, "text": "闸门通过的一改"}], "base_mtime": rd["mtime_ts"]})
    ck("E3 mtime 一致时正常写入", code == 200 and "闸门通过的一改" in f.read_text(encoding="utf-8"), f"{code}")
    code, s12 = http_error(S.api_ai_srt_save, {"path": str(f), "cues": [
        {"start": 1, "end": 2, "text": "不给基准时间"}], "base_mtime": ""})
    ck("E4 不传 base_mtime 就不拦（老调用方照样能用）", code == 200, f"{code}/{s12}")

    # ---------------- F vtt 走同一套
    v = DL / "cap.vtt"
    v.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n一句 vtt\n", encoding="utf-8")
    code, rv = http_error(S.api_ai_srt_read, str(v))
    ck("F1 vtt 能读成一句", code == 200 and len(rv["cues"]) == 1 and rv["cues"][0]["text"] == "一句 vtt"
       and rv["format"] == "vtt", f"{code}/{rv if code != 200 else rv['cues']}")
    code, sv = http_error(S.api_ai_srt_save, {"path": str(v), "cues": [
        {"start": 1.0, "end": 2.5, "text": "vtt 改过了"}]})
    raw_v = v.read_text(encoding="utf-8")
    ck("F2 vtt 写回还是 vtt（首行 WEBVTT、时间用点）", code == 200 and raw_v.startswith("WEBVTT")
       and "00:00:01.000 --> 00:00:02.500" in raw_v, raw_v[:60].replace("\n", "\\n"))
    ck("F3 vtt 也留了备份", (DL / Path(sv["backup"]).name).is_file() and sv["backup"].startswith("cap.vtt.bak-"), sv["backup"])
    code, rv2 = http_error(S.api_ai_srt_read, str(v))
    ck("F4 vtt 改完再读回得到同一句", len(rv2["cues"]) == 1 and rv2["cues"][0]["text"] == "vtt 改过了")

    # ---------------- G 路由与接口面
    paths = [getattr(r_, "path", "") for r_ in S.app.routes]
    ck("G1 两条新路由都挂上了", "/api/ai/srt" in paths and "/api/ai/srt/save" in paths,
       str([p for p in paths if p.endswith("/srt") or p.endswith("/srt/save")]))
    html = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")
    ck("G2 界面调的是这两个同名接口", "/api/ai/srt?path=" in html and "'/api/ai/srt/save'" in html,
       f"{html.count('/api/ai/srt')}")
    # 整句前后移必须「起止同移、句长不变」。实测踩过的坑：止点写成对
    # r.start.toFixed(3)（字符串）再拼接 dur，后面 .toFixed 直接抛错，结果起点改了、止点没改，字幕被压短。
    # 用源码断言把这个形态钉住。
    shift = re.search(r"function srtShiftSel\(step\).*?\n        \}", html, re.S)
    ck("G3 前后移按「起点+句长」重算止点（不能对字符串用 toFixed）",
       bool(shift) and "r.end = +(r.start + dur).toFixed(3);" in shift.group(0)
       and "r.start.toFixed(3) + dur" not in shift.group(0),
       (shift.group(0).strip().replace("\n", " ")[:110] if shift else "找不到 srtShiftSel"))
    ck("G4 校对行里起/止/正文三样都在，且都有合并与删",
       'srt-edit-row' in html and html.count("srtShiftSel(") >= 3 and "srtMerge(" in html and "srtDrop(" in html,
       f"shift={html.count('srtShiftSel(')}")

    # ---------------- H 毫秒位数：时间轴校准与校对台共用同一个换算函数
    cues = [{"timing": "00:00:10,040 --> 00:00:12,500", "text": "甲"},
            {"timing": "00:01:00,250 --> 00:01:05,000", "text": "乙"},
            {"timing": "00:00:01,5 --> 00:00:03,040", "text": "丙"}]
    sh = S.shift_srt_cues(cues, offset_ms=1000)
    ck("H1 平移 1 秒时 ,040 仍按 40 毫秒算（不是 400）",
       sh[0]["timing"] == "00:00:11,040 --> 00:00:13,500", sh[0]["timing"])
    ck("H2 三位毫秒照常", sh[1]["timing"] == "00:01:01,250 --> 00:01:06,000", sh[1]["timing"])
    ck("H3 位数不足（,5 / 两位）按位数补齐换算", sh[2]["timing"] == "00:00:02,500 --> 00:00:04,040", sh[2]["timing"])
finally:
    S.cfg, S.log_mgr = _REAL
    shutil.rmtree(TMP, ignore_errors=True)

print(f"\n共 {TOTAL} 项，失败 {len(FAILED)} 项")
print("FAILED:", ", ".join(FAILED) if FAILED else "none")
sys.exit(1 if FAILED else 0)
