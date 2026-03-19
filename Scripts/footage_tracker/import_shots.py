# -*- coding: utf-8 -*-
"""
Import Shots Module
Handles importing footage from Prism shot structure into After Effects
WITH SMART CACHING SYSTEM FOR INSTANT LOADING
"""

import os
import json
import time
import threading
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
from PrismUtils.Decorators import err_catcher as err_catcher


class CacheManager(QObject):
    """Manages persistent caching with background updates"""
    
    cacheUpdated = Signal(dict)
    
    def __init__(self, core, cache_dir, debug_callback=None):
        super(CacheManager, self).__init__()
        self.core = core
        self.cache_dir = cache_dir
        self.cache_file = os.path.join(cache_dir, "footage_cache.json")
        self.cache_lock = threading.Lock()
        self.stop_thread = False
        self.update_thread = None
        self._current_cache = {}
        self._last_scan_time = 0
        self.debug_callback = debug_callback
        
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _debug(self, message):
        """Send debug message to callback if available"""
        if self.debug_callback:
            try:
                self.debug_callback(message)
            except Exception:
                pass
        print(f"[CacheManager] {message}")
    
    def loadCache(self):
        """Load cache from disk immediately - INSTANT"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    self._current_cache = cache_data.get('hierarchy', {})
                    self._last_scan_time = cache_data.get('scan_time', 0)
                    return self._current_cache
        except Exception as e:
            self._debug(f"ERROR loading cache: {e}")
        return {}
    
    def _countVersionsInDict(self, shot_data):
        """Count versions in a shot data dictionary"""
        count = 0
        for identifier_data in shot_data.values():
            for aov_data in identifier_data.values():
                count += len(aov_data)
        return count
    
    def saveCache(self, hierarchy):
        """Save cache to disk"""
        try:
            cache_data = {
                'hierarchy': hierarchy,
                'scan_time': time.time(),
                'version': '1.0'
            }
            
            temp_file = self.cache_file + ".tmp"
            with open(temp_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            os.rename(temp_file, self.cache_file)
            
            self._current_cache = hierarchy
            self._last_scan_time = cache_data['scan_time']
            self._debug("Cache saved successfully")
        except Exception as e:
            self._debug(f"ERROR saving cache: {e}")
    
    def startBackgroundUpdate(self, shots_folder):
        """Start background thread that continuously updates cache"""
        if self.update_thread and self.update_thread.is_alive():
            return
        
        self.stop_thread = False
        self.update_thread = threading.Thread(
            target=self._backgroundUpdateWorker,
            args=(shots_folder,),
            daemon=True
        )
        self.update_thread.start()
    
    def stopBackgroundUpdate(self):
        """Stop background update thread"""
        self.stop_thread = True
        if self.update_thread:
            self.update_thread.join(timeout=2.0)
    
    def _backgroundUpdateWorker(self, shots_folder):
        """Background worker that scans for changes and updates cache"""
        time.sleep(2)
        
        while not self.stop_thread:
            try:
                new_hierarchy = self._scanProjectStructure(shots_folder)
                
                with self.cache_lock:
                    if new_hierarchy != self._current_cache:
                        self.saveCache(new_hierarchy)
                        try:
                            QMetaObject.invokeMethod(
                                self,
                                "cacheUpdated",
                                Qt.QueuedConnection,
                                Q_ARG(dict, new_hierarchy)
                            )
                        except Exception as e:
                            self._debug(f"ERROR emitting signal: {e}")
                
                for i in range(30):
                    if self.stop_thread:
                        break
                    time.sleep(1)
            except Exception as e:
                self._debug(f"ERROR in background cache update: {e}")
                time.sleep(10)
    
    def _scanProjectStructure(self, shots_folder):
        """Scan project structure and return hierarchy"""
        hierarchy = {}
        
        if not os.path.exists(shots_folder):
            return hierarchy
        
        try:
            sequences = os.listdir(shots_folder)
        except Exception:
            return hierarchy
        
        for sequence in sequences:
            sequence_path = os.path.join(shots_folder, sequence)
            if not os.path.isdir(sequence_path):
                continue
            
            try:
                shots = os.listdir(sequence_path)
            except Exception:
                continue
            
            for shot in shots:
                shot_path = os.path.join(sequence_path, shot)
                if not os.path.isdir(shot_path):
                    continue
                
                renders_path = os.path.join(shot_path, "Renders")
                if not os.path.exists(renders_path):
                    continue
                
                shot_name = f"{sequence}-{shot}"
                self._scanShot(renders_path, shot_name, hierarchy)
        
        return hierarchy
    
    def _scanShot(self, renders_path, shot_name, hierarchy):
        """Scan a shot"""
        if shot_name not in hierarchy:
            hierarchy[shot_name] = {}
        
        try:
            render_type_folders = os.listdir(renders_path)
        except Exception:
            return
        
        for render_type_or_identifier in render_type_folders:
            render_type_path = os.path.join(renders_path, render_type_or_identifier)
            if not os.path.isdir(render_type_path):
                continue
            
            if render_type_or_identifier.lower() in ['2drender', '3drender', 'render']:
                try:
                    identifiers = os.listdir(render_type_path)
                except Exception:
                    continue
                    
                for identifier in identifiers:
                    identifier_path = os.path.join(render_type_path, identifier)
                    if not os.path.isdir(identifier_path):
                        continue
                    self._scanIdentifierFolder(identifier_path, shot_name, identifier, hierarchy)
            else:
                try:
                    render_types = os.listdir(render_type_path)
                except Exception:
                    continue
                    
                for render_type in render_types:
                    inner_render_type_path = os.path.join(render_type_path, render_type)
                    if not os.path.isdir(inner_render_type_path):
                        continue
                    if render_type.lower() in ['2drender', '3drender', 'render']:
                        self._scanIdentifierFolder(
                            inner_render_type_path, shot_name, render_type_or_identifier, hierarchy
                        )
    
    def _scanIdentifierFolder(self, identifier_path, shot_name, identifier, hierarchy):
        """Scan identifier folder"""
        try:
            version_folders = os.listdir(identifier_path)
        except Exception:
            return
        
        for version in version_folders:
            version_path = os.path.join(identifier_path, version)
            
            if not os.path.isdir(version_path):
                continue
            if not version.startswith('v') or len(version) < 5:
                continue
            
            version_match = version.split()[0]
            if not version_match[1:5].isdigit():
                continue
            
            try:
                version_contents = os.listdir(version_path)
            except Exception:
                continue
            
            if not version_contents:
                continue
            
            has_subfolders = False
            has_files = False
            
            for item in version_contents[:5]:
                if item.startswith('_'):
                    continue
                item_path = os.path.join(version_path, item)
                if os.path.isdir(item_path):
                    has_subfolders = True
                    break
                elif os.path.isfile(item_path):
                    has_files = True
            
            if has_subfolders:
                aov_folders = [item for item in version_contents 
                             if not item.startswith('_') and os.path.isdir(os.path.join(version_path, item))]
                
                for aov in aov_folders:
                    aov_path = os.path.join(version_path, aov)
                    
                    try:
                        aov_files = [f for f in os.listdir(aov_path) 
                                   if os.path.isfile(os.path.join(aov_path, f)) 
                                   and not f.startswith('_')
                                   and f.lower().endswith(('.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx'))]
                        aov_files.sort()
                    except Exception:
                        continue
                    
                    if not aov_files:
                        continue
                    
                    if identifier not in hierarchy[shot_name]:
                        hierarchy[shot_name][identifier] = {}
                    if aov not in hierarchy[shot_name][identifier]:
                        hierarchy[shot_name][identifier][aov] = {}
                    
                    hierarchy[shot_name][identifier][aov][version] = {
                        'path': aov_path,
                        'firstFile': aov_files[0]
                    }
            elif has_files:
                try:
                    version_files = [f for f in os.listdir(version_path) 
                                   if os.path.isfile(os.path.join(version_path, f)) 
                                   and not f.startswith('_')
                                   and f.lower().endswith(('.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx'))]
                    version_files.sort()
                except Exception:
                    continue
                
                if not version_files:
                    continue
                
                aov = "main"
                
                if identifier not in hierarchy[shot_name]:
                    hierarchy[shot_name][identifier] = {}
                if aov not in hierarchy[shot_name][identifier]:
                    hierarchy[shot_name][identifier][aov] = {}
                
                hierarchy[shot_name][identifier][aov][version] = {
                    'path': version_path,
                    'firstFile': version_files[0]
                }


class ImportShots(QObject):
    """Handles importing footage from Prism structure with smart caching"""
    
    def __init__(self, tracker):
        super(ImportShots, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main
        self.cache_manager = None
        self._debug_buffer = []
        
        try:
            project_path = self._getProjectPath()
            
            if project_path:
                cache_dir = os.path.join(project_path, "00_Pipeline", "AE_cache")
                self.cache_manager = CacheManager(self.core, cache_dir, debug_callback=None)
                self.cache_manager.cacheUpdated.connect(self.onCacheUpdated)
                
                shots_folder = self._getShotsFolder()
                if shots_folder:
                    self.cache_manager.startBackgroundUpdate(shots_folder)
        except Exception as e:
            print(f"ERROR initializing cache manager: {e}")
    
    def __del__(self):
        """Cleanup when destroyed"""
        if hasattr(self, 'cache_manager') and self.cache_manager:
            self.cache_manager.stopBackgroundUpdate()
    
    def _bufferDebug(self, message):
        """Buffer debug messages before UI is ready"""
        self._debug_buffer.append(message)
        print(message)
    
    def _flushDebugBuffer(self):
        """Flush buffered debug messages to UI"""
        if hasattr(self, 'debugConsole') and self._debug_buffer:
            for msg in self._debug_buffer:
                self.debugLog(msg)
            self._debug_buffer = []
    
    def _getProjectPath(self):
        """Get project path"""
        project_path = getattr(self.core, 'projectPath', None)

        if project_path and os.path.exists(project_path):
            return project_path

        try:
            current_file = self.core.getCurrentFileName()

            if current_file:
                current_file = current_file.replace("'", "").replace('"', '').strip()
        except Exception:
            current_file = None

        if current_file and os.path.exists(current_file):
            parts = current_file.replace("\\", "/").split("/")
            
            try:
                prod_index = -1
                if "02_Production" in parts:
                    prod_index = parts.index("02_Production")
                elif "03_Production" in parts:
                    prod_index = parts.index("03_Production")
                
                if prod_index > 0:
                    project_path = "/".join(parts[:prod_index])
                    
                    if os.path.exists(project_path):
                        try:
                            if not getattr(self.core, 'projectPath', None):
                                self.core.changeProject(project_path)
                        except Exception:
                            pass
                        return project_path
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _getShotsFolder(self):
        """Get the shots folder path"""
        project_path = self._getProjectPath()
        if not project_path:
            return None
        
        shots_folder = os.path.join(project_path, "03_Production", "Shots")
        if not os.path.exists(shots_folder):
            shots_folder = os.path.join(project_path, "02_Production", "Shots")
        if not os.path.exists(shots_folder):
            shots_folder = os.path.join(project_path, "Shots")
        
        return shots_folder if os.path.exists(shots_folder) else None

    @err_catcher(name=__name__)
    def openImportDialog(self):
        """Open the import shots dialog"""
        currentFile = self.getCurrentAEFile()
        shotName = "Unknown Shot"
        if currentFile:
            shotPath = self.getShotPathFromFile(currentFile)
            if shotPath:
                parts = shotPath.replace("\\", "/").split("/")
                if "Shots" in parts:
                    shotsIdx = parts.index("Shots")
                    if len(parts) > shotsIdx + 2:
                        shotName = f"{parts[shotsIdx + 1]}-{parts[shotsIdx + 2]}"
        
        # Check if dialog already exists and is still valid
        if hasattr(self, 'dlg_import') and self.dlg_import is not None:
            try:
                # Check if the widget still exists and hasn't been destroyed
                if not self.dlg_import.isHidden():
                    self.dlg_import.raise_()
                    self.dlg_import.activateWindow()
                    self.dlg_import.showNormal()  # Restore if minimized
                    return True
            except (RuntimeError, AttributeError):
                # Dialog was destroyed, clean up and create new one
                self.dlg_import = None

        # Create new dialog
        self.dlg_import = QDialog(self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None)
        self.dlg_import.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
        )
        self.dlg_import.setWindowTitle(f"Prism - Import Footage ({shotName})")
        self.dlg_import.resize(1000, 700)

        # Clean up when dialog is closed
        self.dlg_import.finished.connect(lambda: setattr(self, 'dlg_import', None))

        self.setupImportUI()
        self.loadAvailableFootage()
        self.dlg_import.show()
        return True
    
    def setupImportUI(self):
        """Build the import dialog UI"""
        layout = QVBoxLayout()
        self.dlg_import.setLayout(layout)
        
        infoLabel = QLabel("<b>Select footage to import into After Effects</b><br>"
                          "Browse available renders from your Prism project structure.")
        layout.addWidget(infoLabel)
        
        topToolbar = QHBoxLayout()

        # API Mode indicator
        self.api_mode_label = QLabel("🔷 API Mode")
        self.api_mode_label.setStyleSheet(
            "color: #00aaff; font-weight: bold; padding: 2px 8px; background: #1a1a2e; border-radius: 3px;"
        )
        self.api_mode_label.setToolTip("Using Prism API for loading footage")
        topToolbar.addWidget(self.api_mode_label)

        self.btn_expandAll = QPushButton("Expand All")
        self.btn_collapseAll = QPushButton("Collapse All")
        topToolbar.addWidget(self.btn_expandAll)
        topToolbar.addWidget(self.btn_collapseAll)
        topToolbar.addStretch()

        self.cache_status_label = QLabel("Ready")
        self.cache_status_label.setStyleSheet("color: gray;")
        topToolbar.addWidget(self.cache_status_label)
        
        versionFilterLabel = QLabel("Show last:")
        self.spin_versionCount = QSpinBox()
        self.spin_versionCount.setMinimum(0)
        self.spin_versionCount.setMaximum(999)
        self.spin_versionCount.setValue(1)
        self.spin_versionCount.setSpecialValueText("All versions")
        self.spin_versionCount.setToolTip("Limit to most recent N versions (0 = show all)")
        self.spin_versionCount.setMinimumWidth(100)
        self.spin_versionCount.valueChanged.connect(self.applyVersionFilter)
        topToolbar.addWidget(versionFilterLabel)
        topToolbar.addWidget(self.spin_versionCount)
        
        self.btn_refresh_import = QPushButton("Refresh")
        self.btn_refresh_import.clicked.connect(self.forceRefreshFootage)
        topToolbar.addWidget(self.btn_refresh_import)

        self.btn_test_api = QPushButton("Test API")
        self.btn_test_api.setToolTip("Test if Prism API is accessible")
        self.btn_test_api.clicked.connect(self.runAPITest)
        topToolbar.addWidget(self.btn_test_api)
        
        self.chk_currentShot = QCheckBox("Current Shot")
        self.chk_currentShot.setChecked(True)
        self.chk_currentShot.setToolTip("Show only footage from the current shot")
        self.chk_currentShot.stateChanged.connect(self.applyFilters)
        topToolbar.addWidget(self.chk_currentShot)
        
        self.chk_lightingOnly = QCheckBox("Lighting Only")
        self.chk_lightingOnly.setChecked(False)
        self.chk_lightingOnly.setToolTip("Show only identifiers that start with 'Lighting'")
        self.chk_lightingOnly.stateChanged.connect(self.applyFilters)
        topToolbar.addWidget(self.chk_lightingOnly)
        
        layout.addLayout(topToolbar)
        
        filterBar = QHBoxLayout()
        filterLabel = QLabel("Filter:")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Search by Shot, Identifier, AOV, or Version...")
        self.filter_input.textChanged.connect(self.applyFilters)
        filterBar.addWidget(filterLabel)
        filterBar.addWidget(self.filter_input, 1)
        layout.addLayout(filterBar)
        
        self.tw_import = QTreeWidget()
        self.tw_import.setHeaderLabels(["Shot / Identifier / AOV / Version", "Path"])
        self.tw_import.setColumnWidth(0, 600)
        self.tw_import.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tw_import.viewport().installEventFilter(self)
        layout.addWidget(self.tw_import)
        
        self.btn_expandAll.clicked.connect(self.tw_import.expandAll)
        self.btn_collapseAll.clicked.connect(self.tw_import.collapseAll)
        self.tw_import.itemExpanded.connect(self.onItemExpanded)
        
        self.statsLabel = QLabel()
        self.statsLabel.setStyleSheet("padding: 5px; background-color: #2b2b2b;")
        layout.addWidget(self.statsLabel)
        
        self.statusBar = QLabel()
        self.statusBar.setStyleSheet("padding: 5px;")
        layout.addWidget(self.statusBar)
        
        self.debugWidget = QWidget()
        debugLayout = QVBoxLayout()
        debugLayout.setContentsMargins(0, 0, 0, 0)
        self.debugWidget.setLayout(debugLayout)
        
        debugHeader = QHBoxLayout()
        self.btn_toggleDebug = QPushButton("[v] Show Debug Log")
        self.btn_toggleDebug.clicked.connect(self.toggleDebugConsole)
        self.btn_toggleDebug.setStyleSheet("text-align: left; padding: 5px;")
        debugHeader.addWidget(self.btn_toggleDebug)
        
        self.btn_clearDebug = QPushButton("Clear")
        self.btn_clearDebug.clicked.connect(self.clearDebugLog)
        debugHeader.addWidget(self.btn_clearDebug)
        debugLayout.addLayout(debugHeader)
        
        self.debugConsole = QTextEdit()
        self.debugConsole.setReadOnly(True)
        self.debugConsole.setMaximumHeight(200)
        self.debugConsole.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace; font-size: 9pt;"
        )
        self.debugConsole.setVisible(False)
        debugLayout.addWidget(self.debugConsole)
        
        layout.addWidget(self.debugWidget)
        
        self._flushDebugBuffer()
        
        if self.cache_manager:
            self.cache_manager.debug_callback = self.debugLog
        
        bottomToolbar = QHBoxLayout()
        
        self.chk_asSequence = QCheckBox("Import as Sequence")
        self.chk_asSequence.setChecked(True)
        self.chk_asSequence.setToolTip("Import image sequences. Uncheck to import as individual frames.")
        bottomToolbar.addWidget(self.chk_asSequence)
        bottomToolbar.addStretch()
        
        self.btn_import = QPushButton("Import Selected")
        self.btn_import.clicked.connect(self.importSelected)
        self.btn_import.setMinimumWidth(120)
        bottomToolbar.addWidget(self.btn_import)
        
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.dlg_import.close)
        self.btn_close.setMinimumWidth(100)
        bottomToolbar.addWidget(self.btn_close)
        
        layout.addLayout(bottomToolbar)
    
    def onCacheUpdated(self, new_hierarchy):
        """Called when cache is updated in background"""
        if hasattr(self, 'dlg_import') and self.dlg_import.isVisible():
            self.cache_status_label.setText("[OK] Cache updated")
            self.cache_status_label.setStyleSheet("color: green;")
            QTimer.singleShot(3000, lambda: self.cache_status_label.setText("[OK] Cache is fresh"))
    
    def toggleDebugConsole(self):
        """Toggle debug console visibility"""
        isVisible = self.debugConsole.isVisible()
        self.debugConsole.setVisible(not isVisible)
        self.btn_toggleDebug.setText("[^] Hide Debug Log" if not isVisible else "[v] Show Debug Log")

    @err_catcher(name=__name__)
    def runAPITest(self):
        """Run Prism API test and show results"""
        self.debugConsole.setVisible(True)
        self.btn_toggleDebug.setText("[^] Hide Debug Log")
        self.clearDebugLog()
        self.debugLog("<b>===== PRISM API TEST =====</b>")

        results = self.testPrismAPI()

        if results['api_available']:
            self.debugLog("<b style='color: green;'>✓ API TEST PASSED</b>")
            self.debugLog(f"Shots in project: {results['shots_count']}")
            self.debugLog(f"Sample identifiers found: {len(results['sample_identifiers'])}")
            self.core.popup(
                "Prism API Test: PASSED ✓\n\n"
                f"Shots: {results['shots_count']}\n"
                f"Entities: {'✓' if results['entities_available'] else '✗'}\n"
                f"MediaProducts: {'✓' if results['mediaProducts_available'] else '✗'}\n\n"
                "Check debug console for details."
            )
        else:
            self.debugLog(f"<b style='color: red;'>✗ API TEST FAILED</b>")
            self.debugLog(f"Error: {results.get('error', 'Unknown error')}")
            self.core.popup(
                f"Prism API Test: FAILED ✗\n\n"
                f"Error: {results.get('error', 'Unknown error')}\n\n"
                "Check debug console for details."
            )
    
    def clearDebugLog(self):
        """Clear debug console"""
        self.debugConsole.clear()
    
    def debugLog(self, message):
        """Add message to debug console"""
        self.debugConsole.append(message)
        scrollbar = self.debugConsole.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def eventFilter(self, obj, event):
        """Event filter to handle shift+click on tree items"""
        if obj == self.tw_import.viewport():
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    if event.modifiers() & Qt.ShiftModifier:
                        item = self.tw_import.itemAt(event.pos())
                        if item:
                            rect = self.tw_import.visualItemRect(item)
                            if event.pos().x() < rect.left():
                                self._shift_expand_item = item
                                return False
            elif event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                    if self.tw_import.selectedItems():
                        return False
                    return True
        return super(ImportShots, self).eventFilter(obj, event)
    
    def onItemExpanded(self, item):
        """Handle item expansion - check if shift+click was used"""
        if hasattr(self, '_shift_expand_item') and self._shift_expand_item == item:
            self.expandAllChildren(item)
            delattr(self, '_shift_expand_item')
    
    def expandAllChildren(self, item):
        """Recursively expand all children of an item"""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setExpanded(True)
            self.expandAllChildren(child)
    
    def applyFilters(self):
        """Apply all active filters"""
        searchText = self.filter_input.text().lower()
        currentShotOnly = self.chk_currentShot.isChecked()
        lightingOnly = self.chk_lightingOnly.isChecked()
        versionLimit = self.spin_versionCount.value()
        
        currentShotName = None
        
        if currentShotOnly:
            currentFile = self.getCurrentAEFile()
            if currentFile:
                shotPath = self.getShotPathFromFile(currentFile)
                if shotPath:
                    parts = [p for p in shotPath.replace("\\", "/").split("/") if p]
                    if "Shots" in parts:
                        shotsIdx = parts.index("Shots")
                        if len(parts) > shotsIdx + 2:
                            currentShotName = f"{parts[shotsIdx + 1]}-{parts[shotsIdx + 2]}"
        
        def filterItem(item):
            userData = item.data(0, Qt.UserRole)
            itemText = item.text(0).lower()
            
            if userData and userData.get('type') == 'group':
                level = userData.get('level')
                
                if level == 'shot':
                    shotMatch = True
                    if currentShotOnly and currentShotName:
                        shotMatch = (item.text(0) == currentShotName)
                    if not shotMatch:
                        item.setHidden(True)
                        return False
                
                if level == 'identifier' and lightingOnly:
                    if not item.text(0).startswith("Lighting"):
                        item.setHidden(True)
                        return False
                
                if level == 'aov' and versionLimit > 0:
                    visibleVersionCount = 0
                    for i in range(item.childCount()):
                        child = item.child(i)
                        childData = child.data(0, Qt.UserRole)
                        if childData and childData.get('type') == 'version':
                            if visibleVersionCount < versionLimit:
                                childText = child.text(0).lower()
                                textMatch = searchText == "" or searchText in childText
                                child.setHidden(not textMatch)
                                if textMatch:
                                    visibleVersionCount += 1
                            else:
                                child.setHidden(True)
                
                hasVisibleChild = False
                for i in range(item.childCount()):
                    childVisible = filterItem(item.child(i))
                    if childVisible:
                        hasVisibleChild = True
                
                textMatch = searchText == "" or searchText in itemText
                shouldShow = hasVisibleChild or (textMatch and hasVisibleChild is not None)
                
                if level in ['shot', 'identifier', 'aov']:
                    shouldShow = hasVisibleChild
                
                item.setHidden(not shouldShow)
                return shouldShow
            elif userData and userData.get('type') == 'version':
                return not item.isHidden()
            
            return True
        
        for i in range(self.tw_import.topLevelItemCount()):
            filterItem(self.tw_import.topLevelItem(i))
    
    def applyVersionFilter(self):
        """Called when version limit spinner changes"""
        self.applyFilters()
    
    @err_catcher(name=__name__)
    def forceRefreshFootage(self):
        """Force immediate rescan using Prism API"""
        self.statusBar.setText("Refreshing from Prism API...")
        self.cache_status_label.setText("🔄 Refreshing...")
        self.cache_status_label.setStyleSheet("color: #ffaa00;")

        try:
            hierarchy = self.loadAvailableFootageFromAPI()

            self.tw_import.clear()
            self.buildImportTree(hierarchy)

            totalShots = len(hierarchy)
            totalVersions = sum(self.countVersions(hierarchy.get(shot, {})) for shot in hierarchy)
            self.statsLabel.setText(f"Total shots: {totalShots}, versions: {totalVersions}")

            self.applyFilters()

            for i in range(self.tw_import.topLevelItemCount()):
                if not self.tw_import.topLevelItem(i).isHidden():
                    self.tw_import.topLevelItem(i).setExpanded(True)

            self.statusBar.setText("Footage refreshed from Prism")
            self.cache_status_label.setText("✓ Refreshed")
            self.cache_status_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.core.popup(f"Error refreshing footage from Prism API:\n{str(e)}")
            self.statusBar.setText("Error refreshing footage")
            self.cache_status_label.setText("✗ Error")
            self.cache_status_label.setStyleSheet("color: #ff4444;")
    
    @err_catcher(name=__name__)
    def loadAvailableFootageFromAPI(self):
        """Load available footage using Prism API instead of file system"""
        self.debugLog("<b>[API MODE] Loading footage from Prism API (not file system)</b>")
        hierarchy = {}
        currentShotEntity = self.getCurrentShotEntity()

        # Get shots to query
        if self.chk_currentShot.isChecked() and currentShotEntity:
            shots = [currentShotEntity]
            self.debugLog(f"[API] Filtering to current shot only")
        else:
            shots = self.getAllShotsFromProject()
            self.debugLog(f"[API] Loading all shots from project: {len(shots) if shots else 0} shots found")

        # Media types to query
        taskTypes = [
            ("3d", "3drenders"),
            ("2d", "2drenders"),
            ("playblast", "playblasts"),
            ("external", "externalMedia")
        ]

        for shot in shots:
            shotName = self.core.entities.getShotName(shot)
            if not shotName:
                continue

            for taskType, mediaType in taskTypes:
                # Get identifiers for this shot/mediaType
                context = shot.copy()
                context["mediaType"] = mediaType

                try:
                    identifiers = self.core.getTaskNames(
                        taskType=taskType,
                        context=context,
                        addDepartments=False
                    )
                    self.debugLog(
                        f"[API] {shotName}/{mediaType}: "
                        f"Found {len(identifiers) if identifiers else 0} identifiers"
                    )
                except Exception as e:
                    self.debugLog(f"[API] Error getting tasks for {shotName}/{mediaType}: {str(e)}")
                    continue

                for identifier in identifiers:
                    # Get ALL versions for this identifier
                    idContext = context.copy()
                    idContext["identifier"] = identifier

                    try:
                        versions = self.core.mediaProducts.getVersionsFromIdentifier(
                            identifier=idContext["identifier"]
                        )
                        self.debugLog(f"[API] {identifier}: Found {len(versions) if versions else 0} versions via API")
                    except Exception as e:
                        self.debugLog(f"[API] Error getting versions for {identifier}: {str(e)}")
                        continue

                    for version in versions:
                        # Get AOVs for this version
                        if mediaType == "3drenders":
                            try:
                                aovs = self.core.mediaProducts.getAOVsFromVersion(version)
                            except Exception as e:
                                self.debugLog(f"[API] Error getting AOVs for {identifier}: {str(e)}")
                                continue
                        else:
                            aovs = [version]  # 2D/playblasts don't have AOVs

                        for aov in aovs:
                            # Get file paths
                            try:
                                filepaths = self.core.mediaProducts.getFilesFromContext(aov)
                            except Exception as e:
                                self.debugLog(f"Error getting files for {identifier}: {str(e)}")
                                continue

                            if not filepaths:
                                continue

                            # Extract version string
                            versionStr = version.get("version", "unknown")

                            # Build hierarchy entry
                            if shotName not in hierarchy:
                                hierarchy[shotName] = {}

                            if identifier not in hierarchy[shotName]:
                                hierarchy[shotName][identifier] = {}

                            aovName = aov.get("aov", "main")
                            if aovName not in hierarchy[shotName][identifier]:
                                hierarchy[shotName][identifier][aovName] = {}

                            hierarchy[shotName][identifier][aovName][versionStr] = {
                                "path": os.path.dirname(filepaths[0]),
                                "firstFile": os.path.basename(filepaths[0])
                            }

        # Summary of what was loaded via API
        totalShots = len(hierarchy)
        totalVersions = sum(self.countVersions(hierarchy.get(shot, {})) for shot in hierarchy)
        self.debugLog(f"<b>[API] Loaded from Prism API: {totalShots} shots, {totalVersions} versions total</b>")
        return hierarchy

    @err_catcher(name=__name__)
    def testPrismAPI(self):
        """Test function to verify Prism API is accessible - run from Python console"""
        results = {
            'api_available': False,
            'entities_available': False,
            'mediaProducts_available': False,
            'shots_count': 0,
            'sample_shot': None,
            'sample_identifiers': [],
            'error': None
        }

        try:
            # Check if core.mediaProducts exists
            if hasattr(self.core, 'mediaProducts'):
                results['mediaProducts_available'] = True
                self.debugLog("[TEST] ✓ core.mediaProducts is available")

                # Check if getVersionsFromIdentifier exists
                if hasattr(self.core.mediaProducts, 'getVersionsFromIdentifier'):
                    self.debugLog("[TEST] ✓ getVersionsFromIdentifier method exists")
                else:
                    results['error'] = "getVersionsFromIdentifier method not found"
                    return results
            else:
                results['error'] = "core.mediaProducts not available"
                return results

            # Check if core.entities exists
            if hasattr(self.core, 'entities'):
                results['entities_available'] = True
                self.debugLog("[TEST] ✓ core.entities is available")

                # Try to get shots
                try:
                    shots = self.core.entities.getShots()
                    results['shots_count'] = len(shots) if shots else 0
                    if shots:
                        results['sample_shot'] = shots[0]
                        shotName = self.core.entities.getShotName(shots[0])
                        self.debugLog(f"[TEST] ✓ Found {results['shots_count']} shots, sample: {shotName}")
                except Exception as e:
                    results['error'] = f"Error getting shots: {str(e)}"
                    return results

            # Try to get task names (identifiers)
            if results['sample_shot']:
                try:
                    context = results['sample_shot'].copy()
                    context["mediaType"] = "3drenders"
                    identifiers = self.core.getTaskNames(
                        taskType="3d",
                        context=context,
                        addDepartments=False
                    )
                    results['sample_identifiers'] = identifiers[:5] if identifiers else []
                    self.debugLog(
                        f"[TEST] ✓ Found {len(identifiers) if identifiers else 0} identifiers for sample shot"
                    )
                    if identifiers:
                        self.debugLog(f"[TEST]   Sample identifiers: {', '.join(identifiers[:3])}")
                except Exception as e:
                    results['error'] = f"Error getting task names: {str(e)}"
                    return results

            results['api_available'] = True
            self.debugLog("<b>[TEST] ✓✓✓ Prism API is fully accessible!</b>")

        except Exception as e:
            import traceback
            results['error'] = f"{str(e)}\n{traceback.format_exc()}"
            self.debugLog(f"[TEST] ✗ Error: {str(e)}")

        return results

    @err_catcher(name=__name__)
    def getCurrentShotEntity(self):
        """Get the current shot entity from the AE project file"""
        currentFile = self.getCurrentAEFile()
        if not currentFile:
            return None

        # Extract shot info from file path
        fileName = os.path.basename(currentFile).replace(".aep", "")
        try:
            shotEntity = self.core.entities.getShotEntity(fileName)
            return shotEntity
        except Exception:
            return None

    @err_catcher(name=__name__)
    def getAllShotsFromProject(self):
        """Get all shots from the current Prism project"""
        try:
            # Use Prism's entity browser to get all shots
            shots = self.core.entities.getShots()
            return shots if shots else []
        except Exception:
            return []

    @err_catcher(name=__name__)
    def loadAvailableFootage(self):
        """Load available footage using Prism API"""
        self.tw_import.clear()
        self.clearDebugLog()
        self._flushDebugBuffer()

        # Clear indication that we're using API mode
        self.debugLog("<b>===== HELIX AE IMPORT DIALOG =====</b>")
        self.debugLog("<b>Mode: Prism API (no file system scanning)</b>")
        self.debugLog("If you see this, the import is using Prism's database!")
        self.debugLog("=======================================")

        self.statusBar.setText("Loading from Prism API...")
        self.cache_status_label.setText("🔄 Querying Prism...")
        self.cache_status_label.setStyleSheet("color: #ffaa00;")

        try:
            hierarchy = self.loadAvailableFootageFromAPI()

            if not hierarchy:
                self.statusBar.setText("No footage found in Prism")
                self.cache_status_label.setText("⚠ No footage")
                self.cache_status_label.setStyleSheet("color: orange;")
                self.core.popup(
                    "No footage found in Prism project.\n\n"
                    "Make sure you have renders registered in the Prism database."
                )
                return

            self.buildImportTree(hierarchy)

            totalShots = len(hierarchy)
            totalVersions = sum(self.countVersions(hierarchy.get(shot, {})) for shot in hierarchy)

            self.statsLabel.setText(f"Total shots: {totalShots}, versions: {totalVersions} (from Prism API)")
            self.statusBar.setText("Loaded from Prism API")
            self.cache_status_label.setText("✓ Prism API")
            self.cache_status_label.setStyleSheet("color: #00ff00; font-weight: bold;")

            self.applyFilters()

            for i in range(self.tw_import.topLevelItemCount()):
                if not self.tw_import.topLevelItem(i).isHidden():
                    self.tw_import.topLevelItem(i).setExpanded(True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.core.popup(f"Error loading footage from Prism API:\n{str(e)}")
            self.statusBar.setText("Error loading footage")
            self.cache_status_label.setText("✗ API Error")
            self.cache_status_label.setStyleSheet("color: #ff4444;")
    
    def _loadWithoutCache(self):
        """Fallback: Load without cache"""
        try:
            shots_folder = self._getShotsFolder()
            if not shots_folder:
                self.core.popup("Could not find Shots folder in project.")
                self.statusBar.setText("Error: Shots folder not found")
                return
            
            hierarchy = {}
            totalShots = 0
            
            try:
                sequences = os.listdir(shots_folder)
            except Exception:
                return
            
            for sequence in sequences:
                sequence_path = os.path.join(shots_folder, sequence)
                if not os.path.isdir(sequence_path):
                    continue
                
                try:
                    shots = os.listdir(sequence_path)
                except Exception:
                    continue
                
                for shot in shots:
                    shot_path = os.path.join(sequence_path, shot)
                    if not os.path.isdir(shot_path):
                        continue
                    
                    renders_path = os.path.join(shot_path, "Renders")
                    if not os.path.exists(renders_path):
                        continue
                    
                    totalShots += 1
                    self.statusBar.setText(f"Scanning {sequence}/{shot}... ({totalShots} shots)")
                    QApplication.processEvents()
                    
                    shot_name = f"{sequence}-{shot}"
                    
                    if self.cache_manager:
                        self.cache_manager._scanShot(renders_path, shot_name, hierarchy)
                    else:
                        self._scanShotInline(renders_path, shot_name, hierarchy)
            
            totalVersions = sum(self.countVersions(hierarchy.get(shot, {})) for shot in hierarchy)
            
            self.buildImportTree(hierarchy)
            self.statsLabel.setText(f"Total shots: {totalShots}, versions: {totalVersions}")
            self.statusBar.setText("Footage loaded")
            
            self.applyFilters()
            
            for i in range(self.tw_import.topLevelItemCount()):
                if not self.tw_import.topLevelItem(i).isHidden():
                    self.tw_import.topLevelItem(i).setExpanded(True)
        except Exception as e:
            import traceback
            self.core.popup(f"Error loading footage:\n{str(e)}\n\n{traceback.format_exc()}")
            self.statusBar.setText("Error loading footage")
    
    def _scanShotInline(self, renders_path, shot_name, hierarchy):
        """Inline shot scanning when cache manager not available"""
        if shot_name not in hierarchy:
            hierarchy[shot_name] = {}
        
        try:
            render_type_folders = os.listdir(renders_path)
        except Exception:
            return
        
        for render_type_or_identifier in render_type_folders:
            render_type_path = os.path.join(renders_path, render_type_or_identifier)
            if not os.path.isdir(render_type_path):
                continue
            
            if render_type_or_identifier.lower() in ['2drender', '3drender', 'render']:
                try:
                    identifiers = os.listdir(render_type_path)
                except Exception:
                    continue
                    
                for identifier in identifiers:
                    identifier_path = os.path.join(render_type_path, identifier)
                    if not os.path.isdir(identifier_path):
                        continue
                    self._scanIdentifierFolderInline(identifier_path, shot_name, identifier, hierarchy)
    
    def _scanIdentifierFolderInline(self, identifier_path, shot_name, identifier, hierarchy):
        """Inline identifier scanning"""
        try:
            version_folders = os.listdir(identifier_path)
        except Exception:
            return
        
        for version in version_folders:
            version_path = os.path.join(identifier_path, version)
            
            if not os.path.isdir(version_path):
                continue
            if not version.startswith('v') or len(version) < 5:
                continue
            
            try:
                version_contents = os.listdir(version_path)
            except Exception:
                continue
            
            if not version_contents:
                continue
            
            has_subfolders = any(os.path.isdir(os.path.join(version_path, item)) 
                               for item in version_contents[:5] if not item.startswith('_'))
            
            if has_subfolders:
                aov_folders = [item for item in version_contents 
                             if not item.startswith('_') and os.path.isdir(os.path.join(version_path, item))]
                
                for aov in aov_folders:
                    aov_path = os.path.join(version_path, aov)
                    
                    try:
                        aov_files = [f for f in os.listdir(aov_path) 
                                   if os.path.isfile(os.path.join(aov_path, f)) 
                                   and not f.startswith('_')
                                   and f.lower().endswith(('.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx'))]
                        aov_files.sort()
                    except Exception:
                        continue
                    
                    if not aov_files:
                        continue
                    
                    if identifier not in hierarchy[shot_name]:
                        hierarchy[shot_name][identifier] = {}
                    if aov not in hierarchy[shot_name][identifier]:
                        hierarchy[shot_name][identifier][aov] = {}
                    
                    hierarchy[shot_name][identifier][aov][version] = {
                        'path': aov_path,
                        'firstFile': aov_files[0]
                    }
    
    def countVersions(self, identifierDict):
        """Count total versions in a shot's hierarchy"""
        count = 0
        for identifier, aovDict in identifierDict.items():
            for aov, versionDict in aovDict.items():
                count += len(versionDict)
        return count
    
    def getCurrentAEFile(self):
        """Get the current After Effects file path"""
        try:
            scpt = "app.project.file ? app.project.file.fsName : 'None'"
            result = self.main.ae_core.executeAppleScript(scpt)
            filePath = str(result).replace("b'", "").replace("'", "").strip()
            
            if filePath == 'None' or not filePath:
                return None
            
            filePath = filePath.replace("\\", "/")
            return filePath if os.path.exists(filePath) else None
        except Exception:
            return None
    
    def getShotPathFromFile(self, filePath):
        """Extract shot path from file path"""
        try:
            parts = filePath.replace("\\", "/").split("/")
            
            if "Scenefiles" in parts:
                scenefilesIndex = parts.index("Scenefiles")
                shotPath = "/".join(parts[:scenefilesIndex])
                return shotPath if os.path.exists(shotPath) else None
            
            if "Shots" in parts:
                shotsIndex = parts.index("Shots")
                if len(parts) > shotsIndex + 2:
                    shotPath = "/".join(parts[:shotsIndex + 3])
                    return shotPath if os.path.exists(shotPath) else None
            
            return None
        except Exception:
            return None
    
    def buildImportTree(self, hierarchy):
        """Build tree widget from hierarchy"""
        for shot in sorted(hierarchy.keys()):
            shotItem = QTreeWidgetItem()
            shotItem.setText(0, shot)
            shotItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'shot'})
            shotItem.setForeground(0, QBrush(QColor(150, 180, 255)))
            font = shotItem.font(0)
            font.setBold(True)
            shotItem.setFont(0, font)
            self.tw_import.addTopLevelItem(shotItem)
            
            for identifier in sorted(hierarchy[shot].keys()):
                identifierItem = QTreeWidgetItem()
                identifierItem.setText(0, identifier)
                identifierItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'identifier'})
                identifierItem.setForeground(0, QBrush(QColor(180, 180, 220)))
                font = identifierItem.font(0)
                font.setBold(True)
                identifierItem.setFont(0, font)
                shotItem.addChild(identifierItem)
                
                for aov in sorted(hierarchy[shot][identifier].keys()):
                    aovItem = QTreeWidgetItem()
                    aovItem.setText(0, aov)
                    aovItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'aov'})
                    aovItem.setForeground(0, QBrush(QColor(200, 200, 240)))
                    identifierItem.addChild(aovItem)
                    
                    for version in sorted(hierarchy[shot][identifier][aov].keys(), reverse=True):
                        data = hierarchy[shot][identifier][aov][version]

                        # Get FPS from global config or version metadata
                        fps = self.core.getConfig("global", "fps", defaultValue=25.0)
                        if 'fps' in data:
                            fps = data['fps']

                        versionItem = QTreeWidgetItem()
                        versionItem.setText(0, version)
                        versionItem.setText(1, data['path'])

                        userData = {
                            'type': 'version',
                            'shot': shot,
                            'identifier': identifier,
                            'aov': aov,
                            'version': version,
                            'path': data['path'],
                            'firstFile': data['firstFile'],
                            'fps': fps
                        }
                        versionItem.setData(0, Qt.UserRole, userData)
                        aovItem.addChild(versionItem)
    
    @err_catcher(name=__name__)
    def importSelected(self):
        """Import selected footage into After Effects"""
        selectedItems = []
        
        def findVersionItems(item):
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'version':
                selectedItems.append(item)
            for i in range(item.childCount()):
                findVersionItems(item.child(i))
        
        for item in self.tw_import.selectedItems():
            findVersionItems(item)
        
        if not selectedItems:
            self.core.popup("Please select one or more versions to import.")
            return
        
        reply = QMessageBox.question(
            self.dlg_import,
            "Import Footage",
            f"Import {len(selectedItems)} footage item(s) into After Effects?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        asSequence = self.chk_asSequence.isChecked()
        successCount = 0
        failedCount = 0
        failedItems = []
        
        self.statusBar.setText(f"Importing {len(selectedItems)} items...")
        QApplication.processEvents()
        
        for item in selectedItems:
            userData = item.data(0, Qt.UserRole)
            try:
                success = self.importFootageItem(userData, asSequence)
                if success:
                    successCount += 1
                else:
                    failedCount += 1
                    item_label = f"{userData['shot']}/{userData['identifier']}/{userData['aov']}/{userData['version']}"
                    failedItems.append(item_label)
            except Exception as e:
                failedCount += 1
                item_label = f"{userData['shot']}/{userData['identifier']}/{userData['aov']}/{userData['version']}"
                failedItems.append(f"{item_label}: {str(e)}")
        
        if failedCount > 0:
            failedList = "\n".join(failedItems[:10])
            if len(failedItems) > 10:
                failedList += f"\n... and {len(failedItems) - 10} more"
            
            self.tracker.showSelectableMessage(
                "Import Complete with Errors",
                f"Successfully imported: {successCount}\n"
                f"Failed: {failedCount}\n\n"
                f"Failed items:\n{failedList}"
            )
        else:
            self.core.popup(f"Successfully imported {successCount} footage item(s)!")
        
        self.statusBar.setText(f"Import complete: {successCount} succeeded, {failedCount} failed")
        
        if hasattr(self.tracker, 'tw_footage'):
            self.tracker.loadFootageData()
    
    def importFootageItem(self, userData, asSequence):
        """Import a single footage item into After Effects with proper folder structure"""
        import platform
        
        path = userData['path']
        firstFile = userData['firstFile']
        shot = userData['shot']
        identifier = userData['identifier']
        aov = userData['aov']
        fps = userData['fps']
        
        if not firstFile:
            return False
        
        fullPath = os.path.join(path, firstFile)
        
        if not os.path.exists(fullPath):
            return False
        
        if platform.system() == "Windows":
            aePath = fullPath.replace('\\', '\\\\\\\\')
        else:
            aePath = fullPath.replace('\\', '/')
        
        if asSequence:
            scpt = f"""
            try {{
                var file = new File('{aePath}');
                if (!file.exists) {{
                    'ERROR: File not found - ' + file.fsName;
                }} else {{
                    var prismFolder = null, shotFolder = null, identifierFolder = null;
                    
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        if (app.project.item(i) instanceof FolderItem && 
                            app.project.item(i).name === 'Prism imports') {{
                            prismFolder = app.project.item(i);
                            break;
                        }}
                    }}
                    if (!prismFolder) prismFolder = app.project.items.addFolder('Prism imports');
                    
                    for (var i = 1; i <= prismFolder.numItems; i++) {{
                        if (prismFolder.item(i) instanceof FolderItem && 
                            prismFolder.item(i).name === '{shot}') {{
                            shotFolder = prismFolder.item(i);
                            break;
                        }}
                    }}
                    if (!shotFolder) shotFolder = prismFolder.items.addFolder('{shot}');
                    
                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        if (shotFolder.item(i) instanceof FolderItem && 
                            shotFolder.item(i).name === '{identifier}') {{
                            identifierFolder = shotFolder.item(i);
                            break;
                        }}
                    }}
                    if (!identifierFolder) identifierFolder = shotFolder.items.addFolder('{identifier}');
                    
                    var importOptions = new ImportOptions(file);
                    importOptions.sequence = true;
                    var footage = app.project.importFile(importOptions);
                    
                    if (footage && footage.mainSource) {{
                        footage.mainSource.conformFrameRate = {fps};
                    }}
                    
                    footage.parentFolder = identifierFolder;
                    footage.name = '{aov}';
                    
                    'SUCCESS:' + footage.id;
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
        else:
            scpt = f"""
            try {{
                var file = new File('{aePath}');
                if (!file.exists) {{
                    'ERROR: File not found - ' + file.fsName;
                }} else {{
                    var prismFolder = null, shotFolder = null, identifierFolder = null;
                    
                    for (var i = 1; i <= app.project.numItems; i++) {{
                        if (app.project.item(i) instanceof FolderItem && 
                            app.project.item(i).name === 'Prism imports') {{
                            prismFolder = app.project.item(i);
                            break;
                        }}
                    }}
                    if (!prismFolder) prismFolder = app.project.items.addFolder('Prism imports');
                    
                    for (var i = 1; i <= prismFolder.numItems; i++) {{
                        if (prismFolder.item(i) instanceof FolderItem && 
                            prismFolder.item(i).name === '{shot}') {{
                            shotFolder = prismFolder.item(i);
                            break;
                        }}
                    }}
                    if (!shotFolder) shotFolder = prismFolder.items.addFolder('{shot}');
                    
                    for (var i = 1; i <= shotFolder.numItems; i++) {{
                        if (shotFolder.item(i) instanceof FolderItem && 
                            shotFolder.item(i).name === '{identifier}') {{
                            identifierFolder = shotFolder.item(i);
                            break;
                        }}
                    }}
                    if (!identifierFolder) identifierFolder = shotFolder.items.addFolder('{identifier}');
                    
                    var importOptions = new ImportOptions(file);
                    var footage = app.project.importFile(importOptions);
                    
                    footage.parentFolder = identifierFolder;
                    footage.name = '{aov}';
                    
                    'SUCCESS:' + footage.id;
                }}
            }} catch(e) {{
                'ERROR: ' + e.toString();
            }}
            """
        
        result = self.main.ae_core.executeAppleScript(scpt)
        resultStr = str(result).replace("b'", "").replace("'", "").strip()
        
        return 'SUCCESS' in resultStr