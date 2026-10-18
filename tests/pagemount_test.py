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

print("\n== 汇总 ==")
if FAILED:
    print(f"共 9 条，失败 {len(FAILED)} 条\n失败清单：" + "、".join(FAILED))
    sys.exit(1)
print("共 9 条，全部通过")
