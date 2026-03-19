# -*- coding: utf-8 -*-
"""
Kitsu Integration Module
"""

import time
from PrismUtils.Decorators import err_catcher as err_catcher
from qtpy.QtCore import *
from qtpy.QtGui import *


class KitsuIntegration:
    """Handles all Kitsu-related functionality"""

    # Cache timeout in seconds (default 5 minutes)
    CACHE_TIMEOUT = 300

    def __init__(self, main, core):
        self.main = main
        self.core = core
        self.kitsuShotData = {}
        self.kitsu = None
        self.kitsuLoadError = None

        # Cache tracking
        self._kitsu_cache_time = None
        self._kitsu_cache_duration = self.CACHE_TIMEOUT

        # Try to import ae_kitsu module
        try:
            from . import ae_kitsu
            self.kitsu = ae_kitsu.AEKitsu(main)
        except Exception as e:
            import traceback
            errorMsg = f"Warning: Could not load ae_kitsu module: {e}\n\nFull traceback:\n{traceback.format_exc()}"
            print(errorMsg)
            self.kitsu_error = errorMsg

    def _isCacheValid(self):
        """Check if cached Kitsu data is still valid"""
        if self._kitsu_cache_time is None:
            return False
        cache_age = time.time() - self._kitsu_cache_time
        return cache_age < self._kitsu_cache_duration

    def _getCacheAge(self):
        """Get the age of the cache in seconds"""
        if self._kitsu_cache_time is None:
            return None
        return time.time() - self._kitsu_cache_time

    @err_catcher(name=__name__)
    def loadKitsuShotData(self, force_refresh=False):
        """
        Load frame ranges and FPS from Kitsu for all shots

        Args:
            force_refresh: If True, bypass cache and force reload from Kitsu
        """
        # Check if we have valid cached data
        if not force_refresh and self._isCacheValid():
            cache_age = self._getCacheAge()
            print(f"[KITSU] ✓ Using cached data (age: {cache_age:.1f}s, timeout: {self._kitsu_cache_duration}s)")
            return

        if force_refresh:
            print(f"[KITSU] ⚠ Force refresh requested, bypassing cache")
        else:
            cache_age = self._getCacheAge()
            if cache_age is not None:
                print(
                    f"[KITSU] ⚠ Cache expired (age: {cache_age:.1f}s, "
                    f"timeout: {self._kitsu_cache_duration}s), fetching from Kitsu..."
                )
            else:
                print(f"[KITSU] ⚠ No cached data, fetching from Kitsu...")
        errorMessages = []
        
        if not self.kitsu:
            errorMessages.append("Kitsu module not loaded")
            self.kitsuLoadError = "\n".join(errorMessages)
            return
        
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if not prjMng:
                errorMessages.append("ProjectManagement plugin not found")
                self.kitsuLoadError = "\n".join(errorMessages)
                return
                
            if not hasattr(prjMng, 'curManager'):
                errorMessages.append("ProjectManagement has no curManager attribute")
                self.kitsuLoadError = "\n".join(errorMessages)
                return
                
            if not prjMng.curManager:
                errorMessages.append("ProjectManagement.curManager is None")
                errorMessages.append("Attempting to activate Kitsu manager...")
                
                if hasattr(prjMng, 'managers') and prjMng.managers:
                    if isinstance(prjMng.managers, dict):
                        errorMessages.append(f"Available managers (dict): {list(prjMng.managers.keys())}")
                        for managerName, manager in prjMng.managers.items():
                            if 'kitsu' in managerName.lower():
                                errorMessages.append(f"Found Kitsu manager: {managerName}")
                                try:
                                    if hasattr(prjMng, 'setCurrentManager'):
                                        prjMng.setCurrentManager(managerName)
                                        errorMessages.append(f"Activated {managerName}")
                                    elif hasattr(manager, 'activate'):
                                        manager.activate()
                                        prjMng.curManager = manager
                                        errorMessages.append(f"Manually activated {managerName}")
                                    break
                                except Exception as e:
                                    errorMessages.append(f"Failed to activate {managerName}: {e}")
                    elif isinstance(prjMng.managers, list):
                        errorMessages.append(
                            f"Available managers (list): "
                            f"{[getattr(m, 'name', str(m)) for m in prjMng.managers]}"
                        )
                        for manager in prjMng.managers:
                            managerName = getattr(manager, 'name', str(manager))
                            if 'kitsu' in managerName.lower():
                                errorMessages.append(f"Found Kitsu manager: {managerName}")
                                try:
                                    if hasattr(prjMng, 'setCurrentManager'):
                                        prjMng.setCurrentManager(manager)
                                        errorMessages.append(f"Called setCurrentManager({managerName})")
                                        errorMessages.append(
                                            f"After setCurrentManager: prjMng.curManager = {prjMng.curManager}"
                                        )
                                        if not prjMng.curManager:
                                            errorMessages.append(f"setCurrentManager didn't work, setting manually...")
                                            prjMng.curManager = manager
                                            errorMessages.append(
                                                f"After manual set: prjMng.curManager = {prjMng.curManager}"
                                            )
                                    else:
                                        prjMng.curManager = manager
                                        errorMessages.append(f"Manually set curManager to {managerName}")
                                    break
                                except Exception as e:
                                    import traceback
                                    errorMessages.append(f"Failed to activate {managerName}: {e}")
                                    errorMessages.append(traceback.format_exc())
                else:
                    errorMessages.append("No managers found in ProjectManagement.managers")
                
                if not prjMng.curManager:
                    self.kitsuLoadError = "\n".join(errorMessages)
                    return
                else:
                    errorMessages.append("Manager successfully activated, continuing...")
            
            kitsuMgr = prjMng.curManager
            errorMessages.append(f"Got kitsuMgr: {kitsuMgr}")
            errorMessages.append(f"Manager name: {kitsuMgr.name}")
            
            if kitsuMgr.name != "Kitsu":
                errorMessages.append(f"Manager is '{kitsuMgr.name}', not 'Kitsu'")
                self.kitsuLoadError = "\n".join(errorMessages)
                return
            
            errorMessages.append(f"Project path: {getattr(self.core, 'projectPath', None)}")
            
            if not getattr(self.core, 'projectPath', None):
                errorMessages.append("Project not loaded, attempting to load...")
                try:
                    import os
                    currentFile = self.core.getCurrentFileName()
                    errorMessages.append(f"Current file: {currentFile}")
                    if currentFile:
                        currentFile = str(currentFile).replace("'", "").replace('"', '').strip()
                        if os.path.exists(currentFile):
                            parts = currentFile.replace("\\", "/").split("/")
                            prodIndex = -1
                            if "02_Production" in parts:
                                prodIndex = parts.index("02_Production")
                            elif "03_Production" in parts:
                                prodIndex = parts.index("03_Production")
                            
                            if prodIndex > 0:
                                projectPath = "/".join(parts[:prodIndex])
                                errorMessages.append(f"Detected project path: {projectPath}")
                                if os.path.exists(projectPath):
                                    errorMessages.append("Calling core.changeProject()...")
                                    self.core.changeProject(projectPath)
                                    errorMessages.append("Project loaded successfully!")
                                else:
                                    errorMessages.append(f"Project path doesn't exist: {projectPath}")
                            else:
                                errorMessages.append("Could not find Production folder in path")
                        else:
                            errorMessages.append(f"Current file doesn't exist: {currentFile}")
                    else:
                        errorMessages.append("No current file found")
                except Exception as e:
                    import traceback
                    errorMessages.append(f"Error loading project: {e}")
                    errorMessages.append(traceback.format_exc())
            else:
                errorMessages.append("Project already loaded")
            
            errorMessages.append(f"Project path after load attempt: {getattr(self.core, 'projectPath', None)}")
            
            try:
                projectFps = kitsuMgr.getFps() or 24.0
                errorMessages.append(f"Project FPS: {projectFps}")
            except Exception as e:
                projectFps = self.core.getConfig("globals", "fps", config="project") or 25.0
                errorMessages.append(f"Could not get FPS from Kitsu, using config: {projectFps}")

            # Get project resolution from Kitsu or config
            projectWidth = None
            projectHeight = None

            # Try to get from Kitsu manager's getResolution method
            try:
                if hasattr(kitsuMgr, 'getResolution'):
                    projectResolution = kitsuMgr.getResolution()
                    print(f"[KITSU] DEBUG - getResolution() returned: {projectResolution}")
                    if projectResolution:
                        import re
                        resMatch = re.search(r'(\d+)\s*[xX]\s*(\d+)', str(projectResolution))
                        if resMatch:
                            projectWidth = int(resMatch.group(1))
                            projectHeight = int(resMatch.group(2))
                            errorMessages.append(f"Project Resolution from Kitsu: {projectWidth}x{projectHeight}")
            except Exception as e:
                print(f"[KITSU] DEBUG - getResolution() error: {e}")
                errorMessages.append(f"Error getting resolution from Kitsu: {e}")

            # Fallback to Prism project config
            if not projectWidth or not projectHeight:
                configWidth = self.core.getConfig("globals", "width", config="project")
                configHeight = self.core.getConfig("globals", "height", config="project")
                print(f"[KITSU] DEBUG - Prism config - width: {configWidth}, height: {configHeight}")
                errorMessages.append(f"Prism config - width: {configWidth}, height: {configHeight}")

                projectWidth = int(configWidth) if configWidth else 1920
                projectHeight = int(configHeight) if configHeight else 1080
                errorMessages.append(f"Using resolution: {projectWidth}x{projectHeight}")
            
            errorMessages.append("Calling kitsuMgr.getShots()...")
            shots = kitsuMgr.getShots() or []
            errorMessages.append(f"Got {len(shots)} shots from Kitsu")

            # Check if there's a gazu client (Kitsu Python API client)
            gazu_client = None
            if hasattr(kitsuMgr, 'gazu'):
                gazu_client = kitsuMgr.gazu

            # Use gazu to get full shot data with resolution
            shot_resolutions = {}
            if gazu_client:
                print(f"[KITSU] Fetching shot details from Kitsu (with resolution)...")
                for shot in shots:
                    shot_id = shot.get('id')
                    shot_name = shot.get('shot', '')
                    sequence = shot.get('sequence', '')

                    if shot_id:
                        try:
                            # Use gazu's get_shot function which returns full shot data
                            full_shot = gazu_client.shot.get_shot(shot_id)

                            # Check for resolution in the shot data
                            shot_resolution = None
                            if 'resolution' in full_shot.get('data', {}):
                                shot_resolution = full_shot['data']['resolution']
                            elif 'resolution_id' in full_shot:
                                # If there's a resolution_id, fetch it
                                resolution_id = full_shot.get('resolution_id')
                                if resolution_id:
                                    shot_resolution_obj = gazu_client.client.get(f"/data/resolutions/{resolution_id}")
                                    shot_resolution = shot_resolution_obj.get('name')

                            shot_resolutions[shot_id] = shot_resolution
                        except Exception as e:
                            pass  # Silent fail, will use project default

                custom_count = sum(1 for r in shot_resolutions.values() if r is not None)
                print(f"[KITSU] Loaded {len(shot_resolutions)} shots, {custom_count} with custom resolution")

            self.kitsuShotData = {}
            shot_list_summary = []  # Store summary for printing at the end

            # Fetch tasks for all shots in one batch (cache them for context menu)
            print(f"[KITSU] Fetching tasks for all shots...")
            all_tasks = {}
            try:
                for shot in shots:
                    shot_id = shot.get("id")
                    if shot_id:
                        try:
                            shot_tasks = kitsuMgr.getTasksFromEntity(shot, quiet=True) or []
                            all_tasks[shot_id] = shot_tasks
                        except Exception:
                            all_tasks[shot_id] = []
                print(f"[KITSU] ✓ Fetched tasks for {len(all_tasks)} shots")
            except Exception as e:
                print(f"[KITSU] ⚠ Could not fetch tasks: {e}")

            for shot in shots:
                shotName = shot.get("shot", "")
                sequence = shot.get("sequence", "")
                shot_id = shot.get("id", "")

                # Get resolution from the gazu-fetched data if available
                shot_resolution = shot_resolutions.get(shot_id) if shot_id else None

                # Default to project resolution
                shot_width = projectWidth if projectWidth else 1920
                shot_height = projectHeight if projectHeight else 1080
                resolution_source = "project default"

                # Parse shot-level resolution if available
                if shot_resolution:
                    import re
                    resMatch = re.search(r'(\d+)\s*[xX]\s*(\d+)', str(shot_resolution))
                    if resMatch:
                        shot_width = int(resMatch.group(1))
                        shot_height = int(resMatch.group(2))
                        resolution_source = "custom from Kitsu"
                        errorMessages.append(
                            f"  Shot resolution from Kitsu: {shot_resolution} -> {shot_width}x{shot_height}"
                        )
                    else:
                        errorMessages.append(f"  Shot resolution found but couldn't parse: {shot_resolution}")

                if shotName:
                    start = shot.get("start")
                    end = shot.get("end")
                    frameRange = f"{start}-{end}" if start is not None and end is not None else None

                    self.kitsuShotData[shotName] = {
                        'frameRange': frameRange,
                        'fps': projectFps,
                        'start': start,
                        'end': end,
                        'width': shot_width,
                        'height': shot_height,
                        'resolution': f"{shot_width}x{shot_height}",
                        'tasks': all_tasks.get(shot_id, []),
                        'id': shot_id
                    }

                    # Add to summary list for printing all shots
                    display_name = f"{sequence}-{shotName}" if sequence and "-" not in shotName else shotName
                    shot_list_summary.append(f"  {display_name}: {shot_width}x{shot_height} ({resolution_source})")

                    if sequence and "-" not in shotName:
                        combinedName = f"{sequence}-{shotName}"
                        self.kitsuShotData[combinedName] = {
                            'frameRange': frameRange,
                            'fps': projectFps,
                            'start': start,
                            'end': end,
                            'width': shot_width,
                            'height': shot_height,
                            'resolution': f"{shot_width}x{shot_height}",
                            'tasks': all_tasks.get(shot_id, []),
                            'id': shot_id
                        }
                        errorMessages.append(f"  Stored as: {shotName} and {combinedName}")
                    else:
                        errorMessages.append(f"  Stored as: {shotName} only")
            
            errorMessages.append(f"\nTotal entries in kitsuShotData: {len(self.kitsuShotData)}")
            self.kitsuLoadError = "\n".join(errorMessages)

            # Update cache timestamp after successful load
            self._kitsu_cache_time = time.time()
            print(f"[KITSU] ✓ Data loaded and cached ({len(self.kitsuShotData)} shots)")

            # Print summary of custom resolution shots
            custom_shots = [line for line in shot_list_summary if "custom from Kitsu" in line]
            if custom_shots:
                print(f"[KITSU] Shots with custom resolution:")
                for line in custom_shots:
                    print(f"[KITSU] {line}")
            else:
                print(
                    f"[KITSU] No shots with custom resolution "
                    f"(all using project default {projectWidth}x{projectHeight})"
                )
                    
        except Exception as e:
            import traceback
            errorMsg = f"Error loading Kitsu data: {e}\n{traceback.format_exc()}"
            errorMessages.append(errorMsg)
            self.kitsuLoadError = "\n".join(errorMessages)
            print(errorMsg)
    
    def getKitsuDataForShot(self, shotName):
        """Get Kitsu frame range and FPS data for a specific shot"""
        return self.kitsuShotData.get(shotName)
    
    def getKitsuShotEntity(self, shotName):
        """Get the Kitsu shot entity for a given shot name"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if not prjMng or not hasattr(prjMng, 'curManager') or not prjMng.curManager:
                return None
            
            kitsuMgr = prjMng.curManager
            shots = kitsuMgr.getShots() or []
            
            for shot in shots:
                if shot.get('shot') == shotName:
                    return shot
                
                sequence = shot.get('sequence', '')
                fullName = f"{sequence}-{shot.get('shot', '')}"
                if fullName == shotName:
                    return shot
            
            return None
        except Exception as e:
            return None
    
    def getStatusColor(self, statusShortName, kitsuMgr):
        """Get status color from Kitsu or use default colors"""
        try:
            if kitsuMgr and hasattr(kitsuMgr, 'getTaskStatusColor'):
                color = kitsuMgr.getTaskStatusColor(statusShortName)
                if color:
                    return QColor(color)
            
            colorMap = {
                'todo': QColor(150, 150, 150),
                'wip': QColor(50, 115, 220),
                'wfa': QColor(171, 38, 255),
                'done': QColor(34, 197, 94),
                'retake': QColor(239, 68, 68),
            }
            return colorMap.get(statusShortName.lower(), QColor(150, 150, 150))
        except Exception:
            return QColor(150, 150, 150)
    
    def createColorIcon(self, color):
        """Create a small colored circle icon for menu items"""
        from qtpy.QtWidgets import QApplication
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()
        
        return QIcon(pixmap)
    
    @err_catcher(name=__name__)
    def openShotInKitsu(self, shot):
        """Open shot in Kitsu web browser"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                kitsuMgr.openInBrowser("shot", shot)
        except Exception as e:
            self.core.popup(f"Error opening Kitsu:\n{str(e)}")
    
    @err_catcher(name=__name__)
    def openTaskInKitsu(self, task):
        """Open task in Kitsu web browser"""
        try:
            prjMng = self.core.getPlugin("ProjectManagement")
            if prjMng and hasattr(prjMng, 'curManager') and prjMng.curManager:
                kitsuMgr = prjMng.curManager
                kitsuMgr.openInBrowser("task", task)
        except Exception as e:
            self.core.popup(f"Error opening task in Kitsu:\n{str(e)}")
    
    @err_catcher(name=__name__)
    def openKitsuShotList(self):
        """Open the Kitsu shot list dialog"""
        if self.kitsu:
            self.loadKitsuShotData()
            self.kitsu.openShotListDialog()
        else:
            self.core.popup(
                "Kitsu integration is not available. "
                "Please check that the Kitsu plugin is installed and enabled."
            )
    
    def showKitsuError(self, core):
        """Show detailed Kitsu loading error"""
        if hasattr(self, 'kitsu_error'):
            core.popup(self.kitsu_error)
        else:
            core.popup(
                "Kitsu integration is not available. "
                "Please check that the Kitsu plugin is installed and enabled."
            )
