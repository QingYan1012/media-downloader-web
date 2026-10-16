"""按需拉起本机 aria2c 的 RPC 守护进程：只在 127.0.0.1 上听，密码不写日志。

为什么要有这一层：aria2 的 JSON-RPC 客户端（aria2_client.py）假定「对面已经有人开着」，
而磁力/种子任务没有 aria2 就根本跑不起来。所以这里补一个「找不到就自己拉一个」的兜底，
并且把它拉起来的进程记录住，好让界面上的状态说清是「我们启的」还是「你自己启的」。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

_LOCK = threading.Lock()
_PROC: Optional[subprocess.Popen] = None
_STARTED_BY_US = False


def find_binary(configured: str = "", app_dir: Optional[Path] = None,
                runnable: Optional[Callable] = None) -> str:
    """按「设置里指的路径 → tools/ → PATH → 环境变量」找 aria2c，找一个算一个。

    返回空串表示本机没有：这时界面上要能说清「要么装一个，要么在设置里指路径」，
    而不是让下载卡在半路。

    runnable 由调用方注入（server.is_native_binary）：容器镜像的 tools/ 里常带着 Windows 的
    aria2c.exe，文件在但 Linux 执行不了，只判 is_file 会选中它、然后在 Popen 处炸。
    """
    ok = runnable or (lambda p: Path(p).is_file())
    names = ("aria2c.exe", "aria2c") if sys.platform == "win32" else ("aria2c",)
    cands = []
    if configured:
        cands.append(Path(configured))
    if app_dir:
        for n in names:
            cands.append(Path(app_dir) / "tools" / n)
    env = (os.environ.get("MEDIA_ARIA2_BIN") or "").strip()
    if env:
        cands.append(Path(env))
    for c in cands:
        if str(c) and ok(c):
            return str(c)
    for n in names:
        got = shutil.which(n)
        if got and ok(got):
            return got
    return ""


def _state_dir(app_dir: Path) -> Path:
    # 会话文件里记的是磁力 info hash 与真实下载路径，属于本机数据：单独放一个目录，打包时整目录排除
    d = Path(app_dir) / "torrent_state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def running_rpc_port(rpc_url: str) -> int:
    """从 rpc_url 里取端口，拉进程时要用同一个端口，否则设置里的地址就对不上。"""
    p = urlparse(rpc_url or "")
    return p.port or 6800


def ensure_running(
    *,
    rpc_url: str,
    binary: str,
    download_dir: str,
    app_dir: Path,
    ping,
    log,
    wait_sec: int = 20,
) -> tuple[bool, str]:
    """确保 RPC 可用。返回 (是否可用, 说明)。已有进程在听就什么都不做。

    ping: 无参函数，返回 bool。log: 一行文本的回调。
    """
    global _PROC, _STARTED_BY_US
    if ping():
        return True, "aria2 已在运行"
    if not binary or not Path(binary).is_file():
        return False, "本机找不到 aria2c：装一个，或在「组件与依赖」里把它的路径指对"
    u = urlparse(rpc_url or "")
    if u.hostname not in ("127.0.0.1", "localhost", "::1"):
        # 只允许本机：aria2 的 RPC 没有鉴权时等于把下载权交给局域网
        return False, f"RPC 地址 {u.hostname} 不是本机，出于安全不自动拉起"
    port = u.port or 6800
    st = _state_dir(Path(app_dir))
    # aria2 读不到会话文件会当场报错退出，第一次跑必须先把它建出来（空文件就行）
    session = st / "aria2_session.txt"
    if not session.is_file():
        try:
            session.touch()
        except OSError:
            pass
    args = [
        binary,
        "--enable-rpc",
        f"--rpc-listen-port={port}",
        "--rpc-listen-all=false",
        f"--dir={download_dir}",
        f"--input-file={session}",
        f"--save-session={session}",
        "--save-session-interval=30",
        f"--dht-file-path={st / 'dht.dat'}",
        "--seed-ratio=0",
        "--rpc-save-upload-metadata=false",
        f"--log={Path(app_dir) / 'Logs' / 'aria2_daemon.log'}",
        "--log-level=notice",
    ]
    with _LOCK:
        if ping():
            return True, "aria2 已在运行"
        if _PROC is not None and _PROC.poll() is None:
            return False, "aria2 正在启动中，稍等几秒再看状态"
        (Path(app_dir) / "Logs").mkdir(parents=True, exist_ok=True)
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _PROC = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=flags)
        except OSError as e:
            return False, f"启动 aria2c 失败: {e}"
        _STARTED_BY_US = True
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        if _PROC.poll() is not None:
            code = _PROC.returncode
            return False, f"aria2c 启动后立刻退出（退出码 {code}），详见 Logs/aria2_daemon.log"
        if ping():
            log(f"aria2 守护进程已拉起（PID {_PROC.pid}，仅监听 127.0.0.1:{port}）")
            return True, "已自动启动本机 aria2"
        time.sleep(0.5)
    return False, f"等了 {wait_sec} 秒，aria2 的 RPC 还是没有应答（端口 {port}）"


def owned() -> dict:
    """我们拉起来的那个进程现在什么样：界面上要能区分「工具启的」和「用户自己启的」。"""
    if _PROC is None:
        return {"owned": False, "pid": None, "alive": False}
    return {"owned": _STARTED_BY_US, "pid": _PROC.pid, "alive": _PROC.poll() is None}


def shutdown() -> None:
    """收掉我们自己起的 aria2（退出前它会写会话文件，做种状态不丢）。"""
    global _PROC, _STARTED_BY_US
    with _LOCK:
        if _PROC is None or _PROC.poll() is not None:
            _PROC = None
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
