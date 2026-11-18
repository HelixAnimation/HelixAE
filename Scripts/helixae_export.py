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

import helixae_deadline
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

        # Local output
        self.chb_localOutput = QCheckBox("Local output")
        if not self.core.useLocalFiles:
            self.chb_localOutput.setVisible(False)

        lo_prismExport.addLayout(lo_task)
        lo_prismExport.addWidget(self.w_comment)
        lo_prismExport.addLayout(lo_version)
        self.setupOutputPresetUI(lo_prismExport)
        lo_prismExport.addWidget(self.chb_localOutput)

        self.setupDeadlineUI(lo_prismExport)

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

    _FORMAT_EXTENSIONS = {
        "OpenEXR Sequence": ".exr", "PNG Sequence": ".png", "QuickTime": ".mov",
        "H.264": ".mp4", "AVI": ".avi", "AVI (Uncompressed)": ".avi",
        "JPEG Sequence": ".jpg", "TIFF Sequence": ".tif",
        "Photoshop Sequence": ".psd", "Photoshop": ".psd",
        "DPX/Cineon Sequence": ".dpx", "DPX Sequence": ".dpx",
        "Cineon Sequence": ".cin", "Targa Sequence": ".tga",
        "SGI Sequence": ".sgi", "Radiance Sequence": ".hdr",
        "AIFF": ".aif", "WAV": ".wav",
    }

    def setupOutputPresetUI(self, parentLayout):
        self._outputSelection = None
        self._outputTemplates = self.getOutputModules()
        self.cb_formats = QComboBox()
        self._outputError = ""
        grid = QGridLayout()
        grid.addWidget(QLabel("Output Template:"), 0, 0)
        grid.addWidget(self.cb_formats, 0, 1)
        parentLayout.addLayout(grid)
        self.cb_formats.currentIndexChanged.connect(self._inspectOutputSelection)
        self._populateOutputPresets()

    def _populateOutputPresets(self, *args):
        self.cb_formats.blockSignals(True)
        self.cb_formats.clear()
        for name in self._outputTemplates:
            self.cb_formats.addItem(name, name)
        saved = self.core.getConfig("helixae", "outputUserTemplate", dft="", config="user")
        index = self.cb_formats.findData(saved)
        self.cb_formats.setCurrentIndex(index if index >= 0 else (0 if self.cb_formats.count() else -1))
        self.cb_formats.blockSignals(False)
        self._inspectOutputSelection()

    def _extensionForSettings(self, settings):
        """Use AE's actual format, not a template-name guess or an AVI fallback."""
        if not isinstance(settings, dict):
            raise ValueError("After Effects returned no output-module settings")
        fmt = settings.get("Format")
        if fmt not in self._FORMAT_EXTENSIONS:
            raise ValueError("Unsupported output format %r; add an explicit extension mapping." % fmt)
        return self._FORMAT_EXTENSIONS[fmt]

    def _inspectOutputSelection(self, *args):
        self._outputSelection = None
        self._outputError = ""
        template = self.cb_formats.currentData()
        if not template:
            self._outputError = "No output templates available. Connect to AE and reopen the dialog."
            return
        try:
            response = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_inspect_output_template(self._render_comp["id"], template))
            data, error = helixae_protocol.parse_json_response(response)
            if error or not data.get("result"):
                raise ValueError(error or data.get("details", "Template inspection failed"))
            settings = data.get("settings")
            extension = self._extensionForSettings(settings)
            expected = {key: [settings[key]] for key in ("Format", "Depth", "Channels")
                        if isinstance(settings.get(key), str) and settings[key]}
            self._outputSelection = {
                "template": template, "extension": extension, "expected": expected,
            }
            self.exportGetVersions()
        except Exception as e:
            self._outputSelection = None
            self._outputError = "Cannot use '%s': %s" % (template, e)

    def _rememberOutputSettings(self):
        self.core.setConfig("helixae", "outputUserTemplate",
                            val=self._outputSelection["template"], config="user")

    def setupDeadlineUI(self, parentLayout):
        """Build the optional "Submit to Deadline" group.

        Hidden entirely when the Deadline plugin isn't installed. Groups and
        the worker list are loaded lazily (first time the group is checked)
        so opening the export dialog never blocks on ``deadlinecommand``.
        Pools are not offered for now; jobs go to pool "none".
        """
        self.dl_plugin = self.core.getPlugin("Deadline")
        self._dlPoolsLoaded = False

        self.gb_deadline = QGroupBox("Submit to Deadline")
        self.gb_deadline.setCheckable(True)
        self.gb_deadline.setChecked(False)
        lo_deadline = QGridLayout()
        self.gb_deadline.setLayout(lo_deadline)

        self.cb_dlGroup = QComboBox()
        self._dlWorkerNames = []
        self._dlThisPc = os.environ.get("COMPUTERNAME") or platform.node()

        self.cb_dlWorkerMode = QComboBox()
        self.cb_dlWorkerMode.addItem("All workers", helixae_deadline.WORKER_MODE_ALL)
        self.cb_dlWorkerMode.addItem(
            "Only this PC (%s)" % self._dlThisPc, helixae_deadline.WORKER_MODE_THIS_PC
        )
        self.cb_dlWorkerMode.addItem(
            "Whitelist (only checked workers)", helixae_deadline.WORKER_MODE_WHITELIST
        )
        self.cb_dlWorkerMode.addItem(
            "Blacklist (all except checked)", helixae_deadline.WORKER_MODE_BLACKLIST
        )
        self.cb_dlWorkerMode.setToolTip(
            "Which Deadline workers may render the job. Workers must also be "
            "in the selected Group."
        )
        self.lw_dlWorkers = QListWidget()
        self.lw_dlWorkers.setMaximumHeight(120)
        self.b_dlRefreshWorkers = QPushButton("Refresh workers")
        self.b_dlRefreshWorkers.clicked.connect(self._refreshDeadlineWorkers)

        self.sp_dlPriority = QSpinBox()
        self.sp_dlPriority.setRange(0, 100)
        self.sp_dlPriority.setValue(50)

        self.sp_dlFramesPerTask = QSpinBox()
        self.sp_dlFramesPerTask.setRange(1, 100000)
        self.sp_dlFramesPerTask.setValue(10)

        self.sp_dlConcurrentTasks = QSpinBox()
        self.sp_dlConcurrentTasks.setRange(1, 16)
        self.sp_dlConcurrentTasks.setValue(6)
        self.sp_dlConcurrentTasks.setToolTip(
            "Each concurrent task is a separate aerender process on the "
            "same worker (uses more RAM per task). Only useful for image "
            "sequences - movie outputs always render as a single task.\n"
            "The worker's \"Concurrent Task Limit Override\" can cap this."
        )

        self.chb_dlLimitToCpus = QCheckBox("Limit to CPU count")
        self.chb_dlLimitToCpus.setChecked(True)
        self.chb_dlSuspended = QCheckBox("Submit suspended")

        lo_deadline.addWidget(QLabel("Group:"), 0, 0)
        lo_deadline.addWidget(self.cb_dlGroup, 0, 1)
        lo_deadline.addWidget(QLabel("Workers:"), 1, 0)
        lo_deadline.addWidget(self.cb_dlWorkerMode, 1, 1)
        lo_deadline.addWidget(self.lw_dlWorkers, 2, 1)
        lo_deadline.addWidget(self.b_dlRefreshWorkers, 3, 1)
        lo_deadline.addWidget(QLabel("Priority:"), 4, 0)
        lo_deadline.addWidget(self.sp_dlPriority, 4, 1)
        lo_deadline.addWidget(QLabel("Frames per Task:"), 5, 0)
        lo_deadline.addWidget(self.sp_dlFramesPerTask, 5, 1)
        lo_deadline.addWidget(QLabel("Concurrent Tasks:"), 6, 0)
        lo_deadline.addWidget(self.sp_dlConcurrentTasks, 6, 1)
        lo_deadline.addWidget(self.chb_dlLimitToCpus, 7, 0, 1, 2)
        lo_deadline.addWidget(self.chb_dlSuspended, 8, 0, 1, 2)

        parentLayout.addWidget(self.gb_deadline)

        if self.dl_plugin is None:
            self.gb_deadline.setVisible(False)
            return

        self._restoreDeadlineSettings()
        self.cb_dlWorkerMode.currentIndexChanged.connect(self._updateDeadlineWorkerUi)
        self._updateDeadlineWorkerUi()
        self.gb_deadline.toggled.connect(self._onDeadlineToggled)
        if self.gb_deadline.isChecked():
            self._loadDeadlinePoolsGroups()

    def _restoreDeadlineSettings(self):
        """Load the last-used Deadline submission settings (per Prism user)."""
        getCfg = lambda key, dft: self.core.getConfig(
            "helixae", key, dft=dft, config="user"
        )
        self.gb_deadline.setChecked(bool(getCfg("deadlineSubmit", False)))
        self.sp_dlPriority.setValue(int(getCfg("deadlinePriority", 50)))
        self.sp_dlFramesPerTask.setValue(int(getCfg("deadlineFramesPerTask", 10)))
        self.sp_dlConcurrentTasks.setValue(int(getCfg("deadlineConcurrentTasks", 6)))
        self.chb_dlLimitToCpus.setChecked(bool(getCfg("deadlineLimitToCpus", True)))
        self.chb_dlSuspended.setChecked(bool(getCfg("deadlineSuspended", False)))
        modeIdx = self.cb_dlWorkerMode.findData(
            getCfg("deadlineWorkerMode", helixae_deadline.WORKER_MODE_ALL)
        )
        self.cb_dlWorkerMode.setCurrentIndex(max(0, modeIdx))
        # Group combo and checked workers are restored once their items are
        # populated in _loadDeadlinePoolsGroups.

    def _rememberDeadlineSettings(self):
        setCfg = lambda key, val: self.core.setConfig(
            "helixae", key, val=val, config="user"
        )
        setCfg("deadlineSubmit", self.gb_deadline.isChecked())
        setCfg("deadlineGroup", self.cb_dlGroup.currentText())
        setCfg("deadlineWorkerMode", self.cb_dlWorkerMode.currentData())
        if self._dlPoolsLoaded:
            setCfg("deadlineWorkers", self._checkedDeadlineWorkers())
        setCfg("deadlinePriority", self.sp_dlPriority.value())
        setCfg("deadlineFramesPerTask", self.sp_dlFramesPerTask.value())
        setCfg("deadlineConcurrentTasks", self.sp_dlConcurrentTasks.value())
        setCfg("deadlineLimitToCpus", self.chb_dlLimitToCpus.isChecked())
        setCfg("deadlineSuspended", self.chb_dlSuspended.isChecked())

    @err_catcher(name=__name__)
    def _onDeadlineToggled(self, checked):
        if checked:
            self._loadDeadlinePoolsGroups()

    @err_catcher(name=__name__)
    def _loadDeadlinePoolsGroups(self):
        """Load groups and the worker list (once, on first use)."""
        if self._dlPoolsLoaded or self.dl_plugin is None:
            return
        try:
            groups = self.dl_plugin.getDeadlineGroups() or []
        except Exception as e:
            self.core.popup("Could not read Deadline groups:\n%s" % e)
            groups = []

        lastGroup = self.core.getConfig("helixae", "deadlineGroup", dft="", config="user")
        self.cb_dlGroup.clear()
        self.cb_dlGroup.addItems(groups or ["none"])
        if lastGroup and self.cb_dlGroup.findText(lastGroup) >= 0:
            self.cb_dlGroup.setCurrentText(lastGroup)

        lastWorkers = self.core.getConfig(
            "helixae", "deadlineWorkers", dft=[], config="user"
        ) or []
        self._populateDeadlineWorkers(self._queryDeadlineWorkers(), lastWorkers)
        self._dlPoolsLoaded = True

    def _queryDeadlineWorkers(self):
        try:
            output = self.dl_plugin.CallDeadlineCommand(["-GetSlaveNames"], silent=True)
        except Exception:
            output = None
        return helixae_deadline.parse_worker_names(output)

    def _populateDeadlineWorkers(self, names, checkedNames):
        checked = set(str(n).lower() for n in checkedNames or [])
        self._dlWorkerNames = list(names)
        self.lw_dlWorkers.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name.lower() in checked else Qt.Unchecked)
            self.lw_dlWorkers.addItem(item)

    @err_catcher(name=__name__)
    def _refreshDeadlineWorkers(self):
        if self.dl_plugin is None:
            return
        checked = self._checkedDeadlineWorkers()
        names = self._queryDeadlineWorkers()
        if not names:
            self.core.popup("Could not read the Deadline worker list.")
            return
        self._populateDeadlineWorkers(names, checked)

    def _checkedDeadlineWorkers(self):
        result = []
        for i in range(self.lw_dlWorkers.count()):
            item = self.lw_dlWorkers.item(i)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result

    def _updateDeadlineWorkerUi(self, *args):
        mode = self.cb_dlWorkerMode.currentData()
        showList = mode in (
            helixae_deadline.WORKER_MODE_WHITELIST,
            helixae_deadline.WORKER_MODE_BLACKLIST,
        )
        self.lw_dlWorkers.setVisible(showList)
        self.b_dlRefreshWorkers.setVisible(showList)

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
            print(f"[HelixAE Export] Could not read output modules: {e}")
            return []  # Never invent templates after a failed AE query.

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
        selection = getattr(self, "_outputSelection", None)
        if not selection:
            return None
        extension = selection["extension"]
        
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
        if not getattr(self, "_outputSelection", None):
            self.core.popup("Choose an available output template.\n" + getattr(self, "_outputError", ""))
            return None, None
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
                    outputPath, selectedOutputModule, comp_id,
                    expected_settings=(getattr(self, "_outputSelection", None) or {}).get("expected")
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
        try:
            self._rememberOutputSettings()
        except Exception as e:
            # Queueing already succeeded; a preference-write error must not
            # turn that into a reported render failure or duplicate queue item.
            print("[HelixAE Export] Could not remember output selection: %s" % e)
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
        if getattr(self, "_outputSelection", None):
            details["outputPreset"] = dict(
                self._outputSelection,
                actualTemplate=ack.get("outputTemplate"),
                actualSettings={key: (ack.get("outputSettings") or {}).get(key)
                                for key in ("Format", "Depth", "Channels", "Output Audio",
                                            "Audio Sample Rate", "Audio Channels")},
            )

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

        output_data = self.exportGetOutputName(oversion)
        if not output_data:
            self.core.popup("Could not determine the render output path.")
            return False
        outputPath, outputDir, hVersion = output_data
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
            outputPath, self._outputSelection["template"], comp_id
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

    def _removeRenderQueueItem(self, ack, comp_id, outputPath):
        """Best-effort rollback of a queue item added before a failed save.

        Identifies the item by the (index, comp, output path) recorded in
        ``ack`` (see build_remove_render_queue_item; RenderQueueItem has
        no stable ``.id`` to key off) so a queue mutated in the meantime
        is never removed by mistake. Reports to the user instead of
        silently leaving a stale item when that happens.
        """
        try:
            script = helixae_protocol.build_remove_render_queue_item(
                ack.get("queueItemIndex"), comp_id, ack.get("outputFile") or outputPath
            )
            result = self.main.ae_core.executeAppleScript(script)
            data, error = helixae_protocol.parse_json_response(result)
        except Exception as e:
            data, error = None, str(e)

        if error or not data.get("result"):
            self.core.popup(
                "The scene save failed, and the render queue item that was "
                "added for it could not be removed automatically "
                "(%s).\n\nPlease remove it manually in After Effects."
                % (error or data.get("details", data.get("reason", "unknown reason")))
            )

    def _resolveDeadlineQueueConflicts(self, comp):
        """Unqueue other QUEUED render-queue items for ``comp``.

        Must run before a new queue item for ``comp`` is added and the
        scene is saved: Deadline's AfterEffects plugin runs ``aerender
        -comp`` on the farm, which renders the composition's *first
        currently-queued* render-queue item in the saved project using
        that item's own output module. After a Deadline submission the
        local item stays QUEUED, so without this a second submission of
        the same comp (e.g. the next version) would have its farm job
        silently re-render the stale item instead of the new one.

        The stale items are unqueued (``render = false``) without asking;
        they stay in the Render Queue and can be re-checked in After
        Effects later.

        Returns the unqueued items as ``{"index", "outputPath"}`` dicts
        (an empty list when there was nothing to unqueue) so the caller
        can report them, or ``None`` to abort (the queue could not be
        checked, or the conflicting items could not be unqueued).
        """
        try:
            script = helixae_protocol.build_find_other_queued_render_items(comp["id"])
            result = self.main.ae_core.executeAppleScript(script)
            data, error = helixae_protocol.parse_json_response(result)
        except Exception as e:
            data, error = None, str(e)

        if error:
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                "Could not check the render queue for conflicting items:\n%s" % error,
            )
            return None

        conflicts = data.get("conflicts") or []
        if not conflicts:
            return []

        try:
            targets = [
                {
                    "index": c.get("index"),
                    "compId": c.get("compId"),
                    "outputPath": c.get("outputPath"),
                }
                for c in conflicts
            ]
            unqueueScript = helixae_protocol.build_unqueue_render_items(targets)
            result = self.main.ae_core.executeAppleScript(unqueueScript)
            data, error = helixae_protocol.parse_json_response(result)
        except Exception as e:
            data, error = None, str(e)

        if error or not data.get("result"):
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                "Could not unqueue the conflicting render queue item(s):\n%s"
                % (error or data.get("details", "unknown reason")),
            )
            return None
        return [
            {"index": c.get("index"), "outputPath": c.get("outputPath")}
            for c in conflicts
        ]

    @err_catcher(name=__name__)
    def renderAndSave(self):
        """Add to render queue, then save the project so the .aep contains it.

        The queue item is created first so the save that follows persists
        it; if that save fails, the queue item is removed again instead of
        leaving a stray item the scene on disk doesn't know about.
        """

        taskName, _ = self._validateExportInputs()
        if not taskName:
            return False

        oversion = "next" if self.chb_useNextVersion.isChecked() else self.cb_versions.currentText()
        if not oversion:
            QMessageBox.warning(self.core.messageParent, "Warning", "Invalid version")
            return False

        # Output path resolution is independent of the scene's saved
        # version: it comes from mediaProducts.generateMediaProductPath for
        # the chosen task/version, not from the current .aep's version.
        output_data = self.exportGetOutputName(oversion)
        if not output_data:
            self.core.popup("Could not determine the render output path.")
            return False
        outputPath, outputDir, hVersion = output_data
        if not outputPath:
            self.core.popup("Could not determine the render output path.")
            return False

        # Check path length on Windows
        if platform.system() == "Windows" and len(outputPath) > 255:
            self.core.popup(
                f"The outputpath is longer than 255 characters ({len(outputPath)}), "
                "which is not supported on Windows."
            )
            return False

        # Collect comp-scoped dependencies before creating anything.
        keep_going, render_dependencies = self._prepareRenderDependencies()
        if not keep_going:
            return False

        # Create output directory
        os.makedirs(outputDir, exist_ok=True)

        comp = getattr(self, "_render_comp", None)
        comp_id = comp["id"] if comp else None

        # Deadline's aerender -comp renders a comp's first *currently
        # queued* item from the saved project; a stale item from an
        # earlier submission (its local queue item stays QUEUED after
        # submit) must be unqueued before this one is added and saved,
        # not only before submitting. The unqueued items are reported in
        # the Deadline submission feedback below.
        uncheckedConflicts = []
        if self.dl_plugin is not None and self.gb_deadline.isChecked() and comp is not None:
            uncheckedConflicts = self._resolveDeadlineQueueConflicts(comp)
            if uncheckedConflicts is None:
                return False

        # Add to render queue first so the save below persists it.
        ack = self._addRenderQueueItem(
            outputPath, self._outputSelection["template"], comp_id
        )
        if ack is None:
            return False

        # Save as new version (same as CEP Save Version button) so the
        # saved .aep contains the queue item just added. The ae_core save
        # already shows a popup explaining any failure.
        try:
            # Render metadata only needs the versions used in the comp.
            self.main.ae_core._skip_version_scan_next = True
            try:
                saved = self.core.saveScene()
            finally:
                self.main.ae_core._skip_version_scan_next = False
        except Exception as e:
            self._removeRenderQueueItem(ack, comp_id, outputPath)
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                f"Save failed: {str(e)}\n\nRender cancelled."
            )
            return False
        if saved is False:
            self._removeRenderQueueItem(ack, comp_id, outputPath)
            return False

        # Re-read the scene path after saving: the save may create a new
        # version, and sourceScene metadata must point at the saved file.
        currentFile = self._currentPipelineFile()
        if not currentFile:
            self._removeRenderQueueItem(ack, comp_id, outputPath)
            return False

        metadata_ok, metadata_error = self._writeExportMetadata(
            ack, outputPath, taskName, hVersion, currentFile, render_dependencies
        )

        if not metadata_ok:
            self._reportMetadataFailure(metadata_error)

        if self.dl_plugin is not None:
            self._rememberDeadlineSettings()
            if self.gb_deadline.isChecked():
                # Unused for now; a future dependent job (e.g. an ffmpeg
                # encode submitted with JobDependencies=<renderJobId>)
                # chains onto this.
                renderJobId = self._submitToDeadline(
                    ack,
                    outputPath,
                    currentFile,
                    comp,
                    taskName,
                    hVersion,
                    unchecked_conflicts=uncheckedConflicts,
                )

        self.dlg_export.close()

        return True

    @err_catcher(name=__name__)
    def _submitToDeadline(
        self,
        ack,
        outputPath,
        sceneFile,
        comp,
        taskName,
        hVersion,
        unchecked_conflicts=None,
    ):
        """Submit the just-saved, queued comp as a Deadline AfterEffects job.

        Runs after the local render-queue item and metadata are already
        confirmed; nothing here ever removes either of those, even on
        failure, so the artist always keeps a working local render path.

        ``unchecked_conflicts`` is the list ``_resolveDeadlineQueueConflicts``
        returned for this comp (or ``None``): those older queue items were
        unqueued so the farm picks up this one, and every popup below says
        so.

        Returns the submitted job id, or ``None`` on any failure/skip.
        Kept as a return value (rather than only a popup) so a follow-up
        dependent job - e.g. an ffmpeg encode submitted afterwards with
        ``JobDependencies=<this job id>`` - can be chained onto it later.
        """
        dl = self.dl_plugin

        # Older queued items for this comp were unqueued before this one
        # was added (see _resolveDeadlineQueueConflicts); mention them in
        # every popup so the artist knows the Render Queue changed.
        uncheckedNote = ""
        if unchecked_conflicts:
            uncheckedLines = "\n".join(
                "- #%s: %s"
                % (
                    item.get("index"),
                    os.path.basename(
                        str(item.get("outputPath") or "").replace("\\", "/")
                    )
                    or "(no output)",
                )
                for item in unchecked_conflicts
            )
            uncheckedNote = (
                "\n\nUnchecked %d older queued item(s) for this comp so the "
                "farm renders this one:\n%s"
                % (len(unchecked_conflicts), uncheckedLines)
            )

        def _warn(title, message):
            QMessageBox.warning(self.core.messageParent, title, message + uncheckedNote)

        # Cheap sanity check only: renderAndSave() already resolved any
        # same-comp conflict (by unqueueing stale items) before this item
        # was even added. A conflict here means something re-queued the
        # comp in between; abort rather than guess which item aerender
        # would pick up on the farm.
        try:
            conflictScript = helixae_protocol.build_find_other_queued_render_items(
                comp["id"],
                exclude_index=ack.get("queueItemIndex"),
                exclude_output_path=ack.get("outputFile") or outputPath,
            )
            result = self.main.ae_core.executeAppleScript(conflictScript)
            data, error = helixae_protocol.parse_json_response(result)
        except Exception as e:
            data, error = None, str(e)

        if error:
            _warn(
                "Deadline Submission Skipped",
                "Could not verify the render queue before submitting:\n%s\n\n"
                "The render was added to the queue locally, but was not "
                "submitted to Deadline." % error,
            )
            return None
        if data.get("hasConflict"):
            _warn(
                "Deadline Submission Skipped",
                "Composition '%s' has another queued render-queue item "
                "again. The render was added to the local queue, but was "
                "not submitted to Deadline." % comp["name"],
            )
            return None

        try:
            versionResult = self.main.ae_core.executeAppleScript(
                helixae_protocol.build_get_app_version()
            )
            versionData, versionError = helixae_protocol.parse_json_response(versionResult)
            if versionError or not versionData.get("result"):
                raise Exception(versionError or versionData.get("details", "unknown error"))
            appVersion = str(versionData.get("version") or "")
            majorVersion = helixae_deadline.ae_major_version(appVersion)
        except Exception as e:
            _warn(
                "Deadline Submission Skipped",
                "Could not determine the After Effects version:\n%s" % e,
            )
            return None

        homeDir = dl.CallDeadlineCommand(["-GetCurrentUserHomeDirectory"])
        if homeDir is False or not homeDir:
            _warn(
                "Deadline Submission Skipped",
                "Could not reach Deadline (deadlinecommand -GetCurrentUserHomeDirectory failed).",
            )
            return None
        homeDir = homeDir.replace("\r", "").replace("\n", "")

        submitScenes = self.core.getConfig(
            "deadline", "submitScenes", dft=True, config="project"
        )

        # Mirrors _writeExportMetadata's details construction so the
        # project's deadlineJobName template sees the same context fields.
        fnameData = self.core.getScenefileData(sceneFile)
        jobNameDetails = fnameData.copy()
        if "filename" in jobNameDetails:
            del jobNameDetails["filename"]
        if "extension" in jobNameDetails:
            del jobNameDetails["extension"]
        jobNameDetails["identifier"] = taskName
        jobNameDetails["version"] = hVersion

        jobName = dl.getJobName(
            details=jobNameDetails, origin=None, quiet=True
        ) or "%s - %s" % (os.path.splitext(os.path.basename(sceneFile))[0], comp["name"])

        startFrame = ack.get("startFrame")
        endFrame = ack.get("endFrame")
        # ack["outputFile"] is the fsName After Effects actually assigned to
        # the output module, which includes any sequence padding ([#####])
        # AE auto-inserts; outputPath (no padding token) is only a fallback
        # for older acks that didn't carry it.
        deadlineOutputPath = ack.get("outputFile") or outputPath

        try:
            workerMode = self.cb_dlWorkerMode.currentData()
            thisPcWorker = None
            if workerMode == helixae_deadline.WORKER_MODE_THIS_PC:
                thisPcWorker = helixae_deadline.resolve_this_pc_worker(
                    self._dlThisPc, self._dlWorkerNames
                )
                if thisPcWorker is None:
                    raise ValueError(
                        "This PC (%s) is not a Deadline worker, so an "
                        "\"Only this PC\" job would never render." % self._dlThisPc
                    )
            workerFilter = helixae_deadline.resolve_worker_filter(
                workerMode, self._checkedDeadlineWorkers(), thisPcWorker
            )
            chunkSize = helixae_deadline.resolve_chunk_size(
                deadlineOutputPath, self.sp_dlFramesPerTask.value(), startFrame, endFrame
            )
            concurrentTasks = helixae_deadline.resolve_concurrent_tasks(
                deadlineOutputPath, self.sp_dlConcurrentTasks.value()
            )
            jobInfos = helixae_deadline.build_job_infos(
                name=jobName,
                comment=self.le_comment.text(),
                pool="none",
                secondary_pool="",
                group=self.cb_dlGroup.currentText(),
                priority=self.sp_dlPriority.value(),
                start_frame=startFrame,
                end_frame=endFrame,
                chunk_size=chunkSize,
                output_path=deadlineOutputPath,
                prism_project=self.core.prismIni.replace("\\", "/"),
                prism_source_scene=sceneFile,
                concurrent_tasks=concurrentTasks,
                limit_concurrent_tasks_to_cpus=self.chb_dlLimitToCpus.isChecked(),
                suspended=self.chb_dlSuspended.isChecked(),
                worker_filter=workerFilter,
            )
            pluginInfos = helixae_deadline.build_plugin_infos(
                comp_name=comp["name"],
                output_path=deadlineOutputPath,
                major_version=majorVersion,
                app_version_str=appVersion,
                scene_file=None if submitScenes else sceneFile,
            )
        except Exception as e:
            _warn(
                "Deadline Submission Skipped",
                "Could not build the Deadline job:\n%s" % e,
            )
            return None

        jobInfoFile = helixae_deadline.job_info_file_path(homeDir)
        pluginInfoFile = helixae_deadline.plugin_info_file_path(homeDir)
        os.makedirs(os.path.dirname(jobInfoFile), exist_ok=True)

        arguments = [jobInfoFile, pluginInfoFile]
        if submitScenes:
            arguments.append(sceneFile)

        result = dl.deadlineSubmitJob(jobInfos, pluginInfos, arguments)
        jobId = helixae_deadline.parse_job_id(result)

        if jobId:
            self.core.popup(
                "Submitted to Deadline.\n\nJob ID: %s%s" % (jobId, uncheckedNote)
            )
        else:
            _warn(
                "Deadline Submission Failed",
                "The render queue item and metadata were saved locally, "
                "but the Deadline submission failed:\n\n%s" % result,
            )

        return jobId

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
