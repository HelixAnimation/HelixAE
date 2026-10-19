# -*- coding: utf-8 -*-
"""
Composition-specific context menu methods: multi-comp actions, Kitsu sync, add-to-comp.
"""

import helixae_protocol

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAction, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QAbstractItemView
)

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuCompositions:
    """Mixin: composition context menu actions"""

    def _addMultipleCompActions(self, menu, comp_items, kitsu_shot_data):
        """Add actions for multiple selected compositions"""
        revealAction = QAction("Reveal All in Project", menu)
        revealAction.triggered.connect(lambda: self.revealMultipleComps(comp_items))
        menu.addAction(revealAction)
        menu.addSeparator()

        if kitsu_shot_data:
            kitsuMenu = menu.addMenu("Sync All with Kitsu")

            kitsu_frame_range = kitsu_shot_data.get('frameRange')
            if kitsu_frame_range:
                setFrameRangeAction = QAction(f"Set All Frame Ranges to {kitsu_frame_range}", kitsuMenu)
                setFrameRangeAction.triggered.connect(
                    lambda: self.setMultipleCompFrameRangesFromKitsu(comp_items, kitsu_frame_range)
                )
                kitsuMenu.addAction(setFrameRangeAction)

            kitsu_fps = kitsu_shot_data.get('fps')
            if kitsu_fps:
                setFPSAction = QAction(f"Set All FPS to {kitsu_fps}", kitsuMenu)
                setFPSAction.triggered.connect(
                    lambda: self.setMultipleCompFPSFromKitsu(comp_items, kitsu_fps)
                )
                kitsuMenu.addAction(setFPSAction)

            if kitsu_frame_range and kitsu_fps:
                setBothAction = QAction(
                    f"Set All Frame Ranges & FPS ({kitsu_frame_range} @ {kitsu_fps} fps)", kitsuMenu
                )
                setBothAction.triggered.connect(
                    lambda: self.setMultipleCompFromKitsu(comp_items, kitsu_frame_range, kitsu_fps)
                )
                kitsuMenu.addAction(setBothAction)

    def _addKitsuCompSync(self, menu, compId, compName, kitsu_shot_data):
        """Add Kitsu synchronization options for single composition"""
        syncMenu = menu.addMenu("Sync")

        kitsu_frame_range = kitsu_shot_data.get('frameRange')
        kitsu_fps = kitsu_shot_data.get('fps')
        kitsu_width = kitsu_shot_data.get('width')
        kitsu_height = kitsu_shot_data.get('height')

        if kitsu_frame_range:
            frameRangeAction = QAction("Frame Range", syncMenu)
            frameRangeAction.setToolTip(f"Set frame range to {kitsu_frame_range}")
            frameRangeAction.triggered.connect(
                lambda: self.tracker.setCompFrameRangeFromKitsu(compId, compName, kitsu_frame_range)
            )
            syncMenu.addAction(frameRangeAction)

        if kitsu_fps:
            fpsAction = QAction("FPS", syncMenu)
            fpsAction.setToolTip(f"Set FPS to {kitsu_fps}")
            fpsAction.triggered.connect(
                lambda: self.tracker.setCompFPSFromKitsu(compId, compName, kitsu_fps)
            )
            syncMenu.addAction(fpsAction)

        if kitsu_width and kitsu_height:
            resolutionAction = QAction(f"Resolution ({kitsu_width}x{kitsu_height})", syncMenu)
            resolutionAction.setToolTip(f"Set resolution to Kitsu project resolution ({kitsu_width}x{kitsu_height})")
            resolutionAction.triggered.connect(
                lambda: self.tracker.comp_manager.setCompResolutionFromKitsu(
                    compId, compName, kitsu_width, kitsu_height
                )
            )
            syncMenu.addAction(resolutionAction)

    def revealMultipleComps(self, comp_items):
        """Reveal multiple compositions in project panel"""
        self.tracker.comp_manager.revealMultipleComps(comp_items)

    def setMultipleCompFrameRangesFromKitsu(self, comp_items, kitsu_frame_range):
        """Set frame ranges for multiple compositions from Kitsu data"""
        self.tracker.comp_manager.setMultipleCompFrameRangesFromKitsu(comp_items, kitsu_frame_range)

    def setMultipleCompFPSFromKitsu(self, comp_items, kitsu_fps):
        """Set FPS for multiple compositions from Kitsu data"""
        self.tracker.comp_manager.setMultipleCompFPSFromKitsu(comp_items, kitsu_fps)

    def setMultipleCompFromKitsu(self, comp_items, kitsu_frame_range, kitsu_fps):
        """Set both frame range and FPS for multiple compositions from Kitsu data"""
        self.tracker.comp_manager.setMultipleCompFromKitsu(comp_items, kitsu_frame_range, kitsu_fps)

    def _revealCompInProject(self, compId):
        """Reveal composition in After Effects project panel"""
        self.tracker.comp_manager.revealCompInProject(compId)

    def _selectedFootageIds(self):
        """Collect valid AE footage ids of the current tree selection."""
        selected_items = self.tracker.tw_footage.selectedItems()
        footage_ids = []
        for item in selected_items:
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'footage' and userData.get('id'):
                footage_ids.append(userData['id'])
        return footage_ids

    def _executeCompScript(self, script):
        """Run a comp protocol script. Returns (data, error)."""
        try:
            response = self.tracker.main.ae_core.executeAppleScript(script)
        except Exception as e:
            return None, "After Effects bridge error: %s" % e
        return helixae_protocol.parse_json_response(response)

    @err_catcher(name=__name__)
    def addFootageToActiveComp(self):
        """Add selected footage items to the active composition in After Effects"""
        footage_ids = self._selectedFootageIds()
        if not footage_ids:
            self.core.popup("No footage items selected")
            return

        try:
            script = helixae_protocol.build_add_footage_to_comp(None, footage_ids)
        except (TypeError, ValueError) as e:
            self.core.popup("Error adding footage to active composition:\n%s" % e)
            return

        data, error = self._executeCompScript(script)
        if error:
            self.core.popup("Error adding footage to active composition:\n%s" % error)
            return

        if not data.get("result"):
            reason = data.get("reason") or data.get("details") or ""
            if reason == "no_active_comp":
                self.core.popup(
                    "No active composition found.\n\nPlease open a composition first, then try again.")
            elif reason == "not_a_comp":
                self.core.popup("The active item is not a composition.")
            else:
                self.core.popup("Could not add footage to the active composition.\n%s" % reason)
            return

        self._reportAddResult(data, "active composition")

    @err_catcher(name=__name__)
    def addFootageToSelectedComp(self):
        """Add selected footage items to a user-selected composition via dialog"""
        footage_ids = self._selectedFootageIds()
        if not footage_ids:
            self.core.popup("No footage items selected")
            return

        data, error = self._executeCompScript(helixae_protocol.build_list_project_comps())
        if error:
            self.core.popup("Could not read the composition list:\n%s" % error)
            return
        if not data.get("result"):
            self.core.popup("Could not read the composition list from After Effects.")
            return

        comp_list = [c for c in (data.get("comps") or []) if isinstance(c, dict)]
        if not comp_list:
            self.core.popup("No compositions found in this project.")
            return

        dlg = QDialog(self.tracker.dlg_footage)
        dlg.setWindowTitle("Select Composition")
        dlg.resize(400, 500)

        layout = QVBoxLayout()

        label = QLabel(f"Select composition to add {len(footage_ids)} footage item(s) to:")
        layout.addWidget(label)

        comp_list_widget = QListWidget()
        comp_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        for comp in comp_list:
            item = QListWidgetItem(str(comp.get("name", "")))
            item.setData(Qt.UserRole, comp.get("id"))
            comp_list_widget.addItem(item)

        layout.addWidget(comp_list_widget)

        if comp_list_widget.count() > 0:
            comp_list_widget.setCurrentRow(0)

        button_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        add_btn = QPushButton("Add")
        add_btn.setStyleSheet("QPushButton { font-weight: bold; }")

        cancel_btn.clicked.connect(dlg.reject)
        add_btn.clicked.connect(lambda: self._addFootageToSelectedCompExecute(
            dlg, comp_list_widget, footage_ids
        ))

        button_layout.addWidget(cancel_btn)
        button_layout.addStretch()
        button_layout.addWidget(add_btn)
        layout.addLayout(button_layout)

        dlg.setLayout(layout)
        dlg.exec_()

    @err_catcher(name=__name__)
    def _addFootageToSelectedCompExecute(self, dialog, comp_list_widget, footage_ids):
        """Execute adding footage to the selected composition"""
        selected_items = comp_list_widget.selectedItems()
        if not selected_items:
            self.core.popup("Please select a composition.")
            return

        comp_id = selected_items[0].data(Qt.UserRole)

        try:
            script = helixae_protocol.build_add_footage_to_comp(comp_id, footage_ids)
        except (TypeError, ValueError) as e:
            dialog.close()
            self.core.popup("Error adding footage to selected composition:\n%s" % e)
            return

        data, error = self._executeCompScript(script)
        dialog.close()

        if error:
            self.core.popup("Error adding footage to selected composition:\n%s" % error)
            return

        if not data.get("result"):
            reason = data.get("reason") or data.get("details") or ""
            if reason == "not_a_comp":
                self.core.popup("Selected composition not found.")
            else:
                self.core.popup("Could not add footage to the composition.\n%s" % reason)
            return

        self._reportAddResult(data, "composition")

    def _reportAddResult(self, data, target_label):
        """Report the {addedCount, failedItems} acknowledgement."""
        added_count = int(data.get("addedCount") or 0)
        failed_items = [str(f) for f in (data.get("failedItems") or [])]
        failed_count = len(failed_items)

        if added_count > 0:
            if failed_count > 0:
                message = f"Added {added_count} footage item(s) to {target_label}, but {failed_count} failed:"
                for item in failed_items[:5]:
                    message += f"\n- {item}"
                if failed_count > 5:
                    message += f"\n... and {failed_count - 5} more"
                self.core.popup(message)
        else:
            detail = "\n".join(failed_items) if failed_items else "Unknown error"
            self.core.popup("Failed to add any footage items.\n\n" + detail)
