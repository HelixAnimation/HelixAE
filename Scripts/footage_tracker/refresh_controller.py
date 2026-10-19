"""GUI-thread coordinator; workers operate exclusively on captured plain data."""
import copy
import json
import time

from qtpy.QtCore import QObject, QTimer, Qt
from qtpy.QtWidgets import QApplication, QLabel

import helixae_refresh
import helixae_sequence
from . import kitsu_keys, xmp_payload
from .utils import FootageUtils


class RefreshController(QObject):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.core = main.core
        self.jobs = helixae_refresh.BackgroundJobs()
        self.tracker = None
        self.scene = None
        self.project = getattr(self.core, 'projectPath', '')
        self.snapshot = None
        self.nas = {}
        self.kitsu = {}
        self._legacy_bypasses = None
        self.status = {}
        self.errors = {}
        self._started = time.perf_counter()
        self._attached_at = self._started
        self._nas_after_snapshot = True
        self._kitsu_after_snapshot = True
        self._kitsu_requested = False
        self._render_due = False
        self._rendered_snapshot = None
        self._rendered_dialog = None
        self._rendered_grouping = None
        self._next_probe = 0
        self._last_completed = None
        self._last_scene_callback = 0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.stop)

    def stop(self):
        self.timer.stop()
        self.jobs.stop()

    def validate_sequences(self, paths):
        paths = tuple(dict.fromkeys(paths))
        if not paths:
            return
        self.status['integrity'] = {'text': 'Validating sequence files…'}
        self.errors.pop('integrity', None)
        self.jobs.request('integrity', lambda cancel, report: helixae_sequence.check_sequences(paths, cancel, report))

    def cancel_sequence_validation(self):
        self.jobs.invalidate('integrity')
        self.status.pop('integrity', None)

    def invalidate(self):
        self.jobs.invalidate()
        self.scene = None
        self.snapshot = None
        self.nas = {}
        self.kitsu = {}
        self._legacy_bypasses = None
        self.status = {}
        self.errors = {}
        self._last_completed = None
        self._nas_after_snapshot = True
        self._kitsu_after_snapshot = True
        self._kitsu_requested = False
        self._render_due = False
        self.project = getattr(self.core, 'projectPath', '')
        if self.tracker:
            self.tracker.kitsu_integration.kitsuShotData = {}
            self.tracker._stored_hierarchy = None
            self.tracker._footage_snapshot_identity = None
            self.tracker.data_parser._prepared_scene_path = None
            if getattr(self.tracker, 'dlg_footage', None):
                self.tracker.tw_footage.setEnabled(False)

    def scene_opened(self):
        # Callback may precede AE's confirmed completion. A cheap probe schedules
        # the snapshot; no network/AE call takes place in this GUI callback.
        now = time.monotonic()
        if now - self._last_scene_callback < 0.5:
            return
        self._last_scene_callback = now
        self.invalidate()
        self._next_probe = 0

    def attach(self, tracker):
        self.tracker = tracker
        self._attached_at = time.perf_counter()
        self._apply_kitsu()
        if self.snapshot:
            self._render_due = True
        elif 'snapshot' not in self.jobs.running:
            self.refresh_footage(initial=True)
        self._progress()

    def refresh_footage(self, initial=False):
        self._started = time.perf_counter()
        self._last_completed = None
        self._nas_after_snapshot = True
        self._kitsu_after_snapshot = (initial or self.snapshot is None) and not self._kitsu_requested
        # Old NAS results for the old inventory must not land during a new query.
        if 'nas' in self.jobs.running:
            self.jobs.generations['nas'] += 1
            self.jobs.running['nas'][1].set()
            self.jobs.pending.pop('nas', None)
        self.status.pop('nas', None)
        self.errors.pop('snapshot', None)
        self.status['snapshot'] = {'text': 'Reading footage from After Effects…'}
        self.jobs.request('snapshot', helixae_refresh.collect_snapshot)
        self._progress()

    def _capture_kitsu(self):
        # These calls only capture Prism state. Do not call getShots, getFps,
        # ensureLoggedIn or makeDbRequest here: inspected methods contain Qt/UI.
        manager_plugin = self.core.getPlugin('ProjectManagement')
        manager = getattr(manager_plugin, 'curManager', None)
        if manager is None:
            managers = getattr(manager_plugin, 'managers', {})
            candidates = managers.values() if isinstance(managers, dict) else (managers or [])
            manager = next((candidate for candidate in candidates
                            if getattr(candidate, 'name', '') == 'Kitsu'), None)
        if manager is None or getattr(manager, 'name', '') != 'Kitsu':
            return None
        gazu = getattr(manager, 'gazu', None)
        client = getattr(getattr(gazu, 'client', None), 'default_client', None)
        if not client:
            return None
        tokens = dict(getattr(client, 'tokens', {}) or {})
        session = getattr(client, 'session', None)
        context = {'host': getattr(client, 'host', ''), 'token': tokens.get('access_token'),
                   'verify': getattr(session, 'verify', True), 'cert': getattr(session, 'cert', None),
                   'projectName': self.core.getConfig('prjManagement', 'kitsu_projectName', config='project'),
                   'useEpisodes': self.core.getConfig('globals', 'useEpisodes', config='project') or False,
                   'fps': self.core.getConfig('globals', 'fps', config='project') or 25,
                   'width': self.core.getConfig('globals', 'width', config='project') or 1920,
                   'height': self.core.getConfig('globals', 'height', config='project') or 1080}
        return context

    def refresh_kitsu(self):
        self._kitsu_requested = True
        self._last_completed = None
        self._started = time.perf_counter()
        try:
            context = self._capture_kitsu()
        except Exception:
            context = None
        self.status['kitsu'] = {'text': 'Updating Kitsu data…'}
        self.errors.pop('kitsu', None)
        self.jobs.request('kitsu', lambda cancel, report: helixae_refresh.fetch_kitsu(context, cancel, report))
        self._progress()

    def _request_nas(self):
        snapshot, previous = copy.deepcopy(self.snapshot), copy.deepcopy(self.nas)
        self.status['nas'] = {'text': 'Checking NAS versions…'}
        self.errors.pop('nas', None)
        self.jobs.request('nas', lambda cancel, report: helixae_refresh.check_nas(snapshot, previous, cancel, report))

    def _apply_kitsu(self):
        if not self.tracker:
            return
        integration = self.tracker.kitsu_integration
        integration.kitsuShotData = self.kitsu
        integration._kitsu_cache_project = self.project
        if self.kitsu:
            integration._kitsu_cache_time = time.time()
        integration.kitsuLoadError = self.errors.get('kitsu', '')

    def _poll(self):
        if getattr(self.core, 'projectPath', '') != self.project:
            self.invalidate()
            self._next_probe = 0
        now = time.monotonic()
        # Probe only when not already querying AE; no inventory scans on a timer.
        if now >= self._next_probe and 'identity' not in self.jobs.running and 'snapshot' not in self.jobs.running:
            self._next_probe = now + 3
            self.jobs.request('identity', helixae_refresh.scene_identity, replace=False)
        for lane, kind, value in self.jobs.poll():
            if kind == 'progress':
                self.status[lane] = value
            elif kind == 'error':
                self.status.pop(lane, None)
                if lane == 'identity':
                    self.errors['bridge'] = 'AE bridge unavailable — showing last prepared data'
                else:
                    self.errors[lane] = value
                    print('[TRACKER] %s check failed: %s' % (lane, value))
            elif kind == 'result':
                self.status.pop(lane, None)
                if lane == 'identity':
                    self.errors.pop('bridge', None)
                    if self.scene != value:
                        self.invalidate()
                        self.scene = value
                        self.refresh_footage(initial=True)
                    elif self.snapshot is None and 'snapshot' not in self.jobs.running:
                        self.refresh_footage(initial=True)
                elif lane == 'snapshot':
                    if self.scene is not None and self.scene != value['scene']:
                        # The user changed the AE scene while the job was running.
                        self.invalidate()
                    self.scene = value['scene']
                    self.snapshot = value
                    self._render_due = True
                    print('[TIMING] AE snapshot %.3fs; %d footage, %d comps, %s layer visits' % (
                        value['snapshotSeconds'], len(value['footage']), len(value['comps']), value.get('layerVisits', '?')))
                    if self._nas_after_snapshot:
                        self._request_nas()
                    if self._kitsu_after_snapshot and not self._kitsu_requested:
                        self.refresh_kitsu()
                elif lane == 'nas' and value is not None:
                    self.nas = value['paths']
                    self._legacy_bypasses = value.get('bypasses')
                    if value['errors']:
                        self.errors['nas'] = 'Some NAS checks failed — previous results retained where available'
                    print('[TIMING] NAS %.3fs; %d directory scans, %d metadata reads' % (
                        value['seconds'], value['directoryScans'], value['metadataReads']))
                    self._render_due = True
                elif lane == 'kitsu':
                    self.kitsu, _ = kitsu_keys.build_shot_key_map(value['shots'], lambda shot: shot)
                    self._apply_kitsu()
                    print('[TIMING] Kitsu %.3fs; %d HTTP requests' % (value['seconds'], value['requests']))
                    self._render_due = True
                elif lane == 'integrity':
                    if self.tracker and getattr(self.tracker, 'dlg_footage', None):
                        self.tracker.showSelectableMessage('Sequence file validation', helixae_sequence.format_results(value))
        if (self._render_due and self.snapshot and self.tracker and getattr(self.tracker, 'dlg_footage', None)
                and not QApplication.activeModalWidget() and not QApplication.activePopupWidget()):
            self._render_due = False
            self._render()
        self._progress()

    def update_bypasses(self, ignored_items, scene_path):
        """Repaint cached issue cells after persistence; never request new scans."""
        if not self.scene or self.scene['path'].replace('\\', '/') != (scene_path or '').replace('\\', '/'):
            return
        ignored = {key: set(ignored_items.get(key, [])) for key in
                   ('outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch')}
        if self.tracker:
            self.tracker.startup_warnings._ignored_items_cache = ignored
            self.tracker.startup_warnings._ignored_items_cache_file = self.scene['path']
            self.tracker._prepared_ignored_items = ignored
        # The timer delivers this after menus/dialogs close, using the same
        # snapshot and incremental cells so rows, selection and scroll survive.
        self._render_due = bool(self.snapshot)

    def _render(self):
        tracker = self.tracker
        dialog = tracker.dlg_footage
        tree_ops = tracker.tree_ops
        tree = tracker.tw_footage
        expanded = tree_ops.saveTreeExpansionState()
        scroll = tree.verticalScrollBar().value()
        selected = set()
        for item in tree.selectedItems():
            data = item.data(0, Qt.UserRole) or {}
            if data.get('id') is not None:
                selected.add((data.get('type'), str(data['id'])))
        nas = copy.deepcopy(self.nas)
        if 'nas' in self.status:
            for entry in nas.values():
                if entry['versionInfo'].get('checkState') == 'checked':
                    entry['versionInfo']['checkState'] = 'cached'
        hierarchy = helixae_refresh.build_inventory(self.snapshot, FootageUtils.extractHierarchy, nas)
        tree_ops.shot_alternatives = tree_ops.hierarchy_builder.buildShotAlternativesIndex(hierarchy)
        for group, attr in [('3D Renders', 'group_by_mode_3d'), ('2D Renders', 'group_by_mode_2d')]:
            if getattr(tracker, attr, 'shot') == 'identifier':
                hierarchy[group] = tree_ops.hierarchy_builder.pivot_to_identifier_first(hierarchy[group])
        config_ignored = self.core.getConfig('footage_tracker', 'bypassed_items', config='project') or {}
        ignored = {key: set(config_ignored.get(key, [])) for key in
                   ('outdated', 'fps_mismatch', 'frame_range_mismatch', 'resolution_mismatch')}
        payload, error = xmp_payload.extract_payload(self.snapshot.get('xmp', ''), 'BypassedItems')
        if not error and payload:
            try:
                data = json.loads(payload)
                ignored = {key: set(data.get(key, [])) for key in ignored}
            except (ValueError, TypeError):
                pass
        elif self._legacy_bypasses:
            ignored = {key: set(self._legacy_bypasses.get(key, [])) for key in ignored}
        # Prefer currently edited bypass state, otherwise snapshot/config fallback.
        cached = getattr(tracker.startup_warnings, '_ignored_items_cache', None)
        if cached is not None and getattr(tracker.startup_warnings, '_ignored_items_cache_file', None) == self.scene['path']:
            ignored = cached
        tracker._prepared_ignored_items = ignored
        tracker.data_parser._prepared_scene_path = self.scene['path']
        started = time.perf_counter()
        enabled = tree.updatesEnabled()
        tree.setUpdatesEnabled(False)
        try:
            grouping = (tracker.group_by_mode_3d, tracker.group_by_mode_2d)
            if (self._rendered_snapshot is self.snapshot and self._rendered_dialog is dialog
                    and self._rendered_grouping == grouping):
                tree_ops.tree_renderer.updatePreparedCells(hierarchy)
            else:
                tree_ops.tree_renderer.renderHierarchyTree(hierarchy)
            self._rendered_snapshot, self._rendered_dialog, self._rendered_grouping = self.snapshot, dialog, grouping
            tree_ops.restoreTreeExpansionState(expanded)
            records_by_id = {str(row['footageId']): row for row in self.snapshot['footage']}
            stack = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
            while stack:
                item = stack.pop()
                data = item.data(0, Qt.UserRole) or {}
                record = records_by_id.get(str(data.get('id'))) if data.get('type') == 'footage' else None
                published = (self.nas.get(record['path'], {}).get('published') if record else None)
                if isinstance(published, dict):
                    data['published'] = published
                    item.setData(0, Qt.UserRole, data)
                    text = '\n\nPublished metadata (AE values above remain authoritative):\n' + '\n'.join(
                        '%s: %s' % (key, published[key]) for key in
                        ('startframe', 'endframe', 'frameRange', 'fps', 'resolution', 'duration') if key in published)
                    for column in (3, 4, 5):
                        marker = '\n\nPublished metadata (AE values above remain authoritative):'
                        item.setToolTip(column, item.toolTip(column).split(marker)[0] + text)
                        widget = tree.itemWidget(item, column)
                        if widget:
                            for label in widget.findChildren(QLabel):
                                label.setToolTip(label.toolTip().split(marker)[0] + text)
                if (data.get('type'), str(data.get('id'))) in selected:
                    item.setSelected(True)
                stack.extend(item.child(i) for i in range(item.childCount()))
            tracker.ui_setup.applyFilter()
            tree.verticalScrollBar().setValue(scroll)
            tree_ops.updateStatistics()
            tree.setEnabled(True)
            tracker._stored_hierarchy = hierarchy
            tracker._footage_snapshot_identity = (str(self.project).replace('\\', '/'), self.scene['path'].replace('\\', '/'))
            self.main._footage_hierarchy = hierarchy
            tracker.updateCheckIssuesButton()
        except Exception as error:
            self.errors['display'] = 'Could not update footage list: ' + str(error)
        else:
            self.errors.pop('display', None)
        finally:
            tree.setUpdatesEnabled(enabled)
        print('[TIMING] UI batch %.3fs; useful display %.3fs after request / %.3fs after opening' % (
            time.perf_counter() - started, time.perf_counter() - self._started, time.perf_counter() - self._attached_at))

    def _progress(self):
        if not self.tracker or not getattr(self.tracker, 'dlg_footage', None):
            return
        bar = getattr(self.tracker, 'refreshProgress', None)
        if bar is None:
            return
        states = [value for lane, value in self.status.items() if lane != 'identity']
        if self._render_due and self.snapshot:
            states.append({'text': 'Updating list…'})
        incomplete = bool(states or self.errors)
        if getattr(self.tracker, '_checks_incomplete', None) != incomplete:
            self.tracker._checks_incomplete = incomplete
            self.tracker.updateCheckIssuesButton()
        if states:
            bar.show()
            # A numeric total only describes the NAS directory stage. Overlapping
            # or network stages use an indeterminate animation, never fake %.
            if len(states) == 1 and states[0].get('total', 0) > 0:
                bar.setRange(0, states[0]['total'])
                bar.setValue(states[0].get('done', 0))
            else:
                bar.setRange(0, 0)
            text = ' | '.join(state['text'] for state in states)
            if self.errors:
                text += ' | ' + ' | '.join('%s: %s' % pair for pair in self.errors.items())
            self.tracker.dlg_footage.statusBar.setText(text)
        else:
            bar.hide()
            if self._last_completed is None:
                self._last_completed = time.perf_counter() - self._started
            if self.errors:
                self.tracker.dlg_footage.statusBar.setText(' | '.join('%s: %s' % pair for pair in self.errors.items()))
            elif self.snapshot:
                self.tracker.dlg_footage.statusBar.setText('Updated in %.2fs — Footage and Kitsu refresh independently' % self._last_completed)
