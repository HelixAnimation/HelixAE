# Initial codebase scan

Initial static review: September 30, 2026. This describes the NAS snapshot imported
for local development. Python syntax and CEP JavaScript syntax pass, and the
existing CEP ZIP matches all seven panel source files. Runtime behavior still
needs validation inside Windows, Prism and After Effects.

## Architecture

HelixAE is a Prism 2 application plugin. Its 45 Python modules under `Scripts/`
are loaded by Prism, rather than installed as a standalone Python package.

| Area | Main files | Responsibility |
| --- | --- | --- |
| Prism entry point | `Scripts/Prism_HelixAE_init.py`, `HelixAE_Variables.py` | Plugin identity, capabilities, compatibility class names |
| Prism-facing facade | `Scripts/HelixAE_Functions.py` | Callbacks, save/import commands, AE lifecycle checks, lazy tracker creation |
| AE communication | `Scripts/helixae_core.py`, `Integration/helixae/js/main.js` | Python TCP client, CEP Node server, ExtendScript evaluation |
| UI process launcher | `Integration/helixae.cmd`, `Scripts/HelixAE_MenuTools.py` | Launch Prism Python, Windows single-instance mutex, command forwarding |
| Installer | `Scripts/HelixAE_Integration.py` | Install CEP ZIP, expand launcher template paths |
| Tracker | `Scripts/helixae_footage_tracker.py`, `Scripts/footage_tracker/tracker.py` | Lazy wrapper and tracker orchestration |
| Footage tree | `tree_operations.py`, `tree_operations_core.py`, `tree_renderer.py`, `hierarchy_builder.py`, `data_parser.py` | Query and present footage, grouping, version/status display, bypass state |
| Media and compositions | `ae_operations.py`, `import_shots.py`, `import_dialog.py`, `comp_manager.py`, `shot_switcher.py`, `context_menu*.py` | Import/update footage, manage compositions and shot workflows |
| Caching and Kitsu | `version_cache_manager.py`, `kitsu_integration.py`, `ae_kitsu.py` | Persistent render-version cache and cached production metadata |
| Rendering | `Scripts/helixae_export.py`, `Scripts/helixae_ui.py` | Output modules, Prism paths/versions, render/save workflows |
| Image processing | `image_resizer.py`, `context_menu_image_resize.py`, `lib/` | EXR/AOV resizing and vendored binary dependencies |

Unqualified tracker filenames in the table live under `Scripts/footage_tracker/`.

### Communication flow

```text
CEP panel button
  -> installed helixae.cmd
  -> Prism Python / HelixAE_MenuTools.py
  -> existing Prism UI process on localhost:43210 (when already running)
  -> plugin operation
  -> CEP Node bridge on 127.0.0.1:9888
  -> After Effects ExtendScript
  -> null-terminated result back to Python
```

The two TCP ports serve different purposes. Python clients already accumulate
response chunks until a null byte; preserve that behavior for large AE results.
Panel installation uses `Integration/helixae.zip`, so updating source alone does
not update the installed panel.

### State locations

- UI geometry/settings: Qt `QSettings` on the work PC.
- Version cache: `.prism_footage_cache.json` under the active Prism project,
  with a Prism temporary-directory fallback.
- Import cache: project `00_Pipeline/AE_cache/footage_cache.json`.
- Save/export metadata: archive/version information alongside project output.

These project/user state locations are separate from the plugin source.

## Prioritized findings

### 1. Fix panel process launching first

**Confirmed source defect:** `Integration/helixae/js/main.js:69–94` declares
`const child` inside each platform branch, then accesses `child` outside those
blocks. That causes a `ReferenceError` after the spawn call succeeds, preventing
normal stdout/error handling. `node --check` cannot detect this runtime error.

The Windows `.cmd` launch with `shell: false` also needs verification against
CEP's Node version. The macOS branch uses `%` as if it were Python string
formatting; JavaScript treats it as remainder arithmetic.

Recommended scope: repair the launcher, validate Windows command/path handling,
rebuild/reinstall the CEP integration and test panel commands.

### 2. Frame incoming AE bridge requests

**Confirmed protocol weakness:** `main.js:11–23` evaluates each TCP `data` event
as a complete script. TCP does not preserve message boundaries. A large script
can arrive in multiple chunks and be evaluated as fragments. The Python client
currently sends raw script bytes, so a framing fix must update both ends.

Keep null-terminated responses and add a clear request boundary, accumulation,
and consistent error handling. Also handle server startup errors such as an
occupied port. The current listener has no explicit loopback address.

### 3. Make UI-process startup ordering robust

**Potential race identified from source:** `HelixAE_MenuTools.py:71` starts its
listener before importing Qt and creating `commandHandler`. A second command
during startup can reach code that references globals not initialized yet.
The Windows mutex is acquired before the listener is ready, so a second launcher
can also encounter connection refusal. Validate repeated quick clicks during
startup, then queue commands or defer readiness until initialization completes.

### 4. Profile tracker refresh before changing its structure

`tracker.py` calls `loadFootageData()` before showing the dialog. There are
already timing logs and cache layers; use those to measure where opening and
refreshing large projects spend time. AE round trips, NAS scans and Kitsu calls
are useful profiling targets. This is an investigation priority, not a measured
performance defect from this scan.

### 5. Strengthen shared cache writes

`version_cache_manager.py:108–129` writes the shared project cache directly using
`open(..., 'w')`. Its lock coordinates threads in one instance, not separate
workstations/processes. A temporary-file-and-replace strategy would reduce
partial-file exposure; concurrent update handling needs a separate decision.
The import cache already uses a temporary file and is a useful reference.

## Development constraints

- Preserve Prism's flat imports, entry class and compatibility aliases.
- The launcher selects Prism `Python313`; image processing deliberately checks
  vendored Python 3.11 libraries. Validate actual runtimes before changing either.
- No automated runtime test suite or lint configuration was present in the
  imported repository. Syntax checks alone cannot validate Qt/Prism/AE behavior.
- Improve logging and large-module boundaries incrementally when touching a
  feature, after stabilizing launching and bridge communication.

Recommended first improvement: **panel launching and bridge reliability**, then
target the artist workflow that needs the most attention.
