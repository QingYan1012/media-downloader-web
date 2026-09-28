# -*- coding: utf-8 -*-
"""轻量说话人分离（diarization）：不给每个词找说话人，只给已经切好的字幕句贴一个音色标签。

为什么不用 pyannote / speechbrain：那两条路都要 torch + 几 GB 权重 + HuggingFace 门禁
token，而这个包的定位是"拷走就能用"。所以这里只用 numpy + ffmpeg 做一版极简声纹。

能力边界要说清楚：
- 特征：整条音轨 → 40 维对数梅尔谱，每句取「各带的时域起伏」当近似声纹，再用
  「按时间顺序贪心贴类 + 两轮质心重排」合成 K 个说话人；合并阈值拿一段单人主讲实录标定过。
- 分得开音色差别大的（男女、低沉 vs 尖细、录音环境明显不同的两段）；
- 音色接近的两个人、重叠说话、背景音乐很重的段落，会分错或全部归一类；
- 句数太少（<3）时不猜，直接不标。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import List, Optional, Sequence, Tuple

SR = 16000
FRAME_SEC = 0.025
HOP_SEC = 0.010
N_MELS = 40
# 合并阈值：距离小于它算同一个人。0.09 是标定出来的 —— 一段 70 句的单人主讲实录在 0.08~0.10
# 都收敛成 1 类，而男/女、两个男声、共振峰相近的两把嗓子在这点上都能分成 2 类；再宽就开始并人。
MERGE_THRESHOLD = 0.09
MIN_SEG_SEC = 0.5


def available() -> bool:
    """能不能跑：numpy 在、ffmpeg 在（便携包里两样都带着）。"""
    if not shutil.which("ffmpeg"):
        return False
    try:
        import numpy  # noqa: F401
    except Exception:
        return False
    return True


def _run_ffmpeg_to_pcm(media: str, log) -> Optional[bytes]:
    exe = ffmpeg_executable()
    cmd = [
        exe, "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", media, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-",
    ]
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=600, **kw)
    except Exception as e:
        log(f"声纹分离取音频失败: {e}", "warning")
        return None
    if p.returncode != 0 or not p.stdout:
        log("声纹分离取音频失败: ffmpeg 没吐出声轨", "warning")
        return None
    return p.stdout


def ffmpeg_executable() -> str:
    """打包版把 ffmpeg 放在 tools/ 下，PATH 里那份未必是它 —— 由 server 注入更靠谱的路径。"""
    return _FFMPEG or "ffmpeg"


_FFMPEG = ""


def set_ffmpeg(path: str) -> None:
    """server 启动/检测后把实际用的 ffmpeg 路径告知本模块。"""
    global _FFMPEG
    _FFMPEG = path or ""


def _load_pcm(raw: bytes):
    import numpy as np
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def _mel_filterbank(n_fft: int) -> "object":
    import numpy as np
    freqs = np.linspace(0.0, SR / 2.0, n_fft // 2 + 1)
    hz2mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    mel2hz = lambda m: 700.0 * (10.0 ** (m / 2595.0) - 1.0)
    edges = mel2hz(np.linspace(hz2mel(0.0), hz2mel(SR / 2.0), N_MELS + 2))
    fb = np.zeros((N_MELS, len(freqs)), dtype=np.float32)
    for i in range(N_MELS):
        lo, mid, hi = edges[i], edges[i + 1], edges[i + 2]
        up = (freqs - lo) / max(mid - lo, 1e-6)
        dn = (hi - freqs) / max(hi - mid, 1e-6)
        fb[i] = np.maximum(0.0, np.minimum(up, dn))
    return fb


def _logmel(x, log) -> "object":
    """整条音轨 → (帧数, N_MELS) 对数梅能量。"""
    import numpy as np
    if x.size < SR // 10:
        return None
    win = max(16, int(FRAME_SEC * SR))
    hop = max(8, int(HOP_SEC * SR))
    n_fft = 1
    while n_fft < win:
        n_fft <<= 1
    pad = np.pad(x, (0, max(0, win - x.size % hop)))
    frames = np.lib.stride_tricks.as_strided(
        pad, shape=((len(pad) - win) // hop + 1, win), strides=(pad.strides[0] * hop, pad.strides[0])
    )
    env = np.hanning(win).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames * env, n=n_fft)).astype(np.float32) ** 2
    mel = np.log1p(_mel_filterbank(n_fft) @ spec.T).T
    # 减每帧均值：去掉响度/信道增益这类跟"是谁"无关的整体偏移
    return mel - mel.mean(axis=1, keepdims=True)


def _seg_vector(mel, start: float, end: float) -> "object":
    """一句话说完的声纹：各梅尔带在本句内的时域起伏（std），L2 归一。

    先用本句均值把每句的谱形拉平，剩下的起伏才是音色（谐噪比、共振峰的动态）；
    直接取 mean+std 的话，向量里装的是"这句多响、在讲什么"，同一个人换个话题就能差出去。
    """
    import numpy as np
    hop = max(8, int(HOP_SEC * SR))
    a = max(0, int(start * SR) // hop)
    b = min(mel.shape[0], int(end * SR) // hop)
    if b - a < 3:
        return None
    part = mel[a:b] - mel[a:b].mean(axis=0)
    v = part.std(axis=0).astype(np.float32)
    nrm = float(np.linalg.norm(v))
    return v / nrm if nrm > 1e-6 else None


def _labels_by_greedy(vecs, max_speakers: int) -> List[int]:
    """按时间顺序贪心贴类 + 两轮质心重排。层次聚类在这里慢得没道理（每并一次重扫所有组对）。"""
    import numpy as np
    n = len(vecs)
    if n == 0:
        return []
    cap = max(1, min(int(max_speakers or 4), 8))
    labels: List[int] = []
    cents: List["np.ndarray"] = []
    for v in vecs:
        if not cents:
            cents.append(v.copy())
            labels.append(0)
            continue
        sims = np.vstack(cents) @ v
        j = int(np.argmax(sims))
        if 1.0 - float(sims[j]) <= MERGE_THRESHOLD:
            labels.append(j)                       # 听上去还是这个人
        elif len(cents) < cap:
            cents.append(v.copy())
            labels.append(len(cents) - 1)          # 另开一类
        else:
            labels.append(j)                       # 到上限了，硬贴最像的那个
    # 质心重排：贪心的结果跟句子先后有关，再扫两轮把贴错的拽回来
    m = np.vstack(vecs)
    for _ in range(2):
        for c in range(len(cents)):
            sel = [i for i, lb in enumerate(labels) if lb == c]
            if sel:
                mu = m[sel].mean(axis=0)
                nrm = float(np.linalg.norm(mu))
                cents[c] = mu / nrm if nrm > 1e-6 else cents[c]
        if not cents:
            break
        sims = m @ np.vstack(cents).T
        new = sims.argmax(axis=1).tolist()
        if new == labels:
            break
        labels = [int(x) for x in new]
    # 类号按第一次出现的顺序重排成 1..K
    order = {}
    out = []
    for lb in labels:
        out.append(order.setdefault(lb, len(order) + 1))
    return out


def diarize_segments(
    media_path: str,
    spans: Sequence[Tuple[float, float]],
    log=lambda *_a, **_k: None,
    max_speakers: int = 4,
) -> Optional[List[int]]:
    """给字幕句贴说话人号（1 起）。拿不到音频/句数太少时返回 None，让调用方照常出字幕。"""
    try:
        import numpy  # noqa: F401 —— 只做依赖探针，真正用在哪里各函数自己 import
    except Exception:
        return None
    usable = [i for i, (a, b) in enumerate(spans) if (b - a) >= MIN_SEG_SEC]
    if len(usable) < 3:
        return None
    raw = _run_ffmpeg_to_pcm(media_path, log)
    if not raw:
        return None
    mel = _logmel(_load_pcm(raw), log)
    if mel is None or mel.shape[0] < 50:
        log("声纹分离跳过：音轨太短", "warning")
        return None
    vecs, kept = [], []
    for i in usable:
        v = _seg_vector(mel, spans[i][0], spans[i][1])
        if v is not None:
            vecs.append(v)
            kept.append(i)
    if len(kept) < 3:
        return None
    # 不再做逐维标准化：句数一少，逐维 std 本身就是噪声，除下去会把三句同样的声音
    # 放大成三个方向（实测同性别三句被拆成三个人）。向量已各自 L2 归一，直接比即可。
    sub = _labels_by_greedy(vecs, max_speakers)
    out = [0] * len(spans)
    for j, i in enumerate(kept):
        out[i] = int(sub[j]) if j < len(sub) else 0
    return out
