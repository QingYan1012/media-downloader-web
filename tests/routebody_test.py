r"""请求体模型的自检：路由签名里用到的 Pydantic 模型，必须在装饰那一刻就已经定义。

server.py 顶部有 `from __future__ import annotations`，函数注解是字符串；FastAPI 在写
`@app.post(...)` 的那一刻就要把注解解析成类型。解析不到（类还在文件后面才定义）不会报错，
而是把这个参数**降级成查询参数**：
  - 必填的（`body: IdsBody`）→ POST JSON 直接报「缺参数」，接口等于不能用；
  - 选填的（`body: IdsBody = None`）→ 永远收到 None，于是 /api/live/end 不分对象地
    结束所有录制，属于「不报错但做错事」，更难发现。
另外 /openapi.json 会整个 500（MCP 和接口文档都从它取）。

全程不起服务、不写 config、不碰下载目录：被点的队列方法全部换成记账桩。

跑法：`python tests/routebody_test.py`（末行 FAILED 不为 0 就是没过）
"""
from __future__ import annotations

import sys
import typing
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pydantic  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server as S  # noqa: E402

FAILED: List[str] = []
TOTAL = 0


def ck(name: str, cond: bool, detail=""):
    global TOTAL
    TOTAL += 1
    print(("OK   " if cond else "FAIL ") + name + ("" if cond else "  <== " + str(detail)[:300]))
    if not cond:
        FAILED.append(name)


def _qnames(route) -> List[str]:
    """FastAPI 认定这个接口收哪些查询参数（降级后的模型就会混在这里）。"""
    dep = getattr(route, "dependant", None)
    if dep is None:
        return []
    return [getattr(f, "name", None) or getattr(f, "alias", "") for f in dep.query_params]


def _model_params(fn) -> List[str]:
    """函数签名里标了 BaseModel 子类的参数名（此时模块已加载完，注解一定能解析）。"""
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        return []
    return [n for n, a in hints.items()
            if isinstance(a, type) and issubclass(a, pydantic.BaseModel)]


# ---------- A. OpenAPI 必须生成得出来 ----------
try:
    SPEC = S.app.openapi()
    n_paths = len(SPEC.get("paths") or {})
    ck("A1 openapi 生成得出（MCP 与接口文档都从它取）", n_paths > 100, n_paths)
except Exception as e:
    SPEC, n_paths = {}, 0
    ck("A1 openapi 生成得出", False, "%s: %s" % (type(e).__name__, str(e)[:200]))

# ---------- B. 请求体模型不能掉进查询参数 ----------
leaked: List[tuple] = []
checked_routes = 0
for r in S.app.routes:
    fn = getattr(r, "endpoint", None)
    if fn is None:
        continue
    models = _model_params(fn)
    if not models:
        continue
    checked_routes += 1
    bad = [m for m in models if m in _qnames(r)]
    if bad:
        leaked.append((getattr(r, "path", "?"), getattr(r, "methods", set()), bad))
ck("B1 每个请求体模型都走请求体（没有一个漏进查询参数）", not leaked, leaked)
# 正向对照：B1 不是空跑——真有一批接口带请求体
ck("B2 确实有 %d 个接口带请求体模型（不然 B1 只是查了个空集）" % checked_routes,
   checked_routes >= 30, checked_routes)

# openapi 侧再查一遍：文档里出现名为 body 的 query 参数就是同一个毛病
doc_bad = []
for path, item in (SPEC.get("paths") or {}).items():
    for method, op in (item or {}).items():
        for p in op.get("parameters") or []:
            if p.get("in") == "query" and p.get("name") in ("body",):
                doc_bad.append("%s %s" % (method.upper(), path))
ck("B3 openapi 文档里没有任何接口把 body 写成查询参数", not doc_bad, doc_bad)

# ---------- C. 真调用：这些接口要能吃 JSON 请求体 ----------
calls: dict = {}


class _FakeLog:
    def log(self, *a, **k):
        calls.setdefault("log", []).append(a)


def _record(key):
    def _f(*a, **k):
        calls[key] = {"args": a, "kw": k}
        return []
    return _f


_REAL = {"pin_tasks": S.queue.pin_tasks, "move_to_top": S.queue.move_to_top,
         "set_later": S.queue.set_later, "end_live_tasks": S.queue.end_live_tasks,
         "finalize_part_files": S.finalize_part_files, "log_mgr": S.log_mgr}
try:
    S.log_mgr = _FakeLog()
    S.queue.pin_tasks = _record("pin")
    S.queue.move_to_top = _record("top")
    S.queue.set_later = _record("later")
    S.queue.end_live_tasks = _record("end")
    S.finalize_part_files = lambda *a, **k: 0  # 别真去扫下载目录收 .part
    client = TestClient(S.app)

    # 五个点名任务的接口：ids 要从请求体里读到
    for path, key, flag in [("/api/tasks/pin", "pin", "pinned"), ("/api/tasks/unpin", "pin", "pinned"),
                            ("/api/tasks/top", "top", None), ("/api/tasks/later", "later", "later"),
                            ("/api/tasks/start-later", "later", "later")]:
        calls.clear()
        resp = client.post(path, json={"ids": ["tid-abc"]})
        got = calls.get(key) or {}
        ids = (got.get("args") or [None])[0]
        # 置顶/稍后都带一个布尔标记，值必须是该接口的那一种，不然等于按错了钮
        if flag is None:
            marked = True
        else:
            val = (got.get("kw") or {}).get(flag)
            want_val = {"pinned": "unpin" not in path,
                        "later": path == "/api/tasks/later"}[flag]
            marked = val is want_val
        ck("C %s 把请求体里的 ids 和状态标记都送到了（修复前它只会报缺参数）" % path,
           resp.status_code == 200 and ids == ["tid-abc"] and marked,
           {"status": resp.status_code, "calls": calls.get(key), "body": resp.text[:120]})

    # 选填的那个：给了 ids 就必须点名，不给才是全部 —— 修复前 ids 永远是 None
    calls.clear()
    resp = client.post("/api/live/end", json={"ids": ["tid-live-1"]})
    arg = (calls.get("end", {}).get("args") or ["<没调用>"])[0]
    ck("C /api/live/end 点名一条时只结束这一条（修复前把 None 传下去 = 结束全部录制）",
       resp.status_code == 200 and arg == ["tid-live-1"], {"status": resp.status_code, "ids": arg})
    calls.clear()
    resp = client.post("/api/live/end", json={})
    arg2 = (calls.get("end", {}).get("args") or ["<没调用>"])[0]
    ck("C /api/live/end 不带 ids 时仍是「全部」（选填语义没被改坏）",
       resp.status_code == 200 and not arg2, {"status": resp.status_code, "ids": arg2})
finally:
    S.log_mgr = _REAL["log_mgr"]
    S.queue.pin_tasks = _REAL["pin_tasks"]
    S.queue.move_to_top = _REAL["move_to_top"]
    S.queue.set_later = _REAL["set_later"]
    S.queue.end_live_tasks = _REAL["end_live_tasks"]
    S.finalize_part_files = _REAL["finalize_part_files"]

# ---------- D. 反向验证：把「先用后定义」原样复现一遍，确认上面几条真的会红 ----------
# 这两条路由故意写在 MiniBody 定义之前，装饰时就解析不到类型。
app2 = FastAPI()


@app2.post("/mini-pin")
def mini_pin(body: MiniBody):  # noqa: F821  故意引用还没定义的模型
    return {"ids": body.ids}


@app2.post("/mini-end")
def mini_end(body: MiniBody = None):  # noqa: F821
    return {"all": body is None}


class MiniBody(pydantic.BaseModel):
    ids: List[str] = []


ck("D1 复现出来的接口确实掉进了查询参数（证明 B1 测的是这个坑）",
   "body" in _qnames([r for r in app2.routes if getattr(r, "path", "") == "/mini-pin"][0]),
   _qnames([r for r in app2.routes if getattr(r, "path", "") == "/mini-pin"][0]))
try:
    app2.openapi()
    d2 = False
except Exception as e:
    d2 = True
    print("   复现的接口生成 openapi 时的报错（就是线上那一个）: %s" % str(e)[:160])
ck("D2 复现出来的接口让 openapi 生成失败（证明 A1 不是空断言）", d2, "竟然生成成功")
c2 = TestClient(app2)
r2 = c2.post("/mini-pin", json={"ids": ["x"]})
ck("D3 复现出来的接口 POST JSON 会被拒（证明 C 那几条测的是请求体通道）",
   r2.status_code == 422, r2.status_code)

print("TOTAL: %d FAILED: %d %s" % (TOTAL, len(FAILED), FAILED))
sys.exit(1 if FAILED else 0)
