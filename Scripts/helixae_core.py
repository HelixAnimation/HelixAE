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

from PrismUtils.Decorators import err_catcher as err_catcher

import helixae_bridge
import helixae_protocol


class HelixAECore:
    def __init__(self, main):
        self.main = main
        self.core = main.core
        self.win = platform.system() == "Windows"

    @err_catcher(name=__name__)
    def executeAppleScript(self, script):
        """
        Send ExtendScript to After Effects via a fresh socket connection per call.

        Requests and responses are null-terminated frames (see
        Scripts/helixae_bridge.py); exactly one request is sent per connection.
        Returns bytes with the script result. Transport failures raise: a
        connection that closes before the response terminator is never treated
        as a valid (empty) response.
        """
        # Prepend JSON polyfill if the script uses JSON (json2, ExtendScript
        # has no native JSON — see Scripts/helixae_protocol.py)
        script = helixae_protocol.ensure_json_polyfill(script)

        frame = helixae_bridge.frame_ae_request(script)

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(120.0)  # 120s — imports can take a long time
                s.connect(('127.0.0.1', 9888))
            except Exception as e:
                raise Exception("Cannot connect to After Effects on 127.0.0.1:9888 (%s)" % e)

            s.sendall(frame)
            return helixae_bridge.recv_ae_response(s)

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

    # The JSON polyfill lives in Scripts/helixae_protocol.py (JSON2_POLYFILL).
    # Kept as an alias for backwards compatibility.
    _JSON_POLYFILL = helixae_protocol.JSON2_POLYFILL

    @err_catcher(name=__name__)
    def getCurrentFileName(self, origin, path=True):
        """Get current AE project file path"""
        try:
            result = self.executeAppleScript(helixae_protocol.build_get_current_file())
            data, error = helixae_protocol.parse_json_response(result)
            if error or not data.get("result"):
                return ""
            file_path = data.get("path") or ""
            if not file_path:
                return ""
            file_name, _ = os.path.splitext(file_path)
            currentFileName = file_name.replace("\\\\", "/")
            return currentFileName + ".aep" if path else currentFileName.split("\\")[-1]
        except Exception:
            return ""

    @err_catcher(name=__name__)
    def getSceneExtension(self, origin):
        """Get scene file extension"""
        doc = self.core.getCurrentFileName()
        return os.path.splitext(doc)[1] if doc else self.main.sceneFormats[0]

    @err_catcher(name=__name__)
    def saveScene(self, origin, filepath, details={}):
        """Save AE project to specified filepath and generate archive info.

        The save is only reported as successful when After Effects confirms
        it (see helixae_protocol.build_save_scene). Archive data is owned by
        the exact save that produced it: stale data from a previous save is
        never reused for a later one.
        """
        # Per-save state: anything left from a previous save is stale.
        self._last_archive_data = None
        self._last_archive_path = None
        skip_version_scan = bool(getattr(self, "_skip_version_scan_next", False))
        self._skip_version_scan_next = False
        try:
            result = self.executeAppleScript(helixae_protocol.build_save_scene(filepath))
            data, error = helixae_protocol.parse_json_response(result)
            if error:
                raise Exception("Save failed: %s" % error)
            if not data.get("result"):
                raise Exception(
                    "Save failed: %s" % data.get("details", "unknown After Effects error")
                )

            # Save confirmed. Archive info generation must not fail the save.
            try:
                from footage_tracker import archive_info
                from footage_tracker.utils import FootageUtils
                from footage_tracker.tree_operations import TreeOperations  # noqa: F401

                # Create utils instance for parsing paths
                utils = FootageUtils()
                version_cache = {}

                # Generate archive JSON file next to the .aep file
                archive_path = os.path.splitext(filepath)[0] + "_archiveinfo.json"

                # Fresh footage scan (JSON; file-backed items only)
                result = self.executeAppleScript(
                    helixae_protocol.build_collect_footage_records()
                )
                footage_records, scan_error = helixae_protocol.parse_footage_records(result)
                if scan_error:
                    raise Exception("footage scan failed: %s" % scan_error)

                # Process the footage data into hierarchy (same logic as loadFootageData)
                hierarchy = {
                    "3D Renders": {},
                    "2D Renders": {},
                    "Resources": {},
                    "External": {},
                    "Comps": {}
                }

                for record in footage_records:
                    name = record["name"]
                    path = record["path"]

                    versionInfo = utils.parseFootagePath(
                        path,
                        version_cache,
                        verify_versions=False,
                        scan_versions=not skip_version_scan,
                    )
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

                    footage_entry = {
                        'name': name,
                        'footageId': record['footageId'],
                        'versionInfo': versionInfo,
                        'fps': record['fps'],
                        'duration': record['duration'],
                        'startFrame': record['startFrame'],
                        'endFrame': record['endFrame'],
                        'path': path,
                        'group': group,
                        'hierarchy_type': hierarchy_type,
                        'isLatest': versionInfo['currentVersion'] == versionInfo['latestVersion']
                    }

                    if hierarchy_type == 'render':
                        # For renders, use shot/identifier/aov structure
                        if shot not in hierarchy[group]:
                            hierarchy[group][shot] = {}
                        if identifier not in hierarchy[group][shot]:
                            hierarchy[group][shot][identifier] = {}
                        if aov not in hierarchy[group][shot][identifier]:
                            hierarchy[group][shot][identifier][aov] = []

                        hierarchy[group][shot][identifier][aov].append(footage_entry)
                    else:
                        # For preserved structures, use relative path structure
                        relative_path = identifier if identifier else os.path.splitext(name)[0]
                        if relative_path not in hierarchy[group]:
                            hierarchy[group][relative_path] = []

                        footage_entry['relative_path'] = relative_path
                        hierarchy[group][relative_path].append(footage_entry)

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
                    # Owned by THIS save; postSaveScene only uses it for this path.
                    self._last_archive_data = archive_data
                    self._last_archive_path = os.path.normpath(os.path.abspath(filepath))

                    written = archive_info.write_archive_json(archive_data, archive_path)
                    if not written:
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
        except Exception as e:
            self.core.popup(f"Saving in After Effects failed:\n{str(e)}")
            return False

    def _patchVersionInfo(self, filepath, archive_data=None):
        """Patch versioninfo with dependencies and externalFiles from archive data."""
        try:
            import json as _json
            base = os.path.splitext(filepath)[0]
            ext = self.core.configs.getProjectExtension()
            versioninfo_path = base + "versioninfo" + ext
            if not os.path.exists(versioninfo_path):
                return

            # Fall back to reading the archiveinfo file if no data passed in
            if archive_data is None:
                archiveinfo_path = base + "_archiveinfo.json"
                if not os.path.exists(archiveinfo_path):
                    return
                with open(archiveinfo_path, 'r') as f:
                    archive_data = _json.load(f)

            with open(versioninfo_path, 'r') as f:
                vinfo = _json.load(f)

            source_paths = archive_data.get("source_paths", {})
            dependencies = [
                p.replace("\\", "/") for p in
                source_paths.get("3d_renders", []) +
                source_paths.get("2d_renders", [])
            ]
            external_files = [
                p.replace("\\", "/") for p in
                source_paths.get("resources", []) +
                archive_data.get("external_paths", [])
            ]

            # An absent category in archive data means "keep whatever the
            # archive file says"; a present (even empty) list is authoritative.
            if "source_paths" in archive_data:
                vinfo["dependencies"] = dependencies
                vinfo["externalFiles"] = external_files

            with open(versioninfo_path, 'w') as f:
                _json.dump(vinfo, f, indent=2)

        except Exception as e:
            print(f"[HelixAE] Failed to patch versioninfo: {e}")

    @err_catcher(name=__name__)
    def getAppVersion(self, origin):
        """Get After Effects version"""
        if self.win:
            return self.main.psApp.Version
        scpt = f'tell application "{self.psAppName}"\napplication version\nend tell'
        return self.executeAppleScript(scpt)

    @err_catcher(name=__name__)
    def openScene(self, origin, filepath, force=False):
        """Open AE project file.  Success requires a confirmed AE ack."""
        if not filepath.endswith(".aep"):
            return False
        try:
            result = self.executeAppleScript(helixae_protocol.build_open_scene(filepath))
            data, error = helixae_protocol.parse_json_response(result)
            if error:
                raise Exception(error)
            if not data.get("result"):
                raise Exception(
                    data.get("details", "After Effects did not open the project")
                )
            preparation = getattr(self.main, '_footage_preparation', None)
            if preparation:
                preparation.scene_opened()
            return True
        except Exception as e:
            self.core.popup(f"Opening in After Effects failed:\n{str(e)}")
            return False

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
