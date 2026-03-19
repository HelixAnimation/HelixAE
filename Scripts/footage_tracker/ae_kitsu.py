# -*- coding: utf-8 -*-
"""
Prism AfterEffects Kitsu Integration
Gets shot information from Kitsu including frame ranges, fps, etc.
"""

import os
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class AEKitsu(QObject):
    def __init__(self, main):
        super(AEKitsu, self).__init__()
        self.main = main
        self.core = main.core
    
    @err_catcher(name=__name__)
    def openShotListDialog(self):
        """Open the shot list dialog"""
        # Debug: Check what's available
        debugInfo = []
        debugInfo.append(f"core.projectPath: {getattr(self.core, 'projectPath', None)}")
        
        # Check if a project is currently loaded
        if not getattr(self.core, 'projectPath', None):
            # Try to load from current scene
            try:
                currentFile = self.core.getCurrentFileName()

                # Clean up the path - remove any stray quotes
                if currentFile:
                    currentFile = currentFile.replace("'", "").replace('"', '').strip()

                if currentFile and os.path.exists(currentFile):
                    # Try to detect project from file path
                    parts = currentFile.replace("\\", "/").split("/")

                    try:
                        # Try both 02_Production and 03_Production
                        prodIndex = -1
                        if "02_Production" in parts:
                            prodIndex = parts.index("02_Production")
                        elif "03_Production" in parts:
                            prodIndex = parts.index("03_Production")

                        if prodIndex > 0:
                            projectPath = "/".join(parts[:prodIndex])

                            if os.path.exists(projectPath):
                                self.core.changeProject(projectPath)

                    except (ValueError, IndexError):
                        pass

            except Exception:
                pass

            # Check again if project was loaded
            if not getattr(self.core, 'projectPath', None):
                self.core.popup("Could not detect Prism project from current scene.\n\n"
                               "Please ensure you have a Prism scene file open from a project.")
                return False
        
        # Check if dialog already exists and is still valid
        if hasattr(self, 'dlg_shots') and self.dlg_shots is not None:
            try:
                # Check if the widget still exists and hasn't been destroyed
                if not self.dlg_shots.isHidden():
                    self.dlg_shots.raise_()
                    self.dlg_shots.activateWindow()
                    self.dlg_shots.showNormal()  # Restore if minimized
                    return True
            except (RuntimeError, AttributeError):
                # Dialog was destroyed, clean up and create new one
                self.dlg_shots = None

        # Create new dialog
        self.dlg_shots = QDialog()
        self.dlg_shots.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint
        )
        self.dlg_shots.setWindowTitle("Prism - Kitsu Shot List")
        self.dlg_shots.resize(1000, 600)

        # Clean up when dialog is closed
        self.dlg_shots.finished.connect(lambda: setattr(self, 'dlg_shots', None))

        self.setupShotListUI()
        self.loadShotsFromKitsu()
        self.dlg_shots.show()
        return True
    
    def setupShotListUI(self):
        """Build the shot list UI"""
        layout = QVBoxLayout()
        self.dlg_shots.setLayout(layout)
        
        # Top toolbar
        topToolbar = QHBoxLayout()
        
        # Refresh button (left)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.loadShotsFromKitsu)
        topToolbar.addWidget(self.btn_refresh)
        
        topToolbar.addStretch()
        
        layout.addLayout(topToolbar)
        
        # Filter bar
        filterBar = QHBoxLayout()
        filterLabel = QLabel("Filter:")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Search by Shot, Sequence, or Episode...")
        self.filter_input.textChanged.connect(self.applyFilter)
        
        filterBar.addWidget(filterLabel)
        filterBar.addWidget(self.filter_input, 1)
        layout.addLayout(filterBar)
        
        # Tree widget for shots
        self.tw_shots = QTreeWidget()
        self.tw_shots.setHeaderLabels([
            "Episode / Sequence / Shot", 
            "Frame Range", 
            "FPS", 
            "Tasks"
        ])
        self.tw_shots.setColumnWidth(0, 300)
        self.tw_shots.setColumnWidth(1, 150)
        self.tw_shots.setColumnWidth(2, 80)
        self.tw_shots.setColumnWidth(3, 400)
        self.tw_shots.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tw_shots.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tw_shots.customContextMenuRequested.connect(self.showShotContextMenu)
        
        layout.addWidget(self.tw_shots)
        
        # Statistics bar
        self.statsLabel = QLabel()
        self.statsLabel.setStyleSheet("padding: 5px; background-color: #2b2b2b;")
        layout.addWidget(self.statsLabel)
        
        # Status bar
        self.dlg_shots.statusBar = QLabel()
        self.dlg_shots.statusBar.setStyleSheet("padding: 5px;")
        layout.addWidget(self.dlg_shots.statusBar)
        
        # Bottom toolbar
        bottomToolbar = QHBoxLayout()
        bottomToolbar.addStretch()
        
        # Close button
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.dlg_shots.close)
        self.btn_close.setMinimumWidth(100)
        bottomToolbar.addWidget(self.btn_close)
        
        layout.addLayout(bottomToolbar)
    
    def applyFilter(self):
        """Filter tree items based on search text"""
        searchText = self.filter_input.text().lower()
        
        def filterItem(item):
            userData = item.data(0, Qt.UserRole)
            itemText = item.text(0).lower()
            
            if userData and userData.get('type') == 'group':
                hasVisibleChild = False
                for i in range(item.childCount()):
                    childVisible = filterItem(item.child(i))
                    if childVisible:
                        hasVisibleChild = True
                shouldShow = hasVisibleChild or (searchText in itemText)
                item.setHidden(not shouldShow)
                return shouldShow
            elif userData and userData.get('type') == 'shot':
                textMatch = searchText == "" or searchText in itemText
                shouldShow = textMatch
                item.setHidden(not shouldShow)
                return shouldShow
            return True
        
        for i in range(self.tw_shots.topLevelItemCount()):
            filterItem(self.tw_shots.topLevelItem(i))
    
    @err_catcher(name=__name__)
    def loadShotsFromKitsu(self):
        """Query Kitsu for all shots and their information"""
        self.tw_shots.clear()
        self.dlg_shots.statusBar.setText("Loading shots from Kitsu...")
        
        try:
            # Get the Project Management plugin and Kitsu manager
            prjMng = self.core.getPlugin("ProjectManagement")
            if not prjMng:
                self.core.popup("Project Management plugin is not loaded.")
                self.dlg_shots.statusBar.setText("Error: Project Management plugin not found")
                return
            
            # Get the current manager (should be Kitsu)
            if not hasattr(prjMng, 'curManager') or not prjMng.curManager:
                self.core.popup("No project management system is configured.")
                self.dlg_shots.statusBar.setText("Error: No project management system configured")
                return
            
            kitsuMgr = prjMng.curManager
            
            # Check if it's actually Kitsu
            if kitsuMgr.name != "Kitsu":
                self.core.popup(f"Current project management system is '{kitsuMgr.name}', not Kitsu.")
                self.dlg_shots.statusBar.setText(f"Error: Using {kitsuMgr.name}, not Kitsu")
                return
            
            # Get project FPS
            try:
                projectFps = kitsuMgr.getFps() or 24.0
            except Exception:
                projectFps = self.core.getConfig("globals", "fps", config="project") or 25.0
            
            # Get all shots from Kitsu
            shots = kitsuMgr.getShots() or []
            
            if not shots:
                self.core.popup("No shots found in Kitsu project.")
                self.dlg_shots.statusBar.setText("No shots found")
                self.statsLabel.setText("Total shots: 0")
                return
            
            # Organize shots into hierarchy
            hierarchy = {}
            totalShots = 0
            
            useEpisodes = self.core.getConfig("globals", "useEpisodes", config="project") or False
            
            for shot in shots:
                totalShots += 1
                
                # Get episode/sequence/shot structure
                if useEpisodes:
                    episode = shot.get("episode", "Unknown Episode")
                    sequence = shot.get("sequence", "Unknown Sequence")
                else:
                    episode = None
                    sequence = shot.get("sequence", "Unknown Sequence")
                
                shotName = shot.get("shot", "Unknown Shot")
                
                # Build hierarchy
                if useEpisodes:
                    if episode not in hierarchy:
                        hierarchy[episode] = {}
                    if sequence not in hierarchy[episode]:
                        hierarchy[episode][sequence] = []
                    hierarchy[episode][sequence].append(shot)
                else:
                    if sequence not in hierarchy:
                        hierarchy[sequence] = []
                    hierarchy[sequence].append(shot)
            
            # Build tree
            self.buildShotTree(hierarchy, useEpisodes, projectFps)
            
            self.statsLabel.setText(f"Total shots: {totalShots}")
            self.dlg_shots.statusBar.setText("Shots loaded successfully from Kitsu")
            
        except Exception as e:
            import traceback
            self.core.popup(f"Error loading shots from Kitsu:\n{str(e)}\n\n{traceback.format_exc()}")
            self.dlg_shots.statusBar.setText("Error loading shots")
    
    def buildShotTree(self, hierarchy, useEpisodes, projectFps):
        """Build tree widget from shot hierarchy"""
        prjMng = self.core.getPlugin("ProjectManagement")
        kitsuMgr = prjMng.curManager if prjMng and hasattr(prjMng, 'curManager') else None
        
        if useEpisodes:
            # Episode -> Sequence -> Shot structure
            for episode in sorted(hierarchy.keys()):
                episodeItem = QTreeWidgetItem()
                episodeItem.setText(0, episode)
                episodeItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'episode'})
                episodeItem.setForeground(0, QBrush(QColor(150, 180, 255)))
                font = episodeItem.font(0)
                font.setBold(True)
                episodeItem.setFont(0, font)
                self.tw_shots.addTopLevelItem(episodeItem)
                
                for sequence in sorted(hierarchy[episode].keys()):
                    sequenceItem = QTreeWidgetItem()
                    sequenceItem.setText(0, sequence)
                    sequenceItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'sequence'})
                    sequenceItem.setForeground(0, QBrush(QColor(180, 180, 220)))
                    font = sequenceItem.font(0)
                    font.setBold(True)
                    sequenceItem.setFont(0, font)
                    episodeItem.addChild(sequenceItem)
                    
                    # Add shots
                    for shot in hierarchy[episode][sequence]:
                        self.addShotToTree(sequenceItem, shot, projectFps, kitsuMgr)
                
                episodeItem.setExpanded(True)
        else:
            # Sequence -> Shot structure
            for sequence in sorted(hierarchy.keys()):
                sequenceItem = QTreeWidgetItem()
                sequenceItem.setText(0, sequence)
                sequenceItem.setData(0, Qt.UserRole, {'type': 'group', 'level': 'sequence'})
                sequenceItem.setForeground(0, QBrush(QColor(150, 180, 255)))
                font = sequenceItem.font(0)
                font.setBold(True)
                sequenceItem.setFont(0, font)
                self.tw_shots.addTopLevelItem(sequenceItem)
                
                # Add shots
                for shot in hierarchy[sequence]:
                    self.addShotToTree(sequenceItem, shot, projectFps, kitsuMgr)
                
                sequenceItem.setExpanded(True)
    
    def getStatusColor(self, statusShortName, kitsuMgr):
        """Get status color from Kitsu or use default colors"""
        try:
            # Try to get color from Kitsu
            if kitsuMgr and hasattr(kitsuMgr, 'getTaskStatusColor'):
                color = kitsuMgr.getTaskStatusColor(statusShortName)
                if color:
                    return QColor(color)
            
            # Fallback to default color mapping
            colorMap = {
                'todo': QColor(150, 150, 150),      # Gray
                'wip': QColor(50, 115, 220),        # Blue
                'wfa': QColor(171, 38, 255),        # Purple
                'done': QColor(34, 197, 94),        # Green
                'retake': QColor(239, 68, 68),      # Red
            }
            return colorMap.get(statusShortName.lower(), QColor(150, 150, 150))
        except Exception:
            # Final fallback
            return QColor(150, 150, 150)
    
    def addShotToTree(self, parentItem, shot, projectFps, kitsuMgr):
        """Add a single shot to the tree"""
        shotName = shot.get("shot", "Unknown")
        
        item = QTreeWidgetItem()
        item.setText(0, shotName)
        
        # Frame range
        start = shot.get("start")
        end = shot.get("end")
        if start is not None and end is not None:
            frameRange = f"{start}-{end}"
        else:
            frameRange = "N/A"
        item.setText(1, frameRange)
        
        # FPS (use project FPS as default)
        item.setText(2, f"{projectFps:.2f}")
        
        # Get tasks for this shot and create a rich text widget
        try:
            if not kitsuMgr:
                raise Exception("Kitsu manager not available")
            
            tasks = kitsuMgr.getTasksFromEntity(shot, quiet=True) or []
            
            if tasks:
                # Create a widget with colored task labels
                taskWidget = QWidget()
                taskLayout = QHBoxLayout(taskWidget)
                taskLayout.setContentsMargins(4, 2, 4, 2)
                taskLayout.setSpacing(8)
                
                for i, task in enumerate(tasks[:5]):  # Show up to 5 tasks
                    taskName = task.get('task', 'Unknown')
                    statusShortName = task.get('status', 'todo')
                    
                    # Create colored label for each task
                    taskLabel = QLabel(f"{taskName} ({statusShortName})")
                    statusColor = self.getStatusColor(statusShortName, kitsuMgr)
                    r, g, b = statusColor.red(), statusColor.green(), statusColor.blue()
                    taskLabel.setStyleSheet(
                        f"color: rgb({r}, {g}, {b}); font-weight: bold;"
                    )
                    taskLayout.addWidget(taskLabel)
                
                if len(tasks) > 5:
                    moreLabel = QLabel(f"+{len(tasks) - 5} more...")
                    moreLabel.setStyleSheet("color: #888888; font-style: italic;")
                    taskLayout.addWidget(moreLabel)
                
                taskLayout.addStretch()
                
                # Add item and set widget
                parentItem.addChild(item)
                self.tw_shots.setItemWidget(item, 3, taskWidget)
            else:
                item.setText(3, "No tasks")
                item.setForeground(3, QBrush(QColor(150, 150, 150)))
                parentItem.addChild(item)
                
        except Exception as e:
            item.setText(3, "Error loading tasks")
            item.setForeground(3, QBrush(QColor(255, 100, 100)))
            parentItem.addChild(item)
        
        # Store shot data
        userData = {
            'type': 'shot',
            'shot': shot,
            'shotName': shotName,
            'frameRange': frameRange,
            'start': start,
            'end': end,
            'fps': projectFps
        }
        item.setData(0, Qt.UserRole, userData)
    
    @err_catcher(name=__name__)
    def showShotContextMenu(self, position):
        """Show context menu on right-click"""
        try:
            item = self.tw_shots.itemAt(position)
            if not item:
                return
            
            userData = item.data(0, Qt.UserRole)
            if not userData or userData.get('type') != 'shot':
                return
            
            shot = userData.get('shot')
            if not shot:
                return
            
            menu = QMenu(self.tw_shots)
            
            # Open in Kitsu browser - with submenu for tasks
            openKitsuMenu = QMenu("Open in Kitsu", menu)
            
            # Add "Open Shot" action
            openShotAction = QAction("Open Shot", openKitsuMenu)
            openShotAction.triggered.connect(lambda: self.openShotInKitsu(shot))
            openKitsuMenu.addAction(openShotAction)
            
            # Try to get tasks and add them to submenu
            try:
                prjMng = self.core.getPlugin("ProjectManagement")
                if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                    kitsuMgr = prjMng.curManager
                    tasks = kitsuMgr.getTasksFromEntity(shot, quiet=True) or []
                    
                    if tasks:
                        openKitsuMenu.addSeparator()
                        
                        # Group tasks by department for better organization
                        tasksByDept = {}
                        for task in tasks:
                            dept = task.get('department', 'Other')
                            if dept not in tasksByDept:
                                tasksByDept[dept] = []
                            tasksByDept[dept].append(task)
                        
                        # Add tasks to submenu
                        for dept in sorted(tasksByDept.keys()):
                            for task in tasksByDept[dept]:
                                taskName = task.get('task', 'Unknown')
                                statusShortName = task.get('status', 'todo')
                                
                                # Create action with task name and status
                                taskAction = QAction(f"{taskName} ({statusShortName})", openKitsuMenu)
                                
                                # Get status color and apply it
                                statusColor = self.getStatusColor(statusShortName, kitsuMgr)
                                icon = self.createColorIcon(statusColor)
                                taskAction.setIcon(icon)
                                
                                # Connect to open task in Kitsu
                                taskAction.triggered.connect(lambda checked=False, t=task: self.openTaskInKitsu(t))
                                openKitsuMenu.addAction(taskAction)
            except Exception as e:
                # If tasks can't be loaded, just add a disabled "No tasks" item
                noTasksAction = QAction("No tasks available", openKitsuMenu)
                noTasksAction.setEnabled(False)
                openKitsuMenu.addAction(noTasksAction)
            
            menu.addMenu(openKitsuMenu)
            
            menu.addSeparator()
            
            # Copy shot info
            copyInfoAction = QAction("Copy Shot Information", menu)
            copyInfoAction.triggered.connect(lambda: self.copyShotInfo(shot, userData))
            menu.addAction(copyInfoAction)
            
            # Copy frame range
            copyRangeAction = QAction("Copy Frame Range", menu)
            copyRangeAction.triggered.connect(lambda: QApplication.clipboard().setText(userData.get('frameRange', '')))
            menu.addAction(copyRangeAction)
            
            menu.addSeparator()
            
            # View tasks
            viewTasksAction = QAction("View Tasks Details", menu)
            viewTasksAction.triggered.connect(lambda: self.showTasksDetails(shot))
            menu.addAction(viewTasksAction)
            
            menu.exec_(self.tw_shots.viewport().mapToGlobal(position))
            
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")
    
    def createColorIcon(self, color):
        """Create a small colored circle icon for menu items"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        
        return QIcon(pixmap)
    
    @err_catcher(name=__name__)
    def openShotInKitsu(self, shot):
        """Open shot in Kitsu web browser"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                kitsuMgr.openInBrowser("shot", shot)
        except Exception as e:
            self.core.popup(f"Error opening Kitsu:\n{str(e)}")
    
    @err_catcher(name=__name__)
    def openTaskInKitsu(self, task):
        """Open task in Kitsu web browser"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                kitsuMgr.openInBrowser("task", task)
        except Exception as e:
            self.core.popup(f"Error opening task in Kitsu:\n{str(e)}")
    
    @err_catcher(name=__name__)
    def copyShotInfo(self, shot, userData):
        """Copy shot information to clipboard"""
        shotName = self.core.entities.getShotName(shot)
        info = f"Shot: {shotName}\n"
        info += f"Frame Range: {userData.get('frameRange', 'N/A')}\n"
        info += f"FPS: {userData.get('fps', 'N/A')}\n"
        
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                tasks = kitsuMgr.getTasksFromEntity(shot, quiet=True) or []
                info += f"\nTasks ({len(tasks)}):\n"
                for task in tasks:
                    info += f"  - {task['task']} ({task['department']}) - Status: {task.get('status', 'N/A')}\n"
            else:
                info += "\nTasks: Kitsu not available"
        except Exception:
            info += "\nTasks: Error loading"
        
        QApplication.clipboard().setText(info)
        self.dlg_shots.statusBar.setText("Shot information copied to clipboard")
        QTimer.singleShot(3000, lambda: self.dlg_shots.statusBar.setText(""))
    
    @err_catcher(name=__name__)
    def showTasksDetails(self, shot):
        """Show detailed tasks dialog"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if not prjMng or not hasattr(prjMng, 'curManager') or not prjMng.curManager:
                self.core.popup("Kitsu manager not available")
                return
            
            kitsuMgr = prjMng.curManager
            tasks = kitsuMgr.getTasksFromEntity(shot, quiet=True) or []
            
            dlg = QDialog(self.dlg_shots)
            dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
            shotName = self.core.entities.getShotName(shot)
            dlg.setWindowTitle(f"Tasks for {shotName}")
            dlg.resize(600, 400)
            
            layout = QVBoxLayout()
            dlg.setLayout(layout)
            
            # Info label
            infoLabel = QLabel(f"<b>{shotName}</b> - {len(tasks)} task(s)")
            layout.addWidget(infoLabel)
            
            # Tasks tree
            taskTree = QTreeWidget()
            taskTree.setHeaderLabels(["Department", "Task", "Status"])
            taskTree.setColumnWidth(0, 150)
            taskTree.setColumnWidth(1, 200)
            taskTree.setColumnWidth(2, 150)
            
            for task in tasks:
                taskItem = QTreeWidgetItem()
                taskItem.setText(0, task.get('department', 'N/A'))
                taskItem.setText(1, task.get('task', 'N/A'))
                taskItem.setText(2, task.get('status', 'N/A'))
                taskTree.addTopLevelItem(taskItem)
            
            layout.addWidget(taskTree)
            
            # Close button
            closeBtn = QPushButton("Close")
            closeBtn.clicked.connect(dlg.close)
            layout.addWidget(closeBtn)
            
            dlg.exec_()
            
        except Exception as e:
            import traceback
            self.core.popup(f"Error loading tasks:\n{str(e)}\n\n{traceback.format_exc()}")
