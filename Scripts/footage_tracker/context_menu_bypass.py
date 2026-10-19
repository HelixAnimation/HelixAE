# -*- coding: utf-8 -*-
"""
Bypass/unbypass context menu methods for footage and composition tree items.
"""

from qtpy.QtCore import Qt

from footage_tracker import bypass_keys
from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuBypass:
    """Mixin: bypass/unbypass tree item actions"""

    def _buildItemKey(self, item, userData):
        """Build the bypass key for a footage or comp item.

        Implementation lives in footage_tracker/bypass_keys.py so the
        context menu and the issue checker share one key format.
        """
        item_type = userData.get('type')
        shot_name = ''
        if item_type == 'footage':
            shot_name = self.tracker.getShotNameFromItem(item) or userData.get('shot', '')
        return bypass_keys.key_from_tree_item(
            item_type,
            item.text(0),
            shot_name,
            userData.get('identifier', ''),
            comp_id=userData.get('id'),
            comp_name=userData.get('compName', userData.get('name', '')),
            path=userData.get('path', ''),
        )

    def _bypassTreeItem(self, item):
        """Bypass an item in the footage tracker tree"""
        userData = item.data(0, Qt.UserRole)
        if not userData:
            return

        ignored_items = self.tracker.startup_warnings._getIgnoredItems()
        item_key = self._buildItemKey(item, userData)

        print(f"[DEBUG BYPASS] _bypassTreeItem:")
        print(f"  item.text(0) = {item.text(0)}")
        print(f"  userData = {userData}")
        print(f"  item_key = {item_key}")

        if not item_key:
            return

        if userData.get('type') == 'footage':
            ignored_items['outdated'].add(item_key)
            ignored_items['fps_mismatch'].add(item_key)
            ignored_items['frame_range_mismatch'].add(item_key)
            ignored_items['resolution_mismatch'].add(item_key)
        elif userData.get('type') == 'comp':
            ignored_items['fps_mismatch'].add(item_key)
            ignored_items['frame_range_mismatch'].add(item_key)
            ignored_items['resolution_mismatch'].add(item_key)

        self.tracker.startup_warnings._saveIgnoredItems(ignored_items)

        self.tracker.startup_warnings._updateCachedIssueCounts()
        self.tracker.updateCheckIssuesButton()

    def _unbypassTreeItem(self, item):
        """Unbypass an item in the footage tracker tree"""
        userData = item.data(0, Qt.UserRole)
        if not userData:
            return

        ignored_items = self.tracker.startup_warnings._getIgnoredItems()
        item_key = self._buildItemKey(item, userData)

        if not item_key:
            return

        for issue_type in ignored_items.values():
            issue_type.discard(item_key)

        self.tracker.startup_warnings._saveIgnoredItems(ignored_items)

        self.tracker.startup_warnings._updateCachedIssueCounts()
        self.tracker.updateCheckIssuesButton()

    def _isTreeItemBypassed(self, item):
        """Check if a tree item is bypassed"""
        userData = item.data(0, Qt.UserRole)
        if not userData:
            return False

        ignored_items = self.tracker.startup_warnings._getIgnoredItems()
        item_key = self._buildItemKey(item, userData)

        if not item_key:
            return False

        if userData.get('type') == 'footage':
            return (item_key in ignored_items.get('outdated', set()) or
                    item_key in ignored_items.get('fps_mismatch', set()) or
                    item_key in ignored_items.get('frame_range_mismatch', set()) or
                    item_key in ignored_items.get('resolution_mismatch', set()))
        elif userData.get('type') == 'comp':
            return (item_key in ignored_items.get('fps_mismatch', set()) or
                    item_key in ignored_items.get('frame_range_mismatch', set()) or
                    item_key in ignored_items.get('resolution_mismatch', set()))

        return False
