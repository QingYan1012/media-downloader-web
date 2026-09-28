# -*- coding: utf- -*-
"""最终验收：全部走 diarize_tools 的公开入口（_seg_vector/MERGE_THRESHOLD 改动的就是这里），
不再用脚本内的复刻实现。
  A 真实单人主讲实录  → 只该 1~2 类
  B 男女交替          → 2 类且交替
  C 两个男声          → 2 类
  D 同男声 x4         → 1 类（→ 上层不加任何标记）
  E 相近音色          → 允许并成 1 类，但不能乱拆
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
import diarize_tools as dt  # noqa: E402
import server               # noqa: E402

dt.set_ffmpeg(os.path.join(APP, "tools", "ffmpeg.exe"))
SR = 16000
tmp = Path(tempfile.mkdtemp(prefix="md_diar_final_"))
FF = os.path.join(APP, "tools", "ffmpeg.exe")


def gen(f0, formants, dur, amp=0.6, drift=0.03, noise=0.02):
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        f = f0 * (1.0 + drift * math.sin(2 * math.pi * 3.0 * t))
        v = 0.0
        for h in range(1, 12):
            harm = f * h
            w = 0.0
            for fc, bw in formants:
                w += math.exp(-((harm - fc) ** 2) / (2 * bw * bw)) / h
            v += w * math.sin(2 * math.pi * harm * t)
        v += noise * math.sin(2 * math.pi * 5237.0 * t + i * 0.7)
        out.append(max(-1.0, min(1.0, amp * v / 3.0)))
    return out


MALE = (110, [(500, 90), (1200, 120), (2500, 200)])
FEMALE = (220, [(900, 110), (2000, 160), (3200, 250)])
MALE2 = (128, [(420, 130), (1750, 150), (2600, 260)])
HARD = (150, [(650, 300), (1500, 300), (2400, 300)])


def synth(seqs, name, dur=1.4):
    buf, spans = [], []
    for i, p in enumerate(seqs):
        if i:
            buf.extend([0.0] * int(0.4 * SR))
        a = len(buf) / SR
        buf.extend(gen(*p, dur))
        spans.append((round(a, 3), round(len(buf) / SR, 3)))
    w = tmp / (name + ".wav")
    with wave.open(str(w), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR)
        f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in buf))
    return str(w), spans


CASES = {
    "B 男女交替": (synth([MALE, FEMALE] * 3, "mf"), [i % 2 for i in range(6)]),
    "C 两个男声": (synth([MALE, MALE2] * 3, "mm"), [i % 2 for i in range(6)]),
    "D 同一男声": (synth([MALE] * 4, "s4"), [0] * 4),
    "E 相近音色": (synth([MALE, HARD] * 3, "hh"), [i % 2 for i in range(6)]),
}

dl = Path(APP) / "Downloads"
media = next(p for p in dl.glob("Nintendo Direct*.mkv"))
cues = server.parse_srt(media.with_suffix(".srt").read_text(encoding="utf-8", errors="ignore"))


def _se(c):
    a, _, b = (c.get("timing") or "").partition("-->")
    return server._srt_ts_to_ms(a) / 1000.0, server._srt_ts_to_ms(b) / 1000.0


spans = [x for x in (_se(c) for c in cues) if x[1] - x[0] >= 1.5][:70]
wav_real = tmp / "real.wav"
subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-t", str(spans[-1][1] + 2),
                "-i", str(media), "-vn", "-ac", "1", "-ar", str(SR), str(wav_real)], capture_output=True)

checks = []
ck = lambda n, c, note="": checks.append((n, bool(c), note))
log = lambda *a, **k: None

lab = dt.diarize_segments(str(wav_real), spans, log=log, max_speakers=4)
k = len({x for x in lab if x})
ck("A 真实单人主讲 70 句 → 不超过 2 类", k <= 2, f"实际 {k} 类")
print("A 真实:", k, "类，前 20 句标签", lab[:20])

for name, ((path, sp), truth) in CASES.items():
    lab = dt.diarize_segments(path, sp, log=log, max_speakers=4)
    kk = len({x for x in lab if x})
    pairs_same = all((truth[i] == truth[j]) == (lab[i] == lab[j]) for i in range(len(lab)) for j in range(i + 1, len(lab)))
    print(f"{name}: {lab} 真值 {truth} → {kk} 类")
    exp = 1 if name == "D 同一男声" else 2
    if name == "E 相近音色":
        ck(f"{name} → 不乱拆（<=2 类）", kk <= 2, f"实际 {kk} 类")
    elif name == "D 同一男声":
        ck(f"{name} → 只 1 类", kk == 1, f"实际 {kk} 类")
    else:
        ck(f"{name} → 恰好 2 类且分组正确", kk == 2 and pairs_same, f"实际 {kk} 类 分组正确={pairs_same}")

# 阈值确实是模块里的 0.09
ck("MERGE_THRESHOLD 已换成标定值 0.09", abs(dt.MERGE_THRESHOLD - 0.09) < 1e-9, str(dt.MERGE_THRESHOLD))

# server 侧：单人时不加标记，多人时加
CFG_ON = {"model": "base", "device": "cpu", "compute": "int8", "lang": "zh", "diarize": True, "max_speakers": 3}
server._whisper_cfg = lambda: dict(CFG_ON)
import faster_whisper  # noqa: E402


class FakeSeg:
    def __init__(self, a, b, t):
        self.start, self.end, self.text = a, b, t


class FakeModel:
    def __init__(self, *a, **k):
        pass

    def transcribe(self, path, **kw):
        return [FakeSeg(a, b, f"第{i+1}句") for i, (a, b) in enumerate(SPANS[0])], type("I", (), {"language": "zh"})()


faster_whisper.WhisperModel = FakeModel
SPANS = [[], []]
mp4 = tmp / "mf.mp4"
subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", CASES["B 男女交替"][0][0],
                "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", str(mp4)], capture_output=True)
SPANS[0] = CASES["B 男女交替"][0][1]
logs = []
out = server._whisper_via_faster(mp4, "transcribe", "zh", lambda m, lv="info": logs.append(m))
txt = out.read_text(encoding="utf-8")
tagged = [ln for ln in txt.split("\n") if ln.startswith("[说话人")]
print("多人 SRT 标记:", tagged)
ck("server 侧：男女对白写出 6 个标记", len(tagged) == 6, str(len(tagged)))
ck("server 侧：交替 1/2", [t[4] for t in tagged] == ["1", "2", "1", "2", "1", "2"], str([t[4] for t in tagged]))

one4 = tmp / "one4.mp4"
subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y", "-i", tmp / "s4.wav",
                "-f", "lavfi", "-i", "color=c=black:s=320x240:r=10", "-shortest",
                "-c:v", "libx264", "-c:a", "aac", str(one4)], capture_output=True)
SPANS[0] = CASES["D 同一男声"][0][1]
logs.clear()
out2 = server._whisper_via_faster(one4, "transcribe", "zh", lambda m, lv="info": logs.append(m))
txt2 = out2.read_text(encoding="utf-8")
ck("server 侧：单人转写不加标记", "[说话人" not in txt2)
ck("server 侧：单人时日志说明了原因", any("只听出一个人" in m for m in logs), " | ".join(logs))

print()
for n, ok, note in checks:
    print(("PASS " if ok else "FAIL ") + n + (f"  [{note}]" if note and not ok else ""))
print("FAILED:", ", ".join(n for n, o, _ in checks if not o) or "none")
print("config 未被写:", "diarization_enabled" not in server.cfg.data or server.cfg.data["diarization_enabled"] is False)
print("tmp:", tmp)
