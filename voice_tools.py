"""
语音增强工具（参考 voice-pro 能力，可选依赖）:
  - Demucs 人声/伴奏分离
  - Edge-TTS 字幕配音
  - deep-translator 免费机翻兜底
"""
from __future__ import annotations

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

def demucs_available() -> bool:
    try:
        import demucs  # noqa: F401
        return True
    except Exception:
        return bool(shutil.which("demucs"))


def separate_vocals(
    media_path: str,
    *,
    out_dir: str = "",
    model: str = "htdemucs",
    two_stems: str = "vocals",
    log: LogFn = print,
) -> dict:
    """
    人声/伴奏分离。返回 {vocals, no_vocals, other...} 路径。
    依赖: pip install demucs
    """
    src = Path(media_path)
    if not src.is_file():
        raise FileNotFoundError(media_path)
    dest = Path(out_dir) if out_dir else src.parent / "demucs"
    dest.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "demucs",
        "-n", model or "htdemucs",
        "--two-stems", two_stems or "vocals",
        "-o", str(dest),
        str(src),
    ]
    _log(log, f"Demucs 开始: {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    except FileNotFoundError:
        raise RuntimeError("未找到 demucs，请 pip install demucs")
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-800:]
        raise RuntimeError(f"Demucs 失败: {err}")

    # 输出结构: dest / model / track_name / vocals.wav, no_vocals.wav
    track = src.stem
    found = {}
    for wav in dest.rglob("*.wav"):
        if track.lower() in wav.parent.name.lower() or wav.parent.name == track:
            key = wav.stem  # vocals / no_vocals / drums ...
            found[key] = str(wav)
    if not found:
        # 宽松匹配最近修改
        wavs = sorted(dest.rglob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        for w in wavs[:6]:
            found[w.stem] = str(w)
    _log(log, f"Demucs 完成: {found}")
    return found


def install_demucs(log: LogFn = print, mirror: str = "") -> str:
    from pkg_update import pip_install

    ok, res = pip_install(["demucs"], log=lambda m, lv="info": _log(log, m, lv), mirror=mirror, timeout=900)
    return "ok" if ok else f"failed: {res}"


# ── Edge-TTS ────────────────────────────────────────────

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
