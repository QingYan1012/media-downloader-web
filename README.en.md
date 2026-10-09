<div align="center">

# MediaDownloader Web · 多媒体下载器 Web

**Link parsing & download · page sniffing · cross-platform music · subtitles & AI · voice tools · subscription tracking**

A media downloader and processor that runs entirely on your own machine: paste a link and it downloads, and the browser handles queues, m3u8 captured from pages, music lookup by song title, subtitles, transcription and subscription tracking.
Settings, cookies, history and downloaded files all stay in the folder the program runs from — nothing is uploaded anywhere.

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue)](LICENSE)
[![Version](https://img.shields.io/badge/Version-v1.2.9-informational)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.12-green)](requirements.txt)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Docker-blueviolet)](#get-started-in-30-seconds)
[![Storage](https://img.shields.io/badge/Data-100%25%20local-lightgrey)](#privacy)

<p>
  <img src="docs/screenshots/home-light.png" alt="Download & parse page: paste media links and resolve them into selectable formats, with output preferences and add-on switches on the left, presets and fine control on the right" width="100%" />
</p>

[中文（主文档）](README.md) · English

</div>

> **Note on UI language.** The interface itself is Chinese-only (labels are given below with English glosses). This file documents behaviour; it does not translate the app.

This tool does **not** bypass login walls, paywalls, DRM or human-verification challenges. It never executes a site's JS challenge and never forges its anti-bot signature. Full boundaries: [Out of scope by design](#out-of-scope-by-design).

## Contents

- **Start**: [Get started in 30 seconds](#get-started-in-30-seconds) · [What is in the portable package](#what-is-in-the-portable-package) · [Screenshots](#screenshots)
- **Capabilities**: [Features](#features) · [The 16 pages](#the-16-pages) · [Download & queue](#download--queue) · [Cookies & site logins](#cookies--site-logins) · [Network & proxies](#network--proxies) · [Music](#music) · [Telegram](#telegram) · [Subscriptions](#subscriptions) · [Subtitles & AI processing](#subtitles--ai-processing) · [Voice tools](#voice-tools) · [Browser extension](#browser-extension) · [Components & dependencies](#components--dependencies-updated-from-inside-the-app) · [Resolver plugins & aria2](#resolver-plugins--aria2) · [Notifications](#notifications) · [Themes](#themes)
- **Development**: [Offline self-tests](#offline-self-tests) · [Repository layout](#repository-layout) · [Common API endpoints](#common-api-endpoints) · [Contributing](#contributing)
- **Boundaries & licence**: [Privacy](#privacy) · [Known limitations](#known-limitations) · [FAQ](#faq) · [Out of scope by design](#out-of-scope-by-design) · [Acknowledgements](#acknowledgements) · [License](#license) · [Disclaimer](#disclaimer)

## Get started in 30 seconds

**Windows, no install (recommended)**

1. Download `MediaDownloader-1.2.9-portable.zip` (~218 MB) from [Releases](https://github.com/QingYan1012/media-downloader-web/releases/latest).
2. Unpack it to a path with no non-ASCII characters and no spaces, and not under `C:\Program Files`.
3. Double-click `启动.bat`; `http://127.0.0.1:8765` opens by itself after about 3 seconds.

The archive bundles the Python runtime and pip, FFmpeg / ffprobe, yt-dlp, N_m3u8DL-RE and fpcalc, and generates a clean default configuration on first start.

**From source**

```bash
pip install -r requirements.txt
python server.py
```

The app then serves `http://127.0.0.1:8765`. Changes to `.py` files need a process restart; changes to `static/index.html` only need a page reload.

**Docker (NAS / home server)**

```bash
docker compose up -d --build
docker compose --profile aria2 up -d   # optional: with aria2
```

Port already busy, a component missing, or you want member-tier audio? Each has a one-line answer in the [FAQ](#faq).

## What is in the portable package

The only real trade-off of the no-install route: the voice stack (faster-whisper plus models, Demucs, librosa) is gigabytes, so it is not bundled — every red-dot item installs on demand from **Settings → Components & dependencies**, no re-download needed.

<details>
<summary>Details: the three install routes, what is bundled and what is not, the privacy exclusion leak-scan, port override and unpack location</summary>

Three ways to get running; pick one.

| Route | Who it is for | How | After that |
| --- | --- | --- | --- |
| **Portable package (no install, recommended)** | Windows users who do not want Python | `MediaDownloader-1.2.9-portable.zip` (~218 MB) in this repository's [Releases](https://github.com/QingYan1012/media-downloader-web/releases/latest) | Unpack, double-click `启动.bat` (the launcher); `http://127.0.0.1:8765` opens in ~3 s. Bundles its own Python runtime **with pip**, plus FFmpeg / yt-dlp / N_m3u8DL-RE |
| **Run from source** | You already have Python 3.12 | `git clone`, then [Get started in 30 seconds](#get-started-in-30-seconds) | Put ffmpeg / ffprobe / yt-dlp / N_m3u8DL-RE into `tools/`, or install them from Settings |
| **Docker** | NAS / home server | `docker compose up -d --build` (optionally `--profile aria2`) | See [Dockerfile](Dockerfile) and [docker-compose.yml](docker-compose.yml) |

What the portable archive does and does not contain:

| Included | Not included (installable from inside the app) |
| --- | --- |
| Embedded Python runtime **and pip** | faster-whisper itself and the Whisper models (several GB) |
| `tools/`: ffmpeg, ffprobe, yt-dlp, N_m3u8DL-RE | Demucs / torch |
| Music stack: musicdl, mutagen, edge-tts, deep-translator, zhconv | librosa / numba (needed by "audio analysis") |
| Telegram stack: telethon, python-socks, cryptg | — |
| Audio fingerprinting: `chromaprint/fpcalc.exe` | — |
| `启动.bat`, `使用说明.txt` (usage notes), `README.md` / `README.en.md` / `CHANGELOG.md` / `LICENSE` | — |

- Anything shown as a red dot in **Settings → Components & dependencies** installs on demand with the bundled pip (or with "update all"), so a missing extra never requires re-downloading the package. Restart the launcher afterwards to load it.
- The archive **excludes all local data by construction**: no `config.json`, no cookies, no `Downloads/`, no history, no subscription records. A clean default configuration is generated on first start. The packing script runs a leak scan and aborts the build if anything private slipped in.
- Unpack somewhere that is not `C:\Program Files`, and avoid non-ASCII or spaces in the path (third-party libraries concatenate tool paths).
- Port busy? Create a `改端口启动.bat` containing two lines — `set MEDIADOWNLOADER_PORT=8899` and `启动.bat` — and double-click it.
- The Git repository holds source, docs and offline self-tests only. No binaries, no downloads: `.gitignore` uses a default-deny allowlist, so new top-level files are ignored until explicitly unignored.

</details>

## Features

**Downloading and streaming**

- Paste one link or a batch; it resolves to selectable formats and enqueues, with normalization and de-duplication. Queue-only mode is available.
- Queues support multi-select, pause/resume, pin to top, move to front and "later"; named queues get their own limits, plus a per-host concurrency cap, adaptive 429 throttling and a global speed cap.
- HLS / DASH segments go to the dedicated N_m3u8DL-RE engine (falling back to ffmpeg / yt-dlp); segmented streams can be range-trimmed.
- MKV by default: a single-file mp4 stream is losslessly remuxed, never re-encoded; post-download integrity verification kills "fake success".
- Optional embedded cover art, metadata, chapters and per-language subtitles, plus a sidecar `.vtt`; Bilibili videos also save danmaku as `.xml` and embeddable `.ass`.

**Sniffing**

- The bundled browser extension watches m3u8 / mp4 / ts / m4s requests and pushes the selected ones into the local queue.
- It also receives POST pushes from the third-party cat-catch sniffer and can import the regex rules from its settings export.

**Music**

- Multi-source search (each source has a time budget, and an empty result says why), lyrics / cover / tag writing by title, whole-playlist download, source switching, self-built favourites list.
- "Is this the same song?" is one scoring gate: title, artist and duration are scored separately and must clear an acceptance threshold; rejected candidates are logged with the reason.
- Local library index plus a persistent bottom playback bar; quality requirements reorder results, can refuse to fetch below spec, and finished files are re-verified from their own tags.
- The "lossless reference" adds Qobuz / Tidal **metadata only** (ISRC, duration, bit depth / sample rate, lossless flag) — not a byte of audio.

**Subtitles, AI and voice**

- Per-language subtitle selection, glossary-checked translations, smart line wrapping, bilingual export as SRT / VTT / ASS, hardsub burning.
- Four-stage AI pipeline: subtitles → polish → summary → translation, each stage written to disk and re-runnable on its own.
- Local transcription with speaker diarization (click a timestamp to jump), Edge-TTS dubbing, Demucs vocal / instrumental separation, audio analysis (BPM, key, loudness, spectral centroid), AcoustID fingerprint lookup.

**Automation and operations**

- Telegram: anonymous `t.me/s/` history listing, batch downloads through your own account session, and subscription tracking.
- Four subscription source types (RSS, web-page changes, Telegram channels, music playlists) scanned on a schedule, each with per-subscription rules.
- Three notification channels — Telegram Bot, WeCom, ServerChan — each with separate finished / failed / subscription switches.
- Components and dependencies update from inside the app (one-click batch update, plus an automatic upstream-version check when the app opens), mirror probing, and an operation log that records every UI action and rotates daily.
- 5 accent themes × light / dark; every bit of data stays local.

Which engine backs each capability area is in the table below and in the sections that follow.

<details>
<summary>Capability table: what each area does and what implements it</summary>

| Area | What it does | Backed by |
| --- | --- | --- |
| Parsing & download | Paste links, resolve to selectable formats, enqueue; multiple URLs at once with normalization and de-duplication; queue-only mode | yt-dlp, resolver plugins |
| Queue control | Multi-select, pause/resume, pin to top, move to front, "later"; named queues with per-queue limits; per-host concurrency cap, adaptive 429 throttling, global speed cap | built-in scheduler |
| Streaming | HLS / DASH segment downloads; sniffer-detected m3u8 goes to a dedicated engine; **range trimming works only on segmented streams** | N_m3u8DL-RE, falling back to ffmpeg / yt-dlp |
| Page sniffing | Browser extension watches m3u8/mp4/ts/m4s requests and pushes them to the local queue; also receives POST pushes from the third-party cat-catch extension | `extension/`, `POST /api/catcatch/push` |
| Output integrity | Mux to MKV by default (a single-file mp4 stream is losslessly remuxed, never re-encoded); post-download integrity verification kills "fake success"; every failure reason is phrased in plain language with the original error attached | FFmpeg |
| Extras | Embedded cover art, metadata and chapters; subtitle embedding per language plus sidecar `.vtt`; Bilibili danmaku saved as `.xml` and embeddable `.ass` | FFmpeg, mutagen |
| Music | Multi-source search, lyrics / cover / tag writing by song title, whole-playlist download, cross-platform title matching, source switching, self-built favourites list, local library index, persistent bottom playback bar | musicdl, mutagen, AcoustID / MusicBrainz |
| Same-song detection | One scoring gate: title, artist and duration scored separately, then combined against an acceptance threshold; rejected candidates are logged with the reason | built-in matcher |
| Audio quality | Quality requirements reorder results, can refuse to fetch below spec, and re-verify finished files from their own tags; the "lossless reference" adds Qobuz / Tidal **metadata only** | mutagen, ffprobe |
| Subtitles & AI | Per-language subtitle embedding, glossary-aware translation checks, smart line wrapping, bilingual export as SRT / VTT / ASS, hardsub burning, four-stage AI pipeline | faster-whisper, deep-translator |
| Voice | Local transcription with speaker diarization (voiceprint clustering), Edge-TTS dubbing, Demucs vocal/instrumental separation, audio analysis (BPM, key, loudness, spectral centroid), fingerprint lookup | faster-whisper, Demucs, librosa, chromaprint |
| Telegram | Anonymous `t.me/s/` history listing, MTProto session login for batch media from channels your own account can access, subscription tracking | telethon, cryptg |
| Subscriptions | RSS, web-page changes, Telegram channels and music playlists, scanned on a schedule and enqueued; per-subscription rules (type, duration, must-contain / exclude words, date window, quality, naming template, per-run cap) | built-in scanner |
| Library | Resource browser with playback and packaging, file browser, Bilibili / YouTube favourites & following sync, exportable download history | local scans |
| Notifications | Telegram Bot, WeCom, ServerChan — separate switches for finished / failed / subscription events | outbound push (keys local only) |
| Operations | Full operation log including every UI action (daily files, auto-deleted after 7 days, path shown in the UI with a one-click "open folder"), in-app component updates, mirror probing, 5 themes × light/dark | `pkg_update.py` |

</details>

## The 16 pages

The sidebar has 16 pages in 5 groups:

| Group | Pages | Purpose |
| --- | --- | --- |
| Download | 下载解析 (parse) / 队列 (queue) / 嗅探 (sniff) / 媒体信息 (media info) | Paste and resolve links, queue and pause/resume, capture m3u8 and mp4 from a page, inspect containers and streams |
| Acquire & process | 聚合搜索 (aggregate search) / 音乐搜索 (music) / Telegram 频道批量 / 直播录制 (live recording) / 语音工具 (voice) | Search several sources then pick one, fetch lyrics / cover / tags by title, batch channel history, record on-air streams with a managed-browser sniffer, transcribe and dub |
| Library | 资源库 (resources) / 文件浏览 (files) / 收藏关注 (favourites & following) / 历史记录 (history) | Search, play and package downloaded content, sync Bilibili and YouTube collections, export history |
| Automation | 订阅追踪 (subscriptions) | Scheduled scanning and enqueueing for RSS, web changes, Telegram channels, music playlists |
| System | 运行日志 (log) / 设置 (settings) | Complete operation log (UI actions included; daily rotation, auto-delete past 7 days, file location shown and openable from the page), cookies, network, notifications, components |

<details>
<summary>List behaviour: pagination rules, what header sorting covers, aggregate-search ordering and result caps</summary>

Lists longer than one screen (queue / files / history / aggregate search / music / Telegram / favourites / subscriptions / resources / web sniffing / live) paginate at 50 rows with previous, next and jump-to-page; the pager is hidden when there are fewer than 50 rows. Header sorting applies to the whole result set, not just the current page. Favourites / following fetch all upstream pages (Bilibili collections 500, following lists 2000, YouTube playlists up to 200); when a real cap is hit the table says so above it.

Aggregate search can sort by relevance, view count or publish date. Changing the sort re-fetches with the platform's own sort parameter (Bilibili `order`, YouTube `sp`) rather than re-ordering whatever the front end already holds. One platform, one content type returns 100 items per request; the aggregate result caps at 300, and the results area states how many the upstream returned when it was cut.

</details>

## Screenshots

Every image below comes from a **freshly unpacked, never-used instance**: no download history, no cookies, no subscriptions, and the save directory is the package default. The interface itself is Chinese-only; the page names are glossed in [The 16 pages](#the-16-pages).

| Music search: 24 platforms queried in parallel by song title, with match source and audio-quality gates | Aggregate search: keyword search across YouTube / Bilibili / Douyin with content-type filters |
| --- | --- |
| <img src="docs/screenshots/music-search.png" alt="Music search page: search box and source checkboxes on top, results and the user-built favourites list below" width="100%" /> | <img src="docs/screenshots/aggregate-search.png" alt="Aggregate search page: keyword box followed by three rows of platform, content type and sort filters" width="100%" /> |
| Telegram channel batch: list public channel history anonymously, or use a logged-in account session | Subscriptions: channels / playlists / RSS / music playlists in one table, new items download automatically |
| <img src="docs/screenshots/telegram-channel.png" alt="Telegram channel batch page: channel name, media type, item limit and date range before listing history" width="100%" /> | <img src="docs/screenshots/subscriptions.png" alt="Subscriptions page: paste addresses on the left, scan controls on the right, subscription table below" width="100%" /> |

Dark mode is the same application with inverted surface colours — the moon / sun button in the header switches at any time, and five accent colours are available (see [Themes](#themes)).

<p align="center">
  <img src="docs/screenshots/home-dark.png" alt="The download & parse page in dark mode, identical layout to the light theme" width="100%" />
</p>

## Download & queue

Paste → resolve to selectable formats → enqueue. If something this job must have is missing locally, pressing “start download” fails on the spot, names the exact row to install from, and creates no task at all.

<details>
<summary>Details: the pre-enqueue dependency check, named queues, per-host concurrency and where 429 throttling is triggered, global speed cap, MKV remux and integrity verification, why range trimming only works on segmented streams</summary>

- Multiple URLs can be pasted at once; they are normalized and de-duplicated. "Queue only, download later" enqueues without starting.
- **Dependency preflight before enqueueing**: if you press "start download" and this machine lacks something the job must use — yt-dlp for site resolution, FFmpeg for subtitle / cover / chapter embedding, MKV muxing or range trimming, faster-whisper for local transcription, N_m3u8DL-RE for HLS, telethon for `tgmt://`, or a download directory you cannot write to — the request fails on the spot, naming which row of **Settings → Components & dependencies** to install, and **no task is created at all**. The refusal is also written to the operation log. Cases that merely make things slower or lower-quality (no FFmpeg but a direct mp4 download) are not blocked; they get a log note.
- Queue: multi-select, pause / resume, pin to top, move to front, download later; task cards show "pinned" and "later" badges.
- **Named queues** `queue_name`: `default` / `night` / `subscribe` / `sniff` (configurable via `named_queues`; batch music uses `music`). Speed limits and gating can be set per queue.
- **Per-host concurrency cap** `max_per_host` (default 2) combined with **adaptive 429 throttling** `adaptive_throttle`: after a site rate-limits you, that domain is temporarily dropped to one concurrent connection and put into cooldown (duration taken from "risk control → 429 cooldown (seconds)", which is also the value used for anti-bot challenge-page classification). A "site throttled" bar appears at the top of the queue page and can be reset immediately. Triggers are not limited to HTTP 429 inside the download loop: a Douyin search classified by `risk_control` as "rate limited" or "anti-bot challenge page" marks the same throttle point, as does a download failure in either category. A "login required" verdict deliberately does **not** mark the point, because slowing down does not help. The Douyin search entry checks this table **before** sending anything: while still in cooldown it repeats the previous verdict on screen (`本次没有再向它发请求`), sends zero requests and does not add another strike — otherwise every extra click would extend the penalty on the same domain, and retrying is the only action available to the user. To really search before the cooldown expires, click "resume now" on the throttled bar.
- **Global speed limit** `global_speed_limit` (e.g. `2M`) — either this or the per-task `speed_limit`.
- MKV by default: when the site offers a single mp4 stream the file is only losslessly remuxed, never re-encoded. Downloaded files are verified for integrity to prevent "fake success"; failure reasons are translated into plain language with the original error attached.
- **Extras** checkboxes: embed cover thumbnail (`thumb`), metadata (`embed_metadata`), chapters (`embed_chapters`). Bilibili videos additionally save danmaku as `.xml` plus an embeddable `.ass`.
- **Range selection** `download_section`: enter `00:01:00-00:02:30`. Under the hood this uses yt-dlp's `download_ranges` with a forced `*` auto-segment prefix, **so only HLS/m3u8-style segmented streams can be trimmed**; for single-file streams the parameter is ignored and the task log says so.

</details>

## Cookies & site logins

Sites that need a login are handled with cookies, either read straight from your own browser or a Netscape-format `cookies.txt` dropped into `cookies/`. Music-platform login cookies are stored per platform and never leave the machine.

<details>
<summary>Details: browser-read constraints, the YouTube bot check, how Douyin's no-cookie responses are classified, the three-state display and merge rules for the three music-platform cookies</summary>

Two ways, pick either:

1. Settings → Cookie → "read from browser" pulls cookies for sites you are already logged into (Chrome must be fully quit for its cookie store; Edge / Firefox need no shutdown).
2. Drop a Netscape-format `cookies.txt` into the `cookies/` directory — it is read by default, no setting to change.

Without cookies, YouTube hits the "sign in to confirm you're not a bot" wall (resolution fails, or only 360p is offered). That is a site-side restriction, not a bug.

Cookie-less Douyin search returns two shapes in local testing: the search API answers HTTP 200 with `{"status_code":2483,"status_msg":"请先登录，再继续搜索吧"}`, and the search page HTML is a ByteDance JS challenge page (`Set-Cookie: __ac_nonce`, body containing `byted_acrawler` / `__ac_signature`). Neither means "this content does not exist". Such cases are now classified as login-required / anti-bot challenge / rate-limited / API error / genuinely empty, with the reason shown in the aggregate search results area and the basis recorded in the log; download failures use the same classification vocabulary. This is identification and reporting only: the program never executes JavaScript handed down by a site and never forges a signature.

The music side keeps its own per-platform cookies under Settings → "音乐平台登录 Cookie" in three separate fields (NetEase Cloud Music / QQ Music / Kugou). Leaving them empty just means the free tier. The NetEase field offers "get by QR", using NetEase's own login QR (confirm in the mobile app, then press "check scan status" to import the session) — no third-party login service is involved. QQ Music and Kugou have **no** QR flow: their QR endpoints require an anti-bot signature, and forging one would cross the line, so you still copy-paste from browser dev tools. Each field reports tri-state "logged in / missing key fields / not configured" based on the keys that platform actually needs and names the missing ones (e.g. "missing token or userid, this source cannot reach member quality"), so pasting a useless key string no longer shows as configured. These three cookies are merged with the global cookie above into one string for the downloader (each platform picks the keys it recognizes); a cookie pasted into the search box overrides only same-named keys and does not evict the saved login. Cookie values are written only into the local `config.json`; logs record key counts, never values, and `cookies/` plus that file are on the packing exclusion list.

</details>

## Network & proxies

Three proxy modes: automatic per platform (foreign through a proxy, domestic forced direct), always, or leave it to the system. Each platform can be overridden individually and the address actually in use is shown.

<details>
<summary>Details: the per-platform proxy table, one-click system proxy and what “reset the network” clears, mirror probing, TLS fingerprinting and the PO Token health gate</summary>

- Three proxy policies: `auto` (per platform: overseas through the proxy, domestic forced direct) / `always` / `none` (leave it to the system).
- In auto mode, **Settings → Network & concurrency → per-platform proxy** lists each platform and music source with this run's verdict, a manual override (auto / via proxy / forced direct) and the proxy address actually in effect; changes save and apply immediately.
- Reads the system proxy with a "use system proxy" button; "clear and reset network" only clears proxy addresses, per-platform policies and the sniffer list — cookies, history and tasks are untouched.
- **Mirror probing**: `/api/mirrors/probe` speed-tests the built-in GitHub / HuggingFace mirror candidates and picks usable prefixes; when direct access fails, the download tools try the built-in mirrors in order automatically.
- TLS fingerprint impersonation (curl_cffi), optional SSL verification skip, PO Token health gating and the `player_client` fallback chain are all configurable in Settings.

</details>

## Music

Multi-source search, whole-playlist download, cross-platform matching by song title, source switching and a self-built favourites list. This is the longest section: every rule about fetch behaviour, de-duplication, index caching and quality verification is inside the collapse.

<details>
<summary>Details: default and fallback match sources, every threshold of the scoring gate and its rejection reasons, playlist de-duplication and chunked batches, skipping songs already downloaded, when source switching rewrites a row, the local library snapshot index, quality requirements and the lossless reference, favourites list and filename template</summary>

Aggregate search and the music search page use `musicdl` for multi-source search (each source has a time budget; when a source returns 0 items the reason is put on screen), plus lyrics, cover art, tag writing, MusicBrainz lookups and AcoustID audio fingerprinting (`chromaprint/fpcalc.exe` is bundled).

### Cross-platform title matching: the scoring gate

Spotify playlists cannot be downloaded wholesale because of DRM, so the approach is "list the tracks only, then download each title by matching it on other platforms". Which platforms are searched is decided by **music search → parallel strategy → match sources**; the candidate list is identical to "search sources" and every one of them is selectable. The defaults are NetEase / QQ / Migu / Kugou / Kuwo (these resolve addresses on their own CDNs — find it and you can download it). Spotify and Apple are labelled "slow address resolution": their URLs come via third-party conversion services, single tracks do work in practice but take ~10 s each and fail often, so they are not in the default set. The fallback to the default five sources happens only when you specified no match sources at all, and it is stated in the log — it never silently switches platforms.

Deciding "is this the same song" goes through a scoring gate. Beyond three quick criteria there are thresholds: title and artist are **scored separately** — title similarity below 60 means two different songs, artist below 70 means a different person, duration below 25 (roughly 14 s apart) cannot be the same recording; when titles are not exactly equal the duration requirement tightens (below 50 is rejected, about 7 s), and the combined score must clear an 85 acceptance line. Duration acts only as a gate and never adds points — two different songs of identical length is far too common. The two fast paths remain: title + artist equal after normalization and duration inside `min(60 s, max(20 s, 12% of the full length))` (a 30 s clip may differ by 20 s, a 4 h podcast by 60 s); or titles match but artists differ, in which case durations must be near-identical (within 5 s). Version suffixes appearing on the finished file are hard-blocked — you wanted the studio version and the file says `(Live)` / `DJ` / `karaoke`, that is a different recording. The reverse is not blocked (the playlist says Live and the library entry omits the suffix, which is usually the same recording). When several candidates pass, the one with the highest `(score, quality)` wins, so lossy and lossless coexisting yields lossless. Rejected candidates are logged with the reason ("same title «XXX», different artist, duration off by 78 s", "«XXX» duration off by 78 s, outside tolerance", "finished file says live, not the same recording as annotated"), which makes "not found" distinguishable: no such song in the library, a same-title song rejected on duration, or a different artist.

### Playlist de-duplication and chunked batch download

When a playlist lists the same song several times, the list merges it into one row marked `×N` after the title (hover states how many entries it stands for, and the download fetches it once). "Download selected" also de-duplicates the manifest before starting, using the same rule (which covers picking rows in separate selections), and names the affected songs in the log (`下载清单里有 1 首重复（同一首歌排了两遍），只下第一遍：「晴天」×2`). The rule is the same as title matching: identical title + artist, then duration inside `min(60 s, max(20 s, 12% of the full length))`. Title and artist normalization flattens case, runs of whitespace and spaces around commas, but **does not strip version words such as `(Live) / 现场 / karaoke`**, so a studio version and a live version are never merged into one row — which would make one of them disappear from the list. Rows without a title are never merged, and rows whose cache entry cannot be found are always kept. The progress total counts the de-duplicated number; skipped duplicates are recorded separately as `dup_skipped`, apart from "no address obtained" failures, and the completion receipt reports the two facts separately.

"Download selected" proceeds in chunks of 6 songs, and each chunk is archived to the location its filename template points to as soon as it finishes — so the file page fills up while the batch still runs instead of at the end. This path does not enter the download queue; progress goes to the operation log (`下载进度 x/N（成功 k 首，已归档 i/j 片）`), and at the end the UI shows a receipt: "multi-select download finished: x succeeded, y had no address, z seconds elapsed" (plus "N were duplicates of the same song and were fetched once" when the manifest was de-duplicated). An error in the middle of a chunk does not void the chunk: already-written files are located on the spot and archived normally (`第 i/n 片中断后从缓存救回 k/n 首`), and the songs not yet on disk are each retried individually (`第 i/n 片逐首重试补回 k 首`), so one bad path does not take down innocent neighbours in the same chunk. The same error line is followed by the last three stack frames with standard-library frames (`os.makedirs` recursion and the like) stripped, so the caller is identifiable. The whole-round budget for title matching is 1500 s, widened to 3000 s when Spotify or Apple are among the match sources (their addresses go through a conversion service, ~10 s per song). Songs never reached before the budget expires are reported separately as "not searched this round" with a remedy (run it again, or use the fast default match sources) and are never merged into "not found by title". Both lists are printed in full in the log (header line, 10 titles per line — not truncated to the first 12) and the UI shows the same lists again at the end under the heading "tracks not matched by title". Before handing work to musicdl, each song's destination is checked: a title starting with `/` or `\` makes musicdl build a path that escapes to the drive root, and its `\\?\H:/` form then fails with `FileNotFoundError [WinError 2]`, taking the whole chunk with it — titles are sanitized here and the file is kept inside the download directory, naming the affected song in the log. A batch runs concurrently and the download library returns finished files in **thread completion order**, so "which file belongs to which song" cannot be positional. It is now resolved by title: the filename (after stripping the " - index (1)" suffix the library adds to avoid collisions, and after normalizing illegal-character replacement and path truncation) must match that row's title; a candidate is taken only if exactly one matches in that directory, and if none matches the song is counted as not downloaded rather than grabbing some other leftover file — the log lists each song whose file could not be identified.

Songs from a previous run still sitting in the download directory are not fetched a second time when you re-run the whole playlist: **"skip already downloaded"** (checked by default), to the right of "N items" in the manifest, scans the audio in the download directory before starting and puts every candidate through the same scoring gate on title / artist / duration. A row judged to be the same song by the same person is dropped from this run's manifest, the full list is written to the operation log with scores, and the receipt and progress line add "N songs already had a finished copy in the directory and were not fetched again". Unchecking it re-downloads. What is compared is the **song**, not the filename (the same track from a different platform usually differs in filename style and bitrate, and old copies stop matching after you change the naming template), and a different extension still counts as the same song (`.flac` on disk versus `.mp3` computed by the template). This directory check additionally requires the artist to match (`require_artist`): the same title by different people is usually genuinely a different recording (original versus cover), so title + duration alone is not enough. Untagged rows have their title guessed from the filename — and while the downloader's default template is "title - artist", the filename fallback splits "artist - title", the exact opposite direction, so those rows are also tried with the parts swapped (tagged rows have a trustworthy direction and are not doubled). To deliberately re-fetch one song use the per-row "download" button — a single explicit action is not bound by that checkbox. Four situations never block and download as normal: the template contains `{id}` or `{source}` (every path is source-specific, so equal names are not the same song), no title can be obtained, the target directory does not exist yet, or the directory holds only sidecar files such as `.lrc` or covers. Archiving no longer creates copies either: if a file already exists at the destination the old one is wholly replaced, and both byte counts are logged (the previous behaviour renamed to `title_1.mp3` and kept two).

If the address a row got on platform A will not download, or you want another platform to get lossless, use the row's "switch source"; for bulk edits use the toolbar's "switch source for selected". The backend re-searches the other match sources and **rewrites the row only if the candidate passes the scoring gate and the new address probes successfully** (no probe result means the row is left alone). A failed switch states in both log and UI whether title, artist or duration blocked it, and unmatched tracks are listed once more at the end of the batch. Rows produced by the local scan and "lossless reference" rows refuse this operation outright with a reason: the former is already a file on disk, the latter is metadata only — neither has an "alternative source" to switch to.

A row labelled Spotify may actually have been pulled from YouTube. This used to be visible only in the log; now the source column says so: such rows carry a "converted" marker, hover shows the full chain (`Spotify → YouTube`, `Spotify → spotsaver`), and the download log records that real route as well. The adjacent "block re-uploads" checkbox (off by default) is about something else: when on, a fetched file that does not match the row you clicked (different title or artist, or duration off by more than 3 s) is not downloaded, is logged on the spot and is listed at the end. Mind its boundary — it does **not** block "fetched from another platform via a conversion service" as such: Spotify and Apple have no official audio path at all, so blocking that category would mean a playlist downloads nothing. Only metadata mismatches (a re-upload of a different recording) can be caught, which is why it stays off by default.

### Local library and snapshot index

With "include local library" ticked, search results also include songs already in your download directory. This path now reads the **tags carried by the file**: everything mutagen can give (title / artist / album / duration / bitrate / sample rate / bit depth / embedded cover / embedded lyrics / tag type) is taken in one pass, ffprobe is consulted only for what it cannot give, such as bit depth, and filename guessing is the last resort — each row is marked as tag-derived or guessed. Parse results are cached by "path + byte size + mtime", and the whole scan index is stored as a **snapshot** under `local_index\` in the program directory, one file per scanned directory (the name is a hash of the directory path, so indexing several download directories never overwrites each other). **Nothing is written into your download directory any more**; a `local_music_index.json` left there by an older version is moved into the program directory on first read and the original deleted, and its records are reused rather than re-parsed. Search uses snapshots younger than 5 minutes by default: a hit is returned immediately without even walking the directory. When the snapshot is stale, the **previous snapshot is handed to the UI first** (thousands of songs still open in milliseconds) while the re-scan runs on a background thread, one thread per directory at a time, so the next query gets fresh content. Moving a file computes its age from the file's original mtime, not from the moment it was moved, so an index made an hour ago is still correctly recognized as stale. To rescan right now press "scan local library" — it bypasses the snapshot, and the result states how many songs were found and where the index file is; if the background is scanning that same directory at that moment, the button joins that run and waits for it (up to 90 s) instead of returning numbers you already see. Ordinary searches and the "skip already downloaded" check never wait on a scan. The "skip already downloaded" check ignores snapshots and rescans current disk state every time, so a song that just finished cannot be hidden by a stale snapshot and re-downloaded the next day; after a batch finishes, the snapshot is refreshed in the background. All these differences matter more as the library grows.

There is exactly one place to listen: clicking "preview" on a music result row or a favourites row puts the controls in the **persistent bar at the bottom of the window** (current title and artist, cover, progress bar and time, previous / play-pause / next, volume and mute, close). Switching pages does not hide it and does not restart playback in a new player. The spacebar toggles play/pause, except when focus is in an input, textarea or select, when it is on a button or link, or when any dialog is open. When a track ends the next one in the same list's queue plays automatically; with no next item it stops. At the end of a batch download, songs blocked by "skip already downloaded" are listed row by row in a dialog: title → the filename already in the directory, with the matching score and the title found there, ending with the hint to uncheck "skip already downloaded" above the manifest if you wanted a re-download.

### Quality requirements and the lossless reference

With "lossless reference" ticked, every search additionally queries the Qobuz / Tidal official catalog metadata once: title, artist, album, exact duration, ISRC, bit depth and sample rate, lossless flag, official link. What local results lack most is "how long should this actually be, and is there a lossless version", and musicdl's own Qobuz / Tidal sources require account tokens — logged out they return 0 items — so this path supplies exactly that one thing. **It stops at metadata**: the audio step sits behind a third-party human-verification gate that was put there deliberately, so the program does not obtain verification tokens, does not bypass the check, and does not touch any credentials. Such rows are easy to spot: the source column reads "Qobuz·ref", hover lists ISRC, bit depth/sample rate, exact duration, version note, release date and label, always ending with "read-only, audio is not downloaded from this row", and the action column is "official page" (it opens only the platform-provided official link). They cannot be selected and never enter the download or matching path.

The **"quality requirements"** dropdowns in "parallel strategy" (format / bit depth / sample rate / bitrate) plus "do not download below spec" do three things that are possible, and the one that is not possible is stated first: **this layer cannot pin which tier a platform hands you** — each source's quality tier is a constant hard-coded in musicdl's source classes, and when building a client the only things you can pass are search size, retry count, working directory and cookies; there is no entry point for "give me 24-bit". So the requirement does not pretend to pin anything; it does exactly three things: (1) when several platforms have the same song, the tier that meets the requirement is ordered first; (2) with "do not download below spec" ticked, a song whose **platform-declared tier is confirmed below** the requirement is never handed over, and the log names the song and which dimension failed; (3) after a file lands, its **own tags** are read to verify the actual tier, which also catches a lying label (a 128k MP3 wearing a flac name) — the verdict is appended to that row's "downloaded" log line and listed again at the end of the batch. Two rules are fixed: if a dimension **cannot be read, that dimension does not disqualify anything** and is reported as "not verified" (otherwise every source that does not self-report would be skipped by "lossless only", which would treat "unknown" as "failed"); and **lossless files are not judged by bitrate** (16-bit/44.1 kHz flac is already above 900 kbps, platforms often do not report a bitrate for lossless, and gating on bitrate would classify the best tier as failing). With "lossless reference" ticked, each result and each finished file is also compared against the Qobuz / Tidal row on bit depth / sample rate / lossless — again metadata only, no audio at all. That comparison passes the same scoring gate first: if the reference row's duration does not line up, the verdict is "no comparable reference" rather than "below reference", because that is a different recording, not a lower quality, and the conclusion carries the reference ISRC so you can check the official page yourself. The tier tables exist in one place in the backend and the UI renders them from the status endpoint, so the two cannot disagree. To re-check files already on disk, open the resource library and press "verify quality": every audio file in the current filter has its own tags read, and the verdict hangs on that row's "quality" column (below requirement / meets / not verified / file missing), with a summary line above the card giving counts. That endpoint accepts only paths inside the download directory; one out-of-bounds path rejects the whole batch and states where the directory is.

"More → fingerprint" on the file page uses the bundled `chromaprint/fpcalc.exe`, so you do not need to add it to PATH ("add to PATH" only affects terminals opened afterwards; a running service will not pick it up). The settings field wants the **application** client key (registered at acoustid.org); the user API key you see after logging in is rejected by AcoustID as `invalid API key`. Missing fpcalc, a rejected key, and a file with no audio track all produce an immediate dialog on click instead of "fingerprinting…" followed by a buried log line.

### Favourites list and filename template

Clicking "favourite" on a search result row accumulates songs found across platforms into your own list: the manifest card supports whole-list download, per-row and bulk source switching, and remembers tracks that were not found last time. The list lives in the local `music_favorites.json` (never packed into a shared archive), and rows are identified by "title + artist + duration", so storing the same song twice merges into one entry. Each row also owns a cache slot: a song added from the same search round has the real result living in that slot, so a whole-list download fetches it as-is; when the slot is empty (the service restarted, or the cache cap evicted it) the address is re-found by title at download time, and if that fails the row is marked stale. Staleness has two distinct causes with two remedies: "not matched by title in the match sources — switch source, or add that platform's login first before downloading this list", and "the whole round timed out and this track was not reached (this is not 'not found') — just download it again".

The **filename template** accepts `{name}`, `{artist}`, `{album}`, `{source}`, `{id}`, `{ext}` plus the archival fields `{track}`, `{disc}`, `{year}`, `{date}`, e.g. `{artist}/{album}/{year}/{track} - {name}` — the directory layout Emby / Jellyfin-style libraries read. Track numbers are zero-padded to `01`, otherwise a library sorts them 1, 10, 11, 2; `{track}` prefers the platform's own track number (key names differ per platform: NetEase hides the release date inside the album's millisecond timestamp, QQ puts the track number on the entry itself), falling back to the row's position in the playlist. Fields with no value stay empty: empty directory levels are not created, a dangling leading/trailing "- " is trimmed, and a mistyped placeholder (`{track_no}`) never appears literally as braces in a filename. Dates accept `2005-01-01`, `2005.1.1`, `2005年1月1日`, `20050101` and second / millisecond timestamps; anything unrecognized stays empty rather than producing a weird folder name.

</details>

## Telegram

Public channels can be listed anonymously; private ones go through your own account session (api_id / api_hash + phone verification code + 2FA) to batch-download media your account can already access. Channels where the owner enabled “restrict saving content” are treated as an explicit do-not-save signal and are not worked around.

<details>
<summary>Details: the anonymous listing endpoint, MTProto sessions and `tgmt://` routing, how restricted channels are flagged and confirmed one by one, the two branches used for subscription tracking</summary>

- **Anonymous history listing**: `t.me/s/` pages are listed without downloading (`/api/telegram/list`), with a date window and quick ranges.
- **MTProto user session**: enter api_id / api_hash plus a phone login code and 2FA to sign in as **your own** account, then batch-download media your account can legitimately access in private channels (`tgmt://` tasks are routed to this engine). This is the only login method; there is no QR sign-in.
- A channel whose owner enabled "restrict saving content" is treated as an explicit no-save signal; the program does not work around that protection. When the API refuses, the reason is shown verbatim, restricted channels are highlighted in red and confirmed one by one.
- **Subscription tracking**: public channels go through the anonymous path, private ones through your session; a local incremental cursor downloads only new entries, and a date window can backfill history.

</details>

## Subscriptions

RSS, web-page changes, Telegram channels and music playlists are managed on one page; each scan enqueues only entries that are new. Rules can be set per subscription, and blank means follow the global setting.

<details>
<summary>Details: rule fields and when they apply, how scans are logged, why the playlist cursor is keyed on title+artist+duration, and why new entries are not marked read while a batch is still running</summary>

RSS / web-page / Telegram channel / music playlist sources are all managed on the "subscriptions" page (there is no separate screen any more). Top-left is the "add subscription" card (paste a link, detect the source type, choose how Telegram is read); top-right is the "tracking & scan" card with "scan all now", the "auto-download new items" switch and a `共 N 个 · 已启用 N` counter; the full-width card below is the list itself. Each subscription can carry its own rules: content type (long video / short video / live / audio-podcast), duration range, must-contain and exclude words, date window, quality and naming template, audio-only, and a maximum number of items per run. Blank means follow the global setting. Rules apply only to entries that appear after they are set; the operation log states for every scan how many were downloaded, how many were blocked and why. `sub_first_download_n` controls whether a first scan also fetches the most recent N items (0 = record IDs only).

Music platform playlist links (NetEase / QQ / Kugou / Migu / Kuwo / Spotify / Apple and similar) are recognized as "music playlist" sources: each scan re-fetches the whole list and downloads only newly appearing tracks. Cursors for these sources key on "title + artist + duration", so the same song listed by another platform is not downloaded twice. Some platforms in "list titles only" fast mode give only a title per row (no artist, no duration); in that case a hash of that row's link is appended to the key so that two different songs sharing a title (an original and a remix) are not merged into one entry. Rows that carry only a title have no audio address, so the program re-resolves them by title against the match sources instead of dumping them into the general download queue. Each round looks at 300 items and the cursor stores 300 (songs must not be permanently missed because the window was too narrow). Entries of this kind always count as "audio/podcast", so ticking only "long video" in the content-type rule blocks the entire playlist every round. Batch music has a single channel in the program: if the previous music batch is still running, this round's new songs are **not marked as read** (marking them would leave nobody to fetch them) and the log says "will be picked up next scan". Title matching may also find nothing at all (no such song in the match sources, or a row that only has a title to go on); the log lists every unfound track in full, but those rows are still marked as read and will not be retried next round — to retry, either make the playlist spell that row differently or change the match sources and press "scan now". These sources have no reliable per-track publish time, so "backfill by date" speaks for the whole playlist when no date window is given, instead of pretending a window applied.

</details>

## Subtitles & AI processing

Site subtitles can be embedded per language or saved as a sidecar `.vtt`; local transcription, glossary checks, bilingual export and the four-stage AI pipeline all live on this path.

<details>
<summary>Details: language-code matching, diarization and timestamp seeking, the SRT / VTT / ASS trio, stage artefacts on disk with single-stage re-runs, the hardsub entry point and output naming</summary>

- Site-provided subtitles are embedded per language you tick (exact language-code matching), and can additionally be saved as sidecar `.vtt` files.
- Local transcription: faster-whisper (with speaker diarization, voiceprint-clustering variant); clicking a timestamp in the transcript seeks to it.
- Glossary / custom dictionary verification of translated terms, smart subtitle line wrapping, bilingual export as **SRT / VTT / ASS**.
- **AI pipeline**: subtitles → polish → summarize → translate, four stages, each artifact persisted and individually re-runnable (`/api/ai/pipeline`).
- **Hardsub burning**: file page, per-video "more → burn subtitles" — pick subtitles and styling and you get `name.hardsub.mp4`; the source file is untouched.

</details>

## Voice tools

Transcription, dubbing and vocal separation are on the voice page; audio analysis and fingerprint lookup are under “more” on the files page. Models and dependencies are not bundled and install from Settings.

<details>
<summary>Details: the five analysis metrics and the 180-second sampling rule, why everything is downmixed to PCM first, the pre-flight checks before a thread starts, the bundled fpcalc fallback and the client-key trap</summary>

faster-whisper transcription, Edge-TTS synthesis, Demucs vocal/instrumental separation and voiceprint speaker diarization all live on the "voice" page; models and dependencies are installable from Settings (the portable package omits them by default — see [What is in the portable package](#what-is-in-the-portable-package) and [Components & dependencies](#components--dependencies-updated-from-inside-the-app)).

**Audio analysis** is on the file page under "more → audio analysis": librosa reports BPM, key (Krumhansl style-correlation matching), loudness in dBFS, spectral centroid and total duration. The result is written to the operation log and to a sidecar `name.analysis.json`; only the first 180 seconds are used by default so long videos do not eat memory. Audio is always extracted to 22050 Hz mono PCM via ffmpeg first, so `.mkv` / `.mp4` and `.mp3` are treated identically. Before spawning the thread, the file header is probed with ffmpeg: files that yield no media info (an image or a script picked by mistake) or have no audio track at all fail immediately with the reason in the dialog, instead of answering "analyzing" and burying the failure in the log. The same applies when librosa is not installed — instant error, pointing at "Components & dependencies".

</details>

## Browser extension

The bundled extension watches m3u8 / mp4 / ts / m4s on the page and pushes selections into the local queue; if you would rather not install it, you can only receive cat-catch pushes.

<details>
<summary>Details: the MV2 / MV3 manifests and install steps, intercepting browser downloads, the dedicated-engine fallback chain, the cat-catch request body and how AES keys are held, regex rule import, why the URL must stay 127.0.0.1</summary>

`extension/` contains two manifests: `manifest.json` (MV2, Firefox) and `manifest.chrome.json` (MV3, Chrome / Edge).

- Chrome: `chrome://extensions` → developer mode → load unpacked. Firefox: `about:debugging` → load temporary add-on → pick manifest.json.
- Capability: watch page requests for m3u8 / mp4 / ts / m4s → tick items in the popup → send them to the local downloader in one click; right-click "send to MediaDownloader"; optionally intercept browser downloads and route them into the local queue instead.
- Sniffed HLS goes to the dedicated engine `N_m3u8DL-RE` by default (falling back to ffmpeg streaming, then to yt-dlp).
- The extension ZIP can be downloaded from the settings page (`/api/extension/zip`).

### Receiving cat-catch pushes

The third-party sniffing extension [cat-catch](https://github.com/xifangczy/cat-catch) (GPL-3.0) has no server-side interface: you can only make its "settings → send data" POST sniffed resources to an address you fill in. This tool provides that address: `POST /api/catcatch/push`. In the UI it is the "sniffing → receive cat-catch pushes" card, where the "send data URL" and "request body template" fields are copied into cat-catch (choose POST as the method). The card also shows cumulative receptions, items blocked by rules, and pending decryption keys.

- Integration follows only the request-body shapes stated in its public documentation; **none of its code is used**. The docs themselves say the feature is still experimental and JSON shapes differ between versions, so `data` is accepted as an object, an array, stringified JSON or a bare link; anything unrecognized is named in the operation log.
- `referer`, `cookie` and `userAgent` in a push are attached to that task as-is (HLS goes to `N_m3u8DL-RE`, split Bilibili audio+video goes to the merge path, everything else to the general queue). AES keys arriving via the `addKey` action are stored per tab for 1 hour, and m3u8 pushed from the same page automatically picks them up (`--key` / `-decryption_key`). Neither key contents nor cookie contents are ever logged — only byte counts.
- "import cat-catch config" reads the `cat-catch-<version>-<date>.txt` file that cat-catch itself exports (its full configuration JSON) and takes only the regex rules: ordinary rules annotate addresses with an extension, while the `blackList` entry works the opposite way — a matching address is not enqueued and the log names which rule blocked it. Rules are stored in `catcatch_rules.json`, can be disabled or deleted individually, and are on the packaging exclusion list.
- A push contains the site's login cookies, so the "send data URL" should only ever be `http://127.0.0.1:8765/...`; do not point it at an external address. The card states this too.

</details>

## Components & dependencies: updated from inside the app

Every row shows a green or red dot with an install / update button: tools come from GitHub, Python packages through the bundled pip and a mirror, with automatic fallback. “Update all” runs the whole batch in one go. On startup the app also checks upstream versions automatically and, when something is actually newer, shows the reminder once and marks “Settings” with an orange dot (this auto-check can be turned off on the card).

<details>
<summary>Details: what breaks without zhconv / librosa / cryptg, where the current / bundled / latest versions come from, the upstream-version auto-check at startup, how a batch update is ordered and how failures are handled, why numba caps numpy, the scope of the one-click PATH button</summary>

Settings → "Components & dependencies": every item shows a green dot (ready) or red dot (not installed) with an update or install button.

- Tools (FFmpeg, yt-dlp, N_m3u8DL-RE) are fetched from GitHub through the mirror prefix in Settings, switching sources automatically on failure.
- Python dependencies (musicdl, zhconv, mutagen, edge-tts, deep-translator, numpy, librosa, telethon, python-socks, cryptg, faster-whisper) install through the pip bundled in the package and the PyPI mirror in Settings, falling back to the official index and other regional mirrors on failure. `zhconv` does one thing: it normalizes song titles and artists to Simplified Chinese before cross-platform title matching (the matching criterion is "exactly equal after normalization", so a Traditional-Chinese playlist matches nothing in a Simplified catalog and shows up as "not found"). Without it the app still works; you just get the old "Traditional does not match" behaviour. `librosa` is what "audio analysis" needs (it pulls numba / llvmlite). `cryptg` is optional, but without it telethon falls back to pure-Python cryptography and Telegram operations become noticeably slow — those two startup log lines `Failed to load SSL library` / `cryptg module not installed` are exactly that (portable packages from v1.2.8 onwards bundle cryptg, so no install needed).
- **Three versions per row**: `current` = what the running process uses; `bundled` = what shipped inside the portable package (shown only after you updated something, so it differs from current); `latest` = the upstream version, fetched only when you press "check upstream versions". The bundled versions come from `components_bundled.json`, written into the package at build time (it records the runtime and each `tools/` binary). Running from source has no such manifest, so "bundled" simply does not appear. "Latest" is asked of pip itself (`pip index versions`), so the PyPI mirror in Settings applies, and results are cached for 10 minutes; FFmpeg and N_m3u8DL-RE are not on PyPI, so those two rows have no `latest`. When it cannot be determined, the row states why rather than leaving a blank.
- **Auto-check on startup**: three seconds after launch a background thread asks upstream once (it blocks neither startup nor the UI) and caches the result for 10 minutes, so refreshing the same table does not keep asking pip. Only when something really is newer does a reminder pop up — once per browser session; after that the orange dot is left alone and nothing nags you again — and “Settings” in the sidebar gets an orange dot too. Clicking “Go to components & dependencies” in the popup switches to the settings page and scrolls to that card. Two groups are excluded from the judgement: items that are not installed at all (faster-whisper is deliberately not shipped, so counting it would nag about the same thing at every boot), and FFmpeg and N_m3u8DL-RE, which are not on PyPI. The card also has a “Check now” button (it discards the 10-minute cache and really asks upstream) and a switch; with the switch off there is no automatic check and no popup. The change needs “Save settings” and takes effect on the next start. API: `GET` / `POST /api/components/update-check`; `GET /api/components` also returns `auto_check` plus the current check result.
- **Update all**: the first button in the card's button row queues the whole batch at once instead of clicking row by row. It handles "not installed" plus "checked upstream and genuinely newer" — with no version check performed it only fills in what is missing, never guessing at latest versions; a line under the button states in advance which items this run covers. Clicking opens an item-by-item list (`install X (current: not installed)` / `update Y: old → new`); after confirmation it runs **strictly sequentially**, never concurrently (two pip installs would trample each other). Progress and "last batch update: N / M succeeded" show under the button; if faster-whisper is included the models come with it, which can take a while and occupy hundreds of MB. A failure affects only that item and the batch continues, with the source used and the outcome logged per item. Pressing the button while a batch is running says "a batch is already running" and does not queue. If a selected item is not recognized on this machine, the whole batch is rejected on the spot and names the item.
- **How far numpy can go is decided by numba**: librosa depends on numba, and numba caps numpy (`numba 0.65.0` requires `numpy < 2.5`). In testing, upgrading numpy alone from 2.4.6 to 2.5.3 broke every call to "voice → audio analysis" and voiceprint diarization with `Numba needs NumPy 2.4 or less. Got NumPy 2.5.`. `numba 0.67.0` raises the cap to `numpy < 2.6`, so the two packages must be upgraded together. But numba has no row in the components table, so it has to be upgraded with pip directly; if that is a hassle, leave numpy out of this batch. This only bites machines that already had an older numba and then upgraded numpy alone: a fresh librosa install lets pip pair them correctly, and the portable package ships neither, so installing gets current versions.
- The whole process is visible in the operation log (which source was used, whether it worked). The running process may still hold the old version in memory; restart to apply.
- The "command-line PATH" block can add `tools/` and `chromaprint/` to your user PATH with one click (user variable only, removable at any time; on macOS / Linux it just prints the export command).

</details>

## Resolver plugins & aria2

Drop a `.py` into `plugins/` implementing `match(url)` and `resolve(url, ctx)` and it gets loaded; aria2 is optional and used for segmented CDN direct links.

<details>
<summary>Details: the plugin interface and reload endpoints, the two example plugins, how aria2 is enabled and the Docker profile</summary>

- **Resolver plugins**: drop a `.py` into `plugins/` implementing `match(url)` and `resolve(url, ctx)` and it is loaded (`/api/plugins` lists them, `/api/plugins/test` trial-resolves, `/api/plugins/reload` hot-reloads). Page links are resolved to real media URLs before enqueueing; the repository includes `example_passthrough.py` and `site_b23_short.py` as references.
- **aria2 (optional)**: when enabled in Settings, CDN direct links are sharded through aria2 (`aria2_client.py`, status at `/api/aria2/status`). Docker Compose has an `aria2` profile to start the RPC service.

</details>

## Notifications

Outbound push through Telegram Bot, WeCom and ServerChan, each with separate finished / failed / subscription switches. Keys are stored only in the local `config.json`, never packaged, never logged.

<details>
<summary>Details: the fields and switch keys each channel needs</summary>

- **Telegram Bot**: Bot Token and Chat ID, with three independent switches — `telegram_notify_done` / `_fail` / `_sub`.
- **WeCom (企业微信)**: CorpID / Secret / AgentID / touser plus a test send, with the same three tiers `wecom_notify_*`.
- **ServerChan**: a SendKey pushes on download completion; no separate switches for the other tiers.
- All secrets live only in the local `config.json`; they are never packed and never logged.

</details>

## Themes

5 accent themes (annual blue by default / vivid orange / pop pink / meadow green / terracotta) × light and dark, switched from the top bar's right side (colour dots plus a light/dark toggle); the choice persists in `ui_theme` and `dark_mode`. The reference-project and dependency credits live under "Settings → Credits / reference projects" and must be kept in sync when a dependency or reference is added. UI copy is currently Chinese-only.

## Offline self-tests

`tests/` contains standalone self-test scripts (e.g. `python tests/musicarchive_test.py`). Each prints PASS/FAIL per assertion and exits 0 only when everything is green. They write only into temporary directories, never touch `config.json`, and never write into the download directory. Install `requirements.txt` first; the diarization suites additionally use the ffmpeg binary in `tools/`. `tests/fixtures/` holds four HTML snapshots of **public** pages — three `t.me/s/` channel pages and one fragment of a Douyin anti-bot challenge page — with no login content and no cookies, so the Telegram crawler and Douyin risk-classification tests can assert offline.

## Repository layout

```
server.py            FastAPI backend (routes, download scheduling, subtitles and AI)
music_search.py      aggregate music search and playlist matching   telegram_channel.py  t.me/s anonymous crawler
telegram_mt.py       MTProto session and private-channel batches    voice_tools.py       TTS / Demucs
ai_pipeline.py       AI pipeline stage artifacts                    diarize_tools.py     voiceprint diarization
audio_analyze.py     audio analysis and fingerprinting              pkg_update.py        component and dependency self-update
risk_control.py      classification of risk-control and anti-bot replies   aria2_client.py  optional aria2 RPC client
pack_release.py      portable package build script (with self-checks)
static/              front end (single-file Vue 3 app)              extension/           browser sniffing extension
plugins/             URL resolver plugins                           tools/               ffmpeg / ffprobe / yt-dlp / N_m3u8DL-RE
tests/               offline self-tests and fixtures                 cookies/             cookies.txt
Downloads/           default download directory
musicdl_outputs/     musicdl intermediate cache (search pickles, unarchived temp files)
_preview/            the temporary audio fetched by "preview" (last 20 only)
```

Every intermediate file the tool creates stays in the program folder, never in your download directory (the music cache and preview temporaries used to be scattered as `Downloads/_musicdl_cache` and `Downloads/_preview`), and their locations are anchored to the program's own directory rather than resolved relative to the current working directory. Your finished media still lands in the download directory according to the filename template alone. The repository contains only source (`server.py` and friends), documentation, `static/`, `extension/`, `plugins/`, `tests/`, plus `requirements.txt` / `Dockerfile` / `docker-compose.yml`; `tools/`, `Downloads/`, `config.json` and every other local file are deliberately not committed.

## Common API endpoints

The backend is a single FastAPI file; the full route list is browsable and testable at `/docs`.

<details>
<summary>Details: the general endpoints and the music-path endpoints</summary>

`GET /api/status` `POST /api/analyze` `POST /api/download` `GET /api/tasks` `GET /api/net/info` `GET /api/components` `GET /api/plugins` `GET /api/queues` `GET /api/events` (SSE progress) `POST /api/ui_event` (front-end action telemetry, local only).

The music side additionally has: `GET /api/music/status` (source list, default sources, stored strategies, the four settings echoes for naming template / tag embedding / filtering unavailable / including the local library, plus the current quality requirement and the four tier tables), `POST /api/music/search`, `POST /api/music/playlist`, `POST /api/music/probe`, `POST /api/music/download` (de-duplication and the "skip already downloaded" check run first; both accept `quality_spec`; `GET /api/music/download_status` reports batch progress and unmatched lists), `POST /api/music/check_quality` (reads each finished file's own tags against this batch's requirement; only paths inside the download directory are accepted), `POST /api/music/switch_source`, `GET/POST /api/music/favorites` with `/favorites/remove`, `/favorites/download` and `/favorites/mark`, `POST /api/music/local_scan` and `GET /api/music/local_cover`, `GET/POST /api/music/cookies` (the three per-platform logins), and `GET /api/music/netease/qr/generate` / `POST /api/music/netease/qr/poll` (NetEase's own QR login). The full list is in `server.py` under the `@app.` decorators or at `/docs`.

</details>

## Contributing

Single-file backend `server.py` plus single-file front end `static/index.html`; editing `.py` requires a restart. When opening a PR, state the reproduction steps and which self-tests you ran.

<details>
<summary>Details: environment setup, adding a site resolver, self-tests and fixtures, the three places a new dependency must be added, UI and copy rules, re-packaging after document edits, how the default-deny allowlist unignores files</summary>

1. Bring it up: `pip install -r requirements.txt`, then `python server.py`, and open `http://127.0.0.1:8765`. Put ffmpeg / ffprobe / yt-dlp / N_m3u8DL-RE into `tools/`, or install them from Settings.
2. Read this before editing: the backend is the single file `server.py`, the front end the single file `static/index.html`; `.py` changes need a process restart.
3. Adding a site resolver: drop a `.py` into `plugins/` implementing `match(url)` and `resolve(url, ctx)`; trial it with `/api/plugins/test`.
4. Run the self-tests: `python tests/<name>_test.py` prints PASS/FAIL per assertion and exits 0 when green. `tests/fixtures/` contains four HTML snapshots of public pages (no login content, no cookies) so the offline assertions stay offline.
5. A new dependency must be registered in three places: `requirements.txt`, `PKGS` in `pack_release.py`, and the "Components & dependencies" table (including the `CREDITS` array in the front end; reference projects likewise). A new top-level `.py` module **must** be added to `APP_PY` in `pack_release.py` — omitting it means the packaged app cannot import it.
6. UI conventions: new controls default to `size="small"`, only the primary CTA uses `large`; the accent colour stays blue, with green and yellow reserved for status; one section per screen equals one card; lists beyond one screen paginate at 50 with jump-to-page; every UI action must write to the operation log. Copy should be formal but plain, refer to actual control names, and error messages must keep every technical fact.
7. Rebuilding docs and package: after touching `server.py`, `static/index.html`, README or CHANGELOG the archive does not follow automatically — re-run `python pack_release.py --skip-runtime`; the md5 of the documents inside the zip must equal the ones on disk.
8. Do not commit local state: `.gitignore` is default-deny with an explicit allowlist, so new documentation or directories need their own unignore line. `config.json`, cookies, history, downloads and session files never go in.
9. In pull requests, describe the reproduction steps and which self-tests you ran. Changes that would bypass a login, a paywall, DRM, a human-verification challenge or a platform's anti-bot signature are not accepted — see [Out of scope by design](#out-of-scope-by-design).

</details>

## Privacy

- Everything stays local: `config.json`, `history.json`, cookies and downloaded content all live inside the working directory; the program uploads nothing.
- Logs record actions and errors only — never tokens, secrets, api_hash, passwords, cookie values, SendKey or HLS key contents. Saving settings logs only the changed key names and counts.
- The portable package forcibly excludes `config.json`, `cookies/`, `Downloads/`, `history.json`, `subscriptions.json`, `rss_feeds.json`, `music_favorites.json` (your self-built music list), `local_index/` (music index snapshots, which contain real local paths), `tg_session/`, `browser_sniff_profile/`, and every local cache and log; a leak check before packing aborts the build if any of them slipped in.

## Known limitations

What cannot be done is stated in the UI as well; the app never pretends to succeed:

| Limitation | Symptom | Reason |
| --- | --- | --- |
| Range trimming is segmented-stream only | a single mp4 with `download_section` set ignores it, and the task log says so | it rides on yt-dlp's `download_ranges`, which works on HLS segment boundaries |
| YouTube wants cookies | resolution fails or offers only 360p without cookies | the site's "sign in to confirm you're not a bot" wall |
| Douyin search is empty without cookies | classified as login-required / anti-bot challenge / rate-limited / API error / genuinely empty, with the basis shown | the search API returns 200 with the `status_code:2483` login wall, or serves a JS challenge page; this tool does not execute site JS or forge signatures |
| Spotify / Apple have no official audio path | "list titles only + match by title elsewhere", or ~10 s third-party conversions that often fail | DRM; which is why neither is a default match source |
| Quality requirements cannot pin a platform's tier | only ordering, refusal below spec, and post-hoc verification are possible | tiers are hard-coded constants in musicdl's source classes; no client parameter selects quality |
| The lossless reference is metadata only | "Qobuz·ref" rows cannot be selected or downloaded | the audio sits behind a third-party human check; no tokens, no bypass |
| Batch music has a single channel | new songs are not marked read while a previous batch runs; the log says "next scan will catch up" | marking them read would leave them unfetched |
| Title matches are not retried automatically | unmatched rows are marked read and not retried next round | change how the playlist spells that row, or change match sources and press "scan now" |
| Voice stack is not preinstalled | faster-whisper / Demucs / librosa start as red dots in the portable package | models and dependencies are several GB; install from "Components & dependencies" |
| UI is Chinese-only | no language switch | documentation exists in two languages; the interface is not internationalized |

## FAQ

**Pressing "start download" errors out and no task was created.** That is the dependency preflight (missing yt-dlp / FFmpeg / faster-whisper / N_m3u8DL-RE / telethon, or a download directory you cannot write to). The error names exactly which row of "Settings → Components & dependencies" to install. Cases that merely run slower or lower quality are not blocked.

**YouTube fails or caps at 360p.** The site demands a logged-in session; add cookies or change egress. See [Cookies & site logins](#cookies--site-logins).

**Spotify / Apple tracks in a playlist keep coming back "not found".** Check the match sources: the default five resolve addresses fast and download immediately; Spotify and Apple go through a third-party conversion service, which is slow and flaky. When the scoring gate rejects a candidate the log names the dimension (title / artist / duration), and "not searched this round" is reported separately from "not found by title" — the remedies differ.

**I selected a range but got the whole file.** Single-file streams cannot be trimmed; the task log records that the parameter was ignored. Only HLS / m3u8 segmented streams support ranges.

**"Skip already downloaded" is on and it still re-downloaded that song.** The per-row "download" button is an explicit single action and is not bound by that checkbox. Also, four cases never block: the template contains `{id}` or `{source}`, no title is available, the target directory does not exist yet, or the directory holds only sidecar files (`.lrc`, covers).

**Audio analysis fails with `Numba needs NumPy 2.4 or less. Got NumPy 2.5.`** numba caps numpy, and numba has no row in the components table — either upgrade numba alongside numpy with pip, or leave numpy out of this batch.

**Two startup log lines about SSL library / cryptg not installed.** telethon has fallen back to pure-Python crypto and Telegram operations will be slow. The portable package from v1.2.8 onwards bundles cryptg; from source, just install it.

**Fingerprint lookup reports `invalid API key`.** That field wants the acoustid.org **application** client key, not the user API key shown after you log in.

**I installed dependencies but nothing changed.** The running process still holds the old version in memory — restart (`python server.py`, or relaunch `启动.bat`). Front-end-only changes in `static/index.html` just need a page reload.

**Where is the log file?** The "log" page states its location at the top — it is in the program folder — and opens it with one click. Files rotate daily and are deleted after 7 days.

## Out of scope by design

These are deliberate omissions, not a backlog:

- No bypassing login walls, paywalls, DRM or any human-verification challenge (Turnstile / CAPTCHA); no obtaining or forging verification tokens.
- No executing a site's challenge JavaScript and no forging its anti-bot signature.
- Telegram channels with "restrict saving content" are an explicit no-save signal and are not worked around; login is api_id / api_hash plus phone code and 2FA only — no QR sign-in.
- The Qobuz / Tidal lossless reference reads metadata only; not a byte of audio is fetched.
- HLS keys pushed by cat-catch are only the ones you already captured yourself; the program never goes looking for or breaks one.

## Acknowledgements

This tool wires together existing public interfaces and open-source downloading components. Primary dependencies: [yt-dlp](https://github.com/yt-dlp/yt-dlp), [N_m3u8DL-RE](https://github.com/nilaoda/N_m3u8DL-RE), [FFmpeg](https://ffmpeg.org), [aria2](https://github.com/aria2/aria2), [musicdl](https://github.com/CharlesPikachu/musicdl), [mutagen](https://github.com/quodlibet/mutagen), [edge-tts](https://github.com/rany2/edge-tts), [deep-translator](https://github.com/nidhaloff/deep-translator), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Demucs](https://github.com/facebookresearch/demucs), [Telethon](https://github.com/LonamiWebs/Telethon), [Chromaprint / fpcalc](https://github.com/acoustid/chromaprint), [AcoustID](https://acoustid.org), [MusicBrainz](https://musicbrainz.org), [FastAPI](https://github.com/fastapi/fastapi), [Vue](https://vuejs.org), [Element Plus](https://element-plus.org).

Interfaces and features referenced from: [Ghost-Downloader-3](https://github.com/XiaoYouChR/Ghost-Downloader-3), [voice-pro](https://github.com/abus-aikorea/voice-pro), [AI-Video-Transcriber](https://github.com/wendy7756/AI-Video-Transcriber), [cat-catch](https://github.com/xifangczy/cat-catch) (GPL-3.0; this project implements only the receiving end of its "send data" feature and its regex-config import, against the documented format, with no code copied), [spotDL](https://github.com/spotdl/spotDL) (the scoring-gate idea for same-song detection, no code copied), and Emby / Jellyfin (the directory layout convention behind `{track}` / `{disc}` / `{year}` / `{date}`).

The complete list, with what each project is used for, is in "Settings → Credits / reference projects", where every name links to its home page.

## License

Released under GNU GPL-3.0-only; the full text is in [LICENSE](LICENSE). Derivative works, and works that include this source, must be open-sourced under GPL-3.0 as well and must retain the upstream acknowledgements.

## Disclaimer

- This program is only a local graphical front end that strings together existing public interfaces and open-source download components (`yt-dlp`, `N_m3u8DL-RE`, `aria2`, and others). It provides no capability to bypass logins, payments, DRM or site risk controls, and it will not do those things for you.
- You are responsible for the legality of and authorization for every link you download with it. Respect each platform's terms of service and the copyright law of your jurisdiction; use it to back up and study content you are entitled to access, and do not redistribute or commercialize unauthorized works.
- Cookies, Telegram credentials, WeCom / ServerChan keys and AI service keys are written only into the local working directory and are never uploaded with the source. Nothing in the public repository contains them; configure them yourself after cloning or forking.
- The author accepts no liability for account restrictions, failed downloads, lost files or legal consequences arising from the use of this program.

---

Release notes are in [CHANGELOG.md](CHANGELOG.md) (Chinese). The primary, most complete documentation is [README.md](README.md).
