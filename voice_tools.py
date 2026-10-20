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

# 就列界面下拉里那三个：htdemucs 是默认，htdemucs_ft 是微调四轨，mdx_extra 是老 mdx 一路。
# htdemucs_6s / mdx23c 这些名字在 demucs 的注册表里确实有，但这台机器上没实测下载与跑通，
# 没验过的名字不给选项 —— 给了就是让用户点下去报「模型下不下来」。
DEMUCS_MODELS = ["htdemucs", "htdemucs_ft", "mdx_extra"]
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
) -> dict:
    """用 venv 里的 demucs 分离；设备三档靠它自己的 -d（实测 cpu/cuda 两档吞吐差 3.5 倍）。"""
    py = separator_python()
    if not py:
        raise RuntimeError("分离引擎的独立环境还没建（tools/separator/venv 里没有 python）")
    probe = separation_probe()
    if probe.get("demucs_import", "") != "ok":
        raise RuntimeError("这个环境里的 demucs 起不来：%s" % probe.get("demucs_import", "没探到"))
    want = _resolved_device(device, probe)
    if device == "cuda" and not probe.get("cuda_available"):
        raise RuntimeError("这个环境看不到 CUDA（torch 报 cuda_available=False），选不了 GPU")
    dest = Path(out_dir) if out_dir else Path(media_path).parent / "demucs"
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [py, "-m", "demucs", "--two-stems", "vocals", "-n", model or "htdemucs",
           "-d", want, "-o", str(dest), str(media_path)]
    _log(log, f"Demucs 开始: {model} / {want}")
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
            "stems": found, "device_matched": True}


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
    所以它证明的是一致性，不是上游作者的真伪 —— 那句「已就绪」也只说到这儿。"""
    if expect_sha:
        h = hashlib.sha256()
        with open(part, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != expect_sha:
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
    for u in github_url_candidates(url):
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
