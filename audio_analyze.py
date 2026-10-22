"""
Librosa 音频分析摘要：BPM、调性、响度、时长等。
可选写出 .analysis.json 旁路文件。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

LogFn = Callable[..., None]


def _log(log: LogFn, msg: str, level: str = "info"):
    try:
        log(msg, level)
    except TypeError:
        log(msg)


DECODE_SR = 22050


def _ffmpeg_exe() -> str:
    try:
        from diarize_tools import ffmpeg_executable

        return ffmpeg_executable()
    except Exception:
        return "ffmpeg"


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(cmd, capture_output=True, timeout=600, **kw)


def _decode_pcm(path: str, duration: float) -> Tuple[Any, int]:
    """librosa 1.0 只解得动 libsndfile 认得的容器，mkv/mp4 要先让 ffmpeg 抽成单声道 PCM。"""
    import numpy as np

    cmd = [_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-i", path, "-vn", "-ac", "1", "-ar", str(DECODE_SR), "-f", "s16le", "-"]
    try:
        p = _run(cmd)
    except Exception as e:
        raise RuntimeError(f"ffmpeg 取音轨失败: {e}")
    if p.returncode != 0 or not p.stdout:
        tail = (p.stderr or b"")[-200:].decode("utf-8", "ignore").strip()
        raise RuntimeError(f"ffmpeg 没有输出音轨（这份文件可能没有声轨）{('：' + tail) if tail else ''}")
    return np.frombuffer(p.stdout, dtype="<i2").astype(np.float32) / 32768.0, DECODE_SR


def probe_media(path: str) -> Tuple[Optional[float], bool, str]:
    """让 ffmpeg 读一遍头部：返回 (整段时长, 有没有声轨, 认不出来时的原因尾巴)。"""
    try:
        p = _run([_ffmpeg_exe(), "-hide_banner", "-i", path])
    except Exception as e:
        return None, False, f"ffmpeg 启动失败：{e}"
    txt = (p.stderr or b"").decode("utf-8", "ignore")
    m = re.search(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", txt)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    has_audio = any("Stream #" in ln and ": Audio" in ln for ln in txt.splitlines())
    tail = ""
    if "Duration:" not in txt:
        # 有些容器给不出时长（裸 aac 是 N/A），所以只把「整段头部都没读出来」当失败
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        tail = lines[-1] if lines else "ffmpeg 没有任何输出"
    return dur, has_audio, tail


def preflight(path: str) -> str:
    """起线程之前先判一次：读不懂、或压根没有声轨，就当场回错，别只写进日志。"""
    _dur, has_audio, tail = probe_media(path)
    if tail:
        return f"ffmpeg 读不出这个文件的媒体信息：{tail}"
    if not has_audio:
        return "这份文件没有声轨，音频分析需要带音轨的媒体文件"
    return ""


def _probe_duration(path: str) -> Optional[float]:
    """整段时长读 ffmpeg 横幅里的 Duration，省掉再依赖 ffprobe。"""
    return probe_media(path)[0]


def analyze_audio(
    path: str,
    *,
    write_json: bool = True,
    max_duration: float = 180.0,
    log: LogFn = print,
) -> dict:
    """
    分析单个音频/含音轨媒体。
    max_duration: 最长分析秒数（从头截取，控制内存）。
    """
    p = Path(path)
    out = {
        "ok": False,
        "path": str(p),
        "name": p.name,
        "duration_sec": None,
        "sr": None,
        "tempo_bpm": None,
        "key": None,
        "key_strength": None,
        "rms_mean": None,
        "rms_db": None,
        "spectral_centroid_hz": None,
        # 可选那两项：没装分析依赖时这几个键也要在，界面与旁路 JSON 不用判断「键在不在」
        "bpm": None,
        "beats": [],
        "downbeats": [],
        "segments": [],
        "bpm_allin1": None,
        "analysis_device": "",
        "analysis_note": "",
        "analysis_error": "",
        "message": "",
        "json_path": "",
    }
    if not p.is_file():
        out["message"] = "文件不存在"
        return out

    try:
        import librosa
        import numpy as np
    except ImportError:
        out["message"] = ("缺少 librosa，音频分析未启动：请在「设置 → 组件与依赖」的 Python 依赖里"
                          "安装 librosa（会连带装 numba / llvmlite），或在本机执行 pip install librosa 后重试")
        _log(log, out["message"], "warning")
        return out

    try:
        # 只取前 max_duration 秒的 PCM，避免长视频爆内存
        y, sr = _decode_pcm(str(p), max_duration)
        if y is None or len(y) < sr * 0.5:
            out["message"] = "有效音频过短"
            return out

        duration = float(librosa.get_duration(y=y, sr=sr))
        # 若文件更长，用完整时长（不整文件 decode）
        full_dur = _probe_duration(str(p)) or duration

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, "__len__"):
            tempo = float(np.asarray(tempo).reshape(-1)[0])
        else:
            tempo = float(tempo)

        rms = librosa.feature.rms(y=y)
        rms_mean = float(np.mean(rms))
        # PCM 已归一到 ±1.0，ref=1.0 才是真实 dBFS；ref=np.max 会拿自己当基准，恒等于 0
        rms_db = float(librosa.amplitude_to_db(np.array([rms_mean]), ref=1.0)[0]) if rms_mean > 0 else -120.0

        cent = librosa.feature.spectral_centroid(y=y, sr=sr)
        cent_mean = float(np.mean(cent))

        # 调性：chroma + key profile 相关
        key_name, key_strength = _estimate_key(y, sr)

        # 拍点与段落结构：装在分离那个独立环境里，没装就只少这两项，上面那五个指标照旧。
        # 注意跑的是整首（段落结构要看全曲），和上面 180 秒封顶的 tempo 不是同一个窗口。
        extra: dict = {}
        try:
            from voice_tools import analyze_beats_structure
            extra = analyze_beats_structure(str(p), device="auto", log=log) or {}
        except Exception as e:
            extra = {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:160])}
        bpm_new = extra.get("bpm")
        note = ""
        if bpm_new and tempo and tempo > 0:
            ratio = float(bpm_new) / float(tempo)
            if ratio >= 1.25 or ratio <= 0.8:
                # 实测样本：180 BPM 的歌 librosa 报 89.1、76 报成 152 —— 差一倍不是精度差一点，
                # 所以这里不静默替换，把两个数都留着让人自己看
                note = f"旧读数 {tempo:.1f}（相差 {ratio:.2f} 倍）"
        segs = extra.get("segments") or []
        # 起点留一位小数：整秒会把 0.0 与 0.1 两段并成同一个「@0s」，看着像同一段重复了
        lab_txt = "、".join(f"{s.get('label', '?')}@{s.get('start', 0):.1f}s" for s in segs[:3])

        out.update({
            "ok": True,
            "duration_sec": round(full_dur, 3),
            "analyzed_sec": round(duration, 3),
            "sr": int(sr),
            "tempo_bpm": round(tempo, 2),
            "key": key_name,
            "key_strength": round(key_strength, 3) if key_strength is not None else None,
            "rms_mean": round(rms_mean, 6),
            "rms_db": round(rms_db, 2),
            "spectral_centroid_hz": round(cent_mean, 1),
            "bpm": bpm_new,
            "beats": extra.get("beats") or [],
            "downbeats": extra.get("downbeats") or [],
            "segments": segs,
            "bpm_allin1": extra.get("bpm_allin1"),
            "analysis_device": extra.get("device") or "",
            "analysis_note": note,
            "analysis_error": ("" if extra.get("ok")
                               else str(extra.get("error") or extra.get("reason") or ""))
                              or "; ".join(str(x) for x in (extra.get("errors") or [])),
            "message": (
                f"{p.name}: {full_dur:.1f}s · {bpm_new or tempo:.1f} BPM · "
                f"调性 {key_name or '?'} · 响度 {rms_db:.1f} dB"
                + (f" · 拍点 {len(extra.get('beats') or [])} 段 {len(segs)}"
                   f"（{lab_txt}…）" if segs else "")
                + (" · 段落结构没算出来" if (extra and not segs and not extra.get("skipped")) else "")
                + (f" · {note}" if note else "")
            ),
        })
        _log(log, f"[分析] {out['message']}")

        if write_json:
            jp = p.with_suffix(p.suffix + ".analysis.json")
            # 更清晰：name.analysis.json
            jp = p.with_name(p.stem + ".analysis.json")
            payload = {k: v for k, v in out.items() if k != "ok"}
            jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            out["json_path"] = str(jp)
            _log(log, f"分析 JSON: {jp.name}")

        return out
    except Exception as e:
        out["message"] = f"分析失败: {e}"
        _log(log, out["message"], "error")
        return out


def _estimate_key(y, sr) -> tuple:
    """简易 Krumhansl 风格调性估计。"""
    try:
        import librosa
        import numpy as np
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        # major / minor profiles (Krumhansl-Schmuckler 简化)
        major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        best_key, best_corr = None, -1.0
        for i in range(12):
            maj = float(np.corrcoef(chroma_mean, np.roll(major, i))[0, 1])
            min_ = float(np.corrcoef(chroma_mean, np.roll(minor, i))[0, 1])
            if maj > best_corr:
                best_corr, best_key = maj, f"{notes[i]} major"
            if min_ > best_corr:
                best_corr, best_key = min_, f"{notes[i]} minor"
        if best_corr != best_corr:  # NaN
            return None, None
        return best_key, best_corr
    except Exception:
        return None, None
