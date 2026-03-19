# -*- coding: utf-8 -*-
"""
Dialog Manager Module
Provides reusable dialog creation and management functionality
"""

import os
from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import *

from PrismUtils.Decorators import err_catcher as err_catcher


class DialogManager:
    """Manages dialog creation and common UI patterns"""

    def __init__(self, parent):
        self.parent = parent
        self.core = parent.core

    @err_catcher(name=__name__)
    def createErrorDialog(self, title, message, copy_button=True, extra_buttons=None):
        """Create a standardized error dialog with optional copy button"""
        # Get the proper parent dialog
        parent_dialog = None
        if hasattr(self.parent, 'tracker') and hasattr(self.parent.tracker, 'dlg_footage'):
            parent_dialog = self.parent.tracker.dlg_footage
        elif hasattr(self.parent, 'dlg_footage'):
            parent_dialog = self.parent.dlg_footage

        dlg = QDialog(parent_dialog)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle(title)
        dlg.resize(600, 400)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Text edit for error message
        textEdit = QTextEdit()
        textEdit.setPlainText(message)
        textEdit.setReadOnly(True)
        textEdit.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(textEdit)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        if copy_button:
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(message))
            button_layout.addWidget(copy_btn)

        if extra_buttons:
            for btn_text, btn_callback in extra_buttons:
                btn = QPushButton(btn_text)
                btn.clicked.connect(btn_callback)
                button_layout.addWidget(btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        return dlg

    @err_catcher(name=__name__)
    def createInfoDialog(self, title, message, show_copy=True):
        """Create a standardized info dialog"""
        return self.createErrorDialog(title, message, copy_button=show_copy)

    @err_catcher(name=__name__)
    def createConfirmationDialog(self, title, message, detailed_text=None):
        """Create a standardized confirmation dialog"""
        # Get the proper parent dialog
        parent_dialog = None
        if hasattr(self.parent, 'tracker') and hasattr(self.parent.tracker, 'dlg_footage'):
            parent_dialog = self.parent.tracker.dlg_footage
        elif hasattr(self.parent, 'dlg_footage'):
            parent_dialog = self.parent.dlg_footage

        dlg = QDialog(parent_dialog)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        dlg.setWindowTitle(title)
        dlg.resize(500, 300)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        # Main message
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        # Detailed text if provided
        if detailed_text:
            details_text = QTextEdit()
            details_text.setPlainText(detailed_text)
            details_text.setReadOnly(True)
            details_text.setMaximumHeight(200)
            layout.addWidget(details_text)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("Confirm")
        confirm_btn.setDefault(True)
        confirm_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)
        return dlg

    @err_catcher(name=__name__)
    def showPopupMessage(self, title, message, msg_type=QMessageBox.Information):
        """Show a popup message using QMessageBox"""
        msg = QMessageBox(self.parent.dlg_footage if hasattr(self.parent, 'dlg_footage') else self.parent)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(msg_type)
        msg.exec_()

    @err_catcher(name=__name__)
    def createProgressDialog(self, title, minimum=0, maximum=100):
        """Create a progress dialog"""
        # Get the proper parent dialog
        parent_dialog = None
        if hasattr(self.parent, 'tracker') and hasattr(self.parent.tracker, 'dlg_footage'):
            parent_dialog = self.parent.tracker.dlg_footage
        elif hasattr(self.parent, 'dlg_footage'):
            parent_dialog = self.parent.dlg_footage

        dlg = QProgressDialog(parent_dialog)
        dlg.setWindowTitle(title)
        dlg.setRange(minimum, maximum)
        dlg.setWindowModality(Qt.WindowModal)
        return dlg

    @err_catcher(name=__name__)
    def createLoadingDialog(self, title="Loading...", message="Please wait..."):
        """Create a simple loading dialog"""
        # Get the proper parent dialog
        parent_dialog = None
        if hasattr(self.parent, 'tracker') and hasattr(self.parent.tracker, 'dlg_footage'):
            parent_dialog = self.parent.tracker.dlg_footage
        elif hasattr(self.parent, 'dlg_footage'):
            parent_dialog = self.parent.dlg_footage

        dlg = QDialog(parent_dialog)
        dlg.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(300, 100)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        label = QLabel(message)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # Add a simple progress bar
        progress = QProgressBar()
        progress.setRange(0, 0)  # Indeterminate progress
        layout.addWidget(progress)

        return dlg

    @err_catcher(name=__name__)
    def createDebugDialog(self, title, debug_info, refresh_callback=None):
        """Create a debug information dialog with optional refresh button"""
        extra_buttons = []
        if refresh_callback:
            refresh_btn = QPushButton("Refresh")
            refresh_btn.clicked.connect(refresh_callback)
            extra_buttons.append(("Refresh", refresh_btn))

        return self.createErrorDialog(title, debug_info, copy_button=True, extra_buttons=extra_buttons)