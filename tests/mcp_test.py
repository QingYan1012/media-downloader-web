r"""MCP 桥（mcp_server.py）的离线自检。

全程不起真服务、不碰下载目录、不写 config：靶子是一台只绑 127.0.0.1 随机端口的假 HTTP 服务，
openapi 是手写的样例，专挑容易踩的形状（anyOf、$ref、枚举、自由 dict、路径参数、422、500、
二进制、超长 JSON、SSE）。要验的口径有四处：
  1. 映射：一条 /api/ 操作对应一个工具，同路径的 GET/POST 不能撞名；
  2. 拆参：查询参数走 URL、请求体走 body，多余的参数不许偷偷发出去（#186 那类「body 被当成
     查询参数」的缺陷，这里当守门项盯着）；
  3. 报错：状态码和服务原话必须带出来，只回「调用失败」等于没报；
  4. 脱敏：凭据类参数打码、响应体一个字都不落盘。

跑法：`python tests/mcp_test.py`（末行 FAILED 不为 0 就是没过）
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socket
import socketserver
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WEB))
os.environ["MEDIADOWNLOADER_BASE_URL"] = "http://127.0.0.1:1"  # 占位，假服务起来后改
os.environ["MEDIADOWNLOADER_MCP_TIMEOUT"] = "5"
import mcp_server as M  # noqa: E402

LOG = Path(tempfile.gettempdir()) / "mcp_test_calls.log"
LOG.unlink(missing_ok=True)
M.LOG_FILE = LOG
M.STREAM_PATHS = {"/api/events", "/api/slow"}

FAILED: list[str] = []
TOTAL = 0


def ck(name: str, cond: bool, detail=""):
    global TOTAL
    TOTAL += 1
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else "  <== " + str(detail)[:260]))
    if not cond:
        FAILED.append(name)


# ---------------------------------------------------------------- 假靶子
HITS: list[dict] = []

SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "fake", "version": "0"},
    "paths": {
        # 两条非 /api 的诱饵：不该变成工具
        "/": {"get": {"summary": "首页", "responses": {"200": {"description": "ok"}}}},
        "/static/app.js": {"get": {"responses": {"200": {"description": "ok"}}}},
        "/api/search": {"get": {
            "summary": "搜东西",
            "parameters": [
                {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                {"name": "limit", "in": "query", "schema": {"anyOf": [{"type": "integer"},
                                                                      {"type": "null"}],
                                                            "default": 20}},
                {"name": "tags", "in": "query", "schema": {"type": "array",
                                                           "items": {"enum": ["a", "b"]}}},
            ],
            "responses": {"200": {"description": "ok"}}}},
        "/api/thing": {
            "get": {"responses": {"200": {"description": "ok"}}},
            "post": {"requestBody": {"required": True, "content": {"application/json":
                                                                   {"schema": {"$ref":
                                                                    "#/components/schemas/Thing"}}}},
                     "responses": {"200": {"description": "ok"}}}},
        "/api/model": {"post": {
            "requestBody": {"required": True, "content": {"application/json":
                                                          {"schema": {"$ref":
                                                           "#/components/schemas/InModel"}}}},
            "responses": {"200": {"description": "ok"}}}},
        "/api/free": {"post": {
            "requestBody": {"required": True, "content": {"application/json":
                                                          {"schema": {"type": "object"}}}},
            "responses": {"200": {"description": "ok"}}}},
        "/api/bad": {"post": {
            "requestBody": {"required": True, "content": {"application/json":
                                                          {"schema": {"$ref":
                                                           "#/components/schemas/Sel"}}}},
            "responses": {"200": {"description": "ok"}}}},
        "/api/item/{itemId}": {"get": {
            "parameters": [{"name": "itemId", "in": "path", "required": True,
                           "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok"}}}},
        "/api/boom": {"get": {"responses": {"500": {"description": "x"}}}},
        "/api/file": {"get": {"responses": {"200": {"description": "x"}}}},
        "/api/big": {"get": {"responses": {"200": {"description": "x"}}}},
        "/api/secret": {"get": {"responses": {"200": {"description": "x"}}}},
        "/api/events": {"get": {"responses": {"200": {"description": "x"}}}},
        "/api/slow": {"get": {"responses": {"200": {"description": "x"}}}},
    },
    "components": {"schemas": {
        "Thing": {"type": "object", "properties": {"name": {"type": "string"}}},
        "Opt": {"type": "object", "properties": {"code": {"enum": ["x", "y"]},
                                                 "n": {"type": "integer"}}},
        "Meta": {"type": "object", "properties": {
            "name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "opts": {"type": "array", "items": {"$ref": "#/components/schemas/Opt"}}}},
        "InModel": {"type": "object", "required": ["enable"], "properties": {
            "enable": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
            "count": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "mode": {"enum": ["fast", "slow"], "type": "string", "default": "fast"},
            "meta": {"$ref": "#/components/schemas/Meta"}}},
        "Sel": {"type": "object", "required": ["task_id", "indices"], "properties": {
            "task_id": {"type": "string"},
            "indices": {"type": "array", "items": {"type": "integer"}}}},
    }}
}

SECRET = "SET-COOKIE-LEAK-1234567890"


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        pass

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, lines: list[str], code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for s in lines:
            self.wfile.write(s.encode("utf-8"))
            self.wfile.flush()

    def _go(self, method: str):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        hit = {"method": method, "path": u.path,
               "query": {k: v for k, v in urllib.parse.parse_qs(u.query).items()},
               "body": json.loads(raw.decode("utf-8")) if raw else None}
        HITS.append(hit)
        if u.path == "/openapi.json":
            return self._send(200, "application/json", json.dumps(SPEC).encode())
        if u.path == "/api/bad":
            return self._send(422, "application/json", json.dumps({"detail": [
                {"type": "missing", "loc": ["body", "task_id"], "msg": "Field required"}]}).encode())
        if u.path == "/api/boom":
            return self._send(500, "text/plain; charset=utf-8", "磁盘满了，写不进去".encode())
        if u.path == "/api/file":
            return self._send(200, "application/octet-stream", b"\x00\x01" * 50)
        if u.path == "/api/big":
            return self._send(200, "application/json",
                              json.dumps({"text": "长" * 4000}).encode())
        if u.path == "/api/secret":
            return self._send(200, "application/json", json.dumps({"ok": True,
                                                                   "cookie": SECRET}).encode())
        if u.path == "/api/events":
            return self._stream([": ping\n\n", 'data: {"running": 3}\n\n'])
        if u.path == "/api/slow":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                import time as _t
                _t.sleep(30)  # 一直不发事件
            except Exception:
                pass
            return
        if u.path.startswith("/api/item/"):
            return self._send(200, "application/json", json.dumps(
                {"id": u.path.rsplit("/", 1)[-1], "query": hit["query"]}).encode())
        return self._send(200, "application/json", json.dumps({"ok": True, "hit": hit}).encode())

    def do_GET(self):
        self._go("get")

    def do_POST(self):
        self._go("post")


class Serv(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


srv = Serv(("127.0.0.1", 0), H)   # 不能用 with：出了块就把监听 socket 关了，线程只会拿到 -1
PORT = srv.server_address[1]
os.environ["MEDIADOWNLOADER_BASE_URL"] = f"http://127.0.0.1:{PORT}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
for _ in range(50):  # 等它真的开始监听，别让第一批请求撞上空窗
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/openapi.json", timeout=2).read()
        break
    except Exception:
        import time as _t
        _t.sleep(0.1)


def tools_():
    return {t["name"]: t for t in M.build_tools(SPEC)}


NOTE = [""]


def call(name: str, args: dict | None = None):
    by = tools_()
    if name not in by:
        return True, f"没有这个工具：{name}"
    err, txt, note = M._call_tool(by[name], args or {})
    NOTE[0] = note
    return err, txt


def last_hit():
    return HITS[-1]


def text_of(res):
    return (res.get("content") or [{}])[0].get("text", "")


# ---------------------------------------------------------------- A 映射
by = tools_()
api_ops = [(m, p) for p, v in SPEC["paths"].items() if p.startswith("/api/")
           for m in v if m in ("get", "post")]
ck("A1 工具数 = openapi 里 /api/ 的操作数", len(by) == len(api_ops) == 13, f"{len(by)} vs {len(api_ops)}")
ck("A2 非 /api 的接口没被做成工具", "/" not in by and "/static/app.js" not in str(by.values()), "")
ck("A3 同路径的 GET/POST 各自带动词前缀", "get_thing" in by and "post_thing" in by, sorted(by))
ck("A4 工具名唯一", len({t["name"] for t in M.build_tools(SPEC)}) == 13, sorted(by))
ck("A5 每条描述都点名 METHOD + path",
   all("[GET /api/" in t["description"] or "[POST /api/" in t["description"]
       for t in M.build_tools(SPEC)), [t["description"] for t in M.build_tools(SPEC)][:3])
lst = M._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
M.TOOLS = M.build_tools(SPEC)
lst = M._handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
one = lst["result"]["tools"][0]
ck("A6 tools/list 不外泄内部字段", set(one) == {"name", "description", "inputSchema"}, sorted(one))
ck("A7 每个 inputSchema 都是封闭对象",
   all(t["inputSchema"]["type"] == "object" and t["inputSchema"]["additionalProperties"] is False
       for t in M.build_tools(SPEC)), "")

# ---------------------------------------------------------------- B 类型解包
im = SPEC["components"]["schemas"]["InModel"]["properties"]
ck("B0 靶子的字段确实是 anyOf/$ref 写的（不是直接给 type）",
   "anyOf" in im["enable"] and "$ref" in im["meta"], json.dumps(im["enable"]))
mp = by["model"]["inputSchema"]["properties"]
ck("B1 可空布尔解成 boolean、可空整数解成 integer",
   mp["enable"]["type"] == "boolean" and mp["count"]["type"] == "integer", mp["enable"])


def naive(v):  # 修复前的取法：只挑现成的 key
    out = {k: v[k] for k in ("type", "enum", "items", "default", "description") if k in v}
    out.setdefault("type", "string")
    return out


ck("B2 反向对照：不解包就全成了 string（所以 B1 抓的是真缺陷）",
   naive(im["enable"])["type"] == "string" and naive(im["meta"])["type"] == "string",
   json.dumps([naive(im["enable"]), naive(im["meta"])]))
ck("B3 枚举和默认值都留着",
   mp["mode"]["enum"] == ["fast", "slow"] and mp["mode"]["default"] == "fast", mp["mode"])
ck("B4 $ref 嵌套模型摊成 object 且子字段可见",
   mp["meta"]["type"] == "object" and set(mp["meta"]["properties"]) == {"name", "opts"}, mp["meta"])
ck("B5 数组里套 $ref 也能摊平（枚举不丢）",
   mp["meta"]["properties"]["opts"]["items"]["properties"]["code"]["enum"] == ["x", "y"],
   mp["meta"]["properties"]["opts"])
ck("B6 查询参数的可空整数不是 string",
   by["search"]["inputSchema"]["properties"]["limit"]["type"] == "integer",
   by["search"]["inputSchema"]["properties"]["limit"])
ck("B7 必填项来自 openapi 而不是猜",
   by["model"]["inputSchema"]["required"] == ["enable"]
   and by["bad"]["inputSchema"]["required"] == ["indices", "task_id"],
   by["bad"]["inputSchema"]["required"])
leftover = [(t["name"], k) for t in M.build_tools(SPEC)
            for k, v in t["inputSchema"]["properties"].items()
            if "anyOf" in v or "$ref" in v or "oneOf" in v]
ck("B8 全量扫完：参数表里没有没解开的 anyOf/$ref", leftover == [], leftover)
ck("B9 路径参数也在参数表里并且必填",
   "itemId" in by["item_itemid"]["inputSchema"]["properties"]
   and "itemId" in by["item_itemid"]["inputSchema"]["required"], by["item_itemid"]["inputSchema"])

# ---------------------------------------------------------------- C 拆参
HITS.clear()
call("search", {"q": "周处", "limit": 5, "tags": ["a", "b"], "顺手": "不该发出去"})
hh = last_hit()
ck("C1 查询参数走 URL：值原样、数组按 doseq 展开",
   hh["path"] == "/api/search" and hh["query"]["q"] == ["周处"]
   and hh["query"]["tags"] == ["a", "b"], hh)
ck("C2 请求体没被塞进查询串（GET 也不带 body）", hh["body"] is None, hh)
ck("C3 schema 里没有的参数不会偷偷发出去",
   "顺手" not in json.dumps(hh, ensure_ascii=False), hh)
call("post_thing", {"name": "abc"})
hh = last_hit()
ck("C4 POST 具名模型：参数只进 body，query 为空",
   hh["body"] == {"name": "abc"} and hh["query"] == {}, hh)
call("model", {"enable": True, "count": 3, "meta": {"name": None}})
hh = last_hit()
ck("C5 布尔/整数到服务端仍是原类型，没被字符串化",
   hh["body"]["enable"] is True and hh["body"]["count"] == 3, hh["body"])
ck("C6 没给的选填字段不补空值", "mode" not in hh["body"], hh["body"])
call("bad")
hh = last_hit()
ck("C7 空参数的 POST 发的是 {} 而不是裸 POST", hh["body"] == {}, hh)
call("free", {"payload": {"a": 1, "b": [2, 3]}})
ck("C8 自由 dict 接口整包走 payload", last_hit()["body"] == {"a": 1, "b": [2, 3]}, last_hit())
ck("C9 自由 dict 只暴露一个 payload 参数",
   list(by["free"]["inputSchema"]["properties"]) == ["payload"], by["free"]["inputSchema"])
call("item_itemid", {"itemId": "12/34", "q": "带在 query"})
hh = last_hit()
ck("C10 路径参数填进 URL 并转义，不再当查询参数",
   hh["path"] == "/api/item/12%2F34" or hh["path"] == "/api/item/12/34", hh)

# ---------------------------------------------------------------- D 报错口径
err, txt = call("bad", {"task_id": "t1"})  # indices 缺失 -> 靶子回 422
ck("D1 4xx：isError + 状态码 + URL + 服务原话",
   err and "422" in txt and "Field required" in txt and "/api/bad" in txt, txt)
err, txt = call("boom")
ck("D2 5xx 纯文本把原话带出来（不是只报字节数）",
   err and "500" in txt and "磁盘满了" in txt, txt)
err, txt = call("file")
ck("D3 二进制响应只报类型和大小，不塞字节",
   not err and "octet-stream" in txt and "100 字节" in txt, txt)
old, M.MAX_TEXT = M.MAX_TEXT, 300
err, txt = call("big")
ck("D4 超长结果截断并写明上限", "已截断到 300 字" in txt and len(txt) < 400, len(txt))
M.MAX_TEXT = old
err, txt = call("search", {"q": "x"})  # 参数齐但必填校验在真服务才有意义；这里回 200
ck("D5 正常调用里没有「连不上」字样（反向对照）",
   not err and "MEDIADOWNLOADER_BASE_URL" not in txt, txt)
os.environ["MEDIADOWNLOADER_BASE_URL"] = "http://127.0.0.1:1"
err, txt = call("search", {"q": "x"})
ck("D6 连不上时点名当前 BASE 并给出下一步",
   err and "连不上" in txt and "MEDIADOWNLOADER_BASE_URL" in txt and ":1/api/search" in txt, txt)
os.environ["MEDIADOWNLOADER_BASE_URL"] = f"http://127.0.0.1:{PORT}"
err, txt = call("no_such_tool", {})
ck("D7 未知工具说「没有这个工具」", err and "没有这个工具" in txt, txt)

# ---------------------------------------------------------------- E 日志脱敏
# 日志是在协议层（tools/call）落的，直接用 _call_tool 不会留痕，这一段必须走 _handle
_seq = [0]


def hcall(name: str, args: dict | None = None):
    _seq[0] += 1
    r = M._handle({"jsonrpc": "2.0", "id": _seq[0], "method": "tools/call",
                   "params": {"name": name, "arguments": args or {}}})
    res = r["result"]
    return res.get("isError"), text_of(res)


LOG.unlink(missing_ok=True)
hcall("search", {"q": "普通值"})
hcall("free", {"payload": {"cookie": "SESS=abc", "token": "t-1",
                           "deep": {"api_key": "KKK", "sendKey": "SK-1"}}})
hcall("free", {"payload": {"长文": "Z" * 300}})
logtxt = LOG.read_text(encoding="utf-8")
ck("E1 cookie/token/api_key/sendKey 的值都变「已隐藏」",
   logtxt.count("<已隐藏>") >= 4 and "SESS=abc" not in logtxt and "KKK" not in logtxt
   and "t-1" not in logtxt and "SK-1" not in logtxt, logtxt)
ck("E2 嵌套 dict 里的凭据也藏得住", "deep" in logtxt and "api_key" in logtxt
   and "KKK" not in logtxt, logtxt)
ck("E3 超长字符串留前 80 字并标总长", "…(共 300 字)" in logtxt, logtxt)
ck("E4 普通参数照旧可查（反向：不是全抹掉）", "普通值" in logtxt, logtxt)
err, txt = hcall("secret")
logtxt = LOG.read_text(encoding="utf-8")
ck("E5 响应体确实给了调用方", SECRET in txt, txt[:120])
ck("E6 但响应体一个字都不进日志", SECRET not in logtxt, logtxt.splitlines()[-1])
ck("E7 日志留的是「哪个工具、参数形状、成败、状态码与大小」",
   " free " in logtxt and "-> ok" in logtxt and "POST /api/free" in logtxt
   and "字节" in logtxt, logtxt.splitlines()[-2:])
ck("E8 出错也在日志里标出来", hcall("bad", {})[0] and "ERROR" in
   LOG.read_text(encoding="utf-8").splitlines()[-1], LOG.read_text(encoding="utf-8").splitlines()[-1])
M.LOG_FILE = Path(tempfile.gettempdir()) / "这目录不存在呀" / "x.log"
err, txt = call("search", {"q": "y"})
ck("E9 日志写不下去也不能影响调用本身", not err and '"ok": true' in txt, txt[:120])
M.LOG_FILE = LOG

# ---------------------------------------------------------------- F SSE
err, txt = call("events")
ck("F1 推送流只取第一条 data:，心跳注释被跳过",
   not err and txt.startswith('data: {"running": 3}') and "只取第一条" in txt, txt)
ck("F2 工具描述里写明不会挂住",
   "实时推送流" in by["events"]["description"], by["events"]["description"])
M.TIMEOUT = 1.0
err, txt = call("slow")
ck("F3 流开着但没事件时说「没有新事件」，不说「连不上」",
   not err and "没有新事件" in txt and "连不上" not in txt, txt)
M.TIMEOUT = 5.0

# ---------------------------------------------------------------- G 只连本机
os.environ["MEDIADOWNLOADER_BASE_URL"] = "http://localhost:8765"
ck("G1 localhost 放行", M.base_url() == "http://localhost:8765", M.base_url())
for bad_base in ("http://10.0.0.5:8765", "https://example.com", "http://192.168.1.7:8765/api",
                 "127.0.0.1:8765"):
    os.environ["MEDIADOWNLOADER_BASE_URL"] = bad_base
    try:
        M.base_url()
        got = ""
    except SystemExit as e:
        got = str(e)
    ck(f"G2 拒绝非环回/畸形地址 {bad_base}", "只允许连本机" in got, got)
os.environ["MEDIADOWNLOADER_BASE_URL"] = f"http://127.0.0.1:{PORT}/"
ck("G3 末尾斜杠不影响", M.base_url() == f"http://127.0.0.1:{PORT}", M.base_url())

# ---------------------------------------------------------------- H 协议与版本
r = M._handle({"jsonrpc": "2.0", "id": 7, "method": "initialize",
               "params": {"protocolVersion": "2024-11-05"}})
ck("H1 客户端报旧版本就沿用旧版本", r["result"]["protocolVersion"] == "2024-11-05", r)
r = M._handle({"jsonrpc": "2.0", "id": 8, "method": "initialize",
               "params": {"protocolVersion": "2099-01-01"}})
ck("H2 客户端报未来版本不会假装支持", r["result"]["protocolVersion"] == M.PROTOCOL, r)
ck("H3 通知不回话", M._handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None, "")
ck("H4 ping 回空 result", M._handle({"jsonrpc": "2.0", "id": 9, "method": "ping"})["result"] == {}, "")
r = M._handle({"jsonrpc": "2.0", "id": 10, "method": "bogus"})
ck("H5 未知方法给 -32601", r["error"]["code"] == -32601, r)
html = (WEB / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
ck("H6 serverInfo 的版本就是界面里那个真源",
   M._app_version().split(" ")[0] in re.search(r"const appVersion = '([^']+)'", html).group(1),
   M._app_version())
r = M._handle({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
               "params": {"name": "search", "arguments": {"q": "协议层也要走通"}}})
ck("H7 tools/call 从协议层真的通",
   r["result"]["isError"] is False and "协议层也要走通" in text_of(r["result"]), r)

srv.shutdown()
print(f"\nTOTAL: {TOTAL} FAILED: {len(FAILED)}")
for f in FAILED:
    print("  - " + f)
sys.exit(1 if FAILED else 0)
