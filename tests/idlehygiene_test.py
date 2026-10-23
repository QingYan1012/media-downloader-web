r"""闲置清理与依赖探测落盘的离线自检。

口径：
- 没有请求满 30 分钟、队列空闲、没有 AI 作业时，释放模型/解析缓存，并删 24 小时前的预览文件；
- 版本探测结果落在 STATE_DIR/version_cache.json，24 小时内重启/闲置恢复都不重复起子进程；
- 清理只动可重建的缓存，不碰 cookies、历史、下载成品。

跑法：`python tests/idlehygiene_test.py`
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
SRC = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")

FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def section(start: str, end: str, text: str = SRC) -> str:
    a = text.find(start)
    b = text.find(end, a + len(start)) if a >= 0 else -1
    return text[a:b] if a >= 0 and b > a else ""


print("== A. 闲置判定 ==")
ck("A1 默认闲置阈值 30 分钟，可用环境变量缩短（自检/沙箱）",
   'IDLE_CLEAN_SEC = float(os.environ.get("MEDIADOWNLOADER_IDLE_CLEAN_SEC") or 1800)' in SRC)
ck("A2 用户请求刷新活动时间；健康探针与页面轮询不算",
   "_ACTIVITY_EXEMPT" in SRC and "if request.url.path not in _ACTIVITY_EXEMPT:" in SRC
   and all(p in SRC for p in ('"/api/health"', '"/api/status"', '"/api/tasks"')))
ck("A2b 剪贴板不再 2 秒轮询，只在进页面/回前台各问一次",
   "pollClipboard();" in HTML and "pollClipboard(); }, 2000)" not in HTML
   and "clipTimer" not in HTML)
tick = section("def _idle_janitor_tick", "def _idle_janitor_loop")
ck("A3 队列空闲且没有 AI 作业才清",
   "if queue.running or queue.pending:" in tick and '_AI_JOBS["active"] > 0' in tick)
ck("A4 一轮空闲只清一次（新请求重新计时）",
   'float(_IDLE_STATE["cleaned_at"]) >= last' in tick)
ck("A5 组件检测/一键更新进行中也不清",
   '_COMP_ALL.get("running")' in tick and '_COMP_CHECK.get("status") == "running"' in tick)

print("== B. 清理内容 ==")
clean = section("def _idle_cleanup_once", "def _idle_janitor_tick")
ck("B1 释放已加载的 Whisper 模型", 'globals().get("_FW_MODEL_CACHE")' in clean and "models.clear()" in clean)
ck("B2 清 URL 解析缓存", 'getattr(engine, "_info_cache", None)' in clean and "info.clear()" in clean)
ck("B3 只清版本内存缓存（落盘 24 小时仍在）",
   all(x in clean for x in ("ffmpeg_mgr._ver_cache.clear()", "_YTDLP_VER_CACHE.clear()",
                            "_N3_VER_CACHE.clear()", "_WHISPER_ST_CACHE.clear()",
                            "_ARIA2_VER_CACHE.clear()")) and "_ver_cache_drop" not in clean)
ck("B4 只删 24 小时前的预览文件",
   "IDLE_PREVIEW_KEEP_SEC = 24 * 3600" in SRC and 'p.stat().st_mtime < cutoff' in clean)
ck("B5 预览目录可被沙箱挪走，默认仍是工具目录",
   'MEDIADOWNLOADER_PREVIEW_DIR' in SRC and 'PREVIEW_DIR = Path(' in SRC
   and 'prev_dir = PREVIEW_DIR' in SRC)
ck("B6 一次清理只写一条可翻译日志", 'k="srv.idle.cleaned"' in clean
   and "'srv.idle.cleaned'" in JS and "闲置清理：释放 {models}" in JS
   and "[Idle] Released {models}" in JS)
ck("B7 启动时挂上守护线程", "threading.Thread(target=_idle_janitor_loop, daemon=True).start()" in SRC)
ck("B8 /api/status 能读到上次清理结果",
   '"idle_clean_at": float(_IDLE_STATE["cleaned_at"])' in SRC and '"idle_clean": dict(' in SRC)

print("== C. 版本探测落盘 24 小时 ==")
ck("C1 落盘文件在状态目录、TTL 24 小时",
   'VER_CACHE_FILE = STATE_DIR / "version_cache.json"' in SRC and "VER_CACHE_TTL = 24 * 3600" in SRC)
ff = section("    def version(self) -> str:", "    def _probe_version")
ck("C2 ffmpeg 先内存再落盘，最后才起子进程",
   '_ver_cache_get("ffmpeg")' in ff and "_ver_cache_put(\"ffmpeg\"" in ff
   and ff.find('_ver_cache_get("ffmpeg")') < ff.find("ver = self._probe_version(path)"))
n3 = section("def n_m3u8dl_version", "def _n3_probe_version")
ck("C3 N_m3u8DL 同一口径", '_ver_cache_get("n_m3u8dl")' in n3 and "_ver_cache_put(\"n_m3u8dl\"" in n3)
yd = section("    def check_ytdlp(self) -> str:", "    def _probe_ytdlp_version")
ck("C4 yt-dlp 落盘并按本地文件 mtime 校验",
   '_ver_cache_get("ytdlp")' in yd and "sig" in yd and "_ytdlp_probe_sig" in SRC)
ws = section("def whisper_status", "def update_whisper")
ck("C5 whisper 状态落盘", '_ver_cache_get("whisper")' in ws and "_ver_cache_put(\"whisper\"" in ws)
ck("C6 上游最新版也走同一份 24 小时落盘",
   "LATEST_TTL = VER_CACHE_TTL" in SRC and '_ver_cache_get("latest")' in SRC
   and '_ver_cache_put("latest"' in SRC)
ck("C7 手动「立即检测」才强制绕过缓存",
   '_latest_cache["ts"] = 0.0' in SRC and '_ver_cache_drop("latest")' in SRC)
PACK = (ROOT / "pack_release.py").read_text(encoding="utf-8")
ck("C8 版本缓存不跟着包走：排除表与出包泄漏自检都点名它",
   r"version_cache\.json" in PACK and '"version_cache.json"' in PACK)

print("== D. 自起沙箱：真的会清、重启不重复探测 ==")
TMP = Path(tempfile.mkdtemp(prefix="md_idlehygiene_"))
STATE = TMP / "state"
DL = TMP / "downloads"
PREV = TMP / "preview"
for d in (STATE, DL, PREV):
    d.mkdir(parents=True)
(STATE / "config.json").write_text(json.dumps({
    "download_dir": str(DL), "po_provider_enabled": False,
    "cleanup_enabled": False, "components_auto_check": False,
    "cookie_file": str(TMP / "none.txt"),
}), encoding="utf-8")
old_prev = PREV / "old-preview.mp3"
new_prev = PREV / "new-preview.mp3"
old_prev.write_bytes(b"old")
new_prev.write_bytes(b"new")
_old = time.time() - 2 * 24 * 3600
os.utime(old_prev, (_old, _old))

procs: list[subprocess.Popen] = []


def start_server(port: int):
    env = dict(os.environ, MEDIADOWNLOADER_STATE_DIR=str(STATE),
               MEDIADOWNLOADER_PREVIEW_DIR=str(PREV),
               MEDIADOWNLOADER_PORT=str(port),
               MEDIADOWNLOADER_IDLE_CLEAN_SEC="2",
               MEDIADOWNLOADER_IDLE_CLEAN_TICK="0.4",
               PYTHONIOENCODING="utf-8")
    o = open(TMP / f"o-{port}.log", "wb")
    e = open(TMP / f"e-{port}.log", "wb")
    p = subprocess.Popen([PY, "server.py"], cwd=str(ROOT), env=env, stdout=o, stderr=e)
    procs.append(p)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return p, base
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("server did not become healthy")


def status(base: str) -> dict:
    with urllib.request.urlopen(base + "/api/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


try:
    p1, base1 = start_server(free_port())
    # 健康探针只刷新活动时间；之后 4 秒不再请求，阈值 2 秒应触发一次清理
    time.sleep(4.2)
    ck("D1 24 小时前的预览被删掉", not old_prev.exists())
    ck("D2 刚生成的预览保留", new_prev.exists())
    st = status(base1)
    ck("D3 /api/status 报出这次清理", float(st.get("idle_clean_at") or 0) > 0,
       str(st.get("idle_clean_at")))
    cache_file = STATE / "version_cache.json"
    ck("D4 版本探测结果已落盘", cache_file.is_file())
    first = json.loads(cache_file.read_text(encoding="utf-8"))
    ts1 = float((first.get("ffmpeg") or {}).get("ts") or 0)
    ck("D5 ffmpeg / yt-dlp / whisper 都在落盘文件里",
       all(k in first for k in ("ffmpeg", "ytdlp", "whisper")), str(sorted(first)))
    st2 = status(base1)
    second = json.loads(cache_file.read_text(encoding="utf-8"))
    ts2 = float((second.get("ffmpeg") or {}).get("ts") or 0)
    ck("D6 同一进程第二次状态查询不重复探测", ts2 == ts1 and ts2 > 0, f"{ts1} -> {ts2}")
    # 重启：同一状态目录，第一次 /api/status 也应直接读盘
    p1.terminate()
    try:
        p1.wait(timeout=10)
    except Exception:
        p1.kill()
    p2, base2 = start_server(free_port())
    st3 = status(base2)
    third = json.loads(cache_file.read_text(encoding="utf-8"))
    ts3 = float((third.get("ffmpeg") or {}).get("ts") or 0)
    ck("D7 重启后首次状态查询读落盘，不复探", ts3 == ts1 and st3.get("ffmpeg"), f"{ts1} -> {ts3}")
    p2.terminate()
finally:
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

print()
if FAILED:
    print(f"FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("FAILED: none")
