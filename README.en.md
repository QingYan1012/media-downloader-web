<div align="center">

# MediaDownloader Web · 多媒体下载器 Web

**Link parsing & download · torrents & magnets · page sniffing · cross-platform music · subtitles & AI · voice tools · subscription tracking**

A media downloader and processor that runs entirely on your own machine: paste a link and it downloads, and the browser handles queues, magnet and `.torrent` jobs, m3u8 captured from pages, music lookup by song title, subtitles with sentence-by-sentence proofreading, transcription and subscription tracking.
Settings, cookies, history and downloaded files all stay in the folder the program runs from — nothing is uploaded anywhere.

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue)](LICENSE)
[![Version](https://img.shields.io/badge/Version-v1.4.0-informational)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.12-green)](requirements.txt)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Docker-blueviolet)](#get-started-in-30-seconds)
[![Storage](https://img.shields.io/badge/Data-100%25%20local-lightgrey)](#privacy)

<p>
  <img src="docs/screenshots/home-light.png" alt="Download & parse page: paste media links and resolve them into selectable formats, with output preferences and add-on switches on the left, presets and fine control on the right" width="100%" />
</p>

[中文（主文档）](README.md) · English

</div>

> **Note on UI language.** The interface is bilingual: an `AUTO / 中 / EN` group in the header switches the whole app between Chinese and English, following the browser language by default. The labels listed below still carry English glosses, because this file documents behaviour rather than translating the screen row by row.

This tool does **not** bypass login walls, paywalls, DRM or human-verification challenges. It never executes a site's JS challenge and never forges its anti-bot signature. Full boundaries: [Out of scope by design](docs/detailed-features.en.md#out-of-scope-by-design).

> This README covers **how to start** and **what it does**. How each page works, the judgement rules behind every capability, the known limitations and the FAQ live in the **[detailed feature guide](docs/detailed-features.en.md)**; per-version changes are in [CHANGELOG.md](CHANGELOG.md) (Chinese).

## Get started in 30 seconds

1. Download `MediaDownloader-1.4.0-portable.zip` from [Releases](https://github.com/QingYan1012/media-downloader-web/releases/latest).
2. Unpack it to a path with no non-ASCII characters and no spaces, and not under `C:\Program Files`.
3. Double-click `启动.bat` (the launcher); `http://127.0.0.1:8765` opens by itself after about 3 seconds.

Not the portable route: `pip install -r requirements.txt && python server.py` (the same route on Linux / macOS), or `docker compose up -d --build` for a NAS / home server — that image ships aria2c too.
**aria2c is not in the portable package** — the engine of the "磁力 / 种子" (torrents & magnets) page — but you do not have to hunt it down on GitHub: clicking "install" on the aria2 row under **Settings → Components & dependencies** fetches it into `tools/`.

Port override, relocating the data directory and headless runs each have their own environment variable, and the full list of bundled dependencies is in [detailed feature guide → Getting started, in full](docs/detailed-features.en.md#getting-started-in-full).

## What is in the portable package

Bundled: the Python runtime **and pip**, FFmpeg / ffprobe, yt-dlp, N_m3u8DL-RE, fpcalc, the music stack (musicdl / mutagen / edge-tts / deep-translator / zhconv) and the Telegram stack (telethon / python-socks / cryptg). A clean default configuration is generated on first start.

Not bundled: the gigabyte-sized voice stack (faster-whisper plus models, Demucs, librosa), aria2c and psutil — all three are red-dot rows in **Settings → Components & dependencies**, installable on demand with the bundled pip; restart the launcher afterwards, no re-download needed.

The archive **contains no local data by construction**: no `config.json`, no cookies, no `Downloads/`, no history, no subscription records. The packing script runs a leak scan before building and aborts if anything private slipped in.

## The feature summary

The sidebar has 17 pages in 5 groups (download / acquire & process / library / automation / system). The capabilities fall into eight blocks:

| Block | In one line | And one more |
| --- | --- | --- |
| [Parsing & download](docs/detailed-features.en.md#download--queue) | Paste one link or a batch, resolve them into selectable formats with a size estimate per row; per-domain concurrency, automatic slowdown on 429, a global cap, and speed limits by time window | The queue supports multi-select, pause / resume, pin to top, move to front and "download later"; one rule table (match the name or the link) decides which subdirectory of the download folder each task lands in — a directory you picked yourself still wins; the clipboard watcher is off by default and, when on, only asks about a link you just copied — it never enqueues anything on its own |
| [Finished-file checks](docs/detailed-features.en.md#download--queue) | After a download, ffprobe reads the real height of the file and compares it with the tier you picked; a mismatch is reported with the name of the party at fault | Default mux is mkv; when a site only offers one progressive mp4 the file is rewrapped losslessly, never re-encoded; integrity is verified so a "success" is never fake |
| [Streaming & torrents](docs/detailed-features.en.md#torrents--magnets) | HLS / DASH segments go through N_m3u8DL-RE (a range of the stream can be selected); magnets and `.torrent` files have their own page: pick files inside, watch seeding, add trackers, auto-file by torrent name or link, separate upload / download limits | That page's engine is the local aria2 — missing? install it from the Components table; the same rule table also files ordinary downloads, and a rule can be test-run in the UI before you save it |
| [Page sniffing](docs/detailed-features.en.md#browser-extension) | The bundled browser extension watches m3u8 / mp4 / ts / m4s on the page and pushes what you tick into the local queue | It also accepts POST pushes from the third-party cat-catch extension and can import its regex rule files |
| [Music](docs/detailed-features.en.md#music) | Search up to 24 platforms in parallel by song title, with lyrics / cover / tag writing, whole-playlist downloads, single-track link parsing (Spotify / NetEase), source switching, your own favourites lists, a local library index and a persistent play bar | "Is this the same song" is a scoring gate (title / artist / duration scored separately) and rejected candidates come with the reason; matching queries every ticked platform and keeps the best hit — tick order only breaks an exact tie; quality requirements can drive sorting, or refuse downloads below spec outright |
| [Subtitles / AI / voice](docs/detailed-features.en.md#subtitles--ai-processing) | Pick site subtitles per language, validate names against a glossary, export bilingual SRT / VTT / ASS, burn hard subtitles; a four-stage AI pipeline: subtitles → polish → summary → translation | Sentence-by-sentence QC after machine translation, plus a three-metric timeline check (coverage / largest gap / reading speed) and a proofreading desk; local transcription with speaker diarisation, Edge-TTS dubbing, vocal / accompaniment separation (RoFormer and Demucs, in their own environment, CPU or GPU), audio analysis, fingerprint lookup |
| [Telegram & subscriptions](docs/detailed-features.en.md#subscriptions) | List public channel history anonymously through `t.me/s/`, or batch-download with your own account session; four subscription source types (RSS / page changes / Telegram channel / music playlist) scan and queue on a schedule | Each subscription carries its own rules; a scan first prints the plan for that round, and entries deleted upstream are archived instead of vanishing |
| [Notifications & operations](docs/detailed-features.en.md#notifications) | Three notification channels (Telegram bot, WeCom, ServerChan) with independent switches per event type; undelivered notices are persisted and retried with growing delays, surviving a restart | Components & dependencies update from inside the app, mirror speed-test in one click, the run log records UI write actions and failures only (browsing adds no lines), one-click desensitised diagnostics export, settings auto-save per changed key with per-item / one-click restore, opt-in login protection, 5 themes × light / dark, a bilingual Chinese / English interface (`AUTO / 中 / EN` in the header), and a first screen that asks nothing of any external CDN (the six framework files ship in the package) |

Live recordings can be set to "stop and save after N minutes": the job ends on its own and runs the complete save path (reaping the streaming subprocess, finalising `.part`, detaching danmaku and chat files). Every HTTP endpoint is also exposed through a local-only [MCP bridge](docs/detailed-features.en.md#mcp-bridge) for agents that speak MCP.

## Privacy

- Everything stays local: configuration, history, cookies and downloads all live in the program folder; nothing is uploaded.
- Logs and the diagnostics export record actions and errors only — never passwords, tokens, keys or cookie contents. Desensitisation happens in the backend, so cookies, Telegram sessions, downloaded files and seeding state are never included.
- The only route that can send cookies off the machine is the optional **CookieCloud sync**: **off by default**, and when on it talks only to the server address you typed; its key is stored locally, never echoed in the UI.
- With "access protection" enabled: passwords are stored only as a salted hash, sessions are locally signed cookies, and the failed-attempt counter and lockout list stay in a local file that is never packaged.

The full account, including the packaging exclusion list, is in [detailed feature guide → Privacy](docs/detailed-features.en.md#privacy).

## Further reading

- **[Detailed feature guide](docs/detailed-features.en.md)** — the 17 pages, the rules behind every capability, repository layout, common API endpoints, contributing, [known limitations](docs/detailed-features.en.md#known-limitations) and the [FAQ](docs/detailed-features.en.md#faq).
- [中文主文档 README.md](README.md) · [Release notes (English digest)](CHANGELOG.en.md) · [CHANGELOG.md](CHANGELOG.md) (full record, Chinese)
- `使用说明.txt` inside the portable archive is the shortest version of all: how to launch, what to do when the port is busy, and which row to click when a component is missing.

## License

Released under GNU GPL-3.0-only; the full text is in [LICENSE](LICENSE). Derivative works, and works that include this source, must be open-sourced under GPL-3.0 as well and must retain the upstream acknowledgements.

## Disclaimer

This program is only a local graphical front end that strings together existing public interfaces and open-source download components. It provides no capability to bypass logins, payments, DRM or site risk controls, and it will not do those things for you; you are responsible for the legality of and authorization for every link you download with it. The author accepts no liability for account restrictions, failed downloads, lost files or legal consequences arising from its use.

---

Release notes have an [English digest](CHANGELOG.en.md); the full, authoritative record is [CHANGELOG.md](CHANGELOG.md) (Chinese). The primary, most complete documentation is [README.md](README.md).
