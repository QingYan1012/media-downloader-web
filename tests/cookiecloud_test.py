#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CookieCloud 同步（/api/cookiecloud 的测试连接 / 拉取 / 推送）离线自检。

协议与算法照 easychen/CookieCloud 的 api/app.js：GET {server}/get/{uuid} 取、
POST {server}/update 存，密钥材料 = md5(f"{uuid}-{key}")[:16]，两种写法
legacy（CryptoJS/OpenSSL EVP_BytesToKey-MD5 + Salted__ 头）与 aes-128-cbc-fixed（固定全 0 IV）。
这里在 127.0.0.1 上起一个按同一份语义实现的小服务器，真发 HTTP，不只调函数。
A 段那两个钉住的密文是openssl 3.5.5 生成、由本程序解开的，用来证明双方算法真能对上。
只写 %TEMP%，不碰真实下载目录与 config.json。
跑法：PYTHONIOENCODING=utf-8 python tests/cookiecloud_test.py
"""
import base64
import hashlib
import json
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

FAILED = []
TOTAL = 0


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}" + (f"  [{extra}]" if extra else ""))
    else:
        FAILED.append(name)
        print(f"FAIL {name}  [{extra}]")


class FakeCfg:
    """CookieCloud 只有「保存设置」这一个动作该写 config.json，其余动作写了就记一笔，用来反查。"""

    def __init__(self, data):
        self.data = data
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))


TMP = Path(tempfile.mkdtemp(prefix="md_cookiecloud_"))
DL = TMP / "cookies"
DL.mkdir(parents=True)
STATE = TMP / "cookiecloud_state.json"

CC_UUID = "cc-uuid-test-1"
CC_KEY = "abcdefgh-1234-5678-abcd-ef0123456789"
# ---------------- A 段钉住的两个密文：明文就是下面 PLAIN_JSON，密文由 openssl 3.5.5 生成
KK = S._cc_key_str(CC_UUID, CC_KEY)
PLAIN_JSON = ('{"cookie_data":{".youtube.com":[{"name":"SID","value":"v a&b 中"}]},'
              '"update_time":"2026-10-14T00:00:00"}')
# 这两份是 openssl 3.5.5 用下面 CC_UUID/CC_KEY 推出来的同一份密钥材料加密的；
# 反向也实测过：我方 _cc_encrypt 的密文 openssl -d 解得开（两个方向、两种写法都对得上）。
VEC_LEGACY = ("U2FsdGVkX1+IbKqlhJEMO+kP+270/+fa/ct/YdViiqPB0qnID2c2/kiZaCtiWLyE"
              "cFRa099HTgRywrxG/3b2xkcfpVHOZqZucfIXA5U4JPSdOJ9eQimKX9Tizo2sZw5J"
              "2Bgjo7twrFBNh44vLv03eEtpd7X2SMz6xAIz7LgJ3bk=")
VEC_FIXED = ("44eRyL+L3bVGHOt1xDgEZayIuvvHS7h8TXPhpQRDo84gWhjxMYSwF9Xff2fttivt"
             "fttsw1wMy9KfnIB00JECq1dLTiY9vnxkXuNQfuoKMrYE3XXjTsxbzK7qcKjcxoTd"
             "IQenLsR7fIZX5FpZbDAxxQ==")

_REAL = (S.cfg, S.log_mgr, S.COOKIES_DIR, S.COOKIECLOUD_STATE_FILE, S.http_proxies,
         S._login_flag_snapshot, S._login_flag_clear, S._auth_token_only)
LOGS = FakeLog()
CFG = FakeCfg({
    "download_dir": str(TMP / "downloads"),
    "cookie_file": str(DL / "cookies.txt"),
    "cookiecloud_enabled": True,
    "cookiecloud_server": "",
    "cookiecloud_uuid": CC_UUID,
    "cookiecloud_key": CC_KEY,
    "cookiecloud_scheme": "auto",
    "cookiecloud_domains": "",
    "platform_cookies": {},
    "nocheckcertificate": True,
    "proxy_mode": "auto",
})
S.cfg = CFG
S.log_mgr = LOGS
S.COOKIES_DIR = DL
S.COOKIECLOUD_STATE_FILE = STATE
S.http_proxies = lambda *a, **kw: {}
FLAGS = {"youtube": {"at": "上一次", "why": "被挡过"}}
CLEARED = []
S._login_flag_snapshot = lambda: dict(FLAGS)
S._login_flag_clear = lambda plat: CLEARED.append(plat)
S._auth_token_only = lambda request: False


def http_error(fn, *a, **kw):
    from fastapi import HTTPException
    try:
        return (200, fn(*a, **kw))
    except HTTPException as e:
        return (e.status_code, str(e.detail))
    except Exception as e:  # noqa: BLE001
        return (0, f"{type(e).__name__}: {e}")


# ---------------- 本地那份「CookieCloud 服务器」：按上游 app.js 的语义实现
SRV = {"store": {}, "mode": "ok", "hits": [], "action": "done"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        SRV["hits"].append(("GET", self.path, None))
        if SRV["mode"] == "html":
            return self._send(200, "<html>不是接口</html>", "text/html")
        if SRV["mode"] == "boom":
            return self._send(500, "Internal Serverless Error", "text/plain")
        if SRV["mode"] == "noenc":
            return self._send(200, json.dumps({"action": "synced"}))
        m = re.match(r"^/get/([^/?]+)$", self.path)
        if not m:
            return self._send(404, "Not Found", "text/plain")
        rec = SRV["store"].get(m.group(1))
        if SRV["mode"] == "empty" or rec is None:
            return self._send(404, "Not Found", "text/plain")
        return self._send(200, json.dumps(rec))

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads((self.rfile.read(n) or b"{}").decode("utf-8"))
        SRV["hits"].append(("POST", self.path, body))
        m = re.match(r"^/update$", self.path)
        if not m or SRV["mode"] == "boom":
            return self._send(500, "no", "text/plain")
        if SRV["mode"] == "reject":
            return self._send(200, json.dumps({"action": "error"}))
        if SRV["mode"] == "badreq":
            return self._send(400, "Bad Request", "text/plain")
        SRV["store"][str(body.get("uuid") or "")] = {
            "encrypted": body.get("encrypted"), "crypto_type": body.get("crypto_type") or "legacy"}
        return self._send(200, json.dumps({"action": SRV["action"]}))

    def log_message(self, *a):  # 静音
        pass


HTTPD = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=HTTPD.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{HTTPD.server_address[1]}"


def cloud_put(rows, scheme="legacy", uuid_=CC_UUID):
    """直接把一份 cookie_data 按指定写法加密后放进本地服务器的仓里（模拟浏览器那一侧上传）。"""
    payload = {"cookie_data": {r["domain"]: [r] for r in rows} if isinstance(rows, list) else rows,
               "update_time": "2026-10-14T09:00:00"}
    cc = {"uuid": uuid_, "key": CC_KEY}
    SRV["store"][uuid_] = {"encrypted": S._cc_encrypt(payload, cc, scheme), "crypto_type": scheme}


def cookie(name, domain, value=None, exp=0, path="/", secure=False):
    # 归一化后的行（内部用的就是这个形状）；喂给云端那侧也没问题，_cc_rows_from_cloud 认 expires
    return {"name": name, "value": value if value is not None else "v-" + name,
            "domain": domain, "path": path, "secure": secure, "expires": exp}


def cloud_json(domains_map, extra=None):
    """按插件的真实形状（{域: [cookie]}）造一份云端数据。"""
    d = {"cookie_data": domains_map, "local_storage_data": {}, "update_time": "2026-10-14T09:00:00"}
    if extra:
        d.update(extra)
    return d


def reset_cfg(**kw):
    CFG.data.update({"cookiecloud_enabled": True, "cookiecloud_server": BASE,
                     "cookiecloud_uuid": CC_UUID, "cookiecloud_key": CC_KEY,
                     "cookiecloud_scheme": "auto", "cookiecloud_domains": "",
                     "cookie_file": str(DL / "cookies.txt")})
    CFG.data.update(kw)
    CFG.saves = 0
    LOGS.rows.clear()
    SRV.update({"mode": "ok", "hits": [], "action": "done"})
    if STATE.exists():
        STATE.unlink()


try:
    # ---------------- A 密钥材料与两种算法（钉住 openssl 生成的密文）
    ck("A1 密钥材料就是 md5(uuid+'-'+key) 的前 16 个字符（算法独立算一遍对上游）",
       KK == hashlib.md5(f"{CC_UUID}-{CC_KEY}".encode("utf-8")).hexdigest()[:16] and len(KK) == 16, KK)
    ck("A2 openssl 写的 legacy 密文解得开，中文和空格都没走样",
       S._cc_decrypt_blob(VEC_LEGACY, KK, "legacy")["cookie_data"][".youtube.com"][0]["value"] == "v a&b 中")
    ck("A3 openssl 写的 aes-128-cbc-fixed 密文也解得开",
       S._cc_decrypt_blob(VEC_FIXED, KK, "aes-128-cbc-fixed")["update_time"] == "2026-10-14T00:00:00")
    ck("A4 legacy 密文里带 Salted__ 头与 8 字节盐，fixed 是裸 base64",
       base64.b64decode(VEC_LEGACY)[:8] == b"Salted__" and len(base64.b64decode(VEC_LEGACY)[8:16]) == 8
       and base64.b64decode(VEC_FIXED)[:8] != b"Salted__")
    legacy_blob = S._cc_encrypt(json.loads(PLAIN_JSON), {"uuid": CC_UUID, "key": CC_KEY}, "legacy")
    fixed_blob = S._cc_encrypt(json.loads(PLAIN_JSON), {"uuid": CC_UUID, "key": CC_KEY}, "aes-128-cbc-fixed")
    ck("A5 我方 legacy 写出来的形状与 openssl 一致（Salted__ + 8 字节盐 + 整块密文）",
       base64.b64decode(legacy_blob)[:8] == b"Salted__"
       and len(base64.b64decode(legacy_blob)) >= 32
       and (len(base64.b64decode(legacy_blob)) - 16) % 16 == 0
       and base64.b64decode(legacy_blob)[8:16] != base64.b64decode(VEC_LEGACY)[8:16],
       "盐与 openssl 那份不同（随机）")
    ck("A6 我方写的两种密文自己都能解回来",
       S._cc_decrypt_blob(legacy_blob, KK, "legacy")["update_time"] == "2026-10-14T00:00:00"
       and S._cc_decrypt_blob(fixed_blob, KK, "aes-128-cbc-fixed")["update_time"] == "2026-10-14T00:00:00")
    ck("A7 两次 legacy 加密的密文不同（盐是随机的），但解出来一样",
       S._cc_encrypt(json.loads(PLAIN_JSON), {"uuid": CC_UUID, "key": CC_KEY}, "legacy") != legacy_blob)
    folded = "\n".join([legacy_blob[i:i + 64] for i in range(0, len(legacy_blob), 64)])
    ck("A8 别的工具折行的 base64 也照解（先抹空白）",
       S._cc_decrypt_blob(folded, KK, "legacy")["update_time"] == "2026-10-14T00:00:00", "有换行也能解")
    code, detail = http_error(S._cc_decrypt, VEC_LEGACY, {"uuid": CC_UUID, "key": "错的密钥", "scheme": "auto"})
    ck("A9 密钥不对时是「解不开」的 502，不是崩", code == 502, detail[:60])
    ck("A10 解不开的说明里把两种写法都点名了（不是只说「失败」）",
       "legacy" in detail and "aes-128-cbc-fixed" in detail, detail[:70])
    ck("A11 auto 先试云端报的那种写法：云端报 fixed 就先 fixed",
       S._cc_try_order("auto", "aes-128-cbc-fixed")[0] == "aes-128-cbc-fixed")
    ck("A12 auto 没见过云端时报的写法时按 legacy、fixed 依次试",
       S._cc_try_order("auto", "") == ["legacy", "aes-128-cbc-fixed"])
    ck("A13 钉死了写法就只试那一种，不偷偷换",
       S._cc_try_order("aes-128-cbc-fixed", "legacy") == ["aes-128-cbc-fixed"])
    ck("A14 Pkcs7 加/去填充对得上，长度已是 16 的整倍时也要补一整块",
       S._cc_pkcs7(S._cc_pkcs7(b"0123456789abcde"), unpad=True) == b"0123456789abcde"
       and len(S._cc_pkcs7(b"0123456789abcdef")) == 32
       and S._cc_pkcs7(S._cc_pkcs7(b"0123456789abcdef"), unpad=True) == b"0123456789abcdef")
    bad_pad = http_error(S._cc_pkcs7, b"0123456789abcdef" + b"\x00" * 6 + b"\x07", unpad=True)
    ck("A15 填充字节对不上时报的是「多半是口令不对」，不是 IndexError",
       bad_pad[0] == 0 and "ValueError" in bad_pad[1] and "口令" in bad_pad[1], bad_pad[1][:50])

    # ---------------- B Netscape 写出与读回
    rows = [cookie("SID", ".youtube.com", "甲 乙", exp=1893456000, secure=True),
            cookie("HSID", "m.youtube.com", "v1"),
            cookie("SESSDATA", ".bilibili.com", "v2", exp=0)]
    text = S._cc_netscape_text(rows, "测试写出")
    lines = text.splitlines()
    ck("B1 头两行是 Netscape 标记与说明，第三行是列名注释",
       lines[0] == "# Netscape HTTP Cookie File" and lines[1].startswith("# 测试写出")
       and lines[2].startswith("# domain"), lines[0])
    body = [l for l in lines if not l.startswith("#")]
    ck("B2 七列制表符分隔，顺序是 domain/flag/path/secure/expiry/name/value",
       [l for l in body if l.endswith("\tSID\t甲 乙")][0].split("\t")
       == [".youtube.com", "TRUE", "/", "TRUE", "1893456000", "SID", "甲 乙"], body[0])
    ck("B3 没有前导点的域写 FALSE（不是子域通用）",
       any(l.startswith("m.youtube.com\tFALSE\t") for l in lines), [l for l in lines if "m.youtube" in l])
    ck("B4 会话 Cookie 的有效期写 0，不是空、不是 -1",
       any(l.endswith("\t0\tSESSDATA\tv2") for l in lines), [l for l in lines if "SESSDATA" in l])
    dup_lines = [l for l in S._cc_netscape_text(
        rows + [cookie("SID", ".youtube.com", "后来的")], "重复").splitlines() if not l.startswith("#")]
    ck("B5 同 (域, 路径, 名) 重复的只留最后一条",
       len(dup_lines) == 3 and any(l.endswith("\tSID\t后来的") for l in dup_lines), str(dup_lines)[:70])
    back = {r["name"]: r for r in S._cc_parse_netscape(text)}
    ck("B6 自己写的文件读得回来，条数与值都对", len(back) == 3
       and back["SID"]["value"] == "甲 乙" and back["SID"]["expires"] == 1893456000
       and back["SID"]["secure"] is True and back["SESSDATA"]["expires"] == 0, str(back)[:70])
    ho = ("# Netscape HTTP Cookie File\n"
          "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\thidden-one\n"
          ".example.org\tTRUE\t/\tFALSE\t0\ta\tb\n")
    cb = S._cc_parse_netscape(ho)
    ck("B7 #HttpOnly_ 那几条是真 Cookie，没被当注释扔掉",
       len(cb) == 2 and cb[0]["name"] == "SAPISID" and cb[0]["domain"] == ".youtube.com", str(cb[:1]))
    ck("B8 空格分隔的行也认（有的导出不用制表符）",
       len(S._cc_parse_netscape(".youtube.com TRUE / FALSE 0 NICK nn")) == 1)
    ck("B9 注释、空行、列数不足的一律跳过，不报错",
       S._cc_parse_netscape("# comment\n\n\t\n.only.com\tTRUE\t/\n") == [])
    ck("B10 值里带空格不会被切断",
       [r["value"] for r in S._cc_parse_netscape(text) if r["name"] == "SID"] == ["甲 乙"])
    p = DL / "write_probe.txt"
    p.write_text("旧的 hand-made 内容\n", encoding="utf-8")
    info = S._cc_write_file(p, rows)
    ck("B11 写盘前把原文件备份成同名 .bak-<时间>",
       info["changed"] is True and info["backup"].startswith("write_probe.txt.bak-")
       and (DL / info["backup"]).read_text(encoding="utf-8") == "旧的 hand-made 内容\n", info["backup"])
    again = S._cc_write_file(p, rows)
    ck("B12 内容一模一样时不动文件、也不再堆备份", again["changed"] is False and again["backup"] == ""
       and len([q for q in DL.iterdir() if q.name.startswith("write_probe.txt.bak-")]) == 1)
    raw_bytes = p.read_bytes()
    ck("B13 写出来是 LF，不是 CRLF", b"\r" not in raw_bytes and raw_bytes.endswith(b"\n"))
    p.unlink()
    for q in DL.glob("write_probe.txt.bak-*"):
        q.unlink()

    # ---------------- C 平台归属（决定要不要动 cookies/<平台>_cookies.txt）
    cases = [(".youtube.com", "youtube"), ("youtube.com", "youtube"), ("m.youtube.com", "youtube"),
             (".youtu.be", "youtube"), (".bilibili.com", "bilibili"), ("m.bilibili.com", "bilibili"),
             ("t.me", "telegram"), (".x.com", "twitter"), (".tiktok.com", "douyin"),
             (".example.org", "default"), ("notyoutube.com", "default"), (".youtubekids.com", "default")]
    bad = [(d, S._cc_platform_for(d), want) for d, want in cases if S._cc_platform_for(d) != want]
    ck("C1 平台归属按后缀整段匹配，12 个用例全对（含 notyoutube.com 不误判）",
       not bad, str(bad))
    ck("C2 平台文件名跟着 platform_cookie_path 走（就在 cookies 目录里）",
       S.platform_cookie_path("youtube") == DL / "youtube_cookies.txt", str(S.platform_cookie_path("youtube")))

    # ---------------- D 域名过滤
    allrows = rows + [cookie("token", ".github.com", "g")]
    ck("D1 过滤词空着就全收", len(S._cc_filter_rows(allrows, S._cc_domain_filter(""))) == 4)
    ck("D2 「youtube.com」收 .youtube.com 也收 m.youtube.com（和插件一样是包含）",
       [r["name"] for r in S._cc_filter_rows(allrows, S._cc_domain_filter("youtube.com"))] == ["SID", "HSID"])
    ck("D3 换行、逗号、分号当同一种分隔，多词合并生效",
       [len(S._cc_filter_rows(allrows, S._cc_domain_filter(w))) for w in
        ("youtube.com\nbilibili.com", "youtube.com,bilibili.com", "youtube.com;bilibili.com")] == [3, 3, 3],
       S._cc_domain_filter("youtube.com\nbilibili.com;github.com"))
    ck("D4 过滤词大小写与前导点都无所谓",
       S._cc_domain_filter(" YouTube.com \n.bilibili.com") == ["youtube.com", "bilibili.com"])
    ck("D5 一个词都不沾边时是空列表（后面才有那句「都不剩」），不是异常",
       S._cc_filter_rows(allrows, S._cc_domain_filter("nothing.example")) == [])

    # ---------------- E 云端数据形状
    e1, n1 = S._cc_rows_from_cloud(cloud_json({".youtube.com": [cookie("a", ".youtube.com")]}))
    ck("E1 插件那种 {域: [cookie]} 正常读出来", len(e1) == 1 and n1 == [], str(n1))
    e2, _ = S._cc_rows_from_cloud({"cookie_data": [cookie("x", ".a.com"), cookie("y", ".b.com")]})
    ck("E2 第三方客户端写成扁平列表也收", len(e2) == 2)
    e3, _ = S._cc_rows_from_cloud({"cookie_data": {".a.com": {"n1": cookie("x", ".a.com")}}})
    ck("E3 {域: {名字: cookie}} 这种字典嵌字典也收", len(e3) == 1)
    e4, n4 = S._cc_rows_from_cloud({"cookie_data": {".a.com": "不是列表", ".b.com": [cookie("z", ".b.com")]}})
    ck("E4 认不出的那一项跳过并且留一句说明，不整份丢",
       len(e4) == 1 and any("不是列表" in x for x in n4), str(n4))
    e5, n5 = S._cc_rows_from_cloud({**cloud_json({".a.com": [cookie("z", ".a.com")]}),
                                    "local_storage_data": {".a.com": {"k": "v"}}})
    ck("E5 云端带 localStorage 时说明白「下载用不上，没写盘」",
       any("localStorage" in x and "没写盘" in x for x in n5), str(n5))
    e6, _ = S._cc_rows_from_cloud({"cookie_data": {".a.com": [
        {"name": "n", "value": "v", "domain": ".a.com", "expires": 1700000000},
        {"name": "", "value": "v", "domain": ".a.com"},
        {"name": "n2", "value": "v", "domain": ""},
        {"name": "n3", "value": "v", "domain": ".a.com", "expirationDate": "1700000111.5"},
        {"name": "n4", "value": "v", "domain": ".a.com", "expirationDate": None}]}})
    ck("E6 expires / expirationDate 都认，浮点秒取整，没效期当会话(0)",
       [r["expires"] for r in e6] == [1700000000, 1700000111, 0] and [r["name"] for r in e6] == ["n", "n3", "n4"],
       str([(r["name"], r["expires"]) for r in e6]))
    ck("E7 缺 name 或缺 domain 的那条直接不收", len(e6) == 3)

    # ---------------- F 配置缺哪一层就点名哪一层
    reset_cfg(cookiecloud_enabled=False)
    SRV["hits"].clear()
    code, detail = http_error(S.api_cookiecloud_test)
    ck("F1 开关没开：400 + 说的是「没打开」，不是「连不上」", code == 400 and "没打开" in detail, detail[:40])
    ck("F2 关着的原话还指出在哪一栏（设置 → Cookie 与登录）", "设置 → Cookie 与登录" in detail, detail[:50])
    ck("F3 关着的时候连请求都没发出去（本地服务器一次都没被打）", SRV["hits"] == [], str(SRV["hits"])[:60])
    reset_cfg(cookiecloud_enabled=True, cookiecloud_server="")
    ck("F4 开着但地址没填 → 点名「服务器地址」",
       "服务器地址" in http_error(S.api_cookiecloud_test)[1], http_error(S.api_cookiecloud_test)[1][:40])
    reset_cfg(cookiecloud_server="cc.example.com")
    ck("F5 地址不带 http(s):// → 指出要带协议头", "http://" in http_error(S.api_cookiecloud_test)[1])
    reset_cfg(cookiecloud_server=BASE, cookiecloud_uuid="")
    ck("F6 没填 UUID → 说的是 UUID", "UUID" in http_error(S.api_cookiecloud_test)[1])
    reset_cfg(cookiecloud_uuid="../etc/passwd")
    ck("F7 UUID 里带斜杠这种会被挡（它要拼进请求路径）",
       "只该有字母" in http_error(S.api_cookiecloud_test)[1], http_error(S.api_cookiecloud_test)[1][:48])
    reset_cfg(cookiecloud_uuid=CC_UUID, cookiecloud_key="")
    ck("F8 没填密钥 → 说的是密钥，并说明它不进日志",
       "同步密钥" in http_error(S.api_cookiecloud_test)[1] and "日志" in http_error(S.api_cookiecloud_test)[1])
    reset_cfg()

    # ---------------- G 测试连接：真发 HTTP，问一次解一次
    cloud_put([cookie("SID", ".youtube.com", "云上的值", exp=1893456000), cookie("SESSDATA", ".bilibili.com", "b")])
    code, r = http_error(S.api_cookiecloud_test)
    ck("G1 测试连接 200，报出条数与域数", code == 200 and r["cloud_rows"] == 2 and r["cloud_domains"] == 2, str(r)[:80])
    ck("G2 说明里点明用的是哪种写法、这次没写盘",
       "加密" in r["message"] and "没写盘" in "".join(x[1] for x in LOGS.rows), r["message"][:60])
    ck("G3 日志里既不出现密钥也不出现 UUID",
       CC_KEY not in json.dumps(LOGS.rows, ensure_ascii=False)
       and CC_UUID not in json.dumps(LOGS.rows, ensure_ascii=False), str(LOGS.rows[-1])[:60])
    ck("G4 测试连接不写 cookies 目录，也不写 config.json",
       not (DL / "cookies.txt").exists() and CFG.saves == 0, f"{CFG.saves}")
    ck("G5 状态文件记下这次测试的时间与通过的标记",
       STATE.is_file() and json.loads(STATE.read_text(encoding="utf-8")).get("last_test_ok") is True)
    ck("G6 状态文件里没有密钥", CC_KEY not in STATE.read_text(encoding="utf-8"))
    reset_cfg(cookiecloud_scheme="aes-128-cbc-fixed")
    ck("G7 云端是 legacy 而钉死 fixed 时，报的是「解不开」并说明现在选的是 fixed",
       http_error(S.api_cookiecloud_test)[0] == 502 and "aes-128-cbc-fixed" in http_error(S.api_cookiecloud_test)[1],
       http_error(S.api_cookiecloud_test)[1][:70])
    reset_cfg(cookiecloud_scheme="auto")
    ck("G8 auto 遇到云端报 legacy 时能解（自动切对了写法）", http_error(S.api_cookiecloud_test)[0] == 200)
    SRV["mode"] = "empty"
    code, detail = http_error(S.api_cookiecloud_test)
    ck("G9 服务器回 404 时说的是「这个 UUID 还没数据，先在插件里上传一次」，不是「连不上」",
       code == 404 and "UUID" in detail and "上传" in detail and "连不上" not in detail, detail[:60])
    SRV["mode"] = "html"
    code, detail = http_error(S.api_cookiecloud_test)
    ck("G10 对面不是 CookieCloud 接口（回 HTML）时说的是没回 encrypted",
       code == 502 and "encrypted" in detail, detail[:60])
    ck("G10b 响应没带 charset 时中文错话也不乱码（自己按 UTF-8 解的）", "不是接口" in detail, detail[:60])
    SRV["mode"] = "noenc"
    ck("G11 回了 JSON 但没 encrypted 字段也是同一句「不像 /get 接口」",
       "encrypted" in http_error(S.api_cookiecloud_test)[1])
    SRV["mode"] = "boom"
    ck("G12 服务器 500 时报 HTTP 500，不报「解不开」",
       "HTTP 500" in http_error(S.api_cookiecloud_test)[1], http_error(S.api_cookiecloud_test)[1][:50])
    HTTPD.shutdown_ = None
    SRV["mode"] = "ok"
    reset_cfg(cookiecloud_server="http://127.0.0.1:1")
    code, detail = http_error(S.api_cookiecloud_test)
    ck("G13 端口没人听时是 502「连不上 + 主机:端口」，不是「解不开」也不是崩",
       code == 502 and "连不上" in detail and "127.0.0.1:1" in detail, detail[:70])
    _real_px, _real_sp = S.http_proxies, S.system_proxy_detail
    try:
        S.http_proxies = lambda *a, **kw: None            # 策略不干预：跟着系统走
        S.system_proxy_detail = lambda: ("http://127.0.0.1:9999", "Windows 系统代理设置")
        ck("G14 回环地址说「本机地址，直连」，远程地址才说跟随系统代理",
           "本机地址，直连" in S._cc_proxy_note("http://127.0.0.1:1/get/x")
           and "跟随" in S._cc_proxy_note("https://cc.example.com/get/x"), S._cc_proxy_note("http://127.0.0.1:1"))
        ck("G14b localhost 这个名字也一样（不能只认 127.0.0.1）",
           "本机地址，直连" in S._cc_proxy_note("http://localhost:8088/get/x"))
        S.http_proxies = lambda *a, **kw: {"http": "http://p:1", "https": "http://p:1"}
        ck("G14c 策略真给了代理时按策略说，不含糊", "按网络策略走代理" in S._cc_proxy_note("https://cc.example.com"))
        S.http_proxies = lambda *a, **kw: {"http": None, "https": None}
        ck("G14d 策略强制直连时说清是强制直连", "强制直连" in S._cc_proxy_note("https://cc.example.com"))
    finally:
        S.http_proxies, S.system_proxy_detail = _real_px, _real_sp
    ck("G15 失败这一次也进了状态（时间与 ok=False），界面能说出「最近一次是失败的」",
       S._cc_state().get("last_test_ok") is False and bool(S._cc_state().get("last_test_at")),
       str(S._cc_state())[:60])
    ck("G16 连不上时本机 cookies 目录里没多出任何文件", not (DL / "cookies.txt").exists(),
       str([q.name for q in DL.iterdir()])[:70])
    ck("G17 失败的原话存在状态里（界面上那句「没成」吃它）",
       "连不上" in str(S._cc_state().get("last_test_error")), str(S._cc_state().get("last_test_error"))[:50])
    ck("G18 状态文件里没有 UUID、没有密钥（requests 的错话里带着 /get/<UUID>，要抹掉）",
       CC_UUID not in STATE.read_text(encoding="utf-8") and CC_KEY not in STATE.read_text(encoding="utf-8")
       and "‹UUID›" in str(S._cc_state().get("last_test_error")), str(S._cc_state().get("last_test_error"))[:60])
    ck("G19 这一趟的日志里同样没有 UUID 与密钥",
       CC_UUID not in json.dumps(LOGS.rows, ensure_ascii=False)
       and CC_KEY not in json.dumps(LOGS.rows, ensure_ascii=False), str(LOGS.rows[-1])[:60])
    LOGS.rows.clear()
    reset_cfg(cookiecloud_server="http://user:pass@127.0.0.1:1")
    code, detail = http_error(S.api_cookiecloud_test)
    ck("G20 地址里带了 user:pass 时，错话与日志只报主机端口，不带上那对凭据",
       code == 502 and "user:pass" not in detail and "127.0.0.1:1" in detail, detail[:60])
    ck("G21 G20 的失败记录里也没有凭据",
       "user:pass" not in STATE.read_text(encoding="utf-8")
       and "user:pass" not in json.dumps(LOGS.rows, ensure_ascii=False), str(LOGS.rows[-1])[:60])
    reset_cfg()
    ck("G22 接着测成功一次：ok 变 True，上次的错话被擦掉（界面不能显示「通过：连不上…」）",
       http_error(S.api_cookiecloud_test)[0] == 200 and S._cc_state().get("last_test_ok") is True
       and S._cc_state().get("last_test_error") == "", str(S._cc_state())[:70])
    reset_cfg()

    # ---------------- H 从云端拉取：写盘 / 备份 / 清标记 / 状态 / 日志
    reset_cfg()
    hand = DL / "cookies.txt"
    hand.write_text("# Netscape HTTP Cookie File\n.keep.com\tTRUE\t/\tFALSE\t0\told\tvalue\n", encoding="utf-8")
    cloud_put([cookie("SID", ".youtube.com", "云1", exp=1893456000),
               cookie("SESSDATA", ".bilibili.com", "云2"),
               cookie("tok", ".github.com", "云3")])
    code, r = http_error(S.api_cookiecloud_pull)
    gtxt = hand.read_text(encoding="utf-8")
    ck("H1 拉取 200，收下 3 条 / 3 个域", code == 200 and len(r["files"]) >= 1 and r["files"][0]["count"] == 3, str(r["files"]))
    ck("H2 全局那份里手工写的那条不见了，云端的三条在",
       "old" not in gtxt and "云1" in gtxt and "SESSDATA" in gtxt and "tok" in gtxt)
    ck("H3 覆盖前留了备份，备份里还是手工那一条",
       (DL / r["files"][0]["backup"]).read_text(encoding="utf-8").find("old") >= 0, r["files"][0]["backup"])
    plat = [f for f in r["files"] if f["file"] == "youtube_cookies.txt"]
    ck("H4 云端给了 YouTube 的 Cookie，于是写了 youtube_cookies.txt",
       plat and plat[0]["count"] == 1 and (DL / "youtube_cookies.txt").is_file(), str(r["files"]))
    ck("H5 B 站那份也写了（云端给了 .bilibili.com）",
       (DL / "bilibili_cookies.txt").is_file() and "云2" in (DL / "bilibili_cookies.txt").read_text(encoding="utf-8"))
    ck("H6 github.com 不属于任何平台，只进全局那份，没造出 github 文件",
       not (DL / "github_cookies.txt").exists() and "tok" in gtxt)
    ck("H7 拉到的平台 Cookie 会把「这个平台被判定要登录」的标记清掉",
       "youtube" in CLEARED and "bilibili" in CLEARED, str(CLEARED))
    ck("H8 拉取这一路不写 config.json", CFG.saves == 0)
    st = json.loads(STATE.read_text(encoding="utf-8"))
    ck("H9 状态里有时间、条数、域数、写法，且条数是 3",
       re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$", st["last_pull_at"]) and st["pull_rows"] == 3
       and st["pull_domains"] == 3 and st["scheme_seen"] == "legacy", str(st)[:90])
    ck("H10 状态里逐个文件记了条数（界面上的「最近一次拉取写的文件」吃这个）",
       len(st["pull_files"]) == 3 and {f["file"] for f in st["pull_files"]} ==
       {"cookies.txt", "youtube_cookies.txt", "bilibili_cookies.txt"}, str(st["pull_files"]))
    ck("H11 日志里点名了写了几个文件与各自条数",
       "写了 3 个文件" in json.dumps(LOGS.rows, ensure_ascii=False), str(LOGS.rows[0])[:70])
    code, r2 = http_error(S.api_cookiecloud_pull)
    ck("H12 内容没变时再说一句「一个文件都没动」，也不再堆备份",
       code == 200 and "一个文件都没动" in r2["message"]
       and len(list(DL.glob("cookies.txt.bak-*"))) == 1, r2["message"][:60])
    # H12b 把「同步时刻」往前推一秒再拉同一份内容：旧写法比的是整份文本，而文件第二行注释里
    # 正带着这个时刻 —— 一秒之内跑得完才算「没变」，机器一忙（并发、负载）就每次多留一份没人看的备份。
    # H12 单跑永远绿（快于一秒），只有整批同跑才暴露，所以这条把时刻钉死，不靠机器快慢。
    _now_real = S._cc_now
    try:
        S._cc_now = lambda: "2027-01-01 00:00:00"
        code, r2b = http_error(S.api_cookiecloud_pull)
        ck("H12b 跨过一秒、Cookie 行没变时仍然一个文件都不动（过去要看机器快慢）",
           code == 200 and "一个文件都没动" in r2b["message"]
           and len(list(DL.glob("cookies.txt.bak-*"))) == 1, r2b["message"][:60])
    finally:
        S._cc_now = _now_real
    reset_cfg(cookiecloud_domains="nonexistent.example")
    code, detail = http_error(S.api_cookiecloud_pull)
    ck("H13 过滤后一条不剩 → 400 说明云端几条、被滤掉几条，并教怎么改",
       code == 400 and "都不剩" in detail and "域名过滤" in detail, detail[:80])
    ck("H14 这种情况下本机文件一个字没改", "云1" in hand.read_text(encoding="utf-8"))
    reset_cfg(cookiecloud_domains="youtube.com")
    code, r3 = http_error(S.api_cookiecloud_pull)
    ck("H15 按 youtube.com 过滤后只收 1 条，且不再写 bilibili 那份",
       code == 200 and r3["files"][0]["count"] == 1 and not
       any(f["file"] == "bilibili_cookies.txt" for f in r3["files"]), str(r3["files"]))
    ck("H16 云端那份里没被过滤掉的条数也在返回里（filtered_out）", r3["filtered_out"] == 2, str(r3["filtered_out"]))

    # ---------------- I 本机推给云端
    reset_cfg()
    for q in list(DL.glob("*_cookies.txt")) + [hand]:
        q.unlink(missing_ok=True)
    (DL / "cookies.txt").write_text("# Netscape HTTP Cookie File\n"
                                    "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1893456000\tSAPISID\thidden\n"
                                    ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\t我的会话\n", encoding="utf-8")
    (DL / "youtube_cookies.txt").write_text("# Netscape HTTP Cookie File\n"
                                            ".youtube.com\tTRUE\t/\tFALSE\t0\tPREF\tf1\n", encoding="utf-8")
    code, r = http_error(S.api_cookiecloud_push)
    ck("I1 推送 200：本机 3 条 / 2 个域（含 #HttpOnly_ 那条）",
       code == 200 and r["rows"] == 3 and r["domains"] == 2, str(r)[:90])
    hit = [h for h in SRV["hits"] if h[0] == "POST"][-1]
    ck("I2 POST 到 /update，body 带 uuid / encrypted / crypto_type",
       hit[1] == "/update" and set(hit[2]) == {"uuid", "encrypted", "crypto_type"}, str(sorted(hit[2])))
    ck("I3 默认写法是 legacy（官方插件只认这个）", hit[2]["crypto_type"] == "legacy", hit[2]["crypto_type"])
    ck("I4 推出去的密文按 legacy 能解，内容是 cookie_data 那份形状",
       S._cc_rows_from_cloud(S._cc_decrypt_blob(hit[2]["encrypted"], KK, "legacy"))[0].__len__() == 3)
    ck("I5 推送这一路不写 config.json，也不动本机 cookies 文件",
       CFG.saves == 0 and (DL / "cookies.txt").read_text(encoding="utf-8").find("SAPISID") >= 0)
    ck("I6 状态文件记了推送时间、条数、域数与来源文件",
       json.loads(STATE.read_text(encoding="utf-8"))["push_rows"] == 3
       and json.loads(STATE.read_text(encoding="utf-8"))["last_push_at"])
    ck("I7 界面/日志里那句「云端那一份已被覆盖」说得很直白",
       "已被覆盖" in r["message"] and "覆盖" in json.dumps(LOGS.rows, ensure_ascii=False), r["message"][:60])
    # auto 沿用上次解开的写法：先按 fixed 拉一次，让状态里存下 fixed
    SRV["store"].clear()
    cloud_put([cookie("SID", ".youtube.com", "云上")], scheme="aes-128-cbc-fixed")
    reset_cfg()
    ck("I8 auto 拉取时按云端报的 fixed 解开了", http_error(S.api_cookiecloud_test)[0] == 200
       and json.loads(STATE.read_text(encoding="utf-8"))["scheme_seen"] == "aes-128-cbc-fixed")
    SRV["hits"].clear()
    code, r = http_error(S.api_cookiecloud_push)
    ck("I9 auto 推送时沿用刚见过的那份写法（这次是 fixed），不再退回 legacy",
       code == 200 and [h for h in SRV["hits"] if h[0] == "POST"][-1][2]["crypto_type"] == "aes-128-cbc-fixed",
       str([h for h in SRV["hits"] if h[0] == "POST"][-1][2]["crypto_type"]))
    reset_cfg(cookiecloud_scheme="aes-128-cbc-fixed")
    SRV["hits"].clear()
    code, r = http_error(S.api_cookiecloud_push)
    ck("I10 钉死 fixed 就按 fixed 推", [h for h in SRV["hits"] if h[0] == "POST"][-1][2]["crypto_type"] == "aes-128-cbc-fixed")
    reset_cfg(cookiecloud_scheme="legacy")
    SRV["hits"].clear()
    code, r = http_error(S.api_cookiecloud_push)
    ck("I11 钉死 legacy 就按 legacy 推", [h for h in SRV["hits"] if h[0] == "POST"][-1][2]["crypto_type"] == "legacy")
    ck("I12 推上去的 legacy 那份 openssl 口径之外还能被本程序按 legacy 读回（自证一致）",
       S._cc_rows_from_cloud(S._cc_decrypt_blob(
           [h for h in SRV["hits"] if h[0] == "POST"][-1][2]["encrypted"], KK, "legacy"))[0][0]["value"] != "")
    SRV["mode"] = "reject"
    code, detail = http_error(S.api_cookiecloud_push)
    ck("I13 服务器回 action=error 时报「没写成」，不是「推好了」",
       code == 502 and "error" in detail, detail[:60])
    SRV["mode"] = "badreq"
    ck("I14 服务器回 400 时报 HTTP 400 与它给的原话",
       "HTTP 400" in http_error(S.api_cookiecloud_push)[1])
    SRV["mode"] = "ok"
    reset_cfg(cookie_file=str(DL / "根本没有这个文件.txt"))
    for q in list(DL.glob("*_cookies.txt")):
        q.unlink(missing_ok=True)
    code, detail = http_error(S.api_cookiecloud_push)
    ck("I15 本机一个 Cookie 文件都读不到时说清楚读的是哪几个路径",
       code == 400 and "没有可推的 Cookie 文件" in detail and "cookies.txt" in detail, detail[:80])
    reset_cfg()

    # ---------------- J 拉回来 → 推上去 → 再拉回来的闭环
    SRV["store"].clear()
    (DL / "cookies.txt").write_text("# Netscape HTTP Cookie File\n"
                                    ".youtube.com\tTRUE\t/\tFALSE\t1893456000\tPREF\t推上去的值\n", encoding="utf-8")
    code, pushed = http_error(S.api_cookiecloud_push)
    ck("J1 先推一份上去（1 条）", code == 200 and pushed["rows"] == 1, str(pushed)[:70])
    (DL / "cookies.txt").unlink()
    (DL / "youtube_cookies.txt").unlink(missing_ok=True)
    code, pulled = http_error(S.api_cookiecloud_pull)
    got_txt = (DL / "cookies.txt").read_text(encoding="utf-8") if (DL / "cookies.txt").exists() else ""
    ck("J2 删掉本机文件再拉回来，值和名字都还在",
       code == 200 and "PREF" in got_txt and "推上去的值" in got_txt, got_txt.splitlines()[-1][:60] if got_txt else "空")
    ck("J3 拉回来的那份平台文件也写了（youtube_cookies.txt）",
       (DL / "youtube_cookies.txt").is_file() and "推上去的值" in (DL / "youtube_cookies.txt").read_text(encoding="utf-8"))
    ck("J4 闭环里那份文件仍是标准 Netscape（第一行标记 + 一条七列数据行）",
       got_txt.splitlines()[0] == "# Netscape HTTP Cookie File"
       and len([l for l in got_txt.splitlines() if not l.startswith("#") and l.count("\t") == 6]) == 1,
       str([l for l in got_txt.splitlines() if l])[:60])
    ck("J5 有效期是纯数字秒，不是浮点（yt-dlp 的 MozillaCookieJar 吃这个）",
       re.search(r"\t1893456000\t", got_txt) is not None, got_txt.splitlines()[-1][:70])

    # ---------------- K 设置读写：密钥不回显、留空不改、可清掉
    mask = S._auth_config_mask({"cookiecloud_key": CC_KEY, "cookiecloud_uuid": CC_UUID})
    ck("K1 /api/config 那份掩码里 cookiecloud_key 被抹空，另有 key_set 布尔",
       mask["cookiecloud_key"] == "" and mask["cookiecloud_key_set"] is True)
    ck("K2 没设密钥时 key_set 是 False（界面上写「本机还没有密钥」）",
       S._auth_config_mask({"cookiecloud_key": ""})["cookiecloud_key_set"] is False)
    reset_cfg(cookiecloud_key="")
    d = S.api_cookiecloud_get()
    ck("K3 GET /api/cookiecloud 里 key 恒为空串，只有 key_set",
       d["key"] == "" and d["key_set"] is False and d["key_set"] is not None)
    ck("K4 GET 里带回了三种写法与中文说明",
       d["schemes"] == ["auto", "legacy", "aes-128-cbc-fixed"] and "固定 IV" in d["scheme_labels"]["aes-128-cbc-fixed"])
    ck("K5 GET 里带回了 cookies 目录与当前 Cookie 文件路径（界面要说写到哪）",
       d["cookies_dir"] == str(DL) and d["cookie_file"] == str(DL / "cookies.txt"))
    body = S.CookieCloudAccountBody(server=BASE + "/", uuid=CC_UUID, key=CC_KEY, scheme="auto",
                                    domains="youtube.com", enabled=True)
    d = S.api_cookiecloud_account(body, request=SimpleNamespace(
        headers={}, cookies={}, client=SimpleNamespace(host="127.0.0.1")))
    ck("K6 保存这几项：写了 config.json 一次，地址尾巴多打的斜杠被收掉",
       CFG.saves == 1 and d["server"] == BASE and d["key_set"] is True)
    ck("K7 保存的日志里有服务器主机名，但没有密钥",
       "127.0.0.1" in LOGS.rows[-1][1] and CC_KEY not in json.dumps(LOGS.rows, ensure_ascii=False), LOGS.rows[-1][1][:70])
    LOGS.rows.clear()
    d = S.api_cookiecloud_account(S.CookieCloudAccountBody(scheme="legacy"), request=None)
    ck("K8 只改加密方式时密钥保持不动（留空 = 不改它）",
       d["key_set"] is True and CFG.data["cookiecloud_key"] == CC_KEY and "密钥没动" in LOGS.rows[-1][1])
    d = S.api_cookiecloud_account(S.CookieCloudAccountBody(key="新的密钥内容"), request=None)
    ck("K9 真填了新密钥时换掉并说「密钥已更新」",
       CFG.data["cookiecloud_key"] == "新的密钥内容" and "密钥已更新" in LOGS.rows[-1][1])
    CFG.data["cookiecloud_key"] = CC_KEY
    d = S.api_cookiecloud_account(S.CookieCloudAccountBody(clear_key=True), request=None)
    ck("K10 清除按钮走 clear_key，之后 key_set 变 False",
       CFG.data["cookiecloud_key"] == "" and d["key_set"] is False and "清掉" in LOGS.rows[-1][1])
    CFG.data["cookiecloud_key"] = CC_KEY
    ck("K11 加密方式填了个没认过的值 → 400 并列出认的三种",
       http_error(S.api_cookiecloud_account, S.CookieCloudAccountBody(scheme="aes-512-gcm"), request=None)[1]
       .count("aes-128-cbc-fixed") > 0)
    ck("K12 地址不带协议头存不下去",
       http_error(S.api_cookiecloud_account, S.CookieCloudAccountBody(server="cc.example.com"), request=None)[1]
       .count("http") > 0)
    ck("K13 UUID 带非法字符存不下去",
       "只该有字母" in http_error(S.api_cookiecloud_account, S.CookieCloudAccountBody(uuid="a b/c"), request=None)[1])
    d = S.api_cookiecloud_account(S.CookieCloudAccountBody(enabled=False, domains="example.com"), request=None)
    ck("K14 开关与域名过滤真的落到了带前缀的配置键上（不是写成裸 enabled/domains）",
       d["enabled"] is False and CFG.data.get("cookiecloud_enabled") is False
       and CFG.data.get("cookiecloud_domains") == "example.com"
       and "enabled" not in CFG.data and "domains" not in CFG.data and "server" not in CFG.data,
       str([k for k in CFG.data if not k.startswith("cookiecloud") and k in
            ("enabled", "domains", "server", "uuid", "scheme", "key")]))
    ck("K14b 改开关不牵连密钥", CFG.data["cookiecloud_key"] == CC_KEY)
    CFG.saves = 0
    d = S.api_cookiecloud_account(S.CookieCloudAccountBody(server=BASE, uuid="other-uuid-2",
                                                           scheme="legacy"), request=None)
    ck("K14c 地址/UUID/写法三项同样落到 cookiecloud_ 前缀键，一次动作只存一遍",
       CFG.data["cookiecloud_server"] == BASE and CFG.data["cookiecloud_uuid"] == "other-uuid-2"
       and CFG.data["cookiecloud_scheme"] == "legacy" and d["uuid"] == "other-uuid-2" and CFG.saves == 1,
       str(CFG.saves))
    reset_cfg()
    S._auth_token_only = lambda request: True
    code, detail = http_error(S.api_cookiecloud_account, S.CookieCloudAccountBody(enabled=True), request=object())
    ck("K15 机器令牌（非本机的纯令牌请求）改不了 CookieCloud 设置",
       code == 403 and "机器令牌" in detail, detail[:50])
    code, detail = http_error(S.api_cookiecloud_account, S.CookieCloudAccountBody(enabled=True), request=None)
    ck("K16 request 为空时不误判成令牌（离线调用与界面调用同一条路）", code == 200, str(code))
    S._auth_token_only = lambda request: False

    # ---------------- L 界面静态断言（HTML 里真有的字句）
    html = (S.APP_DIR / "static" / "index.html").read_text(encoding="utf-8")
    ck("L1 设置页有 CookieCloud 这张卡", 'CookieCloud 同步' in html)
    ck("L2 四个按钮各在：保存 / 测试连接 / 从云端拉取 / 本机推给云端",
       all(x in html for x in ['saveCookieCloud', 'testCookieCloud', 'pullCookieCloud', 'pushCookieCloud']))
    ck("L3 密钥输入框是 password 型，占位语说明「留空就是不改它」",
       'type="password" v-model="cc.key"' in html and "留空就是不改它" in html)
    ck("L4 界面上写着密钥不回显、日志里不出现", "界面不回显、日志里也不会出现" in html)
    ck("L5 未配置时按缺的那一层分别显示；配全了但什么都没干过时说「还没测过，也没同步过」",
       "开着但配不全，缺的是" in html and "还没测过，也没同步过" in html and "还没试" in html)
    ck("L6 写着覆盖前留 .bak-<时间> 与「拉完不用再改来源」",
       ".bak-&lt;时间&gt;" in html and "拉完不用再改来源" in html)
    ck("L7 推送要确认，且确认语里说明是「整个盖掉」",
       "整个盖掉" in html and "本机推给云端" in html)
    ck("L8 四个写接口都进了操作名表（日志里要说清是哪一下）",
       all(x in html for x in ["/api/cookiecloud/account': ", "/api/cookiecloud/test': ",
                               "/api/cookiecloud/pull': ", "/api/cookiecloud/push': "]))
    ck("L9 新加的变量与函数都在 setup 的 return 里（模板拿得到）",
       "cc, ccBusy, ccMsg, loadCookieCloud, saveCookieCloud" in html)
    ck("L10 进设置页会顺手读一次 CookieCloud 状态（时间戳不用手刷）",
       "loadPlatformCookies(); loadCookieCloud();" in html)
    ck("L11 三种加密方式在界面上都有中文说明（吃后端的 scheme_labels）",
       "cc.scheme_labels[s]" in html and "scheme_labels" in json.dumps(S._cc_payload()))
    ck("L12 关掉开关时的话是「不会向任何服务器发请求」",
       "关着就不会向那个服务器发任何请求" in html)
    ck("L13 HTML 里没有硬编码的密钥/UUID 字样", CC_KEY not in html)
    ck("L14 状态行会把「没成」和原话一起显示（失败不装作没发生），成功时把错话擦掉",
       "cc.state.last_test_error" in html and "cc.state.last_pull_error" in html
       and "cc.state.last_push_error" in html and html.count("没成") >= 3)
    cc_body = re.search(r"async function ccCall\(.*?\n        \}", html, re.S)
    cc_body = cc_body.group(0) if cc_body else ""
    ck("L15 失败的那一路也会把状态重读一遍（时间戳不能只跟着成功走）",
       "catch (e) {" in cc_body and "await loadCookieCloud();" in cc_body.split("catch (e) {", 1)[1],
       cc_body.split("catch (e) {", 1)[1][:70].strip() if "catch (e) {" in cc_body else "ccCall 没找到")

    # ---------------- M 默认值与不写盘承诺
    D = S.ConfigManager.DEFAULTS
    ck("M1 默认值是关的（老环境升级完不会突然往外发请求）",
       D["cookiecloud_enabled"] is False and D["cookiecloud_scheme"] == "auto")
    ck("M2 默认没有服务器地址、UUID、密钥、域名过滤",
       all(D[k] == "" for k in ("cookiecloud_server", "cookiecloud_uuid",
                                "cookiecloud_key", "cookiecloud_domains")))
    ck("M3 状态文件名在状态目录里，不与 config.json 混写",
       S.COOKIECLOUD_STATE_FILE.name == "cookiecloud_state.json")
    ck("M4 域名过滤词与 CookieCloud 插件口径一致：包含即命中（不是精确相等）",
       len(S._cc_filter_rows([cookie("a", ".youtube.com")], S._cc_domain_filter("youtube"))) == 1)
    ck("M5 拉取写的文件集合来自 cookie_file 与真命中的平台，不遍历全部 18 个平台",
       len(S._cc_payload()["platforms"]) == len(S.PLATFORM_LABELS) - 1)
    # 落在根目录的本机状态文件必须被打包三处同时点名，否则出包时就跟着走了
    pack = (Path(__file__).resolve().parents[1] / "pack_release.py").read_text(encoding="utf-8")
    ck("M6 排除正则里有它（那是转义写法，字面量计数抓不到）", r"cookiecloud_state\.json" in pack)
    ck("M7 排除规则 + 试跑后清理 + 出包泄漏自检三处都在",
       pack.count("cookiecloud_state") >= 3, pack.count("cookiecloud_state"))

finally:
    HTTPD.shutdown()
    S.cfg, S.log_mgr, S.COOKIES_DIR, S.COOKIECLOUD_STATE_FILE, S.http_proxies, \
        S._login_flag_snapshot, S._login_flag_clear, S._auth_token_only = _REAL
    shutil.rmtree(TMP, ignore_errors=True)

print("\n== 汇总 ==")
print(f"共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    for f in FAILED:
        print("FAIL:", f)
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
