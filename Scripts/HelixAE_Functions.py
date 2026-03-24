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


    @err_catcher(name=__name__)
    def checkAeAlive(self):
        if "psutil" not in globals():
            return

        if self.aePid and psutil.pid_exists(self.aePid):
            self.aeAliveTimer.start(5 * 1000)
        else:
            QApplication.instance().quit()

    @err_catcher(name=__name__)
    def sendCmd(self, cmd):
        """Send a lightweight command over a short-lived socket (does not block the ae_core mutex)"""
        import socket as _socket
        HOST, PORT = '127.0.0.1', 9888
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((HOST, PORT))
                s.sendall(cmd.encode("utf-8"))
                chunks = []
                while True:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    if b'\x00' in chunk:
                        chunks.append(chunk[:chunk.index(b'\x00')])
                        break
                    chunks.append(chunk)
                return b''.join(chunks)
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

    @err_catcher(name=__name__)
    def getCurrentFileName(self, origin=None, path=True):
        """Get current AE project file path"""
        if origin is None:
            # Default origin if not specified
            origin = "footage_tracker"
        cmd = "app.project.file.fsName;"
        filename = (self.sendCmd(cmd) or "".encode()).decode("utf-8")
        if path:
            return filename
        else:
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
    def getImportPaths(self, origin):
        return False

    @err_catcher(name=__name__)
    def hasActiveComp(self):
        cmd = """
        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
            "{\\"result\\": True}";
        } else {
            "{\\"result\\": False}";
        }"""

        result = self.sendCmd(cmd)
        if not result:
            return

        result = result.decode("utf-8")
        if result == "null":
            return

        result = eval(result)
        return result["result"]

    @err_catcher(name=__name__)
    def getCompositionNames(self):
        cmd = """
        function getAllCompositions() {
            var project = app.project;
            var compositions = [];

            if (project && project.items) {
                for (var i = 1; i <= project.items.length; i++) {
                    var item = project.items[i];
                    if (item instanceof CompItem) {
                        compositions.push(item.name);
                    }
                }
            }

            return compositions;
        }

        // Example usage
        var compositions = getAllCompositions();
        var compositionNames = compositions.join(",");
        "{\\"result\\": True, \\"compositions\\": \\"" + compositionNames + "\\"}";"""

        result = self.sendCmd(cmd)
        if not result:
            return

        result = result.decode("utf-8")
        if result == "null":
            return

        result = eval(result)
        return [x for x in result["compositions"].split(",") if x]

    @err_catcher(name=__name__)
    def getFrameRange(self, origin):
        startframe = None
        endframe = None

        cmd = """
        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
            var comp = app.project.activeItem;
            var frameRate = comp.frameRate;
            var startFrame = comp.displayStartFrame;
            var durationFrames = comp.duration * frameRate;
            var endFrame = startFrame + durationFrames - 1;
            "{\\"result\\": True, \\"startFrame\\": " + startFrame + ", \\"endFrame\\": " + endFrame + "}";
        } else {
            "{\\"result\\": False, \\"details\\": \\"No active composition found.\\"}";
        }"""

        result = self.sendCmd(cmd)
        if not result:
            return [startframe, endframe]

        result = result.decode("utf-8")
        if result == "null":
            return [startframe, endframe]

        result = eval(result)
        if result["result"] is True:
            startframe = result["startFrame"]
            endframe = result["endFrame"]

        return [startframe, endframe]

    @err_catcher(name=__name__)
    def setFrameRange(self, origin, startFrame, endFrame):
        cmd = """
        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
            var comp = app.project.activeItem;
            var frameRate = comp.frameRate;
            var startFrame = %s;
            comp.displayStartFrame = startFrame;
            comp.duration = (%s - startFrame + 1) / frameRate;
            comp.workAreaStart = 0;
            comp.workAreaDuration = comp.duration;
            "{\\"result\\": True}";
        } else {
            "{\\"result\\": False, \\"details\\": \\"No active composition found.\\"}";
        }""" % (startFrame, endFrame)
        self.sendCmd(cmd)

    @err_catcher(name=__name__)
    def getFPS(self, origin):
        cmd = """
        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
            var comp = app.project.activeItem;
            var frameRate = comp.frameRate;
            "{\\"result\\": True, \\"frameRate\\": " + frameRate + "}";
        } else {
            "{\\"result\\": False, \\"details\\": \\"No active composition found.\\"}";
        }"""

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        result = eval(result)
        if result["result"] is True:
            return result["frameRate"]
        else:
            return None

    @err_catcher(name=__name__)
    def setFPS(self, origin, fps):
        cmd = """
        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
            var comp = app.project.activeItem;
            comp.frameRate = %s;
            "{\\"result\\": True, \\"frameRate\\": " + comp.frameRate + "}";
        } else {
            "{\\"result\\": False, \\"details\\": \\"No active composition found.\\"}";
        }""" % fps

        self.sendCmd(cmd)

    @err_catcher(name=__name__)
    def getAppVersion(self, origin):
        cmd = """
        if (app) {
            var version = app.version;
            "{\\"result\\": True, \\"version\\": \\"" + version + "\\"}";
        } else {
            "{\\"result\\": False, \\"details\\": \\"No app found.\\"}";
        }"""

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        result = eval(result)
        if result["result"] is True:
            return result["version"]
        else:
            return None

    @err_catcher(name=__name__)
    def openScene(self, origin, filepath, force=False):
        cmd = "app.open(File(\"%s\"));" % filepath
        self.sendCmd(cmd)
        return True

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

            res = res.decode("utf-8")
            if res == "null":
                continue

            result = eval(res)

        return result.get("result") if result else False

    @err_catcher(name=__name__)
    def importMedia(self, filepath, addToComp=False):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return

        if addToComp:
            addToComp = """
    if (activeItem instanceof CompItem) {
        var newLayer = activeItem.layers.add(importedFile);
    }
            """
        else:
            addToComp = ""

        cmd = """
if (app.project) {
    var activeItem = app.project.activeItem;
    var importOptions = new ImportOptions(File("%s"));
    importOptions.sequence = %s;
    if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {
        importOptions.importAs = ImportAsType.FOOTAGE;
    }
    var importedFile = app.project.importFile(importOptions);
    %s
    "{\\"result\\": True, \\"fileName\\": \\"" + importedFile.name + "\\"}";
} else {
    "{\\"result\\": False, \\"details\\": \\"No project found.\\"}";
}""" % (filepaths[0].replace("\\", "/"), "true" if len(filepaths) > 1 else "false", addToComp)

        result = self.sendCmd(cmd)
        return result

    @err_catcher(name=__name__)
    def replaceActiveItem(self, filepath):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return

        cmd = """
if (app.project && app.project.activeItem && app.project.activeItem instanceof FootageItem) {
    var curItem = app.project.activeItem
    if (curItem instanceof FootageItem) {
        curItem.replace(File("%s"));
    }
    "{\\"result\\": True, \\"fileName\\": \\"" + curItem.name + "\\"}";
} else {
    "{\\"result\\": False, \\"details\\": \\"No active item found.\\"}";
}""" % (filepaths[0].replace("\\", "/"))

        if len(filepaths) > 1:
            old_replace = "curItem.replace(File(\"%s\"));" % filepaths[0].replace("\\", "/")
            new_replace = "curItem.replaceWithSequence(File(\"%s\"), false);" % filepaths[0].replace("\\", "/")
            cmd = cmd.replace(old_replace, new_replace)

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        result = eval(result)
        if result["result"] is False:
            self.core.popup(result["details"])

        return result["result"]

    @err_catcher(name=__name__)
    def replaceItem(self, idx, filepath):
        filepaths = self.core.media.getFilesFromSequence(filepath)
        if not filepaths:
            return

        cmd = """
if (app.project) {
    var curItem = app.project.item(%s)
    if (curItem instanceof FootageItem) {
        curItem.replace(File("%s"));
    }
    "{\\"result\\": True, \\"fileName\\": \\"" + curItem.name + "\\"}";
} else {
    "{\\"result\\": False, \\"details\\": \\"No project active.\\"}";
}""" % (idx, filepaths[0].replace("\\", "/"))

        if len(filepaths) > 1:
            old_replace = "curItem.replace(File(\"%s\"));" % filepaths[0].replace("\\", "/")
            new_replace = "curItem.replaceWithSequence(File(\"%s\"), false);" % filepaths[0].replace("\\", "/")
            cmd = cmd.replace(old_replace, new_replace)

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        result = eval(result)
        if result["result"] is False:
            self.core.popup(result["details"])

        return result["result"]

    @err_catcher(name=__name__)
    def getFootageFromProject(self):
        cmd = """
function getAllFootage() {
    var project = app.project;
    var footages = [];

    if (project && project.items) {
        for (var i = 1; i <= project.items.length; i++) {
            var item = project.items[i];
            if (item instanceof FootageItem) {
                footages.push(i);
                footages.push(item.file.path);
                footages.push(item.file.name);
            }
        }
    }

    return footages;
}
if (app.project) {
    var footage = getAllFootage();
    var footageData = footage.join(",");
    "{\\"result\\": True, \\"footage\\": \\"" + footageData + "\\"}";
} else {
    "{\\"result\\": False, \\"details\\": \\"No project active.\\"}";
}"""

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        result = eval(result)
        if result["result"] is False:
            self.core.popup(result["details"])
        else:
            resultData = []
            for idx, data in enumerate(result["footage"].split(",")):
                if (idx % 3) == 2:
                    resultData[-1]["path"] = os.path.normpath(resultData[-1]["path"] + "/" + data)
                    resultData[-1]["name"] = data
                elif (idx % 3) == 1:
                    if data and data[0] == "/" and data[1] != "/" and data[2] == "/":
                        data = data.strip("/")
                        data = os.path.normpath(data[0].upper() + ":" + data[1:])

                    resultData[-1]["path"] = data
                elif data:
                    resultData.append({"idx": int(data)})

            return resultData

    @err_catcher(name=__name__)
    def openImportMediaDlg(self):
        from helixae_ui import ImportMediaDlg
        self.dlg_importMedia = ImportMediaDlg(self)
        self.dlg_importMedia.show()

    @err_catcher(name=__name__)
    def checkVersions(self):
        items = self.getFootageFromProject() or []
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
        cmd = """
if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
    var comp = app.project.activeItem;
    var renderQueueItem = app.project.renderQueue.items.add(comp);
    var outputModule = renderQueueItem.outputModule(1);
    var templateNames = outputModule.templates.join(",")
    renderQueueItem.remove();
    "{\\"result\\": True, \\"templates\\": \\"" + templateNames + "\\"}";
} else {
    "{\\"result\\": False, \\"details\\": \\"No app found.\\"}";
}"""

        result = self.sendCmd(cmd)
        if not result:
            return None

        result = result.decode("utf-8")
        if result == "null":
            return None

        try:
            result = eval(result)
        except Exception:
            result = {"result": False}

        if result["result"] is True:
            templates = [x for x in result["templates"].split(",") if not x.startswith("_HIDDEN") ]
            return templates
        else:
            return None

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
