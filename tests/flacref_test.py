r"""无损参照源（flacdownloader.com 的 Qobuz/Tidal 搜索）：只借它查元数据，不借它下音频。

全程不联网：HTTP 一律用桩替掉，真发请求的那一段只验它把 URL/参数/代理拼成什么样。
跑法：`python tests/flacref_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


QOBUZ_RAW = {
    "album": "周杰伦钢琴曲集", "albumArtist": "CIP Music", "artist": "CIP Music",
    "barcode": "0199999059011", "bitDepth": 24, "composer": "Jay Chou",
    "cover": "https://static.qobuz.com/images/covers/0a/pd/x_org.jpg",
    "date": "2024-12-19", "durationMs": 267000, "hires": True, "id": 308984973,
    "isrc": "QZPJ32432001", "label": "CIP Music", "samplingRate": 48,
    "title": "晴天", "trackNumber": 1,
    "url": "https://open.qobuz.com/track/308984973", "version": "钢琴版",
}
TIDAL_RAW = {
    "album": "葉惠美", "artist": "Jay Chou", "cover": "https://resources.tidal.com/images/x.jpg",
    "discNumber": 1, "durationMs": 270000, "hires": True, "id": 337502796,
    "isrc": "TWK970300503", "lossless": True, "tags": ["LOSSLESS", "HIRES_LOSSLESS"],
    "title": "晴天", "trackNumber": 3, "url": "https://tidal.com/browse/track/337502796",
    "version": "",
}

# ---------------------------------------------------------------- 1. 行归一化
print("=== A. 元数据折成搜索行 ===")
q = M._flacref_row("qobuz", QOBUZ_RAW)
ck("A1 Qobuz：ISRC / 精确时长 / 官方链接原样带出",
   q["isrc"] == "QZPJ32432001" and q["duration_s"] == 267 and q["duration"] == "4:27"
   and q["url"] == "https://open.qobuz.com/track/308984973", repr(q))
ck("A2 Qobuz：位深写进品质列（够短，不撑爆 70px），采样率留在字段里",
   q["quality"] == "flac 24bit" and q["sampling_rate"] == 48, repr(q["quality"]))
ck("A3 版本标注单独留档（「钢琴版」这种不是原曲，界面上要看得见）",
   q["version"] == "钢琴版" and q["date"] == "2024-12-19" and q["label"] == "CIP Music")
t = M._flacref_row("tidal", TIDAL_RAW)
ck("A4 Tidal：没给 bitDepth，只标 flac 不编位深",
   t["quality"] == "flac" and t["bit_depth"] == 0, repr(t["quality"]))
ck("A5 Tidal：歌手是英文名照抄，不做任何改写",
   t["artists"] == "Jay Chou" and t["source"] == "Tidal·参照", repr(t["artists"]))
ck("A6 两种源都标成参照行且明确下不了",
   all(r["reference_only"] and r["can_musicdl_download"] is False
       and r["id"].startswith("ref:") for r in (q, t)), repr([q["id"], t["id"]]))
ck("A7 繁体歌手/专辑名不被简化改写（参照就该照抄官方写法）",
   M._flacref_row("tidal", TIDAL_RAW)["album"] == "葉惠美")

# ---------------------------------------------------------------- 2. 脏数据
print("=== B. 拿不到的字段一律留空，不编 ===")
ck("B1 没曲名的行直接丢掉", M._flacref_row("qobuz", {"artist": "X", "id": 1}) == {})
ck("B2 时长缺失 → 0 秒 + 空时长文本（不是 0:00 也不是猜一个）",
   M._flacref_row("qobuz", {"title": "X", "id": 2})["duration_s"] == 0
   and M._flacref_row("qobuz", {"title": "X", "id": 2})["duration"] == "")
ck("B3 字符串/浮点时长不会炸整个查询",
   M._flacref_row("qobuz", {"title": "X", "id": 3, "durationMs": "267000.0",
                            "bitDepth": "24"})["duration_s"] == 267,
   repr(M._flacref_row("qobuz", {"title": "X", "id": 3, "durationMs": "267000.0"})))
ck("B4 没有任何无损标记 → 品质留空",
   M._flacref_row("qobuz", {"title": "X", "id": 4, "bitDepth": 16})["quality"] == "")

# ---------------------------------------------------------------- 3. 请求形状
print("=== C. 真发请求那段：只准打开放的搜索接口 ===")
import requests  # noqa: E402

CALLS: list = []


class FakeResp:
    payload = {"tracks": [QOBUZ_RAW, "脏数据", TIDAL_RAW]}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


_orig_get = requests.get


def fake_get(url, **kw):
    CALLS.append((url, kw))
    return FakeResp()


requests.get = fake_get
try:
    rows = M._flacref_get("qobuz", "晴天 周杰伦", 0, proxy="http://127.0.0.1:9999")
    no_proxy_url, no_proxy_kw = None, None
    M._flacref_get("tidal", "晴天", 0)
    no_proxy_kw = CALLS[-1][1]
    url1, kw1 = CALLS[0]
    bad = M._flacref_get("qobuz", "x", 0)
finally:
    requests.get = _orig_get

ck("C1 URL 就是站内开放的搜索路径，只带 q/offset",
   url1 == "https://flacdownloader.com/api/qobuz/search"
   and kw1["params"] == {"q": "晴天 周杰伦", "offset": 0}, repr((url1, kw1.get("params"))))
ck("C2 只带 User-Agent（这个站开放搜索就认它），不塞任何凭据",
   set(kw1["headers"]) == {"User-Agent", "Accept"}
   and all(k not in str(kw1) for k in ("token", "Cookie", "appSecret", "x-user-auth")), repr(kw1["headers"]))
ck("C3 给了代理才传 proxies，没给就不传（跟随环境）",
   kw1["proxies"] == {"http": "http://127.0.0.1:9999", "https": "http://127.0.0.1:9999"}
   and "proxies" not in no_proxy_kw, repr([kw1.get("proxies"), "proxies" in no_proxy_kw]))
ck("C4 非 dict 的行被剔掉，其余照常返回", len(rows) == 2, repr(len(rows)))
ck("C5 六条被访问的 URL 里没有任何一道门槛路径（prepare / queue / keys / turnstile）",
   all("/search" in u for u, _k in CALLS)
   and not any(x in u.lower() for u, _k in CALLS
               for x in ("/prepare", "/queue", "/keys", "turnstile", "captcha")),
   repr([u for u, _k in CALLS]))

# ---------------------------------------------------------------- 4. 查询编排
print("=== D. flacref_search：一个源挂了别跟着全挂 ===")
LOGS: list = []
log = lambda *a, **k: LOGS.append((a[0] if a else "", str(k.get("level") or "")))  # noqa: E731


def stub_get(table):
    def _s(platform, query, offset, *, proxy="", timeout=12.0):
        v = table.get(platform)
        if isinstance(v, Exception):
            raise v
        return v
    return _s


_old_get = M._flacref_get
try:
    M._flacref_get = stub_get({"qobuz": [QOBUZ_RAW], "tidal": [TIDAL_RAW]})
    both = M.flacref_search("晴天 周杰伦", log=log)
    ck("D1 两个平台都回时按 Qobuz、Tidal 顺序拼起来",
       [r["source"] for r in both] == ["Qobuz·参照", "Tidal·参照"], repr([r["source"] for r in both]))

    M._flacref_get = stub_get({"qobuz": RuntimeError("SSL: EOF"), "tidal": [TIDAL_RAW]})
    LOGS.clear()
    one = M.flacref_search("晴天", log=log)
    ck("D2 Qobuz 报错不影响 Tidal 出货",
       [r["source"] for r in one] == ["Tidal·参照"], repr(one))
    ck("D3 报错当场写明是哪个源、什么错，不静默",
       any("Qobuz" in m and "SSL: EOF" in m for m, _lv in LOGS), repr(LOGS))

    M._flacref_get = stub_get({"qobuz": [QOBUZ_RAW], "bogus": [QOBUZ_RAW]})
    ck("D4 不认识的平台名忽略，不报错",
       [r["source"] for r in M.flacref_search("晴天", platforms=("qobuz", "bogus"), log=log)]
       == ["Qobuz·参照"])
    ck("D5 空关键词不发请求", M.flacref_search("   ", log=log) == [])

    M._flacref_get = stub_get({"qobuz": [dict(QOBUZ_RAW, id=i, title=f"歌{i}") for i in range(40)]})
    ck("D6 limit 收着每源条数", len(M.flacref_search("晴天", limit=3, platforms=("qobuz",), log=log)) == 3)
finally:
    M._flacref_get = _old_get

# ---------------------------------------------------------------- 5. 接进搜索
print("=== E. search_music 里的开关与合并 ===")
_old_avail, _old_run = M.musicdl_available, M._run_source_searches
_old_ref = M.flacref_search
CALL_COUNT: list = []
try:
    M.musicdl_available = lambda: True

    def fake_run(srcs, kw, **k):
        return ([{"id": "c1", "title": "晴天", "artists": "周杰伦", "duration_s": 269,
                  "duration": "4:29", "source": "Netease", "quality": "mp3",
                  "album": "叶惠美", "url": "", "can_musicdl_download": True}],
                {"Netease": 1}, {}, 0.1)

    M._run_source_searches = fake_run
    REF_ROWS = [
        {"id": "ref:qobuz:1", "title": "晴天", "artists": "周杰伦", "duration_s": 267,
         "source": "Qobuz·参照", "quality": "flac 24bit", "reference_only": True,
         "can_musicdl_download": False, "isrc": "QZPJ32432001"},
        {"id": "ref:tidal:2", "title": "稻香", "artists": "周杰伦", "duration_s": 223,
         "source": "Tidal·参照", "quality": "flac", "reference_only": True,
         "can_musicdl_download": False, "isrc": "TWK970800100"},
    ]

    def fake_ref(*a, **k):
        CALL_COUNT.append(1)
        return [dict(r) for r in REF_ROWS]

    M.flacref_search = fake_ref

    r0 = M.search_music("晴天 周杰伦", sources=["NeteaseMusicClient"], include_ytdlp=False,
                        hide_unavailable=False, log=log)
    ck("E1 反向验证：不勾参照就一次都不问外部站",
       CALL_COUNT == [] and all(not str(x["id"]).startswith("ref:") for x in r0), repr(CALL_COUNT))

    CALL_COUNT.clear()
    r1 = M.search_music("晴天 周杰伦", sources=["NeteaseMusicClient"], include_ytdlp=False,
                        hide_unavailable=False, include_reference=True, log=log)
    ck("E2 勾了才问一次", len(CALL_COUNT) == 1, repr(CALL_COUNT))
    ck("E3 本平台已有的歌不再放一份参照行（免得同一首出现两行勾不动）",
       [x["id"] for x in r1] == ["c1", "ref:tidal:2"], repr([x["id"] for x in r1]))
    ck("E4 可下载行排在前，参照行只会追加在后面",
       r1[0]["can_musicdl_download"] and r1[-1]["reference_only"])

    CALL_COUNT.clear()
    M.search_music("晴天", sources=["NeteaseMusicClient"], include_ytdlp=False,
                   hide_unavailable=False, search_type="album", include_reference=True, log=log)
    ck("E5 搜专辑/歌单时不掺参照行（参照是单曲级的元数据）", CALL_COUNT == [], repr(CALL_COUNT))

    def boom(*a, **k):
        CALL_COUNT.append(1)
        raise RuntimeError("参照站挂了")

    M.flacref_search = boom
    r2 = M.search_music("晴天 周杰伦", sources=["NeteaseMusicClient"], include_ytdlp=False,
                        hide_unavailable=False, include_reference=True, log=log)
    ck("E6 参照查询挂了不影响本平台结果，报错写上屏幕",
       [x["id"] for x in r2] == ["c1"] and any("参照" in m and "挂了" in m for m, _lv in LOGS),
       repr([m for m, _ in LOGS][-2:]))
finally:
    M.musicdl_available, M._run_source_searches = _old_avail, _old_run
    M._flacref_get = _old_get
    M.flacref_search = _old_ref

print()
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
