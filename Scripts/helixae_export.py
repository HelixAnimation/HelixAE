# -*- coding: utf-8 -*-
"""
Helix AE Export Functions
Handles exporting renders from AE to Prism pipeline
"""

import os
import platform
from qtpy.QtCore import *
from qtpy.QtGui import QCursor
from qtpy.QtWidgets import *

import helixae_protocol
import helixae_render_deps
from PrismUtils.Decorators import err_catcher as err_catcher


class HelixAE_Export:
    def __init__(self, main):
        self.main = main
        self.core = main.core

    def _getActiveCompInfo(self):
        """Return the active composition as ``{id, name}`` or None."""
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_get_active_comp_info()
            )
            data, error = helixae_protocol.parse_json_response(result)
            if error:
                self.core.popup(
                    "Could not determine the active composition:\n%s" % error
                )
                return None
            if not data.get("result"):
                self.core.popup(
                    "Could not determine the active composition:\n%s"
                    % data.get("details", "no active composition")
                )
                return None
            comp_id = data.get("compId")
            comp_name = data.get("compName")
            if comp_id is None or not comp_name:
                self.core.popup(
                    "Could not determine the active composition:\n"
                    "After Effects returned an incomplete response."
                )
                return None
            return {"id": str(comp_id), "name": str(comp_name)}
        except Exception as e:
            self.core.popup(
                "Could not determine the active composition:\n%s" % e
            )
            return None

    @err_catcher(name=__name__)
    def exportImage(self):
        """Show export dialog for rendering from AE"""
        if not self.core.projects.ensureProject() or not self.core.users.ensureUser():
            return False

        comp = self._getActiveCompInfo()
        if comp is None:
            return False
        self._render_comp = comp

        self.dlg_export = QDialog()
        self.core.parentWindow(self.dlg_export)
        self.dlg_export.setWindowTitle("Helix AE - Export - %s" % comp["name"])

        self.setupExportUI()
        self.exportGetTasks()
        self.dlg_export.show()
        return True

    def setupExportUI(self):
        """Build export dialog UI"""
        lo_export = QVBoxLayout()
        self.dlg_export.setLayout(lo_export)

        self.w_task = QWidget()
        lo_prismExport = QVBoxLayout()
        self.w_task.setLayout(lo_prismExport)

        comp = getattr(self, "_render_comp", None)
        comp_text = "unknown composition"
        if comp:
            comp_text = "%s (ID: %s)" % (comp["name"], comp["id"])
        self.l_comp = QLabel("Composition: %s" % comp_text)
        self.l_comp.setWordWrap(True)
        lo_prismExport.addWidget(self.l_comp)

        # Task selection
        lo_task = QHBoxLayout()
        self.le_task = QLineEdit()
        self.b_task = QPushButton("...")
        self.b_task.setFixedSize(24, 24)
        self.b_task.setStyleSheet("padding: 0px; border: none;")
        lo_task.addWidget(QLabel("Task:"))
        lo_task.addWidget(self.le_task)
        lo_task.addWidget(self.b_task)

        # Comment
        self.w_comment = QWidget()
        lo_comment = QHBoxLayout()
        self.w_comment.setLayout(lo_comment)
        self.le_comment = QLineEdit()
        lo_comment.addWidget(QLabel("Comment (optional):"))
        lo_comment.addWidget(self.le_comment)

        # Version
        lo_version = QHBoxLayout()
        self.chb_useNextVersion = QCheckBox("Use next version")
        self.chb_useNextVersion.setChecked(True)
        self.cb_versions = QComboBox()
        self.cb_versions.setEnabled(False)
        lo_version.addWidget(self.chb_useNextVersion)
        lo_version.addWidget(self.cb_versions)
        lo_version.addStretch()

        # Output format
        lo_extension = QHBoxLayout()
        self.cb_formats = QComboBox()
        outputModules = self.getOutputModules()
        self.cb_formats.addItems(outputModules)
        lo_extension.addWidget(QLabel("Output Module:"))
        lo_extension.addWidget(self.cb_formats)
        lo_extension.addStretch()

        # Local output
        self.chb_localOutput = QCheckBox("Local output")
        if not self.core.useLocalFiles:
            self.chb_localOutput.setVisible(False)

        lo_prismExport.addLayout(lo_task)
        lo_prismExport.addWidget(self.w_comment)
        lo_prismExport.addLayout(lo_version)
        lo_prismExport.addLayout(lo_extension)
        lo_prismExport.addWidget(self.chb_localOutput)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.b_render = QPushButton("Add to Render Queue")

        button_layout.addWidget(self.b_render)

        lo_export.addWidget(self.w_task)
        lo_export.addStretch()
        lo_export.addLayout(button_layout)

        # Connect signals
        self.b_task.clicked.connect(self.exportShowTasks)
        self.le_comment.textChanged.connect(
            lambda: self.core.validateLineEdit(self.le_comment)
        )
        self.chb_useNextVersion.toggled.connect(
            lambda checked: (
                self.cb_versions.setEnabled(not checked), 
                self.w_comment.setEnabled(checked)
            )
        )
        self.le_task.editingFinished.connect(self.exportGetVersions)
        self.b_render.clicked.connect(self.renderAndSave)

    def getOutputModules(self):
        """Query After Effects for available output module templates"""
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_get_output_module_templates()
            )
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                raise Exception(
                    error or data.get("details", "unknown After Effects error")
                )
            modules = data.get("templates") or []
            return [x.strip() for x in modules if x.strip() and "_HIDDEN" not in x.upper()]
        except Exception as e:
            # Fallback to common output modules if the bridge fails
            print(f"[HelixAE Export] Could not read output modules: {e}")
            return ["Lossless", "PNG Sequence", "JPEG Sequence", "H.264"]

    @err_catcher(name=__name__)
    def exportGetTasks(self):
        """Get available 2D tasks"""
        self.taskList = self.core.getTaskNames("2d")
        if "_ShotCam" in self.taskList:
            self.taskList.remove("_ShotCam")
        self.b_task.setHidden(len(self.taskList) == 0)

    @err_catcher(name=__name__)
    def exportShowTasks(self):
        """Show task selection menu"""
        tmenu = QMenu(self.dlg_export)
        for task in self.taskList:
            action = QAction(task, self.dlg_export)
            action.triggered.connect(
                lambda _, t=task: (self.le_task.setText(t), self.exportGetVersions())
            )
            tmenu.addAction(action)
        tmenu.exec_(QCursor.pos())

    @err_catcher(name=__name__)
    def exportGetVersions(self):
        """Get existing versions for selected task"""
        outData = self.exportGetOutputName()
        if not outData:
            return
        
        versionDir = os.path.dirname(outData[1])
        existingVersions = []
        
        if os.path.exists(versionDir):
            for item in reversed(sorted(os.listdir(versionDir))):
                if len(item) >= 5 and item.startswith("v") and item[1:5].isnumeric():
                    existingVersions.append(item)
        
        self.cb_versions.clear()
        self.cb_versions.addItems(existingVersions if existingVersions else [outData[2]])

    @err_catcher(name=__name__)
    def exportGetOutputName(self, useVersion="next"):
        """Generate output path for export"""
        if not self.le_task.text():
            return None
        
        task = self.le_task.text()
        outputModule = self.cb_formats.currentText()
        
        # Map output modules to file extensions
        extensionMap = {
            "PNG_Helix": ".png", 
            "H264_Helix": ".mp4"
        }
        extension = extensionMap.get(outputModule, ".avi")
        
        fileName = self.core.getCurrentFileName()
        fnameData = self.core.getScenefileData(fileName)
        if "type" not in fnameData:
            return None
        
        versionToUse = None if useVersion == "next" else useVersion
        outputPathData = self.core.mediaProducts.generateMediaProductPath(
            entity=fnameData, 
            task=task, 
            extension=extension,
            comment=fnameData.get("comment", ""), 
            framePadding="",
            version=versionToUse, 
            location="global",
            returnDetails=True, 
            mediaType="2drenders"
        )
        
        return outputPathData["path"], os.path.dirname(outputPathData["path"]), outputPathData["version"]

    def _currentPipelineFile(self):
        """Return the current .aep path if it belongs to this project."""
        currentFile = self.core.getCurrentFileName()
        projectPath = getattr(self.core, 'projectPath', self.core.prismRoot)

        if not currentFile or not projectPath or not os.path.normpath(currentFile).lower().startswith(
            os.path.normpath(projectPath).lower()
        ):
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                "The current file is not inside the Pipeline.\n"
                "Use the Project Browser to create a file in the Pipeline."
            )
            return None
        return currentFile

    def _validateExportInputs(self):
        """Return (taskName, currentFile) or (None, None) after warning."""
        taskName = self.le_task.text()
        if not taskName:
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                "Please choose a taskname"
            )
            return None, None

        currentFile = self._currentPipelineFile()
        if not currentFile:
            return None, None
        return taskName, currentFile

    def _collectCompDependencies(self, comp):
        """Return ``(block, missing_paths, error)`` for one composition."""
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_comp_dependency_script(comp["id"])
            )
        except Exception as e:
            return None, [], str(e)

        parsed, error = helixae_protocol.parse_comp_dependency_result(result)
        if error:
            return None, [], error

        try:
            from footage_tracker.utils import FootageUtils
            block, missing = helixae_render_deps.build_render_dependencies_block(
                parsed["composition"],
                parsed["footage"],
                FootageUtils.detectFolderType,
                os.path.exists,
            )
        except Exception as e:
            return None, [], "could not classify dependencies: %s" % e
        return block, missing, None

    def _confirmDependencyProblem(self, title, text, details):
        """Show a Continue/Stop dialog.  Returns True to continue."""
        parent = self.dlg_export if hasattr(self, "dlg_export") else self.core.messageParent
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        if details:
            box.setInformativeText(details)
        continue_button = box.addButton("Continue", QMessageBox.AcceptRole)
        stop_button = box.addButton("Stop", QMessageBox.RejectRole)
        box.setDefaultButton(stop_button)
        box.exec_()
        return box.clickedButton() is continue_button

    def _prepareRenderDependencies(self):
        """Collect comp metadata before queueing.

        Returns ``(continue, block)``.  ``continue`` is False only when the
        user chose Stop.  On a failed scan plus Continue, ``block`` is None
        so the stale ``renderDependencies`` key is removed instead of writing
        a misleading empty list.
        """
        comp = getattr(self, "_render_comp", None)
        if comp is None:
            return True, None

        block, missing, error = self._collectCompDependencies(comp)
        if error:
            keep_going = self._confirmDependencyProblem(
                "Dependency Scan Failed",
                "Could not collect dependencies for '%s'." % comp["name"],
                "%s\n\nContinue without renderDependencies metadata, or stop "
                "before adding the render to the queue." % error,
            )
            return keep_going, None

        if missing:
            shown = "\n".join(missing[:10])
            if len(missing) > 10:
                shown += "\n... and %d more" % (len(missing) - 10)
            keep_going = self._confirmDependencyProblem(
                "Missing Source Files",
                "%d source file(s) used by '%s' could not be found."
                % (len(missing), comp["name"]),
                "%s\n\nOn Continue, missing files are excluded from "
                "renderDependencies." % shown,
            )
            if not keep_going:
                return False, None

        return True, block

    def _addRenderQueueItem(self, outputPath, selectedOutputModule, comp_id=None):
        """Add a specific comp (or the active comp) to the AE render queue.

        Returns the confirmed acknowledgement dict (including frame range,
        fps, and composition identity) or None when After Effects did not
        confirm the queue item.  On failure a partial queue item is removed
        by the AE script itself and the reason is shown to the user.
        """
        try:
            result = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_add_to_render_queue(
                    outputPath, selectedOutputModule, comp_id
                )
            )
        except Exception as e:
            self.core.popup(f"Could not add the render to the queue:\n{e}")
            return None

        data, error = helixae_protocol.parse_json_response(result)
        if error:
            self.core.popup(f"Could not add the render to the queue:\n{error}")
            return None
        if not data.get("result"):
            self.core.popup(
                "Could not add the render to the queue:\n%s"
                % data.get("details", "unknown After Effects error")
            )
            return None
        return data

    def _writeExportMetadata(self, ack, outputPath, taskName, hVersion, fileName,
                             render_dependencies=None):
        """Persist versioninfo + dependency patch AFTER a confirmed queue add.

        Returns ``(ok, error)``.  A failure here does not remove the queued
        render, but the caller must report it instead of claiming full
        success.
        """
        fnameData = self.core.getScenefileData(fileName)

        details = fnameData.copy()
        if "filename" in details:
            del details["filename"]
        if "extension" in details:
            del details["extension"]

        details["version"] = hVersion
        details["sourceScene"] = fileName.replace("\\", "/")
        details["identifier"] = taskName
        details["comment"] = self.le_comment.text()

        if ack.get("startFrame") is not None:
            details["startframe"] = int(ack["startFrame"])
        if ack.get("endFrame") is not None:
            details["endframe"] = int(ack["endFrame"])
        if ack.get("fps"):
            details["fps"] = float(ack["fps"])

        try:
            self.core.saveVersionInfo(
                filepath=os.path.dirname(outputPath),
                details=details
            )
        except Exception as e:
            return False, "versioninfo.json could not be created: %s" % e

        result = self._patchRenderVersionInfo(
            outputPath, fileName, render_dependencies
        )
        return result

    def _reportMetadataFailure(self, error):
        QMessageBox.warning(
            self.core.messageParent,
            "Metadata Not Saved",
            "The render was added to the queue, but its metadata could not "
            "be saved:\n\n%s" % error,
        )

    @err_catcher(name=__name__)
    def saveExport(self):
        """Execute export to render queue"""
        taskName, currentFile = self._validateExportInputs()
        if not taskName:
            return False

        oversion = "next" if self.chb_useNextVersion.isChecked() else self.cb_versions.currentText()
        if not oversion:
            QMessageBox.warning(self.core.messageParent, "Warning", "Invalid version")
            return False

        outputPath, outputDir, hVersion = self.exportGetOutputName(oversion)
        if not outputPath:
            self.core.popup("Could not determine the render output path.")
            return False

        # Check path length on Windows
        if platform.system() == "Windows" and len(outputPath) > 255:
            self.core.popup(
                f"The outputpath is longer than 255 characters ({len(outputPath)}), "
                "which is not supported on Windows."
            )
            return

        # Collect comp-scoped dependencies before creating anything.
        keep_going, render_dependencies = self._prepareRenderDependencies()
        if not keep_going:
            return False

        # Create output directory
        os.makedirs(outputDir, exist_ok=True)

        comp = getattr(self, "_render_comp", None)
        comp_id = comp["id"] if comp else None

        # Add to render queue in AE first; metadata only on confirmed success
        ack = self._addRenderQueueItem(
            outputPath, self.cb_formats.currentText(), comp_id
        )
        if ack is None:
            return False

        metadata_ok, metadata_error = self._writeExportMetadata(
            ack, outputPath, taskName, hVersion, currentFile, render_dependencies
        )

        if metadata_ok:
            self.core.popup(f"Render added to queue!\n\nOutput: {outputPath}")
        else:
            self._reportMetadataFailure(metadata_error)
        self.dlg_export.close()

        return True

    @err_catcher(name=__name__)
    def renderAndSave(self):
        """Save the project and add to render queue"""

        taskName, _ = self._validateExportInputs()
        if not taskName:
            return False

        # Save as new version (same as CEP Save Version button). The
        # ae_core save already shows a popup explaining any failure.
        try:
            # Render metadata only needs the versions used in the comp.
            self.main.ae_core._skip_version_scan_next = True
            try:
                saved = self.core.saveScene()
            finally:
                self.main.ae_core._skip_version_scan_next = False
        except Exception as e:
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                f"Save failed: {str(e)}\n\nRender cancelled."
            )
            return False
        if saved is False:
            return False

        # Re-read the scene path after saving: the save may create a new
        # version, and sourceScene metadata must point at the saved file.
        currentFile = self._currentPipelineFile()
        if not currentFile:
            return False

        # Then proceed with export/render setup
        oversion = "next" if self.chb_useNextVersion.isChecked() else self.cb_versions.currentText()
        if not oversion:
            QMessageBox.warning(self.core.messageParent, "Warning", "Invalid version")
            return

        outputPath, outputDir, hVersion = self.exportGetOutputName(oversion)
        if not outputPath:
            self.core.popup("Could not determine the render output path.")
            return False

        # Check path length on Windows
        if platform.system() == "Windows" and len(outputPath) > 255:
            self.core.popup(
                f"The outputpath is longer than 255 characters ({len(outputPath)}), "
                "which is not supported on Windows."
            )
            return

        # Collect comp-scoped dependencies before creating anything.
        keep_going, render_dependencies = self._prepareRenderDependencies()
        if not keep_going:
            return False

        # Create output directory
        os.makedirs(outputDir, exist_ok=True)

        comp = getattr(self, "_render_comp", None)
        comp_id = comp["id"] if comp else None

        # Add to render queue (don't auto-start - let user start from AE);
        # metadata only on confirmed success
        ack = self._addRenderQueueItem(
            outputPath, self.cb_formats.currentText(), comp_id
        )
        if ack is None:
            return False

        metadata_ok, metadata_error = self._writeExportMetadata(
            ack, outputPath, taskName, hVersion, currentFile, render_dependencies
        )

        if not metadata_ok:
            self._reportMetadataFailure(metadata_error)
        self.dlg_export.close()

        return True

    def _patchRenderVersionInfo(self, outputPath, sceneFile, render_dependencies=None):
        """Patch render versioninfo.json with scene and comp dependencies.

        The top-level arrays stay scene-wide; ``renderDependencies`` is the
        subset needed to reproduce the queued composition.  Passing ``None``
        for ``render_dependencies`` removes a stale key (failed scan that the
        user chose to continue through).  Returns ``(ok, error)``.
        """
        try:
            import json
            versioninfo_path = os.path.join(os.path.dirname(outputPath), "versioninfo.json")
            archiveinfo_path = os.path.splitext(sceneFile)[0] + "_archiveinfo.json"

            if not os.path.exists(versioninfo_path):
                return False, "versioninfo.json was not created: %s" % versioninfo_path

            with open(versioninfo_path, 'r') as f:
                vinfo = json.load(f)

            if os.path.exists(archiveinfo_path):
                with open(archiveinfo_path, 'r') as f:
                    archive = json.load(f)
                source_paths = archive.get("source_paths", {})
                if not isinstance(source_paths, dict):
                    raise ValueError("archive source_paths is not an object")

                def _normalized(values):
                    if not isinstance(values, list):
                        return []
                    return [str(p).replace("\\", "/") for p in values]

                vinfo["dependencies"] = (
                    _normalized(source_paths.get("3d_renders"))
                    + _normalized(source_paths.get("2d_renders"))
                )
                vinfo["externalFiles"] = (
                    _normalized(source_paths.get("resources"))
                    + _normalized(archive.get("external_paths"))
                )

            helixae_render_deps.apply_render_dependencies(vinfo, render_dependencies)
            helixae_render_deps.write_json_atomic(versioninfo_path, vinfo)
            return True, None

        except Exception as e:
            return False, str(e)

    @err_catcher(name=__name__)
    def getCompositionFrameRange(self):
        """Get frame range, FPS, resolution, and duration from active composition"""
        try:
            scpt = """
            if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {
                var comp = app.project.activeItem;
                var fps = comp.frameRate;
                var width = comp.width;
                var height = comp.height;
                var displayStartTime = comp.displayStartTime;
                var duration = comp.duration;
                var frameDuration = comp.frameDuration;

                // Calculate frame range
                var startFrame = Math.round(displayStartTime / frameDuration);
                var endFrame = Math.round((displayStartTime + duration) / frameDuration - 1);
                var frameRange = startFrame + "-" + endFrame;

                // Get resolution
                var resolution = width + "x" + height;

                // Return JSON string
                JSON.stringify({
                    "frameRange": frameRange,
                    "fps": fps,
                    "resolution": resolution,
                    "duration": duration,
                    "startFrame": startFrame,
                    "endFrame": endFrame
                });
            } else {
                JSON.stringify({
                    "frameRange": "",
                    "fps": "",
                    "resolution": "",
                    "duration": ""
                });
            }
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            if result:
                import json
                return json.loads(result)
            return {}
        except Exception as e:
            print(f"[HelixAE Export] Error getting composition frame range: {e}")
            return {}
