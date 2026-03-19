import os
import json
from datetime import datetime
try:
    from PrismUtils.Decorators import err_catcher
except ImportError:
    # Fallback if PrismUtils path is different
    def err_catcher(name):
        def decorator(func):
            def wrapper(*args, **kwargs):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        return None
            return wrapper
        return decorator


@err_catcher(name=__name__)
def generate_archive_info(tracker, filepath, hierarchy=None):
    """
    Generate archive information for the current project.

    Args:
        tracker: The footage tracker instance
        filepath: Path of the saved .aep file
        hierarchy: Optional pre-loaded hierarchy data (if None, will get from tracker)

    Returns:
        dict: Archive information to be written to JSON. Contains:
            - project_file: Path to the saved .aep file
            - generated_timestamp: ISO timestamp
            - aftereffects_version: After Effects version number
            - footage: List of footage entries with parent directory paths
            - source_paths: Sorted list of all render file paths (3D and 2D renders)
            - resource_paths: Sorted list of all resource directory paths
            - external_paths: Sorted list of all external directory paths
    """
    # Get After Effects version
    ae_version = "Unknown"
    try:
        # Try to get version via AppleScript directly
        if hasattr(tracker, 'main') and hasattr(tracker.main, 'ae_core'):
            scpt = """
            if (app.version) {
                app.version;
            } else {
                "Unknown";
            }
            """
            result = tracker.main.ae_core.executeAppleScript(scpt)
            if result:
                # Convert bytes to string if needed
                if isinstance(result, bytes):
                    version_raw = result.decode('utf-8')
                else:
                    version_raw = str(result)
                version_raw = version_raw.strip()

                # Format version to match About dialog style
                # Convert "25.2x131" to "Version 25.2.0 (Build 131)"
                if 'x' in version_raw:
                    main_ver, build = version_raw.split('x')
                    # Add .0 to main version if needed
                    if '.' in main_ver and len(main_ver.split('.')) == 2:
                        main_ver += '.0'
                    ae_version = f"Version {main_ver} (Build {build})"
                else:
                    ae_version = f"Version {version_raw}"
            else:
                ae_version = "Unknown"
    except Exception:
        ae_version = "Unknown"

    # Get footage usage in compositions
    used_footage = get_used_footage_from_comps(tracker)

    # Get stored hierarchy from parameter or tracker
    if hierarchy is None:
        hierarchy = getattr(tracker, '_stored_hierarchy', {})

    # Filter hierarchy to include only used footage
    filtered_footage = []
    render_files = set()  # 3D and 2D renders - actual files
    resource_paths = set()  # Resources - directories
    external_paths = set()  # External - directories

    # The new hierarchy is organized by groups
    for group in ["3D Renders", "2D Renders", "Resources", "External"]:
        if group not in hierarchy:
            continue

        group_data = hierarchy[group]
        if not isinstance(group_data, dict):
            continue

        # Different handling for renders vs preserved
        if group in ["3D Renders", "2D Renders"]:
            # Render groups have shot > identifier structure
            for shot_name, shot_data in group_data.items():
                if not isinstance(shot_data, dict):
                    continue
                for identifier, identifier_data in shot_data.items():
                    if not isinstance(identifier_data, dict):
                        continue
                    for aov, footage_list in identifier_data.items():
                        if not isinstance(footage_list, list):
                            continue
                        for footage_item in footage_list:
                            if not isinstance(footage_item, dict):
                                continue

                            footage_id = footage_item.get('footageId')

                            # Check if this footage is used in any composition
                            if footage_id in used_footage:
                                # Get original path
                                original_path = footage_item.get('path', '')

                                # For renders, add the actual file path (not just the directory)
                                if original_path and os.path.exists(original_path):
                                    render_files.add(original_path)

                                # Get parent directory for the archive entry
                                parent_path = os.path.dirname(original_path) if original_path else ''

                                # Create archive entry
                                archive_entry = {
                                    "id": footage_id,
                                    "name": footage_item.get('name', ''),
                                    "path": parent_path,  # Use parent path for the entry
                                    "shot": shot_name,
                                    "identifier": identifier,
                                    "aov": aov,
                                    "version": {
                                        "current": footage_item.get('versionInfo', {}).get('currentVersion', ''),
                                        "latest": footage_item.get('versionInfo', {}).get('latestVersion', '')
                                    },
                                    "used_in_comps": used_footage[footage_id]
                                }
                                filtered_footage.append(archive_entry)
        else:
            # Resources and External have relative path structure
            for relative_path, footage_list in group_data.items():
                if not isinstance(footage_list, list):
                    continue
                for footage_item in footage_list:
                    if not isinstance(footage_item, dict):
                        continue

                    footage_id = footage_item.get('footageId')

                    # Check if this footage is used in any composition
                    if footage_id in used_footage:
                        # Get original path
                        original_path = footage_item.get('path', '')

                        # Get parent directory
                        parent_path = os.path.dirname(original_path) if original_path else ''

                        # Add to appropriate paths collection (directories)
                        if group == "External":
                            if parent_path:
                                external_paths.add(parent_path)
                        else:  # Resources
                            if parent_path:
                                resource_paths.add(parent_path)

                        # Create archive entry
                        archive_entry = {
                            "id": footage_id,
                            "name": footage_item.get('name', ''),
                            "path": parent_path,
                            "relative_path": relative_path,
                            "group": group,
                            "version": {
                                "current": footage_item.get('versionInfo', {}).get('currentVersion', ''),
                                "latest": footage_item.get('versionInfo', {}).get('latestVersion', '')
                            },
                            "used_in_comps": used_footage[footage_id]
                        }
                        filtered_footage.append(archive_entry)

    # Get all resource files (not just directories) for source_paths
    resource_files = set()  # Store actual resource files
    external_files = set()  # Store actual external files

    # Process Resources group to collect actual files
    if "Resources" in hierarchy:
        resource_group = hierarchy["Resources"]
        if isinstance(resource_group, dict):
            for relative_path, footage_list in resource_group.items():
                if not isinstance(footage_list, list):
                    continue
                for footage_item in footage_list:
                    if not isinstance(footage_item, dict):
                        continue

                    footage_id = footage_item.get('footageId')
                    # Only include if used in compositions
                    if footage_id in used_footage:
                        original_path = footage_item.get('path', '')
                        if original_path and os.path.exists(original_path):
                            resource_files.add(original_path)

    # Process External group to collect actual files
    if "External" in hierarchy:
        external_group = hierarchy["External"]
        if isinstance(external_group, dict):
            for relative_path, footage_list in external_group.items():
                if not isinstance(footage_list, list):
                    continue
                for footage_item in footage_list:
                    if not isinstance(footage_item, dict):
                        continue

                    footage_id = footage_item.get('footageId')
                    # Only include if used in compositions
                    if footage_id in used_footage:
                        original_path = footage_item.get('path', '')
                        if original_path and os.path.exists(original_path):
                            external_files.add(original_path)

    # Separate render files by type
    render_3d_files = set()
    render_2d_files = set()

    # Process 3D Renders
    if "3D Renders" in hierarchy:
        render_3d_group = hierarchy["3D Renders"]
        if isinstance(render_3d_group, dict):
            for shot_name, shot_data in render_3d_group.items():
                if not isinstance(shot_data, dict):
                    continue
                for identifier, identifier_data in shot_data.items():
                    if not isinstance(identifier_data, dict):
                        continue
                    for aov, footage_list in identifier_data.items():
                        if not isinstance(footage_list, list):
                            continue
                        for footage_item in footage_list:
                            if not isinstance(footage_item, dict):
                                continue
                            footage_id = footage_item.get('footageId')
                            if footage_id in used_footage:
                                original_path = footage_item.get('path', '')
                                if original_path and os.path.exists(original_path):
                                    render_3d_files.add(original_path)

    # Process 2D Renders
    if "2D Renders" in hierarchy:
        render_2d_group = hierarchy["2D Renders"]
        if isinstance(render_2d_group, dict):
            for shot_name, shot_data in render_2d_group.items():
                if not isinstance(shot_data, dict):
                    continue
                for identifier, identifier_data in shot_data.items():
                    if not isinstance(identifier_data, dict):
                        continue
                    for aov, footage_list in identifier_data.items():
                        if not isinstance(footage_list, list):
                            continue
                        for footage_item in footage_list:
                            if not isinstance(footage_item, dict):
                                continue
                            footage_id = footage_item.get('footageId')
                            if footage_id in used_footage:
                                original_path = footage_item.get('path', '')
                                if original_path and os.path.exists(original_path):
                                    render_2d_files.add(original_path)

    # Convert sets to sorted lists
    resource_paths_list = sorted(list(resource_paths))  # Keep resource directories for compatibility
    external_paths_list = sorted(list(external_paths))

    # Create final archive data with proper order
    archive_data = {
        "project_file": filepath,
        "generated_timestamp": datetime.utcnow().isoformat() + "Z",
        "aftereffects_version": ae_version,
        "footage": filtered_footage,
        "source_paths": {
            "3d_renders": sorted(list(render_3d_files)),
            "2d_renders": sorted(list(render_2d_files)),
            "resources": sorted(list(resource_files))
        },
        "resource_paths": resource_paths_list  # Resources - directories (kept for compatibility)
    }

    # Add external_paths at the end to ensure it's at the bottom
    archive_data["external_paths"] = sorted(list(external_files))

    return archive_data


@err_catcher(name=__name__)
def get_used_footage_from_comps(tracker):
    """
    Get all footage items that are used in compositions.

    Args:
        tracker: The footage tracker instance

    Returns:
        dict: Mapping of footage IDs to list of composition names
    """
    # Use tree operations to collect footage data
    hierarchy = getattr(tracker, '_stored_hierarchy', {})
    used_footage = {}

    # Get footage usage via AE operations
    try:
        scpt = """
        var usedFootage = {};
        for (var i = 1; i <= app.project.numItems; i++) {
            var item = app.project.item(i);
            if (item instanceof CompItem) {
                for (var j = 1; j <= item.numLayers; j++) {
                    var layer = item.layer(j);
                    if (layer.source && layer.source instanceof FootageItem) {
                        var footageId = layer.source.id;
                        if (!usedFootage[footageId]) {
                            usedFootage[footageId] = [];
                        }
                        if (usedFootage[footageId].indexOf(item.name) == -1) {
                            usedFootage[footageId].push(item.name);
                        }
                    }
                }
            }
        }
        var result = [];
        for (var footageId in usedFootage) {
            var compsString = usedFootage[footageId].join(',');
            result.push(footageId + '::' + compsString);
        }
        result.join(':::');
        """

        result = tracker.main.ae_core.executeAppleScript(scpt)

        # Handle bytes result properly
        result_str = ""
        if result:
            if isinstance(result, bytes):
                result_str = result.decode('utf-8')
            else:
                result_str = str(result)

        if result_str.strip():
            footage_data = result_str.split(':::')
            for item_data in footage_data:
                if item_data.strip():
                    parts = item_data.split('::')
                    if len(parts) >= 2:
                        footage_id = parts[0].strip()
                        comps = parts[1].strip().split(',')
                        used_footage[footage_id] = [comp.strip() for comp in comps if comp.strip()]

        # Also try alternative method if first one fails
        if not used_footage:
            try:
                scpt2 = """
                var result2 = [];
                for (var i = 1; i <= app.project.numItems; i++) {
                    var item = app.project.item(i);
                    if (item instanceof CompItem) {
                        for (var j = 1; j <= item.numLayers; j++) {
                            var layer = item.layer(j);
                            if (layer.source && layer.source instanceof FootageItem) {
                                var footageId = layer.source.id;
                                if (result2.indexOf(footageId) == -1) {
                                    result2.push(footageId);
                                }
                            }
                        }
                    }
                }
                result2.join('::');
                """

                result2 = tracker.main.ae_core.executeAppleScript(scpt2)
                if result2:
                    result2_str = result2.decode('utf-8') if isinstance(result2, bytes) else str(result2)
                    if result2_str.strip():
                        footage_ids = result2_str.split('::')
                        for footage_id in footage_ids:
                            if footage_id.strip():
                                used_footage[footage_id] = []
            except Exception as e2:
                import traceback
                traceback.print_exc()

    except Exception as e:
        import traceback
        traceback.print_exc()

    return used_footage


@err_catcher(name=__name__)
def write_archive_json(data, filepath):
    """
    Write archive data to a JSON file.

    Args:
        data: Dictionary containing archive information
        filepath: Path of the saved .aep file OR the full archive file path

    Returns:
        str: Path of the created JSON file, or None if failed
    """
    try:
        # Ensure filepath is a string, not bytes
        if isinstance(filepath, bytes):
            filepath = filepath.decode('utf-8')
        elif not isinstance(filepath, str):
            filepath = str(filepath)

        # Check if filepath already ends with "_archiveinfo.json"
        if filepath.endswith("_archiveinfo.json"):
            archive_path = filepath
        else:
            # Generate archive info file path from .aep file
            base_path = os.path.splitext(filepath)[0]
            archive_path = base_path + "_archiveinfo.json"

        # Write JSON file with nice formatting (no sort_keys to preserve order)
        with open(archive_path, 'w') as f:
            json.dump(data, f, indent=2)

        return archive_path

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"


@err_catcher(name=__name__)
def create_archive_info_file(tracker, filepath):
    """
    Main function to create archive info file.

    Args:
        tracker: The footage tracker instance
        filepath: Path of the saved .aep file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Generate archive data
        archive_data = generate_archive_info(tracker, filepath)

        # Write to file
        archive_path = write_archive_json(archive_data, filepath)

        if archive_path:
            tracker.core.app.print(f"Archive info created: {archive_path}")
            return True
        else:
            tracker.core.app.print("Failed to create archive info file")
            return False

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False