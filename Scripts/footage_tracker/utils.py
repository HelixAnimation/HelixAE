# -*- coding: utf-8 -*-
"""
Path and Footage Utilities
"""

import os
import re


class FootageUtils:
    """Utility functions for footage path parsing and manipulation"""
    
    @staticmethod
    def parseFootagePath(path):
        """Extract version info from footage file path"""
        try:
            pathParts = path.replace('\\', '/').split('/')

            # Find version folder (e.g., v0023, v0003 (mp4), v0003 (mov))
            currentVersionFull = None
            currentVersionBase = None
            versionIndex = -1
            for i, part in enumerate(pathParts):
                if part.startswith('v') and len(part) >= 5 and part[1:5].isdigit():
                    # Extract base version (v0003) ignoring suffix like " (mp4)"
                    baseVersionMatch = re.match(r'(v\d+)', part)
                    if baseVersionMatch:
                        currentVersionBase = baseVersionMatch.group(1)
                        currentVersionFull = part
                    versionIndex = i
                    break

            if not currentVersionBase:
                # For non-versioned footage (resources, references, etc.), create a dummy version
                return {
                    'currentVersion': 'v0000',
                    'latestVersion': 'v0000',
                    'currentVersionFull': 'v0000',
                    'allVersions': ['v0000'],
                    'task': os.path.basename(os.path.dirname(path)) if os.path.dirname(path) else 'Unknown'
                }

            # Get task name (parent of version folder)
            task = pathParts[versionIndex - 1] if versionIndex > 0 else "Unknown"

            # Find all versions in the same task folder
            # Normalize path for proper OS compatibility
            versionDir = '/'.join(pathParts[:versionIndex])
            # Convert forward slashes to backslashes on Windows for os.path.exists
            if os.name == 'nt':
                import platform
                if platform.system() == "Windows":
                    # Handle Windows paths including drive letters
                    versionDir = versionDir.replace('/', '\\')
            allVersions = []  # Full folder names with suffixes for dropdown
            allVersionsBase = set()  # Base versions for finding latest

            if os.path.exists(versionDir):
                try:
                    # Custom sort: base version first, then suffixes alphabetically, within each version group
                    def versionSortKey(versionFolder):
                        """Sort key for version folders: v0003 < v0003 (mp4) < v0003 (mov) < v0002"""
                        match = re.match(r'(v\d+)(.*)', versionFolder)
                        if match:
                            baseVer = match.group(1)  # e.g., "v0003"
                            suffix = match.group(2) or ''  # e.g., " (mp4)" or '' for base version

                            # Extract version number for descending order (v0003 > v0002)
                            verNum = int(baseVer[1:])  # Extract number from "v0003" -> 3

                            # Base version (no suffix) should come first within each version group
                            # 0 for base version, 1 for versions with suffix
                            hasSuffix = 0 if suffix == '' else 1

                            # Return tuple: (-versionNum for descending, hasSuffix, suffix for alphabetical)
                            return (-verNum, hasSuffix, suffix)
                        return (0, 0, versionFolder)  # Fallback for non-matching patterns

                    versionItems = []
                    for item in os.listdir(versionDir):
                        if item.startswith('v') and len(item) >= 5 and item[1:5].isdigit():
                            # Extract base version (v0003) ignoring suffix like " (mp4)"
                            baseVersionMatch = re.match(r'(v\d+)', item)
                            if baseVersionMatch:
                                baseVersion = baseVersionMatch.group(1)
                                # Check if this version folder contains actual footage files
                                if FootageUtils.versionHasFootage(os.path.join(versionDir, item)):
                                    versionItems.append(item)  # Collect items

                    # Sort using custom key
                    for item in sorted(versionItems, key=versionSortKey):
                        baseVersionMatch = re.match(r'(v\d+)', item)
                        if baseVersionMatch:
                            baseVersion = baseVersionMatch.group(1)
                            allVersions.append(item)  # Keep full name for dropdown
                            allVersionsBase.add(baseVersion)  # Track base version

                except Exception as e:
                    # If listing fails, fall back to current version
                    import sys
                    print(f"[DEBUG] Error listing version directory {versionDir}: {e}", file=sys.stderr)
                    allVersions = [currentVersionFull]
                    allVersionsBase = {currentVersionBase}

            # Find latest base version (e.g., v0003 > v0002)
            latestVersionBase = max(allVersionsBase) if allVersionsBase else currentVersionBase

            return {
                'currentVersion': currentVersionBase,  # Base version for status check
                'latestVersion': latestVersionBase,    # Base version for comparison
                'currentVersionFull': currentVersionFull,  # Full folder name for dropdown
                'allVersions': allVersions,  # Full folder names for dropdown menu
                'task': task
            }

        except Exception as e:
            return None

    @staticmethod
    def extractHierarchy(path, name):
        """Extract Shot/Identifier/AOV from path or filename"""
        try:
            pathParts = path.replace('\\', '/').split('/')

            shot = "Unknown Shot"
            identifier = "Unknown Identifier"
            aov = "Unknown AOV"
            group = None  # To determine if this is Resources or External

            # Determine folder type first
            folder_type = FootageUtils.detectFolderType(path)

            # Only extract shot/identifier/aov for renders
            if folder_type in ['01_3D_Renders', '02_2D_Renders']:
                # Find the shot folder (e.g., SH010)
                shotIndex = -1
                sequenceIndex = -1
                for i, part in enumerate(pathParts):
                    partLower = part.lower()
                    # Check if this looks like a shot folder (SH010, sh010, etc.)
                    if re.match(r'sh\d+', partLower):
                        shotIndex = i
                        # Check if the previous folder is a sequence (CH09, SQ01, etc.)
                        if i > 0:
                            prevPart = pathParts[i - 1]
                            # Check for sequence patterns: CH##, SQ##, etc.
                            if re.match(r'(ch|sq|ep)\d+', prevPart.lower()):
                                sequenceIndex = i - 1
                        break

                # Build the shot name as SEQUENCE-SHOT (e.g., CH09-SH010)
                if shotIndex != -1:
                    if sequenceIndex != -1:
                        shot = f"{pathParts[sequenceIndex]}-{pathParts[shotIndex]}"
                    else:
                        shot = pathParts[shotIndex]

                # Find version folder
                versionIndex = -1
                for i, part in enumerate(pathParts):
                    if re.match(r'v\d{4}', part):
                        versionIndex = i
                        break

                # Get identifier (folder before version)
                if shotIndex != -1 and versionIndex != -1:
                    if versionIndex > 0:
                        identifier = pathParts[versionIndex - 1]

                # Get AOV (folder after version or from filename)
                if versionIndex != -1 and versionIndex + 1 < len(pathParts):
                    aovFolder = pathParts[versionIndex + 1]
                    if '.' not in aovFolder:
                        aov = aovFolder
                    else:
                        aov = re.split(r'[._]\d{4}', name)[0]
                        aovParts = aov.split('_')
                        if len(aovParts) > 1:
                            aov = aovParts[-1]

            # Set group name based on folder type
            if folder_type == '01_3D_Renders':
                group = "3D Renders"
            elif folder_type == '02_2D_Renders':
                group = "2D Renders"
            elif folder_type == '04_External':
                group = "External"
            elif folder_type == '03_Resources':
                group = "Resources"
            else:
                group = "Resources"

            # Determine hierarchy type and return appropriate data
            if folder_type in ['01_3D_Renders', '02_2D_Renders']:
                # For renders, use the shot/identifier/aov structure
                return shot, identifier, aov, group, 'render'
            else:
                # For Resources/External, preserve folder structure
                relative_path, group_folder_type = FootageUtils.extractPreservedStructure(pathParts, folder_type)
                if relative_path:
                    return None, relative_path, None, group, 'preserved'
                else:
                    # Fallback: use filename as identifier
                    return None, os.path.splitext(name)[0], None, group, 'preserved'

        except Exception as e:
            return "Unknown Shot", "Unknown Identifier", name, "Resources", "render"
    
    @staticmethod
    def getFrameRangeFromFolder(filePath):
        """Scan the folder to find the actual frame range of the sequence.
        Handles various naming patterns for both 3D and 2D renders."""
        try:
            filePath = filePath.replace('\\', '/')
            if not os.path.splitext(filePath)[1]:
                folderPath = filePath
                if os.path.exists(folderPath):
                    files = [f for f in os.listdir(folderPath) if os.path.isfile(os.path.join(folderPath, f))]
                    if files:
                        fileName = files[0]
                    else:
                        return "N/A"
                else:
                    return "N/A"
            else:
                folderPath = os.path.dirname(filePath)
                fileName = os.path.basename(filePath)

            if not os.path.exists(folderPath):
                return "N/A"

            # Extract base name - more flexible patterns for 3D and 2D renders
            # Try multiple patterns:
            # 1. Standard pattern: name.####.ext or name_####.ext
            baseMatch = re.match(r'^(.+?)[._](\d{3,6})\.[^.]+$', fileName)

            # 2. Pattern for files with multiple separators: shot_playblast_v001_####.ext
            if not baseMatch:
                # Find the last frame number in the filename
                baseMatch = re.match(r'^(.+?)[._](\d{3,6})\.[^.]+$', fileName)

            if not baseMatch:
                return "N/A"

            baseName = baseMatch.group(1)
            frameNumbers = []

            for file in os.listdir(folderPath):
                # More flexible matching - look for frame numbers in various positions
                # Match frame number at end of filename before extension (3-6 digits)
                frameMatch = re.search(r'[._](\d{3,6})\.[^.]+$', file)
                if frameMatch:
                    frameNumbers.append(int(frameMatch.group(1)))

            if frameNumbers:
                frameNumbers.sort()
                return f"{frameNumbers[0]}-{frameNumbers[-1]}"
            else:
                return "N/A"
        except Exception as e:
            return "N/A"
    
    @staticmethod
    def detectAlphaType(filename, path):
        """Detect alpha channel type - defaults to Straight for most render formats"""
        if any(ext in filename.lower() for ext in ['.exr', '.png', '.tif', '.tiff']):
            return "Straight"
        elif any(ext in filename.lower() for ext in ['.jpg', '.jpeg']):
            return "None"
        return "Straight"

    @staticmethod
    def extractPreservedStructure(pathParts, folder_type):
        """Extract folder structure for Resources and External groups"""
        try:
            # Find the group index in the path
            group_map = {
                '03_Resources': ['04_resources', 'resources'],
                '04_External': []  # External uses drive detection
            }

            group_keywords = group_map.get(folder_type, ['resources'])

            # Build relative path from group folder onwards
            if folder_type == '04_External':
                # For external, include all folders after Z:
                # Find the Z: drive first
                z_index = -1
                for i, part in enumerate(pathParts):
                    if part.lower().startswith('z:'):
                        z_index = i
                        break

                if z_index == -1:
                    return None, folder_type

                # Include all folders after Z:
                relative_parts = pathParts[z_index + 1:] if z_index + 1 < len(pathParts) else []
            else:
                # For resources, find the group folder
                group_index = -1
                for i, part in enumerate(pathParts):
                    part_lower = part.lower()
                    if any(keyword in part_lower for keyword in group_keywords):
                        group_index = i
                        break

                if group_index == -1:
                    return None, folder_type

                # Include folders after the group folder
                relative_parts = pathParts[group_index + 1:] if group_index + 1 < len(pathParts) else []

            # Join with forward slashes for consistency
            relative_path = '/'.join(relative_parts) if relative_parts else ''

            return relative_path, folder_type

        except Exception as e:
            return None, folder_type

    @staticmethod
    def detectFolderType(path):
        """Detect which category folder a file belongs to"""
        path_lower = path.lower()

        # Normalize path separators
        normalized_path = path_lower.replace('\\', '/')

        # EXACT PATH MATCHING FROM TreePlan.md
        # 3D Renders: X:/Halloween_2025/03_Production/Shots/SQ01/SH010/Renders/3dRender/Lighting/v0010/beauty
        if '/renders/3drender/' in normalized_path:
            return '01_3D_Renders'

        # 2D Renders: X:/Halloween_2025/03_Production/Shots/SQ01/SH010/Renders/2dRender/HighRes/v0004
        elif '/renders/2drender/' in normalized_path:
            return '02_2D_Renders'

        # Playblasts: X:/Laughlin_CLEAR_and_BBB/03_Production/Shots/SQ02/SH010/Playblasts/Layout/v0004
        # Treat Playblasts as 2D Renders
        elif '/playblasts/' in normalized_path:
            return '02_2D_Renders'

        # Resources: X:/Halloween_2025/04_Resources/Libraries/PolyHaven/hdri/rogland_clear_night_4k.hdr
        elif '/04_resources/' in normalized_path:
            return '03_Resources'

        # External: Z:/Library/StockFootage/iStock-Prescription Pills Fall in a Pile.mov
        elif normalized_path.startswith('z:/'):
            return '04_External'

        # Fallback patterns - check folder names
        else:
            # Check each part of the path
            path_parts = normalized_path.split('/')

            for i, part in enumerate(path_parts):
                # Check for 3D Render patterns
                if part == '3drender' or part == '3drenders':
                    return '01_3D_Renders'

                # Check for 2D Render patterns
                elif part == '2drender' or part == '2drenders':
                    return '02_2D_Renders'

                # Check for Playblasts (treat as 2D Renders)
                elif part == 'playblasts' or part == 'playblast':
                    return '02_2D_Renders'

                # Check for Resources folder (04_Resources)
                elif part == '04_resources' or part == 'resources':
                    return '03_Resources'

                # Check for External indicators
                elif part == 'stockfootage' or part == 'library' and i > 0 and path_parts[i-1].lower().startswith('z'):
                    return '04_External'

            # Final fallback - check if path contains render keywords
            if any(keyword in normalized_path for keyword in ['renders/3d', '3d/render', 'renders3d']):
                return '01_3D_Renders'
            elif any(keyword in normalized_path for keyword in [
                'renders/2d', '2d/render', 'renders2d', 'playblasts/', 'playblast/'
            ]):
                return '02_2D_Renders'
            elif any(keyword in normalized_path for keyword in [
                'texture', 'background', 'bg', 'library', 'hdr', 'hdri'
            ]):
                return '03_Resources'
            elif any(keyword in normalized_path for keyword in ['stock', 'external']):
                return '04_External'

            # Default to Resources if nothing matches
            return '03_Resources'
    
    @staticmethod
    def versionHasFootage(versionPath):
        """Check if a version folder contains valid footage files"""
        try:
            if not os.path.exists(versionPath) or not os.path.isdir(versionPath):
                return False

            # Look for footage files in the version folder and its subdirectories
            footageExtensions = [
                '.exr', '.jpg', '.jpeg', '.png', '.tif', '.tiff',
                '.hdr', '.pic', '.tga', '.bmp', '.psd', '.ai',
                '.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv'
            ]

            # Check direct files in version folder
            for item in os.listdir(versionPath):
                itemPath = os.path.join(versionPath, item)
                if os.path.isfile(itemPath):
                    # Check if it's a supported footage file
                    if any(item.lower().endswith(ext) for ext in footageExtensions):
                        return True
                elif os.path.isdir(itemPath):
                    # Check subdirectories for footage files
                    for subitem in os.listdir(itemPath):
                        subitemPath = os.path.join(itemPath, subitem)
                        if os.path.isfile(subitemPath):
                            if any(subitem.lower().endswith(ext) for ext in footageExtensions):
                                return True

            return False
        except Exception:
            return False

    @staticmethod
    def isSequence(path):
        """Check if a path represents an image sequence"""
        try:
            # If path is a folder, check if it contains sequence files
            if os.path.isdir(path):
                files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
                # Check if any files have frame numbers
                for f in files:
                    if re.search(r'[._]\d{4,5}[._]', f):
                        return True
                return False
            
            # Check parent directory if file doesn't exist
            parentDir = os.path.dirname(path)
            if not os.path.exists(path) and os.path.isdir(parentDir):
                # Check if parent directory has sequence files
                files = [f for f in os.listdir(parentDir) if os.path.isfile(os.path.join(parentDir, f))]
                for f in files:
                    if re.search(r'[._]\d{4,5}[._]', f):
                        return True
                return False
            
            # Check if filename has frame numbers
            filename = os.path.basename(path)
            # Look for patterns like _1001.exr, .1001.exr, _####.exr, etc.
            if re.search(r'[._]\d{4,5}[._]', filename) or re.search(r'[._]#+[._]', filename):
                return True
            
            return False
        except Exception:
            return False
    
    @staticmethod
    def ensureSequencePath(path):
        """Ensure path points to the first frame of a sequence or the folder"""
        _footage_exts = {
            '.exr', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.tga', '.bmp', '.psd', '.hdr', '.pic', '.ai',
            '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'
        }
        try:
            # If it's already a directory that exists and contains sequences, find first frame
            if os.path.isdir(path):
                files = sorted([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
                for f in files:
                    if re.search(r'[._]\d{4,5}[._]', f) and any(f.lower().endswith(ext) for ext in _footage_exts):
                        return os.path.join(path, f)
                # No sequence found, return directory path
                return path

            # If the exact path exists and is a file, return it
            if os.path.isfile(path):
                return path

            # Extract base info from path
            parentDir = os.path.dirname(path)
            filename = os.path.basename(path)

            # If parent directory doesn't exist, return original path
            if not os.path.isdir(parentDir):
                return path

            # Try to find matching sequence files (footage only)
            files = sorted([
                f for f in os.listdir(parentDir)
                if os.path.isfile(os.path.join(parentDir, f))
                and any(f.lower().endswith(ext) for ext in _footage_exts)
            ])
            if not files:
                return path

            # Extract base name (everything before frame number)
            baseMatch = re.match(r'^(.+?)[._]?\d{4,5}[._]', filename)
            if baseMatch:
                baseName = baseMatch.group(1)
                # Find files with same base name
                for f in files:
                    if f.startswith(baseName) and re.search(r'[._]\d{4,5}[._]', f):
                        return os.path.join(parentDir, f)

            # If we can't match pattern, return first file with frame numbers
            for f in files:
                if re.search(r'[._]\d{4,5}[._]', f):
                    return os.path.join(parentDir, f)

            # Last resort: return first footage file
            return os.path.join(parentDir, files[0])
        except Exception as e:
            # If anything fails, return original path
            return path
    
    @staticmethod
    def ensureStillPath(path):
        """Ensure path points to a single still image file"""
        _footage_exts = {
            '.exr', '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.tga', '.bmp', '.psd', '.hdr', '.pic', '.ai',
            '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.webm'
        }
        try:
            # If the exact path exists and is a file, return it
            if os.path.isfile(path):
                return path

            # If path is a directory, find a still image (no frame numbers)
            parentDir = path if os.path.isdir(path) else os.path.dirname(path)

            if not os.path.isdir(parentDir):
                return path

            files = [
                f for f in os.listdir(parentDir)
                if os.path.isfile(os.path.join(parentDir, f))
                and any(f.lower().endswith(ext) for ext in _footage_exts)
            ]
            if not files:
                return path

            # Look for files WITHOUT frame numbers
            for f in files:
                if not re.search(r'[._]\d{4,5}[._]', f):
                    fullPath = os.path.join(parentDir, f)
                    if os.path.isfile(fullPath):
                        return fullPath

            # If no still found, return first footage file
            return os.path.join(parentDir, files[0])
        except Exception as e:
            return path
