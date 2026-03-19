# -*- coding: utf-8 -*-
"""
Image resize context menu methods: resize menus, confirm dialogs, batch resize, package install.
"""

import os

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QAction, QApplication, QComboBox, QDialog, QHBoxLayout, QLabel,
    QProgressDialog, QPushButton, QScrollArea, QTextEdit, QVBoxLayout
)

from PrismUtils.Decorators import err_catcher as err_catcher


class ContextMenuImageResize:
    """Mixin: image resize context menu actions"""

    @err_catcher(name=__name__)
    def _addImageResizeMenu(self, menu, file_path, position):
        """Add image resize submenu with preset options"""
        from .image_resizer import ImageResizer

        print(f"[DEBUG MENU] _addImageResizeMenu called")

        resizer = ImageResizer(self.tracker)
        missing_packages = resizer.getMissingPackages()

        if missing_packages:
            print(f"[DEBUG MENU] Missing packages: {missing_packages}")
        else:
            print(f"[DEBUG MENU] All required packages available")

        if missing_packages:
            resizeAction = QAction(f"Resize AOV Images ({', '.join(missing_packages)} missing)", menu)
            resizeAction.triggered.connect(lambda: self._offerPackagesInstall(file_path, position, missing_packages))
            resizeAction.setStatusTip("Click to install required dependencies")
            menu.addAction(resizeAction)
            print(f"[DEBUG MENU] Showing install option for: {missing_packages}")
            return

        selected_aovs = self._getSelectedAOVs()
        is_batch = len(selected_aovs) > 1

        if is_batch:
            print(f"[DEBUG MENU] Batch resize detected: {len(selected_aovs)} AOVs selected")
            menu_label = f"Resize {len(selected_aovs)} AOVs"
        else:
            print("[DEBUG MENU] Creating resize submenu")
            menu_label = "Resize AOV Images"

        resizeMenu = menu.addMenu(menu_label)

        shot_name = None
        kitsu_resolution = None

        if is_batch:
            if selected_aovs:
                first_aov = selected_aovs[0]
                first_aov_file = first_aov.get('sample_file', '')
                shot_name = self._extractShotFromFootagePath(first_aov_file)
        else:
            shot_name = self._extractShotFromFootagePath(file_path)

        if shot_name and self.tracker.kitsuShotData and shot_name in self.tracker.kitsuShotData:
            kitsu_data = self.tracker.kitsuShotData[shot_name]
            kitsu_width = kitsu_data.get('width')
            kitsu_height = kitsu_data.get('height')
            if kitsu_width and kitsu_height:
                try:
                    kitsu_resolution = (int(kitsu_width), int(kitsu_height))
                except (ValueError, TypeError):
                    pass

        presets = []

        if kitsu_resolution:
            w, h = kitsu_resolution
            presets.append(("Kitsu (%sx%s)" % (w, h), w, h))

        presets.extend([
            ("HD (1280x720)", 1280, 720),
            ("Full HD (1920x1080)", 1920, 1080),
            ("4K (3840x2160)", 3840, 2160),
        ])

        for label, width, height in presets:
            action = QAction(label, resizeMenu)
            if is_batch:
                action.triggered.connect(
                    lambda checked, w=width, h=height: self._executeBatchResize(
                        selected_aovs, w, h, position
                    )
                )
            else:
                action.triggered.connect(
                    lambda checked, w=width, h=height: self._executeResize(
                        file_path, w, h, position
                    )
                )
            resizeMenu.addAction(action)

    @err_catcher(name=__name__)
    def _addImageResizeMenu_lazy(self, menu):
        """Lazy-load Image Resize menu contents"""
        if menu.actions():
            return

        import time
        t_start = time.perf_counter()

        file_path = menu.property("filePath")
        position = menu.property("position")

        if not file_path:
            print("[DEBUG MENU] No filePath stored for resize menu")
            return

        from .image_resizer import ImageResizer

        resizer = ImageResizer(self.tracker)
        missing_packages = resizer.getMissingPackages()

        if missing_packages:
            print(f"[DEBUG MENU] Missing packages: {missing_packages}")
            resizeAction = QAction(f"Resize AOV Images ({', '.join(missing_packages)} missing)", menu)
            resizeAction.triggered.connect(lambda: self._offerPackagesInstall(file_path, position, missing_packages))
            resizeAction.setStatusTip("Click to install required dependencies")
            menu.addAction(resizeAction)
            print(f"[DEBUG MENU] Showing install option for: {missing_packages}")
            t_end = time.perf_counter()
            if t_end - t_start > 0.01:
                print(f"[DEBUG MENU] Image Resize menu (lazy) took {t_end-t_start:.4f}s")
            return
        else:
            print(f"[DEBUG MENU] All required packages available")

        selected_aovs = self._getSelectedAOVs()
        is_batch = len(selected_aovs) > 1

        shot_name = None
        kitsu_resolution = None

        if is_batch:
            if selected_aovs:
                first_aov = selected_aovs[0]
                first_aov_file = first_aov.get('sample_file', '')
                shot_name = self._extractShotFromFootagePath(first_aov_file)
        else:
            shot_name = self._extractShotFromFootagePath(file_path)

        if shot_name and self.tracker.kitsuShotData and shot_name in self.tracker.kitsuShotData:
            kitsu_data = self.tracker.kitsuShotData[shot_name]
            kitsu_width = kitsu_data.get('width')
            kitsu_height = kitsu_data.get('height')
            if kitsu_width and kitsu_height:
                try:
                    kitsu_resolution = (int(kitsu_width), int(kitsu_height))
                except (ValueError, TypeError):
                    pass

        presets = []

        if kitsu_resolution:
            w, h = kitsu_resolution
            presets.append(("Kitsu (%sx%s)" % (w, h), w, h))

        presets.extend([
            ("HD (1280x720)", 1280, 720),
            ("Full HD (1920x1080)", 1920, 1080),
            ("4K (3840x2160)", 3840, 2160),
        ])

        for label, width, height in presets:
            action = QAction(label, menu)
            if is_batch:
                action.triggered.connect(
                    lambda checked, w=width, h=height: self._executeBatchResize(
                        selected_aovs, w, h, position
                    )
                )
            else:
                action.triggered.connect(
                    lambda checked, w=width, h=height: self._executeResize(
                        file_path, w, h, position
                    )
                )
            menu.addAction(action)

        t_end = time.perf_counter()
        if t_end - t_start > 0.01:
            print(f"[DEBUG MENU] Image Resize menu (lazy) took {t_end-t_start:.4f}s")

    @err_catcher(name=__name__)
    def _getSelectedAOVs(self):
        """Get all selected AOVs from the tree widget for batch resizing"""
        from .image_resizer import ImageResizer

        resizer = ImageResizer(self.tracker)
        selected_items = self.tracker.tw_footage.selectedItems()
        aovs = []

        for item in selected_items:
            userData = item.data(0, Qt.UserRole)
            if not userData or userData.get('type') != 'footage':
                continue

            filePath = userData.get('path', '')
            if not self._is3DRenderFootage(filePath):
                continue

            aov_name = resizer.detectAOVFromPath(filePath)
            if not aov_name:
                continue

            aov_folder = os.path.dirname(filePath)
            if not os.path.isdir(aov_folder):
                continue

            files, _ = resizer.collectAOVFiles(filePath)
            if not files:
                continue

            duplicate = False
            for existing_aov in aovs:
                if existing_aov['folder'] == aov_folder:
                    duplicate = True
                    break

            if not duplicate:
                aovs.append({
                    'name': aov_name,
                    'folder': aov_folder,
                    'file_count': len(files),
                    'sample_file': filePath
                })

        return aovs

    @err_catcher(name=__name__)
    def _executeResize(self, file_path, width, height, position):
        """Execute the resize operation with confirmation"""
        from .image_resizer import ImageResizer

        resizer = ImageResizer(self.tracker)

        aov_name = resizer.detectAOVFromPath(file_path)
        files, aov_folder = resizer.collectAOVFiles(file_path)

        if not files:
            self.core.popup("No image files found in AOV folder.")
            return

        interpolation, should_interpolate, interp_name = resizer.getInterpolationMethod(aov_name)

        dlg = self._createResizeConfirmDialog(
            aov_name, len(files), (width, height), interp_name, aov_folder
        )

        if dlg.exec_() != QDialog.Accepted:
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_folder = os.path.join(aov_folder, f"originals_backup_{timestamp}")
        os.makedirs(backup_folder, exist_ok=True)

        progress = QProgressDialog(
            f"Resizing {len(files)} images...",
            "Cancel",
            0,
            len(files),
            self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        )
        progress.setWindowTitle("Resizing Images")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        def progress_callback(current, total):
            progress.setValue(current)
            QApplication.processEvents()

        results = resizer.batchResizeAOV(
            files, (width, height), interpolation, should_interpolate,
            backup_folder, progress_callback
        )

        progress.close()

        self._showResizeResults(results, backup_folder)

        self.tracker.loadFootageData(preserve_scroll=True)

    @err_catcher(name=__name__)
    def _executeBatchResize(self, selected_aovs, width, height, position):
        """Execute batch resize operation for multiple AOVs with confirmation"""
        from .image_resizer import ImageResizer

        resizer = ImageResizer(self.tracker)

        total_files = sum(aov['file_count'] for aov in selected_aovs)
        total_aovs = len(selected_aovs)

        aov_details = []
        for aov in selected_aovs:
            interpolation, should_interpolate, interp_name = resizer.getInterpolationMethod(aov['name'])
            aov_details.append({
                'name': aov['name'],
                'folder': aov['folder'],
                'file_count': aov['file_count'],
                'interpolation': interpolation,
                'should_interpolate': should_interpolate,
                'interp_name': interp_name
            })

        dlg = self._createBatchResizeConfirmDialog(
            aov_details, total_files, total_aovs, (width, height)
        )

        if dlg.exec_() != QDialog.Accepted:
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        progress = QProgressDialog(
            f"Resizing {total_files} images in {total_aovs} AOVs...",
            "Cancel",
            0,
            total_files,
            self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        )
        progress.setWindowTitle("Batch Resizing Images")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        aggregate_results = {
            'total': total_files,
            'success': 0,
            'failed': 0,
            'errors': [],
            'aov_results': [],
            'backup_folders': []
        }

        current_file_index = 0

        for aov_info in aov_details:
            aov_name = aov_info['name']
            aov_folder = aov_info['folder']
            interpolation = aov_info['interpolation']

            progress.setLabelText(
                f"Resizing AOV: {aov_name} ({current_file_index}/{total_files} files processed)"
            )
            QApplication.processEvents()

            backup_folder = os.path.join(aov_folder, f"originals_backup_{timestamp}")
            os.makedirs(backup_folder, exist_ok=True)

            _fallback = (os.path.join(aov_folder, os.listdir(aov_folder)[0])
                         if os.path.exists(aov_folder) else '')
            files, _ = resizer.collectAOVFiles(aov_info.get('sample_file', _fallback))

            if not files:
                files = []
                for item in os.listdir(aov_folder):
                    item_path = os.path.join(aov_folder, item)
                    if os.path.isfile(item_path):
                        ext = os.path.splitext(item)[1].lower()
                        if ext in resizer.SUPPORTED_FORMATS:
                            files.append(item_path)
                files = sorted(files)

            def progress_callback(current, total):
                nonlocal current_file_index
                progress.setValue(current_file_index + current)
                QApplication.processEvents()

            results = resizer.batchResizeAOV(
                files, (width, height), interpolation, aov_info['should_interpolate'],
                backup_folder, progress_callback
            )

            aggregate_results['aov_results'].append({
                'aov_name': aov_name,
                'results': results,
                'backup_folder': backup_folder
            })

            aggregate_results['success'] += results['success']
            aggregate_results['failed'] += results['failed']
            aggregate_results['errors'].extend(results['errors'])
            aggregate_results['backup_folders'].append(backup_folder)

            current_file_index += len(files)

        progress.close()

        self._showBatchResizeResults(aggregate_results)

        self.tracker.loadFootageData(preserve_scroll=True)

    @err_catcher(name=__name__)
    def _createResizeConfirmDialog(self, aov_name, file_count, size, interpolation, folder_path):
        """Create confirmation dialog for resize operation"""
        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dlg = QDialog(parent)
        dlg.setWindowTitle("Confirm Image Resize")
        dlg.resize(500, 350)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        msg = QLabel(
            f"<h3>Resize {file_count} images in AOV: <b>{aov_name}</b></h3>"
            f"<p>Target size: <b>{size[0]}x{size[1]}</b></p>"
            f"<p style='background-color: #2b2b2b; padding: 8px; border-radius: 4px;'>"
            f"Filter: <b style='color: #4CAF50;'>{interpolation}</b></p>"
            f"<p>Original files will be backed up to:</p>"
            f"<p style='font-family: monospace; font-size: 11px;'>"
            f"...{os.path.basename(folder_path)}/originals_backup_TIMESTAMP/</p>"
            f"<p style='color: red;'><b>This operation cannot be undone.</b></p>"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("Resize")
        confirm_btn.setStyleSheet("background-color: #d32f2f; color: white; padding: 5px 15px;")
        confirm_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)
        return dlg

    @err_catcher(name=__name__)
    def _showResizeResults(self, results, backup_folder):
        """Show results of resize operation"""
        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dlg = QDialog(parent)
        dlg.setWindowTitle("Resize Complete")
        dlg.resize(400, 300)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        summary = QLabel(
            f"<h2>Resize Complete</h2>"
            f"<p>Total files: <b>{results['total']}</b></p>"
            f"<p>Success: <b style='color: green;'>{results['success']}</b></p>"
            f"<p>Failed: <b style='color: red;'>{results['failed']}</b></p>"
        )
        layout.addWidget(summary)

        if results['errors']:
            error_text = QLabel("<b>Errors:</b>")
            layout.addWidget(error_text)

            error_list = QTextEdit()
            error_list.setReadOnly(True)
            error_list.setMaximumHeight(100)
            error_list.setText("\n".join(results['errors'][:10]))
            if len(results['errors']) > 10:
                error_list.append(f"\n... and {len(results['errors']) - 10} more")
            layout.addWidget(error_list)

        button_layout = QHBoxLayout()

        open_backup_btn = QPushButton("Open Backup Folder")
        open_backup_btn.clicked.connect(lambda: self.tracker.openInExplorer(backup_folder))
        button_layout.addWidget(open_backup_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dlg.exec_()

    @err_catcher(name=__name__)
    def _createBatchResizeConfirmDialog(self, aov_details, total_files, total_aovs, size):
        """Create confirmation dialog for batch resize operation showing all AOVs"""
        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dlg = QDialog(parent)
        dlg.setWindowTitle("Confirm Batch Image Resize")
        dlg.resize(600, 450)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        aov_list_html = "<table style='border-collapse: collapse;'>"
        aov_list_html += (
            "<tr style='border-bottom: 1px solid #444;'>"
            "<th style='padding: 5px; text-align: left;'>AOV</th>"
            "<th style='padding: 5px; text-align: center;'>Files</th>"
            "<th style='padding: 5px; text-align: left;'>Filter</th>"
            "</tr>"
        )
        for aov in aov_details:
            aov_list_html += f"<tr style='border-bottom: 1px solid #333;'>"
            aov_list_html += f"<td style='padding: 5px;'>{aov['name']}</td>"
            aov_list_html += f"<td style='padding: 5px; text-align: center;'>{aov['file_count']}</td>"
            aov_list_html += f"<td style='padding: 5px;'><span style='color: #4CAF50;'>{aov['interp_name']}</span></td>"
            aov_list_html += f"</tr>"
        aov_list_html += "</table>"

        msg = QLabel(
            f"<h3>Batch Resize {total_files} images in {total_aovs} AOVs</h3>"
            f"<p>Target size: <b>{size[0]}x{size[1]}</b></p>"
            f"<p><b>AOVs to process:</b></p>"
            f"<div style='background-color: #1e1e1e; padding: 10px; border-radius: 4px;'>{aov_list_html}</div>"
            f"<p>Original files will be backed up to timestamped folders in each AOV directory.</p>"
            f"<p style='color: red;'><b>This operation cannot be undone.</b></p>"
        )
        msg.setWordWrap(True)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(msg)
        scroll.setMaximumHeight(250)
        layout.addWidget(scroll)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)

        confirm_btn = QPushButton("Resize All")
        confirm_btn.setStyleSheet("background-color: #d32f2f; color: white; padding: 5px 15px;")
        confirm_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(confirm_btn)

        layout.addLayout(button_layout)
        return dlg

    @err_catcher(name=__name__)
    def _showBatchResizeResults(self, aggregate_results):
        """Show results of batch resize operation"""
        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dlg = QDialog(parent)
        dlg.setWindowTitle("Batch Resize Complete")
        dlg.resize(600, 500)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        summary = QLabel(
            f"<h2>Batch Resize Complete</h2>"
            f"<p>Total AOVs: <b>{len(aggregate_results['aov_results'])}</b></p>"
            f"<p>Total files: <b>{aggregate_results['total']}</b></p>"
            f"<p>Success: <b style='color: green;'>{aggregate_results['success']}</b></p>"
            f"<p>Failed: <b style='color: red;'>{aggregate_results['failed']}</b></p>"
        )
        layout.addWidget(summary)

        aov_breakdown_label = QLabel("<b>Per-AOV Breakdown:</b>")
        layout.addWidget(aov_breakdown_label)

        aov_table = QTextEdit()
        aov_table.setReadOnly(True)
        aov_table.setMaximumHeight(150)

        table_html = "<table style='border-collapse: collapse;'>"
        table_html += (
            "<tr style='border-bottom: 1px solid #555;'>"
            "<th style='padding: 4px; text-align: left;'>AOV</th>"
            "<th style='padding: 4px; text-align: center;'>Total</th>"
            "<th style='padding: 4px; text-align: center; color: green;'>OK</th>"
            "<th style='padding: 4px; text-align: center; color: red;'>Failed</th>"
            "</tr>"
        )
        for aov_result in aggregate_results['aov_results']:
            results = aov_result['results']
            table_html += f"<tr style='border-bottom: 1px solid #333;'>"
            table_html += f"<td style='padding: 4px;'>{aov_result['aov_name']}</td>"
            table_html += f"<td style='padding: 4px; text-align: center;'>{results['total']}</td>"
            table_html += f"<td style='padding: 4px; text-align: center; color: green;'>{results['success']}</td>"
            table_html += f"<td style='padding: 4px; text-align: center; color: red;'>{results['failed']}</td>"
            table_html += f"</tr>"
        table_html += "</table>"
        aov_table.setHtml(table_html)
        layout.addWidget(aov_table)

        if aggregate_results['errors']:
            error_text = QLabel("<b>Errors:</b>")
            layout.addWidget(error_text)

            error_list = QTextEdit()
            error_list.setReadOnly(True)
            error_list.setMaximumHeight(80)
            error_list.setText("\n".join(aggregate_results['errors'][:10]))
            if len(aggregate_results['errors']) > 10:
                error_list.append(f"\n... and {len(aggregate_results['errors']) - 10} more")
            layout.addWidget(error_list)

        backup_label = QLabel("<b>Backup Folders:</b>")
        layout.addWidget(backup_label)

        backup_combo = QComboBox()
        for backup_path in aggregate_results['backup_folders']:
            backup_combo.addItem(backup_path)
        layout.addWidget(backup_combo)

        button_layout = QHBoxLayout()

        open_backup_btn = QPushButton("Open Selected Backup")
        open_backup_btn.clicked.connect(lambda: self.tracker.openInExplorer(backup_combo.currentText()))
        button_layout.addWidget(open_backup_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)
        dlg.exec_()

    @err_catcher(name=__name__)
    def _offerPackagesInstall(self, file_path, position, missing_packages):
        """Offer to install missing packages using direct wheel download"""
        import os
        import sys
        import tempfile
        import zipfile
        import shutil
        import urllib.request

        current_dir = os.path.dirname(os.path.abspath(__file__))
        aftereffects_dir = os.path.dirname(os.path.dirname(current_dir))
        local_lib = os.path.join(aftereffects_dir, "lib", "python311", "site-packages")
        os.makedirs(local_lib, exist_ok=True)

        parent = self.tracker.dlg_footage if hasattr(self.tracker, 'dlg_footage') else None
        dlg = QDialog(parent)
        dlg.setWindowTitle("Install Required Dependencies")
        dlg.resize(550, 300)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        package_descriptions = {
            'OpenImageIO': 'OpenImageIO Python bindings (EXR, Deep EXR, AOV metadata)'
        }

        package_list = ""
        for pkg in missing_packages:
            desc = package_descriptions.get(pkg, 'Required dependency')
            package_list += f"<li><b>{pkg}</b> - {desc}</li>"

        msg = QLabel(
            "<h3>Required Dependencies Missing</h3>"
            "<p>The image resize feature requires the following packages:</p>"
            f"<ul>{package_list}</ul>"
            f"<p>Packages will be downloaded and extracted locally.</p>"
            f"<p><i>Install location:</i><br>"
            f"<code>{local_lib}</code></p>"
        )
        msg.setWordWrap(True)
        layout.addWidget(msg)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        button_layout.addWidget(cancel_btn)

        install_btn = QPushButton("Install")
        install_btn.setStyleSheet("background-color: #2e7d32; color: white; padding: 5px 15px;")
        install_btn.clicked.connect(dlg.accept)
        button_layout.addWidget(install_btn)

        layout.addLayout(button_layout)

        if dlg.exec_() != QDialog.Accepted:
            return

        progress = QProgressDialog(
            "Preparing installation...",
            None,
            0,
            0,
            parent
        )
        progress.setWindowTitle("Installing Dependencies")
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        temp_dir = tempfile.mkdtemp(prefix="oiio_install_")

        try:
            package_urls = {
                'OpenImageIO': [
                    (
                        "https://files.pythonhosted.org/packages"
                        "/ac/47/69007f17bc789f4c82d162323af339c350917b412d7e492c5fa942ac4407"
                        "/openimageio-3.1.8.0-cp311-cp311-win_amd64.whl"
                    ),
                ]
            }

            all_errors = []

            for package in missing_packages:
                if package not in package_urls:
                    error_msg = f"No URL found for package: {package}"
                    all_errors.append(error_msg)
                    print(f"[DEBUG INSTALL] {error_msg}")
                    continue

                urls = package_urls[package]
                success = False

                for url_idx, url in enumerate(urls):
                    try:
                        whl_filename = os.path.basename(url)
                        whl_path = os.path.join(temp_dir, whl_filename)

                        error_detail = f"Attempt {url_idx + 1}: {package}\nURL: {url}\nTarget: {whl_path}"
                        print(f"[DEBUG INSTALL] {error_detail}")
                        QApplication.processEvents()

                        progress.setLabelText(f"Downloading {package}...\n{whl_filename}")
                        QApplication.processEvents()

                        urllib.request.urlretrieve(url, whl_path)

                        if not os.path.exists(whl_path):
                            raise Exception(f"Download failed - file not created: {whl_path}")

                        file_size = os.path.getsize(whl_path)
                        print(f"[DEBUG INSTALL] Downloaded: {file_size} bytes")
                        QApplication.processEvents()

                        if file_size < 1000:
                            with open(whl_path, 'r', errors='ignore') as f:
                                content = f.read(500)
                            raise Exception(
                                f"Downloaded file too small ({file_size} bytes), "
                                f"possibly error page:\n{content[:200]}"
                            )

                        progress.setLabelText(f"Extracting {package}...")
                        QApplication.processEvents()

                        with zipfile.ZipFile(whl_path, 'r') as zip_ref:
                            namelist = zip_ref.namelist()
                            print(f"[DEBUG INSTALL] Wheel contains {len(namelist)} files")
                            print(f"[DEBUG INSTALL] First few: {namelist[:5]}")
                            QApplication.processEvents()

                            zip_ref.extractall(local_lib)

                        extracted_files = os.listdir(local_lib)
                        print(f"[DEBUG INSTALL] Local lib now has {len(extracted_files)} items")
                        QApplication.processEvents()

                        if package == 'OpenImageIO':
                            oiio_path = os.path.join(local_lib, "OpenImageIO")
                            if os.path.exists(oiio_path):
                                print(f"[DEBUG INSTALL] SUCCESS: OpenImageIO folder found at {oiio_path}")
                            else:
                                print(
                                    f"[DEBUG INSTALL] Warning: No OpenImageIO folder found. "
                                    f"Contents: {extracted_files[:20]}"
                                )

                        os.remove(whl_path)
                        print(f"[DEBUG INSTALL] Successfully installed {package}")
                        success = True
                        break

                    except Exception as e:
                        error_msg = f"URL {url_idx + 1} failed: {str(e)}"
                        all_errors.append(error_msg)
                        print(f"[DEBUG INSTALL] {error_msg}")
                        import traceback
                        traceback_str = traceback.format_exc()
                        print(f"[DEBUG INSTALL] {traceback_str}")
                        QApplication.processEvents()
                        continue

                if not success:
                    error_summary = (
                        f"Failed to install {package} after {len(urls)} attempts.\n\nErrors:\n"
                        + "\n".join(all_errors)
                    )
                    raise Exception(error_summary)

            progress.close()

            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

            result_dlg = QDialog(parent)
            result_dlg.setWindowTitle("Installation Complete")
            result_dlg.resize(400, 150)

            result_layout = QVBoxLayout()
            result_dlg.setLayout(result_layout)

            result_msg = QLabel(
                "<h3>Installation Successful!</h3>"
                f"<p>{', '.join(missing_packages)} have been installed locally.</p>"
                "<p><b>Please restart After Effects</b> for the changes to take effect.</p>"
            )
            result_msg.setWordWrap(True)
            result_layout.addWidget(result_msg)

            ok_btn = QPushButton("OK")
            ok_btn.clicked.connect(result_dlg.accept)
            result_layout.addWidget(ok_btn)

            result_dlg.exec_()

        except Exception as e:
            progress.close()
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            import traceback
            self.core.popup(
                f"Error during installation:\n{str(e)}\n\n"
                f"Details:\n{traceback.format_exc()}"
            )
