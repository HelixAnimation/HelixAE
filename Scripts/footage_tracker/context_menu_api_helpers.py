# -*- coding: utf-8 -*-
"""
Prism API helper methods for shot/task/AOV data access.
"""

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuApiHelpers:
    """Mixin: Prism API helper methods"""

    @err_catcher(name=__name__)
    def _getCurrentShotEntity(self):
        """Get the current shot entity from the AE project file"""
        current_file = self.core.getCurrentFileName()
        if not current_file:
            return None

        path_parts = current_file.replace("\\", "/").split("/")

        shots_idx = next((i for i, p in enumerate(path_parts) if p.upper() == "SHOTS"), -1)
        if shots_idx == -1 or shots_idx + 2 >= len(path_parts):
            print(f"[DEBUG] No Shots folder found in path: {current_file}")
            return None

        seq = path_parts[shots_idx + 1]
        shot = path_parts[shots_idx + 2]
        target_shot_name = f"{seq}-{shot}"

        print(f"[DEBUG] Looking for shot: {target_shot_name}")

        try:
            all_shots = self.core.entities.getShots()
            if not all_shots:
                print(f"[DEBUG] No shots found in Prism project")
                return None

            for shot_entity in all_shots:
                shot_name = self.core.entities.getShotName(shot_entity)
                if shot_name == target_shot_name:
                    print(f"[DEBUG] Found matching shot entity: {shot_name}")
                    return shot_entity

            available = [self.core.entities.getShotName(s) for s in all_shots[:5]]
            print(f"[DEBUG] Shot '{target_shot_name}' not found in Prism. Available shots: {available}...")
            return None

        except Exception as e:
            print(f"[DEBUG] Error getting shot entity: {e}")
            return None

    @err_catcher(name=__name__)
    def _getLightingTasksFromAPI(self, shot_entity):
        """Get all lighting tasks from Prism API for current shot"""
        if not shot_entity:
            return []

        context = shot_entity.copy()
        context["mediaType"] = "3drenders"

        all_identifiers = self.core.getTaskNames(
            taskType="3d",
            context=context,
            addDepartments=False
        )

        lighting_tasks = [id for id in all_identifiers
                         if "lighting" in id.lower()]

        return lighting_tasks

    @err_catcher(name=__name__)
    def _getTaskDataFromAPI(self, shot_entity, task_name, latest_only=True):
        """
        Get task data (versions, AOVs, files) from Prism API.
        Returns: {
            'latest_version': version_string,
            'all_versions': [version_dict, ...],
            'aovs': {aov_name: {'version': version_dict, 'files': [paths]}}
        }
        """
        context = shot_entity.copy()
        context["mediaType"] = "3drenders"
        context["identifier"] = task_name

        if latest_only:
            versions = [self.core.mediaProducts.getLatestVersionFromIdentifier(context)]
        else:
            versions = self.core.mediaProducts.getVersionsFromIdentifier(context)

        if not versions or not versions[0]:
            return None

        latest_version = versions[0]
        version_str = latest_version.get("version", "unknown")

        aovs = {}
        try:
            aov_list = self.core.mediaProducts.getAOVsFromVersion(latest_version)
        except Exception:
            aov_list = []

        for aov in aov_list:
            aov_name = aov.get("aov", "main")
            try:
                filepaths = self.core.mediaProducts.getFilesFromContext(aov)
            except Exception:
                filepaths = []

            if filepaths:
                aovs[aov_name] = {
                    'version': latest_version,
                    'files': filepaths
                }

        return {
            'latest_version': version_str,
            'all_versions': versions,
            'aovs': aovs
        }

    @err_catcher(name=__name__)
    def _isAOVAlreadyImported(self, task_name, aov_name):
        """Check if an AOV is already imported in the current project"""
        try:
            current_shot = self.tracker.tree_ops.data_parser.extractCurrentShotFromProject()
            if not current_shot:
                return False

            if '-' in current_shot:
                seq_shot = current_shot
            else:
                seq_shot = current_shot

            footage_name = aov_name

            script = f"""
            var render3dFolder = null, shotFolder = null, taskFolder = null;

            for (var i = 1; i <= app.project.numItems; i++) {{
                if (app.project.item(i) instanceof FolderItem &&
                    app.project.item(i).name === '3D Renders') {{
                    render3dFolder = app.project.item(i);
                    break;
                }}
            }}

            if (render3dFolder) {{
                for (var i = 1; i <= render3dFolder.numItems; i++) {{
                    if (render3dFolder.item(i) instanceof FolderItem &&
                        render3dFolder.item(i).name === '{seq_shot}') {{
                        shotFolder = render3dFolder.item(i);
                        break;
                    }}
                }}
            }}

            if (shotFolder) {{
                for (var i = 1; i <= shotFolder.numItems; i++) {{
                    if (shotFolder.item(i) instanceof FolderItem &&
                        shotFolder.item(i).name === '{task_name}') {{
                        taskFolder = shotFolder.item(i);
                        break;
                    }}
                }}
            }}

            if (taskFolder) {{
                for (var i = 1; i <= taskFolder.numItems; i++) {{
                    var item = taskFolder.item(i);
                    if (item instanceof FootageItem && item.name === '{footage_name}') {{
                        'EXISTS';
                        break;
                    }}
                }}
            }}
            """

            result = self.tracker.main.ae_core.executeAppleScript(script)
            return b'EXISTS' in result

        except Exception:
            return False

    @err_catcher(name=__name__)
    def _getCurrentShotPath(self):
        """Get the shot path from current project file"""
        try:
            current_file = self.core.getCurrentFileName()
            if not current_file:
                return None

            path_parts = current_file.replace("\\", "/").split("/")

            shots_idx = next((i for i, p in enumerate(path_parts) if p.upper() == "SHOTS"), -1)
            if shots_idx == -1 or shots_idx + 2 >= len(path_parts):
                return None

            return "/".join(path_parts[:shots_idx + 3])
        except Exception:
            return None
