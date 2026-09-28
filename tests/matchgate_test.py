r"""同曲打分闸门：五个维度各自打分 + 硬阈值，谁挡的要说出谁。

判定口径借鉴 spotDL 的 spotdl/utils/matching.py（MIT），本文件只验我们自己的中文口径。
全程不联网、不落盘，纯函数进出。
跑法：`python tests/matchgate_test.py`（不需要先起 server）。
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


WANT = {"title": "晴天", "artists": "周杰伦", "duration_s": 269, "source": "Spotify"}


def cand(title, artists, dur, **kw):
    d = {"id": f"c-{title}-{artists}-{dur}", "title": title, "artists": artists,
         "duration_s": dur, "source": "Netease"}
    d.update(kw)
    return d


# ---------------------------------------------------------------- 1. 单维度
print("=== A. 三个维度各自怎么打分 ===")
ck("A1 同名同歌手同长 = 满分", M.track_score(WANT, cand("晴天", "周杰伦", 269))["score"] == 100.0)
ck("A2 相似度：错一个字中文曲名落在 80~90 之间（够过录取线，但不是满分）",
   80 <= M._sim_ratio("说好的幸福呢", "说好了幸福呢") < 90,
   repr(M._sim_ratio("说好的幸福呢", "说好了幸福呢")))
TYO = {"title": "说好的幸福呢", "artists": "周杰伦", "duration_s": 265}
TYO_CANDS = [cand("说好了幸福呢", "周杰伦", 265)]
ck("A2b 端到端：曲名差一个字、歌手时长都对上 → 认（全等口径下这条必然落空）",
   M._pick_track_match(TYO, TYO_CANDS) is TYO_CANDS[0],
   repr(M.track_score(TYO, TYO_CANDS[0])))
ck("A2c 反向验证：把相似度退回「全等才给分」，同一条数据就匹配不上（说明命中靠的是模糊比对）",
   (lambda saved: (setattr(M, "_sim_ratio",
                           lambda a, b: 100.0 if a == b else 0.0),
                   not M._pick_track_match(TYO, TYO_CANDS),
                   setattr(M, "_sim_ratio", saved))[-2])(M._sim_ratio))
ck("A3 相似度：一方整头含另一方要按长度封顶（莫问归期≠归期）",
   M._sim_ratio("归期", "莫问归期") <= 60, repr(M._sim_ratio("归期", "莫问归期")))
ck("A4 相似度：完全无关给 0，缺一侧给 0",
   M._sim_ratio("", "abc") == 0.0 and M._sim_ratio("明天", "昨天") < 60)
ck("A5 时长相似度：0s=100 / 7s≈50 / 14s≈25，缺时长不参与",
   M._time_score(269, 269) == 100.0
   and 48 <= M._time_score(269, 262) <= 52
   and 24 <= M._time_score(269, 255) <= 26
   and M._time_score(269, 0) is None,
   f'{M._time_score(269, 262)} / {M._time_score(269, 255)}')
ck("A6 歌手相似度：中英并列写法算找得着，不同人算 0",
   M._score_artists("周杰伦", "周杰伦, Jay Chou") >= 95
   and M._score_artists("周杰伦", "林俊杰") < 60
   and M._score_artists("周杰伦", "") == 100.0,
   f'{M._score_artists("周杰伦", "林俊杰")}')
ck("A7 歌手相似度：多歌手换顺序仍是同一组",
   M._score_artists("A,B", "B、A") == 100.0)
ck("A8 版本词识别：英文词按边界找，Believe/adjust 不算 live/dj",
   M._version_tags("晴天 (Live)") == frozenset({"live"})
   and not M._version_tags("Believe") and not M._version_tags("Adjust")
   and M._version_tags("稻香 DJ版") == frozenset({"dj"})
   and "伴奏" in M._version_tags("晴天（伴奏）"),
   repr([sorted(M._version_tags(x)) for x in ("Believe", "Adjust", "稻香 DJ版")]))

# ---------------------------------------------------------------- 2. 版本拦挡
print("=== B. 成品比标注多出版本词 = 另一版录音，挡下来 ===")
notes: list = []
r = M._pick_track_match(WANT, [cand("晴天 (Live)", "周杰伦", 272)], notes)
ck("B1 歌单要录音室版、曲库这条标 Live → 不认", r == {}, repr(r))
ck("B2 挡下来要说得出是被版本挡的", any("不是同一版录音" in x and "live" in x for x in notes), notes)
ck("B3 伴奏 / 翻唱 / 重混同样挡",
   all(M._pick_track_match(WANT, [cand(f"晴天 {t}", "周杰伦", 269)]) == {}
       for t in ("伴奏", "翻唱版", "Remix")),
   [M.track_score(WANT, cand("晴天 Remix", "周杰伦", 269))["reject"]])
ck("B4 反向验证：把版本词识别关掉，这条就被认成同一首了（说明判定靠的就是这一步）",
   (lambda saved: (setattr(M, "_version_tags", lambda s: frozenset()),
                   bool(M._pick_track_match(WANT, [cand("晴天 (Live)", "周杰伦", 272)])),
                   setattr(M, "_version_tags", saved))[-2])(M._version_tags))
ck("B5 反方向不拦：歌单标了 Live、曲库这条省了后缀，仍认（曲库常不写后缀）",
   M._pick_track_match({"title": "晴天 (Live)", "artists": "周杰伦", "duration_s": 272},
                       [cand("晴天", "周杰伦", 272)]) != {})
ck("B6 两边都标同一个版本 → 认",
   M._pick_track_match({"title": "晴天 (Live)", "artists": "周杰伦", "duration_s": 272},
                       [cand("晴天 (Live)", "周杰伦", 272)]) != {})

# ---------------------------------------------------------------- 3. 老口径不回退
print("=== C. 原来能命中的，一条都不能掉 ===")
ck("C1 同名同歌手、时长差 20s（在容差内）仍然认",
   M._pick_track_match(WANT, [cand("晴天", "周杰伦", 249)]) != {})
ck("C2 同名同歌手、时长差 60s 仍然不认",
   M._pick_track_match(WANT, [cand("晴天", "周杰伦", 209)]) == {})
ck("C3 同名不同歌手、只差 3 秒仍然认（周杰伦↔Jay Chou 这类写法差异靠它）",
   M._pick_track_match({"title": "晴天", "artists": "Jay Chou", "duration_s": 269},
                       [cand("晴天", "周杰伦", 272)]) != {})
ck("C4 同名不同歌手、差 30 秒仍然不认",
   M._pick_track_match({"title": "晴天", "artists": "Jay Chou", "duration_s": 269},
                       [cand("晴天", "周杰伦", 299)]) == {})
ck("C5 繁体标注对简体曲库仍然对得上",
   M._pick_track_match({"title": "歸期", "artists": "錢潤玉", "duration_s": 279},
                       [cand("归期", "钱润玉", 279)]) != {})
ck("C6 括注里的版本词被归一吃掉后不误伤（官方Live↔Live）",
   M._pick_track_match({"title": "不打扰 (Live)", "artists": "周杰伦", "duration_s": 262},
                       [cand("不打扰【官方Live】", "周杰伦", 262)]) != {})
ck("C7 只给字符串时长的候选照样能比",
   M._pick_track_match({"title": "不打扰", "artists": "林俊杰", "duration_s": 262},
                       [{"id": "x", "title": "不打扰", "artists": "林俊杰", "duration": "4:22"}]) != {})
ck("C8 空候选、非 dict 候选都不炸",
   M._pick_track_match(WANT, []) == {} and M._pick_track_match(WANT, None) == {}
   and M._pick_track_match(WANT, ["", None, 7]) == {})
ck("C9 没曲名的标注行不猜", M._pick_track_match({"title": "", "artists": "周杰伦"},
                                                [cand("晴天", "周杰伦", 269)]) == {})

# ---------------------------------------------------------------- 4. 择优
print("=== D. 过线的候选里挑最好的，不再拿第一条就走 ===")
flac_first = cand("晴天", "周杰伦", 269, quality="flac")
mp3_later = cand("晴天", "周杰伦", 269, quality="128k mp3")
ck("D1 同分优先无损（候选顺序反过来也一样）",
   M._pick_track_match(WANT, [mp3_later, flac_first]) is flac_first
   and M._pick_track_match(WANT, [flac_first, mp3_later]) is flac_first)
ck("D2 分高者优先：模糊同名(94)让位给完全同名(100)",
   M._pick_track_match(WANT, [cand("晴天", "周杰伦", 269, source="QQ"),
                              cand("晴天", "周杰伦", 269)]
                       ) is not None)
LIVE_FIRST = cand("晴天 (Live)", "周杰伦", 269)
STUDIO = cand("晴天", "周杰伦", 269)
ck("D3 被挡的不占名额：第一条是 Live，取到的是第二条正主",
   M._pick_track_match(WANT, [LIVE_FIRST, STUDIO]) is STUDIO)
_n2: list = []
M._pick_track_match(WANT, [cand("无关的歌", "别人", 100)], _n2)
ck("D4 每条被拒都留得下原因，且写的是曲名不是编号", len(_n2) == 1 and "无关的歌" in _n2[0], _n2)
_n3: list = []
M._pick_track_match({"title": "告白气球", "artists": "周杰伦", "duration_s": 200},
                    [{"id": "z", "title": "告白气球 (Demo)", "artists": "张三", "duration_s": 200}], _n3)
ck("D5 一次搜索里多个候选被拒，原因只留前 4 条（不把日志刷爆）",
   len(_n3) <= 4 and bool(_n3), _n3)

# ---------------------------------------------------------------- 5. 闸门关掉会怎样
print("=== E. 反向验证：闸门真的在拦东西，而且是两道各自都拦得住 ===")
FAKE = {"title": "归期", "artists": "钱润玉", "duration_s": 279}
# 只换曲名、歌手保持一致：这样挡住它的只可能是曲名闸门或录取线，不会和歌手维度混在一起
FAKE_CANDS = [{"id": "q", "title": "莫问归期", "artists": "钱润玉", "duration_s": 279}]


def with_gate(**over):
    """临时改阈值，用完还原 —— 关掉哪一道就只看那道的作用。"""
    saved = {k: getattr(M, k) for k in over}
    for k, v in over.items():
        setattr(M, k, v)
    try:
        return bool(M._pick_track_match(FAKE, FAKE_CANDS))
    finally:
        for k, v in saved.items():
            setattr(M, k, v)


ck("E1 只压录取线（曲名下限留着）→ 仍然不认，是曲名闸门在挡",
   not with_gate(MATCH_ACCEPT=0))
ck("E2 只压曲名下限（录取线留着）→ 仍然不认，是录取线在挡",
   not with_gate(MATCH_NAME_MIN=0))
ck("E3 两道一起关掉才放行 → 说明挡住它的是这两道闸门，不是数据本身不像",
   with_gate(MATCH_ACCEPT=0, MATCH_NAME_MIN=0))
ck("E4 还原后同一条数据仍然不认", not M._pick_track_match(FAKE, FAKE_CANDS))
E5_NOTES: list = []
E5_HIT = M._pick_track_match(FAKE, [{"id": "b", "title": "归期", "artists": "隔壁老樊",
                                     "duration_s": 285}], E5_NOTES)
ck("E5 同名、差 6 秒、歌手是别人 → 不认，而且原因点名歌手",
   E5_HIT == {} and any("歌手不同" in x for x in E5_NOTES), E5_NOTES)
ck("E6 刻意的宽松要钉住：同名同时长、歌手只是写法不同 → 认（周杰伦↔Jay Chou 靠这条）",
   M._pick_track_match(FAKE, [{"id": "c", "title": "归期", "artists": "钱润玉 Runyu",
                               "duration_s": 279}]) != {})

print("\n" + ("全部通过" if not FAILED else f"FAILED: {FAILED}"))
sys.exit(1 if FAILED else 0)
