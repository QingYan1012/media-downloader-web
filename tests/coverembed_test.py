r"""内嵌封面开关真生效：勾了真进文件、不勾真不进，结论按回读而不是「我调用过写入函数」。

起因：界面上那个「内嵌封面」以前只管一趟静默的 ffmpeg 重封装，auto_tag_audio 却无条件把封面
写进标签（不勾也照样嵌上）；反过来勾了也不保证 —— 平台没给封面地址、容器装不了、走队列兜底时
那侧写死 True，全都没有结论。这一批把口径统一成一个开关：写不写进文件、写完回读、逐行给原因。

跑法：`python tests/coverembed_test.py`（不起 server；造素材要随包 ffmpeg）。
全部产物落在 %TEMP%\md_coverembed_test\<时刻>\，绝不碰真实下载目录 / config / 索引。
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

APP = pathlib.Path(__file__).resolve().parent.parent
FFMPEG = APP / "tools" / "ffmpeg.exe"
if not FFMPEG.is_file():
    FFMPEG = pathlib.Path(shutil.which("ffmpeg") or "ffmpeg")

ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_coverembed_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)
FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


def run(args):
    return subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"] + args,
                          capture_output=True, text=True, timeout=120,
                          encoding="utf-8", errors="replace")


def make_audio(dest: pathlib.Path) -> bool:
    """按容器造真音频；ffmpeg 造不出来的容器就跳过，不拿假文件凑断言"""
    codec = {".mp3": ["-c:a", "libmp3lame", "-b:a", "128k"],
             ".flac": ["-c:a", "flac"],
             ".m4a": ["-c:a", "aac", "-f", "ipod"],
             ".ogg": ["-c:a", "libvorbis"]}.get(dest.suffix)
    if codec is None:
        return False
    run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2"] + codec + [str(dest)])
    return dest.is_file()


# ── 素材：真图片 + 各容器空白件 ───────────────────────────────────────
PPM = SHARD / "c.ppm"
PPM.write_bytes(b"P6\n8 8\n255\n" + bytes(range(192)))
JPG, PNG, WEBP = SHARD / "cover.jpg", SHARD / "cover.png", SHARD / "cover.webp"
run(["-i", str(PPM), str(JPG)])
run(["-i", str(PPM), str(PNG)])
run(["-i", str(PPM), str(WEBP)])
ck("A1 素材：造出了 jpg 与 png（webp 有的话另说）",
   JPG.is_file() and PNG.is_file(), f"webp={WEBP.is_file()}")
JPG_BYTES = JPG.read_bytes() if JPG.is_file() else b""
BLANK: dict[str, pathlib.Path] = {}
for _ext in (".mp3", ".flac", ".m4a", ".ogg"):
    _p = SHARD / ("blank" + _ext)
    if make_audio(_p):
        BLANK[_ext] = _p
ck("A2 空白音频造出了 mp3 / flac / m4a", all(e in BLANK for e in (".mp3", ".flac", ".m4a")),
   str(sorted(BLANK)))


def fresh(ext: str, tag: str) -> pathlib.Path:
    """每轮从空白件复制：上一轮写进标签的封面不能污染下一轮"""
    d = SHARD / f"{tag}{ext}"
    shutil.copyfile(BLANK[ext], d)
    return d


def embedded(p: pathlib.Path) -> bytes:
    data, _mime = M.audio_embedded_cover(str(p))
    return data or b""


# ---------------------------------------------------------------- B. 开关真管写入
print("== B. 勾了才写进文件、不勾就不写：读文件自己的标签，不信返回值 ==")
for ext in (".mp3", ".flac", ".m4a"):
    if ext not in BLANK:
        continue
    label = ext.lstrip(".")
    on = fresh(ext, "on_" + label)
    ok = M.auto_tag_audio(str(on), title="晴天", artists="周杰伦", album="八度空间",
                          cover_path=str(JPG), embed_cover=True)
    ck(f"B1[{label}] 勾了：回读到的封面字节就是那张 jpg",
       ok and embedded(on) == JPG_BYTES, f"回读 {len(embedded(on))} 字节 / jpg {len(JPG_BYTES)} 字节")

    off = fresh(ext, "off_" + label)
    ok2 = M.auto_tag_audio(str(off), title="晴天", artists="周杰伦", album="八度空间",
                           cover_path=str(JPG), embed_cover=False)
    ck(f"B2[{label}] 不勾：回读为空（以前这里无条件嵌，那个勾等于没管）",
       ok2 and embedded(off) == b"", f"回读 {len(embedded(off))} 字节")
    # 不勾只关「进文件」这一步，文字标签照写 —— 否则这个勾会变成「别打标签」
    from mutagen import File as _MF
    _tags = getattr(_MF(str(off)), "tags", None) or {}
    flat = " ".join(str(v) for v in _tags.values())
    ck(f"B3[{label}] 不勾时文字标签照写（曲名还在）", "晴天" in flat, flat[:40])

# ---------------------------------------------------------------- C. 归因写清楚
print("== C. 没嵌上是哪一种原因：回读之后归因，不是「我调用过写入函数」 ==")
if ".mp3" in BLANK:
    p = fresh(".mp3", "v_ok")
    M.auto_tag_audio(str(p), cover_path=str(JPG), embed_cover=True)
    ck("C1 嵌成功了：want / has 都对、没有原因",
       M.cover_verdict(str(p), True, str(JPG)) == {"want": True, "has": True, "why": ""},
       str(M.cover_verdict(str(p), True, str(JPG))))

    ck("C2 该嵌上却没嵌上：归因 failed（格式支持、封面也在场）",
       M.cover_verdict(str(fresh(".mp3", "v_failed")), True, str(JPG)).get("why") == "failed")

    ck("C3 平台没给封面：归因 nocover（和写失败不是一回事）",
       M.cover_verdict(str(fresh(".mp3", "v_nocover")), True, "").get("why") == "nocover")

    ck("C4 没勾、文件本来也干净：既不算失败也不进账",
       M.cover_verdict(str(fresh(".mp3", "v_off")), False, "")
       == {"want": False, "has": False, "why": ""})

    seeded = fresh(".mp3", "v_seeded")
    M.auto_tag_audio(str(seeded), cover_path=str(JPG), embed_cover=True)
    ck("C5 勾了不嵌、文件里却还有图：归因 kept（那是移出去这一步没成，不是「本来就有所以不管」）",
       M.cover_verdict(str(seeded), False, "") == {"want": False, "has": True, "why": "kept"})

if ".ogg" in BLANK:
    ogg = SHARD / "unsupported.ogg"
    shutil.copyfile(BLANK[".ogg"], ogg)
    ck("C6 容器装不了封面：归因 fmt，而不是笼统一句「没成功」",
       M.cover_verdict(str(ogg), True, str(JPG)).get("why") == "fmt")

if WEBP.is_file() and ".m4a" in BLANK:
    wp = fresh(".m4a", "v_webp")
    M.auto_tag_audio(str(wp), cover_path=str(WEBP), embed_cover=True)
    ck("C7 webp 进 m4a：不硬贴个 jpeg 旗标冒充（回读为空、归因 fmt）",
       embedded(wp) == b"" and M.cover_verdict(str(wp), True, str(WEBP)).get("why") == "fmt",
       str(M.cover_verdict(str(wp), True, str(WEBP))))

ck("C8 原因文案四种齐全（日志与界面都得落到具体那一种）",
   set(M.COVER_WHY_TEXT) >= {"fmt", "nocover", "failed", "kept"}, str(sorted(M.COVER_WHY_TEXT)))
ck("C8b kept 那句说的是「没能移出去」，不再是「原样保留」",
   "移出" in M.COVER_WHY_TEXT["kept"] and "保留" not in M.COVER_WHY_TEXT["kept"],
   M.COVER_WHY_TEXT["kept"])

# ---------------------------------------------------------------- D. 不再重封装
print("== D. 封面只走 mutagen 写标签：ffmpeg 重封装那一趟删了，sidecar 照旧留 ==")
SRC_MS = pathlib.Path(APP / "music_search.py").read_text(encoding="utf-8")
src_slc = inspect.getsource(M.save_lyrics_and_cover)
ck("D1 save_lyrics_and_cover 里不再起 subprocess / ffmpeg / attached_pic",
   not any(w in src_slc for w in ("subprocess", "ffmpeg", "attached_pic")))
ck("D2 整个模块没有 attached_pic 的重封装口径残留", "attached_pic" not in SRC_MS)
ck("D3 写封面的通道只有 mutagen 标签（auto_tag_audio 的三条分支）",
   "id3.add(APIC" in SRC_MS and "add_picture(pic)" in SRC_MS and 'audio["covr"]' in SRC_MS)

if ".mp3" in BLANK and JPG.is_file():
    side = fresh(".mp3", "side")
    before = side.read_bytes()
    real_fetch = M.fetch_url_bytes
    M.fetch_url_bytes = lambda url, *a, **k: JPG_BYTES
    try:
        got = M.save_lyrics_and_cover(str(side), cover_url="http://x/cover.jpg")
    finally:
        M.fetch_url_bytes = real_fetch
    jpg_out = pathlib.Path(got.get("cover") or "")
    ck("D4 sidecar 落地：不勾内嵌时目录里也看得见这张封面",
       jpg_out.is_file() and jpg_out.read_bytes() == JPG_BYTES, str(got))
    ck("D5 落 sidecar 这一步不动音频文件本身（字节一模一样，没有重封装）",
       side.read_bytes() == before, f"{len(before)} 字节")

# ---------------------------------------------------------------- E. 批量结论汇总
print("== E. 批量任务的账：成功进 ok、嵌不上进 miss、没勾却还有图进 kept ==")
import server as S  # noqa: E402

lines: list[tuple[str, str]] = []


def log(msg, level="info"):
    lines.append((level, msg))


job: dict = {}
S.note_music_cover(job, {"want": True, "has": True, "why": ""}, "a.mp3", "晴天", log)
S.note_music_cover(job, {"want": True, "has": False, "why": "nocover"}, "b.mp3", "稻香", log)
S.note_music_cover(job, {"want": True, "has": False, "why": "fmt"}, "c.ogg", "七里香", log)
S.note_music_cover(job, {"want": False, "has": True, "why": "kept"}, "d.m4a", "半岛铁盒", log)
S.note_music_cover(job, {"want": False, "has": False, "why": ""}, "e.mp3", "安静", log)
cov = job.get("cover") or {}
ck("E1 计数分得开：ok=1 / kept=1 / miss=2（没勾且干净的哪本账都不进）",
   cov.get("ok") == 1 and cov.get("kept") == 1 and len(cov.get("miss") or []) == 2, str(cov))
ck("E2 miss 里带曲名与原因，界面展开才指得是哪几首",
   [x["title"] for x in cov["miss"]] == ["稻香", "七里香"]
   and [x["why"] for x in cov["miss"]] == ["nocover", "fmt"], str(cov["miss"]))
ck("E3 逐行给结论：四首各一句，其中两句是「没嵌上」、一句是「没移出」",
   len(lines) == 4
   and sum(1 for lv, m in lines if lv == "warning" and "封面没嵌上" in m) == 2
   and sum(1 for lv, m in lines if lv == "warning" and "封面没移出" in m) == 1,
   f"{len(lines)} 行")
ck("E4 日志那句带原因原文（写日志的一侧仍是中文，界面渲染是另一套）",
   any(M.COVER_WHY_TEXT["nocover"] in m for _lv, m in lines))
ck("E5 不勾却还有图那句是告警、说的是没移出，且没混进嵌失败的名单",
   any("封面没移出: d.m4a" in m and M.COVER_WHY_TEXT["kept"] in m
       for lv, m in lines if lv == "warning")
   and all(x["title"] != "半岛铁盒" for x in cov["miss"]))
ck("E6 没勾且文件干净的没写日志（不该为「本来就没有」吵一句）",
   not any("安静" in m for _lv, m in lines))

# ---------------------------------------------------------------- F. 接线
print("== F. 开关接到音乐页两条下载路，默认开 ==")
SVC = pathlib.Path(APP / "server.py").read_text(encoding="utf-8")
IDX = pathlib.Path(APP / "static" / "index.html").read_text(encoding="utf-8")


def block_of(src: str, start: str, end: str) -> str:
    """从源码里抠一段：整份 server.py 里同名的行别处也有，只在自己那一段里比才不算假绿"""
    i = src.find(start)
    if i < 0:
        return ""
    j = src.find(end, i)
    return src[i:j if j > i else i + 600]


ck("F1 配置项存在且默认 True（默认勾上）",
   S.ConfigManager.DEFAULTS.get("music_embed_metadata") is True,
   str(S.ConfigManager.DEFAULTS.get("music_embed_metadata")))
ck("F2 批量那一路：收尾时把开关传给 auto_tag_audio 的 embed_cover",
   "cover_path=cover_file," in SVC and "embed_cover=embed," in SVC)
ck("F3 批量那一路：写完回读并记账（cover_verdict + note_music_cover）",
   "cover_verdict(str(pp), embed, cover_file)" in SVC and "note_music_cover(_MUSIC_JOB," in SVC)
ck("F4 单曲那一路也听同一个开关（以前这条路根本没打标签）",
   "embed_cover=embed_meta," in SVC)
fb = block_of(SVC, "    opts = {\n        \"audio_only\": True,", "\n    }")
ck("F5 队列兜底那一路的 embed_thumb 跟着开关走（以前这里写死 True）",
   '"embed_thumb": embed_meta,' in fb, fb[:120])
ck("F5b 开关取值是「本次请求优先、config 兜底」：勾完不点「保存策略」也算数",
   "embed_meta = body.get(\"embed_metadata\")" in SVC
   and 'embed_meta = bool(cfg.data.get("music_embed_metadata", True))' in SVC)
ck("F5c 收藏清单那条内部转发也把开关带上（漏了它就只会用 config 里的旧值）",
   '"embed_metadata": body.get("embed_metadata"),' in SVC)
ck("F5d 音乐页四个下载入口每次都带当前勾选值（整批 / 链接入队 / 单行 / 收藏清单）",
   len(re.findall(r"(?<!music_)embed_metadata: !!musicEmbedMeta\.value", IDX)) == 4,
   str(re.findall(r"\b(?:music_)?embed_metadata: !!musicEmbedMeta\.value", IDX)))
ck("F6 界面重开时按后端存的值回填（不是每次回到默认）",
   '"embed_metadata": bool(cfg.data.get("music_embed_metadata", True))' in SVC)
ck("F6b 批量开头先把开关状态写进日志（不勾时后面每首都安静，没这句分不清是没勾还是没封面）"
   "· #93b 把这句拆成两处字面调用，开与关两支各挂一键，话还是那句",
   'k="srv.music.embed_on"' in SVC and 'k="srv.music.embed_off"' in SVC
   and "内嵌封面: 开" in SVC and "内嵌封面: 关" in SVC)
sig = inspect.signature(M.download_songs)
ck("F7 download_songs / download_via_musicdl 都接了 embed_cover",
   "embed_cover" in sig.parameters
   and "embed_cover" in inspect.signature(M.download_via_musicdl).parameters,
   str(list(sig.parameters)))
ck("F8 界面默认勾选，且随策略一起存回后端",
   "const musicEmbedMeta = ref(true);" in IDX
   and "music_embed_metadata: !!musicEmbedMeta.value" in IDX
   and "if (typeof st.embed_metadata === 'boolean')" in IDX)
ck("F9 勾选框有说明开关到底管什么的 tooltip", "tr('music.embedMetaHint')" in IDX)
ck("F10 批量小结会说「嵌上几首 / 几首没嵌上 / 几首没移出」，失败能展开",
   "tr('music.coverOkPart'" in IDX and "tr('music.coverMissPart'" in IDX
   and "tr('music.coverKeptPart'" in IDX and "showCoverMiss(coverMiss)" in IDX)
ck("F10b 没移出那一本账读的是 s.cover.kept（后端记的就是这个键，写成别的名字永远显示不出来）",
   "s.cover.kept) ? tr('music.coverKeptPart'" in IDX and "tr('music.coverKeptPart', { n: s.cover.kept })" in IDX)
ck("F11 小结里封面那三句排在「用时」之前（拼接顺序钉住，跑完先看结果再看耗时）",
   0 < IDX.index("tr('music.coverOkPart'") < IDX.index("tr('music.coverMissPart'")
   < IDX.index("tr('music.coverKeptPart'") < IDX.index("tr('music.elapsedPart'"))
I18N_C = pathlib.Path(APP / "static" / "i18n.js").read_text(encoding="utf-8")
ck("F12 「没移出」那句中英都有（i18n 的门是逐个键比对的，少一边就是切英文后空白）",
   I18N_C.count("'music.coverKeptPart'") == 2, str(I18N_C.count("'music.coverKeptPart'")))

# ---------------------------------------------------------------- G. 端点里真的取这个值
print("== G. 端点实测：勾与不勾落到队列 opts 上的 embed_thumb 不一样（假 cfg / 假队列，不写真实 config） ==")


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeQueue:
    def __init__(self):
        self.calls: list[dict] = []

    def add_urls(self, urls, opts):
        self.calls.append({"urls": list(urls), "opts": dict(opts)})
        return ["fake-%d" % len(self.calls)]


ORIG = {k: getattr(S, k, None) for k in ("cfg", "log_mgr", "queue")}
fq = FakeQueue()
try:
    S.cfg = FakeCfg({"download_dir": str(SHARD / "dl"), "music_embed_metadata": True})
    S.log_mgr = type("L", (), {"log": staticmethod(lambda *a, **k: None)})()
    S.queue = fq
    U = ["https://example.com/watch?v=1"]
    S.api_music_download({"urls": U, "embed_metadata": False})
    S.api_music_download({"urls": U, "embed_metadata": True})
    S.api_music_download({"urls": U})          # 没带 = 老客户端，按 config 里存的值
    got = [c["opts"].get("embed_thumb") for c in fq.calls]
    ck("G1 不勾→opts.embed_thumb=False，勾了→True，没带→按 config（不再写死）",
       got == [False, True, True], str(got))
    ck("G2 这一趟没碰真实 config（假 cfg 也没被 save 过）",
       S.cfg.saves == 0, "saves=%d" % S.cfg.saves)
    ck("G3 其它队列参数没被顺手改掉（audio_only / format 照旧）",
       all(c["opts"].get("audio_only") is True and c["opts"].get("format") == "m4a" for c in fq.calls),
       str([c["opts"] for c in fq.calls[:1]])[:120])
finally:
    for k, v in ORIG.items():
        setattr(S, k, v)

# ---------------------------------------------------------------- H. 不勾就连下载器写的那张也移出去
print("== H. 勾了不嵌时把已经在标签里的图移出去：只动标签，音频数据与同名图片文件都不碰 ==")
FFPROBE = APP / "tools" / "ffprobe.exe"
if not FFPROBE.is_file():
    FFPROBE = pathlib.Path(shutil.which("ffprobe") or "ffprobe")


def probe(p: pathlib.Path):
    """回读音频自己的流信息：移图前后不一致就说明动到了数据，不是只动标签"""
    r = subprocess.run([str(FFPROBE), "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", str(p)],
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace")
    try:
        j = json.loads(r.stdout)
    except Exception:
        return None
    st = next((s for s in (j.get("streams") or []) if s.get("codec_type") == "audio"), {})
    return (st.get("codec_name"), str(j.get("format", {}).get("duration")),
            str(j.get("format", {}).get("bit_rate")))


def text_tag(p: pathlib.Path) -> str:
    from mutagen import File as _MF
    t = getattr(_MF(str(p)), "tags", None) or {}
    return " ".join(str(v) for v in t.values())


def mp3_frames(p: pathlib.Path) -> bytes:
    """ID3 那一段之后的全部字节 —— 就是音频帧本身。标签怎么写都不该动它。"""
    b = p.read_bytes()
    i = 0
    if b[:3] == b"ID3":
        size = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
        i = 10 + size
    while i < len(b) - 1 and not (b[i] == 0xFF and (b[i + 1] & 0xE0) == 0xE0):
        i += 1
    return b[i:]


def flac_blocks(p: pathlib.Path):
    """flac 自己的元数据块表：[(块类型, 长度, 内容是否全零)]。移图后不该再有 6(PICTURE)。"""
    b = p.read_bytes()
    assert b[:4] == b"fLaC", b[:4]
    i, out = 4, []
    while True:
        hdr = b[i]
        size = int.from_bytes(b[i + 1:i + 4], "big")
        out.append((hdr & 0x7F, size, b[i + 4:i + 4 + size].count(0) == size))
        i += 4 + size
        if hdr & 0x80:
            break
    return out, len(b), i   # i 之后就是音频帧


if ".mp3" in BLANK and JPG.is_file():
    keep = SHARD / "sibling.jpg"
    keep.write_bytes(JPG_BYTES)

    seeded = fresh(".mp3", "strip_seed")
    M.auto_tag_audio(str(seeded), title="晴天", artists="周杰伦", album="八度空间",
                     cover_path=str(JPG), embed_cover=True)
    before_probe = probe(seeded)
    ck("H0 先把图嵌进去（这一组要移的是「已经在文件里」的那张，不是空气）",
       embedded(seeded) == JPG_BYTES, f"{len(embedded(seeded))} 字节")

    gone = SHARD / "strip_done.mp3"
    shutil.copyfile(seeded, gone)
    ok = M.auto_tag_audio(str(gone), title="晴天", artists="周杰伦", album="八度空间",
                          cover_path=str(JPG), embed_cover=False)
    ck("H1 不勾这一趟：文件里的图真没了（回读为空）",
       ok and embedded(gone) == b"", f"回读 {len(embedded(gone))} 字节")
    ck("H2 移图只动标签：音频帧一个字节没变（容器总码率会变，那是标签区小了，不是数据被动过）",
       mp3_frames(gone) == mp3_frames(BLANK[".mp3"]) == mp3_frames(seeded)
       and probe(gone)[:2] == before_probe[:2],
       f"{before_probe} -> {probe(gone)} / 帧 {len(mp3_frames(gone))} 字节")
    ck("H3 文字标签没被一起带走（曲名还在）", "晴天" in text_tag(gone), text_tag(gone)[:40])
    ck("H4 移完的体积回到空白件附近（图没了却留 80KB 空壳＝padding 没收回）",
       abs(gone.stat().st_size - BLANK[".mp3"].stat().st_size) < 4096,
       f"空白 {BLANK['.mp3'].stat().st_size} / 现在 {gone.stat().st_size}")
    ck("H5 同名图片文件不碰（移的是文件里那张，旁边那张是留给用户看的）",
       keep.read_bytes() == JPG_BYTES)

    clean = fresh(".mp3", "strip_clean")
    raw = clean.read_bytes()
    ck("H6 文件本来就没图：不动它、照实返回 True（不该为「没有」重写一篇）",
       M.strip_embedded_cover(str(clean)) and clean.read_bytes() == raw)

    ro = fresh(".mp3", "strip_ro")
    M.auto_tag_audio(str(ro), cover_path=str(JPG), embed_cover=True)
    os.chmod(ro, 0o444)
    msgs: list[tuple[str, str]] = []
    try:
        res = M.strip_embedded_cover(str(ro), log=lambda m, lv="info": msgs.append((lv, m)))
    finally:
        os.chmod(ro, 0o644)
    ck("H7 移不动就说移不动：返回 False 且给一句告警，不假装成功",
       res is False and any(lv == "warning" and "封面没移出" in m for lv, m in msgs), str(msgs)[:120])

    ck("H8 不勾这一趟真调用移图（写在 auto_tag_audio 的收尾里，不是只在归因里说说）",
       "strip_embedded_cover(str(pth), log=log)" in inspect.getsource(M.auto_tag_audio))
    ck("H9 mp3 那条用 callable 给 padding（ID3.save(padding=256) 会 TypeError，等于这条支路从没跑通过）",
       "padding=lambda _t: 256" in SRC_MS)

for ext, tag in ((".flac", "flac"), (".m4a", "m4a")):
    if ext not in BLANK or not JPG.is_file():
        continue
    p = fresh(ext, "strip_" + tag)
    M.auto_tag_audio(str(p), cover_path=str(JPG), embed_cover=True)
    seeded_art = embedded(p)
    seeded_bytes = p.read_bytes()
    seeded_probe = probe(p)
    seeded_layout = flac_blocks(p) if tag == "flac" else None
    ck(f"H10a[{tag}] 先确认真把图嵌进去了 {ext}（不然后面「移完了」是句空话）",
       seeded_art == JPG_BYTES, f"回读 {len(seeded_art)} 字节 / jpg {len(JPG_BYTES)} 字节")
    M.auto_tag_audio(str(p), title="稻香", artists="周杰伦", cover_path=str(JPG), embed_cover=False)
    ck(f"H10[{tag}] {ext} 走的是各自的标签通道，移完回读为空",
       embedded(p) == b"" and seeded_bytes != p.read_bytes(),
       f"{len(seeded_bytes)} → {p.stat().st_size}")
    ck(f"H10b[{tag}] 移图没改流本身：编码与时长前后一致（重编码会动这两个；总码率会随标签区变小）",
       probe(p)[:2] == seeded_probe[:2], f"{seeded_probe} -> {probe(p)}")
    if tag == "flac":
        # 活体读到的形状：图没了、腾出来的位置补成全零 PADDING、整文件字节数不变 —— 口径已定，钉住别被「顺手优化」掉
        blocks, total, audio_start = flac_blocks(p)
        ck("H12[flac] 移之前真有 PICTURE 块、移之后没了，腾出的位置是全零 PADDING（不是旧图残留）",
           any(c == 6 for c, _s, _z in seeded_layout[0])
           and all(c != 6 for c, _s, _z in blocks)
           and any(c == 1 and z for c, _s, z in blocks),
           f"{[(c, s) for c, s, _ in seeded_layout[0]]} → {[(c, s) for c, s, _ in blocks]}")
        ck("H12b[flac] 旧图那段字节移前确实在文件里、移完整个文件一个都不剩（含被并进 padding 的那段）",
           JPG_BYTES[3:60] in seeded_bytes and JPG_BYTES[3:60] not in p.read_bytes(),
           f"移前 {len(seeded_bytes)} 字节含图 / 移后 {total} 字节、音频帧从 {audio_start} 起")
        ck("H12c[flac] 移完体积与音频帧起点都不变（flac 这一路不缩，mp3 才收标签区 —— 按实测说）",
           total == seeded_layout[1] and audio_start == seeded_layout[2],
           f"{seeded_layout[1]} → {total}，帧起点 {seeded_layout[2]} → {audio_start}")

src_strip = inspect.getsource(M.strip_embedded_cover)
ck("H11 认不了的容器照实说「没动它」并回 False（不把「不支持」混报成「移出去了」）",
   "return False" in src_strip and "没动它" in src_strip)

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)