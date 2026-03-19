# -*- coding: utf-8 -*-
"""
Helix AE Core Functions
Handles basic AE operations: startup, scene management, script execution, archive info generation
"""

import os
import socket
import platform
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

# For socket thread safety
from qtpy.QtCore import QMutex, QMutexLocker

from PrismUtils.Decorators import err_catcher as err_catcher


class HelixAECore:
    def __init__(self, main):
        self.main = main
        self.core = main.core
        self.win = platform.system() == "Windows"
        self._socket = None  # Persistent socket connection
        self._socket_lock = QMutex()  # Thread safety

        # Try to connect immediately when plugin loads
        self._tryConnect()

    def _tryConnect(self):
        """Attempt to establish socket connection to AE"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(0.5)  # Quick timeout for initial connect
            self._socket.connect(('127.0.0.1', 9888))
            self._socket.settimeout(None)  # Remove timeout for normal use
            return True
        except Exception as e:
            self._socket = None
            return False

    @err_catcher(name=__name__)
    def startup(self, origin):
        """Initialize Helix AE UI styling and detect AE version"""
        origin.timer.stop()
        root = os.path.dirname(self.main.pluginDirectory).replace("\\", "/").split("Scripts")[0]

        # Load stylesheet
        stylesheet_path = os.path.join(root, "UserInterfaces", "HelixAEStyleSheet", "HelixAE.qss")
        with open(stylesheet_path, "r") as ssFile:
            ssheet = ssFile.read().replace(
                "qss:",
                os.path.join(root, "UserInterfaces", "HelixAEStyleSheet").replace("\\", "/") + "/"
            )

        qApp.setStyleSheet(ssheet)
        qApp.setWindowIcon(QIcon(os.path.join(
            self.core.prismRoot, "Scripts", "UserInterfacesPrism", "p_tray.png"
        )))

        # macOS: Find and activate AE
        if not self.win:
            self.psAppName = "Adobe AfterEffects CC 2019"
            for foldercont in os.walk("/Applications"):
                for folder in reversed(sorted(foldercont[1])):
                    if folder.startswith("Adobe AfterEffects"):
                        self.psAppName = folder
                        break
                break
            self.executeAppleScript(f'tell application "{self.psAppName}"\nactivate\nend tell')

        # Auto-open footage tracker if setting is enabled
        from qtpy.QtCore import QSettings
        settings = QSettings("HelixAE", "HelixAEPlugin")
        if settings.value("FootageTracker/OpenOnStart", False, type=bool):
            # Use QTimer to delay opening so UI is fully loaded first
            from qtpy.QtCore import QTimer
            QTimer.singleShot(1000, lambda: self.openFootageTracker())

        return False

    @err_catcher(name=__name__)
    def executeAppleScript(self, script):
        """
        Send ExtendScript to After Effects via persistent socket connection
        Returns bytes object with script result
        """
        with QMutexLocker(self._socket_lock):
            # Ensure we have a connection
            if self._socket is None:
                if not self._tryConnect():
                    raise Exception("Cannot connect to After Effects on 127.0.0.1:9888")

            try:
                self._socket.sendall(script.encode("utf-8"))
                return self._socket.recv(16384)
            except (ConnectionError, BrokenPipeError, OSError) as e:
                # Connection lost - try to reconnect once
                self._socket = None
                if self._tryConnect():
                    self._socket.sendall(script.encode("utf-8"))
                    return self._socket.recv(16384)
                raise Exception(f"Connection to After Effects lost: {e}")

    @err_catcher(name=__name__)
    def getCurrentFileName(self, origin, path=True):
        """Get current AE project file path"""
        try:
            result = self.executeAppleScript("app.project.file.fsName;")
            if result:
                # Clean up the result from AE - ensure it's a string
                if isinstance(result, bytes):
                    result = result.decode('utf-8')
                elif not isinstance(result, str):
                    result = str(result)
                result = result.strip()

                # Remove any quote/backtick wrappers
                if result.startswith("u'") or result.startswith('u"'):
                    result = result[2:-1]  # Remove u' or u" wrapper
                elif result.startswith("'") or result.startswith('"') or result.startswith("`"):
                    result = result[1:-1]  # Remove ' or " or ` wrapper
                result = result.rstrip('`\'"')  # Remove trailing backticks, quotes, apostrophes

                file_name, _ = os.path.splitext(result)
                currentFileName = file_name.replace("\\\\", "/")
                return currentFileName + ".aep" if path else currentFileName.split("\\")[-1]
            return ""
        except Exception:
            return ""

    @err_catcher(name=__name__)
    def getSceneExtension(self, origin):
        """Get scene file extension"""
        doc = self.core.getCurrentFileName()
        return os.path.splitext(doc)[1] if doc else self.main.sceneFormats[0]

    @err_catcher(name=__name__)
    def saveScene(self, origin, filepath, details={}):
        """Save AE project to specified filepath and generate archive info"""
        try:
            # Escape backslashes in filepath for ExtendScript
            escaped_path = filepath.replace(chr(92), "//")
            scpt = f"app.project.save(File('{escaped_path}'));"
            result = self.executeAppleScript(scpt)

            # Check for errors in the result
            if result and b"error" in result.lower():
                raise Exception(f"Save failed: {result.decode('utf-8', errors='ignore')}")

            # After successful save, always generate archive info
            try:
                # Import required modules for archive info generation
                from footage_tracker import archive_info
                from footage_tracker.utils import FootageUtils
                from footage_tracker.tree_operations import TreeOperations

                # Create utils instance for parsing paths
                utils = FootageUtils()

                # Generate archive JSON file next to the .aep file
                archive_path = os.path.splitext(filepath)[0] + "_archiveinfo.json"

                # Always scan the footage list and generate fresh hierarchy
                # Get fresh footage data from AE directly
                scpt = """
                    var footageList = [];
                    for (var i = 1; i <= app.project.numItems; i++) {
                        var item = app.project.item(i);
                        if (item instanceof FootageItem && item.mainSource instanceof FileSource) {
                            var fps = 'N/A';
                            var duration = 'N/A';
                            var startFrame = 'N/A';
                            var endFrame = 'N/A';

                            try {
                                fps = item.mainSource.conformFrameRate.toFixed(2);
                            } catch(e) {}

                            try {
                                duration = item.duration.toFixed(2);
                            } catch(e) {}

                            try {
                                if (item.mainSource instanceof FileSource) {
                                    var filePath = item.mainSource.file.fsName;
                                    var fileName = item.mainSource.file.name;
                                    var frameMatch = fileName.match(/[._](\\d{4,5})\\.[^.]+$/);
                                    if (frameMatch) {
                                        startFrame = parseInt(frameMatch[1]);
                                        if (duration != 'N/A' && fps != 'N/A') {
                                            var frameCount = Math.floor(parseFloat(duration) * parseFloat(fps));
                                            endFrame = startFrame + frameCount - 1;
                                        }
                                    }
                                }
                            } catch(e) {}

                            footageList.push(
                                item.id + '|||' +
                                item.name + '|||' +
                                item.mainSource.file.fsName + '|||' +
                                fps + '|||' +
                                duration + '|||' +
                                startFrame + '|||' +
                                endFrame
                            );
                        }
                    }
                    footageList.join('::ITEM::');
                    """

                result = self.executeAppleScript(scpt)

                # Handle bytes result properly
                result_str = ""
                if result:
                    if isinstance(result, bytes):
                        result_str = result.decode('utf-8')
                    else:
                        result_str = str(result)

                footageData = result_str.split('::ITEM::') if result_str else []

                # Process the footage data into hierarchy (same logic as loadFootageData)
                hierarchy = {
                    "3D Renders": {},
                    "2D Renders": {},
                    "Resources": {},
                    "External": {},
                    "Comps": {}
                }

                processed_count = 0
                for footage in footageData:
                    if not footage or '|||' not in footage:
                        continue

                    parts = footage.split('|||')
                    if len(parts) < 7:
                        continue

                    processed_count += 1
                    footageId, name, path, fps, duration, startFrame, endFrame = parts
                    path = path.replace('\\\\', '/')

                    versionInfo = utils.parseFootagePath(path)
                    if not versionInfo:
                        continue
                    if not versionInfo:
                        continue

                    # Extract hierarchy with new return format
                    result = utils.extractHierarchy(path, name)
                    if len(result) == 5:
                        shot, identifier, aov, group, hierarchy_type = result
                    else:
                        # Handle old format for backward compatibility
                        shot, identifier, aov, group = result[:4]
                        hierarchy_type = result[4] if len(result) > 4 else 'render'

                    # Ensure group is one of our valid groups
                    if group not in hierarchy:
                        if hierarchy_type == 'render':
                            # Default renders to 3D Renders if not specified
                            group = "3D Renders"
                        else:
                            # Default preserved to Resources if not specified
                            group = "Resources"

                    if hierarchy_type == 'render':
                        # For renders, use shot/identifier/aov structure
                        if shot not in hierarchy[group]:
                            hierarchy[group][shot] = {}
                        if identifier not in hierarchy[group][shot]:
                            hierarchy[group][shot][identifier] = {}
                        if aov not in hierarchy[group][shot][identifier]:
                            hierarchy[group][shot][identifier][aov] = []

                        footageData = {
                            'name': name,
                            'footageId': footageId,
                            'versionInfo': versionInfo,
                            'fps': fps,
                            'duration': duration,
                            'startFrame': startFrame,
                            'endFrame': endFrame,
                            'path': path,
                            'group': group,
                            'hierarchy_type': hierarchy_type,
                            'isLatest': versionInfo['currentVersion'] == versionInfo['latestVersion']
                        }
                        hierarchy[group][shot][identifier][aov].append(footageData)
                    else:
                        # For preserved structures, use relative path structure
                        relative_path = identifier if identifier else os.path.splitext(name)[0]
                        if relative_path not in hierarchy[group]:
                            hierarchy[group][relative_path] = []

                        footageData = {
                            'name': name,
                            'footageId': footageId,
                            'versionInfo': versionInfo,
                            'fps': fps,
                            'duration': duration,
                            'startFrame': startFrame,
                            'endFrame': endFrame,
                            'path': path,
                            'group': group,
                            'hierarchy_type': hierarchy_type,
                            'relative_path': relative_path,
                            'isLatest': versionInfo['currentVersion'] == versionInfo['latestVersion']
                        }
                        hierarchy[group][relative_path].append(footageData)

                # Get tracker for archive info generation (use ae_footage like old plugin)
                main_functions = getattr(self.main, 'functions', None) or self.main
                tracker = getattr(main_functions, 'ae_footage', None)

                # Store hierarchy if tracker exists
                if tracker:
                    tracker._stored_hierarchy = hierarchy
                if hasattr(main_functions, '_footage_hierarchy'):
                    main_functions._footage_hierarchy = hierarchy

                # Generate archive data with fresh hierarchy (only if tracker available)
                if tracker:
                    archive_data = archive_info.generate_archive_info(tracker, filepath, hierarchy)

                    if archive_info.write_archive_json(archive_data, archive_path):
                        self.core.popup(f"Archive info saved automatically!\n\nFile: {archive_path}")
                    else:
                        self.core.popup("Failed to save archive info file.")
                else:
                    self.core.popup(
                        "Warning: Footage tracker not available. Could not generate archive info.\n\n"
                        "Open the Footage Tracker once to enable automatic archive info generation."
                    )

            except Exception as e:
                # Don't fail the save operation if archive generation fails
                import traceback
                traceback.print_exc()
                self.core.popup(f"Warning: Could not generate archive info.\nError: {str(e)}")

            return True
        except Exception:
            self.core.popup("There is no active document in AfterEffects.")
            return False

    @err_catcher(name=__name__)
    def getAppVersion(self, origin):
        """Get After Effects version"""
        if self.win:
            return self.main.psApp.Version
        scpt = f'tell application "{self.psAppName}"\napplication version\nend tell'
        return self.executeAppleScript(scpt)

    @err_catcher(name=__name__)
    def openScene(self, origin, filepath, force=False):
        """Open AE project file"""
        if not filepath.endswith(".aep"):
            return False
        self.executeAppleScript(f"app.open(File('{filepath}'));")
        return True

    @err_catcher(name=__name__)
    def openFootageTracker(self):
        """Open the Footage Version Tracker dialog"""
        try:
            # Try to call through main plugin
            if hasattr(self.main, 'openFootageTracker'):
                return self.main.openFootageTracker()
            # Or try through functions
            elif hasattr(self.main, 'functions') and hasattr(self.main.functions, 'openFootageTracker'):
                return self.main.functions.openFootageTracker()
            else:
                self.core.popup("Footage Tracker not available. Please ensure the footage_tracker module is installed.")
        except Exception as e:
            self.core.popup(f"Failed to open Footage Tracker:\n{str(e)}")
