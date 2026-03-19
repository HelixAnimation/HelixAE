# -*- coding: utf-8 -*-
"""
Unified Import Dialog Module
Provides a single table dialog for importing 3D and 2D footage
Uses the same UI pattern as Import Media dialog
"""

import os
import re
import copy
import fnmatch
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher
from .ui_setup import FloatingSearchBar


class UnifiedImportDialog(QDialog):
    """Unified dialog for importing 3D and 2D footage with shot selection"""

    def __init__(self, tracker):
        super(UnifiedImportDialog, self).__init__(tracker.dlg_footage)
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main
        self.plugin = tracker.main  # For compatibility with Import Media pattern

        # Cache of all shot entities from Prism
        self._all_shot_entities = None

        # Storage for dialog data - shots can be multiple
        self.shots = None  # List of shot entities
        self.identifiers = []  # For compatibility

        # Selected footage data - unified list with type info
        self.selected_items = []  # List of dicts with shot, type, task, aov, version, filepaths
        self.all_selected_items = []  # Store all items before filtering

        # Type filters - all checked by default
        self.type_filters = {'3d': True, '2d': True, 'pb': True}

        # Filter bar
        self.filter_bar_widget = None
        self.filter_bar_visible = False

        self._setupUI()
        self._loadData()

    @err_catcher(name=__name__)
    def showDialog(self):
        """Show the dialog"""
        self.exec_()

    def _setupUI(self):
        """Setup the dialog UI - single unified table"""
        self.setWindowTitle("Import Footage")
        self.resize(950, 650)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Top control row
        top_layout = QHBoxLayout()

        # Shot selection
        self.l_shot = QLabel("Shot:")
        top_layout.addWidget(self.l_shot)

        self.l_shotName = QLabel("")
        self.l_shotName.setWordWrap(True)
        self.l_shotName.setMinimumWidth(200)
        top_layout.addWidget(self.l_shotName)

        self.b_shot = QPushButton("Choose...")
        self.b_shot.setStyleSheet("color: rgb(240, 50, 50); border-color: rgb(240, 50, 50);")
        self.b_shot.clicked.connect(self.chooseEntity)
        self.b_shot.setFocusPolicy(Qt.NoFocus)
        top_layout.addWidget(self.b_shot)

        top_layout.addStretch()

        # Import All Lighting button
        self.import_all_lighting_btn = QPushButton("Import All Lighting")
        self.import_all_lighting_btn.clicked.connect(self._importAllLighting)
        self.import_all_lighting_btn.setToolTip("Import all lighting task AOVs from selected shot(s)")
        top_layout.addWidget(self.import_all_lighting_btn)

        layout.addLayout(top_layout)

        # Options row
        options_layout = QHBoxLayout()

        # Type filter checkboxes
        self.chb_filter_3d = QCheckBox("3D")
        self.chb_filter_3d.setChecked(True)
        self.chb_filter_3d.stateChanged.connect(lambda: self._toggleTypeFilter('3d'))
        options_layout.addWidget(self.chb_filter_3d)

        self.chb_filter_2d = QCheckBox("2D")
        self.chb_filter_2d.setChecked(True)
        self.chb_filter_2d.stateChanged.connect(lambda: self._toggleTypeFilter('2d'))
        options_layout.addWidget(self.chb_filter_2d)

        self.chb_filter_pb = QCheckBox("PB")
        self.chb_filter_pb.setChecked(True)
        self.chb_filter_pb.stateChanged.connect(lambda: self._toggleTypeFilter('pb'))
        options_layout.addWidget(self.chb_filter_pb)

        # Separator
        options_layout.addWidget(QWidget())
        options_layout.addStretch()

        # Show/Hide Shot column checkbox
        self.chb_show_shot = QCheckBox("Show Shot Column")
        self.chb_show_shot.setChecked(True)
        self.chb_show_shot.stateChanged.connect(self._toggleShotColumn)
        options_layout.addWidget(self.chb_show_shot)

        layout.addLayout(options_layout)

        # Floating search bar (like footage tracker)
        self.filter_bar_widget = FloatingSearchBar(self, self._applyFilter, self._hideFilterBar)
        self.filter_bar_widget.hide()

        # Add Ctrl+Space shortcut to toggle filter bar
        self.filter_toggle_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self, self._toggleFilterBar)
        self.filter_toggle_shortcut.setEnabled(True)

        # Unified table for both 3D and 2D
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Shot", "Type", "Task/Identifier", "AOV", "Version", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 120)  # Shot
        self.table.setColumnWidth(1, 60)   # Type
        self.table.setColumnWidth(2, 150)  # Task/Identifier
        self.table.setColumnWidth(3, 150)  # AOV
        self.table.setColumnWidth(4, 80)   # Version
        self.table.setColumnWidth(5, 100)  # Status
        layout.addWidget(self.table)

        # Selection counter
        self.selection_label = QLabel("0 AOV(s) selected")
        self.selection_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.selection_label)

        # Update selection counter
        self.table.itemSelectionChanged.connect(self._updateSelectionCount)

        # API Mode indicator
        api_label = QLabel("🔷 Data source: Prism API")
        api_label.setStyleSheet("color: #00aaff; font-size: 11px; margin: 5px 0;")
        layout.addWidget(api_label)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        import_btn = QPushButton("Import Selected")
        import_btn.clicked.connect(self._importSelected)
        import_btn.setStyleSheet("font-weight: bold;")
        button_layout.addWidget(import_btn)

        layout.addLayout(button_layout)

    def _toggleShotColumn(self, state):
        """Show or hide the Shot column"""
        self.table.setColumnHidden(0, state == Qt.Unchecked)

    def _toggleTypeFilter(self, type_key):
        """Toggle type filter (3d, 2d, or pb)"""
        checkbox = getattr(self, f'chb_filter_{type_key}')
        self.type_filters[type_key] = checkbox.isChecked()

        # Only apply filters if we have data loaded
        if self.all_selected_items:
            self._applyFilter()

    def _toggleFilterBar(self):
        """Toggle the floating search bar visibility"""
        if self.filter_bar_visible:
            self._hideFilterBar()
        else:
            self._showFilterBar()

    def _showFilterBar(self):
        """Show the floating search bar"""
        # Position at top-right of the table
        table_rect = self.table.geometry()
        global_pos = self.mapToGlobal(table_rect.topLeft())

        # Position slightly offset from top-right corner
        x = global_pos.x() + table_rect.width() - 320
        y = global_pos.y() + 10

        self.filter_bar_widget.move(x, y)
        self.filter_bar_widget.show()
        self.filter_bar_widget.search_edit.setFocus()
        self.filter_bar_visible = True

    def _hideFilterBar(self):
        """Hide the floating search bar"""
        self.filter_bar_widget.hide()
        self.filter_bar_visible = False

    def _applyFilter(self, search_text=None):
        """Apply search filter to the table"""
        if search_text is None:
            search_text = self.filter_bar_widget.search_edit.text().lower()
        else:
            search_text = search_text.lower()

        # First apply type filters by repopulating the filtered table
        self._applyTypeAndSearchFilters(search_text)

    def _applyTypeAndSearchFilters(self, search_text=""):
        """Apply both type filters and search filter"""
        # Filter all_selected_items based on type checkboxes
        filtered_items = []

        for item in self.all_selected_items:
            item_type = item.get('type', '')

            # Check if this type should be shown
            if item_type == '3d' and not self.type_filters.get('3d', True):
                continue
            if item_type == '2d' and not self.type_filters.get('2d', True):
                continue
            if item_type == 'pb' and not self.type_filters.get('pb', True):
                continue

            # Apply search filter if provided
            if search_text:
                # Search in shot, type, task, aov, version
                shot = item.get('shot', '').lower()
                task = item.get('task', '').lower()
                aov = item.get('aov', '').lower()
                version = item.get('version', '').lower()
                type_display = item.get('type', '').upper()

                searchable_text = f"{shot} {type_display} {task} {aov} {version}"

                # Use fnmatch for wildcard matching
                if not fnmatch.fnmatchcase(searchable_text, f"*{search_text}*"):
                    continue

            filtered_items.append(item)

        # Update selected_items and repopulate table
        self.selected_items = filtered_items
        self._populateTableFromSelectedItems()

    def _populateTableFromSelectedItems(self):
        """Populate the table from selected_items (after filtering)"""
        self.table.setRowCount(0)

        if not self.selected_items:
            return

        row = 0
        for item_data in self.selected_items:
            self.table.insertRow(row)

            # Get values
            shot_name = item_data.get('shot', '')
            item_type = item_data.get('type', '').upper()
            task_name = item_data.get('task', '')
            aov_name = item_data.get('aov', '')
            version = item_data.get('version', '')
            item_type_lower = item_data.get('type', '')

            # Shot column
            shot_item = QTableWidgetItem(shot_name)
            shot_item.setFlags(shot_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, shot_item)

            # Type column
            type_item = QTableWidgetItem(item_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, type_item)

            # Task/Identifier column
            task_item = QTableWidgetItem(task_name)
            task_item.setFlags(task_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, task_item)

            # AOV column
            aov_item = QTableWidgetItem(aov_name)
            aov_item.setFlags(aov_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, aov_item)

            # Version column
            version_item = QTableWidgetItem(version)
            version_item.setFlags(version_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 4, version_item)

            # Status column
            if item_type_lower == '3d':
                footage_name = aov_name
                import_count = self._isFootageImported(task_name, footage_name, "3d", shot_name)
            elif item_type_lower == '2d':
                footage_name = f"[2D] {task_name}"
                import_count = self._isFootageImported(task_name, footage_name, "2d", shot_name)
            else:  # pb
                footage_name = f"[PB] {task_name}"
                import_count = self._isFootageImported(task_name, footage_name, "pb", shot_name)

            status_text = f"✓ {import_count}" if import_count > 0 else ""
            status_item = QTableWidgetItem(status_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if import_count > 0:
                status_item.setForeground(QColor(100, 150, 100))
            self.table.setItem(row, 5, status_item)

            row += 1

    @err_catcher(name=__name__)
    def _loadData(self):
        """Load initial data for the dialog - default to current shot"""
        # Get current shot path
        current_shot_name = self._getCurrentShotPath()

        # If we have a current shot, set it as default
        if current_shot_name:
            shot_entity = self._getShotEntity(current_shot_name)
            if shot_entity:
                self.setShots([shot_entity])

    @err_catcher(name=__name__)
    def setShots(self, shots):
        """Set shots from EntityDlg - like Import Media"""
        if not isinstance(shots, list):
            shots = [shots]

        self.shots = shots

        # Update UI
        shotNames = []
        for shot in self.shots:
            shotName = self.core.entities.getShotName(shot)
            if shotName:
                shotNames.append(shotName)

        shotStr = ", ".join(shotNames)

        # Update shot display
        self.b_shot.setStyleSheet("")  # Remove red styling
        self.l_shotName.setText(shotStr)

        # Populate table with selected shots
        self._populateTable()

    @err_catcher(name=__name__)
    def chooseEntity(self):
        """Open EntityDlg for shot selection"""
        dlg = self._createEntityDlg()
        if dlg.exec_() == QDialog.Accepted:
            # Entity will be set via signal
            pass

    def _createEntityDlg(self):
        """Create EntityDlg for shot selection - like Import Media"""
        from .import_dialog_entitydlg import EntityDlg
        dlg = EntityDlg(self)
        dlg.w_browser.w_entities.getPage("Shots").tw_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        dlg.w_browser.w_entities.tb_entities.removeTab(0)
        dlg.w_browser.w_entities.navigate({"type": "shot"})
        dlg.w_browser.entered(navData={"type": "shot"})
        dlg.entitiesSelected.connect(self.setShots)
        if self.shots:
            dlg.w_browser.w_entities.navigate(self.shots)
        return dlg

    def _getCurrentShotPath(self):
        """Extract current shot from AE project path"""
        try:
            return self.tracker.tree_ops.extractCurrentShotFromProject()
        except Exception:
            return None

    def _getAllShotEntities(self):
        """Get all shot entities from Prism (cached)"""
        if self._all_shot_entities is None:
            try:
                self._all_shot_entities = self.core.entities.getShots() or []

                # Add project context to each shot entity if not present
                try:
                    project_entity = self.core.entities.getProjectEntity()
                    if project_entity:
                        project_name = project_entity.get('name', '')
                        project_code = project_entity.get('code', '')

                        for shot_entity in self._all_shot_entities:
                            if 'project' not in shot_entity:
                                shot_entity['project'] = project_name
                            if 'project_code' not in shot_entity and project_code:
                                shot_entity['project_code'] = project_code
                except Exception as e:
                    pass

            except Exception as e:
                self._all_shot_entities = []
        return self._all_shot_entities

    def _getShotEntity(self, shot_name):
        """Get Prism entity for a shot name by iterating through all shots"""
        try:
            all_shots = self._getAllShotEntities()

            for shot_entity in all_shots:
                entity_shot_name = self.core.entities.getShotName(shot_entity)
                if entity_shot_name == shot_name:
                    return shot_entity

            return None

        except Exception as e:
            return None

    @err_catcher(name=__name__)
    def _populateTable(self):
        """Populate the unified table with 3D and 2D footage from selected shots"""
        self.table.setRowCount(0)
        self.selected_items = []
        self.all_selected_items = []

        if not self.shots:
            self.import_all_lighting_btn.setEnabled(False)
            return

        # Enable Import All Lighting button
        self.import_all_lighting_btn.setEnabled(True)

        # Collect data for all selected shots - 3D, 2D, and Playblasts
        for shot_entity in self.shots:
            shot_name = self.core.entities.getShotName(shot_entity)
            if not shot_name:
                continue

            # Collect 3D footage data
            self._collect3DForShot(shot_entity, shot_name)

            # Collect 2D footage data
            self._collect2DForShot(shot_entity, shot_name)

            # Collect Playblast footage data
            self._collectPlayblastsForShot(shot_entity, shot_name)

        # Store all items and apply filters
        self.all_selected_items = list(self.selected_items)

        # Apply type and search filters
        search_text = self.filter_bar_widget.search_edit.text().lower() if self.filter_bar_widget else ""
        self._applyTypeAndSearchFilters(search_text)

    @err_catcher(name=__name__)
    def _collect3DForShot(self, shot_entity, shot_name):
        """Collect 3D footage data for a single shot"""
        try:
            context = shot_entity.copy()
            context["mediaType"] = "3drenders"

            all_tasks = self.core.getTaskNames(
                taskType="3d",
                context=context,
                addDepartments=False
            )

            if not all_tasks:
                return

            for task_name in sorted(all_tasks):
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True, media_type="3drenders")

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']

                for aov_name, aov_info in sorted(task_data['aovs'].items()):
                    filepaths = aov_info['files']
                    if not filepaths:
                        continue

                    # Store data for import
                    self.selected_items.append({
                        'shot': shot_name,
                        'shot_entity': shot_entity,
                        'type': '3d',
                        'task': task_name,
                        'aov': aov_name,
                        'version': version,
                        'filepaths': filepaths
                    })

        except Exception as e:
            import traceback
            print(f"Error collecting 3D for {shot_name}: {e}")

    @err_catcher(name=__name__)
    def _collect2DForShot(self, shot_entity, shot_name):
        """Collect 2D footage data for a single shot"""
        try:
            context = shot_entity.copy()
            context["mediaType"] = "2drenders"

            all_tasks = self.core.getTaskNames(
                taskType="2d",
                context=context,
                addDepartments=False
            )

            if not all_tasks:
                return

            for task_name in sorted(all_tasks):
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True, media_type="2drenders")

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']

                for aov_name, aov_info in sorted(task_data['aovs'].items()):
                    filepaths = aov_info['files']
                    if not filepaths:
                        continue

                    # Store data for import
                    self.selected_items.append({
                        'shot': shot_name,
                        'shot_entity': shot_entity,
                        'type': '2d',
                        'task': task_name,
                        'aov': aov_name,
                        'version': version,
                        'filepaths': filepaths
                    })

        except Exception as e:
            import traceback
            print(f"Error collecting 2D for {shot_name}: {e}")

    @err_catcher(name=__name__)
    def _collectPlayblastsForShot(self, shot_entity, shot_name):
        """Collect Playblast footage data for a single shot"""
        try:
            context = shot_entity.copy()
            context["mediaType"] = "playblasts"

            all_tasks = self.core.getTaskNames(
                taskType="playblast",
                context=context,
                addDepartments=False
            )

            if not all_tasks:
                return

            for task_name in sorted(all_tasks):
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True, media_type="playblasts")

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']

                for aov_name, aov_info in sorted(task_data['aovs'].items()):
                    filepaths = aov_info['files']
                    if not filepaths:
                        continue

                    # Store data for import
                    self.selected_items.append({
                        'shot': shot_name,
                        'shot_entity': shot_entity,
                        'type': 'pb',
                        'task': task_name,
                        'aov': aov_name,
                        'version': version,
                        'filepaths': filepaths
                    })

        except Exception as e:
            import traceback
            print(f"Error collecting Playblasts for {shot_name}: {e}")

    def _getTaskDataFromAPI(self, shot_entity, task_name, latest_only=True, media_type="3drenders"):
        """
        Get task data (versions, AOVs, files) from Prism API
        Returns: {
            'latest_version': version_string,
            'all_versions': [version_dict, ...],
            'aovs': {aov_name: {'version': version_dict, 'files': [paths]}}
        }
        """
        context = shot_entity.copy()
        context["mediaType"] = media_type
        context["identifier"] = task_name

        # Use getLatestVersionFromIdentifier like Import Media does
        if latest_only:
            version = self.core.mediaProducts.getLatestVersionFromIdentifier(context)
            all_versions = [version] if version else []
        else:
            all_versions = self.core.mediaProducts.getVersionsFromIdentifier(context)

        if not all_versions or not all_versions[0]:
            return None

        if latest_only:
            all_versions.sort(
                key=lambda x: int(
                    x.get('version', '0').replace('v', '').replace('V', '').lstrip('0') or '0'
                ),
                reverse=True
            )
            versions = [all_versions[0]]
        else:
            versions = all_versions

        if not versions or not versions[0]:
            return None

        latest_version = versions[0]
        version_str = latest_version.get("version", "unknown")

        # For 2D renders and Playblasts, the version itself is the AOV (no separate AOV structure)
        if media_type in ["2drenders", "playblasts"]:
            try:
                filepaths = self.core.mediaProducts.getFilesFromContext(latest_version)
            except Exception:
                filepaths = []

            # Filter out metadata/sidecar files - only keep actual footage files
            filepaths = [f for f in filepaths if not f.lower().endswith('.json')]

            if filepaths:
                return {
                    'latest_version': version_str,
                    'all_versions': versions,
                    'aovs': {
                        'main': {
                            'version': latest_version,
                            'files': filepaths
                        }
                    }
                }
            return None

        # For 3D renders, get AOVs from version
        aovs = {}
        try:
            aov_list = self.core.mediaProducts.getAOVsFromVersion(latest_version)
        except Exception as e:
            aov_list = []

        for aov in aov_list:
            aov_name = aov.get("aov", "main")
            try:
                filepaths = self.core.mediaProducts.getFilesFromContext(aov)
            except Exception:
                filepaths = []

            if filepaths:
                aovs[aov_name] = {
                    'version': latest_version,
                    'files': filepaths
                }

        return {
            'latest_version': version_str,
            'all_versions': versions,
            'aovs': aovs
        }

    def _isFootageImported(self, task_name, aov_name, render_type, shot_name=None):
        """Return count of how many times an AOV is already imported in the current project for a specific shot"""
        try:
            # If no shot_name provided, use current project shot
            if shot_name is None:
                shot_name = self.tracker.tree_ops.data_parser.extractCurrentShotFromProject()
                if not shot_name:
                    return 0

            # Build seq_shot from shot_name
            if '-' in shot_name:
                seq_shot = shot_name
            else:
                seq_shot = shot_name

            # Determine folder structure based on render type
            if render_type == "3d":
                folder_name = '3D Renders'
            elif render_type == "pb":
                folder_name = 'Playblasts'
            else:  # 2d
                folder_name = '2D Renders'

            footage_name = aov_name

            # For 2D renders and Playblasts, footage is directly in shot folder
            # For 3D renders, footage is in task folder
            if render_type in ["2d", "pb"]:
                script = f"""
                var renderFolder = null, shotFolder = null;
                var count = 0;

                // Find {folder_name} folder
                for (var i = 1; i <= app.project.numItems; i++) {{
                    if (app.project.item(i) instanceof FolderItem &&
                        app.project.item(i).name === '{folder_name}') {{
                        renderFolder = app.project.item(i);
                        break;
                    }}
                }}

                if (renderFolder) {{
                    // Find shot folder ({seq_shot})
                    for (var i = 1; i <= renderFolder.numItems; i++) {{
                        if (renderFolder.item(i) instanceof FolderItem &&
                            renderFolder.item(i).name === '{seq_shot}') {{
                            shotFolder = renderFolder.item(i);
                            break;
                        }}
                    }}
                }}

                if (shotFolder) {{
                    // Count footage items matching the base name (including numbered duplicates)
                    var baseName = '{footage_name}';
                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        var item = shotFolder.item(i);
                        if (item instanceof FootageItem) {{
                            var itemName = item.name;
                            if (itemName === baseName ||
                                itemName.indexOf(baseName + ' (') === 0) {{
                                count++;
                            }}
                        }}
                    }}
                }}

                count;
                """
            else:  # 3D renders
                script = f"""
                var renderFolder = null, shotFolder = null, taskFolder = null;
                var count = 0;

                // Find {folder_name} folder
                for (var i = 1; i <= app.project.numItems; i++) {{
                    if (app.project.item(i) instanceof FolderItem &&
                        app.project.item(i).name === '{folder_name}') {{
                        renderFolder = app.project.item(i);
                        break;
                    }}
                }}

                if (renderFolder) {{
                    // Find shot folder ({seq_shot})
                    for (var i = 1; i <= renderFolder.numItems; i++) {{
                        if (renderFolder.item(i) instanceof FolderItem &&
                            renderFolder.item(i).name === '{seq_shot}') {{
                            shotFolder = renderFolder.item(i);
                            break;
                        }}
                    }}
                }}

                if (shotFolder) {{
                    // Find task folder ({task_name})
                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        if (shotFolder.item(i) instanceof FolderItem &&
                            shotFolder.item(i).name === '{task_name}') {{
                            taskFolder = shotFolder.item(i);
                            break;
                        }}
                    }}
                }}

                if (taskFolder) {{
                    // Count footage items matching the base name (including numbered duplicates)
                    var baseName = '{footage_name}';
                    for (var i = 1; i <= taskFolder.numItems; i++) {{
                        var item = taskFolder.item(i);
                        if (item instanceof FootageItem) {{
                            var itemName = item.name;
                            if (itemName === baseName ||
                                itemName.indexOf(baseName + ' (') === 0) {{
                                count++;
                            }}
                        }}
                    }}
                }}

                count;
                """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8').strip()
            try:
                return int(result) if result else 0
            except ValueError:
                return 0

        except Exception as e:
            return 0

    def _updateSelectionCount(self):
        """Update the selection count label"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        self.selection_label.setText(f"{len(selected_rows)} AOV(s) selected")

    @err_catcher(name=__name__)
    def _importAllLighting(self):
        """Import all lighting task AOVs from selected shots"""
        if not self.shots:
            self.core.popup("No shots selected.")
            return

        # Import lighting for all selected shots
        for shot_entity in self.shots:
            shot_name = self.core.entities.getShotName(shot_entity)
            if not shot_name:
                continue
            self._importLightingForShot(shot_entity, shot_name)

    @err_catcher(name=__name__)
    def _importLightingForShot(self, shot_entity, shot_name):
        """Import all lighting passes for a specific shot"""
        try:
            context = shot_entity.copy()
            context["mediaType"] = "3drenders"

            all_tasks = self.core.getTaskNames(
                taskType="3d",
                context=context,
                addDepartments=False
            )

            # Filter for lighting tasks only
            lighting_tasks = [t for t in all_tasks if t.lower() in ['lighting', 'light']]

            if not lighting_tasks:
                return

            # Collect all AOVs from lighting tasks
            all_source_data = []

            for task_name in lighting_tasks:
                task_data = self._getTaskDataFromAPI(shot_entity, task_name, latest_only=True, media_type="3drenders")

                if not task_data or not task_data['aovs']:
                    continue

                version = task_data['latest_version']

                for aov_name, aov_info in task_data['aovs'].items():
                    filepaths = aov_info['files']
                    if not filepaths:
                        continue

                    all_source_data.append((
                        filepaths[0],
                        0,
                        len(filepaths) - 1,
                        task_name,
                        aov_name,
                        version
                    ))

            if not all_source_data:
                return

            # Import using the context menu's importLightingSequences method
            from .context_menu import ContextMenu
            menu_handler = ContextMenu(self.tracker)
            menu_handler.importLightingSequences(all_source_data)

        except Exception as e:
            import traceback
            self.core.popup(f"Error importing lighting:\n{str(e)}")

    @err_catcher(name=__name__)
    def _importSelected(self):
        """Import selected items from the table"""
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            self.core.popup("No AOVs selected for import.")
            return

        # Separate 3D, 2D, and Playblast imports
        source_data_3d = []
        source_data_2d = []
        source_data_pb = []

        for row in sorted(selected_rows):
            if row < len(self.selected_items):
                item_data = self.selected_items[row]
                print(
                    f"[DEBUG] Importing item: type={item_data.get('type')},"
                    f" task={item_data.get('task')}, shot={item_data.get('shot')}"
                )
                filepaths = item_data['filepaths']
                if not filepaths:
                    continue

                if item_data['type'] == '3d':
                    source_data_3d.append((
                        filepaths[0],
                        0,
                        len(filepaths) - 1,
                        item_data['task'],
                        item_data['aov'],
                        item_data['version'],
                        item_data['shot']
                    ))
                elif item_data['type'] == '2d':
                    source_data_2d.append({
                        'filepath': filepaths[0],
                        'task': item_data['task'],
                        'version': item_data['version'],
                        'shot': item_data['shot']
                    })
                elif item_data['type'] == 'pb':
                    source_data_pb.append({
                        'filepath': filepaths[0],
                        'task': item_data['task'],
                        'version': item_data['version'],
                        'shot': item_data['shot']
                    })

        print(
            f"[DEBUG] 3D items: {len(source_data_3d)},"
            f" 2D items: {len(source_data_2d)}, PB items: {len(source_data_pb)}"
        )

        # Import 3D footage using importLightingSequences
        imported_3d = 0
        if source_data_3d:
            from .context_menu import ContextMenu
            menu_handler = ContextMenu(self.tracker)
            # Convert to format expected by importLightingSequences
            formatted_3d = [(d[0], d[1], d[2], d[3], d[4], d[5]) for d in source_data_3d]
            menu_handler.importLightingSequences(formatted_3d)
            imported_3d = len(formatted_3d)

        # Import 2D footage using proper 2D structure
        imported_2d = 0
        if source_data_2d:
            print(f"[DEBUG] Calling _import2DSequences with {len(source_data_2d)} items")
            imported_2d = self._import2DSequences(source_data_2d)

        # Import Playblast footage using proper Playblast structure
        imported_pb = 0
        if source_data_pb:
            print(f"[DEBUG] Calling _importPlayblastSequences with {len(source_data_pb)} items")
            imported_pb = self._importPlayblastSequences(source_data_pb)

        total_imported = imported_3d + imported_2d + imported_pb
        print(f"[DEBUG] Total imported: {total_imported} (3D: {imported_3d}, 2D: {imported_2d}, PB: {imported_pb})")
        if total_imported > 0:
            self.core.popup(f"Imported {total_imported} item(s) successfully.")
            self.tracker.loadFootageData()  # Refresh footage tracker
            self.accept()
        else:
            self.core.popup("No items were imported (they may already exist).")

    @err_catcher(name=__name__)
    def _import2DSequences(self, source_data):
        """Import 2D sequences into AE with proper Prism folder structure

        2D Structure: 2D Renders/SQ01-SH010/[2D] LowRes
        Shot folder: SQ01-SH010
        Footage name: [2D] {identifier} (e.g., [2D] LowRes)
        """
        import re
        try:
            imported_count = 0

            print(f"[DEBUG 2D] Processing {len(source_data)} items")

            for item in source_data:
                file_path = item['filepath']
                identifier = item['task']  # For 2D, task is actually the identifier
                shot_name = item['shot']

                print(f"[DEBUG 2D] Importing: shot={shot_name}, identifier={identifier}")
                print(f"[DEBUG 2D] File exists: {os.path.exists(file_path)}")

                if not os.path.exists(file_path):
                    continue

                # Footage name: [2D] {identifier}
                footage_name = f"[2D] {identifier}"

                full_file_path = file_path.replace("\\", "/")
                # Escape backslashes for ExtendScript string
                escaped_path = full_file_path.replace("\\", "\\\\")

                script = f"""
                var importFile = new File('{escaped_path}');
                if (importFile.exists) {{
                    var render2dFolder = null, shotFolder = null;

                    // Find or create "2D Renders" folder
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        if (app.project.item(i) instanceof FolderItem &&
                            app.project.item(i).name === '2D Renders') {{
                            render2dFolder = app.project.item(i);
                            break;
                        }}
                    }}
                    if (!render2dFolder) render2dFolder = app.project.items.addFolder('2D Renders');

                    // Find or create shot folder (e.g., SQ01-SH010)
                    for (var i = 1; i <= render2dFolder.numItems; i++) {{
                        if (render2dFolder.item(i) instanceof FolderItem &&
                            render2dFolder.item(i).name === '{shot_name}') {{
                            shotFolder = render2dFolder.item(i);
                            break;
                        }}
                    }}
                    if (!shotFolder) shotFolder = render2dFolder.items.addFolder('{shot_name}');

                    // Check if footage with this name already exists in shot folder
                    // If it exists, find the next available number for duplicate
                    var baseFootageName = '{footage_name}';
                    var existingCount = 0;
                    var finalFootageName = baseFootageName;

                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        var item = shotFolder.item(i);
                        if (item instanceof FootageItem && item.name === baseFootageName) {{
                            existingCount++;
                            break;
                        }}
                    }}

                    if (existingCount > 0) {{
                        // Find all duplicates to determine next number
                        var dupCount = 0;
                        for (var i = 1; i <= shotFolder.numItems; i++) {{
                            var item = shotFolder.item(i);
                            if (item instanceof FootageItem) {{
                                var itemName = item.name;
                                if (itemName === baseFootageName ||
                                    itemName.indexOf(baseFootageName + ' (') === 0) {{
                                    dupCount++;
                                }}
                            }}
                        }}
                        finalFootageName = baseFootageName + ' (' + dupCount + ')';
                    }}

                    // Import footage (not as sequence for 2D video files)
                    var importOptions = new ImportOptions(importFile);
                    if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {{
                        importOptions.importAs = ImportAsType.FOOTAGE;
                        var footage = app.project.importFile(importOptions);
                        footage.parentFolder = shotFolder;
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
                elif b'ERROR' in result or b'FILE_NOT_FOUND' in result:
                    print(f"Error importing 2D {identifier}: {result}")

            return imported_count

        except Exception as e:
            import traceback
            self.core.popup(f"Error importing 2D sequences:\n{str(e)}\n\n{traceback.format_exc()}")
            return 0

    @err_catcher(name=__name__)
    def _importPlayblastSequences(self, source_data):
        """Import Playblast sequences into AE with proper Prism folder structure

        Playblast Structure: Playblasts/SQ01-SH010/[PB] {identifier}
        Shot folder: SQ01-SH010
        Footage name: [PB] {identifier} (e.g., [PB] Review)
        """
        import re
        try:
            imported_count = 0

            print(f"[DEBUG PB] Processing {len(source_data)} items")

            for item in source_data:
                file_path = item['filepath']
                identifier = item['task']  # For playblasts, task is the identifier
                shot_name = item['shot']

                print(f"[DEBUG PB] Importing: shot={shot_name}, identifier={identifier}")
                print(f"[DEBUG PB] File exists: {os.path.exists(file_path)}")

                if not os.path.exists(file_path):
                    continue

                # Footage name: [PB] {identifier}
                footage_name = f"[PB] {identifier}"

                full_file_path = file_path.replace("\\", "/")
                # Escape backslashes for ExtendScript string
                escaped_path = full_file_path.replace("\\", "\\\\")

                script = f"""
                var importFile = new File('{escaped_path}');
                if (importFile.exists) {{
                    var playblastFolder = null, shotFolder = null;

                    // Find or create "Playblasts" folder
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        if (app.project.item(i) instanceof FolderItem &&
                            app.project.item(i).name === 'Playblasts') {{
                            playblastFolder = app.project.item(i);
                            break;
                        }}
                    }}
                    if (!playblastFolder) playblastFolder = app.project.items.addFolder('Playblasts');

                    // Find or create shot folder (e.g., SQ01-SH010)
                    for (var i = 1; i <= playblastFolder.numItems; i++) {{
                        if (playblastFolder.item(i) instanceof FolderItem &&
                            playblastFolder.item(i).name === '{shot_name}') {{
                            shotFolder = playblastFolder.item(i);
                            break;
                        }}
                    }}
                    if (!shotFolder) shotFolder = playblastFolder.items.addFolder('{shot_name}');

                    // Check if footage with this name already exists in shot folder
                    // If it exists, find the next available number for duplicate
                    var baseFootageName = '{footage_name}';
                    var existingCount = 0;
                    var finalFootageName = baseFootageName;

                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        var item = shotFolder.item(i);
                        if (item instanceof FootageItem && item.name === baseFootageName) {{
                            existingCount++;
                            break;
                        }}
                    }}

                    if (existingCount > 0) {{
                        // Find all duplicates to determine next number
                        var dupCount = 0;
                        for (var i = 1; i <= shotFolder.numItems; i++) {{
                            var item = shotFolder.item(i);
                            if (item instanceof FootageItem) {{
                                var itemName = item.name;
                                if (itemName === baseFootageName ||
                                    itemName.indexOf(baseFootageName + ' (') === 0) {{
                                    dupCount++;
                                }}
                            }}
                        }}
                        finalFootageName = baseFootageName + ' (' + dupCount + ')';
                    }}

                    // Import footage (not as sequence for playblast video files)
                    var importOptions = new ImportOptions(importFile);
                    if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {{
                        importOptions.importAs = ImportAsType.FOOTAGE;
                        var footage = app.project.importFile(importOptions);
                        footage.parentFolder = shotFolder;
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
                elif b'ERROR' in result or b'FILE_NOT_FOUND' in result:
                    print(f"Error importing Playblast {identifier}: {result}")

            return imported_count

        except Exception as e:
            import traceback
            self.core.popup(f"Error importing Playblast sequences:\n{str(e)}\n\n{traceback.format_exc()}")
            return 0
