#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PO Token 的「两层」说法与那一行组件状态，离线自检。

为什么要有这个文件：上一轮把风控提示里「启用 PO Token」那句改对了以后，这一轮要把
**判断本身**也修对。两件只有读代码 / 跑一次才看得见的缺陷：

1. `_pot_plugin_installed()` 探的是 `bgutil_ytdlp_pot_provider` 这个模块名 —— pip 包
   `bgutil-ytdlp-pot-provider` 落盘的根本不是同名模块，而是
   `yt_dlp_plugins/extractor/getpot_bgutil*.py`。查错名字会把「插件已经装好」一直报成
   「插件没装」，用户照着提示重装一遍，状态不变。
2. 「组件与依赖」不能只看 pip 版本给绿点：这一行点「安装」只装得到插件那层，
   服务端是 tools/bgutil-pot-server 里那个要 node 跑起来的独立服务，两层都通才叫就绪。
   反过来说：两层都绿 = 票取得到，4K 还要「会吃票的客户端（all）」跟上 ——
   上一轮那句「它不解决 4K，缺的是网络出口」是错的结论，别让它再回到文案里。

跑法：PYTHONIOENCODING=utf-8 python tests/potcomponent_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402
import pkg_update as P  # noqa: E402

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
PKG = "bgutil-ytdlp-pot-provider"
URL = "http://127.0.0.1:4416"


def fake_health(val):
    return lambda *a, **k: dict(val)


# ---------- A 插件检测查的名字 ----------
body = SRC.split("def _pot_plugin_installed")[1].split("def ")[0]
ck("A1 检测改探 yt-dlp 真正加载的插件模块", "yt_dlp_plugins.extractor.getpot_bgutil" in body)
ck("A2 探不到的那个假模块名不再留着", "bgutil_ytdlp_pot_provider" not in body)
ck("A3 三个插件入口任一在就算装了（http / script 各一个）",
   "getpot_bgutil_http" in body and "getpot_bgutil_script" in body)

# ---------- B 组件行那一句话：缺哪层说哪层 ----------
n = S._pot_component_note({"installed": False, "ok": False, "detail": "x"},
                          {"po_provider_enabled": True, "po_provider_url": URL})
ck("B1 插件没装：说清「安装」只覆盖插件层", "安装" in n and "pip" in n, n)
ck("B2 插件没装：同时说服务端在 tools/ 里、要靠本机 node", "tools/" in n and "node" in n, n)

n = S._pot_component_note({"installed": True, "ok": False, "detail": "连不上"},
                          {"po_provider_enabled": False, "po_provider_url": URL})
ck("B3 开关关着：说的是关着，而不是「服务没人应答」", "关" in n and "没人应答" not in n, n)

n = S._pot_component_note({"installed": True, "ok": False, "detail": "连不上该地址（服务没启动或端口不对）"},
                          {"po_provider_enabled": True, "po_provider_url": URL})
ck("B4 只差服务端：点名地址并说程序会自己拉（node 不在才拉不起来）",
   URL in n and "没人应答" in n and "node" in n, n)
ck("B5 只差服务端：带上现探到的原因，不写死文案", "服务没启动或端口不对" in n, n)

n = S._pot_component_note({"installed": True, "ok": True, "detail": "HTTP 200"},
                          {"po_provider_enabled": True, "po_provider_url": URL})
ck("B6 两层都齐：说的是「票 + 会吃票的客户端」，不再写成它不解决 4K",
   "all" in n and "不解决 4K" not in n and "缺的是网络出口" not in n, n)
ck("B7 配置整个缺字段也不炸", bool(S._pot_component_note({}, {})))

_cases = [
    ("install", {"installed": False}, {"po_provider_enabled": True, "po_provider_url": URL}),
    ("gate_off", {"installed": True, "ok": False}, {"po_provider_enabled": False, "po_provider_url": URL}),
    ("no_server", {"installed": True, "ok": False, "detail": "x"},
     {"po_provider_enabled": True, "po_provider_url": URL}),
    ("ready", {"installed": True, "ok": True}, {"po_provider_enabled": True, "po_provider_url": URL}),
]
_states = [S._pot_component_note_state(po, cfg)[0] for _, po, cfg in _cases]
ck("B8 四种情形各有一个语言无关的状态码（英文界面据此取词表那句）",
   _states == [x[0] for x in _cases], str(_states))
ck("B9 no_server 的状态码带着地址与现探到的原因",
   S._pot_component_note_state({"installed": True, "ok": False, "detail": "连不上"},
                               {"po_provider_enabled": True, "po_provider_url": URL})[1]
   == {"url": URL, "detail": "连不上", "dir": S.POT_SERVER_DIR_NAME})

# ---------- C 组件行的 ok 判定 ----------
row = {"key": PKG, "pkg": PKG, "label": "x", "active": "2.0.2", "ok": True}
cfg = {"po_provider_enabled": True, "po_provider_url": URL}
_orig_installed = S._pot_plugin_installed
_orig_health = S.po_token_health
try:
    S._pot_plugin_installed = lambda: False
    S.po_token_health = fake_health({"ok": True, "installed": False, "detail": "HTTP 200"})
    r = S._pot_row_extra(dict(row), cfg)
    ck("C1 插件没装：pip 版本再全也不给绿点（服务端通着也没用）", r["ok"] is False, str(r))

    S._pot_plugin_installed = lambda: True
    S.po_token_health = fake_health({"ok": False, "installed": True, "detail": "连不上该地址（服务没启动或端口不对）"})
    r = S._pot_row_extra(dict(row), cfg)
    ck("C2 服务端没起：不给绿点", r["ok"] is False and "缺的是服务端" in r["note"], str(r))

    S.po_token_health = fake_health({"ok": True, "installed": True, "detail": "HTTP 200"})
    r = S._pot_row_extra(dict(row), cfg)
    ck("C3 插件 + 开关 + 服务三层都齐才转绿", r["ok"] is True and "都通了" in r["note"], str(r))

    r = S._pot_row_extra(dict(row), {"po_provider_enabled": False, "po_provider_url": URL})
    ck("C4 开关关着不算就绪（关着就不去取票）", r["ok"] is False and "关" in r["note"], str(r))

    S._pot_plugin_installed = lambda: False
    r = S._pot_row_extra(dict(row), cfg, {"ok": True, "installed": True, "detail": "HTTP 200"})
    ck("C5 传进来的那份 installed 是缓存旧值时现查，不照抄", r["ok"] is False and "安装" in r["note"], str(r))

    other = {"key": "mutagen", "pkg": "mutagen", "ok": True}
    ck("C6 别的行一律不动（不塞 note、不改 ok）", S._pot_row_extra(dict(other), cfg) == dict(other))
    ck("C7 POT 那行交给「一键更新」跳过（缺的是服务端，替人装插件没意义）",
       S._pot_row_extra(dict(row), cfg).get("skip_all") is True)
finally:
    S._pot_plugin_installed = _orig_installed
    S.po_token_health = _orig_health

# ---------- D 风控卡：票没问题时要收口 ----------
t = S._po_ready_tip({"ok": True}, {"po_provider_url": URL})
ck("D1 票这层通着：说清 all 也试过了，仍没有更高的档位", "all" in t and "仍没有更高的档位" in t, t)
ck("D2 并且不再教人去动那个已经开好的开关", "启用 PO Token" not in t and "门控" not in t, t)
ck("D3 地址取自己配的，不写死", URL not in S._po_ready_tip({"ok": True}, {"po_provider_url": "http://127.0.0.1:9999"}))
ck("D4 缺字段也不炸", isinstance(S._po_ready_tip({}, {}), str))

formats = [{"is_video": True, "has_audio": True, "height": 1080, "format_id": "18"},
           {"is_video": True, "has_audio": True, "height": 720, "format_id": "92"}]
S.po_token_health = fake_health({"ok": True, "installed": True, "detail": "HTTP 200"})
try:
    gate = S._format_gate_note("youtube", formats, ["default"],
                               {"po_provider_enabled": True, "po_provider_url": URL}, "u")
    tips = gate.get("tips") or []
    ck("D5 票通着仍被裁：提示里有「这一层是通的」，不是干脆不提",
       gate.get("limited") and any("PO Token 这一层是通的" in x for x in tips), str(tips))
    ck("D6 票通着时不再教人去开 PO Token（老文案彻底不走这条路）",
       not any(("启用 PO Token" in x or "PO Token 服务门控" in x) for x in tips), str(tips))

    S.po_token_health = fake_health({"ok": False, "installed": True, "detail": "连不上该地址（服务没启动或端口不对）"})
    gate = S._format_gate_note("youtube", formats, ["default"],
                               {"po_provider_enabled": True, "po_provider_url": URL}, "u")
    tips = gate.get("tips") or []
    ck("D7 票不通时仍指服务端，不混进「通的」那句",
       any("没人应答" in x for x in tips) and not any("这一层是通的" in x for x in tips), str(tips))
finally:
    S.po_token_health = _orig_health

# ---------- E 接线 ----------
seg = SRC[SRC.index("def _component_rows"):SRC.index('@app.get("/api/components")')]
ck("E1 组件表逐行过 _pot_row_extra", "_pot_row_extra(row, cfg.data)" in seg)
ck("E2 PIP_PACKAGES 确实有这条（否则 /api/update/pkg 白名单不认它）",
   any(p["name"] == PKG for p in P.PIP_PACKAGES))
ck("E3 风控卡那条改走 _po_ready_tip", "tips.append(_po_ready_tip(po, cfg or {}))" in SRC)
_html = Path("static/index.html").read_text(encoding="utf-8")
ck("E4 界面那行按 note_state 取词表，不再直出后端中文 note",
   "{{ compNote(it) }}" in _html and "const COMP_NOTE_KEYS = {" in _html
   and "{{ it.note }}" not in _html)

print(f"\nTOTAL {TOTAL}  FAILED {len(FAILED)}"
      + ("" if not FAILED else "  ==> " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
