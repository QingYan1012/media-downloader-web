r"""剪贴板监听（#206④）：默认关、只问一句、绝不自动入队 —— 这几条都要有读得出来的钉子。

这一功能的风险不在下载，在「程序盯着我复制了什么」：所以自检里除了行为，还专门钉两条口径 ——
① 读到的内容一个字都不许进运行日志（开关本身可以记一行）；
② 界面拿到的是抽出来的那一条链接，不是剪贴板原文，前端也拿不到别的。

全程不碰真剪贴板：`clipboard_text` 被换成脚本喂进去的内容，除最后一条「这台机器上真的读一次」
的可用性检查 —— 那条只比返回类型与一致性，不比内容，也不打印；剪贴板正好是空的也算通过
（空是一句合法的读数，不该借用户复制了什么当夹具）。

跑法：`python tests/clipboard_test.py`
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import server as S  # noqa: E402

_RE_EXC = re.compile(r"^(Traceback|\w*(Error|Exception)\b)")

TOTAL = 0
FAILED: list[str] = []


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if not cond:
        FAILED.append(name)
        print("FAIL", name, " ", extra)
    else:
        print("PASS", name, " ", extra if name.startswith("K0") else "")


class CapCfg:
    def __init__(self, data):
        self.data = data
        self.saved = None

    def save(self):
        self.saved = dict(self.data)


class CapLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))


_REAL_CFG, _REAL_LOG = S.cfg, S.log_mgr
_REAL_CLIP_TEXT = S.clipboard_text      # 桩换掉之后，K18 那两条「真读一次」仍然要走真接口


class _NoYdl:
    def __init__(self, *a, **k):
        raise RuntimeError("offline")


S.yt_dlp_ytdlp = _NoYdl
S.ydl_logger = lambda *a, **k: None
S.FASTAPI_AVAILABLE = False
S.HAS_LIBCRAWLER = False
S.cfg = CapCfg({"download_dir": "downloads"})

LOGS = CapLog()
S.log_mgr = LOGS

YOUTUBE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
MAG = "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=某剧%20S01E02%201080p&tr=http%3A%2F%2Fx%2Fannounce"

# ---------- K1~K6 从剪贴板内容里认链接 ----------
ck("K1 整段就是一条 http 链接：原样认出",
   S.clip_extract_link(YOUTUBE) == YOUTUBE, S.clip_extract_link(YOUTUBE))
ck("K1b 磁力认得到，且只到第一个空白为止（后面跟了说明文字也算同一条）",
   S.clip_extract_link(MAG) == MAG and S.clip_extract_link(MAG + "  这个片子不错") == MAG)
ck("K1c 一句话里夹着链接时抽出那条（分享文案是常态）",
   S.clip_extract_link("看这个 https://b站.example/v/1 很好") == "https://b站.example/v/1",
   S.clip_extract_link("看这个 https://b站.example/v/1 很好"))
ck("K1d 链接尾巴上的中文标点不算进去（复制链接时旁边总跟着个「」或逗号）",
   S.clip_extract_link("https://example.com/a.mkv，谢谢") == "https://example.com/a.mkv"
   and S.clip_extract_link("「https://example.com/a.mkv」") == "https://example.com/a.mkv"
   and S.clip_extract_link("https://example.com/a(1).mkv") == "https://example.com/a(1).mkv",
   S.clip_extract_link("https://example.com/a(1).mkv"))
ck("K1e 没有链接的普通文本、空串、超长的一大段都不算（刨文章里的链接不是这功能要干的事）",
   S.clip_extract_link("今天天气不错") == "" and S.clip_extract_link("") == ""
   and S.clip_extract_link("https://example.com/" + "x" * S.CLIP_TEXT_CAP) == "")
ck("K1f 本机文件路径 / file:// 不接：这条路要用户自己走「种子文件」那一格",
   S.clip_extract_link("file:///H:/Downloads/a.torrent") == ""
   and S.clip_extract_link(r"H:\Downloads\a.torrent") == "")

# ---------- K7~K13 轮询一次的行为：新内容才挂、同一条不重弹 ----------
_FEED = [""]


def _fake_clip():
    return _FEED[0], ""


_old_tick_api = (S.clipboard_text, S._clip_state, S._clip_lock)
S.clipboard_text = _fake_clip


def _reset_state():
    with S._clip_lock:
        S._clip_state.update({"last_key": "", "seen": [], "pending": None,
                              "error": "", "checks": 0, "hits": 0})


_reset_state()
_FEED[0] = YOUTUBE
S._clip_tick()
p1 = S._clip_state["pending"]
ck("K7 复制一条链接后，待定栏里挂上了这一条（带类型和时间，界面才说得出人话）",
   p1 and p1["link"] == YOUTUBE and p1["kind"] == "http" and p1["ts"], str(p1))
ck("K7b 挂的是抽出来的链接，不是剪贴板原文（前端不该拿到用户复制的整段文字）",
   set(p1.keys()) == {"link", "kind", "chars", "ts"}, str(sorted(p1.keys())))
S._clip_tick()
S._clip_tick()
ck("K8 同一条内容反复轮询只弹一次（每 2 秒问一遍，重复弹才是骚扰）",
   S._clip_state["hits"] == 1 and S._clip_state["pending"] == p1, str(S._clip_state))
S._clip_state["pending"] = None
S._clip_tick()
ck("K8b 点了「忽略」之后同一条内容不会又冒出来（seen 里记着这一份）",
   S._clip_state["pending"] is None and S._clip_state["hits"] == 1, str(S._clip_state["hits"]))
_FEED[0] = MAG
S._clip_tick()
ck("K9 换一条磁力：挂上来的类型是 magnet（界面上那句「磁力」才不是假话）",
   S._clip_state["pending"]["kind"] == "magnet", str(S._clip_state["pending"]))
_FEED[0] = "今天写了个脚本"
S._clip_tick()
ck("K10 复制了一段没有链接的文字：什么都不新挂，上一条也原样留着（悄悄消失比留着更糟，用户没法点「忽略」）",
   S._clip_state["pending"]["link"] == MAG, str(S._clip_state["pending"]))
_FEED[0] = "顺手贴一条 " + YOUTUBE
S._clip_tick()
ck("K10b 带上下文的链接照样挂（抽出来的那一条仍是干净的 URL）",
   S._clip_state["pending"]["link"] == YOUTUBE, str(S._clip_state["pending"]))
for i in range(S.CLIP_SEEN_KEEP + 10):
    _FEED[0] = f"https://example.com/{i}.mkv"
    S._clip_tick()
ck("K11 记住的历史有上限，不会一路涨（长期开着也不能把内存当账本）",
   len(S._clip_state["seen"]) <= S.CLIP_SEEN_KEEP, str(len(S._clip_state["seen"])))
_RESET_FEED = [""]


def _clip_err():
    return "", "剪贴板正被别的程序占着，下一次轮询自动再试"


S.clipboard_text = _clip_err
_reset_state()
S._clip_tick()
ck("K12 读不到时把缘故留给界面看，但不挂任何东西、也不抛（下一轮自动再试）",
   S._clip_state["pending"] is None and "占着" in S._clip_state["error"], str(S._clip_state["error"]))
S.clipboard_text = _fake_clip

# ---------- K13~K16 接口层：开关决定给不给，clear 只管翻篇 ----------
_reset_state()
_FEED[0] = YOUTUBE
S._clip_tick()
S.cfg = CapCfg({"download_dir": "downloads", "clipboard_watch": False})
r_off = S.api_clipboard_status()
ck("K13 开关关着时接口回 enabled=false 且不交出待定内容（默认关不是摆设）",
   r_off["ok"] and r_off["enabled"] is False and r_off["pending"] is None, str(r_off))
S.cfg.data["clipboard_watch"] = True
r_on = S.api_clipboard_status()
ck("K13b 打开后同一条还在（服务一直在看，页面开着才有得点）",
   r_on["enabled"] is True and r_on["pending"]["link"] == YOUTUBE, str(r_on))
r_cl = S.api_clipboard_clear()
ck("K14 「忽略 / 加入」之后待定栏清空，接口只回一句成没成",
   r_cl["ok"] and S.api_clipboard_status()["pending"] is None, str(r_cl))
S.cfg.data["clipboard_watch"] = False
LOGS.rows.clear()
S._apply_config({"clipboard_watch": True})
ck("K15 打开开关这一件事记一行日志，且那一行里没有任何剪贴板内容",
   any("剪贴板监听已打开" in m for _l, m in LOGS.rows)
   and not any(YOUTUBE in m or "youtube" in m for _l, m in LOGS.rows), str([m for _l, m in LOGS.rows]))
LOGS.rows.clear()
S._apply_config({"clipboard_watch": False})
ck("K15b 关掉也记一行（谁什么时候让程序盯剪贴板，事后该看得见）",
   any("剪贴板监听已关闭" in m for _l, m in LOGS.rows), str([m for _l, m in LOGS.rows]))
LOGS.rows.clear()
S._apply_config({"clipboard_watch": True, "download_dir": "H:\\别的目录"})
S._apply_config({"clipboard_watch": True})
ck("K15c 开关没变的那一次保存不重复记（日志是给人翻的，不是心跳）",
   sum(1 for _l, m in LOGS.rows if "剪贴板监听" in m) == 1, str([m for _l, m in LOGS.rows]))
ck("K16 界面传来的开关归一成 bool（字符串、None 都能落回真假）",
   S.cfg.data.get("clipboard_watch") is True)

# ---------- K17 后台线程：关着时一次都不读 ----------
_reset_state()
S.cfg = CapCfg({"download_dir": "downloads", "clipboard_watch": False})
S._clip_stop.clear()
S._clip_state["pending"] = None
S.start_clipboard_watch()
time.sleep(2.4)
checks_off = S._clip_state["checks"]
ck("K17 开关关着时，线程醒了也不碰剪贴板（checks 一次没涨）",
   checks_off == 0, str(checks_off))
S.cfg.data["clipboard_watch"] = True
time.sleep(2.4 + S.CLIP_POLL_SEC)
ck("K17b 打开后才开始读，且读到的是一条待定的链接（不是自动入队 —— 这里没有任何任务被创建）",
   S._clip_state["checks"] > 0 and S._clip_state["pending"] is not None
   and len(S.queue.tasks) == 0, str((S._clip_state["checks"], S.queue.tasks)))
S._clip_stop.set()
time.sleep(S.CLIP_POLL_SEC + 0.2)
_after = S._clip_state["checks"]
time.sleep(2.4)
ck("K17c 停止信号能让线程收住（关掉程序不该留一个还在读剪贴板的线程）",
   S._clip_state["checks"] == _after, str((S._clip_state["checks"], _after)))

# ---------- K18 这台机器上真的读一次：只比类型，不比内容 ----------
def _doc_check():
    """把 sys.platform 换成别的系统跑一次：接口不该抛，只该把「这台机器读不了」讲出来。"""
    _sp = sys.platform
    try:
        sys.platform = "linux"
        t, e = _REAL_CLIP_TEXT()
    finally:
        sys.platform = _sp
    assert t == ""
    return e


_reset_state()
_txt, _err = _REAL_CLIP_TEXT()
# 只比类型与一致性，不比内容：剪贴板是用户的东西，自检里既不写也不清。
# 「空剪贴板」是合法读数（回 ("", "")），拿「必须有字或有错」当断言 = 借用户的东西当夹具，
# 用户什么时候复制过什么，不该决定这套自检红不红。
ck("K18 真读一次系统剪贴板：回的是（文字, 缘故）两个字符串，且绝不抛",
   isinstance(_txt, str) and isinstance(_err, str) and not (_txt and _err),
   f"txt={len(_txt)}chars err={_err[:40]!r}")
ck("K18c 读到的缘故（如果有）是一句人话，不是异常名糊上去的",
   not _err or (len(_err) >= 6 and not _RE_EXC.match(_err)),
   f"err={_err[:60]!r}")
ck("K18b 别的系统上这条要说清为什么没得读（口径写死，别让非 Windows 静默失灵）",
   _doc_check().startswith("这一功能只在 Windows"))

S.cfg, S.log_mgr = _REAL_CFG, _REAL_LOG
print("\nTOTAL:", TOTAL, "FAILED:", len(FAILED))
if FAILED:
    print("FAILED:", " | ".join(FAILED))
sys.exit(1 if FAILED else 0)
