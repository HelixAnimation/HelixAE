# -*- coding: utf-8 -*-
"""
Hierarchy Builder Module
Builds and manages the footage hierarchy tree structure
"""

import os
import re
from datetime import datetime
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class HierarchyBuilder:
    """Builds hierarchy structures from footage data"""

    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core
        self.utils = tracker.utils

        # In-memory version cache for current session
        self._xmp_cache = None
        self._xmp_cache_dirty = False

        # Initialize cache manager for backward compatibility (fallback)
        from .version_cache_manager import VersionCacheManager
        self.cache_manager = VersionCacheManager(tracker)

    @err_catcher(name=__name__)
    def _readVersionCacheFromXMP(self):
        """Read version cache from .aep file's XMP metadata"""
        import json

        try:
            # Read XMP metadata from the project
            scpt = """
            if (app.project && app.project.xmpPacket) {
                app.project.xmpPacket;
            } else {
                '';
            }
            """
            result = self.tracker.main.ae_core.executeAppleScript(scpt)
            if result and isinstance(result, bytes):
                result = result.decode('utf-8')

            if result and 'PrismFootageTracker:VersionCache' in result:
                # Extract the JSON data between the tags
                start_marker = 'PrismFootageTracker:VersionCache">'
                end_marker = '</rdf:li'

                start_idx = result.find(start_marker)
                if start_idx > 0:
                    start_idx += len(start_marker)
                    end_idx = result.find(end_marker, start_idx)
                    if end_idx > start_idx:
                        json_str = result[start_idx:end_idx].strip()
                        cache_data = json.loads(json_str)
                        entry_count = len(cache_data.get('versions', {}))
                        print(f"[CACHE XMP] Loaded version cache from .aep XMP: {entry_count} entries")
                        return cache_data
        except Exception as e:
            print(f"[CACHE XMP] Error reading XMP: {e}")

        return None

    @err_catcher(name=__name__)
    def _writeVersionCacheToXMP(self, cache_data):
        """Write version cache to .aep file's XMP metadata"""
        import json

        try:
            # Read current XMP
            scpt_read = """
            if (app.project && app.project.xmpPacket) {
                app.project.xmpPacket;
            } else {
                '';
            }
            """
            current_xmp = self.tracker.main.ae_core.executeAppleScript(scpt_read)
            if current_xmp and isinstance(current_xmp, bytes):
                current_xmp = current_xmp.decode('utf-8')
            else:
                current_xmp = ''

            # Prepare the cache data as JSON
            cache_json = json.dumps(cache_data)

            # Create XMP structure for our cache
            xmp_entry = f'        <rdf:li>PrismFootageTracker:VersionCache">{cache_json}</rdf:li'

            # Check if we need to update existing entry or create new one
            if 'PrismFootageTracker:VersionCache' in current_xmp:
                # Replace existing entry
                import re
                pattern = r'        <rdf:li>PrismFootageTracker:VersionCache">.*?</rdf:li'
                new_xmp = re.sub(pattern, xmp_entry, current_xmp, flags=re.DOTALL)
            else:
                # Add new entry - find a good place to insert it
                if '</rdf:Description>' in current_xmp:
                    new_xmp = current_xmp.replace(
                        '</rdf:Description>',
                        f'{xmp_entry}\n    </rdf:Description>'
                    )
                else:
                    # Create basic XMP structure if none exists
                    new_xmp = f'''<?xpacket begin="..." id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.6-c140 79.160451">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about="" xmlns:PrismFootageTracker="http://prism-pipeline.com/FootageTracker/1.0/">
{xmp_entry}
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

            # Write updated XMP back to project
            scpt_write = f'''
            if (app.project) {{
                app.project.xmpPacket = "{new_xmp.replace(chr(10), '\\n').replace(chr(13), '').replace('"', '\\"')}";
            }}
            '''
            self.tracker.main.ae_core.executeAppleScript(scpt_write)
            print(f"[CACHE XMP] Saved version cache to .aep XMP: {len(cache_data.get('versions', {}))} entries")
            return True

        except Exception as e:
            print(f"[CACHE XMP] Error writing XMP: {e}")
            import traceback
            traceback.print_exc()
            return False

    @err_catcher(name=__name__)
    def getVersionInfoFromAPI(self, path):
        """
        Get version info using smart cache:
        1. Check persistent cache (instant if available)
        2. Scan versioninfo.json files (Prism Houdini export) - FAST
        3. Fallback to versionHasFootage() for renders without versioninfo - SLOW
        4. Cache results for next time

        Returns: {
            'currentVersion': 'v0025',
            'latestVersion': 'v0025',
            'currentVersionFull': 'v0025',
            'allVersions': ['v0025', 'v0024', ...],
            'task': 'Lighting_Humans'
        }
        """
        try:
            # Extract current version full name (with suffix) from path
            pathParts = path.replace('\\', '/').split('/')
            currentVersionFull = 'v0000'
            task = 'Unknown'
            versionIndex = -1

            for i, part in enumerate(pathParts):
                if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                    currentVersionFull = part
                    versionIndex = i
                    if i > 0:
                        task = pathParts[i - 1]
                    break

            if versionIndex == -1:
                # Not a versioned render (Resources, External, etc.)
                return {
                    'currentVersion': 'v0000',
                    'latestVersion': 'v0000',
                    'currentVersionFull': 'v0000',
                    'allVersions': ['v0000'],
                    'task': os.path.basename(os.path.dirname(path)) if os.path.dirname(path) else 'Unknown'
                }

            # Extract base version (without suffix like " (mp4)")
            baseVersionMatch = re.match(r'(v\d+)', currentVersionFull)
            currentVersion = baseVersionMatch.group(1) if baseVersionMatch else currentVersionFull

            # Load XMP cache on first access
            if self._xmp_cache is None:
                self._xmp_cache = self._readVersionCacheFromXMP()
                if not self._xmp_cache:
                    # Initialize empty cache structure
                    self._xmp_cache = {
                        "version": "1.0",
                        "last_updated": datetime.now().isoformat(),
                        "versions": {}
                    }

            # Get cache key for this path
            cache_key = self.cache_manager._getCacheKey(path)

            # Try XMP cache first (zero file system access)
            if cache_key and cache_key in self._xmp_cache.get("versions", {}):
                cached_info = self._xmp_cache["versions"][cache_key]
                allVersions = cached_info.get("allVersions", [])
                latestVersion = cached_info.get("latestVersion", currentVersion)
            else:
                # Not in cache - scan and cache for next time
                versionDir = '/'.join(pathParts[:versionIndex])
                if os.name == 'nt':
                    versionDir = versionDir.replace('/', '\\')

                allVersions = []
                latestVersion = currentVersion

                if os.path.exists(versionDir):
                    try:
                        # Custom sort for version folders
                        def versionSortKey(versionFolder):
                            match = re.match(r'(v\d+)(.*)', versionFolder)
                            if match:
                                baseVer = match.group(1)
                                suffix = match.group(2) or ''
                                verNum = int(baseVer[1:])
                                hasSuffix = 0 if suffix == '' else 1
                                return (-verNum, hasSuffix, suffix)
                            return (0, 0, versionFolder)

                        versionItems = []
                        for item in os.listdir(versionDir):
                            if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                                versionFolderPath = os.path.join(versionDir, item)

                                # FAST PATH: Check for versioninfo.json (created by Prism Houdini export)
                                # This is much faster than scanning folder contents
                                versioninfoPath = os.path.join(versionFolderPath, "versioninfo.json")
                                if os.path.exists(versioninfoPath):
                                    versionItems.append(item)
                                elif self.utils.versionHasFootage(versionFolderPath):
                                    # SLOW PATH: Fallback for renders without versioninfo
                                    versionItems.append(item)

                        # Sort and cache
                        for item in sorted(versionItems, key=versionSortKey):
                            allVersions.append(item)
                            if len(allVersions) == 1:
                                baseMatch = re.match(r'(v\d+)', item)
                                if baseMatch:
                                    latestVersion = baseMatch.group(1)

                    except Exception as e:
                        import sys
                        print(f"[DEBUG] Error listing version directory {versionDir}: {e}", file=sys.stderr)
                        allVersions = [currentVersionFull]
                        latestVersion = currentVersion
                else:
                    allVersions = [currentVersionFull]
                    latestVersion = currentVersion

                # Cache this result for next time (in XMP)
                versionInfo = {
                    "allVersions": allVersions,
                    "latestVersion": latestVersion or allVersions[0] if allVersions else "v0000",
                    "last_scanned": datetime.now().isoformat()
                }
                self._xmp_cache.setdefault("versions", {})[cache_key] = versionInfo
                self._xmp_cache_dirty = True

            return {
                'currentVersion': currentVersion,
                'latestVersion': latestVersion,
                'currentVersionFull': currentVersionFull,
                'allVersions': allVersions,
                'task': task
            }
        except Exception as e:
            # Fallback to basic info if error
            import traceback
            print(f"[DEBUG] getVersionInfoFromAPI failed for {path}: {e}")
            traceback.print_exc()
            return {
                'currentVersion': 'v0000',
                'latestVersion': 'v0000',
                'currentVersionFull': 'v0000',
                'allVersions': ['v0000'],
                'task': 'Unknown'
            }

    @err_catcher(name=__name__)
    def buildHierarchy(self, footage_data, comp_data):
        """Build complete hierarchy from footage and composition data"""
        import time

        build_start = time.perf_counter()

        # Load XMP cache on first buildHierarchy call
        # (project should be loaded by now, so XMP is accessible)
        if self._xmp_cache is None:
            self._xmp_cache = self._readVersionCacheFromXMP()
            if not self._xmp_cache:
                # Initialize empty cache structure
                self._xmp_cache = {
                    "version": "1.0",
                    "last_updated": datetime.now().isoformat(),
                    "versions": {}
                }

        hierarchy = {
            "3D Renders": {},
            "2D Renders": {},
            "Resources": {},
            "External": {},
            "Comps": {}
        }

        totalCount = 0
        upToDateCount = 0
        outdatedCount = 0

        # Process footage data
        footage_start = time.perf_counter()
        parse_time = 0
        extract_time = 0

        # Simple cache for this load operation only (cleared each reload)
        # Avoids repeated API calls for the same path within a single load
        version_cache = {}

        for footage_item in footage_data:
            path = footage_item['path']

            parse_start = time.perf_counter()
            # Use Prism API instead of file system scanning (10x faster!)
            if path in version_cache:
                versionInfo = version_cache[path]
            else:
                versionInfo = self.getVersionInfoFromAPI(path)
                version_cache[path] = versionInfo
            parse_end = time.perf_counter()
            parse_time += (parse_end - parse_start)

            if not versionInfo:
                # Create a default version info if parsing fails
                versionInfo = {
                    'currentVersion': 'v0001',
                    'latestVersion': 'v0001',
                    'currentVersionFull': 'v0001',
                    'allVersions': ['v0001']
                }

            totalCount += 1

            # Extract hierarchy with new return format
            extract_start = time.perf_counter()
            result = self.utils.extractHierarchy(path, footage_item['name'])
            extract_end = time.perf_counter()
            extract_time += (extract_end - extract_start)

            if len(result) == 5:
                shot, identifier, aov, group, hierarchy_type = result
            else:
                # Handle old format for backward compatibility
                shot, identifier, aov, group = result[:4]
                hierarchy_type = result[4] if len(result) > 4 else 'render'

            # Ensure group is one of our valid groups
            if group not in hierarchy:
                if hierarchy_type == 'render':
                    # Default renders to 3D Renders if not specified
                    group = "3D Renders"
                else:
                    # Default preserved to Resources if not specified
                    group = "Resources"

            if hierarchy_type == 'render':
                # For renders, use shot/identifier/aov structure
                if shot not in hierarchy[group]:
                    hierarchy[group][shot] = {}
                if identifier not in hierarchy[group][shot]:
                    hierarchy[group][shot][identifier] = {}
                if aov not in hierarchy[group][shot][identifier]:
                    hierarchy[group][shot][identifier][aov] = []

                footageData = {
                    'name': footage_item['name'],  # Original filename
                    'footageId': footage_item['footageId'],
                    'versionInfo': versionInfo,
                    'fps': footage_item['fps'],
                    'duration': footage_item['duration'],
                    'startFrame': footage_item['startFrame'],
                    'endFrame': footage_item['endFrame'],
                    'width': footage_item.get('width', 'N/A'),
                    'height': footage_item.get('height', 'N/A'),
                    'path': path,
                    'group': group,
                    'hierarchy_type': hierarchy_type,
                    'shotName': shot,  # Add shot name for Kitsu lookup
                    'isLatest': versionInfo.get(
                        'isLatest',
                        versionInfo['currentVersion'] == versionInfo['latestVersion']
                    )
                }
                hierarchy[group][shot][identifier][aov].append(footageData)
            else:
                # For preserved structures, use relative path structure
                relative_path = identifier if identifier else os.path.splitext(footage_item['name'])[0]
                if relative_path not in hierarchy[group]:
                    hierarchy[group][relative_path] = []

                footageData = {
                    'name': footage_item['name'],
                    'footageId': footage_item['footageId'],
                    'versionInfo': versionInfo,
                    'fps': footage_item['fps'],
                    'duration': footage_item['duration'],
                    'startFrame': footage_item['startFrame'],
                    'endFrame': footage_item['endFrame'],
                    'width': footage_item.get('width', 'N/A'),
                    'height': footage_item.get('height', 'N/A'),
                    'path': path,
                    'group': group,
                    'hierarchy_type': hierarchy_type,
                    'relative_path': relative_path,
                    'isLatest': versionInfo.get(
                        'isLatest',
                        versionInfo['currentVersion'] == versionInfo['latestVersion']
                    )
                }
                hierarchy[group][relative_path].append(footageData)

            if versionInfo.get('isLatest', versionInfo['currentVersion'] == versionInfo['latestVersion']):
                upToDateCount += 1
            else:
                outdatedCount += 1

        footage_end = time.perf_counter()
        print(
            f"[TIMING]     Process footage data: {footage_end - footage_start:.4f}s"
            f" (parse: {parse_time:.4f}s via Prism API, extract: {extract_time:.4f}s)"
        )

        # Process composition data
        comps_start = time.perf_counter()
        hierarchy["Comps"] = {}
        for comp_info in comp_data:
            category = comp_info['category']

            # Add to Comps hierarchy
            if category not in hierarchy["Comps"]:
                hierarchy["Comps"][category] = []

            # Check if this comp already exists to avoid duplicates
            comp_exists = False
            for existing_comp in hierarchy["Comps"][category]:
                if existing_comp.get('compId') == comp_info['compId']:
                    comp_exists = True
                    break

            if not comp_exists:
                hierarchy["Comps"][category].append(comp_info)

        comps_end = time.perf_counter()
        print(f"[TIMING]     Process comp data: {comps_end - comps_start:.4f}s")

        build_end = time.perf_counter()
        print(f"[TIMING]   buildHierarchy internal: {build_end - build_start:.4f}s")

        # Save XMP cache if it was updated
        if self._xmp_cache_dirty:
            self._xmp_cache["last_updated"] = datetime.now().isoformat()
            self._writeVersionCacheToXMP(self._xmp_cache)
            self._xmp_cache_dirty = False

        return hierarchy, {
            'total': totalCount,
            'up_to_date': upToDateCount,
            'outdated': outdatedCount
        }

    @err_catcher(name=__name__)
    def pivot_to_identifier_first(self, render_data):
        """Pivot 3D render hierarchy from shot > identifier > aov to identifier > shot > aov"""
        pivoted = {}
        for shot, identifiers in render_data.items():
            if not isinstance(identifiers, dict):
                continue
            for identifier, aovs in identifiers.items():
                if not isinstance(aovs, dict):
                    continue
                if identifier not in pivoted:
                    pivoted[identifier] = {}
                if shot not in pivoted[identifier]:
                    pivoted[identifier][shot] = {}
                for aov, footage_list in aovs.items():
                    if aov not in pivoted[identifier][shot]:
                        pivoted[identifier][shot][aov] = []
                    if isinstance(footage_list, list):
                        pivoted[identifier][shot][aov].extend(footage_list)
        return pivoted

    @err_catcher(name=__name__)
    def buildShotAlternativesIndex(self, hierarchy):
        """Create reverse lookup: (identifier, aov) → [shots]"""
        alternatives = {}

        # Only process render groups (3D Renders and 2D Renders)
        for group in ["3D Renders", "2D Renders"]:
            if group in hierarchy and isinstance(hierarchy[group], dict):
                for shot in hierarchy[group]:
                    if isinstance(hierarchy[group][shot], dict):
                        for identifier in hierarchy[group][shot]:
                            if isinstance(hierarchy[group][shot][identifier], dict):
                                for aov in hierarchy[group][shot][identifier]:
                                    key = (identifier, aov)
                                    if key not in alternatives:
                                        alternatives[key] = []
                                    alternatives[key].append(shot)

        return alternatives

    @err_catcher(name=__name__)
    def cleanup(self):
        """Cleanup when closing the footage tracker."""
        # Save XMP cache if dirty
        if self._xmp_cache_dirty and self._xmp_cache:
            self._xmp_cache["last_updated"] = datetime.now().isoformat()
            self._writeVersionCacheToXMP(self._xmp_cache)
            self._xmp_cache_dirty = False

    @err_catcher(name=__name__)
    def preCacheProject(self, project_path=None):
        """
        Pre-cache all render folders for the project.
        XMP cache is built on-demand, so this is now a no-op.
        Kept for backward compatibility.
        """
        print("[CACHE XMP] Pre-caching is now automatic - no manual action needed")
        pass