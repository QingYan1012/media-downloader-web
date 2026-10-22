# -*- coding: utf-8 -*-
"""转写档位闸门：CPU 上不许拿 float16 去建模型，也不许把「没跑成」报成「没装」。

起因（2026-10-22 实测）：用户把 faster-whisper 更到 1.2.1（ctranslate2 4.8.2）后，
设置里 whisper_device=auto、whisper_compute=float16，这台机器的 torch 是 +cpu 构建，
于是 ctranslate2 在**建模型那一步**就抛
`ValueError: Requested float16 compute type, but the target device or backend do not support
efficient float16 computation.`
—— 不是偷偷降级，是直接失败；失败之后界面看到的最后一句却是
「未找到 faster-whisper 或 Whisper 可执行文件。请 pip install faster-whisper」，
而 faster-whisper 明明装着。两句都不说实话。

这里不加载真模型：把 faster_whisper 桩掉，只问「最后递给 WhisperModel 的是哪一档」，
以及「哪句话该出现、哪句话不该出现」。
"""
import os
import sys
import tempfile
import types
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="md_wctest_state_")
os.environ["MEDIADOWNLOADER_STATE_DIR"] = STATE
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server as S  # noqa: E402

TOTAL = []
FAILED = []
CALLS = []


def ck(name, cond, detail=""):
    TOTAL.append(name)
    if not cond:
        FAILED.append(name + ("  [%s]" % detail if detail else ""))
    print(("PASS " if cond else "FAIL ") + name + ("  [%s]" % detail if detail and not cond else ""),
          flush=True)


class _Seg:
    def __init__(self, s, e, t):
        self.start, self.end, self.text = s, e, t


class _Info:
    language = "zh"


class FakeModel:
    def __init__(self, path, **kw):
        CALLS.append(dict(kw, path=str(path)))

    def transcribe(self, media, **kw):
        return [_Seg(0.2, 2.4, "第一句"), _Seg(2.6, 4.8, "第二句")], _Info()


class _TorchNoCuda:
    class cuda:
        @staticmethod
        def is_available():
            return False


def install_stubs():
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = FakeModel
    sys.modules["faster_whisper"] = fw
    sys.modules.setdefault("torch", _TorchNoCuda())


class Log:
    def __init__(self):
        self.rows = []

    def __call__(self, msg, level="info", **kw):
        self.rows.append((level, str(msg)))

    def text(self):
        return " || ".join(m for _, m in self.rows)

    def has(self, needle):
        return needle in self.text()


def run(device_pref, compute_pref, tmp):
    CALLS.clear()
    # 进程内那份模型缓存要一起清，否则第二开始根本不再建模型，
    # CALLS[-1] 读到的会是上一轮的档位 —— 那就成了假绿
    if hasattr(S, "_FW_MODEL_CACHE"):
        S._FW_MODEL_CACHE.clear()
    media = tmp / "clip.wav"
    media.write_bytes(b"RIFFfake")
    log = Log()
    out = S._whisper_via_faster(media, "transcribe", "zh", log,
                                model_size="tiny-stub", device_pref=device_pref,
                                compute_pref=compute_pref)
    assert CALLS, "这一发根本没建过模型，桩或缓存把测试骗了"
    return log, out


def main():
    install_stubs()
    tmp = Path(STATE) / "Downloads"
    tmp.mkdir(parents=True, exist_ok=True)

    # 1) 用户实际踩的那两条：CPU 与 auto（这台机器看不到 CUDA）+ float16
    for pref, label in (("cpu", "CPU"), ("auto", "auto（本机看不到 CUDA）")):
        log, out = run(pref, "float16", tmp)
        ctype = (CALLS[-1].get("compute_type") if CALLS else None)
        ck(f"W1 {label} + float16：递给 WhisperModel 的是 int8，不是 float16", ctype == "int8", str(ctype))
        ck(f"W2 {label} + float16：那句降级警告说出口，且带上原来那一档",
           "CPU 跑不动 float16" in log.text() and "int8" in log.text(), log.text()[:200])
    # int8_float16 同样含 fp16 权重，CPU 上一样跑不动
    log, out = run("cpu", "int8_float16", tmp)
    ck("W3 int8_float16 在 CPU 上也降到 int8（它含 fp16 权重，不是「int8 开头就安全」）",
       CALLS[-1].get("compute_type") == "int8" and "CPU 跑不动 int8_float16" in log.text(),
       str(CALLS[-1]))
    # 2) 不该多嘴的两条
    log, out = run("cpu", "int8", tmp)
    ck("W4 CPU + int8 原样不动，也不报那句警告（别把没坏的事说成修过）",
       CALLS[-1].get("compute_type") == "int8" and "CPU 跑不动" not in log.text(), log.text()[:200])
    log, out = run("cuda", "float16", tmp)
    ck("W5 真有 GPU 时 float16 保留：这一档是给人有卡的时候用的，不能一刀切",
       CALLS[-1].get("compute_type") == "float16" and CALLS[-1].get("device") == "cuda"
       and "CPU 跑不动" not in log.text(), str(CALLS[-1]) + " | " + log.text()[:160])
    # 3) 走完整条链：字幕真写出来了
    log, out = run("cpu", "float16", tmp)
    txt = Path(out).read_text(encoding="utf-8") if out else ""
    ck("W6 降完档这条链跑得完：SRT 有编号与时间轴，两句话都在",
       bool(out) and txt.lstrip().startswith("1") and txt.count("-->") == 2 and "第二句" in txt,
       txt[:120].replace("\n", " / "))
    # 4) 「没跑成」与「没装」是两句话
    SRC = (ROOT / "server.py").read_text(encoding="utf-8")
    i = SRC.index("装着但这一项没跑成")
    seg = SRC[i - 20:i + 170]
    ck("W7 装着但失败时那句不再喊 pip install faster-whisper（那是把人往错的方向支使）",
       "pip install" not in seg and "原因见上面那行" in seg and "可执行文件可退" in seg, seg)
    ck("W8 真没装时那句照旧给安装指引，两条分支各说各的",
       "未找到 faster-whisper 或 Whisper 可执行文件" in SRC and "find_spec(\"faster_whisper\")" in SRC)
    ck("W9 降级那两行不挂消息键：这一式是函数参数里的裸 log，闸门扫不到，挂了就成孤儿键",
       'k="srv.ai.whisper_cpu_compute"' not in SRC)
    i18n = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
    ck("W10 词表里也没有为它凭空多出的句子（K6 不许没人用的键）",
       "whisper_cpu_compute" not in i18n)

    print(f"\n== 汇总 ==\n共 {len(TOTAL)} 条，失败 {len(FAILED)} 条")
    for f in FAILED:
        print("FAIL " + f)
    import shutil
    shutil.rmtree(STATE, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
