# -*- coding: utf-8 -*-
"""
Data Parser Module
Handles parsing of footage and composition data from After Effects
"""

import os
import re
import json
from qtpy.QtWidgets import QApplication
import helixae_protocol
from PrismUtils.Decorators import err_catcher as err_catcher


class DataParser:
    """Handles parsing of data from After Effects"""

    def __init__(self, main, core):
        self.main = main
        self.core = core

        # Cache for extractCurrentShotFromProject result
        self._cached_current_shot = None
        self._cached_project_file = None

    @err_catcher(name=__name__)
    def readExportJSON(self, footage_path):
        """Read frame range and FPS from export JSON file"""
        try:
            # Look for versioninfo.json in the same directory as the footage
            footage_dir = os.path.dirname(footage_path)

            # Try to find versioninfo.json
            json_path = os.path.join(footage_dir, "versioninfo.json")

            if not os.path.exists(json_path):
                return None

            with open(json_path, 'r') as f:
                data = json.load(f)

            result = {}

            # Extract frame range - use startframe/endframe (3D format) or frameRange (old format)
            if data.get("startframe") is not None:
                result["startFrame"] = str(data["startframe"])
            elif data.get("frameRange"):
                result["startFrame"] = data["frameRange"].split("-")[0]

            if data.get("endframe") is not None:
                result["endFrame"] = str(data["endframe"])
            elif data.get("frameRange"):
                result["endFrame"] = data["frameRange"].split("-")[1]

            # Extract FPS
            if data.get("fps"):
                result["fps"] = str(data["fps"])

            # Extract resolution
            if data.get("resolution"):
                parts = data["resolution"].split("x")
                if len(parts) == 2:
                    result["width"] = parts[0]
                    result["height"] = parts[1]

            # Extract duration
            if data.get("duration"):
                result["duration"] = str(data["duration"])

            if result:
                print(f"[JSON FOOTAGE TRACKER] Read frame range from JSON: {footage_path}")
                print(f"  startFrame={result.get('startFrame')}, endFrame={result.get('endFrame')}, fps={result.get('fps')}")

            return result if result else None

        except Exception as e:
            print(f"[JSON FOOTAGE TRACKER] Error reading export JSON: {e}")
            return None

    @err_catcher(name=__name__)
    def parseFootageData(self, result):
        """Parse footage data from the AE bridge (JSON array response)"""
        try:
            parsed_footage, error = helixae_protocol.parse_footage_records(result)
            if error:
                # Transport/parse failure: tell the user instead of
                # silently showing an empty tracker tree.
                self.core.popup(f"Error parsing footage data:\n{error}")
                return []

            for record in parsed_footage:
                # Try to read frame range and FPS from export JSON first
                json_data = self.readExportJSON(record['path'])
                if json_data:
                    for field in ('startFrame', 'endFrame', 'fps',
                                  'width', 'height', 'duration'):
                        if json_data.get(field) is not None:
                            record[field] = str(json_data[field])

            return parsed_footage
        except Exception as e:
            self.core.popup(f"Error parsing footage data:\n{str(e)}")
            return []

    @err_catcher(name=__name__)
    def parseCompData(self, result):
        """Parse composition data from the AE bridge (JSON array response)"""
        try:
            parsed_comps, error = helixae_protocol.parse_comp_records(result)
            if error:
                self.core.popup(f"Error parsing composition data:\n{error}")
                return []

            for compInfo in parsed_comps:
                # displayStartTime comes from the JSON inPoint field
                compInfo['displayStartTime'] = compInfo.get('inPoint', '0')
                # Determine comp category
                compInfo['category'] = "Pre-comps" if compInfo['isPrecomp'] else "Main Comps"

            return parsed_comps
        except Exception as e:
            self.core.popup(f"Error parsing composition data:\n{str(e)}")
            return []

    @err_catcher(name=__name__)
    def getFootageAppleScript(self):
        """Get ExtendScript for fetching footage data (JSON response)"""
        return helixae_protocol.build_collect_tracker_footage()

    @err_catcher(name=__name__)
    def getCompAppleScript(self):
        """Get ExtendScript for fetching composition data (JSON response)"""
        return helixae_protocol.build_collect_comp_records()

    @err_catcher(name=__name__)
    def extractCurrentShotFromProject(self):
        """Extract the current shot from the .aep file name (cached)"""
        try:
            # Get the current project file path
            current_file = getattr(self, '_prepared_scene_path', None)
            if current_file is None:
                current_file = self.core.getCurrentFileName()

            # Check if we can use cached value
            if current_file and current_file == self._cached_project_file:
                return self._cached_current_shot

            # Cache miss - compute the shot
            if not current_file:
                self._cached_project_file = None
                self._cached_current_shot = None
                return None

            # Extract just the filename without path and extension
            filename = os.path.basename(current_file)
            name_without_ext = os.path.splitext(filename)[0]

            # Look for shot pattern in the filename (e.g., SQ01-SH010)
            shot_pattern = r'(SQ\d+-SH\d+)'
            match = re.search(shot_pattern, name_without_ext, re.IGNORECASE)

            result = None
            if match:
                result = match.group(1).upper()
            else:
                # If no SQ-SH pattern found, try just SH pattern
                sh_pattern = r'(SH\d+)'
                sh_match = re.search(sh_pattern, name_without_ext, re.IGNORECASE)

                if sh_match:
                    # Try to get SQ from the beginning of the filename
                    sq_pattern = r'(SQ\d+)'
                    sq_match = re.search(sq_pattern, name_without_ext, re.IGNORECASE)

                    if sq_match:
                        result = f"{sq_match.group(1).upper()}-{sh_match.group(1).upper()}"
                    else:
                        result = sh_match.group(1).upper()

            # Update cache
            self._cached_project_file = current_file
            self._cached_current_shot = result

            return result
        except Exception as e:
            print(f"Error extracting shot from project: {e}")
            return None

    def _copyToClipboard(self, text):
        """Copy text to clipboard with error handling"""
        try:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            else:
                # Fallback: try to print to console if clipboard is not available
                print("COPY TO CLIPBOARD:")
                print(text)
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")
            print("COPY TO CLIPBOARD:")
            print(text)

    @err_catcher(name=__name__)
    def getVersionNumber(self, version_str):
        """Extract version number from version string (e.g., v0004 -> 4)"""
        if not version_str:
            return 0

        try:
            # Remove 'v' prefix and convert to int
            if version_str.lower().startswith('v'):
                return int(version_str[1:])
            return int(version_str)
        except Exception:
            return 0
