# -*- coding: utf-8 -*-
"""
Tree Operations Module (Refactored)
Main module that coordinates all tree operations through specialized sub-modules
"""

import os
import platform
import re
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher

# Import refactored modules
from .dialog_manager import DialogManager
from .data_parser import DataParser
from .hierarchy_builder import HierarchyBuilder
from .tree_operations_core import TreeOperationsCore
from .tree_renderer import TreeRenderer
from .shot_switcher import ShotSwitcher
from .context_menu import ContextMenu
from .comp_manager import CompManager
from .ae_organize_manager import AEOrganizeManager


class TreeOperations(QObject):
    """Main tree operations coordinator that delegates to specialized modules"""

    def __init__(self, tracker):
        super(TreeOperations, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

        # Initialize specialized modules
        self.dialog_manager = DialogManager(self)
        self.data_parser = DataParser(self.main, self.core)
        self.hierarchy_builder = HierarchyBuilder(self.tracker)
        self.tree_ops = TreeOperationsCore(self.tracker)
        self.tree_renderer = TreeRenderer(self.tracker)
        self.shot_switcher = ShotSwitcher(self.tracker)
        self.context_menu = ContextMenu(self.tracker)
        self.comp_manager = CompManager(self.tracker)
        self.ae_organize_manager = AEOrganizeManager(self.tracker)

        # Initialize shot alternatives storage for switching functionality
        self.shot_alternatives = {}

        # Expose modules for compatibility
        self.tracker.data_parser = self.data_parser
        self.tracker.hierarchy_builder = self.hierarchy_builder
        self.tracker.dialog_manager = self.dialog_manager
        self.tracker.comp_manager = self.comp_manager
        self.tracker.context_menu = self.context_menu
        self.tracker.ae_organize_manager = self.ae_organize_manager

        # Delegate event filtering to core module
        self.eventFilter = self.tree_ops.eventFilter
        self.widgetChildHasFocus = self.tree_ops.widgetChildHasFocus
        self.expandCollapseRecursively = self.tree_ops.expandCollapseRecursively
        self.saveTreeExpansionState = self.tree_ops.saveTreeExpansionState
        self.restoreTreeExpansionState = self.tree_ops.restoreTreeExpansionState
        self.updateStatistics = self.tree_ops.updateStatistics

    @err_catcher(name=__name__)
    def loadFootageData(self, preserve_scroll=True):
        """Load footage and composition data

        Args:
            preserve_scroll: If True, save and restore the scroll position
        """
        import time

        print("[FOOTAGE] Loading footage data...")
        load_start = time.perf_counter()

        # Guard: abort if the tree widget has been destroyed (e.g. dialog closed
        # while a QTimer callback is still pending).
        try:
            self.tracker.tw_footage.verticalScrollBar()
        except RuntimeError:
            print("[FOOTAGE] tw_footage already deleted, skipping loadFootageData")
            return

        # Save scroll position before clearing the tree
        scroll_position = None
        if preserve_scroll:
            scroll_position = self.tracker.tw_footage.verticalScrollBar().value()
            print(f"[TIMING] Saving scroll position: {scroll_position}")

        expand_start = time.perf_counter()
        expandedState = self.saveTreeExpansionState()
        expand_end = time.perf_counter()
        print(f"[TIMING] Save expansion state: {expand_end - expand_start:.4f}s")

        clear_start = time.perf_counter()
        self.tracker.tw_footage.clear()
        clear_end = time.perf_counter()
        print(f"[TIMING] Clear tree widget: {clear_end - clear_start:.4f}s")

        self.tracker.dlg_footage.statusBar.setText("Loading footage data...")

        # Load Kitsu data (will use cache if available and fresh)
        # Note: Only the "↻ Kitsu" button forces a refresh from server
        kitsu_start = time.perf_counter()
        self.tracker.loadKitsuShotData(force_refresh=False)
        kitsu_end = time.perf_counter()
        print(f"[TIMING] Kitsu data ready: {len(self.tracker.kitsuShotData)} shots in {kitsu_end - kitsu_start:.4f}s")

        # Update "List all shots" button tooltip now that data is loaded
        if hasattr(self.tracker, 'btn_listAllShots') and self.tracker.kitsuShotData:
            shot_count = len(self.tracker.kitsuShotData)
            self.tracker.btn_listAllShots.setToolTip(
                f"Open Kitsu shot list ({shot_count} shots loaded)"
            )

        self.tracker.debugLog = []
        self.tracker.debugLog.append("=" * 80)
        self.tracker.debugLog.append("FOOTAGE TRACKER DEBUG LOG")
        self.tracker.debugLog.append("=" * 80)
        self.tracker.debugLog.append(f"\nKitsu shots loaded: {len(self.tracker.kitsuShotData)}")

        if hasattr(self.tracker.kitsu_integration, 'kitsuLoadError'):
            self.tracker.debugLog.append("\nKitsu Loading Details:")
            self.tracker.debugLog.append("-" * 80)
            self.tracker.debugLog.append(self.tracker.kitsu_integration.kitsuLoadError)
            self.tracker.debugLog.append("-" * 80)

        if self.tracker.kitsuShotData:
            self.tracker.debugLog.append("\nSample Kitsu data:")
            for shotName in list(self.tracker.kitsuShotData.keys())[:5]:
                data = self.tracker.kitsuShotData[shotName]
                self.tracker.debugLog.append(f"  {shotName}: {data['frameRange']} @ {data['fps']} fps")

        hierarchy = {
            "3D Renders": {},
            "2D Renders": {},
            "Resources": {},
            "External": {},
            "Comps": {}
        }

        self.tracker.debugLog.append("\n" + "=" * 80)
        self.tracker.debugLog.append("FOOTAGE COMPARISON:")
        self.tracker.debugLog.append("=" * 80)

        try:
            # Fetch footage data using data parser
            print("[FOOTAGE] Fetching footage AppleScript...")
            script_gen_start = time.perf_counter()
            scpt = self.data_parser.getFootageAppleScript()
            script_gen_end = time.perf_counter()
            print(f"[TIMING] Generate footage AppleScript: {script_gen_end - script_gen_start:.4f}s")

            exec_start = time.perf_counter()
            result = self.main.ae_core.executeAppleScript(scpt)
            exec_end = time.perf_counter()
            print(f"[TIMING] Execute footage AppleScript: {exec_end - exec_start:.4f}s")

            parse_start = time.perf_counter()
            footage_data = self.data_parser.parseFootageData(result)
            parse_end = time.perf_counter()
            print(f"[TIMING] Parse footage data: {len(footage_data)} items in {parse_end - parse_start:.4f}s")

            # Fetch composition data using data parser
            print("[FOOTAGE] Fetching composition AppleScript...")
            script_gen_start = time.perf_counter()
            scpt_comps = self.data_parser.getCompAppleScript()
            script_gen_end = time.perf_counter()
            print(f"[TIMING] Generate comp AppleScript: {script_gen_end - script_gen_start:.4f}s")

            exec_start = time.perf_counter()
            result_comps = self.main.ae_core.executeAppleScript(scpt_comps)
            exec_end = time.perf_counter()
            print(f"[TIMING] Execute comp AppleScript: {exec_end - exec_start:.4f}s")

            self.tracker.debugLog.append(f"\nComps loading result: {result_comps}")

            parse_start = time.perf_counter()
            comp_data = self.data_parser.parseCompData(result_comps)
            parse_end = time.perf_counter()
            print(f"[TIMING] Parse comp data: {len(comp_data)} items in {parse_end - parse_start:.4f}s")
            self.tracker.debugLog.append(f"\nParsed {len(comp_data)} comp items")

            # Build hierarchy using hierarchy builder
            print("[FOOTAGE] Building hierarchy...")
            hierarchy_start = time.perf_counter()
            hierarchy, stats = self.hierarchy_builder.buildHierarchy(footage_data, comp_data)
            hierarchy_end = time.perf_counter()
            print(f"[TIMING] Build hierarchy: {hierarchy_end - hierarchy_start:.4f}s")
            print(
                f"[TIMING]   - Total: {stats.get('total', 0)},"
                f" Up-to-date: {stats.get('up_to_date', 0)},"
                f" Outdated: {stats.get('outdated', 0)}"
            )

            # Build shot alternatives index
            print("[FOOTAGE] Building shot alternatives index...")
            alt_start = time.perf_counter()
            self.shot_alternatives = self.hierarchy_builder.buildShotAlternativesIndex(hierarchy)
            alt_end = time.perf_counter()
            print(
                f"[TIMING] Build shot alternatives: {alt_end - alt_start:.4f}s"
                f" ({len(self.shot_alternatives)} alternatives)"
            )

            # Pivot render hierarchies if identifier-first mode is active per group
            if getattr(self.tracker, 'group_by_mode_3d', 'shot') == 'identifier':
                if hierarchy.get("3D Renders"):
                    hierarchy["3D Renders"] = self.hierarchy_builder.pivot_to_identifier_first(
                        hierarchy["3D Renders"]
                    )
            if getattr(self.tracker, 'group_by_mode_2d', 'shot') == 'identifier':
                if hierarchy.get("2D Renders"):
                    hierarchy["2D Renders"] = self.hierarchy_builder.pivot_to_identifier_first(
                        hierarchy["2D Renders"]
                    )

            # Render tree using tree renderer
            print("[FOOTAGE] Rendering tree widget...")
            render_start = time.perf_counter()
            self.tree_renderer.renderHierarchyTree(hierarchy)
            render_end = time.perf_counter()
            print(f"[TIMING] Render tree widget: {render_end - render_start:.4f}s")

            # Update statistics
            stats_start = time.perf_counter()
            self.updateStatistics()
            stats_end = time.perf_counter()
            print(f"[TIMING] Update statistics: {stats_end - stats_start:.4f}s")

            self.tracker.dlg_footage.statusBar.setText("Footage data loaded successfully")

            # Restore tree expansion state
            restore_start = time.perf_counter()
            self.restoreTreeExpansionState(expandedState)
            restore_end = time.perf_counter()
            print(f"[TIMING] Restore expansion state: {restore_end - restore_start:.4f}s")

            # Restore scroll position after tree is fully rendered
            if preserve_scroll and scroll_position is not None:
                from qtpy.QtCore import QTimer
                # Use singleShot to ensure scroll position is set after UI updates
                QTimer.singleShot(0, lambda: self.tracker.tw_footage.verticalScrollBar().setValue(scroll_position))
                print(f"[TIMING] Scheduled scroll position restore to: {scroll_position}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error loading footage:\n{str(e)}\n\n{traceback.format_exc()}")
            self.tracker.dlg_footage.statusBar.setText("Error loading footage data")

        finally:
            # ALWAYS store hierarchy data for shot switching functionality, even if partial
            self.tracker._stored_hierarchy = hierarchy
            self.tracker.main.ae_footage = self.tracker
            self.tracker.main._footage_hierarchy = hierarchy

            # Update Check Issues button state (after hierarchy is stored)
            button_start = time.perf_counter()
            self.tracker.updateCheckIssuesButton()
            button_end = time.perf_counter()
            print(f"[TIMING] Update Check Issues button: {button_end - button_start:.4f}s")

            # Total time for loadFootageData
            load_end = time.perf_counter()
            print(f"[TIMING] TOTAL loadFootageData time: {load_end - load_start:.4f}s")
            print(f"{'-'*80}")

            # Run startup checks for outdated versions and FPS mismatches (only on first load)
            if not hasattr(self, '_startup_check_done'):
                self._startup_check_done = True
                # Don't auto-run for now - user can click "Check Issues" button
                # self.tracker.runStartupCheck(hierarchy)

    # Delegate remaining methods to appropriate modules or implement here
    # For now, we'll keep the original methods that weren't extracted yet

    @err_catcher(name=__name__)
    def handleMultiVersionChange(self, currentItem, newVersion, currentUserData):
        """Handle version change for multiple selected footage items"""
        try:
            # Get all selected footage items
            selectedFootageItems = []

            for item in self.tracker.tw_footage.selectedItems():
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'footage':
                    selectedFootageItems.append((item, userData))

            # If only one item is selected, use the original single-item behavior
            if len(selectedFootageItems) <= 1:
                self.tracker.updateFootageVersion(currentItem, newVersion, currentUserData)
                return

            # Filter items that have the requested version available
            compatibleItems = []
            for item, userData in selectedFootageItems:
                # Get the actual available versions from the combo box
                versionWidget = self.tracker.tw_footage.itemWidget(item, 1)
                if versionWidget and versionWidget.layout().count() > 0:
                    combo = versionWidget.layout().itemAt(0).widget()
                    if isinstance(combo, QComboBox):
                        availableVersions = [combo.itemText(i) for i in range(combo.count())]
                        if newVersion in availableVersions:
                            compatibleItems.append((item, userData))

            if not compatibleItems:
                QMessageBox.warning(
                    self.tracker.dlg_footage,
                    "No Compatible Footage",
                    f"None of the selected {len(selectedFootageItems)} footage items"
                    f" have version '{newVersion}' available."
                )
                return

            # Show confirmation dialog
            reply = QMessageBox.question(
                self.tracker.dlg_footage,
                "Update Multiple Footage Versions",
                f"Update {len(compatibleItems)} compatible footage item(s) to version '{newVersion}'?\n\n"
                f"Total selected: {len(selectedFootageItems)}\n"
                f"Compatible with version '{newVersion}': {len(compatibleItems)}",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

            # Update all compatible items
            self.tracker.updateMultipleFootageVersions(compatibleItems, newVersion)

        except Exception as e:
            import traceback
            self.core.popup(f"Error handling multi-version change:\n{str(e)}\n\n{traceback.format_exc()}")

    # Delegate missing methods to appropriate modules for compatibility
    def extractCurrentShotFromProject(self):
        """Delegate to data_parser"""
        return self.data_parser.extractCurrentShotFromProject()

    def getVersionNumber(self, version_str):
        """Delegate to data_parser"""
        return self.data_parser.getVersionNumber(version_str)

    @err_catcher(name=__name__)
    def showFootageContextMenu(self, position):
        """Delegate to context_menu"""
        print(f"DEBUG: tree_operations.showFootageContextMenu called with position {position}")
        return self.context_menu.showFootageContextMenu(position)

    @err_catcher(name=__name__)
    def showCompContextMenu(self, comp_items, position):
        """Delegate to context_menu"""
        return self.context_menu.showCompContextMenu(comp_items, position)

    @err_catcher(name=__name__)
    def showCompInfo(self, compId, compName):
        """Delegate to comp_manager"""
        return self.comp_manager.showCompInfo(compId, compName)

    @err_catcher(name=__name__)
    def showRawCompInfo(self, compId, compName):
        """Delegate to shot_switcher"""
        return self.shot_switcher.showRawCompInfo(compId, compName)

    @err_catcher(name=__name__)
    def showShotSelectionDialog(self, footage_items):
        """Delegate to shot_switcher"""
        return self.shot_switcher.showShotSelectionDialog(footage_items)

    @err_catcher(name=__name__)
    def switchToLatestVersion(self, footage_items, target_shot):
        """Delegate to shot_switcher"""
        return self.shot_switcher.switchToLatestVersion(footage_items, target_shot)

    @err_catcher(name=__name__)
    def findLatestVersionInShot(self, target_shot, identifier, aov):
        """Delegate to shot_switcher"""
        return self.shot_switcher.findLatestVersionInShot(target_shot, identifier, aov)

    @err_catcher(name=__name__)
    def setCompFrameRangeFromKitsu(self, compId, compName, kitsu_frame_range):
        """Delegate to comp_manager"""
        return self.comp_manager.setCompFrameRangeFromKitsu(compId, compName, kitsu_frame_range)

    @err_catcher(name=__name__)
    def setCompFPSFromKitsu(self, compId, compName, kitsu_fps):
        """Delegate to comp_manager"""
        return self.comp_manager.setCompFPSFromKitsu(compId, compName, kitsu_fps)

    @err_catcher(name=__name__)
    def setCompFromKitsu(self, compId, compName, kitsu_frame_range, kitsu_fps):
        """Delegate to comp_manager"""
        return self.comp_manager.setCompFromKitsu(compId, compName, kitsu_frame_range, kitsu_fps)

    @err_catcher(name=__name__)
    def revealMultipleComps(self, comp_items):
        """Delegate to comp_manager"""
        return self.comp_manager.revealMultipleComps(comp_items)

    @err_catcher(name=__name__)
    def deleteFootageFromTree(self, items):
        """Delete footage items from AE and remove from tree"""
        try:
            if not items:
                return

            # Collect all items to delete (including children of groups)
            items_to_delete = []
            item_names = []

            def collect_items(item):
                userData = item.data(0, Qt.UserRole)
                if userData:
                    item_type = userData.get('type')
                    if item_type == 'footage':
                        items_to_delete.append(('footage', item, userData))
                        item_names.append(f"Footage: {item.text(0)}")
                    elif item_type == 'comp':
                        items_to_delete.append(('comp', item, userData))
                        item_names.append(f"Comp: {item.text(0)}")
                    elif item_type == 'group':
                        # For groups, collect all children
                        for i in range(item.childCount()):
                            collect_items(item.child(i))
                        item_names.append(f"Group: {item.text(0)} (with {item.childCount()} items)")

            for item in items:
                collect_items(item)

            if not items_to_delete:
                self.core.popup("No deletable items selected.\n\nOnly footage and compositions can be deleted.")
                return

            # Show confirmation dialog
            count_msg = f"{len(items_to_delete)} item(s)" if len(items_to_delete) > 1 else "1 item"
            reply = QMessageBox.question(
                self.tracker.dlg_footage,
                "Confirm Delete",
                f"Delete {count_msg} from After Effects project?\n\n"
                f"This action cannot be undone.\n\n"
                f"Items to delete:\n" + "\n".join(item_names[:10]) +
                (f"\n... and {len(item_names) - 10} more" if len(item_names) > 10 else ""),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes  # Set Yes as default so Enter confirms deletion
            )

            if reply == QMessageBox.No:
                return

            # Delete items from AE
            success_count = 0
            failed_count = 0
            failed_items = []

            for item_type, item, userData in items_to_delete:
                try:
                    if item_type == 'footage':
                        result = self.tracker.ae_ops.deleteFootageItem(userData['id'])
                        if result.get('success'):
                            success_count += 1
                        else:
                            failed_count += 1
                            failed_items.append(f"{item.text(0)}: {result.get('error', 'Unknown error')}")
                    elif item_type == 'comp':
                        result = self.tracker.ae_ops.deleteCompItem(userData['id'])
                        if result.get('success'):
                            success_count += 1
                        else:
                            failed_count += 1
                            failed_items.append(f"{item.text(0)}: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    failed_count += 1
                    failed_items.append(f"{item.text(0)}: {str(e)}")

            # Show result
            if failed_count > 0:
                error_msg = "\n".join(failed_items[:10])
                if len(failed_items) > 10:
                    error_msg += f"\n... and {len(failed_items) - 10} more"
                self.tracker.showSelectableMessage(
                    "Delete Complete with Errors",
                    f"Successfully deleted: {success_count}\n"
                    f"Failed to delete: {failed_count}\n\n"
                    f"Errors:\n{error_msg}"
                )
            else:
                self.tracker.dlg_footage.statusBar.setText(f"Deleted {success_count} item(s)")
                QTimer.singleShot(2000, lambda: self.tracker.dlg_footage.statusBar.setText(""))

            # Reload footage data to refresh the tree
            self.tracker.loadFootageData()

        except Exception as e:
            import traceback
            self.core.popup(f"Error deleting items:\n{str(e)}\n\n{traceback.format_exc()}")

    # Keep existing methods for now - these will need to be refactored further
    # TODO: Move context menu methods to a separate module
    # TODO: Move shot switching methods to shot_switcher.py
    # TODO: Move comp info methods to a separate module