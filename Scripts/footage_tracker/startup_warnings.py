# -*- coding: utf-8 -*-
"""
Startup Warnings Module
Checks for outdated versions, FPS mismatches, and resolution issues on startup
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class StartupWarnings(QObject):
    """Handles startup warning checks for footage issues"""

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main
        # Cache for ignored items to avoid repeated XMP reads
        self._ignored_items_cache = None
        self._ignored_items_cache_file = None

    @err_catcher(name=__name__)
    def checkFootageIssues(self, hierarchy=None, silent=False, force_refresh=False):
        """
        Show issues from the footage tracker's cached data.
        The footage tracker is the single source of truth for all issues.

        Args:
            hierarchy: Not used - kept for compatibility
            silent: If True, don't show dialogs or popups
            force_refresh: If True, reload footage data from AE
        """
        # Force refresh means reload from AE
        if force_refresh:
            self.tracker.loadFootageData()

        # Get issues from footage tracker (single source of truth)
        cached_items = getattr(self.tracker, '_cached_issue_items', None)
        cached_counts = getattr(self.tracker, '_cached_issue_counts', None)

        if not cached_items or not cached_counts:
            if not silent:
                self.core.popup("No footage data loaded.\n\nPlease load footage data first.")
            return {'outdated': 0, 'fps_mismatch': 0, 'frame_range_mismatch': 0, 'resolution_mismatch': 0, 'total': 0}

        # Convert cached items to the format expected by the dialog
        issues = {
            'outdated': cached_items.get('outdated', []),
            'fps_mismatch': cached_items.get('fps_mismatch', []),
            'frame_range_mismatch': cached_items.get('frame_range_mismatch', []),
            'resolution_mismatch': cached_items.get('resolution_mismatch', []),
            'total_footage': cached_counts.get('total_footage', 0),
            'total_comps': cached_counts.get('total_comps', 0)
        }

        # Get project FPS
        project_fps = 25.0
        try:
            fps_config = self.core.getConfig("globals", "fps", config="project")
            if fps_config:
                project_fps = float(fps_config)
        except Exception:
            pass

        # Show warning dialog if issues found (only if not silent)
        if not silent:
            # Use cached_counts which already excludes bypassed items
            total_issues = (cached_counts.get('outdated', 0) + cached_counts.get('fps_mismatch', 0) +
                          cached_counts.get('frame_range_mismatch', 0) + cached_counts.get('resolution_mismatch', 0))
            if total_issues > 0:
                self._showWarningDialog(issues, project_fps)
            else:
                # Show dialog with no issues but with Reset Ignored button available
                self._showWarningDialog(issues, project_fps, no_issues_mode=True)

        # Return the counts from cached_counts (excludes bypassed items)
        return {
            'outdated': cached_counts.get('outdated', 0),
            'fps_mismatch': cached_counts.get('fps_mismatch', 0),
            'frame_range_mismatch': cached_counts.get('frame_range_mismatch', 0),
            'resolution_mismatch': cached_counts.get('resolution_mismatch', 0),
            'total': issues['total_footage'] + issues['total_comps']
        }

    def _checkFootage(self, footage, project_fps, issues, identifier=None, aov=None):
        """Check a single footage item for issues"""
        issues['total_footage'] += 1

        name = footage.get('name', 'Unknown')
        fps = footage.get('fps', 'N/A')
        is_latest = footage.get('isLatest', True)
        path = footage.get('path', '')
        group = footage.get('group', '')
        hierarchy_type = footage.get('hierarchy_type', 'render')

        # Check for outdated version
        if not is_latest:
            version_info = footage.get('versionInfo', {})
            current = version_info.get('currentVersion', 'v001')
            latest = version_info.get('latestVersion', 'v001')
            issues['outdated'].append({
                'name': name,
                'current': current,
                'latest': latest,
                'path': path,
                'group': group,
                'shot': footage.get('shotName', ''),
                'identifier': identifier or ''
            })

        # Check for FPS mismatch
        try:
            if fps != 'N/A':
                footage_fps = float(fps)
                if abs(footage_fps - project_fps) > 0.01:  # Allow small floating point differences
                    issues['fps_mismatch'].append({
                        'name': f"[{group}] {name}",
                        'footage_fps': footage_fps,
                        'project_fps': project_fps,
                        'path': path,
                        'group': group,
                        'original_name': name,
                        'shot': footage.get('shotName', ''),
                        'identifier': identifier or ''
                    })
        except (ValueError, TypeError):
            pass

        # Check resolution for renders (3D and 2D)
        if hierarchy_type == 'render':
            width = footage.get('width', 0)
            height = footage.get('height', 0)
            start_frame = footage.get('startFrame', 0)
            end_frame = footage.get('endFrame', 0)

            # Convert width and height to integers for comparison
            try:
                width = int(width) if width and width != 'N/A' else 0
                height = int(height) if height and height != 'N/A' else 0
            except (ValueError, TypeError):
                width = 0
                height = 0

            # Get shot name from footage for Kitsu lookup
            shot_name = footage.get('shotName', '')
            kitsu_data = {}

            # Use data_parser's method to extract shot from project file if not in footage
            if not shot_name:
                shot_name = self.tracker.tree_ops.extractCurrentShotFromProject()

            if shot_name and self.tracker.kitsuShotData and shot_name in self.tracker.kitsuShotData:
                kitsu_data = self.tracker.kitsuShotData[shot_name]

            # Check against Kitsu resolution first
            expected_width = kitsu_data.get('width', None)
            expected_height = kitsu_data.get('height', None)

            if expected_width and expected_height and width > 0 and height > 0:
                try:
                    expected_width = int(expected_width)
                    expected_height = int(expected_height)
                    if width != expected_width or height != expected_height:
                        issues['resolution_mismatch'].append({
                            'name': f"[{group}] {name}",
                            'current': f"{width}x{height}",
                            'expected': f"{expected_width}x{expected_height}",
                            'shot': shot_name,
                            'group': group,
                            'original_name': name,
                            'identifier': identifier or ''  # Use the render layer identifier (Lighting_Beauty, etc.)
                        })
                except (ValueError, TypeError):
                    pass
            else:
                # Fallback to common resolutions check
                common_resolutions = [
                    (1920, 1080),   # Full HD
                    (2048, 858),    # 2K Scope
                    (2048, 1152),   # 2K Flat
                    (3840, 2160),   # 4K UHD
                    (4096, 1716),   # 4K Scope
                    (4096, 2304),   # 4K Flat
                    (5120, 2160),   # 5K
                    (8192, 4320),   # 8K
                ]

                current_res = (width, height)

                # Flag if resolution is unusual (not in common resolutions)
                # Only check if we have valid resolution data
                if width > 0 and height > 0 and current_res not in common_resolutions:
                    issues['resolution_mismatch'].append({
                        'name': f"[{group}] {name}",
                        'current': f"{width}x{height}",
                        'expected': "Standard resolution",
                        'shot': shot_name if shot_name else '',
                        'group': group,
                        'original_name': name,
                        'identifier': identifier or ''  # Use the render layer identifier
                    })


    def _checkComp(self, comp_name, comp_data, project_fps, issues):
        """Check a composition for frame range, FPS, and resolution issues"""
        issues['total_comps'] += 1

        # Get comp properties - keys from data_parser.py
        try:
            start_frame = int(comp_data.get('startFrame', 0)) if comp_data.get('startFrame') else 0
            end_frame = int(comp_data.get('endFrame', 0)) if comp_data.get('endFrame') else 0
        except (ValueError, TypeError):
            start_frame = 0
            end_frame = 0

        comp_fps = comp_data.get('frameRate', project_fps)
        try:
            width = int(comp_data.get('width', 0))
            height = int(comp_data.get('height', 0))
        except (ValueError, TypeError):
            width = 0
            height = 0

        # Try to extract shot name from the current AE project file name
        shot_name = None
        kitsu_data = {}

        # Use data_parser's method to extract shot from project file
        shot_name = self.tracker.tree_ops.extractCurrentShotFromProject()

        if shot_name and self.tracker.kitsuShotData and shot_name in self.tracker.kitsuShotData:
            kitsu_data = self.tracker.kitsuShotData[shot_name]

        # Get comp_id for sync operations
        comp_id = comp_data.get('compId', None)

        # Check FPS mismatch
        try:
            comp_fps_float = float(comp_fps)
            if abs(comp_fps_float - project_fps) > 0.01:
                issues['fps_mismatch'].append({
                    'name': f"[Comp] {comp_name}",
                    'footage_fps': comp_fps_float,
                    'project_fps': project_fps,
                    'path': f"Composition: {comp_name}",
                    'comp_id': comp_id,
                    'comp_name': comp_name,
                    'group': 'Comps',
                    'original_name': comp_name
                })
        except (ValueError, TypeError):
            pass

        # Check frame range mismatch with Kitsu - disabled
        if False and kitsu_data and shot_name:
            kitsu_start = kitsu_data.get('start', None)
            kitsu_end = kitsu_data.get('end', None)

            if kitsu_start is not None and kitsu_end is not None:
                try:
                    kitsu_start = int(kitsu_start)
                    kitsu_end = int(kitsu_end)
                    comp_duration = end_frame - start_frame
                    kitsu_duration = kitsu_end - kitsu_start

                    if abs(start_frame - kitsu_start) > 10 or abs(end_frame - kitsu_end) > 10:
                        issues['frame_range_mismatch'].append({
                            'name': f"[Comp] {comp_name}",
                            'comp_range': f"{start_frame}-{end_frame}",
                            'kitsu_range': f"{kitsu_start}-{kitsu_end}",
                            'shot': shot_name,
                            'comp_id': comp_id,
                            'comp_name': comp_name,
                            'kitsu_start': kitsu_start,
                            'kitsu_end': kitsu_end,
                            'kitsu_fps': kitsu_data.get('fps', project_fps),
                            'group': 'Comps',
                            'original_name': comp_name,
                            'identifier': ''  # Comps don't have identifier
                        })
                except (ValueError, TypeError):
                    pass

        # Check resolution - common resolutions for the project
        # You can customize these based on your project standards
        common_resolutions = [
            (1920, 1080),   # Full HD
            (2048, 858),    # 2K Scope
            (2048, 1152),   # 2K Flat
            (3840, 2160),   # 4K UHD
            (4096, 1716),   # 4K Scope
            (4096, 2304),   # 4K Flat
            (5120, 2160),   # 5K
            (8192, 4320),   # 8K
        ]

        # Get expected resolution from Kitsu or project config
        expected_width = kitsu_data.get('width', None)
        expected_height = kitsu_data.get('height', None)

        if expected_width and expected_height:
            try:
                expected_width = int(expected_width)
                expected_height = int(expected_height)
                if width != expected_width or height != expected_height:
                    issues['resolution_mismatch'].append({
                        'name': f"[Comp] {comp_name}",
                        'current': f"{width}x{height}",
                        'expected': f"{expected_width}x{expected_height}",
                        'shot': shot_name,
                        'group': 'Comps',
                        'original_name': comp_name,
                        'comp_id': comp_id
                    })
            except (ValueError, TypeError):
                pass

        # Also check if resolution is unusual (not in common resolutions)
        # Only do this check if we DON'T have Kitsu data
        if not (expected_width and expected_height):
            current_res = (width, height)
            if current_res not in common_resolutions and not (width == 0 or height == 0):
                if width > 0 and height > 0:  # Only flag if resolution is set
                    issues['resolution_mismatch'].append({
                        'name': f"[Comp] {comp_name}",
                        'current': f"{width}x{height}",
                        'expected': "Standard resolution (check Kitsu)",
                        'shot': shot_name if shot_name else "Unknown",
                        'group': 'Comps',
                        'original_name': comp_name,
                        'comp_id': comp_id
                    })

    def _showWarningDialog(self, issues, project_fps, no_issues_mode=False):
        """Show warning dialog with all found issues - with checkboxes for selective updating"""
        parent = getattr(self.tracker, 'dlg_footage', None)
        dlg = QDialog(parent)
        self._current_dialog = dlg  # Store reference for reload after bypass
        dlg.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint | Qt.WindowStaysOnTopHint)
        dlg.setWindowTitle("Footage Issues")
        dlg.resize(1100, 700)
        # Removed hardcoded stylesheet to use global theme

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        dlg.setLayout(layout)

        # Get ignored items to calculate non-ignored counts for button labels
        ignored_items = self._getIgnoredItems()

        # Calculate non-ignored counts for button labels
        non_ignored_outdated = len([
            i for i in issues['outdated']
            if self._generateItemKey(i, 'outdated') not in ignored_items.get('outdated', set())
        ])
        non_ignored_fps = len([
            i for i in issues['fps_mismatch']
            if self._generateItemKey(i, 'fps_mismatch') not in ignored_items.get('fps_mismatch', set())
        ])
        non_ignored_frame_range = len([
            i for i in issues['frame_range_mismatch']
            if self._generateItemKey(i, 'frame_range_mismatch')
            not in ignored_items.get('frame_range_mismatch', set())
        ])
        non_ignored_resolution_comps = len([
            i for i in issues['resolution_mismatch']
            if i.get('group') == 'Comps'
            and self._generateItemKey(i, 'resolution_mismatch')
            not in ignored_items.get('resolution_mismatch', set())
        ])

        # Header with summary and select controls (total includes ALL items, even ignored)
        total_issues = (len(issues['outdated']) + len(issues['fps_mismatch']) +
                       len(issues['frame_range_mismatch']) + len(issues['resolution_mismatch']))

        # Special mode for no issues - show simplified dialog
        if no_issues_mode or total_issues == 0:
            header = QLabel("<h2>✓ No Issues Found</h2>")
            layout.addWidget(header)

            msg = QLabel("All footage and compositions are up to date.")
            layout.addWidget(msg)

            # Close button
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            button_layout.addWidget(close_btn)

            layout.addStretch()
            layout.addLayout(button_layout)
            dlg.exec_()
            return

        header_layout = QHBoxLayout()

        header_text = f"<b>{total_issues}</b> issue{'s' if total_issues != 1 else ''} found"
        header = QLabel(header_text)
        header_layout.addWidget(header)

        header_layout.addStretch()

        # Add checkbox to toggle bypassed rows visibility
        show_bypassed_checkbox = QCheckBox("Show Bypassed")
        show_bypassed_checkbox.setChecked(False)  # Default: hide bypassed rows
        # Use global stylesheet for checkbox
        header_layout.addWidget(show_bypassed_checkbox)

        layout.addLayout(header_layout)

        # Store checkboxes and their associated issue data
        checkbox_data = {}  # {checkbox_obj: {'type': 'outdated', 'data': item_dict}}

        # Load current ignored items
        current_ignored = self._getIgnoredItems()

        # Table widget for all issues - NO checkbox column, right-click instead
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Folder", "Type", "Shot", "Identifier", "Name", "Details"])
        table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        # Enable context menu on table
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        # Add gridlines while using global theme for rest
        table.setStyleSheet("""
            QTableWidget {
                gridline-color: rgb(80, 80, 80);
            }
        """)

        # Auto-resize rows to fit content properly
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Store issue data for each row (instead of checkbox_data)
        row_data = {}  # {row_index: {'type': 'outdated', 'data': item_dict}}

        # Track bypassed rows for show/hide functionality
        bypassed_rows = set()  # Set of row indices that are bypassed

        # Add all issues to table with right-click bypass support
        # Outdated: #FF6464 foreground
        # FPS: #3498DB foreground (blue)
        # Frame Range: #AB26FF foreground (purple)
        # Resolution: #DAA520 foreground (golden)
        # Ignored items: Grayed out with "(Ignored)" suffix
        row = 0
        for item in issues['outdated'][:100]:
            table.insertRow(row)
            item_key = self._generateItemKey(item, 'outdated')
            is_ignored = item_key in current_ignored.get('outdated', set())
            row_data[row] = {'type': 'outdated', 'data': item}

            text_color = "#666666" if is_ignored else "#C8C8C8"
            self._setTextItem(table, row, 0, item.get('group', 'Unknown'), text_color)
            type_color = "#666666" if is_ignored else "#FF6464"
            self._setTypeItem(table, row, 1, "Outdated", type_color, "📦")
            self._setTextItem(table, row, 2, item.get('shot', ''), text_color)
            # For 2D renders, show full name with prefix and suffix in identifier column
            identifier_text = (
                item.get('original_name', item.get('identifier', ''))
                if item.get('group') == '2D Renders'
                else item.get('identifier', '')
            )
            self._setTextItem(table, row, 3, identifier_text, text_color)  # Identifier
            # Name column stays empty for 2D renders
            name_text = '' if item.get('group') == '2D Renders' else item['name']
            self._setTextItem(table, row, 4, name_text + (" (Ignored)" if is_ignored else ""), text_color)
            self._setTextItem(table, row, 5, f"{item['current']} → {item['latest']}", text_color)
            if is_ignored:
                self._setRowGray(table, row)
                bypassed_rows.add(row)
            row += 1

        for item in issues['fps_mismatch'][:100]:
            table.insertRow(row)
            item_key = self._generateItemKey(item, 'fps_mismatch')
            is_ignored = item_key in current_ignored.get('fps_mismatch', set())
            row_data[row] = {'type': 'fps', 'data': item}

            text_color = "#666666" if is_ignored else "#C8C8C8"
            self._setTextItem(table, row, 0, item.get('group', 'Unknown'), text_color)
            type_color = "#666666" if is_ignored else "#3498DB"
            self._setTypeItem(table, row, 1, "FPS", type_color, "🎬")
            self._setTextItem(table, row, 2, item.get('shot', ''), text_color)
            # For 2D renders, show full name with prefix and suffix in identifier column
            identifier_text = (
                item.get('original_name', item.get('identifier', ''))
                if item.get('group') == '2D Renders'
                else item.get('identifier', '')
            )
            self._setTextItem(table, row, 3, identifier_text, text_color)  # Identifier
            # Name column stays empty for 2D renders
            name_text = '' if item.get('group') == '2D Renders' else item.get('original_name', item['name'])
            self._setTextItem(table, row, 4, name_text + (" (Ignored)" if is_ignored else ""), text_color)
            self._setTextItem(table, row, 5, f"{item['footage_fps']} fps → {item['project_fps']} fps", text_color)
            if is_ignored:
                self._setRowGray(table, row)
                bypassed_rows.add(row)
            row += 1

        for item in issues['frame_range_mismatch'][:100]:
            table.insertRow(row)
            item_key = self._generateItemKey(item, 'frame_range_mismatch')
            is_ignored = item_key in current_ignored.get('frame_range_mismatch', set())
            row_data[row] = {'type': 'frame_range', 'data': item}

            print(f"[DEBUG TABLE] frame_range_mismatch item:")
            print(f"  item = {item}")
            print(f"  item_key = {item_key}")
            print(f"  is_ignored = {is_ignored}")
            print(f"  current_ignored['frame_range_mismatch'] = {current_ignored.get('frame_range_mismatch', set())}")

            text_color = "#666666" if is_ignored else "#C8C8C8"
            self._setTextItem(table, row, 0, item.get('group', 'Unknown'), text_color)
            type_color = "#666666" if is_ignored else "#AB26FF"
            self._setTypeItem(table, row, 1, "Frame Range", type_color, "🎞")
            self._setTextItem(table, row, 2, item.get('shot', ''), text_color)
            # For 2D renders, show full name with prefix and suffix in identifier column
            identifier_text = (
                item.get('original_name', item.get('identifier', ''))
                if item.get('group') == '2D Renders'
                else item.get('identifier', '')
            )
            self._setTextItem(table, row, 3, identifier_text, text_color)  # Identifier
            # Name column stays empty for 2D renders
            name_text = '' if item.get('group') == '2D Renders' else item.get('original_name', item['name'])
            self._setTextItem(table, row, 4, name_text + (" (Ignored)" if is_ignored else ""), text_color)
            self._setTextItem(table, row, 5, f"{item['comp_range']} → {item['kitsu_range']}", text_color)
            if is_ignored:
                self._setRowGray(table, row)
                bypassed_rows.add(row)
            row += 1

        for item in issues['resolution_mismatch'][:100]:
            table.insertRow(row)
            item_key = self._generateItemKey(item, 'resolution_mismatch')
            is_ignored = item_key in current_ignored.get('resolution_mismatch', set())
            row_data[row] = {'type': 'resolution', 'data': item}

            text_color = "#666666" if is_ignored else "#C8C8C8"
            self._setTextItem(table, row, 0, item.get('group', 'Unknown'), text_color)
            type_color = "#666666" if is_ignored else "#DAA520"
            self._setTypeItem(table, row, 1, "Resolution", type_color, "🖼")
            self._setTextItem(table, row, 2, item.get('shot', ''), text_color)
            # For 2D renders, show full name with prefix and suffix in identifier column
            identifier_text = (
                item.get('original_name', item.get('identifier', ''))
                if item.get('group') == '2D Renders'
                else item.get('identifier', '')
            )
            self._setTextItem(table, row, 3, identifier_text, text_color)  # Identifier for resolution
            # Name column stays empty for 2D renders
            name_text = '' if item.get('group') == '2D Renders' else item.get('original_name', item['name'])
            self._setTextItem(table, row, 4, name_text + (" (Ignored)" if is_ignored else ""), text_color)
            self._setTextItem(table, row, 5, f"{item['current']} → {item['expected']}", text_color)
            if is_ignored:
                self._setRowGray(table, row)
                bypassed_rows.add(row)
            # No bright yellow background - just use the golden type badge color
            row += 1

        table.resizeColumnsToContents()
        table.setColumnWidth(0, 100)  # Folder column
        table.setColumnWidth(1, 100)  # Type column - fixed width for badges
        table.setColumnWidth(3, 150)  # Identifier column
        table.setColumnWidth(4, 280)  # Name column wider
        table.setColumnWidth(5, 250)  # Details column - wider to prevent truncation

        # Connect context menu
        table.customContextMenuRequested.connect(
            lambda pos: self._showTableContextMenu(pos, table, row_data)
        )

        # Function to toggle bypassed rows visibility
        def toggleBypassedRows(checked):
            """Show or hide bypassed rows based on checkbox state"""
            for row in bypassed_rows:
                if row < table.rowCount():
                    table.setRowHidden(row, not checked)

        # Connect checkbox to toggle function
        show_bypassed_checkbox.stateChanged.connect(lambda state: toggleBypassedRows(bool(state)))

        # Initially hide bypassed rows (checkbox is unchecked by default)
        for row in bypassed_rows:
            if row < table.rowCount():
                table.setRowHidden(row, True)

        layout.addWidget(table)

        # Show count if truncated
        if row >= 100:
            truncated = total_issues - 100
            note = QLabel(f"Showing first 100 of {total_issues} issues")
            note.setAlignment(Qt.AlignRight)
            layout.addWidget(note)

        # Buttons - update all items (using non-ignored counts for labels)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        if issues['outdated']:
            outdated_btn = QPushButton(f"Update {non_ignored_outdated} Outdated")
            outdated_btn.setStyleSheet(self._buttonStyle("#FF6464"))
            outdated_btn.clicked.connect(lambda: self._updateAllOutdated(dlg))
            button_layout.addWidget(outdated_btn)

        if issues['fps_mismatch']:
            fps_btn = QPushButton(f"Update {non_ignored_fps} FPS")
            fps_btn.setStyleSheet(self._buttonStyle("#3498DB"))
            fps_btn.clicked.connect(lambda: self._fixAllFPS(dlg))
            button_layout.addWidget(fps_btn)

        # Resolution button for comps only
        if non_ignored_resolution_comps > 0:
            resolution_btn = QPushButton(f"Update {non_ignored_resolution_comps} Comp Resolution")
            resolution_btn.setStyleSheet(self._buttonStyle("#DAA520"))
            # Read from cached items when clicked and filter out ignored items
            resolution_btn.clicked.connect(lambda: self._updateCompResolution(dlg))
            button_layout.addWidget(resolution_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._buttonStyle("#666"))
        close_btn.clicked.connect(dlg.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dlg.exec_()

    def _setTextItem(self, table, row, col, text, color):
        """Create a text item with consistent widget for alignment"""
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        label = QLabel(str(text))
        label.setObjectName("text_label")
        label.setStyleSheet(f"color: {color};")
        layout.addWidget(label)

        layout.addStretch()
        widget.setLayout(layout)

        item = QTableWidgetItem("")
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, col, item)
        table.setCellWidget(row, col, widget)

    def _setTypeItem(self, table, row, col, text, color, icon=""):
        """Create a colored type item with icon and background"""
        widget = QWidget()
        widget.setStyleSheet("background-color: transparent;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Color badge
        badge = QLabel()
        badge.setObjectName("type_badge")
        badge.setFixedSize(10, 10)
        badge.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        layout.addWidget(badge)

        # Icon + text
        label = QLabel(f"{icon} {text}" if icon else text)
        label.setObjectName("type_text")
        label.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")
        layout.addWidget(label)

        layout.addStretch()
        widget.setLayout(layout)

        item = QTableWidgetItem("")
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        table.setItem(row, col, item)
        table.setCellWidget(row, col, widget)

    def _setRowBackground(self, table, row, bgColor):
        """Set the background color for all items in a row"""
        if bgColor:
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    item.setBackground(QBrush(QColor(bgColor)))
        else:
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item:
                    item.setBackground(QBrush(QColor(47, 48, 54)))

    def _setRowGray(self, table, row):
        """Set the entire row to gray (for ignored items)"""
        gray_color = QColor("#666666")
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                item.setForeground(QBrush(gray_color))

    def _createTableItem(self, text, color=""):
        """Create a table item with optional color"""
        item = QTableWidgetItem(str(text))
        if color:
            item.setForeground(QBrush(QColor(color)))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        # Set consistent text alignment to prevent shifting on hover/select
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return item

    def _buttonStyle(self, color):
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {self._darkenColor(color)};
            }}
        """

    def _darkenColor(self, hex_color, percent=15):
        """Darken a hex color by percent"""
        from qtpy.QtGui import QColor
        color = QColor(hex_color)
        h, s, v, a = color.getHsv()
        v = max(0, v - (255 * percent // 100))
        new_color = QColor.fromHsv(h, s, v, a)
        return new_color.name()

    def _updateAllOutdated(self, dlg):
        """Update all outdated footage"""
        dlg.hide()
        # Run the update
        self.tracker.updateAllOutdated()
        # Re-check after 500ms
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _fixAllFPS(self, dlg):
        """Fix all FPS issues"""
        dlg.hide()
        # Run the FPS fix
        self.tracker.updateAllFPS()
        # Re-check after 500ms
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _filterIgnoredItems(self, items, issue_type):
        """Filter out ignored items from a list of issue items"""
        ignored_items = self._getIgnoredItems()
        config_type = self._mapToConfigType(issue_type)
        ignored_set = ignored_items.get(config_type, set())

        filtered = []
        for item in items:
            item_key = self._generateItemKey(item, issue_type)
            if item_key not in ignored_set:
                filtered.append(item)
        return filtered

    def _syncAllCompsWithKitsu(self, dlg):
        """Sync all compositions frame ranges with Kitsu data (reads from footage tracker cache)"""
        dlg.hide()

        # Read from footage tracker cache and filter out ignored items
        cached_items = getattr(self.tracker, '_cached_issue_items', {})
        frame_range_issues = self._filterIgnoredItems(cached_items.get('frame_range_mismatch', []), 'frame_range')

        # Group comps by Kitsu data to minimize API calls
        comps_by_kitsu = {}
        for item in frame_range_issues:
            shot = item.get('shot', '')
            if shot:
                key = (shot, item.get('kitsu_start'), item.get('kitsu_end'))
                if key not in comps_by_kitsu:
                    comps_by_kitsu[key] = []
                comps_by_kitsu[key].append({
                    'comp_id': item.get('comp_id'),
                    'comp_name': item.get('comp_name')
                })

        # Sync each group of comps
        total_synced = 0
        for key, comps in comps_by_kitsu.items():
            shot, kitsu_start, kitsu_end = key
            kitsu_frame_range = f"{int(kitsu_start)}-{int(kitsu_end)}"

            for comp in comps:
                comp_id = comp.get('comp_id')
                comp_name = comp.get('comp_name')
                if comp_id:
                    # Call the comp_manager's setCompFrameRangeFromKitsu method (frame range only, no FPS change)
                    result = self.tracker.comp_manager.setCompFrameRangeFromKitsu(
                        comp_id, comp_name, kitsu_frame_range
                    )
                    total_synced += 1

        self.core.popup(f"Updated frame ranges for {total_synced} composition(s).")

        # Re-check after 500ms
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _updateCompResolution(self, dlg):
        """Update composition resolutions from Kitsu data (reads from footage tracker cache)"""
        dlg.hide()

        # Read from footage tracker cache and filter out ignored items
        cached_items = getattr(self.tracker, '_cached_issue_items', {})
        resolution_issues = self._filterIgnoredItems(cached_items.get('resolution_mismatch', []), 'resolution')
        # Only comps
        comp_resolution_issues = [i for i in resolution_issues if i.get('group') == 'Comps']

        # Group comps by shot to get Kitsu data
        comps_by_shot = {}
        for item in comp_resolution_issues:
            shot = item.get('shot', '')
            comp_id = item.get('comp_id')
            comp_name = item.get('original_name', item.get('comp_name', ''))
            if shot and comp_name:
                if shot not in comps_by_shot:
                    comps_by_shot[shot] = []
                comps_by_shot[shot].append({
                    'comp_id': comp_id,
                    'comp_name': comp_name
                })

        total_updated = 0
        for shot, comps in comps_by_shot.items():
            # Get Kitsu data for this shot
            if shot in self.tracker.kitsuShotData:
                kitsu_data = self.tracker.kitsuShotData[shot]
                kitsu_width = kitsu_data.get('width')
                kitsu_height = kitsu_data.get('height')

                if kitsu_width and kitsu_height:
                    for comp in comps:
                        comp_id = comp.get('comp_id')
                        comp_name = comp.get('comp_name')
                        if comp_id:
                            # Use comp_manager to set resolution
                            result = self.tracker.comp_manager.setCompResolutionFromKitsu(
                                comp_id, comp_name, kitsu_width, kitsu_height
                            )
                            total_updated += 1

        self.core.popup(f"Updated {total_updated} composition(s) to Kitsu resolution.")
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _update3DRendersResolution(self, dlg, renders_resolution_issues):
        """Update 3D renders resolution using Kitsu data"""
        dlg.hide()

        # Import the ImageResizer
        from .image_resizer import ImageResizer
        import os

        resizer = ImageResizer(self.tracker)

        # Check for missing packages
        missing_packages = resizer.getMissingPackages()
        if missing_packages:
            self.core.popup(
                f"Cannot resize 3D renders - missing required packages:\n"
                f"{', '.join(missing_packages)}\n\n"
                f"Please install them first."
            )
            return

        # Group renders by shot to minimize Kitsu lookups and batch by AOV
        aovs_by_shot = {}
        for item in renders_resolution_issues:
            shot = item.get('shot', '')
            if not shot:
                continue

            # Get the path from the item - need to find the actual footage path
            # The issue item has 'name' which is like "[3D Renders] filename"
            original_name = item.get('original_name', '')

            # We need to find the actual footage in the hierarchy to get the path
            # For now, collect the shots we need to process
            if shot not in self.tracker.kitsuShotData:
                continue

            if shot not in aovs_by_shot:
                aovs_by_shot[shot] = []

        if not aovs_by_shot:
            self.core.popup("No valid shots found with Kitsu resolution data.")
            return

        # Get the actual footage paths from the hierarchy
        hierarchy = getattr(self.tracker, '_stored_hierarchy', None)
        if not hierarchy:
            self.core.popup("No footage hierarchy found. Please load footage data first.")
            return

        # Collect all unique AOV folders that need resizing
        aov_folders_to_resize = {}  # {(shot, width, height): [folder_paths]}

        for group_name in ["3D Renders", "2D Renders"]:
            if group_name not in hierarchy:
                continue

            for shot, shot_data in hierarchy[group_name].items():
                if shot not in aovs_by_shot:
                    continue

                # Get Kitsu resolution for this shot
                if shot not in self.tracker.kitsuShotData:
                    continue
                kitsu_data = self.tracker.kitsuShotData[shot]
                kitsu_width = kitsu_data.get('width')
                kitsu_height = kitsu_data.get('height')

                if not kitsu_width or not kitsu_height:
                    continue

                try:
                    target_width = int(kitsu_width)
                    target_height = int(kitsu_height)
                except (ValueError, TypeError):
                    continue

                key = (shot, target_width, target_height)
                if key not in aov_folders_to_resize:
                    aov_folders_to_resize[key] = set()

                # Find all AOV folders for this shot
                if isinstance(shot_data, dict):
                    for identifier, identifier_data in shot_data.items():
                        if isinstance(identifier_data, dict):
                            for aov, footage_list in identifier_data.items():
                                if isinstance(footage_list, list) and footage_list:
                                    # Get the first footage item to find the AOV folder
                                    first_footage = footage_list[0]
                                    path = first_footage.get('path', '')
                                    if path:
                                        # Get the AOV folder (parent of the file)
                                        aov_folder = os.path.dirname(path)
                                        if os.path.isdir(aov_folder):
                                            aov_folders_to_resize[key].add(aov_folder)

        if not aov_folders_to_resize:
            self.core.popup("No AOV folders found that need resizing.")
            return

        # Count total files
        total_files = 0
        for (shot, w, h), folders in aov_folders_to_resize.items():
            for folder in folders:
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    if os.path.isfile(file_path):
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in resizer.SUPPORTED_FORMATS:
                            total_files += 1

        if total_files == 0:
            self.core.popup("No image files found to resize.")
            return

        # Show confirmation dialog
        from qtpy.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
        from qtpy.QtCore import Qt

        confirm = QDialog(self.tracker.dlg_footage)
        confirm.setWindowTitle("Resize 3D Renders")
        confirm.resize(400, 200)
        layout = QVBoxLayout()
        confirm.setLayout(layout)

        info_text = QLabel(
            f"Found {total_files} image files to resize.\n\n"
            "This will create backups and resize images to Kitsu resolution."
        )
        layout.addWidget(info_text)

        btn_layout = QHBoxLayout()
        yes_btn = QPushButton("Yes, Resize")
        no_btn = QPushButton("Cancel")
        btn_layout.addWidget(yes_btn)
        btn_layout.addWidget(no_btn)
        layout.addLayout(btn_layout)

        yes_btn.clicked.connect(confirm.accept)
        no_btn.clicked.connect(confirm.reject)

        if confirm.exec_() != QDialog.Accepted:
            return

        # Create progress dialog
        progress = QDialog(self.tracker.dlg_footage)
        progress.setWindowTitle("Resizing 3D Renders...")
        progress.resize(400, 120)
        prog_layout = QVBoxLayout()
        progress.setLayout(prog_layout)

        status_label = QLabel("Resizing images...")
        prog_layout.addWidget(status_label)

        prog_bar = QProgressBar()
        prog_bar.setMaximum(total_files)
        prog_layout.addWidget(prog_bar)

        progress.show()
        from qtpy.QtWidgets import QApplication
        QApplication.processEvents()

        # Execute resize - match context menu implementation
        current_file = 0
        success_count = 0
        error_count = 0

        for (shot, target_width, target_height), folders in aov_folders_to_resize.items():
            for folder in folders:
                # Create backup folder
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_folder = os.path.join(folder, f"originals_backup_{timestamp}")
                os.makedirs(backup_folder, exist_ok=True)

                # Use resizer.collectAOVFiles to properly collect files (like context menu)
                # Get a sample file from the folder
                sample_file = ''
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    if os.path.isfile(file_path):
                        ext = os.path.splitext(filename)[1].lower()
                        if ext in resizer.SUPPORTED_FORMATS:
                            sample_file = file_path
                            break

                if not sample_file:
                    continue

                # Collect files using the resizer method
                files, _ = resizer.collectAOVFiles(sample_file)

                if not files:
                    continue

                # Detect AOV name and get interpolation method (like context menu)
                aov_name = resizer.detectAOVFromPath(sample_file)
                interpolation, should_interpolate, interp_name = resizer.getInterpolationMethod(aov_name)

                # Progress callback for this folder
                def progress_callback(current, total):
                    nonlocal current_file
                    prog_bar.setValue(current_file + current)
                    status_label.setText(f"Processing {shot} - {aov_name}: {current}/{total} files")
                    QApplication.processEvents()

                # Resize using ImageResizer batch method (same as context menu)
                results = resizer.batchResizeAOV(
                    files, (target_width, target_height),
                    interpolation, should_interpolate,
                    backup_folder, progress_callback
                )

                current_file += results['total']
                success_count += results['success']
                error_count += results['failed']

        progress.close()

        # Show results
        result_msg = f"Resize complete!\n\n"
        result_msg += f"Successfully resized: {success_count} files\n"
        if error_count > 0:
            result_msg += f"Errors: {error_count} files\n"

        self.core.popup(result_msg)

        # Re-check after resize
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _checkAfterUpdate(self):
        """Re-check for issues after update and show results"""
        # Reload footage data from AE to get updated hierarchy
        self.tracker.loadFootageData()

        # Small delay to ensure data is loaded
        QTimer.singleShot(500, self._showUpdatedWarning)

    def _showUpdatedWarning(self):
        """Show updated warning after data reload"""
        # Get fresh hierarchy
        hierarchy = getattr(self.tracker, '_stored_hierarchy', None)

        if hierarchy:
            # Force a fresh check (clear cache to ensure we get the latest issues)
            # After an update, some issues may have been fixed, so we need to rescan
            self.checkFootageIssues(hierarchy, force_refresh=True)

    def _updateCheckedOutdated(self, dlg, checked_items):
        """Update only checked outdated footage items"""
        if not checked_items:
            self.core.popup("No items selected to update.")
            return

        dlg.hide()
        # Get the paths of checked items
        paths = [item.get('path') for item in checked_items if item.get('path')]
        if paths:
            self.tracker.updateSpecificOutdated(paths)
        # Re-check after 500ms
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _updateCheckedFPS(self, dlg, checked_items):
        """Fix FPS for only checked items"""
        if not checked_items:
            self.core.popup("No items selected to update.")
            return

        dlg.hide()

        # Group by comp vs footage
        comp_items = [i for i in checked_items if i.get('group') == 'Comps']
        footage_items = [i for i in checked_items if i.get('group') != 'Comps']

        # Update comps via comp_manager
        comp_success = 0
        if comp_items:
            for item in comp_items:
                comp_id = item.get('comp_id')
                comp_name = item.get('comp_name', item.get('original_name', ''))
                if comp_id:
                    result = self.tracker.comp_manager.setCompFPSFromKitsu(
                        comp_id, comp_name, item.get('project_fps', 25.0), silent=True
                    )
                    if result:
                        comp_success += 1

        # Update footage items via ae_ops (similar to updateAllFPS but specific items)
        footage_success = 0
        footage_failed = 0

        if footage_items:
            # Find tree items for the footage paths
            target_paths = {item.get('path') for item in footage_items if item.get('path')}
            target_fps_map = {
                item.get('path'): item.get('project_fps', 25.0)
                for item in footage_items if item.get('path')
            }

            footage_tree_items = []

            def findFootageByPath(item):
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'footage':
                    itemPath = userData.get('path', '')
                    if itemPath in target_paths:
                        footage_tree_items.append((item, target_fps_map[itemPath]))

                for i in range(item.childCount()):
                    findFootageByPath(item.child(i))

            for i in range(self.tracker.tw_footage.topLevelItemCount()):
                findFootageByPath(self.tracker.tw_footage.topLevelItem(i))

            # Update the found footage items
            for item, targetFps in footage_tree_items:
                fpsWidget = self.tracker.tw_footage.itemWidget(item, 4)
                if fpsWidget and fpsWidget.layout().count() > 0:
                    spinBox = fpsWidget.layout().itemAt(0).widget()
                    if isinstance(spinBox, QDoubleSpinBox):
                        spinBox.setValue(targetFps)
                        footage_success += 1

        # Show results
        total_updated = comp_success + footage_success
        self.core.popup(f"Updated FPS for {total_updated} item(s) ({comp_success} comps, {footage_success} footage).")

        # Re-check after 500ms
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _updateCheckedFrameRange(self, dlg, checked_items):
        """Sync frame ranges for only checked composition items"""
        if not checked_items:
            self.core.popup("No items selected to update.")
            return

        dlg.hide()

        # Filter to only comp items
        comp_items = [i for i in checked_items if i.get('group') == 'Comps']

        if not comp_items:
            self.core.popup("No compositions selected to update.")
            return

        # Group comps by Kitsu data to minimize processing
        comps_by_kitsu = {}
        for item in comp_items:
            shot = item.get('shot', '')
            if shot:
                key = (shot, item.get('kitsu_start'), item.get('kitsu_end'))
                if key not in comps_by_kitsu:
                    comps_by_kitsu[key] = []
                comps_by_kitsu[key].append({
                    'comp_id': item.get('comp_id'),
                    'comp_name': item.get('comp_name')
                })

        # Sync each group of comps
        total_synced = 0
        for key, comps in comps_by_kitsu.items():
            shot, kitsu_start, kitsu_end = key
            kitsu_frame_range = f"{int(kitsu_start)}-{int(kitsu_end)}"

            for comp in comps:
                comp_id = comp.get('comp_id')
                comp_name = comp.get('comp_name')
                if comp_id:
                    result = self.tracker.comp_manager.setCompFrameRangeFromKitsu(
                        comp_id, comp_name, kitsu_frame_range
                    )
                    total_synced += 1

        self.core.popup(f"Updated frame ranges for {total_synced} composition(s).")
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _updateCheckedCompResolution(self, dlg, checked_items):
        """Update resolution for only checked composition items"""
        if not checked_items:
            self.core.popup("No items selected to update.")
            return

        dlg.hide()

        # Filter to only comp items
        comp_items = [i for i in checked_items if i.get('group') == 'Comps']

        if not comp_items:
            self.core.popup("No compositions selected to update.")
            return

        # Group comps by shot to get Kitsu data
        comps_by_shot = {}
        for item in comp_items:
            shot = item.get('shot', '')
            comp_id = item.get('comp_id')
            comp_name = item.get('original_name', item.get('comp_name', ''))
            if shot and comp_name:
                if shot not in comps_by_shot:
                    comps_by_shot[shot] = []
                comps_by_shot[shot].append({
                    'comp_id': comp_id,
                    'comp_name': comp_name
                })

        total_updated = 0
        for shot, comps in comps_by_shot.items():
            # Get Kitsu data for this shot
            if shot in self.tracker.kitsuShotData:
                kitsu_data = self.tracker.kitsuShotData[shot]
                kitsu_width = kitsu_data.get('width')
                kitsu_height = kitsu_data.get('height')

                if kitsu_width and kitsu_height:
                    for comp in comps:
                        comp_id = comp.get('comp_id')
                        comp_name = comp.get('comp_name')
                        if comp_id:
                            result = self.tracker.comp_manager.setCompResolutionFromKitsu(
                                comp_id, comp_name, kitsu_width, kitsu_height
                            )
                            total_updated += 1

        self.core.popup(f"Updated {total_updated} composition(s) to Kitsu resolution.")
        QTimer.singleShot(500, lambda: self._checkAfterUpdate())

    def _generateItemKey(self, item_data, issue_type):
        """
        Generate a unique key for an item - matches footage tracker's key format exactly.

        Key formats:
        - 3D Footage: footage_{shot}_{identifier}_{aov}
        - 2D Footage: footage_{shot}_{identifier}
        - Comps: comp_{comp_id}_{comp_name}
        """
        print(f"[DEBUG CHECK] _generateItemKey called:")
        print(f"  issue_type = {issue_type}")
        print(f"  item_data = {item_data}")

        if item_data.get('group') == 'Comps':
            # For comps, use compId + compName
            comp_id = item_data.get('compId') or item_data.get('id') or item_data.get('comp_id')
            comp_name = item_data.get('compName') or item_data.get('original_name') or item_data.get('name', '')
            return f"comp_{comp_id}_{comp_name}"
        else:
            # For footage, use shot + identifier + optional AOV
            shot = item_data.get('shot', '')
            identifier = item_data.get('identifier', '')
            aov = item_data.get('aov', '')
            original_name = item_data.get('original_name') or item_data.get('name', '')

            # For 3D renders with AOV: include AOV for individual bypass
            if shot and identifier and aov:
                return f"footage_{shot}_{identifier}_{aov}"

            # For 2D renders (no AOV): use shot + identifier
            # But check for duplicate suffix in tree_text (or original_name as fallback) and include it in identifier
            if shot and identifier and not aov:
                # Prefer tree_text for 2D renders (matches the tree display text used when saving bypass)
                text_for_suffix = item_data.get('tree_text', original_name)
                # Check if this is a 2D render by looking at tree_text or original_name prefix
                is_2d_render = text_for_suffix.startswith('[2D]') or text_for_suffix.startswith('[PB]')
                if is_2d_render:
                    # Extract suffix from tree_text if present
                    # e.g., "[2D] LowRes (1)" -> identifier should become "LowRes (1)" for unique bypass
                    text_without_prefix = text_for_suffix.replace('[2D] ', '').replace('[PB] ', '')
                    if text_without_prefix != identifier:
                        # There's a duplicate suffix
                        suffix = text_without_prefix.replace(identifier, '', 1).strip()
                        if suffix:
                            identifier = f"{identifier} {suffix}"
                return f"footage_{shot}_{identifier}"

            # For 2D renders, identifier might be in original_name
            # Try to extract identifier from the name (e.g., "LowRes" from "[2D Renders] LowRes")
            group = item_data.get('group', '')

            if shot and original_name:
                # Use shot + name as fallback (matches footage tracker's item.text(0) fallback)
                return f"footage_{shot}_{original_name}"
            elif original_name:
                return f"footage_{group}_{original_name}"
            else:
                # Last resort - use path if available
                path = item_data.get('path', '')
                item_key = f"footage_{path}"

        # Debug: show what generated
        print(
            f"[DEBUG CHECK] Generated key: {item_key} from item_data: "
            f"shot={item_data.get('shot', 'N/A')}, identifier={item_data.get('identifier', 'N/A')}, "
            f"aov={item_data.get('aov', 'N/A')}, original_name={item_data.get('original_name', 'N/A')}"
        )

        return item_key

    def _getIgnoredItems(self):
        """Load ignored items from .aep file XMP metadata (with caching)"""
        import json
        import os

        # Try to get current .aep file path
        current_file = None
        try:
            current_file = self.core.getCurrentFileName()
            if current_file and isinstance(current_file, bytes):
                current_file = current_file.decode('utf-8')
        except Exception:
            pass

        # Check cache - return cached data if file hasn't changed
        if self._ignored_items_cache is not None and self._ignored_items_cache_file == current_file:
            print(f"[DEBUG XMP CACHE] Using cached ignored_items (cache hit for {current_file})")
            return self._ignored_items_cache

        print(f"[DEBUG XMP CACHE] Cache miss - reloading ignored_items for {current_file}")
        # Cache miss or file changed - reload
        self._ignored_items_cache_file = current_file

        # Only use XMP metadata if we have an .aep file
        if current_file and current_file.endswith('.aep'):
            try:
                # Read XMP metadata from the project
                scpt = """
                if (app.project && app.project.xmpPacket) {
                    app.project.xmpPacket;
                } else {
                    '';
                }
                """
                result = self.main.ae_core.executeAppleScript(scpt)
                print(f"[DEBUG XMP READ] ExtendScript result length: {len(result) if result else 0}")
                if result and isinstance(result, bytes):
                    result = result.decode('utf-8')

                if result:
                    print(f"[DEBUG XMP READ] XMP packet length: {len(result)}")
                    # Parse XMP to find our custom data
                    # Look for PrismFootageTracker:BypassedItems tag
                    if 'PrismFootageTracker:BypassedItems' in result:
                        print(f"[DEBUG XMP READ] Found PrismFootageTracker:BypassedItems tag")
                        # Extract the JSON data between the tags
                        start_marker = 'PrismFootageTracker:BypassedItems">'
                        end_marker = '</rdf:li'

                        start_idx = result.find(start_marker)
                        print(f"[DEBUG XMP READ] start_idx: {start_idx}")
                        if start_idx > 0:
                            start_idx += len(start_marker)
                            # Find the end of this RDF element (use end_marker variable)
                            end_idx = result.find(end_marker, start_idx)
                            print(f"[DEBUG XMP READ] end_idx: {end_idx}")
                            if end_idx > start_idx:
                                json_str = result[start_idx:end_idx].strip()
                                print(f"[DEBUG XMP READ] JSON string: {json_str}")
                                bypassed = json.loads(json_str)
                                result_data = {k: set(v) for k, v in bypassed.items()}
                                # Ensure all keys exist
                                all_keys = ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']
                                for key in all_keys:
                                    if key not in result_data:
                                        result_data[key] = set()
                                print(f"[DEBUG XMP] Loaded bypassed items from .aep XMP metadata")
                                print(f"[DEBUG XMP] Result: {result_data}")
                                self._ignored_items_cache = result_data
                                return result_data
                            else:
                                print(f"[DEBUG XMP READ] Could not find end marker")
                    else:
                        print(f"[DEBUG XMP READ] PrismFootageTracker:BypassedItems tag NOT found in XMP")
                else:
                    print(f"[DEBUG XMP READ] Empty XMP packet")
            except Exception as e:
                print(f"[DEBUG XMP] Error reading XMP metadata: {e}")
                import traceback
                traceback.print_exc()

        # Fallback 1: Try sidecar file (migration)
        if current_file and current_file.endswith('.aep'):
            bypassed_file = os.path.splitext(current_file)[0] + '_bypassed.json'
            if os.path.exists(bypassed_file):
                try:
                    with open(bypassed_file, 'r') as f:
                        bypassed = json.load(f)
                    result_data = {k: set(v) for k, v in bypassed.items()}
                    # Ensure all keys exist
                    all_keys = ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']
                    for key in all_keys:
                        if key not in result_data:
                            result_data[key] = set()
                    print(f"[DEBUG XMP] Loaded from sidecar file (migration)")
                    self._ignored_items_cache = result_data
                    return result_data
                except Exception:
                    pass

        # Fallback 2: Project config (old method)
        bypassed = self.core.getConfig("footage_tracker", "bypassed_items", config="project")
        if bypassed:
            # Convert to sets and ensure all keys exist
            result_data = {k: set(v) for k, v in bypassed.items()}
            # Ensure all keys exist (in case config only has partial data)
            all_keys = ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']
            for key in all_keys:
                if key not in result_data:
                    result_data[key] = set()
            print(f"[DEBUG XMP] Loaded from project config (legacy)")
            print(f"[DEBUG XMP] Loaded data: {result_data}")
            self._ignored_items_cache = result_data
            return result_data

        # Default empty state
        result_data = {'outdated': set(), 'fps_mismatch': set(),
                       'frame_range_mismatch': set(), 'resolution_mismatch': set()}
        print(f"[DEBUG XMP] No bypassed items found, using empty state")
        self._ignored_items_cache = result_data
        return result_data

    def _saveIgnoredItems(self, ignored_items):
        """Save ignored items to .aep file XMP metadata"""
        import json

        print(f"[DEBUG SAVE] _saveIgnoredItems called with: {ignored_items}")

        # Ensure all keys exist and convert sets to lists for JSON serialization
        all_keys = ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']
        to_save = {}
        for key in all_keys:
            if key in ignored_items:
                to_save[key] = list(ignored_items[key]) if isinstance(ignored_items[key], set) else ignored_items[key]
            else:
                to_save[key] = []

        json_data = json.dumps(to_save)
        print(f"[DEBUG SAVE] Saving to config: {to_save}")

        # Invalidate cache when saving new data
        self._ignored_items_cache = None
        self._ignored_items_cache_file = None

        # Try to get current .aep file path
        current_file = None
        try:
            current_file = self.core.getCurrentFileName()
            if current_file and isinstance(current_file, bytes):
                current_file = current_file.decode('utf-8')
        except Exception:
            pass

        # Only write to XMP if we have an .aep file
        if current_file and current_file.endswith('.aep'):
            try:
                # Read current XMP packet
                scpt_read = """
                if (app.project && app.project.xmpPacket) {
                    app.project.xmpPacket;
                } else {
                    '';
                }
                """
                result = self.main.ae_core.executeAppleScript(scpt_read)
                if result and isinstance(result, bytes):
                    result = result.decode('utf-8')

                xmp_packet = result if result else ''

                # Check if our custom data already exists
                custom_tag = 'PrismFootageTracker:BypassedItems'
                if custom_tag in xmp_packet:
                    # Replace existing data
                    start_marker = f'{custom_tag}>'
                    end_marker = '</rdf:li>'

                    start_idx = xmp_packet.find(start_marker)
                    if start_idx > 0:
                        start_idx += len(start_marker)
                        end_idx = xmp_packet.find(end_marker, start_idx)
                        if end_idx > start_idx:
                            # Replace the JSON data
                            xmp_packet = xmp_packet[:start_idx] + json_data + xmp_packet[end_idx:]
                        else:
                            # Couldn't find proper end, append instead
                            xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)
                    else:
                        # Marker not found, append
                        xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)
                else:
                    # Add our custom data to XMP
                    xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)

                # Write the updated XMP packet back to the project
                # Need to escape the XMP packet for ExtendScript
                xmp_escaped = (
                    xmp_packet.replace('\\', '\\\\').replace('"', '\\"')
                    .replace('\n', '\\n').replace('\r', '\\r')
                )

                scpt_write = f'''
                if (app.project) {{
                    app.project.xmpPacket = "{xmp_escaped}";
                    "SUCCESS";
                }} else {{
                    "ERROR: No project";
                }}
                '''

                result = self.main.ae_core.executeAppleScript(scpt_write)
                if result and b'SUCCESS' in result:
                    print(f"[DEBUG XMP] Successfully saved bypassed items to .aep XMP metadata")
                else:
                    print(f"[DEBUG XMP] Failed to save XMP, result: {result}")
                # Always save to project config as reliable fallback
                # (AE may strip non-standard XMP tags on re-parse)
                self.core.setConfig("footage_tracker", "bypassed_items", to_save, config="project")

            except Exception as e:
                print(f"[DEBUG XMP] Error writing XMP metadata: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to project config
                self.core.setConfig("footage_tracker", "bypassed_items", to_save, config="project")
        else:
            # No .aep file - save to project config
            self.core.setConfig("footage_tracker", "bypassed_items", to_save, config="project")
            print(f"[DEBUG XMP] Saved to project config (no .aep file)")

    def _appendBypassedItemsToXMP(self, xmp_packet, json_data):
        """Append bypassed items to XMP packet"""
        # Our custom namespace and data
        custom_data = f'''<rdf:li rdf:parseType="Resource">PrismFootageTracker:BypassedItems>{json_data}</rdf:li>'''

        # Find a good place to insert our data
        # Look for the UserDefined array in the XMP
        if '<pdfx:UserDefined>' in xmp_packet:
            # Insert into existing UserDefined section
            marker = '<pdfx:UserDefined>'
            insert_pos = xmp_packet.find(marker)
            if insert_pos > 0:
                insert_pos += len(marker)
                xmp_packet = xmp_packet[:insert_pos] + custom_data + xmp_packet[insert_pos:]
                return xmp_packet

        # If no UserDefined section, create one
        # Find a good insertion point - before the closing x:xmpmeta tag
        if '</x:xmpmeta>' in xmp_packet:
            user_defined_section = f'<pdfx:UserDefined>{custom_data}</pdfx:UserDefined>'
            xmp_packet = xmp_packet.replace('</x:xmpmeta>', user_defined_section + '</x:xmpmeta>')
            return xmp_packet

        # Last resort - append at the end
        return xmp_packet + custom_data

    def _updateCachedIssueCounts(self):
        """Update cached issue counts by filtering ignored items from the cached items"""
        cached_items = getattr(self.tracker, '_cached_issue_items', None)
        if not cached_items:
            return

        # Get ignored items
        ignored_items = self._getIgnoredItems()

        # Count non-ignored items for each type
        for issue_type in ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']:
            ignored_set = ignored_items.get(issue_type, set())
            count = 0
            for item in cached_items.get(issue_type, []):
                # Generate key for this item
                if issue_type == 'outdated':
                    item_key = self._generateItemKey(item, 'outdated')
                elif issue_type == 'fps_mismatch':
                    item_key = self._generateItemKey(item, 'fps_mismatch')
                elif issue_type == 'frame_range_mismatch':
                    item_key = self._generateItemKey(item, 'frame_range_mismatch')
                elif issue_type == 'resolution_mismatch':
                    item_key = self._generateItemKey(item, 'resolution_mismatch')
                else:
                    item_key = None

                # Count only non-ignored items
                if item_key and item_key not in ignored_set:
                    count += 1

            self.tracker._cached_issue_counts[issue_type] = count

    def _resetIgnoredItems(self, dlg):
        """Clear all ignored items and refresh the dialog"""
        reply = QMessageBox.question(
            dlg,
            "Reset Ignored Items",
            "This will clear all ignored items. All issues will be shown again.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._saveIgnoredItems({'outdated': set(), 'fps_mismatch': set(),
                                   'frame_range_mismatch': set(), 'resolution_mismatch': set()})
            dlg.accept()
            # Re-run check to show all items
            QTimer.singleShot(100, lambda: self.checkFootageIssues())

    def _showConfigLocation(self):
        """Show the config file location in a message box"""
        project_path = getattr(self.core, 'projectPath', None)

        if not project_path:
            QMessageBox.information(
                None,
                "Config Location",
                "No Prism project is currently loaded.\n\n"
                "The config file will be stored in the project's Prism configuration\n"
                "once a project is loaded."
            )
            return

        # The config is stored in the project's Prism config
        # In Prism, project-level configs are typically stored as JSON files
        # within the project directory structure
        config_info = (
            f"<b>Prism Project Path:</b><br>"
            f"{project_path}<br><br>"
            f"<b>Config Key:</b> footage_tracker.bypassed_items<br><br>"
            f"<b>Config Type:</b> Project-level (shared with Footage Tracker)<br><br>"
            f"The bypassed items are stored in the Prism project configuration.<br>"
            f"This is the same config used by the Footage Tracker's Ctrl+Shift+Click bypass.<br>"
            f"You can access and modify this config through Prism's config system<br>"
            f"or by editing the project's config JSON file directly."
        )

        QMessageBox.information(
            None,
            "Config File Location",
            config_info
        )

    def _showTableContextMenu(self, position, table, row_data):
        """Show context menu for table rows with Bypass/Unbypass options"""
        # Get the item at position
        item = table.itemAt(position)
        if not item:
            return

        # Get selected rows
        selected_items = table.selectedItems()
        if not selected_items:
            return

        selected_rows = set(table.row(item) for item in selected_items)
        selected_rows = sorted(selected_rows)

        # Check if any rows are not in row_data
        valid_rows = [r for r in selected_rows if r in row_data]
        if not valid_rows:
            return

        menu = QMenu(table)

        # Check bypass state of all selected items
        bypassed_count = 0
        not_bypassed_count = 0
        ignored_items = self._getIgnoredItems()

        for row in valid_rows:
            info = row_data[row]
            item_key = self._generateItemKey(info['data'], info['type'])
            issue_type = self._mapToConfigType(info['type'])
            if item_key in ignored_items.get(issue_type, set()):
                bypassed_count += 1
            else:
                not_bypassed_count += 1

        total_count = len(valid_rows)

        if total_count == 1:
            # Single item - show original menu
            row = valid_rows[0]
            info = row_data[row]
            item_key = self._generateItemKey(info['data'], info['type'])
            issue_type = self._mapToConfigType(info['type'])
            is_bypassed = item_key in ignored_items.get(issue_type, set())

            if is_bypassed:
                # Show Unbypass option
                unbypassAction = QAction("Unbypass This Item", menu)
                unbypassAction.triggered.connect(
                    lambda checked=False, r=row, i=info, t=table: self._unbypassSingleItem(i, t, r)
                )
                menu.addAction(unbypassAction)
            else:
                # Show Bypass options
                type_name = self._getTypeName(info['type'])
                bypassAction = QAction(f"Bypass This {type_name}", menu)
                bypassAction.triggered.connect(
                    lambda checked=False, r=row, i=info, t=table: self._bypassSingleItem(i, t, r)
                )
                menu.addAction(bypassAction)

                menu.addSeparator()

                # Bulk bypass option
                type_label = self._getTypeLabel(info['type'])
                bypassAllAction = QAction(f"Bypass All {type_label}", menu)
                bypassAllAction.triggered.connect(
                    lambda checked=False, it=info['type'], rd=row_data, t=table: self._bypassAllOfType(it, rd, t)
                )
                menu.addAction(bypassAllAction)
        else:
            # Multiple items selected - capture values with default arguments
            # Use checked=False to handle Qt's triggered signal parameter
            if not_bypassed_count > 0:
                bypassAction = QAction(f"Bypass Selected ({not_bypassed_count} items)", menu)
                bypassAction.triggered.connect(
                    lambda checked=False, vr=valid_rows, rd=row_data, t=table: self._bypassMultipleItems(vr, rd, t)
                )
                menu.addAction(bypassAction)

            if bypassed_count > 0:
                unbypassAction = QAction(f"Unbypass Selected ({bypassed_count} items)", menu)
                unbypassAction.triggered.connect(
                    lambda checked=False, vr=valid_rows, rd=row_data, t=table: self._unbypassMultipleItems(vr, rd, t)
                )
                menu.addAction(unbypassAction)

        menu.exec_(table.viewport().mapToGlobal(position))

    def _bypassSingleItem(self, info, table, row):
        """Bypass item and reload dialog"""
        item_key = self._generateItemKey(info['data'], info['type'])
        config_type = self._mapToConfigType(info['type'])

        # Save to config for persistence
        ignored_items = self._getIgnoredItems()
        ignored_items[config_type].add(item_key)
        self._saveIgnoredItems(ignored_items)

        # Update cached counts immediately (before loadFootageData)
        self._updateCachedIssueCounts()

        # Reload footage tracker tree to update bypass styling
        self.tracker.loadFootageData()

        # Close and reopen dialog
        if hasattr(self, '_current_dialog') and self._current_dialog:
            self._current_dialog.accept()
        QTimer.singleShot(50, lambda: self.checkFootageIssues())

    def _unbypassSingleItem(self, info, table, row):
        """Unbypass item and reload dialog"""
        item_key = self._generateItemKey(info['data'], info['type'])
        config_type = self._mapToConfigType(info['type'])

        # Remove from ignored config
        ignored_items = self._getIgnoredItems()
        ignored_items[config_type].discard(item_key)
        self._saveIgnoredItems(ignored_items)

        # Update cached counts immediately (before loadFootageData)
        self._updateCachedIssueCounts()

        # Reload footage tracker tree to update bypass styling
        self.tracker.loadFootageData()

        # Close and reopen dialog
        if hasattr(self, '_current_dialog') and self._current_dialog:
            self._current_dialog.accept()
        QTimer.singleShot(50, lambda: self.checkFootageIssues())

    def _bypassMultipleItems(self, rows, row_data, table):
        """Bypass multiple selected items and reload dialog"""
        ignored_items = self._getIgnoredItems()
        bypassed_count = 0

        for row in rows:
            if row not in row_data:
                continue
            info = row_data[row]
            item_key = self._generateItemKey(info['data'], info['type'])
            issue_type = self._mapToConfigType(info['type'])

            # Only bypass if not already bypassed
            if item_key not in ignored_items.get(issue_type, set()):
                ignored_items[issue_type].add(item_key)
                bypassed_count += 1

        self._saveIgnoredItems(ignored_items)

        if bypassed_count > 0:
            # Update cached counts immediately (before loadFootageData)
            self._updateCachedIssueCounts()

            # Reload footage tracker tree to update bypass styling
            self.tracker.loadFootageData()

            # Close and reopen dialog
            if hasattr(self, '_current_dialog') and self._current_dialog:
                self._current_dialog.accept()
            QTimer.singleShot(50, lambda: self.checkFootageIssues())

    def _unbypassMultipleItems(self, rows, row_data, table):
        """Unbypass multiple selected items and reload dialog"""
        ignored_items = self._getIgnoredItems()
        restored_count = 0

        # Clear selection to prevent interference with updates
        table.clearSelection()

        for row in rows:
            if row not in row_data:
                continue
            info = row_data[row]
            item_key = self._generateItemKey(info['data'], info['type'])
            issue_type = self._mapToConfigType(info['type'])

            # Only unbypass if currently bypassed
            if item_key in ignored_items.get(issue_type, set()):
                ignored_items[issue_type].discard(item_key)
                restored_count += 1

        self._saveIgnoredItems(ignored_items)

        if restored_count > 0:
            # Update cached counts immediately (before loadFootageData)
            self._updateCachedIssueCounts()

            # Reload footage tracker tree to update bypass styling
            self.tracker.loadFootageData()

            # Close and reopen dialog
            if hasattr(self, '_current_dialog') and self._current_dialog:
                self._current_dialog.accept()
            QTimer.singleShot(50, lambda: self.checkFootageIssues())

    def _bypassAllOfType(self, issue_type, row_data, table):
        """Bypass all items of a specific issue type and reload dialog"""
        ignored_items = self._getIgnoredItems()
        config_type = self._mapToConfigType(issue_type)
        bypassed_count = 0

        for row, info in row_data.items():
            if info['type'] == issue_type:
                item_key = self._generateItemKey(info['data'], issue_type)
                if item_key not in ignored_items.get(config_type, set()):
                    ignored_items[config_type].add(item_key)
                    bypassed_count += 1

        self._saveIgnoredItems(ignored_items)

        if bypassed_count > 0:
            # Update cached counts immediately (before loadFootageData)
            self._updateCachedIssueCounts()

            # Reload footage tracker tree to update bypass styling
            self.tracker.loadFootageData()

            # Close and reopen dialog
            if hasattr(self, '_current_dialog') and self._current_dialog:
                self._current_dialog.accept()
            QTimer.singleShot(50, lambda: self.checkFootageIssues())

    def _mapToConfigType(self, checkbox_type):
        """Map checkbox type to config type"""
        mapping = {
            'outdated': 'outdated',
            'fps': 'fps_mismatch',
            'frame_range': 'frame_range_mismatch',
            'resolution': 'resolution_mismatch'
        }
        return mapping.get(checkbox_type, checkbox_type)

    def _getTypeName(self, checkbox_type):
        """Get display name for issue type"""
        names = {
            'outdated': 'Item',
            'fps': 'FPS Issue',
            'frame_range': 'Frame Range Issue',
            'resolution': 'Resolution Issue'
        }
        return names.get(checkbox_type, 'Item')

    def _getTypeLabel(self, checkbox_type):
        """Get type label for badge"""
        labels = {
            'outdated': 'Outdated',
            'fps': 'FPS',
            'frame_range': 'Frame Range',
            'resolution': 'Resolution'
        }
        return labels.get(checkbox_type, '')

    def _getTypeIcon(self, checkbox_type):
        """Get icon emoji for type"""
        icons = {
            'outdated': '📦',
            'fps': '🎬',
            'frame_range': '🎞',
            'resolution': '🖼'
        }
        return icons.get(checkbox_type, '')

    def _getTypeColor(self, checkbox_type):
        """Get color for type"""
        colors = {
            'outdated': '#FF6464',
            'fps': '#3498DB',
            'frame_range': '#AB26FF',
            'resolution': '#DAA520'
        }
        return colors.get(checkbox_type, '#C8C8C8')

    def _refreshRowAppearance(self, table, row, info):
        """Refresh a single row's appearance (for unbypass)"""
        # Re-set items with normal colors
        text_color = "#C8C8C8"
        type_color = self._getTypeColor(info['type'])

        # Update folder column
        folder_item = table.item(row, 0)
        if folder_item:
            folder_item.setForeground(QBrush(QColor(text_color)))
            folder_item.setBackground(QBrush(QColor(47, 48, 54)))

        # Update type badge
        self._setTypeItem(table, row, 1, self._getTypeLabel(info['type']),
                          type_color, self._getTypeIcon(info['type']))

        # Update shot column
        shot_item = table.item(row, 2)
        if shot_item:
            shot_item.setForeground(QBrush(QColor(text_color)))
            shot_item.setBackground(QBrush(QColor(47, 48, 54)))

        # Update name column - remove (Ignored) suffix
        name_item = table.item(row, 4)
        if name_item:
            text = name_item.text().replace(' (Ignored)', '')
            name_item.setText(text)
            name_item.setForeground(QBrush(QColor(text_color)))
            name_item.setBackground(QBrush(QColor(47, 48, 54)))

        # Update details column
        details_item = table.item(row, 5)
        if details_item:
            details_item.setForeground(QBrush(QColor(text_color)))
            details_item.setBackground(QBrush(QColor(47, 48, 54)))
