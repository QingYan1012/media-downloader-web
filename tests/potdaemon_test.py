#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PO Token 服务端的「常驻」与解析的「补试 all」，离线自检。

为什么要加这个文件：上一轮把 4K 丢了的原因归给了「网络出口」，结论是错的 ——
10-13 实测：同一条视频，票在 + 用 all 客户端 = 38 条 / 4320p / 23 条独立视频轨；
票在但只用 default,web_safari = 11 条 / 1080p / 零分流；票停再用 all 也掉回 11 条。
所以「票」和「会吃票的客户端」两样都要，而这两样都得是程序自己管得住的：

1. 服务端不能再只活在临时目录里（重启机器就没了，界面那行永远灰）。它挪到了
   tools/bgutil-pot-server/，探测到端口空着时由 pot_daemon 用本机 node 补拉一次。
   这一层的安全边界要钉死：只允许 127.0.0.1 / localhost / ::1，指向别的地址一律不动手。
2. 解析不能拿着「没有独立视频轨」的清单就收工。后面还排着 all 那次尝试时，这一份只能当兜底。

跑法：PYTHONIOENCODING=utf-8 python tests/potdaemon_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402
import pot_daemon as D  # noqa: E402

FAILED = []
TOTAL = 0


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}" + (f"  [{extra}]" if extra else ""))
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{extra}]")


SRC = Path(S.__file__).read_text(encoding="utf-8")
APP = Path(S.__file__).resolve().parent
LOCAL = "http://127.0.0.1:4416"


# ---------- A 端口 / 归属：只管本机 ----------
ck("A1 本机地址认得出端口", D.local_port(LOCAL) == 4416)
ck("A2 localhost / ::1 也算本机", D.local_port("http://localhost:4416") == 4416
   and D.local_port("http://[::1]:4416") == 4416)
ck("A3 没写端口用默认 4416", D.local_port("http://127.0.0.1") == D.DEFAULT_PORT)
ck("A4 远程地址一律不自动拉起（返回 None 让上层照实报）",
   D.local_port("http://192.168.1.20:4416") is None
   and D.local_port("http://pot.example.com:4416") is None, D.local_port("http://pot.example.com:4416"))
ck("A5 空地址不当本机处理", D.local_port("") is None)

# ---------- B 服务端文件就在 tools/ 里（常驻，不是临时目录） ----------
ck("B1 目录约定是 tools/bgutil-pot-server",
   D.server_dir(APP) == APP / "tools" / "bgutil-pot-server")
ck("B2 入口是编译产物 build/main.js",
   D.entry_file(APP) == APP / "tools" / "bgutil-pot-server" / "build" / "main.js")
ck("B3 本机这份真的在（不是只写了个路径规则）", D.ready(APP), str(D.entry_file(APP)))
ck("B4 随包 tools 清单里没有它：130+ MB 的 node 依赖不进分享包",
   "bgutil-pot-server" not in Path("pack_release.py").read_text(encoding="utf-8"))
import pack_release as PKG  # noqa: E402
ck("B5 pot_daemon.py 本身要在 APP_PY 里：漏了它，包里的「程序代起」只剩一句自动拉起失败",
   "pot_daemon.py" in PKG.APP_PY, str(PKG.APP_PY))

# ---------- C ensure_running 的每条分支都给出「缺的是哪一层」 ----------
_orig_node, _orig_missing = D.node_bin, D._NODE_MISSING
try:
    got, why = D.ensure_running(url=LOCAL, app_dir=APP, ping=lambda: True, log=lambda m: None)
    ck("C1 已经在听就什么都不做", got is True and "已在运行" in why, why)

    D._NODE_MISSING = False
    got, why = D.ensure_running(url="http://10.20.30.40:4416", app_dir=APP,
                                ping=lambda: False, log=lambda m: None)
    ck("C2 非本机地址：拒绝启动并说清只管本机", got is False and "本机" in why, why)

    got, why = D.ensure_running(url=LOCAL, app_dir=Path("Z:/没有这个目录"),
                                ping=lambda: False, log=lambda m: None)
    ck("C3 服务端文件不在：说清缺的是 build/main.js 这一层",
       got is False and "build/main.js" in why and "tools/" in why, why)

    D.node_bin = lambda: ""
    got, why = D.ensure_running(url=LOCAL, app_dir=APP, ping=lambda: False, log=lambda m: None)
    ck("C4 没有 node：说的是缺 node，不是含糊的「启动失败」",
       got is False and "node" in why, why)
    ck("C5 没有 node 这件事记一次，后续不再反复重试 Popen", D._NODE_MISSING is True)

    D._NODE_MISSING = False
    D.node_bin = _orig_node
    # 用 4499 这个空端口跑「拉了但等不应答」这条路：4416 上真有一个在听的，端口号要能和它区分开
    got, why = D.ensure_running(url="http://127.0.0.1:4499", app_dir=APP, ping=lambda: False,
                                log=lambda m: None, wait_sec=1)
    ck("C6 起了但等不到应答：端口号写进话里并指日志文件",
       got is False and "pot_daemon.log" in why and "4499" in why, why)
    D.shutdown()
finally:
    D.node_bin, D._NODE_MISSING = _orig_node, _orig_missing

st = D.status(APP)
ck("C7 status 把「文件在不在 / node 在哪 / 谁起的」一次给全",
   {"dir_exists", "node", "owned", "pid", "alive"} <= set(st), str(st))
ck("C8 owned() 没起进程时是干净的 False，不假装有权收掉别人的服务",
   D.owned()["owned"] is False and D.owned()["pid"] is None, str(D.owned()))

# ---------- D 探测失败时的自愈接线：只在「没人应答」这一种原因下补拉 ----------
seg = SRC[SRC.index("def po_token_health"):SRC.index("# ---------- 自定义 yt-dlp 参数")]
ck("D1 探测异常里认出「连不上该地址」才补拉", '"连不上该地址" in detail' in seg)
ck("D2 补拉走 pot_daemon.ensure_running", "pot_daemon.ensure_running(" in seg)
ck("D3 补拉成功那句要说明是程序代起的", "程序代起" in seg)
ck("D4 HTTP 200 但内容不对时不去乱起（只有连不上才补）",
   seg.index('ok = r.status_code == 200') < seg.index('detail = _po_err_cn(e)'))
ck("D5 ping 用的是配置里的地址，不写死 4416", "_po_ping_ok(url, timeout)" in seg)

boot = SRC[SRC.index("def _boot_pot_server"):SRC.index("def _boot_pot_server") + 900]
ck("D6 启动时门控关着就不拉（不替人做主）", 'po_provider_enabled' in boot and "return" in boot)
ck("D7 退出时只收程序自己起的那个", "_pot_daemon_stop" in SRC and "pot_daemon.owned()" in SRC)

# ---------- E 解析的「补试 all」：没分流的清单不算数 ----------
ck("E1 补试只排在票取得到的时候（没票时试 all 是白费一遍网络）",
   S._yt_widen_attempt({"po_provider_enabled": False}) == []
   and S._yt_widen_attempt({}) == [])
_orig_health = S.po_token_health
try:
    S.po_token_health = lambda *a, **k: {"ok": True, "installed": True, "detail": "HTTP 200"}
    ck("E2 票通着 + 门控开着 = 排一次 all", S._yt_widen_attempt({"po_provider_enabled": True}) == [["all"]])
    S.po_token_health = lambda *a, **k: {"ok": False, "installed": True, "detail": "连不上"}
    ck("E3 票取不到就不排 all（省一趟 12s 超时）",
       S._yt_widen_attempt({"po_provider_enabled": True}) == [])
finally:
    S.po_token_health = _orig_health

PROG = [{"format_id": "18", "height": 1080, "vcodec": "avc1", "acodec": "mp4a"},
        {"format_id": "140", "height": 0, "vcodec": "none", "acodec": "mp4a"}]
DASH = [{"format_id": "313", "height": 2160, "vcodec": "vp9", "acodec": "none"},
        {"format_id": "140", "height": 0, "vcodec": "none", "acodec": "mp4a"}]
ck("E4 全是影音同条时判成「被裁」", S._yt_has_dash(PROG) is False)
ck("E5 有独立视频轨时判成「没被裁」", S._yt_has_dash(DASH) is True)
ck("E6 空清单不炸", S._yt_has_dash([]) is False and S._yt_max_h([]) == 0)
ck("E7 取最高档位认 resolution 字符串（有些客户端不给 height）",
   S._yt_max_h([{"format_id": "x", "resolution": "1920x1080"}]) == 1080)
ck("E8 兜底那份取的是「最高的」，不是「最后一个」", S._yt_max_h(DASH) > S._yt_max_h(PROG))

_i = SRC.index("for ci, clients in enumerate(client_tries)")
loop = SRC[_i:_i + 6000]
ck("E9 接受条件里加了「后面还排着 all 就先不收」",
   "widen_pending and not _yt_has_dash(fmts)" in loop)
ck("E10 不收的那份留成兜底，不是丢掉", "_keep_best(info)" in loop)
ck("E11 兜底放在每次调用自己的盒子里，并发解析不互相盖",
   "fb_box = [None]" in SRC and "self._info_fallback" not in SRC)
ck("E12 日志说的是「带票的 all 还没试」，人能看出程序在干什么",
   "还没试，重解一遍取优" in loop)

# ---------- F 下载沿用解析那套客户端（不静默降质） ----------
dl = SRC[SRC.index("elif is_yt and not audio_only:"):SRC.index("is_pl_info = bool(info)")]
ck("F1 解析来自宽客户端时不再被设置里的窄链覆盖", "wide = bool(clients)" in dl and "if wide:" in dl)
ck("F2 日志说清「下载沿用同一套客户端」", "下载沿用同一套客户端" in dl)
ck("F3 窄链那条路还在（错误轮换靠它），只是排在 wide 之后", "elif pc_chain:" in dl)

# ---------- G 格式表达式：高度上限要挂在每一个备选上 ----------
# 编解码偏好本身是 "[vcodec*=av01]/[vcodec*=av1]" 这种 / 串联，整串拼进 bv*…[height<=2160]
# 时上限只落在最后一个备选上，第一个备选成了「不限高度的 AV1」。
# 10-13 实测：界面选 4K，下出来是 7680x4320 / 519.8 MB 的那个文件就是这么来的。
Eng = S.DownloaderEngine
fa = Eng._resolve_format([], "4K", "best", False, "av1")
bad = [a for a in fa.split("/") if a.startswith("bv*[vcodec") and "[height<=" not in a]
ck("G1 4K + AV1：每个带编解码偏好的备选都各自带高度上限", not bad, str(bad))
ck("G2 表达式里不再出现「不限高度的 AV1」", "bv*[vcodec*=av01]+" not in fa, fa)
f1 = Eng._resolve_format([], "1080p", "best", False, "avc")
ck("G3 1080p + AVC 同理（低档请求不能被第一个备选顶到上面去）",
   not [a for a in f1.split("/") if a.startswith("bv*[vcodec") and "[height<=1080]" not in a], f1)
ck("G4 高度上限就是用户点的那一档", "[height<=2160]" in fa and "[height<=1080]" in f1)
ck("G5 末尾的兜底还在（源里真没有分流时仍能下完，不报无解）", fa.rstrip("/").endswith("bv*+ba/b"))
ck("G6 音质档位照样生效：abr 上限紧跟在合并表达式后",
   "[abr<=128]" in Eng._resolve_format([], "4K", "128k", False, "auto"))
ck("G7 没选编解码偏好时不冒出空的备选段（不变成 bv*+ba//…）", "//" not in Eng._resolve_format([], "4K", "best", False, "auto"))

print(f"\nTOTAL {TOTAL}  FAILED {len(FAILED)}"
      + ("" if not FAILED else "  ==> " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
