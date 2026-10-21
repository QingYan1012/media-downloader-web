#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人声分离（#78）离线自检：两套引擎共用一个独立 venv，引擎/权重/设备都能在界面上选。

钉的是这几件容易悄悄坏掉的事：
A. 引擎表与界面选项一致 —— DEMUCS_MODELS 和下拉里那几条必须一模一样，
   否则「保存设置」那一道只认表内值的闸门会把界面自己给出去的选项判成非法。
B. CPU 档的机制 —— 本机实测 CUDA_VISIBLE_DEVICES 藏不住 GPU，只有「import audio_separator
   之前把 torch.cuda.is_available 换成 False」这一种成立。顺序一挪，CPU 那格就变假。
C. 状态回包把「缺哪一层」说清 —— venv / runner / import / weights 四种是四句不同的话。
D. 选了 GPU 却没跑在 GPU 上必须自己说破，不能默默用 CPU 交差。
E. 权重下载写 .part 再改名 —— 半截文件落在真名字上会被当成「已就绪」放进选项。
F. 界面接线：端点换了名字、菜单项跟上了、四个新键在默认表 / ConfigBody / 人话名表 / 两份词表里都有。
G. 打包：入口脚本进包，venv 与权重不进包（口径定的）。

全程不起子进程、不联网、不碰真 config.json（探测与权重表都换成假的）。
跑法：PYTHONIOENCODING=utf-8 python tests/separator_test.py
"""
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
RUNNER = (ROOT / "separator_runner.py").read_text(encoding="utf-8")
PACK = (ROOT / "pack_release.py").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
VT_SRC = (ROOT / "voice_tools.py").read_text(encoding="utf-8")

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


import voice_tools as V  # noqa: E402
import server as S  # noqa: E402

# ------------------------------------------------------------ A. 两张引擎表
ck("A1 预载的 RoFormer 就是 BS 与 Mel-Band 两家，四条 id 不重名",
   [m["family"] for m in V.ROFORMER_MODELS] == ["bs_roformer", "bs_roformer",
                                                "mel_band_roformer", "mel_band_roformer"]
   and len({m["id"] for m in V.ROFORMER_MODELS}) == 4,
   str([m["id"] for m in V.ROFORMER_MODELS]))
ck("A2 每条权重都有 ckpt 与 yaml 两个真文件名（只给一个就跑不起来）",
   all(m.get("file") and m.get("yaml") for m in V.ROFORMER_MODELS))
ck("A3 设备只有三档，界面不会给出去第四个", V.SEPARATION_DEVICES == ["auto", "cpu", "cuda"],
   str(V.SEPARATION_DEVICES))

_demucs_block = HTML[HTML.index('v-model="settings.demucs_model"'):]
_demucs_block = _demucs_block[:_demucs_block.index("</el-select>")]
_ui_demucs = re.findall(r'<el-option label="([^"]+)" value="([^"]+)"', _demucs_block)
ck("A4 Demucs 下拉里的选项和后端那张表逐条相等（不一致时保存会把界面自己的选项判成非法）",
   [v for _l, v in _ui_demucs] == V.DEMUCS_MODELS, f"界面={[v for _l, v in _ui_demucs]} 表={V.DEMUCS_MODELS}")
_ui_roformer = re.findall(r'v-for="m in sepModels"', HTML)
ck("A5 RoFormer 那格是照后端那张表渲染的，不在界面里抄第二份名单",
   len(_ui_roformer) == 1 and "SEP_MODEL_NAMES" in HTML)

ck("A6 每条权重都钉了 ckpt 与 yaml 两个校验值（这条路径上 TLS 不验证，值是唯一能挡住截断和镜像错位的）",
   all(re.fullmatch(r"[0-9a-f]{64}", m.get("file_sha256") or "")
       and re.fullmatch(r"[0-9a-f]{64}", m.get("yaml_sha256") or "") for m in V.ROFORMER_MODELS))

# ------------------------------------------------------------ B. CPU 档的机制
_imp_as = RUNNER.index("from audio_separator")
_patch_at = RUNNER.index("torch.cuda.is_available = lambda: False")
ck("B1 CPU 档改的是包自己据以选设备的那个判断，且必须排在 import audio_separator 之前",
   _patch_at < _imp_as, f"patch={_patch_at} import={_imp_as}")
ck("B2 这个顺序写在注释里说清了原因（不然下次有人会把它「整理」到 import 后面）",
   "CUDA_VISIBLE_DEVICES" in RUNNER and "is_available" in RUNNER)
ck("B3 设备三档在 runner 里各自有落点，非法值退回 auto 而不是拼进命令行",
   '"--device"' in VT_SRC and "device if device in V" not in VT_SRC
   and 'device if device in SEPARATION_DEVICES else "auto"' in VT_SRC)
ck("B4 回包里的 actual_device 是问 torch 要的，不是问设置要的",
   "actual_device" in RUNNER and "device_matched" in RUNNER)

# ------------------------------------------------------------ C. 状态回包分层
_real_probe, real_models = V.separation_probe, V.roformer_model_states
try:
    def _mk(venv=True, runner=True, as_ok="ok", ready=2, gpu=False):
        V.separation_probe = lambda refresh=False: {
            "python_present": venv, "runner_present": runner,
            "audio_separator_import": as_ok, "demucs_import": "ok",
            "audio_separator_version": "0.47.0", "demucs_version": "4.1.0",
            "torch": "2.14.1+cu130", "cuda_available": gpu, "gpu_name": "X" if gpu else "",
            "vram_gib": 8.0 if gpu else None}
        V.roformer_model_states = lambda: [
            {"id": f"m{i}", "present": i < ready, "missing": "" if i < ready else "ckpt",
             "file": f"{i}.ckpt", "yaml": f"{i}.yaml"} for i in range(4)]

    V._setup_lock.acquire()
    try:
        V.separator_python = lambda: "PY"
        _mk(ready=2)
        r = S.api_voice_status()
        ck("C0 搭建任务在跑时回包说得出「正在搭」（界面那枚转圈跟的是它，不是猜的秒数）",
           r["separation"]["setup_running"] is True, str(r["separation"]["setup_running"]))
    finally:
        V._setup_lock.release()

    V.separator_python = lambda: ""
    _mk(venv=False)
    ck("C1 缺 venv：两个引擎的 reason 都是 venv，available 全 False",
       all(e["reason"] == "venv" and not e["available"]
           for e in S.api_voice_status()["separation"]["engines"]))
    V.separator_python = lambda: "PY"
    _mk(runner=False)
    st = S.api_voice_status()["separation"]
    ck("C2 venv 在、runner 不在：RoFormer 的 reason 换成 runner，但 Demucs 照旧可用 —— "
       "它走 python -m demucs，不经过那个入口脚本（两者缺的不是同一个文件）",
       {e["id"]: (e["reason"], e["available"]) for e in st["engines"]}
       == {"roformer": ("runner", False), "demucs": ("", True)},
       str([(e["id"], e["reason"], e["available"]) for e in st["engines"]]))
    _mk(runner=True, as_ok="no module named foo")
    ck("C3 包 import 不动：RoFormer 的 reason 是 import，Demucs 不看它（各自一个包）",
       {e["id"]: e["reason"] for e in S.api_voice_status()["separation"]["engines"]}
       == {"roformer": "import", "demucs": ""})
    _mk(as_ok="ok", ready=0)
    ck("C4 一条权重都没有：reason 是 weights，ready_models 是空的",
       S.api_voice_status()["separation"]["engines"][0]["reason"] == "weights"
       and S.api_voice_status()["separation"]["ready_models"] == [])
    _mk(as_ok="ok", ready=2, gpu=True)
    st = S.api_voice_status()["separation"]
    ck("C5 齐了：reason 是空、default_model 取第一条就绪的、GPU 读数照搬探测结果",
       st["engines"][0]["reason"] == "" and st["default_model"] == "m0"
       and st["cuda_available"] is True, str(st["default_model"]))
    ck("C7 回包带两个引擎包的版本与可用标记（设置页要列出用的是什么）",
       st["audio_separator_version"] == "0.47.0" and st["demucs_version"] == "4.1.0"
       and st["audio_separator_ok"] is True and st["demucs_ok"] is True,
       str({k: st[k] for k in ("audio_separator_version", "demucs_version",
                               "audio_separator_ok", "demucs_ok")}))
    ck("C6 回包不再给那个笼统的 demucs 布尔（一个 bool 说不清缺哪一层）",
       "demucs" not in S.api_voice_status())
finally:
    V.separation_probe, V.roformer_model_states = _real_probe, real_models
    V.separator_python = real_venv_py = V.__dict__["separator_python"]

# ------------------------------------------------------------ D. 设备不许说谎
try:
    V.separation_probe = lambda refresh=False: {"cuda_available": False, "demucs_import": "ok",
                                                "audio_separator_import": "ok"}
    try:
        V.separate_demucs("x", device="cuda")
        ck("D1 看不到 CUDA 却要 GPU：直接抛错，不悄悄改用 CPU 跑完", False, "没抛")
    except RuntimeError as e:
        ck("D1 看不到 CUDA 却要 GPU：抛的那句点名 CUDA", "CUDA" in str(e), str(e)[:70])
    except Exception as e:
        ck("D1 看不到 CUDA 却要 GPU：抛错但句式变了", False, f"{type(e).__name__}: {str(e)[:70]}")
finally:
    V.separation_probe = _real_probe
ck("D2 分离端点里那条「选了 GPU 实际在 CPU」的 warning 还在（回包说真话的那一半）",
   re.search(r'device == "cuda".*?\n.*?没跑在 GPU', SERVER, re.S) is not None)

# ------------------------------------------------------------ E. 权重下载的卫生
ck("E1 下载先写 .part 再改名（半截文件不能顶着真名字被当成就绪）",
   ".part" in VT_SRC and 'os.replace(part, dest)' in VT_SRC)
ck("E2 比对了字节数：requests 被掐断时只会正常结束，不比对就会把半截当完整",
   'Content-Length' in VT_SRC and "字节数对不上" in VT_SRC)
ck("E3 续传走 Range，且认 206/416 两种回码（416 = .part 本身就是全的）",
   'bytes={have}-' in VT_SRC and "416" in VT_SRC and '"ab"' in VT_SRC)
ck("E4 候选地址来自 pkg_update 的镜像表（GitHub 直连不通的机器也下得动）",
   "github_url_candidates" in VT_SRC)
ck("E5 ckpt 与 yaml 各自的基址分开写：官方那批 yaml 在主基址全是 404",
   V.SEP_CKPT_BASE in V.SEP_YAML_BASE.replace("/releases/download/model-configs", "")
   or (V.SEP_CKPT_BASE != V.SEP_YAML_BASE and "model-configs" in V.SEP_YAML_BASE),
   V.SEP_YAML_BASE)
ck("E6 「缺的是 ckpt 还是 yaml」在状态里分得开（两种处置不一样）",
   '"ckpt_present"' in VT_SRC and '"yaml_present"' in VT_SRC and '"missing"' in VT_SRC)

# ------------------------------------------------------------ F. 界面接线
ck("F1 老端点 /api/ai/demucs 已经从程序与界面里退干净",
   "/api/ai/demucs" not in SERVER and "/api/ai/demucs" not in HTML)
ck("F2 新端点在：vocal_separate 收引擎/权重/设备三项设置，separator_setup 管搭建",
   '@app.post("/api/ai/vocal_separate")' in SERVER
   and '@app.post("/api/ai/separator_setup")' in SERVER)
ck("F3 环境根本不在时不用等三十秒：端点先把 venv 这一层报出来再回",
   SERVER.index('if not separator_python() or not SEP_RUNNER.is_file()')
   < SERVER.index("def job():", SERVER.index('@app.post("/api/ai/vocal_separate")')))
ck("F4 四个新键在默认表、ConfigBody、校验闸门三处都齐",
   all(k in S.cfg.DEFAULTS and k in S.ConfigBody.model_fields
       for k in ("vocal_engine", "roformer_model", "ai_device", "vocal_native_fp16"))
   and all(f'("{k}"' in SERVER for k in ("vocal_engine", "ai_device", "roformer_model"))
   and '"demucs_model"' in SERVER)
ck("F5 默认是 auto：GPU 被人占着时降级跑，而不是抛错让人以为功能坏了",
   S.cfg.DEFAULTS["ai_device"] == "auto" and S.cfg.DEFAULTS["vocal_engine"] == "roformer")
ck("F6 文件页菜单指到新函数，command 与 FILE_ACTIONS、return 名单三处对得上",
   "aiVocalSeparate|" in HTML and HTML.count("aiVocalSeparate") >= 5
   and "aiDemucs" not in HTML)
ck("F7 语音页三个下拉绑的就是那四个键，成品去向写在卡片里",
   all(f'v-model="settings.{k}"' in HTML for k in
       ("vocal_engine", "roformer_model", "ai_device", "vocal_native_fp16")))
ck("F8 GPU 那一项在探不到 CUDA 时是灰的，不是点下去才报错",
   ':disabled="!sepHasGpu"' in HTML)
ck("F9 缺权重的那几条在选项里标出来且禁用，但仍留在列表里（让人知道要去点「下载权重」）",
   ':disabled="!m.present"' in HTML and 'sepModelLabel(m)' in HTML)
ck("F10 状态文案只从 separation 那一段拼，不再读那个已经不存在的 s.demucs 布尔"
   "（注意别拿 settings.demucs_model 当它，那一条是真存在的设置键）",
   re.search(r"s\.demucs\s*[?.;]", HTML) is None and "sepInfo.value" in HTML)
_zh = I18N[I18N.find("    zh: {"):I18N.find("\n    en: {")]
_en = I18N[I18N.find("\n    en: {"):]
_newkeys = ["settings.cfg.vocal_engine", "settings.cfg.roformer_model",
            "settings.cfg.ai_device", "settings.cfg.vocal_native_fp16",
            "settings.voiceStatusReadFail", "settings.voiceStatusNoSep"]
ck("F11 新增的词表键两份都有（恢复默认那张表靠它们说人话）",
   all(f"'{k}'" in _zh and f"'{k}'" in _en for k in _newkeys),
   str([k for k in _newkeys if f"'{k}'" not in _zh or f"'{k}'" not in _en]))
ck("F12 四个键在人话名表里有名字（settingsave I5 那条闸门的正面）",
   all(f'"{k.split(".")[-1]}":' in HTML for k in _newkeys[:4]))
ck("F13 语音页一进去就取状态：那三个下拉没有别的来源",
   "if (p === 'voice') loadVoiceStatus();" in HTML)
ck("F14 搭建转圈跟的是服务端的 setup_running，不是前端自己数的秒",
   "setup_running" in HTML and "const sepBusy = computed" in HTML)
# 活体跑抓到的那一条：五格下拉绑在 settings 上、后端也存了，但 loadConfig 从不回填，
# 于是配置里写着 cuda、页面开出来显示「自动」。通用闸门是 settingsave 的 I27，这里钉自己这五格。
_lc = HTML[HTML.index("async function loadConfig()"):HTML.index("function applyDark")]
ck("F15 五个分离设置在 loadConfig 里真回填（只写不读 = 界面显示的是默认值不是存的那个）",
   all(re.search(r"settings\.value\.%s\s*=" % k, _lc) for k in
       ("vocal_engine", "roformer_model", "demucs_model", "ai_device", "vocal_native_fp16")),
   str([k for k in ("vocal_engine", "roformer_model", "demucs_model", "ai_device",
                    "vocal_native_fp16") if not re.search(r"settings\.value\.%s\s*=" % k, _lc)]))
ck("F16 组件页把两个引擎包与版本列出来，不只一句权重就绪数",
   "RoFormer · audio-separator {{ sepRoformerVer }}" in HTML
   and "Demucs · demucs {{ sepDemucsVer }}" in HTML
   and "torch {{ sepTorchVer }}" in HTML)
ck("F17 回包缺两个包的字段时界面说「版本未知」，不冒充「未安装」",
   "settings.sepVerUnknown" in HTML and "sepPkgVer(sepInfo.value" in HTML)

# ------------------------------------------------------------ G. 打包
ck("G1 入口脚本进包（voice_tools 只拼路径调它，漏了就是「能选引擎」成空话）",
   '"separator_runner.py"' in PACK)
ck("G2 venv 与权重都不进包：打包没有一条路径把 tools/separator 拷过去（口径定的）",
   re.search(r'tools.{0,40}separator', PACK.replace('"separator_runner.py"', "")) is None)
ck("G3 独立环境钉的是具体版本，不是「装个最新的」",
   all("==" in p for p in V.SEP_ENGINE_PINS) and len(V.SEP_ENGINE_PINS) == 2,
   str(V.SEP_ENGINE_PINS))
ck("G4 建 venv 用主程序的 python，demucs 也只往这个 venv 装（不再回主环境）",
   "[sys.executable, \"-m\", \"venv\"" in VT_SRC
   and 'cmd = [py, "-m", "pip"' in VT_SRC)

# ------------------------------------------------------------ H. 上游版本检测与更新
# 这两个包在独立 venv 里，组件表那套 installed_version 问的是主环境，天然看不见它们。
# 抓的就是「0.47.1 已经发布，界面还只有 获取 / 补齐、通知条也不报」这一次。
_SV = V.separator_engine_versions
try:
    V.separator_engine_versions = lambda refresh=False: {"audio-separator": "0.47.0", "demucs": "4.1.0"}
    lv = {"audio-separator": {"version": "0.47.1"}, "demucs": {"version": "4.1.0"}}
    st = S._sep_engine_state(lv)
    ck("H1 两个引擎读得出当前版本，0.47.0 对 0.47.1 判可更新、同版本的不算",
       st["installed"] and {i["pkg"]: (i["active"], i["latest"], i["updatable"])
                            for i in st["items"]}
       == {"audio-separator": ("0.47.0", "0.47.1", True),
           "demucs": ("4.1.0", "4.1.0", False)}, str(st))
    av = S._sep_engine_available(lv)
    ck("H2 检测名单只报一条 sep:engines，带着包名与「当前 → 最新」",
       len(av) == 1 and av[0]["key"] == "sep:engines" and av[0]["pkg"] == "audio-separator"
       and av[0]["current"] == "0.47.0" and av[0]["latest"] == "0.47.1", str(av))
    ck("H3 同版本不算更新（反向验证，别把每一次检查都报成有新版）",
       S._sep_engine_available({"audio-separator": {"version": "0.47.0"}}) == [])
    V.separator_engine_versions = lambda refresh=False: {}
    ck("H4 没建 venv / 读不到版本时不算更新，也不在开机时催装",
       not S._sep_engine_state(lv)["installed"] and S._sep_engine_available(lv) == [])
finally:
    V.separator_engine_versions = _SV
ck("H5 后台检测把引擎条目并进 available（否则通知条与侧栏点永远不报它）",
   "available += _sep_engine_available(lv)" in SERVER)
ck("H6 一键更新认得 sep:engines（名单进了、接口不认就只会弹确认再 400）",
   '"sep:engines"' in SERVER and 'key == "sep:engines"' in SERVER)
ck("H7 更新走 venv 里的 pip -U 并回读版本；新建环境的钉死版本不被改写",
   "def update_separator_engines" in VT_SRC
   and '"install", "-U"' in VT_SRC
   and "separator_engine_versions(refresh=True)" in VT_SRC
   and "audio-separator==0.47.0" in VT_SRC)
ck("H8 界面有常驻「更新」按钮与最新版标签：按钮不按有无更新切换显隐，样式与普通组件行一致",
   ':loading="sepBusy" @click="updateSeparatorEngines"' in HTML
   and 'v-if="sepUpdatable"' not in HTML
   and 'type="primary" plain :loading="sepBusy" @click="updateSeparatorEngines"' not in HTML
   and "setupSeparator('engines')" in HTML and "sepLatest('audio-separator')" in HTML)
ck("H9 separator_setup 接受 engines；setup_separator 把它转给更新函数，不重复进锁",
   '"venv", "weights", "all", "engines"' in SERVER
   and 'if step == "engines":' in VT_SRC)
ck("H10 更新与搭建的回话分开说：点「更新」不该回一句「搭建中」",
   "分离引擎更新中，进度看运行日志" in SERVER
   and '"srv.ai.update_ready"' in SERVER and '"srv.ai.update_failed"' in SERVER)

# ------------------------------------------------- I. 六轨与分轨混音台（参照 StemDeck）
_stems_block = HTML[HTML.index('v-model="settings.demucs_stems"'):]
_stems_block = _stems_block[:_stems_block.index("</el-select>")]
ck("I1 分轨范围三档在界面上给全，且值与后端那张表逐条相等（不一致时保存闸门会判界面自己的选项非法）",
   sorted(re.findall(r'value="(vocal|four|six)"', _stems_block)) == sorted(V.DEMUCS_STEMS_MODES)
   and [f'value="{x}"' for x in V.DEMUCS_STEMS_MODES]
   and all(f'value="{x}"' in _stems_block for x in V.DEMUCS_STEMS_MODES),
   str(V.DEMUCS_STEMS_MODES))
ck("I2 默认值仍是只取人声：DEFAULTS、前端 settings 初值、loadConfig 回填三处都说 vocal（改了默认等于替老用户重跑分离）",
   '"demucs_stems": "vocal"' in SERVER and "demucs_stems: 'vocal'," in HTML
   and "settings.value.demucs_stems" in HTML)
ck("I3 demucs_stems 上了保存那道闸门（它是直接拼进子进程命令行的参数，脏值不能进）",
   '("demucs_stems", tuple(DEMUCS_STEMS_MODES)' in SERVER and "DEMUCS_STEMS_MODES" in SERVER)
ck("I4 --two-stems 只在 vocal 档出现，four/six 走全轨（写死它就一直只有两条）",
   VT_SRC.index('if mode == "vocal":') < VT_SRC.index('"--two-stems", "vocals"')
   and VT_SRC.count('"--two-stems"') == 1)
ck("I5 六轨只允许 htdemucs_6s，且界面与后端两处都拦（跑完几分钟才发现轨数不对太亏）",
   'if mode == "six" and cap < 6' in VT_SRC and '(stems_mode == "six" and cap < 6)' in SERVER
   and ':disabled="settings.demucs_model !== \'htdemucs_6s\'"' in HTML)
ck("I6 六轨模型进表的条件是这台机器真跑通过（实测：4 秒片段 CPU 262 s，出 bass/drums/guitar/other/piano/vocals）",
   "htdemucs_6s" in V.DEMUCS_MODELS and V.DEMUCS_STEMS_BY_MODEL.get("htdemucs_6s") == 6,
   str(V.DEMUCS_STEMS_BY_MODEL))
# 混音导出：filter 链少一个 ';' 就是 500（第一版就是这么翻车的），别让它回潮
def _slice(src, start, stop):
    """按标记截一段函数体；标记找不到就退回整段尾部，绝不让整套自检在 ValueError 上中断。"""
    a = src.find(start)
    if a < 0:
        return ""
    b = src.find(stop, a)
    return src[a:(b if b > a else len(src))]


_mix_fn = _slice(SERVER, "def api_voice_mix", '@app.get("/api/voice/stems")')
ck("I7 混音的 filter_complex 用 ';' 串起来（连写会被 ffmpeg 判成非法 filterchain，接口直接 500）",
   '";".join(labels)' in _mix_fn and '";" + "".join' in _mix_fn)
ck("I8 混音只收下载目录里的成品，且至少两条不静音的轨（静音的不进命令）",
   "只能混下载目录里的成品" in _mix_fn and "至少留两条不静音的轨" in _mix_fn
   and "if not isinstance(t, dict) or t.get(\"mute\"):" in _mix_fn)
ck("I9 amix 关掉 normalize：不然界面调好的平衡和写出来的文件不是一个东西",
   "normalize=0" in _mix_fn and "duration=longest" in _mix_fn)
_stem_fn = _slice(SERVER, "def api_voice_stems", '@app.post("/api/ai/tts")')
ck("I10 轨列表按曲名那一层精确取，并排掉自己的混音成品（不然重载一次会把 mix 当成第七条轨）",
   'rglob(f"{media.stem}/*.wav")' in _stem_fn and "MIX_NAME_MARK in cand.name" in _stem_fn
   and 'MIX_NAME_MARK = "-mix-"' in SERVER and 'f"{stem}-mix-' in SERVER)
ck("I11 混音台卡在语音页里，行内有静音/独奏/音量/循环与导出，全部文字走 tr()",
   "voice.mixTitle" in HTML and 'class="row row--tight mix-row"' in HTML
   and "applyMixGains" in HTML and "exportMix" in HTML)
ck("I12 混音台的七个新名字都挂进了 setup 的 return（漏一个整页渲染炸，不是少一行）",
   all(("mixSrc, " in HTML or "mixSrc," in HTML) for _ in [0])
   and "stemLabel, streamUrl, loadStems, applyMixGains, applyMixLoop, toggleMixPlay, exportMix," in HTML)
_dict_src = I18N
_mix_keys = ["voice.mixTitle", "voice.mixCount", "voice.mixExportHint", "voice.stemVocals",
             "voice.stemGuitar", "voice.stemsSix", "srv.ai.mix_done", "srv.ai.mix_failed"]
_zh_half = _dict_src[:_dict_src.index("\n    en: {")]
_pad = [k for k in _mix_keys
        if (m := re.search(r"^      '%s': '(.*?)',$" % re.escape(k), _zh_half, re.M))
        and m.group(1) != m.group(1).strip()]
_han = [k for k in _mix_keys
        if re.search(r"[\u4e00-\u9fff]", "".join(re.findall(
            r"^      '%s': '(.*?)',$" % re.escape(k), _dict_src[_dict_src.index("\n    en: {"):], re.M)))]
ck("I13 新键两份词表都在（各出现两次），zh 那半不带首尾空格、en 那半不含汉字"
   "（只查这批新键，不拿整份词表当靶子 —— 拼接片段本来就以空格为内容）",
   all(_dict_src.count(f"'{k}':") == 2 for k in _mix_keys) and not _pad and not _han,
   f"空格 {list(_pad)} 汉字 {list(_han)}")
ck("I14 混音那两条后端日志从一开始就带键与 kv（#55 口径：新写的句子不留裸中文）",
   'k="srv.ai.mix_done"' in _mix_fn and 'k="srv.ai.mix_failed"' in _mix_fn)

print(f"== 汇总 ==\n共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    for f in FAILED:
        print("FAIL " + f)
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
