# -*- coding: utf-8 -*-
"""
UI Setup Module - Handles all UI construction
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *
import sys
import fnmatch

from .ui_components import NoHoverDelegate
from qtpy.QtCore import QPropertyAnimation, QEasingCurve
from qtpy.QtCore import QStringListModel


class FloatingSearchBar(QWidget):
    """Modern hovering search bar with shadow, rounded corners, and fade animation"""

    def __init__(self, parent, on_apply_callback, on_hide_callback=None):
        super(FloatingSearchBar, self).__init__(parent)

        # Window flags for floating behavior
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.StrongFocus)  # IMPORTANT: Allow widget to receive focus

        self.on_apply_callback = on_apply_callback
        self.on_hide_callback = on_hide_callback
        self.search_edit = None
        self.setupUI()

        # Install event filter on the application to catch clicks outside
        QApplication.instance().installEventFilter(self)

    def setupUI(self):
        """Setup the search bar UI"""
        # Fixed size
        self.resize(300, 52)

        # Container widget (rounded background)
        self.container = QWidget(self)
        self.container.setObjectName("container")
        self.container.setFixedSize(self.size())

        # Search field
        self.search_edit = QLineEdit(self.container)
        self.search_edit.setPlaceholderText("Search...")
        self.search_edit.setFrame(False)
        self.search_edit.setText("")  # Start empty
        self.search_edit.setStyleSheet("""
            QLineEdit {
                color: #ddd;
                font-size: 14px;
                background: transparent;
            }
        """)

        # Layout
        layout = QHBoxLayout(self.container)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addWidget(self.search_edit)

        # Style
        self.container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(40, 40, 40, 250);
                border-radius: 14px;
            }
        """)

        # Setup keyboard shortcuts (after search_edit is added to layout)
        self.enter_shortcut = QShortcut(QKeySequence("Return"), self)
        self.enter_shortcut.setEnabled(True)
        self.enter_shortcut.activated.connect(self.onEnterPressed)

        # Numpad Enter key support
        self.numpad_enter_shortcut = QShortcut(QKeySequence(Qt.Key_Enter), self)
        self.numpad_enter_shortcut.setEnabled(True)
        self.numpad_enter_shortcut.activated.connect(self.onEnterPressed)

        self.escape_shortcut = QShortcut(QKeySequence("Escape"), self)
        self.escape_shortcut.setEnabled(True)
        self.escape_shortcut.activated.connect(self.onEscapePressed)

    def onEnterPressed(self):
        """Handle Enter key - apply filter and close"""
        if self.on_apply_callback:
            self.on_apply_callback(self.search_edit.text())
        self.hide()
        # Update visibility state
        if self.on_hide_callback:
            self.on_hide_callback()

    def onEscapePressed(self):
        """Handle Escape key - close without applying"""
        self.hide()
        # Update visibility state
        if self.on_hide_callback:
            self.on_hide_callback()

    def showAnimated(self, text_to_restore=""):
        """Show with fade-in animation and focus"""
        # Restore text if provided
        if text_to_restore:
            self.search_edit.setText(text_to_restore)

        # Set opacity to 0 for fade-in
        self.setWindowOpacity(0.0)

        # Position at cursor (centered)
        cursor_pos = QCursor.pos()
        self.move(cursor_pos.x() - self.width() // 2, cursor_pos.y() - self.height() // 2)

        # Show the window
        self.show()

        # Bring to front & activate (CRITICAL for Windows focus)
        self.raise_()
        self.activateWindow()

        # Fade-in animation
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(180)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_anim.start(QAbstractAnimation.DeleteWhenStopped)

        # Focus on search field with zero delay (proper sequence)
        QTimer.singleShot(0, self._focusSearchEdit)

    def _focusSearchEdit(self):
        """Focus on the search edit and select all text"""
        self.search_edit.setFocus(Qt.ActiveWindowFocusReason)
        self.search_edit.selectAll()

    def focusOutEvent(self, event):
        """Auto-hide when focus is lost"""
        # Use a small delay to avoid hiding when clicking completer
        QTimer.singleShot(100, self._checkFocus)

    def _checkFocus(self):
        """Check if we should hide (focus not in this widget or completer)"""
        focus_widget = QApplication.focusWidget()
        if focus_widget is None or not self.isAncestorOf(focus_widget):
            self.hide()
            if self.on_hide_callback:
                self.on_hide_callback()

    def eventFilter(self, obj, event):
        """Event filter to catch clicks outside the search bar"""
        # Only process events when we're visible
        if not self.isVisible():
            return False

        # Check for mouse button press on other widgets
        if event.type() == QEvent.MouseButtonPress:
            # If the click is not on our search bar or its children, hide it
            if obj != self and not self.isAncestorOf(obj):
                # Delay hiding to avoid interfering with other events
                QTimer.singleShot(0, self._hideIfNotFocused)

        return False

    def _hideIfNotFocused(self):
        """Hide if focus is not on this widget"""
        if not self.hasFocus() and not self.isAncestorOf(QApplication.focusWidget()):
            self.hide()
            if self.on_hide_callback:
                self.on_hide_callback()


class DebugConsoleKeyPressFilter(QObject):
    """Event filter to catch backtick key press for debug console toggle"""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            text = event.text()
            # Log to help debug (visible in main Prism console if output not captured)
            import sys
            print(f"[DEBUG KEY] Key: {key}, Text: '{text}', Modifiers: {event.modifiers()}", file=sys.__stderr__)
            sys.__stderr__.flush()
            # Try: QuoteLeft, Apostrophe, or direct ASCII check
            if key == Qt.Key_QuoteLeft or key == Qt.Key_Apostrophe or text == '`' or text == '~':
                print("[DEBUG KEY] Backtick detected!", file=sys.__stderr__)
                sys.__stderr__.flush()
                self.callback()
                return True
        return False


class DebugConsole:
    """Debug console output handler"""
    def __init__(self, text_edit):
        self.text_edit = text_edit

    def _is_valid(self):
        """Check if the widget is still valid"""
        try:
            # Use sip to check if the C++ object is deleted
            from qtpy import sip
            return not sip.isdeleted(self.text_edit)
        except Exception:
            # If sip check fails, try accessing the widget
            try:
                _ = self.text_edit.objectName()
                return True
            except Exception:
                return False

    def write(self, text):
        if text.strip():  # Only write non-empty text
            if self._is_valid():
                try:
                    self.text_edit.appendPlainText(text.strip())
                except RuntimeError:
                    pass

    def flush(self):
        pass


class UISetup(QObject):
    """Handles all UI setup and construction"""

    def __init__(self, tracker):
        super(UISetup, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main
        self.debug_console_visible = False
        self.last_filter_search = ""  # Store last search string

    def createCustomTitleBar(self):
        """Create a custom title bar with title and close button"""
        # Create title bar widget
        title_bar = QWidget()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #3a3a3a;
            }
        """)

        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar.setLayout(title_bar_layout)

        # Title label on the left
        title_label = QLabel("Footage Version Tracker")
        title_label.setStyleSheet("""
            QLabel {
                color: #ccc;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        title_bar_layout.addWidget(title_label)

        title_bar_layout.addStretch()

        # Lock window button (hidden)
        self.tracker.btn_lockWindow = QPushButton("🔓")
        self.tracker.btn_lockWindow.setCheckable(True)
        self.tracker.btn_lockWindow.hide()

        # Always on top button
        self.tracker.btn_alwaysOnTop = QPushButton("📌")
        self.tracker.btn_alwaysOnTop.setCheckable(True)
        self.tracker.btn_alwaysOnTop.setFixedSize(24, 24)
        self.tracker.btn_alwaysOnTop.setToolTip("Keep window on top of other windows")
        font = QFont()
        font.setFamily("Segoe UI Emoji")
        font.setPointSize(10)
        self.tracker.btn_alwaysOnTop.setFont(font)
        self.tracker.btn_alwaysOnTop.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ccc;
                border: none;
                font-family: "Segoe UI Emoji";
                font-size: 14px;
                border-radius: 2px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: white;
            }
            QPushButton:checked {
                background-color: rgb(129, 84, 32);
                color: white;
            }
        """)
        settings = QSettings("Prism", "AfterEffectsPlugin")
        saved_always_on_top = settings.value("FootageTracker/AlwaysOnTop", False, type=bool)
        self.tracker.btn_alwaysOnTop.setChecked(saved_always_on_top)
        if saved_always_on_top:
            base_flags = Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
            self.tracker.dlg_footage.setWindowFlags(base_flags | Qt.WindowStaysOnTopHint)
        self.tracker.btn_alwaysOnTop.clicked.connect(self.toggleAlwaysOnTop)
        title_bar_layout.addWidget(self.tracker.btn_alwaysOnTop)


        # Return the title bar widget
        return title_bar

    def setupFootageUI(self):
        """Build the footage tracker UI"""
        import time

        ui_start = time.perf_counter()

        # Create the main layout structure
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.tracker.dlg_footage.setLayout(main_layout)
        layout_end = time.perf_counter()
        print(f"[TIMING]   UI - Create main layout: {layout_end - ui_start:.4f}s")

        # Custom title bar (added first to main layout)
        title_bar_start = time.perf_counter()
        title_bar = self.createCustomTitleBar()
        main_layout.addWidget(title_bar)
        # Set the title bar as the draggable area for the dialog
        if hasattr(self.tracker.dlg_footage, 'setTitleBarWidget'):
            self.tracker.dlg_footage.setTitleBarWidget(title_bar)
        title_bar_end = time.perf_counter()
        print(f"[TIMING]   UI - Custom title bar: {title_bar_end - title_bar_start:.4f}s")

        # Content wrapper for the rest of the UI (with margins)
        content_wrapper = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(2)
        content_wrapper.setLayout(content_layout)
        main_layout.addWidget(content_wrapper)

        # Top toolbar
        toolbar_start = time.perf_counter()
        topToolbar = QHBoxLayout()

        self.tracker.btn_expandAll = QPushButton("Expand All")
        self.tracker.btn_collapseAll = QPushButton("Collapse All")
        self.tracker.btn_listAllShots = QPushButton("List all shots")

        # Hide expand/collapse/list buttons - Shift+Click on items now handles this
        self.tracker.btn_expandAll.hide()
        self.tracker.btn_collapseAll.hide()
        self.tracker.btn_listAllShots.hide()

        topToolbar.addWidget(self.tracker.btn_expandAll)
        topToolbar.addWidget(self.tracker.btn_collapseAll)
        topToolbar.addWidget(self.tracker.btn_listAllShots)

        topToolbar.addStretch()

        # Import button (hidden)
        self.tracker.btn_import = QPushButton("Import...")
        self.tracker.btn_import.clicked.connect(self.tracker.openImportDialog)
        self.tracker.btn_import.setToolTip("Import footage from Prism project")
        self.tracker.btn_import.setMinimumWidth(100)
        self.tracker.btn_import.hide()  # Hide the import button
        topToolbar.addWidget(self.tracker.btn_import)

        # Archive button
        archive_style_start = time.perf_counter()
        self.tracker.btn_archive = QPushButton("📁 Export Archive")
        self.tracker.btn_archive.clicked.connect(self.tracker.exportArchiveInfo)
        self.tracker.btn_archive.setToolTip("Export archive information to JSON file")
        self.tracker.btn_archive.setMinimumWidth(140)
        self.tracker.btn_archive.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        archive_style_end = time.perf_counter()
        print(f"[TIMING]   UI - Archive button style: {archive_style_end - archive_style_start:.4f}s")

        topToolbar.addWidget(self.tracker.btn_archive)
        self.tracker.btn_archive.hide()

        content_layout.addLayout(topToolbar)
        toolbar_end = time.perf_counter()
        print(f"[TIMING]   UI - Top toolbar: {toolbar_end - toolbar_start:.4f}s")

        # Modern floating search bar
        filter_start = time.perf_counter()
        self.filter_bar_widget = FloatingSearchBar(self.tracker.dlg_footage, self.onSearchApply, self.onSearchHide)

        # Setup autocomplete completer
        self.filter_completer = QCompleter()
        self.filter_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.filter_completer.setFilterMode(Qt.MatchContains)
        self.filter_completer.setCompletionMode(QCompleter.PopupCompletion)
        self.filter_bar_widget.search_edit.setCompleter(self.filter_completer)

        # Status combo (hidden, created for backward compatibility)
        self.tracker.status_combo = QComboBox()
        self.tracker.status_combo.addItems(["All", "Latest", "Outdated"])
        self.tracker.status_combo.currentTextChanged.connect(self.applyFilter)
        self.tracker.status_combo.hide()

        # Expose filter_input for backward compatibility
        self.tracker.filter_input = self.filter_bar_widget.search_edit

        self.filter_bar_visible = False

        filter_end = time.perf_counter()
        print(f"[TIMING]   UI - Filter bar: {filter_end - filter_start:.4f}s")

        # Add Ctrl+Space shortcut to toggle filter bar (on main dialog)
        self.filter_toggle_shortcut = QShortcut(
            QKeySequence("Ctrl+Space"), self.tracker.dlg_footage, self.toggleFilterBar
        )
        self.filter_toggle_shortcut.setEnabled(True)

        # Tree widget
        tree_start = time.perf_counter()
        self.tracker.tw_footage = QTreeWidget()
        self.tracker.tw_footage.setItemDelegate(NoHoverDelegate(self.tracker.tw_footage))
        tree_style_start = time.perf_counter()
        self.tracker.tw_footage.setStyleSheet("""
            QTreeWidget {
                selection-background-color: rgba(100, 150, 255, 100);
            }
            QTreeWidget::item {
                background-color: transparent;
            }
            QTreeWidget::item:hover {
                background-color: none;
            }
            QTreeWidget::item:selected {
                background-color: rgba(100, 150, 255, 100);
            }
            QTreeWidget::item:selected:hover {
                background-color: rgba(100, 150, 255, 100);
            }
        """)
        tree_style_end = time.perf_counter()
        print(f"[TIMING]   UI - Tree widget style: {tree_style_end - tree_style_start:.4f}s")

        self.tracker.tw_footage.setHeaderLabels([
            "Shot / Identifier / AOV", "Version", "Status", "Frame Range", "FPS", "Resolution", "Full Path"
        ])
        self.tracker.tw_footage.setColumnWidth(0, 350)
        self.tracker.tw_footage.setColumnWidth(1, 120)
        self.tracker.tw_footage.setColumnWidth(2, 100)
        self.tracker.tw_footage.setColumnWidth(3, 150)
        self.tracker.tw_footage.setColumnWidth(4, 60)
        self.tracker.tw_footage.setColumnWidth(5, 80)
        self.tracker.tw_footage.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tracker.tw_footage.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tracker.tw_footage.customContextMenuRequested.connect(self.tracker.showFootageContextMenu)

        # Install event filter
        self.tracker.tw_footage.installEventFilter(self.tracker.tree_ops)
        self.tracker.tw_footage.viewport().installEventFilter(self.tracker.tree_ops)

        # Add Delete key shortcut for deleting selected items
        self.delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.tracker.tw_footage)
        self.delete_shortcut.setEnabled(True)
        self.delete_shortcut.activated.connect(self.onDeleteKeyPressed)

        content_layout.addWidget(self.tracker.tw_footage)
        tree_end = time.perf_counter()
        print(f"[TIMING]   UI - Tree widget: {tree_end - tree_start:.4f}s")

        # Connect expand/collapse buttons
        self.tracker.btn_expandAll.clicked.connect(self.tracker.tw_footage.expandAll)
        self.tracker.btn_collapseAll.clicked.connect(self.tracker.tw_footage.collapseAll)

        # Connect List all shots button
        kitsu_start = time.perf_counter()
        if self.tracker.kitsu:
            self.tracker.btn_listAllShots.clicked.connect(self.tracker.openKitsuShotList)
            # Don't load Kitsu data here - it will be loaded during loadFootageData()
            # Just set a generic tooltip that will be updated after data loads
            self.tracker.btn_listAllShots.setToolTip("Open Kitsu shot list (loading...)")
        else:
            self.tracker.btn_listAllShots.clicked.connect(self.tracker.showKitsuError)
            self.tracker.btn_listAllShots.setToolTip("Kitsu integration not available - Click for details")
            self.tracker.btn_listAllShots.setStyleSheet("QPushButton { color: #888888; }")
        kitsu_end = time.perf_counter()
        print(f"[TIMING]   UI - Kitsu setup: {kitsu_end - kitsu_start:.4f}s (deferred Kitsu loading to data load)")

        # Statistics bar with Check Issues button
        stats_start = time.perf_counter()
        statsBarLayout = QHBoxLayout()
        statsBarLayout.setContentsMargins(0, 0, 0, 0)

        # Check Issues button
        self.tracker.btn_checkIssues = QPushButton("⚠ Check Issues")
        self.tracker.btn_checkIssues.clicked.connect(self.tracker.runStartupWarningsCheck)
        self.tracker.btn_checkIssues.setToolTip(
            "Check for outdated versions, FPS, frame range, and resolution mismatches"
        )
        check_style_start = time.perf_counter()
        self.tracker.btn_checkIssues.setStyleSheet("""
            QPushButton {
                background-color: rgb(129, 84, 32);
                color: white;
                border: none;
                padding: 5px 10px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgb(150, 100, 50);
            }
            QPushButton:disabled {
                background-color: #555;
                color: #888;
            }
        """)
        check_style_end = time.perf_counter()
        print(f"[TIMING]   UI - Check Issues button style: {check_style_end - check_style_start:.4f}s")
        statsBarLayout.addWidget(self.tracker.btn_checkIssues)

        # Statistics label
        self.tracker.statsLabel = QLabel()
        self.tracker.statsLabel.setTextFormat(Qt.RichText)
        self.tracker.statsLabel.setStyleSheet("padding: 5px; background-color: #2b2b2b;")
        statsBarLayout.addWidget(self.tracker.statsLabel, 1)  # Give label stretch to fill remaining space

        # Refresh menu button (icon on right side of stats bar)
        self.tracker.btn_refreshMenu = QPushButton("⟳")
        self.tracker.btn_refreshMenu.setToolTip("Refresh options...")
        self.tracker.btn_refreshMenu.setFixedSize(32, 24)
        font = QFont()
        font.setFamily("Segoe UI Symbol")
        font.setPointSize(10)
        self.tracker.btn_refreshMenu.setFont(font)
        self.tracker.btn_refreshMenu.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #ccc;
                border: none;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: rgb(129, 84, 32);
                border-radius: 2px;
            }
        """)
        self.tracker.btn_refreshMenu.clicked.connect(self.showRefreshMenu)
        statsBarLayout.addWidget(self.tracker.btn_refreshMenu)

        statsBarWidget = QWidget()
        statsBarWidget.setLayout(statsBarLayout)
        statsBarWidget.setStyleSheet("background-color: #2b2b2b;")
        content_layout.addWidget(statsBarWidget)

        stats_end = time.perf_counter()
        print(f"[TIMING]   UI - Stats bar: {stats_end - stats_start:.4f}s")

        # Status bar (hidden by default)
        status_start = time.perf_counter()
        self.tracker.dlg_footage.statusBar = QLabel()
        self.tracker.dlg_footage.statusBar.setStyleSheet("padding: 5px;")
        content_layout.addWidget(self.tracker.dlg_footage.statusBar)
        self.tracker.dlg_footage.statusBar.hide()  # Hidden by default
        status_end = time.perf_counter()
        print(f"[TIMING]   UI - Status bar: {status_end - status_start:.4f}s")

        # Bottom toolbar
        bottom_start = time.perf_counter()
        bottomToolbar = QHBoxLayout()

        self.tracker.btn_updateAll = QPushButton("Update All Outdated")
        self.tracker.btn_updateAll.clicked.connect(self.tracker.updateAllOutdated)
        self.tracker.btn_updateSelected = QPushButton("Update Selected Outdated")
        self.tracker.btn_updateSelected.clicked.connect(self.tracker.updateSelectedOutdated)
        self.tracker.btn_updateFPS = QPushButton("Update FPS")
        self.tracker.btn_updateFPS.clicked.connect(self.tracker.updateAllFPS)
        self.tracker.btn_batchFPS = QPushButton("Set FPS for Selected")
        self.tracker.btn_batchFPS.clicked.connect(self.tracker.batchUpdateFPS)

        # Hide update buttons
        self.tracker.btn_updateAll.hide()
        self.tracker.btn_updateSelected.hide()
        self.tracker.btn_updateFPS.hide()
        self.tracker.btn_batchFPS.hide()

        bottomToolbar.addWidget(self.tracker.btn_updateAll)
        bottomToolbar.addWidget(self.tracker.btn_updateSelected)
        bottomToolbar.addWidget(self.tracker.btn_updateFPS)
        bottomToolbar.addWidget(self.tracker.btn_batchFPS)

        self.tracker.btn_toggleDebug = QPushButton("▶ Debug")
        self.tracker.btn_toggleDebug.setCheckable(True)
        self.tracker.btn_toggleDebug.clicked.connect(self.toggleDebugConsole)
        self.tracker.btn_toggleDebug.hide()  # Hidden by default, shown with backtick
        debug_style_start = time.perf_counter()
        self.tracker.btn_toggleDebug.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                padding: 5px 10px;
                text-align: left;
            }
            QPushButton:hover {
                color: #ccc;
            }
            QPushButton:checked {
                color: #2196F3;
            }
        """)
        debug_style_end = time.perf_counter()
        bottomToolbar.addWidget(self.tracker.btn_toggleDebug)

        # Add debug console toggle shortcut using QShortcut (Ctrl+Shift+D)
        self.debug_shortcut = QShortcut(
            QKeySequence("Ctrl+Shift+D"), self.tracker.dlg_footage,
            self.toggleDebugConsoleWithShortcut
        )
        self.debug_shortcut.setEnabled(True)

        bottomToolbar.addStretch()

        self.tracker.btn_close = QPushButton("Close")
        self.tracker.btn_close.clicked.connect(self.tracker.dlg_footage.close)
        self.tracker.btn_close.setMinimumWidth(100)
        # Hide close button
        self.tracker.btn_close.hide()
        bottomToolbar.addWidget(self.tracker.btn_close)

        content_layout.addLayout(bottomToolbar)
        bottom_end = time.perf_counter()
        print(f"[TIMING]   UI - Bottom toolbar: {bottom_end - bottom_start:.4f}s")

        # Debug Console (collapsible)
        debug_console_start = time.perf_counter()
        self.tracker.debug_console = QPlainTextEdit()
        self.tracker.debug_console.setMaximumHeight(0)  # Start collapsed
        self.tracker.debug_console.setMinimumHeight(0)
        self.tracker.debug_console.setReadOnly(True)
        self.tracker.debug_console.setVisible(False)  # Completely hidden initially
        debug_style_start = time.perf_counter()
        self.tracker.debug_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: none;
                margin: 0;
                padding: 0;
            }
        """)
        debug_style_end = time.perf_counter()
        print(f"[TIMING]   UI - Debug console style: {debug_style_end - debug_style_start:.4f}s")

        # Console is always in layout, just collapsed to height 0
        content_layout.addWidget(self.tracker.debug_console)

        # Setup context menu for debug console
        self.tracker.debug_console.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tracker.debug_console.customContextMenuRequested.connect(self.showDebugConsoleContextMenu)

        # Setup debug output handler - ALWAYS capture output
        handler_start = time.perf_counter()
        self.debug_console_handler = DebugConsole(self.tracker.debug_console)

        # Immediately redirect stdout to capture ALL output from the start
        import sys
        if hasattr(sys, '__stdout__'):
            sys.stdout = self.debug_console_handler
            sys.stderr = self.debug_console_handler
        handler_end = time.perf_counter()
        print(f"[TIMING]   UI - Debug console handler: {handler_end - handler_start:.4f}s")

        # Add resize grip to bottom-right corner for resizing
        self.tracker.resize_grip = QSizeGrip(self.tracker.dlg_footage)
        self.tracker.resize_grip.setFixedSize(20, 20)
        self.tracker.resize_grip.setStyleSheet("background: transparent;")

        # Connect to dialog show event to position the grip
        self.tracker.dlg_footage.finished.connect(lambda: setattr(self.tracker, 'resize_grip', None))

        ui_total_end = time.perf_counter()
        print(f"[TIMING] UI setup TOTAL: {ui_total_end - ui_start:.4f}s")
        print(f"[TIMING] UI setup breakdown complete")
        print(f"{'='*80}")

    def toggleDebugConsole(self):
        """Toggle debug console visibility with animated collapse/expand"""
        self.debug_console_visible = not self.debug_console_visible

        if self.debug_console_visible:
            # Make sure widget is visible first
            self.tracker.debug_console.setVisible(True)
            self.tracker.btn_toggleDebug.setText("▼ Debug")
            self.tracker.btn_toggleDebug.setChecked(True)

            # Animate from 0 to 150
            self._animate_height(0, 150)
        else:
            # Collapse: animate from current height to 0, then hide
            self.tracker.btn_toggleDebug.setText("▶ Debug")
            self.tracker.btn_toggleDebug.setChecked(False)

            # Create animation for collapsing
            self._animate_height(self.tracker.debug_console.height(), 0)

            # Hide after animation completes (via a timer)
            from qtpy.QtCore import QTimer
            QTimer.singleShot(300, lambda: self.tracker.debug_console.setVisible(not self.debug_console_visible))

    def toggleDebugConsoleWithShortcut(self):
        """Toggle debug console with Ctrl+Shift+D - also shows/hides the toggle button"""
        # First time: show button and expand console
        if self.tracker.btn_toggleDebug.isHidden():
            self.tracker.btn_toggleDebug.show()
            # Force expand regardless of current state
            self.debug_console_visible = True
            self.tracker.debug_console.setVisible(True)
            self.tracker.btn_toggleDebug.setText("▼ Debug")
            self.tracker.btn_toggleDebug.setChecked(True)
            self._animate_height(0, 150)
        else:
            # Subsequent times: toggle visibility
            self.toggleDebugConsole()
            self.tracker.btn_toggleDebug.setChecked(False)
            self.tracker.btn_toggleDebug.hide()
            self._animate_height(current_height, 0)

    def _animate_height(self, start_height, end_height):
        """Animate the debug console height"""
        self.animation = QPropertyAnimation(self.tracker.debug_console, b"maximumHeight")
        self.animation.setDuration(200)  # 200ms animation
        self.animation.setStartValue(start_height)
        self.animation.setEndValue(end_height)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

        # Also animate minimumHeight to match
        self.animation_min = QPropertyAnimation(self.tracker.debug_console, b"minimumHeight")
        self.animation_min.setDuration(200)
        self.animation_min.setStartValue(start_height)
        self.animation_min.setEndValue(end_height)
        self.animation_min.setEasingCurve(QEasingCurve.OutCubic)

        self.animation.start()
        self.animation_min.start()

    def clearDebugConsole(self):
        """Clear the debug console"""
        self.tracker.debug_console.clear()

    def showDebugConsoleContextMenu(self, position):
        """Show context menu for debug console"""
        menu = QMenu(self.tracker.debug_console)
        menu.setStyleSheet("""
            QMenu {
                background-color: #3a3a3a;
                color: #ddd;
                border: 1px solid #555;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: #2196F3;
            }
        """)

        clear_action = menu.addAction("Clear")
        clear_action.triggered.connect(self.clearDebugConsole)

        select_all_action = menu.addAction("Select All")
        select_all_action.triggered.connect(self.tracker.debug_console.selectAll)

        menu.exec_(self.tracker.debug_console.mapToGlobal(position))

    def showRefreshMenu(self):
        """Show refresh options menu"""
        menu = QMenu(self.tracker.btn_refreshMenu)
        menu.setStyleSheet("""
            QMenu {
                background-color: #3a3a3a;
                color: #ddd;
                border: 1px solid #555;
            }
            QMenu::item {
                padding: 5px 20px;
            }
            QMenu::item:selected {
                background-color: #2196F3;
            }
        """)

        # Footage refresh option
        footage_action = menu.addAction("Footage")
        footage_action.setToolTip("Reload footage hierarchy from After Effects (uses cached Kitsu data)")
        footage_action.triggered.connect(self.tracker.loadFootageData)

        # Kitsu refresh option
        kitsu_action = menu.addAction("Kitsu")
        kitsu_action.setToolTip("Force refresh Kitsu data from server (bypasses 5-min cache)")
        kitsu_action.triggered.connect(self.tracker.forceRefreshKitsuData)

        # Show menu at current cursor position
        menu.exec_(QCursor.pos())

    def toggleWindowLock(self):
        """Toggle window lock (prevent moving/resizing)"""
        is_locked = self.tracker.btn_lockWindow.isChecked()
        dlg = self.tracker.dlg_footage

        if is_locked:
            # Lock window - remove move and resize capabilities
            dlg.setFixedSize(dlg.size())
            self.tracker.btn_lockWindow.setText("🔒")
            self.tracker.btn_lockWindow.setToolTip("Window locked - click to unlock")
        else:
            # Unlock window - restore move and resize capabilities
            dlg.setFixedSize(QSize.WildCard, QSize.WildCard)  # Remove size constraint
            # Restore minimum size
            dlg.setMinimumSize(400, 300)
            self.tracker.btn_lockWindow.setText("🔓")
            self.tracker.btn_lockWindow.setToolTip("Lock window (prevent moving/resizing)")

    def toggleAlwaysOnTop(self):
        """Toggle always on top"""
        is_on_top = self.tracker.btn_alwaysOnTop.isChecked()
        dlg = self.tracker.dlg_footage

        # Save setting
        settings = QSettings("Prism", "AfterEffectsPlugin")
        settings.setValue("FootageTracker/AlwaysOnTop", is_on_top)

        # Always rebuild from base flags to avoid stripping window decorations
        base_flags = Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
        if is_on_top:
            dlg.setWindowFlags(base_flags | Qt.WindowStaysOnTopHint)
        else:
            dlg.setWindowFlags(base_flags)

        dlg.show()
        dlg.activateWindow()

    def applyFilter(self):
        """Filter tree items based on search text with wildcard support"""
        searchText = self.tracker.filter_input.text().lower()
        statusFilter = self.tracker.status_combo.currentText()

        def matchPattern(text, pattern):
            """Match text against pattern with wildcard support"""
            if not pattern:
                return True
            # Use fnmatch for wildcard matching (*, ?, [])
            try:
                return fnmatch.fnmatchcase(text, pattern)
            except Exception:
                # If pattern is invalid, fall back to substring matching
                return pattern in text

        def filterItem(item, parentMatched=False):
            userData = item.data(0, Qt.UserRole)
            itemText = item.text(0).lower()

            if userData and userData.get('type') == 'group':
                # Check if this group matches the search
                groupMatches = matchPattern(itemText, searchText)

                hasVisibleChild = False
                for i in range(item.childCount()):
                    # If this group matched, show all children without filtering
                    # If parent matched, pass True to children
                    childVisible = filterItem(item.child(i), parentMatched=groupMatches or parentMatched)
                    if childVisible:
                        hasVisibleChild = True

                # Show if: has visible children, OR text matches, OR parent matched
                shouldShow = hasVisibleChild or groupMatches or parentMatched
                item.setHidden(not shouldShow)
                return shouldShow
            elif userData and userData.get('type') == 'footage':
                # If parent matched, show all footage without filtering
                if parentMatched:
                    item.setHidden(False)
                    return True

                textMatch = matchPattern(itemText, searchText)
                statusMatch = True
                if statusFilter == "Latest":
                    statusMatch = item.data(2, Qt.UserRole + 1) == "current"
                elif statusFilter == "Outdated":
                    statusMatch = item.data(2, Qt.UserRole + 1) == "outdated"
                shouldShow = textMatch and statusMatch
                item.setHidden(not shouldShow)
                return shouldShow
            else:
                # For items without userData or unknown type
                if parentMatched:
                    item.setHidden(False)
                    return True
                shouldShow = matchPattern(itemText, searchText)
                item.setHidden(not shouldShow)
                return shouldShow

        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            filterItem(self.tracker.tw_footage.topLevelItem(i))

    def toggleFilterBar(self):
        """Toggle filter bar visibility with Ctrl+Space key"""
        self.filter_bar_visible = not self.filter_bar_visible

        if self.filter_bar_visible:
            # Update suggestions first
            self.updateFilterSuggestions()
            # Show with animation and restore last search
            self.filter_bar_widget.showAnimated(self.last_filter_search)
        else:
            # Hide filter bar
            self.filter_bar_widget.hide()

    def onSearchApply(self, search_text):
        """Callback when search is applied (Enter pressed)"""
        # Save the search text
        self.last_filter_search = search_text
        # Apply the filter
        self.applyFilter()

    def onSearchHide(self):
        """Callback when search bar is hidden (Escape or click outside)"""
        self.filter_bar_visible = False

    def onDeleteKeyPressed(self):
        """Handle Delete key press to delete selected items from tree"""
        selected_items = self.tracker.tw_footage.selectedItems()
        if selected_items:
            self.tracker.tree_ops.deleteFootageFromTree(selected_items)

    def updateFilterSuggestions(self):
        """Update filter suggestions from tree data"""
        suggestions = set()

        # Collect all shot names, identifiers, and AOVs from the tree
        def collectSuggestions(item):
            userData = item.data(0, Qt.UserRole)
            item_text = item.text(0)

            if userData and userData.get('type') == 'group':
                # Add shot/group names
                suggestions.add(item_text)
                # Recurse into children
                for i in range(item.childCount()):
                    collectSuggestions(item.child(i))
            elif userData and userData.get('type') == 'footage':
                # Add footage item text (could be identifier or AOV)
                suggestions.add(item_text)
                # Also add identifier from userData if present
                identifier = userData.get('identifier', '')
                if identifier and identifier != item_text:
                    suggestions.add(identifier)

        # Collect from all top-level items
        for i in range(self.tracker.tw_footage.topLevelItemCount()):
            collectSuggestions(self.tracker.tw_footage.topLevelItem(i))

        # Update completer with sorted suggestions
        suggestion_list = sorted(list(suggestions))
        self.filter_completer.setModel(QStringListModel(suggestion_list))
