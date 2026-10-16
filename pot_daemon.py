"""按需拉起 tools/bgutil-pot-server 这个 PO Token 服务端：只在 127.0.0.1 上听，不起远程。

为什么要这一层：yt-dlp 的 bgutil 插件（pip 包）只是「要票的人」，票是那个独立的 node 服务造的。
以前它只在临时目录里搭过一次，重启机器就没了，界面上那行永远显示「服务端没起来」，
用户只能对着提示干瞪眼。现在服务端跟着程序放在 tools/ 里，探测不通时由这里补拉一次。

前提是本机有 node（bgutil 服务端是 node 程序，程序不带 node 二进制）：没有就只说「缺 node」，
不去猜别的。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

SERVER_DIR_NAME = "bgutil-pot-server"
DEFAULT_PORT = 4416
# 没 node 就别每次探测都重试一遍 Popen：这一条记一次就够
_NODE_MISSING = False
_LOCK = threading.Lock()
_PROC: Optional[subprocess.Popen] = None
_STARTED_BY_US = False


def server_dir(app_dir: Path) -> Path:
    return Path(app_dir) / "tools" / SERVER_DIR_NAME


def entry_file(app_dir: Path) -> Path:
    return server_dir(app_dir) / "build" / "main.js"


def node_bin() -> str:
    env = (os.environ.get("MEDIA_NODE_BIN") or "").strip()
    if env and Path(env).is_file():
        return env
    return shutil.which("node") or ""


def local_port(url: str) -> Optional[int]:
    """只有指向本机的地址才允许自动拉起 —— 远程服务不该由这个进程管。

    返回 None 表示「这不是本机地址，别碰」。
    """
    u = urlparse(str(url or "").strip() or None)
    host = (u.hostname or "").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return None
    return u.port or DEFAULT_PORT


def ready(app_dir: Path) -> bool:
    return entry_file(app_dir).is_file()


def ensure_running(
    *,
    url: str,
    app_dir: Path,
    ping: Callable[[], bool],
    log: Callable[[str], None],
    wait_sec: int = 20,
) -> tuple[bool, str]:
    """确保本机 POT 服务端在听。已经在听就什么都不做。返回 (是否可用, 说明)。"""
    global _PROC, _STARTED_BY_US, _NODE_MISSING
    if ping():
        return True, "PO Token 服务已在运行"
    port = local_port(url)
    if port is None:
        host = urlparse(str(url or "")).hostname or "?"
        return False, f"{host} 不是本机地址，不自动拉起（这个进程只管 127.0.0.1 上的那个）"
    if not ready(Path(app_dir)):
        return False, (f"缺少 tools/{SERVER_DIR_NAME}/build/main.js：服务端文件不在，"
                       "自己放一份或用 Docker 跑 bgutil-ytdlp-pot-provider")
    if _NODE_MISSING:
        return False, "本机 PATH 里没有 node，POT 服务端起不来（装 Node.js 后重启程序）"
    node = node_bin()
    if not node:
        _NODE_MISSING = True
        return False, "本机 PATH 里没有 node，POT 服务端起不来（装 Node.js 后重启程序）"

    d = server_dir(Path(app_dir))
    args = [node, str(entry_file(Path(app_dir))), "--port", str(port)]
    logpath = Path(app_dir) / "Logs" / "pot_daemon.log"
    with _LOCK:
        if ping():
            return True, "PO Token 服务已在运行"
        if _PROC is not None and _PROC.poll() is None:
            return False, "POT 服务端正在启动，稍等几秒再看状态"
        try:
            logpath.parent.mkdir(parents=True, exist_ok=True)
            fh = open(logpath, "ab")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _PROC = subprocess.Popen(args, cwd=str(d), stdout=fh, stderr=fh, creationflags=flags)
        except OSError as e:
            return False, f"启动 POT 服务端失败: {e}"
        _STARTED_BY_US = True
        p = _PROC
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if p.poll() is not None:
            return False, (f"POT 服务端启动后立刻退出（退出码 {p.returncode}），"
                           f"详见 Logs/{logpath.name}")
        if ping():
            log(f"PO Token 服务端已拉起（PID {p.pid}，仅监听 127.0.0.1:{port}）")
            return True, "已自动启动本机 PO Token 服务端"
        time.sleep(0.4)
    return False, f"等了 {wait_sec} 秒，{port} 端口还是没有应答（看 Logs/{logpath.name}）"


def owned() -> dict:
    """区分「程序起的」和「用户自己起的」，界面那行要说得准。"""
    return {
        "owned": _STARTED_BY_US,
        "pid": _PROC.pid if _PROC is not None else None,
        "alive": _PROC is not None and _PROC.poll() is None,
        "node": node_bin(),
    }


def status(app_dir: Path) -> dict:
    d = server_dir(Path(app_dir))
    return {
        "dir_exists": entry_file(Path(app_dir)).is_file(),
        "dir": str(d),
        "node": node_bin(),
        "owned": _STARTED_BY_US,
        "pid": _PROC.pid if _PROC is not None else None,
        "alive": _PROC is not None and _PROC.poll() is None,
    }


def shutdown() -> None:
    """只收程序自己起的 node；用户自己开的服务进程不动。"""
    global _PROC, _STARTED_BY_US
    with _LOCK:
        if _PROC is None or _PROC.poll() is not None:
            _PROC = None
            _STARTED_BY_US = False
            return
        try:
            _PROC.terminate()
            _PROC.wait(timeout=8)
        except Exception:
            try:
                _PROC.kill()
            except Exception:
                pass
        _PROC = None
        _STARTED_BY_US = False
