#!/usr/bin/env bash
# Deploy this working tree to the existing NAS plugin, without deleting NAS-only files.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_ROOT='/volume1/Renders/Users/Dimitar/Claude/Projects/AE_Plugin/HelixAE'
PYTHON="${PYTHON:-python3}"
MODE="${1:-}"
if [[ $# -gt 1 || ( -n "$MODE" && "$MODE" != '--dry-run' && "$MODE" != '--help' ) ]]; then
    printf 'Usage: bash dev_sync.sh [--dry-run|--help]\n' >&2
    exit 2
fi
if [[ "$MODE" == '--help' ]]; then
    printf 'Usage: bash dev_sync.sh [--dry-run]\nChecks syntax and CEP packaging, then copies to nassk and verifies SHA-256 hashes.\nNAS-only files are retained. Git metadata and caches are not deployed.\n'
    exit 0
fi

"$PYTHON" -m compileall -q "$ROOT/Scripts"
node --check "$ROOT/Integration/helixae/js/main.js"
"$PYTHON" "$ROOT/dev_panel.py"

# Explicit roots keep local environments, credentials and Git metadata out of deployment.
files=(Integration Presets Resources Scripts UserInterfaces lib docs
       __init__.py README.md mkdocs.yml AGENTS.md .gitignore .gitattributes
       dev_sync.sh dev_panel.py)
exclude=(--exclude=__pycache__ --exclude='*.pyc' --exclude='*.pyo'
         --exclude=@eaDir --exclude=.DS_Store --exclude=Thumbs.db
         --exclude=desktop.ini --exclude=node_modules --exclude=.debug)

tar "${exclude[@]}" -cf /dev/null -C "$ROOT" "${files[@]}"
ssh nassk "test -d '$REMOTE_ROOT' && test -f '$REMOTE_ROOT/Scripts/Prism_HelixAE_init.py' && test -w '$REMOTE_ROOT' && command -v tar sha256sum mktemp >/dev/null"
if [[ "$MODE" == '--dry-run' ]]; then
    printf 'Checks passed. Would copy these roots to nassk:%s:\n' "$REMOTE_ROOT"
    printf '  %s\n' "${files[@]}"
    printf 'No NAS files changed. Deployment overwrites matching files and retains NAS-only files.\n'
    exit 0
fi

TEMP="$(mktemp -d)"
REMOTE_TEMP=''
cleanup() {
    rm -rf -- "$TEMP"
    if [[ -n "$REMOTE_TEMP" ]]; then
        ssh nassk "rm -rf -- '$REMOTE_TEMP'" || true
    fi
}
trap cleanup EXIT

# Finish creating and transferring the archive before touching live files.
tar "${exclude[@]}" -czf "$TEMP/payload.tar.gz" -C "$ROOT" "${files[@]}"
"$PYTHON" - "$TEMP/payload.tar.gz" "$TEMP/checksums" <<'PY'
import hashlib
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as archive, open(sys.argv[2], "w") as output:
    for entry in archive:
        if entry.isfile():
            if "\n" in entry.name or "\\" in entry.name:
                raise SystemExit("Unsupported deployment filename: " + repr(entry.name))
            digest = hashlib.sha256(archive.extractfile(entry).read()).hexdigest()
            output.write(digest + "  " + entry.name + "\n")
PY
REMOTE_TEMP="$(ssh nassk "mktemp -d '$REMOTE_ROOT/../.helixae-deploy.XXXXXXXX'")"
case "$REMOTE_TEMP" in
    "$REMOTE_ROOT/../.helixae-deploy."*) ;;
    *) printf 'Unexpected staging path: %s\n' "$REMOTE_TEMP" >&2; REMOTE_TEMP=''; exit 1 ;;
esac
ssh nassk "cat > '$REMOTE_TEMP/payload.tar.gz'" < "$TEMP/payload.tar.gz"
ssh nassk "cat > '$REMOTE_TEMP/checksums'" < "$TEMP/checksums"
DIGEST="$(sha256sum "$TEMP/payload.tar.gz")"
DIGEST="${DIGEST%% *}"
ssh nassk "set -eu
printf '%s  %s\n' '$DIGEST' '$REMOTE_TEMP/payload.tar.gz' | sha256sum -c -
tar --no-same-owner --no-same-permissions --no-overwrite-dir -xzf '$REMOTE_TEMP/payload.tar.gz' -C '$REMOTE_ROOT'
cd '$REMOTE_ROOT'
sha256sum -c '$REMOTE_TEMP/checksums' > '$REMOTE_TEMP/verification.log' 2>&1 || { cat '$REMOTE_TEMP/verification.log'; exit 1; }"
printf 'Deployed and checksum-verified: nassk:%s\n' "$REMOTE_ROOT"
printf 'Reload Prism for Python changes. For panel changes, reinstall the integration in Prism and restart AE.\n'
