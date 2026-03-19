# -*- coding: utf-8 -*-
"""
Prism AfterEffects Footage Tracker - Main Tracker Class
"""

import os
import subprocess
import platform
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher

from .ui_components import NoHoverDelegate
from .utils import FootageUtils
from .kitsu_integration import KitsuIntegration
from .ui_setup import UISetup
from .ae_operations import AEOperations
from .tree_operations import TreeOperations
from .import_shots import ImportShots
from .dialog_storage import get_dialog, set_dialog, has_dialog
from .startup_warnings import StartupWarnings


# Settings for remembering window position
TRACKER_SETTINGS_KEY = "FootageTracker/WindowGeometry"


class DraggableDialog(QDialog):
    """Standard dialog with native Windows borders and resizing"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def setTitleBarWidget(self, title_bar):
        """No-op for compatibility - standard dialog has its own title bar"""
        pass


class AEFootageTracker(QObject):
    def __init__(self, main):
        super(AEFootageTracker, self).__init__()
        self.main = main
        self.core = main.core
        self.utils = FootageUtils()

        # Initialize Kitsu integration
        self.kitsu_integration = KitsuIntegration(main, self.core)

        # Initialize operations handlers
        self.ae_ops = AEOperations(self)
        self.tree_ops = TreeOperations(self)
        self.ui_setup = UISetup(self)
        self.import_shots = ImportShots(self)
        self.startup_warnings = StartupWarnings(self)

        # Expose Kitsu properties for compatibility
        self.kitsu = self.kitsu_integration.kitsu

        if hasattr(self.kitsu_integration, 'kitsu_error'):
            self.kitsu_error = self.kitsu_integration.kitsu_error

    @property
    def kitsuShotData(self):
        """Property to access Kitsu shot data"""
        return self.kitsu_integration.kitsuShotData

    @err_catcher(name=__name__)
    def openFootageVersionTracker(self, pos_x=None, pos_y=None):
        """Open the footage version tracking dialog

        Args:
            pos_x: Optional X coordinate for window position
            pos_y: Optional Y coordinate for window position
        """
        import time

        # Start total timing
        total_start = time.perf_counter()
        print(f"{'='*80}")
        print(f"FOOTAGE TRACKER TIMING: Starting to open footage tracker")
        print(f"{'='*80}")

        # Check if dialog already exists in global storage
        existing_dialog = get_dialog("footage")
        if existing_dialog is not None:
            # Dialog exists, bring it to front
            existing_dialog.raise_()
            existing_dialog.activateWindow()
            existing_dialog.showNormal()  # Restore if minimized
            return True

        # Time UI setup
        ui_start = time.perf_counter()

        # Create new dialog only if none exists (always create on first call)
        self.dlg_footage = DraggableDialog()
        self.dlg_footage.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
        )
        self.dlg_footage.setWindowTitle("Prism - Footage Version Tracker")
        self.dlg_footage.resize(1200, 600)

        # Restore saved position if available
        settings = QSettings("Prism", "AfterEffectsPlugin")
        saved_geometry = settings.value(TRACKER_SETTINGS_KEY)

        if pos_x is not None and pos_y is not None:
            # Use provided position
            print(f"[TRACKER] Using provided position: ({pos_x}, {pos_y})")
            self.dlg_footage.move(pos_x, pos_y)
        elif saved_geometry:
            # Restore saved position/geometry
            print(f"[TRACKER] Restoring saved geometry")
            self.dlg_footage.restoreGeometry(saved_geometry)
        else:
            # Default position - align to right side of screen
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                x = screen_geometry.right() - 1250  # Width + small margin
                y = 100
                self.dlg_footage.move(x, y)
                print(f"[TRACKER] Using default position: ({x}, {y})")

        # Store in global dialog storage and setup cleanup
        set_dialog("footage", self.dlg_footage)

        # Clean up when dialog is closed - restore stdout if debug console was active
        def cleanupOnClose():
            # Save window geometry for next time
            settings.setValue(TRACKER_SETTINGS_KEY, self.dlg_footage.saveGeometry())
            print(f"[TRACKER] Saved window geometry")
            setattr(self, 'dlg_footage', None)
            # Restore stdout in case debug console was left open
            import sys
            if hasattr(sys, '__stdout__'):
                sys.stdout = sys.__stdout__
                sys.stderr = sys.__stderr__

        self.dlg_footage.finished.connect(cleanupOnClose)

        self.ui_setup.setupFootageUI()

        ui_end = time.perf_counter()
        print(f"[TIMING] UI setup took: {ui_end - ui_start:.4f} seconds")

        # Time data loading
        data_start = time.perf_counter()
        self.loadFootageData()
        data_end = time.perf_counter()
        print(f"[TIMING] Data loading took: {data_end - data_start:.4f} seconds")

        show_start = time.perf_counter()
        self.dlg_footage.show()
        show_end = time.perf_counter()
        print(f"[TIMING] Show dialog took: {show_end - show_start:.4f} seconds")

        total_end = time.perf_counter()
        print(f"[TIMING] TOTAL TIME to open footage tracker: {total_end - total_start:.4f} seconds")
        print(f"{'='*80}")
        return True

    @err_catcher(name=__name__)
    def loadFootageData(self, preserve_scroll=True):
        """Query After Effects for all footage and check versions

        Args:
            preserve_scroll: If True, save and restore the scroll position after reloading
        """
        # Delegate to tree operations
        self.tree_ops.loadFootageData(preserve_scroll=preserve_scroll)

    def getShotNameFromItem(self, item):
        """Get the shot name by traversing up the tree hierarchy"""
        current = item
        while current:
            userData = current.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'group' and userData.get('level') == 'shot':
                return current.text(0)
            current = current.parent()
        return None
    
    def getKitsuDataForShot(self, shotName):
        """Get Kitsu frame range and FPS data for a specific shot"""
        return self.kitsu_integration.getKitsuDataForShot(shotName)
    
    def getKitsuShotEntity(self, shotName):
        """Get the Kitsu shot entity for a given shot name"""
        return self.kitsu_integration.getKitsuShotEntity(shotName)
    
    def getStatusColor(self, statusShortName, kitsuMgr):
        """Get status color from Kitsu or use default colors"""
        return self.kitsu_integration.getStatusColor(statusShortName, kitsuMgr)
    
    def createColorIcon(self, color):
        """Create a small colored circle icon for menu items"""
        return self.kitsu_integration.createColorIcon(color)

    @err_catcher(name=__name__)
    def openShotInKitsu(self, shot):
        """Open shot in Kitsu web browser"""
        self.kitsu_integration.openShotInKitsu(shot)
    
    @err_catcher(name=__name__)
    def openTaskInKitsu(self, task):
        """Open task in Kitsu web browser"""
        self.kitsu_integration.openTaskInKitsu(task)

    @err_catcher(name=__name__)
    def openKitsuShotList(self):
        """Open the Kitsu shot list dialog"""
        self.kitsu_integration.openKitsuShotList()
    
    @err_catcher(name=__name__)
    def showKitsuError(self):
        """Show detailed Kitsu loading error"""
        self.kitsu_integration.showKitsuError(self.core)

    @err_catcher(name=__name__)
    def loadKitsuShotData(self, force_refresh=False):
        """
        Load frame ranges and FPS from Kitsu for all shots

        Args:
            force_refresh: If True, bypass cache and force reload from Kitsu
        """
        self.kitsu_integration.loadKitsuShotData(force_refresh=force_refresh)

    @err_catcher(name=__name__)
    def forceRefreshKitsuData(self):
        """Force refresh Kitsu data from server (bypasses cache) and reload footage"""
        import time

        if hasattr(self, 'dlg_footage') and self.dlg_footage:
            self.dlg_footage.statusBar.setText("Force refreshing Kitsu data from server...")

        start_time = time.perf_counter()

        # Force refresh Kitsu data (bypasses cache)
        self.loadKitsuShotData(force_refresh=True)

        refresh_time = time.perf_counter() - start_time

        # Update button tooltip with new shot count
        if hasattr(self, 'btn_listAllShots') and self.kitsuShotData:
            self.btn_listAllShots.setToolTip(f"Open Kitsu shot list ({len(self.kitsuShotData)} shots loaded)")
            print(f"[REFRESH] Kitsu data refreshed: {len(self.kitsuShotData)} shots in {refresh_time:.2f}s")

        # Reload footage data to reflect any Kitsu changes
        self.loadFootageData()

        if hasattr(self, 'dlg_footage') and self.dlg_footage:
            self.dlg_footage.statusBar.setText(f"Kitsu data refreshed ({len(self.kitsuShotData)} shots)")

    @err_catcher(name=__name__)
    def openImportDialog(self):
        """Open the import shots dialog"""
        self.import_shots.openImportDialog()

    # Delegate AE operations
    @err_catcher(name=__name__)
    def updateFootageVersion(self, item, newVersion, userData):
        """Update footage to use a different version"""
        return self.ae_ops.updateFootageVersion(item, newVersion, userData)

    @err_catcher(name=__name__)
    def updateMultipleFootageVersions(self, compatibleItems, newVersion):
        """Update multiple footage items to use a different version"""
        return self.ae_ops.updateMultipleFootageVersions(compatibleItems, newVersion)

    @err_catcher(name=__name__)
    def updateFootageFPS(self, item, fps, userData):
        """Update footage FPS in After Effects"""
        self.ae_ops.updateFootageFPS(item, fps, userData)

    @err_catcher(name=__name__)
    def updateCompFPS(self, item, fps, compInfo):
        """Update composition FPS in After Effects"""
        self.ae_ops.updateCompFPS(item, fps, compInfo)

    @err_catcher(name=__name__)
    def updateCompFrameRange(self, item, startFrame, endFrame, compInfo):
        """Update composition frame range in After Effects"""
        self.ae_ops.updateCompFrameRange(item, startFrame, endFrame, compInfo)

    @err_catcher(name=__name__)
    def updateCompResolution(self, item, width, height, compInfo):
        """Update composition resolution in After Effects"""
        self.ae_ops.updateCompResolution(item, width, height, compInfo)

    @err_catcher(name=__name__)
    def updateAllOutdated(self):
        """Update all outdated footage to latest versions"""
        self.ae_ops.updateAllOutdated()

    @err_catcher(name=__name__)
    def updateSpecificOutdated(self, paths):
        """Update specific outdated footage items by their paths"""
        self.ae_ops.updateSpecificOutdated(paths)

    @err_catcher(name=__name__)
    def updateSelectedOutdated(self):
        """Update selected outdated footage to latest versions"""
        self.ae_ops.updateSelectedOutdated()

    @err_catcher(name=__name__)
    def updateAllFPS(self):
        """Update FPS for all footage to match Kitsu project FPS"""
        self.ae_ops.updateAllFPS()

    @err_catcher(name=__name__)
    def batchUpdateFPS(self):
        """Update FPS for all selected footage"""
        self.ae_ops.batchUpdateFPS()

    @err_catcher(name=__name__)
    def updateSelectedToKitsuFPS(self):
        """Update FPS for selected footage to match Kitsu values"""
        self.ae_ops.updateAllFPS(selected_only=True)

    @err_catcher(name=__name__)
    def runStartupCheck(self, hierarchy=None):
        """Run startup checks for outdated versions and FPS mismatches"""
        # Run check in background to not block UI
        QTimer.singleShot(500, lambda: self.startup_warnings.checkFootageIssues(hierarchy))

    @err_catcher(name=__name__)
    def runStartupWarningsCheck(self):
        """Manual trigger for startup warnings check - called from UI button"""
        # Get current hierarchy
        hierarchy = getattr(self, '_stored_hierarchy', None)

        # If no hierarchy, load it first
        if hierarchy is None:
            self.core.popup("No footage data loaded yet.\n\nPlease load footage first.")
            return

        # Run the check immediately (no delay for manual trigger)
        result = self.startup_warnings.checkFootageIssues(hierarchy)

        # Update button state based on issue counts
        self.updateCheckIssuesButton(result)

    @err_catcher(name=__name__)
    def updateCheckIssuesButton(self, issue_counts=None):
        """Update the Check Issues button state based on issue counts"""
        import time

        update_start = time.perf_counter()

        if issue_counts is None:
            # Use cached issue counts from tree rendering (already computed)
            issue_counts = getattr(self, '_cached_issue_counts', None)
            print(f"[TIMING]   updateCheckIssuesButton: Using cached counts (no recalculation)")

            # If no cached counts available, return with default state
            if issue_counts is None:
                # No data - disable button
                if hasattr(self, 'btn_checkIssues'):
                    self.btn_checkIssues.setEnabled(False)
                    self.btn_checkIssues.setText("⚠ Check Issues")
                return

        # Calculate total issues
        calc_start = time.perf_counter()
        if issue_counts:
            total_issues = (
                issue_counts.get('outdated', 0) +
                issue_counts.get('fps_mismatch', 0) +
                issue_counts.get('frame_range_mismatch', 0) +
                issue_counts.get('resolution_mismatch', 0)
            )
        else:
            total_issues = 0
        calc_end = time.perf_counter()

        # Update button
        if hasattr(self, 'btn_checkIssues'):
            if total_issues > 0:
                self.btn_checkIssues.setEnabled(True)
                self.btn_checkIssues.setText(f"⚠ Check Issues ({total_issues})")
            else:
                # Keep button enabled so user can access "Reset Ignored" option
                self.btn_checkIssues.setEnabled(True)
                self.btn_checkIssues.setText("✓ No Issues")

        update_end = time.perf_counter()
        print(
            f"[TIMING]   updateCheckIssuesButton: {update_end - update_start:.4f}s"
            f" (calc: {calc_end - calc_start:.4f}s, issues: {total_issues})"
        )

    @err_catcher(name=__name__)
    def revealInProject(self, footageId):
        """Reveal and select footage in After Effects Project panel"""
        self.ae_ops.revealInProject(footageId)

    @err_catcher(name=__name__)
    def revealInCompositions(self, footageId):
        """Show all compositions that use this footage"""
        self.ae_ops.revealInCompositions(footageId)

    @err_catcher(name=__name__)
    def openComposition(self, compId, compName, parentDialog):
        """Open a composition in After Effects"""
        self.ae_ops.openComposition(compId, compName, parentDialog)

    # Context menu and UI operations
    @err_catcher(name=__name__)
    def showFootageContextMenu(self, position):
        """Show context menu on right-click"""
        print(f"DEBUG: tracker.showFootageContextMenu called with position {position}")
        self.tree_ops.showFootageContextMenu(position)

    # Kitsu sync methods - delegate to comp_manager
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
    def showCompInfo(self, compId, compName):
        """Delegate to comp_manager"""
        return self.comp_manager.showCompInfo(compId, compName)

    @err_catcher(name=__name__)
    def showRawCompInfo(self, compId, compName):
        """Delegate to comp_manager"""
        return self.comp_manager.showRawCompInfo(compId, compName)

    @err_catcher(name=__name__)
    def openInExplorer(self, folderPath):
        """Open folder in file explorer"""
        try:
            if not os.path.exists(folderPath):
                self.core.popup(f"Path does not exist:\n{folderPath}")
                return
            
            if platform.system() == "Windows":
                os.startfile(folderPath)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", folderPath])
            else:
                subprocess.Popen(["xdg-open", folderPath])
        except Exception as e:
            self.core.popup(f"Error opening folder:\n{str(e)}")

    def updateStatistics(self):
        """Recalculate and update statistics display"""
        self.tree_ops.updateStatistics()

    @err_catcher(name=__name__)
    def showSelectableMessage(self, title, message):
        """Show a message dialog with selectable text"""
        dlg = QDialog(self.dlg_footage if hasattr(self, 'dlg_footage') else None)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle(title)
        dlg.resize(700, 400)
        
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        
        textEdit = QTextEdit()
        textEdit.setPlainText(message)
        textEdit.setReadOnly(True)
        textEdit.setLineWrapMode(QTextEdit.NoWrap)
        textEdit.setFontFamily("Courier New")
        layout.addWidget(textEdit)
        
        buttonLayout = QHBoxLayout()
        copyBtn = QPushButton("Copy to Clipboard")
        copyBtn.clicked.connect(lambda: QApplication.clipboard().setText(message))
        buttonLayout.addWidget(copyBtn)
        
        closeBtn = QPushButton("Close")
        closeBtn.clicked.connect(dlg.close)
        closeBtn.setDefault(True)
        buttonLayout.addWidget(closeBtn)
        
        layout.addLayout(buttonLayout)
        dlg.exec_()

    @err_catcher(name=__name__)
    def showArchiveExportDialog(self, archive_path):
        """Show dialog after successful archive export with Open and Open in Explorer options"""
        dlg = QDialog(self.dlg_footage if hasattr(self, 'dlg_footage') else None)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle("Archive Exported")
        dlg.resize(500, 150)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Success message
        icon_label = QLabel("✓")
        icon_label.setStyleSheet("font-size: 48px; color: #4CAF50;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        msg_label = QLabel("Archive info exported successfully!")
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(msg_label)

        path_label = QLabel(archive_path)
        path_label.setAlignment(Qt.AlignCenter)
        path_label.setStyleSheet("font-size: 12px; color: #666; padding: 0 20px;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        # Buttons
        button_layout = QHBoxLayout()

        open_btn = QPushButton("Open")
        open_btn.setMinimumWidth(100)
        open_btn.clicked.connect(lambda: self.openArchiveFile(archive_path))
        button_layout.addWidget(open_btn)

        explorer_btn = QPushButton("Open in Explorer")
        explorer_btn.setMinimumWidth(120)
        explorer_btn.clicked.connect(lambda: self.openArchiveInExplorer(archive_path))
        button_layout.addWidget(explorer_btn)

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(dlg.close)
        close_btn.setDefault(True)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dlg.exec_()

    @err_catcher(name=__name__)
    def openArchiveFile(self, archive_path):
        """Open the archive JSON file with the default system application"""
        try:
            if platform.system() == "Windows":
                os.startfile(archive_path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", archive_path])
            else:
                subprocess.Popen(["xdg-open", archive_path])
        except Exception as e:
            self.core.popup(f"Error opening archive file:\n{str(e)}")

    @err_catcher(name=__name__)
    def openArchiveInExplorer(self, archive_path):
        """Open the folder containing the archive file and select it"""
        try:
            folder_path = os.path.dirname(archive_path)

            if platform.system() == "Windows":
                # On Windows, use explorer with /select to highlight the file
                subprocess.Popen(["explorer", "/select,", archive_path])
            elif platform.system() == "Darwin":
                # On macOS, use open with -R to reveal in Finder
                subprocess.Popen(["open", "-R", archive_path])
            else:
                # On Linux, just open the folder
                subprocess.Popen(["xdg-open", folder_path])
        except Exception as e:
            self.core.popup(f"Error opening explorer:\n{str(e)}")

    @err_catcher(name=__name__)
    def exportArchiveInfo(self):
        """Export archive information to JSON file"""
        try:
            # Check if we have footage data
            if not hasattr(self, '_stored_hierarchy') or not self._stored_hierarchy:
                self.core.popup("No footage data available. Please refresh the footage list first.")
                return

            # Get current AE project file path
            current_file = self.core.getCurrentFileName()
            if not current_file:
                self.core.popup("No project file is currently open. Please save or open a project first.")
                return

            # Create archive file path with same name and location as AEP file
            archive_path = os.path.splitext(current_file)[0] + "_archiveinfo.json"

            # Import and use archive_info module
            from . import archive_info
            archive_data = archive_info.generate_archive_info(self, current_file)

            result = archive_info.write_archive_json(archive_data, archive_path)

            if result and not result.startswith("Error:"):
                # Show dialog with Open and Open in Explorer options
                self.showArchiveExportDialog(result)
            else:
                self.core.popup(f"Failed to export archive info.\n\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error exporting archive info:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showDebugLog(self):
        """Show the debug log in a dialog with selectable text"""
        if not hasattr(self, 'debugLog') or not self.debugLog:
            self.core.popup("No debug log available. Please refresh the footage list first.")
            return

        dlg = QDialog(self.dlg_footage)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle("Debug Log - Frame Range Comparison")
        dlg.resize(800, 600)
        
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        
        label = QLabel("<b>Debug Log:</b> This shows the comparison between footage frame ranges and Kitsu data.")
        layout.addWidget(label)
        
        debugText = QTextEdit()
        debugText.setPlainText("\n".join(self.debugLog))
        debugText.setReadOnly(True)
        debugText.setLineWrapMode(QTextEdit.NoWrap)
        debugText.setFontFamily("Courier New")
        layout.addWidget(debugText)
        
        buttonLayout = QHBoxLayout()
        copyBtn = QPushButton("Copy to Clipboard")
        copyBtn.clicked.connect(lambda: QApplication.clipboard().setText("\n".join(self.debugLog)))
        buttonLayout.addWidget(copyBtn)
        
        closeBtn = QPushButton("Close")
        closeBtn.clicked.connect(dlg.close)
        buttonLayout.addWidget(closeBtn)
        
        layout.addLayout(buttonLayout)
        dlg.exec_()
