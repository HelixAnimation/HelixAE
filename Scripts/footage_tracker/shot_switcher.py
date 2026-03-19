# -*- coding: utf-8 -*-
"""
Shot Switcher Module
Handles switching footage between different shots
"""

import os
import re
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class ShotSwitcher:
    """Handles shot switching functionality"""

    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

    @err_catcher(name=__name__)
    def showShotSelectionDialog(self, footage_items):
        """Show shot selection dialog for changing footage to a different shot (always latest version)"""
        try:
            all_shots = self._getAllAvailableShots()

            if not all_shots:
                self._showNoShotsDialog()
                return

            # Get current shot from selected footage
            current_shot = None
            identifier = None
            aov = None

            if footage_items:
                first_item = footage_items[0]
                identifier, aov = self._extractIdentifierAndAOVFromItem(first_item)
                current_shot = self.tracker.getShotNameFromItem(first_item)

            # Create and show shot selection dialog
            target_shots = self._createShotSelectionDialog(all_shots, current_shot, identifier, aov)

            # Process selected shots
            for target_shot in target_shots:
                self.switchToLatestVersion(footage_items, target_shot)

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing shot selection dialog:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def switchToLatestVersion(self, footage_items, target_shot):
        """Switch footage to target shot using the latest version"""
        try:
            success_count = 0
            failed_count = 0
            failed_items = []

            # For multiple footage items, show a bulk confirmation
            if len(footage_items) > 1:
                reply = QMessageBox.question(
                    self.tracker.dlg_footage,
                    f"Change Shot - Multiple Footage Items",
                    f"Switch {len(footage_items)} footage item(s) to {target_shot}?\n\n"
                    f"This will replace each footage with the latest version "
                    f"of the corresponding identifier/AOV in {target_shot}.\n\n"
                    f"This will replace the footage source in After Effects.",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply == QMessageBox.No:
                    return

            for footage_item in footage_items:
                try:
                    # Get identifier and AOV for this specific item
                    identifier, aov = self._extractIdentifierAndAOVFromItem(footage_item)

                    if not identifier or not aov:
                        failed_count += 1
                        failed_items.append(f"{footage_item.text(0)}: Could not determine identifier/AOV")
                        continue

                    # Find latest version for this shot with its identifier/AOV
                    latest_version = self.findLatestVersionInShot(target_shot, identifier, aov)

                    if not latest_version:
                        failed_count += 1
                        failed_items.append(f"{target_shot}/{identifier}/{aov}: No footage found")
                        continue

                    # Show brief confirmation for each (optional - can be skipped for batch)
                    if len(footage_items) == 1:
                        reply = QMessageBox.question(
                            self.tracker.dlg_footage,
                            f"Change Shot (Custom)",
                            f"Switch {footage_item.text(0)} to {target_shot}?\n\n"
                            f"Identifier: {identifier}\n"
                            f"AOV: {aov}\n"
                            f"Version: {latest_version['version']} (Latest)\n\n"
                            f"This will replace the footage source in After Effects.",
                            QMessageBox.Yes | QMessageBox.No
                        )

                        if reply == QMessageBox.No:
                            failed_count += 1
                            failed_items.append(f"{footage_item.text(0)}: User cancelled")
                            continue

                    # Perform the replacement
                    if not hasattr(latest_version['footage_data'], 'footageId'):
                        # This is footage from disk, not in AE yet
                        success = self._importAndReplaceFootage(footage_item, target_shot, latest_version)
                        if success:
                            success_count += 1
                        else:
                            failed_count += 1
                            failed_items.append(f"{footage_item.text(0)}: Failed to replace")
                    else:
                        # Perform the normal switching for footage already in AE
                        self._performBatchShotSwitch([footage_item], target_shot, latest_version)
                        success_count += 1

                except Exception as e:
                    failed_count += 1
                    failed_items.append(f"{footage_item.text(0)}: {str(e)}")

            # Show results
            if failed_count == 0:
                if len(footage_items) == 1:
                    self.core.popup(f"Successfully switched footage to {target_shot}")
                else:
                    self.core.popup(f"Successfully switched all {success_count} footage item(s) to {target_shot}")

                # Refresh the footage tracker after successful change
                try:
                    self.tracker.loadFootageData()
                except Exception:
                    pass
            else:
                failed_text = "\n".join(failed_items[:5])  # Limit to first 5 items
                if len(failed_items) > 5:
                    failed_text += f"\n... and {len(failed_items) - 5} more items"
                self.core.popup(f"Switched {success_count} footage item(s) successfully.\n\n"
                              f"Failed ({failed_count}):\n{failed_text}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error switching shot:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def findLatestVersionInShot(self, target_shot, identifier, aov):
        """Find the latest version for given shot/identifier/aov combination"""
        try:
            # Skip hierarchy check entirely - go straight to disk search
            latest_version = self._findLatestVersionOnDisk(target_shot, identifier, aov)
            return latest_version

        except Exception as e:
            import traceback
            self.core.popup(f"Error finding latest version:\n{str(e)}\n\n{traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def changeToCurrentShot(self, footage_items):
        """Change footage to the current shot based on the .aep file name"""
        try:
            # Extract current shot from project file
            current_shot = self.tracker.tree_ops.extractCurrentShotFromProject()

            if not current_shot:
                error_msg = (
                    "Could not determine current shot from project file name.\n\n"
                    "Make sure the .aep file contains a shot name (e.g., SQ01-SH010)."
                )
                dlg = QDialog(self.tracker.dlg_footage)
                dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
                dlg.setWindowTitle("Error - Cannot Determine Current Shot")
                dlg.resize(500, 200)

                layout = QVBoxLayout()
                dlg.setLayout(layout)

                label = QLabel(error_msg)
                label.setWordWrap(True)
                layout.addWidget(label)

                # Buttons
                button_layout = QHBoxLayout()
                button_layout.addStretch()

                copy_btn = QPushButton("Copy to Clipboard")
                copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(error_msg))
                button_layout.addWidget(copy_btn)

                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dlg.accept)
                button_layout.addWidget(close_btn)

                layout.addLayout(button_layout)
                dlg.exec_()
                return

            # Check if current_shot is already the shot for the selected footage
            first_item_data = footage_items[0].data(0, Qt.UserRole)
            if first_item_data and first_item_data.get('shot') == current_shot:
                # Show message that footage is already from current shot
                msg = QMessageBox(self.tracker.dlg_footage)
                msg.setWindowTitle("Info - Already Current Shot")
                msg.setText("Selected footage is already from the current shot.")
                msg.setInformativeText(f"Current shot: {current_shot}")
                msg.setIcon(QMessageBox.Information)
                msg.exec_()
                return

            # Use the existing switchToLatestVersion method with the current shot
            self.switchToLatestVersion(footage_items, current_shot)

        except Exception as e:
            import traceback
            error_msg = f"Error changing to current shot:\n{str(e)}\n\n{traceback.format_exc()}"

            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            dlg.setWindowTitle("Error - Change Shot Failed")
            dlg.resize(600, 400)

            layout = QVBoxLayout()
            dlg.setLayout(layout)

            label = QLabel(error_msg)
            label.setWordWrap(True)
            layout.addWidget(label)

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(error_msg))
            button_layout.addWidget(copy_btn)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)
            dlg.exec_()

    def _getAllAvailableShots(self):
        """Get all available shots from Kitsu API and hierarchy"""
        all_shots = set()

        # First, try to get all shots directly from Kitsu API
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                if kitsuMgr.name == "Kitsu":
                    shots = kitsuMgr.getShots() or []
                    for shot in shots:
                        shotName = shot.get("shot", "")
                        sequence = shot.get("sequence", "")
                        if shotName:
                            # Combine sequence and shot if both exist
                            if sequence and "-" not in shotName:
                                fullShotName = f"{sequence}-{shotName}"
                                all_shots.add(fullShotName)
                            else:
                                all_shots.add(shotName)
        except Exception:
            # Fallback to stored Kitsu data if API call fails
            if self.tracker.kitsuShotData:
                for key in self.tracker.kitsuShotData.keys():
                    # Add both full names (SQ01-SH010) and shot-only names (SH010)
                    if '-' in key:
                        all_shots.add(key)
                    elif key.startswith('SH'):
                        all_shots.add(key)

        # Also try to get shots from the hierarchy
        hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
        if not hierarchy:
            self.tracker.loadFootageData()
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})

        # Collect shots from 3D Renders and 2D Renders
        for group_name in ['3D Renders', '2D Renders']:
            if group_name in hierarchy:
                group_data = hierarchy[group_name]
                if isinstance(group_data, dict):
                    all_shots.update(group_data.keys())

        return all_shots

    def _showNoShotsDialog(self):
        """Show debug dialog when no shots are found"""
        hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
        debug_msg = "No shots found in the project.\n\n"

        # Check Kitsu connection
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                debug_msg += f"Project Manager: {kitsuMgr.name}\n"
                if kitsuMgr.name == "Kitsu":
                    shots = kitsuMgr.getShots() or []
                    debug_msg += f"Kitsu API returned {len(shots)} shots\n"
                else:
                    debug_msg += "Manager is not Kitsu!\n"
            else:
                debug_msg += "No project manager configured\n"
        except Exception as e:
            debug_msg += f"Error checking Kitsu: {str(e)}\n"

        debug_msg += f"\nStored Kitsu data exists: {bool(self.tracker.kitsuShotData)}\n"
        if self.tracker.kitsuShotData:
            debug_msg += f"Stored Kitsu shots: {len(self.tracker.kitsuShotData)}\n"
            debug_msg += f"Sample keys: {list(self.tracker.kitsuShotData.keys())[:5]}\n"

        debug_msg += f"Hierarchy exists: {bool(hierarchy)}\n"
        debug_msg += "\nPlease make sure Kitsu is connected and the project has shots."

        self.tracker.dialog_manager.createDebugDialog("Debug Information - No Shots Found", debug_msg)

    def _createShotSelectionDialog(self, all_shots, current_shot, identifier, aov):
        """Create and show the shot selection dialog"""
        hierarchy = getattr(self.tracker, '_stored_hierarchy', {})

        # Create dialog
        dlg = QDialog(self.tracker.dlg_footage)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle("Change Shot")
        dlg.resize(400, 500)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Header
        header_label = QLabel("Select target shots (Ctrl/Cmd+click to select multiple):")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header_label)

        # Current info
        if current_shot and identifier and aov:
            current_label = QLabel(f"Current: {current_shot} / {identifier} / {aov}")
            current_label.setStyleSheet("color: #888888; font-style: italic; margin: 5px 0;")
            layout.addWidget(current_label)

        layout.addWidget(QLabel(""))

        # Shot list
        shot_list = QListWidget()
        shot_list.setAlternatingRowColors(False)
        layout.addWidget(shot_list)

        # Selection counter
        selection_label = QLabel("0 shots selected")
        selection_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(selection_label)

        # Update selection counter when selection changes
        shot_list.itemSelectionChanged.connect(
            lambda: selection_label.setText(f"{len(shot_list.selectedItems())} shot(s) selected")
        )

        # Add shots to list
        for shot in sorted(all_shots):
            # Skip current shot
            if shot == current_shot:
                continue

            # Check if this shot has the identifier/AOV combination
            has_footage = False
            if identifier and aov and hierarchy:
                for group_name in ['3D Renders', '2D Renders']:
                    if (group_name in hierarchy and
                        isinstance(hierarchy[group_name], dict) and
                        shot in hierarchy[group_name] and
                        isinstance(hierarchy[group_name][shot], dict) and
                        identifier in hierarchy[group_name][shot] and
                        aov in hierarchy[group_name][shot][identifier]):
                        has_footage = True
                        break

            # Add all shots by default, but indicate which ones have the matching footage
            item = QListWidgetItem(shot)

            if has_footage:
                item.setToolTip(f"Switch to {shot}\nHas {identifier}/{aov}")
                # Add a checkmark icon for shots that have the footage
                item.setText(f"✓ {shot}")
            else:
                # Still show the shot but with a warning
                item.setToolTip(f"Switch to {shot}\nWarning: May not have {identifier}/{aov} (will check on switch)")

            shot_list.addItem(item)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)

        change_btn = QPushButton("Change Shot")
        change_btn.setDefault(True)
        change_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(change_btn)

        layout.addLayout(button_layout)

        # Enable multiple selection
        shot_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Show dialog
        result = dlg.exec_()

        if result == QDialog.Accepted:
            selected_items = shot_list.selectedItems()
            target_shots = []
            for item in selected_items:
                shot_name = item.text()
                # Remove ✓ prefix if present
                if shot_name.startswith('✓ '):
                    shot_name = shot_name[2:]
                target_shots.append(shot_name)

            return target_shots

        return []

    def _extractIdentifierAndAOVFromItem(self, item):
        """Extract identifier and AOV from footage item by traversing tree structure"""
        try:
            # Get identifier from parent item
            identifier_item = item.parent()
            if not identifier_item:
                return None, None

            identifier = identifier_item.text(0)
            aov = item.text(0)  # AOV is the item's text (column 0)

            return identifier, aov
        except Exception:
            return None, None

    def _extractProjectPathFromCurrentFile(self):
        """Extract the main project path from the current .aep file path"""
        try:
            # Get current AE project file path
            # Get current file using core method
            current_file = self.core.getCurrentFileName()
            if not current_file:
                return None

            # Extract project path from the .aep file path
            # Example: X:\Align_iTero_Lumina_MultiPreps\03_Production\Shots\SQ02\SH020\Scenefiles\LookDev\HighRes
            #          \SQ02-SH020_HighRes_v0004.aep
            # Should extract: X:\Align_iTero_Lumina_MultiPreps

            # Convert forward slashes to backslashes for consistency
            current_file = current_file.replace('/', '\\')

            # Find the project root by looking for the path before "03_Production"
            if '03_Production' in current_file:
                project_path = current_file.split('03_Production')[0].rstrip(':\\')
                return project_path
            else:
                # If no "03_Production" folder, try other common patterns
                parts = current_file.split('\\')

                # Look for common project root indicators
                project_indicators = ['Production', '03_Production', 'Shots', 'Scenefiles']

                for i, part in enumerate(parts):
                    if part in project_indicators and i > 0:
                        project_path = '\\'.join(parts[:i])
                        return project_path

                # Fallback: assume the second-to-last part is the project
                if len(parts) >= 2:
                    project_path = '\\'.join(parts[:-1])
                    return project_path

            return None

        except Exception as e:
            return None

    def _findLatestVersionOnDisk(self, target_shot, identifier, aov):
        """Find latest version on disk when not found in hierarchy"""
        try:
            # Parse target shot
            sequence = target_shot.split('-')[0] if '-' in target_shot else 'SQ01'
            shot = target_shot.split('-')[-1] if '-' in target_shot else target_shot

            # Get project paths
            possible_project_paths = []

            # First try to extract from current .aep file
            current_project_path = self._extractProjectPathFromCurrentFile()
            if current_project_path:
                possible_project_paths.append(current_project_path)

            # Add fallback project paths that might be relevant
            fallback_paths = [
                "X:/Align_iTero_Lumina_MultiPreps",
                "X:/Halloween_2025",
                # Add more project paths here if needed
            ]

            for fallback_path in fallback_paths:
                if fallback_path not in possible_project_paths:
                    possible_project_paths.append(fallback_path)

            # Build the search paths for each possible project
            search_paths = []

            for project_path in possible_project_paths:
                # Check if the basic shot folder exists first
                basic_path = os.path.join(project_path, "03_Production", "Shots", sequence, shot)

                if not os.path.exists(basic_path):
                    continue

                # Try the exact path first
                exact_path = os.path.join(
                    project_path, "03_Production", "Shots", sequence, shot, "Renders", "3dRender", identifier
                )

                if os.path.exists(exact_path):
                    search_paths.append(exact_path)

            if search_paths:
                # First, find the latest version overall
                all_versions = []
                for search_path in search_paths:
                    for item in os.listdir(search_path):
                        if os.path.isdir(os.path.join(search_path, item)) and item.startswith('v'):
                            version_num = self.getVersionNumber(item)
                            all_versions.append((version_num, item, search_path))

                # Sort by version number (highest first)
                all_versions.sort(key=lambda x: x[0], reverse=True)

                # Find the latest version that has the requested AOV
                latest_version = None
                latest_version_path = None

                for version_num, version_name, search_path in all_versions:
                    version_path = os.path.join(search_path, version_name)
                    if os.path.exists(version_path):
                        # Check if this version has the requested AOV (case-insensitive)
                        for aov_dir in os.listdir(version_path):
                            aov_full_path = os.path.join(version_path, aov_dir)
                            if os.path.isdir(aov_full_path) and aov_dir.lower() == aov.lower():
                                # Check if this AOV folder actually has files (not just subfolders)
                                has_files = False
                                for item in os.listdir(aov_full_path):
                                    item_path = os.path.join(aov_full_path, item)
                                    if os.path.isfile(item_path) and not item.startswith('.'):
                                        # Allow image files (they may have dots in the name like .1001.exr)
                                        if not item.endswith('.json'):
                                            has_files = True
                                            break

                                if has_files:
                                    latest_version = version_name
                                    latest_version_path = aov_full_path
                                    break

                        if latest_version:
                            break

                # If still not found, look for any valid AOV in the latest version
                if not latest_version and all_versions:
                    version_name, search_path = all_versions[0][1], all_versions[0][2]
                    version_path = os.path.join(search_path, version_name)
                    if os.path.exists(version_path):
                        for aov_dir in os.listdir(version_path):
                            aov_full_path = os.path.join(version_path, aov_dir)
                            if os.path.isdir(aov_full_path) and not aov_dir.endswith('.json'):
                                # Check if this AOV folder actually has files
                                has_files = False
                                for item in os.listdir(aov_full_path):
                                    item_path = os.path.join(aov_full_path, item)
                                    if os.path.isfile(item_path) and not item.startswith('.'):
                                        # Allow image files (they may have dots)
                                        if not item.endswith('.json'):
                                            has_files = True
                                            break

                                if has_files:
                                    latest_version = version_name
                                    latest_version_path = aov_full_path
                                    break

                if latest_version and latest_version_path:
                    # We already have the AOV directory path
                    # Only include actual files (not directories), excluding hidden files and json files
                    files = [f for f in os.listdir(latest_version_path)
                            if not f.startswith('.')
                            and not f.endswith('.json')
                            and os.path.isfile(os.path.join(latest_version_path, f))]
                    if files:
                        file_path = os.path.join(latest_version_path, files[0])
                        return {
                            'version': latest_version,
                            'path_preview': os.path.basename(file_path),
                            'full_path': file_path,
                            'footage_data': {
                                'path': latest_version_path,
                                'versionInfo': {
                                    'currentVersion': latest_version,
                                    'latestVersion': latest_version
                                }
                            }
                        }

        except Exception as e:
            # Return None will trigger the error message in the calling method
            return None

    def _importAndReplaceFootage(self, current_item, target_shot, latest_version):
        """Import footage from disk and replace current footage in AE"""
        try:
            # Get current footage item ID
            userData = current_item.data(0, Qt.UserRole)
            current_footage_id = userData.get('id')

            if not current_footage_id:
                self.core.popup("Could not get current footage ID")
                return False

            # Get the path to the new footage files
            aov_path = latest_version['full_path']
            # Check if aov_path is a file or directory
            if os.path.isfile(aov_path):
                # If it's a file, get the directory
                aov_path = os.path.dirname(aov_path)

            # Check if this is a sequence or single file
            # Only include actual files (not directories), excluding hidden files and json files
            files = [f for f in os.listdir(aov_path)
                    if not f.startswith('.')
                    and not f.endswith('.json')
                    and os.path.isfile(os.path.join(aov_path, f))]

            if not files:
                self.core.popup(f"No files found in {aov_path}")
                return False

            # Find the sequence pattern
            first_file = files[0]
            full_path = os.path.join(aov_path, first_file)
            # Convert path to forward slashes for AE
            full_path_ae = full_path.replace('\\', '/')

            # Check if this is a sequence
            is_sequence = bool(re.search(r'\.\d{4,5}\.[^.]+$', first_file))

            # Execute AppleScript to replace footage
            if is_sequence:
                scpt = f"""
                try {{
                    var footageItem = app.project.itemByID({current_footage_id});
                    if (footageItem && footageItem instanceof FootageItem) {{
                        var newFile = new File("{full_path_ae}");
                        footageItem.replaceWithSequence(newFile, false);
                        footageItem.mainSource.alphabeticOrder = false;
                        "SUCCESS";
                    }} else {{
                        "ERROR: Footage item not found";
                    }}
                }} catch(e) {{
                    "ERROR: " + e.toString();
                }}
                """
            else:
                # For single files, use normal replace
                scpt = f"""
                try {{
                    var footageItem = app.project.itemByID({current_footage_id});
                    if (footageItem && footageItem instanceof FootageItem) {{
                        var newFile = new File("{full_path_ae}");
                        footageItem.replace(newFile);
                        "SUCCESS";
                    }} else {{
                        "ERROR: Footage item not found";
                    }}
                }} catch(e) {{
                    "ERROR: " + e.toString();
                }}
                """

            result = self.tracker.main.ae_core.executeAppleScript(scpt)

            # Convert result to string if it's bytes
            result_str = result.decode('utf-8') if isinstance(result, bytes) else str(result)

            if result and "SUCCESS" in result_str:
                return True
            else:
                self.core.popup(f"Failed to replace footage in After Effects.\n\nError: {result_str}")
                return False

        except Exception as e:
            import traceback
            error_msg = f"Error importing and replacing footage:\n{str(e)}\n\n{traceback.format_exc()}"
            self.tracker.dialog_manager.createErrorDialog("Error - Import Failed", error_msg)
            return False

    def _performBatchShotSwitch(self, footage_items, target_shot, latest_version):
        """Perform batch shot switching for footage already in AE"""
        # This would contain the logic for switching multiple items
        # Implementation would depend on the specific switching requirements
        pass

    def getVersionNumber(self, version_str):
        """Extract numeric version from version string (e.g., 'v0009' -> 9)"""
        try:
            import re
            match = re.search(r'(\d+)', version_str)
            return int(match.group(1)) if match else 0
        except Exception:
            return 0

    @err_catcher(name=__name__)
    def showVariableSelectionDialog(self, footage_items):
        """Show dialog for selecting which path variables to change"""
        try:
            if not footage_items:
                self.core.popup("No footage items selected")
                return

            # Get path from first footage item to extract variables
            first_item = footage_items[0]
            file_path = first_item.text(6)  # Path is in column 6

            # Extract variables from the path
            variables = self._extractPathVariables(file_path)
            if not variables:
                self.core.popup("Could not extract variables from the selected footage path")
                return

            # Show variable selection dialog
            selected_variables = self._createVariableSelectionDialog(variables, file_path)
            if not selected_variables:
                return  # User cancelled

            # Process variable changes
            self._processVariableChanges(footage_items, variables, selected_variables)

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing variable selection dialog:\n{str(e)}\n\n{traceback.format_exc()}")

    def _extractPathVariables(self, file_path):
        """Extract variables from a file path"""
        try:
            # Normalize path
            path = file_path.replace('\\', '/')
            path_parts = path.split('/')

            # Find the key parts by looking for known patterns
            variables = {}

            # Extract project path (everything before "03_Production")
            production_index = -1
            for i, part in enumerate(path_parts):
                if "03_Production" in part or "Production" in part:
                    production_index = i
                    break

            if production_index > 0:
                # Extract source_folder (everything before the project folder)
                # and project (the folder before 03_Production)
                if production_index > 1:
                    variables['source_folder'] = '/'.join(path_parts[:production_index-1])
                    variables['project'] = path_parts[production_index-1]
                else:
                    variables['source_folder'] = path_parts[production_index-1].split(':')[0] + ':/'
                    variables['project'] = path_parts[production_index-1]

            # Extract sequence, shot, identifier, version, AOV from the path pattern
            # Pattern: .../Shots/[Sequance]/[Shot]/Renders/3dRender/[Identifier]/[Version]/[AOV]/filename
            for i, part in enumerate(path_parts):
                if part == "Shots" and i + 2 < len(path_parts):
                    variables['sequence'] = path_parts[i + 1]
                    variables['shot'] = path_parts[i + 2]

                elif part == "Renders" and i + 4 < len(path_parts):
                    # Look for the task/identifier after Renders
                    if path_parts[i + 1] == "3dRender" or path_parts[i + 1] == "2dRender":
                        variables['identifier'] = path_parts[i + 2]  # Task/Identifier

                        # Look for version pattern
                        for j in range(i + 3, len(path_parts)):
                            if (path_parts[j].startswith('v')
                                    and len(path_parts[j]) >= 5
                                    and path_parts[j][1:5].isdigit()):
                                variables['version'] = path_parts[j]

                                # AOV is the next part (if exists)
                                if j + 1 < len(path_parts):
                                    variables['aov'] = path_parts[j + 1]
                                break

            return variables

        except Exception as e:
            self.core.popup(f"Error extracting path variables:\n{str(e)}")
            return {}

    def _createVariableSelectionDialog(self, variables, original_path):
        """Create dialog for user to select which variables to change using dropdown menus"""
        # Define the order and scanning function for each variable
        variable_order = ['source_folder', 'project', 'sequence', 'shot', 'identifier', 'version', 'aov']

        dialog = QDialog(self.tracker.dlg_footage)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dialog.setWindowTitle("Change Path Variables")
        dialog.resize(650, 350)
        dialog.setModal(True)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Store original variables for color comparison
        dialog.original_variables = variables.copy()
        # Track the dependency state when each dropdown was last refreshed
        dialog.refresh_states = {}  # {var_name: {dep_var: value_at_refresh_time}}

        # Extract the drive from the current file path to use for scanning
        current_drive = 'X:'  # Default fallback
        if 'source_folder' in variables and variables['source_folder']:
            # Extract drive from the current source folder path
            source_path = variables['source_folder']
            if ':' in source_path:
                current_drive = source_path.split(':')[0] + ':'
        elif 'project' in variables and variables['project']:
            # Fallback to project path extraction
            project_path = variables['project']
            if ':' in project_path:
                current_drive = project_path.split(':')[0] + ':'

        dialog.current_drive = current_drive
        self.tracker.debugLog.append(
            f"DEBUG: Detected current drive: {current_drive} from source_folder: "
            f"{variables.get('source_folder', 'None')}"
        )

        # Header
        header_label = QLabel("Select variables to change:")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header_label)

        # Original path
        path_label = QLabel(f"Original: {original_path}")
        path_label.setStyleSheet("color: #888888; font-style: italic; margin: 5px 0;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        layout.addWidget(QLabel(""))

        # Variable selection using simple grid layout
        grid_layout = QGridLayout()
        grid_layout.setSpacing(8)

        # Create checkboxes, refresh buttons, and dropdowns for each variable
        checkboxes = {}
        dropdowns = {}
        refresh_buttons = {}

        # Store reference to dropdowns for dependent updates
        dialog.dropdowns = dropdowns

        for i, var_name in enumerate(variable_order):
            if var_name not in variables:
                continue

            if var_name == 'source_folder':
                # Special handling for source_folder - use browse button instead of dropdown
                checkbox = QCheckBox("Source Folder:")
                checkbox.setChecked(False)
                checkboxes[var_name] = checkbox
                grid_layout.addWidget(checkbox, i, 0, Qt.AlignLeft)

                # Current value label
                current_label = QLabel(f"Current: {variables.get('source_folder', 'Not set')}")
                current_label.setStyleSheet("color: #888888; font-style: italic;")
                current_label.setMinimumWidth(200)
                grid_layout.addWidget(current_label, i, 1)

                # Store reference to current label for updates
                dialog.source_folder_label = current_label

                # Set the refresh button column to be exactly 24px wide and prevent expansion
                grid_layout.setColumnMinimumWidth(2, 24)
                grid_layout.setColumnStretch(2, 0)  # Prevent this column from stretching

                # Empty space where refresh button would be (source_folder doesn't need refresh)
                empty_widget = QWidget()
                grid_layout.addWidget(empty_widget, i, 2, Qt.AlignCenter)

                # Browse button
                browse_button = QPushButton("Browse...")
                browse_button.setEnabled(False)
                browse_button.setMinimumWidth(100)
                browse_button.clicked.connect(lambda: self._browseForSourceFolder(dialog, checkboxes, dropdowns))
                grid_layout.addWidget(browse_button, i, 3)

                # Store reference to browse button
                dialog.source_folder_browse_button = browse_button
            else:
                # Normal handling for other variables
                checkbox = QCheckBox(f"{var_name.title()}:")
                checkbox.setChecked(False)
                checkboxes[var_name] = checkbox
                grid_layout.addWidget(checkbox, i, 0, Qt.AlignLeft)

                # Current value label
                current_label = QLabel(f"Current: {variables[var_name]}")
                current_label.setStyleSheet("color: #888888; font-style: italic;")
                current_label.setMinimumWidth(200)
                grid_layout.addWidget(current_label, i, 1)

                # Set the refresh button column to be exactly 24px wide and prevent expansion
                grid_layout.setColumnMinimumWidth(2, 24)
                grid_layout.setColumnStretch(2, 0)  # Prevent this column from stretching

                # Refresh button (initially green) with proper icon
                refresh_button = QPushButton()
                refresh_button.setFixedSize(24, 24)  # Small square button
                refresh_button.setText("⟲")  # Better refresh symbol
                refresh_button.setStyleSheet("""
                    QPushButton {
                        background-color: #90EE90;  /* Light green */
                        border: 1px solid #228B22;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                        color: #006400;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #7CFC00;  /* Brighter green on hover */
                        border: 1px solid #006400;
                    }
                    QPushButton:pressed {
                        background-color: #32CD32;  /* Darker green when pressed */
                        border: 1px solid #006400;
                    }
                """)
                refresh_button.setEnabled(False)
                refresh_buttons[var_name] = refresh_button
                grid_layout.addWidget(refresh_button, i, 2, Qt.AlignCenter)

                # Dropdown
                dropdown = QComboBox()
                dropdown.setEnabled(False)
                dropdown.setMinimumWidth(200)
                dropdown.setEditable(False)  # Make it non-editable so clicking anywhere opens the dropdown
                dropdowns[var_name] = dropdown
                grid_layout.addWidget(dropdown, i, 3)

        layout.addLayout(grid_layout)

        # Set column stretch factors to control width
        grid_layout.setColumnStretch(0, 0)  # Checkbox - no stretch
        grid_layout.setColumnStretch(1, 1)  # Current value - can stretch
        grid_layout.setColumnStretch(2, 0)  # Refresh button - no stretch (exactly 24px)
        grid_layout.setColumnStretch(3, 2)  # Dropdown - can stretch more

        # Connect checkbox signals to populate dropdowns when checked
        def on_checkbox_toggled(var_name, checked):
            if checked:
                self._populateDropdown(var_name, dropdowns[var_name], variables, checkboxes, dropdowns, dialog)
                dropdowns[var_name].setEnabled(True)
                refresh_buttons[var_name].setEnabled(True)
                dropdowns[var_name].setFocus()
            else:
                dropdowns[var_name].setEnabled(False)
                refresh_buttons[var_name].setEnabled(False)
                # Clear the dropdown when unchecked to prevent stale data
                dropdowns[var_name].clear()

            # Update all button colors after checkbox change
            updateAllRefreshButtonColors()

        # Connect refresh button signals
        def on_refresh_clicked(var_name):
            self.tracker.debugLog.append(f"DEBUG: Refresh button clicked for {var_name}")

            # Store current dropdown selection
            current_text = dropdowns[var_name].currentText() if dropdowns[var_name].count() > 0 else ""

            # Simple rescan - just get current selections and call the original scan function
            current_selections = {}
            for v_name, checkbox in checkboxes.items():
                if checkbox.isChecked() and dropdowns.get(v_name) and dropdowns[v_name].count() > 0:
                    display_text = dropdowns[v_name].currentText()
                    if display_text.endswith(" (current)"):
                        current_selections[v_name] = display_text[:-10]
                    else:
                        current_selections[v_name] = display_text
                else:
                    current_selections[v_name] = variables.get(v_name)

            self.tracker.debugLog.append(f"DEBUG: Current selections before refresh: {current_selections}")

            # Call the exact same populate function as the checkbox
            self._populateDropdown(var_name, dropdowns[var_name], variables, checkboxes, dropdowns, dialog)

            # Update the refresh state for this dropdown to reflect current dependencies
            variable_dependencies = {
                'source_folder': [],
                'project': ['source_folder'],
                'sequence': ['source_folder', 'project'],
                'shot': ['source_folder', 'project', 'sequence'],
                'identifier': ['source_folder', 'project', 'sequence', 'shot'],
                'version': ['source_folder', 'project', 'sequence', 'shot', 'identifier'],
                'aov': ['source_folder', 'project', 'sequence', 'shot', 'identifier', 'version']
            }

            # Save the current state of all dependencies for this dropdown
            refresh_state = {}
            for dep_var in variable_dependencies[var_name]:
                if dep_var in checkboxes and checkboxes[dep_var].isChecked():
                    if dep_var in dropdowns and dropdowns[dep_var].count() > 0:
                        current_text = dropdowns[dep_var].currentText()
                        if current_text.endswith(" (current)"):
                            refresh_state[dep_var] = current_text[:-10]
                        else:
                            refresh_state[dep_var] = current_text
                    else:
                        refresh_state[dep_var] = variables.get(dep_var, '')
                else:
                    refresh_state[dep_var] = variables.get(dep_var, '')

            self.tracker.debugLog.append(f"DEBUG: Saving refresh state for {var_name}: {refresh_state}")
            dialog.refresh_states[var_name] = refresh_state

            # Make sure signal is connected (reconnect if needed)
            try:
                dropdowns[var_name].currentTextChanged.disconnect()
            except Exception:
                pass

            # Set flag during refresh population
            dropdowns[var_name].setProperty("is_populating", True)

            def on_refresh_dropdown_changed(text, v=var_name):
                # Only process color changes if not currently populating
                if not dropdowns[v].property("is_populating"):
                    self.tracker.debugLog.append(
                        f"DEBUG: {v} dropdown changed by user to '{text}' during refresh, updating colors"
                    )
                    self._updateRefreshButtonColors(dialog, checkboxes, dropdowns, refresh_buttons)

            dropdowns[var_name].currentTextChanged.connect(on_refresh_dropdown_changed)

            # Update button colors after refresh
            updateAllRefreshButtonColors()

            # Clear flag after refresh is complete
            dropdowns[var_name].setProperty("is_populating", False)

            # Try to restore the previous selection
            if current_text and dropdowns[var_name].count() > 0:
                index = dropdowns[var_name].findText(current_text)
                if index >= 0:
                    dropdowns[var_name].setCurrentIndex(index)

        # Function to update all refresh button colors based on dependency changes
        def updateAllRefreshButtonColors():
            # Call the unified method to handle color updates
            self._updateRefreshButtonColors(dialog, checkboxes, dropdowns, refresh_buttons)

        
        # Connect checkbox signals to update refresh button colors
        def on_checkbox_toggled_with_color_update(var_name, checked):
            # Handle checkbox toggle
            if checked:
                if var_name == 'source_folder':
                    # Special handling for source_folder - enable browse button instead of dropdown
                    if hasattr(dialog, 'source_folder_browse_button'):
                        dialog.source_folder_browse_button.setEnabled(True)

                    # Store the original source folder if not already stored
                    if not hasattr(dialog, 'selected_source_folder') and 'source_folder' in variables:
                        dialog.selected_source_folder = variables['source_folder']
                        if hasattr(dialog, 'source_folder_label'):
                            display_folder = variables['source_folder'] + " (current)"
                            dialog.source_folder_label.setText(f"Current: {display_folder}")
                else:
                    # Normal handling for other variables
                    # Set flag during population to prevent color updates during population
                    dropdowns[var_name].setProperty("is_populating", True)
                    self._populateDropdown(var_name, dropdowns[var_name], variables, checkboxes, dropdowns, dialog)
                    # Clear flag after population is complete
                    dropdowns[var_name].setProperty("is_populating", False)
                    dropdowns[var_name].setEnabled(True)
                    refresh_buttons[var_name].setEnabled(True)
                    dropdowns[var_name].setFocus()

                # Record the current dependency state when this dropdown is populated
                variable_dependencies = {
                    'source_folder': [],
                    'project': ['source_folder'],
                    'sequence': ['source_folder', 'project'],
                    'shot': ['source_folder', 'project', 'sequence'],
                    'identifier': ['source_folder', 'project', 'sequence', 'shot'],
                    'version': ['source_folder', 'project', 'sequence', 'shot', 'identifier'],
                    'aov': ['source_folder', 'project', 'sequence', 'shot', 'identifier', 'version']
                }

                # Save the current state of all dependencies for this dropdown
                refresh_state = {}
                for dep_var in variable_dependencies[var_name]:
                    if dep_var in checkboxes and checkboxes[dep_var].isChecked():
                        if dep_var in dropdowns and dropdowns[dep_var].count() > 0:
                            current_text = dropdowns[dep_var].currentText()
                            if current_text.endswith(" (current)"):
                                refresh_state[dep_var] = current_text[:-10]
                            else:
                                refresh_state[dep_var] = current_text
                        else:
                            refresh_state[dep_var] = variables.get(dep_var, '')
                    else:
                        refresh_state[dep_var] = variables.get(dep_var, '')

                self.tracker.debugLog.append(
                    f"DEBUG: Checkbox enabled - saving refresh state for {var_name}: {refresh_state}"
                )
                dialog.refresh_states[var_name] = refresh_state

                # Connect the signal after dropdown is populated, but add a flag to ignore initial population
                self.tracker.debugLog.append(f"DEBUG: Connecting signal for {var_name} dropdown")

                def on_dropdown_changed_with_flag(text, v=var_name):
                    # Only process color changes if not currently populating
                    if not dropdowns[v].property("is_populating"):
                        self.tracker.debugLog.append(
                            f"DEBUG: {v} dropdown changed by user to '{text}', updating colors"
                        )
                        self._updateRefreshButtonColors(dialog, checkboxes, dropdowns, refresh_buttons)

                dropdowns[var_name].currentTextChanged.connect(on_dropdown_changed_with_flag)

                # Clear the flag AFTER connecting the signal - now the dropdown is ready for user interaction
                dropdowns[var_name].setProperty("is_populating", False)
                self.tracker.debugLog.append(f"DEBUG: Cleared is_populating flag for {var_name}")
            else:
                if var_name == 'source_folder':
                    # Disable browse button when unchecked
                    if hasattr(dialog, 'source_folder_browse_button'):
                        dialog.source_folder_browse_button.setEnabled(False)
                    if hasattr(dialog, 'source_folder_label'):
                        dialog.source_folder_label.setText(f"Current: {variables.get('source_folder', 'Not set')}")
                else:
                    # Normal handling for other variables
                    dropdowns[var_name].setEnabled(False)
                    refresh_buttons[var_name].setEnabled(False)
                    # Disconnect signal when disabled to prevent interference
                    try:
                        dropdowns[var_name].currentTextChanged.disconnect()
                    except Exception:
                        pass
                    # Clear the dropdown when unchecked to prevent stale data
                    dropdowns[var_name].clear()
                    # Remove refresh state when disabled
                    if var_name in dialog.refresh_states:
                        del dialog.refresh_states[var_name]

            # Update all button colors
            updateAllRefreshButtonColors()

        for var_name in variable_order:
            if var_name in variables:
                checkboxes[var_name].toggled.connect(
                    lambda checked, name=var_name: on_checkbox_toggled_with_color_update(name, checked)
                )
                # Only connect refresh button for variables that are not source_folder
                if var_name != 'source_folder' and var_name in refresh_buttons:
                    refresh_buttons[var_name].clicked.connect(
                        lambda checked=False, name=var_name: on_refresh_clicked(name)
                    )

        # Initial color update
        updateAllRefreshButtonColors()

        layout.addWidget(QLabel(""))

        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("Apply Changes")
        ok_button.setStyleSheet("QPushButton { font-weight: bold; }")
        ok_button.setDefault(True)

        button_layout.addWidget(cancel_button)
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        # Connect button signals
        def on_cancel():
            dialog.reject()

        def on_ok():
            # Collect selected variables and their new values
            selected = {}
            for var_name in variable_order:
                if var_name in checkboxes and checkboxes[var_name].isChecked():
                    if dropdowns[var_name].count() > 0:
                        display_text = dropdowns[var_name].currentText()
                        # Get the actual value (remove "(current)" suffix if present)
                        if display_text.endswith(" (current)"):
                            actual_value = display_text[:-10]  # Remove " (current)"
                        else:
                            actual_value = display_text

                        # Check if it's actually the same as current value
                        if actual_value == variables[var_name]:  # No change selected
                            self.core.popup(f"Please select a different value for {var_name}")
                            return
                        selected[var_name] = actual_value
                    else:
                        self.core.popup(f"No options available for {var_name}")
                        return

            if not selected:
                self.core.popup("No variables selected for change")
                return

            dialog.accept()
            return selected

        cancel_button.clicked.connect(on_cancel)
        ok_button.clicked.connect(on_ok)

        # Show dialog
        result = dialog.exec_()
        if result == QDialog.Accepted:
            # Get the selected variables
            selected = {}
            for var_name in variable_order:
                if var_name in checkboxes and checkboxes[var_name].isChecked():
                    if dropdowns[var_name].count() > 0:
                        display_text = dropdowns[var_name].currentText()
                        # Get the actual value (remove "(current)" suffix if present)
                        if display_text.endswith(" (current)"):
                            actual_value = display_text[:-10]  # Remove " (current)"
                        else:
                            actual_value = display_text
                        selected[var_name] = actual_value
            return selected

        return None

    def _populateDropdown(self, var_name, dropdown, variables, checkboxes, dropdowns, dialog=None):
        """Populate dropdown with options based on disk scanning"""
        try:
            dropdown.clear()
            dropdown.addItem("Scanning...", 0)

            # Get the current selection state of other variables
            current_selections = {}
            for v_name, checkbox in checkboxes.items():
                if checkbox.isChecked() and dropdowns.get(v_name):
                    current_selections[v_name] = dropdowns[v_name].currentText()
                else:
                    current_selections[v_name] = variables.get(v_name)

            # Use a timer to avoid blocking the UI during scanning
            QTimer.singleShot(
                100, lambda: self._performDropdownScan(var_name, dropdown, variables, current_selections, dialog)
            )

        except Exception as e:
            self.core.popup(f"Error populating dropdown for {var_name}: {str(e)}")

    def _performDropdownScan(self, var_name, dropdown, variables, current_selections, dialog=None):
        """Perform the actual disk scanning for dropdown options"""
        try:
            dropdown.clear()
            options = []

            if var_name == 'source_folder':
                # Scan for source folders/drives
                options = self._scanDrivesAndFolders()
                self.tracker.debugLog.append(f"DEBUG: Source folder scanning found: {options[:10]}")
            elif var_name == 'project':
                # Scan for projects in the selected source folder
                source_folder = current_selections.get('source_folder') or variables.get('source_folder')
                if source_folder and source_folder.endswith(" (current)"):
                    source_folder = source_folder[:-10]

                self.tracker.debugLog.append(f"DEBUG: Scanning for projects in source folder: {source_folder}")
                options = self._scanSequences(source_folder)  # Scan source folder for projects
                self.tracker.debugLog.append(
                    f"DEBUG: Project scanning found projects in {source_folder}: {options[:10]}"
                )
            elif var_name == 'sequence':
                selected_project = current_selections.get('project') or variables.get('project')

                # Clean up the selected_project (remove " (current)" if present)
                if selected_project and selected_project.endswith(" (current)"):
                    selected_project = selected_project[:-10]

                # Get the source folder and project for path construction
                source_folder = current_selections.get('source_folder') or variables.get('source_folder')
                if source_folder and source_folder.endswith(" (current)"):
                    source_folder = source_folder[:-10]

                # Build the full project path
                if selected_project.startswith('/') or ':' in selected_project:
                    # It's already a full path or contains a drive letter
                    project_path = selected_project
                else:
                    # It's just the project name, build the full path with source folder
                    if source_folder:
                        project_path = os.path.join(source_folder, selected_project)
                    else:
                        project_path = selected_project

                self.tracker.debugLog.append(
                    f"DEBUG: Scanning sequences - selected_project: '{selected_project}', "
                    f"project_path: '{project_path}'"
                )
                options = self._scanSequencesFromShotsFolder(project_path)
                self.tracker.debugLog.append(f"DEBUG: Found {len(options)} sequences: {options[:10]}")  # Show first 10
            elif var_name == 'shot':
                project_path = current_selections.get('project') or variables.get('project')
                sequence = current_selections.get('sequence') or variables.get('sequence')

                # Clean up the project_path (remove " (current)" if present)
                if project_path and project_path.endswith(" (current)"):
                    project_path = project_path[:-10]

                # Clean up the sequence (remove " (current)" if present)
                if sequence and sequence.endswith(" (current)"):
                    sequence = sequence[:-10]

                # Get the current drive for path construction
                current_drive = getattr(dialog, 'current_drive', 'X:')

                # Ensure project_path starts with the detected drive if it doesn't already have a drive
                if project_path and not (':' in project_path or project_path.startswith('/')):
                    project_path = f"{current_drive}/{project_path}"

                self.tracker.debugLog.append(
                    f"DEBUG: Scanning shots - project_path: '{project_path}', sequence: '{sequence}'"
                )
                self.tracker.debugLog.append(
                    f"DEBUG: Project path type: {type(project_path)}, sequence type: {type(sequence)}"
                )

                options = self._scanShots(project_path, sequence)
                self.tracker.debugLog.append(f"DEBUG: Found {len(options)} shots: {options}")
            elif var_name == 'identifier':
                project_path = current_selections.get('project') or variables.get('project')
                sequence = current_selections.get('sequence') or variables.get('sequence')
                shot = current_selections.get('shot') or variables.get('shot')

                # Clean up all variables (remove " (current)" if present)
                for var_name_clean, var_value in [
                    ('project_path', project_path), ('sequence', sequence), ('shot', shot)
                ]:
                    if var_value and var_value.endswith(" (current)"):
                        if var_name_clean == 'project_path':
                            project_path = var_value[:-10]
                        elif var_name_clean == 'sequence':
                            sequence = var_value[:-10]
                        elif var_name_clean == 'shot':
                            shot = var_value[:-10]

                # Ensure project_path starts with X:/
                if project_path and not project_path.startswith('X:/'):
                    project_path = f"X:/{project_path}"

                options = self._scanIdentifiers(project_path, sequence, shot)
                self.tracker.debugLog.append(f"DEBUG: Found {len(options)} identifiers: {options}")
            elif var_name == 'version':
                project_path = current_selections.get('project') or variables.get('project')
                sequence = current_selections.get('sequence') or variables.get('sequence')
                shot = current_selections.get('shot') or variables.get('shot')
                identifier = current_selections.get('identifier') or variables.get('identifier')

                # Clean up all variables (remove " (current)" if present)
                for var_name_clean, var_value in [
                    ('project_path', project_path), ('sequence', sequence),
                    ('shot', shot), ('identifier', identifier)
                ]:
                    if var_value and var_value.endswith(" (current)"):
                        if var_name_clean == 'project_path':
                            project_path = var_value[:-10]
                        elif var_name_clean == 'sequence':
                            sequence = var_value[:-10]
                        elif var_name_clean == 'shot':
                            shot = var_value[:-10]
                        elif var_name_clean == 'identifier':
                            identifier = var_value[:-10]

                # Ensure project_path starts with X:/
                if project_path and not project_path.startswith('X:/'):
                    project_path = f"X:/{project_path}"

                options = self._scanVersions(project_path, sequence, shot, identifier)
                self.tracker.debugLog.append(f"DEBUG: Found {len(options)} versions: {options}")
            elif var_name == 'aov':
                project_path = current_selections.get('project') or variables.get('project')
                sequence = current_selections.get('sequence') or variables.get('sequence')
                shot = current_selections.get('shot') or variables.get('shot')
                identifier = current_selections.get('identifier') or variables.get('identifier')
                version = current_selections.get('version') or variables.get('version')

                # Clean up all variables (remove " (current)" if present)
                for var_name_clean, var_value in [
                    ('project_path', project_path), ('sequence', sequence),
                    ('shot', shot), ('identifier', identifier), ('version', version)
                ]:
                    if var_value and var_value.endswith(" (current)"):
                        if var_name_clean == 'project_path':
                            project_path = var_value[:-10]
                        elif var_name_clean == 'sequence':
                            sequence = var_value[:-10]
                        elif var_name_clean == 'shot':
                            shot = var_value[:-10]
                        elif var_name_clean == 'identifier':
                            identifier = var_value[:-10]
                        elif var_name_clean == 'version':
                            version = var_value[:-10]

                # Ensure project_path starts with X:/
                if project_path and not project_path.startswith('X:/'):
                    project_path = f"X:/{project_path}"

                options = self._scanAOVs(project_path, sequence, shot, identifier, version)
                self.tracker.debugLog.append(f"DEBUG: Found {len(options)} AOVs: {options}")

            if options:
                # Add options to dropdown, excluding the current value
                current_value = variables.get(var_name, '')
                self.tracker.debugLog.append(f"DEBUG: Current {var_name} value: '{current_value}'")
                self.tracker.debugLog.append(f"DEBUG: Available options: {sorted(options)}")

                sorted_options = sorted(options)
                self.tracker.debugLog.append(f"DEBUG: Processing sorted options: {sorted_options}")

                for option in sorted_options:
                    if option != current_value:
                        dropdown.addItem(option, option)
                        self.tracker.debugLog.append(
                            f"DEBUG: Added option: {option} (dropdown count: {dropdown.count()})"
                        )
                    else:
                        # Add current value as first option with "current" indicator
                        dropdown.insertItem(0, f"{option} (current)", option)
                        dropdown.setCurrentIndex(0)
                        self.tracker.debugLog.append(f"DEBUG: Added current value: {option} at position 0")

                # If current value wasn't in options (shouldn't happen), add it
                if current_value not in options and current_value:
                    dropdown.insertItem(0, f"{current_value} (current)", current_value)
                    dropdown.setCurrentIndex(0)
            else:
                dropdown.addItem("No options found", 0)
                self.tracker.debugLog.append(f"DEBUG: No options found for {var_name}")

        except Exception as e:
            dropdown.clear()
            dropdown.addItem(f"Error: {str(e)}", 0)
            self.tracker.debugLog.append(f"DEBUG: Error in _performDropdownScan for {var_name}: {str(e)}")

    def _scanProjectDrives(self):
        """Scan for available project drives (X:, Y:, Z:, etc.)"""
        try:
            import platform
            drives = []

            if platform.system() == "Windows":
                # Check common drive letters
                for letter in ['Z', 'Y', 'X', 'W', 'V', 'U', 'T', 'S', 'R', 'Q', 'P']:
                    drive = f"{letter}:/"
                    if os.path.exists(drive):
                        drives.append(letter)
            else:
                # For non-Windows systems, check common mount points
                common_paths = ['/Volumes', '/mnt']
                for path in common_paths:
                    if os.path.exists(path):
                        try:
                            drives.extend([item for item in os.listdir(path)
                                        if os.path.isdir(os.path.join(path, item))])
                        except Exception:
                            pass

            return drives

        except Exception as e:
            return []

    def _scanSequences(self, project_path):
        """Scan for sequences/projects - lists ALL folders in the specified path"""
        try:
            if not project_path:
                self.tracker.debugLog.append("DEBUG: No project_path provided")
                return []

            # Extract drive letter if it's just a letter
            if len(project_path) == 1 and project_path.isalpha():
                drive_path = f"{project_path}:/"
            else:
                drive_path = project_path

            self.tracker.debugLog.append(f"DEBUG: Scanning path: {drive_path}")
            sequences = []

            # Check if path exists
            if not os.path.exists(drive_path):
                self.tracker.debugLog.append(f"DEBUG: Path does not exist: {drive_path}")
                return []

            # Simply list all directories in the path (like 'ls')
            try:
                all_items = os.listdir(drive_path)
                self.tracker.debugLog.append(f"DEBUG: Found {len(all_items)} items in directory")

                for item in all_items:
                    item_path = os.path.join(drive_path, item)
                    if os.path.isdir(item_path):
                        sequences.append(item)
                        self.tracker.debugLog.append(f"DEBUG: Found directory: {item}")

                self.tracker.debugLog.append(f"DEBUG: Total directories found: {len(sequences)}")
            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error listing directory {drive_path}: {str(e)}")

            return sorted(sequences)

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanSequences: {str(e)}")
            return []

    def _isProjectFolder(self, folder_path):
        """Check if a folder looks like a project folder"""
        try:
            # Look for common project indicators
            project_indicators = [
                "03_Production",
                "Production",
                "Shots",
                "02_PreProduction",
                "01_Development"
            ]

            folder_contents = os.listdir(folder_path)
            for content in folder_contents:
                content_path = os.path.join(folder_path, content)
                if os.path.isdir(content_path):
                    if content in project_indicators:
                        return True
                    # Also check if this folder contains Shots directly
                    if content == "Shots":
                        return True

            return False
        except Exception:
            return False

    def _findSequencesInFolder(self, folder_path):
        """Recursively find sequence folders within a directory"""
        sequences = []
        try:
            # Check for Shots folder first
            shots_paths = [
                os.path.join(folder_path, "03_Production", "Shots"),
                os.path.join(folder_path, "Production", "Shots"),
                os.path.join(folder_path, "Shots")
            ]

            for shots_path in shots_paths:
                if os.path.exists(shots_path):
                    # List sequences in this Shots folder
                    try:
                        for item in os.listdir(shots_path):
                            item_path = os.path.join(shots_path, item)
                            if os.path.isdir(item_path):
                                sequences.append(item)
                    except Exception:
                        pass
                    return sequences

            # If no Shots folder found, check if this folder contains subdirectories that could be sequences
            # Limit recursion depth to avoid scanning too deep
            try:
                subdirs = [d for d in os.listdir(folder_path)
                          if os.path.isdir(os.path.join(folder_path, d))
                          and not d.startswith('.')
                          and not d.startswith('__')]

                # Only scan subdirectories if there are a reasonable number
                if len(subdirs) <= 50:  # Arbitrary limit to avoid huge scans
                    for subdir in subdirs:
                        subdir_path = os.path.join(folder_path, subdir)
                        # Check if this subdir looks like it contains shots
                        if self._containsShots(subdir_path):
                            sequences.append(subdir)
            except Exception:
                pass

        except Exception:
            pass

        return sequences

    def _containsShots(self, folder_path):
        """Check if a folder contains shot-like subdirectories"""
        try:
            # Look for common shot naming patterns
            contents = os.listdir(folder_path)
            shot_count = 0

            for item in contents[:20]:  # Check only first 20 items for performance
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    # Common shot naming patterns
                    if (re.match(r'^SH\d{3,4}$', item, re.IGNORECASE) or  # SH010, SH0123
                        re.match(r'^SQ\d{3,4}$', item, re.IGNORECASE) or  # SQ01, SQ1234
                        re.match(r'^\w{2,}_\d{3,4}$', item) or            # Any 2-4 letter prefix with numbers
                        item.upper().startswith('SHOT') or
                        item.upper().startswith('SEQUENCE')):
                        shot_count += 1

            return shot_count > 0
        except Exception:
            return False

    def _scanDrivesAndFolders(self):
        """Scan for available drives and common archive folders"""
        try:
            import platform
            import string

            options = []

            if platform.system() == 'Windows':
                # Scan available drives on Windows
                for drive in string.ascii_uppercase:
                    drive_path = f"{drive}:/"
                    if os.path.exists(drive_path):
                        options.append(drive_path)
                        self.tracker.debugLog.append(f"DEBUG: Found drive: {drive_path}")

                # Also check for common archive folders on C: if available
                common_archives = ['C:/archive', 'C:/Archive', 'C:/ARCHIVE']
                for archive in common_archives:
                    if os.path.exists(archive):
                        options.append(archive)
                        self.tracker.debugLog.append(f"DEBUG: Found archive: {archive}")
            else:
                # For non-Windows systems, just add root and common paths
                options.extend(['/'])
                common_paths = ['/archive', '/mnt/archive', '/home/archive']
                for path in common_paths:
                    if os.path.exists(path):
                        options.append(path)
                        self.tracker.debugLog.append(f"DEBUG: Found path: {path}")

            return sorted(options)

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanDrivesAndFolders: {str(e)}")
            return []

    def _scanSequencesFromShotsFolder(self, project_path):
        """Scan for sequences in X:\\[project]\\03_Production\\Shots"""
        try:
            if not project_path:
                return []

            # Build the Shots path: X:\[project]\03_Production\Shots
            shots_path = os.path.join(project_path, "03_Production", "Shots")
            self.tracker.debugLog.append(f"DEBUG: Looking for Shots folder at: {shots_path}")
            self.tracker.debugLog.append(f"DEBUG: Project path received: {project_path}")
            self.tracker.debugLog.append(f"DEBUG: Shots path exists: {os.path.exists(shots_path)}")

            if not os.path.exists(shots_path):
                self.tracker.debugLog.append(f"DEBUG: Shots folder does not exist: {shots_path}")
                return []

            # List first-level directories (sequences) in Shots folder
            sequences = []
            try:
                all_items = os.listdir(shots_path)
                self.tracker.debugLog.append(f"DEBUG: All items in Shots folder: {all_items}")

                for item in all_items:
                    item_path = os.path.join(shots_path, item)
                    is_dir = os.path.isdir(item_path)
                    self.tracker.debugLog.append(f"DEBUG: Item: {item}, Is Directory: {is_dir}")

                    if is_dir:
                        sequences.append(item)
                        self.tracker.debugLog.append(f"DEBUG: Found sequence: {item}")
            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error reading Shots folder: {str(e)}")

            self.tracker.debugLog.append(f"DEBUG: Total sequences found: {len(sequences)}")
            self.tracker.debugLog.append(f"DEBUG: Final sequences list: {sequences}")
            return sorted(sequences)

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanSequencesFromShotsFolder: {str(e)}")
            return []

    def _scanShots(self, project_path, sequence):
        """Scan for shots in the sequence"""
        try:
            if not project_path or not sequence:
                return []

            # For this structure, the sequence folder itself contains the shots
            # The sequence name is the shot name (e.g., CH01, SQ01, etc.)
            # So we need to look for subfolders within the sequence folder
            if len(project_path) == 1 and project_path.isalpha():
                drive_path = f"{project_path}:/"
                sequence_path = os.path.join(drive_path, sequence, "03_Production", "Shots", sequence)
            else:
                sequence_path = os.path.join(project_path, "03_Production", "Shots", sequence)

            self.tracker.debugLog.append(f"DEBUG: Looking for shots in sequence_path: {sequence_path}")
            self.tracker.debugLog.append(f"DEBUG: Sequence path exists: {os.path.exists(sequence_path)}")

            if not os.path.exists(sequence_path):
                # If no subfolder structure, the sequence itself is the only shot
                # Return the sequence name as a single shot option
                self.tracker.debugLog.append(f"DEBUG: No subfolder structure, returning sequence as shot: {sequence}")
                return [sequence]

            # List first-level directories (shots/subfolders) in sequence folder
            shots = []
            try:
                all_items = os.listdir(sequence_path)
                self.tracker.debugLog.append(f"DEBUG: All items in sequence folder: {all_items}")

                for item in all_items:
                    item_path = os.path.join(sequence_path, item)
                    if os.path.isdir(item_path):
                        shots.append(item)
                        self.tracker.debugLog.append(f"DEBUG: Found shot/subfolder: {item}")

                # If no subfolders found, the sequence itself is the shot
                if not shots:
                    shots.append(sequence)
                    self.tracker.debugLog.append(f"DEBUG: No subfolders found, using sequence as shot: {sequence}")

            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error reading sequence folder: {str(e)}")
                # Fallback: return the sequence name as the shot
                shots.append(sequence)

            self.tracker.debugLog.append(f"DEBUG: Final shots found: {shots}")
            return sorted(shots)

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanShots: {str(e)}")
            return []

    def _scanIdentifiers(self, project_path, sequence, shot):
        """Scan for identifiers/tasks in the shot's 3dRender folder"""
        try:
            if not project_path or not sequence or not shot:
                return []

            # Build the path to the 3dRender folder: X:\@project\03_Production\Shots\@sequence\@shot\Renders\3dRender
            renders_3d_path = os.path.join(
                project_path, "03_Production", "Shots", sequence, shot, "Renders", "3dRender"
            )

            self.tracker.debugLog.append(f"DEBUG: Scanning identifiers in: {renders_3d_path}")
            self.tracker.debugLog.append(f"DEBUG: 3dRender path exists: {os.path.exists(renders_3d_path)}")

            if not os.path.exists(renders_3d_path):
                self.tracker.debugLog.append(f"DEBUG: 3dRender folder does not exist: {renders_3d_path}")
                return []

            identifiers = []
            try:
                # List all folders in the 3dRender directory - these are the identifiers
                items = os.listdir(renders_3d_path)
                self.tracker.debugLog.append(f"DEBUG: Items in 3dRender folder: {items}")

                for item in items:
                    item_path = os.path.join(renders_3d_path, item)
                    if os.path.isdir(item_path):
                        identifiers.append(item)
                        self.tracker.debugLog.append(f"DEBUG: Found identifier: {item}")

            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error reading 3dRender folder: {str(e)}")
                return []

            self.tracker.debugLog.append(f"DEBUG: Final identifiers found: {sorted(identifiers)}")
            return sorted(identifiers)

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanIdentifiers: {str(e)}")
            return []

    def _scanVersions(self, project_path, sequence, shot, identifier):
        """Scan for versions in the identifier folder"""
        try:
            if not all([project_path, sequence, shot, identifier]):
                return []

            # Build the path to the identifier folder:
            # X:\@project\03_Production\Shots\@sequence\@shot\Renders\3dRender\@identifier
            identifier_path = os.path.join(
                project_path, "03_Production", "Shots", sequence, shot, "Renders", "3dRender", identifier
            )

            self.tracker.debugLog.append(f"DEBUG: Scanning versions in: {identifier_path}")
            self.tracker.debugLog.append(f"DEBUG: Identifier path exists: {os.path.exists(identifier_path)}")

            if not os.path.exists(identifier_path):
                self.tracker.debugLog.append(f"DEBUG: Identifier folder does not exist: {identifier_path}")
                return []

            versions = []
            try:
                # List all folders in the identifier directory - look for version folders (v####)
                items = os.listdir(identifier_path)
                self.tracker.debugLog.append(f"DEBUG: Items in identifier folder: {items}")

                for item in items:
                    item_path = os.path.join(identifier_path, item)
                    if os.path.isdir(item_path):
                        # Check if it's a version folder (starts with v and has digits)
                        if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                            versions.append(item)
                            self.tracker.debugLog.append(f"DEBUG: Found version: {item}")

            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error reading identifier folder: {str(e)}")
                return []

            # Sort latest first
            sorted_versions = sorted(versions, reverse=True)
            self.tracker.debugLog.append(f"DEBUG: Final versions found: {sorted_versions}")
            return sorted_versions

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _scanVersions: {str(e)}")
            return []

    def _scanAOVs(self, project_path, sequence, shot, identifier, version):
        """Scan for AOVs in the version folder"""
        try:
            if not all([project_path, sequence, shot, identifier, version]):
                return []

            # Build the path to the version folder:
            # X:\@project\03_Production\Shots\@sequence\@shot\Renders\3dRender\@identifier\@version
            version_path = os.path.join(
                project_path, "03_Production", "Shots", sequence, shot, "Renders", "3dRender", identifier, version
            )

            self.tracker.debugLog.append(f"DEBUG: Scanning AOVs in: {version_path}")
            self.tracker.debugLog.append(f"DEBUG: Version path exists: {os.path.exists(version_path)}")

            if not os.path.exists(version_path):
                self.tracker.debugLog.append(f"DEBUG: Version folder does not exist: {version_path}")
                return []

            aovs = []
            try:
                # List all folders in the version directory - these are the AOVs
                items = os.listdir(version_path)
                self.tracker.debugLog.append(f"DEBUG: Items in version folder: {items}")

                for item in items:
                    item_path = os.path.join(version_path, item)
                    if os.path.isdir(item_path):
                        aovs.append(item)
                        self.tracker.debugLog.append(f"DEBUG: Found AOV: {item}")

            except Exception as e:
                self.tracker.debugLog.append(f"DEBUG: Error reading version folder: {str(e)}")
                return []

            self.tracker.debugLog.append(f"DEBUG: Final AOVs found: {sorted(aovs)}")
            return sorted(aovs)

        except Exception as e:
            return []

    def _processVariableChanges(self, footage_items, original_variables, selected_variables):
        """Process the variable changes and update footage"""
        try:
            success_count = 0
            failed_count = 0
            failed_items = []

            for footage_item in footage_items:
                try:
                    # Get original path
                    original_path = footage_item.text(6)

                    # Build new path with modified variables
                    new_path = self._buildNewPath(original_variables, selected_variables, original_path)

                    if not new_path or new_path == original_path:
                        failed_count += 1
                        failed_items.append(f"{footage_item.text(0)}: No path changes made")
                        continue

                    # Check if new path exists
                    if not os.path.exists(new_path):
                        failed_count += 1
                        failed_items.append(f"{footage_item.text(0)}: New path does not exist\n{new_path}")
                        continue

                    # Show confirmation for single item
                    if len(footage_items) == 1:
                        reply = QMessageBox.question(
                            self.tracker.dlg_footage,
                            "Change Footage Path",
                            f"Replace footage source?\n\n"
                            f"From: {original_path}\n"
                            f"To: {new_path}\n\n"
                            f"This will replace the footage source in After Effects.",
                            QMessageBox.Yes | QMessageBox.No
                        )
                        if reply == QMessageBox.No:
                            failed_count += 1
                            failed_items.append(f"{footage_item.text(0)}: User cancelled")
                            continue

                    # Replace the footage
                    success = self._replaceFootageWithNewPath(footage_item, new_path)
                    if success:
                        success_count += 1
                    else:
                        failed_count += 1
                        failed_items.append(f"{footage_item.text(0)}: Failed to replace footage")

                except Exception as e:
                    failed_count += 1
                    failed_items.append(f"{footage_item.text(0)}: {str(e)}")

            # Show results
            if failed_count == 0:
                if len(footage_items) == 1:
                    self.core.popup("Successfully changed footage path")
                else:
                    self.core.popup(f"Successfully changed {success_count} footage path(s)")

                # Refresh the footage tracker
                try:
                    self.tracker.loadFootageData()
                except Exception:
                    pass
            else:
                failed_text = "\n".join(failed_items[:5])
                if len(failed_items) > 5:
                    failed_text += f"\n... and {len(failed_items) - 5} more items"
                self.core.popup(f"Changed {success_count} footage path(s) successfully.\n\n"
                              f"Failed ({failed_count}):\n{failed_text}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error processing variable changes:\n{str(e)}\n\n{traceback.format_exc()}")

    def _buildNewPath(self, original_variables, selected_variables, original_path):
        """Build new path by replacing selected variables"""
        try:
            # Normalize path
            path = original_path.replace('\\', '/')
            path_parts = path.split('/')

            # Create a copy of path parts to modify
            new_path_parts = path_parts[:]

            # Apply variable changes
            for var_name, new_value in selected_variables.items():
                if var_name == 'project':
                    # Find and replace project portion
                    production_index = -1
                    for i, part in enumerate(new_path_parts):
                        if "03_Production" in part or "Production" in part:
                            production_index = i
                            break

                    if production_index > 0:
                        # Replace everything before production with new project path
                        new_project_parts = new_value.replace('\\', '/').split('/')
                        new_path_parts = new_project_parts + new_path_parts[production_index:]

                elif var_name == 'sequence':
                    # Find and replace sequence
                    for i, part in enumerate(new_path_parts):
                        if part == "Shots" and i + 1 < len(new_path_parts):
                            if new_path_parts[i + 1] == original_variables.get('sequence'):
                                new_path_parts[i + 1] = new_value
                                break

                elif var_name == 'shot':
                    # Find and replace shot
                    for i, part in enumerate(new_path_parts):
                        if part == "Shots" and i + 2 < len(new_path_parts):
                            if new_path_parts[i + 2] == original_variables.get('shot'):
                                new_path_parts[i + 2] = new_value
                                break

                elif var_name == 'identifier':
                    # Find and replace identifier
                    for i, part in enumerate(new_path_parts):
                        if part == "Renders" and i + 1 < len(new_path_parts):
                            if new_path_parts[i + 1] in ["3dRender", "2dRender"] and i + 2 < len(new_path_parts):
                                if new_path_parts[i + 2] == original_variables.get('identifier'):
                                    new_path_parts[i + 2] = new_value
                                    break

                elif var_name == 'version':
                    # Find and replace version
                    for i, part in enumerate(new_path_parts):
                        if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                            if part == original_variables.get('version'):
                                new_path_parts[i] = new_value
                                break

                elif var_name == 'aov':
                    # Find and replace AOV
                    for i, part in enumerate(new_path_parts):
                        if part == original_variables.get('aov'):
                            new_path_parts[i] = new_value
                            break

            # Rebuild the directory path
            new_path = '/'.join(new_path_parts)

            # Update the filename with the new variables
            if os.path.isfile(new_path):
                # If new_path is a file, just update the filename part
                new_path = self._updateFilename(new_path, original_variables, selected_variables)
            else:
                # If new_path is a directory, find the file and update filename
                updated_path = self._updateFilename(new_path, original_variables, selected_variables)
                if updated_path:
                    new_path = updated_path

            # Convert back to system path format
            return os.path.normpath(new_path)

        except Exception as e:
            self.core.popup(f"Error building new path:\n{str(e)}")
            return None

    def _updateFilename(self, path, original_variables, selected_variables):
        """Update filename with new variables in the format: @sequence-@shot_@identifier_@version_@aov.1001.exr"""
        try:
            if os.path.isdir(path):
                # If path is a directory, look for image sequence files
                import glob
                pattern = os.path.join(path, "*.?????.exr")
                files = glob.glob(pattern)
                if files:
                    # Use the first file found in the sequence
                    path = files[0]
                else:
                    # If no sequence files found, try any file
                    files = glob.glob(os.path.join(path, "*"))
                    if files:
                        path = files[0]
                    else:
                        return path  # Return directory if no files found

            # Extract directory and filename
            directory = os.path.dirname(path)
            filename = os.path.basename(path)

            # Parse the filename to extract the variables
            # Pattern: @sequence-@shot_@identifier_@version_@aov.1001.exr
            import re

            # Update variables dictionary with selected changes
            current_variables = original_variables.copy()
            current_variables.update(selected_variables)

            # Extract frame number and extension
            frame_match = re.search(r'\.(\d{4,5})\.(exr|jpg|png|tga|tif)$', filename)
            if frame_match:
                frame_num = frame_match.group(1)
                extension = frame_match.group(2)

                # Build new filename: @sequence-@shot_@identifier_@version_@aov.frame_num.extension
                seq = current_variables['sequence']
                sht = current_variables['shot']
                ident = current_variables['identifier']
                ver = current_variables['version']
                aov_val = current_variables['aov']
                new_filename = f"{seq}-{sht}_{ident}_{ver}_{aov_val}.{frame_num}.{extension}"
            else:
                # If no frame number detected, just use the extension
                name, ext = os.path.splitext(filename)
                seq = current_variables['sequence']
                sht = current_variables['shot']
                ident = current_variables['identifier']
                ver = current_variables['version']
                aov_val = current_variables['aov']
                new_filename = f"{seq}-{sht}_{ident}_{ver}_{aov_val}{ext}"

            # Combine directory and new filename
            new_path = os.path.join(directory, new_filename)

            self.tracker.debugLog.append(f"DEBUG: Updated filename from '{filename}' to '{new_filename}'")
            return new_path

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Error updating filename: {str(e)}")
            return path  # Return original path if update fails

    def _replaceFootageWithNewPath(self, footage_item, new_path):
        """Replace footage item with new path"""
        try:
            footage_id = footage_item.data(0, Qt.UserRole).get('id')
            if not footage_id:
                return False

            # Use AE operations to replace the footage
            # Pre-process the path to avoid backslash in f-string
            processed_path = new_path.replace('\\', '/')
            scpt = f'''
            var footageItem = app.project.itemByID({footage_id});
            if (footageItem && footageItem instanceof FootageItem) {{
                var newFile = new File("{processed_path}");
                if (newFile.exists) {{
                    footageItem.replace(newFile);
                    "SUCCESS";
                }} else {{
                    "ERROR: File does not exist: " + newFile.fsName;
                }}
            }} else {{
                "ERROR: Footage item not found";
            }}
            '''

            result = self.tracker.main.ae_core.executeAppleScript(scpt)
            result_str = result.decode('utf-8') if isinstance(result, bytes) else str(result)

            if result and "SUCCESS" in result_str:
                return True
            else:
                self.core.popup(f"Failed to replace footage in After Effects.\n\nError: {result_str}")
                return False

        except Exception as e:
            import traceback
            self.core.popup(f"Error replacing footage:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

    def _browseForSourceFolder(self, dialog, checkboxes, dropdowns):
        """Browse for source folder using folder selection dialog"""
        try:
            from qtpy.QtWidgets import QFileDialog

            # Get current source folder as starting point
            current_folder = getattr(dialog, 'selected_source_folder', '')
            if not current_folder and 'source_folder' in dialog.original_variables:
                current_folder = dialog.original_variables['source_folder']

            if not current_folder:
                current_folder = "X:/"  # Default fallback

            # Open folder browser dialog
            folder = QFileDialog.getExistingDirectory(
                dialog,
                "Select Source Folder",
                current_folder,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )

            if folder:
                # Normalize path (replace backslashes with forward slashes)
                folder = folder.replace('\\', '/')

                # Store the selected folder
                dialog.selected_source_folder = folder

                # Store dropdowns reference in dialog if not already there
                if not hasattr(dialog, 'dropdowns'):
                    dialog.dropdowns = dropdowns

                # Update the current label
                if hasattr(dialog, 'source_folder_label'):
                    display_folder = folder
                    if ('source_folder' in dialog.original_variables
                            and folder == dialog.original_variables['source_folder']):
                        display_folder += " (current)"
                    dialog.source_folder_label.setText(f"Current: {display_folder}")

                self.tracker.debugLog.append(f"DEBUG: Selected source folder: {folder}")

                # Trigger dependent dropdown updates if they're enabled
                self._triggerDependentUpdates('source_folder', dialog, checkboxes)

        except Exception as e:
            self.core.popup(f"Error browsing for folder:\n{str(e)}")
            self.tracker.debugLog.append(f"DEBUG: Exception in _browseForSourceFolder: {str(e)}")

    def _triggerDependentUpdates(self, changed_var_name, dialog, checkboxes):
        """Trigger updates for all dependent variables when a variable changes"""
        try:
            # Define dependencies
            variable_dependencies = {
                'source_folder': [],
                'project': ['source_folder'],
                'sequence': ['source_folder', 'project'],
                'shot': ['source_folder', 'project', 'sequence'],
                'identifier': ['source_folder', 'project', 'sequence', 'shot'],
                'version': ['source_folder', 'project', 'sequence', 'shot', 'identifier'],
                'aov': ['source_folder', 'project', 'sequence', 'shot', 'identifier', 'version']
            }

            # Find all variables that depend on the changed variable
            dependents = []
            for var_name, deps in variable_dependencies.items():
                if changed_var_name in deps and checkboxes.get(var_name) and checkboxes[var_name].isChecked():
                    dependents.append(var_name)

            # Repopulate all dependent dropdowns
            # Get the dropdowns from dialog if available
            available_dropdowns = getattr(dialog, 'dropdowns', {})
            if available_dropdowns and dependents:
                for dependent in dependents:
                    if dependent in available_dropdowns:
                        # Clear and repopulate the dependent dropdown
                        available_dropdowns[dependent].clear()
                        available_dropdowns[dependent].addItem("Scanning...", 0)

                        # Schedule repopulation
                        current_selections = {}
                        for v_name, checkbox in checkboxes.items():
                            if checkbox.isChecked() and v_name in available_dropdowns:
                                current_selections[v_name] = available_dropdowns[v_name].currentText()
                            else:
                                current_selections[v_name] = dialog.original_variables.get(v_name, '')

                        # Use QTimer to avoid blocking
                        from qtpy.QtCore import QTimer
                        QTimer.singleShot(100, lambda: self._performDropdownScan(
                            dependent, available_dropdowns[dependent],
                            dialog.original_variables, current_selections, dialog
                        ))

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _triggerDependentUpdates: {str(e)}")

    def _updateRefreshButtonColors(self, dialog, checkboxes, dropdowns, refresh_buttons):
        """Update refresh button colors based on whether dropdown content is up-to-date with dependencies"""
        # Define dependencies for each variable in order
        variable_dependencies = {
            'source_folder': [],
            'project': ['source_folder'],
            'sequence': ['source_folder', 'project'],
            'shot': ['source_folder', 'project', 'sequence'],
            'identifier': ['source_folder', 'project', 'sequence', 'shot'],
            'version': ['source_folder', 'project', 'sequence', 'shot', 'identifier'],
            'aov': ['source_folder', 'project', 'sequence', 'shot', 'identifier', 'version']
        }

        # Get original values from dialog
        original_variables = getattr(dialog, 'original_variables', {})
        refresh_states = getattr(dialog, 'refresh_states', {})

        self.tracker.debugLog.append("DEBUG: _updateRefreshButtonColors called")
        self.tracker.debugLog.append(f"DEBUG: refresh_states = {refresh_states}")

        for var_name, refresh_button in refresh_buttons.items():
            if var_name == 'source_folder':
                continue  # Skip source_folder in color checks (it uses browse button instead)

            self.tracker.debugLog.append(
                f"DEBUG: Checking variable '{var_name}', enabled: {refresh_button.isEnabled()}"
            )

            # Check if this dropdown needs refresh by comparing current dependency values
            # with the values that were current when this dropdown was last refreshed
            needs_refresh = False

            # Check this variable if it's enabled OR if it has dependencies that are enabled
            should_check = False
            if refresh_button.isEnabled():
                should_check = True
                self.tracker.debugLog.append(f"DEBUG: {var_name} is enabled")
            elif var_name in checkboxes and checkboxes[var_name].isChecked():
                should_check = True
                self.tracker.debugLog.append(f"DEBUG: {var_name} is explicitly checked")
            else:
                # Also check if this variable has any enabled dependencies
                self.tracker.debugLog.append(
                    f"DEBUG: {var_name} is not enabled and not checked, checking dependencies..."
                )
                for dep_var in variable_dependencies[var_name]:
                    self.tracker.debugLog.append(f"DEBUG: {var_name}: checking if {dep_var} is enabled...")
                    if dep_var in checkboxes and checkboxes[dep_var].isChecked():
                        self.tracker.debugLog.append(
                            f"DEBUG: {var_name}: {dep_var} IS enabled, so {var_name} should be checked"
                        )
                        should_check = True
                        break
                if not should_check:
                    self.tracker.debugLog.append(f"DEBUG: {var_name}: no enabled dependencies found")

            if not should_check:
                self.tracker.debugLog.append(f"DEBUG: {var_name} should not be checked, skipping")
                continue

            self.tracker.debugLog.append(
                f"DEBUG: {var_name} should be checked (enabled or has enabled dependencies), checking dependencies"
            )

            # Get the refresh state for this variable (when it was last populated)
            var_refresh_state = refresh_states.get(var_name, {})
            self.tracker.debugLog.append(f"DEBUG: {var_name} refresh_state = {var_refresh_state}")

            # Check each dependency to see if it has changed since this dropdown was refreshed
            for dep_var in variable_dependencies[var_name]:
                self.tracker.debugLog.append(f"DEBUG: {var_name}: checking dependency '{dep_var}'")

                # Get current value of this dependency
                current_dep_value = ''
                if dep_var in checkboxes and checkboxes[dep_var].isChecked():
                    if dep_var in dropdowns and dropdowns[dep_var].count() > 0:
                        current_text = dropdowns[dep_var].currentText()
                        if current_text.endswith(" (current)"):
                            current_dep_value = current_text[:-10]
                        else:
                            current_dep_value = current_text
                    else:
                        current_dep_value = original_variables.get(dep_var, '')
                else:
                    # For unchecked dependencies, use original value
                    current_dep_value = original_variables.get(dep_var, '')

                # Get the value that this dependency had when this dropdown was last refreshed
                refreshed_dep_value = var_refresh_state.get(dep_var, None)

                self.tracker.debugLog.append(
                    f"DEBUG: {var_name}: {dep_var} current='{current_dep_value}', "
                    f"refresh_time='{refreshed_dep_value}'"
                )

                # If refresh state doesn't exist for this dependency, it means this dropdown
                # was populated before dependencies were set up, so it needs refresh
                if refreshed_dep_value is None:
                    self.tracker.debugLog.append(f"DEBUG: {var_name}: {dep_var} refresh_state is None, needs refresh")
                    needs_refresh = True
                    break

                # If the current value is different from the refresh-time value, this dropdown needs refresh
                if current_dep_value != refreshed_dep_value:
                    self.tracker.debugLog.append(f"DEBUG: {var_name}: {dep_var} values differ, needs refresh")
                    needs_refresh = True
                    break
            else:
                self.tracker.debugLog.append(f"DEBUG: {var_name}: all dependencies match, no refresh needed")

            self.tracker.debugLog.append(f"DEBUG: {var_name} final result: needs_refresh = {needs_refresh}")

            # Update button color based on whether refresh is needed
            if needs_refresh:
                refresh_button.setStyleSheet("""
                    QPushButton {
                        background-color: #FFB6C1;  /* Light red */
                        border: 1px solid #DC143C;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                        color: #8B0000;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #FF69B4;  /* Hot pink on hover */
                        border: 1px solid #8B0000;
                    }
                    QPushButton:pressed {
                        background-color: #DC143C;  /* Crimson when pressed */
                        border: 1px solid #8B0000;
                    }
                """)
            else:
                refresh_button.setStyleSheet("""
                    QPushButton {
                        background-color: #90EE90;  /* Light green */
                        border: 1px solid #228B22;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                        color: #006400;
                        padding: 0px;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #7CFC00;  /* Brighter green on hover */
                        border: 1px solid #006400;
                    }
                    QPushButton:pressed {
                        background-color: #32CD32;  /* Darker green when pressed */
                        border: 1px solid #006400;
                    }
                """)
    @err_catcher(name=__name__)
    def getAvailable2DIdentifiers(self, shot_name):
        """Scan the Prism file system to find all available 2D render and Playblast identifiers for a shot"""
        try:
            import os
            import re

            print(f"[DEBUG IDENTIFIER SCAN] Scanning for 2D/PB identifiers for shot: {shot_name}")

            # First, get a reference path from existing footage to determine the project structure
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
            reference_path = None

            print(f"[DEBUG IDENTIFIER SCAN] Hierarchy has '2D Renders': {'2D Renders' in hierarchy}")
            if '2D Renders' in hierarchy:
                print(f"[DEBUG IDENTIFIER SCAN] Shots in 2D Renders: {list(hierarchy['2D Renders'].keys())}")

            if '2D Renders' in hierarchy and shot_name in hierarchy['2D Renders']:
                print(f"[DEBUG IDENTIFIER SCAN] Shot {shot_name} found in hierarchy")
                # Get the path from the first footage in the hierarchy
                for identifier in hierarchy['2D Renders'][shot_name]:
                    identifier_data = hierarchy['2D Renders'][shot_name][identifier]
                    for aov, footage_list in identifier_data.items():
                        if footage_list and len(footage_list) > 0:
                            reference_path = footage_list[0].get('path', '')
                            print(f"[DEBUG IDENTIFIER SCAN] Got reference from {identifier}/{aov}")
                            break
                        if reference_path:
                            break
                    if reference_path:
                        break

            if not reference_path:
                print(f"[DEBUG IDENTIFIER SCAN] No reference path found in hierarchy")
                return []

            print(f"[DEBUG IDENTIFIER SCAN] Reference path: {reference_path[:100]}")

            # Extract the project path structure
            path_parts = reference_path.replace('\\', '/').split('/')
            print(f"[DEBUG IDENTIFIER SCAN] Path parts: {path_parts}")

            # Find key path components (shot folder)
            production_index = -1
            shots_folder_index = -1  # Index of "Shots" folder
            shot_folder_index = -1  # Index of the actual shot folder (e.g., SH020)

            for i, part in enumerate(path_parts):
                if "03_Production" in part:
                    production_index = i
                elif part == "Shots" and production_index > 0:
                    shots_folder_index = i
                # Look for shot folder pattern (SH####, SQ####)
                elif shots_folder_index > 0 and shot_folder_index == -1:
                    import re
                    if re.match(r'(SH|SQ|CH|EP)\d+', part, re.IGNORECASE):
                        # Check if next part is also a shot folder (sequence-shot pattern)
                        if i + 1 < len(path_parts):
                            next_part = path_parts[i + 1]
                            if re.match(r'(SH|SQ|CH|EP)\d+', next_part, re.IGNORECASE):
                                # This is the sequence folder, next is shot
                                shot_folder_index = i + 1
                                break
                        # Single shot folder pattern
                        shot_folder_index = i
                        break

            print(
                f"[DEBUG IDENTIFIER SCAN] shots_folder_index: {shots_folder_index}, "
                f"shot_folder_index: {shot_folder_index}"
            )

            if shot_folder_index == -1:
                print(f"[DEBUG IDENTIFIER SCAN] Could not find shot folder in path")
                return []

            # Build the base path to the shot folder
            # .../03_Production/Shots/[Sequence]/[Shot]/
            shot_base_path = '/'.join(path_parts[:shot_folder_index + 1])
            print(f"[DEBUG IDENTIFIER SCAN] Shot base path: {shot_base_path}")

            # Collect all identifiers from both 2dRender and Playblasts folders
            all_identifiers = {}  # identifier -> folder_type mapping

            # Check for 2dRender folder: .../Shots/[Seq]/[Shot]/Renders/2dRender/
            renders_2d_path = shot_base_path + '/Renders/2dRender'
            if os.path.exists(renders_2d_path):
                print(f"[DEBUG IDENTIFIER SCAN] Scanning 2dRender folder: {renders_2d_path}")
                try:
                    for item in os.listdir(renders_2d_path):
                        item_path = renders_2d_path + '/' + item
                        if os.path.isdir(item_path):
                            # Check if this could be an identifier folder (has version folders inside)
                            has_version_folders = False
                            for subitem in os.listdir(item_path):
                                if subitem.startswith('v') and len(subitem) >= 5 and subitem[1:5].isdigit():
                                    has_version_folders = True
                                    break
                            if has_version_folders:
                                all_identifiers[item] = '2dRender'
                                print(f"[DEBUG IDENTIFIER SCAN] Found 2D identifier: {item}")
                except Exception as e:
                    print(f"[DEBUG IDENTIFIER SCAN] Error scanning 2dRender: {str(e)}")

            # Check for Playblasts folder: .../Shots/[Seq]/[Shot]/Playblasts/
            playblasts_path = shot_base_path + '/Playblasts'
            print(f"[DEBUG IDENTIFIER SCAN] Checking Playblasts path: {playblasts_path}")
            print(f"[DEBUG IDENTIFIER SCAN] Playblasts exists: {os.path.exists(playblasts_path)}")
            if os.path.exists(playblasts_path):
                print(f"[DEBUG IDENTIFIER SCAN] Scanning Playblasts folder: {playblasts_path}")
                try:
                    for item in os.listdir(playblasts_path):
                        item_path = playblasts_path + '/' + item
                        if os.path.isdir(item_path):
                            # Check if this could be an identifier folder (has version folders inside)
                            has_version_folders = False
                            for subitem in os.listdir(item_path):
                                if subitem.startswith('v') and len(subitem) >= 5 and subitem[1:5].isdigit():
                                    has_version_folders = True
                                    break
                            if has_version_folders:
                                all_identifiers[item] = 'Playblasts'
                                print(f"[DEBUG IDENTIFIER SCAN] Found PB identifier: {item}")
                except Exception as e:
                    print(f"[DEBUG IDENTIFIER SCAN] Error scanning Playblasts: {str(e)}")
                    import traceback
                    print(f"[DEBUG IDENTIFIER SCAN] Traceback: {traceback.format_exc()}")
            else:
                print(f"[DEBUG IDENTIFIER SCAN] Playblasts folder not found at: {playblasts_path}")

            # Sort identifiers and return them with folder info
            sorted_identifiers = sorted(all_identifiers.keys())
            print(f"[DEBUG IDENTIFIER SCAN] Total identifiers found: {sorted_identifiers}")

            # Return list of (identifier, folder_type) tuples
            return [(ident, all_identifiers[ident]) for ident in sorted_identifiers]

        except Exception as e:
            import traceback
            print(f"[DEBUG IDENTIFIER SCAN] Exception: {str(e)}")
            print(f"[DEBUG IDENTIFIER SCAN] Traceback: {traceback.format_exc()}")
            return []

    @err_catcher(name=__name__)
    def getAvailable3DIdentifiers(self, shot_name):
        """Scan the Prism file system to find all available 3D render identifiers for a shot"""
        try:
            import os
            import re

            print(f"[DEBUG IDENTIFIER SCAN] Scanning for 3D identifiers for shot: {shot_name}")

            # First, get a reference path from existing footage to determine the project structure
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
            reference_path = None

            print(f"[DEBUG IDENTIFIER SCAN] Hierarchy has '3D Renders': {'3D Renders' in hierarchy}")
            if '3D Renders' in hierarchy:
                print(f"[DEBUG IDENTIFIER SCAN] Shots in 3D Renders: {list(hierarchy['3D Renders'].keys())}")

            if '3D Renders' in hierarchy and shot_name in hierarchy['3D Renders']:
                print(f"[DEBUG IDENTIFIER SCAN] Shot {shot_name} found in hierarchy")
                # Get the path from the first footage in the hierarchy
                for identifier in hierarchy['3D Renders'][shot_name]:
                    identifier_data = hierarchy['3D Renders'][shot_name][identifier]
                    for aov, footage_list in identifier_data.items():
                        if footage_list and len(footage_list) > 0:
                            reference_path = footage_list[0].get('path', '')
                            print(f"[DEBUG IDENTIFIER SCAN] Got reference from {identifier}/{aov}")
                            break
                        if reference_path:
                            break
                    if reference_path:
                        break

            if not reference_path:
                print(f"[DEBUG IDENTIFIER SCAN] No reference path found in hierarchy")
                return []

            print(f"[DEBUG IDENTIFIER SCAN] Reference path: {reference_path[:100]}")

            # Extract the project path structure
            path_parts = reference_path.replace('\\', '/').split('/')
            print(f"[DEBUG IDENTIFIER SCAN] Path parts: {path_parts}")

            # Find key path components (shot folder)
            production_index = -1
            shots_folder_index = -1  # Index of "Shots" folder
            shot_folder_index = -1  # Index of the actual shot folder (e.g., SH020)

            for i, part in enumerate(path_parts):
                if "03_Production" in part:
                    production_index = i
                elif part == "Shots" and production_index > 0:
                    shots_folder_index = i
                # Look for shot folder pattern (SH####, SQ####)
                elif shots_folder_index > 0 and shot_folder_index == -1:
                    import re
                    if re.match(r'(SH|SQ|CH|EP)\d+', part, re.IGNORECASE):
                        # Check if next part is also a shot folder (sequence-shot pattern)
                        if i + 1 < len(path_parts):
                            next_part = path_parts[i + 1]
                            if re.match(r'(SH|SQ|CH|EP)\d+', next_part, re.IGNORECASE):
                                # This is the sequence folder, next is shot
                                shot_folder_index = i + 1
                                break
                        # Single shot folder pattern
                        shot_folder_index = i
                        break

            print(
                f"[DEBUG IDENTIFIER SCAN] shots_folder_index: {shots_folder_index}, "
                f"shot_folder_index: {shot_folder_index}"
            )

            if shot_folder_index == -1:
                print(f"[DEBUG IDENTIFIER SCAN] Could not find shot folder in path")
                return []

            # Build the base path to the shot folder
            # .../03_Production/Shots/[Sequence]/[Shot]/
            shot_base_path = '/'.join(path_parts[:shot_folder_index + 1])
            print(f"[DEBUG IDENTIFIER SCAN] Shot base path: {shot_base_path}")

            # Collect all identifiers from 3dRender folder
            all_identifiers = {}  # identifier -> folder_type mapping

            # Check for 3dRender folder: .../Shots/[Seq]/[Shot]/Renders/3dRender/
            renders_3d_path = shot_base_path + '/Renders/3dRender'
            if os.path.exists(renders_3d_path):
                print(f"[DEBUG IDENTIFIER SCAN] Scanning 3dRender folder: {renders_3d_path}")
                try:
                    for item in os.listdir(renders_3d_path):
                        item_path = renders_3d_path + '/' + item
                        if os.path.isdir(item_path):
                            # Check if this could be an identifier folder (has version folders inside)
                            has_version_folders = False
                            for subitem in os.listdir(item_path):
                                if subitem.startswith('v') and len(subitem) >= 5 and subitem[1:5].isdigit():
                                    has_version_folders = True
                                    break
                            if has_version_folders:
                                all_identifiers[item] = '3dRender'
                                print(f"[DEBUG IDENTIFIER SCAN] Found 3D identifier: {item}")
                except Exception as e:
                    print(f"[DEBUG IDENTIFIER SCAN] Error scanning 3dRender: {str(e)}")

            # Sort identifiers and return them with folder info
            sorted_identifiers = sorted(all_identifiers.keys())
            print(f"[DEBUG IDENTIFIER SCAN] Total 3D identifiers found: {sorted_identifiers}")

            # Return list of (identifier, folder_type) tuples
            return [(ident, all_identifiers[ident]) for ident in sorted_identifiers]

        except Exception as e:
            import traceback
            print(f"[DEBUG IDENTIFIER SCAN] Exception: {str(e)}")
            print(f"[DEBUG IDENTIFIER SCAN] Traceback: {traceback.format_exc()}")
            return []

    @err_catcher(name=__name__)
    def getLatestVersionPathFor2DIdentifier(self, shot_name, identifier, target_folder_type=None):
        """Get the path to the latest version of a 2D render identifier from the file system
        Args:
            shot_name: The shot name
            identifier: The identifier/task name
            target_folder_type: '2dRender' or 'Playblasts' - which folder to look in
        """
        try:
            import os
            import re

            print(
                f"[DEBUG IDENTIFIER PATH] Finding latest version for {shot_name}/{identifier}, "
                f"target: {target_folder_type}"
            )

            # First, get a reference path from existing footage to determine the project structure
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
            reference_path = None

            print(f"[DEBUG IDENTIFIER PATH] Hierarchy keys: {list(hierarchy.keys())}")
            print(f"[DEBUG IDENTIFIER PATH] '2D Renders' in hierarchy: {'2D Renders' in hierarchy}")

            if '2D Renders' in hierarchy:
                print(f"[DEBUG IDENTIFIER PATH] 2D Renders shots: {list(hierarchy['2D Renders'].keys())}")
                print(f"[DEBUG IDENTIFIER PATH] Looking for shot: '{shot_name}'")

            if '2D Renders' in hierarchy and shot_name in hierarchy['2D Renders']:
                # Get the path from the first footage in the hierarchy
                for ident in hierarchy['2D Renders'][shot_name]:
                    identifier_data = hierarchy['2D Renders'][shot_name][ident]
                    for aov, footage_list in identifier_data.items():
                        if footage_list and len(footage_list) > 0:
                            reference_path = footage_list[0].get('path', '')
                            break
                        if reference_path:
                            break
                    if reference_path:
                        break

            if not reference_path:
                print(f"[DEBUG IDENTIFIER PATH] No reference path found in hierarchy")
                return None

            # Use target_folder_type if provided, otherwise detect from reference path
            if target_folder_type:
                folder_type = target_folder_type
            else:
                if '/playblasts/' in reference_path.lower():
                    folder_type = 'Playblasts'
                else:
                    folder_type = '2dRender'

            print(f"[DEBUG IDENTIFIER PATH] Using folder type: {folder_type}")

            # Extract the project path structure
            # Pattern for 2D Renders: .../03_Production/Shots/[Sequence]/[Shot]/Renders/2dRender/[Identifier]/...
            # Pattern for Playblasts: .../03_Production/Shots/[Sequence]/[Shot]/Playblasts/[Identifier]/...
            path_parts = reference_path.replace('\\', '/').split('/')

            # Find key path components
            production_index = -1
            shots_folder_index = -1  # Index of "Shots" folder
            shot_folder_index = -1  # Index of the actual shot folder (e.g., SH020)

            for i, part in enumerate(path_parts):
                if "03_Production" in part:
                    production_index = i
                elif part == "Shots" and production_index > 0:
                    shots_folder_index = i
                # Look for shot folder pattern (SH####, SQ####)
                elif shots_folder_index > 0 and shot_folder_index == -1:
                    import re
                    if re.match(r'(SH|SQ|CH|EP)\d+', part, re.IGNORECASE):
                        # Check if next part is also a shot folder (sequence-shot pattern)
                        if i + 1 < len(path_parts):
                            next_part = path_parts[i + 1]
                            if re.match(r'(SH|SQ|CH|EP)\d+', next_part, re.IGNORECASE):
                                # This is the sequence folder, next is shot
                                shot_folder_index = i + 1
                                break
                        # Single shot folder pattern
                        shot_folder_index = i
                        break

            if shot_folder_index == -1:
                print(f"[DEBUG IDENTIFIER PATH] Could not find shot folder in path")
                return None

            # Build the shot base path
            shot_base_path = '/'.join(path_parts[:shot_folder_index + 1])

            # Build the identifier folder path based on folder_type
            if folder_type == 'Playblasts':
                identifier_path = shot_base_path + '/Playblasts/' + identifier
            else:
                identifier_path = shot_base_path + '/Renders/2dRender/' + identifier

            print(f"[DEBUG IDENTIFIER PATH] Identifier folder: {identifier_path}")

            if not os.path.exists(identifier_path):
                print(f"[DEBUG IDENTIFIER PATH] Identifier folder does not exist: {identifier_path}")
                return None

            # Find all version folders
            version_folders = []
            try:
                for item in os.listdir(identifier_path):
                    # Use forward slash consistently to avoid escaping issues in JavaScript
                    item_path = identifier_path + '/' + item
                    if os.path.isdir(item_path):
                        # Check if this is a version folder (v#### pattern)
                        if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                            version_num = int(item[1:5])
                            version_folders.append((version_num, item_path))
                            print(f"[DEBUG IDENTIFIER PATH] Found version: {item} (v{version_num})")

            except Exception as e:
                print(f"[DEBUG IDENTIFIER PATH] Error scanning versions: {str(e)}")
                return None

            if not version_folders:
                print(f"[DEBUG IDENTIFIER PATH] No version folders found")
                return None

            # Sort by version number and get the latest
            version_folders.sort(key=lambda x: x[0], reverse=True)
            latest_version_path = version_folders[0][1]
            print(f"[DEBUG IDENTIFIER PATH] Latest version folder: {latest_version_path}")

            # Now find the footage file in this version folder
            # Look for common image sequences or movie files
            footage_path = None
            try:
                print(f"[DEBUG IDENTIFIER PATH] Scanning version folder: {latest_version_path}")

                # First, list all contents to understand the structure
                all_items = os.listdir(latest_version_path)
                print(f"[DEBUG IDENTIFIER PATH] Version folder contents: {all_items}")

                for item in all_items:
                    # Use forward slash consistently to avoid escaping issues in JavaScript
                    item_path = latest_version_path + '/' + item

                    if os.path.isdir(item_path):
                        item_lower = item.lower()
                        # Check for common render folders (beauty, main, render, etc.)
                        if any(x in item_lower for x in ['beauty', 'main', 'render', 'final', 'comp', 'output']):
                            # Look for files in this subfolder
                            print(f"[DEBUG IDENTIFIER PATH] Checking render subfolder: {item}")
                            subfolder_path = latest_version_path + '/' + item
                            try:
                                for file in os.listdir(subfolder_path):
                                    file_path = subfolder_path + '/' + file
                                    if os.path.isfile(file_path):
                                        # Check for image sequence or movie files
                                        ext = os.path.splitext(file)[1].lower()
                                        if ext in ['.exr', '.jpg', '.png', '.tiff', '.tif', '.mov', '.mp4', '.avi']:
                                            footage_path = file_path
                                            print(f"[DEBUG IDENTIFIER PATH] Found footage: {footage_path}")
                                            break
                                if footage_path:
                                    break
                            except Exception as sub_e:
                                print(f"[DEBUG IDENTIFIER PATH] Error scanning subfolder: {sub_e}")
                    elif os.path.isfile(item_path):
                        # Check if this is a footage file
                        ext = os.path.splitext(item)[1].lower()
                        if ext in ['.exr', '.jpg', '.png', '.tiff', '.tif', '.mov', '.mp4', '.avi']:
                            footage_path = item_path
                            print(f"[DEBUG IDENTIFIER PATH] Found footage in version root: {footage_path}")
                            break

            except Exception as e:
                print(f"[DEBUG IDENTIFIER PATH] Error finding footage file: {str(e)}")
                import traceback
                print(f"[DEBUG IDENTIFIER PATH] Traceback: {traceback.format_exc()}")
                return None

            if not footage_path:
                print(f"[DEBUG IDENTIFIER PATH] No footage file found in latest version")
                return None

            print(f"[DEBUG IDENTIFIER PATH] Final footage path: {footage_path}")
            return footage_path

        except Exception as e:
            import traceback
            print(f"[DEBUG IDENTIFIER PATH] Exception: {str(e)}")
            print(f"[DEBUG IDENTIFIER PATH] Traceback: {traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def getLatestVersionPathFor3DIdentifier(self, shot_name, identifier, aov='beauty'):
        """Get the path to the latest version of a 3D render identifier's AOV from the file system

        Args:
            shot_name: The shot name
            identifier: The identifier/task name (e.g., "Lighting", "Layout")
            aov: The AOV name (e.g., "beauty", "diffuse", "normal")

        Returns:
            Path to the latest version file or None
        """
        try:
            import os
            import re

            print(f"[DEBUG IDENTIFIER PATH 3D] Finding latest version for {shot_name}/{identifier}/{aov}")

            # First, get a reference path from existing footage to determine the project structure
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
            reference_path = None

            print(f"[DEBUG IDENTIFIER PATH 3D] Hierarchy keys: {list(hierarchy.keys())}")
            print(f"[DEBUG IDENTIFIER PATH 3D] '3D Renders' in hierarchy: {'3D Renders' in hierarchy}")

            if '3D Renders' in hierarchy:
                print(f"[DEBUG IDENTIFIER PATH 3D] 3D Renders shots: {list(hierarchy['3D Renders'].keys())}")
                print(f"[DEBUG IDENTIFIER PATH 3D] Looking for shot: '{shot_name}'")

            if '3D Renders' in hierarchy and shot_name in hierarchy['3D Renders']:
                # Get the path from the first footage in the hierarchy
                for ident in hierarchy['3D Renders'][shot_name]:
                    identifier_data = hierarchy['3D Renders'][shot_name][ident]
                    for aov_key, footage_list in identifier_data.items():
                        if footage_list and len(footage_list) > 0:
                            reference_path = footage_list[0].get('path', '')
                            print(f"[DEBUG IDENTIFIER PATH 3D] Got reference from {ident}/{aov_key}")
                            break
                        if reference_path:
                            break
                    if reference_path:
                        break

            if not reference_path:
                print(f"[DEBUG IDENTIFIER PATH 3D] No reference path found in hierarchy")
                return None

            # Extract the project path structure
            # Pattern for 3D Renders:
            # .../03_Production/Shots/[Sequence]/[Shot]/Renders/3dRender/[Identifier]/v####/[AOV]/...
            path_parts = reference_path.replace('\\', '/').split('/')

            # Find key path components
            production_index = -1
            shots_folder_index = -1  # Index of "Shots" folder
            shot_folder_index = -1  # Index of the actual shot folder (e.g., SH020)

            for i, part in enumerate(path_parts):
                if "03_Production" in part:
                    production_index = i
                elif part == "Shots" and production_index > 0:
                    shots_folder_index = i
                # Look for shot folder pattern (SH####, SQ####)
                elif shots_folder_index > 0 and shot_folder_index == -1:
                    import re
                    if re.match(r'(SH|SQ|CH|EP)\d+', part, re.IGNORECASE):
                        # Check if next part is also a shot folder (sequence-shot pattern)
                        if i + 1 < len(path_parts):
                            next_part = path_parts[i + 1]
                            if re.match(r'(SH|SQ|CH|EP)\d+', next_part, re.IGNORECASE):
                                # This is the sequence folder, next is shot
                                shot_folder_index = i + 1
                                break
                        # Single shot folder pattern
                        shot_folder_index = i
                        break

            if shot_folder_index == -1:
                print(f"[DEBUG IDENTIFIER PATH 3D] Could not find shot folder in path")
                return None

            # Build the shot base path
            shot_base_path = '/'.join(path_parts[:shot_folder_index + 1])

            # Build the AOV folder path for 3D renders
            # Pattern: .../Shots/[Seq]/[Shot]/Renders/3dRender/[Identifier]/v####/[AOV]/
            identifier_path = shot_base_path + '/Renders/3dRender/' + identifier

            print(f"[DEBUG IDENTIFIER PATH 3D] Identifier folder: {identifier_path}")

            if not os.path.exists(identifier_path):
                print(f"[DEBUG IDENTIFIER PATH 3D] Identifier folder does not exist: {identifier_path}")
                return None

            # Find all version folders
            version_folders = []
            try:
                for item in os.listdir(identifier_path):
                    item_path = identifier_path + '/' + item
                    if os.path.isdir(item_path):
                        # Check if this is a version folder (v#### pattern)
                        if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                            version_num = int(item[1:5])
                            version_folders.append((version_num, item_path))
                            print(f"[DEBUG IDENTIFIER PATH 3D] Found version: {item} (v{version_num})")

            except Exception as e:
                print(f"[DEBUG IDENTIFIER PATH 3D] Error scanning versions: {str(e)}")
                return None

            if not version_folders:
                print(f"[DEBUG IDENTIFIER PATH 3D] No version folders found")
                return None

            # Sort by version number and get the latest
            version_folders.sort(key=lambda x: x[0], reverse=True)
            latest_version_path = version_folders[0][1]
            print(f"[DEBUG IDENTIFIER PATH 3D] Latest version folder: {latest_version_path}")

            # Now find the AOV folder and footage file
            aov_path = latest_version_path + '/' + aov
            print(f"[DEBUG IDENTIFIER PATH 3D] Looking for AOV folder: {aov_path}")

            if not os.path.exists(aov_path):
                print(f"[DEBUG IDENTIFIER PATH 3D] AOV folder does not exist: {aov_path}")
                return None

            # Find the footage file in the AOV folder
            footage_path = None
            try:
                print(f"[DEBUG IDENTIFIER PATH 3D] Scanning AOV folder: {aov_path}")

                for file in os.listdir(aov_path):
                    file_path = aov_path + '/' + file
                    if os.path.isfile(file_path):
                        # Check for image sequence or movie files
                        ext = os.path.splitext(file)[1].lower()
                        if ext in ['.exr', '.jpg', '.png', '.tiff', '.tif', '.mov', '.mp4', '.avi']:
                            footage_path = file_path
                            print(f"[DEBUG IDENTIFIER PATH 3D] Found footage: {footage_path}")
                            break

            except Exception as e:
                print(f"[DEBUG IDENTIFIER PATH 3D] Error finding footage file: {str(e)}")
                import traceback
                print(f"[DEBUG IDENTIFIER PATH 3D] Traceback: {traceback.format_exc()}")
                return None

            if not footage_path:
                print(f"[DEBUG IDENTIFIER PATH 3D] No footage file found in AOV folder")
                return None

            print(f"[DEBUG IDENTIFIER PATH 3D] Final footage path: {footage_path}")
            return footage_path

        except Exception as e:
            import traceback
            print(f"[DEBUG IDENTIFIER PATH 3D] Exception: {str(e)}")
            print(f"[DEBUG IDENTIFIER PATH 3D] Traceback: {traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def showIdentifierSelectionDialog(self, footage_items, available_identifiers, all_shot_identifiers=None,
                                      common_identifiers=None, identifier_availability=None, render_type='2d'):
        """Show identifier selection dialog for changing 2D or 3D renders to a different identifier
        (always latest version)

        Args:
            footage_items: List of tree widget items
            available_identifiers: Set of identifier display strings
                (with prefixes like "[2D] ", "[3D] " or "[PB] ")
            all_shot_identifiers: Dict of shot -> list of (identifier, folder_type) tuples
            common_identifiers: Set of clean identifier names that exist in ALL shots
            identifier_availability: Dict of prefixed identifier ->
                {'shots': set, 'folder_type': str, 'clean_name': str}
            render_type: '2d' or '3d' - specifies the type of renders
        """
        try:
            # Get all unique shots and current identifiers
            shots = set()
            current_identifiers = set()
            for item in footage_items:
                shot = self.tracker.getShotNameFromItem(item)
                if shot:
                    shots.add(shot)
                identifier = item.data(0, Qt.UserRole).get('identifier', '')
                current_identifiers.add(identifier)

            # Build lookup for prefixed identifier -> folder_type
            identifier_to_folder = {}
            if all_shot_identifiers:
                for shot_tuples in all_shot_identifiers.values():
                    for ident, folder_type in shot_tuples:
                        if folder_type == 'Playblasts':
                            prefixed = f"[PB] {ident}"
                        elif folder_type == '2dRender':
                            prefixed = f"[2D] {ident}"
                        elif folder_type == '3dRender':
                            prefixed = f"[3D] {ident}"
                        else:
                            prefixed = ident
                        identifier_to_folder[prefixed] = (ident, folder_type)

            # Create dialog
            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            render_type_label = "3D" if render_type == '3d' else "2D"
            if len(shots) == 1:
                dlg.setWindowTitle(f"Change {render_type_label} Identifier - {list(shots)[0]}")
            else:
                dlg.setWindowTitle(f"Change {render_type_label} Identifier - {len(shots)} shots")
            dlg.resize(500, 450)

            layout = QVBoxLayout()
            dlg.setLayout(layout)

            # Header
            header_label = QLabel(f"<h3>Select {render_type_label} Identifier</h3>")
            layout.addWidget(header_label)

            # Info about shots and identifiers
            if len(shots) == 1:
                shot_text = f"Shot: {list(shots)[0]}"
            else:
                shot_text = f"Shots: {len(shots)} different shots"

            if len(current_identifiers) == 1:
                id_text = f"Current identifier: <b>{list(current_identifiers)[0]}</b>"
            else:
                id_text = f"Current identifiers: {len(current_identifiers)} different"

            info_label = QLabel(f"{shot_text}<br>{id_text}")
            layout.addWidget(info_label)

            layout.addSpacing(5)

            # Add legend for multi-shot selection
            if len(shots) > 1:
                legend = QLabel("<i>Grayed out items are not available in all shots</i>")
                legend.setStyleSheet("color: gray;")
                layout.addWidget(legend)

            layout.addSpacing(5)

            # Identifier list
            list_label = QLabel("Available identifiers:")
            layout.addWidget(list_label)

            identifier_list = QListWidget()
            identifier_list.setSelectionMode(QAbstractItemView.SingleSelection)

            # Separate common and non-common identifiers for sorting
            common_items = []
            non_common_items = []

            for identifier in available_identifiers:
                # Check if this is the current identifier (strip prefix for comparison)
                clean_identifier = identifier
                if identifier.startswith('[PB] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[2D] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[3D] '):
                    clean_identifier = identifier[5:]

                # For multi-shot: check if common to all shots
                is_common = True
                if len(shots) > 1 and common_identifiers is not None:
                    is_common = clean_identifier in common_identifiers

                # Also check if it's the current identifier (always common)
                is_current = clean_identifier in current_identifiers and len(current_identifiers) == 1

                if is_common or is_current:
                    common_items.append(identifier)
                else:
                    non_common_items.append(identifier)

            # Sort and add common items first, then non-common
            for identifier in sorted(common_items):
                item = QListWidgetItem(identifier)
                clean_identifier = identifier
                if identifier.startswith('[PB] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[2D] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[3D] '):
                    clean_identifier = identifier[5:]

                # Gray out current identifier
                if clean_identifier in current_identifiers and len(current_identifiers) == 1:
                    item.setBackground(QColor(200, 200, 200))
                    item.setFlags(Qt.NoItemFlags)

                identifier_list.addItem(item)

            # Add separator if there are both common and non-common items
            if common_items and non_common_items:
                separator_item = QListWidgetItem("---")
                separator_item.setFlags(Qt.NoItemFlags)
                separator_item.setForeground(QColor(200, 200, 200))
                identifier_list.addItem(separator_item)

            # Sort and add non-common items at the bottom
            for identifier in sorted(non_common_items):
                item = QListWidgetItem(identifier)
                clean_identifier = identifier
                if identifier.startswith('[PB] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[2D] '):
                    clean_identifier = identifier[5:]
                elif identifier.startswith('[3D] '):
                    clean_identifier = identifier[5:]

                # Change text color to desaturated red, keep default background
                item.setForeground(QColor(180, 120, 120))

                # Add tooltip showing which shots have this identifier
                if identifier_availability and identifier in identifier_availability:
                    avail_shots = identifier_availability[identifier]['shots']
                    shot_count = len(avail_shots)
                    total_count = len(shots)
                    item.setToolTip(f"Available in {shot_count} of {total_count} shots")
                    # Optionally append count to the item text
                    item.setText(f"{identifier} ({shot_count}/{total_count})")

                # Make non-common items unselectable
                item.setFlags(Qt.NoItemFlags)

                identifier_list.addItem(item)

            layout.addWidget(identifier_list)

            layout.addSpacing(10)

            # Buttons
            button_layout = QHBoxLayout()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(dlg.reject)
            button_layout.addWidget(cancel_btn)

            change_btn = QPushButton("Change Identifier")
            change_btn.setDefault(True)
            change_btn.clicked.connect(dlg.accept)
            button_layout.addWidget(change_btn)

            layout.addLayout(button_layout)

            # Show dialog
            if dlg.exec_() != QDialog.Accepted:
                return

            # Get selected identifier
            selected_items = identifier_list.selectedItems()
            if not selected_items:
                return

            selected_text = selected_items[0].text()

            # Strip count suffix if present (e.g., "[2D] LowRes (2/3)" -> "[2D] LowRes")
            if ' (' in selected_text and selected_text.count(' (') == 1:
                selected_text = selected_text.split(' (')[0]

            # Strip prefix and get folder_type
            if selected_text in identifier_to_folder:
                new_identifier, folder_type = identifier_to_folder[selected_text]
            else:
                # Fallback: strip prefix manually
                if selected_text.startswith('[PB] '):
                    new_identifier = selected_text[5:]
                    folder_type = 'Playblasts'
                elif selected_text.startswith('[2D] '):
                    new_identifier = selected_text[5:]
                    folder_type = '2dRender'
                elif selected_text.startswith('[3D] '):
                    new_identifier = selected_text[5:]
                    folder_type = '3dRender'
                else:
                    new_identifier = selected_text
                    folder_type = None

            # Perform the identifier change with folder_type
            self.changeIdentifier(footage_items, new_identifier, folder_type)

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing identifier selection dialog:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def changeIdentifier(self, footage_items, new_identifier, target_folder_type=None):
        """Change 2D or 3D render footage to use a different identifier (latest version)

        Args:
            footage_items: List of tree widget items
            new_identifier: The identifier name to switch to
            target_folder_type: '2dRender', 'Playblasts', or '3dRender' - specifies which folder to look in
        """
        try:
            print(
                f"[DEBUG IDENTIFIER] Starting changeIdentifier to '{new_identifier}', "
                f"folder_type: {target_folder_type}"
            )

            # Auto-detect render type from first item if not specified
            if target_folder_type is None and footage_items:
                first_item = footage_items[0]
                item_group = first_item.data(0, Qt.UserRole).get('group', '')
                if item_group == '3D Renders':
                    target_folder_type = '3dRender'
                elif item_group == '2D Renders':
                    # Check if it's a playblast or 2d render
                    path = first_item.data(0, Qt.UserRole).get('path', '')
                    if '/playblasts/' in path.lower() or '\\playblasts\\' in path.lower():
                        target_folder_type = 'Playblasts'
                    else:
                        target_folder_type = '2dRender'

            print(f"[DEBUG IDENTIFIER] Detected render type: {target_folder_type}")

            success_count = 0
            failed_count = 0
            failed_items = []

            # Get all unique shots from selected items
            shots = set()
            for item in footage_items:
                shot_name = self.tracker.getShotNameFromItem(item)
                if shot_name:
                    shots.add(shot_name)

            print(f"[DEBUG IDENTIFIER] Shots: {shots}")

            # For multiple footage items, show a bulk confirmation
            if len(footage_items) > 1:
                if len(shots) == 1:
                    shot_text = f"shot {list(shots)[0]}"
                else:
                    shot_text = f"{len(shots)} shots"

                render_type_label = "3D" if target_folder_type == '3dRender' else "2D"
                reply = QMessageBox.question(
                    self.tracker.dlg_footage,
                    f"Change {render_type_label} Identifier - Multiple Footage Items",
                    f"Switch {len(footage_items)} footage item(s) to identifier '{new_identifier}' in {shot_text}?\n\n"
                    f"This will replace each footage with the latest version "
                    f"of {new_identifier} for each shot.\n\n"
                    f"This will replace the footage source in After Effects.",
                    QMessageBox.Yes | QMessageBox.No
                )

                if reply == QMessageBox.No:
                    return

            # Get the hierarchy to find the latest version for the new identifier
            hierarchy = getattr(self.tracker, '_stored_hierarchy', {})
            hierarchy_key = '3D Renders' if target_folder_type == '3dRender' else '2D Renders'
            print(f"[DEBUG IDENTIFIER] Hierarchy keys: {list(hierarchy.keys())}")
            print(f"[DEBUG IDENTIFIER] target_folder_type: {target_folder_type}, hierarchy_key: {hierarchy_key}")
            print(f"[DEBUG IDENTIFIER] '{hierarchy_key}' in hierarchy: {hierarchy_key in hierarchy}")
            if hierarchy_key in hierarchy:
                print(f"[DEBUG IDENTIFIER] {hierarchy_key} shots: {list(hierarchy[hierarchy_key].keys())}")

            for footage_item in footage_items:
                try:
                    # Get shot and current identifier for this item
                    item_shot = self.tracker.getShotNameFromItem(footage_item)
                    current_identifier = footage_item.data(0, Qt.UserRole).get('identifier', '')
                    footage_id = footage_item.data(0, Qt.UserRole).get('id', '')

                    # For 3D renders, extract the AOV from the item text
                    aov = None
                    if target_folder_type == '3dRender':
                        aov = footage_item.text(0)  # AOV is the item text for 3D renders
                        # Strip duplicate suffix like " (1)", " (2)" etc.
                        if ' (' in aov and aov.count(' (') == 1 and aov.endswith(')'):
                            aov = aov.split(' (')[0]

                    print(
                        f"[DEBUG IDENTIFIER] Processing item: {footage_item.text(0)}, Shot: {item_shot}, "
                        f"ID: {footage_id}, Current identifier: '{current_identifier}', AOV: {aov}"
                    )

                    # Skip if already using this identifier
                    if current_identifier == new_identifier:
                        print(f"[DEBUG IDENTIFIER] Skipping - already using this identifier")
                        continue

                    # Find the latest version for the new identifier in the hierarchy
                    latest_version_data = None

                    if hierarchy_key in hierarchy and item_shot in hierarchy[hierarchy_key]:
                        shot_data = hierarchy[hierarchy_key][item_shot]
                        print(f"[DEBUG IDENTIFIER] Shot data keys: {list(shot_data.keys())}")
                        if new_identifier in shot_data:
                            identifier_data = shot_data[new_identifier]
                            id_data_repr = (
                                identifier_data if not isinstance(identifier_data, dict)
                                else f"dict with {len(identifier_data)} keys"
                            )
                            print(
                                f"[DEBUG IDENTIFIER] Identifier data type: {type(identifier_data)}, "
                                f"value: {id_data_repr}"
                            )
                            # Check if identifier_data is a dict with AOV entries
                            if identifier_data and isinstance(identifier_data, dict):
                                # For 3D renders, look for the specific AOV
                                if target_folder_type == '3dRender' and aov:
                                    if aov in identifier_data:
                                        footage_list = identifier_data[aov]
                                        if footage_list:
                                            # Find the latest version
                                            for footage in footage_list:
                                                if footage and footage.get('isLatest', False):
                                                    latest_version_data = footage
                                                    print(f"[DEBUG IDENTIFIER] Found latest version for AOV {aov}!")
                                                    break
                                            if not latest_version_data and footage_list:
                                                latest_version_data = footage_list[0]
                                                print(
                                                    f"[DEBUG IDENTIFIER] Using first footage as fallback for AOV {aov}"
                                                )
                                        else:
                                            print(
                                                f"[DEBUG IDENTIFIER] AOV {aov} exists but footage_list "
                                                f"is empty/None, trying other AOVs..."
                                            )
                                    else:
                                        print(
                                            f"[DEBUG IDENTIFIER] AOV {aov} not found in new identifier "
                                            f"(available: {list(identifier_data.keys())}), trying other AOVs..."
                                        )

                                    # Fallback: use the first available AOV if requested AOV not found or empty
                                    if not latest_version_data:
                                        for aov_key, footage_list in identifier_data.items():
                                            if footage_list:
                                                for footage in footage_list:
                                                    if footage and footage.get('isLatest', False):
                                                        latest_version_data = footage
                                                        print(
                                                            f"[DEBUG IDENTIFIER] Found latest version in "
                                                            f"fallback AOV {aov_key}!"
                                                        )
                                                        break
                                                if not latest_version_data and footage_list:
                                                    latest_version_data = footage_list[0]
                                                    print(
                                                        f"[DEBUG IDENTIFIER] Using first footage from "
                                                        f"fallback AOV {aov_key}"
                                                    )
                                                break
                                else:
                                    # For 2D renders, get the first entry
                                    for aov_key, footage_list in identifier_data.items():
                                        if footage_list:
                                            for footage in footage_list:
                                                if footage and footage.get('isLatest', False):
                                                    latest_version_data = footage
                                                    print(f"[DEBUG IDENTIFIER] Found latest version!")
                                                    break
                                            if not latest_version_data and footage_list:
                                                latest_version_data = footage_list[0]
                                                print(f"[DEBUG IDENTIFIER] Using first footage as fallback")
                                            break
                            else:
                                print(
                                    f"[DEBUG IDENTIFIER] identifier_data is not a dict or is empty: "
                                    f"{type(identifier_data)}"
                                )

                    if not latest_version_data:
                        print(f"[DEBUG IDENTIFIER] No latest version data found in hierarchy for {new_identifier}")
                        # Fall back to scanning the file system
                        if target_folder_type == '3dRender':
                            print(
                                f"[DEBUG IDENTIFIER] Scanning file system for 3D "
                                f"{item_shot}/{new_identifier}/{aov}..."
                            )
                            footage_path = self.getLatestVersionPathFor3DIdentifier(
                                item_shot, new_identifier, aov or 'beauty'
                            )
                            if not footage_path and aov and aov != 'beauty':
                                print(f"[DEBUG IDENTIFIER] AOV {aov} not found, trying beauty...")
                                footage_path = self.getLatestVersionPathFor3DIdentifier(
                                    item_shot, new_identifier, 'beauty'
                                )
                        else:
                            print(
                                f"[DEBUG IDENTIFIER] Scanning file system for 2D {item_shot}/{new_identifier}, "
                                f"target_folder_type: {target_folder_type}..."
                            )
                            footage_path = self.getLatestVersionPathFor2DIdentifier(
                                item_shot, new_identifier, target_folder_type
                            )

                        if footage_path:
                            latest_version_data = {'path': footage_path}
                            print(f"[DEBUG IDENTIFIER] Found footage in file system: {footage_path[:100]}")
                        else:
                            error_detail = f"{new_identifier}"
                            if target_folder_type == '3dRender':
                                error_detail = f"{new_identifier}/{aov or 'beauty'}"
                            print(f"[DEBUG IDENTIFIER] No version found for {error_detail}")
                            failed_count += 1
                            failed_items.append(f"{footage_item.text(0)}: No version found for {error_detail}")
                            continue

                    print(f"[DEBUG IDENTIFIER] Latest version path: {latest_version_data.get('path', 'N/A')[:100]}")
                    print(
                        f"[DEBUG IDENTIFIER] Calling replaceFootage with ID: "
                        f"{footage_item.data(0, Qt.UserRole).get('id')}"
                    )

                    # Replace the footage
                    result = self.tracker.ae_ops.replaceFootage(
                        footage_item.data(0, Qt.UserRole).get('id'),
                        latest_version_data['path']
                    )

                    print(f"[DEBUG IDENTIFIER] Replace result: {result}")

                    if result.get('success'):
                        success_count += 1
                        print(f"[DEBUG IDENTIFIER] SUCCESS!")
                    else:
                        failed_count += 1
                        failed_items.append(f"{footage_item.text(0)}: {result.get('error', 'Unknown error')}")
                        print(f"[DEBUG IDENTIFIER] FAILED: {result.get('error', 'Unknown error')}")

                except Exception as e:
                    import traceback
                    print(f"[DEBUG IDENTIFIER] Exception: {str(e)}")
                    print(f"[DEBUG IDENTIFIER] Traceback: {traceback.format_exc()}")
                    failed_count += 1
                    failed_items.append(f"{footage_item.text(0)}: {str(e)}")

            # Show result summary
            if failed_count > 0:
                error_msg = "\n".join(failed_items[:10])
                if len(failed_items) > 10:
                    error_msg += f"\n... and {len(failed_items) - 10} more"
                self.tracker.showSelectableMessage(
                    f"Change Identifier Complete with Errors",
                    f"Successfully changed: {success_count}\n"
                    f"Failed: {failed_count}\n\n"
                    f"Errors:\n{error_msg}"
                )
            else:
                self.tracker.dlg_footage.statusBar.setText(f"Changed {success_count} item(s) to {new_identifier}")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))

            # Refresh the tree to show changes
            QTimer.singleShot(100, lambda: self.tracker.loadFootageData())

        except Exception as e:
            import traceback
            error_msg = f"Error changing identifier:\n{str(e)}\n\n{traceback.format_exc()}"

            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            dlg.setWindowTitle("Error - Change Identifier Failed")
            dlg.resize(600, 400)

            layout = QVBoxLayout()
            dlg.setLayout(layout)

            label = QLabel("An error occurred while changing the identifier:")
            layout.addWidget(label)

            textEdit = QTextEdit()
            textEdit.setPlainText(error_msg)
            textEdit.setReadOnly(True)
            layout.addWidget(textEdit)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.close)
            layout.addWidget(close_btn)

            dlg.exec_()
