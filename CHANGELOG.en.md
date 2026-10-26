# Release notes — English digest

This file is a **digest, not a mirror**. The authoritative record is [CHANGELOG.md](CHANGELOG.md) (Chinese); it is
written as a development journal, and every claim there is backed by a reading taken at the time — a self-test
suite, a live HTTP response, a byte count. The pages below keep those readings and drop the narration.

Identifiers are quoted verbatim from the Chinese record: function and config-key names, endpoint paths and
`tests/*.py` names. The Chinese entries also carry `server.py` line numbers, frozen at the moment each change was
made; the file has grown since, so this digest names the identifiers and leaves the line numbers to the source.
The version number has one source: `appVersion` in `static/index.html`, which
`pack_release.py` reads from the same place, so the UI, the README title and the portable package name cannot drift.

---

## v1.4.0 · 2026-10-15 — published

Fifteen items accumulated before this was cut, so the version went from `v1.3.2` straight to **v1.4.0** and was
packaged once at the end. Sections written earlier inside the same round say "no package this round" — that was
each round's own state; `appVersion` really did stay on `v1.3.2` until the batch was finished.

### What landed

**Download queue**

- **Scheduled run windows** (`run_window` globally, `queue_windows[<queue name>]` per queue): "may new tasks start
  between these hours". It reuses the speed-window parser rather than adding a second one, so `22:00-06:00` means
  that night into the early morning and hits at both 23:30 and 02:00. A download already in progress is never
  interrupted — cutting off a file mid-write is not what "run the queue at 2am" means. Window-held tasks are
  re-queued ahead of cooldown tasks (`held + skipped + pending`), and a queue page banner names which queues are
  held and when each resumes. `tests/runwindow_test.py`, `tests/sse_test.py`.
- **Checksum verification**: pass an expected MD5/SHA when enqueuing, and the finished file is hashed with the same
  algorithm. A match writes one line to the runtime log; only a mismatch puts a line on the card — as a notice, and
  it never deletes the file. Reuses the existing `verify_note` channel, so no new key and no new column.
  `tests/hashverify_test.py`.
- **Public-first cookie policy** (`cookie_public_first`, off by default): parse each link once as an anonymous
  visitor, and only re-parse with cookies when that attempt hits a login/membership/age/risk wall or comes back with
  a clipped format list. Cookie'd and anonymous parses are *not* the same manifest — with cookies, yt-dlp skips the
  android/ios client chains — so this is not just a cache question. With the switch off, behaviour is identical to
  before, pinned by the default value, self-test group E and live reading L1. `tests/cookiefirst_test.py`.
- **Auto-sort by URL rule**: the destination-subdirectory rule table used to compare only torrent/magnet *names*, so
  "YouTube goes to `视频\YouTube`" could never apply to ordinary downloads, which have no file name at enqueue time.
  Rules now carry a second dimension — match the name or the link. `tests/subrules_test.py`.
- **Clipboard watch** (`clipboard_watch`, off by default): with it on, the app recognises a link you just copied and
  asks one question. It never enqueues anything by itself. `tests/clipboard_test.py`.

**Encoding**

- **Hardware encoders with a fallback chain**: `_encoder_args()` maps the one outward-facing CRF
  number onto each encoder's own flag syntax (`-crf` / `-rc vbr -cq N -b:v 0` / `-global_quality` /
  `-rc cqp -qp_i -qp_p`), with a separate NVENC preset table (veryfast→p1, fast→p2, medium→p4, slow→p5). HEVC inside
  mp4 always gets `-tag:v hvc1`, otherwise QuickTime can't see the track. `_video_encode_chain()`
  tries the vendor encoder first and the CPU last, with x265↔x264 as mutual fallbacks and
  `X265_TIMEOUT_MULT = 3.0` for the cost step. New `GET /api/video/encoders`; probe has a hard 8 s timeout.
  `tests/hwenc_test.py`.

**Reliability and access control**

- **Notification outbox**: undelivered Telegram / WeCom / Server酱 messages are persisted to
  `notify_outbox.json` (atomic temp-file + `os.replace`) and retried on growing intervals `(30, 120, 600, 1800,
  3600)` s — about 1.7 hours of attempts before an entry is dropped. A restart does not lose the queue, and sends
  moved off the download thread onto one idle tick. WeCom's `access_token` is now cleared on `errcode`
  40014/42001/41001 instead of being reused. `tests/outbox_test.py`.
- **Optional web access protection** (off by default): gates only non-local clients, decided by
  `request.client.host` and never by `X-Forwarded-For`. Passwords are stored as
  `pbkdf2_sha256$rounds$salt$derived_key` — PBKDF2-HMAC-SHA256, 240,000 rounds, 16-byte salt — compared with
  `hmac.compare_digest`. Sessions idle out after 12 h (`web_auth_session_hours`, sliding), "remember" lasts 30 days
  (`web_auth_remember_days`, deliberately not sliding); a failed-attempt window in `login_state.json` answers 423
  before the password is ever checked. `GET /api/config` masks `secret_key`, the password hash and the machine
  token. `tests/auth_test.py`.
- **Age-based cleanup** (`cleanup_log_days`, `cleanup_trash_days`, …): off by default; even when on, it only
  collects log archives, edit backups and a recycle directory. Finished downloads are only ever removed after a
  person reads the list and presses delete. `tests/cleanup_test.py`.
- **Settings auto-save that submits only the changed keys.** The old save button POSTed the whole snapshot read when
  the page opened, so any key changed elsewhere in the meantime — the magnet page, another tab, `/api/config`
  itself, the app itself — was silently overwritten with the stale value. Per-item and one-click restore-defaults
  came with it. `tests/settingsave_test.py`.

**Music**

- **Match confidence on screen**: the score that already existed behind the acceptance gate is now a tag in the
  source column (green above the line, yellow below, red when rejected), and hovering shows the total, the
  thresholds, the three sub-scores (title / artist / duration — `null` displays as "did not participate"), the
  rejection reason, and the reminder that the score never claims two recordings are the same take. Thresholds stay
  as they were: `MATCH_NAME_MIN=60`, `MATCH_ARTIST_MIN=70`, `MATCH_ACCEPT=85`. A high score can still be rejected by
  the version gate — `晴天 (Live) / 林俊杰, 周杰伦` scored **98** and stayed red.
  `tests/matchgate_test.py`.
- **Single-track links from Spotify / NetEase Cloud** now take the same path as a full playlist: placeholder
  (`needs_match`) → match → download, one track at a time. The matching rule was written and approved before the
  code; the first version ("the checked order is the priority, stop at the first usable hit") was then **revoked by
  the user** — every checked platform is searched and the best hit wins — and that correction was rewritten into the
  code, the tooltip, two detailed guides and both READMEs. `tests/musicsingle_test.py`, `tests/matchround_test.py`.

**Subtitles**

- **Three-axis timeline QC after machine translation**: coverage, longest gap, and character rate (9/s Chinese,
  14/s foreign language), over an 8% band with a 10 s floor and 90 s cap. `POST /api/subtitle/qc` gained
  `media` / `media_seconds` / `timeline` / `timeline_text`; a missing media file returns `available:false`, which is
  deliberately not the same as "QC is switched off". `tests/timelineqc_test.py`.

**Cookies from your own CookieCloud server**

- `GET {server}/get/{uuid}` and `POST {server}/update`, key derived as `md5(f"{uuid}-{password}").hexdigest()[:16]`,
  both `aes-128-cbc-fixed` and the `legacy` passphrase scheme, cross-checked byte-for-byte against `openssl` in both
  directions. The server rate-limits to 100 requests per 15 minutes, so **there is no polling** — connect, sync now,
  and a timestamp. The key is write-only through `POST /api/cookiecloud/account`, never echoed, and masked in
  config reads. `tests/cookiecloud_test.py`.

**Interface**

- Seven screenshot-driven reports closed in one round (`#34–#40`): counts that should exist at startup no longer
  waited for the page to be opened; one setting that was stored twice; a settings page of twenty flat cards that
  learned to group and collapse; the Bilibili QR login and the music-platform cookies merged into one block; the
  live-recording duration kept in sync between its page and the general settings; the library defaulting to sort by
  modification time; the dependency-update card shortened and translated into Chinese.
- **Navigating no longer writes to the runtime log.** The log page shows the last 200 lines and every click on the
  sidebar used to add `[界面] 切换到「X」`, so walking through 17 pages burned 17 lines and pushed the real write
  operations off the screen. Read-only navigation should not flush genuine records. `tests/navlog_test.py`.
- The music result table spreads its leftover width across title / artist / album (`min-width` instead of hard
  `width` on the last two) instead of letting the title column swallow all of it.

### Bugs this batch caught

Caught by the offline suites:

- `ConfigBody` serialised with `model_dump(exclude_none=True)`, which silently dropped keys the model hadn't
  declared — a new config setting could be written and never arrive.
- `?refresh=1` never re-probed the encoders: `if not (refresh or …)` had the precedence inverted.
- The encoder probe reported `built: true` from an empty `-encoders` listing; it now reports `null`, meaning
  "unknown", rather than a confident lie.
- `ffmpeg_mgr.find()` called with no argument ignored the configured FFmpeg path.
- Whole-package settings save re-submitted a snapshot ~15 minutes old (`保存设置（132 项变更）`) — the concrete case
  that motivated saving only changed keys.
- `api_music_search` persisted `sources` into `musicdl_sources` and called `cfg.save()` as a side effect, with no
  `ConfigBody` field for it; the default search sources had drifted to two platforms and were restored to five.
- Karaoke `.vtt` reported 2,500 characters/second: the inline `<00:00:35.626>` timing tags were being counted as
  text and 0.01 s flash cues as reading time. Now stripped by `_qc_plain()`, cues under 0.1 s excluded.
- `GET /api/auth/status` wrote a 48-character `web_auth_machine_token` into the real `config.json` — a read endpoint
  with a side effect. Only `POST /api/auth/machine_token` persists it now.
- CookieCloud had seven separate problems: bare keys written into the state file, failures never recorded, a charset
  garble on non-ASCII payloads, the UUID and a `user:pass` pair leaking into logs, a "loopback" claim in the UI that
  wasn't true, `cookiecloud_state.json` missing from the packaging exclusion list, and a frozen timestamp when a
  call threw.
- A false green that only appears in a full batch run: CookieCloud's "content unchanged" verdict was reading the
  sync-timestamp line, so it was green when run alone and red when another suite ran first.
- `matchgate_test.py` G9 had been dead *before* this release: the assertion looked for `"> 不像</span>"` with a space
  the UI never had. The test was fixed, not the product; the replacement pins the whole rejection sentence in
  `:title`.

Caught while packaging:

- One stray `|` in the exclusion regex created an empty alternative, which matches everything. The script reached
  "完成：…zip", exit code 0, every in-package check green, `leaks=[]` — **and the package had no interface at all.**
  Fixed, and `check_present()` now names every file that must be in the zip and aborts if one is missing.

Caught as false reds, not product bugs:

- `siteproxy_test.py` judged 12 "should use the proxy" cases as `inherit` on a re-run with the table untouched: the
  suite was reading this machine's proxy address.
- Three suites (`potdaemon_test.py`, `potcomponent_test.py`, `matchgate_test.py`) resolve `pack_release.py` and
  `static/index.html` relatively, so starting them from `tests/` instead of the `web_app` root raised
  `FileNotFoundError` — three invented reds.
- Two self-test suites (`hardsub_e2e.py`, `subrules_test.py`) had their target hardcoded to the instance the
  developer uses daily, so their log lines landed in the user's `app.log` and one of them rewrote the user's real
  subscription rules. Both now spawn their own instance: `MEDIADOWNLOADER_STATE_DIR` at a `tempfile.mkdtemp()` plus
  `MEDIADOWNLOADER_PORT` on a port freed by `bind(0)`, torn down with its state directory at the end. The guards are
  `G1`/`G2` and `H1`–`H4`: the first asserts nothing new landed in the project-root log (comparing only the bytes
  appended after the run started, because that instance may be writing concurrently), the second is a positive
  control proving the lines did land where they belong.

### Verification readings

- Full batch after the fixes: **59 suites, 3,796 assertions, nothing red**; `python -m py_compile server.py
  pack_release.py` passes.
- Counting caveat, learned the hard way in this batch: four suites print `OK` instead of `PASS` (140 items), so a
  `^PASS` count reads 3,656 — and a red assertion prints nothing, so the judgement is each suite's exit code, never
  the line count.
- Screenshots in `docs/screenshots/` were re-shot against a throwaway instance, never the one in daily use, and the
  download directory was rewritten to a neutral path before shooting: the field on the home page would otherwise
  have published this machine's user path. The pixels are subject to the same redaction rule as the text.

### Published artifacts

- `dist/MediaDownloader-1.4.0-portable.zip` — **219.2 MB**, 10,899 entries; expanded 564.9 MB
  (`runtime` 322.4 MB + `tools` 234.5 MB + `chromaprint` 4.0 MB + `docs` 1.3 MB + `static` 771.8 KB +
  `extension` 28.7 KB + `plugins` 2.3 KB).
- Four in-package gates: `check_present`, `check_module_imports` (14 top-level modules), `selfupdate_probe`
  (the bundled pip installs and imports one round), `smoke_test` (starts the server, hits `/api/music/status` and
  `/api/components`, 12 bundled components matched). Private-data scan `leaks=[]`; `cookies/` holds only the
  placeholder, `Downloads/` is empty.
- 45 application files inside the zip hashed identically to the working tree **at the commit that was packaged** — so
  that specific download is reproducible from the repository at that commit. Later commits (this file included) are
  not in the archive until it is rebuilt.
- **Checksums are deliberately not written into this file or its Chinese source.** A zip cannot carry its own
  checksum and stay byte-identical to itself; the exact bytes and hex live in the sibling
  `MediaDownloader-1.4.0-portable.zip.sha256`, verifiable with `sha256sum -c` from inside `dist/`.
- **Relation to the GitHub Release**: the asset published as `v1.4.0-portable.zip` is byte-identical to that local
  build — 229,823,103 B, and the digest in the sibling `.zip.sha256` equals the one GitHub reports for the asset
  (both read on 2026-10-16). What trails the archive is documentation only: the release record in the repository has
  moved on since the archive was compressed, and re-compressing a 219 MB package for a docs-only delta has
  deliberately been left for a decision rather than done silently. One genuine open item, also left by decision:
  the `v1.4.0` tag still points at an earlier commit than the release's content.
- Interface language is rolled out in batches. In the working tree — not yet in the published archive — the first
  batch covered the chrome (brand, sidebar group names and items, page titles, header counters and tooltips, Element
  Plus's own strings); **the second batch covered every page body, all 17 of them** (see *After v1.4.0* below). Still
  Chinese by design: backend error text (`friendlyError`'s 22 branches, its own batch), runtime log lines written by
  the backend, and the `ACTION_NAMES` action-name table — all of them written records and targets of the assertions
  above.

---

## v1.5.4 · 2026-10-26 — this round's package

This round started from the log of a YouTube download that would not finish: the analysis said "done", the list only
had 180p, and the download failed three times with `No video formats found!`. The cause was yt-dlp's JS challenge
solver never running. The analyse page also got the whole row of subtitle options it was missing, and the
"download section" path was fixed - it had never worked.

### Only storyboards left: the EJS solver was not running

- The 180p was a misreading: it is the height of the cover image `sb0` (320x180). `_h()` and `_yt_max_h()` picked
  heights without excluding storyboards, while the download side - which only counts video codecs - correctly said 0p.
- Reproduced with the same proxy and cookies: `yt-dlp -F` listed 4 storyboards and warned `Signature solving failed`
  and `n challenge solving failed`; without cookies it is `Sign in to confirm you're not a bot`, so cookies and PO
  tokens were both fine (`tools/bgutil-pot-server` still mints tickets and `/api/components` says the plugin and the
  service are both reachable).
- Root cause: yt-dlp 2026.10.21 defaults `js_runtimes` to `{'deno': {}}`. This machine has Node, not Deno, so the
  challenge solver never ran and YouTube withheld the separated streams.
- Fix: `_ydl_opts` keeps the deno default and also enables Node when `shutil.which("node")` finds it; analysis and
  download share one opts builder. Measured on the same video: 0 video tracks -> 25 video tracks, up to 1080p; one
  parse 19.6-25.0s -> 6.6-9.2s.

### Subtitles on the analyse page

- `/api/analyze` now returns `subtitles`: `_subtitle_tracks()` folds `subtitles` / `automatic_captions` into one row
  per language, manual wins over the same language's auto track, `live_chat` is not a subtitle, and each row carries
  `lang` / `name` / `auto` / `formats`.
- The analyse page gained a subtitle block: language chips with a manual/auto badge, select all / clear, a selected
  counter and "download with these settings"; download options (embed, separate file, Whisper transcription) and
  translation options (machine-translation switch, target language, engine) sit in the same view. When none of the
  previously selected languages is in this batch the first manual track is picked; playlists do not show the block.
- `subtitle_target_lang`, `subtitle_translate_provider` and `local_ai_mt_after_transcribe` joined `AddUrlsBody` and
  the per-task override list, so they apply per task; unset stays None and the global reading still rules.

### Two places that reported success without doing it

- **Section downloads never worked**: `download_range_func(None, [sec])` handed the string
  `"*00:00:10-00:00:30"` to yt-dlp as a range list, which unpacked it character by character and ended the task with
  `too many values to unpack (expected 2)`. It now goes through `yt_dlp.parse_options(["--ignore-config",
  "--download-sections", sec])`, so comma-separated ranges, negative timestamps and `inf` follow the CLI. Measured: a
  10-30 s section produced 400,852 B with a 640x360 / 322-frame video track, and the log records the clip.
- **The free translation engine cried success**: rate-limited by Google, `deep-translator` returned every line
  unchanged, and `translate_with_fallback` only compares lengths, so the log said `翻译成功: deep_translator`
  while the file was still Japanese. "Nothing changed at all" now raises and the fallback chain moves on. Measured:
  `deep_translator 失败 -> deepl -> 翻译成功: deepl`, with real English in `.ja.en.srt` and `.ja.en.bi.srt`.

### Known limitations (not changed this round)

- In a section download with subtitles the embedded subtitle track is still full length, so the container reads as the
  whole video (the video track really is cut - that 400,852 B file reports 271.5 s).
- When only storyboards are left, `_h()` / `_yt_max_h()` still report their 180 as "about 180p". Enabling Node means
  this path is no longer reached, but the reading itself is unfixed.

### Self-tests and packaging

- Full sweep **72 suites** (69 `*_test.py` + 3 `*_e2e.py` / `*_selftest.py`), bad=0, counted by `^(PASS|OK)` lines;
  this round adds `tests/info_subtitle_test.py` with 42 items. The batch needs `PYTHONIOENCODING=utf-8`: without it
  five suites die while printing unusual characters (`UnicodeEncodeError: 'gbk'`) - console encoding, not a failed
  assertion.
- Live readings: one YouTube link 29 formats / 25 video tracks / up to 1080p / 1 subtitle; one Bilibili link
  15 formats / 12 video tracks / up to 1080p; 18 component rows with `update-check` reporting nothing to update; PO
  token plugin and service both reachable; aria2 RPC online; 50 effective trackers.
- Browser check of the analyse page: the block renders "Subtitles (1 parsed) - Japanese (ja) - manual", the chip
  toggles between 0 and 1 selected, all 16 new strings show in English and back in Chinese, and the intercepted
  `/api/download` body carries `subtitle_langs: "ja"`, `embed_sub: true`, `local_ai_mt_after_transcribe: true`,
  `subtitle_target_lang: "zh"`, `subtitle_translate_provider: "deepl"`.
- **Redaction while we were at it**: a user-facing error example in `server.py`, a "measured on this machine" comment in `music_search.py` and a docstring in `telegram_mt.py` carried this machine's proxy port verbatim; they now use a generic example or a `<port>` placeholder - only that address is replaced, every other reading stays literal. These three have been inside the package since v1.4.0 and were not introduced this round; the local state file `config.json` is neither packaged nor committed.
- `appVersion` moves to `v1.5.4`.

### Artifact readings (built 2026-10-26 19:08)

- **Artifact**: `dist\MediaDownloader-1.5.4-portable.zip`, **230,684,164 B (220.0 MB)**, sha256
  `b13b148c878113f86f0bd85533b795ba31791dd5364d5bb6f426645a10e15c02`, 10,906 entries; `sha256sum -c` from `dist/`
  passes and an independent recomputation equals the sidecar. Staged directory 595,251,353 B (567.7 MB): runtime
  322.4 MB / 9,795 files, tools 234.5 MB, chromaprint 4.0 MB, static 3.0 MB, docs 1.4 MB, with extension /
  plugins / cookies at KB scale.
- **Packaging self-checks**: 18 dependencies + 3 tools in the manifest (ffmpeg 9.0.1, yt-dlp.exe 2026.10.21,
  N_m3u8DL-RE 0.6.0); must-include files present (13 under `static`); 21 `__pycache__` removed; 15 top-level
  modules import inside the package; in-package pip install -> import passes; the packaged service answers the
  smoke call with all three version tiers and 12 manifest hits; the manifest records `app = 1.5.4`,
  `python = 3.12.2`, `built = 2026-10-26 19:08`.
- **Package versus source**: 58 application entries, 54 byte-identical to the working tree (CRLF folded), 4
  generated by the packager, none unexplained. Zero private/state hits (`config.json`, `cookies.txt`,
  `history.json`, `app.log`, `*.bak-*`, `__pycache__`, `.pyc`), and `Downloads` / `Whisper` /
  `browser_sniff_profile` / `local_index` are removed before compression in this archive and in 1.5.3 alike.
  Zero hits for this machine's proxy port in packaged text - the three that shipped since v1.4.0 were redacted
  this round. The packaged `CHANGELOG.md` is CRLF (2123 lines, 0 bare LF), carries v1.5.4 and does not contain
  this digest.
- **The fixes really are inside**: the packaged `server.py` has `_subtitle_tracks()`, `js_runtimes["node"]` and the
  `parse_options(... "--download-sections" ...)` call; `voice_tools.py` has the "nothing translated" raise; the
  packaged `static/index.html` has exactly one version string, `v1.5.4`, and the subtitle block.
- **Runtime reuse**: `PKGS` and `requirements.txt` were untouched, and a full build still stops at
  `zhconv==1.4.3` (the index offers up to 1.4.1), so the verified v1.5.3 runtime was copied whole (11,179 files,
  9,795 after the `__pycache__` sweep) and `--skip-runtime` finished the copy and the four self-checks. Same
  verified combination as 1.5.2 / 1.5.3.
- **The artifact changed**: 230,684,164 B against 1.5.3's 230,674,638 B, 10,906 entries, mtime from this build -
  readings, not just an exit code.
- **Tag / release**: this commit is pushed to `origin/main`; no tag created or moved and no GitHub Release
  touched - the zip is not in the repository (`dist/` sits outside the allow-list), so the Release asset has to
  be uploaded by hand. Awaiting approval.

---

## v1.5.3 · 2026-10-23 — this round's package

This round first removes the background cost behind "leave it overnight and it comes back sluggish", then adds a
liquid-glass skin. The version cache and the idle cleanup are two ends of the same thing: do not start a row of
subprocesses on every start or when coming back from idle, and release the rebuildable models and caches once nobody
is using the app. The glass skin is visual only - no behaviour changes.

### Why it got sluggish: measure first

The backend was not the culprit: a warm `/api/status` answered in 3.8-4.1 ms, memory was flat, and there was no
sleep/wake event that night. The remaining cost was in the browser plus asking every dependency for its version
after each restart - the component check took about 13 seconds to fill in, starting ffmpeg / yt-dlp / whisper
subprocesses one by one, while the loaded Whisper model and the URL parse cache stayed in memory when idle.

- **Version probes land on disk for 24 hours** (`STATE_DIR/version_cache.json`): ffmpeg / N_m3u8DL / aria2 validate
  by path + mtime, yt-dlp by the mtime signature of `version.py` and `extractor/youtube.py`, whisper and the
  upstream-latest table by TTL. A hit returns without starting a subprocess; "Check now" bypasses the cache, and any
  successful component update drops the affected key. Measured: after a restart the component check is complete in
  about 3 seconds, previously about 13.
- **Idle cleanup after 30 minutes**: `_idle_janitor_loop` looks once a minute and only acts when the last user
  request is at least 30 minutes old, the queue has nothing running or pending, no AI job is active, and no
  component check or one-click update is running. It releases loaded Whisper models, the parse cache, the in-memory
  version caches, and removes preview files under `_preview` older than 24 hours; cookies, history and finished
  downloads are never touched. `/api/status` exposes `idle_clean_at` and `idle_clean` with four counters, and the
  log gets exactly one keyed line (`srv.idle.cleaned`, Chinese and English).
- **Health probes and page polling are not "someone is using it"**: `/api/health`, `/api/status` and `/api/tasks` do
  not refresh the activity clock - otherwise background polling would postpone cleanup forever. The clipboard's
  2-second poll is gone as well: the server still watches, and the page asks once on entry and once when it returns
  to the foreground.
- **Sandbox verification**: with a temporary `STATE_DIR` / `PREVIEW_DIR` and the threshold shortened to 2 seconds, an
  old preview is removed while a new one stays; a second version read in the same process starts no subprocess, and a
  restart reads the disk instead of probing again. `tests/idlehygiene_test.py`, `tests/idlecost_test.py`,
  `tests/components_test.py`, `tests/clipboard_test.py` and `tests/pagemount_test.py` cover all of it.

### Liquid glass: every glass background is now a solid colour

- Page background, cards, sidebar, header, player bar, dialogs, dropdown poppers and primary buttons are all solid;
  the radial glow on cards and the aurora `body::before` are gone, and the boot splash no longer uses orbs or
  gradients. `--glass-panel` (0.74 light / 0.8 dark) is dedicated to floating layers so a dialog over the 0.5 black
  scrim no longer turns mid-grey with unreadable body text.
- The sidebar follows the theme accent in both the base and the glass skin:
  `color-mix(in srgb, var(--accent) 30%, #0b1220)`. Blue / orange / pink / green / clay were each captured, the
  sampled colours differ, and white text still contrasts.
- Light/dark still follows the system and can still be overridden; both skins were screenshot-checked
  (`tmp/glass_shots/`).

### Packaging

- `pack_release.py` now excludes `version_cache.json` in both the exclusion regex and the post-build leak check: it
  holds absolute paths of this machine's components and their upstream versions, and a new machine should probe for
  itself. `tests/idlehygiene_test.py` C8 pins it.
- `appVersion` moves to `v1.5.3`. Full sweep: **68 suites, bad=0**.

### Artifact readings (built 2026-10-23 16:57)

- **Artifact**: `dist\MediaDownloader-1.5.3-portable.zip`, **230,674,638 B (220.0 MB)**, sha256
  `e45ca61e391ee9a3da921f4fdbf3e93a89367188c18eb4cf6ffe8ea2141241e3`, 10,906 entries; `sha256sum -c` from `dist/`
  passes. Staged directory 567.6 MB: runtime 322.4, tools 234.5, static 3.0, chromaprint 4.0, docs 1.4, extension
  28.7 KB, plugins 2.3 KB, cookies 184 B (placeholder note only).
- **Packaging self-checks**: 18 dependencies + 3 tools in the manifest; must-include files present (13 under
  `static`); 21 `__pycache__` removed; 15 top-level modules import inside the package; in-package pip install ->
  import passes; the packaged service answers the smoke call with all three version tiers present and 12 manifest
  hits; the manifest records `app = 1.5.3`, `python = 3.12.2`, `built = 2026-10-23 16:57`.
- **Package versus source**: 58 application entries, 54 byte-identical to the working tree (CRLF folded), 4 generated
  by the packager (`components_bundled.json`, the usage note, the launcher, the cookies placeholder). Zero
  private/state hits (including the new `version_cache.json`), zero forbidden directories, no `.pyc`, no `/venv/`.
  The packaged `CHANGELOG.md` is CRLF (2041 lines, 0 bare LF), carries v1.5.3, and does not contain this digest -
  the copy inside the zip predates the build and still says readings are appended after it.
- **Runtime reuse and a failed full build**: the full build was attempted first and stopped at `zhconv==1.4.3` -
  the index only offers up to 1.4.1; the source-build fallback then hit `MemoryError` while building `construct`.
  `PKGS` and `requirements.txt` were untouched this round, so the verified v1.5.2 runtime was copied whole into
  `dist/MediaDownloader-1.5.3-portable/runtime` (9,795 files) and `--skip-runtime` completed the copy and the four
  self-checks. The pin issue is left for the next packaging round; this archive runs on the same verified
  combination as 1.5.2.
- **Tag / release**: nothing pushed, no tag created or moved, no Release touched - awaiting approval.

## v1.5.2 · 2026-10-22 — this round's package

One fix ships here: **"skip already downloaded" ignored the kind of output, so anyone who had downloaded the video and
then asked for audio-only got nothing at all** (#136 - details and the real A/B in the section below). The v1.5.1
package already carried #135 (float16 on CPU raising at model construction), so this release only brings the published
bytes up to date. It also corrects something I said earlier: `30280` in that log is bilibili's **192k audio stream**,
not a video-only stream, so the "video stream + audio extraction" contradiction I described never existed and the
greying-out of the two control rows that I proposed from it **was not done**.

`appVersion` moves to `v1.5.2` (still the single line in `static/index.html`). Full sweep: **64 suites, bad=0**.

### Release artifacts

- **Artifact**: `dist\MediaDownloader-1.5.2-portable.zip`, **230,645,942 B (220.0 MB)**, sha256
  `c9e543369f613c23b64d1581562083c6f7e720fdde06ae78d03bbe9d2ddbbe6e`, 10,906 entries, plus the `.sha256` sidecar.
  Staged directory 567.5 MB: runtime 322.4, tools 234.5, static 3.0, chromaprint 4.0, docs 1.4, cookies 184 B
  (placeholder note only).
- **Packaging self-checks**: manifest of 18 dependencies + 3 tools; the must-be-included check passes (13 items under
  `static`); 21 `__pycache__` removed; 15 top-level modules import from inside the package; the in-package pip
  install -> import probe passes; the packaged service answers a smoke call with all three component version tiers
  present and 12 manifest hits. Manifest records `app = 1.5.2`, `python = 3.12.2`, `built = 2026-10-22 15:10`.
- **Package versus source**: of the 59 application entries, 55 are byte-identical to the working tree (CRLF folded);
  the other four are generated by the packager (`components_bundled.json`, the usage note, the launcher, the cookies
  placeholder). Zero hits for private/state files (`config.json`, `cookies.txt`, `history.json`, `library_cache.json`,
  `music_favorites.json`, `catcatch_rules.json`, `app.log`, `pack_release.py`, both `download_archive*.txt`), zero
  forbidden directories among the application files, no `.pyc`, and the separator `venv` is not shipped (zero `/venv/`
  hits). The packaged `CHANGELOG.md` is CRLF (1947 lines, all of them with a carriage return), carries the v1.5.2
  section, and **does not contain this digest** - release notes never quote their own.
- **Runtime reused**: `pack_release.py` and `requirements.txt` are unchanged since v1.5.1, so `--skip-runtime` re-ran
  only the copy step and the four self-checks; the runtime was copied whole from the 1.5.1 staging directory (9,795
  files, 0 failures). One reading that bears on #134: the packaged runtime has no `numpy`, `numba` or `librosa` at
  all, so that upper-bound mismatch is not an out-of-the-box breakage in the portable package - it only appears once
  dependencies are installed from inside the program.
- **Tag**: lightweight `v1.5.2` points at `c26d46c` - the version-and-notes commit, i.e. the bytes this archive was
  built from. `v1.5.1` (`6e3ac97`) and `v1.5.0` (`fc2a9b4`) and their Release assets were left exactly as they are;
  nothing was replaced or deleted.
- **Push and publish (same day, after a wait)**: for about ninety minutes the local proxy answered CONNECT with 200 and
  then dropped every TLS handshake inside the tunnel (GitHub, PyPI and Hugging Face alike), a plain HTTP request through
  it came back 502, and without the proxy GitHub connections were reset while domestic sites worked - so the round ended
  at "package built". Once the proxy's upstream came back the rest was done in order: `git push origin main v1.5.2`
  (remote `main` moves `9d33446` → `05e0d04`, tag `v1.5.2` lands on `c26d46c`), then the Release (id 420541780,
  https://github.com/QingYan1012/media-downloader-web/releases/tag/v1.5.2) with both assets uploaded, the byte counts
  confirmed server-side, and the archive fetched back through `browser_download_url` and re-hashed - identical to the
  local file (`c9e54336…bbe6e`), 8/8 publish checks green. `v1.5.0` and `v1.5.1` and their assets were left untouched.
  One honest wrinkle at that moment: the `CHANGELOG.md` inside that published archive was written before the push
  succeeded, so the copy *in the package* still said the push and Release were pending.
- **Rebuilt (same day, after the user ran #137 by hand)**: that wrinkle and the mux-audio feature itself are both
  settled by rebuilding this archive - `appVersion` stays `v1.5.2` (not one character changed), what changes is the
  text carried inside the package and the multi-track feature it now has.
- **Readings of the rebuilt archive**: `MediaDownloader-1.5.2-portable.zip`, **230,660,015 B (220.0 MB)**, sha256
  `bcb00cf95ae0bc8a02e4c472d92c2cd508dbe5454a1c0d3e18171d27459de477`, 10,906 entries; 59 application entries of which
  55 are byte-identical to the working tree and 4 are generated by the packager; zero private-file hits, zero forbidden
  directories among the application files, no `.pyc`, no `/venv/`. The packaged `CHANGELOG.md` is CRLF (1987 lines, all
  with a carriage return) and does not contain this digest. Manifest records `app = 1.5.2`, `built = 2026-10-22 18:10`,
  and the four packaging self-checks read the same as before (18 dependencies + 3 tools, 13 items under `static`,
  21 `__pycache__` removed, 15 top-level modules import, in-package pip install -> import passes, smoke answers all
  three component tiers with 12 manifest hits). The bytes behind this archive are `7c7079d` - #137 itself plus the
  reworded release notes - and the tag and the Release assets are aligned to it.
- **What alignment meant**: tag `v1.5.2` moves `c26d46c` → `7c7079d` (force-pushed; the `v1.5.0` / `v1.5.1` tags were
  left alone); on Release 420541780 the old zip and `.sha256` were deleted first, then the new pair uploaded (the server
  took 230,660,015 and 101 bytes, matching the local files), and the body was replaced with the version that carries the
  mux-audio section. Finally the archive was pulled back through `browser_download_url` and re-hashed -
  `bcb00cf9…de477`, byte-identical to the local file, and the published `.sha256` names the same digest. The previous
  body and asset list were backed up first under `tmp/release_backups/` (timestamp 20261022-182323).

---

## After v1.5.2 - "mux audio" on the files page: several audio tracks into one video

The user asked whether the app can mux different audio files into a video. It could not: `_ydl_opts` uses `bv*+ba/b` and yt-dlp merges exactly one best audio stream (there is no `audio_multistreams` anywhere in the repo), the hand-written sniff merge is fixed at `-map 0:v:0 -map 1:a:0?`, and the separator's stems plus the mixer's export are separate audio files that never go back into the video. This adds it (#137, four decisions approved one by one).

- **Entry point**: the video row's "more → mux audio" (`v-if="isVideoFile(row)"`, so audio rows have no such item). The dialog first lists the audio next to this video - its own stems and audio files in the same folder, each tagged with its origin - and browses the download folder for anything else. Every picked track gets language (nine choices) / track name / codec, the arrows set the track order of the output, and the "default track" field decides which one the player opens with.
- **Backend**: `GET /api/files/audio_candidates` and `POST /api/files/mux_audio`, with the command assembled by the pure function `build_mux_command()` so the suite can compare the argument list directly. The video stream is always copied, the container is always mkv, the output is a separate `name.mux.mkv`, and an existing file needs "overwrite the old output" first (409).
- **Two things only measurement told**: `-disposition:a:N default=0` is not valid - ffmpeg 8.1 exits with `Unable to parse "disposition" option value`, and clearing the flag means passing the value `-default`; and leaving disposition out entirely makes mkv mark *every* track as default, so each one has to be named. A mov_text subtitle is refused by mkv, so the failure is retried without subtitles and both the log line and the completion message say the output carries video and audio only.
- **No guessing**: the new tracks' indices start after however many audio tracks the source already has, so when ffprobe cannot answer, the dialog says it cannot tell and points at FFmpeg rather than assuming 0 - assuming 0 would paste the language and track name onto the original track and still report success.
- **Checks**: new `tests/audio_mux_test.py`, 46 checks (ffmpeg stubbed, temporary directory only); the H20 action-table counter in `tests/i18n_test.py` moves from 140 to 141. Two live passes: one through the real route with the real ffmpeg (17 checks, the output read back track by track with ffprobe for codec, language, name and default flag), one clicking through the real UI (18 checks, sandbox instance, one screenshot of the dialog in each language).
- **Packaging**: this was not in the first v1.5.2 build; after the user ran it by hand the same version number was
  rebuilt, so it ships with the `v1.5.2` artifacts (readings in the "Rebuilt" bullet of the section above).

---

## After v1.5.1 — an audio-only request must not be blocked by the video's download record

The user asked, screenshot in hand: "I picked audio-only, why did it still download a packaged video?" Comparing the
log with the disk, **nothing was downloaded at all that time**:

- 14:13:16 the video finished (`….mkv`, 97,043,593 B); at 14:14:37 and 14:15:34 two audio-only requests came in, both
  correct (`指定格式: ba/bestaudio`, `目标容器=m4a`, `后期处理=FFmpegExtractAudio`), and both answered
  `本次未重新下载：….mkv 已在下载记录里`. There is **no m4a in the download directory** - the queue rows were showing
  the old mkv, which is exactly what made it look like "audio-only downloaded a video".
- **Root cause**: every line in yt-dlp's `download_archive` is only "site key + video id" (here
  `bilibili BV1AHnB6NEhM`) - **no format**. So once a video has been downloaded, every later request for it,
  audio-only included, is treated as done and yt-dlp returns without writing anything.

Per the approved 口径 - **mismatch means re-download**:

- `archive_filename(audio_only)` gives audio-only its own record file (`download_archive_audio.txt`) while the video
  one keeps its exact old name, so nobody's existing 46 records are invalidated. Presence checking now asks
  "has **this kind of output** been downloaded" instead of "has this video been downloaded": video first then
  audio-only really downloads, and a second click in the same kind still skips (separate files ≠ re-downloading
  every time).
- "Clear download records" deletes both files (clearing only the video one would leave audio requests silently
  skipped) and returns a `cleared` list; the sentence names both files in both language halves.
- **A UI state leak fixed on the way**: clicking 仅音频 writes `m4a` into the container selector, and that chip only
  restored `force_format` and `audio_only` afterwards - **not the container** - so the next video click would extract
  audio instead. The chip now remembers and restores it, since it was always meant to apply to that one run.
- **One correction of mine**: I first read `指定格式: 30280` as "bilibili's video-only stream" and from that inferred a
  self-contradictory request (video stream + audio extraction), and proposed greying the two control rows against
  each other. Measured: **30280 is the 192k audio stream** (`vcodec none / acodec mp4a`), so both requests were
  ordinary audio-only ones - the contradiction never existed and the greying idea was built on a wrong premise,
  so it was not done.

- Checks: new `tests/archivekind_test.py`, 8 assertions (both filenames; one real opts dict built offline to see which
  record file is attached; neither attached when "skip already downloaded" is off; the download call site really passes
  `audio_only`; clearing removes both and reports `cleared`; the UI chip remembers and restores the container; the
  sentence names both files in both dictionary halves). Full sweep **64 suites, bad=0**.
- Real A/B (own sandbox download dir, never the project's `Downloads/`): seed `bilibili BV1AHnB6NEhM` into the video
  record, then run a real audio-only download - **this time it is not skipped**, it goes through extraction and writes
  itself into `download_archive_audio.txt`, and the video record stays byte-identical. (That arm's output was an mp4
  rather than an m4a because the hand-made probe cfg did not carry the format string the real request path computes -
  unrelated to this fix.)

---

## v1.5.1 · 2026-10-22 — published

A patch package for one fix: **asking for float16 while the device is CPU makes Whisper fail to load, and the error
then told you to install something that was already installed** (#135). The v1.5.0 archive does not contain it, so
this one goes out separately.

- **What happened**: settings were `whisper_device=auto` + `whisper_compute=float16`, while this machine's main
  environment ships a `+cpu` torch build - so the device resolved to cpu and the tier stayed float16. ctranslate2 4.8
  does **not** downgrade silently; it raises inside `WhisperModel()`:
  `ValueError: Requested float16 compute type, but the target device or backend do not support efficient float16
  computation.` Measured with the same large-v3 weights here: float16 raises after 5.2 s, int8 loads in 5.9 s. It only
  appeared after faster-whisper was updated to 1.2.1 (pulling ctranslate2 4.8.2) - older versions accepted fp16 on CPU
  by converting internally.
- **The second untruth**: the last log line then said "faster-whisper or the Whisper executable was not found, run
  pip install faster-whisper" - while 1.2.1 was installed and working up to that call.
- **What changed**: any `float16` / `int8_float16` tier that lands on cpu becomes int8, with a warning naming the tier
  it came from; **a real GPU still gets float16** (that is what the option is for); cpu + int8 stays quiet. The CLI
  fallback message was split: installed-but-this-run-failed now says "see the line above" instead of pushing a pip
  command, and the genuinely-missing case keeps its installation guidance.
- The warning carries no message key: it logs through the bare `log(...)` parameter, which is not one of the three
  receiver forms the i18n gate scans (`log_mgr.log` / `self.log` / `self.log.log`), so keying it would create an
  orphan key (gate K6). It gets a key when #55 widens that form.
- **Checks**: new `tests/whispercompute_test.py`, **12 assertions** (it stubs `faster_whisper.WhisperModel` and asks
  only which `compute_type` was finally passed; **each case clears the in-process `_FW_MODEL_CACHE`**, because
  otherwise later cases never construct a model and read the previous case's tier - a textbook false green).
  Full sweep **63 suites, bad=0**. End-to-end with real speech (a Chinese clip synthesized with edge-tts, CPU, the
  setting deliberately left at float16): one warning, `compute=int8`, `转写完成 (lang=zh, 2 句)`, text correct.

### Release artifacts

- **Artifact**: `dist\MediaDownloader-1.5.1-portable.zip`, **230,639,754 B (220.0 MB)**, sha256
  `b83c5b0deadd9bfc80d48b65a94f24213e33f09103715bc3f8b6b24203f0fbaa`, 10,906 entries, plus the `.sha256` sidecar.
  Staged directory 567.5 MB: runtime 322.4, tools 234.5, static 3.0, chromaprint 4.0, docs 1.4, cookies 184 B
  (placeholder note only).
- **Packaging self-checks**: manifest of 18 dependencies + 3 tools; the must-be-included check passes (13 items under
  `static`); 21 `__pycache__` removed; 15 top-level modules import from inside the package; the in-package pip
  install → import probe passes; the packaged service answers a smoke call with all three component version tiers
  present and 12 manifest hits. Manifest records `app = 1.5.1`, `python = 3.12.2`, `built = 2026-10-22 13:57`.
- **Package versus source**: 42 application files are byte-identical to the working tree (CRLF folded); the four
  package-only entries are generated by the packager; zero hits for private/state files (`config.json`,
  `cookies.txt`, `history.json`, `library_cache.json`, `music_favorites.json`, `catcatch_rules.json`, `app.log`,
  `pack_release.py`), zero hits for forbidden directories, no `.pyc`. The packaged `CHANGELOG.md` is CRLF, carries the
  v1.5.1 section, and **does not contain this digest** - release notes never quote their own.
- **Runtime reused**: `pack_release.py` and `requirements.txt` are unchanged since v1.5.0, so `--skip-runtime` re-ran
  only the copy step and the four self-checks.
- **Tag**: lightweight `v1.5.1` points at `6e3ac97` - the version-and-notes commit, i.e. the bytes this archive was
  built from. `v1.5.0` (`fc2a9b4`) and its Release assets (230,635,022 B / `6ba9ae84…fe00`) were left exactly as they
  are; nothing was replaced or deleted.

---

## v1.5.0 · 2026-10-22 — published

`appVersion` moves from `v1.4.0` to **`v1.5.0`** (the single source is that one line in `static/index.html`;
`pack_release.py`'s `app_version()` reads the same place, so the sidebar, the package name and the README title
cannot drift). This release collects the **32 commits** after `d922732` - the commit behind the previously published
bytes: one feature line (stem separation plus the second layer of audio analysis) and a long run of interface and
runtime-log clean-up. It is not a patch by size - six-stem separation, a stem mixer, the separation chooser, Demucs
model fill-in, and beats/structure would each justify their own minor number.

The sections below are that content, kept where each round wrote them. Two notes on readings: the numbers quoted in
each section are the ones recorded in that round's own commit (this entry consolidates, it does not re-measure), and
the commit count is deliberately not written down anywhere - every new commit made such a line wrong the moment it
was made (it used to say 37, then 28), so ask git with `git rev-list --count origin/main..HEAD`.

What shipped: **#129** six-stem Demucs + a three-way stem range (the default stays "vocals only", byte-for-byte the
behaviour before the option existed) and the stem mixer; **#131** the engine/model/range/device chooser moved to the
files-page action where the click actually happens, which also exposed a real bug (a status read that only loaded on
the voice page left two model dropdowns empty); **#132** Demucs model files joined Components & dependencies as
detect-and-fill, deliberately outside the one-click batch; **#133** beats and song structure folded into the same
audio-analysis output, with **librosa's old reading kept rather than replaced** (synthetic 180 BPM came back as 89.1,
a real 76 as 152, 85.7 as 112.3, while the two neural sources agreed within 1%). Plus **#55** backend-log batches
15-34 - keyed call sites in the gate went **144 → 370**, the dictionary is **3,102 keys per side**, and the
**#93a** fragment-key and **#93b** split-conditional 口径 both landed after being approved first; **#92** the network
reset list stops printing Chinese into an English UI; **#80** the collapsed-rail button returns to the logo row;
**#98** short-window spacing so the live and voice pages need no scrolling; **#96** two test leaks that wrote into
the project's own `app.log` (a full sweep now appends **0 bytes**).

One environment-level defect was found and fixed on the way: numpy 2.5.x in the main environment with numba 0.65
(capped at `<2.5`) makes `import numba` raise, which breaks audio analysis and voiceprint diarization outright.
**This machine hit it twice** - the earlier round rolled numpy back to 2.4.6, this round fixes forward with
`numba 0.68.0` + `llvmlite 0.50.0`. numba still has no row in the components table, so a numpy-only upgrade can
desynchronise them again; that gap is open as #134.

Checks: full sweep **62 suites, bad=0**, of which `separator_test.py` **117** (J1-J9 chooser / K1-K13 Demucs models /
L1-L23 beats and structure), `i18n_test.py` **517 gates, FAILED: none**, `pagemount_test.py` 40. Every live check ran
in its own sandbox (`MEDIADOWNLOADER_STATE_DIR` + a `bind(0)` port, never 8765): 12 checks for the chooser, 6 for the
model row, 14 for the analysis layer.

### Stem separation: a six-stem model, and a stem mixer

Asked whether [StemDeck](https://github.com/stemdeckapp/stemdeck) could be added, we compared it against what this
app already does and took only the two real gaps: **six stems** and **multi-track mixing**. Its bundled FastAPI plus
own Python runtime (700 MB - 1.6 GB) collides with our rule that neither the separation venv nor the weights ship in
the archive, so nothing is integrated - the model choice is borrowed, and the credits list gained an entry for it
(the project is Apache-2.0).

- **`htdemucs_6s` earned its place in the table by running here**: a 4-second synthetic clip on CPU, 262 s, producing
  `bass / drums / guitar / other / piano / vocals` at 705,644 B each. The comment above that table says an unverified
  name does not become an option, because it only means the user clicks it and gets "model would not download" - so
  `mdx23c` and friends still stay out.
- **Three stem ranges, and the default is the old behaviour verbatim**: `demucs_stems=vocal` builds exactly the
  command used before (`--two-stems vocals`, two files); `four` / `six` drop that flag and let Demucs lay out all of
  its stems. The default is written in four places - `DEFAULTS`, `ConfigBody`, the save-time validator and the UI
  initial value - because changing it would silently re-run separation for everyone who upgraded.
- **A range that does not fit the model is refused before the thread starts**: only `htdemucs_6s` can do six, the UI
  option is greyed out and the backend rejects it again. Learning the stem count was wrong after a several-minute run
  is the worst possible failure.
- **Stem mixer** (new card on the voice page): `GET /api/voice/stems` reads exactly
  `<track>/demucs/<model>/<track>/*.wav` - a plain recursive glob would serve two batches of same-named stems for a
  track separated twice with different models - and skips its own `*-mix-*` output. `POST /api/voice/mix` mixes with
  the local ffmpeg: muted stems never reach the command, output is WAV (`pcm_s16le`) or MP3 (320k), written next to the
  first stem.
- **`amix` runs with `normalize=0`**: left on, it divides the level by the track count, so the balance you dialled in
  the UI is not what lands in the file. The first cut also failed outright - filter chains need `;` between them, and
  ffmpeg rejected the chain with a 500.
- **The fader stops at 100% on purpose**: preview goes through `element.volume`, which cannot exceed 1, so a slider
  that offered 200% would be lying. Real gain would need a Web Audio `GainNode` layer, left for later.
- The engine option no longer hard-codes a stem count ("Demucs (four stems...)" became range-driven), and
  `tests/separator_test.py` gained I1-I14 covering it. Two existing assertions had their sampling window widened the
  honest way - they sliced a fixed character count / scanned the whole file, and this change pushed the target out of
  frame without anything actually breaking.
- End to end in a self-spawned sandbox: six stems listed, a four-stem mix written (guitar and piano muted, bass at
  50%), `ffprobe` reading it back as `pcm_s16le / 44100 / 2ch`, and the browser button producing the same file with a
  toast and zero `pageerror`.

### The chooser moved to where the action is

The first thing the user said after that round was "there is no engine chooser on separate vocals". Six stems and the
mixer had both been built on the voice page, but separation is started from the files page - and clicking it there
offered no choice at all. Everything existed; it was sitting in the wrong place.

- **The files page's "more → separate vocals" opens a chooser now**: engine / model / stem range / device, prefilled
  from Settings, and what you change applies to this run only. The voice page card stays the home of the defaults, so
  starting a job from the dialog never writes back to `settings.*` (assertion J3 is exactly that: no assignment to a
  settings field anywhere in the dialog's code). After starting, the button becomes "open the mixer" and carries the
  file's path across.
- **The mixer gets an entry point on the files page too**: for a file that has been separated, "mix stems" jumps to the
  mixer and reads the stems back immediately. It draws no divider line - it is the next step of separation, not the
  head of a family.
- **One copy of the model list**: the four Demucs names used to be hard-coded twice in the UI (voice page + dialog).
  `/api/ai/voice_status` now returns them as `separation.demucs_models` and both dropdowns render from it - a second
  copy drifts from the list the save-time validator checks, which would then mark the app's own option illegal.
  Assertion A4 changed shape accordingly: it no longer compares a hard-coded quartet, it requires both dropdowns to be
  `v-for` and forbids a written-out option.
- **A real bug the live run caught (not a wiring problem)**: `loadVoiceStatus()` was only called when the voice page
  opened, so a user who went straight from the files page to the chooser found both `v-for` dropdowns **empty**, with
  the selection degraded to a bare id (`htdemucs_6s`, `bs_1297`). The first diagnosis was wrong - it blamed `v-if` /
  `v-else` reusing the component instance, added `key` to both branches, re-ran: still empty. Looking at the DOM showed
  the static options (engine / device / stem range) present and only the `v-for` ones missing, which points at data that
  never arrived. The fix is `if (!sepInfo.value) loadVoiceStatus()` in `openSepDlg`, and the `key` experiment was
  reverted. Offline gates cannot see this: `voice_status` is stubbed in that batch, and the stub always returned both
  fields.
- **Changing the model pulls the stem range back, never forward**: `htdemucs_6s` with "six stems" switched to another
  model clamps to "vocals only", but switching back does not restore six - that would be deciding how someone else
  wants to run their job.
- Tests: `tests/separator_test.py` gained J1-J9 (the old bare POST is gone, the five overrides match the five
  `body.get()` calls one for one, the dialog never writes settings, the clamp rule, both `return` lines carry the new
  names, the six new keys exist in both dictionary halves, and opening the dialog fetches the status). `pagemount_test.py`
  P8's menu count moved 15 → 16; the number of divider lines is still five. The live run passed 12 checks in a
  self-spawned sandbox: prefilled readings, the field set changing with the engine, clamp and re-pick, the five
  overrides in the intercepted request body, the jump carrying the path, six stems read back from the files-page entry,
  zero `pageerror`.
- Files touched: `server.py` (`voice_status` also returns `demucs_models`), `static/index.html` (the dialog, two menu
  items, both `v-for` dropdowns, the `sepDlg` family of functions), `static/i18n.js` (+6 keys per language),
  `tests/separator_test.py`, `tests/pagemount_test.py`, `CHANGELOG.md`, `CHANGELOG.en.md`,
  `docs/详细功能介绍.md`, `docs/detailed-features.en.md`.

### Demucs models joined the components table: what is missing, and a button that fills it in

The other half of the user's request - "add the dependency too, with update detection". The four RoFormer weights were
already listed; Demucs was not, because that path does not go through us at all: the package fetches its own files
into torch's cache, so the table could not see them and nobody could tell how long "separate with htdemucs" would take
the first time.

- **The 口径 first, because it decides the wording: these models have no version of their own.** What can be detected
  is presence - how many files are there, how many are missing; what "update" can mean is filling in the gap. The line
  on screen says `{ready} / {total} models complete, {n} file(s) still missing` and never "an update is available",
  because there is no such thing here.
- **Names, addresses and checksums are all read from the installed package**: `remote/files.txt` is "`root:` subfolder
  plus one filename per line", and each `remote/<model>.yaml` lists the first eight hex digits of those filenames -
  only the two tables together give a URL. `voice_tools` keeps no second copy (K1: a literal
  `xxxxxxxx-xxxxxxxx.th` may not appear in that source). A signature listed in a yaml but missing from the index must
  be zero (K2) - the symptom of a parsing hole is a UI that says "missing" forever.
- **Checksums compare exactly as far as they go**: the second half of the filename is an 8-digit sha256 prefix, and
  both torch.hub and demucs (`check_hash=True`) verify only that far, so we verify only that far and do not promise
  more. `_finish_weight` used to require equality with a full digest; it now compares `hexdigest()[:len(expect)]`,
  which leaves the RoFormer behaviour (64 digits) unchanged (K5).
- **Only missing files are fetched; files already present are not touched** - this is filling a gap, not re-downloading.
  One job at a time (`_DEMUCS_MODEL_LOCK`): two threads writing the same `.part` overwrite each other's bytes and
  neither ends up complete. Both "no package" and "nothing missing" answer before any thread starts (K7).
- **It is deliberately not in the one-click batch**: several hundred MB should not be spendable by an accidental
  double click. The row has its own "Fetch missing models" button and progress goes to the run log.
- Side cleanup: `_fetch_weight` used to prepend GitHub mirror prefixes to *any* URL. The Demucs files live on
  Meta's own host, so those candidates were a list of guaranteed 404s - prefixes are now applied to GitHub URLs only.
- Readings taken from disk after the suite ran: `htdemucs_6s` 1/1 file present, 54,996,327 B; `htdemucs` 0/1,
  `htdemucs_ft` 0/4, `mdx_extra` 0/4 - nine files missing in total.
- Tests: K1-K13 in `tests/separator_test.py`. F1 ("the old `/api/ai/demucs` endpoint is gone") had to be tightened to
  match the whole quoted path - the new `/api/ai/demucs_models` is a different thing and substring matching hit it.
- Files touched: `voice_tools.py` (`demucs_ckpt_dir` / `demucs_remote_dir` / `demucs_model_index` /
  `demucs_models_status` / `download_demucs_models`, the prefix comparison in `_finish_weight`, the mirror guard in
  `_fetch_weight`), `server.py` (`voice_status` returns `demucs_model_files`; new `POST /api/ai/demucs_models`),
  `static/index.html` (the status line and button, `sepDemucsState` / `fetchDemucsModels`, the endpoint's action name),
  `static/i18n.js` (+11 keys per language), `tests/separator_test.py`.

### Audio analysis gained beats and song structure - two neural sources, and the old reading is not replaced silently

The follow-up question was "why isn't StemDeck an engine or a component, with model and engine update detection".
What the comparison found: **StemDeck itself stays out** (JS/Electron plus its own 305 MB Python runtime, demucs
underneath, not on PyPI - adding it would do the same job twice), **but it has the two capabilities we lack**:
beats (beat-this) and structure (all-in-one). Per the approved 口径 only the capabilities were taken: install into
`tools/separator/venv` to reuse the same torch, fold the output into the existing audio-analysis JSON and run log,
put both packages in the engine table so upstream versions and updates are detected, and hang both model sets on the
"present / fill it in" machinery from the previous section - not in the one-click batch.

- **Why this was worth taking: librosa's tempo is not imprecise, it is wrong by a factor.** A synthetic 180 BPM clip
  came back as 89.1; the real song 說好不哭 is 76 and got 152, Brave Shine is 85.7 and got 112.3. The two neural
  sources agree within 1% on the same files (85.7 / 86.0). So **the old reading is not replaced quietly**:
  `tempo_bpm` and `bpm` each keep their own number, and only when they differ by more than 25% does the log line gain
  `旧读数 112.3（相差 0.76 倍）` (L9 pins both the threshold and that wording).
- **The neural pass reads the whole track, not the same 180 seconds.** Structure only means anything over a full
  song, while the librosa cell stays capped at `max_duration=180` - the comment says so instead of pretending the two
  windows are one 口径 (L10).
- **Whichever layer is missing is the layer that gets named, and no subprocess starts**: packages, models and venv
  each have their own `reason` (L7), and the eight result keys are present on the failure paths too, so neither the
  UI nor the sidecar JSON has to ask "is this key there?" (L8).
- **One broken package costs one item, not both**: the two `try` blocks in `separator_runner.py --analyze` keep their
  own errors, `audio_analyze.py` merges them into `analysis_error`, and when structure was attempted but produced
  nothing the log adds "段落结构没算出来" (L6, L21). Reading only `ok` used to swallow a structure failure whenever
  beats succeeded.
- **Both packages join the upstream check and the one-click batch; the models do not.** Packages have versions to
  report, models do not - a missing model must be named on screen, which is "fill it in", not "an update exists".
  The table shows one row, "音频分析依赖", rather than two near-identical notifications (L12). Installing and fetching
  share the separator environment's lock: two pips writing one venv overwrite each other's fresh files (L13).
- **The beat weights are only reachable through a third-party mirror.** The author's `.ckpt` sits on
  `cloud.cp.jku.at`, which measured as a site-wide 503 this round. Using a mirror means saying it out loud - the row
  gains "拍点模型取自第三方镜像（作者站当前不可达），已按钉死的 sha256 核对", the author host is tried first, and the
  fallback must match a pinned full sha256 (L3, L16). The hyperparameters are pinned too: the mirror file is a bare
  `state_dict` and does not fit the author's `load_model()`.

Three traps only showed up while making the install actually work:

1. **Pinning everything is not the same as pinning a satisfiable set.** `omegaconf==2.4.0` contradicts
   `hydra-core==1.3.7` (which needs `<2.4`) and pip refused outright; the probe environment had worked only because
   those two went in with `--no-deps`. Exactly one combination works - `omegaconf 2.3.1` itself requires
   `antlr4-python3-runtime==4.9.*`, which is precisely the measured "the default antlr breaks omegaconf's grammar"
   constraint (L17 pins that trio).
2. **What reaches all-in-one has to be a wav.** The venv's torchaudio is 2.11, whose bundled decoders were removed in
   favour of torchcodec, so an mp3 gives `TorchCodec is required`; the library's own wav / flac path uses soundfile.
   The runner now **decodes once and shares it**, hands the library a temporary wav, and redirects that library's
   `demix_dir` / `spec_dir` into the temp folder - by default they land in the current directory, which would scatter
   by-products into the program folder (L18-L20).
3. **"Is the model there?" cannot be answered by us reading the cache layout.** The library's runtime call is
   `hf_hub_download(repo_id, filename)` with no revision, so it only resolves the default branch: the eight folds we
   had filed under a pinned commit were invisible to it (measured - files present, still `LocalEntryNotFound`). The
   check now **asks the venv's own huggingface_hub** (`local_files_only=True`) and counts a file only if the library
   resolves it *and* its sha256 matches what we pinned; the pin itself moved from a commit number to eight file
   digests (L4, L22-L23). Filling in follows the same rule: `snapshot_download` only reports that it tried, so a
   read-back mismatch is reported as missing rather than run with unverified weights.

- Readings (own sandbox, never 8765; a real 252.3 s song): GPU 55.6 s for `bpm 85.7 / 339 beats / 88 downbeats /
  14 segments` with an empty `analysis_error`; the CPU arm took 93.7 s on a 180 s clip and produced the same 85.7.
  The install is 9 pinned items (torchaudio and matplotlib included); the weights are 77 MB plus 8 × 1,400,571 B.
  The row renders in both UI languages, and switching language takes effect without a restart.
- **The live run also exposed an unrelated real defect**: the main environment had `numpy 2.5.4` with `numba 0.65.0`
  (metadata says `numpy<2.5`), so `import numba` raised and audio analysis plus voiceprint separation were simply
  broken - and 8765 runs on the same interpreter. Per the user's choice this was fixed forward with
  `numba==0.68.0` + `llvmlite==0.50.0` (allows `<2.6`), after which all six readings came back green. numba is not in
  the components table, so the one-click batch cannot keep it in step with numpy; recorded as the next item.
- Tests: L1-L23 in `tests/separator_test.py` (pins, mirror digest and hyperparameters, when `--analyze` dispatches,
  the `@@@JSON` and the separated fault tolerance, the three early exits, the eight keys, the old-reading sentence,
  the two windows, where the components row reads from, the detection/update trade-off, the lock, both dictionary
  halves, the UI wiring, saying the mirror out loud, the version trio, the wav, the temp directory, one decode,
  errors not swallowed, and read-back-instead-of-trust).
- Files touched: `voice_tools.py` (`SEP_ANALYSIS_PINS` / `analysis_pkg_versions` / `install_analysis_pkgs` /
  `analysis_model_states` / `download_analysis_models` / `analysis_status` / `analyze_beats_structure` /
  `setup_analysis`, one venv probe answering both versions and model presence), `separator_runner.py` (`--analyze`:
  one decode, beats, structure), `audio_analyze.py` (the eight keys, the old-reading sentence, segment labels),
  `server.py` (`POST /api/ai/analysis_setup`, `sep_analysis` in `/api/components`, one more row in the upstream check
  and the batch), `static/index.html` (the row, the button, four computeds), `static/i18n.js` (+12 keys per language),
  `tests/separator_test.py`, `tests/i18n_test.py`.

### Interface language, second batch: all 17 page bodies

The scope moved from "frontend only, log lines untouched" to **frontend in full plus the runtime log following the
UI language**, one commit per page. The log was not rewritten: every entry keeps its Chinese `message` (it is a
written record, an archived file, the target of thousands of assertions) and carries an optional `k` / `kv` pair; an
English UI renders a sentence from the key at display time, anything without a key falls back to the message.
**The backend never reads `ui_language`** — same file, two languages, bytes unchanged.

- The dictionary went from 52 keys (chrome) to **2481 per language**, key sets identical; `tr(` appears 2640 times in
  `static/index.html`, and no template block retains Chinese outside comments. Per-namespace: `settings` 823,
  `music` 234, `files` 169, `subs` 168, `bt` 151, `tg` 118, `home` 115, `live` 73, `sniff` 59, `queue` 59, `voice` 58,
  `info` 56, `search` 36, `library` 36, `favs` 33, `logs` 19, `history` 15, plus shared `common` 48 / `nav` 17 /
  `page` 17 / `header` 16.
- Data tables had to store **keys, not literals** (`tgTypeOptions` → `labelKey`, `QA_TAGS`, `SUB_KIND_META` →
  `labelKey`/`hintKey`, the three music option tables, `dateShortcuts` converted to a computed) — language switches at
  runtime, so anything baked in at module init cannot follow. `formatCount` got two breakpoint sets: Chinese keeps its
  original literals (16.0亿 / 1.2万), English switches to K/M/B.
- `tests/i18n_test.py` grew 75 → **491 assertions**, plus a new `tests/pagemount_test.py` with 40. The per-page gates
  that matter: **I7** a handler called from a template must be in `setup`'s return list (in-DOM templates don't lose a
  row, they lose the whole page — `taskHeadline` was missed and only showed up as 0 language buttons);
  **I8 / `MAIDIAN_EXPECT`** pins the number of `logAction` / `uiName` / `logSort` lines per page so a finished page
  cannot quietly swallow the `ACTION_NAMES` batch; **I10** no second copy of a label; **I11** a separator belongs
  either to the value or to the template, never both (`· 最近一次` printed `· ·`); **I12** the live page's task filter
  matches the Chinese word in a backend title, so translating that row empties the page.
- Two product bugs came out of the same pass: `ElMessageBox` is imperative and never goes through
  `el-config-provider`, so confirmation dialogs kept Chinese buttons after the body switched (wrapped
  confirm/prompt/alert — a caller's literal words are never overridden); and joining two `tr()` values on one line
  drops the space English needs (`thelatest`, `butqueues`, `byte for bytedownloads`) — now gated by C21/C22.
- Re-pinning nine suites for moved literals **exposed three false greens**: `cookiefirst` I8 matched a clipboard hint
  instead of the Cookie switch's "off by default" sentence that #22 said must be on screen (the sentence was restored
  to `settings.publicHintP1`); `cleanup` M5 and `outbox` J14 were matching strings in the `ACTION_NAMES` table, never
  the UI; `runwindow` G11 didn't fail red, it raised `ValueError` and stopped the suite mid-run. Batch went from
  54 OK / 7 FAIL to **61 exit codes of 0**.
- Verification was a live A/B per page: self-spawned sandbox instance (own `MEDIADOWNLOADER_STATE_DIR`, a port from
  `bind(0)`, neutral `download_dir`), HEAD checked out into its own worktree as the control arm, both fed the same
  fake data and the same click sequence, comparing rendered text nodes. Chinese arm row-for-row identical; English
  arm 0 rows of frontend Chinese, 0 bare keys, 0 page errors, `library_cache.json` byte-restored. On the settings
  page: 769 rows before, 768 after, the only real difference being that restored sentence.

### Mount only the current page (the "everything is slow" fix)

Seventeen page blocks were `v-show`, so they all stayed in the DOM; the library was scanned at boot and every row
carried an `el-select` (with its teleported option list). With 60 finished files, one keystroke on the download page
cost **24.5 ms** (6653 nodes, 91 `el-select`s) — past the 16.7 ms frame. Switching to `v-if` page blocks, lazy
library cache reads and native `select`s in rows brought the same probe to **2.0 ms** (564 nodes). The cost is
honest: entering the Files or Settings page now remounts, measured 0.52 s / 0.33 s (was 0.10 / 0.09 because they were
already mounted). `tests/pagemount_test.py` pins it; the audio player is paused before a block is destroyed.

### Cover embedding: a real switch, then a real removal

The checkbox used to be ignored in three places (it only reached the config when "save strategy" was pressed; the
queue fallback hard-coded `embed_thumb=True`; the write happened through an ffmpeg re-mux that never reported
success). All four music download paths now send the current value every time, writing goes through mutagen tags
only, and each track is read back (`audio_embedded_cover`) to say "embedded" or "not embedded (why)". Two read/write
bugs surfaced: m4a/mp4 covers live in `covr` and the readback never looked there; a webp pasted with a JPEG magic
header read back as bytes and was reported as embedded while no player could decode it.

Then the honest half of "not embedded" turned out to be a lie: musicdl's `auto_supplement_song` default writes the
cover before tagging, so an unchecked box still produced files with art. `strip_embedded_cover()`
(`music_search.py:4937`) now removes it — `ID3.delall("APIC")` / `clear_pictures()` / `tags["covr"]` — which is a tag
operation, not a re-encode (mp3 needs `padding=lambda _t: 256`; the bare integer raises `TypeError`). Live reading,
same file both arms: unchecked → 0 picture blocks, audio frames **153,430,544 bytes in both arms**, the sibling
`.jpg` and the text tags intact; checked → 1 block of 157,712 bytes. One measured asymmetry kept rather than
smoothed over: **flac does not shrink** — mutagen replaces the picture with all-zero PADDING — while mp3's tag area
does contract. Both shapes are pinned by self-tests.

### Collections land in one folder; a batch that changed container is matched back to its file

`playlist_subdir` (default `False`) adds one directory level named after the collection, **below** wherever that run
would have written (download directory, auto-classify target, or a manually picked folder) — never instead of it. The
name comes from the container title, or from `playlist_folder` handed over by the parse page when the episodes are
queued as N independent tasks; if neither is available the batch stays flat and the log says so instead of inventing a
folder name. Single downloads and live recording still land flat, and nothing already on disk is moved. The settings
note that used to suggest `%(uploader)s/%(title)s` in the filename template was false — `/` and `\` are replaced
before rendering. New: `tests/playlistdir_test.py`, 39 items.

With a remuxer attached (target container mp4/mkv/webm) or audio extraction on, yt-dlp writes back the **pre-remux**
`filepath`, so a whole playlist was judged missing episode by episode: "1 item in the list, 0 files written into the
download directory", then `.NA` in the title, then "downloaded but the file is unusable" — while the `.mkv` was on
disk. Single-item downloads already had a find-it-by-base-name loop; the playlist branch didn't. Now
`resolve_written_file(pth, prefer)` (`server.py:9546`) keeps the reported name when it exists and otherwise looks for
the same base name under another extension, **the container this run asked for first** (an older `.mp4` can sit beside
the new `.mkv`); when nothing matches, the original name is returned and the failure is stated plainly.
`REMUX_FALLBACK_EXTS` is defined once and shared. New: `tests/remuxcount_test.py`, 18 items, plus a three-arm live
run before/after (before: both batch arms printed both false messages; after: all three `finished`, false strings 0).
History rows already written keep their old wording — this fixed the shape, not the record.

### Startup no longer looks hung

A healthy start prints only the four banner lines (uvicorn's "running on" is INFO and `log_level="warning"` suppresses
it), so a server ready in 2.1 s looked identical to a hang; a busy port printed only `Errno 10048`. The port is now
trial-bound before anything starts: if something answers `/api/health` it is another instance of this app (use that
one, address given), otherwise another program owns it — either way one runtime-log line and exit code 1, so a `.bat`
window keeps the message. Only `EADDRINUSE`-class errors are interpreted; everything else is left to uvicorn. The
"ready" line is printed by a background thread that polls `/api/health` — deliberately not `/api/status`, which runs
`ffmpeg --version` and walks the Whisper directory. New: `tests/startup_test.py`, including three real instances each
with its own `STATE_DIR`.

### Voice separation: its own venv, two RoFormer families, three device modes

The engine lives in `tools/separator/venv`, separate from the app interpreter (the bundled torch is a `+cpu` build, so
a separation package installed inside it could never use the GPU); **neither the venv nor the weights are shipped**.
`ROFORMER_MODELS` lists four weights with per-file sha256 (`bs_1297` / `bs_1296` / `mel_1143` / `mel_inst_v2`, ids used
as dictionary keys so the backend never builds Chinese strings); `DEMUCS_MODELS` lists the three verified on this
machine; the other 84 names in the upstream `models.json` are a recognition catalogue with no reachable source, so they
are not offered. `SEP_ENGINE_PINS` freezes `audio-separator==0.47.0` + `demucs==4.1.0`; `_fetch_weight()` resumes and
verifies each digest, discarding a mismatch instead of calling it done. Forcing CPU means patching
`torch.cuda.is_available` to `False` **before** `import audio_separator` — the package has no device parameter, and on
this machine `CUDA_VISIBLE_DEVICES` neither hides the GPU (still `True`) nor is safe to set to `-1`/`void` (exit
3221225477). `POST /api/ai/vocal_separate` replaces `/api/ai/demucs`; `POST /api/ai/separator_setup` builds it;
`GET /api/ai/voice_status` reports **which layer is missing** — venv / runner / import / weights / no CUDA are five
different sentences with five different remedies, not one boolean. Five settings keys: `vocal_engine`, `roformer_model`,
`demucs_model`, `ai_device`, `vocal_native_fp16`. The live run caught a write-only class of defect: dropdowns bound to
`settings` that `loadConfig` never repopulated, so a stored `cuda` displayed "auto" while the engine really ran on the
GPU — display was the only liar. Five keys were fixed with #78 and the other six (`ai_polish`, `ai_summarize`,
`components_auto_check`, `edge_tts_voice`, `subtitle_first`, `translate_auto_fallback`) in the follow-up commit, which
also emptied the exemption list in `settingsave_test.py` I27 and turned I28 into "this list must stay empty".
New: `tests/separator_test.py`, 44 items. Measured: torch `2.14.1+cu130`, RTX 4060 Laptop, 4/4 weights,
`actual_device=cpu` and `actual_device=cuda` for the same source, outputs under `separated/` and
`demucs/htdemucs/<track>/`.

### Eight interface items from the reference mockup

- **Collapsible sidebar**: the width was already `var(--sidebar-w)`, so `.sidebar.is-collapsed` redeclares that one
  variable to 64 px — no second source of truth (gate P10 fails anyone who hard-codes 212/64). Group headers are
  replaced by divider lines (4 between 5 groups, none above the first), every item gains a `:title`, badges move to the
  corner. The state lives in `localStorage.md_nav_collapsed` — a read-only view preference, never in config. Measured
  212→64 px, main area 1228→1376 px, no horizontal overflow, keystroke cost 2.68 → 1.85 ms. The first badge test was
  a false test: it asserted the badge stayed inside the cell while the badge was empty, because the home page never
  calls `/api/tasks`. Later the toggle moved into the logo row as a 30×30 button (P36/P37).
- **`Ctrl+K` palette** — jump to a page or run one of five actions, deliberately **not** a content search (each list
  page already has its own filter; cross-page search would mean flattening five lists and then locating a row).
  Matching consumes the current-language page names, the other language's names, and an alias table that is never
  displayed. The panel hangs off `.layout`, outside `.main`: a `position: fixed` ancestor with `transform` or
  `backdrop-filter` becomes its containing block (gates P13–P16). 22 rows on open (17 pages + 5 actions).
- **Persistent top banner** for the three things that are true right now but only visible inside some page (component
  updates, unsent notifications, a domain throttled down), each with its inline remedy; dismissal is per-reason in
  `sessionStorage`. The automatic-update popup became a banner — a manual "check now" still gets a dialog, because a
  button someone pressed owes them a receipt. Sticky is not `top: 0`: `.content` has its own 22 px padding and scrolls,
  so the padding became `--content-pad-y` and the banner offsets by its negative. Two readings had to be taken twice —
  `gotoCard` needed per-frame re-alignment (data filling in pushed the target 1358 px away), and the "banner costs
  1.15 ms per keystroke" number was an artifact of an SSE stub reconnecting every 800 ms. Gates P17–P26.
- **Row context menu** that lists exactly the buttons that row really has (no second action list, so tracking,
  confirmations and toasts stay single-sourced), recognises three row shapes, and yields to the browser's native menu
  on inputs/selects/checkboxes/selections/rows with no actions. Danger-red follows the button's `el-button--danger`
  class, never the word "delete" — a Chinese literal test breaks the moment the dictionary switches. Gates P27–P34.
- **Inline labels centred against their controls**: 31 rows across 17 pages were ≥1.5 px low, all from one cause —
  `.hint { margin-top: 6px }` inside a flex container centres the margin box, not the content. Dropped for
  same-row hints (`:not(.hint--block)` keeps the multi-line hints intact).
- **File browser defaults to modification time**, same rule as the library: three places in one move (`:default-sort`,
  `fileSort`, `fileSortDir`), directories still pinned first; the backend `/api/files` ordering was left alone because
  sorting there would do the same job twice. Gate P35.

### The six framework assets moved to `static/vendor/`

The report was "the machine stayed on, and next morning the external browser is slow while the built-in one isn't".
Three arms on one page and one server, only the browser side changing: warm cache DOMContentLoaded **214 ms** (all six
CDN assets served from cache, 0 ms), cold profile **2282 ms**, and a "connects but never delivers" jsdelivr
**168,084 ms** — the six blocking tags wait 28 s each, serially, `window.Vue` never appears, 1332 bare braces stay on
screen and not one `/api` call is made. That is not slow rendering, it is a template that never mounted; the render
layer was ruled out with the same probe (582 nodes, 0 long tasks, p50 32 ms per keystroke). Vue 3.5.12, Element Plus
2.8.8 (css, `index.full.min.js`, both locales) and lucide 0.468.0 now sit in `static/vendor/` at their original
versions, 1.8 MB, order unchanged because EP's UMD needs `window.Vue` first; digests were fetched twice over two
network paths and compared, and the CSS turned out to reference only inline data URIs (no fonts to chase). After the
change, the stalled-CDN arm mounts in 0.5 s with 0 CDN requests. Gates **P38–P40** (no external root-level
script/link, the six files present with matching sha256, the tags point at the local paths), with the pre-change HTML
fed through as a negative control, plus `static/vendor` named in `pack_release.check_present` — a vendor directory
swallowed by the exclusion list leaves `static` non-empty, so the old gate would have shipped a package that is a white
screen. `.gitattributes` marks `static/vendor/** -text`: this machine runs `core.autocrlf=true`, which rewrites LF to
CRLF at checkout, so a digest-pinned gate passes in the working tree and fails for anyone cloning fresh; the suite was
re-run in a clean `git worktree` to prove it. Two collateral reds, both from suites grepping literals out of
`index.html`: C4 was anchored on a CDN path, and C8's template slice ended at `HTML.find("/vue@3")` — once that literal
disappeared `find` returned -1, the slice silently widened to the whole file and counted an extra occurrence from a
comment. Boundaries now anchor on the next `<script`, which depends on no filename. Left measured but untouched, for a
separate decision: `/api/status` costs 1.0–1.3 s per call (it runs `ffmpeg --version`, imports `yt_dlp`, walks the
Whisper directory), `/` is `no-store` so 817 KB of HTML is re-transmitted and re-parsed every visit, and an idle tab
issues 25 requests per 20 s of which 15 are the 2 s clipboard poll.

### Closing this round: pushing, restarting, and this documentation sync

37 commits (`3f9cafc..ea16c82`, a single fast-forward) are now on `origin/main`: the 17 translated pages of the second
language batch, the performance fix, cover embedding, the collection folder, the container-recovery bug, the startup
message, the eight reference-mockup items, separation and the vendor localization. The diff was read before pushing —
38 files, 12,259 added lines, no binaries, no state files (`config.json` / `history.json` / `app.log` / `cookies/` are
all absent), and the only credential-shaped string is the `http://user:pass@` placeholder inside
`tests/cookiecloud_test.py`. **The `v1.4.0` tag still sits at `7ac0ff6` and neither the portable package nor the
published release asset moved**, so the published build lags the repository by everything from `3f9cafc` onwards. This
commit is documentation only: `appVersion` stays `v1.4.0 · Element Plus` and no package was rebuilt (by convention the
docs are snapshotted at zip time). The instance in daily use was restarted onto `ea16c82` after confirming the queue
was empty; its served HTML is byte-identical to the repository copy (817,010 B, 0 jsdelivr hits).

What this commit changed: `docs/详细功能介绍.md`, `docs/detailed-features.en.md`, both READMEs and this digest now
describe #65 / #63 / #66, #78, #87, the eight interface items and the second language batch; the stale "the UI is
Chinese-only" statements are gone. **No self-test or live measurement was re-run for this commit** — every reading
above was recorded when its own round finished, and this file only carries it over.

### #52 — the `v1.4.0` tag and the published bytes: the decision is to leave the tag alone and write the difference down

Several entries above end with "the `v1.4.0` tag still points at `7ac0ff6`, package and release asset untouched". That
only said the tag trails; it never said **which tree the published archive was actually built from**, and it is not
`7ac0ff6`. This entry lines the two sides up to a comparable degree, then follows the agreed decision: **the tag stays
put** — no tag move, no rebuild, no asset swap, documentation only.

- **The archive corresponds to the `caeb4f6` tree**, and that is a fresh measurement, not carried over. Two application
  files were read out of `dist/MediaDownloader-1.4.0-portable.zip` itself (not out of the already-extracted
  `dist/MediaDownloader-1.4.0-portable/` directory), their CRLFs folded back to LF, and hashed with git's blob
  algorithm:
  - `static/index.html` → 773,906 B, `28b090bc4ac12e1a195c8cac938807871cbbcc57`, identical to
    `caeb4f6:static/index.html`;
  - `CHANGELOG.md` → 476,725 B, `15da28dc587b3c9b022321a2be5489fa05a590c5`, identical to `caeb4f6:CHANGELOG.md`.
  At the same paths `7ac0ff6` holds 773,890 B / `fd5f19626b3532447919016eaf45f56250577e16` and 466,999 B — neither of
  them the numbers above. **The newline folding is not optional**: the `index.html` entry in the archive is 787,201 B
  and contains 13,295 CR bytes, and 773,906 + 13,295 = 787,201 exactly — the build ran on this Windows box, where
  `core.autocrlf=true` had already rewritten LF to CRLF at checkout. This is the same hazard that cost #87 its
  sha256 pin, seen from the other side.
- **The two trees differ by exactly two commits** (`7ac0ff6..caeb4f6`): `c7226b1` replaces six PNGs under
  `docs/screenshots/` and nothing else; `caeb4f6` changes 4 lines of `static/index.html` (the music result table's
  artist and album columns move from `width` to `min-width` so the slack spreads out), one assertion in
  `tests/matchgate_test.py` (the G9 check was pinned to `:title` after it turned out to be a false green), one
  changelog section and `music-search.png`. **So the gap is not documentation-only**: checking out `v1.4.0` and
  rebuilding reproduces the table *before* that width change — four real style lines away from what people actually
  downloaded.
- **The decision and why** (recorded here so it is not reopened as a bug next time): the `v1.4.0` label is already
  published and already downloaded, so moving the tag or swapping the asset now would make one label stand for yet
  another set of bytes and make reconciliation harder, not easier. The tag stays at `7ac0ff6` and the fact that
  "package = `caeb4f6`" is written into the docs instead.
- **Which route gets you which artifact**: the source tree matching the published bytes is `git checkout caeb4f6`
  (`git archive` if you want it as a bundle); the file users actually downloaded is the
  `MediaDownloader-1.4.0-portable.zip` on the release, 229,823,103 B, verifiable in `dist/` with `sha256sum -c`
  against the sidecar of the same name (which currently reads `4ea6a8ec…`, and that line is what this round read).
  **The digest still does not go into this packaged file** — same convention as the "Release artifacts" sections
  above: no archive can carry its own checksum.
- This entry touches `CHANGELOG.md` and `CHANGELOG.en.md` only: `appVersion` unchanged, no rebuild, release untouched,
  tag unmoved, and no live run. The blob comparison above is the only new measurement in it.

### After v1.4.0 — separator engines join the upstream check; network card grouped; the tag moves and the package is rebuilt

Trigger: upstream `python-audio-separator` was at **v0.47.1** (released 13 hours earlier) while the dedicated venv still
had **0.47.0**, and the components row offered only "Set up / fill in" — no Update button and no banner. The cause was
not a missing button: the engines live in `tools/separator/venv`, and the existing upstream scan only walked the main
environment's `pkg_update.PIP_PACKAGES`.

- **Backend**: `latest_versions_cached()` now appends `voice_tools.SEP_ENGINE_PKGS`; `separator_engine_versions()`
  reads the venv's `importlib.metadata` only (no torch import, 120-second cache), and
  `_sep_engine_rows / _sep_engine_state / _sep_engine_available` compare each package against upstream.
  `/api/components` returns a `sep_engine` block; the background check appends `sep:engines` to `available`; one entry
  covers both packages because they are upgraded as one group. `_comp_update_one`, the update-all allow-list and
  `api_separator_setup` all accept the key; `setup_separator()` forwards `step == "engines"` before taking
  `_setup_lock`, so the update path does not deadlock against itself.
- **Update path**: `update_separator_engines()` runs `pip install -U ... audio-separator demucs` inside that lock,
  then forces a fresh version read and a `separation_probe`; success is reported from the read-back, not from pip's
  exit code. **`SEP_ENGINE_PINS` is unchanged** (new environments still get 0.47.0 / 4.1.0) — only an explicit Update
  moves past it. Logs use `srv.ai.update_ready` / `srv.ai.update_failed`, and the endpoint no longer answers an update
  request with "setup in progress".
- **Frontend**: the row reads `RoFormer · audio-separator 0.47.0 · latest 0.47.1 (updatable)` / `Demucs · demucs
  4.1.0` and shows an **Update** button when one exists. `updateSeparatorEngines()` saves the mirror setting first,
  calls the `engines` step, waits on the server's `setup_running` flag (15-minute cap), then re-reads versions and the
  component check. `compTargets` includes `sep:engines`, so the banner count and the sidebar dot follow.
- **Readings** (sandbox instance with its own state directory and a `bind(0)` port, never 8765): the real upstream
  query returned `audio-separator 0.47.1` (Tsinghua mirror) and `demucs 4.1.0`; `update-check` reported exactly one
  `sep:engines` entry (0.47.0 → 0.47.1); `sep_engine.items` held 0.47.0 / 4.1.0 with only the former updatable; the
  row rendered the two lines above, the banner read "1 component has a new version: 人声分离引擎", console errors 0.
  **The working venv was not actually upgraded** — the update path is covered by code and stub assertions (H1–H10),
  not by a real `pip -U` against the 0.47.0 environment in use; the button in the UI is what performs it.
- **Network card**: the 18 fields are grouped into five sections (proxy & concurrency / speed limits / queues /
  downloader / mirrors) with full-width `.net-sec` dashed headings; long fields span two columns, and the queue item
  is full-width with per-queue rows on `auto-fill minmax(280px, 1fr)`. Measured at 1600 / 1200 / 860: 4 / 2 / 1
  columns, `hOver=0`, `docOver=0`. The settings page still scrolls (1639 / 842); this round only tidied the network
  card.
- **Tests**: `tests/separator_test.py` 57 (new H1–H10), `i18n_test` 509, `components_test`, `runwindow_test`,
  `pagemount_test` 40 and `settingsave_test` 113 all green; full sweep **65/65 rc=0** (185.8 s).
- **Tag and package**: on the explicit 2026-10-20 instruction ("修改后再推送动标签打包"), the lightweight `v1.4.0` tag
  moves from `7ac0ff6` to this commit and is force-pushed, and `pack_release.py --skip-runtime` rebuilds the portable
  package. This **supersedes the "#52 — leave the tag alone" decision** above: that decision assumed nobody had asked
  for a tag move, and now someone has. Replacing the public release asset still waits for a separate approval.

### Same round, follow-up: queue names, one upstream button, a permanent Update, clean shutdown

This landed after the package in the section above; `appVersion` is still `v1.4.0`, and the tag, package and release asset were not touched.

- **Queue names follow the UI language**: the run-window rows used to print the backend identifiers (`default / night / subscribe / sniff / music`). `queueLabel()` now maps the five built-ins through `QUEUE_NAME_KEYS` (默认 / 夜间 / 订阅 / 嗅探 / 音乐, or Default / Night / Subscribe / Sniff / Music in English); a user-created queue is not in the table and keeps its exact name, with the raw identifier still in `title`. Sandbox EN run: all five built-ins in English, custom name unchanged, 0 console errors.
- **One upstream entry on the components page**: "Check now" already forces a fresh upstream query; the bottom "Query latest upstream versions" button only issued the cached `GET /api/components?latest=1` again. The duplicate is removed, and the Latest column is now refreshed by `loadComponents('1')` when the check finishes (reads the server cache, no second network pass); `latestBusy` is gone. In the sandbox, one check filled the Latest column on 16 rows and the footer kept three buttons (update all / re-check / save mirror).
- **The separator Update button is permanent**: it used to be gated by `sepUpdatable`, so as soon as the engines reached 0.47.1 / 4.1.0 (both current) the button disappeared and there was no way to force a reinstall. It is now always rendered, like every other component row; "latest x.y.z (updatable)" still appears when a newer version exists. Sandbox reading: both `sep_engine` items active (0.47.1 / 4.1.0) with `updatable=false`, row buttons `["更新", "获取 / 补齐"]`, 0 console errors.
- **No more CancelledError on shutdown**: the pasted `Cancel 1 running task(s), timeout graceful shutdown exceeded` / `Exception in ASGI application ... CancelledError` is produced when a browser still holds the `/api/events` SSE stream and Ctrl+C is pressed: after `timeout_graceful_shutdown=5`, uvicorn cancels the remaining stream task. It is **shutdown noise, not a runtime crash**, and the BT daemon cleanup in `finally` still runs. `main()` now owns the `uvicorn.Server`, and the SSE generator checks `should_exit` on every tick and closes the stream itself. A/B with one SSE client connected: before 5.14 s plus the full Cancel/CancelledError trace, after 0.13 s and zero stderr lines. An end-to-end probe (real `python server.py`, sandbox port, SSE connected, then CTRL_BREAK) closed in 0.17 s with no Cancel line; the Ctrl+C exit path is unchanged.
- **Tests**: `separator_test` 57 (H8 now pins that the button is not conditionally rendered), `platform_test` 45 (new E1b pins the `should_exit` check), `startup_test` (B2/B4 re-anchored to `_UVICORN_SERVER.run()`), `sse_test`, `i18n_test` 509, `pagemount_test` 40, `settingsave_test` 113 and `runwindow_test` all green; full sweep **65/65 rc=0** (189.4 s).

### Same round, follow-up: the whole components page in English, inline Updates on one style

Still `appVersion = v1.4.0`; the tag, package and release asset were not touched. Two screenshots showed parts of the components page still in Chinese and row buttons that did not share one style.

- **Five Chinese sources on one page, not one dictionary gap**: row names came from the backend `cn` field (18 entries), hover text from `label`, the POT row's paragraph from `_pot_component_note()`, and states from `active`'s `未安装 / 未找到`; the update-all banner list and progress also printed backend `cn / label`. Editing the dictionary alone would not have changed any of them.
- **Names and descriptions use literal key maps**: `COMP_NAME_KEYS` (18 packages or tools plus `sep:engines`) and `COMP_DESC_KEYS` (18 entries) in `static/index.html`, pointing at `components.name.*` / `components.desc.*`; `compName()` / `compDesc()` fall back to the backend string for anything not in a map. Keys are written out in full rather than concatenated, because `i18n_test` B2 only permits the `nav.` / `navGroup.` dynamic prefixes, and the literal values also keep every new key counted as used by B10. The Chinese values are identical to the backend's `cn / label`, so the Chinese UI did not change.
- **States get their own keys**: `compActive()` maps `未安装` / `未找到` to `settings.notInstalled` / `settings.compNotFound`; version strings pass through.
- **The POT paragraph stays a backend decision**: `_pot_component_note_state()` returns a language-neutral `note_state` (`install / gate_off / no_server / ready`) plus `note_kv` (`dir / url / detail`); `COMP_NOTE_KEYS` + `compNote()` choose the localized sentence from `settings.compPotNote*`. The Chinese `note` remains for logs and older callers; the template no longer prints it.
- **All three update-all surfaces follow**: the banner list, the current item in progress and the summary call `compName()`. The backend now also reports `current_key` (set to `keys[0]` on start, rewritten per item, cleared in `finally`), so an English progress line only falls back to the Chinese `current` when the key is unknown.
- **One primary button per page**: the separator row was the only row using `type="primary" plain`; it is now the same default grey `el-button--small` as the other 18, leaving "Update all" as the single CTA.
- **Tests**: `components_test` gains C12 (every row has a name key), C13 (hover text coverage) and C14 (template uses `compName / compNote / compActive`), 109 green; `potcomponent_test` gains B8/B9 for the four `note_state` values and the `no_server` kv, and E4 now pins the localized template, 30 with 0 failures; `separator_test` H8 pins the absence of `type="primary plain"` on the row button, 57 with 0 failures. `i18n_test` 509, `pagemount_test` 40 and `indexsnap_test` green; full sweep **65/65 rc=0** (190.3 s).
- **Sandbox readings** (own `STATE_DIR` and a `bind(0)` port, never 8765): in English all 19 rows yield `CJK_ROWS []`, `CJK_TITLES []` and `CARD_CJK []`; the 18 inline Update buttons compute to one style (`el-button el-button--small`, white fill, `rgb(220,223,230)` border, 66×24), and "Update all" is the only `el-button--primary`; the card is 884 px with `SCROLL_H 882`, no scrollbar; 0 console errors. Screenshot: `tmp/ui_comp_i18n_en.png`.

---

### Same round, follow-up: the appearance bar on one line, theme dots back in the chips

Still `appVersion = v1.4.0`; the tag, package and release asset were not touched. The first request was one horizontal row under the Appearance title; a follow-up screenshot showed that the five theme chips had lost their colour dots.

- **Layout**: the `Appearance` title stays outside the card, and a full-width bar (`.appearance-wrap` across the whole `.settings-grid`) holds `Accent colour` + five chips and the `Dark mode` switch on one row, with the save/restore-defaults card spanning the row below. In the first attempt the bar sat in a third-width column: five equal columns left each chip 40.7 / 27.3 px at 1600 / 1400, and the 12 px `.theme-dot--inline` was flexed down to 0 — the capture showed bare text.
- **Dots**: `theme-grid` is content-sized instead of five equal columns (a chip is 79 px: 12 px dot + 6 px gap + three characters), and `.theme-dot--inline` gained `flex: 0 0 auto` so no container can crush it. Computed dot colours are `#1d55ee / #c2540a / #c92f6f / #2f7d4f / #a85c3c`.
- **One English spacing fix**: `settings.savePendHead` ended with a colon and no space, so a dark-mode probe rendered `1 setting(s) waiting to be saveddark_mode`; a trailing space was added.
- **Sandbox readings** (own `STATE_DIR`, `bind(0)` port, never 8765): all chips 79 px wide at 2000 / 1600 / 1200, dots 12×12, `gridRows = 1`, `docScrollW == docClientW`, 0 console errors; in English at 1600 the five chips measure 65–155 px with 12 px dots, and English plus dark mode is also clean. Screenshots: `tmp/ui_appearance_dots_1600.png`, `tmp/ui_appearance_en_dark_1600.png`.
- **Tests**: full sweep **65/65 rc=0** (190.9 s).

### Release artifacts

- **Artifact**: `dist\MediaDownloader-1.5.0-portable.zip`, **230,635,022 B (220.0 MB)**, sha256
  `6ba9ae84805c92aa5e625357201cdca3e31706f5ddff96f6d5102afa1d60fe00`, 10,906 entries, plus the
  `…zip.sha256` sidecar (verifiable with `sha256sum -c` from inside `dist/`). Staged directory 567.5 MB:
  runtime 322.4, tools 234.5, static 3.0, chromaprint 4.0, docs 1.4, cookies 184 B (the placeholder note only).
- **Packaging self-checks**: manifest carries 18 dependencies + 3 tools; the "must-be-in-the-package" check passes
  (13 items under `static`); 21 `__pycache__` directories removed; all 15 top-level modules import from inside the
  package; the in-package pip install → import probe passes (so in-app dependency updates work); the packaged service
  answers a smoke call with all three component version tiers present and 12 manifest hits. The manifest records
  `app = 1.5.0`, `python = 3.12.2`, `built = 2026-10-22 13:23`.
- **Package versus source**: **all 42 application files inside the package are byte-identical to the working tree**
  (compared with CRLF folded); the four entries that exist only in the package are generated by the packager itself
  (`components_bundled.json`, the cookies placeholder, `使用说明.txt`, `启动.bat`).
- **The runtime was reused**: `pack_release.py` and `requirements.txt` are untouched across these 32 commits
  (checkable with `git log`), so `--skip-runtime` re-ran only the copy step and those four self-checks instead of
  reinstalling the embedded runtime.
- **Private-state scan**: zero hits for `config.json` / `cookies.txt` / `history.json` / `library_cache.json` /
  `music_favorites.json` / `catcatch_rules.json` / `app.log` / `pack_release.py`; zero hits for the forbidden
  directories (`local_index` / `Downloads` / `Whisper` / `tg_session` / `browser_sniff_profile`); no `.pyc` left.
- **Tag**: the lightweight `v1.5.0` tag points at `fc2a9b4` - the version-and-overview commit, i.e. the bytes this
  package was built from. **The size and digest in this section were written back after the zip existed**, so the
  `CHANGELOG.md` inside the archive does not contain this section: that is the "release notes never quote their own
  digest" rule, not an omission. The packaged `CHANGELOG.md` is CRLF, because Windows Notepad is its reader.
- **The previous release is untouched**: `v1.4.0` still points at `d922732`, and its asset remains the 230,529,549 B
  `5f570ce7…88c57a` zip.

---

## Earlier releases (summary)

The full entries are in [CHANGELOG.md](CHANGELOG.md).

| Version | Date | One line |
| --- | --- | --- |
| v1.3.2 | 2026-10-13 | Gap analysis against a published platform list: site recognition table completed, finished-file resolution read back with ffprobe and compared against the selected tier. A suspected TikTok misattribution turned out to be my misreading — no product change, one assertion added to pin the reading. |
| v1.3.0 | 2026-10-13 | Six independent lines at once; magnet/torrent became a full page of its own (file selection, seeding, trackers, auto-sort, split up/down limits) modelled on qBittorrent Enhanced Edition, and subtitles grew a per-line review bench. |
| v1.2.9 | 2026-10-09 | The components table learned to speak only when there is something to say; a 12 px adjacency rule from Element Plus was the real cause of a button row that looked crooked. |
| v1.2.8 | 2026-09-24 | Music-led release: "is this the same song" became one scoring gate shared by three places that had each carried their own string comparison. |
| v1.2.7 | 2026-09-22 | Fetch-everything, sort, and keep a trace: 50 per page across long lists, truncated favourites genuinely paged, aggregate search sortable, runtime log archived daily with 7 days retained. |
| v1.2.6 | 2026-09-21 | No new engines: 16 pages unified into one product, and every interface operation given a trace in the runtime log. |
| earlier | — | Iterations before v1.2.6 (subtitle embedding, download integrity checks, human-readable failure reasons, per-site concurrency, PO Token gating, subscription rules, Telegram scraper and MTProto, voice tools and voiceprint separation, the portable-package script) were not kept version-by-version; for what the app does, read `README.en.md`. |
