# -*- coding: utf-8 -*-
"""解析页字幕这一排：字幕轨出口、任务级翻译选项、JS 运行时、区间与免费机翻的失败口径。

口径（2026-10-26 与用户逐条过）：
- `/api/analyze` 把 yt-dlp 的 subtitles / automatic_captions 收成一行一条，人工优先、
  同语言的自动轨不再重复列，`live_chat`（弹幕）不算字幕。
- 解析页选中的语言就是 `opts.subtitle_langs`，与下载页共用同一格；机翻的目标语言与翻译引擎
  按任务覆盖全局设置，不再只能去设置页改。
- 这三格（`subtitle_target_lang` / `subtitle_translate_provider` / `local_ai_mt_after_transcribe`）
  没传时保持 None，让全局读数继续生效。

三条来自实测的坑，都有对应断言：
- 2026-10-26 本机：yt-dlp 2026.10.21 的 `js_runtimes` 默认只有 deno，本机只有 node 时签名/n
  挑战求解静默失败，清单只剩 storyboard，下载报 No video formats found。
- 同一天：`download_range_func(None, [sec])` 把 "*00:00:10-00:00:30" 当 ranges，yt-dlp 遍历时
  按字符解包，区间任务以 too many values to unpack 收尾。
- 同一天：deep-translator 被限流时把原文逐条原样返回，`translate_with_fallback` 只比长度，
  于是日志写「翻译成功」而产物仍是日文 —— 失败路径必须抛错，不能装作成了。
"""
import os
import re
import shutil
import sys
import tempfile
import types
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="md_infosub_state_")
os.environ["MEDIADOWNLOADER_STATE_DIR"] = STATE
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server as S  # noqa: E402

TOTAL = []
FAILED = []
SRC = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
CHLOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def ck(name, cond, extra=""):
    TOTAL.append(name)
    if not cond:
        FAILED.append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or not extra else f"  [{extra}]"),
          flush=True)


# ---------------- A. 字幕轨收成一行一条
info = {
    "subtitles": {
        "ja": [{"ext": "srt", "name": "Japanese"}, {"ext": "vtt", "name": "Japanese"}, {"ext": "srt"}],
        "live_chat": [{"ext": "json", "name": "chat"}],
        "zh": [],
        "de": [{"name": "German"}],
    },
    "automatic_captions": {"ja": [{"ext": "vtt"}], "en": [{"ext": "vtt", "name": "English (auto-generated)"}]},
}
got = S._subtitle_tracks(info)
rows = [(x["lang"], x["auto"]) for x in got]
ck("A1 只留有人工/自动轨的语言，live_chat 与空清单不算", rows == [("ja", False), ("en", True)], str(rows))
ck("A2 同一语言两边都有时只留人工那份", sum(1 for x in got if x["lang"] == "ja") == 1)
ck("A3 人工轨排在自动轨前面", [x["auto"] for x in got] == [False, True])
ja = next(x for x in got if x["lang"] == "ja")
ck("A4 语言名取第一条带 name 的格式", ja["name"] == "Japanese", ja["name"])
ck("A5 可用格式去重后带上", ja["formats"] == ["srt", "vtt"], str(ja["formats"]))
ck("A6 一条 ext 都没有的不算字幕轨", "de" not in [x["lang"] for x in got])
ck("A7 两边都没有时回空表", S._subtitle_tracks({}) == [])

# ---------------- B. 解析接口把字幕轨带出去
ck("B1 单视频解析回 subtitles", '"subtitles": _subtitle_tracks(info),' in SRC)
ck("B2 播放列表那一支也带空 subtitles", '"subtitles": [],' in SRC)

# ---------------- C. 任务级翻译选项进得了请求体、盖得住全局配置
m = re.search(r"class AddUrlsBody\(BaseModel\):\n(.*?)\n\nclass ", SRC, re.S)
body = m.group(1) if m else ""
for k in ("subtitle_target_lang: Optional[str] = None",
          "subtitle_translate_provider: Optional[str] = None",
          "local_ai_mt_after_transcribe: Optional[bool] = None"):
    ck(f"C1 AddUrlsBody 收 {k.split(':')[0]}", k in body)
seg = SRC[SRC.index("本次任务选项覆盖全局配置"):SRC.index("本次任务选项覆盖全局配置") + 1500]
ck("C2 三格列入任务覆盖白名单",
   all(k in seg for k in ("local_ai_mt_after_transcribe", "subtitle_target_lang", "subtitle_translate_provider")))
ck("C3 没传的那一格不覆盖全局", "if opts.get(k) is not None:" in seg)

# ---------------- D. JS 运行时：解析与下载同一套 opts
eng = S.DownloaderEngine()
yt = "https://www.youtube.com/watch?v=6C3zYwUmMKE"
o_info = eng._ydl_opts({}, for_info=True, url=yt)
o_dl = eng._ydl_opts({"skip_downloaded": False}, for_info=False, url=yt)
jr_i, jr_d = o_info.get("js_runtimes") or {}, o_dl.get("js_runtimes") or {}
ck("D1 解析 opts 保留 deno 默认项", "deno" in jr_i, str(jr_i))
ck("D2 下载 opts 与解析同一套", "deno" in jr_d, str(jr_d))
node = shutil.which("node")
ck("D3 探到 node 就带上真实路径", (not node) or (jr_i.get("node") or {}).get("path") == node,
   f'{jr_i.get("node")} vs {node}')
ck("D4 自定义参数能关掉（用户写 --no-js-runtimes 就不开）",
   eng._ydl_opts({"ytdlp_extra_args": "--no-js-runtimes"}, for_info=True, url=yt).get("js_runtimes") == {})

# ---------------- E. 片段区间与命令行同口径
class _Y:
    def to_screen(self, *a):
        pass


def _ranges(sec):
    from yt_dlp import parse_options
    f = parse_options(["--ignore-config", "--download-sections", sec]).ydl_opts.get("download_ranges")
    return list(f({"id": "x", "duration": 300}, _Y()))


try:
    ck("E1 *00:00:10-00:00:30 解成 10-30 两个数",
       _ranges("*00:00:10-00:00:30") == [{"start_time": 10, "end_time": 30}], str(_ranges("*00:00:10-00:00:30")))
    ck("E2 逗号多段照旧支持", len(_ranges("*0-1,2-3")) == 2)
    ck("E3 inf 收尾认得", _ranges("*10:15-inf")[0]["end_time"] == float("inf"))
except Exception as e:  # noqa: BLE001
    ck("E1 区间解析可用", False, f"{type(e).__name__}: {e}")
ck("E4 不再把字符串直接塞给 download_range_func", "download_range_func(None, [sec])" not in SRC)
ck("E5 区间走 yt-dlp 自己的 CLI 解析器", 'parse_options(["--ignore-config", "--download-sections", sec])' in SRC)
try:
    _ranges("*abc")
    bad = "非法区间没报错"
except Exception:  # noqa: BLE001 - OptParseError / SystemExit 都算
    bad = ""
ck("E6 非法区间会抛（源码那层同时接 Exception 与 SystemExit）",
   not bad and "except (Exception, SystemExit) as e:" in SRC, bad)

# ---------------- F. 免费机翻引擎的失败路径
import voice_tools as VT  # noqa: E402

_saved = sys.modules.get("deep_translator")


class _Stub:
    mode = "same"

    def __init__(self, source=None, target=None):
        pass

    def translate(self, text):
        return text if _Stub.mode == "same" else "\n\n".join("en:" + p for p in text.split("\n\n"))


_stub_mod = types.ModuleType("deep_translator")
_stub_mod.GoogleTranslator = _Stub
sys.modules["deep_translator"] = _stub_mod
try:
    _Stub.mode = "same"
    raised = ""
    try:
        VT.translate_batch_deep_translator(["会いたい", "きみに会いたい"], "en", "ja", log=lambda *a: None)
    except RuntimeError as e:
        raised = str(e)
    ck("F1 整批原样返回时抛错，不再谎报翻译成功", bool(raised), raised)
    ck("F2 抛出的话里说清是限流那类", "限流" in raised or "未产生译文" in raised, raised)
    _Stub.mode = "done"
    out = VT.translate_batch_deep_translator(["会いたい", "きみに会いたい"], "en", "ja", log=lambda *a: None)
    ck("F3 真译出来了就不抛，长度对齐", out == ["en:会いたい", "en:きみに会いたい"], str(out))
finally:
    if _saved is not None:
        sys.modules["deep_translator"] = _saved
    else:
        sys.modules.pop("deep_translator", None)

# ---------------- G. 中英两条文案都齐
SUB_KEYS = ("info.subTitle", "info.subNone", "info.subManual", "info.subAuto", "info.subAll",
            "info.subClear", "info.subSelected", "info.subDownload", "info.subHint",
            "info.subDlOptions", "info.subDlHint", "info.subTranslateOptions", "info.subMtAfter",
            "info.subTargetLang", "info.subMtEngine", "info.subTranslateHint")
off = [k for k in SUB_KEYS if I18N.count(f"'{k}'") != 2]
ck(f"G1 字幕这 {len(SUB_KEYS)} 条文案中英各一条", not off, "、".join(off))

# ---------------- H. 解析页接线
ck("H1 字幕区块挂在解析结果里", "tr('info.subTitle', { n: infoSubTracks.length })" in HTML)
ck("H2 chips 点一下就是选/撤这一条字幕轨", '@click="toggleInfoSub(s.lang)"' in HTML)
ck("H3 人工 / 自动角标按轨的性质给", "s.auto ? tr('info.subAuto') : tr('info.subManual')" in HTML)
ck("H4 合集/播放列表那一支不显示字幕格",
   "mediaInfo.type !== 'playlist' && !(mediaInfo.entries && mediaInfo.entries.length)" in HTML)
ck("H5 解析回来的语言参与已选口径", "const infoSubTracks = computed(() => (mediaInfo.value && mediaInfo.value.subtitles) || []);" in HTML)
ck("H6 没有交集时自动选中第一条人工轨", "const manual = tracks.filter(t => !t.auto);" in HTML)
ck("H7 每次解析都重算一遍已选", "\n            initInfoSubLangs();" in HTML)
ck("H8 三格默认值在 opts 里，读设置时回填",
   all(s in HTML for s in ("subtitle_target_lang: 'zh',", "subtitle_translate_provider: 'deepl',",
                           "local_ai_mt_after_transcribe: false,")))
ck("H9 设置读数回填这三格",
   all(s in HTML for s in ("opts.value.subtitle_target_lang = data.subtitle_target_lang || 'zh';",
                           "opts.value.subtitle_translate_provider = data.subtitle_translate_provider || 'deepl';",
                           "opts.value.local_ai_mt_after_transcribe = !!data.local_ai_mt_after_transcribe;")))
ret = HTML[HTML.index("return {"):]
ck("H10 新函数都在 setup 的 return 里",
   "infoSubTracks, subTrackLabel, toggleInfoSub, selectAllInfoSubs, clearInfoSubs," in ret)
ck("H11 这一屏有按所选设置直接下载的入口", "tr('info.subDownload')" in HTML and "@click=\"downloadFromInfo\"" in HTML)

# ---------------- I. 版本号只有一处真源，且与发布说明对齐
import pack_release as PKG  # noqa: E402

ver = PKG.app_version()
ck("I1 index.html 里版本号只出现一处", len(re.findall(r"v\d+\.\d+\.\d+", HTML)) == 1, ver)
ck(f"I2 包名跟着 appVersion 走（{ver}）", re.search(r"v(\d+\.\d+\.\d+)", HTML).group(1) == ver)
ck("I3 CHANGELOG 最新一节就是这一版", re.search(r"## v(\d+\.\d+\.\d+)", CHLOG).group(1) == ver)

print(f"\nTOTAL {len(TOTAL)} FAILED: " + ("none" if not FAILED else ", ".join(FAILED)))
sys.exit(1 if FAILED else 0)
