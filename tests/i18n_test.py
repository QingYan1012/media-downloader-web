# -*- coding: utf-8 -*-
"""界面多语言（zh / en）离线自检（#53）。

口径（人后来改过一轮，这一套钉的是改完的那版）：**切换语言要把界面全量切过去**，运行日志也一起 ——
推进节奏是按使用频率逐页，一页一提交。骨架那一批（只翻前端 + 错误码）已经不是终点了，但它钉的
那几条线仍然有效，只是又往上加了两组：

1. **词表本身**（A）：zh 与 en 的键集合一致、占位符对得上、没有空值。少哪一份都是运行时才露馅的错，
   而运行时没人会点遍每个页面。
2. **模板用到的键**（B）：把 index.html 里 `tr('…')` 的字面键、以及 `nav.` / `navGroup.` / `page.`
   三个动态前缀背后那些 key/id 全扫出来，逐个要求两份词表都在。这一条防的是「切到英文界面上印出键名」。
3. **接线与后端那一层**（C/D）：引用顺序、el-config-provider 的覆盖范围、帮助函数没被 v-for 遮蔽；
   `ui_language` 进 DEFAULTS、进 ConfigBody、进恢复默认名单，校验只认 auto/zh/en —— 并且后端除了
   那 4 行之外**没有任何一处读它**（D7）：日志按语言渲染发生在前端，落盘的那份字节不因语言而变。
4. **真实行为**（G，node）：把 static/i18n.js 原样喂给 node，用替身 window 跑 t / detect / apply / boot /
   elementLocale / has，看的是返回值而不是源码文本 —— 包括「en 的词包没加载上时不能把 locale 传成 undefined」
   「刷新后第一帧按 localStorage 镜像，不闪另一种语言」，以及拼出来的中文句与改前模板串一字不差。
5. **日志的键通道**（H）：log() 收 k/kv 但只在给了键时才加字段，进内存与落盘的都是同一条中文 message；
   埋点参数先收口再入库，键形不对就当没给；前端只在英文界面且两份词表都有这个词时才现拼。
6. **逐页闸门**（I）：一页一块地抠模板 —— 登记过的页（PAGES_DONE）除了注释以外不许有中文；
   同一页的处理动作在脚本里拼的那几句也一样（PAGE_HANDLERS），注释不算，它在讲代码。
   比后端数据的那几行（预设名、占位标题）登记在 RESIDUE 里：允许的到底是哪几行，逐行对，
   悄悄多出来一行也算红。没登记的页只报中文行数，不当断言 —— 那是接下来一批一批要清零的债。

全程不起服务、不写 config、不碰下载目录（H 组真跑 LogManager.log，但 LOG_FILE 临时挪到 %TEMP%）；
node 的读数写到 %TEMP% 再读回（控制台是 GBK）。
跑法：PYTHONIOENCODING=utf-8 python tests/i18n_test.py
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import server as S  # noqa: E402

HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
I18N_SRC = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
SERVER_SRC = (ROOT / "server.py").read_text(encoding="utf-8")
PACK = (ROOT / "pack_release.py").read_text(encoding="utf-8")
SELF_TXT = (ROOT / "tests" / "i18n_test.py").read_text(encoding="utf-8")
# 模板区（#app 到 Vue 那几个 script 之间）：数 v-for 这类只有模板里才有的写法时用它，
# 免得把解释这段代码的那句注释本身也数进去（注释里写的字面量是真的出现，但它不在模板里）
_t0 = HTML.find('<div id="app">')
TEMPLATE = HTML[_t0:HTML.find("/vue@3", _t0)] if _t0 > 0 else ""

FAILED: list[str] = []
TOTAL = 0


def ck(name: str, cond, extra="") -> None:
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}" + (f"  [{extra}]" if extra else ""))
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{extra}]")


def block(src: str, start_mark: str, end_mark: str) -> str:
    """从 start_mark 起切到 end_mark 之前；切不到回空串，调用方当场判红，不假装通过"""
    i = src.find(start_mark)
    if i < 0:
        return ""
    j = src.find(end_mark, i)
    return src[i:j] if j > 0 else ""


PAIR = re.compile(r"['\"]?([A-Za-z][\w.-]*)['\"]?:\s*'((?:[^'\\]|\\.)*)'")
PLACE = re.compile(r"\{\w+\}")

zh_blob = block(I18N_SRC, "    zh: {", "\n    en: {")
en_blob = block(I18N_SRC, "    en: {", "\n  };\n")
DICT = {lang: dict(PAIR.findall(blob)) for lang, blob in (("zh", zh_blob), ("en", en_blob))}

# ---------------------------------------------------------------- A. 词表
print("== A. 词表两份要对得上 ==")
ck("A1 zh 词表抠出来了", len(DICT["zh"]) >= 30, f"{len(DICT['zh'])} 键")
ck("A2 en 词表抠出来了", len(DICT["en"]) >= 30, f"{len(DICT['en'])} 键")
only_zh = sorted(set(DICT["zh"]) - set(DICT["en"]))
only_en = sorted(set(DICT["en"]) - set(DICT["zh"]))
ck("A3 zh 与 en 的键集合一致", not only_zh and not only_en, f"只 zh 有={only_zh} 只 en 有={only_en}")
empties = [f"{lang}.{k}" for lang in ("zh", "en") for k, v in DICT[lang].items() if not str(v).strip()]
ck("A4 没有空值（空串会让界面上什么都不显示）", not empties, str(empties[:6]))
# 鸣谢里 Emby 那条：zh 的 {专辑}{年份}{序号}{曲名} 是它在**描述别人的目录写法**（中文 token），
# 不是本程序要填的参数 —— 英文照原样留四个中文括号反而更糟，所以那句翻成 album / year / number - title。
A5_OK = {"settings.credit.emby"}
bad_ph = {k: (PLACE.findall(DICT["zh"][k]), PLACE.findall(DICT["en"][k]))
          for k in (set(DICT["zh"]) & set(DICT["en"])) - A5_OK
          if sorted(PLACE.findall(DICT["zh"][k])) != sorted(PLACE.findall(DICT["en"][k]))}
ck("A5 同一个键两边的 {n} 占位符一致", not bad_ph, str(bad_ph))
dollar = [f"{lang}.{k}" for lang in ("zh", "en") for k, v in DICT[lang].items() if "${" in str(v)]
ck("A6 词表里没有 JS 模板串残留（${} 在单引号里不会被替换）", not dollar, str(dollar))
ck("A7 值里没有裸露的 HTML 标签（词表只放文字）",
   not re.search(r"<[a-zA-Z/]", "".join(DICT["zh"].values()) + "".join(DICT["en"].values())))
other_ph = [f"{lang}.{k}" for lang in ("zh", "en") for k, v in DICT[lang].items()
            if "%s" in str(v) or "{}" in str(v)]
ck("A8 占位符只用花括号一种写法", not other_ph, str(other_ph))
# 分隔符那一类例外：它是 join 的接缝，首尾那两个空格本来就是它的内容，挪不进模板。
# 除此以外的中文片段之间的空格一律写在模板的接缝上（元素与插值之间那一个不带换行的空格，
# 本机这份 Vue 编译后照样保留，实测见 tmp/vue_ws_probe2.js）。
A9_OK = {"settings.orSep"}
padded = [k for k, v in DICT["zh"].items() if v != v.strip() and k not in A9_OK]
ck("A9 zh 的词表值不带首尾空格（渲染出来就是错位）", not padded, str(padded[:6]))
# 英文里引用界面名称用普通双引号；「」是中文标点，F8 那条（en 不许有汉字）管不到它。
# 顺带盯住换过来时最容易犯的错：全角括号两侧本来不需要空格，换成直引号后就成了 word"word。
en_br = [k for k, v in DICT["en"].items() if "「" in str(v) or "」" in str(v)]
ck("A10 en 的值里不留中文引号「」", not en_br, str(en_br[:6]))
en_glue = [k for k, v in DICT["en"].items() if re.search(r'[A-Za-z0-9]"[A-Za-z0-9]', str(v))]
ck("A11 en 的引号两侧不直接贴词（补空格这类活由脚本干，别让它在词表里留着）", not en_glue, str(en_glue[:6]))

# ---------------------------------------------------------------- B. 模板用到的键
print("== B. 模板里用到的每个键都在词表 ==")
html_keys = sorted(set(re.findall(r"\btr\(\s*'([^']*)'", HTML)))
js_keys = sorted(set(re.findall(r"\bI18N\.t\(\s*'([^']*)'", I18N_SRC)))
dyn = [k for k in html_keys if k.endswith(".")]
literal = [k for k in html_keys if not k.endswith(".")]
ck("B1 模板里确有 tr('字面键') 在用", len(literal) >= 8, f"{len(literal)} 个：{literal[:4]}")
ck("B2 动态前缀就那三个", sorted(dyn) == ["nav.", "navGroup."], str(sorted(dyn)))
miss_zh = [k for k in literal if k not in DICT["zh"]]
miss_en = [k for k in literal if k not in DICT["en"]]
ck("B3 字面键 zh 词表全有（缺了会印出键名）", not miss_zh, str(miss_zh))
ck("B4 字面键 en 词表全有", not miss_en, str(miss_en))

navs_blob = block(HTML, "const navs = [", "];")
groups_blob = block(HTML, "const NAV_GROUPS = [", "];")
nav_keys = re.findall(r"\{ key: '(\w+)'", navs_blob)
group_ids = re.findall(r"\{ id: '(\w+)'", groups_blob)
ck("B5 navs 的 17 个键抠出来了", len(nav_keys) == 17, f"{len(nav_keys)} 个")
ck("B6 分组 id 抠出来了", len(group_ids) == 5, str(group_ids))
ck("B7 每个导航键都有 nav.<key>（两份都要）",
   not [k for k in nav_keys if f"nav.{k}" not in DICT["zh"] or f"nav.{k}" not in DICT["en"]],
   str([k for k in nav_keys if f"nav.{k}" not in DICT["zh"]]))
ck("B8 每个分组都有 navGroup.<id>，兜底那份 other 也在",
   not [k for k in group_ids + ["other"]
        if f"navGroup.{k}" not in DICT["zh"] or f"navGroup.{k}" not in DICT["en"]],
   str([k for k in group_ids + ["other"] if f"navGroup.{k}" not in DICT["zh"]]))
miss_page = [k for k in nav_keys if f"page.{k}" not in DICT["zh"] or f"page.{k}" not in DICT["en"]]
ck("B9 每个页面都有 page.<key>（页头标题走的是它）", not miss_page, str(miss_page))
covered = set(literal) | set(js_keys)
# 三元表达式里的键（tr(cond ? 'home.magnet' : 'home.weblink')）不在 tr(' 后面，字面扫会漏；
# 这里把 HTML 里所有像键名的单引号串都算作「有人在用」，代价是键名若被无缘无故抄在 HTML 里就查不出死键
covered |= set(re.findall(r"'([a-z][A-Za-z0-9_.-]*)'", HTML)) & set(DICT["zh"])
# 日志那条线的键不是在模板里出现的：ui.* 由 logAction('ui.lang_' + pref) 拼前缀，
# log.* 由后端 k="log.xxx" 带进条目 —— 这两处引用也算「有人在用」，否则 B10 会把它们报成死键
ui_prefixes = re.findall(r"logAction\(\s*'([a-z][\w.]*)'\s*\+", HTML)
srv_keys = set(re.findall(r'\bk=["\']((?:log|ui)\.[\w.]+)["\']', SERVER_SRC))
dead = sorted(k for k in DICT["zh"]
              if k not in covered and k not in srv_keys
              and not (ui_prefixes and any(k.startswith(p) for p in ui_prefixes))
              and not (k.startswith("nav.") and k.split(".", 1)[1] in nav_keys)
              and not (k.startswith("navGroup.") and k.split(".", 1)[1] in group_ids + ["other"])
              and not (k.startswith("page.") and k.split(".", 1)[1] in nav_keys))
ck("B10 词表里没有谁都不用的死键", not dead, str(dead))
ck("B11 侧栏标签真的走词表，没留着写死的那句",
   "{{ tr('nav.' + item.key) }}" in HTML
   and '<i :data-lucide="item.icon" class="nav-lucide"></i><span>{{ item.label }}</span>' not in HTML)
ck("B12 navs 里不再抄一份名字（数据与词表只能有一个真源）", "label:" not in navs_blob,
   "navs 块里还有 label:")
ck("B13 NAV_GROUPS 里同理没有第二份组名", "title:" not in groups_blob, "NAV_GROUPS 里还有 title:")
# 两张数据表里存的是词表键（渲染处 tr(g.titleKey) / cfgLabel 里 tr(CFG_KEYS[k])）：
# 键写错不是「那一格空着」，是把 settings.cfg.acoustid_api_key 这种原文印到界面上。
cfg_blob = block(HTML, "const CFG_KEYS = {", "};")
credit_blob = block(HTML, "const CREDITS = [", "];")
table_keys = sorted(set(re.findall(r":\s*'([^']+)'", cfg_blob))
                    | set(re.findall(r"(?:titleKey|noteKey): '([^']+)'", credit_blob)))
miss_table = [k for k in table_keys if k not in DICT["zh"] or k not in DICT["en"]]
ck("B14 数据表里登记的词表键两份都在（缺一个界面上就印键名）",
   len(table_keys) > 100 and not miss_table, f"{len(table_keys)} 个，缺 {miss_table[:6]}")
ck("B15 表里不再抄第二份文案（CREDITS 只剩 noteKey，CFG_RAW 那种两边一样的厂商名才算例外）",
   "note:" not in credit_blob and "title:" not in credit_blob, "CREDITS 里还有 note:/title:")

# ---------------------------------------------------------------- C. 接线
print("== C. 页面接线：引用顺序与那层 config-provider ==")
i_script = HTML.find('src="/static/i18n.js"')
i_boot = HTML.find("MD_I18N.boot()")
i_create = HTML.find("createApp({")
ck("C1 i18n.js 在 index.html 里被引用", i_script > 0)
ck("C2 引用它在 createApp 之前（否则 window.MD_I18N 还是 undefined）",
   0 < i_script < i_create, f"script={i_script} createApp={i_create}")
ck("C3 boot() 也在 createApp 之前", 0 < i_boot < i_create, f"boot={i_boot}")
ck("C4 Element Plus 的 en 词包有加载", "dist/locale/en.min.js" in HTML)
ck("C5 创建应用时的 locale 不再写死 zh-cn",
   "locale: window.MD_I18N ? window.MD_I18N.elementLocale() : window.ElementPlusLocaleZhCn" in HTML)
ck("C6 整棵子树被 el-config-provider 包住（一开一合）",
   HTML.count('<el-config-provider :locale="epLocale">') == 1
   and HTML.count("</el-config-provider>") == 1)
ck("C7 epLocale 是按 uiLang 算的 computed（传参才会被切语言触发重算）",
   "const epLocale = computed(() => (window.MD_I18N ? window.MD_I18N.elementLocale(uiLang.value)" in HTML)
ck("C8 帮助函数叫 tr 不叫 t（模板里 7 处 v-for=「t in …」会把它遮蔽）",
   "const tr = (key, vars) =>" in HTML and TEMPLATE.count('v-for="t in ') == 7,
   f"模板区内 v-for=\"t in \" 实测 {TEMPLATE.count('v-for=\"t in ')} 处")
ck("C9 顶栏有语言钮，点它调 setLang",
   'class="lang-btn"' in HTML and '@click="setLang(lg.key)"' in HTML)
ck("C10 语言钮的选中态读 settings.ui_language（与主题色板同一个路子）",
   "(settings.ui_language || 'auto') === lg.key" in HTML)
ck("C11 UI_LANGS 的选项来自 i18n.js，不在这里再抄一遍",
   "const UI_LANGS = (window.MD_I18N && window.MD_I18N.langs)" in HTML)
# 锚点取的是这一串里不会随新增名字挪位的片段：早先锚的是「page, navs, navGroups,」，
# #71 在 page 后面插了 navCollapsed 就把整行锚断了（闸门红得没错，但错的原因不好猜）
ret_line = block(HTML, "navs, navGroups, CREDITS", "\n")
ck("C12 setup 返回清单里 tr / uiLang / UI_LANGS / epLocale / setLang 都在",
   all(n in ret_line for n in ("tr,", "uiLang,", "UI_LANGS,", "epLocale,", "setLang,")),
   ret_line.strip()[:120])
ck("C13 CSS 有 .lang-btn 的明暗两套（暗色下不能白底白字）",
   ".lang-btn {" in HTML and "body.dark .lang-btn.active" in HTML)
ck("C14 页头标题走 pageTitle → tr('page.…')，没词时留空而不是印键名",
   "const k = 'page.' + page.value;" in HTML and "return s === k ? '' : s;" in HTML)
ck("C15 loadSettings 把后端的值收敛成 auto/zh/en 再应用",
   "settings.value.ui_language = ['zh', 'en'].includes(data.ui_language) ? data.ui_language : 'auto';" in HTML
   and "applyLang(settings.value.ui_language);" in HTML)
ck("C16 界面初值也是 auto（后端读回来之前不至于闪一下别的语言）",
   "ui_language: 'auto'," in HTML)
# ElMessageBox 是命令式弹的，不吃 el-config-provider：语言只在 .use(ElementPlus) 那刻定过一次，
# 在页面里切成英文后确认框的按钮仍印「取消/确定」。接线改成了弹出时现取按钮词，钉住三件事。
ck("C17 confirm/prompt/alert 三个入口都被包了一层（少一个就有一类框漏掉）",
   "const mb = ElementPlus.ElMessageBox;" in HTML
   and "['confirm', 'prompt', 'alert'].forEach" in HTML, "")
ck("C18 按钮词按当前界面语言现取，且调用方写死的按钮词排在后面（顺序反了就把「按这份名单删」盖成「确定」）",
   "confirmButtonText: tr('common.ok'), cancelButtonText: tr('common.cancel'), ...opt" in HTML, "")
ck("C19 alert 不硬塞取消键（它天生只有一个按钮），但别人显式给了就留着",
   "if (name === 'alert' && opt.cancelButtonText === undefined) delete filled.cancelButtonText;" in HTML, "")
ck("C20 这两个按钮词两份词表都有（缺 en 就印回中文，缺 zh 界面直接空着）",
   "'common.ok':" in zh_blob and "'common.cancel':" in zh_blob
   and "'common.ok':" in en_blob and "'common.cancel':" in en_blob, "")
# 模板里两截字面量中间只隔一个标签（{{ A }}<strong>{{ B }}</strong>{{ C }}），中文连着写不用空格，
# 英文必须留：不留就渲染成 "thelatest"、"butqueues"（订阅页这两处在翻完时实测到了）。
# 跨行写的那类不算：换行本来就被浏览器折成一个空格。
# 用零宽预查：A-B 与 B-C 连着两处接缝要都能抓到（普通匹配会把 B 那句吃掉，只留下前一半）。
# 只认行内标签夹着的那类：表格两个单元格 </th><th> 相邻不连着读，不该按缺空格算。
SEAM = re.compile(r"(?=\{\{\s*tr\('([^']*)'\s*\)\s*\}\}(?:</?(?:b|strong|em|i|u|span|code|small|sup|sub|mark|a)[^>]*>){1,2}\{\{\s*tr\('([^']*)')")
_seams = [(a, b) for a, b in SEAM.findall(re.sub(r"<!--.*?-->", "", HTML, flags=re.S))
          if a in DICT["en"] and b in DICT["en"]]
ck("C21 抓到了同标签接缝（一条没有就是闸门空转）", len(_seams) >= 2, f"{len(_seams)} 处：{_seams}")
ck("C22 英文的接缝处要么前一句带尾空格，要么后一句以空格/标点开头",
   not [f"{a}|{b}" for a, b in _seams
        if not (DICT["en"][a].endswith(" ") or DICT["en"][b].startswith(" ")
                or DICT["en"][b][:1] in ",.;:!?、。）]」』\"'")],
   str([f"{a}|{b}" for a, b in _seams if not (DICT["en"][a].endswith(" ") or DICT["en"][b].startswith(" ")
        or DICT["en"][b][:1] in ",.;:!?、。）]」』\"'")]))

# ---------------------------------------------------------------- D. 后端那一层
print("== D. 后端：只存这一项，别处一概不读 ==")
ck("D1 UI_LANGUAGES 就三个值", S.UI_LANGUAGES == ("auto", "zh", "en"), str(S.UI_LANGUAGES))
ck("D2 DEFAULTS 有 ui_language 且默认 auto", S.cfg.DEFAULTS.get("ui_language") == "auto",
   repr(S.cfg.DEFAULTS.get("ui_language")))
ck("D3 ConfigBody 声明了 ui_language（没声明就写不进去）", "ui_language" in S.ConfigBody.model_fields)
ck("D4 校验只认 auto/zh/en，乱写的落回 auto",
   'data["ui_language"] = data["ui_language"] if data["ui_language"] in UI_LANGUAGES else "auto"' in SERVER_SRC)
ck("D5 能一键恢复默认（在 defaultable 名单里）", "ui_language" in S._cfg_defaultable())
ck("D6 密钥类禁改名单没把它误收（否则恢复默认会跳过它）",
   "ui_language" not in S.CONFIG_RESET_FORBIDDEN,
   str(sorted(S.CONFIG_RESET_FORBIDDEN)[:6]))
ui_lines = [l.strip() for l in SERVER_SRC.splitlines() if "ui_language" in l]
ck("D7 后端只有 4 行认得它（DEFAULTS / 字段 / 校验两行），别处不读",
   len(ui_lines) == 4, f"{len(ui_lines)} 行：" + " | ".join(ui_lines)[:200])
ck("D8 exclude_none：没交这一项就不会被顺手改写",
   S.ConfigBody().model_dump(exclude_none=True).get("ui_language") is None)
ck("D9 校验挂在 _apply_config 里（与 ui_theme 同一条闸门，恢复默认走的也是它）",
   'if "ui_language" in data:' in block(SERVER_SRC, "def _apply_config(data: dict", "\n@app."))

# ---------------------------------------------------------------- E. 打包
print("== E. 这个新文件会随包走 ==")
ck("E1 static 整个目录在打包清单里（i18n.js 不用再单独登记）",
   re.search(r'APP_DIRS\s*=\s*\[[^\]]*"static"', PACK) is not None)
ck("E2 文件真在场且不空", (ROOT / "static" / "i18n.js").is_file() and len(I18N_SRC) > 2000, f"{len(I18N_SRC)} 字")
ck("E3 换行口径：static/i18n.js 与 index.html 都是 LF（与仓库其余前端文件一致）",
   "\r\n" not in I18N_SRC and "\r\n" not in HTML)
ck("E4 本套是 LF（与仓库其余测试文件一致）", "\r\n" not in SELF_TXT)
# 「这套件不起服务」要用 AST 查，不能用子串查：子串会先命中原谅要禁止的那两个词本身（第 206 行就是这么红的）
_self_tree = ast.parse(SELF_TXT)
_self_calls = {n.attr for n in ast.walk(_self_tree) if isinstance(n, ast.Attribute)}
_self_imports = {a.name.split(".")[0] for n in ast.walk(_self_tree)
                 if isinstance(n, ast.Import) for a in n.names}
_forbidden = {"urlopen", "Popen", "create_server", "run_app"}
ck("E5 本套不发 HTTP、不 spawn 实例（AST 里没有 urlopen / Popen 这类调用）",
   not (_self_calls & _forbidden) and "socket" not in _self_imports and "urllib" not in _self_imports,
   f"calls={sorted(_self_calls & _forbidden)} imports={sorted(_self_imports)}")

# ---------------------------------------------------------------- F. 口径边界
print("== F. 边界：这一批没有动后端话术 ==")
fe_body = block(HTML, "function friendlyError(raw) {", "\n        }\n")
fe_branches = len(re.findall(r"return (?:withTail|keepTail)\(", fe_body))
ck("F1 friendlyError 那 22 条分支还在，且没被 tr() 接手（报错翻译排在界面模块批次之后）",
   fe_branches == 22 and "tr(" not in fe_body, f"抠到 {fe_branches} 条分支，{len(fe_body)} 字")
ck("F2 后端原话「原因：…（依据 …）」仍然原样上屏",
   "if (s.includes('原因：') || s.includes('（依据 ')) return s;" in HTML)
ck("F3 界面埋点仍先落一句中文原话（键是附带的，不是替掉原文）",
   "const zh = hasK ? MD_I18N.t(textOrKey, params, 'zh') : String(textOrKey || '');" in HTML
   and 'text: leaky ? \'[已隐藏敏感参数]\' : t,' in HTML)
ck("F4 i18n.js 里 t() 的回落链是 en → zh → 键名",
   "(DICT[L] && DICT[L][key] != null)" in I18N_SRC
   and "DICT.zh[key] != null ? DICT.zh[key] : key" in I18N_SRC)
ck("F5 词表里没有订阅规则摘要那类后端正文",
   not [k for k in DICT["zh"] if "规则已更新" in DICT["zh"][k] or "每次最多" in DICT["zh"][k]])
CJK = re.compile(r"[\u4e00-\u9fff]")
latin = re.compile(r"[A-Za-z]")
# 例外：zh 原话里本来就没有汉字的那几条 —— 「aria2c：」是工具名加全角冒号，
# 后面接的是本机路径。给它编一句中文反而是我新写的话，不是界面原本那句
# 音乐页那三条是纯拼接模板（「{name}」—— {why}、统计的（{s}））：值里只有全角括号、破折号与占位符，
# 翻的是英文一侧的标点（（）→ () 、「」—— → — ），汉字本来就不该有
F6_OK = {"bt.binFound", "music.favFailLine", "music.statsWrap", "music.switchFailLine",
         # 平台名与协议名：界面原文里就没有汉字，编一句中文反而是我新写的话
         "settings.platformYoutube", "settings.platformTwitch", "settings.optFlv", "settings.optHls",
         # ffmpeg 的那个词本机界面就写作 mtime；全角括号那条只是 ( {where} ) 模板
         "settings.clMtimeWord", "auth.deviceParen",
         # 机翻引擎这两项界面原文就是「厂商名（括号里还是厂商名）」，一个汉字也没有
         "settings.mtOptClaude", "settings.mtOptGemini",
         # Whisper 的运算设备与计算精度同理：界面原文就是「设备名/精度名（全角括号里一个缩写）」
         "settings.deviceOptCuda", "settings.computeOptFp16", "settings.computeOptInt8",
         # 组件那一行的箭头缝：值里只有全角冒号、破折号和两个占位符，两边版本字符串是数据不是话
         "settings.compAllRowArrow",
         # CookieCloud 那行备注的外壳同理：（{list}）→ () ，括号里的原话来自后端
         "settings.ccNotesParen",
         # 一键更新那行的外壳同理：组件名（后端给的失败原因）——括号里那句是人家的话，不是界面文案
         "settings.compAllReason"}
zh_plain = [k for k, v in DICT["zh"].items()
            if not CJK.search(str(v)) and latin.search(str(v)) and k not in F6_OK]
ck("F6 zh 那份每条要么含中文、要么只是不含字母的标点（词表里的分隔符）——不许混进其实是英文的条目",
   not zh_plain, str(zh_plain[:6]))
# 专有名词照抄才是对的：这几条两边一致不算「没翻」
F7_OK = {"settings.platformYoutube", "settings.platformTwitch", "settings.optFlv", "settings.optHls"}
same = [k for k in set(DICT["zh"]) & set(DICT["en"])
        if DICT["zh"][k] == DICT["en"][k] and k not in F7_OK]
ck("F7 en 那份没有哪条与 zh 一字不差（那样等于根本没翻）", not same, str(same[:6]))
en_cjk = [k for k, v in DICT["en"].items() if CJK.search(str(v))]
ck("F8 en 那份没有哪条还含中文（含了就是这条根本没翻）", not en_cjk, str(en_cjk[:6]))

# ---------------------------------------------------------------- H. 日志的键通道
print("== H. 运行日志：正文照旧落中文，英文界面按 k/kv 现拼 ==")
import threading   # 只为搭一个 LogManager 的替身；套件的 E5 闸门管的是网络与 spawn
import types

LOG_BODY = block(SERVER_SRC, "    def log(self, message: str", "\n    def get(")
ck("H1 log() 接了 k/kv，且只在给了键时才往条目里加字段",
   'k: str = "", kv: dict | None = None' in LOG_BODY and "if k:" in LOG_BODY
   and 'entry["k"] = k' in LOG_BODY and 'entry["kv"] = dict(kv or {})' in LOG_BODY,
   LOG_BODY.strip().splitlines()[0][:90] if LOG_BODY.strip() else "抠不到 log() 的函数体")
ck("H2 进内存与落盘的都是同一个 entry：message 排第一手，英文渲染不进文件",
   '"message": message,' in LOG_BODY and "f.write(json.dumps(entry" in LOG_BODY)

# 真跑一次 log()：LOG_FILE 是调用时才读的模块全局，临时挪到 %TEMP%，不碰项目的 app.log
_box_path = Path(tempfile.gettempdir()) / "i18n_logbox.log"
_real_log_file = S.LOG_FILE
_box = types.SimpleNamespace(_lock=threading.Lock(), entries=[], max_entries=5, _seq=0,
                             _day=S.datetime.now().strftime("%Y-%m-%d"))
S.LOG_FILE = _box_path
try:
    S.LogManager.log(_box, "[界面] 保存设置（2 项变更）", "info", k="log.settings_saved", kv={"n": 2})
    S.LogManager.log(_box, "没有键的一句")
    _written = _box_path.read_text(encoding="utf-8")
finally:
    S.LOG_FILE = _real_log_file
    _box_path.unlink(missing_ok=True)
e0, e1 = _box.entries[0], _box.entries[1]
ck("H3 带键的条目：k/kv 存下来了，message 仍是那句中文原话",
   e0.get("k") == "log.settings_saved" and e0.get("kv") == {"n": 2}
   and e0["message"] == "[界面] 保存设置（2 项变更）", str(e0))
ck("H4 没带键的条目：一个多余字段都不塞（旧条目与读它的代码不受影响）",
   "k" not in e1 and "kv" not in e1, str(sorted(e1)))
ck("H5 写进日志文件的就是这份条目（键在，正文也在，没有按语言分两份）",
   '"k": "log.settings_saved"' in _written and "[界面] 保存设置（2 项变更）" in _written
   and "没有键的一句" in _written, f"{len(_written.splitlines())} 行")

kv_junk = S._clean_log_kv({"n": 3, "ok": True, "rate": 1.5, "name": "  挤 掉   空白  ",
                           "bad key": 1, "big": "x" * 200, "obj": {"a": 1},
                           **{f"k{i}": i for i in range(12)}})
ck("H6 埋点参数进日志前先收口：只留标量、键名合规、字符串截断、条数封顶（乱键不占名额）",
   kv_junk == {"n": 3, "ok": True, "rate": 1.5, "name": "挤 掉 空白", "big": "x" * 80,
               "k0": 0, "k1": 1, "k2": 2},
   str({k: (v if not isinstance(v, str) or len(v) < 20 else f"{len(v)} 字") for k, v in kv_junk.items()}))
ck("H7 键形不对就不当键用（浏览器不能把任意字符串塞成 k）",
   S._LOG_KEY_RE.fullmatch("log.settings_saved") and S._LOG_KEY_RE.fullmatch("ui.lang_en")
   and not S._LOG_KEY_RE.fullmatch("随便一句话") and not S._LOG_KEY_RE.fullmatch("nav.")
   and not S._LOG_KEY_RE.fullmatch("a.b.c.d.e.f"),
   str([bool(S._LOG_KEY_RE.fullmatch(x)) for x in ("log.settings_saved", "随便一句话", "a.b.c.d.e.f")]))
ui_body = block(SERVER_SRC, "def api_ui_event(body: UiEventBody):", "\n\n")
ck("H8 埋点接口把 k/kv 交给 log()，键形不过关就退化成只记那句人话",
   'k = str(body.k or "")[:80]' in ui_body and "if k and not _LOG_KEY_RE.fullmatch(k):" in ui_body
   and 'log_mgr.log(f"[界面] {text}", level, k=k, kv=_clean_log_kv(body.kv) if k else None)' in ui_body)
ck("H9 后端带键的那句，与词表 zh 的值是同一句（漂了中文界面就会显示另一套话）",
   DICT["zh"].get("log.settings_saved") == "[界面] 保存设置（{n} 项变更）",
   repr(DICT["zh"].get("log.settings_saved")))
log_keys = [k for k in DICT["zh"] if k.startswith(("log.", "ui."))]
bad_pre = [k for k in log_keys
           if (k.startswith("log.") and not DICT["zh"][k].startswith("[界面] "))
           or (k.startswith("ui.") and ("[界面]" in DICT["zh"][k] or "[界面]" in DICT["en"][k]))
           or (k.startswith("ui.") and not DICT["en"][k].startswith("[UI] "))]
ck("H10 前缀分工没写反：log.* 的 zh 带「[界面] 」（后端拼进 message 的就是它），"
   "ui.* 的 zh 不带（前缀由 /api/ui_event 加）、en 自带「[UI] 」",
   bool(log_keys) and not bad_pre, f"log/ui 键 {len(log_keys)} 个，写反的 {bad_pre}")
ck("H11 前端只在英文界面、且这个词两份都在时才拼；中文界面永远是后端原话",
   "if (!e || !e.k || uiLang.value !== 'en') return msg;" in HTML and "MD_I18N.has(e.k)" in HTML)
ck("H12 搜索按渲染结果匹配（英文态不敲服务端那句中文原话）",
   "logText(e).toLowerCase().includes(k)" in HTML
   and 'search: uiLang.value === \'en\' ? \'\' : logSearch.value,' in HTML)
ck("H13 语言切换那句埋点走的是键，不再手拼中文句子",
   "logAction('ui.lang_' + pref);" in HTML and "logAction('切换界面语言为「'" not in HTML)
ck("H14 日志行渲染的是 logText(e)，不是裸 e.message", "{{ logText(e) }}" in HTML
   and "{{ e.message }}" not in HTML)
ck("H15 停在日志页切语言会重取一次（搜索是按当时语言筛的）",
   "if (page.value === 'log') loadLogs();" in block(HTML, "function setLang(key) {", "\n        }\n"))
ck("H16 藏原文时连键一起藏：不然英文界面会照 kv 把那句话再拼出来",
   "k: leaky ? '' : (hasK ? String(textOrKey) : '')," in HTML
   and "kv: leaky ? null : params," in HTML)

# ---------------------------------------------------------------- I. 逐页正文闸门
print("== I. 逐页推进：翻完的那几页，块里除注释以外不许再有中文 ==")
MARKS = [(m.group(1), m.start()) for m in
         re.finditer("""<div v-(?:show|if)="page === '(\\w+)'">""", HTML)]
ck("I1 17 个页面块全抠到了（一页一块，按使用频率一批一页地翻）",
   len(MARKS) == 17 and len(set(k for k, _ in MARKS)) == 17, f"{len(MARKS)} 块")


def page_block(name: str) -> str:
    """这一页的模板块：到下一页的起点为止；最后一页（设置）到常驻播放条的注释为止"""
    at = [i for i, (k, _) in enumerate(MARKS) if k == name]
    if not at:
        return ""
    i = at[0]
    start = MARKS[i][1]
    end = MARKS[i + 1][1] if i + 1 < len(MARKS) else HTML.find("<!-- 底部常驻播放条", start)
    return HTML[start:end] if end > start else ""


def strip_comments(src: str) -> str:
    return re.sub(r"<!--.*?-->", "", src, flags=re.S)


PAGES_DONE = ["home", "queue", "bt", "files", "subs", "music", "settings", "tg", "sniff", "live", "info", "search", "favs", "library", "voice", "history", "log"]   # ← 每翻完一页把页名加进来；登记了却没翻干净会被 I3 判红
ck("I2 PAGES_DONE 都是真有的页", all(page_block(k) for k in PAGES_DONE),
   str([k for k in PAGES_DONE if not page_block(k)]))
for _pg in PAGES_DONE:
    _body = strip_comments(page_block(_pg))
    _left = [ln.strip()[:46] for ln in _body.splitlines() if CJK.search(ln)]
    ck(f"I3[{_pg}] 模板块里没有中文残留（注释不算，它在讲代码）", not _left, str(_left[:4]))
    _used = sorted(set(re.findall(r"\btr\(\s*'([^']*)'", _body)))
    ck(f"I4[{_pg}] 这一页用到的键两份词表都有（缺了英文界面就印键名）",
       all("." in k or k for k in _used) and not [k for k in _used if k not in DICT["zh"] or k not in DICT["en"]],
       str([k for k in _used if k not in DICT["zh"] or k not in DICT["en"]]))
PAGE_HANDLERS = {
    # 这一页的模板翻干净了还不算：点下去弹的那句提示是脚本里拼的，也得跟着翻
    "home": ["applyPreset", "pasteUrl", "clipAdd", "clipIgnore", "startDownload", "stopAll",
             "importUrlFile", "onUrlFile", "browsePath", "doAnalyze", "analyze",
             "pasteAnalyzeUrl", "downloadSpecificFormat", "downloadQualityPreset"],
    "queue": ["retryFailed", "editTaskHeaders", "retrySelected", "cleanupParts", "clearFinished",
              "toggleSelect", "toggleSelectAll", "pauseSelected", "resumeSelected", "deleteSelected",
              "pinSelected", "unpinSelected", "moveTopSelected", "laterSelected", "startLaterSelected",
              "pauseAll", "resumeAll", "resetThrottle", "gotoTask", "notifyDone",
              "statusLabel", "taskHeadline", "taskSpecTitle", "taskSpec"],
    # 磁力 / 种子页：卡片模板与队列共用（task.* / status.*），这一页自己的动作全在这里登记。
    # 同页还调的 saveSettings（设置页那一批）与 friendlyError（排在界面路径翻完之后）没登记，
    # 它们各自的中文行数仍然在下面的脚本区残留计数里看得见。
    "bt": ["btSourceLabel", "applyBtSelect", "testBtRule", "seedTotals", "seedReadout",
           "stopSeed", "stopAllSeeding", "checkAria2", "installAria2", "btTrackerHead",
           "btTrackerProblems", "loadBtTrackers", "refreshBtTrackers", "applyBtLimit",
           "onTorrentFile", "pasteBt", "startBtDownload"],
    # 文件页：目录浏览、在线播放的逐句校对与字幕质检、烧录、流水线、批量字幕。
    # burnStatusText 也翻过，但它是 computed、js_fn() 只抠得到 function，所以没登记在这里；
    # 它那一行「进行中」由下面的脚本区残留计数兜着，改回中文会红。
    "files": ["clearArchive", "deleteFile", "exportBilingualSelected", "goParentDir",
              "loadFiles", "onFileRowClick", "onFileSortChange", "openDownloadFolder",
              "openSrtEditor", "qcDropNoise", "rerunStage", "runBatchAi",
              "runSrtCalibrateSelected", "runSrtQc", "runSrtRewrap", "srtCloseEdit",
              "srtDiscard", "srtSave", "startBurn", "stopBurn", "zipPath"],
    # 订阅页：一张表 + 规则 / 回填 / 同步计划预览三张卡。subStatus 也登记（那一列的四个状态词
    # 是脚本里给的）。两个 one-liner（closeSubBackfill / closeSubRules）没登记：
    # js_fn() 是从下一行开始找到第一个单独成行的 }，一行的函数会把后面整个函数体一起抠进来，
    # 登记它俩等于把 runSubBackfill / saveSubRules 数第二遍。
    "subs": ["addSub", "removeSub", "toggleSub", "setSubAuto", "scanOneSub", "openSubBackfill",
             "runSubBackfill", "scanAllSubs", "openSubPlan", "closeSubPlan", "loadSubPlan",
             "runSubPlanNow", "clearSubArchive", "openSubRules", "saveSubRules", "subStatus"],
    # 音乐页：搜索表 + 歌单解析 + 自建收藏清单 + musicdl 安装。选项表的标签这次改成渲染时现取
    # （musicQualityOptions / musicPresetOptions 都换成了 computed），所以「切语言不用重新问后端」，
    # 后端 quality_options 只留原始值在 musicQualityRaw 里。ensureMusicStatus 也登记：它以前在脚本里
    # 拼「16bit 以上」那几张表。startNeteaseQr / pollNeteaseQr 在本页脚本里但不归这批（设置页那一批）。
    "music": ["ensureMusicStatus", "qualitySpecLabel", "searchMusic", "batchSearchDownload",
              "fetchRowLyrics", "playerLoad", "playFrom", "previewMusicRow", "probeMusicRow",
              "switchMusicSource", "refHint", "matchHint", "openRefLink", "scanLocalMusic",
              "saveMusicStrategy", "applyMusicPreset", "saveMusicPlaylistMode", "parseMusicPlaylist",
              "watchMusicBatch", "showAlreadyHave", "showUnmatched", "onMusicSelection",
              "downloadMusicSelected", "downloadMusicRow", "onMusicSortChange", "onMusicFavSelection",
              "addMusicFav", "removeMusicFav", "clearMusicFav", "previewMusicFav", "switchMusicFav",
              "downloadMusicFav", "loadMusicFavs", "installMusicdl", "showCoverMiss"],
    # 设置页：这一页的模板最早翻干净（594 行中文那一批），但真正的话一半在脚本里拼——
    # 名单是从设置页模板调到的处理器沿调用链铺出来的（tmp/settings_closure.py），
    # 不是按卡片手挑的：这一页的按钮背后还套着 load* / apply* / ccCall 那几层，漏一层就会有一句中文
    # 从「保存设置」的报错里冒出来。共用的底座没登记在这里：api / logAction / actionName /
    # friendlyError / loadConfig / loadStatus / applyTheme / applyDark / applyLang / maybePopupCompUpdates
    # / loadSubs —— 它们剩下的中文各自属于 ACTION_NAMES 埋点、friendlyError 那 22 条分支、
    # 日志的 log.* 键与后端原话比较那几批，登记进来只会让 I5 报在设置页头上。
    "settings": [
        "applyAuthPassword", "applyCompCheck", "applyNcQrResult", "applyOutbox",
        "applyRiskPreset", "browsePlatformCookie", "ccApply", "ccCall",
        "changedKeys", "checkEnv", "checkGlossary", "checkPoToken",
        "checkRunWindows", "checkSpeedWindows", "clDescribe", "clGroupList",
        "clRun", "clearCookieCloudKey", "clearCookieFlag", "clearMusicCookie",
        "clearOutbox", "compUpdatable", "copyMachineToken", "defBrief",
        "downloadExtension", "exportSync", "fetchCompCheck", "fmtWait",
        "formatSize", "installVoicePkgs", "loadAuthStatus", "loadCleanup",
        "loadCleanupTrash", "loadComponents", "loadConfigDefaults", "loadCookieCloud",
        "loadEncoders", "loadMusicCookies", "loadNetInfo", "loadOutbox",
        "loadPlatformCookies", "loadVoiceStatus", "markSaved", "mergeCompLatest",
        "mirrorHint", "mirrorLabel", "netOverrideValue", "netVerdictText",
        "onImportSync", "pendingAutoSave", "pollBiliQr", "pollNeteaseQr",
        "previewCleanup", "probeMirrors", "pullCookieCloud", "pushCookieCloud",
        "refreshRunWindow", "reloadPlugins", "resetAllDefaults", "resetKeys",
        "resetNetwork", "restoreAllTrash", "restoreTrash", "retryOutbox",
        "rotateMachineToken", "runCleanup", "runOneGroup", "saveAcoustid",
        "saveAuthKnobs", "saveCleanup", "saveCookieCloud", "saveMusicCookie",
        "savePlatformCookie", "savePlatformCookieText", "saveSettings", "setEnvPath",
        "setFlags", "setProxyOverride", "setTheme", "startBiliQr",
        "startCompAllPoll", "startCompCheck", "startNeteaseQr", "stopCompAllPoll",
        "testCookie", "testCookieCloud", "testStorage", "testTelegram",
        "testWecom", "toggleDark", "triggerImportSync", "unlockAll",
        "unlockIp", "updateAllComponents", "updateComponent", "updateFfmpeg",
        "updateNm3u8", "updateWhisper", "updateYtdlp", "useSystemProxy",
        "verCmp", "waitCompCheck",
    ],
    # Telegram 频道页：匿名 / 账号会话两套界面共用一个卡片，会话那套的凭据框与登录流程都在本页脚本里。
    # 名单来自 tmp/tg_scope.py（模板直接调到的 + 沿调用链铺出来的）。五个 one-liner 没登记
    # （downloadTgSelected / downloadTgRow / openTgRow / tgRowSelectable / tgTypeLabel）：
    # js_fn() 会把它们后面整个函数体一起抠进来，登记等于把 tgEnqueue 数第二遍。
    # 共用的 onPaste 也没登记（bt / music 那两批同样没登记它）：它只做粘贴归一、本体没有话术，
    # 而且六个页面都在用，归到任何一页都会让 I5 报在错的人头上。
    "tg": ["clearTgResults", "copyTgUrls", "gotoSubsAdd", "listTgChannel", "loadTgMtStatus",
           "onTgSortChange", "saveTgMtConfig", "tgAckProtected", "tgEnqueue",
           "tgMtLogout", "tgMtSendCode", "tgMtSignIn"],
    # 嗅探页：三张卡（浏览器 CDP 嗅探 / 静态页面嗅探 / 接收猫抓推送）都在同一段模板里，
    # 名单来自 tmp/sniff_scope.py（模板调用点 + 一层铺出来的 pollBrowserSniff）。
    # 遇到共用底座就停：sniffDownloadSelected 背后那串 loadTasks → applyTaskList → notifyDone
    # 归队列页，登记过来只会把同一句中文数两遍、报在错的页头上。
    # copyText 同样没登记（六页共用，那两枚「已复制 / 复制失败」跟着共用底座那一批收）；
    # sniffSelectNone 是一行的函数，js_fn() 会把后面整个函数体一起抠进来，登记等于把 runSniff 数两遍。
    "sniff": ["clearBrowserSniff", "clearCatcatchRules", "deleteCatcatchRule", "loadCatcatch",
              "onCatcatchConfig", "pollBrowserSniff", "runSniff", "sniffDownloadMerge",
              "sniffDownloadOne", "sniffDownloadSelected", "sniffSelectAll", "startBrowserSniff",
              "stopBrowserSniff", "toggleCatcatchRule", "triggerCatcatchImport"],
    # 直播页：录制卡片 + 监控房间表 + 本房间设置弹窗 + 任务卡片，四张卡共用一段模板。
    # 名单是这一页模板调到的处理器（含一层铺出来的 loadLiveMonitors）。
    # liveDefaultMinutesText 是个 computed，登记进来靠的是 js_fn() 后来支持抠 computed 的函数体
    # （不登记它就等于给这一页留了个没人看的洞：词表键在、闸门看不见）。
    # isLiveRunning / fileBasename 没登记：一个谓词一个路径工具，本体没有话术，
    # 而且 fileBasename 是队列与文件页共用的。
    "live": ["startLiveRecord", "endAllLive", "endLiveTask", "cancelLiveTask", "pauseLiveTask",
             "resumeLiveTask", "openLiveFile", "clearFinishedLiveTasks", "liveAutoSaveText",
             "liveDefaultMinutesText", "addLiveMonitor", "removeLiveMonitor", "pauseLiveMonitor",
             "resumeLiveMonitor", "scanLiveMonitors", "loadLiveMonitors", "openLiveMonitorCfg",
             "saveLiveMonitorCfg", "liveMonitorCfgText"],
    # 解析页（info）：模板里那些清晰度芯片、编码芯片、区间勾选弹层都是这一页自己的话。
    # downloadSpecificFormat / downloadQualityPreset / pasteAnalyzeUrl 归 home 那一批（它们最早是给
    # 下载页那一串动作写的，同一函数登记两遍只会把同一句中文数两次）；analyze / doAnalyze 同理。
    # copyText 仍然没登记（七页共用，「已复制 / 复制失败」跟共用底座那一批收）。
    # tierSizeText / infoCodecOptions 是 computed 但它是这一页上屏的那句话，照 live 页的先例登记；
    # tierSizeGroup 是它唯一的调用者，「最佳」那一档的名字就在里面，漏登记等于这一句没人看。
    "info": ["analyzeFromInfoPage", "downloadFromInfo", "downloadAllEntries",
             "downloadSelectedEntries", "downloadEntry", "entryAt", "selectEntryRange",
             "clearEntrySel", "copyFormats", "tierSizeGroup", "tierSizeText", "infoCodecOptions"],
    # 聚合搜索页：三张名字表（平台 / 内容类型 / 排序）现在存的是键名，取值处现翻 ——
    # 语言是运行时切的，模块初始化时把中文焊死就翻不动了。后端来的那条原因（n.text）仍显示原文。
    "search": ["doSearch", "setSearchSort", "normalizeSearchUrl", "downloadSearchItem",
               "analyzeSearchItem", "subscribeSearchItem"],
    # 收藏关注页：六个标签 + 三张表头 + 两个批量按钮，加上这一页弹出来的那九句。
    # applyFavList 也登记：它是这三张卡的共同出口，那句埋点行归 ACTION_NAMES 那一批、由 I8 数着。
    # onFavSelChange 没登记：它是一行的函数，js_fn() 会把后面整个函数体一起吞进来（同 subs 页那两个 one-liner）。
    "favs": ["applyFavList", "loadFavTab", "loadFavFolderItems", "loadYtPlaylist", "onFavSortChange",
             "downloadFavSelected", "downloadFavOne", "subscribeFavSelected", "subscribeFavOne"],
    # 资源库页：九列表头 + 音质核对那一段汇总 + 这一页弹出来的句子。
    # libQaTag 也登记：QA_TAGS 那张表从「存字面」改成「存键名」，上屏的那句话只在取值处才拼得出来。
    # toggleSort / sortIcon / applySort / libAudioText / formatSize / formatDuration 没登记：
    # 前四个是全工程共用的排序与格式化底座（本体没有话术，埋点那句在 logSort 里、归 ACTION_NAMES 那一批），
    # 后两个早已登记在 settings 那一批里 —— 同一函数数两遍只会把同一句中文报在错的页头上。
    "library": ["loadLibrary", "checkLibraryQuality", "libQaTag", "runTranscode", "openLibFolder"],
    # 语音工具页：三张卡（依赖 / 人声分离 / 准实时转写）+ 分离那几张只在这页读的数。
    # setupSeparator 登记的是本体：外面那两枚（setupSeparatorEnv / setupSeparatorWeights）是一行的函数，
    # js_fn() 会把后面整个函数体一起抠进来，登记等于把 setupSeparator 数两遍。
    # loadVoiceStatus / installVoicePkgs 已登记在 settings 那一批（同一函数数两遍只会把同一句中文
    # 报在错的页头上）；refreshSepStatus 本体没有话术，上屏的是 sepStatusText 那句。
    # SEP_MODEL_NAMES 那张表存的是产品名（BS-RoFormer 12.97 等），本来就没有中文，不转键名。
    "voice": ["sepStatusText", "sepDeviceText", "sepEngineReason", "sepModelLabel",
              "setupSeparator", "toggleRealtime"],
    # 下载历史页：四格统计 + 六个表头 + 两枚批量按钮 + 行内两枚，加上清空确认框与打开文件夹那三条回执。
    # statusLabel / statusType / toggleSort / sortIcon 没登记：前两个已记在 queue 那一批（状态列的
    # 五个词是共用的），后两个是全工程共用的排序底座，本体没有话术、埋点那句在 logSort 里归 ACTION_NAMES。
    # redownload 与 loadHistory / exportHistory 本体一句界面文字都没有，登记进来是为了「以后有人往里加中文会红」。
    "history": ["loadHistory", "exportHistory", "clearHistory", "redownload", "openHistoryFile"],
    # 运行日志页（最后一页）。logText / logMatches 也登记：它们现在一句中文都没有，
    # 但这两处正是以后最容易顺手拼中文的地方（渲染侧一拼中文，英文界面就漏）。
    "log": ["loadLogs", "logText", "logMatches", "clearLogs", "openLogDir", "exportDiagnostics"],
}
# 允许留中文的处理器：这些行比的是后端发来的数据（预设名、占位标题），翻成英文这行判断就失效。
# 「允许留下」不等于「不用管」——残留的行数和那几句都钉死，改了名字或悄悄多出一行都判红
RESIDUE = {
    "downloadQualityPreset": ["仅音频"],
    "taskHeadline": ["等待中..."],
    # 按龄清理的报错：这句是在比后端原话里有没有「名单」两个字（后端给的 message 仍是中文），
    # 翻成英文这行判断就永远不成立。
    "clRun": ["名单"],
}


def js_fn(name: str) -> str:
    """取 index.html 里这个 setup 函数的函数体（八个空格那一层的 } 收尾）

    函数抠不到时再认一种写法：computed 属性。直播页那句「录满 N 分钟自动保存」的读数
    就是这么写的，登记成处理器却抠不到等于整页白翻没人看 —— 一行的 computed 仍然抠不到
    （会把后面整个函数体一起吞进来），那种留在下面的整行断言里钉。
    """
    m = re.search(r"^        (?:async )?function %s\(" % re.escape(name), HTML, flags=re.M)
    tail = "\n        }\n"
    if not m:
        m = re.search(r"^        const %s = computed\(\(\) => \{" % re.escape(name), HTML, flags=re.M)
        tail = "\n        });\n"
    if not m:
        return ""
    start = HTML.index("\n", m.start()) + 1
    end = HTML.find(tail, start)
    return HTML[start:end] if end > start else ""


def strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^[ \t]*//.*$", "", src, flags=re.M)


ck("I5a 每个登记了处理动作的页名都是真有的页",
   all(k in [m[0] for m in MARKS] for k in PAGE_HANDLERS), str(list(PAGE_HANDLERS)))
_registered = {f for _fns in PAGE_HANDLERS.values() for f in _fns}
ck("I5b 每个允许留中文的处理器都登记在某一页里（漏登记就没人盯它了）",
   all(f in _registered for f in RESIDUE), str([f for f in RESIDUE if f not in _registered]))
# 埋点那一句（uiName / logAction 的动作名）是发给后端进运行日志的记录，排在 ACTION_NAMES 那一批再收。
# I5 不算它，但每一页有几条要钉住：悄悄多出一条埋点，或者那一批改完忘了删这里的名额，都会判红。
# uiName 认到冒号为止：音乐页那条是三元表达式（勾选行 / 整单两种说法），值不写在引号里，也只算一行。
# logAction 认到左括号为止、ccCall 同理：设置页那一批把句子换成了 tr(...)，动作名却在参数里留着中文，
# 这两种写法都要认得到，否则「翻完了」会表现为埋点行凭空少几条。
MAIDIAN = re.compile(r"""uiName:|logAction\(|logSort\(|ccCall\(""")
MAIDIAN_EXPECT = {"home": 0, "queue": 0, "bt": 7, "files": 4, "subs": 0, "music": 5, "settings": 17, "tg": 1,
                  "sniff": 0, "live": 0, "info": 0, "search": 0,
                  # applyFavList 那句 logAction（ tab 名来自 FAV_TAB_NAMES）+ onFavSortChange 那句 logSort
                  "favs": 2,
                  # 这一页五个处理器里没有埋点行：loadLibrary / runTranscode 那两次 api 都没带 uiName，
                  # 点表头的留痕在共用的 logSort 里，跟 ACTION_NAMES 那一批一起收
                  "library": 0,
                  # toggleRealtime 那两句 logAction（开始 / 停止准实时转写）等 ACTION_NAMES 那一批
                  "voice": 2,
                  # 这一页五个处理器里没有埋点行：清历史与打开文件夹都只调 api()，没带 uiName；
                  # 点表头那次的留痕在共用的 logSort 里（histSort.t 的「下载历史」也归 ACTION_NAMES 那一批）
                  "history": 0,
                  # 这一页两行：openLogDir 的 uiName '打开日志文件夹' 与 exportDiagnostics 收尾那句
                  # logAction(done + '（失败）')。动作名本身归 ACTION_NAMES 那一批，落盘侧不跟界面语言。
                  "log": 2}
# 来源类型那一列的名字与提示：键不是写在 tr(' …') 里而是存在表里（labelKey / hintKey），
# 上面那遍字面扫抓不到它们，所以单独比一遍 —— 少哪一份英文界面就印键名
kind_meta = block(HTML, "const SUB_KIND_META = {", "};")
kind_keys = re.findall(r"(?:labelKey|hintKey): '([^']*)'", kind_meta)
ck("I9 来源类型表里的键两份词表都有，且四类来源的提示一个都没漏",
   len(kind_keys) >= 6 and not [k for k in kind_keys if k not in DICT["zh"] or k not in DICT["en"]],
   f"{len(kind_keys)} 个键，缺：{[k for k in kind_keys if k not in DICT['zh'] or k not in DICT['en']]}")
# Telegram 那张类型表也存的是键（labelKey），渲染处 tr(t.labelKey)：上面 I4 那遍只认 tr(' 后面，
# 键名写在表里它抓不到，所以单独比一遍 —— 少哪一份，下拉与表格那一列就印 tg.typeVideo 这种原文。
tg_type_blob = block(HTML, "const tgTypeOptions = [", "];")
tg_type_keys = re.findall(r"labelKey: '([^']*)'", tg_type_blob)
tg_type_miss = [k for k in tg_type_keys if k not in DICT["zh"] or k not in DICT["en"]]
ck("I10 Telegram 类型表五个键两份词表都有，表里也不留第二份 label",
   len(tg_type_keys) == 5 and not tg_type_miss and "label:" not in tg_type_blob,
   f"{len(tg_type_keys)} 个键，缺：{tg_type_miss}")
# 分隔符这类字符（· ， 、）到底算文案还是算排版，两边写重了只有浏览器看得出来：
# 值里带「·」、模板那一行又留了一份，界面印成「· ·」；反过来值里没有、模板里的空格又被 Vue 压掉，
# 点前少一个空格。 sniff 页撞上的正是第一种（sniff.ccLast 与它前面那个字面「·」），活体 A/B 量出来的。
# 认的是「同一个分隔符在插值两边紧邻的模板文本里又出现了一次」，两边都不许。
SEP_CH = "·，、；,·"
_tr_hit = re.compile(r"\{\{\s*tr\('([\w.-]+)'\s*[,)]")


def sep_dupes(tpl: str, zh: dict, en: dict) -> list:
    out = []
    for m in _tr_hit.finditer(tpl):
        k = m.group(1)
        ls = tpl.rfind("\n", 0, m.start()) + 1
        gap_b = tpl[max(tpl.rfind("}}", ls, m.start()), ls):m.start()]
        ne = tpl.find("{{", m.end())
        ne = len(tpl) if ne < 0 else ne
        after = tpl[m.end():ne]
        gap_a = after[after.find("}}") + 2:] if "}}" in after else after
        for half, d in (("zh", zh), ("en", en)):
            v = d.get(k) or ""
            if not v:
                continue
            if v[0] in SEP_CH and v[0] in gap_b:
                out.append("%s/%s 值开头那个「%s」，模板前面又写了一遍：%r" % (half, k, v[0], gap_b[-46:]))
            if v[-1] in SEP_CH and v[-1] in gap_a:
                out.append("%s/%s 值结尾那个「%s」，模板后面又写了一遍：%r" % (half, k, v[-1], gap_a[:46]))
    return out


_sep_now = sep_dupes(TEMPLATE, DICT["zh"], DICT["en"])
ck("I11a 模板与词表没有把同一个分隔符各写一份", not _sep_now, str(_sep_now[:4]))
# 反向对照：把 ccLast 的 zh 改回带点的那份写法，上面那条必须报错 —— 不然它可能是空转
_probe = dict(DICT["zh"])
_probe["sniff.ccLast"] = "· 最近一次 {at}"
ck("I11b 分隔符那条闸门自己会响（把 ccLast 的 zh 改回带点的写法必须判红）",
   bool(sep_dupes(TEMPLATE, _probe, DICT["en"])))
# 直播任务那一筛比的是后端发来的标题里有没有「直播」两个字（is_live 之外的兜底），
# 翻成英文这一筛就永远为空。它是一行的 computed，js_fn() 抠不到（会把后面整个函数体一起吞进来），
# 所以整行钉住：换写法或把这个词翻掉，这里判红。
ck("I12 liveTasks 仍按后端原话「直播」筛（翻了这一行直播页就空了）",
   "const liveTasks = computed(() => tasks.value.filter(t => t.is_live || (t.title || '').includes('直播')));"
   in HTML)
# formatCount 只有搜索页一处调用（正文里那行「UP · 1.2万 次播放」），它是这页英文界面唯一的
# 中文残留来源：活体 A/B 量到英文页上印着 16.0亿/1.2万。两套断点必须按语言分开钉住 ——
# 中文那支的字面与阈值一个字节都不能动（A/B 的中文逐行等式靠它），英文那支不许漏出 万/亿。
_fc_body = js_fn("formatCount")
_zh_at = _fc_body.find("uiLang.value !== 'en'")
_en_at = _fc_body.find("if (n >= 1e9)")
ck("I13a formatCount 抠到了、两支都在（改名或挪走要连带改这一闸门）",
   bool(_fc_body) and 0 <= _zh_at < _en_at, f"body={bool(_fc_body)} zh={_zh_at} en={_en_at}")
_fc_zh, _fc_en = _fc_body[_zh_at:_en_at], _fc_body[_en_at:]
ck("I13b 中文那支仍是 1e4/1e8 + 万/亿（切英文不该动中文读数）",
   "'亿'" in _fc_zh and "'万'" in _fc_zh and "n >= 1e8" in _fc_zh and "n >= 1e4" in _fc_zh,
   repr(_fc_zh[:120]))
ck("I13c 英文那支用 K/M/B，且这一支里不许再有中文",
   "'B'" in _fc_en and "'M'" in _fc_en and "'K'" in _fc_en and not CJK.search(_fc_en),
   repr(_fc_en[:120]))
for _pg, _fns in PAGE_HANDLERS.items():
    _md = 0
    for _fn in _fns:
        _b = js_fn(_fn)
        if not _b:
            ck(f"I5[{_pg}.{_fn}] 这个处理器抠到了", False, "找不到函数体（改名了？）")
            continue
        _left = [ln.strip() for ln in strip_js_comments(_b).splitlines() if CJK.search(ln)]
        _nowords = [ln for ln in _left if not MAIDIAN.search(ln)]
        _md += len(_left) - len(_nowords)
        if _fn in RESIDUE:
            _exp = RESIDUE[_fn]
            ck(f"I6[{_pg}.{_fn}] 残留只有比后端数据的那 {len(_exp)} 行",
               len(_nowords) == len(_exp) and all(x in ln for x, ln in zip(_exp, _nowords)),
               str([ln[:60] for ln in _nowords]))
        else:
            ck(f"I5[{_pg}.{_fn}] 处理动作弹给用户的句子全走词表", not _nowords, str(_nowords[:3]))
    ck(f"I8[{_pg}] 埋点动作名仍只有 {MAIDIAN_EXPECT[_pg]} 行在等 ACTION_NAMES 那一批",
       _md == MAIDIAN_EXPECT[_pg], f"实际 {_md} 行")
# 模板里调用的处理器必须出现在 setup 的 return 名单里：漏一个不是「那一行不显示」，
# 是整页渲染抛错 —— 静态切片看不出来，只有浏览器里才炸（沙箱实测就是这么撞上的）
_ret_at = HTML.rindex("statusType, statusLabel,")
RETURNED = HTML[HTML.rindex("return {", 0, _ret_at):HTML.index("};", _ret_at)]
_defs = set(re.findall(r"^ {8}(?:async )?function ([a-z][A-Za-z0-9_]*)\(", HTML, flags=re.M))
_cands = set()
for _pg in PAGES_DONE:
    _cands |= set(re.findall(r"\b([a-z][A-Za-z0-9_]*)\s*\(", strip_comments(page_block(_pg))))
_missing = sorted(n for n in _cands if n in _defs and n not in RETURNED)
ck("I7 登记过的页里，模板调用的处理器都在 setup 的 return 名单里", not _missing, str(_missing))

_todo = []
for _k, _ in MARKS:
    if _k in PAGES_DONE:
        continue
    _b = strip_comments(page_block(_k))
    _todo.append(f"{_k}:{len([ln for ln in _b.splitlines() if CJK.search(ln)])}")
print(f"   还剩 {len(MARKS) - len(PAGES_DONE)} 页未翻（页名:块内中文行数）：" + ", ".join(_todo))
_leak = len([ln for ln in strip_comments(HTML[HTML.find("const ACTION_NAMES"):]).splitlines()
             if CJK.search(ln) and "logAction" not in ln])
print(f"   脚本区（含 ACTION_NAMES 起的埋点表）注释外含中文的行：{_leak} —— 随各页批次一起收")

# ---------------------------------------------------------------- G. node 跑真实行为
print("== G. node：i18n.js 的真实返回值 ==")

JS = r"""
const fs = require('fs');
const OUT = __OUT__;
const SRC = __SRC__;
const ZhCn = { name: 'zh-cn', el: { pagination: { total: '共' } } };
const En = { name: 'en', el: { pagination: { total: 'Total' } } };

function mkWin(opt) {
  opt = opt || {};
  const store = Object.assign({}, opt.store || {});
  const doc = { title: '', documentElement: { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } } };
  const win = {
    localStorage: {
      getItem: (k) => (Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null),
      setItem: (k, v) => { store[k] = String(v); },
    },
    document: doc,
    ElementPlusLocaleZhCn: opt.noZh ? undefined : ZhCn,
    ElementPlusLocaleEn: opt.noEn ? undefined : En,
  };
  if (opt.noNav !== true) {
    win.navigator = opt.navigator === undefined ? { language: opt.lang || 'zh-CN' } : opt.navigator;
  }
  win.window = win;
  new Function('window', SRC)(win);
  return { win: win, I: win.MD_I18N, store: store, doc: doc };
}

const R = {};
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const rec = (name, got, want) => { R[name] = { got: got, want: want, pass: eq(got, want) }; };

let w = mkWin({ lang: 'zh-CN' });
rec('g0_loaded', [!!w.I, typeof w.I.t, typeof w.I.apply], [true, 'function', 'function']);
rec('g1_nav_zh', w.I.t('nav.home', null, 'zh'), '下载解析');
rec('g2_nav_en', w.I.t('nav.home', null, 'en'), 'Parse');
rec('g3_ph_zh', w.I.t('header.active', { n: 3 }, 'zh'), '进行中 3');
rec('g4_ph_en', w.I.t('header.active', { n: 3 }, 'en'), 'Running 3');
rec('g5_unknown', w.I.t('nope.key', null, 'en'), 'nope.key');
rec('g6_ph_leftalone', w.I.t('header.active', null, 'en'), 'Running {n}');
rec('g7_langs', w.I.langs.map((x) => x.key), ['auto', 'zh', 'en']);
rec('g8_lang_names_en', w.I.langs.map((x) => x.name.en), ['Auto (follow browser)', '简体中文', 'English']);

rec('g9_detect_zh_tw', mkWin({ lang: 'zh-TW' }).I.lang, 'zh');
rec('g10_detect_en_us', mkWin({ lang: 'en-US' }).I.lang, 'en');
rec('g11_detect_no_navigator', mkWin({ noNav: true }).I.lang, 'zh');
rec('g12_detect_blank', mkWin({ navigator: {} }).I.lang, 'zh');
w = mkWin({ lang: 'en-US' });
rec('g13_apply_overrides_browser', [w.I.apply('zh'), w.I.t('brand', null, w.I.lang)], ['zh', '多媒体下载器']);

w = mkWin({ lang: 'zh-CN' });
rec('g14_apply_en', w.I.apply('en'), 'en');
rec('g15_apply_en_title', w.doc.title, 'Media Downloader');
rec('g16_apply_en_html_lang', w.doc.documentElement.attrs.lang, 'en');
rec('g17_apply_en_store', [w.store.md_lang, w.store.md_lang_resolved], ['en', 'en']);
rec('g18_apply_bogus_is_auto', [w.I.apply('xyz'), w.store.md_lang], ['zh', 'auto']);
rec('g19_apply_zh_back', [w.I.apply('zh'), w.doc.documentElement.attrs.lang], ['zh', 'zh-CN']);
rec('g20_apply_zh_title', w.doc.title, '多媒体下载器');

w = mkWin({ lang: 'zh-CN', store: { md_lang_resolved: 'en' } });
rec('g21_boot_uses_mirror', [w.I.boot(), w.I.pref], ['en', 'en']);
w = mkWin({ lang: 'en-US', store: { md_lang_resolved: 'zh' } });
rec('g22_boot_mirror_beats_browser', w.I.boot(), 'zh');
w = mkWin({ lang: 'en-US' });
rec('g23_boot_no_mirror', [w.I.boot(), w.I.pref], ['en', 'auto']);
w = mkWin({ lang: 'en-US', store: { md_lang_resolved: '乱写的' } });
rec('g24_boot_bad_mirror', w.I.boot(), 'en');

w = mkWin({ lang: 'zh-CN' });
rec('g25_locale_en', w.I.elementLocale('en') === En, true);
rec('g26_locale_zh', w.I.elementLocale('zh') === ZhCn, true);
rec('g27_locale_default', w.I.elementLocale() === ZhCn, true);
w = mkWin({ lang: 'zh-CN', noEn: true });
rec('g28_locale_en_missing', w.I.elementLocale('en') === ZhCn, true);
w = mkWin({ lang: 'zh-CN' });
rec('g29_locale_never_undefined', [w.I.elementLocale('en'), w.I.elementLocale('zh'), w.I.elementLocale()].every((x) => !!x), true);

// 日志那条线：先问词表有没有这个词，再按语言现拼一句（拼的就是界面上显示的那句）
w = mkWin({ lang: 'zh-CN' });
rec('g30_has_known', [w.I.has('nav.home'), w.I.has('ui.lang_en'), w.I.has('log.settings_saved')], [true, true, true]);
rec('g31_has_unknown', [w.I.has('nav.nope'), w.I.has(''), w.I.has(null), w.I.has('DICT')], [false, false, false, false]);
rec('g32_log_render_en', w.I.t('log.settings_saved', { n: 3 }, 'en'), '[UI] Settings saved (3 change(s))');
rec('g33_log_render_zh', w.I.t('log.settings_saved', { n: 3 }, 'zh'), '[界面] 保存设置（3 项变更）');
rec('g34_ui_key_zh_plain', w.I.t('ui.lang_en', null, 'zh'), '切换界面语言为「英文」');

// 入队成功那句是三截拼起来的：中文这边必须与改前 index.html 里那句模板串一字不差
rec('g35_added_zh_join',
    w.I.t('home.tAdded', { n: 3 }, 'zh') + ' · ' + w.I.t('home.tMerged', { n: 1 }, 'zh')
    + ' · ' + w.I.t('home.tSkippedInvalid', { n: 2 }, 'zh'),
    '已加入 3 个任务 · 已合并 1 条重复 · 2 条链接无效被忽略');
rec('g36_args_zh_join',
    w.I.t('home.tArgsNotApplied', { n: 5, list: ['甲', '乙', '丙'].join(w.I.t('home.tListSep', null, 'zh')) + ' 等' }, 'zh'),
    '「自定义 yt-dlp 参数」有 5 项没生效：甲；乙；丙 等');
// 搜索页那句运行日志：中文这份要与改造前 index.html 里那条模板串一字不差，
// 英文这份证明「键 + kv」落盘后日志页能按当前语言现拼出来（数字与关键词是数据，不跟着翻）
rec('g37_search_log_zh',
    w.I.t('search.log_ran_notes', { q: 'sorry', total: 120, shown: 100, n: 3 }, 'zh'),
    '聚合搜索「sorry」：取回 120 条，显示 100 条，3 条空结果原因');
rec('g38_search_log_en',
    w.I.t('search.log_ran', { q: 'sorry', total: 120, shown: 100, n: 0 }, 'en'),
    'Aggregated search "sorry": got 120, showing 100');

fs.writeFileSync(OUT, JSON.stringify(R));
"""

TMP = Path(tempfile.gettempdir())
RES = TMP / "i18n_result.json"
HARNESS = TMP / "i18n_harness.js"


def run_node() -> dict:
    if subprocess.run(["node", "--version"], capture_output=True, text=True).returncode != 0:
        return {}
    if RES.exists():
        RES.unlink()
    js = JS.replace("__OUT__", json.dumps(str(RES))).replace("__SRC__", json.dumps(I18N_SRC))
    HARNESS.write_text(js, encoding="utf-8")
    p = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True, encoding="utf-8")
    if not RES.exists():
        print("NODE FAIL:", (p.stderr or p.stdout)[:900])
        return {}
    return json.loads(RES.read_text(encoding="utf-8"))


def show(*names) -> str:
    return str({n: {"got": R[n]["got"], "want": R[n]["want"]} for n in names if n in R})


R = run_node()
ck("G0 node 跑通了（本机没有 node 就别假绿）", bool(R), "harness 没产出" if not R else "")
if R:
    names = [k for k in R if k != "g0_loaded"]
    ck("G1 行为读数一条不缺（39 条 rec，除首条装载检查外 38 条）", len(names) == 38, f"{len(names)} 项")
    reds = sorted(k for k in names if not R[k]["pass"])
    ck("G2 这 38 条读数与预期全部一致", not reds, show(*reds[:4]) if reds else "")
    ck("G3 t()：两份词表都取得到、未知键回键名、没传 vars 时占位符原样留着",
       all(R[k]["pass"] for k in ("g1_nav_zh", "g2_nav_en", "g3_ph_zh", "g4_ph_en", "g5_unknown", "g6_ph_leftalone")),
       show("g3_ph_zh", "g4_ph_en", "g5_unknown"))
    ck("G4 detect：zh-CN / zh-TW 判中文，en-US 判英文",
       R["g9_detect_zh_tw"]["pass"] and R["g10_detect_en_us"]["pass"],
       show("g9_detect_zh_tw", "g10_detect_en_us"))
    ck("G5 detect：没有 navigator 或 language 为空时判中文（环境读不出来不该把界面甩成英文）",
       R["g11_detect_no_navigator"]["pass"] and R["g12_detect_blank"]["pass"],
       show("g11_detect_no_navigator", "g12_detect_blank"))
    ck("G6 显式选 zh 压过浏览器（apply('zh') 之后取到的是中文词）", R["g13_apply_overrides_browser"]["pass"],
       show("g13_apply_overrides_browser"))
    ck("G7 apply('en') 同时改了 document.title、<html lang> 与两份 localStorage",
       all(R[k]["pass"] for k in ("g14_apply_en", "g15_apply_en_title", "g16_apply_en_html_lang", "g17_apply_en_store")),
       show("g15_apply_en_title", "g16_apply_en_html_lang", "g17_apply_en_store"))
    ck("G8 apply 认不出的值当 auto（既不抛，也不当成 zh）", R["g18_apply_bogus_is_auto"]["pass"],
       show("g18_apply_bogus_is_auto"))
    ck("G9 apply('zh') 切回来时标题与 lang 一起改（不是只改词表）",
       R["g19_apply_zh_back"]["pass"] and R["g20_apply_zh_title"]["pass"],
       show("g19_apply_zh_back", "g20_apply_zh_title"))
    ck("G10 boot() 优先用上次生效的镜像（英文界面刷新后不闪回中文）",
       R["g21_boot_uses_mirror"]["pass"] and R["g22_boot_mirror_beats_browser"]["pass"],
       show("g21_boot_uses_mirror", "g22_boot_mirror_beats_browser"))
    ck("G11 没镜像时 boot() 跟随浏览器；镜像被写坏时退回 auto 而不是抛",
       R["g23_boot_no_mirror"]["pass"] and R["g24_boot_bad_mirror"]["pass"],
       show("g23_boot_no_mirror", "g24_boot_bad_mirror"))
    ck("G12 elementLocale 按传入语言给（computed 靠这个参数才会重算）",
       R["g25_locale_en"]["pass"] and R["g26_locale_zh"]["pass"] and R["g27_locale_default"]["pass"],
       show("g25_locale_en", "g26_locale_zh"))
    ck("G13 en 的词包没加载上时回 zh-cn，绝不把 locale 传成 undefined",
       R["g28_locale_en_missing"]["pass"] and R["g29_locale_never_undefined"]["pass"],
       show("g28_locale_en_missing", "g29_locale_never_undefined"))
    ck("G14 语言钮的英文名来自同一份 langs（顶栏 tooltip 用的就是它）",
       R["g8_lang_names_en"]["pass"], show("g8_lang_names_en"))
    ck("G15 has() 只认两份都有的键，空串/null/顶层对象名都不算",
       R["g30_has_known"]["pass"] and R["g31_has_unknown"]["pass"],
       show("g30_has_known", "g31_has_unknown"))
    ck("G16 日志的键真能拼出中英两句（含 {n} 代入），ui.* 的 zh 那句不带前缀",
       R["g32_log_render_en"]["pass"] and R["g33_log_render_zh"]["pass"] and R["g34_ui_key_zh_plain"]["pass"],
       show("g32_log_render_en", "g33_log_render_zh", "g34_ui_key_zh_plain"))
else:
    print("（node 不可用，G1~G16 未跑）")

print()
print(f"共 {TOTAL} 项，FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
