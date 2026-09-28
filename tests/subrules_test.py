r"""订阅按条规则自检。

两段：
  1) 纯内存跑规则清洗 / 逐条判定 / scan_one 入队 —— 假 engine、假 queue、save() 空转，
     不碰 subscriptions.json，也不联网。
  2) 打本机 server（127.0.0.1:8765）验 HTTP 口径 + 规则真的落盘；跑完把 subscriptions.json
     按原字节还原（G8），内存态要靠重启 server 才跟磁盘一致，所以收尾必须重启一次。

跑法：先起 server.py，再 `python tests/subrules_test.py`。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

BASE = "http://127.0.0.1:8765"
FAILED: list[str] = []
LOGS: list[str] = []
SUBS_SNAPSHOT = S.SUBS_FILE.read_bytes() if S.SUBS_FILE.exists() else None


def ck(name: str, cond, extra: str = ""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


# ---------------------------------------------------------------- 假组件
class FakeCfg:
    def __init__(self, **kw):
        d = dict(S.ConfigManager.DEFAULTS)
        d.update(kw)
        self.data = d


class FakeEngine:
    def __init__(self, entries):
        self.entries = entries

    def get_info(self, url, cfg):
        return {"_type": "playlist", "title": "测试频道", "entries": self.entries}


class FakeQueue:
    def __init__(self):
        self.batches = []

    def add_urls(self, urls, options):
        self.batches.append((list(urls), dict(options or {})))
        return [str(i) for i in range(len(urls))]


class FakeTG:
    def __init__(self):
        self.notices = []

    def notify_sub(self, title, n, samples):
        self.notices.append((title, n, list(samples or [])))


class MemSubs(S.SubscriptionManager):
    """只在内存里跑 —— 探针不许碰用户的 subscriptions.json。"""

    def load(self):
        self.subs = []

    def save(self):
        self.saved = getattr(self, "saved", 0) + 1


def ent(i, title, url, dur=None, live=False, vcodec=None):
    e = {"id": f"vid{i}", "title": title, "url": url, "webpage_url": url}
    if dur is not None:
        e["duration"] = dur
    if live:
        e["is_live"] = True
    if vcodec:
        e["vcodec"] = vcodec
    return e


ENTRIES = [
    ent(1, "第 1 期 正片", "https://www.youtube.com/watch?v=a1", 1200),
    ent(2, "切片 竖屏", "https://www.youtube.com/shorts/a2", 40),
    ent(3, "直播回放", "https://www.youtube.com/watch?v=a3", 3600, live=True),
    ent(4, "EP.12 播客节目", "https://www.youtube.com/watch?v=a4", 2400, vcodec="none"),
    ent(5, "第 2 期 正片", "https://www.youtube.com/watch?v=a5", 900),
    ent(6, "预告 第 3 期", "https://www.youtube.com/watch?v=a6", 30),
    ent(7, "没有时长信息的一期", "https://www.youtube.com/watch?v=a7"),
]


def new_mgr(entries=None, **cfgkw):
    q, tg = FakeQueue(), FakeTG()
    mgr = MemSubs(FakeEngine(entries or ENTRIES), FakeCfg(**cfgkw), q, tg,
                  lambda m, lv="info": LOGS.append(m))
    return mgr, q, tg


# ---------------------------------------------------------------- 1. 规则清洗
print("=== A. 规则清洗：垃圾值不留，越界值夹紧 ===")
ck("A1 老订阅没 rules → 沿用旧的单次 20 条封顶", S._norm_sub_rules(None) == {"max_per_scan": 20}, S._norm_sub_rules(None))
r = S._norm_sub_rules({"types": ["video", "bogus", "video"], "only_kw": "  ", "skip_kw": "预告，，会员",
                       "min_dur": "abc", "max_dur": 999999, "video_quality": "999p",
                       "format": "MKV", "run_ai": "maybe", "audio_only": 1})
ck("A2 只认合法类型且去重", r.get("types") == ["video"], r)
ck("A3 空关键词丢弃、中文逗号分词", "only_kw" not in r and r.get("skip_kw") == ["预告", "会员"], r)
ck("A4 非数字时长丢弃，越界时长夹到 86400", "min_dur" not in r and r.get("max_dur") == 86400, r)
ck("A5 不认识的画质丢弃，封装转小写", "video_quality" not in r and r.get("format") == "mkv", r)
ck("A6 run_ai 只认 on/off", "run_ai" not in r, r)
ck("A7 audio_only 真值落盘", r.get("audio_only") is True, r)
ck("A8 显式 0 = 单次不限条数", S._norm_sub_rules({"max_per_scan": 0})["max_per_scan"] == 0)
ck("A9 上限夹到 50", S._norm_sub_rules({"max_per_scan": 999})["max_per_scan"] == 50)
ck("A10 命名模板限长 200", len(S._norm_sub_rules({"filename_template": "x" * 500})["filename_template"]) == 200)
ck("A11 四种类型全选 = 不限类型", "types" not in S._norm_sub_rules({"types": list(S.SUB_TYPES)}))
ck("A12 类型重复勾选只记一份", S._norm_sub_rules({"types": ["video", "video", "live"]})["types"] == ["video", "live"])
saved = S._norm_sub_rules({"types": ["video"], "only_kw": "正片,教程", "skip_kw": ["预告", "直播"]})
ck("A13 存盘的列表形态直接吃", saved["skip_kw"] == ["预告", "直播"], saved)
ck("A14 清洗两次结果一致（读取时会反复清洗）", S._norm_sub_rules(saved) == saved, S._norm_sub_rules(saved))

# ---------------------------------------------------------------- 2. 条目分类与判定
print("=== B. 逐条判定：类型 / 时长 / 关键词 ===")
ck("B1 普通视频算长视频", S._sub_entry_kind(ENTRIES[0]) == "video")
ck("B2 /shorts/ 算短视频", S._sub_entry_kind(ENTRIES[1]) == "short")
ck("B3 is_live 算直播", S._sub_entry_kind(ENTRIES[2]) == "live")
ck("B4 vcodec=none 算音频", S._sub_entry_kind(ENTRIES[3]) == "audio")
ck("B5 podcast 链接算音频", S._sub_entry_kind(ent(9, "x", "https://podcast.example.com/e9")) == "audio")
ck("B6 live.bilibili.com 算直播", S._sub_entry_kind(ent(9, "x", "https://live.bilibili.com/123")) == "live")
ok, why = S._sub_rule_match(ENTRIES[1], S._norm_sub_rules({"types": ["video"]}))
ck("B7 只要长视频会挡掉短视频并给出原因", (not ok) and "短视频" in why, why)
ck("B8 时长偏短挡掉", not S._sub_rule_match(ENTRIES[5], S._norm_sub_rules({"min_dur": 300}))[0])
ck("B9 时长偏长挡掉", not S._sub_rule_match(ENTRIES[2], S._norm_sub_rules({"max_dur": 600}))[0])
ck("B10 平台没报时长的条目不被时长挡掉", S._sub_rule_match(ENTRIES[6], S._norm_sub_rules({"min_dur": 600}))[0])
ck("B11 标题关键词大小写不敏感", S._sub_rule_match(ent(1, "OFFICIAL Trailer", "u"), S._norm_sub_rules({"only_kw": "trailer"}))[0]
   and not S._sub_rule_match(ent(1, "正片", "u"), S._norm_sub_rules({"only_kw": "trailer"}))[0])
ck("B12 排除词一票否决（哪怕命中了关键词）", not S._sub_rule_match(ENTRIES[5], S._norm_sub_rules({"only_kw": "预告", "skip_kw": "预告"}))[0])
ck("B13 没规则时全部放行", S._sub_rule_match(ENTRIES[1], S._norm_sub_rules(None))[0])

# ---------------------------------------------------------------- 3. 规则摘要
print("=== C. 规则摘要要说人话 ===")
ck("C1 默认口径", S._sub_rules_text(S._norm_sub_rules(None)) == "每次最多 20 条", S._sub_rules_text(S._norm_sub_rules(None)))
full = S._norm_sub_rules({"types": ["video", "audio"], "min_dur": 300, "max_dur": 7200, "only_kw": "正片,教程",
                          "skip_kw": "预告", "audio_only": True, "video_quality": "1080p", "format": "mp4",
                          "run_ai": "on", "filename_template": "%(title)s.%(ext)s", "max_per_scan": 5})
t = S._sub_rules_text(full)
for frag in ("只要 长视频/音频/播客", "时长≥5分钟", "时长≤2.0小时", "标题含「正片」「教程」", "排除「预告」",
             "只下音频", "画质 1080p", "封装 mp4", "下完转写", "自定义命名", "每次最多 5 条"):
    ck(f"C2 摘要含「{frag}」", frag in t, t if frag not in t else "")
ck("C3 0 条上限读作不限", "单次不限条数" in S._sub_rules_text(S._norm_sub_rules({"max_per_scan": 0})))
ck("C4 run_ai=off 读作不转写", "不转写" in S._sub_rules_text(S._norm_sub_rules({"run_ai": "off"})))
ck("C5 1 分钟以下按秒说", S._fmt_dur(45) == "45秒" and S._fmt_dur(90) == "2分钟")

# ---------------------------------------------------------------- 4. 首次订阅
print("=== D. 首次订阅：首下载也受这条订阅的规则管 ===")
mgr, q, tg = new_mgr(sub_first_download_n=3)
sub = {"id": "s1", "url": "https://www.youtube.com/channel/x", "title": "", "last_ids": [],
       "rules": {"types": ["video", "audio"], "max_per_scan": 3}}
n = mgr.scan_one(sub)
urls, opts = q.batches[0]
ck("D1 首次下载按 first_n 封顶", n == 3 and len(urls) == 3, (n, urls))
ck("D2 短视频/直播没混进来", sorted(u.split("v=")[-1] for u in urls) == ["a1", "a4", "a5"], urls)
ck("D3 入队走订阅队列且默认不重下", opts.get("queue_name") == "subscribe" and opts.get("skip_downloaded") is True, opts)
ck("D4 日志写明按哪条规则下的", any("按规则[只要 长视频/音频/播客、每次最多 3 条]首次下载 3 条" in m for m in LOGS), LOGS[-1])
ck("D5 首次扫描记下全部 ID", len(sub["last_ids"]) == 7, sub["last_ids"])

# ---------------------------------------------------------------- 5. 增量扫描
print("=== E. 增量扫描：规则筛选 + 入队选项 + 上限顺延 ===")
LOGS.clear()
mgr, q, tg = new_mgr(sub_auto_download=True, video_quality="best", format="mkv")
sub = {"id": "s2", "url": "https://www.youtube.com/channel/x", "title": "测试频道",
       "last_ids": ["vid1", "vid2", "vid3", "vid4"],
       "rules": {"types": ["video"], "skip_kw": "预告", "video_quality": "720p",
                 "format": "mp4", "run_ai": "off",
                 "filename_template": "%(title)s.%(ext)s", "max_per_scan": 0}}
n = mgr.scan_one(sub)
urls, opts = q.batches[0]
ck("E1 新增条数按全部新条目计", n == 3, n)
ck("E2 预告被规则挡掉，只入队 2 条正片", len(urls) == 2 and sorted(u.split("v=")[-1] for u in urls) == ["a5", "a7"], urls)
ck("E3 画质/封装/命名按规则覆盖全局", opts["video_quality"] == "720p" and opts["format"] == "mp4"
   and opts["filename_template"] == "%(title)s.%(ext)s", opts)
ck("E4 run_ai=off 同时关掉转写和机翻", opts["local_ai_transcribe"] is False and opts["local_ai_translate"] is False, opts)
ck("E5 没设的规则项仍跟随全局", opts["audio_only"] is False and opts["audio_quality"] == "best", opts)
ck("E6 日志报了挡掉哪条为什么", any("规则挡掉 1 条" in m and "命中排除词「预告」" in m for m in LOGS), LOGS[-1])
ck("E7 Telegram 只推真正入队那几条", tg.notices and tg.notices[0][1] == 3 and len(tg.notices[0][2]) == 2, tg.notices)
mgr_r, q_r, _ = new_mgr(sub_auto_download=True)
sub_r = {"id": "s9", "url": "https://www.youtube.com/channel/x", "title": "测试频道",
         "last_ids": ["vid1", "vid2", "vid3", "vid4", "vid5", "vid7"],
         "rules": {"run_ai": "on", "audio_only": True, "format": "mp3"}}
mgr_r.scan_one(sub_r)
_u, o_r = q_r.batches[0]
ck("E8 run_ai=on 强制转写、只要音频与封装一起带进出队选项",
   o_r.get("local_ai_transcribe") is True and "local_ai_translate" not in o_r
   and o_r.get("audio_only") is True and o_r.get("format") == "mp3", o_r)
ck("E15 规则摘要在日志里对得上", any("按规则[只下音频、封装 mp3、下完转写、每次最多 20 条]" in m for m in LOGS), LOGS[-1])

mgr2, q2, _ = new_mgr(sub_auto_download=True)
sub2 = {"id": "s3", "url": "https://www.youtube.com/channel/x", "title": "测试频道",
        "last_ids": ["vid1", "vid2", "vid3", "vid4"],
        "rules": {"max_per_scan": 2}}
LOGS.clear()
mgr2.scan_one(sub2)
enqueued, _o = q2.batches[0]
ck("E9 单次上限只入队 2 条", len(enqueued) == 2, enqueued)
ck("E10 第 3 条不算见过，下次扫描还会补", "vid7" not in (sub2["last_ids"] or [])
   and "vid5" in sub2["last_ids"], sub2["last_ids"])
ck("E11 日志说明留到下次", any("留到下次扫描" in m for m in LOGS), LOGS[-1])

mgr3, q3, _ = new_mgr(sub_auto_download=False)
sub3 = {"id": "s4", "url": "u", "title": "测试频道", "last_ids": ["vid1"], "rules": {}}
LOGS.clear()
mgr3.scan_one(sub3)
ck("E12 全局自动下载关掉时不入队", not q3.batches, q3.batches)
ck("E13 日志说明未开自动下载", any("未开自动下载" in m for m in LOGS), LOGS[-1])
ck("E14 探针没写过盘", (S.SUBS_FILE.read_bytes() if S.SUBS_FILE.exists() else None) == SUBS_SNAPSHOT)

# ---------------------------------------------------------------- 6. set_rules
print("=== F. set_rules：先讲清楚再落盘 ===")
mgr4, _q4, _t4 = new_mgr()
mgr4.subs = [{"id": "s5", "url": "u", "title": "测试频道"}]
LOGS.clear()
try:
    mgr4.set_rules("s5", {"filename_template": "%(title)s.%(quality)s"})
    ck("F1 模板少了 ext 要拦住", False)
except ValueError as e:
    ck("F1 模板少了 ext 要拦住", "扩展名" in str(e), e)
try:
    mgr4.set_rules("nope", {})
    ck("F2 不存在的订阅直接报错", False)
except ValueError as e:
    ck("F2 不存在的订阅直接报错", "不存在" in str(e), e)
got = mgr4.set_rules("s5", {"only_kw": "正片", "max_per_scan": 7, "video_quality": "bogus"})
ck("F3 存进去的是清洗过的规则", got == {"only_kw": ["正片"], "max_per_scan": 7}, got)
ck("F4 保存后日志回读生效口径", any("规则已更新" in m and "标题含「正片」" in m for m in LOGS), LOGS[-1])

# ---------------------------------------------------------------- 7. HTTP
print("=== G. HTTP 口径（打真实 server，跑完按原字节还原 subscriptions.json） ===")


def http(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw).get("detail", raw)
        except Exception:
            return e.code, raw


code, data = http("GET", "/api/subs")
live_subs = data.get("subs", []) if isinstance(data, dict) else []
ck("G1 GET /api/subs 可用", code == 200, code)
ck("G2 每条订阅都带生效口径", all(isinstance(s.get("rules"), dict) and s.get("rules_text") for s in live_subs),
   [s.get("rules_text") for s in live_subs])
ck("G3 顺带下发选项表", isinstance(data.get("type_labels"), dict) and isinstance(data.get("qualities"), list)
   and isinstance(data.get("formats"), list), data.get("formats"))
c4, d4 = http("POST", "/api/subs/rules", {"id": "deadbeef00", "rules": {}})
ck("G4 不存在的订阅 404", c4 == 404, (c4, d4))
if live_subs:
    sid = live_subs[0]["id"]
    try:
        c5, d5 = http("POST", "/api/subs/rules", {"id": sid, "rules": {"filename_template": "%(title)s.%(quality)s"}})
        ck("G5 缺 %(ext)s 的模板 400 且话术能看懂", c5 == 400 and "扩展名" in str(d5), (c5, d5))
        c6, d6 = http("POST", "/api/subs/rules", {"id": sid, "rules": {"types": ["video"], "max_per_scan": 3,
                                                                      "skip_kw": "预告,直播", "min_dur": 300}})
        ck("G6 保存成功并回读摘要", c6 == 200 and "只要 长视频" in d6.get("rules_text", "")
           and "每次最多 3 条" in d6.get("rules_text", ""), d6.get("rules_text") if c6 == 200 else d6)
        on_disk = json.loads(S.SUBS_FILE.read_text(encoding="utf-8"))
        ck("G7 规则真的落盘", any(s.get("id") == sid and (s.get("rules") or {}).get("types") == ["video"] for s in on_disk),
           [s.get("rules") for s in on_disk])
        _c8, d8 = http("GET", "/api/subs")
        ck("G8 列表接口返回同一份规则", d8["subs"][0]["rules"]["skip_kw"] == ["预告", "直播"], d8["subs"][0]["rules"])
        _c8b, d8b = http("GET", "/api/subs")
        ck("G8b 连读两次规则不变形", d8b["subs"][0]["rules"] == d8["subs"][0]["rules"], d8b["subs"][0]["rules"])
    finally:
        if SUBS_SNAPSHOT is not None:
            S.SUBS_FILE.write_bytes(SUBS_SNAPSHOT)
            ck("G9 subscriptions.json 已按原字节还原", S.SUBS_FILE.read_bytes() == SUBS_SNAPSHOT)
            ck("G10 内存态需重启才与磁盘一致（收尾必做）", True)
else:
    print("（当前没有订阅，跳过落盘往返）")

print()
print("FAILED: " + (", ".join(FAILED) if FAILED else "none"))
sys.exit(1 if FAILED else 0)
