r"""右键 / Ctrl+V 粘贴清洗的自检：接线在模板里，判定口径在 JS 里，两头都要钉住。

为什么要有这个文件：`@paste="onPaste(box, 'url')"` 这种「带参数的表达式」在 Vue 模板里是**语句**
而不是处理器 —— 表达式在渲染时执行一次，它返回的那个函数会被直接丢掉，于是粘贴事件是个空操作，
界面看不出任何异常。只有把 `$event` 显式传进处理函数才真的挂得上。这条坑靠读代码很容易看漏，
所以 A 段专门反向钉它。

B 段把 `extractUrls` / `cleanPasted` / `onPaste` 三个函数从 index.html 里原样抠出来，
交给本机 node 跑真实输入（不复制第二份实现，改了就测到）。

全程不起服务、不写 config、不碰下载目录；node 的读数写到 %TEMP% 再读回（控制台是 GBK）。

跑法：`python tests/paste_test.py`（末行 FAILED 不为 0 就是没过）
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

APP_DIR = Path(__file__).resolve().parent.parent
INDEX = APP_DIR / "static" / "index.html"
SRC = INDEX.read_text(encoding="utf-8")

FAILED: List[str] = []
TOTAL = 0


def ck(name: str, cond: bool, detail=""):
    global TOTAL
    TOTAL += 1
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else "  <== " + str(detail)[:300]))
    if not cond:
        FAILED.append(name)


def extract_fn(name: str) -> str:
    """抠出 `function name(...) { ... }` 整段原文。

    不能数大括号：这个文件里的 JS 有 `/[)\\]}>;,、，。；：:!?\"']+/` 这种字符类，
    正则里的 `}` 会让计数提前归零、抠出来的是半截函数。改按本项目的缩进规矩收尾
    （函数体结束的那一行正好是「和 function 同缩进的 }」）。
    """
    lines = SRC.split("\n")
    for i, line in enumerate(lines):
        if re.match(r"(async )?function %s\(" % re.escape(name), line.strip()):
            indent = line[:len(line) - len(line.lstrip())]
            for j in range(i + 1, len(lines)):
                if lines[j] == indent + "}":
                    return "\n".join(lines[i:j + 1])
            return ""
    return ""


def setup_return_text() -> str:
    """setup() 末尾那份返回值清单 —— 模板只取得到写在这里名字。"""
    for m in re.finditer(r'return \{', SRC):
        seg = SRC[m.start():m.start() + 6000]
        end = seg.find("\n        }")
        block = seg[:end] if end > 0 else seg
        if "startDownload" in block and "pasteUrl" in block:
            return block
    return ""


BINDINGS = re.findall(r'@paste="onPaste\(([^)]*)\)"', SRC)

# ---------- A. 模板接线 ----------
ck("A1 单行框的粘贴绑定共 7 处", len(BINDINGS) == 7, BINDINGS)
ck("A2 每处都把 $event 显式传进处理函数",
   all(re.fullmatch(r"\$event, '(url|text)'", b) for b in BINDINGS), BINDINGS)
ck("A3 反向：不许残留「把 v-model 变量当第一个参数」的写法（那种写法事件收不到）",
   not re.search(r'@paste="onPaste\((?!\$event)[A-Za-z_$][A-Za-z0-9_$]*,', SRC),
   re.findall(r'@paste="onPaste\([^)]*\)', SRC))
ck("A3b 反向：A3 不是空断言（把绑定改回 onPaste(analyzeUrl, 'url') 就查得出来）",
   re.search(r'@paste="onPaste\((?!\$event)[A-Za-z_$][A-Za-z0-9_$]*,',
             '<el-input @paste="onPaste(analyzeUrl, \'url\')"></el-input>') is not None, "查不出来")
BOUND_MODELS = re.findall(r'v-model="([A-Za-z0-9_]+)"[^>]*?@paste="onPaste\(\$event',
                          SRC, flags=re.S)
expect_models = {"analyzeUrl", "searchQuery", "musicPlaylistUrl", "liveMonitorUrl",
                 "btRuleTestName", "tgChannel", "ytPlaylistUrl"}
ck("A4 被绑定的正好是这七个单行框", set(BOUND_MODELS) == expect_models, sorted(BOUND_MODELS))

MULTILINE = ["urlText", "btText", "musicKeyword", "subUrl", "liveUrl"]


def multiline_violations(src: str) -> List[str]:
    """哪些多行批量框被误绑了清洗（绑上就会把整段批量内容压成一条）。"""
    bad = []
    for model in MULTILINE:
        p = src.find('v-model="%s"' % model)
        if p < 0:
            bad.append("%s 找不到" % model)
            continue
        start = src.rfind("<el-input", max(0, p - 260), p + 1)
        end = src.find(">", p)
        tag = src[start:end + 1] if start >= 0 and end > start else ""
        if "@paste" in tag:
            bad.append(model)
    return bad


ck("A5 多行批量框不绑清洗（粘进来的原文要留在框里对着看）",
   not multiline_violations(SRC), multiline_violations(SRC))
fake = SRC.replace('v-model="urlText"', 'v-model="urlText" @paste="onPaste($event, \'url\')"')
ck("A6 反向：A5 不是空断言（给 urlText 补一个绑定就能查出来）",
   multiline_violations(fake) == ["urlText"], multiline_violations(fake))

ret_txt = setup_return_text()
ck("A7 onPaste 与 cleanPasted 都在 setup 返回值里（模板取不到就是静默失效）",
   "onPaste" in ret_txt and "cleanPasted" in ret_txt, ret_txt[-200:])
ck("A8 「粘贴」按钮全部保留（右键粘贴是补充，不是替代）",
   all('function %s(' % f in SRC for f in ("pasteUrl", "pasteAnalyzeUrl")) and
   re.search(r'@click="pasteUrl\(\)"|@click="pasteUrl"', SRC) is not None,
   [f for f in ("pasteUrl", "pasteAnalyzeUrl") if 'function %s(' % f not in SRC])
onp = extract_fn("onPaste")
ck("A9 处理函数走的是「改原生输入框 + 补发 input 事件」这条路（v-model 才会跟着变）",
   all(s in onp for s in ("e.preventDefault()", "e.target.value = v", "new Event('input'")), onp[:200])
cp = extract_fn("cleanPasted")
ck("A10 清洗口径只有一条：cleanPasted 里调 extractUrls 且没有第二套 URL 正则",
   "extractUrls(" in cp and re.search(r"/https\?:", cp) is None, cp[:240])
pa = extract_fn("pasteAnalyzeUrl")
ck("A11 「粘贴」按钮与右键粘贴共用同一个 cleanPasted", "cleanPasted(" in pa, pa[:240])

# ---------- B. 真实输入跑 node ----------
HARNESS = """
%(extractUrls)s
%(cleanPasted)s
%(onPaste)s

class FakeEvent {
  constructor(text) {
    this.clipboardData = { getData: () => text };
    this.defaultPrevented = false;
    this.target = { value: null, dispatched: [] };
    this.target.dispatchEvent = (ev) => this.target.dispatched.push(ev.type);
  }
  preventDefault() { this.defaultPrevented = true; }
}

const inputs = [
  ["分享 https://www.bilibili.com/video/BV1xx411c7mD?p=1 复制到bilibili打开\\n第二条 https://example.com/a", "url"],
  ["访问 https://example.com/a，或者这个 https://example.com/b", "url"],
  ["看 https://example.com/a。", "url"],
  ["magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=x 来自站点", "url"],
  ["  @some_channel   后缀一堆字   ", "url"],
  ["  sorry   the  song\\n\\n第二条", "text"],
  ["sorry https://example.com/1", "text"],
  ["", "url"],
  ["   \\n  \\n ", "text"],
  ["https://a.example.com/1 https://b.example.com/2 https://c.example.com/3", "url"]
];

const readings = inputs.map(([text, kind]) => {
  const cleaned = cleanPasted(text, kind);
  const ev = new FakeEvent(text);
  onPaste(ev, kind);
  return { text, kind, cleaned, prevented: ev.defaultPrevented,
           value: ev.target.value, dispatched: ev.target.dispatched };
});

const fs = require("fs");
fs.writeFileSync(process.argv[2], JSON.stringify(readings), "utf8");
"""


def run_node() -> List[dict]:
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if node.returncode != 0:
        return []
    body = HARNESS % {"extractUrls": extract_fn("extractUrls"),
                      "cleanPasted": extract_fn("cleanPasted"),
                      "onPaste": extract_fn("onPaste")}
    tmp = Path(tempfile.gettempdir())
    js = tmp / "paste_test_harness.js"
    res = tmp / "paste_test_result.json"
    js.write_text(body, encoding="utf-8")
    p = subprocess.run(["node", str(js), str(res)], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0 or not res.exists():
        print("   node 跑不动：%s %s" % ((p.stderr or "")[:300], (p.stdout or "")[:200]))
        return []
    data = json.loads(res.read_text(encoding="utf-8"))
    js.unlink(missing_ok=True)
    res.unlink(missing_ok=True)
    return data


rows = run_node()
ck("B0 本机 node 能把三个函数跑起来", len(rows) == 10, len(rows))
if len(rows) == 10:
    r = rows[0]
    ck("B1 分享文案里只留第一条链接，后面那条与换行都不进框",
       r["cleaned"] == "https://www.bilibili.com/video/BV1xx411c7mD?p=1", r)
    r = rows[1]
    ck("B2 中文顿号逗号这类分隔符按 extractUrls 的口径切掉",
       r["cleaned"] == "https://example.com/a", r)
    r = rows[2]
    ck("B2b 句尾中文句号不进框", r["cleaned"] == "https://example.com/a", r)
    r = rows[3]
    ck("B3 磁力链接粘进单行框只留 magnet: 那一段",
       r["cleaned"].startswith("magnet:?xt=urn:btih:0123") and " 来自站点" not in r["cleaned"], r)
    r = rows[4]
    ck("B4 没有 http 前缀时退回第一行，不把用户写的频道名改坏",
       r["cleaned"] == "@some_channel   后缀一堆字", r)
    r = rows[5]
    ck("B5 关键词框粘进多行只留首行并压掉多余空格",
       r["cleaned"] == "sorry the song", r)
    r = rows[6]
    ck("B6 反向：关键词框里粘到链接也不许被换成只剩链接（口径不同）",
       r["cleaned"] == "sorry https://example.com/1", r)
    r = rows[7]
    ck("B7 空剪贴板不拦事件、不改框里的值（不破坏正常粘贴）",
       r["prevented"] is False and r["value"] is None and r["dispatched"] == [], r)
    r = rows[8]
    ck("B8 只有空白也算空，同样不拦不改",
       r["prevented"] is False and r["value"] is None, r)
    r = rows[9]
    ck("B9 一行挤三条链接时只取第一条，且值真的写进了输入框并补发 input",
       r["cleaned"] == "https://a.example.com/1" and r["value"] == r["cleaned"]
       and r["prevented"] is True and r["dispatched"] == ["input"], r)

print("TOTAL: %d FAILED: %d %s" % (TOTAL, len(FAILED), FAILED))
sys.exit(1 if FAILED else 0)
