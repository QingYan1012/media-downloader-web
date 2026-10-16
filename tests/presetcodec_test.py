#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析面板那三排选项（画质 / 画面编码 / 音质）离线自检。

为什么要有这个文件：这一轮把 4K 的事查到底之后，`/api/analyze` 改成按「高度 × 编码族」出档位，
两个缺陷只有真联网才看得见，而联网这一次要等 YouTube 风控、跑一分钟还不稳定：

1. 每个高度都被多贴了一条「族名为空」的重复档位 —— 界面上是并排两个「1080p」，点哪个都是同一条流，
   用户以为自己在选码率。根因是 `ordered += [...] or [""]`：列表推导为空时 `or` 才补 `[""]`，
   而这恰好是「只有一个已知编码族」那种最常见的情况。
2. 音质档位从渐进流的 tbr 里取 —— 渐进流的 tbr 是影音合计，界面于是显示「3879 kbps」这种数，
   而且选了也不改变任何东西。只有独立音轨的码率才算音质。

两件事都改成可以离线钉住的纯函数（`_quality_presets` / `_audio_abrs`），输入就是解析用的
那份归一化格式清单，不再靠联网复现。

跑法：PYTHONIOENCODING=utf-8 python tests/presetcodec_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

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


SRC = Path(S.__file__).read_text(encoding="utf-8")


def mk(fid, height, vcodec, acodec, tbr, filesize=0, protocol="https"):
    """归一化后的格式条目：字段与 api_analyze 里拼的那份 dict 一致。"""
    is_video = vcodec != "none"
    return {
        "format_id": str(fid),
        "ext": "mp4" if "avc" in vcodec or "mp4a" in acodec else "webm",
        "resolution": f"{height}p" if height else "audio",
        "height": height,
        "width": 0,
        "fps": 30,
        "vcodec": vcodec,
        "acodec": acodec,
        "tbr": tbr,
        "filesize": filesize,
        "filesize_est": 0 if filesize else int(tbr * 125 * 100) if tbr else 0,
        "note": "",
        "protocol": protocol,
        "is_video": is_video,
        "is_audio": acodec != "none" and not is_video,
        "has_audio": acodec != "none",
    }


# 本机实测：YouTube 风控时只回 91–96 这组 HLS 渐进流 + itag 18，没有一条独立音轨
GATED = [
    mk(96, 1080, "avc1.640028", "mp4a.40.2", 3879.2, protocol="m3u8_native"),
    mk(95, 720, "avc1.4D401F", "mp4a.40.2", 1305.5, protocol="m3u8_native"),
    mk(18, 360, "avc1.42001E", "mp4a.40.2", 662.3, filesize=25198544),
    mk(91, 144, "avc1.4D400C", "mp4a.40.5", 154.6, protocol="m3u8_native"),
]

# 正常放行：DASH 分流，4K 同时有 AV1 与 VP9，1080p 同时有 AVC 与 VP9
DASH = [
    mk(337, 2160, "av01.0.19M.08", "none", 11000, filesize=900000000, protocol="https"),
    mk(313, 2160, "vp09.00.51.08", "none", 12000, filesize=1200000000, protocol="https"),
    mk(271, 1440, "vp09.00.50.08", "none", 5000, protocol="https"),
    mk(137, 1080, "avc1.640028", "none", 3000, protocol="https"),
    mk(247, 720, "vp09.00.40.08", "none", 1500, protocol="https"),
    mk(140, 0, "none", "mp4a.40.2", 129.4, protocol="https"),
    mk(251, 0, "none", "opus", 160.0, protocol="https"),
    mk(171, 0, "none", "vorbi", 139.0, protocol="https"),
]

# ---------- A 高度 × 编码族：一个组合只能有一条 ----------
ps = S._quality_presets(GATED)
by_h = {}
for p in ps:
    by_h.setdefault(p["height"], []).append(p)
ck("A1 每个高度只留一条（不再有并排两个 1080p）",
   all(len(v) == 1 for v in by_h.values()), {k: [x["label"] for x in v] for k, v in by_h.items()})
ck("A2 单一编码族时标签不挂族名，界面就是 1080p", [p["label"] for p in ps if p["height"] == 1080] == ["1080p"])
ck("A3 档位仍带得出编码族（下载时按它挑码流）",
   by_h[1080][0]["codec_family"] == "AVC" and by_h[1080][0]["prefer_codec"] == "avc")
ck("A4 渐进流的表达式就是它自己的 format_id，不再拼 +bestaudio",
   by_h[1080][0]["format_expr"] == "96", by_h[1080][0]["format_expr"])
ck("A5 顺序：最佳画质在最前，之后按高度从高到低，仅音频在最后",
   ps[0]["label"] == "最佳画质" and ps[-1]["label"] == "仅音频"
   and [p["height"] for p in ps[1:-1]] == sorted([p["height"] for p in ps[1:-1]], reverse=True),
   [p["label"] for p in ps])
ck("A6 每档都能落到具体流上（format_id 不为空）", all(p["format_id"] for p in ps if p["height"] > 0))
ck("A7 没有独立音轨时音质档位是空的，不是渐进流的影音合计码率", S._audio_abrs(GATED) == [], S._audio_abrs(GATED))

# ---------- B 同高度多编码族：这才该拆开 ----------
ps2 = S._quality_presets(DASH)
lab2 = {h: [p["label"] for p in ps2 if p["height"] == h] for h in (2160, 1440, 1080, 720)}
ck("B1 4K 有 AV1 与 VP9 时给两条，标签写清族名",
   sorted(lab2[2160]) == sorted(["2160p · AV1", "2160p · VP9"]), lab2[2160])
ck("B2 同一高度 AVC 排在前面（兼容性最好）",
   [p["codec_family"] for p in ps2 if p["height"] == 1080] == ["AVC"],
   [p["codec_family"] for p in ps2 if p["height"] == 1080])
ck("B3 只有单一族的高度不挂族名", [p["label"] for p in ps2 if p["height"] == 720] == ["720p"])
ck("B4 分流视频轨的表达式带上 bestaudio 兜底",
   all("+bestaudio" in p["format_expr"] for p in ps2 if p["height"] in (2160, 1080)),
   [p["format_expr"] for p in ps2 if p["height"] in (2160, 1080)])
ck("B5 纯音频流不会变成画质档位（清单里的 0p 只有「最佳画质」那一条）",
   [p["label"] for p in ps2 if p["height"] == 0] == ["最佳画质"],
   [p["label"] for p in ps2 if p["height"] == 0])
abrs = S._audio_abrs(DASH)
ck("B6 音质档位取独立音轨码率，降序", abrs == [160.0, 139.0, 129.4], abrs)
ck("B7 档位是 kbps 量级的数字，不是每秒字节数", all(10 < a < 1000 for a in abrs), abrs)

# ---------- C 边界 ----------
ck("C1 空清单也给出「最佳画质 + 仅音频」两条兜底",
   [p["label"] for p in S._quality_presets([])] == ["最佳画质", "仅音频"])
odd = S._quality_presets([mk("v1", 480, "mp4v.2", "mp4a.40.2", 800)])
ck("C2 认不出的编码只留一条、不带族名（以前这里是两条重复）",
   [p["label"] for p in odd] == ["最佳画质", "480p", "仅音频"], [p["label"] for p in odd])
ck("C3 认不出的编码不假装能选码率：prefer_codec 退回 auto",
   odd[1]["prefer_codec"] == "auto" and odd[1]["codec_family"] == "", odd[1])
ck("C4 没有 format_id 的那条流直接跳过，不留空档位",
   all(p["format_id"] for p in S._quality_presets([{"format_id": "", "height": 720, "is_video": True,
                                                    "vcodec": "avc1", "has_audio": True, "tbr": 900}])))
ck("C5 编码族判定认得 AV1 的多种写法", S._codec_family("av01.0.19M.08")[0] == "AV1"
   and S._codec_family("vp09.00.51.08")[0] == "VP9" and S._codec_family("h264")[0] == "AVC")
ck("C6 HEVC/VP8 也有位置，不会掉进空白档",
   S._codec_family("hev1.1.6")[0] == "HEVC" and S._codec_family("vp8")[0] == "VP8")

# ---------- D 接线 ----------
seg = SRC[SRC.index("def _analyze_single_formats"):SRC.index('@app.get("/api/files")')]
ck("D1 解析接口改用这两个纯函数（界面读的就是它们的结果）",
   "quality_presets = _quality_presets(formats)" in seg and "audio_abrs = _audio_abrs(formats)" in seg)
ck("D2 响应仍带着画质档位、音质档位与风控说明",
   all(k in seg for k in ('"quality_presets"', '"audio_abrs"', '"format_gate"')))
ck("D3 解析入口把单视频那段拆成了可测函数，不是埋在路由里",
   "return _analyze_single_formats(info, body.url)" in SRC)
ck("D4 旧的影音合计码率兜底没有留着（就是它造出 3879 kbps）",
   'or [f for f in formats if f.get("has_audio")]' not in seg)

# ---------- E PO Token 这一步的下一步 ----------
# 界面上那句提示以前不管三七二十一都写「启用 PO Token 服务」，可开关明明已经拧开了 ——
# 用户对着一个打开的开关收到「去打开它」，等于没有下一步。开关、服务、插件是三件事。
URL = "http://127.0.0.1:4416"
off = S._po_gate_tip({"ok": False, "installed": False, "detail": "未启用"},
                     {"po_provider_enabled": False, "po_provider_url": URL})
ck("E1 开关没开：说的是「开关是关的」，不是「服务没响应」",
   "开关是关的" in off and "没人应答" not in off, off)
on_dead = S._po_gate_tip({"ok": False, "installed": True, "detail": "连不上该地址（服务没启动或端口不对）"},
                         {"po_provider_enabled": True, "po_provider_url": URL})
ck("E2 开关已开、服务不通：不再教人去开一个已经开了的开关",
   "开关是关的" not in on_dead and "已经打开" in on_dead, on_dead)
ck("E3 说清缺的是那个要自己跑起来的独立服务，并带上地址与原因",
   URL in on_dead and "bgutil" in on_dead and "连不上该地址" in on_dead)
ck("E4 插件已装时不再提插件（不然三条都缺，改一条看不到第二条）",
   "POT 插件也没装" not in on_dead)
no_plugin = S._po_gate_tip({"ok": False, "installed": False, "detail": "探测超时（服务没响应）"},
                           {"po_provider_enabled": True, "po_provider_url": URL})
ck("E5 插件没装时点名它，票是靠插件取的", "POT 插件也没装" in no_plugin, no_plugin)
ck("E6 地址是用户填的那个，不写死 4416",
   "127.0.0.1:5555" in S._po_gate_tip({"ok": False, "installed": True, "detail": "x"},
                                      {"po_provider_enabled": True, "po_provider_url": "http://127.0.0.1:5555"}))
ck("E7 配置整个缺字段也不炸（老 config 没有这两个键）",
   "开关是关的" in S._po_gate_tip({}, {}))
gate = SRC[SRC.index("def _format_gate_note"):SRC.index('@app.get("/api/files")')]
ck("E8 风控说明里的这一步改走 _po_gate_tip", "_po_gate_tip(po, cfg" in gate)
ck("E9 写死的「当前状态 未启用」没有留着", '当前状态 {po.get' not in SRC and "当前状态" not in gate)

print(f"\nTOTAL {TOTAL}  FAILED {len(FAILED)}"
      + ("" if not FAILED else "  ==> " + "; ".join(FAILED)))
sys.exit(1 if FAILED else 0)
