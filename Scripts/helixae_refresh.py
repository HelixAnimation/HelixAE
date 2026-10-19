"""Worker-safe tracker preparation. No Prism or Qt imports or callbacks."""
import copy
import json
import os
import queue
import re
import socket
import threading
import time

import helixae_bridge
import helixae_protocol


class BackgroundJobs:
    """At most one worker per lane; superseded jobs cannot publish results."""
    def __init__(self):
        self.events = queue.Queue()
        self.running = {}
        self.pending = {}
        self.generations = {}
        self.closed = False

    def request(self, lane, work, replace=True):
        if self.closed:
            return None
        if lane in self.running and not replace:
            return self.generations[lane]
        generation = self.generations.get(lane, 0) + 1
        self.generations[lane] = generation
        self.pending[lane] = (generation, work)
        if lane in self.running:
            self.running[lane][1].set()
        else:
            self._start(lane)
        return generation

    def _start(self, lane):
        generation, work = self.pending.pop(lane)
        cancel = threading.Event()
        def run():
            def report(value):
                if not cancel.is_set():
                    self.events.put((lane, generation, 'progress', value))
            try:
                value = work(cancel, report)
                self.events.put((lane, generation, 'result', value))
            except Exception as error:
                self.events.put((lane, generation, 'error', str(error)))
            finally:
                self.events.put((lane, generation, 'finished', None))
        worker = threading.Thread(target=run, name='HelixAE-' + lane, daemon=True)
        self.running[lane] = (generation, cancel, worker)
        worker.start()

    def poll(self):
        while True:
            try:
                lane, generation, kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'finished':
                current = self.running.get(lane)
                if current and current[0] == generation:
                    self.running.pop(lane)
                    if lane in self.pending and not self.closed:
                        self._start(lane)
            elif not self.closed and self.generations.get(lane) == generation:
                yield lane, kind, value

    def invalidate(self, lane=None):
        lanes = set(self.pending) | set(self.running) if lane is None else {lane}
        for name in lanes:
            self.pending.pop(name, None)
            self.generations[name] = self.generations.get(name, 0) + 1
        for name, (_, cancel, _) in self.running.items():
            if name not in lanes:
                continue
            cancel.set()

    def stop(self):
        self.closed = True
        self.invalidate()
        deadline = time.monotonic() + 0.25
        for _, _, thread in list(self.running.values()):
            thread.join(max(0, deadline - time.monotonic()))


def ae_query(script, timeout=120):
    with socket.create_connection(('127.0.0.1', 9888), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(helixae_bridge.frame_ae_request(
            helixae_protocol.ensure_json_polyfill(script)))
        return helixae_bridge.recv_ae_response(connection)


def collect_snapshot(cancel, report):
    started = time.perf_counter()
    report({'text': 'Reading footage from After Effects…'})
    data, error = helixae_protocol.parse_tracker_snapshot(ae_query(helixae_protocol.build_tracker_snapshot()))
    if error:
        raise ValueError(error)
    data['snapshotSeconds'] = time.perf_counter() - started
    return data


def scene_identity(cancel, report):
    data, error = helixae_protocol.parse_tracker_identity(
        ae_query(helixae_protocol.build_get_tracker_identity(), timeout=3))
    if error:
        raise ValueError(error)
    return data


def base_version(path):
    parts = path.replace('\\', '/').split('/')
    for index, part in enumerate(parts):
        match = re.match(r'^(v\d{4,})(?:\b|_)', part)
        if match:
            return {'currentVersion': match.group(1), 'currentVersionFull': part,
                    'latestVersion': match.group(1), 'allVersions': [part],
                    'task': parts[index - 1] if index else 'Unknown', 'checkState': 'unchecked'}, '/'.join(parts[:index])
    return {'currentVersion': 'v0000', 'currentVersionFull': 'v0000',
            'latestVersion': 'v0000', 'allVersions': ['v0000'], 'task': 'Unknown',
            'checkState': 'not_applicable'}, None


MEDIA = {'.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx', '.mov', '.mp4',
         '.avi', '.mkv', '.tga', '.bmp', '.cin', '.hdr', '.psd', '.webm', '.m4v'}


def _has_media(folder, cancel):
    # Only version root and immediate AOV children, matching Prism render layouts.
    with os.scandir(folder) as entries:
        children = []
        for entry in entries:
            if cancel.is_set():
                return False
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in MEDIA:
                return True
            if entry.is_dir():
                children.append(entry.path)
    for child in children:
        with os.scandir(child) as entries:
            for entry in entries:
                if cancel.is_set():
                    return False
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in MEDIA:
                    return True
    return False


def _sort_version(name):
    match = re.match(r'^v(\d+)', name)
    return (-int(match.group(1)), len(name), name) if match else (0, 0, name)


def check_nas(snapshot, previous, cancel, report):
    """One scan per identifier directory and one metadata read per distinct folder."""
    started = time.perf_counter()
    paths = {record['path'] for record in snapshot['footage']}
    directories = {base_version(path)[1] for path in paths} - {None}
    versions = {}
    errors = []
    for index, folder in enumerate(sorted(directories)):
        if cancel.is_set():
            return None
        report({'text': 'Checking NAS versions: %d / %d' % (index + 1, len(directories)),
                'done': index, 'total': len(directories)})
        try:
            with os.scandir(folder) as entries:
                candidates = [entry.path for entry in entries
                              if re.match(r'^v\d{4,}', entry.name) and entry.is_dir()]
            versions[folder] = sorted([os.path.basename(path) for path in candidates
                                       if _has_media(path, cancel)], key=_sort_version)
        except OSError as error:
            errors.append('%s: %s' % (folder, error))
    metadata = {}
    results = {}
    for path in sorted(paths):
        if cancel.is_set():
            return None
        info, folder = base_version(path)
        if folder in versions:
            available = versions[folder]
            info.update(allVersions=available or [info['currentVersionFull']],
                        latestVersion=re.match(r'v\d+', available[0]).group(0) if available else None,
                        checkState='checked')
        elif folder:
            old = (previous or {}).get(path, {}).get('versionInfo')
            if old:
                info = dict(old)
            info['checkState'] = 'stale' if old else 'failed'
        directory = os.path.dirname(path)
        if directory not in metadata:
            try:
                with open(os.path.join(directory, 'versioninfo.json'), encoding='utf-8') as handle:
                    metadata[directory] = json.load(handle)
            except FileNotFoundError:
                metadata[directory] = None
            except (OSError, ValueError) as error:
                metadata[directory] = None
                errors.append('Metadata %s: %s' % (directory, error))
        results[path] = {'versionInfo': info, 'published': metadata[directory]}
    bypasses = None
    scene_path = snapshot.get('scene', {}).get('path', '')
    if scene_path.lower().endswith('.aep') and not cancel.is_set():
        try:
            with open(os.path.splitext(scene_path)[0] + '_bypassed.json', encoding='utf-8') as handle:
                value = json.load(handle)
                if isinstance(value, dict):
                    bypasses = value
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            errors.append('Legacy bypass metadata: %s' % error)
    return {'paths': results, 'errors': errors, 'bypasses': bypasses, 'seconds': time.perf_counter() - started,
            'directoryScans': len(directories), 'metadataReads': len(metadata)}


def build_inventory(snapshot, classify, nas=None):
    """No filesystem/Prism calls: AE actual values never overwritten by published data."""
    hierarchy = {name: {} for name in ('3D Renders', '2D Renders', 'Resources', 'External', 'Comps')}
    for source in snapshot['footage']:
        row = dict(source)
        path = row['path']
        shot, identifier, aov, group, kind = classify(path, row['name'])
        if group not in hierarchy:
            group = 'Resources'
        enrichment = (nas or {}).get(path, {})
        info = copy.deepcopy(enrichment.get('versionInfo') or base_version(path)[0])
        row.update(versionInfo=info, group=group, hierarchy_type=kind, shotName=shot,
                   published=enrichment.get('published'),
                   isLatest=(info['checkState'] == 'checked' and info['currentVersion'] == info['latestVersion']))
        if kind == 'render':
            hierarchy[group].setdefault(shot, {}).setdefault(identifier, {}).setdefault(aov, []).append(row)
        else:
            row['relative_path'] = identifier or os.path.splitext(row['name'])[0]
            hierarchy[group].setdefault(row['relative_path'], []).append(row)
    for comp in snapshot['comps']:
        hierarchy['Comps'].setdefault(comp['category'], []).append(dict(comp))
    return hierarchy


def fetch_kitsu(context, cancel, report, session_factory=None):
    """Own authenticated HTTP session, bounded waits, no manager/login/Qt calls."""
    if not context or not context.get('token'):
        raise ValueError('Kitsu is not authenticated; sign in through Prism and refresh Kitsu')
    if session_factory is None:
        import requests
        session_factory = requests.Session
    started = time.perf_counter()
    count = 0
    with session_factory() as session:
        session.verify = context.get('verify', True)
        session.cert = context.get('cert')
        session.headers.update({'Authorization': 'Bearer ' + context['token'], 'User-Agent': 'HelixAE'})
        def get(path):
            nonlocal count
            if cancel.is_set():
                raise RuntimeError('Kitsu check canceled')
            count += 1
            report({'text': 'Updating Kitsu data…'})
            response = session.get(context['host'].rstrip('/') + '/data/' + path.lstrip('/'), timeout=(5, 20))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, (dict, list)):
                raise ValueError('Malformed Kitsu response')
            return data
        projects = get('projects')
        if not isinstance(projects, list):
            raise ValueError('Malformed Kitsu project list')
        matches = [project for project in projects if project.get('name') == context['projectName']]
        if len(matches) != 1:
            raise ValueError('Kitsu project selection is missing or ambiguous')
        project = matches[0]
        project_id = str(project['id'])
        sequences = get('projects/%s/sequences' % project_id)
        shots = get('projects/%s/shots' % project_id)
        if not isinstance(sequences, list) or not isinstance(shots, list):
            raise ValueError('Malformed Kitsu shot/sequence list')
        episodic = project.get('has_episodes') or any(
            entry.get('parent_id') not in (None, project_id) for entry in sequences)
        episodes = get('projects/%s/episodes' % project_id) if episodic else []
        resolutions = {}
        for resolution_id in {str((shot.get('data') or {}).get('resolution_id')) for shot in shots
                              if (shot.get('data') or {}).get('resolution_id')}:
            resolutions[resolution_id] = get('resolutions/' + resolution_id)
    sequence_names = {entry['id']: entry.get('name', '') for entry in sequences}
    if episodes and not context.get('useEpisodes'):
        episode_names = {entry['id']: entry.get('name', '') for entry in episodes}
        for entry in sequences:
            episode = episode_names.get(entry.get('parent_id'))
            if episode:
                sequence_names[entry['id']] = episode + ' - ' + entry.get('name', '')
    def resolution(value, fallback):
        match = re.search(r'(\d+)\s*[xX]\s*(\d+)', str(value or ''))
        if match:
            return int(match.group(1)), int(match.group(2))
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0]), int(value[1])
        return fallback
    project_res = resolution(project.get('resolution'), (context.get('width', 1920), context.get('height', 1080)))
    fps = float(project.get('fps') or context.get('fps') or 25)
    records = []
    for shot in shots:
        if shot.get('canceled'):
            continue
        data = shot.get('data') or {}
        specific = resolutions.get(str(data.get('resolution_id')), {})
        width, height = resolution(data.get('resolution') or specific.get('name'), project_res)
        start, end = data.get('frame_in'), data.get('frame_out')
        records.append({'shot': shot.get('name', ''), 'sequence': sequence_names.get(shot.get('parent_id'), ''),
                        'id': shot['id'], 'start': start, 'end': end,
                        'frameRange': '%s-%s' % (start, end) if start is not None and end is not None else None,
                        'fps': fps, 'width': width, 'height': height, 'resolution': '%dx%d' % (width, height)})
    return {'shots': records, 'seconds': time.perf_counter() - started, 'requests': count}
