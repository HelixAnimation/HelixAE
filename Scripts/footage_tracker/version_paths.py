# -*- coding: utf-8 -*-
"""Deterministic version-path helpers for footage version switching.

Pure-stdlib module (no Qt/Prism imports) so the path arithmetic behind
version updates can be unit tested directly (see tests/test_version_paths.py).

Contract notes:

- A *version folder token* is the ``v####`` folder name on disk
  (``v0003``).  A *full version label* may carry a suffix
  (``v0003 (mp4)``) as shown in the tracker dropdown; folder names and
  filename tokens always use the bare token.
- ``build_new_version_path`` replaces the version folder and the version
  inside the filename deterministically (fixes the historic
  ``_vv0003_`` doubling produced by substituting a folder token into
  ``_v<digits>_``).
- ``match_footage_file`` replaces the old lazy-regex base comparison that
  collapsed distinct filenames to their first character.
"""

import os
import re

_VERSION_FOLDER_RE = re.compile(r"^v\d+$")
_FILENAME_VERSION_RE = re.compile(r"_v\d+(?=[_.\[])")


def extract_version_token(version):
    """Return the bare ``v####`` token from a version folder name or label."""
    if isinstance(version, bytes):
        version = version.decode("utf-8")
    if not isinstance(version, str):
        raise TypeError("version must be str, got %r" % type(version).__name__)
    version = version.strip()
    if not version:
        raise ValueError("empty version")
    match = re.match(r"(v\d+)", version)
    if not match:
        raise ValueError("invalid version: %r" % version)
    return match.group(1)


def version_folder_index(path_parts):
    """Index of the first ``v####`` folder component, or -1."""
    for i, part in enumerate(path_parts):
        if _VERSION_FOLDER_RE.match(part):
            return i
    return -1


def substitute_version_in_filename(filename, new_version):
    """Replace the ``_v####_`` token in a filename with the new version.

    ``new_version`` may be a bare token or a full label; only the bare
    token is ever substituted, so ``v0003`` never becomes ``vv0003``.
    Returns the filename unchanged when it carries no version token.
    """
    token = extract_version_token(new_version)
    return _FILENAME_VERSION_RE.sub("_" + token, filename, count=1)


def build_new_version_path(old_path, new_version):
    """Rebuild ``old_path`` pointing at ``new_version``.

    Works for both layouts (AOV subfolder under the version folder, i.e.
    3D renders, and plain version-folder paths).  Always returns a
    forward-slash path.  Raises ``ValueError`` when no version folder
    exists in ``old_path``.
    """
    if isinstance(old_path, bytes):
        old_path = old_path.decode("utf-8")
    if not isinstance(old_path, str) or not old_path.strip():
        raise ValueError("empty path")
    token = extract_version_token(new_version)

    parts = old_path.replace("\\", "/").split("/")
    idx = version_folder_index(parts)
    if idx < 0:
        raise ValueError("no version folder in path: %r" % old_path)
    parts[idx] = token
    parts[-1] = substitute_version_in_filename(parts[-1], token)
    return "/".join(parts)


def footage_base_name(filename):
    """Deterministic base name for matching footage files.

    Strips the extension and then, repeatedly from the end: a ``[word]``
    marker, a ``_<digits>`` marker, a frame-number suffix, and a ``_v####``
    marker.  Unlike the old lazy regex this never truncates the name to
    its first character.
    """
    if isinstance(filename, bytes):
        filename = filename.decode("utf-8")
    if not isinstance(filename, str):
        raise TypeError("filename must be str, got %r" % type(filename).__name__)
    name = filename
    dot = name.rfind(".")
    if dot > 0:
        name = name[:dot]
    changed = True
    while changed:
        changed = False
        suffix = re.search(r"\[\w+\]$", name)
        if suffix:
            name = name[: suffix.start()]
            changed = True
            continue
        suffix = re.search(r"_\d+$", name)
        if suffix:
            name = name[: suffix.start()]
            changed = True
            continue
        suffix = re.search(r"\.\d{1,6}$", name)
        if suffix:
            name = name[: suffix.start()]
            changed = True
            continue
        suffix = re.search(r"_v\d+$", name)
        if suffix:
            name = name[: suffix.start()]
            changed = True
    return name


_VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".mkv")
_FOOTAGE_EXTENSIONS = {
    ".exr", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".tga", ".bmp", ".psd",
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm",
}


def is_footage_file(filename):
    if isinstance(filename, bytes):
        filename = filename.decode("utf-8")
    if not isinstance(filename, str):
        raise TypeError("filename must be str, got %r" % type(filename).__name__)
    lowered = filename.lower()
    return any(lowered.endswith(ext) for ext in _FOOTAGE_EXTENSIONS)


def match_footage_file(files, old_filename):
    """Pick the new-version file corresponding to ``old_filename``.

    Deterministic: input order is normalized with ``sorted()`` and the
    preference is video file, then frame-numbered sequence file, then
    any file with the same base name.  Returns ``None`` when nothing
    matches.
    """
    if not files:
        return None
    base = footage_base_name(old_filename)
    candidates = sorted(
        f
        for f in files
        if is_footage_file(f) and footage_base_name(f) == base
    )
    if not candidates:
        return None
    videos = [f for f in candidates if f.lower().endswith(_VIDEO_EXTENSIONS)]
    if videos:
        return videos[0]
    sequences = [f for f in candidates if re.search(r"[._]\d{4,6}[._]", f)]
    if sequences:
        return sequences[0]
    return candidates[0]


def sorted_listing(directory):
    """Sorted, deterministic ``os.listdir`` (errors propagate as [])."""
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []


__all__ = [
    "extract_version_token",
    "version_folder_index",
    "substitute_version_in_filename",
    "build_new_version_path",
    "footage_base_name",
    "is_footage_file",
    "match_footage_file",
    "sorted_listing",
]
