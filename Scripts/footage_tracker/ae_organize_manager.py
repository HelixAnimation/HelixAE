# -*- coding: utf-8 -*-
"""
AE Organization Manager Module
Handles organization of After Effects project items into proper folder structures
"""

import os
import re
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class AEOrganizeManager(QObject):
    """Manages organization of After Effects project items"""

    def __init__(self, tracker):
        super(AEOrganizeManager, self).__init__()
        self.tracker = tracker
        self.core = tracker.core

    @err_catcher(name=__name__)
    def organizeFolder(self, folder_name):
        """Main entry point for organizing a folder"""
        try:
            print(f"DEBUG: AEOrganizeManager.organizeFolder called with folder: {folder_name}")

            # Get the current folder tree widget item
            folder_item = self._getFolderTreeItem(folder_name)
            if not folder_item:
                self.core.popup(f"Could not find {folder_name} folder in the tree view.")
                return

            # Analyze items in this folder
            analysis = self.analyzeFolderItems(folder_item, folder_name)

            if not analysis['items']:
                self.core.popup(f"No items found in {folder_name} folder to organize.")
                return

            # Show preview dialog
            self.showOrganizationPreview(folder_name, analysis)

        except Exception as e:
            import traceback
            self.core.popup(f"Error in AE Organization:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def _getFolderTreeItem(self, folder_name):
        """Get the tree widget item for a folder"""
        try:
            root = self.tracker.tw_footage.invisibleRootItem()
            for i in range(root.childCount()):
                child = root.child(i)
                userData = child.data(0, Qt.UserRole)
                if userData and userData.get('group_name') == folder_name:
                    return child
            return None
        except Exception as e:
            print(f"Error finding folder item: {e}")
            return None

    @err_catcher(name=__name__)
    def analyzeFolderItems(self, folder_item, folder_name):
        """Analyze items in the folder and determine organization needed"""
        try:
            analysis = {
                'folder_name': folder_name,
                'items': [],
                'target_structure': {},
                'operations_needed': []
            }

            # Get all children recursively
            self._collectFolderItems(folder_item, analysis)

            return analysis
        except Exception as e:
            print(f"Error analyzing folder: {e}")
            return {'folder_name': folder_name, 'items': [], 'target_structure': {}, 'operations_needed': []}

    @err_catcher(name=__name__)
    def _collectFolderItems(self, parent_item, analysis):
        """Recursively collect all items in a folder"""
        try:
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                userData = child.data(0, Qt.UserRole)

                if userData and userData.get('type') in ['footage', 'comp']:
                    # Debug: Show what userData contains
                    item_id = userData.get('id')
                    self.tracker.debugLog.append(
                        f"DEBUG: Found {userData.get('type')} item with ID: '{item_id}', "
                        f"userData keys: {list(userData.keys())}"
                    )

                    # Get actual AE project item name, not tree widget text
                    actual_name = self._getActualAEItemName(item_id, userData.get('type'))

                    tree_name = child.text(0)
                    if not actual_name:
                        # If we can't get the AE project name, show error instead of using fallback
                        actual_name = f"[ERROR: Cannot get AE project name for ID {item_id}]"
                        self.tracker.debugLog.append(f"DEBUG: Failed to get AE project name for ID {item_id}")

                    item_info = {
                        'name': actual_name,  # Only use actual AE name
                        'tree_name': tree_name,  # Keep tree name for reference
                        'type': userData.get('type'),
                        'id': item_id,
                        'tree_item': child
                    }
                    analysis['items'].append(item_info)

                # Recurse into sub-folders
                if child.childCount() > 0:
                    self._collectFolderItems(child, analysis)
        except Exception as e:
            print(f"Error collecting folder items: {e}")

    @err_catcher(name=__name__)
    def _getActualAEItemName(self, item_id, item_type):
        """Get the actual name of an AE project item by its ID"""
        try:
            if not item_id:
                self.tracker.debugLog.append(f"DEBUG: No item_id provided")
                return None

            self.tracker.debugLog.append(f"DEBUG: Attempting to get AE item name for ID {item_id}")

            # Use JavaScript instead of AppleScript for better compatibility
            script = f"""
            var item = app.project.itemByID({item_id});
            if (item) {{
                item.name;
            }} else {{
                'Item not found';
            }}
            """

            self.tracker.debugLog.append(f"DEBUG: Executing AE script: {script}")

            result = self.tracker.main.ae_core.executeAppleScript(script)
            self.tracker.debugLog.append(f"DEBUG: AE script result for item {item_id}: {result}")
            self.tracker.debugLog.append(f"DEBUG: Result type: {type(result)}, is bytes: {isinstance(result, bytes)}")

            if isinstance(result, bytes):
                result = result.decode('utf-8')
                self.tracker.debugLog.append(f"DEBUG: Decoded result: '{result}'")

            # Clean up the result
            result = str(result).strip()

            # Remove AppleScript wrapping if present
            if result.startswith("'") and result.endswith("'"):
                result = result[1:-1]
                self.tracker.debugLog.append(f"DEBUG: Removed quotes: '{result}'")
            elif result.startswith('"') and result.endswith('"'):
                result = result[1:-1]
                self.tracker.debugLog.append(f"DEBUG: Removed quotes: '{result}'")

            # Check for error responses
            if result and result not in ['Item not found', 'undefined', 'null', '']:
                self.tracker.debugLog.append(f"DEBUG: Successfully got AE item name: '{result}'")
                return result
            else:
                self.tracker.debugLog.append(f"DEBUG: AE script returned error or empty: '{result}'")
                return None

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Exception in _getActualAEItemName: {str(e)}")
            import traceback
            self.tracker.debugLog.append(f"DEBUG: Traceback: {traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def _getTreeItemPath(self, tree_item, folder_name):
        """Extract the folder path from the tree widget hierarchy"""
        try:
            path_parts = []
            current = tree_item
            hierarchy_debug = []

            # Walk up the tree to collect the hierarchy
            while current:
                userData = current.data(0, Qt.UserRole)
                item_text = current.text(0)

                if userData:
                    debug_info = f"Item: '{item_text}', Type: {userData.get('type')}, Level: {userData.get('level')}"
                    if userData.get('type') == 'group':
                        group_name = userData.get('group_name')
                        level = userData.get('level', '')
                        debug_info += f", Group: '{group_name}'"
                        # Always use the actual item text for folder names, ignore group_name
                        if item_text != folder_name:  # Don't include the main folder
                            path_parts.append(item_text)
                    hierarchy_debug.append(debug_info)

                current = current.parent()

            # Debug the hierarchy
            self.tracker.debugLog.append(f"DEBUG: Tree hierarchy for '{tree_item.text(0)}': {hierarchy_debug}")
            self.tracker.debugLog.append(f"DEBUG: Extracted path parts: {path_parts}")

            # Build the path in correct order (reverse since we walked up)
            if not path_parts:
                return f"{folder_name}"

            # Reverse to get correct order (root to leaf)
            path_parts.reverse()

            # Build the final path (exclude root folder from path_parts)
            if path_parts:
                # Filter out the root folder if it's in the path parts
                filtered_parts = [part for part in path_parts if part != f"📁 {folder_name}" and part != folder_name]

                if filtered_parts:
                    final_path = f"{folder_name}/{'/'.join(filtered_parts)}"
                    self.tracker.debugLog.append(f"DEBUG: Final path: '{final_path}'")
                    return final_path
                else:
                    self.tracker.debugLog.append(f"DEBUG: All path parts were filtered, returning main folder")
                    return folder_name
            else:
                self.tracker.debugLog.append(f"DEBUG: No path parts found, returning main folder")
                return folder_name

        except Exception as e:
            self.tracker.debugLog.append(f"DEBUG: Error getting tree item path: {e}")
            import traceback
            self.tracker.debugLog.append(f"DEBUG: Traceback: {traceback.format_exc()}")
            return f"{folder_name}/Misc"

    @err_catcher(name=__name__)
    def showOrganizationPreview(self, folder_name, analysis):
        """Show preview dialog with organization changes"""
        try:
            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowTitle(f"Organize {folder_name} - Preview")
            dlg.resize(600, 500)
            dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

            layout = QVBoxLayout()
            dlg.setLayout(layout)

            # Title
            title_label = QLabel(f"<h3>Organization Preview: {folder_name}</h3>")
            layout.addWidget(title_label)

            # Summary
            summary_label = QLabel(f"Found {len(analysis['items'])} items to organize:")
            layout.addWidget(summary_label)

            # Options section
            options_group = QGroupBox("Options")
            options_layout = QVBoxLayout()

            names_checkbox = QCheckBox("Rename items to target names")
            names_checkbox.setChecked(True)  # Default checked
            names_checkbox.setToolTip("Apply the target naming convention to footage items")
            options_layout.addWidget(names_checkbox)

            labels_checkbox = QCheckBox("Apply label colors based on task")
            labels_checkbox.setChecked(True)  # Default checked
            labels_checkbox.setToolTip("Color-code footage based on their task folder (e.g., Beauty=Red, Fog=Yellow)")
            options_layout.addWidget(labels_checkbox)

            comments_checkbox = QCheckBox("Add task comments")
            comments_checkbox.setChecked(True)  # Default checked
            comments_checkbox.setToolTip("Add task folder name as comment (e.g., 'Lighting_Beauty')")
            options_layout.addWidget(comments_checkbox)

            options_group.setLayout(options_layout)
            layout.addWidget(options_group)

            # Create preview tree
            preview_tree = QTreeWidget()
            preview_tree.setHeaderLabels(["Current Name", "Target Name", "Target Folder"])
            preview_tree.setAlternatingRowColors(False)
            layout.addWidget(preview_tree)

            # Populate preview
            for item in analysis['items']:
                current_name = item['name']  # AE project name
                tree_name = item['tree_name']  # Footage tracker processed name
                tree_widget_item = item['tree_item']  # The actual tree widget item

                # Get the folder path from the tree widget hierarchy
                folder_path = self._getTreeItemPath(tree_widget_item, folder_name)

                parsed = self.parseFootageName(current_name)
                target_path = folder_path  # Use the existing tree hierarchy path
                # Use the new naming convention for 3D renders
                target_name = self.generateFootageTargetName(item, folder_name)

                # Debug output
                self.tracker.debugLog.append(
                    f"DEBUG: AE: '{current_name}' -> FT: '{target_name}'"
                    f" -> Path: '{target_path}' -> type: {parsed.get('type')}"
                )

                tree_item = QTreeWidgetItem()
                tree_item.setText(0, current_name)
                tree_item.setText(1, target_name)
                tree_item.setText(2, target_path)

                # Color code based on naming status
                if parsed['type'] == 'unknown':
                    # Only color red if it's truly unknown (no recognizable pattern)
                    # but current name is already organized differently
                    if current_name != target_name:
                        tree_item.setForeground(0, QColor(255, 0, 0))  # Red text for unknown names
                elif current_name != target_name:
                    tree_item.setForeground(1, QColor(255, 100, 0))  # Orange text for names that need to change
                else:
                    tree_item.setForeground(1, QColor(0, 200, 0))  # Green text for already correct names

                preview_tree.addTopLevelItem(tree_item)

            # Resize columns
            for col in range(3):
                preview_tree.resizeColumnToContents(col)

            # Buttons
            button_layout = QHBoxLayout()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(dlg.reject)
            button_layout.addWidget(cancel_btn)

            button_layout.addStretch()

            organize_btn = QPushButton("Organize Items")
            organize_btn.setStyleSheet("QPushButton { font-weight: bold; }")
            organize_btn.clicked.connect(lambda: self.executeOrganization(
                dlg, folder_name, analysis,
                names_checkbox.isChecked(),
                labels_checkbox.isChecked(),
                comments_checkbox.isChecked()
            ))
            button_layout.addWidget(organize_btn)

            layout.addLayout(button_layout)

            # Show dialog
            result = dlg.exec_()

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing preview:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def _getTaskNameFromTreeItem(self, tree_item):
        """Extract task name from tree widget item hierarchy"""
        parent = tree_item.parent()
        while parent:
            text = parent.text(0).replace('📁 ', '').replace('📂 ', '').strip()
            # Check if this looks like a task folder (has underscores or is named Lighting_*)
            if '_' in text or text.startswith('Lighting'):
                return text
            parent = parent.parent()
        return None

    @err_catcher(name=__name__)
    def _getTaskColorMapForItems(self, items):
        """Get label color mapping for items based on their task folders"""
        task_color_map = {}
        available_colors = list(range(2, 17))  # Start from 2 (Red), up to 16

        # Group items by task folder
        for item in items:
            tree_widget_item = item['tree_item']
            task_name = self._getTaskNameFromTreeItem(tree_widget_item)

            if task_name and task_name not in task_color_map:
                if available_colors:
                    task_color_map[task_name] = available_colors.pop(0)
                else:
                    task_color_map[task_name] = 1  # Default to Gray

        return task_color_map

    @err_catcher(name=__name__)
    def _updateCompLayers(self, items, do_labels, do_comments):
        """Update layers in compositions with label colors and comments

        Returns the number of layers updated.
        """
        import json

        # Create the script with conditional label and comment updates
        label_script_part = """
                        layer.label = layer.source.label;
        """ if do_labels else ""

        comment_script_part = """
                        if (layer.source.parentFolder && layer.source.parentFolder.name) {
                            layer.comment = layer.source.parentFolder.name;
                        }
        """ if do_comments else ""

        script = f"""
        var footageIds = {json.dumps([item['id'] for item in items])};
        var updatedLayers = 0;

        for (var i = 0; i < footageIds.length; i++) {{
            var sourceId = footageIds[i];

            // Find all layers using this footage in all compositions
            for (var c = 1; c <= app.project.numItems; c++) {{
                var compItem = app.project.item(c);
                if (compItem instanceof CompItem) {{
                    for (var l = 1; l <= compItem.numLayers; l++) {{
                        var layer = compItem.layer(l);
                        if (layer.source && layer.source.id == sourceId) {{
                            {label_script_part}
                            {comment_script_part}
                            updatedLayers++;
                        }}
                    }}
                }}
            }}
        }}
        updatedLayers;
        """

        result = self.tracker.main.ae_core.executeAppleScript(script)

        # Try to parse the result as an integer
        try:
            if isinstance(result, bytes):
                result = result.decode('utf-8')
            # Clean up the result
            result = str(result).strip()
            # Remove quotes if present
            if result.startswith("'") and result.endswith("'"):
                result = result[1:-1]
            elif result.startswith('"') and result.endswith('"'):
                result = result[1:-1]

            # Try to convert to int
            return int(result) if result.isdigit() else 0
        except Exception:
            return 0

    @err_catcher(name=__name__)
    def executeOrganization(self, dialog, folder_name, analysis, do_names, do_labels, do_comments):
        """Execute the actual organization

        Args:
            dialog: The preview dialog
            folder_name: Name of folder being organized
            analysis: Analysis dict with items to organize
            do_names: Whether to rename items to target names
            do_labels: Whether to apply label colors based on task
            do_comments: Whether to add task comments
        """
        try:
            self.tracker.debugLog.append("=== STARTING ORGANIZATION EXECUTION ===")
            self.tracker.debugLog.append(f"Found {len(analysis['items'])} items to organize in {folder_name}")

            # Show progress
            progress = QProgressDialog(
                f"Organizing {folder_name}...", "Cancel", 0, len(analysis['items']), self.tracker.dlg_footage
            )
            progress.setWindowTitle("Organizing...")
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            # Track created folders to avoid duplicates
            created_folders = {}

            # Get task color map if labels are enabled
            task_color_map = {}
            if do_labels:
                task_color_map = self._getTaskColorMapForItems(analysis['items'])
                self.tracker.debugLog.append(f"Task color map: {task_color_map}")

            organized_count = 0
            errors = []

            for i, item in enumerate(analysis['items']):
                if progress.wasCanceled():
                    self.tracker.debugLog.append("Organization cancelled by user")
                    break

                progress.setValue(i)
                progress.setLabelText(f"Organizing: {item['name']}")

                try:
                    self.tracker.debugLog.append(
                        f"Processing item {i+1}: {item['name']} (type: {item['type']}, id: {item['id']})"
                    )

                    # Get the folder path from the tree widget hierarchy
                    tree_widget_item = item['tree_item']
                    folder_path = self._getTreeItemPath(tree_widget_item, folder_name)
                    # Generate target name using the new naming convention for 3D renders
                    target_name = self.generateFootageTargetName(item, folder_name)

                    # Get task info for labels and comments
                    task_name = None
                    label_color = None
                    if do_labels or do_comments:
                        task_name = self._getTaskNameFromTreeItem(tree_widget_item)
                        self.tracker.debugLog.append(f"  - Task name: '{task_name}'")

                    if do_labels and task_name:
                        label_color = task_color_map.get(task_name, 1)
                        self.tracker.debugLog.append(f"  - Label color: {label_color}")

                    self.tracker.debugLog.append(f"  - AE Name: '{item['name']}'")
                    self.tracker.debugLog.append(f"  - Target Name: '{target_name}'")
                    self.tracker.debugLog.append(f"  - Target Path: '{folder_path}'")
                    self.tracker.debugLog.append(
                        f"  - Do names: {do_names}, Do labels: {do_labels}, Do comments: {do_comments}"
                    )

                    # Determine if name change is needed
                    name_changes = item['name'] != target_name
                    if name_changes and do_names:
                        self.tracker.debugLog.append(f"  - Name needs to change, proceeding with rename")
                    elif name_changes and not do_names:
                        self.tracker.debugLog.append(
                            "  - Name would change but 'Names' checkbox is unchecked, skipping rename"
                        )
                    else:
                        self.tracker.debugLog.append(f"  - Name already correct")

                    # Create folder structure if not already created
                    if folder_path not in created_folders:
                        self.tracker.debugLog.append(f"  - Creating folder structure for: '{folder_path}'")

                        # Create folder structure in AE project
                        folder_parts = folder_path.split('/')
                        current_path = ""

                        self.tracker.debugLog.append(f"  - Folder parts: {folder_parts}")

                        parent_folder_id = 0  # Start with root folder (0)
                        for j, part in enumerate(folder_parts):
                            if current_path:
                                current_path += '/' + part
                            else:
                                current_path = part

                            if current_path not in created_folders:
                                self.tracker.debugLog.append(
                                    f"    - Creating folder '{part}' with parent ID {parent_folder_id}"
                                )

                                result = self.tracker.ae_ops.createFolderStructure(parent_folder_id, part)
                                self.tracker.debugLog.append(f"    - Folder creation result: {result}")

                                if result.get('success'):
                                    folder_id = result.get('folderId', 0)  # Note: 'folderId' not 'folder_id'
                                    created_folders[current_path] = folder_id
                                    parent_folder_id = folder_id  # Use this folder as parent for next folder
                                    self.tracker.debugLog.append(
                                        f"    - Folder '{part}' created successfully with ID: {folder_id}"
                                        f" (stored in created_folders)"
                                    )
                                else:
                                    # Folder might already exist, try to find it
                                    created_folders[current_path] = 0
                                    parent_folder_id = 0
                                    self.tracker.debugLog.append(
                                        f"    - Folder creation failed or already exists:"
                                        f" {result.get('error', 'Unknown error')}"
                                    )
                            else:
                                # Folder already exists, use its ID as parent for next folder
                                parent_folder_id = created_folders[current_path]
                                self.tracker.debugLog.append(
                                    f"    - Using existing folder '{part}' with ID: {parent_folder_id}"
                                    f" (from created_folders)"
                                )
                    else:
                        self.tracker.debugLog.append(f"  - Folder structure already exists for: '{folder_path}'")

                    # Get the target folder ID (the deepest folder)
                    target_folder_id = created_folders.get(folder_path, 0)
                    self.tracker.debugLog.append(f"  - Target folder ID: {target_folder_id}")
                    self.tracker.debugLog.append(f"  - Created folders dictionary: {created_folders}")
                    self.tracker.debugLog.append(f"  - Looking for path: '{folder_path}'")
                    self.tracker.debugLog.append(
                        f"  - Available keys in created_folders: {list(created_folders.keys())}"
                    )

                    # Only rename if do_names is checked
                    actual_rename_name = target_name if do_names else item['name']

                    # Always move item to target folder (rename only if do_names is checked)
                    if item['type'] == 'footage':
                        action_type = "Moving" if actual_rename_name == item['name'] else "Moving and renaming"
                        self.tracker.debugLog.append(
                            f"  - {action_type} footage item '{item['name']}' (ID: {item['id']})"
                            f" to '{actual_rename_name}' in folder {target_folder_id}"
                        )
                    else:
                        action_type = "Moving" if actual_rename_name == item['name'] else "Moving and renaming"
                        self.tracker.debugLog.append(
                            f"  - {action_type} comp item '{item['name']}' (ID: {item['id']})"
                            f" to '{actual_rename_name}' in folder {target_folder_id}"
                        )

                    # Additional validation before calling duplicate
                    if target_folder_id == 0:
                        self.tracker.debugLog.append(
                            "  - WARNING: Target folder ID is 0 (root folder), this might cause issues"
                        )

                    if item['type'] == 'footage':
                        result = self.tracker.ae_ops.duplicateFootageItem(
                            item['id'], actual_rename_name, target_folder_id
                        )
                    elif item['type'] == 'comp':
                        result = self.tracker.ae_ops.duplicateCompItem(item['id'], actual_rename_name, target_folder_id)

                    self.tracker.debugLog.append(f"  - Organization result: {result}")

                    if result.get('success'):
                        organized_count += 1
                        if actual_rename_name == item['name']:
                            self.tracker.debugLog.append(
                                f"  - Successfully moved item {organized_count} (name unchanged)"
                            )
                        else:
                            self.tracker.debugLog.append(f"  - Successfully moved and renamed item {organized_count}")

                        # Set label color if labels_checkbox is checked
                        if do_labels and label_color:
                            script_add_label = f"""
                            var item = app.project.itemByID({item['id']});
                            if (item) {{
                                item.label = {label_color};
                            }}
                            "SUCCESS";
                            """
                            label_result = self.tracker.main.ae_core.executeAppleScript(script_add_label)
                            self.tracker.debugLog.append(f"  - Label result: {label_result}")

                        # Set comment if comments_checkbox is checked
                        if do_comments and task_name:
                            script_add_comment = f"""
                            var item = app.project.itemByID({item['id']});
                            if (item) {{
                                item.comment = '{task_name}';
                            }}
                            "SUCCESS";
                            """
                            comment_result = self.tracker.main.ae_core.executeAppleScript(script_add_comment)
                            self.tracker.debugLog.append(f"  - Comment result: {comment_result}")
                    else:
                        error_msg = f"Failed to organize {item['name']}: {result.get('error', 'Unknown error')}"
                        errors.append(error_msg)
                        self.tracker.debugLog.append(f"  - ERROR: {error_msg}")

                except Exception as e:
                    error_msg = f"Failed to organize {item['name']}: {str(e)}"
                    errors.append(error_msg)
                    self.tracker.debugLog.append(f"  - EXCEPTION: {error_msg}")
                    import traceback
                    self.tracker.debugLog.append(f"  - Traceback: {traceback.format_exc()}")

            progress.setValue(len(analysis['items']))
            progress.close()

            # Remove all empty folders from the project
            self.tracker.debugLog.append("=== REMOVING EMPTY FOLDERS ===")
            empty_folder_result = self.tracker.ae_ops.removeAllEmptyFolders()
            deleted_count = empty_folder_result.get('deletedCount', 0) if isinstance(empty_folder_result, dict) else 0
            self.tracker.debugLog.append(f"Removed {deleted_count} empty folder(s)")

            # After processing all items, update composition layers if needed
            if do_labels or do_comments:
                self.tracker.debugLog.append("=== UPDATING COMPOSITION LAYERS ===")
                updated_layers = self._updateCompLayers(analysis['items'], do_labels, do_comments)
                self.tracker.debugLog.append(f"Updated {updated_layers} composition layer(s)")

            # Show results
            dialog.close()

            self.tracker.debugLog.append("=== ORGANIZATION COMPLETE ===")
            result_msg = f"Organization Complete!\n\n"
            result_msg += f"Items organized: {organized_count}\n"
            result_msg += f"Empty folders removed: {deleted_count}"

            if errors:
                result_msg += f"\n\nErrors:\n" + "\n".join(errors[:5])
                if len(errors) > 5:
                    result_msg += f"\n... and {len(errors) - 5} more errors"

            self.core.popup(result_msg)

        except Exception as e:
            import traceback
            self.core.popup(f"Error during organization:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def organizeMultipleFolders(self, folder_names):
        """Organize multiple folders in sequence"""
        try:
            self.tracker.debugLog.append(f"=== STARTING MULTI-FOLDER ORGANIZATION ===")
            self.tracker.debugLog.append(f"Folders to organize: {folder_names}")

            # Show confirmation dialog
            reply = QMessageBox.question(
                self.tracker.dlg_footage,
                f"Organize {len(folder_names)} Folders",
                f"This will organize all items in the following folders:\n\n{', '.join(folder_names)}\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

            # Show progress dialog for multi-folder operation
            total_items = 0
            folder_analyses = {}

            # First, analyze all folders to count total items
            for folder_name in folder_names:
                analysis = self.analyzeAEProject(folder_name)
                folder_analyses[folder_name] = analysis
                total_items += len(analysis['items'])

            progress = QProgressDialog(
                f"Organizing {len(folder_names)} folders...", "Cancel", 0, total_items, self.tracker.dlg_footage
            )
            progress.setWindowTitle("Multi-Folder Organization")
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            organized_count = 0
            all_errors = []

            current_progress = 0

            # Organize each folder in sequence
            for i, folder_name in enumerate(folder_names):
                if progress.wasCanceled():
                    break

                progress.setValue(current_progress)
                progress.setLabelText(f"Organizing folder {i+1}/{len(folder_names)}: {folder_name}")

                try:
                    self.tracker.debugLog.append(f"--- Processing folder {i+1}/{len(folder_names)}: {folder_name} ---")

                    analysis = folder_analyses[folder_name]

                    if len(analysis['items']) == 0:
                        self.tracker.debugLog.append(f"  No items to organize in {folder_name}")
                        continue

                    # Execute organization for this folder (reuse existing logic but without progress dialog)
                    folder_organized, folder_errors = self._executeFolderOrganization(
                        folder_name, analysis, current_progress
                    )

                    current_progress += len(analysis['items'])
                    organized_count += folder_organized
                    all_errors.extend(folder_errors)

                    self.tracker.debugLog.append(f"  ✓ Completed organization for {folder_name}")

                except Exception as e:
                    error_msg = f"Error organizing {folder_name}: {str(e)}"
                    all_errors.append(error_msg)
                    self.tracker.debugLog.append(f"  ✗ {error_msg}")
                    import traceback
                    self.tracker.debugLog.append(f"  Traceback: {traceback.format_exc()}")

            progress.setValue(total_items)
            progress.close()

            # Remove all empty folders from the project
            self.tracker.debugLog.append("=== REMOVING EMPTY FOLDERS ===")
            empty_folder_result = self.tracker.ae_ops.removeAllEmptyFolders()
            deleted_count = empty_folder_result.get('deletedCount', 0) if isinstance(empty_folder_result, dict) else 0
            self.tracker.debugLog.append(f"Removed {deleted_count} empty folder(s)")

            # Show results
            result_msg = f"Multi-Folder Organization Complete!\n\n"
            result_msg += f"Folders processed: {len(folder_names)}\n"
            result_msg += f"Items organized: {organized_count}\n"
            result_msg += f"Empty folders removed: {deleted_count}\n"

            if all_errors:
                result_msg += f"\n\nErrors occurred:\n" + "\n".join(all_errors[:3])
                if len(all_errors) > 3:
                    result_msg += f"\n... and {len(all_errors) - 3} more errors"

            self.tracker.debugLog.append("=== MULTI-FOLDER ORGANIZATION COMPLETE ===")

            # Refresh the tree view to show changes
            self.tracker.loadFootageData()

            # Show summary
            QMessageBox.information(self.tracker.dlg_footage, "Organization Complete", result_msg)

        except Exception as e:
            import traceback
            self.core.popup(f"Error during multi-folder organization:\n{str(e)}\n\n{traceback.format_exc()}")

    def _executeFolderOrganization(self, folder_name, analysis, starting_progress):
        """Execute organization for a single folder without progress dialog"""
        try:
            # Track created folders to avoid duplicates
            created_folders = {}
            organized_count = 0
            errors = []

            for i, item in enumerate(analysis['items']):
                # Update parent progress (if available)
                try:
                    self.tracker.dlg_footage.statusBar.setText(
                        f"Organizing {folder_name}: {item['name']} ({i+1}/{len(analysis['items'])})"
                    )
                except Exception:
                    pass  # Status bar might not exist

                try:
                    self.tracker.debugLog.append(
                        f"Processing item {i+1}: {item['name']} (type: {item['type']}, id: {item['id']})"
                    )

                    # Get the folder path from the tree widget hierarchy
                    tree_widget_item = item['tree_item']
                    folder_path = self._getTreeItemPath(tree_widget_item, folder_name)
                    # Generate target name using the new naming convention for 3D renders
                    target_name = self.generateFootageTargetName(item, folder_name)

                    self.tracker.debugLog.append(f"  - AE Name: '{item['name']}'")
                    self.tracker.debugLog.append(f"  - Target Name: '{target_name}'")
                    self.tracker.debugLog.append(f"  - Target Path: '{folder_path}'")

                    # Always organize - move to correct folder and rename if needed
                    if item['name'] != target_name:
                        self.tracker.debugLog.append(f"  - Name needs to change, proceeding with organization")
                    else:
                        self.tracker.debugLog.append(f"  - Name already correct, still moving to proper folder")

                    # Create folder structure if not already created
                    if folder_path not in created_folders:
                        self.tracker.debugLog.append(f"  - Creating folder structure for: '{folder_path}'")

                        # Create folder structure in AE project
                        folder_parts = folder_path.split('/')
                        current_path = ""

                        self.tracker.debugLog.append(f"  - Folder parts: {folder_parts}")

                        parent_folder_id = 0  # Start with root folder (0)
                        for j, part in enumerate(folder_parts):
                            if current_path:
                                current_path += '/' + part
                            else:
                                current_path = part

                            if current_path not in created_folders:
                                self.tracker.debugLog.append(
                                    f"    - Creating folder '{part}' with parent ID {parent_folder_id}"
                                )

                                result = self.tracker.ae_ops.createFolderStructure(parent_folder_id, part)
                                self.tracker.debugLog.append(f"    - Folder creation result: {result}")

                                if result.get('success'):
                                    folder_id = result.get('folderId', 0)  # Note: 'folderId' not 'folder_id'
                                    created_folders[current_path] = folder_id
                                    parent_folder_id = folder_id  # Use this folder as parent for next folder
                                    self.tracker.debugLog.append(
                                        f"    - Folder '{part}' created successfully with ID: {folder_id}"
                                        f" (stored in created_folders)"
                                    )
                                else:
                                    # Folder might already exist, try to find it
                                    created_folders[current_path] = 0
                                    parent_folder_id = 0
                                    self.tracker.debugLog.append(
                                        f"    - Folder creation failed or already exists:"
                                        f" {result.get('error', 'Unknown error')}"
                                    )
                            else:
                                # Folder already exists, use its ID as parent for next folder
                                parent_folder_id = created_folders[current_path]
                                self.tracker.debugLog.append(
                                    f"    - Using existing folder '{part}' with ID: {parent_folder_id}"
                                    f" (from created_folders)"
                                )
                    else:
                        self.tracker.debugLog.append(f"  - Folder structure already exists for: '{folder_path}'")

                    # Get the target folder ID (the deepest folder)
                    target_folder_id = created_folders.get(folder_path, 0)
                    self.tracker.debugLog.append(f"  - Target folder ID: {target_folder_id}")

                    # Always move item to target folder (rename only if needed)
                    if item['type'] == 'footage':
                        action_type = "Moving" if item['name'] == target_name else "Moving and renaming"
                        self.tracker.debugLog.append(
                            f"  - {action_type} footage item '{item['name']}' (ID: {item['id']})"
                            f" to '{target_name}' in folder {target_folder_id}"
                        )

                        result = self.tracker.ae_ops.duplicateFootageItem(item['id'], target_name, target_folder_id)
                    elif item['type'] == 'comp':
                        action_type = "Moving" if item['name'] == target_name else "Moving and renaming"
                        self.tracker.debugLog.append(
                            f"  - {action_type} comp item '{item['name']}' (ID: {item['id']})"
                            f" to '{target_name}' in folder {target_folder_id}"
                        )

                        result = self.tracker.ae_ops.duplicateCompItem(item['id'], target_name, target_folder_id)

                    self.tracker.debugLog.append(f"  - Organization result: {result}")

                    if result.get('success'):
                        organized_count += 1
                        if item['name'] == target_name:
                            self.tracker.debugLog.append(
                                f"  - Successfully moved item {organized_count} (name already correct)"
                            )
                        else:
                            self.tracker.debugLog.append(f"  - Successfully moved and renamed item {organized_count}")
                    else:
                        error_msg = f"Failed to organize {item['name']}: {result.get('error', 'Unknown error')}"
                        errors.append(error_msg)
                        self.tracker.debugLog.append(f"  - ERROR: {error_msg}")

                except Exception as e:
                    error_msg = f"Failed to organize {item['name']}: {str(e)}"
                    errors.append(error_msg)
                    self.tracker.debugLog.append(f"  - EXCEPTION: {error_msg}")
                    import traceback
                    self.tracker.debugLog.append(f"  - Traceback: {traceback.format_exc()}")

            return organized_count, errors

        except Exception as e:
            import traceback
            raise Exception(
                f"Error executing folder organization for {folder_name}: {str(e)}\n\n{traceback.format_exc()}"
            )

    @err_catcher(name=__name__)
    def analyzeAEProject(self, folder_name):
        """Analyze AE project items for organization"""
        analysis = {
            'folder': folder_name,
            'items': []
        }

        try:
            self.tracker.debugLog.append(f"=== ANALYZING FOLDER: {folder_name} ===")

            # Find the root tree widget item for the given folder
            root_item = None

            for i in range(self.tracker.tw_footage.topLevelItemCount()):
                item = self.tracker.tw_footage.topLevelItem(i)
                userData = item.data(0, Qt.UserRole)
                self.tracker.debugLog.append(
                    f"Root item {i}: '{item.text(0)}'"
                    f" - Type: {userData.get('type') if userData else 'None'}"
                    f", Level: {userData.get('level') if userData else 'None'}"
                    f", Group: {userData.get('group_name') if userData else 'None'}"
                )

                if (userData and userData.get('type') == 'group' and
                    userData.get('level') == 'group' and
                    userData.get('group_name') == folder_name):
                    root_item = item
                    self.tracker.debugLog.append(f"  ✓ FOUND matching root item: '{item.text(0)}'")

            if not root_item:
                self.tracker.debugLog.append(f"✗ Could not find root folder item for {folder_name}")
                available = [
                    self.tracker.tw_footage.topLevelItem(i).text(0)
                    for i in range(self.tracker.tw_footage.topLevelItemCount())
                ]
                self.tracker.debugLog.append(f"  Available root folders: {available}")
                return analysis

            # Recursively collect all items under this folder
            def collect_items(item, items_list, depth=0):
                indent = "  " * depth
                userData = item.data(0, Qt.UserRole)
                self.tracker.debugLog.append(
                    f"{indent}Processing item: '{item.text(0)}'"
                    f" - Type: {userData.get('type') if userData else 'None'}"
                )

                if userData and userData.get('type') in ['footage', 'comp']:
                    # Get actual AE item name
                    ae_name = self._getActualAEItemName(userData.get('id'), userData.get('type'))
                    items_list.append({
                        'type': userData.get('type'),
                        'id': userData.get('id'),
                        'name': ae_name,
                        'tree_name': item.text(0),  # Footage tracker processed name
                        'tree_item': item,  # Store the actual tree widget item
                        'user_data': userData
                    })
                    self.tracker.debugLog.append(
                        f"{indent}  ✓ Added {userData.get('type')} item: AE='{ae_name}' FT='{item.text(0)}'"
                    )

                # Recurse into children
                for i in range(item.childCount()):
                    collect_items(item.child(i), items_list, depth + 1)

            # Collect all items
            collect_items(root_item, analysis['items'])
            self.tracker.debugLog.append(f"Found {len(analysis['items'])} items in {folder_name} for organization")

            if len(analysis['items']) == 0:
                self.tracker.debugLog.append(f"⚠ No items found to organize in {folder_name}!")
                # Check if there are any child items at all
                if root_item.childCount() > 0:
                    self.tracker.debugLog.append(
                        f"  But root item has {root_item.childCount()} children, checking types..."
                    )
                    for i in range(root_item.childCount()):
                        child = root_item.child(i)
                        child_data = child.data(0, Qt.UserRole)
                        self.tracker.debugLog.append(
                            f"    Child {i}: '{child.text(0)}'"
                            f" - Type: {child_data.get('type') if child_data else 'None'}"
                        )

            return analysis

        except Exception as e:
            import traceback
            self.tracker.debugLog.append(f"Error analyzing {folder_name}: {str(e)}")
            self.tracker.debugLog.append(f"Traceback: {traceback.format_exc()}")
            return analysis

    @err_catcher(name=__name__)
    def generateAEFolderStructure(self, analysis):
        """Generate target folder structure for AE project"""
        """Placeholder for folder structure generation"""
        # TODO: Implement folder structure logic based on analysis
        pass

    @err_catcher(name=__name__)
    def createAEFolderHierarchy(self, structure):
        """Create folder hierarchy in AE project"""
        """Placeholder for folder creation using ExtendScript"""
        # TODO: Implement folder creation with ExtendScript
        pass

    @err_catcher(name=__name__)
    def duplicateAndRenameItems(self, items, target_structure):
        """Duplicate and rename items with proper naming conventions"""
        """Placeholder for item duplication and renaming"""
        # TODO: Implement item duplication and renaming logic
        pass

    # Folder-specific organization methods
    @err_catcher(name=__name__)
    def organizeFootageInAE(self, folder_name):
        """Organize footage items in AE project"""
        """Placeholder for footage organization"""
        pass

    @err_catcher(name=__name__)
    def organizeCompsInAE(self, folder_name):
        """Organize composition items in AE project"""
        """Placeholder for composition organization"""
        pass

    # Helper methods for naming convention parsing
    def parseFootageName(self, footage_name):
        """Parse footage name to extract components (seq, shot, task, version, aov)"""
        """
        Expected patterns:
        - 3D renders: SQ01-SH010_Lighting_v0010_Z
        - 2D renders: SQ01-SH010_Comp_v0010
        - Comps: SQ01-SH010_Main_v0028
        - Your format: SQ01-SH010_HighRes_v0028
        - Resources: various patterns
        - External: various patterns
        """
        # More flexible patterns to match your actual naming convention
        # Order matters - check more specific patterns first
        patterns = [
            ('3d_render', r'^([A-Z0-9\-]+)[_-]([A-Za-z0-9_]+)[_-]v(\d+)[_-]([a-z]+)(?:\.[\d\-]+)?\.exr.*$'),
            ('2d_render',
             r'^([A-Z0-9\-]+)[_-]([A-Za-z0-9_]+)[_-]v(\d+)(?:\.[\d\-]+)?\.(?:mov|avi|mp4|exr|png|jpg|tif).*'),
            ('comp', r'^([A-Z0-9\-]+)[_-]([A-Za-z0-9_]+)[_-]v(\d+)(?:\.[\d\-]+)?$'),
        ]

        for pattern_type, pattern in patterns:
            match = re.match(pattern, footage_name)
            if match:
                if pattern_type == '3d_render':
                    seq_shot, task, version, aov = match.groups()
                    # Create clean name without frame range: SQ01-SH010_Lighting_v0007_beauty
                    clean_base = f"{seq_shot}_{task}_v{version.zfill(4)}_{aov}"
                    return {
                        'type': '3d_render',
                        'seq_shot': seq_shot,
                        'task': task,
                        'version': version,
                        'aov': aov,
                        'clean_name': clean_base
                    }
                elif pattern_type == '2d_render':
                    seq_shot, task, version = match.groups()
                    return {
                        'type': '2d_render',
                        'seq_shot': seq_shot,
                        'task': task,
                        'version': version,
                        'clean_name': f"{seq_shot}_{task}_v{version}"
                    }
                elif pattern_type == 'comp':
                    seq_shot, comp_name, version = match.groups()
                    return {
                        'type': 'comp',
                        'seq_shot': seq_shot,
                        'comp_name': comp_name,
                        'version': version,
                        'clean_name': f"{seq_shot}_{comp_name}_v{version}"
                    }

        # If no pattern matches, return original name info
        return {
            'type': 'unknown',
            'original_name': footage_name,
            'clean_name': footage_name
        }

    def generateTargetPath(self, parsed_name, folder_type):
        """Generate target folder path based on parsed name and folder type"""
        if parsed_name['type'] == '3d_render':
            seq_shot = parsed_name['seq_shot']
            task = parsed_name['task']
            version = parsed_name['version']
            aov = parsed_name['aov']

            # Extract seq and shot from seq_shot (e.g., SQ01-SH010 -> SQ01/SH010)
            if '-' in seq_shot:
                seq, shot = seq_shot.split('-', 1)
                return f"{folder_type}/{seq}/{shot}/{task}/v{version.zfill(4)}/{aov}"
            else:
                return f"{folder_type}/{seq_shot}/{task}/v{version.zfill(4)}/{aov}"

        elif parsed_name['type'] == '2d_render':
            seq_shot = parsed_name['seq_shot']
            task = parsed_name['task']
            version = parsed_name['version']

            if '-' in seq_shot:
                seq, shot = seq_shot.split('-', 1)
                return f"{folder_type}/{seq}/{shot}/{task}/v{version.zfill(4)}"
            else:
                return f"{folder_type}/{seq_shot}/{task}/v{version.zfill(4)}"

        elif parsed_name['type'] == 'comp':
            seq_shot = parsed_name['seq_shot']
            comp_name = parsed_name['comp_name']
            version = parsed_name['version']

            # Determine if it's a main comp or precomp based on name
            if any(keyword in comp_name.lower() for keyword in ['main', 'master', 'final']):
                comp_type = 'Main_Comps'
            else:
                comp_type = 'PreComps'

            if '-' in seq_shot:
                seq, shot = seq_shot.split('-', 1)
                return f"{folder_type}/{comp_type}/{seq}/{shot}"
            else:
                return f"{folder_type}/{comp_type}/{seq_shot}"

        # For unknown types or resources
        return f"{folder_type}/Misc"

    def generateFootageTargetName(self, item, folder_name):
        """Generate the target name for footage items based on the new naming convention
        For 3D renders: just the AOV name (e.g., beauty, cryptomatte)
        For other items: use the tree_name as-is

        Note: Task information is now stored in comments instead of name prefixes
        """
        if folder_name != '3D Renders':
            # Not a 3D render, use tree_name as-is
            return item['tree_name']

        # For 3D renders, just use the AOV name (task info is in comments now)
        return item['tree_name']