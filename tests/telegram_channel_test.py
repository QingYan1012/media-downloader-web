"""telegram_channel 离线解析测试：用真实抓下来的 t.me/s/ 页面当 fixture。

fixture 是 2026-09-20 从 europa_press / audiobook_english / telegram 三个公开频道
存的原始页面，覆盖视频（含 blured / not_supported 两种变体）、文档、图片三类。
只加 --live 时才真联网，默认测试不依赖网络。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import telegram_channel as T  # noqa: E402

FAILED: list[str] = []
FIX = pathlib.Path(__file__).resolve().parent / "fixtures"


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


def load(ch):
    return (FIX / f"tg_s_{ch}.html").read_text(encoding="utf-8")


print("== A. 频道名归一 ==")
ck("A1 t.me/s/ 链接", T.normalize_channel("https://t.me/s/europa_press") == "europa_press")
ck("A2 @频道", T.normalize_channel("@europa_press") == "europa_press")
ck("A3 裸名 + 尾斜杠", T.normalize_channel(" Europa_Press/ ") == "Europa_Press")
ck("A4 帖子链接取频道", T.normalize_channel("t.me/europa_press/18446") == "europa_press")
ck("A5 telegram.me 也认", T.normalize_channel("https://telegram.me/durov") == "durov")
ck("A6 私有 c/ 判死", T.normalize_channel("https://t.me/c/1122334455/77") == "")
ck("A7 太短/非法名判死", T.normalize_channel("ab") == "" and T.normalize_channel("1bad") == "")
ck("A8 空输入不炸", T.normalize_channel("") == "" and T.normalize_channel(None) == "")

print("== B. 视频帖解析 ==")
vids = T.parse_messages(load("europa_press"), "europa_press")
ck("B1 只出媒体条目", len(vids) == 7, f"{len(vids)} 条")
ck("B2 全是视频", all(r["type"] == "video" for r in vids))
one = vids[0]
ck("B3 帖子号/下载 URL", one["post_id"] and one["url"] == f"https://t.me/europa_press/{one['post_id']}", one["url"])
ck("B4 时长解析成秒", any(r["duration_sec"] == 14 for r in vids), str([r["duration"] for r in vids[:3]]))
ck("B5 有封面", all(r["thumb"].startswith("https://") for r in vids))
ck("B6 可下载的那些直链带 token",
   all("token=" in r["direct_url"] for r in vids if r["downloadable"]))
ck("B7 标题取正文并去掉 emoji 图", "As" in vids[0]["title"] or len(vids[0]["title"]) > 8, vids[0]["title"][:36])
ck("B8 日期是 ISO 日", all(r["date"].startswith("202") for r in vids), str({r["date"] for r in vids}))
ck("B9 只有 3 条匿名可下", sum(1 for r in vids if r["downloadable"]) == 3,
   f'{sum(1 for r in vids if r["downloadable"])}/{len(vids)}')
ck("B10 帖子号互不相同", len({r["id"] for r in vids}) == len(vids))
ck("B11 拿不到直链的照样列出并写原因",
   all(not r["downloadable"] and r["note"] for r in vids if not r["direct_url"]),
   str({r["note"][:18] for r in vids if not r["direct_url"]}))

print("== C. 文档 / 图片帖 ==")
docs = T.parse_messages(load("audiobook_english"), "audiobook_english")
d = [r for r in docs if r["type"] == "document"]
p = [r for r in docs if r["type"] == "photo"]
ck("C1 解析出文档条目", len(d) == 7, f"{len(d)} 个")
ck("C2 文件名与大小", d[0]["filename"].endswith(".epub") and d[0]["size_text"], f'{d[0]["filename"]} / {d[0]["size_text"]}')
ck("C3 文档标为需登录", all(not r["downloadable"] and "登录" in r["note"] for r in d))
ck("C4 图片单独归类不误报", len(p) == 6 and all("图片" in r["note"] for r in p))
audio_rows = T.parse_messages(
    load("audiobook_english").replace("BooksWithAudio).epub", "BooksWithAudio).m4a"),
    "audiobook_english")
ck("C5 音频按扩展名归类", any(r["type"] == "audio" and r["filename"].endswith(".m4a") for r in audio_rows),
   str({t: sum(r["type"] == t for r in audio_rows) for t in T.ALL_TYPES}))

print("== D. 混排频道 ==")
mixed = T.parse_messages(load("telegram"), "telegram")
ck("D1 视频+图片都在", sum(r["type"] == "video" for r in mixed) == 13 and sum(r["type"] == "photo" for r in mixed) == 3,
   str({t: sum(r["type"] == t for r in mixed) for t in T.ALL_TYPES}))
ck("D2 换频道名不误吞", T.parse_messages(load("telegram"), "other_channel") == [])
ck("D3 空页/脏页不炸", T.parse_messages("", "x") == [] and T.parse_messages("<html>nothing</html>", "x") == [])

print("== E. 只留指定类型的过滤 ==")
want = [r for r in mixed if r["type"] == "video"]
ck("E1 类型过滤后无图片", len(want) == 13)
ck("E2 同帖多视频各占一行", len({r["id"] for r in want}) <= len(want))

print("== F. 日期窗与上限（打桩翻页） ==")
pages = [load("europa_press")]
orig_fetch = T._fetch
T._fetch = lambda u, params, proxy, timeout: (200, pages[0])
try:
    items, diag = T.list_channel_history("europa_press", limit=3, budget=0, page_sleep=0, log=lambda *a: None)
    ck("F1 limit 生效", len(items) == 3, f"{len(items)} 条")
    ck("F2 诊断记了页数与结论", diag["pages"] >= 1 and "上限" in diag["stopped"], diag["stopped"])
    ck("F5 只能列出的条数进了结论",
       diag["no_link"] == sum(1 for r in items if not r["downloadable"]) and "匿名下不动" in diag["stopped"],
       f'{diag["no_link"]} · {diag["stopped"]}')
    items2, diag2 = T.list_channel_history("europa_press", limit=50, since="2030-01-01",
                                           budget=0, page_sleep=0, log=lambda *a: None)
    ck("F3 日期窗把整页挡掉后收工", items2 == [] and "2030" in diag2["stopped"], diag2["stopped"])
    items3, diag3 = T.list_channel_history("t.me/c/999/1", limit=5, log=lambda *a: None)
    ck("F4 私有链接直接判死", items3 == [] and "无效" in diag3["stopped"], diag3["stopped"])
finally:
    T._fetch = orig_fetch

print("== G. 限流 / HTTP 错误要说清 ==")
for code, key in ((429, "限流"), (404, "HTTP 404")):
    T._fetch = lambda u, params, proxy, timeout, _c=code: (_c, "boom")
    try:
        it, dg = T.list_channel_history("europa_press", limit=50, page_sleep=0, log=lambda *a: None)
        ck(f"G{code} 非 200 不静默", it == [] and key in dg["stopped"], dg["stopped"])
    finally:
        T._fetch = orig_fetch

print("== H. 占位页不能当成「到底了」 ==")
PLACEHOLDER = ('<div class="tgme_page_wrap"><div class="tgme_page_extra">@zz_no_such</div>'
               '<span class="tgme_page_username">Telegram: Contact @zz_no_such</span></div>')
T._fetch = lambda u, params, proxy, timeout: (200, PLACEHOLDER)
try:
    it, dg = T.list_channel_history("zz_no_such_channel", limit=10, page_sleep=0, log=lambda *a: None)
    ck("H1 200 占位页判为频道不可用", it == [] and "频道不存在" in dg["stopped"], dg["stopped"])
    ck("H2 不误报成历史到底", "到底了" not in dg["stopped"])
    ck("H3 报错明细留了一行", bool(dg["errors"]), str(list(dg["errors"].items())[:1]))
finally:
    T._fetch = orig_fetch

print("== I. 代理三档真的传到 requests ==")
import requests as _rq  # noqa: E402
_orig_get = _rq.get
cap: list[dict] = []


class _Resp:
    status_code = 200
    text = ""


def spy_get(url, **kw):
    cap.append(kw)
    return _Resp()


_rq.get = spy_get
try:
    T._fetch("https://t.me/s/x", None, T.PROXY_DIRECT, (5, 5))
    T._fetch("https://t.me/s/x", None, "http://127.0.0.1:7897", (5, 5))
    T._fetch("https://t.me/s/x", None, "", (5, 5))
    ck("I1 强制直连压过系统代理", cap[0]["proxies"] == {"http": None, "https": None}, str(cap[0]["proxies"]))
    ck("I2 填了地址两个协议都走", cap[1]["proxies"] == {"http": "http://127.0.0.1:7897",
                                                        "https": "http://127.0.0.1:7897"})
    ck("I3 空值=不干预，跟随系统", cap[2]["proxies"] is None, str(cap[2]["proxies"]))
    ck("I4 带 UA，别被当成脚本直接拒", all("Mozilla" in k["headers"]["User-Agent"] for k in cap))
finally:
    _rq.get = _orig_get

if "--live" in sys.argv:
    print("== L. 真实联网冒烟（只列不下载） ==")
    try:
        live, ld = T.list_channel_history("europa_press", limit=5, budget=90,
                                          page_sleep=0.5, log=print)
        ck("L1 真频道列出条目", len(live) >= 3, f"{len(live)} 条")
        ck("L2 每条都有 yt-dlp 能吃的帖子链接",
           all(r["url"].startswith("https://t.me/") for r in live))
        ck("L3 诊断有页数", ld["pages"] >= 1 and ld["media_posts"] >= 5, str({k: ld[k] for k in ('pages', 'media_posts', 'stopped')}))
    except Exception as e:
        ck("L0 联网冒烟没抛异常", False, f"{type(e).__name__}: {e}")

print(f"\nFAILED: {FAILED if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
