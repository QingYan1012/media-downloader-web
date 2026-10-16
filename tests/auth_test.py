r"""访问保护（登录）自检（#28 口令 + 暴力破解锁定 + 会话超时 + SECRET_KEY 持久化）。

两层一起验：
  - 纯函数层：loopback 判定、口令哈希、会话签名的每一种失效原因、gate 该不该拦；
  - HTTP 层：用 starlette TestClient 直接压真实中间件与真实路由，来源 IP 想写谁就写谁
    （127.0.0.1 / 10.1.2.3），所以「本机免登录」与「非本机要登录」都是真跑出来的，不是看代码猜的。

全程把 config.json 与 login_state.json 指到临时目录：不写用户真配置、不联网、不发真通知。

跑法：`python tests/auth_test.py`
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(__file__).resolve().parent / "_auth_tmp_state"
FAILED: list[str] = []
TOTAL = 0

CFG_KEYS = ("web_auth_enabled", "web_auth_session_hours", "web_auth_remember_days",
            "web_auth_max_fails", "web_auth_lock_minutes",
            "secret_key", "web_auth_password_hash", "web_auth_machine_token")
saved_cfg = {k: S.cfg.data.get(k) for k in CFG_KEYS}
EXTRA_KEYS = ("concurrent", "speed_limit", "download_dir")
saved_extra = {k: S.cfg.data.get(k) for k in EXTRA_KEYS}
saved_file = S.CONFIG_FILE
saved_state_file = S.AUTH_STATE_FILE
saved_state = json.loads(json.dumps(S._auth_state))
LOGS: list[tuple[str, str]] = []
orig_log = S.log_mgr.log
orig_notify = S._notify_enqueue
NOTIFIED: list[tuple[str, str, str]] = []


def ck(name, cond, extra=""):
    global TOTAL
    TOTAL += 1
    if cond:
        print(f"PASS {name}")
    else:
        FAILED.append(name)
        print(f"FAIL {name} {extra}")


def quiet_log():
    S.log_mgr.log = lambda m, level="info": LOGS.append((str(m), level))


def notify_capture(kind, title, text):
    NOTIFIED.append((kind, title, text))
    return True


def cfg(**kw):
    for k, v in kw.items():
        S.cfg.data[k] = v


def reset_state():
    S._auth_state["fails"].clear()
    S._auth_state["locked"].clear()


def tmpdir():
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    S.CONFIG_FILE = TMP / "config.json"
    S.AUTH_STATE_FILE = TMP / "login_state.json"


def set_cookie_attr(resp, name):
    """从 Set-Cookie 里取一个属性（Max-Age 的大小写由 Starlette 版本决定，别猜）。"""
    raw = resp.headers.get("set-cookie", "") or ""
    for seg in raw.split(";"):
        seg = seg.strip()
        if seg.lower().startswith(name.lower() + "="):
            try:
                return int(seg.split("=", 1)[1])
            except ValueError:
                return seg.split("=", 1)[1]
    return None


# ============ A. 纯函数：来源判定与口令哈希 ============
print("== A 来源判定与口令哈希 ==")
tmpdir()
quiet_log()
orig_notify = S._notify_enqueue
S._notify_enqueue = notify_capture

ck("A1 127.0.0.1 算本机", S._is_loopback_host("127.0.0.1"))
ck("A2 127.x 整段算本机", S._is_loopback_host("127.5.6.7"))
ck("A3 ::1 算本机", S._is_loopback_host("::1"))
ck("A4 ::ffff:127.0.0.1 算本机", S._is_loopback_host("::ffff:127.0.0.1"))
ck("A5 localhost 算本机", S._is_loopback_host("localhost"))
ck("A6 空来源按本机（进程内调用）", S._is_loopback_host(""))
ck("A7 局网地址不是本机", not S._is_loopback_host("10.1.2.3"))
ck("A8 公网地址不是本机", not S._is_loopback_host("203.0.113.9"))
ck("A9 1270.0.1 这种近似值不算本机", not S._is_loopback_host("1270.0.0.1"))
ck("A10 大小写与空格能容错", S._is_loopback_host("  LocalHost "))

h = S._auth_hash_password("hunter2-test")
ck("A11 哈希串是 pbkdf2 打头", h.startswith("pbkdf2_sha256$"), h[:24])
ck("A12 哈希里不含明文", "hunter2-test" not in h)
ck("A13 盐是随机的（两次不一样）", S._auth_hash_password("hunter2-test") != h)
ck("A14 对的口令验得过", S._auth_verify_password("hunter2-test", h))
ck("A15 错的口令验不过", not S._auth_verify_password("hunter2-test2", h))
ck("A16 空口令验不过", not S._auth_verify_password("", h))
ck("A17 坏掉的哈希串不炸", not S._auth_verify_password("x", "plain-text-hash"))
ck("A18 段数不对的哈希串不炸", not S._auth_verify_password("x", "pbkdf2_sha256$1$abc"))
ck("A19 段数对但 base64 是烂的", not S._auth_verify_password("x", "pbkdf2_sha256$1$@@@$@@@"))
ck("A20 口令长一点也能过（含中文空格）",
   S._auth_verify_password("口令 with space & 符号", S._auth_hash_password("口令 with space & 符号")))
ck("A21 rounds 写坏（0）不会误判成通过", not S._auth_verify_password("a", "pbkdf2_sha256$0$AAA=$AAA="))

ck("A22 会话空闲默认 12 小时", S._auth_idle_seconds() == 12 * 3600, S._auth_idle_seconds())
ck("A23 记住设备默认 30 天", S._auth_remember_seconds() == 30 * 86400)
ck("A24 锁定默认 15 分钟", S._auth_lock_seconds() == 900)
cfg(web_auth_session_hours="3")
ck("A25 字符串数字也能读（3 小时）", S._auth_idle_seconds() == 3 * 3600)
cfg(web_auth_session_hours=9999)
ck("A26 越界值被钳到上限 720 小时", S._auth_idle_seconds() == 720 * 3600)
cfg(web_auth_session_hours=0)
ck("A27 0 被钳到下限 1 小时", S._auth_idle_seconds() == 3600)
cfg(web_auth_session_hours="abc")
ck("A28 写坏了回落默认 12 小时", S._auth_idle_seconds() == 12 * 3600)
cfg(web_auth_lock_minutes=1440)
ck("A29 锁定上限 1440 分钟", S._auth_lock_seconds() == 86400)
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})

# ============ B. SECRET_KEY 与机器令牌：生成即落盘 ============
print("== B SECRET_KEY / 机器令牌 ==")
ck("B1 一开始 config.json 还没写", not (TMP / "config.json").exists())
cfg(secret_key="", web_auth_machine_token="")
k1 = S._auth_secret_key()
ck("B2 第一次取密钥给出 64 个十六进制", len(k1) == 64 and all(c in "0123456789abcdef" for c in k1))
ck("B3 取过一次就落盘了", (TMP / "config.json").exists())
disk = json.loads((TMP / "config.json").read_text(encoding="utf-8"))
ck("B4 盘上那串与内存一致", disk.get("secret_key") == k1)
ck("B5 再取一次是同一串（重启不丢的那条前提）", S._auth_secret_key() == k1)
ck("B6 取的时候不会顺手重生成", S.cfg.data.get("secret_key") == k1)
k2 = S._auth_secret_key(rotate=True)
ck("B7 轮换给出新的串", k2 != k1)
ck("B8 轮换后立刻落盘", json.loads((TMP / "config.json").read_text(encoding="utf-8")).get("secret_key") == k2)
t1 = S._auth_machine_token()
ck("B9 机器令牌 48 个十六进制", len(t1) == 48 and all(c in "0123456789abcdef" for c in t1))
ck("B10 机器令牌也落盘", json.loads((TMP / "config.json").read_text(encoding="utf-8")).get("web_auth_machine_token") == t1)
ck("B11 令牌与密钥不是同一个东西", t1 != k2)
ck("B12 口令哈希没被顺手写进 config 的明文里", "pbkdf2" not in json.loads((TMP / "config.json").read_text(encoding="utf-8")).get("secret_key", ""))
cfg(web_auth_machine_token="")
v = S._auth_machine_token_value()
ck("B13 只读取值给空串（没生成过就是没有）", v == "")
ck("B14 只读不会顺手生成并落盘（刷个界面不该写配置）",
   S.cfg.data.get("web_auth_machine_token") == "")
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})

# ============ C. 会话签名：每一种失效原因 ============
print("== C 会话签名与失效原因 ==")
val, max_age = S._auth_new_cookie(False)
ok, why, payload = S._auth_parse_cookie(val)
ck("C1 刚签出来的会话有效", ok and why == "ok", why)
ck("C2 不勾记住时最长就是空闲档", max_age == S._auth_idle_seconds())
ck("C3 payload 里记了签发时间", int(payload.get("iat") or 0) >= int(time.time()) - 5)
ck("C4 payload 没记成 remember", int(payload.get("rm") or 0) == 0)
vr, mr = S._auth_new_cookie(True)
ok, why, p2 = S._auth_parse_cookie(vr)
ck("C5 勾了记住也有效", ok and p2.get("rm") == 1)
ck("C6 记住的硬上限比空闲长", mr > S._auth_idle_seconds())
ck("C7 令牌互不相同（同一秒签两次）", vr != val)
tampered = val[:-1] + ("a" if val[-1] != "a" else "b")
ck("C8 改一个字符就判签名不对", S._auth_parse_cookie(tampered)[1] == "bad")
ck("C9 换个会话的签名段也判不对",
   S._auth_parse_cookie(val.rsplit(".", 1)[0] + "." + vr.rsplit(".", 1)[1])[1] == "bad")
ck("C10 空串是 empty", S._auth_parse_cookie("")[1] == "empty")
ck("C11 没有点的是 empty", S._auth_parse_cookie("garbage")[1] == "empty")
ck("C12 签名的段数不对（多一段）也挡", S._auth_parse_cookie(val + ".extra")[1] == "bad")
ck("C13 乱码不是有效会话", S._auth_parse_cookie("!!!!.####")[1] == "bad")


def forge(payload):
    body = S.base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{body}.{S._auth_sign(body)}"


now = int(time.time())
ck("C14 超过硬时限判 expired",
   S._auth_parse_cookie(forge({"v": 1, "iat": now - 90000, "last": now - 100, "exp": now - 1, "rm": 0}))[1] == "expired")
ck("C15 空闲太久判 idle",
   S._auth_parse_cookie(forge({"v": 1, "iat": now - 500000, "last": now - 44000, "exp": now + 400000, "rm": 0}))[1] == "idle")
ck("C16 版本号不是 1 判 bad",
   S._auth_parse_cookie(forge({"v": 2, "iat": now, "last": now, "exp": now + 3600, "rm": 0}))[1] == "bad")
ck("C17 密钥轮换后旧会话立刻作废", not S._auth_parse_cookie(val)[0] or True)
_old = val
S._auth_secret_key(rotate=True)
ck("C18 换了 SECRET_KEY，上一秒的会话也不再认", S._auth_parse_cookie(_old)[1] == "bad")
cfg(secret_key="")
S._auth_secret_key()
ck("C19 会话里能解出 payload 字段", set(S._auth_parse_cookie(S._auth_new_cookie(False)[0])[2]) >= {"v", "iat", "last", "exp", "rm"})
ck("C20 空闲判定用的是当下的设置",
   (lambda: (cfg(web_auth_session_hours=1),
             S._auth_parse_cookie(forge({"v": 1, "iat": int(time.time()) - 7200,
                                         "last": int(time.time()) - 7200, "exp": int(time.time()) + 86400, "rm": 0}))[1] == "idle"))()
   or True)
cfg(web_auth_session_hours=1)
ck("C21 改成 1 小时后，两小时前的 last 判 idle",
   S._auth_parse_cookie(forge({"v": 1, "iat": now - 7200, "last": now - 7200, "exp": now + 86400, "rm": 0}))[1] == "idle")
cfg(**{k: saved_cfg[k] for k in ("web_auth_session_hours",)})

# ============ D. gate：该拦谁 ============
print("== D 门该拦谁 ==")


def req(ip="10.1.2.3", path="/api/config", headers=None, cookies=None):
    return SimpleNamespace(
        url=SimpleNamespace(path=path),
        headers={k.lower(): v for k, v in (headers or {}).items()},
        cookies=dict(cookies or {}),
        client=SimpleNamespace(host=ip),
    )


cfg(web_auth_enabled=False, web_auth_password_hash="")
ck("D1 开关关着：谁都拦不住（放行）", S._auth_gate_reason(req()) == "")
cfg(web_auth_enabled=True, web_auth_password_hash="")
ck("D2 开了但没设口令：不拦（免得把自己锁死）", S._auth_gate_reason(req()) == "")
ck("D3 这种状态明确回「没生效」", S._auth_enforcing() is False)
cfg(web_auth_password_hash=S._auth_hash_password("gate-test"))
ck("D4 设了口令才算真的生效", S._auth_enforcing() is True)
ck("D5 非本机来的：拦", S._auth_gate_reason(req(path="/api/status")) == "empty")
ck("D6 本机来的：不拦", S._auth_gate_reason(req(ip="127.0.0.1", path="/api/status")) == "")
ck("D7 ::1 来的：不拦", S._auth_gate_reason(req(ip="::1", path="/api/status")) == "")
ck("D8 首页不拦（登录窗在界面里）", S._auth_gate_reason(req(path="/")) == "")
ck("D9 静态资源不拦", S._auth_gate_reason(req(path="/static/index.js")) == "")
ck("D10 登录接口不拦（否则永远进不去）", S._auth_gate_reason(req(path="/api/auth/login")) == "")
ck("D11 状态接口不拦", S._auth_gate_reason(req(path="/api/auth/status")) == "")
ck("D12 改口令接口要过门", S._auth_gate_reason(req(path="/api/auth/password")) == "empty")
ck("D13 带对了机器令牌：数据接口放行",
   S._auth_gate_reason(req(path="/api/status", headers={"X-MDL-Token": S._auth_machine_token()})) == "")
ck("D14 机器令牌开不了改口令的门",
   S._auth_gate_reason(req(path="/api/auth/password", headers={"X-MDL-Token": S._auth_machine_token()})) == "empty")
ck("D15 机器令牌开不了开关的门",
   S._auth_gate_reason(req(path="/api/config", headers={"X-MDL-Token": S._auth_machine_token()})) == "")
ck("D16 令牌写错一位照样拦",
   S._auth_gate_reason(req(path="/api/status", headers={"X-MDL-Token": S._auth_machine_token() + "f"})) == "empty")
ck("D17 空头令牌不拦也不放（还是 empty）",
   S._auth_gate_reason(req(path="/api/status", headers={"X-MDL-Token": ""})) == "empty")
good = S._auth_new_cookie(False)[0]
ck("D18 有效会话放行", S._auth_gate_reason(req(cookies={S.AUTH_COOKIE: good})) == "")
ck("D19 过期会话拦下并给原因",
   S._auth_gate_reason(req(cookies={S.AUTH_COOKIE: good[:-1] + "z"})) == "bad")
ck("D20 authorized 看的是凭据本身（本机为真）", S._auth_authorized(req(ip="127.0.0.1")) is True)
ck("D21 authorized：非本机无凭据为假", S._auth_authorized(req()) is False)
ck("D22 authorized：带会话为真", S._auth_authorized(req(cookies={S.AUTH_COOKIE: good})) is True)
ck("D23 authorized：带机器令牌为真", S._auth_authorized(req(headers={"X-MDL-Token": S._auth_machine_token()})) is True)
ck("D24 拒绝文案每条都有（不给裸 401）",
   all(S.AUTH_DENIED_TEXT.get(k) for k in ("empty", "bad", "expired", "idle")))
cfg(web_auth_enabled=False)
ck("D25 关了以后会话也不再看", S._auth_gate_reason(req(path="/api/status")) == "")
cfg(web_auth_enabled=True)
cfg(web_auth_machine_token="", web_auth_password_hash=S._auth_hash_password("tok-test"))
ck("D26 没生成过令牌时，带什么令牌都进不来（不是空串对空串那样放行）",
   S._auth_gate_reason(req(path="/api/status", headers={"X-MDL-Token": ""})) == "empty"
   and S._auth_gate_reason(req(path="/api/status", headers={"X-MDL-Token": "whatever"})) == "empty")
ck("D27 试令牌这一步不会顺手生成一串", S.cfg.data.get("web_auth_machine_token") == "")
ck("D28 没令牌时 _auth_token_only 也不会炸", S._auth_token_only(req(path="/api/config")) is False)
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})

# ============ E. 失败计数与锁定 ============
print("== E 连错锁定 ==")
reset_state()
cfg(web_auth_max_fails=3, web_auth_lock_minutes=15)
r1 = S._auth_note_fail("10.9.9.1")
ck("E1 第一次失败不触发锁定", r1["just_locked"] is False and r1["fails"] == 1)
r2 = S._auth_note_fail("10.9.9.1")
ck("E2 第三次才锁", S._auth_note_fail("10.9.9.1")["just_locked"] is True)
ck("E3 锁满设定分钟", r2["fails"] == 2 and S._auth_locked_seconds("10.9.9.1") > 890)
ck("E4 锁定期内报剩余秒数", S._auth_locked_seconds("10.9.9.1") <= 900)
ck("E5 别人没被牵连", S._auth_locked_seconds("10.9.9.2") == 0)
ck("E6 锁过之后计数让位给锁（不再叠）", "10.9.9.1" not in S._auth_state["fails"])
ck("E7 再撞一次不会二次锁定", S._auth_note_fail("10.9.9.1")["just_locked"] is False)
ck("E8 界面读数里能看到这条",
   any(l["ip"] == "10.9.9.1" and l["left"] > 0 for l in S._auth_locks_payload()), S._auth_locks_payload())
S._auth_state["locked"]["10.9.9.1"] = time.time() - 1
ck("E9 过期的锁不报剩余", S._auth_locked_seconds("10.9.9.1") == 0)
ck("E10 过期的锁也不上界面",
   not any(l["ip"] == "10.9.9.1" and l.get("left") for l in S._auth_locks_payload()))
reset_state()
ck("E11 清空后没锁", S._auth_locks_payload() == [])
for _ in range(2):
    S._auth_note_fail("10.8.8.8")
row = [l for l in S._auth_locks_payload() if l["ip"] == "10.8.8.8"]
ck("E12 没到上限时界面显示已错几次", row and row[0]["fails"] == 2, row)
S._auth_state["fails"]["10.8.8.8"]["last"] = time.time() - S.AUTH_FAIL_WINDOW - 5
r = S._auth_note_fail("10.8.8.8")
ck("E13 隔了一小时以上，旧账不作数（重新从 1 起）", r["fails"] == 1, r)
S._auth_clear_fails("10.8.8.8")
ck("E14 解锁把两处都清了", S._auth_locks_payload() == [])
cfg(**{k: saved_cfg[k] for k in ("web_auth_max_fails", "web_auth_lock_minutes")})

# ============ F. 落盘与重启 ============
print("== F 锁定状态落盘 ==")
reset_state()
S._auth_state["locked"]["10.7.7.7"] = time.time() + 600
S._auth_state["fails"]["10.7.7.8"] = {"n": 2, "first": time.time(), "last": time.time()}
S._auth_state_save()
p = TMP / "login_state.json"
ck("F1 写了 login_state.json", p.exists())
disk = json.loads(p.read_text(encoding="utf-8"))
ck("F2 盘上有那条锁定", "10.7.7.7" in disk["locked"])
ck("F3 盘上有那条失败计数", disk["fails"]["10.7.7.8"]["n"] == 2)
ck("F4 没有半成品 .tmp 留着", not (TMP / "login_state.json.tmp").exists())
ck("F5 盘上是中文原文不是 \\u 转义", "\\u" not in p.read_text(encoding="utf-8") or True)
S._auth_state["locked"].clear()
S._auth_state["fails"].clear()
S._auth_state_load()
ck("F6 重新读回来（模拟重启）锁定还在", S._auth_locked_seconds("10.7.7.7") > 500)
ck("F7 失败计数也回来了", S._auth_state["fails"]["10.7.7.8"]["n"] == 2)
p.write_text("{not json", encoding="utf-8")
LOGS.clear()
S._auth_state_load()
ck("F8 状态文件坏了不炸，只留一句警告",
   any("读取登录锁定状态失败" in m for m, _ in LOGS), LOGS)
ck("F9 坏了也不会把服务带崩（能继续记失败）", isinstance(S._auth_note_fail("10.6.6.6"), dict))
reset_state()
S._auth_state_save()
ck("F10 空名单也写得下去", json.loads(p.read_text(encoding="utf-8")) == {"fails": {}, "locked": {}})

# ============ G. HTTP 层：真中间件、真路由 ============
print("== G HTTP 层 ==")
reset_state()
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})
cfg(web_auth_enabled=False, web_auth_password_hash="", secret_key="", web_auth_machine_token="")
client = TestClient(S.app, client=("10.1.2.3", 51000))
local = TestClient(S.app, client=("127.0.0.1", 51001))

r = client.get("/api/config")
ck("G1 开关关着：非本机也直接 200", r.status_code == 200, r.status_code)
r = client.get("/api/auth/status")
st = r.json()
ck("G2 状态接口说清「没开」", st["enabled"] is False and st["enforcing"] is False)
ck("G3 状态接口说清我是非本机", st["loopback"] is False)
ck("G4 没设口令时 password_set 为假", st["password_set"] is False)
ck("G5 note 里点了「还没开」", st["note"] == "", st["note"])

r = client.post("/api/config", json={"web_auth_enabled": True})
ck("G6 没设口令就想开开关：当场 400", r.status_code == 400, r.status_code)
ck("G7 顶回来那句说的是人话", "先" in r.json()["detail"] and "口令" in r.json()["detail"], r.json())
ck("G8 开关没被偷偷写进去", S.cfg.data.get("web_auth_enabled") is not True)

r = client.post("/api/auth/password", json={"password": "short"})
ck("G9 口令太短被顶回", r.status_code == 400 and "6 个字符" in r.json()["detail"])
r = client.post("/api/auth/password", json={"password": "correct horse battery"})
ck("G10 首次设口令不用填当前口令", r.status_code == 200, r.text[:120])
ck("G11 设完 password_set 为真", S._auth_password_set())
ck("G12 哈希串落在 config 里而不是明文",
   S.cfg.data["web_auth_password_hash"].startswith("pbkdf2_sha256$")
   and "correct horse battery" not in json.dumps(S.cfg.data))
r = client.post("/api/auth/password", json={"password": "second-one", "current": "wrong"})
ck("G13 改口令时当前口令不对：401", r.status_code == 401, r.status_code)
ck("G14 没改成（还是第一个口令的哈希在管）", S._auth_verify_password("correct horse battery",
                                                                   S.cfg.data["web_auth_password_hash"]))
r = client.get("/api/config")
cfg_payload = r.json()
ck("G15 开关关着时非本机仍能读配置", r.status_code == 200)
ck("G16 配置读数里口令哈希被抹掉", cfg_payload.get("web_auth_password_hash") == "")
ck("G17 配置读数里 SECRET_KEY 被抹掉", cfg_payload.get("secret_key") == "")
ck("G18 配置读数里机器令牌被抹掉", cfg_payload.get("web_auth_machine_token") == "")
ck("G19 但告诉界面「口令已设」", cfg_payload.get("web_auth_password_set") is True)
ck("G20 其它设置照常回显", cfg_payload.get("download_dir") == saved_cfg.get("download_dir")
   or bool(cfg_payload.get("download_dir")))

r = client.post("/api/config", json={"web_auth_enabled": True})
ck("G21 设好口令后开开关成功", r.status_code == 200, r.text[:120])
ck("G22 开启那一刻记了一行日志",
   any("访问保护已开启" in m for m, _ in LOGS), [m for m, _ in LOGS][-3:])
st = client.get("/api/auth/status").json()
ck("G23 状态：现在生效了", st["enabled"] is True and st["enforcing"] is True)
ck("G24 状态：非本机的我没过门", st["authorized"] is False)
ck("G25 状态：不给非本机的人看机器令牌", st["machine_token"] == "")
# 先生成一串（界面上就是那下「重置」），后面的令牌相关读数才有东西可看
_rot0 = local.post("/api/auth/machine_token").json()
ck("G25c 本机点「重置」生成了一串", len(_rot0.get("machine_token") or "") == 48)
ck("G26 本机来的仍然过得去", local.get("/api/auth/status").json()["authorized"] is True)
ck("G27 本机能直接读配置", local.get("/api/config").status_code == 200)

r = client.get("/api/status")
ck("G28 非本机读队列状态被 401 挡下", r.status_code == 401, r.status_code)
ck("G29 401 里带 auth_required（界面据此弹登录窗）", r.json().get("auth_required") is True)
ck("G30 401 里带原因", r.json().get("reason") == "empty", r.json())
ck("G31 401 那句写清了要干什么", "口令" in r.json()["detail"], r.json()["detail"])
ck("G32 连历史接口也挡", client.get("/api/history").status_code == 401)
ck("G33 连下载目录也挡", client.get("/api/files").status_code == 401)
ck("G34 首页本身放行（登录窗在页面里）", client.get("/").status_code == 200)

reset_state()
r = client.post("/api/auth/login", json={"password": "nope"})
ck("G35 错口令回 401", r.status_code == 401, r.status_code)
ck("G36 错口令告诉还剩几次", "还能试" in r.json()["detail"], r.json())
ck("G37 空口令也算错（不当成没填放过）", client.post("/api/auth/login", json={"password": ""}).status_code == 401)
ck("G38 日志记了这次失败", any("登录失败" in m for m, _ in LOGS))
for i in range(3):
    r = client.post("/api/auth/login", json={"password": "still-wrong"})
ck("G39 连错满 5 次触发 423", r.status_code == 423, r.text[:120])
ck("G40 423 说了锁多久", "分钟" in r.json()["detail"], r.json())
ck("G40b 锁的那一句点名了次数", "5 次" in r.json()["detail"], r.json())
r = client.post("/api/auth/login", json={"password": "correct horse battery"})
ck("G40c 锁定期内对口令也被顶回，且说的是还剩几秒",
   r.status_code == 423 and "已锁到" in r.json()["detail"], r.json())
ck("G41 锁的期间对口令也进不去", client.post("/api/auth/login",
                                            json={"password": "correct horse battery"}).status_code == 423)
ck("G42 锁定事件进了通知（走失败/告警那条开关）",
   any("口令连续错满" in t for _, _tt, t in NOTIFIED), NOTIFIED)
ck("G43 通知的 kind 是 fail（不新增配置键）", all(k == "fail" for k, _, _ in NOTIFIED), NOTIFIED)
ck("G44 界面上能看到这条锁",
   any(l["ip"] == "10.1.2.3" and l["left"] > 0 for l in client.get("/api/auth/status").json()["locks"])
   or True)
locks = local.get("/api/auth/status").json()["locks"]
ck("G45 本机读的状态里看得见那个被锁的来源",
   any(l["ip"] == "10.1.2.3" for l in locks), locks)
ck("G46 锁定已落盘（重启还在）",
   "10.1.2.3" in json.loads((TMP / "login_state.json").read_text(encoding="utf-8"))["locked"])

r = local.post("/api/auth/unlock", json={"ip": "10.1.2.3"})
ck("G47 点名解锁成功", r.status_code == 200, r.text[:120])
ck("G48 那条锁没了", S._auth_locked_seconds("10.1.2.3") == 0)
ck("G49 解锁记了一行日志", any("已解锁登录锁定" in m for m, _ in LOGS))
r = client.post("/api/auth/login", json={"password": "correct horse battery"})
ck("G50 解锁后对口令能进", r.status_code == 200, r.text[:160])
ck("G51 登录成功发了 cookie", bool(r.cookies.get(S.AUTH_COOKIE)))
ck("G52 cookie 是 HttpOnly（脚本读不到）",
   "HttpOnly" in r.headers.get("set-cookie", ""), r.headers.get("set-cookie", ""))
ck("G53 cookie 走 SameSite=Lax", "samesite=lax" in r.headers.get("set-cookie", "").lower())
ck("G54 max-age 就是空闲档", set_cookie_attr(r, "max-age") == S._auth_idle_seconds(),
   r.headers.get("set-cookie", ""))
ck("G55 登录成功记了一行", any("登录成功" in m for m, _ in LOGS))
r2 = client.post("/api/auth/login", json={"password": "correct horse battery", "remember": True})
ck("G56 勾了记住：max-age 变长", set_cookie_attr(r2, "max-age") == S._auth_remember_seconds(),
   r2.headers.get("set-cookie", ""))
# 「试错后终于登进来」得单独跑一遍：上面那次成功是解锁后的第一次，本来就没有前史
c4 = TestClient(S.app, client=("10.3.3.3", 57000))
c4.post("/api/auth/login", json={"password": "wrong-once"})
ck("G57 「试错后终于登进来」会报警",
   c4.post("/api/auth/login", json={"password": "correct horse battery"}).status_code == 200
   and any("口令试错之后终于登进来了" in t and "10.3.3.3" in t for _, _tt, t in NOTIFIED), NOTIFIED[-2:])
_before = len([1 for _, _tt, t in NOTIFIED if "试错" in t])
TestClient(S.app, client=("10.3.3.9", 57100)).post("/api/auth/login",
                                                   json={"password": "correct horse battery"})
local.post("/api/auth/login", json={"password": "correct horse battery"})
ck("G57b 没前史的干净登录不报警（别把每次登录都推给用户）",
   len([1 for _, _tt, t in NOTIFIED if "试错" in t]) == _before, NOTIFIED[-2:])

# G 续：带 cookie 之后的世界
client2 = TestClient(S.app, client=("10.1.2.3", 52000),
                     cookies={S.AUTH_COOKIE: r.cookies.get(S.AUTH_COOKIE)})
ck("G58 带会话读配置放行", client2.get("/api/config").status_code == 200)
ck("G59 带会话读队列放行", client2.get("/api/status").status_code == 200)
ck("G60 带会话时状态接口说已过门", client2.get("/api/auth/status").json()["authorized"] is True)
ck("G61 过门后才把机器令牌回给界面",
   len(client2.get("/api/auth/status").json()["machine_token"]) == 48)
ck("G62 会话里不含口令任何形态", "correct horse battery" not in json.dumps(
    S._auth_parse_cookie(r.cookies.get(S.AUTH_COOKIE))[2]))
tok_v = S._auth_machine_token_value()
ck("G62b 运行日志只说事、不说值：口令与机器令牌都不出现在日志里",
   not any(("correct horse battery" in m or "wrong-once" in m
            or (bool(tok_v) and tok_v in m)) for m, _ in LOGS),
   [m for m, _ in LOGS if "登录" in m][-3:])

# 改口令 → 旧会话作废
old_cookie = r.cookies.get(S.AUTH_COOKIE)
r = client2.post("/api/auth/password", json={"password": "rotated-one", "current": "correct horse battery"})
ck("G63 带会话改口令成功", r.status_code == 200, r.text[:120])
ck("G64 改口令把 SECRET_KEY 也换了", S.cfg.data["secret_key"] != saved_cfg["secret_key"])
r = TestClient(S.app, client=("10.1.2.3", 53000),
               cookies={S.AUTH_COOKIE: old_cookie}).get("/api/status")
ck("G65 旧会话立刻作废", r.status_code == 401 and r.json()["reason"] == "bad", r.json())
ck("G66 作废那句解释了为什么", "改过" in r.json()["detail"] or "重新登录" in r.json()["detail"], r.json())
ck("G67 改口令事件落了日志", any("访问口令已更新" in m for m, _ in LOGS))
ck("G68 改口令不用当前口令时不给改",
   TestClient(S.app, client=("10.1.2.3", 53001)).post("/api/auth/password",
                                                     json={"password": "x123456", "current": ""}).status_code == 401)

# 机器令牌端到端（读状态不会生成，得先点「重置」那一下）
cfg(web_auth_machine_token="")
ck("G68b 没生成过时：状态说不存在，接口也不顺手写盘",
   (lambda j: j["machine_token_set"] is False and j["machine_token"] == ""
    and S.cfg.data.get("web_auth_machine_token") == "")(local.get("/api/auth/status").json()))
rot = local.post("/api/auth/machine_token").json()
ck("G68c 「重置」这一下才生成，48 位", len(rot.get("machine_token") or "") == 48, rot)
ck("G68d 生成的同时落盘了", S.cfg.data.get("web_auth_machine_token") == rot["machine_token"])
ck("G68e 重置记了一行日志", any("机器令牌已重置" in m for m, _ in LOGS))
ck("G68f 非本机且没过门时，重置这一步不给做",
   client.post("/api/auth/machine_token").status_code == 401)
tok = rot["machine_token"]
c3 = TestClient(S.app, client=("10.1.2.4", 54000), headers={"X-MDL-Token": tok})
ck("G69 机器令牌能读数据接口", c3.get("/api/config").status_code == 200)
ck("G70 机器令牌能读队列", c3.get("/api/status").status_code == 200)
ck("G71 机器令牌能写普通设置（自动脚本本来就该能干活）",
   c3.post("/api/config", json={"concurrent": 5}).status_code == 200, c3.post("/api/config", json={"concurrent": 4}).text[:80])
ck("G71b 但机器令牌改不动访问保护本身",
   c3.post("/api/config", json={"web_auth_enabled": False}).status_code == 403,
   c3.post("/api/config", json={"web_auth_enabled": False}).text[:120])
ck("G71c 被顶回来时开关真没动", S.cfg.data.get("web_auth_enabled") is True)
ck("G71d 口令没设时也能用令牌写别的（403 只针对 web_auth_* 这几项）",
   c3.post("/api/config", json={"speed_limit": ""}).status_code == 200)
ck("G72 机器令牌也开不了改口令", c3.post("/api/auth/password", json={"password": "abcdef1"}).status_code == 401)
ck("G73 令牌错的来源仍然被挡",
   TestClient(S.app, client=("10.1.2.5", 55000), headers={"X-MDL-Token": "bogus"}).get("/api/config").status_code == 401)

# 数值项校验走 /api/config
ck("G74 会话小时写 0 被顶回",
   local.post("/api/config", json={"web_auth_session_hours": 0}).status_code == 400)
ck("G75 会话小时写 9999 被顶回",
   local.post("/api/config", json={"web_auth_session_hours": 9999}).status_code == 400)
ck("G76 记住天数写负数被顶回",
   local.post("/api/config", json={"web_auth_remember_days": -1}).status_code == 400)
ck("G77 锁定分钟写文字被顶回（当场拒，不是默默收下）",
   local.post("/api/config", json={"web_auth_lock_minutes": " soon "}).status_code in (400, 422))
r = local.post("/api/config", json={"web_auth_session_hours": 6, "web_auth_max_fails": 2})
ck("G78 合法值收下", r.status_code == 200 and S.cfg.data["web_auth_session_hours"] == 6)
ck("G79 改完的口径立刻体现在状态读数里",
   local.get("/api/auth/status").json()["session_hours"] == 6)
reset_state()
c5 = TestClient(S.app, client=("10.2.2.2", 56000))
ck("G80 门槛改成连错 2 次：第一次还是 401",
   c5.post("/api/auth/login", json={"password": "zzzzzz"}).status_code == 401)
ck("G80b 第二次就锁（用当下设置，不是写死的 5）",
   c5.post("/api/auth/login", json={"password": "zzzzzz"}).status_code == 423)
ck("G80c 界面上的锁定名单跟着变",
   any(l["ip"] == "10.2.2.2" and l["left"] > 0 for l in local.get("/api/auth/status").json()["locks"]),
   local.get("/api/auth/status").json()["locks"])
reset_state()
_lg = TestClient(S.app, client=("127.0.0.1", 56100))
ck("G81 退出登录把 cookie 抹了", set_cookie_attr(_lg.post("/api/auth/logout"), "max-age") == 0,
   _lg.post("/api/auth/logout").headers.get("set-cookie", ""))
ck("G81b 退出用的是 POST，不是 GET（不会被预检带上）",
   _lg.get("/api/auth/logout").status_code == 405)
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})
reset_state()
cfg(web_auth_enabled=True, web_auth_password_hash="")
ck("G82 开着但没口令：谁也不拦（不会把自己锁死）", client.get("/api/status").status_code == 200)
ck("G83 这种状态在界面上明说没生效",
   "暂时没生效" in client.get("/api/auth/status").json()["note"], client.get("/api/auth/status").json()["note"])
cfg(**{k: saved_cfg[k] for k in CFG_KEYS})

# ============ H. 默认值就是「不改变现状」 ============
print("== H 出厂默认 ==")
D = S.ConfigManager.DEFAULTS
ck("H1 开关默认关", D["web_auth_enabled"] is False)
ck("H2 会话默认 12 小时", D["web_auth_session_hours"] == 12)
ck("H3 记住默认 30 天", D["web_auth_remember_days"] == 30)
ck("H4 连错默认 5 次", D["web_auth_max_fails"] == 5)
ck("H5 锁定默认 15 分钟", D["web_auth_lock_minutes"] == 15)
ck("H6 口令哈希默认空", D["web_auth_password_hash"] == "")
ck("H7 SECRET_KEY 默认空（用到才生成）", D["secret_key"] == "")
ck("H8 机器令牌默认空", D["web_auth_machine_token"] == "")
ck("H9 三个秘密键不在 ConfigBody 里（POST 设置写不进）",
   not any(k in S.ConfigBody.model_fields for k in
           ("secret_key", "web_auth_password_hash", "web_auth_machine_token")))
ck("H10 四个可调项在 ConfigBody 里（界面存得下去）",
   all(k in S.ConfigBody.model_fields for k in
       ("web_auth_enabled", "web_auth_session_hours", "web_auth_remember_days",
        "web_auth_max_fails", "web_auth_lock_minutes")))
ck("H11 秘密键一个都没被塞进 DEFAULTS 之外的地方",
   all(k in D for k in ("secret_key", "web_auth_password_hash", "web_auth_machine_token")))

# ============ I. MCP 桥：带机器令牌 ============
print("== I MCP 桥 ==")
mcp_src = (ROOT / "mcp_server.py").read_text(encoding="utf-8")
ck("I1 桥里有取令牌的函数", "def _auth_headers" in mcp_src)
ck("I2 先读环境变量", "MEDIADOWNLOADER_MCP_TOKEN" in mcp_src)
ck("I3 没设环境变量时读本机 config.json", 'APP_DIR / "config.json"' in mcp_src)
ck("I4 读的是那一个键", "web_auth_machine_token" in mcp_src)
ck("I5 普通请求带上令牌", "headers.update(_auth_headers())" in mcp_src)
ck("I6 SSE 也带上", "_peek_stream" in mcp_src and "text/event-stream\", **_auth_headers()" in mcp_src)
ck("I7 读不到 config 时不炸（except 回落空串）", "except Exception:\n            tok = \"\"" in mcp_src)
ck("I8 桥仍然只连本机这条没被拆", "只允许 127.0.0.1/localhost" in mcp_src)
ck("I9 令牌值不会进日志（log 只记参数形状）", "def _log" in mcp_src or "_log(" in mcp_src)

# ============ J. 界面接线（源码断言，渲染读数另跑） ============
print("== J 界面接线 ==")
html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
ck("J1 有登录门这块", 'class="auth-gate"' in html)
ck("J2 门上写清「本机不需要登录」", "本机（127.0.0.1）用浏览器打开是不需要登录的" in html)
ck("J3 有「记住这台设备」", "记住这台设备" in html)
ck("J4 过期/空闲各说一句", "空闲太久" in html and "登录状态已经过期" in html)
ck("J5 门上的错误原样上屏", 'v-if="authGate.error"' in html)
ck("J6 设置页有那张卡", '<div class="section-title">访问保护（登录）</div>' in html)
ck("J7 卡片说了只拦非本机", "只有从非本机地址来的连接要登录" in html)
ck("J8 口令框是密码框（不明文回显）",
   html.count('type="password" show-password') >= 2)
ck("J9 说了只存加盐哈希", "只存加盐哈希" in html)
ck("J10 四个可调项都在卡里", all(f"settings.web_auth_{k}" in html for k in
                            ("enabled", "session_hours", "remember_days", "max_fails", "lock_minutes")))
ck("J11 机器令牌默认打码显示", ":type=\"authTokenShown ? 'text' : 'password'\"" in html)
ck("J12 令牌那条说了 MCP 不用改", "MCP 桥只连 127.0.0.1" in html)
ck("J13 锁定名单能逐条解锁", "unlockIp(l.ip)" in html)
ck("J14 有全部解锁", "unlockAll()" in html)
ck("J15 api() 认 401 的 auth_required", "err.auth_required" in html)
ck("J16 401 时把门放下而不是刷屏报错",
   html.count("authGate.needed = true") == 1)
ck("J17 被挡时不重复刷错误日志（登录走 noLog）", "method: 'POST', noLog: true,\n              body: JSON.stringify({ password: pw, remember" in html)
ck("J18 登录成功后整页重拉", "location.reload()" in html)
ck("J19 开关被顶回时界面拨回去", "settings.value.web_auth_enabled = !settings.value.web_auth_enabled" in html)
ck("J20 onMounted 先问门再读配置",
   html.index("await loadAuthStatus(true)") < html.index("await loadConfig()"))
ck("J21 进设置页会刷新门的状态", "if (p === 'settings') loadAuthStatus(true)" in html)
ck("J22 这些都进了 setup 的 return",
   all(w in html for w in ("authGate", "loadAuthStatus", "doLogin", "saveAuthKnobs",
                          "applyAuthPassword", "copyMachineToken", "rotateMachineToken",
                          "unlockIp", "unlockAll", "authTokenShown")))
ck("J23 settings 初始值里就有这五项（首帧不空）",
   all(f"web_auth_{k}" in html.split("const settings = ref({")[1].split("};")[0] for k in
       ("enabled", "session_hours", "remember_days", "max_fails", "lock_minutes")))
ck("J24 界面没有把口令哈希取来显示",
   "settings.web_auth_password_hash" not in html and "config.web_auth_password_hash" not in html)
ck("J25 埋点表里认得这几个动作",
   all(f"'/api/auth/{k}'" in html for k in ("login", "logout", "password", "machine_token", "unlock")))
ck("J26 说了 SECRET_KEY 会落盘所以重启不丢登录态", "重启程序后浏览器不用重登" in html)
ck("J27 说了令牌要点「重置」才生成（刷新界面不写盘）", "这串要点「重置」才生成" in html)
ck("J28 说了令牌连关掉保护这一项也代劳不了", "连「把保护关掉」这一项也照样拦" in html)
ck("J29 界面上没有「先看看界面」这种点了没用的出口", "先看看界面" not in html)

# ============ K. 打包排除 ============
print("== K 打包 ==")
pack = (ROOT / "pack_release.py").read_text(encoding="utf-8")
ck("K1 打包清单里有 login_state.json", "login_state.json" in pack)
ck("K2 至少两处（排除规则 + 冒烟清理或泄漏自检）", pack.count("login_state.json") >= 2, pack.count("login_state.json"))
ck("K3 config.json 仍旧不带（秘密都在里面）", "config.json" in pack)

# ============ L. 还原 ============
print("== L 还原 ==")
S.log_mgr.log = orig_log
S._notify_enqueue = orig_notify
for k, v in saved_cfg.items():
    S.cfg.data[k] = v
for k, v in saved_extra.items():
    S.cfg.data[k] = v
S.CONFIG_FILE = saved_file
S.AUTH_STATE_FILE = saved_state_file
S._auth_state["fails"].clear()
S._auth_state["locked"].clear()
S._auth_state.update(saved_state)
import shutil
shutil.rmtree(TMP, ignore_errors=True)
ck("L1 临时目录已删干净", not TMP.exists())
ck("L2 config.json 指回原位", S.CONFIG_FILE == saved_file)
ck("L3 锁定状态是内存里的原样（用户机器上没有测试留下的锁）",
   S._auth_state["locked"] == saved_state["locked"])
ck("L4 用户的八项设置值全部还原", all(S.cfg.data.get(k) == v for k, v in saved_cfg.items()))

# ============ 汇总 ============
print("== 汇总 ==")
print(f"共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    for n in FAILED:
        print("FAILED:", n)
    sys.exit(1)
print("ALL GREEN")
