"""MCP 桥：把本机 MediaDownloader 的 HTTP 接口原样映射成 MCP 工具（stdio 传输，零额外依赖）。

设计口径（都写在代码里，别处不用猜）：
  - 工具清单不手写，开桥时从 `<BASE>/openapi.json` 现取，所以接口增减会自动跟上；
  - 只连本机：BASE 默认 http://127.0.0.1:8765，可用环境变量改端口，但只允许 127.0.0.1/localhost；
  - 请求体的拆法照 openapi 来：具名模型的字段摊平成工具参数，自由 dict 的接口用一个 payload 整包传；
  - 出错要把服务的原话带出来（状态码 + 响应体摘要），只回「调用失败」等于没报；
  - 日志只记调了什么工具、参数形状与结果状态，凭据类字段一律打码，响应体一个字都不落盘。

跑法：`python mcp_server.py`（供 MCP 客户端拉起）；`python mcp_server.py --tools` 只看映射结果。
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROTOCOL = "2025-06-18"
DEFAULT_BASE = "http://127.0.0.1:8765"
TIMEOUT = float(os.environ.get("MEDIADOWNLOADER_MCP_TIMEOUT") or 60)
LOG_FILE = APP_DIR / "mcp_calls.log"
# 这些接口的响应不是一次性 JSON：/api/events 是实时推送，取第一条就收口
STREAM_PATHS = {"/api/events"}
# 参数名里出现这些字样就不能进日志（值也不能带）
REDACT = ("cookie", "token", "secret", "password", "passwd", "api_hash", "apikey",
          "api_key", "send_key", "sendkey", "authorization", "key")
MAX_TEXT = 20000  # 单个工具结果给客户端的上限，超出截断并说明


def base_url() -> str:
    raw = (os.environ.get("MEDIADOWNLOADER_BASE_URL") or DEFAULT_BASE).rstrip("/")
    m = re.match(r"^https?://([^/:]+)(:\d+)?$", raw)
    host = (m.group(1).lower() if m else "")
    if host not in ("127.0.0.1", "localhost", "::1"):
        # 只监听本机是这整套东西的前提；改成远端就等于把无鉴权接口暴露出去
        raise SystemExit(f"MCP 只允许连本机，BASE 的 host 必须是 127.0.0.1/localhost，当前是 {raw}")
    return raw


# 环回地址不该走系统代理：注册表代理一开，连本机都要绕一圈，失败信息还很难看
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http(url: str, payload=None, timeout: float = None):
    """发一次请求，返回 (状态码, content-type, 原始字节)。非 2xx 也照样把响应体带回来。"""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with _OPENER.open(req, timeout=timeout or TIMEOUT) as r:
            return r.status, (r.headers.get("content-type") or ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("content-type") if e.headers else "") or "", e.read()


def _app_version() -> str:
    """版本号只有一处真源（界面里的 appVersion），桥跟着它，别自己写死一个过期的。"""
    try:
        html = (APP_DIR / "static" / "index.html").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"const appVersion = '([^']+)'", html)
        if m:
            return m.group(1).split(" ")[0]
    except OSError:
        pass
    return "unknown"


def _deref(schema: dict, spec: dict, depth: int = 0) -> dict:
    """把 $ref / anyOf(可空) 展平成一个能直接给客户端看的 schema。"""
    s = schema or {}
    if depth > 4:
        return {"type": "string"}
    if "$ref" in s:
        name = s["$ref"].split("/")[-1]
        return _deref((spec.get("components") or {}).get("schemas", {}).get(name, {}), spec, depth + 1)
    if "anyOf" in s or "oneOf" in s:
        parts = [x for x in (s.get("anyOf") or s.get("oneOf") or []) if x.get("type") != "null"]
        out = _deref(parts[0] if parts else {}, spec, depth + 1)
        for k in ("description", "default"):
            if k in s:
                out[k] = s[k]
        return out
    if "items" in s:
        s = dict(s)
        s["items"] = _deref(s["items"], spec, depth + 1)
    return s


def _prop(schema: dict, spec: dict, depth: int = 0) -> dict:
    """摊平成客户端能照着填的参数：对象和数组的子字段要一路带下去，不然只能靠猜。"""
    s = _deref(schema, spec, depth)
    out = {k: s[k] for k in ("type", "enum", "default", "description", "format") if k in s}
    out.setdefault("type", "string")
    if s.get("type") == "object" and s.get("properties"):
        out["properties"] = {k: _prop(v, spec, depth + 1) for k, v in s["properties"].items()}
        if s.get("required"):
            out["required"] = list(s["required"])
    if "items" in s:
        out["items"] = _prop(s["items"], spec, depth + 1)
    return out


def _tool_name(path: str, method: str) -> str:
    body = re.sub(r"[^a-zA-Z0-9]+", "_", path[len("/api"):]).strip("_").lower()
    return body or "root"


def build_tools(spec: dict) -> list:
    """openapi -> MCP 工具清单。同名（同一路径挂了 GET 又挂 POST）时补上动词。"""
    raw = []
    for path, item in (spec.get("paths") or {}).items():
        if not path.startswith("/api/"):
            continue
        for method, op in (item or {}).items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            raw.append((path, method, op))
    raw.sort(key=lambda r: (r[0], r[1]))
    used = {}
    tools = []
    for path, method, op in raw:
        name = _tool_name(path, method)
        used[name] = used.get(name, 0) + 1
        if used[name] > 1 or any(_tool_name(p, m) == name for p, m, _ in raw if (p, m) != (path, method)):
            name = f"{method}_{name}"
        props, required, q_names, p_names, b_names, free_body = {}, [], [], [], [], False
        for p in op.get("parameters") or []:
            if p.get("in") not in ("query", "path"):
                continue
            props[p["name"]] = _prop(p.get("schema") or {}, spec)
            (p_names if p.get("in") == "path" else q_names).append(p["name"])
            if p.get("required"):
                required.append(p["name"])
        rb = ((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}
        if rb.get("schema"):
            bs = _deref(rb["schema"], spec)
            if bs.get("properties"):
                for k, raw_v in bs["properties"].items():
                    if k in props:
                        continue
                    # 字段本身也可能是 anyOf（Optional[x]）或 $ref（嵌套模型），不解开就只剩默认 string
                    props[k] = _prop(raw_v, spec)
                    b_names.append(k)
                    if k in (bs.get("required") or []):
                        required.append(k)
            else:
                # 接口签名是 body: dict，openapi 里没字段可摊平，整包传
                props["payload"] = {"type": "object",
                                    "description": "这个接口收自由结构的 JSON，整包放这里"}
                b_names.append("__payload__")
                free_body = True
                if rb.get("required"):
                    required.append("payload")
        desc = (op.get("summary") or op.get("description") or "").strip()
        note = f"{method.upper()} {path}"
        if path in STREAM_PATHS:
            note += "｜实时推送流：只取第一条事件就返回，不会挂在那儿等"
        tools.append({
            "name": name,
            "description": (desc + "  " if desc else "") + f"[{note}]",
            "inputSchema": {"type": "object", "properties": props,
                            "required": sorted(set(required)), "additionalProperties": False},
            "_call": {"path": path, "method": method, "query": q_names,
                      "pathParams": p_names, "body": b_names, "freeBody": free_body},
        })
    return tools


def _redact(args: dict) -> dict:
    out = {}
    for k, v in (args or {}).items():
        if any(r in k.lower() for r in REDACT):
            out[k] = "<已隐藏>"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        elif isinstance(v, str) and len(v) > 80:
            out[k] = v[:80] + f"…(共 {len(v)} 字)"
        else:
            out[k] = v
    return out


def _log(line: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # 日志写不下去不能影响调用本身


def _call_tool(tool: dict, args: dict):
    """返回 (是否出错, 给客户端的文本, 只用于日志的安全摘要)。

    第三项绝不含响应内容：接口回的东西里可能有 Cookie、Bot Token、密钥（/api/config 就是一例），
    而 mcp_calls.log 是要留在硬盘上的。
    """
    spec = tool["_call"]
    args = args or {}
    path = spec["path"]
    verb = spec["method"].upper()
    # 路径里的 {id} 得真填进去，当成查询参数发出去就是 404（当前接口没有路径参数，这条是给以后兜底）
    for k in spec.get("pathParams") or []:
        if k not in args:
            return True, f"缺少路径参数 {k}（{verb} {path} 要用它）", f"{verb} {path} 缺参数 {k}"
        path = path.replace("{%s}" % k, urllib.parse.quote(str(args[k]), safe=""))
    q = {k: args[k] for k in spec["query"] if k in args}
    url = base_url() + path
    if q:
        url += "?" + urllib.parse.urlencode(q, doseq=True)
    payload = None
    if spec["body"]:
        if spec["freeBody"]:
            payload = args.get("payload")
        else:
            payload = {k: args[k] for k in spec["body"] if k in args}
            if not payload:
                payload = None if spec["method"] == "get" else {}
    t0 = time.time()
    if spec["path"] in STREAM_PATHS:
        return _peek_stream(url, t0)
    try:
        code, ctype, raw = _http(url, payload)
    except Exception as e:
        # 服务没起 / 端口不对是这里最常见的失败，得点名 BASE 地址，否则排查全靠猜
        return True, (f"连不上 {url}：{type(e).__name__}: {e}"
                      f"｜先确认服务在跑，或把 MEDIADOWNLOADER_BASE_URL 指对（当前 {base_url()}）"), \
            f"{verb} {path} 连不上"
    cost = time.time() - t0
    note = f"{verb} {path} {code}，{len(raw)} 字节，{cost:.1f}s"
    body = _brief(ctype, raw)
    if code >= 400:
        return True, f"{code} {url}（{cost:.1f}s）：{body}", note
    return False, body, note


def _brief(ctype: str, raw: bytes) -> str:
    if not raw:
        return "(空响应)"
    if "json" in ctype:
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
            txt = json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            txt = raw.decode("utf-8", "replace")
    elif ctype.startswith("text/"):
        # 报错页、纯文本结果：原话比「多少字节」有用得多
        txt = raw.decode("utf-8", "replace")
    else:
        # 文件/压缩包这类响应不能整份塞进对话，只报是什么、多大
        txt = f"(非 JSON 响应 content-type={ctype or '未知'}，{len(raw)} 字节)"
    if len(txt) > MAX_TEXT:
        txt = txt[:MAX_TEXT] + f"\n…（结果过长，已截断到 {MAX_TEXT} 字）"
    return txt


def _peek_stream(url: str, t0: float):
    """SSE 只取第一条 data:，取到就断，不让客户端等到超时。"""
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    first = ""
    got = 0
    try:
        with _OPENER.open(req, timeout=min(TIMEOUT, 15)) as r:
            try:
                for _ in range(200):
                    line = r.readline()
                    if not line:
                        break
                    s = line.decode("utf-8", "replace").strip()
                    if s.startswith("data:"):
                        first = s
                        got += 1
                        break
                    if s:
                        got += 1
            except (TimeoutError, socket.timeout):
                pass  # 流是开着的，只是这段时间没有新事件——不能报成「连不上」
    except Exception as e:
        return True, f"连不上 {url}：{type(e).__name__}: {e}", "GET /api/events 连不上"
    cost = time.time() - t0
    note = f"GET {url.split('?')[0]} sse {got} 帧，{cost:.1f}s"
    if not first:
        return False, f"(流开着但 {min(TIMEOUT, 15)} 秒内没有新事件，{cost:.1f}s)", note
    return False, first + f"\n(只取第一条，{cost:.1f}s)", note


def _load_spec():
    code, ctype, raw = _http(base_url() + "/openapi.json")
    if code >= 400 or "json" not in ctype:
        raise SystemExit(f"取不到 {base_url()}/openapi.json（{code}）：{ _brief(ctype, raw)[:200] }"
                         "｜服务得先跑起来")
    return json.loads(raw.decode("utf-8", "replace"))


TOOLS: list = []


def _handle(msg: dict):
    """一条 JSON-RPC 请求 -> 响应体（通知返回 None）。"""
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if method == "initialize":
        want = params.get("protocolVersion") or PROTOCOL
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": min(want, PROTOCOL),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "media-downloader", "version": _app_version()},
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"tools": [{k: t[k] for k in ("name", "description", "inputSchema")}
                                     for t in TOOLS]}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            _log(f"{datetime.now().isoformat(timespec='seconds')} 未知工具 {name}")
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"isError": True, "content": [{"type": "text",
                                    "text": f"没有这个工具：{name}"}]}}
        err, text, note = _call_tool(tool, args)
        # 落盘的只有「调了哪个工具、参数形状（打码后）、成功与否、状态码与大小」；响应内容一个字都不写
        _log("%s %s %s -> %s | %s" % (
            datetime.now().isoformat(timespec="seconds"), name,
            json.dumps(_redact(args), ensure_ascii=False)[:300],
            "ERROR" if err else "ok", note))
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"isError": err, "content": [{"type": "text", "text": text}]}}
    if mid is None:  # 没 id 的都是通知，不许回话
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"不支持的方法：{method}"}}


def main():
    global TOOLS
    if "--tools" in sys.argv:
        TOOLS = build_tools(_load_spec())
        print(json.dumps({"base": base_url(), "tools": len(TOOLS),
                          "names": [t["name"] for t in TOOLS]}, ensure_ascii=False, indent=1))
        return
    TOOLS = build_tools(_load_spec())
    _log(f"{datetime.now().isoformat(timespec='seconds')} 桥启动 base={base_url()} 工具 {len(TOOLS)} 个")
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line.decode("utf-8", "replace"))
        except Exception as e:
            _log(f"收到不是一行 JSON 的输入：{e}")
            continue
        try:
            resp = _handle(msg)
        except Exception as e:  # 单条请求崩了不能带垮整个桥
            resp = {"jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32000, "message": f"{type(e).__name__}: {str(e)[:200]}"}}
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()


if __name__ == "__main__":
    main()
