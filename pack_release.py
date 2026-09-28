"""打包可分享的便携版（内嵌 Python，解压双击即用）。

用法：
    python pack_release.py                # 完整打包（首次会下载内嵌 Python + 装依赖）
    python pack_release.py --skip-runtime # 复用已下载的 runtime 与已装依赖，只重打应用文件
    python pack_release.py --no-zip       # 只生成 dist/ 目录，不压缩

产物：dist/MediaDownloader-<版本>-portable/ 以及同名 .zip
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DIST = APP_DIR / "dist"
CACHE = APP_DIR / "pack_cache"

# 依赖版本对齐本机已验证可用的组合，避免对方拿到未测过的版本
PKGS = [
    "fastapi==0.115.12",
    "uvicorn==0.34.2",
    "pydantic==2.11.3",
    "python-multipart",  # FastAPI 的 Form() 接口（上传/实时转写）必需，requirements.txt 里漏了
    "requests==2.32.5",
    "yt-dlp==2026.8.19",
    "qrcode==8.2",
    "pillow==12.3.0",
    "websocket-client==1.9.2",
    "curl_cffi==0.16.3",
    # 音乐下载（歌词/标签/TTS/翻译）
    "musicdl==2.14.0",
    "mutagen==1.47.0",
    "edge-tts",
    "deep-translator",
    "zhconv==1.4.3",
    # Telegram 私有/受限频道：MTProto 会话 + 它的 SOCKS 支持 + 加解密加速
    "telethon==1.45.0",
    "python-socks[asyncio]==3.1.1",
    "cryptg==0.6.0",
]

APP_PY = [
    "server.py",
    "pkg_update.py",
    "risk_control.py",
    "music_search.py",
    "telegram_channel.py",
    "telegram_mt.py",
    "ai_pipeline.py",
    "aria2_client.py",
    "audio_analyze.py",
    "diarize_tools.py",
    "voice_tools.py",
]
APP_FILES = ["requirements.txt", "README.md", "README.en.md", "CHANGELOG.md", "LICENSE", "Dockerfile", "docker-compose.yml"]
APP_DIRS = ["static", "plugins", "extension"]
TOOLS_FILES = ["ffmpeg.exe", "ffprobe.exe", "N_m3u8DL-RE.exe", "yt-dlp.exe"]

EXCLUDE_DIR_NAMES = {
    "__pycache__", ".git", ".idea", ".vscode", "node_modules",
    "Downloads", "Whisper", "browser_sniff_profile", "cookies",
    "dist", "pack_cache", "musicdl_outputs", "Logs", "X", "master",
    "_preview",  # 「试听」临时件：本机下出来的真实歌曲
    "local_index",  # 本地音乐索引快照：记的是本机文件的真实路径
    # 登录过账号的会话文件绝对不能进分享包
    "tg_session",
}
EXCLUDE_FILE_RE = re.compile(
    r"(?i)\.(pyc|pyo|log|zip|7z|rar|part|tmp|bak)$|"
    r"^(config\.json|history\.json|library_cache\.json|live_monitors\.json|tg_media_index\.json|"
    r"rss_feeds\.json|subscriptions\.json|music_favorites\.json|catcatch_rules\.json|pack_release\.py)$"
)


def app_version() -> str:
    try:
        html = (APP_DIR / "static" / "index.html").read_text(encoding="utf8", errors="ignore")
        m = re.search(r"v(\d+\.\d+\.\d+)", html)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def run(cmd, **kw) -> None:
    print("  $", " ".join(str(c) for c in cmd)[:160], flush=True)
    subprocess.run(cmd, check=True, **kw)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


PIP_TOOLCHAIN = ["pip", "setuptools", "wheel", "packaging"]


def check_pip(rt: Path) -> None:
    """包内实跑一次 python -m pip —— 自更新功能全靠它，宁可在打包阶段失败。"""
    r = subprocess.run(
        [str(rt / "python.exe"), "-m", "pip", "--version"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit("[runtime] 内嵌 runtime 的 pip 不可用：" + (r.stderr or r.stdout).strip()[:300])
    print("[runtime] pip 就绪：" + r.stdout.strip())


def seed_pip(rt: Path) -> None:
    """把 pip 铺进内嵌 runtime，让对方不用重新发包就能在网页里更新依赖。"""
    sp = rt / "Lib" / "site-packages"
    sp.mkdir(parents=True, exist_ok=True)
    if not (sp / "pip").exists():
        print("[runtime] 铺 pip / setuptools 到内嵌 runtime（供程序内更新依赖）")
        run([sys.executable, "-m", "pip", "install", "--target", str(sp), "--upgrade",
             "--no-cache-dir", "--no-warn-script-location", *PIP_TOOLCHAIN])
        # bin\ 里的 pip.exe 写死了打包机的 Python 路径，在对方电脑上只会误导
        shutil.rmtree(sp / "bin", ignore_errors=True)
    check_pip(rt)


# ---------------------------------------------------------------- runtime
def build_runtime(rt: Path, skip: bool) -> None:
    if skip and (rt / "python.exe").exists() and (rt / "Lib" / "site-packages" / "fastapi").exists():
        print(f"[runtime] 复用 {rt}")
        copy_tkinter(rt)
        seed_pip(rt)
        check_tkinter(rt)
        return
    rt.mkdir(parents=True, exist_ok=True)
    vi = sys.version_info
    tag = f"{vi.major}{vi.minor}"  # 内嵌包文件名用 python312 这种无点写法
    zip_name = f"python-{vi.major}.{vi.minor}.{vi.micro}-embed-amd64.zip"
    url = f"https://www.python.org/ftp/python/{vi.major}.{vi.minor}.{vi.micro}/{zip_name}"
    cached = CACHE / zip_name
    if not cached.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"[runtime] 下载内嵌 Python（与本机 {sys.version.split()[0]} 同版本，保证 wheel 兼容）\n         {url}")
        import urllib.request

        with urllib.request.urlopen(url, timeout=120) as r, open(cached, "wb") as w:
            shutil.copyfileobj(r, w, 1024 * 1024)
    if not (rt / "python.exe").exists():
        print(f"[runtime] 解压 -> {rt}")
        with zipfile.ZipFile(cached) as z:
            z.extractall(rt)

    # 内嵌版默认忽略 PYTHONPATH 与 site-packages，必须改 ._pth 才能吃到 --target 装的包
    pth = next(rt.glob(f"python{tag}._pth"), None)
    if not pth:
        raise SystemExit(f"[runtime] 找不到 {tag}._pth")
    pth.write_text(
        f"python{tag}.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii"
    )

    copy_tkinter(rt)

    sp = rt / "Lib" / "site-packages"
    sp.mkdir(parents=True, exist_ok=True)
    print("[runtime] pip 安装依赖到内嵌 runtime")
    cmd = [sys.executable, "-m", "pip", "install", "--target", str(sp), "--upgrade",
           "--no-cache-dir", "--no-warn-script-location", "--only-binary=:all:", *PKGS]
    try:
        run(cmd)
    except subprocess.CalledProcessError:
        print("[runtime] 纯 wheel 安装失败，回退允许源码构建")
        run([c for c in cmd if c != "--only-binary=:all:"])
    # pip / setuptools 保留在包里：网页里「组件与依赖」的更新按钮要靠它在对方电脑上自升级
    seed_pip(rt)
    check_tkinter(rt)


def copy_tkinter(rt: Path) -> None:
    """内嵌 Python 不带 tkinter，而「选择文件夹」按钮依赖它 —— 从本机完整版补进来。"""
    base = Path(sys.base_prefix)
    # 内嵌版 sys.path 只有 python312.zip / runtime 根 / Lib\site-packages，且不会把
    # DLLs 加进 DLL 搜索路径 —— 所以 .pyd 和它依赖的 DLL 全放根目录，tkinter 包体放 site-packages。
    # tcl86t.dll 还链接了 DLLs\zlib1.dll，漏了它会报「DLL load failed」。
    need = [f for f in (base / "DLLs" / "_tkinter.pyd", base / "DLLs" / "tcl86t.dll",
                        base / "DLLs" / "tk86t.dll", base / "DLLs" / "zlib1.dll") if f.exists()]
    if not any(f.name == "_tkinter.pyd" for f in need):
        print("[runtime] 本机无 tkinter 组件，跳过（「选择文件夹」将不可用，可手动输入路径）")
        return
    for f in need:
        shutil.copy2(f, rt / f.name)
    shutil.copytree(base / "tcl", rt / "tcl", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.lib", "*.sh"))
    tk_pkg = base / "Lib" / "tkinter"
    shutil.rmtree(rt / "Lib" / "tkinter", ignore_errors=True)  # 不在内嵌版 sys.path 上，纯占体积
    for f in (rt / "DLLs" / "_tkinter.pyd", rt / "DLLs" / "tcl86t.dll", rt / "DLLs" / "tk86t.dll"):
        f.unlink(missing_ok=True)  # 内嵌版不会把 DLLs 加进 DLL 搜索路径
    if tk_pkg.exists():
        shutil.copytree(tk_pkg, rt / "Lib" / "site-packages" / "tkinter", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))


def check_tkinter(rt: Path) -> None:
    """在打好的包里实跑一次 tkinter —— 宁可在打包阶段报错，也别发出去后对方点「选择文件夹」没反应。"""
    if not (rt / "_tkinter.pyd").exists():
        return
    env = dict(os.environ)
    env.pop("TCL_LIBRARY", None)
    env.pop("TK_LIBRARY", None)
    # 内嵌版 ._pth 里有 import site，会自动加载 sitecustomize —— 用它补 TCL/TK 路径，
    # 这样即使对方不双击「启动.bat」而是直接跑 python.exe server.py 也能弹窗。
    sc = rt / "Lib" / "site-packages" / "sitecustomize.py"
    if not sc.exists():
        sc.write_text(
            "import os\n"
            "from pathlib import Path\n"
            '_RT = Path(__file__).resolve().parents[2] / "tcl"\n'
            'for _v, _s in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):\n'
            "    _p = _RT / _s\n"
            "    if _p.is_dir() and not os.environ.get(_v):\n"
            "        os.environ[_v] = str(_p)\n",
            encoding="utf-8",
        )
    probe = subprocess.run(
        [str(rt / "python.exe"), "-c", "import tkinter as tk; r=tk.Tk(); r.destroy(); print('tk ok')"],
        capture_output=True, text=True, env=env,
    )
    if "tk ok" not in (probe.stdout or ""):
        raise SystemExit(f"[runtime] tkinter 补入后仍不可用：{(probe.stderr or '').strip()[-300:]}")
    print("[runtime] tkinter/tcl 已补入并自检通过")


def check_components_payload(d: dict) -> None:
    """包内实答的组件接口必须给得出三档版本 —— 「随包」那一列只有真包里才有，漏了要当场拦。"""
    items = d.get("items") or []
    bad = [i.get("key") for i in items if not {"active", "bundled", "latest"} <= set(i)]
    if bad:
        raise SystemExit(f"[ABORT] /api/components 的这些行缺 active/bundled/latest 字段：{bad}")
    if not (d.get("bundled") or {}).get("app"):
        raise SystemExit("[ABORT] /api/components 报不出便携包版本（components_bundled.json 没读到）")
    if not any(i.get("bundled") for i in items):
        raise SystemExit(
            "[ABORT] 没有任何一行带得到「随包」版本，清单八成是空的："
            + str([(i.get("key"), i.get("bundled")) for i in items][:6]))
    print(f"[smoke] 组件接口三档版本齐全，随包清单命中 {sum(1 for i in items if i.get('bundled'))} 项")


def smoke_test(dst: Path) -> None:
    """真起一次打包后的服务，打一个会 import 同目录模块的接口。

    内嵌 runtime 带 python312._pth，sys.path 被锁在 runtime 里、也不认 PYTHONPATH，
    server.py 里 `from music_search import ...` 这类按需导入曾经就是这么在对方机器上
    直接 ModuleNotFoundError 的 —— 只看服务起没起来发现不了。
    """
    import time
    import urllib.request

    port = "8791"
    env = dict(os.environ, MEDIADOWNLOADER_PORT=port, PYTHONUTF8="1")
    proc = subprocess.Popen(
        [str(dst / "runtime" / "python.exe"), str(dst / "server.py")],
        cwd=str(dst), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    urls = (
        f"http://127.0.0.1:{port}/api/music/status",
        f"http://127.0.0.1:{port}/api/components",
    )
    try:
        err = None
        for _ in range(40):
            time.sleep(1)
            try:
                got = []
                for u in urls:
                    with urllib.request.urlopen(u, timeout=5) as r:
                        got.append(r.read().decode("utf-8", "replace"))
                if not all(b.lstrip().startswith("{") for b in got):
                    continue
                print("[smoke] 包内服务已响应，music_search / pkg_update 等同目录模块导入正常")
                check_components_payload(json.loads(got[1]))
                return
            except SystemExit:
                raise
            except Exception as e:
                err = e
                if proc.poll() is not None:
                    break
        raise SystemExit(
            "[smoke] 打包后的服务没能正常工作："
            f"{(proc.stderr.read().decode('utf-8', 'replace') or str(err))[-600:]}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        # 试跑会在包里落下本机配置/缓存，绝不能跟着 zip 出去
        for f in ("config.json", "history.json", "app.log", "library_cache.json",
                  "subscriptions.json", "live_monitors.json", "rss_feeds.json",
                  "music_favorites.json", "catcatch_rules.json"):
            (dst / f).unlink(missing_ok=True)
        for p in dst.glob("app-*.log"):   # 按天归档的运行日志同样属于本机数据
            p.unlink(missing_ok=True)
        for d in ("Downloads", "Whisper", "browser_sniff_profile", "local_index"):
            shutil.rmtree(dst / d, ignore_errors=True)
        for p in dst.rglob("__pycache__"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)


def check_module_imports(dst: Path) -> None:
    """用包内 runtime 逐个 import 顶层模块 —— 专治「server.py 按需 import 的模块忘了进 APP_PY」。

    smoke_test() 只打两个接口，那种缺文件要等对方点了「说话人分离」才炸（diarize_tools.py
    就是这么漏出去的）。内嵌 runtime 的 ._pth 不含当前目录，所以要显式把 '.' 插进 sys.path。
    """
    py = str(dst / "runtime" / "python.exe")
    bad = []
    for f in APP_PY:
        mod = Path(f).stem
        if mod == "server":
            continue  # import server 会跑掉模块级初始化，服务起不来不代表包坏了
        r = subprocess.run(
            [py, "-c", f"import sys; sys.path.insert(0, '.'); import {mod}"],
            cwd=str(dst), capture_output=True, text=True,
        )
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()
            bad.append(f"{mod} -> {tail[-1] if tail else '导入失败'}")
    if bad:
        raise SystemExit("[ABORT] 包内模块 import 失败（检查 APP_PY）：" + " | ".join(bad))
    print(f"[check] {len(APP_PY) - 1} 个顶层模块在包内均可 import")


def selfupdate_probe(dst: Path) -> None:
    """用包内 pip 真装一个微型包再卸掉 —— 证明对方点「更新依赖」时写得进包内 runtime。

    曾经打包脚本为了省体积把 pip 删了，对方点「安装 musicdl」只得到 No module named pip，
    这种坑只有真跑一次安装才拦得住。
    """
    py = str(dst / "runtime" / "python.exe")
    probe = "six"
    before = subprocess.run([py, "-c", f"import {probe}"], capture_output=True, text=True)
    was_there = before.returncode == 0
    r = subprocess.run(
        [py, "-m", "pip", "install", "-U", "--no-cache-dir", "--no-warn-script-location",
         "--disable-pip-version-check", probe],
        capture_output=True, text=True, timeout=600,
    )
    if r.returncode != 0:
        raise SystemExit(
            "[ABORT] 包内 pip 装包失败，网页里的依赖更新会全废："
            + (r.stderr or r.stdout or "")[-400:]
        )
    imp = subprocess.run([py, "-c", f"import {probe}"], capture_output=True, text=True)
    if imp.returncode != 0:
        raise SystemExit(
            "[ABORT] 包内 pip 装上了却 import 不到（site-packages 不在 sys.path 上）："
            + (imp.stderr or "")[-400:]
        )
    if not was_there:
        subprocess.run(
            [py, "-m", "pip", "uninstall", "-y", "--disable-pip-version-check", probe],
            capture_output=True, text=True, timeout=300,
        )
    print("[probe] 包内 pip 安装→导入 通过，程序内依赖更新可用")


# ---------------------------------------------------------------- bundled versions
TOOL_VERSION_ARGS = {
    "ffmpeg.exe": ["-version"],
    "yt-dlp.exe": ["--version"],
    "N_m3u8DL-RE.exe": ["--version"],
}


def bundled_pip_versions(rt: Path) -> dict:
    """问包内 runtime 自己要依赖版本 —— 记的是「装进包里的那些」，不是打包机的全局 Python。"""
    names = [re.split(r"[=<>\[\s]", p)[0] for p in PKGS]
    code = (
        "import json,sys,importlib.metadata as md\n"
        "out={}\n"
        "for n in json.loads(sys.argv[1]):\n"
        "    try:\n        out[n]=md.version(n)\n    except Exception:\n        pass\n"
        "print(json.dumps(out))\n"
    )
    r = subprocess.run([str(rt / "python.exe"), "-c", code, json.dumps(names)],
                       capture_output=True, text=True, timeout=120, errors="replace")
    if r.returncode != 0:
        raise SystemExit("[ABORT] 读不出包内依赖版本，随包版本清单写不出来："
                         + (r.stderr or r.stdout or "").strip()[-300:])
    line = [ln for ln in (r.stdout or "").splitlines() if ln.strip().startswith("{")]
    return json.loads(line[-1]) if line else {}


def bundled_tool_versions(dst: Path) -> dict:
    """包内 tools\\ 里的工具各是什么版本；跑不出来就整个省略这一项，不记空值。"""
    out = {}
    for exe, args in TOOL_VERSION_ARGS.items():
        p = dst / "tools" / exe
        if not p.exists():
            continue
        try:
            r = subprocess.run([str(p), *args], capture_output=True, text=True,
                               timeout=30, errors="replace")
            text = (r.stdout or "") + (r.stderr or "")
        except Exception:
            continue
        m = re.search(r"\d{4}\.\d+\.\d+(?:\.\d+)?|\d+\.\d+(?:\.\d+)?", text)
        if m:
            out[exe] = m.group(0)
    return out


def write_bundled_manifest(dst: Path, version: str) -> None:
    """落 components_bundled.json：设置页「组件与依赖」的「随包」版本就从这里读。"""
    data = {
        "app": version,
        "built": time.strftime("%Y-%m-%d %H:%M"),
        "python": ".".join(str(x) for x in sys.version_info[:3]),
        "pip": bundled_pip_versions(dst / "runtime"),
        "tools": bundled_tool_versions(dst),
    }
    (dst / "components_bundled.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manifest] 随包版本清单：{len(data['pip'])} 个依赖 + {len(data['tools'])} 个工具")


# ---------------------------------------------------------------- app files
def copy_app(dst: Path) -> None:
    for name in APP_PY + APP_FILES:
        src = APP_DIR / name
        if src.exists():
            shutil.copy2(src, dst / name)
    for name in APP_DIRS:
        src = APP_DIR / name
        if not src.exists():
            continue
        shutil.copytree(src, dst / name, dirs_exist_ok=True, ignore=ignore_tree)
    tools = dst / "tools"
    tools.mkdir(exist_ok=True)
    for name in TOOLS_FILES:
        src = APP_DIR / "tools" / name
        if src.exists():
            shutil.copy2(src, tools / name)
        else:
            print(f"  ! 缺少 tools/{name}（对应功能在对方机器上不可用）")
    src = APP_DIR / "tools" / "yt_dlp"
    if src.exists():
        shutil.copytree(src, tools / "yt_dlp", dirs_exist_ok=True, ignore=ignore_tree)
    src = APP_DIR / "chromaprint" / "fpcalc.exe"
    if src.exists():
        (dst / "chromaprint").mkdir(exist_ok=True)
        shutil.copy2(src, dst / "chromaprint" / "fpcalc.exe")
    for d in ("Downloads", "cookies"):
        (dst / d).mkdir(exist_ok=True)
    (dst / "cookies" / "放 cookies.txt 在这里.txt").write_text(
        "Netscape 格式 cookies.txt 放这里，文件名 cookies.txt。\r\n"
        "或者在网页「设置 - Cookie」里直接从本机浏览器读取（需先在浏览器登录对应站点）。\r\n",
        encoding="utf-8",
    )


def ignore_tree(directory: str, contents: list[str]) -> set[str]:
    d = Path(directory)
    if d.name in EXCLUDE_DIR_NAMES:
        return set(contents)
    skip = {c for c in contents if (d / c).is_dir() and c in EXCLUDE_DIR_NAMES}
    skip |= {c for c in contents if EXCLUDE_FILE_RE.search(c)}
    return skip


# ---------------------------------------------------------------- launchers
BAT = """@echo off
rem  MediaDownloader portable launcher  (ASCII only on purpose)
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%runtime\\python.exe"
set "TCL_LIBRARY=%ROOT%runtime\\tcl\\tcl8.6"
set "TK_LIBRARY=%ROOT%runtime\\tcl\\tk8.6"
set "PYTHONUTF8=1"
if not exist "%PY%" (
  echo [ERROR] runtime\\python.exe not found. Extract the whole folder, do not move files out of it.
  pause
  exit /b 1
)
if "%MEDIADOWNLOADER_PORT%"=="" set "MEDIADOWNLOADER_PORT=8765"
echo MediaDownloader is starting...  http://127.0.0.1:%MEDIADOWNLOADER_PORT%
echo Keep this window open while downloading. Close it to stop.
start "" /b cmd /c "timeout /t 3 /nobreak >nul 2>&1 && start http://127.0.0.1:%MEDIADOWNLOADER_PORT%"
"%PY%" "%ROOT%server.py"
echo.
echo Server stopped. If it exited with an error, scroll up to read it.
pause
"""

README_SHARE = """多媒体下载器 Web 版 · 便携包使用说明
=================================================

【怎么用】
1. 把整个文件夹解压到任意位置（不要放进 C:\\Program Files；路径里尽量不要有中文或空格）。
2. 双击「启动.bat」，等 3 秒会自动打开浏览器 http://127.0.0.1:8765
   黑色窗口是程序本体，下载期间不要关；关掉窗口 = 停止程序。
3. 第一次运行不需要装 Python，依赖都在包里的 runtime\\ 目录内；
   runtime\\ 也自带 pip，之后在程序里点「更新」就够了，不用重新发包。

【端口被占用打不开】
新建一个「改端口启动.bat」，内容两行：
    set MEDIADOWNLOADER_PORT=8899
    启动.bat
然后双击它，访问 http://127.0.0.1:8899

【Cookie / 登录站点】
不配 Cookie 也能用，但 YouTube 会从风控拦你（提示 sign in to confirm you're not a bot），
表现是解析失败或只给 360p —— 这是 YouTube 侧的限制，不是程序坏了，换个网络出口或加 Cookie 就好。
两种加 Cookie 的办法，任选其一：
  A. 设置 → Cookie → 「从浏览器读取」，选你登录过该网站的浏览器。
     读 Chrome 时 Chrome 必须完全退出（它锁着 Cookie 数据库）；Edge / Firefox 不用退。
  B. 把 Netscape 格式的 cookies.txt 直接放进包里的 cookies\\ —— 默认就会去读这个路径，
     不用改任何设置（文件名必须是 cookies.txt）。

【下载目录】
默认在包内 Downloads\\，可在设置里改成别的盘。

【字幕 / 封装 / 重复下载】
- 存储格式选 mkv，成品就是 mkv：即使站点给的是单条 mp4 流，也只做无损「换壳」，不重新编码，画质音质不变。
- 字幕只会嵌站点真实存在的语言（语言码要整码匹配，zh 匹配不到 zh-Hant）。任务日志会写明
  「字幕已写入 N 条 …… 视频没有这些语言，已跳过 ……」，没有字幕不等于功能坏了。
- 想要外挂字幕文件（.vtt，播放器直接加载、不改视频）：下载页勾「写出外挂字幕文件」，
  「嵌入字幕」可勾可不勾 —— 只勾前者就只出文件不塞容器，两个都勾则内嵌并另留一份。
- 开着「跳过已下载」时，同一个视频第二次提交不会重新下载（日志会提示已在下载记录里）。
  要重下就把这个开关关掉。

【订阅追踪（每条订阅单独设规则）】
订阅页每行有「规则」按钮，可以只按这条订阅的口径下载：
- 内容类型（长视频 / 短视频 / 直播 / 音频播客）、时长区间、标题必含词与排除词（逗号分隔）；
- 画质 / 封装 / 命名模板 / 只下音频 / 下载后是否转写，留空都表示跟随全局设置；
- 单次最多入队条数：防止一次涌进几十条，超出的不会丢，下次扫描继续补。
规则只对「设好之后新出现的条目」生效，已经记为见过的旧条目不会回头补下。
运行日志里每次扫描都会写明按哪套规则下了几条、挡掉几条、为什么挡。

【硬字幕烧录（把字幕烧进画面）】
文件列表里视频那一行的「烧字幕」按钮：弹窗里选字幕文件和样式（字号/位置/字体/画质），点「开始烧制」。
- 字幕吃现成的：转写导出的 .srt、双语导出的 .ass、下载页写出的外挂字幕都能用；
  不选就自动取视频旁边同名的那一份，找不到会直接说明原因，不会拿错字幕往画面上烧。
- 输出是新建一个文件「原名.hardsub.mp4」，源视频不动；同一个视频再烧一次要勾「覆盖旧文件」。
- 烧进去的字幕擦不掉（它是画面的一部分），适合投给不支持外挂字幕的播放器或电视。

【音乐下载（歌词/封面/标签）】
需要联网访问 musicdl 支持的源；中文歌歌词走网易云兜底。
musicdl 已经装在包里：页面显示绿色的「● musicdl 已就绪 · v版本号」即可直接用。
要是显示红字（比如对方自己删过 runtime 里的东西），点旁边的「安装 musicdl」就能联网补回来；
已就绪时那个按钮是「更新 musicdl」，走设置里的 PyPI 镜像拉最新版。

【组件与依赖：在程序里更新，不用重新发包】
设置 → 「组件与依赖」：每一项都是绿点（就绪）或红点（未安装），右边就是更新/安装按钮。
- 工具（FFmpeg、yt-dlp、N_m3u8DL-RE）从 GitHub 拉，走设置里的「GitHub/HF 镜像前缀」；
  直连不通会自动依次试内置镜像。
- Python 依赖（musicdl、zhconv、mutagen、edge-tts、deep-translator、numpy、faster-whisper）走包内自带的 pip，
  其中 `zhconv` 用于跨平台按曲名匹配前把歌名/歌手统一成简体，缺了只是退回「繁體歌单匹配不上」的旧行为。
  用设置里的「PyPI 镜像」；该源失败会自动回落到官方源和其它国内镜像。
- 更新过程写在「运行日志」里（能看到用的哪个源、成功没有）。
装完当前进程可能仍用内存里的旧版本：重启一次「启动.bat」即可生效。

【本地语音转写（Whisper）】
包里刻意不带 faster-whisper 和模型（加起来好几 GB），所以初始状态是红的。
现在能直接在程序里补：设置 → 组件与依赖 → faster-whisper 点「安装」（体积大，看网速要等几分钟），
再到「语音/AI」设置里选模型点「获取/更新 Whisper」下载模型。
不想占这个空间的话，用解析页勾选站点自带字幕就够了。

【格式列表里的「≈」】
带 ≈ 的大小是按码率估算的：HLS/m3u8 流不报真实体积，只有 DASH/渐进流是准确值。

【工具位置与一键配置环境变量】
所有外部工具都在这包的 tools\\ 里：ffmpeg / ffprobe / yt-dlp / N_m3u8DL-RE，
程序默认就用它们，不需要你另外安装，也不需要配置任何路径。

想在 cmd / PowerShell 里直接敲 ffmpeg、yt-dlp（比如自己写批处理），
打开 设置 → 「组件与依赖」 → 下面「命令行 PATH」那一块，点「一键加入 PATH」：
只把你的用户 PATH 加上 tools\\ 和 chromaprint\\（后者是 fpcalc 音频指纹工具）这两项，
不动系统 PATH，随时可以点「从 PATH 移除」还原。
加完要重开一个命令行窗口才生效（已经开着的窗口读不到新值）。
Mac / Linux 下这个按钮不会改注册表，只会给你一行 export 命令自己贴到 shell 配置里。

【隐私】
本包不含任何账号信息：没有 config.json、没有 Cookie、没有下载历史，
首次启动会生成一份干净的默认配置。你之前在本机的配置不会被带出去。
"""


def write_launchers(dst: Path, version: str) -> None:
    (dst / "启动.bat").write_bytes(BAT.encode("ascii"))
    (dst / "使用说明.txt").write_text(
        f"版本 v{version}\n\n{README_SHARE}", encoding="utf-8"
    )


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-runtime", action="store_true", help="复用已装好的 runtime")
    ap.add_argument("--no-zip", action="store_true", help="只生成目录不压缩")
    args = ap.parse_args()

    version = app_version()
    name = f"MediaDownloader-{version}-portable"
    dst = DIST / name
    print(f"== 打包 {name} ==")

    if dst.exists():
        if args.skip_runtime:
            for p in dst.iterdir():
                if p.name == "runtime":
                    continue
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        else:
            shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    build_runtime(dst / "runtime", args.skip_runtime)
    copy_app(dst)
    write_bundled_manifest(dst, version)
    write_launchers(dst, version)

    # 复用旧 runtime 时会带着上次试跑生成的字节码目录，纯占体积
    caches = [p for p in dst.rglob("__pycache__") if p.is_dir()]
    for p in caches:
        shutil.rmtree(p, ignore_errors=True)
    if caches:
        print(f"[clean] 清掉 {len(caches)} 个 __pycache__")

    # 自检：先验证包内 pip 能装依赖，再真跑服务，最后确认没把私密文件带出去
    check_module_imports(dst)
    selfupdate_probe(dst)
    smoke_test(dst)
    leaks = [str(p.relative_to(dst)) for p in dst.rglob("*")
             if p.is_file() and (
                 p.name in ("config.json", "cookies.txt", "history.json", "library_cache.json")
                 or p.name == "app.log"
                 or (p.name.startswith("app-") and p.name.endswith(".log")))]
    if leaks:
        raise SystemExit(f"[ABORT] 包里混入私密/本机文件：{leaks}")

    total = dir_size(dst)
    print(f"\n目录大小：{human(total)}")
    for sub in sorted(dst.iterdir()):
        if sub.is_dir():
            print(f"   {sub.name:14s} {human(dir_size(sub))}")

    if not args.no_zip:
        zp = DIST / f"{name}.zip"
        if zp.exists():
            zp.unlink()
        print("\n压缩中…")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(dst.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(DIST))
        print(f"完成：{zp}  {human(zp.stat().st_size)}")


if __name__ == "__main__":
    os.chdir(APP_DIR)
    main()
