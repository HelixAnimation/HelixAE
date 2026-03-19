# -*- coding: utf-8 -*-
"""
Global Dialog Storage - Ensures single instances of dialogs across all plugin contexts
This module-level storage persists across multiple plugin instantiations.
"""

from qtpy.QtWidgets import QDialog

# Global module-level dialog storage
# These variables will persist across all plugin instances
_DIALOGS = {}


def get_dialog(dialog_type):
    """Get existing dialog or return None if it doesn't exist or is invalid"""
    dialog = _DIALOGS.get(dialog_type)

    if dialog is not None:
        try:
            # Check if dialog still exists and hasn't been destroyed
            # Try accessing a Qt property to verify the dialog is still valid
            _ = dialog.windowTitle()
            if not dialog.isHidden():
                return dialog
            else:
                # Dialog exists but is hidden, still return it so it can be shown
                return dialog
        except (RuntimeError, AttributeError, ReferenceError):
            # Dialog was destroyed, clean up
            _DIALOGS[dialog_type] = None
            return None

    return None


def set_dialog(dialog_type, dialog):
    """Store dialog reference and setup cleanup"""
    _DIALOGS[dialog_type] = dialog

    # Clean up when dialog is closed
    if dialog:
        dialog.finished.connect(lambda: cleanup_dialog(dialog_type))


def cleanup_dialog(dialog_type):
    """Clean up dialog reference when dialog is closed"""
    if dialog_type in _DIALOGS:
        _DIALOGS[dialog_type] = None


def has_dialog(dialog_type):
    """Check if dialog exists and is valid"""
    dialog = _DIALOGS.get(dialog_type)
    if dialog is not None:
        try:
            # Try to access a property to check if dialog is still valid
            _ = dialog.windowTitle()
            return True
        except (RuntimeError, AttributeError, ReferenceError):
            # Dialog was destroyed
            _DIALOGS[dialog_type] = None
            return False
    return False


def clear_all_dialogs():
    """Clear all dialog references - useful for testing or cleanup"""
    global _DIALOGS
    _DIALOGS.clear()


def get_all_dialogs():
    """Get a copy of all current dialog references - for debugging"""
    return _DIALOGS.copy()