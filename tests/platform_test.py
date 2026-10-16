r"""多平台（Linux / macOS / 容器）崩溃点自检：本机是 Windows，所以把「Linux 口径」借进来跑。

为什么要这样做：这些分支只有换到非 Windows 才会走到，等真机翻车就晚了。sys.platform 在 CPython
里是可写的，而本次改的判断（is_native_binary / find_n_m3u8dl / aria2_daemon.find_binary）都是
调用时才读 sys.platform，所以可以在 Temp 里造一个 PE 假二进制、把平台借成 linux，直接看它会不会选中。

D 段单独起子进程，因为 STATE_DIR 是 import 时读环境变量定下来的，只能在干净进程里验。
全程只写 %TEMP%（退出即删），不联网、不起服务、不碰 config.json 与下载目录。
控制台是 GBK，子进程读数一律落 UTF-8 文件再读回。

跑法：`python tests/platform_test.py`（末行 FAILED 不为 0 就是没过）
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import List

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
SERVER_PY = (APP_DIR / "server.py").read_text(encoding="utf-8")
DOCKERFILE = (APP_DIR / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (APP_DIR / "docker-compose.yml").read_text(encoding="utf-8")
DOCKERIGNORE = (APP_DIR / ".dockerignore").read_text(encoding="utf-8")

import aria2_daemon as A  # noqa: E402
import server as S  # noqa: E402

FAILED: List[str] = []
TOTAL = 0
TMP = Path(tempfile.mkdtemp(prefix="md_platform_test_"))
atexit.register(shutil.rmtree, TMP, True)

PE = b"MZ\x90\x00\x03\x00\x00\x00"          # PE/COFF 头（Windows 二进制）
ELF = b"\x7fELF\x02\x01\x01\x00"            # ELF 头（Linux 二进制）
SCRIPT = b"#!/bin/sh\necho hi\n"
JUNK = b"this is not a binary at all"


def ck(name: str, cond, detail=""):
    global TOTAL
    TOTAL += 1
    ok = bool(cond)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  <== {str(detail)[:260]}"))
    if not ok:
        FAILED.append(name)


@contextmanager
def as_platform(name: str):
    """把 sys.platform 借成别的系统。被测函数都是调用时才读，所以这一层就够。

    PATH 分隔符要一起借：os.pathsep 是解释器启动时按当前系统定死的字符串常量，
    在 Windows 上就是 ";"，只改 sys.platform 的话「按 os.pathsep 拆 PATH」这条改动测不到。
    """
    old_plat, old_sep = sys.platform, os.pathsep
    sys.platform = name
    os.pathsep = ";" if name == "win32" else ":"
    try:
        yield
    finally:
        sys.platform, os.pathsep = old_plat, old_sep


def put(path: Path, head: bytes = ELF) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head)
    return path


print("== A. is_native_binary：认头不认后缀 ==")
f_pe = put(TMP / "a" / "tool.exe", PE)
f_elf = put(TMP / "a" / "tool", ELF)
f_sh = put(TMP / "a" / "tool.sh", SCRIPT)
f_junk = put(TMP / "a" / "tool.txt", JUNK)
f_dir = TMP / "a" / "adir"
f_dir.mkdir()
with as_platform("linux"):
    ck("A1 Linux 上拒 PE（.exe 存在也不能选）", S.is_native_binary(f_pe) is False, "PE 被判成可执行")
    ck("A2 Linux 上认 ELF", S.is_native_binary(f_elf) is True)
    ck("A3 Linux 上认 shebang 脚本", S.is_native_binary(f_sh) is True)
    ck("A4 既非 ELF 也非脚本的普通文件不算", S.is_native_binary(f_junk) is False)
    ck("A5 目录不算", S.is_native_binary(f_dir) is False)
    ck("A6 不存在的文件不算", S.is_native_binary(TMP / "a" / "nope") is False)
ck("A7 Windows 口径不变：文件在就算（不读文件头）", S.is_native_binary(f_junk) is True)
pe_renamed = put(TMP / "a" / "pretends-to-be-linux", PE)   # 内容仍是 PE，只是把 .exe 后缀拿掉
zero = put(TMP / "a" / "zero-byte", b"")
with as_platform("linux"):
    ck("A8 反向验证：光改后缀骗不过去，PE 内容照样被拒", S.is_native_binary(pe_renamed) is False)
    ck("A9 反向验证：空文件（读不到文件头）不算可执行", S.is_native_binary(zero) is False)

print("== B. 工具查找：Linux 上不能选中随包的 Windows 二进制 ==")
tools = TMP / "b" / "tools"
put(tools / "N_m3u8DL-RE.exe", PE)
_orig_tools = S.TOOLS_DIR
S.TOOLS_DIR = tools
try:
    with as_platform("linux"):
        ck("B1 只有 .exe 时 Linux 查不到 N_m3u8DL-RE（回「未安装」而不是崩在 Exec format）",
           S.find_n_m3u8dl() is None, S.find_n_m3u8dl())
        put(tools / "N_m3u8DL-RE", ELF)
        got = S.find_n_m3u8dl()
        ck("B2 补上 ELF 就选中 ELF 那一个", got is not None and Path(got).name == "N_m3u8DL-RE", got)
    ck("B3 Windows 仍然选中 .exe（改动没把本机弄瞎）",
       Path(S.find_n_m3u8dl() or "").name == "N_m3u8DL-RE.exe", S.find_n_m3u8dl())
finally:
    S.TOOLS_DIR = _orig_tools

wh = TMP / "b" / "Whisper"
put(wh / "whisper.exe", PE)
_orig_whisper = S.WHISPER_DIR
S.WHISPER_DIR = wh
try:
    with as_platform("linux"):
        ck("B4 Whisper 目录里只有 whisper.exe 时 Linux 不认", S._find_local_whisper_bin() is None,
           S._find_local_whisper_bin())
finally:
    S.WHISPER_DIR = _orig_whisper

ar = TMP / "b" / "aria"
put(ar / "tools" / "aria2c.exe", PE)
with as_platform("linux"):
    ck("B5 aria2c：Linux 不选随包 .exe",
       A.find_binary("", ar, S.is_native_binary) == "", A.find_binary("", ar, S.is_native_binary))
    put(ar / "tools" / "aria2c", ELF)
    ck("B6 补上 ELF 后按当前平台的名字找到",
       Path(A.find_binary("", ar, S.is_native_binary)).name == "aria2c")
ck("B7 Windows 仍按 aria2c.exe 命中（.exe 排在前面）",
   Path(A.find_binary("", ar, S.is_native_binary)).name == "aria2c.exe")
ck("B8 不传 runnable 时退回旧的「文件在就算」，老调用方不受影响",
   Path(A.find_binary("", ar)).name == "aria2c.exe")

print("== C. PATH 分隔符：Linux 是「:」不是「;」 ==")
with as_platform("linux"):
    ck("C1 含冒号的 PATH 被拆成多项", len(S._path_split("/app/tools:/usr/bin:/bin")) == 3,
       S._path_split("/app/tools:/usr/bin:/bin"))
    ck("C2 反向：旧写法会把整条当成一项", len("/app/tools:/usr/bin:/bin".split(";")) == 1)
    ck("C3 拼接也用同一个分隔符", S._path_add("/usr/bin", ["/app/tools"]) == "/usr/bin:/app/tools",
       S._path_add("/usr/bin", ["/app/tools"]))
    ck("C4 删除项同样按冒号", S._path_remove("/app/tools:/usr/bin", ["/app/tools"]) == "/usr/bin")
ck("C5 Windows 的分号口径没变", S._path_add("A;B", ["C"]) == "A;B;C" and len(S._path_split("A;B")) == 2)

print("== D. MEDIADOWNLOADER_STATE_DIR：容器只挂一卷就能保住状态 ==")
probe = r"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["_MD_APP"])
import server as S
out = {
    "state": str(S.STATE_DIR), "app": str(S.APP_DIR),
    "config": str(S.CONFIG_FILE), "cookies": str(S.COOKIES_DIR),
    "downloads": str(S.DEFAULT_DOWNLOAD_DIR), "log": str(S.LOG_FILE),
    "history": str(S.HISTORY_FILE),
}
open(os.environ["_MD_OUT"], "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False))
"""
_script = TMP / "probe.py"
_script.write_text(probe, encoding="utf-8")


def run_probe(state_dir: str = "") -> dict:
    import json as _json
    out_file = TMP / f"probe_out_{abs(hash(state_dir))}.json"
    env = dict(os.environ)
    env.update({"_MD_APP": str(APP_DIR), "_MD_OUT": str(out_file),
                "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    if state_dir:
        env["MEDIADOWNLOADER_STATE_DIR"] = state_dir
    else:
        env.pop("MEDIADOWNLOADER_STATE_DIR", None)
    r = subprocess.run([sys.executable, str(_script)], cwd=str(APP_DIR), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if not out_file.exists():
        ck(f"D-子进程跑通（state={state_dir or '未设'}）", False, (r.stderr or "")[-400:])
        return {}
    return _json.loads(out_file.read_text(encoding="utf-8"))


want = TMP / "state"
d1 = run_probe(str(want))
ck("D1 设了环境变量：config/cookies/Downloads/日志全部落到那一卷",
   d1 and Path(d1["config"]) == want / "config.json" and Path(d1["cookies"]) == want / "cookies"
   and Path(d1["downloads"]) == want / "Downloads" and Path(d1["log"]) == want / "app.log"
   and Path(d1["history"]) == want / "history.json", d1)
ck("D2 代码与工具仍留在 APP_DIR（镜像里的 /app）",
   d1 and Path(d1["app"]) == APP_DIR and Path(d1["state"]) != d1["app"], d1)
ck("D3 目录被建出来（首启不自编报错）", (want / "Downloads").is_dir() and (want / "cookies").is_dir())
d2 = run_probe()
ck("D4 不设环境变量：STATE_DIR == APP_DIR，本机行为与历史一致",
   d2 and d2["state"] == d2["app"] and Path(d2["config"]) == APP_DIR / "config.json", d2)

print("== E. 服务化接线（静态钉住，改漏就红） ==")
ck("E1 uvicorn 带 timeout_graceful_shutdown：SSE 挂着也能在 docker stop 里干净退出",
   "timeout_graceful_shutdown=" in SERVER_PY)
ck("E2 监听地址读环境变量（容器里 127.0.0.1 等于外面进不来）",
   'os.environ.get("MEDIADOWNLOADER_HOST")' in SERVER_PY
   and 'os.environ.get("MEDIADOWNLOADER_PORT")' in SERVER_PY)
ck("E3 存在专门的 /api/health 探针路由", '@app.get("/api/health")' in SERVER_PY)
health_body = SERVER_PY.split('def api_health():')[1].split('@app.get("/api/status")')[0]
ck("E4 探针不查工具（不跑 ffmpeg/yt-dlp/whisper），否则每 30s 白烧一次 CPU",
   all(k not in health_body for k in ("ffmpeg_mgr.version", "check_ytdlp", "whisper_status", "find_n_m3u8dl")),
   health_body[:200])
ck("E5 无桌面时「打开文件夹」给的是可懂的替代说明，不是 TclError 原文",
   "无界面运行" in SERVER_PY and "503" in SERVER_PY.split("def api_browse")[1][:1600])
ck("E6 PATH 读写没有残留写死的分号", 'split(";")' not in SERVER_PY and '";".join' not in SERVER_PY)
ck("E7 工具状态在 Linux 上认系统 PATH（apt 装的 ffmpeg 不该报缺失）",
   "present += [n for n in tools if n not in present and shutil.which(n)]" in SERVER_PY)
ck("E8 界面「组件与依赖」的文件名列跟随平台（不再硬写 .exe）",
   SERVER_PY.count('f"ffmpeg{exe}"') >= 1 and '"tool": "ffmpeg.exe"' not in SERVER_PY)

print("== F. 镜像与编排三件套 ==")
ck("F1 Dockerfile 用 apt 带上 aria2 与 fpcalc（镜像里没有 tools/*.exe）",
   "aria2" in DOCKERFILE and "libchromaprint-tools" in DOCKERFILE)
ck("F2 主机绑定 0.0.0.0 且状态目录指向 /data",
   "MEDIADOWNLOADER_HOST=0.0.0.0" in DOCKERFILE and "MEDIADOWNLOADER_STATE_DIR=/data" in DOCKERFILE)
ck("F3 声明了 UTF-8 环境（否则中文日志与文件名成问号）",
   "PYTHONUTF8=1" in DOCKERFILE and "LANG=C.UTF-8" in DOCKERFILE)
hc = [l for l in DOCKERFILE.splitlines() if not l.strip().startswith("#") and "api/" in l]
ck("F4 HEALTHCHECK 的探针行只打 /api/health（注释里提到 /api/status 不算违规）",
   any(l.strip().startswith("HEALTHCHECK") for l in DOCKERFILE.splitlines()
       if not l.strip().startswith("#"))
   and len(hc) == 1 and "/api/health" in hc[0] and "/api/status" not in hc[0], hc)
ck("F5 .dockerignore 挡掉了几个 GB 的本机目录与状态文件",
   all(x in DOCKERIGNORE for x in ("tools/", "Whisper/", "Downloads/", "config.json"))
   and any(x in DOCKERIGNORE for x in ("*.session", "cookies.txt")))
ck("F6 .dockerignore 没顺手挡掉运行时要的东西",
   all(x not in DOCKERIGNORE for x in ("\nserver.py", "\nstatic/", "\nrequirements.txt")))
ck("F7 compose 不再把 Windows 的 config.json / tools 挂进容器",
   "./config.json" not in COMPOSE and "./tools" not in COMPOSE)
ck("F8 compose 有独立卷承接状态", "volumes:" in COMPOSE and "mediadownloader_data:/data" in COMPOSE)
ck("F9 默认只绑 127.0.0.1（程序本身没有登录）", '"127.0.0.1:8765:8765"' in COMPOSE)
bare = [l for l in COMPOSE.splitlines()
        if l.strip().endswith('"8765:8765"') and not l.strip().startswith("#")]
ck("F10 反向：没有对全网开放的裸端口映射（不带 127.0.0.1 的写法只能留在注释里）", bare == [], bare)

print(f"\nTOTAL: {TOTAL} FAILED: {len(FAILED)}")
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
sys.exit(1 if FAILED else 0)
