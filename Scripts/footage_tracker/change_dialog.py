# -*- coding: utf-8 -*-
"""Unified Change dialog for shot, identifier and AOV selection."""

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from PrismUtils.Decorators import err_catcher as err_catcher

from footage_tracker import version_paths


class ChangeFootageDialog(QDialog):
    """Change shot, identifier and AOV for one or more footage items."""

    def __init__(self, tracker, shot_switcher, footage_items):
        super(ChangeFootageDialog, self).__init__(
            getattr(tracker, 'dlg_footage', None))
        self.tracker = tracker
        self.core = tracker.core
        self.shot_switcher = shot_switcher
        self.items = list(footage_items)
        self.is_3d = all(
            self.shot_switcher.is3DFootageItem(item) for item in self.items)
        self._resolved_entries = []
        self._refreshing = False
        self._identifier_cache = {}
        self._aov_cache = {}

        self._setupUI()
        self._populateShots()
        self._populateIdentifiers()
        self._populateAOVs()
        self._refreshPreview()

    @err_catcher(name=__name__)
    def showDialog(self):
        """Show the dialog modally."""
        self.exec_()

    def _setupUI(self):
        self.setWindowTitle("Change Footage")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.resize(820, 560)

        layout = QVBoxLayout(self)

        if len(self.items) == 1:
            header_text = "Change footage source"
        else:
            header_text = f"Change footage source for {len(self.items)} items"
        header = QLabel(header_text)
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        form = QFormLayout()
        self.cb_shot = QComboBox()
        self.cb_shot.currentIndexChanged.connect(self._onShotChanged)
        form.addRow("Shot:", self.cb_shot)

        self.cb_identifier = QComboBox()
        self.cb_identifier.currentIndexChanged.connect(self._onIdentifierChanged)
        form.addRow("Identifier:", self.cb_identifier)

        self.l_aov = QLabel("AOV:")
        self.cb_aov = QComboBox()
        self.cb_aov.currentIndexChanged.connect(lambda *_: self._refreshPreview())
        form.addRow(self.l_aov, self.cb_aov)
        layout.addLayout(form)

        info = QLabel(
            "Shot or identifier changes use the latest version. "
            "Changing only the AOV keeps the current version when it contains "
            "that pass; otherwise the newest version with the pass is used."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(info)

        layout.addWidget(QLabel("Preview:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(200)
        self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.preview, 1)

        self.summary = QLabel("")
        self.summary.setStyleSheet("color: #888888;")
        layout.addWidget(self.summary)

        button_layout = QHBoxLayout()
        self.btn_advanced = QPushButton("Advanced — Path Variables…")
        self.btn_advanced.clicked.connect(lambda: self._openAdvanced())
        button_layout.addWidget(self.btn_advanced)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.btn_change = QPushButton("Change")
        self.btn_change.setDefault(True)
        self.btn_change.setStyleSheet("font-weight: bold;")
        self.btn_change.clicked.connect(lambda: self._apply())
        button_layout.addWidget(self.btn_change)
        layout.addLayout(button_layout)

    def _currentShots(self):
        shots = set()
        for item in self.items:
            shot = self.tracker.getShotNameFromItem(item)
            if not shot:
                shot = (item.data(0, Qt.UserRole) or {}).get('shot', '')
            if shot:
                shots.add(shot)
        return shots

    def _currentIdentifiers(self):
        identifiers = set()
        for item in self.items:
            identifier = (item.data(0, Qt.UserRole) or {}).get('identifier', '')
            if identifier:
                identifiers.add(identifier)
        return identifiers

    def _currentAOVs(self):
        aovs = set()
        for item in self.items:
            aov = self.shot_switcher.getAOVNameFromItem(item)
            if aov:
                aovs.add(aov)
        return aovs

    @staticmethod
    def _keepCurrentLabel(values, noun):
        values = sorted(value for value in values if value)
        if len(values) == 1:
            return f"Keep current ({values[0]})"
        if values:
            return f"Keep current (mixed {noun}s)"
        return "Keep current"

    def _effectiveShot(self):
        shot = self.cb_shot.currentData()
        if shot:
            return shot
        current = self._currentShots()
        if len(current) == 1:
            return next(iter(current))
        return None

    def _selectedIdentifierChoice(self):
        choice = self.cb_identifier.currentData()
        return choice if isinstance(choice, dict) else None

    def _populateShots(self):
        self.cb_shot.blockSignals(True)
        try:
            self.cb_shot.clear()
            self.cb_shot.addItem(
                self._keepCurrentLabel(self._currentShots(), "shot"), None)
            for shot in (self.shot_switcher.getChangeDialogShots() or []):
                self.cb_shot.addItem(shot, shot)

            selected = 0
            current = self._currentShots()
            if len(current) == 1:
                index = self.cb_shot.findData(next(iter(current)))
                if index >= 0:
                    selected = index
            self.cb_shot.setCurrentIndex(selected)
        finally:
            self.cb_shot.blockSignals(False)

    def _populateIdentifiers(self):
        self.cb_identifier.blockSignals(True)
        try:
            self.cb_identifier.clear()
            current_identifiers = self._currentIdentifiers()
            self.cb_identifier.addItem(
                self._keepCurrentLabel(current_identifiers, "identifier"), None)

            shot = self._effectiveShot()
            if not shot:
                self.cb_identifier.setEnabled(False)
                self.cb_identifier.setCurrentIndex(0)
                return

            self.cb_identifier.setEnabled(True)
            cache_key = (shot, self.is_3d)
            if cache_key not in self._identifier_cache:
                self._identifier_cache[cache_key] = (
                    self.shot_switcher.getChangeIdentifierChoices(
                        self.items, shot) or [])
            choices = self._identifier_cache[cache_key]

            current_type = None
            if len(current_identifiers) == 1:
                source_path = (self.items[0].data(0, Qt.UserRole) or {}).get(
                    'path', '')
                current_type = version_paths.render_type_from_path(source_path)
            current_name = (next(iter(current_identifiers))
                            if len(current_identifiers) == 1 else None)

            matches = []
            for choice in choices:
                label = choice['label']
                is_current = (current_name is not None
                              and choice['identifier'] == current_name)
                if is_current:
                    label += " (current)"
                self.cb_identifier.addItem(label, choice)
                index = self.cb_identifier.count() - 1
                if is_current:
                    matches.append((index, choice))

            selected = 0
            if matches:
                selected = matches[0][0]
                if current_type:
                    for index, choice in matches:
                        if choice.get('type') == current_type:
                            selected = index
                            break
            self.cb_identifier.setCurrentIndex(selected)
        finally:
            self.cb_identifier.blockSignals(False)

    def _populateAOVs(self):
        if not self.is_3d:
            self.l_aov.setVisible(False)
            self.cb_aov.setVisible(False)
            self.cb_aov.blockSignals(True)
            self.cb_aov.clear()
            self.cb_aov.blockSignals(False)
            return

        self.l_aov.setVisible(True)
        self.cb_aov.setVisible(True)
        self.cb_aov.blockSignals(True)
        try:
            self.cb_aov.clear()
            current_aovs = self._currentAOVs()
            self.cb_aov.addItem(
                self._keepCurrentLabel(current_aovs, "AOV"), None)

            shot = self._effectiveShot()
            if not shot:
                self.cb_aov.setEnabled(False)
                self.cb_aov.setCurrentIndex(0)
                return

            self.cb_aov.setEnabled(True)
            choice = self._selectedIdentifierChoice()
            cache_key = (
                shot,
                choice.get('type') if choice else None,
                choice.get('parent') if choice else None,
                choice.get('identifier') if choice else None,
            )
            if cache_key not in self._aov_cache:
                self._aov_cache[cache_key] = (
                    self.shot_switcher.getChangeAOVChoices(
                        self.items, shot, choice) or [])
            aovs = self._aov_cache[cache_key]

            selected = 0
            current_name = (next(iter(current_aovs))
                            if len(current_aovs) == 1 else None)
            for aov in aovs:
                label = aov
                if current_name is not None and aov == current_name:
                    label += " (current)"
                self.cb_aov.addItem(label, aov)
                if current_name is not None and aov == current_name:
                    selected = self.cb_aov.count() - 1
            if not aovs:
                self.cb_aov.setEnabled(False)
            self.cb_aov.setCurrentIndex(selected)
        finally:
            self.cb_aov.blockSignals(False)

    def _onShotChanged(self, index):
        self._populateIdentifiers()
        self._populateAOVs()
        self._refreshPreview()

    def _onIdentifierChanged(self, index):
        self._populateAOVs()
        self._refreshPreview()

    @err_catcher(name=__name__)
    def _refreshPreview(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            target_shot = self.cb_shot.currentData()
            identifier_choice = self._selectedIdentifierChoice()
            target_aov = self.cb_aov.currentData() if self.is_3d else None
            entries = self.shot_switcher.resolveChangeTargets(
                self.items, target_shot, identifier_choice, target_aov) or []
            self._resolved_entries = entries

            lines = []
            ready = 0
            unchanged = 0
            missing = 0
            for entry in entries[:30]:
                if entry.get('error'):
                    missing += 1
                    lines.append(f"✗ {entry['label']}: {entry['error']}")
                elif entry.get('unchanged'):
                    unchanged += 1
                    lines.append(f"= {entry['label']}: already {entry['version']}")
                else:
                    ready += 1
                    lines.append(
                        f"✓ {entry['label']} → {entry['version']}  {entry['path']}")
            if len(entries) > 30:
                lines.append(f"... and {len(entries) - 30} more")

            self.preview.setPlainText("\n".join(lines))
            self.summary.setText(
                f"{ready} to change, {unchanged} unchanged, {missing} missing")
            self.btn_change.setEnabled(ready > 0)
        finally:
            self._refreshing = False

    @err_catcher(name=__name__)
    def _apply(self):
        self._refreshPreview()
        entries = self._resolved_entries
        changes = [entry for entry in entries
                   if entry.get('path') and not entry.get('unchanged')]
        missing = [entry for entry in entries if not entry.get('path')]

        if not changes:
            if missing:
                self.core.popup(
                    "No selected target has media. Choose a different "
                    "shot, identifier or AOV.")
            else:
                self.core.popup("No changes selected.")
            return

        if missing:
            reply = QMessageBox.question(
                self,
                "Change Footage",
                f"{len(missing)} item(s) have no media for the selected target."
                f"\n\nChange the {len(changes)} item(s) that resolve?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.shot_switcher.applyChangeTargets(changes)
        self.accept()

    def _openAdvanced(self):
        items = list(self.items)
        self.accept()
        self.shot_switcher.showVariableSelectionDialog(items)


class ChangeAOVDialog(QDialog):
    """Small list dialog for choosing a single AOV."""

    def __init__(self, tracker, footage_items, aovs, current_aovs):
        super(ChangeAOVDialog, self).__init__(
            getattr(tracker, 'dlg_footage', None))
        self.tracker = tracker
        self.items = list(footage_items)
        self.setWindowTitle("Change AOV")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.resize(440, 500)

        layout = QVBoxLayout(self)
        header = QLabel("Select AOV")
        header.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(header)

        current = sorted(aov for aov in current_aovs if aov)
        if len(current) == 1:
            current_text = current[0]
        elif current:
            current_text = "mixed AOVs"
        else:
            current_text = "unknown AOV"
        info = QLabel(
            f"Current: {current_text}\n"
            "The chosen pass keeps the current version when it contains that "
            "AOV; otherwise the newest version with the pass is used."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(info)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setAlternatingRowColors(False)
        layout.addWidget(self.list, 1)

        selected_index = -1
        for aov in aovs:
            label = aov + (" (current)" if aov in current_aovs else "")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, aov)
            self.list.addItem(item)
            if len(current) == 1 and aov == current[0]:
                selected_index = self.list.count() - 1

        if not aovs:
            placeholder = QListWidgetItem("No AOVs found")
            placeholder.setFlags(Qt.NoItemFlags)
            self.list.addItem(placeholder)
        elif selected_index >= 0:
            self.list.setCurrentRow(selected_index)
        else:
            self.list.setCurrentRow(0)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.btn_change = QPushButton("Change")
        self.btn_change.setDefault(True)
        self.btn_change.setStyleSheet("font-weight: bold;")
        self.btn_change.clicked.connect(self.accept)
        button_layout.addWidget(self.btn_change)
        layout.addLayout(button_layout)

        self.list.itemSelectionChanged.connect(self._updateSelection)
        self._updateSelection()

    def _updateSelection(self):
        item = self.list.currentItem()
        self.btn_change.setEnabled(bool(item and item.data(Qt.UserRole)))

    def selectedAOV(self):
        """Return the selected AOV name, or ``None``."""
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None
