#!/usr/bin/env python3
"""Check or rebuild the CEP archive Prism installs (standard library only)."""

import argparse
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "Integration" / "helixae"
ARCHIVE = ROOT / "Integration" / "helixae.zip"


def panel_files():
    return {
        path.relative_to(SOURCE).as_posix(): path
        for path in sorted(SOURCE.rglob("*"))
        if path.is_file()
        and not any(part in {"node_modules", "__pycache__", "@eaDir", ".git"}
                    for part in path.relative_to(SOURCE).parts)
        and path.name not in {".debug", ".DS_Store", "Thumbs.db"}
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="Rebuild a stale ZIP")
    args = parser.parse_args()
    files = panel_files()
    for required in ("index.html", "CSXS/manifest.xml", "js/main.js"):
        if required not in files:
            parser.error("Missing panel file: " + required)
    try:
        with zipfile.ZipFile(ARCHIVE) as archive:
            names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
            matches = (len(names) == len(files) and set(names) == set(files)
                       and all(archive.read(name) == path.read_bytes()
                               for name, path in files.items()))
    except (OSError, zipfile.BadZipFile):
        matches = False
    if matches:
        print("CEP ZIP matches panel source.")
        return
    if not args.build:
        parser.exit(1, "CEP ZIP is stale. Run: python dev_panel.py --build\n")
    with tempfile.NamedTemporaryFile(dir=ARCHIVE.parent, suffix=".zip", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, path in files.items():
                archive.write(path, name)
        temporary.chmod(0o644)
        temporary.replace(ARCHIVE)
    finally:
        temporary.unlink(missing_ok=True)
    print("Rebuilt Integration/helixae.zip. Reinstall the integration in Prism after deployment.")


if __name__ == "__main__":
    main()
