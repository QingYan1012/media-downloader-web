# -*- coding: utf-8 -*-
"""文件页「封入音轨」：把若干音频无损封进一条视频，做成多音轨 mkv。

口径（用户 2026-10-22 逐条点过）：候选先给这条视频旁边的音轨（分轨产物 + 同目录音频），要封别处的
按下载目录去翻；原视频自带的音轨保留、新轨排在后面；一律封成 mkv、另存 .mux.mkv，同名要确认；
wav 这类无损轨默认压一道（192k opus），界面上可关。

两条来自实测的坑，都有对应断言：
- 2026-10-22 本机 ffmpeg 8.1：`-disposition:a:0 default=0` 是无效参数，直接
  `Unable to parse "disposition" option value` 退出；清标记的写法是值写 `-default`。
  而且不写 disposition 时 mkv 每条轨的 default 都是 1（三条音轨全是默认轨），所以每条都得写。
- 同一天：mp4 里的 mov_text 字幕 copy 进 mkv 会被拒，所以带字幕那一版失败后要不带字幕重来一遍，
  并在日志里说清成品少了什么，不能只报「成了」。
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="md_mux_state_")
os.environ["MEDIADOWNLOADER_STATE_DIR"] = STATE
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server as S  # noqa: E402

TOTAL = []
FAILED = []
SRC = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
DL = Path(STATE) / "Downloads"


def ck(name, cond, detail=""):
    TOTAL.append(name)
    if not cond:
        FAILED.append(name + ("  [%s]" % detail if detail else ""))
    print(("PASS " if cond else "FAIL ") + name + ("  [%s]" % detail if detail and not cond else ""),
          flush=True)


def has(cmd, key, val):
    """命令里是否真有「这个选项 = 这个值」这一对（-metadata:s:a:1 一条轨会出现两次，
    所以只能按对查找，不能摊成字典 —— 摊成字典后一条语言标签会被同轨的轨名盖掉，
    上一版就是这么把 B2/B3 判成红的，代码没错。）"""
    return any(cmd[i] == key and cmd[i + 1] == val for i in range(len(cmd) - 1))


def opts_of(cmd, key):
    return [cmd[i + 1] for i in range(len(cmd) - 1) if cmd[i] == key]


def main():
    DL.mkdir(parents=True, exist_ok=True)
    S.cfg.data["download_dir"] = str(DL)

    # ---------------- A 语言与默认编码 ----------------
    ck("A1 语言：常见两字母写法翻成 mkv 认的三字母",
       S.mux_lang_code("zh") == "chi" and S.mux_lang_code("EN") == "eng" and S.mux_lang_code("ja") == "jpn",
       f'{S.mux_lang_code("zh")}/{S.mux_lang_code("EN")}')
    ck("A2 语言：已经是三字母的原样收（别人手写过 fra 不该被改成 und）",
       S.mux_lang_code("fra") == "fra" and S.mux_lang_code("deu") == "deu")
    ck("A3 语言：认不出一律 und，不许猜成 eng（猜错一条比留未标注更难发现）",
       S.mux_lang_code("English") == "und" and S.mux_lang_code("") == "und" and S.mux_lang_code("zzz!") == "und",
       S.mux_lang_code("English"))
    ck("A4 默认编码：无损轨压 opus、已经压过的原样 copy，界面上选了就算",
       S.mux_track_codec(Path("a.wav"), "") == "opus"
       and S.mux_track_codec(Path("a.flac"), "") == "copy"
       and S.mux_track_codec(Path("a.wav"), "copy") == "copy"
       and S.mux_track_codec(Path("a.mp3"), "aac") == "aac")
    # 界面那格给的是 'auto' 而不是空串：Element Plus 把空串当「没选」，会显示成「请选择」
    ck("A5 界面送 'auto' 与送空串是同一个意思（少这一条，那一格会一直写着「请选择」）",
       S.mux_track_codec(Path("a.wav"), "auto") == "opus"
       and S.mux_track_codec(Path("a.mp3"), "auto") == "copy")

    # ---------------- B 命令构造 ----------------
    tr = [{"path": DL / "v.wav", "codec": "opus", "language": "chi", "title": "人声"},
          {"path": DL / "b.mp3", "codec": "copy", "language": "eng", "title": ""}]
    media, out = DL / "clip.mp4", DL / "clip.mux.mkv"
    c = S.build_mux_command("ff", media, out, tr, src_audio=1, keep_original=True, default_index=0)
    ck("B1 画面只 map 视频轨且全局 copy（重编就不是「无损封入」了）",
       has(c, "-map", "0:v:0") and has(c, "-c", "copy"))
    ck("B2 原片音轨保留时排在前面，新轨的下标从 src_audio 起",
       has(c, "-map", "0:a?") and has(c, "-map", "1:a:0") and has(c, "-map", "2:a:0")
       and has(c, "-metadata:s:a:1", "language=chi") and has(c, "-metadata:s:a:2", "language=eng")
       and not has(c, "-metadata:s:a:0", "language=chi"),
       " ".join(opts_of(c, "-metadata:s:a:1")))
    ck("B3 默认带源字幕那条（0:v + 0:a? + 0:s? + 两条新轨 = 五次 map）",
       len(opts_of(c, "-map")) == 5 and has(c, "-map", "0:s?"))
    ck("B4 wav 压 opus 带 192k，copy 那条不加编码项；轨名与语言同在这一条轨上",
       has(c, "-c:a:1", "libopus") and has(c, "-b:a:1", S.MUX_BITRATE)
       and "-c:a:2" not in c and opts_of(c, "-metadata:s:a:1") == ["language=chi", "title=人声"],
       str(opts_of(c, "-metadata:s:a:1")))
    ck("B5 默认轨只点名一条，其余写 -default（default=0 那种写法 ffmpeg 8 会当无效参数退出）",
       has(c, "-disposition:a:0", "-default") and has(c, "-disposition:a:1", "default")
       and has(c, "-disposition:a:2", "-default"),
       str(opts_of(c, "-disposition:a:0")))
    ck("B6 「默认给原片」与「默认给新轨」落的是不同下标，不是一句空话",
       has(S.build_mux_command("ff", media, out, tr, src_audio=1, keep_original=True,
                               default_index=-1), "-disposition:a:0", "default"))
    c2 = S.build_mux_command("ff", media, out, tr, src_audio=1, keep_original=False, default_index=1)
    ck("B7 不保留原音轨时整条 0:a? 不出现，新轨下标从 0 起",
       "0:a?" not in c2 and has(c2, "-c:a:0", "libopus")
       and has(c2, "-metadata:s:a:0", "language=chi") and has(c2, "-disposition:a:1", "default"),
       " ".join(opts_of(c2, "-c:a:0")))
    ck("B8 default_index 超出条数时被夹到最后一条（界面上删过轨就会留下越界的下标）",
       has(S.build_mux_command("ff", media, out, tr, src_audio=0, keep_original=False,
                               default_index=99), "-disposition:a:1", "default"))
    ck("B9 源里一条音轨都没有时不该 map 0:a?，也没必要留原轨",
       "0:a?" not in S.build_mux_command("ff", media, out, tr, src_audio=0, keep_original=True,
                                         default_index=-1))
    cw = S.build_mux_command("ff", media, out, tr, src_audio=1, keep_original=True,
                             default_index=0, with_subs=True)
    cn = S.build_mux_command("ff", media, out, tr, src_audio=1, keep_original=True,
                             default_index=0, with_subs=False)
    ck("B10 丢掉字幕那一版只少 -map 0:s?，其余参数一字不变（回退不能顺手改别的行为）",
       cw.count("0:s?") == 1 and cn.count("0:s?") == 0 and len(cw) - len(cn) == 2
       and [x for x in cw if x.startswith("-metadata")] == [x for x in cn if x.startswith("-metadata")],
       f"{len(cw)}/{len(cn)}")
    ck("B11 成品路径是最后一个参数，且 mkv 是硬口径（mp4 装不下 wav 的 PCM 与 opus）",
       c[-1] == str(out) and str(out).endswith(".mux.mkv"), c[-1])

    # ---------------- C 就近候选 ----------------
    stem_dir = DL / "demucs" / "htdemucs" / "clip"
    stem_dir.mkdir(parents=True, exist_ok=True)
    (stem_dir / "vocals.wav").write_bytes(b"RIFF")
    (stem_dir / "no_vocals.wav").write_bytes(b"RIFF")
    (stem_dir / "clip-mix-101112.wav").write_bytes(b"RIFF")      # 混音台自己产的，不该再当候选
    (DL / "clip.mp4").write_bytes(b"x")
    (DL / "take2.m4a").write_bytes(b"FIX")
    (DL / "clip.srt").write_text("1\n", encoding="utf-8")
    (DL / "clip.mux.mkv").write_bytes(b"x")                       # 上一次的成品，不该当音轨
    rows = S._mux_candidate_rows(DL / "clip.mp4")
    got = {r["name"]: r["origin"] for r in rows}
    ck("C1 分轨产物按「曲名那一层」精确取，标成 stem",
       got.get("vocals") == "stem" and got.get("no_vocals") == "stem", str(got))
    ck("C2 同目录的音频文件算候选，字幕与源自己不算",
       got.get("take2") == "side" and "clip" not in got and "clip.srt" not in got, str(got))
    ck("C3 混音成品（-mix-）与上一次封入的 .mux.mkv 都不列（不然封来封去会把自己套进去）",
       all("-mix-" not in r["name"] and not r["path"].endswith(S.MUX_OUT_SUFFIX) for r in rows), str(got))
    ck("C4 候选给的是相对下载目录的路径（界面回传后端再还原成绝对）",
       all(not str(r["path"]).startswith(str(DL)) for r in rows), str(rows[:1]))
    r2 = S.api_files_audio_candidates(path=str(DL / "clip.mp4"))
    ck("C5 候选接口把起始目录一起回给界面，省得人自己抄路径",
       r2["ok"] and r2["dir"] == "" and len(r2["tracks"]) == len(rows),
       str(r2)[:120])
    # 上面那份 .mux.mkv 只是「上一次成品不该当候选」的夹具，留着会让 D1 撞上同名 409
    (DL / "clip.mux.mkv").unlink(missing_ok=True)

    # ---------------- D 接口那道校验 ----------------
    calls, orig = [], (S.ffmpeg_mgr.find, S._ffprobe_info, S._ffprobe_audio_count, subprocess.run)
    S.ffmpeg_mgr.find = lambda *a, **k: "ff"
    S._ffprobe_info = lambda p: {"width": 1280, "duration": 3.0, "acodec": "aac"}

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kw):
        calls.append(cmd)
        Path(cmd[-1]).write_bytes(b"made")
        return R()

    def counting(n_media, n_track=1):
        def f(p):
            return n_media if Path(p) == DL / "clip.mp4" else n_track
        return f

    S._ffprobe_audio_count = counting(1)
    subprocess.run = S.subprocess.run = fake_run

    def body(**kw):
        base = {"path": "clip.mp4", "tracks": [{"path": "demucs/htdemucs/clip/vocals.wav"}],
                "keep_original": True, "default_index": 0, "overwrite": False}
        base.update(kw)
        return S.MuxAudioIn(**base)

    rr = S.api_files_mux_audio(body())
    ck("D1 走通一次：成品写在同目录、回的是相对路径、条数算得对",
       rr["ok"] and rr["path"] == "clip.mux.mkv" and rr["tracks"] == 2 and rr["added"] == 1,
       str(rr)[:160])
    ck("D2 成品文件真的落出来了（写路径却产出空文件那种，接口该报错而不是报成功）",
       (DL / "clip.mux.mkv").exists())
    ck("D3 跑完锁被放开（异常路径漏放锁的话，第二次点会一直 409 卡死）",
       str(DL / "clip.mp4") not in S.MUX_BUSY, str(S.MUX_BUSY))
    (DL / "clip.mux.mkv").unlink()

    def expect(status, fn, name, note=""):
        try:
            fn()
            ck(name, False, "没抛异常")
        except S.HTTPException as e:
            ck(name, e.status_code == status, f"{e.status_code} {e.detail}")
        except Exception as e:  # noqa: BLE001
            ck(name, False, f"{type(e).__name__}: {e} {note}")

    expect(409, lambda: (Path(DL / "clip.mux.mkv").write_bytes(b"x"),
                         S.api_files_mux_audio(body())),
           "D4 同名成品已存在时先要一句确认（409），不许闷头覆盖")
    Path(DL / "clip.mux.mkv").unlink()
    rr2 = S.api_files_mux_audio(body(overwrite=True))
    ck("D5 勾了「覆盖旧成品」才走覆盖这条路", rr2["ok"] and len(calls) == 2, f"{len(calls)} 次")
    Path(DL / "clip.mux.mkv").unlink()

    expect(400, lambda: S.api_files_mux_audio(body(tracks=[])), "D6 一条轨都不选就 400")
    expect(400, lambda: S.api_files_mux_audio(body(tracks=[{"path": "clip.srt"}])),
           "D7 非音频文件当轨拒收")
    expect(400, lambda: S.api_files_mux_audio(body(tracks=[{"path": "clip.mp4"}])),
           "D8 不许把这条视频自己封进这条视频")
    expect(400, lambda: S.api_files_mux_audio(
        body(tracks=[{"path": "demucs/htdemucs/clip/vocals.wav"}] * (S.MUX_TRACK_MAX + 1))),
        "D9 超出条数上限拒收（mkv 装得下，但那已经不是给人用的界面了）")
    S._ffprobe_audio_count = counting(-1)
    expect(400, lambda: S.api_files_mux_audio(body()),
           "D10 数不出原片有几条音轨时报「没法判」，不能当 0 把标签贴到错的轨上")
    S._ffprobe_audio_count = counting(1, 0)
    expect(400, lambda: S.api_files_mux_audio(body()),
           "D11 候选文件自己没音轨时当场拒，别让 ffmpeg 报一句「map 没匹配到流」")
    S._ffprobe_audio_count = counting(1)

    # 字幕那条的回退：第一次非 0 且报错指着字幕 → 不带字幕再来一遍，并记一句成品少了什么
    logs = []
    orig_log = S.log_mgr.log

    def spy(msg, level="info", **kw):
        logs.append(msg)
        return 0

    S.log_mgr.log = spy
    calls.clear()

    seq = {"n": 0}

    def failing_subs(cmd, **kw):
        seq["n"] += 1
        calls.append(cmd)
        if seq["n"] == 1:
            r = R()
            r.returncode = 1
            r.stderr = "Codec mov_text not implemented for the Matroska format."
            return r
        Path(cmd[-1]).write_bytes(b"made")
        return R()

    subprocess.run = S.subprocess.run = failing_subs
    rr3 = S.api_files_mux_audio(body())
    ck("D12 mov_text 字幕被拒时丢掉字幕重来一遍，且第二遍不带 -map 0:s?",
       rr3["ok"] and rr3["dropped_subs"] and "0:s?" in calls[0] and "0:s?" not in calls[1],
       f"{len(calls)} 次")
    ck("D13 这句回退要记进运行日志（界面上只说「成了」会把丢了字幕藏起来）",
       any("字幕没能一起封装" in m for m in logs), str(logs[-2:])[:200])
    Path(DL / "clip.mux.mkv").unlink(missing_ok=True)

    seq["n"] = 0

    def always_fail(cmd, **kw):
        calls.append(cmd)
        r = R()
        r.returncode = 1
        r.stderr = "Invalid argument"
        return r

    subprocess.run = S.subprocess.run = always_fail
    expect(500, lambda: S.api_files_mux_audio(body()), "D14 两次都不成要报 500，别把失败说成成功")
    ck("D15 失败时半成品要清掉（留下半个 mkv 比没有更坏）",
       not (DL / "clip.mux.mkv").exists() and str(DL / "clip.mp4") not in S.MUX_BUSY,
       f'{(DL / "clip.mux.mkv").exists()} {str(S.MUX_BUSY)}')

    S.ffmpeg_mgr.find, S._ffprobe_info, S._ffprobe_audio_count, subprocess.run = orig
    S.subprocess.run = orig[3]
    S.log_mgr.log = orig_log

    # ---------------- E 界面接线 ----------------
    seg = HTML[HTML.index("function openMuxDlg"):]
    ck("E1 下拉项与 FILE_ACTIONS 都挂上了（只加菜单不挂函数，点了就是没反应）",
       "'openMuxDlg|' + $index" in HTML and "openMuxDlg," in HTML[HTML.index("const FILE_ACTIONS = {"):][:400])
    ck("E2 语言选项是九个写死的 tr()，不是 v-for 拼键（拼出来的键名 B10 会当死键，界面也会印键名）",
       HTML.count("tr('files.muxLang") == 9, str(HTML.count("tr('files.muxLang")))
    ck("E3 提交带的字段与后端口径一致：keep_original / default_index / overwrite",
       all(x in seg[:3500] for x in ["keep_original: muxDlg.keep", "default_index: defIdx",
                                     "overwrite: muxDlg.overwrite"]), seg[2000:2200])
    ck("E4 默认轨在界面上是 'orig' 或 tN，换算就一行（-1 交给后端夹，前端不再算下标）",
       "muxDlg.defSel === 'orig' ? -1" in seg, "")
    ck("E5 字幕被丢掉那句会拼进完成提示，而不是只弹「成了」",
       "if (r.dropped_subs)" in seg)
    ck("E6 埋点表里给这个写接口登了名（没登的按钮点了不进运行日志）",
       "'/api/files/mux_audio': 'act.files.mux_audio'," in HTML)

    # ---------------- F 词表与文档 ----------------
    for k in ["srv.files.mux_start", "srv.files.mux_done", "srv.files.mux_subs_dropped", "srv.files.mux_failed"]:
        ck(f"F {k} 两份词表各一条", I18N.count("'%s'" % k) == 2, str(I18N.count("'%s'" % k)))

    print(f"\n== 汇总 ==\n共 {len(TOTAL)} 条，失败 {len(FAILED)} 条")
    for f in FAILED:
        print("FAIL " + f)
    shutil.rmtree(STATE, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
