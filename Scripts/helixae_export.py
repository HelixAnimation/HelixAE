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

from PrismUtils.Decorators import err_catcher as err_catcher


class HelixAE_Export:
    def __init__(self, main):
        self.main = main
        self.core = main.core

    @err_catcher(name=__name__)
    def exportImage(self):
        """Show export dialog for rendering from AE"""
        if not self.core.projects.ensureProject() or not self.core.users.ensureUser():
            return False

        curfile = self.core.getCurrentFileName()
        fname = self.core.getScenefileData(curfile)
        entityType = "context" if fname["filename"] == "invalid" else fname["filename"]

        self.dlg_export = QDialog()
        self.core.parentWindow(self.dlg_export)
        self.dlg_export.setWindowTitle("Helix AE - Export")

        self.setupExportUI(entityType)
        self.exportGetTasks()
        self.dlg_export.show()
        return True

    def setupExportUI(self, entityType):
        """Build export dialog UI"""
        lo_export = QVBoxLayout()
        self.dlg_export.setLayout(lo_export)

        self.rb_task = QRadioButton(f"Export into current {entityType}")
        self.rb_task.setChecked(True)  # Always checked by default
        self.w_task = QWidget()
        lo_prismExport = QVBoxLayout()
        self.w_task.setLayout(lo_prismExport)

        # Task selection
        lo_task = QHBoxLayout()
        self.le_task = QLineEdit()
        self.b_task = QPushButton("▼")
        self.b_task.setMaximumSize(35, 500)
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
        self.b_export = QPushButton("Render")

        button_layout.addWidget(self.b_render)
        button_layout.addWidget(self.b_export)

        lo_export.addWidget(self.rb_task)
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
        self.b_export.clicked.connect(self.saveExport)
        self.b_render.clicked.connect(self.renderAndSave)

    def getOutputModules(self):
        """Query After Effects for available output module templates"""
        try:
            scpt = """
            var renderQueue = app.project.renderQueue;
            var templates = [];
            
            // Check if render queue has items
            if (renderQueue.numItems > 0) {
                templates = renderQueue.item(1).outputModule(1).templates;
            } else {
                // If queue is empty, temporarily add active comp to get templates
                if (app.project.activeItem && app.project.activeItem instanceof CompItem) {
                    var tempItem = renderQueue.items.add(app.project.activeItem);
                    templates = tempItem.outputModule(1).templates;
                    tempItem.remove();  // Remove the temporary item
                }
            }
            
            var templateList = [];
            for (var i = 0; i < templates.length; i++) {
                templateList.push(templates[i]);
            }
            templateList.join('|||');
            """
            result = self.main.ae_core.executeAppleScript(scpt)
            modules = str(result).replace("b'", "").replace("'", "").split('|||')
            return [x.strip() for x in modules if x.strip() and "_HIDDEN" not in x.upper()]
        except Exception as e:
            # Fallback to common output modules if script fails
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

    @err_catcher(name=__name__)
    def saveExport(self):
        """Execute export to render queue"""
        if not self.rb_task.isChecked():
            return
        
        taskName = self.le_task.text()
        if not taskName:
            QMessageBox.warning(
                self.core.messageParent, 
                "Warning", 
                "Please choose a taskname"
            )
            return

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
            return False

        oversion = "next" if self.chb_useNextVersion.isChecked() else self.cb_versions.currentText()
        if not oversion:
            QMessageBox.warning(self.core.messageParent, "Warning", "Invalid version")
            return

        outputPath, outputDir, hVersion = self.exportGetOutputName(oversion)
        
        # Check path length on Windows
        if platform.system() == "Windows" and len(outputPath) > 255:
            self.core.popup(
                f"The outputpath is longer than 255 characters ({len(outputPath)}), "
                "which is not supported on Windows."
            )
            return

        # Create output directory
        os.makedirs(outputDir, exist_ok=True)

        # Add to render queue in AE first
        selectedOutputModule = self.cb_formats.currentText()
        scpt = f"""
        var resultFile = new File('{outputPath.replace(chr(92), "//")}');
        var renderQueue = app.project.renderQueue;
        app.activeViewer.setActive();
        var sel = app.project.activeItem;
        var render = renderQueue.items.add(sel);
        render.outputModules[1].applyTemplate('{selectedOutputModule}');
        render.outputModules[1].file = resultFile;

        // Get frame range - check if work area is set, otherwise use full comp
        var comp = sel;
        var fps = comp.frameRate;
        var frameDuration = comp.frameDuration;

        // Get display start frame (offset for frame numbering)
        var displayStartFrame = Math.round(comp.displayStartTime / frameDuration);

        // Try to get from render item settings first
        var startTime = render.startTime;
        var duration = render.timeSpan;

        // If duration is invalid, use composition work area or full duration
        if (duration <= 0 || isNaN(duration)) {{
            // Check if work area is set (smaller than comp duration)
            if (comp.workAreaDuration < comp.duration && comp.workAreaDuration > 0) {{
                startTime = comp.workAreaStart;
                duration = comp.workAreaDuration;
            }} else {{
                startTime = comp.displayStartTime;
                duration = comp.duration;
            }}
        }}

        var startFrame = Math.round(startTime / frameDuration) + displayStartFrame;
        var endFrame = Math.round((startTime + duration) / frameDuration - 1) + displayStartFrame;

        startFrame + "||" + endFrame + "||" + fps;
        """
        frameRangeResult = self.main.ae_core.executeAppleScript(scpt)

        # Get full entity data from current scene file
        fileName = self.core.getCurrentFileName()
        fnameData = self.core.getScenefileData(fileName)

        # Build full details like old Prism AE
        details = fnameData.copy()
        if "filename" in details:
            del details["filename"]
        if "extension" in details:
            del details["extension"]

        details["version"] = hVersion
        details["sourceScene"] = fileName
        details["identifier"] = taskName
        details["comment"] = self.le_comment.text()

        # Add frame range data from render queue
        if frameRangeResult:
            try:
                resultStr = str(frameRangeResult).replace("b'", "").replace("'", "")
                parts = resultStr.split("||")
                if len(parts) == 3:
                    details["startframe"] = int(parts[0])
                    details["endframe"] = int(parts[1])
                    details["fps"] = float(parts[2])
            except Exception as e:
                print(f"[HelixAE Export] Error parsing frame range: {e}")

        self.core.saveVersionInfo(
            filepath=os.path.dirname(outputPath),
            details=details
        )

        self.core.popup(f"Render added to queue!\n\nOutput: {outputPath}")
        self.dlg_export.close()

        return True

    @err_catcher(name=__name__)
    def renderAndSave(self):
        """Save the project and add to render queue, then start rendering"""
        if not self.rb_task.isChecked():
            return

        taskName = self.le_task.text()
        if not taskName:
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                "Please choose a taskname"
            )
            return

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
            return False

        # First, save the current project (with archive info)
        try:
            currentFile = self.core.getCurrentFileName()
            if not currentFile:
                QMessageBox.warning(
                    self.core.messageParent,
                    "Warning",
                    "No file is currently open. Please save or create a file first."
                )
                return False

            # Use ae_core.saveScene which includes archive info generation
            saveResult = self.main.ae_core.saveScene(origin="renderAndSave", filepath=currentFile)
            if not saveResult:
                QMessageBox.warning(
                    self.core.messageParent,
                    "Warning",
                    "Save failed. Render cancelled."
                )
                return False
        except Exception as e:
            QMessageBox.warning(
                self.core.messageParent,
                "Warning",
                f"Save failed: {str(e)}\n\nRender cancelled."
            )
            return False

        # Then proceed with export/render setup
        oversion = "next" if self.chb_useNextVersion.isChecked() else self.cb_versions.currentText()
        if not oversion:
            QMessageBox.warning(self.core.messageParent, "Warning", "Invalid version")
            return

        outputPath, outputDir, hVersion = self.exportGetOutputName(oversion)

        # Check path length on Windows
        if platform.system() == "Windows" and len(outputPath) > 255:
            self.core.popup(
                f"The outputpath is longer than 255 characters ({len(outputPath)}), "
                "which is not supported on Windows."
            )
            return

        # Create output directory
        os.makedirs(outputDir, exist_ok=True)

        # Add to render queue (don't auto-start - let user start from AE)
        selectedOutputModule = self.cb_formats.currentText()
        scpt = f"""
        var resultFile = new File('{outputPath.replace(chr(92), "//")}');
        var renderQueue = app.project.renderQueue;
        app.activeViewer.setActive();
        var sel = app.project.activeItem;
        var render = renderQueue.items.add(sel);
        render.outputModules[1].applyTemplate('{selectedOutputModule}');
        render.outputModules[1].file = resultFile;

        // Get frame range from render queue item (respects custom start/end)
        var comp = sel;
        var fps = comp.frameRate;
        var renderStartTime = render.startTime;
        var renderDuration = render.timeSpan;
        var frameDuration = comp.frameDuration;

        // Calculate actual render frame range
        var startFrame = Math.round(renderStartTime / frameDuration);
        var endFrame = Math.round((renderStartTime + renderDuration) / frameDuration - 1);

        JSON.stringify({{
            "startFrame": startFrame,
            "endFrame": endFrame,
            "fps": fps
        }});
        """
        frameRangeResult = self.main.ae_core.executeAppleScript(scpt)

        # Get full entity data from current scene file
        fileName = self.core.getCurrentFileName()
        fnameData = self.core.getScenefileData(fileName)

        # Build full details like old Prism AE
        details = fnameData.copy()
        if "filename" in details:
            del details["filename"]
        if "extension" in details:
            del details["extension"]

        details["version"] = hVersion
        details["sourceScene"] = fileName
        details["identifier"] = taskName
        details["comment"] = self.le_comment.text()

        # Add frame range data from render queue
        if frameRangeResult:
            import json
            try:
                frameRangeData = json.loads(frameRangeResult)
                if frameRangeData.get("startFrame") is not None:
                    details["startframe"] = frameRangeData["startFrame"]
                if frameRangeData.get("endFrame") is not None:
                    details["endframe"] = frameRangeData["endFrame"]
                if frameRangeData.get("fps"):
                    details["fps"] = frameRangeData["fps"]
            except:
                pass

        self.core.saveVersionInfo(
            filepath=os.path.dirname(outputPath),
            details=details
        )

        self.core.popup(
            f"Saved and added to render queue!\n\nOutput: {outputPath}"
            "\n\nClick Render in AE's Render Queue to start."
        )
        self.dlg_export.close()

        return True

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
