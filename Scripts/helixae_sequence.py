"""Read-only, worker-safe sequence checks. No image decoding or source writes."""
import os
import re

IMAGE_EXTENSIONS = {'.exr', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.dpx', '.cin', '.bmp', '.tga'}


def sequence_pattern(path):
    name = os.path.basename(path.replace('\\', '/'))
    stem, extension = os.path.splitext(name)
    match = re.match(r'^(.*?)(\d+)$', stem)
    if extension.lower() not in IMAGE_EXTENSIONS or not match:
        return None
    prefix, digits = match.groups()
    return re.compile(r'^' + re.escape(prefix) + r'(\d{' + str(len(digits)) + r'})' + re.escape(extension) + r'$', re.IGNORECASE)


def check_sequences(paths, cancel, report):
    """Find interior gaps and empty files; unspecified sequence boundaries stay unknown."""
    results, listings = [], {}
    paths = list(dict.fromkeys(paths))
    for index, path in enumerate(paths):
        if cancel.is_set():
            break
        report({'text': 'Validating sequence files', 'done': index, 'total': len(paths)})
        row = {'path': path, 'files': 0, 'missing': [], 'empty': [], 'errors': [], 'range': None}
        pattern = sequence_pattern(path)
        if pattern is None:
            row['errors'].append('Not a numbered image sequence')
            results.append(row)
            continue
        folder = os.path.dirname(path)
        try:
            if folder not in listings:
                listings[folder] = sorted(os.listdir(folder))
            frames = set()
            for name in listings[folder]:
                if cancel.is_set():
                    break
                match = pattern.match(name)
                if not match:
                    continue
                frames.add(int(match.group(1)))
                row['files'] += 1
                try:
                    if os.stat(os.path.join(folder, name)).st_size == 0:
                        row['empty'].append(name)
                except OSError as error:
                    row['errors'].append('%s: %s' % (name, error))
            ordered = sorted(frames)
            if ordered:
                row['range'] = [ordered[0], ordered[-1]]
                row['missing'] = [[left + 1, right - 1] for left, right in zip(ordered, ordered[1:]) if right > left + 1]
            else:
                row['errors'].append('No matching sequence files found')
        except OSError as error:
            row['errors'].append(str(error))
        results.append(row)
    report({'text': 'Sequence validation complete', 'done': len(results), 'total': len(paths)})
    return {'results': results, 'canceled': cancel.is_set()}


def format_results(value):
    lines = ['Read-only sequence validation (observed bounds only; image contents not decoded).']
    if value['canceled']:
        lines.append('Canceled — results are incomplete.')
    for row in value['results']:
        lines.extend(['', row['path'], '%d matching files; observed range: %s' % (row['files'], row['range'])])
        gaps = ', '.join(str(a) if a == b else '%d–%d' % (a, b) for a, b in row['missing'][:30])
        lines.append('Missing interior frames: ' + (gaps or 'none'))
        if len(row['missing']) > 30:
            lines.append('… %d additional gap ranges' % (len(row['missing']) - 30))
        lines.append('Empty files: %d' % len(row['empty']))
        lines.extend(row['empty'][:30])
        lines.extend('Check failed: ' + error for error in row['errors'][:10])
    return '\n'.join(lines)
