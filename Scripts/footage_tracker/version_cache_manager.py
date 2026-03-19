# -*- coding: utf-8 -*-
"""
Version Cache Manager
Maintains a persistent cache of version information per project.
"""

import os
import json
import threading
from datetime import datetime

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
    CACHE_STALE_SECONDS = 300  # Cache is stale after 5 minutes

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
                    self.cache_data = json.load(f)

                # Validate cache structure
                if not self._validateCache():
                    self.cache_data = self._createEmptyCache()
                    return False

                # Check if cache is for the correct project
                cache_project = self.cache_data.get("project_path", "")
                if cache_project.replace('\\', '/') != self.project_path.replace('\\', '/'):
                    self.cache_data = self._createEmptyCache()
                    return False

                # Use stale cache - will be refreshed as needed
                entry_count = len(self.cache_data.get('versions', {}))
                if entry_count > 0:
                    print(f"[CACHE] Loaded {entry_count} cached render folders")

                return True

            except Exception as e:
                print(f"[CACHE] Error loading cache: {e}")
                self.cache_data = self._createEmptyCache()
                return False

    @err_catcher(name=__name__)
    def saveCache(self):
        """Save cache to disk."""
        with self.cache_lock:
            if not self.cache_path:
                self.cache_path = self.getCachePath()

            self.cache_data["last_updated"] = datetime.now().isoformat()

            try:
                # Ensure directory exists
                cache_dir = os.path.dirname(self.cache_path)
                if cache_dir and not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)

                with open(self.cache_path, 'w', encoding='utf-8') as f:
                    json.dump(self.cache_data, f, indent=2, ensure_ascii=False)

                return True

            except Exception as e:
                print(f"[CACHE] Error saving cache: {e}")
                return False

    @err_catcher(name=__name__)
    def getVersionInfo(self, path, version_dir=None, force_rescan=False):
        """
        Get version info from cache.

        Args:
            path: Full path to footage file
            version_dir: Directory containing versions (optional)
            force_rescan: If True, bypass cache and rescan

        Returns:
            Cached version info, or None if not in cache or force_rescan=True
        """
        with self.cache_lock:
            if force_rescan:
                # Bypass cache completely
                return None

            # Extract cache key from path
            cache_key = self._getCacheKey(path)
            if not cache_key:
                return None

            versions_data = self.cache_data.get("versions", {})
            if cache_key in versions_data:
                # Return cached data - no file system access
                return versions_data[cache_key]

            return None

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
                # Get all version folders
                versionItems = []
                for item in os.listdir(folder_path):
                    if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                        # Check if this version folder contains actual footage files
                        if self.utils.versionHasFootage(os.path.join(folder_path, item)):
                            versionItems.append(item)

                # Sort versions
                def versionSortKey(versionFolder):
                    match = re.match(r'(v\d+)(.*)', versionFolder)
                    if match:
                        baseVer = match.group(1)
                        suffix = match.group(2) or ''
                        verNum = int(baseVer[1:])
                        hasSuffix = 0 if suffix == '' else 1
                        return (-verNum, hasSuffix, suffix)
                    return (0, 0, versionFolder)

                for item in sorted(versionItems, key=versionSortKey):
                    allVersions.append(item)
                    # First item is latest
                    if len(allVersions) == 1:
                        baseMatch = re.match(r'(v\d+)', item)
                        if baseMatch:
                            latestVersion = baseMatch.group(1)

            # Create version info
            versionInfo = {
                "allVersions": allVersions,
                "latestVersion": latestVersion or allVersions[0] if allVersions else "v0000",
                "last_scanned": datetime.now().isoformat()
            }

            # Update cache
            with self.cache_lock:
                if "versions" not in self.cache_data:
                    self.cache_data["versions"] = {}

                self.cache_data["versions"][cache_key] = versionInfo

                if force_save:
                    self.saveCache()
                else:
                    # Mark cache as dirty (will be saved on next background update)
                    self.cache_data["dirty"] = True

            return versionInfo

        except Exception as e:
            import traceback
            print(f"[CACHE] Error scanning folder {folder_path}: {e}")
            traceback.print_exc()
            return None

    @err_catcher(name=__name__)
    def stop(self):
        """Save cache before exiting."""
        with self.cache_lock:
            if self.cache_data.get("dirty", False):
                self.saveCache()

    @err_catcher(name=__name__)
    def _getCacheKey(self, path):
        """
        Extract a cache key from a path.

        For: X:/Project/03_Production/Shots/SQ020/SH030/Renders/3dRender/Lighting_Humans/v0016/beauty/...
        Returns: "SQ020-SH030/Lighting_Humans"
        """
        try:
            pathParts = path.replace('\\', '/').split('/')

            # Find shot and task
            shot = None
            sequence = None
            task = None
            versionIndex = -1

            for i, part in enumerate(pathParts):
                # Find shot folder
                if re.match(r'sh\d+', part.lower()):
                    shot = part
                    if i > 0 and re.match(r'(ch|sq|ep)\d+', pathParts[i-1].lower()):
                        sequence = pathParts[i-1]

                # Find task (folder before version)
                if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                    versionIndex = i
                    if i > 0:
                        task = pathParts[i - 1]
                    break

            if shot and task:
                entity = f"{sequence}-{shot}" if sequence else shot
                return f"{entity}/{task}"

            return None

        except Exception as e:
            return None

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
    def _validateCache(self):
        """Validate cache structure."""
        required_keys = ["version", "project_path", "versions"]
        for key in required_keys:
            if key not in self.cache_data:
                return False
        return True

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
            if cache_key and "versions" in self.cache_data and cache_key in self.cache_data["versions"]:
                del self.cache_data["versions"][cache_key]
                print(f"[CACHE] Invalidated cache for {cache_key}")
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
