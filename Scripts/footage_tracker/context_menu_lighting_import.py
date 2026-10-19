# -*- coding: utf-8 -*-
"""
Lighting import context menu methods: import lighting/AOVs, label colors, custom AOV dialog.
"""

import helixae_protocol

import os
import re

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QAbstractItemView, QAction, QApplication, QDialog, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout
)

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuLightingImport:
    """Mixin: lighting import and label color methods"""

    def _executeLightingScript(self, script):
        """Run a protocol script. Returns (data, error)."""
        try:
            response = self.tracker.main.ae_core.executeAppleScript(script)
        except Exception as e:
            return None, "After Effects bridge error: %s" % e
        return helixae_protocol.parse_json_response(response)

    @err_catcher(name=__name__)
    def showUnifiedImportDialog(self):
        """Show the unified import dialog with 3D and 2D tabs"""
        from .import_dialog import UnifiedImportDialog
        dialog = UnifiedImportDialog(self.tracker)
        dialog.showDialog()

    @err_catcher(name=__name__)
    def importCurrentShotLighting(self):
        """Import all lighting passes from current shot (wrapper for folder context menu)"""
        self.importLighting()

    @err_catcher(name=__name__)
    def importLighting(self):
        """Import all lighting passes from current shot using Prism API"""
        try:
            print("[API] ========================================")
            print("[API] Import Lighting - Using Prism API")
            print("[API] ========================================")

            current_file = self.core.getCurrentFileName()
            print(f"[API] Current file: {current_file}")

            shot_entity = self._getCurrentShotEntity()
            if not shot_entity:
                self.core.popup(
                    f"Could not determine current shot.\n\nMake sure the AE project is saved"
                    f" and the shot exists in Prism.\n\nFile:\n{current_file}"
                )
                return

            shot_name = self.core.entities.getShotName(shot_entity)
            print(f"[API] Shot: {shot_name}")

            lighting_tasks = self._getLightingTasksFromAPI(shot_entity)
            print(f"[API] Found {len(lighting_tasks)} lighting task(s) via Prism API")
            for task in lighting_tasks:
                print(f"[API]   - {task}")

            if not lighting_tasks:
                self.core.popup(
                    f"No lighting tasks found for shot: {shot_name}"
                    f"\n\n(Queried from Prism API - no file system scan)"
                )
                return

            all_source_data = []

            for task_name in lighting_tasks:
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True)

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']
                aov_count = len(task_data['aovs'])
                print(f"[API] Task '{task_name}' v{version}: {aov_count} AOV(s)")

                for aov_name, aov_info in task_data['aovs'].items():
                    filepaths = aov_info['files']
                    if not filepaths:
                        continue

                    file_count = len(filepaths)
                    print(f"[API]   - {aov_name}: {file_count} files from API")

                    all_source_data.append((
                        filepaths[0],
                        0,
                        file_count - 1,
                        task_name,
                        aov_name,
                        version
                    ))

            if not all_source_data:
                self.core.popup("No AOVs found in lighting tasks.\n\n(Queried from Prism API)")
                return

            print(f"[API] Total AOVs to import: {len(all_source_data)}")
            print("[API] Calling importLightingSequences...")

            self.importLightingSequences(all_source_data)

            print("[API] Import complete!")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.core.popup(f"Error importing lighting:\n{str(e)}")

    @err_catcher(name=__name__)
    def _getTaskColorMap(self, source_data):
        """Get label color mapping for tasks - auto-assigns colors to new tasks"""
        unique_tasks = list(set(item[3] for item in source_data))

        available_colors = list(range(2, 17))

        task_color_map = {}
        color_assignments = []

        for task_name in unique_tasks:
            existing_color = 0

            try:
                script = helixae_protocol.build_find_task_folder_label(task_name)
            except (TypeError, ValueError) as e:
                print(f"[DEBUG COLOR MAP] Skipping invalid task name {task_name!r}: {e}")
                continue

            data, error = self._executeLightingScript(script)
            if error:
                existing_color = 0
            elif data.get("result"):
                try:
                    existing_color = int(data.get("label") or 0)
                except (TypeError, ValueError):
                    existing_color = 0

            if existing_color > 0:
                task_color_map[task_name] = existing_color
                color_assignments.append(f"{task_name}: Existing color {existing_color}")
                if existing_color in available_colors:
                    available_colors.remove(existing_color)
            else:
                if available_colors:
                    new_color = available_colors.pop(0)
                    task_color_map[task_name] = new_color
                    color_assignments.append(f"{task_name}: New color {new_color}")
                else:
                    task_color_map[task_name] = 1
                    color_assignments.append(f"{task_name}: Default gray (no colors left)")

        print(f"[DEBUG COLOR MAP] Assignments: {color_assignments}")
        print(f"[DEBUG COLOR MAP] Final map: {task_color_map}")

        return task_color_map

    @err_catcher(name=__name__)
    def applyLabelColorsTo3DRenders(self):
        """Apply label colors to all existing 3D Renders footage based on task folders"""
        try:
            data, error = self._executeLightingScript(
                helixae_protocol.build_list_task_folder_footage())
            if error:
                self.core.popup("Could not read 3D Renders footage:\n%s" % error)
                return
            if not data.get("result"):
                self.core.popup("Could not read 3D Renders footage from After Effects.")
                return

            task_footage_map = {}
            for task in (data.get("tasks") or []):
                if isinstance(task, dict) and task.get("name") and task.get("itemIds"):
                    task_footage_map.setdefault(str(task["name"]), []).extend(task["itemIds"])

            if not task_footage_map:
                self.core.popup("No 3D Renders footage found.")
                return

            available_colors = list(range(2, 17))
            task_color_map = {}

            for task_name in task_footage_map.keys():
                check_data, check_error = self._executeLightingScript(
                    helixae_protocol.build_find_task_folder_label(task_name))
                existing_color = 0
                if not check_error and check_data.get("result"):
                    try:
                        existing_color = int(check_data.get("label") or 0)
                    except (TypeError, ValueError):
                        existing_color = 0

                if existing_color > 0:
                    task_color_map[task_name] = existing_color
                    if existing_color in available_colors:
                        available_colors.remove(existing_color)
                else:
                    if available_colors:
                        task_color_map[task_name] = available_colors.pop(0)
                    else:
                        task_color_map[task_name] = 1

            total_updated = 0
            for task_name, footage_ids in task_footage_map.items():
                label_color = task_color_map.get(task_name, 1)

                try:
                    apply_script = helixae_protocol.build_set_item_labels(footage_ids, label_color)
                except (TypeError, ValueError) as e:
                    print(f"[LABEL COLORS] Invalid ids for task {task_name!r}: {e}")
                    continue

                apply_data, apply_error = self._executeLightingScript(apply_script)
                if apply_error or not apply_data.get("result"):
                    print(f"[LABEL COLORS] Could not apply colors for task {task_name!r}: "
                          f"{apply_error or apply_data.get('details')}")
                    continue
                total_updated += int(apply_data.get("updatedCount") or 0)

            self.core.popup(
                f"Applied label colors to {total_updated} footage item(s) "
                f"across {len(task_footage_map)} task(s)."
            )
            self.tracker.loadFootageData()

        except Exception as e:
            import traceback
            self.core.popup(f"Error applying label colors:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def applyLabelColorsToAllCompLayers(self):
        """Update label colors on layers in all compositions to match their source footage"""
        try:
            data, error = self._executeLightingScript(
                helixae_protocol.build_update_layers_from_source())
            if error:
                self.core.popup("Error updating layer colors:\n%s" % error)
                return
            if not data.get("result"):
                reason = data.get("reason") or data.get("details") or ""
                self.core.popup("Could not update layer colors.\n%s" % reason)
                return

            total_comps = int(data.get("totalComps") or 0)
            total_layers = int(data.get("totalLayers") or 0)
            updated_layers = int(data.get("updatedLayers") or 0)

            self.core.popup(
                f"Updated {updated_layers} layer(s) across {total_comps} composition(s).\n\n"
                f"Total layers scanned: {total_layers}\n"
                f"Layers updated: {updated_layers}"
            )

        except Exception as e:
            import traceback
            self.core.popup(f"Error updating layer colors:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def importLightingSequences(self, source_data):
        """Import lighting sequences into AE with proper Prism folder structure"""
        try:
            imported_count = 0

            task_color_map = self._getTaskColorMap(source_data)

            for file_path, first_frame, last_frame, task_name, aov_name, version in source_data:
                folder_path = os.path.dirname(file_path)
                if not os.path.exists(folder_path):
                    continue

                path_parts = folder_path.replace("\\", "/").split("/")
                seq_shot = "Unknown-Unknown"

                for i, part in enumerate(path_parts):
                    if part.upper() == "SHOTS" and i + 2 < len(path_parts):
                        seq = path_parts[i + 1]
                        shot = path_parts[i + 2]
                        if re.match(r'SQ\d+', seq) and re.match(r'SH\d+', shot):
                            seq_shot = f"{seq}-{shot}"
                        break

                footage_name = aov_name
                label_color = task_color_map.get(task_name, 1)

                full_file_path = file_path.replace("\\", "/")

                try:
                    script = helixae_protocol.build_import_to_shot_folder(
                        full_file_path,
                        "3D Renders",
                        seq_shot,
                        footage_name,
                        sequence=True,
                        task_folder=task_name,
                        label_color=label_color,
                        comment=task_name,
                    )
                except (TypeError, ValueError) as e:
                    self.core.popup(f"Error importing {task_name}/{aov_name}:\n{e}")
                    continue

                data, error = self._executeLightingScript(script)
                if error:
                    self.core.popup(f"Error importing {task_name}/{aov_name}:\n{error}")
                    continue
                if not data.get("result"):
                    reason = data.get("reason") or data.get("details") or ""
                    if reason == "file_not_found":
                        reason = "The file does not exist in After Effects."
                    elif reason == "cannot_import":
                        reason = "The file cannot be imported as footage."
                    self.core.popup(f"Error importing {task_name}/{aov_name}:\n{reason}")
                    continue

                imported_count += 1

            msg = f"Imported {imported_count} lighting pass(es)"
            self.core.popup(msg)
            self.tracker.loadFootageData()

        except Exception as e:
            import traceback
            self.core.popup(f"Error importing sequences:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showCustom3DAOVSelectionDialog(self):
        """Show dialog for selecting specific AOVs from all 3D render tasks using Prism API"""
        try:
            print("[API] ========================================")
            print("[API] Custom Import Dialog - Using Prism API")
            print("[API] ========================================")

            current_file = self.core.getCurrentFileName()
            print(f"[API] Current file: {current_file}")

            shot_entity = self._getCurrentShotEntity()
            if not shot_entity:
                self.core.popup(
                    f"Could not determine current shot.\n\nMake sure the AE project is saved"
                    f" and the shot exists in Prism.\n\nFile:\n{current_file}"
                )
                return

            shot_name = self.core.entities.getShotName(shot_entity)
            print(f"[API] Shot: {shot_name}")

            context = shot_entity.copy()
            context["mediaType"] = "3drenders"

            all_tasks = self.core.getTaskNames(
                taskType="3d",
                context=context,
                addDepartments=False
            )

            print(f"[API] Found {len(all_tasks)} 3D task(s) via Prism API")
            for task in all_tasks:
                print(f"[API]   - {task}")

            if not all_tasks:
                self.core.popup(
                    f"No 3D tasks found for shot: {shot_name}"
                    f"\n\n(Queried from Prism API - no file system scan)"
                )
                return

            tasks_and_aovs = {}
            total_aovs = 0

            for task_name in all_tasks:
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True)

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']
                aov_count = len(task_data['aovs'])
                total_aovs += aov_count
                print(f"[API] Task '{task_name}' v{version}: {aov_count} AOV(s)")

                aov_list = []
                for aov_name, aov_info in task_data['aovs'].items():
                    filepaths = aov_info['files']
                    if filepaths:
                        aov_list.append({
                            'name': aov_name,
                            'files': filepaths
                        })
                        print(f"[API]   - {aov_name}: {len(filepaths)} files from API")

                if aov_list:
                    tasks_and_aovs[task_name] = {
                        'version': version,
                        'aovs': aov_list
                    }

            if not tasks_and_aovs:
                self.core.popup(f"No AOVs found for shot: {shot_name}\n\n(Queried from Prism API)")
                return

            print(f"[API] Total: {len(tasks_and_aovs)} tasks, {total_aovs} AOVs loaded from Prism API")
            print("[API] Showing selection dialog...")

            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowTitle("Import 3D Passes - Custom (Prism API)")
            dlg.resize(600, 500)

            layout = QVBoxLayout()
            label = QLabel("Select AOVs to import:")
            label.setStyleSheet("font-weight: bold; font-size: 12px;")
            layout.addWidget(label)

            api_label = QLabel("🔷 Data source: Prism API (no file system scan)")
            api_label.setStyleSheet("color: #00aaff; font-size: 11px; margin: 2px 0;")
            layout.addWidget(api_label)

            current_shot_label = QLabel(f"Shot: {shot_name}")
            current_shot_label.setStyleSheet("color: #888888; font-style: italic; margin: 5px 0;")
            layout.addWidget(current_shot_label)

            layout.addWidget(QLabel(""))

            aov_table = QTableWidget()
            aov_table.setColumnCount(4)
            aov_table.setHorizontalHeaderLabels(["Task", "AOV", "Version", "Status"])
            aov_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            aov_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
            aov_table.setAlternatingRowColors(False)
            aov_table.verticalHeader().setVisible(False)
            aov_table.horizontalHeader().setStretchLastSection(False)
            aov_table.setColumnWidth(0, 180)
            aov_table.setColumnWidth(1, 150)
            aov_table.setColumnWidth(2, 80)
            aov_table.setColumnWidth(3, 100)
            layout.addWidget(aov_table)

            selection_label = QLabel("0 AOV(s) selected")
            selection_label.setStyleSheet("color: #666; font-style: italic;")
            layout.addWidget(selection_label)

            aov_table.itemSelectionChanged.connect(
                lambda: selection_label.setText(
                    f"{len(aov_table.selectedItems()) // aov_table.columnCount()} AOV(s) selected"
                )
            )

            row = 0
            for task_name, data in sorted(tasks_and_aovs.items()):
                for aov_data in sorted(data['aovs'], key=lambda x: x['name']):
                    aov = aov_data['name']
                    aov_table.insertRow(row)

                    task_item = QTableWidgetItem(task_name)
                    task_item.setFlags(task_item.flags() & ~Qt.ItemIsEditable)
                    aov_table.setItem(row, 0, task_item)

                    aov_item = QTableWidgetItem(aov)
                    aov_item.setFlags(aov_item.flags() & ~Qt.ItemIsEditable)
                    aov_table.setItem(row, 1, aov_item)

                    version_item = QTableWidgetItem(data['version'])
                    version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
                    aov_table.setItem(row, 2, version_item)

                    is_imported = self._isAOVAlreadyImported(task_name, aov)
                    status_item = QTableWidgetItem("✓ Imported" if is_imported else "")
                    status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                    if is_imported:
                        status_item.setForeground(QColor(100, 150, 100))
                    aov_table.setItem(row, 3, status_item)

                    task_item.setData(Qt.UserRole, {
                        'task': task_name,
                        'aov': aov,
                        'version': data['version'],
                        'files': aov_data['files']
                    })

                    tooltip = f"{task_name}/{aov} - v{data['version']}"
                    if is_imported:
                        tooltip += " (Already imported)"
                    aov_table.item(row, 0).setToolTip(tooltip)
                    aov_table.item(row, 1).setToolTip(tooltip)
                    aov_table.item(row, 2).setToolTip(tooltip)

                    row += 1

            button_layout = QHBoxLayout()
            cancel_btn = QPushButton("Cancel")
            import_btn = QPushButton("Import Selected")
            import_btn.setStyleSheet("QPushButton { font-weight: bold; }")

            cancel_btn.clicked.connect(dlg.reject)
            import_btn.clicked.connect(lambda: self.importSelected3DAOVs(dlg, aov_table))

            button_layout.addWidget(cancel_btn)
            button_layout.addStretch()
            button_layout.addWidget(import_btn)
            layout.addLayout(button_layout)

            dlg.setLayout(layout)
            dlg.exec_()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.core.popup(f"Error showing AOV selection dialog:\n{str(e)}")

    @err_catcher(name=__name__)
    def importSelected3DAOVs(self, dialog, aov_table):
        """Import the selected AOVs from the custom dialog using API file data"""
        try:
            selected_rows = set()
            for index in aov_table.selectedIndexes():
                selected_rows.add(index.row())

            if not selected_rows:
                return

            source_data = []

            for row in selected_rows:
                task_item = aov_table.item(row, 0)
                if not task_item:
                    continue

                data = task_item.data(Qt.UserRole)
                task_name = data['task']
                aov_name = data['aov']
                version = data['version']
                files = data['files']

                if files:
                    source_data.append((
                        files[0],
                        0,
                        len(files) - 1,
                        task_name,
                        aov_name,
                        version
                    ))

            dialog.close()

            if source_data:
                self.importLightingSequences(source_data)
            else:
                self.core.popup("No files found to import.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.core.popup(f"Error importing selected AOVs:\n{str(e)}")
