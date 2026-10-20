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
- Interface language is rolled out in batches. In the working tree — not yet in the published archive — the first
  batch covered the chrome (brand, sidebar group names and items, page titles, header counters and tooltips, Element
  Plus's own strings); **the second batch covered every page body, all 17 of them** (see *After v1.4.0* below). Still
  Chinese by design: backend error text (`friendlyError`'s 22 branches, its own batch), runtime log lines written by
  the backend, and the `ACTION_NAMES` action-name table — all of them written records and targets of the assertions
  above.

---

## After v1.4.0 — 37 commits in the repository, none of them in the published package

Everything below landed after the archive was compressed. It is pushed (`3f9cafc..ea16c82` on `main`, one
fast-forward, screened first: 38 files, no binaries, no state files — the only credential-shaped string in the range
is the `http://user:pass@` placeholder inside `tests/cookiecloud_test.py`). **The `v1.4.0` tag still points at
`7ac0ff6` and no package was rebuilt**, so the published asset trails all of this. The readings quoted here are the
ones recorded in each round's own commit — this entry consolidates them, it does not re-measure them.

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
