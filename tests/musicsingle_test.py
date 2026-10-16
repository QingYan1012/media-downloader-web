r"""#23 单曲入口自检：Spotify / 网易云的单曲链接能认出元数据，QQ 如实说拿不到。

全在内存里跑：不 import server、不读 config、不发真请求（联网那几处都换成假对象）。
  A) 链接识别：/track/、intl 前缀、歌单页不算单曲、网易云 ?id= 与 #/song?id=、QQ 的 songmid
  B) _spotify_track_fields 两种形状都吃（歌单行 artists.items[].profile / 单曲 firstArtist+otherArtists）
  C) pathfinder 指纹表：扫一次主包就把 fetchPlaylist 与 getTrack 一起记住，第二次不再发请求
  D) list_spotify_track：成功产一条 needs_match 占位；NotFound / 非 Track / 短链各有各的话术
  E) list_netease_track：免 Cookie 的 api/song/detail 折成同一形状的占位
  F) QQ 单曲的说法：点名「免 Cookie 拿不到」，不许写成「接口不通」
  G) parse_playlist 的路由：单曲走单曲分支、不许退回逐曲取址，歌单链接照旧

跑法：`python tests/musicsingle_test.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import music_search as M  # noqa: E402

FAILED: list[str] = []


def ck(name: str, cond, extra: str = ""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


def union(title="Hello", first="A", others=(), ms=200000, tid="abc123", album="Single"):
    """getTrack 返回的那个 trackUnion 的最小形状（照抄探针读到的字段名）。"""
    def a(n):
        return {"profile": {"name": n}, "id": "art"}
    return {
        "__typename": "Track", "name": title, "id": tid,
        "uri": f"spotify:track:{tid}",
        "duration": {"totalMilliseconds": ms},
        "firstArtist": {"items": [a(first)] if first else [], "totalCount": 1 if first else 0},
        "otherArtists": {"items": [a(n) for n in others], "totalCount": len(others)},
        "albumOfTrack": {"name": album, "coverArt": {"sources": [
            {"width": 64, "url": "c64.jpg"}, {"width": 640, "url": "c640.jpg"}]}},
    }


print("== A. 单曲链接识别 ==")
ck("A1 /track/ 认", M._spotify_track_id("https://open.spotify.com/track/0VjIjW4G") == "0VjIjW4G")
ck("A2 intl 前缀也认",
   M._spotify_track_id("https://open.spotify.com/intl-ja/track/0VjIjW4G") == "0VjIjW4G")
ck("A3 歌单页不算单曲",
   M._spotify_track_id("https://open.spotify.com/playlist/37i9dQZF") == "")
ck("A4 专辑页不算单曲", M._spotify_track_id("https://open.spotify.com/album/4dem9") == "")
ck("A5 短链域名认出来",
   M._is_spotify_short("https://spotify.link/abc123")
   and not M._is_spotify_short("https://open.spotify.com/track/0VjIjW4G"))
ck("A6 网易云 ?id=", M._netease_song_id("https://music.163.com/song?id=186000") == "186000")
ck("A7 网易云 #/song?id=",
   M._netease_song_id("https://music.163.com/#/song?id=186000") == "186000")
ck("A8 网易云 m 站 #track=",
   M._netease_song_id("https://music.163.com/m/#/track/186000") == "186000")
ck("A9 网易云歌单页不算单曲",
   M._netease_song_id("https://music.163.com/playlist?id=1234567") == "")
ck("A10 网易云要 4 位以上数字", M._netease_song_id("https://music.163.com/song?id=12") == "")
ck("A11 QQ songdetail",
   M._qq_song_mid("https://y.qq.com/n/ryqq/songdetail/0040B1amiZ1fBg") == "0040B1amiZ1fBg")
ck("A12 QQ ?songmid=",
   M._qq_song_mid("https://y.qq.com/msa/230/0_4567.html?songmid=0040B1amiZ1fBg") == "0040B1amiZ1fBg")
ck("A13 QQ 歌单页不算单曲",
   M._qq_song_mid("https://y.qq.com/portal/playlist.html?pic_surl=abc") == "")

print("== B. _spotify_track_fields 两种形状 ==")
row = {"itemV2": {"data": {
    "__typename": "Track", "name": "Song", "id": "xyz",
    "artists": {"items": [{"profile": {"name": "A"}}, {"profile": {"name": "B"}}]},
    "trackDuration": {"totalMilliseconds": 198840},
    "albumOfTrack": {"name": "Al", "coverArt": {"sources": [{"width": 300, "url": "c300.jpg"}]}}}}}
d = M._spotify_track_fields(row)
ck("B1 歌单行照旧",
   (d["title"], d["artists"], d["duration_s"], d["cover"]) == ("Song", "A, B", 199, "c300.jpg"),
   json.dumps(d, ensure_ascii=False)[:200])
u = M._spotify_track_fields(union("Blinding Lights", "The Weeknd", (), 200040, "0VjI"),
                           track_union=True)
ck("B2 单曲形状收（时长来自 duration 字段）",
   (u["title"], u["artists"], u["duration_s"]) == ("Blinding Lights", "The Weeknd", 200),
   json.dumps(u, ensure_ascii=False)[:220])
ck("B3 单曲的合著歌手并进来",
   M._spotify_track_fields(union("Domino", "Oxia", ("Space 92",), 232500),
                           track_union=True)["artists"] == "Oxia, Space 92")
ck("B4 单曲页地址自己拼得出",
   u["page_url"] == "https://open.spotify.com/track/0VjI", u["page_url"])
ck("B5 单曲也是待匹配占位",
   u["needs_match"] is True and u["url"] == "" and u["can_musicdl_download"] is False)
ck("B6 播客单集不收",
   M._spotify_track_fields({"__typename": "Episode", "name": "x"}, track_union=True) == {})
ck("B7 没曲名不收", M._spotify_track_fields({"__typename": "Track"}, track_union=True) == {})

print("== C. pathfinder 指纹表 ==")


class FakeResp:
    def __init__(self, text="", url="", status=200):
        self.text, self.url, self.status_code = text, url, status

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self.text or "{}")


class FakeSession:
    def __init__(self, js_text, payload=None):
        self.js, self.payload, self.gets, self.posts = js_text, payload or {}, [], []

    def get(self, url, **kw):
        self.gets.append(url)
        return FakeResp(text=self.js)

    def post(self, url, headers=None, json=None, timeout=None, **kw):
        self.posts.append(json)
        import json as _json
        return FakeResp(text=_json.dumps(self.payload.get((json or {}).get("operationName")) or {}))


JS = ('x{0:"a",1:"b"}{0:"a",1:"b"}{0:"a",1:"b"}{0:"s1",1:"s2"}{0:"h1",1:"h2"}'
      '"fetchPlaylist","query","8964e8eafb21aa992a7d951d256d83285c04be2105d209262901de70cb97584a"'
      '"getTrack","query","a8ef9e9f02b836feb0da3003c31dbb30decc6f4b473ef89ca88c882386d668de"'
      '"trackUnion","query","deadbeef00000000000000000000000000000000000000000000000000000000"')
M._SPOTIFY_HASH["value"], M._SPOTIFY_HASH["ts"] = {}, 0.0
s = FakeSession(JS)
ck("C1 一次扫包同时记住两个操作名",
   M._spotify_hash(s, "https://x/js.js", {}) == "8964e8eafb21aa992a7d951d256d83285c04be2105d209262901de70cb97584a"
   and M._spotify_hash(s, "https://x/js.js", {}, op="getTrack")
   == "a8ef9e9f02b836feb0da3003c31dbb30decc6f4b473ef89ca88c882386d668de",
   str(s.gets))
ck("C2 第二次走缓存，不再下载 JS 包", len(s.gets) == 1, str(s.gets))
ck("C3 表里没有的操作名返回空", M._spotify_hash(s, "https://x/js.js", {}, op="noSuchOp") == "")
M._SPOTIFY_HASH["value"], M._SPOTIFY_HASH["ts"] = {}, 0.0
s2 = FakeSession("没有查询串")
ck("C4 主包扫不到就补扫分片（仍不给假指纹）",
   M._spotify_hash(s2, "", {}) == "" and M._spotify_scan_hashes(s2, "", {}) == {})
M._SPOTIFY_HASH["value"], M._SPOTIFY_HASH["ts"] = {}, 0.0

print("== D. list_spotify_track ==")
_real_client = M._spotify_client
_real_scan = M._spotify_scan_hashes


SINGLE_SESSION = FakeSession("", {"getTrack": {"data": {"trackUnion": union(
    "Blinding Lights", "The Weeknd", (), 200040, "0VjI")}}})


def stub_client(proxy=""):
    return SINGLE_SESSION, {"jsPack": ""}, \
        {"access": "A", "client": "C", "version": "V"}, {}, ""


M._spotify_client = stub_client
M._spotify_scan_hashes = lambda session, js, ovr: {
    "getTrack": "a8ef9e9f02b836feb0da3003c31dbb30decc6f4b473ef89ca88c882386d668de"}
ses, item, err = None, {}, ""
item, err = M.list_spotify_track("https://open.spotify.com/track/0VjI", log=lambda *a: None)
ck("D1 单曲占位一条，错误为空", bool(item) and not err and item.get("needs_match"),
   json.dumps(item, ensure_ascii=False)[:200] + " | " + err)
ck("D2 占位进了缓存（下载时才换成真 SongInfo）",
   bool(item.get("id")) and M.get_cached_song(item["id"]) is not None)
_probe = SINGLE_SESSION
M.list_spotify_track("https://open.spotify.com/track/0VjI", log=lambda *a: None)
ck("D3 请求打的是 getTrack，变量是 uri",
   _probe.posts[-1]["operationName"] == "getTrack"
   and _probe.posts[-1]["variables"] == {"uri": "spotify:track:0VjI"},
   json.dumps(_probe.posts[-1], ensure_ascii=False)[:200])


def client_of(payload):
    def _c(proxy=""):
        return FakeSession("", payload), {"jsPack": ""}, \
            {"access": "A", "client": "C", "version": "V"}, {}, ""
    return _c


M._spotify_client = client_of({"getTrack": {"data": {"trackUnion": {
    "__typename": "NotFound", "message": "Object with uri 'spotify:track:zz' not found"}}}})
item, err = M.list_spotify_track("https://open.spotify.com/track/zz", log=lambda *a: None)
ck("D4 下架/错 id 说实话", not item and "不是歌" in err and "not found" in err, err)
M._spotify_client = client_of({"getTrack": {"data": {"trackUnion": {
    "__typename": "Episode", "name": "ep"}}}})
ck("D5 播客单集不收", M.list_spotify_track("https://open.spotify.com/track/ep",
                                        log=lambda *a: None)[1] != "")
M._spotify_client = lambda proxy="": (None, {}, {}, {}, "连不上 Spotify 的公开接口：超时")
ck("D6 令牌阶段的错误原样递出去",
   M.list_spotify_track("https://open.spotify.com/track/0VjI", log=lambda *a: None)
   == ({}, "连不上 Spotify 的公开接口：超时"))
M._spotify_client = lambda proxy="": (None, {}, {}, {}, "")
ck("D7 不是单曲页不硬试",
   M.list_spotify_track("https://open.spotify.com/playlist/37i9", log=lambda *a: None)[1]
   == "链接里没有 /track/<id>，不是 Spotify 单曲页")
M._spotify_client, M._spotify_scan_hashes = _real_client, _real_scan

print("== E. list_netease_track ==")
import requests  # noqa: E402

_real_get = requests.get
CALLS = []


def fake_get(url, **kw):
    CALLS.append(url)
    body = json.dumps({"songs": [{"name": "我的地盘", "duration": 244640,
                                  "artists": [{"name": "周杰伦"}, {"name": ""}],
                                  "album": {"name": "七里香", "picUrl": "p.jpg"}}]})
    return FakeResp(text=body)


requests.get = fake_get
item, err = M.list_netease_track("https://music.163.com/song?id=186000", log=lambda *a: None)
ck("E1 免 Cookie 拿到元数据",
   (item.get("title"), item.get("artists"), item.get("duration_s"), item.get("album"))
   == ("我的地盘", "周杰伦", 245, "七里香") and not err,
   json.dumps(item, ensure_ascii=False)[:220] + " | " + err)
ck("E2 也是 needs_match 占位（接口不回音频地址）",
   item.get("needs_match") is True and item.get("url") == ""
   and item.get("musicdl_source") == "NeteaseMusicClient")
ck("E3 页地址回到那首歌", item.get("page_url") == "https://music.163.com/song?id=186000")
ck("E4 请求打的是 api/song/detail", "api/song/detail" in CALLS[0], CALLS[0])
requests.get = lambda url, **kw: FakeResp(text=json.dumps({"songs": []}))
ck("E5 空返回说实话", M.list_netease_track("https://music.163.com/song?id=1",
                                          log=lambda *a: None)[1] != "")
requests.get = _real_get
ck("E6 不是单曲链接不硬试",
   M.list_netease_track("https://music.163.com/playlist?id=1234567",
                        log=lambda *a: None)[1].startswith("链接里没有"))

print("== F. QQ 单曲的说法 ==")
note = M.qq_single_track_note("https://y.qq.com/n/ryqq/songdetail/0040B1amiZ1fBg")
ck("F1 点名免 Cookie 拿不到", "免 Cookie" in note and "曲名" in note, note)
ck("F2 不许写成接口不通", "接口不通" not in note and "连不上" not in note, note)
ck("F3 给出下一步（去搜索框）", "搜索" in note, note)
ck("F4 不是单曲页不给说法", M.qq_single_track_note("https://y.qq.com/portal/playlist.html") == "")

print("== G. parse_playlist 的路由 ==")
_real_list = M.list_spotify_playlist
_real_netease = M.list_netease_track
_real_unreach = M._unreachable_reason
_real_avail = M.musicdl_available
_real_musicdl = M._parse_playlist_via_musicdl
calls = {"musicdl": 0, "ytdlp": 0, "list": 0}
M._unreachable_reason = lambda *a, **k: ""
M.musicdl_available = lambda: True


def stub_musicdl(*a, **k):
    calls["musicdl"] += 1
    return [], ""


def stub_ytdlp(*a, **k):
    calls["ytdlp"] += 1
    return [], ""


M._parse_playlist_via_musicdl = stub_musicdl
M._ytdlp_playlist_parse = stub_ytdlp
def stub_list(url, **k):
    calls["list"] += 1
    return [], "", ""


M.list_spotify_playlist = stub_list
def run(url, srcs=("NeteaseMusicClient",), prefer="fast"):
    for k in calls:
        calls[k] = 0
    logs = []
    got = M.parse_playlist(url, sources=list(srcs),
                           log=lambda m, lvl="info": logs.append(f"[{lvl}] {m}"),
                           prefer=prefer)
    return got, logs, dict(M._LAST_PLAYLIST_DIAG)


M.list_spotify_track = lambda url, **k: ({}, "测试桩：这一轮拿不到元数据")
out, logs, diag = run("https://open.spotify.com/track/0VjI")
ck("G1 单曲链接走单曲分支（元数据拿不到就是拿不到）",
   out == [] and calls["musicdl"] == 0 and calls["list"] == 0,
   f"count={len(out)} musicdl={calls['musicdl']} list={calls['list']}")
ck("G1b 拿不到时把原因递出去，不静默转成歌单报错",
   any("测试桩" in l for l in logs), str(logs[-1:])[:200])
M.list_spotify_track = lambda url, **k: ({"title": "X", "needs_match": True, "id": ""}, "")
out, logs, diag = run("https://open.spotify.com/track/0VjI")
ck("G2 成功时只回来一条占位", len(out) == 1 and out[0]["needs_match"], str(len(out)))
ck("G3 不退回 musicdl 逐曲取址", calls["musicdl"] == 0, str(calls))
ck("G4 diag 记下走的是单曲分支", diag.get("engine") == "spotify-single", str(diag.get("engine")))
out, logs, diag = run("https://open.spotify.com/playlist/37i9")
ck("G5 歌单链接照旧走列表", calls["list"] == 1 and calls["musicdl"] <= 1
   and diag.get("engine") != "spotify-single", str(calls))
M.list_netease_track = lambda url, **k: ({"title": "我的地盘", "needs_match": True}, "")
out, logs, diag = run("https://music.163.com/song?id=186000")
ck("G6 网易云单曲同一条路", len(out) == 1 and out[0]["title"] == "我的地盘", str(out)[:120])
ck("G7 网易云单曲不惊动逐曲取址", calls["musicdl"] == 0
   and diag.get("engine") == "netease-single", str(calls))
out, logs, diag = run("https://y.qq.com/n/ryqq/songdetail/0040B1amiZ1fBg", ("QQMusicClient",))
ck("G8 QQ 单曲给的是那句话，不是通用报错",
   out == [] and "免 Cookie" in (diag.get("hint") or "") and calls["musicdl"] == 0,
   str(diag.get("hint"))[:120])
M.list_spotify_playlist, M.list_netease_track = _real_list, _real_netease
M._unreachable_reason, M.musicdl_available = _real_unreach, _real_avail
M._parse_playlist_via_musicdl = _real_musicdl

print("\n=== 结果 ===")
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
