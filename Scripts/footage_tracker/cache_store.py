# -*- coding: utf-8 -*-
"""Pure helpers for the on-disk version cache (stdlib only).

Used by ``version_cache_manager.VersionCacheManager``.  Kept free of
Prism/Qt imports so it is unit-testable by file-path loading.
"""

import json
import os
import re
import tempfile

# A version folder looks like "v0007", "v0012 (mp4)", ...
_VERSION_FOLDER_RE = re.compile(r"^v\d{4,}$")
_VERSION_TOKEN_RE = re.compile(r"^(v\d+)")
_SHOT_RE = re.compile(r"^sh\d+", re.IGNORECASE)
_SEQUENCE_RE = re.compile(r"^(ch|sq|ep)\d+", re.IGNORECASE)

REQUIRED_ROOT_KEYS = ("version", "project_path", "versions")


def normalize_path(path):
    """Normalize separators for comparisons (backslashes → slashes)."""
    if not isinstance(path, str):
        raise TypeError("expected str, got %r" % type(path).__name__)
    return path.replace("\\", "/")


def is_version_folder(name):
    """True for folder names like ``v0007`` (plain, no suffix)."""
    if not isinstance(name, str):
        return False
    return bool(_VERSION_FOLDER_RE.match(name))


def version_sort_key(version_folder):
    """Sort versions newest-first, plain before suffixed."""
    match = _VERSION_TOKEN_RE.match(version_folder)
    if match:
        base_version = match.group(1)
        suffix = version_folder[len(base_version):]
        version_number = int(base_version[1:])
        has_suffix = 0 if suffix == "" else 1
        return (-version_number, has_suffix, suffix)
    return (0, 0, version_folder)


def get_cache_key(path):
    """Extract the render-folder cache key from a media path.

    For ``X:/Project/03_Production/Shots/SQ020/SH030/Renders/3dRender/
    Lighting_Humans/v0016/beauty/...`` returns ``"SQ020-SH030/
    Lighting_Humans"``.  Returns ``None`` when the path contains neither
    a shot folder nor a version folder.
    """
    if isinstance(path, bytes):
        path = path.decode("utf-8", errors="replace")
    if not isinstance(path, str) or not path:
        return None
    try:
        path_parts = normalize_path(path).split("/")

        shot = None
        sequence = None
        task = None

        for i, part in enumerate(path_parts):
            if _SHOT_RE.match(part):
                shot = part
                if i > 0 and _SEQUENCE_RE.match(path_parts[i - 1]):
                    sequence = path_parts[i - 1]

            if is_version_folder(part) or (
                part.startswith("v") and len(part) >= 5 and part[1:5].isdigit()
            ):
                if i > 0:
                    task = path_parts[i - 1]
                break

        if shot and task:
            entity = "%s-%s" % (sequence, shot) if sequence else shot
            return "%s/%s" % (entity, task)
        return None
    except Exception:
        return None


def validate_cache(cache_data):
    """Return ``(clean_data, error)`` for a loaded cache document.

    Drops malformed version entries instead of failing the whole cache.
    """
    if not isinstance(cache_data, dict):
        return None, "cache document is not an object"
    for key in REQUIRED_ROOT_KEYS:
        if key not in cache_data:
            return None, "cache document missing key %r" % key

    versions = cache_data.get("versions")
    if not isinstance(versions, dict):
        return None, "cache 'versions' is not an object"

    clean_versions = {}
    for key, entry in versions.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        all_versions = entry.get("allVersions")
        latest = entry.get("latestVersion")
        if not isinstance(all_versions, list) or not all(
            isinstance(v, str) for v in all_versions
        ):
            continue
        if not isinstance(latest, str) or not latest:
            continue
        clean_entry = dict(entry)
        clean_entry["allVersions"] = all_versions
        clean_entry["latestVersion"] = latest
        clean_versions[key] = clean_entry

    clean = dict(cache_data)
    clean["versions"] = clean_versions
    return clean, None


def entry_is_fresh(entry, now_iso, max_age_seconds):
    """True when a cache entry's ``last_scanned`` is within the age limit."""
    if not isinstance(entry, dict):
        return False
    last_scanned = entry.get("last_scanned", "")
    if not last_scanned:
        return False
    try:
        from datetime import datetime

        scanned = datetime.fromisoformat(last_scanned)
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
        return (now - scanned).total_seconds() <= max_age_seconds
    except Exception:
        return False


def atomic_write_json(path, data, indent=2):
    """Write JSON durably: unique temp file + ``os.replace``.

    A unique temporary name keeps concurrent writers (two Prism
    processes sharing a NAS project) from corrupting each other, and
    ``os.replace`` makes the swap atomic on both POSIX and Windows.
    Returns ``(True, None)`` or ``(False, reason)``; corrupts nothing on
    failure (the previous file stays intact).
    """
    if not isinstance(path, str) or not path:
        return False, "empty path"
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory)
        except OSError as e:
            return False, "cannot create cache directory: %s" % e

    try:
        fd, temp_path = tempfile.mkstemp(
            prefix=os.path.basename(path) + ".tmp.", dir=directory or "."
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except BaseException:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise
        return True, None
    except Exception as e:  # pragma: no cover - disk failures
        return False, str(e)


__all__ = [
    "normalize_path",
    "is_version_folder",
    "version_sort_key",
    "get_cache_key",
    "validate_cache",
    "entry_is_fresh",
    "atomic_write_json",
    "REQUIRED_ROOT_KEYS",
]
