r"""按曲名匹配那一轮的三件事：预算按源分档、未完清单列全、落盘目录不许甩出下载目录。

全程不联网：搜索打桩，坏曲名用前导斜杠复现线上 musicdl 的死法，只读写 %TEMP%。
跑法：`python tests/matchround_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
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


OUT = Path(tempfile.mkdtemp(prefix="md_matchround_test_"))
DL = OUT / "dl"
DL.mkdir(parents=True)
CACHE = DL / "_musicdl_cache"
CACHE.mkdir(parents=True)


class Song:
    """只带这一轮真用到的字段，桩不许比真 SongInfo 宽。"""

    def __init__(self, name, artists="某歌手", source="NeteaseMusicClient"):
        self.song_name, self.singers, self.source = name, artists, source
        self.ext, self.identifier = "mp3", "id1"
        self.work_dir, self._save_path = str(CACHE), None
        self.lyric, self.cover_url = "", ""

    @property
    def save_path(self):
        # 真 SongInfo 在这里还会 sanitize + 对盘根 mkdir，那一步用下面的假客户端复现
        return self._save_path or os.path.join(
            self.work_dir, f"{self.song_name} - {self.identifier}.{self.ext}")


HIT: set = set()
SLOW: set = set()
SEARCHED: list[str] = []


def fake_search(src, keyword, **kw):
    SEARCHED.append(f"{src}|{keyword}")
    title = keyword.split(" ", 1)[-1]
    if title in SLOW:
        time.sleep(0.4)
    if title not in HIT:
        return [], []
    s = Song(title, source=src)
    return [{"id": M._cache_song(s), "title": title, "artists": "某歌手",
             "duration_s": 200}], []


def pairs_of(titles):
    return [(f"cid_{t}", {"title": t, "artists": "某歌手", "duration_s": 200})
            for t in titles]


def run_round(titles, sources, report=None):
    LOGS.clear()
    return M.resolve_placeholders(pairs_of(titles), sources=sources,
                                  work_dir=str(DL), log=log, report=report)


M._search_one_source = fake_search
_real_budget = (M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_BUDGET_RELAY, M.TRACK_MATCH_WORKERS)

# ---------------------------------------------------------------- 预算按源分档
print("=== K. 整轮预算：Spotify/Apple 放宽，其余照旧，四处用同一个数 ===")
run_round(["甲"], ["NeteaseMusicClient"])
start = next((m for m in LOGS if "开始按曲名匹配" in m), "")
ck("K1 默认匹配源仍是 TRACK_MATCH_BUDGET", f"整轮最长 {M.TRACK_MATCH_BUDGET}s" in start, start)
ck("K2 默认匹配源不提放宽", "放宽" not in "".join(LOGS), LOGS)
run_round(["甲"], ["SpotifyMusicClient"])
start_sp = next((m for m in LOGS if "开始按曲名匹配" in m), "")
ck("K3 匹配源含 Spotify 时整轮预算用 RELAY（3000s）",
   f"整轮最长 {M.TRACK_MATCH_BUDGET_RELAY}s" in start_sp
   and M.TRACK_MATCH_BUDGET_RELAY == 3000, start_sp)
ck("K4 转链提示里写的是同一个数，不是两处各说各话",
   any("第三方转链" in m and f"{M.TRACK_MATCH_BUDGET_RELAY}s" in m for m in LOGS),
   [m for m in LOGS if "第三方转链" in m])
run_round(["乙"], ["AppleMusicClient"])
ck("K5 Apple 同样放宽",
   any(f"整轮最长 {M.TRACK_MATCH_BUDGET_RELAY}s" in m for m in LOGS), LOGS)

M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_WORKERS = 0.2, 1
SLOW.update({"慢1", "慢2", "慢3", "慢4"})
run_round(["慢1", "慢2", "慢3", "慢4"], ["NeteaseMusicClient"])
M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_WORKERS = _real_budget[:1] + (3,)
ck("K6 反向验证：预算真跟着常量走（打桩 0.2s 就按 0.2s 收摊，不是硬编码）",
   any("超过 0.2s" in m for m in LOGS), [m for m in LOGS if "超过" in m])
ck("K7 「没轮到搜」汇总行里的秒数与实际生效的一致",
   any("本轮没轮到搜" in m and "0.2s" in m for m in LOGS), [m for m in LOGS if "没轮到" in m])

M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_BUDGET_RELAY = 99, 0.2
M.TRACK_MATCH_WORKERS = 1
run_round(["慢1", "慢2", "慢3", "慢4"], ["SpotifyMusicClient"])
M.TRACK_MATCH_BUDGET, M.TRACK_MATCH_BUDGET_RELAY, M.TRACK_MATCH_WORKERS = _real_budget
ck("K8 反向验证：开跑 Spotify 时超时判定用的是 RELAY 那个常量",
   any("超过 0.2s" in m for m in LOGS) and not any("99s" in m for m in LOGS),
   [m for m in LOGS if "超过" in m])

# ---------------------------------------------------------------- 未完清单
print("=== L. 未完清单：整份列出，不截断，还要交给界面 ===")
T15 = [f"歌{i:02d}" for i in range(15)]
rep: dict = {}
n_hit = run_round(T15, ["NeteaseMusicClient"], report=rep)
hdr = next((i for i, m in enumerate(LOGS) if "按曲名没找到" in m), -1)
block = "".join(LOGS[hdr + 1:hdr + 6]) if hdr >= 0 else ""
ck("L1 汇总行下面把 15 首全列出来（不是只有逐首判定那几行）",
   hdr >= 0 and all(t in block for t in T15), block)
ck("L2 汇总行的计数与列出的条数一致", n_hit == 0
   and any(f"有 15 首" in m for m in LOGS), [m for m in LOGS if "没找到" in m])
ck("L3 清单里没有省略号（截断痕迹）", not any("…" in m for m in LOGS),
   [m for m in LOGS if "…" in m])
ck("L4 report 回填了本轮结论",
   rep.get("missed") == T15 and rep.get("unsearched") == [] and rep.get("matched") == 0
   and rep.get("budget") == M.TRACK_MATCH_BUDGET and "Netease" in rep.get("sources", ""), rep)
HIT.add("甲")
rep2: dict = {}
ck("L5 反向验证：全部命中时不列清单、report 里是空的",
   run_round(["甲"], ["NeteaseMusicClient"], report=rep2) == 1
   and rep2["missed"] == [] and not any("没找到" in m for m in LOGS), (LOGS, rep2))
HIT.discard("甲")

rows: list[str] = []
M.log_name_list(lambda m, lv="info": rows.append(m), "有 25 首没找到",
                 [f"名{i}" for i in range(25)])
ck("L6 长清单分行打印，25 个名字一个不少",
   len(rows) == 4 and sum(r.count("、") + 1 for r in rows[1:]) == 25, rows)

# ---------------------------------------------------------------- 落盘目录守卫
print("=== M. 落盘目录：曲名把文件甩出格子就会整片中断 ===")
_real_cache_dir, M.musicdl_cache_dir = M.musicdl_cache_dir, (lambda base="": str(CACHE))
bad = Song("/坏名")
ok_song = Song("好名")
out = [bad, ok_song, {"needs_match": True}]
n_fix = M._guard_song_paths(out, str(DL), log)
ck("M1 前导斜杠的曲名被洗干净，文件留在下载目录内",
   n_fix == 1 and bad.song_name == "坏名" and M._path_is_inside(
       str(DL), os.path.dirname(bad.save_path)), (n_fix, bad.save_path))
ck("M2 缓存那一层目录保留（归档按它找文件）", bad.work_dir == str(CACHE), bad.work_dir)
ck("M3 反向验证：正常曲名一个字段都不动",
   ok_song.song_name == "好名" and ok_song.work_dir == str(CACHE)
   and ok_song._save_path is None, vars(ok_song))
ck("M4 占位 dict 直接跳过，不报错", isinstance(out[2], dict))
pinned = Song("歌名")
pinned._save_path = os.path.join(os.path.splitdrive(str(DL))[0], "计划外.mp3")
M._guard_song_paths([pinned], str(DL), log)
ck("M5 搜索时算坏的旧计划路径（已指向盘根）也拉回下载目录内",
   M._path_is_inside(str(DL), os.path.dirname(pinned.save_path))
   and pinned._save_path in (None, ""), pinned.save_path)
ck("M6 _path_is_inside 认盘根为外面",
   not M._path_is_inside(str(DL), os.path.splitdrive(str(DL))[0] + "\\")
   and M._path_is_inside(str(DL), str(CACHE)))

HAS_MUSICDL = M.musicdl_available()
if HAS_MUSICDL:
    from musicdl.modules.utils.data import SongInfo  # type: ignore

    si = SongInfo(song_name="/盘根", work_dir=str(CACHE), ext="mp3", identifier="x1")
    planned = os.path.dirname(si.save_path)
    ck("M7 真 musicdl 用这种曲名算出的落盘目录塌成盘根（跑到下载目录外面）",
       not M._path_is_inside(str(DL), planned)
       and os.path.splitdrive(planned)[1].strip("\\/") == "", planned)
    root_ext = "\\\\?\\" + os.path.splitdrive(str(DL))[0] + "/"
    boom = ""
    try:
        os.makedirs(root_ext)
    except OSError as e:
        boom = f"{type(e).__name__}: {e}"
    if boom:
        ck("M7b 盘根的 \\\\?\\ 写法建不出来（线上日志里那句报错就是这么来的）",
           "WinError 2" in boom, boom)
    else:
        print(f"SKIP M7b：这台机器上 makedirs({root_ext!r}) 没抛，线上日志里的 "
              "WinError 2 只在 H: 实测过")
    M._guard_song_paths([si], str(DL), log)
    still = ""
    try:
        still = si.save_path or ""
    except Exception as e:
        still = f"仍抛 {type(e).__name__}: {e}"
    ck("M8 过守卫后同一个对象算出的路径落回下载目录内",
       "仍抛" not in still and M._path_is_inside(str(DL), os.path.dirname(still)), still)

    # ---- \\?\ 前缀：线上日志里那句 '\\\\?\\H:/' 就是这个形状建不出来（实测）
    from musicdl.modules.utils.misc import IOUtils  # type: ignore

    def _mkdir_like_download(s):
        """照抄 musicdl 下载第一句：对 save_path 的目录建目录。它炸这儿就炸在那儿。"""
        IOUtils.touchdir(os.path.dirname(s.save_path))

    for tag, target in (("work_dir", str(CACHE)),
                        ("_save_path", str(Path(CACHE) / "计划内.mp3"))):
        px = Song(f"前缀{tag}")
        setattr(px, tag, "\\\\?\\" + target)
        boom = ""
        try:
            _mkdir_like_download(px)
        except Exception as e:
            boom = f"{type(e).__name__}: {e}"
        LOGS.clear()
        fixed = M._guard_song_paths([px], str(DL), log)
        after = ""
        try:
            _mkdir_like_download(px)
        except Exception as e:
            after = f"{type(e).__name__}: {e}"
        ck(f"M9 {tag} 带上 \\\\?\\ 前缀时下载必炸（线上原形状）", bool(boom), boom or "没炸")
        ck(f"M10 守卫能把这条改到建得出目录（改写 {fixed} 条）", not after and fixed == 1,
           after or "不再炸")
        ck(f"M11 {tag} 被收回缓存格子而不是下载目录（归档找得到）",
           Path(px.work_dir) == CACHE, px.work_dir)
        ck(f"M12 日志点名是哪首歌、原始落点长什么样",
           any(f"前缀{tag}" in m and "\\\\?\\" in m for m in LOGS), LOGS[-1:])
else:
    print("SKIP M7/M8：本机没有 musicdl，真结构复现没跑")

# ---------------------------------------------------------------- download_songs 接线
print("=== N. download_songs：守卫在递交前跑，report 一路带回界面 ===")
GIVEN: list[list] = []


class StrictClient:
    """照 musicdl 的 _download：先对 save_path 的目录建目录，盘根在 Windows 上必炸。"""

    def download(self, song_infos=None):
        infos = list(song_infos or [])
        GIVEN.append(infos)
        out = []
        for s in infos:
            d = os.path.dirname(s.save_path)
            if os.path.splitdrive(os.path.abspath(d))[1].strip("\\/") == "":
                # Windows 上盘根 mkdir 的真实样子：[WinError 2]
                exc = FileNotFoundError(2, "系统找不到指定的文件。")
                exc.winerror = 2
                exc.filename = d
                raise exc
            p = Path(d) / f"{os.path.basename(s.save_path)}"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"audio-" + s.song_name.encode("utf-8"))
            cp = Song(s.song_name)
            cp._save_path = str(p)
            out.append(cp)
        return out


_real2 = (M.musicdl_available, M._build_client, M.musicdl_cache_dir,
          M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover)
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: StrictClient()
M.musicdl_cache_dir = lambda base="": str(CACHE)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}

ids = [M._cache_song(Song("/坏名A")), M._cache_song(Song("好名B"))]
LOGS.clear()
rep3: dict = {}
got = M.download_songs(ids, work_dir=str(DL), log=log, match_report=rep3)
ck("N1 坏曲名在递交前就被改掉，整片不再中断",
   [s.song_name for s in GIVEN[-1]] == ["坏名A", "好名B"]
   and all(p and Path(p).is_file() for p in got), (GIVEN[-1], got))
ck("N2 守卫写明了是哪首、为什么", any("曲名带路径分隔符" in m and "坏名A" in m for m in LOGS),
   [m for m in LOGS if "曲名带路径分隔符" in m])
ck("N3 成品归档到下载目录", any(Path(p).parent == DL for p in got), got)
ck("N4 没有占位条目时不跑匹配，report 保持空", rep3 == {}, rep3)

GIVEN.clear()
M._guard_song_paths, _real_guard = (lambda *a, **k: 0), M._guard_song_paths
LOGS.clear()
try:
    M.download_songs([M._cache_song(Song("/坏名C"))], work_dir=str(DL), log=log)
finally:
    M._guard_song_paths = _real_guard
ck("N5 反向验证：关掉守卫，同一首歌就会把整片带崩",
   any("下载中断" in m and "WinError 2" in m for m in LOGS),
   [m for m in LOGS if "中断" in m])

pend = {"id": "", "title": "查无此歌", "artists": "某歌手", "duration_s": 200,
        "source": "Spotify", "url": "", "needs_match": True}
pend["id"] = M._cache_song(pend)
rep4: dict = {}
M.download_songs([pend["id"]], work_dir=str(DL), log=log,
                 match_sources=["NeteaseMusicClient"], match_report=rep4)
ck("N6 占位没匹配上时 report 一路带回「没找到」清单",
   rep4.get("missed") == ["查无此歌"], rep4)

# -------------------------------------------------- 跨批次不下载第二份
print("=== O. 归档时替换而不是另存 _1（判重本身在 tests/switchsource_test.py 的 B 段验）===")
ODL = OUT / "odl"
ODL.mkdir(parents=True)


def mk(rel_name, data=b"old-older"):
    p = ODL / rel_name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


LOGS.clear()
mk("陈奕迅/十年 - 陈奕迅.mp3")            # 目录里已有的那份旧成品（9 字节）
tgt = ODL / "陈奕迅" / "十年 - 陈奕迅.mp3"
new = mk("incoming.mp3", b"new-song")
out_path = M.promote_music_file(new, tgt, log=log)
ck("O11 归档时目标已有就整只替换，目录里没有 _1 副本",
   Path(out_path) == tgt and tgt.read_bytes() == b"new-song"
   and len(list((ODL / "陈奕迅").glob("十年*"))) == 1,
   [p.name for p in (ODL / "陈奕迅").glob("十年*")])
ck("O12 替换那条日志写明新旧两份字节数、且说不另存副本",
   any("已经有一份" in m and "9 字节" in m and "8 字节" in m and "没有另存副本" in m
       for m in LOGS), LOGS[-1:])
LOGS.clear()
src2 = mk("incoming2.mp3", b"12345")
d2 = M.promote_music_file(src2, ODL / "新人" / "第一次 - 新人.mp3", log=log)
ck("O13 目录里还没有这份时照常归档，不多说一句",
   d2.is_file() and not src2.exists() and LOGS == [], (str(d2), LOGS))

# ------------------------------------------------- 缓存格子在下载目录外面
print("=== Q. 缓存搬到工具文件夹（下载目录外面）：正常曲目不许被改写，成品不许被自己删掉 ===")
# 前面几段的 CACHE 建在下载目录里，那是 _musicdl_cache 搬家之前的旧形状 ——
# 守卫按「在下载目录内」判合法，旧形状的 fixture 首首都合法，所以整条回归它是测不出来的。
_real_out3 = M.MUSICDL_OUTPUTS
M.musicdl_cache_dir = _real_cache_dir      # 换回真函数：只有它算得出搬家后的落点
M.MUSICDL_OUTPUTS = str(OUT / "q_outputs")
QDL = OUT / "qdl"
QDL.mkdir(parents=True)
QCACHE = Path(M.musicdl_cache_dir(str(QDL)))


def qsong(name: str) -> Song:
    s = Song(name)
    s.work_dir = str(QCACHE)               # musicdl 每首歌自带的落点就是缓存格子
    return s


ck("Q0 前置：缓存格子确实在下载目录外（旧口径守卫在这一步误判每一首）",
   not M._path_is_inside(str(QDL), str(QCACHE))
   and M._download_dir_ok(str(QDL), str(QCACHE)), str(QCACHE))

LOGS.clear()
GIVEN.clear()
got_q = M.download_songs([M._cache_song(qsong("晴天")), M._cache_song(qsong("稻香"))],
                         work_dir=str(QDL), log=log)
ck("Q1 正常曲目一首没被守卫改动（落点在缓存格子里就算合法）",
   not any("落点收回" in m or "曲名改成" in m for m in LOGS)
   and [s.song_name for s in GIVEN[-1]] == ["晴天", "稻香"]
   and all(s.work_dir == str(QCACHE) for s in GIVEN[-1]),
   [m for m in LOGS if "曲名" in m or "曲目" in m])
ck("Q2 两首 mp3 都真在下发目录里（回归时这里返回的路径指向空气）",
   len(got_q) == 2 and all(p and Path(p).is_file() and Path(p).parent == QDL for p in got_q),
   got_q)

# 反向验证：拿掉「源＝目标」那句问话，同一份输入就会被当成重复删掉自己
QSELF = QDL / "自删.mp3"
QSELF.write_bytes(b"same-size-body")
_real_same = M._same_file
M._same_file = lambda a, b: False
try:
    qback = M.collect_and_promote_downloads(str(QCACHE), str(QDL), log=log,
                                            only=[str(QSELF)])
finally:
    M._same_file = _real_same
ck("Q3 反向验证：去掉 _same_file 问句，源＝目标时源当场被删、返回路径指向空气",
   qback == [str(QSELF)] and not QSELF.exists(), (qback, QSELF.exists()))

QKEEP = QDL / "留下.mp3"
QKEEP.write_bytes(b"same-size-body")
qback2 = M.collect_and_promote_downloads(str(QCACHE), str(QDL), log=log, only=[str(QKEEP)])
ck("Q4 同一份输入、守卫在位：文件还在，返回的仍是它自己",
   qback2 == [str(QKEEP)] and QKEEP.is_file(), (qback2, QKEEP.is_file()))

(QCACHE / "qa").mkdir(parents=True, exist_ok=True)
(QCACHE / "qb").mkdir(parents=True, exist_ok=True)
QDUPA = QCACHE / "qa" / "同一首.mp3"
QDUPB = QCACHE / "qb" / "同一首.mp3"
for qd in (QDUPA, QDUPB):
    qd.write_bytes(b"duplicate-body")
qdup = M.collect_and_promote_downloads(str(QCACHE), str(QDL), log=log,
                                       only=[str(QDUPA), str(QDUPB)])
ck("Q5 真·重复没被放宽：不同文件、同名同大小，仍只留一份、第二份删掉",
   qdup[0] == qdup[1] and Path(qdup[0]).is_file()
   and not QDUPA.exists() and not QDUPB.exists(), (qdup, str(QDUPB.exists())))

LOGS.clear()
got_bad = M.download_songs([M._cache_song(qsong("/坏名Z"))], work_dir=str(QDL), log=log)
ck("Q6 反向验证：真会甩到盘根的曲名照样在递交前被改名，成品仍归档进下载目录",
   any("曲名带路径分隔符" in m and "坏名Z" in m for m in LOGS)
   and got_bad and Path(got_bad[0]).is_file() and Path(got_bad[0]).parent == QDL,
   ([m for m in LOGS if "曲名带路径分隔符" in m], got_bad))

qforeign = Song("外来落点")
qforeign.work_dir = str(OUT / "elsewhere")
LOGS.clear()
got_f = M.download_songs([M._cache_song(qforeign)], work_dir=str(QDL), log=log)
ck("Q7 两个目录之外才改写，且落点收回缓存格子（归档找得到，成品跟着进下载目录）",
   any("落在下载目录与工具输出目录之外" in m and "落点收回" in m for m in LOGS)
   and got_f and Path(got_f[0]).is_file() and Path(got_f[0]).parent == QDL,
   ([m for m in LOGS if "曲目" in m], got_f))

_real_collect = M.collect_and_promote_downloads
M.collect_and_promote_downloads = lambda *a, **k: [str(QCACHE / "并不存在.mp3")]
LOGS.clear()
got_d = M.download_songs([M._cache_song(qsong("消失"))], work_dir=str(QDL), log=log)
M.collect_and_promote_downloads = _real_collect
ck("Q8 归档回了路径、文件却不在 → 这一首按失败算，不再报「已下载」",
   got_d == [""] and any("归档后文件不见了" in m for m in LOGS)
   and not any("musicdl 已下载" in m for m in LOGS), (got_d, LOGS[-3:]))

# 反向验证：守卫把坏落点「收回下载目录」（1.2.7 之前的旧动作）＋归档不查同源，成品当场被删
# （线上丢 6 首就是这么来的）；现在收回的是缓存格子，同样的旧口径下成品活得下来。
_old_ok, _old_same, _old_cell = M._download_dir_ok, M._same_file, M.musicdl_cache_dir
M._download_dir_ok = lambda base, target: M._path_is_inside(base, target)   # 旧口径：只认下载目录
M._same_file = lambda a, b: False
LOGS.clear()
try:
    M.musicdl_cache_dir = lambda base="": str(QDL)      # 旧动作：坏落点收回下载目录本身
    got_old = M.download_songs([M._cache_song(qsong("退旧写法"))], work_dir=str(QDL), log=log)
finally:
    M._download_dir_ok, M._same_file, M.musicdl_cache_dir = _old_ok, _old_same, _old_cell
ck("Q9 反向验证：收回下载目录（旧动作）＋不查同源，这一首的成品当场被删（线上丢的就是这个形状）",
   got_old == [""] and not list(QDL.glob("退旧写法*"))
   and any("归档后文件不见了" in m and "退旧写法" in m for m in LOGS)
   and not any("musicdl 已下载" in m for m in LOGS),
   (got_old, [m for m in LOGS if "不见了" in m or "已下载" in m]))

M._download_dir_ok = lambda base, target: M._path_is_inside(base, target)
M._same_file = lambda a, b: False
LOGS.clear()
try:
    got_new = M.download_songs([M._cache_song(qsong("收回格子"))], work_dir=str(QDL), log=log)
finally:
    M._download_dir_ok, M._same_file = _old_ok, _old_same
ck("Q10 同样退回旧口径，只要坏落点收回的是缓存格子，成品就还在、也照样归档进下载目录",
   got_new and Path(got_new[0]).is_file() and Path(got_new[0]).parent == QDL
   and list(QDL.glob("收回格子*")), (got_new, [m for m in LOGS if "落点收回" in m]))

M.MUSICDL_OUTPUTS = _real_out3
for name, val in zip(("musicdl_available", "_build_client", "musicdl_cache_dir",
                      "fetch_lyric_fallback_cn", "save_lyrics_and_cover"), _real2):
    setattr(M, name, val)
M.musicdl_cache_dir = _real_cache_dir      # _real2[2] 抓到的已经是 M 段的桩
M._search_one_source = fake_search

# ---------------------------------------------------------------- 工具有关文件落在工具文件夹
_real_outputs = M.MUSICDL_OUTPUTS
src_text = Path(_real_outputs).with_name("music_search.py").read_text(encoding="utf-8")
ck("P1 musicdl 工作目录锚在模块自身所在文件夹（绝对，不跟进程 CWD 走）",
   os.path.isabs(_real_outputs)
   and _real_outputs == str(Path(M.__file__).resolve().parent / "musicdl_outputs"), _real_outputs)
ck("P2 反向验证：源码里不再留相对的 \"musicdl_outputs\" 字面量",
   'or "musicdl_outputs"' not in src_text and '= "musicdl_outputs"' not in src_text
   and ': str = "musicdl_outputs"' not in src_text)
ck("P3 musicdl 客户端的默认工作目录就是那份绝对路径",
   __import__("inspect").signature(M._build_client).parameters["work_dir"].default == _real_outputs)
M.MUSICDL_OUTPUTS = str(OUT / "mdl")
DL_DIR = OUT / "Downloads"
cache_batch = M.musicdl_cache_dir(str(DL_DIR))
ck("P4 中间目录搬到工具文件夹下，用户的下载目录里不再多出 _musicdl_cache",
   cache_batch.startswith(M.MUSICDL_OUTPUTS) and not (DL_DIR / "_musicdl_cache").exists(), cache_batch)
ck("P5 幂等：把结果再传回去仍是同一个目录（否则写入与归档扫描对不上）",
   all(M.musicdl_cache_dir(p) == M.musicdl_cache_dir(M.musicdl_cache_dir(p))
       for p in (str(DL_DIR), "", cache_batch, M.MUSICDL_OUTPUTS, str(OUT / "preview_tmp"))))
ck("P6 按 base 末级分格：批量与试听各扫各的目录，不会把对方的文件当成本次成果",
   M.musicdl_cache_dir(str(DL_DIR)) != M.musicdl_cache_dir(str(OUT / "music_preview_x")))
ck("P7 无 base 与 base=工作目录本身归到同一格（不再拼出 musicdl_outputs/musicdl_outputs）",
   M.musicdl_cache_dir("") == M.musicdl_cache_dir(M.MUSICDL_OUTPUTS) == os.path.join(
       M.MUSICDL_OUTPUTS, "_musicdl_cache"))
M.MUSICDL_OUTPUTS = _real_outputs
shutil.rmtree(OUT, ignore_errors=True)

print("FAILED: " + ("; ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
