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
   没登记的页只报中文行数，不当断言 —— 那是接下来一批一批要清零的债。

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
bad_ph = {k: (PLACE.findall(DICT["zh"][k]), PLACE.findall(DICT["en"][k]))
          for k in set(DICT["zh"]) & set(DICT["en"])
          if sorted(PLACE.findall(DICT["zh"][k])) != sorted(PLACE.findall(DICT["en"][k]))}
ck("A5 同一个键两边的 {n} 占位符一致", not bad_ph, str(bad_ph))
dollar = [f"{lang}.{k}" for lang in ("zh", "en") for k, v in DICT[lang].items() if "${" in str(v)]
ck("A6 词表里没有 JS 模板串残留（${} 在单引号里不会被替换）", not dollar, str(dollar))
ck("A7 值里没有裸露的 HTML 标签（词表只放文字）",
   not re.search(r"<[a-zA-Z/]", "".join(DICT["zh"].values()) + "".join(DICT["en"].values())))
other_ph = [f"{lang}.{k}" for lang in ("zh", "en") for k, v in DICT[lang].items()
            if "%s" in str(v) or "{}" in str(v)]
ck("A8 占位符只用花括号一种写法", not other_ph, str(other_ph))
padded = [k for k, v in DICT["zh"].items() if v != v.strip()]
ck("A9 zh 的词表值不带首尾空格（渲染出来就是错位）", not padded, str(padded[:6]))

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
ret_line = block(HTML, "          page, navs, navGroups,", "\n")
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
zh_plain = [k for k, v in DICT["zh"].items() if not CJK.search(str(v)) and latin.search(str(v))]
ck("F6 zh 那份每条要么含中文、要么只是不含字母的标点（词表里的分隔符）——不许混进其实是英文的条目",
   not zh_plain, str(zh_plain[:6]))
same = [k for k in set(DICT["zh"]) & set(DICT["en"]) if DICT["zh"][k] == DICT["en"][k]]
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


PAGES_DONE = ["home"]   # ← 每翻完一页把页名加进来；登记了却没翻干净会被 I3 判红
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
             "pasteAnalyzeUrl", "downloadSpecificFormat"],
}


def js_fn(name: str) -> str:
    """取 index.html 里这个 setup 函数的函数体（八个空格那一层的 } 收尾）"""
    m = re.search(r"^        (?:async )?function %s\(" % re.escape(name), HTML, flags=re.M)
    if not m:
        return ""
    start = HTML.index("\n", m.start()) + 1
    end = HTML.find("\n        }\n", start)
    return HTML[start:end] if end > start else ""


def strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^[ \t]*//.*$", "", src, flags=re.M)


ck("I5a 每个登记了处理动作的页名都是真有的页",
   all(k in [m[0] for m in MARKS] for k in PAGE_HANDLERS), str(list(PAGE_HANDLERS)))
for _pg, _fns in PAGE_HANDLERS.items():
    for _fn in _fns:
        _b = js_fn(_fn)
        if not _b:
            ck(f"I5[{_pg}.{_fn}] 这个处理器抠到了", False, "找不到函数体（改名了？）")
            continue
        _left = [ln.strip()[:50] for ln in strip_js_comments(_b).splitlines() if CJK.search(ln)]
        ck(f"I5[{_pg}.{_fn}] 处理动作弹给用户的句子全走词表", not _left, str(_left[:3]))
# downloadQualityPreset 比的是后端解析出来的预设名（'仅音频'），名字翻了这行判断就失效，
# 它跟后端正文同一批走（键 + 现拼）；这一条钉住「剩下的中文只剩这一处」，别让它悄悄长大
_qp = [ln.strip() for ln in strip_js_comments(js_fn("downloadQualityPreset")).splitlines() if CJK.search(ln)]
ck("I6[home] 唯一没翻的处理器残留就是后端预设名那一条比对", len(_qp) == 1 and "仅音频" in _qp[0], str(_qp[:2]))
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
    ck("G1 行为读数一条不缺（37 条 rec，除首条装载检查外 36 条）", len(names) == 36, f"{len(names)} 项")
    reds = sorted(k for k in names if not R[k]["pass"])
    ck("G2 这 36 条读数与预期全部一致", not reds, show(*reds[:4]) if reds else "")
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
