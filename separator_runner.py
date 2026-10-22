# -*- coding: utf-8 -*-
"""人声分离（RoFormer）的子进程入口。由主程序用 tools/separator/venv 里的 python 调起来。

为什么不直接用装好的 audio-separator.exe：
1) 它没有 CPU 开关。0.47.0 的 argparse 表里一个 --force_cpu / --use_cuda 都没有，
   Separator.__init__ 也没有 device 参数 —— 设备只由 separator.py 里 setup_torch_device()
   那一句 `if torch.cuda.is_available():` 决定。
2) 而本机实测：CUDA_VISIBLE_DEVICES="" 藏不住 GPU（is_available 仍 True、device_count 0、
   torch.zeros(4).cuda() 照样落 cuda:0）；设成 -1 或 void 直接把解释器打崩
   （rc 3221225477）。所以「只用 CPU」这一档没法靠环境变量做出来。
   这里在 import 之前把那个判断函数换成 False，改的是包自己据以选设备的那个判断，
   换完它会自己打「No hardware acceleration could be configured, running in CPU mode」
   并把 torch_device 定成 cpu —— 成立与否以它这句话为准，不是以我这边的转述为准。
3) CLI 只把成品文件名打在日志里，我们要的是确切路径。这里把结果按 JSON 打在一行里回给主程序。

--probe 是给 /api/ai/voice_status 用的：主程序的 torch 是 +cpu 的构建，问它「有没有 GPU」
永远得到「没有」，那是这台机器的第二个 python 的事，只能让 venv 自己报。
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def probe() -> int:
    d = {"python": sys.version.split()[0]}
    try:
        import torch
        d["torch"] = torch.__version__
        d["cuda_build"] = torch.version.cuda
        d["cuda_available"] = bool(torch.cuda.is_available())
        d["device_count"] = torch.cuda.device_count()
        if d["cuda_available"]:
            p = torch.cuda.get_device_properties(0)
            d["gpu_name"] = torch.cuda.get_device_name(0)
            d["vram_gib"] = round(p.total_memory / 2**30, 1)
    except Exception as e:  # noqa: BLE001 报不出来的原因本身就是状态
        d["torch_error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
    for mod in ("audio_separator", "demucs"):
        try:
            __import__(mod)
            d[mod + "_import"] = "ok"
        except Exception as e:  # noqa: BLE001
            d[mod + "_import"] = "%s: %s" % (type(e).__name__, str(e)[:120])
    try:
        from importlib import metadata
        for dist, key in (("audio-separator", "audio_separator_version"),
                          ("demucs", "demucs_version")):
            try:
                d[key] = metadata.version(dist)
            except Exception:  # noqa: BLE001 包没装就没有版本，由 import 状态说明缺哪层
                pass
    except Exception:  # noqa: BLE001
        pass
    print("@@@" + json.dumps(d, ensure_ascii=False))
    return 0


def analyze(path: str, device: str, models_dir: str) -> int:
    """拍点 / 降拍（beat-this）+ 段落结构（all-in-one），一行 @@@JSON 回给主程序。

    两件事分开容错：一个包坏了或模型没下，只缺它那一项，不连带把另一项也报成没有。
    超参与镜像文件的规矩都取自 voice_tools 里钉死的那份 —— 这里再抄一遍就会和补齐时核对的不是同一份。
    """
    out = {"ok": False, "path": path, "device": "", "bpm": None, "beats": [], "downbeats": [],
           "beat_source": "", "segments": [], "bpm_allin1": None, "errors": []}
    try:
        import numpy as np
        import torch
    except Exception as e:
        out["errors"].append("torch: %s: %s" % (type(e).__name__, str(e)[:160]))
        print("@@@" + json.dumps(out, ensure_ascii=False))
        return 1
    if device == "cpu":
        torch.cuda.is_available = lambda: False
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    out["device"] = dev
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import voice_tools as VT
    except Exception:
        VT = None

    # ---- 解码一次，两边共用：soundfile 在这台机器上不需要 torchcodec，mp3 也解得开 ----
    y = None
    sr = 0
    try:
        import soundfile as sf
        y, sr = sf.read(path)
        if getattr(y, "ndim", 1) > 1:
            y = y.mean(axis=1)
        y = np.asarray(y, dtype="float32")
    except Exception as e:
        out["errors"].append("decode: %s: %s" % (type(e).__name__, str(e)[:180]))

    # ---- 拍点：镜像那份是裸 state_dict，装不进作者那句 load_model()，只能自己按钉死的超参构造 ----
    try:
        from safetensors.torch import load_file
        from beat_this.model.beat_tracker import BeatThis
        from beat_this.inference import Audio2Beats
        ck = os.path.join(models_dir or "", "beat_this", "beat_this-model.safetensors")
        if not os.path.isfile(ck):
            raise FileNotFoundError(ck)
        if y is None:
            raise RuntimeError("音频没解码成功，拍点没法跑")
        cfg = dict(VT.BEATTHIS_HPARAMS) if VT else json.load(open(ck + ".config.json", encoding="utf-8"))
        model = BeatThis(**cfg)
        model.load_state_dict(load_file(ck), strict=False)   # 缺的只有 init 算出来的 rotary 缓冲
        model.to(dev).eval()
        a2b = Audio2Beats(None, device=dev)
        a2b.model = model
        beats, downs = a2b(y, sr)
        b = [round(float(x), 3) for x in np.asarray(beats, dtype=float).reshape(-1)]
        d = [round(float(x), 3) for x in np.asarray(downs, dtype=float).reshape(-1)]
        out["beats"], out["downbeats"] = b, d
        if len(b) > 1:
            out["bpm"] = round(float(60.0 / np.median(np.diff(b))), 1)
        out["beat_source"] = "beat_this"
    except Exception as e:
        out["errors"].append("beat_this: %s: %s" % (type(e).__name__, str(e)[:180]))

    # ---- 段落结构：all-in-one 自己去 HF 取那 8 个 fold（补齐时已经按 commit 号下过）----
    try:
        import shutil
        import tempfile
        import allin1_infer as A
        if y is None:
            raise RuntimeError("音频没解码成功，结构分析没法跑")
        # 它读 mp3 走 torchaudio，而这份 torchaudio（2.11）自己不带解码器、要额外的 torchcodec；
        # wav/flac 那条路它用的是 soundfile，和上面解出来的就是同一份数据，所以这里递一份临时 wav，
        # 不为一个解码器再拖一层依赖。临时目录也接住它的 demix/spec 副产品 —— 那两个默认写在
        # 当前目录下，会把文件拉进程序自己的目录里。
        tmp = tempfile.mkdtemp(prefix="a1_")
        try:
            wav = os.path.join(tmp, "in.wav")
            sf.write(wav, np.asarray(y, dtype="float32"), sr, subtype="PCM_16")
            r = A.analyze(wav, device=dev, out_dir=None, demix_dir=os.path.join(tmp, "demix"),
                          spec_dir=os.path.join(tmp, "spec"), keep_byproducts=False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        d = r if isinstance(r, dict) else getattr(r, "__dict__", {})
        segs = d.get("segments") or []
        out["segments"] = [{"start": round(float(s.start), 2), "end": round(float(s.end), 2),
                            "label": str(s.label)} for s in segs]
        if d.get("bpm"):
            out["bpm_allin1"] = round(float(d["bpm"]), 1)
    except Exception as e:
        out["errors"].append("allin1: %s: %s" % (type(e).__name__, str(e)[:180]))

    out["ok"] = bool(out["beats"] or out["segments"])
    print("@@@" + json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="audio-separator 子进程入口（供主程序调用）")
    ap.add_argument("--probe", action="store_true", help="只报这个 python 看到的 torch/CUDA/包状态")
    ap.add_argument("--input", help="要分离的音频文件")
    ap.add_argument("--model", help="权重文件名（models-dir 里已有的 .ckpt）")
    ap.add_argument("--models-dir", default="", help="权重目录，避免包自己去下载")
    ap.add_argument("--output-dir", default="", help="成品目录")
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    ap.add_argument("--native-fp16", action="store_true")
    ap.add_argument("--analyze", help="只分析不分离：给音频路径，回一行 @@@JSON（拍点 + 段落结构）")
    a = ap.parse_args()

    if a.probe:
        return probe()
    if a.analyze:
        return analyze(a.analyze, a.device, a.models_dir)
    missing = [k for k in ("input", "model") if not getattr(a, k)]
    if missing:
        print("缺少参数：%s" % ", ".join("--" + m for m in missing), file=sys.stderr)
        return 2

    import torch
    if a.device == "cpu":
        # 必须在 import audio_separator 之前换：setup_torch_device 拿的就是这个函数
        torch.cuda.is_available = lambda: False
    from audio_separator.separator import Separator

    out_dir = a.output_dir or os.path.dirname(os.path.abspath(a.input))
    os.makedirs(out_dir, exist_ok=True)
    kwargs = {"output_dir": out_dir, "output_format": "FLAC",
              "use_native_fp16": bool(a.native_fp16)}
    # 空串/None 都别传：__init__ 的默认值是 "/tmp/audio-separator-models/"，
    # 传个空的进去等于告诉它「权重在这个没有名字的目录里」，找不到就自己开下载。
    if a.models_dir:
        kwargs["model_file_dir"] = a.models_dir
    sep = Separator(**kwargs)
    sep.load_model(model_filename=a.model)
    files = sep.separate(a.input) or []
    want = {"cpu": "cpu", "cuda": "cuda"}.get(a.device)
    got = str(getattr(sep, "torch_device", "未知"))
    # separate() 回的是裸文件名（实测 'src_(Vocals)_model_bs_roformer_ep_317_sdr_12.flac'），
    # 既不是绝对路径也没说相对谁 —— 主程序拿这个字符串去找文件就会「分离成功、文件不可用」。
    # 所以这里按「output_dir → 当前目录」两处各认一次，认到了才发绝对路径。
    resolved = []
    for f in files:
        p = str(f)
        if os.path.isabs(p):
            resolved.append(p)
            continue
        for cand in (os.path.join(out_dir, p), os.path.abspath(p)):
            if os.path.isfile(cand):
                resolved.append(cand)
                break
        else:
            resolved.append(os.path.join(out_dir, p))
    print("@@@" + json.dumps({
        "requested_device": a.device,
        "actual_device": got,
        # 包自己说 cpu，我们才敢写「按你要的跑了」；要 GPU 却拿到 cpu 是降级，得让调用方看见
        "device_matched": (want is None or got.startswith(want)),
        "outputs": resolved,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
