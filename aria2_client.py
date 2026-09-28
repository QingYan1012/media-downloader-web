"""可选 aria2 JSON-RPC 后端：大文件 HTTP 分片加速。"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional
from urllib.request import Request, urlopen


class Aria2Client:
    def __init__(self, rpc_url: str = "http://127.0.0.1:6800/jsonrpc", secret: str = ""):
        self.rpc_url = (rpc_url or "").rstrip("/")
        self.secret = secret or ""

    def _call(self, method: str, params: list = None, timeout: int = 15) -> Any:
        params = list(params or [])
        if self.secret:
            params = [f"token:{self.secret}"] + params
        body = json.dumps(
            {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}
        ).encode("utf-8")
        req = Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "error" in data:
            raise RuntimeError(data["error"])
        return data.get("result")

    def ping(self) -> bool:
        try:
            self._call("aria2.getVersion")
            return True
        except Exception:
            return False

    def add_uri(
        self,
        urls: list,
        out_dir: str,
        filename: str = "",
        headers: Optional[list] = None,
        split: int = 8,
        max_conn: int = 8,
    ) -> str:
        opts = {
            "dir": out_dir,
            "split": str(split),
            "max-connection-per-server": str(max_conn),
            "continue": "true",
            "auto-file-renaming": "false",
        }
        if filename:
            opts["out"] = filename
        if headers:
            opts["header"] = headers
        return self._call("aria2.addUri", [list(urls), opts])

    def tell_status(self, gid: str) -> dict:
        return self._call("aria2.tellStatus", [gid]) or {}

    def remove(self, gid: str) -> None:
        try:
            self._call("aria2.forceRemove", [gid])
        except Exception:
            pass
