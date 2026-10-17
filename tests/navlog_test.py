#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「翻页面不写运行日志」离线自检（#33）。

钉两层：
1. 行为层（node）：把 `index.html` 里 `watch(page, …)` 的**回调体**与 `api()` 原样抠出来跑。
   翻遍 17 个页面一条埋点都不发，但每页该加载的数据照旧加载（这次删的只是那一行日志，不是加载）；
   写操作照旧记一行、GET 与轮询照旧不记、`/api/ui_event` 自己不再进埋点（否则无限递归）。
2. 后端 `/api/ui_event` 那条通道本身没被改坏：空文本不记、换行压平、200 字截断、level 只认
   info / warning。界面少发一类事件，不等于通道换成另一副样子。

全程不起服务、不写 config、不碰下载目录；node 的读数写到 %TEMP% 再读回（控制台是 GBK）。
跑法：PYTHONIOENCODING=utf-8 python tests/navlog_test.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

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


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info", k="", kv=None):   # k/kv 是 #53 给日志加的可选消息键，这里不收
        self.rows.append((level, str(msg)))

    def texts(self):
        return [m for _l, m in self.rows]


LOGS = FakeLog()
_REAL_LOG = S.log_mgr

WATCH_MARK = "watch(page, (p) => {"
API_MARK = "async function api(path, options = {}) {"


def slice_between(start: int, end_mark: str) -> str:
    j = HTML.find(end_mark, start)
    return HTML[start:j] if j >= 0 else ""


PAGE_WATCH_FULL = slice_between(HTML.find(WATCH_MARK), "\n        });")
API_FN_FULL = slice_between(HTML.find(API_MARK), "\n        }\n") + "\n        }"
# 回调体：去掉 `watch(page, (p) => {` 这一行头
PAGE_WATCH_BODY = PAGE_WATCH_FULL[len(WATCH_MARK):] if PAGE_WATCH_FULL else ""

PAGES = ["home", "sniff", "queue", "bt", "info", "search", "music", "tg", "live", "subs",
         "library", "files", "favs", "history", "voice", "log", "settings"]

EXPECT_LOADS = {
    "queue": ["loadTasks"],
    "bt": ["loadTasks", "loadSeeding", "loadBtTrackers"],
    "live": ["loadTasks", "loadLiveMonitors"],
    "history": ["loadHistory"],
    "log": ["loadLogs"],
    "files": ["loadFiles"],
    "subs": ["loadSubs"],
    "sniff": ["loadCatcatch"],
    "favs": ["loadFavTab"],
    "library": ["loadLibrary"],
    "music": ["loadMusicFavs"],
    "tg": ["loadTgMtStatus"],
    "settings": ["loadPlatformCookies", "loadCookieCloud", "loadMusicCookies", "loadRiskPresets",
                 "loadComponents", "loadNetInfo", "loadCleanup", "loadConfigDefaults"],
}
# 这几页在这个回调里没有要取的数据（都靠各自的按钮与轮询），跑完只该留下入场动画那一步
QUIET_PAGES = ["home", "info", "search", "voice"]

# ---------- A. 后端埋点通道本身 ----------
print("== A. 后端 /api/ui_event 的口径 ==")
try:
    S.log_mgr = LOGS

    LOGS.rows.clear()
    r = S.api_ui_event(S.UiEventBody(text="删除任务 abc"))
    ck("A1 正常一句记成 [界面] …", r.get("ok") is True and LOGS.texts() == ["[界面] 删除任务 abc"],
       str(LOGS.texts()))
    ck("A2 返回值不夹带配置或任务", set(r.keys()) <= {"ok", "level"}, str(sorted(r.keys())))

    LOGS.rows.clear()
    ck("A3 空文本不记", S.api_ui_event(S.UiEventBody(text="")).get("ok") is False and not LOGS.rows)
    LOGS.rows.clear()
    ck("A4 纯空白不记", S.api_ui_event(S.UiEventBody(text="  \n\t ")).get("ok") is False and not LOGS.rows)

    LOGS.rows.clear()
    S.api_ui_event(S.UiEventBody(text="第一行\n第二行\t再来一个  空格"))
    ck("A5 换行与连续空白压成一行", LOGS.texts() == ["[界面] 第一行 第二行 再来一个 空格"],
       str(LOGS.texts()))

    LOGS.rows.clear()
    S.api_ui_event(S.UiEventBody(text="x" * 400))
    got = LOGS.texts()[0] if LOGS.rows else ""
    ck("A6 超长截到 200 字（一行日志有上限）", len(got) == len("[界面] ") + 200, str(len(got)))

    LOGS.rows.clear()
    S.api_ui_event(S.UiEventBody(text="保存失败", level="warning"))
    S.api_ui_event(S.UiEventBody(text="普通一句", level="error"))
    S.api_ui_event(S.UiEventBody(text="再来一句", level=""))
    S.api_ui_event(S.UiEventBody(text="乱写的", level="<script>"))
    lv = [lvl for lvl, _m in LOGS.rows]
    ck("A7 level 只认 info / warning", lv == ["warning", "info", "info", "info"], str(lv))
    ck("A8 界面这条通道写不出 error 级", "error" not in lv)

    LOGS.rows.clear()
    S.api_ui_event(S.UiEventBody(text="口令 abc123"))
    ck("A9 后端不做二次改写（脱敏在前端发之前那一步）",
       LOGS.texts() == ["[界面] 口令 abc123"], str(LOGS.texts()))

    LOGS.rows.clear()
    S.api_ui_event(S.UiEventBody(text="点了两次同一个按钮"))
    S.api_ui_event(S.UiEventBody(text="点了两次同一个按钮"))
    ck("A10 埋点不去重：每次都是一件真发生过的事", len(LOGS.rows) == 2, str(len(LOGS.rows)))
finally:
    S.log_mgr = _REAL_LOG

# ---------- B. 前端静态口径 ----------
print("== B. 前端：哪些事件还发埋点 ==")
ck("B1 `watch(page, …)` 抠到了", PAGE_WATCH_FULL.startswith(WATCH_MARK) and len(PAGE_WATCH_FULL) > 200,
   f"{len(PAGE_WATCH_FULL)} 字")
ck("B2 `api()` 抠到了", API_FN_FULL.startswith(API_MARK) and len(API_FN_FULL) > 200,
   f"{len(API_FN_FULL)} 字")
ck("B3 页面切换回调里再没有 logAction", "logAction" not in PAGE_WATCH_BODY)
ck("B4 全站没有「切换到「X」」这种埋点", not re.search(r"logAction\(\s*[`'\"][^\n]*切换到", HTML))
ck("B5 每页的加载动作还在这段回调里", "if (p === 'queue'" in PAGE_WATCH_BODY
   and "p === 'settings'" in PAGE_WATCH_BODY)
ck("B6 写操作的埋点分支还在", "if (tracked) logAction(uiName || actionName(path));" in HTML)
ck("B7 失败也记一行并降成 warning", "+ '（失败）', 'warning'" in HTML)
ck("B8 埋点只认非 GET", "String(init.method || 'GET').toUpperCase() !== 'GET'" in HTML)
ck("B9 /api/ui_event 自己不再进埋点（否则无限递归）",
   "String(path).indexOf(UI_EVENT_PATH) !== 0" in HTML)
ck("B10 轮询用的写接口可以点名不记", "const noLog = options.noLog === true;" in HTML)
ck("B11 发出去之前仍过一遍敏感词（#53 之后过的是 zh、en 与 kv 三份，藏起来时键也一起藏）",
   ".some((s) => SENSITIVE_RE.test(String(s)))" in HTML
   and "text: leaky ? '[已隐藏敏感参数]' : t," in HTML)

# 这三条是这次留下的界线：由外部触发的一次性动作，不是「翻页面」
ck("B12 点系统通知跳过来仍记一行（句子搬进词表后按 ui.goto_* 两个键钉，磁力与队列各一条）",
   "logAction(isBt ? 'ui.goto_bt' : 'ui.goto_queue');" in HTML)
ck("B13 点更新弹窗跳设置仍记一行", "logAction('弹窗跳转：设置 → 组件与依赖');" in HTML)
ck("B14 主题与明暗仍记（它们真的写进配置）",
   "logAction('切换主题为「'" in HTML and "logAction(settings.value.dark_mode" in HTML)

ck("B15 日志页把这条口径写在界面上", "光翻页面不占行" in HTML)
ck("B16 页头标题仍用 pageTitle（不是顺手把变量删了）", "{{ pageTitle }}" in HTML)
ck("B17 页面切换的入场动画没被一起删掉", "classList.add('is-enter')" in PAGE_WATCH_BODY)

# ---------- C. node 跑真实回调体与 api() ----------
print("== C. node：翻遍 17 页与几类请求 ==")

JS = """
const fs = require('fs');
const RES = %s;
const calls = [];
const seen = [];
globalThis.logAction = (t, level) => calls.push([String(t), level === 'warning' ? 'warning' : 'info']);

// 给回调体里每一个名字一个「能调用、有 .value、再点下去还有下一层」的替身，省掉维护名单
function u(name) {
  const fn = function () { seen.push(name); return undefined; };
  return new Proxy(fn, {
    get: (t, k) => {
      if (k === 'value') return '';
      if (typeof k === 'symbol') return undefined;
      if (k === 'length' || k === 'name' || k === 'call' || k === 'apply' || k === 'bind') {
        return Reflect.get(t, k);
      }
      return u(name + '.' + String(k));
    },
    apply: () => { seen.push(name); return undefined; },
  });
}
const ctx = new Proxy(Object.create(null), {
  has: (t, k) => k !== 'p' && k !== 'logAction',
  get: (t, k) => (typeof k === 'symbol' ? undefined : u(String(k))),
});

// 1) 页面切换回调体：index.html 里 watch(page, (p) => { … }) 那段的原样内容
const pageWatch = new Function('p', 'ctx', 'with (ctx) {' + %s + '}');
const perPage = {};
for (const p of %s) {
  calls.length = 0; seen.length = 0;
  let err = '';
  try { pageWatch(p, ctx); } catch (e) { err = String((e && e.message) || e); }
  perPage[p] = { logs: calls.slice(), loads: seen.slice(), err };
}

// 2) api()：GET / 写操作 / 点名不记 / 埋点自身 / 失败
const UI_EVENT_PATH = '/api/ui_event';
function actionName(path) { return '动作:' + path; }
function friendlyError(x) { return '友好:' + String(x); }
const authGate = { needed: false, reason: '' };
let fetchMode = 'ok';
globalThis.fetch = async (path, init) => {
  if (fetchMode === 'fail') {
    return { ok: false, status: 401, statusText: 'Unauthorized',
             json: async () => ({ detail: 'nope', auth_required: true, reason: 'locked' }) };
  }
  return { ok: true, status: 200, json: async () => ({ ok: true }) };
};
%s
(async () => {
  const out = {};
  const one = async (path, opt) => {
    calls.length = 0;
    let threw = false;
    try { await api(path, opt); } catch (_) { threw = true; }
    return { logs: calls.slice(), threw };
  };
  out.getByGet = await one('/api/tasks');
  out.postByApi = await one('/api/download', { method: 'POST', body: '{}' });
  out.postWithNoLog = await one('/api/logs', { method: 'POST', noLog: true });
  out.postSelf = await one('/api/ui_event', { method: 'POST', body: '{}' });
  out.postNamed = await one('/api/config', { method: 'POST', uiName: '保存设置' });
  fetchMode = 'fail';
  out.postFail = await one('/api/download', { method: 'POST' });
  out.postFailGate = authGate.needed === true;
  out.putFail = await one('/api/tasks/clear', { method: 'PUT' });
  fs.writeFileSync(RES, JSON.stringify({ perPage, out }));
})();
"""


def run_node() -> dict:
    if subprocess.run(["node", "--version"], capture_output=True, text=True).returncode != 0:
        return {}
    tmp = Path(tempfile.gettempdir())
    res = tmp / "navlog_result.json"
    if res.exists():
        res.unlink()
    js = JS % (json.dumps(str(res)), json.dumps(PAGE_WATCH_BODY), json.dumps(PAGES), API_FN_FULL)
    harness = tmp / "navlog_harness.js"
    harness.write_text(js, encoding="utf-8")
    p = subprocess.run(["node", str(harness)], capture_output=True, text=True, encoding="utf-8")
    if not res.exists():
        print("NODE FAIL:", (p.stderr or p.stdout)[:900])
        return {}
    return json.loads(res.read_text(encoding="utf-8"))


R = run_node()
ck("C0 node 跑通了（本机没有 node 就别假绿）", bool(R), "harness 没产出" if not R else "")
if R:
    per = R.get("perPage") or {}
    out = R.get("out") or {}
    errs = {p: v.get("err") for p, v in per.items() if v.get("err")}
    ck("C0b 17 页的回调体都能跑起来", not errs, str(errs))
    logged = {p: v["logs"] for p, v in per.items() if v.get("logs")}
    ck("C1 17 个页面翻一遍，一条埋点都不发", len(per) == len(PAGES) and not logged, str(logged))
    missing = {p: [n for n in want if n not in (per.get(p) or {}).get("loads", [])]
               for p, want in EXPECT_LOADS.items()}
    missing = {p: v for p, v in missing.items() if v}
    ck("C2 删掉的只是那一行日志，每页该取的数据照旧取", not missing, str(missing))
    quiet = {p: [n for n in (per.get(p) or {}).get("loads", []) if not n.startswith("document")]
             for p in QUIET_PAGES}
    quiet = {p: v for p, v in quiet.items() if v}
    ck("C3 没有加载任务的页，跑完什么都不剩（没被偷偷加回埋点）", not quiet, str(quiet))
    ck("C4 设置页仍会取默认值表与清理卡片",
       "loadConfigDefaults" in (per.get("settings") or {}).get("loads", [])
       and "loadCleanup" in (per.get("settings") or {}).get("loads", []),
       str((per.get("settings") or {}).get("loads")))
    ck("C5 GET 不记（轮询刷不出日志）", (out.get("getByGet") or {}).get("logs") == [],
       str(out.get("getByGet")))
    pb = (out.get("postByApi") or {}).get("logs") or []
    ck("C6 写操作记一行，名字来自路径映射", len(pb) == 1 and pb[0][0].startswith("动作:/api/download"),
       str(pb))
    ck("C7 点名不记的写操作照旧不记", (out.get("postWithNoLog") or {}).get("logs") == [],
       str(out.get("postWithNoLog")))
    ck("C8 埋点接口自己不给自己记（递归那条）", (out.get("postSelf") or {}).get("logs") == [],
       str(out.get("postSelf")))
    ck("C9 同一个接口被不同按钮共用时写的是按钮名",
       (out.get("postNamed") or {}).get("logs") == [["保存设置", "info"]], str(out.get("postNamed")))
    pf = (out.get("postFail") or {}).get("logs") or []
    ck("C10 失败那一下记成 warning 且带「（失败）」",
       len(pf) == 1 and pf[0][1] == "warning" and pf[0][0].endswith("（失败）"), str(pf))
    ck("C11 失败仍然抛（埋点没把错误咽掉）", (out.get("postFail") or {}).get("threw") is True)
    ck("C12 401 仍走登录门", out.get("postFailGate") is True)
    pu = (out.get("putFail") or {}).get("logs") or []
    ck("C13 PUT 也算写操作（不是只认 POST）",
       len(pu) == 1 and pu[0][0].startswith("动作:/api/tasks/clear"), str(pu))

print("== 汇总 ==")
ck("Z1 后端那份 log_mgr 已还原", S.log_mgr is _REAL_LOG)
print(f"共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    print("失败清单：" + " / ".join(FAILED))
    sys.exit(1)
print("ALL GREEN")
