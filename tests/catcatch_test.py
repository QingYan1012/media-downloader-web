r"""猫抓（cat-catch）接收端的离线自检。

不联网、不碰下载目录：入队那一步换成替身，只看解析与传参；规则文件拐进临时目录。
跑法：`python tests/catcatch_test.py`（不需要先起 server）。
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED: list[str] = []


def ck(name: str, cond, extra=""):
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


class FakeReq:
    def __init__(self, raw: bytes):
        self._raw = raw

    async def body(self):
        return self._raw


def push(payload, as_text=None):
    raw = as_text if as_text is not None else json.dumps(payload).encode("utf-8")
    return asyncio.run(S.api_catcatch_push(FakeReq(raw)))


tmp = Path(tempfile.mkdtemp(prefix="md_cc_test_"))
S.CATCATCH_RULES_FILE = tmp / "catcatch_rules.json"
LOGS: list[tuple] = []
S.log_mgr = SimpleNamespace(log=lambda m, level="info", k="", kv=None: LOGS.append((level, str(m))))
ENQUEUED: list[tuple] = []


def fake_enqueue(urls, opts):
    ENQUEUED.append((list(urls), dict(opts or {})))
    return {"ok": True, "ids": [f"t{len(ENQUEUED)}"], "count": 1}


S._sniff_enqueue = fake_enqueue

# ---------- A. data 的四种版本形状 ----------
res_obj = {"url": "https://cdn.example.com/a.mp4", "name": "a.mp4",
           "requestHeaders": {"referer": "https://ex.com/", "cookie": "SESS=x"}}
ck("A1 data 是对象", S._catcatch_items(res_obj) == [res_obj])
ck("A2 data 是数组", len(S._catcatch_items([res_obj, res_obj])) == 2)
ck("A3 data 是字符串化 JSON", S._catcatch_items(json.dumps(res_obj)) == [res_obj])
ck("A4 data 是裸链接", S._catcatch_items("https://cdn.example.com/b.m3u8")
   == [{"url": "https://cdn.example.com/b.m3u8"}])
ck("A5 非链接的字符串不收", S._catcatch_items("catch") == [])
ck("A6 数组里再套字符串化数组", len(S._catcatch_items([json.dumps([res_obj, res_obj])])) == 2)

# ---------- B. HLS 密钥归一 ----------
KEY16 = bytes(range(1, 17))
hex16 = KEY16.hex()
b64 = base64.b64encode(KEY16).decode()
ck("B1 base64 → 16 进制", S._hls_key_to_hex(b64) == hex16, b64)
ck("B2 16 进制原样（转小写）", S._hls_key_to_hex(hex16.upper()) == hex16)
ck("B3 字节数组 → 16 进制", S._hls_key_to_hex(list(KEY16)) == hex16)
ck("B4 认不出的给空串", S._hls_key_to_hex("不是密钥!!") == "")
ck("B5 超长的不给（防把整段文本当密钥）", S._hls_key_to_hex("A" * 500) == "")

# ---------- C. 从猫抓导出配置里递归找正则规则 ----------
cc_conf = {
    "regexRule": [
        {"type": "request", "regex": r"\.mp4$", "ext": "mp4", "blackList": False, "state": "1"},
        {"type": "request", "regex": r"ads\.", "ext": "", "blackList": True, "state": "1"},
        {"type": "request", "regex": r"off\.", "ext": "m4a", "blackList": False, "state": "0"},
    ],
    "other": {"nested": json.dumps([{"regex": r"deep\.ts", "ext": "ts"}])},
}
found = S._collect_regex_rules(cc_conf)
ck("C1 顶层数组 + 深层字符串化都找到", len(found) == 4, f"got {len(found)}")
ck("C2 黑名单标记读对", sum(1 for r in found if r.get("blackList")) == 1)
ck("C3 没有 regex 的键不误收", S._collect_regex_rules({"a": {"b": [1, "x"]}}) == [])
# 规则数组本身挂在 regex 这个键名下（猫抓导出真会出现这形状）：旧写法只看「有没有这个键」，
# 会把整只容器当成一条规则（正则 = str(列表)，还可能编译得过），里面两条真规则一条都进不来。
cc_wrapped = {"regex": [
    {"regex": r"\.flac$", "ext": "flac", "blackList": False, "state": "1"},
    {"regex": r"ads\.", "ext": "", "blackList": True, "state": "1"},
]}
found_w = S._collect_regex_rules(cc_wrapped)
ck("C4 挂在 regex 键下的两条规则都找到", len(found_w) == 2, f"got {len(found_w)}")
ck("C5 找到的每条 regex 都是字符串（不是整只容器的 str）",
   all(isinstance(r.get("regex"), str) for r in found_w), str(found_w)[:90])
ck("C6 regex 值为空串或非字符串时不收、也不误收容器",
   S._collect_regex_rules({"regex": {"x": 1}}) == [] and S._collect_regex_rules({"regex": "   "}) == [])

# ---------- D. 导入端点：新增 / 重复 / 非法 ----------
r1 = S.api_catcatch_import_config({"text": json.dumps(cc_conf)})
ck("D1 四条里新增 4", r1["found"] == 4 and r1["added"] == 4, str(r1))
rules = json.loads(S.CATCATCH_RULES_FILE.read_text(encoding="utf-8"))
ck("D2 state=0 落成停用", [x["enabled"] for x in rules if x["ext"] == "m4a"] == [False])
ck("D3 blackList 落成排除", [x["blacklist"] for x in rules if x["blacklist"]] == [True])
r2 = S.api_catcatch_import_config({"text": json.dumps(cc_conf)})
ck("D4 再导一次全算重复", r2["added"] == 0 and r2["duplicated"] == 4, str(r2))
bad = {"rules": [{"regex": "([未闭合", "ext": "mp4"}]}
r3 = S.api_catcatch_import_config({"text": json.dumps(bad)})
ck("D5 非法正则跳过并回报原因", r3["added"] == 0 and len(r3["invalid"]) == 1, str(r3["invalid"]))
for msg, payload in (
    ("D6 空内容报 400", {"text": "  "}),
    ("D7 非 JSON 报 400", {"text": "这不是 JSON"}),
    ("D8 没有正则规则报 400", {"text": json.dumps({"theme": "dark"})}),
):
    try:
        S.api_catcatch_import_config(payload)
        ck(msg, False, "没报错")
    except S.HTTPException as e:
        ck(msg, e.status_code == 400 and bool(e.detail), str(e.detail)[:40])

_before_rules = S._load_catcatch_rules()
rw = S.api_catcatch_import_config({"text": json.dumps(cc_wrapped)})
_after_rules = S._load_catcatch_rules()
S._save_catcatch_rules(_before_rules)
ck("D9 挂在 regex 键下的配置逐条入库（旧写法这里只会 found=1，且入库的是假规则）",
   rw["found"] == 2 and rw["added"] == 1 and rw["duplicated"] == 1
   and [x["regex"] for x in _after_rules[len(_before_rules):]] == [r"\.flac$"], str(rw))

# ---------- E. 规则闸门 ----------
keep, ext, hit = S._catcatch_match("https://x.com/movie.mp4")
ck("E1 命中普通规则并带出扩展名", keep and ext == "mp4", f"{keep} {ext} {hit}")
ck("E1b 带查询串时行尾锚不命中（与猫抓按原文匹配一致）",
   S._catcatch_match("https://x.com/movie.mp4?t=1")[1] == "")
keep2, _, hit2 = S._catcatch_match("https://ads.example.com/trailer.mp4")
ck("E2 命中黑名单则挡下", not keep2 and hit2, hit2)
ck("E3 停用中的规则不参与", S._catcatch_match("https://x.com/off.m4a")[0] is True
   and S._catcatch_match("https://x.com/off.m4a")[1] == "")
ck("E4 一条没命中时照收", S._catcatch_match("https://x.com/other.mpd") == (True, "", ""))
S._save_catcatch_rules([])
ck("E5 没有规则时全收", S._catcatch_match("https://ads.example.com/a.mp4")[0] is True)

# ---------- F. 推送接收 ----------
LOGS.clear(); ENQUEUED.clear()
out = push({"action": "catch", "data": res_obj, "tabId": 7})
u, o = ENQUEUED[0]
ck("F1 回 ok 且带 received", out["ok"] and out["received"] == 1, str(out)[:80])
ck("F2 Referer 传进入队", o.get("referer") == "https://ex.com/")
ck("F3 Cookie 传进入队", o.get("cookie") == "SESS=x")
ck("F4 文件名取自推送的 name", o.get("title") == "a", str(o.get("title")))
ck("F5 推来的已是直链，跳过插件解析", o.get("skip_plugins") is True)
ck("F6 标签页号只当字符串用", o.get("hls_key") is None, "非 m3u8 不该带钥")
ck("F7 日志里不出现 Cookie 内容", not any("SESS=x" in m for _, m in LOGS), str(LOGS))
ck("F8 日志点名了带凭证", any("带 Cookie" in m for _, m in LOGS), str(LOGS))

S._save_catcatch_rules([{"name": "排除广告", "regex": r"ads\.", "ext": "",
                         "blacklist": True, "enabled": True}])
LOGS.clear(); ENQUEUED.clear()
out2 = push({"action": "catch",
             "data": [{"url": "https://ads.example.com/v.mp4", "name": "v.mp4"},
                      {"url": "https://cdn.example.com/ok.mp4", "name": "ok.mp4"}],
             "tabId": 8})
ck("F9 黑名单那条不入队", len(ENQUEUED) == 1 and ENQUEUED[0][0] == ["https://cdn.example.com/ok.mp4"])
ck("F10 回包里分开计数", out2["received"] == 1 and out2["dropped"] == 1, str(out2))
ck("F11 挡下时日志点名规则", any("排除广告" in m for _, m in LOGS), str(LOGS))
S._save_catcatch_rules([])

# ---------- G. 密钥 → 下一条 m3u8 ----------
LOGS.clear(); ENQUEUED.clear(); S._catcatch_keys.clear()
kr = push({"action": "addKey", "data": b64, "tabId": 11})
ck("G1 addKey 收下", kr.get("ok") is True)
ck("G2 日志不写密钥本身", not any(hex16 in m or b64 in m for _, m in LOGS), str(LOGS))
push({"action": "catch", "data": {"url": "https://cdn.example.com/master.m3u8", "name": "master.m3u8"},
      "tabId": 11})
ck("G3 同标签页的 m3u8 自动带钥", ENQUEUED and ENQUEUED[-1][1].get("hls_key") == hex16,
   str(ENQUEUED[-1][1] if ENQUEUED else {}))
S._catcatch_keys["11"]["ts"] = time.time() - S._CATCATCH_KEY_TTL - 5
ENQUEUED.clear()
push({"action": "catch", "data": {"url": "https://cdn.example.com/master.m3u8"}, "tabId": 11})
ck("G4 超时后不再带钥（反向验证）", ENQUEUED and "hls_key" not in ENQUEUED[-1][1])
push({"action": "catch", "data": {"url": "https://cdn.example.com/other.mpd"}, "tabId": 11})
ck("G5 非 HLS 不塞钥", "hls_key" not in ENQUEUED[-1][1])

# ---------- H. 各种坏请求体不炸服务 ----------
S._catcatch_keys.clear()
for name, raw in (
    ("H1 空 body", b""),
    ("H2 非 JSON", b"hello"),
    ("H3 JSON 但不是对象", b"[1,2,3]"),
    ("H4 缺 data", b'{"action":"catch"}'),
    ("H5 data 里没链接", b'{"action":"catch","data":{"name":"x"}}'),
):
    LOGS.clear(); ENQUEUED.clear()
    try:
        r = push(None, as_text=raw)
        ck(name, r.get("ok") is False and not ENQUEUED, str(r)[:60])
    except Exception as e:
        ck(name, False, f"抛异常 {type(e).__name__}: {e}")
LOGS.clear(); ENQUEUED.clear()
r6 = push({"action": "addKey", "data": "乱七八糟", "tabId": 3})
ck("H6 密钥认不出时回 ok=false 不抛", r6.get("ok") is False and not ENQUEUED)
ck("H7 认不出密钥时日志点名", any("没认出来" in m for _, m in LOGS), str(LOGS))

# ---------- I. 规则维护端点 ----------
S._save_catcatch_rules([
    {"name": "a", "regex": "a", "ext": "", "blacklist": False, "enabled": True},
    {"name": "b", "regex": "b", "ext": "", "blacklist": True, "enabled": True},
])
t = S.api_catcatch_rules_toggle({"index": 1})
ck("I1 开关只动那一条", t["rules"][1]["enabled"] is False and t["rules"][0]["enabled"] is True)
d = S.api_catcatch_rules_delete({"index": 0})
ck("I2 删除按编号", len(d["rules"]) == 1 and d["rules"][0]["name"] == "b")
for name, body in (("I3 编号缺失报 400", {}), ("I4 编号越界报 400", {"index": 99})):
    try:
        S.api_catcatch_rules_delete(body)
        ck(name, False, "没报错")
    except S.HTTPException as e:
        ck(name, e.status_code == 400)
c = S.api_catcatch_rules_clear()
ck("I5 清空后落盘是空表", c["rules"] == [] and json.loads(S.CATCATCH_RULES_FILE.read_text(encoding="utf-8")) == [])
st = S.api_catcatch_status()
ck("I6 状态里给得出接收地址", st["endpoint"].endswith("/api/catcatch/push") and "127.0.0.1" in st["endpoint"])
ck("I7 状态里给得出请求体模板", "${action}" in st["body_template"] and "${data}" in st["body_template"])

print()
print(f"共 {len(FAILED)} 项失败" if FAILED else "全部通过")
print("临时目录:", tmp)
if FAILED:
    for f in FAILED:
        print("  FAIL:", f)
    sys.exit(1)
