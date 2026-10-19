# HelixAE Agent Notes

## Local Development and NAS Deployment

- Develop in `/mnt/storage/OpenCodeProjects/CG/HelixAE`. The live NAS copy is `/volume1/Renders/Users/Dimitar/Claude/Projects/AE_Plugin/HelixAE` on `ssh nassk`.
- After completing and verifying a requested change, run `bash dev_sync.sh` to deploy it and report the result. Do not auto-sync unfinished saves. Run `bash dev_sync.sh --dry-run` to check prerequisites without writing to the NAS.
- Git history is maintained locally; deployment excludes `.git`. Preserve existing NAS-only files. Source removals/renames require deliberate cleanup of the corresponding old NAS files because deployment does not delete them.
- For panel changes, run `python dev_panel.py --build` before deployment. The deploy command checks Python/JS syntax and ZIP/source parity, and verifies deployed file hashes.
- See `docs/development.md` for the workflow and reload requirements.

## Durable Implementation Rules

- After Effects responses must be parsed as JSON via dedicated protocol helpers (see `Scripts/footage_tracker/comp_cleanup.py`); never use `eval()` or delimiter-split parsing on AE responses.
- All new AE round trips must use `Scripts/helixae_protocol.py` (stdlib-only, top level): `js_string()` for every Python string embedded into ExtendScript (paths, names, AOVs, templates), the `build_*` script builders for queries/mutations, and the strict `parse_*` parsers (which treat `None`/empty/non-JSON as failure). Mutation builders confirm success explicitly and clean up partially created AE objects on failure; do not report success from a fire-and-forget script.
- ExtendScript that returns JSON can rely on the json2 polyfill injected by `HelixAECore.executeAppleScript()` and `HelixAE_Functions.sendCmd()` (triggered by the literal `JSON.` in the script; idempotent).
- Mutating AE operations must distinguish success/failure/empty outcomes; an empty or `None` bridge response is a failure, never success.
- Prism's `err_catcher` swallows exceptions on the GUI thread and returns `None` (Prism 2, `Scripts/PrismUtils/Decorators.py`); do not rely on exceptions propagating out of decorated methods.
- Keep AE protocol/decision logic in stdlib-only modules so it stays unit-testable without Prism/Qt; load them by file path in tests to skip the Qt-importing package `__init__`. Wire-format helpers live in `Scripts/helixae_bridge.py` (top level because `HelixAE_MenuTools.py` imports it before Prism is on `sys.path`); AE-response protocol helpers live under `Scripts/footage_tracker/`.
- Both TCP bridges are framed via `Scripts/helixae_bridge.py`: 9888 requests and responses are null-terminated (one request per connection; premature EOF is a transport failure, never an empty result); 43210 commands are newline-terminated with ok/error acknowledgement and a `KNOWN_COMMANDS` allowlist. Panel JS and Python must be deployed together (reinstall the CEP integration through Prism after a bridge change).
- `HelixAE_MenuTools.py` is launched standalone by `helixae.cmd` under Prism's embedded Python, which runs isolated (`python313._pth`: no site, script dir not on `sys.path`). It must insert its own Scripts directory into `sys.path` before importing sibling plugin modules.
- Regression tests live in `tests/` (local only, never deployed to the NAS); run `python tests/run_tests.py` and add a focused test for every fixed bug.
- Windows verification is separate from local checks: prefer read-only `ssh helix` inspection (PowerShell via `-EncodedCommand` because remote cmd eats pipes) before any runtime smoke test, which needs AE + Prism open and a disposable project.
- The improvement program is tracked in `docs/improvement-plan.md`; update its phase status table and phase notes when a phase advances.

## Runtime Shape

- Tracker background preparation is plugin-owned (`footage_tracker/refresh_controller.py`),
  with worker-only plain-data operations in `Scripts/helixae_refresh.py`. Never call
  Prism Kitsu manager/login methods or access Qt widgets from these workers. Capture
  authentication/project state on the GUI thread, use an independent HTTP session
  with explicit timeouts, and generation-check results before touching current UI.
  Keep AE actual values separate from published metadata, and preserve the existing
  independent Footage/Kitsu refresh controls.

- This is a Prism 2 application plugin, not a standalone Python package. Prism loads `Scripts/Prism_HelixAE_init.py`; keep its `Prism_HelixAE` class and compatibility aliases intact.
- Prism puts `Scripts/` on `sys.path`, so top-level modules intentionally use flat imports such as `from HelixAE_Variables import ...`. Do not convert these to package-relative imports without testing inside Prism.
- `Scripts/HelixAE_Functions.py` is the Prism-facing facade. It lazily creates the footage tracker through `Scripts/helixae_footage_tracker.py`; the implementation is split under `Scripts/footage_tracker/`.
- `Integration/helixae/js/main.js` is the CEP/Node bridge. It evaluates ExtendScript in After Effects on TCP `9888`; responses are terminated with a null byte. Preserve the terminator and chunked receive loops because AE responses can exceed one socket read.
- TCP `43210` in `Scripts/HelixAE_MenuTools.py` is separate: it forwards panel commands to the single Prism UI process guarded by the Windows mutex. (Was `65432`, moved out of Hyper-V's dynamic excluded port range.)

## Integration Packaging

- Integration updates use the stdlib-only `Scripts/helixae_install.py` transaction: preflight the payload/runtime, stage, retain previous targets, publish and verify before deleting backups. Keep failed-recovery backups and report their path. Do not restore delete-first installation or imply the two-target swap is crash-atomic.

- `HelixAE_Integration.addIntegration()` installs the CEP panel by extracting `Integration/helixae.zip`; it does not copy `Integration/helixae/` directly. Any panel change must be made in the source directory and mirrored into the ZIP with the same root layout (`index.html`, `CSXS/`, `js/`, etc.).
- `Integration/helixae.cmd` is an installation template. Prism replaces `PRISMROOT` and `PLUGINROOT` during installation; do not replace these placeholders in the repository copy.
- The command template currently launches Prism's `Python313/python.exe`, while image resizing deliberately searches the vendored `lib/python311/site-packages` first. Treat those paths as separate runtime and binary-dependency concerns rather than "fixing" the version mismatch casually.
- `lib/` contains vendored OpenImageIO/NumPy runtime files, not project source. Avoid broad formatting, searches, or dependency updates there.

## Verification

- Python syntax: `python -m compileall -q Scripts`; CEP JavaScript: `node --check Integration/helixae/js/main.js`; regression tests: `python tests/run_tests.py` (stdlib only, no Prism/Qt needed).
- Integrated behavior requires Windows, Prism, After Effects, and the installed CEP extension. After bridge changes, reinstall the integration through Prism so the updated ZIP reaches the Adobe CEP extensions directory, then smoke-test the affected panel command and an AE round trip on port `9888`.
- Keep artist-facing behavior documented under `docs/`; `mkdocs.yml` is the navigation source of truth when adding or moving pages.
