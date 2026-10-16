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

## v1.4.0 · 2026-10-15 — current release

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
- Interface language is being rolled out in batches. In the working tree — not yet in the published archive — only
  the chrome follows the language setting so far: brand, sidebar group names and items, page titles, the header
  counters and tooltips, and Element Plus's own strings. Page bodies, backend error text, runtime log lines and
  subscription rule summaries are still Chinese, because the latter three are written records and the target of the
  assertions above.

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
