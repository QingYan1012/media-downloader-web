r"""匹配口径的两处修正：繁简归一 + 歌手分隔符不能被提前吃掉。

全程不联网、不落盘：只用纯函数 _norm_text / _song_fingerprint / _track_key /
_pick_track_match / merge_duplicate_tracks / dedupe_results。
跑法：`python tests/zhnorm_test.py`（不需要先起 server）。
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


def without_zh(fn):
    """把被测功能关掉再跑一遍：真出问题的话这条断言就该翻过来。"""
    saved = M._zh_convert
    M._zh_convert = None
    try:
        return fn()
    finally:
        M._zh_convert = saved


# ---- 1) 繁简归一 ----
ck("Z1 繁體歌名与简体歌名归一到同一个 key",
   M._norm_text("歸期") == M._norm_text("归期") == "归期",
   f'{M._norm_text("歸期")!r} / {M._norm_text("归期")!r}')
ck("Z2 繁體歌手名同样归一",
   M._norm_text("錢潤玉") == "钱润玉", repr(M._norm_text("錢潤玉")))
ck("Z3 繁體版本词也能被剥掉（剥词的表是简体写的）",
   M._norm_text("歸期【官方】") == M._norm_text("归期") == M._norm_text("归期（现场）"),
   repr(M._norm_text("歸期【官方】")))
ck("Z4 反向验证：关掉繁简转换后繁体与简体就分开了（说明判定靠的就是这一步）",
   without_zh(lambda: M._norm_text("歸期") != M._norm_text("归期")))
ck("Z5 简体串过一遍不被改坏（繁转简是幂等的单向映射）",
   all(M._norm_text(s) == M._norm_text(M._norm_text(s))
       for s in ("归期", "钱润玉Runyu", "愛人錯過", "帶我去找夜生活")))
ck("Z6 空串与纯英文不受影响",
   M._norm_text("") == "" and M._norm_text("Yesterday") == "yesterday")

# ---- 2) 端到端：繁體占位行到简体候选 ----
WANT = {"title": "歸期", "artists": "錢潤玉", "duration_s": 279}
CANDS = [{"title": "归期", "artists": "钱润玉", "duration_s": 279, "source": "NeteaseMusicClient"}]
ck("Z7 繁體歌单里的歌能在简体曲库里匹配上（修复前这里是必然落空）",
   M._pick_track_match(WANT, CANDS) is CANDS[0],
   repr(M._pick_track_match(WANT, CANDS)))
ck("Z8 反向验证：关掉繁简转换后同一组数据匹配不到",
   without_zh(lambda: not M._pick_track_match(WANT, CANDS)))
ck("Z9 没有放宽判据：同名不同歌手、时长差 30s 仍然不认",
   not M._pick_track_match(WANT, [dict(CANDS[0], artists="别人", duration_s=309)]))
ck("Z10 没有放宽判据：歌名真不同（莫问归期）仍然不认",
   not M._pick_track_match(WANT, [dict(CANDS[0], title="莫问归期")]))

# ---- 3) 歌手分隔符 ----
fp = lambda a: M._song_fingerprint({"title": "T", "artists": a})  # noqa: E731
ck("F1 多歌手换顺序不再算成两首歌",
   fp("A,B") == fp("B,A") == fp("A/B") == fp("B/A") == fp("A、B") == fp("B & A") == "t|a,b",
   repr([fp(x) for x in ("A,B", "B,A", "A/B", "A、B", "B & A")]))
ck("F2 反向验证：整串先归一会把顺序固化进串里（ab 与 ba 不相等，切分形同虚设）",
   (M._norm_text("A,B"), M._norm_text("B,A")) == ("ab", "ba")
   and fp("A,B") == fp("B,A"),
   f'旧口径 {(M._norm_text("A,B"), M._norm_text("B,A"))} / 新指纹 {fp("A,B")}')
ck("F3 与 _track_key 口径一致",
   all(M._song_fingerprint({"title": t, "artists": a}) ==
       M._track_key({"title": t, "artists": a})
       for t, a in (("歸期", "錢潤玉"), ("归期", "B,A"), ("x", "甲、乙"))),
   repr([M._song_fingerprint({"title": "x", "artists": "B,A"}),
         M._track_key({"title": "x", "artists": "B,A"})]))
ck("F4 单歌手不受影响", fp("錢潤玉") == "t|钱润玉", repr(fp("錢潤玉")))
ck("F5 空歌手字段仍是空段（不会凭空多出分隔符）",
   fp("") == "t|" and M._song_fingerprint({"title": "T", "artists": ""}, within_source=True) == "|t|")

# ---- 4) 列表侧：合并与去重 ----
rows = [{"song_name": "歸期", "singers": "錢潤玉", "duration_s": 279},
        {"song_name": "归期", "singers": "钱润玉", "duration_s": 279},
        {"song_name": "歸期", "singers": "别人", "duration_s": 279}]
merged = M.merge_duplicate_tracks(rows)
ck("L1 繁體行与简体行在列表里合成一行并标 ×2",
   len(merged) == 2 and merged[0].get("dup_count") == 2,
   f'{len(merged)} 行, dup_count={merged[0].get("dup_count")}')
kept, skipped = M.drop_duplicate_tracks(rows)
ck("L2 下载入口同样只下一遍", kept == {0, 2} and skipped == [{"title": "歸期", "count": 2}],
   f"{sorted(kept)} {skipped}")
ck("L3 反向验证：关掉繁简转换后繁體行与简体行各算一首",
   len(without_zh(lambda: M.merge_duplicate_tracks(list(rows)))) == 3)
ck("L4 _track_norm 没有因为加了繁简归一就被放宽（括注/版本词仍保留）",
   M._track_key({"title": "归期(Live)", "singers": "钱润玉"})
   != M._track_key({"title": "归期(录音室)", "singers": "钱润玉"}))
dup_items = [{"title": "歸期", "artists": "B,A", "source": "Netease", "quality": "320kbps"},
             {"title": "归期", "artists": "A,B", "source": "QQ", "quality": "flac"}]
ck("L5 搜索结果跨源去重：写法不同但同一首歌只留一条",
   len(M.dedupe_results(dup_items, "global")) == 1,
   repr(M.dedupe_results(dup_items, "global")))
ck("L6 反向验证：源内去重仍按源分开（不同源不会互相吃掉）",
   len(M.dedupe_results(dup_items, "source")) == 2)

print("FAILED: " + ("; ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
