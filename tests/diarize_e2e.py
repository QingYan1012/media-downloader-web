# -*- coding: utf- -*-
"""端到端（决定论版）：把 faster-whisper 换成假模型，只验 server 这一侧的写盘接线——
开开关后 [说话人N] 是否真进了 SRT、关掉时是否完全不变、分不出人时是否保持原样。
音频用合成的男女交替对白，只读写 %TEMP%。
"""
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

APP = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, APP)
SR = 16000


def gen(f0, formants, dur, amp=0.6):
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        f = f0 * (1.0 + 0.03 * math.sin(2 * math.pi * 3.0 * t))
        v = 0.0
        for h in range(1, 12):
            harm = f * h
            w = 0.0
            for fc, bw in formants:
                w += math.exp(-((harm - fc) ** 2) / (2 * bw * bw)) / h
            v += w * math.sin(2 * math.pi * harm * t)
        v += 0.02 * math.sin(2 * math.pi * 5237.0 * t + i * 0.7)
        out.append(max(-1.0, min(1.0, amp * v / 3.0)))
    return out


MALE = (110, [(500, 90), (1200, 120), (2500, 200)])
FEMALE = (220, [(900, 110), (2000, 160), (3200, 250)])

tmp = Path(tempfile.mkdtemp(prefix="md_diar_e2e_"))
media = tmp / "dialogue.mp4"
buf = []
spans = []
gap = int(0.4 * SR)
TEXTS = ["第一句男的说的", "第二句换女声", "第三句又回到男的", "第四句还是女的"]
for i in range(4):
    g = MALE if i % 2 == 0 else FEMALE
    buf.extend([0.0] * (gap if i else 0))
    start = len(buf) / SR
    buf.extend(gen(*g, 1.4))
    spans.append((round(start, 3), round(len(buf) / SR, 3)))
wav = tmp / "dialogue.wav"
with wave.open(str(wav), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in buf))
subprocess.run([os.path.join(APP, "tools", "ffmpeg.exe"), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(wav), "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10",
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(media)], capture_output=True)
print("合成音视频:", media.name, spans)

import server  # noqa: E402
import faster_whisper  # noqa: E402


class FakeSeg:
    def __init__(self, a, b, t):
        self.start, self.end, self.text = a, b, t


class FakeModel:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, path, **kw):
        return ([FakeSeg(a, b, t) for (a, b), t in zip(spans, TEXTS)],
                type("I", (), {"language": "zh"})())


faster_whisper.WhisperModel = FakeModel
_orig_import = __import__


def fake_import(name, *a, **k):
    if name == "faster_whisper":
        return faster_whisper
    return _orig_import(name, *a, **k)


server.__dict__["__builtins__"]  # noqa —— 只确认可访问
CFG = {"model": "base", "device": "cpu", "compute": "int8", "lang": "zh",
       "diarize": False, "max_speakers": 4}
server._whisper_cfg = lambda: dict(CFG)
logs = []
log = lambda m, lv="info": (logs.append(f"[{lv}] {m}"), print(f"  [{lv}] {m}"))

checks = []
ck = lambda n, c: checks.append((n, bool(c)))

# A) 开关关：与旧行为完全一致，不带任何标记
out = server._whisper_via_faster(media, "transcribe", "zh", log)
txt_off = out.read_text(encoding="utf-8")
ck("关时不写说话人", "[说话人" not in txt_off)
ck("关时 4 条字幕", txt_off.count("-->") == 4)
ck("关时不做声纹计算", not any("声纹" in m or "说话人分离" in m for m in logs))

# B) 开关开：贴标记
logs.clear()
CFG["diarize"] = True
out = server._whisper_via_faster(media, "transcribe", "zh", log)
txt_on = out.read_text(encoding="utf-8")
print("---- 开说话人后的 SRT ----")
print(txt_on)
ck("开时写了说话人标记", "[说话人1]" in txt_on and "[说话人2]" in txt_on)
ck("男女交替正确", [ln.split("]")[0] + "]" for ln in txt_on.split("\n")
    if ln.startswith("[说话人")] == ["[说话人1]", "[说话人2]", "[说话人1]", "[说话人2]"])
ck("时间轴没被改动", "--> 00:00:0" in txt_on and txt_on.count("-->") == 4)
ck("日志给出结论", any("说话人分离" in m for m in logs))

# C) 走 /api/ai/transcript 的解析器能还原回去
got = []
for c in server.parse_srt(txt_on):
    m = server.SPEAKER_PREFIX_RE.match(c["text"])
    got.append((m.group(2) if m else "", server.SPEAKER_PREFIX_RE.sub("", c["text"], count=1)))
print("parse_srt 还原:", got)
ck("解析回去 4 行", len(got) == 4)
ck("说话人号 1/2/1/2", [g[0] for g in got] == ["1", "2", "1", "2"])
ck("正文不含前缀", all(not g[1].startswith("[") for g in got))

# D) 全同一人：不该标
logs.clear()
male_wav = tmp / "male.wav"
mb = []
mspans = []
for i in range(3):
    mb.extend([0.0] * (gap if i else 0))
    a = len(mb) / SR
    mb.extend(gen(*MALE, 1.4))
    mspans.append((round(a, 3), round(len(mb) / SR, 3)))
with wave.open(str(male_wav), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in mb))
one = tmp / "one.mp4"
subprocess.run([os.path.join(APP, "tools", "ffmpeg.exe"), "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(male_wav),
                "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", str(one)], capture_output=True)
spans_back = list(spans)
spans[:] = mspans
print("单人 spans:", spans)
out2 = server._whisper_via_faster(one, "transcribe", "zh", log)
txt_one = out2.read_text(encoding="utf-8")
ck("单人时确实取到了音轨", any("取音频失败" not in m for m in logs) and not any("取音频失败" in m for m in logs))
ck("单人日志说只听出一个", any("只听出一个人的音色" in m for m in logs))
ck("单人时不加标记", "[说话人" not in txt_one)
spans[:] = spans_back
print()
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + n)
print("FAILED:", ", ".join(n for n, o in checks if not o) or "none")
print("config.json 未写:", server.cfg.data.get("diarization_enabled") is False, "| tmp:", tmp)
