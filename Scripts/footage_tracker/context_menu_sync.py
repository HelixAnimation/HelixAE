# -*- coding: utf-8 -*-
"""
Sync submenu methods: version, FPS, and resolution sync for footage items.
"""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QAction

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuSync:
    """Mixin: sync submenu actions"""

    def _addSyncMenu(self, menu, footage_items, position):
        """Add 'Sync' submenu with Version, FPS, and Resolution options"""
        syncMenu = menu.addMenu("Sync")

        versionAction = QAction("Version", syncMenu)
        versionAction.setToolTip("Update selected footage to latest version")
        versionAction.triggered.connect(lambda: self.tracker.updateSelectedOutdated())
        syncMenu.addAction(versionAction)

        fpsAction = QAction("FPS", syncMenu)
        fpsAction.setToolTip("Update FPS to Kitsu values")
        fpsAction.triggered.connect(lambda: self.tracker.updateSelectedToKitsuFPS())
        syncMenu.addAction(fpsAction)

        has_3d_render = any(self._is3DRenderFootage(item.data(0, Qt.UserRole).get('path', ''))
                           for item in footage_items if item.data(0, Qt.UserRole))

        if has_3d_render and self.tracker.kitsuShotData:
            first_3d_item = None
            for item in footage_items:
                userData = item.data(0, Qt.UserRole)
                if userData and self._is3DRenderFootage(userData.get('path', '')):
                    first_3d_item = item
                    break

            if first_3d_item:
                file_path = first_3d_item.data(0, Qt.UserRole).get('path', '')
                shot_name = self._extractShotFromFootagePath(file_path)

                kitsu_resolution = None
                if shot_name and shot_name in self.tracker.kitsuShotData:
                    kitsu_data = self.tracker.kitsuShotData[shot_name]
                    kitsu_width = kitsu_data.get('width')
                    kitsu_height = kitsu_data.get('height')
                    if kitsu_width and kitsu_height:
                        try:
                            kitsu_resolution = (int(kitsu_width), int(kitsu_height))
                        except (ValueError, TypeError):
                            pass

                if kitsu_resolution:
                    w, h = kitsu_resolution
                    resolutionAction = QAction(f"Resolution (Kitsu {w}x{h})", syncMenu)
                    resolutionAction.setToolTip(f"Resize selected 3D renders to Kitsu resolution ({w}x{h})")
                    resolutionAction.triggered.connect(
                        lambda checked, width=w, height=h: self._executeBatchResize(
                            self._getSelectedAOVs(), width, height, position
                        )
                    )
                    syncMenu.addAction(resolutionAction)
                else:
                    resolutionAction = QAction("Resolution (No Kitsu data)", syncMenu)
                    resolutionAction.setEnabled(False)
                    syncMenu.addAction(resolutionAction)
        else:
            resolutionAction = QAction("Resolution (3D renders only)", syncMenu)
            resolutionAction.setEnabled(False)
            syncMenu.addAction(resolutionAction)

    @err_catcher(name=__name__)
    def _addSyncMenu_lazy(self, menu, footage_items, position):
        """Lazy-load Sync menu contents"""
        if menu.actions():
            return

        import time
        t_start = time.perf_counter()

        versionAction = QAction("Version", menu)
        versionAction.setToolTip("Update selected footage to latest version")
        versionAction.triggered.connect(lambda: self.tracker.updateSelectedOutdated())
        menu.addAction(versionAction)

        fpsAction = QAction("FPS", menu)
        fpsAction.setToolTip("Update FPS to Kitsu values")
        fpsAction.triggered.connect(lambda: self.tracker.updateSelectedToKitsuFPS())
        menu.addAction(fpsAction)

        has_3d_render = any(self._is3DRenderFootage(item.data(0, Qt.UserRole).get('path', ''))
                           for item in footage_items if item.data(0, Qt.UserRole))

        if has_3d_render and self.tracker.kitsuShotData:
            first_3d_item = None
            for item in footage_items:
                userData = item.data(0, Qt.UserRole)
                if userData and self._is3DRenderFootage(userData.get('path', '')):
                    first_3d_item = item
                    break

            if first_3d_item:
                file_path = first_3d_item.data(0, Qt.UserRole).get('path', '')
                shot_name = self._extractShotFromFootagePath(file_path)

                kitsu_resolution = None
                if shot_name and shot_name in self.tracker.kitsuShotData:
                    kitsu_data = self.tracker.kitsuShotData[shot_name]
                    kitsu_width = kitsu_data.get('width')
                    kitsu_height = kitsu_data.get('height')
                    if kitsu_width and kitsu_height:
                        try:
                            kitsu_resolution = (int(kitsu_width), int(kitsu_height))
                        except (ValueError, TypeError):
                            pass

                if kitsu_resolution:
                    w, h = kitsu_resolution
                    resolutionAction = QAction(f"Resolution (Kitsu {w}x{h})", menu)
                    resolutionAction.setToolTip(f"Resize selected 3D renders to Kitsu resolution ({w}x{h})")
                    resolutionAction.triggered.connect(
                        lambda checked, width=w, height=h: self._executeBatchResize(
                            self._getSelectedAOVs(), width, height, position
                        )
                    )
                    menu.addAction(resolutionAction)
                else:
                    resolutionAction = QAction("Resolution (No Kitsu data)", menu)
                    resolutionAction.setEnabled(False)
                    menu.addAction(resolutionAction)
        else:
            resolutionAction = QAction("Resolution (3D renders only)", menu)
            resolutionAction.setEnabled(False)
            menu.addAction(resolutionAction)

        t_end = time.perf_counter()
        if t_end - t_start > 0.01:
            print(f"[DEBUG MENU] Sync menu (lazy) took {t_end-t_start:.4f}s")
