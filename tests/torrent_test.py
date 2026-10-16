#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""磁力 / 种子（aria2 后端 + 做种看护）离线自检。

只写 %TEMP%，不碰真实下载目录、config.json 与真实队列；aria2 全部用假客户端顶替。
跑法：PYTHONIOENCODING=utf-8 python tests/torrent_test.py
"""
import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

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
    def __init__(self, data):
        self.data = data

    def save(self):
        raise AssertionError("磁力/种子自检不该写 config.json")


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info"):
        self.rows.append((level, str(msg)))


class Clock:
    """假钟：sleep 就把时间往前推，让「等元数据超时」这种分支秒过。"""

    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, s):
        try:
            self.t += max(0.0, float(s))
        except (TypeError, ValueError):
            pass


TMP = Path(tempfile.mkdtemp(prefix="md_torrent_"))
DL = TMP / "downloads"
DL.mkdir(parents=True)

_REAL = (S.cfg, S.log_mgr, S.queue.log, S._bt_client, S.bt_ensure, S.time)
LOGS = FakeLog()
S.cfg = FakeCfg({"download_dir": str(DL)})
S.log_mgr = LOGS
S.queue.log = LOGS
# 让「等元数据超时」的等待在假钟里秒过：假钟每次 sleep 按秒推进

MAGNET40 = ("magnet:?xt=urn:btih:" + "a" * 40 +
            "&dn=%E6%BC%94%E7%A4%BA%E7%89%87&tr=udp%3A%2F%2Ftracker.example%3A1337")
MAGNET32 = "magnet:?xt=urn:btih:" + "k" * 31 + "4" + "&tr=http%3A%2F%2Ft2%2Fannounce"
MAGNET_BAD = "magnet:?xt=urn:btcd:deadbeef&dn=x"

# ---------- A. 认得出磁力 / 种子吗 ----------
r40 = S.parse_torrent_ref(MAGNET40)
ck("A1 磁力（40 位十六进制）识别", bool(r40) and r40["kind"] == "magnet" and r40["info_hash"] == "a" * 40,
   str(r40))
ck("A2 磁力的 dn 解出中文名", bool(r40) and r40["name"] == "演示片", (r40 or {}).get("name"))
r32 = S.parse_torrent_ref(MAGNET32)
ck("A3 磁力（32 位 base32）识别", bool(r32) and r32["info_hash"] == ("k" * 31 + "4").lower(), str(r32))
ck("A4 没有 xt=urn:btih 的磁力不收", S.parse_torrent_ref(MAGNET_BAD) is None)
ck("A5 报错点名缺了哪一段", "xt=urn:btih" in S.torrent_reject_reason(MAGNET_BAD),
   S.torrent_reject_reason(MAGNET_BAD))
ck("A6 普通网页链接不算磁力", S.parse_torrent_ref("https://example.com/v.mp4") is None)
ck("A7 网上的 .torrent 链接走普通下载", S.parse_torrent_ref("https://example.com/a.torrent") is None)

tp = TMP / "种子 一号.torrent"
tp.write_bytes(b"d8:announce")
rf = S.parse_torrent_ref(str(tp))
ck("A8 本地种子路径识别", bool(rf) and rf["kind"] == "torrent-file" and Path(rf["path"]).name == "种子 一号.torrent",
   str(rf))
ru = S.parse_torrent_ref(tp.as_uri())
ck("A9 file:// 也认，且与直接写路径同一条内容", bool(ru) and ru["path"] == rf["path"], str(ru))
ck("A10 file:// 指向非种子要拒，且说清只认 .torrent",
   S.parse_torrent_ref((TMP / "x.txt").as_uri()) is None
   and ".torrent" in S.torrent_reject_reason((TMP / "x.txt").as_uri()),
   S.torrent_reject_reason((TMP / "x.txt").as_uri()))

# ---------- B. 归一化与去重 ----------
ck("B1 磁力的 tr=/dn= 不会被参数清洗删掉", S.normalize_url(MAGNET40) == MAGNET40)
m_same = ("magnet:?xt=urn:btih:" + "a" * 40 + "&tr=udp%3A%2F%2Fother%3A6969&dn=%E5%88%AB%E5%90%8D&xl=100")
ck("B2 同一 hash 换 tracker/名字 = 同一条任务", S.url_dedup_key(MAGNET40) == S.url_dedup_key(m_same),
   S.url_dedup_key(MAGNET40))
ck("B3 不同 hash 是两条", S.url_dedup_key(MAGNET40) != S.url_dedup_key(MAGNET32))
ck("B4 同一个种子文件按路径去重", S.url_dedup_key(str(tp)) == S.url_dedup_key(ru["path"]))


def _benc(o):
    if isinstance(o, int):
        return b"i%de" % o
    if isinstance(o, bytes):
        return b"%d:%s" % (len(o), o)
    if isinstance(o, str):
        return _benc(o.encode("utf-8"))
    if isinstance(o, list):
        return b"l" + b"".join(_benc(x) for x in o) + b"e"
    if isinstance(o, dict):
        return b"d" + b"".join(_benc(k) + _benc(v) for k, v in sorted(o.items())) + b"e"
    raise TypeError(type(o))


# pieces 那种二进制段里全是 d/e，还塞了个假 4:info：靠搜关键字或数字符都会切错段
_INFO = {"name": "同一个内容.mp4", "length": 123, "piece length": 32768,
         "pieces": b"\x00de4:info" + b"edl" * 20}
_TOR_A = _benc({"announce": b"http://t1/ann", "comment": b"decoy 4:info here", "info": _INFO})
_TOR_B = _benc({"announce": "http://t2/ann", "creation date": 1700000000, "info": _INFO})
_TOR_C = _benc({"announce": "http://t1/ann", "info": dict(_INFO, name="换个内容.mp4")})
_IH = hashlib.sha1(_benc(_INFO)).hexdigest()
for _n, _body in (("a.torrent", _TOR_A), ("b.torrent", _TOR_B), ("c.torrent", _TOR_C)):
    (TMP / _n).write_bytes(_body)
ck("B5 info 段哈希算得对：按长度跳过二进制段，不被假 4:info 骗",
   S.torrent_info_hash(_TOR_A) == _IH and S.torrent_info_hash(_TOR_B) == _IH,
   f"{S.torrent_info_hash(_TOR_A)} | {_IH}")
ck("B6 同一个内容、两个不同 tracker 的种子文件 = 同一条任务",
   S.url_dedup_key(str(TMP / "a.torrent")) == S.url_dedup_key(str(TMP / "b.torrent")),
   S.url_dedup_key(str(TMP / "a.torrent")))
ck("B7 本地种子和它的磁力链接合成一条",
   S.url_dedup_key(str(TMP / "a.torrent")) == S.url_dedup_key("magnet:?xt=urn:btih:" + _IH))
ck("B8 换个内容（名字不同）还是两条",
   S.url_dedup_key(str(TMP / "a.torrent")) != S.url_dedup_key(str(TMP / "c.torrent")))
ck("B9 解析不了的种子退回整文件哈希，不谎称是 info 哈希",
   S.torrent_info_hash(b"d8:announce") == "" and len(S.torrent_bytes_identity(b"d8:announce")) == 16,
   S.torrent_bytes_identity(b"d8:announce"))

# ---------- C. 文件清单与主成品 ----------
raw_files = [
    {"path": str(DL / "包" / "演示.mkv"), "length": "1048576", "completedLength": "1048576", "selected": "true"},
    {"path": str(DL / "包" "说明.txt"), "length": "2048", "completedLength": "2048", "selected": "true"},
    {"path": str(DL / "包" "样本.iso"), "length": "99999999", "completedLength": "0", "selected": "false"},
]
fl = S.bt_file_list(raw_files)
ck("C1 文件清单有序号 / 名称 / 大小", len(fl) == 3 and fl[0]["index"] == 1 and fl[0]["name"] == "演示.mkv"
   and fl[0]["size"] == 1048576, str(fl[:1]))
ck("C2 未选中的文件标出来", fl[2]["selected"] is False and fl[0]["selected"] is True)
ck("C3 完成度按已下字节给", fl[0]["done"] == 1048576 and fl[2]["done"] == 0)

pkg = DL / "包"
pkg.mkdir(parents=True, exist_ok=True)
(pkg / "演示.mkv").write_bytes(b"x" * 4096)
(pkg / "说明.txt").write_text("hello world, longer than the mkv?" * 10, encoding="utf-8")
big = pkg / "样本.iso"
big.write_bytes(b"z" * 8192)
ck("C4 主成品优先挑媒体文件（哪怕别的更大）",
   Path(S.bt_pick_primary([str(pkg / "说明.txt"), str(big), str(pkg / "演示.mkv")])).name == "演示.mkv",
   S.bt_pick_primary([str(pkg / "说明.txt"), str(big), str(pkg / "演示.mkv")]))
ck("C5 全是非媒体时挑最大的那个",
   Path(S.bt_pick_primary([str(pkg / "说明.txt"), str(big)])).name == "样本.iso")
ck("C6 文件都不在时回空串（不当成成功）", S.bt_pick_primary([str(DL / "没有这个.mkv")]) == "")
ck("C7 字节数成人话", S._bt_hsize("1048576") == "1.0 MB" and S._bt_hsize(None) == "0 B",
   f"{S._bt_hsize('1048576')}|{S._bt_hsize(None)}")


# ---------- D. 假 aria2 ----------
class FakeAria:
    """按 aria2c 1.37.0 真回过的字段形状顶替（磁力那一段照 probe 实测写死，见 D27 那组）。"""

    def __init__(self, states, files=None, follow=True):
        self.states = list(states)
        self.files = files or []
        self.gid = "GID-" + str(id(self))[-5:]
        self.child = "CHD-" + self.gid[4:]   # 磁力拿到元数据后，真文件由这个新任务号下
        self.follow = follow
        self.removed = []
        self.added_uri = None
        self.added_torrent = None
        self.opts = []
        self.changed = []

    def add_uri(self, urls, out_dir, filename="", headers=None, split=8, max_conn=8, extra_opts=None):
        self.added_uri = {"urls": list(urls), "dir": out_dir, "opts": dict(extra_opts or {})}
        return self.gid

    def add_torrent(self, torrent_path, out_dir, urls=None, extra_opts=None):
        self.added_torrent = {"path": torrent_path, "dir": out_dir, "opts": dict(extra_opts or {})}
        return self.gid

    def _raw_state(self, gid):
        return self.states.pop(0) if self.states else {"status": "complete", "totalLength": "4096",
                                                       "completedLength": "4096", "numPeers": "1", "speed": "0"}

    def tell_status(self, gid, keys=None):
        st = self._raw_state(gid)
        # 实测（aria2 1.37.0）：磁力父任务把元数据下完就报 complete、totalLength 只有元数据那一两百字节，
        # 同一帧 followedBy 指向下真文件的新任务号；元数据没到手时既没有 complete 也没有 followedBy。
        if gid == self.gid and self.follow and str(st.get("status")) == "complete" \
                and int(st.get("totalLength") or 0):
            st = dict(st, followedBy=[self.child])
        return st

    def get_files(self, gid):
        return list(self.files)

    def remove(self, gid):
        self.removed.append(gid)

    def change_option(self, gid, opts):
        self.changed.append((gid, dict(opts)))
        return True

    def tell_active(self, keys=None):
        return []

    def ping(self, timeout=5):
        return True


def run_job(url, states, files=None, cfg=None, client=None, kind_seed=None):
    """跑一趟 _torrent_job：返回 (任务, 结果三元组, 用到的假客户端)。"""
    t = S.DownloadTask(id="t-" + str(len(S.queue.tasks) + 1), url=url)
    if kind_seed:
        t.kind = kind_seed
    ac = client or FakeAria(states, files)
    prog = []
    S._bt_client = lambda c: ac
    S.bt_ensure = lambda c, lg: (True, "")
    old_watch = S.queue._bt_watch_start
    S.queue._bt_watch_start = lambda: None
    try:
        res = S.queue._torrent_job(t, cfg or dict(BT_CFG), str(DL),
                                   lambda tid, pct, spd, eta, meta=None: prog.append((tid, pct, spd, meta)))
    finally:
        S.queue._bt_watch_start = old_watch
    return t, res, ac, prog


BT_CFG = {"aria2_rpc": "http://127.0.0.1:6800/jsonrpc", "aria2_secret": "",
          "aria2_autostart": True, "aria2_bin": "", "download_dir": str(DL),
          "torrent_meta_timeout": 30, "torrent_seed_ratio": 1.5, "torrent_seed_time": 600}
S._BT_WATCH.clear()

# D1 正常一趟（照 aria2 磁力的两趟：父任务只到元数据，真文件在 followedBy 指的子任务上）
LOGS.rows.clear()
t1, (ok1, p1, note1), ac1, prog1 = run_job(
    MAGNET40,
    [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"},
     {"status": "complete", "totalLength": "114", "completedLength": "114", "numPeers": "1", "speed": "0"},
     {"status": "active", "totalLength": "4096", "completedLength": "2048", "numPeers": "3", "speed": "512"},
     {"status": "complete", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
)
ck("D1 磁力任务报成功", ok1 is True, note1)
ck("D2 主成品是种子里的媒体文件", Path(p1).name == "演示.mkv", p1)
ck("D3 整包目录与文件清单都记住了",
   t1.result_dir == str(pkg) and len(t1.files) == 3 and t1.kind == "torrent",
   f"{t1.result_dir}|{len(t1.files)}|{t1.kind}")
ck("D4 记下 aria2 的任务号（磁力换记下真文件那个子任务号）",
   t1.gid == ac1.child and t1.gid in (t1.resume_hint or ""), f"{t1.gid}|{t1.resume_hint}")
ck("D5 提交的是这条磁力本身", ac1.added_uri and ac1.added_uri["urls"] == [MAGNET40]
   and ac1.added_uri["dir"] == str(DL), str(ac1.added_uri))
ck("D6 让 aria2 永不停种（停种由看护决定）：只给 seed-ratio=0，不能再给 seed-time",
   ac1.added_uri["opts"].get("seed-ratio") == "0" and "seed-time" not in ac1.added_uri["opts"],
   str(ac1.added_uri["opts"]))
ck("D7 进度报过百分比与节点数", any("3 个节点" in str(x[2]) for x in prog1), str(prog1))
ck("D7b 进度里带上卡片要用的已下/总字节（aria2 报的是整个下载，不是主文件）",
   any((x[3] or {}).get("total_bytes") == 4096 and (x[3] or {}).get("done_bytes") == 2048
       for x in prog1), str(prog1))
ck("D8 完成时标题用磁力里的名字，不被清空", t1.title == "演示片", t1.title)
w = S._BT_WATCH.get(ac1.child) or {}
ck("D9 下完转入做种看护，比率/时长按设置登记",
   w.get("ratio") == 1.5 and w.get("seconds") == 600 and w.get("task_id") == t1.id, str(w))
ck("D9b 看护表里记的是子任务号（父任务这时候已经 complete，停它停不掉上传）",
   ac1.gid not in S._BT_WATCH, str(list(S._BT_WATCH)))
ck("D10 提示里说清了包内文件数", "2 个文件" in (note1 or ""), note1)
ck("D10b 日志按真实来源写「磁力任务交给 aria2」",
   any("磁力任务交给 aria2" in m for _l, m in LOGS.rows), str([m for _l, m in LOGS.rows][:1]))

# D11 本地种子走 addTorrent
S._BT_WATCH.clear()
LOGS.rows.clear()
t2, (ok2, p2, note2), ac2, _ = run_job(
    tp.as_uri(),
    [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"},
     {"status": "complete", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
)
ck("D11 本地种子走 aria2.addTorrent", ok2 and ac2.added_torrent
   and ac2.added_torrent["path"] == str(tp), str(ac2.added_torrent))
ck("D12 种子文件名当任务名", t2.title == "种子 一号", t2.title)
ck("D12b 上传的种子不该被日志说成磁力",
   any("种子任务交给 aria2" in m for _l, m in LOGS.rows)
   and not any("磁力任务交给" in m for _l, m in LOGS.rows),
   str([m for _l, m in LOGS.rows][:1]))

# D13 等不到元数据：超时要移除任务并把原因讲清
S._BT_WATCH.clear()
clock = Clock()
S.time = clock
t3, (ok3, p3, note3), ac3, prog3 = run_job(
    MAGNET32, [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"}] * 40,
    cfg=dict(BT_CFG, torrent_meta_timeout=30),
)
S.time = _REAL[5]
ck("D13 等不到元数据报失败", ok3 is False and p3 == "")
ck("D14 超时报错讲清「没人在做种 / DHT 被挡」", "没拿到种子元数据" in note3 and "30 秒" in note3, note3)
ck("D15 超时后把 aria2 那边的任务移除了", ac3.removed == [ac3.gid], str(ac3.removed))
ck("D16 等待期间界面知道在等什么", all(x[2] == "等待种子元数据" for x in prog3) and len(prog3) >= 2, str(prog3[:2]))

# D17 aria2 报错要带上错误码
S._BT_WATCH.clear()
t4, (ok4, p4, note4), ac4, _ = run_job(
    MAGNET40,
    [{"status": "error", "totalLength": "4096", "completedLength": "0", "errorCode": "9",
      "errorMessage": "Cannot resolve host name", "numPeers": "0", "speed": "0"}],
    raw_files,
)
ck("D17 aria2 报错回失败", ok4 is False)
ck("D18 报错保留错误码与原文", "代码 9" in note4 and "Cannot resolve host name" in note4, note4)

# D19 用户点停止：aria2 那边也要跟着移除
S._BT_WATCH.clear()
t5 = S.DownloadTask(id="t-stop", url=MAGNET40)
S.queue.engine._stop_flags[t5.id] = True
ac5 = FakeAria([{"status": "active", "totalLength": "4096", "completedLength": "10", "numPeers": "1", "speed": "10"}])
S._bt_client = lambda c: ac5
S.bt_ensure = lambda c, lg: (True, "")
old_watch = S.queue._bt_watch_start
S.queue._bt_watch_start = lambda: None
try:
    ok5, p5, note5 = S.queue._torrent_job(t5, BT_CFG, str(DL), lambda *a: None)
finally:
    S.queue._bt_watch_start = old_watch
S.queue.engine._stop_flags.pop(t5.id, None)
ck("D19 停止的磁力报「已停止」", ok5 is False and "已停止" in note5, note5)
ck("D20 停止时 aria2 任务被移除", ac5.removed == [ac5.gid], str(ac5.removed))

# D21 aria2 连不上：bt_ensure 的说明要原样给到界面
S._BT_WATCH.clear()
t6 = S.DownloadTask(id="t-noaria", url=MAGNET40)
S.bt_ensure = lambda c, lg: (False, "本机找不到 aria2c：装一个，或在「组件与依赖」里把它的路径指对")
ok6, p6, note6 = S.queue._torrent_job(t6, BT_CFG, str(DL), lambda *a: None)
ck("D21 aria2 不可用时当场回错，不进 aria2", ok6 is False and "找不到 aria2c" in note6, note6)
ck("D22 这种失败不该有任务号", t6.gid == "")

# D23 报完成但一个文件都没落盘
S._BT_WATCH.clear()
t7, (ok7, p7, note7), ac7, _ = run_job(
    MAGNET40,
    [{"status": "active", "totalLength": "10", "completedLength": "10", "numPeers": "1", "speed": "0"},
     {"status": "complete", "totalLength": "10", "completedLength": "10", "numPeers": "1", "speed": "0"}],
    [{"path": str(DL / "并不存在.mkv"), "length": "10", "completedLength": "10", "selected": "true"}],
)
ck("D23 落盘没有文件不算成功", ok7 is False and "一个文件都没落盘" in note7, note7)


class SeedForever(FakeAria):
    """照 aria2 的真样子：给了 seed-ratio=0 之后，真文件下满了状态也一直是 active，永远不会报 complete。"""

    def _raw_state(self, gid):
        if gid == self.gid:      # 父任务只下元数据，一百来字节就报 complete，同时把子任务号递出来
            return {"status": "complete", "totalLength": "114", "completedLength": "114",
                    "numPeers": "1", "speed": "0"}
        return {"status": "active", "totalLength": "4096", "completedLength": "4096",
                "numPeers": "1", "speed": "0", "seedingTime": "30", "uploadLength": "0"}


# D24 做种中的任务必须靠「下满了」收尾，不然界面会永远卡在 99%
S._BT_WATCH.clear()
ac24 = SeedForever([], raw_files)
t8, (ok8, p8, note8), _, _ = run_job(MAGNET40, [], client=ac24)
ck("D24 下满即收尾，不等 aria2 报 complete", ok8 is True and Path(p8).name == "演示.mkv", note8)
ck("D25 收尾当场打上做种标记（看护线程 15 秒才走一拍）", t8.seeding is True)
ck("D26 看护表记的是拿到元数据之后那个任务号，aria2 任务没被移除",
   ac24.child in S._BT_WATCH and not ac24.removed, f"{list(S._BT_WATCH)}|{ac24.removed}")


class TwoStage(FakeAria):
    """磁力在 aria2 里是两趟：父任务只下元数据（getFiles 只有一行 [METADATA]，total 也就那么一两百字节），
    元数据一到 aria2 另起一个 gid 下真文件。父任务这时候报的 complete 当真不得。"""

    def _raw_state(self, gid):
        if gid == self.gid:
            return {"status": "complete", "totalLength": "114", "completedLength": "114",
                    "numPeers": "1", "speed": "0"}
        if getattr(self, "_child_polls", 0) == 0:
            self._child_polls = 1
            return {"status": "active", "totalLength": "4096", "completedLength": "2048",
                    "numPeers": "2", "speed": "512"}
        return {"status": "active", "totalLength": "4096", "completedLength": "4096",
                "numPeers": "2", "speed": "0", "seedingTime": "10", "uploadLength": "0"}

    def get_files(self, gid):
        if gid == self.gid:
            return [{"index": "1", "path": "[METADATA]演示片", "length": "114",
                     "completedLength": "114", "selected": "true"}]
        return list(self.files)


S._BT_WATCH.clear()
ac9 = TwoStage([], raw_files)
t9, (ok9, p9, note9), _, prog9 = run_job(MAGNET40, [], client=ac9)
ck("D27 磁力元数据那一帧的 complete 不当成下载完成（不再报「一个文件都没落盘」）",
   ok9 is True and "一个文件都没落盘" not in (note9 or ""), f"{ok9}|{note9}")
ck("D28 任务号跟着换到下真文件的那个", t9.gid == ac9.child and t9.gid in (t9.resume_hint or ""),
   f"{t9.gid}|{t9.resume_hint}")
ck("D29 看护表登记的也是子任务号（停做种要停得掉），父任务号不进表",
   ac9.child in S._BT_WATCH and ac9.gid not in S._BT_WATCH, str(list(S._BT_WATCH)))
ck("D30 文件清单里没有 [METADATA] 那行占位",
   all("[METADATA]" not in f["name"] for f in (t9.files or [])) and len(t9.files) == 3,
   str([f["name"] for f in (t9.files or [])]))
ck("D31 进度报的是子任务的字节数（不是元数据那一两百字节）",
   any("512 B/s · 2 个节点" in str(x[2]) for x in prog9), str(prog9))

md_row = [{"index": "1", "path": "[METADATA]演示片", "length": "114", "completedLength": "114",
           "selected": "true"},
          {"index": "7", "path": str(pkg / "演示.mkv"), "length": "4096", "completedLength": "4096",
           "selected": "true"}]
fl_md = S.bt_file_list(md_row)
ck("D32 清单把占位行剔掉，序号仍按 aria2 给的那个数（改选要能对上）",
   len(fl_md) == 1 and fl_md[0]["index"] == 7, str(fl_md))

# ---------- E. 做种看护 ----------
S._BT_WATCH.clear()
S.bt_ensure = lambda c, lg: (True, "")
tE = S.DownloadTask(id="t-seed", url=MAGNET40, title="演示片", kind="torrent", gid="G-SEED", seeding=True)
old_tasks = dict(S.queue.tasks)
S.queue.tasks["t-seed"] = tE
try:
    acE = FakeAria([{"status": "active", "uploadLength": "1500", "completedLength": "1000",
                     "seedingTime": "120", "totalLength": "1000"}])
    S._bt_client = lambda c: acE
    S.time = Clock()
    S._BT_WATCH["G-SEED"] = {"task_id": "t-seed", "ratio": 1.0, "seconds": 600, "name": "演示.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E1 比率达标就停止上传", acE.removed == ["G-SEED"], str(acE.removed))
    ck("E2 停完把看护记录摘掉", "G-SEED" not in S._BT_WATCH)
    ck("E3 任务行的「做种中」跟着灭", tE.seeding is False)
    ck("E4 日志说清了为什么停", any("磁力做种结束" in m and "上传比率" in m for _l, m in LOGS.rows),
       str([m for _l, m in LOGS.rows if "做种" in m][-1:]))
    ck("E5 上传量与比率写进任务", tE.uploaded == 1500 and abs(tE.share_ratio - 1.5) < 1e-6, f"{tE.uploaded}|{tE.share_ratio}")

    # E5b 任务卡那行说明要跟着改口：做种都停了还写着「一直做种」就是假话
    #     （上一行 E5 之后 tE 已经被看护线程停掉了，这里把「一直做种」那句补回去再走一遍）
    tE.resume_hint = "1 个文件，一直做种（要停就在「做种中」那行按「停止做种」）"
    S._BT_WATCH["G-SEED"] = {"task_id": "t-seed", "ratio": 1.0, "seconds": 600, "name": "演示.mkv"}
    acE2 = FakeAria([{"status": "active", "uploadLength": "1500", "completedLength": "1000",
                      "seedingTime": "120", "totalLength": "1000"}])
    S._bt_client = lambda c: acE2
    S.time = Clock()
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E5b 自动停种后那行说明改成「做种结束」，不再写着「一直做种」",
       "一直做种" not in (tE.resume_hint or "") and "做种结束" in (tE.resume_hint or ""),
       tE.resume_hint)

    # E6 只按时长的做种：比率没到但时间满了也要停
    tF = S.DownloadTask(id="t-seed2", url=MAGNET40, title="演示片 2", kind="torrent", gid="G-TIME", seeding=True)
    S.queue.tasks["t-seed2"] = tF
    acF = FakeAria([{"status": "active", "uploadLength": "100", "completedLength": "1000",
                     "seedingTime": "700", "totalLength": "1000"}])
    S._bt_client = lambda c: acF
    S.time = Clock()
    S._BT_WATCH["G-TIME"] = {"task_id": "t-seed2", "ratio": 1.0, "seconds": 600, "name": "x.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E6 做满时长也停种", acF.removed == ["G-TIME"] and tF.seeding is False and tF.seed_seconds == 700)
    ck("E7 日志按原因写「做种满」", any("做种满 700 秒" in m for _l, m in LOGS.rows))

    # E8 aria2 回不来（重启过 / 任务没了）：本地记录不能留一个永远不停的「做种中」
    tG = S.DownloadTask(id="t-seed3", url=MAGNET40, kind="torrent", gid="G-GONE", seeding=True)
    S.queue.tasks["t-seed3"] = tG

    class DeadAria(FakeAria):
        def tell_status(self, gid, keys=None):
            raise RuntimeError("connection refused")

    S._bt_client = lambda c: DeadAria([])
    S.time = Clock()
    S._BT_WATCH["G-GONE"] = {"task_id": "t-seed3", "ratio": 1.0, "seconds": 600, "name": "y.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E8 aria2 失联时清掉做种标记", "G-GONE" not in S._BT_WATCH and tG.seeding is False)

    # E9 看护线程 15 秒才走一拍，睡这一觉的工夫用户可能已经按了「停止做种」：
    #      它手里那份 15 秒前的快照不能把这条重新标成「做种中」
    tJ = S.DownloadTask(id="t-seed4", url=MAGNET40, kind="torrent", gid="G-STOP", seeding=True)
    S.queue.tasks["t-seed4"] = tJ

    class PopWhileSleeping(Clock):
        def __init__(self, awake_hook):
            super().__init__()
            self.awake_hook = awake_hook

        def sleep(self, s):
            super().sleep(s)
            self.awake_hook()

    acJ = FakeAria([{"status": "active", "uploadLength": "9000", "completedLength": "1000",
                     "seedingTime": "5", "totalLength": "1000"}])
    S._bt_client = lambda c: acJ

    def _user_stopped():
        with S._BT_WATCH_LOCK:
            S._BT_WATCH.pop("G-STOP", None)
        tJ.seeding = False

    S.time = PopWhileSleeping(_user_stopped)
    S._BT_WATCH["G-STOP"] = {"task_id": "t-seed4", "ratio": 1.0, "seconds": 600, "name": "z.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E9 手动停种后，看护的旧快照不把它标回「做种中」",
       tJ.seeding is False and tJ.uploaded == 0 and "G-STOP" not in S._BT_WATCH,
       f"{tJ.seeding}|{tJ.uploaded}|{list(S._BT_WATCH)}")
    ck("E9b 这条早就不归看护管了，不该再去问 aria2", acJ.removed == [] and len(acJ.states) == 1,
       f"{acJ.removed}|{len(acJ.states)}")

    # E10 任务号已从 aria2 摘掉时它不抛异常，只回一个空对象：这同样得算没在做种
    tK = S.DownloadTask(id="t-seed5", url=MAGNET40, kind="torrent", gid="G-EMPTY", seeding=True)
    S.queue.tasks["t-seed5"] = tK

    class EmptyAria(FakeAria):
        """aria2 认不出这个任务号时不抛异常，只回一个空对象。看护少了处理就会一直缠着它转，
        所以这里数着调用次数：第二次直接把看护表清空让线程退出来，由 E10 断言「只该问一次」。"""

        def __init__(self):
            super().__init__([])
            self.calls = 0

        def tell_status(self, gid, keys=None):
            self.calls += 1
            if self.calls > 1:
                with S._BT_WATCH_LOCK:
                    S._BT_WATCH.clear()
            return {}

    acK = EmptyAria()
    S._bt_client = lambda c: acK
    S.time = Clock()
    S._BT_WATCH["G-EMPTY"] = {"task_id": "t-seed5", "ratio": 1.0, "seconds": 600, "name": "w.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E10 aria2 回空对象时也清掉做种标记", "G-EMPTY" not in S._BT_WATCH and tK.seeding is False,
       f"{tK.seeding}|{list(S._BT_WATCH)}")
    ck("E10b 这种任务只该问一次，不能缠着 aria2 空转", acK.calls == 1, f"calls={acK.calls}")

    # E11~E13 aria2 自己报出来的三种「不在做种」状态：看护不能还挂着「做种中」
    #      （实测 1.37.0：正在做种是 active；本地文件不齐是 error；
    #        被 removeSeed/外部停掉后 tellStatus 回 complete；手动 pause 后回 paused，
    #        而 paused 不会出现在 tellActive 里，所以做种清单只能靠 tellStatus 兜出来）
    tL = S.DownloadTask(id="t-err", url=MAGNET40, title="缺文件的.mkv", kind="torrent",
                        gid="G-ERR", seeding=True)
    tM = S.DownloadTask(id="t-done", url=MAGNET40, title="传完的.mkv", kind="torrent",
                        gid="G-DONE", seeding=True)
    S.queue.tasks["t-err"], S.queue.tasks["t-done"] = tL, tM

    class StatusByGid(FakeAria):
        """按任务号回固定状态，不看 states 队列——测的就是「状态本身」这一支。"""

        def __init__(self, table):
            super().__init__([])
            self.table = dict(table)

        def tell_status(self, gid, keys=None):
            return dict(self.table.get(gid) or {})

    acL = StatusByGid({"G-ERR": {"status": "error", "uploadLength": "0", "completedLength": "0",
                                  "totalLength": "0", "seedingTime": "0"},
                       "G-DONE": {"status": "complete", "uploadLength": "1000",
                                  "completedLength": "1000", "totalLength": "1000",
                                  "seedingTime": "90"}})
    S._bt_client = lambda c: acL
    S.time = Clock()
    S._BT_WATCH["G-ERR"] = {"task_id": "t-err", "ratio": 1.0, "seconds": 600, "name": "缺文件的.mkv"}
    S._BT_WATCH["G-DONE"] = {"task_id": "t-done", "ratio": 1.0, "seconds": 600, "name": "传完的.mkv"}
    LOGS.rows.append(("info", "marker-e11"))
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E11 aria2 报 error 的做种任务：登记摘掉、「做种中」灭、说明写清是出错",
       "G-ERR" not in S._BT_WATCH and tL.seeding is False
       and "已出错" in (tL.resume_hint or ""), f"{tL.seeding}|{tL.resume_hint}")
    ck("E12 aria2 报 complete（它自己停了做种）：同样摘登记、灭标记",
       "G-DONE" not in S._BT_WATCH and tM.seeding is False
       and "停种" in (tM.resume_hint or ""), f"{tM.seeding}|{tM.resume_hint}")
    ck("E12b 这两种 aria2 都已经不管了，看护不该再去 remove 一次", acL.removed == [], str(acL.removed))
    ck("E12c 反常状态要进运行日志，不然界面上「做种中」凭空消失没人知道为什么",
       all(any("做种看护" in m and k in m for _l, m in LOGS.rows) for k in ("出错", "停种")),
       str([m for _l, m in LOGS.rows if "做种看护" in m]))

    tN = S.DownloadTask(id="t-pz", url=MAGNET40, title="被暂停的.mkv", kind="torrent",
                        gid="G-PZ", seeding=True)
    S.queue.tasks["t-pz"] = tN

    class PausedAria(FakeAria):
        """paused 的做种任务还得留在看护表里，「做种中」那行才点得到「停止做种」。
        第二次问的时候替用户把它停掉，线程才退得出来；calls==2 就反证第一次没被摘。"""

        def __init__(self):
            super().__init__([])
            self.calls = 0

        def tell_status(self, gid, keys=None):
            self.calls += 1
            if self.calls > 1:
                with S._BT_WATCH_LOCK:
                    S._BT_WATCH.pop(gid, None)
            return {"status": "paused", "uploadLength": "0", "completedLength": "1000",
                    "totalLength": "1000", "seedingTime": "50"}

    acN = PausedAria()
    S._bt_client = lambda c: acN
    S.time = Clock()
    S._BT_WATCH["G-PZ"] = {"task_id": "t-pz", "ratio": 1.0, "seconds": 600, "name": "被暂停的.mkv"}
    S.queue._bt_watch_loop()
    S.time = _REAL[5]
    ck("E13 paused 不上传了就说「当前不上传」，标记灭",
       tN.seeding is False and "paused" in (tN.resume_hint or "")
       and "重新提交" in (tN.resume_hint or ""), tN.resume_hint)
    ck("E13b paused 要留在看护表里（第二拍还在问它＝登记没被摘）；摘掉就没法停止做种了",
       acN.calls == 2, f"calls={acN.calls}")
    ck("E13c 本程序的暂停/继续不碰 aria2，所以说明里不能承诺按哪个按钮能恢复",
       "继续" not in (tN.resume_hint or "") and acN.removed == [], f"{tN.resume_hint}|{acN.removed}")

finally:
    S.queue.tasks.clear()
    S.queue.tasks.update(old_tasks)
    S._BT_WATCH.clear()

# ---------- F. 入队闸门与预检 ----------
S.bt_ensure = lambda c, lg: (True, "")
_added = {}


class FakeQueue:
    def add_urls(self, urls, options):
        _added["urls"] = list(urls)
        _added["options"] = dict(options)
        return ["id" + str(i) for i in range(len(urls))]


_real_queue = S.queue
S.queue = FakeQueue()
try:
    body = S.AddUrlsBody(urls=[MAGNET40, MAGNET_BAD])
    try:
        S.api_download(body)
        ck("F1 缺 xt=urn:btih 的磁力当场拒绝", False, "没抛 400")
    except S.HTTPException as e:
        ck("F1 缺 xt=urn:btih 的磁力当场拒绝", e.status_code == 400 and "xt=urn:btih" in e.detail, str(e.detail))
    ck("F1b 拒绝时一个任务都不建", "urls" not in _added, str(_added))
    r2 = S.api_download(S.AddUrlsBody(urls=[MAGNET40, tp.as_uri(), "https://example.com/a.torrent",
                                            MAGNET32 + "&foo=1", "  ", "not-a-link"]))
    got_urls = _added.get("urls", [])
    good = [u for u in got_urls if S.parse_torrent_ref(u)]
    ck("F2 磁力与本地种子都能入队", len(good) == 3 and MAGNET40 in good and tp.as_uri() in good, str(got_urls))
    ck("F3 网上的 .torrent 链接仍按普通链接排队，不被当本地种子",
       "https://example.com/a.torrent" in got_urls and S.parse_torrent_ref("https://example.com/a.torrent") is None,
       str(got_urls))
    ck("F3b 无效条目照旧被忽略", "not-a-link" not in got_urls and r2["skipped"] >= 1, str(r2))
    ck("F4 磁力尾巴上多出来的参数不改变它是哪条内容",
       S.url_dedup_key(MAGNET32 + "&foo=1") == S.url_dedup_key(MAGNET32))
    # F5 磁力单不需要 yt-dlp / FFmpeg，也不该被它们的缺失拦住
    S.cfg = FakeCfg({"download_dir": str(DL), "aria2_rpc": "http://127.0.0.1:6800/jsonrpc"})
    errs, warns = S.download_preflight([MAGNET40], {})
    ck("F5 纯磁力单不检查 yt-dlp / FFmpeg", errs == [], str(errs))
    errs2, _w = S.download_preflight([MAGNET40, tp.as_uri(), "https://example.com/a.torrent"], {})
    ck("F6 混进网页链时仍按网页链检查", isinstance(errs2, list))
    # F7 aria2 起不来要拦住入队
    S.bt_ensure = lambda c, lg: (False, "RPC 没有应答")
    errs3, _w3 = S.download_preflight([MAGNET40], {})
    ck("F7 aria2 连不上时磁力不入队", any("aria2" in e for e in errs3), str(errs3))
    S.bt_ensure = lambda c, lg: (True, "")
    # F8 种子文件不见了要说清
    gone = (TMP / "没了.torrent")
    errs4, _w4 = S.download_preflight([gone.as_uri()], {})
    ck("F8 种子文件缺失报错点名路径", any("不存在" in e and "没了.torrent" in e for e in errs4), str(errs4))
finally:
    S.queue = _real_queue
    S.cfg = FakeCfg({"download_dir": str(DL)})

# ---------- G. 上传种子 ----------
STORE = TMP / "uploads"
STORE.mkdir(parents=True)
_real_store = S._torrent_store_dir
S._torrent_store_dir = lambda: STORE


class Up:
    """顶替 fastapi 的 UploadFile：只用得到 filename 和 await read()。"""

    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


up_body = tp.read_bytes()
up1 = asyncio.run(S.api_torrent_upload(Up("种子 一号.torrent", up_body)))
ck("G1 上传种子回一条能入队的 file:// 链接",
   up1["ok"] and S.parse_torrent_ref(up1["url"])["kind"] == "torrent-file", str(up1))
ck("G1b 回的名字是人看得懂的文件名", up1["name"] == "种子 一号", up1["name"])
up1b = asyncio.run(S.api_torrent_upload(Up("种子 一号.torrent", up_body)))
ck("G2 同一份种子重复上传落回同一个文件", up1b["path"] == up1["path"], f"{up1['path']} | {up1b['path']}")
up2 = asyncio.run(S.api_torrent_upload(Up("改名了.torrent", up_body)))
ck("G2b 换个文件名但内容相同 = 同一条任务（去重按内容哈希）",
   up2["path"] != up1["path"] and S.url_dedup_key(up1["url"]) == S.url_dedup_key(up2["url"]),
   f"{up1['path']} | {up2['path']}")
ck("G3 存下来的种子内容没变样", Path(up1["path"]).read_bytes() == up_body)
up3 = asyncio.run(S.api_torrent_upload(Up("种子 一号.torrent", b"d8:another different")))
ck("G3b 同名但内容不同：另存一份，不把先前的种子覆盖掉",
   up3["path"] != up1["path"] and Path(up1["path"]).read_bytes() == up_body
   and S.url_dedup_key(up1["url"]) != S.url_dedup_key(up3["url"]), f"{up1['path']} | {up3['path']}")
ck("G4 恶意文件名被洗掉，落在 uploads 目录里",
   Path(up1["path"]).parent == STORE and ".." not in Path(up1["path"]).name, str(up1["path"]))
import inspect  # noqa: E402

_src_store = inspect.getsource(_real_store)
ck("G5 默认落点在 torrent_state/uploads（打包要整目录排除）",
   "torrent_state" in _src_store and "uploads" in _src_store, _src_store.replace("\n", " ")[:120])
for bad_name, bad_body, tag in (("a.txt", b"d8:announce", "G6 非 .torrent 后缀要拒"),
                                ("a.torrent", b"", "G7 空文件要拒"),
                                ("a.torrent", b"not bencode at all", "G8 内容不像种子要拒")):
    try:
        asyncio.run(S.api_torrent_upload(Up(bad_name, bad_body)))
        ck(tag, False, "没抛 400")
    except S.HTTPException as e:
        ck(tag, e.status_code == 400, str(e.detail))
try:
    got = asyncio.run(S.api_torrent_upload(Up(".." + chr(92) + ".." + chr(92) + "evil.torrent", b"d8:x")))
    ck("G9 带路径分隔的文件名跳不出 uploads 目录",
       Path(got["path"]).parent == STORE and str(TMP) in str(got["path"]), str(got["path"]))
except S.HTTPException as e:
    ck("G9 带路径分隔的文件名跳不出 uploads 目录", False, str(e.detail))
S._torrent_store_dir = _real_store

# ---------- H. 改选文件 / 做种清单 / 停种 ----------
tH = S.DownloadTask(id="t-sel", url=MAGNET40, kind="torrent", gid="G-SEL", title="演示片")
tH.files = list(fl)
old_tasks = dict(S.queue.tasks)
S.queue.tasks["t-sel"] = tH
try:
    acH = FakeAria([], raw_files)
    S._bt_client = lambda c: acH
    r = S.api_torrent_select(S.TorrentSelectBody(task_id="t-sel", indices=[3, 1, 1]))
    ck("H1 改选按序号交给 aria2（去重升序）", acH.changed and acH.changed[0][1]["select-file"] == "1,3",
       str(acH.changed))
    ck("H2 改选把序号列表交给 select-file（aria2 只认这个写法，select-file=true + index 会被拒）",
       acH.changed and acH.changed[0][1].get("select-file") == "1,3" and "index" not in acH.changed[0][1],
       str(acH.changed[:1]))
    ck("H3 返回新的文件清单", len(r["files"]) == 3 and r["count"] == 2, str(r))
    ck("H3b 回给界面的勾选状态按这次点名的序号写（aria2 的 selected 要过一秒才翻，直接回它就成了回退）",
       [f["selected"] for f in sorted(r["files"], key=lambda x: x["index"])] == [True, False, True],
       str([(f["index"], f["selected"]) for f in r["files"]]))
    try:
        S.api_torrent_select(S.TorrentSelectBody(task_id="t-none", indices=[1]))
        ck("H4 没交给 aria2 的任务改不了选", False, "没抛 404")
    except S.HTTPException as e:
        ck("H4 没交给 aria2 的任务改不了选", e.status_code == 404, str(e.detail))
    try:
        S.api_torrent_select(S.TorrentSelectBody(task_id="t-sel", indices=[]))
        ck("H5 一个都不选要拒绝", False, "没抛 400")
    except S.HTTPException as e:
        ck("H5 一个都不选要拒绝", e.status_code == 400 and "至少" in e.detail, str(e.detail))

    # H6 做种清单：我们管着的 + aria2 里我们没管过的都要列出来
    S._BT_WATCH["G-SEED2"] = {"task_id": "t-sel", "ratio": 1.0, "seconds": 600, "name": "演示.mkv"}
    tH.seeding = True
    tH.uploaded, tH.share_ratio, tH.seed_seconds = 2000, 2.0, 60

    class MixedAria(FakeAria):
        def tell_active(self, keys=None):
            return [{"gid": "G-OUTSIDE", "status": "active", "totalLength": "1000", "completedLength": "1000",
                     "uploadLength": "500", "uploadSpeed": "1024", "seedingTime": "33",
                     "bittorrent": {"infoHash": "b" * 40}},
                    {"gid": "G-SEED2", "status": "active", "totalLength": "1", "completedLength": "1",
                     "uploadLength": "1", "seedingTime": "1", "numPeers": "3", "numSeeders": "1",
                     "uploadSpeed": "2048",
                     "bittorrent": {"infoHash": "c" * 40, "info": {"name": "演示片（整包）"},
                                    "announceList": [["http://a/announce"], ["http://b/announce"]]}},
                    {"gid": "G-HTTP", "status": "active", "totalLength": "1", "completedLength": "1",
                     "uploadLength": "0", "seedingTime": "0"}]

        def tell_status(self, gid, keys=None):
            # 暂停的做种任务不在 tellActive 里（实测），清单要补问一次才知道它到底算什么状态
            if gid == "G-PAUSED":
                return {"status": "paused", "completedLength": "10", "uploadLength": "5",
                        "seedingTime": "7", "bittorrent": {"info": {"name": "暂停的那份"}}}
            return {}

        def get_files(self, gid):
            return [{"path": str(pkg / "外部.mkv"), "length": "1000", "completedLength": "1000"}]

    S._bt_client = lambda c: MixedAria([])
    S._BT_WATCH["G-PAUSED"] = {"task_id": "t-paused-only", "ratio": 1.0, "seconds": 600, "name": "暂停的那份"}
    seed = S.api_torrent_seeding()
    rows = {r0["gid"]: r0 for r0 in seed["items"]}
    ck("H6 做种清单列出程序管着的任务",
       "G-SEED2" in rows and rows["G-SEED2"]["managed"] and rows["G-SEED2"]["share_ratio"] == 1.0, str(rows))
    ck("H6b 做种清单用 aria2 当场读数，不拿任务里那份旧数充当现状",
       rows["G-SEED2"]["uploaded"] == 1 and rows["G-SEED2"]["seed_seconds"] == 1, str(rows["G-SEED2"]))
    ck("H6c 上传速率 / peer 数 / tracker 数按 aria2 的读数给出",
       rows["G-SEED2"]["upload_speed"] == "2048" and rows["G-SEED2"]["num_peers"] == "3"
       and rows["G-SEED2"]["tracker_count"] == 2, str(rows["G-SEED2"]))
    ck("H6d 名字取种子里的 info.name，不是「清单里第一个文件」",
       rows["G-SEED2"]["name"] == "演示片（整包）", str(rows["G-SEED2"].get("name")))
    ck("H6e aria2 没回这个键就不写成 0 假装量过（0 会被界面当成「没 peer」）",
       "num_peers" not in rows["G-OUTSIDE"], str(rows["G-OUTSIDE"]))
    ck("H6e2 tracker 数同理：bittorrent 里没有 announceList 就不给这个键"
       "（实测做种中的任务 aria2 会回 numSeeders 却不回 numPeers，缺键是真会发生的）",
       "tracker_count" not in rows["G-OUTSIDE"] and rows["G-OUTSIDE"].get("num_seeders") is None,
       str(rows["G-OUTSIDE"]))
    ck("H6f 暂停的做种任务不在活动队列里，也要列出来并补读出它的状态",
       rows.get("G-PAUSED", {}).get("in_queue") is False
       and rows["G-PAUSED"].get("aria2_status") == "paused"
       and rows["G-PAUSED"].get("share_ratio") == 0.5, str(rows.get("G-PAUSED")))
    ck("H7 也列出 aria2 里程序没管过的做种", "G-OUTSIDE" in rows and rows["G-OUTSIDE"]["managed"] is False
       and rows["G-OUTSIDE"]["name"] == "外部.mkv", str(rows.get("G-OUTSIDE")))
    ck("H8 同一个 gid 不重复列", sum(1 for r0 in seed["items"] if r0["gid"] == "G-SEED2") == 1)
    ck("H9 非 BT 的活动任务不进这张表", "G-HTTP" not in rows, str(list(rows)))

    # H10 停种要按点名的范围，不给范围就一个都不停
    S._BT_WATCH.pop("G-PAUSED", None)  # 这条只为测「不在活动队列也要列出来」，留着会搅乱后面的停种计数
    class AllAria(FakeAria):
        """aria2 里除程序登记过的那两条，还挂着一条下满了的（没人管）和一条正在下的。"""

        def tell_active(self, keys=None):
            return [{"gid": "G-OUTSIDE2", "status": "active", "totalLength": "1000",
                     "completedLength": "1000", "uploadLength": "500",
                     "bittorrent": {"infoHash": "d" * 40}},
                    {"gid": "G-DL", "status": "active", "totalLength": "2000",
                     "completedLength": "500", "uploadLength": "0",
                     "bittorrent": {"infoHash": "e" * 40}}]

    ac10 = AllAria([])
    S._bt_client = lambda c: ac10
    st = S.api_torrent_stop_seed(S.TorrentStopBody(ids=["t-other"]))
    ck("H10a 没点到就一个都不停", st["stopped"] == 0 and ac10.removed == [] and "G-SEED2" in S._BT_WATCH, str(st))
    st2 = S.api_torrent_stop_seed(S.TorrentStopBody(gids=["G-OUTSIDE"]))
    ck("H10b 只给 gid 也能停（程序外的做种）", st2["stopped"] == 1 and "G-OUTSIDE" in ac10.removed, str(st2))
    tH.resume_hint = "1 个文件，一直做种（要停就在「做种中」那行按「停止做种」）"
    st3 = S.api_torrent_stop_seed(S.TorrentStopBody(ids=["t-sel"]))
    ck("H10c 按任务 ID 停：看护记录摘掉、做种标记灭",
       st3["stopped"] == 1 and "G-SEED2" not in S._BT_WATCH and tH.seeding is False, str(st3))
    ck("H10h 手动停种后那行说明跟着改口（停完还写「一直做种」就是假话）",
       "一直做种" not in (tH.resume_hint or "") and "手动停止" in (tH.resume_hint or ""),
       tH.resume_hint)
    S._BT_WATCH["G-ALL1"] = {"task_id": "t-a", "ratio": 1.0, "seconds": 600, "name": "一.mkv"}
    S._BT_WATCH["G-ALL2"] = {"task_id": "t-b", "ratio": 1.0, "seconds": 600, "name": "二.mkv"}
    st4 = S.api_torrent_stop_seed(S.TorrentStopBody(all=True))
    ck("H10d all=true 才全停", st4["stopped"] == 3 and {"G-ALL1", "G-ALL2"} <= set(ac10.removed),
       f"{st4}|{ac10.removed}")
    ck("H10f all=true 连程序没登记、但已经下满还在上传的也停掉（清单列得出来就得停得掉）",
       "G-OUTSIDE2" in ac10.removed, str(ac10.removed))
    ck("H10g 正在下载的不受「全部停止做种」牵连", "G-DL" not in ac10.removed, str(ac10.removed))
    ck("H10e 不给范围时一个都不停（防止手滑）",
       S.api_torrent_stop_seed(S.TorrentStopBody())["stopped"] == 0)
    LOGS.rows.append(("info", "marker"))
    ck("H11 停种写进运行日志", any("手动停止做种" in m for _l, m in LOGS.rows))
finally:
    S._BT_WATCH.clear()
    S.queue.tasks.clear()
    S.queue.tasks.update(old_tasks)

# ---------- I. 删除任务要顺带停掉 aria2 那边 ----------
tI = S.DownloadTask(id="t-del", url=MAGNET40, kind="torrent", gid="G-DEL", seeding=True)
S.queue.tasks["t-del"] = tI
S._BT_WATCH["G-DEL"] = {"task_id": "t-del", "ratio": 1.0, "seconds": 600, "name": "z.mkv"}
acI = FakeAria([])
S._bt_client = lambda c: acI
_real_pump = S.queue._pump
S.queue._pump = lambda: None
try:
    S.queue.delete_tasks(["t-del"])
finally:
    S.queue._pump = _real_pump
ck("I1 删除磁力任务把 aria2 任务移除", acI.removed == ["G-DEL"], str(acI.removed))
ck("I2 删除后看护表里没有残留", "G-DEL" not in S._BT_WATCH)
ck("I3 「清除已完成」不动做种（那是列表整理，不是放弃上传）",
   "bt_release" not in Path(S.__file__).read_text(encoding="utf-8").split("def clear_finished")[1][:200])

# ---------- J. 接口与配置齐不齐 ----------
paths = {getattr(r, "path", "") for r in S.app.routes}
for need in ("/api/torrent/upload", "/api/torrent/select", "/api/torrent/seeding", "/api/torrent/stop-seed"):
    ck(f"J1 路由已注册 {need}", need in paths)
d = S.ConfigManager.DEFAULTS
ck("J2 默认配置有 aria2 路径与自启开关", "aria2_bin" in d and d.get("aria2_autostart") is True)
ck("J3 默认做种比率/时长/元数据等待都有",
   d.get("torrent_seed_ratio") == 1.0 and d.get("torrent_seed_time") == 3600
   and d.get("torrent_meta_timeout") == 180, str({k: d.get(k) for k in
                                                 ("torrent_seed_ratio", "torrent_seed_time", "torrent_meta_timeout")}))
ck("J4 磁力不进参数清洗（原样交给 aria2）", S.normalize_url(MAGNET40) == MAGNET40)
ck("J5 任务对象带着做种要用的字段",
   all(hasattr(S.DownloadTask(id="x", url="http://a"), k)
       for k in ("kind", "files", "result_dir", "gid", "seeding", "uploaded", "share_ratio", "seed_seconds")))
spec = S.AddUrlsBody(urls=["http://a"])
ck("J6 单条任务能覆盖做种目标",
   "torrent_seed_ratio" in spec.model_dump() and spec.torrent_seed_time is None)
cb = S.ConfigBody(aria2_bin="H:/Varia/aria2c.exe", aria2_autostart=False,
                  torrent_seed_ratio=2.5, torrent_seed_time=7200, torrent_meta_timeout=60)
dumped = cb.model_dump(exclude_none=True)
ck("J7 保存设置收得下 aria2 与做种这几项（收不下就是界面填了留不住）",
   set(dumped) == {"aria2_bin", "aria2_autostart", "torrent_seed_ratio", "torrent_seed_time", "torrent_meta_timeout"},
   str(sorted(dumped)))


class WritableCfg(FakeCfg):
    def save(self):
        pass


_J_CFG = WritableCfg({"download_dir": str(DL)})
_real_cfg_j = S.cfg
S.cfg = _J_CFG
try:
    S.api_set_config(S.ConfigBody(torrent_seed_ratio=-5, torrent_seed_time=99999999, torrent_meta_timeout=1))
    got = {k: _J_CFG.data.get(k) for k in ("torrent_seed_ratio", "torrent_seed_time", "torrent_meta_timeout")}
    ck("J8 越界的做种参数夹回可用范围",
       got == {"torrent_seed_ratio": 0.0, "torrent_seed_time": 604800, "torrent_meta_timeout": 30}, str(got))
    S.api_set_config(S.ConfigBody(aria2_autostart=False, aria2_bin=""))
    ck("J9 关掉的自启与清空的路径能原样存下（False/空串不算没填）",
       _J_CFG.data.get("aria2_autostart") is False and _J_CFG.data.get("aria2_bin") == "",
       str(_J_CFG.data.get("aria2_autostart")))
finally:
    S.cfg = _real_cfg_j

# ---------- K. aria2 守护进程只在 127.0.0.1 ----------
import aria2_daemon as AD  # noqa: E402

ck("K1 指到不存在的路径时不会硬用那个", AD.find_binary(str(TMP / "nope.exe"), TMP) != str(TMP / "nope.exe"),
   AD.find_binary(str(TMP / "nope.exe"), TMP))
fake_bin = TMP / "aria2c.exe"
fake_bin.write_bytes(b"x")
ck("K2 设置里指的路径优先", AD.find_binary(str(fake_bin), TMP) == str(fake_bin))
ck("K3 端口从 RPC 地址里取", AD.running_rpc_port("http://127.0.0.1:6999/jsonrpc") == 6999
   and AD.running_rpc_port("http://127.0.0.1/jsonrpc") == 6800)
okk, why = AD.ensure_running(rpc_url="http://10.0.0.8:6800/jsonrpc", binary=str(fake_bin),
                             download_dir=str(DL), app_dir=TMP, ping=lambda: False, log=lambda m: None)
ck("K4 非本机 RPC 一律不自动拉起", okk is False and "本机" in why, why)
okk2, why2 = AD.ensure_running(rpc_url="http://127.0.0.1:6800/jsonrpc", binary=str(TMP / "没有这个.exe"),
                               download_dir=str(DL), app_dir=TMP, ping=lambda: False, log=lambda m: None)
ck("K5 没有 aria2c 时说清要么装要么指路径", okk2 is False and "aria2c" in why2, why2)
okk3, why3 = AD.ensure_running(rpc_url="http://127.0.0.1:6800/jsonrpc", binary=str(fake_bin),
                               download_dir=str(DL), app_dir=TMP, ping=lambda: True, log=lambda m: None)
ck("K6 RPC 已经有人应答就什么都不做", okk3 and "已在运行" in why3, why3)
ck("K7 没拉起过进程时 owned 说「不是我们起的」", AD.owned() == {"owned": False, "pid": None, "alive": False},
   str(AD.owned()))
AD.shutdown()
ck("K8 shutdown 对没拉起的进程是安全的", AD.owned()["owned"] is False)

# ---------- L. 客户端的参数覆盖 ----------
from aria2_client import Aria2Client, BT_KEYS  # noqa: E402

captured = {}


class Cap(Aria2Client):
    def _call(self, method, params=None, timeout=15):
        captured["method"] = method
        captured["params"] = list(params or [])
        return "OK"


c = Cap("http://127.0.0.1:6800/jsonrpc", "")
c.add_uri(["magnet:?x"], out_dir=str(DL), extra_opts={"seed-ratio": "0", "split": "1"})
o = captured["params"][1]
ck("L1 extra_opts 能覆盖默认值（磁力不分片）",
   o["seed-ratio"] == "0" and o["split"] == "1" and o["dir"] == str(DL), str(o))
c.add_torrent(str(tp), str(DL), extra_opts={"seed-ratio": "0"})
import base64 as _b64  # noqa: E402

_m2, _p2 = captured["method"], captured["params"]
ck("L2 addTorrent 把种子内容 base64 交上去",
   _m2 == "aria2.addTorrent" and _b64.b64decode(_p2[0]) == tp.read_bytes() and _p2[2]["seed-ratio"] == "0"
   and _p2[2]["dir"] == str(DL), str(_p2[2]))
ck("L3 BT_KEYS 里做种要读的字段齐",
   {"uploadLength", "seedingTime", "numPeers", "completedLength", "errorCode"} <= set(BT_KEYS))
ck("L4 默认字段仍留给直链加速用（out/split/continue）",
   "continue" in o and "out" not in o)

# ---------- M. aria2 回 HTTP 错误码时要把它的理由带出来 ----------
# 实测过：坏种子文件 aria2 回 HTTP 400 + {"error":{"message":"Bencode decoding failed"}}，
# urllib 会抛 HTTPError 并把响应体藏起来；只报「HTTP Error 400: Bad Request」等于把原因丢了。
import aria2_client as AC  # noqa: E402
import io  # noqa: E402
from email.message import Message as _Msg  # noqa: E402

_real_urlopen = AC.urlopen


def _http_error(payload, code=400):
    return AC.HTTPError("http://127.0.0.1:16851/jsonrpc", code, "Bad Request", _Msg(), io.BytesIO(payload))


def _raise(payload, code=400):
    def _f(req, timeout=None):
        raise _http_error(payload, code)
    return _f


def _resp(payload):
    class _R:
        def read(self_inner):
            return payload

        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

    def _f(req, timeout=None):
        return _R()
    return _f


ac_m = AC.Aria2Client("http://127.0.0.1:16851/jsonrpc", "")


def _grab(fn):
    try:
        fn()
    except Exception as e:
        return str(e)
    return ""


try:
    AC.urlopen = _raise(b'{"error":{"code":1,"message":"Bencode decoding failed"}}')
    m1 = _grab(lambda: ac_m.add_torrent(str(tp), str(DL)))
    ck("M1 aria2 的拒绝理由跟着一起报出来（不是只剩 HTTP 400）",
       "HTTP 400" in m1 and "Bencode decoding failed" in m1, m1)
    AC.urlopen = _raise(b"<html>Bad Request</html>")
    m2 = _grab(lambda: ac_m.tell_status("G-NOPE"))
    ck("M2 响应体读不出 JSON 时也要说「没给原因」，不能退化成裸 400",
       "HTTP 400" in m2 and "且没有给出原因" in m2, m2)
    AC.urlopen = _raise(b'{"result":"16ce9127b200af05"}')
    m3 = _grab(lambda: ac_m.tell_status("G-NOPE"))
    ck("M3 4xx 但响应体里没有 error 字段：同样归到「没给原因」",
       "HTTP 400" in m3 and "且没有给出原因" in m3, m3)
    AC.urlopen = _raise(b'{"error":{"code":1,"message":"Unauthorized"}}', code=401)
    m4 = _grab(lambda: ac_m.add_uri(["http://a"], str(DL)))
    ck("M4 状态码不能写死 400（Secret 不对时的 401 也要照实报）",
       "HTTP 401" in m4 and "Unauthorized" in m4, m4)
    AC.urlopen = _raise(b'{"error":{"code":1,"message":"boom"}}')
    ck("M5 ping 撞上 aria2 拒绝只说连不上、不往外抛（检测按钮不能因此崩）",
       ac_m.ping(timeout=2) is False)
    AC.urlopen = _resp(b'{"error":{"code":23,"message":"No such download for gid: G-OLD"}}')
    m6 = _grab(lambda: ac_m.tell_status("G-OLD"))
    ck("M6 JSON-RPC 层的错误信息原样带出（新分支没吃掉老通道）",
       "No such download for gid" in m6, m6)
    AC.urlopen = _resp(b'{"jsonrpc":"2.0","id":"x","result":"16ce9127b200af05"}')
    ck("M7 正常返回照旧拿到任务号", ac_m.add_torrent(str(tp), str(DL)) == "16ce9127b200af05")

    # M8~M9 aria2 代码 13：本机实测撞上的死路（目录里已有旧成品、却没有 .aria2 续传记录，
    #       aria2 为防把成品截断成 0 字节当场取消）。报错要保留原话，还要指得出下一步按哪个按钮。
    e13 = ("File C:/x/Downloads/演示片 exists, but a control file(*.aria2) does not exist. "
           "Download was canceled in order to prevent your file from being truncated to 0.")
    t13 = S.bt_error_text("13", e13)
    ck("M8 代码 13 的原话一个字不删，另加两条走法（删掉重下 / 勾「只做种」）",
       "代码 13" in t13 and "control file" in t13 and "truncated to 0" in t13
       and "只做种" in t13 and "删掉" in t13, t13)
    ck("M9 别的错误码不能顺带挂上这套建议（那是 13 特有的坑，挂错了会把人引去删文件）",
       "只做种" not in S.bt_error_text("3", "Resource not found")
       and S.bt_error_text("3", "") == "aria2 报错（代码 3）：未知原因", S.bt_error_text("3", ""))
    # M10 代码 12：界面实测撞上的另一个坑——同一个 .torrent 提交第二次，aria2 直接回
    #       "InfoHash ... is already registered"，而下完转做种的那条也算数，界面上看着没任务却加不进去。
    e12 = "InfoHash c8e38c57cb2025c5f867771eb79027c5e3bbe58d is already registered."
    t12 = S.bt_error_text("12", e12)
    ck("M10 代码 12 保留 infohash 原话，并指出先去删旧任务或停止做种",
       "代码 12" in t12 and "InfoHash" in t12 and "already registered" in t12
       and "停止做种" in t12 and "只做种" not in t12, t12)
    ck("M11 代码 13 的走法不会串到代码 12 上（两套坑的解法不同）",
       "truncated" not in t12 and "删掉" in t12 and "删掉" not in S.bt_error_text("3", "x"))
finally:
    AC.urlopen = _real_urlopen

# ---------- N. 自动分类规则（参照 qBittorrent 的分类：按种子里的名字决定落到哪个子目录）----------
_TOR_M = _benc({"info": {"name": "演示片（整包）", "files": [{"path": ["子目录", "1.mkv"], "length": 10}],
                         "piece length": 32768, "pieces": b"\x00" * 20}})
TOR_A_URI = (TMP / "a.torrent").as_uri()   # 种子内部名字：同一个内容.mp4；文件名却叫 a
RULES = [
    {"name": "剧集", "mode": "contains", "pattern": "1080p", "subdir": "剧集", "enabled": True},
    {"name": "按集号", "mode": "regex", "pattern": r"S\d{2}E\d{2}", "subdir": "综艺/2026", "enabled": True},
    {"name": "关掉的那条", "mode": "contains", "pattern": "同一个内容", "subdir": "不该出现", "enabled": False},
]

ck("N1 分类认的是种子内部的名字，不是本地文件名（pieces 里那个假 4:info 也没把它带偏）",
   S.bt_torrent_name(_TOR_A) == "同一个内容.mp4", S.bt_torrent_name(_TOR_A))
ck("N1b 多文件种子取顶层 name（整包目录名）",
   S.bt_torrent_name(_TOR_M) == "演示片（整包）", S.bt_torrent_name(_TOR_M))
ck("N2 种子读不出名字就回空串，不抛异常（截断的、非字典的都算）",
   S.bt_torrent_name(b"d8:announce") == "" and S.bt_torrent_name(b"") == ""
   and S.bt_torrent_name(b"not benc") == "")
ck("N3 子目录收成相对路径：正反斜杠都吃、多级保序",
   S.bt_rule_subdir("剧集\\2026/番剧")[0] == "剧集/2026/番剧", S.bt_rule_subdir("剧集\\2026/番剧"))
ck("N3b 开头写成 / 也落回下载目录里面（不许借绝对路径跑出去）",
   S.bt_rule_subdir("/etc")[0] == "etc", S.bt_rule_subdir("/etc"))
ck("N4 带 .. 或盘符的子目录当场拒绝，并把该怎么写讲出来",
   ".." in S.bt_rule_subdir("../out")[1] and "盘符" in S.bt_rule_subdir("C:/Windows")[1]
   and S.bt_rule_subdir("a/../b")[1] != "", str(S.bt_rule_subdir("a/../b")))
_bad_clean = S.bt_rules_clean([{"pattern": "", "mode": "contains", "subdir": "x"},
                              {"name": "r", "pattern": "[", "mode": "regex"},
                              {"pattern": "ok", "mode": "startswith"},
                              ["不是字典"],
                              {"pattern": "good", "subdir": "影片"}])
ck("N5 保存前逐条体检：缺关键词 / 正则写坏 / 匹配方式不认识 / 形状不对，各自点名第几条",
   len(_bad_clean[0]) == 1 and len(_bad_clean[1]) == 4
   and all(f"第 {i} 条" in m for i, m in zip((1, 2, 3, 4), _bad_clean[1])), str(_bad_clean))
ck("N5b 收下来的规则补上默认值（匹配方式默认「包含」、默认启用、名字缺省也补一个、匹配对象默认「名字」）",
   _bad_clean[0][0] == {"name": "规则 5", "pattern": "good", "mode": "contains",
                        "subdir": "影片", "scope": "name", "enabled": True}, str(_bad_clean[0]))
_sc_clean = S.bt_rules_clean([{"name": "链接的", "scope": "url", "pattern": "youtube.com", "subdir": "视频"},
                              {"name": "对象写错", "scope": "referer", "pattern": "x"},
                              {"name": "缺关键词的链接规则", "scope": "url", "pattern": "  "}])
ck("N5c 匹配对象只认「名字 / 链接」：写错的点名，链接规则缺关键词时那句说的是链接",
   len(_sc_clean[0]) == 1 and _sc_clean[0][0]["scope"] == "url"
   and "匹配对象" in _sc_clean[1][0] and "没写要匹配的链接" in _sc_clean[1][1], str(_sc_clean))
ck("N6 匹配不分大小写（种子里 1080P / 1080p 混着写是常态，分成两条规则只会越写越长）",
   S.bt_rule_match("Show.S01E01.1080P.x264", RULES)[0]["name"] == "剧集")
ck("N7 顺序就是优先级：两条都命中时按从上往下第一条定",
   S.bt_rule_match("演示片 1080p S02E03", RULES)[0]["name"] == "剧集"
   and S.bt_rule_match("演示片 S02E03", RULES)[0]["name"] == "按集号")
ck("N8 关掉的规则不参与（那条写的是同一个内容，开着就会命中）",
   S.bt_rule_match("同一个内容.mp4", RULES)[0] is None)
ck("N9 正则坏掉的那条只跳过自己，后面的规则照旧能命中，绝不把任务卡住",
   S.bt_rule_match("演示片 S02E03", [{"pattern": "[", "mode": "regex", "enabled": True},
                                     RULES[1]])[0]["name"] == "按集号")
ck("N9b 规则列表里混进非字典（手改 config.json 的常见事故）不炸",
   S.bt_rule_match("演示片 1080p", ["x", None, RULES[0]])[0]["name"] == "剧集")

_LOG = []


def _lg(m, level="info"):
    _LOG.append((level, str(m)))


_TOR_HIT = _benc({"info": {"name": "某剧 S01E02 1080p.mkv", "length": 10,
                           "piece length": 32768, "pieces": b"\x00" * 20}})
(TMP / "hit.torrent").write_bytes(_TOR_HIT)
_ref_hit = {"kind": "torrent-file", "name": "hit", "path": str(TMP / "hit.torrent"), "has_dn": False}
_d, _c, _w = S.bt_target_dir(_ref_hit, {"bt_auto_rules": RULES}, str(DL), _lg)
ck("N10 命中规则：落点变成下载目录下的子目录，回分类名，并说清撞了哪条",
   _d == str(Path(DL) / "剧集") and _c == "剧集" and "1080p" in _w, str((_d, _c, _w)))
ck("N10a 撞上的那条写的是正则时也照样报出缘故（命中来源要说得出口）",
   S.bt_target_dir({"kind": "magnet", "name": "Only.Show.S01E09.720p", "path": "", "has_dn": True},
                   {"bt_auto_rules": RULES}, str(DL), _lg)[1] == "按集号")
ck("N10b 日志里能看到「自动分类」和最终目录",
   any("自动分类" in m and "剧集" in m for _l, m in _LOG), str([m for _l, m in _LOG]))
ck("N10c 命中了规则但那条没填子目录：只打分类标记，目录仍用默认的（不擅自建目录）",
   S.bt_target_dir(_ref_hit, {"bt_auto_rules": [{"name": "只打标", "mode": "contains",
                                                 "pattern": "1080p", "subdir": ""}]},
                   str(DL), _lg)[:2] == (str(DL), ""))
ck("N10d 种子文件读不出内部名字时退回文件名，而不是干脆不分类",
   S.bt_rule_name({"kind": "torrent-file", "name": "种子 一号", "path": str(tp)}, _lg)[0] == "种子 一号",
   S.bt_rule_name({"kind": "torrent-file", "name": "种子 一号", "path": str(tp)}, _lg))
_LOG.clear()
_d2, _c2, _w2 = S.bt_target_dir({"kind": "magnet", "name": "x" * 12, "path": "", "has_dn": False},
                                {"bt_auto_rules": RULES}, str(DL), _lg)
ck("N11 磁力没带 dn：不硬猜、走默认目录，日志说明名字要等元数据",
   _d2 == str(DL) and _c2 == "" and any("元数据" in m for _l, m in _LOG), str([m for _l, m in _LOG]))
_LOG.clear()
_d3, _c3, _w3 = S.bt_target_dir({"kind": "magnet", "name": "随便一个片子 1080p", "path": "", "has_dn": True},
                                {"bt_auto_rules": RULES, "bt_auto_fallback": "没分类"}, str(DL), _lg)
ck("N12 命中磁力 dn：按规则落子目录，分类名带上",
   _d3 == str(Path(DL) / "剧集") and _c3 == "剧集", str((_d3, _c3)))
_d4, _c4, _w4 = S.bt_target_dir({"kind": "magnet", "name": "没人管的名字", "path": "", "has_dn": True},
                                {"bt_auto_rules": RULES, "bt_auto_fallback": "没分类"}, str(DL), _lg)
ck("N13 一条都没命中但有兜底目录：进兜底目录，分类标成「兜底」",
   _d4 == str(Path(DL) / "没分类") and _c4 == "兜底", str((_d4, _c4)))
_LOG.clear()
_d5, _c5, _w5 = S.bt_target_dir({"kind": "magnet", "name": "没人管的名字", "path": "", "has_dn": True},
                                {"bt_auto_rules": RULES, "bt_auto_fallback": "../跑出去"}, str(DL), _lg)
ck("N14 兜底目录本身写坏：只警告并留在默认目录，绝不跟着跑出去",
   _d5 == str(DL) and _c5 == "" and any("warning" == l and "兜底" in m for l, m in _LOG), str(_LOG))
_LOG.clear()
_d6, _c6, _w6 = S.bt_target_dir({"kind": "magnet", "name": "演示片 1080p", "path": "", "has_dn": True},
                               {}, str(DL), _lg)
ck("N15 没配规则时目录原样、一条日志都不多写（默认设置不该凭空多出一层目录）",
   _d6 == str(DL) and not _LOG and _c6 == "", str((_d6, _LOG)))

# ---------- N24~N33：同一张表里的「链接规则」—— 普通下载也按规则落子目录 ----------
URL_RULES = RULES + [
    {"name": "网页视频", "scope": "url", "mode": "contains", "pattern": "youtube.com",
     "subdir": "视频/YouTube", "enabled": True},
    {"name": "论坛直链", "scope": "url", "mode": "regex", "pattern": r"/bbs/\d+",
     "subdir": "论坛", "enabled": True},
]
ck("N24 一张表里两种规则各问各的：链接规则不会拿去比种子名",
   S.bt_rule_match("https://www.youtube.com/watch?v=1", URL_RULES, "url")[0]["name"] == "网页视频"
   and S.bt_rule_match("某剧 1080p", URL_RULES, "name")[0]["name"] == "剧集"
   and S.bt_rule_match("演示片 1080p", URL_RULES, "url")[0] is None,
   str([S.bt_rule_match("某剧 1080p", URL_RULES, "name")[0],
        S.bt_rule_match("演示片 1080p", URL_RULES, "url")[0]]))
ck("N24b 老规则没写 scope（手改 config.json / 旧配置文件升级上来）当作名字规则，不会误吃链接",
   S.bt_rule_match("https://x/y", [{"pattern": "x", "mode": "contains", "subdir": "z"}], "url")[0] is None
   and S.bt_rule_match("x", [{"pattern": "x", "mode": "contains", "subdir": "z"}], "name")[0] is not None)
ck("N25 磁力先问名字、名字没中才问链接（两条都撞得上时，名字那条赢）",
   S._rule_decide("某剧 S01E02 1080p", "https://www.youtube.com/watch?v=1", URL_RULES)[0]["name"] == "剧集"
   and S._rule_decide("没人管的名字", "https://www.youtube.com/watch?v=1", URL_RULES)[0]["name"] == "网页视频"
   and S._rule_decide("", "https://www.youtube.com/watch?v=1", URL_RULES)[0]["name"] == "网页视频",
   str(S._rule_decide("某剧 S01E02 1080p", "https://www.youtube.com/watch?v=1", URL_RULES)))
_LOG.clear()
_u1, _uc1, _uw1 = S.url_target_dir("https://www.youtube.com/watch?v=abc", {"bt_auto_rules": URL_RULES},
                                  str(DL), _lg)
ck("N26 普通下载命中链接规则：落到下载目录下的子目录，回分类名",
   _u1 == str(Path(DL) / "视频" / "YouTube") and _uc1 == "网页视频" and "youtube.com" in _uw1,
   str((_u1, _uc1, _uw1)))
ck("N26b 链接规则写成正则时也算得中（直链按路径归类是常见写法）",
   S.url_target_dir("https://bbs.example.com/bbs/123/f.mkv", {"bt_auto_rules": URL_RULES},
                    str(DL), _lg)[1] == "论坛直链")
_LOG.clear()
_u2, _uc2, _uw2 = S.url_target_dir("https://example.com/没撞上任何规则.mkv",
                                  {"bt_auto_rules": URL_RULES, "bt_auto_fallback": "没分类"},
                                  str(DL), _lg)
ck("N27 普通下载没命中：留在默认目录，绝不进兜底档（兜底只管磁力 / 种子，不然加一条链接规则就把整个下载目录改了地方）",
   _u2 == str(DL) and _uc2 == "" and not _LOG, str((_u2, _uc2, _LOG)))
_LOG.clear()
_u3, _uc3, _uw3 = S.url_target_dir("https://www.youtube.com/watch?v=abc",
                                  {"bt_auto_rules": URL_RULES}, str(Path(DL) / "手选的目录"), _lg,
                                  manual=True)
ck("N27b 用户手填了保存目录时手动的赢：不改落点，但日志仍写明本可以命中哪条",
   _u3 == str(Path(DL) / "手选的目录") and _uc3 == ""
   and any("手动指定" in m and "youtube.com" in m for _l, m in _LOG), str((_u3, _uc3, [m for _l, m in _LOG])))
_LOG.clear()
_u4, _uc4, _uw4 = S.url_target_dir("https://www.youtube.com/watch?v=abc", {"bt_auto_rules": RULES},
                                  str(DL), _lg)
ck("N27c 表里一条链接规则都没有时，普通下载原样走默认目录、一个字都不写（老设置不该有任何变化）",
   _u4 == str(DL) and _uc4 == "" and not _LOG, str((_u4, _uc4, _LOG)))
ck("N28 判断「手动指定」不能用非空：界面那格预填的就是全局目录",
   S._opts_dir_is_manual("", str(DL)) is False
   and S._opts_dir_is_manual(str(DL), str(DL)) is False
   and S._opts_dir_is_manual(str(DL) + "\\", str(DL)) is False
   and S._opts_dir_is_manual(str(Path(DL) / "别的"), str(DL)) is True)

# N16~N18 真跑一趟 _torrent_job：aria2 收到的目录必须就是分类后的目录
S._BT_WATCH.clear()
LOGS.rows.clear()
tA, (okA, _pA, _nA), acA, _prA = run_job(
    TOR_A_URI,
    [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"},
     {"status": "complete", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
    cfg=dict(BT_CFG, bt_auto_rules=RULES + [{"name": "演示", "mode": "contains",
                                             "pattern": "同一个内容", "subdir": "影片"}]))
ck("N16 本地种子交给 aria2 的目录就是分类目录（不是先默认目录再指望它自己搬）",
   acA.added_torrent and acA.added_torrent["dir"] == str(Path(DL) / "影片"), str(acA.added_torrent))
ck("N16b 任务上记下命中的分类名，界面才说得出为什么在这儿", tA.category == "演示", tA.category)
LOGS.rows.clear()
tB, (_okB, _pB, _nB), acB, _prB = run_job(
    TOR_A_URI,
    [{"status": "active", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
    cfg=dict(BT_CFG, bt_auto_rules=RULES + [{"name": "演示", "mode": "contains",
                                             "pattern": "同一个内容", "subdir": "影片"}],
             torrent_seed_only=True))
ck("N17 勾了「只做种」就不改落点：成品在本来的位置，换目录只会让它报「找不到文件」",
   acB.added_torrent and acB.added_torrent["dir"] == str(DL), str(acB.added_torrent))
ck("N17b 这件事在运行日志里看得见，不是默默地不生效",
   any("只做种" in m and "自动分类" in m for _l, m in LOGS.rows), str([m for _l, m in LOGS.rows]))
LOGS.rows.clear()
tC, (_okC, _pC, _nC), acC, _prC = run_job(
    MAGNET32,
    [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"},
     {"status": "complete", "totalLength": "114", "completedLength": "114", "numPeers": "1", "speed": "0"},
     {"status": "complete", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
    cfg=dict(BT_CFG, bt_auto_rules=RULES, bt_auto_fallback="没分类"))
ck("N18 没带 dn 的磁力没名字可比：有兜底目录就先进兜底目录（照 qBittorrent 的「名字未知」那档）",
   acC.added_uri and acC.added_uri["dir"] == str(Path(DL) / "没分类"), str(acC.added_uri))
ck("N18b 日志说清是「此刻还没名字」，不是「这个名字没命中规则」",
   any("还没有可比的名字" in m for _l, m in LOGS.rows), str([m for _l, m in LOGS.rows]))
LOGS.rows.clear()
_tD, (_okD, _pD, _nD), acD, _prD = run_job(
    MAGNET32,
    [{"status": "active", "totalLength": "0", "completedLength": "0", "numPeers": "0", "speed": "0"},
     {"status": "complete", "totalLength": "114", "completedLength": "114", "numPeers": "1", "speed": "0"},
     {"status": "complete", "totalLength": "4096", "completedLength": "4096", "numPeers": "1", "speed": "0"}],
    raw_files,
    cfg=dict(BT_CFG, bt_auto_rules=RULES + [{"name": "按 tracker", "scope": "url", "mode": "contains",
                                             "pattern": "announce", "subdir": "种子"}]))
ck("N18c 没带 dn 的磁力也能按链接规则落点：这条链接里有 announce，链接规则把它接走了（不必等名字）",
   acD.added_uri and acD.added_uri["dir"] == str(Path(DL) / "种子"), str(acD.added_uri))
LOGS.rows.clear()


# N19~N21 接口层：保存时挡住非法规则、试跑接口说得中是哪条
class CapCfg:
    def __init__(self, data):
        self.data = data

    def save(self):
        self.saved = dict(self.data)


_old_cfg_n = S.cfg
try:
    S.cfg = CapCfg({"download_dir": str(DL)})
    try:
        S.api_set_config(S.ConfigBody(bt_auto_rules=[
            {"pattern": "", "mode": "contains"},
            {"name": "坏正则", "pattern": "[", "mode": "regex"}]))
        n19 = "没报错"
    except S.HTTPException as e:
        n19 = str(e.detail)
    ck("N19 非法规则存不下去，且点名第几条、错在哪（规则写歪会把整批下载带偏）",
       "第 1 条" in n19 and "第 2 条" in n19 and "存不下" in n19, n19)
    S.cfg = CapCfg({"download_dir": str(DL)})
    S.api_set_config(S.ConfigBody(bt_auto_rules=[
        {"name": "影片", "pattern": "1080P", "subdir": "影片\\下载中"}, {"pattern": "S01E01", "mode": "regex"}],
        bt_auto_fallback="其他/其他"))
    saved = S.cfg.saved.get("bt_auto_rules") or []
    ck("N20 合法规则存下来时已归一：子目录变相对斜杠、匹配方式补默认、兜底目录一并归一",
       len(saved) == 2 and saved[0]["subdir"] == "影片/下载中" and saved[0]["mode"] == "contains"
       and saved[1]["mode"] == "regex" and S.cfg.saved.get("bt_auto_fallback") == "其他/其他", str(saved))
    ck("N20b 没写子目录的规则也算合法：命中它只是打个分类标记，目录仍用默认的",
       saved[1]["subdir"] == "", str(saved[1]))

    S.cfg = CapCfg({"download_dir": str(DL), "bt_auto_rules": RULES + [
        {"name": "演示", "mode": "contains", "pattern": "同一个内容", "subdir": "影片"}],
        "bt_auto_fallback": "没分类"})
    g1 = S.api_torrent_rules_test(S.BtRuleTestBody(name="某部片子 1080P"))
    ck("N21 试跑按名字：说出命中哪条、落到哪，界面上当场就能验证",
       g1["matched"]["name"] == "剧集" and g1["dir"] == str(Path(DL) / "剧集")
       and "剧集" in g1["message"], str(g1))
    g2 = S.api_torrent_rules_test(S.BtRuleTestBody(url=TOR_A_URI))
    ck("N21b 试跑按链接：用的是种子内部的名字，且说清名字从哪来",
       g2["matched"]["name"] == "演示" and "种子文件内的名称" == g2["name_from"]
       and g2["dir"] == str(Path(DL) / "影片"), str(g2))
    g3 = S.api_torrent_rules_test(S.BtRuleTestBody(url=MAGNET32))
    ck("N21c 没带 dn 的磁力试跑不说「没命中」，而是说清此刻根本没有名字可比",
       g3["matched"] is None and "还没有可比的名字" in g3["message"]
       and g3["dir"] == str(Path(DL) / "没分类"), str(g3))
    g4 = S.api_torrent_rules_test(S.BtRuleTestBody(name="随便什么"))
    ck("N21d 都没命中时兜底目录讲明白，别让用户以为规则没生效",
       g4["matched"] is None and "兜底目录" in g4["message"], str(g4))
    S.cfg = CapCfg({"download_dir": str(DL)})
    g5 = S.api_torrent_rules_test(S.BtRuleTestBody(name="随便什么"))
    ck("N21e 一条规则都没配时直说「还没配规则」，而不是回一个看起来像结果的空对象",
       g5["matched"] is None and "还没配规则" in g5["message"]
       and g5["dir"] == str(DL), str(g5))
    try:
        S.api_torrent_rules_test(S.BtRuleTestBody(url="ftp://example.com/movie.mp4"))
        n22 = "没报错"
    except S.HTTPException as e:
        n22 = str(e.detail)
    ck("N22 既不是磁力 / 种子、也不是 http(s) 的链接仍然当场顶回去（这种地址程序本来就不接）",
       "magnet" in n22 and n22 != "没报错", n22)
    n22b = S.api_torrent_rules_test(S.BtRuleTestBody(url="https://example.com/a.torrent"))
    ck("N22b 网上的 .torrent 链接不再被拒：它走的是普通下载这条路，按链接规则给个结论就行（口径改了）",
       n22b["ok"] is True and n22b["matched"] is None
       and "普通下载链接" in n22b["name_from"] and n22b["dir"] == str(DL), str(n22b))
    try:
        S.api_torrent_rules_test(S.BtRuleTestBody())
        n23 = "没报错"
    except S.HTTPException as e:
        n23 = str(e.detail)
    ck("N23 名字和链接都没给时问一句要试什么", n23 != "没报错" and "试" in n23, n23)

    # 链接规则进了同一张表以后，试跑入口也得能吃网页链接（#206③）
    S.cfg = CapCfg({"download_dir": str(DL), "bt_auto_rules": RULES + [
        {"name": "网页视频", "scope": "url", "mode": "contains", "pattern": "youtube.com",
         "subdir": "视频/YouTube"},
        {"name": "按 tracker", "scope": "url", "mode": "contains", "pattern": "announce",
         "subdir": "种子"}],
        "bt_auto_fallback": "没分类"})
    h1 = S.api_torrent_rules_test(S.BtRuleTestBody(url="https://www.youtube.com/watch?v=abc"))
    ck("N29 试跑贴一条网页链接：说的是链接规则撞上了哪条、落到哪，并写明名字一栏为什么是空的",
       h1["matched"]["name"] == "网页视频" and h1["dir"] == str(Path(DL) / "视频" / "YouTube")
       and "普通下载链接" in h1["name_from"], str(h1))
    h2 = S.api_torrent_rules_test(S.BtRuleTestBody(url="https://example.com/没撞上的.mp4"))
    ck("N29b 网页链接没命中时那句要写清它不吃兜底目录（不然用户会以为兜底档会把普通下载也接住）",
       h2["matched"] is None and h2["dir"] == str(DL)
       and "兜底只管磁力" in h2["message"] and "链接规则" in h2["message"], str(h2))
    h3 = S.api_torrent_rules_test(S.BtRuleTestBody(
        url="magnet:?xt=urn:btih:" + "m" * 32 + "&dn=%E6%9F%90%E5%89%A7%20S01E02%201080p&tr=http%3A%2F%2Fx%2Fannounce"))
    ck("N29c 磁力带 dn 时先问名字规则：这条的名字撞上「剧集」，链接里那个 announce 规则不许抢",
       h3["matched"]["name"] == "剧集" and h3["dir"] == str(Path(DL) / "剧集"), str(h3))
    h4 = S.api_torrent_rules_test(S.BtRuleTestBody(
        url="magnet:?xt=urn:btih:" + "n" * 32 + "&dn=%E6%B2%A1%E4%BA%BA%E7%AE%A1&tr=http%3A%2F%2Fx%2Fannounce"))
    ck("N29d 名字没中才轮到链接规则：announce 撞上，落点是链接规则那条",
       h4["matched"]["name"] == "按 tracker" and h4["dir"] == str(Path(DL) / "种子"), str(h4))
    h5 = S.api_torrent_rules_test(S.BtRuleTestBody(url=MAGNET32))
    ck("N29e 没带 dn 的磁力此刻没有名字可比，但链接规则照样能接住它（这正是加 URL 规则的意义）",
       h5["matched"]["name"] == "按 tracker" and h5["dir"] == str(Path(DL) / "种子"), str(h5))
    h6 = S.api_torrent_rules_test(S.BtRuleTestBody(url="magnet:?xt=urn:btih:" + "p" * 32))
    ck("N29f 名字和链接都没命中、又是没带 dn 的磁力：那句要说清问的是两种规则、兜底档接的是这一类",
       h6["matched"] is None and "名字与链接的规则" in h6["message"]
       and h6["dir"] == str(Path(DL) / "没分类"), str(h6))
finally:
    S.cfg = _old_cfg_n

# ---------- 还原 ----------
S.cfg, S.log_mgr, S.queue.log, S._bt_client, S.bt_ensure, S.time = _REAL
S._BT_WATCH.clear()
import shutil  # noqa: E402

shutil.rmtree(TMP, ignore_errors=True)

print("\nTOTAL:", TOTAL, "FAILED:", len(FAILED))
if FAILED:
    print("FAILED:", " | ".join(FAILED))
sys.exit(1 if FAILED else 0)
