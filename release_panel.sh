#!/usr/bin/env bash
# Sign the CEP panel on the Windows signing host and publish it atomically.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
HOST="${HELIXAE_SIGNING_HOST:-helix}"
SIGNING_ROOT="${HELIXAE_SIGNING_ROOT:-C:/secure/helixae-signing}"
REMOTE_WORK="$SIGNING_ROOT/work/$$"
NO_TIMESTAMP=0
TEMP=''
REMOTE_WORK_CREATED=0

usage() {
    printf 'Usage: bash release_panel.sh [--no-timestamp|--help]\n'
    printf 'Signs Integration/helixae.zip on %s and verifies it before replacing the local ZIP.\n' "${HELIXAE_SIGNING_HOST:-helix}"
    printf 'Use --no-timestamp only when the timestamp server is unavailable.\n'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-timestamp) NO_TIMESTAMP=1 ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

for tool in ssh scp iconv base64 tar mktemp install; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'Required tool is missing: %s\n' "$tool" >&2
        exit 1
    }
done

ps_command() {
    local command="$1"
    local encoded
    encoded="$(printf '%s' "$command" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)"
    ssh "$HOST" "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded"
}

cleanup() {
    if [[ -n "$TEMP" ]]; then
        rm -rf -- "$TEMP"
    fi
    rm -f -- "$ROOT/Integration/helixae.zip.tmp"
    if [[ "$REMOTE_WORK_CREATED" -eq 1 ]]; then
        ps_command "Remove-Item -LiteralPath '$REMOTE_WORK' -Recurse -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if "$PYTHON" "$ROOT/dev_panel.py" >/dev/null 2>&1; then
    printf 'Panel source already matches the signed Integration/helixae.zip; nothing to sign.\n'
    exit 0
fi

TEMP="$(mktemp -d)"
BEFORE="$("$PYTHON" "$ROOT/dev_panel.py" --hash)"
"$PYTHON" "$ROOT/dev_panel.py" --stage "$TEMP/panel" >/dev/null
AFTER="$("$PYTHON" "$ROOT/dev_panel.py" --hash)"
if [[ "$BEFORE" != "$AFTER" ]]; then
    printf 'Panel source changed while staging; aborting.\n' >&2
    exit 1
fi

tar -czf "$TEMP/panel.tar.gz" -C "$TEMP/panel" .

printf 'Preparing signing workspace on %s...\n' "$HOST"
ps_command "New-Item -ItemType Directory -Force -Path '$REMOTE_WORK/src' | Out-Null; New-Item -ItemType Directory -Force -Path '$REMOTE_WORK/tools' | Out-Null"
REMOTE_WORK_CREATED=1
scp -q "$TEMP/panel.tar.gz" "$HOST:$REMOTE_WORK/panel.tar.gz"
scp -q "$ROOT/tools/sign_panel.ps1" "$HOST:$REMOTE_WORK/tools/sign_panel.ps1"

ps_command "& tar -xzf '$REMOTE_WORK/panel.tar.gz' -C '$REMOTE_WORK/src'"
ps_command "if (-not (Test-Path -LiteralPath '$REMOTE_WORK/src/index.html')) { throw 'Panel extraction failed' }"

SIGN_ARGS="-InputDirectory '$REMOTE_WORK/src' -OutputZxp '$REMOTE_WORK/helixae.zxp' -SigningRoot '$SIGNING_ROOT'"
if [[ "$NO_TIMESTAMP" -eq 1 ]]; then
    SIGN_ARGS="$SIGN_ARGS -NoTimestamp"
fi

printf 'Signing on %s...\n' "$HOST"
ps_command "& '$REMOTE_WORK/tools/sign_panel.ps1' $SIGN_ARGS"

scp -q "$HOST:$REMOTE_WORK/helixae.zxp" "$TEMP/helixae.zip"

# Validate the downloaded package against the live source before publishing it.
"$PYTHON" "$ROOT/dev_panel.py" --archive "$TEMP/helixae.zip"

install -m 0644 "$TEMP/helixae.zip" "$ROOT/Integration/helixae.zip.tmp"
mv -f -- "$ROOT/Integration/helixae.zip.tmp" "$ROOT/Integration/helixae.zip"
"$PYTHON" "$ROOT/dev_panel.py"

printf 'Signed and verified Integration/helixae.zip.\n'
printf 'Next: python tests/run_tests.py && git diff --check\n'
