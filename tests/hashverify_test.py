r"""成品校验值核对（期望 MD5/SHA 比对）离线自检。

钉的是四件事：
1. 写法收拢只有一处实现，而且收不拢时说的是「哪一位不对」，不是静默按一边算 ——
   复制漏字符最常见的后果是一句没头没尾的「对不上」，那会把人往「下载坏了」那条路上带。
2. 摘要是真算的：>1MB 的文件必须读到尾巴（只读文件头也能「算出」一个摘要，那种绿是假的）。
3. 对不上的话术分两支：链接下载下完还要转封装/嵌字幕，成品字节是本机重写过的，
   拿发布方给的原文件摘要去对必然不同 —— 把这归成下载坏了是冤枉；磁力/种子那种原样落盘才是真可比。
4. 接线：AddUrlsBody 得真声明这两个键（没声明的键会在 model_dump 那一步静默丢掉，本项目的 G2 那类 bug），
   核对走的还是 verify_note 那条通道（卡片与历史 tooltip 自动带上），而且落在 verify_download 闸门之外、
   网盘转存之前。

跑法：PYTHONIOENCODING=utf-8 python tests/hashverify_test.py
"""
import hashlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import server as S  # noqa: E402

SRC = Path(S.__file__).read_text(encoding="utf-8")
HTML = (APP / "static" / "index.html").read_text(encoding="utf-8")
# 界面文字的唯一真源搬到了词表（#53 多语言）：这两条原本在模板里写死，现在在 i18n.js 的 zh 那一份里
I18N_ZH = (APP / "static" / "i18n.js").read_text(encoding="utf-8").split("\n    en: {")[0]
FAILED = []
TOTAL = 0
TMP = Path(tempfile.mkdtemp(prefix="md_hashverify_"))


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{str(extra)[:260]}]")


MD5 = "d41d8cd98f00b204e9800998ecf8427e"          # 空文件的 MD5
SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"  # 空文件的 SHA-1
SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # 空文件的 SHA-256

print("== A. 写法收拢：认得来的、认不来要说清 ==")
ck("A1 留空 / None = 没让核对（三个都是空，不是报错）",
   S.normalize_hash_expect("", "auto") == ("", "", "")
   and S.normalize_hash_expect(None, None) == ("", "", ""), S.normalize_hash_expect("  ", "auto"))
ck("A2 32 位十六进制 → 按长度认成 MD5",
   S.normalize_hash_expect(MD5) == (MD5, "md5", ""), S.normalize_hash_expect(MD5))
ck("A3 40 位 → SHA-1，64 位 → SHA-256，128 位 → SHA-512",
   S.normalize_hash_expect(SHA1)[1] == "sha1" and S.normalize_hash_expect(SHA256)[1] == "sha256"
   and S.normalize_hash_expect("a" * 128)[1] == "sha512",
   [S.normalize_hash_expect(x)[1] for x in (SHA1, SHA256, "a" * 128)])
ck("A4 大写、空格、UUID 那种连字符都收得下（粘出来的样子五花八门）",
   S.normalize_hash_expect(MD5.upper())[0] == MD5
   and S.normalize_hash_expect("d41d8cd9-8f00-b204-e980-0998ecf8427e")[0] == MD5
   and S.normalize_hash_expect(" e3b0c442 98fc1c14 9afbf4c8 996fb924 27ae41e4 649b934c a495991b 7852b855 ")[0] == SHA256,
   S.normalize_hash_expect("d41d8cd9-8f00-b204-e980-0998ecf8427e"))
ck("A5 站点页与磁力参数那种 sha256= / MD5: 前缀先剥掉",
   S.normalize_hash_expect("sha256=" + SHA256, "auto")[0] == SHA256
   and S.normalize_hash_expect("MD5: " + MD5)[1] == "md5",
   S.normalize_hash_expect("sha256=" + SHA256))
ck("A6 算法名的写法（SHA-256 / sha256 / SHA2-256 / sha-2-256）都收到 sha256",
   all(S.normalize_hash_algo(x) == "sha256" for x in ("SHA-256", "sha256", "SHA2-256", "sha-2-256", "sha256")),
   [S.normalize_hash_algo(x) for x in ("SHA-256", "SHA2-256", "sha-2-256")])
ck("A7 只写 sha / sha2 这种半截名字时不猜：交回长度反推",
   S.normalize_hash_algo("sha") == "" and S.normalize_hash_algo("sha2") == ""
   and S.normalize_hash_expect(SHA256, "sha2")[1] == "sha256", S.normalize_hash_expect(SHA256, "sha"))
ck("A8 混进非十六进制字符 → 点名是哪个字符，并说 Base64 那种写法收不了",
   "不是十六进制的字符" in S.normalize_hash_expect("sha256=jZ8OiX+abc=", "sha256")[2]
   and "Base64" in S.normalize_hash_expect("z" * 64)[2], S.normalize_hash_expect("z" * 64)[2])
ck("A9 长度不是任何一家（6 位）→ 把四家的位数摆出来，让人知道差多少",
   "MD5 是 32 位" in S.normalize_hash_expect("abc123")[2] and "SHA-512 是 128 位" in S.normalize_hash_expect("abc123")[2],
   S.normalize_hash_expect("abc123")[2])
ck("A10 明说 SHA-256 却只给 63 位（复制漏一位）→ 当场说「应该 64 位、现在 63 位」",
   "应该是 64 位" in S.normalize_hash_expect(SHA256[:-1], "sha256")[2]
   and "63 位" in S.normalize_hash_expect(SHA256[:-1], "sha256")[2],
   S.normalize_hash_expect(SHA256[:-1], "sha256")[2])
ck("A11 明说 SHA-256 给的是 MD5 长度 → 顺带说一句「看着更像 MD5」",
   "更像 MD5" in S.normalize_hash_expect(MD5, "sha256")[2], S.normalize_hash_expect(MD5, "sha256")[2])
ck("A12 算法与长度一致时不因「两边都写了」报错（界面点 MD5 + 粘 32 位是常态）",
   S.normalize_hash_expect(MD5, "MD5") == (MD5, "md5", ""), S.normalize_hash_expect(MD5, "MD5"))
_a13 = S.normalize_hash_expect(" SHA256: " + SHA256, "auto")
_b13 = S.normalize_hash_expect(_a13[0], _a13[1])
ck("A13 收拢是幂等的：api_download 收一遍、add_urls 再收一遍，第二遍不该变成错",
   _b13[:2] == (SHA256, "sha256") and _b13[2] == "", (_a13, _b13))
ck("A14 只有分隔符的串算「没让核对」，不是一句错",
   S.normalize_hash_expect("::--") == ("", "", "期望校验值是空的") and S.normalize_hash_expect("   ") == ("", "", ""))

print("== B. 摘要是真算的（分块读到尾巴，不是只读文件头） ==")
small = TMP / "small.bin"
small.write_bytes(b"media-downloader-hash-probe")
ck("B1 小文件 MD5 与 hashlib 直接算的一致",
   S.hash_media_file(small, "md5") == hashlib.md5(small.read_bytes()).hexdigest(),
   S.hash_media_file(small, "md5"))
ck("B2 同一个文件的 sha256 / sha1 / sha512 都对得上",
   all(S.hash_media_file(small, a) == getattr(hashlib, a)(small.read_bytes()).hexdigest()
       for a in ("sha1", "sha256", "sha512")))
big = TMP / "big.bin"
head = b"A" * (1 << 20)
big.write_bytes(head + b"tail-1")
d1 = S.hash_media_file(big, "sha256")
big.write_bytes(head + b"tail-2")   # 前面 1MB 一字不差，只有尾巴变了
d2 = S.hash_media_file(big, "sha256")
ck("B3 只改 1MB 之后的尾巴，摘要就得变（只读文件头的话这条会红）",
   bool(d1) and bool(d2) and d1 != d2, (d1, d2))
ck("B4 和 hashlib 在 1MB+ 的文件上逐字节一致",
   d2 == hashlib.sha256(big.read_bytes()).hexdigest())
ck("B5 认不出的算法名不瞎算，返回空串", S.hash_media_file(small, "md5 ") == "" and S.hash_media_file(small, "") == "")
ck("B6 文件不在 / 是个目录 → 空串，不抛异常",
   S.hash_media_file(TMP / "没有这个文件.bin", "md5") == "" and S.hash_media_file(TMP, "md5") == "",
   S.hash_media_file(TMP, "md5"))

print("== C. 对不上的两句话说的是两件事 ==")
steps = ["封装成 mkv", "内嵌封面"]
st, got, note = S.hash_readback(small, hashlib.md5(small.read_bytes()).hexdigest(), "md5", [])
ck("C1 一致 → 结论 ok、有实算值、卡片那一句是空的（不亮橙色）",
   st == "ok" and len(got) == 32 and note == "", (st, got, note))
ck("C2 没让核对（期望值空）→ 三个都空，不去读文件", S.hash_readback(small, "", "md5", []) == ("", "", ""))
ck("C3 算法名不合法时也不去比对（宁可闭嘴）", S.hash_readback(small, "0" * 32, "crc32", []) == ("", "", ""))
ck("C4 期望值是大写粘来的也能判成一致",
   S.hash_readback(small, hashlib.md5(small.read_bytes()).hexdigest().upper(), "md5", [])[0] == "ok")
st4, _g4, n4 = S.hash_readback(small, "0" * 32, "md5", [])
ck("C5 原样落盘那支：说「不是期望的那一支」，并承诺文件没删",
   st4 == "bad" and "不是期望的那一支" in n4 and "文件已保留" in n4, n4)
st5, _g5, n5 = S.hash_readback(small, "0" * 32, "md5", steps)
ck("C6 本机重写过那一支：点名是哪几步，且不说「不是期望的那一支」这种冤枉话",
   st5 == "bad" and "本来就不会相同" in n5 and "封装成 mkv" in n5 and "磁力/种子" in n5
   and "不是期望的那一支" not in n5, n5)
st6, g6, n6 = S.hash_readback(TMP / "被移走了.bin", "0" * 32, "md5", steps)
ck("C7 成品读不出来 → unknown + 「这一项没法判」，不假装对上了",
   st6 == "unknown" and g6 == "" and "没法判" in n6, (st6, n6))
ck("C8 句子里给的是缩写（头 8 尾 6），不是全长 64 个字符（卡片不撑破）",
   SHA256 not in S.hash_readback(small, SHA256[:-8] + "0" * 8, "sha256", [])[2]
   and "…" in S.hash_readback(small, SHA256[:-8] + "0" * 8, "sha256", [])[2],
   S.hash_readback(small, SHA256[:-8] + "0" * 8, "sha256", [])[2])
ck("C9 一句不超过 400 字符（进历史与悬浮提示，长了没法看）",
   max(len(n4), len(n5), len(n6)) <= 400, (len(n4), len(n5), len(n6)))

print("== D. 「会不会重写成品字节」判的是同一批开关 ==")
ck("D1 默认那一套（封装 mkv + 嵌封面/元数据/章节/字幕）全被点名",
   all(k in S.hash_rewrite_steps({"format": "mkv", "embed_thumb": True, "embed_meta": True,
                                  "embed_chapters": True, "embed_sub": True}, "link")
       for k in ("封装成 mkv", "内嵌封面", "内嵌元数据", "内嵌章节", "内嵌字幕")),
   S.hash_rewrite_steps({"format": "mkv", "embed_thumb": True, "embed_meta": True,
                         "embed_chapters": True, "embed_sub": True}, "link"))
ck("D2 种子（aria2 原样落盘）一律不算重写：这一支才是真可比的那一支",
   S.hash_rewrite_steps({"format": "mkv", "embed_thumb": True, "embed_sub": True}, "torrent") == [])
ck("D3 容器是 mp3/m4a/flac 时说「抽成音频」，不是「封装成」",
   S.hash_rewrite_steps({"format": "flac"}, "link") == ["抽成音频（flac）"],
   S.hash_rewrite_steps({"format": "flac"}, "link"))
ck("D4 SponsorBlock 只标记也算重写（它要往容器里写章节）",
   "按 SponsorBlock 处理广告段" in S.hash_rewrite_steps({"format": "", "sponsorblock": "mark"}, "link"),
   S.hash_rewrite_steps({"format": "", "sponsorblock": "mark"}, "link"))
ck("D5 全关掉、容器不指定 → 空名单（这条直链是真原样落盘，期望值可比）",
   S.hash_rewrite_steps({"format": "", "embed_thumb": False, "embed_meta": False,
                         "embed_chapters": False, "embed_sub": False, "sponsorblock": "off",
                         "download_section": "", "use_hls_engine": False,
                         "local_ai_transcribe": False, "local_ai_translate": False}, "link") == [])
ck("D6 选段与 HLS 专用引擎各自单独算一步",
   "按时间点选段" in S.hash_rewrite_steps({"format": "", "download_section": "60-120"}, "link")
   and "HLS 专用引擎合并" in S.hash_rewrite_steps({"format": "", "use_hls_engine": True}, "link"))

print("== E. 入队接口与任务字段（G2 那一类：没声明的键会静默丢掉） ==")
b = S.AddUrlsBody(urls=["https://example.com/v"], expect_hash=SHA256, hash_algo="sha256")
ck("E1 AddUrlsBody 真声明了这两个键",
   {"expect_hash", "hash_algo"} <= set(S.AddUrlsBody.model_fields), sorted(S.AddUrlsBody.model_fields))
ck("E2 model_dump 之后值还在（声明了才会走到 preflight/add_urls）",
   b.model_dump().get("expect_hash") == SHA256 and b.model_dump().get("hash_algo") == "sha256",
   {k: v for k, v in b.model_dump().items() if "hash" in k})
ck("E3 不传 = None / auto：老调用方（MCP、扩展）不用改也不会误开核对",
   S.AddUrlsBody(urls=["u"]).model_dump()["expect_hash"] is None
   and S.AddUrlsBody(urls=["u"]).model_dump()["hash_algo"] == "auto")
t = S.DownloadTask(id="t-h", url="https://example.com/v")
d = t.to_dict()
ck("E4 任务四个字段默认全空（没核对时界面一个都不出现）",
   t.expect_hash == "" and t.hash_algo == "" and t.file_hash == "" and t.hash_state == "")
ck("E5 四个字段都出得来（asdict 自动，SSE 不用改）",
   all(k in d for k in ("expect_hash", "hash_algo", "file_hash", "hash_state")),
   sorted(k for k in d if "hash" in k))


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))


class FakeCfg:
    def __init__(self):
        self.data = {"concurrent": 3, "plugins_enabled": False, "download_dir": str(TMP)}

    def get(self, k, default=None):
        return self.data.get(k, default)


q = S.TaskQueue(SimpleNamespace(log=None), FakeCfg(), FakeLog(), SimpleNamespace(add=lambda *a, **k: None))
q.engine = SimpleNamespace(log=lambda *a, **k: None, pop_listed_max=lambda _t: 0)
ids = q.add_urls(["https://example.com/one"], {"expect_hash": " SHA256: " + SHA256, "hash_algo": "auto",
                                               "download_later": True})
tk = q.tasks[ids[0]]
ck("E6 入队就把收拢好的期望值挂到任务上（界面看到的是干净的那一串）",
   tk.expect_hash == SHA256 and tk.hash_algo == "sha256", (tk.expect_hash, tk.hash_algo))
ids2 = q.add_urls(["https://example.com/two"], {"expect_hash": "abc123", "download_later": True})
tk2 = q.tasks[ids2[0]]
ck("E7 别的入队口（订阅规则/嗅探/MCP）交了不像摘要的东西：忽略它并记一行，不带着脏值跑",
   tk2.expect_hash == "" and tk2.hash_algo == ""
   and any("没被采用" in m for _l, m in q.log.rows), (tk2.expect_hash, q.log.rows))

_real_engine_check = S.engine.check_ytdlp
_real_ff_find = S.ffmpeg_mgr.find
_real_n = S.find_n_m3u8dl
_real_bt = S.bt_ensure
try:
    S.engine.check_ytdlp = lambda: "found"
    S.ffmpeg_mgr.find = lambda *a, **k: str(TMP / "ffmpeg.exe")
    S.find_n_m3u8dl = lambda: str(TMP / "N_m3u8DL-RE")
    S.bt_ensure = lambda d, log=None: (True, "")

    o_bad = {"expect_hash": "abc123", "hash_algo": "md5"}
    e, w = S.download_preflight(["https://example.com/v"], o_bad)
    ck("E8 界面入队遇到收不拢的期望值：当场 400 级错，并把「该多少位 / 现在几位」说出来",
       any("期望校验值" in x and "32 位" in x and "6 位" in x for x in e), e)

    o_ok = {"expect_hash": MD5.upper(), "hash_algo": "auto", "format": "mkv",
            "embed_thumb": True, "embed_sub": False}
    e2, w2 = S.download_preflight(["https://example.com/v"], o_ok)
    ck("E9 收拢结果写回 opts（后面 add_urls 拿到的是干净那一份，不会二次报错）",
       o_ok["expect_hash"] == MD5 and o_ok["hash_algo"] == "md5" and not e2, (o_ok["expect_hash"], e2))
    ck("E10 链接下载会重写容器 → 入队就警告，但用的是「除非原样落盘」这种有条件的口气",
       any("本来就不会相同" in x and "封装成 mkv" in x and "除非它按 CDN 直链原样落盘" in x for x in w2), w2)

    o_bt = {"expect_hash": MD5, "hash_algo": "auto", "format": "mkv", "embed_thumb": True}
    _e3, w3 = S.download_preflight(["magnet:?xt=urn:btih:" + "a" * 40], o_bt)
    ck("E11 磁力/种子不给这句警告（aria2 原样落盘，本来就可比）",
       not any("本来就不会相同" in x for x in w3), w3)

    o_none = {"hash_algo": "auto", "format": "mkv"}
    _e4, w4 = S.download_preflight(["https://example.com/v"], o_none)
    ck("E12 没给期望值时一个字都不提（默认关，不打扰）",
       not any("校验值" in x for x in w4) and o_none["expect_hash"] == "", (w4, o_none))
finally:
    S.engine.check_ytdlp = _real_engine_check
    S.ffmpeg_mgr.find = _real_ff_find
    S.find_n_m3u8dl = _real_n
    S.bt_ensure = _real_bt

print("== F. 收尾接线：核对站在 verify_download 之外、转存之前 ==")
# 取块要先确认那块代码还在：锚点找不到就整段崩掉的话，接线被改坏这一类反而看不出是哪条
_h0 = SRC.find("if ok and path and task.expect_hash:")
ck("F0 收尾里那块核对还在（改了写法就要跟着改这里，别让后面的断言空转）", _h0 >= 0, SRC[_h0 - 200:_h0] if _h0 >= 0 else "没找到")
hash_blk = SRC[_h0:] if _h0 >= 0 else ""
_end = hash_blk.find("# NAS / 网盘转存")
blk = hash_blk[:_end] if _end > 0 else hash_blk
ck("F1 有独立的核对块，缩进和 verify_download 那道闸门同级（体检关了也要能核对）",
   SRC.count("\n        if ok and path and task.expect_hash:") == 1
   and "cfg.get(\"verify_download\"" not in blk, blk[:200])
ck("F2 只在任务成功、且有成品路径时才算（已经判失败的没必要再读几个 G）",
   blk.startswith("if ok and path and task.expect_hash:") and "task.status" not in blk.splitlines()[0])
ck("F3 核对走在网盘/NAS 转存之前：算的是本机这份成品",
   0 <= _h0 < SRC.index("transfer_to_storage(path, self.cfg.data"))
ck("F4 对不上才上屏，并进 verify_note 那一条通道（卡片与历史 tooltip 自动带上）",
   'task.verify_note = f"{task.verify_note}；{note}" if task.verify_note else note' in blk, blk[:400])
ck("F5 一致时只进运行日志，不占卡片一行", 'elif state == "ok":' in blk and "校验值核对：" in blk)
ck("F6 历史不用加新键：句子跟着 verify_note 入库", '"verify_note": task.verify_note' in SRC)
ck("F7 核对本身出问题不牵连任务结论（与成品回读同一口径）", "校验值核对异常（跳过）" in blk)
ck("F8 种子的 kind 在收尾之前就已定下（torrent 那一支走「不算重写」）",
   'task.kind = "torrent"' in SRC[:SRC.index("def _run(self, task")])
ck("F9 画质回读那一支没被改动（两句用同一个字段但各判各的）",
   SRC.count("task.verify_note = tier_readback(") == 1)
# 「算不算原样落盘」的口径必须只有引擎那一份：收尾自己再判一次 URL 的话，
# 引擎那张直链名单一改，两句就会互相打脸（活体第一遍正是这么被抓出来的）
ck("F10 收尾问的是引擎记下的标记，不是自己再判一遍 URL",
   "raw_bytes = self.engine.pop_raw_bytes(task.id)" in SRC
   and "hsteps = [] if raw_bytes else hash_rewrite_steps(hview, task.kind)" in SRC)
ck("F11 CDN 直链那一支确实打了标记，而且只在那一支",
   SRC.count("self.note_raw_bytes(task_id)") == 1
   and SRC.index("self.note_raw_bytes(task_id)") < SRC.index("CDN 直链下载（绕过 yt-dlp）"))
ck("F12 标记取走即清（和 pop_listed_max 同一口径，不留残值给下一个任务）",
   "self._raw_bytes.pop(task_id, False)" in SRC)
eng_h = S.engine
eng_h._raw_bytes["t-raw"] = True
ck("F13 pop 一次给值、再来就是 False；没记过的任务不 KeyError",
   eng_h.pop_raw_bytes("t-raw") is True and eng_h.pop_raw_bytes("t-raw") is False
   and eng_h.pop_raw_bytes("没有这个 id") is False)

print("== G. 界面上屏 ==")
ck("G1 卡片两张模板的标签改成「成品核对」（这一行现在也可能装校验值；句子搬进词表后按 tr 的键钉）",
   HTML.count("{{ tr('task.verifyPrefix') }} · {{ t.verify_note }}") == 2 and "画质核对 ·" not in HTML
   and "'task.verifyPrefix': '成品核对'," in I18N_ZH,
   HTML.count("{{ tr('task.verifyPrefix') }} · {{ t.verify_note }}"))
ck("G2 入队默认对象里有这两个键（v-model 指到没声明的键上，Vue 那侧是 undefined）",
   "expect_hash: ''," in HTML and "hash_algo: 'auto'," in HTML)
ck("G3 v-model 的键都在默认对象里（这一对是新加的，别只写模板）",
   all(('opts.' + k) in HTML for k in ("expect_hash", "hash_algo"))
   and HTML.count("v-model=\"opts.expect_hash\"") == 1)
ck("G4 四个入队口都靠 ...opts.value 带出去（少一个就是那条路不核对）",
   HTML.count("...opts.value") >= 4, HTML.count("...opts.value"))
ck("G5 一致时给一句悬浮提示，不亮橙色的行", "t.hash_state === 'ok'" in HTML and "校验值一致" in HTML)
ck("G6 unknown 也在悬浮里说清（不是「对上了」也不是「没核对」）", "hash_state === 'unknown'" in HTML)
ck("G7 输入框的提示文案把「原样落盘才可比」这条界线写在界面上，不只写在文档里",
   "原样落盘" in I18N_ZH and "留空 = 不核对" in I18N_ZH
   and "{{ tr('home.hashHintA') }}" in HTML and "tr('home.hashPh')" in HTML)
ck("G8 算法档位只给能选的四家（sha512 走「算法自动」按长度认）",
   all(("opts.hash_algo === '" + a + "'") in HTML for a in ("auto", "md5", "sha1", "sha256")))
ck("G9 界面那句把话说成有条件的（直链原样落盘可比，解析下载才谈重写），不是一刀切",
   "可比的是磁力/种子与被识别成 CDN 直链" in I18N_ZH and "（卡片上那句会说明是哪一种）" in I18N_ZH)

print(f"\nTOTAL {TOTAL} FAILED: {', '.join(FAILED) if FAILED else 'none'}")
sys.exit(1 if FAILED else 0)
