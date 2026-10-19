#!/usr/bin/env python3
"""Check, stage, or rebuild the CEP archive Prism installs (standard library only)."""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Integration" / "helixae"
ARCHIVE = ROOT / "Integration" / "helixae.zip"
SCRIPT_DIR = ROOT / "Scripts"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import helixae_install  # noqa: E402


IGNORED_DIRS = {"node_modules", "__pycache__", "@eaDir", ".git"}
IGNORED_NAMES = {".debug", ".DS_Store", "Thumbs.db"}


def panel_files(source=SOURCE):
    source = Path(source)
    if not source.is_dir():
        raise ValueError("Panel source directory does not exist: %s" % source)

    files = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        name = relative.as_posix()
        if path.is_symlink():
            raise ValueError("Unsupported symlink in panel source: %s" % name)
        if not path.is_file():
            continue
        if name == helixae_install.SIGNATURE_MEMBER:
            raise ValueError(
                "Panel source must not contain %s; release_panel.sh generates it."
                % helixae_install.SIGNATURE_MEMBER
            )
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        if path.name in IGNORED_NAMES:
            continue
        files[name] = path
    return files


def validate_required(files):
    missing = sorted(helixae_install.REQUIRED_FILES - set(files))
    if missing:
        raise ValueError("Missing panel file(s): %s" % ", ".join(missing))


def source_hash(files):
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(Path(files[name]).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def stage_panel_files(files, destination):
    destination = Path(destination)
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    destination.mkdir(parents=True)
    for name, path in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return destination


def archive_signature_state(archive):
    if not Path(archive).exists():
        return "missing"
    try:
        return helixae_install.archive_signature_state(archive)
    except (OSError, zipfile.BadZipFile):
        return "malformed"


def check_archive(archive, files, allow_unsigned=False):
    files_by_name = helixae_install.archive_files(archive)
    state = helixae_install.signature_state_from_files(files_by_name)
    if state != "signed":
        if state == "unsigned" and allow_unsigned:
            pass
        else:
            raise ValueError(
                "CEP ZIP signature is %s. Run bash release_panel.sh to sign the panel."
                % state
            )

    panel_names = set(files)
    archive_names = set(files_by_name) - {helixae_install.SIGNATURE_MEMBER}
    missing = sorted(panel_names - archive_names)
    extra = sorted(archive_names - panel_names)
    if missing or extra:
        details = []
        if missing:
            details.append("missing: %s" % ", ".join(missing))
        if extra:
            details.append("extra: %s" % ", ".join(extra))
        raise ValueError("CEP ZIP does not match panel source (%s)." % "; ".join(details))
    for name, path in files.items():
        source_data = Path(path).read_bytes()
        archive_data = files_by_name[name]
        if name == "mimetype":
            # ZXPSignCmd normalizes the mimetype member by dropping CRLF.
            source_data = source_data.rstrip(b"\r\n")
            archive_data = archive_data.rstrip(b"\r\n")
        if archive_data != source_data:
            raise ValueError("CEP ZIP differs from panel source: %s" % name)
    return state


def verify_signature(archive):
    command = (
        os.environ.get("ZXPSIGNCMD")
        or shutil.which("ZXPSignCmd")
        or shutil.which("ZXPSignCmd.exe")
    )
    if not command:
        raise ValueError(
            "ZXPSignCmd is not available locally; release_panel.sh verifies on the signing host."
        )
    result = subprocess.run(
        [command, "-verify", str(archive)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        raise ValueError("ZXPSignCmd verification failed: %s" % (output or "unknown error"))


def build_archive(archive, files, allow_unsigned=False):
    archive = Path(archive)
    if archive.exists():
        state = archive_signature_state(archive)
        if state == "signed" and not allow_unsigned:
            raise ValueError(
                "Refusing to overwrite a signed ZIP. Run bash release_panel.sh, "
                "or pass --allow-unsigned for a development build."
            )
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=archive.parent, suffix=".zip", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as package:
            for name, path in files.items():
                package.write(path, name)
        temporary.chmod(0o644)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE, help="Panel source directory")
    parser.add_argument("--archive", type=Path, default=ARCHIVE, help="CEP ZIP to inspect")
    parser.add_argument("--build", action="store_true", help="Rebuild an unsigned development ZIP")
    parser.add_argument("--stage", metavar="DIR", help="Copy the clean panel source to DIR")
    parser.add_argument("--hash", action="store_true", help="Print the panel source hash")
    parser.add_argument(
        "--signature-state",
        action="store_true",
        help="Print signed/unsigned/empty/malformed/missing and exit",
    )
    parser.add_argument(
        "--verify-signature",
        action="store_true",
        help="Run ZXPSignCmd -verify after the local checks",
    )
    parser.add_argument(
        "--allow-unsigned",
        action="store_true",
        help="Allow a missing signature for local development only",
    )
    args = parser.parse_args(argv)

    special = [args.stage is not None, args.hash, args.signature_state, args.verify_signature]
    if args.build and any(special):
        parser.error("--build cannot be combined with stage/hash/signature-state/verify")
    if sum(special) > 1:
        parser.error("choose only one of --stage, --hash, --signature-state, --verify-signature")
    return parser, args


def main(argv=None):
    parser, args = parse_args(argv)
    try:
        if args.signature_state:
            state = archive_signature_state(args.archive)
            print(state)
            return 0 if state == "signed" else 1

        files = panel_files(args.source)
        validate_required(files)

        if args.hash:
            print(source_hash(files))
            return 0

        if args.stage is not None:
            stage_path = Path(args.stage).resolve()
            if stage_path in (Path("/"), ROOT.resolve(), Path(args.source).resolve()):
                raise ValueError("Refusing to stage into %s" % stage_path)
            stage_panel_files(files, stage_path)
            print("Staged %d panel files in %s." % (len(files), stage_path))
            return 0

        if args.build:
            build_archive(args.archive, files, args.allow_unsigned)
            print(
                "Rebuilt unsigned %s. Reinstall only with "
                "HELIXAE_ALLOW_UNSIGNED=1 set." % args.archive
            )
            return 0

        state = check_archive(args.archive, files, args.allow_unsigned)
        if args.verify_signature:
            verify_signature(args.archive)
        suffix = " (unsigned development mode)" if state != "signed" else ""
        print("CEP ZIP matches panel source%s." % suffix)
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, "ERROR: %s\n" % error)


if __name__ == "__main__":
    sys.exit(main())
