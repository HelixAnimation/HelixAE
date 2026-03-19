# -*- coding: utf-8 -*-
"""
Composition-specific context menu methods: multi-comp actions, Kitsu sync, add-to-comp.
"""

import os

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
        self.core.popup("Reveal multiple comps functionality not yet implemented")

    def setMultipleCompFrameRangesFromKitsu(self, comp_items, kitsu_frame_range):
        """Set frame ranges for multiple compositions from Kitsu data"""
        for comp_item in comp_items:
            userData = comp_item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'comp':
                compId = userData.get('id')
                compName = comp_item.text(0)
                self.tracker.comp_manager.setCompFrameRangeFromKitsu(compId, compName, kitsu_frame_range)

    def setMultipleCompFPSFromKitsu(self, comp_items, kitsu_fps):
        """Set FPS for multiple compositions from Kitsu data"""
        for comp_item in comp_items:
            userData = comp_item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'comp':
                compId = userData.get('id')
                compName = comp_item.text(0)
                self.tracker.comp_manager.setCompFPSFromKitsu(compId, compName, kitsu_fps)

    def setMultipleCompFromKitsu(self, comp_items, kitsu_frame_range, kitsu_fps):
        """Set both frame range and FPS for multiple compositions from Kitsu data"""
        for comp_item in comp_items:
            userData = comp_item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'comp':
                compId = userData.get('id')
                compName = comp_item.text(0)
                self.tracker.comp_manager.setCompFromKitsu(compId, compName, kitsu_frame_range, kitsu_fps)

    def _revealCompInProject(self, compId):
        """Reveal composition in After Effects project panel"""
        self.core.popup("Reveal comp in project functionality not yet implemented")

    def _debugSetCompFrameRange(self, compId, compName, kitsu_frame_range):
        """Debug wrapper for setCompFrameRangeFromKitsu"""
        print(
            f"DEBUG: _debugSetCompFrameRange called with compId={compId}, "
            f"compName={compName}, range={kitsu_frame_range}"
        )
        self.tracker.setCompFrameRangeFromKitsu(compId, compName, kitsu_frame_range)

    @err_catcher(name=__name__)
    def addFootageToActiveComp(self):
        """Add selected footage items to the active composition in After Effects"""
        try:
            selected_items = self.tracker.tw_footage.selectedItems()
            footage_items = [item for item in selected_items
                           if item.data(0, Qt.UserRole) and item.data(0, Qt.UserRole).get('type') == 'footage']

            if not footage_items:
                self.core.popup("No footage items selected")
                return

            footage_list = []
            for item in footage_items:
                userData = item.data(0, Qt.UserRole)
                footage_id = userData.get('id')
                footage_name = item.text(0)
                if footage_id:
                    footage_list.append({'id': footage_id, 'name': footage_name})

            if not footage_list:
                self.core.popup("No valid footage IDs found")
                return

            footage_ids_json = str([f['id'] for f in footage_list]).replace("'", '"')

            script = f"""
            var footageIds = {footage_ids_json};
            var resultStr = '';

            if (!app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {{
                resultStr = 'NO_ACTIVE_COMP';
            }} else {{
                var activeComp = app.project.activeItem;
                var addedCount = 0;
                var failedItems = [];

                for (var i = 0; i < footageIds.length; i++) {{
                    var footageId = footageIds[i];
                    var footageItem = null;

                    for (var j = 1; j <= app.project.numItems; j++) {{
                        var item = app.project.item(j);
                        if (item.id == footageId) {{
                            footageItem = item;
                            break;
                        }}
                    }}

                    if (footageItem) {{
                        try {{
                            var newLayer = activeComp.layers.add(footageItem);
                            newLayer.label = footageItem.label;
                            if (footageItem.parentFolder && footageItem.parentFolder.name) {{
                                newLayer.comment = footageItem.parentFolder.name;
                            }}
                            addedCount++;
                        }} catch (e) {{
                            failedItems.push(footageId + ': ' + e.toString());
                        }}
                    }} else {{
                        failedItems.push(footageId + ': Footage not found');
                    }}
                }}

                resultStr = 'SUCCESS|' + addedCount + '|' + failedItems.length + '|' + failedItems.join('|||');
            }}

            resultStr;
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)

            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if 'NO_ACTIVE_COMP' in result:
                self.core.popup("No active composition found.\n\nPlease open a composition first, then try again.")
                return
            elif result.startswith('SUCCESS|'):
                parts = result.split('|')
                if len(parts) >= 3:
                    added_count = int(parts[1])
                    failed_count = int(parts[2])
                    failed_items_str = parts[3] if len(parts) > 3 else ""

                    if added_count > 0:
                        if failed_count > 0:
                            failed_items = failed_items_str.split('|||') if failed_items_str else []
                            message = f"Added {added_count} footage item(s), but {failed_count} failed:"
                            for item in failed_items[:5]:
                                message += f"\n- {item}"
                            if failed_count > 5:
                                message += f"\n... and {failed_count - 5} more"
                            self.core.popup(message)
                    else:
                        _detail = failed_items_str.replace('|||', '\n') if failed_items_str else "Unknown error"
                        self.core.popup("Failed to add any footage items.\n\n" + _detail)
                else:
                    self.core.popup(f"Unexpected result format:\n{result}")
            else:
                self.core.popup(f"Unexpected result:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error adding footage to active composition:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def addFootageToSelectedComp(self):
        """Add selected footage items to a user-selected composition via dialog"""
        try:
            selected_items = self.tracker.tw_footage.selectedItems()
            footage_items = [item for item in selected_items
                           if item.data(0, Qt.UserRole) and item.data(0, Qt.UserRole).get('type') == 'footage']

            if not footage_items:
                self.core.popup("No footage items selected")
                return

            footage_ids = []
            for item in footage_items:
                userData = item.data(0, Qt.UserRole)
                footage_id = userData.get('id')
                if footage_id:
                    footage_ids.append(footage_id)

            if not footage_ids:
                self.core.popup("No valid footage IDs found")
                return

            script = """
            if (!app.project) {
                'NO_PROJECT';
            } else {
                var comps = [];
                for (var i = 1; i <= app.project.numItems; i++) {
                    var item = app.project.item(i);
                    if (item instanceof CompItem) {
                        comps.push(item.id + '|' + item.name);
                    }
                }
                if (comps.length === 0) {
                    'NO_COMPS';
                } else {
                    comps.join('|||');
                }
            }
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if 'NO_PROJECT' in result:
                self.core.popup("No project open.")
                return
            if 'NO_COMPS' in result:
                self.core.popup("No compositions found in this project.")
                return

            comp_list = result.split('|||')
            if not comp_list:
                self.core.popup("No compositions found.")
                return

            dlg = QDialog(self.tracker.dlg_footage)
            dlg.setWindowTitle("Select Composition")
            dlg.resize(400, 500)

            layout = QVBoxLayout()

            label = QLabel(f"Select composition to add {len(footage_ids)} footage item(s) to:")
            layout.addWidget(label)

            comp_list_widget = QListWidget()
            comp_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
            for comp_str in comp_list:
                parts = comp_str.split('|')
                if len(parts) == 2:
                    comp_id, comp_name = parts
                    item = QListWidgetItem(comp_name)
                    item.setData(Qt.UserRole, comp_id)
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

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing composition selection dialog:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def _addFootageToSelectedCompExecute(self, dialog, comp_list_widget, footage_ids):
        """Execute adding footage to the selected composition"""
        try:
            selected_items = comp_list_widget.selectedItems()
            if not selected_items:
                self.core.popup("Please select a composition.")
                return

            comp_id = selected_items[0].data(Qt.UserRole)
            footage_ids_json = str(footage_ids).replace("'", '"')

            script = f"""
            var compId = {comp_id};
            var footageIds = {footage_ids_json};

            var targetComp = null;
            for (var i = 1; i <= app.project.numItems; i++) {{
                var item = app.project.item(i);
                if (item.id == compId && item instanceof CompItem) {{
                    targetComp = item;
                    break;
                }}
            }}

            if (!targetComp) {{
                'COMP_NOT_FOUND';
            }} else {{
                var addedCount = 0;
                var failedItems = [];

                for (var i = 0; i < footageIds.length; i++) {{
                    var footageId = footageIds[i];
                    var footageItem = null;

                    for (var j = 1; j <= app.project.numItems; j++) {{
                        var item = app.project.item(j);
                        if (item.id == footageId) {{
                            footageItem = item;
                            break;
                        }}
                    }}

                    if (footageItem) {{
                        try {{
                            var newLayer = targetComp.layers.add(footageItem);
                            newLayer.label = footageItem.label;
                            if (footageItem.parentFolder && footageItem.parentFolder.name) {{
                                newLayer.comment = footageItem.parentFolder.name;
                            }}
                            addedCount++;
                        }} catch (e) {{
                            failedItems.push(footageId + ': ' + e.toString());
                        }}
                    }} else {{
                        failedItems.push(footageId + ': Footage not found');
                    }}
                }}

                'SUCCESS|' + addedCount + '|' + failedItems.length + '|' + failedItems.join('|||');
            }}
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            dialog.close()

            if 'COMP_NOT_FOUND' in result:
                self.core.popup("Selected composition not found.")
                return
            elif result.startswith('SUCCESS|'):
                parts = result.split('|')
                if len(parts) >= 3:
                    added_count = int(parts[1])
                    failed_count = int(parts[2])
                    failed_items_str = parts[3] if len(parts) > 3 else ""

                    if added_count > 0:
                        if failed_count > 0:
                            failed_items = failed_items_str.split('|||') if failed_items_str else []
                            message = f"Added {added_count} footage item(s), but {failed_count} failed:"
                            for item in failed_items[:5]:
                                message += f"\n- {item}"
                            if failed_count > 5:
                                message += f"\n... and {failed_count - 5} more"
                            self.core.popup(message)
                    else:
                        _detail = failed_items_str.replace('|||', '\n') if failed_items_str else "Unknown error"
                        self.core.popup("Failed to add any footage items.\n\n" + _detail)
                else:
                    self.core.popup(f"Unexpected result format:\n{result}")
            else:
                self.core.popup(f"Unexpected result:\n{result}")

        except Exception as e:
            import traceback
            dialog.close()
            self.core.popup(f"Error adding footage to selected composition:\n{str(e)}\n\n{traceback.format_exc()}")
