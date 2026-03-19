# -*- coding: utf-8 -*-
"""
Context Menu Module
Handles all context menu creation and routing for footage, composition, and folder items.

Sub-modules (mixin classes):
  context_menu_footage.py       - Shot/identifier changes, file ops, render-type checks
  context_menu_compositions.py  - Comp actions, Kitsu comp sync, add-to-comp dialogs
  context_menu_sync.py          - Sync submenu (version, FPS, resolution)
  context_menu_image_resize.py  - Resize menus, confirm dialogs, batch resize
  context_menu_lighting_import.py - Import lighting/AOVs, label colors
  context_menu_bypass.py        - Bypass/unbypass tree items
  context_menu_api_helpers.py   - Prism API helpers (shot entity, tasks, AOVs)
  context_menu_folder.py        - Folder organize, refresh, validate naming
"""

import os

from qtpy.QtCore import Qt, QObject
from qtpy.QtWidgets import QAction, QMenu

from PrismUtils.Decorators import err_catcher as err_catcher

from .context_menu_footage import ContextMenuFootage
from .context_menu_compositions import ContextMenuCompositions
from .context_menu_sync import ContextMenuSync
from .context_menu_image_resize import ContextMenuImageResize
from .context_menu_lighting_import import ContextMenuLightingImport
from .context_menu_bypass import ContextMenuBypass
from .context_menu_api_helpers import ContextMenuApiHelpers
from .context_menu_folder import ContextMenuFolder


class ContextMenu(
    QObject,
    ContextMenuFootage,
    ContextMenuCompositions,
    ContextMenuSync,
    ContextMenuImageResize,
    ContextMenuLightingImport,
    ContextMenuBypass,
    ContextMenuApiHelpers,
    ContextMenuFolder,
):
    """Manages context menus for footage, composition, and folder items"""

    def __init__(self, tracker):
        super(ContextMenu, self).__init__()
        self.tracker = tracker
        self.core = tracker.core

    @err_catcher(name=__name__)
    def showFootageContextMenu(self, position):
        """Show context menu on right-click for footage items, folders, and compositions"""
        try:
            import time
            start_time = time.perf_counter()

            item = self.tracker.tw_footage.itemAt(position)
            if not item:
                self.showEmptySpaceContextMenu(position)
                return

            userData = item.data(0, Qt.UserRole)

            selected_items = self.tracker.tw_footage.selectedItems()
            print(f"[DEBUG MENU] Selected items: {len(selected_items)}")

            # Check if we have multiple main folders selected
            main_folders_selected = []
            for selected_item in selected_items:
                selected_data = selected_item.data(0, Qt.UserRole)
                if (selected_data and selected_data.get('type') == 'group' and
                    selected_data.get('level') == 'group' and
                    selected_data.get('group_name') in ['3D Renders', '2D Renders', 'Resources', 'External', 'Comps']):
                    main_folders_selected.append(selected_item)
                    print(f"DEBUG: Found main folder: {selected_data.get('group_name')}")

            if len(main_folders_selected) > 1:
                print("DEBUG: Multiple main folders selected, showing multi-folder context menu")
                return self.showMultiFolderContextMenu(position, main_folders_selected)

            if (userData and userData.get('type') == 'group' and
                userData.get('level') == 'group' and
                userData.get('group_name') in ['3D Renders', '2D Renders', 'Resources', 'External', 'Comps']):
                print("DEBUG: Detected main folder item, showing folder context menu")
                return self.showFolderContextMenu(position, userData)

            if not userData or userData.get('type') not in ['footage', 'comp']:
                print("DEBUG: Not a footage or comp item")
                return

            if userData.get('type') == 'comp':
                print("DEBUG: Detected comp item, showing comp context menu")
                selected_items = self.tracker.tw_footage.selectedItems()
                comp_items = [item for item in selected_items
                            if item.data(0, Qt.UserRole) and item.data(0, Qt.UserRole).get('type') == 'comp']
                return self.showCompContextMenu(comp_items, position)

            filePath = item.text(6)
            folderPath = os.path.dirname(filePath)
            footageId = userData.get('id')

            menu = QMenu(self.tracker.tw_footage)

            if footageId:
                revealAction = QAction("Reveal in Project", menu)
                revealAction.triggered.connect(lambda: self.tracker.revealInProject(footageId))
                menu.addAction(revealAction)

                revealCompsAction = QAction("Reveal in Compositions", menu)
                revealCompsAction.triggered.connect(lambda: self.tracker.revealInCompositions(footageId))
                menu.addAction(revealCompsAction)

                addToMenu = menu.addMenu("Add to Comp")

                currentCompAction = QAction("Current Comp", addToMenu)
                currentCompAction.triggered.connect(lambda: self.addFootageToActiveComp())
                addToMenu.addAction(currentCompAction)

                chooseCompAction = QAction("Choose Comp...", addToMenu)
                chooseCompAction.triggered.connect(lambda: self.addFootageToSelectedComp())
                addToMenu.addAction(chooseCompAction)

                menu.addSeparator()

            t1 = time.perf_counter()
            if self.tracker.kitsuShotData:
                self._addKitsuMenu(menu, item)
                menu.addSeparator()
            t2 = time.perf_counter()
            if t2 - t1 > 0.01:
                print(f"[DEBUG MENU] Kitsu menu took {t2-t1:.4f}s")

            selected_items = self.tracker.tw_footage.selectedItems()
            if selected_items:
                footage_items = [item for item in selected_items
                               if item.data(0, Qt.UserRole) and item.data(0, Qt.UserRole).get('type') == 'footage']

                if footage_items:
                    changeShotMenu = menu.addMenu("Change Shot")
                    changeShotMenu.aboutToShow.connect(
                        lambda: self._addChangeShotMenu_lazy(changeShotMenu, footage_items)
                    )
                    menu.addSeparator()

                t5 = time.perf_counter()
                footage_2d_items = [item for item in footage_items if self._is2DRenderFootage(item)]
                footage_3d_items = [item for item in footage_items if self._is3DRenderFootageItem(item)]
                t6 = time.perf_counter()
                if t6 - t5 > 0.01:
                    print(f"[DEBUG MENU] 2D/3D filter took {t6-t5:.4f}s for {len(footage_items)} items")
                print(f"[DEBUG MENU] Found {len(footage_2d_items)} 2D items, {len(footage_3d_items)} 3D items")

                if footage_2d_items:
                    type_label = "2D" if len(footage_2d_items) == 1 else f"2D ({len(footage_2d_items)} items)"
                    changeId2dMenu = menu.addMenu(f"Change {type_label} Identifier")
                    changeId2dMenu.aboutToShow.connect(lambda menu=changeId2dMenu, items=footage_2d_items:
                        self._addChangeIdentifierMenu_lazy(menu, items, '2d'))
                    menu.addSeparator()

                if footage_3d_items:
                    type_label = "3D" if len(footage_3d_items) == 1 else f"3D ({len(footage_3d_items)} items)"
                    changeId3dMenu = menu.addMenu(f"Change {type_label} Identifier")
                    changeId3dMenu.aboutToShow.connect(lambda menu=changeId3dMenu, items=footage_3d_items:
                        self._addChangeIdentifierMenu_lazy(menu, items, '3d'))
                    menu.addSeparator()

                syncMenu = menu.addMenu("Sync")
                syncMenu.aboutToShow.connect(lambda: self._addSyncMenu_lazy(syncMenu, footage_items, position))
                menu.addSeparator()

            if (selected_items
                    and hasattr(self.tracker.tree_ops, 'shot_alternatives')
                    and self.tracker.tree_ops.shot_alternatives):
                t9 = time.perf_counter()
                self._addShotSwitchMenu(menu, selected_items)
                t10 = time.perf_counter()
                if t10 - t9 > 0.01:
                    print(f"[DEBUG MENU] Shot Switch menu took {t10-t9:.4f}s")
                menu.addSeparator()

            self._addFileOperations(menu, filePath, folderPath)

            if userData and userData.get('type') == 'footage':
                filePath_check = userData.get('path', '')
                if self._is3DRenderFootage(filePath_check):
                    menu.addSeparator()
                    resizeMenu = menu.addMenu("Resize AOV Images")
                    resizeMenu.setProperty("filePath", filePath_check)
                    resizeMenu.setProperty("position", position)
                    resizeMenu.aboutToShow.connect(lambda m=resizeMenu: self._addImageResizeMenu_lazy(m))

            if userData and userData.get('type') == 'footage':
                menu.addSeparator()
                t11 = time.perf_counter()
                is_bypassed = self._isTreeItemBypassed(item)
                t12 = time.perf_counter()
                if t12 - t11 > 0.01:
                    print(f"[DEBUG MENU] _isTreeItemBypassed took {t12-t11:.4f}s")

                if is_bypassed:
                    unbypassAction = QAction("Unbypass", menu)
                    # Capture item by value to avoid reference issues
                    unbypassAction.triggered.connect(lambda checked=False, item=item: self._unbypassTreeItem(item))
                    menu.addAction(unbypassAction)
                else:
                    bypassAction = QAction("Bypass", menu)
                    # Capture item by value to avoid reference issues
                    bypassAction.triggered.connect(lambda checked=False, item=item: self._bypassTreeItem(item))
                    menu.addAction(bypassAction)
                    print(f"[DEBUG CONTEXT MENU] Added 'Bypass' action for item: {item.text(0)}")
                    print(f"[DEBUG CONTEXT MENU] Added 'Bypass' action for item: {item.text(0)}")

            t_end = time.perf_counter()
            total = t_end - start_time
            if total > 0.05:
                print(f"[DEBUG MENU] Total menu creation time: {total:.4f}s")
            menu.exec_(self.tracker.tw_footage.viewport().mapToGlobal(position))
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showCompContextMenu(self, comp_items, position):
        """Show context menu for compositions"""
        try:
            print(f"DEBUG: showCompContextMenu called with {len(comp_items)} items")

            current_shot = self.tracker.tree_ops.data_parser.extractCurrentShotFromProject()
            kitsu_shot_data = None
            if current_shot and current_shot in self.tracker.kitsuShotData:
                kitsu_shot_data = self.tracker.kitsuShotData[current_shot]

            print(f"DEBUG: current_shot={current_shot}, kitsu_shot_data={kitsu_shot_data is not None}")

            menu = QMenu(self.tracker.tw_footage)

            if len(comp_items) > 1:
                menu.setTitle(f"{len(comp_items)} Compositions")
                self._addMultipleCompActions(menu, comp_items, kitsu_shot_data)
            else:
                comp_item = comp_items[0]
                userData = comp_item.data(0, Qt.UserRole)
                compId = userData.get('id')
                compName = comp_item.text(0)

                menu.setTitle(f"Composition: {compName}")

                openAction = QAction("Open Composition", menu)
                openAction.triggered.connect(
                    lambda: self.tracker.openComposition(compId, compName, self.tracker.dlg_footage)
                )
                menu.addAction(openAction)

                revealAction = QAction("Reveal in Project", menu)
                revealAction.triggered.connect(lambda: self._revealCompInProject(compId))
                menu.addAction(revealAction)

                menu.addSeparator()

                infoAction = QAction("Show Info", menu)
                infoAction.triggered.connect(lambda: self.tracker.showCompInfo(compId, compName))
                menu.addAction(infoAction)

                rawInfoAction = QAction("Show Raw Info", menu)
                rawInfoAction.triggered.connect(lambda: self.tracker.showRawCompInfo(compId, compName))
                menu.addAction(rawInfoAction)

                menu.addSeparator()

                removeUnusedAction = QAction("Remove Unused", menu)
                removeUnusedAction.setStatusTip("Remove comps and footage not used by this composition")
                removeUnusedAction.triggered.connect(
                    lambda: self.tracker.comp_manager.removeUnusedFromComp(compId, compName)
                )
                menu.addAction(removeUnusedAction)

                menu.addSeparator()

                if kitsu_shot_data:
                    self._addKitsuCompSync(menu, compId, compName, kitsu_shot_data)

                menu.addSeparator()

                is_bypassed = self._isTreeItemBypassed(comp_item)

                if is_bypassed:
                    unbypassAction = QAction("Unbypass", menu)
                    # Capture comp_item by value to avoid reference issues
                    unbypassAction.triggered.connect(lambda checked=False, item=comp_item: self._unbypassTreeItem(item))
                    menu.addAction(unbypassAction)
                else:
                    bypassAction = QAction("Bypass", menu)
                    # Capture comp_item by value to avoid reference issues
                    bypassAction.triggered.connect(lambda checked=False, item=comp_item: self._bypassTreeItem(item))
                    menu.addAction(bypassAction)

            menu.exec_(self.tracker.tw_footage.viewport().mapToGlobal(position))
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showFolderContextMenu(self, position, userData):
        """Show context menu for main folders (3D Renders, 2D Renders, Resources, External, Comps)"""
        try:
            print(f"DEBUG: showFolderContextMenu called for folder: {userData.get('group_name')}")

            folder_name = userData.get('group_name')

            menu = QMenu(self.tracker.tw_footage)
            menu.setTitle(f"Folder: {folder_name}")

            organiseAction = QAction("Organise...", menu)
            organiseAction.setStatusTip(f"Organize {folder_name} items in After Effects project")
            organiseAction.triggered.connect(lambda: self._organizeFolder(folder_name))
            menu.addAction(organiseAction)

            menu.addSeparator()

            if folder_name == 'Comps':
                refreshAction = QAction("Refresh Composition List", menu)
                refreshAction.triggered.connect(lambda: self._refreshComps())
                menu.addAction(refreshAction)
            elif folder_name in ['3D Renders', '2D Renders']:
                validateAction = QAction("Validate Naming Convention", menu)
                validateAction.triggered.connect(lambda: self._validateNaming(folder_name))
                menu.addAction(validateAction)

                if folder_name == '3D Renders':
                    menu.addSeparator()
                    import3dMenu = QMenu("Import", menu)

                    current_shot = self.tracker.tree_ops.extractCurrentShotFromProject()

                    if current_shot:
                        lightingAction = QAction(f"Lighting ({current_shot})", import3dMenu)
                    else:
                        lightingAction = QAction("Lighting (Unknown)", import3dMenu)
                        lightingAction.setEnabled(False)
                    lightingAction.triggered.connect(lambda: self.importCurrentShotLighting())
                    import3dMenu.addAction(lightingAction)

                    if current_shot:
                        customAction = QAction(f"Custom ({current_shot})", import3dMenu)
                    else:
                        customAction = QAction("Custom (Unknown)", import3dMenu)
                        customAction.setEnabled(False)
                    customAction.triggered.connect(lambda: self.showCustom3DAOVSelectionDialog())
                    import3dMenu.addAction(customAction)

                    menu.addMenu(import3dMenu)
            elif folder_name == 'Resources':
                categorizeAction = QAction("Auto-Categorize", menu)
                categorizeAction.triggered.connect(lambda: self._autoCategorizeResources())
                menu.addAction(categorizeAction)

            menu.exec_(self.tracker.tw_footage.viewport().mapToGlobal(position))
        except Exception as e:
            import traceback
            self.core.popup(f"Error in folder context menu:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showMultiFolderContextMenu(self, position, folder_items):
        """Show context menu for multiple selected folders"""
        try:
            print(f"DEBUG: showMultiFolderContextMenu called for {len(folder_items)} folders")

            folder_names = []
            for item in folder_items:
                userData = item.data(0, Qt.UserRole)
                folder_names.append(userData.get('group_name'))

            menu = QMenu(self.tracker.tw_footage)
            menu.setTitle(f"Multiple Folders ({len(folder_names)})")

            organiseAction = QAction(f"Organise All {len(folder_names)} Folders...", menu)
            organiseAction.setStatusTip(f"Organize all selected folders in After Effects project")
            organiseAction.triggered.connect(lambda: self._organizeMultipleFolders(folder_names))
            menu.addAction(organiseAction)

            menu.addSeparator()

            folderListAction = QAction(f"Folders: {', '.join(folder_names)}", menu)
            folderListAction.setEnabled(False)
            menu.addAction(folderListAction)

            menu.exec_(self.tracker.tw_footage.viewport().mapToGlobal(position))

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing multi-folder context menu:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showEmptySpaceContextMenu(self, position):
        """Show context menu when right-clicking on empty space"""
        try:
            menu = QMenu(self.tracker.tw_footage)

            importAction = QAction("Import...", menu)
            importAction.triggered.connect(lambda: self.showUnifiedImportDialog())
            menu.addAction(importAction)

            menu.exec_(self.tracker.tw_footage.viewport().mapToGlobal(position))
        except Exception as e:
            import traceback
            self.core.popup(f"Error:\n{str(e)}\n\n{traceback.format_exc()}")
