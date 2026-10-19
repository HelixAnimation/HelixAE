# HelixAE Improvement Plan

Status tracking for the reliability and data-correctness improvement program derived from the
deep code review. Each phase moves through: `pending` → `implemented` → `locally verified` →
`Windows verified`.

| Phase | Scope | Status |
|---|---|---|
| 0 | Runtime baseline | Completed (read-only subset) |
| 1 | Composition cleanup correctness | Implemented, deployed; Windows verification pending |
| 2 | Launcher, bridge framing, startup dispatch | Windows verified (panel + menus confirmed working) |
| 3 | Trustworthy AE data and operation results | Implemented, locally verified, deployed; Windows verification pending |
| 4 | Version discovery, replacement, imports | Implemented, locally verified, deployed; Windows verification pending |
| 5 | Caches, metadata, bypass persistence | Implemented, locally verified, deployed; Windows verification pending |
| 6 | Tracker responsiveness and lifecycle | Background scene preparation locally verified and deployed; Windows verification/timings pending |
| 7 | Image resize recoverability | Deployed; resize cancellation Windows confirmed; OIIO fixture verification pending |
| 8 | Installation hardening, regression pass | Deployed; Windows integration update confirmed working; failure-path fixtures locally verified |

Findings below were established at source level. Items marked *needs runtime* must be confirmed
on the Windows workstation (Prism + After Effects + installed CEP extension) before or during
the phase that changes them.

## 1. Findings that drive the plan

| Priority | Finding | Evidence and consequence |
|---|---|---|
| **Critical** | Cleanup can classify used footage as unused | `Scripts/footage_tracker/comp_manager.py` parsed used items only if the response contained `;;`. A composition using exactly one footage item produced no separator, so its used-item set became empty while still passing the caller's truthiness guard. Used footage could then appear in the removal list. |
| **High** | Version replacement can choose or construct the wrong file | `ae_operations.py` generated `_vv0003_` when passed `v0003` as the new version, and the filename base regex reduced unrelated filenames to their first character (reproduced locally: two distinct `S...` names both matched `S`). |
| **High** | Shot switching can search unrelated projects or substitute another AOV | `shot_switcher.py` includes hard-coded fallback project paths and falls back to a different AOV when the requested one is absent. |
| **High** | Footage parsing alters names and paths | `data_parser.py` converted response bytes with `str()` and stripped apostrophes; Unicode names became escaped byte representations and delimiter-containing names broke the record format. |
| **High** | Launcher and transport are unreliable | `Integration/helixae/js/main.js` references `child` outside its declaration scope; the TCP server evaluates each incoming chunk as a complete script; `HelixAE_MenuTools.py` accepts commands before initialization is safely ready. |
| **High** | Save/open/export can report success without confirmed success | `helixae_core.py` save accepted empty responses; facade `openScene()` ignored the response; export wrote metadata and announced a queued render even after a failed AE operation. |
| **High** | Cache repairs have hidden dependencies | `version_cache_manager.py` uses `re` without importing it and calls `saveCache()` while already holding its non-reentrant lock. Fixing only the import would expose stale-cache/key problems in `hierarchy_builder.py`. |
| **High** | Version-cache XMP construction is malformed | `hierarchy_builder.py` builds an incomplete `</rdf:li` closing tag and inserts cache JSON without XML escaping. |
| **Medium** | Shared import cache can lose valid data | `import_shots.py` uses a fixed `.tmp` filename, deletes the old cache before renaming, and can persist an empty/partial hierarchy after failed NAS scans. |
| **Medium** | Tracker/Kitsu refresh blocks the UI and can retain wrong context | Tracker data loads before the window is shown; Kitsu performs per-shot network calls; cache validity is time-based rather than project-based; short shot-name aliases can collide across sequences. |
| **Medium** | Resize writes directly over source media | `image_resizer.py` resizes in place and restores from backup only on failure; restore failures are only printed; the Cancel button does not stop the loop. |
| **Medium** | Integration replacement removes the working installation too early | `HelixAE_Integration.addIntegration()` deletes the existing panel before validating/staging its replacement. |

## 2. Execution rules

- Working root: `/mnt/storage/OpenCodeProjects/CG/HelixAE`
- Production checkout: `ssh nassk` → `/volume1/Renders/Programs/PrismPlugins/HelixAE`.
- Verify locally, then commit/push and pull into the NAS checkout only when explicitly
  authorized. `dev_sync.sh` is a legacy direct-copy helper, not the production workflow.
- Sign `Integration/helixae.zip` with `bash release_panel.sh` whenever panel sources change.
  `python dev_panel.py --build` is unsigned local-development packaging only.
- Preserve the Prism entry class, compatibility aliases, flat top-level imports, ports
  `9888`/`43210`, null-terminated chunked responses.
- Local checks: `python -m compileall -q Scripts`, `node --check Integration/helixae/js/main.js`,
  `python dev_panel.py`, `git diff --check`, plus `tests/run_tests.py` (see Phase 1).
- Integrated behavior requires Windows + Prism + AE + installed CEP extension; record Windows
  verification separately from local checks.
- Do not commit or push unless explicitly requested.

## Phase 0 — Runtime baseline

Goal: resolve external contracts before changing them.

Read-only observation via `ssh helix`:

- Running processes (AfterFX, CEPHtmlEngine, Prism python) and listeners on `9888`/`43210`.
- Installed extension location and expanded `helixae.cmd` (reveals real `PRISMROOT`/`PLUGINROOT`).
- Installed panel file hashes vs repository (ZIP parity).
- Prism's `err_catcher` decorator behavior and Qt binding from the installed Prism copy.
- AE version from registry/install path.

Runtime stage requiring the workstation UI (not read-only): Prism `postSaveScene` callback
argument order, save return-value handling, CEP embedded Node version, and creation of the
disposable AE test project (one-footage comp, nested precomps, 2D movies/stills/EXR sequences,
multi-shot/AOV, apostrophe/Unicode names).

### Phase 0 results (read-only subset)

Recorded during implementation; see "Phase 0 baseline notes" at the end of this file.

## Phase 1 — Composition cleanup correctness

Primary file: `Scripts/footage_tracker/comp_manager.py`, supported by the new
`Scripts/footage_tracker/comp_cleanup.py` protocol module and
`tests/test_comp_cleanup.py` regression tests.

Tasks:

1. Replace delimiter-based used/unused responses with structured JSON using a single atomic
   AE evaluation (used scan + unused computation server-side in one script).
2. Distinguish valid empty composition, invalid composition ID, and failed scan.
3. Abort removal when the scan failed.
4. Retain the selected composition and its recursive dependency tree.
5. Revalidate items before removal (existence + type + not in retained set, enforced both
   client- and server-side).
6. Return actual removed / not-found / failed counts.
7. Make Cancel effective between batches.
8. Wrap removal in an AE undo group with reliable cleanup.

Acceptance tests (covered by `tests/test_comp_cleanup.py` unless marked *Windows*):

- A comp using exactly one footage item never lists that footage for deletion.
- Zero, one, and multiple dependencies parse correctly.
- Nested precomps retain all dependencies.
- A failed bridge request causes no deletion.
- Cancellation and partial failure produce accurate summaries. (*Windows for UI behavior*)
- Round-trip through one AE evaluation preserves item names including Unicode/apostrophes. (*Windows*)

### Phase 1 implementation notes (2026-09-30)

- New `Scripts/footage_tracker/comp_cleanup.py`: stdlib-only protocol module — single
  atomic ExtendScript query (used scan + unused computation in one evaluation), JSON
  responses via the `executeAppleScript` json2 polyfill, batched removal script wrapped
  in one AE undo group with server-side revalidation (`retained` / `not_found` /
  `wrong_type` guards, anchor-comp abort), and strict parsers that treat `None`/empty
  responses as failures (per the resolved `err_catcher` contract).
- `Scripts/footage_tracker/comp_manager.py`: `removeUnusedFromComp` now distinguishes
  scan failure / no project / comp gone / not a comp / nothing to do; `_executeRemoval`
  rewritten as cancelable batches (20 ids/call) returning real counts; obsolete
  delimiter-based methods removed (`_getUsedItemsByComp`, `_getUnusedItems`,
  `_removeCompsFromProject`, `_removeFootageFromProject`).
- `tests/test_comp_cleanup.py` + `tests/run_tests.py`: 25 tests, all passing.
- Local checks: compileall, `node --check`, ZIP parity, `git diff --check` clean.
- Deployed to NAS with `dev_sync.sh` (checksum-verified). Python-only change: reload
  Prism on the workstation to pick it up; no CEP reinstall needed.
- Windows verification pending (list in the summary of this phase's report).

## Phase 2 — Launcher, bridge framing, startup dispatch

Primary files: `Integration/helixae/js/main.js`, `Integration/helixae.cmd`,
`Scripts/HelixAE_MenuTools.py`, `Scripts/HelixAE_Functions.py`, `Scripts/helixae_core.py`.

Tasks: fix `child` scope and launch error handling; use a Windows batch-launch mechanism tested
with CEP's embedded Node; correct cmd quoting while preserving placeholders; introduce explicit
request framing on `9888` (accumulate bytes before decoding, keep null-terminated chunked
responses, reject premature EOF, set timeouts before connecting); bind to loopback and handle
listener errors; enable panel operations only after bridge startup; handle occupied port;
frame `43210` commands fully with readiness handling, bounded retries, and acknowledgements;
queue commands until Prism is ready; validate the mutex and enter the event loop explicitly.

Deployment dependency: Python clients, CEP source, ZIP, and installed extension must move
together; a NAS sync alone does not update the installed extension.

### Phase 2 implementation notes (2026-09-30)

- New `Scripts/helixae_bridge.py`: stdlib-only wire protocol module (importable without
  Prism/Qt, also from `HelixAE_MenuTools.py` before Prism is on `sys.path`, and by the
  regression tests). Defines both bridges:
  - AE bridge (9888): `frame_ae_request()` / `recv_ae_response()` — null-terminated
    requests (embedded nulls rejected), one request per connection, chunked reads,
    premature EOF raises `BridgeError` (an empty-but-terminated response stays `b""`).
  - Command bridge (43210): `frame_command()` / `recv_command()` / `ok_reply()` /
    `error_reply()` / `recv_reply()` / `send_command()` — newline-terminated frames,
    4 KiB cap, `KNOWN_COMMANDS` allowlist, bounded-connect-retry forwarding
    (40 × 0.25 s default) with an explicit ok/error acknowledgement meaning
    "accepted for dispatch", not "action completed".
- `Integration/helixae/js/main.js`: requests are now accumulated as bytes until the
  null terminator (decoded once, so UTF-8 split across chunks survives); empty or
  oversized frames destroy the socket; `pid` stays a synchronous special case; idle
  timeout applies only until the frame is complete. Server binds explicitly to
  `127.0.0.1:9888`, has an `error` handler (EADDRINUSE disables the panel and shows
  the reason instead of silently manipulating the other AE instance), and buttons plus
  the auto-launch are gated on successful `listening`. Launcher fixed: function-scoped
  `child`, allowlisted commands only, Windows spawns `cmd.exe /d /s /c` with the
  double-quote wrap and `windowsVerbatimArguments` (quotes survive paths with
  spaces), nonzero exit codes surface an alert, non-Windows spawns directly and
  reports the failure through the error handler.
- `Integration/helixae.cmd`: `set "NAME=value"` quoting (installer token replacement
  unaffected, CRLF preserved).
- `Scripts/HelixAE_MenuTools.py`: startup command resolved (with default) and
  validated before any dispatch; Windows mutex creation now has argtypes/restype
  and a NULL-handle warning; the secondary instance forwards via
  `helixae_bridge.send_command()` (framed, retried, acknowledged) and exits with a
  meaningful code. The command listener binds synchronously in the main thread after
  Qt is importable — bind failure aborts startup loudly instead of running a UI with
  a dead command port. Received commands are framed reads, validated against
  `KNOWN_COMMANDS`, dispatched via queued invocation and acknowledged. Commands that
  arrive while `PrismCore.create()` is still initializing (splash/nested event loops)
  are queued and flushed once `pcore` exists. Unknown commands are logged and
  rejected (the legacy `"tools"` command with its undefined
  `openAfterEffectsTools()` reference was removed — no senders existed). The event
  loop is entered unconditionally via `sys.exit(qapp.exec_())`.
- `Scripts/helixae_core.py` / `Scripts/HelixAE_Functions.py`: both 9888 senders use
  `helixae_bridge` framing; the 120 s AE timeout is set before `connect()`;
  `_recvAll` removed; `sendCmd` returns `None` on premature EOF (transport failure,
  never `b""`).
- `tests/test_helixae_bridge.py`: 29 tests — request/response framing, premature
  EOF, chunked + terminator-split + UTF-8-split reassembly, 300 KB response,
  oversized command rejection, control-character rejection, ok/error reply parsing,
  sanitization, connect-retry/exhaustion, client-side unknown-command rejection,
  socket close verification. Total suite: 54 tests passing.
- Local checks: compileall, `node --check`, ZIP parity after `dev_panel.py --build`
  (ZIP rebuilt for the new `main.js`), `git diff --check` clean (known CRLF
  normalization warnings only).
- **Deployment caveat**: this is a coordinated protocol change. The workstation must
  reinstall the HelixAE integration through Prism (updates the installed panel from
  the new ZIP) **before** restarting Prism/AE — an old panel with the new Python
  clients cannot talk to each other (old server evaluates unframed chunks).
- **Windows verification finding (fixed 2026-09-30)**: first panel launch after the
  reinstall failed with exit code 1. Read-only diagnosis via `ssh helix` showed the
  new panel healthy (9888 loopback listener owned by the panel renderer, new quoted
  `helixae.cmd` installed) but no Python UI process surviving. Root cause: Prism's
  embedded Python is fully isolated (`python313._pth` lists only `python313.zip`
  and `.`, no site, script dir never added to `sys.path`), so the new
  `import helixae_bridge` in `HelixAE_MenuTools.py` raised `ModuleNotFoundError`.
  Fix: MenuTools now inserts its own Scripts directory into `sys.path` before the
  import and shows a visible message box on import failure (no Qt available yet at
  that point).   Recorded as a durable rule in AGENTS.md. Python-only change: redeploy
  + relaunch from the panel; no CEP reinstall needed.
- **Windows verification (2026-09-30, user-confirmed)**: after the fix the panel
  launches Prism, all panel buttons/menus work, and the new bridge framing is in
  use end to end. Remaining Windows spot-checks worth doing opportunistically:
  rapid clicks during cold start (exactly-once dispatch), a second AE instance
  (expect the disabled-panel message), and the Phase 1 cleanup scenarios.

## Phase 3 — Trustworthy AE data and operation results

Primary files: `helixae_core.py`, `HelixAE_Functions.py`, `helixae_export.py`, `helixae_ui.py`,
`data_parser.py`, `ae_operations.py`, `import_shots.py`.

Tasks: shared JS string serialization helper; JSON instead of `eval()`/quote-stripping; decode
UTF-8 directly; explicit success/error results for save/open/import/replace/export; require
confirmed queue creation before publishing export metadata; check the real Prism save result;
associate archive data with the exact save and clear stale state; consolidate version-info
patch paths after verifying Prism callbacks; preserve legitimate empty dependency lists;
validate active comp/template and clean up partially created queue items.

### Phase 3 implementation notes (2026-09-30)

- New `Scripts/helixae_protocol.py` (stdlib-only, top level): the single source of AE
  request/response encoding. `js_string()` embeds any Python string into ExtendScript
  (ASCII-escaped JSON literal — apostrophes, quotes, backslashes, Unicode, newlines in
  paths and names survive); `build_*` builders produce try/catch IIFE scripts that
  always answer via `JSON.stringify` (mutations confirm success explicitly and remove
  partially created AE objects on failure); strict `parse_*` parsers treat
  `None`/empty/non-JSON/non-object payloads as failures; `ensure_json_polyfill()` is
  idempotent. `ae_operations.py` was explicitly left for Phase 4 (scope).
- `helixae_core.py`: `saveScene` requires a confirmed save ack (verifies the on-disk
  project path) before any archive work, pops up the real reason otherwise; archive
  data (`_last_archive_data`) is owned by the exact save path via a normalized
  `_last_archive_path` and reset per save (no cross-save leakage); the footage scan is
  JSON (`build_collect_footage_records` + `parse_footage_records`, file-backed items
  only); `getCurrentFileName` is JSON with `''` on failure (fixes the `'null'` string);
  `openScene` requires a confirmed ack; `_patchVersionInfo` assigns
  `dependencies`/`externalFiles` unconditionally when archive data is known (empty
  lists are authoritative instead of leaving stale entries behind).
- `HelixAE_Functions.py`: `sendCmd` injects the polyfill (new optional `timeout=3.0`
  parameter — the dead-but-preserved `RenderDlg` uses 3600 s for blocking renders);
  all ten `eval()` sites replaced with protocol builders/parsers; `checkVersions`
  distinguishes bridge failure (popup, stop) from an empty project (up to date);
  `getFootageFromProject` skips solids/placeholders (old code crashed on
  `item.file` of a solid); `postSaveScene` only passes archive data when the saved
  path matches `_last_archive_path` (else the patch reads `_archiveinfo.json` from
  disk).
- `helixae_export.py`: shared `_addRenderQueueItem`/`_writeExportMetadata`/
  `_validateExportInputs` helpers deduplicate `saveExport`/`renderAndSave`; the render
  queue item must be confirmed created (comp validated, template applied, output file
  set, failures clean up the partial queue item) **before** any `saveVersionInfo` /
  versioninfo patch / success popup — no more false success when AE is unreachable;
  `renderAndSave` also aborts when `saveScene` returns `False`; `getOutputModules`
  surfaces failures and falls back to the well-known template list only because it
  feeds a dialog.
- `helixae_ui.py`: `RenderDlg.render()` uses `build_render_with_template` with strict
  parsing (long timeout noted above). `RenderDlg` itself remains dead code (never
  instantiated; kept for future wiring).
- `data_parser.py`: `parseFootageData`/`parseCompData` delegate to the protocol
  parsers (transport/parse failures now pop up visibly; valid empty arrays stay
  empty); `getFootageAppleScript`/`getCompAppleScript` return the JSON collectors —
  the `str(bytes).replace("b'","")` quote-stripping (which corrupted
  `Client's éclair`-style names) and the `|||`/`::ITEM::` delimiter formats are gone.
  The `'N/A'` sentinel semantics for absent footage fields are preserved (tree
  consumers compare against them).
- `import_shots.py`: `importFootageItem` uses `build_import_footage_item` (JSON ack,
  `js_string` embedding, fps conformed only for valid sequence imports) — replaces
  the quadruple-backslash Windows path hack, unescaped f-string interpolation, and
  `SUCCESS:`/`ERROR:` prefix parsing.
- `HelixAE_MenuTools.py`: `_patchVersionInfo` now delegates to the single
  authoritative implementation on `ae_core` (prefers fresh archive data for the
  just-saved path, falls back to `_archiveinfo.json` on disk) instead of patching
  versioninfo files itself with duplicated, guard-only-if-nonempty logic.
- Tests: `tests/test_helixae_protocol.py` (44 tests) covers polyfill idempotency,
  `js_string` escaping (apostrophe/backslash/Unicode/newline), strict failure modes
  (`None`/empty/whitespace/invalid JSON/non-object/`null`), builder validation
  (frames, fps, paths, indexes, templates, import args), script shapes,
  `'N/A'` coercion + backslash normalization + Unicode/delimiter round-trips for
  tracker records, and simulated AE ack round trips (save success/failure, transport
  failure never success, script errors). Total suite: 98 tests passing.
- Local checks: compileall, `node --check`, ZIP parity (`dev_panel.py` — no panel
  change, ZIP untouched), `git diff --check` clean (known CRLF warnings only).
- Deployment: Python-only change — `dev_sync.sh`; workstation needs a Prism restart,
  **no CEP reinstall**.
- Windows verification pending: save/open with AE closed (expect a clear failure,
  no metadata), export with a bad template/AE closed (expect "Could not add the
  render to the queue", no versioninfo written), footage tracker refresh with
  apostrophe/Unicode names, `Check Issues`/`Check Versions` with the bridge down
  (expect the explicit error popup), import via tracker with a sequence.

## Phase 4 — Version discovery, replacement, imports

Primary files: `ae_operations.py`, `shot_switcher.py`, `utils.py`, `import_shots.py`.

Tasks: fix doubled `v` substitution; deterministic media matching instead of the permissive
regex; keep full version-folder names separate from base versions; resolve actual files;
remove hard-coded cross-project fallbacks; require requested identifier/AOV with a clear
missing-target result; deterministic sequence sorting; don't treat `versioninfo.json` alone as
usable media; remove the "first five entries" discovery heuristic; deduplicate selected import
descendants.

### Phase 4 implementation notes (2026-09-30)

- NEW `Scripts/footage_tracker/version_paths.py` (stdlib-only, unit-tested): version token
  extraction/validation, version-folder index, single-substitution filename rewriting
  (`_v0003_` never doubles to `_vv0003_`; handles `_v0002.mov`, `_v0002.1001.exr`,
  `_v0002[mp4].mov`), `build_new_version_path` (folder + filename, forward-slash output,
  `ValueError` without a version folder), deterministic `footage_base_name` (replaces the lazy
  regex that collapsed `SQ02-SH010_HighRes_v0002.mov` to `S`), footage-extension whitelist,
  `match_footage_file` (sorted; video > frame-numbered > plain; base-name equality required,
  `None` when nothing matches — no arbitrary first-entry pick), `sorted_listing`.
- `Scripts/helixae_protocol.py` additions: `_as_id` (digits-only id validation),
  `build_get_footage_properties` (isStill + conformFrameRate), `build_replace_footage_by_id`
  (still/sequence replace by AE item id; reads previous conform rate and re-applies it or an
  explicit `conform_fps`; `alphabeticOrder = false` for sequences; AE-side `file.exists`
  check; JSON ack), `build_set_footage_fps`, `build_set_comp_fps`,
  `build_set_comp_frame_range`, `build_set_comp_resolution`.
- `ae_operations.py` update family rewritten onto the protocol: `_resolveNewVersionPath`
  (builds the new path, matches the actual file in the AOV/version folder, honors the
  tracker's sequence/still-path helpers, verifies existence), `_replaceFootageInAE`,
  `_getFootageProperties`; `updateFootageVersion` (clear "Version Not Found" popup with old
  path and requested version; base/full version distinction and tree ✓/⚠ status kept),
  `_updateFootageVersionNoRefresh`, `_updateSingleFootageVersion`,
  `updateFootageFPS`/`updateCompFPS`/`updateCompFrameRange`/`updateCompResolution`
  (confirmed acks; failure popups instead of fire-and-forget), `updateAllFPS`/`batchUpdateFPS`.
  Zero `str(result).replace("b'","")` sites remain in the file.
- `shot_switcher.py`: hard-coded cross-project fallbacks (`X:/Align_iTero_Lumina_MultiPreps`,
  `X:/Halloween_2025`) removed from `_findLatestVersionOnDisk`; the "any valid AOV" fallback
  removed (the requested AOV is required — a wrong-pass import is worse than a clear miss);
  media whitelists + `sorted()` for version-dir listings; `_importAndReplaceFootage` and
  `_replaceFootageWithNewPath` replaced via `build_replace_footage_by_id` with JSON acks and
  failure popups (the last `SUCCESS` string-protocol site in the version-switch path).
- `import_shots.py`: the `[:5]` scan heuristics replaced with full scans using the footage
  whitelist (`versioninfo.json` alone no longer marks a version as having media);
  `importSelected` deduplicates selected items so an ancestor + descendant selection no
  longer double-imports.
- Originally deferred in Phase 4; completed by the legacy protocol sweep below:
  the reveal/duplicate/delete/organize family
  in `ae_operations.py` (revealInProject, revealInCompositions, openComposition,
  createFolderStructure — which also has a duplicated method definition where the second
  shadows the first — duplicateFootageItem, duplicateCompItem, deleteFootageItem,
  deleteCompItem, removeAllEmptyFolders, replaceFootage) still uses hand-built string
  protocols, as do `context_menu_compositions.py` (`SUCCESS|` format),
  `context_menu_lighting_import.py`, `import_dialog.py`, `tree_operations_core.py`,
  `ae_organize_manager.py`, and `startup_warnings.py` `SUCCESS` sites. They are read-only or
  non-version-path operations. These historical findings motivated the completed sweep.
- Tests: `tests/test_version_paths.py` (45 tests) covering token extraction, the no-doubling
  regression, deterministic base names (`SQ02-SH010_HighRes_v0002.mov` →
  `SQ02-SH010_HighRes`), path building for both layouts, match determinism (no arbitrary
  first-entry fallback, cross-AOV isolation), and the seven new protocol builders including
  id/fps/resolution validation and conform-rate preservation. Writing the tests caught and
  fixed a real bug: the trailing `_<digits>` strip regex matched literal parentheses
  (`_(\d+)`) instead of `_2`-style suffixes. Suite total: 143 tests passing.
- Verification: `compileall -q Scripts`, `node --check`, `dev_panel.py` (no panel change;
  ZIP untouched), `tests/run_tests.py` 143/143, `git diff --check` clean. Deployed via
  `dev_sync.sh` (checksum-verified). Python-only change: Prism restart on the workstation
  suffices, no CEP reinstall.

#### Phase 4 Windows verification checklist

1. Restart Prism; open a project with 3D-render footage.
2. Switch a footage item to another version → correct file loads (movie stays a movie,
   sequence stays a sequence with its frame range and conform fps).
3. Request a version that does not exist on disk → "Version Not Found" popup naming the old
   path and the requested version; nothing changes in AE.
4. Footage/comp FPS, frame range, and resolution updates apply and report failures visibly.
5. Shot switcher imports the requested AOV only; a missing AOV produces a clear message
   (never a different pass); no `X:/...` cross-project fallbacks occur.
6. Import dialog: a version folder containing only `versioninfo.json` is not offered as
   media; selecting a parent and child together imports each item once.

## Phase 5 — Caches, metadata, bypass persistence

Primary files: `version_cache_manager.py`, `hierarchy_builder.py`, `import_shots.py`,
`startup_warnings.py`, `context_menu_bypass.py`, `tree_renderer.py`.

Coordinated repair, never a partial one: missing imports and nested-lock deadlocks;
project-scoped cache keys supporting file and folder paths; schema validation, expiry, forced
refresh, project-change invalidation; last-known-good on NAS failure; unique temp files and
replace-based writes; defined multi-process behavior for the shared import cache; failed
persistence keeps dirty state; valid namespace-aware XMP handling that preserves unrelated
metadata; keep disposable discovery caches out of the `.aep`; one shared bypass-key builder
with legacy migration.

### Phase 5 implementation notes (2026-09-30)

Status: implemented, locally verified (238/238 tests), deployed; Windows verification
pending.

- **New stdlib modules** (testable by file-path load, per house convention):
  - `Scripts/footage_tracker/cache_store.py` — path/version-folder parsing, deterministic
    version sort (newest first, plain before suffixed), cache-key extraction
    (`SQ020-SH030/Lighting_Humans` from render paths), cache schema validation that drops
    malformed entries instead of failing the whole document, entry freshness via
    `last_scanned`, and `atomic_write_json` (unique temp file + `fsync` + `os.replace`).
  - `Scripts/footage_tracker/bypass_keys.py` — one canonical bypass-key builder shared by
    the context menu (`key_from_tree_item`) and startup warnings
    (`key_from_item_data`), preserving the historic key strings exactly (3-part
    `footage_{shot}_{identifier}_{aov}`, 2D two-part keys with duplicate-suffix folding,
    comp keys, all fallbacks).
  - `Scripts/footage_tracker/xmp_payload.py` — namespace-aware XMP payload storage
    (`prismft` namespace, canonical `<prismft:Tag>escaped</prismft:Tag>` inside an
    `rdf:Description`). Reads BOTH legacy malformed variants (`Tag">` from
    hierarchy_builder and `Tag>` from the old startup-warnings append path — the bug that
    made append-saved bypasses unreadable on reload), strips/replaces them on write, and
    XML-escapes payloads.
  - `Scripts/helixae_protocol.py` gained `build_get_xmp_packet()` /
    `build_set_xmp_packet()` (confirmed readback; `required_marker` check).
- **`version_cache_manager.py` rewritten**: fixed the missing `import re` (NameError masked
  by `err_catcher`) and all three nested-lock deadlocks (`stop()`, `invalidateEntry()`,
  `scanAndCacheFolder()` saved the cache while already holding the non-reentrant
  `cache_lock`); saves are now atomic (`atomic_write_json`), keep dirty state on failure,
  clear it on success; corrupt cache files are moved aside (`*.corrupt`); per-entry
  5-minute expiry; project-change invalidation via normalized path compare; new
  `storeEntry()` / `isDirty()` / `mergeEntries()` APIs (merge keeps existing entries and is
  used by the one-time legacy XMP migration).
- **`import_shots.py` CacheManager**: unique pid-suffixed temp file + `os.replace` (no
  fixed `.tmp` name, no remove+rename gap); UTF-8 reads/writes; state swaps under the
  lock; worker never saves while holding the lock; last-known-good guard (an empty rescan
  no longer wipes a non-empty cache during a NAS blip); the update signal now uses
  `self.cacheUpdated.emit(...)` (the old `QMetaObject.invokeMethod` +
  `Q_ARG(dict)` used an unregistered metatype and silently never fired).
- **`hierarchy_builder.py`**: no longer writes the disposable version cache into the
  `.aep` XMP packet (the malformed `<rdf:li ...` writer is deleted). The cache lives in
  `.prism_footage_cache.json` next to the project root; a one-time migration reads the
  legacy XMP `VersionCache` payload and merges it into the file cache without writing XMP
  back. Scan results are stored with `last_scanned` timestamps; dirty caches are saved at
  the end of `buildHierarchy()` / `cleanup()`.
- **`startup_warnings.py`**: bypassed items are read via `build_get_xmp_packet()` +
  `xmp_payload.extract_payload` (accepts both legacy variants AND the canonical form) and
  written via `upsert_payload` + `build_set_xmp_packet(required_marker=...)` with a strict
  confirmed ack; the marker-mismatch append path (`_appendBypassedItemsToXMP`) is deleted.
  Sidecar `_bypassed.json` and project-config fallbacks are unchanged; the config
  dual-write is kept. `_generateItemKey` now delegates to `bypass_keys` (no more per-call
  debug spam).
- **`context_menu_bypass.py`**: `_buildItemKey` delegates to
  `bypass_keys.key_from_tree_item` — one shared key format, so context-menu bypasses and
  startup-warning keys can never drift apart again.
- **Bugs caught by the new regression tests and fixed before deploy**: the legacy XMP
  regex did not allow the historic `PrismFootageTracker:` prefix between `<rdf:li>` and
  the tag (legacy blocks were never stripped/replaced), and `bypass_keys` built a
  two-part key before the 2D duplicate-suffix fold could run (parity break with the
  historic key format).
- **Tests**: `tests/test_cache_store.py`, `tests/test_bypass_keys.py`,
  `tests/test_xmp_payload.py` (95 new tests; suite total 238 passing).
- **Deployment**: Python-only change — `dev_sync.sh` checksum-verified deploy; workstation
  needs a Prism restart, no CEP reinstall.

### Phase 5 Windows verification checklist (pending)

1. Restart Prism on the workstation.
2. Bypass an issue in Check Issues, save, close/reopen the project → the bypass is still
   applied (including bypasses saved by the OLD version — both legacy XMP variants).
3. `.prism_footage_cache.json` appears next to the project root after a tracker refresh;
   second refresh is fast (cache hit).
4. A transient NAS outage during the import dialog does not wipe `footage_cache.json`
   (last-known-good), and the import tree recovers on the next poll.
5. Two Prism processes on the same project cannot corrupt the caches (unique temp files,
   atomic replace).
6. No `PrismFootageTracker:VersionCache` XMP is added to newly saved projects (disposable
   caches stay out of the `.aep`).

## Phase 6 — Tracker responsiveness and lifecycle

Primary files: `tracker.py`, `tree_operations.py`, `tree_renderer.py`, `kitsu_integration.py`,
`import_shots.py`.

Tasks: measure phases separately; show dialog before slow work; keep last-good snapshot during
refresh; move suitable filesystem/network work off the GUI thread (verify Prism/Kitsu thread
suitability first); generation IDs to discard obsolete results; explicit worker shutdown;
project-keyed Kitsu caches; sequence-qualified shot keys; batch/lazy Kitsu tasks; restore the
actual previous output streams when closing the debug UI.

### Phase 6 implementation notes (2026-09-30)

#### Follow-up: reopening rescans (2026-09-30)

#### Follow-up: Project Browser open timeout (2026-09-30)

- User reported "Opening in After Effects failed: empty response from After
  Effects" when opening a scene from the Project Browser. The facade was using
  the lightweight 3-second command timeout for project loading. It now delegates
  to the core open handler, which waits up to 120 seconds and still requires a
  confirmed JSON acknowledgement. No automatic replay of an uncertain open.
- Three regression tests ensure operation-handler routing, argument forwarding,
  and propagation of failure/None rather than success. Total: 255 passing tests.
- Windows verification pending: restart Prism and open the affected scene from
  Project Browser. Confirm the project loads and the warning no longer appears.

#### Reopen snapshot behavior

- Reopening the tracker for the same saved AE scene now renders its last
  successful in-memory hierarchy instead of querying all footage, loading
  Kitsu, and discovering versions again. A lightweight current-scene query
  checks ownership against the Prism project and scene path. Different scenes,
  unsaved/unavailable scenes, and missing snapshots still take the normal load
  path. The status bar identifies cached data; use Refresh to see external AE
  edits or newly published versions. Snapshots last for the current Prism
  process, and successful refreshes replace them.
- Opening the tracker no longer restarts the import-folder polling worker.
  Opening Import Footage restarts that worker when needed instead.
- Five regression tests cover same-scene reuse, changed/unavailable scenes,
  missing snapshots, and legitimate empty snapshots. Total: 252 passing tests.
- Windows check: restart Prism, open/close/reopen the tracker on the same scene
  (last-scan status, no full load), then Refresh and open a different scene
  (fresh load). No CEP reinstall is needed for this Python-only fix.

- Tracker dialog is shown and painted before the initial load. Queries still
  run on the GUI thread; this change does not make the full refresh nonblocking.
- Refresh validates both AE query responses and builds the replacement hierarchy
  before clearing the visible tree. Query/parse/hierarchy failures retain the
  previous tree and stored hierarchy. Generation and dialog-identity checks
  reject obsolete commits and delayed scroll restores. Renderer failures after
  the tree has been cleared do not yet have a transactional rollback.
- Kitsu caches are scoped to the Prism project. Sequence-qualified shot keys are
  retained, while ambiguous bare aliases are omitted rather than selecting an
  arbitrary sequence. Shot entity lookup follows the same ownership map.
- Kitsu tasks are fetched and cached when the footage context menu requests them,
  removing the eager per-shot task-query loop during tracker startup.
- Debug output is queued through a Qt string signal. Closing the tracker restores
  the actual previous output streams, provided another owner has not replaced
  them in the meantime.
- Closing the tracker explicitly stops the import-cache worker. Poll/backoff
  waits are interruptible, and a stopped worker discards an in-flight scan before
  saving or emitting. An OS-level NAS scan cannot be forcibly interrupted; if it
  outlasts the bounded shutdown wait, reopening waits for that worker to exit
  before a later open can restart it.
- Added nine regression tests for shot-key collisions and the actual refresh
  orchestration under bridge/parse/NAS failures. Full local suite: **247 passing**;
  Python syntax, JavaScript syntax, ZIP parity and diff checks pass.
- Deployment is Python-only: restart the Prism UI launched by the panel. The
  existing CEP panel does not require reinstallation.

**Remaining work at the time of the initial subset:** verify Prism/Kitsu thread suitability before moving
network or AE work off the GUI thread, collect Windows timing measurements using
the existing phase instrumentation, and validate lifecycle behavior in the
installed Qt/CEP runtime. These gates remain open; Phase 6 is partially complete.

The background-loading implementation below supersedes the worker-boundary
deferral. Windows runtime validation and measured timings remain required.

**Windows verification checklist:**

1. Restart Prism, open the tracker, and confirm it appears before data loading.
2. Refresh once successfully, then make the bridge unavailable and refresh:
   expect a clear error with the previous tree preserved.
3. Check shots with the same name in two sequences: qualified names must resolve
   correctly, and an ambiguous bare name must not select a different sequence.
4. Open footage context menus and confirm Kitsu tasks load on demand; switch
   Prism projects and confirm old project data is not reused.
5. Close/reopen the tracker while the import cache polls; confirm no duplicate
   workers or destroyed-widget errors, and that other Prism logging still works.
6. Capture cold/warm load timings before scheduling background-loading work.

### Phase 6 background scene-preparation plan and implementation (2026-10-02)

Approved plan, preserving the existing middle-click Footage/Kitsu menu and
bottom-right **⟳** menu:

1. Profile AE collection, metadata/version scans, Kitsu requests and UI work
   separately; inspect installed Prism methods before choosing thread boundaries.
2. Collect one scene-stamped AE snapshot, capturing project items once and walking
   each comp layer once to construct the precomp-parent map.
3. Build the usable inventory from AE values without NAS or Kitsu waits. Enrich
   it with deduplicated NAS scans/metadata reads and independent Kitsu requests.
4. Own preparation at plugin level, independent of the tracker dialog, with
   lane-specific generations, coalescing, cancellation and bounded shutdown.
5. Prepare after confirmed scene opening and at startup; use a lightweight scene
   identity probe for changes made directly in AE. Avoid periodic inventory scans.
6. Display available inventory first, update existing leaf items as checks finish,
   preserve expansion/selection/scroll/filter/grouping, and provide animated
   progress beside the existing refresh control.
7. Test races and failure/data-integrity cases, verify/deploy, then measure and
   validate the installed Windows/Prism/AE workflow.

Implementation:

- `helixae_protocol.py`: combined snapshot and cheap scene identity builders with
  strict parsing. The combined script captures the project item array once and
  builds parent relationships with one layer walk. It also includes existing XMP
  in the snapshot, avoiding row-by-row AE queries for bypass styling. Actual
  numeric values are not prematurely rounded before calculating frame ranges.
  A Node execution fixture verifies item/layer visit counts and parent deduping;
  native ExtendScript object/session identity behavior still needs Windows checks.
- `helixae_refresh.py`: stdlib worker/job service and read-only AE/NAS preparation.
  One worker per lane, latest-request coalescing, generation-checked delivery
  (including invalidation during queue draining), cooperative cancellation and
  bounded shutdown. NAS identifiers are scanned once per refresh, metadata folders
  read once, and JSON-only version folders are not counted as usable media.
  Failed NAS checks retain prior versions with explicit stale/failed states.
  Legacy bypass sidecars are read in the NAS worker.
- `footage_tracker/refresh_controller.py`: plugin-owned Qt coordinator with
  scene/project scoping and prewarming without constructing a tracker window.
  Confirmed open and Prism callbacks invalidate preparation; startup and direct
  AE changes are detected with a three-second identity probe that does not list
  project items or inspect media. Cached dialog reopening does not request an AE
  snapshot or rescan NAS. Preparation survives closing the tracker. A changed
  scene disables old rows until the new inventory arrives; same-scene refresh
  retains the usable list while work runs.
- Kitsu boundary verified by read-only inspection of the installed Prism Kitsu
  code: `getShots`, project/FPS/resolution helpers and authentication wrappers can
  invoke Qt/login UI. They are **not** executed in workers. Instead the GUI captures
  already available host/token/TLS/project settings; a worker owns its HTTP session,
  uses explicit connect/read timeouts, reads project/sequence/shot collections and
  deduplicates shot-resolution lookups. Episode naming and sequence-qualified keys
  are preserved. No credentials are logged or persisted; missing/expired auth is
  an explicit check failure, with signing in handled through Prism.
- AE actual values remain separate from `published` metadata. Published fields are
  available as row data/tooltips and never overwrite displayed AE FPS/dimensions/
  frame range. Pending, stale and unavailable version checks are not labeled
  current/outdated. Incomplete checks do not produce a green “No Issues” result.
- `tracker.py`, `tree_operations.py`, `ui_setup.py` and `tree_renderer.py`: the
  existing Footage action requests AE + NAS work and reuses Kitsu; Kitsu requests
  only Kitsu and reuses AE + NAS data. Initial inventory builds the grouping tree;
  enrichment updates existing leaf items/cells without clearing it. Selection is
  restored by AE IDs, with scroll/expansion/filter/grouping retained. Delivery
  pauses while a modal dialog or popup menu is active. GUI widget work remains on
  the GUI thread, with repainting suppressed for each update batch.
- A slim progress bar appears next to **⟳** with phase text. Unknown/overlapping
  stages use a busy animation; a lone NAS stage can show real directory counts.
  Errors are shown independently of ongoing work. Stage timings and directory/
  HTTP counts are logged; workstation speedups are not inferred from local mocks.
- Import discovery/cache initialization is lazy at import-dialog opening, avoiding
  an unrelated import scan when opening the footage tracker.

The OS can still block a NAS filesystem call beyond cooperative cancellation;
HTTP requests use per-request timeouts. Shutdown discards late results and does
not wait indefinitely or touch destroyed Qt widgets. The small Qt update batch is
still GUI-thread work; large-scene rendering performance requires real timings.
Scene-preparation results are process-local and refreshed on scene change or the
existing manual controls; legacy file-cache helpers remain available to older
callers.

Focused tests cover worker races/coalescing/independent lanes/bounded shutdown,
hidden preparation and cached reopening, snapshot failure retention, NAS scan
deduplication/JSON-only folders/stale data, separate published values, batch Kitsu
requests/resolution/episode naming, leaf identity preservation, and actual generated
JS execution including cheap scene probes. Windows verification remains separate.

Local verification: all **297 regression tests passed**, Python compilation and
CEP JavaScript syntax checks passed, panel ZIP/source parity passed, and
`git diff --check` passed. Deployment uses `bash dev_sync.sh` with remote checksum
verification. These are Python-only changes: restart panel-launched Prism to load
them; no CEP integration reinstall is required.

**Windows verification:** restart panel-launched Prism (no CEP reinstall), then:

Live follow-up: an empty tracker after opening a scene was traced through AE MCP
to an invalid retained AE Project object. ExtendScript throws even when comparing
that disposed object with the current project. The scene identity builder now
catches the invalid comparison and renews its token. The corrected probe was
verified against the live project (35 items); a generated-script regression covers
the invalid reference. All 298 local tests and required syntax/parity checks pass.

1. Open a scene without opening the tracker; later open the tracker and check that
   prepared data appears. Close/reopen it: no inventory/NAS rescan should occur.
2. Open the tracker immediately after a scene change: AE rows should appear before
   NAS/Kitsu finish, with animated progress and explicit unchecked statuses.
3. Use both existing refresh menus. Footage should refresh AE/NAS only; Kitsu should
   refresh Kitsu only. Repeated clicks must not create overlapping same-lane jobs.
4. Keep a filter, selection, expansion state and scroll position while checks finish;
   open/close a context menu and confirm delayed delivery is safe.
5. Change scenes during checks, reopen the same path, create an unsaved project and
   Save As. No result from the previous scene/project may be applied.
6. Check NAS/API/bridge failures: previous valid results remain clearly stale or
   incomplete, with no false green status. After Prism sign-in, Kitsu refresh should
   populate the correct project/sequence/resolution data.
7. Capture `[TIMING]` AE, NAS, Kitsu and UI logs for a real cold and warm large scene.
   Compare first-usable-list time separately from time until all checks finish.

### Phase 6 follow-up: backend accuracy, replacement reliability, sequence integrity (2026-10-02)

Approved scope after user feedback: keep the existing tree/search/status-filter
interface unchanged and improve the underlying checks. No replacement UI, no
automatic image modification; EXR resize work remains deferred.

- **Replacement reliability.** Version switching no longer forces a 25 fps conform
  rate on footage without an explicit interpretation (AE reports 0 when the rate is
  native/unset); the original rate — including fractional rates like 23.976 — is
  preserved, stills are skipped, and alpha/field/pulldown/loop interpretation is
  captured before `replace()`/`replaceWithSequence()` and restored afterwards.
  Interpretation properties AE cannot restore are reported explicitly in a popup
  instead of being silently dropped. `_resolveNewVersionPath` now rejects missing
  and zero-byte targets before touching AE.
- **On-demand sequence validation.** New read-only background action
  "Validate sequence files…" on the footage context menu checks interior frame
  gaps and zero-byte files for the selected footage paths. It runs in its own
  worker lane (cancelable via "Cancel sequence validation"; cancelling that lane
  no longer cancels other running checks), reuses one directory listing for
  duplicate selections, never modifies sources, and reports gaps as ranges rather
  than allocating per-frame entries (a 1→99999999 gap stays one range). Sequence
  boundaries outside the on-disk files remain unknown and are not guessed.
- **Published tooltips.** Repeated NAS enrichment no longer appends duplicate
  published-metadata blocks to the same tooltips.

Focused tests (`tests/test_sequence_integrity.py`): gap/empty-file/AOV isolation,
huge-gap range representation, duplicate-path dedup with sources unmodified,
directory/stat failure reporting (never success), pre-scan cancellation, movie/
non-numbered rejection, per-lane cancellation isolation, and generated-JS
replacement round trips (native rate 0 preserved, fractional conform rate
preserved, partial interpretation failure reported with success ack).

Local verification: **309 tests passed**, `compileall`, `node --check`, panel ZIP
parity and `git diff --check` passed. Python-only change — restart panel-launched
Prism; no CEP reinstall.

**Windows verification:** switch a version of sequence footage with no explicit
conform rate (must not become 25 fps), replace footage whose target folder has an
empty/missing file (must fail before AE), replace footage with alpha
interpretation (status preserved), run "Validate sequence files…" on healthy and
gapped sequences and cancel it mid-run.

**Windows verified (2026-10-02):** user confirmed the improvements work on the
workstation ("works great").

## Phase 7 — Image resize recoverability

Primary files: `image_resizer.py`, `context_menu_image_resize.py`.

Tasks: keep the backup workflow; write resized output to a temporary sibling; validate output
before replacing the source; explicit restoration failure reporting; cancellation between
files with accurate counts; prevent overlapping resize actions; verify EXR/ID-pass/Cryptomatte
behavior and deep EXR with the installed OpenImageIO build.

### Phase 7 implementation notes

- Added stdlib-only `resize_transaction.py`: exclusive-create backups verified
  by SHA-256, unique same-directory output with the original format extension,
  source-change detection, and replacement only after renderer validation.
  Failed rendering, validation or replacement retains the source; a successful
  replacement keeps the verified backup. No automatic backup restoration is
  needed because the renderer never writes to the original. Backup and replace
  errors are reported in the results instead of hidden in debug output.
- `image_resizer.py` reads the completed output back before allowing replacement;
  checks dimensions, channel names, EXR pixel/channel types and Cryptomatte
  attributes. Copies input attributes/channel names to output, writes with the
  source pixel type, and forces nearest-neighbor for detected Cryptomatte.
  Mask/ID fallback classification now precedes color classification.
- Deep, multipart and mipmapped images are explicitly rejected with originals
  retained; no claim of deep-image preservation is made. The installed Windows
  OIIO build still needs actual color/ID/Cryptomatte fixture verification.
- Single and multi-AOV actions share a process-wide guard, including modal
  confirmation and Qt event-processing re-entry. This is not a distributed
  lock against other workstations editing the same images; source fingerprints
  detect changes observed before replacement.
- Cancel is checked before every file and subsequent AOV. Results show completed,
  failed, skipped and canceled status. Batch selection freezes sorted file lists
  before confirmation; removed the unsafe arbitrary-first-folder-entry fallback.
  Backup directory timestamps include microseconds and existing backups are
  never overwritten.
- Eleven focused regressions cover verified backups, partial/empty output,
  replacement failure, preexisting backup preservation, external edits,
  cancellation counts, missing renderer results, action re-entry, deep-image
  rejection and in-place-call rejection. **266 tests pass**, Python/JS syntax,
  ZIP parity and `git diff --check` pass. Python-only deployment: restart Prism;
  CEP reinstallation is not required.

### Phase 7 Windows verification (pending)

Follow-up: user reported Cancel ineffective on the workstation. The initial
implementation still blocked Qt during each file and relied on the progress
dialog's resettable cancellation flag. File processing now runs on a joined
worker while the GUI pumps events; progress is queued back to the GUI thread.
A `threading.Event` connected to the canceled signal persists across progress
updates and AOVs, with auto-reset/auto-close disabled. The current file finishes
safely, then the remaining files are skipped. A focused regression waits for a
GUI cancellation event during a busy file and verifies the next file is untouched;
worker exceptions also propagate. Windows confirmation remains pending.

1. Restart the panel-launched Prism process. Use a disposable AOV copy to resize
   several color frames; check dimensions, channels and retained backups.
2. Cancel a multi-frame/multi-AOV operation; the current file finishes, remaining
   files stay unchanged, and success + failed + skipped equals total.
3. Test ID and Cryptomatte EXRs: nearest sampling, ID values, channel types and
   manifests must remain valid with the installed OpenImageIO version.
4. Test deep/multipart input: clear per-file failure, original retained. Test
   a locked destination: replacement failure, original and backup retained.
5. Attempt a second resize during the first; it must report an active action.

## Phase 8 — Installation hardening, regression pass

Primary files: `HelixAE_Integration.py`, `Integration/helixae.cmd`, `dev_panel.py`,
`dev_sync.sh`, `docs/`.

Tasks: validate ZIP/launcher/runtime prerequisites before replacing an installation; stage the
replacement with a recovery path; verify expanded launcher paths and installed hashes; document
the supported platform accurately (current macOS branch is not a working implementation);
verify UI behavior vs docs (queue-only vs immediate render); review placeholder organize
methods for reachable callers before implementing or removing; keep the established NAS
deployment workflow.

## Follow-up — Legacy protocol sweep (2026-10-02)

**Status:** implemented, locally verified and checksum-verified on the NAS;
user confirmed the workstation actions work (2026-10-02). This is a follow-up
to the original phases 0–8.

- Reveal, open-composition, folder creation, rename/move, delete, empty-folder
  cleanup and replacement paths now use shared script builders and strict JSON
  acknowledgements. Removed the duplicate `createFolderStructure` definition and
  success fallbacks that previously accepted missing or malformed responses.
- Replaced six composition actions that sent literal AppleScript through the
  ExtendScript bridge. Composition information, reveal actions and single/batch
  Kitsu synchronization now use ExtendScript JSON. FPS changes preserve start
  frame and frame count. Batch FPS callers now consume confirmed boolean results.
- Connected the context-menu composition reveal actions to their working manager
  implementations; they previously displayed unimplemented-action messages.
- Converted add-to-composition, lighting/2D/playblast import, item labels/comments
  and layer-label propagation. Imports serialize paths/names safely and clean up
  partially imported items and newly created empty folders on failure. Same task
  names across shots retain all their footage when applying label colors.
- Ctrl+Shift+Click bypass toggles now use the shared key builder and persistence
  path, fixing 2D-key drift and removing the duplicate legacy XMP writer. Shared
  set-backed bypass storage is handled correctly when toggling on and off.
- Scene-path lookups preserve apostrophes/Unicode and use the protocol `path`
  field. Numeric ID arrays are sent as numbers, including IDs originally stored
  as strings in the Python UI data.
- Removed five unused organization placeholder methods after checking callers.
  The active organization workflow remains in `executeOrganization`; label and
  comment failures now appear in its error summary, and the empty-folder count
  uses the actual returned field.
- Verification: **324 tests passed**, including 15 focused regressions executing
  generated scripts under Node with an AE DOM fixture and actual Python methods
  extracted without Qt. Python compilation, panel JavaScript syntax, ZIP/source
  parity and `git diff --check` passed. No panel payload change; reload the
  panel-launched Prism process after deployment.

**Windows checks:** on a disposable project, try composition info/reveal,
single/multi-comp Kitsu FPS/frame-range sync, adding footage to active/selected
compositions, lighting and 2D/playblast import, labels/layer colors, organization,
and Ctrl+Shift+Click bypass persistence. Native AE execution remains separate
from local fixture verification. EXR work remains deferred. Remaining unrelated
menu placeholders (multiple-footage switching, naming validation and resource
auto-categorization) and dead core AppleScript lifecycle methods are outside this
sweep; no claim is made that every feature stub has been implemented.

### Bypass display-only follow-up (2026-10-02)

Bypassing warnings does not change footage, so it no longer requests a new AE
snapshot or NAS/Kitsu scan. Context-menu bypass/unbypass, Ctrl+Shift+Click and
Check Issues bypass actions persist the edit, retain the edited bypass cache and
schedule incremental cell/count/filter updates using the existing scene snapshot.
Selection, expansion and scroll use the existing cached-render preservation path.
Updates wait until open menus/modal dialogs close. Stale-scene edits cannot alter
the current scene. Persistence still writes XMP/config; this is not a footage scan.

Local verification: **328 tests passed**, including four regressions proving
bypass/unbypass needs no inventory-refresh method and cached repaint keeps the
same snapshot. Compilation, panel syntax/ZIP parity and diff checks passed.
Windows check after Prism restart: bypass/unbypass via both tracker gestures and
menus, verify warning styling/counts/status filter change without a footage scan,
then save/reopen to confirm persistence.

### Interpretation follow-up: inactive field separation (2026-10-05)

Version replacement previously tried to restore `highQualityFieldSeparation` on
progressive footage whose `fieldSeparationType` was OFF. AE rejects that setter,
so successful replacements displayed an unnecessary preservation warning.
The replacement builder now skips that property when the restored/current field
separation is OFF; it still restores it for active field separation and retains
warnings for actual restoration failures. Two executing-script regressions cover
both cases. All **330 tests**, compilation, panel syntax/ZIP parity and diff
checks passed. Windows confirmation after Prism restart remains pending.

## Verification and release checklist

### Phase 8 implementation notes

- Added stdlib-only `Scripts/helixae_install.py`: validates the complete archive
  (required members, CRC, traversal, symlinks and case-insensitive duplicates), runtime,
  plugin script and launcher placeholders before touching the active installation.
- Stages the panel and expanded launcher in a unique same-filesystem directory.
  Prior targets are retained until both replacements and SHA-256/launcher verification
  succeed. Caught failures restore both old targets; failed recovery retains backups
  and reports their location. Process termination/power-loss recovery remains manual;
  the two-target replacement is not crash-atomic and concurrent installations are unsupported.
- `HelixAE_Integration.addIntegration` delegates to the transaction. Constructor no
  longer creates directories. Unsupported hosts are handled explicitly, and advertised
  platforms now match the Windows launcher. AE registry versions are sorted numerically
  and paths without `AfterFX.exe` are skipped. The legacy extraction entry point validates
  archives too; active installs use staging rather than that entry point.
- Launcher expansion disables delayed expansion while retaining template placeholders
  in the repository. `%`, quotes and newline-containing roots fail preflight. Real Windows
  batch execution with unusual/Unicode paths still needs runtime verification.
- The five placeholder organize methods in `ae_organize_manager.py` have no in-repository
  callers. They are retained as unused compatibility stubs rather than inventing behavior.
- Corrected render documentation to match the actual queue-only export dialog. Corrected
  resize documentation: validated resized frames replace sources with retained backups,
  rather than being separate proxy files. User confirmed the Phase 7 Cancel follow-up works.
- Ten focused installer tests exercise corrupt/missing/unsafe payloads, missing runtime,
  template expansion, successful hashes, publication failure, verification failure and
  retained backups after failed recovery. Full suite: **278 tests passing**; Python syntax,
  panel JS syntax, ZIP/source parity and diff checks passed. Deployment uses the existing
  checksum-verified NAS workflow; no panel source/ZIP change was needed.

### Signed CEP panel follow-up (2026-10-19)

- Production `Integration/helixae.zip` is now signed on `ssh helix` with ZXPSignCmd
  and a self-signed certificate stored under `C:\secure\helixae-signing\`. The release
  script stages a clean source snapshot, signs and verifies remotely, validates the
  downloaded ZIP against the live source, and only then atomically replaces the local
  ZIP. The certificate, password and signing binary are never committed or deployed.
- Added strict signature checks to `dev_panel.py` and `dev_sync.sh`, a signature-state
  policy in `helixae_install.py`/`HelixAE_Integration.addIntegration()`, and the
  `HELIXAE_ALLOW_UNSIGNED=1` development fallback that enables `PlayerDebugMode` for
  existing `CSXS.*` keys plus `CSXS.12`. Signed archives need no registry changes.
- Added `Scripts/Prism_HelixAE_Variables.py` as a compatibility alias for Prism's plugin
  metadata loader. Panel `1.0.2` declares the CEP runtime required by its AE host range.
- Local verification covers the signature parser, unsigned-development policy, registry
  helper and staging/parity checks; all 371 tests pass. The user confirmed the panel
  and plugin work on Windows after manual CEP installation and correction of the local
  Prism registration. The installed `1.0.2` panel passes Adobe signature verification.
  NAS rollout and an explicit AE round trip remain separate verification steps.

### Phase 8 Windows verification

User confirmed that updating the existing CEP integration through Prism works.
Windows failure/recovery and unusual-path fixtures below remain pending; their
transaction behavior is covered by local regression tests.

1. Restart Prism to load the installer changes; close After Effects before reinstalling
   the HelixAE integration through Prism at the existing CEP extensions path.
2. Reopen AE and the panel; check auto-launch, Project Browser, Save and Footage Tracker.
3. Use an isolated temporary installation folder for failure tests (missing/corrupt ZIP,
   missing runtime, unwritable/locked target). The old panel/launcher must survive or the
   error must identify retained recovery backups. Do not alter the live payload to test errors.
4. Verify installed panel hashes and expanded launcher paths; unusual-path batch behavior
   requires a disposable Windows fixture. Linux transaction tests do not establish this.

```bash
python -m compileall -q Scripts
node --check Integration/helixae/js/main.js
python dev_panel.py
python tests/run_tests.py
git diff --check
```

Panel changes additionally: `python dev_panel.py --build`.

After a coherent phase passes local checks, obtain authorization to commit/push and
pull the release into the production NAS checkout; reinstall the CEP integration
through Prism when required and run the phase's Windows tests. For each phase record:
changed files, fixed findings, test results,
deployment result, Windows verification status, remaining blockers.

Recommended first milestone: Phases 0–3 (runtime baseline, correct cleanup, reliable
communication, truthful operation results).

---

## Phase 0 baseline notes

Collected 2026-09-30 via read-only `ssh helix` inspection. Note: remote cmd.exe eats
PowerShell pipes — use `powershell -NoProfile -EncodedCommand` (base64 UTF-16LE).

Environment:

- Workstation user: `DimitarHelix`. After Effects **2025** installed (desktop shortcut);
  the `HKLM:\SOFTWARE\Adobe\AfterEffects` registry query returned nothing — version key
  needs a different hive/view when it next matters.
- AE was **not running** during inspection: no AfterFX/CEPHtmlEngine/Prism python
  processes, no listeners on 9888/43210.
- Prism 2 at `C:\Program Files\Prism2` (Plugins, Presets, Python313, PythonLibs,
  Scripts, Tools, prism.bat).
- Prism Python: embedded CPython **3.13.9** (`Python313\python.exe`, `python313._pth`,
  zipped stdlib).
- Qt binding: **qtpy + PySide6 + shiboken6** under `PythonLibs\Python3\PySide\`.
- `PrismUtils` lives at `C:\Program Files\Prism2\Scripts\PrismUtils`.

CEP extension installation (per-user):

- Installed at `C:\Users\DimitarHelix\AppData\Roaming\Adobe\CEP\extensions\helixae`.
- All 7 installed files are SHA256-identical to the repository `Integration/helixae.zip`
  members (index.html, mimetype, css/style.css, CSXS/manifest.xml, js/main.js,
  js/libs/CSInterface.js, META-INF/signatures.xml).
- `helixae.cmd` is installed at the extension **root** (`...\extensions\helixae.cmd`),
  matching `main.js` resolving `path.join(__dirname, '..', 'helixae.cmd')`. Content:

  ```bat
  @echo off
  set PRISM_ROOT=C:/Program Files/Prism2
  set HELIXAE_PLUGIN=Z:/Users/Dimitar/Claude/Projects/AE_Plugin/HelixAE
  "%PRISM_ROOT%/Python313/python.exe" "%HELIXAE_PLUGIN%/Scripts/HelixAE_MenuTools.py" %*
  ```

- The work PC therefore runs the plugin **directly from the NAS deployment copy** via
  `Z:`. `dev_sync.sh` deployment is the only step needed to ship Python changes to the
  workstation (restart Prism/panel required); CEP changes additionally need the
  integration reinstalled through Prism.

Resolved contracts:

- **`err_catcher` (Prism 2, `Scripts/PrismUtils/Decorators.py`)**: wraps decorated
  methods in try/except. On the Qt GUI thread with a valid `core`, exceptions are
  swallowed (written via `core.writeErrorLog`) and the decorator returns `None`.
  Off the GUI thread, or without a `core`, the exception is re-raised. Consequence:
  decorated bridge methods (e.g. `executeAppleScript`) return `None` on connection
  failure instead of raising — protocol parsers must treat `None`/empty as failure.

Still pending (require the runtime stage with AE + Prism open, not read-only):

- Prism `postSaveScene` callback argument order and save return-value handling.
- CEP embedded Node version (`process.versions`, `__dirname` behavior).
- AE registry version key location.
- Creation of the disposable AE test project for phase acceptance tests.
