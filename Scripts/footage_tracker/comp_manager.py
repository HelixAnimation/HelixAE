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


class CompManager(QObject):
    """Manages composition operations and information"""

    def __init__(self, tracker):
        super(CompManager, self).__init__()
        self.tracker = tracker
        self.core = tracker.core
        self.main = tracker.main

    @err_catcher(name=__name__)
    def setCompFrameRangeFromKitsu(self, compId, compName, kitsu_frame_range):
        """Set composition frame range from Kitsu data"""
        try:
            if not kitsu_frame_range:
                return

            # Parse the frame range (expected format: "1001-1100" or "1001-1100 (100)")
            if "-" in kitsu_frame_range:
                frame_parts = kitsu_frame_range.split("-")
                start_frame = frame_parts[0].strip()
                end_frame = frame_parts[1].split()[0].strip()  # Remove any frame count in parentheses
            else:
                self.core.popup(f"Invalid Kitsu frame range format: {kitsu_frame_range}")
                return

            # Create JavaScript/ExtendScript to set frame range
            kitsu_start_frame = int(start_frame)
            kitsu_end_frame = int(end_frame)

            scpt = f'''
            var compId = {compId};
            var kitsuStartFrame = {kitsu_start_frame};
            var kitsuEndFrame = {kitsu_end_frame};

            if (app.project && app.project.numItems > 0) {{
                var comp = app.project.itemByID(compId);
                if (comp && comp instanceof CompItem) {{
                    try {{
                        var frameRate = comp.frameRate;

                        // Use the formula with floating-point precision compensation
                        var epsilon = 0.000001;
                        var displayStartTime = kitsuStartFrame / frameRate + epsilon;
                        var duration = (kitsuEndFrame - kitsuStartFrame + 1) / frameRate + epsilon;

                        // Apply the calculated values to the comp
                        comp.displayStartTime = displayStartTime;
                        comp.duration = duration;

                        "Success: Set " + comp.name + " to " + kitsuStartFrame + "-" + kitsuEndFrame;
                    }} catch (e) {{
                        "Error: " + e.toString();
                    }}
                }} else {{
                    "Error: Composition not found";
                }}
            }} else {{
                "Error: No project open";
            }}
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            # Handle result that might be bytes or string
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if result.startswith("Success"):
                # Refresh the footage data to show updated info
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
                return result
            else:
                self.core.popup(f"Error setting frame range for {compName}:\n{result}")
                return None

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting frame range:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def setCompFPSFromKitsu(self, compId, compName, kitsu_fps, silent=False):
        """Set composition FPS from Kitsu data"""
        try:
            if not kitsu_fps:
                return

            # Parse the FPS (expected format: "24" or "23.976")
            try:
                fps_value = float(kitsu_fps)
            except ValueError:
                if not silent:
                    self.core.popup(f"Invalid Kitsu FPS format: {kitsu_fps}")
                return

            # Create JavaScript/ExtendScript to set composition FPS (same as setCompFromKitsu)
            scpt = f'''
            var compId = {compId};
            var kitsuFps = {fps_value};

            if (app.project && app.project.numItems > 0) {{
                var comp = app.project.itemByID(compId);
                if (comp && comp instanceof CompItem) {{
                    try {{
                        // Get current frame range to preserve it
                        var currentStartFrame = Math.floor(comp.displayStartTime * comp.frameRate);
                        var currentDuration = comp.duration;
                        var currentFrameCount = Math.floor(currentDuration * comp.frameRate);

                        // Set FPS
                        comp.frameRate = kitsuFps;

                        // Preserve frame range by recalculating with new FPS
                        var epsilon = 0.000001;
                        comp.displayStartTime = currentStartFrame / kitsuFps + epsilon;
                        comp.duration = currentFrameCount / kitsuFps + epsilon;

                        "Success: Set " + comp.name + " FPS to " + kitsuFps;
                    }} catch (e) {{
                        "Error: " + e.toString();
                    }}
                }} else {{
                    "Error: Composition not found";
                }}
            }} else {{
                "Error: No project open";
            }}
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            # Handle result that might be bytes or string
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if result.startswith("Success"):
                if not silent:
                    self.core.popup(f"Successfully set {compName} FPS to {fps_value}")
                    # Refresh the footage data to show updated info
                    if hasattr(self.tracker, 'tw_footage'):
                        self.tracker.loadFootageData()
                return result
            else:
                if not silent:
                    self.core.popup(f"Error setting FPS for {compName}:\n{result}")
                return None

        except Exception as e:
            import traceback
            if not silent:
                self.core.popup(f"Error setting FPS:\n{str(e)}\n\n{traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def setCompResolutionFromKitsu(self, compId, compName, kitsu_width, kitsu_height):
        """Set composition resolution from Kitsu data"""
        try:
            if not kitsu_width or not kitsu_height:
                return

            # Parse the resolution values
            try:
                width_value = int(kitsu_width)
                height_value = int(kitsu_height)
            except ValueError:
                self.core.popup(f"Invalid Kitsu resolution format: {kitsu_width}x{kitsu_height}")
                return

            # Create JavaScript/ExtendScript to set composition resolution
            scpt = f'''
            var compId = {compId};
            var newWidth = {width_value};
            var newHeight = {height_value};

            if (app.project && app.project.numItems > 0) {{
                var comp = app.project.itemByID(compId);
                if (comp && comp instanceof CompItem) {{
                    try {{
                        comp.width = newWidth;
                        comp.height = newHeight;
                        "Success: Set " + comp.name + " resolution to " + newWidth + "x" + newHeight;
                    }} catch (e) {{
                        "Error: " + e.toString();
                    }}
                }} else {{
                    "Error: Composition not found";
                }}
            }} else {{
                "Error: No project open";
            }}
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            # Handle result that might be bytes or string
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if result.startswith("Success"):
                self.core.popup(f"Successfully set {compName} resolution to {width_value}x{height_value}")
                # Refresh the footage data to show updated info
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
                return result
            else:
                self.core.popup(f"Error setting resolution for {compName}:\n{result}")
                return None

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting resolution:\n{str(e)}\n\n{traceback.format_exc()}")
            return None

    @err_catcher(name=__name__)
    def setCompFromKitsu(self, compId, compName, kitsu_frame_range, kitsu_fps):
        """Set both frame range and FPS from Kitsu data"""
        try:
            if not kitsu_frame_range or not kitsu_fps:
                self.core.popup("Both frame range and FPS are required from Kitsu data")
                return

            # Parse the frame range
            if "-" in kitsu_frame_range:
                frame_parts = kitsu_frame_range.split("-")
                start_frame = int(frame_parts[0].strip())
                end_frame = int(frame_parts[1].split()[0].strip())
            else:
                self.core.popup(f"Invalid Kitsu frame range format: {kitsu_frame_range}")
                return

            # Parse the FPS
            try:
                fps_value = float(kitsu_fps)
            except ValueError:
                self.core.popup(f"Invalid Kitsu FPS format: {kitsu_fps}")
                return

            # Create JavaScript/ExtendScript to set both frame range and FPS
            scpt = f'''
            var compId = {compId};
            var kitsuStartFrame = {start_frame};
            var kitsuEndFrame = {end_frame};
            var kitsuFps = {fps_value};

            if (app.project && app.project.numItems > 0) {{
                var comp = app.project.itemByID(compId);
                if (comp && comp instanceof CompItem) {{
                    try {{
                        var frameRate = kitsuFps;

                        // Use the formula with floating-point precision compensation
                        var epsilon = 0.000001;
                        var displayStartTime = kitsuStartFrame / frameRate + epsilon;
                        var duration = (kitsuEndFrame - kitsuStartFrame + 1) / frameRate + epsilon;

                        // Set FPS first
                        comp.frameRate = frameRate;

                        // Then set frame range
                        comp.displayStartTime = displayStartTime;
                        comp.duration = duration;

                        "Success: Set " + comp.name + " to "
                            + kitsuStartFrame + "-" + kitsuEndFrame
                            + " at " + frameRate + " fps";
                    }} catch (e) {{
                        "Error: " + e.toString();
                    }}
                }} else {{
                    "Error: Composition not found";
                }}
            }} else {{
                "Error: No project open";
            }}
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            # Handle result that might be bytes or string
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if result.startswith("Success"):
                # Don't show popup for each comp - just refresh
                # Refresh the footage data to show updated info
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
            else:
                self.core.popup(f"Error setting {compName} from Kitsu:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting composition from Kitsu:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showCompInfo(self, compId, compName):
        """Show detailed information about a composition"""
        try:
            # Get current shot for Kitsu comparison
            current_shot = self.tracker.data_parser.extractCurrentShotFromProject()
            kitsu_shot_data = None
            if current_shot and current_shot in self.tracker.kitsuShotData:
                kitsu_shot_data = self.tracker.kitsuShotData[current_shot]

            # Create AppleScript to get composition info
            apple_script_template = '''
            tell application "Adobe After Effects 2024"
                set compRef to item id {comp_id} of project 1
                try
                    set compName to name of compRef
                    set compWidth to width of compRef
                    set compHeight to height of compRef
                    set pixelAspect to pixel aspect ratio of compRef
                    set frameDuration to frame duration of compRef
                    set frameRate to 1.0 / frameDuration
                    set startTime to start time of compRef
                    set duration to duration of compRef
                    set startFrame to round (startTime * frameRate)
                    set endFrame to round ((startTime + duration) * frameRate) - 1
                    set frameRange to (startFrame as string) & "-" & (endFrame as string)

                    set compInfo to {{}}
                    set compInfo to compInfo & {{name:compName}}
                    set compInfo to compInfo & {{width:compWidth}}
                    set compInfo to compInfo & {{height:compHeight}}
                    set compInfo to compInfo & {{pixelAspect:pixelAspect}}
                    set compInfo to compInfo & {{frameRate:frameRate}}
                    set compInfo to compInfo & {{startFrame:startFrame}}
                    set compInfo to compInfo & {{endFrame:endFrame}}
                    set compInfo to compInfo & {{frameRange:frameRange}}
                    set compInfo to compInfo & {{duration:duration}}

                    -- Get layer count
                    set layerCount to count of layers of compRef
                    set compInfo to compInfo & {{layerCount:layerCount}}

                    -- Get used layers count
                    set usedLayers to 0
                    repeat with i from 1 to layerCount
                        set layerRef to layer i of compRef
                        try
                            if enabled of layerRef then
                                set usedLayers to usedLayers + 1
                            end if
                        end try
                    end repeat
                    set compInfo to compInfo & {{usedLayers:usedLayers}}

                    return my jsonify(compInfo)
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell

            on jsonify(compInfo)
                set jsonStr to "{"
                set firstItem to true
                set keyList to {"name", "width", "height", "pixelAspect", ¬
                    "frameRate", "startFrame", "endFrame", "frameRange", ¬
                    "duration", "layerCount", "usedLayers"}
                repeat with key in keyList
                    if not firstItem then
                        set jsonStr to jsonStr & ", "
                    end if
                    set firstItem to false
                    set value to compInfo's key

                    if key is "name" then
                        set jsonStr to jsonStr & "\\"name\\"" & ": \\"" & value & "\\""
                    else if key is "frameRange" then
                        set jsonStr to jsonStr & "\\"frameRange\\"" & ": \\"" & value & "\\""
                    else
                        set jsonStr to jsonStr & "\\"" & key & "\\"" & ": " & value
                    end if
                end repeat
                set jsonStr to jsonStr & "}"
                return jsonStr
            end jsonify
            '''

            scpt = apple_script_template.format(comp_id=compId)

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Error"):
                self.core.popup(f"Error getting composition info:\n{result}")
                return

            try:
                comp_info = json.loads(result)
            except json.JSONDecodeError:
                self.core.popup(f"Failed to parse composition info:\n{result}")
                return

            # Create info dialog
            dialog = QDialog(self.tracker.dlg_footage)
            dialog.setWindowTitle(f"Composition Info - {compName}")
            dialog.resize(500, 600)
            dialog.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

            layout = QVBoxLayout()
            dialog.setLayout(layout)

            # Title
            title = QLabel(f"<h2>{comp_info.get('name', 'Unknown')}</h2>")
            title.setAlignment(Qt.AlignCenter)
            layout.addWidget(title)

            # Basic info
            info_text = QTextEdit()
            info_text.setReadOnly(True)

            info_content = f"""
<b>Composition Settings:</b><br>
• Dimensions: {comp_info.get('width', 'N/A')} x {comp_info.get('height', 'N/A')}<br>
• Pixel Aspect Ratio: {comp_info.get('pixelAspect', 'N/A')}<br>
• Frame Rate: {comp_info.get('frameRate', 'N/A')} fps<br>
• Frame Range: {comp_info.get('frameRange', 'N/A')}<br>
• Duration: {comp_info.get('duration', 'N/A')} seconds<br><br>

<b>Layers:</b><br>
• Total Layers: {comp_info.get('layerCount', 'N/A')}<br>
• Used Layers: {comp_info.get('usedLayers', 'N/A')}<br>
• Unused Layers: {comp_info.get('layerCount', 0) - comp_info.get('usedLayers', 0)}<br>
            """

            # Add Kitsu comparison if available
            if kitsu_shot_data:
                frame_range = kitsu_shot_data.get('frameRange', 'N/A')
                kitsu_fps = kitsu_shot_data.get('fps', 'N/A')
                kitsu_info = (
                    f"<br><b>Kitsu Shot Data:</b><br>"
                    f"• Expected Frame Range: {frame_range}<br>"
                    f"• Expected FPS: {kitsu_fps}<br>"
                )
                info_content += kitsu_info

            info_text.setHtml(info_content)
            layout.addWidget(info_text)

            # Close button
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.close)
            layout.addWidget(close_button)

            dialog.exec_()

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing composition info:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def showRawCompInfo(self, compId, compName):
        """Show raw composition information without calculations"""
        try:
            # Create JavaScript/ExtendScript to get raw composition info
            scpt = f'''
            var compId = {compId};
            var compName = "{compName}";

            if (app.project && app.project.numItems > 0) {{
                var comp = app.project.itemByID(compId);
                if (comp && comp instanceof CompItem) {{
                    try {{
                        var compInfo = compName + "\\n";
                        compInfo += "ID: " + compId + "\\n";
                        compInfo += "Width: " + comp.width + "\\n";
                        compInfo += "Height: " + comp.height + "\\n";
                        compInfo += "Pixel Aspect: " + comp.pixelAspect + "\\n";
                        compInfo += "Frame Duration: " + comp.frameDuration + "\\n";
                        compInfo += "Start Time: " + comp.startTime + "\\n";
                        compInfo += "Duration: " + comp.duration + "\\n";
                        compInfo += "Display Start Time: " + comp.displayStartTime + "\\n";
                        compInfo += "Display Start Frame: " + comp.displayStartFrame + "\\n";
                        compInfo += "Frame Rate: " + comp.frameRate + "\\n";
                        compInfo += "Work Area Start: " + comp.workAreaStart + "\\n";
                        compInfo += "Work Area Duration: " + comp.workAreaDuration + "\\n";
                        compInfo += "Layer Count: " + comp.numLayers + "\\n";

                        compInfo;
                    }} catch (e) {{
                        "Error: " + e.toString();
                    }}
                }} else {{
                    "Error: Composition not found";
                }}
            }} else {{
                "Error: No project open";
            }}
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            # Handle result that might be bytes or string
            if isinstance(result, bytes):
                result = result.decode('utf-8')

            if result.startswith("Error"):
                self.core.popup(f"Error getting raw composition info:\n{result}")
                return

            # Show raw info dialog
            self.tracker.showSelectableMessage(f"Raw Composition Info - {compName}", result)

        except Exception as e:
            import traceback
            self.core.popup(f"Error showing raw composition info:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def revealMultipleComps(self, comp_items):
        """Reveal multiple compositions in the project panel"""
        try:
            if not comp_items:
                return

            comp_ids = []
            for item in comp_items:
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'comp':
                    comp_ids.append(userData.get('id'))

            if not comp_ids:
                self.core.popup("No valid compositions selected")
                return

            # Create AppleScript to select multiple compositions
            ids_list = ", ".join([str(cid) for cid in comp_ids])
            scpt = f'''
            tell application "Adobe After Effects 2024"
                try
                    set compRefs to {{}}
                    repeat with compID in {{{ids_list}}}
                        try
                            set end of compRefs to item id compID of project 1
                        end try
                    end repeat

                    if count of compRefs > 0 then
                        set selection of project 1 to compRefs
                        -- Scroll to first composition
                        set firstComp to item 1 of compRefs
                        reveal firstComp in project 1
                        return "Success: Revealed " & (count of compRefs as string) & " compositions"
                    else
                        return "Error: No valid compositions found"
                    end if
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Success"):
                self.core.popup(f"Successfully revealed {len(comp_ids)} compositions in project panel")
            else:
                self.core.popup(f"Error revealing compositions:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error revealing compositions:\n{str(e)}\n\n{traceback.format_exc()}")

    # Multiple composition sync methods
    def setMultipleCompFrameRangesFromKitsu(self, comp_items, kitsu_frame_range):
        """Set frame ranges for multiple compositions from Kitsu data"""
        try:
            if not comp_items or not kitsu_frame_range:
                return

            comp_ids = []
            for item in comp_items:
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'comp':
                    comp_ids.append(userData.get('id'))

            if not comp_ids:
                self.core.popup("No valid compositions selected")
                return

            # Parse the frame range
            if "-" in kitsu_frame_range:
                frame_parts = kitsu_frame_range.split("-")
                start_frame = frame_parts[0].strip()
                end_frame = frame_parts[1].split()[0].strip()
            else:
                self.core.popup(f"Invalid Kitsu frame range format: {kitsu_frame_range}")
                return

            # Create AppleScript to set frame ranges for multiple compositions
            ids_list = ", ".join([str(cid) for cid in comp_ids])
            scpt = f'''
            tell application "Adobe After Effects 2024"
                try
                    set successCount to 0
                    repeat with compID in {{{ids_list}}}
                        try
                            set compRef to item id compID of project 1
                            set frameRate to frame duration of compRef
                            set frameRate to 1.0 / frameRate
                            set startFrame to {start_frame}
                            set endFrame to {end_frame}
                            set duration to (endFrame - startFrame + 1) / frameRate

                            set frameRate of compRef to 1.0 / frameRate
                            set start time of compRef to startFrame / frameRate
                            set duration of compRef to duration
                            set successCount to successCount + 1
                        end try
                    end repeat

                    return "Success: Updated " & (successCount as string) & " compositions"
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Success"):
                self.core.popup(f"Successfully set frame range for compositions to {kitsu_frame_range}\n{result}")
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
            else:
                self.core.popup(f"Error setting frame ranges:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting multiple frame ranges:\n{str(e)}\n\n{traceback.format_exc()}")

    def setMultipleCompFPSFromKitsu(self, comp_items, kitsu_fps):
        """Set FPS for multiple compositions from Kitsu data"""
        try:
            if not comp_items or not kitsu_fps:
                return

            comp_ids = []
            for item in comp_items:
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'comp':
                    comp_ids.append(userData.get('id'))

            if not comp_ids:
                self.core.popup("No valid compositions selected")
                return

            # Parse the FPS
            try:
                fps_value = float(kitsu_fps)
            except ValueError:
                self.core.popup(f"Invalid Kitsu FPS format: {kitsu_fps}")
                return

            # Create AppleScript to set FPS for multiple compositions
            ids_list = ", ".join([str(cid) for cid in comp_ids])
            scpt = f'''
            tell application "Adobe After Effects 2024"
                try
                    set successCount to 0
                    repeat with compID in {{{ids_list}}}
                        try
                            set compRef to item id compID of project 1
                            set currentDuration to duration of compRef
                            set currentStart to start time of compRef
                            set frameRate to {fps_value}
                            set frameDuration of compRef to 1.0 / frameRate
                            set duration of compRef to currentDuration
                            set start time of compRef to currentStart
                            set successCount to successCount + 1
                        end try
                    end repeat

                    return "Success: Updated " & (successCount as string) & " compositions"
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Success"):
                self.core.popup(f"Successfully set FPS for compositions to {kitsu_fps} fps\n{result}")
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
            else:
                self.core.popup(f"Error setting FPS:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting multiple FPS:\n{str(e)}\n\n{traceback.format_exc()}")

    def setMultipleCompFromKitsu(self, comp_items, kitsu_frame_range, kitsu_fps):
        """Set both frame range and FPS for multiple compositions from Kitsu data"""
        try:
            if not comp_items or not kitsu_frame_range or not kitsu_fps:
                return

            comp_ids = []
            for item in comp_items:
                userData = item.data(0, Qt.UserRole)
                if userData and userData.get('type') == 'comp':
                    comp_ids.append(userData.get('id'))

            if not comp_ids:
                self.core.popup("No valid compositions selected")
                return

            # Parse the frame range
            if "-" in kitsu_frame_range:
                frame_parts = kitsu_frame_range.split("-")
                start_frame = frame_parts[0].strip()
                end_frame = frame_parts[1].split()[0].strip()
            else:
                self.core.popup(f"Invalid Kitsu frame range format: {kitsu_frame_range}")
                return

            # Parse the FPS
            try:
                fps_value = float(kitsu_fps)
            except ValueError:
                self.core.popup(f"Invalid Kitsu FPS format: {kitsu_fps}")
                return

            # Create AppleScript to set both frame range and FPS for multiple compositions
            ids_list = ", ".join([str(cid) for cid in comp_ids])
            scpt = f'''
            tell application "Adobe After Effects 2024"
                try
                    set successCount to 0
                    repeat with compID in {{{ids_list}}}
                        try
                            set compRef to item id compID of project 1
                            set frameRate to {fps_value}
                            set frameDuration of compRef to 1.0 / frameRate

                            set startFrame to {start_frame}
                            set endFrame to {end_frame}
                            set duration to (endFrame - startFrame + 1) / frameRate

                            set start time of compRef to startFrame / frameRate
                            set duration of compRef to duration
                            set successCount to successCount + 1
                        end try
                    end repeat

                    return "Success: Updated " & (successCount as string) & " compositions"
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Success"):
                self.core.popup(f"Successfully set {kitsu_frame_range} @ {kitsu_fps} fps for compositions\n{result}")
                if hasattr(self.tracker, 'tw_footage'):
                    self.tracker.loadFootageData()
            else:
                self.core.popup(f"Error setting composition properties:\n{result}")

        except Exception as e:
            import traceback
            self.core.popup(f"Error setting multiple compositions from Kitsu:\n{str(e)}\n\n{traceback.format_exc()}")

    def revealCompInProject(self, compId):
        """Reveal composition in After Effects project panel"""
        try:
            scpt = f'''
            tell application "Adobe After Effects 2024"
                try
                    set compRef to item id {compId} of project 1
                    set selection of project 1 to {{compRef}}
                    reveal compRef in project 1
                    return "Success: Revealed composition in project panel"
                on error errMsg
                    return "Error: " & errMsg
                end try
            end tell
            '''

            result = self.main.ae_core.executeAppleScript(scpt)

            if result.startswith("Success"):
                return True  # Success
            else:
                self.core.popup(f"Error revealing composition:\n{result}")
                return False

        except Exception as e:
            import traceback
            self.core.popup(f"Error revealing composition:\n{str(e)}\n\n{traceback.format_exc()}")
            return False

    @err_catcher(name=__name__)
    def removeUnusedFromComp(self, compId, compName):
        """Remove compositions and footage not used by the selected composition"""
        try:
            from qtpy.QtWidgets import QTabWidget, QListWidget, QProgressDialog
            from qtpy.QtCore import Qt
            from qtpy.QtWidgets import QApplication

            # Step 1: Get items used by this comp
            used_items = self._getUsedItemsByComp(compId)
            if not used_items:
                self.core.popup("Could not determine used items for this composition")
                return

            # Step 2: Get unused items
            unused_items = self._getUnusedItems(used_items)

            unused_footage = unused_items.get('footage', {})
            unused_comps = unused_items.get('comps', {})

            # Exclude the selected comp itself
            comp_id_str = str(compId) if not isinstance(compId, str) else compId
            if comp_id_str in unused_comps:
                del unused_comps[comp_id_str]

            # Check if there's anything to remove
            if not unused_footage and not unused_comps:
                QMessageBox.information(
                    self.tracker.dlg_footage,
                    "No Unused Items",
                    f"All items in the project are used by '{compName}'.\n\nNothing to remove."
                )
                return

            # Step 3: Show confirmation dialog
            reply = self._showRemoveUnusedDialog(unused_footage, unused_comps, compName)
            if reply != QDialog.Accepted:
                return

            # Step 4: Remove items with progress
            self._executeRemoval(unused_footage, unused_comps)

            # Step 5: Refresh tree
            if hasattr(self.tracker, 'tw_footage'):
                self.tracker.loadFootageData()

            # Show success message
            QMessageBox.information(
                self.tracker.dlg_footage,
                "Removal Complete",
                f"Successfully removed:\n\n"
                f"- {len(unused_comps)} composition(s)\n"
                f"- {len(unused_footage)} footage item(s)\n\n"
                "The footage tracker has been refreshed."
            )

        except Exception as e:
            import traceback
            self.core.popup(f"Error removing unused items:\n{str(e)}\n\n{traceback.format_exc()}")

    @err_catcher(name=__name__)
    def _getUsedItemsByComp(self, compId):
        """Get all footage and comps used by the selected composition (recursive for precomps)"""
        scpt = f'''
        var compId = {compId};
        var usedItems = {{
            footage: {{}},
            comps: {{}}
        }};
        var checkedComps = {{}};

        function checkComp(comp) {{
            if (checkedComps[comp.id]) return;
            checkedComps[comp.id] = true;

            for (var i = 1; i <= comp.numLayers; i++) {{
                try {{
                    var layer = comp.layer(i);
                    if (layer.source) {{
                        if (layer.source instanceof FootageItem) {{
                            usedItems.footage[layer.source.id] = layer.source.name;
                        }} else if (layer.source instanceof CompItem) {{
                            usedItems.comps[layer.source.id] = layer.source.name;
                            // Recursively check precomps
                            checkComp(layer.source);
                        }}
                    }}
                }} catch(e) {{
                    // Layer may not have source
                }}
            }}
        }}

        if (app.project && app.project.numItems > 0) {{
            var targetComp = app.project.itemByID(compId);
            if (targetComp && targetComp instanceof CompItem) {{
                checkComp(targetComp);
            }}
        }}

        var result = [];
        for (var id in usedItems.footage) {{
            result.push("FOOTAGE:" + id + "::" + usedItems.footage[id]);
        }}
        for (var id in usedItems.comps) {{
            result.push("COMP:" + id + "::" + usedItems.comps[id]);
        }}
        result.join(";;");
        '''

        result = self.main.ae_core.executeAppleScript(scpt)
        if isinstance(result, bytes):
            result = result.decode('utf-8')

        used_items = {'footage': {}, 'comps': {}}

        if result and ';;' in result:
            items = result.split(';;')
            for item in items:
                if '::' in item:
                    type_id, name = item.split('::', 1)
                    if ':' in type_id:
                        item_type, item_id = type_id.split(':', 1)
                        if item_type == 'FOOTAGE':
                            used_items['footage'][item_id] = name
                        elif item_type == 'COMP':
                            used_items['comps'][item_id] = name

        return used_items

    @err_catcher(name=__name__)
    def _getUnusedItems(self, used_items):
        """Get all items in project that are NOT used"""
        # Convert used items to strings for ExtendScript comparison
        used_footage_ids = list(used_items['footage'].keys())
        used_comp_ids = list(used_items['comps'].keys())

        footage_array = ",".join([str(fid) for fid in used_footage_ids])
        comp_array = ",".join([str(cid) for cid in used_comp_ids])

        scpt = f'''
        var usedFootageIds = [{footage_array}];
        var usedCompIds = [{comp_array}];
        var usedFootage = {{}};
        var usedComps = {{}};

        for (var i = 0; i < usedFootageIds.length; i++) {{
            usedFootage[usedFootageIds[i].toString()] = true;
        }}
        for (var i = 0; i < usedCompIds.length; i++) {{
            usedComps[usedCompIds[i].toString()] = true;
        }}

        var unusedItems = [];

        for (var i = 1; i <= app.project.numItems; i++) {{
            try {{
                var item = app.project.item(i);
                var idStr = item.id.toString();

                if (item instanceof FootageItem) {{
                    if (!usedFootage[idStr]) {{
                        unusedItems.push("FOOTAGE:" + item.id + "::" + item.name);
                    }}
                }} else if (item instanceof CompItem) {{
                    if (!usedComps[idStr]) {{
                        unusedItems.push("COMP:" + item.id + "::" + item.name);
                    }}
                }}
            }} catch(e) {{
                // Item may have been deleted
            }}
        }}

        unusedItems.join(";;");
        '''

        result = self.main.ae_core.executeAppleScript(scpt)
        if isinstance(result, bytes):
            result = result.decode('utf-8')

        unused_items = {'footage': {}, 'comps': {}}

        if result and ';;' in result:
            items = result.split(';;')
            for item in items:
                if '::' in item:
                    type_id, name = item.split('::', 1)
                    if ':' in type_id:
                        item_type, item_id = type_id.split(':', 1)
                        if item_type == 'FOOTAGE':
                            unused_items['footage'][item_id] = name
                        elif item_type == 'COMP':
                            unused_items['comps'][item_id] = name

        return unused_items

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
            f"<p style='color: red;'><b>This action cannot be undone.</b></p>"
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
    def _executeRemoval(self, unused_footage, unused_comps):
        """Execute the removal with progress dialog"""
        from qtpy.QtWidgets import QProgressDialog
        from qtpy.QtCore import Qt
        from qtpy.QtWidgets import QApplication

        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None

        total_items = len(unused_footage) + len(unused_comps)
        progress = QProgressDialog(
            f"Removing {total_items} unused items...",
            "Cancel",
            0,
            total_items,
            parent
        )
        progress.setWindowTitle("Removing Unused Items")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        QApplication.processEvents()

        removed_count = 0
        errors = []

        # Remove compositions first (to avoid dependency issues)
        if unused_comps:
            progress.setLabelText(f"Removing compositions (0/{len(unused_comps)})...")
            QApplication.processEvents()

            comp_ids = list(unused_comps.keys())
            result = self._removeCompsFromProject(comp_ids, progress, removed_count)
            removed_count, comp_errors = result
            errors.extend(comp_errors)

        # Remove footage
        if unused_footage:
            progress.setLabelText(f"Removing footage (0/{len(unused_footage)})...")
            QApplication.processEvents()

            footage_ids = list(unused_footage.keys())
            result = self._removeFootageFromProject(footage_ids, progress, removed_count)
            removed_count, footage_errors = result
            errors.extend(footage_errors)

        progress.close()

        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            self.core.popup(f"Removal completed with some errors:\n{error_msg}")

    @err_catcher(name=__name__)
    def _removeCompsFromProject(self, comp_ids, progress, start_count):
        """Remove compositions from project"""
        ids_array = ",".join([str(cid) for cid in comp_ids])
        removed_count = start_count
        errors = []

        scpt = f'''
        var compIds = [{ids_array}];
        var results = [];

        for (var i = 0; i < compIds.length; i++) {{
            try {{
                var item = app.project.itemByID(compIds[i]);
                if (item && item instanceof CompItem) {{
                    item.remove();
                    results.push("SUCCESS:" + compIds[i]);
                }} else {{
                    results.push("NOT_FOUND:" + compIds[i]);
                }}
            }} catch(e) {{
                results.push("ERROR:" + compIds[i] + "::" + e.toString());
            }}
        }}

        results.join(";;");
        '''

        result = self.main.ae_core.executeAppleScript(scpt)
        if isinstance(result, bytes):
            result = result.decode('utf-8')

        if result:
            items = result.split(';;')
            for i, item in enumerate(items):
                progress.setValue(removed_count + i + 1)
                from qtpy.QtWidgets import QApplication
                QApplication.processEvents()

                if item.startswith('ERROR:'):
                    parts = item.split('::', 1)
                    if len(parts) > 1:
                        errors.append(f"Failed to remove comp {parts[0][6:]}: {parts[1]}")

        return removed_count + len(comp_ids), errors

    @err_catcher(name=__name__)
    def _removeFootageFromProject(self, footage_ids, progress, start_count):
        """Remove footage from project"""
        ids_array = ",".join([str(fid) for fid in footage_ids])
        removed_count = start_count
        errors = []

        scpt = f'''
        var footageIds = [{ids_array}];
        var results = [];

        for (var i = 0; i < footageIds.length; i++) {{
            try {{
                var item = app.project.itemByID(footageIds[i]);
                if (item && item instanceof FootageItem) {{
                    item.remove();
                    results.push("SUCCESS:" + footageIds[i]);
                }} else {{
                    results.push("NOT_FOUND:" + footageIds[i]);
                }}
            }} catch(e) {{
                results.push("ERROR:" + footageIds[i] + "::" + e.toString());
            }}
        }}

        results.join(";;");
        '''

        result = self.main.ae_core.executeAppleScript(scpt)
        if isinstance(result, bytes):
            result = result.decode('utf-8')

        if result:
            items = result.split(';;')
            for i, item in enumerate(items):
                progress.setValue(removed_count + i + 1)
                from qtpy.QtWidgets import QApplication
                QApplication.processEvents()

                if item.startswith('ERROR:'):
                    parts = item.split('::', 1)
                    if len(parts) > 1:
                        errors.append(f"Failed to remove footage {parts[0][6:]}: {parts[1]}")

        return removed_count + len(footage_ids), errors