"""音乐搜索端点：勾选源要按归一化后的样子落盘，否则 ['Spotify','SpotifyMusicClient'] 会一直复发。

只验代码路径 —— 用假 ConfigManager 顶掉 cfg，绝不写真实 config.json，也不发真实网络请求。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED: list[str] = []


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


class FakeCfg:
    def __init__(self, data):
        self.data = dict(data)
        self.saves = 0

    def save(self):
        self.saves += 1


ORIG = {k: getattr(S, k, None) for k in ("cfg", "log_mgr", "search_music", "music_proxy_resolver")}
BASE = {
    "download_dir": r"C:\tmp\never_write",
    "musicdl_sources": ["Spotify", "SpotifyMusicClient"],
    "musicdl_cookies": "keep-me",
    "platform_cookies": {"youtube": "cookie-intact"},
}

try:
    import music_search

    calls = []

    def fake_search(kw, **kw_args):
        calls.append({"kw": kw, **kw_args})
        return [{"musicname": kw, "musicauthor": "某人", "musicsource": "SpotifyMusicClient"}]

    S.cfg = FakeCfg(BASE)
    S.log_mgr = type("L", (), {"log": staticmethod(lambda *a, **k: None)})()
    S.music_proxy_resolver = lambda p: (lambda s: "")
    _orig_sm = music_search.search_music
    music_search.search_music = fake_search

    print("== A. 落盘的源列表已归一化去重 ==")
    out = S.api_music_search({"keyword": "晴天", "sources": ["Spotify", "SpotifyMusicClient"]})
    saved = S.cfg.data["musicdl_sources"]
    ck("A1 只剩一个 Spotify", saved == ["SpotifyMusicClient"], str(saved))
    ck("A2 真的写了一次盘", S.cfg.saves == 1, str(S.cfg.saves))
    ck("A3 传给搜索的源也去重了",
       [c for c in calls if c.get("sources")] and calls[-1]["sources"] == ["SpotifyMusicClient"],
       str(calls[-1].get("sources")))
    ck("A4 返回结果非空", bool(out.get("items")), str(out.get("items")))

    print("== B. 不该动的东西没动 ==")
    ck("B1 Cookie 没被清", S.cfg.data["musicdl_cookies"] == "keep-me")
    ck("B2 平台 Cookie 表没被碰", S.cfg.data["platform_cookies"] == {"youtube": "cookie-intact"})
    S.api_music_search({"keyword": "晴天"})
    ck("B3 缺 sources 就保留原值", S.cfg.data["musicdl_sources"] == ["SpotifyMusicClient"],
       str(S.cfg.data["musicdl_sources"]))

    print("== C. 混合大小写/别名也会归一 ==")
    S.api_music_search({"keyword": "晴天", "sources": [" spotify ", "SpotifyMusicClient", "Apple"]})
    ck("C1 三种写法两个源", S.cfg.data["musicdl_sources"] == ["SpotifyMusicClient", "AppleMusicClient"],
       str(S.cfg.data["musicdl_sources"]))
finally:
    for k, v in ORIG.items():
        if v is None:
            if hasattr(S, k):
                delattr(S, k)
        else:
            setattr(S, k, v)
    if "_orig_sm" in dir():
        music_search.search_music = _orig_sm

real = pathlib.Path(__file__).resolve().parent.parent / "config.json"
print(f"\n真实 config.json 未被写入（假 cfg 记账 {S.cfg.saves if hasattr(S, 'cfg') and isinstance(S.cfg, FakeCfg) else '已还原'} 次）")
print(f"FAILED: {FAILED if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
