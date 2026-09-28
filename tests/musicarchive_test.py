r"""Emby / Jellyfin 归档口径自检（⑥ / #139）。

要钉住四件事：
1. 命名模板多出 {track} {disc} {year} {date} 四个字段，序号补零（Emby 按文件名排序，不补零是 1、10、11、2）；
2. 平台没给这些字段时**留空**：整段空掉的目录不建、文件名行首行尾孤零零的「- 」削掉、
   打错的占位符丢掉 —— 三条都是为了不写出 `{track} - 晴天.mp3` 这种名字；
3. 歌单行的序号在解析时就盖好（列表位置），平台自己给了碟片序号的行不覆盖；
   占位行匹配成功换成真结果时，序号要跟着搬过去，否则收尾重命名读不到号；
4. server.py 那一处调用点给的参数名，必须是 format_music_path 收得下的（拼错了不会报错，只会静默不下号）。

全程离线：只在 %TEMP% 下算路径，不建文件、不碰 musicdl 网络，
收尾用目录快照 diff 证明没往工具文件夹和 Downloads 落任何东西。

跑法：`python tests/musicarchive_test.py`
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import shutil
import sys
import time

APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import music_search as M  # noqa: E402

FAILED: list[str] = []
ROOT = pathlib.Path(shutil.os.environ.get("TEMP", "C:\\tmp")) / "md_musicarchive_test"
SHARD = ROOT / time.strftime("%H%M%S")
SHARD.mkdir(parents=True, exist_ok=True)


def ck(name, cond, got=""):
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not ok:
        FAILED.append(name)


def snapshot():
    out = {str(p.name) for p in APP.glob("*")}
    dl = APP / "Downloads"
    if dl.is_dir():
        out |= {"Downloads/" + p.name for p in dl.glob("*")}
    return out


SNAP_BEFORE = snapshot()


class Obj:
    """占位 dict 之外的另一种行：真结果对象（只带这一轮用到的字段）。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


# ---------------------------------------------------------------- A. 补零 / 取值
print("=== A. _pad_num / _num_prefix / _norm_date ===")
ck("A1 个位补成两位", M._pad_num(1) == "01" and M._pad_num("9") == "09", M._pad_num(9))
ck("A2 两位不补", M._pad_num(10) == "10" and M._pad_num("23") == "23")
ck("A3 三位以上按三位（一张碟不会超过 99 首，但跨年合辑会）", M._pad_num(100) == "100", M._pad_num(100))
ck("A4 带汉字的序号取数字前缀", M._pad_num("第12首") == "12", M._pad_num("第12首"))
ck("A5 没有数字就不编造", M._pad_num("") == "" and M._pad_num(None) == "" and M._pad_num("无") == "")
ck("A6 _num_prefix 取第一段数字", M._num_prefix("CD2 12") == "2" and M._num_prefix("7") == "7")
ck("A7 日期：ISO / 点分 / 紧凑 都归成 YYYY-MM-DD",
   M._norm_date("2005-01-01") == "2005-01-01" and M._norm_date("2005.1.1") == "2005-01-01"
   and M._norm_date("20050101") == "2005-01-01",
   [M._norm_date("2005.1.1"), M._norm_date("20050101")])
ck("A7b 日期：汉字写法与斜杠", M._norm_date("2005年1月1日") == "2005-01-01"
   and M._norm_date("2005/3/7") == "2005-03-07", M._norm_date("2005/3/7"))
ck("A7c 日期：只给到月份就按年月（网易云不少条目只到这个精度）",
   M._norm_date("2005-11") == "2005-11", M._norm_date("2005-11"))
ck("A7d 日期：8 位数字但月/日离谱的不硬凑", M._norm_date("20051301") == "", M._norm_date("20051301"))
ck("A8 日期：毫秒时间戳（网易云 album.publishTime 就是它）",
   M._norm_date(1104537600000) == "2005-01-01", M._norm_date(1104537600000))
ck("A9 日期：秒时间戳", M._norm_date("1104537600") == "2005-01-01", M._norm_date("1104537600"))
ck("A10 日期：只有年份就按年份", M._norm_date("2005年") == "2005", M._norm_date("2005年"))
ck("A11 日期：认不出来返回空，绝不写出怪目录名",
   M._norm_date("") == "" and M._norm_date("暂无") == "" and M._norm_date(None) == "")
ck("A12 反向验证：不是日期开头的数字串不会被当成 2005-01-01",
   M._norm_date("11045376000001") == "", M._norm_date("11045376000001"))

# ---------------------------------------------------------------- B. 从一行结果取归档字段
print("=== B. song_archive_meta：结果行 + raw_data 里的原始返回 ===")
ck("B1 行上直接有序号就用",
   M.song_archive_meta({"title": "x", "track_index": 7})["track"] == "7")
ck("B2 平台原始返回里的序号能挖到（QQ 把曲目号写在条目自己身上）",
   M.song_archive_meta(Obj(raw_data={"search": {"trackNumber": 5}}))["track"] == "5")
ck("B3 嵌一层也挖得到（网易云把发布日期写在 album.publishTime）",
   M.song_archive_meta(Obj(raw_data={"search": {"album": {"publishTime": 1104537600000}}})).get("date")
   == "2005-01-01")
ck("B4 年份跟着日期走",
   M.song_archive_meta(Obj(raw_data={"search": {"publish_time": "2018-03-02"}}))["year"] == "2018")
ck("B5 碟片号", M.song_archive_meta({"disc": "2"})["disc"] == "2")
ck("B6 值是 0 或空串当没有（平台常拿 0 占位）",
   M.song_archive_meta(Obj(raw_data={"search": {"track": 0, "disc": ""}}))
   == {"track": "", "disc": "", "year": "", "date": ""},
   M.song_archive_meta(Obj(raw_data={"search": {"track": 0, "disc": ""}})))
ck("B7 什么字段都没有 → 四个键全空，不报错",
   M.song_archive_meta(Obj(song_name="晴天")) == {"track": "", "disc": "", "year": "", "date": ""})
ck("B8 raw_data 形状不对也不会炸",
   M.song_archive_meta(Obj(raw_data="不是字典"))["track"] == "")
ck("B9 行上自带的序号优先于 raw_data（歌单位置就是用户看到的那个数）",
   M.song_archive_meta({"track_index": 3, "raw_data": {"search": {"track": 9}}})["track"] == "3")

# ---------------------------------------------------------------- C. 歌单盖序号
print("=== C. stamp_track_index：把「第几首」盖进行和真结果 ===")
try:
    from musicdl.modules.utils.data import SongInfo
    HAS_SONGINFO = True
except Exception as e:
    HAS_SONGINFO = False
    print(f"  (musicdl 不可用：{e})")

reset = dict(M._SONG_CACHE)
rows = []
ids = []
if HAS_SONGINFO:
    s1 = SongInfo(song_name="第一首")
    s2 = SongInfo(song_name="第二首", raw_data={"search": {"album": {"songs": [{"no": 0}]}, "track": 4}})
    s3 = SongInfo(song_name="第三首")
    for s in (s1, s2, s3):
        ids.append(M._cache_song(s))
    rows = [{"title": "第一首", "id": ids[0]}, {"title": "第二首", "id": ids[1]},
            {"title": "第三首", "id": ids[2]}, {"title": "没有缓存行"}]
    M.stamp_track_index(rows)
    ck("C1 普通行按列表位置盖号", rows[0]["track_index"] == "1" and rows[2]["track_index"] == "3",
       [r.get("track_index") for r in rows])
    ck("C2 号同时写进缓存里那条真结果（收尾重命名读的是它）",
       getattr(M.get_cached_song(ids[0]), "track_index", None) == 1,
       getattr(M.get_cached_song(ids[0]), "track_index", None))
    ck("C3 真结果是 musicdl 的 SongInfo，能挂上这个字段（不是 __slots__ 挡住的类）", HAS_SONGINFO)
    ck("C4 平台自己给了碟片序号的行不覆盖（那个号比列表位置可信）",
       "track_index" not in rows[1] and getattr(M.get_cached_song(ids[1]), "track_index", None) is None,
       rows[1])
    ck("C5 缓存查不到的行也照号盖（占位行就靠这个）", rows[3]["track_index"] == "4", rows[3])
    ck("C6 已经盖过的不重盖（合并重复曲目后再跑一次不跳号）",
       (M.stamp_track_index(rows), rows[0]["track_index"] == "1")[1])
    ck("C7 反向验证：不盖号的行确实取不到序号 —— 说明号是从这里来的，不是平台给的",
       M.song_archive_meta(Obj(song_name="裸行"))["track"] == "")
    rows[0].pop("track_index")
    _saved = M.get_cached_song(ids[0])
    try:
        delattr(_saved, "track_index")
    except Exception:
        pass
    ck("C8 反向验证：行和缓存都清干净后，同一行读数变空",
       M.song_archive_meta(M.get_cached_song(ids[0]))["track"] == "")
else:
    ck("C0 musicdl 的 SongInfo 可用（本机跑测试必须有）", False)

ph = {"title": "占位行", "needs_match": True}
pid = M._cache_song(ph)
prow = [{"title": "占位行", "id": pid}]
M.stamp_track_index(prow)
ck("C9 占位行（dict 进缓存）盖号不炸", prow[0]["track_index"] == "1", prow[0])
M._SONG_CACHE.clear()
M._SONG_CACHE.update(reset)

# ---------------------------------------------------------------- D. 匹配换真结果时带号
print("=== D. carry_archive_fields：占位换成真结果，号要跟着走 ===")
real = Obj(song_name="真结果")
M.carry_archive_fields({"track_index": "6", "disc": "2"}, real)
ck("D1 占位上的序号/碟片号搬到真结果", getattr(real, "track_index", None) == "6"
   and getattr(real, "disc", None) == "2", real.__dict__)
ck("D2 真结果自己有序号时不覆盖",
   (M.carry_archive_fields({"track_index": "9"}, real), getattr(real, "track_index", None) == "6")[1])
ck("D3 源不是 dict（真结果对真结果）时不动",
   M.carry_archive_fields(Obj(track_index="x"), real) is None and real.track_index == "6")
ck("D4 搬完之后归档读数拿得到号", M.song_archive_meta(real)["track"] == "6")
ck("D5 调用点确实接在换缓存之前（_resolve_placeholder 里）",
   "carry_archive_fields" in inspect.getsource(M._resolve_placeholder))

# ---------------------------------------------------------------- E. 渲染模板
print("=== E. format_music_path：占位取不到值时的收口 ===")
B = str(SHARD)
p = lambda tpl, **kw: M.format_music_path(tpl, base_dir=B, **kw).relative_to(B)
ck("E1 老模板一字不变（回归）",
   str(p("{artist}/{name} - {artist}", title="晴天", artists="周杰伦"))
   == str(pathlib.Path("周杰伦") / "晴天 - 周杰伦.mp3"), p("{artist}/{name} - {artist}", title="晴天", artists="周杰伦"))
ck("E2 {track} 补零", str(p("{track} - {name}", title="晴天", track=3)) == "03 - 晴天.mp3",
   p("{track} - {name}", title="晴天", track=3))
ck("E3 序号进目录也补零", str(p("{album}/{track}/{name}", title="晴天", album="八度空间", track="11"))
   == str(pathlib.Path("八度空间") / "11" / "晴天.mp3"))
ck("E4 取不到值的目录段整段消失（不落下空层也不写 Unknown）",
   str(p("{artist}/{year}/{name}", title="晴天", artists="周杰伦")) == str(pathlib.Path("周杰伦") / "晴天.mp3"),
   p("{artist}/{year}/{name}", title="晴天", artists="周杰伦"))
ck("E5 行首孤零零的连接符削掉", str(p("{track} - {name}", title="晴天")) == "晴天.mp3",
   p("{track} - {name}", title="晴天"))
ck("E6 行尾孤零零的连接符削掉", str(p("{name} - {track}", title="晴天")) == "晴天.mp3",
   p("{name} - {track}", title="晴天"))
ck("E7 整条模板都空 → 退回曲名，不会写出只剩扩展名的文件",
   str(p("{track}/{disc}", title="晴天")) == "晴天.mp3", p("{track}/{disc}", title="晴天"))
ck("E8 打错的占位符不会变成文件名里的花括号",
   str(p("{track_no} - {name}", title="晴天")) == "晴天.mp3", p("{track_no} - {name}", title="晴天"))
ck("E9 {year} 有日期就能算", str(p("{year}/{name}", title="晴天", date="2005-01-01"))
   == str(pathlib.Path("2005") / "晴天.mp3"))
ck("E10 {date} 直接用归一后的日期", str(p("{date} - {name}", title="晴天", date=1104537600000))
   == "2005-01-01 - 晴天.mp3", p("{date} - {name}", title="晴天", date=1104537600000))
ck("E11 {ext} 显式写出来时不重复附加",
   str(p("{name}.{ext}", title="晴天", ext="flac")) == "晴天.flac")
ck("E12 曲名里的分隔符与非法字符都被换掉（曲名不会越权建目录）",
   p("{name}", title="晴天/恶作:\\剧").as_posix() == "晴天_恶作__剧.mp3",
   p("{name}", title="晴天/恶作:\\剧").as_posix())
ck("E13 结果永远落在 base_dir 里面",
   str(p("..\\{name}", title="晴天")).startswith("..") is False
   and M.format_music_path("{name}", title="晴天", base_dir=B).is_relative_to(B))
ck("E14 默认模板（传空串）行为不变",
   str(p("", title="晴天", artists="周杰伦")) == "晴天 - 周杰伦.mp3", p("", title="晴天", artists="周杰伦"))

# 反向验证：{track} 走的确实是 _pad_num，而不是随手把值塞进文件名
_orig_pad = M._pad_num
M._pad_num = lambda v: str(v or "")
try:
    nowrap = str(p("{track} - {name}", title="晴天", track=3))
finally:
    M._pad_num = _orig_pad
ck("E15 反向验证：把补零换掉，同一模板读数是 3 而不是 03", nowrap == "3 - 晴天.mp3", nowrap)

# 反向验证：空段丢弃真的由 _tidy_segment/过滤负责
_orig_tidy = M._tidy_segment
M._tidy_segment = lambda s: str(s or "").strip()
try:
    dirty = str(p("{track} - {name}", title="晴天"))
finally:
    M._tidy_segment = _orig_tidy
ck("E16 反向验证：削连接符换掉后就会留下「- 晴天.mp3」", dirty == "- 晴天.mp3", dirty)

# ---------------------------------------------------------------- F. 参数对得上
print("=== F. server.py 的调用点拼错参数会被抓出来 ===")
srv = (APP / "server.py").read_text(encoding="utf-8", errors="ignore")
params = set(inspect.signature(M.format_music_path).parameters)
calls = [n for n in ast.walk(ast.parse(srv))
         if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "format_music_path"]
ck("F1 server.py 里只有一处调用（改口径不用到处找）", len(calls) == 1, len(calls))
if calls:
    kws = {k.arg for k in calls[0].keywords}
    ck("F2 调用点给的参数名 format_music_path 全收得下", kws <= params, sorted(kws - params))
    ck("F3 四个归档字段都传了", {"track", "disc", "year", "date"} <= kws, sorted(kws))
    ck("F4 base_dir 还在（不然成品落到进程工作目录）", "base_dir" in kws)
ck("F5 解析歌单收尾盖了序号", "stamp_track_index(items)" in inspect.getsource(M.parse_playlist))
ck("F6 序号补零只用 _pad_num 一处，模板与别处不会各写一套",
   sum(1 for ln in (APP / "music_search.py").read_text(encoding="utf-8", errors="ignore").splitlines()
       if "zfill" in ln) == 1)

# ---------------------------------------------------------------- G. 收尾
print("=== G. 本机目录没被写过 ===")
ck("G1 测试产物只在 TEMP", str(SHARD).startswith(str(ROOT)) and not any(
   (SHARD / n).exists() for n in ("晴天.mp3", "03 - 晴天.mp3")))
SNAP_AFTER = snapshot()
extra = sorted(SNAP_AFTER - SNAP_BEFORE)
ck("G2 工具文件夹与 Downloads 顶层没多出任何新文件", not extra, extra[:6])
shutil.rmtree(SHARD, ignore_errors=True)

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
