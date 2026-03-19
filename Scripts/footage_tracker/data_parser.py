# -*- coding: utf-8 -*-
"""
Data Parser Module
Handles parsing of footage and composition data from After Effects
"""

import os
import re
import json
from qtpy.QtWidgets import QApplication
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
        """Parse footage data from AppleScript result"""
        try:
            footageData = str(result).replace("b'", "").replace("'", "").split('::ITEM::')
            parsed_footage = []

            for footage in footageData:
                if not footage or '|||' not in footage:
                    continue

                parts = footage.split('|||')
                if len(parts) < 9:
                    continue

                footageId, name, path, width, height, fps, duration, startFrame, endFrame = parts
                path = path.replace('\\\\', '/')

                # Try to read frame range and FPS from export JSON first
                json_data = self.readExportJSON(path)

                if json_data:
                    # Use JSON data for frame range and FPS
                    startFrame = json_data.get('startFrame', startFrame)
                    endFrame = json_data.get('endFrame', endFrame)
                    fps = json_data.get('fps', fps)
                    width = json_data.get('width', width)
                    height = json_data.get('height', height)
                    duration = json_data.get('duration', duration)

                parsed_footage.append({
                    'footageId': footageId,
                    'name': name,
                    'path': path,
                    'width': width,
                    'height': height,
                    'fps': fps,
                    'duration': duration,
                    'startFrame': startFrame,
                    'endFrame': endFrame
                })

            return parsed_footage
        except Exception as e:
            self.core.popup(f"Error parsing footage data:\n{str(e)}")
            return []

    @err_catcher(name=__name__)
    def parseCompData(self, result):
        """Parse composition data from AppleScript result"""
        try:
            compData = str(result).replace("b'", "").replace("'", "").split('::COMP::')
            parsed_comps = []

            for comp in compData:
                if not comp or '|||' not in comp:
                    continue

                parts = comp.split('|||')
                # We expect 18 parts now with all fields
                if len(parts) < 18:
                    continue

                # Extract all the parts we need
                # Clean up inPoint - sometimes it contains unexpected data like "1220::ITEM::188"
                inPoint = parts[8]
                # Remove any non-numeric characters except decimal point and minus
                inPoint_clean = re.sub(r'[^\d.-]', '', inPoint) if inPoint else '0'
                if not inPoint_clean:
                    inPoint_clean = '0'

                compInfo = {
                    'compId': parts[0],
                    'name': parts[1],
                    'width': parts[2],
                    'height': parts[3],
                    'pixelAspect': parts[4],
                    'duration': parts[5],
                    'frameRate': parts[6],
                    'frameDuration': parts[7],
                    'inPoint': parts[8],
                    'outPoint': parts[9],
                    'displayStartFrame': parts[10],
                    'workAreaStart': parts[11],
                    'workAreaDuration': parts[12],
                    'startFrame': parts[13],
                    'endFrame': parts[14],
                    'isPrecomp': parts[15] == 'true',
                    'parentComps': parts[16] if len(parts) > 16 else "",
                    'numLayers': parts[17] if len(parts) > 17 else "",
                    'displayStartTime': inPoint_clean  # Use cleaned value
                }

                # Determine comp category
                compInfo['category'] = "Pre-comps" if compInfo['isPrecomp'] else "Main Comps"

                parsed_comps.append(compInfo)

            return parsed_comps
        except Exception as e:
            self.core.popup(f"Error parsing composition data:\n{str(e)}")
            return []

    @err_catcher(name=__name__)
    def getFootageAppleScript(self):
        """Get AppleScript for fetching footage data"""
        return """
        var footageList = [];
        for (var i = 1; i <= app.project.numItems; i++) {
            var item = app.project.item(i);
            if (item instanceof FootageItem && item.mainSource instanceof FileSource) {
                var fps = 'N/A';
                var duration = 'N/A';
                var startFrame = 'N/A';
                var endFrame = 'N/A';
                var width = 'N/A';
                var height = 'N/A';

                try {
                    // conformFrameRate is 0 when footage uses its native rate — fall back to nativeFrameRate
                    var conformRate = item.mainSource.conformFrameRate;
                    fps = (conformRate > 0 ? conformRate : item.mainSource.nativeFrameRate).toFixed(2);
                } catch(e) {}

                try {
                    duration = item.duration.toFixed(2);
                } catch(e) {}

                try {
                    width = item.width.toString();
                    height = item.height.toString();
                } catch(e) {}

                // Calculate frame range
                try {
                    if (fps != 'N/A' && duration != 'N/A') {
                        var fpsFloat = parseFloat(fps);
                        var durationFloat = parseFloat(duration);
                        var fileName = item.mainSource.file.name;

                        // Check if this is a video file (mp4, mov, etc.)
                        var isVideoFile = /\\.(mp4|mov|avi|mkv|flv|wmv|webm|m4v|m4p|mpg|mpeg|mp2|webm)$/i.test(fileName);

                        var startFrameNum = 0;
                        var frameCount = Math.round(durationFloat * fpsFloat);

                        if (isVideoFile) {
                            // For video files (2D renders), use 0-based frame range
                            // Kitsu frame range will be used for display in tree renderer
                            startFrame = 0;
                            endFrame = frameCount - 1;
                        } else {
                            // For image sequences, try to extract frame number from filename
                            var frameMatch = fileName.match(/(\\d{4,6})\\.\\w+$/);
                            if (frameMatch) {
                                startFrameNum = parseInt(frameMatch[1], 10);
                            }
                            startFrame = startFrameNum;
                            endFrame = startFrameNum + frameCount - 1;
                        }
                    }
                } catch(e) {}

                footageList.push(
                    item.id + '|||' +
                    item.name + '|||' +
                    item.mainSource.file.fsName + '|||' +
                    width + '|||' +
                    height + '|||' +
                    fps + '|||' +
                    duration + '|||' +
                    startFrame + '|||' +
                    endFrame
                );
            }
        }
        footageList.join('::ITEM::');
        """

    @err_catcher(name=__name__)
    def getCompAppleScript(self):
        """Get AppleScript for fetching composition data"""
        return """
        var compList = [];
        for (var i = 1; i <= app.project.numItems; i++) {
            var item = app.project.item(i);
            if (item instanceof CompItem) {
                var isPrecomp = false;
                var parentComps = [];

                // Check if this comp is used as a layer in other comps
                for (var j = 1; j <= app.project.numItems; j++) {
                    var parentItem = app.project.item(j);
                    if (parentItem instanceof CompItem) {
                        for (var k = 1; k <= parentItem.numLayers; k++) {
                            var layer = parentItem.layer(k);
                            if (layer.source === item) {
                                isPrecomp = true;
                                parentComps.push(parentItem.name);
                                break;
                            }
                        }
                    }
                }

                var compInfo = {
                    id: item.id,
                    name: item.name,
                    width: item.width,
                    height: item.height,
                    pixelAspect: item.pixelAspect,
                    duration: item.duration.toFixed(2),
                    frameRate: item.frameRate.toFixed(2),
                    frameDuration: item.frameDuration.toFixed(6),
                    inPoint: item.displayStartTime.toFixed(2),
                    outPoint: (item.displayStartTime + item.duration).toFixed(2),
                    displayStartFrame: item.displayStartFrame,
                    workAreaStart: item.workAreaStart.toFixed(2),
                    workAreaDuration: item.workAreaDuration.toFixed(2),
                    startFrame: Math.round(item.displayStartTime / item.frameDuration),
                    endFrame: Math.round((item.displayStartTime + item.duration) / item.frameDuration - 1),
                    isPrecomp: isPrecomp,
                    parentComps: parentComps.join(','),
                    numLayers: item.numLayers
                };

                compList.push(
                    compInfo.id + '|||' +
                    compInfo.name + '|||' +
                    compInfo.width + '|||' +
                    compInfo.height + '|||' +
                    compInfo.pixelAspect + '|||' +
                    compInfo.duration + '|||' +
                    compInfo.frameRate + '|||' +
                    compInfo.frameDuration + '|||' +
                    compInfo.inPoint + '|||' +
                    compInfo.outPoint + '|||' +
                    compInfo.displayStartFrame + '|||' +
                    compInfo.workAreaStart + '|||' +
                    compInfo.workAreaDuration + '|||' +
                    compInfo.startFrame + '|||' +
                    compInfo.endFrame + '|||' +
                    (compInfo.isPrecomp ? 'true' : 'false') + '|||' +
                    compInfo.parentComps + '|||' +
                    compInfo.numLayers
                );
            }
        }
        compList.join('::COMP::');
        """

    @err_catcher(name=__name__)
    def extractCurrentShotFromProject(self):
        """Extract the current shot from the .aep file name (cached)"""
        try:
            # Get the current project file path
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