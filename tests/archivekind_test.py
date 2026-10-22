# -*- coding: utf-8 -*-
"""下载记录按成品类别分文件：先下过视频，再点「仅音频」不该被算成已下载。

实测（2026-10-22，本机 bilibili BV1AHnB6NEhM）：14:13 下了视频（97,043,593 B 的 mkv），
14:14 与 14:15 两次点「仅音频」，日志都是
`本次未重新下载：….mkv 已在下载记录里` —— 下载目录里一个 m4a 都没有，
队列那几行显示的却是旧 mkv，看着就像「选了仅音频还是下成了视频」。
根因是 yt-dlp 的 download_archive 每行只有「站点键 + 视频 id」，不带格式。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="md_arch_state_")
os.environ["MEDIADOWNLOADER_STATE_DIR"] = STATE
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server as S  # noqa: E402

TOTAL = []
FAILED = []
SRC = (ROOT / "server.py").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")


def ck(name, cond, detail=""):
    TOTAL.append(name)
    if not cond:
        FAILED.append(name + ("  [%s]" % detail if detail else ""))
    print(("PASS " if cond else "FAIL ") + name + ("  [%s]" % detail if detail and not cond else ""),
          flush=True)


def main():
    dl = Path(STATE) / "Downloads"
    dl.mkdir(parents=True, exist_ok=True)
    cfg = dict(S.DEFAULTS if hasattr(S, "DEFAULTS") else {})
    cfg.update({"download_dir": str(dl), "skip_downloaded": True, "cookie": "", "proxy": ""})

    # 1) 文件名本身
    ck("A1 视频那一档的文件名一字未改（升级上来的人已有 46 条记录一条都不作废）",
       S.archive_filename(False) == "download_archive.txt", S.archive_filename(False))
    ck("A2 仅音频另开一份，不与视频共用",
       S.archive_filename(True) == "download_archive_audio.txt", S.archive_filename(True))

    # 2) 真拼一次 opts 字典（离线，不打网络）。注意：解析那一支（for_info=True）根本不挂下载记录，
    #    所以这里必须按下载那一支问，否则测的是「没挂」而不是「挂的是哪一份」
    E = S.engine
    URL = "https://www.bilibili.com/video/BV1AHnB6NEhM"
    ov = E._ydl_opts(cfg, for_info=False, url=URL)
    oa = E._ydl_opts(cfg, for_info=False, url=URL, audio_only=True)
    ck("A3 _ydl_opts 按 audio_only 分别落到两份记录文件上",
       str(ov.get("download_archive", "")).endswith("download_archive.txt")
       and str(oa.get("download_archive", "")).endswith("download_archive_audio.txt")
       and ov.get("download_archive") != oa.get("download_archive"),
       f"{ov.get('download_archive')} vs {oa.get('download_archive')}")
    off = dict(cfg, skip_downloaded=False)
    ck("A4 关掉「跳过已下载」时两份都不挂（这个开关的含义没被这次改动扩大）",
       "download_archive" not in E._ydl_opts(off, for_info=False, url="https://b.com/x")
       and "download_archive" not in E._ydl_opts(off, for_info=False, url="https://b.com/x",
                                                 audio_only=True), "")

    # 3) 真正下载那一支必须把 audio_only 传下去（解析那一支不需要，它不下东西）
    dl_call = SRC[SRC.index("opts = self._ydl_opts(cfg, for_info=False"):]
    ck("A5 下载那一支把 audio_only 传进 _ydl_opts（只改函数不改调用点，等于没改）",
       "audio_only=bool(audio_only)" in dl_call[:200], dl_call[:160].replace("\n", " | "))

    # 4) 清空下载记录要清两份
    (dl / "download_archive.txt").write_text("bilibili AAAA\n", encoding="utf-8")
    (dl / "download_archive_audio.txt").write_text("bilibili BBBB\n", encoding="utf-8")
    S.cfg.data["download_dir"] = str(dl)
    r = S.api_clear_archive()
    ck("A6 「清空下载记录」两份都删掉（只删视频那份，音频下次照样被跳过）",
       not (dl / "download_archive.txt").exists() and not (dl / "download_archive_audio.txt").exists()
       and sorted(r.get("cleared") or []) == ["download_archive.txt", "download_archive_audio.txt"],
       json.dumps(r, ensure_ascii=False))

    # 5) 界面那一格：点了「仅音频」不能把封装永久留在 m4a
    seg = HTML[HTML.index("async function downloadQualityPreset"):][:1600]
    ck("A7 清晰度这一格是「只改这一次」：进函数记住封装，结束后还原",
       "const fmtBefore = opts.value.format;" in seg and "opts.value.format = fmtBefore;" in seg,
       seg[:160].replace("\n", " | "))

    # 6) 那句话两份词表都在，且中文与后端字面一致（K3 全局也管，这里点名一次）
    cleared = [ln for ln in I18N.splitlines() if "'srv.files.archive_cleared'" in ln]
    ck("A8 清空记录那句改口成两份文件名，中英各一条、两条都点到 audio 那份",
       len(cleared) == 2 and all("download_archive_audio.txt" in ln for ln in cleared),
       [ln.strip()[:70] for ln in cleared])
    # 后端那句与词表是否逐字相同由 i18n_test 的 K3 全局管，这里不重复一遍（重复的那份只会先烂掉）

    print(f"\n== 汇总 ==\n共 {len(TOTAL)} 条，失败 {len(FAILED)} 条")
    for f in FAILED:
        print("FAIL " + f)
    import shutil
    shutil.rmtree(STATE, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
