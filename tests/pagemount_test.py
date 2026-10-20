# -*- coding: utf-8 -*-
r"""页面挂载闸门：一次按键的重画只该付当前页的钱。

起因（2026-10-17 实测）：17 个页面块一直是 v-show，全部常驻 DOM；资源库又在开机就扫，
每行还带一个 el-select（连同 teleport 出去的整份预设选项）。60 个成品时，主工作树那份
在首页敲一个字要 24.5 ms（节点 6653 / el-select 91），早超了一帧的 16.7 ms，所以「每个页面都卡」。
改成只挂当前页 + 资源库进页才读 + 行内原生 select 后，同一把探针量到 2.0 ms（节点 564）。
这三条都是能被顺手改回去的，所以钉在这里。

跑法：`python tests/pagemount_test.py`（纯读文件，不起 server）。

第二起因（2026-10-19 实测）：首屏那 6 件框架文件原先挂在 jsdelivr 上，链路一卡就各等 28 秒、还是串行的，
DOMContentLoaded 168 秒、页面里 1332 处裸 {{ }}、一次 /api 都没发；搬到 /static/vendor/ 后同一臂 0.4 秒挂载。
P38-P40 钉的就是「不许再引外部 CDN，且这六件本地文件字节得对」。
"""
from __future__ import annotations

import hashlib
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

# ---------------------------------------------------------------- #73 顶部常驻通知条
_banner_names = ["banners", "dismissBanner"]
_ret73 = HTML[HTML.rindex("return {"):]
ck("P17 通知条模板用到的名字都在 setup 的返回清单里（同 P13：漏一个整页空白）",
   all(re.search(r"\b%s\b" % n, _ret73) for n in _banner_names),
   str([n for n in _banner_names if not re.search(r"\b%s\b" % n, _ret73)]))
# 「常驻」靠的是挂在 .content 顶上、17 页共用一处；谁把它挪进某一页的 v-if 块里，
# 别的页面就静默没有提醒了 —— 静态切一片就知道位置对不对
_c_at = HTML.find('<div class="content">')
_b_at = HTML.find('class="banner-stack"')
_home_at = HTML.find("<!-- 下载页 -->")
ck("P18 通知条排在 .content 的最前、任何一页的块之前（这才叫常驻，切页不重写）",
   -1 < _c_at < _b_at < _home_at, "content %d / stack %d / 首页块 %d" % (_c_at, _b_at, _home_at))
ck("P19 关闭写 sessionStorage、名单从 sessionStorage 读回，且每条事由都过一遍过滤",
   "const BANNER_DISMISS_KEY = 'md_banner_dismiss';" in HTML
   and "sessionStorage.setItem(BANNER_DISMISS_KEY, JSON.stringify(bannerOff.value))" in HTML
   and "JSON.parse(sessionStorage.getItem(BANNER_DISMISS_KEY) || '[]')" in HTML
   and "out.filter((b) => bannerOff.value.indexOf(b.id) < 0)" in HTML)
# 旧的自动弹窗换成通知条之后，这三处残留一个都算「改了但没改干净」：
# 会话一次性变量留着 = 自动检测还能弹窗；存储键留着 = 老用户浏览器里躺一个没人读的键
_b_boot = HTML[HTML.find("async function bootCompCheck() {"):HTML.find("async function bootCompCheck() {") + 900]
ck("P20 自动检测那条弹窗路径真断了：bootCompCheck 不再调它，会话变量与旧存储键一起清了",
   "maybePopupCompUpdates" not in _b_boot and "compPopupShown" not in HTML
   and "mdCompUpdatePopupShown" not in HTML)
# gotoCard 的锚点写错（或卡片搬进折叠组没跟着展开）不会报错，只是点「查看」页面跳过去了却停在原地
_anchors = set(re.findall(r"gotoCard\(\s*'[\w']+',\s*'([^']+)'", HTML))
ck("P21 每个跳转锚点在模板里都真有一个同 id 的元素",
   bool(_anchors) and all('id="%s"' % a in HTML for a in _anchors),
   str([a for a in _anchors if 'id="%s"' % a not in HTML]))
# 补发队列卡片已从「不常用项」折叠组移到通知页常驻可见，跳转不再需要先展开；
# 卡片必须仍带锚点 id 且由通知页签控制显隐，横幅点击只切页 + gotoCard
ck("P22 补发队列卡片在通知页直接可见、跳转只切页（不再依赖折叠组展开）",
   'v-show="stab === \'notify\'" class="card card--wide" id="outbox-card"' in HTML
   and "stab.value = 'notify'; gotoCard('settings', 'outbox-card'" in HTML)
_b_computed = HTML[HTML.find("const banners = computed("):]
_b_computed = _b_computed[:_b_computed.find("\n        });")]
ck("P23 通知条的文案全走词表（事由行里除了注释不许有硬编码中文）",
   not [ln for ln in _b_computed.splitlines()
        if re.search(r"[一-鿿]", ln) and not ln.strip().startswith(("//", "/*", "*"))],
   str([ln.strip()[:40] for ln in _b_computed.splitlines()
        if re.search(r"[一-鿿]", ln) and not ln.strip().startswith(("//", "/*", "*"))]))
ck("P24 开机预取一次补发队列（不预取的话通知条在别的页面上永远是空的）", "loadOutbox();" in boot)
# gotoCard 改成逐帧对齐不是摆设：一次「去更新」实测停在偏 1358 px 的地方（页面还在往目标上面填内容）。
# 谁改回「找到就 scrollIntoView 一次」，这个偏位不会报错、只会让人以为按钮没反应
_gc73 = HTML[HTML.find("function gotoCard("):HTML.find("function gotoCard(") + 1400]
ck("P25 跳转是逐帧重对齐（落点变了再滚一次、连续几帧不动才收手），不是一次性 scrollIntoView",
   "sc.scrollTop += off - pad" in _gc73 and "requestAnimationFrame(step)" in _gc73
   and "scrollIntoView" not in _gc73, _gc73[:60].replace("\n", " "))
ck("P26 落点让出顶部通知条的高度（通知条是 sticky 压在内容区上沿的，齐平等于把卡片头藏进条子里）",
   "document.querySelector('.banner-stack')" in _gc73 and "+ 10" in _gc73)

# ---------------------------------------------------------------- #75 行内右键菜单
_ctx_names = ["ctxMenu", "runCtxItem"]
ck("P27 右键菜单模板用到的名字都在 setup 的返回清单里（同 P13：漏一个整页空白）",
   all(re.search(r"\b%s\b" % n, _ret73) for n in _ctx_names),
   str([n for n in _ctx_names if not re.search(r"\b%s\b" % n, _ret73)]))
# 同 P15 那个坑：.card 带 backdrop-filter，弹层写进任何一张卡片里都会歪进那一格。
# 菜单必须和面板同一侧 —— 在 .layout 里、在 .main 外
_at_cmdk = HTML.find('class="cmdk-mask"')
_at_ctx = HTML.find('class="ctx-menu"')
ck("P28 菜单模板挂在 .layout 里、.main 外（排在面板之后、config-provider 收尾之前）",
   -1 < _at_cmdk < _at_ctx < HTML.find("</el-config-provider>"),
   "cmdk %d / ctx %d" % (_at_cmdk, _at_ctx))
_ctx_fn = HTML[HTML.find("function ctxItemsOf("):HTML.find("function onCtxPointer(")]
ck("P29 菜单项是从那一行现有的按钮读出来的（不许在这里另写一份动作名单——那是第二个真源）",
   "row.querySelectorAll('button')" in _ctx_fn
   and not re.search(r"tr\('(files|queue|library)\.", _ctx_fn),
   str(re.findall(r"tr\('[a-z]+\.[\w.]+'", _ctx_fn)))
ck("P30 代管下拉的那一项走词表，且只有行里真有「更多」时才多这一项",
   "const more = row.querySelector('.el-dropdown button');" in HTML
   and "if (more && !more.disabled && more.offsetParent !== null)" in HTML
   and "tr('ctx.more')" in HTML)
ck("P31 全局 contextmenu 监听挂了也必须摘（同 P14 那条规矩）",
   "document.addEventListener('contextmenu', onDocContextmenu)" in HTML
   and "document.removeEventListener('contextmenu', onDocContextmenu)" in HTML)
# 三种行式样（EP 表格 / 任务卡片 / 原生 table）都要认，少写一种就是那一页右键什么都不出
_sel75 = HTML[HTML.find("const CTX_ROW_SEL ="):]
_sel75 = _sel75[:_sel75.find(";")]
ck("P32 行的认定覆盖三种式样（.el-table__row / .task-card / tbody tr）",
   all(k in _sel75 for k in (".el-table__row", ".task-card", "tbody tr")), _sel75.strip())
# 原生右键让路是这一项的边界：输入框里粘贴、选完字的复制，都不该被菜单抢走
ck("P33 输入框/选字/没有动作这三类情况让回浏览器原生菜单（不 preventDefault）",
   "e.target.closest('input, textarea, select, [contenteditable], .el-select, .el-checkbox')" in HTML
   and "sel.isCollapsed" in HTML and "if (!items.length) return false;" in HTML)
# 染红判据必须是按钮自带的类：按「删除」这两个字猜，词表一切成英文就整条失灵
ck("P34 破坏性那一项的红是跟按钮走的，不是按字面猜的",
   "b.classList.contains('el-button--danger')" in _ctx_fn
   and "'ctx-menu__item--bad': it.bad" in HTML
   and not re.search(r"label === '删除'|/删除/\.test\(label", HTML))

# 默认排序是三处联动的：表头箭头看模板的 default-sort，行序看两个 ref，改一处就会出现
# 「箭头指着修改时间、行却按名字排」。目录永远在最前这条也不能被时间序碰坏。
ck("P35 文件页默认按修改时间倒序，三处联动一致（目录仍钉在最前）",
   "const fileSort = ref('mtime');" in HTML
   and "const fileSortDir = ref('desc');" in HTML
   and ':default-sort="{ prop: \'mtime\', order: \'descending\' }"' in HTML
   and "const FILE_DIR = { name: 'asc', size: 'desc', mtime: 'desc' };" in HTML
   and "if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;" in HTML)

# ---- #80 折叠钮移进标题行 ----
# 这条只能静态钉「挂在哪儿」，量不出来「64px 里到底放不放得下」——
# 后者是活体读的（tmp/collapse_pos.py，2026-10-20 沙箱：展开 30×30 贴右端；折叠 logo x1..37 与
# 钮 x37..63 并排一行、两者中心同高（centerDiff 0）、钮心命中钮自己、来回点都回得来、零 pageerror）。
_logo_blk = HTML[HTML.index('<div class="sidebar-logo">'):HTML.index('<div class="nav-scroll">')]
_btn_at = _logo_blk.index('class="nav-collapse"')
ck("P36 折叠钮挂在标题行里、排在品牌名之后（挪回标题行下面那条整宽条，这一条就红）",
   HTML.count('class="nav-collapse"') == 1
   and '<div class="brand">' in _logo_blk[:_btn_at]
   and "</div>" in _logo_blk[_logo_blk.index("</button>", _btn_at):])
_btn_rule = re.search(r"\.nav-collapse \{([^}]*)\}", HTML)
_cl_logo = re.search(r"\.sidebar\.is-collapsed \.sidebar-logo \{([^}]*)\}", HTML)
_cl_btn = re.search(r"\.sidebar\.is-collapsed \.nav-collapse \{([^}]*)\}", HTML)
ck("P37 两档位置各靠一条规则：展开用 margin-left:auto 顶到右端、不再自带下划线；"
   "折叠不换行（flex-wrap: nowrap），钮收成 26px 与 logo 并排在这一行里",
   _btn_rule is not None and _cl_logo is not None and _cl_btn is not None
   and re.search(r"margin-left:\s*auto", _btn_rule.group(1)) is not None
   and "border-bottom" not in _btn_rule.group(1)
   and "flex-wrap: nowrap" in _cl_logo.group(1)
   and re.search(r"width:\s*26px", _cl_btn.group(1)) is not None
   and "width: 100%" not in _cl_btn.group(1),
   "btn=%r clLogo=%r clBtn=%r" % (_btn_rule and _btn_rule.group(1), _cl_logo and _cl_logo.group(1),
                                  _cl_btn and _cl_btn.group(1)))

VENDOR = {
    "vue.global.prod.js": "89bc6871c5ebe1f55e65deca4de0c81b37ffea58720f601a9617794c4e9e1e36",
    "element-plus.full.min.js": "9f1e40409d9efba7464b72e77bb038aff7bcb9e924bd61e61159b23877e36bf1",
    "element-plus.index.css": "f23e78f5016cee5505829e416cfecfd8954bd5cc484d4ef3dde40b240dd3d009",
    "element-plus.locale.zh-cn.js": "21e89d13b18fdf57e116cce052f614ea2fa74b84487b7b79569996c534e363b3",
    "element-plus.locale.en.min.js": "615fe4dd0e851bebcfed011367a8dba3d5de2168e744c33c049bdd6052458b27",
    "lucide.min.js": "3411692820cb8d47543f69496aa25fd603a358f4498046f41c508a5a3342210e",
}
_ext = re.findall(r'<(?:script[^>]+\bsrc|link[^>]+\bhref)="(https?://[^"]+)"', HTML)
ck("P38 首屏不再挂任何外部 CDN（挂上去时链路一慢，阻塞脚本挨个等超时，页面几分钟起不来）",
   not _ext, "仍外链：" + "、".join(_ext[:3]))
_root = pathlib.Path(__file__).resolve().parent.parent / "static" / "vendor"
_bad = [n for n, d in VENDOR.items()
        if not _root.is_dir() or not (_root / n).is_file()
        or hashlib.sha256((_root / n).read_bytes()).hexdigest() != d]
ck("P39 六件框架文件真在 static/vendor/ 且字节没被改坏（半截文件或空目录都算红）",
   _root.is_dir() and not _bad, "不对的文件：" + "、".join(_bad))
ck("P40 index.html 引的就是这六件本地路径（漏一件就还在走外网）",
   all(f'/static/vendor/{n}"' in HTML for n in VENDOR))

print("\n== 汇总 ==")
if FAILED:
    print(f"共 40 条，失败 {len(FAILED)} 条\n失败清单：" + "、".join(FAILED))
    sys.exit(1)
print("共 40 条，全部通过")
