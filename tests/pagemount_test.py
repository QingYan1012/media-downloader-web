# -*- coding: utf-8 -*-
r"""页面挂载闸门：一次按键的重画只该付当前页的钱。

起因（2026-10-17 实测）：17 个页面块一直是 v-show，全部常驻 DOM；资源库又在开机就扫，
每行还带一个 el-select（连同 teleport 出去的整份预设选项）。60 个成品时，主工作树那份
在首页敲一个字要 24.5 ms（节点 6653 / el-select 91），早超了一帧的 16.7 ms，所以「每个页面都卡」。
改成只挂当前页 + 资源库进页才读 + 行内原生 select 后，同一把探针量到 2.0 ms（节点 564）。
这三条都是能被顺手改回去的，所以钉在这里。

跑法：`python tests/pagemount_test.py`（纯读文件，不起 server）。
"""
from __future__ import annotations

import pathlib
import re
import sys

HTML = (pathlib.Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


PAGES = ["home", "queue", "bt", "sniff", "info", "search", "music", "tg", "live", "voice",
         "library", "files", "favs", "history", "subs", "log", "settings"]

blocks = {p: bool(re.search(r'<div v-(if|show)="page === \'%s\'">' % p, HTML)) for p in PAGES}
ck("P1 17 个页面块都在，且一个不漏用 v-if",
   all(blocks.values()) and 'v-show="page === ' not in HTML,
   str([p for p, ok in blocks.items() if not ok]))

boot = HTML[HTML.find("onMounted(async () => {"):HTML.find("onMounted(async () => {") + 4000]
ck("P2 开机不再扫资源库（它只服务一页，却给每页垫了 50 行）", "loadLibrary" not in boot)
ck("P3 开机仍预取订阅计数（顶栏角标要它，别跟着一起删）", "loadSubs()" in boot)

watch_body = HTML[HTML.find("watch(page, (p) => {"):HTML.find("watch(tgMode")]
ck("P4 进资源库那一页才读一次", "if (p === 'library') loadLibrary(false);" in watch_body)
ck("P5 离开页面先把预览播放器停下（v-if 会连节点一起摘掉，声音却不会自己停）",
   "mediaEl.value" in watch_body and ".pause()" in watch_body)

LIB_MARK = '<div class="lib-transcode">'
cell = HTML[HTML.find(LIB_MARK):HTML.find(LIB_MARK) + 600]
ck("P6 资源库行内下拉是原生 select，不是 el-select",
   "<select v-model=\"it._preset\">" in cell and "el-select" not in cell, cell[:80])
ck("P7 原生下拉留了箭头的位置（右侧 padding 比左侧重）",
   re.search(r"\.lib-transcode select\s*\{[^}]*padding:\s*0 20px 0 6px", HTML) is not None)

# 文件页那一行「更多」里 15 项全靠 v-if 按文件类型增减，分组线只能挂在「确有前族」的组首上。
# Element Plus 2.8.8 的 divided 是给这一项前面另插一个 <li role="separator">，
# 所以线挂错地方 = 菜单顶上凭空一条，源码看不出来（2026-10-18 沙箱逐类文件量过）。
_FM_MARK = '<el-dropdown v-if="!row.is_dir && (isMediaFile(row) || isSrtFile(row) || isAudioFile(row))"'
_fm_at = HTML.find(_FM_MARK)
_fm = HTML[_fm_at:HTML.find("</el-dropdown-menu>", _fm_at)] if _fm_at >= 0 else ""
# 只数挂在项上的，别把讲这段话的注释也算进去
_fm_items = [l for l in _fm.splitlines() if l.strip().startswith("<el-dropdown-item")]
_fm_div = [l.strip()[:120] for l in _fm_items if re.search(r"(?::divided=|\sdivided(?!=))", l)]
ck("P8 文件页行内下拉的分组线只挂在五个组首（流水线 / 分离人声 / 配音 / 烧录字幕 / Picard）",
   len(_fm_div) == 5 and len(_fm_items) == 15,
   "项 %d，带线 %d：%s" % (len(_fm_items), len(_fm_div), [d.split("command=")[0].strip()[:40] for d in _fm_div]))
ck("P9 Picard 那条线是条件的：flac/ogg/wma/opus 不在 isMediaFile 里，这类行的菜单从 Picard 开头，写死就悬空一条",
   ':divided="isMediaFile(row)"' in _fm
   and re.search(r'v-if="isAudioFile\(row\)"\s+divided\b', _fm) is None)

# ---- #71 侧栏折叠 ----
# 折叠只改一个 CSS 变量，宽度、主区让位、过渡全跟着它走；
# 一旦有人把 212/64 写死在两条规则里，折叠就变成「图标挤在一块儿，主区宽度不动」。
_SB_W = re.search(r"\.sidebar\s*\{[^}]*width:\s*var\(--sidebar-w\)", HTML)
ck("P10 侧栏宽度仍只由 --sidebar-w 一处决定，折叠是在同一个元素上改这个变量",
   _SB_W is not None and ".sidebar.is-collapsed { --sidebar-w: 64px; }" in HTML
   and not re.search(r"\.sidebar(\.is-collapsed)?\s*\{[^}]*width:\s*\d+px", HTML),
   "找到 %r" % (_SB_W.group(0)[-40:] if _SB_W else None))
# navCollapsed 漏在 setup 返回清单里 = 按钮点不动、界面上什么都不显示，且不报错
ck("P11 navCollapsed 有声明、在返回清单里、且记在浏览器本地（漏任一处都是静默失效）",
   "const navCollapsed = ref(" in HTML
   and re.search(r"return \{[^}]*\bpage, navCollapsed, navs\b", HTML) is not None
   and "localStorage.getItem('md_nav_collapsed')" in HTML
   and "localStorage.setItem('md_nav_collapsed'" in HTML)
# 折叠态收起分组标题，换成组间一条线：5 组 4 条、第一组顶上不留（沙箱 2026-10-18 量过）
ck("P12 折叠态的分组线默认不显示、只在折叠时出现，且第一条不画（v-if=gi > 0）",
   ".nav-group-line { display: none;" in HTML
   and ".sidebar.is-collapsed .nav-group-line { display: block; }" in HTML
   and '<div v-if="gi > 0" class="nav-group-line"></div>' in HTML)

# ---- #72 Ctrl+K 面板 ----
# 模板是 in-DOM 的，setup 返回清单里漏一个名字不是「那一块不显示」，是整页渲染抛错。
# I7 那类闸门只覆盖登记过的页面块，面板挂在 .layout 上、不在任何页块里，所以这里自己钉。
_PALETTE_NAMES = ["palette", "paletteInput", "paletteRows", "paletteGroups",
                  "kbdMod", "openPalette", "closePalette", "runPalette"]
_ret = HTML[HTML.rindex("return {"):]
ck("P13 面板用到的每个名字都在 setup 的返回清单里（漏一个 = 整页空白且只在建应用时才报）",
   all(re.search(r"\b%s\b" % n, _ret) for n in _PALETTE_NAMES),
   str([n for n in _PALETTE_NAMES if not re.search(r"\b%s\b" % n, _ret)]))
ck("P14 Ctrl+K 的监听挂了也必须摘（挂 in-DOM 模板上没人替你清）",
   "window.addEventListener('keydown', onPaletteKey)" in HTML
   and "window.removeEventListener('keydown', onPaletteKey)" in HTML)
# position:fixed 的祖先一旦带 transform / filter / backdrop-filter，包含块就变成那个祖先，
# 面板会歪进那一格里 —— 这条不是洁癖，是这类弹层最贵的坑（.card 就带 backdrop-filter）。
ck("P15 面板的祖先（#app / .layout）身上没有 transform 与 backdrop-filter",
   re.search(r"\.layout\s*\{[^}]*?(?:transform|backdrop-filter)", HTML) is None
   and re.search(r"html, body, #app\s*\{[^}]*?(?:transform|backdrop-filter)", HTML) is None)
# 别名表只拿去匹配、界面上一个都不显示；键写错（多个字、少个页）不会报错，只是那一页搜不到
_navs_blob = HTML[HTML.find("const navs = ["):]
_navs_blob = _navs_blob[:_navs_blob.find("];")]
_nav_keys = set(re.findall(r"\{ key: '(\w+)'", _navs_blob))
_alias = HTML[HTML.find("const SEARCH_ALIAS = {"):]
_alias = _alias[:_alias.find("};")]
_alias_keys = re.findall(r"^\s{10}(\w+):", _alias, flags=re.M)
ck("P16 别名表的键全是真页名（写错的键不报错，只是那一页永远搜不到）",
   bool(_nav_keys) and bool(_alias_keys) and all(k in _nav_keys for k in _alias_keys),
   "别名 %d 键，页名 %d 个，错键 %s" % (len(_alias_keys), len(_nav_keys),
                                    [k for k in _alias_keys if k not in _nav_keys]))

print("\n== 汇总 ==")
if FAILED:
    print(f"共 16 条，失败 {len(FAILED)} 条\n失败清单：" + "、".join(FAILED))
    sys.exit(1)
print("共 16 条，全部通过")
