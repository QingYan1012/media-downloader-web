r"""判重与换源：认歌靠打分闸门，不靠文件名。

起因（#123 / #135）：「跳过已下载」以前按命名模板比文件名，同一首歌换个平台写法不同、
或者用户改了模板，老成品就对不上号，于是隔几天又下一份，最后落成套 `曲名_1.mp3`。
现在改成扫一遍下载目录、按 #132 的曲名+歌手+时长闸门判同一首；换源同理，
只有闸门放过、并且新地址当场探得到结果，才算换成。

全程不联网：搜索与探测打桩，闸门用真函数。素材由 ffmpeg 真写，只落在 %TEMP%。
跑法：`python tests/switchsource_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import music_search as M  # noqa: E402

FFMPEG = APP / "tools" / "ffmpeg.exe"
if not FFMPEG.is_file():
    FFMPEG = pathlib.Path(shutil.which("ffmpeg") or "ffmpeg")

FAILED: list[str] = []
LOGS: list[str] = []


def ck(name, cond, got=""):
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not ok:
        FAILED.append(name)


def log(m, lv="info"):
    LOGS.append(f"[{lv}] {m}")


def run(args):
    return subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y"] + args,
                          capture_output=True, text=True, timeout=120,
                          encoding="utf-8", errors="replace")


ROOT = pathlib.Path(os.environ.get("TEMP", "C:\\tmp")) / "md_switchsource_test"
SHARD = ROOT / time.strftime("%H%M%S")
DL = SHARD / "dl"                 # 模拟下载目录（判重看这里）
DL.mkdir(parents=True)
# 判重会走本地索引快照那套落盘逻辑；不拐进 SHARD 就会往程序目录的 local_index 里漏水
M._LOCAL_INDEX_DIR = SHARD / "index_dir"

# ── 素材：一首带标签（晴天）、一首只有文件名没标签（海阔天空）、一首别人唱的同名曲 ──
TAGGED = DL / "周杰伦" / "晴天 - 周杰伦.mp3"
TAGGED.parent.mkdir(parents=True)
r1 = run(["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-b:a", "192k",
          "-metadata", "title=晴天", "-metadata", "artist=周杰伦",
          "-metadata", "album=八度空间", str(TAGGED)])
UNT = DL / "Beyond" / "海阔天空 - Beyond.mp3"     # 名字按下载器模板「曲名 - 歌手」，无标签
UNT.parent.mkdir(parents=True)
r2 = run(["-f", "lavfi", "-i", "sine=frequency=520:duration=3", "-b:a", "192k", str(UNT)])
OTHER = DL / "某人" / "晴天 - 某人.mp3"           # 同名不同人：不算已有
OTHER.parent.mkdir(parents=True)
r3 = run(["-f", "lavfi", "-i", "sine=frequency=640:duration=3", "-b:a", "192k", str(OTHER)])
(TDL := DL / "附属文件").mkdir()
(TDL / "和平饭店 - 某人.lrc").write_text("[00:00.50]只有歌词\n", encoding="utf-8")
(TDL / "和平饭店 - 某人.jpg").write_bytes(b"\xff\xd8\xff\xe0junk")
CLIP = DL / "现场.mp4"
r4 = run(["-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=10", str(CLIP)])
ck("T0 素材齐了（三首 mp3 + 只有歌词封面的目录 + 一段视频）",
   all(x.returncode == 0 for x in (r1, r2, r3, r4)),
   "|".join((x.stderr or "")[:60] for x in (r1, r2, r3, r4)))
if FAILED:
    print("素材都没造出来，后面全部作废")
    sys.exit(1)


class Song:
    """只带这一轮真用到的字段，桩不许比真 SongInfo 宽。"""

    def __init__(self, name, artists="某歌手", source="NeteaseMusicClient",
                 duration="0:03", ext="mp3"):
        self.song_name, self.singers, self.source = name, artists, source
        self.duration, self.ext = duration, ext
        self.cover_url = f"https://img.example/{abs(hash(name))}.jpg"
        self.download_url = f"https://audio.example/{abs(hash(name))}.{ext}"


# ---------------------------------------------------------------- A. 比对样本
print("=== A. want_from_song：清单上的这一行归一成闸门要的样本 ===")
w_obj = M.want_from_song(Song("晴天", "周杰伦", duration="3:22"))
ck("A1 SongInfo 对象取 song_name/singers，时长换算成秒",
   w_obj["title"] == "晴天" and w_obj["artists"] == "周杰伦" and w_obj["duration_s"] == 202, w_obj)
w_dic = M.want_from_song({"title": "海阔天空", "artists": ["黄", "贯", "中"], "duration_s": 3})
ck("A2 占位 dict 直接沿用，歌手列表按逗号拼",
   w_dic["title"] == "海阔天空" and w_dic["artists"] == "黄, 贯, 中" and w_dic["duration_s"] == 3, w_dic)
w_none = M.want_from_song(None)
ck("A3 空行不抛异常，各字段就是空", w_none["title"] == "" and w_none["duration_s"] == 0, w_none)

# ---------------------------------------------------- B. 判重：扫目录按闸门认歌
print("=== B. find_existing_local_songs：目录里有没有这一首，按曲名+歌手+时长判 ===")
WANTS = [{"title": "晴天", "artists": "周杰伦", "duration_s": 3},
         {"title": "海阔天空", "artists": "Beyond", "duration_s": 3},
         {"title": "晴天", "artists": "别的歌手", "duration_s": 3},
         {"title": "和平饭店", "artists": "某人", "duration_s": 3},
         {"title": "", "artists": "没曲名", "duration_s": 0},
         {"title": "查无此歌", "artists": "某人", "duration_s": 3}]
hits = M.find_existing_local_songs(WANTS, str(DL), log=log)
by_i = {i: (os.path.relpath(p, DL), sc, mt) for i, p, sc, mt in hits}
ck("B1 带标签的成品认出来了（曲名歌手都来自标签）",
   by_i.get(0, ("", 0, ""))[0] == os.path.join("周杰伦", "晴天 - 周杰伦.mp3"), by_i)
ck("B2 判定分数过线", by_i.get(0) and by_i[0][1] >= M.MATCH_ACCEPT, by_i.get(0))
ck("B3 没标签、按「曲名 - 歌手」命名的成品也认出来（文件名兜底方向与模板相反，靠对调候选）",
   by_i.get(1, ("", 0, ""))[0] == os.path.join("Beyond", "海阔天空 - Beyond.mp3"), by_i)
ck("B4 同名不同歌手不误伤：那首是别人的录音，照旧要下",
   2 not in by_i, by_i)
ck("B5 目录里只有歌词没有音频不算已有（附属文件不收进候选）", 3 not in by_i, by_i)
ck("B6 没曲名的行一律放过，判不了就不拦", 4 not in by_i and 5 not in by_i, by_i)
ck("B7 返回的第三项是分数、第四项是目录里那份的曲名",
   isinstance(by_i[0][1], int) and by_i[0][2] == "晴天", by_i[0])
rows = M.scan_local_music(str(DL), log=lambda *a, **k: None)
unt_row = next((r for r in rows if r["path"] == str(UNT)), {})
ck("B8 没标签的行 tagged 为假、带标签的为真（对调候选就按这个决定要不要投）",
   unt_row.get("tagged") is False
   and next((r for r in rows if r["path"] == str(TAGGED)), {}).get("tagged") is True,
   (unt_row.get("tagged"), unt_row.get("title"), unt_row.get("artists")))
_want = {"title": "海阔天空", "artists": "Beyond", "duration_s": 3}
ck("B9 反向验证：只把目录里那一行原样喂给真闸门，认不出是同一首（命中确实来自对调那条）",
   not M._pick_track_match(_want, [unt_row]).get("path"),
   M.track_score(_want, unt_row))
ck("B10 反向验证：补上对调的那条，同一份闸门就认出来了",
   bool(M._pick_track_match(_want, [unt_row,
                                    {**unt_row, "title": unt_row["artists"],
                                     "artists": unt_row["title"]}]).get("path")))
before = {p.name for p in DL.rglob("*")}
ck("B11 判重只读不写：没在下载目录里留下索引或临时文件",
   M.find_existing_local_songs(WANTS, str(DL), log=lambda *a, **k: None) and
   {p.name for p in DL.rglob("*")} == before,
   {p.name for p in DL.rglob("*")} ^ before)
ck("B12 目录不存在时一首都不跳（判不了就不拦）",
   M.find_existing_local_songs(WANTS, str(SHARD / "no_such_dir"), log=log) == [])
ck("B13 视频不当作已有成品（.mp4 不在音频口径里）",
   M.find_existing_local_songs([{"title": "现场", "artists": "", "duration_s": 1}],
                               str(DL), log=log) == [])

# ---------------------------------------------------------- C. 换源：真闸门 + 桩搜索
print("=== C. switch_song_source：只有闸门放过才算换成 ===")
_real_search, _real_probe = M._search_one_source, M.range_probe
POOL: dict = {}      # 源名 → 该源返回的候选（曲名, 歌手, 时长）
CALLS: list[str] = []


def fake_search(src, keyword, **kw):
    CALLS.append(f"{src}|{keyword}")
    got = POOL.get(src)
    if not got:
        return [], []
    out = []
    for name, artists, dur, ext in got:
        s = Song(name, artists, source=src, duration=dur, ext=ext)
        out.append({"id": M._cache_song(s), "title": name, "artists": artists,
                    "duration_s": M._dur_seconds(dur), "quality": ext, "source": src})
    return out, []


def fake_probe(url, timeout=12.0):
    CALLS.append(f"probe|{url}")
    return {"size": 4096, "accept_ranges": True}


M._search_one_source, M.range_probe = fake_search, fake_probe
try:
    SRC = ["NeteaseMusicClient", "QQMusicClient"]
    cid = M._cache_song(Song("晴天", "周杰伦", source="NeteaseMusicClient"))
    orig = M.get_cached_song(cid)
    POOL["QQMusicClient"] = [("晴天", "周杰伦", "0:03", "flac")]
    r = M.switch_song_source(cid, sources=SRC, work_dir=str(SHARD),
                             current_source="NeteaseMusicClient")
    ck("C1 换成成功：回报新平台、分数与行数据",
       r["ok"] and r["to"] == "QQ" and r["score"] >= M.MATCH_ACCEPT
       and r["row"]["quality"] == "flac", r)
    ck("C2 换成功后缓存里这一行已是新平台那条（下载时用的就是它）",
       M.get_cached_song(cid) is not orig
       and M.get_cached_song(cid).source == "QQMusicClient")
    ck("C3 行 id 不变：没有另铸一份缓存（否则界面上勾不上、下载会「缓存失效」）",
       M.get_cached_song(cid) is not None and r["row"].get("id", cid) == cid, r["row"])
    ck("C4 探测打的是换到的新地址，只打一次",
       [c for c in CALLS if c.startswith("probe|")]
       == [f"probe|{M.get_cached_song(cid).download_url}"], CALLS)
    ck("C5 新来路的行数据带 source/musicdl_source/时长/封面，界面才改得动",
       r["row"]["source"] == "QQ" and r["row"]["musicdl_source"] == "QQMusicClient"
       and r["row"]["duration"] == "0:03" and r["row"]["cover"].startswith("https"), r["row"])

    CALLS.clear()
    cid2 = M._cache_song(Song("天地between", "某歌手", source="NeteaseMusicClient"))
    POOL["QQMusicClient"] = [("完全另一首", "某歌手", "0:03", "mp3")]
    keep2 = M.get_cached_song(cid2)
    r2_ = M.switch_song_source(cid2, sources=SRC, work_dir=str(SHARD),
                               current_source="NeteaseMusicClient")
    ck("C6 反向验证：闸门没放过就不算换成，reason 说得出被哪一维挡",
       not r2_["ok"] and "没换成" not in r2_["reason"] and r2_["reason"], r2_)
    ck("C7 换不成时缓存保持原样（清单不会被改成另一首歌）",
       M.get_cached_song(cid2) is keep2)

    POOL["QQMusicClient"] = [("晴天", "周杰伦", "9:00", "mp3")]
    r3_ = M.switch_song_source(M._cache_song(Song("晴天", "周杰伦", source="NeteaseMusicClient")),
                               sources=SRC, work_dir=str(SHARD),
                               current_source="NeteaseMusicClient")
    ck("C8 同名同歌手但时长差得远 → 闸门按时长挡下，reason 里写明时长",
       not r3_["ok"] and ("时长" in r3_["reason"] or "秒" in r3_["reason"]), r3_["reason"])

    CALLS.clear()
    r4_ = M.switch_song_source(M._cache_song(Song("晴天", "周杰伦", source="NeteaseMusicClient")),
                               sources=["NeteaseMusicClient"], work_dir=str(SHARD),
                               current_source="NeteaseMusicClient")
    ck("C9 候选源里只剩当前这一个：直接回不能换，一次搜索都不发起",
       not r4_["ok"] and "没有可换的源" in r4_["reason"] and not CALLS, (r4_, CALLS))
    POOL["QQMusicClient"] = [("晴天", "周杰伦", "0:03", "flac")]
    ck("C10 排除当前源认得短名写法（界面传来的 source 列就是短名）",
       M.switch_song_source(M._cache_song(Song("晴天", "周杰伦")),
                            sources=["NeteaseMusicClient", "QQMusicClient"],
                            work_dir=str(SHARD), current_source="Netease")["ok"])

    POOL["QQMusicClient"] = []
    r5_ = M.switch_song_source("不存在的id", sources=SRC, work_dir=str(SHARD))
    ck("C11 缓存里查不到的行回明原因，不抛异常",
       not r5_["ok"] and "缓存里查不到" in r5_["reason"], r5_)
finally:
    M._search_one_source, M.range_probe = _real_search, _real_probe

# ------------------------------------------------------- D. 接口接线（不碰真实配置）
print("=== D. POST /api/music/switch_source：挡参照行、取匹配源、逐首回结论 ===")
import server as S  # noqa: E402

_real_cfg, _real_log, _real_resolver = S.cfg, S.log_mgr.log, S.music_proxy_resolver
_real_switch = M.switch_song_source
SEEN: list[dict] = []
SLOG: list[str] = []


class _Cfg:
    def __init__(self, data):
        self.data = data

    def save(self):
        raise AssertionError("换源不该写配置")


try:
    S.cfg = _Cfg({"download_dir": str(DL), "musicdl_cookies": "",
                  "musicdl_strategy": {"match_sources": ["NeteaseMusicClient", "QQMusicClient"]},
                  "musicdl_sources": ["NeteaseMusicClient"]})
    S.log_mgr.log = lambda m, lv="info", k="", kv=None: SLOG.append(f"[{lv}] {m}")
    S.music_proxy_resolver = lambda _p: (lambda _s: "")

    def stub_switch(cid, **kw):
        SEEN.append({"cid": cid, **kw})
        return {"ok": True, "from": "Netease", "to": "QQ", "score": 96, "id": cid,
                "title": "晴天", "row": {"title": "晴天", "source": "QQ"}}

    M.switch_song_source = stub_switch
    ok_cid = M._cache_song(Song("晴天", "周杰伦", source="NeteaseMusicClient"))
    out = S.api_music_switch_source({"ids": [ok_cid]})
    ck("D1 接口通了：逐行回结论，counts 对得上",
       out["ok"] and out["switched"] == 1 and out["results"][0]["to"] == "QQ", out)
    ck("D2 匹配源按 本次请求 → 策略里存的 → 搜索源 取（这里用了策略存的两个）",
       SEEN[-1]["sources"] == ["NeteaseMusicClient", "QQMusicClient"], SEEN[-1]["sources"])
    ck("D3 当前平台从行上的 musicdl_source 读出来传下去（好排除它）",
       SEEN[-1]["current_source"] == "NeteaseMusicClient", SEEN[-1]["current_source"])
    ck("D4 换源不写下载目录、也不落 config",
   not any(p.name.startswith("local_music_index") for p in DL.rglob("*")))
    ck("D5 逐首结论进了运行日志（写明换成哪个源、判定多少分）",
       any("换源「晴天」" in m and "QQ" in m and "96 分" in m for m in SLOG), SLOG[-1:])

    SEEN.clear()
    for bad, key in (("ref:qobuz:123", "无损参照"), ("local:C:\\x\\a.mp3", "本地成品")):
        try:
            S.api_music_switch_source({"ids": [bad]})
            ck(f"D6 {key}那一行被挡在接口外", False, "没抛 400")
        except S.HTTPException as e:
            ck(f"D6 {key}那一行被挡在接口外（不进换源逻辑）",
               e.status_code == 400 and "不能换源" in e.detail and not SEEN, e.detail)

    try:
        S.api_music_switch_source({"ids": []})
        ck("D7 一行都没给时报 400", False)
    except S.HTTPException as e:
        ck("D7 一行都没给时报 400", e.status_code == 400, e.detail)
    try:
        S.api_music_switch_source({"ids": [ok_cid], "sources": ["NeteaseMusicClient"]})
        ck("D8 显式只给一个源时照样往下走（由换源逻辑判「只剩当前源」）",
           SEEN and SEEN[-1]["sources"] == ["NeteaseMusicClient"], SEEN[-1:])
    except S.HTTPException as e:
        ck("D8 显式只给一个源时照样往下走（由换源逻辑判「只剩当前源」）", False, e.detail)

    SEEN.clear()

    def failing(cid, **kw):
        return {"ok": False, "reason": "其他源里没有过闸门的结果：曲名对不上", "id": cid,
                "title": "晴天", "to": ""}

    M.switch_song_source = failing
    out2 = S.api_music_switch_source({"id": ok_cid})
    ck("D9 换不成：接口 200 返回、switched 为 0，reason 原样带回界面",
       out2["ok"] is False and out2["switched"] == 0 and out2["count"] == 1
       and "过闸门" in out2["results"][0]["reason"], out2)
    ck("D10 换不成也写日志（用 warning，界面那行要标红）",
       any(m.startswith("[warning]") and "没换成" in m for m in SLOG), SLOG[-1:])
    ck("D11 单个 id 的写法（body.id）也认，不必非传数组", out2["count"] == 1, out2)
finally:
    S.cfg, S.music_proxy_resolver = _real_cfg, _real_resolver
    S.log_mgr.log = _real_log
    M.switch_song_source = _real_switch

shutil.rmtree(SHARD, ignore_errors=True)
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
