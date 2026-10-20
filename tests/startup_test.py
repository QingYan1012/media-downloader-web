r"""启动这段控制台输出别再让人误判「卡住」：端口预检说清是谁占着，就绪那行按真答过话打。

起因：这台程序启动成功后，控制台永远只有那四行横幅 —— uvicorn 的「Uvicorn running on」是 INFO，
被 main() 里的 log_level="warning" 压掉了；而端口被占时它抛的是一句 Errno 10048。
两种情况看着一模一样，用户拿截图问「是不是卡住了」，实测下来健康那台 2.1 秒就在服务了，
控制台却一个字都没多。这一批把两头都补上话：启动前先试绑一次，占着就分「本程序已开着一台」
和「别的程序占着」两种说清并以退出码 1 结束；横幅之后由 /api/health 真答过话再打「服务已就绪」。

跑法：`python tests/startup_test.py`（A/B 组在本进程里判形状，C 组真起三台实例）。
C 组每台都带自己的 MEDIADOWNLOADER_STATE_DIR，绝不写仓库的 app.log / config.json；
library_cache.json 钉在 APP_DIR、任何实例都会重写它，所以起之前备份、跑完按字节还原。
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import threading
import time
import urllib.request

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import server as S  # noqa: E402

ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_startup_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def hold_port():
    """占着一个端口当「别的程序」：只 listen，绝不答 /api/health。"""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest() if p.is_file() else "-"


# ---------------------------------------------------------------- A. 三个新函数的行为
print("== A. 预检与探针：认「地址被占」和认「是本程序另一台」是两件事 ==")
ck("A1 绑 0.0.0.0 / :: / * 时探针地址换成 127.0.0.1（拿监听地址当客户端目标连不上）",
   all(S._probe_host(h) == "127.0.0.1" for h in ("0.0.0.0", "::", "*", "", "  "))
   and S._probe_host("localhost") == "localhost",
   str([S._probe_host(h) for h in ("0.0.0.0", "::", "*", "", "localhost")]))
p_idle = free_port()
ck("A2 没人用的端口：port_taken 说不占", S.port_taken("127.0.0.1", p_idle) is False, str(p_idle))
sock_busy, p_busy = hold_port()
ck("A3 有人 listen 的端口：port_taken 说占", S.port_taken("127.0.0.1", p_busy) is True, str(p_busy))
ck("A4 占着的是裸 socket（不是本程序）：port_taken_by_us 认不出来，别乱说「用原来那台」",
   S.port_taken_by_us("127.0.0.1", p_busy) is False)


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = b'{"ok": true, "running": false, "pending": 0}' if self.path == "/api/health" else b'{}'
        self.send_response(200 if self.path == "/api/health" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


fake = http.server.HTTPServer(("127.0.0.1", 0), _HealthHandler)
threading.Thread(target=fake.serve_forever, daemon=True).start()
p_fake = fake.server_address[1]
ck("A5 答 /api/health {ok:true} 的才算本程序另一台", S.port_taken_by_us("127.0.0.1", p_fake) is True)
fake.shutdown()
sock_busy.close()

# ---------------------------------------------------------------- B. main() 的接线
print("== B. 接线顺序：预检在起服务之前，就绪那行在横幅之后 ==")
SRC = (APP / "server.py").read_text(encoding="utf-8")
main_src = SRC[SRC.index("def main():"):]
i_host = main_src.index('MEDIADOWNLOADER_HOST')
i_taken = main_src.index("if port_taken(host, port):")
i_exit = main_src.index("raise SystemExit(1)")
i_banner = main_src.index('print("  多媒体下载器 Web 版 (Element Plus)")')
i_announce = main_src.index("_boot_ready_announcer(host, port)")
i_run = main_src.index("_UVICORN_SERVER.run()")
ck("B1 端口/host 解析在预检之前（预检要知道撞的是哪个端口）", 0 < i_host < i_taken, f"{i_host}<{i_taken}")
ck("B2 预检在横幅与 uvicorn 起服务之前：占着就别半启动（线程、aria2 都还没拉起）",
   i_taken < i_banner < i_run, f"{i_taken}<{i_banner}<{i_run}")
ck("B3 撞端口那支以退出码 1 结束（.bat 窗口里留着那句，不靠人看控制台）",
   i_taken < i_exit < i_banner, f"{i_taken}<{i_exit}")
ck("B4 就绪那行是横幅之后由探针打的（横幅在绑定之前，光看它不知道端口起来没有）",
   i_banner < i_announce < i_run, f"{i_banner}<{i_announce}<{i_run}")
ck("B5 探针问的是 /api/health 不是 /api/status（后者会真跑 ffmpeg --version、扫 Whisper 目录）",
   '/api/health' in SRC[SRC.index("def port_taken_by_us"):SRC.index("def _boot_ready_announcer")]
   and '/api/status' not in SRC[SRC.index("def port_taken_by_us"):SRC.index("def _boot_ready_announcer")])
ck("B6 errno 在模块顶部就 import 了（OSError 分支一走才碰到它，漏了就 NameError 白修）",
   "\nimport errno\n" in SRC[:SRC.index("def main():")])
ck("B7 预检只认「地址被占」这一类错，别的错留给 uvicorn 自己报",
   "errno.EADDRINUSE" in SRC and "别在这里替它下结论" in SRC)
ck("B8 撞端口那句也写进运行日志（只有控制台话的话，事后查不到这台为什么没起来）",
   'log_mgr.log("端口 %d 已被占用' in main_src[:i_banner])
health_line = 'def api_health' 
ck("B9 /api/health 确实是个只读探针（这几项断言靠它答话，它自己要很重就本末倒置）",
   health_line in SRC and "别用 /api/status 当探针" in SRC)

# ---------------------------------------------------------------- C. 真起实例
print("== C. 真进程 A/B：健康那台会打「服务已就绪」，撞端口那台说清是谁占着 ==")
CACHE = APP / "library_cache.json"
CACHE_BAK = SHARD / "library_cache.json.bak"
if CACHE.is_file():
    CACHE_BAK.write_bytes(CACHE.read_bytes())
LOG_BEFORE = md5(APP / "app.log")
CFG_BEFORE = md5(APP / "config.json")
kids: list[subprocess.Popen] = []


def spawn(tag: str, port: int) -> subprocess.Popen:
    state = SHARD / tag / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "config.json").write_text(json.dumps({
        "download_dir": str(SHARD / tag / "downloads"),
        "aria2_autostart": False, "web_auth_enabled": False,
        "telegram_enabled": False, "components_auto_check": False,
        "po_provider_enabled": False, "clipboard_watch": False,
    }), encoding="utf-8")
    (SHARD / tag / "downloads").mkdir(exist_ok=True)
    env = dict(os.environ, MEDIADOWNLOADER_STATE_DIR=str(state),
               MEDIADOWNLOADER_PORT=str(port), PYTHONIOENCODING="utf-8",
               PYTHONUNBUFFERED="1")
    out = open(SHARD / ("%s.out" % tag), "wb")
    p = subprocess.Popen([sys.executable, str(APP / "server.py")], cwd=str(APP),
                         env=env, stdout=out, stderr=subprocess.STDOUT)
    kids.append(p)
    return p


def console(tag: str) -> str:
    f = SHARD / ("%s.out" % tag)
    return f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""


def served(port: int, timeout_s: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/api/health" % port, timeout=2) as r:
                if r.status == 200 and json.loads(r.read().decode()).get("ok"):
                    return True
        except Exception:
            time.sleep(0.5)
    return False


port_ok = free_port()
a = spawn("A", port_ok)
ok_a = served(port_ok)
# 「服务已就绪」由探针线程打，最多等它 15 秒
for _ in range(30):
    if "服务已就绪" in console("A"):
        break
    time.sleep(0.5)
ck("C1 空闲端口那台真的起来了（预检没把正常启动拦掉）", ok_a, "port=%d" % port_ok)
ck("C2 它的控制台在横幅之后补了一行「服务已就绪」，健康启动不再只有四行",
   "服务已就绪" in console("A"), repr(console("A").splitlines()[-1][:40]) if console("A") else "空")
ck("C3 就绪那行排在横幅之后（横幅在绑定之前，顺序反了就是假话）",
   console("A").find("打开浏览器访问") < console("A").find("服务已就绪"))

b = spawn("B", port_ok)
rc_b = None
for _ in range(60):
    if b.poll() is not None:
        rc_b = b.returncode
        break
    time.sleep(0.5)
ck("C4 撞同一个端口的第二台自己退出了（不再留一个看着像卡住的窗口）",
   rc_b == 1, "退出码=%s" % rc_b)
ck("C5 它说的是「已经开着一个多媒体下载器」并给出原来那个地址（这种情况该劝人用原来那台）",
   "已经开着一个多媒体下载器" in console("B") and str(port_ok) in console("B"),
   repr(console("B")[-120:]))
ck("C6 它还说了换端口的办法（MEDIADOWNLOADER_PORT）", "MEDIADOWNLOADER_PORT" in console("B"))
ck("C7 第二台退出后，第一台仍在服务（预检不该碰到别人的实例）", served(port_ok, timeout_s=5))

sock_other, p_other = hold_port()
c = spawn("C", p_other)
rc_c = None
for _ in range(60):
    if c.poll() is not None:
        rc_c = c.returncode
        break
    time.sleep(0.5)
sock_other.close()
ck("C8 端口被「别的程序」占着时说的是另一种话（不误导人去找一个下载器实例）",
   rc_c == 1 and "被别的程序占着" in console("C"), repr(console("C")[-120:]))

for p in kids:
    if p.poll() is None:
        p.terminate()
time.sleep(3)
for p in kids:
    if p.poll() is None:
        p.kill()
if CACHE_BAK.is_file():
    CACHE.write_bytes(CACHE_BAK.read_bytes())
ck("C9 这三台都没往仓库的 app.log / config.json 写一个字（各自带 STATE_DIR）",
   md5(APP / "app.log") == LOG_BEFORE and md5(APP / "config.json") == CFG_BEFORE,
   "app.log %s→%s" % (LOG_BEFORE[:8], md5(APP / "app.log")[:8]))
ck("C10 library_cache.json 已按备份还原（它钉在 APP_DIR，实例一定会写它）",
   (not CACHE_BAK.is_file()) or md5(CACHE) == md5(CACHE_BAK))

print("\nFAILED: " + ("none" if not FAILED else " | ".join(FAILED)))
sys.exit(1 if FAILED else 0)
