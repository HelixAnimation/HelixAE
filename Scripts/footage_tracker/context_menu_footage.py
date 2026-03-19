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
        """Add Kitsu integration menu to footage context menu (uses cached data, no API call)"""
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
            tasks = self.tracker.kitsuShotData[shotName].get('tasks', [])

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

    def _addChangeShotMenu(self, menu, footage_items):
        """Add 'Change Shot' submenu to context menu"""
        changeShotMenu = menu.addMenu("Change Shot")

        current_shot = self.tracker.tree_ops.extractCurrentShotFromProject()

        if current_shot:
            changeShotCurrentAction = QAction(f"Current ({current_shot})", changeShotMenu)
            changeShotCurrentAction.triggered.connect(lambda: self.onChangeShotCurrentClicked(footage_items))
            changeShotMenu.addAction(changeShotCurrentAction)
        else:
            changeShotCurrentAction = QAction("Current (Unknown)", changeShotMenu)
            changeShotCurrentAction.setEnabled(False)
            changeShotMenu.addAction(changeShotCurrentAction)

        changeShotCustomAction = QAction("Custom", changeShotMenu)
        changeShotCustomAction.triggered.connect(
            lambda checked: self.tracker.tree_ops.showShotSelectionDialog(footage_items)
        )
        changeShotMenu.addAction(changeShotCustomAction)

        changeShotAllAction = QAction("All", changeShotMenu)
        changeShotAllAction.triggered.connect(
            lambda checked: self.onChangeShotAllClicked(footage_items)
        )
        changeShotMenu.addAction(changeShotAllAction)

    @err_catcher(name=__name__)
    def _addChangeShotMenu_lazy(self, menu, footage_items):
        """Lazy-load Change Shot menu contents"""
        if menu.actions():
            return

        import time
        t3 = time.perf_counter()

        current_shot = self.tracker.tree_ops.extractCurrentShotFromProject()

        if current_shot:
            changeShotCurrentAction = QAction(f"Current ({current_shot})", menu)
            changeShotCurrentAction.triggered.connect(lambda: self.onChangeShotCurrentClicked(footage_items))
            menu.addAction(changeShotCurrentAction)
        else:
            changeShotCurrentAction = QAction("Current (Unknown)", menu)
            changeShotCurrentAction.setEnabled(False)
            menu.addAction(changeShotCurrentAction)

        changeShotCustomAction = QAction("Custom", menu)
        changeShotCustomAction.triggered.connect(
            lambda checked: self.tracker.tree_ops.showShotSelectionDialog(footage_items)
        )
        menu.addAction(changeShotCustomAction)

        changeShotAllAction = QAction("All", menu)
        changeShotAllAction.triggered.connect(
            lambda checked: self.onChangeShotAllClicked(footage_items)
        )
        menu.addAction(changeShotAllAction)

        t4 = time.perf_counter()
        if t4 - t3 > 0.01:
            print(f"[DEBUG MENU] Change Shot menu (lazy) took {t4-t3:.4f}s")

    def onChangeShotCurrentClicked(self, footage_items):
        """Handle 'Change Shot > Current' menu click"""
        self.changeToCurrentShot(footage_items)

    def onChangeShotAllClicked(self, footage_items):
        """Handle 'Change Shot > All' menu click"""
        self.tracker.tree_ops.shot_switcher.showVariableSelectionDialog(footage_items)

    def changeToCurrentShot(self, footage_items):
        """Change footage items to current shot"""
        self.tracker.tree_ops.shot_switcher.changeToCurrentShot(footage_items)

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

    def _addChangeIdentifierMenu(self, menu, footage_items, render_type='2d'):
        """Add 'Change Identifier' submenu to context menu for 2D or 3D renders"""
        print(
            f"[DEBUG IDENTIFIER MENU] Creating Change Identifier menu for "
            f"{len(footage_items)} items, type: {render_type}"
        )

        type_label = "2D" if render_type == '2d' else "3D"
        if len(footage_items) > 1:
            changeIdentifierMenu = menu.addMenu(f"Change {type_label} Identifier ({len(footage_items)} items)")
        else:
            changeIdentifierMenu = menu.addMenu(f"Change {type_label} Identifier")

        if render_type == '2d':
            aep_identifier = None
            current_file = self.core.getCurrentFileName()
            if current_file:
                current_file = str(current_file).replace('\\', '/')
                aep_identifier = os.path.basename(os.path.dirname(current_file))

            print(f"[DEBUG IDENTIFIER MENU] .aep identifier: {aep_identifier}")

            if aep_identifier:
                currentAction = QAction(f"Current ({aep_identifier})", changeIdentifierMenu)
                currentAction.triggered.connect(lambda: self.onChangeIdentifierCurrentClicked(footage_items))
                changeIdentifierMenu.addAction(currentAction)
            else:
                currentAction = QAction("Current (Unknown)", changeIdentifierMenu)
                currentAction.setEnabled(False)
                changeIdentifierMenu.addAction(currentAction)

        customAction = QAction("Custom", changeIdentifierMenu)
        customAction.triggered.connect(lambda checked: self.onChangeIdentifierCustomClicked(footage_items, render_type))
        changeIdentifierMenu.addAction(customAction)

    @err_catcher(name=__name__)
    def _addChangeIdentifierMenu_lazy(self, menu, footage_items, render_type='2d'):
        """Lazy-load Change Identifier menu contents"""
        if menu.actions():
            return

        import time
        t_start = time.perf_counter()

        if render_type == '2d':
            aep_identifier = None
            current_file = self.core.getCurrentFileName()
            if current_file:
                current_file = str(current_file).replace('\\', '/')
                aep_identifier = os.path.basename(os.path.dirname(current_file))

            print(f"[DEBUG IDENTIFIER MENU] .aep identifier: {aep_identifier}")

            if aep_identifier:
                currentAction = QAction(f"Current ({aep_identifier})", menu)
                currentAction.triggered.connect(lambda: self.onChangeIdentifierCurrentClicked(footage_items))
                menu.addAction(currentAction)
            else:
                currentAction = QAction("Current (Unknown)", menu)
                currentAction.setEnabled(False)
                menu.addAction(currentAction)

        customAction = QAction("Custom", menu)
        customAction.triggered.connect(lambda checked: self.onChangeIdentifierCustomClicked(footage_items, render_type))
        menu.addAction(customAction)

        t_end = time.perf_counter()
        if t_end - t_start > 0.01:
            print(f"[DEBUG MENU] {render_type.upper()} Change Identifier menu (lazy) took {t_end-t_start:.4f}s")

    def onChangeIdentifierClicked(self, footage_items, new_identifier, folder_type):
        """Handle 'Change Identifier' menu click"""
        self.tracker.tree_ops.shot_switcher.changeIdentifier(footage_items, new_identifier, folder_type)

    def onChangeIdentifierCurrentClicked(self, footage_items):
        """Handle 'Change Identifier > Current' - updates to latest version of .aep file's identifier"""
        print(f"[DEBUG IDENTIFIER CURRENT] === Starting Change Identifier Current ===")

        current_file = self.core.getCurrentFileName()
        print(f"[DEBUG IDENTIFIER CURRENT] Current .aep file: {current_file}")

        if not current_file:
            self.core.popup("Could not determine current .aep file path.")
            return

        current_file = str(current_file).replace('\\', '/')
        parent_folder = os.path.basename(os.path.dirname(current_file))

        print(f"[DEBUG IDENTIFIER CURRENT] Normalized path: {current_file}")
        print(f"[DEBUG IDENTIFIER CURRENT] Extracted parent folder (identifier): {parent_folder}")

        if not parent_folder:
            self.core.popup(f"Could not extract identifier from path: {current_file}")
            return

        first_item = footage_items[0]
        current_path = first_item.data(0, Qt.UserRole).get('path', '')
        print(f"[DEBUG IDENTIFIER CURRENT] First footage path: {current_path}")

        if '/playblasts/' in current_path.lower():
            folder_type = 'Playblasts'
        else:
            folder_type = '2dRender'

        print(f"[DEBUG IDENTIFIER CURRENT] Detected folder_type: {folder_type}")
        print(
            f"[DEBUG IDENTIFIER CURRENT] Calling changeIdentifier with "
            f"identifier='{parent_folder}', folder_type='{folder_type}'"
        )

        self.tracker.tree_ops.shot_switcher.changeIdentifier(footage_items, parent_folder, folder_type)

    def onChangeIdentifierCustomClicked(self, footage_items, render_type='2d'):
        """Handle 'Change Identifier > Custom' - scans and shows dialog with all identifiers"""
        shots = set()
        for item in footage_items:
            shot_name = self.tracker.getShotNameFromItem(item)
            if shot_name:
                shots.add(shot_name)

        if not shots:
            self.core.popup("No shot found for selected items.")
            return

        all_shot_identifiers = {}
        for shot in shots:
            if render_type == '2d':
                shot_identifier_tuples = self.tracker.tree_ops.shot_switcher.getAvailable2DIdentifiers(shot)
            else:
                shot_identifier_tuples = self.tracker.tree_ops.shot_switcher.getAvailable3DIdentifiers(shot)
            all_shot_identifiers[shot] = shot_identifier_tuples

        all_unique_identifiers = set()
        common_identifiers = set()

        for shot_tuples in all_shot_identifiers.values():
            for ident, folder_type in shot_tuples:
                all_unique_identifiers.add(ident)

        if all_shot_identifiers and len(all_shot_identifiers) > 0:
            for ident in all_unique_identifiers:
                exists_in_all = True
                for shot_tuples in all_shot_identifiers.values():
                    shot_ident_names = [i[0] for i in shot_tuples]
                    if ident not in shot_ident_names:
                        exists_in_all = False
                        break
                if exists_in_all:
                    common_identifiers.add(ident)

        all_available_identifiers = set()
        identifier_availability = {}

        for shot, shot_tuples in all_shot_identifiers.items():
            for ident, folder_type in shot_tuples:
                if render_type == '2d':
                    if folder_type == 'Playblasts':
                        prefixed = f"[PB] {ident}"
                    elif folder_type == '2dRender':
                        prefixed = f"[2D] {ident}"
                    else:
                        prefixed = ident
                else:
                    prefixed = f"[3D] {ident}"

                all_available_identifiers.add(prefixed)

                if prefixed not in identifier_availability:
                    identifier_availability[prefixed] = {
                        'shots': set(), 'folder_type': folder_type, 'clean_name': ident
                    }
                identifier_availability[prefixed]['shots'].add(shot)

        self.tracker.tree_ops.shot_switcher.showIdentifierSelectionDialog(
            footage_items, all_available_identifiers, all_shot_identifiers,
            common_identifiers, identifier_availability, render_type
        )

    def _is2DRenderFootage(self, item):
        """Check if a footage item is a 2D render (optimized - checks userData)"""
        try:
            userData = item.data(0, Qt.UserRole)
            if not userData or userData.get('type') != 'footage':
                return False

            footage_type = userData.get('footage_type')
            if footage_type in ('playblast', '2drender'):
                return True

            path = userData.get('path', '')
            if path:
                path_lower = path.lower()
                if '/playblasts/' in path_lower or '\\playblasts\\' in path_lower:
                    return True
                if '/renders/2drender/' in path_lower or '\\renders\\2drender\\' in path_lower:
                    return True

            return False
        except Exception:
            return False

    def _is3DRenderFootageItem(self, item):
        """Check if a footage item is a 3D render (optimized - checks userData)"""
        try:
            userData = item.data(0, Qt.UserRole)
            if not userData or userData.get('type') != 'footage':
                return False

            path = userData.get('path', '')
            if path:
                path_lower = path.lower()
                if '/renders/3drender/' in path_lower or '\\renders\\3drender\\' in path_lower:
                    return True
                if '3d_render' in path_lower or '3drender' in path_lower or '3d renders' in path_lower:
                    return True

            return False
        except Exception:
            return False

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
