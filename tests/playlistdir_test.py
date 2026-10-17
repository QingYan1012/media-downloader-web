r"""合集整批的落点：勾了才多建一层，名字只从合集自己来，日志说「存到 X」时 X 得真的在场。

起因（实测）：下载目录里那 12 集《尼古喵喵》的 mkv 与每集的 danmaku.xml/.ass 平铺在根上，
和 40 个音乐艺人文件夹混在同一层；「设置 → 文件名模板」也救不了这一格 —— 模板里的「/」「\」
在拼 outtmpl 之前就被换成「_」，所以靠模板写不出子目录。这一批把口径收成一个开关：
整批下合集时在下载目录（或自动分类命中的那个子目录）下面建一层，名字取合集自己的标题。

跑法：`python tests/playlistdir_test.py`（不起 server，不联网，全部产物落在 %TEMP%\md_playlistdir_test\<时刻>\）。
"""
from __future__ import annotations

import inspect
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_playlistdir_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)
FAILED: list[str] = []

# 用户那台机器上真实存在过的容器标题（history.json 里那条 B 站 season）
PL_TITLE = "合集·【官方中字】尼古喵喵 （全12集）"


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


# ---------------------------------------------------------------- A. 名字怎么来
print("== A. 文件夹名只用合集自己的标题：禁字符换掉、截断、逃逸挡掉、没名字就不建 ==")
a1 = S.playlist_folder_name(PL_TITLE)
ck("A1 真实容器标题原样能用（「合集·」「（全12集）」这类前缀照用户口径留着不削）",
   a1 == PL_TITLE, a1)
a2 = S.playlist_folder_name("A/B:C*D?E|F 第1集")
ck("A2 Windows 禁字符逐个换掉，绝不在名字里留下路径分隔符",
   a2 == "A_B-CDE-F 第1集" and "/" not in a2 and "\\" not in a2, a2)
a3 = S.playlist_folder_name("某某合集" + "很长" * 40)
ck("A3 超长标题截到 60 字符（与成品名同一口径，不额外发明一套）",
   len(a3) == 60, f"{len(a3)} 字符")
ck("A4 空标题 / 纯标点 / 「..」都回空串：没名字就不建夹，不兜一个「download」出来",
   S.playlist_folder_name("") == "" and S.playlist_folder_name("   ") == ""
   and S.playlist_folder_name("..") == "" and S.playlist_folder_name("——·：？") == "",
   f"{S.playlist_folder_name('..')!r} / {S.playlist_folder_name('——·：？')!r}")
ck("A5 「CON」这类 Windows 保留名加前导下划线（继承 safe_filename_component 那层）",
   S.playlist_folder_name("CON") == "_CON", S.playlist_folder_name("CON"))
ck("A6 带转义的名字不出目录：分隔符换成「_」，绝不拼出 ../../elsewhere",
   S.playlist_folder_name("../../Windows/system32") == "_.._Windows_system32"
   and "/" not in S.playlist_folder_name("../../Windows/system32")
   and "\\" not in S.playlist_folder_name("../../Windows/system32"),
   S.playlist_folder_name("../../Windows/system32"))

# ---------------------------------------------------------------- B. 落点与那句人话
print("== B. 落点：勾了才建、建在这趟原本的目录下面、并且真的建出来了 ==")
base = SHARD / "base"
base.mkdir(parents=True, exist_ok=True)

d, note = S.playlist_landing_dir(str(base), PL_TITLE, False, is_playlist=True)
ck("B1 没勾：原目录、一句话都不说、也不许偷偷建夹（默认关就得跟改前一模一样）",
   d == str(base) and note == "" and not (base / PL_TITLE).exists(), note)

d, note = S.playlist_landing_dir(str(base), PL_TITLE, True, is_playlist=True)
ck("B2 勾了 + 容器就是这一趟的 info：建在下载目录下面这一层，目录真在场",
   d == str(base / PL_TITLE) and pathlib.Path(d).is_dir(), d)
ck("B3 那句话带上落点与名字来处（整表那一颗要说「容器标题」）",
   PL_TITLE in note and "容器标题" in note, note)

one = S.playlist_landing_dir(str(base), PL_TITLE, True, is_playlist=True)
ck("B4 同一合集的第二趟复用同一个文件夹（补下不产生第二层，也不叫「名字 (1)」）",
   one[0] == d, one[0])

sub = base / "动漫"      # 自动分类规则给出的子目录当 base_dir 传进来
sub.mkdir(parents=True, exist_ok=True)
d2, note2 = S.playlist_landing_dir(str(sub), PL_TITLE, True, is_playlist=True)
ck("B5 合集这一层加在自动分类给的目录下面，不替掉它",
   d2 == str(sub / PL_TITLE) and pathlib.Path(d2).is_dir()
   and str(sub) in note2, d2)

d3, note3 = S.playlist_landing_dir(str(base), PL_TITLE, True)
ck("B6 逐条链接那一侧：名字取入队时带过来的那份，人话说清是「解析页带过来的合集名」",
   d3 == str(base / PL_TITLE) and "解析页带过来的合集名" in note3, note3)

d4, note4 = S.playlist_landing_dir(str(base), "", True)
ck("B7 单条下载没带合集名：原目录、安静、不建夹（勾了开关也不该给单条造文件夹）",
   d4 == str(base) and note4 == "", note4)

d5, note5 = S.playlist_landing_dir(str(base), PL_TITLE, True, is_live=True)
ck("B8 直播录制不建这层（录的是流，不是一个合集）",
   d5 == str(base) and note5 == "", note5)

d6, note6 = S.playlist_landing_dir(str(base), "。。：？——", True, is_playlist=True)
ck("B9 容器没给可用标题：照实说「仍平铺」，别把没建成说成建好了",
   d6 == str(base) and "仍平铺" in note6 and "容器" in note6, note6)

d7, note7 = S.playlist_landing_dir(str(base), "", True, is_playlist=True)
ck("B10 容器标题是空的：同一句「仍平铺」，路径也带着，用户翻目录时能对上",
   d7 == str(base) and "仍平铺" in note7 and str(base) in note7, note7)

d8, note8 = S.playlist_landing_dir(str(base), "..", True)
ck("B11 带过来的名字清洗完没剩下可用字符：点名那个名字并说仍平铺",
   d8 == str(base) and "可用字符" in note8, note8)

blocked = SHARD / "blocked"
blocked.write_text("我不是目录")   # 拿一个已存在的文件当 base_dir：建不出来必须回落到平铺
d9, note9 = S.playlist_landing_dir(str(blocked), PL_TITLE, True, is_playlist=True)
ck("B12 文件夹建不出来时回原目录，并把缘故说清（不能让 outtmpl 指向一个不存在又建不出的地方）",
   d9 == str(blocked) and "建不出来" in note9, note9[:80])

# ---------------------------------------------------------------- C. 接线
print("== C. 接线：设置、请求字段、opts→cfg、outtmpl 两处都跟着这层走 ==")
SVC = pathlib.Path(APP / "server.py").read_text(encoding="utf-8")
IDX = pathlib.Path(APP / "static" / "index.html").read_text(encoding="utf-8")
I18N = pathlib.Path(APP / "static" / "i18n.js").read_text(encoding="utf-8")

ck("C1 设置项存在且默认 False（默认关，老目录结构不突变）",
   S.ConfigManager.DEFAULTS.get("playlist_subdir") is False,
   str(S.ConfigManager.DEFAULTS.get("playlist_subdir")))
ck("C2 下载请求带这两个字段：开关 + 这一批属于哪个合集（不传＝跟随全局）",
   S.AddUrlsBody.model_fields["playlist_subdir"].default is None
   and S.AddUrlsBody.model_fields["playlist_folder"].default is None,
   str([S.AddUrlsBody.model_fields[k].default for k in ("playlist_subdir", "playlist_folder")]))
ck("C3 综合设置能存这个开关", "playlist_subdir" in S.ConfigBody.model_fields)
mb = inspect.getsource(S.TaskQueue._run)
ck("C4 本次请求的这两个值会覆盖全局配置（漏了勾了就永远只吃设置里那份）",
   '"playlist_subdir", "playlist_folder",' in mb,
   "" if '"playlist_subdir", "playlist_folder",' in mb else "合并名单里找不到这两个键")
dl = inspect.getsource(S.DownloaderEngine.download)
ck("C5 落点由 playlist_landing_dir 一处定，日志那句就是它给的",
   "dl_dir, pl_note = playlist_landing_dir(" in dl and 'self.log(f"[{task_id[:8]}] {pl_note}")' in dl)
ck("C6 两条出文件名的那一路都改用 dl_dir（固定安全名那一支和模板那一支）",
   'out_tmpl = str(Path(dl_dir) / f"{safe_title}' in dl
   and "out_tmpl = str(Path(dl_dir) / template)" in dl)
ck("C7 没有残留还拿 out_dir 拼 outtmpl 的老写法（留一处就等于那一趟不建夹）",
   'Path(out_dir) / f"{safe_title}' not in dl
   and "Path(out_dir) / template" not in dl)
ck("C8 名字两个来处都在：容器标题优先，否则用请求带过来的那份",
   '(info or {}).get("title")' in dl and 'cfg.get("playlist_folder")' in dl)

ck("C9 界面：下载页那一格有勾、也有说明",
   'v-model="opts.playlist_subdir"' in IDX and "tr('home.playlistSubdir')" in IDX
   and "tr('home.playlistSubdirHint')" in IDX)
ck("C10 界面：设置页「合集落点」那一格绑的是同一个键",
   'v-model="settings.playlist_subdir"' in IDX)
ck("C11 界面：重开页面按后端存的值回填（两处都回填，不然一次保存就把存好的冲掉）",
   "opts.value.playlist_subdir = !!data.playlist_subdir;" in IDX
   and "settings.value.playlist_subdir = !!data.playlist_subdir;" in IDX)
ck("C12 界面：整表 / 选中分集 / 单条补下三颗入口都把合集名带过去，用完清空",
   IDX.count("opts.value.playlist_folder = mediaInfo.value.title") == 3
   and IDX.count("opts.value.playlist_folder = '';") >= 3,
   str(IDX.count("opts.value.playlist_folder = mediaInfo.value.title")))
ck("C13 opts 默认值里这两个键都在（少一个就是界面绑定到 undefined）",
   "playlist_subdir: false," in IDX and "playlist_folder: ''," in IDX)
ck("C14 恢复默认那张表给这个键留了人话名（settingsave_test 钉的是「有控制项就要有名」）",
   '"playlist_subdir": "' in IDX)
ck("C15 文件名模板那句说明不再举例带「/」的写法（模板里的分隔符会被换成「_」，写了也出不来目录）",
   "%(uploader)s/%(title)s" not in IDX and "会被换成「_」" in IDX)
ck("C16 中英两边都有这两个键（i18n 的门是逐个键比对的）",
   I18N.count("'home.playlistSubdir'") == 2 and I18N.count("'home.playlistSubdirHint'") == 2)

# ---------------------------------------------------------------- D. 端点实测
print("== D. 端点实测：请求里的开关与合集名真的落到任务的 opts 上（假队列，不真下载） ==")


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)

    def save(self):
        pass


class FakeQueue:
    def __init__(self):
        self.calls: list[dict] = []

    def add_urls(self, urls, opts):
        self.calls.append({"urls": list(urls), "opts": dict(opts)})
        return ["fake-%d" % len(self.calls)]


ORIG = {k: getattr(S, k, None) for k in ("cfg", "log_mgr", "queue")}
fq = FakeQueue()
try:
    S.cfg = FakeCfg({"download_dir": str(SHARD / "dl"), "playlist_subdir": False})
    S.log_mgr = type("L", (), {"log": staticmethod(lambda *a, **k: None)})()
    S.queue = fq
    eps = ["https://www.bilibili.com/video/BV1AAAAAAAA", "https://www.bilibili.com/video/BV2BBBBBBBB"]
    S.api_download(S.AddUrlsBody(urls=eps, playlist_subdir=True, playlist_folder=PL_TITLE))
    S.api_download(S.AddUrlsBody(urls=eps))          # 没带＝开关跟全局、合集名没有
    o1 = fq.calls[0]["opts"] if fq.calls else {}
    o2 = fq.calls[1]["opts"] if len(fq.calls) > 1 else {}
    ck("D1 带过来的开关与合集名逐条落到任务 opts（两条链接共用同一批的合集名）",
       o1.get("playlist_subdir") is True and o1.get("playlist_folder") == PL_TITLE
       and len(fq.calls[0]["urls"]) == 2, str({k: o1.get(k) for k in ("playlist_subdir", "playlist_folder")}))
    ck("D2 没带时是 None（不是 False 覆盖全局、也不是空串冒充合集名）",
       o2.get("playlist_subdir") is None and o2.get("playlist_folder") is None,
       str({k: o2.get(k) for k in ("playlist_subdir", "playlist_folder")}))
    ck("D3 同一批的链接没被拆开（12 集一次入队还是一个批量）",
       all(c["opts"].get("playlist_folder") in (PL_TITLE, None) for c in fq.calls))
finally:
    for k, v in ORIG.items():
        setattr(S, k, v)

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
