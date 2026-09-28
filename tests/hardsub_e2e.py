r"""硬字幕烧录（POST /api/ai/hardsub）端到端自检。

跑法：先按平时的方式起 server.py（127.0.0.1:8765），再 `python tests/hardsub_e2e.py`。
素材全部现造在 %TEMP%\md_burn_selftest，输出也只落那里；不碰 Downloads、不写 config.json。
用完自动清干净（留 --keep 可以留着看抽帧图）。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FF = os.path.join(APP, "tools", "ffmpeg.exe")
FP = os.path.join(APP, "tools", "ffprobe.exe")
D = os.path.join(os.environ.get("TEMP", "/tmp"), "md_burn_selftest")
KW = {"creationflags": subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0}
fails: list[str] = []


def check(name: str, cond, extra: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


def call(path: str, payload=None):
    req = urllib.request.Request(
        BASE + path,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        method="POST" if payload is not None else "GET",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"detail": (e.read().decode("utf-8", "replace") or "")[:300]}
    except Exception as e:  # 连不上 server 直说，别假装功能坏了
        return 0, {"raw": str(e)}


def ff(*args: str) -> int:
    return subprocess.run([FF, "-hide_banner", "-loglevel", "error", *args], capture_output=True, **KW).returncode


def probe(p: str) -> dict:
    raw = subprocess.run(
        [FP, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", p],
        capture_output=True, text=True, encoding="utf-8", errors="replace", **KW,
    ).stdout
    d = json.loads(raw or "{}")
    vs = [s for s in d.get("streams", []) if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    aus = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    return {
        "duration": float((d.get("format") or {}).get("duration") or 0),
        "vcodec": vs[0]["codec_name"] if vs else "",
        "width": vs[0].get("width") if vs else 0,
        "acodec": aus[0]["codec_name"] if aus else "",
        "subs": len([s for s in d.get("streams", []) if s.get("codec_type") == "subtitle"]),
    }


def frame(video: str, at: float, png: str) -> bool:
    ff("-y", "-ss", str(at), "-i", video, "-frames:v", "1", png)
    return os.path.isfile(png) and os.path.getsize(png) > 0


def wait_job(media: str, timeout: int = 180) -> dict:
    key = media.replace("\\", "/")
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, body = call("/api/ai/hardsub_jobs")
        j = next((x for x in (body.get("jobs") or []) if x.get("media", "").replace("\\", "/") == key), None)
        if j and j.get("status") in ("done", "failed", "stopped"):
            return j
        time.sleep(0.4)
    return {"status": "timeout"}


def settle(timeout: int = 120) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, b = call("/api/ai/hardsub_jobs")
        if not [j for j in (b.get("jobs") or []) if j.get("status") == "running"]:
            return True
        time.sleep(0.5)
    return False


def build_fixtures() -> None:
    shutil.rmtree(D, ignore_errors=True)
    os.makedirs(D, exist_ok=True)
    ff("-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=8",
       "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", os.path.join(D, "clip.mp4"))
    ff("-y", "-i", os.path.join(D, "clip.mp4"), "-c:v", "copy", "-c:a", "libopus", "-b:a", "96k",
       os.path.join(D, "clip_opus.mkv"))
    ff("-y", "-i", os.path.join(D, "clip.mp4"), "-vn", "-c:a", "libmp3lame", os.path.join(D, "audio_only.mp3"))
    open(os.path.join(D, "clip.srt"), "w", encoding="utf-8").write(
        "1\n00:00:00,500 --> 00:00:02,300\n第一句：硬字幕烧录测试\n\n"
        "2\n00:00:02,400 --> 00:00:04,200\n第二句 中文 English 123\n\n"
        "3\n00:00:04,400 --> 00:00:06,200\n这是一行比较长的中文字幕，用来看智能换行会不会把它拆成两行显示\n\n"
        "4\n00:00:06,400 --> 00:00:07,800\n第四句 [说话人1] 带说话人标记\n")


def main() -> int:
    if not (os.path.isfile(FF) and os.path.isfile(FP)):
        print("这套自检需要 tools/ 下的 ffmpeg + ffprobe")
        return 2
    if call("/api/status")[0] != 200:
        print(f"连不上 {BASE}，先把 server.py 起起来再跑")
        return 2
    build_fixtures()
    src = os.path.join(D, "clip.mp4")
    out = os.path.join(D, "clip.hardsub.mp4")

    print("=== A. 自动找同名轴 + mp4/aac 直通 ===")
    st, body = call("/api/ai/hardsub", {"path": src, "fontsize": 44, "position": "bottom",
                                        "font": "Microsoft YaHei", "crf": 23})
    check("A1 接口接单并报出用哪份轴", st == 200 and "clip.srt" in str(body), f"{st} {body}")
    job = wait_job(src)
    check("A2 任务跑完", job.get("status") == "done", json.dumps(job, ensure_ascii=False))
    check("A3 进度字段有值（前端进度条靠它）", bool(re.match(r"^\d\d:\d\d:\d\d$", str(job.get("elapsed")))), str(job.get("elapsed")))
    before = os.stat(src)
    if os.path.isfile(out):
        pi = probe(out)
        check("A4 视频重编成 h264", pi["vcodec"] == "h264", pi["vcodec"])
        check("A5 音频保持 aac（不做无谓重编）", pi["acodec"] == "aac", pi["acodec"])
        check("A6 时长对齐 8s", 7.5 <= pi["duration"] <= 8.5, pi["duration"])
        check("A7 输出里没有字幕轨：字幕是像素", pi["subs"] == 0, pi["subs"])
        check("A8 源文件没被动过", os.stat(src).st_size == before.st_size and os.stat(src).st_mtime == before.st_mtime)
        check("A9 临时 ass 不留在目录里", not [f for f in os.listdir(D) if f.startswith("_burnsub_")])
        a = frame(out, 3.0, os.path.join(D, "burned.png"))
        b = frame(src, 3.0, os.path.join(D, "plain.png"))
        check("A10 抽帧成功", a and b)
        if a and b:
            check("A11 同一帧画面确实变了（字被画进去了）",
                  open(os.path.join(D, "burned.png"), "rb").read() != open(os.path.join(D, "plain.png"), "rb").read())
    else:
        check("A3b 输出存在", False, str(os.listdir(D)))

    print("=== B. mkv+opus：mp4 装不下 opus，必须转 aac ===")
    src2 = os.path.join(D, "clip_opus.mkv")
    st, body = call("/api/ai/hardsub", {"path": src2, "srt": os.path.join(D, "clip.srt"),
                                        "fontsize": 64, "position": "top", "crf": 26})
    check("B1 接单", st == 200, f"{st} {body}")
    check("B2 跑完", wait_job(src2).get("status") == "done")
    out2 = os.path.join(D, "clip_opus.hardsub.mp4")
    if os.path.isfile(out2):
        check("B3 音频已转成 aac", probe(out2)["acodec"] == "aac", probe(out2)["acodec"])
    else:
        check("B3 输出存在", False)

    print("=== C. 拒绝都要讲人话 ===")
    st, body = call("/api/ai/hardsub", {"path": os.path.join(D, "audio_only.mp3")})
    check("C1 纯音频拒烧", st == 400 and "没有视频轨" in str(body), f"{st} {body}")
    st, body = call("/api/ai/hardsub", {"path": src})
    check("C2 已有输出时先问，不闷头覆盖", st == 409 and "覆盖" in str(body), f"{st} {body}")
    st, body = call("/api/ai/hardsub", {"path": src, "overwrite": True, "crf": 28})
    check("C3 勾了覆盖才能重来", st == 200, f"{st} {body}")
    check("C4 重跑跑得完", wait_job(src).get("status") == "done")
    for ext in (".srt", ".vtt", ".ass"):
        hp = os.path.join(D, "clip" + ext)
        if os.path.isfile(hp):
            os.replace(hp, os.path.join(D, "hold" + ext))
    open(os.path.join(D, "clip.zh.srt"), "w", encoding="utf-8").write("1\n00:00:00,500 --> 00:00:03,000\n另一路字幕\n")
    st, body = call("/api/ai/hardsub", {"path": src})
    check("C5 只有前缀相近的轴时不许自动拿它烧", st == 400 and "同名" in str(body), f"{st} {body}")
    os.remove(os.path.join(D, "clip.zh.srt"))
    for ext in (".srt", ".vtt", ".ass"):
        hp = os.path.join(D, "hold" + ext)
        if os.path.isfile(hp):
            os.replace(hp, os.path.join(D, "clip" + ext))
    st, body = call("/api/ai/hardsub", {"path": src, "srt": os.path.join(D, "audio_only.mp3")})
    check("C6 字幕后缀不对直接拒", st == 400, f"{st} {body}")

    print("=== D. vtt 也吃（字幕导出会产 .bi.vtt） ===")
    check("D0 前面的任务都落定了", settle())
    open(os.path.join(D, "clip.vtt"), "w", encoding="utf-8").write(
        "WEBVTT\n\n00:00:00.500 --> 00:00:03.000\nVTT 第一行 中文\n\n00:00:04.000 --> 00:00:07.000\nVTT 第二行\n")
    st, body = call("/api/ai/hardsub", {"path": src, "srt": os.path.join(D, "clip.vtt"), "overwrite": True, "crf": 30})
    check("D1 接单并报出 vtt", st == 200 and "clip.vtt" in str(body), f"{st} {body}")
    check("D2 烧得完", wait_job(src).get("status") == "done")
    check("D3 成片可播", probe(out)["vcodec"] == "h264")

    print("=== E. 双语导出的 ASS 主样式没被改坏（回归） ===")
    open(os.path.join(D, "clip.srt"), "w", encoding="utf-8").write("1\n00:00:00,500 --> 00:00:03,000\n主字幕\n")
    open(os.path.join(D, "clip.zh.srt"), "w", encoding="utf-8").write("1\n00:00:00,500 --> 00:00:03,000\n译文\n")
    st, body = call("/api/ai/subtitle_export", {"path": os.path.join(D, "clip.zh.srt")})
    check("E1 双语导出照常", st == 200 and body.get("cues"), f"{st} {body}")
    bi = os.path.join(D, "clip.zh.bi.ass")
    lines = [l for l in open(bi, encoding="utf-8").read().splitlines() if l.startswith("Style: Main")] if os.path.isfile(bi) else []
    expect = ("Style: Main,Noto Sans CJK SC,44,&H00FFFFFF,&H000000FF,&H00101010,&H7F000000,"
              "-1,0,0,0,100,100,0,0,1,2.2,1.2,2,40,40,36,1")
    check("E2 主样式与改动前逐字节一致", lines and lines[0] == expect, str(lines)[:160])

    print("=== F. 停止：半成品必须删干净 ===")
    big = os.path.join(D, "big.mp4")
    ff("-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=40",
       "-f", "lavfi", "-i", "sine=frequency=440:duration=40",
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", big)
    open(os.path.join(D, "big.srt"), "w", encoding="utf-8").write("1\n00:00:01,000 --> 00:00:39,000\n长字幕\n")
    st, body = call("/api/ai/hardsub", {"path": big, "crf": 18})
    check("F1 长任务启动", st == 200, f"{st} {body}")
    time.sleep(3)
    st, body = call("/api/ai/hardsub_stop", {"path": big})
    check("F2 停止端点认这个任务", st == 200 and body.get("ok"), f"{st} {body}")
    job = wait_job(big, timeout=40)
    check("F3 最终状态是 stopped", job.get("status") == "stopped", json.dumps(job, ensure_ascii=False))
    check("F4 半成品 mp4 已删", not os.path.exists(os.path.join(D, "big.hardsub.mp4")))
    check("F5 临时 ass 已删", not [f for f in os.listdir(D) if f.startswith("_burnsub_")])
    st, body = call("/api/ai/hardsub", {"path": big, "crf": 18})
    check("F6 停完还能再开", st == 200, f"{st} {body}")
    time.sleep(2)
    call("/api/ai/hardsub_stop", {"path": big})
    settle(60)

    print()
    print("FAILED:", fails or "none")
    if "--keep" in sys.argv:
        print("素材留在", D)
    else:
        shutil.rmtree(D, ignore_errors=True)
        print("已清理", D, "→", os.path.exists(D))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
