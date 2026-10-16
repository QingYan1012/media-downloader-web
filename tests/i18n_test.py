# -*- coding: utf-8 -*-
"""界面多语言（zh / en）离线自检（#53 的第一批：骨架）。

口径（人已点头的那三条）：只翻前端 + 错误码、zh/en 且默认跟随浏览器、骨架先行再按模块分批。
这一套钉的是「骨架」这一层的四条线：

1. **词表本身**（A）：zh 与 en 的键集合一致、占位符对得上、没有空值。少哪一份都是运行时才露馅的错，
   而运行时没人会点遍每个页面。
2. **模板用到的键**（B）：把 index.html 里 `tr('…')` 的字面键、以及 `nav.` / `navGroup.` / `page.`
   三个动态前缀背后那些 key/id 全扫出来，逐个要求两份词表都在。这一条防的是「切到英文界面上印出键名」。
3. **接线与后端那一层**（C/D）：引用顺序、el-config-provider 的覆盖范围、帮助函数没被 v-for 遮蔽；
   `ui_language` 进 DEFAULTS、进 ConfigBody、进恢复默认名单，校验只认 auto/zh/en —— 并且后端除了
   那 4 行之外**没有任何一处读它**（D7 反向钉住「后端话术不翻」）。
4. **真实行为**（G，node）：把 static/i18n.js 原样喂给 node，用替身 window 跑 t / detect / apply / boot /
   elementLocale，看的是返回值而不是源码文本 —— 包括「en 的词包没加载上时不能把 locale 传成 undefined」
   和「刷新后第一帧按 localStorage 镜像，不闪另一种语言」。

全程不起服务、不写 config、不碰下载目录；node 的读数写到 %TEMP% 再读回（控制台是 GBK）。
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


PAIR = re.compile(r"['\"]?([A-Za-z][\w.]*)['\"]?:\s*'((?:[^'\\]|\\.)*)'")
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
dead = sorted(k for k in DICT["zh"]
              if k not in covered
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
ck("F3 运行日志正文仍由后端写中文一句（界面只发埋点文本）", "logAction('切换界面语言为「'" in HTML)
ck("F4 i18n.js 里 t() 的回落链是 en → zh → 键名",
   "(DICT[L] && DICT[L][key] != null)" in I18N_SRC
   and "DICT.zh[key] != null ? DICT.zh[key] : key" in I18N_SRC)
ck("F5 词表里没有订阅规则摘要那类后端正文",
   not [k for k in DICT["zh"] if "规则已更新" in DICT["zh"][k] or "每次最多" in DICT["zh"][k]])
CJK = re.compile(r"[\u4e00-\u9fff]")
latin = re.compile(r"[A-Za-z]")
no_cjk = [k for k, v in DICT["zh"].items() if not CJK.search(str(v))]
ck("F6 zh 那份每条都含中文（没有哪条其实是英文，把中文界面改成了英文）", not no_cjk, str(no_cjk[:6]))
same = [k for k in set(DICT["zh"]) & set(DICT["en"]) if DICT["zh"][k] == DICT["en"][k]]
ck("F7 en 那份没有哪条与 zh 一字不差（那样等于根本没翻）", not same, str(same[:6]))
no_latin = [k for k, v in DICT["en"].items() if not latin.search(str(v))]
ck("F8 en 那份每条都含拉丁字母", not no_latin, str(no_latin[:6]))

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
rec('g29_locale_never_undefined', [w.I.elementLocale('en'), w.I.elementLocale('zh'), w.I.elementLocale()].every((x) => !!x), true);

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
    ck("G1 行为读数一条不缺（30 条 rec，除首条装载检查外 29 条）", len(names) == 29, f"{len(names)} 项")
    reds = sorted(k for k in names if not R[k]["pass"])
    ck("G2 这 29 条读数与预期全部一致", not reds, show(*reds[:4]) if reds else "")
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
else:
    print("（node 不可用，G1~G14 未跑）")

print()
print(f"共 {TOTAL} 项，FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
