r"""⑦ 格式/位深指定下载 + 用无损参照核对成品音质。

口径只有三条，这份自检就围着它们转：
1. 档位钉不住平台，所以「音质要求」只用于挑候选、可选地拦下确认不达标的、以及下完后核对；
2. 「读不出来」永远不等于「不达标」；
3. 与无损参照只比元数据（曲名/歌手/时长/位深/采样率），不碰第三方音频。

全程离线：musicdl 与参照接口一律打桩，真发请求那段只验参数怎么拼；只读写 %TEMP%。
跑法：`python tests/qualityspec_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def log(m, lv="info"):
    LOGS.append(f"[{lv}] {m}")


OUT = Path(tempfile.mkdtemp(prefix="md_qualityspec_test_"))
DL = OUT / "dl"
DL.mkdir(parents=True)
CACHE = DL / "_musicdl_cache"
CACHE.mkdir(parents=True)

print("=== A. 要求本身的清洗与措辞 ===")
ck("A1 全默认 = 没提要求，整条链路跳过", not M.quality_spec_active({}) and not M.quality_spec_active(None))
ck("A2 认得的档位才留下（大小写与空格都吃得下），格式表里没有的（如 flac）退回不限",
   M.norm_quality_spec({"format": " LOSSLESS ", "min_bit_depth": "24"})["format"] == "lossless"
   and M.norm_quality_spec({"min_bit_depth": "24"})["min_bit_depth"] == 24
   and M.norm_quality_spec({"format": "flac"})["format"] == "")
n_bad = M.norm_quality_spec({"format": "ape", "min_bit_depth": 20, "min_bitrate": 999,
                             "min_sample_rate": "abc", "strict": 1})
ck("A3 非法值退回「不限」而不是把整批判歪（ape/20bit/999k 都不在档位表里）",
   n_bad == {"format": "", "min_bit_depth": 0, "min_sample_rate": 0, "min_bitrate": 0,
             "strict": True}, n_bad)
ck("A4 措辞与界面那句话同一份（日志里也要能对上）",
   M.quality_spec_label({"format": "lossless", "min_bit_depth": 24, "min_sample_rate": 96000,
                         "min_bitrate": 320}) == "无损、24bit 以上、96kHz 以上、320k 以上",
   M.quality_spec_label({"format": "lossless", "min_bit_depth": 24, "min_sample_rate": 96000,
                         "min_bitrate": 320}))
ck("A5 采样率按人话写：44100 → 44.1，48000 → 48",
   M._khz(44100) == "44.1" and M._khz(48000) == "48", f"{M._khz(44100)}/{M._khz(48000)}")

print("=== B. 逐维核对：ok / low / unknown / none 四种结论 ===")
FLAC24 = {"quality": "flac 24bit", "bit_depth": 24, "sampling_rate": 96000}
MP3320 = {"quality": "MP3 320k 44.1kHz"}
MP3128 = {"quality": "MP3 128k"}
LOSSLESS = {"format": "lossless"}


def qa(facts, spec):
    return M.quality_against_spec(M.row_audio_facts(facts), spec)


ck("B1 无损成品对「仅无损」= 符合", qa(FLAC24, LOSSLESS)["state"] == "ok", qa(FLAC24, LOSSLESS))
r_low = qa(MP3320, LOSSLESS)
ck("B2 MP3 对「仅无损」= 不达标，且说清为什么",
   r_low["state"] == "low" and "不是无损" in r_low["note"], r_low)
ck("B3「320k」这种只带码率的标注也算知道格式（不会被当成没标注混过仅无损）",
   M.row_audio_facts(MP3320)["format_known"] and M.row_audio_facts({"quality": ""})["format_known"] is False,
   M.row_audio_facts(MP3320))
r_unk = qa({"quality": ""}, LOSSLESS)
ck("B4 什么都没标的是「没核到」，不是不达标", r_unk["state"] == "unknown"
   and "格式" in r_unk["unknown"], r_unk)
ck("B5 无损不看码率这一维（否则最好的那档反被判不达标）",
   qa(FLAC24, {"format": "lossless", "min_bitrate": 320})["state"] == "ok")
ck("B6 有损按码率卡：128k 低于 320k",
   qa(MP3128, {"min_bitrate": 320})["state"] == "low", qa(MP3128, {"min_bitrate": 320}))
r_sr = qa(MP3320, {"min_sample_rate": 96000})
ck("B7 采样率不达标会点名两边各是多少",
   r_sr["state"] == "low" and "44.1kHz" in r_sr["note"] and "96kHz" in r_sr["note"], r_sr)
r_fmt = qa(FLAC24, {"format": "mp3"})
ck("B8 容器对不上（要求 MP3、这条是无损）也算不达标，并点名两边",
   r_fmt["state"] == "low" and "不是 MP3" in r_fmt["note"], r_fmt)
ck("B9 没提要求时一律 none，不给任何行打标",
   qa(FLAC24, {})["state"] == "none")
ck("B10 只提位深时，缺位深只算没核到（不拿「不知道」卡人）",
   qa({"quality": "flac"}, {"min_bit_depth": 24})["state"] == "unknown")
rows = [{"id": "1", "title": "晴天", "quality": "MP3 320k"},
        {"id": "2", "title": "稻香", "quality": "flac 24bit"},
        {"id": "3", "title": "无条件", "reference_only": True, "quality": "flac 24bit"},
        {"id": "local:x", "title": "本地曲", "is_local": True, "quality": ""}]
M.annotate_quality_spec(rows, LOSSLESS)
ck("B11 批量标注只碰可下载行", rows[0]["quality_state"] == "low"
   and rows[1]["quality_state"] == "ok", [r.get("quality_state") for r in rows])
ck("B12 参照行与本地行不标（前者不是成品，后者的档位来自真标签）",
   "quality_state" not in rows[2] and "quality_state" not in rows[3], rows[2])
before = [{"title": "A", "artists": "B", "duration_s": 200, "source": "NeteaseMusicClient"}]
M.annotate_quality_spec(before, None)
ck("B13 不勾要求时一行都不标（老行为零改动）", "quality_state" not in before[0], before)

print("=== C. 下载前只能信平台标注（musicdl 的 SongInfo） ===")


class SongInfoStub:
    """只带这一轮真用到的字段；桩不许比真 SongInfo 宽 —— 这些字段真 SongInfo 全有。"""

    def __init__(self, name, *, ext="mp3", bitrate=None, samplerate=None, raw_quality="",
                 source="NeteaseMusicClient"):
        self.song_name, self.source, self.ext = name, source, ext
        self.singers, self.identifier = "某歌手", "id-" + name
        self.work_dir, self._save_path = str(CACHE), None
        self.lyric, self.cover_url = "", ""
        if bitrate is not None:
            self.bitrate = bitrate          # 真 musicdl 这里填的是 bps
        if samplerate is not None:
            self.samplerate = samplerate
        if raw_quality:
            self.raw_data = {"quality": raw_quality}

    @property
    def save_path(self):
        return self._save_path or os.path.join(
            self.work_dir, f"{self.song_name} - {self.identifier}.{self.ext}")


f1 = M.song_spec_facts(SongInfoStub("甲", ext="flac", bitrate=1411000, samplerate=96000,
                                     raw_quality="lossless"))
ck("C1 SongInfo 的 bitrate 是 bps，抠出来要换算成 kbps（无损不看码率）",
   f1["bitrate_kbps"] == 1411 and f1["lossless"], f1)
f2 = M.song_spec_facts(SongInfoStub("乙", ext="mp3", bitrate=320000))
ck("C2 320k 的 mp3 标注如实成 320k", f2["bitrate_kbps"] == 320 and not f2["lossless"], f2)
f3 = M.song_spec_facts(SongInfoStub("丁", ext="", raw_quality="flac"))
ck("C3 平台自报的档位名只在 raw_data 里，也认得（网易云 hires 那种）",
   f3["lossless"], f3)
f4 = M.song_spec_facts(SongInfoStub("丙", ext=""))
ck("C4 什么都没自报 → 一档都抠不出来（这只是「没核到」的原料，不是不达标）",
   not f4["known"] and not f4["bitrate_kbps"], f4)
ck("C5 占位 dict 也吃得下（没匹配到平台前它就是个 dict）",
   isinstance(M.song_spec_facts({"title": "戊", "needs_match": True}), dict))

print("=== D. 与无损参照比一比：只比元数据 ===")
REF24 = {"id": "ref:qobuz:9", "reference_only": True, "title": "晴天", "artists": "周杰伦",
         "duration_s": 240, "quality": "flac 24bit", "bit_depth": 24, "sampling_rate": 48000,
         "isrc": "TW-A1-24-00009"}
r_same = M.ref_compare(M.row_audio_facts({"quality": "flac 24bit 48khz"}), REF24)
ck("D1 与参照同档", r_same["state"] == "same", r_same)
r_below = M.ref_compare(M.row_audio_facts({"quality": "flac 16bit 44.1khz"}), REF24)
ck("D2 位深/采样率低于参照会逐条点名",
   r_below["state"] == "below" and "位深 16bit 低于参照 24bit" in r_below["note"]
   and "采样率 44.1kHz 低于参照 48kHz" in r_below["note"], r_below)
r_mp3 = M.ref_compare(M.row_audio_facts({"quality": "MP3 320k 44.1kHz"}), REF24)
ck("D3 参照是无损而这条不是：低于参照", r_mp3["state"] == "below" and "参照是无损" in r_mp3["note"], r_mp3)
r_no = M.ref_compare(M.row_audio_facts({"quality": ""}), REF24)
ck("D4 这条没档位信息 → 只说无法比对，不判低于", r_no["state"] == "unknown"
   and "无法与参照" in r_no["note"], r_no)
r_partial = M.ref_compare(M.row_audio_facts({"quality": "flac 24bit"}), REF24)
ck("D5 参照有采样率而这条没写：算没核到，不算低于", r_partial["state"] == "unknown"
   and "采样率" in r_partial["note"], r_partial)
ck("D6 没有参照时结论是 none（不写一句吓人的话）",
   M.ref_compare(M.row_audio_facts({"quality": "flac"}), {})["state"] == "none")

cands = [
    {"id": "a", "title": "晴天", "artists": "周杰伦", "duration_s": 240, "quality": "flac 16bit 44.1khz"},
    {"id": "b", "title": "晴天", "artists": "周杰伦", "duration_s": 400, "quality": "MP3 320k"},
    {"id": "c", "title": "不存在的歌", "artists": "某人", "duration_s": 240, "quality": "MP3 320k"},
    {"id": "d", "title": "晴天（Live）", "artists": "周杰伦", "duration_s": 240, "quality": "flac 24bit 48khz"},
]
M.annotate_reference_compare(cands, [REF24])
ck("D7 同一首歌才比：a 判低于参照", cands[0]["ref_state"] == "below", cands[0])
ck("D8 时长对不上的是两版录音，结论是「没有可比对的参照」",
   cands[1]["ref_state"] == "none" and "时长对不上" in cands[1]["ref_note"], cands[1])
ck("D9 参照里没这首歌就照实说", cands[2]["ref_state"] == "none"
   and "没有这首歌" in cands[2]["ref_note"], cands[2])
ck("D10 参照行自己不参与比对",
   "ref_state" not in dict(REF24), REF24.get("ref_state"))
ck("D11 比对结论带上参照的 ISRC，用户能自己去官方页面对一眼",
   cands[0].get("ref_isrc") == REF24["isrc"], cands[0].get("ref_isrc"))
ck("D12 没有任何参照行时整批原样返回（不写 ref_note）",
   "ref_state" not in M.annotate_reference_compare([{"id": "z", "title": "x"}], [])[0])

print("=== E. 下载接线：拦不拦看得勾没勾，成品落盘后逐首核对 ===")
GIVEN: list[list] = []
FILE_META: dict = {}
_real_meta = M.audio_file_meta


def fake_meta(path, *, log=print):
    """成品标签桩：按文件名片段命中 —— 归档会换目录，曲名一定还在文件名里。"""
    name = Path(str(path)).name
    for key, val in FILE_META.items():
        if key in name:
            return dict(val)
    return {"title": name, "artists": "某歌手", "duration_s": 240, "quality": "", "reader": "stub"}


class StubClient:
    def download(self, song_infos=None):
        infos = list(song_infos or [])
        GIVEN.append(infos)
        out = []
        for s in infos:
            p = Path(s.save_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"audio-" + s.song_name.encode("utf-8"))
            cp = SongInfoStub(s.song_name)
            cp._save_path = str(p)
            out.append(cp)
        return out


_real = (M.musicdl_available, M._build_client, M.musicdl_cache_dir,
         M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover)
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: StubClient()
M.musicdl_cache_dir = lambda base="": str(CACHE)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}
M.audio_file_meta = fake_meta
META_OK = {"title": "有无损", "artists": "某歌手", "duration_s": 240, "quality": "flac 24bit",
           "bit_depth": 24, "lossless": True, "reader": "mutagen"}
META_LOW = {"title": "只有mp3", "artists": "某歌手", "duration_s": 240, "quality": "MP3 128k",
            "bitrate_kbps": 128, "reader": "mutagen"}

mp3_id = M._cache_song(SongInfoStub("只有mp3", ext="mp3", bitrate=128000))
flac_id = M._cache_song(SongInfoStub("有无损", ext="flac", bitrate=1411000, samplerate=96000,
                                     raw_quality="lossless"))
blind_id = M._cache_song(SongInfoStub("没自报", ext="", bitrate=None))
try:
    FILE_META.update({"有无损": META_OK, "只有mp3": META_LOW})
    LOGS.clear()
    got = M.download_songs([mp3_id, flac_id], work_dir=str(DL), log=log,
                           quality_spec={"format": "lossless", "min_bitrate": 320})
    ck("E1 没勾「不达标不下」：标注不达标的照样下（要求只用于挑候选与核对）",
       {s.song_name for s in GIVEN[-1]} == {"有无损", "只有mp3"}, GIVEN[-1])
    ck("E2 开始就写清这次的要求、并且说明档位钉不住",
       any("本次音质要求：无损、320k 以上" in m and "档位由平台决定" in m for m in LOGS),
       [m for m in LOGS if "音质要求" in m][:1])
    ck("E3 没勾时不出现「不下」那半句",
       not any("勾了「不达标不下」" in m for m in LOGS), [m for m in LOGS if "音质要求" in m][:1])
    ck("E4 成品读出来确实低于要求：写在同一行下载日志上，让人看见而不是猜",
       any("musicdl 已下载" in m and "低于要求" in m and "只有mp3" in m for m in LOGS),
       [m for m in LOGS if "已下载" in m])
    ck("E5 收尾把不达标的那几首列全：先报数量，再逐行点名到文件名",
       any("首成品读元数据后确认低于本次要求" in m and "1 首" in m for m in LOGS)
       and any("只有mp3" in m and m.split("] ", 1)[-1].startswith("「") for m in LOGS),
       [m for m in LOGS if "确认低于" in m or "只有mp3" in m])

    LOGS.clear()
    got = M.download_songs([mp3_id, flac_id], work_dir=str(DL), log=log,
                           quality_spec={"format": "lossless", "strict": True})
    ck("E6 勾了「不达标不下」：平台标注确认不达标的根本不递交",
       [s.song_name for s in GIVEN[-1]] == ["有无损"], GIVEN[-1])
    ck("E7 拦下那一首点名曲名与原因",
       any("档位不达标，按勾选不下" in m and "只有mp3" in m and "不是无损" in m for m in LOGS),
       [m for m in LOGS if "不达标" in m][:2])
    ck("E8 被拦下的那首回空串（界面知道这一首没成）", len(got) == 2 and got[0] == "", got)
    ck("E9 全批核过且没有不达标的，就照实说核了几首",
       any("音质核对：1 首成品逐首读过元数据，没有低于本次要求" in m for m in LOGS),
       [m for m in LOGS if "音质核对" in m])

    LOGS.clear()
    M.download_songs([blind_id], work_dir=str(DL), log=log,
                     quality_spec={"format": "lossless", "strict": True})
    ck("E10 平台没自报档位的不算不达标（「不知道」不当「不合格」用）",
       [s.song_name for s in GIVEN[-1]] == ["没自报"], GIVEN[-1])

    FILE_META["有无损"] = dict(META_LOW, title="有无损")
    LOGS.clear()
    M.download_songs([flac_id], work_dir=str(DL), log=log, quality_spec={"format": "lossless"})
    ck("E11 平台标注骗人（挂着 flac 却下回个 128k）：读成品自己的标签照样核出来",
       any("低于要求" in m and "有无损" in m for m in LOGS), [m for m in LOGS if "低于" in m])
    FILE_META["有无损"] = {"title": "有无损", "artists": "某歌手", "duration_s": 240,
                           "quality": "", "reader": "mutagen"}
    LOGS.clear()
    M.download_songs([flac_id], work_dir=str(DL), log=log, quality_spec={"format": "lossless"})
    ck("E12 成品读不出档位：只报没核到，不报不达标",
       any("有一维读不出来" in m for m in LOGS) and not any("确认低于本次要求" in m for m in LOGS),
       [m for m in LOGS if "读不出" in m or "无法核对" in m])
    FILE_META["有无损"] = META_OK

    # 反向验证：把逐维核对换成永远合格，拦人的那一步就必须失效
    _real_qa = M.quality_against_spec
    M.quality_against_spec = lambda facts, spec: {"state": "ok", "note": "", "unknown": [],
                                                  "spec": spec, "want": "", "have": ""}
    try:
        LOGS.clear()
        M.download_songs([mp3_id], work_dir=str(DL), log=log,
                         quality_spec={"format": "lossless", "strict": True})
        ck("E13 反向验证：闸门一撤，同一首 MP3 就真的被下出去了（说明拦它靠的就是这一步）",
           [s.song_name for s in GIVEN[-1]] == ["只有mp3"], GIVEN[-1])
    finally:
        M.quality_against_spec = _real_qa
    LOGS.clear()
    M.download_songs([mp3_id], work_dir=str(DL), log=log, quality_spec=None)
    ck("E14 反向验证：不填要求时既照下，也不产任何音质日志（老行为零改动）",
       [s.song_name for s in GIVEN[-1]] == ["只有mp3"]
       and not any("音质" in m or "不达标" in m for m in LOGS),
       [m for m in LOGS if "音质" in m or "不达标" in m])
finally:
    (M.musicdl_available, M._build_client, M.musicdl_cache_dir,
     M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover,
     M.audio_file_meta) = _real + (_real_meta,)
    FILE_META.clear()

print("=== F. 单独核对成品（/api/music/check_quality 走的那一步） ===")
GOOD = DL / "好成品.flac"
BAD = DL / "差成品.mp3"
BLANK = DL / "没标签.flac"
GONE = DL / "已经不在了.flac"     # 故意不建：验「文件不在原位」这一支
for p, blob in ((GOOD, b"flac"), (BAD, b"mp3"), (BLANK, b"flac")):
    p.write_bytes(blob)
META = {str(GOOD): {"title": "好成品", "artists": "周杰伦", "duration_s": 240,
                    "quality": "flac 24bit 48khz", "bit_depth": 24, "sample_rate": 48000,
                    "lossless": True, "reader": "mutagen"},
        str(BAD): {"title": "差成品", "artists": "周杰伦", "duration_s": 240,
                   "quality": "MP3 128k", "bitrate_kbps": 128, "reader": "mutagen"},
        str(BLANK): {"title": "没标签", "artists": "", "duration_s": 0,
                     "quality": "", "reader": "mutagen"}}
REAL_SEARCHED: list[str] = []
_real_flacref = M.flacref_search


def spy_flacref(kw, **kw2):
    """回一条「同一首歌、曲库里是 24bit/48kHz 无损」的参照行：曲名取查询词的后半，
    这样它才过得了打分闸门 —— 闸门不放行的话结论本就该是「没有可比对的参照」。"""
    REAL_SEARCHED.append(kw)
    return [dict(REF24, title=str(kw).split(" ", 1)[-1], id="ref:qobuz:" + str(len(REAL_SEARCHED)))]


M.audio_file_meta = lambda p, *, log=print: dict(META.get(str(p), {"title": Path(str(p)).stem,
                                                                   "quality": "", "reader": "stub"}))
M.flacref_search = spy_flacref
try:
    rows_q = M.check_quality([str(GOOD), str(BAD), str(GONE)], spec={"format": "lossless",
                                                                     "min_bitrate": 320})
    ck("F1 达标的那份：state=ok，报的是文件自己的档位",
       rows_q[0]["state"] == "ok" and "无损" in rows_q[0]["have"], rows_q[0])
    ck("F2 低于要求的那份点名是哪一份、差在哪",
       rows_q[1]["state"] == "low" and "128k 低于要求 320k" in rows_q[1]["note"], rows_q[1])
    ck("F3 文件不在原位的照实说，不混进「不达标」",
       rows_q[2]["state"] == "missing" and "文件不在" in rows_q[2]["note"], rows_q[2])
    ck("F4 没勾参照就一次都不打参照接口（不发网络）", REAL_SEARCHED == [], REAL_SEARCHED)

    REAL_SEARCHED.clear()
    rows_r = M.check_quality([str(BAD), str(GOOD)], spec={}, use_reference=True)
    ck("F5 没提要求但勾了参照：档位这一维回 none，参照那一份照样给结论",
       rows_r[0]["state"] == "none" and rows_r[0]["ref_state"] == "below", rows_r[0])
    ck("F6 参照比对同样只比元数据（结论里点的是位深/采样率/无损，不涉及音频地址）",
       "低于参照" in rows_r[0]["ref_note"]
       and not any("http" in str(v) for v in rows_r[0].values()), rows_r[0]["ref_note"])
    ck("F7 参照查询用的就是成品自己的曲名歌手",
       REAL_SEARCHED and "好成品" in "".join(REAL_SEARCHED), REAL_SEARCHED)

    def boom(*a, **k):
        raise RuntimeError("参照站挂了")

    M.flacref_search = boom
    rows_e = M.check_quality([str(GOOD)], spec={"format": "lossless"}, use_reference=True)
    ck("F8 参照查询挂了不影响「实际档位」这一份结论",
       rows_e[0]["state"] == "ok" and "参照查询失败" in rows_e[0]["ref_note"], rows_e[0])
    M.flacref_search = lambda *a, **k: []
    rows_n = M.check_quality([str(GOOD)], spec={"format": "lossless"}, use_reference=True)
    ck("F9 参照里没有这首歌 = 没有可比对的参照，不是低于",
       rows_n[0]["ref_state"] in ("none", "") and not rows_n[0]["ref_note"].startswith("低于"),
       rows_n[0])
    rows_bare = M.check_quality([str(DL / "没标签.flac")], spec={"format": "lossless"})
    ck("F10 成品读不出档位时只算没核到（不判不达标）",
       rows_bare[0]["state"] in ("unknown",), rows_bare[0])
    ck("F11 空清单不炸", M.check_quality([], spec={"format": "lossless"}) == [])
    ck("F12 反向验证：不勾参照时永远不会写 ref_note",
       all(not r.get("ref_note") for r in M.check_quality([str(GOOD), str(BAD)],
                                                           spec={"format": "lossless"})))
finally:
    M.audio_file_meta = _real_meta
    M.flacref_search = _real_flacref

print("=== G. 界面那句话与后端同源 ===")
ck("G1 选项表由接口回给界面，前端不抄第二份（改档位只改这一处）",
   M.QUALITY_FORMAT_OPTIONS and M.QUALITY_BIT_DEPTH_OPTIONS[1:] == (16, 24)
   and M.QUALITY_SAMPLE_RATE_OPTIONS[1:] == (44100, 48000, 96000)
   and M.QUALITY_BITRATE_OPTIONS[1:] == (128, 192, 320),
   (M.QUALITY_FORMAT_OPTIONS, M.QUALITY_BIT_DEPTH_OPTIONS))
ck("G2 「不限」档永远是 0，前端默认值与后端默认值是同一份",
   M.QUALITY_SPEC_DEFAULT == {"format": "", "min_bit_depth": 0, "min_sample_rate": 0,
                              "min_bitrate": 0, "strict": False}, M.QUALITY_SPEC_DEFAULT)

shutil_rmtree = None
try:
    import shutil
    shutil.rmtree(OUT, ignore_errors=True)
except Exception:
    pass

print()
if FAILED:
    print(f"FAILED {len(FAILED)}：")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("ALL PASS")
