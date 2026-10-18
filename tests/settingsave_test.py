#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设置写入通路（部分保存 + 恢复默认）离线自检。

钉的是三件事：
1. 界面只交「刚改的那几项」—— 整包回存会把这一页打开之后由别的入口（另一个页签、接口、
   程序自己）改过的键一起盖回去，而界面看不出来盖掉了什么。B 段先证明旧写法真会盖，再证明新写法不盖。
2. 默认值表只有后端那一份 `cfg.DEFAULTS`，「恢复默认」走的是和保存同一条闸门 `_apply_config`，
   而且这门锁本身和它的钥匙（口令哈希 / SECRET_KEY / 机器令牌 / CookieCloud 密钥）绝不被抹掉。
3. 界面上每一个 `v-model="settings.X"` 的键，后端都得真收得下、且在默认表里有名字 ——
   ConfigBody 没声明的键会在 `model_dump(exclude_none=True)` 那一步静默丢掉（本项目的 G2 那类 bug）。

只写 %TEMP%，不碰真实 config.json（`cfg` 整个换成假对象，`DEFAULTS` 挂真那份，测的就是这张表）。
跑法：PYTHONIOENCODING=utf-8 python tests/settingsave_test.py
"""
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as S  # noqa: E402

HTML = (Path(__file__).resolve().parent.parent / "static" / "index.html").read_text(encoding="utf-8")
# 界面文案搬进词表后，这里判的「界面上说了什么」要看词表的中文那一份：键名留在 HTML 里，字在 i18n.js 里
I18N = (Path(__file__).resolve().parent.parent / "static" / "i18n.js").read_text(encoding="utf-8")
_zh_blob = I18N[I18N.find("    zh: {"):I18N.find("\n    en: {")]
ZH = dict(re.findall(r"'([A-Za-z][\w.-]*)':\s*'((?:[^'\\]|\\.)*)'", _zh_blob))

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
    """DEFAULTS 挂真那一份：这一套测的就是「界面按后端这张表恢复」，抄第二份就测不到了。"""

    def __init__(self, data, defaults):
        self.data = data
        self.DEFAULTS = defaults
        self.saves = 0

    def save(self):
        self.saves += 1


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, msg, level="info", k="", kv=None):   # k/kv 是 #53 给日志加的可选消息键，这里不收
        self.rows.append((level, str(msg)))

    def texts(self):
        return [m for _l, m in self.rows]

    def last(self, needle):
        hits = [m for m in self.texts() if needle in m]
        return hits[-1] if hits else ""


class FakeQueue:
    def __init__(self):
        self.max_concurrent = 3
        self.pumps = 0

    def queue_names(self):
        return ["default"]

    def _pump(self):
        self.pumps += 1


FIELDS = set(S.ConfigBody.model_fields)
DEFAULTS = dict(S.cfg.DEFAULTS)
FORBIDDEN = tuple(S.CONFIG_RESET_FORBIDDEN)
TOKEN_REQ = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
# 真那份 config.json 的内容先记下来：整套自检只动假 cfg，末尾要证明它一个字节都没被写过
CFG_ON_DISK = Path(S.CONFIG_FILE)
CFG_BYTES_BEFORE = CFG_ON_DISK.read_bytes() if CFG_ON_DISK.exists() else None

_REAL = (S.cfg, S.log_mgr, S.queue, S.ffmpeg_mgr, S._auth_password_set, S._auth_token_only,
         S.CONFIG_FILE)
LOGS = FakeLog()
Q = FakeQueue()
TMP = Path(tempfile.mkdtemp(prefix="md_settingsave_"))
CFGFILE = TMP / "config.json"
S.CONFIG_FILE = CFGFILE           # 「恢复默认前留一份 config.json.bak-<时间>」写在这儿，不碰真那份


def disk(payload):
    """把「盘上此刻的 config.json」摆成给定的样子（备份对不对，比的就是这一份）。"""
    CFGFILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def baks():
    return sorted(p.name for p in TMP.glob("config.json.bak-*"))


def fresh(**over):
    """一份从 DEFAULTS 起步的干净配置，段与段之间不互相污染。返回的是同一个 dict，便于直接改。"""
    data = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
            for k, v in DEFAULTS.items()}
    data.update(over)
    S.cfg.data = data
    S.cfg.saves = 0
    LOGS.rows.clear()
    return data


def post(request=None, **over):
    """模拟界面那一下 POST：Body 只带交上去的字段，走 `api_set_config` 全链路。"""
    return S.api_set_config(S.ConfigBody(**over), request=request)


def reset(keys=None, all_=False, request=None):
    return S.api_reset_config(S.ConfigResetBody(keys=keys, all=all_), request=request)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except S.HTTPException as e:
        return e


S.log_mgr = LOGS
S.queue = Q
S.ffmpeg_mgr = SimpleNamespace(manual_path="", path="", available=False)
S._auth_password_set = lambda: True          # 默认：口令已经设过，开保护不该被拦
S._auth_token_only = lambda r: False         # 默认：不是机器令牌那一路
S.cfg = FakeCfg(dict(DEFAULTS), DEFAULTS)

try:
    # ------------------------------------------------------------ A 段：默认值表就是后端那一份
    defaultable = S._cfg_defaultable()
    ck("A1 可默认名单 = DEFAULTS ∩ ConfigBody − 那四样",
       set(defaultable) == (set(DEFAULTS) & FIELDS) - set(FORBIDDEN), f"defaultable={len(defaultable)}")
    ck("A2 ConfigBody 声明的键全都在 DEFAULTS 里（否则恢复默认会写进一个 None）",
       not (FIELDS - set(DEFAULTS)), str(sorted(FIELDS - set(DEFAULTS)))[:120])
    ck("A3 那四样不在可默认名单里", all(k not in defaultable for k in FORBIDDEN))
    ck("A4 门与钥匙的名单就是这四样",
       set(FORBIDDEN) == {"secret_key", "web_auth_password_hash",
                          "web_auth_machine_token", "cookiecloud_key"})

    r = S.api_config_defaults()
    items = {i["key"]: i for i in r["items"]}
    ck("A5 /api/config/defaults 的条目数和 count 对得上",
       r["count"] == len(r["items"]) == len(defaultable), f"count={r['count']}")
    ck("A6 全默认状态下差异为 0",
       r["differs"] == 0 and not any(i["differs"] for i in r["items"]), str(r["differs"]))
    ck("A7 每一项都带着默认值、现值与「是不是密钥」三个读数",
       all({"default", "value", "secret"} <= set(i) for i in r["items"]))
    ck("A8 那四样根本不出现在差异表里（界面上也就点不到它们）",
       not any(k in items for k in FORBIDDEN))
    ck("A9 掩码生成的 *_set 三个布尔不是配置项，没混进表里",
       not any(k.endswith("_set") and k not in DEFAULTS for k in items),
       str([k for k in items if k.endswith("_set")])[:80])
    ck("A10 表里带上了 forbidden 名单，界面能照着说清哪些动不到",
       set(r["forbidden"]) == set(FORBIDDEN))
    ck("A11 concurrent 的默认值就是 3，表里报的是同一个",
       items["concurrent"]["default"] == 3 and items["concurrent"]["value"] == 3)
    ck("A12 表里每一项的默认值都取得到（没有 None 混进来）",
       all(i["key"] in DEFAULTS for i in r["items"]))

    d = fresh(concurrent=9, proxy="http://127.0.0.1:7890")
    r = S.api_config_defaults()
    got = {i["key"]: i for i in r["items"]}
    ck("A13 改了值之后差异数如实跟上", r["differs"] == 2, str(r["differs"]))
    ck("A14 差异项报出「现值 → 默认值」两端",
       got["concurrent"]["value"] == 9 and got["concurrent"]["default"] == 3
       and got["proxy"]["value"].startswith("http://") and got["proxy"]["default"] == "")
    ck("A15 没动的项照样不在差异表里", not got["speed_limit"]["differs"])

    # ------------------------------------------------------------ B 段：部分写入 vs 整包回存
    d = fresh()
    snap = dict(d)                                  # 界面打开时读回来的那一份
    S.cfg.data["speed_limit"] = "2M"                # 之后别的入口改了它
    post(**{**snap, "proxy": "http://127.0.0.1:7890"})   # 旧写法：整包回存
    ck("B1 旧写法（整包回存）确实会把别的入口的改动盖回去 —— 这就是要修的那件事",
       S.cfg.data["speed_limit"] == "", repr(S.cfg.data["speed_limit"]))

    d = fresh()
    d["speed_limit"] = "2M"
    n0 = S.cfg.saves
    out = post(proxy="http://127.0.0.1:7890")       # 新写法：只交改动的那一项
    ck("B2 新写法只交改动项，别的入口刚改的 speed_limit 保住",
       S.cfg.data["speed_limit"] == "2M" and S.cfg.data["proxy"] == "http://127.0.0.1:7890",
       f'{S.cfg.data["speed_limit"]} / {S.cfg.data["proxy"]}')
    ck("B3 一次改动只落一次盘", S.cfg.saves == n0 + 1, f"{S.cfg.saves}")
    ck("B4 日志按改动项数写，不写值",
       LOGS.last("保存设置") == "[界面] 保存设置（1 项变更）", LOGS.last("保存设置"))
    ck("B5 回包带的是合并后的整份配置，界面据此刷新读数",
       out["ok"] and out["data"]["proxy"] == "http://127.0.0.1:7890"
       and out["data"]["speed_limit"] == "2M")
    ck("B6 没交的键一个都不动（包括那四样钥匙）",
       all(S.cfg.data[k] == DEFAULTS[k] for k in DEFAULTS
           if k not in ("proxy", "speed_limit")), "其余键原样")

    d = fresh(concurrent=3, proxy="", ui_theme="blue")
    out = post(concurrent=7, proxy="http://a:1", ui_theme="pink")
    ck("B7 一次交三项就记三项",
       S.cfg.data["concurrent"] == 7 and S.cfg.data["ui_theme"] == "pink"
       and LOGS.last("保存设置") == "[界面] 保存设置（3 项变更）", LOGS.last("保存设置"))
    ck("B8 三项都落到了 data 里，回包带的就是合并后的那份",
       out["data"]["proxy"] == "http://a:1" and out["data"]["concurrent"] == 7)

    # ------------------------------------------------------------ C 段：恢复默认（单项 / 顶回 / 令牌）
    d = fresh(concurrent=9, proxy="http://p:1", speed_limit="1M")
    r = reset(keys=["concurrent"])
    ck("C1 恢复单项只动那一项",
       S.cfg.data["concurrent"] == 3 and S.cfg.data["proxy"] == "http://p:1"
       and S.cfg.data["speed_limit"] == "1M", str(S.cfg.data["concurrent"]))
    ck("C2 回包点名恢复了哪几项、哪些没动", r["restored"] == ["concurrent"] and r["refused"] == [])
    ck("C3 恢复默认走的是同一条写入通路（落盘 + 日志）",
       S.cfg.saves == 1 and LOGS.last("恢复默认") == "[界面] 恢复默认：1 项（concurrent）",
       LOGS.last("恢复默认"))
    ck("C4 恢复走同一条闸门，所以队列也跟着改",
       Q.max_concurrent == 3, str(Q.max_concurrent))

    e = raises(reset, keys=["no_such_key_at_all"])
    ck("C5 认不出的键单独请求 → 400，并指名道姓",
       e is not None and e.status_code == 400 and "no_such_key_at_all" in e.detail, str(e.detail)[:90])
    ck("C6 认不出的键被归到「界面写不进去的键」这一类说法",
       e is not None and "界面写不进去" in e.detail, str(e.detail)[:90])

    e = raises(reset, keys=[])
    ck("C7 没说要恢复哪一项 → 400，不静默成功",
       e is not None and e.status_code == 400 and "没说要恢复哪一项" in e.detail)
    e = raises(reset, keys=[""])
    ck("C8 空字符串键名也算没说，不是「恢复一项空的」",
       e is not None and e.status_code == 400, str(e)[:80])

    d = fresh(concurrent=9, proxy="http://p:1")
    e = raises(reset, keys=list(FORBIDDEN))
    ck("C9 想恢复口令/SECRET_KEY/机器令牌/CookieCloud 密钥 → 400",
       e is not None and e.status_code == 400, str(e)[:80])
    ck("C10 顶回的话说清那是门锁本身，不是「键名打错了」",
       e is not None and "这门锁本身" in e.detail, str(e.detail)[:120])
    ck("C11 被顶回之后这四样一个都没动",
       all(S.cfg.data[k] == "" for k in FORBIDDEN), str({k: S.cfg.data[k] for k in FORBIDDEN}))

    d = fresh(secret_key="SK-KEEP", web_auth_password_hash="HASH-KEEP",
              web_auth_machine_token="MT-KEEP", cookiecloud_key="CC-KEEP", concurrent=9)
    r = reset(keys=["concurrent", "secret_key", "web_auth_password_hash"])
    ck("C12 混着交时：认得的恢复，认不出的进 refused，不整体失败",
       S.cfg.data["concurrent"] == 3 and r["restored"] == ["concurrent"]
       and sorted(r["refused"]) == sorted(["secret_key", "web_auth_password_hash"]),
       f'{r["restored"]} / {r["refused"]}')
    ck("C13 一键/单项都碰不到那四样：钥匙还是原来那把",
       S.cfg.data["secret_key"] == "SK-KEEP" and S.cfg.data["web_auth_password_hash"] == "HASH-KEEP"
       and S.cfg.data["web_auth_machine_token"] == "MT-KEEP"
       and S.cfg.data["cookiecloud_key"] == "CC-KEEP")
    ck("C14 refused 也进日志，数量对得上",
       LOGS.last("恢复默认").endswith("，另有 2 项没动（不在可默认名单里）"), LOGS.last("恢复默认"))

    S._auth_password_set = lambda: False
    fresh()
    e = raises(post, web_auth_enabled=True)
    ck("H1 同一道闸门还在：口令没设就开保护，照样当场顶回",
       e is not None and e.status_code == 400 and "先在「访问保护」里设好访问口令" in e.detail,
       str(e.detail)[:60])
    ck("H2 被顶回时配置一个字节都没写", S.cfg.saves == 0 and S.cfg.data["web_auth_enabled"] is False,
       f"saves={S.cfg.saves}")
    S._auth_password_set = lambda: True
    e = raises(post, video_encoder="zzz")
    ck("H3 非法编码模式照样顶回（恢复默认同一条路，不会绕过校验）",
       e is not None and e.status_code == 400)
    post(concurrent=99)
    ck("H4 越界的数照样夹住", S.cfg.data["concurrent"] == 10, str(S.cfg.data["concurrent"]))
    post(ui_theme="not-a-theme")
    ck("H5 认不出的主题退回默认，不是原样收下", S.cfg.data["ui_theme"] == "blue",
       str(S.cfg.data["ui_theme"]))

    S._auth_token_only = lambda r: True
    e = raises(reset, keys=["concurrent"], request=TOKEN_REQ)
    ck("C15 机器令牌不许把设置拧回默认 → 403",
       e is not None and e.status_code == 403 and "从界面登录" in e.detail, str(e.detail)[:80])
    e = raises(post, request=TOKEN_REQ, web_auth_enabled=True)
    ck("C16 机器令牌改访问保护那几项照样 403（这条线没被新入口稀释）",
       e is not None and e.status_code == 403)
    r = reset(keys=["concurrent"], request=None)
    ck("C17 界面（非令牌）照样能恢复", r["restored"] == ["concurrent"])
    S._auth_token_only = lambda r: False

    # ------------------------------------------------------------ D 段：一键恢复默认
    keeps = {"secret_key": "SK-KEEP", "web_auth_password_hash": "HASH-KEEP",
             "web_auth_machine_token": "MT-KEEP", "cookiecloud_key": "CC-KEEP"}
    d = fresh(**keeps, concurrent=8, ui_theme="dark", proxy="http://z:1", telegram_bot_token="TOK")
    before = sum(1 for i in S.api_config_defaults()["items"] if i["differs"])
    r = reset(all_=True)
    ck("D1 一键把差异全部抹平",
       S.cfg.data["concurrent"] == 3 and S.cfg.data["ui_theme"] == "blue"
       and S.cfg.data["proxy"] == "" and S.cfg.data["telegram_bot_token"] == ""
       and S.api_config_defaults()["differs"] == 0, f"before={before}")
    ck("D2 一键恢复的条数就是差异条数", len(r["restored"]) == before, f"{len(r['restored'])}")
    ck("D3 那四样钥匙不在一键的名单里，值原样留着",
       not any(k in r["restored"] for k in FORBIDDEN)
       and all(S.cfg.data[k] == v for k, v in keeps.items()),
       str({k: S.cfg.data[k] for k in FORBIDDEN}))
    e = raises(reset, all_=True)
    ck("D4 已经全是默认值时再来一次 → 400「没说要恢复哪一项」，不是假装成功",
       e is not None and e.status_code == 400 and "没说要恢复哪一项" in e.detail, str(e.detail)[:60])
    ck("D5 一键之后差异表立刻是空的（界面重新核对看得见结果）",
       S.api_config_defaults()["differs"] == 0)

    # ------------------------------------------------------------ E 段：表与列表是拷贝
    d = fresh(named_queues=["mine"], queue_windows={"default": "22:00-06:00"}, bt_auto_rules=[{"a": 1}])
    reset(keys=["named_queues", "queue_windows", "bt_auto_rules"])
    ck("E1 列表默认值给出去的是拷贝",
       S.cfg.data["named_queues"] == DEFAULTS["named_queues"]
       and S.cfg.data["named_queues"] is not DEFAULTS["named_queues"])
    S.cfg.data["named_queues"].append("把默认表写脏")
    ck("E2 改配置里那份不会脏 DEFAULTS 本身",
       DEFAULTS["named_queues"] == ["default", "night", "subscribe", "sniff"],
       str(DEFAULTS["named_queues"]))
    ck("E3 dict 与规则表同样给拷贝",
       S.cfg.data["queue_windows"] is not DEFAULTS["queue_windows"]
       and S.cfg.data["bt_auto_rules"] is not DEFAULTS["bt_auto_rules"]
       and S.cfg.data["queue_windows"] == {} and S.cfg.data["bt_auto_rules"] == [])
    d2 = fresh()
    ck("E4 DEFAULTS 全程没被这几轮写脏（差异重新算回 0）",
       S.api_config_defaults()["differs"] == 0, str(S.api_config_defaults()["differs"]))

    # ------------------------------------------------------------ F 段：密钥不外泄
    LEAKS = {"telegram_bot_token": "TOK-LEAK-CHECK", "hf_token": "HF-LEAK-CHECK",
             "aria2_secret": "AR-LEAK-CHECK", "serverchan_sendkey": "SC-LEAK-CHECK",
             "wecom_corp_secret": "WC-LEAK-CHECK", "cookiecloud_key": "CC-LEAK-CHECK",
             "secret_key": "SK-LEAK-CHECK", "web_auth_password_hash": "PH-LEAK-CHECK",
             "web_auth_machine_token": "MT-LEAK-CHECK"}
    d = fresh(**LEAKS)
    text = json.dumps(S.api_config_defaults(), ensure_ascii=False, default=str)
    ck("F1 默认值表里一个密钥值都不带", not any(v in text for v in LEAKS.values()),
       str([k for k, v in LEAKS.items() if v in text])[:80])
    got = {i["key"]: i for i in S.api_config_defaults()["items"]}
    ck("F2 名字像密钥的都标了 secret",
       all(got[k]["secret"] for k in ("telegram_bot_token", "hf_token", "aria2_secret",
                                      "serverchan_sendkey", "wecom_corp_secret")))
    ck("F3 密钥项的 value 与 default 两端都是空串",
       all(got[k]["value"] == "" and got[k]["default"] == ""
           for k in ("telegram_bot_token", "hf_token", "aria2_secret")))
    ck("F4 密钥填没填照样报得出（secret 项靠 filled，不靠值）",
       got["telegram_bot_token"]["filled"] is True and got["telegram_bot_token"]["differs"] is True)
    ck("F5 掩码那四样根本不在表里，谈不上泄", not any(k in got for k in FORBIDDEN))
    cfgtext = json.dumps(S.api_get_config(), ensure_ascii=False, default=str)
    ck("F6 GET /api/config 也不回报那四样（口令/SECRET_KEY/机器令牌/CC 密钥）",
       not any(LEAKS[k] in cfgtext for k in FORBIDDEN))
    ck("F7 掩码只留布尔读数，界面据此显示「已设置」",
       S.api_get_config()["web_auth_password_set"] is True
       and S.api_get_config()["secret_key_set"] is True
       and S.api_get_config()["cookiecloud_key_set"] is True)
    logtext = "\n".join(LOGS.texts())
    ck("F8 这几轮的日志里没有密钥值", not any(v in logtext for v in LEAKS.values()))

    # ------------------------------------------------------------ G 段：空值契约（界面为什么点名）
    ck("G1 交 null 等于没交（exclude_none）—— 所以界面要把这种项点名",
       S.ConfigBody(speed_limit=None).model_dump(exclude_none=True) == {})
    ck("G2 清空要靠空串，不是 null",
       S.ConfigBody(speed_limit="").model_dump(exclude_none=True) == {"speed_limit": ""})
    d = fresh(speed_limit="2M")
    before = dict(S.cfg.data)
    out = post()
    ck("G3 什么都不交时不写盘、不改配置",
       S.cfg.saves == 0 and S.cfg.data == before, f"saves={S.cfg.saves}")
    ck("G4 空 body 的回包仍然是 ok + 整份配置（界面不会当成失败）",
       out["ok"] and "data" in out)

    # ------------------------------------------------------------ I 段：界面那份脚本
    lc0 = HTML.index("async function loadConfig()")
    LOADCFG_BODY = HTML[lc0:HTML.index("function applyDark", lc0)]
    bound = set(re.findall(r'v-model="settings\.([a-z0-9_]+)"', HTML))
    ck("I1 界面上有控制项的键都读到了", len(bound) > 100, f"bound={len(bound)}")
    ck("I2 界面绑的键后端全收得下（ConfigBody 没声明的会静默丢掉 —— G2 那类 bug）",
       bound <= FIELDS, str(sorted(bound - FIELDS))[:160])
    ck("I3 界面绑的键在默认表里都有名字（否则恢复默认那栏点不动它）",
       bound <= set(DEFAULTS), str(sorted(bound - set(DEFAULTS)))[:160])
    m = re.search(r'const CFG_KEYS = \{(.*?)\n        \};', HTML, re.S)
    keys = set(re.findall(r'"([a-z0-9_]+)":', m.group(1))) if m else set()
    m2 = re.search(r'const CFG_RAW = \{(.*?)\n        \};', HTML, re.S)
    raws = set(re.findall(r'"([a-z0-9_]+)":', m2.group(1))) if m2 else set()
    labels = keys | raws
    ck("I4 人话名表拿到了（词表键一份、两边一样的厂商名一份）",
       len(labels) > 100 and keys and raws, f"词表键={len(keys)} 原样={len(raws)}")
    ck("I5 界面上有控制项的可默认键都叫得出名字",
       (bound & set(defaultable)) <= labels, str(sorted((bound & set(defaultable)) - labels))[:200])
    ck("I6 人话名表里没有多余键名（打错的键永远不会被用上）",
       labels <= set(DEFAULTS), str(sorted(labels - set(DEFAULTS)))[:160])
    ck("I7 叫不出名字时退回键名，不是显示 undefined",
       "const cfgLabel = k => (CFG_KEYS[k] ? tr(CFG_KEYS[k]) : CFG_RAW[k] || k);" in HTML)
    ck("I8 不再整包回存（settings.value 没有一处被直接 POST 出去）",
       "JSON.stringify(settings.value)" not in HTML)
    ck("I9 走的是「只交改动项」那一份 payload",
       "body: JSON.stringify(sent)" in HTML)
    ck("I10 快照锚在刚从后端读回配置的那一刻（所有赋值都定完才定表）",
       "markSaved();" in LOADCFG_BODY and "CFG_KNOWN.clear();" in LOADCFG_BODY
       and LOADCFG_BODY.rindex("settings.value.") < LOADCFG_BODY.rindex("markSaved();"))
    ck("I11 后端没这个键就不发（不发出去被 pydantic 悄悄丢掉）",
       "CFG_KNOWN" in HTML and "if (!CFG_KNOWN.has(k)) { unknown.push(k); continue; }" in HTML)
    ck("I12 快照没建立之前一律不写（拿默认值覆盖真配置是最坏情况）",
       "if (!CFG_SNAPSHOT.ready) return;" in HTML)
    ck("I13 半截文本会被顶回的那几栏不自动存",
       re.search(r"const AUTO_SAVE_OFF = new Set\(\[(.*?)\]\);", HTML, re.S) is not None
       and {"speed_windows", "run_window", "queue_windows", "ytdlp_extra_args",
            "subtitle_glossary", "bt_auto_rules", "bt_trackers", "web_auth_enabled"}
       <= set(re.findall(r"'([a-z0-9_]+)'",
                         re.search(r"const AUTO_SAVE_OFF = new Set\(\[(.*?)\]\);", HTML, re.S).group(1))))
    off = set(re.findall(r"'([a-z0-9_]+)'",
                         re.search(r"const AUTO_SAVE_OFF = new Set\(\[(.*?)\]\);", HTML, re.S).group(1)))
    ck("I14 不自动存的键都是真配置键", off <= set(DEFAULTS), str(sorted(off - set(DEFAULTS)))[:120])
    ck("I15 深 watch 挂着，且只走 pendingAutoSave 那道过滤",
       re.search(r"watch\(settings, \(\) => \{[\s\S]{0,900}\}, \{ deep: true \}\);", HTML) is not None
       and "pendingAutoSave()" in HTML)
    ck("I16 自动存是防抖的，不是每敲一个字写一次",
       "const AUTO_SAVE_MS = 700;" in HTML and "clearTimeout(autoSaveTimer)" in HTML)
    ck("I17 写正在飞时又改了 → 这一轮结束后补一轮，不把改动卡在界面上",
       "finally {\n              autoSaveBusy = false;\n              scheduleAutoSave();" in HTML)
    ck("I18 恢复默认之前先把没落地的改动写回去（否则紧随的 loadConfig 把它们冲掉）",
       re.search(r"const pend = pendingAutoSave\(\);\n\s*if \(pend\.length\) \{ try \{ await saveSettings\(true, pend\); \} catch", HTML)
       is not None)
    retm = HTML[HTML.rindex("\n        return {"):]
    missing = [n for n in ("autoSaveNote", "cfgDefs", "defRows", "defBrief", "defBusy", "cfgLabel",
                           "loadConfigDefaults", "resetKeys", "resetAllDefaults", "saveSettings")
               if not re.search(r'(^|[ ,\n])' + n + r'\s*[,}]', retm)]
    ck("I19 模板要用的名字都从 setup 里交出去了", not missing, str(missing))
    ck("I20 恢复默认那张卡真的渲染在设置页里",
       "tr('settings.resetAllBtn')" in HTML and 'v-for="it in defRows"' in HTML
       and "tr('settings.resetOneBtn')" in HTML and 'defBusy === it.key' in HTML)
    ck("I21 界面上说了哪些栏不自动存",
       "<b>{{ tr('settings.noAutoSaveBold') }}</b>{{ tr('settings.noAutoSaveList') }}" in HTML
       and "限速时段" in ZH.get("settings.noAutoSaveList", "")
       and "访问保护开关" in ZH.get("settings.noAutoSaveList", ""))
    ck("I22 界面文案点名了那四样动不到的钥匙",
       "tr('settings.defSecretBold')" in HTML
       and all(w in ZH.get("settings.defSecretBold", "")
               for w in ("口令", "签名密钥", "机器令牌", "CookieCloud 同步密钥")))
    ck("I23 差异表用的是后端算好的 differs，界面不再抄一份默认值",
       "cfgDefs.value.items" in HTML and "const DEFAULTS_JS" not in HTML)
    ck("I24 进设置页会重新核对默认值",
       re.search(r"if \(p === 'settings'\) \{[^\n]*loadConfigDefaults\(\);", HTML) is not None)
    ck("I25 界面说了恢复默认前会留一份配置备份（卡上与确认框都写了）",
       HTML.count("config.json.bak-") >= 2 and "r.backup ? tr('settings.defBackupAt'" in HTML
       and "改前的配置留在 {file}" in ZH.get("settings.defBackupAt", ""))
    ck("I26 一键恢复的确认框逐个点名将被清空的密钥，不写成一句「密钥类会被清空」",
       "defRows.value.filter(i => i.secret)" in HTML
       and "tr('settings.defAllSecLead'" in HTML
       and "会被清空的密钥（{n} 项）" in ZH.get("settings.defAllSecLead", ""))
    # 有控制项却不在 loadConfig 里回填 = 界面显示的是 JS 默认值，不是后端存着的那个。
    # #78 的活体跑就是这么抓到人声分离那五格的（配置存 cuda、页面开出来显示「自动」，
    # 而引擎其实一直照 cuda 跑 —— 只有显示在骗人）；顺带查出的那六个老键在紧接着的那次提交里补完了，
    # 所以这张表现在是空的。空着写死是故意的：谁想靠往这里加键名把 I27 蒙过去，得先让 I28 红一次。
    UNHYDRATED_KNOWN = set()
    hydr = set(re.findall(r"settings\.value\.([a-z0-9_]+)\s*=", LOADCFG_BODY))
    ck("I27 界面上有控制项的键都会被 loadConfig 回填（这张豁免表现在是空的）",
       not (bound - hydr - UNHYDRATED_KNOWN),
       "漏回填: %s" % sorted(bound - hydr - UNHYDRATED_KNOWN)[:8])
    ck("I28 豁免表必须保持空（往里加键名等于承认界面在骗人，先去补回填）",
       not UNHYDRATED_KNOWN, str(sorted(UNHYDRATED_KNOWN))[:120])

    # ------------------------------------------------------------ J 段：日志口径
    d = fresh(concurrent=9, telegram_bot_token="TOK-IN-LOG")
    post(proxy="http://secret-ish:1", telegram_bot_token="TOK-IN-LOG")
    line = LOGS.last("保存设置")
    ck("J1 日志只写条数，不写值",
       line == "[界面] 保存设置（2 项变更）" and "TOK-IN-LOG" not in line
       and "secret-ish" not in line, line)
    reset(keys=["telegram_bot_token"])
    ck("J2 恢复默认那行点名的是键名，不是值",
       LOGS.last("恢复默认").startswith("[界面] 恢复默认：1 项（telegram_bot_token）"),
       LOGS.last("恢复默认"))
    ck("J3 全程没有一行日志写过密钥值",
       "TOK-IN-LOG" not in "\n".join(LOGS.texts()))

    # ------------------------------------------------------------ K 段：恢复默认前留一份配置备份
    TMP_BAK_START = len(baks())
    disk({"concurrent": 9, "telegram_bot_token": "OLD-TOK-IN-BACKUP"})
    r = reset(keys=["concurrent"])
    ck("K1 单项、又不是密钥又不是路径：不留备份（点一下就堆一份没人看的文件没道理）",
       r["backup"] == "" and len(baks()) == TMP_BAK_START, f'{r["backup"]} / {baks()}')

    r = reset(keys=["telegram_bot_token"])
    ck("K2 恢复的是密钥类那一项：动手前留一份，文件名回给界面",
       r["backup"].startswith("config.json.bak-") and Path(TMP / r["backup"]).is_file(),
       r["backup"])
    ck("K3 备份里就是改动前盘上那一份（旧密钥还在，这才是能反悔的意思）",
       json.loads((TMP / r["backup"]).read_text(encoding="utf-8"))["telegram_bot_token"]
       == "OLD-TOK-IN-BACKUP")
    ck("K4 日志只说备份叫什么，不写里面的值",
       r["backup"] in LOGS.last("恢复默认") and "OLD-TOK-IN-BACKUP" not in "\n".join(LOGS.texts()),
       LOGS.last("恢复默认"))

    n0 = len(baks())
    r = reset(keys=["concurrent", "ui_theme"])
    ck("K5 一次恢复多项：也留", r["backup"] != "" and len(baks()) == n0 + 1, f"{r['backup']}")

    disk({"download_dir": "D:\\这里是我自己的目录"})
    r = reset(keys=["download_dir"])
    ck("K6 指向本机位置的单项（下载目录）也算「回不去」，一样留备份",
       r["backup"].startswith("config.json.bak-"), r["backup"])

    n0 = len(baks())
    disk({"x": 1})
    r1 = reset(keys=["telegram_bot_token", "hf_token"])
    r2 = reset(keys=["telegram_bot_token", "hf_token"])
    ck("K7 同一秒内连点两次，两份备份都在，后一份不盖掉前一份",
       len(baks()) == n0 + 2 and r1["backup"] != r2["backup"], f'{r1["backup"]} / {r2["backup"]}')

    CFGFILE.unlink()
    n0 = len(baks())
    r = reset(keys=["telegram_bot_token", "hf_token"])
    ck("K8 盘上还没有 config.json（第一次运行）：没东西可备份，不报错，恢复照常",
       r["backup"] == "" and len(r["restored"]) == 2 and len(baks()) == n0, str(r["restored"]))

    disk({"y": 2})
    _real_bak = S._edit_backup_path
    S._edit_backup_path = lambda p: (_ for _ in ()).throw(OSError("磁盘满了"))
    try:
        r = reset(keys=["telegram_bot_token", "hf_token"])
    finally:
        S._edit_backup_path = _real_bak
    ck("K9 备份没写成不该把「恢复默认」整个卡住：照样执行，并记一行说清没留成",
       r["backup"] == "" and len(r["restored"]) == 2
       and LOGS.last("备份没成").startswith("[界面] 恢复默认前想留一份配置备份没成：磁盘满了"),
       LOGS.last("备份没成"))

    ck("K10 每个恢复回包都带 backup 字段（界面读它，不该拿到 undefined）",
       "backup" in reset(keys=["concurrent"]))
    d = fresh(concurrent=9)
    ck("K11 备份这一手不会把真那份 config.json 扯进来",
       (CFG_ON_DISK.read_bytes() if CFG_ON_DISK.exists() else None) == CFG_BYTES_BEFORE)

    # ------------------------------------------------------------ L 段：打包清单跟得上
    pr = (Path(__file__).resolve().parent.parent / "pack_release.py").read_text(encoding="utf-8")
    ck("L1 带时间后缀的备份名不会被现有的「以 .bak 结尾」规则逮住 —— 所以打包要单列一条",
       re.compile(r"(?i)\.(pyc|pyo|log|zip|7z|rar|part|tmp|bak)$")
       .search("config.json.bak-20261015-100812") is None)
    ck("L2 打包时按文件名排掉 .bak-<数字> 这种备份",
       re.search(r"EXCLUDE_FILE_RE = re\.compile\([\s\S]{0,700}?\.bak-", pr) is not None)
    ck("L3 出包前的泄漏自查也把 .bak- 算进私密文件",
       re.search(r"leaks = \[[\s\S]{0,600}?\.bak-", pr) is not None)

    # ------------------------------------------------------------ Z 段：没碰到真东西
    ck("Z1 真那份 config.json 一个字节都没被写过",
       (CFG_ON_DISK.read_bytes() if CFG_ON_DISK.exists() else None) == CFG_BYTES_BEFORE,
       str(CFG_ON_DISK))
    ck("Z2 全程用的是假 cfg / 假日志 / 假队列",
       isinstance(S.cfg, FakeCfg) and S.log_mgr is LOGS and S.queue is Q)
finally:
    (S.cfg, S.log_mgr, S.queue, S.ffmpeg_mgr, S._auth_password_set, S._auth_token_only,
     S.CONFIG_FILE) = _REAL
    shutil.rmtree(TMP, ignore_errors=True)

print(f"== 汇总 ==\n共 {TOTAL} 条，失败 {len(FAILED)} 条")
if FAILED:
    for f in FAILED:
        print("FAIL " + f)
    sys.exit(1)
print("ALL GREEN")
sys.exit(0)
