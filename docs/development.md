# Local development and NAS deployment

## Windows-only setup verification (2026-10-19)

At the user's request, the current plugin was installed locally on `helix`, without
updating the NAS or performing Git operations. Prism's HelixAE registration and the
installed CEP launcher point to
`C:\Users\DimitarHelix\AppData\Local\HelixAE\plugin\HelixAE`.
Previous registration/panel backups are under the sibling `HelixAE\backups` folder.
This workstation now uses that local snapshot until its registration is changed again.
Prism discovers plugins by their directory basename: the registered root must end
in `HelixAE`, not a timestamp. The initial timestamp-root registration was corrected
after Prism reported that the app plugin could not be found. The installed launcher
and registration now use the same local root, and Prism's actual `searchPlugins`
method confirms discovery. Manual reinstalls from an older Prism process can restore
the NAS launcher path; restart Prism before reinstalling again.

Panel v1.0.2 adds the previously missing `RequiredRuntimeList` (`CSXS` 9.0, matching
the minimum AE 16 host). The package and installed directory pass Adobe signature
verification; installed hashes and imports under Prism's Python were verified.
The full local suite passes 371 tests. The user subsequently confirmed the panel
and plugin work after manual CEP installation and correction of the Prism registration.
This confirmation used the Windows-local plugin snapshot; production NAS rollout
still needs verification after the checkout is updated.

## Locations

- Development copy: `/mnt/storage/OpenCodeProjects/CG/HelixAE`
- Production plugin path: `\\nassk\Renders\Programs\PrismPlugins\HelixAE`
- NAS checkout: `nassk:/volume1/Renders/Programs/PrismPlugins/HelixAE`

Edit and verify the local copy. Production updates are committed and pushed locally,
then pulled into the NAS checkout. Each Git operation and NAS update requires explicit
authorization; there is no automatic sync. The repository origin is
`https://github.com/HelixAnimation/HelixAE.git`.

## Integration installation

HelixAE currently supports **Windows**. Reinstall through Prism after restarting Prism
to load installer changes. Close the AE panel/After Effects before reinstalling, then
reopen it. The installer checks the ZIP, launcher template, Prism `Python313/python.exe`
and plugin `Scripts/HelixAE_MenuTools.py` before replacing either installed target.
It stages files beside the installation, checks their hashes, retains the previous panel
and launcher during replacement, and verifies the published files. A caught installation
failure restores the previous targets. If recovery fails, the error gives the retained
`.helixae-install-*` backup location for manual recovery; do not delete that folder.

Replacement of the panel folder and launcher is sequential, not an atomic pair.
A killed process or power loss may leave a staging/backup directory requiring recovery.
Install one update at a time. No elevation fallback is used: select a writable per-user
CEP extensions directory. Launcher paths containing `%`, quotes or newlines are rejected;
spaces, ampersands and exclamation marks are preserved without delayed expansion.

## CEP panel signing

Production releases use a signed `Integration/helixae.zip`. The installer rejects a
missing, empty or malformed `META-INF/signatures.xml`; a signed archive needs no
`PlayerDebugMode` registry changes. For deliberate unsigned development only, set
`HELIXAE_ALLOW_UNSIGNED=1` before reinstalling. That explicit fallback writes
`PlayerDebugMode=1` for existing `CSXS.*` keys and `CSXS.12`. Do not use it on artist
machines.

One-time setup on the Windows signing host:

1. Copy `tools/setup_signing.ps1` to `ssh helix` and run it with PowerShell
   `-ExecutionPolicy Bypass -File`.
2. It downloads the pinned ZXPSignCmd 4.1.3 x64 build, creates
   `C:\secure\helixae-signing`, restricts that folder to the current Windows user,
   generates a random password file and a 10-year self-signed `helixae.p12`, then
   smoke-signs and verifies a disposable package.
3. Back up `helixae.p12` and `password.txt` securely. Never add either to Git, the NAS
   deployment or documentation.

Sign the panel after any change under `Integration/helixae/`:

```bash
bash release_panel.sh
```

The script stages a clean panel snapshot, transfers it to `ssh helix`, signs and verifies
it remotely, checks source parity and the signature before replacing the local ZIP, and
leaves the previous ZIP in place on failure. If the panel source already matches the
signed ZIP, it exits without signing. `--no-timestamp` is available when the timestamp
server is unreachable. `python dev_panel.py --build` is only for unsigned local
development and refuses to overwrite a signed ZIP without `--allow-unsigned`.

`Integration/helixae/META-INF/signatures.xml` must not exist in the source tree; the
signature is generated into the ZIP. Git delivers removal of the old tracked source
placeholder when the release is pulled. Do not hand-edit `META-INF/signatures.xml`.
Panel v1.0.3 preserves CEP source bytes using `.gitattributes` (`Integration/helixae/**
text eol=lf`), so Windows/Linux checkout settings cannot change source/ZIP parity.

## Daily workflow

1. Make and review changes locally.
2. If anything under `Integration/helixae/` changed, bump
   `ExtensionBundleVersion` and the extension `Version` in
   `Integration/helixae/CSXS/manifest.xml`, then sign the panel:

   ```bash
   bash release_panel.sh
   ```

3. Run local checks:

   ```bash
   python -m compileall -q Scripts
   node --check Integration/helixae/js/main.js
   python dev_panel.py
   python tests/run_tests.py
   git diff --check
   ```

4. When explicitly authorized, commit and push the reviewed changes, including the
   signed ZIP for panel changes. Separately pull the release into the NAS checkout.
5. Register `\\nassk\Renders\Programs\PrismPlugins\HelixAE` in artist Prism settings.
   Restart Prism before reinstalling the integration so the launcher uses that NAS
   root. Reload the affected application and smoke-test on the work PC.

Python-only changes do not require re-signing; update the checkout and restart Prism.
Artists do not need the signing certificate or signing tools: Prism installs the
already signed ZIP from the checkout.

### Legacy direct-copy helper

`dev_sync.sh` remains available only for an explicitly requested direct-copy deployment.
It is not the production commit/push/pull workflow and must not run automatically.

The deployment command runs Python compilation, Node syntax checking, the CEP
signature check, and a byte-for-byte comparison of panel source against
`Integration/helixae.zip`. It requires Bash, Python 3.8+, Node, tar, sha256sum, and
working `ssh nassk` access. The NAS needs tar, sha256sum and mktemp, but no Git or
Python for deployment. Synology's rsync rejected transfers in this setup, so deployment
uses tar over SSH. `dev_sync.sh --allow-unsigned` is for deliberate local development
builds only.

An explicit list of project roots is transferred, including vendored runtime
libraries (and their `.pyd` files). Git metadata, bytecode caches, CEP node_modules,
and NAS/desktop metadata are excluded. Add new top-level source folders to the
`files` array in `dev_sync.sh` when needed.

The archive is fully uploaded and checksum-checked before extraction; every
deployed regular file is then checked against its SHA-256 digest. This is an
in-place deployment, not an atomic whole-project switch. Deploy between active
plugin operations. An interrupted extraction may leave mixed file versions;
rerun deployment to restore a complete copy.

Matching NAS files are overwritten. NAS-only files and settings are retained;
deletions and renames require deliberate cleanup of the old NAS paths.
Do not edit both copies independently. Bring any work-PC source changes back
to the local copy before deploying again.

`--dry-run` runs the checks, checks destination access and lists included roots;
it does not produce a per-file difference report or write to the NAS.

## Picking up changes on the work PC

- **Python:** restart the HelixAE/Prism UI process; closing only its window may
  leave the single-instance process alive. Ensure Prism's plugin path is the NAS
  path above.
- **CEP HTML/CSS/JavaScript or command template:** reinstall the After Effects
  integration through Prism, then restart After Effects. Prism extracts the signed
  `Integration/helixae.zip` into the local Adobe CEP extensions folder and expands
  the command template's `PLUGINROOT` and `PRISMROOT` placeholders.
- **Smoke test:** open the panel, launch Footage Tracker, refresh footage and test
  the feature that changed. The AE bridge uses port `9888`; Prism UI forwarding
  uses `43210`.

Verify the installed signature when diagnosing a panel that is listed but does not
open:

```bat
dir "%APPDATA%\Adobe\CEP\extensions\helixae\META-INF\signatures.xml"
C:\secure\helixae-signing\ZXPSignCmd.exe -verify "%APPDATA%\Adobe\CEP\extensions\helixae"
```

Also check for a second `com.helix.ae` bundle, confirm the installed layout is
`helixae\index.html`, and inspect the CEP log under `%TEMP%` for the running AE
version. Signing is necessary but not sufficient: the panel must still load in
After Effects and complete an AE round trip. Use `PlayerDebugMode` only for
unsigned development builds.

OpenCode is instructed in `AGENTS.md` to verify locally and wait for explicit
authorization before Git operations or NAS updates. Changes become available on
the NAS after the production checkout is updated; application reload and CEP
reinstallation remain separate steps.

## Git and line endings

The initial NAS working copy included an uncommitted menu-port change from
`65432` to `43210` and an untracked `AGENTS.md`; both were preserved.
`.gitattributes` lets Git normalize Windows CRLF files for comparisons without
rewriting the copied source or vendored libraries. Command templates retain CRLF
on checkout and shell scripts use LF.
