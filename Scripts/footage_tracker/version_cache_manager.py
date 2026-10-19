# -*- coding: utf-8 -*-
"""
Version Cache Manager
Maintains a persistent cache of version information per project.

Concurrency contract:
- ``cache_lock`` guards ``cache_data`` and ``cache_path``.  Only
  ``_saveCacheLocked`` performs disk writes, and it is only ever called
  with the lock already held (by ``saveCache``).  No method acquires the
  lock twice, so the non-reentrant ``threading.Lock`` can never
  deadlock.
- Writes are atomic (unique temp file + ``os.replace``) so a crashed or
  concurrent writer can never leave a truncated cache behind.
- A failed save keeps the ``dirty`` flag set so the next ``stop()`` or
  background pass retries (last-known-good on transient NAS failures).
"""

import os
import json
import threading
from datetime import datetime

from footage_tracker import cache_store
from PrismUtils.Decorators import err_catcher as err_catcher


class VersionCacheManager:
    """
    Manages a persistent cache of version information for render folders.

    Cache structure:
    {
        "project_path": "X:/Project",
        "last_updated": "2025-01-15T10:30:00",
        "versions": {
            "SQ020-SH030/Lighting_Humans": {
                "allVersions": ["v0025", "v0024", "v0023"],
                "latestVersion": "v0025",
                "last_scanned": "2025-01-15T10:30:00"
            }
        }
    }
    """

    CACHE_VERSION = "1.0"
    CACHE_FILENAME = ".prism_footage_cache.json"
    CACHE_STALE_SECONDS = 300  # individual entries expire after 5 minutes

    def __init__(self, tracker):
        super(VersionCacheManager, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.utils = tracker.utils

        self.cache_data = {}
        self.cache_path = None
        self.project_path = None
        self.is_running = False
        self.cache_lock = threading.Lock()

    @err_catcher(name=__name__)
    def getCachePath(self, project_path=None):
        """Get the cache file path for the current or specified project."""
        if project_path:
            # Store cache in the project folder
            cache_path = os.path.join(project_path, self.CACHE_FILENAME)
        elif self.project_path:
            cache_path = os.path.join(self.project_path, self.CACHE_FILENAME)
        else:
            # Fallback to Prism temp folder
            temp_dir = self.core.paths.getTempPath()
            cache_path = os.path.join(temp_dir, self.CACHE_FILENAME)

        return os.path.normpath(cache_path)

    @err_catcher(name=__name__)
    def loadCache(self, project_path=None):
        """Load cache from disk for the specified project."""
        with self.cache_lock:
            if project_path:
                self.project_path = project_path

            if not self.project_path:
                return False

            self.cache_path = self.getCachePath()

            if not os.path.exists(self.cache_path):
                self.cache_data = self._createEmptyCache()
                return False

            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
            except Exception as e:
                print(f"[CACHE] Error loading cache: {e}")
                # Keep the last-known-good file aside instead of parsing a
                # corrupt file forever; the next save rewrites cleanly.
                try:
                    os.replace(self.cache_path, self.cache_path + ".corrupt")
                except OSError:
                    pass
                self.cache_data = self._createEmptyCache()
                return False

            # Validate cache structure (drops malformed entries)
            cache_data, error = cache_store.validate_cache(raw_data)
            if error:
                print(f"[CACHE] Invalid cache: {error}")
                self.cache_data = self._createEmptyCache()
                return False

            # Check if cache is for the correct project (project-change
            # invalidation)
            cache_project = cache_data.get("project_path", "")
            if cache_store.normalize_path(cache_project) != cache_store.normalize_path(
                self.project_path
            ):
                self.cache_data = self._createEmptyCache()
                return False

            self.cache_data = cache_data
            self.cache_data["dirty"] = False

            entry_count = len(self.cache_data.get('versions', {}))
            if entry_count > 0:
                print(f"[CACHE] Loaded {entry_count} cached render folders")

            return True

    def _saveCacheLocked(self):
        """Write the cache; ONLY called with ``cache_lock`` held."""
        if not self.cache_path:
            self.cache_path = self.getCachePath()

        self.cache_data["last_updated"] = datetime.now().isoformat()

        ok, error = cache_store.atomic_write_json(self.cache_path, self.cache_data)
        if not ok:
            print(f"[CACHE] Error saving cache: {error}")
            # Keep the dirty flag so a later stop()/save retries.
            return False

        self.cache_data["dirty"] = False
        return True

    @err_catcher(name=__name__)
    def saveCache(self):
        """Save cache to disk."""
        with self.cache_lock:
            return self._saveCacheLocked()

    @err_catcher(name=__name__)
    def getVersionInfo(self, path, version_dir=None, force_rescan=False):
        """
        Get version info from cache.

        Args:
            path: Full path to footage file
            version_dir: Directory containing versions (optional)
            force_rescan: If True, bypass cache and rescan

        Returns:
            Fresh cached version info, or None when not cached, expired,
            or force_rescan=True
        """
        with self.cache_lock:
            if force_rescan:
                # Bypass cache completely
                return None

            cache_key = self._getCacheKey(path)
            if not cache_key:
                return None

            versions_data = self.cache_data.get("versions", {})
            entry = versions_data.get(cache_key)
            if entry is None:
                return None

            # Entry-level expiry: stale entries are treated as misses so a
            # later scan refreshes them.
            if not cache_store.entry_is_fresh(
                entry, None, self.CACHE_STALE_SECONDS
            ):
                return None

            return entry

    @err_catcher(name=__name__)
    def scanAndCacheFolder(self, folder_path, force_save=False):
        """
        Scan a render folder and cache the version information.

        Returns the version info dict.
        """
        cache_key = self._getCacheKey(folder_path)
        if not cache_key:
            return None

        try:
            # Scan the folder for versions
            allVersions = []
            latestVersion = None

            if os.path.exists(folder_path):
                versionItems = []
                for item in os.listdir(folder_path):
                    if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                        # Check if this version folder contains actual footage files
                        if self.utils.versionHasFootage(os.path.join(folder_path, item)):
                            versionItems.append(item)

                for item in sorted(versionItems, key=cache_store.version_sort_key):
                    allVersions.append(item)
                    if len(allVersions) == 1:
                        import re

                        baseMatch = re.match(r'(v\d+)', item)
                        if baseMatch:
                            latestVersion = baseMatch.group(1)

            versionInfo = {
                "allVersions": allVersions,
                "latestVersion": latestVersion or allVersions[0] if allVersions else "v0000",
                "last_scanned": datetime.now().isoformat()
            }

            with self.cache_lock:
                if "versions" not in self.cache_data:
                    self.cache_data["versions"] = {}

                self.cache_data["versions"][cache_key] = versionInfo

                if not force_save:
                    # Mark cache as dirty (saved on next background update)
                    self.cache_data["dirty"] = True
                # NOTE: saving happens after the lock is released below.

            if force_save:
                self.saveCache()

            return versionInfo

        except Exception as e:
            import traceback
            print(f"[CACHE] Error scanning folder {folder_path}: {e}")
            traceback.print_exc()
            return None

    @err_catcher(name=__name__)
    def stop(self):
        """Save cache before exiting (retries failed persistence)."""
        with self.cache_lock:
            dirty = bool(self.cache_data.get("dirty", False))

        if dirty:
            self.saveCache()

    @err_catcher(name=__name__)
    def _getCacheKey(self, path):
        """Cache key for a media path (see cache_store.get_cache_key)."""
        return cache_store.get_cache_key(path)

    @err_catcher(name=__name__)
    def mergeEntries(self, entries):
        """Merge externally collected version entries (legacy migration).

        Existing entries win (they come from a fresh scan); returns the
        number of merged entries.
        """
        if not isinstance(entries, dict):
            return 0
        merged = 0
        with self.cache_lock:
            versions = self.cache_data.setdefault("versions", {})
            for key, entry in entries.items():
                if key in versions:
                    continue
                _, error = cache_store.validate_cache(
                    {"version": "1.0", "project_path": "", "versions": {key: entry}}
                )
                if error:
                    continue
                versions[key] = entry
                merged += 1
            if merged:
                self.cache_data["dirty"] = True
        return merged

    @err_catcher(name=__name__)
    def storeEntry(self, cache_key, version_info):
        """Store one externally scanned version entry and mark dirty.

        Used when a caller performs its own (faster) folder scan and wants
        to share the result through this cache.
        """
        if not cache_key or not isinstance(version_info, dict):
            return False
        _, error = cache_store.validate_cache(
            {
                "version": "1.0",
                "project_path": "",
                "versions": {cache_key: version_info},
            }
        )
        if error:
            return False
        with self.cache_lock:
            self.cache_data.setdefault("versions", {})[cache_key] = version_info
            self.cache_data["dirty"] = True
        return True

    @err_catcher(name=__name__)
    def isDirty(self):
        """True when unsaved changes are pending."""
        with self.cache_lock:
            return bool(self.cache_data.get("dirty", False))

    @err_catcher(name=__name__)
    def _createEmptyCache(self):
        """Create an empty cache structure."""
        return {
            "version": self.CACHE_VERSION,
            "project_path": self.project_path or "",
            "created": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "versions": {}
        }

    @err_catcher(name=__name__)
    def _isCacheStale(self):
        """Check if cache is stale."""
        last_updated = self.cache_data.get("last_updated", "")
        if not last_updated:
            return True

        try:
            last_time = datetime.fromisoformat(last_updated)
            age = (datetime.now() - last_time).total_seconds()
            return age > self.CACHE_STALE_SECONDS
        except Exception:
            return True

    @err_catcher(name=__name__)
    def _getCacheAge(self):
        """Get cache age in seconds."""
        last_updated = self.cache_data.get("last_updated", "")
        if not last_updated:
            return 999999

        try:
            last_time = datetime.fromisoformat(last_updated)
            return (datetime.now() - last_time).total_seconds()
        except Exception:
            return 999999

    @err_catcher(name=__name__)
    def invalidateEntry(self, path):
        """
        Invalidate cache for a specific render folder.
        Call this after rendering new versions to trigger a rescan.
        """
        with self.cache_lock:
            cache_key = self._getCacheKey(path)
            if not cache_key or cache_key not in self.cache_data.get("versions", {}):
                return
            del self.cache_data["versions"][cache_key]
            print(f"[CACHE] Invalidated cache for {cache_key}")
            self.cache_data["dirty"] = True

        # Save outside the lock (saveCache acquires it).
        self.saveCache()

    @err_catcher(name=__name__)
    def clearCache(self):
        """Clear the cache."""
        with self.cache_lock:
            self.cache_data = self._createEmptyCache()
            if self.cache_path and os.path.exists(self.cache_path):
                os.remove(self.cache_path)

    @err_catcher(name=__name__)
    def getCacheStats(self):
        """Get cache statistics."""
        with self.cache_lock:
            versions_count = len(self.cache_data.get("versions", {}))
            age = self._getCacheAge()
            return {
                "versions": versions_count,
                "age_seconds": age,
                "stale": age > self.CACHE_STALE_SECONDS,
                "cache_path": self.cache_path
            }
