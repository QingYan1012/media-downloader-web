"""
语音增强工具（参考 voice-pro 能力，可选依赖）:
  - Demucs 人声/伴奏分离
  - Edge-TTS 字幕配音
  - deep-translator 免费机翻兜底
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Tuple

LogFn = Callable[..., None]


def _log(log: LogFn, msg: str, level: str = "info"):
    try:
        log(msg, level)
    except TypeError:
        log(msg)


# ── Demucs ──────────────────────────────────────────────

def install_demucs(log: LogFn = print, mirror: str = "") -> str:
    """把 demucs 装进分离专用的 venv（#78 方案二）。

    不再往主环境装：主程序的 torch 是 +cpu 构建，装进去的 demucs 永远跑不了 GPU，
    而分离命令又固定从 venv 起 —— 装在别处的 demucs 程序根本用不到，
    那种「装好了」是假消息。venv 不在就说清缺哪一层，不悄悄退回主环境。
    """
    py = separator_python()
    if not py:
        msg = "没有 tools/separator/venv，装不了分离用的 demucs（要先建这个环境）"
        _log(log, msg, "error")
        return f"failed: {msg}"
    cmd = [py, "-m", "pip", "install", "-U", "--disable-pip-version-check",
           "--no-input", "--no-warn-script-location", "demucs==4.1.0"]
    if mirror:
        cmd += ["-i", mirror]
    _log(log, "在分离环境里安装 demucs …")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if r.returncode != 0:
        return "failed: " + ((r.stderr or r.stdout or "").strip()[-300:])
    separation_probe(refresh=True)
    return "ok"


# ── 人声分离：两套引擎共用同一个 venv（#78 方案二）────────────
#
# 为什么要单独一个 venv：主程序的 torch 是 +cpu 构建（本机实测 cuda_build=None），
# 在它里面装 audio-separator 只会在「分离人声」这一项上继续跑 CPU。
# 方案二把 demucs 也装进 tools/separator/venv，两个引擎都从这一个 python 起，
# 所以「选 GPU」对两边都是真能选，而不是 RoFormer 能选、Demucs 那格是灰的。
# 实测（2026-10-18，同一条 3 秒合成音频）：venv 里 torch 2.14.1+cu130、
# CUDA 可用、RTX 4060 Laptop 8.0 GiB；demucs -d cuda 7.39 秒/秒音频，-d cpu 2.09 秒/秒。

SEP_APP_ROOT = Path(__file__).resolve().parent
SEP_VENV_PY = SEP_APP_ROOT / "tools" / "separator" / "venv" / "Scripts" / "python.exe"
SEP_MODELS_DIR = SEP_APP_ROOT / "tools" / "separator" / "models"
SEP_RUNNER = SEP_APP_ROOT / "separator_runner.py"

# 权重表只列官方 roformer_download_list 里真能下载、且随项目预载的那四条。
# id 是给界面当词表键用的（文案在 i18n.js，后端不拼中文），file/yaml 是磁盘上的真名字。
# 包里 models.json 另外那 84 个社区模型名字只是「识别名录」，没有可达的下载源，不能当选项给出去。
ROFORMER_MODELS = [
    {"id": "bs_1297", "family": "bs_roformer",
     "file": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
     "yaml": "model_bs_roformer_ep_317_sdr_12.9755.yaml",
     "file_sha256": "5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa",
     "yaml_sha256": "2bfdd16c656bd9519aba757cc4f8834b7ede675eb1e00ec4772d74ae1c41af7f"},
    {"id": "bs_1296", "family": "bs_roformer",
     "file": "model_bs_roformer_ep_368_sdr_12.9628.ckpt",
     "yaml": "model_bs_roformer_ep_368_sdr_12.9628.yaml",
     "file_sha256": "f6c94864adfb73bbb0ca58ec14d58dd0b364549e9fb61433ae51916f3e2f8d0b",
     "yaml_sha256": "aea599b3f9bd4892a9c6bf5ac7c44787d3c99f717903d16054702665d477c86b"},
    {"id": "mel_1143", "family": "mel_band_roformer",
     "file": "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
     "yaml": "model_mel_band_roformer_ep_3005_sdr_11.4360.yaml",
     "file_sha256": "21b9d0958e35b8ebfbe2afe69bbd5444e5ffe2f5d80ae0d583b833d2f3c0d139",
     "yaml_sha256": "d9b083b48dfdd0bd10f8a29a9c18777b0419496d938827f48a1db31bf0193aa3"},
    {"id": "mel_inst_v2", "family": "mel_band_roformer",
     "file": "melband_roformer_inst_v2.ckpt",
     "yaml": "config_melbandroformer_inst_v2.yaml",
     "file_sha256": "bd19766620f7d6f58fdf7aaada7e89907fe41bc64490ce3faa9a6dab15d6e1f2",
     "yaml_sha256": "4b902a7360a930c178edb4846b30e4e326aa1219d1b2daf660d46a311e0cd50b"},
]

# 就列界面下拉里那几个：htdemucs 是默认，htdemucs_ft 是微调四轨，mdx_extra 是老 mdx 一路。
# htdemucs_6s 是六轨（多吉他与钢琴），参照 StemDeck（Apache-2.0）的选型加进来 ——
# 但它必须在本机真跑通下载与分离才配出现在下拉里，mdx23c 那类仍按老规矩先验后列。
DEMUCS_MODELS = ["htdemucs", "htdemucs_ft", "mdx_extra", "htdemucs_6s"]
# 分轨范围：vocal = 只取人声（--two-stems vocals，现有默认，出两条）；
# four / six = 去掉 --two-stems，让 demucs 把自己那套轨全铺开，档位与模型必须对得上，
# 否则用户选「六轨」拿到的是四条，或选「四轨」却下了一份六轨的权重。
DEMUCS_STEMS_MODES = ["vocal", "four", "six"]
DEMUCS_SIX_MODEL = "htdemucs_6s"
DEMUCS_STEMS_BY_MODEL = {DEMUCS_SIX_MODEL: 6, "htdemucs": 4, "htdemucs_ft": 4, "mdx_extra": 4}
SEPARATION_DEVICES = ["auto", "cpu", "cuda"]

_probe_cache: dict = {"at": 0.0, "data": None}
_probe_lock = threading.Lock()


def _subprocess_env() -> dict:
    import os
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    return env


def separator_python() -> str:
    """分离专用 python 的路径；没建 venv 就回空串（界面据此说「缺的是 venv 这一层」）。"""
    return str(SEP_VENV_PY) if SEP_VENV_PY.is_file() else ""


def roformer_model_states() -> List[dict]:
    """逐条报权重在不在，缺的话缺的是 ckpt 还是 yaml —— 这两件事的处置不一样：
    缺 ckpt 是「去下载权重」，缺 yaml 是「模型结构配置没跟着下来，包会自己去找并下载」。"""
    out = []
    for m in ROFORMER_MODELS:
        ckpt = (SEP_MODELS_DIR / m["file"]).is_file()
        yaml_ = (SEP_MODELS_DIR / m["yaml"]).is_file()
        out.append({**m,
                    "ckpt_present": ckpt,
                    "yaml_present": yaml_,
                    "present": ckpt and yaml_,
                    "missing": "" if (ckpt and yaml_) else ("ckpt" if not ckpt else "yaml")})
    return out


def separation_probe(refresh: bool = False) -> dict:
    """问 venv 自己「你的 torch 看到 GPU 了吗」。

    必须在子进程里问：主程序的 torch 是 +cpu 的，问它永远得到「没有 GPU」，
    那会把一个能跑 GPU 的引擎说成不能。这一步一次要几秒（import torch），所以带缓存。
    """
    import time
    now = time.time()
    with _probe_lock:
        if not refresh and _probe_cache["data"] is not None and now - _probe_cache["at"] < 300:
            return dict(_probe_cache["data"])
        py = separator_python()
        data: dict = {"python_present": bool(py), "runner_present": SEP_RUNNER.is_file()}
        if not py or not SEP_RUNNER.is_file():
            data["reason"] = "venv" if not py else "runner"
        else:
            try:
                r = subprocess.run([py, str(SEP_RUNNER), "--probe"],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=180, env=_subprocess_env())
                line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
                if line:
                    data.update(json.loads(line[3:]))
                else:
                    data["probe_error"] = ((r.stderr or r.stdout or "").strip()[-300:]
                                           or "没回 @@@ 那行")
            except FileNotFoundError:
                data["probe_error"] = "找不到 venv python"
            except subprocess.TimeoutExpired:
                data["probe_error"] = "探测超时（180 秒）"
        _probe_cache["at"] = now
        _probe_cache["data"] = data
        return dict(data)


def _resolved_device(device: str, probe: dict) -> str:
    """auto 落到具体设备名，好让日志和界面说的是「实际用了什么」而不是「设置里写了什么」。"""
    if device == "cpu":
        return "cpu"
    if device == "cuda":
        return "cuda"
    return "cuda" if probe.get("cuda_available") else "cpu"


def separate_roformer(
    media_path: str,
    *,
    model_id: str = "",
    device: str = "auto",
    out_dir: str = "",
    native_fp16: bool = False,
    log: LogFn = print,
) -> dict:
    """用 venv 里的 audio-separator 跑 RoFormer。返回 {outputs, actual_device, ...}。

    失败原因分成「哪一层缺」而不是笼统一句「不可用」：venv 没建、权重没下、
    包 import 不动，三者在界面上是三句不同的话，处置也不同。
    """
    src = Path(media_path)
    if not src.is_file():
        raise FileNotFoundError(str(src))
    py = separator_python()
    if not py:
        raise RuntimeError("分离引擎的独立环境还没建（tools/separator/venv 里没有 python）")
    if not SEP_RUNNER.is_file():
        raise RuntimeError("找不到 separator_runner.py，无法用独立环境跑分离")
    chosen = next((m for m in ROFORMER_MODELS if m["id"] == model_id), ROFORMER_MODELS[0])
    state = {m["id"]: m for m in roformer_model_states()}[chosen["id"]]
    if not state["present"]:
        raise RuntimeError("权重不全（缺 %s）：%s" % (state["missing"], chosen["file"]))
    dest = Path(out_dir) if out_dir else src.parent / "separated"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [py, str(SEP_RUNNER), "--input", str(src), "--model", chosen["file"],
           "--models-dir", str(SEP_MODELS_DIR), "--output-dir", str(dest),
           "--device", device if device in SEPARATION_DEVICES else "auto"]
    if native_fp16:
        cmd.append("--native-fp16")
    _log(log, f"RoFormer 开始: {chosen['file']} / {device}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=7200, env=_subprocess_env())
    line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
    if r.returncode != 0 or not line:
        tail = ((r.stderr or "") + (r.stdout or "")).strip()[-800:]
        raise RuntimeError(f"RoFormer 失败: {tail}")
    fact = json.loads(line[3:])
    missing = [p for p in fact.get("outputs", []) if not Path(p).is_file()]
    if missing:
        # 包说成功了、文件却不在：这是最不该含糊的一种「成功」，宁可报错也别回空
        raise RuntimeError("RoFormer 报成功但成品不在: %s" % ", ".join(missing[:2]))
    _log(log, f"RoFormer 完成: 实际设备 {fact.get('actual_device')}，{len(fact.get('outputs', []))} 个成品")
    return fact


def separate_demucs(
    media_path: str,
    *,
    model: str = "htdemucs",
    device: str = "auto",
    out_dir: str = "",
    log: LogFn = print,
    stems_mode: str = "vocal",
) -> dict:
    """用 venv 里的 demucs 分离；设备三档靠它自己的 -d（实测 cpu/cuda 两档吞吐差 3.5 倍）。

    stems_mode 只决定要不要带 --two-stems：vocal 沿用现有那条命令（人声 + 伴奏两条），
    four / six 让 demucs 铺开自己全部的轨。档与模型不匹配直接抛，不让它跑完才发现轨数不对。
    """
    py = separator_python()
    if not py:
        raise RuntimeError("分离引擎的独立环境还没建（tools/separator/venv 里没有 python）")
    probe = separation_probe()
    if probe.get("demucs_import", "") != "ok":
        raise RuntimeError("这个环境里的 demucs 起不来：%s" % probe.get("demucs_import", "没探到"))
    want = _resolved_device(device, probe)
    if device == "cuda" and not probe.get("cuda_available"):
        raise RuntimeError("这个环境看不到 CUDA（torch 报 cuda_available=False），选不了 GPU")
    mode = (stems_mode or "vocal").strip().lower()
    if mode not in DEMUCS_STEMS_MODES:
        raise RuntimeError("分轨范围只认 %s，收到的是 %s" % (" / ".join(DEMUCS_STEMS_MODES), stems_mode))
    mdl = (model or "htdemucs").strip()
    cap = DEMUCS_STEMS_BY_MODEL.get(mdl)
    if cap is None:
        raise RuntimeError("Demucs 模型只认 %s，收到的是 %s" % (" / ".join(DEMUCS_MODELS), model))
    if mode == "six" and cap < 6:
        raise RuntimeError("六轨只有 %s 出得来，当前模型 %s 是 %d 轨" % (DEMUCS_SIX_MODEL, mdl, cap))
    if mode == "four" and cap != 4:
        raise RuntimeError("%s 出的是 %d 轨，配不上「四轨」这一档" % (mdl, cap))
    dest = Path(out_dir) if out_dir else Path(media_path).parent / "demucs"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [py, "-m", "demucs"]
    if mode == "vocal":
        cmd += ["--two-stems", "vocals"]
    cmd += ["-n", mdl, "-d", want, "-o", str(dest), str(media_path)]
    _log(log, f"Demucs 开始: {mdl} / {want} / {mode}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=7200, env=_subprocess_env())
    if r.returncode != 0:
        raise RuntimeError(f"Demucs 失败: {((r.stderr or '') + (r.stdout or '')).strip()[-800:]}")
    track = Path(media_path).stem
    found: dict = {}
    for wav in dest.rglob("*.wav"):
        if wav.parent.name.lower() == track.lower():
            found[wav.stem] = str(wav)
    if not found:
        raise RuntimeError("Demucs 跑完了但没找到成品（期望 %s/vocals.wav）" % track)
    _log(log, f"Demucs 完成: 实际设备 {want}，{len(found)} 条轨")
    return {"outputs": sorted(found.values()), "actual_device": want,
            "stems": found, "device_matched": True, "stems_mode": mode, "model": mdl}


# ── 独立环境的搭建与权重预载 ────────────────────────────
#
# 便携包里既不带 venv 也不带权重（口径定的），所以在别人的机器上这两层要靠程序自己补。
# 没有这一步，界面上那三个下拉就是三块永远点不动的灰：能说出「缺哪一层」却给不出补法，
# 等于把功能做给了这台机器一个人。

SEP_VENV_DIR = SEP_VENV_PY.parents[1]
# 钉死版本：audio-separator 的模型表和设备判定每次小版本都在动，
# 装成「当时最新的」会让这台机器验过的选项在下一次装机的机器上变成没验过的。
SEP_ENGINE_PINS = ["audio-separator==0.47.0", "demucs==4.1.0"]
SEP_ENGINE_PKGS = ("audio-separator", "demucs")
# 更新检查只读包的元数据，不 import torch：main 环境里那次 import 要几秒，
# 组件页每次加载都做一遍会把「查一眼有没有新版」变成卡顿。
_engine_ver_cache: dict = {"at": 0.0, "data": {}}
# ckpt 在 TRvlvr 的 release 里，yaml 在 audio-separator 自己的 model-configs release 里。
# 逐条 HEAD 过：官方那批 RoFormer 的 yaml 在主基址（.../mdx_model_data/mdx_c_configs）全是 404，
# 只有备用基址能取到，所以这里写死备用那一个。
SEP_CKPT_BASE = "https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models"
SEP_YAML_BASE = ("https://github.com/nomadkaraoke/python-audio-separator"
                 "/releases/download/model-configs")
_setup_lock = threading.Lock()


def separator_setup_running() -> bool:
    """搭建任务此刻在不在跑。界面那枚转圈只跟着这个真实读数，不跟着前端猜的秒数。"""
    return _setup_lock.locked()


def _pip_in_venv(args: List[str], log: LogFn, timeout: int = 3600) -> Tuple[bool, str]:
    r = subprocess.run([str(SEP_VENV_PY), "-m", "pip", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=_subprocess_env())
    tail = ((r.stderr or "") + (r.stdout or "")).strip()[-400:]
    return r.returncode == 0, tail


def separator_engine_versions(refresh: bool = False) -> dict:
    """只问 venv 的包元数据，拿两个引擎装在什么版本。

    组件页要拿它和上游最新版比，这一步不能 import torch（要几秒），
    所以单独起一次 importlib.metadata，结果缓存两分钟。"""
    import time
    py = separator_python()
    if not py:
        return {}
    now = time.time()
    if not refresh and _engine_ver_cache["data"] and now - _engine_ver_cache["at"] < 120:
        return dict(_engine_ver_cache["data"])
    code = ("import importlib.metadata as m, json\n"
            "out = {}\n"
            f"for p in {list(SEP_ENGINE_PKGS)!r}:\n"
            "    try:\n"
            "        out[p] = m.version(p)\n"
            "    except Exception:\n"
            "        pass\n"
            "print('@@@' + json.dumps(out))")
    data: dict = {}
    try:
        r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30,
                           env=_subprocess_env())
        line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
        if line:
            got = json.loads(line[3:])
            if isinstance(got, dict):
                data = {k: str(v) for k, v in got.items() if v}
    except Exception:
        data = {}
    _engine_ver_cache.update(at=now, data=data)
    return dict(data)


def ensure_separator_venv(log: LogFn = print, mirror: str = "") -> str:
    """建 tools/separator/venv 并装进两个引擎。用主程序的 python 起 venv，
    所以出来的 torch 是 PyPI 默认那份（本机实测 2.14.1+cu130），GPU 才有的选。"""
    if separator_python():
        _log(log, "分离环境已经在，跳过创建")
        return "ok"
    _log(log, f"创建分离环境：{SEP_VENV_DIR}")
    r = subprocess.run([sys.executable, "-m", "venv", str(SEP_VENV_DIR)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900, env=_subprocess_env())
    if r.returncode != 0 or not SEP_VENV_PY.is_file():
        msg = "建 venv 失败：" + (((r.stderr or "") + (r.stdout or "")).strip()[-300:] or "没生出 python.exe")
        _log(log, msg, "error")
        return f"failed: {msg}"
    idx = ["-i", mirror] if mirror else []
    _pip_in_venv(["install", "-U", "--disable-pip-version-check", *idx, "pip"], log, 600)
    _log(log, "在分离环境里装 " + " ".join(SEP_ENGINE_PINS) + "（torch 那一层有两个多 GB，要等一会）")
    ok, tail = _pip_in_venv(["install", "-U", "--disable-pip-version-check", "--no-input",
                             *idx, *SEP_ENGINE_PINS], log)
    if not ok:
        msg = "引擎装不上：" + tail
        _log(log, msg, "error")
        return f"failed: {msg}"
    separation_probe(refresh=True)
    return "ok"


def update_separator_engines(log: LogFn = print, mirror: str = "") -> str:
    """把 venv 里的两个引擎升到上游最新版（用户点「更新」才走这里）。

    SEP_ENGINE_PINS 只钉「新建环境时装什么」，不负责拦更新：
    不升级依赖大版本，torch 只在引擎的新依赖强制要求时才会被 pip 动。
    成功与失败都回读一次真实版本，界面不信这一次命令的退出码说话。"""
    if not _setup_lock.acquire(blocking=False):
        return "busy"
    try:
        if not separator_python():
            return "failed: 分离环境还没建，先用「获取 / 补齐」把环境装上"
        idx = ["-i", mirror] if mirror else []
        _log(log, "在分离环境里更新 " + " / ".join(SEP_ENGINE_PKGS) + " …")
        ok, tail = _pip_in_venv(["install", "-U", "--disable-pip-version-check",
                                 "--no-input", *idx, *SEP_ENGINE_PKGS], log)
        separator_engine_versions(refresh=True)
        separation_probe(refresh=True)
        if not ok:
            msg = "引擎更新失败：" + tail
            _log(log, msg, "error")
            return f"failed: {msg}"
        _log(log, "分离引擎已更新：" + " / ".join(
            f"{k} {v}" for k, v in separator_engine_versions().items()))
        return "ok"
    finally:
        _setup_lock.release()


def _finish_weight(part: Path, dest: Path, log: LogFn, expect_sha: str) -> bool:
    """核完校验值才把 .part 换成真名字。
    钉的是「下载过程中被截断、被中间设备改写、镜像给错了文件」这三种，
    值本身是本机下回来的字节算出来的（两条独立下载路径算出同一份），
    所以它证明的是一致性，不是上游作者的真伪 —— 那句「已就绪」也只说到这儿。
    比对按「给多长核多长」：RoFormer 那批给的是整份 sha256，Demucs 那边文件名里只有 8 位前缀
    （torch.hub 与 demucs 自己也只按这个前缀核），写死等长就没法用同一套下载。"""
    if expect_sha:
        h = hashlib.sha256()
        with open(part, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest()[:len(expect_sha)] != expect_sha:
            part.unlink(missing_ok=True)
            _log(log, f"{dest.name} 校验值对不上（{h.hexdigest()[:12]}…），这份丢掉不用", "error")
            return False
    os.replace(part, dest)
    _log(log, f"权重到位：{dest.name}（{dest.stat().st_size >> 20} MB）")
    return True


def _fetch_weight(url: str, dest: Path, log: LogFn, expect_sha: str = "") -> bool:
    """下一个权重。先写 .part 再改名：roformer_model_states 只认文件名在不在，
    半截文件直接落在真名字上会把「没下完」报成「已就绪」，那是更坏的一种谎。
    断点续传是必需的而不是讲究 —— 961 MB 那条实测断过三轮。"""
    import requests
    from pkg_update import github_url_candidates

    part = dest.with_name(dest.name + ".part")
    # 镜像前缀只对 GitHub 那两个 release 地址有意义；Demucs 的模型在 facebook 自己的站上，
    # 给它拼镜像前缀只会得到一串必然 404 的候选，白绕几圈。
    cands = github_url_candidates(url) if "github.com" in url else [url]
    for u in cands:
        for _round in range(4):
            have = part.stat().st_size if part.is_file() else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                with requests.get(u, stream=True, timeout=180, verify=False,
                                  headers=headers) as r:
                    if r.status_code == 416:
                        # 服务器说这个起点已经越界 = .part 本身就是全的
                        return _finish_weight(part, dest, log, expect_sha)
                    if r.status_code not in (200, 206):
                        raise OSError(f"HTTP {r.status_code}")
                    # 206 才是真接住了 Range；服务器回 200 表示它不理会续传，那就从头重写
                    mode = "ab" if r.status_code == 206 else "wb"
                    with open(part, mode) as f:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            if chunk:
                                f.write(chunk)
                    cl = int(r.headers.get("Content-Length") or 0)
                    want_size = have + cl if r.status_code == 206 and cl else cl
                    got_size = part.stat().st_size
                    if want_size and got_size != want_size:
                        # 连接被掐断时 requests 只会正常结束循环，不抛异常；
                        # 不比对字节数的话，半截 ckpt 会被当成「已就绪」放进选项里。
                        raise OSError(f"字节数对不上：{got_size} != {want_size}")
                return _finish_weight(part, dest, log, expect_sha)
            except Exception as e:
                done_mb = (part.stat().st_size >> 20) if part.is_file() else 0
                _log(log, f"{dest.name} 这一轮没下完（已存 {done_mb} MB）：{str(e)[:120]}", "warning")
    return False


def download_roformer_weights(log: LogFn = print) -> dict:
    """把缺的 ckpt / yaml 补齐。回 {ok:[ids], failed:[ids]}，界面按这两个列表说话，
    不在这里塞中文，也不在这里假装「都好了」。"""
    done: List[str] = []
    failed: List[str] = []
    for m in roformer_model_states():
        if m["present"]:
            done.append(m["id"])
            continue
        want = ([("file", m["file"], SEP_CKPT_BASE, m.get("file_sha256", ""))
                 if not m["ckpt_present"] else []])
        if not m["yaml_present"]:
            want.append(("yaml", m["yaml"], SEP_YAML_BASE, m.get("yaml_sha256", "")))
        ok = True
        for _kind, fname, base, sha in want:
            _log(log, f"下载权重 {fname} …")
            ok = _fetch_weight(f"{base}/{fname}", SEP_MODELS_DIR / fname, log, sha) and ok
        (done if ok else failed).append(m["id"])
    return {"ok": done, "failed": failed}


# ---- Demucs 的模型：名单、地址、校验值全在装好的那个包里，这里只读不抄 ----
# 抄一份就会漂移：包里换了一个签名，界面还在报「有 / 缺」，实际载入的却是另一个文件。
DEMUCS_ROOT_URL = "https://dl.fbaipublicfiles.com/demucs/"
DEMUCS_FILE_RE = re.compile(r"^([0-9a-f]{8})-([0-9a-f]{8})\.th$")


def demucs_ckpt_dir() -> Path:
    """demucs 取模型走 torch.hub，所以文件落在它的缓存目录里，不在程序目录下。
    TORCH_HUB / TORCH_HOME 任一个都能改这个位置 —— 改过的机器上「缺不缺」要问对地方。"""
    hub = os.environ.get("TORCH_HUB")
    if hub:
        return Path(hub) / "checkpoints"
    root = os.environ.get("TORCH_HOME") or str(Path.home() / ".cache" / "torch")
    return Path(root) / "hub" / "checkpoints"


def demucs_remote_dir() -> Optional[Path]:
    """装好的 demucs 包里那个 remote/ 目录（files.txt 与各模型的 yaml 都在里面）。"""
    venv = SEP_VENV_PY.parents[1]
    for cand in [venv / "Lib" / "site-packages" / "demucs" / "remote"] + \
            sorted(venv.glob("lib*/site-packages/demucs/remote")):
        if (cand / "files.txt").is_file():
            return cand
    return None


def demucs_model_index() -> dict:
    """{模型名: [{sig, file, checksum, url}]}。
    files.txt 是「root: 子目录 + 一行一个文件名」，<模型>.yaml 的 models: [...] 给的是文件名
    前半那 8 位签名 —— 两张表拼起来才是完整地址；文件名后半那 8 位就是 sha256 前缀，
    torch.hub 与 demucs 载入时都按它核（check_hash=True），所以我们核的也是它，不多承诺一分。"""
    rd = demucs_remote_dir()
    if not rd:
        return {}
    by_sig: dict = {}
    root = ""
    try:
        listing = (rd / "files.txt").read_text(encoding="utf-8")
    except OSError:
        return {}
    for line in listing.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("root:"):
            root = s.split(":", 1)[1].strip()
            continue
        m = DEMUCS_FILE_RE.match(s)
        if m:
            by_sig[m.group(1)] = {"sig": m.group(1), "file": s, "checksum": m.group(2),
                                  "url": DEMUCS_ROOT_URL + root + s}
    out: dict = {}
    for name in DEMUCS_MODELS:
        y = rd / f"{name}.yaml"
        if not y.is_file():
            continue
        try:
            body = y.read_text(encoding="utf-8")
        except OSError:
            continue
        decl = next((l for l in body.splitlines() if l.strip().startswith("models:")), "")
        files = [by_sig[s] for s in re.findall(r"[0-9a-f]{8}", decl) if s in by_sig]
        if files:
            out[name] = files
    return out


def demucs_models_status() -> dict:
    """每个模型「几个文件在、缺哪几个」。模型没有独立版本号，所以这里能说的就是在不在 ——
    体积也不猜（没 HEAD 过就不知道远端多大），只报本机已在的字节数。"""
    idx = demucs_model_index()
    d = demucs_ckpt_dir()
    rows = []
    for name, files in idx.items():
        miss, size = [], 0
        for f in files:
            p = d / f["file"]
            if p.is_file():
                size += p.stat().st_size
            else:
                miss.append(f["file"])
        rows.append({"name": name, "files": len(files), "present": len(files) - len(miss),
                     "missing": miss, "bytes": size, "ready": not miss})
    return {"known": bool(idx), "dir": str(d), "models": rows,
            "ready": sum(1 for r in rows if r["ready"]), "total": len(rows),
            "missing_files": sum(len(r["missing"]) for r in rows)}


def download_demucs_models(log: LogFn = print) -> dict:
    """补齐缺的 Demucs 模型文件。名字必须和包里列的一致（前半签名就是它找文件的键），
    先写 .part 再按 sha256 前缀改名，和 RoFormer 那批同一套卫生。
    已经在的那些一个字节都不动 —— 这是「补齐」，不是「重下」。"""
    idx = demucs_model_index()
    done: List[str] = []
    failed: List[str] = []
    if not idx:
        _log(log, "看不到 demucs 包里的模型清单：分离环境还没建，建完再来补模型", "error")
        return {"ok": done, "failed": failed, "known": False}
    d = demucs_ckpt_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name, files in idx.items():
        ok = True
        for f in files:
            dest = d / f["file"]
            if dest.is_file():
                continue
            _log(log, f"下载 Demucs 模型 {f['file']}（{name}）…")
            ok = _fetch_weight(f["url"], dest, log, f["checksum"]) and ok
        (done if ok else failed).append(name)
    return {"ok": done, "failed": failed, "known": True}


# ---- 音频分析的第二批依赖：拍点与段落结构（选型参照 StemDeck，跑在同一个 venv 里）----
# 版本全部钉死，依据是这轮实测而不是「上游最新」：
#  · torchaudio 只到 2.11.0 —— PyPI 上没有配 torch 2.14 的那份。装它只为满足两个包的硬 import
#    （beat_this/preprocessing.py 与 allin1_infer/stems.py 都是 import 期就要），
#    它自己的 load() 在 2.7 之后要额外的 torchcodec，我们的调用路径不碰它。
#  · omegaconf 只能 2.3.1：hydra-core 1.3.7 要 omegaconf<2.4，而 2.3.1 自己钉死
#    antlr4-python3-runtime==4.9.*（2.4.0 换成要 4.13）。三者的交集只有这一组数，
#    钉错任何一项都会退化成「装上了但 import 不动」—— 实测是 Could not deserialize ATN。
SEP_ANALYSIS_PINS = [
    "all-in-one-infer==3.1.0", "beat-this==1.1.0",
    "torchaudio==2.11.0", "antlr4-python3-runtime==4.9.3",
    "hydra-core==1.3.7", "omegaconf==2.3.1", "matplotlib==3.11.2",
    "madmom-infer==0.2.0", "demucs-infer==4.4.0",
]
SEP_ANALYSIS_PKGS = ("all-in-one-infer", "beat-this")
# 结构模型：原作者的 HF 仓库里那 8 个 fold 检查点。钉的是逐个文件的 sha256，不是 commit 号 ——
# 因为库运行时那句 hf_hub_download(repo_id, filename) 不带 revision、只认默认分支，
# 按 commit 下的那份它根本不看（实测：8 个文件都在缓存里，仍报 LocalEntryNotFound）。
# commit 号留在注释里当出处；文件名带随机后缀，所以名字也必须一起钉。
ALLIN1_HF_REPO = "taejunkim/allinone"
ALLIN1_HF_REVISION = "379e5fd010b3fdd0ee8381ff8cbcfa51d70b5c19"
ALLIN1_HF_SIZE = 1400571   # 8 个各这么大（实测），合计 11.2 MB
ALLIN1_HF_FILES = [
    ("harmonix-fold0-0vra4ys2.pth", "0db596dfb0995f41d62f6267d76a9d54c046f1649bd35e1dbeca0c5f9a7b8acd"),
    ("harmonix-fold1-3ozjhtsj.pth", "607b4864eaabccd4f6951410d5ea6676666ad1cfa6ce2e18bc99f3824b77c3b7"),
    ("harmonix-fold2-gmgo0nsy.pth", "67c28ec7ca612d365e5fcb152f6530eb53e34c4303940afb30fd17a295c958a4"),
    ("harmonix-fold3-i92b7m8p.pth", "446d05672b2669cdb7d9b8bbbc228a4f3592484335a7995cca89a744e3950ddc"),
    ("harmonix-fold4-1bql5qo0.pth", "96327222ab9b33c005388b788ba602f529aa03cc4dde1c859c011f1004490493"),
    ("harmonix-fold5-x4z5zeef.pth", "c87f162a1090290bcbb863688746784919cf912c56744fb3d81a1a7dba3b114e"),
    ("harmonix-fold6-x7t226rq.pth", "13e7e639bf30fcd3fa049ad863088773a4e57b06d7c68581385b3ef625c60688"),
    ("harmonix-fold7-qwwskhg6.pth", "b888b7fba95efa3d5a37ca013fe7efe2741621ea9ca335e6b2723e4fd0fade57"),
]
# 拍点模型：作者那份 .ckpt 放在 cloud.cp.jku.at，本轮实测整站 503；
# HF 上只有第三方镜像（裸 state_dict + 它自己的 config.json，不是 Lightning 包）。
# 用镜像必须钉 sha256，而且界面/日志要写明「非作者发布」—— 这是来源没验到，不是内容没验到。
BEATTHIS_OFFICIAL_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt"
BEATTHIS_MIRROR_REPO = "safe-models/beat-this-final0"
BEATTHIS_MIRROR_FILE = "model.safetensors"
BEATTHIS_MIRROR_SHA256 = "f758c77ba5d862cad3718a95705964e9af55298b1fb3544c62c9d79184ea0f2e"
BEATTHIS_MIRROR_BYTES = 81029488
# 镜像的权重键是裸 state_dict，装不进作者那句 load_model()（它要 checkpoint["hyper_parameters"]），
# 所以超参也得钉住 —— 来源同样是第三方仓库里的 config.json。
BEATTHIS_HPARAMS = {"dropout": {"frontend": 0.1, "transformer": 0.2}, "ff_mult": 4,
                    "head_dim": 32, "n_layers": 6, "partial_transformers": True,
                    "spect_dim": 128, "stem_dim": 32, "sum_head": True, "transformer_dim": 512}
_analysis_probe_cache: dict = {"at": 0.0, "data": {}}


def analysis_model_dir() -> Path:
    """拍点模型落在这儿（和 RoFormer 权重同一目录，都在程序目录下，不进包）。"""
    return SEP_MODELS_DIR / "beat_this"


def _venv_code(probe: bool) -> str:
    """给 venv 里跑的那段：报两个包的版本 + 库自己能不能从缓存认出这 8 个 fold。
    必须在 venv 里问 —— 认缓存的是那份 huggingface_hub，换一份库就可能给出另一个答案。
    probe=False 时缺的就顺手取回来（不带 revision：带了运行时也不看，等于白钉）。"""
    names = [fn for fn, _ in ALLIN1_HF_FILES]
    head = ("import importlib.metadata as m, json\n"
            "out = {'pkgs': {}, 'hf': {}, 'error': ''}\n"
            f"for p in {list(SEP_ANALYSIS_PKGS)!r}:\n"
            "    try:\n"
            "        out['pkgs'][p] = m.version(p)\n"
            "    except Exception:\n"
            "        pass\n"
            f"from huggingface_hub import hf_hub_download as dl\n"
            f"repo = {ALLIN1_HF_REPO!r}\n"
            f"for fn in {names!r}:\n")
    if probe:
        head += ("    try:\n"
                 "        out['hf'][fn] = dl(repo_id=repo, filename=fn, local_files_only=True)\n"
                 "    except Exception:\n"
                 "        out['hf'][fn] = None\n")
    else:
        head += ("    try:\n"
                 "        try:\n"
                 "            out['hf'][fn] = dl(repo_id=repo, filename=fn, local_files_only=True)\n"
                 "        except Exception:\n"
                 "            out['hf'][fn] = dl(repo_id=repo, filename=fn)\n"
                 "    except Exception as e:\n"
                 "        out['hf'][fn] = None\n"
                 "        out['error'] = out['error'] + fn + ': ' + type(e).__name__ + ' ' + str(e)[:120] + '; '\n")
    return head + "print('@@@' + json.dumps(out))"


def _analysis_probe(refresh: bool = False) -> dict:
    """只读的那一发（不下载）。和引擎那批一样不 import torch，免得组件页卡住。"""
    import time
    py = separator_python()
    if not py:
        return {}
    now = time.time()
    if not refresh and _analysis_probe_cache["data"] and now - _analysis_probe_cache["at"] < 120:
        return dict(_analysis_probe_cache["data"])
    data: dict = {}
    try:
        r = subprocess.run([py, "-c", _venv_code(True)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=_subprocess_env())
        line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
        if line:
            got = json.loads(line[3:])
            if isinstance(got, dict):
                data = {"pkgs": {k: str(v) for k, v in (got.get("pkgs") or {}).items() if v},
                        "hf": got.get("hf") or {}, "error": str(got.get("error") or "")}
    except Exception:
        data = {}
    _analysis_probe_cache.update(at=now, data=data)
    return dict(data)


def _sha_ok(path_str: str, want: str) -> bool:
    """缓存里那个文件是不是我们钉死的那份内容。"""
    try:
        h = hashlib.sha256()
        with open(path_str, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == want
    except Exception:
        return False


def analysis_pkg_versions(refresh: bool = False) -> dict:
    """两个分析包的版本（venv 元数据，和缓存探测共用同一次子进程）。"""
    return dict((_analysis_probe(refresh) or {}).get("pkgs") or {})


def install_analysis_pkgs(log: LogFn = print, mirror: str = "") -> str:
    """把拍点/结构这两个包（连同钉死的依赖）装进分离环境。环境不在就先建环境 ——
    这两个包都要 torch，没有 torch 的 venv 装了也用不了。"""
    if not separator_python():
        got = ensure_separator_venv(log=log, mirror=mirror)
        if got != "ok":
            return got
    have = analysis_pkg_versions(refresh=True)
    want = [p for p in SEP_ANALYSIS_PINS if p.split("==")[0].replace("-", "_") not in have
            and p.split("==")[0] not in have]
    if not want:
        _log(log, "拍点与结构分析这两个包已经在，跳过安装")
        return "ok"
    args = ["install", "--no-warn-script-location", *want]
    if mirror:
        args += ["-i", mirror]
    _log(log, f"安装音频分析依赖（{len(want)} 项，含 torchaudio 与 matplotlib）…")
    ok, tail = _pip_in_venv(args, log, timeout=3600)
    if not ok:
        _log(log, f"音频分析依赖没装上：{tail[:200]}", "error")
        return "failed"
    _analysis_probe_cache.update(at=0.0, data={})
    _log(log, "音频分析依赖到位（all-in-one-infer / beat-this）")
    return "ok"


def analysis_model_states() -> list:
    """两个模型各在不在。判「在」的标准是库自己能不能认出这份文件：结构模型问的是 venv 里那份
    huggingface_hub（local_files_only），它认不出来就等于没有 —— 我们自己去翻缓存目录不算数。
    拍点模型走我们自己的目录 —— 因为它没有官方可达源，必须是我们钉死哈希的那一份。"""
    rows = []
    hf = (_analysis_probe() or {}).get("hf") or {}
    good = sum(1 for fn, sha in ALLIN1_HF_FILES if hf.get(fn) and _sha_ok(str(hf[fn]), sha))
    rows.append({"id": "allin1_structure", "present": good == len(ALLIN1_HF_FILES),
                 "files": good, "of": len(ALLIN1_HF_FILES),
                 "source": f"huggingface.co/{ALLIN1_HF_REPO}",
                 "verified": "sha256" if good else ""})
    ck = analysis_model_dir() / f"beat_this-{BEATTHIS_MIRROR_FILE}"
    rows.append({"id": "beat_this_final0", "present": ck.is_file(), "files": 1 if ck.is_file() else 0,
                 "of": 1, "source": (f"huggingface.co/{BEATTHIS_MIRROR_REPO}" if ck.is_file()
                                     else BEATTHIS_OFFICIAL_URL),
                 "verified": "sha256" if ck.is_file() else ""})
    return rows


def fetch_analysis_models_venv(log: LogFn = print) -> dict:
    """让 venv 按库自己的问法把那 8 个 fold 取回缓存（不带 revision：带了运行时也不看）。"""
    py = separator_python()
    if not py:
        return {"hf": {}, "error": "venv 不在"}
    try:
        r = subprocess.run([py, "-c", _venv_code(False)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800,
                           env=_subprocess_env())
        line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
        got = json.loads(line[3:]) if line else {}
        return {"hf": got.get("hf") or {}, "error": str(got.get("error") or "")}
    except Exception as e:
        return {"hf": {}, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def download_analysis_models(log: LogFn = print) -> dict:
    """补齐两个模型。拍点模型：先试作者的 .ckpt，503 就退回第三方镜像并核对钉死的 sha256，
    用了镜像就在日志里明写「非作者发布」；结构模型：让 venv 按库自己的问法取回那 8 个 fold，
    取回来还要逐个核 sha256 —— 上游换过文件就停在这儿，不拿没核过的权重接着跑。"""
    ok: List[str] = []
    failed: List[str] = []
    d = analysis_model_dir()
    d.mkdir(parents=True, exist_ok=True)
    ck = d / f"beat_this-{BEATTHIS_MIRROR_FILE}"
    if not ck.is_file():
        got_official = False
        _log(log, "下载拍点模型（作者源）…")
        try:
            with urllib.request.urlopen(BEATTHIS_OFFICIAL_URL, timeout=30) as r:
                got_official = bool(r.status and r.status < 400)
        except Exception as e:
            _log(log, f"作者源取不到（{type(e).__name__}: {str(e)[:90]}），改用第三方镜像", "warning")
        if not got_official:
            url = (f"https://huggingface.co/{BEATTHIS_MIRROR_REPO}/resolve/main/"
                   f"{BEATTHIS_MIRROR_FILE}")
            _log(log, f"从第三方镜像取：{BEATTHIS_MIRROR_REPO}（非作者发布）")
            if not _fetch_weight(url, ck, log, BEATTHIS_MIRROR_SHA256):
                failed.append("beat_this_final0")
            else:
                ok.append("beat_this_final0")
        else:
            # 作者源活着：按它自己的规矩下 .ckpt，库会自己核
            if _fetch_weight(BEATTHIS_OFFICIAL_URL, d / "beat_this-final0.ckpt", log, ""):
                ok.append("beat_this_final0")
            else:
                failed.append("beat_this_final0")
    else:
        ok.append("beat_this_final0")
    _log(log, f"补齐结构模型（{len(ALLIN1_HF_FILES)} 个 fold，合计约 "
              f"{len(ALLIN1_HF_FILES) * ALLIN1_HF_SIZE // 1024 // 1024} MB）…")
    got = fetch_analysis_models_venv(log)
    if got.get("error"):
        _log(log, f"结构模型有文件没取到：{str(got['error'])[:200]}", "error")
    _analysis_probe_cache.update(at=0.0, data={})   # 刚下完，缓存里那份「认不出来」要作废
    row = next((r for r in analysis_model_states() if r["id"] == "allin1_structure"), {})
    # 库认得、且内容对得上钉死的 sha256 才算补好 —— 上游换过文件时会停在这里，而不是拿新权重接着跑
    if row.get("present"):
        ok.append("allin1_structure")
    else:
        _log(log, f"结构模型只回读到 {row.get('files', 0)}/{len(ALLIN1_HF_FILES)} 个"
                  f"（认不出或哈希对不上，不拿没核过的权重跑）", "error")
        failed.append("allin1_structure")
    return {"ok": ok, "failed": failed}


def analysis_status() -> dict:
    """一屏说完：包装了没、模型在不在、缺的话该点哪个按钮。界面上那句「为什么没有拍点」只读这里。"""
    vers = analysis_pkg_versions()
    rows = analysis_model_states()
    return {"installed": all(p in vers for p in SEP_ANALYSIS_PKGS), "versions": vers,
            "models": rows, "models_ok": all(r["present"] for r in rows),
            "missing": [r["id"] for r in rows if not r["present"]],
            "model_dir": str(analysis_model_dir()),
            "setup_running": _setup_lock.locked()}


def analyze_beats_structure(media_path: str, device: str = "auto",
                            timeout: int = 1800, log: LogFn = print) -> dict:
    """在 venv 里跑拍点 + 段落结构，拿回那行 @@@JSON。

    必须在 venv 里跑：主程序那份 torch 是 +cpu 的、也没有 torchaudio，
    在这里 import beat_this 只会得到「缺依赖」，而不是结果。
    没装齐就直接回一句「没装」，不去起子进程 —— 让失败说清缺的是哪一层。
    """
    st = analysis_status()
    if not st["installed"]:
        return {"ok": False, "skipped": True, "reason": "packages",
                "error": "拍点与段落结构没装：在「设置 → 组件与依赖」点「音频分析依赖」装好，"
                         "再点「补齐模型」"}
    if not st["models_ok"]:
        return {"ok": False, "skipped": True, "reason": "models",
                "error": "分析模型还缺：%s，点「补齐模型」取回" % "、".join(st["missing"])}
    py = separator_python()
    if not py or not SEP_RUNNER.is_file():
        return {"ok": False, "skipped": True, "reason": "venv", "error": "分离环境不在"}
    cmd = [py, str(SEP_RUNNER), "--analyze", str(media_path),
           "--device", device if device in ("auto", "cpu", "cuda") else "auto",
           "--models-dir", str(SEP_MODELS_DIR)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=_subprocess_env())
    except subprocess.TimeoutExpired:
        _log(log, f"拍点/结构分析超过 {timeout} 秒没回，先按没算出来处理", "warning")
        return {"ok": False, "error": f"timeout {timeout}s"}
    line = next((ln for ln in (r.stdout or "").splitlines() if ln.startswith("@@@")), "")
    if not line:
        tail = ((r.stderr or "") + (r.stdout or "")).strip()[-240:]
        _log(log, f"拍点/结构分析没回数据：{tail}", "warning")
        return {"ok": False, "error": tail or f"exit {r.returncode}"}
    try:
        return json.loads(line[3:])
    except Exception as e:
        return {"ok": False, "error": f"回包不是合法 JSON: {e}"}


def setup_analysis(log: LogFn = print, *, step: str = "all", mirror: str = "") -> str:
    """一次点齐「装分析用的包 + 补两个模型」。锁和分离环境共用同一把 ——
    两个 pip 同时往同一个 venv 里写会互相盖掉对方刚落的文件，它们是不是同一类包不改变这件事。"""
    if not _setup_lock.acquire(blocking=False):
        return "busy"
    try:
        missing: List[str] = []
        if step in ("pkgs", "all"):
            if install_analysis_pkgs(log, mirror) != "ok":
                missing.append("packages")
        if step in ("models", "all"):
            missing += list((download_analysis_models(log) or {}).get("failed") or [])
        return "ok" if not missing else "failed:" + "、".join(missing)
    finally:
        _setup_lock.release()


def setup_separator(log: LogFn = print, *, step: str = "all", mirror: str = "") -> str:
    """一次点齐「建环境 + 补权重」，同一时刻只允许一个在跑：
    两个进程往同一个 venv 里 pip 会互相把对方刚写的文件盖掉。
    step="engines" 走引擎升级，不碰权重。"""
    if step == "engines":
        return update_separator_engines(log, mirror)
    if not _setup_lock.acquire(blocking=False):
        return "busy"
    try:
        SEP_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        if step in ("all", "venv"):
            r = ensure_separator_venv(log, mirror)
            if r != "ok" or step == "venv":
                return r
        if step in ("all", "weights"):
            got = download_roformer_weights(log)
            separation_probe(refresh=True)
            if got["failed"]:
                return "failed: 权重没下全 " + ", ".join(got["failed"])
        return "ok"
    finally:
        _setup_lock.release()




EDGE_VOICE_PRESETS = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-cn": "zh-CN-XiaoxiaoNeural",
    "zh-tw": "zh-TW-HsiaoChenNeural",
    "en": "en-US-JennyNeural",
    "en-us": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "yue": "zh-HK-HiuMaanNeural",
}


def edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        return bool(shutil.which("edge-tts"))


def srt_to_plain_text(srt_path: str) -> str:
    text = Path(srt_path).read_text(encoding="utf-8", errors="ignore")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.isdigit() or re.match(r"\d{2}:\d{2}:\d{2}", line):
            continue
        lines.append(line)
    return "\n".join(lines)


async def _edge_tts_save(text: str, voice: str, out_mp3: Path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_mp3))


def edge_tts_from_text(
    text: str,
    out_path: str,
    *,
    voice: str = "",
    lang: str = "zh",
    log: LogFn = print,
) -> str:
    if not text.strip():
        raise ValueError("文本为空")
    voice = voice or EDGE_VOICE_PRESETS.get((lang or "zh").lower(), "zh-CN-XiaoxiaoNeural")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _log(log, f"Edge-TTS: voice={voice} → {out.name}")

    try:
        import asyncio
        asyncio.run(_edge_tts_save(text, voice, out))
    except RuntimeError:
        # 已有事件循环
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_edge_tts_save(text, voice, out))
        finally:
            loop.close()
    except ImportError:
        # CLI fallback
        cmd = ["edge-tts", "--voice", voice, "--text", text[:4000], "--write-media", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr or "edge-tts 失败")
    if not out.is_file() or out.stat().st_size < 100:
        raise RuntimeError("Edge-TTS 未生成有效音频")
    _log(log, f"Edge-TTS 完成: {out}")
    return str(out)


def edge_tts_from_srt(
    srt_path: str,
    *,
    out_path: str = "",
    voice: str = "",
    lang: str = "zh",
    log: LogFn = print,
) -> str:
    text = srt_to_plain_text(srt_path)
    if not out_path:
        out_path = str(Path(srt_path).with_suffix(".tts.mp3"))
    return edge_tts_from_text(text, out_path, voice=voice, lang=lang, log=log)


def install_edge_tts(log: LogFn = print, mirror: str = "") -> str:
    from pkg_update import pip_install

    ok, res = pip_install(["edge-tts"], log=lambda m, lv="info": _log(log, m, lv), mirror=mirror, timeout=300)
    return "ok" if ok else f"failed: {res}"


# ── Deep-Translator 免费兜底 ─────────────────────────────

def deep_translator_available() -> bool:
    try:
        import deep_translator  # noqa: F401
        return True
    except Exception:
        return False


def translate_batch_deep_translator(
    texts: List[str],
    target_lang: str = "zh-CN",
    source_lang: str = "auto",
    log: LogFn = print,
) -> List[str]:
    """使用 deep-translator（默认 Google 免费接口）批量翻译。"""
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        raise RuntimeError("请 pip install deep-translator")

    tgt = target_lang
    # 规范化
    m = {
        "zh": "zh-CN", "zh-cn": "zh-CN", "zh-hans": "zh-CN",
        "zh-tw": "zh-TW", "zh-hant": "zh-TW",
        "en": "en", "ja": "ja", "jp": "ja", "ko": "ko",
        "auto": "auto",
    }
    tgt = m.get(tgt.lower(), tgt)
    src = m.get((source_lang or "auto").lower(), source_lang or "auto")
    if src in ("", "auto"):
        src = "auto"

    translator = GoogleTranslator(source=src if src != "auto" else "auto", target=tgt)
    out: List[str] = []
    # 合并短句减少请求，但 Google 有长度限制 ~4500
    batch, batch_idx = [], []
    def flush():
        nonlocal batch, batch_idx, out
        if not batch:
            return
        joined = "\n\n".join(batch)
        try:
            result = translator.translate(joined)
            parts = (result or "").split("\n\n")
            if len(parts) != len(batch):
                # 逐条
                for t in batch:
                    try:
                        out.append(translator.translate(t) or t)
                    except Exception:
                        out.append(t)
            else:
                out.extend(parts)
        except Exception as e:
            _log(log, f"deep-translator 批次失败，逐条重试: {e}", "warning")
            for t in batch:
                try:
                    out.append(translator.translate(t) or t)
                except Exception:
                    out.append(t)
        batch, batch_idx = [], []

    for i, t in enumerate(texts):
        batch.append(t or " ")
        batch_idx.append(i)
        if sum(len(x) for x in batch) > 3500 or len(batch) >= 40:
            flush()
    flush()
    # 对齐长度
    while len(out) < len(texts):
        out.append(texts[len(out)])
    # 一条都没变 = 这一路实际上没翻译（Google 免费接口限流时就这样）。
    # 别把原文当译文返回给上层，抛出后由 translate_with_fallback 换下一个引擎。
    if texts and all((a or "").strip() == (b or "").strip() for a, b in zip(out, texts)):
        raise RuntimeError("deep-translator 未产生译文（可能被限流）")
    return out[: len(texts)]


def install_deep_translator(log: LogFn = print, mirror: str = "") -> str:
    from pkg_update import pip_install

    ok, res = pip_install(["deep-translator"], log=lambda m, lv="info": _log(log, m, lv), mirror=mirror, timeout=300)
    return "ok" if ok else f"failed: {res}"


# ── 翻译失败自动换引擎 ───────────────────────────────────

# 优先级：用户选择 → 其余付费/免费 → deep-translator
FALLBACK_CHAIN = [
    "deepl", "openai", "claude", "gemini", "google", "azure", "deep_translator",
]


def translate_with_fallback(
    texts: List[str],
    *,
    preferred: str,
    target_lang: str,
    source_lang: str = "",
    translate_fns: dict,
    log: LogFn = print,
) -> Tuple[List[str], str]:
    """
    translate_fns: {provider: callable(texts, target, source, log) -> list}
    返回 (translated, used_provider)
    """
    order = []
    pref = (preferred or "deepl").strip().lower()
    if pref and pref != "none":
        order.append(pref)
    for p in FALLBACK_CHAIN:
        if p not in order:
            order.append(p)

    last_err = None
    for prov in order:
        fn = translate_fns.get(prov)
        if not fn:
            continue
        try:
            _log(log, f"尝试翻译引擎: {prov}")
            result = fn(texts, target_lang, source_lang, log)
            if result and len(result) == len(texts):
                _log(log, f"翻译成功: {prov}")
                return result, prov
        except Exception as e:
            last_err = e
            _log(log, f"引擎 {prov} 失败: {e}，切换下一个", "warning")
            continue
    raise RuntimeError(f"所有翻译引擎均失败: {last_err}")
