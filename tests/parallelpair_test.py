r"""并发批量的「哪首歌对应哪个文件」自检（#122 线上读数查出的错配）。

线上实测（2026-09-24 18:48，收藏清单整单 4 首，咪咕一个源）：
    清单顺序   = Memento Mori(527s) / Aimer(222s) / Aimer Vivre(336s) / Aimer La Vie(194s)
    归档顺序   = Aimer Vivre / Aimer La Vie / Aimer / Memento Mori   ← 日志「已归档:」四行
    成品实测   = 名字为 Memento Mori 的文件 339.1s、Aimer 的 194.1s、
                 Aimer Vivre 的 222.6s、Aimer La Vie 的 526.7s        ← 整个倒过来
四个名字都装了别人的音频。原因在 download_songs 的对位那一步：同一批歌的计划 save_path
落在同一个目录里，而 musicdl 的 download() 是按线程完成顺序往回给副本的，
代码却按「每个位置从该目录里顺手指一个没用过的文件」配对 —— 完成顺序一不等于清单顺序就串。

这里不联网：桩客户端照线上那个形状造文件（同一个目录、按完成倒序返回、计划路径那份并不存在），
文件内容写成自己的曲名，跑完逐首核对「回报的路径里装的是不是这一首」。

跑法：`python tests/parallelpair_test.py`
"""
from __future__ import annotations

import copy
import shutil
import tempfile
import pathlib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import music_search as M  # noqa: E402

FAILED: list[str] = []
OUT = Path(tempfile.mkdtemp(prefix="md_parallelpair_test_"))
DL = OUT / "dl"
DL.mkdir()
CACHE = DL / "_musicdl_cache"
CACHE.mkdir()
LOGS: list[str] = []


def ck(name, cond, got=""):
    ok = bool(cond)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not ok:
        FAILED.append(name)


def log(msg, level="info"):
    LOGS.append(str(msg))


# 线上那四首：曲名 + 清单里记的时长（秒）
SONGS = [("Memento Mori", 527), ("Aimer", 222), ("Aimer Vivre", 336),
         ("Aimer La Vie (Soy Un Truhan Soy Un Senor)", 194)]


class FakeSong:
    """照 musicdl 的 SongInfo 形状造：work_dir 是整批共用的搜索目录，计划路径那一份并不落盘。"""

    def __init__(self, name, dur):
        self.song_name = name
        self.singers = "某歌手"
        self.source = "MiguMusicClient"
        self.ext = ".mp3"
        self.identifier = str(600000000000000000 + len(name))
        self.duration = f"{dur // 60}:{dur % 60:02d}"
        self.duration_s = dur
        self.download_url = "https://example.invalid/x.mp3"
        self.download_url_status = {"ok": True}
        self.work_dir = str(CACHE)                       # 同一批四首共用一个目录
        self._save_path = None
        self.lyric = ""
        self.cover_url = ""

    @property
    def save_path(self):
        # musicdl 自己的算法：work_dir/曲名 - identifier.ext，同名往后排 (1)
        if self._save_path is None:
            self._save_path = str(Path(self.work_dir) / f"{self.song_name} - {self.identifier}.mp3")
        return self._save_path


class CrossClient:
    """照线上形状交付：真落盘的名字被 musicdl 排成「… (1).mp3」（同名避让），
    所以传进去那批对象身上搜索时算的计划路径在磁盘上根本不存在 —— 对位只能退回
    「同一目录里顺手指一个」，而返回顺序是线程完成顺序（这里取倒序）。"""

    def __init__(self):
        self.given: list = []

    def download(self, song_infos=None):
        infos = list(song_infos or [])
        self.given = infos
        done = []
        for s in infos:
            p = Path(s.work_dir) / f"{s.song_name} - {s.identifier} (1).mp3"
            p.write_bytes(("BODY::" + s.song_name).encode("utf-8"))
            cp = copy.copy(s)
            cp._save_path = str(p)
            done.append(cp)
        return list(reversed(done))          # 完成顺序 ≠ 清单顺序


CLIENT = CrossClient()
_real = (M.musicdl_available, M._build_client, M.musicdl_cache_dir,
         M.fetch_lyric_fallback_cn, M.save_lyrics_and_cover, M._guard_song_paths)
M.musicdl_available = lambda: True
M._build_client = lambda *a, **k: CLIENT
M.musicdl_cache_dir = lambda base="": str(CACHE)
M.fetch_lyric_fallback_cn = lambda *a, **k: ""
M.save_lyrics_and_cover = lambda *a, **k: {}
M._guard_song_paths = lambda items, out_dir, log=log: 0     # 落点守卫另有自检，这里不掺进来

ids = [M._cache_song(FakeSong(n, d)) for n, d in SONGS]
pairs: list[tuple[int, str]] = []
got = M.download_songs(ids, work_dir=str(DL), log=log, on_result=lambda i, p: pairs.append((i, p)))

print("=== A. 回报的路径与清单位置一一对应 ===")
ck("A1 返回与 ids 等长", len(got) == 4, got)
ck("A2 on_result 每首回报一次", [i for i, _ in pairs] == [0, 1, 2, 3], pairs)
ck("A3 四首都有成品", all(p for _i, p in pairs), pairs)

print("=== B. 文件名、文件内容、清单行三者必须是同一首歌 ===")
for i, p in pairs:
    want_name = SONGS[i][0]
    if not p:
        ck(f"B{i+1} 有成品", False, p)
        continue
    stem = Path(p).name
    body = Path(p).read_bytes().decode("utf-8", "replace") if Path(p).is_file() else ""
    ck(f"B{i+1} 文件名是自己的歌「{want_name[:18]}」", stem.startswith(want_name + " - "), stem)
    ck(f"B{i+1}b 文件里装的也是这首", body == "BODY::" + want_name, body[:60])

print("=== C. download_songs 的返回值同样按位置对齐 ===")
for i, p in enumerate(got):
    if p:
        ck(f"C{i+1} 返回值装的是这一首", Path(p).read_bytes().decode() == "BODY::" + SONGS[i][0],
           Path(p).name)

print("=== D. 报错路径不受影响（反向验证：桩没串顺序时对得上）===")


class OrderedClient(CrossClient):
    def download(self, song_infos=None):
        infos = list(song_infos or [])
        self.given = infos
        done = []
        for s in infos:
            p = Path(s.work_dir) / f"{s.song_name} - {s.identifier} (1).mp3"
            p.write_bytes(("BODY::" + s.song_name).encode("utf-8"))
            cp = copy.copy(s)
            cp._save_path = str(p)
            done.append(cp)
        return done                          # 只有顺序不同：完成顺序恰好等于清单顺序


CACHE2 = DL / "_musicdl_cache"
CLIENT2 = OrderedClient()
M._build_client = lambda *a, **k: CLIENT2
for p in CACHE2.glob("*.mp3"):
    p.unlink()
for p in DL.glob("*.mp3"):
    p.unlink()
ids2 = [M._cache_song(FakeSong(n, d)) for n, d in SONGS]
pairs2: list[tuple[int, str]] = []
M.download_songs(ids2, work_dir=str(DL), log=log, on_result=lambda i, p: pairs2.append((i, p)))
ck("D1 完成顺序与清单一致时四首也各归各（错配只可能来自对位，不是来自造文件）",
   all(p and Path(p).read_bytes().decode() == "BODY::" + SONGS[i][0] for i, p in pairs2),
   [Path(p or '-').name for _i, p in pairs2])

print("=== F. 反向验证：目录里只有别人的文件时，宁可不给也不指认 ===")


class ForeignClient(CrossClient):
    """真落盘的文件名与本批四首全不相干（等价于线上「同目录还有别的歌的成品」）。
    桩不许比真对象宽：这里照样返回四个对象，所以对位要是还肯给路径，就一定是瞎指。"""

    def download(self, song_infos=None):
        infos = list(song_infos or [])
        self.given = infos
        done = []
        for k, s in enumerate(infos):
            p = Path(s.work_dir) / f"无关曲目{k + 1} - 7000000000000000{ k}.mp3"
            p.write_bytes(("BODY::无关曲目" + str(k + 1)).encode("utf-8"))
            cp = copy.copy(s)
            cp._save_path = str(p)          # 路径是真的，只是名字不是这一首
            done.append(cp)
        return done


for _p in list(DL.glob("*.mp3")) + list(CACHE.glob("*.mp3")):
    _p.unlink()
LOGS.clear()
CLIENT3 = ForeignClient()
M._build_client = lambda *a, **k: CLIENT3
ids3 = [M._cache_song(FakeSong(n, d)) for n, d in SONGS]
pairs3: list[tuple[int, str]] = []
got3 = M.download_songs(ids3, work_dir=str(DL), log=log, on_result=lambda i, p: pairs3.append((i, p)))
ck("F1 四行都不给路径（没有一条被瞎指）", all(not p for p in got3), got3)
ck("F2 也不回报路径", all(not p for _i, p in pairs3), pairs3)
ck("F3 报了「认不出哪个文件是它自己」", any("认不出哪个文件是它自己" in m for m in LOGS),
   [m[:70] for m in LOGS if "认不出" in m][:2])

# F5：把对位换回修复前的老逻辑，同样的桩必须被瞎指出去 —— 否则 F1~F3 是恒真断言
_new_pair = M._pair_paths_by_name


def _old_pair(piece, real_by_dir, used, *, log=print):
    out, pool_used = [], set(str(x) for x in used)
    for _i, s in piece:
        sp = str(M._song_field(s, "save_path", "filepath"))
        if sp and sp not in pool_used and Path(sp).is_file():
            out.append(sp); pool_used.add(sp); continue
        d = str(Path(sp).parent) if sp else ""
        out.append(next((c for c in real_by_dir.get(d, []) if c not in pool_used), ""))
        if out[-1]:
            pool_used.add(out[-1])
    used.clear(); used.update(pool_used)
    return out


for _p in list(DL.glob("*.mp3")) + list(CACHE.glob("*.mp3")):
    _p.unlink()
M._pair_paths_by_name = _old_pair
ids4 = [M._cache_song(FakeSong(n, d)) for n, d in SONGS]
got4 = M.download_songs(ids4, work_dir=str(DL), log=log)
M._pair_paths_by_name = _new_pair
ck("F5 老逻辑下四行会被指到无关文件（证明 F1~F3 有牙）",
   all(p and "无关曲目" in Path(p).name for p in got4), [Path(p or '-').name for p in got4])

print("=== E. 产物只在临时目录 ===")
left = sorted(str(p.relative_to(APP)) for p in (APP / "Downloads").rglob("*.mp3")
              if p.stat().st_mtime > OUT.stat().st_mtime)
ck("E1 没往工具的 Downloads 落文件", not left, left[:4])

M.musicdl_available, M._build_client, M.musicdl_cache_dir, M.fetch_lyric_fallback_cn, \
    M.save_lyrics_and_cover, M._guard_song_paths = _real
shutil.rmtree(OUT, ignore_errors=True)

print("\nFAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
