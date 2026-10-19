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

import helixae_protocol
from footage_tracker import version_paths


class AEOperations:
    """Handles all After Effects script execution and operations"""

    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

    def _resolveNewVersionPath(self, oldPath, newVersion):
        """Deterministically rebuild ``oldPath`` for ``newVersion``.

        Uses footage_tracker.version_paths (single implementation for the
        3D/2D layouts), then matches the actual file inside the new
        version directory.  Returns the forward-slash path to the
        sequence/still target, or None when the version folder or file
        does not exist.
        """
        try:
            newPath = version_paths.build_new_version_path(oldPath, newVersion)
        except ValueError:
            return None

        # Match the real file in the new version's directory (the parent
        # of the reconstructed file path: AOV folder for 3D renders,
        # version folder for 2D renders).
        parent = newPath.rsplit("/", 1)[0]
        if not os.path.isdir(parent):
            return None
        chosen = version_paths.match_footage_file(
            version_paths.sorted_listing(parent), os.path.basename(oldPath.replace("\\", "/"))
        )
        if chosen:
            newPath = parent + "/" + chosen

        if self.tracker.utils.isSequence(newPath):
            newPath = self.tracker.utils.ensureSequencePath(newPath)
        else:
            newPath = self.tracker.utils.ensureStillPath(newPath)

        if not os.path.isfile(newPath) or os.path.getsize(newPath) == 0:
            return None
        return newPath

    def _replaceFootageInAE(self, footageId, newPath, isSequence, conformFps):
        """Replace a footage item by id via the JSON protocol.

        Returns (True, None) on confirmed success, (False, reason).
        """
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_replace_footage_by_id(
                    footageId, newPath, isSequence, conform_fps=conformFps
                )
            )
        except Exception as e:
            return False, str(e)
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            return False, error
        if not data.get("result"):
            return False, data.get("details", "unknown After Effects error")
        if data.get('warnings'):
            self.tracker.showSelectableMessage(
                'Footage replaced — interpretation needs attention',
                newPath + '\n\n' + '\n'.join(data['warnings']))
        return True, None

    def _getFootageProperties(self, footageId):
        """Returns (props dict, None) or (None, reason)."""
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_get_footage_properties(footageId)
            )
        except Exception as e:
            return None, str(e)
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            return None, error
        if not data.get("result"):
            return None, data.get("details", "footage item not found")
        return data, None

    @err_catcher(name=__name__)
    def updateFootageVersion(self, item, newVersion, userData):
        """Update footage to use a different version"""
        try:
            oldPath = userData['path']
            self.tracker.debugLog.append(f"updateFootageVersion: oldPath = {oldPath}")

            newPath = self._resolveNewVersionPath(oldPath, newVersion)
            if newPath is None:
                self.tracker.showSelectableMessage(
                    "Version Not Found",
                    f"Could not find the target version on disk:\n"
                    f"Old path: {oldPath}\n"
                    f"Requested version: {newVersion}\n\n"
                    f"Please check that the version folder and its media exist."
                )
                return False

            newIsSequence = self.tracker.utils.isSequence(newPath)
            self.tracker.debugLog.append(f"updateFootageVersion: newPath = {newPath}, sequence = {newIsSequence}")

            props, propError = self._getFootageProperties(userData['id'])
            if props is None:
                self.tracker.showSelectableMessage(
                    "Failed to Get Footage Properties",
                    f"Failed to get footage properties:\n{propError}"
                )
                return False
            originalFPS = props.get("conformFrameRate") or None

            ok, reason = self._replaceFootageInAE(userData['id'], newPath, newIsSequence, originalFPS)
            if not ok:
                self.tracker.showSelectableMessage(
                    "Failed to Update Footage",
                    f"Failed to update footage in After Effects\n\nDetails: {reason}"
                )
                return False

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
                item.setText(2, "\u2713 Up to date")
                item.setForeground(2, QBrush(QColor(100, 200, 100)))
                item.setData(2, Qt.UserRole + 1, "current")
            else:
                item.setText(2, "\u26a0 Outdated")
                item.setForeground(2, QBrush(QColor(255, 150, 50)))
                item.setData(2, Qt.UserRole + 1, "outdated")

            self.tracker.updateStatistics()
            self.tracker.dlg_footage.statusBar.setText(f"Updated to {newVersion}")
            QTimer.singleShot(3000, lambda: self.tracker.updateStatistics())
            # Reload footage data to refresh compositions that use this footage
            self.tracker.loadFootageData()
            return True

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

            newPath = self._resolveNewVersionPath(oldPath, newVersion)
            if newPath is None:
                return False

            newIsSequence = self.tracker.utils.isSequence(newPath)

            props, _propError = self._getFootageProperties(userData['id'])
            if props is None:
                return False
            originalFPS = props.get("conformFrameRate") or None

            ok, _reason = self._replaceFootageInAE(userData['id'], newPath, newIsSequence, originalFPS)
            if not ok:
                return False

            # Update userData but don't refresh
            userData['path'] = newPath
            userData['currentVersion'] = newVersion
            item.setText(6, newPath)
            return True

        except Exception:
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

            newPath = self._resolveNewVersionPath(oldPath, newVersion)
            if newPath is None:
                return False

            newIsSequence = self.tracker.utils.isSequence(newPath)

            props, _propError = self._getFootageProperties(userData['id'])
            if props is None:
                return False
            originalFPS = props.get("conformFrameRate") or 25.0

            ok, _reason = self._replaceFootageInAE(userData['id'], newPath, newIsSequence, originalFPS)
            if not ok:
                return False

            userData['path'] = newPath
            userData['currentVersion'] = newVersion
            item.setText(6, newPath)

            if newVersion == userData['latestVersion']:
                item.setText(2, "\u2713 Up to date")
                item.setForeground(2, QBrush(QColor(100, 200, 100)))
                item.setData(2, Qt.UserRole + 1, "current")
            else:
                item.setText(2, "\u26a0 Outdated")
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

    @err_catcher(name=__name__)
    def updateFootageFPS(self, item, fps, userData):
        """Update footage FPS in After Effects"""
        try:
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_set_footage_fps(userData['id'], fps)
                )
            except Exception as e:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                reason = error or data.get("details", "unknown After Effects error")
                self.core.popup(f"Failed to update FPS in After Effects\n\nDetails: {reason}")
                return False
            self.tracker.dlg_footage.statusBar.setText(f"Updated FPS to {fps}")
            QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
            # Reload footage data to refresh compositions that use this footage
            self.tracker.loadFootageData()
            return True
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating FPS:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

    @err_catcher(name=__name__)
    def updateCompFPS(self, item, fps, compInfo):
        """Update composition FPS in After Effects"""
        try:
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_set_comp_fps(compInfo['compId'], fps)
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                reason = error or data.get("details", "unknown After Effects error")
                self.core.popup(f"Failed to update comp FPS in After Effects\n\nDetails: {reason}")
                return False
            self.tracker.dlg_footage.statusBar.setText(f"Updated comp FPS to {fps}")
            QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
            self.tracker.loadFootageData()
            return True
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp FPS:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

    @err_catcher(name=__name__)
    def updateCompFrameRange(self, item, startFrame, endFrame, compInfo):
        """Update composition frame range in After Effects"""
        try:
            # displayStartTime = startFrame / fps; duration covers start..end
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_set_comp_frame_range(
                        compInfo['compId'], startFrame, endFrame, compInfo['frameRate']
                    )
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                reason = error or data.get("details", "unknown After Effects error")
                self.core.popup(f"Failed to update comp frame range in After Effects\n\nDetails: {reason}")
                return False
            self.tracker.dlg_footage.statusBar.setText(f"Updated comp frame range to {startFrame}-{endFrame}")
            QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
            self.tracker.loadFootageData()
            return True
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp frame range:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

    @err_catcher(name=__name__)
    def updateCompResolution(self, item, width, height, compInfo):
        """Update composition resolution in After Effects"""
        try:
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_set_comp_resolution(compInfo['compId'], width, height)
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                reason = error or data.get("details", "unknown After Effects error")
                self.core.popup(f"Failed to update comp resolution in After Effects\n\nDetails: {reason}")
                return False
            self.tracker.dlg_footage.statusBar.setText(f"Updated comp resolution to {width}x{height}")
            QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))
            self.tracker.loadFootageData()
            return True
        except Exception as e:
            import traceback
            self.core.popup(f"Error updating comp resolution:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

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

                    try:
                        result = self.main.ae_core.executeAppleScript(
                            helixae_protocol.build_set_footage_fps(footageId, targetFps)
                        )
                    except Exception:
                        result = None
                    data, error = helixae_protocol.parse_json_response(result)
                    fpsUpdated = bool(data) and data.get("result") and not error

                    if fpsUpdated:
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

                    if result:
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
                try:
                    result = self.main.ae_core.executeAppleScript(
                        helixae_protocol.build_set_footage_fps(userData['id'], fps)
                    )
                except Exception:
                    result = None
                data, error = helixae_protocol.parse_json_response(result)
                if data and not error and data.get("result"):
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
            try:
                footage_id = helixae_protocol._as_id(footageId, "footage id")
            except (TypeError, ValueError) as e:
                self.core.popup(f"Could not reveal footage:\n{e}")
                return
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_reveal_item_in_project(footage_id)
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                self.tracker.dlg_footage.statusBar.setText(
                    f"Footage revealed in Project panel - Press Ctrl+Alt+G to open Interpret Footage"
                )
                QTimer.singleShot(5000, lambda: self.tracker.updateStatistics())
            else:
                reason = (data or {}).get("reason") or (data or {}).get("details") or error or "no response"
                self.core.popup(
                    f"Could not find footage in After Effects project.\n\n{reason}"
                )
        except Exception as e:
            self.core.popup(f"Error:\n{str(e)}")

    @err_catcher(name=__name__)
    def revealInCompositions(self, footageId):
        """Show all compositions that use this footage"""
        try:
            try:
                footage_id = helixae_protocol._as_id(footageId, "footage id")
            except (TypeError, ValueError) as e:
                self.core.popup(f"Could not search compositions:\n{e}")
                return
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_find_comps_using_item(footage_id)
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if not data or error or not data.get("result"):
                reason = (data or {}).get("reason") or (data or {}).get("details") or error or "no response"
                self.core.popup(f"Could not search compositions in After Effects.\n\n{reason}")
                return
            comps = data.get("comps") or []
            if not comps:
                self.core.popup("This footage is not used in any compositions.")
                return
            self._showCompositionList(
                [(str(c.get("id", "")), str(c.get("name", ""))) for c in comps]
            )
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")

    def _showCompositionList(self, compsList):
        """Display list of compositions using the footage"""
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
            try:
                comp_id = helixae_protocol._as_id(compId, "comp id")
            except (TypeError, ValueError) as e:
                self.core.popup(f"Could not open composition '{compName}':\n{e}")
                return
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_open_comp_in_viewer(comp_id)
                )
            except Exception:
                result = None
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                self.tracker.dlg_footage.statusBar.setText(f"Opened composition: {compName}")
                QTimer.singleShot(3000, lambda: self.tracker.updateStatistics())
                parentDialog.close()
            else:
                reason = (data or {}).get("reason") or (data or {}).get("details") or error or "no response"
                self.core.popup(f"Could not open composition '{compName}'\n\n{reason}")
        except Exception as e:
            self.core.popup(f"Error:\n{str(e)}")


    # ========== AE Organization Methods ==========

    @err_catcher(name=__name__)
    def createFolderStructure(self, parent_folder_id, folder_path):
        """Create folder structure in AE project using ExtendScript"""
        try:
            try:
                script = helixae_protocol.build_create_folder_structure(parent_folder_id, folder_path)
            except (TypeError, ValueError) as e:
                return {'success': False, 'error': str(e)}
            try:
                result = self.main.ae_core.executeAppleScript(script)
            except Exception as e:
                return {'success': False, 'error': str(e)}
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                return {
                    'success': True,
                    'folder_id': data.get('folderId'),
                    'folder_name': data.get('folderName'),
                }
            reason = (data or {}).get('reason') or (data or {}).get('details') or error or 'no response'
            return {'success': False, 'error': str(reason)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def duplicateFootageItem(self, footage_id, new_name, target_folder_id):
        """Rename a footage item and move it to a parent folder (preserves comp links)"""
        return self._renameMoveItem(footage_id, new_name, target_folder_id, "footage")

    def _renameMoveItem(self, item_id, new_name, target_folder_id, expected_type):
        try:
            try:
                script = helixae_protocol.build_rename_move_item(
                    item_id, new_name, target_folder_id, expected_type
                )
            except (TypeError, ValueError) as e:
                return {'success': False, 'error': str(e)}
            try:
                result = self.main.ae_core.executeAppleScript(script)
            except Exception as e:
                return {'success': False, 'error': str(e)}
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                return {
                    'success': True,
                    'new_id': data.get('newId'),
                    'new_name': data.get('newName'),
                }
            reason = (data or {}).get('reason') or (data or {}).get('details') or error or 'no response'
            return {'success': False, 'error': str(reason)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def duplicateCompItem(self, comp_id, new_name, target_folder_id):
        """Rename a composition item and move it to a parent folder (preserves all links)"""
        return self._renameMoveItem(comp_id, new_name, target_folder_id, "comp")

    @err_catcher(name=__name__)
    def deleteFootageItem(self, footage_id):
        """Delete a footage item from the After Effects project"""
        return self._deleteProjectItem(footage_id, "footage")

    def _deleteProjectItem(self, item_id, expected_type):
        try:
            try:
                script = helixae_protocol.build_delete_project_item(item_id, expected_type)
            except (TypeError, ValueError) as e:
                return {'success': False, 'error': str(e)}
            try:
                result = self.main.ae_core.executeAppleScript(script)
            except Exception as e:
                return {'success': False, 'error': str(e)}
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                return {
                    'success': True,
                    'deleted_id': item_id,
                    'deleted_name': data.get('deletedName'),
                }
            reason = (data or {}).get('reason') or (data or {}).get('details') or error or 'no response'
            return {'success': False, 'error': str(reason)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def deleteCompItem(self, comp_id):
        """Delete a composition item from the After Effects project"""
        return self._deleteProjectItem(comp_id, "comp")

    @err_catcher(name=__name__)
    def removeAllEmptyFolders(self):
        """Remove all empty folders from the After Effects project"""
        try:
            try:
                result = self.main.ae_core.executeAppleScript(
                    helixae_protocol.build_remove_empty_folders()
                )
            except Exception as e:
                return {'success': False, 'error': str(e)}
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                return {'success': True, 'deleted_count': data.get('deletedCount', 0)}
            reason = (data or {}).get('reason') or (data or {}).get('details') or error or 'no response'
            return {'success': False, 'error': str(reason)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @err_catcher(name=__name__)
    def replaceFootage(self, footage_id, new_path):
        """Replace a footage item's source with a new file path"""
        try:
            import os
            if not os.path.exists(new_path):
                return {'success': False, 'error': f'File does not exist: {new_path}'}

            # Determine if it's a sequence and normalise the path for AE
            new_is_sequence = self.tracker.utils.isSequence(new_path)
            if new_is_sequence:
                new_path = self.tracker.utils.ensureSequencePath(new_path)
            else:
                new_path = self.tracker.utils.ensureStillPath(new_path)
            ae_path = new_path.replace('\\', '/')

            try:
                script = helixae_protocol.build_replace_footage_by_id(
                    footage_id, ae_path, sequence=new_is_sequence
                )
            except (TypeError, ValueError) as e:
                return {'success': False, 'error': str(e)}
            try:
                result = self.main.ae_core.executeAppleScript(script)
            except Exception as e:
                return {'success': False, 'error': str(e)}
            data, error = helixae_protocol.parse_json_response(result)
            if data and not error and data.get("result"):
                response = {'success': True, 'newPath': data.get('fileName')}
                warnings = data.get('warnings') or []
                if warnings:
                    response['warnings'] = warnings
                return response
            reason = (data or {}).get('reason') or (data or {}).get('details') or error or 'no response'
            return {'success': False, 'error': str(reason)}
        except Exception as e:
            import traceback
            return {'success': False, 'error': str(e), 'traceback': traceback.format_exc()}
