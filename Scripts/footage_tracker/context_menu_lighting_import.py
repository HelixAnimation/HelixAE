# -*- coding: utf-8 -*-
"""
Lighting import context menu methods: import lighting/AOVs, label colors, custom AOV dialog.
"""

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
            script = f"""
            var taskName = '{task_name}';
            var foundColor = 0;

            var render3dFolder = null;
            for (var i = 1; i <= app.project.numItems; i++) {{
                if (app.project.item(i) instanceof FolderItem &&
                    app.project.item(i).name === '3D Renders') {{
                    render3dFolder = app.project.item(i);
                    break;
                }}
            }}

            if (render3dFolder) {{
                for (var i = 1; i <= render3dFolder.numItems; i++) {{
                    var shotFolder = render3dFolder.item(i);
                    if (shotFolder instanceof FolderItem) {{
                        for (var j = 1; j <= shotFolder.numItems; j++) {{
                            var taskFolder = shotFolder.item(j);
                            if (taskFolder instanceof FolderItem && taskFolder.name === taskName) {{
                                for (var k = 1; k <= taskFolder.numItems; k++) {{
                                    var item = taskFolder.item(k);
                                    if (item instanceof FootageItem && item.label > 0) {{
                                        foundColor = item.label;
                                        break;
                                    }}
                                }}
                                break;
                            }}
                        }}
                    }}
                }}
            }}

            foundColor;
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            try:
                existing_color = int(result.strip())
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
            except (ValueError, AttributeError) as e:
                if available_colors:
                    new_color = available_colors.pop(0)
                    task_color_map[task_name] = new_color
                    color_assignments.append(f"{task_name}: New color {new_color} (error: {e})")
                else:
                    task_color_map[task_name] = 1
                    color_assignments.append(f"{task_name}: Default gray (error: {e})")

        print(f"[DEBUG COLOR MAP] Assignments: {color_assignments}")
        print(f"[DEBUG COLOR MAP] Final map: {task_color_map}")

        return task_color_map

    @err_catcher(name=__name__)
    def applyLabelColorsTo3DRenders(self):
        """Apply label colors to all existing 3D Renders footage based on task folders"""
        try:
            script = """
            var render3dFolder = null;
            var taskFootageMap = {};

            for (var i = 1; i <= app.project.numItems; i++) {
                if (app.project.item(i) instanceof FolderItem &&
                    app.project.item(i).name === '3D Renders') {
                    render3dFolder = app.project.item(i);
                    break;
                }
            }

            if (render3dFolder) {
                for (var i = 1; i <= render3dFolder.numItems; i++) {
                    var shotFolder = render3dFolder.item(i);
                    if (shotFolder instanceof FolderItem) {
                        for (var j = 1; j <= shotFolder.numItems; j++) {
                            var taskFolder = shotFolder.item(j);
                            if (taskFolder instanceof FolderItem) {
                                var taskName = taskFolder.name;
                                if (!(taskName in taskFootageMap)) {
                                    taskFootageMap[taskName] = [];
                                }
                                for (var k = 1; k <= taskFolder.numItems; k++) {
                                    var item = taskFolder.item(k);
                                    if (item instanceof FootageItem) {
                                        taskFootageMap[taskName].push(item.id);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            var result = [];
            for (var task in taskFootageMap) {
                result.push(task + '|||' + taskFootageMap[task].join(',,,'));
            }
            result.join(';;;');
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if not result or result.strip() == '':
                self.core.popup("No 3D Renders footage found.")
                return

            task_footage_map = {}
            task_list = result.split(';;;')
            for task_data in task_list:
                parts = task_data.split('|||')
                if len(parts) == 2:
                    task_name = parts[0]
                    footage_ids = parts[1].split(',,,') if parts[1] else []
                    if footage_ids:
                        task_footage_map[task_name] = footage_ids

            if not task_footage_map:
                self.core.popup("No 3D Renders footage found.")
                return

            available_colors = list(range(2, 17))
            task_color_map = {}

            for task_name in task_footage_map.keys():
                check_script = f"""
                var taskName = '{task_name}';
                var existingColor = 0;

                var render3dFolder = null;
                for (var i = 1; i <= app.project.numItems; i++) {{
                    if (app.project.item(i) instanceof FolderItem &&
                        app.project.item(i).name === '3D Renders') {{
                        render3dFolder = app.project.item(i);
                        break;
                    }}
                }}

                if (render3dFolder) {{
                    for (var i = 1; i <= render3dFolder.numItems; i++) {{
                        var shotFolder = render3dFolder.item(i);
                        if (shotFolder instanceof FolderItem) {{
                            for (var j = 1; j <= shotFolder.numItems; j++) {{
                                var taskFolder = shotFolder.item(j);
                                if (taskFolder instanceof FolderItem && taskFolder.name === taskName) {{
                                    for (var k = 1; k <= taskFolder.numItems; k++) {{
                                        var item = taskFolder.item(k);
                                        if (item instanceof FootageItem && item.label > 0) {{
                                            existingColor = item.label;
                                            break;
                                        }}
                                    }}
                                    break;
                                }}
                            }}
                        }}
                    }}
                }}

                existingColor;
                """

                check_result = self.tracker.main.ae_core.executeAppleScript(check_script)
                if isinstance(check_result, bytes):
                    check_result = check_result.decode('utf-8')

                try:
                    existing_color = int(check_result.strip())
                    if existing_color > 0:
                        task_color_map[task_name] = existing_color
                        if existing_color in available_colors:
                            available_colors.remove(existing_color)
                    else:
                        if available_colors:
                            task_color_map[task_name] = available_colors.pop(0)
                        else:
                            task_color_map[task_name] = 1
                except (ValueError, AttributeError):
                    if available_colors:
                        task_color_map[task_name] = available_colors.pop(0)
                    else:
                        task_color_map[task_name] = 1

            total_updated = 0
            for task_name, footage_ids in task_footage_map.items():
                label_color = task_color_map.get(task_name, 1)
                footage_ids_json = str(footage_ids).replace("'", '"')

                apply_script = f"""
                var footageIds = {footage_ids_json};
                var labelColor = {label_color};
                var updatedCount = 0;

                for (var i = 0; i < footageIds.length; i++) {{
                    var footageId = footageIds[i];
                    for (var j = 1; j <= app.project.numItems; j++) {{
                        var item = app.project.item(j);
                        if (item.id == footageId) {{
                            item.label = labelColor;
                            updatedCount++;
                            break;
                        }}
                    }}
                }}

                updatedCount;
                """

                apply_result = self.tracker.main.ae_core.executeAppleScript(apply_script)
                if isinstance(apply_result, bytes):
                    apply_result = apply_result.decode('utf-8')

                try:
                    total_updated += int(apply_result.strip())
                except ValueError:
                    pass

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
            script = """
            var totalComps = 0;
            var totalLayers = 0;
            var updatedLayers = 0;

            for (var i = 1; i <= app.project.numItems; i++) {
                var item = app.project.item(i);
                if (item instanceof CompItem) {
                    totalComps++;

                    for (var j = 1; j <= item.numLayers; j++) {
                        totalLayers++;
                        var layer = item.layer(j);
                        var sourceFootage = layer.source;

                        if (sourceFootage instanceof FootageItem && sourceFootage.label > 0) {
                            var isFrom3DRender = false;
                            var parentFolder = sourceFootage.parentFolder;

                            while (parentFolder) {
                                if (parentFolder.name === '3D Renders') {
                                    isFrom3DRender = true;
                                    break;
                                }
                                parentFolder = parentFolder.parentFolder;
                            }

                            if (isFrom3DRender) {
                                layer.label = sourceFootage.label;

                                if (sourceFootage.parentFolder && sourceFootage.parentFolder.name) {
                                    layer.comment = sourceFootage.parentFolder.name;
                                }

                                updatedLayers++;
                            }
                        }
                    }
                }
            }

            totalComps + '|' + totalLayers + '|' + updatedLayers;
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if '|' in result:
                parts = result.split('|')
                total_comps = int(parts[0]) if parts[0].strip() else 0
                total_layers = int(parts[1]) if parts[1].strip() else 0
                updated_layers = int(parts[2]) if parts[2].strip() else 0

                self.core.popup(
                    f"Updated {updated_layers} layer(s) across {total_comps} composition(s).\n\n"
                    f"Total layers scanned: {total_layers}\n"
                    f"Layers updated: {updated_layers}"
                )
            else:
                self.core.popup(f"Completed. Result: {result}")

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
                script = f"""
                var importFile = new File('{full_file_path}');
                if (importFile.exists) {{
                    var render3dFolder = null, shotFolder = null, taskFolder = null;

                    for (var i = 1; i <= app.project.numItems; i++) {{
                        if (app.project.item(i) instanceof FolderItem &&
                            app.project.item(i).name === '3D Renders') {{
                            render3dFolder = app.project.item(i);
                            break;
                        }}
                    }}
                    if (!render3dFolder) render3dFolder = app.project.items.addFolder('3D Renders');

                    for (var i = 1; i <= render3dFolder.numItems; i++) {{
                        if (render3dFolder.item(i) instanceof FolderItem &&
                            render3dFolder.item(i).name === '{seq_shot}') {{
                            shotFolder = render3dFolder.item(i);
                            break;
                        }}
                    }}
                    if (!shotFolder) shotFolder = render3dFolder.items.addFolder('{seq_shot}');

                    var taskName = '{task_name}';
                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        if (shotFolder.item(i) instanceof FolderItem &&
                            shotFolder.item(i).name === taskName) {{
                            taskFolder = shotFolder.item(i);
                            break;
                        }}
                    }}
                    if (!taskFolder) taskFolder = shotFolder.items.addFolder(taskName);

                    var footageName = '{footage_name}';
                    var existingCount = 0;
                    var finalFootageName = footageName;

                    for (var i = 1; i <= taskFolder.numItems; i++) {{
                        var item = taskFolder.item(i);
                        if (item instanceof FootageItem && item.name === footageName) {{
                            existingCount++;
                            break;
                        }}
                    }}

                    if (existingCount > 0) {{
                        var dupCount = 0;
                        for (var i = 1; i <= taskFolder.numItems; i++) {{
                            var item = taskFolder.item(i);
                            if (item instanceof FootageItem) {{
                                var itemName = item.name;
                                if (itemName === footageName ||
                                    itemName.indexOf(footageName + ' (') === 0) {{
                                    dupCount++;
                                }}
                            }}
                        }}
                        finalFootageName = footageName + ' (' + dupCount + ')';
                    }}

                    var importOptions = new ImportOptions(importFile);
                    if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {{
                        importOptions.importAs = ImportAsType.FOOTAGE;
                        importOptions.sequence = true;
                        var footage = app.project.importFile(importOptions);
                        var labelColor = {label_color};
                        footage.label = labelColor;
                        footage.comment = '{task_name}';
                        footage.parentFolder = taskFolder;
                        footage.name = finalFootageName;
                        'SUCCESS';
                    }} else {{
                        'ERROR: Cannot import as footage';
                    }}
                }} else {{
                    'FILE_NOT_FOUND';
                }}
                """

                result = self.tracker.main.ae_core.executeAppleScript(script)
                if b'SUCCESS' in result:
                    imported_count += 1
                if b'ERROR' in result or b'FILE_NOT_FOUND' in result:
                    self.core.popup(f"Error importing {task_name}/{aov_name}:\n{result}")

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
