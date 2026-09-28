"""
字幕优先流水线（参考 AI-Video-Transcriber）:
  1) 旁路已有字幕 (.srt/.vtt)
  2) 若有 webpage_url / info.json → yt-dlp 只拉字幕
  3) 否则 faster-whisper
  4) 可选 LLM 润色 / 摘要 / 条件机翻
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

LogFn = Callable[..., None]


def _log(log: LogFn, msg: str, level: str = "info"):
    try:
        log(msg, level)
    except TypeError:
        log(msg)


def find_sidecar_subs(media: Path) -> Optional[Path]:
    """同目录下已有字幕文件。"""
    stem = media.stem
    parent = media.parent
    candidates = []
    for p in parent.iterdir():
        if not p.is_file():
            continue
        n = p.name.lower()
        if not (n.endswith(".srt") or n.endswith(".vtt") or n.endswith(".ass")):
            continue
        if p.stem == stem or p.stem.startswith(stem + ".") or stem in p.stem:
            candidates.append(p)
    if not candidates:
        return None
    # 优先 srt 非 en 机翻后缀随意
    candidates.sort(key=lambda x: (0 if x.suffix.lower() == ".srt" else 1, len(x.name)))
    return candidates[0]


def vtt_to_srt_text(vtt: str) -> str:
    lines = []
    idx = 1
    blocks = re.split(r"\n\s*\n", vtt.replace("\r\n", "\n"))
    time_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})"
    )
    for block in blocks:
        blines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not blines:
            continue
        if blines[0].upper().startswith("WEBVTT") or blines[0].startswith("NOTE"):
            continue
        tline = None
        text_lines = []
        for ln in blines:
            m = time_re.search(ln)
            if m:
                tline = f"{m.group(1).replace('.', ',')} --> {m.group(2).replace('.', ',')}"
            elif not ln.isdigit() and "-->" not in ln:
                # 去 VTT 标签
                clean = re.sub(r"<[^>]+>", "", ln).strip()
                if clean:
                    text_lines.append(clean)
        if tline and text_lines:
            lines.append(str(idx))
            lines.append(tline)
            lines.append("\n".join(text_lines))
            lines.append("")
            idx += 1
    return "\n".join(lines)


def ensure_srt(path: Path, log: LogFn = print) -> Optional[Path]:
    """把 vtt/ass 尽量转成 srt；已是 srt 则返回。"""
    if not path.is_file():
        return None
    suf = path.suffix.lower()
    if suf == ".srt":
        return path
    out = path.with_suffix(".srt")
    if suf == ".vtt":
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            srt = vtt_to_srt_text(text)
            if srt.strip():
                out.write_text(srt, encoding="utf-8")
                _log(log, f"VTT→SRT: {out.name}")
                return out
        except Exception as e:
            _log(log, f"VTT 转换失败: {e}", "warning")
    # ffmpeg 兜底
    try:
        cmd = ["ffmpeg", "-y", "-i", str(path), str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.is_file() and out.stat().st_size > 20:
            _log(log, f"ffmpeg 字幕转换: {out.name}")
            return out
    except Exception as e:
        _log(log, f"ffmpeg 字幕转换失败: {e}", "warning")
    return None


def find_info_json(media: Path) -> Optional[Path]:
    parent = media.parent
    stem = media.stem
    for p in parent.glob("*.info.json"):
        if stem in p.stem or p.stem.replace(".info", "") in stem:
            return p
    # 宽松：同目录最近的 info.json
    infos = sorted(parent.glob("*.info.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    return infos[0] if infos else None


def webpage_url_from_info(info_path: Path) -> str:
    try:
        data = json.loads(info_path.read_text(encoding="utf-8", errors="ignore"))
        return str(data.get("webpage_url") or data.get("original_url") or data.get("url") or "")
    except Exception:
        return ""


def ydl_download_subs_only(
    url: str,
    out_dir: Path,
    *,
    langs: Optional[List[str]] = None,
    log: LogFn = print,
) -> Optional[Path]:
    """仅下载字幕，不下载视频。返回 srt 路径。"""
    if not url.startswith("http"):
        return None
    langs = langs or ["zh-Hans", "zh-CN", "zh", "en", "ja", "all"]
    out_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(out_dir / "%(title).80B [%(id)s]")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", ",".join(langs),
        "--convert-subs", "srt",
        "--sub-format", "srt/vtt/best",
        "-o", outtmpl,
        "--no-playlist",
        url,
    ]
    _log(log, "字幕优先: yt-dlp 仅拉字幕…")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:
        _log(log, f"拉字幕失败: {e}", "warning")
        return None
    # 找最新 srt
    srts = sorted(out_dir.glob("*.srt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not srts:
        # 可能写出 vtt
        vtts = sorted(out_dir.glob("*.vtt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for v in vtts[:5]:
            s = ensure_srt(v, log)
            if s:
                return s
        _log(log, "未拿到平台字幕，将走 Whisper", "warning")
        return None
    _log(log, f"平台字幕: {srts[0].name}")
    return srts[0]


def srt_plain_text(srt_path: Path, max_chars: int = 120000) -> str:
    text = srt_path.read_text(encoding="utf-8", errors="ignore")
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.isdigit() or re.match(r"\d{2}:\d{2}:\d{2}", line):
            continue
        lines.append(line)
    body = "\n".join(lines)
    return body[:max_chars]


def llm_chat(
    messages: List[dict],
    *,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    timeout: int = 180,
) -> str:
    import urllib.request
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        or ""
    ).strip()


def polish_transcript(
    text: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    lang: str = "zh",
    log: LogFn = print,
) -> str:
    if not text.strip() or not api_key:
        return text
    _log(log, "LLM 润色转写文本…")
    sys_prompt = (
        "你是字幕润色助手。请修正明显错别字、补全残缺句、合理分段，"
        "不要添加原文没有的信息，不要翻译，保持原语言。"
        "只输出润色后的正文，不要解释。"
    )
    if lang and lang not in ("auto", ""):
        sys_prompt += f" 源语言倾向: {lang}。"
    try:
        out = llm_chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text[:80000]},
            ],
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return out or text
    except Exception as e:
        _log(log, f"润色失败: {e}", "warning")
        return text


def summarize_transcript(
    text: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    summary_lang: str = "zh",
    log: LogFn = print,
) -> str:
    if not text.strip() or not api_key:
        return ""
    _log(log, f"LLM 摘要 → {summary_lang}…")
    lang_name = {
        "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어",
        "zh-cn": "中文", "zh-hans": "中文",
    }.get((summary_lang or "zh").lower(), summary_lang)
    sys_prompt = (
        f"请用{lang_name}为以下音视频转写写一份结构化摘要："
        "包含一句话总览、要点列表、如有时间线可简述。不要编造原文没有的内容。"
    )
    try:
        return llm_chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text[:80000]},
            ],
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    except Exception as e:
        _log(log, f"摘要失败: {e}", "warning")
        return ""


PIPELINE_STAGES = ("subtitle", "polish", "summary", "translate")


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def pipeline_manifest_path(media) -> Path:
    return Path(media).with_name(Path(media).stem + ".pipeline.json")


def load_manifest(media) -> Dict:
    p = pipeline_manifest_path(media)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("stages"), dict):
            return data
    except Exception:
        pass
    return {"media": str(media), "stages": {}}


def save_manifest(media, data: Dict) -> str:
    p = pipeline_manifest_path(media)
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)
    except Exception:
        return ""


def update_manifest(media, stage: str, *, status: str, out: str = "", note: str = "", extra: Dict = None) -> Dict:
    """写回某个阶段的结果；status 取 running|done|skipped|failed。"""
    data = load_manifest(media)
    prev = data["stages"].get(stage) or {}
    entry = dict(prev)
    entry["status"] = status
    if out:
        entry["out"] = out
    elif status == "running":
        entry.setdefault("out", "")
    if note:
        entry["note"] = note
    if extra:
        entry.update(extra)
    entry["at"] = _now_iso()
    data["stages"][stage] = entry
    data["media"] = str(media)
    data["updated"] = entry["at"]
    data["manifest"] = save_manifest(media, data)
    return data


def _stage_artifact(media, stage: str) -> Optional[Path]:
    """manifest 里记录的某阶段产物，仍存在于磁盘才返回。"""
    entry = (load_manifest(media).get("stages") or {}).get(stage) or {}
    out = entry.get("out") or ""
    if not out:
        return None
    p = Path(out)
    return p if p.is_file() else None


def find_pipeline_srt(media) -> Optional[Path]:
    """单步重跑时找回上一步的字幕产物。"""
    m = Path(media)
    p = _stage_artifact(m, "subtitle")
    if p:
        return p
    direct = m.with_suffix(".srt")
    if direct.is_file():
        return direct
    sibs = sorted(
        (x for x in m.parent.glob(m.stem + "*.srt") if x.is_file()),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    return sibs[0] if sibs else None


def run_pipeline(
    media_path: str,
    *,
    subtitle_first: bool = True,
    use_whisper: bool = True,
    polish: bool = False,
    summarize: bool = False,
    translate_after: bool = False,
    lang: str = "auto",
    summary_lang: str = "zh",
    target_lang: str = "zh",
    whisper_fn=None,
    translate_fn=None,
    openai_key: str = "",
    openai_base: str = "https://api.openai.com/v1",
    openai_model: str = "gpt-4o-mini",
    only: str = "",
    log: LogFn = print,
) -> Dict:
    """
    返回 {
      ok, srt, path_type: subtitle|whisper|existing,
      polished, summary, translated_srt, manifest, message
    }
    only 取 PIPELINE_STAGES 之一时只重跑该阶段，输入沿用上一步落盘产物。
    """
    media = Path(media_path)
    only = (only or "").strip().lower()
    if only and only not in PIPELINE_STAGES:
        only = ""
    run_all = not only

    def wants(stage: str, flag: bool) -> bool:
        return (only == stage) if not run_all else flag

    result = {
        "ok": False,
        "srt": "",
        "path_type": "",
        "polished": "",
        "summary": "",
        "translated_srt": "",
        "manifest": "",
        "message": "",
    }
    if not media.is_file():
        result["message"] = "文件不存在"
        return result

    def mark(stage: str, status: str, out="", note: str = "") -> Dict:
        data = update_manifest(media, stage, status=status, out=str(out or ""), note=note)
        result["manifest"] = data.get("manifest", "")
        return data

    srt_path: Optional[Path] = None
    path_type = ""

    if run_all or only == "subtitle":
        mark("subtitle", "running")

        # 1) 旁路字幕
        if subtitle_first:
            side = find_sidecar_subs(media)
            if side:
                s = ensure_srt(side, log)
                if s:
                    srt_path = s
                    path_type = "existing"
                    _log(log, f"使用已有字幕: {s.name}")

        # 2) yt-dlp 平台字幕
        if srt_path is None and subtitle_first:
            info = find_info_json(media)
            url = webpage_url_from_info(info) if info else ""
            if url:
                got = ydl_download_subs_only(url, media.parent, log=log)
                if got:
                    # 复制/改名为与媒体同主名，便于关联
                    dest = media.with_suffix(".srt")
                    try:
                        if got.resolve() != dest.resolve():
                            dest.write_text(got.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
                            srt_path = dest
                        else:
                            srt_path = got
                    except Exception:
                        srt_path = got
                    path_type = "subtitle"

        # 3) Whisper
        if srt_path is None and use_whisper and whisper_fn:
            _log(log, "无平台字幕 → Whisper 转写")
            try:
                produced = whisper_fn(str(media), lang=lang)
                if produced:
                    srt_path = Path(produced[0] if isinstance(produced, list) else produced)
                    path_type = "whisper"
            except Exception as e:
                _log(log, f"Whisper 失败: {e}", "error")
                mark("subtitle", "failed", note=str(e))
                result["message"] = str(e)
                return result

        if srt_path is None or not srt_path.is_file():
            msg = "未能得到字幕"
            mark("subtitle", "failed", note=msg)
            result["message"] = msg
            return result

        result["srt"] = str(srt_path)
        result["path_type"] = path_type or "unknown"
        result["ok"] = True
        result["message"] = f"字幕路径={path_type} → {srt_path.name}"
        mark("subtitle", "done", out=srt_path, note=path_type)
    else:
        srt_path = find_pipeline_srt(media)
        if srt_path is None:
            msg = "找不到上一步的字幕产物，请先跑转写"
            mark(only, "failed", note=msg)
            result["message"] = msg
            return result
        result["srt"] = str(srt_path)
        result["path_type"] = "cached"
        result["ok"] = True

    plain = srt_plain_text(srt_path)

    # 4) 润色
    if wants("polish", polish):
        if not openai_key:
            mark("polish", "skipped", note="未配置 API Key")
        else:
            mark("polish", "running", out=result["polished"])
            polished = polish_transcript(
                plain, api_key=openai_key, base_url=openai_base,
                model=openai_model, lang=lang, log=log,
            )
            if polished and polished != plain:
                md = srt_path.with_name(srt_path.stem + ".polished.txt")
                md.write_text(polished, encoding="utf-8")
                result["polished"] = str(md)
                plain = polished
                mark("polish", "done", out=md)
            else:
                mark("polish", "skipped", note="无改动")

    # 5) 摘要
    if wants("summary", summarize):
        if not openai_key:
            mark("summary", "skipped", note="未配置 API Key")
        else:
            prev_polish = _stage_artifact(media, "polish")
            src_text = prev_polish.read_text(encoding="utf-8", errors="ignore") if prev_polish else plain
            mark("summary", "running", out=result["summary"])
            summary = summarize_transcript(
                src_text, api_key=openai_key, base_url=openai_base,
                model=openai_model, summary_lang=summary_lang, log=log,
            )
            if summary:
                sp = srt_path.with_name(srt_path.stem + f".summary.{summary_lang}.md")
                sp.write_text(summary, encoding="utf-8")
                result["summary"] = str(sp)
                _log(log, f"摘要已写: {sp.name}")
                mark("summary", "done", out=sp)
            else:
                mark("summary", "failed", note="模型未返回内容")

    # 6) 条件机翻：目标语言与识别语言不同时
    if wants("translate", translate_after):
        if not translate_fn:
            mark("translate", "skipped", note="机翻引擎不可用")
        elif lang and target_lang and lang.lower()[:2] == target_lang.lower()[:2] and lang != "auto" and run_all:
            _log(log, "源语言与目标相同，跳过机翻")
            mark("translate", "skipped", note="源语言与目标相同")
        else:
            mark("translate", "running", out=result["translated_srt"])
            try:
                out = translate_fn(str(srt_path), target_lang)
                if out:
                    result["translated_srt"] = str(out)
                    mark("translate", "done", out=out)
                else:
                    mark("translate", "failed", note="未产出译文文件")
            except Exception as e:
                _log(log, f"机翻失败: {e}", "warning")
                mark("translate", "failed", note=str(e))

    return result
