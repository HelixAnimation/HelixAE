# -*- coding: utf-8 -*-
#
####################################################
#
# Helix AE - Pipeline extension for Adobe After Effects
#
# Copyright (C) 2016-2025 Richard Frangenberg
# Copyright (C) 2023 Prism Software GmbH
# Copyright (C) 2025 Helix Project Contributors
#
# Licensed under GNU LGPL-3.0-or-later
#
# This file is part of Helix AE (based on Prism).
#
# Helix AE is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Helix AE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Helix AE.  If not, see <https://www.gnu.org/licenses/>.


import os
import sys
import socket
import logging
try:
    import psutil
except Exception:
    pass

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher

import helixae_bridge
import helixae_protocol


logger = logging.getLogger(__name__)


class HelixAE_Functions(object):
    def __init__(self, core, plugin):
        self.core = core
        self.plugin = plugin
        self.core.registerCallback(
            "onProjectBrowserStartup", self.onProjectBrowserStartup, plugin=self.plugin
        )
        self.core.registerCallback(
            "mediaPlayerContextMenuRequested", self.mediaPlayerContextMenuRequested, plugin=self.plugin
        )
        self.core.registerCallback(
            "postSaveScene", self.postSaveScene, plugin=self.plugin
        )

        # Initialize submodules (like old plugin - only when Functions is initialized)
        import helixae_core
        import helixae_export

        self.ae_core = helixae_core.HelixAECore(self)
        self.ae_export = helixae_export.HelixAE_Export(self)

        # Footage tracker will be initialized on first use (lazy loading)
        self._ae_footage = None
        self._ae_footage_init_error = None

    @err_catcher(name=__name__)
    def startup(self, origin):
        origin.timer.stop()

        # Disable Prism's built-in framerange mismatch check on scene open
        try:
            checks = self.core.sanities.checksToRun.get("onSceneOpen", {}).get("checks", [])
            self.core.sanities.checksToRun["onSceneOpen"]["checks"] = [
                c for c in checks if c["name"] != "checkFramerange"
            ]
        except Exception:
            pass

        appIcon = QIcon(self.appIcon)
        qapp = QApplication.instance()
        qapp.setWindowIcon(appIcon)

        origin.messageParent = QWidget()
        self.core.setActiveStyleSheet("HelixAE")
        if self.core.useOnTop:
            origin.messageParent.setWindowFlags(
                origin.messageParent.windowFlags() ^ Qt.WindowStaysOnTopHint
            )

        pid = self.getAePid()
        self.aePid = int(pid) if pid else None
        self.aeAliveTimer = QTimer()
        self.aeAliveTimer.timeout.connect(self.checkAeAlive)
        self.aeAliveTimer.setSingleShot(True)
        self.checkAeAlive()
        origin.startAutosaveTimer()

        # Prepare scene data without opening a tracker window. Timer/worker jobs
        # never delay this startup callback or enumerate AE on the GUI thread.
        QTimer.singleShot(0, self._getFootagePreparation)

    def _getFootagePreparation(self):
        preparation = getattr(self, '_footage_preparation', None)
        if preparation is None:
            from footage_tracker.refresh_controller import RefreshController
            preparation = RefreshController(self)
            self._footage_preparation = preparation
        return preparation


    @err_catcher(name=__name__)
    def checkAeAlive(self):
        if "psutil" not in globals():
            return

        if self.aePid and psutil.pid_exists(self.aePid):
            self.aeAliveTimer.start(5 * 1000)
        else:
            QApplication.instance().quit()

    @err_catcher(name=__name__)
    def sendCmd(self, cmd, timeout=3.0):
        """Send a lightweight command over a short-lived socket (does not block the ae_core mutex).

        Requests and responses are null-terminated frames (Scripts/helixae_bridge.py);
        premature EOF is a transport failure and returns None, never b"".

        ``timeout`` covers the whole round trip; pass a larger value for
        blocking AE operations (e.g. renderQueue.render()).
        """
        import socket as _socket
        HOST, PORT = helixae_bridge.AE_HOST, helixae_bridge.AE_PORT
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(float(timeout))
                s.connect((HOST, PORT))
                s.sendall(
                    helixae_bridge.frame_ae_request(
                        helixae_protocol.ensure_json_polyfill(cmd)
                    )
                )
                return helixae_bridge.recv_ae_response(s)
        except Exception as e:
            logger.debug("sendCmd failed: %s" % str(e))
            return None

    @err_catcher(name=__name__)
    def getAePid(self):
        cmd = "pid"
        result = self.sendCmd(cmd)
        if result:
            try:
                return result.decode("utf-8").strip('\x00')
            except Exception:
                pass
        return None

    @err_catcher(name=__name__)
    def autosaveEnabled(self, origin):
        cmd = (
            "app.preferences.getPrefAsLong(\"Auto Save\", \"Enable Auto Save3\","
            " PREFType.PREF_Type_MACHINE_INDEPENDENT);"
        )
        enabled = (self.sendCmd(cmd) or "".encode()).decode("utf-8")
        return enabled == "1"

    @err_catcher(name=__name__)
    def sceneOpen(self, origin):
        if self.core.shouldAutosaveTimerRun():
            origin.startAutosaveTimer()
        self._getFootagePreparation().scene_opened()

    @err_catcher(name=__name__)
    def getCurrentFileName(self, origin=None, path=True):
        """Get current AE project file path ('' when nothing is open)"""
        result = self.sendCmd(helixae_protocol.build_get_current_file())
        data, error = helixae_protocol.parse_json_response(result)
        if error or not data.get("result"):
            return ""
        filename = (data.get("path") or "").replace("\\", "/")
        if path:
            return filename
        return os.path.basename(filename)

    @err_catcher(name=__name__)
    def getSceneExtension(self, origin=None):
        """Get scene file extension"""
        if origin is None:
            origin = "footage_tracker"
        return self.sceneFormats[0]

    @err_catcher(name=__name__)
    def saveScene(self, origin, filepath, details={}):
        # Use ae_core.saveScene which includes archive info generation
        return self.ae_core.saveScene(origin, filepath, details)

    @err_catcher(name=__name__)
    def postSaveScene(self, origin, filepath, versionUp, comment, publish, details):
        # Prism creates versioninfo.json before firing this callback, so it's safe to patch now.
        # Only pass archive data that was produced by THIS save (per-save ownership).
        archive_data = None
        last_path = getattr(self.ae_core, "_last_archive_path", None)
        if last_path and os.path.normpath(os.path.abspath(filepath)) == last_path:
            archive_data = getattr(self.ae_core, "_last_archive_data", None)
        self.ae_core._patchVersionInfo(filepath, archive_data)

    @err_catcher(name=__name__)
    def getImportPaths(self, origin):
        return False

    @err_catcher(name=__name__)
    def hasActiveComp(self):
        result = self.sendCmd(helixae_protocol.build_has_active_comp())
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            return None
        return bool(data.get("result"))

    @err_catcher(name=__name__)
    def getCompositionNames(self):
        result = self.sendCmd(helixae_protocol.build_get_composition_names())
        data, error = helixae_protocol.parse_json_response(result)
        if error or not data.get("result"):
            return None
        return [x for x in data.get("compositions", []) if x]

    @err_catcher(name=__name__)
    def getFrameRange(self, origin):
        startframe = None
        endframe = None

        result = self.sendCmd(helixae_protocol.build_get_frame_range())
        data, error = helixae_protocol.parse_json_response(result)
        if not error and data.get("result"):
            startframe = data.get("startFrame")
            endframe = data.get("endFrame")

        return [startframe, endframe]

    @err_catcher(name=__name__)
    def setFrameRange(self, origin, startFrame, endFrame):
        try:
            cmd = helixae_protocol.build_set_frame_range(startFrame, endFrame)
        except ValueError as e:
            logger.warning("setFrameRange: %s" % e)
            return False
        result = self.sendCmd(cmd)
        data, error = helixae_protocol.parse_json_response(result)
        return bool(data.get("result")) if not error else False

    @err_catcher(name=__name__)
    def getFPS(self, origin):
        result = self.sendCmd(helixae_protocol.build_get_fps())
        data, error = helixae_protocol.parse_json_response(result)
        if error or not data.get("result"):
            return None
        return data.get("frameRate")

    @err_catcher(name=__name__)
    def setFPS(self, origin, fps):
        try:
            cmd = helixae_protocol.build_set_fps(fps)
        except ValueError as e:
            logger.warning("setFPS: %s" % e)
            return False
        result = self.sendCmd(cmd)
        data, error = helixae_protocol.parse_json_response(result)
        return bool(data.get("result")) if not error else False

    @err_catcher(name=__name__)
    def getAppVersion(self, origin):
        result = self.sendCmd(helixae_protocol.build_get_app_version())
        data, error = helixae_protocol.parse_json_response(result)
        if error or not data.get("result"):
            return None
        return data.get("version")

    @err_catcher(name=__name__)
    def openScene(self, origin, filepath, force=False):
        # Project loading can exceed the lightweight command timeout (3s),
        # especially over the NAS. Use the core's 120s operation transport
        # and its confirmed acknowledgement instead of timing out mid-open.
        return self.ae_core.openScene(origin, filepath, force=force)

    @err_catcher(name=__name__)
    def getCurrentSceneFiles(self, origin):
        curFileName = self.core.getCurrentFileName()
        scenefiles = [curFileName]
        return scenefiles

    @err_catcher(name=__name__)
    def onProjectBrowserStartup(self, origin):
        origin.actionStateManager.setEnabled(False)

    @err_catcher(name=__name__)
    def mediaPlayerContextMenuRequested(self, origin, menu):
        if len(origin.seq) > 0 and type(origin).__name__ == "MediaPlayer":
            actReplace = QAction("Replace Active Item...", origin)
            actReplace.triggered.connect(lambda: self.replaceActiveItemFromMediaBrowser(origin))
            menu.addAction(actReplace)

    @err_catcher(name=__name__)
    def replaceActiveItemFromMediaBrowser(self, origin):
        sourceData = origin.compGetImportSource()
        for sourceDat in sourceData:
            filepath = sourceDat[0]
            self.replaceActiveItem(filepath)

    @err_catcher(name=__name__)
    def importImages(self, filepath=None, mediaBrowser=None, parent=None):
        if mediaBrowser:
            if mediaBrowser.origin.getCurrentAOV() and mediaBrowser.origin.w_preview.cb_layer.count() > 1:
                fString = "Please select an import option:"
                buttons = ["Current AOV", "All AOVs"]
                result = self.core.popupQuestion(fString, buttons=buttons, icon=QMessageBox.NoIcon)
            else:
                result = "Current AOV"

            if result == "Current AOV":
                self.importSource(mediaBrowser)
            elif result == "All AOVs":
                self.importAOVs(mediaBrowser)
            else:
                return

    @err_catcher(name=__name__)
    def importSource(self, origin):
        sourceData = origin.compGetImportSource()
        for sourceDat in sourceData:
            filepath = sourceDat[0]
            self.importMedia(filepath)

    @err_catcher(name=__name__)
    def importAOVs(self, origin):
        sourceData = origin.compGetImportPasses()
        for sourceDat in sourceData:
            filepath = sourceDat[0]
            self.importMedia(filepath)

    @err_catcher(name=__name__)
    def sm_getExternalFiles(self, origin):
        footageItems = self.getFootageFromProject() or []
        paths = []
        for footageItem in footageItems:
            paths.append(footageItem["path"])

        return [paths, []]

    @err_catcher(name=__name__)
    def getMediaFromEntities(self, entities, identifier):
        versions = []
        for entity in entities:
            if entity.get("type") != "shot":
                continue

            for idf in [idf.strip() for idf in identifier.split(",")]:
                context = entity.copy()
                if identifier.endswith(" (playblast)"):
                    context["mediaType"] = "playblasts"
                    idf = identifier.replace(" (playblast)", "")
                elif identifier.endswith(" (2d)"):
                    context["mediaType"] = "2drenders"
                    idf = identifier.replace(" (2d)", "")
                elif identifier.endswith(" (external)"):
                    context["mediaType"] = "externalMedia"
                    idf = identifier.replace(" (external)", "")
                else:
                    context["mediaType"] = "3drenders"

                context["identifier"] = idf

                version = self.core.mediaProducts.getLatestVersionFromIdentifier(context)
                if not version:
                    logger.debug("Couldn't find a version for context: %s" % context)
                    continue

                if context.get("mediaType") not in ["playblasts", "2drenders"]:
                    aovs = self.core.mediaProducts.getAOVsFromVersion(version)
                    if not aovs:
                        logger.debug("Couldn't find any AOVs for version: %s" % version)
                        continue

                    aov = aovs[0]
                else:
                    aov = version

                filepaths = self.core.mediaProducts.getFilesFromContext(aov)
                if not filepaths:
                    logger.debug("Couldn't find any files for AOV: %s" % aov)
                    continue

                version["filepaths"] = filepaths
                versions.append(version)

        return versions

    @err_catcher(name=__name__)
    def importMediaVersions(self, entities, identifiers, addToComp=False):
        versions = []
        for identifier in identifiers:
            versions += self.getMediaFromEntities(entities, identifier)

        if not versions:
            msg = "Couldn't find any media for the selected context."
            self.core.popup(msg)
            return False

        result = False
        for version in versions:
            pattern = self.core.media.getSequenceFromFilename(version["filepaths"][0])
            res = self.importMedia(pattern, addToComp=addToComp)
            if not res:
                continue
            result = True

        return result

    @err_catcher(name=__name__)
    def importMedia(self, filepath, addToComp=False):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return None

        cmd = helixae_protocol.build_import_media(
            filepaths[0], sequence=len(filepaths) > 1, add_to_comp=addToComp
        )
        result = self.sendCmd(cmd)
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            self.core.popup("Importing media failed:\n%s" % error)
            return None
        if not data.get("result"):
            self.core.popup(
                "Importing media failed:\n%s"
                % data.get("details", "unknown After Effects error")
            )
            return None
        return True

    @err_catcher(name=__name__)
    def replaceActiveItem(self, filepath):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return None

        cmd = helixae_protocol.build_replace_active_item(
            filepaths[0], sequence=len(filepaths) > 1
        )
        result = self.sendCmd(cmd)
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            self.core.popup("Replacing item failed:\n%s" % error)
            return None
        if not data.get("result"):
            self.core.popup(
                "Replacing item failed:\n%s"
                % data.get("details", "unknown After Effects error")
            )
            return None
        return True

    @err_catcher(name=__name__)
    def replaceItem(self, idx, filepath):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return None

        try:
            cmd = helixae_protocol.build_replace_item(
                idx, filepaths[0], sequence=len(filepaths) > 1
            )
        except ValueError as e:
            logger.warning("replaceItem: %s" % e)
            return None

        result = self.sendCmd(cmd)
        data, error = helixae_protocol.parse_json_response(result)
        if error:
            self.core.popup("Replacing item failed:\n%s" % error)
            return None
        if not data.get("result"):
            self.core.popup(
                "Replacing item failed:\n%s"
                % data.get("details", "unknown After Effects error")
            )
            return None
        return True

    @err_catcher(name=__name__)
    def getFootageFromProject(self):
        """File-backed footage as [{'idx', 'path', 'name'}]; None on failure."""
        result = self.sendCmd(helixae_protocol.build_get_footage_from_project())
        records, error = helixae_protocol.parse_json_array(result)
        if error:
            logger.debug("getFootageFromProject failed: %s" % error)
            return None
        resultData = []
        for record in records:
            if not isinstance(record, dict):
                continue
            try:
                idx = int(record.get("idx"))
            except (TypeError, ValueError):
                continue
            path = record.get("path") or ""
            resultData.append(
                {"idx": idx, "path": os.path.normpath(path), "name": record.get("name") or path}
            )
        return resultData

    @err_catcher(name=__name__)
    def openImportMediaDlg(self):
        from helixae_ui import ImportMediaDlg
        self.dlg_importMedia = ImportMediaDlg(self)
        self.dlg_importMedia.show()

    @err_catcher(name=__name__)
    def checkVersions(self):
        items = self.getFootageFromProject()
        if items is None:
            # Bridge/scan failure is not "everything is up to date".
            self.core.popup(
                "Could not read the footage list from After Effects.\n"
                "Please make sure After Effects is running and the HelixAE panel is open."
            )
            return
        outdatedItems = []
        for item in items:
            version = self.core.mediaProducts.getLatestVersionFromFilepath(item["path"])
            if version and version["path"] not in item["path"]:
                filepattern = self.core.mediaProducts.getFileFromVersion(version, findExisting=True)
                if not filepattern:
                    continue

                item["latestPath"] = filepattern
                outdatedItems.append(item)

        if outdatedItems:
            msg = "The following versions are outdated:\n\n"
            for item in outdatedItems:
                msg += item["name"] + "\n"
        else:
            msg = "All versions are up to date."
            self.core.popup(msg, severity="info")
            return

        result = self.core.popupQuestion(msg, buttons=["Update All", "Cancel"])
        if result == "Update All":
            for item in outdatedItems:
                idx = item["idx"]
                self.replaceItem(idx, item["latestPath"])

    @err_catcher(name=__name__)
    def openRenderDlg(self):
        """Open the export dialog for rendering from AE"""
        return self.ae_export.exportImage()

    @err_catcher(name=__name__)
    def getRenderTemplates(self):
        result = self.sendCmd(helixae_protocol.build_get_output_module_templates())
        data, error = helixae_protocol.parse_json_response(result)
        if error or not data.get("result"):
            return None
        return [
            x
            for x in data.get("templates", [])
            if x and not x.startswith("_HIDDEN")
        ]

    @property
    def ae_footage(self):
        """Lazily initialize the footage tracker on first access"""
        if self._ae_footage is None and self._ae_footage_init_error is None:
            try:
                import helixae_footage_tracker
                self._ae_footage = helixae_footage_tracker.AEFootageTracker(self)
                print("[HelixAE] Footage tracker initialized successfully")
            except Exception as e:
                import traceback
                self._ae_footage_init_error = str(e)
                traceback.print_exc()
                print(f"[HelixAE] Warning: Failed to initialize footage tracker: {e}")
        return self._ae_footage

    @ae_footage.setter
    def ae_footage(self, value):
        """Allow tree_operations to set the tracker reference"""
        self._ae_footage = value
        self._ae_footage_init_error = None

    @err_catcher(name=__name__)
    def openFootageTracker(self):
        """Open the Footage Version Tracker dialog"""
        try:
            # Check if ae_footage was successfully initialized
            tracker = self.ae_footage  # Access through property to trigger lazy loading
            if tracker is None:
                error_msg = self._ae_footage_init_error or "Unknown error"
                self.core.popup(f"Footage Tracker is not available.\n\nInitialization error:\n{error_msg}")
                return None
            # Use the footage tracker
            return tracker.openFootageVersionTracker()
        except Exception as e:
            self.core.popup(f"Failed to open Footage Tracker:\n{str(e)}")
            return None

    @err_catcher(name=__name__)
    def openImportDialog(self):
        """Open the Footage Tracker import dialog directly"""
        try:
            tracker = self.ae_footage
            if tracker is None:
                error_msg = self._ae_footage_init_error or "Unknown error"
                self.core.popup(f"Import dialog is not available.\n\nInitialization error:\n{error_msg}")
                return None
            return tracker.context_menu.showUnifiedImportDialog()
        except Exception as e:
            self.core.popup(f"Failed to open Import dialog:\n{str(e)}")
            return None

    @err_catcher(name=__name__)
    def checkIssues(self):
        """Run the footage tracker issues check from the shelf button"""
        try:
            tracker = self.ae_footage
            if tracker is None:
                error_msg = self._ae_footage_init_error or "Unknown error"
                self.core.popup(f"Check Issues is not available.\n\nInitialization error:\n{error_msg}")
                return None
            return tracker.runStartupWarningsCheck()
        except Exception as e:
            self.core.popup(f"Failed to run Check Issues:\n{str(e)}")
            return None
