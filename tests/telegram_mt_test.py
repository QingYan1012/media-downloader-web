"""telegram_mt 离线测试：不起网络、不登录，只验纯逻辑和「没配好时要说清楚」。

登录本身测不了（要真人手机号 + my.telegram.org 的 api_id），所以这里守住三件事：
链接分流别抢 yt-dlp 的活、条目形状前端能直接用、缺凭据/缺登录时报的是人话而不是堆栈。
"""
import pathlib
import sys
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import telegram_mt as M  # noqa: E402
from telegram_channel import TYPE_AUDIO, TYPE_DOCUMENT, TYPE_PHOTO, TYPE_VIDEO, TYPE_VOICE  # noqa: E402

FAILED: list[str] = []
TMP = pathlib.Path(tempfile.mkdtemp(prefix="md_tgmt_"))


def ck(name, cond, got=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{got}]" if got else ""))
    if not cond:
        FAILED.append(name)


_ATTR = {TYPE_VOICE: "voice", TYPE_VIDEO: "video", TYPE_AUDIO: "audio",
         TYPE_PHOTO: "photo", TYPE_DOCUMENT: "file"}


def msg(media=None, kind=None, mid=42, text="周一早报",
        date=datetime(2026, 9, 20, 8, 30, tzinfo=timezone.utc), chat_id=-1001234567890):
    m = SimpleNamespace(id=mid, text=text, date=date, media=media, chat_id=chat_id,
                        to_id=None, video_note=None)
    for name in _ATTR.values():
        setattr(m, name, None)
    if kind:
        setattr(m, _ATTR[kind], media)
    return m


INFO = {"peer": "-1001234567890", "title": "内部频道", "username": "",
        "noforwards": False, "is_channel": True}

print("== A. 链接分流：只抢该抢的 ==")
ck("A1 自家方案带 idx", M.parse_tgmt("tgmt://-100123/42?idx=2") == {"chat": "-100123", "msg": 42, "idx": 2})
ck("A2 私有 t.me/c/ 归一成 -100 id",
   M.parse_tgmt("https://t.me/c/123456/789?single") == {"chat": "-100123456", "msg": 789, "idx": 0})
ck("A3 公开帖子留给 yt-dlp", M.parse_tgmt("https://t.me/europa_press/18446") is None)
ck("A4 别的站点不误食",
   all(M.parse_tgmt(u) is None for u in
       ("https://www.youtube.com/watch?v=abc", "tgmt://x/abc", "tgmt://x", "", None)))

print("== B. 频道名归一：用户粘什么都能吃下 ==")
for raw, want in (("@durov", "durov"), ("https://t.me/s/durov", "durov"),
                  ("t.me/durov/123", "durov"), ("  durov  ", "durov"),
                  ("https://t.me/c/123456/789", "-100123456"), ("-100123456", "-100123456")):
    ck(f"B {raw.strip()!r} → {want}", M.normalize_entity(raw) == want, M.normalize_entity(raw))
ck("B7 非法输入判空", all(M.normalize_entity(x) == "" for x in ("", "  ", "ab", "1bad", "http://x.com/y")))

print("== C. 媒体类型判定 ==")
cases = [
    (TYPE_VOICE, SimpleNamespace(size=1024, attributes=[], mime_type="audio/ogg")),
    (TYPE_VIDEO, SimpleNamespace(size=1, attributes=[], mime_type="video/mp4")),
    (TYPE_AUDIO, SimpleNamespace(size=1, attributes=[], mime_type="audio/mpeg")),
    (TYPE_PHOTO, SimpleNamespace(size=1, attributes=[], mime_type="")),
    (TYPE_DOCUMENT, SimpleNamespace(size=1, name="lectures.epub", mime_type="application/epub+zip")),
    (TYPE_AUDIO, SimpleNamespace(size=1, name="lecture.m4a", mime_type="application/octet-stream")),
]
for want, media in cases:
    got = M._media_kind(msg(media, want))[0]
    ck(f"C 归类 {want}", got == want, got)

print("== D. 条目形状：前端拿到的字段要对得上匿名那套 ==")
media = SimpleNamespace(size=5 * 1024 * 1024, attributes=[SimpleNamespace(file_name="clip.mp4")],
                        mime_type="video/mp4", duration=95, title="")
r = M._row(INFO, msg(media, TYPE_VIDEO), TYPE_VIDEO, media, 0)
need = {"id", "channel", "peer", "post_id", "media_index", "url", "mt_url", "date", "datetime",
        "text", "type", "title", "duration", "duration_sec", "filename", "size_text",
        "thumb", "direct_url", "downloadable", "note", "protected"}
ck("D1 字段齐全", need <= set(r), str(sorted(need - set(r))))
ck("D2 类型/时长/大小", r["type"] == TYPE_VIDEO and r["duration"] == "1:35" and r["size_text"] == "5.0 MB",
   f'{r["duration"]} / {r["size_text"]}')
ck("D3 会话条目可下载", r["downloadable"] and not r["protected"] and r["note"] == "")
ck("D4 私有频道也给出链接", r["url"] == "https://t.me/c/1234567890/42" and
   r["mt_url"] == "tgmt://-1001234567890/42", f'{r["url"]} | {r["mt_url"]}')
pub = M._row(dict(INFO, username="durov", peer="-1001"), msg(media, TYPE_VIDEO), TYPE_VIDEO, media, 0)
ck("D5 有用户名就用用户名（裸 id 要靠会话缓存）", pub["mt_url"].startswith("tgmt://durov/"), pub["mt_url"])
prot = M._row(dict(INFO, noforwards=True), msg(media, TYPE_VIDEO), TYPE_VIDEO, media, 0)
ck("D6 受限频道标出来并写原因", prot["protected"] and "限制保存内容" in prot["note"], prot["note"])
ck("D7 相册第二条也带 idx", M._row(INFO, msg(media, TYPE_VIDEO), TYPE_VIDEO, media, 1)["mt_url"].endswith("?idx=1"))

print("== E. 文件名安全 ==")
n1 = M._safe_name("", msg(media, TYPE_VIDEO), media, TYPE_VIDEO, 5)
n2 = M._safe_name("{date}#{msg}.{type}", msg(media, TYPE_VIDEO), media, TYPE_VIDEO, 5)
ck("E1 默认用日期+正文", n1 == "2026-09-20 周一早报.mp4", n1)
ck("E2 模板能展开（自带后缀就照办）", n2 == "2026-09-20#42.video", n2)
ck("E3 非法字符换掉", all(c not in M._safe_name("", msg(media, TYPE_VIDEO,
                         text='a/b\\c:d*e?f"g<h>i|j'), media, TYPE_VIDEO, 5) for c in '\\/:*?"<>|'))
ck("E4 无后缀时补上", M._safe_name("plain", msg(media, TYPE_VIDEO), media, TYPE_VIDEO, 5).endswith(".mp4"),
   M._safe_name("plain", msg(media, TYPE_VIDEO), media, TYPE_VIDEO, 5))
yt = M._safe_name("%(title).60B [%(id)s].%(ext)s", msg(media, TYPE_VIDEO), media, TYPE_VIDEO, 5)
ck("E5 认得全局设置里的 yt-dlp 模板写法", yt == "周一早报 [42].mp4", yt)
ck("E6 不认的占位符不留残渣", "%" not in M._safe_name("%(uploader)s-%(title)s", msg(media, TYPE_VIDEO),
                                                     media, TYPE_VIDEO, 5))

print("== F. 下载记录（跳过已下）==")
idx = M.MediaIndex(TMP / "index.json")
f = TMP / "a file.mp4"
f.write_bytes(b"x" * 10)
idx.mark("-1001", 42, 0, 1024, str(f), "标题")
ck("F1 记过的能查到", idx.seen("-1001", 42, 0, 1024) == str(f))
ck("F2 换大小/换 idx 不算同一条", idx.seen("-1001", 42, 0, 999) == "" and idx.seen("-1001", 42, 1, 1024) == "")
f.unlink()
ck("F3 文件已删就不算下过", idx.seen("-1001", 42, 0, 1024) == "")
ck("F4 重新加载读得到", M.MediaIndex(TMP / "index.json").get(idx.key("-1001", 42, 0, 1024)) is not None)
ck("F5 坏文件不炸", M.MediaIndex(TMP / "nope.json").data == {} and
   M.MediaIndex((TMP / "index.json")).seen("x", 1, 0) == "")

print("== G. 没配好时的报错要能照着做 ==")
cfg = {}
ses = M.TelegramSession(lambda: dict(cfg), log=lambda *a: None,
                        session_dir=TMP / "sess", index_path=TMP / "index.json")
st = ses.status()
ck("G1 Telethon 装着", st["installed"] is True, st["version"])
ck("G2 没凭据 = 未配置未登录", st["configured"] is False and st["logged_in"] is False)
ck("G3 session 目录没被凭空建出来或写脏", not (TMP / "sess").exists() or not list((TMP / "sess").iterdir()))
# 与 server.py 的调用方式完全一致，防参数名漂移
ok, path, err = ses.download_ref(
    "tgmt://-1001234567890/42", str(TMP / "out"),
    audio_only=False, filename_template="", progress=lambda *a: None,
    stopped=lambda: False, force=False)
ck("G4 缺凭据直接失败", ok is False and path == "", str((ok, path)))
ck("G5 说的是去哪拿 api_id", "my.telegram.org" in err, err)
ok2, _, err2 = ses.download_ref("https://example.com/x", str(TMP / "out"))
ck("G6 非会话链接拒收", ok2 is False and "Telegram 会话链" in err2, err2)
try:
    ses.send_code("abc")
    ck("G7 手机号太短要拦", False, "没拦")
except ValueError as e:
    ck("G7 手机号太短要拦", "国家码" in str(e), str(e))
try:
    ses.sign_in("12345")
    ck("G8 没发码就登录要拦", False, "没拦")
except RuntimeError as e:
    ck("G8 没发码就登录要拦", "发验证码" in str(e), str(e))
cfg["tgmt_proxy"] = "http://127.0.0.1:7897"
try:
    ses._proxy()
    ck("G9 代理格式错要报错", False, "没报")
except ValueError as e:
    ck("G9 代理格式错要报错", "host:port" in str(e), str(e))
cfg["tgmt_proxy"] = "socks5://127.0.0.1:7897"
ck("G10 代理能解析成 (host, port)", ses._proxy() == ("127.0.0.1", 7897), str(ses._proxy()))

print("== H. 报错翻译表覆盖真实异常 ==")
from telethon import errors  # noqa: E402


def _mk(cls, **kw):
    try:
        return cls(**kw)
    except Exception:
        return RuntimeError(getattr(cls, "__name__", "x"))


ck("H1 限制保存内容 → 说清是频道主人的设置",
   "限制保存内容" in M._download_err_cn(_mk(errors.ChatForwardsRestrictedError)),
   M._download_err_cn(_mk(errors.ChatForwardsRestrictedError)))
ck("H2 会话失效 → 让人重新登录", "重新登录" in M._download_err_cn(_mk(errors.AuthKeyUnregisteredError)))
ck("H3 私有频道 → 说这个账号没加入", "没加入" in M._lookup_err_cn(_mk(errors.ChannelPrivateError)))
ck("H4 频道不存在 → 不谎称历史到底", "找不到" in M._lookup_err_cn(_mk(errors.UsernameNotOccupiedError)))
ck("H5 验证码错 → 提示重发", "重新" in M._login_err_cn(_mk(errors.PhoneCodeInvalidError)))
ck("H6 两步验证 → 提示填云密码", "两步验证" in M._login_err_cn(_mk(errors.SessionPasswordNeededError)))
ck("H7 未知异常也不空着", M._lookup_err_cn(RuntimeError("boom")).startswith("读取失败"), M._lookup_err_cn(RuntimeError("boom")))

print(f"\nFAILED: {FAILED if FAILED else 'none'}")
print(f"临时目录: {TMP}")
sys.exit(1 if FAILED else 0)
