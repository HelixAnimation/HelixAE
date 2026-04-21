# -*- coding: utf-8 -*-
"""
Tree Operations Core Module
Handles core tree widget operations (expansion, selection, event filtering)
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class CircularMenu(QDialog):
    """5-slice pie menu with filter commands"""

    def __init__(self, parent=None, on_expand=None, on_collapse=None, on_kitsu=None, on_footage=None,
                 on_all=None,
                 on_filter_fps=None, on_filter_framerange=None, on_filter_resolution=None, on_filter_outdated=None,
                 theme_color=None):
        super().__init__(parent)

        # Callbacks
        self.on_expand = on_expand
        self.on_collapse = on_collapse
        self.on_kitsu = on_kitsu
        self.on_footage = on_footage
        self.on_all = on_all
        self.on_filter_fps = on_filter_fps
        self.on_filter_framerange = on_filter_framerange
        self.on_filter_resolution = on_filter_resolution
        self.on_filter_outdated = on_filter_outdated

        # Theme color for pie slices (default: dark gray, alternative: green)
        self.theme_color = theme_color if theme_color else QColor(60, 60, 60, 200)

        # Simple mode: when no theme color (default gray), show 4 slices (Collapse, Kitsu, Expand, Footage)
        self.is_simple_mode = (theme_color is None)

        # Window setup - use Popup to get mouse events properly
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.BypassWindowManagerHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(320, 320)
        self.setMouseTracking(True)

        # Track which slice is hovered (0-5, or None)
        self.hovered_slice = None

        # Active filter states
        self.active_filters = {
            'fps': False,
            'framerange': False,
            'resolution': False,
            'outdated': False
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Use dynamic center based on widget size
        center = self.rect().center()
        outer_radius = 130
        inner_radius = 50

        # Slice labels and configuration based on mode
        if self.is_simple_mode:
            # Simple mode: 4 slices (Collapse, Kitsu, Expand, Footage)
            slice_labels = ["Collapse", "↻ Kitsu", "Expand", "↻ Footage"]
            # Using positive spans (counter-clockwise)
            slices = [
                # (start_angle, span, label_index) - start in Qt degrees, span in 1/16ths (positive = counter-clockwise)
                (45, 1440, 0),     # Collapse (top)
                (315, 1440, 1),    # Kitsu (right, wraps through 360°)
                (225, 1440, 2),    # Expand (bottom)
                (135, 1440, 3),    # Footage (left)
            ]
        else:
            # Full mode: 5 slices (All, Res, FPS, FrameRange, Outdated)
            slice_labels = ["All", "Res", "FPS", "Frames", "Outdated"]
            slices = [
                # (start_angle, span, label_index) - start in Qt degrees, span in 1/16ths
                (-210, -1920, 0),   # All: 300° to 60° from top (wraps, 120°)
                (30, -960, 1),      # Res: 60° to 120° from top = 30° to -30° Qt (60°)
                (-30, -960, 2),     # FPS: 120° to 180° from top = -30° to -90° Qt (60°)
                (-90, -960, 3),     # FrameRange: 180° to 240° from top = -90° to -150° Qt (60°)
                (-150, -960, 4),    # Outdated: 240° to 300° from top = -150° to -210° Qt (60°)
            ]

        # Gap thickness for parallel separator lines
        gap_thickness = 12  # 2x the original 6px

        import math

        # Draw pie slices
        for i, (start_angle, span, label_idx) in enumerate(slices):
            label = slice_labels[label_idx]

            # Skip empty labels
            if label == "":
                continue

            # Determine if this slice is active (filter)
            is_active = False
            if label_idx == 1:  # Resolution
                is_active = self.active_filters['resolution']
            elif label_idx == 2:  # FPS
                is_active = self.active_filters['fps']
            elif label_idx == 3:  # FrameRange
                is_active = self.active_filters['framerange']
            elif label_idx == 4:  # Outdated
                is_active = self.active_filters['outdated']

            # Set color based on hover and active state
            if self.hovered_slice == i:
                fill_color = QColor(255, 160, 80, 220)  # Light orange when hovered
                text_color = QColor(255, 255, 255)
            elif is_active:
                fill_color = QColor(80, 180, 80, 200)  # Green when active
                text_color = QColor(255, 255, 255)
            else:
                fill_color = self.theme_color  # Use theme color (dark gray or green)
                text_color = QColor(180, 180, 180)

            # Draw pie slice without border
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill_color)

            pie_rect = QRect(center.x() - outer_radius, center.y() - outer_radius, outer_radius * 2, outer_radius * 2)
            painter.drawPie(pie_rect, start_angle * 16, span)

        # Use destination-out composition to create transparent gaps
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)

        # Draw separator lines that will "erase" the pie slices
        if self.is_simple_mode:
            # Simple mode: boundaries at 315°, 45°, 135°, 225° Qt (or -45°, 45°, 135°, 225°)
            boundary_angles_qt = [-45, 45, 135, 225, 315]  # Qt angles
        else:
            # Full mode: boundaries at 60°, 120°, 180°, 240°, 300° from top
            boundary_angles_qt = [30, -30, -90, -150, -210]  # Qt angles

        painter.setPen(QPen(QColor(255, 255, 255, 255), gap_thickness))
        painter.setBrush(Qt.NoBrush)

        for angle_qt in boundary_angles_qt:
            angle_rad = math.radians(angle_qt)
            x1 = center.x() + inner_radius * math.cos(angle_rad)
            y1 = center.y() - inner_radius * math.sin(angle_rad)
            x2 = center.x() + outer_radius * math.cos(angle_rad)
            y2 = center.y() - outer_radius * math.sin(angle_rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Also erase the inner circle to create true hole in pie slices
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawEllipse(center, inner_radius, inner_radius)

        # Restore normal composition mode
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        # Draw center cancel circle (transparent, no border)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, inner_radius, inner_radius)

        # Draw labels
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # Calculate text positions for each slice
        if self.is_simple_mode:
            # Simple mode: Collapse at 0°, Kitsu at 90°, Expand at 180°, Footage at 270°
            slice_angles = [0, 90, 180, 270]
        else:
            # Full mode: Slice center angles for 5 slices (from top, clockwise)
            slice_angles = [0, 90, 150, 210, 270]  # All=0°, Res=90°, FPS=150°, Frames=210°, Outdated=270°

        import math
        text_radius = (inner_radius + outer_radius) / 2  # Middle of the ring

        for i, angle_deg in enumerate(slice_angles):
            label = slice_labels[i]
            if label == "":
                continue

            # Convert angle to radians (adjust for coordinate system)
            rad = math.radians(angle_deg - 90)

            text_x = int(center.x() + text_radius * math.cos(rad))
            text_y = int(center.y() + text_radius * math.sin(rad))

            # Determine if active (filters only apply to full mode)
            is_active = False
            if not self.is_simple_mode:
                if i == 1:  # Resolution
                    is_active = self.active_filters['resolution']
                elif i == 2:  # FPS
                    is_active = self.active_filters['fps']
                elif i == 3:  # FrameRange
                    is_active = self.active_filters['framerange']
                elif i == 4:  # Outdated
                    is_active = self.active_filters['outdated']

            # Set text color based on hover
            if self.hovered_slice == i:
                painter.setPen(QColor(255, 255, 255))
            elif is_active:
                painter.setPen(QColor(150, 255, 150))
            else:
                painter.setPen(QColor(180, 180, 180))

            # Draw centered text with checkmark if active
            display_label = label
            if is_active:
                display_label = label + "✓"

            rect = QRect(text_x - 40, text_y - 15, 80, 30)
            painter.drawText(rect, Qt.AlignCenter, display_label)

        # Draw center decoration circle (on top of everything)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(60, 60, 60, 100))  # More transparent dark gray
        painter.drawEllipse(center, 38, 38)

        # Draw X in center
        painter.setPen(QPen(QColor(180, 180, 180, 40), 3))
        x_offset = 12
        painter.drawLine(int(center.x() - x_offset), int(center.y() - x_offset),
                       int(center.x() + x_offset), int(center.y() + x_offset))
        painter.drawLine(int(center.x() + x_offset), int(center.y() - x_offset),
                       int(center.x() - x_offset), int(center.y() + x_offset))

    def mouseMoveEvent(self, event):
        """Track which slice is being hovered based on gesture direction"""
        center = self.rect().center()
        dx = event.pos().x() - center.x()
        dy = event.pos().y() - center.y()
        distance = (dx * dx + dy * dy) ** 0.5

        # Inside center circle = no selection
        if distance < 50:
            if self.hovered_slice is not None:
                self.hovered_slice = None
                self.update()
            return

        # Calculate angle in degrees (gesture-based, can be outside outer circle)
        import math
        angle = math.degrees(math.atan2(dy, dx))  # -180 to 180

        # Convert to 0-360 starting from top, going clockwise
        angle_from_top = (angle + 90) % 360

        # Determine which slice based on mode (gesture direction, not distance)
        if self.is_simple_mode:
            # Simple mode: 4 slices
            # Collapse: 315-45° (wraps), Kitsu: 45-135°, Expand: 135-225°, Footage: 225-315°
            if angle_from_top >= 315 or angle_from_top < 45:
                slice_index = 0  # Collapse
            elif 45 <= angle_from_top < 135:
                slice_index = 1  # Kitsu
            elif 135 <= angle_from_top < 225:
                slice_index = 2  # Expand
            else:  # 225-315
                slice_index = 3  # Footage
        else:
            # Full mode: 5 slices
            # All: 300-60°, Res: 60-120°, FPS: 120-180°, FrameRange: 180-240°, Outdated: 240-300°
            if angle_from_top >= 300 or angle_from_top < 60:
                slice_index = 0  # All
            elif 60 <= angle_from_top < 120:
                slice_index = 1  # Resolution
            elif 120 <= angle_from_top < 180:
                slice_index = 2  # FPS
            elif 180 <= angle_from_top < 240:
                slice_index = 3  # FrameRange
            else:  # 240-300
                slice_index = 4  # Outdated

        if slice_index is None or not (0 <= slice_index < 5):
            if self.hovered_slice is not None:
                self.hovered_slice = None
                self.update()
            return

        # Only update if changed
        if self.hovered_slice != slice_index:
            self.hovered_slice = slice_index
            self.update()

    def mouseReleaseEvent(self, event):
        """Handle mouse release - execute commands based on gesture direction"""
        # Only respond to middle mouse button release
        if event.button() != Qt.MidButton:
            self.reject()
            return

        # No slice selected = cancel
        if self.hovered_slice is None:
            self.reject()
            return

        # Handle based on mode
        if self.is_simple_mode:
            # Simple mode: 4 slices (Collapse, Kitsu, Expand, Footage)
            if self.hovered_slice == 0:  # Collapse
                if self.on_collapse:
                    self.on_collapse()
                self.accept()
            elif self.hovered_slice == 1:  # Kitsu
                if self.on_kitsu:
                    self.on_kitsu()
                self.accept()
            elif self.hovered_slice == 2:  # Expand
                if self.on_expand:
                    self.on_expand()
                self.accept()
            elif self.hovered_slice == 3:  # Footage
                if self.on_footage:
                    self.on_footage()
                self.accept()
            else:
                self.reject()
        else:
            # Full mode: 5 slices (All, Res, FPS, FrameRange, Outdated)
            if self.hovered_slice == 0:  # All
                if self.on_all:
                    self.on_all()
                self.accept()
            elif self.hovered_slice == 1:  # Resolution
                self.active_filters['resolution'] = not self.active_filters['resolution']
                if self.on_filter_resolution:
                    self.on_filter_resolution(self.active_filters['resolution'])
                self.accept()
            elif self.hovered_slice == 2:  # FPS
                self.active_filters['fps'] = not self.active_filters['fps']
                if self.on_filter_fps:
                    self.on_filter_fps(self.active_filters['fps'])
                self.accept()
            elif self.hovered_slice == 3:  # FrameRange
                self.active_filters['framerange'] = not self.active_filters['framerange']
                if self.on_filter_framerange:
                    self.on_filter_framerange(self.active_filters['framerange'])
                self.accept()
            elif self.hovered_slice == 4:  # Outdated
                self.active_filters['outdated'] = not self.active_filters['outdated']
                if self.on_filter_outdated:
                    self.on_filter_outdated(self.active_filters['outdated'])
                self.accept()
            else:
                self.reject()


class TreeOperationsCore:
    """Handles core tree widget operations"""

    def __init__(self, tracker):
        self.tracker = tracker
        self.core = tracker.core

        # Active filters for tree view
        self._active_filters = {
            'fps': False,
            'framerange': False,
            'resolution': False,
            'outdated': False
        }

    @err_catcher(name=__name__)
    def eventFilter(self, obj, event):
        """Event filter to catch Shift+Click on tree widget expand arrows,
        block Enter key, and handle Ctrl+Click for bypass"""
        # Early validation check - if tree widget doesn't exist, don't process events
        if not hasattr(self.tracker, 'tw_footage') or self.tracker.tw_footage is None:
            return False

        # Check if widget has been deleted (happens during dialog close)
        try:
            # Try to access a simple attribute to check if widget is still valid
            _ = self.tracker.tw_footage.objectName()
        except (RuntimeError, AttributeError):
            # Widget has been deleted, stop processing events
            return False

        # Block Enter key to prevent accidental item activation
        if obj == self.tracker.tw_footage and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                currentItem = self.tracker.tw_footage.currentItem()
                if currentItem:
                    for col in range(self.tracker.tw_footage.columnCount()):
                        widget = self.tracker.tw_footage.itemWidget(currentItem, col)
                        if widget:
                            if widget.hasFocus() or self.widgetChildHasFocus(widget):
                                return False
                return True

        # Handle Ctrl+Shift+Click for bypass - catch from any object in tree
        if event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                # Use bitwise AND check for Qt5/Qt6 compatibility
                control_modifier = (Qt.ControlModifier if hasattr(Qt, 'ControlModifier')
                                    else Qt.KeyboardModifier.ControlModifier)
                shift_modifier = (Qt.ShiftModifier if hasattr(Qt, 'ShiftModifier')
                                  else Qt.KeyboardModifier.ShiftModifier)
                if (modifiers & control_modifier) and (modifiers & shift_modifier):
                    print(f"[DEBUG] Ctrl+Shift+Click detected on obj: {obj}, type: {type(obj).__name__}")
                    # Get position - could be from any widget
                    pos = event.pos()
                    print(f"[DEBUG] Event pos: {pos}")
                    # Map position to viewport coordinates if from child widget
                    if obj != self.tracker.tw_footage.viewport():
                        global_pos = obj.mapToGlobal(pos)
                        viewport_pos = self.tracker.tw_footage.viewport().mapFromGlobal(global_pos)
                        print(f"[DEBUG] Mapped from child widget to viewport_pos: {viewport_pos}")
                    else:
                        viewport_pos = pos
                        print(f"[DEBUG] Direct viewport_pos: {viewport_pos}")

                    item = self.tracker.tw_footage.itemAt(viewport_pos)
                    print(f"[DEBUG] Item found: {item}")
                    if item:
                        print(f"[DEBUG] Item text: {item.text(0)}")
                        column = self.tracker.tw_footage.columnAt(viewport_pos.x())
                        print(f"[DEBUG] Column at position: {column}")
                        self._handleCtrlClickBypass(item, viewport_pos)
                        return True
                    else:
                        print(f"[DEBUG] No item found at viewport_pos: {viewport_pos}")

        # Handle Shift+Click on tree widget items for recursive expand/collapse
        if obj == self.tracker.tw_footage.viewport() and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                modifiers = QApplication.keyboardModifiers()
                # Use bitwise AND for Qt5/Qt6 compatibility
                control_modifier = (Qt.ControlModifier if hasattr(Qt, 'ControlModifier')
                                    else Qt.KeyboardModifier.ControlModifier)
                shift_modifier = (Qt.ShiftModifier if hasattr(Qt, 'ShiftModifier')
                                  else Qt.KeyboardModifier.ShiftModifier)

                # Shift+Click WITHOUT Ctrl = recursive expand/collapse
                if (modifiers & shift_modifier) and not (modifiers & control_modifier):
                    pos = event.pos()
                    item = self.tracker.tw_footage.itemAt(pos)
                    if item:
                        userData = item.data(0, Qt.UserRole)
                        if userData and userData.get('type') == 'group':
                            # Check if click is on the expansion arrow (indentation area)
                            # The arrow is in the indentation area at the left of the item
                            item_depth = self._getItemDepth(item)
                            indent = self.tracker.tw_footage.indentation()
                            # Arrow area is roughly: (depth * indent) to ((depth + 1) * indent)
                            arrow_left = item_depth * indent
                            arrow_right = (item_depth + 1) * indent

                            # Only trigger if click is on the expansion arrow, not the label
                            if arrow_left <= pos.x() < arrow_right:
                                isExpanded = item.isExpanded()
                                self.expandCollapseRecursively(item, not isExpanded)
                                return True

            # Middle-click press to show circular expand/collapse menu
            elif event.button() == Qt.MidButton:
                # Get global position for menu
                pos = event.pos()
                global_pos = obj.mapToGlobal(pos)

                # Check if Shift key is pressed for orange theme
                modifiers = QApplication.keyboardModifiers()
                use_orange_theme = modifiers == Qt.ShiftModifier

                # Create theme color based on Shift key (same as tree mismatch background)
                theme_color = QColor(129, 84, 32, 200) if use_orange_theme else None

                # Create and show circular menu with callbacks
                menu = CircularMenu(
                    self.tracker.tw_footage,
                    on_expand=lambda: self._expandAllGroups(),
                    on_collapse=lambda: self._collapseAllGroups(),
                    on_kitsu=lambda: self.tracker.forceRefreshKitsuData(),
                    on_footage=lambda: self.tracker.loadFootageData(),
                    on_all=self._toggleFilterAll,
                    on_filter_fps=self._toggleFilterFPS,
                    on_filter_framerange=self._toggleFilterFrameRange,
                    on_filter_resolution=self._toggleFilterResolution,
                    on_filter_outdated=self._toggleFilterOutdated,
                    theme_color=theme_color
                )

                # Set initial filter states to match current state
                menu.active_filters = self._active_filters.copy()

                # Center menu on cursor (320x320 menu, offset by 160 to center)
                menu.move(global_pos.x() - 160, global_pos.y() - 160)
                menu.show()

                # Set up tracking - don't grab mouse, just track the menu
                self._circular_menu = menu
                self._menu_press_pos = pos

                return True

        # Note: Middle mouse release is handled by the CircularMenu itself
        # Don't intercept it here - let the menu process the click

        return False

    @err_catcher(name=__name__)
    def widgetChildHasFocus(self, widget):
        """Recursively check if widget or any of its children have focus"""
        if widget.hasFocus():
            return True
        for child in widget.findChildren(QWidget):
            if child.hasFocus():
                return True
        return False

    @err_catcher(name=__name__)
    def expandCollapseRecursively(self, item, expand):
        """Recursively expand or collapse an item and all its children"""
        item.setExpanded(expand)
        for i in range(item.childCount()):
            child = item.child(i)
            self.expandCollapseRecursively(child, expand)

    @err_catcher(name=__name__)
    def _expandAllGroups(self):
        """Expand all groups in the tree"""
        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            topLevelItem = self.tracker.tw_footage.topLevelItem(i)
            self.expandCollapseRecursively(topLevelItem, True)

    @err_catcher(name=__name__)
    def _collapseAllGroups(self):
        """Collapse all groups in the tree"""
        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            topLevelItem = self.tracker.tw_footage.topLevelItem(i)
            self.expandCollapseRecursively(topLevelItem, False)

    @err_catcher(name=__name__)
    def _toggleFilterAll(self):
        """Show all items - clear all filters"""
        self._active_filters = {
            'fps': False,
            'framerange': False,
            'resolution': False,
            'outdated': False
        }
        self._applyFilters()

    @err_catcher(name=__name__)
    def _toggleFilterFPS(self, active):
        """Toggle FPS filter - show only items with FPS issues"""
        self._active_filters['fps'] = active
        self._applyFilters()

    @err_catcher(name=__name__)
    def _toggleFilterFrameRange(self, active):
        """Toggle Frame Range filter - show only items with frame range issues"""
        self._active_filters['framerange'] = active
        self._applyFilters()

    @err_catcher(name=__name__)
    def _toggleFilterResolution(self, active):
        """Toggle Resolution filter - show only items with resolution issues"""
        self._active_filters['resolution'] = active
        self._applyFilters()

    @err_catcher(name=__name__)
    def _toggleFilterOutdated(self, active):
        """Toggle Outdated filter - show only outdated items"""
        self._active_filters['outdated'] = active
        self._applyFilters()

    @err_catcher(name=__name__)
    def _applyFilters(self):
        """Apply all active filters to the tree"""
        # Clear search text and status filter when using circular menu filters
        self.tracker.filter_input.clear()
        self.tracker.status_combo.setCurrentIndex(0)  # Set to "All"

        # Get issue items from tree_renderer (same data source as Check Issues dialog)
        # self.tracker.tree_ops is TreeOperations, which has tree_renderer as an attribute
        parent_tree_ops = self.tracker.tree_ops
        if hasattr(parent_tree_ops, 'tree_renderer'):
            issue_items = getattr(parent_tree_ops.tree_renderer, 'issue_items', {
                'outdated': [],
                'fps_mismatch': [],
                'frame_range_mismatch': [],
                'resolution_mismatch': []
            })
        else:
            issue_items = {
                'outdated': [],
                'fps_mismatch': [],
                'frame_range_mismatch': [],
                'resolution_mismatch': []
            }

        # Build sets of item keys for each issue type (faster lookup)
        outdated_keys = set()
        fps_keys = set()
        framerange_keys = set()
        resolution_keys = set()

        for item in issue_items.get('outdated', []):
            key = self.tracker.startup_warnings._generateItemKey(item, 'outdated')
            outdated_keys.add(key)

        for item in issue_items.get('fps_mismatch', []):
            key = self.tracker.startup_warnings._generateItemKey(item, 'fps_mismatch')
            fps_keys.add(key)

        for item in issue_items.get('frame_range_mismatch', []):
            key = self.tracker.startup_warnings._generateItemKey(item, 'frame_range_mismatch')
            framerange_keys.add(key)

        for item in issue_items.get('resolution_mismatch', []):
            key = self.tracker.startup_warnings._generateItemKey(item, 'resolution_mismatch')
            resolution_keys.add(key)

        def filterItem(item):
            userData = item.data(0, Qt.UserRole)

            if userData and userData.get('type') == 'group':
                hasVisibleChild = False
                for i in range(item.childCount()):
                    childVisible = filterItem(item.child(i))
                    if childVisible:
                        hasVisibleChild = True
                shouldShow = hasVisibleChild
                item.setHidden(not shouldShow)
                return shouldShow
            elif userData and userData.get('type') in ('footage', 'comp'):
                # Generate key for this item
                item_key = self._generateTreeItemKey(item, userData)

                # Check if any active filters match
                matches_filter = False
                has_any_active = any(self._active_filters.values())

                if not has_any_active:
                    # No filters active, show all
                    matches_filter = True
                else:
                    # Check if item matches any active filter (OR logic)
                    if self._active_filters['fps'] and item_key in fps_keys:
                        matches_filter = True
                    if self._active_filters['framerange'] and item_key in framerange_keys:
                        matches_filter = True
                    if self._active_filters['resolution'] and item_key in resolution_keys:
                        matches_filter = True
                    if self._active_filters['outdated'] and item_key in outdated_keys:
                        matches_filter = True

                item.setHidden(not matches_filter)
                return matches_filter
            return True

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            filterItem(self.tracker.tw_footage.topLevelItem(i))

    def _generateTreeItemKey(self, item, userData):
        """Generate a unique key for a tree item (matches tree_renderer._checkAndApplyBypassStyling format)"""
        # For comps, use compId + compName
        if userData.get('type') == 'comp':
            comp_id = userData.get('id') or userData.get('compId')
            comp_name = userData.get('name') or userData.get('compName') or item.text(0)
            return f"comp_{comp_id}_{comp_name}"

        # For footage - use the same logic as bypass styling
        shot_name = self.tracker.getShotNameFromItem(item)
        identifier = userData.get('identifier', '')

        # Check if this is a 3D render (has identifier which is the parent identifier)
        is_3d_render = identifier and identifier != item.text(0)

        # For 3D renders, include AOV in key
        if is_3d_render:
            aov = item.text(0)  # AOV name (e.g., "Z", "beauty")
        else:
            # For 2D renders: identifier is the item text, no AOV
            aov = ''
            if not identifier:
                identifier = item.text(0)

        # Generate key based on shot/identifier/aov (not version-specific)
        if shot_name and identifier:
            if aov:
                # 3D render: include AOV for individual bypass
                return f"footage_{shot_name}_{identifier}_{aov}"
            else:
                # 2D render: no AOV
                return f"footage_{shot_name}_{identifier}"
        else:
            # Fallback to path if hierarchy info not available
            return f"footage_{userData.get('path', '')}"

    def _getItemDepth(self, item):
        """Calculate the depth of a tree widget item (root level = 0)"""
        depth = 0
        current = item
        while current.parent():
            depth += 1
            current = current.parent()
        return depth

    @err_catcher(name=__name__)
    def _handleCtrlClickBypass(self, item, pos):
        """Handle Ctrl+Shift+Click to bypass/unbypass an issue type for an item (regardless of current state)"""
        userData = item.data(0, Qt.UserRole)
        if not userData:
            print(f"[DEBUG BYPASS] No userData found")
            return

        item_type = userData.get('type')
        print(f"[DEBUG BYPASS] item_type: {item_type}")
        if item_type not in ('footage', 'comp'):
            print(f"[DEBUG BYPASS] Item type not in (footage, comp)")
            return  # Only bypass footage or comp items

        # Determine which column was clicked
        column = self.tracker.tw_footage.columnAt(pos.x())
        print(f"[DEBUG BYPASS] column: {column}")

        # Determine issue type based on column (allow bypassing any column, even if no current issue)
        issue_type = None

        if column == 2:
            issue_type = 'outdated'
        elif column == 3:
            issue_type = 'frame_range_mismatch'
        elif column == 4:
            issue_type = 'fps_mismatch'
        elif column == 5:
            issue_type = 'resolution_mismatch'

        print(f"[DEBUG BYPASS] issue_type: {issue_type}")
        if not issue_type:
            return  # Not a valid column for bypassing

        # Generate item key for bypass storage based on shot/identifier (not version-specific)
        # This ensures bypassing applies to all versions of the same render
        print(f"[DEBUG BYPASS] userData keys: {list(userData.keys())}")
        print(f"[DEBUG BYPASS] userData: {userData}")
        if item_type == 'footage':
            # Get shot name from tree hierarchy, fall back to userData['shot'] for 2D renders
            shot_name = self.tracker.getShotNameFromItem(item) or userData.get('shot', '')
            print(f"[DEBUG BYPASS] shot_name: {shot_name}")

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

            print(f"[DEBUG BYPASS] identifier: {identifier}, aov: {aov}, is_3d_render: {is_3d_render}")

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
                path = userData.get('path', '')
                item_key = f"footage_{path}"
        elif item_type == 'comp':
            comp_id = userData.get('id', '')
            comp_name = userData.get('compName', userData.get('name', ''))
            item_key = f"comp_{comp_id}_{comp_name}"
        else:
            return

        print(f"[DEBUG BYPASS] Generated item_key: {item_key}")

        # Also show what the issue data would generate
        print(f"[DEBUG BYPASS] Item userData: {userData if item_type == 'footage' else 'N/A (comp)'}")

        # Get current bypass state from .aep XMP metadata
        import json

        bypassed_items = self._getBypassedItemsFromXMP()

        if issue_type not in bypassed_items:
            bypassed_items[issue_type] = []

        print(f"[DEBUG BYPASS] Before: bypassed_items[{issue_type}] has {len(bypassed_items[issue_type])} items")

        # Toggle bypass state
        if item_key in bypassed_items[issue_type]:
            # Unbypass
            bypassed_items[issue_type].remove(item_key)
            print(f"[DEBUG BYPASS] UNBYPASS: Removed item_key")
        else:
            # Bypass
            bypassed_items[issue_type].append(item_key)
            print(f"[DEBUG BYPASS] BYPASS: Added item_key")

        print(f"[DEBUG BYPASS] After: bypassed_items[{issue_type}] has {len(bypassed_items[issue_type])} items")

        # Save to .aep XMP metadata
        self._saveBypassedItemsToXMP(bypassed_items)

        # Save current scroll position
        scroll_position = self.tracker.tw_footage.verticalScrollBar().value()

        # Reload footage data to update visuals
        self.tracker.loadFootageData()

        # Restore scroll position
        self.tracker.tw_footage.verticalScrollBar().setValue(scroll_position)

    def _getBypassedItemsFromXMP(self):
        """Get bypassed items from .aep file XMP metadata"""
        import json
        import os

        try:
            # Read XMP metadata from the project
            scpt = """
            if (app.project && app.project.xmpPacket) {
                app.project.xmpPacket;
            } else {
                '';
            }
            """
            result = self.core.executeAppleScript(scpt)
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
                        print(f"[DEBUG BYPASS XMP] Loaded from .aep XMP metadata")
                        return bypassed
        except Exception as e:
            print(f"[DEBUG BYPASS XMP] Error reading XMP: {e}")

        # Fallback 1: Try sidecar file (migration)
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
                    print(f"[DEBUG BYPASS XMP] Loaded from sidecar (migration)")
                    return bypassed
                except Exception:
                    pass

        # Fallback 2: Project config
        bypassed = self.core.getConfig("footage_tracker", "bypassed_items", config="project")
        if bypassed:
            print(f"[DEBUG BYPASS XMP] Loaded from project config (legacy)")
            return bypassed

        return {}

    def _saveBypassedItemsToXMP(self, bypassed_items):
        """Save bypassed items to .aep file XMP metadata"""
        import json

        # Ensure all keys exist (convert sets to lists for JSON)
        all_keys = ['outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch']
        to_save = {}
        for key in all_keys:
            if key in bypassed_items:
                # Convert set to list for JSON serialization
                to_save[key] = list(bypassed_items[key]) if isinstance(bypassed_items[key], set) else bypassed_items[key]
            else:
                to_save[key] = []

        json_data = json.dumps(to_save)

        try:
            # Read current XMP packet
            scpt_read = """
            if (app.project && app.project.xmpPacket) {
                app.project.xmpPacket;
            } else {
                '';
            }
            """
            result = self.core.executeAppleScript(scpt_read)
            if result and isinstance(result, bytes):
                result = result.decode('utf-8')

            xmp_packet = result if result else ''

            # Update or append our custom data
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
                        xmp_packet = xmp_packet[:start_idx] + json_data + xmp_packet[end_idx:]
                    else:
                        xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)
                else:
                    xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)
            else:
                xmp_packet = self._appendBypassedItemsToXMP(xmp_packet, json_data)

            # Write back to project
            xmp_escaped = xmp_packet.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')

            scpt_write = f'''
            if (app.project) {{
                app.project.xmpPacket = "{xmp_escaped}";
                "SUCCESS";
            }} else {{
                "ERROR: No project";
            }}
            '''

            result = self.core.executeAppleScript(scpt_write)
            if result and b'SUCCESS' in result:
                print(f"[DEBUG BYPASS XMP] Successfully saved to .aep XMP metadata")
                # Invalidate startup_warnings cache
                if hasattr(self.tracker, 'startup_warnings'):
                    self.tracker.startup_warnings._ignored_items_cache = None
                    self.tracker.startup_warnings._ignored_items_cache_file = None
            else:
                print(f"[DEBUG BYPASS XMP] Failed to save XMP, result: {result}")
                # Fallback to project config
                self.core.setConfig("footage_tracker", "bypassed_items", bypassed_items, config="project")
                # Invalidate startup_warnings cache
                if hasattr(self.tracker, 'startup_warnings'):
                    self.tracker.startup_warnings._ignored_items_cache = None
                    self.tracker.startup_warnings._ignored_items_cache_file = None

        except Exception as e:
            print(f"[DEBUG BYPASS XMP] Error writing XMP: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to project config
            self.core.setConfig("footage_tracker", "bypassed_items", bypassed_items, config="project")
            # Invalidate startup_warnings cache
            if hasattr(self.tracker, 'startup_warnings'):
                self.tracker.startup_warnings._ignored_items_cache = None
                self.tracker.startup_warnings._ignored_items_cache_file = None

    def _appendBypassedItemsToXMP(self, xmp_packet, json_data):
        """Append bypassed items to XMP packet"""
        custom_data = f'<rdf:li rdf:parseType="Resource">PrismFootageTracker:BypassedItems>{json_data}</rdf:li>'

        if '<pdfx:UserDefined>' in xmp_packet:
            marker = '<pdfx:UserDefined>'
            insert_pos = xmp_packet.find(marker)
            if insert_pos > 0:
                insert_pos += len(marker)
                xmp_packet = xmp_packet[:insert_pos] + custom_data + xmp_packet[insert_pos:]
                return xmp_packet

        if '</x:xmpmeta>' in xmp_packet:
            user_defined_section = f'<pdfx:UserDefined>{custom_data}</pdfx:UserDefined>'
            xmp_packet = xmp_packet.replace('</x:xmpmeta>', user_defined_section + '</x:xmpmeta>')
            return xmp_packet

        return xmp_packet + custom_data

    @err_catcher(name=__name__)
    def saveTreeExpansionState(self):
        """Save the current expansion state of all tree items"""
        expandedState = {}

        def saveItemState(item, path=""):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'group':
                itemName = item.text(0)
                currentPath = f"{path}/{itemName}" if path else itemName
                expandedState[currentPath] = item.isExpanded()

                for i in range(item.childCount()):
                    saveItemState(item.child(i), currentPath)

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            saveItemState(self.tracker.tw_footage.topLevelItem(i))

        return expandedState

    @err_catcher(name=__name__)
    def restoreTreeExpansionState(self, expandedState):
        """Restore the expansion state of all tree items"""
        if not expandedState:
            for i in range(self.tracker.tw_footage.topLevelItemCount()):
                self.tracker.tw_footage.topLevelItem(i).setExpanded(True)
            return

        def restoreItemState(item, path=""):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'group':
                itemName = item.text(0)
                currentPath = f"{path}/{itemName}" if path else itemName

                if currentPath in expandedState:
                    item.setExpanded(expandedState[currentPath])

                for i in range(item.childCount()):
                    restoreItemState(item.child(i), currentPath)

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            restoreItemState(self.tracker.tw_footage.topLevelItem(i))

    @err_catcher(name=__name__)
    def updateStatistics(self):
        """Recalculate and update statistics display with all issue types"""
        # Use cached issue counts from tree_renderer (computed during rendering)
        parent_tree_ops = self.tracker.tree_ops
        if hasattr(parent_tree_ops, 'tree_renderer'):
            issue_counts = parent_tree_ops.tree_renderer.issue_counts
        else:
            issue_counts = {
                'outdated': 0,
                'fps_mismatch': 0,
                'frame_range_mismatch': 0,
                'resolution_mismatch': 0,
                'total_footage': 0,
                'total_comps': 0
            }

        # Get non-ignored counts from cached data
        cached_counts = getattr(self.tracker, '_cached_issue_counts', {})
        outdated_count = cached_counts.get('outdated', issue_counts.get('outdated', 0))
        fps_count = cached_counts.get('fps_mismatch', issue_counts.get('fps_mismatch', 0))
        frame_count = cached_counts.get('frame_range_mismatch', issue_counts.get('frame_range_mismatch', 0))
        res_count = cached_counts.get('resolution_mismatch', issue_counts.get('resolution_mismatch', 0))

        # Build statistics text with color-coded issues
        stats_parts = []
        if outdated_count > 0:
            stats_parts.append(f"<span style='color: #FF6464;'>Outdated: {outdated_count}</span>")
        if fps_count > 0:
            stats_parts.append(f"<span style='color: #3498DB;'>FPS: {fps_count}</span>")
        if frame_count > 0:
            stats_parts.append(f"<span style='color: #AB26FF;'>Frames: {frame_count}</span>")
        if res_count > 0:
            stats_parts.append(f"<span style='color: #DAA520;'>Res: {res_count}</span>")

        if stats_parts:
            stats_text = " | ".join(stats_parts)
        else:
            stats_text = ""

        self.tracker.statsLabel.setText(stats_text)
        self.tracker.dlg_footage.statusBar.setText("")
