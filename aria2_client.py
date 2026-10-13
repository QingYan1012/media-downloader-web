"""可选 aria2 JSON-RPC 后端：大文件 HTTP 分片加速，以及磁力/种子任务的增删查。"""
from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# 磁力/种子任务要回读的字段：一次 tellStatus 拿全，省得轮询里逐字段补刀
BT_KEYS = [
    "status", "totalLength", "completedLength", "downloadLength", "uploadLength",
    "speed", "uploadSpeed", "seedingTime", "numSeeders", "numPeers",
    "errorCode", "errorMessage", "followedBy", "bittorrent",
]


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
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            # aria2 的拒绝理由写在响应体里（例如种子文件坏掉时的「Bencode decoding failed」），
            # 只报「HTTP Error 400」等于把原因丢了，用户和我们都看不出是哪儿坏了。
            reason = ""
            try:
                err = json.loads(e.read().decode("utf-8", "replace")).get("error") or {}
                reason = str(err.get("message") or "")
            except Exception:
                pass
            raise RuntimeError("aria2 回 HTTP %s" % e.code + ("：" + reason if reason else "，且没有给出原因")) from None
        if "error" in data:
            raise RuntimeError(data["error"])
        return data.get("result")

    def ping(self, timeout: int = 5) -> bool:
        try:
            self._call("aria2.getVersion", timeout=timeout)
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
        extra_opts: Optional[dict] = None,
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
        # 磁力没有 HTTP 分片可言，extra_opts 里同名键要能覆盖上面这套默认值
        opts.update(extra_opts or {})
        return self._call("aria2.addUri", [list(urls), opts])

    def add_torrent(self, torrent_path: str, out_dir: str, urls: Optional[list] = None,
                    extra_opts: Optional[dict] = None) -> str:
        """本地 .torrent 文件走 aria2.addTorrent（文件内容 base64 上传）。"""
        raw = Path(torrent_path).read_bytes()
        opts = {"dir": out_dir, "auto-file-renaming": "false"}
        opts.update(extra_opts or {})
        return self._call("aria2.addTorrent", [base64.b64encode(raw).decode("ascii"), list(urls or []), opts])

    def tell_status(self, gid: str, keys: Optional[list] = None) -> dict:
        if keys:
            return self._call("aria2.tellStatus", [gid, keys]) or {}
        return self._call("aria2.tellStatus", [gid]) or {}

    def get_files(self, gid: str) -> list:
        """种子内文件清单：拿到元数据后才有内容，没元数据时是空表。"""
        res = self._call("aria2.getFiles", [gid]) or []
        return res if isinstance(res, list) else []

    def tell_active(self, keys: Optional[list] = None) -> list:
        res = self._call("aria2.tellActive", [keys or ["gid", "status", "totalLength", "completedLength"]]) or []
        return res if isinstance(res, list) else []

    def change_option(self, gid: str, opts: dict) -> bool:
        """下载中改选项：目前只用来做「只下勾选的那几个文件」（select-file + index）。"""
        try:
            return str(self._call("aria2.changeOption", [gid, opts])).strip().upper() == "OK"
        except Exception:
            return False

    def change_option_detail(self, gid: str, opts: dict) -> tuple:
        """同 change_option，但把 aria2 的原话留着。

        实测有两类坑：有的键它当场回「Cannot change option for GID#…」（bt-tracker），
        有的键它回 OK 却根本不改值（seed-ratio、check-integrity、bt-prioritize-piece）。
        所以调用方不能只看回话，必须 get_option 读回——这里先把拒绝的理由交出去。
        """
        try:
            r = self._call("aria2.changeOption", [gid, opts])
            return (str(r).strip().upper() == "OK", "" if str(r).strip().upper() == "OK" else str(r))
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def get_option(self, gid: str) -> dict:
        """读回某个任务当前真正生效的选项（限速、tracker 都在这儿，别信 RPC 的 OK）。"""
        try:
            return self._call("aria2.getOption", [gid]) or {}
        except Exception:
            return {}

    def remove(self, gid: str) -> None:
        try:
            self._call("aria2.forceRemove", [gid])
        except Exception:
            pass

    def force_shutdown(self) -> None:
        """只关我们自己拉起来的那个 aria2 守护进程。"""
        try:
            self._call("aria2.shutdown")
        except Exception:
            pass
