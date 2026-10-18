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
    print("@@@" + json.dumps(d, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="audio-separator 子进程入口（供主程序调用）")
    ap.add_argument("--probe", action="store_true", help="只报这个 python 看到的 torch/CUDA/包状态")
    ap.add_argument("--input", help="要分离的音频文件")
    ap.add_argument("--model", help="权重文件名（models-dir 里已有的 .ckpt）")
    ap.add_argument("--models-dir", default="", help="权重目录，避免包自己去下载")
    ap.add_argument("--output-dir", default="", help="成品目录")
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    ap.add_argument("--native-fp16", action="store_true")
    a = ap.parse_args()

    if a.probe:
        return probe()
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
