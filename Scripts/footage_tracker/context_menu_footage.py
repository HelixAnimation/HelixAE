# -*- coding: utf-8 -*-
"""
Footage-specific context menu methods: shot/identifier changes, file ops, render-type checks.
"""

import os
import platform

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QAction, QApplication, QMenu

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuFootage:
    """Mixin: footage item context menu actions"""

    def _addKitsuMenu(self, menu, item):
        """Add Kitsu links, loading task lists only when needed."""
        shotName = self.tracker.getShotNameFromItem(item)
        if not shotName:
            return

        shotEntity = self.tracker.getKitsuShotEntity(shotName)
        if not shotEntity:
            return

        openKitsuMenu = QMenu("Open in Kitsu", menu)

        openShotAction = QAction("Open Shot", openKitsuMenu)
        openShotAction.triggered.connect(lambda: self.tracker.openShotInKitsu(shotEntity))
        openKitsuMenu.addAction(openShotAction)

        if shotName in self.tracker.kitsuShotData:
            tasks = self.tracker.kitsu_integration.getTasksForShot(shotName)

            if tasks:
                openKitsuMenu.addSeparator()

                tasksByDept = {}
                for task in tasks:
                    dept = task.get('department', 'Other')
                    if dept not in tasksByDept:
                        tasksByDept[dept] = []
                    tasksByDept[dept].append(task)

                prjMng = self.core.getPlugin("ProjectManagement")
                kitsuMgr = None
                if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                    kitsuMgr = prjMng.curManager

                for dept in sorted(tasksByDept.keys()):
                    for task in tasksByDept[dept]:
                        taskName = task.get('task', 'Unknown')
                        statusShortName = task.get('status', 'todo')

                        taskAction = QAction(f"{taskName} ({statusShortName})", openKitsuMenu)

                        if kitsuMgr:
                            statusColor = self.tracker.getStatusColor(statusShortName, kitsuMgr)
                            icon = self.tracker.createColorIcon(statusColor)
                            taskAction.setIcon(icon)

                        taskAction.triggered.connect(lambda checked=False, t=task: self.tracker.openTaskInKitsu(t))
                        openKitsuMenu.addAction(taskAction)

        menu.addMenu(openKitsuMenu)

    def _getCommonIdentifierAOVForSelection(self, selected_items):
        """Get common identifier/AOV combinations for selected items"""
        return {}

    def switchMultipleFootageToShot(self, selected_items, shot):
        """Switch multiple footage items to different shot"""
        self.core.popup("Switch multiple footage functionality not yet implemented")

    @err_catcher(name=__name__)
    def _addShotSwitchMenu(self, menu, selected_items):
        """Add shot switching menu with alternatives"""
        identifier_aov_combinations = self._getCommonIdentifierAOVForSelection(selected_items)

        if not identifier_aov_combinations:
            return

        available_shots = set()
        for (identifier, aov), items in identifier_aov_combinations.items():
            key = (identifier, aov)
            if key in self.tracker.tree_ops.shot_alternatives:
                for shot in self.tracker.tree_ops.shot_alternatives[key]:
                    current_shots = set()
                    for item in items:
                        current_shot = self.tracker.getShotNameFromItem(item)
                        if current_shot:
                            current_shots.add(current_shot)
                    if shot not in current_shots:
                        available_shots.add(shot)

        if available_shots:
            switchMenu = QMenu("Switch to Shot (Choose Version)", menu)

            for alt_shot in sorted(available_shots):
                action = QAction(f"{alt_shot}", switchMenu)
                action.triggered.connect(
                    lambda checked, shot=alt_shot: self.switchMultipleFootageToShot(selected_items, shot)
                )
                switchMenu.addAction(action)

            menu.addMenu(switchMenu)

    def _addFileOperations(self, menu, filePath, folderPath):
        """Add file operation actions to context menu"""
        actionText = {
            "Windows": "Open in Explorer",
            "Darwin": "Reveal in Finder"
        }.get(platform.system(), "Open in File Manager")

        openAction = QAction(actionText, menu)
        openAction.triggered.connect(lambda: self.tracker.openInExplorer(folderPath))
        menu.addAction(openAction)

        copyAction = QAction("Copy Path", menu)
        copyAction.triggered.connect(lambda: QApplication.clipboard().setText(filePath))
        menu.addAction(copyAction)

    @err_catcher(name=__name__)
    def _is3DRenderFootage(self, file_path):
        """Check if file belongs to 3D Renders hierarchy"""
        path_normalized = file_path.replace('\\', '/')
        path_parts = path_normalized.split('/')

        for part in path_parts:
            part_lower = part.lower()
            if '3d_render' in part_lower or '3drender' in part_lower or '3d renders' in part_lower:
                return True

        try:
            folder_type = self.tracker.utils.detectFolderType(file_path)
            return folder_type == '01_3D_Renders'
        except Exception:
            pass

        return False

    def _extractShotFromFootagePath(self, file_path):
        """Extract shot name from a footage file path"""
        try:
            filename = os.path.basename(file_path) if file_path else ""
            if not filename:
                return None

            result = self.tracker.utils.extractHierarchy(file_path, filename)
            if result and len(result) >= 1:
                shot = result[0]
                if shot and shot != "Unknown Shot":
                    return shot
            return None
        except Exception as e:
            print(f"[DEBUG MENU] Error extracting shot from path: {e}")
            return None
