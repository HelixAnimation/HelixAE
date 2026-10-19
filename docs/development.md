# Local development and NAS deployment

## Locations

- Development copy: `/mnt/storage/OpenCodeProjects/CG/HelixAE`
- Work PC plugin path: `\\nassk\Renders\Users\Dimitar\Claude\Projects\AE_Plugin\HelixAE`
- SSH destination: `nassk:/volume1/Renders/Users/Dimitar/Claude/Projects/AE_Plugin/HelixAE`

Edit the local copy. The NAS is the deployment copy used by Prism on the work PC.
The original Git history and origin (`https://github.com/HelixAnimation/HelixAE.git`)
were copied locally. Commits and pushes are separate from deployment.

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

## Daily workflow

1. Make and review changes locally.
2. If anything under `Integration/helixae/` changed, rebuild its installer ZIP:

   ```bash
   python dev_panel.py --build
   ```

3. Preview deployment or deploy:

   ```bash
   bash dev_sync.sh --dry-run
   bash dev_sync.sh
   ```

4. Reload the affected application and smoke-test on the work PC.

The deployment command runs Python compilation, Node syntax checking, and a
byte-for-byte comparison of panel source against `Integration/helixae.zip`.
It requires Bash, Python 3.8+, Node, tar, sha256sum, and working `ssh nassk` access.
The NAS needs tar, sha256sum and mktemp, but no Git or Python for deployment.
Synology's rsync rejected transfers in this setup, so deployment uses tar over SSH.

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
  integration through Prism, then restart After Effects. Prism extracts
  `Integration/helixae.zip` into the local Adobe CEP extensions folder and expands
  the command template's `PLUGINROOT` and `PRISMROOT` placeholders.
- **Smoke test:** open the panel, launch Footage Tracker, refresh footage and test
  the feature that changed. The AE bridge uses port `9888`; Prism UI forwarding
  uses `43210`.

OpenCode is instructed in `AGENTS.md` to deploy after each completed, verified
change. There is no background save watcher. Changes become available on the NAS
when deployment completes; application reload and CEP reinstallation remain
separate steps.

## Git and line endings

The initial NAS working copy included an uncommitted menu-port change from
`65432` to `43210` and an untracked `AGENTS.md`; both were preserved.
`.gitattributes` lets Git normalize Windows CRLF files for comparisons without
rewriting the copied source or vendored libraries. Command templates retain CRLF
on checkout and shell scripts use LF.
