# 版本更新说明

版本号真源在 `static/index.html` 的 `appVersion`（侧栏底部显示处），`pack_release.py` 的 `app_version()` 从同一处抓取，因此界面显示、README 标题、便携包名三者始终一致。
本仓库早前的便携包曾标为 2.6.x，自 v1.2.6 起重编为 1.x 版本线。

---

## v1.5.2 · 2026-10-22（本轮出包）

只收一笔修复：**「跳过已下载」不看成品类别，先下过视频的人点「仅音频」会什么都没下**（#136，细节与真 A/B 见下一节）。
v1.5.1 已经带上的 #135（CPU 上 float16 建模型直接抛）不在这一版的增量里，这里只是把发布物对上号。
另含一处对上一条判断的更正：日志里的 `30280` 是 B 站的 **192k 音频流**，不是我先前说的纯视频流 —— 所以「视频流 + 抽音频」
那种自相矛盾的请求并不存在，据此提议的「两排控件互斥置灰」也**没有做**。

`appVersion` 进到 `v1.5.2`（真源仍是 `static/index.html` 那一行）。全批自检 **64 套 bad=0**。

### 发布物

- **产物**：`dist\MediaDownloader-1.5.2-portable.zip` **230,645,942 B（220.0 MB）**，sha256
  `c9e543369f613c23b64d1581562083c6f7e720fdde06ae78d03bbe9d2ddbbe6e`，10,906 个条目，旁路 `.sha256` 同目录可
  `sha256sum -c` 核。包目录 567.5 MB：runtime 322.4、tools 234.5、static 3.0、chromaprint 4.0、docs 1.4、
  cookies 184 B（只有占位说明）。
- **打包自检**：随包清单 18 个依赖 + 3 个工具；必进包文件齐（static 13 项）；清掉 21 个 `__pycache__`；
  包内 15 个顶层模块 import 全过；包内 pip 装 → 导入通过；起包内服务冒烟，组件接口三档版本齐全、清单命中 12 项。
  清单记 `app = 1.5.2`、`python = 3.12.2`、`built = 2026-10-22 15:10`。
- **与源码逐条比对**：包内 59 个应用文件条目，其中 55 个与工作树逐字节一致（折叠 CRLF），4 处「包里有、工作树没有」
  是打包器生成的（`components_bundled.json` / `使用说明.txt` / `启动.bat` / cookies 的占位说明）；私密同名文件
  （`config.json` / `cookies.txt` / `history.json` / `library_cache.json` / `music_favorites.json` /
  `catcatch_rules.json` / `app.log` / `pack_release.py` / 两份 `download_archive*.txt`）零命中，应用文件里禁带目录
  零命中，`.pyc` 0 残留，分离引擎那个 `venv` 没进包（`/venv/` 零命中）。包内那份 `CHANGELOG.md` 是 CRLF
  （1947 行全带回车、裸 LF 0）、含 `v1.5.2` 这一节、且**不含本节的哈希**。
- **runtime 复用**：`pack_release.py` 与 `requirements.txt` 从 v1.5.1 起一字未动，所以 `--skip-runtime` 只重跑复制与
  那四道自检；runtime 整目录从 1.5.1 那份复制（9,795 个文件、0 失败）。顺带一个与 #134 有关的读数：包内 runtime
  根本没有 `numpy` / `numba` / `librosa`，所以那个上限脱钩的坑在便携包里不是开箱即坏，得自己在程序里更新过依赖才会碰上。
- **标签**：轻量标签 `v1.5.2` 指向 `c26d46c`（版本号进位与这一节那一笔，也就是这份包背后的字节）。
  `v1.5.1`（`6e3ac97`）与 `v1.5.0`（`fc2a9b4`）的 Release 资产原样留着，没有替换或删除。
- **推送与发布（同日补上）**：那一半小时里本机代理只对 CONNECT 回 200、隧道里的 TLS 握手全部断流（GitHub、PyPI、Hugging Face 一律如此），
  走明文 HTTP 它回 502，不走代理直连 GitHub 又被重置，所以当时只推到「包已建好」。代理上游恢复后按顺序做完了：
  `git push origin main v1.5.2`（远端 `main` 从 `9d33446` 进到 `05e0d04`，标签 `v1.5.2` 落在 `c26d46c`），
  再建 Release（id 420541780，https://github.com/QingYan1012/media-downloader-web/releases/tag/v1.5.2），
  zip 与 `.sha256` 两个资产都传上去、服务端收下的字节数与本地一致，然后从 `browser_download_url` 把包整个下载回来重算
  sha256 —— 与本地那份逐字节相同（`c9e54336…bbe6e`），发布脚本 8 条核对全绿。`v1.5.0`、`v1.5.1` 与它们的资产原样没动。
  当时还有一处对不上：**那份压缩包里的 `CHANGELOG.md` 是推送成功之前写的**，包内那一份写着「push 与 Release 待办」。
- **重打（同日，用户手动跑通 #137 之后）**：上面那句「对不上」连同 #137 一起，靠重打这一份包解决 —— 版本号仍是
  `v1.5.2`（`appVersion` 一字未动），换的是包内文本与那份多音轨功能本身。
- **重打后的读数**：`MediaDownloader-1.5.2-portable.zip` **230,660,015 B（220.0 MB）**，sha256
  `bcb00cf95ae0bc8a02e4c472d92c2cd508dbe5454a1c0d3e18171d27459de477`，10,906 个条目；应用文件 59 个，其中 55 个与工作树
  逐字节一致、4 个由打包器生成；私密同名文件与禁带目录零命中、`.pyc` 0、`/venv/` 没进包。包内那份 `CHANGELOG.md`
  是 CRLF（1987 行全带回车、裸 LF 0）且不含本节哈希。清单记 `app = 1.5.2`、`built = 2026-10-22 18:10`；打包那四道
  自检的原文读数与上一份一致（18 个依赖 + 3 个工具、static 13 项齐、清掉 21 个 `__pycache__`、15 个顶层模块 import
  全过、包内 pip 装 → 导入通过、冒烟三档版本齐全、清单命中 12 项）。这一份包背后的字节是 `7c7079d`
  （#137 本体 + 这次改口的发布说明），标签与 Release 资产都按它对齐。

---

## v1.5.2 之后 —— 文件页「封入音轨」：几条音频封进同一条视频

用户问「支持封装不同音轨文件至视频里面吗」。答案是当时不支持：`_ydl_opts` 走 `bv*+ba/b`，yt-dlp 默认只挑一条最佳音轨来合（全仓库没有 `audio_multistreams`），嗅探页那条手写合并也固定 `-map 0:v:0 -map 1:a:0?`，成品永远只有一条音轨；分轨出来的是各自独立的音频文件，混音台产的也是一条新的混合音频，都不回填进视频。这一笔把它补上（#137，口径四条由用户逐条点过）。

- **入口**：文件页视频行的「更多 → 封入音轨」（`v-if="isVideoFile(row)"`，音频行没这一项）。对话框先列「这条视频旁边的音轨」：它自己的分轨产物与同目录音频，各带一枚来源标签；右边按下载目录去翻别处的。每条选进来的轨给语言（九档）/ 轨名 / 编码三格，上下移就是成品里的轨序，「默认轨」那格决定播放器开场用哪一条。
- **后端**：`GET /api/files/audio_candidates` 与 `POST /api/files/mux_audio`，命令由纯函数 `build_mux_command()` 拼出来（自检直接比对参数表）。画面永远 copy、一律封成 mkv、成品另存 `原名.mux.mkv`、同名先 409 再要「覆盖旧成品」。
- **两处实测才知道的事**：`-disposition:a:N default=0` 是无效参数（ffmpeg 8.1 直接 `Unable to parse "disposition" option value` 退出），清标记要写值 `-default`；而且不写 disposition 时 mkv 每条轨的 default 都是 1，所以每条都得点名。源字幕是 mov_text 时 mkv 拒收，于是失败后不带字幕重来一遍，并在日志与完成提示里写明「成品只有画面与音轨」。
- **不猜的口径**：新轨的下标从「原片已有几条音轨」往后算，ffprobe 数不出来时报「没法判」并让人去修 FFmpeg，不按 0 处理 —— 按 0 会把语言与轨名贴到原片那条上，界面照样显示成功。
- **自检**：新增 `tests/audio_mux_test.py` 46 条（ffmpeg 换成桩，全程只写临时目录）；`tests/i18n_test.py` 的 H20 埋点表计数从 140 进到 141。活体两遍：一遍真 ffmpeg 走接口（17 条，成品用 ffprobe 逐条读回编码 / 语言 / 轨名 / 默认标记），一遍真点界面（18 条，沙箱实例，中英各截一张对话框）。
- **出包**：这一笔先不在 1.5.2 的第一份字节里；用户手动跑通之后重打了同一版号的包，所以它随 `v1.5.2` 的发布物一起出去（读数见上面那一节的「重打」条）。

---

## 仅音频不该被「视频那条记录」挡下来（v1.5.1 之后）

用户截图问：「选择了基础仅下载音频还是下载了封包好的视频是什么情况」。日志与磁盘对完，**不是下成了视频，那次根本没下**：

- 14:13:16 下过视频（`….mkv` 97,043,593 B）；14:14:37 与 14:15:34 两次点「仅音频」，请求都是对的（`指定格式: ba/bestaudio`、`目标容器=m4a`、`后期处理=FFmpegExtractAudio`），两次都回一句 `本次未重新下载：….mkv 已在下载记录里`；下载目录里**一个 m4a 都没有**，队列那几行显示的却是旧 mkv，看着就像"选了仅音频还是下成了视频"。
- **根因**：yt-dlp 的 `download_archive` 每行只有「站点键 + 视频 id」（本机那条就是 `bilibili BV1AHnB6NEhM`），**不带格式**。所以一个视频只要下过一次，之后任何请求 —— 包括仅音频 —— 都被它当成已完成、什么都不做就返回。

按用户定的口径「**不一致就重下**」改：

- `archive_filename(audio_only)` 把**仅音频那份记录单独写**（`download_archive_audio.txt`），视频那一档的文件名一字未改 —— 升级上来的人已有 46 条记录一条都不作废。判重的语义因此从「这个视频下过没有」变成「**这一类成品下过没有**」：先下视频再点仅音频会真下；同一档第二次点仍然跳过（分文件不等于每次都重下）。
- 「清空下载记录」两份都清（只清视频那份的话，音频下次照样被跳过），返回值多带一个 `cleared` 列出真删了哪几份；那句话中英两份都改口点名两个文件名。
- **顺带修一处界面状态泄漏**：点「仅音频」会把封装改成 `m4a`，而这一格用完只还原了 `force_format` 与 `audio_only`，**没还原封装** —— 之后再点视频档也会被抽成音频。现在进函数先记住、结束还原（这一格从头到尾都是「只改这一次」）。
- **一处更正**：我先前把日志里的 `指定格式: 30280` 说成「B 站的纯视频流」，据此推出了「视频流 + 抽音频」这种自相矛盾的请求，并提议把两排控件互斥置灰。实测 `30280` 是 **192k 音频流**（`vcodec none / acodec mp4a`），那两次都是正常的仅音频请求 —— 矛盾不存在，置灰那条前提不成立，**没做**。

- 自检：新增 `tests/archivekind_test.py` 8 条（两份文件名、真拼一次 opts 字典看挂的是哪份、关掉「跳过已下载」时两份都不挂、调用点确实把 `audio_only` 传了下去、清空删两份且回 `cleared`、界面那格记住并还原封装、那句话两份词表都点名两个文件）。全批 **64 套 bad=0**。
- 真 A/B（沙箱下载目录，不碰项目 `Downloads/`）：先塞一条 `bilibili BV1AHnB6NEhM` 进视频那份记录，再以 `audio_only=True` 跑真下载 —— **这次没被跳过**，走完解码并写入 `download_archive_audio.txt`，视频那份一字未增。（这一臂的成品是 `.mp4` 而不是 m4a，因为探针手搓的 cfg 没带上真实请求路径算出的那条格式串，与本笔修复无关。）

---

## v1.5.1 · 2026-10-22（已发布）

只为一笔修复出的补丁包：**CPU 上拿 float16 建 Whisper 模型会当场抛，而报错把人往「没装」的方向支使**（#135）。v1.5.0 的发布物里没有这一笔，所以单独走一次。

- **现象**：设置 `whisper_device=auto` + `whisper_compute=float16`，而本机主环境 torch 是 `+cpu` 构建 → 设备落在 CPU、档位仍是 float16。ctranslate2 4.8 在这种组合下**不是偷偷降级，而是在 `WhisperModel()` 那一步直接抛** `ValueError: Requested float16 compute type, but the target device or backend do not support efficient float16 computation.` 同一份 large-v3 本机实测：float16 5.2 秒抛错，int8 5.9 秒载入成功。是 13:02 那次把 faster-whisper 更到 1.2.1（连带 ctranslate2 4.8.2）才现形的 —— 旧版允许 CPU 用 fp16（内部转），新版不允许。
- **第二处不实**：失败之后最后一句是「未找到 faster-whisper 或 Whisper 可执行文件。请 pip install faster-whisper」，而它明明装着 1.2.1。
- **改法**：落到 CPU 的 `float16` / `int8_float16` 一律换 int8，并打一句带原档位名的警告；**真有 GPU 时 float16 保留**（那一档本来就是给人有卡的时候用的）；CPU + int8 不多嘴。CLI 兜底那句拆两支：装着但这一项没跑成 → 「原因见上面那行」，不再喊 pip install；真没装 → 照旧给安装指引。
- **警告那行不挂消息键**：这一式是函数参数里那份裸 `log(...)`，不在闸门扫的三式（`log_mgr.log` / `self.log` / `self.log.log`）里，挂上就是 K6 说的孤儿键 —— 等 #55 把这一式接进扫描再补。
- **自检**：新增 `tests/whispercompute_test.py` **12 条**（桩掉 `faster_whisper.WhisperModel`，只问最后递进去的是哪一档；**每发都清进程内那份 `_FW_MODEL_CACHE`** —— 不清的话第二轮起根本不再建模型，读到的是上一轮档位，是典型假绿）。全批 **63 套 bad=0**。真语音端到端（edge-tts 合成一段中文、CPU、设置故意留 float16）：警告一句 → `compute=int8` → `转写完成 (lang=zh, 2 句)`，文字逐字对。

### 发布物

- **产物**：`dist\MediaDownloader-1.5.1-portable.zip` **230,639,754 B（220.0 MB）**，sha256
  `b83c5b0deadd9bfc80d48b65a94f24213e33f09103715bc3f8b6b24203f0fbaa`，10,906 个条目，旁路 `.sha256` 同目录可
  `sha256sum -c` 核。包目录 567.5 MB：runtime 322.4、tools 234.5、static 3.0、chromaprint 4.0、docs 1.4、
  cookies 184 B（只有占位说明）。
- **打包自检**：随包清单 18 个依赖 + 3 个工具；必进包文件齐（static 13 项）；清掉 21 个 `__pycache__`；
  包内 15 个顶层模块 import 全过；包内 pip 装 → 导入通过；起包内服务冒烟，组件接口三档版本齐全、清单命中 12 项。
  清单记 `app = 1.5.1`、`python = 3.12.2`、`built = 2026-10-22 13:57`。
- **与源码逐条比对**：包内 42 个应用文件与工作树逐字节一致（折叠 CRLF），4 处「包里有、工作树没有」是打包器生成的；
  私密同名文件（`config.json` / `cookies.txt` / `history.json` / `library_cache.json` / `music_favorites.json` /
  `catcatch_rules.json` / `app.log` / `pack_release.py`）零命中，禁带目录零命中，`.pyc` 0 残留。
  包内那份 `CHANGELOG.md` 是 CRLF、含 `v1.5.1` 这一节、且**不含本节的哈希**（发布记录不写自己的摘要）。
- **runtime 复用**：`pack_release.py` 与 `requirements.txt` 从 v1.5.0 到现在一字未动，所以 `--skip-runtime`
  只重跑复制与那四道自检。
- **标签**：轻量标签 `v1.5.1` 指向 `6e3ac97`（版本号与这一节那一笔，也就是这份包背后的字节）。
  `v1.5.0`（`fc2a9b4`）与它那条 Release 的资产（230,635,022 B / `6ba9ae84…fe00`）原样留着，没有替换或删除。

---

## v1.5.0 · 2026-10-22（已发布）

`appVersion` 从 `v1.4.0` 升到 **`v1.5.0`**（真源只有 `static/index.html` 那一行，`pack_release.py` 的 `app_version()` 从同一处抓，界面显示 / 便携包名 / README 标题跟着一起走）。这一版收的是 `d922732`（上一轮发布物背后的那一笔）之后的 **32 笔**：一条大的功能线（分轨与音频分析的第二层）加一整批界面与日志收口。量上不是补丁 —— 六轨分离、分轨混音台、分离选择框、Demucs 模型补齐、拍点与段落结构、后端日志二十批挂键，任何一件都够单独一个次版本号。

**功能线（下面四节有逐条细节，位置沿用它们各自落地时写下的位置）**

- **#129 六轨与分轨混音台**：`htdemucs_6s` 出 bass / drums / guitar / other / piano / vocals，分轨范围三档（默认仍是「只取人声」，与这一项存在之前逐字相同）；混音台逐轨静音 / 独奏 / 音量、整段循环、按当前平衡导出。
- **#131 分离的选择框挪到动手那一步**：文件页「更多 → 分离人声」先弹引擎 / 模型 / 分轨范围 / 跑在哪四项，预填自设置而**不回头写设置**；顺带抓出一个真 bug —— 那份状态读数原先只在进语音页时才取，从不进语音页的人开对话框，两格模型下拉是空的。
- **#132 Demucs 的模型进「组件与依赖」**：能检测缺哪几个文件、能一键补齐，名单与校验值读自装好的那个包；模型没有独立版本号，所以这里只有「在不在」，也不进一键批次。
- **#133 音频分析的第二层**：拍点（beat-this）与段落结构（all-in-one）装进分离那个 venv 复用同一份 torch，产出并进同一份 JSON 与同一行日志；**librosa 的旧读数不静默替换**（合成 180 BPM 它报 89.1、真歌 76 报成 152、85.7 报成 112.3，而两个神经网络来源彼此差不到 1%）。

**界面与运行日志收口**

- **#55 后端运行日志第十五～三十四批**（20 批）：闸门里带 `srv.*` 键的调用点从 **144 涨到 370**，词表两份各 **3102 键**；其中 **#93a 片段键机制**（兜底词与状态词走 `misc.*` / `ccnote.*`）与 **#93b 条件句拆两处字面调用**是这一段的两个新口径，各先定口径再动代码。第十七批的前置一笔把 `self.log(...)` 这条接收式接上 `k`/`kv` 通道，一下解锁了原先不可见的 100 处（K10 现在读 113 处裸调用 / 送到 4 份适配口 / 送不到 0）。
- **#92** 网络重置的清空项名单改回语言中立的 key，英文界面不再印中文；**#80 续** 折叠栏里的展开钮回到 logo 那一行；**#98** 矮屏加一层紧凑留白，直播与语音页收进免滚动。
- **#96** 自检不再把日志写进项目根的 `app.log`：两处泄漏（`outbox_test.py` 的嵌套桩恢复错了对象、`bt_boost_test.py` 只换了 cfg 而接口仍走真 `log_mgr`），修完一轮全批 append **0 B**。

**这一版踩到并修好的环境级缺陷**：主环境 numpy 升到 2.5.x 而 numba 停在 0.65（上限 `<2.5`）会让 `import numba` 直接抛错，音频分析与声纹说话人分离整条坏掉 —— 这条本机**踩过两次**，上一轮按「退回 numpy 2.4.6」处理，这一轮按选择往前修（`numba 0.68.0` + `llvmlite 0.50.0`）。numba 不在「组件与依赖」表里、一键更新带着 numpy 单独走就还会脱钩，这一条记成 #134 未做。

**自检**：全批 **62 套 bad=0**，其中 `separator_test.py` **117 项**（J1–J9 选择框 / K1–K13 Demucs 模型 / L1–L23 拍点与结构）、`i18n_test.py` **517 项 FAILED: none**、`pagemount_test.py` 40 项；活体一律自起沙箱（`MEDIADOWNLOADER_STATE_DIR` + 空端口），分离对话框 12 条、Demucs 模型行 6 条、拍点与结构 14 条各自全过。

### 发布物

- **产物**：`dist\MediaDownloader-1.5.0-portable.zip` **230,635,022 B（220.0 MB）**，sha256
  `6ba9ae84805c92aa5e625357201cdca3e31706f5ddff96f6d5102afa1d60fe00`，10,906 个条目；
  旁路 `…zip.sha256`（在 `dist/` 里 `sha256sum -c` 可核）。包目录 567.5 MB：runtime 322.4、tools 234.5、
  static 3.0、chromaprint 4.0、docs 1.4、cookies 184 B（只有那句占位说明）。
- **打包自检**：随包清单 18 个依赖 + 3 个工具；「必进包的文件与目录齐了（static 里 13 项）」通过；清掉 21 个
  `__pycache__`；包内 15 个顶层模块 import 全过；包内 pip 装 → 导入通过（程序内依赖更新可用）；起包内服务冒烟，
  组件接口三档版本齐全、随包清单命中 12 项。清单里 `app = 1.5.0`、`python = 3.12.2`、`built = 2026-10-22 13:23`。
- **与源码逐条比对**：包内 **42 个应用文件与工作树逐字节一致**（折叠 CRLF 后比）；4 处「包里有、工作树没有」
  全是打包器自己生成的（`components_bundled.json`、cookies 占位说明、`使用说明.txt`、`启动.bat`）。
- **runtime 是复用的**：这一段 32 笔里 `pack_release.py` 与 `requirements.txt` 一字未动（`git log` 可查），
  所以沿用上版装好的内嵌 runtime 重装一遍没有意义，用 `--skip-runtime` 只重跑复制与那四道自检。
- **私密与状态扫描**：`config.json` / `cookies.txt` / `history.json` / `library_cache.json` /
  `music_favorites.json` / `catcatch_rules.json` / `app.log` / `pack_release.py` 零命中；禁带目录
  （`local_index` / `Downloads` / `Whisper` / `tg_session` / `browser_sniff_profile`）零命中；`.pyc` 0 残留。
- **标签**：轻量标签 `v1.5.0` 指向 `fc2a9b4`（版本号与这一版总览那一笔，也就是这份包背后的字节）。
  **本节里的字节数与 sha256 是包打完才回填的**，所以包内那份 `CHANGELOG.md` 不含本节 —— 这是
  「发布记录不写自己的摘要」那条口径的结果，不是漏写；同理包内 `CHANGELOG.md` 是 CRLF（Windows 记事本要读它）。
- **上一版原样留着**：`v1.4.0` 标签仍指 `d922732`，那条 Release 的资产是 230,529,549 B /
  `5f570ce7…88c57a`，没有改动或删除。

---

## 分轨：六轨模型与分轨混音台（同一轮内，参照 StemDeck）

有人问「StemDeck 这个能加吗」。核完差距只有两处值得拿：**六轨**与**多轨混音**，其余（它自带 FastAPI + 自己的 Python 运行时、700 MB～1.6 GB 的分发）和我们「venv 与权重都不进包」的口径冲突，不做集成、只借选型。它本身是 Apache-2.0，界面鸣谢名单里补了一条。

- **`htdemucs_6s` 进表的条件是这台机器真跑通**：4 秒合成片段、CPU、262 秒，落出 `bass / drums / guitar / other / piano / vocals` 六条各 705,644 B。`voice_tools.py` 那张表原来的注释写着「没验过的名字不给选项 —— 给了就是让人点下去报『模型下不下来』」，所以先验再列，`mdx23c` 那类仍然不给选项。
- **分轨范围三档，默认那档就是改动前的行为**：`demucs_stems` 取 `vocal` 时命令与从前逐字相同（仍带 `--two-stems vocals`，出「人声 + 伴奏」两条），`four` / `six` 才去掉那个参数让 Demucs 铺全轨。默认值 `vocal` 写进 `DEFAULTS`、`ConfigBody`、保存闸门与界面初值四处 —— 把默认改成多轨等于替每个老用户重跑一遍分离。
- **档与模型对不上在起线程之前就说破**：六轨只有 `htdemucs_6s` 出得来，界面那格直接置灰，后端再拒一次。跑完几分钟才发现拿回的轨数不对，是最亏的一种失败。
- **分轨混音台**（语音页新卡）：`GET /api/voice/stems` 按 `<曲名>/demucs/<模型>/<曲名>/*.wav` 精确取轨（整目录 rglob 会把同一首歌换模型跑过的两批同名轨一起端上来），并排掉自己产出的 `*-mix-*`；`POST /api/voice/mix` 用本机 ffmpeg 合成，静音的轨不进命令，导出 WAV（`pcm_s16le`）或 MP3（320k），成品写在首条轨旁边。
- **`amix` 关掉 `normalize`**：开着它会把每条轨按轨数等分压下去，人在界面上调好的平衡和写出来的文件就不是一个东西。第一版还翻过一次车 —— filter chain 之间少了 `;`，ffmpeg 直接判非法、接口 500。
- **音量条只做 0–100%，不做增益**：预览走 `element.volume`，它上不去 1；给一根能拉到 200% 的条就是骗人。要增益得换 Web Audio 的 GainNode，那一层留给以后。
- 「分离引擎」那一格的措辞从「Demucs（四轨，能出 `no_vocals`）」改成不写死轨数 —— 现在轨数由「分轨范围」决定。
- 自检：`tests/separator_test.py` 加 I1–I14（`--two-stems` 只出现一次、六轨只配 `htdemucs_6s`、filter chain 用 `;`、自产文件被排除、混音台七个新名字都在 setup 的 return 里）；`hwenc_test.py` H3/H4 与 `platform_test.py` E6 的取样窗口原先按固定字符数 / 全文件扫，被这一轮的改动撑歪，改成按函数边界取。活体端到端在自起沙箱里跑通：6 轨读全 → 导出 4 轨混音（静音吉他与钢琴、贝斯 50%）→ `ffprobe` 回读 `pcm_s16le / 44100 / 2ch` → 浏览器点导出真落盘并弹提示，`pageerror` 0。
- 改 / 加的文件：`voice_tools.py`（模型表、`DEMUCS_STEMS_MODES` / `DEMUCS_STEMS_BY_MODEL`、`separate_demucs` 的 `stems_mode`）、`server.py`（`DEFAULTS` / `ConfigBody` / 保存闸门 / `api_ai_vocal_separate` / 新 `api_voice_stems` 与 `api_voice_mix`）、`static/index.html`（分轨范围那一格、混音台卡、`CREDITS` 补一条）、`static/i18n.js`（+35 键 / 份）、`tests/separator_test.py`、`tests/hwenc_test.py`、`tests/platform_test.py`、`CHANGELOG.md`、`CHANGELOG.en.md`、`docs/详细功能介绍.md`、`docs/detailed-features.en.md`。

---

## 分轨的下一步 · 选择挪到动手的那一步（用户指正）

上面那一轮做完，用户第一句是「人声分离没有选择引擎窗口啊」。六轨与混音台都建在语音页，可分离是从文件页点的 —— 点下去连引擎都没得挑。功能都在，只是摆错了地方。

- **文件行「更多 → 分离人声」先弹一格选择框**：引擎 / 模型 / 分轨范围 / 跑在哪，四项预填自设置，改的只有这一次。语音页那张卡不动，它仍是默认值的家 —— 从对话框点出去不回头写 `settings.*`（自检 J3 钉的就是这条：对话框里不许出现给设置赋值）。开始之后那枚按钮换成「去混音台」，带着这个文件的路径跳过去。
- **混音台的入口也挂到文件页**：分离过的文件，菜单里多一条「分轨混音」，跳过去直接把那几条轨读回来。这一条不画分组线 —— 它是「分离人声」的下一步，不是一族之首。
- **模型名单收回到一份**：Demucs 那四个名字原先在界面里写死了两份（语音页一格 + 对话框一格），现在由 `/api/ai/voice_status` 的 `separation.demucs_models` 带回，两处 `v-for` 渲染。界面抄第二份名单迟早和保存闸门那份对不上，把界面自己的选项判成非法值（A4 从「比对写死的四项」改成「两处都是 v-for，且界面里不许再出现写死的 option」）。
- **活体跑抓到的真 bug（不是接线问题）**：`loadVoiceStatus()` 原先只在 `page === 'voice'` 时调用，从不进语音页的人直接开对话框，两格 `v-for` 的模型下拉是**空的**，选中值退化成裸 id（`htdemucs_6s` / `bs_1297`）。第一次误判成「v-if/v-else 复用组件实例」，加了 `key` 复跑 —— 没用，同一处仍然空；回到 DOM 上看才看清静态选项（引擎 / 设备 / 分轨范围）都在、只有 `v-for` 的没在，指向的是数据没到。修法是 `openSepDlg` 里 `if (!sepInfo.value) loadVoiceStatus()`，`key` 那两处撤回。自检测不到这一条：`voice_status` 的读数在离线批里是桩，桩回包一直有这两个字段。
- **换模型时范围自己收回**：`htdemucs_6s` 配「六轨」，换成别的模型时那档已经点不得了，`clampSepStems` 把它收回「只取人声」，但**不会**在换回 6s 时自动替人选回六轨 —— 那是替别人决定跑法。
- 自检：`separator_test.py` 加 J1–J9（老那条裸 POST 断干净、五项覆盖与后端五个 `body.get` 一一对上、对话框不写设置、收回规则、两处 return 都挂名、新键两份词表齐、打开时补取状态），`pagemount_test.py` P8 的菜单项数从 15 改 16（带线的仍是五个组首）。活体在自起沙箱里 12 条全过：预填读数、切引擎换格、收回与再点、请求体五项、跳混音台带路径、从文件页读回六条轨、`pageerror` 0。
- 改 / 加的文件：`server.py`（`voice_status` 多带 `demucs_models`）、`static/index.html`（对话框、两项菜单、两处 `v-for`、`sepDlg` 一族函数）、`static/i18n.js`（+6 键 / 份）、`tests/separator_test.py`、`tests/pagemount_test.py`、`CHANGELOG.md`、`CHANGELOG.en.md`、`docs/详细功能介绍.md`、`docs/detailed-features.en.md`。

---

## Demucs 的模型进「组件与依赖」：能检测缺哪几个，也能一键补齐

上一节做完，用户那句还挂着：「依赖也加上并支持检测更新」。RoFormer 那四条权重本来就在表里，缺的是 Demucs 这一路 —— 它不经过我们，是包自己去 torch 的缓存目录取，所以表上既看不见它，也就没人知道「选了 htdemucs 要等多久」。

- **口径先说死：模型没有独立版本号。** 能检测的只有「在不在、缺几个文件」，能「更新」的只有「补齐缺的那几个」。界面那句话就写 `{ready} / {total} 个模型的文件齐了，还缺 {n} 个`，不写成「有新版可更新」——那是没有的东西。
- **名单、地址、校验值全部读自装好的那个包**：`remote/files.txt` 是「`root:` 子目录 + 一行一个文件名」，`remote/<模型>.yaml` 的 `models: [...]` 给的是文件名前半那 8 位签名，两张表拼起来才是完整地址。`voice_tools` 里不写第二份名单（K1 钉着：源码里不许出现 `xxxxxxxx-xxxxxxxx.th` 这样的字面量）。yaml 列了而索引没接住的签名必须为 0（K2）—— 真漏了的症状是界面上永远显示「缺」，其实是解析没接住。
- **校验值按「给多长核多长」**：文件名后半那 8 位是 sha256 前缀，torch.hub 与 demucs 载入时（`check_hash=True`）也就核到这个长度，所以我们核的也是它 —— 不多承诺一分。原先 `_finish_weight` 写死与整份 sha256 相等，改成前缀比对（RoFormer 那批给的是 64 位，行为不变，K5 钉住）。
- **只补缺的，已经在的一个字节不动**；同一时刻只让一个在补（`_DEMUCS_MODEL_LOCK`）—— 两个线程往同一个 `.part` 上写，会互相把对方刚写的字节盖掉，最后谁都不完整。包不在、或一个都不缺，都在起线程之前就回话（K7）。
- **不进「一键更新」的自动挑选**：几百 MB 的东西不该被一次顺手点掉。那一格旁边单独一枚「补齐 Demucs 模型」，进度写运行日志。
- **顺手一处卫生**：`_fetch_weight` 以前对任何地址都拼 GitHub 镜像前缀，Demucs 的模型在 facebook 自己的站上，拼出来是一串必然 404 的候选 —— 现在只有 GitHub 的地址才拼。
- **缓存目录跟着 torch 走**：`TORCH_HUB` / `TORCH_HOME` 改过的机器上，问错地方就会把「有」报成「缺」。
- 本机读数（跑完自检现问磁盘）：`htdemucs_6s` 1 / 1 个文件在，54,996,327 B；`htdemucs` 0 / 1、`htdemucs_ft` 0 / 4、`mdx_extra` 0 / 4 —— 合计缺 9 个文件。
- 自检：`tests/separator_test.py` 加 K1–K13（名单来源、签名零漏、状态问磁盘、目录随 torch、前缀校验、镜像不乱拼、端点两条早退、锁、三条新日志带键、状态随 voice_status 回、界面接线与 return、两份词表、不进一键）。F1 的「老端点退干净」改成按整串路径查 —— 新的 `/api/ai/demucs_models` 是另一回事，子串匹配会误伤。
- 改 / 加的文件：`voice_tools.py`（`demucs_ckpt_dir` / `demucs_remote_dir` / `demucs_model_index` / `demucs_models_status` / `download_demucs_models`，`_finish_weight` 前缀比对，`_fetch_weight` 镜像守卫）、`server.py`（`voice_status` 带 `demucs_model_files`、新 `POST /api/ai/demucs_models`）、`static/index.html`（那一格的状态行与按钮、`sepDemucsState` / `fetchDemucsModels`、端点动作名）、`static/i18n.js`（+11 键 / 份）、`tests/separator_test.py`。

---

## 音频分析接上拍点与段落结构：两个神经网络来源，旧读数不静默替换

「stemdeck 怎么没加入引擎与组件」这一问，查下来的答案是：**它本身不接**（JS/Electron + 一份 305 MB 的独立 Python 运行时，内部还是 demucs，不上 PyPI，接进来等于把同一件事做两遍），**但它那两项能力我们缺** —— 拍点（beat-this）与段落结构（all-in-one）。按批准的口径只接能力：装进 `tools/separator/venv` 复用同一份 torch，产出并入现有「音频分析」的 JSON 与运行日志，两个包进引擎表能检测上游版本与更新，两组模型文件挂进上一节那套「在不在 / 补齐」并且不进一键。

- **为什么值得接：librosa 那个 tempo 不是精度差一点，是读数会错一倍。** 合成 180 BPM 它报 89.1；真歌「說好不哭」实际 76 报成 152、「Brave Shine」实际 85.7 报成 112.3。同一批文件上两个神经网络来源彼此差不到 1%（85.7 / 86.0）。所以**旧读数不静默替换**：`tempo_bpm` 与 `bpm` 各留各的，相差超过 25% 才在日志末尾补一句 `旧读数 112.3（相差 0.76 倍）`（L9 钉住这条判定与那句原文）。
- **跑的是整首，不是那 180 秒。** 段落结构要看全曲才有意义，而 librosa 那一格仍按 `max_duration=180` 封顶 —— 两个窗口不同这件事写在注释里，不装作同一个口径（L10）。
- **缺哪一层就报哪一层，不起子进程**：没装包、缺模型、没有环境，三种说法各自的 `reason`（L7），失败路径上那八个键也照样在（L8），界面与旁路 JSON 不用判断「键在不在」。
- **一个包坏了不连带把另一项报成没有**：`separator_runner.py --analyze` 里两件事各自 `try`，报错原文进 `errors`；`audio_analyze.py` 把 `errors` 并进 `analysis_error`，段落为空但确实跑过时日志多一句「段落结构没算出来」（L6、L21）。以前只看 `ok`，拍点成功会把结构失败整个吞掉。
- **两个包进上游检测与一键，模型不进**：包有版本号可报，模型没有 —— 缺了要在界面上点名，那是「补齐」不是「有新版」。表上只挂一条「音频分析依赖」，两行并一条，免得变成两条同义通知（L12）。装包与补模型共用分离环境那把锁：两个 pip 同写一个 venv 会互相盖掉对方刚落的文件（L13）。
- **拍点权重只有第三方镜像可达**：作者那份 `.ckpt` 在 `cloud.cp.jku.at`，本轮实测整站 503。用镜像就把这句话说出口 —— 界面那一行多一句「拍点模型取自第三方镜像（作者站当前不可达），已按钉死的 sha256 核对」，下载时先试作者源、退到镜像必须整份 sha256 对上（L3、L16）。超参也一起钉住：镜像那份是裸 `state_dict`，装不进作者那句 `load_model()`。

三处坑是装到能用这一步才现形的：

1. **钉版本自洽不等于钉得够多。** `omegaconf==2.4.0` 与 `hydra-core==1.3.7`（要 `<2.4`）互斥，pip 直接拒；探针环境当初能跑是因为那两件是 `--no-deps` 装进去的。能用的组合只有一组 —— `omegaconf 2.3.1` 恰好要求 `antlr4-python3-runtime==4.9.*`，与「默认那版 antlr 会让 omegaconf 的语法表反序列化失败」那条实测正好对上（L17 钉住这一组数）。
2. **递给 all-in-one 的必须是 wav。** venv 里那份 torchaudio 是 2.11，自带解码器已被拿掉、要额外的 torchcodec，mp3 走它就是 `TorchCodec is required`；它自己的 wav / flac 路径用 soundfile。改成**解码一次两边共用**，临时 wav 只递给库，并把它的 `demix_dir` / `spec_dir` 接进临时目录 —— 那两个默认写在当前目录下，会把副产品拉进程序目录（L18~L20）。
3. **「模型在不在」不能由我们自己翻缓存目录。** 库运行时那句 `hf_hub_download(repo_id, filename)` 不带 revision、只认默认分支，按 commit 号下进缓存的那 8 个 fold 它一个都不认（实测：文件全在，仍报 `LocalEntryNotFound`）。改成**问 venv 里那份库**（`local_files_only=True`），认得出、且逐个文件 sha256 与钉死值对得上才算「在」；钉的东西也随之从 commit 号换成 8 个文件的 sha256（L4、L22~L23）。补齐时同理：`snapshot_download` 只会说「我试过了」，回读对不上就报缺，不拿没核过的权重接着跑。

- **本机读数**（自起沙箱，不碰 8765；真歌整首 252.3 秒）：GPU 55.6 秒出 `bpm 85.7 / 339 拍点 / 88 降拍 / 14 段`，`analysis_error` 为空；CPU 臂一段 180 秒的 93.7 秒，同一个 85.7。装包一次 9 项（含 torchaudio 与 matplotlib），模型 77 MB + 8 × 1,400,571 B。界面那一行中英两种语言都读得出（切语言当场生效，不重启）。
- **顺带照出来一件真缺陷**：主环境 `numpy 2.5.4` + `numba 0.65.0`（元数据写 `numpy<2.5`）让 `import numba` 直接抛错，「音频分析」与声纹说话人分离整条是坏的 —— 8765 用的是同一个解释器。按选择升到 `numba==0.68.0` + `llvmlite==0.50.0`（允许 `<2.6`）后六项读数全绿。numba 不在「组件与依赖」表里、一键更新不会带着它走，这件事记成下一项。
- 自检：`tests/separator_test.py` 加 L1–L23（钉版本、镜像哈希与超参、`--analyze` 分派时机、`@@@JSON` 与分开容错、三层早退、八个键、旧读数那句、两个窗口、组件表取数处、检测与一键的取舍、锁、两份词表、界面接线、镜像要说出口、版本自洽、wav、临时目录、一次解码、错误不吞、回读才算补齐、问库不翻目录）。
- 改 / 加的文件：`voice_tools.py`（`SEP_ANALYSIS_PINS` / `analysis_pkg_versions` / `install_analysis_pkgs` / `analysis_model_states` / `download_analysis_models` / `analysis_status` / `analyze_beats_structure` / `setup_analysis`，venv 探测一次问齐版本与模型）、`separator_runner.py`（`--analyze`：解码一次、拍点、结构）、`audio_analyze.py`（那八个键、旧读数那句、段落标签）、`server.py`（`POST /api/ai/analysis_setup`、`/api/components` 的 `sep_analysis`、上游检测与一键里的一条）、`static/index.html`（那一行与按钮、四个 computed）、`static/i18n.js`（+12 键 / 份）、`tests/separator_test.py`、`tests/i18n_test.py`。

---

## v1.4.0 · 2026-10-15（已发布）

这一批从 #206② 起攒了 15 项（#19~#23 那五条 + #26~#40 那一轮界面收口 + #24/#25 + 两条更正与一条批量跑抓出来的假绿），早过了一个补丁号的量，按要求直接把版本号升到 **v1.4.0** 并**统一出一次包**。下面每一节末尾那句「本轮没出包」写的是当时那一轮自己的状态 —— 那时 `appVersion` 确实还停在 `v1.3.2`，包是这批做完最后一次性打的，见本批末尾的「发布物」。

按上一轮排定的顺序往下做，先落 **#206 那张清单的 ②：队列级定时窗**。这件事以前的形态是「人守着」—— 想让一批任务夜里跑，就得半夜起来点一下「全部继续」，忘了就白等；`paused` 那个开关只会整个停，不会挑时候。现在把「几点到几点才开新任务」写进设置，到点自己继续，**已经在下载的一根毛都不动**（掐断正在写的文件不是「定时跑队列」的意思）。**这一轮只动代码、离线自检与文档：`appVersion` 仍是 `v1.3.2`，便携包与 Release 都没碰。**

### 后端

- **钟点口径与「限速时段」同源，不另起一套**：`_SPEED_ARROW_RE` / `_SPEED_SPAN_RE` / `_hhmm`（server.py:5001 起的 `_hm_to_min`、`_hm_until`、`window_hit`，以及 5021 的 `parse_run_windows`）全部复用，跨零点同一条规则（起 > 止 就按「当晚到凌晨」算，`22:00-06:00` 在 23:30 和 02:00 都算命中）。用户从限速那栏照抄一行 `09:00-12:00 -> 2M` 过来也只取前半段，不会报错 —— 两栏长得像、行为也该像。
- **两道闸**：`run_window`（全局）与 `queue_windows[队列名]`（命名队列各自的窗）。全局那道在 `_pump()` 取任务之前（server.py:8557），关着就一条新的都不开；队列那道在取出单个任务之后、同域并发上限之前（8592），关着的排进 `held` 继续看下一个 —— 所以「night 只在夜里跑」不会连带把 default 队列一起冻住。放回顺序是 `held + skipped + pending`（8637）：被窗压住的排在同域冷却的前头，开门那一刻先跑它们。
- **到点自醒不走 `_wake_later`**：`_arm_window_wake()`（server.py:8358）自己排一个 `threading.Timer`。原因是那条通道给站点冷却用，`min(900.0, …)` 封顶，而「离开门还差六小时」按它排就永远醒在错误的时间上。剩多少分钟由 `_hm_until()` 按 24 小时圈取模，恒为非负；同时有多个窗关着时保留更早的那个闹钟，不让后一个把前一个换掉。
- **默认值这一条必须守住**：`window_open("")` 回 `(True, "没设定时窗，什么时候都能跑", "", 0)` —— 升级上来的人没填过这一栏，行为要和从前一字不差。配置里存着认不出的行（手改 `config.json` 那种）时说明句会带出「没认出来的行：…」，开门判断照旧按认得出的那些走，不静默生效。
- **保存当场核对**：`parse_run_windows` 的错逐行顶回 400，`a == b` 单独拒（「说不上是整圈还是零圈」），存进去的钟点统一补零归一化成 `HH:MM`。队列名也要核：`known = named_queues ∪ KNOWN_QUEUE_NAMES ∪ 队列里真用过的名字`（server.py:5018），只按设置那张 `named_queues` 表校验会把后端自己入队用的 `music`（15033 那条）顶回去，表现就是「设了没用还报错」。存完立刻 `queue._pump()`（12033 那段），改完窗不用等下一个事件才放行。
- **`window_status()`（server.py:8383）一次说清三件事**：现在能不能跑、不能跑到几点开、每条队列各自的窗与压着几条。**没填窗的队列也照样列出来**（`windows: ""`、`open: true`）—— 设置页那张输入框表要按这份名单逐行渲染，漏一行用户就没法给它填窗。
- **给界面的三个口**：`GET /api/tasks` 多带 `window`（12289）、SSE `state` 帧多带同一份（19758 附近），新加的体检口 `POST /api/config/run_window/check`（12071）只体检不写配置，`live` 里回活体状态。SSE 签名（`_sse_state_sig`）里定时窗**只签「开没开、几点开、压了几条」，不签还剩几分钟** —— 那个数字每拍都在掉，为它整张任务表重推是本末倒置，界面按 `resume_at` 自己倒数。

### 一处自检抓出来的接口漏口

`ConfigBody`（server.py:9643）那份 pydantic 模型用 `model_dump(exclude_none=True)` 收身，**没在模型上声明的键在这一步就掉了**：`run_window` / `queue_windows` 起初只加了 `DEFAULTS` 和读写代码，接口层根本收不到，表现是「设置存了、界面显示正常、队列毫无变化」。补自检时逐处核对接口层才发现，`Optional[str]` / `Optional[dict]` 两行挂在 `speed_windows` 旁边（9724 附近），并落成自检里一条 `G2`（断言的是模型里那两行声明本身，不是「配置有默认值」这种看着像在理的旁证）。**离线全绿照样能漏这种事，这是本轮唯一一次真抓到。**

### 队列级窗的一句话日志（第一次重启之后补的）

第一遍活体读数里，全局窗关着会记一行「[queue] 队列定时窗：…」，而队列级窗压住任务时**日志一片安静** —— 界面横幅看得见，走 Telegram 或只看日志的人看不见。补上按「队列名 + 开门钟点」去重的一行（`_window_logged_q`，server.py:8335 声明、8592 那段写），排队多少个只记一行。补完重启并重跑，这条的活体读数在下面第二段。

### 界面

- **设置页多一张「队列定时窗」卡片**，排在「限速时段」之后（`static/index.html:4098`）：上面一栏全局窗（textarea，占位写的是 `09:00-12:00` / `22:00-06:00` 两行例子），下面每条命名队列一个输入框（`queueRows` 来自后端那份名单），右侧就地显示「关着，压着 N 条，HH:MM 自动开始」或「开着」；说明里点明与「限速时段」的分工 —— **那边管跑多快，这边管跑不跑**。
- **「检查格式」按钮 + `runWinStat` 读数**（`checkRunWindows()`，11328）与限速那栏同一套写法：输入停 300 毫秒静默体检，点一下才弹消息；认不出的行只报前两条，其余靠卡片文案自己回头。
- **队列页多一条横幅**（`v-if="windowHeld"`，1863）：全局关着、或任意一条队列关着，就逐个队列挂一个 tag，写清「等待几条 · 几点自动开始」。数据两个来源都接 —— SSE `state` 帧（9734 附近）与 `/api/tasks` 轮询（9699）都往 `queueWindow` 灌，SSE 断了轮询照旧能把状态纠回来。`saveSettings()` 里跟一句 `refreshRunWindow()`，刚存下去的窗立刻反映到横幅与每队列那一行。

### 自检

- 新增 **`tests/runwindow_test.py` 75 项全绿**（A 解析 11 / B 命中与说明 14 / C `_pump` 两道闸 14 / D 开窗放行 3 / E `window_status()` 10 / F SSE 签名 6 / G 接线静态 16 / H 收尾 1）。C 段全部**内存跑**：假 engine、假 cfg、`_run` 用实例属性盖成记账函数，断言「一条都不开、pending 一字不动、闹钟排上了、日志只一行、同队列三个任务只记一行」，以及「压住的排在同域暂缓之前」。测试用的时段不是写死的钟点，而是**按跑测试那一刻推出来的** `CLOSED_WIN`（起点在六小时以后、宽一小时）与 `OPEN_WIN`（`00:00-23:59`），加上 B0 那条基准断言，所以这套自检在凌晨三点跑和在下午三点跑结果一致 —— 上一版写死 `22:00-06:00` 时，测试在窗内会整段静默跳过，那是假绿。
- **`tests/sse_test.py` 被这次改动当场弄红，然后修的是它**：那份 `FakeQueue` 没有 `window_status()`，`_sse_state()` 一调就 `AttributeError`，自检直接红 —— 这正是它该做的事。补上假队列的 `window_status()`（连同「`wait_minutes` 每拍都在掉」这个真行为），断言从原来的数目涨到 **72 项全绿**，新增 `C10b~C10g` 六条钉住「开没开 / 几点开 / 压了几条进签名，剩几分钟不进」，`E5b` 钉住首帧 `state` 就带 `window`。
- 回归面：**46 套**（42 个 `*_test.py` + `_e2e.py` / `_selftest.py` 那几套）重跑，逐套按 `^PASS` 计数、以退出码判红，**2231 条 PASS、`RED=none`**；`python -m py_compile server.py` 通过。这一遍也顺手抓到跑法本身的一个坑：第一版统计脚本用 `runtime/python.exe` 去跑（那个路径在本机不存在），输出为空、`^PASS` 数为 0，差点报成「46 套全绿但一项没有」—— 计数为 0 本身就是红灯，不是绿灯。

### 说明：改完按要求重启了 8765 并取线上读数

PID 42580 → 28660 → 46216，两次重启前都确认过 `running=0 / pending=0`，没打断任何在跑的任务。

- **没配置时的默认**：`GET /api/tasks` 的 `window` 回 `open=true`、`note="没设定时窗，什么时候都能跑"`、`held=0`，队列行 5 条（`default / night / subscribe / sniff / music`）`windows` 全空 —— 升级不影响任何人。
- **三种存不下去的写法都当场 400**：`晚上十点-早上六点`（点名第 1 行）、`12:00-12:00`（「说不上是整圈还是零圈」）、`queue_windows: {"nosuchqueue": …}`（「没有这条命名队列「nosuchqueue」」）。
- **存进去读得回**：`run_window="10:24-10:44"` 之后 `GET /api/config` 回同值（归一化后仍是 `10:24-10:44`），`window` 回 `open=false / resume_at=10:24 / wait_minutes=1`。
- **全局窗外真的不放行**：窗关着时入队一条（audio_only），3 秒后读回 `pending=1`、任务 `queued`、`window.held=1`，日志一行 `[queue] 队列定时窗：现在不在运行时段（10:24–10:44），10:24 自动开始`；期间反复泵也不刷第二行。
- **交给队列级那道窗接着压**：把全局清空、改成 `queue_windows={"default": "10:27-10:42"}`，读回全局 `open=true` 而 `default` 行 `open=false / held=1`，任务仍是 `queued` —— 两道闸各管各的。
- **到点自己继续（这条是本次最想看的）**：10:27 之前没有任何 API 调用，10:27:44 读回 `running=1 / pending=0 / status=downloading`，闹钟那条 `threading.Timer` 真的把队列泵起来了。
- **队列级窗的日志行（补完之后那一遍）**：`queue_windows={"default": "10:53-11:13"}` 入队一条，读回 `pending=1`、状态 `queued`、全局 `open=true`、`default` 行 `held=1`，日志一行 `[queue] 队列「default」定时窗：10:53 之前不开新任务`。
- **体检口**：`22:00-06:00 -> 2M` / `晚上十点` / `09:00-12:00` 三行送进去，回 `count=2 / open=true`（当时 10:26，命中 09:00–12:00），说明句里带出「没认出来的行：第 2 行…」，`live` 是当时的活体状态。
- **界面是渲染出来读回来的，不是看代码**：队列页横幅实测文本「⏱ 定时窗外，暂不开新任务 · default · 等待 1 条 · 10:27 自动开始」；设置页那张卡片共 6 个输入框（全局 textarea + 5 条队列），`default` 一行显示「关着，压着 1 条，10:27 自动开始」，存进去的 `10:27-10:42` 回填在它自己那个框里，其余四行为空。
- **测试痕迹清干净了**：那条任务先停后删，留下的 `Big Buck Bunny … .m4a`（31,787,344 字节，音频下完了才被我停掉）已从 `Downloads/` 删除，`Downloads/download_archive.txt` 里对应的 `youtube aqz-KE-bpKQ` 一行同步删掉（19 → 18 行，删前备份），免得下次「跳过已下载」把它悄悄挡掉；`history.json` 仍是 31 项没变（任务删在停止态，没入库）。两个窗配置都清回 `run_window=""` / `queue_windows={}`，读回 `open=true / held=0`。
  - **清完又被填回来一次，这一条值得单独记**：约十分钟后 `GET /api/tasks` 的 `window` 又回出 `queue_windows={"default": "10:27-10:42"}`，磁盘 `config.json` 的 mtime 与 `app.log` 里那句 `[界面] 保存设置（132 项变更）` 同在一秒 —— 是这一轮为了读界面而一直开着的那个设置页，拿着**它自己十几分钟前加载的整包快照**把设置原样回存了一次，正好把刚清掉的窗填了回来。危害很具体：`10:27-10:42` 在当下是**关着**的，不处理的话用户的队列会一声不响地停摆到明天这个时候。处理办法是再清一次 + **把那个页面重新加载成当前配置**（磁盘与内存两处都读到 `run_window=` / `queue_windows={}`、`open=true`、队列行 `windows` 全空才算完）。「整包 POST 设置」是既有设计、不是本轮引进的，但定时窗把它的后果从「某个开关不对」放大成「整条队列不开工」—— 以后凡是往 8765 写过配置再去截界面，截完要么刷新那个页面，要么关掉它。

---

## B5 · 关键词吻合度上屏（同一轮内，接在 #206② 之后）

分数本来就在算，只是**只有换源和查重看得见**。`track_score()`（music_search.py:2400）一直回 `{score,name,artist,time,reject}` 五个数，管的是「这条与那条标注**是不是同一版录音**」；而普通搜索结果那一片表上**一个数都没有** —— 一百来条同名单曲摊在屏幕上，谁像谁不像全靠眼睛。这一轮把那个数字引到界面上，并说清它回答的是**另一个问题**：自由输入的关键词既没有 title/artist 结构、也没有时长，所以它只能管「对不对得上你输入的关键词」。

### 后端

- **新函数 `query_score(keyword, cand)`（music_search.py:2459 起）**，返回形状与 `track_score` 一致、**`time` 恒为 `None`**（关键词侧没有时长可比），沿用同一套硬阈值 `MATCH_NAME_MIN=60 / MATCH_ARTIST_MIN=70 / MATCH_ACCEPT=85`（music_search.py:2279，仍然写死、界面改不了，文案里就照实说「阈值写死在后端 music_search 的 MATCH_* 里」）。`annotate_query_score(rows, keyword)` 给每行落六个键：`score / score_name / score_artist / score_time / score_reject / match_accept`，挂在 `search_music` 的注解流水线末尾（`annotate_quality_spec` → `annotate_reference_compare` → `annotate_query_score` → `return`）。
- **模式词不参与比对**：`search_album` 是往关键词尾巴上拼「专辑」再调 `search_music` 的薄包装，留着它，专辑搜索每一行的曲名维都会被这三个字拖到线以下 —— `_QUERY_STOP = {专辑, album, 单曲, 歌曲, collection}`。
- **两处是真数据打出来的问题，不是想出来的**：
  1. 最初把整串关键词塞进一个字段比对，「夜曲 / 周杰伦」对「周杰伦 晴天」拿了 **95 且没有拒因**，翻唱行也被喂了个没意义的曲名 40。原因是 `_sim_ratio` 的长度封顶与 `_score_artists` 的宽容把认不出来的词原谅掉了。改成**逐词**拿去曲名与歌手两个字段各比一次、按维取平均。
  2. 两个字段里都找不着的词（`rest`）不能再被原谅：它们归给**没人认领的那一维**补 0 分，并单独产出一句拒因，点名是哪个词认不出来、这条的歌手栏实际写的是什么。第二版那句写成「在曲名和歌手里都找不到」，碰上「晴天 (原唱 周杰伦) / RyaVocal」这种就成了自相矛盾的话（明明找到了「晴天」），改成「在这条的曲名/歌手上认不出来（这条歌手一栏写的是「RyaVocal」）」。

### 界面

- **「来源」列那格多一个数字 tag**（`static/index.html:2934` 附近）：≥ 录取线绿、没过线黄、带拒因红，后面跟一个「不像」；鼠标停在数字上是 `matchHint(row)`（11 行左右，接在 `refHint` 之后）—— 总分 / 录取线 / 曲名·歌手·时长三维子分（`null` 显示「未参与」）/ 被挡的原因 / 那句「它不判是不是同一版录音」的分工说明。表头下补一条 `v-if="musicHasScore"` 的图例，配 `musicScoreLine`（取第一行的 `match_accept`）。
- **换源把旧分数清掉**：合并新行时显式写 `score: null … score_reject: ''` —— 上一行的数字不能跟着换完源还挂在原地。
- 接口层没动：`api_music_search` 是 `{"ok", "keyword", "count", "items": items}` **整包原样返回**，不逐字段重建，所以新键天然到得了前端（这一条落成了自检 `G6`，正是 #206② 那轮 `ConfigBody` 静默掉键的同类漏口的反面）。

### 自检

- **`tests/matchgate_test.py` 从 46 项涨到 64 项全绿**：新增 F 段 16 条（完全同名 100、词序无关、曲名/歌手两类拒因、版本词拦挡、单词查询时歌手维「未参与」、只填歌手、模式词被忽略、时长恒不参与、繁简、空与脏输入不炸、把 `MATCH_NAME_MIN` 临时抬到 100 的反向验证，F13~F15 钉的就是上面那两个真数据 bug）；G 段 12 条钉**接线**（注解真被调用、`match_accept` 来自 `MATCH_ACCEPT`、非 dict 行不炸、`'"items": items'` 在 `api_music_search` 那一段里、tag 标记与 danger/success 三元、`matchHint` 的两串文案、「不像」、图例、换源清分、两个 computed 与 `matchHint` 都在 setup return 里）。

### 说明：改完按要求重启了 8765 并取线上读数

PID 51204（这一轮最后一次重启）。**界面是渲染出来读回来的**：音乐页填「周杰伦 晴天」点搜索，5 个源全开，搜完 50 行 —— 每行都带上了分数，`success` 1 行、`danger` 49 行、「不像」49 个，图例那句照常渲染。

- **过线的只有一条**：`晴天 / 周杰伦 / QQ` = **100**，tooltip 里「曲名 100 · 歌手 100 · 时长 未参与」。
- **被挡的都说得出是谁挡的**：`晴天 / 张信哲` 50「关键词里的周杰伦在这条的曲名/歌手上认不出来（这条歌手一栏写的是「张信哲」）」；`我的地盘 / 周杰伦` 50 反向点名「晴天」认不出来；`星晴 / 周杰伦` 75 走的是曲名闸门「曲名「星晴」与关键词不像（相似度 50）」。
- **高分照样会被版本闸门拦下，界面把两件事一起显示**：`晴天 (Live) / 林俊杰, 周杰伦` 数字 **98** 却是红 tag —— 关键词里没有版本词、这条自己标了 Live，属于另一版录音。这正是「分数高 ≠ 就给你下」的原意。
- **一个自己造成的副作用，如实记在这里**：`api_music_search` 会把请求里的 `sources` 落到 `cfg.data["musicdl_sources"]` 并 `cfg.save()`（server.py:14175 那段），所以前面那些只勾两个源的验证搜索把用户的默认组合改成了 `['QQMusicClient','MiguMusicClient']`。`ConfigBody` 里**没有** `musicdl_sources` 这个字段（只有 `musicdl_cookies` / `musicdl_strategy`），走 POST /api/config 存不回去 —— 只能改 `config.json` 再重启，或让界面用五个源搜一次。本轮按前者恢复成 `Migu/Netease/QQ/Apple/Spotify`，重启后 `GET /api/music/status` 读回同值、侧栏显示「已勾选 5 个源」；随后那次界面搜索又用同样这五个源回存了一次，round-trip 对得上。

---

## #26 · 硬件编码与 x265（同一轮内，接在 B5 之后）

排定的这批里第 ① 项。以前的形态是「转码预设里写死一串 libx264」—— 有 NVENC / QSV / AMF 的机器一样只能用 CPU，想省体积只能自己开命令行。**默认取值就是从前那一条**（`cpu` / `x264` / `medium`），不升驱动、不装新 FFmpeg 的人成品编码一个字都不该变；硬件编码与 x265 要自己在设置里点一下才生效。**这一轮只动代码、离线自检与文档：`appVersion` 仍是 `v1.3.2`，便携包与 Release 都没碰。**

### 后端

- **一个函数收口所有参数口径**：`_encoder_args(name, quality, preset)`（server.py:3986）把对外那一个「越小越费码率」的 CRF 数字映射到各家自己的参数名（`-crf` / `-rc vbr -cq N -b:v 0` / `-global_quality` / `-rc cqp -qp_i -qp_p`），nvenc 的档位另走一张表（veryfast→p1、fast→p2、medium→p4、slow→p5）。**HEVC 装进 mp4 一律补 `-tag:v hvc1`**，不然 QuickTime 和部分播放器认不出轨道。
- **降级链**：`_video_encode_chain(quality)`（4024）—— 厂商优先、CPU 永远垫底、x265 与 x264 互为兜底（只缺 libx265 的构建不该让整件事失败）。探测缓存说这个硬件起不来时，这里直接把它从链上摘掉（`libx*` 那两条永不摘），链最后不会为空。
- **探测必须真跑一帧**：`ffmpeg -encoders` 列得出名字不代表能用。本机实测三种坏法各不相同 —— NVENC「列得出、驱动不认」，QSV 报 `The current mfx implementation is not supported`，AMF 曾经**直接挂住不返回**。所以 `_probe_encoder()`（4092）喂一帧黑场进 `-f null` 且**必带 8 秒硬超时**，超时就按不可用处理：不写这个超时，探测那一步会把界面整个卡死。Linux 的 VAAPI 这轮不做，原因写在代码注释里（要 `-vaapi_device` 加 `hwupload` 改写滤镜链，会和烧字幕那条 `ass=` 打架）。
- **x265 的超时预算是量出来的**：同一台机器、1080p30、同一段 30 秒、CRF 23 / preset medium —— `libx264 4.3s` vs `libx265 11.9s` = **2.75 倍**（合成噪声源那一次 3.6 倍）。`X265_TIMEOUT_MULT = 3.0` 是留了余量的口径，不是猜的；倍数只加在真正会用 x265 的那一次尝试上。
- **烧字幕与转码都改成「按链挨个试」**：`api_ai_hardsub` 的 `job()`（11435 起）与 `_run_transcode()`（19454 起）同一条链、同一套口径 —— 失败先把半成品删掉再换下一个（换编码器是从头编一遍，留着残件只会让人误判），记一行 warning 点名换成了谁，被用户「停止」不当成功也不重试。`-c copy` 与抽音频那两条预设不参与编码器替换，`flv_to_mp4` 的 copy→重编兜底保留。
- **保存当场核对**：`api_set_config`（12199）按三张表逐条校验，认不出的写法顶回 400 并点名允许值；`ConfigBody`（9890）补上那三行 `Optional[str]` 声明 —— 上一轮 G2 那个「模型没声明就被 `model_dump(exclude_none=True)` 静默丢掉」的坑一模一样，这次是先写断言再写实现，没让它重演。
- **新接口 `GET /api/video/encoders`**（19443）：一次回本机每个候选编码器可用与否（连原因）、当前偏好、三张可选值表、以及按已存设置排出来的降级链。

### 自检抓出来的两个真 bug

1. **`?refresh=1` 从来不会重探**：`if not (refresh or c["items"] and …)` 那个优先级写反了，`refresh` 被整个 `not (...)` 吞掉 —— 第一版 G 段断言「refresh=1 会重探」当场把它跑红。不修的话「升了驱动 / 换了 FFmpeg 再点探测」永远拿旧答案。改成正写的 `if refresh or not (缓存命中)`。
2. **探测列不出编码器时对界面谎称「有」**：`built` 为空集（`-encoders` 那一步超时或报错）时 `items[].built` 报的是 `True`。改成 `None` = 不知道，`available` 仍按真跑那一帧的结果走。

### 顺手补的一处既有漏洞（不止影响本轮功能）

`ffmpeg_mgr.find()` 空参调用时**完全不看设置里的「FFmpeg 路径」**：`find(manual)` 只认传进去的那个参数，而 `_encoder_probe_status` / `api_ai_hardsub` / `_run_transcode` 三处都是空参调用。后果很具体 —— 用户在设置里指了另一个 ffmpeg，界面显示的版本是它，实际转码和烧字幕用的还是 `tools/ffmpeg.exe`。本轮把这三处改成 `find(ffmpeg_mgr.manual_path)`（`_run_transcode` 里那处正是转码在用的）。**其余十几处空参调用没动** —— 那是另一件事，不在这轮范围里，记在这里免得以为全修完了。

### 界面

- **「设置 → 视频编码（转码与烧字幕）」卡片**，排在「FFmpeg 路径（可选）」之后（`static/index.html:4698`）：三个下拉（编码器偏好 / CPU 编码器 / CPU 预设）、「探测编码器」按钮、每个编码器一行（绿点=可用，红点=不可用，后面直接跟那句中文原因）、以及「当前降级链」那一句。
- **不白跑探测**：`watch(page, …)` 只在进设置页时拉一次读数；点「探测编码器」才是 `refresh=1` 真重探；`saveSettings()` 里跟一句 `loadEncoders()`（不刷新缓存，只重拉链），改完偏好不用重开页面。

### 自检

- 新增 **`tests/hwenc_test.py` 101 项全绿**（A 参数口径 12 / B 设置归一化 7 / C 降级链 14 / D 只换那一段 8 / E 报错翻译 6 / F 探测与超时 9 / G 缓存与读数 13 / H 接线静态核对 28 / I 内存还原 5）。C 段全在内存里拿假探测缓存跑：「起不来的硬件被摘掉」「CPU 两条永不摘」「缓存过期就当没探测过」「点名 nvenc 而起不来时也不会空链」。F/G 段用假 `subprocess.run` 与假 `ffmpeg_mgr.find`，一次真进程都不起。
- I 段钉的是「测试自己有没有还原干净」：那三项设置、探测缓存、`ffmpeg_mgr.find/version`、`subprocess.run/Popen` 出口，跑完全数归位。

### 说明：改完按要求重启了 8765 并取线上读数

PID 51204 → 22228 → 51272 → 25604，每次重启前都确认 `running=0 / pending=0`，没打断任何在跑的任务。测试用的源片段是本地生成的 8 秒 640×360 小文件，与任何真实下载无关。

- **没配置时的默认**：`GET /api/video/encoders` 回 `preference={cpu, x264, medium}`、链 `[libx264(1.0), libx265(3.0)]` —— 升级上来的人行为与从前一字不差。
- **本机五项探测的真实读数**：`hevc_nvenc` 不可用「显卡驱动不支持这个 FFmpeg 要的 NVENC API 版本（要 13.1，本机驱动只有 13.0）—— 升 NVIDIA 驱动，或换更旧的 FFmpeg」；`hevc_qsv` 不可用「起不来：The current mfx implementation is not supported…」；**`hevc_amf` 可用**；`libx265` / `libx264` 可用。（上一轮盘点是判 AMF「挂住」的，这次它 8 秒内过了 —— 挂不挂看机器当下状态，那条硬超时正因为如此不能撤。）
- **点名 nvidia 而 nvenc 探测不可用**：链变成 `[libx264, libx265]`，不会白试一趟注定失败的编码。
- **`auto` + `x265` 时链首真是硬件**：链 `[hevc_amf, libx265, libx264]`；真转码 8 秒片段（`mp4_1080` 预设）**0.8 秒**出一段，`ffprobe` 回 `hevc / hvc1 / 1920x1080`；日志 `开始转码: hwtest_src_auto.mp4（转 MP4 并限制 1080p · 用 H.265/HEVC（AMD 硬件 AMF））`。
- **CPU/x265 也真出了 HEVC**：`hwtest_src_x265_out.mp4` 回 `hevc / hvc1`，日志点名「用 H.265/HEVC（CPU · libx265）」—— `-tag:v hvc1` 那一步落实在成品上，不是只看命令行参数。
- **烧字幕真用上了硬件**：`{status: done, message: "已生成 hwtest_src_burn.hardsub.mp4（1 MB · H.265/HEVC（AMD 硬件 AMF））"}`，成品 `hevc,hvc1,640x360,240 帧`（8 秒 @30fps 一帧不少）。
- **降级链不是摆设（这一条最想看的就是它）**：临时把设置里的「FFmpeg 路径」指向一个 `.cmd` 假 ffmpeg —— 探测那类调用（不带 `-y`）原样放行，真转码 / 真烧字幕的调用（带 `-y`）碰到 `hevc_amf` 就退出 1，模拟「探测说可用、真内容上却失败」。转码日志三行连起来：`转码用 H.265/HEVC（AMD 硬件 AMF） 没成（[hwtest shim] hevc_amf init failure on real input…），换 H.265/HEVC（CPU · libx265） 重来` → `转码改用了 H.265/HEVC（CPU · libx265）: hwtest_fb_out.mp4` → `转码完成`，成品仍是 `hevc,hvc1`。烧字幕同一套，最后 `烧字幕完成: hwtest_fb_burn.hardsub.mp4（1 MB · 用 H.265/HEVC（CPU · libx265））`。这一跑同时验出了上面那处 `ffmpeg_path` 的既有漏洞：第一遍挂假 ffmpeg 时转码毫无反应（`find()` 空参根本没读它），改成 `find(ffmpeg_mgr.manual_path)` 之后才吃到。
- **枚举校验四种写法都当场 400**：`video_encoder=arm64`、`video_cpu_codec=av1`、`video_cpu_preset=ultra`、以及大写 `GPU`（认不出就是认不出，不猜他想说什么）；`CPU` 这种只是大小写混写的会归一成 `cpu` 后收下。
- **界面是渲染出来读回来的，不是看代码**：卡片三个下拉显示「CPU（最稳，一定可用）／x264（快，兼容最好）／medium（默认）」，编码器五行（两个红点各带一句原因、三个绿点），降级链那句「H.264（CPU · libx264） → H.265/HEVC（CPU · libx265），前一个真跑失败了就自动换下一个重来」。在界面上把偏好改成「自动」、CPU 编码器改成「x265」再点保存 → 弹「已保存」→ 卡片那句链**自己**变成「H.265/HEVC（AMD 硬件 AMF） → H.265/HEVC（CPU · libx265） → H.264（CPU · libx264）」；接着改回 CPU / x264 保存，链回到两条。控制台无报错。
- **测试痕迹清干净了**：`Downloads/` 里 15 个 `hwtest_*`（源、字幕、五份转码与烧字幕成品）全删；那个假 ffmpeg `.cmd` 也删了，而且 `ffmpeg_path` 是在删文件**之前**就先清回空串的，免得服务下次启动去 exec 一个不存在的路径。最后 `GET /api/config` 与磁盘 `config.json` 两处都读回 `video_encoder=cpu / video_cpu_codec=x264 / video_cpu_preset=medium / ffmpeg_path=""`，也就是出厂默认，用户的设置没被我留在改动状态。上一轮那条教训照用：截完界面就把那个页面重新加载一次，别留着一整包旧快照回存。

---

## #27 · 通知 outbox：先落盘再发，失败按递增间隔补发（同一轮内，接在 #26 之后）

**原来是什么样**：一条通知就是「事件发生的那一刻同步发一次」——`TaskQueue._run` 收尾时喊 `notify_done/notify_fail`、订阅扫描喊 `notify_sub`、直播监控喊 `tg_notifier.send`。发不出去只在运行日志里留一行 warning，这条消息就**永久没了**：对端抖一下、正好断网、赶上限流、或者恰好卡在程序重启的那几秒，用户侧的表现都是「说好下载完成会通知我，结果什么都没有」。企业微信还是 16574 那三个猴子补丁函数挂在 `TelegramNotifier` 上的，同一句文案在两处各拼一遍，改一处漏一处。

**这一轮改成**：事件先进 outbox 落盘，发送由后台线程做。

- **落盘才是事实**：`NOTIFY_OUTBOX_FILE = STATE_DIR / "notify_outbox.json"`（和 config/history 同一个地方），进队即写盘，不写不叫「已排队」。写盘走 `临时文件 + os.replace`，**不用本项目那套裸 `open(w)` 惯例** —— 这个文件存在的意义就是「进程在任何时刻被杀也还剩东西」，写到一半崩了不能让它下次读不回任何东西。表上限 50 条，裁的时候先淘汰已经了结的。
- **递增间隔就是用户点的那五档**：`NOTIFY_RETRY_DELAYS = (30, 120, 600, 1800, 3600)`，第 N 次失败后等第 N 档；首发 + 5 次补发都失败才标 `dropped` 并在日志里点名是哪条消息、最后一次为什么。整条时间线约 1.7 小时，之后不再骚扰。
- **补发不重发**：每条记录自己记还欠哪些通道，**成功一个划掉一个**。Telegram 送到、Server酱 超时 —— 下一轮只重试 Server酱，不会把已经收到的那条再发一遍。这是「一条消息 = 一个通道一次」的底线。
- **通道判定收成一个函数**（`_notify_targets(kind)`），开关语义与改造前一字不差：Telegram 看 `telegram_notify_{done|fail|sub}`（`live` 那类不受订阅开关管）、Server酱 仍只跟着「下载完成」、企业微信看 `wecom_notify_*`（它的「订阅更新」在 DEFAULTS 里就是 False）。**没有新增任何设置项**，`ConfigBody` 一个字没动 —— 少一个键就少一次「undeclared key 被 `model_dump(exclude_none=True)` 静默吞掉」的坑。三个 `notify_*` 方法改成拼文案 + 进队，16574 那段猴子补丁整体删掉；文案与改造前逐字相同（自检 B 段就是拿旧字符串对着比的）。
- **顺带改掉的一处既有隐患**：企业微信的 access_token 缓存在 `errcode 40014/42001/41001`（票过期 / 无效）时会被清掉。不清的话，outbox 的每一次重试都拿同一张废票去撞，一直到被丢弃 —— 重试机制反而把一个「本来 20 秒后就能恢复的问题」固化成「一小时内必失败」。
- **另一个行为变化，写在明面上**：通知不再占着下载线程。原来 `notify_done` 最坏要吃 Telegram 15s + Server酱 15s + 企业微信 12+15s 才让位给下一个任务；现在事件写完盘就走，发送在 `notify-outbox` 那条 daemon 线程里，新事件被 `kick` 一下立刻送达（正常仍是秒级），空闲时 5 秒看一眼有没有到期的。
- **「测试消息」那两个按钮故意不走队列**：`/api/telegram/test`、`/api/wecom/test` 仍是直发。点一下是「当场要结果」，让它进重试表反而会把用户自己的正常通知排在后面。
- **界面**：企业微信卡片下面新增「通知补发队列」一张卡。顶部那句间隔表是**从读数里拿的**（`{{ outbox.retry_delays.join(' → ') }}`），不是写死在 HTML 里 —— 以后改节奏不用改界面。三个按钮：刷新 / 立即重试 / 清空；「立即重试」只把待发的推到「现在就试」并踢醒后台线程，**请求自己不等那 15 秒超时**。每行显示：事件类别、还欠哪些通道、试了几次、下次几点再试（`2 分钟` 这种人话而不是 120）、最后一次失败的原因。清空前先问一句。进设置页才拉一次，读走 `noLog`。
- **自检**：`tests/outbox_test.py`，**134 项，全绿**（A 通道判定 14 / B 文案与改造前一致 9 / C 进队 10 / D 投递记账 14 / E 递增间隔 12 / F 落盘与读回 13 / G 重启不丢 6 / H tick 与线程 8 / I 读数与接口 18 / J 接线 24 / K 内存还原 6）。三个通道发送原语各加一个 `_detail` 版本返回 `(ok, 原因)`，老名字 `send / send_serverchan / wecom_send` 留着包一层（别处还在调）。自检里 H 段是真的把 `start_notify_outbox()` 起起来、发一条、等它送出去、再 stop 掉的 —— 不是只断言「代码里有这行」。

### 说明：改完按要求重启了 8765 并取线上读数

下面每一条都是真发出去、真失败、真重启读回来的（通知通道是临时挂一个假的 CorpID，跑完原样还回去；本机 Telegram 与企业微信本来都是关的，没有真人被骚扰）。

- **启动日志**：`通知 outbox 已启动（失败的通知会落盘重试，重启不丢）`，紧跟 `Web 服务启动 | FFmpeg=9.0.1…`。空队列时 `GET /api/notify/outbox` 回 `counts={0,0,0}`、`retry_delays=[30,120,600,1800,3600]`、`file=…\notify_outbox.json`。
- **真事件真落盘**：临时把企业微信挂上无效凭证，再让一个必然失败的任务跑完（`https://outbox-invalid.example.com/v.mp4`，aria2 DNS 失败 → 直链 SSL EOF → yt-dlp 无法提取）。`/api/notify/outbox` 回一条 `kind=fail / 下载失败`，`attempts=1`、`channels=["企业微信"]`、`error="企业微信：CorpID / Secret 换不到 access_token"`（真从对端拿回来的原因），`next_in=22`。磁盘上那份 JSON 与接口一字不差，中文没被转义。
- **30 秒后自己补发**：不做任何操作等 35 秒，读数变 `attempts=2 / next_in=93` —— 第二档 120 秒，扣掉已经过的时间正好对得上。
- **重启不丢（这一条是整个功能的卖点）**：`taskkill` 掉进程再起来，读数仍是 `attempts=2 / status=pending / created_at=1791957476.7766762`（原来那条事件的时间，没被重置成当下），**已经试过的次数不会被清零**（否则每次重启都从头猛发一轮）。启动日志同时给了一句 `通知 outbox：读回 1 条上次没送出去的，按 30s → 120s → 600s → 1800s → 3600s 的节奏继续重试`。
- **界面是渲染出来读回来的**：卡片正文那句「按 30 → 120 → 600 → 1800 → 3600 秒的间隔重试」、计数「待发 1 · 已送出 0 · 已丢弃 0」、行内「下载失败 · 待补发 / 2026/10/14 14:05:48 · 试了 2 次 · 还欠 企业微信 · 2 分钟 后再试 · 企业微信：CorpID / Secret 换不到 access_token」。在界面上点「立即重试」→ 多出「已把 1 条排到最前，稍等一下再刷新看结果」，行内自己变成「试了 3 次 · 10 分钟 后再试」（第三档 600 秒，读数是 10 分钟，不是界面算的）。点「清空」→ 弹「清空后待补发的通知不会再重试，已送出的记录也会一并抹掉。」，确认后 toast「已清空」、计数归零、行换成空态那句「队列是空的。一个通知通道都没开时，事件到这里就直接跳过，连盘都不写。」。控制台全程零消息。
- **打包侧**：`notify_outbox.json` 记的是「这台机器下过什么」，三处都补上了 —— `EXCLUDE_FILE_RE`（源目录那份根本不会跟着包走）、smoke 试跑后的清理、以及出包前那道 `leaks` 中止检查（用它自己的话说是 ABORT，不是 warning）。
- **测试痕迹清干净了**：两次验证用的任务从队列删掉、`history.json` 里那两条测试记录在停服状态下抹掉（33 → 32 条，读回无残留），临时凭证还原成 `wecom_enabled=False` + CorpID/Secret/AgentId 全空（与进来时一致，`GET /api/config` 读回确认）。盘上留着一个 `records=[]` 的 `notify_outbox.json`，那是这个功能的正常运行时文件。

---

## #28 · 访问保护（Web 登录）：只拦从非本机地址来的连接（同一轮内，接在 #27 之后）

**原来是什么样**：这个端口是裸的。谁能连上 8765，谁就是管理员 —— 改设置、翻下载目录、把已存好的平台 cookie 拿去用，都不需要任何身份。只在 `127.0.0.1` 上自己用本来无所谓，但一旦放进局域网、或者挂到反向代理后面，就是「整台机器的下载目录 + 一堆平台账号」对着网络敞开。

**这一轮改成**：加一道门，默认关着，**开着也只拦非本机来的连接**（这是用户点定的口径：`127.0.0.1` 自己用、MCP 接口桥、浏览器扩展一律照旧不用登录）。

- **来源判定只认 `request.client.host`，明确不读 `X-Forwarded-For`**：同一个值决定的是「这台算不算本机、要不要输口令」。信请求头等于把门交给任何能写头的人 —— 谁都可以在头里自称 `127.0.0.1`。代价写在明面上：走反代的用户会看到登录窗口，这是有意的。
- **口令只存加盐哈希**：PBKDF2-HMAC-SHA256、24 万轮、16 字节随机盐，落成 `pbkdf2_sha256$轮数$盐$派生键` 一行，比对走 `hmac.compare_digest`。任何接口都不回口令或哈希，`GET /api/config` 里这一项永远是空的。
- **会话是签名 cookie，不是服务端那张表**：`mdl_session` = 版本 / 签发时间 / 最后活动 / 绝对到期 的 base64 + `secret_key` 的 HMAC 截断，`HttpOnly` + `SameSite=Lax` + `path=/`。不用内存表的理由有两个：重启不该把所有人踢下线，也不该攒一堆永远清不掉的会话。空闲超过 `web_auth_session_hours`（默认 12）要重登；滑动续期只在 `last` 超过 5 分钟且没勾「记住」时重签 —— 勾了「记住这台设备」按 `web_auth_remember_days`（默认 30 天）的绝对上限走，那一档**故意不滑**，否则「最长 30 天」会变成「只要一直开着页面就永远不过期」。
- **SECRET_KEY 持久化**：第一次用到时 `secrets.token_hex(32)` 生成并 `cfg.save()` 写进 `config.json` —— 所以**重启程序后浏览器不用重登**（这本来就是「持久化」这个词要解决的问题）。改口令会轮转它，于是所有旧会话立刻作废：口令可能已经漏了，这是要的副作用，卡片上也写明了。
- **连错锁定落在 `login_state.json`**：临时文件 + `os.replace` 写盘（和 outbox 同一个理由：这个文件存在的意义就是「进程被硬杀也还剩东西」，用本项目那套裸 `open(w)` 惯例会留下读不回的半个 JSON）。失败窗口一小时，一小时前的那些不再计数 —— 手滑一次不该一直背着。**锁定检查排在验密之前**，所以锁期内**口令输对了也照样 423**，回的是还剩多少秒而不是「对了」。
- **机器令牌是第二道门，而且只开数据接口**：`X-MDL-Token` 给跨主机 / 走反代的自动脚本用。它过得了下载、队列、历史，**过不了这门本身** —— `/api/auth/*` 在门里就直接不认它，`POST /api/config` 只要带任何 `web_auth_*` 键就 403。加这条是因为想到「令牌漏了」最坏不该是「保护被关掉」：一把钥匙不该能把锁拆了。
- **告警复用 outbox 的 `fail` 一档，没有新增通道开关**：只在两个时刻发 —— ①某个来源刚被锁上，②某个来源在失败之后终于登进来了（有人撞门并且撞开了）。正常登录保持安静，不会每次刷新都骚扰。`_auth_notify` 整段包 try/except：通知出岔子绝不能把登录接口拖成 500。
- **配置遮蔽与写入口收窄**：`GET /api/config` 过一遍 `_auth_config_mask()`，把 `secret_key` / `web_auth_password_hash` / `web_auth_machine_token` 抹成空，另给两个派生布尔 `*_set`；`ConfigBody` 里只声明开关 + 四个数字，三条密钥**没有配置写入口**（少一个键就少一次「整包回存把密钥覆盖掉」的事故，也少一次 `model_dump(exclude_none=True)` 静默吞键的坑）。
- **「开关开了但口令还没设」时不拦人**：`_auth_enforcing()` 要求哈希非空。那时没人能登进来，拦了等于把整个服务（包括本机自己）关死。`POST /api/config` 想在这状态下开开关 → 400 让用户先去设口令，卡片与状态接口也直说「保护暂时没生效」。
- **界面**：登录遮罩（三种失败原因各说各的话、回车提交、剩余次数实时显示、「记住这台设备」勾选）+ 设置页「访问保护（登录）」卡片（开关、这台设备的来源与登录状态、设 / 改口令、四个数字、机器令牌显示 / 复制 / 重置、锁定名单逐个解锁与全部解锁）。遮罩上原本还挂了个「先看看界面」的按钮，做完整轮读数后**删掉了** —— 后台轮询会立刻再 401 把遮罩顶回来，留着只是骗人。
- **MCP 桥**：`_auth_headers()` 先读环境变量 `MEDIADOWNLOADER_MCP_TOKEN`，没设时读本机 `config.json` 里那串。按默认口径（桥只连 127.0.0.1）本来就用不上它，带着是为了**将来改绑法不用改桥**；桥那条「只准连环回」的约束一个字没动。
- **打包侧**：`login_state.json` 记的是谁在撞这门，和 `notify_outbox.json` 一样三处补齐 —— `EXCLUDE_FILE_RE`、smoke 试跑后的清理、出包前那道 `leaks` 中止检查。
- **自检**：`tests/auth_test.py`，**271 项全绿**（A 来源判定与口令哈希 29 / B SECRET_KEY 与机器令牌 14 / C 会话签名 21 / D 门该拦谁 28 / E 连错锁定 14 / F 落盘 10 / G HTTP 层 99 / H 出厂默认 11 / I MCP 桥 9 / J 界面接线 29 / K 打包 3 / L 还原 4，合计 271）。B / D / G 三处都有「**只读不会顺手生成并落盘**」这类断言 —— 见下面那条活体读数抓出来的真 bug。G 段里另有一条断言日志「只说事、不说值」：跑完一整轮登录 / 失败 / 锁定 / 改口令之后，日志里不许出现口令原文或令牌原文。

### 一处活体读数抓出来的真 bug（自检全绿也没拦住）

上线前 `tests/auth_test.py` 已经 270 项全绿，但第一次拿真 `127.0.0.1:8765` 读 `/api/auth/status`，**用户那份真 `config.json` 里就多了一串 48 位的 `web_auth_machine_token`** ——「读一下状态」这个动作把配置写了盘。自检为什么没抓到：它所有断言都在问「令牌对不对」，没有一条问「读令牌之前它存不存在」。改法是加一个不生成的读值函数 `_auth_machine_token_value()`，门、状态、授权判定、两处 GET 全用它，**只有 `POST /api/auth/machine_token`（卡片上那个「重置」）才生成并落盘**；卡片文案与「复制」的空态跟着改成「这串要点『重置』才生成 —— 光是刷新界面不会写盘」。补了 B13 / B14 / D26-D28 / G68b 五条钉住它。那串已经写进用户配置里的令牌，在停服状态下清回 `""`，重启后连读两次 `/api/auth/status`，`machine_token_set` 仍是 `False`，盘上那一项仍是 `""`。

### 说明：改完按要求重启了 8765 并取线上读数

跨网线的证明不是在本机演的：另起了一个临时实例绑 `0.0.0.0:8766`（自己的 STATE_DIR、自己的下载目录、口令 `lan-verify-2026`、锁时临时调成 1 分钟好等），从局域网地址 `192.168.1.100` 读，并且绕过系统代理（不然连本机都要绕一圈，失败信息还难看）。跑完杀掉、目录删掉。

- **用户自己那台 8765 的出厂口径没变**：`/api/auth/status` 回 `enabled=False / enforcing=False / password_set=False / machine_token_set=False / 12·30·5·15`，`/api/config` 里三条密钥全空，`/api/status`、`/api/tasks`、`/api/logs` 等老接口照旧 200 —— 默认关着，谁都不拦。
- **门真的在拦**：8766 上未登录从 `192.168.1.100` 读 → `401 {'detail': '要登录：请在弹出的窗口里输入访问口令', 'auth_required': True, 'reason': 'empty'}`；同一时刻 `127.0.0.1` 连它照样 200；`/` 本身 200（HTML 拿不到就谈不上弹登录窗口）。状态接口如实报 `client_ip=192.168.1.100`、`authorized=False`、`note='保护已生效：只有非本机来的连接要登录'`。
- **爆破真被锁**：连错 → 「口令不对，还能试 2 次」→「口令连续错满 5 次，已锁 1 分钟」→ 锁期内换正确口令仍是 423「连续错太多次，已锁到 60 秒之后」。盘上 `login_state.json` = `{"fails": {}, "locked": {"192.168.1.100": 1791962495.88}}`。本机那侧看得到这条锁，点「解锁」后登录 200，`expires_in=43200`，回 `Set-Cookie: mdl_session=…`；带着这枚 cookie 读 `/api/status`、`/api/config` 都 200（哈希仍遮蔽），而 `127.0.0.1` 根本不需要 cookie。
- **令牌那只开一半的门**：「重置」生成 48 位；带着它读数据接口 200、写 `concurrent` 200、写 `web_auth_enabled` **403「机器令牌只开数据接口：改访问保护的设置要从界面登录」**，随便一串 401；登出后再读又回 401。
- **界面是渲染出来读回来的**：在 `http://192.168.1.100:8766` 上遮罩出现，文案是「这台下载器设了访问口令 / 本机（127.0.0.1）用浏览器打开是不需要登录的，你是从别的地址连进来的。」；先输错一次 → 行内「口令不对，还能试 4 次」；输对 → 页面自己刷新、数据真加载（队列「进行中 0」、下载页各控件与档位表都在），而 `document.cookie` 里读不到那枚会话串（`HttpOnly` 生效）；设置页卡片「这台设备：来源 192.168.1.100（非本机） · 登录状态 过得去」，四个数字框实读 12 / 30 / 5 / 1（那个 1 就是临时实例自己改过的锁时），点「显示」出 48 位令牌。回到 `127.0.0.1:8765`：遮罩不出现，卡片写「未开启：谁连上这个端口都能直接用 · 口令还没设（没设口令时开了也不拦人，见下面先设口令）」、来源「127.0.0.1（本机，不拦）」、令牌框点开是空的（读不会顺手生成）、锁定名单「没有」。**两个页面控制台全程零消息。**
- **测试痕迹清干净了**：8766 那个实例 `taskkill`，`tests/_auth_live_state/`（config / login_state / app.log / 下载目录）整目录删除；用户真 `config.json` 里那串被「读接口顺手写盘」写进去的机器令牌已清回 `""`（其余 189 个键原样），`web_auth_enabled=False`、口令哈希空、`secret_key` 空 —— 与进来时一致。

---

## #29 · 字幕时间轴三维质检：覆盖率 / 最大间隙 / 字符速率（同一轮内，接在 #28 之后）

用户点名的第四项。原来译后质检只会逐句对照文字（空句、漏译、术语、数字、超长），时间轴本身没人看：字幕整段没盖上、两句之间空了一分半、一句话挤在半秒里读不完，这些以前一律不出声。这一轮把时间轴单独量成三个数，并且明确「算不出来」和「用户没开质检」是两回事。

### 三个维度都不吃「另一路原文」

单语字幕也算得出来，这是它和逐句对照那一路最大的区别：只需要这份字幕自己的起止时间与正文。

- **覆盖率** = 所有字幕时间段的并集 ÷ 媒体时长。按并集算而不是相加，因为站点自动字幕常用滚动式排布，两条本来就叠在一起，相加会算出 110%。低于 35% 标一句「大段没有字幕」，但这只是提示不是判错——器乐、无人声、纯画面的段落本来就该空着，它要和最大间隙合起来看才说明问题。
- **最大间隙** = 句与句之间空得最久的那一段，阈值 30 秒。三条口径是这轮定下来的：①第一条字幕之前的**片头空档**也算一条（片子一开始就该有字幕）；②**片尾容忍带**按媒体时长的 8% 给，下限 10 秒、上限 90 秒，落在带里的空档不计入最大间隙，末句之后那段一律单列并写明「不计入」——演职员表与片尾曲本来就没词；③句子之间的重叠不算问题，只单独计数。空档列表按大小排，最多列 8 条，计数按全部。
- **字符速率** = 每句的显示宽度 ÷ 那句的显示秒数。上限中文 9、外文换算后 14（同一套 `text_units` 加权，跟换行与「超出每行字数」那条用的是同一个度量），低于 0.4 秒的句子进「太短」名单，又快又短的只按超限报一次。

另外两类只列名单、不动文件：**整句只是语气词**（嗯啊呃哦 / um uh 这种，且全句宽度不超过 3）与**同一句连着复读三遍以上**（Whisper 在静音和片尾背景乐上最容易这样吐）。程序没有替你删——歌词副歌本来就会重复，纪录片里的「嗯」也可能正是要的内容。界面上给一个「按名单删掉这 N 句」的按钮：弹确认、句序从大到小删、只改界面上这份，按「保存」才写盘（写盘前照例留备份）。

### 「这一项没算」不等于「质检被关着」

两头都写了，缺的那一头如实交代，关着的那一头也如实交代：

- 拿不到媒体时长时（字幕旁边找不到配对的媒体、本机没有 ffprobe、ffprobe 读不出时长三种原因分开写），覆盖率这一项回 `available: false`，说明文字直接写「这一项没算：……（是缺输入，不是质检被关着）」。片尾那一项跟着改成 `available: false, seconds: null`，不再装作量出来是 0 秒；日志句里也不再出现「片尾空档 N 秒」这一节。
- 用户真的关了质检时，流水线补一行「字幕质检没开（设置 → 字幕翻译）：这一轮逐句对照与时间轴三维都没跑，日志里看不到质检行不等于「查过且没问题」」。以前关掉就是安静地什么都不写，看上去跟「查过且没问题」一模一样。

### 界面上

`POST /api/subtitle/qc` 的响应多了 `media` / `media_seconds` / `timeline` / `timeline_text` 四个字段，「逐句校对」里新增一块「时间轴三维」。这一块只看 `timeline` 在不在，不看可疑行数——一份文字挑不出毛病、时间轴却空了一分半的字幕，以前整块面板都不渲染。阈值随结构一起回（`thresholds`），界面不用自己抄一遍数字；名单被截断时界面上写明「其余 N 句没列在这里」。

### 活体读数抓出来的两处真问题（都在我自己新写的代码里）

1. **卡拉 OK / 滚动式 VTT 报出「最快 2500 字每秒」**，中位 26.83，59 句超限。两个原因叠在一起：VTT 正文里内联着 `<00:00:35.626>` 这类时间戳标记和 `<c>` 标签，被当字计了；排布器还会插 0.01 秒的重复「闪光条」，2 个字除以 0.01 秒。修法是算字数前先 `_qc_plain()` 剥标签（复读判定也走同一个函数，不然剥完标签才看得出的重复会漏报），比 0.1 秒还短的条目单独归一笔不参与读速。修完同一份文件：中位 3.36、32 条闪光条被排除、超限 3 句——这 3 句是真的挤。
2. **`leading` 字段是死代码**。它写成 `gaps[0] ... if gaps[0]["before"] == ordered[0][0]`，而排最前那条永远不会有「它之前的空档」，所以条件恒假。自检的 B10 直接把它抓出来了：片头空档根本没被量。改成从 0 秒起算第一条之前的空档并计入间隙，界面与日志再按 `leading` 标记说成「片头空了 40 秒（第一条字幕之前）」而不是「第 1 句之前」。

### 活体读数

改完按要求重启了 8765（现 PID 2920），用真文件取读数：

| 文件 | 句数 | 媒体 | 覆盖率 | 最大间隙 | 片尾 | 读速 |
|---|---|---|---|---|---|---|
| Nintendo Direct 2026.9.9 `.srt` | 727 | 2839.73 秒 | 92%（2614.48 秒有字幕） | 108.62 秒（第 370 句之前），超 30 秒的 3 处 | 13.82 秒不计入（容忍带 90） | 中位 4.0，超限 14 句（名单列 8） |
| 【Akie秋絵】歌に形はないけれど `.zh-Hans.vtt` | 70 | 330.02 秒 | 76% | 片头空了 34.76 秒（第一条之前） | 43.34 秒不计入（容忍带 26.4） | 中位 3.36，超限 3 句，闪光条 32 条没参与 |
| 探针：只有字幕、旁边没媒体 | 3 | 无 | 没算（缺输入，不是质检没关） | 片头 40 秒 | 没算 | 都在上限内 |

第二行是「覆盖率吃不到媒体就别算」的反面用例：那份 `.zh-Hans.vtt` 靠剥语言后缀找回了同目录的 `.mkv`。浏览器里读回渲染结果：三项各就各位，片头那条显示「第一条之前 | 空了 40 秒 | 片头 | 片子一开始就该有字幕，第一条却等到 40 秒才出现」，缺媒体那项显示「这一项没算……是缺输入，不是质检没开」，截断提示显示「其余 6 句读速慢一些的没列在这里」；点「第 7 句之前」的跳转把选中行落在正确的句序上（这条一开始是坏的：空档条目带的是 `before`，跳转函数只认 `i`，点了会跳到第 1 句）。控制台除了下面那条遗留缺口的 400 之外没有别的报错。

### 一处遗留缺口（本次没动，只是发现了）

`ai_pipeline.find_pipeline_srt()` 只在同目录找 `.srt`，站点直接下回来的 `.zh-Hans.vtt` 不认，所以从播放器进「逐句校对」时打不开这种字幕（上面第二行我是靠 `/api/subtitle/qc` 直接给字幕路径量的，质检本身完全支持 `.vtt`）。它属于流水线产物查找那一层，和单步重跑共用，不该塞进 #29 里顺手改，留给下一轮定夺。

### 自检

新增 `tests/timelineqc_test.py`，**110 条**（A 覆盖率 7 / B 间隙与片尾带 13 / C 读速 14 / D 语气词与复读 13 / E 缺输入≠关闭 12 / F 媒体名回找 6 / G 流水线日志 12 / H 转写产物自检 6 / I 端点 11 / J 界面静态断言 14），全部只写 %TEMP%，`_ffprobe_bin` / `_ffprobe_info` 换成读时长表的桩子，跑完恢复原函数。D 段专门钉「只列名单不代删」：算完之后字幕文件内容与 mtime 都没变。全套 **47 套离线自检 exit 0**（含既有 46 套无回归），`node --check` 通过。

---

## #30 · CookieCloud 同步 Cookie（同一轮内，接在 #29 之后）

用户点名的第五项。Cookie 在本机一直是「一台一份、手抄一遍」：换设备、重装、或者浏览器里重新登录了一次，下载器这边还是旧的那份，表现就是「浏览器打得开会员视频，这里却说这是需要登录的内容」。浏览器扩展那边的 CookieCloud 已经在做同步了，这一轮把下载器接成它的**又一个客户端**：不改动扩展、不新起服务、也不要求用户先搭什么 —— 自建、官方托管、第三方镜像的地址都直接填进来。**默认关**，六个键（开关 / 服务器 / UUID / 同步密钥 / 写法 / 域名过滤）全空时下载链路一字不变。

### 协议按上游写，没自造一套

`GET {server}/get/{uuid}` 取、`POST {server}/update` 存，请求体是 `{uuid, encrypted, crypto_type}`，存成功回 `{"action":"done"}`。服务器地址由用户整串填（自带协议、端口，以及自建时那层 API_ROOT 子目录），代码只做 `rstrip("/")` 归一化再拼 `/get/`、`/update`（server.py:15424），所以「存进配置的那串」和「真发出去的那串」是同一个，界面回显不骗人。四条语义分开处理，没有都塞进一句「连不上」：连不上 → 502，并且带上这一趟是怎么走的（`_cc_proxy_note`，15447）；回 404 → 404 并说「先在浏览器插件里按一次『上传』」；HTTP 非 200 → 原话截 160 字；回了 JSON 但没有 `encrypted` → 「不像 CookieCloud 的 /get 接口」并附上它到底回了什么。上游有 15 分钟 100 次的限流，所以界面上**没有任何轮询**：状态只在进设置页和点完按钮之后各读一次（index.html:12275）。

### 两种写法，跟 openssl 双向都对得上

密钥材料照上游是 `md5(f"{uuid}-{password}").hexdigest()[:16]`（`_cc_key_str`，15488）。这 16 个十六进制字符既是 `aes-128-cbc-fixed` 的原始密钥（UTF-8 直接当 AES-128 key、IV 取 16 个零字节），也是 `legacy` 那条口令。`legacy` 就是 CryptoJS/OpenSSL 的口令模式：`base64("Salted__" + 8 字节随机盐 + AES-256-CBC(EVP_BytesToKey-MD5, Pkcs7))`，KDF 自己实现（`_cc_evpkdf`，15501：D1=MD5(pw+salt)、Dn=MD5(D_{n-1}+pw+salt)，前 32 字节当 key、后 16 当 IV），没有去调 openssl 命令行，也没有加新依赖 —— `pycryptodome` 本来就在 `requirements.txt` 里（第 25 行这次显式写明 `>=3.23`）。

- **`auto`（默认）不猜**：先按服务器在响应里标的 `crypto_type` 解，解不开再换另一种，两种都试过才报错，而且报错时**把两次各自失败的原因都列出来**（`_cc_try_order` / `_cc_decrypt`，15538 / 15545）。「云端不是这两种写法存的」和「UUID 或密钥填错了」因此是同一句原话里两种能分辨的说法。
- **推的时候不发明**：`_cc_do_push`（15952）用配置指定的写法；配置还是 `auto` 时退到「这一轮已经验过的写法」（状态里的 `scheme_seen`），最后才落到 `legacy` —— 官方扩展只实现了 `legacy`，所以默认往兼容那一侧写。
- 密文里的换行先抹掉空白再 base64 解（`_cc_decrypt_blob`，15522）：openssl 的输出是折行的，CryptoJS 的不是。

### 密钥这条线：不回显、不进日志、状态文件里也不留

- 六个键里只有 `cookiecloud_key` 算凭据。它**只能从 `POST /api/cookiecloud/account`（15802）这一条口子写**，留空表示「这次不改」、`clear_key:true` 才是清掉，其它写配置的接口碰不到它。`GET /api/config` 走 `_auth_config_mask`（10952）时把它强制发空串，另给一个派生的 `cookiecloud_key_set` 让界面知道「本机存过没有」，所以那个密码框永远不回填值。
- 体检导出那套 `_DIAG_SECRET_RE`（14816）是按键名整片收走 cookie 相关项的，而 `cookiecloud_scheme/domains/server/enabled` 四行只是算法、过滤词、主机名和开关，加进了白名单 `_DIAG_COOKIE_PLAIN`（14826）；`uuid` 和 `key` 留在名单之外照藏 —— 这俩是一对，藏一个漏一个等于两个都没藏。
- **机器令牌改不了这一层**：带令牌（无会话）打 `/account` 直接 403「CookieCloud 的服务器、UUID、密钥要从界面登录了再改」。「有个能写配置的令牌」不该顺手把「把 Cookie 往哪儿送」的开关也开掉。
- `_cc_redact()`（15847）：requests 的异常原话里带着完整的 `/get/<UUID>`，而这条原话会被抄进状态文件和运行日志，凡是过 `_cc_run` 的失败信息都先把当前 UUID 换成 `‹UUID›` 再落盘。
- `[CookieCloud]` 每一行日志只写主机和端口（`_cc_host`，15437），不写 netloc —— 地址里夹 `user:pass` 是常见写法，netloc 会把它一起抄出来。

### 拉下来写哪儿、推上去读哪儿

- **拉**（`_cc_do_pull`，15902）：写 `cookie_file` 那一份全局文件，再按 `_cc_platform_for()`（15617，用现成的 `PLATFORM_RULES` 认域）分派到 `cookies/<平台>_cookies.txt`；**云端这一份里真给了该平台 Cookie 的平台文件才动**，其它一个字节不碰。真被覆盖过的平台顺手 `_login_flag_clear()`，界面上那个「已登录」标记不会拿旧内容糊弄人。每个文件覆盖前留 `.bak-<时间>`（`_cc_write_file`，15670），而内容一模一样时**不动文件也不造备份** —— 不然天天同步的人手上会堆一堆没人看的备份。写完下载链路什么都不用改，yt-dlp 那边本来就读这些文件。
- **推**（`_cc_local_rows`，15722）：读全局文件 + `PLATFORM_RULES` 里每个平台的文件 + `platform_cookies` 里用户自己指过的路径，去重后按域组成 `{cookie_data, local_storage_data, update_time}` 那份形状，`local_storage_data` 推空对象（下载不读 localStorage）。这是**把服务器上该 UUID 的那一份整个覆盖**，所以只有界面上确认过的按钮能触发，别的设备之后拉到的就是这一份。
- **过滤**按插件同一口径（`_cc_filter_rows`，15610）：`.youtube.com` 命中 `youtube.com`，`m.youtube.com` 也命中。填了词却一条都不剩时报 400 并写清「云端 N 条，被滤掉 M 条」，不会静默生成一份空 Cookie 文件。
- **认不出的东西只说明，不猜**（`_cc_rows_from_cloud`，15570）：第三方客户端把 `cookie_data` 写成扁平列表的也收；某一项既不是列表也不是对象就跳过并附一句说明；云端带了 localStorage 就报「下载用不上，没写盘」。
- 时间、条数、写法存在 `web_app/cookiecloud_state.json`（server.py:65），和 `login_state.json` 一样进打包排除名单（三处，见下面第 7 条）。它是 `STATE_DIR` 里独立的一个文件，不塞进 `config.json` —— 里面有「上次拉了哪几个文件」这种会变的历史，配置那份该保持能整份抄走。写盘走 tmp + `os.replace`，写失败只让时间戳不更新，不影响这次同步本身（15756）。

### 抓出来的七处真问题（前六处来自自检，第七处来自核对打包清单）

1. **`/account` 写的是裸键，配置根本没存住**（K14）。pydantic 模型 `model_dump` 出来的字段名不带前缀（`server` / `uuid` / `scheme`），早期代码直接把这些 `cfg.data.update(...)`，于是「保存成功、界面回显正常、下次进来又空了」。改成一律落 `cookiecloud_*` 前缀键。这跟这一批开头 #206② 那一轮 `ConfigBody` 的漏口是同一个形状，只是这次发生在写侧。
2. **失败从来不进状态文件**（G17，这条是活体读数抓的，不是套件）。`last_test_ok` 只在成功路径上写，结果界面「上次测试」那一行永远显示通过，哪怕最后一回连的是个死端口。补了 `_cc_run()`（15854）把 test / pull / push 三个动作包住：失败也记时间、`ok:false` 与原话，成功时把上一条错话擦掉；三个内层函数不再自己写 `last_*`，免得两头各写一半。
3. **服务器没在响应里写 charset 时中文错话变乱码**（G10b）。`r.text` 会猜 ISO-8859-1，而自建 Docker 镜像默认就这么回。`_cc_http`（15464）改成自己 `r.content.decode("utf-8")`，原因写在那行注释里。
4. **失败原话里带着 UUID**（G18 / G19）→ `_cc_redact`。
5. **地址里带 `user:pass` 会被抄进日志和状态**（G20 / G21）→ `_cc_host`。
6. **回环地址那句代理说明在说谎**（G14–G16）：自建 CookieCloud 常跑在 `127.0.0.1:12345`，requests 对回环本来就绕过系统代理，可那句话写成「跟随系统设置的 …」。改成「本机地址，直连」。同一轮里 `_cc_write_file` 头部注释的条数原本是按去重前的行数算的（F 段），文件里实际只有去重后那些，现在先 dedup 再拼注释。

7. **新落的根目录状态文件没进打包排除名单**（这条不是自检抓的，是写文档时对着 `pack_release.py` 核对抓的）。`cookiecloud_state.json` 记的是「这台机器哪天拉过、写了哪几个 Cookie 文件」，而 README 的承诺是「本机状态文件一个都不出包」—— 排除正则、试跑后清理、出包泄漏自检三处原先都只写着 `login_state.json` / `notify_outbox.json`，新文件名不加进去就等于跟着 zip 走了。三处都补上，并落成自检的 M6 / M7（M6 专门匹配转义写法，因为字面量计数抓不到正则里那份）。`.gitignore` 不用改：它是 `/*` 起手的白名单写法，根目录新增的状态文件本来就进不了仓库。

界面这条也真坏过一次：`ccCall` 的 catch 分支只弹了个红色 toast，没重读状态，所以时间戳冻在上一回的成功上（L15）；现在 catch 里也走一遍 `loadCookieCloud()`。

### 界面

设置 → Cookie 与登录里新增「CookieCloud 同步」一块（index.html:4921）：开关、服务器地址、UUID、同步密钥（`type=password`，只有「存进去」和「清掉已存的密钥」两条路，永远不回显）、写法三选（选项文案写明白哪种是官方插件那种）、域名过滤多行框。五个按钮：保存这几项 / 测试连接 / 从云端拉取 / 本机推给云端 / 清掉已存的密钥；后四个共用 `ccCall()`（9258），各自 loading，返回的 `message` 与 `notes` 拼成一行显示在卡片里。

- **状态那一行把失败也说给人看**：`上次测试 时间（没成：原话）· 上次拉取 …（收下 N 条 / M 个域）· 上次推送 …（推了 N 条）· 云端那份的写法 …`，`ok===false` 时「没成」标红；开关关着写「现在是关的：这一轮没有向任何服务器发过请求」，开着但配不全时点名缺的是地址、UUID 还是密钥；一样都没做过写「还没测过，也没同步过」。
- 最近一次拉取实际写了哪几个文件、各多少条，单列一行（数据是状态里的 `pull_files`）。
- 「本机推给云端」的确认框把后果说满：「这会把本机 cookies 目录里那几份拼起来，把服务器上这个 UUID 的那一份整个盖掉 —— 别的设备之后拉到的就是现在这一份」，按钮是「先不」/「盖掉那一份」；「清掉已存的密钥」写「服务器地址和 UUID 都留着，但密钥要重新填才解得开云端那一份」。
- 卡片里固定写明覆盖范围与备份口径，并提示推上去是整份覆盖。

### 自检

新增 `tests/cookiecloud_test.py`，**152 条**（A 加解密与 pinned 向量 15 / B Netscape 输出 13 / C 域名过滤口径 2 / D 平台归属 5 / E 密钥材料与两种写法互不串 7 / F 拉取解析与归一化 8 / G 端点语义与失败记录 26 / H 写盘备份与清标记 16 / I 推送与状态 15 / J 完整回环 5 / K 配置与权限 18 / L 界面静态断言 15 / M 默认值与打包排除 7）。两个支点是这轮的关键：

- **不联网**：用 stdlib 起了一个真的 CookieCloud 假服务器（`ThreadingHTTPServer`，127.0.0.1 随机端口），按模式回 200 正常密文 / 404 / HTML 页 / 无 `encrypted` 的 JSON / 500 / `action=error`，端点这一路是真发一次 HTTP，不是打桩返回值。
- **向量不是自己算自己**：A 段两条 pinned 密文是 `openssl enc` 3.5.5 用套件自己的 UUID/密钥（密钥材料 `b64c5eb8065b3c7e`）现生成的，正向证明我方解得开上游写法；E 段反向证明我方 `_cc_encrypt` 的密文 `openssl -d` 解得开 —— 两个方向 × 两种写法四条边都实测过。踩到的三个坑记在注释里：`-a` 从标准输入要行尾换行、`-S` 在 3.5 不再吐 `Salted__`、比对要先解析成 JSON 再比（CryptoJS 与 `json.dumps` 的序列化本来就不逐字节相同）。
- 全部只写临时目录；`http_proxies` / `system_proxy_detail` / `_cc_proxy_note` 这些被打桩的函数在 `finally` 里恢复。H 段专门钉「云端这一份没给某平台就不碰它的文件」，J 段是 push → 删本机 → pull 的完整回环（比内容而不是比条数）。

全套 **48 套离线自检 exit 0**（`suites=48 bad=0`，既有 47 套无回归），`node --check` 通过。

### 活体读数

改完按要求重启了 8765（现 PID 52100），五个接口真走了一遍：

- 默认状态 `GET /api/cookiecloud` 回 `enabled=false`、四个串全空、`key_set=false`、`schemes` 三项、`platforms` 列出 18 个平台各自的文件路径，`cookies_dir` 与 `cookie_file` 是真路径。
- 缺哪一层报哪一层：只开总开关 → 400「没填 CookieCloud 服务器地址：插件设置里那个『同步地址』，端口和子目录一起抄过来」；地址写成 `127.0.0.1:12345` → 400「要带 http:// 或 https://」；地址对了没密钥 → 400「没填同步密钥：这份只存在本机 config.json 里，界面不回显、日志里也不写」。
- 指向一个没人听的端口测连接 → 502「连不上 127.0.0.1:1：ConnectionError …（本机地址，直连）」；**状态文件里同一句存成 `…/get/‹UUID›`**，`grep` 整个 `app.log` 与状态文件都读不到那串 UUID，也读不到密钥。
- `GET /api/config` 里 `cookiecloud_key=""`、`cookiecloud_key_set=false`；带机器令牌 POST `/account` → 403。
- 浏览器里把整张卡片渲染读回：填地址 / UUID / 密钥 → 保存（卡片写「设置已保存：开 · 服务器 127.0.0.1:… · 加密 auto · 密钥已填上」）→ 测试连接（红 toast，那行 502 原话标「没成」，时间戳真的更新了）→ 拉取 / 推送同样如实报没成 → 清掉密钥（确认框文案读回，之后 `key_set` 变 false、密码框是空的）→ 恢复默认（关、四项清空）。控制台除了那两次故意的 502 之外零消息。

### 测试痕迹

探针状态文件 `cookiecloud_state.json` 已删（删后 `GET /api/cookiecloud` 的 `state` 回 `{}`），`config.json` 里六个键回到进来时的空值与 `enabled=false`，`cookies/` 目录下没有留下任何 `.bak-<时间>`（拉取全程没写成功过一个文件）。留下的只有 `app.log` 里 24 行 `[CookieCloud]` 探针记录 —— 那是活体实例的追加日志，里面只有已脱敏的错话（`‹UUID›`）、没有密钥，按日志只追加不改写的口径留着。

---

## #31 · 按龄清理：日志归档 / 编辑备份 / 下载成品 / 回收目录（同一轮内，接在 #30 之后）

`clearFinished` 与「清理临时文件」管的是当场那一堆，`.part` 之外的东西一直是「越攒越多、没人回头收」。这一轮加的是**按文件年龄**的那一层家务活：设置里一张「按龄清理」卡片，四个天数各管一组，**默认关**，开着也只自动收日志归档、编辑备份和回收目录里到期的那些 —— 下载成品那一档只有人先看名单、再亲手点删除才动。

### 后端

- **四组各自一条口径，天数一律按 mtime**（server.py:16039 `CL_GROUPS` / 16040 中文名）：`logs` 认 `app-YYYY-MM-DD.log`（16044 那条正则，只认归档，`app.log` 这份在用的永远不会被列进去）、`backups` 认文件名里带 `.bak-`（字幕/文本编辑时留的那些）、`downloads` 认下载目录里的媒体与字幕成品、`trash` 认回收目录里待够天数的。按 mtime 而不是按历史里的记录时间，是因为历史会改写、会导入，而文件最后被动过没有就是没有。
- **默认值就是「不碰」**：`cleanup_enabled=False`、`cleanup_log_days=7`、`cleanup_backup_days=0`、`cleanup_download_days=0`、`cleanup_trash_days=30`（server.py:3560 起）。天数填 0 = 这一档整条不扫（16223 直接带 `note` 返回空名单），所以升级上来什么也没填的人，行为跟从前一字不差。
- **成品不硬删，先进回收目录**：`downloads` 与 `backups` 命中的是 `shutil.move` 进 `<下载目录>/_cleanup_trash/`（16030 `CL_TRASH_DIRNAME`，子目录结构按相对路径保住，16478 `_cl_rel_for`），在里面待够 `cleanup_trash_days` 才由 `trash` 那组真删；日志归档是直接删（它本来就只是历史）。账本 `manifest.json` 记着每一条的来路与落处（16207 `_cl_manifest_save`），所以「放回原位」是有账可查的放回，而不是猜。
- **放回时原位置被占就不覆盖**（16548 `_cl_restore`）：那份可能是重新下过的新东西，宁可留一条 `refused` 让界面点名，也不悄悄把用户的东西换掉；账本里那条留在原地不动，回头还能再放。
- **两道 dry-run**：`POST /api/cleanup/preview`（16761）只算名单、指纹、体积，一个字节都不碰盘；`POST /api/cleanup/run`（16773）必须带上刚生成的指纹，`_cl_apply` 进来先比指纹（对不上 409「这中间磁盘上的东西变了」），再看有没有过 `CL_PLAN_TTL=600` 秒（16395–16400），然后**重算一遍 plan 再比一次**（16401–16403）才算真动手。客户端传来的永远是组名，路径一律由服务端重算（16388）。界面上「按名单删除」那颗按钮在名单超过十分钟后直接置灰，跟后端同一条线。
- **正在用的东西护住**：`_cl_busy()`（16127）把排队中、下载中、暂停、稍后四种状态和**仍在做种的任务**占住的路径收成精确集合 + 目录前缀集合；做种那条是整个目录都护 —— 种子目录里的文件 mtime 可能很旧，按龄看全该删，其实正被占用。名单里不会出现它们，运行时会再挡一次（16420），界面和日志都报「护住 N 个」。`.part` / `.ytdl` / `.temp` / `.aria2` 仍归原来那个「清理临时文件」按钮管（16036），这一轮不抢它的活。
- **回收目录不会被当成成品**：`CL_SKIP_DIRS`（16043）里带着 `_cleanup_trash`，媒体库扫描与这四组走盘都跳过它连同它的子目录（不是只挡一层）。挪出原位的文件顺手从 `library_cache.json` 摘掉（16346 `_cl_forget_library`），放回后再扫一次就回来了。符号链接不跟着删（16090 `_cl_walk` 只对真文件下手）—— 跟过去删会把盘外的东西一起带走。
- **一趟最多翻 20000 个、逐条只列 200 条**（16031 / 16032）：目录被挪走、深到没边时不把进程拖死；名单超上限时明确写「另有 N 个同规则的没列出来，这一轮也不动它们」，而不是让人以为看到的就是全部。
- **闹钟**：`start_cleanup_scheduler()`（16668，启动时 22803 调）排一个 `threading.Timer` 到每天 `03:05`（16033 `CL_AUTO_HOUR` / 16034），响完再排下一次；保存设置后按新时间重排（16751 那句 `_cl_arm()`）。进程在那个点之后才起来（或者压根没开着过夜）时，`_cl_auto_due()` 认状态文件里的 `auto_date`，**开机补一趟**，一天最多一趟。自动那一趟走 `_cl_apply(groups=CL_AUTO_GROUPS, by="auto")` —— `CL_AUTO_GROUPS` 里没有 `downloads`（16042），这条是代码层面的，不靠界面别给按钮。
- **和既有日志轮转接上，不另起一套**：`LOG_KEEP_DAYS` 那个写死的 7 天改成读 `cleanup_log_days`（server.py:4078–4088 与 4113 两处），开着按龄清理就按填的天数删、填 0 就一份都不删，没开才退回默认 7 天。
- **写这条口子的门禁**：`POST /api/cleanup/account`（16729）是唯一能改这四个天数和总开关的口子，带机器令牌（不带会话那种）打它直接 403 —— 「有个能写配置的令牌」不该顺手把「会删文件的开关」也开掉；负数与超过 3650 天 400，`ids` 空的还原 400。
- `cleanup_state.json` 只记上次跑的时间、组、条数与体积（16507 / 16515），和 `config.json`、`notify_outbox.json`、`login_state.json`、`cookiecloud_state.json` 一起进打包排除清单（pack_release.py:90、333、706 三处同步），记着这台机器删过什么的东西不跟着包走。

### 界面

设置页那张卡片：总开关 + 四个天数、四颗按钮（保存这几项 / 先看名单 / 按名单删除 / 看回收目录），名单按组列出「文件 · 最后动过 · 多少天 · 大小」并逐组标清是「直接删」还是「挪进回收目录」，每组末尾一颗「只清这一组」。回收目录那张表带「挪进来」时间、原来在哪个路径、单条放回与全部放回原位，没账的那些写明「没有账，不知道原位置」并把按钮置灰。「上次自动 / 上次手动 / 回收目录里现在几个文件」都从 `GET /api/cleanup` 一次读回，进设置页时读一次，没有轮询。

### 自检

`tests/cleanup_test.py`，**156 项**（A–P 段）：默认关时四组都空、天数 0 整条不扫、mtime 口径、名单指纹与 TTL（拖过十分钟那颗 409）、指纹对不上时的 409、run 只认组名不认客户端路径、正在下/暂停/做种的路径不出现在名单里、`.part` 那类不抢、符号链接不跟删、回收目录连同子目录被媒体库跳过、账本自己不算「回收目录里的一个文件」（空目录报 0 不是 1）、挪走的从 `library_cache.json` 摘掉、放回不覆盖被占的那条与它留在账本里、机器令牌 403、天数越界 400、下载目录整个不存在时不炸、名单按体积从大到小排与 200 条上限。全程只写临时目录，`finally` 里把 `cfg` / `log_mgr` / `queue` / 状态文件路径 / 各缓存与目录常量全部还原，`_CL_TIMER` 的闹钟取消。全套 **49 套离线自检 exit 0**（`suites=49 bad=0`，既有 48 套无回归），`index.html` 内联脚本语法检查通过。

### 一处活体读数抓出来的文案 bug（在我自己新写的代码里）

还原那行日志原来是 `f"[清理] 还原 {len(restored)} 个（回到原位），" + (…if refused else "")`：只放回成功的时候尾巴上挂着一个空逗号（线上读回来就是 `[清理] 还原 1 个（回到原位），`），而**一个都没放回（全被原位置挡住）时它一个字都不写** —— 界面看得见 refused 列表，只看日志或走 Telegram 的人等于没发生。改成按实际状态拼这一段（`restored` / `refused` / `errors` 三样谁有写谁，只要动过就记），并落成两条自检（N18 钉那句原文没有尾巴逗号，N19/N20 钉「全被挡住时也有日志、被挡那条不丢」）。

### 一处遗留缺口（本次没动，只是发现了）

`mcp_server.py` 的工具清单是从 `<BASE>/openapi.json` 现取的（不手写、接口增减自动跟上），所以这六个 `/api/cleanup/*` 也一并挂给了智能体：带机器令牌的调用方**先 `preview` 再 `run`** 是走得通的 —— 指纹那道门只保证「删之前看过名单」，不保证「看的人是登录进来的」。本轮守住的是「开关与四个天数只能从 `/api/cleanup/account` 写，令牌 403」，而 `run` 这一头沿用了项目里既有那条约定（`/api/cleanup-parts`、删任务、清历史这些动本机数据的口子，机器令牌都能打）：自动化的正当用法就在这些口子上，把它们一起关掉是另一件事、要单独定口径，不该塞进本轮顺手改。真要收紧，正确的形状是「`run` 只认会话不认令牌」，同时给 MCP 那一侧留一句明确的「这条得有人在界面上点」，而不是补一个 `if` 就完事。

### 活体读数

改完按要求重启了 8765，六条接口真走了一遍：

- 昨日 21:31 那趟完整回环（真下载目录）：`preview` 报「日志 0 个 / 备份 0 个 / 下载成品 6 个 / 回收目录到期 0 个，合计 1346.6 MB（一个都没动）」→ `run` 带指纹回执 `moved=6 deleted=0`，日志记「挪进回收目录 6 个、直接删 0 个，腾出 1346.6 MB」→ `GET /api/cleanup/trash` 列回 6 条各带原路径 → `restore` 放回 1 个 + 全部放回 5 个，`Downloads/_cleanup_trash/` 里只剩一个 18 字节的空账本，`GET /api/cleanup` 的 `trash_count` 回到 0。
- 今日 09:20 重启后再取一遍（今天的构建带着那处日志改法）：`GET /api/cleanup` 回 `enabled=false`、`log_days=7` / `backup_days=0` / `download_days=0` / `trash_days=30`、`auto_hour=03:05`、`trash_dir` 是真路径、`last_manual` 就是上面那趟（`moved=6 / 1346.6 MB / errors=0`）；`POST /api/cleanup/preview` 四组都在（各自带 `days` / `count` / `hard` / `rows`），合计 0 个 —— 日志归档最新的 `app-2026-10-14.log` 距今不到 7 天，这一轮的 0 是对的。
- 前端契约对着活体读数核过一遍：卡片里用到的 `cl.*` 十个字段全部在 `GET /api/cleanup` 的返回里，名单表七列与回收目录表四列要的 `rel` / `mtime_str` / `age_days` / `bytes` / `id` / `orig` / `moved_str` 也都在，`_cl_plan()` 每组都带 `group`（`v-for` 遍历对象只给值不给键，那颗「只清这一组」靠它）。
- 浏览器里的目视渲染这轮没做（自动模式下网络与浏览器动作被拦在门外，改动又只是一行日志文案），所以上面是接口层与代码层的核对；目视那一遍留给出包前那轮统一复检。

### 测试痕迹

`cleanup_state.json` 留着上面那趟 `last_manual` 的记录（这台机器自己删过什么，正是不出包的那个东西），`Downloads/_cleanup_trash/` 只剩空账本 `manifest.json`，`Downloads/` 里六个文件都回到原位（大小与 mtime 都没被改写）；`config.json` 五个键没被这轮改动过（还是默认值与 `enabled=false`）。运行日志里 `[清理]` 那几行按只追加不改写的口径留着。

## #32 · 设置改动自动保存（只交改动项）+ 单项 / 一键恢复默认（同一轮内，接在 #31 之后）

「改完记得点保存」这一条一直有两个洞：一个是人改了开关就切走，值回到原样；更要紧的是另一个 —— 那颗按钮交的是**整包回存**，界面把打开这一页时读回来的那一份全数 POST 回去，于是页面开着的时候由别的入口（磁力页、订阅页、另一个页签、`/api/config` 本身、程序自己）改过的键，会被这份旧快照一起盖回去，而界面上一个字都不提。这一轮把写入改成**只交改动的那几项**，并补上「哪几项和出厂默认不一样、点一下拧回去」。

### 后端

- **一份配置写入只有一条通路**：`_apply_config()`（server.py:13358）承接原来 `api_set_config` 那 140 行校验与副作用，`POST /api/config`（13353）只剩一行 `body.model_dump(exclude_none=True)`，`POST /api/config/reset`（13579）也调它 —— 「恢复默认」不是另开一条宽松闸门，夹取、逐行核对、`ffmpeg_path` 落地、队列重泵、写盘、日志一次不缺。
- **空请求不落盘**（13362）：一项都没交就直接回 `ok + 整份配置`，既不写文件也不在日志里记一句「0 项变更」。
- **默认表由后端算，界面不抄第二份**：`GET /api/config/defaults`（13556）列的是 `cfg.DEFAULTS`（200 键）∩ `ConfigBody` 字段（163 个）**再减掉那四样**（`_cfg_defaultable()`，13546）= 163 项。这条交集线必须钉着：只按 `DEFAULTS` 列会把界面根本写不进去的键也列进去，表现就是「点了恢复默认，什么都没发生」—— 没在 `ConfigBody` 声明的键在 `model_dump(exclude_none=True)` 那一步就掉了（本项目 G2 那一类）。
- **每一项报三端**：`default` / `value` / `differs`，外加 `secret` 与 `filled`。名字里带 key / token / secret / password / sendkey / passwd 的（`_CFG_SECRET_NAME_RE`，13513）值与默认**两端都回空串**，只回「已填」，差异却照旧按真值算 —— 不泄密也能告诉人哪一项动过。
- **这门锁本身和它的钥匙不在表里**：`CONFIG_RESET_FORBIDDEN`（13510）= `secret_key` / `web_auth_password_hash` / `web_auth_machine_token` / `cookiecloud_key`，一键恢复与单项恢复都点不到它们；单项请求里混进它们时**不整体失败**，认得的照常恢复、这些进 `refused` 并写进日志（13580）；全是这四样时 400，话是说「这门锁本身，不在默认值表里」而不是「键名打错了」。已经全是默认值时再点一键 → 400「没说要恢复哪一项」，不假装成功。
- **机器令牌这条线没被新入口稀释**：带令牌（不带会话）打 `POST /api/config/reset` 直接 403（13561），和从前「不许改访问保护那几项」同一条口径 —— 一个能写配置的令牌不该顺手把「会抹掉设置的东西」也拿到。
- **恢复之前先留一份 `config.json.bak-<时间>`**（`CONFIG_RESET_BACKUP_KEYS` 13526 / `_cfg_backup_config()` 13530）：条件是**这一轮 ≥2 项，或动的是一项密钥 / 指向本机路径的值**（下载目录、Cookie 文件与来源、FFmpeg 路径、aria2c、按浏览器取的 Cookie 表）；命名沿用字幕编辑台那套 `_edit_backup_path()`（12261，同目录、同一秒往后加序号），所以它天然归 #31 那条「编辑备份」的清理组收，不会堆到天荒地老。备份没写成**不把恢复卡住**（那样用户看到的只是「按钮按不动」），照常执行并记一行；文件名回在 `out["backup"]`，界面上说得出留在哪儿。
- **打包清单跟着改了三处**：原来那条 `\.(...|bak)$` 逮不住 `config.json.bak-20261015-101458`（它是数字结尾），于是 `pack_release.py:88` 单列一条 `\.bak-\d`，试跑后的清扫加一条 `dst.glob("*.bak-*")`（339），出包前的私密文件自查也认 `.bak-`（712）。带时间后缀的备份里就是这台机器的密钥，这条不补就是往分享包里塞 DeepL Key。

### 界面

- **差异从「刚从后端读回来」那一刻起算**：`loadConfig()` 收尾时 `markSaved()`（index.html:7576），快照没建立之前一律不写（12491）—— 拿着默认值去覆盖真配置是最坏情况。
- **改完停手 700ms 自动写，且只写改动项**：深 `watch(settings, …, {deep:true})`（12629）+ 防抖（`AUTO_SAVE_MS`），写正在飞的时候又改了 → 这一轮完事再补一轮（12613），不把改动卡在界面上；`pendingAutoSave()` 只碰后端认得的键 —— 认得的键名从 `GET /api/config` 实际回的那份收成 `CFG_KNOWN`（7570），界面里多出来的键发过去只会被丢掉，所以既不自动存、手动存时也点名说出来。
- **十栏不参与自动保存**（`AUTO_SAVE_OFF`，12456）：限速时段、队列定时窗、每队列窗、自定义 yt-dlp 参数、字幕术语表、tracker 名单与来源、自动分类规则、按平台代理、访问保护开关 —— 半截写法存过去只会被后端顶回 400，它们各有「检查格式 / 保存」那颗按钮负责落盘。访问保护开关单列是因为口令还没设就自动把门锁上，等于把人自己关在门外。
- **清空成 null 的项当场说清**：`ConfigBody` 163 个字段全是 `Optional`，交 `null` 等于没交，所以界面把这类项挑出来标「空值后端不收 —— 要回出厂值请用「恢复默认」」，而不是静默失效。
- **新卡片「改动怎么存 · 恢复默认」**（4116，设在设置页最前面）：一句说明哪些改完即存、哪些不自动存；状态行（`N 项待保存：并发数 / 限速…` 或 `已自动保存 N 项`）；「重新核对默认值」；「一键恢复默认」；以及逐条列出与默认不一样的那几项，每条写 `现 X → 默认 Y` 带一颗「恢复这一项」。中文名表 `CFG_LABELS`（12318，126 条：99 条从界面上现成的 `el-form-item label` 摘、27 条是通知 / 访问保护 / 路径那几栏手写补的），叫不出名字才退回键名。
- **一键之前先把没落地的改动写回去**（12560）：否则紧随其后的 `loadConfig()` 会拿服务端的值覆盖界面，用户刚拧的那一下被悄悄吞掉。
- **确认框点名要丢什么**：把将被清空的密钥按中文名列出来（前 6 项 + 「等」）、说明指向本机位置的值也回默认、说明改前那份存在哪个文件名，并重申那四样动不到 —— 一句「密钥类会被清空」太轻，人是在不知情的情况下丢掉自己抄了三天的 API Key。

### 自检

`tests/settingsave_test.py`（**111 条，ALL GREEN**；只写 %TEMP%，`cfg` / 日志 / 队列 / `CONFIG_FILE` 全换假的，末尾 Z1 逐字节比对真那份 `config.json` 没被动过）。A 段：可默认名单 = `DEFAULTS ∩ ConfigBody − 那四样`、`ConfigBody` 没有孤儿字段、全默认时差异为 0、改两项差异就变 2。B 段先**证明旧写法真会盖**（页面打开后别的入口把 `speed_limit` 改成 `2M`，整包回存把它盖回空），再证明新写法不盖、一次改动只落一次盘、日志写「（1 项变更）」。C 段：单项恢复只动那一项、`refused`、空请求 400、那四样 400 且话说是门锁、混着交不整体失败、机器令牌 403 两处。D 段：一键抹平 4 项差异后 `differs=0`，再来一次 400。E 段：表 / 列表给出去的是拷贝，`DEFAULTS` 全程没被写脏。F 段：默认表、`GET /api/config`、日志**三处都不含密钥明文**，密钥项的 `value`/`default` 两端都是空串而 `filled`/`differs` 照样准。G 段：`null` 等于没交、空串才是清空。H 段：同一道闸门还在（口令没设就开保护 400 且不写盘、非法编码模式 400、越界数字夹住、认不出的主题退回默认）。I 段扫 `index.html`：126 个 `v-model="settings.X"` 全部 ∈ `ConfigBody` ∩ `DEFAULTS` 且在 `CFG_LABELS` 里、`JSON.stringify(settings.value)` 一处不剩、`CFG_KNOWN` / `CFG_SNAPSHOT.ready` / 防抖 / 补那一轮都在、模板要用的名字都从 setup 交了出去。J 段：日志只有条数与键名。K 段：备份的九种情形（单项非密钥不留、密钥项留、备份里就是改前盘上那份、同秒两份不互相覆盖、盘上没文件不报错、备份写不下去不卡住恢复、回包永远带 `backup`）。L 段：打包那三条 `.bak-` 规则。

全套 **50 套离线自检 exit 0**（`suites=50 bad=0`，既有 49 套无回归），`python -m py_compile server.py pack_release.py` 与内联脚本 `node --check` 通过。

### 一处活体读数抓出来的自伤（记在这儿，免得下次重犯）

第一轮活体读数在**真实例**上点了「一键恢复默认」，把这台机器的 19 项真设置连同 `hf_token`、DeepL Key、AcoustID Key、8 条按浏览器取的 Cookie 表、`whisper_model=large-v3`、`po_provider_enabled`、风控三档一起拧回了出厂值。功能本身按规格做的（一键就是真的一键，确认框也弹了），但这一趟让我自己成了这个按钮的第一个受害者：动手前 cp 的那份 `config.json` 副本救了回来，逐值比对后**盘上现在这份与进来时差异键数 0**，探针留下的 `config.json.bak-20261015-101458` 和临时副本都已删掉。这件事就是 K / L 两段与「确认框点名密钥」的由来：**恢复默认可以真恢复，但必须可反悔、必须说清会丢什么。** 之后的活体读数只在真实例上动我自己设的那两项，并在结尾做一次逐值比对。

### 活体读数

改完重启了两次 8765（最终 PID 24292），第二次的构建带着备份那一段：

- 默认状态 `GET /api/config/defaults` 回 `count=163`、`differs=19`（这台机器真动过的那 19 项）、`forbidden` 是那四样，条目里 `default` / `value` / `secret` / `filled` / `differs` 五个字段都在。
- 只交 `proxy` 一项之后：`proxy="http://127.0.0.1:18888"` 落地，同时 `hf_token` 还在、`whisper_model=large-v3` 还在、8 条 `platform_cookies` 一条没少 —— 这就是「不盖别的入口」在真配置上的样子。
- 填一个 Bot Token 后再取默认表：整张表里 `LIVE-LEAK-NOPE` 出现 0 次，那一项回的是 `{"default":"","value":"","secret":true,"filled":true,"differs":true}`。
- `POST /api/config/reset {"keys":["telegram_bot_token"]}` → 200、`restored=["telegram_bot_token"]`、**`backup="config.json.bak-20261015-101458"`**，日志同一句：`[界面] 恢复默认：1 项（telegram_bot_token），改动前的配置留在 config.json.bak-20261015-101458`；随后 `{"keys":["proxy"]}` → `backup=""`（单项、非密钥、非路径，不留噪音）。
- `{"keys":[那四样]}` → 400，逐条点名「这门锁本身，不在默认值表里」；`{}` → 400「没说要恢复哪一项」；`{"all":true}` 在已经全是默认值时 → 同一个 400。
- 收工逐值比对：`config.json`（盘上）与进来时那份差异键 0，`GET /api/config/defaults` 的 `differs` 回到 19。

### 目视那一遍还是没做

`browser-use` 导航这轮同样被自动模式拦在门外（和前几轮一致），所以「改动怎么存 · 恢复默认」这张卡的实际渲染 —— 尤其 19 条差异项在 `env-list` 里的排版、以及改一个下拉时状态行是否真的从「N 项待保存」翻成「已自动保存 N 项」—— **没有目视证据**，只有代码层与接口层。留给出包前那轮统一复检。

### 测试痕迹

`config.json` 已逐值恢复到来时那份（差异键 0，`differs` 也回到 19），探针产生的 `config.json.bak-20261015-101458` 与 `_cfg_pre32.json` 临时副本都已从工程目录删掉，`web_app/` 下现在没有 `*.bak-*` 残留；备份相关的所有写入都落在 %TEMP% 的 `md_settingsave_*` 里，随套件结束删除。`app.log` 里这轮多出的 8 行（6 条 `[界面] 保存设置（1 项变更）`、2 条 `[界面] 恢复默认：…`）是活体实例的追加日志，只有条数、键名与备份文件名，没有配置值 —— 按日志只追加不改写的口径留着。

## #33 · 翻页面不再写运行日志（同一轮内，接在 #32 之后）

日志页以前每点一次侧栏就多一行 `[界面] 切换到「X」`。这行对排查没有用（不写任何东西、不取任何数据），却有实打实的代价：日志页只展示最近 200 条，翻一遍 17 个页面就吃掉 17 行，把真正的写操作与失败记录往上顶。这一轮把它去掉 —— **只读导航不该冲掉真记录**。

### 界面（唯一动的一处代码）

- `index.html:12851` 的 `watch(page, (p) => { … })` 里删掉那一行 `logAction('切换到「' + (pageTitle.value || p) + '」')`，原地留一句为什么（这种「少了的一行」最容易被人当成遗漏顺手加回来）。同一段回调里的其余部分一个字没动：入场动画那两步（`classList.remove/add('is-enter')` 与 `void c.offsetWidth` 那次强制回流）、12 个页面各自的按需加载（`loadTasks` / `loadSeeding` / `loadBtTrackers` / `loadLiveMonitors` / `loadHistory` / `loadLogs` / `loadFiles` / `loadSubs` / `loadCatcatch` / `loadFavTab` / `loadMusicFavs` / 设置页那八只 / `loadTgMtStatus`）全都留在原处 —— 删的是日志，不是加载。
- **留下的界线**（不是「凡是界面事件都不记」）：`logAction('通知跳转：…')`（11632）与 `logAction('弹窗跳转：设置 → 组件与依赖')`（7267）保留 —— 那是点系统通知、点更新弹窗这种外部触发的一次性动作，一次一下、不刷屏，而且确实说明「这个人是怎么到这一页的」；主题与明暗（7586 / 7602）保留，因为它们真的往 `config.json` 写 `ui_theme` / `dark_mode`；表头排序、翻页、进目录、取回多少条这类读数也一律照旧，它们本来就不是这一条要收口的对象。**这一轮只收掉「切页」这一种事件**，没有顺手把埋点整层拆了。
- 日志页顶部那行提示补一句口径：「本页最多显示最近 200 条（记的是写操作、失败与点通知跳过来的那一下，光翻页面不占行）」（`index.html:2827`），让用户知道少掉的是哪种行，而不是以为日志坏了。

### 后端：一处没动，是有意的

`POST /api/ui_event`（`server.py:14949`）原样保留：`api_ui_event` 不知道也不需要知道发来的是切页还是点按钮，脱敏在前端发之前就做完（`SENSITIVE_RE`），后端只做「压平空白、截 200 字、level 只认 info / warning、空文本不记」。少发一类事件 ≠ 换一条通道。

### 自检

新增 `tests/navlog_test.py`，**43 条全绿**，三段：

- **A 段（10 条）**：后端通道的口径 —— 正常一句记成 `[界面] …`、返回值只有 `ok` / `level`（不夹带配置或任务）、空文本与纯空白都不记、`\n` 与连续空白压成一行、400 字截到 200、`level` 传 `error` / 空串 / `<script>` 都落回 info（**界面这条通道写不出 error 级**）、后端不做二次改写、同一句发两次记两条（埋点不去重，去重会把「用户真点了两下」抹掉）。
- **B 段（17 条）**：静态钉住「该删的删了、不该动的没动」—— 切页回调里没有 `logAction`，全站再没有 `logAction('切换到…`，写操作分支 / 失败降 warning / 只认非 GET / `/api/ui_event` 自身排除 / `noLog` / 敏感词那道 `SENSITIVE_RE` 全在，通知跳转与弹窗跳转与主题明暗这四处**明确留着**（钉的是这条界线，不是顺手记下的数字），日志页那句新文案在，`pageTitle` 仍被页头用着（不是把变量一起删了），入场动画那行还在。
- **C 段（15 条）**：行为层，照 `paste_test.py` 的路子把 `watch(page, (p) => { … })` 的**回调体**与 `async function api()` **原样抠出来**交给本机 node 跑（不复制第二份实现，改了就测到）。回调体外面套一层 `with (proxy)`，任何名字都给一个「能调用、有 `.value`、再点下去还有下一层」的替身，于是 17 个页面键逐个跑一遍：**发出去的埋点为空**（`C1`），而每页该取的 `load*` 一个没少（`C2` 按 12 页各自的期望名单核对）、`home` / `info` / `search` / `library` / `voice` 这五页跑完只剩动画那一步（`C3`，防止有人日后往这里塞别的事件）。`api()` 那半边用桩 `fetch` 跑六次：GET 不记、POST 记一行且名字来自 `actionName`、`noLog` 不记、打到 `/api/ui_event` 自己不再进埋点（否则递归）、带 `uiName` 的记按钮名、401 失败记成 `…（失败）` 的 warning 但**仍然把错误抛出**、PUT 也算写操作。
- **反向验过一次**：把删掉那行原样塞回 `index.html` 再跑，`B3` / `B4` / `C1` 三条一起红，`C1` 的读数就是 17 页各发一条（`{'home': [['切换到「home」', 'info']], …}`）—— 这三条真能守住这件事，不是空转。改回去后 43 条重新全绿。

### 活体读数（127.0.0.1:8765，改的是前端，不需要重启）

- `GET /api/logs` 当时回 18 条，其中 `[界面]` 10 条、`[界面] 切换到「…」` **4 条**（设置 ×2、运行日志 ×1、聚合搜索 ×1）—— 也就是说这台机器上 40% 的界面行是翻页面翻出来的，而这 4 条对排查没有任何贡献。
- `GET /static/index.html` 直接取回线上正在发的那份（685,159 字节），里面 `logAction('切换到` 已经搜不到、新那句「光翻页面不占行」在 —— 静态文件是每次请求读盘的，前端改动不用重启就生效，这一点顺手确认过，没有靠「刷新一下应该就好了」。
- 通道本身打了一枪：`POST /api/ui_event {"text":"活体读数：写操作仍会记这一行（#33 之后口径不变）"}` → `{"ok":true,"level":"info"}`，日志 18 → 19 条；再发一条纯空白的 → `{"ok":false}`，条数不动。上面那 4 条历史「切换到」仍留在日志里（只追加不改写，不替它们做清理）。

### 目视那一遍还是没做

和前几轮同样被自动模式拦在门外。这一轮的界面变化只有日志页顶部一行提示文案，**没有目视证据**；「翻页面时日志页确实不再新增行」这件事在 node 那层是实测过的（`C1`），但「日志页那个列表在界面上不再往上蹿」没看。留给出包前那轮统一复检。

### 全量回归

`python -m py_compile server.py pack_release.py` 通过（这一轮 `server.py` 没改，一并编译只是守住能编）；`index.html` 里那段 342,923 字的内联脚本 `node --check` JS-OK；离线自检按目录 `tests/*_test.py` 逐个跑（含新增的 `navlog_test.py`），**suites=51 bad=0**。

### 测试痕迹

这一轮的改动全在 `static/index.html`（两处：切页回调删一行 + 日志页提示加半句）与新自检 `tests/navlog_test.py`；`config.json`、`history.json`、下载目录都没碰。node 的临时件在 `%TEMP%\navlog_harness.js` 与 `%TEMP%\navlog_result.json`，随下次覆盖，不在工程目录里。`app.log` 多出 1 行 `[界面] 活体读数：写操作仍会记这一行…`（那一枪的产物，按只追加的口径留着）。

## #21 · 成品校验值核对：入队收一条期望 MD5/SHA，下完对成品算一遍（同一轮内，接在 #33 之后）

发布方附一枚校验值是常见做法，以前这一环只能靠人自己拿工具算。这一轮把「期望摘要」做成入队时可选的一项：完成后对成品实算一次同算法的摘要比对，**一致就只在运行日志留一句，对不上才在卡片上写一行**（提醒，绝不删文件），走的是 1.3.2 那条 `verify_note` 通道 —— 卡片行、历史悬浮、运行日志三处都已经就位，没有新加键、没有新加列。

难点不在算摘要，六行 hashlib 的事；难点在**「对不上」这句话该怪谁**。站内解析下来的成品默认还要转封装、嵌封面/元数据/章节/字幕、剪 SponsorBlock —— 每一步都重写文件字节，拿发布方给的 MD5 去对这种成品，对不上是应该的。如果只做「不等就报警」，这个功能天天在喊狼来了，等于没有。

### 后端

- **规范化只有一份**：`normalize_hash_expect(value, algo)`（server.py:21963）返回 `(hex, algo, err)`。它先把 `md5:` / `SHA-256=` / `校验值：` 这类前缀剥掉（`_HASH_PREFIX_RE`，21945），把空格、`;`、`-` 清干净（UUID 式带连字符的摘要能粘对），再按位数反推算法（`_HASH_ALGOS`，21942：32=MD5、40=SHA-1、64=SHA-256、128=SHA-512）。别名收成同一个名字（`SHA1` / `sha-256` / `sha256sum` 都行），**故意不给裸 `sha` / `sha2` 定性** —— 那两种写法本身就没说清是几代，交给长度去反推，反推不出来就报错。Base64 明拒（错误文案里点名「这里只收十六进制」），非 hex 字符那一句会指出是第几个字符、长什么样。
- **点明算法是为了当场拦住复制漏字符**：选了 SHA-256 却只粘来 63 位，入队就被顶回（「应该是 64 位十六进制字符，可这串只有 63 位…看着更像 MD5」）。这是全链路唯一一次能发现「少粘了一个字符」的时机 —— 等下完再算，只会得到一句「对不上」，而它说的其实是另一回事。
- **两道闸各管各**：`download_preflight`（server.py:13812 起）硬校验并在出错时 400，同时把规范化后的值**写回 `opts`**（13815-13816），`Queue.add_urls`（9438）再规范化一次兜住别的入队口（订阅规则、嗅探、MCP —— 那些口不过 preflight），两道是幂等的（自检 A13 钉的正是这个）。别的口交来一串不像摘要的东西时不拦整批，只记一行 warning 并把它丢掉，不让一条脏值连累同批其余链接。
- **声明到接口层**（这一条差点又走成上一轮那个 G2）：`AddUrlsBody`（server.py:11086-11087）加了 `expect_hash: Optional[str] = None` 与 `hash_algo: str = "auto"`，自检 E 段用 `model_dump(exclude_none=True)` 真跑一遍确认这两行活下来。
- **三种结论、两句话术**：`hash_readback()`（22057）回 `(state, 实算摘要, 上屏那句话)`。一致 → `ok` 且话术为空；读不到成品（被移走 / 没权限）→ `unknown`，只说「这一项没法判」；对不上分两种说 —— 本机会重写成品时点名是哪几步（「和上游那份原文件的摘要本来就不会相同」），原样落盘时才说「这份文件不是期望的那一支（上游给错、下载被截断、算法点错都算在这条里）；文件已保留，没删」。`hash_rewrite_steps()`（22020）是那几步的唯一出处，从容器（`抽成音频（flac）` / `封装成 mkv`）、`audio_only`、四个 embed 开关、SponsorBlock（`"off"` 字符串不算开）、时间点选段、HLS 专用引擎、本地转写/翻译一路列下来；**磁力/种子恒回空**（aria2 原样落盘，可比）。
- **刻意没用 aria2 的 `checksum` 选项**：它认的是「不对就删文件」，而一个 torrent 会落多个文件，一条校验值覆盖不了；本机的口径是只报不删。
- 核对挂在 `verify_download` 那道闸门**之外**（10215 起的独立分支）：体检说「文件能播」，摘要说「是不是这一份文件」，两件事各有各的开关，磁力任务只想要后一句。只在 `ok` 时算，失败的单子不再白读几个 G。核对本身抛异常就跳过（`校验值核对异常（跳过）`），不把成功的任务判失败 —— 与 1.3.2 成品回读同一口径。
- `DownloadTask` 多四个字段（3492-3495）：`expect_hash` / `hash_algo` / `file_hash` / `hash_state`。**历史只多这一句 `verify_note`**（10286 那句沿用 1.3.2），没有 `hash_state` / `file_hash` 键 —— 意思是重启之后，对不上的那一句还在卡片悬浮与历史 tooltip 里，而「一致」的正面确认只剩运行日志那句。这是取舍，不是遗漏。

### 一次活体读数把设计改了：这句话不能靠预测

第一次探针（本机 http 服务上的一条 17 KB `.mp4`，期望值故意填全 0）下完，卡片写的是「这一单下完在本机还过了「封装成 mkv」这几步，成品是被重写过一遍的文件」，而实际成品与源文件**逐字节相同**、MD5 也相同 —— 那一单根本没走 yt-dlp，`fmt` 与开关只是照着配置**预测**了一遍后处理，预测错了。

改法是把「有没有被重写」交给**引擎自己那次的事实**，而不是收尾去猜：`_raw_bytes` 那张按 task_id 记的表（server.py:6119）+ `note_raw_bytes()` / `pop_raw_bytes()`（6121 / 6127），与 1.3.2 的 `_listed_max` / `pop_listed_max()` 同一套取走即清的形状；调用点只有一处，就在 CDN 直链那一支的下载动作之前（6427，紧挨着「CDN 直链下载（绕过 yt-dlp）…」那行日志）—— 这一支不转封装不嵌轨，成品就是上游那份字节。收尾拿到 `raw_bytes` 后 `hsteps = [] if raw_bytes else hash_rewrite_steps(...)`（10221），入队那句预警文案也跟着改成有条件的（「除非它按 CDN 直链原样落盘」），界面 hint 同理。

顺带把「为什么 .mp4 直链总能落进原样那一支」查清了：随包的 `plugins/example_passthrough.py` 对任何以 `.mp4/.flv/.mkv/...` 结尾的 URL 都返回 `direct_cdn: True`，而插件选项覆盖入队参数 —— 探针里显式传 `direct_cdn=false` 因此完全没起作用。这不是 bug（直链走 yt-dlp generic 反而更慢更不稳），但它说明了文案为什么必须写两种：站内解析那一路才是会被重写的那一路。

### 界面

- 「精细控制」末尾多一张 tile「期望校验值（可选）」（`index.html:1857`）：一个输入框 + 算法 chip（自动 / MD5 / SHA-1 / SHA-256），hint 里写清位数反推算法这件事、以及**哪一类成品才是可比的**。`opts` 默认 `expect_hash: ''` / `hash_algo: 'auto'`（5850-5851），四个入队口（普通 / 磁力 / 订阅 / 批量）都靠既有的 `...opts.value` 带上，前端零接线。
- 卡片那一行的标题从「画质核对」改成**「成品核对」**（1992 / 2116 两处模板同改）：这一句现在可能来自画质回读、可能来自校验值、也可能是两句用「；」拼起来，叫「画质核对」就成了假话。
- 一致时卡片不亮行（免得每次都橙色），但用户确实问过这件事 —— `taskSpecTitle()` 的悬浮里补一句「校验值一致 · MD5 754a369d0817…」，`unknown` 给「校验值没法判：成品读不出来」（12067-12069）。历史那行仍挂在状态标 tooltip 上，表格没加列。

### 自检

新增 `tests/hashverify_test.py`，**70 条全绿**：A 规范化 14（含 A13 两道闸幂等）/ B 真算摘要 6（B3、B4 是刻意跨过 1 MB 分块边界，防止只哈希首块）/ C 话术矩阵 9（含「重写那一句里绝不能出现『不是期望的那一支』」这种反向断言、话术不超过 400 字）/ D 后处理步数 6（torrent 恒空、全关且空容器时也为空）/ E 接线行为 13（真 `TaskQueue` + 假 cfg/log 验 `add_urls` 落字段，真 `download_preflight` 只桩 `engine.check_ytdlp` / `ffmpeg_mgr.find` / `find_n_m3u8dl` / `bt_ensure` 并在 `finally` 交回）/ F 收尾静态 14 / G 界面 9。

F 段这次学乖了：锚点一律先 `SRC.find(...)` 取值再断言（新增 F0 守「锚点存在」），因为上一轮 falsification 时 `SRC.index()` 直接 `ValueError` 把整套自检崩掉 —— 崩掉不等于红，读日志的人会以为只是没跑成。反向验过两轮：把 `note_raw_bytes` 那行删掉、把 400 改成 warning，各自有对应断言变红，改回后重新全绿。

### 活体读数（本机另一台实例 127.0.0.1:8799 + 夹具 http 服务 127.0.0.1:8798；8765 全程空跑没碰）

这台探针实例是另起的端口，`telegram_enabled=false` / `web_auth_enabled=false` 先读回确认过，不会往外发通知；下载目录在 `%TEMP%`，没进 `Downloads/`。

- **一致那一支**：期望值填源文件真 MD5 → 日志 `[c5dfd444] 校验值核对：MD5 一致（754a369d0817263c…）`，任务 `hash_state=ok`、`file_hash` 与源文件同值，卡片没有多出橙色行。
- **原样落盘 + 对不上**：期望值填全 0 → 「这份文件不是期望的那一支…；文件已保留，没删」，实算摘要与源文件一致，证明读的是同一份字节。这是第一次探针报错话之后重跑的那一遍，措辞已经跟着事实走了。
- **本机重写过 + 对不上**（这一条是补出来的，不是撞上的）：把夹具改名成 `.mp4v`（MIME 仍是 video/mp4，但不在透传插件的正则里），于是这一单真的走 yt-dlp，日志明写 `目标容器=mkv 后期处理=FFmpegVideoRemuxer`，成品落成 `clip [clip].mkv`（16,954 字节 ≠ 源 17,521），实算 `74850e27…` ≠ 源 `754a369d…`，卡片那句是「这一单下完在本机还过了「封装成 mkv」这几步…本来就不会相同」。**三支话术都有活体证据了。**
- **任务字段实读**：`GET /api/tasks` 回 `hash_state="bad"` / `file_hash` / `expect_hash`，`verify_note` 里是画质回读与校验值两句用「；」拼的那一条。
- **入队当场拦下**：`format` 默认 mkv 且链接下载时，warning 文案在响应与日志里都出现（「这批里有链接下载：这一路还勾着「封装成 mkv」这几步，除非它按 CDN 直链原样落盘…」）；磁力那一单同字段则完全安静（自检 E11 钉的就是这份安静）。
- 顺带读到一个既有行为，不是本轮引进的：`.mp4` 结尾的本机 http 直链恒走 CDN 分支，插件注入的 `direct_cdn=True` 优先于入队参数。想复现「被重写」那一支得换个不被正则认出的扩展名。

### 目视那一遍还是没做

和前几轮同样被自动模式拦在门外。这一轮的界面变化是一张新 tile（输入框 + 四个 chip + hint）、卡片标题改名、悬浮多一句，**都没有目视证据**；tile 的字段绑定在自检里是静态钉住的（G 段那 9 条），chip 点下去改的是 `opts.hash_algo` 这件事没在浏览器里点过。留给出包前那轮统一复检。

### 全量回归

`python -m py_compile server.py` 通过；`index.html` 内联脚本 343,274 字 `node --check` JS-OK（整份 HTML 774,655 字节）。离线自检按 `tests/*_test.py` 逐个跑、以退出码判红，**suites=52 bad=0**（含新增的 `hashverify_test.py`；`hashverify` 自己 70 条 `TOTAL 70 FAILED: none`）。

### 测试痕迹

夹具与下载全在 `%TEMP%\md_hash_live\`（`clip.mp4` / `clip.mp4v` / `dl` / `dl2` / `dl3`），已整目录删除；探针实例（PID 14288）与夹具 http 服务（PID 52304）已终止，8765 那个实例（PID 24292）全程没被重启或改动。`history.json` 里那 6 行探针记录已按快照还原（39 → 33 项，`127.0.0.1:879` 一条不剩），`local_index` / `library_cache.json` / `Downloads/` 里搜不到夹具的任何痕迹。自检留下的临时目录按本轮清理（`%TEMP%\md_hashverify_*` 13 个，每个约 1.1 MB；其余套件留临时目录是既有行为，没顺手改）。`app.log` 多出约 60 行探针记录与两次实例启动行 —— 按只追加、不改写的口径留着，没有替它们做清理。`config.json` 没碰（探针实例与主实例共用它，这也是为什么这一轮所有写操作都只发生在 `%TEMP%` 的下载目录里）。

---

## #22 · 公开优先的 Cookie 策略：解析先不带 Cookie，被登录墙那类挡住才升（同一轮内，接在 #21 之后）

Cookie 这一层以前只有一条路：只要配了来源，`_cookie_source()`（server.py:5960）一解出来就无条件挂进 `_ydl_opts()`，**每一次解析、每一次下载都带上它**，没有「先不带」这个选项。对必须登录的内容这是必需的，对公开就能看的东西则是每回都把登录态多送出去一次；而且这一次并不白送 —— 带 Cookie 时 yt-dlp 会跳过 android/ios 两条客户端链（6374-6384 那段耦合），匿名那次和带 Cookie 那次**本来就不是同一份清单**，不是「同一份的删减版」。现在加一档 `cookie_public_first`（默认关）：开着时每条链接先按「没登录」解析一次，只有那一次被登录墙 / 会员 / 年龄 / 风控校验那类挡住、或只给到被裁的清单，才带 Cookie 再解析一次；判过的结论按链接记 15 分钟，下载沿用同一次判定。**关着时与从前一字不差** —— 这句话是靠默认值、自检 E1/E2 和活体 L1 三头钉住的，不是读代码读出来的。

### 后端

- **档位与接线**：`ConfigManager.DEFAULTS` 加 `"cookie_public_first": False`（server.py:3553），`ConfigBody` 加 `cookie_public_first: Optional[bool] = None`（11322）—— 少了后一行，这个键会在 `model_dump(exclude_none=True)` 那一步静默掉，就是本项目 G2 那一类 bug，自检 I 段逐层钉。界面侧四处：开关（`static/index.html:4963`）、`settings` 初值（5958）、`loadConfig` 回填（7472）、`CFG_LABELS`（12378，「恢复默认」那一行文案的来源）。
- **匿名那一遍怎么做到真不带**：`cfg_without_cookie()`（5774）把 `cookie_source` 打成 `none`、浏览器来源、文件路径、逐平台覆写、手工 `cookie` 串、以及 `http_headers` 里那一条 Cookie 一次清空 —— 少清一处就等于那一次还是带了。
- **判定表挂在引擎上**：`cookie_pref_state()`（5912）/ `cookie_off()`（5938）/ `note_cookie_pref()`（5942）/ `drop_cookie_pref()`（5949），状态是 `_cookie_pref`（6250，`{url: (时间戳, 要不要带)}`），TTL `_COOKIE_PREF_TTL = 900`（6251）。TTL 必须大于解析缓存的 180 秒，否则判定刚过期而缓存还热，解析侧和下载侧就会各拿一套答案（C9 钉这条）。短链展开会产出一个新 URL，两张 key 都记（`_note()`，6327），不然「用户输入那一条」在下载侧拦不住 Cookie。
- **一个出口，多处问它**：`_cookie_source()` 开头 `if self.cookie_off(cfg, url): return None, None`（5965）—— 客户端链选择（6320、6378）、`cookiefile` / `cookiesfrombrowser`、手工 Cookie 头（6045）、CDN/aria2 直链请求头（10221）全从这一处走，没有第二套判断。下载侧因此不重算，也不会在解析判了「匿名」之后偷偷把票带上。
- **重试门槛是一张排除表，不是一句话**：`cookie_might_help()`（5743）先看 `risk_control.classify_failure_text()` 的 `kind`，`RATE_LIMITED / NETWORK / NOT_FOUND` 三种**直接不重跑**（带 Cookie 对它们没有用，多打一次只会把 429 的冷却加长），`LOGIN_REQUIRED / DENIED / BOT_CHALLENGE` 和 `_COOKIE_HELP_RE`（5735，年龄墙 / 会员 / 需要登录那几句，中英文都收）才放行。
- **两次尝试共用同一个缓存位，是刻意的**：当初的打算写的是「`_info_cache` 的 key 必须分开，否则匿名那份低清会被当答案缓存 180 秒」。真做下来分 key 更糟：15 分钟后重新解析会拿到一份 15 分钟前的匿名清单当答案。现在改成**谁被返回谁占缓存位**，判「带 Cookie 那份反而更低」时连缓存位一起改回匿名那份（6354-6358），原因落在 `_get_info_once()` 的 docstring 里（6365-6366）。
- **改 Cookie 就作废判定**：`COOKIE_LAYER_KEYS`（5794，六个键名）+ `drop_all_cookie_prefs()`（5798），写在配置保存（13778，紧跟 `cfg.save()` 之后）、三个逐平台 Cookie 接口（15780 / 15800 / 15821）、CookieCloud 拉取（16399，只在 `changed` 时）、B 站扫码登录（19986）五处，外加重试任务按单条 URL 清（10754）。不这么做的话，「这条匿名就够了」那条旧判定会接着替刚换过票的配置做决定。

### 两次活体读数把设计改了（这两处都不是推出来的）

**① 重试门槛原稿会把整条链接判死。** 第一版只认「需要登录 / 会员 / 年龄」那几句，其余一律不重跑。探针（`md_ytfailure_probe.py`）拿本机一个**公开**视频跑纯匿名那一遍，回的是 `No video formats found` —— 这句在 `risk_control._ERR_RULES` 里落 `UNKNOWN`，于是原稿判「不是登录墙那类，不为此带 Cookie 重跑」，解析直接返回 None。同一条链接换成真配置的浏览器 Cookie（firefox）却给到 43 条流、最高 2160p、独立视频轨齐（那份读数的 V2）。也就是说，**这台机器上 YouTube 匿名失败的样子不是「被登录墙挡」，而是「一条流都不给」**；照原稿写死，开着这一档的人会把原本能下的 4K 公开视频下成失败，那比「省不下一次 Cookie」严重得多。现在补的是：`UNKNOWN / EMPTY` 且平台是 YouTube 时算「值得再打一次」，排除表仍然优先，429 照样不放行（A8 与 A8c 钉的就是这一对）。B 站那边不享受这个放宽，它的 `UNKNOWN` 该判死就判死。界面 hint 里那句「或一条流都不给（这台机器实测公开视频也会这样）」是这次之后补进去的 —— 文案跟着设计改，不是先写好再找理由。

**② 兜底那一次不该改判定。** 第二版在「匿名拿到了被裁的清单、带 Cookie 那次反而失败」这一支上写的是 `_note(False)`（当作「匿名够用」）+ 用匿名那份。活体里这一支就是撞 429 的那次：`_note(False)` 会把那份**被裁的**（影音同条、最高 1080p）清单钉成 15 分钟内的正确答案，接下来下的每一条都按 1080p 走 —— 正是 B3 那一轮抓过的静默降质形状。现在这句只说「先用匿名那份；这条下次解析还带 Cookie」，判定保持 `cookie`（6345-6352），E18/E19/E20 断言的是判定值本身而不是日志文案。

### 界面

开关挂在「全局 Cookie」那张卡里、Cookie 路径 hint 之后（`static/index.html:4963`）。下面那段 hint 说清四件事：关着时与从前一模一样；开着时先按没登录解析、哪些情况才带 Cookie；429 / 连不上 / 内容不存在这三类不会为此重跑；逐平台覆写照常优先，这一档只决定「第一次要不要带」。

### 自检

- 新增 **`tests/cookiefirst_test.py` 127 条全绿**：A 重试门槛 13（含 A2b「429 和 Sign in to confirm 混在同一段报文里」仍按排除表走、A8 YouTube 的 `No video formats found` 放行、A8c 同一句加 429 照样不放行）/ B `cfg_without_cookie` 7（六个入口加请求头，一例不漏）/ C 判定与 TTL 12（C0 规范化幂等、C11 短链两张 key）/ D `_cookie_source` 唯一出口 6 / E 门面分支 30（用桩盖掉 `_get_info_once`，桩按真的缓存写法镜像，所以断的是返回哪一份 + 判定记成什么）/ F `_anon_list_clipped` 8（F8：4K 影音同条仍算被裁）/ G Cookie 层失效 15（六个写点逐个点名、G4 钉在 `cfg.save()` 之后、G10 把直播聊天抓取那条链钉成「有意的例外」（它照旧按配置带 Cookie，会员直播的聊天没有匿名退路））/ H 下载侧 6 / K 真调 `_ydl_opts` 9（K2：判「匿名」时 `cookiefile` 与 `cookiesfrombrowser` 两个键根本不出现在 opts 里）/ I 接线与门面锚点 17 / J 收尾 4。整套在 `finally` 里按快照还原 `_get_info_once`、实例上的 `log`、`_cookie_pref` 与 `_info_cache`（E28），不给后面的套件留状态。
- **顺手抓到 `tests/cookiecloud_test.py` 在写真工作区状态**：那套直接对 `cc.STATE_PATH` 与 `cookies/cookiecloud_browser.json` 落盘，跑一次就多出一批 `cookiecloud_state.json` 和 `config.json.bak-<时间>` —— 全属本轮盘点过的「绝不能进包」的本机状态。改成全部走 `%TEMP%`，现在 152 条、退出码 0、跑完工作区零写入（`config.json` 与 `history.json` 的 MD5 前后相同，`cookiecloud_state.json` 与 `config.json.bak-*` 不再出现）。这条与 #22 本身无关，是「跑 53 套全量」那一步抓到的。

### 活体读数（三遍，都在本机另起的进程里跑，没开 HTTP 服务）

探针写法：`sys.path` 指向工作区的 `server.py`，`cfg.save` 盖成抛异常的桩、`engine.log` 盖成收集器、`_get_info_once` 盖成计数包装 —— 于是每次解析都能报出「打了几次、各次带不带 Cookie」。

- **L1 开关关着（基线）**：1 次调用，带 Cookie，43 条流 / 最高 2160p —— 与从前同一条路。
- **L2 开关开着，同一条 YouTube**：2 次调用 `[False, True]`，结果仍是 43 条流 / 2160p，判定记 `cookie`，日志「公开优先：匿名那一次被挡，带 Cookie 再解析一次」。这就是①那处改动的正证：匿名那次真被挡，重跑真把 4K 救回来了。
- **L3 B 站公开视频**：1 次调用 `[False]`，15 条流 / 1080p，判定 `anon`，**下载侧带 Cookie = False** —— 「解析判了匿名，下载就不带」是真发生的，不是推断。
- **L4 B 站一个不存在的 ID**：0.3 秒、1 次调用就收，日志「不为此带 Cookie 重跑」，判定不记。
- **L5 判定留着时省掉的到底是哪一次**：第二遍的 L5 白测了 —— 探针自己的 `run()` 里调了 `drop_cookie_pref()`，把要测的东西先清掉了；第三遍按真的先后顺序重跑（同一条链接连解两次，中间只清解析缓存，等于 180 秒后再解析）：YouTube 那条第一次 2 次调用 `[False, True]`、第二次 1 次调用 `[True]`；B 站那条反过来，第一次 `[False]`、第二次还是 `[False]`。开关一关，同一条 YouTube 立刻回到一次 `[True]` 且判定不当数。
- 三遍跑完 `config.json` / `history.json` / `cookies/cookies.txt` 的 mtime 逐个和开跑前对过（读数里带这行，`与开跑前一致 = True`）。没有下载、没有历史行、没有 `app.log` 写入（日志被收集器接走了）。

### 目视那一遍还是没做

和 #21、#32、#33 同一句：浏览器目视这一轮照样被自动模式拦在门外。这一轮的界面变化是「全局 Cookie」卡里多一个开关和一段 hint，`v-model` 绑定、初值、回填、`CFG_LABELS` 四处都在 I 段静态钉住了，但**开关在界面上点下去是什么样子、hint 会不会把卡片撑坏，没有目视证据**。留给出包前那轮统一复检。

### 没做到的两支

- **真需要会员的那一支没在平台上跑过。** 活体走「带 Cookie 再解析一次」那一支，靠的是 YouTube 匿名一条流都不给（①那处）；「当真是会员视频、匿名被登录墙话术挡住」这一支只在 A 段用报文样钉着。手边没有可测的大会员链接，所以那一支的判定值目前只有自检证据。
- **逐平台覆写 × 这一档的组合只在自检里对过**（D/H/G 段加上 L3b 那一次匿名尝试）。没有把三个平台的 Cookie 来源在界面上挨个改一遍、再看判定是否跟着作废 —— 写点清干净这件事验的是 `drop_all_cookie_prefs()` 的调用位置，不是真点按钮。

### 全量回归

`python -m py_compile server.py` 通过（23,455 行 / 1,061,130 字节 CRLF）；`index.html` 内联脚本 343,444 字 `node --check` JS-OK（整份 776,258 字节 / 13,131 行）。离线自检按 `tests/*_test.py` 逐个跑、以退出码判红，**suites=53 bad=0**（新增 `cookiefirst_test.py`；`bt_boost_test` 那三行 `Exception ignored in _TemporaryFileCloser.__del__` 是解释器既有的噪音，那套自己报 `TOTAL 85 FAILED: none`）。反向验证：把 server.py 里 9 处关键判断逐个改坏 —— 判定不当数（`cookie_off` 永远假）、429 也允许重跑、匿名那份被裁的清单也收下、匿名那次其实带着 Cookie（没换配置）、开关关着也照样走两次的路、TTL 反过来判（过期的一直不过期）、下载侧不看判定（CDN 请求头照带）、保存 Cookie 不作废判定、`ConfigBody` 少声明这个键（G2 那类）—— 每一处都有对应断言转红，改回后 server.py 与备份逐字节相同。

### 测试痕迹

自检临时目录 `%TEMP%\md_cookiefirst_*` 按本轮清掉（36 个，每个一份 29 字节的 `cookies.txt` 夹具）；其余套件留临时目录是既有行为，没顺手改。三个探针脚本、探针输出、那份改坏的 server.py 备份（`md_falsify_*` / `md_cookiefirst_live*` / `md_ytfailure_probe*`）也已删。判定表 `_cookie_pref` 只在内存里，进程退出就没，没有落盘状态要清。

**一处必须记下的副作用**：最早那遍探针为了造「配了 Cookie」的场景，把**内存里**那份 cfg 的全局 Cookie 来源指到 `cookies/cookies.txt` 并用它解析过一次 YouTube（`config.json` 本身一个字没写，`cfg.save` 是抛异常的桩）。yt-dlp 在带 Cookie 解析之后会把刷新过的票**回写**进那个文件，于是工作区里这份真实 Cookie 被改了：92,824 → 90,497 字节，580 行 / 202 个域名，仍是合法的 Netscape 格式，没有备份。两点让它不致于伤到东西：这份文件本来就归程序自己写（每次用文件票解析都可能回写，不是本轮独有的动作），且它在打包排除清单里，不会进包；探针读数也显示这份文件对 YouTube 已经不起作用（V3：文件 Cookie → None，同一条 V2 浏览器 Cookie → 43 条流），所以被刷掉的不是一份还能用的会话。

---

## #34–#40 · 一轮界面收口：七条带截图的反馈（同一轮内，接在 #22 之后）

七条的共同点不是「功能没做」，而是**界面把话说错了时机或说乱了地方**：该开机就有的数要等点进那一页才有、同一个设置在两处各存一份、二十张卡片一路排下来找不到北。逐条落：

### #34 订阅新增计数：启动就要有数

现象是「检测完那一次显示，重启客户端后不显示」。查下来计数**本来就持久化** —— `new_count` 随整条订阅一起存在 `subscriptions.json` 里，`GET /api/subs` 重启后照样回 5 / 50 / 10。缺的不是数据是**取数据的时机**：前端按页面懒加载（`watch(page)`），没点进订阅页就没人去读，顶栏那枚 chip 与侧栏角标自然一直空着。修法是在 `onMounted` 里预取一次（`static/index.html:12956` 那句 `loadSubs()`），不动持久化、不加缓存层。

### #35 资源库默认按修改时间

`libSort` 的默认值改成 `{ key: 'mtime', dir: 'desc', t: '资源库' }`（6236）。理由很直白：进这一页十有八九是来找刚下完的那一条。

### #36 直播录制时长：页面与综合设置是同一个值

「设置里改了 30，直播页还是 0」的根因是**页面自己留了一份影子状态** —— `liveRecordMinutes` 这个 ref 与 `settings.live_max_minutes` 各存各的，谁也不给谁赋值。修法不是补同步代码，而是**把影子删掉**（6184 那行注释记录了这件事）：直播页那一格直接 `v-model="settings.live_max_minutes"`（3796），`startLiveRecord` 读的也是它（8340），提示文案改口成「这一格就是设置里那一格，在哪边改都算数」。全站还剩一处写「跟随设置」的是监控房间配置里的 per-room 覆盖值，那是真的覆盖（房间自己填了就不吃全局），留着没动。

### #37 扫码登录与 Cookie 归到一块

B 站扫码与三个音乐源的 Cookie 原本分在两张卡片，中间还隔着别的设置。合成一张「扫码登录与 Cookie」（4438），开头一句共同口径：这几处记的都是本机 Cookie，扫码成功或粘贴保存后只写进本机配置文件，不写运行日志，也不会被打进分享包。

### #38 不常用设置下移并支持折叠

原来 20 张卡片一路排下来。现在 `.settings-main` 只留 11 张常用的（网络与并发 / 保存位置 / 文件名模板 / 界面外观 / 订阅与直播 / 扫码登录与 Cookie / 多平台 Cookie / Telegram 通知 / 企业微信通知 / 访问保护 / 风控与加速），其余 10 张收进「不常用设置」折叠块（4827–4832），点标题行展开收起，**展开状态记在 `localStorage.md_fold_rare`**（6718–6720），下次打开页面还在。

### #39 「组件与依赖」简化并中文化

以前每一行都挂一枚按钮、行名是一长串英文说明，看着像依赖清单而不像「要不要更新」。改成：行名显示中文短标签（`it.cn || it.label`，完整 `label` 留在 `title` 里鼠标停留能看），按钮只在**没装**或**上游确有新版**时出现（`compUpdatable()`，6714），其余显示「已就绪」，包名与版本号收进「看包名与版本号」那一枚开关后面（`compDetail`，6713）。中文短标签在后端补：`pkg_update.PIP_PACKAGES` 每项加 `cn`（14 项），`server._component_rows()` 的四个工具行也加（13303–13320），pip 行把 `cn` 带出去（13331）。**`label` 一个字没改** —— 运行日志与 tooltip 还用原来那句，短标签只服务界面。

### #40 README 精简，细节整段搬去「详细功能介绍」

`README.md` 788 行 / 170 KB → **89 行**，`README.en.md` 790 行 → **91 行**：留横幅、30 秒上手（三步 + 另两条取法各一行）、便携包里有什么、关键功能（八块各两句，逐块链到详情）、隐私、进一步阅读、许可与免责声明。其余正文**整段搬进** `docs/详细功能介绍.md` 与 `docs/detailed-features.en.md`（各 773 行），一字未删：拆分按标题切，锚点、`../` 相对路径、`docs/screenshots/` → `screenshots/` 随之改写，「目录」在两份新文档里按各自标题重新生成。原来那段 dense 的 Linux/macOS 与 Docker 说明也没丢，改名下成「上手的完整说明」一节。

两条硬要求一起守住：**搬完不丢内容** —— 拿原文逐行比对（跳过被改写的链接行），416 / 419 行非链接正文在新文档里 **0 缺失**；**链接不指空** —— 四份文档共 240 个内链 + 图片，逐个对着目标文件的标题表核过，`bad: []`。包里必须带上这两份新文档，否则包内 README 指着不存在的文件：`pack_release.APP_FILES` 收了 `docs/详细功能介绍.md` 与 `docs/detailed-features.en.md`（71–72），`copy_app()` 顺手 `(dst / name).parent.mkdir(parents=True, exist_ok=True)`（470）好让带子路径的条目落得进去。包内那份 `使用说明.txt` 由 `README_SHARE` 常量生成、不读 README，所以精简 README 没有动到随包说明。

### 界面这一轮的读数（重启前后各一遍）

七条都在本机跑着的 8765 上取过界面读数：折叠块默认收起、点开时 `localStorage` 写入 `md_fold_rare='1'`，常用 11 张 / 不常用 10 张；直播页数字框显示 30（与设置同一值）；资源库表头「修改时间↓」，行按 2026-10-14 20:55:56 / 11:28:24 / 2026-10-13 22:29:23 倒序；非订阅页上「订阅新增 65」这枚 chip 也在；组件表每行显示「已就绪」而不再挂按钮。

#39 的中文短标签要重启才回得到前端（重启前那个进程内存里还是旧的 `server.py` / `pkg_update.py`，界面靠 `it.cn || it.label` 兜底显示长 label）。确认过本机空闲（`/api/health` running 0 / pending 0，监控房间空）之后按同一条命令重启，重启后的读数：**`GET /api/components` 18 行全部带 `cn`，没有一行是空**（5 个工具行 + 13 个 pip 行；`label` 与旧文案逐字未变），开机那次上游检测 7 秒跑完（14:11:47 → 14:11:54，`status: done`、`available: []`），界面上每行显示「视频合并 / 转码」「站点解析工具」「解析规则（Python 包）」「繁简归一」这类短标签，右侧一律「已就绪」，卡片上只剩「立即检测 / 看包名与版本号 / 一键更新」这几枚全局按钮。顺带在新进程上重取了另外六条：首页（没进过订阅页）就显示「订阅新增 65」、侧栏订阅那行带角标 65；资源库表头「修改时间↓」且行按 2026-10-14 20:55:56 / 11:28:24 / 2026-10-13 22:29:23 倒序；直播页「录满自动保存」显示 30 并带那句「这一格就是设置里那一格」；设置页常用 11 张 + 折叠块 10 张。浏览器控制台无报错。`appVersion` 仍是 `v1.3.2`，本轮没出包。

## #23 · Spotify / 网易云单曲链接入口（同一轮内，接在 #34–#40 之后）

这一项按要求**先把口径写出来过一遍再动代码**。口径要定的其实是一句话：一条只带曲名的单曲链接，下载时到底听谁的。定稿是 —— **`match_sources` 勾选顺序就是优先级，第一个搜到并且过了分/时长那道闸的就用，不重排、不暗中剔除、失败也不去敲其它源的门**；Spotify 与网易云的单曲链接从此和整张歌单走同一条占位（`needs_match`）→ 匹配 → 下载的路，差别只在「一次只有一首」。

> **这条定稿的「第一个搜到就用」后来被用户指正推翻了**，现行口径与实测写在下面「#23 更正 · 匹配把勾选的源全搜完再择优」那一节。本节其余内容（链接识别、单曲元数据、QQ 的说法）不受影响。

**口径里三条被实测推翻了，先记在这儿，因为它们都是我当时按「读代码得来的印象」写的：**

1. 我当 operation 名是 `trackUnion`。实测**没有这个 operation** —— `trackUnion` 是响应里的字段（`data.trackUnion`），persisted query 的名字是 **`getTrack`**，指纹 `a8ef9e9f…668de`（`fetchPlaylist` 是 `8964e8ea…584a`）。两者都从同一个 JS 包里搜出来。
2. 我按 musicdl 那句「每页约 45s」估了取指纹的代价。实测**主包一跳 1.2 秒就带回全部 81 个查询指纹**，而那 81 个指纹引用的 75 个分片要 57.6 秒、且一个查询串都不含 —— musicdl 自己每次都全量扫，所以慢的是它。于是 `_spotify_scan_hashes`（music_search.py:2027）改成**先只扫主包，扫不到要的那个操作名才补分片**，整表按 6 小时缓存（`SPOTIFY_HASH_TTL`，1970），第二张歌单、翻页、单曲都不再付这笔钱。**拿不到真指纹就报错，不编一个假的顶上**（C4 钉这条）。
3. 我说网易云单曲「直接给真地址」。实测 `api/song/detail` 只回**元数据**（曲名/歌手/专辑/时长/封面），音频地址该给的时候不给 —— 所以网易云这条也铸 `needs_match` 占位。看着像绕远（网易云的链接又要靠搜索去网易云匹配），其实不是：这一步把「有没有 VIP、这一档给不给 FLAC」这些只有搜索链路才有的判断交给了同一条闸，而且它通常就匹配回网易云自己。

### 后端（全在 `music_search.py`）

- **链接识别**：`_spotify_path_id`（2004）把歌单/单曲的取 id 收成一条，`_spotify_playlist_id`（1994）与新的 `_spotify_track_id`（1999）各自只喂 `kind`；`/intl-xxx/` 前缀先削掉，短链 `spotify.link` / `t.spotify.com`（`SPOTIFY_SHORT_HOSTS`，2263）由 `_spotify_unshort`（2271）**只发一个 GET 看 Location，不执行页面下发的任何 JS**。`_netease_song_id`（2330）认 `song?id=` 与 hash 两种写法，并把 `playlist?id=` 明确推开 —— 同域名下那是整张歌单，A9 钉住这条。`_qq_song_mid`（2353）只在路径/碎片含 `song` 时收裸 `mid=`，避免把专辑 mid 当歌。
- **共用 machinery**：`_spotify_tokens`（2060）、`_spotify_client`（2188）、`_spotify_query`（2087）从原来那条只服务歌单的链路里抽出来，`_spotify_fetch_page` 变成 `_spotify_query` 的一层薄壳；`list_spotify_playlist`（2206）改吃 `_spotify_client`，指纹过期时把整表清掉重扫。**歌单那条路的行为一个字没动**（回归读数在下面）。
- **Spotify 单曲**：`list_spotify_track`（2284）拿 `getTrack` + `{"uri": "spotify:track:<id>"}`，`SPOTIFY_TRACK_BUDGET = 60` 封顶，NotFound / Episode / 空曲名分别给三条不同的实话；`_spotify_track_fields`（2120）同时吃得下 `itemV2.data` 与 `trackUnion` 两种形状（歌手缺 `artists` 时退回 `firstArtist + otherArtists`，时长 `trackDuration` 与 `duration` 都认）。
- **网易云单曲**：`list_netease_track`（2382）打 `music.163.com/api/song/detail?ids=[<id>]`，域名不通退 `interface3.music.163.com`，产出的占位与 Spotify 同构（`url: ""` / `needs_match: True` / `can_musicdl_download: False`，`page_url` 回填成规范单曲页）。
- **QQ 这条不装**：`qq_single_track_note`（2450）直接说「免 Cookie 拿不到曲名与时长（实测它的三个详情接口分别回 空 data / 500003 / 500005，网页是 JS 壳），而本程序没有做带 Cookie 的 QQ 单曲解析 —— 请把『曲名 歌手』填到上面的搜索框」。带 Cookie 的 QQ 单曲解析**没有实现**，因为本机没有 QQ 音乐 Cookie，写了就是一条测不到的断言；宁可让用户去搜索框，那边是真能出可下载曲目的。
- **路由**：`parse_playlist`（3244）里新增 `_single_track_kind`（3342）与 `_try_single_track`（3352），位置卡在 `unreachable` / `musicdl_available` 之后、`prefer != "quality"` 那条 Spotify 分支之前，三种返回值分得很干净：`None` = 这不是单曲页（照旧走歌单），`[]` = 是单曲页但拿不到（原因写进 `diag["hint"]`），`[item]` = 成功（`diag["engine"] = "<kind>-single"`）。**卡在 quality 分支之前是重点**：选了「逐曲获取高音质地址」时一条 Spotify 单曲也不会退回 `_try_musicdl` 去逐曲取址（G3）。

### 界面（`static/index.html`，七处文案）

输入框占位改「歌单或单曲链接 music.163.com / y.qq.com / open.spotify.com / …」（2952），按钮「解析歌单 / 单曲」（2957），空态提示、页首那句「多源并行搜索、歌单与单曲链接解析…」、接口活动名「解析音乐歌单 / 单曲」（6888）同步改口；**「匹配源」tooltip 重写**（3001），把「勾选的顺序就是优先级，第一个搜到能用的就停」和「整张歌单与单曲链接同一条路」两句写进去 —— 这句话原来是这条设置项唯一的行为说明，口径变了它必须跟着变。**（前一句随后被更正，见下一节；tooltip 现在说的是「全部搜一遍再择优」。）**结果消息按 `engine` 结尾的 `-single` 分流：成功说「单曲 N 首（只列了曲目，下载时才按曲名去勾选的源里匹配地址）」，失败不再冒充「歌单解析失败」，改口「解析失败：…」。后端那两处（`/api/music/playlist` 的 docstring 与 400 文案）同批改。

### 自检

- 新增 **`tests/musicsingle_test.py` 50 项全绿**（A 链接识别 13 / B 两种响应形状 7 / C 指纹表 4 / D `list_spotify_track` 7 / E `list_netease_track` 6 / F QQ 的说法 4 / G `parse_playlist` 路由 9），全在内存里跑：假 session、假 `list_spotify_playlist` / `stub_ytdlp`，`cfg.save` 不涉及，不联网不读 config。C 段那两条（一次扫包记住两个操作名、缓存命中不再下载 JS 包）是冲着「别把 57 秒的代价留给用户」写的；G 段里 `G1b` 钉「Spotify 单曲绝不退回逐曲取址」。
- 回归：**57 套**（54 个 `*_test.py` + `diarize_selftest` / `diarize_e2e` / `hardsub_e2e`）全跑，退出码全 0，**`PASS` 3585 条 + `OK` 140 条**；`python -m py_compile server.py` 通过。`spotifylist_test.py`（77 项）与 `matchgate_test.py` / `matchround_test.py` / `switchsource_test.py` 都没红 —— 抽公共 machinery 这件事如果碰坏了歌单，最先红的是它们。
- **抓到一条陈旧断言，红的是它自己不是新功能**：`tests/liveduration_test.py` 的 G1 / G5 断言直播页还绑着 `liveRecordMinutes` 这个页面级影子 ref —— 那东西在 #36 就被**故意删掉**了（改成直接绑 `settings.live_max_minutes`），当时只改了 `index.html` 没改这份自检。这一遍全量重跑才把它顶出来。修法是把断言改成现在的样子（`G1` 数 `v-model="settings.live_max_minutes"` 至少两处、并断 `liveRecordMinutes` 在整个文件里不出现；`G5` 从返回清单里划掉那个名字），改完 38 项全绿。**这条不是本轮代码引入的**，但它一直让「全套自检」这句话不能按字面说。

### 活体读数

**接口层**（`%TEMP%` 里的探针，代理与勾选源按本机设置）：

- Spotify 单曲 `0VjIjW4G…`（Blinding Lights）：**冷启 5.4 秒**（含扫包）出 1 条，指纹表热了以后 3.0 秒 / 单次接口 1.9–2.2 秒；`/intl-…` 前缀同结果（3.0 秒）；不存在的 `spotify:track:7yiUopE…` 回「Spotify 说这条链接不是歌（或已经下架）」（2.5 秒）。**歌单回归**：同一条链路列 Today's Top Hits 仍是 50 首、`spotify-list`、2.4 秒。
- 网易云单曲 `song?id=186000`（我的地盘）**0.4 秒**出 1 条，hash 写法同结果（0.5 秒）；QQ 单曲 0.7 秒出 0 条并带上面那句实话。
- **端到端下了三首真成品，`match_sources` 那句口径就是这么测出来的**：① Spotify 单曲 + 源序 `Netease/QQ` → 匹配 Netease，36.9 秒，`Blinding Lights - 1406633327.flac` 129,336,950 字节；② 网易云单曲 + 源序 `QQ/Netease` → **匹配 QQ**（它自己的链接排在后面的网易云没被优先用上），68.3 秒，`我的地盘 - 004WrpV81DMGHv.flac` 171,767,742 字节；③ Spotify 单曲 the cure + 源序 `QQ/Netease` → 匹配 QQ，75.6 秒，201,662,118 字节。三次的 `match_report` 都是 `matched 1 / missed [] / unsearched []`。②③ 当时被当作「勾选顺序即优先级，不重排、不暗中剔除」的证据 —— 占位来自哪个平台，跟它去哪个平台匹配音频地址是两件事。**这三次测的是「只问了一个源就收场」的旧行为，那条判据已被更正，见下一节。**

**界面层**（重启 8765 之后取，PID 53436 → 53364；重启前 `running=0 / pending=0`、监控房间 0 个，没打断任何东西）：

- 音乐页输入框占位、按钮「解析歌单 / 单曲」、空态提示、页首那句、以及重写的「匹配源」tooltip 全部按新文案渲染出来了（tooltip 是抓 DOM `title` 逐字读的）。
- 粘 Spotify 单曲 → 表里一行「Blinding Lights / The Weeknd / After Hours / **Spotify 待匹配** / 3:20 / 换源·下载·收藏」，绿条「单曲 1 首（只列了曲目，下载时才按曲名去勾选的源里匹配地址）」。
- 粘网易云单曲 → 「我的地盘 / 周杰伦 / 七里香 / **Netease 待匹配** / 4:05」，同一句「单曲 1 首」。
- 粘 QQ 单曲 → 表清空，红条「**解析失败：QQ 音乐单曲页免 Cookie 拿不到这首歌的曲名与时长（实测它的三个详情接口分别回 空 data / 500003 / 500005，网页是 JS 壳）…请把「曲名 歌手」填到上面的搜索框**」，日志同步记一行 error。
- 运行日志这三条分别是「Spotify 单曲「Blinding Lights」元数据已取得（The Weeknd，3:20）…」「网易云单曲「我的地盘」…」「单曲解析: 0 首 —— …」，活动名显示成新的那句「[界面] 解析音乐歌单 / 单曲」。浏览器控制台**无任何报错**。

### 测试痕迹

探针脚本与输出（`%TEMP%\md_spot_probe*` / `md_singles_live.txt` / `md_singles_dl_out.txt` / `md_singles_dl\`）按本轮删除；三首 FLAC 是下到 `%TEMP%` 的临时目录里测的，`Downloads/` 没有新增。自检这遍在 `musicdl_outputs/_musicdl_cache/` 落了 **61 个空的 `md_*` 测试目录**（`playlistdup_test.py` 用 `tempfile.mkdtemp` 起 work_dir，musicdl 按 basename 在真缓存目录下开同名空目录），已用 `rmdir` 逐个删 —— 只对空目录有效，那 285 MB 的真缓存内容一行没动。`config.json`（10:58）与 `history.json`（11:46）mtime 未变，`notify_outbox.json` 未变，解析动作不写历史也不落盘。**`appVersion` 仍是 `v1.3.2`，本轮没出包。**

## #23 更正 · 匹配要把勾选的源全搜完再择优（用户指正，接在上面那一节之后）

用户的话是：**「第一个搜到能用的就停，错误的，需要确保所有平台都历遍。」** 上一节那条口径（「勾选顺序就是优先级，第一个搜到能用的就停」）是我写的，代码、tooltip、两份详细文档、两份 README 都跟着它落地了 —— 这一条把它作废，改动同时回写到那五处文案。

### 旧行为错在哪

`_resolve_placeholder` 按勾选顺序逐源搜，**第一个有货的源里出了过闸候选就直接 return**，后面的平台连问都不问。于是「同一首歌两家都有、其中一家档位更好」这种最常见的情况，拿到的永远是排在前面的那家 —— 打分闸门只在单个源内部择优，跨源之间它根本没参与。上面那三次端到端读数（②③）测的正是这个旧行为，所以那两行的结论已就地标注作废。

### 现在的口径

1. **勾选的源全部搜完**，候选汇成一个池子交给 `_pick_track_match`，取 `(分数, 档位, 音质)` 最高的一条；不重排、不暗中剔除任何勾选的源。
2. **只有平票（三项全等）才按勾选顺序**，先勾的赢 —— 顺序从「优先级」降级成「决胜局」，这是这句口径与上一版的实际差别。
3. 平票的「勾选顺序」按 `srcs` 的下标归位（`buckets` 按序号回填），**不是按谁先回话**。并行发问之后到达顺序会随网络抖，如果按到达顺序排，同一张歌单两次下到的平台可能不一样。

### 代价，以及为什么顺手改了并发

遍历全部源把「一首歌的取址代价」从「第一个源的耗时」变成「所有源之和」：串行实测**晴天 133.9s、Blinding Lights 103.1s**（5 个源 ×8 条结果，QQ 单源就 59~63s）。50 首的清单按 `TRACK_MATCH_WORKERS = 3` 要跑四十分钟，一定撞进 `TRACK_MATCH_BUDGET = 1500` 的「本轮没轮到搜」——那不是变慢，那是后半张歌单不下。所以每一首内部把源**并行问**（新增 `TRACK_MATCH_SOURCE_WORKERS = 4`，music_search.py:1982），一首的墙钟变成「最慢那个源」：**晴天 63.5s、Blinding Lights 31.6s**。并发量 3 首 × 4 源 = 至多 12 路，与聚合搜索「每源一条线程」同量级，没有新开线程池模型。

### 改了哪几处

- **代码**：`_resolve_placeholder`（music_search.py:2852）—— 逐源循环换成并行 `_ask` + 按 `srcs` 下标回填的 `buckets`，`asked` 记住「这条候选是问谁家搜来的」（条目自带的 `source` 是平台返回的署名，不是我们敲的门；平票与日志都要后者）；`resolve_placeholders` 那句开场日志改「每首把这些源都搜一遍，再取最像的那条」。**换源（`switch_song_source`）走同一个函数，自动继承这条新口径**，不用另写。
- **文案五处**：「匹配源」tooltip（index.html:3001）、`docs/详细功能介绍.md` 与 `docs/detailed-features.en.md` 的单曲那一节、两份 README 的音乐行。README 那句原来写「匹配源勾选顺序就是优先级」，现在是「勾选的平台全部搜一遍再择优，只有三项全等时才按勾选顺序」。
- **自检**：`matchround_test.py` 新增 R 段 9 条（R0 先核对两条候选的分确实差 96/100 一档，R1 两个源都被问到、R2 取分高的那条哪怕它在后面那个源、R3 日志措辞、R4 平票按勾选顺序、**R4b 先勾的回话慢、后勾的先到时仍按勾选顺序**、R5 前面空手后面有货照样命中、R6 全对不上算没命中且跨源拒因带得出来、R7 三个源就搜三遍）；`spotifylist_test.py` 的 E8 原来钉的是「问到一个就停」，改成钉全问一遍，另加 E8b 钉平票。R1/R5、E8 的**顺序断言改成集合/排序断言**——并行发问后「问的先后」不再是口径，「一个都没漏」才是；顺序这件事由 R4/R4b/E8b 专门钉。
- 顺带一条陈年噪音：`bt_boost_test.py` 收尾会打三条 `Exception ignored in _TemporaryFileCloser.__del__`（musicdl 的临时文件被换了个没有 `close()` 的对象），是 stderr 噪音不是失败，那套 85/0 全绿、退出码 0，本轮没动它。

### 活体读数（真实网络，只发搜索、不下任何一个字节）

探针把 `_search_one_source` 包一层记账再调真实现，`%TEMP%\md_traverse_probe.py`（跑完删）：

| 曲目 | 问到的源（到达顺序） | 各源回了多少条 / 耗时 | 最终用的源 | 一首的墙钟 |
| --- | --- | --- | --- | --- |
| 周杰伦 晴天 | Migu / Netease / Kugou / Kuwo / QQ | 8 条 / 5.6s、8 / 14.5s、8 / 23.9s、8 / 24.2s、8 / 63.5s | **QQ**（勾选表里排第 2，最后回话） | 63.5s |
| The Weeknd · Blinding Lights | Migu / Netease / Kugou / Kuwo / QQ | 8 / 5.2s、8 / 13.9s、8 / 19.7s、8 / 17.2s、8 / 31.5s | **Netease**（第 1 个勾的） | 31.6s |

**「晴天」这一行就是用户要的那个证据**：五个源全被问到，其中网易云先回了话（14.5s）、QQ 最后回（63.5s），旧代码在 14.5s 那一步就收场了，现在等到 63.5s 把 QQ 那条更好的取走。占位最终换成的是真 `SongInfo`（不再是 `needs_match` 的 dict），两家都回 8 条、没有一家报错。

`config.json`（10:58）/ `history.json`（11:46）/ `notify_outbox.json`（14:09）mtime 未变，`Downloads/` 无新增；探针在 `musicdl_outputs/_musicdl_cache/` 落的空 `md_*` 目录已 `rmdir` 清掉。

## #24 · 自动分类带上链接规则：普通下载也按链接落子目录（同一轮内，接在 #23 更正之后）

issue #206 那张清单的 ③。自动分类从前只比**种子 / 磁力的名字**，于是「YouTube 的存到 `视频\YouTube`、论坛直链存到 `视频\直链`」这种愿望落不了地 —— 普通下载（YouTube / B 站 / `.mp4` 直链）压根没有「种子名」这种东西可比，规则表再长也管不到它们。这一条给规则加一维「问的是名字还是链接」，让链接也能当匹配对象，普通下载跟着落子目录。

### 四条口径（动手前定的，用户逐条拍板）

1. **同一张表加一维，不另起一张表**：每条规则多一个 `scope`（`name` / `url`），界面还是那一张规则表，只是每行多一个下拉。分两张表的话「从上往下第一条命中生效」这条顺序口径就跨表失效了，用户也说不清哪张表赢。
2. **手动指定目录的赢，规则跳过** —— 但**日志仍要点名本可以命中哪条**：「这一条已手动指定保存目录，规则不改落点（仍存 …）」。不点名的话用户会以为规则写错了，去改那条本来没问题的规则。
3. **磁力先问名字规则，名字没中才问链接规则**：种子里的标题是人能读懂的东西，比 URL 那串 `xt=` 可靠得多；`_rule_decide()`（server.py:9444）就是这个顺序，**真正落盘与界面「试匹配」共用这一个函数**，两处不会漂。
4. **普通下载不吃「都不命中时存到」那个兜底目录**：兜底档是给磁力「此刻还没有可比的名字」准备的，普通下载一旦也走它，等于加一条链接规则就把整个下载目录改了地方。没命中就留在默认目录（server.py:9511-9512 明写了这条理由）。

### 后端

- **`bt_rules_clean()`（server.py:9357）收 `scope`**：只认 `name` / `url`，收到别的值逐条点名退回（「第 3 条「网页」的匹配对象只认「名字」或「链接」，现在收到的是「path」」）。空关键词的文案也跟着 scope 变（「没写要匹配的链接 / 名字」）。
- **`bt_rule_match()`（server.py:9394）多一个 `scope` 形参，且只问同一类的规则**：一张表里混排时，「这条是问链接的」不能被拿去比种子名 —— 否则 `https://` 这种关键词会把所有种子一律收走。大小写一律忽略（同一批人一会儿 `1080P` 一会儿 `1080p`，分两种写法只会让规则表越写越长）。
- **`bt_target_dir()`（server.py:9452）多收 `url=`**：名字与链接两条都问完后，说明句按「表里到底有没有链接规则」变两种写法（9466-9471）—— 只有名字规则时写「名字「…」没命中任何规则」，两种都有时写「名字与链接都没命中」。**不配规则时仍旧原样回默认目录、一条日志都不多写**，「开着默认设置却莫名其妙多了层目录」是不能出现的。
- **新增 `url_target_dir()`（server.py:9505）管普通下载**：表里一条链接规则都没有 → 直接原样返回默认目录并**一个字都不写**（老设置升级上来必须毫无变化）；命中才建 `下载目录/<子目录>`；`manual=True` 时按口径 2 让路。
- **新增 `_opts_dir_is_manual()`（server.py:9491）**：判据不能是「非空」—— 界面那一格预填的就是全局目录（`loadConfig` 里 `opts.download_dir = data.download_dir`），只有与全局**不一样**才算手动。用 `_same_dir()` 比，Windows 下大小写 / 尾斜杠 / `.\` 这些写法差异都算同一个目录。
- **接线在 `_run()` 的普通下载分支**（server.py:10353-10357）：`if not parse_torrent_ref(task.url)` 才调 `url_target_dir()` —— 磁力那一页由 `bt_target_dir()` 自己管，两边都跑会套两层目录。
- **试跑口 `POST /api/torrent/rules/test`（server.py:23334）收三种输入**：给名字、给磁力 / 种子链接、给一条 `http(s)` 普通链接。回话里 `kind` 决定问的是哪一档，`name_from` 说清名字从哪来；没命中时那句「 asked 规则」也跟着变（「名字与链接的规则」/「链接规则」/「名字规则」，23381-23383），普通链接那一档专门补一句「『都不命中时存到』那个兜底只管磁力 / 种子」（23389-23391）。

### 界面（`static/index.html`）

- **规则表每行多一个「问什么」下拉**（2267，120px），匹配方式与关键词占位文案跟着 scope 变（2272「链接包含」/「名字包含」，2275 举例 `youtube.com`）；新增规则默认 `scope: 'name'`（11379），`loadConfig` 把旧配置里没有这一维的规则归一成 `name`（7587）—— 手改过 `config.json` 的人不用重写规则。
- **试跑那一行**（2287-2291）：一个框同时吃名字 / 磁力 / 网页链接，结果那句把「比的是哪个名字、它从哪来」一并显示（`testBtRule`，11399）—— 磁力在元数据到手前根本没有名字可比，这件事必须看得见，而不是给个空结果让人猜。

### 自检

`tests/torrent_test.py` 从 206 项涨到 **224 项全绿**（`共 224 条，失败 0 条`）。新写的一段用 `URL_RULES` 夹具（`网页视频` / `论坛直链` 两条 `scope:"url"`）：

- **N24** 一张表里两种规则各问各的 —— 链接规则不许拿去比种子名；**N24b** 老规则没写 `scope` 时当名字规则，不会误吃链接（升级路径）。
- **N25** 磁力名字与链接都撞得上时**名字那条赢**；**N29c/N29d/N29e/N29f** 把这四条顺序在试跑口上再钉一遍（含「没带 dn 的磁力此刻没有名字可比，链接规则照样接得住」—— 这正是加 URL 规则的意义）。
- **N26/N26b** 普通下载命中链接规则（含正则那一档，直链按路径归类是常见写法）；**N27** 没命中时留在默认目录且**绝不进兜底档**；**N27b** 手动指定时手动赢、日志仍点名本可以命中哪条；**N27c** 表里一条链接规则都没有时原样走默认目录、**一个字都不写**；**N28** 判「手动指定」不能用非空。
- 试跑那一段改了四条既有断言：**N21e** 没配规则时直说「还没配规则」；**N22** 既不是磁力也不是 http(s) 的仍然当场顶回；**N22b** 网上的 `.torrent` 链接**不再被拒**（它走普通下载这条路，按链接规则给结论就行 —— 这一条是口径改了，不是回归）；**N29/N29b** 网页链接的两种回话。

### 活体读数（真下了一条，本机 127.0.0.1:8765）

先按口径把规则表填成一条 `scope:"url"` 的「网页视频」（关键词 `youtube.com`，子目录 `视频/YouTube`），提交一条真实 YouTube 链接：

- `app.log`：`自动分类：「https://www.youtube.com/watch?v=oZpYEEcvu5I」里含「youtube.com」 → 规则「网页视频」，这一条存到 …\Downloads\视频\YouTube`
- 成品落在 `Downloads\视频\YouTube\`，**61,874,878 字节**（不是默认目录）；历史多一行 `2026-10-15 18:45:16`。
- 写配置走的是页面自己的 `POST /api/config`（只交改动项），**没有直接编辑 `config.json`** —— 服务正在跑，手改文件会被下一次整包保存盖掉，也会让这一轮的 mtime 读数失去意义。

### 测试痕迹与收尾

这条读数是**真下载**，所以收尾做了：`history.json` 34 → 33 行、`download_archive.txt` 22 → 21 行（两份改前都备份到 `%TEMP%`），`Downloads\视频` 整个删掉，「网页视频」规则删回 `bt_auto_rules: []`，`bt_auto_fallback` 归空。改完 `config.json` 里这三项与本轮开始时一致。

## #25 · 剪贴板监听：默认关、只问一句、绝不自动入队（同一轮内，接在 #24 之后）

issue #206 那张清单的 ④。**这一项的风险不在下载，在「程序盯着我复制了什么」**，所以口径先于代码定死三条，并且三条都有读得出来的钉子。

### 三条口径（用户拍板「本机服务读系统剪贴板」这一档）

1. **读的人是本机服务，不是页面**：ctypes 走 `user32` / `kernel32`，**零新依赖**（不引 pyperclip / win32clipboard），页面关着也照读，回来还能看见那一条。反过来说 —— 服务没跑就没有监听，这是这一档的代价，写在设置页那张卡片上。
2. **默认关，而且是真关**：`DEFAULTS["clipboard_watch"] = False`（server.py:3747）。线程常驻但每轮先看开关（7852），关着时 `checks` 一次都不涨；`GET /api/clipboard` 在关着时**连待定内容都不交出**（23407-23412），不是只停线程。
3. **绝不自动入队**：认出链接只是挂到「待定」上，界面弹一张「加入 / 忽略」的卡片；**「加入」也只是把这一条填进链接框**（10977-10984），之后要不要解析、要不要下载仍归用户按那一下。

另有两条隐私口径，也在自检里：**读到的内容一个字都不进运行日志**（只有开关本身开 / 关各记一行，13971-13978；「谁在什么时候让程序盯剪贴板」该看得见，盯到了什么不该留在盘上）；**界面拿到的是抽出来的那一条链接，不是剪贴板原文**（7832-7838 只挂 `link`，10970 只接 `pending`）。

### 后端（server.py:7734-7860 一节）

- **`clipboard_text()`（7754）只读**：不写、不清、不动别的格式。`OpenClipboard` 失败不当错误处理 —— 剪贴板是全局锁资源，别的程序正写着时读不到是常态，回一句「正被别的程序占着，下一次轮询自动再试」，**绝不重试到把界面卡住**；没有文本格式（图片 / 文件列表）回空串且不算异常。64 位上 `GetClipboardData.restype` 必须显式设成 `c_void_p`（7776）：默认 `c_int` 会把 HANDLE 截成 32 位，读出来必是垃圾 —— 这一条是写完第一遍就自查补上的。
- **`clip_extract_link()`（7806）**：`magnet:` 与 `http(s)://` 两条正则（7744），停字符类 `_CLIP_STOP`（7743）把中英文标点、全角括号、书名号都挡在链接外（粘一整段分享文案也只留链接；半角括号放行，`a(1).mkv` 太常见；冒号只排全角，端口要留）。尾巴上那一个半角标点再切一刀（`link[-1] in ",.)]"`，7816）。超过 `CLIP_TEXT_CAP = 4000` 字直接放弃 —— 刨文章里的链接不是这功能要干的事。
- **`_clip_tick()`（7819）去重**：`sha1[:16]` 当键，同一条内容反复轮询只弹一次（每 2 秒问一遍，重复弹才是骚扰）；`seen` 只留最近 `CLIP_SEEN_KEEP = 30` 份（长期开着不能把内存当账本）。**没有链接时不清旧的待定** —— 悄悄消失比留着更糟，用户连「忽略」都没法点。新链接直接顶掉旧的（复制得快说明旧的那条不要了）。
- **两个接口**：`GET /api/clipboard`（23400）回开关、待定、`checks/hits/error/supported/poll_sec`；`POST /api/clipboard/clear`（23416）只是清空待定，不看内容、不留记录。**`/api/clipboard` 不在 `AUTH_PUBLIC_PATHS`（11028）里** —— 开了访问保护后，非本机地址要先登录才问得到，待定那条链接不会顺着匿名接口漏出去。

### 界面

- 首页（「下载」页）多一张 `v-if="clipPending"` 的卡片（1756-1764）：显示抽出来的那条链接（`.clip-link`，641）与「磁力 / 网页链接」的类型，两个按钮「加入」「忽略」。
- 设置页多一张「剪贴板监听」卡片（4467-4483）：开关 + 三段说明，把「默认关」「页面关着也照读」「不自动入队 / 不自动解析 / 不自动下载」「内容不落日志」三件事写在开关旁边，而不是藏在 tooltip 里。
- 轮询 `pollClipboard()`（10967）在 `onMounted` 起一次并 `setInterval` 2 秒（13072-13073），`onUnmounted` 清 timer；`clipNote` 那行显示「已读 N 次，认出 M 条链接」，非 Windows 补一句「这台机器不是 Windows，读不了系统剪贴板」（口径写死，别让非 Windows 静默失灵）。这一项在自动保存的字段名表里也有中文名（12492 `"clipboard_watch": "剪贴板监听"`），改完就是「只交改动项」那条老路子。

### 自检

**新增 `tests/clipboard_test.py` 28 项全绿**，全程 `clipboard_text` 被换成脚本喂进去的内容，**不碰真剪贴板**（只读也不写不清，也不打印用户复制过什么）：

- K1~K1f 抽取口径（整段一条链接 / 磁力到第一个空白为止 / 分享文案里夹的链接 / 尾部中文标点不算进去 / 没链接的普通文本与超长文本一律不算 / 本机路径与 `file://` 不接）。
- K7~K12 轮询行为，其中 **K7b 钉的是「挂的是抽出来的链接，不是剪贴板原文」**、K10 钉「没有链接时上一条不许悄悄消失」、K11 钉 `seen` 有上限、K12 钉「读不到时把缘故留给界面但不挂任何东西也不抛」。
- K13~K17c 开关与线程：K13 关着时接口不交出待定；K15/K15b/K15c **打开、关闭各记一行且那一行里没有任何剪贴板内容**，开关没变的那次保存不重复记（日志是给人翻的，不是心跳）；K17 关着时线程醒了也不碰（`checks` 一次没涨）、K17b 打开后读到的是一条待定而**没有任何任务被创建**、K17c 停止信号能收住线程。
- K18 是这套自检自己踩过的一次坑，记在这儿：**第一版把它写成「真读一次剪贴板并且非空」，等于拿用户当下复制的内容当夹具** —— 剪贴板是空的、或者里面是一张图片，这条就红，而代码没错。现在钉的是契约：回的是 `(文字, 缘故)` 两个字符串、两者不同时有值、绝不抛，K18c 另钉「缘故那一栏如果有内容必须是一句人话，不是异常名糊上去的」；文档字符串里明写「空剪贴板是合法读数，不许拿来当夹具」。

### 活体读数（本机 127.0.0.1:8765，PID 32320）

开关这一路走页面自己的 `POST /api/config`（只交 `{"clipboard_watch": …}` 这一项，**不直接编辑 `config.json`**），计数器取自 `GET /api/clipboard`：

- **打开**（20:38:30）：隔 5 秒取两次 → `"checks":2` → `"checks":4`（2.0 秒一跳，`enabled:true`、`supported:true`、`error:""`）。
- **关掉**（20:38:43，即 kill-switch）：再隔 6 秒取两次 → **`"checks":8` 两次一字不差** —— 关着就是真的一次都不读，不是读得少。
- 日志这两行逐字是「剪贴板监听已打开：发现链接只在界面上问一句，加入 / 忽略由你决定」「剪贴板监听已关闭：程序不再读系统剪贴板」，**行里没有任何剪贴板内容**，这一路只多两条 `[界面] 保存设置（1 项变更）`。
- 「复制一条链接 → 首页弹卡片 → 点加入」那一段是本轮早些时候在浏览器里取的：点「加入」后 `/api/tasks` 仍是 `taskCount:0`、`/api/clipboard` 的 `pending` 回 null，日志多一行 `[界面] 调用 clipboard/clear` —— **没有任务被创建**，链接只是填进了输入框。
- 界面那一遍（浏览器）：卡片文案、「已读 N 次」计数在涨、点「忽略」后同一条不再复现，控制台无报错。

读数取完 `clipboard_watch` 已改回 `false`（`config.json` 与本轮开始时一致）。

### 测试痕迹

`clipboard_watch` 读数后已改回 `false`；本轮没有下载任何东西，`history.json` / `download_archive.txt` 未因此项变动（#24 那一条的收尾在上一节）。自检脚本只写 `%TEMP%`。

## 整批同跑抓到的一条假绿 · CookieCloud 判「内容没变」不该看同步时刻那一行

这一条不是新功能，是**把整批 59 套一次性跑完**才浮出来的红。单独跑 `tests/cookiecloud_test.py` 时 H12 一直是绿的，批量跑才红 —— 差别只在「前面有没有别的测试先跑过」。

### 症状与根因

`_cc_write_file()` 判「内容一样就不动盘、不堆备份」用的是**整份文本相等**，而那份文本的第二行是 `# CookieCloud 同步写入 <yyyy-MM-dd HH:mm:ss>，共 N 条…`。于是「没变」这件事取决于机器快慢：同一秒内连续拉两次才算没变，跨过 1 秒边界就必然「变了」，每次都多一份没人看的 `cookies.txt.bak-<时间>`，界面那句「一个文件都没动」也就说不出口。单独跑时两次拉取恰好落在同一秒里 → 绿；批量跑前面 58 套把时钟推走了 → 红。**这是假绿的教科书样子：断言本身没错，错在实现把口径交给了不该交给的东西（墙钟）。**

### 改法

- 抽出 **`_cc_netscape_lines(rows)`（server.py:16321）**：只渲染 Cookie 那几行（去重 + 排序），不含头部注释；`_cc_netscape_text()`（16335）改为在它外面包三行头。
- 新增 **`_cc_body_same(path, rows)`（16372）**：把**本机文件读回来再走同一个渲染函数**，比的是格式化后的 Cookie 行，不是内存里的 dict —— 两边同一条流水线，读回时那 7 列的顺序、`#HttpOnly_` 前缀、`TRUE/FALSE` 写法都不会和写入时漂。认不出来的文件（不存在 / 读炸）一律当「变了」。
- `_cc_write_file()`（16395-16401）里 `if existed and path.read_text(...) == text:` 换成 `if _cc_body_same(path, rows):`，函数文档字符串跟着改口（「Cookie 行一模一样就不动」）。

### 自检

`tests/cookiecloud_test.py` 从 152 项涨到 **153 项全绿**：H12 原样留着（同秒那一路），新增 **H12b 把 `S._cc_now` 桩成 `"2027-01-01 00:00:00"`**，即两次拉取之间**必然**跨时刻，断言仍是「一个文件都没动」且 `cookies.txt.bak-*` 只有一份，`finally` 里把 `_cc_now` 换回来。**A/B 反向验证**（`md_cc_ab.py`，跑完删）：把 `_cc_body_same` 猴补丁回「整份文本相等」，H12b 立刻红并打回那句「写了 3 个文件」，`共 153 条，失败 1 条`，而 H12 照旧绿 —— 新断言确实钉住了这一处，不是换着花样测同一件事。

### 顺带一条批量跑的教训

这一轮写的那个批量统计脚本，第一版把「有没有红」压在 `^FAIL` 这类通用行上，报出 2 套红，实际是扫描器按行匹配的错（`catcatch` / `matchgate` 两套都打了「全部通过」且退出码 0）。各套自检的通过行措辞本来就不统一（`FAILED: none` / `ALL GREEN` / `ALL PASS` / `全部通过` / `TOTAL: N FAILED: 0` / `共 N 条，失败 0 条` / `FAILURES: none`），而 `bt_boost_test.py` 会**故意**打出预期内的 traceback。**判红只看退出码，措辞只用来数 PASS** —— 计数为 0 本身就是红灯，不是绿灯。

改完后整批：**59 套、3652 行 `^PASS`、判红一项都没有**；`python -m py_compile server.py` 通过；服务按要求重启（PID 32320，127.0.0.1:8765）。

## 出包这一轮抓到的一处打包脚本 bug：排除表里多一个 `|`，包里的界面是空的

版本号升到 `v1.4.0` 后按 `--skip-runtime` 出了第一个包，脚本一路跑到「完成：…zip」，退出码 0，包内自检 `[check] / [probe] / [smoke]` 全过，泄漏扫描 `leaks=[]` —— **而那个包里根本没有界面。**

### 症状

打第一遍时目录大小打印里就写着 `static 0.0 B`（`plugins` / `extension` 同样 0 B），zip 里 9830 个条目一条 `static/` 都没有。`server.py`、两份 README、`music_search.py` 这些却都在 —— 因为它们是 `APP_PY` / `APP_FILES` 走 `shutil.copy2` 单文件复制的，**只有 `APP_DIRS` 那几棵树走带 `ignore=` 的 `copytree`**。smoke 检只打 `/api/music/status` 和 `/api/components` 两个接口，服务照样起、照样回 JSON，**界面空不空它看不见**。这个包如果就这么发出去，对方解压双击 `启动.bat`，浏览器打开是一片空白。

### 根因

`EXCLUDE_FILE_RE` 是分段拼接的，第一段结尾写成了 `…(pyc|pyo|log|zip|7z|rar|part|tmp|bak)$|`，下一段又以 `|\.bak-\d|` 开头 —— 拼出来中间是 **`||`，一个空分支**。正则里的空分支对任何字符串都在位置 0 零宽匹配，于是 `EXCLUDE_FILE_RE.search(任何文件名)` 恒为真，「排除表」当场反变成「全排除」，`ignore_tree()` 把 `static/` 里每个文件都报了回去。

这个写法是本轮给排除表加 `notify_outbox.json` / `login_state.json` / `cookiecloud_state.json` / `cleanup_state.json` 那几项时动到的（加的是 `.bak-\d` 那一段）。**本轮已有的四条打包断言一条都没拦住**：`auth_test` / `outbox_test` / `cookiecloud_test` / `cleanup_test` 那几处钉的都是「某个名字在不在 `pack_release.py` 的文本里」（字面量计数）—— 全排除是把不该进的挡得更狠，对「名字在表里」这种断言完全无害。**要测出这一类 bug，断言必须问语义而不是问字符串。**

### 改法（三处，缺一不可）

- **修表**：`pack_release.py:88` 那一行末尾的 `|` 删掉，分隔符交给下一段的开头。修完逐条验：`index.html` / `server.py` / `favicon.svg` 不再匹配，而 `config.json`、`config.json.bak-1712345678`、`app.log`、`mcp_calls.log`、`pack_release.py`、`x.pyc` 照旧全部命中。
- **补语义自检**（`tests/cleanup_test.py` 的 A 段，共 156 → **159 条全绿**）：A10 `import pack_release` 拿**真编译出来的那个正则**断言「随包文件一个都不许被判掉」（`index.html` / `server.py` / 两份 README / CHANGELOG / `详细功能介绍.md` / `music_search.py` / `favicon.svg`，八个名字逐个过一遍真正则）；A11 反向钉「该挡的还挡着」（本机状态文件、带时间的密钥备份、日志、打包脚本自己）；A12 钉下面那道在场自检确实接在流程里。反向验证：把带 `||` 的旧写法单独编译一份喂给同样的名单，`index.html` 立刻匹配（零宽空串），A10 会红 —— 这三条真能拦住这一次的事故。
- **加一道「必进包文件在场」闸门**（`check_present(dst)`，接在 `copy_app` / 写清单 / 写启动器之后、压 zip 之前）：点名要求 `static/index.html`、`server.py`、两份 README、CHANGELOG、`requirements.txt`、`components_bundled.json`、`启动.bat`、`使用说明.txt` 存在，并检查 `static` / `plugins` / `extension` 三棵树非空（以源目录有文件为前提），缺任何一项直接 `SystemExit` 中止，**不让空壳包压出来**。这一道的价值在于：它管的是「什么都没拿到」这类静默失败，而原来的泄漏扫描只管「多拿了东西」，两头都堵上才算闭环。

### 重打包的读数（与源逐项对过）

`[present] 必进包的文件与目录齐了（static 里 5 项）`；目录大小 564.7 MB（`runtime` 322.4 + `tools` 234.5 + `static` 770.6 KB + `docs` 1.2 MB + `extension` 28.7 KB + `plugins` 2.3 KB + `chromaprint` 4.0 MB）；`[check]` 14 个顶层模块、`[probe]` 包内 pip 装-导一轮、`[smoke]` 真起服务打两接口、组件命中随包清单 12 项，全过；泄漏扫描 `leaks=[]`，`cookies/` 里只有那句占位、`Downloads/` 空。zip 10899 个条目与包内目录逐个对齐，**应用文件与工作区逐字节一致**（`sha256` 前 16 位比；压完那一刻的读数，事后又动过的几份见「发布物」那一节）。与上一包 1.3.2 比，多了 `docs/详细功能介绍.md` 与 `docs/detailed-features.en.md` 两份（#40 那轮把细节从 README 搬过去之后，这两份才第一次进 `APP_FILES`），少 0 项。


### 发布物

- **已发包**：`dist/MediaDownloader-1.4.0-portable.zip`（**219.0 MB**，目录展开 564.7 MB：runtime 322.4 MB + tools 234.5 MB + chromaprint 4.0 MB + docs 1.2 MB + static 770.6 KB + extension 28.7 KB + plugins 2.3 KB），`appVersion` 升到 `v1.4.0 · Element Plus`（版本真源只有 `static/index.html` 那一处），两份 README 的徽章与包名、两份详细文档里那两处文件名同处改口。
- **这一节不写自己的校验值**：本文件是打进包里的，一个包不可能把自己的 sha256 装进自己肚子里 —— 数值只记在同名 `.zip.sha256` 里（`sha256sum -c` 或 `Get-FileHash` 都能核，那份 sidecar 不在包内，所以写得下）。当时那一版的 hex 是 `474b7add…8ce8`，**它已经作废**：同一个 `v1.4.0` 号下面后来又重打过，眼下 `dist/` 里这只包的字节以它自己的 sidecar 为准，最后一轮的读数记在本批末尾「发布之后这一轮」的「发布物」小节。
- **runtime 是复用的**：`--skip-runtime`，把 1.3.2 那一份用硬链接铺到新目录（`cp -al`，16.9 秒、不占第二份空间），包内 `pip 26.2.1` 与 18 个依赖、3 个工具版本原样带走；`components_bundled.json` 里 `app` 写的是 1.4.0。
- **包内自检四道全过**：`check_present`（必进包文件与目录在场，static 里 5 项）、`check_module_imports`（14 个顶层模块）、`selfupdate_probe`（包内 pip 装-导一轮）、`smoke_test`（真起服务打 `/api/music/status` 与 `/api/components`，随包清单命中 12 项）。私密扫描 `leaks=[]`，`cookies/` 里只有那句「放 cookies.txt 在这里.txt」占位，`Downloads/` 空。
- **出包后逐字节核过**：45 个应用文件（`APP_PY` + `APP_FILES` + `static` / `plugins` / `extension` / `docs/screenshots` 里没被排除的每一份）与工作区 `sha256` 全同，zip 内 10899 个文件条目与包内目录一一对齐，包内 `static/index.html` 读的到的版本行是 `appVersion = 'v1.4.0 · Element Plus'`。
- **压完之后又动过的三份（当时确实不一致，下面那一轮已经关掉这件事）**：拿工作区整棵树与包内再比一遍（两边都有的文件才计入），得数是 **42 份逐字节一致、3 份不一致**，差的正是 `CHANGELOG.md` 与 `docs/详细功能介绍.md`、`docs/detailed-features.en.md` 三份。原因是同一件：这几份记的是「这一轮做完之后才量到的东西」——两份详细文档里那处是 `cleanup_test.py` 的条数 156 → **159** 与「A 段末尾三条测的是打包」那句说明，本文件里那处是这一节当时想写的包体校验值（见上一条，那条口径本身已经改成不写字面 hex）。**包内那两份文档当时因此还写着 156 条**；按那次「重新打包一次安装包」的口径没有为几行文档再压第二遍。这处差异在「发布之后这一轮」那次重打里补齐了，验证方式写在最后那一节的「发布物」里（读的是 zip 里条目的哈希，不是 `dist/…-portable/` 那棵目录树）。
- **第一次打的那个包是空壳**（`static/` 是空目录，界面整个没进包），根因与修法写在上面「出包这一轮抓到的一处打包脚本 bug」那一节；那个 zip 与它的 `.sha256` 已被重打覆盖，现在 `dist/` 里这个 1.4.0 包是唯一一份。
- 上一包 `dist/MediaDownloader-1.3.2-portable.zip`（218.8 MB，sha256 `91763532…71348d`）**不含这一批的任何改动**，留在 `dist/` 只做回退用。
- **GitHub Release 已经发出去了（2026-10-16 点头之后）**：这一批 squash 成一条提交 `7ac0ff6` 推到 `origin/main`，打**轻量**标签 `v1.4.0`（与仓库既有的那几个同款），Release 条目挂着上面那只 zip 与同名 `.zip.sha256`。这台机器上没有 `gh`，`api.github.com` 也直连不通（直接打过去是超时），走的是 git 自己那条 `http.proxy`；令牌用 `git credential fill` 现取现用，不落文件、不打印。发完把资产回下过一次，哈希与 `474b7add…8ce8` 对得上。（**这只资产后来被同号的重打换掉过**，最后一次换的读数与本批末尾那一节一起记。）

## 复跑全批抓到的一处假红：站点代理判定吃的是这台机器的代理地址

出完包按要求又跑了一遍全批（这是复跑，不是出包前那趟），`siteproxy_test.py` 这次 rc=1：81 条里 69 绿，**C 段 12 条「该走代理」全判成了 `inherit`**。表一个字没动。

- **量到的原因**：那 12 条走的是 `S.proxy_decision(url)` 不带 `cfg_data`，于是读的是**真 `config.json` 里那台机器的 `proxy`**；本轮读到的那一份 `proxy` 是空串。`_decide_by_key` 在 `proxy_mode=auto` 且手填地址为空时会退去要系统代理，而 `HKCU\…\Internet Settings` 的 `ProxyEnable` 是 `0`（`ProxyServer` 记着 `<本机代理地址>` —— 这台机器自己配的本地回环代理，属于本机信息，下面所有读数一律这样脱敏，真值不进发布文档；这个键最后写入时间是 2026-10-15 13:00:56，也就是说当天下午之后系统代理一直是关的）—— 两头都空，就落成 `inherit`。
- **谁把 `proxy` 交回空串：没抓到现行，能排除的都排除了**。写了一个哨兵复跑（先把 `proxy` 钉成 `<本机代理地址>`，逐套跑，每套跑完比一次 `config.json` 里的值，被改就记下并原样钉回去），**59 套没有一套写过真 `config.json`**（`OFFENDERS: none`）——「批量自检把机器配置跑坏了」这条假设到此排除。留下的读数只有 `app-2026-10-15.log` 里 20:52:32 与 20:52:36 那两对：`[界面] 保存设置（1 项变更）` 加一行 `[界面] 保存设置`，后一行是前端那条写操作埋点（`/api/ui_event`），说明这两次保存**来自界面那条保存路**，不是自检里打出来的。但这一行按口径只记改动项数、不记值（配置里有 Bot Token / 代理这类内容，一律不落日志），所以「那一项就是 `proxy`」这句我没法从日志证明，只能记成：写入来自界面保存，改的是哪一项没有字面证据。
- **值按证据恢复**：18:44:11 那条下载日志逐字是 `[380d94dd] 代理: 走 <本机代理地址>（youtube，auto）`（尖括号是唯一脱敏掉的那截地址，其余逐字），而当时系统代理是关的（键写入时间在前），地址只可能来自配置那一份 —— 所以 18:44 时 `proxy` 就是这个值。恢复走的是界面同一条 `POST /api/config`、只交 `proxy` 这一项（不直接编辑 `config.json`，服务在跑），跑完两处读数一致：`GET /api/config` 顶层 `proxy='<本机代理地址>'`、`proxy_mode='auto'`，盘上同一份；顺手复核 `clipboard_watch=False`、`bt_auto_rules=[]` 仍是收尾状态。**这一项如果其实是人自己在界面上清掉的，那现在是我把它填回去了 —— 该由人定，写在下方待点头的那两处里。**
- **修的是自检，不是产品**：`tests/siteproxy_test.py` 的 C 段改成自带夹具 —— 喂 `cfg_data={"proxy": "http://127.0.0.1:9999", "proxy_mode": "auto", "proxy_by_platform": {}}`（假端口，见下条）那份测「该走代理」，喂 `proxy=""` 那份测「认不出的站交回系统」，并把 `S.system_proxy` 在 `try/finally` 里钉成回空串（跑完归还）。顺带补了一条正向断言：认不出的站点 + 用户手填了代理 → 照用手填的（`("proxy", "http://127.0.0.1:9999")`）。这条以前没法测，因为老写法只在「机器上代理正好为空」那一种状态下自洽 —— 换句话说那 12 条与「认不出的站还是 inherit」这一条钉的是**两种互相矛盾的机器状态**，无论 VPN 开还是关，总有一头像红的；它一直在测这台机器此刻有没有代理，而不是那张表。81 → **82 条，`TOTAL 82 FAILED: none`**。
- **我自己那个探针里的 bug**（记下来免得再信它的读数）：哨兵脚本读 `GET /api/config` 时取的是 `d["data"]["proxy"]`，而这条接口把配置**平铺在顶层**（`{"download_dir": …, "proxy": …}`，没有 `data` 这一层），于是「live」那一栏每次打印 `None`，看着像服务没收到值。改成顶层读之后 live / disk 两边都对得上。
- **仓库里不再留这台机器的代理地址**（点头之后做的）：上面那 8 处逐字地址统一写作 `<本机代理地址>` —— 真值只在盘上的 `config.json` 和昨天的日志里，发布文档不需要它。`tests/` 里 8 套共 24 处夹具原本直接抄这台机器真配的那个地址，现在换成假端口 `http://127.0.0.1:9999`：这些断言从来不连那个地址，只是把值喂进去再比回来，换号不影响判据。**改的是自检与文档，随包代码一行没动**（`tests/` 不进包），那 8 套重跑一遍 —— siteproxy 82、cookiecloud 153、flacref 28、musicfavorites 83、subrss 57、subtg 62、telegram_channel 43、telegram_mt 52，合计 **560 条断言、exit code 全 0、判红 none**。还剩两处面向用户的示例（界面报错文案与一处文档串，用的是这类客户端的常见默认端口，不是本机配置记录）和 `music_search.py` 里一句「本机实测」注释没动 —— 这三份都在 1.4.0 那个包里，按「不重压、保持这一份包」的口径不为注释去动随包文件，下一轮出包顺手改掉。
- **复跑读数**：**59 套、3656 行 `^PASS`、判红一项都没有**（`RED: none`，`BAD text lines: none`；siteproxy 那 12+1 条从 69 回到 82）。这一趟是压包之后跑的，只动了 `tests/siteproxy_test.py` 一处和文档，随包的 `server.py` / `static/index.html` 没有再变，因此没有为它重压包。


## 发布之后这一轮：截图换成 v1.4.0 的界面、音乐结果表把富余摊开、重出包换掉 Release 资产

v1.4.0 发出去之后接着三句要求：「跑一下音乐结果表确认排版」、「选 a，并把 github 页面截图也更新下」、「重出一版并替换 Release，把艺人/专辑也改成 min-width 让富余摊开」。**版本号不动，仍是 `v1.4.0`** —— 这一轮不升号，是把同一个号的发布物换掉。

### 先记一条我自己的误判（「排版不好看」得有个能核对的对象）

上一轮我报「结果表右边空一大条、标题列写死 160」，**两句都不成立**。固定视口量下来：1680 时卡片 1420、表 1378、八列之和 1378 —— 表本来就是满的；`标题` 那一列早就是 `min-width="160"` 而不是 `width`，富余全被它一家吃掉（1680 下 468 px）。真正难看的是这件事的反面：**标题 468 px 装两三个字的歌名，而 艺人 120 / 专辑 110 是硬宽度，稍长就变省略号**。写这一段是为了以后翻记录时能分清哪句是量出来的、哪句是看出来的。

### 音乐结果表：富余摊到三列

- 两张表一起改：搜索结果那张（`static/index.html:3141`、`3142`）与「自建收藏清单」那张（`3218`、`3219`），`艺人` / `专辑` 由 `width` 换成 `min-width`，下限数值不变（120 / 110；收藏表那列原本写死 100，一并提到 110 与搜索表同口径）。
- 分配规则是 Element Plus 的：写死 `width` 的列不参与，剩下的空间按各 `min-width` 的比例分给弹性列。所以改完是 标题 : 艺人 : 专辑 = 160 : 120 : 110 在摊，不再一家独吞。
- 读数（headless Chrome 固定 1920 视口、一次真实五源搜索 74 条）：表宽 1618 = 42+386+288+264+190+70+118+260，其中 **标题 386 / 艺人 288 / 专辑 264**。专辑那一列现在「Songs From a Secret Garden」「周杰伦地表最强世界巡回演唱会」这种长度整条放得下。
- 固定宽那四列（来源 190 / 时长 70 / 品质 118 / 操作 260）没动：它们装的是标记与按钮，摊宽只会让按钮行右边留白。

### 截图这件事有个前提：不能在天天在用的那个实例上拍

六张 `docs/screenshots/*.png` 是 v1.2.8 时期拍的（侧栏还没有「磁力 / 种子」，音乐页是空结果）。直接拿 8765 拍会把这台机器的订阅、下载目录、已登录站点一起发到公网，所以走一次性干净实例：

- `MEDIADOWNLOADER_STATE_DIR` 指到临时目录 + `MEDIADOWNLOADER_PORT=8799` 另起一份。这个环境变量搬得走 config / history / subscriptions / cookies / Downloads / app.log（server.py:55 起那一片），**搬不走** `tg_session/`、`browser_sniff_profile/`、`catcatch_rules.json`（这三个钉在 `APP_DIR` 上），所以那份克隆实例只要不碰 Telegram 与浏览器嗅探，就与本机数据无关。新目录里 `web_auth_enabled` 默认 `False`，不用登录。
- **拍之前先把「保存目录」改成中性值**（整包 POST 一份 `download_dir = C:\MediaDownloader\Downloads`）。不改这一处，首页那张图正中间就把本机用户名发出去了 —— 与前面「仓库里不再留这台机器的代理地址」是同一条规矩，只是这次的泄露面在像素里而不在文本里。
- 六张的取景与尺寸：home 明 / 暗 1920×1080、聚合搜索 1920×560、音乐 1920×1026、订阅 1920×860、TG 频道 1920×560。订阅那张从 568 加高到 860 是为了让高亮中的「订阅」整条进画面（新版侧栏多一项，568 下它掉在折线以下，图里看不出这是哪一页）；音乐那张 1026 是裁到最后一整行结束，不把行切成两半。
- 音乐那张**跑了一次真搜索**（关键词「夜曲」，五源，74 条）。图里那句「Spotify —— 180s 内没跑完，本次已放弃等待」没修掉：那是这台机器当时的实话，不是摆拍出来的漂亮图。
- 拍完关掉克隆实例、删掉那份临时状态目录与 `C:\MediaDownloader`，8765 那个自始至终没重启过（截界面这件事只读不写，但**它读的是那份临时实例**，不是用户的）。

### headless Chrome 的三个坑（都实际踩过一遍）

- `page.goto(..., wait_until="networkidle")` 在这份界面上**永远超时** —— 进度流是一条挂着的 SSE。换 `domcontentloaded` + 等 `.nav-item` 出现。
- 点侧栏会把侧栏自己滚走，主区也会滚。截图前要把所有 `scrollTop` 归零、鼠标挪回 (0, 0)，否则「订阅」那张里高亮项掉出画面，还留一圈 hover 底色。
- 想「裁到整行结束」不能靠改视口高度去凑：改高度会让表格重排、行边界跟着动，凑完照样切一行。改成按 `getBoundingClientRect().bottom` 量出边界、截图之后用 PIL 裁那一段。

### 自检

- **`matchgate_test.py` 的 G9 是红的，而且红在这次发布之前就已经红了**：断言要的是 `"> 不像</span>"`（「不像」前面多一个空格），界面上真实的那一行是 `<span v-if="row.score_reject" class="msrc-flag msrc-flag--bad" :title="row.score_reject">不像</span>`。`git show HEAD:…` 两份都还是这个对不上的样子 —— 也就是说上面「复跑全批：59 套 / 3656 项 / `RED: none`」那句读数里，**这一套是被漏判的**（3656 这个条数本身没错，红的那条不打印 `PASS`，所以条数看不出来；判红要看每套的退出码）。改的是断言不是产品：换成 `:title="row.score_reject">不像</span>`，比原句更严，同时钉住「悬浮里就是整句拒因」。
- 复跑全批还纠出**跑法本身**的一处错：cwd 必须是 `web_app` 根。`potdaemon_test.py` / `potcomponent_test.py` / `matchgate_test.py` 三套会按相对路径去读 `pack_release.py` 与 `static/index.html`，在 `tests/` 下起就 `FileNotFoundError` —— 第一遍就是这么误红三套的，不是产品问题。
- 修完复跑：**59 套、3796 项（其中 4 套打印 `OK` 而非 `PASS`，共 140 项，`^PASS` 口径仍是 3656）、判红一项都没有**；`python -m py_compile server.py pack_release.py` 通过。

### 发布物（这一轮重打的这一版）

- **随包变的是两份东西**：`static/index.html`（两张表的 `艺人` / `专辑` 由 `width` 换成 `min-width`）与 `docs/screenshots/` 那六张（音乐那张按改完的排名重拍过）。`server.py` 与 `pack_release.py` 一个字没动；`tests/matchgate_test.py` 那条 G9 改的是自检，而 `tests/` 不进包。
- **产物**：`dist/MediaDownloader-1.4.0-portable.zip` **219.2 MB**，目录展开 **564.9 MB**（`runtime` 322.4 MB + `tools` 234.5 MB + `chromaprint` 4.0 MB + `docs` 1.3 MB + `static` 771.8 KB + `extension` 28.7 KB + `plugins` 2.3 KB），zip **10899** 个条目。`appVersion` 仍是 `v1.4.0 · Element Plus`，**这一轮不升号，是把同一个号的发布物换掉**。校验值照本批上面那一条口径，不写死在这份随包文件里（一个包装不下自己的校验值），精确字节与 hex 都在同名 `.zip.sha256`，在 `dist/` 目录里 `sha256sum -c` 直接核。
- **`--skip-runtime` 那一趟**：runtime 用硬链接复用上一版的 `runtime/`，不占第二份空间，整趟十几秒。
- **包内自检四道全过**：`check_present`（必进包文件与目录在场）、`check_module_imports`（14 个顶层模块）、`selfupdate_probe`（包内 pip 装-导一轮）、`smoke_test`（真起服务打 `/api/music/status` 与 `/api/components`，随包组件清单命中 12 项）；私密扫描 `leaks=[]`，`cookies/` 里只有那句占位、`Downloads/` 空。
- **核的是 zip 里的条目，不是 `dist/…-portable/` 那棵树**：45 份应用文件与工作区 `sha256` 逐字节全同（这一轮新换的那九份 —— 本文件、两份详细文档、`static/index.html`、六张截图 —— 也在其中）。上面「压完之后又动过的三份」那处差异到这一版关闭：两份详细文档里 `cleanup_test.py` 写的是 **159 项**，包内外一致。
- **与 GitHub Release 的关系**：这一刻挂在 `v1.4.0` 那条 Release 上的资产是本小节的**上一版**（229,822,034 B，读数从 API 的 `digest` 字段读回、上传时间 `2026-10-16T03:56:11Z`，与当时本地那只字节相同）。这一版压完之后要不要再把资产换掉，是要人点头的那一步；换了之后请以 GitHub 的 `digest` 字段为准，本文件不追记字面 hex —— 否则每补一次数字就要多压一包。
- **git**：这一轮的随包改动（`static/index.html`、`docs/screenshots/music-search.png`）、`tests/matchgate_test.py` 与本文件在压包之后一起提交、推 `origin/main`（人已点头），所以提交树与包内字节一致，Release 上那份下载能从仓库复现。

## 发布之后又修的自检脚印：硬字幕与订阅规则这两套不再往天天在用的那台实例上跑

界面「运行日志」页上留着一串 11:42 与 11:47 的烧字幕记录（`开始烧字幕: clip.mp4 ← clip.srt`、`已停止烧字幕: big.mp4，半成品已删`…），问的是「这些怎么还在」。

- **根因不是残留、也不是哪里失败**：`tests/hardsub_e2e.py` 的 `BASE` 写死 `http://127.0.0.1:8765`，文件头教的跑法就是「先把平时那台服务起起来再跑」。素材与产物确实只落 `%TEMP%\md_burn_selftest`，可**日志是那台实例自己写的**，落项目根 `app.log`。读数能对上：`app.log` 每行的 `seq` 在那两段是连续的（112→127、128→143），说明写它们的始终是同一个进程；两串内容一字不差 = 同一套件跑了两次；`big.mp4` 那几条 warning 是 F 段「停止烧字幕、半成品要删干净」那几条断言自己造出来的，不是产品报错。
- **改法**：这套件现在**自己起一份沙箱实例** —— `MEDIADOWNLOADER_STATE_DIR` 指到 `tempfile.mkdtemp()`、`MEDIADOWNLOADER_PORT` 取一个 `bind(0)` 空出来的端口，等 `/api/status` 通，跑完 `terminate()` + 连状态目录一起删。这套口径与前面「截图不能在 8765 上拍」那节同源（`STATE_DIR` 搬得走 config / history / cookies / Downloads / app.log；`tg_session/`、`browser_sniff_profile/`、`catcatch_rules.json` 钉在 `APP_DIR` 上，而这套件不碰 Telegram 与浏览器嗅探，所以那三处不会长出东西）。想看真机表现仍可 `--base http://127.0.0.1:8765`，那种跑法日志必然落进那台，G 段自动跳过。
- **加了两条把这件事钉住**（34 → **36 处 `check()`**）：G1 只比对项目根 `app.log` 里**本次新追加的那段字节**（按跑前的 `getsize()` 定位再 seek），断言其中没有「烧字幕 / 双语导出 / `md_burn_selftest`」—— 不比对全文，是因为那台实例可能同时在写，比全文会误红；G2 是正向对照，读沙箱自己那份 `app.log`，确认这些记录**确实落在了该落的地方**，免得 G1 因为「什么都没写」而空过。
- **读数**：`python tests/hardsub_e2e.py` → `[沙箱] 实例已起：端口 10492`、**34 条 `PASS`、`FAILED: none`、rc=0**，跑完 `[沙箱] 实例已关，状态目录已删 → False`、`%TEMP%\md_burn_selftest` 也不在了。断言名逐个与改前的版本比过一遍：**旧的一条没丢，多的就是 G1/G2**。4416 端口那个 `bgutil-pot-server` 的 node 进程创建时间是 2026-10-14 09:56:47，不是这一趟留下的（沙箱那份如果 own 了 POT 服务，`server.py` 的 `_pot_daemon_stop()` 会在退出时收掉）。
- **同一图案的另一处也一起挪进沙箱了（`tests/subrules_test.py`）**：日志里那句 `订阅「中文歌单」规则已更新：只要 长视频、时长≥5分钟、排除「预告」「直播」、每次最多 3 条` 就是它写的 —— 它过去把规则直接写进用户自己的第一条订阅，再按原字节盖回 `subscriptions.json`。现在它预置一条「沙箱自检订阅」（`enabled: False`，`scan_all()` 只挑 `s.get("enabled")` 的条目，所以调度器不会拿它去联网扫），环境变量必须在 `import server` **之前**设 —— `STATE_DIR / SUBS_FILE / LOG_FILE` 都是 import 那一刻算的，先 import 再改 env，本进程看的和被测实例写的那份就不是同一个文件。末尾加 H1~H4 四条（项目根 `app.log` 没多出这条自检订阅 / 记录确实只进了沙箱那份 / 用户自己的 `subscriptions.json` 里没有这条自检订阅 / 沙箱状态目录删干净），81 条 `PASS`、`FAILED: none`、rc=0；断言名与改前逐个比过：**旧的一条没丢，多的就是 H1~H4**。
- **`--base` 跑法的收尾换了口径**：`G9/G10` 两个名字留着，但内容改了 —— 老写法是「把 `subscriptions.json` 整包按字节盖回去，然后必须重启」，盖整包会连带冲掉那台实例自己并发写进去的 `last_check` 之类，而且盖完内存态仍是脏的。现在收尾是拿跑前从 `/api/subs` 读到的 `rules` 再 POST 回去（G9 还回原样、G10 内存态与磁盘同一份），不用重启。这条路径没在 8765 上实跑（跑了就等于又往那台的日志里写一段），沙箱路径实跑。
- **顺带把 `app.log` 里那两段旧记录删了**（人要的）：234 行 → **202 行**、35,663 → 30,061 字节，删掉的 32 行就是 11:41:38–11:42:20 与 11:46:41–11:47:24 两段的 `订阅「中文歌单」规则已更新` ×2 + `开始烧字幕 / 烧字幕完成 / 双语导出 / 已停止烧字幕` ×30，逐行按时间窗 + 话术前缀筛，别的字节一个字没动（CRLF 234 → 202、裸 LF 始终 0）。备份 `app.log.bak-20261016-125457`。核对「读→换」那几微秒有没有把实例自己的写入盖掉：动手前先测过那台实例内存里的 166 条日志与文件里的行**逐字节全同**，删完再比 —— 「内存里有、文件里却没留下的」恰好就是刚删的那 32 条，多一条都没有，说明没误伤。
- **两件要说清楚的**：①「运行日志」页读的是那台实例的**内存**（`LogManager` 启动时不从 `app.log` 回读），所以删文件不会让页面立刻干净 —— 要么重启那台（内存从空开始），要么用页面上的清空。②同一类指纹在 `app.log` 里还留着 **48 行**（09:19–09:25、11:36–11:37 三块，全是这两套改沙箱之前跑出来的），这次只删了点名的那两段，那 48 行等一句定夺。
- **与发布物的关系**：`tests/` 不进包，所以**随包字节一个字没变**，上面那只 12:24 的包与 Release 资产仍然有效；本文件这一节是压包之后加的，包内那份 `CHANGELOG.md` 因此又旧一节 —— 与「校验值」不同，这一处不影响任何数字，要不要为它重压一次听人的。

---

## 界面多语言的第一批：外壳、一份英文发布记录、包内一段英文速览

要求是「界面支持多语言，readme 也支持多语言」。口径先定死三条：**只翻前端界面文字，后端话术一个字不翻**；zh / en 两种，**默认跟随浏览器**；**先骨架，再按模块分批**把各页正文翻下去。

### 界面这一批

- **词表单独一份** `static/i18n.js`：zh 与 en 两套键完全相同的表，占位符写 `{n}`，`t()` 的退回链是 en → zh → 原键。
- **顶栏多一组 `AUTO / 中 / EN`** 小按钮，与主题点并排。偏好写进后端配置 `ui_language`，走 #32 那条「只交改动项」的自动保存；`localStorage` 只当镜像，为的是重载之后第一帧就不跳语言。后端里这个键只占 4 行（DEFAULTS、`ConfigBody` 字段、`_apply_config` 钳位的 if 与赋值），另加一行 `UI_LANGUAGES = ("auto", "zh", "en")`；它落在 DEFAULTS ∩ ConfigBody 且不在禁恢复名单里，所以「恢复默认」自动带上它，不用另写代码。
- **Element Plus 的内建文字跟着换**：`.use(ElementPlus, {locale})` 只在创建那一次读，改成 `<el-config-provider :locale>`；那个 computed 必须把语言当**参数**收进去（`elementLocale(uiLang.value)`）才会失效重算 —— 在函数体里读 `I18N.lang` 那个非响应式的值，永远等不到重跑。en 的词包没加载上就退回 zh-cn，绝不把 locale 传成 `undefined`。
- **helper 叫 `tr` 不叫 `t`**：模板里有 7 处 `v-for="t in …"`（两处主题色板、`status.throttle`、三个分页器、`tgTypeOptions`），叫 `t` 会被它们就地顶掉。
- 侧栏 17 项、5 个分组标题、页面标题与品牌名从此只有词表这一份真相（原先硬写在 `navs` 的 `label` 与 `NAV_GROUPS` 的 `title` 里）。
- **没翻的部分写进注释**：后端返回的报错正文、运行日志、订阅规则摘要都是落盘记录，也是几千条断言的对象；`friendlyError` 那 22 条分支要等它点名的界面路径（「设置 → 网络与并发」这类）先翻完再动，半成品对照只会让报错与界面各说一种语言。

### 自检

新增 `tests/i18n_test.py`：75 项、离线、不起服务。A 词表（两套键集合相等、值非空、`{n}` 成对、不含 `${` 与 HTML、首尾无空格）；B 模板键（出现的 `tr('…')` 全在表里，`nav.` 17 条、`navGroup.` 五个加分组兜底的 `other`、`page.<key>` 一条不缺，也不许多出没人用的键）；C 接线（脚本顺序、`boot()` 在 `createApp` 之前、en 词包在位、provider 一开一合、`epLocale` 是 computed、明暗两套 CSS、`loadSettings` 把配置值与 localStorage 对齐）；D 后端那四处与「恢复默认收得到它」；E 打包（`static` 在 `APP_DIRS`、`i18n.js` 进包、LF 行尾，再用 AST 确认这套件自己不外联不起进程）；F 边界（`friendlyError` 仍 22 条分支且不含 `tr(`、后端原话那段提前 return 还在、`logAction` 仍写中文、zh 值都含中日韩、没有一条 zh==en）；G 用 node 实跑词表，30 处观察断言 29 项。

### 浏览器真读数

沙箱实例（`MEDIADOWNLOADER_STATE_DIR` + `bind(0)` 挑的空端口，绝不在 8765 上试），V1~V24 全过：点 EN → 磁盘上的 `config.json` 里出现 `"ui_language": "en"` → 清掉 localStorage 重载仍是英文；POST zh 重载回到中文且「中」高亮；auto + 浏览器 en-US → 英文且 AUTO 高亮。日期表头变成 `Sun Mon …` 是 provider 真生效的证据，不是看代码推出来的。布局没被那层包装挤歪：侧栏 212、主区左 212、两栏等高、语言行与主题点对齐。控制台无报错；这一趟没往项目根的 `app.log` 写任何东西（跑前 23131 → 跑后 23131 字节）。

### readme 这一批

先量再说：`README.md` / `README.en.md` 是 89 / 91 行的一对，`docs/详细功能介绍.md` / `docs/detailed-features.en.md` 是 792 / 791 行的一对，都标到 v1.4.0 —— **本来就已经双语**。真正缺英文的是三处，这轮都补了：

- **`CHANGELOG.en.md`（新增）**：英文摘要，不假装是逐句对照。里面点名的每个标识符都回到代码里核过一遍才落下（`X265_TIMEOUT_MULT = 3.0`、`NOTIFY_RETRY_DELAYS = (30, 120, 600, 1800, 3600)`、`AUTH_PBKDF2_ROUNDS = 240_000` 与 `os.urandom(16)` 的盐、`QC_TL_CJK_CPS = 9.0` / `QC_TL_LATIN_CPS = 14.0`、`max(10.0, min(90.0, media_seconds * 0.08))`、`_cc_key_str` 的 `md5(f"{uuid}-{key}")[:16]`、`self.pending = held + skipped + self.pending`、48 位机器令牌来自 `secrets.token_hex(24)`、口令存储格式 `pbkdf2_sha256$轮数$盐$派生键`）。两条口径写进文件开头：**源日志里的 `server.py` 行号是当时那一轮的，代码早已移动，摘要只留名字不留行号**；**发布物的读数不抄日志里某一时刻的值**，这轮直接核 API 当下的 —— `v1.4.0` 资产 229,823,103 字节，与 `dist/` 里那只同名同字节、与同名 `.zip.sha256` 的 digest 一致，也就是说上面「Release 资产还是上一版」那句已经过期，留作历史；真正与包内不一致的只有文档本身（含本文件与那份英文摘要）。
- **包内 `使用说明.txt` 末尾加一段 English quick start**（`pack_release.py` 里 `README_SHARE` 那个字符串）：七条 —— 解压、双击 `启动.bat`、端口被占怎么办、Cookie 怎么加、界面语言那个开关、组件在程序里更新、包里不带任何人的账号数据。开头写明「其余是中文，完整英文说明看 README.en.md」。只改字符串，**重打包才落到包里**，这一轮包没动。
- **Release 正文尾部加一段 English**：PATCH 只动正文，改前改后两个资产的 `name` / `size` / `digest` 一个没变（zip 仍是 229,823,103 B / `sha256:4ea6a8ec…`，sidecar 未动），正文 2478 → 5192 字。

顺带两处一致性：`CHANGELOG.en.md` 进 `APP_FILES`（README 里指向它的链接不能进包成死链），`cleanup_test.py` 的 A10「随包文件一个都不许被排除表判掉」名单里补上它；动手前先拿排除正则实跑一遍 —— `CHANGELOG.en.md kept`，且 `EXCLUDE_FILE_RE.search("")` 仍是 `False`（#44 那一课的写法：判语义不判字面量）。`python -m py_compile server.py pack_release.py` 通过，`cleanup_test.py` 159 条全绿。

本轮没出包：`appVersion` 仍是 `v1.4.0`，`dist/` 那只与 Release 资产都不动；标签按「先不动」留在原处。各页正文的翻译排在后面几批。

---

## 界面多语言的第二批：17 个页面逐页翻进词表（同一轮内，接在多语言第一批之后）

上一批只翻了外壳（侧栏、分组标题、页头、顶栏、Element Plus 内建文字），词表里 52 个键。这一批把**每个页面的正文**全部搬进词表，一页一次提交，17 页走完。

### 口径两条（其中一条把人原先点的改了）

- **边界**：从「只翻前端、日志一个字不动」改成 **前端全量 + 运行日志也跟着切**。
- **切法不是去改已经落盘的那句话**：条目仍然带中文原文 `message`（它是历史记录、归档文件与几千条断言的对象），另外带一组可选的 `k` / `kv`；英文界面按 `k` 现拼一句显示，没带键的、旧条目、词表里查不到的，一律显示 `message`。**后端从不读 `ui_language`** —— 同一个日志文件，中文界面看中文，英文界面看英文，字节不变。`LogManager.log` 因此签名变宽，六套自检里的假 `log()` 补上 `k, kv` 形参。

### 词表与页面

- 两份词表现在各 **2481 个键**，键集逐键相同（闸门 B3/B4/B10 管着），`static/index.html` 里 `tr(` 2640 处。按页命名空间数一遍（zh 一份）：`settings` 823 · `music` 234 · `files` 169 · `subs` 168 · `bt` 151 · `tg` 118 · `home` 115 · `live` 73 · `sniff` 59 · `queue` 59 · `voice` 58 · `info` 56 · `search` 36 · `library` 36 · `favs` 33 · `history` 15 · `logs` 19，其余是 `common` 48 / `nav` 17 / `page` 17 / `header` 16 这类跨页共用的。**每个页面块的模板中文残留清零**，含中文的行只在注释里（注释讲代码，不算界面文字）。
- **数据表存的必须是键不是字面**：`tgTypeOptions` 从 `label: '视频'` 改成 `labelKey: 'tg.typeVideo'`、`QA_TAGS`、`SUB_KIND_META`（拆成 `labelKey`/`hintKey`）、音乐那三张选项表、`dateShortcuts`（常量改 computed）同理 —— 语言是运行时切的，模块初始化时把中文焊死就翻不动。这类「表里第二条 label」由闸门 I10 钉住。
- **复用而不是重造**：`common.colDuration` / `colStatus` / `colOps` / `colSize` / `colMtime` / `colType` / `colReason` / `refresh` / `dl` / `cancel` / `stop` / `langZh|En|Ja`、`subs.dateTo`、`files.pagerHint`、`status.failed`、`info.colRes`、`files.openDir` 都是后面几页挪进 `common.` 或直接从别页借的，中文一字未改；反过来「音质」不借 `common.colQuality`（那是「品质」）、「订阅」这枚行内按钮不借 `nav.subs`（侧栏是名词、这里是动词），理由写进词表注释。
- **`formatCount` 按语言分两套断点**：中文那支的字面与阈值一个字节没动（16.0亿 / 1.2万），英文那支改 K/M/B，离线侧 I13a–c 三条分别钉住。

### 逐页闸门长成了什么样子

`tests/i18n_test.py` 从 75 项涨到 **491 项**：I 组按页钉（`PAGES_DONE` 的模板块、`PAGE_HANDLERS` 的处理器函数体、`RESIDUE` 允许留中文的逐行名单、`MAIDIAN_EXPECT` 每页埋点条数）；H 组日志键通道（真跑 `LogManager.log`，`LOG_FILE` 临时挪走）；A9–A11 首尾空格与英文标点；C12/C17–C22 接线与接缝；G 组用 node 实跑词表。新加 `tests/pagemount_test.py`，40 条（P1~P40）。几条只有渲染才现形的：

- **I7**：模板调用过、且在 `setup` 里定义过的处理器，必须出现在 return 名单里。踩这一条的是 `taskHeadline` —— in-DOM 模板漏一个不是「那一行不显示」，是**整页渲染抛错**，静态切片看不出来（沙箱里语言钮从 3 个变成 0 个才看见）。
- **I8 / `MAIDIAN_EXPECT`**：每页 `uiName` / `logAction` / `logSort` 的行数按页钉死（bt 7、music 5、files 4、tg 1、voice 2、favs 2、history 0、log 2…）。这些动作名属于 `ACTION_NAMES` 那一批，现在硬翻会把该由那批收的中文悄悄吃掉；多一条少一条都判红。
- **I11**：`· 最近一次` 这类分隔符，值里写一份、模板里再留一份，界面就印成「· ·」。猫抓统计行就是这么印错的（源码看不出来），按「分隔符算排版」改回模板留点、值里只留文案，并补反向对照（写回带点的版本必须判红）。
- **I12**：直播任务那一筛拿的是后端标题里的「直播」两个字，把这行翻掉，直播页永远为空。
- **I6 `RESIDUE`**：允许留中文的行逐行对（例如设置页埋点那 17 条动作名），悄悄多一行或改了名都红。

### 顺带修掉的产品缺陷与自检假绿

- **`226ee9d`：`ElMessageBox` 的按钮词跟着界面语言走**。它是命令式弹的，不经过 `el-config-provider`，语言只在 `.use(ElementPlus)` 那一刻定过一次 —— 切成英文后正文已翻、按钮还印着「取消/确定」。包一层 confirm/prompt/alert：缺哪个补哪个，调用方写死的**一概不覆盖**（设置页「重置机器令牌」在英文下仍是「先不 / 重置」），`alert` 不硬塞取消键。C17–C20 钉这三条。
- **`28e7907`：两截字面量拼一句时英文少空格由闸门盯着**（C21/C22）。订阅页实测印出 `thelatest` / `butqueues`，闸门第一次跑又抓到解析页 `byte for bytedownloads` —— 中文连着写不用空格，英文必须留，空格补在 en 那一份的接缝上。
- **九套自检被这次搬字挪位弄红，其中三处是假绿**：那几套原来在 `index.html` 里搜中文原话，文字搬进词表就搜不到东西了；改成「 markup 接的是哪个键 + 那个键的中文还是不是那句原话」两半之后，露出 `cookiefirst` 的 I8 搜「默认关」命中的从来是剪贴板那格的提示（#22 明写要上屏的这句话其实没上过屏，补回 `settings.publicHintP1` 的中英两份），`cleanup` M5 与 `outbox` J14 搜到的是 `ACTION_NAMES` 埋点表里的同名串（界面有没有那句根本没在看），`runwindow` G11 不是红而是直接抛 `ValueError` 把整套截停在半路。**改前 54 OK / 7 FAIL → 改后 61 个退出码全 0**。

### 验证怎么做

每页都跑活体 A/B：自起沙箱实例（自己的 `MEDIADOWNLOADER_STATE_DIR` + `bind(0)` 空端口、`download_dir` 指向临时目录），HEAD 那份单独 `git worktree` 出来当对照组，两边喂同一份假数据、点同一串步骤，比的是浏览器渲染出来的文本节点 —— 中文那份**逐行与改前一致**，英文那份前端中文 0 行、印键名 0 处、`pageerror` 0，`library_cache.json` 按字节还原。设置页剔掉随机器/时刻变的行之后改前 769 行、改后 768 行，唯一实质差别就是那句补回来的「默认关。」。TG 页八个臂（两版 × 中英 × 匿名/会话）里下拉那五项在英文界面印成 `video / audio file / document / voice message / photo`，是 `labelKey` 这条路真走通的证据。

### 这一批没动的（另起三批）

`friendlyError` 那 22 分支（要跟界面路径一起改）、后端写中文日志的正文（逐条配 `log.*` 键）、`ACTION_NAMES` 埋点表与 `[已隐藏敏感参数]`；此外还记下两类：英文界面剩的中文**全是后端发来的展示数据**（组件 cn 名、编码器显示名、`scheme_labels`、代理来源、风控预设名、条目标题与文件名），要后端另带 `k`/`kv` 才翻得动；`riskPresets` 那 4 个兜底标签与「胶水标点」（`${name}（${peer}）`、`join('、')`）跟那几批一起做。

---

## 只挂当前页：一次按键不再替 17 页常驻的 DOM 买单（同一轮内，接在多语言第二批之前先做）

17 个页面块一直是 `v-show`，全部常驻；资源库又在开机就扫，每行还带一个 `el-select`（连同 teleport 出去的整份预设选项）。60 个成品时，在下载页敲一个字要 **24.5 ms**（节点 6653、`el-select` 91 个），早过了一帧的 16.7 ms —— 所以体感是「每个页面都卡」而不是某一页卡。改成页面块 `v-if`、资源库进那一页才读缓存、行内下拉换原生 `select` 之后，同一把探针量到 **2.0 ms**（节点 564）。

- 代价说清楚：切到文件页 / 设置页现在每次都要重新挂载，实测 **0.52 / 0.33 秒**（改前 0.10 / 0.09 秒，因为那时它们从开机就挂着）。换来的是打字、勾选、拖动全程回到 2 毫秒。
- 页面块销毁不会顺手停掉预览播放器的声音，所以切页前先 `pause`。
- 新增 `tests/pagemount_test.py` 钉住这几条；`navlog` 那套把资源库从「进页不取数」挪到「进页取一次」。测量本身的坑（`MessageChannel` flush、`APP_DIR` 缓存串扰）各造成过一次误判，写在自检注释里。

## 内嵌封面改成真开关，英文词表的中文引号一并统一（同一轮内，接在上面之后）

「内嵌封面」那个勾以前有三处不算数：只在点「保存策略」时才落进 config（勾完直接点下载等于没勾）、队列兜底那条路写死 `embed_thumb=True`、写进去靠的是 ffmpeg 重封装那一趟（成了也不报告）。

- 现在音乐页四条下载路**每次都带当前勾选值**、默认开，写入只剩 mutagen 标签这一条通道。勾了就用 `audio_embedded_cover` 回读文件自己的标签，逐首写「已嵌入 / 没嵌上（原因）」，批量小结带成功与失败数，失败那份能展开看是哪几首。
- 顺带修两处读写：m4a / mp4 的封面在 `covr` 里，回读函数以前读不到它（界面预览 m4a 跟着一起瞎）；webp 硬贴个 jpeg 旗标回读能得到字节、播放器却认不出，等于假报「已嵌入」，现在按同一张表判成装不了。
- 新增 `tests/coverembed_test.py`（含假 cfg / 假队列的端点 A/B），`i18n_test` 252 项、全批 58 套绿。QQ 实测那条 flac 嵌进去的字节与同名 `jpg` 一致（md5 `ae3f607aab0f`）。
- **en 那半词表有 37 行用了「」**（home 9、queue 1、files 11、music 16，跨了前几批），英文界面里看着就是中文标点；zh 那半一个字没动（那里是对的 106 处）。直接换普通双引号会留下新问题：全角括号两侧本来不需要空格，换完就成了 `reuses"Match sources"and`，所以换的脚本顺手补空格，并加两条闸门 —— **A10** 值里不留「」（F8 只禁汉字，管不到 U+300C，所以以前一直没红过）、**A11** 不许出现 词-引号-词（拿 `reuses"Match` 做过阴性对照，确实会红）。

> 这一笔的「不勾时原样保留文件自带封面」那句后来被推翻：`#63` 那节改成真移出去，读数与口径在那一节。

## 启动不再看着像卡住：端口被占先说清是谁占着，就绪那行按真答过话再打（同一轮内，接在上面之后）

实测过再改的：健康启动的控制台永远只有那四行横幅 —— uvicorn 那句「Uvicorn running on」是 INFO，被 `main()` 里的 `log_level="warning"` 压掉了，于是 2.1 秒就在服务的一台，看着和卡死一模一样；端口被占时它也只丢一句 `Errno 10048`。两种情况摆在同一个窗口里没法分，就有人拿着截图问是不是卡住了。

- 启动前先自己试绑一次端口：占着就分两种说清 —— 答得出 `/api/health` 的是**本程序另一台**（劝人直接用原来那台，并把地址给出来），答不出的才是别的程序占着。两种都写一行运行日志、以退出码 1 结束，`.bat` 那种窗口里话留得住。
- 只认 `EADDRINUSE` 这一类错，别的绑定错误仍交给 uvicorn 自己报，不在这儿替它下结论。预检排在拉起各线程与 aria2 **之前**：端口都不归自己，就不该半启动一台出来。
- 横幅之后由后台线程轮询 `/api/health`，真答过话才打「服务已就绪」。选它当探针是因为它只读内存里的队列计数；`/api/status` 会真跑 `ffmpeg --version`、扫 Whisper 目录，拿它当就绪探针是本末倒置。
- 新增 `tests/startup_test.py`：A 组三个新函数的行为（裸 socket 与假 health 服务两种对照）、B 组接线顺序、C 组真起三台实例（空闲端口起来并答 `/api/health` / 撞本程序另一台 / 撞别的程序），每台带自己的 `STATE_DIR`。全批 59 套绿。

## 发布之后这一轮 · #65 整批下合集时先落进一层同名文件夹（默认关，接在 #59 之后）

起因是 Downloads 里那一季 12 集全平铺：12 个成品混在四十多个别的目录旁边。「用文件名模板开一层目录」这条路走不通 —— 合集那一趟的 `outtmpl` 是 `Path(out_dir) / template`，中间 `template.replace("/", "_").replace("\\", "_")`（server.py:6902）会把模板里的分隔符全换成下划线，所以设置里那栏写不出子目录。

### 后端

- 一个决定点：`playlist_landing_dir(base_dir, title, want, *, is_playlist=, is_live=)`（server.py:9591）。勾了才多建这一层；建不出来（路径被文件占着、权限不够）就回原目录并把缘故说清。文件夹在这里就 `mkdir` 出来 —— 日志那句「合集整批存到 X」里的 X 必须真的在场，不能先报后建。
- 名字有两个来处：① 解析回的 info 本身就是容器（整表那一颗），取容器自己的标题；② 逐条链接那一侧（「下载全部」「选中分集」「单条补下」走的是 N 条独立任务，容器不在手上），用入队时前端带过来的 `playlist_folder`。两个都没拿到就照实说「这一批仍平铺」，不兜一个谁都想不到的文件夹名。
- `playlist_folder_name()`（server.py:9579）刻意不复用成品名那套「空标题兜一个 download」：那是给文件准备的，这一层是用来分堆的目录名，宁可少建一层也不要造出一个认不出来的名字。清洗仍走 `safe_filename_component(…, 60)`（Windows 禁字符换掉、超 60 字截断、保留名加前导下划线），转义路径在这一层出不去：`../../` 会被换成 `_.._`。
- 只管整批那一趟：单条下载、直播录制照旧平铺（录的是流，不是一个合集）。合集这一层加在「下载目录」或自动分类命中的那个子目录**之下，不替掉它**。
- 开关进 config：`playlist_subdir`，默认 `False`（server.py:3635，老目录结构不突变），本次请求可覆盖；`playlist_subdir` / `playlist_folder` 都在 `TaskQueue._run` 的合并名单里（:10524），接口层的声明在 `ConfigBody`（:11613-11614、:11665）。
- 顺带改掉一句假话：设置里「文件名模板」原先举例 `%(uploader)s/%(title)s`，说这样能分子目录 —— 按上面那条替换，永远建不出来。说明改实了，要分层用这一项或「按链接自动分类落目录」。

### 界面

- 下载页那一颗勾（`static/index.html:2252`，`home.playlistSubdir`「整批下合集时存进同名文件夹」）带一段说明讲清生效范围与「不搬已经下好的文件」；综合设置的「保存位置」里同一件事再出现一次（:4817），两处绑同一个键、回填读同一个值（:8205-8206）。
- 三颗批量入口在入队那一刻把容器标题带进 `playlist_folder` 并随后清空（:12852 / :12912 / :12937），避免上一批的名字漏到下一批。

### 自检与活体

- 新增 `tests/playlistdir_test.py` 39 项：A 组清洗（用一条真实容器标题形状，含「合集·」「（全12集）」这类括号与分隔符）、B 组落点 12 项（没勾不许偷偷建夹、同一合集第二趟复用、叠在自动分类目录下面、直播不建、名字退化时那句「仍平铺」带路径、base 被文件占着时回原目录并说缘故）、C 组接线 16 项（config 默认、请求字段、合并名单、两条 outtmpl 都改走 `dl_dir` 且没有 `out_dir` 残留、界面两处绑定与回填、三颗入口带名字并清空、`CFG_LABELS`、模板那句说明、i18n 中英齐）、D 组用假队列端点实测开关与合集名真落到任务 `opts`。
- 活体：自起沙箱实例（自己的 `MEDIADOWNLOADER_STATE_DIR` + 空闲端口，config 与 cookie 都用副本）跑三趟 —— 不勾那趟平铺；容器那趟成品进 `<合集标题>/`；逐条那趟两个成品加 `pipeline.json` 一起进同一层，日志分别说「名字来自容器标题」「名字来自解析页带过来的合集名」。天天在用的那台实例没参与。
- **两条「实现顺手成了这样」的口径问过之后钉住了**（`bc2d9f6`，代码没动、只补自检）：`B13` 给这一批手动挑过落点（`opts.download_dir` 那一格）时，合集文件夹建在它**下面**而不是替掉它；`C17` 钉调用顺序 —— `playlist_landing_dir()` 的第一手参数就是这一趟算完的 `out_dir`，自动分类和手动指定都排在它前面，「加在下面」不是靠文案承诺而是靠这一行的位置。

## 发布之后这一轮 · #63 不勾内嵌封面时，把下载器已经塞进标签的那张图移出去

上面 #58 那一句「不勾就不嵌入」只保证了一半：我们自己不写了，musicdl 的 `auto_supplement_song` 默认还开着，它在打标签之前就把封面塞进了文件。于是界面不勾、成品里照样有图。当时归因写的是「自带封面、原样保留（抹掉要重编码，不该由这个勾选来干）」—— **那句是假话**：mutagen 删掉 APIC / PICTURE / covr 是改标签，不重编码，实测移图之后 ID3 之后那段音频帧字节与空白件一模一样。所以这一轮把它做成真行为，而不是把文案改圆。

### 后端（`music_search.py`）

- `strip_embedded_cover()`（:4937）：mp3 走 `ID3.delall("APIC")`，flac 走 `clear_pictures()`，m4a / mp4 删 `tags["covr"]`；认不了的容器不改、回 `False` 并说「这个容器的封面不是标签级写入，没动它」。**mp3 那条必须给 `padding=lambda _t: 256`** —— 不给的话 mutagen 把原来那段标签区当留白保住，图没了但几十 KB 空壳还留在文件头；而 `ID3.save(padding=256)` 会 `TypeError`，callable 才是它认的写法。
- 写完再回读：改过标签却还能读到图，照实报「回读却仍带着图」并回 `False`，不假装成功。
- `auto_tag_audio()` 在 `embed_cover=False` 的收尾调它（:5074）：文字标签照写，这个勾不是「别打标签」；同名 `.jpg` 一个字节不碰。
- `cover_verdict()`（:4910）：`want=False` 而文件里还有图 → `why="kept"`；`COVER_WHY_TEXT["kept"]`（:4906）的口径改成「勾了不嵌入，但文件里那张没能移出去」；`note_music_cover()`（server.py:18586）那一支由 info 升成 warning，逐行点名是哪几首没移出去；批量开头那句日志不再说「只是不写进文件」。音乐小结补上 `music.coverKeptPart`「，{n} 首封面没能移出去」（i18n.js:2011 zh / :4557 en），`music.embedMetaHint` 中英两句跟着改。

### 自检与活体

- `tests/coverembed_test.py`：C5 与 E 组按新口径改（`kept` 是失败的一种，不再是不进账的「保留」），新增 H 组 17 项 —— 先证图真在文件里再证移得掉、音频帧与编码时长前后一致、同名图片文件不碰、本来没图的文件不动它、只读文件返回 `False` 且给告警、flac / m4a 各一条、两条接线（`auto_tag_audio` 真调用、padding 用 callable）；F 组把小结那句和它读的 `s.cover.kept`、拼接顺序、中英两份键一起钉住。
- 活体（自起沙箱实例，不碰 8765）对同一首 QQ 的 flac 下两臂：勾上 → 回读 1 块 `PICTURE` / 157,712 字节；不勾 → 回读 0 块，日志「已从 … 的标签里移出（同名图片文件仍留在旁边）」。**两臂音频帧都是 153,430,544 字节**，同名 `.jpg` 与 album / artist / title / lyrics 文字标签两边都还在，整文件 md5 不同。改之前同一首歌的不勾臂是「回读仍有图」，这一轮才第一次拿到「不勾就真的没图」的读数。
- 一条按实说的限制，也钉进了自检（`bc2d9f6` 的 `H12/H12b/H12c`）：**flac 这一路体积不会缩**。删掉的 `PICTURE` 位置由 mutagen 补成全零的 `PADDING`（逐字节验过不是旧图残留），整文件字节数与音频帧起点都不变；mp3 那条靠 callable padding 把标签区收小（`H4`：体积回到空白件附近）。两种形状并存是实测，以后谁想「统一成都缩」得先推翻这条读数。

## 发布之后这一轮 · #66 换了容器的整批下载不再误报「写出 0 个文件」

挂了 `FFmpegVideoRemuxer`（目标容器选 mp4 / mkv / webm）或转音频之后，yt-dlp 处理完写回分集 info 的 `filepath` 仍是换容器前那一个（`.webm` / `.mp4`），成品其实躺在旁边换了后缀。`download()` 只认这个名字：分集那支逐条 `Path(pth).exists()` 判在场，于是整批全部判丢 —— 先打「列表 1 条，本次在下载目录写出 0 个文件」，`filepath` 空让 `prepare_filename` 渲染出一个挂 `.NA` 的名字，再被完整性校验说成「下载完成但文件不可用：工具报告成功，但目标文件不存在（文件已保留，未转存网盘）」，而 `.mkv` 确实在盘上。单条那一支早就有一段「按同名换扩展找回来」的循环，**分集那支没有** —— 所以只有整批这一路中招。

### 后端

- `resolve_written_file(pth, prefer)`（server.py:9546）：给的名字在场就原样还；确实不在才按同一个基名换扩展找。`prefer` 是这一趟要的容器，排最前 —— 同一个基名旁边可能既躺着上次选 mp4 留下的旧件、又躺着这次的 mkv 成品，按目标容器先找才不会认领错文件。换哪个扩展都不在场仍把原名还回去，让调用方照实说「文件不存在」，这里不替工具撒谎。
- 成品容器名单 `REMUX_FALLBACK_EXTS`（:9543）只定义一处，两处调用点共用（分集 :7171、单条 :7199），单条那一支的内联版本删掉，不再各抄一份各自漂移。（别处那几组 `.mp4` / `.mkv` 是「是不是媒体文件」的判据，另一种概念，没动。）
- `want_ext` 取这一趟算出来的 `merge_output_format` / `fmt`（:7153），不回头读设置里那份。找回之后仍按「真在场」才入账；「命中下载记录」那两条说法保持原样 —— 那是另一种「没有文件」，不能跟这个混成一回事。

### 自检与活体

- 新增 `tests/remuxcount_test.py` 18 项。A 组测 helper 自己：报 `.webm` 找回 `.mkv`、名字本来在场就不碰旁边、空串进空串出、抽音频同理（`.mp4`→`.m4a`）、新旧容器同场时按 prefer 挑不认领旧文件、全都找不到就原样还、标题带点不被 `with_suffix` 切错基名、prefer 不带点也认、父目录都不在不炸、名单外的 `.ts` 不当成品。B 组测接线：分集那支在 append 之前解析、单条那支换成同一个 helper 且内联循环已消失、判定排在 return 之前、名单全仓库只写一次、remuxer 确实挂在目标容器那一支。端到端那一套不假装能替，交给活体。
- 活体（自起沙箱实例，三臂各跑，目标容器=mkv，同一份 config 副本跑改前/改后两遍）：改前对照组同时打「写出 0 个文件」与「下载完成但文件不可用」，而盘上是那条 `.mkv`（2250 KB）；勾了合集建夹那一臂同一形状，只是文件嵌进了一层；逐条那一臂本来就 finished —— 正是「单条有兜底、整批没有」的形状。改后三臂全 finished，两组误报字样 0 行，对照组多出一个 `.pipeline.json`（以前 `filepath` 是空的，后段根本没拿到文件），沙箱 history 里这几条记的是 `xxx.mkv` + 真实路径，不再是 `xxx.NA`。跑完 md5 核对 `config.json` / `history.json` / `library_cache.json` 与跑前一致。
- **已经落在历史里的那几句旧误报不会被改写**：这一轮修的是形状本身，此前记录的「下载完成但文件不可用」与挂 `.NA` 的标题保持原样；按同名换个扩展去下载目录里找，那些成品本来就在（用户那台 history 里 2026-09-26 连续一批 12 条分集就是这个形状，逐条按同名换扩展去查，12 条全部找得到 `.mkv`，一条不缺 —— 它们没有当活体靶子，因为这一轮下不动）。

## 发布之后这一轮 · UI 参照批量（一）：把概念稿里的四件挪进产品（接在 #66 之后）

一份界面参考稿过了一遍，能落地的按项做，每笔各自带活体读数。这一节是**版面与导航**那四件，交互那三件（Ctrl+K 面板 / 顶部通知条 / 行内右键）写在下一节。

- **侧栏能折成只留图标**（`cf102fa`，#71）：17 项侧栏常驻占掉 212 px，笔记本上主区只剩 1228 px。折叠只改一个 CSS 变量 —— `.sidebar` 的宽度本来就写的是 `width: var(--sidebar-w)`，所以 `.sidebar.is-collapsed` 在同一个元素上把变量改成 64 px 就够，主区让位、宽度过渡全跟着走，**不需要第二份宽度真源**（闸门 P10 钉住「谁写死 212/64 就判红」）。折起来之后：分组标题整排收掉、组与组之间换成一条线（5 组 4 条，第一组顶上不画）、只剩图标就得靠悬停认页所以每项补 `:title`、角标与橙点改绝对定位到格子右上角（不然 47 px 宽的格子放不下）。状态记在 `localStorage` 的 `md_nav_collapsed`，跟「只读视图偏好」同一套约定，不进配置、不写后端。读数：展开 212 px / 17 个标签 / 主区 1228 px；折叠 64 px / 0 个标签 / 17 个图标 / 4 条组间线 / 主区 1376 px（Δ148 = 212−64，让出来的宽度确实接住了）/ 横向溢出 0；按键成本没退化（40 次逐字输入，展开 avg 2.68 ms → 折叠 1.85 ms）。**记一笔假测**：第一版给 `/api/tasks` 打桩塞了一条 downloading 任务，界面上角标却是空的，于是「折叠态角标有没有跑出格子」只断言了「没跑出」= 什么都没测；根因是首页那条轮询根本不敲 `/api/tasks`（只有停在队列 / live / 磁力页，或 `status.running>0` 才 `loadTasks`）。补成「先进队列把任务取回来，再折回去量」才算真测到。
- **折叠钮移进标题行右端**（`02dc91f`，#80）：原来它是标题行下面一条整宽的条，只有右端那 16 px 画着箭头、左边一大片空白也点得着，还自带一条 `border-bottom` 和标题行那条叠成两条线。现在是一枚 30×30 的方块，挂在 `.sidebar-logo` 里、`margin-left:auto` 顶到行末，热区就是看到的那块。折叠档没有跟着缩小图标也没有挤：64 px 里 36 的图标加 30 的钮并排放不下（差 2 px），所以让 `.sidebar-logo` `flex-wrap`，钮换行到图标下面、整行宽居中 —— 把两个都缩小硬挤的话钮只剩十几像素，等于点不着。闸门 P36/P37 钉「钮在标题行元素之内、排在品牌名之后、全文只有一枚」与两档各靠哪条规则。
- **文件页行内「更多」按功能族加分隔线**（`911595e`，#74）：那一行 15 项挤在一起，转写、流水线、人声分离、字幕工具、音乐标签五族全靠肉眼分。线只能挂在「确有一族在前」的项上，而这一份菜单每一项都由 `v-if` 决定在不在，所以不能一律写死：Picard 那一族在 `flac` / `ogg` / `wma` / `opus` 上是整份菜单的第一项（这四个扩展名不在 `isMediaFile` 的表里），那种时候线必须收起来，挂的是 `:divided="isMediaFile(row)"`。沙箱逐类文件量过（mkv / mp3 / flac / ogg / srt 各开一次下拉，按 `li` 顺序读线落在哪一项前面）。**记一笔坑**：Element Plus 2.8.8 的 `divided` 不给这一项加类，而是在它前面另插一个 `<li role="separator" class="el-dropdown-menu__item--divided">`；第一版按单项 `className` 里有没有 divided 去量，五条线一条都没读到，队列页那两个写死的对照组同样读空，差点把「属性没传进去」当成结论。闸门 P8/P9 钉「线只许挂在五个组首、且 Picard 那条必须是条件式」。
- **行内文本与控件垂直居中对齐**（`171cf38`，#69）：同一行里提示文字比按钮低半截。先量再改 —— 活体逐行比对行容器内每个子元素的 `getBoundingClientRect()` 中心，17 个页面共 **31 行偏差 ≥1.5 px**，且全部是同一个原因：`.hint` 的 `margin-top: 6px`。flex 的 `align-items:center` 居中的是「外边距盒」，内容因此被顶到控件中心下方 3 px。改法是 `.row-actions` / `.el-form-item__content` 里跟控件同排的 `.hint` 去掉那 6 px，用 `:not(.hint--block)` 排除独占一行的说明文字（那点间距正是它跟上一行的分隔，设置页限速时段、队列定时窗那几段多行说明改前改后像素一致，没有连带损失）。复测阈值降到 0.4 px：17 个页面每页 0 行不齐。
- **文件浏览页默认按修改时间倒序**（`9d4d377`，#77，与资源库那条同口径）：改的是三处联动 —— 模板 `:default-sort`（`static/index.html:3137`）、`fileSort`（:7167）、`fileSortDir`（:7179）。后端 `/api/files` 没动，这一页的排序本来就整个在前端 `filteredFiles` 里做，后端给的那一份只按「目录在前 + 名称」，改它等于把同一件事做两遍。活体造 5 项，故意让字母序与时间序结果完全不同，时间用 `os.utime` 钉死，读渲染出来的行序对上、目录仍然钉在最前。闸门 P35 把三处联动和「目录在前」那条比较器一起钉住。

## 发布之后这一轮 · UI 参照批量（二）：三件新交互 —— 跳页面板、常驻通知条、行内右键菜单（接在上面之后）

- **顶栏 `Ctrl+K` 面板**（`33638eb`，#72）。边界先说清：这一版只做「跳页 + 跑界面上的动作」，**不搜内容** —— 资源库 / 收藏 / 历史 / 队列各自页内已经有筛选框，跨页搜内容要把五份列表拉平到顶栏、命中之后还得先切页再定位那一行，那是另一件事，`header.searchTip` 那句提示就把这条边界写在界面上。面板里的动作五个：回到下载页并聚焦链接框、折叠/展开侧栏（接 #71）、切深浅色、切界面语言、暂停或继续整个队列；标签是动态的，侧栏折起来后那一行自己变成「展开侧栏」。匹配吃三份：当前语言的页面名 + 另一种语言的页面名 + 一张只拿去匹配、一个都不显示在界面上的别名表（空格分词，每个词都得命中，所以「aria2 队列」只剩队列那一条；真源仍然只有词表那一份，闸门 P16 钉「键必须是真页名」）。面板挂在 `.layout` 里、`.main` 外 —— `position:fixed` 的祖先一旦带 `transform` / `backdrop-filter`，包含块就变成那个祖先，弹层会歪进那一格里（`.card` 就带），这条由 P15 钉着。读数：打开后 22 行（17 页 + 5 动作）、焦点已在输入框、选中第一行；`文件`→文件、`file`→文件（中文界面敲英文也落得对）、`zzzz`→空态；`↓` 挪选中行、首行按 `↑` 绕到末行、回车执行；1024 宽下顶栏不横向溢出；明暗两套选中行的对比度 14.33:1 / 3.57:1 —— 亮色那一对就是本项目既有的「主色字压主色浅底」配对（`.icon-btn:hover`、`.hstat--live` 同一配对），要提得连那两处一起提，不由面板单方面改风格。闸门 P13~P16 四条：面板用到的名字必须在 setup 返回清单里（in-DOM 模板漏一个不是少一块，是整页空白且只在建应用时抛，而 I 组那类闸门只覆盖登记过的页块，面板挂在 `.layout` 上不在任何页块里）、`Ctrl+K` 的监听挂了也必须摘、`.layout` / `#app` 身上不许有 `transform` 与 `backdrop-filter`、别名表的键全是真页名。
- **顶部常驻通知条**（`522f9a2`，#73）。口径：只挂「此刻在场、但要进某一页才看得见」的事 —— 组件出了新版、通知欠发没送出、域名被限流降过速。三件事原来各藏在一页里（设置 → 组件与依赖 / 设置 → 通知补发队列 / 队列页那张 🐢 卡），人在下载页时永远看不到。一条一个事由，能就地办就就地办（去更新 / 立即重发·看队列 / 解除降速），办不掉的只提醒不代做。关闭记在 `sessionStorage`、按事由 id 记，同一次浏览器会话里一件事只关一次。**自动检测那条弹窗换成通知条，手动「立即检测」的弹窗留着** —— 人主动按的那一下要有回执，不该只多一条横幅。实现里三处值得写下来：吸顶不是 `top:0` 就完事（`.content` 自己带 22 px 上下留白又是滚动容器，sticky 的子元素按内容盒吸，实测滚下去之后有 22 px 的卡片从通知条上方切片过去；留白抽成 `--content-pad-y` 一个真源，通知条用 `top: calc(var(--content-pad-y) * -1)` 反推偏移）；事由行的深浅沿用令牌那两套（warn 用于「欠着 / 被降速」，info 用于「有新版」），暗色不需要另写一份颜色；组件名单的拼法抽成 `joinCapped()`（超过三个收成「等 n 项」），设置页那行与通知条共用一份。读数（自起沙箱实例）：开机报 4 个可更新时 `popup=False` 而通知条三条同时上屏；切到运行日志仍是 3 条（挂在 `.content` 顶上、17 页共用一处）；滚 520 px 后条顶 58 == 内容顶 58 且 `elementFromPoint` 仍落在 banner 里；「去更新」跳到设置并把组件卡片滚进视野、日志记「通知条跳转：设置 → 组件与依赖」；「解除降速」真调 `throttle_reset` 后那条自己收掉（3→2）；「立即重发」只把队列排到最前、条子留着（重发不等于销账）；`×` 之后 `sessionStorage` 写回 `["comp"]`，刷新后组件那条不回来、另两条照旧。明暗对比按数字判：暗色 warn 10.24:1 / info 14.33:1，亮色 warn 4.73:1 / info 14.68:1。成本：三条横幅常驻 26 个节点，按键 avg 2.52 ms vs 全关 2.30 ms（Δ0.22 ms）。两处是量出来才改对的：① `gotoCard` 原来是「找到元素就 `scrollIntoView` 一次」，页面是 `v-if` 现挂的，滚到位那一拍上面那些卡片还是空壳、数据填进来把目标往下挤 —— 实测停在偏 1358 px 的地方，不报错、看着就像按钮没反应；改成逐帧对齐（落点变了就再滚一次，连续 4 帧不动才收手、最多盯 90 帧），顺手让出通知条高度。② 「通知条让按键成本涨 1.15 ms」那一轮是假红：harness 只往 `/api/status` 注入了 `throttle`，而 SSE 的 `state` 事件同样带（`server.py` 的 `_sse_state`），开机一收到推送就把这条事由抹平了；补上 `/api/events` 桩之后那个桩按 `retry:800` 每 0.8 秒重连一次、每次重推一遍 state，通知条跟着重渲染，按键成本被它自己抬高 —— 把 `retry` 写成 60000 让它只推一次，同一把尺复跑才是 0.22 ms。顺带记下：前端 `if (d.throttle)` 拿到空数组也会覆盖（空数组在 JS 里是真值），这是对的，冷却期过了本来就该收掉，不是 bug。闸门 P17~P26 十条 + `navlog` B13/B13b。
- **行内右键菜单**（`f4592e6`，#75）。边界：这个菜单**不另写一份动作清单**，它把那一行现有的、真能点的按钮当场列出来，点菜单项等于替人点那颗按钮 —— 于是动作自己的埋点、确认框、成功失败提示全都照旧，也不会有「模板改了、菜单还在说旧话」的第二个真源。认三种行式样（Element Plus 表格行 / 任务卡片 / 原生 `table` 的行）。**让路同样是口径**：输入框、下拉框、勾选框上右键，正在选字时的右键，以及这一行根本没有可点动作时，一律不 `preventDefault`，浏览器原生菜单（粘贴、复制选中）原样留着。实现里三处：没有借 `el-dropdown` 代管（全站只有两处用它，它的弹层靠触发元素定位，而右键没有触发元素；`position:fixed` 的包含块又会被带 `backdrop-filter` 的祖先改走），菜单挂在 `.layout` 里、`.main` 外，`z-index` 4100 —— 排在吸顶通知条（6）与 `el-popper`（4000）之上、`Ctrl+K` 面板遮罩（4200）之下；抬头取「第一个有字的格子」而不是 `innerText` 的第一行（原生 `tr` 的 `innerText` 是整行用制表符拼起来的，照原写法资源库那行会顶着一长串被省略号切得看不出个所以然）；破坏性那一项的红跟着按钮自带的 `el-button--danger` 类走，**不按「删除」这两个字猜** —— 词表一切成英文，按字面判的染色就整条失灵。换页收菜单单独写成一条 `watch(page, closeCtxMenu)`，没塞进翻页主回调 —— 那条回调被 `navlog` 逐页审计，混进 UI 收尾会撞上「翻页不许写日志/加载数据」那条闸门（本轮真撞过一次）。读数：文件页一行右键 → 菜单 `['播放','打开','删除','更多操作…']`，与那一行自己的按钮逐项对上、末尾多出的正是代管下拉那一项；点「更多操作…」→ 那一行的 7 项下拉真打开；右键第二行点「删除」→ 弹的是「确定删除 b.mp3？」，取消之后文件仍在磁盘上、`/api/files/delete` 被打到 0 次；分支 `d.txt` `['打开','删除']`（它没下拉，多出来那一项就不该有）、目录行 `['进入','打包','删除']`、资源库行 `['执行','打开目录']`；让路四条全部 `prevented=False`；贴边两个方向都钳住（落点 1426,886 → right 1432 ≤ 1440−8）。三处是第一轮量出来才弄对的：勾选格子的空白落点算「行」不算勾选框；「一滚就收」第一轮判红是尺子不对（沙箱只铺 5 个文件，`.content` 拉不出滚动条，自然没有 `scroll` 事件 —— 补 40 个假文件并先回读 `scrollHeight > clientHeight` 才真的测到）；「右键到上屏 85 ms」把等帧的开销算进去了，改成先记微任务（菜单节点就是这一拍挂上的，2.2 ms）再记帧（35.3 ms），判据落在微任务上。资源库走只读桩 —— 真扫会把 APP_DIR 那份 `library_cache.json` 改成沙箱内容，那是用户实例的文件。闸门 P27~P34 八条。

## 发布之后这一轮 · #78 人声分离：独立环境 + 两族 RoFormer 权重预载可选 + CPU/GPU 三档实测（接在 UI 批量之后）

链接给的参考建议读完之后按方案二落。口径三条：分离引擎装在 `tools/separator/venv` 这个**独立环境**里，不和主程序共用 python（主程序的 torch 是 `+cpu` 构建，在它里面装的分离包永远跑不了 GPU）；BS-RoFormer 与 Mel-Band RoFormer 两对权重都预载、界面上逐条选择；**这个环境与权重都不进便携包**。「支持 CPU 和 GPU 版本选择」= demucs 也装进同一个 venv，两个引擎都能用那块卡。

- `voice_tools.py`：`ROFORMER_MODELS`（:74）四条各带 ckpt / yaml 的 sha256，`id` 是给界面当词表键用的（`bs_1297` / `bs_1296` / `mel_1143` / `mel_inst_v2`，文案在 `i18n.js`，后端不拼中文）—— 官方 `models.json` 里另外那 84 个社区模型名字只是「识别名录」，没有可达的下载源，不给选项；`DEMUCS_MODELS`（:100）只列界面上有、且本机验过的三条（`htdemucs` / `htdemucs_ft` / `mdx_extra`，`htdemucs_6s` 这类注册表里确实有但没在这台跑通过的，给了就是让用户点下去报「模型下不下来」）；`SEP_ENGINE_PINS`（:275）钉死 `audio-separator==0.47.0` + `demucs==4.1.0`（小版本一直在动模型表与设备判定，装成「当时最新」会让这台验过的选项在下次装机上变成没验过的）；`ensure_separator_venv()`（:298）用 `sys.executable` 建 venv；`_fetch_weight()`（:344）断点续传 + 逐份核对校验值，对不上就丢掉这一份、不当「下完了」；`setup_separator(step)`（:405）一把锁，占用中回 `busy`。yaml 基址换到 audio-separator 自己的 `model-configs` release —— 官方主基址对这批 RoFormer 的 yaml 逐条 HEAD 过，全是 404。
- `separator_runner.py`（venv 侧唯一入口，`probe()` / `main()`）：CPU 这一档必须在 `import audio_separator` **之前**把 `torch.cuda.is_available` 换成 `False` —— 包没有 `device` / `force_cpu` 参数，设备只由它自己那一句判断决定；而本机实测 `CUDA_VISIBLE_DEVICES` 藏不住 GPU（仍 `True`），设 `-1` / `void` 直接把解释器打崩（rc 3221225477）。成品按 `output_dir` 认成绝对路径再回：包自己只回裸文件名。
- `server.py`：`POST /api/ai/vocal_separate`（:12467）替掉 `POST /api/ai/demucs`，引擎 / 权重 / 设备三项都取自设置、body 可逐项覆盖；新增 `POST /api/ai/separator_setup`（:12571）；`GET /api/ai/voice_status`（:12209）的 `separation` 回的是「**缺哪一层**」—— `venv` / `runner` / `import` / `weights` / 看不到 CUDA 五种在界面上是五句不同的话、处置也各不相同（前两种是装环境，中间两种是补文件，最后一种是换设备或装驱动），所以不打包成一个 bool（那个 `why()` 函数就是这件事的实现）；表外的权重名与设备名一律 400 并点名认哪些（`SEPARATION_DEVICES = ("auto","cpu","cuda")`，voice_tools.py:101）；选了 GPU 实跑在 CPU 上时自己说破，不让设置里那格变谎话。配置五个新键：`vocal_engine`（默认 `roformer`）/ `roformer_model`（默认 `bs_1297`）/ `demucs_model`（默认 `htdemucs`）/ `ai_device`（默认 `auto`）/ `vocal_native_fp16`（默认 `False`）。
- **活体跑抓到一条只写不读**：五格下拉绑在 settings 上、后端也存了，`loadConfig` 却从不回填 —— 配置存 `cuda`、页面开出来显示「自动」，而引擎其实一直照 `cuda` 跑，**只有显示在骗人**。补回填，并加 `settingsave_test.py` 的 I27/I28 通用闸门（`bound − 回填` 只许落在豁免表里）；豁免表写死这次之前就有的六格，那六格另开一次提交补（`7d3f1b9`，#82）：五格按各自 `DEFAULTS` 的口径回填（三个「默认开」用 `!== false`、两个「默认关」用 `!!`），`edge_tts_voice` 那一格的空值有含义（后端拿它按字幕目标语言挑预设音色，`EDGE_VOICE_PRESETS`），原先顶成晓晓等于存的和发的不是同一个音色 —— 第一版做成一条 `value=""` 的选项实测显示不出来（`el-select` 把空串当「没选」，回的是「请选择」），改成 `placeholder` 说效果、`clearable` 让人清得回去。I27 的豁免表清空，I28 从「这六个确实是老键」改成「这张表必须保持空」。
- 界面：语音页新增「人声分离（RoFormer / Demucs）」卡片 —— 三个下拉 + FP16 开关 + 一句实测状态读数 + 搭建 / 下载权重 / 刷新三个按钮（转圈跟的是服务端 `setup_running`）；文件页那一项菜单接 `aiVocalSeparate`。
- 实测读数（自起沙箱实例，不碰 8765）：venv 里 torch `2.14.1+cu130`、RTX 4060 Laptop 8.0 GiB、权重 4/4；runner `--device cpu` 时包自己打「No hardware acceleration could be configured, running in CPU mode」且回 `actual_device=cpu`，同一份素材 `--device cuda` 回 `actual_device=cuda`；走端点的两轮日志分别是「RoFormer 完成: 实际设备 cpu」「Demucs 完成: 实际设备 cuda，2 条轨」，成品落 `separated/` 与 `demucs/htdemucs/<曲名>/`，路径逐条进运行日志。新增 `tests/separator_test.py` 44 项（A 表 / B CPU 判定顺序 / C 缺哪一层 / D 设备诚实 / E 下载卫生 / F 界面接线 / G 打包）；`navlog` 的 `EXPECT_LOADS` 加 `voice`。全批 62 套 bad=0。

## 发布之后这一轮 · #87 首屏框架六件落到 `static/vendor/`，断掉运行期 jsdelivr 依赖（同一轮的最后一次提交）

起因是「没关机，第二天用外置浏览器打开很卡，内置浏览器不卡」。三臂实测（沙箱自起实例 + Playwright 的热缓存 / 冷缓存 / CDN 拉不动三种处境，同一份页面同一个服务端，只变浏览器这一侧）：热缓存 DOMContentLoaded **214 ms**（6 件全命中缓存、耗时 0）；冷缓存 **2282 ms**；把 jsdelivr 改成「连得上但拉不动」之后，`index.html` 里 6 件阻塞 `script`/`link` 各等 28 秒、**而且是串行的**，DOMContentLoaded **168084 ms**，`window.Vue` 不存在、页面里 1332 处裸花括号、一次 `/api` 都没发 —— 这不是原先以为的渲染卡，是模板根本没挂载。

- 渲染层用同一把探针排掉了：DOM 582 个节点、longtask 0 个、敲键到下一帧 p50 32 ms，#56/#57 那一层不用重开。服务端也没有「跑了一天积累出来的东西」：进程当天才起、只有 4 条 ESTABLISHED、`/api/events` 是 `async def` 不占工作线程、`logs.value` 有 `slice(-200)` 上限。所以「第二天」这个变量落在浏览器一侧的缓存冷热与链路通不通上，而内置浏览器不卡正是上表第一臂（vendor 已在 profile 里缓存）。
- 改的：`vue@3.5.12`、`element-plus@2.8.8` 的 css + `index.full.min.js` + zh-cn + en.min 两枚 locale、`lucide@0.468.0` 六件按原版本号落到 `static/vendor/`（合计 1.8 MB），`<head>` 那枚样式与尾部 4 枚 `script` 改成本地路径，**顺序不动**（EP 的 UMD 要 `window.Vue` 先就位）。文件名换成带包名的写法，免得跟本地下载产物混。六件的 sha256 用两条网络路径各下一次比对一致；element-plus 那份 css 里 5 处 `url()` 全是内联 data URI 与 SVG 片段，没有外部字体要补。进包靠 `pack_release.py` 里已有的 `APP_DIRS "static"`。
- 验证：CDN 拉不动那一臂复跑，**0.5 秒挂载、DOMContentLoaded 402 ms、CDN 请求 0 件**、`has_vue=True`、裸花括号 0。`pagemount_test` 补三条闸门并跑负控：**P38** `index.html` 不得有外部 `script`/`link` 根引用、**P39** 六件真在且 sha256 对得上（半截文件或空目录都算红）、**P40** 引的就是这六件本地路径；把 HEAD 那版喂进同一套，三条全红且列出残留的 jsdelivr URL，改后整套 40/40 绿。`pack_release.check_present` 的点名目录补上 `static/vendor` —— vendor 单独被排除表吞掉时 `static` 仍非空，旧闸门会绿着放出一个解压后白屏的包，这是本次改动新引入的失败模式，得点名。登录不受影响（`server.py:11313` 那条放行规则本来就允许 `/static/` 前缀）。`.gitattributes` 里给 `static/vendor/**` 加了 `-text`：这台机器 `core.autocrlf=true`，checkout 会把 LF 写成 CRLF，sha256 钉的那两条闸门在工作树里绿、在别人新克隆里红 —— 所以拿一份 `git worktree add` 的干净检出复跑过一遍才敢说它对第三方成立。
- 连带两处，都是 `i18n_test` 从 `index.html` 里 grep 字面当锚：C4 原先锚 `dist/locale/en.min.js`，换成 vendor 后的文件名；C8 没引 CDN，但它的模板区切片锚的是 `/vue@3`，那个字面没了之后 `find` 返 `-1`、切片退化成整份文件，把解释这段代码的那句注释里的字面量也数了进去（全文 `v-for="t in "` 8 处、模板区 7 处）—— **红得没错，但错的原因不好猜**。边界改成锚「模板之后的第一枚 `<script`」，那正是原先 Vue 那几件的位置，且不依赖任何文件名。
- 两层实测到了但没动，下一步单独定口径：`/api/status` 每次 1.0–1.3 秒（它会现跑 `ffmpeg --version`、导入 `yt_dlp`、递归扫 Whisper 目录）；`/` 的 `cache-control` 是 `no-store`，817 KB HTML 每次全量重传重解析；一个空闲标签页 20 秒发 25 个请求，其中 15 个是 `/api/clipboard` 的 2 秒轮询。

## 这一轮的收尾：推送、重启与这笔文档同步

- 37 次提交（多语言第二批 17 页 + 1e30481 + 7beb444 + f6c43d3 + #65/#63/#66 + bc2d9f6 + UI 参照批量八项 + #78/#82 + #87）在 `main` 上一次推到 `origin/main`：`3f9cafc..ea16c82`，一次 fast-forward，推前把整段 diff 看过 —— 38 个文件、12,259 行新增、无二进制、无状态文件（`config.json` / `history.json` / `app.log` / `cookies/` 一个都没进），唯一的凭据形状是 `tests/cookiecloud_test.py` 里那个 `http://user:pass@` 占位。
- **标签 `v1.4.0` 仍留在 `7ac0ff6`，便携包与 Release 资产都没动** —— 也就是说已发布的那只包落后仓库自 `3f9cafc` 起的全部内容。这一笔仍然只是文档：`appVersion` 仍是 `v1.4.0 · Element Plus`（`static/index.html:6455`），不重打包（按惯例，文档在 zip 那一刻才快照）。
- 平时在用的那台实例已重启到 `ea16c82`（先确认队列 `running=0 / pending=0` 才停）：首页 HTML 与仓库那份逐字节相同（817,010 B、`jsdelivr_hits=0`），六件本地路径全 200，`/api/status` 回 ffmpeg `9.0.1-essentials_build`。
- 两份公开文档（`docs/详细功能介绍.md` 与 `docs/detailed-features.en.md`）与 `README.md` / `README.en.md` 里「界面只有中文」那类过期说法一并改了；`CHANGELOG.en.md` 新增一节 follow-ups，把这一轮的条目按英文摘要的口径写一遍。**这一笔没有重跑任何活体或自检**：上面每一节里的读数都是各自那一轮跑完时记下的，本文件只搬运、不重新主张。

## #52 · 标签 `v1.4.0` 与已发布字节不一致：口径是标签不动，把差异算清楚写下来

前面好几节都留了一句「标签 `v1.4.0` 仍指 `7ac0ff6`，包与 Release 资产没动」。这句话一直只说到「标签落后」，没说清**落后的是哪一棵树**——已发布那只包压根不是从 `7ac0ff6` 压出来的。这一笔把两边对齐到可比的程度，然后按定下的口径**保持标签不动**：只补文档，移动标签、重打包、换 Release 资产一件都不做。

- **包对应的是 `caeb4f6` 那棵树**，这条是本轮新量的，不是从旧记录里搬的。拿 `dist/MediaDownloader-1.4.0-portable.zip` 里的两份应用文件解出来、把 CRLF 折回 LF，再按 git 的 blob 算法算 sha1：
  - `static/index.html` → 773,906 B、`28b090bc4ac12e1a195c8cac938807871cbbcc57`，与 `caeb4f6:static/index.html` 逐字符相同；
  - `CHANGELOG.md` → 476,725 B、`15da28dc587b3c9b022321a2be5489fa05a590c5`，与 `caeb4f6:CHANGELOG.md` 相同。
  同一位置在 `7ac0ff6` 那一份分别是 773,890 B / `fd5f19626b3532447919016eaf45f56250577e16` 与 466,999 B，全都不是上面这两个数。**折行尾这一步是必须的**：包内 `index.html` 条目 787,201 B、里面 13,295 枚 CR，773,906 + 13,295 正好等于 787,201 —— 打包是在这台 Windows 上做的，检出时 `core.autocrlf=true` 已经把 LF 写成 CRLF。这跟 #87 那节「autocrlf 会毁掉 sha256 钉」是同一件事的另一面。
- **两棵树之间只差两个提交**（`7ac0ff6..caeb4f6`）：`c7226b1` 只换 `docs/screenshots/` 六张 PNG；`caeb4f6` 动的是 `static/index.html` 4 行（音乐结果表「艺人」「专辑」两列 `width` → `min-width`，把富余摊开）、`tests/matchgate_test.py` 一处（2 加 1 删，G9 那条假绿改钉 `:title`）、本文件一节和 `music-search.png` 一张。所以**这处不一致不只在文档**：按 `v1.4.0` 标签 checkout 复现，拿到的是表格宽度改之前的界面，与用户下载到的那只包差 4 行真实样式代码。
- **口径与理由**（人定的，这里记下来免得下次又当成待修）：`v1.4.0` 这个号已经发出去、被人下载过了，这时候把标签往前挪或换掉资产，等于让同一个号对应又一种字节，事后更难对齐；所以宁可让标签停在 `7ac0ff6`，把「包 = `caeb4f6`」这条事实写进文档。
- **要拿回哪种东西，走哪条路**：与已发布字节一致的源码树是 `git checkout caeb4f6`（要归档就 `git archive`）；用户实际下载到的那个文件是 Release 上那只 `MediaDownloader-1.4.0-portable.zip`，229,823,103 B，在 `dist/` 里对同名 `.zip.sha256` 跑 `sha256sum -c` 即可核（sidecar 现在写的是 `4ea6a8ec…`，本轮读的就是这一行）。**校验值仍然不写进这份随包文件**——沿用上面「发布物」那节定的口径，一个包装不下自己的校验值。
- 这一笔只动 `CHANGELOG.md` 与 `CHANGELOG.en.md` 两份文档：`appVersion` 没动、包没重压、Release 没碰、标签没挪，也没有跑任何活体。上面那条 blob 比对是本轮唯一的新测量，读的是 `dist/` 里那只包的 zip 条目本身，不是 `dist/MediaDownloader-1.4.0-portable/` 那棵已解压的目录树。

## 发布之后这一轮 · 分离引擎纳入上游检测与「更新」、设置页网络卡分组；标签 `v1.4.0` 前移并重出包

起因是两张截图对不上：GitHub 上 `python-audio-separator` **v0.47.1** 已经发布 13 小时，本机独立 venv 仍是 **0.47.0**，而「组件与依赖」那一行只有「获取 / 补齐」—— 没有「更新」，顶部通知条也不报。根因不是按钮漏挂：两个引擎装在 `tools/separator/venv`，原有上游检测只遍历主环境的 `pkg_update.PIP_PACKAGES`，这个 venv 从没进过名单。

- **后端**：`latest_versions_cached()` 的查询名单加上 `voice_tools.SEP_ENGINE_PKGS`；新增 `separator_engine_versions()` 只读 venv 的 `importlib.metadata`（不 import torch，结果缓存 120 秒），以及 `_sep_engine_rows / _sep_engine_state / _sep_engine_available`。`/api/components` 多回一份 `sep_engine`（两条包各自的 active / latest / updatable），后台检测 worker 把 `available += _sep_engine_available(lv)` 并进同一份状态；检测结果里只报一条 `sep:engines`（两个包是同一组一起升，列两行会变成两条同义通知）。`_comp_update_one`、一键更新的 labels 与白名单、`api_separator_setup` 的 step 白名单都认这个键；`setup_separator()` 在抢 `_setup_lock` 之前把 `step == "engines"` 转给 `update_separator_engines()`，避免自锁。
- **更新路径**：`update_separator_engines()` 在同一个锁里跑 `pip install -U --disable-pip-version-check --no-input [-i 镜像] audio-separator demucs`，结束后强制刷新版本缓存与 `separation_probe`，成功与否都回读真实版本；**`SEP_ENGINE_PINS`（新建环境钉 0.47.0 / 4.1.0）没有改**，只有用户点「更新」才会脱离钉死版本。运行日志分开发 `srv.ai.update_ready` / `srv.ai.update_failed`，端点回话也不再对「更新」说「搭建中」。
- **界面**：分离行按包显示 `RoFormer · audio-separator 0.47.0 · 最新 0.47.1（可更新）` 与 `Demucs · demucs 4.1.0`，有新版时出现「更新」按钮；`updateSeparatorEngines()` 先静默保存镜像设置，再走 `engines` 步骤，按服务端 `setup_running` 的真实锁收尾，回读版本后刷新组件表与检测状态（15 分钟上限）。`compTargets` 把 `sep:engines` 算进「一键更新」，顶部通知条与侧栏橙点的计数自然带上它。
- **活体读数**（沙箱自起实例，`MEDIADOWNLOADER_STATE_DIR` + `bind(0)` 端口，不碰 8765）：真实查上游回 `audio-separator 0.47.1`（清华源）、`demucs 4.1.0`；`/api/components/update-check` 的 `available` 只有一条 `sep:engines`（0.47.0 → 0.47.1）；`/api/components` 的 `sep_engine.items` 是 0.47.0 / 4.1.0，只有前者 `updatable`；组件页那行渲染出的文字逐字为上面那两行，顶部条为「有 1 个组件出了新版本：人声分离引擎」，控制台 0 错误。**这台机器的 venv 没有真升**——更新路径的自检是代码级与桩级（H1–H10），没有拿正在用的 0.47.0 环境跑真实 `pip -U`；要升由界面那颗按钮触发。
- **设置页网络卡分组**：18 个字段按「代理与并发 / 限速 / 队列 / 下载器 / 镜像」分成五组，组标题 `.net-sec` 通栏、虚线分隔；长字段 `net-span2` 跨两列，队列一项通栏并把每条命名队列铺成 `auto-fill minmax(280px,1fr)`。1600 / 1200 / 860 三档实测列数 4 / 2 / 1，`hOver=0`、`docOver=0`；设置页内容仍比一屏长（滚动 1639 / 842），这次只收拾网络卡，不承诺整页免滚。
- **自检**：`tests/separator_test.py` 57 条（新增 H1–H10）、`i18n_test` 509、`components_test`、`runwindow_test`、`pagemount_test` 40、`settingsave_test` 113 全绿；全批 **65 套 rc=0**（185.8 秒）。`runwindow` 的 G11 锚点跟着 `net-span2` 更新了一次。
- **标签与包**：按 2026-10-20 的明确要求（「修改后再推送动标签打包」），`v1.4.0` 轻量标签从 `7ac0ff6` 前移到本笔提交并 force-push，`pack_release.py --skip-runtime` 重出便携包。这**推翻了上面 #52 那节「标签不动」的处置**——那一条成立的前提是当时没有人要求动标签；现在要求明确，事后以本节为准。公开 Release 的资产替换仍等下一次单独点头。

## 发布之后这一轮（续）· 队列名跟界面语言、组件页只留一个上游入口、分离引擎「更新」常驻、关服不再打 CancelledError

这一笔在上一节出包之后，用户拿两张截图和一段控制台日志继续收口；`appVersion` 仍是 `v1.4.0`，标签、包与 Release 资产都没动。

- **队列名不再露后端标识**：设置页队列定时窗那几行原来直接把 `default / night / subscribe / sniff / music` 印出来。现在由 `queueLabel()` 走 `QUEUE_NAME_KEYS` 词表：中文显示 默认 / 夜间 / 订阅 / 嗅探 / 音乐，英文显示 Default / Night / Subscribe / Sniff / Music；用户自建的队列名不在词表里，照原样显示，`title` 仍保留原始标识。沙箱切到 EN 后五个内置名全是英文，自定义名不动，控制台 0 错误。
- **组件页只留一个上游入口**：顶部「立即检测」本来就会强制刷新上游版本，底部「查询上游最新版本」只是再发一次 `GET /api/components?latest=1`，功能重复。删掉底部那枚，把填「最新」列并进检测完成后的 `loadComponents('1')`（读服务端缓存，不重复联网）；`latestBusy` 一并移除。沙箱实测点一次「立即检测」后 16 行的「最新」列填出，底栏只剩「一键更新 / 重新检测 / 保存镜像设置」三枚。
- **分离引擎的「更新」常驻**：原先按钮随 `sepUpdatable` 显隐，引擎升到 0.47.1 / 4.1.0（都已是最新）后按钮整个消失，用户找不到重装 / 强制升级的入口。现在与其它组件行一致，按钮始终在场；有新版时旁边仍显示「最新 x.y.z（可更新）」。沙箱读数：`sep_engine.items` 两包 active 0.47.1 / 4.1.0、`updatable=false`，那一行的按钮是 `["更新", "获取 / 补齐"]`，控制台 0 错误。
- **关服时不再打 CancelledError**：用户贴的 `ERROR: Cancel 1 running task(s), timeout graceful shutdown exceeded` 与随后的 `Exception in ASGI application ... CancelledError`，触发条件是浏览器留着 `/api/events` 这条 SSE 长连接时按 Ctrl+C —— `timeout_graceful_shutdown=5` 到期后 uvicorn 取消还挂着的流任务，这段堆栈是**关闭阶段的噪声，不是运行期崩溃**，`finally` 里的 BT 守护收尾照常执行。现在 `main()` 自己持有 `uvicorn.Server`，SSE 生成器每轮看一次 `should_exit`，收到退出信号就主动收流；AB 实测（SSE 挂着、同一套配置）：改前 5.14 s 并打出完整 Cancel + CancelledError，改后 0.13 s、stderr 0 行。端到端探针（真 `python server.py`、沙箱端口、SSE 挂着后发 CTRL_BREAK）同样 0.17 s 收流、无 Cancel 行；Ctrl+C 的退出路径与原来一致。
- **自检**：`separator_test` 57（H8 改钉「按钮不按有无更新切换显隐」）、`platform_test` 45（新增 E1b 钉 SSE 看 `should_exit`）、`startup_test`（B2/B4 跟着 `_UVICORN_SERVER.run()` 改锚点）、`sse_test`、`i18n_test` 509、`pagemount_test` 40、`settingsave_test` 113、`runwindow_test` 全绿；全批 **65 套 rc=0**（189.4 秒）。

## 发布之后这一轮（再续）· 组件页整页英文化、行内「更新」统一成默认样式

这一笔仍停在 `appVersion = v1.4.0`；标签、包与 Release 资产都没动。用户拿两张截图指出组件页「还有一些地方没有英文化，按钮风格也不一致」。

- **这一页的中文有四个来源，不是一个词表能盖住的**：行名来自后端 `_component_rows()` 的 `cn`（18 条）、悬停说明来自 `label`、POT 那一行的整段话来自 `_pot_component_note()`、状态来自 `active` 的 `未安装 / 未找到`；「一键更新」的名单与进度也直接印后端的 `cn / label`。翻译只改词表的话，这五处一处都不会变。
- **名字与说明走字面量映射**：`static/index.html` 新增 `COMP_NAME_KEYS`（18 个包 / 工具 + `sep:engines`）与 `COMP_DESC_KEYS`（18 条），值是 `components.name.*` / `components.desc.*`；`compName(row)` / `compDesc(row)` 查表，查不到才回落到后端原话（不在表里的行不会变空白）。没有用 `'components.name.' + key` 这种拼键，因为 `i18n_test` 的 B2 只允许 `nav.` / `navGroup.` 两族动态前缀；写整键也让 B10 的死键检查把 36 个新键都算作「在用」。中文界面的值与原 `cn / label` 同文，显示一字未变。
- **状态词单独走词表**：`compActive()` 把 `未安装` / `未找到` 换成 `settings.notInstalled` / `settings.compNotFound`，其余版本号原样显示。
- **POT 的整段话不把判断逻辑复制到前端**：后端新增 `_pot_component_note_state()`（紧挨 `_pot_component_note`），输出语言无关的 `note_state`（`install / gate_off / no_server / ready`）与 `note_kv`（`dir / url / detail`）；前端 `COMP_NOTE_KEYS` + `compNote()` 按当前界面语言取 `settings.compPotNote*` 四把键。后端那份中文 `note` 照旧保留（日志与旧调用方还在读），只是模板不再直出它。
- **一键更新的三处一起改**：顶部名单、进度里的当前项、结束摘要都走 `compName()`。进度原来只有一个中文 `current`，现在后端多带一个 `current_key`（`api_components_update_all` 启动时是 `keys[0]`，`_comp_update_all` 每换一项就写，`finally` 清掉），前端先用它查词表，查不到才用 `current` —— 英文界面里进度条不会忽然蹦出中文包名。
- **一页只留一个主按钮**：分离引擎那行原来用 `type="primary" plain`，在 19 行里独一份；现在与所有行一致，是默认灰色 `el-button--small`。底部「全部更新」保留 `primary plain` 作为唯一 CTA。
- **自检**：`components_test` 新增 C12（每个组件行都有名字键）、C13（悬停说明覆盖到每一行，`sep:engines` 无独立说明除外）、C14（模板走 `compName / compNote / compActive`，不再直出 `cn / note / 未安装`），109 项全绿；`potcomponent_test` 新增 B8/B9 钉四种 `note_state` 与 `no_server` 的 kv，E4 改钉模板按状态取词，30 项 0 失败；`separator_test` H8 改钉「按钮不带 `type="primary plain"`」，57 项 0 失败。`i18n_test` 509、`pagemount_test` 40、`indexsnap_test` 全绿；全批 **65 套 rc=0**（190.3 秒）。
- **沙箱读数**（独立 `STATE_DIR` + `bind(0)` 端口，不是 8765）：EN 界面 19 行 `CJK_ROWS []`、`CJK_TITLES []`、卡片内 `CARD_CJK []`；18 枚行内 Update 的计算样式只有一种（`el-button el-button--small`、白底 `rgb(255,255,255)`、灰边 `rgb(220,223,230)`、66×24），「Update all」仍是唯一的 `el-button--primary`；卡片 884 px、`SCROLL_H 882` 不出滚动条；控制台 0 错误。截图 `tmp/ui_comp_i18n_en.png`。

## 发布之后这一轮（再续二）· 外观页横排成一条、主题色块不再被挤没

仍在 `appVersion = v1.4.0`；标签、包与 Release 资产都没动。用户先要「红框改成横排一行、拉框在界面外观下方」，看到成果后又指出横排里主题色的五个小色块不见了。

- **布局**：`界面外观` 标题留在框外，标题下是一条通栏卡片（`.appearance-wrap` 横跨 `.settings-grid`）；`主题色` + 五枚 chip 与右端的 `深色模式` 开关同一行，`改动怎么存 · 恢复默认` 整行宽排在下方。第一版把这条塞进 1/3 列时，五等分的 chip 在 1600 / 1400 下只剩 40.7 / 27.3 px，12 px 的 `.theme-dot--inline` 被 flex 压到 0 —— 截图里就是光秃秃的文字。
- **色块**：`theme-grid` 从五等分改为按内容取宽（chip 79 px = 12 px 圆点 + 6 px 间距 + 三字名称），并给 `.theme-dot--inline` 加 `flex: 0 0 auto`，任何容器都压不没它；五个圆点的实色读数为 `#1d55ee / #c2540a / #c92f6f / #2f7d4f / #a85c3c`。
- **一处英文空格**：`settings.savePendHead` 的英文值原来以冒号收尾且无空格，暗色实测拼成 `1 setting(s) waiting to be saveddark_mode`，补了尾随空格。
- **沙箱读数**（独立 `STATE_DIR` + `bind(0)` 端口，不是 8765）：2000 / 1600 / 1200 三档 chip 均 79 px、圆点均 12×12、`gridRows = 1`、`docScrollW == docClientW`，控制台 0 错误；EN 1600 五枚 chip 65–155 px、圆点仍 12 px，EN + 暗色也正常。截图 `tmp/ui_appearance_dots_1600.png`、`tmp/ui_appearance_en_dark_1600.png`。
- **自检**：全批 **65 套 rc=0**（190.9 秒）。

## v1.3.2 · 2026-10-13（已出包）

对着 [joeseesun/qiaomu-download](https://github.com/joeseesun/qiaomu-download) 那份平台清单盘了一遍 ours，盘出两条真的缺口，本轮做掉；第三条（B1 TikTok 归错档）是我看错了，代码一个字没改，判正的读数写在下面。B4（公开优先的 Cookie 策略）与 B5（Spotify 单曲入口 + 匹配置信度）按要求先排着，和 issue #206 那张「有但没做」的清单一起过。**已出包**：`appVersion` 升到 `v1.3.2 · Element Plus`（版本真源只有界面那一处），两份 README 的徽章与包名同处改口，产物见下方「发布物」。

**① 站点识别表补齐（B2）**：`PROXY_NEEDED_PLATFORMS` 里早就写着 facebook / twitch / reddit，可 `PLATFORM_RULES` 根本没有这三个键 —— `detect_platform()` 对它们的 URL 永远回 `default`，集合里那三项等于死代码：既判不出「要走代理」，用户在「网络策略」里也看不见这几行，没法单独指定走不走。vimeo / SoundCloud / LinkedIn / 微博 / AcFun 则是整站落在 `inherit`（跟随系统），代理节点一抖就跟着抖，而它们本该有明确归属。现在八个站点进了识别表、有了中文名、有了默认归属。

**② 成品回读实际档位（B3）**：任务「成功」的含义一直是「进程退出码 0 + 文件能播」，这两条同时成立时，**下到的是不是用户点的那一档没人管**。10-13 那次 YouTube 4K 静默降成 1080p 正是从这道缝里漏过去的 —— 卡片写着成功，实际下到的是清单末尾那条 1080p 渐进流。现在下载完会用 ffprobe 回读成片的真实高度，和所选档位对一下，对不上就在卡片上写一句「是谁的问题」，同时进运行日志和 `history.json`。

### 后端

- **`PLATFORM_RULES` / `PLATFORM_LABELS` 各加 8 项**（server.py:3402 / 3425）：facebook（含 `fb.watch`、`fb.com`）、twitch、reddit（含 `redd.it`）、vimeo、soundcloud、linkedin、weibo（含 `weibo.cn`）、acfun。表的顺序就是优先级，新条目一律追加在末尾，`douyin` / `bilibili` 这些原来排在前面的不受影响（分享链接里顺带出现别的站点名时，仍认前面那个）。
- **归属补齐**：`PROXY_NEEDED_PLATFORMS` += vimeo / soundcloud / linkedin（server.py:3471），`PROXY_DIRECT_PLATFORMS` += 微博 / AcFun（3478）。facebook / twitch / reddit 三项本来就在「要代理」集合里，是键不存在所以从来没生效过，这次不用新写它们。
- **Cookie 那一层一个字没改**，这是核对过的：`_cookie_source()`（server.py:5101）在该平台没单独配置时回落到全局 `cookie_source`，所以表里多了键不会凭空让 vimeo「不吃票」；`/api/platforms/cookies` 也仍然只跳过 `default` 一行。
- **档位高度只剩一个来源**：新增模块级 `VIDEO_QUALITY_HEIGHTS` 与 `quality_height_cap()`（server.py:4608 / 4613），`_resolve_format()` 里那份手抄的 `height_map` 删掉，解析页体积估算的 `_VIDEO_TIERS` 改成从这张表派生（它原本那行注释就写着「上限口径抄自 _resolve_format」—— 抄的那份就是漂移的源头）。`best` 由原来的 `None` 变成 `0`，两处下游都是 `if max_h:` / `max_h or 1080` 的写法，falsy 行为一字不变，A7 / A8 两条断言钉住这件事。
- **`tier_readback()`（server.py:18665）说四种话**：清单里有更高档却下低了 → 「差在选择/合并这一段，不是上游不给」；清单最高就到实得这一档 → 「上游清单最高就到这儿，这一档它给不了」；清单比实得高但仍低于所选 → 两句都说；实得明显高于所选 → 「高度上限没拦住（自定义参数或站点只给这一条流的时候会这样）」。**选 `best`、音频任务、读不到高度、以及差在一个档位容差内（编码按 16 对齐会多出 2176 / 1088 这种，天天误报就没人看了）一律回空串**，界面就不出现这一行。
- **清单上限怎么交到收尾**：`engine.download` 把「这次解析里最高的视频轨」记进 `_listed_max[task_id]`（server.py:5385 声明、5850 写入，多轮重试取最大值，补试 `all` 那一份才是清单最全的），队列收尾用 `pop_listed_max()` 取走即清。**不复用 `_info_cache` 是因为那一份 180 秒就过期，而下载本身能跑十几分钟** —— 收尾再读多半已经没了，那一档就永远判不出。
- **写入点只有一个**：`_run()` 的收尾里，紧跟在 `verify_media_file()` 之后、且只在文件判为可用时做（server.py:9064 起）；`task.is_live` 跳过，因为直播那侧格式恒为 `best`，画质档根本不参与，判了是怪错对象。回读自身抛异常只记一句 warning，不改任务结论。新增的 `DownloadTask.verify_note` 走 `asdict`，接口自动带出，SSE 不用改（完成态走整份任务字典）。

### 界面

- **卡片多一行橙色的「画质核对 · …」**：下载队列与磁力/种子两张卡片模板都加（`static/index.html:1926` 与 `2048` 附近），没偏差时整块不出现。运行日志同一句以 warning 级别落盘，事后能从日志追。
- **历史页不给表格加一列**：那句核对挂在状态标的悬浮提示上（`row.verify_note`），数据本身已经写进 `history.json`，导出 CSV 的列没动。
- **「网络策略」表从 18 行变 26 行**：新认出的 8 个站点自动出现（前端本来就是 `v-for="row in netInfo.platforms"` 全数据驱动，一行代码没改），每行都能单独指定走 / 不走代理。**Cookie 设置列同步从 10 行变 18 行**。

### 一处收回的错判（B1）

上一轮我说「TikTok 被并进抖音、归到直连档，是个真 bug」—— **量下来是我看错了**：`proxy_platform_key()` 早就用 `PROXY_TIKTOK_HINT` 把 TikTok 从 `douyin` 那个 cookie 键里拆出来单独判代理，server.py:3494 那行注释写的就是这个合并是故意的（同属字节，Cookie 通用，归属相反）。本轮没有为 B1 改任何代码，只在 `siteproxy_test.py` C 段留了三条断言钉住现有行为（`tiktok → proxy`、`douyin → direct`、键名仍是拆出来的 `tiktok`），免得下轮顺手把它「并回去」。

> 说明一：**离线自检**新增两套 —— `tests/siteproxy_test.py` **81 项全绿**（A 识别 24 / B 归属 5 / C 判定 25 / D 手动指定 5 / E 界面行 16 / F Cookie 归属 3 / G 顺序误认 4 / H 接线静态 8，最后一项直接断言八个键在 `PLATFORM_RULES` 段落里出现，不只是在集合里出现过），`tests/readback_test.py` **41 项全绿**（A 口径单一来源 8 / B 四种话术 12 / C 清单交接 9 / D 真·端到端 5 / E 入库上屏 7）。B 段是桩 `_ffprobe_info` 只验措辞判定，**D 段用随包 ffmpeg 现场造一条 1280×720 的片子让回读自己 ffprobe**，桩过了真机读不出正是我们要防的那种假绿，所以这台机器没有 ffmpeg 时那几条就该红而不是跳过。回归面本轮重跑并全绿的：`potdaemon_test` 47（G 段高度上限正是被 `_VIDEO_TIERS` 派生改动碰到的）、`potcomponent_test` 28、`presetcodec_test` 33、`qualityspec_test` ALL PASS、`routebody_test` 14、`cookielogin_test`（它的断言是 `len(platforms) == len(PLATFORM_LABELS) - 1`，跟着表一起涨到 18 仍绿）、`douyinrisk_test`、`components_test` `FAILED: none`；`python -m py_compile server.py` 通过。
>
> 说明二：**改完按要求重启了 8765 并取线上读数**（PID 从 6236 → 55996 → 36464，两次重启前都确认过 `running=0 / pending=0`，没打断任何在跑的任务）：
> - **B2**：`GET /api/net/info` 回 **26 行**，新站判定逐个读回 —— facebook / fb.watch / twitch / reddit / vimeo / soundcloud / linkedin → `proxy` + `<本机代理地址>`，微博 / AcFun → `direct`，认不出的站仍 `inherit`；`GET /api/platforms/cookies` 回 **18 行**、`login_issue_count=0`。
> - **B3 未达标那一支**：真把 `https://x.com/vista8/status/2100589…` 按 **所选 4K** 下一条（39 秒、成品 5,101,040 字节），任务 `finished`，`res_label=1080p`，`verify_note="所选 4K，成品 1080p：上游清单最高就到这儿，这一档它给不了"`；直接对成品跑 ffprobe 得 `h264, 1728, 1080` —— **回读说的是真实尺寸，不是进度回调里那个标签**；`app.log` 同刻有 `成品回读：…` 那行 warning，`history.json` 首行多出 `verify_note` 键。
> - **B3 达标那一支**（防「天天报警」）：`Sintel 4K` 那条 YouTube 按 **所选 360p** 下，成品 28,789,336 字节，ffprobe 实测 `640, 360`，`verify_note` 是空串、界面上不出现这一行。
> - 这两条测试下载的成片与历史行都留在 `Downloads/` 和 `history.json` 里，是本轮留下的实测样品，不是用户自己的任务。

### 发布物

- **已发包**：`dist/MediaDownloader-1.3.2-portable.zip`（218.8 MB，目录展开 564.1 MB：runtime 322.4 MB + tools 234.5 MB），校验值记在同名 `.zip.sha256` 里（`sha256sum -c` 或 `Get-FileHash` 都能核）。打包用 `--skip-runtime` 复用 1.3.1 那一份 runtime，因此这一轮进包的只有源码与文档 —— 出包后逐个 `cmp` 过 `server.py` / `static/index.html` / 两份 README / 本文件，五者与工作区逐字节一致；包内自检 `check_module_imports`（14 个顶层模块）、`selfupdate_probe`（包内 pip 装-导一轮）、`smoke_test`（真起服务打 `/api/music/status` 与 `/api/components`，组件命中随包清单 12 项）全过，私密文件扫描 `leaks=[]`（`cookies/` 里只有那句「放 cookies.txt 在这里.txt」占位）。**GitHub Release 没有新条目** —— `web_app/` 是个 git 仓库（远端 `github.com/QingYan1012/media-downloader-web`，分支 `main`；上一句写的「本机这个目录不是 git 仓库」是当时核对错了，仓库一直在，只是从没提交过），这一轮的改动一个字没提交、更没推，往仓库推包是要人点头的那一步。
- 上一包 `dist/MediaDownloader-1.3.1-portable.zip`（218.8 MB，sha256 `ec1510c3…f12097`）**不含本轮这两处改动**，留在 `dist/` 只做回退用。



三条彼此独立的线。**① 前端粘贴**：七个单行输入框右键「粘贴」与 `Ctrl+V` 从此和点「粘贴」按钮走同一套清洗 —— 粘一整段分享文案只会留下链接，不再把「+ 复制此链接打开…」连同尾部标点一起塞进查询串。**② 后端的非 Windows 崩溃点**：核心是一条被忽略了很久的区分 ——「文件在」不等于「这台机器跑得动它」；Docker 的 `COPY` 会把 Windows 的 `tools\*.exe` 一起带进 Linux 镜像，文件存在、`is_file()` 为真，执行却报 `Exec format error`，而调用处普遍用 `try` 把异常吞成「未安装」，于是「组件与依赖」会把一个跑不动的文件报成已装好，任务下到一半才炸。现在统一由一个可执行判定把关，PATH 的分隔符也改用 `os.pathsep`（写死 `;` 在 Linux 上会把整条 PATH 当成一项）。**③ 容器化打磨**：新加一条不打扰任何人的存活探针、给 uvicorn 补上优雅退出超时（SSE 进度流一直挂着时，`docker stop` 原本只能等到超时被 SIGKILL），状态文件整体收进 `MEDIADOWNLOADER_STATE_DIR` 一个目录，Dockerfile / docker-compose / `.dockerignore` 三件套重写。**这一轮只动代码、离线自检与文档：`appVersion` 仍是 `v1.3.0`，便携包与 Release 都没碰**（这半句到本次出包时作废 —— `appVersion` 已升到 `v1.3.1`，包按下方「发布物」打出；8765 那个实例在第一轮结束时还没重启，第二轮按要求重启并验过，见下面「第二轮」那一节的线上读数）。

> 说明一：判定口径与接线全部由**离线自检**覆盖 —— 今天（2026-10-13）本机跑完 `tests/platform_test.py` **44 项全绿**、`tests/paste_test.py` **23 项全绿**，回归面 `torrent_test.py` 206 项、`bt_boost_test.py` 85 项、`components_test.py` 全部 `FAILED: none`。几处值得单独记的断言与反向验证：
> - **A 段：`is_native_binary()` 的四档判定**。伪 Linux 下 ELF（`\x7fELF`）与 shebang（`#!`）脚本判可执行，PE（`MZ`）**判假 —— 即使把这个 `.exe` 改名成没有后缀**（镜像里靠 `COPY` 混进来的正是这种），垃圾字节 / 目录 / 不存在 / 零长度文件一律判假；反向是 Windows 口径不变：`sys.platform == "win32"` 时只看文件在不在，不去读魔数（改了会把本机一切正常变成一切缺失）。
> - **B 段：三个「找工具」的入口都过同一个判定** —— N_m3u8DL-RE（`find_n_m3u8dl`，含递归扫 `tools/` 那一步）、本地 whisper 二进制（`_find_local_whisper_bin`，搜索模式也从 `whisper*.exe` 改成按平台取 `whisper*`）、aria2c（`aria2_daemon.find_binary`）。判定函数由调用方注入而不是在 `aria2_daemon.py` 里再写一份 ELF 判断，**两处口径从此只能是一处**；反向：`find_binary` 不传 `runnable` 时仍旧只判存在，老调用方行为一字不变。
> - **C 段：PATH 按 `os.pathsep` 拆 / 加 / 删**。这条踩过一个测试自身的坑：`os.pathsep` 是解释器启动时按当前系统定死的常量，只把 `sys.platform` 借成 `"linux"` 的话测的还是 `";"`，于是 `as_platform()` 把两者一起借 —— 第一版 C1/C3/C4 三条红的就是这件事，**生产代码当时已经是对的，红的是探针**。反向钉 Windows：`;` 分隔的 PATH 照旧拆成多项，Linux 风格的 `:` 串不被误拆。
> - **D 段用子进程真的 `import server` 两次**（`sys.platform` 在跑起来的进程里改不干净，只能在启动前定死），带与不带 `MEDIADOWNLOADER_STATE_DIR` 各读回 `STATE_DIR` / `CONFIG_FILE` / `COOKIES_DIR` / `DEFAULT_DOWNLOAD_DIR` / `LOG_FILE` / `HISTORY_FILE` 六项，读数写进 `%TEMP%` 的 UTF-8 JSON 再读回（控制台是 GBK）。**不设这个环境变量时 `STATE_DIR == APP_DIR`，本机行为逐字节不变**，这是这一轮唯一的回归保证。
> - **E / F 段静态钉住改漏**：`timeout_graceful_shutdown=` 在、`MEDIADOWNLOADER_HOST` 与 `MEDIADOWNLOADER_PORT` 都读环境变量、`@app.get("/api/health")` 在且**探针函数体里没有 `ffmpeg_mgr.version` / `check_ytdlp` / `whisper_status` / `find_n_m3u8dl` 任何一项**、无桌面时「打开文件夹」给 503 与「无界面运行」而不是 `TclError` 原文、`server.py` 里不再残留 `split(";")` 或 `";".join`、Linux 认系统 PATH 的那行兜底在、界面文件名列用 `f"ffmpeg{exe}"` 而不是写死的 `"tool": "ffmpeg.exe"`。镜像侧：apt 带 aria2 与 `libchromaprint-tools`、`MEDIADOWNLOADER_HOST=0.0.0.0` 与 `MEDIADOWNLOADER_STATE_DIR=/data`、`PYTHONUTF8=1` 与 `LANG=C.UTF-8`、**HEALTHCHECK 只打 `/api/health`**（非注释行里只有一条 `api/` 引用；Dockerfile 的注释里提到 `/api/status` 是解释为什么不用它，F 段特意把注释行排除掉再计数）、`.dockerignore` 挡住 `tools/` `Whisper/` `Downloads/` `config.json` 却没挡住 `server.py` `static/` `requirements.txt`、compose 不再把 `./config.json` 与 `./tools` 挂进去、端口默认 `127.0.0.1:8765:8765` 且没有裸的 `"8765:8765"`。
> - **paste_test A 段是反向钉**：`@paste="onPaste(box, 'url')"` 这种带参数的表达式在 Vue 模板里是**语句**而不是处理器 —— 表达式渲染时执行一次，返回的函数被直接丢掉，粘贴事件就成了空操作且界面上看不出任何异常，所以必须写成 `onPaste($event, 'url')`。B 段把 `extractUrls` / `cleanPasted` / `onPaste` 三个函数从 `index.html` 里**原样抠出来**交给本机 node 跑真实输入（不复制第二份实现，改了就测到），抠取按本项目的缩进规矩收尾而不是数大括号 —— 这个文件里有 `/[)\]}>;,、，。；：:!?"']+/` 这种字符类，数括号会抠出半截函数。

> 说明二：**本轮只有前端那一条有线上读数，别看混。**
> - **粘贴（前端 `static/index.html`，刷新页面即生效）**：七个框逐个在浏览器里读回 **7/7** —— 粘「【抖音】… https://v.douyin.com/xxxx/ 复制此链接」后框里只剩那条链接、`v-model` 跟着更新（`onPaste` 把值写回**原生输入框** `e.target.value` 再补发一个 `input` 事件，因为模板里取到的变量已被解包成字符串，拿它当 ref 赋 `.value` 是空操作）；聚合搜索关键词与磁力页分类试验框只取首行并并掉连续空白；首页媒体链接、磁力添加、订阅地址、直播监控列表四个多行框**原样保留**（这些内容在解析时才归一，粘进来的原文要留在框里对着看）。「粘贴」按钮全部保留，没拆。
> - **后端（`server.py` / `aria2_daemon.py` / `music_search.py`）当时没有线上读数**：写这一段时本机 8765 上跑的还是改动之前起的进程，`/api/health` 打过去仍是 404。**这一条从第二轮起过期** —— 实例已按要求重启，后端那几条现在有了线上读数，列在下面「第二轮」的说明二里。
> - **容器与 Linux/macOS 一律是「代码 + 离线断言」**：本机没有 docker CLI（`docker: command not found`），镜像**一次也没建过、跑过**；也没有 Linux/macOS 真机，非 Windows 分支是靠把 `sys.platform` 与 `os.pathsep` 借成别的系统来验的。所以下面「服务化」那一节的每一条都不许说成「实测跑通」。

### 界面

- **七个单行框支持右键直接粘贴**：媒体信息页「解析媒体链接」、音乐页歌单链接、Telegram 页频道名、直播页直播间链接、收藏关注页 YouTube 播放列表、聚合搜索关键词、磁力 / 种子页自动分类的试验框，各挂 `@paste="onPaste($event, 'url' | 'text')"`。清洗口径复用既有的 `extractUrls()`（抓 `http(s)://` 子串、去掉尾部 `)]}>;,、，。；：:!?"'`，`magnet:` 与 `.torrent` 行整行认）与 `cleanPasted()`，链接框取第一条、关键词框取首行并并掉连续空白，**与点「粘贴」按钮的结果一致，按钮一枚没少**。多行列表框不绑，理由见上。

### 修复（非 Windows 的崩溃点）

- **`is_native_binary()`（server.py:3912）成为唯一的「这台机器跑得动吗」**：Windows 上只看文件在不在；其它平台要求 `os.access(p, os.X_OK)` 且文件头是 ELF 或 shebang，PE 判假。接进 `find_n_m3u8dl()`、`_find_local_whisper_bin()`（server.py:625/631/634）、`env_path_status()`（10998）与 `aria2_daemon.find_binary(..., runnable=...)`（两处调用都注入同一个函数）。
- **PATH 分隔符不再写死**：`_path_split()` / `_path_add()` / `_path_remove()` 一律用 `os.pathsep`，「命令行 PATH」那一键在 Linux/macOS 上仍只打印 `export` 命令（写注册表是 Windows 专属）。
- **Linux 上 apt 装的 ffmpeg 不再被报成缺失**：`env_path_status()` 先按随包文件判，非 Windows 再补一次 `shutil.which()` 兜底，并把 `"platform": sys.platform` 一起带回；「组件与依赖」表格的文件名列改用 `f"ffmpeg{exe}"` / `f"yt-dlp{exe}"` / `f"N_m3u8DL-RE{exe}"`，不再硬写 `.exe`。
- **报错文案分平台**：`fpcalc` 缺失时 Windows 仍指「随包的 `chromaprint/fpcalc.exe`」，非 Windows 改成指 `chromaprint/fpcalc` 并附 `apt install libchromaprint-tools`（`music_search.find_fpcalc()` 的随包查找名同步按平台取）。
- **无桌面时「打开文件夹」给可懂的替代说明**：`api_browse` 捕获到 display / tkinter / 缺模块类异常（`python:slim` 镜像甚至不带 tkinter）且非 Windows 时回 **503 + 「当前是无界面运行（容器/服务器没有桌面），无法弹出系统选择框：下载目录请直接在输入框里填写，例如 /data/Downloads」**，不再把 `TclError` 原文甩上屏。
- **yt-dlp 自更新不再在 Linux 上下一个跑不动的壳**：`update_ytdlp()` 里那个 `yt-dlp.exe` 命令行下载现在只在 `sys.platform == "win32"` 时执行 —— 真正被 import 的是解出来的 `tools/yt_dlp` 源码包，在 Linux/macOS 上下回来既跑不了也没人调用，白占十几 MB。

### 服务化 / 容器

- **新探针 `GET /api/health`**：只读内存里的队列计数（`ok` / `running` / `paused` / `pending`），**不跑 `ffmpeg -version`、不 import `yt_dlp`、不递归扫 `Whisper/`** —— 那三件事 `GET /api/status` 每次都真做一遍，拿它当 30 秒一次的 HEALTHCHECK 等于把 CPU 全烧在工具检测上。路由清单因此从 193 条变成 194 条（MCP 桥挂 193 个工具）。
- **`uvicorn.run(..., timeout_graceful_shutdown=5)`**（server.py:19105）：`/api/events` 这条 SSE 进度流平时一直挂着，uvicorn 默认要等所有连接自己断开才退出，`docker stop` 于是等满超时被 SIGKILL，`finally:` 里的 `_bt_daemon_stop()`（19107，收掉自拉的 aria2c）根本轮不到执行。
- **状态目录收进一个环境变量**：`STATE_DIR = Path(os.environ.get("MEDIADOWNLOADER_STATE_DIR") or APP_DIR)`（server.py:52），配置、历史、订阅、Cookie、日志与默认下载目录全部锚在它下面；aria2 的会话目录跟着走（`ensure_running(..., app_dir=STATE_DIR)`）。**不设就等于程序目录**，Windows 上的落点一个字节没变。
- **Dockerfile 重写**：`python:3.12-slim-bookworm` + apt `ffmpeg aria2 libchromaprint-tools curl ca-certificates`（镜像里没有 `tools/*.exe`，磁力页因此开箱能用，不需要另起 aria2 服务）；先 `COPY requirements.txt` 再 pip、最后才 `COPY . .`，改代码不再重装依赖；`ENV LANG=C.UTF-8 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 TZ=Asia/Shanghai MEDIADOWNLOADER_HOST=0.0.0.0 MEDIADOWNLOADER_PORT=8765 MEDIADOWNLOADER_STATE_DIR=/data`（不设 UTF-8 时中文日志与文件名是一串问号），`VOLUME ["/data"]`，`HEALTHCHECK` 打 `/api/health`，`CMD ["python","server.py"]`。
- **docker-compose.yml 从两个服务减成一个**：`ports` 默认写 `127.0.0.1:8765:8765`（这个程序**没有登录**，直接 `8765:8765` 等于把改设置、发起下载、删任务开放给整个局域网；要对外那行怎么写，注释里给了），状态走命名卷 `mediadownloader_data:/data`，成品目录另挂 `./Downloads:/data/Downloads`。**删掉了原来的 `aria2` 边车与 `profiles:`** —— 镜像已经 apt 装了 aria2c，程序的自动拉起只监听 `127.0.0.1`，边车那种 `http://aria2:6800/jsonrpc` 是非环回地址，守护逻辑本来就会拒绝连它。
- **新增 `.dockerignore`**：`tools/`（Windows 的 `.exe`）、`Whisper/`（约 6 GB）、`Downloads/`、`chromaprint/`、`torrent_state/`、`local_index/`、`musicdl_outputs/`、`pack_cache/`、`browser_sniff_profile/`、`dist/`、`_preview/`、`config.json` / `history.json` / `subscriptions.json` / `live_monitors.json` / `music_favorites.json` / `rss_feeds.json` / `library_cache.json`、`*.session`、`cookies.txt`、`*.log`、`tests/`、`docs/` 与三份文档全挡在构建上下文外 —— 不挡的话 `COPY . .` 会把这台机器下过什么连同 GB 级缓存一起烤进镜像。`.gitignore` 用的是「默认全忽略、再逐项放行」的白名单，同步补 `!/.dockerignore` 才进得了仓库；`pack_release.py` 的 `APP_FILES` 也补上它，让拿到包的人能直接 `docker build`。

### 第二轮（同日）：4K 与码率 / 音质选择、两处按钮位置、aria2 缺失、直播录满自动保存

四条都来自实际使用。**① 「最高支持 4K 的视频只解析出 1080，而且不能选画面码率和音质了」** —— 查下来是两件事叠在一起，得分开说。分辨率那一半**不是本程序的错**：`https://www.youtube.com/watch?v=P65RnyA8UK4` 在本机出口上被 YouTube 风控，`yt-dlp -F` 带与不带 `cookies/cookies.txt` 都只回 7 条流（HLS 的 itag 91–96 加 itag 18），全是视频＋声音同一条的渐进 AVC，**响应里根本不存在 1440p/4K**（YouTube 的高清档只有 DASH 分流的 AV1/VP9 版本）。程序改不了上游给什么，能改的是「什么都不说」：现在 `_format_gate_note()`（server.py:12226）会在解析卡上写明「本次只拿到 N 条流，最高 1080p，且全部是渐进流 —— 这是 YouTube 对这个出口做了风控」，并按本机实际状态给可动的下一步（带 Cookie / 启用 PO Token，当前是未启用 / 换出口 + 更新 yt-dlp），带一枚「去设置」直接跳到设置页。**能选码率与音质这一半确实是本程序的**：档位以前只按高度出一条，现在 `_quality_presets()`（12348）按「高度 × 编码族」出，同一高度有 AV1 与 VP9 时是「2160p · AV1」「2160p · VP9」两条、各自带自己的 `format_id`，只有一个族时仍写「1080p」不加后缀；`_resolve_format()` 走表达式那条路时以前会把界面选的音频码率**静默丢掉**（`abr<=N` 只在别的分支拼过），现在每条视频表达式都带上这个上限。**这条提示后来自己也被修了一次**（见下面「第二轮补」）。

> 说明一（第二轮）：**这一条里有两个缺陷是只有联网才看得见的，别当成离线测出来的。** 拆出纯函数之后才发现并钉住 —— (a) 每个高度都被多贴一条「族名为空」的重复档位，界面上是并排两个「1080p」，点哪个都是同一条流，用户以为自己在选码率；根因是 `ordered += [...] or [""]`，那个 `or` 恰好只在「只有一个已知编码族」这种最常见的情况里触发。(b) 音质档位从渐进流的 `tbr` 里取，而渐进流的 `tbr` 是影音合计，于是界面显示「3879 kbps」这种数，选了也不改变任何东西 —— 现在只认真实存在的独立音轨，一条都没有时那排 chip 整排不显示，改说一句「这个源没有独立音轨：画面和声音在同一条流里，音质跟着清晰度走」。两件都由新增的 `tests/presetcodec_test.py`（**24 项**）离线钉住，输入就是解析用的那份归一化格式清单，不再靠联网复现。

**② 两处主按钮挪到输入框右侧**：媒体信息页的「确定解析」与聚合搜索页的「开始搜索」以前孤零零在输入框下面一行，现在和输入框同在一根 flex 行里（输入框 `flex:1; min-width:240px`），键入完直接回车或点最右边那枚；「粘贴」「清空」仍在下面一行，没跟着挪。

**③ 「读 aria2 活动任务失败: WinError 10061」**：这条红字的根因是**这台机器上当时根本没有 aria2c** —— 「磁力 / 种子」那一页整个引擎就是它，RPC 没人监听，于是每次 30 秒的看护都报「目标计算机积极拒绝」。现在 `tools/aria2c.exe` 装好了（1.37.0，经 ghproxy 镜像取 release 包、只解出 `aria2c.exe` 与随带的 `.dll`），四件事跟着补：`aria2_err_cn()`（server.py:4171）把 `<urlopen error [WinError 10061]…>` 这类原文翻成「本机找不到 aria2c：去「组件与依赖」点 aria2 那行的安装」或「点「检测 aria2」，它会自动拉起」这种能照着做的下一步（超时与带密钥 401/403 各有分支）；做种那一栏先看 RPC 通不通、不通就 `bt_ensure()` 试着拉一次并把原因写进那一行，不再只报「读不到」；「检测 aria2」现在真的负责把进程拉起来，回包带 `ensure:{ok,why}` 显示在状态那行；aria2c 也进了「组件与依赖」那张表（`active` 直接读本机 `aria2 -v` 的版本），配 `POST /api/update/aria2`（`update_aria2()`，4242）与页面上的「安装 / 更新 aria2c」按钮。**顺手修的一处谎报**：`/api/aria2/status` 里 `daemon` 是在自动拉起**之前**读的，于是「刚刚明明是本程序起的，界面却说不是本程序启的」，现在成功拉起后重读一次归属。路由清单因此从 194 条变成 **195 条**（除首页之外的 `/api/*` 有 194 条，MCP 桥挂 194 个工具 —— 这个数是本机 `GET /openapi.json` 现读的）。

**④ 直播录制支持选择时长自动保存**：`最长录制时长` 这个字段本来就存在，但它只对「监控房间自动开录」的那几场生效，**手动点「开始录制」的直播没有任何房间设置可挂，会一直录到人来手动收尾**；更要紧的是 `start_live_monitor_scheduler` 的循环把收尾检查 `_live_recording_tick()` 写在 `if items:` 里面 —— 一个监控房间都没添加过的用户，那检查从来没跑过。现在三处一起补：设置里新增「直播默认最长录制（分钟）」（`live_max_minutes`，0 = 不限），直播页「开始录制」旁边新增这一场的时长框（0 = 跟随设置），每房间设置沿用原字段；生效优先级由 `_live_effective_minutes()`（15280）统一判（任务/房间的非零值 > 全局默认 > 不限，一律夹在 0–1440），收尾检查挪出 `if items:` 每轮必跑（`_live_used_seconds()` 15607：还没记 `started_at` 的排队任务算 0，不会一入队就被收掉），结束调用改成 `end_live_tasks(ids, reason=…)`，任务卡上因此写「已录满 N 分钟，自动结束并保存」而不是以前那句写死的「用户结束录制」；`to_dict()` 对直播任务多带 `live_limit_min`，界面上是「还剩 X 分钟自动保存」的倒计时。**录满那一场会走完整的保存路径**（停拉流子进程 → 收尾 `.part` → 摘弹幕/聊天文件），房间那一侧仍按原设计置为暂停、等下播再放开，免得「最长 N 分钟」变成「每 N 分钟重开一场」。判定与接线由新增的 `tests/liveduration_test.py`（**38 项**）覆盖，其中 B / C 两段是拿真的 `DownloadTask` 与真的墙上时间跑真的 `_live_recording_tick()`，只有结束动作本身换成桩。

> 说明二（第二轮的线上读数）：**8765 那个实例已经按要求重启，第一轮说「后端没有线上读数」的那一节从此刻起过期**（`/api/health` 现在回 `{"ok":true,"running":0,"paused":false,"pending":0}`）。这一轮实测到的：`GET /api/aria2/status` → `online:true`、`binary` 指向 `tools\aria2c.exe`、`ensure:{ok:true,why:"已自动启动本机 aria2"}`，把上一进程留下的孤儿 aria2c 收掉后再打一次 → `daemon:{owned:true,pid:48780,alive:true}`；`GET /api/components` 有 aria2 那一行且 `active:"aria2 version 1.37.0"`；`POST /api/analyze` 对上面那条 4K 视频 → 8 条档位（一个高度一条、标签无重复）、`audio_abrs:[]`、`format_gate.limited:true / max_height:1080`；直播那条走的是**真录制** —— `live_max_minutes:1` 录 `live.bilibili.com/6`，64 秒时仍在录、72 秒那一轮自动结束，成品 `【直播】WE vs FLY 2026-10-13 18-13 [6].flv` 落盘 45,088,768 字节、状态停在 `stopped` 且原因写的是「已录满 1 分钟，自动结束并保存」（验完把这份成品、两个 `.chat.txt` 与封面清掉了，测试任务也已从队列删除）；右键粘贴在浏览器里实测：往直播页监控框粘「  https://live.bilibili.com/21452505 7月21日开播！+ 复制此链接，打开【B站】APP…」→ 框里只剩那条链接且 `defaultPrevented:true`；两处按钮位置只能按结构核（内嵌浏览器视口是 0×0，截不了图）：`.row` 计算样式 `display:flex`，「确定解析」「开始搜索」那两行里输入框的 `flex: 1 1 0%` 在按钮之前，即按钮落在行末。**没有实测的**：多编码族那条路（本机出口拿不到 DASH 分流，只有离线断言）；`POST /api/update/aria2` 的下载分支（本机已装好，没有再走一遍安装）。

### 第二轮补（同日傍晚）：PO Token 那句提示指错了方向

用户拿两张截图对着问：设置里「PO Token 服务门控」的开关明明**已经打开**（`po_provider_enabled: true`，地址 `http://127.0.0.1:4416`），解析卡上那句下一步却写着「启用 PO Token 服务… 当前状态 未启用」。先复现：重跑一次 `POST /api/analyze`，那一条回的是「当前状态 连不上该地址（服务没启动或端口不对）」—— 截图上那句「未启用」来自**开关拧开之前**的解析结果（解析结果缓存 3 分钟），文案本身没有读错键。但这句话该改：它把「开关、服务、插件」三件事混成了一句「去启用」，而用户已经启用了，剩下的两件事他从这句话里看不出来 —— ① `127.0.0.1:4416` 上没人应答，那是 **bgutil-ytdlp-pot-provider**，一个要自己跑起来的独立服务（Docker 或 node 起），本程序不带它；② 连它带的那个 yt-dlp 插件也没装（`_pot_plugin_installed()` 回 `installed:false`），服务起来了也没有地方挂票。

现在这一步由 `_po_gate_tip()`（server.py:12226）分三种状态说：开关没开 → 「当前这个开关是关的，需要票的播放器客户端一律不试」；开关开了但服务不通 → 点名**用户自己填的那个地址**、附上探测到的原因，并写明这是个要自己跑起来的独立服务；插件没装时再补一句「票要靠它取」，装了就不提（三样都缺时用户只会去看第一条）。配置里整段缺这两个键（老 `config.json`）也不炸。**4K 这件事的结论没有变**：本机出口仍被 YouTube 风控，只回 7 条渐进流、最高 1080p，而 PO Token 服务不是这个程序能替用户装上的东西 —— 能改的是别再把人往一个已经拧开的开关上指。**（这后半句到第四轮作废：出口没有被 hard-gate，缺的是「会吃票的客户端」；服务端也真的搬进了 `tools/bgutil-pot-server/` 由程序代起。）**

> 说明：`tests/presetcodec_test.py` 加了 E 段 **9 项**（三状态各自的话术、地址取自配置不写死、`installed` 决定提不提插件、缺键不炸、旧的写死文案没留着），整套 **33 项全绿**。重启后的线上读数：`/api/analyze` 那一条回「PO Token 的开关已经打开，但 http://127.0.0.1:4416 上没人应答（连不上该地址（服务没启动或端口不对））—— …而且 yt-dlp 那边的 bgutil POT 插件也没装（票要靠它取）」；`/api/config` 回 `po_provider_enabled:true`，`/api/status` 回 `po_token:{ok:false,installed:false}`；`/api/health` 仍 `{"ok":true,…}`。**顺带记一笔如实的读数**：`GET /api/aria2/status` 现在是 `online:true` 但 `daemon.owned:false` —— 那个 aria2c 是上一个实例被强杀（`Stop-Process -Force`，`finally:` 没轮到执行）留下的孤儿，本实例没起它，所以「不是本程序启的」这句是对的，不是归属重读那个修复失效。

### 第三轮（同日晚间）：PO Token 那一行加上了，顺手把它能不能解决 4K 测到底

> **⚠️ 这一节里那条「这台机器的 4K 不是 PO Token 缺的那块，缺的是网络出口」的结论是错的，同日晚些被第四轮推翻**（见下面「第四轮」）。错因写在第四轮里一句话：那次 A/B 只在**不吃票的客户端**之间比较，唯一变量根本没落到被检验的东西上。这一节的 ①（组件那一行、插件名检测）仍然有效，只是里面凡是「它不解决 4K / 缺的是网络出口」的话术都已按第四轮改口 —— 读到那几句请当成历史记录。

用户拿着新的解析卡（上面已经是分状态那句话）只说了六个字：**「加，怎么还是提示，解决它」**。这句话里有两件事，分开办了 —— ①把 PO Token 做成「组件与依赖」里能动手的一行；②别再改文案，去把 4K 本身弄明白。

**② 先说结论：这台机器的 4K 不是 PO Token 缺的那块，票这一层从头到尾都不是瓶颈。** 这次没有再靠猜：把 bgutil-ytdlp-pot-provider 2.0.2 真在本机跑起来（`npm ci --ignore-scripts` 绕开 `canvas` 那个要 node-gyp 的原生依赖 → `npx tsc` 出 `build/` → `node build/main.js`，`/ping` 回 `{"version":"2.0.2"}`；`npm ci` 直接跑会卡在 `canvas@3.2.3` 编译，而服务端运行时并不需要画布），再把 wheel 装进跑 `server.py` 的那个解释器，插件层与 8765 实例同时转绿 —— 服务端日志里对这个视频**确实 mint 出了票**。然后做 A/B，同一个视频、同一套 `_ydl_opts`，唯一变量是那个 node 进程在不在：

| 客户端 | 服务在（票已取得） | 服务停（取不到票） |
| --- | --- | --- |
| `default` | 11 条 / 最高 1080p / 独立视频轨 0 条 | 11 条 / 最高 1080p / 独立视频轨 0 条 |
| `tv` | 4 条 / 180p | 4 条 / 180p |
| `web` | 5 条 / 360p | 5 条 / 360p |
| yt-dlp 默认 | 11 条 / 1080p | 11 条 / 1080p |

itags 两边完全一致（`91/92/93/94` 的 HLS 切片 + `18` 的 1080p 渐进流 + `300/301`），**一条分流（video-only DASH）都没有**。又换了三条标着 4K 的片子（搜索取的，避免是个例）—— 同样 11 条 / 1080p / 零分流。所以这台出口（走本机那个回环代理，即上面记作 `<本机代理地址>` 的那一个）被 YouTube 判成只发 HLS + 渐进流的那一档，**带不带票一个样**；4K 不在响应里，任何客户端组合、任何票、任何 yt-dlp 版本都变不出来。要做的是换出口，不是把这个开关再拧一遍。这条结论现在有读数撑着，`_pot_component_note()` 那句「它不解决 4K」也不是免责话术。

**① 那一行加上了，但加之前先修了一个把状态读反的 bug。** `_pot_plugin_installed()` 探的是模块名 `bgutil_ytdlp_pot_provider` —— pip 包 `bgutil-ytdlp-pot-provider` 落盘的根本不是同名模块，而是 `yt_dlp_plugins/extractor/getpot_bgutil{,_http,_script}.py`，yt-dlp 只认后者。也就是说**插件装好了程序也照样报「插件没装」**：上一轮那句提示里「而且 bgutil POT 插件也没装」是假话，用户照着装完第二遍，状态不变。现在改探真正的插件目录（一次 `find_spec`，2 毫秒），三项都验在 `tests/potcomponent_test.py` 的 A 段。

**加的那一行**：`pkg_update.PIP_PACKAGES` 补 `bgutil-ytdlp-pot-provider`（不补进不去 `/api/update/pkg` 的白名单），`_component_rows()` 里每条 pip 行过一遍 `_pot_row_extra()`，只有这一行会被改：

- **绿点要三层都齐才亮**：插件装了 + `po_provider_enabled` 开着 + `/ping` 通。只看 pip 版本就给绿灯是假就绪 —— 这一行点「安装」装得到插件，那个服务端本程序带不来。
- **`_pot_component_note()` 按缺的那层说话**：缺插件 → 「这里点『安装』装的是插件层…服务端层本程序不带」；开关关着 → 「关着就不去取票，`http://127.0.0.1:4416` 通不通都一样」（不说「没人应答」，那是另一件事）；只差服务端 → 点名地址 + 现探到的原因 + 「不在这行的『安装』里」；三层都齐 → 「票取得到。但它不解决 4K…缺的是网络出口」。
- **`skip_all:true`**，界面 `compTargets` 把它从「一键更新」里摘出去 —— 缺的是服务端的机器上，替人 pip 装个插件没有意义，而且这一行会因为 `ok:false` 被天天算进批量更新。

**风控卡补了缺的那半句**：`po.ok` 为真时以前什么都不说，卡片上只剩「换网络出口」，用户没法判断票这一层到底管没管。现在走 `_po_ready_tip()`：「PO Token 这一层是通的（插件已装，`<配置的地址>` 在线取票），高清仍被裁 —— 缺的不是票，别再回去动那个开关」。地址取自配置，不写死 4416。

> 说明：`tests/potcomponent_test.py`（新，**28 项**：A 检测名字 3 / B 话术 7 / C 那一行的判定 7 / D 卡片收口 7 / E 接线 4）。其余四套没有回归：`presetcodec_test.py` 33、`liveduration_test.py` 38、`routebody_test.py` 14、`components_test.py` FAILED:none。重启 8765 后的线上读数：`GET /api/components` 18 行，新增那行 `active:"2.0.2" / ok:true / skip_all:true`，`note` 是「插件和服务两层都通了，票取得到。但它不解决 4K…」；`POST /api/analyze`（`youtube.com/watch?v=N06OlFLHERQ`）→ `format_gate.limited:true / max_height:1080 / format_count:13 / clients:["default","web_safari"]`，tips 两条：「PO Token 这一层是通的…」与「换网络出口…」，带 Cookie 那条不再出现（本机确实有 Cookie）。**这一轮没有做的**：不把 POT 服务端塞进程序自管（`aria2_daemon` 那套是给单个 exe 的，node 服务不在便携包里），也不写「一键起 POT」—— 它证明解决不了 4K，加个按钮只会多一个要维护的进程。本机那个 node 服务是从临时目录里起的副本，重启机器就没了，届时「组件与依赖」那一行会重新报「上没人应答」，那是对的，不是回归。**（这句到第四轮作废：服务端已搬进 `tools/bgutil-pot-server/`，由 `pot_daemon.py` 在探测到端口空着时用本机 node 补拉 —— 见下面第四轮第 4 条。）**

### 第四轮（同日晚间）：用户一句「以前那流都不止这些的」把上一节的结论推翻了

用户发来媒体信息页（`27ivMJDuElo`，卡片写着「本次只拿到 7 条流，最高 1080p」）并说：**「把它挪到 tools/ 常驻。以前那流都不止这些的」**。前半句是要做的事，后半句是对第三轮那个结论的异议 —— 这次先查异议。

**用户是对的，第三轮那条结论作废。** 两条独立证据：① `Downloads/` 里躺着 2026-10-09 之前的成品，ffprobe 读到 **AV1 7680×4320** 与 **VP9 3840×2160** —— 这台出口下到过 8K，「hard-gated 只发 1080p」当场站不住；② 把播放器客户端横向扫一遍（`default` / `web_safari` / `tv` / `tv_embedded` / `webclient` / `mweb` / `android` / `ios` / `android_vr` / `all`），只有 **`all`** 在票在的时候回 **38 条 / 最高 4320p / 独立视频轨 23 条（含 av01）**；把那个 node 服务停掉再跑 `all`，掉回 **11 条 / 1080p / 零分流**。

> **第三轮那次 A/B 错在哪（记下来，这类错误会复发）**：比较的双方是 `default`、`tv`、`web` 和 yt-dlp 默认 —— 这几个客户端**根本不消费票**，所以「服务在 / 服务停」两边回同一批 itag 是必然结果，而不是「票没用」的证据。**改的变量不在被检验的代码路径上**。另一侧同罪：程序的解析链写死 `["default","web_safari"]`，票取到了也没有客户端去花它，于是「打开 PO Token 开关」看起来确实什么都改变不了 —— 界面提示与代码各对一半，合起来把用户支去了换出口。
>
> **正确的口径是「两样都要」**：票取得到 **且** 用的是会吃票的客户端（`all` = 把所有播放器客户端各解一遍再合并，yt-dlp 里唯一会去要票的那一类）。缺一样，高清就不在响应里。

**改了四处代码**（`server.py`）：

1. **解析的接受条件**（`get_info` 里的 `_run_tries`）：清单里**没有独立视频轨**、而后面还排着 `all` 那次尝试时，不算收工 —— 那份 1080p 存进本次调用自己的 `fb_box` 兜底（顺手把 `self._info_fallback` 这个跨任务共享的属性删掉，两个链接同时解析会互相盖），换下一个客户端重解。新加的三个纯函数：`_yt_widen_attempt(cfg)`（只在门控开着**且** `/ping` 取得到票时才把 `all` 排进队列，取不到票就别白跑一趟 12s 超时）、`_yt_has_dash(formats)`、`_yt_max_h(formats)`（`resolution` 是 `宽x高`，取后半个；先匹配到的那个数是宽度，早先写 `(\d{3,4})` 会把 1920 当高度）。
2. **下载不再被窄客户端覆盖**：`elif is_yt and not audio_only` 那一支原来无条件拿设置里的 `pc_chain` 重新指定客户端，把解析刚才用 `all` 解出来的清单丢掉 —— `bv*[height<=2160]+ba` 在窄客户端下匹配不到分流，选择串一路退到末尾的 `b[height<=2160]`，**用户点 4K、实际下 1080p 渐进流，任务状态还是「完成」**。现在解析来自宽客户端就照它下（日志明写「解析出的清单来自 all（含独立视频轨），下载沿用同一套客户端」），错误轮换那条路保留在 `elif pc_chain`。
3. **`_resolve_format` 的高度上限原来会丢**：编解码偏好本身是 `[vcodec*=av01]/[vcodec*=av1]` 这种 `/` 串联的备选，整串拼进 `bv*…[height<=2160]+ba` 时上限只落在**最后一个**备选上，第一个备选成了「不限高度的 AV1」。实测代价：界面选 4K，第一条测试成品 ffprobe 读到 **7680×4320 / 519.8 MB**。改成每个备选各自带上 `[height<=…]`（`G1–G7` 七项钉住，含「1080p 请求不能被顶到 8K」「末尾兜底 `bv*+ba/b` 保留」「`[abr<=…]` 那档不因拆分而失效」）。
4. **PO Token 服务端搬进 `tools/bgutil-pot-server/` 常驻**：`robocopy` 把临时目录那份 `server/` 挪过来（9060 个文件 / 133.69 MB，含 `build/main.js` 与 `node_modules`），`/tmp/bgutil` 已删。新增 **`pot_daemon.py`**（照 `aria2_daemon.py` 的口径）：`po_token_health()` 探测里认出「连不上该地址」这一种原因才补拉一次（HTTP 200 但内容不对、地址写错都不许乱起）；**只允许 `127.0.0.1 / localhost / ::1`**，指向别的机器一律不动手并把原因说清；本机 PATH 没有 `node` 就直说「缺 node」，且这个事实只记一次不再反复 `Popen`；`owned()` 分得清是程序起的还是用户自己起的，退出时（`main()` 的 `finally` → `_pot_daemon_stop()`）只收自己起的那个；启动后台线程在门控开着时探一次（等于开机自拉），`/api/po_token/check` 多回一个 `daemon:{dir_exists,dir,node,owned,pid,alive}`。**不进便携包**：`pack_release.py` 的 `TOOLS_FILES` 是逐个点名的，`node_modules` 又整目录排除，B4 那条断言钉着。
5. **文案跟着改口**：`_pot_component_note()` 那句「它不解决 4K：出口被 YouTube 风控时带票也只发低清流，缺的是网络出口」删掉，绿了的那句改成「4K 要『票 + 会吃票的客户端（all）』两样一起，清单被裁成影音同条时解析会自动换成 all 重解一遍」；缺服务端那句从「要自己用 Docker 或 node 跑，不在这行的『安装』里」改成「程序会拿本机 node 起 `tools/bgutil-pot-server/`，PATH 里没有 node 才起不来」；`_po_ready_tip()` 现在只在 `all` 也试过、清单里仍没有更高档位时才说「这一次是真的只发到这儿了」，不再让人以为程序没试。

> 说明：新增 `tests/potdaemon_test.py` **47 项全绿**（A 端口与归属 5 / B 常驻位置 5 / C `ensure_running` 各分支 8 / D 自愈接线 7 / E 补试 all 12 / F 下载沿用 3 / G 高度上限 7；B 段那条「`pot_daemon.py` 要在打包清单里」是出包时补的，见下方「发布物」），`tests/potcomponent_test.py` 按改口后的话术重算，**28 项全绿**（B2/B4/B6/D1/D2 五条断言是跟着结论改的，不是回归）。其余套件没跑出新红：`presetcodec_test.py` 33、`liveduration_test.py` 38、`routebody_test.py` 14、`components_test.py` FAILED:none。
>
> **线上读数**（8765 按要求重启后）：`POST /api/po_token/check` → `daemon:{dir_exists:true, dir:"H:\…\tools\bgutil-pot-server", node:"H:\nodejs\node.EXE", owned:true, pid:54160, alive:true}`，`detail` 是 `HTTP 200 {"server_uptime":52…}` —— 服务端 uptime 只有 52 秒，说明这一份是新实例从 `tools/` 里拉起来的，不是上一次留下的进程。`POST /api/analyze`（`LTGkt3GrGNY`）→ **34 条流 / 最高 4320p / 独立视频轨 23 条 / 编码含 av01 与 vp9**，`format_gate` 变成空对象（不再报被裁）；日志两条连着看就是这条链在工作：`客户端 ['default','web_safari'] 只给影音同条（最高 1080p），带票的 all 还没试，重解一遍取优` → `[b105c814] 解析出的清单来自 all（含独立视频轨），下载沿用同一套客户端，列表最高约 4320p`。端到端真下两次：修高度上限**前**那条点 4K 得到 7680×4320 / 519.8 MB（就是 bug 本身），修**后**重下同一条 → ffprobe **av1 3840×2160 + opus**，241.2 MB，与界面点的档位一致。两条测试任务与两个成品（519 MB + 241 MB）验完已删，`_probe_matrix.py` / `_probe_clients.py` 等探针草稿一并清掉。
>
> **还没测的**：`all` 是「每个客户端各解一遍再合并」，被裁那条路径的解析要 12–25 秒（读数里 20:13:03 起、20:13:26 才定下格式）—— 只在清单被裁时才付这一趟，清单本来就有分流时一次就收工；容器里跑的那条路没有读数（镜像里没有 node，`pot_daemon` 会照实报「本机 PATH 里没有 node」，不会静默）。

### 已知限制

- **非 Windows 那条路仍然只有代码与离线断言担保**：本机没有 docker CLI（`docker: command not found`），**镜像一次也没建过、跑过**；也没有 Linux / macOS 真机，`sys.platform` 与 `os.pathsep` 是借来的。Windows 这一侧的改动有 8765 实例的线上读数（见上），容器那一侧没有。
- **没有 Linux / macOS 的包**：便携包仍然是 Windows 内嵌 Python 的 zip（`启动.bat`）。非 Windows 只有源码运行与镜像两条路，`tools/` 里的四个 `.exe` 在那边一律无效，得靠 apt 或自己放同名无后缀的二进制。
- **探针不代表「能下载」**：`/api/health` 只说进程活着与队列计数，工具是否就绪仍然只有 `/api/status` 知道 —— 这是刻意的（它贵），所以别把 `ok: true` 读成「ffmpeg 在」。
- **镜像里的工具版本跟着 Debian 走**：apt 装的 ffmpeg / aria2c / fpcalc 与 Windows 包内版本不同源，磁力那页的行为差异（aria2 版本、构建选项）没有对比读数。
- **`.dockerignore` 只管构建上下文**：`docker cp`、卷挂载与 `docker commit` 不受它约束，别把它当数据脱敏手段。

### 发布物

- **已发包**：`static/index.html` 的 `appVersion` 升到 `v1.3.1 · Element Plus`，README 两份的徽章与包名同处改口（版本真源只有界面那一处，`pack_release.py` 的 `app_version()` 从同一行抓，包名因此跟着变成 `MediaDownloader-1.3.1-portable`）。产物：`dist/MediaDownloader-1.3.1-portable.zip`（约 219 MB），校验值写在同名 `.sha256` 里（`sha256sum -c` 或 `Get-FileHash` 都能核；不在本表里抄一份 —— 包内那份 `CHANGELOG.md` 是打包那一刻的快照，校验值只能在包打完之后才算得出来，抄进来必然差一句）。**GitHub Release 没有新条目** —— `web_app/` 是个 git 仓库（远端 `github.com/QingYan1012/media-downloader-web`，分支 `main`；上一句写的「本机这个目录不是 git 仓库」是当时核对错了，仓库一直在，只是从没提交过），这一轮的改动一个字没提交、更没推，往仓库推包是要人点头的那一步。
- **出包前的复检**：`tests/` 下 41 套离线自检全部 exit 0，含这三轮改过的 `presetcodec_test.py` 33、`liveduration_test.py` 38、`potdaemon_test.py` 47（含出包时新加的 B5）、`potcomponent_test.py` 28、`routebody_test.py` 14、`platform_test.py` 44、`paste_test.py` 23、`torrent_test.py` 206、`bt_boost_test.py` 85、`mcp_test.py` 59（`mcp_test` 那条会拿 `mcp_server._app_version()` 和界面里的 `appVersion` 对撞，所以升版后单独重跑过一次；`components_test.py` 里的 `1.3.0` 是它自己写自己读的临时清单桩，不是版本真源）。8765 那台实例的活体读数：`/api/components` 18 行全绿（PO Token 行 `ok=true · active=2.0.2 · skip_all=true`，note 是第四轮改口后的那句）、`/api/po_token/check` 回 `daemon:{owned:true, pid:54160, dir:…\tools\bgutil-pot-server, node:H:\nodejs\node.EXE}` 且 `server_uptime` 在涨、YouTube 解析回 **2160p 的 VP9/AV1 两档 + 24 条独立视频轨**且 `format_gate` 为空、`tier_sizes` 里有 `4K` 一项、Bilibili 解析 12 条流 1080p 无风控卡（证明 `get_info` 那处接受条件的改动没伤到非 YouTube 那条路）、`/api/aria2/status` `online:true` 指向 `tools\aria2c.exe`、`POST /api/bt/trackers/refresh` 回 `ok:true count:30`。
- runtime 复用 1.3.0 那一份（`--skip-runtime`，`PKGS` 依赖清单这轮一个字没改），包内自检照跑不误：`[check] 14 个顶层模块在包内均可 import`、`[probe] 包内 pip 安装→导入 通过`、`[smoke] 包内服务已响应`（真起一次服务打 `/api/music/status` 与 `/api/components`）、`[smoke] 组件接口三档版本齐全，随包清单命中 12 项`，收尾的私密文件检查为空（`config.json` / `cookies.txt` / `history.json` / `library_cache.json` / `app*.log` / `__pycache__` 一样没进 zip，包内 `tools\` 只有 ffmpeg / ffprobe / yt-dlp / N_m3u8DL-RE 与 `yt_dlp\`）。
- **打包面查出的一处漏**：`pot_daemon.py` 不在 `pack_release.py` 的 `APP_PY` 里。漏出去的那台机器上 `import pot_daemon` 直接失败，三处调用点全在 `try` 里，于是表现是「PO Token 那行说程序会自己把服务拉起来」却永远只得到一句「自动拉起失败」—— 文案与实物对不上，而且 `check_module_imports()` 只遍历 `APP_PY`，自检本身也照不出来。已把它补进清单，包内那份与本机逐字节一致（`aria2_daemon.py` 一并对比过，同样一致）。同一处漏另加了一条自检钉住：`tests/potdaemon_test.py` 的 B5 直接断言 `"pot_daemon.py" in pack_release.APP_PY`，该套从 46 项变 **47 项全绿**。
- **打包脚本自己的一个假报错**：`smoke_test()` 的试跑端口原先写死 `8791`，第二次打包就撞上 `WinError 10013`（这端口在 Windows 上是共享的，撞上别人正在用时绑不上），报出来是「打包后的服务没能正常工作」—— 看着像包坏了，其实只是这个端口这一刻不属于我们。改成 `_free_port()` 向系统要一个空闲端口（`bind(("127.0.0.1", 0))` 再取回端口号）。这条只影响打包脚本，界面与包内运行时都不读它；试跑用哪个端口本来无所谓，`MEDIADOWNLOADER_PORT` 照旧传进去。
- `使用说明.txt`（打包脚本里的 `README_SHARE`）在「组件与依赖」加了一条：PO Token 那一行在包里初始是红的，点「安装」只补得上插件，取票那个服务端是 node 项目、不随包带、也不在「一键更新」里 —— 与界面那行的 `note` 同一个口径。
- 本轮改的文件：`server.py`、`aria2_daemon.py`、`music_search.py`、`static/index.html`、`Dockerfile`、`docker-compose.yml`、`.dockerignore`（新）、`.gitignore`、`pack_release.py`（`APP_FILES` 补 `.dockerignore`）、`README.md`、`README.en.md`、`tests/platform_test.py`（新，44 项）、`tests/paste_test.py`（上一轮新增，23 项）。
- README 两份同步（第一轮）：源码运行一节补非 Windows 的工具识别与环境变量；页面总览的折叠里加右键粘贴的口径；离线自检一节点名 `paste_test.py` 与 `platform_test.py`；目录结构列出 `Dockerfile` / `docker-compose.yml` / `.dockerignore`；「已知限制」加「非 Windows 那条路只有代码与离线自检担保」一行；MCP 那两处的路由 / 工具数按新增探针从 193 / 192 改成 **194 / 193**。
- README 两份同步（第二轮）：30 秒上手与「便携包里有什么」不再写「aria2c 要自备」，改成「组件与依赖那一行点一下就装」（对照表、能力域表、解析插件与 aria2 一节、常见问题、已知限制同处改口）；「能做什么」加画质档按高度 × 编码族与风控如实说明两条、加直播录满自动保存一条；「下载与队列」的折叠里新增「画质档怎么排」「上游只回低清流时如实说明」「录满自动对手动开的那一场同样生效」三条并把每房间的 `0 = 不限` 改成 `0 = 跟随设置里的默认`；「页面总览」的折叠加两处主按钮的落点；「磁力与种子」的折叠写清「检测 aria2」负责拉起、`ensure:{ok,why}`、归属重读、`aria2_err_cn()` 与做种栏的 `bt_ensure()`；「离线自检」点名 `presetcodec_test.py` 与 `liveduration_test.py`；「常用 API」补 `POST /api/update/aria2` 与直播时长的三个入口；MCP 那两处的路由 / 工具数按新增的安装端点从 194 / 193 改成 **195 / 194**（本机 `/openapi.json` 现读）。
- 第二轮改 / 加的文件：`server.py`（`_quality_presets` / `_audio_abrs` / `_analyze_single_formats` 拆分、`_format_gate_note` 接进解析响应、`aria2_err_cn`、`update_aria2` / `_components_list` 的 aria2 行、`/api/aria2/status` 的归属重读、直播时长那一整套：`_live_effective_minutes` / `_live_used_seconds` / `_live_recording_tick` / `end_live_tasks(ids, reason)` / `AddUrlsBody.live_max_minutes` / `ConfigBody.live_max_minutes` / `DownloadTask.to_dict` 的 `live_limit_min` / `ConfigManager.DEFAULTS`）、`static/index.html`（直播页时长框与任务卡倒计时、设置里「直播默认最长录制」、解析卡的风控提示与「无独立音轨」那行、两处主按钮位置）、`tests/liveduration_test.py`（新，38 项）、`tests/presetcodec_test.py`（新，**33 项**，含傍晚补的 PO Token 话术那 9 项）、`tools/aria2c.exe`（新装，1.37.0）、`README.md`、`README.en.md`、`CHANGELOG.md`。
- 第三轮改 / 加的文件：`server.py`（`_pot_plugin_installed()` 改探 `yt_dlp_plugins/extractor/getpot_bgutil*`、新增 `POT_PROVIDER_PKG` / `_pot_row_extra()` / `_pot_component_note()` / `_po_ready_tip()`，`_component_rows()` 的 pip 行过一道 `_pot_row_extra()`，`_format_gate_note()` 在 `po.ok` 分支补那半句）、`pkg_update.py`（`PIP_PACKAGES` 补 `bgutil-ytdlp-pot-provider`）、`static/index.html`（组件行显示 `it.note`，`compTargets` 认 `skip_all`）、`tests/potcomponent_test.py`（新，28 项）、`README.md`、`README.en.md`、`CHANGELOG.md`。
- README 两份同步（第三轮）：「组件与依赖」与解析插件一节改口 —— PO Token 的插件层现在能从界面装，服务端层不能，那一行的绿灯要三层齐；风控说明补「票这一层通着时卡片会明说不是票的问题」；常见问题里那条 YouTube 高清的解释补上「本机实测：带票与不带票回同一批 itag」；离线自检点名 `potcomponent_test.py`。
- 第四轮改 / 加的文件：`server.py`（`get_info` 的接受条件与 `client_tries`、新增 `YT_WIDE_CLIENTS` / `POT_SERVER_DIR_NAME` / `_yt_widen_attempt()` / `_yt_has_dash()` / `_yt_max_h()` / `_po_ping_ok()`，`po_token_health()` 加自愈补拉，`_resolve_format()` 的高度上限按备选拆分，`_yt_player_chain` 那条下载分支保住解析用的宽客户端，`_pot_component_note()` / `_po_ready_tip()` / `_po_gate_tip()` 改口，`/api/po_token/check` 回 `daemon`，启动线程 `_boot_pot_server()` 与收尾 `_pot_daemon_stop()`）、**`pot_daemon.py`（新）**、`tools/bgutil-pot-server/`（新，133.69 MB，不进便携包）、`tests/potdaemon_test.py`（新，47 项）、`tests/potcomponent_test.py`（改口后重算，28 项）、`README.md`、`README.en.md`、`CHANGELOG.md`。
- README 两份同步（第四轮）：把第三轮写进去的「带票与不带票回同一批 itag → 缺的是网络出口」那几处结论改掉 —— 常见问题与「高清档位取决于站点给不给」那两行改成「要『票 + 会吃票的客户端（all）』两样一起，程序在清单被裁成影音同条时自动换 all 重解」；「组件与依赖」的 PO Token 那条不再说服务端「本程序不带」，改成「服务端在 `tools/bgutil-pot-server/`，程序用本机 node 补拉，缺的是 node 而不是要人自己跑 Docker」；「解析插件」一节列上 `pot_daemon.py` 与 `tools/bgutil-pot-server/`；离线自检点名 `potdaemon_test.py`。

---

## v1.3.0 · 2026-10-13

本版一次落了六条线，彼此独立。**磁力 / 种子**从「有 aria2 就顺一点」做成了完整的一条：侧栏多一页，下载、选文件、做种看护、tracker 加料、自动分类、分上下行限速都在那一页上，参照的是 qBittorrent Enhanced Edition 的交互口径。**字幕**从「一条流水线跑完就不管了」做成能改的：文件页新增逐句校对台（读完改、改前留备份、被闸门挡住会说是谁在你读之后动过这个文件），翻译链上补了反射质检与「按每行字数重排」。**直播录制**的每一间房终于能各设各的（容器、画质、转码预设、最长录多久、只在几点到几点录）。**订阅**会先告诉你它打算怎么同步，上游删掉的条目也不再凭空消失。**通用下载链**补了一批直通与预估：自定义 yt-dlp 参数（全局与单任务，被拒的项当场点名）、每档画质的预估体积、播放列表按序号区间勾选、限速按时段分档、落盘文件名统一清洗、队列卡片显示实际下到的清晰度 / 字节数 / 封面、浏览器通知点一下跳到那条任务。另外整站接口挂出了一条 **MCP 桥**（192 个工具，只连本机）。还修了一件必须修的：**六个接口的请求体被当成了查询参数**，其中一条连带把 `/openapi.json` 打进 500 —— 那正是 MCP 桥和接口文档唯一的取数处。**音乐下载与收藏那几条链一行判定没动**（本版出现的三行 `music` 分支两行在订阅同步里、一行是诊断包的 Cookie 排除项）；Telegram 只跟着换了同一套文件名清洗口径。

> 说明一：判定口径与接线全部由**离线自检**覆盖 —— 今天（2026-10-13）本机一次跑完 `tests/` 下 **38 个套件、1964 项全绿、0 失败**（子进程 stdout 继承控制台 GBK 会炸 `UnicodeEncodeError`，批量入口固定带 `PYTHONIOENCODING=utf-8`）。本版新增或大改的六套：**torrent 206 项**（磁力/BT 全链）、**bt_boost 85 项**（加料 / 做种 / 自动分类三档）、**mcp 59 项**（协议往返与取数）、**srtedit 50 项**（逐句校对台）、**cookielogin 32 项**（登录态健康提醒）、**routebody 14 项**（请求体通道）。几处值得单独记的断言与反向验证：
> - **跑这批自检查出两处「自检桩没跟上代码签名」**，都不是产品缺陷，但都会让回归网漏掉真问题，已改掉：`sse_test.py` 的 `FakeTask` 少 `res_label / total_bytes / done_bytes / thumbnail` 四个字段，`_sse_prog()`（server.py:18859）一读就 `AttributeError`，退出码 1；`torrent_test.py` 里 `run_job` 的进度回调 lambda 只接 4 个参数，而生产代码 `on_progress(tid, pct, speed, eta, meta=None)`（server.py:8514）传 5 个，`TypeError`。**桩认不出新参数，就等于新参数没被验过** —— 因此顺手补了三条正向断言：`sse_test` 的 **C16**（prog 帧带上卡片要用的清晰度、已下 / 总字节、封面）与 **C17**（反向：没量到的那几项一律不进包，prog 回到「进度 / 速率 / 剩余 / 已用」四件套），`torrent_test` 的 **D7b**（进度里带的是 aria2 报的整个下载的字节，不是主文件那份 —— 两者在单文件种子里能差一个数量级）。
> - **routebody 14 项两头都堵**：A1「`/openapi.json` 生成得出（路径数 > 100）」与 D2「把坑复现回去就 500」配对，证明这条不是空断言；B1「每个请求体模型都走请求体，没有一个漏进查询参数」+ B2「确实有 N 个接口带请求体模型」；C 段逐条按真实接口验业务后果 —— `/api/live/end` **点名一条时只结束这一条**（修复前 `body` 永远是 `None`，等于不分对象地结束全部录制），不带 `ids` 时「全部」的语义没被改坏；D1/D3 复现回老写法必须掉进查询参数、POST JSON 必须被拒。
> - **srtedit 50 项**里三处要紧的：**E1 409 闸门**（读完之后字幕又被改写 → 拒写并在报错里点名文件与改写时刻，让界面重读；**E2** 被拦时盘上正文还是上一版；**E4** 不传 `base_mtime` 就不拦，老调用方照旧能用）；**B11 / C5** 反向（日志里不许出现 Cookie / 令牌字样；几次被拒必须一次都没碰过原文件）；**D4** 一秒内连续保存的备份不许互相覆盖（`原名.bak-<时间>` 撞名时补 `.1 / .2`）；**F1–F4** `.vtt` 读写各走各的格式（写回首行仍是 `WEBVTT`、时间仍用点分隔）；**H1–H3** 毫秒按位数换算（`,040` 是 40 毫秒不是 400，一位两位按十分位补全）；**G2 / G3** 前后端对齐 —— 界面调的就是那两条路由，前端「前后平移选中句」是按「起点 + 句长」重算止点，不许对时间字符串用 `toFixed()`。
> - **bt_boost 85 项 / torrent 206 项**把这条链的口径钉住：tracker 抓取失败不许把任务打死；`bt_tracker_max`（默认 30）限的是**一次给任务带多少条**，不是列表本身；自动分类命中即停、都不中才落 `bt_auto_fallback`（「兜底」），没配规则时不凭空造目录；做种看护按 `torrent_seed_ratio` / `torrent_seed_time` 收，收的是「达标之后停做种」，不是停下载；aria2 的报错码逐条翻成人话（码 12 明确写出「同一个种子在 aria2 里只能登记一次，先删掉或停止做种再重提」）。
> - **mcp 59 项**里三条最要紧：**A6 / B7** 工具的必填项来自 `openapi` 而不是猜的、`tools/list` 不外泄内部字段（`_call` 那种路由句柄不给客户端）；**G2** 拒绝非环回与畸形地址（`http://192.168.1.7:8765/api` 直接拒），`DEFAULT_BASE` 只允许 `127.0.0.1 / localhost / ::1`；**H7** `tools/call` 从协议层真的跑通一次，而不是只把清单列出来。脱敏是另一道闸：`REDACT`（mcp_server.py:34）按字段名（`cookie` / `token` / `secret` / `password` / `api_hash` …）把请求与响应里的值替掉，`mcp_calls.log` 只留长度与状态，`torrent_test` 与自检收尾都比对过落盘文件里不含密钥原文。

> 说明二：线上读回分两层，**别把隔离副本的读数当成用户那台机器上的结论**。
> - **通用下载 / 直播 / 订阅 / 可排障性这四项在本机 8765 那份正在跑的实例上读到**（PID 14392，2026-10-13 07:20:16 起，读之前 `/api/tasks` 是 `running=0 / pending=0`）：
>   - **自定义 yt-dlp 参数（`live_args` 18 项 / `live_cfg` 40 项全绿）**：全局那一串逐项过闸门，`--exec`（下载完成后执行任意命令）、`-f`（格式由首页档位决定）、自带 Cookie、外挂配置文件、会改变失败处理的参数、会连带指定格式的预设全部**点名拒绝并指回该去的地方**，浏览器里同步读到的提示原文是「已保存，其中 2 项参数没生效：--exec 已跳过：会在下载完成后执行任意命令；-f 已跳过：格式由首页的清晰度档位决定，指定某条流请用「指定 format_id」」；**好参数不陪绑**（只报被挡的那一项，`--socket-timeout 60 -N 4` 照常生效并入队）；单任务那一栏空着时按设置里那串报，不重复报两遍。收尾 `config.json` 还原成跑前那份字节、程序目录文件清单一字不差、队列回到空。
>   - **直播每房间设置（六步共 93 项，`FAIL` 0）**：新房间的六项默认全是「跟随软件设置」并当场写进 `live_monitors.json`（不是只在内存里）；非法容器 / 非法画质 / 非法转码预设 / 时长越界（`0–1440` 分钟之外）/ `25:00` 这种时间，逐条点名拒绝且**非法值不入库**；**跨零点时段（20:00–02:00）按原样收下**，只填一端提示「要同时填才生效」并保持另一端原样，开始=结束 会点名「全时段都不录制」并把这一对清空；不存在的房间和不带 `id` 的保存都当场 404（**不许被当成某条房间悄悄写进去**）；空串能把转码改回「跟随软件设置」。真录：设 1 分钟上限的那场在 75 秒内自己收场，日志写「本房间已录满 1 分钟，自动结束录制」，成品用的是这个房间设的 `mp4`、路径逐字等于录制任务自己记的落盘路径，且**转码产物（`audio_mp3`）也回写在房间上**；时段外那一场如实报「直播中(不在监控时段 20:00-02:00)」但一条任务都不开、不写「开播自动录制」日志；手动「结束录制」之后文件字节数不再变大（2097152 → 2097152，证明拉流的 ffmpeg 子进程真被 `_stop_live_recorder_children` 收掉），`.part` 收成可播放文件、目录里没有半截文件，房间不再挂着任务号并转为暂停等下播。探针造出的 24 个文件（16 份 mp4/mp3 + 8 份 chat.txt）逐个删净，监控数、任务清单、下载目录、`config.json` 全部回到基线。界面那半用 Playwright 在 1440 / 1100 两档视口量过：老记录（没有这些字段的）回填成「跟随软件设置 / 不转码 / 0」而不是空白，时段写错时「点名后弹窗保持打开」，改对再保存才成功，操作列三枚按钮（设置 / 暂停自动录制 / 删除）不裁切，每行摘要「本房间：封装 mkv」不越界，累计 6 次 `set` POST 全部被桩接住。
>   - **订阅同步计划预览与上游删档（`live_subs` 35 项全绿）**：`POST /api/subs/preview` 只算不做 —— **不入队、不动游标、不落盘**（反向断言「预览之后队列条数一条没多」「清档也不碰队列」），日志把「读到 N 条 / 未读 M 条 / 计划入队 K 条」三件事写清；查不存在的订阅与给它查留档都当场 404。跑完订阅条数 3、程序目录文件数 58（跑前 58），用户原有订阅每条字段一字不差，探针那条自己删干净，`subscriptions.json` 还在。
>   - **可排障性三件**：诊断包（`live_diag` 44 项 + 浏览器里 `ui_diag` 43 项）—— 包里 9 个条目（`README.txt` / `meta.json` / `config.json` / `status.json` / `components.json` / `tasks.json` / `logs/app.log` + 两份归档日志），`meta.json` 的「本包不含」逐条列出排除项（Cookie 文件本身、`tg_session`、下载成品、做种状态目录），全文**没有裸的鉴权头、没有 `user:pass` 形式的代理地址**，运行日志那句「[界面] 导出诊断包（9 个文件 · 27972 字节 · 配置里隐藏敏感值 1 处）」里的字节数与真包一致；界面上按钮排在「打开日志文件夹」之后、`small` 档、没被裁、工具条不横向溢出，点下去先给持续提示、按后端给的文件名触发 blob 下载，**后端 500 时把原话上屏**（「诊断包生成失败：日志文件读不到」）而不是「导出失败」，空包不当成功也不触发下载，失败也进日志并标注（失败）。限速时段（`t_speed` 56 项 + `ui_speed` 67 项）：一行一条 `00:00-08:00 -> 2M`，`->` `=>` `→` 空格 `=` `–` `~` 「至」「到」都认、全角冒号归一，**优先级是任务级 > 命中时段 > 全局**，`POST /api/config/speed_windows/check` 只按设置本身判、不碰任务级那一档，并说明此刻命中哪一档、当前钟点、认出几档、超出 30 行挡下；干净写法照常收下（反向）。文件名清洗（`t_fn` 86 项）：`server.py` 的 `safe_filename_component` 与 `telegram_mt.py` 的 `_clean_name` **同一口径**，两处正则都**允许多点后缀**（`app.tar.gz` 不能被截成 `app.tar`）、**截断之后才查保留名**（截短本身可能把名字截成 `CON` / `NUL`，那时补下划线前缀），零宽与方向控制符（`\u200b-\u200f`、`\u202a-\u202e`、`\ufeff`）一律替掉，正常中文名反向验证原样不动；`server.py` 里不再残留裸的禁字符内联清洗，`telegram` 侧没有第二套清洗正则。通知可点击（`ui_notify` 73 项）：桌面通知 `onclick` 跳到那条任务并闪 2600ms（120ms 之后再 `scrollIntoView`，避开切页入场动画里 `scrollIntoView({behavior:'smooth'})` 被 Chromium 静默丢弃那个窗口），任务已被清掉时说「这个任务已经不在列表里了」并把通知收起；封面取不到时 `@error` 只藏那一枚，不把卡片打回没有图。
> - **磁力 / 种子那条链的线上读回在隔离副本上做的**：另起一份副本实例（8799）+ 它自己的 aria2 RPC（16873），`aria2_bin` 指本机 `H:/Varia/aria2c.exe`。**用户那台 8765 上现在仍是 `enabled=false / online=false / binary=""`**（本机没装 aria2c），所以磁力页在 8765 上只是「页在、开关没开」，不算端到端跑通。副本上读到的是：重复提交同一个种子回**代码 12 的人话**（上面那条），任务行上 `kind=torrent`、`category=兜底`（界面 tooltip 说明「自动分类把它归到「兜底」，成品存在这一档的子目录里」），做种字段 `seeding / uploaded / share_ratio / seed_seconds` 都在。收尾按规矩做干净：规则清空（`bt_auto_rules=[]`）、任务删净（left 0）、两个探针目录（`分类试验` / `网页做种测试`）删除并验证不存在，8799 与 16873 两个进程 `taskkill` 后端口无监听，只留下本机原有的 8765 / 8795 / 8797。
>   - **一处没掩饰的读数**：队列卡片那次量尺寸（`ui_card3`）里，1440 与 1024 两档都留下一条 `net::ERR_UNSAFE_PORT` 的控制台报错 —— 那是探针喂给 `thumbnail` 的假地址用了浏览器禁用的端口，**不是产品缺陷**；卡片本身两档都量到 `spec`「1080p HDR 60fps · 420.0 MB / 1000.0 MB」（tooltip 写「实际下到的流：…，总量 …」）、磁力页那张种子卡写「1.3 GB / 2.0 GB」（tooltip「总量 2.0 GB」），缩略图 72×41，`metaH` 21 / 17 不越行、卡片与页面无横向溢出。每档预估体积（`live_tiers` 29 项）里两处要紧的反向：**上限之上没有那条分流时回退到实际最高档**（这片只有 1080p），回退**不会算出比 `best` 还大的体积**；「查不到的视频」不被当成「算好了但体积是 0」（那会在界面上写成一个 0 字节的档位）。
> - **只在离线自检里覆盖、线上没读回的**：逐句校对台的 409 闸门与备份撞名（`srtedit`）、MCP 桥的非环回拒绝（`mcp`）、请求体那 6 条接口的逐条业务后果（`routebody` 走的是 TestClient，不是 8765）、字幕反射质检的 10 类标签与每行字数重排（`ui_qc` 91 项是界面桩读数，接口侧靠 `QC_ROWS_CAP=200` 与 `_qc_budget` 的钳位断言）、Cookie 登录态红标的记旗与清旗（`cookielogin` 32 项）。这些**不许说成「线上验证过」**。
> - **本版没有真的按下的两件事**：整批组件更新（包内 runtime 一个字节没动，见「已知限制」前两条），以及磁力页在 8765 上开 `aria2_enabled` —— 那要在用户自己的机器上装 aria2c 并由用户决定。

### 功能

- **磁力 / 种子完整支持，并独立成一页**：下载与做种交给 aria2 的 JSON-RPC（`aria2_client.py` + 新增 `aria2_daemon.py`），程序在 RPC 没人应答时自己拉起一个**只监听 127.0.0.1** 的 aria2c（开关 `aria2_autostart`，默认开；`aria2_bin` 空则按 `tools/` → PATH → 环境变量找）。侧栏「下载」组内新增 `bt` 页（`{ key: 'bt', label: '磁力 / 种子', icon: 'magnet' }`），五节：添加磁力链接或种子（一行一条，本地种子写 `file:///` 或盘符路径）、种子任务（卡片带 aria2 状态、分类标签、做种读数）、Tracker 与限速（列表来源地址、自填 tracker、自动获取开关、注入条数上限 `bt_tracker_max`=30、新任务下 / 上行限速、首尾优先）、自动分类（`bt_auto_rules` + `bt_auto_fallback`，`POST /api/torrent/rules/test` 先在界面试命中再存）、aria2 与做种（RPC 地址、密钥、分片、大文件阈值、`torrent_seed_ratio` / `torrent_seed_time` / `torrent_meta_timeout`）。tracker 列表运行时抓（`bt_trackers.py`，默认源是 ngosang/trackerslist 与 XIU2/TrackersListCollection，`GET /api/bt/trackers` 读、`POST /api/bt/trackers/refresh` 强制刷），抓不到时**不拿空白当最新**、旧缓存照用，任务提交不许被这一步打死。新接口：`/api/torrent/upload`（种子文件）、`/api/torrent/select`（选内部文件下）、`/api/torrent/seeding`（正在做种，带上传速率 / 连接数 / 对方做种人数 / 这份种子里的 tracker 条数）、`/api/torrent/stop-seed`、`/api/bt/limit`。aria2 的报错码逐条翻成人话，码 12 直接告诉用户先删原任务或停止做种。
- **逐句字幕校对台（文件页）**：`GET /api/ai/srt` 按字幕路径或媒体路径读出 `{idx, start, end, speaker, text}` 与 `mtime_ts` / `format`，`.srt` 与 `.vtt` 都支持（毫秒按位数换算）；`POST /api/ai/srt/save` 只在点「保存」时写盘，**写前在同目录留一份 `原名.bak-<时间>` 备份**（撞名补 `.1 / .2`），空正文那行跳过并回报 `dropped`、止比起早的兜到至少 40ms、负起点夹到 0，写一行日志（改了哪个文件、几句、备份叫什么）。若字幕在「读完之后」又被流水线或别人改写，保存返回 **409 并在报错里点名文件与改写时刻**，界面据此要求重读，绝不覆盖刚生成的内容 —— 不传 `base_mtime` 的老调用方不受这道闸门影响。行内支持选中句前后平移（按「起点 + 句长」重算止点）、合并、删句、说话人标记写回时保留；整条平移仍走既有的「时间轴校准」。单份上限按行数卡（超 20000 行拒写并说明）。
- **字幕翻译反射质检 + 按每行字数重排**：`POST /api/subtitle/qc` 逐句查十类问题（`QC_KIND_LABELS`：没有译文 / 没翻译 / 没换成目标语言 / 疑似漏译 / 疑似加戏 / 术语没照表 / 数字对不上 / 疑似复读 / 超出每行字数 / 样式标签丢失），单次最多看 `QC_ROWS_CAP=200` 行，结果只写进运行日志、不改字幕；其中七类（除「超出每行字数」与「样式标签丢失」——换行的事与格式的事反射修不了）交给 `POST /api/subtitle/rewrap` 之外的反射修，`REFLECT_CAP=80` 一次修一批，**模型讲道理、合并成段落时只收带序号的行**，认不出序号就整句留着第一遍的译文，宁可不改也不把说明抄进字幕。`POST /api/subtitle/rewrap` 按 `subtitle_wrap_width`（默认 16，钳位 8–40）与 `subtitle_wrap_lines`（默认 3，钳位 1–4）重新断行，`_qc_budget` 统一算预算；开关 `subtitle_qc`（默认开）与 `subtitle_qc_reflect`（默认关，反射修要再花一次 token）。
- **直播录制的每房间设置**：`POST /api/live/monitors/set`（`LiveMonitorSetBody`）给单间房设六项 —— 容器（`_LIVE_FMTS`：跟随软件设置 / mkv / mp4 / webm）、画质档、转码预设（`TRANSCODE_PRESETS` 六档，如「转 MP4 (H.264 + AAC)」「转 MP4 并限制 1080p」「抽取音频 MP3」）、最长录制时长（`0–1440` 分钟，0 = 不限）、监控时段起 / 止（支持跨零点，只填一端不生效）。**字段为 `None` = 不改，空串 = 恢复「跟随软件设置」**；非法值逐条点名且不入库，六项一起存进 `live_monitors.json`。`_live_recording_tick` 到点收场：结束录制并写「本房间已录满 N 分钟，自动结束录制」，同时把该房间转为暂停（等下播再放开），成品与转码产物路径都回写到房间上。时段外不开录，但状态仍如实写「直播中(不在监控时段 …)」。
- **订阅：同步计划预览 + 上游删条目归档**：`POST /api/subs/preview` 拿一份「这轮打算怎么做」——读到多少条、多少条是未读、按当前规则会入队几条、被哪条规则挡掉，**不入队、不动 `last_ids` 游标、不落盘文件**；`POST /api/subs/archived` 与 `POST /api/subs/archived/clear` 管上游已删除条目的留档（`SUB_ARCHIVE_CAP=100`，超出按最老的挤掉）。`_feed_sync` 的对照口径改成「本轮读到的这一批 = 下一轮的基准」，条目从源上消失时进留档而不是凭空不见（`SUB_FEED_CAP=200`、`SUB_TEXT_CAP=160`）。
- **自定义 yt-dlp 参数直通（全局 + 单任务）**：新增 `ytdlp_extra_args`（设置里一栏 + 首页批量任务那一栏，任务级覆盖全局）。不是原样转发 —— 逐项过闸门，**被拒的项当场逐条点名并指回该去的地方**：`--exec`（会在下载完成后执行任意命令）、`-f` / `--format`（格式由首页档位决定，要指定某条流请用「指定 format_id」）、自带 Cookie（指回设置页）、外挂配置文件、会改变失败处理的参数、会连带指定格式的预设、把链接当参数写的输入。**没被拒的参数不陪绑**：其余照常附加，日志与界面提示只列被挡的那几项，界面上「已保存，其中 N 项参数没生效：…」保持弹窗不关，让用户能改完再存。
- **每档画质的预估体积 + 播放列表按区间勾选**：`_estimate_tier_sizes()`（server.py:11961）用各分流的折算码率乘时长给出每档预估（随 `tier_sizes` 在 12158 一起回给界面，纯音频那档不把视频轨重复算进去、视频行标出这条分流自不自带声音）；**上限之上没有对应分流时回退到实际最高档**，且回退不会算出比 `best` 更大的值，查不到视频时不当「算好了但体积是 0」。播放列表 / 合集那一节新增区间勾选：两个序号框（起 / 止）实时显示「区间起点：第 N 条《标题》」，点「勾选这一区间」批量勾上，再点下载才提交 —— 序号区间与逐条勾选共存（例：勾 5–9 而其中一条已下过就只提 4 条，提示写「已加入 4 个任务」）。
- **限速按时段分档**：新增 `speed_windows`（一行一条 `00:00-08:00 -> 2M`），`parse_speed_windows`（server.py:4684）认 `->` `=>` `→` 空格 `=` `–` `~` 「至」「到」，全角冒号归一，最多 30 行；`resolve_speed_limit()`（4721）的优先级是**任务级 > 命中时段 > 全局**；`POST /api/config/speed_windows/check` 做即时体检，回报认出几档、哪几行报错、此刻钟点命中哪一档（**只按设置本身判，不碰任务级那一档**）。
- **落盘文件名统一清洗**：`safe_filename_component`（server.py:4340）成为唯一入口，`_WIN_RESERVED_RE`（4336）**允许多点后缀**（`app.tar.gz` 不被截成 `app.tar`）、`_BIDI_CTRL_RE`（4338）剥掉零宽与方向控制符，**截断之后才查保留名**（截短本身可能截成 `CON` / `NUL`，这时补下划线前缀）。`telegram_mt.py` 的 `_clean_name()` 换成同一口径，两处 `_safe_name` 都走它；清洗改了名字时日志点名（「标题里有 Windows 不能用于文件名的字符，落盘名已清洗为「…」」）。种子上传的文件名也走这一入口。
- **全量 MCP 桥**：新增 `mcp_server.py`，stdio JSON-RPC，工具清单**不手写**、开桥时从 `<BASE>/openapi.json` 现取（所以接口增减自动跟上）：本版 193 条路由里除首页外 **192 条挂成工具**，`GET /openapi.json` 因此成了这条链唯一的取数处（这也是上面「请求体被当查询参数」必须修的原因）。摊平 query / path / body 三类入参为一份 `inputSchema`，body 签名是自由 `dict` 的接口给 `payload` 整包；`STREAM_PATHS` 那条注明「实时推送流：只取第一条事件就返回，不会挂在那儿等」。安全边界：`DEFAULT_BASE` 是 `http://127.0.0.1:8765`，host 不是 `127.0.0.1 / localhost / ::1` 就 `SystemExit`（**没有鉴权，所以只许本机**）；`REDACT`（34 行）按字段名把调用日志里的值替掉，`mcp_calls.log` 只留长度与状态，不落密钥与 Cookie 原文；`--tools` 只看映射结果不连服务。

### 界面

- **侧栏从 16 页 / 5 组变成 17 页 / 5 组**：「下载」组内插入「磁力 / 种子」（顺序：下载解析、队列、磁力 / 种子、嗅探、信息），`pageTitle` 同步补 `bt: '磁力 / 种子'`。
- **队列卡片显示实际下到的清晰度、字节数与封面**：卡片元信息行新增 `taskSpec()`（`res_label · 已下 / 总量`，例「1080p HDR 60fps · 420.0 MB / 1000.0 MB」），tooltip 由 `taskSpecTitle()` 写成完整一句「实际下到的流：…，总量 …」；缩略图 72×41，`@error` 时只藏这一枚（`thumbBroken[id]`）不把卡片打回没有图，`referrerpolicy="no-referrer"` + `loading="lazy"`。**没量到的那几项一律不占位**：`_sse_prog()` 只在有值时才把 `res_label` / `total_bytes` / `done_bytes` / `thumbnail` 放进 prog 帧，字节数一律「已下 / 总量」成对出现（磁力页那张种子卡只写「1.3 GB / 2.0 GB」，因为种子没有「下到的流」）。字段由 SSE 推，不必额外查一次接口。
- **浏览器通知可点击跳到那条任务**：`notifyDone()` 给通知挂 `onclick → gotoTask(id, task.kind === 'torrent')`（种子的跳新页而不是队列），切页后 **120ms** 再做 `scrollIntoView({block:'start'})`（切页时 `.content` 正在放 `pageIn` 入场动画，那段时间里 `behavior:'smooth'` 会被静默丢弃 —— 沿用 v1.2.9 查出的那条经验），目标卡片闪 2600ms（`flashTaskId`）；任务已被清掉时说「这个任务已经不在列表里了，可能已被清掉」并把通知收起，不留一条点了没反应的横幅。
- **Cookie 卡片学会了自己报「这一家的登录态可能不行」**：某平台的下载被判定为需要登录时，后端在内存里记一面旗（`_LOGIN_FLAGS`，**只保留到程序关闭**，不写盘 —— 那不是配置而是当下的网络事实），`GET` 带回 `login_issue`（时刻、站点、该做什么）与 `login_issue_count`；界面上那一行从「已配置 / 未配置」变成红标「疑似需登录」（tooltip 写是哪一次下载判的），卡顶多一条汇总行说明有几家被标出，行尾「清除标记」调 `POST /api/platforms/cookies/clear-flag`，重新导入该平台 Cookie 也会自动清掉。
- **两张表不再横向滚动 + 提示与控件的间距归位**：订阅源表与历史表原先靠 `table-layout: auto` 让内容自己决定列宽，长链接把表撑到 1516 / 1537px 而容器只有 1136 / 1178px，右侧「操作」列被推出屏幕。加了一个共享变体 `.fmt-table--fit`（`table-layout: fixed` + 单元格 `overflow:hidden; text-overflow:ellipsis`，index.html:775），两张表换上它并各自声明列宽（订阅源 92 / 298 / 100 / 130 / 56 / 84 / 152 / 72 / 152，历史 152 / 280 / 76 / 240 / 280 / 150），标题与链接装不下就截断、完整值留在 `title` 属性里，1440 与 1280 两档量到 `容器 == 表宽`（1136 / 1136、1178 / 1178、976 / 976、1018 / 1018）**不用滚动**、操作列零裁切；本版新出的订阅同步计划那三张表直接用同一个变体。1024 档仍要横向滚（见「已知限制」）。同一段里提示与控件的间距也修了：表单行里 `.hint` 与控件之间那 12px 的左边距在换行后仍留在行首，量到 `gap = -1126`（提示整块被挤到控件下方却仍按行内算）；改成独占一行的说明一律加 `.hint--block`（`flex: 1 0 100`，index.html:1361），同行控件的 gap 读回 12。磁力页那五节照这个口径排，`el-switch` / `el-input-number` 与提示同行、textarea 与提示分行。

### 修复

- **六个接口的请求体被当成了查询参数，其中一个把 `/openapi.json` 打进 500**：写法是 `body: SomeBody`（不带默认值）的模型在 FastAPI 里被当查询参数处理，`POST` 带 JSON 进来收不到，`body` 永远是 `None`。后果不是报错而是**静默做错事**：`/api/live/end` 的 `body` 恒为 `None` 等于不分对象地结束**全部**录制（点名一条时把别的房间一起收了）；`/api/tasks/pin`、`/api/tasks/unpin`、`/api/tasks/top`、`/api/tasks/later`、`/api/tasks/start-later` 只报「缺参数」，界面点「置顶 / 稍后」全无反应；而这类签名会让 `/openapi.json` 生成时抛异常（500），MCP 桥与接口文档唯一的取数处就此断掉。改成请求体通道后，`routebody_test.py` 14 项两头都堵（正向逐条 + 把老写法复现回去必须掉进查询参数并被拒）。

### 可排障性

- **一键导出诊断包**：日志页新增「导出诊断包」按钮（`POST /api/diagnostics/export`，`build_diagnostics_zip()` server.py:12735），把版本与运行环境、`status.json`、组件表、队列、`config.json` 与近期日志（`app.log` 上限 3000 行、归档 800 行、最多 3 份）打成一个 zip，直接发给别人排查。**这个包是给别人看的，所以脱敏在后端做掉**：Cookie 文件本身、`tg_session`、下载成品、做种状态目录一律不带，配置里 `music_platform_cookies` / `musicdl_cookies` / `platform_cookie_content` 等字段整体摘掉并在 `meta.json` 里说明隐藏了几处，正文再按字段名过一遍（密钥、令牌、`user:pass` 形式的代理地址），`README.txt` 提醒对方上传前自查。

### 已知限制

- **便携包里没有 aria2c.exe**：`TOOLS_FILES` 仍是 `ffmpeg.exe` / `ffprobe.exe` / `N_m3u8DL-RE.exe` / `yt-dlp.exe` 四件。拿到包的人要用磁力 / 种子，得自备 aria2c 并在「设置 → aria2 与做种」里填路径或放进 PATH（找不到时那一页直接说不清就报错，不会假装能用）。代码（`aria2_client.py` / `aria2_daemon.py` / `bt_trackers.py`）随包发。
- **便携包的内嵌 runtime 里没有 psutil**：本版新依赖只加进 `requirements.txt` 与「组件与依赖」的可安装清单（`pkg_update.py`），`PKGS` 没动、也没重打 runtime。缺它时后端在 2264 行只 warning 不炸（「缺 psutil，结束录制时没法核对拉流子进程：成品可能还在变大」），但**结束直播录制时收不掉 yt-dlp 派出去拉流的那个 ffmpeg 子进程**，成品可能一直变大、删了又长。要么装上 psutil，要么手动确认拉流进程。
- **MCP 桥只连本机、没有鉴权**：BASE 的 host 不是 `127.0.0.1 / localhost / ::1` 就当场退出。它把 192 条接口原样挂出去，其中包含改设置、发起下载、删任务这类写操作，所以**不要拿它对外提供服务**，也别把 `mcp_calls.log` 发给别人当调试件（值已按字段名摘掉，但接口路径、参数名与队列内容仍在）。
- **1024 宽以下两张表仍需横向滚动**：`table-layout: fixed` 的列宽有下限（时间列 152、操作列 150 等），1024 档量到容器 720 / 762 而表 940 / 900。窄屏要用时靠容器自己的滚动条，不打算再靠缩小字号或砍列去迁就 —— 要收口得先定哪一列可以不要。
- **登录态红标只活到程序关闭**：`_LOGIN_FLAGS` 不落盘，重启或换一次网络就可能重新出现。这是刻意的（它是当下的网络事实，不是配置），但也就意味着「昨天标过的那一家」今天不会自己提醒。
- **磁力 / 种子那条链没在用户自己的 8765 上端到端跑过**：本机没装 aria2c，8765 上 `/api/aria2/status` 仍是 `enabled=false / online=false`；所有读数来自隔离副本（8799 + 它自己的 16873，测完都已停并清干净）。真实大种子的做种长跑、DHT 在 NAT 后的表现都没测过。
- **逐句校对台与质检不在同一处**：质检结果只写进运行日志（`QC_ROWS_CAP=200` 之内），界面要逐条看还是得开校对台；反射修一次最多 `REFLECT_CAP=80` 句且要再花一次 token，默认关。字幕被流水线重跑会覆盖人工改动，409 闸门只挡「读之后被改写」这一种情形 —— 先保存再重跑的顺序仍需人来守。
- **自定义 yt-dlp 参数是白名单式放行**：闸门认得的危险项（`--exec`、自带 Cookie、外挂配置、改失败处理、指定格式）会被点名拒掉，但 yt-dlp 的参数面很宽，**没列进闸门的项就按原样附加**。这一串只对「本机自己下的任务」负责，不要把它的设置目录或诊断包外发给别人后照抄。

### 发布物

- 版本号真源 `static/index.html` 的 `appVersion` 升到 `v1.3.0 · Element Plus`（5162 行），`pack_release.py` 的 `app_version()` 从同一处抓取，包名跟着变成 `MediaDownloader-1.3.0-portable.zip`；`README.md` / `README.en.md` 的首行标题、徽章、功能一览与页面总览（17 页 / 5 组）同步，两份各补磁力 / 种子、逐句校对与质检、每房间直播设置、订阅计划预览、限速时段、文件名清洗、诊断包、MCP 那几节。
- `pack_release.py` 本版已把新模块与排除项写进去：`APP_PY` 收 `aria2_client.py` / `aria2_daemon.py` / `bt_trackers.py` / `mcp_server.py`，`EXCLUDE_DIR_NAMES` 加 `torrent_state`（上传过的种子与 aria2 会话记的是这台机器下过什么），私密件加 `mcp_calls.log`；`build_zip()` 另写一份 `sha256` 旁文件（Windows 文本模式会写成 `\r\n` 而废掉校验文件，所以按字节写）。CREDITS 补 qBittorrent Enhanced Edition、ngosang/trackerslist、XIU2/TrackersListCollection 三项鸣谢。出包后按 md5 核对包内的 `README.md` / `README.en.md` / `CHANGELOG.md` / `LICENSE` / `使用说明.txt` 与仓库里的是同一份，并确认包内含三个新模块与 `docs/screenshots/`、不含 `config.json` / `cookies/` / `Downloads/` / `torrent_state/` / `mcp_calls.log` / `tg_session/` / `local_index/`。Release 挂包与 `sha256` 旁文件，不写 zip 字节数与 sha256 本身（每次重出都会变）。

---

## v1.2.9 · 2026-10-09

本版两处改动都在界面上，彼此无关。**「组件与依赖」那张表学会了自己开口**：程序一打开就在后台查一遍上游最新版，确有得更新才提醒一次，没事时什么都不说。**信息页「按清晰度选择」那一排按钮的左对齐**：看上去只是没对齐，底下是 Element Plus 给相邻按钮补的那 12px 与 flex 间距叠在了一起。下载链、音乐、Telegram 那几条线一行没动，后端只多了一条检测链与一个开关。

> 说明一：判定口径与接线全部由**离线自检**覆盖 —— `tests/components_test.py` 今天（2026-10-09）本机跑完 **106 项全绿**、`FAILED: none`、退出码 0，其中新增的 **G 段 36 项**就是这条自动检测链。几处值得单独记的断言：
> - **G0a–G0h 版本比较器**（`_ver_newer` / `_ver_seg`）必须和界面里的 `verCmp()` 同口径：`2026.8.19 (local)` 对上游 `2026.9.1` 算有新版（括号那段不参与比较）、段数不等时补零（`1.2 < 1.2.3`，反向亦然）、本机显示「未安装」时上游版即算新的、**上游查不到版本号时一律不给结论**（不许拿空白当最新版）。反向验证 G0h：两串写成同一串必须判假，证明比的是数字段而不是字符串真假。
> - **G1–G4c 谁算「有可更新版本」**：只有「已装上 + 上游确实更高」进名单；版本相同、上游反而更旧（本机自己升过）、查不到上游版的都不算；**没装上的不算**（faster-whisper 这类故意不随包发，算进来就是每次开机催同一件事）；不在 PyPI 的 FFmpeg 与 N_m3u8DL-RE 不参与；同一个包的两行（`tools\` 里的 exe 与 pip 包）各算各的 —— exe 那行有新版、pip 那行没装时，只报 exe 那一行。
> - **G6 默认不联网**：`GET /api/components` 不带 `latest` 时那一行仍是空的、检测状态仍为 `idle`，检测必须由「立即检测」或启动那一次显式发起。
> - **G7 一次检测的完整往返**：桩子里故意让联网那一步停 0.5 秒，`POST /api/components/update-check` 仍在 **0.3 秒内**返回 `running`（证明请求没被卡在网络上，界面不转圈）；后台跑完落到 `done` 并记下完成时间；**一次检测只问一遍 pip**（`latest_versions` 被调用 1 次，不是每个包问一次）；`app.log` 留一行可更新数；`GET` 与 `GET /api/components` 带回的是同一份状态并都附带 `auto_check`。**G7g 反向验证**：把 `_comp_check_state()` 返回的 `available` 清空，真状态纹丝不动（给的是副本不是引用，界面改不动后端）。
> - **G8 幂等**：已有检测在跑时再发起不产生第二批（界面轮询不会把同一个查询打很多遍），而收尾之后能再起一批（不是一次性的）。**G8d/G8e 缓存**：`force=True` 确实把那 10 分钟（`LATEST_TTL = 600`）缓存作废（`_latest_cache["ts"]` 归零），不 force 时保留 —— 自动检测不该反复问 pip。
> - **G10 开关**：关掉之后 `GET` 回 `auto_check:false`（界面据此不查也不弹），但「立即检测」本身照样跑得通；`cfg.DEFAULTS["components_auto_check"]` 默认为真（新装机第一次打开就会查）；`ConfigBody` 收得到这个字段 —— 不然是静默丢弃，界面上关了、后端还在开。
>
> 说明二：线上读回分两层。**「没事时不打扰」这一条在本机 8765 那份正在跑的实例上读到了**（那是用户自己在用的进程，10:47:50 起来，本轮没重启它、也没写它的配置）：`GET /api/components/update-check` 回 `auto_check=true, status=done, started=10:47:51, finished=10:48:01, available=[]`，即启动后约一秒发起、整批联网 **10.0 秒**跑完；`app.log` seq 6 那句是「[组件] 检测上游版本：已在用组件都是最新」；`GET /api/components` 同时带回这同一份结果（界面不必多问一次），表里 15 项全绿 —— 没有可更新项，界面上既没有橙点也没有弹窗。收尾时 `/api/tasks` 数到 0 条任务。
> - **「有得更新才提醒」那一层在隔离实例上读**：另起一份副本实例、独立端口，用桩上游把其中一行的最新版抬高，浏览器里断言到侧栏「设置」出橙点、弹窗出现并点名是哪几项、`sessionStorage` 里 `mdCompUpdatePopupShown` 置位后同一会话第二次刷新不再弹；测完配置还原、真实 `config.json` 里根本没有这个键。
> - **跳转查出一个真缺陷并改掉**：弹窗里点「去组件与依赖」，页切过去了、滚动没动。原因是切页时 `.content` 正在放 `pageIn` 入场动画（`transform: translateY(6px)`，`watch(page, …)` 每次切页都会重新挂上 `is-enter`），**这段时间里 `scrollIntoView({behavior:'smooth'})` 会被 Chromium 静默丢弃**。改成动画窗口之后（120ms）走瞬时 `scrollIntoView({block:'start'})`，读回 `scrollTop` 从 0 走到 12534、那张卡的顶边落在 58px。
> - **摘要行初版太长把卡片撑歪了**：`compCheckText` 一开始把整份可更新名单铺出来，实测九行。改成最多列三项、超出写「等 N 项」、时间戳去掉年份之后量到 **两行 / 39px**，明亮与暗色两套都不越界。
> - **`bootCompCheck()` 初版无论开关都补发一次检测** —— 关着开关还去联网，那就是把用户明确关掉的事又做了一遍。加上 `&& d.auto_check` 之后，关掉开关时的网络面板只剩 `GET`、没有 `POST`。

### 功能

- **打开程序自动检测上游版本**：`main()` 里挂一只 daemon 线程，`sleep(3)` 等接口与配置就绪后读 `components_auto_check`，开着才调 `_comp_check_start()` —— 一次查询要十来秒，压在启动路径上会让程序看起来卡住，压在界面请求上会让设置页转圈，所以它既不挡启动也不挡界面，界面只读结果。结果存在 `_COMP_CHECK`（`status` / `started` / `finished` / `available` / `error`），读写都过 `_COMP_CHECK_LOCK`，对外一律给 `_comp_check_state()` 的副本。上游最新版复用既有的那层 10 分钟缓存（`LATEST_TTL = 600`），所以同一张表反复刷新不会反复问 pip，而「立即检测」以 `force=true` 作废缓存去问一次真的。可更新名单由 `_comp_available_updates()` 按上面的口径算（只已装、只 PyPI 上有号的、只 `_ver_newer` 判更高的）。新增两个接口：`GET /api/components/update-check` 读状态、`POST /api/components/update-check` 发起（`CompCheckBody(force, kick)`），`GET /api/components` 也一并带回 `update_check` 与 `auto_check`。前端 `bootCompCheck()` 先 `GET`，若后端那次没跑起来且开关开着（例如刚把开关打开）才补发一次；拿到结果后 `mergeCompLatest()` 把最新版灌进表里各行、`navDot('settings')` 让左侧「设置」亮橙点、`maybePopupCompUpdates()` 在有可更新项时弹一次（`sessionStorage` 键 `mdCompUpdatePopupShown` 加内存标记，保证每个浏览器会话只弹一次，之后只留橙点不再打扰）。卡上配「立即检测」按钮和一个「打开程序时自动检测」开关，开关写在 `components_auto_check`（`DEFAULTS` 默认开、`ConfigBody` 已收该字段），改动要点「保存设置」、下次启动生效。离线自检 G 段 36 项覆盖以上每一条。

### 界面

- **信息页「按清晰度选择（基于实际 format）」那一排对齐**：那一行是 v-for 出来的一排 `el-button`，看上去是按钮没跟上面的标题对齐，实测根因有两条，都来自 Element Plus 的 `.el-button + .el-button { margin-left: 12px }`：它和容器的 flex `gap`（那一行用的是 `--gap-tight` 8px）**叠成 20px**，按钮之间的间距因此比设计令牌说的其它任何一行都宽；更要命的是这份左边距**在换行后仍留在每一行开头那枚按钮上**，于是第二行、第三行凭空缩进 12px，左边缘和上面标题对不齐。改法是给共享行容器家族加一个变体 `.row--flush`（`gap: var(--gap-loose)` 即 16px，并把 `.el-button + .el-button` 的 `margin-left` 归零），那一行由 `row row--tight` 改为 `row row--flush`。这 12px 的抹平在代码里不是第一次做（`.tool-bar`、`.search-actions`、`.btn-grid` 各自都抹过），这次是把它做成一处共享变体而不是第四次重复。**没有顺手推给所有 `.row`** —— 那会连带改动已经验证过的其它布局，要不要全站统一留给用户定。验证用 Playwright 固定视口量左边界（内置浏览器标签页的视口会塌成 0×0，量出来全是 0）：宽窄两档视口下逐行数到每枚按钮的左边界与其所在行的左边缘一致、行首不再有那 12px 凭空缩进，另存了宽窄两张截图人眼复核。

### 发布物

- 版本号真源 `static/index.html` 的 `appVersion` 升到 `v1.2.9 · Element Plus`，`pack_release.py` 的 `app_version()` 从同一处抓取，包名跟着变成 `MediaDownloader-1.2.9-portable.zip`；`README.md` / `README.en.md` 的徽章、下载指引与便携包名同步，两份文档各补一节「打开程序自动检测上游版本」（功能一览、节首概述、`<details>` 摘要与正文四条落点，中英对应）。依赖清单没动（本版的改动不涉及任何包），出包按 `--skip-runtime` 复用上版装好的内嵌 runtime，只重跑复制与包内自检。

---

## v1.2.8 · 2026-09-24

本版落在三条线上。音乐是主线，只有一件事：**把「这是不是同一首歌」从一个判断做成一个口径**。过去「按曲名匹配」「歌单去重」「目录里已有成品」三处各自写着一套字符串相等与文件名的比法，同一个症状（同一首歌被下两遍、或者认成两首歌）要改三个地方。现在三处共用同一道打分闸门，并且顺着这个口径补齐了它周围的能力：本地音乐读出文件自带的真标签、跨平台换一条来路重下、监听歌单追新、把跨平台的歌攒成自己的一单、网易云扫码登录、按 Emby / Jellyfin 读库的排法命名归档、给出音质要求并按它与无损参照核对成品。
另外两条线不在音乐里：通用下载链上的**合集 / 播放列表逐集落点，与「命中下载记录」的诚实报告**（见「修复」前两条），以及嗅探链上**接收浏览器扩展猫抓（cat-catch）的推送**（「功能」倒数第二条与第三条，附带的规则导入缺陷见「修复」最后一条）；此外设置页的「组件与依赖」这一回多了**一键更新**（「功能」最后一条，配套的按钮等宽栅格见「界面」）。

> 说明一：本版改动原本只落在 `web_app/` 磁盘上；便携包已在 2026-09-26 出（`dist\MediaDownloader-1.2.8-portable.zip`，出包过程与包内逐条读回见下面说明十一最后一条）。这条只说明一个顺序：出包之后再动的代码或文档，要重出包才会带进对方电脑。
> 说明二：下面的判定与接线全部由**离线自检**覆盖，今天（2026-09-24）本机一次跑完 19 个音乐相关套件、**862 项全绿**（`matchgate 36`、`matchround 58`、`spotifylist 77`、`playlistdup 40`、`switchsource 40`、`localmeta 45`、`indexsnap 43`、`flacref 28`、`origin 21`、`zhnorm 21`、`music_sources 20`、`library_scan 14`、`music_endpoint 8`、`musicarchive 62`、`musicfavorites 83`、`musiclogin 82`、`musicplaylistsub 100`、`qualityspec 63`、`parallelpair 21`）。自检落点也复查过一次：`playlistdup` 那套跑下载入口端点时会走判重那条链，把本地索引快照写进程序目录的 `local_index\`，现已把它的索引目录一起拐进临时目录，整套跑完 `local_index\` 里只剩真实下载目录那一份。
> 说明三：17:41:48 那次进程（PID 21996）线上读回过的 ——`GET /api/music/favorites`、`GET /api/music/cookies` 均 200，`GET /api/music/status` 带回 `quality_options` / `quality_spec` / `include_local` / `filename_template`；「扫描本地库」回 `count=108` 与 `index_file`（快照落在 `web_app\local_index\`，已是带 `scanned_at` 的新格式，下载目录里不再留老索引）；`POST /api/music/check_quality` 读三份真实成品回 `reader=mutagen+ffprobe`、`have="MP3 44.1kHz/320k"`，越界路径按预期 400 并点名下载目录；资源库扫描回 108 条音频 + 16 条视频，音频行带 `lossless` / `quality` / `bit_depth` / `sample_rate` / `bitrate_kbps`；把快照改成一小时前并藏掉一行之后，搜索当场返回的就是那份旧内容（被藏的那行不在结果里），响应返回后 2 秒内磁盘上的快照自己变新、那一行回来；浏览器侧用 `evaluate_script` 逐条断言过：拿搜索接口真返回的两行本地成品（`is_local` + 磁盘路径）点进播放条，条上曲名 `Brave Shine`、歌手、内嵌封面（`naturalWidth=300`）、进度条上限 252 秒、时长 `4:12`、音量 `80%` 全对；在 首页→队列→文件→音乐 之间切页，播放条一直在且 `currentTime` 从 14.2 秒连续走到 17.7 秒（音频没被打断）；「下一首」跳到第二行并把两端按钮的禁用态对调，音量滑杆改 0.35 后 `<audio>.volume` 同步为 0.35，进度滑杆拖到 120 秒后实际播放位置 121 秒，静音键双向翻转标题与 `audio.muted`；空格在焦点为 `body` 时暂停/恢复各命中一次，而在 `.el-input__inner`、`textarea`、播放条按钮上、以及带 Shift / Ctrl 修饰时**都不触发**，弹窗（`.el-overlay`）开着时在框体与获得焦点的按钮上同样不触发；判重弹窗按真实的 0–100 分渲染，两行都列出「曲名 → 目录里那个文件名（同一首判定 91 分，目录里那首叫「…」）」并写明依据与「要重下就取消勾选『跳过已下载的歌』」；「扫描本地库」的提示为「本地索引 108 首，索引文件在 …\web_app\local_index\local_music_index_f7f582ca27c951db.json」。
> 说明四：18:38:52 重启（PID 47120）之后，那三处后端细化已经在跑的代码里（「搬家保留旧修改时间」那条线上无法再复现 —— 老索引在那次重启之前就已搬完）。这一轮线上读回的是收藏整单实下与按模板实下，并且**从这次读数里查出一个真缺陷**：
> - **收藏整单 4 首实下**：四行 `GET /api/music/favorites` 全回 `resolved=ready`，`POST /api/music/favorites/download` 不带 ids 即整单，18.7 秒跑完、`ok=4/4`，下载目录落 12 个文件（4 音频 + 4 歌词 + 4 封面），收尾没有文件消失。**同一次读数查出：四个名字装的不是自己的音频。** 本地索引按文件自带标签读出的时长是 5:39 / 3:14 / 3:43 / 8:47，而清单标注依次是 8:47 / 3:42 / 5:36 / 3:14 —— 整份倒序，只有文件名与歌词封面是对的（那两步各用行自己的元数据，没走错位的对位）。根因与修复见「修复」第一条；这条修复要下次重启才在跑的进程里生效。18:50 那一单只有两行、按模板下出来的两份是对的（`01 - Memento Mori` 8:47、`02 - Aimer` 3:43），因为这批的线程完成顺序恰好等于清单顺序 —— 缺陷是顺序相关的，不是每次都犯。事后把那 4 组共 12 个文件（连同 18:50 那两份正确产物，一起挪走才能让重测的四行都真下、不被判重闸门摘掉）整体挪进 `%TEMP%\md_crossed_batch1_1848\`，两次「扫描本地库」把索引从 114 削回 108，收藏清单四行仍 `resolved=ready`。
> - **按命名模板实下**：模板临时改成 `{artist}/{album}/{track} - {name}`，成品确实落成 `Downloads\Charles Aznavour\Aznavour - Anthologie\02 - Aimer.mp3` —— `{album}` 取自平台真元数据，`{track}` 在平台没给序号时按清单位置补零；测完模板已还原。
> - **「跳过已下载」闸门线上复测**：第二次提交同一单时 `already=2`、判定分数 100、`already_list` 指向新模板路径，盘上没有出现 `_1` 副本。
> - **YouTube 歌单**：`POST /api/music/playlist` 两次都在 8.0 / 8.1 秒返回 0 行，逐源报错写「连不上该站点（海外平台国内直连通常不通，请在设置里填 HTTP 代理）」—— 本机注册表代理对 `requests` 是通的，所以这条还没查下去，「订阅页识别音乐歌单链接」的线上读回仍欠着。
> - 还欠线上读回的：勾「不达标不下」的拦截、订阅页识别音乐歌单链接、网易云扫码登录（要手机）、界面点「换源」、判重弹窗在浏览器里真弹出来（接口侧的 `already_list` 已读到）、以及重启后用同一单四首复测上面那条音频错配。
>
> 说明五：19:17:27 重启（PID 48532）之后，上面那条按曲名对位的修复已经在跑的代码里。这一轮把说明四末尾欠的四件事读回了：
> - **同一单四首重下（19:38，`skip_downloaded=false`）**：`POST /api/music/favorites` 重收那两行被重启挤掉的（先 `favorites/remove` 再按 19:29 那轮搜索的真实行加入，四行都回到 `resolved=ready`、`reminted=0`），整单 39.3 秒跑完、`ok=4/4`，落 12 个文件。逐份读文件自带标签核对到每一行都是自己那首：`Memento mori - androp, Aimer.m4a` 实测 526.70 秒（清单标 527）、`Aimer vivre - Johnny Hallyday.m4a` 339.74（336）、`Aimer - Charles Aznavour.mp3` 222.59（222）、`Aimer La Vie (Soy Un Truhan Soy Un Senor) - Julio Iglesias.mp3` 194.05（194），标题 / 歌手 / 专辑三项标签也都对得上自己那一行，运行日志里没有「认不出哪个文件是它自己」。**这条只证到没有回归**：这一次 musicdl 交回来的完成顺序又等于清单顺序，所以对位那一步在真进程里仍未被逼出来；逼出来靠离线 `tests/parallelpair_test.py`（人为把完成顺序打乱的桩子，外加「退回老逻辑就必须被瞎指到无关文件」的反向验证）。
> - **判重闸门与弹窗（19:41，界面上勾着「跳过已下载的歌」点「整单下载」）**：`already=4`、四行判定分数都是 100、`already_list` 逐个指向上面那四个真实路径；浏览器里 `.el-message-box` 标题「目录里已经有同一首歌」，正文逐行写成 `曲名 → 目录里那个文件名（同一首判定 100 分，目录里那首叫「…」）`，末尾说明判定按曲名 + 歌手 + 时长打分、不看文件名，以及要重下该取消哪个勾选；关掉弹窗后目录条目数 408 → 408，一件没多，没有出现 `_1` 副本。
> - **勾「不达标不下」的拦截（19:43）**：同一批四个槽位走 `POST /api/music/download`，只在请求体里给 `quality_spec={format:"lossless", min_bit_depth:24, strict:true}` 且 `skip_downloaded=false`（没写进设置，跑完 `config.json` 的 `music_quality_spec` 仍是全空）。日志先复述要求「本批音质要求：无损、24bit 以上｜已勾『不达标不下』」，再逐首点名差在哪一维：两首写「M4A，低于要求 无损、24bit 以上：不是无损」、两首写「MP3，…：不是无损」，收尾一句「没有有效曲目可下载（4 首被『不达标不下』拦下，原因见上面几行）」；状态接口 `total=4 / ok=0 / skipped=4 / elapsed 0.0`，下载目录 342 个文件一个没多。
> - **收藏表「操作」列四枚按钮对齐**：列宽从 230 放到 260 之后，四行（都 `ready`，各显 试听 / 换源 / 下载 / 删除）在浏览器里量到的左边界完全一致 —— 1080 / 1141 / 1202 / 1264，每枚宽 49，四枚的 `top` 同一个值（一行装下、不换行），最右一枚右边界 1313 在单元格右边界 1332 之内。
> - 收尾：重测的 12 个文件挪进 `%TEMP%\md_4song_retest_1938\`，按用户要求删掉下载目录里那 4 个空目录（`Aimer, androp`、`androp, Aimer`、`Charles Aznavour`、`Johnny Hallyday`），「扫描本地库」把索引从 112 削回 108（342 个文件、空目录为 0）。
> - 还欠线上读回的：网易云扫码登录（要手机）、界面点「换源」（订阅页识别音乐歌单链接见下面说明六）。
>
> 说明六：这一轮接着读「订阅页识别音乐歌单链接」。换成网易云公开歌单 `Space Club/蹦迪必备`（`https://music.163.com/#/playlist?id=946216567`）作样本之后识别全通，但**从读数里查出两个真缺陷**，磁盘上已改掉：
> - **线上读回（19:58:23–25，PID 48532）**：订阅页「添加订阅」框粘贴链接 → 卡上预览标签显示「音乐歌单」→ `POST /api/subs/add` 落库 `kind="music"`（后端按域名表重推一遍，不信界面预览）→ 运行日志依次是「先用 yt-dlp 快速列出 NeteaseMusicClient 的曲目（走链接下载）」「yt-dlp 歌单解析: 300 首」「歌单里有 5 首与前面的重复（同一首歌被加过多次），已合并成一行，下载只下一遍」「歌单解析: 295 首（yt-dlp，耗时 2s）」「订阅初始化: Space Club/蹦迪必备 记录 295 条，跳过首次下载」；`new_count=0`，下载目录一个文件没多。20:17:28 那一轮 60 分钟定时器（`sub_interval_min`）又扫了一次，回「订阅扫描完成: 检查 1 源，新增 0」。
> - **缺陷一：同名不同曲并成一条**。快列模式（yt-dlp 只列曲目）在网易云这一路**只给曲名** —— 实测 flat 子条目的 `uploader` / `channel` / `duration` 全是 null，只有 `url` 每首不同（`http://music.163.com/#/song?id=…`），于是盘上那 295 条游标全部长成 `mus:曲名||0`（带别的形状的为 0 条）。一张歌单里两首同名不同曲（原声版与混音版、重名专辑曲）会被并成一条，后一首当成已读、永远下不到。现在 `_music_entry_id()` 在「歌手与时长都空」且拿得到链接时补一段链接哈希（键成 `mus:曲名||0#<12 位 md5>`），曲名先截到 80 字，免得那段哈希被整条键的 120 上限砍掉而静默退回老毛病；歌手或时长任一还在时键的形状一分不动（已有订阅不用整体重下一遍）。收藏清单那头的 `_music_fav_row()` 不传链接，清单主键形状保持不变 —— 那是存盘的主键，一改形状，清单里已有的「只有曲名」那些行就不再被认成同一首、会存进第二遍。
> - **缺陷二：这种行被丢进通用队列**。同样因为快列模式，行上没有音频地址、也没有缓存 id，旧的 `_enqueue_music()` 只能走 `urls` 那条兜底，把歌页链接交给通用 yt-dlp 队列去抽 —— 对音乐平台从来就不稳。现在 `_music_sub_entries()` 给没有缓存 id 的行当场铸一个槽位并写入 `needs_match` 占位（与收藏清单空槽同一套口径），这批行因此走「按曲名匹配」那一轮去取地址；行上本来就带缓存 id 的原样透传不另铸，真没有 sid 又带直链的仍退回通用队列兜底，sid 与直链都没有时当场报「这批新歌一条都没法下」而不是静默吞掉。
> - **顺带查出一个必炸的漏**：`_music_entry_id()` 里用了 `hashlib.md5()`，而 `server.py` 从来没导过 `hashlib` —— 走进那段就抛 `NameError`。是新增的自检第一次跑就炸出来的，已补 `import hashlib`。
> - 这两条修复**当时还没在跑的进程里生效**（PID 48532 是 19:17:27 那次启动的，盘上那 295 条游标仍是旧形状）；重启后的读回见下面说明七。
> - 离线自检 `tests/musicplaylistsub_test.py` 从 81 项扩到 100 项（新增 H 段 19 项，反向验证四条：不写缓存就不可能被匹配轮认到、桩换回真函数立刻认得到、真没有 sid 时仍走兜底、sid 与直链都没有时当场报错）。20:16 本机把 `tests/` 下 27 个离线套件全跑一遍，全部 0 退出码、无 FAIL；`subscriptions.json` 与 `config.json` 内容复查未变。
> - 另外记一笔现场状态：19:58 建的那条测试订阅在 20:16:41 被改过规则（日志「订阅「Space Club/蹦迪必备」规则已更新：只要 长视频、时长≥5分钟、排除「预告」「直播」、每次最多 3 条」）。音乐歌单的条目一律是「音频/播客」这一类，所以勾了「只要 长视频」之后这类源每一轮都会全条被类型规则挡掉、永远下不到歌；时长那条不挡人（条目没有时长时按「读不出来 ≠ 不达标」跳过）。这条订阅要不要留、规则怎么设，等用户定。
> - 还欠线上读回的：网易云扫码登录（要手机）、界面点「换源」。重启后按新口径的复测见下面说明七。
>
> 说明七：20:27:58（PID 37340）重启后，说明六那两条修复已经在跑的代码里；这一轮按新口径把同一张歌单整条链读回，**两条都成立**。
> - **重建订阅**：按用户要求删掉旧的那条（`1a88a9670b`，连带 20:16 那次「只要 长视频」的规则编辑一起没了），`POST /api/subs/add` 重新粘同一个链接 → 新 id `1401978dc2`、`kind="music"`、`init_count=295`。盘上 295 条游标**全部**长成 `mus:曲名||0#<12 位十六进制>`（带 `#` 的 295 条、去重后仍 295 条），旧形状一条不剩 —— 缺陷一改掉。
> - **逼出一首「新增」**：`last_ids` 只在启动时从盘上读一次，所以在服务停着的时候把 `mus:Where I'm From||0#9b55987ea122` 从文件里摘掉一条再重启（20:29:49，PID 32608；重启前后 `/api/tasks` 都是 `running=0 / pending=0`）。20:30:08 `POST /api/subs/scan-one` 回 `new=1`，日志依次是「订阅「Space Club/蹦迪必备」→ musicdl 下载 1 首（后台，每 6 首归档一次），其中 1 首要先去 Spotify 按曲名匹配音频地址，会慢一些（进度见日志）」→「匹配源含 Spotify：这两个源要经第三方转链取址，每首约十秒且时常失败，整单会明显变慢（整轮预算放宽到 3000s）」→「订阅「Space Club/蹦迪必备」新增 1 条，按规则[每次最多 20 条]入队 1 条」→「开始按曲名匹配 1 首：Spotify（每首搜到就停，整轮最长 3000s）」→「匹配 1/1：Where I'm From → 没找到」→「有 1 首在 Spotify 里按曲名没找到同一首歌，已跳过」→「没有有效曲目可下载」。`GET /api/music/download_status` 收在 `total=1 / done=1 / ok=0 / elapsed_s=42.3`、`match={total:1, matched:0, sources:"Spotify", missed:["Where I'm From"]}`，而 `/api/tasks` 全程 0 条 —— 这一首确实走的是音乐那条通道与匹配轮，**没有再被丢进通用队列**，缺陷二改掉。
> - **游标稳不稳**：紧接着再扫一次回 `new=0`、`last_ids` 回到 295 条（被摘掉的那条已按新形状记回）；下载目录 80 项 / 递归 342 个文件、本地索引 108 首，一个字节没多（这一轮没有成品落地，因此不需要挪产物或重扫索引）。
> - **读回时看见的两件事实，都没动手，等用户定**：① 这一首「按曲名没找到」之后**仍然被记成已读**，下一轮不会再试 —— 与「上一批音乐还在跑所以原样不记」那条不同，匹配失败的行等于永久跳过；要不要把没下成的退回未读，是口径问题。② 快列模式那行的 `url` 本来就是网易云自己的歌曲链接，现在的口径是先拿曲名去匹配源找别家（沿用 #27 为 Spotify 这类没有音频地址的清单定的设计），手上这条直链没有先试过；另外本机 `musicdl_strategy.match_sources` 只勾着 Spotify 一家，而这一行只有曲名（歌手与时长都空，打分闸门那两维使不上），没匹配上并不意外。
> - 现场状态：20:31 界面上把新这条订阅的规则存成「每次最多 20 条」（日志「订阅「Space Club/蹦迪必备」规则已更新：每次最多 20 条」），其余规则留空；同一时刻又在「追新与扫描」卡上把它**停用**并关掉了自动下载（`GET /api/subs` 与 `subscriptions.json` 都读到 `enabled=false / auto_download=false`，`new_count` 停在 1），定时扫描因此不会再动它。另外按用户要求删掉了程序目录里那个 0 字节的 `$TEMP` 文件。
>
> 说明八：2026-09-26 这一轮在通用下载链上读回（11:02:24 重启，PID 27400，下面「修复」前两条已在跑的代码里）。按用户要求先清掉 `Downloads\download_archive.txt` 里那 12 行（改前整份备份到 `C:\tmp\md_archive_backup_1102.txt`），再重新实下整个合集 `space.bilibili.com/3707042577516720/lists/9166533?type=season`：
> - **逐集落点成立**：11:03:32 开始，11:12:10 收尾，日志「[2fef29e1] 列表 12 条，本次在下载目录写出 12 个文件；任务记录最后 1 个：【官方中字】尼古喵喵 第12集 [BV1ucaK6UEHR].mkv」—— 12 条对 12 个文件，没有一条是被别人顶掉的。盘上 12 个文件名各带自己那一集的 BV 号（第 1 集 `BV1XDhJ6ZEBn` 到第 12 集 `BV1ucaK6UEHR`），合计 3,120,049,865 字节（2.91 GiB）；`download_archive.txt` 现在正好是那 12 行 `bilibili BV…`，与备份逐行对得上。
> - **旧缺陷的残件已按用户选择删掉**：`合集·【官方中字】尼古喵喵 （全12集） [8a5be301].mkv`，214,588,301 字节，按它自己的标签读出来 title 是「第12集」、PURL 是 `BV1ucaK6UEHR`、时长 1420.1 秒 —— 也就是**第 12 集的标签配着别人那一份的长度**，正是逐集落点没生效时分集互相覆盖留下的产物（它比真正的第 12 集小 66,847,849 字节，却与真正的第 1 集只差 12,698 字节）。删掉后下载目录顶层文件数 68 → 67；11:47 `POST /api/library/scan` 回 `count=137`（删前那一次是 138），扫描结果里尼古喵喵那 12 行逐条在列、`8a5be301` 那条已经没有。
> - **这次读数同时确认还剩一件没做的**：日志在同一秒另有一句「弹幕: 无法解析 cid — …lists/9166533?type=season」—— 合集任务成功后那一步抓弹幕，交给它的是**整表那条链接**，解析不到分集的 cid，所以 12 份 `.danmaku.xml` / `.danmaku.ass` 的时间戳仍是 10:22–10:23 那一批旧文件（这一轮没有重新抓到）。要按集补上弹幕，得把弹幕抓取从任务级挪到逐集那一层；这条本轮没动，等用户定。
> - 同一轮做的猫抓（cat-catch）接入**只做到离线**：`tests/catcatch_test.py` 58 项全绿、`python -m py_compile server.py` 通过，接口与界面都**还没在跑的进程里生效**（PID 27400 是 11:02:24 启动的，早于这批改动），所以 `GET /api/catcatch/status`、模拟 `POST /api/catcatch/push`、配置文件导入与规则增删、以及浏览器里那张新卡的断言，全部欠着，等下一次重启后读回。
>
> 说明九：2026-09-26 这一轮接着把上面欠的读回全部落地，并为「组件与依赖」补了一键更新与按钮对齐。本机今天做过两次重启（前一次是为了让 cat-catch 那批改动进进程，最后一次 **12:34:15、PID 26572**，为了读回下面那条修复），每次重启前后 `/api/tasks` 都是 `running=0 / pending=0`。**读数里查出一个真缺陷**，见下面「修复」最后一条。
> - **cat-catch 接收端逐条线上读回（12:34 那次重启之后）**：`GET /api/catcatch/status` 回 `endpoint="http://127.0.0.1:8765/api/catcatch/push"` 与请求体模板原文；`${action}=addKey` 推一枚 16 字节密钥后 `keys_waiting` 从 0 变 1，推一个不认识的结构则回 `ok:false` 并写明缺什么；配置文件导入回 **`found:4 added:3 invalid:1`**（`invalid` 那条带 Python 原话 `unterminated character set at position 1`，重复那条按设计跳过）；带黑名单命中的地址推回来回 `dropped:1 received:0`，`/api/tasks` 全程 `0 → 0`、新增列表为空；畸形 body（空内容 / 非 JSON / 无 `data`）全部 `ok:false` 且不抛异常；规则「停用 / 启用 / 删除 / 清空」四条改单逐个读回，越界编号回 400 并叫刷新。收尾审计 `app.log`：**base64 原文与 16 进制密钥都没出现过**，只留下「收到 HLS 解密钥 16 字节」这类长度描述。
> - **组件与依赖（Playwright，视口固定 1440×900）**：动作按钮行改成共享 `.btn-grid` 等宽栅格，实测四枚宽度全部 165 px、左边界只有 1057 / 1230 两个值、行间距 8 px、栅格宽 338（卡片可用宽约 340）、没有一枚按钮越出栅格右边界；`pip 可用 · 26.2.1` 与「本次会处理 1 项：cryptg…」各占独立一行，不再挤在按钮行里。确认框宽 420、正文 `[scrollWidth, clientWidth, scrollHeight, clientHeight] = [396, 396, 256, 256]`（内容没有被裁）。点「取消」之后后端 `update_all` 仍是 `running=False total=0 results=0`。
> - **一键更新只走安全路径**：`POST /api/components/update-all` 的未知 key / 空 key / 有效与非法混在一起三种入参都按预期 400 并点名是哪一项，进度只经 `GET /api/components` 带回（不另起查询接口）。**没有真的按下整批更新** —— 表里唯一待处理的那项是本机确实没装的 `cryptg`，装包会改动共享的 Python 环境，这一层留给用户决定（用户随后要求装上，这一步已实际落地，见下面说明十）。
> - **嗅探页那张新卡在浏览器里断言通过**：两格只读输入框的取值分别是推送地址与 `${action}/${data}/${tabId}` 模板原文，「累计接收 / 被规则挡下 / 待用解密钥 / 最近一次」状态行在（读回时为 0 条 / 1 条 / 1 个 / 12:34:41），「清空规则」在无规则时 `disabled=true`，卡内无横向越界元素、页面无脚本错误。
> - 现场状态两件：① 「待用解密钥 1 个」是本轮测试推进内存的一枚假密钥，`_CATCATCH_KEY_TTL` 一小时后自己消失（接收端没有清除接口，也没必要为一次测试加一个）；② `catcatch_rules.json` 与 `history.json` 里那行测试记录都已删掉，测完比对过 `config.json` 一个字节没变。离线自检同时读到最新：`catcatch_test` **62 项**、`components_test` **70 项**（新增 F 段 28 项覆盖一键更新的分派、串行、异常与闸门），两套都是 0 退出码、`FAILED: none`，`py_compile server.py` 通过。
>
> 说明十：接上面「留给用户决定」那一层 —— 用户随后要求装 cryptg，这一步是**真的按下去了**，并且顺带把整表的上游版本查了一遍。
> - **cryptg 走的就是本应用自己的一键更新**：`POST /api/components/update-all`（`keys=["cryptg"]`）19:28:53 提交，回「一键更新已在后台开始（1 项，串行跑，进度见运行日志）」，轮询到 `running=false` 用时 **7.9 秒**，结果 `[{key:"cryptg", ok:true, msg:"https://pypi.tuna.tsinghua.edu.cn/simple"}]`，装后那行读回 `active="0.6.0" ok=true`（装之前是「未安装」）。`app.log` 第 37–42 行整批在案，收尾一句「一键更新结束：完成 1/1 项，全部成功」。这也是这条代码路径第一次真跑通端到端。
> - **telethon 确实用上了它**：新进程里 `from telethon.crypto import aes` 读 `aes.cryptg` —— `telethon 1.45.0 / cryptg_used=true`（探测要在中性目录下跑：站在 `site-packages\telethon\crypto\` 里 `python -c` 会先撞到那儿的 `rsa.py`，报出一个假的 `ImportError: Missing module "rsa"`）。**注意后端是在 telethon 被 import 的那一刻定下来的**，而当前进程是 12:34:15（PID 26572）起的、早于装包，所以正在跑的这份仍走纯 Python 加解密；这条链要吃上 cryptg 要等下一次重启（重启前 `/api/tasks` 已读回 `running=0 / pending=0`，等用户点头）。
> - **整表上游版本查了一遍**（`GET /api/components?latest=1`，6.0 秒，结果缓存 10 分钟）：15 项**全绿**，但有可比上游版本号的是 **13 项** —— ffmpeg 与 N_m3u8DL-RE 那两行的「最新版本」是空的（这张表的上游号只问 pip，那两件走各自发布页下载，`pkg` 字段为空，所以不参与比对）。13 项里 **10 项已是最新**（`faster-whisper 1.2.1`、`yt-dlp 2026.8.19`、`zhconv 1.4.3`、`mutagen 1.48.1`、`edge-tts 7.2.8`、`deep-translator 1.11.4`、`telethon 1.45.0`、`cryptg 0.6.0`、`librosa 1.0.0`，以及 `tools\` 里那个 `ytdlp` —— 它显示为「2026.08.19 (local)」，`verCmp()` 只取第一段数字串逐段比，与上游 `2026.8.19` 判为相同）；**待更新三项**：`musicdl 2.13.11 → 2.14.0`、`python-socks 2.4.3 → 3.1.1`、`numpy 2.4.6 → 2.5.3`。这三项**没有按下去** —— 升的是本机那个共享的 Python 环境（`numpy` 同时被 torch / paddle 与用户自写的脚本用着，`python-socks` 是跨大版本 2→3，动的是 telethon 走 SOCKS 代理那条路），该由用户决定何时升。按前端那口径（`!ok` 或 `latest` 高于 `active`）此刻界面上会写着「本次会处理 3 项」，点下去就是这三项。
> - **全量离线自检**：一次跑完 `tests\` 下 **28 个套件、1415 项全绿、0 失败**，累计 49.0 秒（最长的是 `sse_test` 22.3 秒）；跑完比对过 `web_app\` 顶层文件清单**没有新增文件**。`app.log` 在同一时间窗里涨的那几行是用户自己的界面操作（19:34–19:35 切页、「Space Club/蹦迪必备」订阅规则更新），不是测试写的。另：首轮 `matchgate / spotifylist / telegram_channel` 三套退出码 1 报 `UnicodeEncodeError: 'gbk' codec can't encode character '\u2194'`，那是**子进程 stdout 继承了控制台 GBK**、不是产品回归 —— 加 `PYTHONIOENCODING=utf-8` 重跑即 36 / 77 / 43 项全绿，批量跑的入口脚本已固化这个环境变量。
>
> 说明十一：上面那三项待更新，用户点头后**真的按下去了** —— 过程中撞出一个会打死「音频分析」的坑，在重启之前退回去；出包时又从读数里查出一处不诚实的文案。
> - **整批更新按下（19:45:48）**：`POST /api/components/update-all`（`keys=["musicdl","python-socks","numpy"]`）回「一键更新已在后台开始（3 项，串行跑，进度见运行日志）」，轮询 **24.9 秒**到 `running=false`、`done=3/3`，`results` 三项 `ok:true`（源都是设置里的清华镜像 `https://pypi.tuna.tsinghua.edu.cn/simple`），`app.log` 从「一键更新（1/3）：开始 musicdl…」到「一键更新结束：完成 3/3 项，全部成功」逐条在案。落点：`musicdl 2.13.11 → 2.14.0`、`python-socks 2.4.3 → 3.1.1`、`numpy 2.4.6 → 2.5.3`。
> - **numpy 这一升就把 librosa 打死**：numba 对 numpy 有版本闸门（本机那份 `numba 0.65.0` 的元数据写 `numpy<2.5`，`numba 0.67.0` 才放宽到 `<2.6`），而 librosa 依赖 numba —— 只把 numpy 升到 2.5.3，「语音 → 音频分析」与声纹说话人分离的每次调用都会抛 `ImportError: Numba needs NumPy 2.4 or less. Got NumPy 2.5.`。**这条是在重启之前用探针查出来的**（正在跑的进程还握着旧 numpy，界面上看不出任何异常），所以坏状态没交到用户手上；numba 不在「组件与依赖」这张表里，升它得另走 pip，于是按用户选择把 numpy 退回 2.4.6，重测 librosa 六项全绿（`mfcc` 出 `(20, 130)`、`rms`、`tonnetz`、`beat_track` 92.29 BPM、`onset_strength`、`effects.trim`）。与本轮动手之前的 `pip freeze` 基线（372 行）逐行比，本机净变化只剩 musicdl 与 python-socks 两行。便携包不带 numpy / librosa / numba（出包清单里没这三件），所以这条只在「本机装过老 numba、又只升 numpy」时才踩得到；README「组件与依赖」一节已把这条限制写清。
> - **重启（20:51:49，PID 49972）**：重启前后 `/api/tasks` 都是 `running=0 / pending=0`。新进程读回 `musicdl 2.14.0`、`python-socks 3.1.1`、`numpy 2.4.6`、`cryptg 0.6.0`、`librosa 1.0.0`，整表 15 项全绿；cryptg 这条链到这一步才真接上（`from telethon.crypto import aes` 后 `aes.cryptg` 非空，说明加解密走 cryptg 而非纯 Python —— 后端是 telethon 被 import 那一刻定下来的，所以 19:28 装好之后还得等这一次重启）。
> - **两项幸存的升级各跑了一次真的**：① `POST /api/music/search {"keyword":"Brave Shine"}` 连跑两次，分别回 **60 条**与 **46 条**，行的字段齐全（`title` / `artists` / `duration` / `duration_s` / `url` / `quality` / `cover` / `musicdl_source`），逐源统计 `Migu 20 / Netease 20 / Apple 20 / QQ 0 / Spotify 0`，0 条那两源各带回一句原因（QQ「该源返回 0 条（无匹配、需登录 Cookie 或地区限制）」、Spotify「180s 内没跑完，本次已放弃等待…可以只勾它单独搜」），说明 2.14.0 没有把上一版的逐源预算与报错口径改掉。这个接口在传 `sources` 时会写 `config.json`，探针因此没传该字段，改前改后 md5 同为 `59dba709f7c2c9209dc669eb8fea3ea2`。② python-socks 跨的是大版本（2→3），把 telethon 真正 import 的四个入口逐个试过：`python_socks.ProxyType`、`python_socks.async_.asyncio.Proxy`、`python_socks.sync.Proxy`、`python_socks._errors` 里的 `ProxyError` / `ProxyConnectionError` / `ProxyTimeoutError`。③ librosa 走产品自己的路验：`POST /api/ai/analyze`（截 20 秒）之后 `app.log` 20:53:32 写「[分析] Brave Shine - Aimer.mp3: 252.3s · 112.3 BPM · 调性 D# major · 响度 -16.9 dB」。
> - **读数里查出一处文案不诚实**：那次分析请求传的是 `write_json=false`，接口却回「正在分析: …（结果写日志与 JSON）」—— 不落 JSON 也先承诺落。已改成按参数说话（见下面「修复」最后一条），并在 21:25:57 第二次重启（PID 42360，重启前后 `/api/tasks` 均 `running=0 / pending=0`）之后反向读回两遍：同一份文件传 `write_json=false` 回「（结果写运行日志）」、传 `true` 才回「（结果写运行日志与 JSON）」，且只有后者那一次在边上落出 `Brave Shine - Aimer.analysis.json`（旁路文件就落在成品旁边，测完已删）。新进程同时读回 `musicdl 2.14.0`、`python-socks 3.1.1`、`numpy 2.4.6`、`cryptg 0.6.0`、`librosa 1.0.0`，15 项里没有不绿的。
> - **v1.2.8 便携包**：按用户要求把 cryptg 加进入包清单（新增 `cryptg==0.6.0`），并顺手把 `musicdl` / `python-socks` 的 pin 提到本轮实装的新版。`pack_release.py` 全量跑一次：内嵌 Python 3.12.2 装 14 项依赖 → 包内 import 自检（10 个顶层模块）→ 包内 pip 装-卸自检 → 起包内服务打接口冒烟（`[smoke] 组件接口三档版本齐全，随包清单命中 12 项`）→ 私密文件扫描，全部通过，并清掉 407 个 `__pycache__`。文档随后补了「说明十一」，为让包里的 README / CHANGELOG 与磁盘一致，又用 `--skip-runtime` 重出过（复用装好的 runtime，只重跑复制与那四道自检）。最终产物 `dist\MediaDownloader-1.2.8-portable.zip` **217.6 MB**（包目录 562.3 MB：runtime 322.1、tools 234.5、static 532.0 KB、chromaprint 4.0 MB）。出包后把 zip 摊开逐条读过：`README.md` 与 `CHANGELOG.md` 在、`site-packages` 86 个包里 musicdl / python_socks / cryptg 的 `.dist-info` 就是 2.14.0 / 3.1.1 / 0.6.0、numpy / librosa / numba / faster-whisper 确实没混进来、精确同名的私密与工具文件（`config.json` / `cookies.txt` / `history.json` / `library_cache.json` / `local_music_index*.json` / `music_favorites.json` / `catcatch_rules.json` / `app*.log` / `pack_release.py`）零命中、禁带目录（`local_index` / `Downloads` / `Whisper` / `tg_session` / `browser_sniff_profile`）零命中、`cookies\` 里只有那句占位说明、`.pyc` 零残留；包内 `components_bundled.json` 记 `app 1.2.8`、`python 3.12.2`（`built` 那一项是出包时刻，重出一次就换一个值），工具三件是 `ffmpeg.exe 9.0.1`、`yt-dlp.exe 2026.08.19`、`N_m3u8DL-RE.exe 0.6.0`。老的 `dist\MediaDownloader-2.6.2-portable.zip` 修改时间仍是 09-19 09:44:47，没动。出包前后各跑一次全量离线自检：28 套件 / **1415 项 / 0 失败**（48.4 秒），`py_compile server.py pack_release.py` 通过。（首轮我把汇总行 `FAILURES: none` 当成了失败，报出「24 个套件 BAD」，是判据写错、不是产品回归，换判据后重数即 1415 / 0。）
>
> 说明十二：2026-09-28 这一版源码挂到 GitHub 开源（`https://github.com/QingYan1012/media-downloader-web`，先建的是 private 仓库，20:46 推上首个提交 `e0d1786`），许可证定为 **GPL-3.0-only**，四件事落在这里。
> - **`LICENSE`**：GNU 官网 `gpl-3.0.txt` 原文照抄（674 行 / 35149 字节），不写「见官网」这种要靠网络的话。便携包本身就是一份 GPL 分发，过去却不带许可证全文，所以 `LICENSE` 已加进 `pack_release.py` 的 `APP_FILES`（排在 `CHANGELOG.md` 之后）随包发布 —— 这一改也要重出一次包才算落地。
> - **入库范围用白名单写死**：`.gitignore` 先 `/*` 忽略根目录的一切，再逐项放行 12 个根模块、`static/` `extension/` `plugins/` `tests/` 与七份根文档。暂存区实测 **69 个文件 / 2.71 MB**，最大单文件 `server.py` 667 KB，离 GitHub 单文件 100 MB 的红线很远。本机状态（`config.json`、`cookies/`、`history.json`、`library_cache.json`、`subscriptions.json`、`local_index/`、`app*.log`）、`dist/` 五个包、`tools/` 的四个 exe、`Whisper/` 模型、`pack_cache/`、以及两个写死本机路径的开发用脚本（`start_server_dev.ps1`、`_probe_gen_media.ps1`）都不入库。暂存前对这批文件全量扫过凭据形态（Bot Token、`api_hash`、私钥头、Cookie 值、`AKIA…`、长随机串）：零命中，命中的 `telegram_bot_token` / `aria2_secret` / `wecom_corp_secret` 全是 `""` 默认值和参数名。
> - **README 补三节**：「许可」（GPL-3.0 + 衍生须同源开源）、「免责声明」（只提供图前端，不含绕登录 / 绕付费 / 绕 DRM / 绕风控的能力，合法性由使用者自己确认，凭据只留本机）、「离线自检」（`tests/` 怎么单独跑、只写临时目录）。
> - **写死本机路径的自检脚本改成跟着脚本自身位置走**：`tests/diarize_selftest.py:12`、`tests/diarize_e2e.py:15`、`tests/diarize_final.py:19` 三处由 `r"H:\MediaDownloader_web_v2.2.0\web_app"` 换成 `Path(__file__).resolve().parents[1]`，改前改后各跑一遍那三套，六次全部退出码 0（别人克隆过去不必再把路径抄回本机）。`tests/fixtures/` 那四份是公开页面的快照（三个 `t.me/s/` 频道首页 + 一份抖音话题页头部，合计 356 KB），离线自检靠它们做到全程不联网；扫过确认里面没有邮箱、没有 Cookie，看着像手机号的 11 位数字其实是 Telegram 消息 ID 里的一段。
> - **推完的读回**：`git ls-remote` 与本地 HEAD 是同一个 `e0d1786`，远端 `git ls-tree -r` 数出来正好 69 个文件；不带登录态去访问仓库地址回 404、带上回 200，确认它现在确实是 private。反向验过一次拦截有效：`git add config.json cookies/cookies.txt history.json Downloads app.log` 五个全被 `.gitignore` 挡下（非要 `git add -f` 才进得去，这条路不走）。提交作者用 GitHub 匿名邮箱 `11241476+QingYan1012@users.noreply.github.com`，只在提交命令上带 `-c user.email=`，本机 git 全局配置没动。
>
> 说明十三：转公开之前先把文档做了一轮版式升级，并补出完整英文文档；两件事落在 README，一件事落在出包与仓库。
> - **README 重写为「热门项目」版式**：顶部双名标题 + 七枚静态徽章（GPL-3.0 / v1.2.8 / Python 3.12 / FastAPI / Vue 3 + Element Plus / 数据只落本机 / Windows 与 Docker）+ 一段英文 Overview + 目录，正文原有的技术事实一条没删，只是重新分了节：新增**「下载与获取便携包」**（三种取法对照表：Releases 便携包 / 源码 / Docker，另附「包内已带 · 包内不带（可在程序里现装）」两列对照，以及 218 MB、`启动.bat`、改端口、解压路径避免中文与空格这几条现场规矩）、**「功能一览」**（16 行能力表，每行写做什么与靠什么）、**「已知限制」**（10 行：区间裁剪只认分片流、YouTube 与抖音的 Cookie 墙、Spotify / Apple 没有官方音频通路、音质要求钉不住平台档位、无损参照只到元数据、音乐批量单通道、按曲名没匹配上不自动重试、语音那几项默认不带、界面只有中文）、**「常见问题」**（10 条，全部答的是代码里已有的行为）、**「贡献方式」**（9 步，含「新依赖要三处同步」与「新增顶层模块必须加进 `APP_PY`」这两条会炸的）、**「不在本工具范围内」**、**「鸣谢」**（名单取自 `static/index.html` 的 `CREDITS`，并注明完整名单在「设置 → 鸣谢 / 参考项目」）。音乐那一节按内容拆出 `###` 子标题（打分闸门 / 歌单去重与分片批量 / 跳过已下载与换源 / 本地库与快照 / 音质要求与无损参照 / 收藏清单与命名模板），Telegram 与订阅那两大段原文照搬。
> - **截图位留空、不放图**：新增「界面截图」一节只写占位说明，不贴任何图片链接。原因是截图必然带出本机文件名、下载目录绝对路径与已登录站点，属于本机数据；将来脱敏后进 `docs/screenshots/`，那一节才放图。
> - **英文完整版 `README.en.md`**：不是摘要，与中文版一一对应 —— 打分闸门的全部阈值（60 / 70 / 25 / 50 / 85 与两条快捷判定的容差公式）、6 首一片的归档与中断救回、`dup_skipped` 与「没取到地址」分开、本地索引的 TTL 5 分钟 / `force` 排队 90 秒 / 判重 `ttl=0`、音质要求做得到的三件与做不到的那一件、cat-catch 接收端与「只填 127.0.0.1」、一键更新与 numba 卡 numpy 上限、`/api/*` 全清单、已知限制与贡献方式同样齐。顶部另加一句提醒：**界面目前只有中文**，这份文档解释行为、不等于把界面翻译了。两份 README 之间用顶部语言条互链，README 末尾也各指一次。
> - **数字与清单是核过的，不是抄的**：「16 个页面 / 5 组」按 `static/index.html:4409-4432` 的 `navs` 与 `NAV_GROUPS` 数出来；「包内不带 numpy / librosa / numba / faster-whisper」按 `pack_release.py` 的 `PKGS` 与 `requirements.txt` 逐项对；`tools/` 四件与 `chromaprint/fpcalc.exe` 按包内实际文件；版本号 v1.2.8 来自 `appVersion`（`static/index.html:4492`）。**`tests/fixtures/` 那四份按内容逐份认过**（每份都探 `tgme_channel_info_counter` 这个类名）：三份全是 `t.me/s/` 频道页，第四份是抖音挑战页的头部片段 —— 英文稿初稿写成「两份频道页 + 一份消息页」是错的，已改回「三份频道页 + 一份抖音挑战页头部」，与说明十二里那句「三个 `t.me/s/` 频道首页 + 一份抖音话题页头部」对齐。
> - **随包发布与入库接线**：`pack_release.py` 的 `APP_FILES` 加 `README.en.md`（现 7 项），`.gitignore` 加一行 `!/README.en.md`。文档改完重跑 `python pack_release.py --skip-runtime` 出 v1.2.8 包，包内 `README.md` / `README.en.md` / `CHANGELOG.md` / `LICENSE` 与磁盘 md5 逐字节一致，四道自检（pip 就绪 / tkinter / 包内 pip 真装真卸 / 包内服务冒烟）与私密文件泄漏扫描全过。
> - **便携包挂到仓库 Releases**：tag `v1.2.8`，资产就是上面那只重出的 `MediaDownloader-1.2.8-portable.zip`（约 218 MB，走 Release 资产而不是仓库文件，因此不撞仓库那 100 MB 单文件红线）；README 的「下载与获取便携包」与徽章都指向 `releases/latest`，所以以后每出一版只发一条 Release，文档里的链接不用改。上传前先按包内顶层清单再数一次私密文件，确认零命中。
>
> 说明十四：2026-09-28 两份 README 再改一轮版式，目标是**首屏能扫完、技术细节展开才看**，做法是把长段落折叠而不是删掉，一条事实都没走。
> - **首屏只留四块**：标题 + 徽章 + 两句定位（改了写法，删掉「FastAPI 单文件 + Vue 3 单文件」这类只在开发节才有意义的措辞，换成「粘链接就能下、浏览器里管队列 / 抓 m3u8 / 找歌 / 做字幕 / 追新」与「数据全在程序所在文件夹，不上传」）；紧跟一句「本工具不绕过登录墙、付费墙、DRM 与人机校验，不执行站点 JS、不伪造反爬签名」并链到「不在本工具范围内」；然后是分四组的一行式目录（上手 / 功能 / 开发 / 边界与许可）。
> - **「30 秒上手」把三条路一次写清**：免安装是编号三步（Releases 下 zip → 解压位置的两条规矩 → 双击 `启动.bat` 自动开 `http://127.0.0.1:8765`），源码与 Docker 各一个代码块，`.py` 要重启、`static/index.html` 只要刷新那句留在源码那块下面；末尾把「端口被占用 / 缺组件 / 要会员音质」三种卡点统一指到「常见问题」。原「下载与获取便携包」整节收进新的「便携包里有什么」的折叠块，「启动」一节被首屏取代后取消。
> - **折叠的口径**：17 个 `<details>`，每一节外面只留一句人话概述（说清这节解决什么、哪一步会当场报错），阈值、判定链、缓存 TTL、端点名这类留在 `<summary>` 里当索引。摘要句是新写的，正文一律**原文照搬**：改造用脚本按 `## ` 切节后重新拼装，逐节把旧正文塞进 `<details>`，所以正文与 git 里那份 `HEAD:README.md` 的差异只有首屏与节序，没有段落改写。
> - **顺带查出并修掉的渲染与链接缺陷**：`</details>` 紧跟下一行内容时，CommonMark 会把紧随其后的 `## 标题` 吞进 HTML 块（17 处全中），标题在 GitHub 上变成裸文本 —— 已统一补空行；同一类问题还有 10 处标题前没有空行。锚点两处失效：`#启动`（3 处）与 `#下载与获取便携包`（1 处），分别改指 `#30-秒上手` 与 `#便携包里有什么`；英文侧对应 `#running-from-source`、`#getting-the-portable-package`。校验项：`<details>` / `</details>` 各 17、代码围栏 6 行成对、`## ` 标题 30 个且全部前面有空行、站内锚点零死链。
> - **英文版与中文树一一对应**：同样的首屏四块、同样的 17 个折叠、同样的节序（Features / The 16 pages / Screenshots 可见，Download & queue … Contributing 折叠）。改动过程中一度把「The sidebar has 16 pages in 5 groups:」与「The app then serves …」两句挤掉，已按行数差异查出来补回，其余正文保持原样。
> - **随包文档暂时落后于仓库**：这一轮只动 `README.md` 与 `README.en.md`，按用户决定**没有重出 v1.2.8 便携包**，所以包内那两份仍是说明十三的版本；下次真出版时文档会一并带上，出包后仍需按老规矩核包内文档 md5 与磁盘一致。
>
> 说明十五：2026-09-29 按用户要求把说明十四那轮文档**重进了包里** —— 版本号不变仍是 v1.2.8，`python pack_release.py --skip-runtime` 重出 `dist\MediaDownloader-1.2.8-portable.zip`，上一条末尾那句「包内文档仍是说明十三的版本」到此为止。现在包内 `README.md` / `README.en.md` / `CHANGELOG.md` / `LICENSE` 与磁盘 md5 逐字节一致（本条说明十五是出包之前写进 CHANGELOG 的，所以包里那份也带着它）。四道自检（内嵌 pip 就绪 / tkinter 在位 / 包内 pip 真装真卸 / 包内服务冒烟）与私密文件泄漏扫描逐条过；冒烟走 8791 端口，不撞本机在跑的 8765，试跑落下的 `config.json`、按天运行日志、`Downloads\`、`local_index\`、`__pycache__` 仍按老规矩在压缩前就地删净。仓库侧本轮只提交 `README.md` / `README.en.md` / `CHANGELOG.md` 三份文档，代码一行没动。
>
> 说明十六：2026-09-29 两份 README 补上真实界面截图，占位段作废。版式参照了一个开源项目页的写法（首屏一张居中大图 + 一句话描述式的 `alt`、徽章行、图片进仓库目录用相对路径引），内容全部换成本工具自己的界面。
> - **截图来自一份隔离实例，不是本机那份**：把已出的 `MediaDownloader-1.2.8-portable.zip` 解到 `C:\tmp\MediaDownloader-1.2.8-portable`，用 `MEDIADOWNLOADER_PORT=8793` 起一份全新实例 —— 程序的读写目录锚在它自己所在的文件夹（`APP_DIR = Path(__file__).resolve().parent`），所以这份副本里没有下载历史、没有 Cookie、没有订阅源，保存目录是包内默认值。取图用 Playwright 无头 Chromium，1920×1080 视口，按当前页可见的 `.content .card` 包围盒裁掉多余空白；深色那两张由点顶栏的月亮按钮得到。
> - **入库 6 张，共 0.81 MB**（`docs/screenshots/`）：`home-light.png`、`home-dark.png`、`music-search.png`、`aggregate-search.png`、`telegram-channel.png`、`subscriptions.png`。**设置页与嗅探页被排除**：那两页必然带出本机代理端口与已登录站点名，不属于能公开的画面。每张发布前都用人眼读过一遍。
> - **README 侧改动**：删掉「截图位（暂未上传）」/「Screenshot slot (deliberately empty)」两处占位，换成先声明「下面每一张都取自新解压、没用过的实例」，再接 2×2 图组（音乐搜索 / 聚合搜索 / Telegram 频道批量 / 订阅追踪）+ 深色模式一张；首屏徽章行下方加 `home-light.png` 作 hero。中英两份结构与图片一致，`alt` 各写成一句完整描述。
> - **顺带修掉的文档缺陷**：英文版新加的两处内链写成 `#page-overview`、`#ui-themes`，而实际标题是 `The 16 pages` 与 `Themes`，已改为 `#the-16-pages`、`#themes`；校验脚本复查两份 `## ` 标题生成的锚点，站内锚点零死链，`<img>` 各 6 个、指向的文件全部存在、`alt` 无空或过短。
> - **出包接线**：`.gitignore` 是默认拒绝式白名单，加了 `!/docs/` 才让截图进得了仓库；`pack_release.py` 的 `APP_DIRS` 加 `docs/screenshots`（现 4 项），`.png` 不在排除正则里，所以**这一版包会把图一起带进包**（包内 README 的相对链接才指得到）。
> - **随即重出包并换掉 Release 资产**（按用户确认，版本号仍是 v1.2.8）：`python pack_release.py --skip-runtime` 重出 `dist\MediaDownloader-1.2.8-portable.zip`，包内多出 `docs\screenshots\` 六张图；本条说明十六是出包之前写进 CHANGELOG 的，所以包里那份也带着它。Release `v1.2.8` 的资产走「先传临时名 → 轮询到 `uploaded` 并核对大小与 sha256 → 删旧资产 → 改名」的顺序，中间没有任何一刻 Release 没有可下载的包。

### 功能

- **同曲判定改成打分闸门**：过去「搜索结果里这一条是不是歌单上那一首」用的是「曲名归一后相等 + 时长在容差内」这一条快捷判定，两个缺陷同时存在 —— 曲名稍有出入（平台加了后缀、换了括号写法）就整个认不出，而认得出的那种也不看歌手，华语同名翻唱一抓一把。现在 `music_search.track_score()` 把曲名、歌手、时长**分开打分**再过硬阈值：`MATCH_NAME_MIN=60`（低于它就是两首歌）、`MATCH_ARTIST_MIN=70`（歌手这一维最值钱）、`MATCH_TIME_MIN=25`（约等于差 14 秒）、`MATCH_TIME_SOFT=50`（曲名不完全相同时要求约 7 秒以内）、录取线 `MATCH_ACCEPT=85`，综合分取曲名分与歌手分的均值 —— **时长只当闸门、不参与加分**，因为两首不同的歌恰好同长太常见，让它加分会把不像的抬进来。两条老的快捷判定保留（歌手写法常不同，收紧成纯打分把它们都判丢过）：曲名+歌手归一后完全相同且时长在容差内给 100，同名而歌手不同但相差不到 5 秒给 96。取回来的成品**标了版本词而歌单那行没标**的（成品是 `(Live)` / `DJ` / `伴奏` 而标注要录音室版）单独硬挡；反方向不挡 —— 歌单标了 Live 而曲库这条省了后缀，多半就是同一条录音，那种挡下来只会让用户下不到歌。多条候选都过线时按 `(分数, 音质)` 取最高，音质档由 `_quality_score()` 给（flac / ape / wav 100 > 320k / hires 80 > 192k / m4a / aac 50 > 128k / mp3 30 > ogg 20），所以同一首有损与无损并存时取无损。落点：跨平台按曲名匹配（`_resolve_placeholder` → `_pick_track_match`）、歌单去重（`merge_duplicate_tracks`）、目录判重（`find_existing_local_songs`）三处全部走这一个函数。离线自检 `tests/matchgate_test.py` 36 项盯判定本身，反向验证做了「把相似度算法退回全等，同一份繁体数据必须匹配不上」与「关掉版本词识别，现场版就会被判成同一首」。
- **本地音乐读出文件自带的真元数据**：「包含本地库」这一路过去只按文件名猜（`歌手 - 曲名.mp3` 拆两段），于是内嵌标签里写着专辑、时长、位深的成品在界面上只有一行曲名，`X.flac` 与 `X.mp3` 看起来一模一样。现在 `audio_file_meta()` 一次解析把 mutagen 能给的都拿走（标题 / 歌手 / 专辑 / 时长 / 码率 / 采样率 / 位深 / 内嵌封面 / 内嵌歌词 / 标签类型），**只有位深这类它给不出的才问 ffprobe**，两者都拿不到就返回空字段让文件名继续兜底，并把来源记在 `reader`（`mutagen` / `ffprobe` / `mutagen+ffprobe`）—— 界面上一行是标签给的还是文件名猜的，从此分得开（行上的 `tagged` 就是这个标记）。缓存按 `路径|字节数|修改时间` 三元组建键（`_LOCAL_META_CACHE`），文件没动过就不会重复解析；整份本地索引落盘成快照，重启后 `_warm_meta_cache()` 把「没动过」的行整批灌回内存，本轮只需要解析新出现的那些（快照的位置与刷新策略见下一条）。无损的判定与 `quality` 文案（`flac 24bit`）也在这里算出来。注意内嵌封面与歌词的取法：同文件旁边那份 `.jpg` / `.lrc` 也算，两样都有时以内嵌为准。离线自检 45 项。
- **本地索引改成带 TTL 的快照：搜索秒开、重扫进后台、索引搬家**：上一条只省下了「解析」，每搜一次还是要整目录遍历一遍并读文件状态，几百首就够把搜索拖成肉眼可见的等待；而整份索引当时还写在**用户的下载目录**里。现在读本地库统一走 `local_music_snapshot()`：内存一份、磁盘一份的两级快照，落点是程序目录 `local_index\`，文件名是按被扫描目录路径算出的哈希（`local_music_index_<16位>.json`），所以同时索引几个下载目录不会互相覆盖，用户的下载目录里不再落任何东西；升级前那份 `local_music_index.json` 在第一次读到时整只搬进程序目录并删掉原件，老记录照样拿来回填缓存。默认只认 5 分钟之内的快照（`LOCAL_INDEX_TTL_S = 300`）：命中就直接给结果，连目录都不打开；**快照过期时先把上次那份立刻返回**（界面上永远是秒开），同时把重扫丢给后台线程，跑完落盘、下一次查询即拿到新内容。后台重扫按目录单飞（`_LOCAL_SCANNING` 一个集合 + 一把锁），六个并发请求只会扫一遍，不同目录之间照旧并行。两个入口刻意绕开这层缓存：**「扫描本地库」按钮传 `force=True`**（这个按钮的语义就是「现在重扫」，吃快照会让人以为它坏了，弹窗末尾另写索引文件在哪）；**「跳过已下载」的判重传 `ttl=0`**（刚下完的那首绝不能被旧快照遮住，否则隔天又下一份 `曲名_1` 副本），整批下载收尾时再 `refresh_local_snapshot()` 后台刷一次。首轮线上实测（本机 108 首的下载目录）暴露出三处对上口径不对的地方，一并改掉：① 搬家只搬内容不搬时间，那份一小时前的老索引落到程序目录后顶着一个新 mtime，TTL 再也判不出它旧 —— **过期先回旧内容 + 后台重扫这条路因此永远走不到**，现在 `_migrate_legacy_index()` 用 `os.utime()` 把旧文件的修改时间一起带过去；② `force` 那一条路完全不读快照，也就顺带漏了搬家，老文件会一直留在用户的下载目录里，现在 `_scan_and_save()` 自己先搬一次；③ 后台正在重扫时按「扫描本地库」，`force` 撞上单飞锁就直接退回旧索引，界面数字没变、像是按钮坏了 —— 现在 `force` 并进去等那一次扫完（`_LOCAL_SCAN_JOIN_S = 90` 秒封顶，超时才退回上次那份），而普通读和 `ttl=0` 的判重照旧绝不排队，界面永远不等扫描。`local_index/` 记的是本机文件的真实路径，已进出包排除表，试跑阶段也会就地删掉。离线自检 `tests/indexsnap_test.py` 43 项，反向对照各盯一个「绿了也不代表生效」的坑：删掉内存与磁盘两份快照必须重扫（证明 TTL 的 0 次是真命中）、掐掉索引回填时整目录重解析（证明回填不是空话）、同一时刻按默认 TTL 查是 0 次（证明判重那 5 首确实是 `ttl=0` 换来的）、两个不同目录并行各扫各的（证明单飞不是把一切都串行化的假象）、把搬家后的时间改回「现在」就一次都不重扫（证明后台那次重扫确实是保留旧时间换来的）、扫描桩子换成不读旧索引的实现后老文件必须消失（证明下载目录干净靠的是 `_scan_and_save` 这一手，而不是扫描顺手读到的）、以及不接 `join_wait` 时 `force` 拿到的仍是旧的 1 首（证明「等那一次」不是线程启动抢跑出来的巧合）。
- **「跳过已下载」改用打分闸门，并给出「换源」**：上一条的元数据能力先补齐，判重才换得动口径 —— 「目录里已经有这一首」过去比的是**文件名**（用命名模板算出目标路径再看同名文件在不在），这在两种情况下形同虚设：同一首歌在不同平台收录时文件名写法不同（歌手分隔符、扩展名），以及改了命名模板之后老成品整体对不上号，结果就是隔几天再下一份、盘上多出 `曲名_1.mp3`。现在 `find_existing_local_songs()` 扫一遍下载目录里所有音频（`.mp3 .flac .m4a .aac .ogg .wav .opus .webm`，扩展名不同也算同一首），拿曲名 / 歌手 / 时长跟这一单要下的歌逐条过打分闸门，命中的行在建后台任务之前就从清单里摘掉，日志整份列出是哪几首并带上分数。这里传 `require_artist=True`：目录里同名不同人多半真是两版录音（原版与翻唱），不能只看曲名相同、时长差不多就认同一首；跨平台找歌时仍按默认口径，歌手写法常不同。两个判不了的情况专门处理掉：没标签的行，曲名是按文件名猜的，而下载器默认模板是「曲名 - 歌手」、文件名兜底却按「歌手 - 曲名」拆，方向正好相反，所以对调再投一份候选（带标签的行方向可信，不翻倍）；整目录逐条跑相似度会把这个判断拖成十几秒，所以两侧都有时长时先按时长把候选池削一遍。另一件是**换源**：某一行在 A 平台取到的地址下不动、或者只想换一家拿无损，过去只能整单重下、还会被上面的判重跳过。现在行内有「换源」、批量勾选后有「换源选中项」，后端 `POST /api/music/switch_source` 到「匹配源」里除当前平台之外的其他平台重新找同一首歌，**只有过打分闸门、并且新地址探测得到结果的才改写清单**（探不到地址就维持原样），换不成在日志和界面上写明是被曲名、歌手还是时长挡的，未成功的曲目结束时整份列一次。本地扫描出来的行（`local:` 前缀）与无损参照行（`ref:`）当场拒掉并说明原因：前者本来就是磁盘上的成品、后者只有元数据，两者都没有「换一条来路」这回事。离线自检 `switchsource` 40 项 + `matchround` O 段。
- **音乐歌单接入订阅追新**：订阅页过去只认 RSS、网页与 Telegram 频道三类源，一张会持续加歌的网易云 / QQ 歌单没法盯。现在粘贴歌单链接即可识别为「音乐歌单」类型（`_is_music_playlist()` 按 musicdl 的域名表判，没装 musicdl 时判不了就当不是，不炸），每轮扫描用 `parse_playlist()` 取一次整单，新增曲目走既有的按条规则（时长区间、标题必含与排除词、单次最多入队条数），下完进普通下载链。三处是这条能力的关键：**游标不能用行上的缓存 id**（每次解析都会另铸一个 uuid，那样每轮都会把整张歌单当成新增），所以按「曲名 + 歌手 + 时长」拼稳定键 `mus:曲名|歌手|秒`，同一首歌换个平台收录也不会重复下；而**快列模式（yt-dlp 只列曲目）那一路常常只给曲名** —— 网易云这类平台不给歌手也不给时长，键就退化成曲名本身，一张歌单里两首同名不同曲并成一条、后一首当成已读永远下不到，所以此时（且只在此时、且该行拿得到链接）在键尾补一段 12 位链接哈希，歌手或时长任一还在时键的形状一分不动（否则已有订阅的游标整体挪一遍，隔日重下一张歌单）；**只列了曲名的行不能丢进通用队列**（那种行没有音频地址，把歌页链接交给 yt-dlp 去抽对音乐平台从来就不稳），`_music_sub_entries()` 给这类行当场铸一个槽位并写入 `needs_match` 占位，让它走已有的「按曲名匹配」那一轮取地址，行上本来就带缓存 id 的原样透传；**窗口要装得下整单**（`MUSIC_SUB_WINDOW = 300`，每轮看 300 条、游标也存 300 条，与 `parse_playlist` 的取数上限对齐 —— 歌单里的歌不能因为窗口太窄被永久漏掉，游标比窗口短又会把截掉的条目下一轮当成新增）；**音乐批量只有一条通道**，`_MUSIC_JOB` 还在跑时这一轮的新歌**原样不记已读**，日志写明「这次不记录新增，等下轮扫描再补」，否则会吞掉没人补下的歌。回填历史时这一类源没有日期可用（平台不给单曲发布时间），所以不填日期窗时就按「整张歌单」说话，不假装成「窗口内」。平台不报歌单名时用兜底标题「网易云歌单 8123456789」，比一串 URL 好认。离线自检 100 项。
- **网易云扫码登录 + 三个平台的独立 Cookie**：网易云这个源不带登录 Cookie 时 musicdl 只会去够免费那一档，而界面上唯一的入口是「粘贴一长串 Cookie」，多数人不会从开发者工具里掏。现在设置 → 「音乐平台登录 Cookie」里网易云那一格有「扫码获取」，走的是**网易云自己的登录二维码**（`api/login/qrcode/unikey` 取 key → 手机 App 扫码确认 → `client/login` 轮询返回码），确认后把会话里的 Cookie 收进这一格，界面上写「扫码登录于 时间，已含字段 …」，二维码有效期到了会直接叫用户重新生成而不是拿旧 key 去敲门；网络抖一下不判死，留着 key 让用户再点一次「检查扫码状态」。QQ 音乐与酷狗**没有做扫码**：那两家的二维码登录接口要带风控签名，做出签名绕过就越界了，所以这两格仍是粘贴 Cookie，但补上了过去缺的一半信息 —— 每个平台各自声明「怎样才算真登录上」的必需键（网易云 `MUSIC_U`；QQ `qqmusic_key`/`musickey` + `uin`/`musicid`；酷狗 `token` + `userid`，同组任一命中即可），界面按这一格实际有哪些键显示三态「已登录 / 缺关键字段 / 未配置」，缺哪个直接点名（「缺 token 或 userid，这个源拿不到会员音质」），过去是填了一串没用的键也一律显示成已配置。三条 Cookie 与全局那一条合并成一条交给 musicdl（各源只挑自己认的键，多余的键那个平台会直接忽略），界面临时粘贴的那串只覆盖同名键，一次临时粘贴不该把设置页存好的平台登录整个挤掉。Cookie 值只进本机 `config.json`，日志只写键名个数，不进分享包。离线自检 82 项。
- **自建音乐收藏清单**：跨平台找歌时真正想要的往往是「先攒一单，回头一起下」—— 网易云有这首但音质差、QQ 那首音质好、还有一首要到酷狗找。现在搜索结果行内有「收藏」，攒出来的清单可以整单下载、逐行或批量换源，上次没找到的那几首也会被记住。清单存本机 `music_favorites.json`（已在出包排除表里），行按「曲名 + 歌手 + 时长」算稳定 id，所以同一首歌不会存两遍；每行另配一个缓存槽位（slot）：同一轮搜索里加进来的歌，槽位里就住着那条真结果，整单下载原样下即可；槽位空了（服务重启过、或被 500 条上限挤掉）就在下载时立一个「只有曲名」的占位，交给已有的匹配轮按曲名重新取址，取不到的标成失效。失效区分两种原因并各自给办法：`missing` 是「在匹配源里按曲名没找到同一首歌 —— 换个源、或先补上该平台登录再下这一单」，`unsearched` 是「整轮匹配超时，这一首这轮没轮到搜（不是没找到），再下一遍即可」。界面提示语明确写了「无损参照和本地成品收不进收藏清单：这一单要能整单下」，只有曲名、还要重新找地址的行也不给换源（提示先下这一次）。五个接口：`GET/POST /api/music/favorites`、`/favorites/remove`、`/favorites/download`、`/favorites/mark`。离线自检 83 项。
- **命名模板加了 Emby / Jellyfin 那四个字段**：媒体库按目录读曲（`/{专辑}/{年份}/{序号} - {曲名}`），而过去「文件名模板」只有 `{name} {artist} {album} {source} {id} {ext}`，归档出来的目录少一层年份、文件名开头没有曲目号，或者序号不补零被排成 `1、10、11、2`。现在加了 `{track}` 曲目序号、`{disc}` 碟片号、`{year}` 年份、`{date}` 发布日（模板提示里给了例 `{artist}/{album}/{year}/{track} - {name}`），四件事都是围着「取不到值时必须安静」做的：**序号先从平台原始返回里挖**（各平台键名各写各的，网易云把发布日期塞在 `album.publishTime` 的毫秒时间戳里、QQ 把曲目号写在条目自己的 `trackNumber` 上，所以挖键名要连原始 JSON 一起挖，且值是 `0` 或空串一律当没有 —— 平台常拿 0 占位）；**挖不到就按这一行在歌单里的第几首盖号**（`stamp_track_index()` 在解析收尾统一盖，行上自己有序号的不覆盖，因为平台的号比列表位置可信；合并重复曲目之后再跑一次不跳号）；批量下载时清单被去重和「跳过已下载」剔过一部分行之后的下标已经不是用户看到的第几首，所以在剔之前先把原始位置记下来兜底；**渲染端不落下空层也不写 `unknown`**：取不到值的目录段整段消失，行首行尾孤零零的连接符（`- 晴天` / `03 - `）削掉，打错的占位符（`{track_no}`）宁可丢掉也绝不变成文件名里的花括号，整条模板都空时退回曲名，日期接受 ISO / 点分 / `2005年1月1日` / 紧凑 8 位 / 秒与毫秒时间戳，认不出来就留空、绝不写出 `1104-53-76` 这种怪目录名，序号补零只用一处实现（个位补成两位、三位以上按三位，跨年合辑会超过 99）。离线自检 62 项。
- **Qobuz / Tidal 的无损参照行（只借它查，不借它下）**：本平台搜索结果最缺的是「这首歌到底该多长、有没有无损、是不是这个 ISRC」，而 musicdl 的 Qobuz / Tidal 源要 `X-User-Auth-Token`，没账号就是 0 条。现在勾选「无损参照」（默认关，每次搜索附带查一次）会去取 Qobuz / Tidal 官方曲库的元数据：曲名、歌手、专辑、精确时长、ISRC、位深与采样率、是否无损、官方链接，与本平台结果同屏列出，用来核对找没找对歌。那条**只到元数据为止**：那一站的音频那一步锁在 `/prepare` + Cloudflare 人机校验后面，那是人家有意设的门槛，所以不取令牌、不绕校验、不碰任何凭据，参照行统一带 `reference_only` 与 `ref:` 前缀 id，进不了下载和匹配链路。界面上这一行也一眼认得出来：来源列写「Qobuz·参照」，鼠标停留列出 ISRC、位深/采样率、精确时长、版本标注、发行日与厂牌，末尾固定一句「只读，音频不从这一行下」，操作列不是下载而是「官方页面」（只打开平台给的官方链接）。同一指纹（曲名 + 歌手）本平台已经有结果时不重复列。离线自检 28 项，含「查询失败时不许影响本平台那批结果」这条反向验证。
- **音质要求：挑候选、按勾选拦下不达标、下完逐首核对**：「指定下载 24bit / 无损」这件事在这一层**钉不住** —— musicdl 各平台的音质档是它自己源类里写死的常量，建客户端时能传的参数只有搜索条数、重试次数、工作目录与 Cookie，没有任何一个入口能钉住档位。所以这里不假装能钉，把「音质要求」落在三件真做得到的事上。界面「并行策略」一行新增四个下拉（格式 不限 / 仅无损 / MP3 / M4A、位深、采样率、码率）与「不达标不下」勾选：① 同一首歌在多个平台都有结果时，档位达标的那条排到前面（沿用打分闸门里那一份 `_quality_score()` 档位分，不另立口径）；② 勾上「不达标不下」后，**平台自报的档位确认低于要求**的整首不递交，日志点名是哪一首、差在哪一维（`song_spec_facts()` 读 `SongInfo` 的 `ext` / `bitrate` / `samplerate` 与平台自报的 `raw_data["quality"]`；musicdl 的 `bitrate` 单位是 bps，界面按 kbps 说话，这里换算，否则会判出「320kbps 低于要求 320k 以上」这种反话）；③ 成品落盘后读**它自己的标签**核一遍实际档位（`check_quality()`），平台标注骗人 —— 挂着 flac 的名下回来个 128k 的 MP3 —— 也照样核出来，结论并到那一行「已下载」日志上，结束时再整份列一次。两条口径是这条功能的关键：**「读不出来」永远不等于「不达标」**，缺哪一维就不拿那一维卡人，只报「这一维没核到」（否则所有没自报档位的源会被「仅无损」全部跳过，那是拿「不知道」当「不合格」用）；**无损不看码率**，16bit/44.1kHz 的 flac 本来就在 900kbps 以上，而平台常不给无损文件报码率，按码率卡它只会把最好的那一档判成不达标。勾了「无损参照」时，每条可下载的结果与每份成品还会跟 Qobuz / Tidal 曲库那一行比一比（`ref_compare()`）—— 只比位深 / 采样率 / 是否无损，音频一个字都不取（那一站的音频锁在对方有意设的人机校验后面）；这一步先过**同一道打分闸门**，参照里那条时长对不上的，结论是「没有可比对的参照」而不是「低于参照」，因为那是两版录音、不是音质差，结论里附上参照那条的 ISRC 便于用户自己去官方页面对。档位清单只写在后端一处（`QUALITY_*_OPTIONS`），界面从 `GET /api/music/status` 带回的 `quality_options` 渲染，改档位不会两处不一致。新接口 `POST /api/music/check_quality` 读的是磁盘上的成品，所以只接受下载目录之内的路径，混进一个越界路径就整批拒掉并说明目录在哪。离线自检 `tests/qualityspec_test.py` 63 项，含两条反向验证：把逐维核对换成「永远合格」后同一首 MP3 就真的被下出去（证明拦它靠的就是这一步）、以及不填要求时既不拦也不产生任何音质日志（老行为零改动）。
- **成品的真实来路上屏，另有「拦搬运版」开关**：标着 Spotify 的成品其实是从 YouTube 抽回来的 —— 这件事过去只在日志深处，界面上的来源列写的还是用户点开的平台。现在每条结果带 `real_source`（`Spotify → YouTube`、`Spotify → spotsaver` 这类完整链路）与「非官方」标记，下载日志写的也是这条真实来路。同时新增「拦搬运版」勾选（`music_block_reupload`，**默认关**）：打开后，取回来的成品与用户点开的那一行对不上（曲名 / 歌手不同，或时长差超过 3 秒）就不下，当场记日志并在结束时列清单。这里刻意划清了界线：它**不拦「经转链站从 YouTube 取回」这件事本身**，因为 Spotify / Apple 压根没有官方音频通路，拦掉这一条等于整张歌单下不到歌；只有元数据对不上（也就是另一版录音的搬运版）才守得住，界面提示与开关说明里都写明了这一点。离线自检 `origin` 21 项。
- **接收猫抓（cat-catch）的「发送数据」，含它的 HLS 解密钥**：浏览器扩展页里那套自带嗅探只能送到它自己的界面，而猫抓（`xifangczy/cat-catch`，GPL-3.0）多一个入口 —— 「设置 → 发送数据」可以把嗅到的地址按模板 POST 到指定 URL。现在本机就是它的接收端：`POST /api/catcatch/push` 收 `{"action":"${action}","data":${data},"tabId":"${tabId}"}` 这个模板，把条目直接建进下载队列。方向只做这一趟是有原因的：读了一下它的源码与清单，猫抓没有对外 API、没有本机 HTTP 服务，manifest 里也没有 `externally_connectable`，**从这边伸手去拉它的 `getData` 这条路根本不成立**，所以不猜、不做注入，只把它自己文档里写的推送口接下来（它文档同时警告「数据发送功能测试中，不同版本 JSON 结构会有差异」，因此 `data` 的形状一律不假设：`_catcatch_items()` 对对象 / 数组 / 字符串化 JSON / 裸 http 链接四种形状都收，逐条抽 `url` 或 `link`，认不出的条目静默跳过而不是整批报错）。入队不另写一套分派 —— 原来 `/api/sniff/download` 的函数体抽成 `_sniff_enqueue()`（HLS 走专用引擎 `N_m3u8DL-RE`、B 站 m4s 走音视频合并、其余走通用队列），猫推来的地址和扩展页自己嗅到的一样处理，并固定带上 `skip_plugins=True`（推来的已是真实媒体地址，再让插件解析一遍只会把它改坏）。请求头里带的 `referer` / `cookie` / `userAgent` 分别接到既有的任务级覆盖（`http_headers` 那一条链），扩展名标注规则命中时会写在日志里（只作说明，不参与分派）。**密钥这一条是新能力**：猫抓「抓取密钥」推来的 `${action}=addKey`，`_hls_key_to_hex()` 把 base64 串（有时是字节数组）统一换成 16 进制，按 `tabId` 存一小时（`_CATCATCH_KEY_TTL = 3600`），同一标签页随后推来的 m3u8 自动带上 `hls_key` —— 这个键又新增进任务级覆盖表，并透传到 `download_hls_with_engine()`：`N_m3u8DL-RE` 走 `--key`，回退 ffmpeg 时走 `-decryption_key`（放在 `-i` 之前才生效）。**没做也刻意不做的是绕过任何站点的内容保护**：这里只把用户自己已经抓到的密钥交给解码器，不抓密钥、不破人机校验。隐私上：密钥与 Cookie 的内容**都不进日志**，只写「收到 HLS 解密钥 N 字节」「带 Cookie（N 字）」；`GET /api/catcatch/status` 也只回端点、模板、规则与计数，绝不回密钥。离线自检 `tests/catcatch_test.py` 的 A / B / F / G / H 段（含两条反向验证：密钥超过 1 小时后推来的 m3u8 必须**不带**密钥，证明靠的是那段 TTL 判断而不是缓存里恰好有；非 HLS 地址永远拿不到密钥）。**这批改动已在 12:34:15 重启（PID 26572）后线上读回**（端点、模板、`addKey`、规则增删与浏览器里那张新卡，见上面说明九），离线自检同时从 58 项扩到 62 项 —— 新增的 4 项是说明九里那个缺陷的回归。
- **猫抓的正则规则可以整份导进来**：猫抓「设置 → 正则规则」那套黑白名单（`{type, regex, ext, blackList, state}`）决定它自己嗅不嗅某条地址，用户已经调好的那份规则没必要在这边重抄一遍。现在「导入猫抓配置文件」吃它「设置 → 导入/导出配置」导出的 `cat-catch-版本-日期.txt`（整份 chrome.storage 的 JSON），`_collect_regex_rules()` 递归找带 `regex` 字段的对象（深度上限 6，连**字符串化的那层嵌套 JSON** 也会解开再找，因为存储键名各版本不一样，所以不猜键名只认形状），逐条过 `re.compile`：编译不过的收进 `invalid` 并带 Python 原话报错（例如 `unterminated character set at position 1`），`(正则, 黑白名单)` 已存在的不重复导入，`state` 是 `0` / `false` / `off` 的按停用收下（停用不等于删除，用户回来还得能开）。规则存本机 `catcatch_rules.json`，判定在 `_catcatch_match()`：黑名单一命中就挡（**优先于一切标注**），停用的不参与，命中的标注扩展名只用于日志与界面显示；一条规则都没有时一律放行（不装规则不该改变行为）。规则的管理走 `GET /api/catcatch/status` 带回清单，`POST /api/catcatch/rules/toggle` / `/rules/delete` / `/rules/clear` 三条改单（都按当前索引改并回整份清单，越界编号当场 400 并叫用户刷新，避免两个窗口互相踩）。`catcatch_rules.json` 是个人配置，已进出包排除表（`pack_release.py` 的 `EXCLUDE_FILE_RE`），试跑阶段也会就地删掉。离线自检 `catcatch_test` 的 C / D / E / I 段共 28 项（本轮为「修复」最后一条新增 4 项回归：C4–C6 钉规则形状、D9 钉整条导入链），含「空 body / 非 JSON / JSON 但不是对象 / 少了 `data` / `data` 里没有链接」五种畸形请求全部回 `ok:false` 且不抛异常，以及「带查询串时行尾锚 `$` 不命中」这条与猫抓按原文 `re.search` 一致的口径（要挡带参数的地址得写 `\.mp4`，别写 `\.mp4$`）。这一条也是**线上读回时查出真缺陷的那一处**，见下面「修复」最后一条。
- **组件与依赖「一键更新」**：这张卡过去只能一行一行点 —— 缺 FFmpeg 点 FFmpeg 那行的「安装」，少 `zhconv` 再点另一行的「安装」，一次补齐五六样要点五六回，每次还得自己看清楚哪几项没就绪。现在卡顶多一枚「一键更新」，把整批挑出来按顺序跑完。**待处理 = 没装上的 + 点过「查询上游最新版本」且确实有新版的**，所以没查过版本时它只补缺的、绝不假装知道最新版（界面上那行「本次会处理 N 项」把选中的每一样当场念出来，点下去之前就能看见要动谁）。按下先弹逐项清单（`安装 X（当前：未安装）` / `更新 Y：a → b`），并写明「按上表顺序一项一项进行，期间请勿关闭程序」、工具走「网络与并发」里的 GitHub 镜像、Python 依赖走 pip 镜像，以及含 faster-whisper 时会连同模型一起下、可能占数百 MB。后端 `POST /api/components/update-all` 收 `keys` 数组与可选 `mirror`，全机同一时刻只允许一批（`_COMP_ALL` + `_COMP_ALL_LOCK`），批内**严格串行** —— pip 同时装两个包会互相踩，工具那边也是下载与覆盖同名文件。每项成功与否按各自更新函数自己的口径判（工具比版本号、Python 依赖看 pip 自己的返回），一项抛异常只把这一项记成失败并接着跑下一项，`finally` 一定清掉 `running`（否则一次异常会把这枚按钮永久锁死）。进度**不另起查询接口**：`GET /api/components` 多带一份 `update_all`（`running / total / done / current / started / results`），界面据此每 5 秒轮一次、跑完自己停掉轮询并刷新状态；带回的是副本而不是内部字典本身（否则界面能读到正被改到一半的状态）。闸门三件：`keys` 里有不认识的项、整批为空、有效项与非法项混在一起 —— 全部当场 400 并点名是哪一项，不静默丢掉一半；已有批次在跑时回 `{ok:false, message:"已经有一批更新在跑…"}` 而不是排队等。离线自检 `tests/components_test.py` F 段 28 项：逐键分派与各自己的成功口径、并发计数（三个线程进去只能观测到 1 个在跑，**外加一条反向对照：真用三个线程并发跑就必须测出大于 1**，证明这条断言有牙而不是恒真）、顺序照用户看到的表序、异常时 `running` 必被清掉、整轮自己炸掉也不泄漏状态、批内出错不停后面的项、空与越界入参的 400、闸门提示语、进度随 `GET /api/components` 带回且是副本。

### 界面

- **试听换成窗口底部的常驻播放条，另加空格键**：过去「试听」把 `<audio>` 长在那一行结果卡里，切个页面播放器就跟着没了、想调音量得滚回那张卡，同时点两行还会两首歌一起响。现在整站只有一个播放器：点「试听」后控件出现在**贴在窗口底部的播放条**（曲名与歌手、封面、进度条与两端时间、上一首 / 播放暂停 / 下一首、音量与静音、关闭），它挂在页面滚动容器之外，切页不销毁也不会重头播，同时最多一首。空格键切播放 / 暂停，两种情况明确让路 —— 焦点在输入框 / 文本域 / 下拉框里（含可编辑区域），或停在按钮、链接、弹层与气泡上时不抢键，否则打字和按按钮会被打断。播完自动接同一次列表里的下一首，没有下一首就停住；歌词逐行高亮改成跟着这个全局播放器的时间走。批量下载结束时，这一批被「跳过已下载的歌」拦下的曲目现在会**弹窗逐行列出**：`曲名 → 目录里那一份的文件名（同一首判定 N 分，目录里那首叫「…」）`，末尾说明判定按曲名 + 歌手 + 时长打分、不看文件名，并指回去重下要取消勾选哪个控件；这份清单搭的是既有的 `GET /api/music/download_status`（新增 `already_list` 字段），没有另起接口。播放条取 `--header-bg` + 顶部 `--line` 分隔，图标全部走页内 sprite（新增 pause / skip-back / skip-fwd / volume / volume-x / x 六枚），主色仍只有蓝，音量用的是原生 `input[type=range]` + `accent-color`，拖动时不会被 `timeupdate` 抢回去。
- **音乐页的四个新控件**：搜索结果行内「收藏」「换源」，批量勾选后工具条上的「换源选中项 (N)」，清单区新增整张「收藏清单」卡（可以整单下载、逐行换源，空态提示直接教怎么用），「并行策略」一行加「包含本地库」「无损参照」「拦搬运版」三个勾选。全部按既有档位取 `size="small"`，主色仍只有蓝，新增行不引入第二种按钮语言。
- **音质要求与成品核对都落在看得见的地方**：「并行策略」一行加了「音质要求」四个下拉（格式 / 位深 / 采样率 / 码率）与「不达标不下」勾选，选项一律由 `GET /api/music/status` 带回的 `quality_options` 渲染（前端不再抄第二份档位表，改档位不会两边不一致），下面固定一句「本批要求：无损、24bit 以上 …」与日志里那句同源。搜索结果「品质」列不再只写平台给的一串字：按本批要求逐维比过后加一枚状态标签 —— 符合 / 低于要求 / 未核到（鼠标停留看后端原话，缺哪一维就写哪一维没核到），勾了「无损参照」时下面再跟一行与参照比对的结论，低于参照才标红。资源库卡顶新增「核对音质」，把当前筛选出的音频成品逐份交给后端读它自己的标签，结论回挂在「音质」列同一行上（低于要求 / 符合 / 没核到 / 文件不在），卡顶摘要行报出核对了几份、几份确认低于要求、几份因读不出只算没核到，并注明参照那一步只比元数据。新增控件全部取 `size="small"`，主色仍只有蓝，绿与黄只出现在状态标签上。
- **重开页面不再被默认值骗到**：命名模板、嵌入标签、过滤不可用、包含本地库这四项后端一直在读，但界面过去只在用户点过「保存策略」时才写值 —— 重开页面显示的是硬编码默认，再点一次保存就把存好的设置冲掉。现在 `GET /api/music/status` 一并带回这四项（`filename_template` / `embed_metadata` / `hide_unavailable` / `include_local`），前端首屏回填。
- **模板提示写清归档口径**：那行提示从「可用字段」四个词扩到把 `{track}` 的来源、补零的理由（否则 Emby 排成 1、10、11、2）、以及「平台没给的字段留空，空掉的目录层不建、多余的 `- ` 会被削掉」全部写明 —— 新字段最容易出的状况是用户以为模板生效了而实际上那几段是空的。
- **「组件与依赖」的动作按钮行改成等宽栅格，加按钮不再错位**：那张卡底部那行原本用 `flex wrap` 排四枚按钮，而四枚宽窄不一（「重新检测」五个字、「查询上游最新版本」八个字），换行时第二行的左边界对不上第一行，看上去不是两行而是错位。现在改用样式表里已有的共享 `.btn-grid`：`repeat(auto-fill, minmax(150px, 1fr))` 定列、`gap: var(--gap-tight)` 定距、子按钮一律 `width:100%; margin:0` —— 于是**每枚同宽、上下同列对齐，窗口窄了自己减列、宽了自己加列，以后再加按钮只会多占一格，不需要动任何宽度**（这次的「一键更新」就是直接排进去的）。同一次改动把挤在按钮行里的三样文字挪出栅格、各占一行：`pip 可用 · <版本>` / `pip 不可用：无法在程序内更新 Python 依赖`（状态不是动作，不该与按钮同排，且它此前会把按钮行撑到换行）、`「一键更新」本次会处理 N 项：…`、`上次一键更新（时间）：成功 X / Y` 加未成功清单。实测（视口 1440×900）：四枚都是 165 px，左边界只有 1057 与 1230 两个值，间距 8 px，栅格宽 338 而卡片可用宽约 340，没有一枚按钮越出右边界。
- **嗅探页新增「接收猫抓（cat-catch）推送」一张卡**：接外部扩展这件事的入口全部落在这一张卡里（一页一节 = 一张卡），自上而下是：一句说明（写清去猫抓自己的「设置 → 发送数据」里填什么、请求方法要选 POST）、两格只读输入框各带一枚「复制」（「发送数据 URL」与「请求体模板」，值由 `GET /api/catcatch/status` 带回，前端不抄第二份，端口改了这边跟着变）、一行计数（累计接收 / 被规则挡下 / 待用解密钥 / 最近一次几点收到几条挡下几条）、一块 `--accent-soft` 的「两点须知」（一、推来的内容带该站登录 Cookie，所以「发送数据 URL」要保持为上面这个 127.0.0.1 地址、不要改成外网地址；二、猫抓文档写明该功能仍在测试、版本间格式有差异，接收端认不出来时原因写在「运行日志」里），再往下是「导入猫抓配置文件」（走隐藏 `<input type=file>` 选文件，不必再复制粘贴一整个 txt）、「清空规则」（无规则时禁用）、「刷新」，最后一张规则表按既有 `fmt-table` 排：名称 / 正则 / 扩展名 / 作用 / 操作，「作用」用 `el-tag` 分「排除」与「标注」两种（danger 只出现在排除这一档，符合绿黄只留给状态用的口径），正则那列超长省略号 + 鼠标停留看全文，行内是「停用 / 启用」与「删除」两枚。新增控件一律 `size="small"`，主色仍只有蓝。**这张卡已在 12:34:15 重启后用 Playwright（视口 1440×900）逐条断言通过**：两格只读输入框取值分别是 `http://127.0.0.1:8765/api/catcatch/push` 与 `${action}/${data}/${tabId}` 模板原文、「累计接收 / 被规则挡下 / 待用解密钥 / 最近一次」状态行在、无规则时「清空规则」`disabled=true`、卡内**没有横向越界元素**、页面脚本无错误 —— 见上面说明九。这张卡那三枚按钮（「导入猫抓配置文件」「清空规则」「刷新」）**没有**换成上面那条的 `.btn-grid`：它们是三个宽窄不同的动作、量下来右边界 539 远在卡片之内，等宽栅格反而会把「刷新」撑成 150 px 那一档，所以保持原有的 `.row` 排法。

### 修复

- **合集 / 播放列表的 12 集被写进同一个文件名，互相覆盖成一份**：症状是「任务全部报成功，目录里却只有一个文件」，而那个文件的标签还是某一集的、长度却是另一集的（盘上留下的残件 `合集·【官方中字】尼古喵喵 （全12集） [8a5be301].mkv`：title 写着「第12集」、PURL 是第 12 集那条，大小却与第 1 集只差 12,698 字节）。根因在落点名的那一步：为了避免 Windows 的非法字符与超长标题（`Errno 22 Invalid argument`），这里会先拿已经解析出的 `info` 把标题与 id 净化成固定路径 `安全标题 [id].%(ext)s` 再交给 yt-dlp —— 可**合集/播放列表拿到的 `info` 是容器**：`title` 十二集完全相同（就是那个「合集·…（全12集）」），`id` 干脆是空（于是退化成任务号前 8 位 `8a5be301`），拼出来的固定名对整表是同一个路径，每一条分集都往它上面覆盖，最后活下来的只是收尾那一集写剩下的那半份。现在容器一律不拼固定名：新增 `is_pl_info` 判据（`info["_type"]` 是 `playlist` / `multi_video`，或带着 `entries`），命中就直接走 yt-dlp 自己的输出模板 `%(title).60B [%(id)s].%(ext)s`，让**每条分集各自展开**（`server.py:4832` 起）。另一处配套的是收尾回收：列表任务成功后原先只看容器那一份 info，`prepare_filename(info2)` 算出来的是容器名、磁盘上根本没有，于是任务记录里的「成品」与实际写出多少毫无关系；现在从 `info2["entries"]` 逐条收 `filepath`（yt-dlp 处理完会写回）并按需 `prepare_filename(e)` 兜底，只保留真实存在的那些，任务记录指向最后一个（`server.py:5085` 起）。线上读回见上面说明八：11:03:32 那一单 12 条对 12 个文件，12 个文件名各带自己那集的 BV 号，合计 3,120,049,865 字节。
- **「此前已下载过」被说成「文件不可用 / 下载失败」**：开了「跳过已下载」（yt-dlp 的下载记录）之后，命中记录时 yt-dlp **既不下载也不报错**，只返回 None 或一个不存在的落点 —— 过去这三种情况全部走到「成品不可用」那条报错，用户看到的是一堆红字，而实际原因是「这一条早就下好了」，甚至分不清是不是设置没生效。现在三处分别写明：① 整张列表一条都没写出、而 entries 的 id 全在 `download_archive.txt` 里 → 「这条列表的每一项此前都已下载过（命中下载记录），本次没有重新下载；要重新下载请在下载选项里关掉『跳过已下载』」（`_ids_in_archive()` 会连每条分集自己的 id 一起查，B 站这类还要 extractor 类型对得上，`server.py:5052` 起）；② 单条视频没有文件而 id 在记录里 → 同一句话，并先写一行日志点名是哪一条；③ `extract_info` 返回 None → 先问记录再决定是重试还是判它「此前已下载过」，不再盲目重试三次报「站点没有返回可下载的媒体信息」。反过来，真写出了文件但那份文件的修改时间早于本次开始（yt-dlp 命中记录时原地返回旧文件）也补了一行「本次未重新下载：某文件已在下载记录里，要重下请关掉『跳过已下载』」。列表那行的汇总日志同时报出条数与文件数的差额（「列表 12 条，本次在下载目录写出 12 个文件」，缺时说清「差额是命中下载记录或抽取失败的条目」），不再让「12 条 1 个文件」这种看起来全绿的数字骗人。
- **入队预检自己先抛异常，「去装 FFmpeg」的提示变成了 500**：`download_preflight()` 里读全局设置「成品旁另存字幕文件」用的是 `cfg.get("write_sub_files")`，而 `cfg` 是配置对象、根本没有 `.get` 方法 —— 于是缺 FFmpeg 且开着外挂字幕的那条路径**还没走到报错就先抛 `AttributeError`**，界面上是一句看不懂的 500，而不是它本来要说的「到『设置 → 组件与依赖』点 FFmpeg 那行的『安装』」。改成 `cfg.data.get(...)`（`server.py:9209`），与同一函数里其余几处读法一致。这个 bug 只在「缺 FFmpeg」时才走到，所以本机装了 FFmpeg 的话永远碰不到 —— 这也是它留到今天的原因。
- **并发批量里「哪首歌对应哪个文件」会错位，四个名字装了别人的音频**：一批歌交给 musicdl 时，同批的计划落点都在同一个搜索目录里，而 musicdl 的 `download()` 是按**线程完成顺序**把副本还回来的（`modules/sources/base.py` 里各线程往同一个 `downloaded_song_infos` 列表 append）。收尾那一步原先按「每个位置从该目录里顺手指一个没用过的文件」配对 —— 而对象身上搜索时算出的那条计划路径在磁盘上常常并不存在（musicdl 的同名避让会把它排成 `曲名 - 标识符 (1).mp3`），于是指到的就是别人。线上第一次整单 4 首就撞上这个：四个名字按文件自带标签读出的时长是 5:39 / 3:14 / 3:43 / 8:47，清单标注依次是 8:47 / 3:42 / 5:36 / 3:14，整份倒过来。现在改成按曲名对位（`_pair_paths_by_name()`）：先认对象自己带回来的 `save_path`（要求文件名削掉「 - 标识符 (1)」之后与曲名归一相符），对不上再到同目录候选里找**唯一**命中的那一个，同名多条时先让别的行挑完再回头；**一个都对不上就把这一首按没下成算**，日志逐条列出是哪几首，并写明「不敢拿同目录里剩下的文件顶上 —— 宁可少一首，也不能把别人的歌安到这个名字上」。归一与削尾的口径见 `_name_key()` 与 `_file_name_part()`（曲名自己也可能带「 - 」，所以只削最后一段、且要求那半截像标识符；非法字符被替换与路径截断也在这一步吸收掉）。离线自检 `tests/parallelpair_test.py` 21 项：桩客户端照线上形状造文件（同一目录、计划路径不落盘、按完成倒序返回），逐首断言回报路径、文件名、文件内容三者是同一首歌；两条反向验证分别钉住「完成顺序恰好等于清单顺序时也必须各归各」（证明错配来自对位，不是来自造文件）与「桩只吐别人的歌名时四行必须全空、而把对位退回老逻辑则四行全被瞎指」（证明这两条断言有牙）。另把 `musicfavorites_test` 里「测试期间没往运行日志写东西」那条断言改对了：它原本在整份 `app.log` 里搜「收藏清单」字样，而这词会被线上真实使用写进去，于是从此恒假 —— 改成比对开跑前的出现次数。
- **繁體歌单在简体曲库里一首也认不出**：跨平台按曲名匹配的判据是「归一后精确相等」，繁体写法永远不相等，症状是「明明曲库里有这首歌，日志却说没找到」。现在 `_norm_text()` 先做繁简归一（`zhconv`，已进「组件与依赖」的可安装清单；没装也能用，只是退回旧行为）。同一批还修了歌手分隔符：整串过归一会把逗号 / 斜杠先吃掉，`A,B` 与 `B,A` 于是算成两首歌（去重失效），改成**先按分隔符切开、逐段归一、再排序拼接**。
- **归档那一步读缓存里查不到的行时会静默吞掉重命名**：命名模板收尾要读平台给的归档字段，那段取值原先只在「缓存里查到了这一行」的分支里赋初值，缓存失效的行走到读它的那一句会抛 `NameError`，被宽 `except` 吞成一条看着像模板问题的日志 —— 现在初值和 `meta` 一起建，查不到就是空字段，照常按模板归档。
- **导入猫抓规则时，装规则的容器被当成一条规则，用户的黑名单静默失效**：`_collect_regex_rules()` 递归找「带 `regex` 字段的对象」，判据原先只看**这个键在不在**（`node.get("regex")` 非空即可），而猫抓导出的那份存储里，`regex` 这个键名下面挂的常常是**整只规则数组** —— 各版本键名不固定，所以这一步本来刻意不猜键名只认形状，但形状认得太松。于是递归走到容器那一层就 `return [node]` 直接短路：容器被收成一条规则，数组里真正的规则**一条都不会再被看到**。更糟的是这条假规则能过 `re.compile`（整只列表 `str()` 出来的那串 `[{'regex': ...}]` 恰好是合法正则语法），于是导入接口高高兴兴回「新增 1 条」，界面上规则表里躺着一条谁也不认识的长串，而用户原本指望它挡掉的那些地址一个也没被挡。**这件事是线上读回时抓出来的**：第一次模拟导入回 `found:1 added:1`，紧接着那一次测试推送**真的建了一条下载任务** `e5e77a44-…`（秒失败，盘上没有文件）—— 也就是说黑名单失效不是理论后果，是当场后果。现在判据收紧成「`regex` 的值必须是**非空字符串**才算一条规则」，否则继续往 children 里钻（`server.py:14785` 起）。改完同一份配置回 `found:4 added:3 invalid:1`（`invalid` 那条带 Python 原话 `unterminated character set at position 1`，重复那条按设计跳过），再推同一批地址回 `dropped:1 received:0`、`/api/tasks` 全程 `running+pending = 0 → 0`、新增列表为空。测试造出来的那条任务与 `history.json` 里那一行都已删掉（21 → 20 条），`catcatch_rules.json` 也删了（本机原本没有这个文件）。离线补了 4 项回归：`catcatch_test` 的 C4（挂在 `regex` 键下的两条规则都要找到）、C5（收进来的每条 `regex` 必须是字符串，不能是整只容器的 `str`）、C6（值为空串或非字符串时不收、也不许误收容器）、D9（整条导入链：`found==2 and added==1 and duplicated==1`）；反向验证做了 —— 把判据退回「只看键在不在」，这四项一起红。

---

## v1.2.7 · 2026-09-22

本版收在「取全 + 排序 + 留痕」三件事上：所有超长列表统一每页 50 条、被接口分页截断的收藏与关注内容真正取全，聚合搜索既能按相似度 / 播放量 / 发布时间排序、也能一次取回更多结果，运行日志则改为按天归档并只保留最近 7 天。

> 说明：下面的「分页」与「收藏 / 关注取全」两条在 v1.2.6 的更新说明里已经写过，但那两处改动发生在 1.2.6 便携包打包之后，包内文件并未带上；本版是它们第一次随包发布。同样地，本版各处标有「（1.2.7 包后补）」的改动都做在 1.2.7 便携包打包之后，磁盘上现有的 `MediaDownloader-1.2.7-portable.zip` 尚未包含，随下一次出包才会带上。

### 界面

- **文件页结果卡挪到表格上方（1.2.7 包后补）**：播放器、字幕烧录、流水线产物三张卡原先嵌在文件表格卡的内部，而表格每页 50 行、卡片又排在表格下面 —— 点「播放」「烧录字幕」「查看产物」后界面看似毫无反应，实际功能都已正常执行（实测视频流返回 206 分段、`readyState=4`、时长 325.5s）。现把三张卡提到本页工具条之下、表格之上独立排列，并在 `playFile` / `openBurn` / `showPipeline` 里各补一次 `revealCard()`：卡片所在的结果区在滚动位置之上，不主动滚回去用户仍然看不到，因此渲染完成后调 `scrollIntoView({ block: 'start' })` 把它带到视口顶部（实测滚动容器 `.content` 由 1600 回到 176，卡片顶端与容器顶端齐平，容器内除表头外无吸顶元素遮挡）。
- **超长列表统一分页（每页 50 条）**：队列、文件、历史、聚合搜索、音乐搜索、TG 频道、收藏关注、订阅、资源库、网页嗅探、直播监控与直播任务共 12 个列表接入同一条分页条（`共 N 条 · 上一页 / 页码 / 下一页 / 前往页`，不足 50 条时整条自动隐藏）。为避免「只排当前这一页」的假排序，收藏 / 音乐 / TG 三张 `el-table` 从 Element 内部排序改为 `sortable="custom"` 全量排序后再切片；文件页行内「更多」下拉按当页下标取行，与 `$index` 一一对应。勾选不跨页保留（这些行没有可靠唯一键），因此分页的表下方固定提示「翻页后当前页的勾选会清空」。日志、媒体信息格式表、字幕 cue 列表沿用各自内部的定高滚动区，不再叠一层分页。
- **聚合搜索结果卡片重新排布**：卡片正文改为弹性列，四个操作按钮（下载 / 解析 / 订阅 / 复制）排成等宽两列并贴住卡片底部，标题是一行还是两行都不会让按钮错位；上传方、播放量、发布时间收进同一行，超出部分用省略号，卡片高度不再参差不齐。播放量按中文习惯折成「万 / 亿」，频道类结果显示的是粉丝数，标签随之写成「粉丝」。
- **资源库转码列**：「预设」下拉与「执行」按钮改放进一个固定 12px 间距的弹性行，表头列宽固定 240px，按钮不再紧贴下拉框、也不再被自动列宽挤成一条。
- **订阅页改为 Bento 栅格（1.2.7 包后补）**：这一页过去是三段竖排 —— 添加订阅的输入框占满整行、下面一句提示、再下面是整张订阅表，扫描按钮与「新条目自动下载」夹在中间，而“订阅现在有多少个、几个开着、累计新增了多少条”这几个数根本不在一处看。现在顶部一行拆成两张卡：左侧 4 格「添加订阅」留下链接输入框、类型识别标签、Telegram 读取方式与「添加订阅」主按钮；右侧 2 格「追新与扫描」收拢「立即扫描全部」、「新条目自动下载」开关，以及一行计数标签 `共 N 个 · 已启用 N`（有新条目记录时补一条 `累计新增 N`，鼠标停留写明「历史累计检测到的新条目数，不随下载清零」；有订阅读取失败时补一条红色的 `读取失败 N`，都为 0 时不占位），那段「添加时只记录已有条目、之后只处理最新未读」的说明也挪进这张卡。订阅表单独占下面一整行、收进一张卡，卡头右侧固定一行提示：「规则与目录」里的设置只影响之后新出现的条目。表头排序、分页条与行尾四个图标操作都按原样搬进卡内（点开的「订阅规则」「按日期回填」两张卡仍是按条件出现的整行卡，不进栅格）。本机浏览器实测：栅格 1400px 宽时左右两卡分别 929px 与 457px（2:1）、顶边齐平且高度同为 263px；订阅表所在的整行卡撑满容器；计数标签行 415px 内不换行不溢出；点「标题」表头后该列进入升序（表头显示 `标题↑`）、表格与分页正常；控制台无报错。窄屏走既有断点（≤1320px 四列、≤900px 单列），两卡在窄屏各自摊满一行。
- **组件与依赖每行给出三个版本（1.2.7 包后补）**：这一页过去每行只有一个版本号，报障时上不了口 —— 「我此刻用的是哪一版」「便携包原本带的是哪一版」「上游现在是哪一版」三件事分不开。现在每行写成 `当前 X · 随包 Y · 最新 Z`：`当前` 是程序此刻真正在用的（工具由 exe 自报，Python 包由 `importlib.metadata` 读）；`随包` 取自打包时写进包内的 `components_bundled.json`，只在它与你当前用的不一致时才显示（一致就不占地方，显示出来即说明这一项在你手上被更新过）；`最新` 要点新增的「查询上游最新版本」按钮才联网取，走 `python -m pip index versions`（尊重设置里的 pip 镜像，实测单包 1.7–2.4 秒），一次问完整张清单后缓存 10 分钟，比当前新就标黄并写「（可更新）」。FFmpeg 与 N_m3u8DL-RE 不在 PyPI，这两行没有 `最新`；查询失败时那一行写明原因（超时 / 镜像里没有这个包 / 输出没解析出版本号），不留空白。卡片底部固定一行「本便携包 v1.2.7（打包于 …）」，不用翻压缩包文件名也能确认手上是哪一版。同时修掉一个假就绪：FFmpeg 那行的状态过去判 `"not found" not in 版本字符串`，而这里的报错是中文「未找到」，因此缺 FFmpeg 时界面照样画绿点 —— 现改为直接判断能否找到可执行文件。另有两处是线上验证时才暴露的：`verCmp` 过去只要有一侧读不出数字段就算「相等」，于是当前显示「未安装」的行即使上游有版本也不标「（可更新）」（实测 cryptg 就是这样），现改成有版本号的一侧必然更大；以及点「重新检测」会不带 `latest` 参数重新请求，刚查到的「最新」整列刷没了，现在本次会话里查过一次之后就记住要查（服务端自己有 10 分钟缓存，不会次次联网）。

### 功能

- **聚合搜索支持三种排序**：筛选区新增「排序：相似度 / 播放量 / 发布时间」一行。排序不是把已取回的结果在前端重排，而是带参数重新向平台取数——B 站用 `order=totalrank/click/pubdate`（实测三者都生效），YouTube 用搜索页的 `sp=CAM`（播放量倒序）与 `sp=CAI`（上传时间）。两点如实处理：播放量各平台都给出数值，可以跨平台合并倒序；YouTube 的搜索结果不返回发布时间，把它和其他平台合并排序会让 YouTube 整体沉底，因此「发布时间」沿用各平台自身返回的分块顺序，结果区固定提示「发布时间按各平台自身返回顺序排列；YouTube 搜索结果不返回发布时间，故不参与其中」（另经实测，YouTube 对热门关键词常直接忽略「上传时间」参数，该排序以平台返回为准）。切换排序即重新取数，日志会写明本次用的平台、内容类型与排序。
- **`librosa`、`cryptg` 进入「组件与依赖」可安装清单（1.2.7 包后补）**：`pkg_update.PIP_PACKAGES` 补上 `librosa`（音频分析要用的节拍 / 响度 / 调性库，会连带装 numba / llvmlite，故在标签里写明体积代价）与 `cryptg`（telethon 的加密加速，不装则 Telegram 相关操作退回纯 Python 实现、明显变慢，启动日志里那两行 `Failed to load SSL library` / `cryptg module not installed` 也由此而来）。两项都走既有的 `/api/update/pkg`，在「设置 → 组件与依赖」点「更新」即可装，不必再开终端敲 pip；`/api/components` 会显示当前版本，未装则显示「未安装」。
- **聚合搜索结果不再固定 80 条**：单平台单类内容的取回上限由 80 放宽到 100，前端一次请求 100 条，聚合返回上限由 80 放宽到 300；B 站搜索改为按接口分页取满（单页 50、最多 6 页），不再只读第一页。接口同时返回 `total` 与 `truncated`，被截断时结果区直接说明「上游返回 N 条，一次最多显示 M 条」，并提示可缩小平台或内容类型后再搜（实测单平台关键词 `sorry` 一次取回 100 条，播放量倒序严格成立）。
- **歌单里排了两遍的歌只下一遍（1.2.7 包后补）**：Spotify 这类歌单常把同一首加多次，界面上就出现两行、点「下载选中项」时清单里也排两遍 —— 同一首歌占两次取址、下出两份成品。过去整条歌单路径一次判重都不做：`dedupe_results()` 只被「音乐搜索」调用，`parse_playlist` 与各条分支都没走它；唯一认重复的地方在归档那一步，口径是「文件大小 + 去掉 ` (1)` 的文件名」相同，而那时下载已经发生完了。现在两处都按同一口径判重：**曲名 + 歌手相同，再要时长落在按曲名匹配用的同一条容差内**（`_dur_close`：`min(60, max(20, 时长×12%))` 秒，缺一侧时长就不参与比较）。曲名与歌手只做轻量归一（大小写、连续空白、全角括号、逗号/顿号旁的空格），**刻意不剥「(Live) / 现场 / 伴奏 / 官方」这类版本词** —— 现有的 `_norm_text()` 会连这些一起抹掉，那样录音室版和现场版就成了同一首，合并后其中一版会直接从列表里消失；时长容差也因此还留着区分同名不同版的能力。曲名为空的行永不合并。落地上：① 解析收尾把重复行合并成一行，界面在曲名后标 `×N`（鼠标停留写明「歌单里这首歌排了 N 遍，已合并成一行，下载只下一遍」），被合并的数量经 `diag.dup_merged` 带回、随成功提示写成「已合并 N 首重复」，日志那句「歌单解析: N 首」报的也是合并后的首数；② `POST /api/music/download` 在建后台进度任务**之前**按同一口径清一遍清单（覆盖分次勾选、以及旧缓存里仍然排着的重复），运行日志点名是哪几首（`下载清单里有 1 首重复（同一首歌排了两遍），只下第一遍：「晴天」×2`），进度 `total` 用去重后的首数，重复数量单独记进 `dup_skipped` 并与「没取到地址」的失败数 `skipped` 分开，整批结束的回执与 `GET /api/music/download_status` 都带着它；③ 判不了重的一律保留（缓存里查不到对应条目、或没有曲名的行），绝不会因为判不出重复把用户的任务丢掉。离线自检新增 `tests/playlistdup_test.py` 40 项（判重键、分组、合并、下载入口、解析收尾接线、端点级各一段），反向验证四条：整张歌单没有重复时一行合并日志都不写、`dup_merged` 为 0；把收尾那次合并关掉，五首里的三首重复必须原样冒出来（证明断言盯的是真合并而不是桩子）；清单没有重复时一首不少地交给下载、且日志里不许出现「重复」字样；两行都没有曲名也不许合并。**实测范围**：以上判定与两处接线全部由这 40 项离线自检覆盖；真实歌单「合并掉几首」的读数尚未回填 —— 本机最近一次解析（09-23 15:34 的「中文歌单」）跑在改动生效之前的进程上，日志「共 139 首，列出 139 首」恰好说明旧代码一行都没合并，新代码上线后还没有重新解析过任何一张歌单。已归档的 53 个音频文件按曲名比对没有重复成品。

### 可排障性

- **补上此前记不到的页面操作**：聚合搜索切换平台 / 内容类型 / 排序、各列表点击表头排序（记到「按修改时间降序排序」这一粒度）、文件页进入与返回上级目录、收藏与关注各标签页的加载结果（取回多少条、平台记录多少条）现在都会落一条人话日志。**翻页刻意不记**：分页条每点一次就是一次状态变化，记进日志会把真正有用的下载与报错刷掉。
- **运行日志按天归档并自动清理**：跨天后第一次写日志会把 `app.log` 改名为 `app-YYYY-MM-DD.log`（当天归档已存在则追加合并），启动时删除修改时间超过 7 天的归档，日志数量不再无限增长；日志页固定提示「本页最多显示最近 200 条；磁盘日志按天归档，超过 7 天的归档自动删除」。便携包脚本的清理与私密文件自检同步覆盖 `app-*.log`。
- **音频分析失败当场回错，不再「看着像成功」**：`/api/ai/analyze` 原先无条件起后台线程并回「正在分析」，librosa 没装时失败只落在日志里，界面上弹的是成功提示，用户只能看到一行 `请 pip install librosa`。现在接口先用 `importlib.util.find_spec("librosa")` 判一次，缺失就直接回 `ok:false` 并写明去哪装（「设置 → 组件与依赖」的 Python 依赖，或本机 `pip install librosa`）；前端 `analyzeAudioFile` 按 `ok` 分支，失败弹红色错误、成功才弹绿色提示。同一条人话文案也放进了 `audio_analyze.py` 的 ImportError 分支，直接从脚本调用也能看到同样的指引。顺带把这条操作的日志埋点名由「AI 媒体分析」改为「音频分析」，与「更多」下拉里的按钮名一致，日志里指的就是界面上那个控件。**依赖之外的失败同样当场回错**：新增 `audio_analyze.preflight()`，起线程前只读一次 ffmpeg 头部，认不出这个文件（如误选图片、`.py`）或压根没有声轨（纯视频）时直接回 `ok:false` 带上原因，日志同步写 `音频分析未启动（文件名）：原因`，不必等后台线程跑完才发现；实测选 `server.py` 回「ffmpeg 读不出这个文件的媒体信息：…: Invalid data found when processing input」，选无音轨的 mp4 回「这份文件没有声轨，音频分析需要带音轨的媒体文件」。
- **多选批量下载不再是「点了没反应」的黑箱（1.2.7 包后补）**：勾选几十首点「下载选中项」后，界面只弹一句「后台下载」，此后既没有队列任务（这条路径不走下载队列）、也没有中间日志，而 `client.download()` 是一次性阻塞调用，成品要等整批跑完才从 `_musicdl_cache` 搬到最终目录 —— 实测 45 首那一批 15:15:15 就开始写缓存（25 首 / 3.6 GB），文件页直到 15:33 整批结束才第一次看到东西，中途与「根本没开始下载」完全无法区分。现在下载按每 6 首一片推进，每片下完立即归档到模板路径（成品边下边出现在文件页），日志先写 `开始下载 N 首：每 6 首一片，每片下完立刻归档到 <目录>，不用等整批`、每片再补一条 `下载进度 x/N（成功 k 首，已归档 i/3 片）`；新增 `GET /api/music/download_status` 汇报本批 total/done/ok/skipped/elapsed_s/last，界面据此在整批结束时弹一条明确回执「多选下载结束：成功 x 首，y 首没取到地址（原因见运行日志），用时 z 秒」，并顺手刷新文件列表。改名与歌词/封面/标签的收尾工作也随之从「整批结束后统一做」挪进逐首回调，实测端点级冒烟里 3 首分两片下载（2+1）时，每一片归档后就已经各自落进 `歌手/曲名 - 歌手.mp3`。
- **匹配源摆到界面上，不再静默换成别的平台（1.2.7 包后补）**：源列表只勾 Spotify、解析出的条目全是「Spotify 待匹配」，点下载后日志里却冒出「开始按曲名匹配 50 首：Netease/QQ/Migu/Kugou/Kuwo」—— 用户看到的是「我选的源被自动改成了国内源」。根因在 `resolve_placeholders`：它认定「Spotify 与 Apple 给不了音频地址」并把两者从匹配源里剔除，而界面上过去没有任何地方能指定匹配源，剔完为空就直接回落到默认 5 个源且不写原因。**这个认定经实测是错的**：musicdl 的 Spotify 客户端逐曲经第三方转链（spotubedl / spotisaver 一类）取址，Apple 同理，单曲搜索实测两个平台都能真的下回文件（`晴天 - 5pIcwtJYNJx93l420oR2Vm.mp3` 来自 Spotify、`Sunny Day (Live) - 1721459373.m4a` 来自 Apple），代价是每首约十秒、时常失败 —— 所以它们是"慢"，不是"不行"。现在「音乐搜索 → 并行策略」一行新增「匹配源」多选，候选与「搜索源」完全一致、同序、都能选，Spotify 与 Apple 在标签上标为「取址慢」；默认仍是网易云 / QQ / 咪咕 / 酷狗 / 酷我（取址走自家 CDN，搜到就能下），点「保存策略」即写入 `musicdl_strategy.match_sources`。下载请求按「本次显式指定 → 策略里保存的 → 本次勾选的搜索源」三级取值，界面上的下载按钮改为提交匹配源而非搜索源；不再替用户否决平台，只有完全没指定时才回落，日志写「没指定匹配源，已回落到默认匹配源：…」，勾选里含这两个源时另写一条「匹配源含 Spotify、Apple：这两个源要经第三方转链取址，每首约十秒且时常失败，整单会明显变慢」，回执里也直接点名本次会去哪几个源取地址。
- **匹配源是 Spotify / Apple 时整轮预算放宽到 3000s（1.2.7 包后补）**：勾这两个源时日志仍写「整轮最长 1500s」，而它们每首要经第三方转链约十秒 —— 50 首要 500s 起步，加上失败重试，1500s 只够搜完前几十首，后半程整批落进「本轮没轮到搜」，看上去像「后一半的歌不存在」。现在 `music_search.TRACK_MATCH_BUDGET_RELAY = 3000`：起始那行「整轮最长 Ns」、超预算那行「按曲名匹配超过 Ns，剩下的不再搜了」、放宽提示「（整轮预算放宽到 Ns）」以及回执里的 `budget` 全部取同一个 `budget` 值，不会出现开头说 1500、收尾说 3000 的对不上。默认匹配源那一路仍按 1500s（实测网易云等走自家 CDN，几十秒就能搜完一片，放宽只会让用户白等）。离线自检 `tests/matchround_test.py` K 段：K1/K2 验「只勾默认源时仍是 1500s、也不会提『放宽』」，K3/K5 验「含 Spotify 或含 Apple 时预算取 `TRACK_MATCH_BUDGET_RELAY`（3000s）、起始那行与转链提示跟着变」，K4 验「转链提示里那个数与起始行是同一个数，不是两处各写一遍」，K7 验「『没轮到搜』汇总行里的秒数就是实际生效的那个」；反向验证两条 —— K6 把常量打成 0.2s 后收摊时刻确实跟着变（不是硬编码在字符串里）、K8 把 `RELAY` 压到 0.2s 后超时判定本身也走这个常量。
- **按曲名没匹配上的歌整份列出来，日志与界面各一份（1.2.7 包后补）**：过去收尾只报前 12 首（`…共 N 首，另有若干未列出`），用户照着核完这 12 首以为就差这些，实际还差着一串。现在 `resolve_placeholders` 收尾把两份名单分开整份打完 —— `有 N 首在 Netease/QQ 里按曲名没找到同一首歌，已跳过`、`有 N 首本轮没轮到搜（整轮超过 Ns 就停了），不是没找到，再下一次或改用取址快的默认匹配源即可`，表头一行、每行 10 首（新增 `_log_name_list()`），并且**两类互不重叠**：没轮到搜的歌绝不出现在「没找到」那份里（否则会误导用户再换关键词去搜）。这两份名单同时回填进调用方传入的 `report` 字典（`missed` / `unsearched` / `budget` / `sources` / `total` / `matched`），`server.py` 把它挂在 `_MUSIC_JOB["match"]` 上随 `GET /api/music/download_status` 带回，前端整批结束时除原来的回执外再弹一张「按曲名未匹配的曲目」标题的滚动清单（回执文案也随之从「（原因见运行日志）」改成有清单时的「（清单见下）」）。实测：`tests/matchround_test.py` L 段 L1/L2/L3 验「汇总行下面把 15 首全列出来、计数与列出的条数一致、整段没有省略号这种截断痕迹」，L4 验 report 六个键都回填，L6 验 25 个名字按每行 10 首分行且一个不少，L5 是反向验证 —— 全部命中时两份清单都不许写、report 里保持为空（否则这条收尾只是无条件刷日志）；`tests/spotifylist_test.py` J1–J6 77 项里盯着「每首慢歌必须落在『搜过没找到』或『没轮到搜』之一、不重不漏」「『按曲名没找到』那一段里不能混进没轮到搜的歌」；界面端在本机浏览器断言弹窗渲染出 2 个标题、30+12 个名字全在、内容区 `max-height:468.16px` 且 `overflow-y:auto`、关掉后不留空壳节点。
- **入队前先查依赖与下载目录，注定办不成的单子不当场建任务（1.2.7 包后补）**：`POST /api/download` 过去无条件建任务，于是「没装 FFmpeg 却勾着嵌入字幕」「选了 HLS 专用引擎而包里没有 N_m3u8DL-RE」「下载目录在已经拔掉的移动盘上」这类单子要先排队、跑上几十秒到几分钟，最后报一条看着像站点问题的「下载失败」。现在入队前过一道 `download_preflight()`，**只拦「缺了就一定办不成」的**：缺 yt-dlp（拦普通链接，`tgmt://` 走账号会话不受它管）、缺 FFmpeg 而这一单要用到它（嵌入字幕 / 写出外挂字幕文件 / 嵌入封面 / 写入音频视频标签 / 嵌入章节 / 按 SponsorBlock 剪片头 / 封装成 mkv / 按时间点选段 —— 报错会把这一单实际用到的那几项点名，并写明去「设置 → 组件与依赖」点哪一行的「安装」，或按「把「画质 / 封装」换成 mp4」这类具体动作取消掉）、勾了「下载后本地转写」而没有 faster-whisper、勾了「HLS 用专用引擎」而找不到 N_m3u8DL-RE、`tgmt://` 链接而没有 telethon、下载目录建不出来或写不进去（往里面真写一个 `.md_write_probe` 再删掉，以此验过而不是只看路径字符串）。拦下时一条任务都不建：弹窗直接把这句话回出来，运行日志同步落 `入队前检查未通过（任务没有创建）：…`。**只是会慢、会降质的不拦**，例如缺 FFmpeg 但这一单不需要它 —— 照常入队，只在日志写一条提示，说明分开发布视频与音频的站点只能下到单条流、画质偏低。离线自检 `tests/components_test.py` 的 D、E 两段（含反向验证：依赖齐全时必须一条不错，否则「检查通过」只是空跑）。
- **随包版本清单也进了出包自检（1.2.7 包后补）**：`pack_release.py` 在拷完应用文件、生成启动器之前，用包内 runtime 的 `importlib.metadata` 读一遍 `PKGS` 里的依赖版本，再跑一遍包内 `tools\` 的 `ffmpeg.exe -version` / `yt-dlp.exe --version` / `N_m3u8DL-RE.exe --version`，连同包版本号与打包时间落成包内的 `components_bundled.json`（实测现有 1.2.7 包读出 14 项依赖，含 `musicdl 2.13.11`、`yt-dlp 2026.8.19`；工具三项 `9.0.1 / 2026.08.19 / 0.6.0`）。出包最后那步「真起一次包内服务」的冒烟测试新增 `check_components_payload()`：`/api/components` 的返回里任何一行缺 `active/bundled/latest`、报不出便携包版本号、或者没有任何一行带得到「随包」版本，就直接 `[ABORT]` 停止出包 —— 这类漏法在源码运行下一切正常，只有装进包里才表现为一列空白，所以必须卡在出包这一次。
- **抖音的「无结果」拆成五种原因，不再一律写成「接口易风控」（1.2.7 包后补）**：这一路过去无论站点回什么都落同一句日志（`抖音搜索无结果：需有效抖音 Cookie（设置→平台Cookie→抖音），接口易风控。推荐直接粘贴抖音分享链接下载。`），界面也写死同一句 toast —— 「你还没登录」「站点把你当成了脚本」「被限流」「接口自己拒了」「真的没搜到」这五件完全不同的事在界面上长得一样，照着换关键词或换源重跑都是白跑。判定标记全部来自本机实测（2026-09-23）：不带 Cookie 请求 `general/search/single` 与 `search/item` 两个接口，都是 HTTP 200 配 `{"status_code":2483,"status_msg":"请先登录，再继续搜索吧"}`；打开 `/search/<关键词>` 页面则回 72915 字节的 JS 校验页（`Set-Cookie: __ac_nonce`，正文含 `_$jsvmprt`、`byted_acrawler`、`__ac_signature`，整页没有 `_ROUTER_DATA` 也没有 `aweme_id`）—— 也就是程序化访问本来就一条都拿不到，这跟「没搜到」不是一回事。新增 `risk_control.py`（只依赖标准库，可离线跑）把「站点回了什么」判成九类：`login_required` / `bot_challenge` / `rate_limited` / `api_reject` / `not_found` / `denied` / `empty` / `network` / `unknown`，每条判定带着返回码、站点原话、给人看的一句话、下一步该做什么、依据哪几个标记、以及「降速对这一类有没有用」。判定顺序是刻意排的：先认「这压根不是数据」（校验页 / 限流），再认登录墙，最后才允许下「没有结果」的结论。接口返回码同时认 `status_code`/`code`/`errno` 三种字段名（抖音与 B 站写法不同），并补进「过于频繁」「太频繁」「需要登录」这类不带前缀的中文说法。接入点有四处：① `api_douyin_search` 每一次请求（含 HTML 兜底那一趟）都过一遍分类，重试之间按「设置 → 风控与加速」的「请求间隔」停顿而不是瞬间把接口刷完，判为限流 / 校验页时才向 `HOST_THROTTLE` 打点（受「站点自动降速」开关控制；登录墙不打点，因为降速对它没用），返回体新增 `risk` / `throttle` / `attempts`，日志改成 `抖音搜索无结果 q=…：<这一句人话>｜依据 __ac_nonce,status_code=2483｜已降速 douyin.com`；② 聚合搜索 `/api/search` 新增 `notes`，把每个空手而归的平台连同原因与下一步一起带回，前端在结果区固定列一块「这些平台这次没有给出结果」，写死的抖音 toast 与写死的日志句都已删除（抖音有结果时不写任何「被挡」原因，自检里含这条反向验证）；③ 下载体检 `verify_media_file` 不再把所有 HTML 都含糊地说成「多半是被站点拦下或缺少登录 Cookie」，改由 `describe_downloaded_bytes` 点名：字节的 JS 校验页（带着命中的标记）、CDN 回的 XML 报错（把 `Code` / `Message` 原文抄上屏，如 `Code=AccessDenied，Message=Access denied by bucket policy`）、人机验证页、普通登录跳转页各是各的说法；④ 任务失败原因在原始报错之后补一句 `原因：…；<该做什么>`，认不出来的报错一个字都不加（不编原因），限流 / 校验页这两类顺带打一次降速点（HTTP 429 不重复打点，下载循环里已经打过），并落一条 `按失败原因降速：<域名> 第 N 次命中`。前端 `friendlyError` 相应改了三点：带「原因：」或带「（依据 …）」判定标记的消息原样上屏不再改写（否则后端点名的返回码、站点原话与命中标记会被套话替掉 —— 实测这两条标记一起加之前，体检已经写明「下到的文件就是这张页面」，界面仍会把它换成一句只提抖音的 Cookie 指引）、新增登录墙（2483 / 请先登录 / yt-dlp 的 `Fresh cookies are needed`）与校验页标记两条分支、这两条一律把站点原文附在后面。指引里的控件名按界面实际写法给：「设置 → 多平台 Cookie」里的「抖音/TikTok」那一块（选「浏览器」读已登录的浏览器，或选「文件」填 Netscape 格式）。离线自检 `tests/douyinrisk_test.py` 67 项，用的两份真实材料是那次抓页的前 4 KB（`tests/fixtures/dy_challenge_head.html`）与抄录的 2483 响应体，反向验证含：正常带结果的回答、正常空结果、真实 mp4 与 matroska 文件头都不许被判成风控，关掉了「自动降速」就不能偷偷打点。重启后在本机界面与接口上再过一遍（同一批 2026-09-23 的读数）：不带 Cookie 只勾「抖音」搜 `sorry`，结果区固定出现「这些平台这次没有给出结果：· 抖音 —— 站点把这个请求当成脚本访问了…／带上一份有效登录 Cookie 再试（「设置 → 多平台 Cookie」里的「抖音/TikTok」…）」，且这段说明独占一行、不与原因挤在一起；运行日志同一时刻落 `抖音搜索无结果 q=sorry：站点把这个请求当成脚本访问了：…｜依据 _$jsvmprt,__ac_nonce`，另一次撞上登录墙时落的是 `…：接口回了登录墙：要先登录才给这个结果，返回码 2483，站点原话「请先登录，再继续搜索吧」｜依据 status_code=2483,status_msg`；`/api/status` 的 `throttle` 里能看到 `{"host": "www.douyin.com", "strikes": 1, "cooldown": 60.0, "left": 58.3}` 这条打点（冷却过后自动消失，说明降速确实只对「这一阵」生效）—— 但要说清来源：这条是下载侧按域名的降速记录，**同一次搜索接口自己回的 `throttle` 当时仍是空对象 `{}`**，即上面说的「按请求间隔停顿」与「按判定结果打点」在那一版里其实一次都没走到，原因是五处 `cfg.get` 误用被宽 `try` 吞掉（详见「修复」段同名条目）。假成功那条链也用本机 HTTP 服务验了一遍：把抓到的校验页原样当作 `probe.mp4` 让下载任务下一次，成品落到临时目录、任务状态 `failed`，报错为 `下载完成但文件不可用：站点把这个请求当成脚本访问了：回的是要执行 JS 才能继续的校验页，里面没有任何结果数据；下到的文件就是这张页面，不是媒体数据（依据 _$jsvmprt）（文件已保留，未转存网盘）` —— 过去这一条只会说「多半是被站点拦下或缺少登录 Cookie」。**边界说明**：这一条只做识别与转述，程序不会去执行字节的 JS、也不伪造签名；经实测，无 Cookie 时接口就是回 2483，签名并不能替掉登录，所以「主页 / 合集翻页 + 签名」要单做一阶，且同样不含任何绕登录的逻辑。
- **日志页写明日志在哪，并给一键打开（1.2.7 包后补）**：`LOG_FILE = APP_DIR / "app.log"` —— 日志和程序本体一直在同一个文件夹里，但界面既不写这个位置，也没法一步打开，报障时要用户自己去磁盘上找 `app.log`。现在 `GET /api/logs` 除日志本体外回 `dir`（程序所在目录）、`file`、`archives`（现存归档文件名列表），日志页那行固定提示改写为「本页最多显示最近 200 条；日志写在程序所在文件夹的 `app.log`，跨天归档成 app-日期.log，超过 7 天自动删除」，取到路径时再补一段「（当前在 <绝对路径>，已归档 N 份）」，没取到就整段不显示（不留空括号和「0 份」这种像坏掉的排版）。旁边加「打开日志文件夹」按钮，走既有的 `/api/open-folder`（该接口对绝对路径直接打开该目录，读码确认 `cand.is_absolute()` 分支与 `{"ok": True, "path": ...}` 返回）。两点是顺手补的：**空路径不去敲门** —— 那个接口拿到空 `path` 会退回打开下载目录，按钮写的和实际弹出的文件夹就对不上了，所以点它时若还没有路径就先补拉一次 `/api/logs`，仍然没有就当场回一句「还没拿到日志所在的文件夹，重启程序后再点一次」，在发出请求之前停下；**埋点写明是哪一下** —— `api()` 新增可选的 `uiName`，同一个接口被不同按钮共用时日志记的是按钮名而不是接口名（否则这一下会被记成「打开下载目录」）。实测（本机浏览器，视口 724×836）：提示那一行 63 字、无空括号、所在工具条横向溢出 0 像素；在改动前的旧进程上点按钮得到的正是上面那句提示，且 `app.log` 末尾没有多出任何「打开…文件夹」的记录，也就是请求确实没发出去。**界线**：带真实绝对路径与归档份数的那半句要等重启才看得到 —— 旧进程的 `/api/logs` 只回一个键，实测此刻仍是 `keys=['logs']`。
- **抖音搜索在降速冷却期内不再重复敲门（1.2.7 包后补）**：上一版把风控判定接进降速表之后，实测暴露了一个反直觉的后果 —— 被挡的搜索会让同一条记录越叠越长：连着三次「搜一下」依次得到 `strikes 1 / 冷却 120s`、`strikes 2 / 180s`、`strikes 3 / 240s`（沿每次命中乘 `1 + 0.5×(次数−1)` 的既有递增规则，上限 900s）。而用户撞了风控之后手上唯一还能做的动作就是再点一次搜索、或换个词再试，也就是说**惩罚的恰好是重试的人**，何况那几次请求必然同样被挡，只是白等十来秒。现在 `api_douyin_search` 进函数先问一句「这个域此刻还在冷却里吗」：在冷却中、且记得上一次的判定，就直接把那次判定复述出来，一条请求都不发 —— 返回体 `attempts: []`、`skipped: true`，原因写成 `<上次那句人话>（该站点正在降速冷却，还剩 Ns，本次没有再向它发请求）`，运行日志落 `抖音搜索跳过 q=…：www.douyin.com 冷却还剩 Ns（第 M 次命中），上次判定 bot_challenge`。复述不再打点，因此冷却时长不会因为多点几次而继续增长；界面上「站点降速中」那张卡的「立即恢复」就是为这种情况留的出口 —— 想立刻再真搜一次，先点它。三处实现细节：① 新增 `HostThrottle.peek()` 做只读询问，与 `cap_for` / `snapshot` 的区别是一律不改状态（那两个会把过期条目减 `strikes` 或直接摘掉，拿它们当发请求前的闸门会让「问一句」本身影响后续的降速计算）；② 上次判定记在模块级 `_DY_LAST_BLOCK`，只有「真搜过、且确实空手而归」才写入；③ 聚合搜索 `/api/search` 的原因里，复述那次不再追加「已自动降速：… 冷却 Ns」这句 —— 那一次什么都没发，写出来与「本次没有再向它发请求」自相矛盾，冷却时长也已经写在括号里了。这条闸门目前只接在抖音搜索这一个入口；下载与直播监控那几处仍照旧打点。离线自检新增 I 段 12 项（`tests/douyinrisk_test.py` 由 55 项增至 67 项），反向验证做了三条：光有冷却但没存过判定 → 照搜不误（不能因为记不到原因就把用户的搜索吞掉）；有判定但冷却已结束 → 重新真搜、不复述旧结论；冷却已过的真搜被挡时「已自动降速」这句照旧在（否则上一条会退化成永远成立）。**重启后在本机验过（2026-09-23 14:13）**：不带有效登录态真搜一次 `sorry`，照旧被挡并落点（`/api/status` 给出 `{"host": "www.douyin.com", "strikes": 1, "cooldown": 120.0}`，日志 `…｜已降速 www.douyin.com（120s）`）；紧接着在冷却里换词再搜、走聚合搜索、再换第三个词，三次都是 `0.0s` 返回、`count: 0`、`attempts: []`、`skipped: true`，原因写作「站点把这个请求当成脚本访问了：…（该站点正在降速冷却，还剩 119s／91s／90s，本次没有再向它发请求）」，日志三行分别落 `抖音搜索跳过 q=…：www.douyin.com 冷却还剩 Ns（第 1 次命中），上次判定 bot_challenge` —— 关键是那三次之后 `/api/status` 里这条记录始终是 `strikes 1 / cooldown 120s`，没有再像改动前那样叠成 `2 / 180s`、`3 / 240s`；聚合搜索结果区的说明末尾不再有「已自动降速：… 冷却 Ns」这句自相矛盾的话（同一份自检里 I12 反向盯着它）。

### 修复

- **收藏 / 关注页只加载了接口第一页**：B 站收藏夹接口单页最多 20 条、关注列表单页 50 条，前端却都只发一次请求，于是 116 条的收藏夹只显示 39 条、1124 位关注只显示 50 位 —— 这就是「内容显示不全」的根因，分页条本身救不了它。现两个接口新增 `fetch_all`：收藏夹按 `media_count` 并发补齐剩余分页（最多 6 路，单页失败只降级为部分成功），关注列表按 `total` 补齐（上限 2000 条）；YouTube 喜欢 / 稍后再看 / 播放列表的取回上限由 40/50 放宽到 200，并把 `playlist_count` 作为 `total` 一并返回。界面区分两种差额并各给一条提示：真被上限截断时说「本次只返回前 N 条」，其余情况说明是已失效或不可见的条目（实测 116 条收藏夹取回 109 条，7 条为失效条目）。
- **`GET /api/plugins` 重复注册**：`server.py` 里有两处同路由 handler，FastAPI 按注册顺序取先者，下面那份（含 `description` / `priority` 的插件列表）永远不会执行。现删掉重复路由，原位置留注释指明该接口在上方「文件与目录」段已注册，避免以后再补一份。
- **`GET /api/douyin/search` 绑错了函数：既不搜索，又会把 Cookie 内容回吐出去（1.2.7 包后补）**：这条路由的 `@app.get` 装饰器贴在了 `_load_netscape_cookies(path)` 上，也就是界面里点「抖音」搜索时会去读一个 Cookie 文件而不是搜东西。后果分两层：一是正常调用直接 `422`（缺 `path` 参数），接口从来没真正工作过；二是 `?path=<任意路径>` 会原样返回该文件按 Netscape 制表符格式解析出的 `{Cookie 名: Cookie 值}` —— 本机 `127.0.0.1:8765` 上任何进程（或浏览器里任何一段脚本发出的请求）都能把 `cookies/` 下已登录站点的凭据读走。现把装饰器移回 `api_douyin_search`（按 `q` / `limit` 查询，返回结果 + 本次风控判定），`_load_netscape_cookies` 恢复成普通内部函数。这条是接抖音风控判定时顺手撞上的：`GET /api/douyin/search?q=sorry` 回了 `422 [{"loc":["query","path"]}]`，而这条路由本来的入参是 `q`。离线自检 `tests/douyinrisk_test.py` 的 G 段加了路由绑定断言（该路径只有一条路由、且 endpoint 名为 `api_douyin_search`），反向验证做了：把装饰器临时挪回 `_load_netscape_cookies`，这两条立刻报 `FAILED: G1, G2`、退出码 1，改完文件与原始内容逐字节一致。
- **抖音风控那几处「读设置」全部静默失效：`cfg.get` 在这个文件里根本不存在（1.2.7 包后补）**：接进 `risk_control` 的判断里有五处在模块级函数中写成了 `cfg.get("…")`，而模块级 `cfg` 是 `ConfigManager()` 实例，它只有 `.data` 这一个对外容器、没有 `get` 方法 —— 于是这五句每一次都抛 `AttributeError`，又被外层宽 `try` 全部吃掉：① 「设置 → 风控与加速 → 请求间隔（秒）」对抖音重试完全没生效，接口是被一瞬间连刷完的；② 判为限流 / 校验页之后向 `HOST_THROTTLE` 打点这一步没走到，`/api/douyin/search` 的返回体里 `throttle` 恒为 `{}`，日志里也不会有「已降速」那半句；③ 更要紧的是它把一次本来正常的分类跑成了假结论 —— 异常被 `api_douyin_search` 每次尝试外面的 `except` 接住，追加成一条 `network` /「请求没走通」的判定，所以本机第一次实测的 `attempts` 里多出一条根本没发生过的网络错。现五处统一改成 `cfg.data.get(…)`（`risk_note_for_failure` 两处、`api_douyin_search` 三处）。**下载循环里的 `cfg.get("…")` 不是同类问题**：那里的 `cfg` 是 `download(…, cfg: dict, …)` 的形参（调用方给的是 `dict(self.cfg.data)`），`.get` 本来就是对的，没有改动。离线自检之所以全绿，是因为 `tests/douyinrisk_test.py` 的 `FakeCfg` 多了一个 `get()` —— 桩比真对象宽，误用就测不出来；现在桩和 `ConfigManager` 一样只暴露 `.data`，谁再写 `cfg.get` 当场红。同时补上真正缺的那段覆盖：E 段是把 `api_douyin_search` 换成 lambda 来验聚合搜索透传的，函数本体的重试与打点从来没跑过，新增的 H 段用打桩的 `requests.get` 走真函数（两次接口 × 两套请求头 + 一次 HTML 兜底），断言五条尝试全部被分类且不出现被吞掉的「请求没走通」、`throttle.cooldown` 取到的是配置里的 90 而不是默认 60、四次重试之间按「请求间隔」真的停了 0.3s，并做反向验证：正常拿到条目时不打点、不写原因、也不空等间隔。自检由 48 项增至 55 项。反向验证做过一次：把那两处临时改回 `cfg.get`，H 段立刻 `FAILED`、退出码 1，改回后文件与原始内容逐字节一致。**重启后在本机再过一遍（2026-09-23 13:48，设置里「请求间隔」= 2s、「风控冷却」= 120s）**：不带有效登录态搜 `sorry`，返回体 `throttle` 从原来的空对象变成 `{"host": "www.douyin.com", "strikes": 1, "cooldown": 120.0, "left": 120.0}` —— 冷却值取的是设置里的 120 而不是代码默认的 60，说明这五句真的读到了配置；无结果原因末尾多出 `（已自动降速：www.douyin.com 同时只跑 1 个，冷却 120s）`，运行日志落 `抖音搜索无结果 q=sorry：…｜依据 _$jsvmprt,__ac_nonce｜已降速 www.douyin.com`；`attempts` 由修复前的 6 条（含一条压根没发生过的 `network`／「请求没走通」）收敛成 5 条真实判定（四次接口 `login_required` + 一次 HTML `bot_challenge`）。整次搜索耗时也从误用状态下的 2.7s 变成 11.1s —— 多出来的正是原来被跳过的四次 2 秒重试间隔。另外 `/api/status` 的 `throttle` 现在也会列出这条打点，实测连着三次被挡的搜索依次得到 `strikes 1 / cooldown 120s`、`strikes 2 / 180s`、`strikes 3 / 240s`（沿用既有的「每次命中乘 1 + 0.5×(次数−1)」递增规则，上限 900s），`/api/status` 列出的始终是同一条记录，也就是搜索侧的判定从此和下载侧共用同一张降速表：撞过风控之后那 120 秒里抖音的下载任务会被串行化，这正是「站点自动降速」这一项本来的作用。
- **音频分析打不开 mkv / mp4，响度还恒为 0 dB（1.2.7 包后补）**：装上 librosa 后 mp3 能分析，本站默认下载容器 `.mkv` 仍然失败，报 `Error opening '…mkv': Format not recognised.` —— librosa 1.0 起去掉了自带解码器，只认 libsndfile 支持的 wav / flac / mp3 / ogg，Matroska 与 MP4 一律打不开。现改为先让 ffmpeg 抽出 22050Hz 单声道 `s16le` PCM（复用 `diarize_tools.ffmpeg_executable()` 那条由 server 注入的实际路径，便携包不带 PATH 里的 ffmpeg 也能用），再把数组交给 librosa 算节拍 / 响度 / 频谱质心；整段时长改读 ffmpeg 横幅里的 `Duration:`，不再额外依赖 ffprobe；确实没有声轨时把 ffmpeg 的 stderr 尾串一并写进报错上屏，而不是只说「分析失败」。另一处同时暴露的问题：响度用 `amplitude_to_db(np.array([rms_mean]), ref=np.max)`，而 librosa 1.0 的 `ref` 传可调用对象时是拿数组自身当基准，单元素数组跟自己比，因此任何文件都显示 `0.0 dB`；PCM 已归一到 ±1.0，改用 `ref=1.0` 得到真实 dBFS（实测 `晴天 - Jay Chou.mp3` 318.4s · 136 BPM · G major · -22.0 dB，`808 - You….mkv` 325.5s · 152 BPM · C# major · -18.0 dB）。同一条 mp3 在换解码链路前后的 BPM 读数不同（`librosa.load` 时 152，改走 ffmpeg 重采样后 136），因为音频不再由 librosa 自己解码与重采样，两者都是合法读数，以容器内实际音轨经 ffmpeg 解码的结果为准。
- **「指纹识别」用不上随包的 fpcalc，失败也只落在日志里**：排查音频功能时发现这条操作从来没通过 —— `music_search.find_fpcalc()` 只查 PATH，而设置里的「一键 PATH」写的是用户注册表，正在跑的服务进程读不到，包内自带的 `chromaprint/fpcalc.exe` 因此永远算「未安装」（`/api/music/fpcalc_status` 也跟着报 `available:false`）。现在 PATH 之外回落到同目录那份，实测状态接口报出 `…\web_app\chromaprint\fpcalc.exe`，命令行跑真实 mp3 得到 `duration=249.44` 的指纹。同一条操作还有第二类问题：接口无条件回「正在指纹识别」，缺 fpcalc、AcoustID Key 被拒、文件没有声轨都只在后台线程写一行日志（最迷惑的一种是日志只说「候选=0」，看着像曲库没收录）。现在这三项都在起线程前先判一次并当场回 `ok:false`，`acoustid_lookup` 的报错也改成带上服务端原文（`HTTP 400：invalid API key`）而不是只有状态码。顺带纠正了设置里的口径：那栏原先写着「在 acoustid.org 登录后复制 API Key」，而 AcoustID 的 `/v2/lookup` 只认**应用**的 client key（在 acoustid.org/manage/client 注册获得），账户的 user key 一律被拒 —— 照旧文案操作的人注定匹配不上，标签与提示都已改写。本机那个 Key 属于哪一类没有改动，界面上现在会直接把「拒绝了这个 Key」讲明白。
- **分片下载中断不再吞掉整片成品，报错带上调用栈（1.2.7 包后补）**：另一批 50 首里，第 2 片报 `第 2/4 片下载失败: [WinError 2] 系统找不到指定的文件。: '\\?\H:/'`，回执 `下载进度 23/23 首（成功 17 首，已归档 4/4 片）`，而这一片其实有 3 首已经落盘（`Brave Shine`、`カタオモイ`、`前前前世 - movie ver` 的 mp3 + lrc，共 30.7 MB，文件时间 19:37:32 与报错同一秒）。旧写法把一个分片的「下载 / 对位 / 归档」整个套在同一个 `try` 里，`client.download()` 一抛就整片放弃，成品留在 `_musicdl_cache` 里没人搬 —— 症状与上一那条 braille 报错完全同型。把这 6 首原样重放（同一份 musicdl、同一批关键词、走 Spotify 转链）却正常返回，文件与 `download_results.pkl` 都齐（其中 1 首当场报 Spotify 的 `500 ... pathfinder/v2/query`，属平台侧偶发），说明触发点不是歌的内容；`\\?\H:\` 这种形状既不由本仓库产生，也不由 musicdl 依赖的 `pathvalidate` 产生（两边都按字节正则扫过），而旧日志只有 `str(e)` 一行，指不出是谁调的 `makedirs`。现在每片只把 `client.download()` 框进 `try`：中断只记一条 `第 i/n 片下载中断: <类型>: <消息>｜栈尾 <最后三帧>｜改从缓存里找已经下好的文件`，随后 `_salvage_paths()` 按每首歌的 `save_path` / `work_dir`（musicdl 内部会把它改成斜杠形式，故两边都 `normcase` 再比）从缓存里找回已经落盘的成品，照常归档、改名、配歌词，并写 `第 i/n 片中断后从缓存救回 k/n 首`；归档本身另起一个 `try`，失败只降为 `归档: <原因>` 一条告警而不牵连下载结果。调用栈尾由新的 `_tb_tail()` 统一给出，拼在两条 `error` 日志末尾。首版只截最后三帧，22:53 那批上线后抓到的是 `栈尾 File "<frozen os>", line 215, in makedirs <- … line 215 … <- … line 225, in makedirs` —— 三帧全在 `os.makedirs` 自己的递归里，调用方仍然没点名；现在 `_tb_is_stdlib()` 先把 `<frozen ...>` 帧和标准库 `Lib\` 目录（`site-packages` 除外，musicdl 的帧要保留）剔掉再截尾，剩下的一定是第三方或业务代码。同批还暴露一处：4 个中断片各自只救回 2–3 首（`第 2/6 片中断后从缓存救回 3/6 首`），说明坏路径只属于片里某一两首歌，其余没落盘的是被线程池连坐、压根没下过 —— 于是这一片里没找回的歌现在**逐首单独重试一次**（`第 i/n 片逐首重试补回 k 首`），一首坏路径不再带走同片无辜的歌。这 3 首已按 `{artist}/{name} - {artist}` 归位进 `Downloads\Aimer\` 与 `Downloads\RADWIMPS\`，缓存清空。`\\?\H:\` 这种前缀仍未找到本仓库内的生产者：`pathlib.Path.resolve()` 与 musicdl 的 `legalizepathlength` 实测（短名 / 480 字超长中文名 / 不存在的盘）都不加前缀，全盘按字节扫下来只有 `yt_dlp.utils.to_high_limit_path` 造这个形状，所以等下一次线上栈尾点名调用方再收根因。自检 I 段的假客户端改为「只写下同片里没炸的那几首再抛 WinError 2」，否则缓存里首首有成品，逐首重试那条分支永远跑不到：I8 验没落盘的那首确实被补回并进了最终目录；反向验证（I9 + `ALWAYS_BOOM`）让每次调用都抛、一个文件都不写，此时如实报 `中断后从缓存救回 0/2 首`、位置留空、不多写「补回」、最终目录不多出文件。新增 K 段真调一次 `os.makedirs` 的深 `\\?\H:` 路径：剔噪后栈尾含本自检文件的调用帧，不剔噪时最后三帧全在 `<frozen os>`（反向验证，防止 `_tb_tail` 空转）。
- **曲名以 `/` 开头会把整片下载带走：递交前先钉回落盘目录（1.2.7 包后补）**：上一条留了个未结的问题 —— `\\?\H:\` 这个形状「仍未找到本仓库内的生产者」。找到了，是曲名本身。Spotify 一类歌单里会出现以斜杠开头的曲名（如 `/坏名A`），而 `os.path.join(work_dir, f"{曲名} - {id}.ext")` 遇到绝对样式的第二段会**直接丢掉前缀**，返回 `H:\坏名A - id.mp3` —— 文件被甩到盘根；musicdl 的 `legalizepathlength` 再对这个路径取 `.parent.resolve()`，得到扩展写法 `\\?\H:/`，`base.py` 随后拿它当 `work_dir` 调 `IOUtils.touchdir` → `os.makedirs('\\\\?\\H:/')` → `FileNotFoundError: [WinError 2] 系统找不到指定的文件。`（实测短路径 `os.makedirs('\\\\?\\C:/')` 与 `('\\\\?\\H:/')` 都抛这一句，两个盘也都是 `GetDriveType=3` 本地磁盘；`os.mkdir('C:/')` 抛的则是 `PermissionError [WinError 5]` —— 也就是说这条目录在 Windows 上根本建不出来，无论哪个写法）。因为 `client.download()` 内部是线程池，一首歌抛起来整片 6 首一起中断，剩下的歌压根没下过。现在新增 `_guard_song_paths()`，在 `download_songs` 里 `out_dir` 定下来之后、递交给 `client.download()` **之前**跑一遍：曲名先 `lstrip("/\\")` 打轻，再判断这条计划路径是否仍在下载目录里，不在就改曲名、并把 `work_dir` 收回 `out_dir`（已经在 `out_dir` 里面时**保留原值**，`_musicdl_cache` 那层目录不能动 —— 归档那一步按它找文件），同时把 `_save_path` 置回 `None` 交 musicdl 重算（同名避让那套逻辑仍要留给它），并落一条点名曲名的 `warning`。判不了就不动：`dict` 形式的占位条目（压根不会下载）直接跳过。实测本机 `GetDriveType`、`Path.mkdir` 静默返回、真 `SongInfo` 塌成 `C:\` 这几条都由 `tests/matchround_test.py` M 段钉住（M7 用真 musicdl 断言「不加守卫时 save_path 的父目录就是盘根」，M7b 单独验 `os.makedirs` 的 `\\?\` 写法确实抛 WinError 2，M8 验加守卫后同一个对象算出的路径落回下载目录内）；N 段用一个「只要 dirname 是盘根就抛 WinError 2」的严格假客户端跑真 `download_songs`：N1 整片不再中断、两首都交了出去，N2 报错变成写明是哪首歌的 warning，N5 反向验证 —— 把 `_guard_song_paths` 换成空函数，同一首歌立刻把整片带崩（`第 1/1 片下载中断: FileNotFoundError: [WinError 2] …: 'C:/'`），说明断言盯的是守卫本身而不是假客户端太宽松。上一条的救回与逐首重试逻辑照旧留着，作为第三方库里其它路径问题的兜底；区别是这一类不再需要靠兜底过活。
- **按曲名匹配的时长容差改成「绝对 + 按比例」，并把被拒原因写上屏（1.2.7 包后补）**：`_pick_track_match` 过去只要曲名与歌手都对上，就把时长差 60 秒以内的候选认成同一首 —— 对 262 秒的歌来说等于允许 23% 的偏差，正好把录音室版与另一种版本、剪辑版放进来；反过来真正该挡的「同名不同人」在日志里与「曲库里没这首歌」共用一句「没找到」，用户照着换源再试也看不出差别。现在容差取 `min(60s, max(20s, 时长 × 12%))`（常量 `TRACK_DUR_TOL_ABS` / `TRACK_DUR_TOL_FLOOR` / `TRACK_DUR_TOL_PCT`，下限那 20 秒留给平台之间固有的尾差与编码差），只对上曲名、歌手不同的候选仍要求 5 秒以内（`TRACK_DUR_TOL_STRICT`）；任何一侧没有时长信息时该项不参与判断，不会因为某个平台不给时长就整体匹配不上。被挡下的候选由 `_pick_track_match` 的 `notes` 收集、经 `_resolve_placeholder` 汇总到 `rejects`，逐条日志变成 `匹配 x/N：曲名 → 没找到（「不打扰」时长差 60s，超出容差；同名「晴天」歌手不同、时长差 138s）`。自检 C 段据此改写：C2 换成容差内的例子、C9 同时验「短曲差 60 秒要拒」与「长曲差 55 秒要收」、C10 验两种被拒原因都写得出来、C11 反向验不传 `notes` 时判定结果不变且不调坏。
- **匹配预算用尽的歌不再报成「没找到」（1.2.7 包后补）**：`按曲名匹配超过 1500s，剩下的不再搜了` 之后，还有 22 首在 19:34:39 这同一秒内被判完，汇总写成 `有 27 首在 Spotify 里按曲名没找到同一首歌，已跳过：…夜に駆ける、藍二乗…` —— 这些首本轮根本没排到搜索，结论却是「曲库里没这首歌」，用户照着换源再试纯属白跑。原因是预算到期后 `f.cancel()` 掉的任务在取结果时抛 `CancelledError`，被同一层的 `except Exception` 当成「搜了没搜到」。现在这条分支单独走：逐条写 `匹配 x/N：曲名 → 本轮没轮到搜`，末尾单列一条 `有 k 首本轮没轮到搜（整轮超过 1500s 就停了），不是没找到，再下一次或改用取址快的默认匹配源即可：…`，真搜过又没对上的仍留在「按曲名没找到」那条里，两份名单不互相掺。自检 J 段的搜索打桩必须真的 `sleep`：瞬间返回的桩会让 5 首在第一次判定前就全跑完，`cancel()` 一个都取消不掉，这条分支等于没测（写第一版时就是这样空跑的，日志里两首都写着「没找到」却检过了）。现在 6 首各睡 0.5s、预算 0.2s，超时那一刻至多在跑的只有 2 首，断言「至少 3 首算没轮到搜」以及两类名单不重不漏；反向验证仍然保留：正常搜过没命中的照旧写「按曲名没找到」。
- **分片下载会被进度条的一个转圈字符打断，整片成品烂在缓存（1.2.7 包后补）**：50 首的一批实测只有第 1 片成功，第 2、3、4 片各报 `第 x/6 片下载失败: 'gbk' codec can't encode character '\u2838' in position 0: illegal multibyte sequence`，回执写着「成功 6 首，44 首没取到地址」，而 `_musicdl_cache` 里其实躺着 27 个完整文件 / 3.67 GB。字符 `⠸` 是 rich `SpinnerColumn` 的转圈帧：musicdl 的 `download()` 用带进度条的 `with Progress(...)`，Rich 在**退出时**还要把最后一帧渲染写进 stdout，而服务把 stdout 重定向到日志文件后这股流按系统 GBK 编码，撞上编不出的帧就当场抛 `UnicodeEncodeError`。异常发生在所有并发下载都已经结束、`download_results.pkl` 还没写、归档还没跑的那一刻，于是文件在下、结果没了。第 1 片能过纯属侥幸——那一片退出时每个任务都已 100%，进度条渲染的是结束态（转圈位是空格），不含 braille。现在 `music_search._harden_console_encoding()` 在 `_build_client()`（搜索 / 解析歌单 / 下载三条路径共同的入口）里把 `stdout`、`stderr` 的 `errors` 设为 `replace`：编码本身不动，编不出的字符记成 `?`，进度条照常写日志。自检 `tests/spotifylist_test.py` 新增 H 段，用子进程把 stdout 真的重定向成 GBK 文件流复现：加固后退出码 0，不加固退出码 3 并打出与线上同一条报错（反向验证，防止自检空跑）。线上复验：同一张歌单重跑 36 首，6 片全部下完并归档（`下载进度 36/36 首（成功 36 首，已归档 6/6 片）`），该报错不再出现。
- **工具自己的中间文件不再落在用户的下载目录、也不再跟着启动位置跑（1.2.7 包后补）**：核对目录时发现三处不该在那儿的工具产物。① `web_app\musicdl_outputs`（空，09-23 16:13 建）—— `music_search.py` 里 musicdl 的工作目录默认写的是**相对名** `"musicdl_outputs"`（7 处），相对路径按进程当前目录解析，所以从哪个文件夹启动 server，这个目录就凭空出现在哪儿；本机那次是 `cd web_app` 启动，看着正好在工具文件夹里，换成人双击快捷方式或从别处启动就会撒出去。② `Downloads\_musicdl_cache`（09-23 18:15 建）—— musicdl 的搜索结果 pkl 与「已下载但还没归档」的临时成品一直写在用户下载目录里，文件页得靠 `_hide_names` 专门列名把它们藏起来。③ `Downloads\_preview`（09-18 19:18 建）—— 点「试听」时那份临时音频副本也写进下载目录，而且永不清理。现在三处都收进工具文件夹：新增绝对常量 `MUSICDL_OUTPUTS`（锚在 `music_search.py` 自己所在目录，不再可能受 CWD 影响），`musicdl_cache_dir()` 不再往 `base` 下面挂 `_musicdl_cache`，改为统一落到 `MUSICDL_OUTPUTS/_musicdl_cache`，并按 `base` 的末级名分格 —— 批量下载与试听各扫各的格子，避免两件事同时在跑时把对方的文件当成本次的成果（`collect_and_promote_downloads(cache_root, final_dir)` 本来就分开收这两个参数，缓存搬到哪儿都不影响归档目标）；试听副本改落 `web_app\_preview`，并因它不再被用户直接看见而加了「只留最近 20 份」的自清。幂等性保持：调用方常把 `musicdl_cache_dir()` 的结果再传回来，重复拼接会让写入目录与归档扫描目录对不上、成品只能烂在缓存里。离线自检 `tests/matchround_test.py` 新增 P 段 7 项（整个文件 50 项全绿）：P1 验常量绝对且锚在模块目录，P2 反向验证 —— 源码里再出现相对的 `"musicdl_outputs"` 字面量即红，P3 验 musicdl 客户端默认工作目录就是那份绝对路径，P4 验下载目录里不再长出 `_musicdl_cache`，P5 验幂等，P6 验批量与试听分格，P7 验不再拼出 `musicdl_outputs/musicdl_outputs`。改动前的遗留产物已各自收口：`Downloads\_musicdl_cache`、`Downloads\_preview` 以及工具文件夹里的 `X`、`master` 四处在动手清理前都确认过是空的，只用 `rmdir`（非空即失败）删掉；下载目录（本机配置的是 `web_app\Downloads`）里那 7 个 `_1` 副本本次复查时已经不在了（`find Downloads -name "*_1.*"` 返回 0 条），那是用户自己清的，程序与本会话都没有删过任何成品。
- **上一条把缓存搬走之后，批量下载只剩歌词、歌曲被程序自己删掉（1.2.7 包后补）**：09-23 19:16 那批（Spotify 歌单 9 行、按曲名匹配上 6 首）跑完，下载目录里只有 6 个 `.lrc`，既没有 mp3、也没有按 `{artist}/{name} - {artist}` 归位，资源库里同样查不到，而运行日志里那 6 行 `musicdl 已下载: …mp3` 一条不少 —— 也就是说界面报的是「成功」。根因是上一条搬家留下的口径没跟上，四环串在一起：① `_guard_song_paths()` 仍按「落点在下载目录内才算合法」判定，而缓存格子自上一条起已经搬到 `musicdl_outputs` 下，于是**每一首正常曲目都被判成「要把文件甩出下载目录」**（日志里那 6 行「曲名「她說」会让文件落到下载目录外面…已改成「她說」」改前改后同名，就是这个误判的形状）；② 误判把 `work_dir` 改写成下载目录根，musicdl 就把 mp3 直接写在 `Downloads\` 上；③ 归档那步 `collect_and_promote_downloads()` 算出的目标路径与源路径是同一个文件，撞上「同名 + 同大小 = 重复」那条分支，`p.unlink()` **把刚下完的这首删掉了**，返回值却仍是这个已不存在的路径；④ `_finish_one()` 拿着悬空路径照样写「已下载」并在原地补一个 `.lrc`，`server.py` 的 `finish()` 第一句 `if not pp.is_file(): return` 静默返回，于是没有重命名、没有标签、成功数不计、资源库不入库。三道各自收口：新增 `_download_dir_ok()`（在下载目录内**或**在工具自己的输出目录内都算合法，守卫不再误判正常曲目；只有两处都不在才收回，且这时才写「已收回下载目录内」）；新增 `_same_file()` 并在归档那三处删除前各问一句（源＝目标时把这份认成成果返回，真·重复仍然只留一份）；`download_songs` 收到路径后先验文件在不在，不在就落一条 `归档后文件不见了：…（这一首按失败算，目录里没有留下成品）` 的 error 并把这一首改判失败，`server.py` 那边也同步写 `第 N 首没有成品文件可收尾（路径）——没有重命名、也没有入库`，两层都不再允许假成功。**为什么整条测试线没抓到**：`tests/matchround_test.py` 与 `spotifylist_test.py` 的 `_musicdl_cache` 打桩仍建在下载目录里，那是缓存搬家之前的形状 —— 桩比真对象宽松，守卫在里面首首都「合法」，这条回归从原理上就测不出来。Q 段因此改用真的 `musicdl_cache_dir()` 算落点：Q0 先钉住「缓存格子确实在下载目录外」，Q1/Q2 验正常曲目一首不改、两首 mp3 真落在下载目录，Q4 验源＝目标时文件还在，Q5 验真·重复没被放宽（不同文件、同名同大小仍只留一份），Q7 验两处之外才写「收回」，Q8 验悬空路径按失败算且不报「已下载」；反向验证三条 —— Q3 拿掉 `_same_file` 问句成品当场被删、Q6 真会塌成盘根的曲名照样在递交前被改名、Q9 把守卫口径与 `_same_file` 一起退回旧写法则线上那个形状整个重现（第三道兜底只保证它不再被报成成功，删掉的文件回不来）。本文件由 49 项增至 59 项，`spotifylist_test.py` 77 项 / `playlistdup_test.py` 40 项 / `music_endpoint_test.py` 8 项 / `music_sources_test.py` 20 项均仍全绿。**当场损失**：那 6 首 mp3 是程序删的，磁盘上无法恢复，要拿回必须重新下；`web_app\Downloads` 根上留下的 6 个孤儿 `.lrc`（`她說 / 愛人錯過 / 起風了… / 那些你很冒險的夢 / 不為誰而作的歌 / 回到過去 - Live`）等用户确认后再清。**界线**：以上为离线自检结论。19:47:25 重启（新进程 PID 24020）后用真配置、真网络跑了一批复核线上表现（匹配源 Spotify、下载源网易云 / 咪咕，3 首）：`GET /api/music/download_status` 回 `total 3 / done 3 / ok 3 / dup_skipped 0 / already 0 / skipped 0`，用时 134.9 秒；下载目录前后 diff 是**新增 9 个文件、消失 0 个文件**（三首各自 `曲名 - 歌手.mp3`/`.flac` 加歌词与封面）；三份成品都按 `{artist}/{name} - {artist}` 落进歌手续目录（`周杰伦, 浪花兄弟\你是我的OK绷 - 周杰伦, 浪花兄弟.mp3` 11,263,699 字节、`告五人\爱人错过 - 告五人.flac` 214,789,678 字节、`陈颖恩\那些你很冒险的梦(中国新歌声) - 陈颖恩.mp3` 10,209,321 字节）；日志逐首走满 `已归档 → 重命名 → 歌词 → 自动标签`，那批里再没有出现「曲名「…」会让文件落到下载目录外面…已改成…」这行误判（它只出现在 19:16 那批、也就是改动生效之前的记录里）。**同一批复核「入库」这半边时，另外查出一个独立缺口**（无损成品在资源库里看不见），见下一条。
- **无损成品（`.flac` / `.opus`）在资源库里看不见（1.2.7 包后补）**：接着上一条复核「入库」这半边时发现，`告五人\爱人错过 - 告五人.flac`（214,789,678 字节）确实在下载目录里、按模板归进了歌手续目录、歌词与封面也都在，`GET /api/library` 的 82 条里却没有它 —— 界面上「资源库」这一页压根不知道这首歌存在。根因是 `server.py` 的 `scan_library()` 自己另写了两份窄音频口径，比下载链真正会产出的那份少：① 决定「哪些文件算媒体」的 `media_ext` 里没有 `.flac` 与 `.opus`，无损成品连被扫进清单的机会都没有；② 决定「算音频还是算视频」的 `kind` 判定又是一份单独写死的字面量（只有 mp3/m4a/aac/wav/ogg），即便文件被扫进来也会被标成「视频」，资源库那页顶部的「音频 / 视频」筛选照样找不到它。现在两处共用同一个来源：`audio_ext` 直接取 `music_search.MUSIC_AUDIO_EXTS`（下载链产出什么，资源库就认什么），`.webm` 在这份常量里属于音频、但资源库这一页它历来按视频处理，因此单独排除后再并回视频那组，`kind` 与 `media_ext` 用的是同一个 `audio_ext` 集合，不再各抄一份。新增 `tests/library_scan_test.py` 14 项：A1/A2 验七种音频扩展名全部进库且 `kind` 全为 audio，A3/A4 验歌手续目录里那首 `.flac` 扫得到、`rel` 是相对下载目录的路径（前端按它显示层级），B1/B2 验七种视频扩展名不受这次放宽影响、`.webm` 仍算视频，C1/C2 验歌词 / 封面 / 文本与隐藏文件不混进来，E1/E2 验缓存只写到顶替路径、真实 `library_cache.json` 的 mtime 分毫未动；反向验证 D1–D4 —— 把 `MUSIC_AUDIO_EXTS` 临时退回修复前那份窄字面量，`probe.flac`、`probe.opus` 与歌手续目录里那首 `.flac` 三条当场从结果里消失（`probe.mp3` 仍在，说明不是整段音频被关掉），恢复常量后三条原样回来，并钉住「音频集合就是那份常量去掉 `.webm`」，防止以后又有人抄出第二份字面量。**界线**：以上为离线自检结论；`scan_library()` 跑在 `server.py` 进程里，界面要重启后点「重新扫描」才看得到 `.flac`。用来复核的那三个成品在 20:01–20:02 已被移入回收站（用户在本机的操作，本会话没有删除过任何文件），所以这条的线上读数要等下一次真有无损成品落地时再核。
- **同一首歌隔一天再点整张歌单，会多出一份 `曲名_1.mp3`（1.2.7 包后补）**：本机 `Downloads` 里实测到 7 对同名成品，例如 `Eason Chan\十年 - Eason Chan.mp3`（09-22 22:53:44）与 `十年 - Eason Chan_1.mp3`（09-23 16:54:23）—— 两份都 8,201,694 字节，是同一首被下了两遍；而 `淘汰 - Eason Chan.mp3`（11.28MB）与 `淘汰 - Eason Chan_1.mp3`（11.86MB）大小不同，说明**只比文件大小根本认不出重复**（换源重下同一首，码率常不一样）。根因只有一行：归档那一步 `finish()` 发现模板算出的目标路径已经存在，就直接改名成 `曲名_1`，既没跟目录里那份比过，也没在开始下载前问过一句「这首是不是已经有了」—— 于是 50 首的歌单点两遍，第二次照样整批下完、整批留副本。现在三道都改了：① **下载前先比目录** —— `music_search.find_existing_music_targets()` 用界面上那个命名模板（`music_filename_template`，默认 `{artist}/{name} - {artist}`）算出每首歌的目标路径，去那个目录里找同名音频文件（按文件名比，扩展名不同也算命中，mp3 / flac / m4a 等八种都认）；命中的行在建后台任务之前就从清单里摘掉，日志用「表头 + 每行 10 首」整份列出是哪几首（不是只报前几首），数量记进 `_MUSIC_JOB["already"]`，随 `GET /api/music/download_status` 与整批回执一起带回界面；如果一批里首首都已经有，就不起线程、当场回「这 N 首在下载目录里都已经有了，没有重复下载」。② **归档改成整只替换** —— 原来那句改名成 `_1` 换成 `music_search.promote_music_file()`：目标已有就把旧那份整个替掉，并写明「目录里已经有一份（旧字节数），这次这份（新字节数），已用这次的替换，没有另存副本」，磁盘上不再出现第二份同名文件。③ **界面上有开关** —— 音乐清单「共 N 条」右边新增「跳过已下载的歌」勾选框（默认勾选，随本次请求提交 `skip_downloaded`，不必保存策略），日志与回执里那句「取消勾选清单上方的『跳过已下载的歌』」指的就是它；行内单首「下载」则显式传 `skip_downloaded: false` —— 点到具体某一首是明确的一次重下动作，不该被跳过，重下的结果由②替换旧那份。**判不了重就不拦**，四种情况一律照常下载：模板里带 `{id}` 或 `{source}`（每首路径都带来源，「同名即同一首」这个前提不成立）、曲名拿不到或缓存查不到、目标目录还不存在、目录里只有 `.lrc` / 封面这类附属文件而没有音频成品。离线自检 `tests/matchround_test.py` 新增 O 段 13 项（整个文件 43 项全绿）：O1/O2 验「三首各自认各自的目录、换歌手不误伤」，O5 验「只有曲名的占位条目走同一套」，O6 验「歌手是列表时按逗号拼接后仍然对得上」（真 `SongInfo.singers` 就是列表），O9 专门盯上面那条大小不同的实测对（字节数不同照样认出），O11/O12 验「替换后目录里只剩一份、且新旧字节数都写进日志」；反向验证四条 —— O3/O4 模板含 `{id}`、`{source}` 时判重整个关掉、O7 曲名拿不到的行不许被拦、O8 目录不存在时一首都不跳、O10 只有歌词文件时不许当成已有。**界线**：以上是离线自检的结论。18:57:20 重启后（PID 39168）又拿**真配置**跑过一次判重：`music_filename_template` = `{artist}/{name} - {artist}`、下载目录 = 本机那份，喂进 `十年 / 淘汰 / 愛情轉移 / 因為愛情 / 穩穩的幸福 / 富士山下 / 好久不見` 七行，七行全部命中（如 `十年 - Eason Chan.mp3` 8,201,694 字节、`淘汰 - Eason Chan.mp3` 11,283,583 字节），另造的一行「肯定never_exists的歌」不命中 —— 也就是这道预检对用户目录里真实存在的成品是认得的。仍待回填的是整批下载时那条「有 N 首…已经有一份同名成品」的日志、以及 3000s 预算与未完清单的线上读数，这两项要等下一次真实的批量下载（与「重启后回填三条线上下列读数」同批）。另外那 7 个 `_1` 副本现在的实测状态：在下载目录（`web_app\Downloads`）里 `find . -name "*_1.*"` 返回 0 条，七首歌各只剩一份，且留下的那份修改时间仍是 09-22 22:53 / 22:54（也就是 09-23 16:54 那批旧代码下出来的 `_1` 被清掉了，程序与本会话都没有删过任何成品）。因此「目标已有文件就整只替换、不再改名留副本」这条路径至今只有离线自检覆盖，线上读数仍要等下一次真实批量下载。

---

## v1.2.6 · 2026-09-21

本版是一次以「界面收口 + 可排障」为主的发布：功能面没有新增引擎，全部精力放在把 16 个页面统一成同一个产品、让每一次页面操作都能在运行日志里找到痕迹。

### 界面与主题

- **可切换主题**：5 套主题色 —— 年度蓝（默认）/ 活力橘 / 流行粉 / 草地绿 / 陶土色，每套再分明亮与暗色两档；选择写入配置键 `ui_theme`（暗色为独立键 `dark_mode`）。主题令牌挂在 `body[data-theme]` 上，`--accent`、`--accent-soft` 与 Element Plus 的整条 `--el-color-primary` 色阶由 `color-mix` 派生，因此新增控件不需要单独适配主题。
- **按钮只有一种语言**：每行只有一个实心主按钮（带图标 + 加粗），同行其余按钮一律同形状描边，破坏性动作为红描边；绿色/琥珀色降级为纯状态色，只出现在状态标签和状态点上。全站表格行内不再有 `link`/`text` 型按钮。
- **文件页行操作收口**：常用三项（播放 / 打开 / 删除，目录为进入 / 打包 / 删除）带框直出，其余 15 项动作收进「更多」下拉。
- **复选组改成卡片**：分组标题 + 已选计数 + 组级全选/半选三态，替代原来散落的裸复选框。
- **设置页与通知设置重排**：一屏一节即一张卡片（13 + 5 张平级卡片，废除巨型卡片套多层内嵌面板）；Telegram / 企业微信通知设置改为「常规 / 通知」双标签 + 分组复选卡。
- **首页收成 4 行**：「开始下载 / 全部停止 / 仅排队，稍后下载」并入顶部「媒体链接」卡右侧的独立区块，删掉页面底部那张只放三个控件的「开始」卡——填完链接不必再滚到底部才能提交；「输出偏好」与「快捷预设」左右对调；「运行状态」上移一行与「字幕语言（可多选）」同行，字幕卡按选项隐藏时它自动铺满整行，不留空档。
- **全站节奏统一**：卡片间距 14px、圆角三档（18 / 14 / 10）、控件尺寸两档（small 24px / large 44px，新增控件默认 small），表格表头样式在文件 / 资源库 / 收藏三张表统一。
- **排序做成真排序**：`el-table` 与原生 `.fmt-table` 的表头均可点击升降序，中文标题先剥离行首 emoji 再按 `zh` 排序；去掉原先的下拉式假排序与会造成箭头/数据不一致的第三态。
- 提示文案整体收敛为「书面但易懂」：指代落到具体控件名，报错保留全部技术事实。

### 可排障性

- **所有页面操作进运行日志**：前端埋点走 `POST /api/ui_event`（日志加 `[界面] ` 前缀，单条 200 字上限），任何非 GET 的接口调用由 `api()` 自动按动作名记一条，失败时降级为 warning；后端补齐文件类动作记录（`[文件] 打开 / 已删除 / 删除失败 / 已清空下载记录`）。
- 埋点红线：日志不含 Bot Token、Secret、api_hash、密码、Cookie 内容、SendKey；`/api/config` 只记变更的键名与数量。

### 功能

- **通知按档开关**：Telegram 与企业微信各自有「下载完成 / 下载失败 / 订阅有新内容」三个独立开关（配置键 `telegram_notify_*`、`wecom_notify_*`），完成/失败不再被 Server酱绑在一起；Server酱仍只在下载完成时发送。
- 硬字幕烧录、AI 流水线单步重跑、订阅按条规则与日期窗、Telegram MTProto 会话等能力在本版继续可用，接口未变。

### 修复

- 表单项内的块级提示文字被 flex 挤到按钮右侧折行 —— 现强制换行至控件下方。
- 语音工具卡片标签与选择框重叠（`label-width` 固定 100px 撑不住长标签）—— 改为 `label-position="top"`。
- 设置页「按平台代理」表格：`table-layout:fixed` + `width:100%` 下未指定宽度的「当前代理」列吃掉全部富余宽度，导致「手动覆写」下拉框贴着卡片右缘、中间一条空白 —— 现把两列对调，由末列吸收富余宽度，下拉框紧跟「本次结论」，窄容器下也不再溢出卡片。
- 输入框高度不一致、暗色模式下 Cookie 分区配色不统一、按钮宽度不含文字、页面滚到底出现白条等问题已一并修掉。
- 「语音 → 音频分析」的即时回复过去固定写「结果写日志与 JSON」，而请求体传 `write_json=false` 时并不落那份 JSON —— 现在这句话按参数拼（`server.py:7953`）。界面那一路固定传 `write_json: true`（`static/index.html:7081`），所以界面上看不出差别，这条是探针直接调接口时读出来的。

### 首页与发布物

- **删掉首页「环境与工具」卡**（检测环境 / 更新 yt-dlp / FFmpeg / N_m3u8DL-RE / Whisper / Cookie / 下载浏览器扩展）：上方「运行状态」卡已自动读取这些版本号，重复入口属于噪音。工具的安装与更新统一走 **设置 → 组件与依赖**，功能一个没少。
- **修掉一个只在便携包里才暴露的缺陷**：`diarize_tools.py`（声纹说话人分离）没被列进入包清单 `APP_PY`，本机一切正常、对方点「说话人分离」会直接 ModuleNotFoundError。现已补入，并新增出包自检 `check_module_imports()` —— 用包内 runtime 把每个顶层模块真 import 一遍，缺文件或依赖不对当场中止出包。
- 便携包发布：`pack_release.py` 产出的包内新增 `CHANGELOG.md`；包内 pip 会真装真卸做一次自检（`selfupdate_probe`），打包后的服务会真起一次打两个接口做冒烟（`smoke_test`），并在收尾扫描 `config.json` / `cookies.txt` / `app.log` / `history.json` / `library_cache.json`，混入即中止。

### 已知限制

- 列表分页固定每页 50 条；收藏 / 关注一次性取回的条数有上限（B 站收藏夹 500 条、关注列表 2000 条、YouTube 播放列表 200 条），超出部分不会加载，此时表头的排序与下方翻页只对已加载的部分生效，界面会在表格上方给出截断提示。
- 内嵌 Python 的便携包不带 Whisper 模型与 `faster-whisper`（体积数 GB），首次使用需在设置里点安装。
- 音乐源中的 Spotify 歌单无法整单下载（DRM 下 yt-dlp 拒收），只做「列出曲目 + 跨平台按曲名匹配下载」。
- Telegram 频道若开启了「限制保存内容」，程序不会去绕这个保护；能纳入批量的只有你自己账号正常可访问的频道。

---

## 更早版本

v1.2.6 之前的迭代（字幕嵌入、下载完整性校验、失败原因人话化、按站点自适应并发、PO Token 门控、订阅规则、Telegram 爬虫与 MTProto、语音工具与声纹分离、便携包脚本等）未在本文件逐版留档，功能全貌请以 `README.md` 为准。
