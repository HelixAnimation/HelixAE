# -*- coding: utf-8 -*-
"""
Tree Renderer Module
Handles the visual rendering of the tree widget
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class TreeRenderer:
    """Handles rendering of tree widget items"""

    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core
        self.utils = tracker.utils

        # Issue counters that are populated during rendering
        self.issue_counts = {
            'outdated': 0,
            'fps_mismatch': 0,
            'frame_range_mismatch': 0,
            'resolution_mismatch': 0,
            'total_footage': 0,
            'total_comps': 0
        }

        # Detailed issue items for dialog display (populated during rendering)
        self.issue_items = {
            'outdated': [],
            'fps_mismatch': [],
            'frame_range_mismatch': [],
            'resolution_mismatch': []
        }

    @err_catcher(name=__name__)
    def renderHierarchyTree(self, hierarchy):
        """Render complete hierarchy tree"""
        import time

        render_start = time.perf_counter()

        # TEMPORARY: Always clear the tree to force rebuild with new styling
        self.tracker.tw_footage.clear()

        # Reset issue counters before rendering
        self.issue_counts = {
            'outdated': 0,
            'fps_mismatch': 0,
            'frame_range_mismatch': 0,
            'resolution_mismatch': 0,
            'total_footage': 0,
            'total_comps': 0
        }

        # Reset issue items before rendering
        self.issue_items = {
            'outdated': [],
            'fps_mismatch': [],
            'frame_range_mismatch': [],
            'resolution_mismatch': []
        }

        # The hierarchy is organized by groups
        for group in ["3D Renders", "2D Renders", "Resources", "External", "Comps"]:
            if group in hierarchy and hierarchy[group]:
                group_start = time.perf_counter()
                if group in ["3D Renders", "2D Renders"]:
                    # Build render tree
                    self._buildRenderTree(group, hierarchy[group])
                elif group == "Comps":
                    # Build comps tree
                    self._buildCompsTree(hierarchy[group])
                else:
                    # Build preserved structure tree
                    self._buildPreservedStructureTree(group, hierarchy[group])
                group_end = time.perf_counter()
                print(f"[TIMING]   Render {group}: {group_end - group_start:.4f}s")

        cache_start = time.perf_counter()
        # Get ignored items for counting (but don't filter from cache)
        ignored_items = self.tracker.startup_warnings._getIgnoredItems()

        # Cache ALL items (including ignored ones) - Check Issues dialog will show them grayed out
        all_cached_items = {
            'outdated': list(self.issue_items.get('outdated', [])),
            'fps_mismatch': list(self.issue_items.get('fps_mismatch', [])),
            'frame_range_mismatch': list(self.issue_items.get('frame_range_mismatch', [])),
            'resolution_mismatch': list(self.issue_items.get('resolution_mismatch', []))
        }

        # Count non-ignored items for button counts
        non_ignored_counts = {
            'outdated': 0,
            'fps_mismatch': 0,
            'frame_range_mismatch': 0,
            'resolution_mismatch': 0
        }

        # Count items that are NOT ignored (for button labels)
        for issue_type in ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']:
            ignored_set = ignored_items.get(issue_type, set())
            for item in self.issue_items.get(issue_type, []):
                # Generate key for this item
                if issue_type == 'outdated':
                    item_key = self.tracker.startup_warnings._generateItemKey(item, 'outdated')
                elif issue_type == 'fps_mismatch':
                    item_key = self.tracker.startup_warnings._generateItemKey(item, 'fps_mismatch')
                elif issue_type == 'frame_range_mismatch':
                    item_key = self.tracker.startup_warnings._generateItemKey(item, 'frame_range_mismatch')
                elif issue_type == 'resolution_mismatch':
                    item_key = self.tracker.startup_warnings._generateItemKey(item, 'resolution_mismatch')
                else:
                    item_key = None

                # Count only non-ignored items
                if item_key and item_key not in ignored_set:
                    non_ignored_counts[issue_type] += 1

        # Store cached issue counts (non-ignored only - for button numbers)
        self.tracker._cached_issue_counts = {
            'outdated': non_ignored_counts['outdated'],
            'fps_mismatch': non_ignored_counts['fps_mismatch'],
            'frame_range_mismatch': non_ignored_counts['frame_range_mismatch'],
            'resolution_mismatch': non_ignored_counts['resolution_mismatch'],
            'total_footage': self.issue_counts['total_footage'],
            'total_comps': self.issue_counts['total_comps']
        }
        # Store ALL cached issue items (including ignored ones - dialog will gray them out)
        self.tracker._cached_issue_items = all_cached_items
        cache_end = time.perf_counter()
        print(f"[TIMING]   Cache issue data: {cache_end - cache_start:.4f}s")

        expand_start = time.perf_counter()
        # Expand all top level items
        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            self.tracker.tw_footage.topLevelItem(i).setExpanded(True)
        expand_end = time.perf_counter()
        print(f"[TIMING]   Expand top level: {expand_end - expand_start:.4f}s")

        # Print issue summary
        total_issues = (self.issue_counts['outdated'] +
                       self.issue_counts['fps_mismatch'] +
                       self.issue_counts['frame_range_mismatch'] +
                       self.issue_counts['resolution_mismatch'])
        print(f"[TIMING]   Issues found: {total_issues} (Outdated: {self.issue_counts['outdated']}, "
              f"FPS: {self.issue_counts['fps_mismatch']}, Frame: {self.issue_counts['frame_range_mismatch']}, "
              f"Res: {self.issue_counts['resolution_mismatch']})")
        print(f"[TIMING]   Items: {self.issue_counts['total_footage']} footage, "
              f"{self.issue_counts['total_comps']} comps")

        render_end = time.perf_counter()
        print(f"[TIMING] Total renderHierarchyTree: {render_end - render_start:.4f}s")

    @err_catcher(name=__name__)
    def _buildRenderTree(self, group, render_data):
        """Build tree for 3D and 2D renders"""
        groupItem = QTreeWidgetItem()
        groupItem.setText(0, f"📁 {group}")
        groupItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'group', 'group_name': group})

        # Set colors for different group types
        if group == "3D Renders":
            groupItem.setForeground(0, QBrush(QColor(100, 255, 150)))
        elif group == "2D Renders":
            groupItem.setForeground(0, QBrush(QColor(100, 200, 255)))
        else:
            groupItem.setForeground(0, QBrush(QColor(200, 200, 200)))

        font = groupItem.font(0)
        font.setBold(True)
        groupItem.setFont(0, font)
        self.tracker.tw_footage.addTopLevelItem(groupItem)

        # Check if render_data is valid
        if not render_data or not isinstance(render_data, dict):
            return groupItem

        # Add small toggle button on the group header row
        self._addGroupToggleButton(groupItem, group)

        # Identifier-first mode: data is already pivoted to {identifier: {shot: {aov: [footage]}}}
        mode_attr = 'group_by_mode_3d' if group == "3D Renders" else 'group_by_mode_2d'
        group_by_mode = getattr(self.tracker, mode_attr, 'shot')
        if group_by_mode == 'identifier':
            self._buildRenderTreeIdentifierFirst(groupItem, render_data, group)
            return groupItem

        for shot in sorted(render_data.keys()):
            if not shot or not isinstance(render_data[shot], dict):
                continue

            shotItem = QTreeWidgetItem()
            shotItem.setText(0, shot)
            shotItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'shot'})
            shotItem.setForeground(0, QBrush(QColor(150, 180, 255)))
            font = shotItem.font(0)
            font.setBold(True)
            shotItem.setFont(0, font)
            groupItem.addChild(shotItem)

            for identifier in sorted(render_data[shot].keys()):
                if not identifier or not isinstance(render_data[shot][identifier], dict):
                    continue

                identifier_data = render_data[shot][identifier]
                is_2d_render = (group == "2D Renders")

                # Determine if this is a Playblast or 2D Render from the path
                footage_type_prefix = ""
                if is_2d_render:
                    # Check the first footage item's path to determine type
                    for aov in sorted(identifier_data.keys()):
                        aov_data = identifier_data.get(aov, [])
                        if isinstance(aov_data, list) and aov_data:
                            first_footage = aov_data[0]
                            if isinstance(first_footage, dict) and 'path' in first_footage:
                                path_lower = first_footage['path'].lower()
                                if '/playblasts/' in path_lower:
                                    footage_type_prefix = "[PB] "
                                else:
                                    footage_type_prefix = "[2D] "
                                break

                # For 2D renders, don't create parent identifierItem - each footage creates its own item
                # For 3D renders, create the parent identifierItem
                if not is_2d_render:
                    identifierItem = QTreeWidgetItem()
                    identifierItem.setText(0, identifier or "Unknown Identifier")
                    identifierItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'identifier'})
                    identifierItem.setForeground(0, QBrush(QColor(180, 180, 220)))
                    font = identifierItem.font(0)
                    font.setBold(True)
                    identifierItem.setFont(0, font)
                    shotItem.addChild(identifierItem)

                if not isinstance(identifier_data, dict):
                    continue

                if group == "2D Renders":
                    # 2D renders: Each footage item creates its own identifier item (no parent)
                    # Track duplicates to add suffix
                    identifier_counts = {}
                    for aov in sorted(identifier_data.keys()):
                        aov_data = identifier_data.get(aov, [])
                        if not isinstance(aov_data, list):
                            continue

                        for footageData in aov_data:
                            if not isinstance(footageData, dict):
                                continue

                            # Track count for this identifier
                            if identifier not in identifier_counts:
                                identifier_counts[identifier] = 0
                            suffix = f" ({identifier_counts[identifier]})" if identifier_counts[identifier] > 0 else ""
                            identifier_counts[identifier] += 1

                            # Create a separate identifier item for each footage (to show duplicates)
                            self._render2DFootage(
                                shotItem, identifier, shot, footageData, aov, footage_type_prefix, suffix
                            )
                else:
                    # 3D renders: Shot > Identifier > AOV > Footage
                    # Track duplicates to add suffix
                    aov_counts = {}
                    for aov in sorted(identifier_data.keys()):
                        aov_data = identifier_data.get(aov, [])
                        if not isinstance(aov_data, list):
                            continue

                        for footageData in aov_data:
                            if not isinstance(footageData, dict):
                                continue

                            # Track count for this AOV
                            if aov not in aov_counts:
                                aov_counts[aov] = 0
                            suffix = f" ({aov_counts[aov]})" if aov_counts[aov] > 0 else ""
                            aov_counts[aov] += 1

                            # Pass the identifier text from parent item (e.g., "Lighting_Beauty")
                            parent_identifier = identifierItem.text(0)
                            self._render3DFootage(identifierItem, aov, footageData, shot, parent_identifier, suffix)

        return groupItem

    @err_catcher(name=__name__)
    def _addGroupToggleButton(self, groupItem, group):
        """Replace column 0 of the group header with an inline label + toggle button"""
        mode_attr = 'group_by_mode_3d' if group == "3D Renders" else 'group_by_mode_2d'
        current_mode = getattr(self.tracker, mode_attr, 'shot')
        btn_label = "By Shot" if current_mode == 'shot' else "By ID"

        text_color = "#64ff96" if group == "3D Renders" else "#64c8ff"

        lbl = QLabel(f"📁 {group}")
        font = self.tracker.tw_footage.font()
        font.setBold(True)
        lbl.setFont(font)
        lbl.setStyleSheet(f"color: {text_color}; background: transparent;")

        btn = QLabel(btn_label)
        btn.setFixedSize(52, 14)
        btn.setAlignment(Qt.AlignCenter)
        btn.setToolTip("Toggle grouping: Shot > Identifier  or  Identifier > Shot")
        btn.setStyleSheet("""
            QLabel {
                background-color: #3a3a5c;
                color: #aaaacc;
                border: 1px solid #555580;
                border-radius: 3px;
                font-size: 10px;
                padding: 0px;
            }
            QLabel:hover {
                background-color: #4a4a7c;
                color: white;
            }
        """)
        btn.mousePressEvent = lambda e, g=group: self.tracker.toggleGroupMode(g)

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setFixedHeight(20)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.addWidget(lbl)
        layout.addWidget(btn)
        layout.addStretch()

        from qtpy.QtCore import QSize
        groupItem.setSizeHint(0, QSize(0, 22))
        self.tracker.tw_footage.setItemWidget(groupItem, 0, wrapper)
        # Clear text to prevent double-rendering under the widget
        groupItem.setText(0, "")

    @err_catcher(name=__name__)
    def _buildRenderTreeIdentifierFirst(self, groupItem, render_data, group):
        """Build render tree in identifier > shot > aov order (for both 3D and 2D renders)"""
        is_2d = (group == "2D Renders")

        for identifier in sorted(render_data.keys()):
            if not identifier or not isinstance(render_data[identifier], dict):
                continue

            identifierItem = QTreeWidgetItem()
            identifierItem.setText(0, identifier)
            identifierItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'identifier'})
            identifierItem.setForeground(0, QBrush(QColor(180, 150, 255)))
            font = identifierItem.font(0)
            font.setBold(True)
            identifierItem.setFont(0, font)
            groupItem.addChild(identifierItem)

            for shot in sorted(render_data[identifier].keys()):
                shot_data = render_data[identifier][shot]
                if not isinstance(shot_data, dict):
                    continue

                if not is_2d:
                    shotItem = QTreeWidgetItem()
                    shotItem.setText(0, shot)
                    shotItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'shot'})
                    shotItem.setForeground(0, QBrush(QColor(150, 180, 255)))
                    font = shotItem.font(0)
                    font.setBold(True)
                    shotItem.setFont(0, font)
                    identifierItem.addChild(shotItem)

                item_counts = {}
                for aov in sorted(shot_data.keys()):
                    aov_data = shot_data.get(aov, [])
                    if not isinstance(aov_data, list):
                        continue
                    for footageData in aov_data:
                        if not isinstance(footageData, dict):
                            continue
                        key = aov
                        if key not in item_counts:
                            item_counts[key] = 0
                        suffix = f" ({item_counts[key]})" if item_counts[key] > 0 else ""
                        item_counts[key] += 1

                        if is_2d:
                            path_lower = footageData.get('path', '').lower()
                            footage_type_prefix = "[PB] " if '/playblasts/' in path_lower else "[2D] "
                            # Use shot name as label — identifier is already shown as parent
                            self._render2DFootage(
                                identifierItem, identifier, shot, footageData, aov,
                                footage_type_prefix, suffix, label=shot
                            )
                        else:
                            self._render3DFootage(shotItem, aov, footageData, shot, identifier, suffix)

    @err_catcher(name=__name__)
    def _render2DFootage(self, parentItem, identifier, shot, footageData, aov, footage_type_prefix="[2D] ", suffix="", label=None):
        """Render 2D footage item
        Args:
            parentItem: The parent shot item in the tree
            identifier: The identifier name (e.g., "LowRes")
            shot: The shot name this render belongs to
            footageData: The specific footage data dict to render
            aov: The AOV name
            footage_type_prefix: The prefix to add ([2D] or [PB])
            suffix: Suffix for duplicates like (1), (2), etc.
        """
        import time

        render_start = time.perf_counter()

        # Create a new identifier item for each footage (to show duplicates)
        identifierItem = QTreeWidgetItem()

        # Set identifier text with prefix and suffix
        clean_identifier = identifier
        identifierItem.setText(0, label + suffix if label is not None else footage_type_prefix + identifier + suffix)

        # Determine footage_type from prefix
        footage_type = 'playblast' if '[PB]' in footage_type_prefix else '2drender'

        # Set userData with all necessary fields for bypass functionality
        identifierItem.setData(0, Qt.UserRole, {
            'type': 'footage',
            'level': 'identifier',
            'footage_type': footage_type,
            'identifier': clean_identifier,  # Clean identifier for bypass key (e.g., "LowRes")
            'id': int(footageData['footageId']),
            'path': footageData.get('path', '')  # Add path for fallback bypass key
        })
        identifierItem.setForeground(0, QBrush(QColor(150, 150, 255)))
        font = identifierItem.font(0)
        font.setBold(True)
        identifierItem.setFont(0, font)

        parentItem.addChild(identifierItem)

        if footageData:
            # Add frame range info - Use AE data (now potentially from export JSON)
            frame_start = time.perf_counter()
            startFrame = footageData.get('startFrame', 'N/A')
            endFrame = footageData.get('endFrame', 'N/A')

            # Display the frame range
            if startFrame != 'N/A' and endFrame != 'N/A':
                try:
                    display_frame_range = f"{int(float(startFrame))}-{int(float(endFrame))}"
                except Exception:
                    display_frame_range = f"{startFrame}-{endFrame}"
            else:
                # Last resort: scan file system folder
                display_frame_range = self.utils.getFrameRangeFromFolder(footageData['path'])

            identifierItem.setText(3, display_frame_range or "N/A")
            frame_end = time.perf_counter()

            # Kitsu frame range comparison
            kitsu_shot_data = None
            if shot and shot in self.tracker.kitsuShotData:
                kitsu_shot_data = self.tracker.kitsuShotData[shot]

            if kitsu_shot_data and kitsu_shot_data.get('frameRange') and display_frame_range != "N/A":
                kitsu_frame_range = kitsu_shot_data['frameRange']
                if display_frame_range != kitsu_frame_range:
                    # Mismatch - show warning
                    identifierItem.setBackground(3, QBrush(QColor(129, 84, 32)))
                    identifierItem.setForeground(3, QBrush(QColor(255, 255, 255)))
                    identifierItem.setToolTip(3, (
                        f"Frame Range Mismatch!\n\nCurrent: {display_frame_range}"
                        f"\nShould be: {kitsu_frame_range}"
                        f"\n\nClick to change footage version or update Kitsu."
                    ))
                    # Count and store frame range mismatch
                    self.issue_counts['frame_range_mismatch'] += 1
                    self.issue_items['frame_range_mismatch'].append({
                        'name': '',  # Empty name for 2D renders
                        'comp_range': display_frame_range,
                        'kitsu_range': kitsu_frame_range,
                        'shot': shot,
                        'group': '2D Renders',
                        'original_name': footageData.get('name', 'Unknown'),
                        'identifier': clean_identifier,
                        'tree_text': footage_type_prefix + identifier + suffix  # Store tree display text for bypass key matching
                    })
                else:
                    identifierItem.setToolTip(3, f"✓ Frame range matches Kitsu: {kitsu_frame_range}")
            elif kitsu_shot_data:
                identifierItem.setToolTip(3, (
                    f"Current: {display_frame_range}\n\nKitsu data available but no frame range to compare"
                ))
            else:
                identifierItem.setToolTip(3, f"Current: {display_frame_range}\n\nNo Kitsu data found for shot: {shot}")

            # Resolution column
            res_start = time.perf_counter()
            resolution = f"{footageData.get('width', 'N/A')}x{footageData.get('height', 'N/A')}"
            identifierItem.setText(5, resolution)

            # Compare resolution with Kitsu
            if kitsu_shot_data and kitsu_shot_data.get('width') and kitsu_shot_data.get('height'):
                try:
                    footage_width = int(footageData.get('width', 0))
                    footage_height = int(footageData.get('height', 0))
                    kitsu_width = int(kitsu_shot_data['width'])
                    kitsu_height = int(kitsu_shot_data['height'])
                    kitsu_resolution = kitsu_shot_data.get('resolution', f"{kitsu_width}x{kitsu_height}")

                    if footage_width != kitsu_width or footage_height != kitsu_height:
                        identifierItem.setBackground(5, QBrush(QColor(129, 84, 32)))
                        identifierItem.setForeground(5, QBrush(QColor(255, 255, 255)))
                        identifierItem.setToolTip(5, (
                            f"Resolution Mismatch!\n\nCurrent: {resolution}"
                            f"\nShould be: {kitsu_resolution}"
                            f"\n\nFootage should match project resolution."
                        ))
                        # Count and store resolution mismatch
                        self.issue_counts['resolution_mismatch'] += 1
                        self.issue_items['resolution_mismatch'].append({
                            'name': '',  # Empty name for 2D renders
                            'current': resolution,
                            'expected': kitsu_resolution,
                            'shot': shot,
                            'group': '2D Renders',
                            'original_name': footageData.get('name', 'Unknown'),
                            'identifier': clean_identifier,
                            'tree_text': footage_type_prefix + identifier + suffix  # Store tree display text for bypass key matching
                        })
                    else:
                        identifierItem.setToolTip(5, f"✓ Resolution matches Kitsu: {kitsu_resolution}")
                except Exception:
                    identifierItem.setToolTip(5, f"Current: {resolution}\n\nError comparing with Kitsu resolution")
            elif kitsu_shot_data:
                identifierItem.setToolTip(5, (
                    f"Current: {resolution}\n\nKitsu data available but no resolution to compare"
                ))
            else:
                identifierItem.setToolTip(5, f"Current: {resolution}\n\nNo Kitsu data found for shot: {shot}")
            res_end = time.perf_counter()

            identifierItem.setText(6, footageData['path'])

            # Version widget
            version_start = time.perf_counter()
            self._createVersionWidget(identifierItem, footageData, 1)
            version_end = time.perf_counter()

            # FPS widget
            fps_start = time.perf_counter()
            self._createFPSWidget(
                identifierItem, footageData, 4, kitsu_shot_data, identifier=clean_identifier, shot=shot
            )
            fps_end = time.perf_counter()

            # Status
            status_start = time.perf_counter()
            self._setFootageStatus(identifierItem, footageData, 2, identifier=clean_identifier, shot=shot)
            status_end = time.perf_counter()

            # Check and apply bypass styling for 2D renders
            userData_2d = {
                'type': 'footage',
                'id': int(footageData['footageId']),
                'path': footageData['path'],
                'identifier': clean_identifier,  # Clean identifier for bypass key (e.g., "LowRes")
                'footage_type': footage_type,  # 'playblast' or '2drender'
                'currentVersion': footageData['versionInfo']['currentVersion'],  # Base version
                'latestVersion': footageData['versionInfo']['latestVersion']     # Base version
            }
            identifierItem.setData(0, Qt.UserRole, userData_2d)
            self._checkAndApplyBypassStyling(identifierItem, userData_2d)

            render_end = time.perf_counter()
            print(
                f"[TIMING 2D]     {footageData.get('name', 'Unknown')}: "
                f"{render_end - render_start:.4f}s "
                f"(frame: {frame_end - frame_start:.4f}s, "
                f"res: {res_end - res_start:.4f}s, "
                f"version: {version_end - version_start:.4f}s, "
                f"fps: {fps_end - fps_start:.4f}s, "
                f"status: {status_end - status_start:.4f}s)"
            )

    @err_catcher(name=__name__)
    def _render3DFootage(self, parentItem, aov, footageData, shot, parent_identifier, suffix=""):
        """Render 3D footage item
        Args:
            parentItem: The parent identifier item in the tree
            aov: The AOV name (leaf item like "beauty", "depth")
            footageData: The footage data dict
            shot: The shot name
            parent_identifier: The identifier name from parent item (e.g., "Lighting_Beauty")
            suffix: Suffix for duplicates like (1), (2), etc.
        """
        # Ensure footageData has versionInfo and fps
        if 'versionInfo' not in footageData:
            footageData['versionInfo'] = {
                'currentVersion': 'v001',
                'latestVersion': 'v001',
                'allVersions': ['v001']
            }

        if 'fps' not in footageData:
            footageData['fps'] = 25.0  # Default FPS

        item = QTreeWidgetItem()
        item.setText(0, aov + suffix)

        # OPTIMIZATION: Use AE's frame range data first (no file system scan)
        startFrame = footageData.get('startFrame', 'N/A')
        endFrame = footageData.get('endFrame', 'N/A')

        # Use AE's frame range data directly (fast - no file system access)
        if startFrame != 'N/A' and endFrame != 'N/A':
            try:
                frameRange = f"{int(float(startFrame))}-{int(float(endFrame))}"
            except Exception:
                frameRange = f"{startFrame}-{endFrame}"
        else:
            # Last resort: scan file system folder (SLOW - only if AE has no data)
            frameRange = self.utils.getFrameRangeFromFolder(footageData['path'])
        item.setText(3, frameRange)

        kitsuData = self.tracker.getKitsuDataForShot(shot)
        if kitsuData and kitsuData.get('frameRange') and frameRange != "N/A":
            kitsuFrameRange = kitsuData['frameRange']
            if frameRange != kitsuFrameRange:
                item.setBackground(3, QBrush(QColor(129, 84, 32)))
                item.setForeground(3, QBrush(QColor(255, 255, 255)))
                item.setToolTip(3, (
                    f"Frame Range Mismatch!\n\nCurrent: {frameRange}"
                    f"\nShould be: {kitsuFrameRange}"
                    f"\n\nClick to change footage version or update Kitsu."
                ))
                # Count and store frame range mismatch
                self.issue_counts['frame_range_mismatch'] += 1
                self.issue_items['frame_range_mismatch'].append({
                    'name': f"[{footageData.get('group', '')}] {footageData.get('name', 'Unknown')}",
                    'comp_range': frameRange,
                    'kitsu_range': kitsuFrameRange,
                    'shot': shot,
                    'group': footageData.get('group', ''),
                    'original_name': footageData.get('name', 'Unknown'),
                    'identifier': parent_identifier,  # Parent identifier (e.g., "Lighting_Beauty")
                    'aov': aov  # AOV name (e.g., "Z", "beauty") for individual bypass
                })
            else:
                item.setToolTip(3, f"✓ Frame range matches Kitsu: {kitsuFrameRange}")
        elif kitsuData:
            item.setToolTip(3, f"Current: {frameRange}\n\nKitsu data available but no frame range to compare")
        else:
            item.setToolTip(3, f"Current: {frameRange}\n\nNo Kitsu data found for shot: {shot}")

        # Resolution column
        resolution = f"{footageData.get('width', 'N/A')}x{footageData.get('height', 'N/A')}"
        item.setText(5, resolution)

        # Compare resolution with Kitsu
        if kitsuData and kitsuData.get('width') and kitsuData.get('height'):
            try:
                footage_width = int(footageData.get('width', 0))
                footage_height = int(footageData.get('height', 0))
                kitsu_width = int(kitsuData['width'])
                kitsu_height = int(kitsuData['height'])
                kitsu_resolution = kitsuData.get('resolution', f"{kitsu_width}x{kitsu_height}")

                if footage_width != kitsu_width or footage_height != kitsu_height:
                    item.setBackground(5, QBrush(QColor(129, 84, 32)))
                    item.setForeground(5, QBrush(QColor(255, 255, 255)))
                    item.setToolTip(5, (
                        f"Resolution Mismatch!\n\nCurrent: {resolution}"
                        f"\nShould be: {kitsu_resolution}"
                        f"\n\nFootage should match project resolution."
                    ))
                    # Count and store resolution mismatch
                    self.issue_counts['resolution_mismatch'] += 1
                    self.issue_items['resolution_mismatch'].append({
                        'name': f"[{footageData.get('group', '')}] {footageData.get('name', 'Unknown')}",
                        'current': resolution,
                        'expected': kitsu_resolution,
                        'shot': shot,
                        'group': footageData.get('group', ''),
                        'original_name': footageData.get('name', 'Unknown'),
                        'identifier': parent_identifier,  # Parent identifier (e.g., "Lighting_Beauty")
                        'aov': aov  # AOV name (e.g., "Z", "beauty") for individual bypass
                    })
                else:
                    item.setToolTip(5, f"✓ Resolution matches Kitsu: {kitsu_resolution}")
            except Exception:
                item.setToolTip(5, f"Current: {resolution}\n\nError comparing with Kitsu resolution")
        elif kitsuData:
            item.setToolTip(5, f"Current: {resolution}\n\nKitsu data available but no resolution to compare")
        else:
            item.setToolTip(5, f"Current: {resolution}\n\nNo Kitsu data found for shot: {shot}")

        item.setText(6, footageData['path'])

        userData = {
            'id': int(footageData['footageId']),
            'type': 'footage',
            'group': '3D Renders',  # Add group for render type detection
            'currentVersion': footageData['versionInfo']['currentVersion'],
            'latestVersion': footageData['versionInfo']['latestVersion'],
            'path': footageData['path'],
            'identifier': parent_identifier  # Add parent identifier for bypass key (e.g., "Lighting_Beauty")
        }
        item.setData(0, Qt.UserRole, userData)

        # Add to parent first
        parentItem.addChild(item)

        # Version widget (must be set after adding to tree)
        self._createVersionWidget(item, footageData, 1)

        # FPS widget (must be set after adding to tree)
        self._createFPSWidget(item, footageData, 4, kitsuData, identifier=parent_identifier, shot=shot)

        # Status (must be set after adding to tree)
        self._setFootageStatus(item, footageData, 2, identifier=parent_identifier, shot=shot)

        # Check and apply bypass styling
        self._checkAndApplyBypassStyling(item, userData)

    @err_catcher(name=__name__)
    def _buildCompsTree(self, comps_data):
        """Build tree for compositions with Pre-comps and Main Comps categories"""
        groupItem = QTreeWidgetItem()
        groupItem.setText(0, "📁 Comps")
        groupItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'group', 'group_name': 'Comps'})
        groupItem.setForeground(0, QBrush(QColor(255, 150, 255)))

        font = groupItem.font(0)
        font.setBold(True)
        groupItem.setFont(0, font)
        self.tracker.tw_footage.addTopLevelItem(groupItem)

        # Get current shot for Kitsu comparison
        current_shot = self.tracker.data_parser.extractCurrentShotFromProject()
        kitsu_shot_data = None
        if current_shot and current_shot in self.tracker.kitsuShotData:
            kitsu_shot_data = self.tracker.kitsuShotData[current_shot]

        for category in sorted(comps_data.keys()):
            if category not in ["Main Comps", "Pre-comps"]:
                continue

            comp_list = comps_data[category]
            if not isinstance(comp_list, list):
                continue

            # Create category item
            categoryItem = QTreeWidgetItem()
            categoryItem.setText(0, f"🎬 {category}")
            categoryItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'category', 'category': category})

            # Set different colors for categories
            if category == "Pre-comps":
                categoryItem.setForeground(0, QBrush(QColor(200, 150, 255)))
            else:
                categoryItem.setForeground(0, QBrush(QColor(255, 200, 255)))

            font = categoryItem.font(0)
            font.setBold(True)
            categoryItem.setFont(0, font)
            groupItem.addChild(categoryItem)

            # Add comps to category
            for compInfo in comp_list:
                if not isinstance(compInfo, dict):
                    continue
                self._renderCompItem(categoryItem, compInfo, kitsu_shot_data)

        return groupItem

    @err_catcher(name=__name__)
    def _renderCompItem(self, categoryItem, compInfo, kitsu_shot_data):
        """Render a single composition item"""
        # Count total comps
        self.issue_counts['total_comps'] += 1

        item = QTreeWidgetItem()
        item.setText(0, compInfo['name'])

        # Version column (column 1) - Leave empty for comps
        item.setText(1, "")

        # Status column (column 2)
        if compInfo.get('isPrecomp', False) and compInfo.get('parentComps', 'None') != 'None':
            item.setText(2, f"Used in: {compInfo['parentComps']}")
            item.setForeground(2, QBrush(QColor(150, 150, 150)))
        else:
            item.setText(2, f"Layers: {compInfo['numLayers']}")

        # Calculate frame range and FPS for Kitsu comparison
        comp_fps = float(compInfo['frameRate'])
        # Handle displayStartTime that might have unexpected format (e.g., "1220::ITEM::188")
        try:
            display_start_time = float(compInfo['displayStartTime'])
        except (ValueError, TypeError):
            # Fallback to displayStartFrame if available, otherwise 0
            display_start_time = float(compInfo.get('displayStartFrame', 0)) / comp_fps

        duration = float(compInfo['duration'])

        actual_start_frame = int(round(display_start_time * comp_fps))
        actual_end_frame = int(round((display_start_time + duration) * comp_fps - 1))

        # Resolution column (column 5) - will be set as widget below
        # No direct setText here - widget handles it

        # Path column (column 6) - Leave empty for comps
        item.setText(6, "")

        # Store comp data
        userData = {
            'id': int(compInfo['compId']),
            'type': 'comp',
            'compName': compInfo['name'],  # Add compName for bypass key generation
            'name': compInfo['name'],  # Also add 'name' as backup
            'category': compInfo['category'],
            'isPrecomp': compInfo.get('isPrecomp', False),
            'parentComps': compInfo.get('parentComps', 'None'),
            'width': compInfo['width'],
            'height': compInfo['height'],
            'duration': compInfo['duration'],
            'pixelAspect': compInfo['pixelAspect'],
            'frameRate': compInfo['frameRate'],
            'displayStartFrame': compInfo['displayStartFrame'],
            'workAreaStart': compInfo['workAreaStart'],
            'workAreaDuration': compInfo['workAreaDuration'],
            'numLayers': compInfo['numLayers']
        }
        item.setData(0, Qt.UserRole, userData)
        categoryItem.addChild(item)

        # Frame Range widget (column 3) - Must be added AFTER item is added to tree
        self._createCompFrameRangeWidget(item, compInfo, 3, kitsu_shot_data)

        # FPS widget (column 4) - Must be added AFTER item is added to tree
        self._createCompFPSWidget(item, compInfo, 4)

        # Resolution widget (column 5) - Must be added AFTER item is added to tree
        self._createCompResolutionWidget(item, compInfo, 5, kitsu_shot_data)

        # Compare FPS, Frame Range, and Resolution with Kitsu and set mismatch styling
        if kitsu_shot_data:
            self._compareCompWithKitsu(item, compInfo, kitsu_shot_data, actual_start_frame, actual_end_frame, comp_fps)

        # Check and apply bypass styling
        self._checkAndApplyBypassStyling(item, userData)

    @err_catcher(name=__name__)
    def _compareCompWithKitsu(self, item, compInfo, kitsu_shot_data, actual_start_frame, actual_end_frame, comp_fps):
        """Compare comp data with Kitsu data and highlight mismatches on widgets"""
        comp_name = compInfo['name']
        # Get current shot for logging
        current_shot = self.tracker.data_parser.extractCurrentShotFromProject()

        kitsu_fps = kitsu_shot_data.get('fps')
        kitsu_frame_range = kitsu_shot_data.get('frameRange')
        kitsu_width = kitsu_shot_data.get('width')
        kitsu_height = kitsu_shot_data.get('height')

        orange_color = QColor(129, 84, 32)
        white_color = QColor(255, 255, 255)

        # Get the widget labels for FPS (column 4), Frame Range (column 3), and Resolution (column 5)
        fps_widget = self.tracker.tw_footage.itemWidget(item, 4)
        frame_widget = self.tracker.tw_footage.itemWidget(item, 3)
        resolution_widget = self.tracker.tw_footage.itemWidget(item, 5)

        fps_label = None
        frame_label = None
        resolution_label = None
        if fps_widget:
            fps_label = fps_widget.findChild(QLabel)
        if frame_widget:
            frame_label = frame_widget.findChild(QLabel)
        if resolution_widget:
            resolution_label = resolution_widget.findChild(QLabel)

        # Compare FPS
        if kitsu_fps and fps_label:
            if abs(comp_fps - float(kitsu_fps)) > 0.01:
                # Set item background/foreground (for the cell itself)
                item.setBackground(4, QBrush(orange_color))
                item.setForeground(4, QBrush(white_color))
                # Set label tooltip
                fps_label.setToolTip(
                    f"FPS Mismatch!\n\nCurrent: {comp_fps:.2f}"
                    f"\nShould be: {kitsu_fps}"
                    f"\n\nDouble-click to edit or Ctrl+Click to bypass."
                )
                # Count and store FPS mismatch for comps
                self.issue_counts['fps_mismatch'] += 1
                self.issue_items['fps_mismatch'].append({
                    'name': f"[Comp] {comp_name}",
                    'footage_fps': comp_fps,
                    'project_fps': float(kitsu_fps),
                    'path': f"Composition: {comp_name}",
                    'comp_id': compInfo.get('compId'),
                    'comp_name': comp_name,
                    'group': 'Comps',
                    'original_name': comp_name,
                    'shot': current_shot
                })
            else:
                fps_label.setToolTip(f"✓ FPS matches Kitsu: {kitsu_fps}\n\nDouble-click to edit.")
        elif fps_label:
            fps_label.setToolTip(f"Current: {comp_fps:.2f} fps\n\nNo Kitsu FPS data available\n\nDouble-click to edit.")

        # Compare frame range
        if kitsu_frame_range and frame_label:
            try:
                kitsu_start, kitsu_end = map(int, kitsu_frame_range.split('-'))
                if actual_start_frame != kitsu_start or actual_end_frame != kitsu_end:
                    # Set item background/foreground (for the cell itself)
                    item.setBackground(3, QBrush(orange_color))
                    item.setForeground(3, QBrush(white_color))
                    # Set label tooltip
                    frame_label.setToolTip(
                        f"Frame Range Mismatch!\n\nCurrent: {actual_start_frame}-{actual_end_frame}"
                        f"\nShould be: {kitsu_frame_range}"
                        f"\n\nDouble-click to edit or Ctrl+Click to bypass."
                    )
                    # Count and store frame range mismatch for comps
                    self.issue_counts['frame_range_mismatch'] += 1
                    self.issue_items['frame_range_mismatch'].append({
                        'name': f"[Comp] {comp_name}",
                        'comp_range': f"{actual_start_frame}-{actual_end_frame}",
                        'kitsu_range': kitsu_frame_range,
                        'shot': current_shot,
                        'comp_id': compInfo.get('compId'),
                        'comp_name': comp_name,
                        'kitsu_start': kitsu_start,
                        'kitsu_end': kitsu_end,
                        'group': 'Comps',
                        'original_name': comp_name
                    })
                else:
                    frame_label.setToolTip(f"✓ Frame range matches Kitsu: {kitsu_frame_range}\n\nDouble-click to edit.")
            except Exception:
                frame_label.setToolTip(
                    f"Current: {actual_start_frame}-{actual_end_frame}"
                    f"\n\nError parsing Kitsu frame range: {kitsu_frame_range}"
                    f"\n\nDouble-click to edit."
                )
        elif frame_label:
            frame_label.setToolTip(
                f"Current: {actual_start_frame}-{actual_end_frame}"
                f"\n\nNo Kitsu frame range data available\n\nDouble-click to edit."
            )

        # Compare resolution
        if kitsu_width and kitsu_height and resolution_label:
            try:
                comp_width = int(compInfo.get('width', 0))
                comp_height = int(compInfo.get('height', 0))
                kitsu_width_int = int(kitsu_width)
                kitsu_height_int = int(kitsu_height)
                comp_resolution = f"{comp_width}x{comp_height}"
                kitsu_resolution = f"{kitsu_width_int}x{kitsu_height_int}"

                if comp_width != kitsu_width_int or comp_height != kitsu_height_int:
                    # Set item background/foreground (for the cell itself)
                    item.setBackground(5, QBrush(orange_color))
                    item.setForeground(5, QBrush(white_color))
                    # Set label tooltip
                    resolution_label.setToolTip(
                        f"Resolution Mismatch!\n\nCurrent: {comp_resolution}"
                        f"\nShould be: {kitsu_resolution}"
                        f"\n\nDouble-click to edit or Ctrl+Click to bypass."
                    )
                    # Count and store resolution mismatch for comps
                    self.issue_counts['resolution_mismatch'] += 1
                    self.issue_items['resolution_mismatch'].append({
                        'name': f"[Comp] {comp_name}",
                        'current': comp_resolution,
                        'expected': kitsu_resolution,
                        'shot': current_shot,
                        'group': 'Comps',
                        'original_name': comp_name,
                        'comp_id': compInfo.get('compId'),
                        'comp_name': comp_name
                    })
                else:
                    resolution_label.setToolTip(
                        f"\u2713 Resolution matches Kitsu: {kitsu_resolution}\n\nDouble-click to edit."
                    )
            except Exception:
                resolution_label.setToolTip(
                    f"Current: {comp_width}x{comp_height}"
                    f"\n\nError comparing with Kitsu resolution\n\nDouble-click to edit."
                )
        elif resolution_label:
            comp_width = compInfo.get('width', 'N/A')
            comp_height = compInfo.get('height', 'N/A')
            if kitsu_shot_data:
                resolution_label.setToolTip(
                    f"Current: {comp_width}x{comp_height}"
                    f"\n\nKitsu data available but no resolution to compare\n\nDouble-click to edit."
                )
            else:
                resolution_label.setToolTip(
                    f"Current: {comp_width}x{comp_height}"
                    f"\n\nNo Kitsu data available for comparison\n\nDouble-click to edit."
                )

    @err_catcher(name=__name__)
    def _createVersionWidget(self, item, footageData, column):
        """Create version selection widget"""
        # Check if versionInfo exists and has the expected structure
        versionInfo = footageData.get('versionInfo', {})
        if not versionInfo or 'allVersions' not in versionInfo:
            # Create a simple text display if version info is missing
            versionWidget = QWidget()
            versionLayout = QHBoxLayout(versionWidget)
            versionLayout.setContentsMargins(2, 2, 2, 2)
            versionLabel = QLabel(versionInfo.get('currentVersion', 'N/A'))
            versionLayout.addWidget(versionLabel)
            self.tracker.tw_footage.setItemWidget(item, column, versionWidget)
            return

        versionWidget = QWidget()
        versionLayout = QHBoxLayout(versionWidget)
        versionLayout.setContentsMargins(2, 2, 2, 2)
        versionCombo = QComboBox()
        # Disable mouse wheel to prevent accidental version changes
        versionCombo.setFocusPolicy(Qt.ClickFocus)

        # Completely disable wheel events on the combo box
        def disable_wheel_event(event):
            # Ignore wheel events
            event.ignore()
        versionCombo.wheelEvent = disable_wheel_event

        # Ensure allVersions is a list
        allVersions = versionInfo.get('allVersions', [])
        if isinstance(allVersions, str):
            allVersions = [allVersions]
        elif not isinstance(allVersions, list):
            allVersions = [str(allVersions)]

        versionCombo.addItems(allVersions)
        # Use currentVersionFull for dropdown selection (has suffix like "v0003 (mp4)")
        currentVersionFull = versionInfo.get('currentVersionFull', versionInfo.get('currentVersion', ''))
        if currentVersionFull in allVersions:
            versionCombo.setCurrentText(currentVersionFull)
        elif allVersions:
            versionCombo.setCurrentText(allVersions[0])

        # Get identifier from item's userData if available (for bypass functionality)
        itemUserData = item.data(0, Qt.UserRole) or {}
        item_identifier = itemUserData.get('identifier', '')

        userData = {
            'id': int(footageData['footageId']),
            'type': 'footage',
            'currentVersion': footageData['versionInfo']['currentVersion'],  # Base version for status check
            'latestVersion': footageData['versionInfo']['latestVersion'],    # Base version for comparison
            'currentVersionFull': versionInfo.get('currentVersionFull', currentVersionFull),  # Full ver for switching
            'path': footageData['path'],
            'identifier': item_identifier  # Include identifier for bypass key generation
        }

        versionCombo.currentTextChanged.connect(
            lambda ver, it=item, ud=userData: self.tracker.updateFootageVersion(it, ver, ud)
        )
        versionLayout.addWidget(versionCombo)
        self.tracker.tw_footage.setItemWidget(item, column, versionWidget)

    @err_catcher(name=__name__)
    def _createFPSWidget(self, item, footageData, column, kitsuData=None, identifier=None, shot=None):
        """Create FPS display widget - uses QLabel for display, shows spinbox on double-click
        Args:
            identifier: Optional AOV name for 2D/3D renders (e.g., "LowRes", "beauty")
            shot: The shot name this footage belongs to (for 2D renders)"""
        fpsWidget = QWidget()
        fpsLayout = QHBoxLayout(fpsWidget)
        fpsLayout.setContentsMargins(0, 0, 0, 0)

        # Create a label for display instead of spinbox (prevents single-click focus issue)
        fpsLabel = QLabel()
        fpsLabel.setAlignment(Qt.AlignCenter)

        try:
            fpsValue = float(footageData['fps'])
            fpsLabel.setText(f"{fpsValue:.2f}")
        except Exception:
            fpsLabel.setText("25.00")

        userData = {
            'id': int(footageData['footageId']),
            'type': 'footage',
            'currentVersion': footageData['versionInfo']['currentVersion'],
            'latestVersion': footageData['versionInfo']['latestVersion'],
            'path': footageData['path']
        }

        # Store spinbox reference for double-click handler
        fpsLabel.setProperty("footageData", footageData)
        fpsLabel.setProperty("userData", userData)
        fpsLabel.setProperty("item", item)

        # Create double-click handler to show spinbox
        def showFPSInputDialog(event):
            from qtpy.QtWidgets import QInputDialog
            currentFPS = fpsLabel.text()
            newFPS, ok = QInputDialog.getDouble(
                None,
                "Edit FPS",
                "Enter new FPS value:",
                float(currentFPS),
                1.0,
                240.0,
                2
            )
            if ok:
                self.tracker.updateFootageFPS(item, newFPS, userData)

        # Override mouseDoubleClickEvent on the label
        original_mouseDoubleClickEvent = fpsLabel.mouseDoubleClickEvent
        fpsLabel.mouseDoubleClickEvent = showFPSInputDialog

        fpsLabel.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
                color: white;
                padding: 2px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

        fpsLayout.addWidget(fpsLabel)
        self.tracker.tw_footage.setItemWidget(item, column, fpsWidget)
        # Install event filter on the label to catch Ctrl+Click for bypass
        fpsLabel.installEventFilter(self.tracker.tree_ops)

        # Compare with Kitsu data if available
        if kitsuData and kitsuData.get('fps'):
            try:
                currentFps = float(footageData['fps'])
                kitsuFps = float(kitsuData['fps'])
                if abs(currentFps - kitsuFps) > 0.01:
                    item.setBackground(column, QBrush(QColor(129, 84, 32)))
                    item.setForeground(column, QBrush(QColor(255, 255, 255)))
                    fpsLabel.setToolTip(
                        f"FPS Mismatch!\n\nCurrent: {currentFps:.2f} fps"
                        f"\nShould be: {kitsuFps:.2f} fps"
                        f"\n\nDouble-click to edit or Ctrl+Click to bypass."
                    )
                    # Count and store FPS mismatch
                    self.issue_counts['fps_mismatch'] += 1
                    # Get project FPS from config
                    project_fps = 25.0
                    try:
                        fps_config = self.core.getConfig("globals", "fps", config="project")
                        if fps_config:
                            project_fps = float(fps_config)
                    except Exception:
                        pass
                    self.issue_items['fps_mismatch'].append({
                        'name': ('' if footageData.get('group') == '2D Renders'
                                 else f"[{footageData.get('group', '')}] {footageData.get('name', 'Unknown')}"),
                        'footage_fps': currentFps,
                        'project_fps': kitsuFps,  # Use Kitsu FPS as expected
                        'path': footageData.get('path', ''),
                        'group': footageData.get('group', ''),
                        'original_name': footageData.get('name', 'Unknown'),
                        'shot': shot or footageData.get('shotName', ''),  # Use passed shot or fallback to footageData
                        'identifier': identifier or footageData.get('identifier', ''),  # Parent identifier
                        # Only AOV for 3D renders
                        'aov': item.text(0) if (identifier and footageData.get('group') == '3D Renders') else '',
                        # Store tree display text for 2D renders to match bypass keys
                        'tree_text': item.text(0) if footageData.get('group') == '2D Renders' else ''
                    })
                else:
                    fpsLabel.setToolTip(f"✓ FPS matches Kitsu project: {kitsuFps:.2f} fps\n\nDouble-click to edit.")
            except Exception:
                fpsLabel.setToolTip(f"Current: {footageData['fps']} fps")
        else:
            try:
                fpsLabel.setToolTip(
                    f"Current: {float(footageData['fps']):.2f} fps"
                    f"\n\nNo Kitsu FPS data available for comparison\n\nDouble-click to edit."
                )
            except Exception:
                fpsLabel.setToolTip(f"Current: {footageData['fps']} fps")

    @err_catcher(name=__name__)
    def _setFootageStatus(self, item, footageData, column, identifier=None, shot=None):
        """Set the status indicator for footage
        Args:
            identifier: Optional AOV name for 2D/3D renders (e.g., "LowRes", "beauty")
            shot: The shot name this footage belongs to (for 2D renders)"""
        if footageData.get('isLatest', False):
            item.setText(column, "✓ Up to date")
            item.setForeground(column, QBrush(QColor(100, 200, 100)))
            item.setData(column, Qt.UserRole + 1, "current")
        else:
            item.setText(column, "⚠ Outdated")
            # Use same orange background as other columns (RGB 129, 84, 32)
            item.setBackground(column, QBrush(QColor(129, 84, 32)))
            item.setForeground(column, QBrush(QColor(255, 255, 255)))
            item.setData(column, Qt.UserRole + 1, "outdated")
            # Count and store outdated footage
            self.issue_counts['outdated'] += 1
            version_info = footageData.get('versionInfo', {})
            self.issue_items['outdated'].append({
                'name': '' if footageData.get('group') == '2D Renders' else footageData.get('name', 'Unknown'),
                'current': version_info.get('currentVersion', 'v001'),
                'latest': version_info.get('latestVersion', 'v001'),
                'path': footageData.get('path', ''),
                'group': footageData.get('group', ''),
                'shot': shot or footageData.get('shotName', ''),  # Use passed shot or fallback to footageData
                'original_name': footageData.get('name', 'Unknown'),
                'identifier': identifier or footageData.get('identifier', ''),  # Parent identifier
                # Only AOV for 3D renders
                'aov': item.text(0) if (identifier and footageData.get('group') == '3D Renders') else '',
                # Store tree display text for 2D renders to match bypass keys
                'tree_text': item.text(0) if footageData.get('group') == '2D Renders' else ''
            })
        self.issue_counts['total_footage'] += 1

    @err_catcher(name=__name__)
    def _createCompFPSWidget(self, item, compInfo, column):
        """Create FPS display widget for compositions - uses QLabel for display, shows dialog on double-click"""
        fpsWidget = QWidget()
        fpsLayout = QHBoxLayout(fpsWidget)
        fpsLayout.setContentsMargins(0, 0, 0, 0)

        # Create a label for display with center alignment (like footage items)
        fpsLabel = QLabel()
        fpsLabel.setAlignment(Qt.AlignCenter)

        try:
            fpsValue = float(compInfo['frameRate'])
            fpsLabel.setText(f"{fpsValue:.2f}")
        except Exception:
            fpsLabel.setText("25.00")

        # Store comp data for double-click handler
        fpsLabel.setProperty("compInfo", compInfo)
        fpsLabel.setProperty("item", item)

        # Create double-click handler to show FPS input dialog
        def showFPSInputDialog(event):
            from qtpy.QtWidgets import QInputDialog
            currentFPS = fpsLabel.text()
            newFPS, ok = QInputDialog.getDouble(
                None,
                "Edit Comp FPS",
                "Enter new FPS value:",
                float(currentFPS),
                1.0,
                240.0,
                2
            )
            if ok:
                self.tracker.updateCompFPS(item, newFPS, compInfo)

        # Override mouseDoubleClickEvent on the label
        fpsLabel.mouseDoubleClickEvent = showFPSInputDialog

        fpsLabel.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
                color: white;
                padding: 2px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

        fpsLayout.addWidget(fpsLabel)
        self.tracker.tw_footage.setItemWidget(item, column, fpsWidget)

    @err_catcher(name=__name__)
    def _createCompFrameRangeWidget(self, item, compInfo, column, kitsu_shot_data=None):
        """Create Frame Range display widget for compositions - uses QLabel for display, shows dialog on double-click"""
        frameRangeWidget = QWidget()
        frameRangeLayout = QHBoxLayout(frameRangeWidget)
        frameRangeLayout.setContentsMargins(0, 0, 0, 0)

        # Create a label for display with center alignment (like footage items)
        frameRangeLabel = QLabel()
        frameRangeLabel.setAlignment(Qt.AlignCenter)

        # Calculate frame range using the exact formula from AE
        comp_fps = float(compInfo['frameRate'])
        # Handle displayStartTime that might have unexpected format
        try:
            display_start_time = float(compInfo['displayStartTime'])
        except (ValueError, TypeError):
            display_start_time = float(compInfo.get('displayStartFrame', 0)) / comp_fps

        duration = float(compInfo['duration'])

        actual_start_frame = int(round(display_start_time * comp_fps))
        actual_end_frame = int(round((display_start_time + duration) * comp_fps - 1))

        frame_range = f"{actual_start_frame}-{actual_end_frame}"
        frameRangeLabel.setText(frame_range)

        # Store comp data for double-click handler
        frameRangeLabel.setProperty("compInfo", compInfo)
        frameRangeLabel.setProperty("item", item)
        frameRangeLabel.setProperty("kitsuData", kitsu_shot_data)

        # Create double-click handler to show frame range input dialog
        def showFrameRangeInputDialog(event):
            from qtpy.QtWidgets import QInputDialog
            currentRange = frameRangeLabel.text()
            newRange, ok = QInputDialog.getText(
                None,
                "Edit Comp Frame Range",
                "Enter new frame range (e.g., 1001-1050):",
                text=currentRange
            )
            if ok:
                # Validate format
                try:
                    parts = newRange.split('-')
                    if len(parts) == 2:
                        startFrame = int(parts[0])
                        endFrame = int(parts[1])
                        self.tracker.updateCompFrameRange(item, startFrame, endFrame, compInfo)
                except Exception:
                    pass

        # Override mouseDoubleClickEvent on the label
        frameRangeLabel.mouseDoubleClickEvent = showFrameRangeInputDialog

        frameRangeLabel.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
                color: white;
                padding: 2px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

        frameRangeLayout.addWidget(frameRangeLabel)
        self.tracker.tw_footage.setItemWidget(item, column, frameRangeWidget)

    @err_catcher(name=__name__)
    def _createCompResolutionWidget(self, item, compInfo, column, kitsu_shot_data=None):
        """Create Resolution display widget for compositions - uses QLabel for display, shows dialog on double-click"""
        resolutionWidget = QWidget()
        resolutionLayout = QHBoxLayout(resolutionWidget)
        resolutionLayout.setContentsMargins(0, 0, 0, 0)

        # Create a label for display with center alignment
        resolutionLabel = QLabel()
        resolutionLabel.setAlignment(Qt.AlignCenter)

        resolution = f"{compInfo.get('width', 'N/A')}x{compInfo.get('height', 'N/A')}"
        resolutionLabel.setText(resolution)

        # Store comp data for double-click handler
        resolutionLabel.setProperty("compInfo", compInfo)
        resolutionLabel.setProperty("item", item)
        resolutionLabel.setProperty("kitsuData", kitsu_shot_data)

        # Create double-click handler to show resolution input dialog
        def showResolutionInputDialog(event):
            from qtpy.QtWidgets import QInputDialog
            currentRes = resolutionLabel.text()
            newRes, ok = QInputDialog.getText(
                None,
                "Edit Comp Resolution",
                "Enter new resolution (e.g., 1920x1080):",
                text=currentRes
            )
            if ok:
                # Validate format
                try:
                    parts = newRes.lower().split('x')
                    if len(parts) == 2:
                        width = int(parts[0])
                        height = int(parts[1])
                        self.tracker.updateCompResolution(item, width, height, compInfo)
                except Exception:
                    pass

        # Override mouseDoubleClickEvent on the label
        resolutionLabel.mouseDoubleClickEvent = showResolutionInputDialog

        resolutionLabel.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border: none;
                color: white;
                padding: 2px;
            }
            QLabel:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)

        resolutionLayout.addWidget(resolutionLabel)
        self.tracker.tw_footage.setItemWidget(item, column, resolutionWidget)

    @err_catcher(name=__name__)
    def _buildPreservedStructureTree(self, group, preserved_data):
        """Build tree maintaining original folder structure for Resources and External"""
        groupItem = QTreeWidgetItem()
        groupItem.setText(0, f"📁 {group}")
        groupItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'group', 'group_name': group})

        # Set colors for different group types
        if group == "External":
            groupItem.setForeground(0, QBrush(QColor(255, 200, 100)))
        else:  # Resources
            groupItem.setForeground(0, QBrush(QColor(200, 200, 200)))

        font = groupItem.font(0)
        font.setBold(True)
        groupItem.setFont(0, font)
        self.tracker.tw_footage.addTopLevelItem(groupItem)

        # Process preserved data (relative paths)
        for relative_path in sorted(preserved_data.keys()):
            footage_list = preserved_data[relative_path]
            if not isinstance(footage_list, list):
                continue

            # Create path parts from relative_path
            path_parts = relative_path.split('/')
            current_parent = groupItem

            # Build folder structure
            for i, part in enumerate(path_parts[:-1]):  # Exclude filename
                # Find existing child or create new
                found = False
                for j in range(current_parent.childCount()):
                    child = current_parent.child(j)
                    if child.text(0) == part:
                        current_parent = child
                        found = True
                        break
                if not found:
                    folderItem = QTreeWidgetItem()
                    folderItem.setText(0, part)
                    folderItem.setData(0, Qt.UserRole, {'type': 'folder', 'path': '/'.join(path_parts[:i+1])})
                    folderItem.setForeground(0, QBrush(QColor(160, 160, 160)))
                    current_parent.addChild(folderItem)
                    current_parent = folderItem

            # Add footage items
            for footageData in footage_list:
                if not isinstance(footageData, dict):
                    continue

                item = QTreeWidgetItem()
                item.setText(0, footageData['name'])

                # OPTIMIZATION: Use AE's frame range data first (no file system scan)
                startFrame = footageData.get('startFrame', 'N/A')
                endFrame = footageData.get('endFrame', 'N/A')

                # Use AE's frame range data directly (fast - no file system access)
                if startFrame != 'N/A' and endFrame != 'N/A':
                    try:
                        frameRange = f"{int(float(startFrame))}-{int(float(endFrame))}"
                    except Exception:
                        frameRange = f"{startFrame}-{endFrame}"
                else:
                    # Last resort: scan file system folder (SLOW - only if AE has no data)
                    frameRange = self.utils.getFrameRangeFromFolder(footageData['path'])
                item.setText(3, frameRange)

                resolution = f"{footageData.get('width', 'N/A')}x{footageData.get('height', 'N/A')}"
                item.setText(5, resolution)
                item.setText(6, footageData['path'])

                userData = {
                    'id': int(footageData['footageId']),
                    'type': 'footage',
                    'currentVersion': footageData['versionInfo']['currentVersion'],
                    'latestVersion': footageData['versionInfo']['latestVersion'],
                    'path': footageData['path']
                }
                item.setData(0, Qt.UserRole, userData)

                # Status for preserved items
                if footageData.get('isLatest', False):
                    item.setText(2, "✓ Current")
                    item.setForeground(2, QBrush(QColor(100, 200, 100)))
                    item.setData(2, Qt.UserRole + 1, "current")
                else:
                    item.setText(2, "⚠ Version Available")
                    item.setForeground(2, QBrush(QColor(255, 200, 100)))
                    item.setData(2, Qt.UserRole + 1, "version_available")
                    # Count and store outdated footage for preserved items
                    self.issue_counts['outdated'] += 1
                    version_info = footageData.get('versionInfo', {})
                    self.issue_items['outdated'].append({
                        'name': footageData.get('name', 'Unknown'),
                        'current': version_info.get('currentVersion', 'v001'),
                        'latest': version_info.get('latestVersion', 'v001'),
                        'path': footageData.get('path', ''),
                        'group': footageData.get('group', ''),
                        'shot': footageData.get('shotName', ''),
                        'original_name': footageData.get('name', 'Unknown')
                    })
                self.issue_counts['total_footage'] += 1

                current_parent.addChild(item)

                # Check and apply bypass styling
                self._checkAndApplyBypassStyling(item, userData)

        return groupItem
    def _checkAndApplyBypassStyling(self, item, userData):
        """Check if item is bypassed and apply blue styling"""
        import json

        # Get bypassed items from .aep XMP metadata
        bypassed_items_config = self._getBypassedItemsFromXMP()

        # Convert lists back to sets for easier checking
        bypassed_items = {}
        for key, value in bypassed_items_config.items():
            bypassed_items[key] = set(value)

        # Track all bypassed columns for this item (can have multiple)
        bypassed_columns = []

        if userData.get('type') == 'footage':
            # Generate item_key based on shot/identifier/aov (not version-specific)
            # Get shot name from tree hierarchy
            shot_name = self.tracker.getShotNameFromItem(item)

            # Get identifier from userData
            identifier = userData.get('identifier', '')

            # Check if this is a 3D render (has identifier which is the parent identifier)
            # For 2D renders, identifier exists but item.text(0) includes prefix like "[2D] LowRes"
            # So we need to check if item.text(0) starts with a 2D render prefix
            item_text = item.text(0)
            is_2d_render = (item_text.startswith('[2D]') or item_text.startswith('[PB]'))
            is_3d_render = identifier and not is_2d_render and identifier != item_text

            # For 3D renders, include AOV in key for individual AOV bypass
            if is_3d_render:
                aov = item_text  # AOV name (e.g., "Z", "beauty")
            else:
                # For 2D renders and others: no AOV
                aov = ''
                # For 2D renders, extract duplicate suffix from item text if present
                # e.g., "[2D] LowRes (1)" -> identifier should become "LowRes (1)" for unique bypass
                if is_2d_render and identifier:
                    # Extract suffix from item text (e.g., " (1)" from "[2D] LowRes (1)")
                    # Remove the prefix to get "LowRes (1)" then extract just the suffix
                    text_without_prefix = item_text.replace('[2D] ', '').replace('[PB] ', '')
                    if text_without_prefix != identifier:
                        # There's a duplicate suffix
                        suffix = text_without_prefix.replace(identifier, '', 1).strip()
                        if suffix:
                            identifier = f"{identifier} {suffix}"
                if not identifier:
                    identifier = item_text

            # Generate key based on shot/identifier/aov (not version-specific)
            if shot_name and identifier:
                if aov:
                    # 3D render: include AOV for individual bypass
                    item_key = f"footage_{shot_name}_{identifier}_{aov}"
                else:
                    # 2D render: no AOV
                    item_key = f"footage_{shot_name}_{identifier}"
            else:
                # Fallback to path if hierarchy info not available
                item_key = f"footage_{userData.get('path', '')}"

            print(
                f"[DEBUG STYLING] Checking footage bypass for item: {item.text(0)}, "
                f"shot_name: {shot_name}, identifier: {identifier}, aov: {aov}, item_key: {item_key}"
            )
            # Check each issue type - collect ALL bypassed columns
            for issue_type in ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']:
                if item_key in bypassed_items.get(issue_type, set()):
                    print(f"[DEBUG STYLING] FOUND bypassed for issue_type: {issue_type}")
                    # Map issue type to column
                    if issue_type == 'outdated':
                        bypassed_columns.append(2)
                    elif issue_type == 'frame_range_mismatch':
                        bypassed_columns.append(3)
                    elif issue_type == 'fps_mismatch':
                        bypassed_columns.append(4)
                    elif issue_type == 'resolution_mismatch':
                        bypassed_columns.append(5)
            print(f"[DEBUG STYLING] Result - bypassed_columns: {bypassed_columns}")

        elif userData.get('type') == 'comp':
            comp_name = userData.get('compName', userData.get('name', ''))
            item_key = f"comp_{userData.get('id')}_{comp_name}"
            print(
                f"[DEBUG STYLING] Checking comp bypass for item: {item.text(0)}, "
                f"comp_name: {comp_name}, comp_id: {userData.get('id')}, item_key: {item_key}"
            )
            # Debug: show what bypassed keys exist for comps
            for issue_type in ['fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']:
                comp_keys = [k for k in bypassed_items.get(issue_type, set()) if k.startswith('comp_')]
                if comp_keys:
                    print(f"[DEBUG STYLING] Existing bypassed comp keys for {issue_type}: {comp_keys}")
            # Check each issue type - collect ALL bypassed columns
            for issue_type in ['fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']:
                if item_key in bypassed_items.get(issue_type, set()):
                    print(f"[DEBUG STYLING] FOUND bypassed for issue_type: {issue_type}")
                    # Map issue type to column
                    if issue_type == 'frame_range_mismatch':
                        bypassed_columns.append(3)
                    elif issue_type == 'fps_mismatch':
                        bypassed_columns.append(4)
                    elif issue_type == 'resolution_mismatch':
                        bypassed_columns.append(5)
            print(f"[DEBUG STYLING] Result - bypassed_columns: {bypassed_columns}")

        # Apply blue bypass styling to all bypassed columns
        if bypassed_columns:
            blue_color = QColor(50, 80, 130)  # Desaturated blue (similar saturation to orange RGB 129, 84, 32)
            white_color = QColor(255, 255, 255)
            for bypassed_column in bypassed_columns:
                item.setBackground(bypassed_column, QBrush(blue_color))
                item.setForeground(bypassed_column, QBrush(white_color))

                # Also apply to cell widget if it exists (for FPS label in 2D renders)
                cell_widget = self.tracker.tw_footage.itemWidget(item, bypassed_column)
                if cell_widget:
                    # Find the label within the widget
                    label = None
                    if isinstance(cell_widget, QLabel):
                        label = cell_widget
                    else:
                        # Search for QLabel in the widget's layout
                        for child in cell_widget.findChildren(QLabel):
                            label = child
                            break

                    if label:
                        label.setStyleSheet(f"""
                            QLabel {{
                                background-color: rgb({blue_color.red()}, {blue_color.green()}, {blue_color.blue()});
                                color: rgb({white_color.red()}, {white_color.green()}, {white_color.blue()});
                                border: none;
                                padding: 2px;
                            }}
                        """)

        return bool(bypassed_columns)

    def _getBypassedItemsFromXMP(self):
        """Get bypassed items from .aep file XMP metadata"""
        import json

        try:
            # Read XMP metadata from the project
            scpt = """
            if (app.project && app.project.xmpPacket) {
                app.project.xmpPacket;
            } else {
                '';
            }
            """
            result = self.tracker.main.ae_core.executeAppleScript(scpt)
            if result and isinstance(result, bytes):
                result = result.decode('utf-8')

            if result and 'PrismFootageTracker:BypassedItems' in result:
                # Extract the JSON data between the tags
                start_marker = 'PrismFootageTracker:BypassedItems">'
                end_marker = '</rdf:li'

                start_idx = result.find(start_marker)
                if start_idx > 0:
                    start_idx += len(start_marker)
                    end_idx = result.find(end_marker, start_idx)
                    if end_idx > start_idx:
                        json_str = result[start_idx:end_idx].strip()
                        bypassed = json.loads(json_str)
                        print(f"[DEBUG XMP STYLING] Loaded bypassed items from .aep XMP")
                        return bypassed
        except Exception as e:
            print(f"[DEBUG XMP STYLING] Error reading XMP: {e}")

        # Fallback: Try sidecar file (migration)
        import os
        current_file = None
        try:
            current_file = self.core.getCurrentFileName()
            if current_file and isinstance(current_file, bytes):
                current_file = current_file.decode('utf-8')
        except Exception:
            pass

        if current_file and current_file.endswith('.aep'):
            bypassed_file = os.path.splitext(current_file)[0] + '_bypassed.json'
            if os.path.exists(bypassed_file):
                try:
                    with open(bypassed_file, 'r') as f:
                        bypassed = json.load(f)
                    print(f"[DEBUG XMP STYLING] Loaded from sidecar (migration)")
                    return bypassed
                except Exception:
                    pass

        # Fallback: Project config
        bypassed = self.core.getConfig("footage_tracker", "bypassed_items", config="project")
        if bypassed:
            return bypassed

        return {}
