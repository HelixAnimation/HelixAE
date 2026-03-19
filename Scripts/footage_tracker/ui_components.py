# -*- coding: utf-8 -*-
"""
UI Components and Delegates
"""

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *


class NoHoverDelegate(QStyledItemDelegate):
    """Custom delegate that preserves item backgrounds on hover"""
    def paint(self, painter, option, index):
        # Always remove hover state to prevent default hover styling
        if option.state & QStyle.State_MouseOver:
            option.state &= ~QStyle.State_MouseOver
        
        # Get the item's background
        bgData = index.data(Qt.BackgroundRole)
        
        # If item has a custom background, paint it first
        if bgData:
            painter.save()
            if isinstance(bgData, QBrush):
                painter.fillRect(option.rect, bgData)
            elif isinstance(bgData, QColor):
                painter.fillRect(option.rect, QBrush(bgData))
            painter.restore()
        
        # Continue with normal painting (text, icons, etc.)
        super().paint(painter, option, index)
