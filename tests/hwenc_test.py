r"""视频编码器选择 / 探测 / 降级链自检（#26 硬件编码 + x265）。

全内存跑：假的 ffmpeg 路径、假 subprocess、直接改 `cfg.data` 与 `_encoder_probe_cache`，
不起真转码、不写 config.json、不联网。断言的是「链怎么排、参数长什么样、哪些接口接线了」。

跑法：`python tests/hwenc_test.py`
"""
from __future__ import annotations

import contextlib
import subprocess as _sp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAILED: list[str] = []
TOTAL = 0
saved_cfg = {k: S.cfg.data.get(k) for k in ("video_encoder", "video_cpu_codec", "video_cpu_preset")}
orig_sp_run, orig_sp_popen = _sp.run, _sp.Popen


def ck(name: str, cond, extra: str = ""):
    global TOTAL
    TOTAL += 1
    if not bool(cond):
        FAILED.append(name)
        print(f"FAIL {name} {extra}")
    else:
        print(f"PASS {name}")


@contextlib.contextmanager
def fake_sub(run=None, popen=None):
    """临时把 server 里那个 subprocess 的出口换成记账函数。"""
    orig_run, orig_popen = _sp.run, _sp.Popen
    try:
        if run is not None:
            _sp.run = run
        if popen is not None:
            _sp.Popen = popen
        yield
    finally:
        _sp.run, _sp.Popen = orig_run, orig_popen


@contextlib.contextmanager
def pref(mode=None, codec=None, preset=None):
    """只在内存里改这三项设置，出作用域原样还回去。"""
    saved = {k: S.cfg.data.get(k) for k in ("video_encoder", "video_cpu_codec", "video_cpu_preset")}
    try:
        if mode is not None:
            S.cfg.data["video_encoder"] = mode
        if codec is not None:
            S.cfg.data["video_cpu_codec"] = codec
        if preset is not None:
            S.cfg.data["video_cpu_preset"] = preset
        yield
    finally:
        S.cfg.data.update(saved)


@contextlib.contextmanager
def probe_cache(items=None, ts=None, built=None):
    saved = dict(S._encoder_probe_cache)
    try:
        S._encoder_probe_cache.update(
            ts=time.time() if ts is None else ts,
            ffmpeg="X:\\fake\\ffmpeg.exe",
            items=items if items is not None else {},
            built=built if built is not None else set(),
        )
        yield
    finally:
        S._encoder_probe_cache.clear()
        S._encoder_probe_cache.update(saved)


def encs(chain):
    return [c["encoder"] for c in chain]


# ---------- A. 编码器参数口径 ----------
a1 = S._encoder_args("libx264", 23, "medium")
ck("A1 x264 参数", a1 == ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p"], str(a1))
a2 = S._encoder_args("libx265", 23, "fast")
ck("A2 x265 参数", a2[:6] == ["-c:v", "libx265", "-preset", "fast", "-crf", "23"] and "-tag:v" in a2, str(a2))
ck("A3 HEVC 才补 hvc1", "-tag:v" not in a1 and a2[a2.index("-tag:v") + 1] == "hvc1")
a4 = S._encoder_args("hevc_nvenc", 28, "slow")
ck("A4 nvenc 用 cq 不是 crf", a4[2:4] == ["-preset", "p5"] and "-cq" in a4 and "-crf" not in a4, str(a4))
ck("A5 nvenc 要 -b:v 0 才真按 cq 走", a4[a4.index("-b:v") + 1] == "0" and "-rc" in a4)
a6 = S._encoder_args("hevc_qsv", 26, "medium")
ck("A6 qsv 用 global_quality", a6[2:4] == ["-preset", "medium"] and a6[a6.index("-global_quality") + 1] == "26", str(a6))
a7 = S._encoder_args("hevc_amf", 26, "fast")
ck("A7 amf 用 qp_i/qp_p", a7[a7.index("-qp_i") + 1] == "26" and a7[a7.index("-qp_p") + 1] == "26", str(a7))
ck("A8 硬件的两条像素格式不是 yuv420p",
   a6[a6.index("-pix_fmt") + 1] == "nv12" and a7[a7.index("-pix_fmt") + 1] == "nv12")
ck("A9 nvenc 档位映射", all(S._encoder_args("hevc_nvenc", 23, p)[2:4] == ["-preset", q]
                            for p, q in (("veryfast", "p1"), ("fast", "p2"), ("medium", "p4"), ("slow", "p5"))))
ck("A10 认不出的档位退回 medium", S._encoder_args("libx264", 23, "insane")[2:4] == ["-preset", "medium"])
ck("A11 quality 夹在 0..51", S._encoder_args("libx264", 99, "fast")[5] == "51"
    and S._encoder_args("libx264", -5, "fast")[5] == "0")
try:
    S._encoder_args("libvpx-vp9", 23, "fast")
    ck("A12 不认识的编码器要报错", False)
except ValueError:
    ck("A12 不认识的编码器要报错", True)

# ---------- B. 设置取值归一化 ----------
with pref("cpu", "x264", "medium"):
    ck("B1 默认口径", S._video_encode_pref() == {"mode": "cpu", "codec": "x264", "preset": "medium"})
with pref("NVIDIA", "X265", " Slow "):
    p = S._video_encode_pref()
    ck("B2 大小写与空格归一", p == {"mode": "nvidia", "codec": "x265", "preset": "slow"}, str(p))
with pref("arm64", "av1", "ultra"):
    p = S._video_encode_pref()
    ck("B3 认不出的写法回默认", p == {"mode": "cpu", "codec": "x264", "preset": "medium"}, str(p))
with pref("", "", ""):
    ck("B4 空串也回默认", S._video_encode_pref() == {"mode": "cpu", "codec": "x264", "preset": "medium"})
with pref("vaapi", "x264", "medium"):
    ck("B5 没做的厂商不静启用别的", S._video_encode_pref()["mode"] == "cpu")
ck("B6 厂商表与模式表对齐", set(S.VIDEO_ENCODER_MODES) == {"auto", "cpu"} | set(S.HW_ENCODER_BY_VENDOR))
ck("B7 CPU 两条 codec 都在表里", set(S.VIDEO_CPU_CODECS) == set(S.CPU_ENCODER))

# ---------- C. 降级链 ----------
with pref("cpu", "x264", "medium"), probe_cache({}, 0.0):
    c = S._video_encode_chain(23)
    ck("C1 cpu/x264 首选 x264", encs(c) == ["libx264", "libx265"], str(encs(c)))
    ck("C2 x265 超时预算放大", [x["timeout_mult"] for x in c] == [1.0, S.X265_TIMEOUT_MULT])
with pref("cpu", "x265", "slow"), probe_cache({}, 0.0):
    c = S._video_encode_chain(23)
    ck("C3 cpu/x265 首选 x265", encs(c) == ["libx265", "libx264"], str(encs(c)))
    ck("C4 兜底那条不再放大预算", c[0]["timeout_mult"] == S.X265_TIMEOUT_MULT and c[1]["timeout_mult"] == 1.0)
    ck("C5 档位跟着设置走", c[0]["args"][2:4] == ["-preset", "slow"])
with pref("nvidia", "x264", "medium"), probe_cache({}, 0.0):
    c = S._video_encode_chain(23)
    ck("C6 厂商优先、CPU 垫底", encs(c) == ["hevc_nvenc", "libx264", "libx265"], str(encs(c)))
with pref("auto", "x264", "medium"), probe_cache({}, 0.0):
    c = S._video_encode_chain(23)
    ck("C7 auto 按厂商顺序挨个试",
       encs(c) == ["hevc_nvenc", "hevc_qsv", "hevc_amf", "libx264", "libx265"], str(encs(c)))
dead = {"hevc_nvenc": {"available": False, "reason": "驱动不行"},
        "hevc_qsv": {"available": True, "reason": ""},
        "hevc_amf": {"available": False, "reason": "挂住"},
        "libx265": {"available": False, "reason": "不该看这条"},
        "libx264": {"available": False, "reason": "不该看这条"}}
with pref("auto", "x264", "medium"), probe_cache(dead, time.time()):
    c = S._video_encode_chain(23)
    ck("C8 探测说起不来的硬件被摘掉", "hevc_nvenc" not in encs(c) and "hevc_amf" not in encs(c), str(encs(c)))
    ck("C9 CPU 的两条永不摘（探测说它不可用也不摘）", encs(c) == ["hevc_qsv", "libx264", "libx265"], str(encs(c)))
with pref("auto", "x264", "medium"), probe_cache(dead, time.time() - 99999):
    c = S._video_encode_chain(23)
    ck("C10 探测过期就当没探测过", encs(c) == ["hevc_nvenc", "hevc_qsv", "hevc_amf", "libx264", "libx265"], str(encs(c)))
with pref("nvidia", "x264", "medium"), probe_cache(dead, time.time()):
    c = S._video_encode_chain(23)
    ck("C11 点名 nvenc 而起不来时也不会空链", encs(c) == ["libx264", "libx265"], str(encs(c)))
with pref("amd", "x265", "fast"), probe_cache({}, 0.0):
    c = S._video_encode_chain(28)
    ck("C12 链上每条都带 args 与 label", all(x["args"][0] == "-c:v" and x["label"] for x in c))
    ck("C13 quality 传到了每条 args", all(str(28) in x["args"] for x in c))
ck("C14 x265 倍数是实测来的", S.X265_TIMEOUT_MULT >= 2.0 and S.X265_TIMEOUT_MULT <= 5.0,
   str(S.X265_TIMEOUT_MULT))

# ---------- D. 换编码器只换那一段 ----------
mp4 = list(S.TRANSCODE_PRESETS["mp4"]["args"])
sw = S._swap_encoder(mp4, S._encoder_args("hevc_nvenc", 23, "medium"))
ck("D1 mp4 只换 -c:v 那一段",
   sw[:8] == ["-c:v", "hevc_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23"]
   and sw[sw.index("-c:a"):] == ["-c:a", "aac", "-b:a", "192k"], str(sw))
ck("D2 换完不再有 libx264", "libx264" not in sw)
p1080 = list(S.TRANSCODE_PRESETS["mp4_1080"]["args"])
sw2 = S._swap_encoder(p1080, S._encoder_args("libx265", 23, "medium"))
ck("D3 -vf scale 一个字都不动", sw2[sw2.index("-vf") + 1] == "scale=-2:1080", str(sw2))
ck("D4 1080 预设换成 x265 后带 hvc1", sw2[sw2.index("-tag:v") + 1] == "hvc1")
ck("D5 没有 -c:v 的预设原样返回",
   S._swap_encoder(["-c", "copy", "-bsf:a", "aac_adtstoasc"], ["-c:v", "libx265"]) ==
   ["-c", "copy", "-bsf:a", "aac_adtstoasc"])
ck("D6 needs_encoder 认预设",
   S._preset_needs_encoder(mp4) and S._preset_needs_encoder(p1080)
   and not S._preset_needs_encoder(list(S.TRANSCODE_PRESETS["flv_to_mp4"]["args"]))
   and not S._preset_needs_encoder(list(S.TRANSCODE_PRESETS["mkv_copy"]["args"]))
   and not S._preset_needs_encoder(list(S.TRANSCODE_PRESETS["audio_mp3"]["args"])))
ck("D7 只有重编视频的预设参与", sum(1 for v in S.TRANSCODE_PRESETS.values()
                                    if S._preset_needs_encoder(list(v["args"]))) == 2)
ck("D8 换不动时也不吃掉音频参数", "-b:a" in sw and sw[sw.index("-b:a") + 1] == "192k")

# ---------- E. 报错翻译 ----------
e1 = S._encoder_fail_reason("Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0")
ck("E1 NVENC 驱动版本翻成中文", "驱动" in e1 and "13.1" in e1 and "13.0" in e1, e1)
e2 = S._encoder_fail_reason("minimum required Nvidia driver for nvenc is 610.00")
ck("E2 缺驱动版本号保留", "610.00" in e2, e2)
e3 = S._encoder_fail_reason("Cannot load nv-codec-headers / libcuda.so")
ck("E3 加载不到 NVIDIA 库", "NVIDIA" in e3, e3)
e4 = S._encoder_fail_reason("Unknown encoder 'hevc_nvenc'")
ck("E4 构建里没有该编码器", "FFmpeg 构建" in e4, e4)
e5 = S._encoder_fail_reason("")
ck("E5 空文本也回一句人话", isinstance(e5, str) and e5 and "（ffmpeg 没给出原因）" in e5, e5)
e6 = S._encoder_fail_reason("Some weird failure: not supported by hardware\nsecond line")
ck("E6 认不出的报错也不留空且截断", bool(e6) and len(e6) <= 180, e6)

# ---------- F. 探测：黑场真跑 + 硬超时 ----------
class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


with fake_sub(run=lambda *a, **k: _R(0)):
    ck("F1 探测成功返回 True", S._probe_encoder("X:\\f.exe", "hevc_nvenc") == (True, ""))
with fake_sub(run=lambda *a, **k: _R(1, "", "Driver does not support the required nvenc API version. Required: 13.1 Found: 13.0")):
    ok, why = S._probe_encoder("X:\\f.exe", "hevc_nvenc")
    ck("F2 探测失败带中文原因", ok is False and "显卡驱动" in why, why)


def _hang(*a, **k):
    raise _sp.TimeoutExpired(cmd="ffmpeg", timeout=k.get("timeout", 8))


with fake_sub(run=_hang):
    ok, why = S._probe_encoder("X:\\f.exe", "hevc_amf", timeout_s=8.0)
    ck("F3 挂住的编码器按不可用处理", ok is False and "挂住" in why, why)
    ck("F4 超时原因里写了等了多久", "8 秒" in why, why)
ck("F5 探测默认就带硬超时", __import__("inspect").signature(S._probe_encoder).parameters["timeout_s"].default == 8.0)
seen = {}


def _cap(cmd, *a, **k):
    seen["cmd"] = list(cmd)
    return _R(0)


with fake_sub(run=_cap):
    S._probe_encoder("X:\\ffmpeg.exe", "libx265", timeout_s=3)
ck("F6 探测喂的是 lavfi 黑场、输出 null",
   "lavfi" in seen["cmd"] and any(str(x).startswith("color=c=black") for x in seen["cmd"])
   and seen["cmd"][-3:] == ["-f", "null", "-"] and "-y" not in seen["cmd"], str(seen["cmd"]))
with fake_sub(run=lambda cmd, *a, **k: _R(0, "\n".join([
    "  V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (encoders)",
    "  V..... libx265              libx265/HEVC (encoders)",
    "  V..... hevc_nvenc           NVIDIA NVENC H.264 (encoders)",
    "  A..... aac                  AAC (encoders)",
    "  V..X.. h264_qsv            Intel QSV (encoders)",
]))):
    b = S._encoders_built("X:\\f.exe")
ck("F8 -encoders 只收视频且认得 V.....", {"libx264", "libx265", "hevc_nvenc"} <= b and "aac" not in b, str(sorted(b)))
with fake_sub(run=lambda *a, **k: (_ for _ in ()).throw(_sp.TimeoutExpired("ffmpeg", 15))):
    ck("F9 列不出来就当没有", S._encoders_built("X:\\f.exe") == set())


def _boom(*a, **k):
    raise OSError("拒绝访问")


with fake_sub(run=_boom):
    ck("F10 探测进程起不来也算不可用", S._probe_encoder("X:\\nope.exe", "libx264")[0] is False)

# ---------- G. 探测缓存与状态读数 ----------
calls = {"built": 0, "probe": 0}
orig_built, orig_probe, orig_find, orig_ver = S._encoders_built, S._probe_encoder, S.ffmpeg_mgr.find, S.ffmpeg_mgr.version


def _built(ff):
    calls["built"] += 1
    return {"libx264", "libx265", "hevc_nvenc", "hevc_qsv", "hevc_amf"}


def _probe(ff, name, timeout_s=8.0):
    calls["probe"] += 1
    return (True, "") if name.startswith("libx") else (False, "驱动不行")


try:
    S._encoders_built, S._probe_encoder = _built, _probe
    S.ffmpeg_mgr.find = lambda *a, **k: "X:\\fake\\ffmpeg.exe"
    S.ffmpeg_mgr.version = lambda: "n9.0.1"
    with probe_cache({}, 0.0):
        st = S._encoder_probe_status(True)
        ck("G1 首次探测：-encoders 只列一次、五个编码器各试一次", calls["probe"] == 5 and calls["built"] == 1, str(calls))
        ck("G2 读数带 ok / items / 路径 / 版本", st["ok"] and len(st["items"]) == 5
           and st["ffmpeg_path"] == "X:\\fake\\ffmpeg.exe" and st["ffmpeg_version"] == "n9.0.1")
        ck("G3 起不来的带原因", any((not i["available"]) and i["reason"] == "驱动不行" for i in st["items"]))
        ck("G4 items 的字段口径齐", all(set(i) == {"encoder", "label", "available", "reason", "built"}
                                       for i in st["items"]))
        ck("G5 每个 item 都有中文名", all(i["label"] == S.ENCODER_LABELS.get(i["encoder"], i["encoder"])
                                        for i in st["items"]))
        n0 = calls["probe"]
        st2 = S._encoder_probe_status(False)
        ck("G6 未过期就用缓存，不再起进程", calls["probe"] == n0 and len(st2["items"]) == 5)
        S._encoder_probe_status(True)
        ck("G7 refresh=1 会重探", calls["probe"] == n0 + 5)
    with probe_cache({}, 0.0):
        S._encoders_built = lambda ff: set()
        calls["probe"] = 0
        st3 = S._encoder_probe_status(True)
        ck("G8 列不出编码器时不因此跳过，照样逐个试", calls["probe"] == 5
           and any(i["available"] for i in st3["items"]))
        ck("G9 列不出来时 built 报「不知道」而不是谎称有", all(i["built"] is None for i in st3["items"]),
           str([i["built"] for i in st3["items"]]))
    S._encoders_built = _built
    S.ffmpeg_mgr.find = lambda *a, **k: ""
    st4 = S._encoder_probe_status(True)
    ck("G10 没找到 FFmpeg 说清并回空 items", st4["ok"] is False and "未找到 FFmpeg" in st4["message"] and st4["items"] == [])
    ck("G11 TTL 是十分钟", S._ENCODER_PROBE_TTL == 600.0)
    S.ffmpeg_mgr.find = lambda *a, **k: "X:\\fake\\ffmpeg.exe"
    with pref("cpu", "x265", "fast"), probe_cache({}, time.time()):
        pl = S._video_encoders_payload(False)
        ck("G12 payload 带偏好 / 三张表 / 链",
           pl["preference"] == {"mode": "cpu", "codec": "x265", "preset": "fast"}
           and pl["modes"] == list(S.VIDEO_ENCODER_MODES) and pl["cpu_codecs"] == list(S.VIDEO_CPU_CODECS)
           and pl["presets"] == list(S.VIDEO_CPU_PRESETS) and encs(pl["chain"]) == ["libx265", "libx264"], str(pl["chain"]))
        ck("G13 chain 只露 encoder / label / timeout_mult，不外泄 args",
           all(set(x) == {"encoder", "label", "timeout_mult"} for x in pl["chain"]))
finally:
    S._encoders_built, S._probe_encoder = orig_built, orig_probe
    S.ffmpeg_mgr.find, S.ffmpeg_mgr.version = orig_find, orig_ver

# ---------- H. 接线（静态核对源码，接口漏一个键就红） ----------
srv = (ROOT / "server.py").read_text(encoding="utf-8")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
# 卡片标题与按钮文字搬进词表之后，光在 index.html 里搜「视频编码」就只会搜到空气。
# 这里把 zh 那份词表读出来：断言改成两半 —— 界面接的是哪个键 + 这个词表键的中文还是不是那句原话。
import re as _re  # noqa: E402
_i18n = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
_zh = _i18n[_i18n.find("    zh: {"):_i18n.find("\n    en: {")]
ZH = dict(_re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh))
dm = srv[srv.index("DEFAULTS"):]
ck("H1 三项默认值进 DEFAULTS 且等于改动前的行为",
   '"video_encoder": "cpu"' in dm and '"video_cpu_codec": "x264"' in dm and '"video_cpu_preset": "medium"' in dm)
cb = srv[srv.index("class ConfigBody"):]
cb = cb[:cb.index("def api_set_config") if "def api_set_config" in cb else 4000]
ck("H2 ConfigBody 声明了这三行（不声明 model_dump 会静默丢）",
   "video_encoder: Optional[str]" in cb and "video_cpu_codec: Optional[str]" in cb
   and "video_cpu_preset: Optional[str]" in cb, cb[:200])
blk = srv[srv.index('for k, allowed, label in (("video_encoder"'):]
ck("H3 保存当场校验枚举", 'VIDEO_ENCODER_MODES' in blk[:600] and 'VIDEO_CPU_CODECS' in blk[:600]
   and 'VIDEO_CPU_PRESETS' in blk[:600], blk[:400])
ck("H4 校验不过顶回 400，不静默收下", 'HTTPException(400' in blk[:900], blk[:400])
ck("H5 读数接口注册在 app 之后", srv.count('@app.get("/api/video/encoders")') == 1
   and srv.index('@app.get("/api/video/encoders")') > srv.index('app = FastAPI'))
ck("H6 烧字幕走链，一个不行换下一个", "chain = _video_encode_chain(crf)" in srv
   and "for idx, enc in enumerate(chain)" in srv and "烧字幕用 {enc['label']} 没成" in srv)
ck("H7 换编码器前删半成品", srv.count("out.unlink(missing_ok=True)") >= 3)
ck("H8 完成日志点名用了哪个编码器", "用 {used['label']}" in srv and "{used['label']}" in srv)
ck("H9 转码走链并带超时倍数", "chain = _video_encode_chain(23)" in srv
   and "_attempt(_swap_encoder(base, enc[\"args\"]), enc[\"timeout_mult\"])" in srv)
ck("H10 转码超时被掐断要说出来", "秒被掐断" in srv)
ck("H11 copy 预设不受影响", "if _preset_needs_encoder(base):" in srv)
ck("H12 flv_to_mp4 的 copy→重编兜底还在", 'preset_id == "flv_to_mp4"' in srv and "_with_encoder(enc)" in srv)
ck("H13 VAAPI 明确不做并写了原因", "VAAPI" in srv and "ass=" in srv[srv.index("VAAPI") - 400:srv.index("VAAPI") + 400])
ck("H14 界面有那张卡片",
   """<div class="section-title">{{ tr('settings.videoCodecTitle') }}</div>""" in html
   and """{{ tr('settings.probeEncBtn') }}""" in html
   and ZH.get("settings.videoCodecTitle") == "视频编码（转码与烧字幕）"
   and ZH.get("settings.probeEncBtn") == "探测编码器",
   f"标题={ZH.get('settings.videoCodecTitle')} 按钮={ZH.get('settings.probeEncBtn')}")
ck("H15 三个下拉各绑各的设置项",
   'v-model="settings.video_encoder"' in html and 'v-model="settings.video_cpu_codec"' in html
   and 'v-model="settings.video_cpu_preset"' in html)
ck("H16 五项模式在界面上都有得选", all(f'value="{m}"' in html for m in S.VIDEO_ENCODER_MODES))
ck("H17 读 config 时按白名单收", "settings.value.video_encoder = ['auto', 'cpu', 'nvidia', 'intel', 'amd']" in html)
ck("H18 settings 初值与后端默认一致",
   "video_encoder: 'cpu'" in html and "video_cpu_codec: 'x264'" in html and "video_cpu_preset: 'medium'" in html)
ck("H19 卡片列了每个编码器可用与否", 'v-for="it in encoders.items"' in html and "it.available" in html)
ck("H20 降级链在界面上看得见", 'v-for="(c, i) in encoders.chain"' in html)
ck("H21 探测走 GET 且不打运行日志",
   "api('/api/video/encoders' + (refresh ? '?refresh=1' : ''), { noLog: true })" in html)
ck("H22 存完设置重拉链", "loadEncoders();" in html)
ck("H23 进设置页才探测（不在首页白跑）", "watch(page, p => { if (p === 'settings'" in html)
ck("H24 新增的都 return 给模板了", "encoders, encProbeBusy, encProbeText, loadEncoders," in html)
ck("H25 界面文案不承诺没做的强制选项", "强制使用" not in srv and "强制使用" not in html)
ck("H26 探测/转码/烧字幕都按设置里的 FFmpeg 路径找", srv.count("ffmpeg_mgr.find(ffmpeg_mgr.manual_path)") >= 3)
ck("H27 降级那条日志压成一行（ffmpeg 的报错自带换行）", 'why1 = " ".join((err or "").split())' in srv)

# ---------- I. 收尾：内存改动全部还原 ----------
ck("I1 三项设置还原成跑测试前的值",
   all(S.cfg.data.get(k) == v for k, v in saved_cfg.items()),
   str({k: (S.cfg.data.get(k), v) for k, v in saved_cfg.items() if S.cfg.data.get(k) != v}))
ck("I2 探测缓存还原（没留下假 ffmpeg 路径）",
   S._encoder_probe_cache.get("ffmpeg", "") != "X:\\fake\\ffmpeg.exe"
   and not S._encoder_probe_cache.get("items"), str(S._encoder_probe_cache)[:160])
ck("I3 ffmpeg_mgr 的 find / version 还是原方法",
   getattr(S.ffmpeg_mgr.find, "__func__", None) is getattr(orig_find, "__func__", S.ffmpeg_mgr.find)
   and getattr(S.ffmpeg_mgr.version, "__func__", None) is getattr(orig_ver, "__func__", S.ffmpeg_mgr.version))
ck("I4 _encoders_built / _probe_encoder 已还原", S._encoders_built is orig_built and S._probe_encoder is orig_probe)
ck("I5 subprocess 出口没被留成假的", _sp.run is orig_sp_run and _sp.Popen is orig_sp_popen)

print(f"TOTAL: {TOTAL} FAILED: {len(FAILED)}")
if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
print("ALL PASS")
sys.exit(0)
