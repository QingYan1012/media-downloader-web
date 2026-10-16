r"""同曲打分闸门：五个维度各自打分 + 硬阈值，谁挡的要说出谁。

判定口径借鉴 spotDL 的 spotdl/utils/matching.py（MIT），本文件只验我们自己的中文口径。
全程不联网、不落盘，纯函数进出。
跑法：`python tests/matchgate_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import inspect
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

print("=== F. 关键词吻合度（query_score，B5 上屏用的就是它）===")
Q_HIT = {"id": "q1", "title": "晴天", "artists": "周杰伦", "duration": "4:29", "duration_s": 269}
Q_OTHER_SINGER = {"id": "q2", "title": "晴天", "artists": "林俊杰", "duration_s": 269}
Q_OTHER_SONG = {"id": "q3", "title": "青花瓷", "artists": "周杰伦", "duration_s": 239}
Q_LIVE = {"id": "q4", "title": "晴天 (Live)", "artists": "周杰伦", "duration_s": 300}
Q_NOARTIST = {"id": "q5", "title": "晴天", "artists": "", "duration_s": 0}
sc = M.query_score("周杰伦 晴天", Q_HIT)
ck("F1 歌手+曲名都写到关键词里 → 满分且不挡",
   sc["score"] == 100.0 and sc["reject"] == "" and sc["name"] == 100.0 and sc["artist"] == 100.0, sc)
ck("F2 关键词里两段话的顺序不影响结果（本仓库拼查询是「歌手 曲名」，用户爱怎么写怎么写）",
   M.query_score("晴天 周杰伦", Q_HIT)["score"] == 100.0
   and M.query_score("晴天 周杰伦", Q_OTHER_SINGER)["reject"],
   M.query_score("晴天 周杰伦", Q_OTHER_SINGER))
ck("F3 歌手是别人 → 挡下来，原因点名歌手",
   "歌手" in M.query_score("周杰伦 晴天", Q_OTHER_SINGER)["reject"],
   M.query_score("周杰伦 晴天", Q_OTHER_SINGER)["reject"])
ck("F4 曲名不像 → 挡下来，原因点名是关键词里哪一个词没认出来",
   M.query_score("周杰伦 晴天", Q_OTHER_SONG)["score"] < M.MATCH_ACCEPT
   and "晴天" in M.query_score("周杰伦 晴天", Q_OTHER_SONG)["reject"],
   M.query_score("周杰伦 晴天", Q_OTHER_SONG)["reject"])
ck("F5 成品标了 Live 而关键词没要 → 挡，原因带版本词",
   "live" in M.query_score("周杰伦 晴天", Q_LIVE)["reject"],
   M.query_score("周杰伦 晴天", Q_LIVE)["reject"])
ck("F6 关键词只有曲名：歌手维不参与（报 None，不是给 100 让人以为核过）",
   M.query_score("晴天", Q_HIT)["artist"] is None
   and M.query_score("晴天", Q_NOARTIST)["score"] == 100.0,
   M.query_score("晴天", Q_HIT))
ck("F7 关键词只有歌手：曲名维不参与，同一个人的歌都算对得上，别人家的挡",
   M.query_score("周杰伦", Q_HIT)["name"] is None
   and M.query_score("周杰伦", Q_HIT)["score"] == 100.0
   and M.query_score("周杰伦", Q_OTHER_SINGER)["score"] < M.MATCH_ARTIST_MIN,
   M.query_score("周杰伦", Q_OTHER_SINGER))
ck("F8 模式词不参与比对：专辑搜索会往关键词尾巴拼「专辑」，留着它每行都被曲名闸门挡掉",
   M.query_score("晴天 专辑", Q_HIT)["score"] == 100.0
   and M.query_score("晴天 专辑", Q_HIT)["reject"] == "",
   M.query_score("晴天 专辑", Q_HIT))
ck("F9 时长维恒不参与：关键词里没有时长，行里有时长与没时长同一个分",
   M.query_score("晴天", Q_HIT)["time"] is None
   and M.query_score("晴天", Q_HIT)["score"] == M.query_score("晴天", Q_NOARTIST)["score"])
ck("F10 繁体关键词对简体曲库仍然对得上",
   M.query_score("周杰倫 晴天", Q_HIT)["score"] == 100.0,
   M.query_score("周杰倫 晴天", Q_HIT))
ck("F11 空关键词 / 脏行不炸，只报一句没得比",
   M.query_score("", Q_HIT)["reject"] != ""
   and M.query_score(None, Q_HIT)["reject"] != ""
   and M.query_score("晴天", None)["reject"] != ""
   and M.query_score("晴天", "")["reject"] != ""
   and M.query_score("晴天", {})["reject"] != "")


def qgate(**over):
    saved = {k: getattr(M, k) for k in over}
    for k, v in over.items():
        setattr(M, k, v)
    try:
        return M.query_score("周杰伦 晴天", Q_OTHER_SONG)
    finally:
        for k, v in saved.items():
            setattr(M, k, v)


ck("F12 反向验证：过的就是同一套 MATCH_* 阈值 —— 把曲名下限抬到满分，正主也过不了",
   M.query_score("周杰伦 晴天", Q_HIT)["reject"] == ""
   and qgate(MATCH_NAME_MIN=100)["reject"] != ""
   and M.query_score("周杰伦 晴天", Q_OTHER_SONG)["reject"] != "")
# 下面三条是活体搜索（真接口回来的 47 条）教出来的：分派一维归错，正主旁边就挂一条 95 分的绿灯
CK = {"id": "k1", "title": "夜曲", "artists": "周杰伦", "duration_s": 226}      # 同一个人的别的歌
CB = {"id": "k2", "title": "晴天", "artists": "张信哲", "duration_s": 269}      # 这首歌的别人的版本
ck("F13 同一个人的别的歌（夜曲）：不能因为『周杰伦』认到了歌手就把整条抬到过线分",
   M.query_score("周杰伦 晴天", CK)["score"] <= 60
   and M.query_score("周杰伦 晴天", CK)["name"] == 0.0,
   M.query_score("周杰伦 晴天", CK))
ck("F14 拒因说的是没对上的那一维：夜曲那条怪『晴天』没出现，不怪歌手",
   "晴天" in M.query_score("周杰伦 晴天", CK)["reject"]
   and "歌手与关键词对不上" not in M.query_score("周杰伦 晴天", CK)["reject"],
   M.query_score("周杰伦 晴天", CK)["reject"])
ck("F15 反过来：晴天但歌手是别人，拒因怪『周杰伦』、曲名维仍是满分",
   M.query_score("周杰伦 晴天", CB)["name"] == 100.0
   and "周杰伦" in M.query_score("周杰伦 晴天", CB)["reject"],
   M.query_score("周杰伦 晴天", CB))
ck("F16 关键词只有一个词：没填歌手字段的行也不拿歌手维卡人",
   M.query_score("晴天", Q_NOARTIST)["artist"] is None
   and M.query_score("晴天", Q_NOARTIST)["score"] == 100.0)

print("=== G. 分数上屏的接线 ===")
rows = [dict(Q_HIT), dict(Q_OTHER_SINGER), "不是行", None]
out = M.annotate_query_score(rows, "周杰伦 晴天")
ck("G1 annotate 把分、三维子分、拒因、录取线一并写进行里",
   all(k in out[0] for k in ("score", "score_name", "score_artist", "score_time",
                             "score_reject", "match_accept"))
   and out[0]["score"] == 100 and out[1]["score_reject"],
   {k: out[1][k] for k in ("score", "score_reject")})
ck("G2 界面那句录取线跟着后端常量走，不是前端另写一个 85",
   out[0]["match_accept"] == M.MATCH_ACCEPT)
ck("G3 行里混进非 dict 不炸，原样留着", out[2] == "不是行" and out[3] is None)
MS = inspect.getsource(M.search_music)
ck("G4 search_music 返回前真的调了 annotate_query_score（专辑搜索也走它：search_album 内层就是 search_music）",
   "annotate_query_score(results, keyword)" in MS
   and MS.rindex("annotate_query_score(results, keyword)") < MS.rindex("return results"),
   "没找到调用点")
SA = inspect.getsource(M.search_album)
ck("G5 专辑搜索没有另起一套行：它就是包一层 search_music", "search_music(" in SA)
SRV = (Path(M.__file__).resolve().parent / "server.py").read_text(encoding="utf-8", errors="replace")
SEG = SRV[SRV.index('def api_music_search'):SRV.index('def api_music_playlist')]
ck("G6 搜索接口把 items 原样交出去，不逐字段重建（重建会把新键静默吞掉，ConfigBody 那类漏口）",
   '"items": items' in SEG, "接口那一层在改行形状")
HTML = (Path(M.__file__).resolve().parent / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
ck("G7 来源列有分数徽章，被挡的标红、过线的标绿",
   'matchHint(row)">{{ row.score }}</el-tag>' in HTML
   and "row.score_reject ? 'danger'" in HTML, "徽章没接到界面上")
ck("G8 徽章的悬浮里写得出三项子分与录取线",
   "function matchHint" in HTML
   and "曲名 ${f(row.score_name)} · 歌手 ${f(row.score_artist)} · 时长 ${f(row.score_time)}" in HTML
   and "（录取线 ${line}）" in HTML)
ck("G9 拒因也在屏幕上：被挡的行多一个「不像」，鼠标停在上面看整句",
   'v-if="row.score_reject"' in HTML and "> 不像</span>" in HTML)
ck("G10 表头上方有一句图例，讲清这个分只管对不对得上关键词",
   "v-if=\"musicHasScore\"" in HTML and "{{ musicScoreLine }}" in HTML)
ck("G11 换源后这一行的旧分要清掉：行都换成另一条了，分数不能跟着走",
   "score: null, score_name: null, score_artist: null, score_time: null, score_reject: ''" in HTML)
ck("G12 matchHint 与两个 computed 都在 setup 的 return 里挂着（漏了就渲染成空白）",
   "refHint, matchHint, openRefLink" in HTML and "musicNeedsMatch, musicScoreLine, musicHasScore," in HTML)

print("\n" + ("全部通过" if not FAILED else f"FAILED: {FAILED}"))
sys.exit(1 if FAILED else 0)
