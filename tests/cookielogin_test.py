# -*- coding: utf-8 -*-
r"""站点登录态健康标记的离线自检：什么时候记、什么时候清、接口读出什么形状。

起因：一份 Cookie 还能不能用，只有当场向站点取过一次才知道。所以这里不去猜有效期
（站点普遍不给登录凭据真实 expires，会话 Cookie 常是 0，按它报「快过期」只是噪声），
只把「这一平台刚有一次下载被判定为需要登录」记在内存里，标到「设置 → 多平台 Cookie」。

全程不联网、不起服务、不碰 config.json：cfg 与 log_mgr 换成假对象，cookies 目录拐进 Temp。
反向验证各盯一个「绿了也不代表生效」的坑：限流 / 拒绝 / 认不出来的一类都不许记，
没记时逐行必须读回 null，「清除标记」不许顺手写配置文件。

跑法：`python tests/cookielogin_test.py`
"""
from __future__ import annotations

import asyncio
import atexit
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import risk_control as R  # noqa: E402
import server as S  # noqa: E402

FAILED: list[str] = []
N = 0
TMP = Path(tempfile.mkdtemp(prefix="md_cookielogin_test_"))
atexit.register(shutil.rmtree, TMP, True)
LOGS: list[tuple] = []
SENTINEL = "SECRET-COOKIE-VALUE-DO-NOT-LOG"


def ck(name: str, cond, extra=""):
    global N
    N += 1
    ok = bool(cond)
    if not ok:
        FAILED.append(name)
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra else ""))


class FakeCfg:
    """只给 risk_note_for_failure 与那三个 Cookie 接口用：save() 只计数，绝不写盘。"""

    def __init__(self, data):
        self.data = data
        self.saves = 0

    def get(self, k, default=None):
        return self.data.get(k, default)

    def save(self):
        self.saves += 1


class FakeLog:
    def log(self, msg, level="info"):
        LOGS.append((level, str(msg)))


CFG = FakeCfg({"adaptive_throttle": False, "platform_cookies": {}})
_REAL = (S.cfg, S.log_mgr, S.COOKIES_DIR, dict(S._LOGIN_FLAGS))
S.cfg, S.log_mgr, S.COOKIES_DIR = CFG, FakeLog(), TMP / "cookies"
# 真程序在导入时就建好了 cookies 目录（server.py 顶部那批 _d），这里跟着建一次
S.COOKIES_DIR.mkdir(parents=True, exist_ok=True)
S._LOGIN_FLAGS.clear()


def mark(url: str, raw: str = "需要登录才能继续", task_id: str = "task0001"):
    """走真判定链记一枚标记（和下载失败时那条路完全同一个函数）。"""
    return S._login_flag_mark(url, R.classify_failure_text(raw), task_id)


# ---------------------------------------------------------------- A. 什么时候记
print("== A. 只有「被判定为需要登录」才记 ==")
S._LOGIN_FLAGS.clear()
note = S.risk_note_for_failure("ERROR: [BiliBili] BV1xx411c7mu: 需要登录才能观看此视频",
                              "https://www.bilibili.com/video/BV1xx411c7mu", "abcdef12345")
ck("A1 下载失败判成需要登录时，记下这一平台", list(S._LOGIN_FLAGS) == ["bilibili"], str(list(S._LOGIN_FLAGS)))
ck("A2 原有那句补话照样回给调用方（没改掉报错链）",
   "原因：" in note and "多平台 Cookie" in note, note[:80])
f = S._LOGIN_FLAGS.get("bilibili") or {}
ck("A3 带着时间 / 判定 / 域名 / 任务号四件",
   bool(f.get("at")) and f.get("kind") == R.LOGIN_REQUIRED
   and f.get("host") == "www.bilibili.com" and f.get("task_id") == "abcdef12", str(f))
ck("A4 动作里点名去哪配 Cookie", "多平台 Cookie" in str(f.get("action")), str(f.get("action")))
blob = json.dumps(f, ensure_ascii=False)
ck("A5 标记里不留完整链接（视频 id 不进这份状态）", "BV1xx411c7mu" not in blob, blob[:120])

S._LOGIN_FLAGS.clear()
S.risk_note_for_failure("ERROR: 访问过于频繁，请稍后再试", "https://www.bilibili.com/video/BV1", "t1")
ck("A6 限流不记 —— 它不是登录问题，标了只会把人支去重配 Cookie", S._LOGIN_FLAGS == {}, str(S._LOGIN_FLAGS))
S.risk_note_for_failure("ERROR: got HTTP error 403: Forbidden", "https://www.bilibili.com/video/BV1", "t1")
ck("A7 拒绝访问不记（私有 / 会员 / 地区限制都不等于 Cookie 坏了）",
   S._LOGIN_FLAGS == {}, str(S._LOGIN_FLAGS))
S.risk_note_for_failure("ERROR: 这条链接的签名对不上", "https://www.bilibili.com/video/BV1", "t1")
ck("A8 认不出来的一类不记（UNKNOWN 不许当结论）", S._LOGIN_FLAGS == {}, str(S._LOGIN_FLAGS))
S.risk_note_for_failure("ERROR: 需要登录才能继续", "", "t1")
ck("A9 没有链接就不知道该标谁，于是一条都不记", S._LOGIN_FLAGS == {}, str(S._LOGIN_FLAGS))
S.risk_note_for_failure("ERROR: 需要登录才能继续", "https://some-unknown-site.example/v/1", "t1")
ck("A10 认不出平台的链接不记（卡片上没有那一行，标了也没地方看）",
   S._LOGIN_FLAGS == {}, str(S._LOGIN_FLAGS))

print("== A11-A13 同一个平台连着挡、两个平台各记各的 ==")
S._LOGIN_FLAGS.clear()
LOGS.clear()
S.risk_note_for_failure("ERROR: 需要登录才能继续", "https://www.bilibili.com/video/BV1a", "task-aaaa")
S.risk_note_for_failure("ERROR: 请先登录，再继续搜索吧", "https://www.bilibili.com/video/BV1b", "task-bbbb")
ck("A11 同一平台连挡两次只留最新那一条，不叠一堆",
   len(S._LOGIN_FLAGS) == 1 and S._LOGIN_FLAGS["bilibili"]["task_id"] == "task-bbb",
   str(S._LOGIN_FLAGS["bilibili"]))
ck("A12 只在第一次说一句话（一批任务里同站能连挡几十次）",
   sum(1 for _, m in LOGS if "Cookie 登录态标记" in m) == 1, str(LOGS))
S.risk_note_for_failure("ERROR: 需要登录才能继续", "https://www.douyin.com/video/7123", "t9")
ck("A13 另一平台各记各的，互不覆盖", set(S._LOGIN_FLAGS) == {"bilibili", "douyin"}, str(set(S._LOGIN_FLAGS)))

# ---------------------------------------------------------------- B. 接口读出的形状
print("== B. GET /api/platforms/cookies 的形状 ==")
d = S.api_platform_cookies()
ck("B1 每一行都带 login_issue 这个键（界面按它决定标不标红）",
   all("login_issue" in i for i in d["platforms"]), str(len(d["platforms"])))
ck("B2 被挡过的两行读回判定，其余是 null",
   {i["platform"]: bool(i["login_issue"]) for i in d["platforms"]} ==
   {**{k: False for k in S.PLATFORM_LABELS if k != "default"}, "bilibili": True, "douyin": True})
ck("B3 顶层计数与逐行一致", d["login_issue_count"] == sum(1 for i in d["platforms"] if i["login_issue"]) == 2,
   str(d["login_issue_count"]))
ck("B4 卡片列的就是全部可选平台（default 那行界面没有，因此不参与）",
   len(d["platforms"]) == len(S.PLATFORM_LABELS) - 1, str(len(d["platforms"])))
S._LOGIN_FLAGS.clear()
d0 = S.api_platform_cookies()
ck("B5 反向：一枚都没记时逐行全 null、计数 0（红标不是常驻背景音）",
   d0["login_issue_count"] == 0 and all(i["login_issue"] is None for i in d0["platforms"]))

# ---------------------------------------------------------------- C. 三条清除路
print("== C. 动过 Cookie 就必须把标记抹掉 ==")
S._LOGIN_FLAGS.clear()
mark("https://www.bilibili.com/video/BV1", raw="需要登录", task_id="b1")
mark("https://www.douyin.com/video/7123", raw="需要登录", task_id="d1")
S.api_set_platform_cookie(S.PlatformCookieBody(platform="bilibili", source="browser", browser="edge"))
ck("C1 保存这一平台的 Cookie 来源会清掉它的标记",
   "bilibili" not in S._LOGIN_FLAGS and "douyin" in S._LOGIN_FLAGS, str(list(S._LOGIN_FLAGS)))
r = S.api_save_cookie_text(S.CookieTextBody(
    platform="douyin", content="# Netscape HTTP Cookie File\n" + SENTINEL))
ck("C2 粘贴保存那一路同样清标记，且真写进了 cookies 目录",
   "douyin" not in S._LOGIN_FLAGS and SENTINEL in Path(r["path"]).read_text(encoding="utf-8"), r["path"])
ck("C3 Cookie 内容一个字都不进这份状态与那几行日志",
   not any(SENTINEL in json.dumps(v, ensure_ascii=False) for v in S._LOGIN_FLAGS.values())
   and not any(SENTINEL in m for _, m in LOGS))
mark("https://www.youtube.com/watch?v=zz1", raw="需要登录", task_id="y1")
asyncio.run(S.api_upload_platform_cookie(platform="youtube", content="# Netscape HTTP Cookie File\nyt-行"))
ck("C4 上传文件那一路也清（三条写 Cookie 的路都得清，漏一条就留着假红标）",
   "youtube" not in S._LOGIN_FLAGS, str(list(S._LOGIN_FLAGS)))

mark("https://twitter.com/i/status/1", raw="需要登录", task_id="tw")
saves_before = CFG.saves
out = S.api_clear_cookie_flag(S.CookieFlagClearBody(platform="twitter"))
ck("C5 界面上的「清除标记」清得掉，并回 cleared=true",
   out["cleared"] is True and "twitter" not in S._LOGIN_FLAGS, str(out))
ck("C6 没有标记时按「清除标记」回 cleared=false，不谎报清掉了什么",
   S.api_clear_cookie_flag(S.CookieFlagClearBody(platform="twitter"))["cleared"] is False)
ck("C7「清除标记」只动内存里那枚标记，不写配置文件", CFG.saves == saves_before, f"{saves_before}→{CFG.saves}")
try:
    S.api_clear_cookie_flag(S.CookieFlagClearBody(platform="nosuchsite"))
    raised = ""
except S.HTTPException as e:
    raised = f"{e.status_code}:{e.detail}"
ck("C8 不认的平台当场拒绝，不静默成功", raised.startswith("400"), raised)

# ---------------------------------------------------------------- D. 那句话怎么说
print("== D. 日志与文案的口径 ==")
S._LOGIN_FLAGS.clear()
LOGS.clear()
mark("https://www.bilibili.com/video/BV1", raw="需要登录", task_id="x1")
line = next(m for _, m in LOGS if "Cookie 登录态标记" in m)
ck("D1 那句日志写着哪一平台、怎么清除、留到什么时候",
   "B站" in line and "重新导入" in line and "程序关闭" in line, line[:120])
ck("D2 日志级别是 warning（不是把它当成功记一笔）",
   any(m == line and lv == "warning" for lv, m in LOGS), str(LOGS))
mark("https://www.bilibili.com/video/BV1", raw="需要登录", task_id="x2")
ck("D3 反向验证：同一平台第二次记的日志不再重复出现（去掉那段守卫就会翻红）",
   sum(1 for _, m in LOGS if "Cookie 登录态标记" in m) == 1, str(len(LOGS)))

# ---------------------------------------------------------------- E. 前后端接线
print("== E. 接口与界面的名字对得上 ==")
paths = {getattr(r, "path", "") for r in S.app.routes}
ck("E1 清除标记这条路由真的挂上了",
   "/api/platforms/cookies/clear-flag" in paths, str(sorted(p for p in paths if "platforms" in p)))
html = (S.APP_DIR / "static" / "index.html").read_text(encoding="utf-8")
ck("E2 界面读的就是 login_issue / login_issue_count 这两个名字",
   "p.login_issue" in html and "cookieIssueCount" in html and "clearCookieFlag" in html)
ck("E3 界面调的清除接口与后端同名", "/api/platforms/cookies/clear-flag" in html)

print()
print(f"共 {N} 项，失败 {len(FAILED)} 项")
(S.cfg, S.log_mgr, S.COOKIES_DIR) = _REAL[:3]
S._LOGIN_FLAGS.clear()
S._LOGIN_FLAGS.update(_REAL[3])
print("FAILED:", ", ".join(FAILED) if FAILED else "none")
sys.exit(1 if FAILED else 0)
