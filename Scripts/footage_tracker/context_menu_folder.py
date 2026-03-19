# -*- coding: utf-8 -*-
"""
Folder-specific context menu methods: organize, refresh, validate naming, auto-categorize.
"""

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuFolder:
    """Mixin: folder context menu actions"""

    def _organizeFolder(self, folder_name):
        """Handle Organise action for a folder"""
        try:
            print(f"DEBUG: _organizeFolder called for folder: {folder_name}")

            if not hasattr(self.tracker, 'ae_organize_manager'):
                self.core.popup("AE Organization Manager not initialized. Please contact support.")
                return

            self.tracker.ae_organize_manager.organizeFolder(folder_name)

        except Exception as e:
            import traceback
            self.core.popup(f"Error organizing folder {folder_name}:\n{str(e)}\n\n{traceback.format_exc()}")

    def _organizeMultipleFolders(self, folder_names):
        """Handle Organise action for multiple folders"""
        try:
            print(f"DEBUG: _organizeMultipleFolders called for folders: {folder_names}")

            if not hasattr(self.tracker, 'ae_organize_manager'):
                self.core.popup("AE Organization Manager not initialized. Please contact support.")
                return

            self.tracker.ae_organize_manager.organizeMultipleFolders(folder_names)

        except Exception as e:
            import traceback
            self.core.popup(f"Error organizing multiple folders {folder_names}:\n{str(e)}\n\n{traceback.format_exc()}")

    def _refreshComps(self):
        """Refresh the composition list"""
        self.tracker.loadFootageData(preserve_scroll=True)

    def _validateNaming(self, folder_name):
        """Validate naming convention for renders"""
        self.core.popup(f"Naming validation for {folder_name} not yet implemented")

    def _autoCategorizeResources(self):
        """Auto-categorize resources"""
        self.core.popup("Resource auto-categorization not yet implemented")
