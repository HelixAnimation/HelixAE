"""Recoverable image replacement, independent of Qt and image libraries."""
import functools
import hashlib
import os
import shutil
import tempfile
import threading
import queue

_action_lock = threading.Lock()
_batch_lock = threading.Lock()


def run_background(work, on_progress, pump_events):
    """Run file work on a worker; deliver progress/events on the caller thread."""
    updates = queue.Queue()
    finished = threading.Event()
    outcome = {}

    def worker():
        try:
            outcome['result'] = work(lambda current, total: updates.put((current, total)))
        except Exception as exc:
            outcome['error'] = exc
        finally:
            finished.set()

    thread = threading.Thread(target=worker, name='HelixAE-image-resize')
    thread.start()
    while True:
        while True:
            try:
                current, total = updates.get_nowait()
            except queue.Empty:
                break
            on_progress(current, total)
        pump_events()
        if finished.wait(0.01):
            break
    thread.join()
    while not updates.empty():
        on_progress(*updates.get_nowait())
    if 'error' in outcome:
        raise outcome['error']
    return outcome['result']


def exclusive_resize_action(method):
    """Guard both modal confirmation and processEvents re-entry."""
    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        if not _action_lock.acquire(blocking=False):
            self.core.popup('An image resize action is already running.')
            return
        try:
            return method(self, *args, **kwargs)
        finally:
            _action_lock.release()
    return guarded


def _digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.digest()


def replace_image(source, backup_folder, render):
    """Render into a sibling; callback must validate it before returning True.

    Failed writes/validation/replacement leave the original untouched. Never
    overwrite an existing backup. Retain the verified backup after success.
    """
    temporary = None
    try:
        os.makedirs(backup_folder, exist_ok=True)
        backup = os.path.join(backup_folder, os.path.basename(source))
        with open(source, 'rb') as original, open(backup, 'xb') as saved:
            shutil.copyfileobj(original, saved)
            saved.flush()
            os.fsync(saved.fileno())
        fingerprint = _digest(source)
        if _digest(backup) != fingerprint:
            raise RuntimeError('Backup verification failed: %s' % backup)
        fd, temporary = tempfile.mkstemp(prefix='.helixae-resize-',
                                         suffix=os.path.splitext(source)[1],
                                         dir=os.path.dirname(os.path.abspath(source)))
        os.close(fd)
        outcome = render(source, temporary)
        if not outcome or not outcome[0]:
            raise RuntimeError(outcome[1] if outcome else 'Image renderer returned no result')
        if not os.path.getsize(temporary):
            raise RuntimeError('Resized output is empty')
        if _digest(source) != fingerprint:
            raise RuntimeError('Source changed during resizing; replacement aborted')
        with open(temporary, 'rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, source)
        return True, None
    except Exception as exc:
        return False, str(exc)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def resize_batch(files, backup_folder, render, progress=None, canceled=None):
    files = list(dict.fromkeys(files))
    result = dict(total=len(files), success=0, failed=0, skipped=0,
                  canceled=False, errors=[])
    if not _batch_lock.acquire(blocking=False):
        result.update(skipped=len(files), errors=['Another resize batch is running'])
        return result
    try:
        for index, source in enumerate(files):
            if progress:
                progress(index, len(files))
            if canceled and canceled():
                result['canceled'] = True
                break
            ok, error = replace_image(source, backup_folder, render)
            result['success' if ok else 'failed'] += 1
            if error:
                result['errors'].append('%s: %s' % (os.path.basename(source), error))
            if progress:
                progress(index + 1, len(files))
        result['skipped'] = result['total'] - result['success'] - result['failed']
        return result
    finally:
        _batch_lock.release()
