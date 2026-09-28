"""Telegram 用户会话（MTProto）：登录自己的账号，翻私有/受限频道的历史并把媒体下下来。

为什么匿名爬虫不够：t.me/s/ 只给公开频道的视频直链，文件和音频帖在匿名页上只有
文件名。私有频道（t.me/c/…）根本没有匿名页。这两类都要一个真实的用户会话。

「限制保存内容」这个标志是频道主人设的，我们不绕它：照样把它读出来（entity.noforwards）
标在界面上，取文件时如果 Telegram 返回 ChatForwardsRestricted，就原样把原因上屏并停手。

库选 Telethon：Pyrogram 上游停更过、且有仿冒包前科，这东西是要打进便携包给别人的。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from telegram_channel import (
    ALL_TYPES,
    AUDIO_EXT,
    TYPE_AUDIO,
    TYPE_DOCUMENT,
    TYPE_LABELS,
    TYPE_PHOTO,
    TYPE_VIDEO,
    TYPE_VOICE,
    MAX_LIMIT,
)

DEFAULT_BUDGET = 600
DEFAULT_LIMIT = 100
# 一次会话只跑一个下载：多个任务并发打同一批 DC 容易被判定 flood，队列那边自己排
MAX_FLOOD_WAIT = 300

NEED_TELETHON = "没装 Telethon：到「设置 → 组件与依赖」点 telethon 安装（会按镜像源回退）"
NEED_CRED = "还差 api_id / api_hash：到 my.telegram.org 用这个手机号申请，填到本页的凭据框里"
NEED_LOGIN = "这个会话还没登录账号：先填手机号点「发验证码」，再把收到的码填回来"
PROTECTED_NOTE = "频道开了「限制保存内容」：条目能列出，取文件时 Telegram 可能直接拒绝"

_TGMSG_RE = re.compile(
    r"^https?://t\.me/c/(\d+)/(\d+)(?:[/?#]\S*)?$",
    re.I,
)


def telethon_available() -> bool:
    try:
        import telethon  # noqa: F401

        return True
    except Exception:
        return False


def telethon_version() -> str:
    try:
        from importlib.metadata import version

        return version("telethon")
    except Exception:
        return ""


def human_size(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


def human_dur(sec) -> str:
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    if sec <= 0:
        return ""
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_tgmt(url: str) -> Optional[dict]:
    # 公开的 t.me/<name>/<id> 返回 None：那条路走 yt-dlp，别抢匿名能下的活
    u = (url or "").strip()
    m = re.match(r"^tgmt://([^/?#]+)/(\d+)(?:\?(?:idx|media)=(\d+))?$", u, re.I)
    if m:
        return {"chat": m.group(1), "msg": int(m.group(2)), "idx": int(m.group(3) or 0)}
    m = _TGMSG_RE.match(u)
    if m:
        return {"chat": "-100" + m.group(1), "msg": int(m.group(2)), "idx": 0}
    return None


def tgmt_url(chat, msg, idx: int = 0) -> str:
    u = f"tgmt://{chat}/{int(msg)}"
    return f"{u}?idx={idx}" if idx else u


def normalize_entity(s: str) -> str:
    """用户粘什么都行（@name / t.me/name / t.me/s/name / t.me/c/… / -100…）→ get_entity 能吃的形式。"""
    t = str(s or "").strip().rstrip("/")
    if not t:
        return ""
    m = re.match(r"^(?:https?://)?(?:www\.)?t\.me/c/(\d+)(?:/\d+)?/?$", t, re.I)
    if m:
        return "-100" + m.group(1)
    m = re.match(r"^(?:https?://)?(?:www\.)?t\.me/(?:s/)?([^/?#]+)", t, re.I)
    if m:
        t = m.group(1)
    t = t.lstrip("@").strip()
    if re.fullmatch(r"-?\d+", t):
        return t if t.startswith("-100") else t
    if not re.fullmatch(r"[A-Za-z][\w]{3,31}", t):
        return ""
    return t


def _media_kind(msg) -> Tuple[str, object]:
    """一条消息里的主媒体是什么类型（语音/小视频都归到能落地的桶）。"""
    if getattr(msg, "voice", None):
        return TYPE_VOICE, msg.voice
    if getattr(msg, "video_note", None):
        return TYPE_VIDEO, msg.video_note
    if getattr(msg, "video", None):
        return TYPE_VIDEO, msg.video
    if getattr(msg, "audio", None):
        return TYPE_AUDIO, msg.audio
    if getattr(msg, "photo", None):
        return TYPE_PHOTO, msg.photo
    if getattr(msg, "file", None):
        doc = msg.file
        name = (getattr(doc, "name", "") or "").lower()
        mime = (getattr(doc, "mime_type", "") or "").lower()
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        if ext in AUDIO_EXT or mime.startswith("audio/"):
            return TYPE_AUDIO, doc
        return TYPE_DOCUMENT, doc
    return "", None


def _media_name(msg, media, kind: str) -> str:
    for attr in (getattr(media, "attributes", None) or []):
        name = getattr(attr, "file_name", None)
        if name:
            return str(name)
    if getattr(media, "title", None):
        return str(media.title)
    if kind == TYPE_PHOTO:
        return f"photo-{msg.id}.jpg"
    mime = (getattr(media, "mime_type", "") or "").lower()
    ext = {"video/mp4": ".mp4", "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
           "audio/mp4": ".m4a", "video/ogg": ".ogv"}.get(mime, "")
    text = (msg.text or "").strip().splitlines()
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", (text[0] if text else "")).strip()[:60]
    return f"{base or kind}-{msg.id}{ext or ('.mp4' if kind == TYPE_VIDEO else '.bin')}"


def _post_link(info: dict, msg_id: int) -> str:
    """能给出人话链接就给（@name / t.me/username），私有频道只能给 t.me/c/<内部id>/<msg>。"""
    if info.get("username"):
        return f"https://t.me/{info['username']}/{msg_id}"
    peer = str(info.get("peer") or "")
    inner = peer[4:] if peer.startswith("-100") else peer.lstrip("-")
    return f"https://t.me/c/{inner}/{msg_id}" if inner else ""


def _row(info: dict, msg, kind: str, media, idx: int) -> dict:
    dur = getattr(media, "duration", 0) or getattr(msg, "file_duration", 0)
    name = _media_name(msg, media, kind)
    peer = info.get("peer") or getattr(msg, "chat_id", "") or info.get("title", "")
    noforwards = bool(info.get("noforwards"))
    return {
        "id": f"{peer}-{msg.id}-{idx}",
        "channel": info.get("title", ""),
        "peer": str(peer),
        "post_id": msg.id,
        "media_index": idx,
        "url": _post_link(info, msg.id),
        # 用户名能现解，裸 id 要靠会话缓存；所以能带名字就带名字
        "mt_url": tgmt_url(info.get("username") or peer, msg.id, idx),
        "date": msg.date.strftime("%Y-%m-%d") if msg.date else "",
        "datetime": msg.date.isoformat() if msg.date else "",
        "text": (msg.text or "")[:200],
        "type": kind,
        "title": name if kind in (TYPE_DOCUMENT, TYPE_AUDIO) else ((msg.text or "").strip()[:120] or name),
        "duration": human_dur(dur),
        "duration_sec": int(dur or 0),
        "filename": name,
        "size_text": human_size(getattr(media, "size", None) or getattr(media, "file_size", None)),
        "thumb": "",
        "direct_url": "",
        # 会话读得到的东西就能取；noforwards 只影响 Telegram 肯不肯给，见 note
        "downloadable": True,
        "note": PROTECTED_NOTE if noforwards else "",
        "protected": bool(noforwards),
    }


class MediaIndex:
    """下过的东西记一笔，重复扫到就跳过 —— 键用 (chat, msg, media序号, 大小)。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data: Dict[str, dict] = {}
        try:
            if self.path.is_file():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.data = {str(k): v for k, v in raw.items()}
        except Exception:
            self.data = {}

    @staticmethod
    def key(chat, msg, idx, size=0) -> str:
        return f"{chat}:{msg}:{idx}:{size or 0}"

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            return self.data.get(key)

    def seen(self, chat, msg, idx, size=0) -> str:
        rec = self.get(self.key(chat, msg, idx, size)) or {}
        p = str(rec.get("path") or "")
        return p if p and Path(p).is_file() else ""

    def mark(self, chat, msg, idx, size, path: str, title: str = "") -> None:
        with self._lock:
            self.data[self.key(chat, msg, idx, size)] = {
                "path": str(path),
                "title": title,
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8"
                )
            except Exception:
                pass


class TelegramSession:
    """一个长驻事件循环 + 一个 TelegramClient：登录跨多次 HTTP 请求，客户端不能重建。"""

    def __init__(self, cfg_get: Callable[[], dict], log: Callable = print,
                 session_dir: Path = None, index_path: Path = None):
        self.cfg_get = cfg_get
        self.log = log
        self.session_dir = Path(session_dir) if session_dir else Path(".")
        self.index = MediaIndex(index_path) if index_path else None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._client = None
        self._lock = threading.RLock()
        self._pending_hash = ""
        self._pending_phone = ""

    # ---------------------------------------------------------- 基础设施
    def _ensure_loop(self):
        if self._loop and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, name="tg-mt-loop", daemon=True
        )
        self._loop_thread.start()

    def _run(self, coro, timeout: int = 120):
        self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _proxy(self):
        """tgmt_proxy 填 '127.0.0.1:7897' 这种 SOCKS5 地址；留空 = 直连（Python 不读注册表代理）。"""
        raw = str(self.cfg_get().get("tgmt_proxy") or "").strip()
        if not raw:
            return None
        m = re.match(r"^(?:socks5://|socks5h://)?([^:/]+):(\d+)$", raw)
        if not m:
            raise ValueError("tgmt_proxy 要么留空，要么写成 socks5 的 host:port")
        return (m.group(1), int(m.group(2)))

    async def _build_client(self):
        from telethon import TelegramClient

        cfg = self.cfg_get()
        api_id = int(str(cfg.get("tgmt_api_id") or "0").strip() or 0)
        api_hash = str(cfg.get("tgmt_api_hash") or "").strip()
        if not api_id or not api_hash:
            raise RuntimeError(NEED_CRED)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        name = str(cfg.get("tgmt_session_name") or "media_downloader").strip() or "media_downloader"
        name = re.sub(r"[^\w.-]", "_", name)
        return TelegramClient(
            str(self.session_dir / name), api_id, api_hash,
            proxy=self._proxy(), connection_retries=2, request_timeout=30,
        )

    async def _get_client(self):
        if self._client is None:
            self._client = await self._build_client()
        if not self._client.is_connected():
            await self._client.connect()
        return self._client

    async def _disconnect(self):
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _reset_client(self):
        try:
            self._run(self._disconnect(), timeout=15)
        except Exception:
            self._client = None

    # ---------------------------------------------------------- 登录
    def status(self) -> dict:
        cfg = self.cfg_get()
        out = {
            "installed": telethon_available(),
            "version": telethon_version(),
            "configured": bool(cfg.get("tgmt_api_id") and cfg.get("tgmt_api_hash")),
            "session_dir": str(self.session_dir),
            "session_files": [],
            "logged_in": False,
            "user": None,
            "needs_code": bool(self._pending_phone),
            "proxy": str(cfg.get("tgmt_proxy") or ""),
        }
        try:
            out["session_files"] = sorted(
                p.name for p in self.session_dir.glob("*.session")
            ) if self.session_dir.is_dir() else []
        except Exception:
            pass
        if not (out["installed"] and out["configured"]):
            return out
        try:
            u = self._run(self._whoami(), timeout=25)
            if u:
                out["logged_in"] = True
                out["user"] = u
        except Exception:
            pass
        return out

    async def _whoami(self):
        c = await self._get_client()
        if not await c.is_user_authorized():
            return None
        return _user_dict(await c.get_me())

    def send_code(self, phone: str) -> dict:
        phone = re.sub(r"[^+\d]", "", phone or "")
        if len(phone) < 6:
            raise ValueError("手机号得带国家码，例如 +8613800000000")
        self._reset_client()
        self._pending_phone = phone
        self._pending_hash = ""
        try:
            res = self._run(self._send_code(), timeout=90)
        except Exception as e:
            self._pending_phone = ""
            raise RuntimeError(_login_err_cn(e)) from e
        self._pending_hash = res.get("phone_code_hash") or ""
        return {"ok": True, "phone": phone, "is_email": res.get("is_email", False),
                "length": res.get("length", 5), "hint": "码发到手机上的 Telegram 客户端，不是短信"}

    async def _send_code(self):
        c = await self._get_client()
        sc = await c.send_code_request(self._pending_phone)
        return {"phone_code_hash": getattr(sc, "phone_code_hash", "") or "",
                "is_email": bool(getattr(sc, "type", None) and
                                 getattr(sc.type, "EMAIL", False)),
                "length": getattr(sc, "length", 5) or 5}

    def sign_in(self, code: str, password: str = "") -> dict:
        if not self._pending_phone:
            raise RuntimeError("没有待确认的验证码：先点「发验证码」")
        try:
            user = self._run(self._sign_in(code, password), timeout=90)
        except Exception as e:
            if "password" in type(e).__name__.lower() or "password" in str(e).lower():
                return {"ok": False, "needs_password": True,
                        "message": "这个账号开了两步验证：再填一次云密码"}
            raise RuntimeError(_login_err_cn(e)) from e
        self._pending_phone = ""
        self._pending_hash = ""
        self.log(f"Telegram 会话已登录：{user.get('name') or user.get('username') or user.get('id')}")
        return {"ok": True, "user": user}

    async def _sign_in(self, code: str, password: str = ""):
        c = await self._get_client()
        kw = {"phone": self._pending_phone, "code": str(code or "").strip(),
              "phone_code_hash": self._pending_hash}
        if password:
            kw["password"] = password
        return _user_dict(await c.sign_in(**kw))

    def reconnect(self) -> None:
        """凭据/代理改了：丢连接、留 session 文件，下次调用会按新配置重建客户端。"""
        self._reset_client()

    def logout(self) -> dict:
        self._reset_client()
        removed = []
        try:
            for p in self.session_dir.glob("*"):
                if p.suffix in (".session", ".session-journal") and p.is_file():
                    p.unlink()
                    removed.append(p.name)
        except Exception as e:
            return {"ok": False, "message": f"会话文件没删干净：{e}", "removed": removed}
        self.log("已退出 Telegram 会话并删除本地 session 文件")
        return {"ok": True, "removed": removed}

    # ---------------------------------------------------------- 列历史
    def probe(self, entity: str) -> dict:
        return self._run(self._probe(entity), timeout=90)

    async def _probe(self, entity: str):
        c = await self._get_client()
        e = await c.get_entity(entity)
        return _entity_info(e)

    def list_media(self, entity: str, *, limit: int = DEFAULT_LIMIT,
                   types: Optional[List[str]] = None, since: str = "", until: str = "",
                   budget: int = DEFAULT_BUDGET, search: str = "",
                   skip_seen: bool = False) -> Tuple[List[dict], dict]:
        return self._run(
            self._list_media(entity, limit=limit, types=types, since=since,
                             until=until, budget=budget, search=search,
                             skip_seen=skip_seen),
            timeout=budget + 120,
        )

    async def _list_media(self, entity: str, **kw):
        from telethon import errors

        types = [t for t in (kw.get("types") or []) if t in ALL_TYPES] or [TYPE_VIDEO]
        limit = max(1, min(int(kw.get("limit") or DEFAULT_LIMIT), MAX_LIMIT))
        budget = max(15, min(int(kw.get("budget") or DEFAULT_BUDGET), 3600))
        since = _parse_date(kw.get("since") or "")
        until = _parse_date(kw.get("until") or "")
        t0 = time.monotonic()
        items: List[dict] = []
        diag = {"mode": "mt", "entity": entity, "scanned": 0, "matched": 0,
                "skipped_seen": 0, "stopped": "", "errors": {}, "budget": budget,
                "elapsed": 0.0, "pages": 0}
        try:
            c = await self._get_client()
            ent = await c.get_entity(entity)
        except errors.AuthKeyUnregisteredError as e:
            diag["stopped"] = "会话失效，要重新登录"
            diag["errors"]["登录"] = str(e)
            return items, diag
        except Exception as e:
            diag["stopped"] = _lookup_err_cn(e)
            diag["errors"]["找频道"] = str(e)
            self.log(f"Telegram 会话翻历史失败：{diag['stopped']}", "warning")
            return items, diag

        info = _entity_info(ent)
        diag.update({"title": info["title"], "noforwards": info["noforwards"],
                     "peer": info["peer"], "is_channel": info["is_channel"]})
        kw_iter = {"limit": None, "search": (kw.get("search") or None)}
        if until:
            # iter_messages 从新往旧翻，offset_date 让它从窗口末尾开始而不是从最新一条
            kw_iter["offset_date"] = until
        scanned = 0
        try:
            async for msg in c.iter_messages(ent, **kw_iter):
                if time.monotonic() - t0 > budget:
                    diag["stopped"] = f"{budget}s 预算用完，先把条数上限调小或预算调大"
                    break
                scanned += 1
                if msg.date and since and msg.date < since:
                    diag["stopped"] = f"已翻到 {since:%Y-%m-%d} 之前，按日期收工"
                    break
                if msg.date and until and msg.date > until:
                    continue
                kinds = _msg_medias(msg)
                for idx, (kind, media) in enumerate(kinds):
                    if kind not in types:
                        continue
                    if kw.get("skip_seen") and self.index:
                        size = int(getattr(media, "size", 0) or
                                   getattr(media, "file_size", 0) or 0)
                        if self.index.seen(info["peer"], msg.id, idx, size):
                            diag["skipped_seen"] += 1
                            continue
                    items.append(_row(info, msg, kind, media, idx))
                    if len(items) >= limit:
                        break
                diag["matched"] = len(items)
                if len(items) >= limit:
                    diag["stopped"] = f"已到数量上限 {limit} 条"
                    break
                if scanned % 300 == 0:
                    diag["pages"] += 1
                    await asyncio.sleep(0.2)  # 别把历史翻成 DDOS
        except errors.FloodWaitError as e:
            diag["stopped"] = f"被限流，要等 {getattr(e, 'seconds', 0)}s 再翻"
            diag["errors"]["限流"] = str(e)
        except errors.ChannelPrivateError as e:
            diag["stopped"] = "私有频道：这个账号没加入它（或被踢了），读不到历史"
            diag["errors"]["读不到"] = str(e)
        except Exception as e:
            diag["stopped"] = _lookup_err_cn(e)
            diag["errors"]["中断"] = str(e)

        diag["scanned"] = scanned
        diag["elapsed"] = round(time.monotonic() - t0, 1)
        if not diag["stopped"]:
            diag["stopped"] = "已翻到最早一条" if scanned else "该账号在这频道没读到任何消息"
        self.log(
            f"Telegram 会话翻历史: {info['title'] or entity} 扫 {scanned} 条消息 → "
            f"{len(items)} 条 · {diag['elapsed']}s ｜ {diag['stopped']}"
            + (f"（跳过已下 {diag['skipped_seen']}）" if diag.get("skipped_seen") else "")
        )
        return items, diag

    # ---------------------------------------------------------- 下载
    def download(self, chat, msg_id: int, idx: int, out_dir: str, *,
                 audio_only: bool = False, filename_template: str = "",
                 progress: Optional[Callable[[float, int, str], None]] = None,
                 stopped: Optional[Callable[[], bool]] = None,
                 force: bool = False) -> Tuple[bool, str, str]:
        try:
            return self._run(
                self._download(chat, msg_id, idx, out_dir, audio_only=audio_only,
                               filename_template=filename_template, progress=progress,
                               stopped=stopped, force=force),
                timeout=3600 * 6,
            )
        except Exception as e:
            return False, "", _download_err_cn(e)

    async def _download(self, chat, msg_id: int, idx: int, out_dir: str, **kw):
        from telethon import errors

        c = await self._get_client()
        try:
            target = _chat_ref(chat)
            msgs = await c.get_messages(target, ids=[int(msg_id)])
        except Exception as e:
            return False, "", _lookup_err_cn(e)
        msg = msgs[0] if msgs else None
        if not msg:
            return False, "", "这条消息不存在，或这个账号看不到它"
        kinds = _msg_medias(msg)
        if not kinds:
            return False, "", "这条消息没有媒体附件"
        if idx >= len(kinds):
            idx = 0
        kind, media = kinds[idx]
        peer = _peer_of(msg)
        size = int(getattr(media, "size", 0) or getattr(media, "file_size", 0) or 0)
        if self.index and not kw.get("force"):
            old = self.index.seen(peer, int(msg_id), idx, size)
            if old:
                return True, old, "此前已下过（命中下载记录），要重下请关掉「跳过已下载」"

        out_dir = Path(kw.get("out_dir") or ".")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return False, "", f"下载目录建不出来：{e}"
        name = _safe_name(kw.get("filename_template"), msg, media, kind, size)
        stopped = kw.get("stopped")
        cb = kw.get("progress")
        last = {"pct": -1.0, "t": 0.0}

        def _on_progress(done, todo):
            if stopped and stopped():
                raise _Stopped()
            now = time.monotonic()
            if now - last["t"] < 0.4 or not todo:
                return
            last["t"] = now
            pct = round(done * 100.0 / todo, 1)
            if pct == last["pct"]:
                return
            last["pct"] = pct
            if cb:
                try:
                    cb(pct, int(done), f"{human_size(done)} / {human_size(todo)}")
                except Exception:
                    pass

        tmp = out_dir / f".{name}.part"

        async def _refetch_media():
            """重取一次消息：Telegram 的 file reference 会过期，老引用再下载必失败。"""
            try:
                fresh = (await c.get_messages(target, ids=[int(msg_id)])) or [None]
                kinds = _msg_medias(fresh[0]) if fresh[0] else []
                return kinds[idx][1] if idx < len(kinds) else None
            except Exception:
                return None

        cur_media, err, final = media, "", None
        for attempt in range(3):
            if stopped and stopped():
                _unlink(tmp)
                return False, "", "已停止"
            try:
                got = await c.download_media(cur_media, file=str(tmp),
                                             progress_callback=_on_progress)
                final = Path(got or tmp)
                err = ""
                break
            except _Stopped:
                _unlink(tmp)
                return False, "", "已停止"
            except errors.FloodWaitError as e:
                wait = int(getattr(e, "seconds", 0) or 0)
                _unlink(tmp)
                if wait > MAX_FLOOD_WAIT:
                    return False, "", f"被限流要等 {wait}s（超过 {MAX_FLOOD_WAIT}s 上限），稍后再试"
                self.log(f"被限流，等 {wait}s 再取（第 {attempt + 1} 次）", "warning")
                err = _download_err_cn(e)
                await asyncio.sleep(wait + 1)
            except errors.ChatForwardsRestrictedError as e:
                _unlink(tmp)
                return False, "", (
                    "频道开了「限制保存内容」，Telegram 拒绝把这个文件交给会话 —— "
                    f"这是频道主人的设置，本工具不绕它（{type(e).__name__}）"
                )
            except Exception as e:
                _unlink(tmp)
                err = _download_err_cn(e)
                if "文件引用过期" not in err:
                    return False, "", err
            fresh = await _refetch_media()
            if fresh is None:
                return False, "", err or "消息已经取不到了（被删 / 账号看不到）"
            cur_media = fresh

        if final is None or not final.is_file():
            _unlink(tmp)
            return False, "", err or "下载没产出文件（会话断开 / 消息被删 / 磁盘路径不可写）"

        # 站点声明的大小和成品对不上 = 没下完，不能报成功
        got_size = final.stat().st_size
        if size and got_size + 4096 < size:
            _unlink(final)
            return False, "", (
                f"成品只有 {human_size(got_size)}，站点声明 {human_size(size)}：判定为没下完"
            )

        dst = out_dir / name
        if final != dst:
            try:
                os.replace(final, dst)
            except OSError as e:
                return False, "", f"下载完但落不回正式文件名：{e}"
        note = ""
        final = dst
        if kw.get("audio_only"):
            ok2, path_or_err = _extract_audio(final, self.log)
            if ok2:
                final = Path(path_or_err)
            else:
                # 文件是完整的，只是抽轨没成 —— 报成功并把缺憾写在提示里，不谎称失败
                note = path_or_err

        if self.index:
            self.index.mark(peer, int(msg_id), idx, size, str(final),
                            (msg.text or "")[:120])
        return True, str(final), note

    def download_ref(self, url: str, out_dir: str, **kw) -> Tuple[bool, str, str]:
        ref = parse_tgmt(url)
        if not ref:
            return False, "", f"不是 Telegram 会话链：{url[:60]}"
        return self.download(ref["chat"], ref["msg"], ref["idx"], out_dir, **kw)


# --------------------------------------------------------------- 纯函数helpers
def _entity_info(e) -> dict:
    peer = ""
    try:
        from telethon.utils import get_peer_id

        peer = str(get_peer_id(e))
    except Exception:
        peer = str(getattr(e, "id", "") or "")
    return {
        "peer": peer or str(getattr(e, "id", "") or ""),
        "id": getattr(e, "id", 0),
        "title": getattr(e, "title", None) or getattr(e, "username", None) or "",
        "username": getattr(e, "username", "") or "",
        "noforwards": bool(getattr(e, "noforwards", False)),
        "is_channel": bool(getattr(e, "broadcast", False)),
        "is_group": bool(getattr(e, "megagroup", False) or getattr(e, "gigagroup", False)),
        "is_private": bool(getattr(e, "megagroup", False) or getattr(e, "gigagroup", False)
                           or (not getattr(e, "broadcast", True) and not getattr(e, "username", ""))),
        "count": getattr(e, "participants_count", 0) or 0,
    }


def _user_dict(u) -> dict:
    return {
        "id": getattr(u, "id", 0),
        "name": " ".join(x for x in (getattr(u, "first_name", ""),
                                     getattr(u, "last_name", "")) if x),
        "username": getattr(u, "username", "") or "",
        "phone": getattr(u, "phone", "") or "",
    }


def _msg_medias(msg) -> List[Tuple[str, object]]:
    """一条帖可能带多个媒体（相册），逐个出，顺序稳定，idx 就是它在列表里的位置。"""
    media = getattr(msg, "media", None)
    if media is None:
        return []
    kind, m = _media_kind(msg)
    return [(kind or TYPE_DOCUMENT, m or media)]


def _peer_of(msg) -> str:
    cid = getattr(msg, "chat_id", None)
    if cid:
        return str(cid)
    return str(getattr(getattr(msg, "to_id", None), "chat_id", "") or "")


def _chat_ref(chat: str):
    """tgmt:// 里的 chat 段：数字（可能是 -100… 或对端 id）、@name、或 t.me 用户名。"""
    s = str(chat or "").strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def _parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


_TPL_TOKENS = {"title": "{title}", "id": "{msg}", "ext": "{ext}", "upload_date": "{date}",
               "type": "{type}", "filename": "{filename}"}


def _norm_template(tpl: str) -> str:
    """全局「文件命名模板」存的是 yt-dlp 那套 %(title).60B —— 这里两种写法都认。"""
    def sub(m):
        return _TPL_TOKENS.get(m.group(1).lower(), "")
    return re.sub(r"%\((\w+)\)(?:\.\d+[a-zA-Z]{1,2}|[a-zA-Z])?", sub, tpl)


def _safe_name(template: str, msg, media, kind: str, size: int) -> str:
    name = _norm_template((template or "").strip())
    text = (msg.text or "").strip().replace("\n", " ")
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", text)[:60].strip()
    fname = _media_name(msg, media, kind)
    ext = Path(fname).suffix.lstrip(".") or ("mp4" if kind == TYPE_VIDEO else "bin")
    if name:
        name = (name.replace("{date}", msg.date.strftime("%Y-%m-%d") if msg.date else "")
                    .replace("{msg}", str(msg.id))
                    .replace("{type}", kind)
                    .replace("{ext}", ext)
                    .replace("{title}", title or fname)
                    .replace("{filename}", fname))
    else:
        date = msg.date.strftime("%Y-%m-%d") if msg.date else ""
        name = f"{date} {title or fname}".strip()
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or f"tg-{msg.id}"
    if Path(name).suffix:
        return name[:150]
    return f"{name[:150]}.{ext}"


class _Stopped(Exception):
    """从进度回调里抛出来中断 download_media —— 它每分片调一次，停止因此能在一两秒内生效。"""


def _unlink(p: Path):
    try:
        if Path(p).is_file():
            Path(p).unlink()
    except Exception:
        pass


def _extract_audio(path: Path, log: Callable):
    """只下音频时抽轨；抽不动（容器/编码不合）就如实报，不假装成功。"""
    import subprocess

    dst = path.with_suffix(".m4a")
    for args in (["-c", "copy"], ["-c:a", "aac", "-b:a", "192k"]):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
               "-vn", *args, str(dst)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except FileNotFoundError:
            return False, "没找到 ffmpeg，抽不了音轨：成品保持原样（含画面）"
        except Exception as e:
            return False, f"抽音轨失败：{e}"
        if r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0:
            _unlink(path)
            log(f"仅音频：{path.name} → {dst.name}")
            return True, str(dst)
    _unlink(dst)
    return False, "ffmpeg 抽音轨失败（编码不支持？）：成品保持原样（含画面）"


def _login_err_cn(e: Exception) -> str:
    name = type(e).__name__
    s = str(e)
    table = [
        ("PhoneNumberInvalid", "手机号格式不被接受：要带国家码，例如 +8613800000000"),
        ("PhoneNumberBanned", "这个号被 Telegram 封禁，登录不了"),
        ("PhoneCodeInvalid", "验证码不对或已过期：重新点「发验证码」再填一次"),
        ("PhoneCodeExpired", "验证码过期了，重新发一次"),
        ("SessionPasswordNeeded", "这个账号开了两步验证"),
        ("TwoFaCodeInvalid", "两步验证的云密码不对"),
        ("AuthKeyUnregistered", "会话已失效，要重新登录"),
        ("SessionRevoked", "这个会话被吊销了，重新登录"),
        ("ApiIdInvalid", "api_id / api_hash 不配对：核对 my.telegram.org 里的值"),
        ("ApiKeyInvalid", "api_id / api_hash 不配对：核对 my.telegram.org 里的值"),
        ("AuthRestartRequired", "需要重连：再点一次「发验证码」"),
        ("Flood", "请求太频繁，等一两分钟再发验证码"),
    ]
    for key, cn in table:
        if key.lower() in name.lower() or key.lower() in s.lower():
            return f"{cn}（{s}）" if s else cn
    return f"登录失败：{s or name}"


def _lookup_err_cn(e: Exception) -> str:
    name = type(e).__name__
    s = str(e)
    table = [
        ("UsernameNotOccupied", "频道名/链接找不到对应的公开频道"),
        ("PeerIdInvalid", "这个 id 解析不出来：私有频道要先进过、且用 t.me/c/… 或数字 id"),
        ("InviteHashExpired", "邀请链接过期了"),
        ("UsernameInvalid", "频道链接格式不对"),
        ("ChannelPrivate", "私有频道：这个账号没加入它，或被踢了"),
        ("ChannelInvalid", "频道 id 不对，或这个账号看不到它"),
        ("AuthKeyUnregistered", "会话失效，要重新登录"),
        ("SessionExpired", "会话过期，要重新登录"),
        ("Flood", "被限流，稍后再翻"),
        ("TimedOut", "连不上 Telegram（代理没配 / 直连被墙）：在设置里填 SOCKS5 代理再试"),
        ("Connect", "连不上 Telegram：多半是要在「tg 代理」里填 SOCKS5 地址"),
    ]
    for key, cn in table:
        if key.lower() in name.lower() or key.lower() in s.lower():
            return f"{cn}（{s}）" if s else cn
    return f"读取失败：{s or name}"


def _download_err_cn(e: Exception) -> str:
    name = type(e).__name__
    s = str(e)
    table = [
        ("ChatForwardsRestricted", "频道开了「限制保存内容」，Telegram 拒绝交付文件（这是频道主人的设置，本工具不绕它）"),
        ("FileReferenceExpired", "文件引用过期：重新列一次历史再下"),
        ("MessageIdInvalid", "消息号无效，或这个账号看不到这条消息"),
        ("AuthKeyUnregistered", "会话失效，要重新登录"),
        ("Flood", "被限流，稍后再下"),
        ("Timeout", "下载中断（超时）：可以重试这条"),
    ]
    for key, cn in table:
        if key.lower() in name.lower() or key.lower() in s.lower():
            return f"{cn}（{s}）" if s else cn
    return f"下载失败：{s or name}"


__all__ = [
    "ALL_TYPES", "TYPE_LABELS", "MediaIndex", "TelegramSession", "telethon_available",
    "telethon_version", "parse_tgmt", "tgmt_url", "normalize_entity", "human_size", "human_dur",
    "NEED_TELETHON", "NEED_CRED", "NEED_LOGIN", "PROTECTED_NOTE",
]
