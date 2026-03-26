# -*- coding: utf-8 -*-
"""
After Effects Operations Module
Handles all direct After Effects interactions
"""

import os
import re
import platform
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class AEOperations:
    """Handles all After Effects script execution and operations"""
    
    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

    @err_catcher(name=__name__)
    def updateFootageVersion(self, item, newVersion, userData):
        """Update footage to use a different version"""
        try:
            oldPath = userData['path']

            # Add debug info to tracker's debug log
            self.tracker.debugLog.append(f"updateFootageVersion: oldPath = {oldPath}")

            # Check if this is a 3D render path by looking for EXR files with AOV pattern
            # Check if this is a 3D render path
            # 3D render paths have: 3dRender folder + version folder + AOV subfolder + .exr file
            is_3d_render = False

            path_lower = oldPath.lower()
            if '.exr' in oldPath and '3drender' in path_lower:
                # This looks like a 3D render - verify by checking path structure
                # 3D render paths: .../3dRender/.../v####/<aov_subfolder>/<file>.exr
                # Any subfolder between version folder and the filename counts as an AOV folder.
                path_parts = oldPath.replace('\\', '/').split('/')

                # Find version folder index
                version_idx = -1
                for i, part in enumerate(path_parts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        version_idx = i
                        break

                # If there is at least one path component between version folder and filename,
                # treat it as an AOV subfolder (structure is the signal, not the name).
                if version_idx >= 0 and version_idx + 2 <= len(path_parts) - 1:
                    next_folder = path_parts[version_idx + 1]
                    is_aov = True  # any subfolder after version = AOV folder in 3dRender context
                    if is_aov:
                        is_3d_render = True
                        self.tracker.debugLog.append(
                            f"updateFootageVersion: Detected 3D render via path structure - AOV folder: {next_folder}"
                        )

            if is_3d_render:
                # Handle 3D render paths by reconstructing properly
                # Extract parts from the original path
                path_parts = oldPath.replace('\\', '/').split('/')
                self.tracker.debugLog.append(f"updateFootageVersion: path_parts = {path_parts}")

                # Find the version folder index
                version_idx = -1
                for i, part in enumerate(path_parts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        version_idx = i
                        break

                self.tracker.debugLog.append(f"updateFootageVersion: version_idx = {version_idx}")
                if version_idx >= 0 and version_idx + 1 < len(path_parts):
                    # Check if the next part is an AOV folder (single letter or common multi-letter AOV names)
                    aov_folder = path_parts[version_idx + 1]
                    self.tracker.debugLog.append(
                        f"updateFootageVersion: aov_folder = '{aov_folder}' (len={len(aov_folder)})"
                    )

                    # Any subfolder between version folder and the filename is treated as an AOV folder.
                    # We already confirmed is_3d_render=True by reaching this branch.
                    is_aov_folder = version_idx + 2 <= len(path_parts) - 1

                    if is_aov_folder:
                        # This is a 3D render with AOV folder structure
                        filename = path_parts[-1]  # Last part is filename
                        self.tracker.debugLog.append(f"updateFootageVersion: filename = '{filename}'")

                        # Update version folder
                        path_parts[version_idx] = newVersion
                        self.tracker.debugLog.append(
                            f"updateFootageVersion: After version update: path_parts = {path_parts}"
                        )

                        # Update version in filename
                        new_filename = re.sub(r'_v\d+_', f'_v{newVersion}_', filename)
                        path_parts[-1] = new_filename
                        self.tracker.debugLog.append(f"updateFootageVersion: new_filename = '{new_filename}'")

                        # Reconstruct path with forward slashes (for proper ExtendScript escaping)
                        newPath = '/'.join(path_parts)
                        self.tracker.debugLog.append(f"updateFootageVersion: Final newPath (3D) = {newPath}")
                    else:
                        # Fallback: treat as standard path
                        self.tracker.debugLog.append(
                            "updateFootageVersion: AOV folder not recognized, falling back to 2D logic"
                        )
                        is_3d_render = False
                else:
                    self.tracker.debugLog.append(f"updateFootageVersion: version_idx invalid, falling back to 2D logic")
                    is_3d_render = False

            if not is_3d_render:
                self.tracker.debugLog.append(f"updateFootageVersion: Using 2D render logic")
                # Handle 2D renders and standard paths
                pathParts = oldPath.replace('\\', '/').split('/')

                versionIndex = -1
                oldVersionFolder = None
                for i, part in enumerate(pathParts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        oldVersionFolder = part
                        pathParts[i] = newVersion
                        versionIndex = i
                        break

                if versionIndex == -1:
                    self.core.popup("Could not find version folder in path")
                    return False

                # Get the new version directory path
                newVersionDir = '/'.join(pathParts[:versionIndex + 1])

                # Check if the new version directory exists
                if not os.path.exists(newVersionDir):
                    self.tracker.showSelectableMessage(
                        "Version Folder Does Not Exist",
                        f"Version folder does not exist:\n{newVersionDir}\n\n"
                        f"Old path was: {oldPath}"
                    )
                    return False

                # Get the old filename to match pattern
                oldFilename = os.path.basename(oldPath)

                # Search for actual files in the new version directory
                if os.path.isdir(newVersionDir):
                    try:
                        files = sorted(os.listdir(newVersionDir))

                        # Define footage file extensions to filter out non-footage files (json, txt, etc.)
                        footage_extensions = {
                            '.exr', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.tga', '.bmp', '.psd',
                            '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'
                        }

                        # Extract base pattern from old filename (shot, identifier, etc.)
                        # Match: SQ02-SH010_HighRes_v0002.mov -> SQ02-SH010_HighRes
                        baseMatch = re.match(r'^(.+?)(?:_v\d+)?(?:\[\w+\])?(?:_\(\d+\))?', oldFilename)
                        if baseMatch:
                            basePattern = baseMatch.group(1)
                        elif '_v' in oldFilename:
                            basePattern = oldFilename.split('_v')[0]
                        else:
                            basePattern = oldFilename.rsplit('.', 1)[0]

                        self.tracker.debugLog.append(
                            f"updateFootageVersion: Searching for files matching pattern: {basePattern}"
                        )

                        # Look for files that match the base pattern AND are footage files
                        matchingFiles = []
                        for f in files:
                            # Skip non-footage files (json, txt, etc.)
                            if not any(f.lower().endswith(ext) for ext in footage_extensions):
                                continue

                            # Check if file matches our base pattern
                            fileBase = re.match(r'^(.+?)(?:_v\d+)?(?:\[\w+\])?(?:_\(\d+\))?(?:\.\w+)?', f)
                            if fileBase and fileBase.group(1) == basePattern:
                                matchingFiles.append(f)

                        self.tracker.debugLog.append(
                            f"updateFootageVersion: Found {len(matchingFiles)} matching files: {matchingFiles[:5]}"
                        )

                        if matchingFiles:
                            # Prefer video files first (.mp4, .mov)
                            videoFiles = [
                                f for f in matchingFiles if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))
                            ]
                            if videoFiles:
                                newPath = os.path.join(newVersionDir, videoFiles[0]).replace('\\', '/')
                                self.tracker.debugLog.append(f"updateFootageVersion: Using video file: {newPath}")
                            else:
                                # Use first sequence file found (prefer files with frame numbers)
                                seqFiles = [f for f in matchingFiles if re.search(r'[._]\d{4,5}[._]', f)]
                                if seqFiles:
                                    newPath = os.path.join(newVersionDir, seqFiles[0]).replace('\\', '/')
                                    self.tracker.debugLog.append(
                                        f"updateFootageVersion: Using sequence file: {newPath}"
                                    )
                                else:
                                    # Fallback to first matching file
                                    newPath = os.path.join(newVersionDir, matchingFiles[0]).replace('\\', '/')
                                    self.tracker.debugLog.append(
                                        f"updateFootageVersion: Using fallback file: {newPath}"
                                    )
                        else:
                            # No matching files found - try to construct filename
                            newFilename = (
                                oldFilename.replace(oldVersionFolder, newVersion) if oldVersionFolder else oldFilename
                            )
                            newPath = os.path.join(newVersionDir, newFilename).replace('\\', '/')
                            self.tracker.debugLog.append(
                                f"updateFootageVersion: No matches, constructed path: {newPath}"
                            )
                    except Exception as e:
                        self.tracker.debugLog.append(f"updateFootageVersion: Error searching directory: {e}")
                        # Fallback to simple path construction
                        newFilename = (
                            oldFilename.replace(oldVersionFolder, newVersion) if oldVersionFolder else oldFilename
                        )
                        newPath = os.path.join(newVersionDir, newFilename).replace('\\', '/')
                else:
                    # Directory doesn't exist - construct path anyway and let error handling catch it
                    newFilename = (
                        oldFilename.replace(oldVersionFolder, newVersion) if oldVersionFolder else oldFilename
                    )
                    newPath = os.path.join(newVersionDir, newFilename).replace('\\', '/')

            newIsSequence = self.tracker.utils.isSequence(newPath)

            if newIsSequence:
                newPath = self.tracker.utils.ensureSequencePath(newPath)
            else:
                newPath = self.tracker.utils.ensureStillPath(newPath)

            if not os.path.exists(newPath):
                self.tracker.showSelectableMessage(
                    "Path Does Not Exist",
                    f"Path does not exist:\n{newPath}\n\n"
                    f"Old path was: {oldPath}\n"
                    f"New is sequence: {newIsSequence}\n\n"
                    f"Please check if the version folder exists."
                )
                return False

            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var isSequence = item.mainSource.isStill ? 'STILL' : 'SEQUENCE';
                    var fps = item.mainSource.conformFrameRate;
                    isSequence + '|||' + fps;
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            propsResult = self.main.ae_core.executeAppleScript(scpt)
            propsStr = str(propsResult).replace("b'", "").replace("'", "").strip()

            if 'ERROR' in propsStr:
                self.tracker.showSelectableMessage(
                    "Failed to Get Footage Properties",
                    f"Failed to get footage properties:\n{propsStr}"
                )
                return False

            props = propsStr.split('|||')
            originalFPS = float(props[1]) if len(props) > 1 else 25.0

            # The type is determined by what files exist in the new version folder
            # newIsSequence was already determined above by checking actual files
            # Now use that type to decide which AE method to use
            self.tracker.debugLog.append(f"updateFootageVersion: newIsSequence={newIsSequence}, newPath={newPath}")

            # Normalize path separators and escape for ExtendScript
            # First ensure all separators are forward slashes, then escape for Windows
            normalizedPath = newPath.replace('\\', '/')
            if platform.system() == "Windows":
                aePath = normalizedPath.replace('/', '\\\\')
            else:
                aePath = normalizedPath

            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var file = new File('{aePath}');
                    if (!file.exists) {{
                        'ERROR: File not found by After Effects - ' + file.fsName;
                    }} else {{
                        var originalFPS = {originalFPS};

                        // Use the NEW version's actual type (detected from files)
                        // If new version is a sequence: use replaceWithSequence
                        // If new version is a still: use replace
                        {'item.replaceWithSequence(file, false);' if newIsSequence else 'item.replace(file);'}

                        // Explicitly disable alphabetical ordering for sequences
                        {'item.mainSource.alphabeticOrder = false;' if newIsSequence else ''}

                        try {{
                            item.mainSource.conformFrameRate = originalFPS;
                        }} catch(e) {{}}

                        'SUCCESS';
                    }}
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                userData['path'] = newPath

                # Extract base version (v0003) from full version (v0003 (mp4)) for status comparison
                baseVersionMatch = re.match(r'(v\d+)', newVersion)
                newVersionBase = baseVersionMatch.group(1) if baseVersionMatch else newVersion

                # Update userData with both base and full versions
                userData['currentVersion'] = newVersionBase  # Base version for status check
                userData['currentVersionFull'] = newVersion  # Full version for dropdown
                item.setText(6, newPath)

                # Compare base versions for status (ignore suffixes like "(mp4)")
                if newVersionBase == userData['latestVersion']:
                    item.setText(2, "✓ Up to date")
                    item.setForeground(2, QBrush(QColor(100, 200, 100)))
                    item.setData(2, Qt.UserRole + 1, "current")
                else:
                    item.setText(2, "⚠ Outdated")
                    item.setForeground(2, QBrush(QColor(255, 150, 50)))
                    item.setData(2, Qt.UserRole + 1, "outdated")

                self.tracker.updateStatistics()
                self.tracker.dlg_footage.statusBar.setText(f"Updated to {newVersion}")
                QTimer.singleShot(3000, lambda: self.tracker.updateStatistics())
                # Reload footage data to refresh compositions that use this footage
                self.tracker.loadFootageData()
                return True
            else:
                self.tracker.showSelectableMessage(
                    "Failed to Update Footage",
                    f"Failed to update footage in After Effects\n\nDetails: {resultStr}"
                )
                return False

        except Exception as e:
            import traceback
            self.tracker.showSelectableMessage(
                "Error Updating Footage",
                f"Error:\n{str(e)}\n\n{traceback.format_exc()}"
            )
            return False

    @err_catcher(name=__name__)
    def _updateFootageVersionNoRefresh(self, item, newVersion, userData):
        """Update footage version in After Effects WITHOUT refreshing the tree

        This is used for batch updates where we want to refresh once at the end.
        Returns True if successful, False otherwise.
        """
        try:
            oldPath = userData['path']

            # Check if this is a 3D render path by looking for EXR files with AOV pattern
            is_3d_render = False

            if '.exr' in oldPath:
                filename_pattern = r'([A-Z0-9\-_]+)[_-]v(\d+)_([A-Za-z])\.(\d+)\.exr'
                filename_match = re.search(filename_pattern, oldPath)
                if filename_match:
                    is_3d_render = True

            if is_3d_render:
                # Handle 3D render paths
                path_parts = oldPath.replace('\\', '/').split('/')
                version_idx = -1
                for i, part in enumerate(path_parts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        version_idx = i
                        break

                if version_idx >= 0 and version_idx + 1 < len(path_parts):
                    aov_folder = path_parts[version_idx + 1]
                    if len(aov_folder) == 1 and aov_folder.isalpha():
                        filename = path_parts[-1]
                        path_parts[version_idx] = newVersion
                        new_filename = re.sub(r'_v\d+_', f'_v{newVersion}_', filename)
                        path_parts[-1] = new_filename
                        newPath = '/'.join(path_parts)
                        if '\\' in oldPath:
                            newPath = newPath.replace('/', '\\')
                    else:
                        is_3d_render = False
                else:
                    is_3d_render = False

            if not is_3d_render:
                # Handle 2D renders and standard paths
                pathParts = oldPath.replace('\\', '/').split('/')
                versionIndex = -1
                oldVersionFolder = None
                for i, part in enumerate(pathParts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        oldVersionFolder = part
                        pathParts[i] = newVersion
                        versionIndex = i
                        break

                if versionIndex == -1:
                    return False

                newPath = '/'.join(pathParts)

                if oldVersionFolder:
                    filename = os.path.basename(newPath)
                    if oldVersionFolder in filename:
                        newFilename = filename.replace(oldVersionFolder, newVersion)
                        newPath = os.path.join(os.path.dirname(newPath), newFilename).replace('\\', '/')

            newIsSequence = self.tracker.utils.isSequence(newPath)

            if newIsSequence:
                newPath = self.tracker.utils.ensureSequencePath(newPath)
            else:
                newPath = self.tracker.utils.ensureStillPath(newPath)

            if not os.path.exists(newPath):
                return False

            # Get original FPS
            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var fps = item.mainSource.conformFrameRate;
                    fps.toString();
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            propsResult = self.main.ae_core.executeAppleScript(scpt)
            propsStr = str(propsResult).replace("b'", "").replace("'", "").strip()

            if 'ERROR' in propsStr:
                return False

            originalFPS = float(propsStr) if propsStr and propsStr != 'ERROR' else 25.0

            if not os.path.exists(newPath):
                return False

            # Normalize path separators and escape for ExtendScript
            normalizedPath = newPath.replace('\\', '/')
            if platform.system() == "Windows":
                aePath = normalizedPath.replace('/', '\\\\')
            else:
                aePath = normalizedPath

            # Update footage in After Effects
            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var file = new File('{aePath}');
                    if (!file.exists) {{
                        'ERROR: File not found';
                    }} else {{
                        var originalFPS = {originalFPS};
                        // Use the NEW version's actual type (detected from files)
                        {'item.replaceWithSequence(file, false);' if newIsSequence else 'item.replace(file);'}

                        // Explicitly disable alphabetical ordering for sequences
                        {'item.mainSource.alphabeticOrder = false;' if newIsSequence else ''}

                        try {{
                            item.mainSource.conformFrameRate = originalFPS;
                        }} catch(e) {{}}
                        'SUCCESS';
                    }}
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                # Update userData but don't refresh
                userData['path'] = newPath
                userData['currentVersion'] = newVersion
                item.setText(6, newPath)
                return True
            else:
                return False

        except Exception:
            return False

        return False

    @err_catcher(name=__name__)
    def updateMultipleFootageVersions(self, compatibleItems, newVersion):
        """Update multiple footage items to use a different version"""
        if not compatibleItems:
            self.core.popup("No compatible footage items to update.")
            return

        successCount = 0
        failedCount = 0
        failedItems = []

        self.tracker.dlg_footage.statusBar.setText(f"Updating {len(compatibleItems)} footage items to {newVersion}...")

        for i, (item, userData) in enumerate(compatibleItems):
            try:
                # Update progress
                self.tracker.dlg_footage.statusBar.setText(
                    f"Updating {i+1}/{len(compatibleItems)}: {item.text(0)} to {newVersion}"
                )
                QApplication.processEvents()  # Update UI

                # Reuse the existing single-item update logic
                if self._updateSingleFootageVersion(item, newVersion, userData):
                    successCount += 1
                else:
                    failedCount += 1
                    failedItems.append(item.text(0))

            except Exception as e:
                failedCount += 1
                failedItems.append(f"{item.text(0)}: {str(e)}")

        # Show results
        if failedCount > 0:
            failedText = "\n".join(failedItems[:10])  # Limit to first 10 items
            if len(failedItems) > 10:
                failedText += f"\n... and {len(failedItems) - 10} more items"

            self.tracker.showSelectableMessage(
                "Update Complete with Errors",
                f"Successfully updated {successCount} footage item(s) to {newVersion}.\n"
                f"Failed to update {failedCount} footage item(s):\n\n"
                f"{failedText}"
            )
        else:
            self.tracker.dlg_footage.statusBar.setText(
                f"Successfully updated {successCount} footage item(s) to {newVersion}"
            )
            QTimer.singleShot(3000, lambda: self.tracker.updateStatistics())

        # Reload footage data to refresh compositions that use this footage
        self.tracker.loadFootageData()

    def _updateSingleFootageVersion(self, item, newVersion, userData):
        """Internal method to update a single footage item (extracted from updateFootageVersion)"""
        try:
            oldPath = userData['path']

            # Check if this is a 3D render path (contains single-letter AOV folder)
            # Pattern: .../v0007/Z/SQ01-SH010_Lighting_v0007_Z.1001.exr
            oldPath_normalized = oldPath.replace('\\', '/')
            aov_match = re.search(r'/(v\d+)/([A-Za-z])/([^/]+\.exr)$', oldPath_normalized)
            if aov_match:
                # This is a 3D render path with AOV folder
                version_folder, aov_folder, filename = aov_match.groups()

                # Update the version folder
                new_path = oldPath.replace('/' + version_folder + '/', '/' + newVersion + '/')

                # Update the version in the filename
                new_filename = filename.replace('_' + version_folder + '_', '_' + newVersion + '_')
                new_path = new_path.replace(filename, new_filename)

                newPath = new_path.replace('\\', '/')
            else:
                # Handle 2D renders and standard paths
                pathParts = oldPath.replace('\\', '/').split('/')

                versionIndex = -1
                oldVersionFolder = None
                for i, part in enumerate(pathParts):
                    if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                        oldVersionFolder = part
                        pathParts[i] = newVersion
                        versionIndex = i
                        break

                if versionIndex == -1:
                    return False

                newPath = '/'.join(pathParts)

                if oldVersionFolder:
                    filename = os.path.basename(newPath)
                    if oldVersionFolder in filename:
                        newFilename = filename.replace(oldVersionFolder, newVersion)
                        newPath = os.path.join(os.path.dirname(newPath), newFilename).replace('\\', '/')

            newIsSequence = self.tracker.utils.isSequence(newPath)

            if newIsSequence:
                newPath = self.tracker.utils.ensureSequencePath(newPath)
            else:
                newPath = self.tracker.utils.ensureStillPath(newPath)

            if not os.path.exists(newPath):
                return False

            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var fps = item.mainSource.conformFrameRate;
                    fps.toString();
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            propsResult = self.main.ae_core.executeAppleScript(scpt)
            propsStr = str(propsResult).replace("b'", "").replace("'", "").strip()

            if 'ERROR' in propsStr:
                return False

            originalFPS = float(propsStr) if propsStr and propsStr != 'ERROR' else 25.0

            # Normalize path separators and escape for ExtendScript
            normalizedPath = newPath.replace('\\', '/')
            if platform.system() == "Windows":
                aePath = normalizedPath.replace('/', '\\\\')
            else:
                aePath = normalizedPath

            scpt = f"""
            try {{
                var item = app.project.itemByID({userData['id']});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    'ERROR: Invalid item';
                }} else {{
                    var file = new File('{aePath}');
                    if (!file.exists) {{
                        'ERROR: File not found';
                    }} else {{
                        var originalFPS = {originalFPS};

                        {'item.replaceWithSequence(file, false);' if newIsSequence else 'item.replace(file);'}

                        // Explicitly disable alphabetical ordering for sequences
                        {'item.mainSource.alphabeticOrder = false;' if newIsSequence else ''}

                        try {{
                            item.mainSource.conformFrameRate = originalFPS;
                        }} catch(e) {{}}

                        'SUCCESS';
                    }}
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """

            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                userData['path'] = newPath
                userData['currentVersion'] = newVersion
                item.setText(6, newPath)

                if newVersion == userData['latestVersion']:
                    item.setText(2, "✓ Up to date")
                    item.setForeground(2, QBrush(QColor(100, 200, 100)))
                    item.setData(2, Qt.UserRole + 1, "current")
                else:
                    item.setText(2, "⚠ Outdated")
                    item.setForeground(2, QBrush(QColor(255, 150, 50)))
                    item.setData(2, Qt.UserRole + 1, "outdated")

                # Update the combo box to reflect the change
                versionWidget = self.tracker.tw_footage.itemWidget(item, 1)
                if versionWidget and versionWidget.layout().count() > 0:
                    combo = versionWidget.layout().itemAt(0).widget()
                    if isinstance(combo, QComboBox):
                        combo.blockSignals(True)
                        combo.setCurrentText(newVersion)
                        combo.blockSignals(False)

                return True

        except Exception:
            return False

        return False

    @err_catcher(name=__name__)
    def updateFootageFPS(self, item, fps, userData):
        """Update footage FPS in After Effects"""
        try:
            footageId = userData['id']
            scpt = f"""
            try {{
                var item = app.project.itemByID({footageId});
                if (!item) {{
                    'ERROR: Item not found';
                }} else if (!item.mainSource) {{
                    'ERROR: No main source';
                }} else {{
                    item.mainSource.conformFrameRate = {fps};
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()
            
            if 'SUCCESS' in resultStr:
                self.tracker.dlg_footage.statusBar.setText(f"Updated FPS to {fps}")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
                # Reload footage data to refresh compositions that use this footage
                self.tracker.loadFootageData()
            else:
                errorMsg = f"Failed to update FPS in After Effects\n\nDetails: {resultStr}"
                self.core.popup(errorMsg)
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating FPS:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def updateCompFPS(self, item, fps, compInfo):
        """Update composition FPS in After Effects"""
        try:
            compId = compInfo['compId']
            scpt = f"""
            try {{
                var comp = app.project.itemByID({compId});
                if (!comp) {{
                    'ERROR: Composition not found';
                }} else {{
                    comp.frameRate = {fps};
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                self.tracker.dlg_footage.statusBar.setText(f"Updated comp FPS to {fps}")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
                # Reload footage data to update the tree
                self.tracker.loadFootageData()
            else:
                errorMsg = f"Failed to update comp FPS in After Effects\n\nDetails: {resultStr}"
                self.core.popup(errorMsg)
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp FPS:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def updateCompFrameRange(self, item, startFrame, endFrame, compInfo):
        """Update composition frame range in After Effects"""
        try:
            compId = compInfo['compId']
            compFps = float(compInfo['frameRate'])

            # Reverse the formula to calculate displayStartTime and duration
            # actual_start_frame = round(displayStartTime * comp_fps)
            # actual_end_frame = round((displayStartTime + duration) * comp_fps - 1)
            # displayStartTime = actual_start_frame / comp_fps
            # duration = (actual_end_frame + 1) / comp_fps - displayStartTime

            new_display_start_time = startFrame / compFps
            new_duration = (endFrame + 1) / compFps - new_display_start_time

            scpt = f"""
            try {{
                var comp = app.project.itemByID({compId});
                if (!comp) {{
                    'ERROR: Composition not found';
                }} else {{
                    comp.displayStartTime = {new_display_start_time};
                    comp.duration = {new_duration};
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                self.tracker.dlg_footage.statusBar.setText(f"Updated comp frame range to {startFrame}-{endFrame}")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
                # Reload footage data to update the tree
                self.tracker.loadFootageData()
            else:
                errorMsg = f"Failed to update comp frame range in After Effects\n\nDetails: {resultStr}"
                self.core.popup(errorMsg)
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp frame range:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def updateCompResolution(self, item, width, height, compInfo):
        """Update composition resolution in After Effects"""
        try:
            compId = compInfo['compId']
            scpt = f"""
            try {{
                var comp = app.project.itemByID({compId});
                if (!comp) {{
                    'ERROR: Composition not found';
                }} else {{
                    comp.width = {width};
                    comp.height = {height};
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            resultStr = str(result).replace("b'", "").replace("'", "").strip()

            if 'SUCCESS' in resultStr:
                self.tracker.dlg_footage.statusBar.setText(f"Updated comp resolution to {width}x{height}")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
                # Reload footage data to update the tree
                self.tracker.loadFootageData()
            else:
                errorMsg = f"Failed to update comp resolution in After Effects\n\nDetails: {resultStr}"
                self.core.popup(errorMsg)
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp resolution:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def updateAllOutdated(self):
        """Update all outdated footage to latest versions"""
        outdatedItems = []

        def findOutdated(item):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'footage':
                if item.data(2, Qt.UserRole + 1) == "outdated":
                    outdatedItems.append(item)

            for i in range(item.childCount()):
                findOutdated(item.child(i))

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            findOutdated(self.tracker.tw_footage.topLevelItem(i))

        if not outdatedItems:
            self.core.popup("All footage is already up to date!")
            return

        reply = QMessageBox.question(
            self.tracker.dlg_footage,
            "Update All Outdated",
            f"Update {len(outdatedItems)} outdated footage items?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        successCount = 0
        failedCount = 0
        skippedCount = 0

        for item in outdatedItems:
            try:
                userData = item.data(0, Qt.UserRole)
                combo = self.tracker.tw_footage.itemWidget(item, 1)

                if combo and combo.layout().count() > 0:
                    actual_combo = combo.layout().itemAt(0).widget()
                    if isinstance(actual_combo, QComboBox):
                        # Determine the latest version to use
                        latestVersion = None

                        # First try userData['latestVersion'] (for 3D renders with versionInfo)
                        if 'latestVersion' in userData:
                            latestVersion = userData['latestVersion']
                        else:
                            # For 2D renders and others - get first item from combo (usually the latest)
                            if actual_combo.count() > 0:
                                latestVersion = actual_combo.itemText(0)

                        if not latestVersion:
                            skippedCount += 1
                            continue

                        # Block signals to prevent triggering updateFootageVersion during the update
                        # We'll manually call the update logic and refresh once at the end
                        actual_combo.blockSignals(True)
                        actual_combo.setCurrentText(latestVersion)

                        # Manually call the version update (this will update AE but not refresh the tree)
                        if self._updateFootageVersionNoRefresh(item, latestVersion, userData):
                            # Extract base version for comparison (ignore suffixes like "(mp4)")
                            latestVersionMatch = re.match(r'(v\d+)', latestVersion)
                            latestVersionBase = latestVersionMatch.group(1) if latestVersionMatch else latestVersion
                            userLatestVersion = userData.get('latestVersion', '')

                            # Update combo box to reflect the change
                            if latestVersionBase == userLatestVersion:
                                item.setText(2, "✓ Up to date")
                                item.setForeground(2, QBrush(QColor(100, 200, 100)))
                                item.setData(2, Qt.UserRole + 1, "current")
                                successCount += 1
                            else:
                                item.setText(2, "⚠ Outdated")
                                item.setForeground(2, QBrush(QColor(255, 150, 50)))
                                item.setData(2, Qt.UserRole + 1, "outdated")
                                failedCount += 1
                        else:
                            failedCount += 1

                        actual_combo.blockSignals(False)
                else:
                    skippedCount += 1
            except RuntimeError:
                # Item was deleted during processing (tree was rebuilt)
                # Skip this item and continue
                skippedCount += 1
                continue

        # Build result message
        msg_parts = []
        if successCount > 0:
            msg_parts.append(f"Updated {successCount} footage item(s)")
        if failedCount > 0:
            msg_parts.append(f"Failed to update {failedCount} footage item(s)")
        if skippedCount > 0:
            msg_parts.append(f"Skipped {skippedCount} item(s) without versioning (2D renders, resources, etc.)")

        if msg_parts:
            result_msg = "\n".join(msg_parts)
            if failedCount > 0:
                self.tracker.showSelectableMessage(
                    "Update Complete with Errors",
                    result_msg
                )
            elif successCount > 0:
                self.core.popup(f"Successfully updated:\n{result_msg}")
            else:
                # Only skipped items, no updates or failures
                self.core.popup(f"Version update:\n{result_msg}")
        else:
            self.core.popup("No items were updated.")

        # Update statistics to reflect the changes
        self.tracker.updateStatistics()

    @err_catcher(name=__name__)
    def updateSelectedOutdated(self):
        """Update selected outdated footage to latest versions"""
        selectedOutdatedItems = []

        def findSelectedFootage(item):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'footage':
                if item.isSelected() and item.data(2, Qt.UserRole + 1) == "outdated":
                    selectedOutdatedItems.append(item)

        for item in self.tracker.tw_footage.selectedItems():
            findSelectedFootage(item)

        if not selectedOutdatedItems:
            self.core.popup("No selected outdated footage found!\n\nPlease select one or more outdated footage items.")
            return

        reply = QMessageBox.question(
            self.tracker.dlg_footage,
            "Update Selected Outdated",
            f"Update {len(selectedOutdatedItems)} selected outdated footage items?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        successCount = 0
        failedCount = 0
        skippedCount = 0

        for item in selectedOutdatedItems:
            try:
                userData = item.data(0, Qt.UserRole)
                combo = self.tracker.tw_footage.itemWidget(item, 1)

                if combo and combo.layout().count() > 0:
                    actual_combo = combo.layout().itemAt(0).widget()
                    if isinstance(actual_combo, QComboBox):
                        # Determine the latest version to use
                        latestVersion = None

                        # First try userData['latestVersion'] (for 3D renders with versionInfo)
                        if 'latestVersion' in userData:
                            latestVersion = userData['latestVersion']
                        else:
                            # For 2D renders and others - get first item from combo (usually the latest)
                            if actual_combo.count() > 0:
                                latestVersion = actual_combo.itemText(0)

                        if not latestVersion:
                            skippedCount += 1
                            continue

                        # Block signals to prevent triggering updateFootageVersion during the update
                        # We'll manually call the update logic and refresh once at the end
                        actual_combo.blockSignals(True)
                        actual_combo.setCurrentText(latestVersion)

                        # Manually call the version update (this will update AE but not refresh the tree)
                        if self._updateFootageVersionNoRefresh(item, latestVersion, userData):
                            # Extract base version for comparison (ignore suffixes like "(mp4)")
                            latestVersionMatch = re.match(r'(v\d+)', latestVersion)
                            latestVersionBase = latestVersionMatch.group(1) if latestVersionMatch else latestVersion
                            userLatestVersion = userData.get('latestVersion', '')

                            # Update combo box to reflect the change
                            if latestVersionBase == userLatestVersion:
                                item.setText(2, "✓ Up to date")
                                item.setForeground(2, QBrush(QColor(100, 200, 100)))
                                item.setData(2, Qt.UserRole + 1, "current")
                                successCount += 1
                            else:
                                item.setText(2, "⚠ Outdated")
                                item.setForeground(2, QBrush(QColor(255, 150, 50)))
                                item.setData(2, Qt.UserRole + 1, "outdated")
                                failedCount += 1
                        else:
                            failedCount += 1

                        actual_combo.blockSignals(False)
                else:
                    skippedCount += 1
            except RuntimeError:
                # Item was deleted during processing (tree was rebuilt)
                # Skip this item and continue
                skippedCount += 1
                continue

        # Build result message
        msg_parts = []
        if successCount > 0:
            msg_parts.append(f"Updated {successCount} footage item(s)")
        if failedCount > 0:
            msg_parts.append(f"Failed to update {failedCount} footage item(s)")
        if skippedCount > 0:
            msg_parts.append(f"Skipped {skippedCount} item(s) without versioning (2D renders, resources, etc.)")

        if msg_parts:
            result_msg = "\n".join(msg_parts)
            if failedCount > 0:
                self.tracker.showSelectableMessage(
                    "Update Complete with Errors",
                    result_msg
                )
            elif successCount > 0:
                self.core.popup(f"Successfully updated:\n{result_msg}")
            else:
                # Only skipped items, no updates or failures
                self.core.popup(f"Version update:\n{result_msg}")
        else:
            self.core.popup("No items were updated.")

        # Reload footage data to refresh compositions that use this footage
        if successCount > 0:
            self.tracker.loadFootageData(preserve_scroll=True)

    @err_catcher(name=__name__)
    def updateSpecificOutdated(self, paths):
        """Update specific outdated footage items by their paths"""
        if not paths:
            self.core.popup("No items provided to update.")
            return

        # Find tree items matching the given paths
        targetItems = []

        def findItemByPath(item, targetPaths):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'footage':
                itemPath = userData.get('path', '')
                if itemPath in targetPaths:
                    targetItems.append(item)

            for i in range(item.childCount()):
                findItemByPath(item.child(i), targetPaths)

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            findItemByPath(self.tracker.tw_footage.topLevelItem(i), set(paths))

        if not targetItems:
            self.core.popup("No matching footage items found in the tree.")
            return

        successCount = 0
        failedCount = 0
        skippedCount = 0

        for item in targetItems:
            try:
                userData = item.data(0, Qt.UserRole)
                combo = self.tracker.tw_footage.itemWidget(item, 1)

                if combo and combo.layout().count() > 0:
                    actual_combo = combo.layout().itemAt(0).widget()
                    if isinstance(actual_combo, QComboBox):
                        # Determine the latest version to use
                        latestVersion = None

                        # First try userData['latestVersion'] (for 3D renders with versionInfo)
                        if 'latestVersion' in userData:
                            latestVersion = userData['latestVersion']
                        else:
                            # For 2D renders and others - get first item from combo (usually the latest)
                            if actual_combo.count() > 0:
                                latestVersion = actual_combo.itemText(0)

                        if not latestVersion:
                            skippedCount += 1
                            continue

                        # Block signals to prevent triggering updateFootageVersion during the update
                        # We'll manually call the update logic and refresh once at the end
                        actual_combo.blockSignals(True)
                        actual_combo.setCurrentText(latestVersion)

                        # Manually call the version update (this will update AE but not refresh the tree)
                        if self._updateFootageVersionNoRefresh(item, latestVersion, userData):
                            # Extract base version for comparison (ignore suffixes like "(mp4)")
                            latestVersionMatch = re.match(r'(v\d+)', latestVersion)
                            latestVersionBase = latestVersionMatch.group(1) if latestVersionMatch else latestVersion
                            userLatestVersion = userData.get('latestVersion', '')

                            # Update combo box to reflect the change
                            if latestVersionBase == userLatestVersion:
                                item.setText(2, "✓ Up to date")
                                item.setForeground(2, QBrush(QColor(100, 200, 100)))
                                item.setData(2, Qt.UserRole + 1, "current")
                                successCount += 1
                            else:
                                item.setText(2, "⚠ Outdated")
                                item.setForeground(2, QBrush(QColor(255, 150, 50)))
                                item.setData(2, Qt.UserRole + 1, "outdated")
                                failedCount += 1
                        else:
                            failedCount += 1

                        actual_combo.blockSignals(False)
                else:
                    skippedCount += 1
            except RuntimeError:
                # Item was deleted during processing (tree was rebuilt)
                # Skip this item and continue
                skippedCount += 1
                continue

        # Build result message
        msg_parts = []
        if successCount > 0:
            msg_parts.append(f"Updated {successCount} footage item(s)")
        if failedCount > 0:
            msg_parts.append(f"Failed to update {failedCount} footage item(s)")
        if skippedCount > 0:
            msg_parts.append(f"Skipped {skippedCount} item(s) without versioning (2D renders, resources, etc.)")

        if msg_parts:
            result_msg = "\n".join(msg_parts)
            if failedCount > 0:
                self.tracker.showSelectableMessage(
                    "Update Complete with Errors",
                    result_msg
                )
            elif successCount > 0:
                self.core.popup(f"Successfully updated:\n{result_msg}")
            else:
                # Only skipped items, no updates or failures
                self.core.popup(f"Version update:\n{result_msg}")
        else:
            self.core.popup("No items were updated.")

        # Reload footage data to refresh compositions that use this footage
        if successCount > 0:
            self.tracker.loadFootageData(preserve_scroll=True)

    @err_catcher(name=__name__)
    def updateAllFPS(self, selected_only=False):
        """Update FPS for all footage and compositions to match their target FPS

        Args:
            selected_only: If True, only update selected items
        """
        # Get project FPS from config
        project_fps = 25.0
        try:
            fps_config = self.core.getConfig("globals", "fps", config="project")
            if fps_config:
                project_fps = float(fps_config)
        except Exception:
            pass

        # Get selected items set if filtering
        selected_set = set()
        if selected_only:
            selected_set = set(self.tracker.tw_footage.selectedItems())

        footageItems = []
        compItems = []

        def findItems(item, shot=""):
            userData = item.data(0, Qt.UserRole)
            if userData:
                if userData.get('type') == 'group' and userData.get('level') == 'shot':
                    shot = item.text(0)
                elif userData.get('type') == 'footage':
                    if not selected_only or item in selected_set:
                        kitsuData = self.tracker.getKitsuDataForShot(shot)
                        if kitsuData and kitsuData.get('fps'):
                            footageItems.append((item, shot, kitsuData))
                elif userData.get('type') == 'comp':
                    if not selected_only or item in selected_set:
                        # Comps use project FPS, not Kitsu FPS
                        compItems.append(item)

            for i in range(item.childCount()):
                findItems(item.child(i), shot)

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            findItems(self.tracker.tw_footage.topLevelItem(i))

        if not footageItems and not compItems:
            if selected_only:
                self.core.popup(
                    "No selected footage or compositions with Kitsu FPS data found.\n\n"
                    "Please ensure:\n"
                    "- Footage items are selected\n"
                    "- Items belong to shots with Kitsu data"
                )
            else:
                self.core.popup(
                    "No footage or compositions found.\n\n"
                    "Please ensure items are loaded."
                )
            return

        needsUpdate = []
        # Check footage items (compare to Kitsu FPS)
        for item, shot, kitsuData in footageItems:
            fpsWidget = self.tracker.tw_footage.itemWidget(item, 4)
            if fpsWidget and fpsWidget.layout() and fpsWidget.layout().count() > 0:
                widget = fpsWidget.layout().itemAt(0).widget()
                currentFps = None
                spinBox = None

                if isinstance(widget, QDoubleSpinBox):
                    currentFps = widget.value()
                    spinBox = widget
                elif isinstance(widget, QLabel):
                    # FPS displayed as label (probably has warning color) - parse from text
                    fpsText = widget.text()
                    try:
                        currentFps = float(fpsText)
                    except (ValueError, TypeError):
                        # Try to get from item.text(4) as fallback
                        fpsText = item.text(4)
                        try:
                            currentFps = float(fpsText)
                        except Exception:
                            pass

                if currentFps is not None:
                    kitsuFps = float(kitsuData['fps'])
                    if abs(currentFps - kitsuFps) > 0.01:
                        needsUpdate.append(('footage', item, kitsuFps, spinBox))

        # Check composition items (compare to project FPS)
        for item in compItems:
            # Comps show FPS in column 4 as text
            fpsText = item.text(4)
            try:
                currentFps = float(fpsText)
                if abs(currentFps - project_fps) > 0.01:
                    userData = item.data(0, Qt.UserRole)
                    needsUpdate.append(('comp', item, project_fps, userData))
            except (ValueError, TypeError):
                pass

        if not needsUpdate:
            self.core.popup(
                "All FPS values already match their targets.\n\n"
                f"Total footage checked: {len(footageItems)}\n"
                f"Total compositions checked: {len(compItems)}"
            )
            return

        # Count types
        footageCount = sum(1 for x in needsUpdate if x[0] == 'footage')
        compCount = sum(1 for x in needsUpdate if x[0] == 'comp')

        reply = QMessageBox.question(
            self.tracker.dlg_footage,
            "Update FPS",
            f"Update FPS for {footageCount} footage item(s) to Kitsu FPS\n"
            f"and {compCount} composition(s) to project FPS ({project_fps:.2f})?\n\n"
            f"(Total footage: {len(footageItems)}, Total comps: {len(compItems)})",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return

        successCount = 0
        failedCount = 0
        compSuccessCount = 0
        compFailedCount = 0

        for item_type, item, targetFps, *rest in needsUpdate:
            try:
                if item_type == 'footage':
                    spinBox = rest[0] if rest else None
                    userData = item.data(0, Qt.UserRole)
                    footageId = userData['id']

                    scpt = f"""
                    try {{
                        var item = app.project.itemByID({footageId});
                        if (!item) {{
                            'ERROR: Item not found';
                        }} else if (!item.mainSource) {{
                            'ERROR: No main source';
                        }} else {{
                            item.mainSource.conformFrameRate = {targetFps};
                            'SUCCESS';
                        }}
                    }} catch(e) {{
                        'ERROR: ' + e.toString();
                    }}
                    """
                    result = self.main.ae_core.executeAppleScript(scpt)
                    resultStr = str(result).replace("b'", "").replace("'", "").strip()

                    if 'SUCCESS' in resultStr:
                        # Update UI - handle both QDoubleSpinBox and QLabel cases
                        if spinBox:
                            spinBox.blockSignals(True)
                            spinBox.setValue(targetFps)
                            spinBox.blockSignals(False)
                            spinBox.setToolTip(f"✓ FPS matches Kitsu project: {targetFps:.2f} fps")
                        else:
                            # Widget is a QLabel - update the label text
                            fpsWidget = self.tracker.tw_footage.itemWidget(item, 4)
                            if fpsWidget and fpsWidget.layout() and fpsWidget.layout().count() > 0:
                                widget = fpsWidget.layout().itemAt(0).widget()
                                if isinstance(widget, QLabel):
                                    widget.setText(f"{targetFps:.2f}")
                                    widget.setStyleSheet("color: rgb(255, 255, 255);")

                        # Clear item background/foreground
                        item.setBackground(4, QBrush(QColor(0, 0, 0, 0)))
                        item.setForeground(4, QBrush(QColor(255, 255, 255)))

                        successCount += 1
                    else:
                        failedCount += 1

                elif item_type == 'comp':
                    userData = rest[0]
                    compId = userData.get('id')
                    compName = userData.get('name', 'Unknown')

                    # Use comp_manager to set FPS (silent mode for batch)
                    result = self.tracker.comp_manager.setCompFPSFromKitsu(
                        compId, compName, targetFps, silent=True
                    )

                    if result and 'Success' in str(result):
                        # Update the UI
                        item.setText(4, f"{targetFps:.2f}")
                        compSuccessCount += 1
                    else:
                        compFailedCount += 1

            except Exception as e:
                if item_type == 'footage':
                    failedCount += 1
                else:
                    compFailedCount += 1

        # Build result message
        msg_parts = []
        if successCount > 0:
            msg_parts.append(f"Updated {successCount} footage item(s)")
        if compSuccessCount > 0:
            msg_parts.append(f"Updated {compSuccessCount} composition(s)")

        if failedCount > 0:
            msg_parts.append(f"Failed to update {failedCount} footage item(s)")
        if compFailedCount > 0:
            msg_parts.append(f"Failed to update {compFailedCount} composition(s)")

        result_msg = "\n".join(msg_parts)

        if (failedCount + compFailedCount) > 0:
            self.tracker.showSelectableMessage(
                "Update FPS Complete with Errors",
                result_msg
            )
        else:
            self.core.popup(f"Successfully updated FPS:\n{result_msg}")

        # Reload footage data to refresh compositions that use this footage
        self.tracker.loadFootageData(preserve_scroll=True)
        self.tracker.updateStatistics()

    @err_catcher(name=__name__)
    def batchUpdateFPS(self):
        """Update FPS for all selected footage"""
        selectedItems = []
        
        def findFootageItems(item):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'footage':
                selectedItems.append(item)
            for i in range(item.childCount()):
                findFootageItems(item.child(i))
        
        for item in self.tracker.tw_footage.selectedItems():
            findFootageItems(item)
        
        if not selectedItems:
            self.core.popup("Please select one or more footage items.")
            return
        
        fps, ok = QInputDialog.getDouble(
            self.tracker.dlg_footage, 
            "Batch FPS Update", 
            f"Set FPS for {len(selectedItems)} selected footage item(s):",
            24.0, 1.0, 240.0, 2
        )
        
        if not ok:
            return
        
        successCount = 0
        for item in selectedItems:
            userData = item.data(0, Qt.UserRole)
            try:
                scpt = f"""
                try {{
                    var item = app.project.itemByID({userData['id']});
                    if (item && item.mainSource) {{
                        item.mainSource.conformFrameRate = {fps};
                        'SUCCESS';
                    }} else {{
                        'ERROR: Item or source not found';
                    }}
                }} catch(e) {{
                    'ERROR: ' + e.toString();
                }}
                """
                result = self.main.ae_core.executeAppleScript(scpt)
                resultStr = str(result).replace("b'", "").replace("'", "").strip()
                if 'SUCCESS' in resultStr:
                    fpsWidget = self.tracker.tw_footage.itemWidget(item, 4)
                    if fpsWidget and fpsWidget.layout().count() > 0:
                        spinBox = fpsWidget.layout().itemAt(0).widget()
                        if isinstance(spinBox, QDoubleSpinBox):
                            spinBox.blockSignals(True)
                            spinBox.setValue(fps)
                            spinBox.blockSignals(False)
                    successCount += 1
            except Exception:
                pass
        
        self.core.popup(
            f"FPS Update Complete:\n\n"
            f"Success: {successCount}\n"
            f"Failed: {len(selectedItems) - successCount}"
        )
        # Reload footage data to refresh compositions that use this footage
        self.tracker.loadFootageData()
        self.tracker.updateStatistics()

    @err_catcher(name=__name__)
    def revealInProject(self, footageId):
        """Reveal and select footage in After Effects Project panel"""
        try:
            scpt = f"""
            try {{
                var item = app.project.itemByID({footageId});
                if (!item) {{
                    'ERROR: Item not found';
                }} else {{
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        app.project.item(i).selected = false;
                    }}
                    item.selected = true;
                    
                    try {{
                        app.executeCommand(2523);
                    }} catch(e) {{}}
                    
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            
            if b'ERROR' in result:
                self.core.popup("Could not find footage in After Effects project.")
            else:
                self.tracker.dlg_footage.statusBar.setText(
                    f"Footage revealed in Project panel - Press Ctrl+Alt+G to open Interpret Footage"
                )
                QTimer.singleShot(5000, lambda: self.tracker.updateStatistics())
                
        except Exception as e:
            self.core.popup(f"Error:\n{str(e)}")

    @err_catcher(name=__name__)
    def revealInCompositions(self, footageId):
        """Show all compositions that use this footage"""
        try:
            scpt = f"""
            try {{
                var item = app.project.itemByID({footageId});
                if (!item) {{
                    'ERROR: Item not found';
                }} else {{
                    var comps = [];
                    
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        var comp = app.project.item(i);
                        if (comp instanceof CompItem) {{
                            for (var j = 1; j <= comp.numLayers; j++) {{
                                var layer = comp.layer(j);
                                if (layer.source && layer.source.id == item.id) {{
                                    comps.push(comp.id + '::' + comp.name);
                                    break;
                                }}
                            }}
                        }}
                    }}
                    
                    if (comps.length > 0) {{
                        'COMPS:' + comps.join('|||');
                    }} else {{
                        'NO_COMPS';
                    }}
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            
            if b'ERROR' in result:
                self.core.popup("Could not search compositions in After Effects.")
            elif b'NO_COMPS' in result:
                self.core.popup("This footage is not used in any compositions.")
            else:
                self._showCompositionList(result)
                
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")

    def _showCompositionList(self, result):
        """Display list of compositions using the footage"""
        compsStr = str(result).split('COMPS:')[-1].replace("'", "").replace("b", "").strip()
        compsData = compsStr.split('|||')
        compsList = []
        for comp in compsData:
            if '::' in comp:
                compId, compName = comp.split('::', 1)
                compsList.append((compId, compName))
        
        dlg = QDialog(self.tracker.dlg_footage)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle("Footage Used In Compositions")
        dlg.resize(400, 300)
        
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        
        label = QLabel(
            f"This footage is used in {len(compsList)} composition(s):\n\n"
            "Click a composition to open it:"
        )
        layout.addWidget(label)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)
        
        for compId, compName in compsList:
            btn = QPushButton(compName)
            btn.clicked.connect(
                lambda checked, cid=compId, cname=compName: self.openComposition(cid, cname, dlg)
            )
            scroll_layout.addWidget(btn)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.close)
        layout.addWidget(close_btn)
        
        dlg.exec_()

    @err_catcher(name=__name__)
    def openComposition(self, compId, compName, parentDialog):
        """Open a composition in After Effects"""
        try:
            scpt = f"""
            try {{
                var comp = app.project.itemByID({compId});
                if (!comp) {{
                    'ERROR: Composition not found';
                }} else if (!(comp instanceof CompItem)) {{
                    'ERROR: Not a composition';
                }} else {{
                    comp.openInViewer();
                    'SUCCESS';
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            
            if b'ERROR' in result:
                self.core.popup(f"Could not open composition '{compName}'")
            else:
                self.tracker.dlg_footage.statusBar.setText(f"Opened composition: {compName}")
                QTimer.singleShot(3000, lambda: self.tracker.updateStatistics())
                parentDialog.close()
                
        except Exception as e:
            self.core.popup(f"Error:\n{str(e)}")


    # ========== AE Organization Methods ==========

    @err_catcher(name=__name__)
    def createFolderStructure(self, parent_folder_id, folder_path):
        """Create folder structure in AE project using ExtendScript"""
        try:
            script = f"""
            function createFolderStructure(parentFolderId, folderPath) {{
                try {{
                    var parentFolder;
                    if (parentFolderId) {{
                        parentFolder = app.project.itemByID(parentFolderId);
                    }} else {{
                        parentFolder = app.project.rootFolder;
                    }}

                    if (!parentFolder) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Parent folder not found (ID: ' + parentFolderId + ')'
                        }});
                    }}

                    var folders = folderPath.split('/');
                    var currentFolder = parentFolder;

                    for (var i = 0; i < folders.length; i++) {{
                        var folderName = folders[i];
                        if (!folderName) continue;

                        var folderExists = false;

                        // Check if folder already exists
                        for (var j = 1; j <= currentFolder.numItems; j++) {{
                            if (currentFolder.item(j) instanceof FolderItem &&
                                currentFolder.item(j).name === folderName) {{
                                folderExists = true;
                                currentFolder = currentFolder.item(j);
                                break;
                            }}
                        }}

                        if (!folderExists) {{
                            currentFolder = currentFolder.items.addFolder(folderName);
                        }}
                    }}

                    return JSON.stringify({{
                        success: true,
                        folderId: currentFolder.id,
                        folderName: currentFolder.name
                    }});

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = createFolderStructure({parent_folder_id}, '{folder_path}');
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            return result

        except Exception as e:
            return f"ERROR: {str(e)}"

    # ========== AE Organization Methods ==========

    @err_catcher(name=__name__)
    def createFolderStructure(self, parent_folder_id, folder_path):
        """Create folder structure in AE project using ExtendScript"""
        try:
            script = f"""
            function createFolderStructure(parentFolderId, folderPath) {{
                try {{
                    var parentFolder;
                    if (parentFolderId) {{
                        parentFolder = app.project.itemByID(parentFolderId);
                    }} else {{
                        parentFolder = app.project.rootFolder;
                    }}

                    if (!parentFolder) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Parent folder not found (ID: ' + parentFolderId + ')'
                        }});
                    }}

                    var folders = folderPath.split('/');
                    var currentFolder = parentFolder;

                    for (var i = 0; i < folders.length; i++) {{
                        var folderName = folders[i];
                        if (!folderName) continue;

                        var folderExists = false;

                        // Check if folder already exists
                        for (var j = 1; j <= currentFolder.numItems; j++) {{
                            if (currentFolder.item(j) instanceof FolderItem &&
                                currentFolder.item(j).name === folderName) {{
                                folderExists = true;
                                currentFolder = currentFolder.item(j);
                                break;
                            }}
                        }}

                        if (!folderExists) {{
                            currentFolder = currentFolder.items.addFolder(folderName);
                        }}
                    }}

                    return JSON.stringify({{
                        success: true,
                        folderId: currentFolder.id,
                        folderName: currentFolder.name
                    }});

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = createFolderStructure({parent_folder_id}, '{folder_path}');
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            print(f"DEBUG: createFolderStructure raw socket result: {repr(result)}")
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                parsed = json.loads(result)
                if parsed is None:
                    return {'success': False, 'error': f'AE returned null for folder: {folder_path}'}
                return parsed
            except Exception:
                # If parsing fails, check if it's an error message
                if result and result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'folder_id': 0, 'folder_name': folder_path, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def duplicateFootageItem(self, footage_id, new_name, target_folder_id):
        """Duplicate a footage item with new name and parent folder"""
        try:
            script = f"""
            function duplicateFootageItem(footageId, newName, targetFolderId) {{
                try {{
                    var originalItem = app.project.itemByID(footageId);
                    var targetFolder = app.project.itemByID(targetFolderId);

                    if (!originalItem) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Original footage item not found (ID: ' + footageId + ')'
                        }});
                    }}

                    if (!targetFolder) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Target folder not found (ID: ' + targetFolderId + ')'
                        }});
                    }}

                    if (!(originalItem instanceof FootageItem)) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Item is not a footage item'
                        }});
                    }}

                    // Move footage item and rename it (preserves comp links)
                    try {{
                        app.beginUndoGroup("Organize Footage");

                        // Rename the item
                        originalItem.name = newName;

                        // Move to target folder
                        originalItem.parentFolder = targetFolder;

                        app.endUndoGroup();

                        var result = {{
                            success: true,
                            newId: originalItem.id,
                            newName: originalItem.name
                        }};

                    }} catch(e) {{
                        var result = {{
                            success: false,
                            error: e.toString()
                        }};
                    }}

                    return JSON.stringify(result);

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = duplicateFootageItem({footage_id}, '{new_name}', {target_folder_id});
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            print(f"DEBUG: duplicateFootageItem raw socket result: {repr(result)}")
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                return json.loads(result)
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'new_id': 0, 'new_name': new_name, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def duplicateCompItem(self, comp_id, new_name, target_folder_id):
        """Duplicate a composition item with new name and parent folder"""
        try:
            script = f"""
            function duplicateCompItem(compId, newName, targetFolderId) {{
                try {{
                    var originalComp = app.project.itemByID(compId);
                    var targetFolder = app.project.itemByID(targetFolderId);

                    if (!originalComp) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Original composition not found (ID: ' + compId + ')'
                        }});
                    }}

                    if (!targetFolder) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Target folder not found (ID: ' + targetFolderId + ')'
                        }});
                    }}

                    if (!(originalComp instanceof CompItem)) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Item is not a composition'
                        }});
                    }}

                    // Move composition item and rename it (preserves all links)
                    try {{
                        app.beginUndoGroup("Organize Comp");

                        // Rename the composition
                        originalComp.name = newName;

                        // Move to target folder
                        originalComp.parentFolder = targetFolder;

                        app.endUndoGroup();

                        var result = {{
                            success: true,
                            newId: originalComp.id,
                            newName: originalComp.name
                        }};

                    }} catch(e) {{
                        var result = {{
                            success: false,
                            error: e.toString()
                        }};
                    }}

                    return JSON.stringify(result);

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = duplicateCompItem({comp_id}, '{new_name}', {target_folder_id});
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                return json.loads(result)
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'new_id': 0, 'new_name': new_name, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def deleteFootageItem(self, footage_id):
        """Delete a footage item from the After Effects project"""
        try:
            script = f"""
            function deleteFootageItem(footageId) {{
                try {{
                    var item = app.project.itemByID(footageId);

                    if (!item) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Footage item not found (ID: ' + footageId + ')'
                        }});
                    }}

                    if (!(item instanceof FootageItem)) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Item is not a footage item'
                        }});
                    }}

                    // Get the item name for confirmation
                    var itemName = item.name;

                    // Delete the item
                    app.beginUndoGroup("Delete Footage");
                    item.remove();
                    app.endUndoGroup();

                    return JSON.stringify({{
                        success: true,
                        deletedId: footageId,
                        deletedName: itemName
                    }});

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = deleteFootageItem({footage_id});
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                return json.loads(result)
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'deleted_id': footage_id, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def deleteCompItem(self, comp_id):
        """Delete a composition item from the After Effects project"""
        try:
            script = f"""
            function deleteCompItem(compId) {{
                try {{
                    var item = app.project.itemByID(compId);

                    if (!item) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Composition not found (ID: ' + compId + ')'
                        }});
                    }}

                    if (!(item instanceof CompItem)) {{
                        return JSON.stringify({{
                            success: false,
                            error: 'Item is not a composition'
                        }});
                    }}

                    // Get the item name for confirmation
                    var itemName = item.name;

                    // Delete the item
                    app.beginUndoGroup("Delete Comp");
                    item.remove();
                    app.endUndoGroup();

                    return JSON.stringify({{
                        success: true,
                        deletedId: compId,
                        deletedName: itemName
                    }});

                }} catch(e) {{
                    return JSON.stringify({{
                        success: false,
                        error: e.toString()
                    }});
                }}
            }}

            var result = deleteCompItem({comp_id});
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                return json.loads(result)
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'deleted_id': comp_id, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def removeAllEmptyFolders(self):
        """Remove all empty folders from the After Effects project"""
        try:
            script = """
            function removeAllEmptyFolders() {
                try {
                    var deletedCount = 0;

                    // Keep deleting empty folders until no more are found
                    var deletedThisPass = -1;
                    var maxPasses = 100;  // Safety limit
                    var passCount = 0;

                    app.beginUndoGroup("Remove Empty Folders");

                    while (deletedThisPass !== 0 && passCount < maxPasses) {
                        deletedThisPass = 0;

                        // Function to check and delete empty folders recursively
                        function processFolder(folder) {
                            var foldersToDelete = [];

                            // First, recursively process all subfolders
                            for (var i = folder.numItems; i >= 1; i--) {
                                var item = folder.item(i);
                                if (item instanceof FolderItem) {
                                    processFolder(item);
                                }
                            }

                            // Then check if this folder is now empty
                            if (folder !== app.project.rootFolder) {
                                if (folder.numItems === 0) {
                                    // Folder is empty, delete it
                                    folder.remove();
                                    deletedCount++;
                                    deletedThisPass++;
                                }
                            }
                        }

                        processFolder(app.project.rootFolder);
                        passCount++;
                    }

                    app.endUndoGroup();

                    return JSON.stringify({
                        success: true,
                        deletedCount: deletedCount
                    });

                } catch(e) {
                    return JSON.stringify({
                        success: false,
                        error: e.toString()
                    });
                }
            }

            var result = removeAllEmptyFolders();
            result;
            """

            result = self.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            # Parse the JSON result
            try:
                import json
                return json.loads(result)
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:'):
                    return {'success': False, 'error': result}
                else:
                    return {'success': True, 'raw_result': result}

        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def replaceFootage(self, footage_id, new_path):
        """Replace a footage item's source with a new file path"""
        try:
            import os
            print(f"[DEBUG REPLACE] Starting replaceFootage for ID: {footage_id}")
            print(f"[DEBUG REPLACE] New path: {new_path[:100]}")

            # Check if the new path exists
            if not os.path.exists(new_path):
                print(f"[DEBUG REPLACE] ERROR: Path does not exist!")
                return {'success': False, 'error': f'File does not exist: {new_path}'}

            # Determine if it's a sequence
            new_is_sequence = self.tracker.utils.isSequence(new_path)
            print(f"[DEBUG REPLACE] Is sequence: {new_is_sequence}")

            if new_is_sequence:
                new_path = self.tracker.utils.ensureSequencePath(new_path)
            else:
                new_path = self.tracker.utils.ensureStillPath(new_path)

            print(f"[DEBUG REPLACE] Adjusted path: {new_path[:100]}")

            # Convert path for AE - normalize and escape for ExtendScript
            normalized_path = new_path.replace('\\', '/')
            if platform.system() == "Windows":
                ae_path = normalized_path.replace('/', '\\\\')
            else:
                ae_path = normalized_path

            print(f"[DEBUG REPLACE] AE path: {ae_path[:100]}")

            # Get current properties first
            get_props_script = f"""
            try {{
                var item = app.project.itemByID({footage_id});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    JSON.stringify({{'success': false, 'error': 'Invalid item or not a file source'}});
                }} else {{
                    var fps = item.mainSource.conformFrameRate;
                    var isSequence = item.mainSource.isStill ? false : true;
                    JSON.stringify({{
                        'success': true,
                        'fps': fps,
                        'isSequence': isSequence
                    }});
                }}
            }} catch(e) {{
                JSON.stringify({{'success': false, 'error': e.toString()}});
            }}
            """

            props_result = self.main.ae_core.executeAppleScript(get_props_script)
            if isinstance(props_result, bytes):
                props_result = props_result.decode('utf-8')

            print(f"[DEBUG REPLACE] Props result: {props_result}")

            try:
                import json
                props = json.loads(props_result)
            except Exception:
                print(f"[DEBUG REPLACE] ERROR: Failed to parse props: {props_result}")
                return {'success': False, 'error': f'Failed to parse footage properties: {props_result}'}

            if not props.get('success'):
                print(f"[DEBUG REPLACE] ERROR: Props not successful: {props}")
                return props

            original_fps = props.get('fps', 25.0)
            print(f"[DEBUG REPLACE] Original FPS: {original_fps}")

            # Replace the footage
            replace_script = f"""
            try {{
                var item = app.project.itemByID({footage_id});
                if (!item || !(item.mainSource instanceof FileSource)) {{
                    JSON.stringify({{'success': false, 'error': 'Invalid item or not a file source'}});
                }} else {{
                    var file = new File('{ae_path}');
                    if (!file.exists) {{
                        JSON.stringify({{'success': false, 'error': 'File not found: ' + file.fsName}});
                    }} else {{
                        // Replace the footage
                        {'item.replaceWithSequence(file, false);' if new_is_sequence else 'item.replace(file);'}

                        // Explicitly disable alphabetical ordering for sequences
                        {'item.mainSource.alphabeticOrder = false;' if new_is_sequence else ''}

                        // Try to preserve original FPS
                        try {{
                            item.mainSource.conformFrameRate = {original_fps};
                        }} catch(e) {{}}

                        JSON.stringify({{'success': true, 'newPath': '{ae_path}'}});
                    }}
                }}
            }} catch(e) {{
                JSON.stringify({{'success': false, 'error': e.toString()}});
            }}
            """

            print(f"[DEBUG REPLACE] Executing replace script...")
            result = self.main.ae_core.executeAppleScript(replace_script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            print(f"[DEBUG REPLACE] Replace result: {result}")

            try:
                import json
                parsed = json.loads(result)
                print(f"[DEBUG REPLACE] Parsed result: {parsed}")
                return parsed
            except Exception:
                # If parsing fails, check if it's an error message
                if result.startswith('ERROR:') or 'error' in result.lower():
                    print(f"[DEBUG REPLACE] ERROR in result: {result}")
                    return {'success': False, 'error': result}
                else:
                    print(f"[DEBUG REPLACE] Success (raw result)")
                    return {'success': True, 'raw_result': result}

        except Exception as e:
            import traceback
            print(f"[DEBUG REPLACE] Exception: {str(e)}")
            print(f"[DEBUG REPLACE] Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}