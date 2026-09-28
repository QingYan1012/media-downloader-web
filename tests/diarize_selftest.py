# -*- coding: utf- -*-
"""离线自检 diarize_tools：合成两段音色交替的"对白"，看能不能分成两个人、且贴对行。
只写临时目录，不碰 config.json。
"""
import os
import sys
import wave
import math
import struct
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diarize_tools  # noqa: E402

SR = 16000


def voice(seed_f0, formants, dur, amp=0.6):
    """一个持续音 + 三个共振峰包络，近似一个人的音色。"""
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        f0 = seed_f0 * (1.0 + 0.03 * math.sin(2 * math.pi * 3.0 * t))
        v = 0.0
        for h in range(1, 12):
            harm = f0 * h
            w = 0.0
            for fc, bw in formants:
                w += math.exp(-((harm - fc) ** 2) / (2 * bw * bw)) / h
            v += w * math.sin(2 * math.pi * harm * t)
        # 轻噪声让频谱更"活"
        v += 0.02 * math.sin(2 * math.pi * 5237.0 * t + i * 0.7)
        out.append(max(-1.0, min(1.0, amp * v / 3.0)))
    return out


MALE = voice(110, [(500, 90), (1200, 120), (2500, 200)], 0.0)  # 占位，下面按需生成长度
FEMALE_PARAMS = (220, [(900, 110), (2000, 160), (3200, 250)])


def make_male(dur):
    return voice(110, [(500, 90), (1200, 120), (2500, 200)], dur)


def make_female(dur):
    return voice(*FEMALE_PARAMS[:1] + FEMALE_PARAMS[1:], dur) if False else voice(
        FEMALE_PARAMS[0], FEMALE_PARAMS[1], dur)


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples))


def main():
    tmp = tempfile.mkdtemp(prefix="md_diar_test_")
    media = os.path.join(tmp, "dialogue.wav")
    # 6 句，男女交替，句间 0.4s 静音
    spans = []
    buf = []
    gap = int(0.4 * SR)
    seq = [make_male, make_female] * 3
    for i, gen in enumerate(seq):
        start = len(buf) / SR
        chunk = gen(1.4)
        buf.extend([0.0] * (gap if i else 0))
        start = len(buf) / SR
        buf.extend(chunk)
        end = len(buf) / SR
        spans.append((round(start, 3), round(end, 3)))
    write_wav(media, buf)
    print("合成对白:", media, "时长", round(len(buf) / SR, 2), "s")
    for s in spans:
        print("  span", s)

    logs = []
    log = lambda m, lv="info": (logs.append(m), print(f"  [log:{lv}] {m}"))
    print("available():", diarize_tools.available())
    labels = diarize_tools.diarize_segments(media, spans, log=log, max_speakers=4)
    print("labels:", labels)

    checks = []
    ck = lambda name, cond: checks.append((name, bool(cond)))
    ck("返回逐句标签", labels is not None and len(labels) == len(spans))
    ck("分成 2 类", labels and len({x for x in labels if x}) == 2)
    # 真值：0,2,4 是男（同一人），1,3,5 是女
    ck("同类合并正确(男性别3句同号)", labels and len({labels[0], labels[2], labels[4]}) == 1)
    ck("同类合并正确(女性别3句同号)", labels and len({labels[1], labels[3], labels[5]}) == 1)
    ck("男女不同号", labels and labels[0] != labels[1])
    ck("编号从 1 起", labels and min(labels) >= 1)
    ck("首现顺序=1,2,1,2", labels == [1, 2, 1, 2, 1, 2])

    # 单人全同一类
    spans2 = [(spans[i][0], spans[i][1]) for i in (0, 2, 4)]
    media2 = os.path.join(tmp, "male_only.wav")
    buf2 = []
    for i, s in enumerate(spans2):
        buf2.extend([0.0] * (gap if i else 0))
        buf2.extend(make_male(1.4))
    write_wav(media2, buf2)
    sp = [(i * (1.8) + 0.0, i * 1.8 + 1.4) for i in range(3)]
    lab2 = diarize_tools.diarize_segments(media2, sp, log=log, max_speakers=4)
    print("单人 labels:", lab2)
    ck("单人只出 1 类", lab2 and len({x for x in lab2 if x}) == 1)

    # 句数太少不猜
    ck("2 句直接不标", diarize_tools.diarize_segments(media, spans[:2], log=log) is None)
    # 拿不到音频返回 None（不抛）
    ck("文件不存在不抛异常", diarize_tools.diarize_segments(
        os.path.join(tmp, "nope.wav"), spans, log=lambda *a, **k: None) is None)

    print()
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    print("FAILED:", ", ".join(n for n, o in checks if not o) or "none")
    print("tmp:", tmp)


if __name__ == "__main__":
    main()
