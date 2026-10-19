# -*- coding: utf-8 -*-
"""
Composition Manager Module (Refactored)
Handles all composition-related operations including info display and Kitsu synchronization
"""

import json
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher

from footage_tracker import comp_cleanup
import helixae_protocol


class CompManager(QObject):
    """Manages composition operations and information"""

    def __init__(self, tracker):
        super(CompManager, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

    # ------------------------------------------------------------------
    # Internal helpers (protocol-based, no string parsing)
    # ------------------------------------------------------------------

    def _execute(self, script):
        """Run a protocol script. Returns (data, error) like parse_json_response."""
        try:
            response = self.main.ae_core.executeAppleScript(script)
        except Exception as e:
            return None, "After Effects bridge error: %s" % e
        return helixae_protocol.parse_json_response(response)

    def _ack(self, data, error):
        """Validate an acknowledgement. Returns (ok, failure_reason)."""
        ok, ack_error = helixae_protocol.ack_result(data, error)
        if ack_error:
            return False, ack_error
        if not ok:
            reason = ""
            if isinstance(data, dict):
                reason = data.get("reason") or data.get("details") or ""
            if reason == "comp_not_found":
                reason = "Composition not found"
            return False, reason or "After Effects reported failure"
        return True, ""

    @staticmethod
    def _parseKitsuFrameRange(kitsu_frame_range):
        """Parse '1001-1100' or '1001-1100 (100)'. Returns ((start, end), error)."""
        text = str(kitsu_frame_range or "").strip()
        if "-" in text:
            frame_parts = text.split("-")
            try:
                start_frame = int(frame_parts[0].strip())
                end_frame = int(frame_parts[1].split()[0].strip())
            except (ValueError, IndexError):
                return None, "Invalid Kitsu frame range format: %s" % kitsu_frame_range
            return (start_frame, end_frame), None
        return None, "Invalid Kitsu frame range format: %s" % kitsu_frame_range

    def _applyFrameRange(self, compId, compName, start_frame, end_frame):
        """Apply a parsed frame range to one comp using its current fps."""
        try:
            comp_id = int(compId)
        except (TypeError, ValueError):
            return False, "Invalid composition id: %r" % (compId,)

        info, error = self._execute(helixae_protocol.build_get_comp_info(comp_id))
        if error:
            return False, error
        if not info.get("result"):
            return False, "Composition not found"

        try:
            script = helixae_protocol.build_set_comp_frame_range(
                comp_id, start_frame, end_frame, info.get("frameRate"))
        except (TypeError, ValueError) as e:
            return False, str(e)

        data, error = self._execute(script)
        if error:
            return False, error
        return self._ack(data, error)

    def _applyFps(self, compId, compName, fps_value):
        """Apply a parsed fps to one comp, preserving the frame count."""
        try:
            comp_id = int(compId)
            script = helixae_protocol.build_set_comp_fps(comp_id, fps_value)
        except (TypeError, ValueError) as e:
            return False, str(e)
        data, error = self._execute(script)
        if error:
            return False, error
        return self._ack(data, error)

    def _applyResolution(self, compId, compName, width_value, height_value):
        """Apply a parsed resolution to one comp."""
        try:
            comp_id = int(compId)
            script = helixae_protocol.build_set_comp_resolution(
                comp_id, width_value, height_value)
        except (TypeError, ValueError) as e:
            return False, str(e)
        data, error = self._execute(script)
        if error:
            return False, error
        return self._ack(data, error)

    def _compIdsFromItems(self, comp_items):
        """Extract (id, name) pairs for comp-type tree items."""
        comps = []
        for item in comp_items or []:
            userData = item.data(0, Qt.UserRole)
            if userData and userData.get('type') == 'comp' and userData.get('id') is not None:
                name = userData.get('compName') or userData.get('name') or ''
                comps.append((userData.get('id'), name))
        return comps

    def _applyToComps(self, comps, apply_fn):
        """Apply per-comp operation. Returns (succeeded_names, [(name, error)])."""
        succeeded, failed = [], []
        for comp_id, comp_name in comps:
            ok, error = apply_fn(comp_id, comp_name)
            if ok:
                succeeded.append(comp_name)
            else:
                failed.append((comp_name, error))
        return succeeded, failed

    def _reportMultiResult(self, succeeded, failed, what):
        """Refresh the tracker once and report a multi-comp result."""
        if succeeded and hasattr(self.tracker, 'tw_footage'):
            self.tracker.loadFootageData()
        total = len(succeeded) + len(failed)
        if failed:
            lines = "\n".join("- %s: %s" % (name, error) for name, error in failed[:10])
            if len(failed) > 10:
                lines += "\n... and %d more" % (len(failed) - 10)
            self.core.popup(
                "Updated %d of %d composition(s) to %s.\n\nFailed:\n%s"
                % (len(succeeded), total, what, lines))
        else:
            self.core.popup(
                "Successfully set %s for %d composition(s)." % (what, len(succeeded)))

    # ------------------------------------------------------------------
    # Single-comp Kitsu sync
    # ------------------------------------------------------------------

    @err_catcher(name=__name__)
    def setCompFrameRangeFromKitsu(self, compId, compName, kitsu_frame_range, silent=False):
        """Set composition frame range from Kitsu data"""
        if not kitsu_frame_range:
            return False

        parsed, error = self._parseKitsuFrameRange(kitsu_frame_range)
        if error:
            if not silent:
                self.core.popup(error)
            return False

        ok, apply_error = self._applyFrameRange(compId, compName, parsed[0], parsed[1])
        if not ok:
            if not silent:
                self.core.popup("Error setting frame range for %s:\n%s" % (compName, apply_error))
            return False

        if not silent and hasattr(self.tracker, 'tw_footage'):
            self.tracker.loadFootageData()
        return True

    @err_catcher(name=__name__)
    def setCompFPSFromKitsu(self, compId, compName, kitsu_fps, silent=False):
        """Set composition FPS from Kitsu data"""
        if not kitsu_fps:
            return False

        try:
            fps_value = float(kitsu_fps)
        except (TypeError, ValueError):
            if not silent:
                self.core.popup("Invalid Kitsu FPS format: %s" % kitsu_fps)
            return False

        ok, apply_error = self._applyFps(compId, compName, fps_value)
        if not ok:
            if not silent:
                self.core.popup("Error setting FPS for %s:\n%s" % (compName, apply_error))
            return False

        if not silent:
            self.core.popup("Successfully set %s FPS to %g" % (compName, fps_value))
            if hasattr(self.tracker, 'tw_footage'):
                self.tracker.loadFootageData()
        return True

    @err_catcher(name=__name__)
    def setCompResolutionFromKitsu(self, compId, compName, kitsu_width, kitsu_height):
        """Set composition resolution from Kitsu data"""
        if not kitsu_width or not kitsu_height:
            return False

        try:
            width_value = int(kitsu_width)
            height_value = int(kitsu_height)
        except (TypeError, ValueError):
            self.core.popup("Invalid Kitsu resolution format: %sx%s" % (kitsu_width, kitsu_height))
            return False

        ok, apply_error = self._applyResolution(compId, compName, width_value, height_value)
        if not ok:
            self.core.popup("Error setting resolution for %s:\n%s" % (compName, apply_error))
            return False

        self.core.popup("Successfully set %s resolution to %dx%d" % (compName, width_value, height_value))
        if hasattr(self.tracker, 'tw_footage'):
            self.tracker.loadFootageData()
        return True

    @err_catcher(name=__name__)
    def setCompFromKitsu(self, compId, compName, kitsu_frame_range, kitsu_fps, silent=False):
        """Set both frame range and FPS from Kitsu data"""
        if not kitsu_frame_range or not kitsu_fps:
            if not silent:
                self.core.popup("Both frame range and FPS are required from Kitsu data")
            return False

        parsed, error = self._parseKitsuFrameRange(kitsu_frame_range)
        if error:
            if not silent:
                self.core.popup(error)
            return False

        try:
            fps_value = float(kitsu_fps)
        except (TypeError, ValueError):
            if not silent:
                self.core.popup("Invalid Kitsu FPS format: %s" % kitsu_fps)
            return False

        fps_ok, fps_error = self._applyFps(compId, compName, fps_value)
        if not fps_ok:
            if not silent:
                self.core.popup("Error setting %s from Kitsu:\n%s" % (compName, fps_error))
            return False

        range_ok, range_error = self._applyFrameRange(compId, compName, parsed[0], parsed[1])
        if not range_ok:
            if not silent:
                self.core.popup("Error setting %s from Kitsu:\n%s" % (compName, range_error))
            return False

        if hasattr(self.tracker, 'tw_footage'):
            self.tracker.loadFootageData()
        return True

    # ------------------------------------------------------------------
    # Comp info display
    # ------------------------------------------------------------------

    @err_catcher(name=__name__)
    def showCompInfo(self, compId, compName):
        """Show detailed information about a composition"""
        # Get current shot for Kitsu comparison
        current_shot = self.tracker.data_parser.extractCurrentShotFromProject()
        kitsu_shot_data = None
        if current_shot and current_shot in self.tracker.kitsuShotData:
            kitsu_shot_data = self.tracker.kitsuShotData[current_shot]

        try:
            script = helixae_protocol.build_get_comp_info(int(compId))
        except (TypeError, ValueError):
            self.core.popup("Invalid composition id: %r" % (compId,))
            return

        data, error = self._execute(script)
        if error:
            self.core.popup("Error getting composition info:\n%s" % error)
            return
        if not data.get("result"):
            self.core.popup("Could not read composition info for '%s'.\n%s" % (compName, data.get("reason") or ""))
            return

        comp_info = data

        # Create info dialog
        dialog = QDialog(self.tracker.dlg_footage)
        dialog.setWindowTitle("Composition Info - %s" % compName)
        dialog.resize(500, 600)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Title
        title = QLabel("<h2>%s</h2>" % comp_info.get('name', 'Unknown'))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Basic info
        info_text = QTextEdit()
        info_text.setReadOnly(True)

        info_content = """
<b>Composition Settings:</b><br>
• Dimensions: {width} x {height}<br>
• Pixel Aspect Ratio: {pixelAspect}<br>
• Frame Rate: {frameRate} fps<br>
• Frame Range: {frameRange}<br>
• Duration: {duration} seconds<br><br>

<b>Layers:</b><br>
• Total Layers: {layerCount}<br>
• Used Layers: {usedLayers}<br>
• Unused Layers: {unused}
        """.format(
            width=comp_info.get('width', 'N/A'),
            height=comp_info.get('height', 'N/A'),
            pixelAspect=comp_info.get('pixelAspect', 'N/A'),
            frameRate=comp_info.get('frameRate', 'N/A'),
            frameRange=comp_info.get('frameRange', 'N/A'),
            duration=comp_info.get('duration', 'N/A'),
            layerCount=comp_info.get('layerCount', 'N/A'),
            usedLayers=comp_info.get('usedLayers', 'N/A'),
            unused=comp_info.get('layerCount', 0) - comp_info.get('usedLayers', 0),
        )

        # Add Kitsu comparison if available
        if kitsu_shot_data:
            frame_range = kitsu_shot_data.get('frameRange', 'N/A')
            kitsu_fps = kitsu_shot_data.get('fps', 'N/A')
            kitsu_info = (
                "<br><b>Kitsu Shot Data:</b><br>"
                "• Expected Frame Range: %s<br>"
                "• Expected FPS: %s<br>" % (frame_range, kitsu_fps)
            )
            info_content += kitsu_info

        info_text.setHtml(info_content)
        layout.addWidget(info_text)

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)

        dialog.exec_()

    @err_catcher(name=__name__)
    def showRawCompInfo(self, compId, compName):
        """Show raw composition information without calculations"""
        try:
            script = helixae_protocol.build_get_comp_info(int(compId))
        except (TypeError, ValueError):
            self.core.popup("Invalid composition id: %r" % (compId,))
            return

        data, error = self._execute(script)
        if error:
            self.core.popup("Error getting raw composition info:\n%s" % error)
            return
        if not data.get("result"):
            self.core.popup(
                "Could not read composition info for '%s'.\n%s" % (compName, data.get("reason") or ""))
            return

        lines = [
            compName,
            "ID: %s" % compId,
            "Width: %s" % data.get('width', 'N/A'),
            "Height: %s" % data.get('height', 'N/A'),
            "Pixel Aspect: %s" % data.get('pixelAspect', 'N/A'),
            "Frame Duration: %s" % data.get('frameDuration', 'N/A'),
            "Start Time: %s" % data.get('startTime', 'N/A'),
            "Duration: %s" % data.get('duration', 'N/A'),
            "Display Start Time: %s" % data.get('displayStartTime', 'N/A'),
            "Display Start Frame: %s" % data.get('displayStartFrame', 'N/A'),
            "Frame Rate: %s" % data.get('frameRate', 'N/A'),
            "Work Area Start: %s" % data.get('workAreaStart', 'N/A'),
            "Work Area Duration: %s" % data.get('workAreaDuration', 'N/A'),
            "Layer Count: %s" % data.get('layerCount', 'N/A'),
        ]

        # Show raw info dialog
        self.tracker.showSelectableMessage(
            "Raw Composition Info - %s" % compName, "\n".join(str(line) for line in lines))

    # ------------------------------------------------------------------
    # Reveal operations
    # ------------------------------------------------------------------

    @err_catcher(name=__name__)
    def revealMultipleComps(self, comp_items):
        """Reveal multiple compositions in the project panel"""
        comps = self._compIdsFromItems(comp_items)
        if not comps:
            self.core.popup("No valid compositions selected")
            return

        try:
            script = helixae_protocol.build_reveal_items_in_project(
                [comp_id for comp_id, _ in comps])
        except (TypeError, ValueError) as e:
            self.core.popup("Error revealing compositions:\n%s" % e)
            return

        data, error = self._execute(script)
        if error:
            self.core.popup("Error revealing compositions:\n%s" % error)
            return

        ok, fail_error = self._ack(data, error)
        if not ok:
            self.core.popup("Error revealing compositions:\n%s" % fail_error)
            return

        count = data.get("revealedCount", len(comps))
        self.core.popup("Successfully revealed %d composition(s) in the project panel" % count)

    def revealCompInProject(self, compId):
        """Reveal composition in After Effects project panel"""
        try:
            script = helixae_protocol.build_reveal_item_in_project(int(compId))
        except (TypeError, ValueError) as e:
            self.core.popup("Error revealing composition:\n%s" % e)
            return False

        data, error = self._execute(script)
        if error:
            self.core.popup("Error revealing composition:\n%s" % error)
            return False

        ok, fail_error = self._ack(data, error)
        if not ok:
            self.core.popup("Error revealing composition:\n%s" % fail_error)
            return False
        return True

    # ------------------------------------------------------------------
    # Multiple composition sync
    # ------------------------------------------------------------------

    def setMultipleCompFrameRangesFromKitsu(self, comp_items, kitsu_frame_range):
        """Set frame ranges for multiple compositions from Kitsu data"""
        if not comp_items or not kitsu_frame_range:
            return

        comps = self._compIdsFromItems(comp_items)
        if not comps:
            self.core.popup("No valid compositions selected")
            return

        parsed, error = self._parseKitsuFrameRange(kitsu_frame_range)
        if error:
            self.core.popup(error)
            return

        succeeded, failed = self._applyToComps(
            comps,
            lambda comp_id, comp_name: self._applyFrameRange(
                comp_id, comp_name, parsed[0], parsed[1]))
        self._reportMultiResult(succeeded, failed, "frame range %s" % kitsu_frame_range)

    def setMultipleCompFPSFromKitsu(self, comp_items, kitsu_fps):
        """Set FPS for multiple compositions from Kitsu data"""
        if not comp_items or not kitsu_fps:
            return

        comps = self._compIdsFromItems(comp_items)
        if not comps:
            self.core.popup("No valid compositions selected")
            return

        try:
            fps_value = float(kitsu_fps)
        except (TypeError, ValueError):
            self.core.popup("Invalid Kitsu FPS format: %s" % kitsu_fps)
            return

        succeeded, failed = self._applyToComps(
            comps,
            lambda comp_id, comp_name: self._applyFps(comp_id, comp_name, fps_value))
        self._reportMultiResult(succeeded, failed, "FPS to %g" % fps_value)

    def setMultipleCompFromKitsu(self, comp_items, kitsu_frame_range, kitsu_fps):
        """Set both frame range and FPS for multiple compositions from Kitsu data"""
        if not comp_items or not kitsu_frame_range or not kitsu_fps:
            return

        comps = self._compIdsFromItems(comp_items)
        if not comps:
            self.core.popup("No valid compositions selected")
            return

        parsed, error = self._parseKitsuFrameRange(kitsu_frame_range)
        if error:
            self.core.popup(error)
            return

        try:
            fps_value = float(kitsu_fps)
        except (TypeError, ValueError):
            self.core.popup("Invalid Kitsu FPS format: %s" % kitsu_fps)
            return

        def apply_both(comp_id, comp_name):
            fps_ok, fps_error = self._applyFps(comp_id, comp_name, fps_value)
            if not fps_ok:
                return False, fps_error
            return self._applyFrameRange(comp_id, comp_name, parsed[0], parsed[1])

        succeeded, failed = self._applyToComps(comps, apply_both)
        self._reportMultiResult(
            succeeded, failed, "%s @ %g fps" % (kitsu_frame_range, fps_value))

    @err_catcher(name=__name__)
    def removeUnusedFromComp(self, compId, compName):
        """Remove compositions and footage not used by the selected composition"""
        try:
            try:
                comp_id_int = comp_cleanup.normalize_comp_id(compId)
            except (TypeError, ValueError):
                self.core.popup(f"Invalid composition identifier for '{compName}': {compId!r}")
                return

            query_result = comp_cleanup.parse_unused_items_result(
                self.main.ae_core.executeAppleScript(
                    comp_cleanup.build_unused_items_script(comp_id_int)))

            if not query_result["ok"]:
                self.core.popup(
                    f"Could not determine unused items for '{compName}':\n\n"
                    f"{query_result['error']}\n\nNo items were removed."
                )
                return

            if query_result["reason"]:
                reason = query_result["reason"]
                if reason == comp_cleanup.STATUS_NO_PROJECT:
                    message = "There is no open project in After Effects."
                elif reason == comp_cleanup.STATUS_COMP_NOT_FOUND:
                    message = (
                        f"The composition '{compName}' no longer exists in the project.\n\n"
                        "Refresh the footage tracker and try again."
                    )
                else:
                    message = "The selected item is not a composition."
                QMessageBox.information(
                    self.tracker.dlg_footage,
                    "Cannot Remove Unused Items",
                    message
                )
                return

            unused_footage = query_result["unused"]["footage"]
            unused_comps = query_result["unused"]["comps"]

            if not unused_footage and not unused_comps:
                QMessageBox.information(
                    self.tracker.dlg_footage,
                    "No Unused Items",
                    f"All items in the project are used by '{compName}'.\n\nNothing to remove."
                )
                return

            reply = self._showRemoveUnusedDialog(unused_footage, unused_comps, compName)
            if reply != QDialog.Accepted:
                return

            summary = self._executeRemoval(unused_footage, unused_comps, comp_id_int)

            if hasattr(self.tracker, 'tw_footage'):
                self.tracker.loadFootageData()

            if summary["canceled"]:
                title = "Removal Canceled"
                header = "Removal was canceled. Results before canceling:"
            else:
                title = "Removal Complete"
                header = "Removal finished:"

            message = (
                f"{header}\n\n"
                f"- Removed: {summary['removed']} item(s)\n"
                f"- No longer in project: {summary['not_found']}\n"
                f"- Kept because in use: {summary['retained']}\n"
                f"- Wrong type (skipped): {summary['wrong_type']}\n"
                f"- Failed: {summary['failed']}\n\n"
                "The footage tracker has been refreshed."
            )
            if summary["failed_details"]:
                details = "\n".join(summary["failed_details"][:10])
                if len(summary["failed_details"]) > 10:
                    details += f"\n... and {len(summary['failed_details']) - 10} more"
                message += f"\n\nFailed items:\n{details}"

            QMessageBox.information(self.tracker.dlg_footage, title, message)

        except Exception as e:
            import traceback
            self.core.popup(f"Error removing unused items:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def _showRemoveUnusedDialog(self, unused_footage, unused_comps, comp_name):
        """Show confirmation dialog with tabs for comps and footage"""
        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dialog = QDialog(parent)
        dialog.setWindowTitle(f"Remove Unused Items - '{comp_name}'")
        dialog.resize(700, 550)

        layout = QVBoxLayout()
        dialog.setLayout(layout)

        # Summary message
        msg = QLabel(
            f"<h3>Remove Unused Items</h3>"
            f"<p>This will remove items that are <b>NOT</b> used by <b>'{comp_name}'</b>:</p>"
            f"<p>• <b>{len(unused_comps)}</b> composition(s)</p>"
            f"<p>• <b>{len(unused_footage)}</b> footage item(s)</p>"
            f"<p style='background-color: #2b2b2b; padding: 10px; border-radius: 4px;'>"
            f"<span style='color: orange;'>&#9888; Items will be removed from the AE project only</span><br>"
            f"<span style='color: #4CAF50;'>Files will NOT be deleted from disk</span></p>"
            f"<p>This removal is wrapped in an AE undo group: you can undo it in After Effects (Edit &gt; Undo).</p>"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        # Tab widget for detailed lists
        tabs = QTabWidget()

        # Compositions tab
        if unused_comps:
            comp_list = QListWidget()
            for comp_id, comp_name in sorted(unused_comps.items(), key=lambda x: x[1]):
                comp_list.addItem(f"{comp_name} (ID: {comp_id})")
            tabs.addTab(comp_list, f"Compositions ({len(unused_comps)})")
        else:
            no_comps_label = QLabel("No unused compositions")
            no_comps_label.setAlignment(Qt.AlignCenter)
            tabs.addTab(no_comps_label, "Compositions (0)")

        # Footage tab
        if unused_footage:
            footage_list = QListWidget()
            for footage_id, footage_name in sorted(unused_footage.items(), key=lambda x: x[1]):
                footage_list.addItem(f"{footage_name} (ID: {footage_id})")
            tabs.addTab(footage_list, f"Footage ({len(unused_footage)})")
        else:
            no_footage_label = QLabel("No unused footage")
            no_footage_label.setAlignment(Qt.AlignCenter)
            tabs.addTab(no_footage_label, "Footage (0)")

        layout.addWidget(tabs)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        remove_btn = QPushButton("Remove Items")
        remove_btn.setStyleSheet("background-color: #d32f2f; color: white; padding: 8px 20px; font-weight: bold;")
        remove_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(remove_btn)

        layout.addLayout(button_layout)

        return dialog.exec_()

    @err_catcher(name=__name__)
    def _executeRemoval(self, unused_footage, unused_comps, comp_id):
        """Execute the removal in batches with a cancelable progress dialog.

        Returns a summary dict with actual per-item outcome counts from
        After Effects (removed / not_found / retained / wrong_type / failed).
        """
        from qtpy.QtWidgets import QProgressDialog
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import QApplication

        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None

        comp_ids = list(unused_comps.keys())
        footage_ids = list(unused_footage.keys())
        all_ids = comp_ids + footage_ids
        total_items = len(all_ids)

        summary = {
            "removed": 0,
            "not_found": 0,
            "retained": 0,
            "wrong_type": 0,
            "failed": 0,
            "failed_details": [],
            "canceled": False,
        }

        progress = QProgressDialog(
            f"Removing {total_items} unused items...",
            "Cancel",
            0,
            total_items,
            parent
        )
        progress.setWindowTitle("Removing Unused Items")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        batch_size = 20
        processed = 0
        try:
            for start in range(0, total_items, batch_size):
                if progress.wasCanceled():
                    summary["canceled"] = True
                    break

                batch = all_ids[start:start + batch_size]
                end = start + len(batch)
                progress.setLabelText(f"Removing items {start + 1}-{end} of {total_items}...")
                QApplication.processEvents()

                try:
                    batch_ids = comp_cleanup.normalize_item_ids(batch)
                except (TypeError, ValueError) as e:
                    summary["failed"] += len(batch)
                    summary["failed_details"].append(str(e))
                    break

                result = comp_cleanup.parse_remove_items_result(
                    self.main.ae_core.executeAppleScript(
                        comp_cleanup.build_remove_items_script(comp_id, batch_ids)))

                if not result["ok"]:
                    summary["failed"] += len(batch)
                    summary["failed_details"].append(result["error"])
                    break

                counts = comp_cleanup.summarize_removal_results(result["results"])
                for key in ("removed", "not_found", "retained", "wrong_type", "failed"):
                    summary[key] += counts[key]
                summary["failed_details"].extend(counts["failed_details"])

                processed += len(batch)
                progress.setValue(processed)
                QApplication.processEvents()
        finally:
            progress.close()

        return summary