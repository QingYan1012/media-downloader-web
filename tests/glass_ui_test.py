r"""液态玻璃皮肤与启动壳的离线自检。

口径：classic 是原来的样子，glass 只叠表面与光，不动布局；皮肤只存本机浏览器；
启动壳只负责「还没挂载时别让人看白屏」，挂载后必须自己淡出移除。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")

FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def section(start: str, end: str) -> str:
    a = HTML.find(start)
    b = HTML.find(end, a + 1)
    return HTML[a:b] if a >= 0 and b > a else ""


print("== A. 皮肤在首帧前定下来 ==")
head = section("<head>", "</head>")
ck("A1 样式表之前有皮肤脚本", "localStorage.getItem('md_skin')" in head and head.find("md_skin") < head.find("<style>"))
ck("A2 没存过就默认 glass", "|| 'glass'" in head and "dataset.skin" in head)
ck("A3 读取失败也落 glass（不让首帧裸奔）", "catch (_) { document.documentElement.dataset.skin = 'glass'; }" in head)

print("== B. 玻璃令牌与表面 ==")
glass = section('html[data-skin="glass"] {', '/* 页面底色是纯色')
ck("B1 玻璃令牌单独一组（blur/圆角/半透明底）",
   all(k in glass for k in ("--blur:", "--r-lg:", "--glass-bg:", "--glass-brd:", "--glass-hl:")))
ck("B2 暗色有一份对应令牌", 'html[data-skin="glass"] body.dark {' in HTML)
ck("B3 页面底色是纯色，不叠渐变",
   'html[data-skin="glass"] body {' in HTML
   and 'background: #eef2f8;' in section('html[data-skin="glass"] body {', 'html[data-skin="glass"] body.dark {')
   and "gradient" not in section('html[data-skin="glass"] body {', 'html[data-skin="glass"] body.dark {'))
ck("B4 卡片走玻璃底 + 更强毛玻璃 + 折射描边层",
   'html[data-skin="glass"] body .card {' in HTML
   and "blur(var(--blur)) saturate(1.9)" in HTML
   and "html[data-skin=\"glass\"] body .card::before" in HTML
   and "mask-composite: exclude" in HTML)
ck("B5 侧栏/顶栏/底部播放条都有玻璃规则，侧栏跟随主题色",
   all(x in HTML for x in ('html[data-skin="glass"] body .sidebar {',
                           'html[data-skin="glass"] body .header {',
                           'html[data-skin="glass"] body .playbar {'))
   and 'color-mix(in srgb, var(--accent) 30%, #0b1220)' in HTML)
ck("B6 弹窗/菜单/命令面板共用一套玻璃，浮层用更实的纯色底",
   all(x in HTML for x in ('html[data-skin="glass"] body .el-dialog',
                           'html[data-skin="glass"] body .el-dropdown-menu',
                           'html[data-skin="glass"] body .cmdk,',
                           'html[data-skin="glass"] body .ctx-menu'))
   and 'background: var(--glass-panel);' in HTML
   and '--glass-panel: rgba(255, 255, 255, .74);' in HTML)
ck("B7 输入框与主按钮有玻璃层", '.el-input__wrapper' in HTML and '.el-button--primary:not(.is-disabled)' in HTML)
ck("B8 所有玻璃规则都挂在 html[data-skin=glass] 下，classic 不接管",
   HTML.count("html[data-skin=\"glass\"]") >= 12)
_bg_grad = re.findall(r"background(?:-image)?:\s*(?:linear|radial|conic)-gradient",
                      section("/* ── 液态玻璃外观", "/* 启动壳"))
ck("B9 玻璃表面不再用可见背景渐变（掩膜除外）", not _bg_grad, str(_bg_grad[:2]))
_boot_grad = re.findall(r"background(?:-image)?:\s*(?:linear|radial|conic)-gradient",
                        section("/* 启动壳", "</style>"))
ck("B9b 启动壳也是纯色底，没有光斑/渐变", not _boot_grad, str(_boot_grad[:2]))

print("== C. 启动壳 ==")
body_start = HTML.find("<body")
boot = HTML.find('id="boot-splash"')
app = HTML.find('<div id="app">')
ck("C1 启动壳在 #app 之前（首帧就能画）", 0 < boot < app)
ck("C2 启动壳不依赖外部图片/字体", "boot-splash" in HTML and "<img" not in section('<div id="boot-splash"', "</div>"))
ck("C3 有淡出状态与移除动作",
   "#boot-splash.boot-done" in HTML and "boot.classList.add('boot-done')" in HTML and "boot.remove()" in HTML)
ck("C4 只在挂载之后收（移除代码在 .mount 之后）",
   HTML.find("boot.classList.add('boot-done')") > HTML.find(".mount('#app')"))
ck("C5 载入提示是中英双语的静态字", "正在载入界面 · Loading" in HTML)
ck("C6 启动壳是纯色底，不再有彩色光斑",
   "#boot-splash::before" not in HTML and "#boot-splash::after" not in HTML
   and 'html[data-skin="glass"] #boot-splash {' in HTML
   and "background: #eef2f8;" in section('html[data-skin="glass"] #boot-splash {', "#boot-splash.boot-done"))

print("== D. 图标与皮肤开关 ==")
ck("D1 图标库 defer 到解析后，不挡首屏", 'defer src="/static/vendor/lucide.min.js"' in HTML)
ck("D2 加载完补画一次图标（onload）", "onload=\"try{lucide.createIcons" in HTML)
ck("D3 挂载后的 paintIcons 仍在（页面切换也补）", "const paintIcons" in HTML and "lucide.createIcons({ attrs: { 'stroke-width': 2 } })" in HTML)
ck("D4 皮肤 ref 从 dataset 读，缺省 glass",
   "const skin = ref(document.documentElement.dataset.skin === 'classic' ? 'classic' : 'glass')" in HTML)
ck("D5 applySkin 同时写 dataset 与 localStorage",
   "document.documentElement.dataset.skin = v" in HTML and "localStorage.setItem('md_skin', v)" in HTML)
ck("D6 toggleSkin 走 setSkin，不是各自改状态", "function toggleSkin()" in HTML and "setSkin(skin.value !== 'glass')" in HTML)
ck("D7 顶栏有皮肤钮（aria-pressed 跟着状态走）",
   'class="icon-btn skin-btn"' in HTML and ':aria-pressed="skin === \'glass\'"' in HTML)
ck("D8 设置页外观里有同一开关", "settings.glassSkinLabel" in HTML and '<el-switch :model-value="skin === \'glass\'" @change="setSkin">' in HTML)

print("== E. 词表 ==")
for key, zh, en in (
    ("header.skinGroup", "外观皮肤", "Appearance skin"),
    ("header.skinOnTip", "液态玻璃：开", "Liquid glass: on"),
    ("header.skinOffTip", "液态玻璃：关", "Liquid glass: off"),
    ("settings.glassSkinLabel", "液态玻璃外观", "Liquid-glass skin"),
    ("settings.glassSkinHint", "半透明表面", "Translucent surfaces"),
    ("ui.skin_on", "切换为液态玻璃外观", "[UI] Switched to the liquid-glass skin"),
    ("ui.skin_off", "切换回经典外观", "[UI] Switched back to the classic skin"),
):
    ok = (f"'{key}': '{zh}" in JS or f"'{key}': '{zh}" in JS) and (f"'{key}': '{en}" in JS or f"'{key}': '{en}" in JS)
    ck(f"E1 {key} 中英都在", ok, key)
ck("E2 动作日志用两处字面调用（不是动态拼键）",
   "if (next === 'glass') logAction('ui.skin_on'); else logAction('ui.skin_off');" in HTML)

print("== F. 恢复与挂机开销不回退 ==")
onvis = section("const onVis = () => {", "document.addEventListener('visibilitychange', onVis)")
ck("F1 回到可见先看 hidden", "if (document.hidden) return;" in onvis)
ck("F2 两次读取错峰，不在同一拍抢主线程", "setTimeout(() => { if (!document.hidden) loadStatus(); }, 140)" in onvis
   and "setTimeout(() => { if (!document.hidden) loadTasks(); }, 340)" in onvis)
ck("F3 隐藏时的主轮询仍在最前面", "if (document.hidden) return;" in section("pollTimer = setInterval", "' + 140 + '") or
   "if (document.hidden) return;" in section("pollTimer = setInterval", "}, 1500)"))
ck("F4 剪贴板不再 2 秒轮询，回前台仍补一次",
   "pollClipboard();" in HTML and "pollClipboard(); }, 2000)" not in HTML
   and "clipTimer" not in HTML and "pollClipboard();" in onvis)
ck("F5 LUX 只留下与下载区间有关的那句老注释",
   len(re.findall(r"(?i)lux", SERVER)) == 1 and "播放列表区间（lux 风格" in SERVER)

print("== G. 不收外链 ==")
ck("G1 没有新的 http(s) 脚本/样式", not re.search(r'<(?:script|link)[^>]+(?:src|href)="https?://', HTML))
ck("G2 CSS 里没有引用远程背景图", not re.search(r"url\(['\"]?https?://", HTML))

print("\nFAILED:", FAILED or "none")
sys.exit(1 if FAILED else 0)
