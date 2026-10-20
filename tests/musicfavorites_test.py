r"""自建音乐收藏清单自检（⑤ / #138）。

三件事要钉住：
1. 清单行按「曲名+歌手+时长」的稳定 id 认歌 —— 同一首歌从网易云和从 QQ 音乐各收一次，只能有一行；
2. 每行的缓存槽位是「这一轮能不能直接下」的唯一凭据：加进来时把缓存里那条真结果搬进槽位，
   整单下载就原样下；槽位空了才立「只有曲名」的占位交给匹配轮 —— 已经有真结果的槽位绝对不许被覆盖；
3. 失效标记只认下载流程回填的结论，并且只动这一批的行；
4. 无损参照行（ref:）与本地成品行（local:）在加入时就拒收 —— 这一单承诺「能整单下」，
   收进来也下不动的行不该混在里面。

全程离线：music_favorites.json 落在 %TEMP%，api_music_download 用桩顶掉（真函数会起线程、碰 musicdl），
本机 web_app 目录做快照 diff，断言没在工具文件夹里落下任何产物。

跑法：`python tests/musicfavorites_test.py`
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import time

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import music_search as M  # noqa: E402
import server as S  # noqa: E402

FAILED: list[str] = []
LOGS: list[str] = []
ROOT = pathlib.Path(shutil.os.environ.get("TEMP", "C:\\tmp")) / "md_musicfavorites_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)
FAVS = SHARD / "music_favorites.json"

ORIG = {"favs_file": S.MUSIC_FAVS_FILE, "log_mgr": S.log_mgr, "dl": S.api_music_download,
        "cache": dict(M._SONG_CACHE)}


def snapshot():
    """工具文件夹顶层 + 下载目录顶层的条目名：收尾要证明这轮没往本机目录落新文件。"""
    out = {str(p.name) for p in APP.glob("*")}
    dl = APP / "Downloads"
    if dl.is_dir():
        out |= {"Downloads/" + p.name for p in dl.glob("*")}
    return out


SNAP_BEFORE = snapshot()
LOG_MARK_BEFORE = (S.LOG_FILE.read_text(encoding="utf-8", errors="ignore")
                   if S.LOG_FILE.exists() else "").count("收藏清单")


def ck(name, cond, got=""):
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not ok:
        FAILED.append(name)


class FakeLogMgr:
    def log(self, msg, level="info", k="", kv=None):
        LOGS.append(f"[{level}] {msg}")


def http_error(fn, *a, **kw):
    from fastapi import HTTPException
    try:
        return 200, fn(*a, **kw)
    except HTTPException as e:
        return e.status_code, e.detail


def restore():
    S.MUSIC_FAVS_FILE = ORIG["favs_file"]
    S.log_mgr = ORIG["log_mgr"]
    S.api_music_download = ORIG["dl"]
    S._MUSIC_JOB.pop("running", None)
    M._SONG_CACHE.clear()
    M._SONG_CACHE.update(ORIG["cache"])


def reset_cache():
    M._SONG_CACHE.clear()


class Song:
    """桩只带这一轮真用到的字段，不许比真 SongInfo 宽。"""

    def __init__(self, name, artists="某歌手", source="NeteaseMusicClient",
                 duration="3:22", ext="flac", url=""):
        self.song_name = name
        self.singers = artists
        self.source = source
        self.duration = duration
        self.ext = ext
        self.album = "某专辑"
        self.cover_url = "https://img.example/c.jpg"
        self.download_url = url or f"https://audio.example/{name}.{ext}"


def put(song: Song) -> str:
    """把一条真结果塞进 musicdl 的搜索结果缓存，返回它的缓存 id。"""
    return M._cache_song(song)


# 下载入口的桩：只记录拿到什么，返回一个像样的回执
DL_CALLS: list = []


def fake_download(body: dict):
    DL_CALLS.append(dict(body))
    return {"ok": True, "mode": "musicdl", "message": "桩：已开始", "already": 0}


S.MUSIC_FAVS_FILE = FAVS
S.log_mgr = FakeLogMgr()
S.api_music_download = fake_download


def rows_of(items=None):
    data = json.loads(FAVS.read_text(encoding="utf-8")) if FAVS.exists() else {"items": []}
    return data["items"] if items is None else items


# ---------------------------------------------------------------- A. 收成清单条目
print("=== A. _music_fav_row：一行结果收成一条清单 ===")
rowA = {"id": put(Song("晴天", "周杰伦")), "title": "晴天", "artists": "周杰伦",
        "duration": "3:22", "duration_s": 202, "album": "八度空间", "source": "Netease",
        "musicdl_source": "NeteaseMusicClient", "url": "https://audio.example/晴天.flac",
        "quality": "flac", "cover": "https://img.example/c.jpg"}
favA = S._music_fav_row(rowA)
ck("A1 稳定 id 用「曲名+歌手+时长」，与追新游标同一套口径",
   favA["id"] == S._music_entry_id("晴天", "周杰伦", 202), favA.get("id"))
ck("A2 曲名/歌手/时长/专辑/品质照抄", all(
   favA[k] == v for k, v in (("title", "晴天"), ("artists", "周杰伦"), ("duration", "3:22"),
                             ("duration_s", 202), ("album", "八度空间"), ("quality", "flac"))), favA)
ck("A3 来源简称与 musicdl 源名都存下来",
   favA["source"] == "Netease" and favA["musicdl_source"] == "NeteaseMusicClient", favA)
favShort = S._music_fav_row(dict(rowA, musicdl_source="QQ"))
ck("A4 源名缺 Client 后缀就补上", favShort["musicdl_source"] == "QQMusicClient", favShort)
ck("A5 时长认 3:22 也认秒数", S._music_fav_row({"title": "x", "artists": "y",
                                                "duration": "202"})["duration_s"] == 202)
ck("A6 没曲名的行收不进来（存进去也找不回去）", S._music_fav_row({"artists": "无人"}) == {})
ck("A7 空格/多余空白归一：同一首歌写法不同不会铸出两个 id",
   S._music_fav_row({"title": " 晴天 ", "artists": "周杰伦 ", "duration_s": 202})["id"]
   == S._music_fav_row({"title": "晴天", "artists": "周杰伦", "duration_s": 202})["id"])
ck("A8 跨源同曲是同一个 id（网易云一行、QQ 一行也只该存一遍）",
   S._music_fav_row(dict(rowA, source="QQ", musicdl_source="QQMusicClient"))["id"] == favA["id"])
ck("A9 新行自带空槽位、加入时间、空状态",
   favA["slot"] == "" and len(favA["added_at"]) == 16 and favA["state"] == "", favA["added_at"])
favSp = S._music_fav_row({"title": "Song of 故鄉", "artists": ["张三", "李四"], "duration_s": 60})
ck("A10 歌手是列表时按逗号拼（与打分闸门同口径）", favSp["artists"] == "张三, 李四", favSp)

# ---------------------------------------------------------------- B. 落盘
print("=== B. 读写 music_favorites.json ===")
ck("B1 文件还没写过时读到空清单", S._music_favs_load() == [])
S._music_favs_save([{"id": "mus:a|b|1", "title": "a"}, {"id": ""}, "不是字典", {"title": "没 id"}])
ck("B2 存进去能原样读回来", len(S._music_favs_load()) == 1, S._music_favs_load())
ck("B3 没有稳定 id 的行读的时候一律丢掉（后面按 id 删/下载都靠它）",
   S._music_favs_load()[0]["id"] == "mus:a|b|1")
FAVS.write_text("{这不是 json", encoding="utf-8")
ck("B4 文件坏了当空清单，不炸接口", S._music_favs_load() == [])
FAVS.write_text(json.dumps([{"id": "mus:x|y|1", "title": "旧格式"}]), encoding="utf-8")
ck("B5 裸列表的旧形状也认", [i["title"] for i in S._music_favs_load()] == ["旧格式"])
FAVS.unlink()

# ---------------------------------------------------------------- C. 加入
print("=== C. 加入清单：重复只算一次，槽位认这一轮的真结果 ===")
reset_cache()
idA = put(Song("海阔天空", "Beyond"))
idB = put(Song("和平饭店", "某人"))
rows = [
    {"id": idA, "title": "海阔天空", "artists": "Beyond", "duration": "5:23", "duration_s": 323,
     "source": "Netease", "musicdl_source": "NeteaseMusicClient", "url": "https://a/1.flac"},
    {"id": idB, "title": "和平饭店", "artists": "某人", "duration": "3:22", "duration_s": 202,
     "source": "QQ", "musicdl_source": "QQMusicClient", "url": "https://a/2.mp3"},
    # 同一首歌换个平台再收一次：稳定 id 一样，不该进第二行
    {"id": put(Song("海阔天空", "Beyond", source="QQMusicClient")), "title": "海阔天空",
     "artists": "Beyond", "duration": "5:23", "duration_s": 323, "source": "QQ",
     "musicdl_source": "QQMusicClient", "url": "https://a/1.flac"},
    {"id": "ref:qobuz:9", "title": "只读元数据的参照行", "artists": "某人", "duration_s": 60},
    {"id": "local:c:/x.flac", "title": "磁盘上已有的成品", "artists": "某人", "duration_s": 61},
    {"title": "", "artists": "没曲名"},
]
code, got = http_error(S.api_music_favorites_add, {"rows": rows})
ck("C1 接口 200 且只收下没存过的", code == 200 and got["added"] == 2, got)
ck("C2 跨源重复的那一行被跳过并计数", got["duplicated"] == 1, got)
ck("C3 没曲名的行单独报数，不混进重复里", got["no_title"] == 1, got)
ck("C3b 参照行与本地成品单独拒收（这一单要能下，收进来也下不动）",
   got["refused"] == 2, got)
ck("C4 清单落在 TEMP 且只有两行", len(rows_of()) == 2 and got["total"] == 2, rows_of())
saved = rows_of()
ck("C5 每行都铸了互不相同的槽位", len({s["slot"] for s in saved}) == 2
   and all(len(s["slot"]) == 36 for s in saved), [s["slot"] for s in saved])
ck("C6 加入这一轮的真结果搬进了槽位（整单下载能直接下）",
   S._music_fav_state(saved[0]) == "ready", S._music_fav_state(saved[0]))
ck("C7 槽位里就是缓存里那一个对象，不是复制品",
   M.get_cached_song(saved[0]["slot"]) is M.get_cached_song(idA))
ck("C8 参照行与本地成品一行都没进清单（两条真结果各自能直接下）",
   [i["title"] for i in saved] == ["海阔天空", "和平饭店"]
   and all(S._music_fav_state(s) == "ready" for s in saved), saved)
ck("C9 记了加入时间", len(saved[0]["added_at"]) == 16, saved[0]["added_at"])
ck("C10 日志写了加入几首，没写地址",
   any("收藏清单加入 2 首" in m for m in LOGS) and not any("https://" in m for m in LOGS), LOGS[-2:])
ck("C10b 拒收的那两行在日志里说清为什么",
   any("2 行是无损参照或本地成品" in m for m in LOGS), LOGS[-1:])
LOGS.clear()
code, got2 = http_error(S.api_music_favorites_add, {"rows": rows[:2]})
ck("C11 全部已存在时 added=0 且不重复落盘", code == 200 and got2["added"] == 0
   and got2["duplicated"] == 2 and len(rows_of()) == 2, got2)
ck("C12 跳过的重复要报出来，不能说成「都收下了」",
   any("跳过 2 首" in m for m in LOGS), LOGS)
LOGS.clear()
code, got3 = http_error(S.api_music_favorites_add, {"row": rows[1]})
ck("C13 也接受单行（row 传一个字典）", code == 200 and got3["duplicated"] == 1, got3)
reset_cache()
ck("C14 反向验证：缓存一清空，同一行的读数立刻变 pending",
   S._music_fav_state(rows_of()[0]) == "pending", S._music_fav_state(rows_of()[0]))

# ---------------------------------------------------------------- D. 列表读数
print("=== D. 清单读数与换源后的刷新 ===")
put(Song("海阔天空", "Beyond", source="QQMusicClient", url="https://b/qq.flac"))
code, lst = http_error(S.api_music_favorites_list)
ck("D1 列表 200 并带 count", code == 200 and lst["count"] == 2, lst.get("count"))
ck("D2 每行带 resolved 实时读数", {i["resolved"] for i in lst["items"]} == {"pending"},
   [i["resolved"] for i in lst["items"]])
slotA = lst["items"][0]["slot"]
M.set_cached_song(slotA, Song("海阔天空", "Beyond", source="QQMusicClient",
                              duration="5:23", url="https://b/qq.flac"))
code, lst2 = http_error(S.api_music_favorites_list)
rowQ = lst2["items"][0]
ck("D3 槽位换成真结果后读数变 ready", rowQ["resolved"] == "ready", rowQ["resolved"])
ck("D4 来源跟着换成新平台（换源之后清单不能还写着老平台）",
   rowQ["source"] == "QQMusic" or rowQ["source"] == "QQ", rowQ["source"])
ck("D5 musicdl 源名一并刷新", rowQ["musicdl_source"] == "QQMusicClient", rowQ["musicdl_source"])
ck("D6 音频地址换成新那条", rowQ["url"] == "https://b/qq.flac", rowQ["url"])
ck("D7 刷新结果落进文件（重启后看的还是换到的那条）",
   rows_of()[0]["musicdl_source"] == "QQMusicClient", rows_of()[0]["musicdl_source"])
code, lst3 = http_error(S.api_music_favorites_list)
ck("D8 没有变化时不反复改写文件",
   lst3["items"][0]["musicdl_source"] == "QQMusicClient" and FAVS.exists())
LOGS.clear()
code, lst4 = http_error(S.api_music_favorites_list)
ck("D9 清单里没失效行时 missing 计数为 0", code == 200 and lst4["missing"] == 0, lst4["missing"])

# ---------------------------------------------------------------- E. 删除
print("=== E. 删行 / 清空 ===")
id_first = rows_of()[0]["id"]
code, got = http_error(S.api_music_favorites_remove, {"ids": [id_first]})
ck("E1 按稳定 id 删掉一行", code == 200 and got["removed"] == 1 and got["total"] == 1, got)
ck("E2 文件里确实少了那行", len(rows_of()) == 1 and rows_of()[0]["id"] != id_first, rows_of())
ck("E3 日志记了删除与剩余", any("删除 1 首" in m and "还剩 1" in m for m in LOGS), LOGS[-1:])
code, got = http_error(S.api_music_favorites_remove, {"ids": []})
ck("E4 没给 id 当场 400，不会误删整单", code == 400, (code, got))
code, got = http_error(S.api_music_favorites_remove, {"ids": ["mus:查无此行|无人|0"]})
ck("E5 清单里没有的行报 404，文件不动", code == 404 and len(rows_of()) == 1, (code, got))

# ---------------------------------------------------------------- F. 整单下载
print("=== F. 整单下载：槽位活着直接下，空了才立占位 ===")
reset_cache()
DL_CALLS.clear()
item0 = rows_of()[0]
live = Song("和平饭店", "某人", source="QQMusicClient")
M.set_cached_song(item0["slot"], live)
code, res = http_error(S.api_music_favorites_download, {})
ck("F1 不带 ids 就是整单", code == 200 and res["fav_total"] == 1, (code, res))
ck("F2 把槽位当缓存 id 交给音乐页那套流程", DL_CALLS[-1]["ids"] == [item0["slot"]], DL_CALLS[-1])
ck("F3 回执带 reminted / slots 供界面核对", res["reminted"] == 0 and res["slots"] == [item0["slot"]], res)
ck("F4 反向验证：槽位里已有真结果，绝不被占位覆盖（否则下的是重新搜的别版录音）",
   M.get_cached_song(item0["slot"]) is live)
ck("F5 日志说明开始下几首", any("收藏清单开始下载 1 首" in m for m in LOGS), LOGS[-1:])

LOGS.clear()
DL_CALLS.clear()
# 槽位空掉（等价于重启过一次）：这一首要立「只有曲名」的占位，交给匹配轮
SLOT_DEAD = item0["slot"]
M._SONG_CACHE.pop(SLOT_DEAD, None)
code, res = http_error(S.api_music_favorites_download, {})
ph = M.get_cached_song(SLOT_DEAD)
ck("F6 槽位空了才补占位，并计入 reminted", code == 200 and res["reminted"] == 1, res)
ck("F7 占位带曲名/歌手/时长且标了待匹配",
   isinstance(ph, dict) and ph["title"] == item0["title"] and ph["artists"] == item0["artists"]
   and ph["duration_s"] == item0["duration_s"] and ph["needs_match"] is True, ph)
ck("F8 日志写明有几首要重新找地址", any("1 首要先按曲名重新找地址" in m for m in LOGS), LOGS[-1:])
ck("F9 界面传的参数原样转给下载入口（匹配源/跳过已有/临时 Cookie/代理）",
   DL_CALLS[-1]["match_sources"] == [] and DL_CALLS[-1]["skip_downloaded"] is None, DL_CALLS[-1])
code, res = http_error(S.api_music_favorites_download,
                       {"match_sources": ["NeteaseMusicClient"], "skip_downloaded": False,
                        "block_reupload": True,
                        "cookies": "X=1", "proxy": "http://127.0.0.1:9999"})
ck("F10 match_sources 与 skip_downloaded 会覆盖到这一次请求",
   DL_CALLS[-1]["match_sources"] == ["NeteaseMusicClient"]
   and DL_CALLS[-1]["skip_downloaded"] is False and DL_CALLS[-1]["cookies"] == "X=1", DL_CALLS[-1])
ck("F10b 拦搬运版这项也照传（跟音乐页其它下载同一个开关）",
   DL_CALLS[-1]["block_reupload"] is True, DL_CALLS[-1])
code, res = http_error(S.api_music_favorites_download, {"ids": ["mus:不在清单|无人|0"]})
ck("F11 勾到的行已经被删掉时报 400，不下别人的歌", code == 400 and "不在清单" in str(res), (code, res))
S._MUSIC_JOB["running"] = True
code, res = http_error(S.api_music_favorites_download, {})
ck("F12 上一批还没跑完就 409（音乐批量只有一条通道）", code == 409 and "还没结束" in str(res), (code, res))
S._MUSIC_JOB.pop("running", None)
DL_CALLS.clear()
S._music_favs_save([])
code, res = http_error(S.api_music_favorites_download, {})
ck("F13 空清单当场 400，不起线程", code == 400 and not DL_CALLS, (code, res))
S._music_favs_save([{"id": "mus:甲|A|60", "title": "甲", "artists": "A", "duration_s": 60,
                     "slot": "slot-1", "state": ""},
                    {"id": "mus:乙|B|61", "title": "乙", "artists": "B", "duration_s": 61,
                     "slot": "slot-2", "state": ""}])
code, res = http_error(S.api_music_favorites_download, {"ids": ["mus:乙|B|61"]})
ck("F14 勾选下载只交勾选那几行的槽位", code == 200 and res["fav_total"] == 1
   and DL_CALLS[-1]["ids"] == ["slot-2"], DL_CALLS[-1])
ck("F15 补的占位用的是这一行自己存的曲名歌手", M.get_cached_song("slot-2")["title"] == "乙",
   M.get_cached_song("slot-2"))
ck("F16 没勾到的那行槽位保持空的（没被顺手占上）", M.get_cached_song("slot-1") is None)

# 歌单里只列出曲名的行（Spotify / Apple）：缓存里本来就是一份「只有曲名」的占位
reset_cache()
S._music_favs_save([])
DL_CALLS.clear()
ph_id = M._cache_song({"title": "夜曲", "artists": "周杰伦", "duration_s": 222,
                       "duration": "3:42", "needs_match": True})
code, got = http_error(S.api_music_favorites_add, {"rows": [
    {"id": ph_id, "title": "夜曲", "artists": "周杰伦", "duration": "3:42", "duration_s": 222,
     "source": "Spotify", "musicdl_source": "SpotifyMusicClient", "url": "", "needs_match": True}]})
phFav = rows_of()[0]
ck("F17 只列曲名的行也收得进来（Spotify 歌单攒成一单正是这一单要干的）",
   code == 200 and got["added"] == 1 and phFav["url"] == "", (got, phFav))
ck("F18 槽位里就是那份占位，读数是 pending 而不是 ready",
   M.get_cached_song(phFav["slot"]) is M.get_cached_song(ph_id)
   and S._music_fav_state(phFav) == "pending", S._music_fav_state(phFav))
code, res = http_error(S.api_music_favorites_download, {})
still = M.get_cached_song(phFav["slot"])
ck("F19 下载时不再另立占位（歌单标注的时长要留给匹配轮当基准）",
   code == 200 and res["reminted"] == 0 and isinstance(still, dict)
   and still["duration_s"] == 222 and still["needs_match"] is True, (res, still))
ck("F20 交给下载入口的仍是这一行的槽位", DL_CALLS[-1]["ids"] == [phFav["slot"]], DL_CALLS[-1])
S._music_favs_save([{"id": "mus:甲|A|60", "title": "甲", "artists": "A", "duration_s": 60,
                     "slot": "slot-1", "state": ""},
                    {"id": "mus:乙|B|61", "title": "乙", "artists": "B", "duration_s": 61,
                     "slot": "slot-2", "state": ""}])

# ---------------------------------------------------------------- G. 失效标记
print("=== G. 下载结论回填失效标记 ===")
LOGS.clear()
code, got = http_error(S.api_music_favorites_mark, {"missed": ["乙"], "unsearched": ["甲"]})
ck("G1 回填 200 并统计改动", code == 200 and got["changed"] == 2, (code, got))
items = rows_of()
ck("G2 没找到的标 missing 并写清下一步", items[1]["state"] == "missing"
   and "换个源" in items[1]["note"], items[1])
ck("G3 整轮超时没轮到搜的另标一档（不是没找到）", items[0]["state"] == "unsearched"
   and "没轮到" in items[0]["note"], items[0])
ck("G4 失效计数进列表读数", S.api_music_favorites_list()["missing"] == 1)
ck("G5 日志提醒有几行标着失效", any("标着失效 1 行" in m for m in LOGS), LOGS[-1:])
code, got = http_error(S.api_music_favorites_mark, {"slots": ["slot-1"], "missed": ["甲"]})
items = rows_of()
ck("G6 带 slots 范围时只动这一批的行", code == 200 and got["changed"] == 1
   and items[1]["state"] == "missing", got)
ck("G7 范围里的行按新结论改写（slot-1 从 unsearched 变 missing）",
   items[0]["state"] == "missing", items[0])
code, got = http_error(S.api_music_favorites_mark, {"missed": []})
items = rows_of()
ck("G8 再下一遍都找到了就把标记清掉", got["changed"] == 2 and items[0]["state"] == ""
   and items[1]["state"] == "", items)
ck("G9 清掉标记时备注也一并清掉", items[0]["note"] == "" and items[1]["note"] == "")
code, got = http_error(S.api_music_favorites_mark, {})
ck("G10 空结论等于「全部正常」，不改动就不写文件", code == 200 and got["changed"] == 0, got)
ck("G11 反向验证：曲名对不上的行不会被误标（结论按曲名回表）",
   S.api_music_favorites_mark({"missed": ["根本没有这首歌"]})["changed"] == 0)

# ---------------------------------------------------------------- H. 收尾
print("=== H. 本机目录没被写过 ===")
ck("H1 清单文件只写在 TEMP", FAVS.exists() and "musicfavorites_test" in str(FAVS))
ck("H2 桩没被拆掉前接口仍可用", S.api_music_favorites_list()["count"] == 2)
restore()
ck("H3 真接口的下载入口已还原（不是桩）", S.api_music_download is not fake_download)
ck("H4 还原后清单路径回到本机 APP_DIR", S.MUSIC_FAVS_FILE.name == "music_favorites.json"
   and str(S.MUSIC_FAVS_FILE).startswith(str(APP)), S.MUSIC_FAVS_FILE)
_log_now = (S.LOG_FILE.read_text(encoding="utf-8", errors="ignore")
            if S.LOG_FILE.exists() else "").count("收藏清单")
ck("H5 本轮没往运行日志文件里写收藏清单相关行", _log_now == LOG_MARK_BEFORE,
   f"基线 {LOG_MARK_BEFORE} 次 → 现在 {_log_now} 次")
SNAP_AFTER = snapshot()
extra = sorted(SNAP_AFTER - SNAP_BEFORE)
ck("H6 工具文件夹与 Downloads 顶层没多出任何新文件（清单只在 TEMP）", not extra, extra[:6])
shutil.rmtree(SHARD, ignore_errors=True)

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
