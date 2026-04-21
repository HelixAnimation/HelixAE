# -*- coding: utf-8 -*-
"""
Bypass/unbypass context menu methods for footage and composition tree items.
"""

from qtpy.QtCore import Qt

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuBypass:
    """Mixin: bypass/unbypass tree item actions"""

    def _buildItemKey(self, item, userData):
        """Build the bypass key for a footage or comp item"""
        if userData.get('type') == 'footage':
            shot_name = self.tracker.getShotNameFromItem(item) or userData.get('shot', '')
            identifier = userData.get('identifier', '')

            item_text = item.text(0)
            is_2d_render = (item_text.startswith('[2D]') or item_text.startswith('[PB]'))
            is_3d_render = identifier and not is_2d_render and identifier != item_text

            if is_3d_render:
                aov = item_text
            else:
                aov = ''
                if is_2d_render and identifier:
                    text_without_prefix = item_text.replace('[2D] ', '').replace('[PB] ', '')
                    if text_without_prefix != identifier:
                        suffix = text_without_prefix.replace(identifier, '', 1).strip()
                        if suffix:
                            identifier = f"{identifier} {suffix}"
                if not identifier:
                    identifier = item_text

            if shot_name and identifier:
                if aov:
                    return f"footage_{shot_name}_{identifier}_{aov}"
                else:
                    return f"footage_{shot_name}_{identifier}"
            else:
                return f"footage_{userData.get('path', '')}"

        elif userData.get('type') == 'comp':
            comp_name = userData.get('compName', userData.get('name', ''))
            return f"comp_{userData.get('id')}_{comp_name}"

        return None

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

        scroll_position = self.tracker.tw_footage.verticalScrollBar().value()
        self.tracker.loadFootageData()
        self.tracker.tw_footage.verticalScrollBar().setValue(scroll_position)

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

        scroll_position = self.tracker.tw_footage.verticalScrollBar().value()
        self.tracker.loadFootageData()
        self.tracker.tw_footage.verticalScrollBar().setValue(scroll_position)

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
