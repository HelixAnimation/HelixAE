"""Temporary read-only Cytonics audit. Opens AE sources, never saves or patches them.

Run locally with Python; requires ssh helix/nassk and the running AE CEP bridge.
Reports are written locally beside this script. No production metadata is written.
"""

import base64
import collections
import gzip
import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Scripts'))
import helixae_bridge as bridge
import helixae_protocol as protocol


def norm(path):
    return path.replace('\\', '/')


def ae(script):
    blob = base64.b64encode(gzip.compress(bridge.frame_ae_request(
        protocol.ensure_json_polyfill(script)))).decode('ascii')
    ps = """$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;
$c=New-Object Net.Sockets.TcpClient;$c.ReceiveTimeout=120000;
try{$c.Connect('127.0.0.1',9888);$s=$c.GetStream();
$z=New-Object IO.MemoryStream(,[Convert]::FromBase64String('%s'));
$g=New-Object IO.Compression.GzipStream($z,[IO.Compression.CompressionMode]::Decompress);
$m=New-Object IO.MemoryStream;$g.CopyTo($m);$r=$m.ToArray();$s.Write($r,0,$r.Length);
$m=New-Object IO.MemoryStream;while($true){$v=$s.ReadByte();if($v -lt 0){throw 'Premature EOF'};
if($v -eq 0){break};$m.WriteByte([byte]$v)};
[Console]::WriteLine([Text.Encoding]::UTF8.GetString($m.ToArray()))}finally{$c.Close()}
""" % blob
    result = subprocess.run(
        ['ssh', 'helix', 'powershell -NoProfile -NonInteractive -Command -'],
        input=ps.replace('\n', ' ') + '\n', capture_output=True, text=True,
        timeout=150, check=True)
    data, error = protocol.parse_json_response(result.stdout.lstrip('\ufeff'))
    if error or data.get('result') is not True:
        raise RuntimeError(error or data.get('details') or 'AE query failed')
    return data


def state():
    return ae(protocol._wrap('''
        return JSON.stringify({result:true,path:app.project.file?app.project.file.fsName:null,
            dirty:app.project.dirty});
'''))


def open_scene(path, restart_mcp=False):
    current = state()
    if current['dirty']:
        raise RuntimeError('AE has unsaved changes; refusing to change projects')
    if current['path'] and norm(current['path']).lower() == norm(path).lower():
        return
    print('Opening:', path, flush=True)
    # Limit suppression to project opening and always restore dialog handling.
    # Reuse the confirmed-open protocol builder, including js_string escaping.
    opening = protocol.build_open_scene(path).rstrip(';')
    ack = ae(protocol._wrap(
        'app.beginSuppressDialogs();\n'
        'try { return ' + opening + '; }\n'
        'finally { app.endSuppressDialogs(false);\n'
        + ('if(typeof startCommandChecker === "function") { startCommandChecker(); }\n'
           if restart_mcp else '')
        + '}\n'))
    if norm(ack.get('path', '')).lower() != norm(path).lower():
        raise RuntimeError('AE opened an unexpected project')


QUEUE_SCRIPT = protocol._wrap('''
    var items=[],q=app.project.renderQueue;
    for(var i=1;i<=q.numItems;i++) {
        var item=q.item(i),outputs=[];
        for(var j=1;j<=item.numOutputModules;j++) {
            var file=item.outputModule(j).file;outputs.push(file?file.fsName:null);
        }
        items.push({index:i,compId:String(item.comp.id),compName:item.comp.name,
            done:item.status===RQItemStatus.DONE,outputs:outputs});
    }
    return JSON.stringify({result:true,path:app.project.file.fsName,queue:items});
''')


NAS_QUERY = r'''
import os,json,re
def local(p):
 p=p.replace('\\','/')
 if p.lower().startswith('x:/'):return '/volume1/Renders/X/'+p[3:]
 if p.lower().startswith('z:/'):return '/volume1/Renders/'+p[3:]
 if p.lower().startswith('//nassk/renders/'):return '/volume1/Renders/'+p[16:]
 return None
def win(p):
 return p.replace('/volume1/Renders/X/','X:/').replace('/volume1/Renders/','Z:/')
result=[]
for path in PATHS:
 p=local(path)
 record={'path':path,'exists':os.path.isfile(p) if p else None}
 if p:
  directory=os.path.dirname(p)
  # Stop at the closest named Prism version, including missing metadata cases.
  while directory.startswith('/volume1/Renders/'):
   if re.match(r'^v\d{4}(?:_|$)',os.path.basename(directory)):
    record['version']=win(directory)
    f=directory+'/versioninfo.json';record['metadata_exists']=os.path.isfile(f)
    if record['metadata_exists']:
     try:record['metadata']=json.load(open(f,encoding='utf-8-sig'))
     except Exception as e:record['metadata_error']=str(e)
    break
   directory=os.path.dirname(directory)
  m=re.match(r'^(.*?)(\d{4,6})(\.(?:bgeo\.sc|[^.]+))$',os.path.basename(p))
  if m and os.path.isdir(os.path.dirname(p)):
   expression=re.compile('^'+re.escape(m.group(1))+r'(\d{'+str(len(m.group(2)))+'})'+re.escape(m.group(3))+'$')
   frames=sorted(int(hit.group(1)) for n in os.listdir(os.path.dirname(p)) for hit in [expression.match(n)] if hit and os.path.isfile(os.path.join(os.path.dirname(p),n)))
   if frames:
    gaps=[]
    for a,b in zip(frames,frames[1:]):
     if b>a+1:gaps.append([a+1,b-1])
    record['sequence']={'pattern':path[:-len(os.path.basename(p))]+m.group(1)+'#'*len(m.group(2))+m.group(3),'count':len(frames),'first':frames[0],'last':frames[-1],'gaps':gaps}
 result.append(record)
print(json.dumps(result))
'''


def inspect(paths):
    code = 'PATHS=' + repr(list(paths)) + '\n' + NAS_QUERY
    result = subprocess.run(['ssh', 'nassk', 'python3 -c ' + shlex.quote(code)],
                            capture_output=True, text=True, check=True, timeout=120)
    return json.loads(result.stdout)


def scan_version(node):
    source = node['source']
    open_scene(source)
    snapshot = ae(QUEUE_SCRIPT)
    if norm(snapshot['path']).lower() != norm(source).lower():
        raise RuntimeError('Project changed during queue inspection')
    version = node['version'].lower()
    matches = []
    for item in snapshot['queue']:
        if item['done']:
            for output in item['outputs']:
                if output and norm(output).rsplit('/', 1)[0].lower() == version:
                    # Check the exact movie filename; sequence tokens are resolved
                    # to an existing frame by the subsequent comp scan.
                    candidates = node['input_paths']
                    if (all(not p.lower().endswith(('.mov', '.mp4', '.avi')) for p in candidates)
                            or norm(output).lower() in {p.lower() for p in candidates}):
                        matches.append(item)
    identities = {item['compId'] for item in matches}
    if len(identities) != 1:
        raise RuntimeError('No unique Done queue mapping (%d comp identities)' % len(identities))
    match = matches[-1]
    scan = protocol.build_comp_dependency_script(match['compId']).rstrip(';')
    response = ae(protocol._wrap(
        'var scan=JSON.parse(' + scan + ');\n'
        'return JSON.stringify({result:true,path:app.project.file.fsName,scan:scan});\n'))
    if norm(response['path']).lower() != norm(source).lower():
        raise RuntimeError('Project changed during dependency scan')
    parsed, error = protocol.parse_comp_dependency_result(json.dumps(response['scan']))
    if error:
        raise RuntimeError(error)
    node['queue_match'] = match
    node['composition'] = parsed['composition']
    return sorted({record['path'] for record in parsed['footage']})


def write_report(report, output):
    """Produce a readable, cycle-guarded listing of every known level and path."""
    nodes, files = report['nodes'], report['files']
    ids = {key: 'P%03d' % (i + 1) for i, key in enumerate(sorted(nodes))}
    lines = [
        '# Cytonics — two sample renders, recursive dependency audit', '',
        'AE queue/comp scans performed 2026-10-19. No production metadata was changed.', '',
        '## Interpretation', '',
        '- AE nodes use completed render-queue output matches and recursive comp walks.',
        '- Houdini/Maya/export nodes use their existing publish metadata. Most are scene-wide:',
        '  this portion is a conservative recorded graph, not proven output-scoped inputs.',
        '- All reachable recorded edges are followed with cycle protection; no depth cutoff.',
        '- Missing versioninfo records leave unresolved branches. This is not a certified complete archive.',
        '- Sequence listings enumerate matching files on the NAS, with counts, frame spans and internal gaps.',
        '  They do not validate frame contents or prove that the expected frame range is complete.',
        '- Source scenes are collected as files. Their runtime contents were not inspected in Houdini/Maya.',
        '- Missing representative frames remain visible in this diagnostic report; production AE metadata',
        '  excludes missing paths, so this report must not be copied verbatim into renderDependencies.', '',
        '## Unresolved branches', '',
    ]
    lines.extend('- ' + error for error in report['errors'])
    for root in report['roots']:
        start = files[root]['version'].lower()
        depths, queue = {}, collections.deque([(start, 0)])
        while queue:
            key, depth = queue.popleft()
            if key in depths:
                continue
            depths[key] = depth
            for path in nodes[key]['dependencies']:
                child = files.get(path, {}).get('version', '').lower()
                if child in nodes and child not in depths:
                    queue.append((child, depth + 1))
        paths, sources = {root}, set()
        for key in depths:
            paths.update(nodes[key]['dependencies'])
            if nodes[key]['source']:
                sources.add(nodes[key]['source'])
        sequences = {files[p]['sequence']['pattern']: files[p]['sequence']
                     for p in paths if 'sequence' in files.get(p, {})}
        missing = sorted(p for p in paths | sources if files.get(p, {}).get('exists') is False)
        lines += ['', '## Sample: ' + root, '',
                  '- Reachable publish versions: %d' % len(depths),
                  '- Deepest shortest publish distance: %d (root = level 0)' % max(depths.values()),
                  '- Distinct referenced paths (including the root representative): %d' % len(paths),
                  '- Distinct source scenes: %d' % len(sources),
                  '- Sequence patterns: %d; matching sequence files: %d' % (
                      len(sequences), sum(s['count'] for s in sequences.values())),
                  '- Missing referenced/source paths: %d' % len(missing), '',
                  '### Publish versions by shortest dependency level', '']
        for depth in sorted(set(depths.values())):
            lines += ['', '#### Level %d' % depth, '']
            for key in sorted(k for k, d in depths.items() if d == depth):
                lines.append('- **%s** `%s` — %s' % (ids[key], nodes[key]['version'], nodes[key]['method']))
        lines += ['', '### Missing paths for this sample', '']
        lines.extend('- `' + path + '`' for path in missing)
    lines += ['', '## Publish details — every recorded outgoing edge', '',
              'IDs link repeated versions without duplicating whole subtrees. A path can be a sequence',
              'representative, a loose file, or an input to another publish listed here.', '']
    for key in sorted(nodes):
        node = nodes[key]
        lines += ['', '### %s — %s' % (ids[key], node['version']), '',
                  '- Method: ' + node['method'],
                  '- Metadata: `' + node['version'] + '/versioninfo.json`',
                  '- Source: `' + (node['source'] or '(unresolved)') + '`']
        if node.get('composition'):
            comp = node['composition']
            lines += ['- Composition: `%s` (ID %s); completed queue item %s' % (
                comp['name'], comp['id'], node['queue_match']['index'])]
        for path in node['dependencies']:
            record = files.get(path, {})
            child = record.get('version', '').lower()
            status = 'exists' if record.get('exists') is True else (
                'MISSING' if record.get('exists') is False else 'existence unverified')
            suffix = '; publish ' + ids[child] if child in ids else '; loose file'
            lines.append('- `%s` — %s%s' % (path, status, suffix))
            sequence = record.get('sequence')
            if sequence:
                lines.append('  - `%s`: %d files, frames %d–%d; internal gaps: %s' % (
                    sequence['pattern'], sequence['count'], sequence['first'], sequence['last'],
                    json.dumps(sequence['gaps'])))
    lines += ['', '## Source scenes and resources without publish metadata', '']
    for path, record in sorted(files.items()):
        if not record.get('version'):
            lines.append('- `%s` — %s' % (path, 'exists' if record.get('exists') is True else (
                'MISSING' if record.get('exists') is False else 'existence unverified')))
    with open(output, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    print('Readable report:', output, flush=True)


def main():
    root = 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/'
    roots = [root + 'Renders/2dRender/HighRes/v0015/SQ020-SH020_HighRes_v0015.mov',
             root + 'Renders/2dRender/BG/v0014/SQ020-SH020_BG_v0014_01001.png']
    original = state()
    if original['dirty']:
        raise RuntimeError('Save or resolve unsaved AE changes before running this audit')
    nodes, files, pending, errors = {}, {}, list(roots), []
    try:
        while pending:
            batch = sorted(set(pending) - set(files)); pending = []
            if not batch:
                break
            records = inspect(batch)
            new_versions = set()
            for record in records:
                path = record['path']; files[path] = record
                version = record.get('version')
                if not version:
                    continue
                key = version.lower()
                if key not in nodes:
                    data = record.get('metadata') or {}
                    nodes[key] = {'version': version, 'source': norm(data.get('sourceScene') or ''),
                                  'metadata_exists': record.get('metadata_exists', False),
                                  'input_paths': [], 'dependencies': [], 'method': 'pending'}
                    new_versions.add(key)
                nodes[key]['input_paths'].append(path)
            for key in sorted(new_versions):
                node = nodes[key]
                data = next((r.get('metadata', {}) for r in records
                             if r.get('version', '').lower() == key), {})
                try:
                    if node['source'].lower().endswith('.aep'):
                        node['dependencies'] = scan_version(node)
                        node['method'] = 'AE completed queue + composition walk'
                    elif not node['metadata_exists']:
                        node['method'] = 'UNRESOLVED: missing versioninfo.json'
                        errors.append(node['version'] + ': missing versioninfo.json')
                    else:
                        block = data.get('renderDependencies')
                        scoped = (isinstance(block, dict)
                                  and isinstance(block.get('dependencies'), list)
                                  and isinstance(block.get('externalFiles'), list)
                                  and all(isinstance(p, str) and p.strip() for p in
                                          block['dependencies'] + block['externalFiles']))
                        values = block if scoped else data
                        node['dependencies'] = sorted({norm(p) for field in ['dependencies', 'externalFiles']
                                                       for p in values.get(field, []) if isinstance(p, str) and p})
                        node['method'] = 'publish renderDependencies' if scoped else 'publish scene-wide metadata'
                    pending.extend(node['dependencies'])
                    if node['source']:
                        # Sources are collected as files, not recursively treated
                        # as render outputs or opened in other DCCs.
                        source_record = inspect([node['source']])[0]
                        files[node['source']] = source_record
                except Exception as exc:
                    node['method'] = 'UNRESOLVED: ' + str(exc)
                    errors.append(node['version'] + ': ' + str(exc))
                print(node['version'], node['method'], len(node['dependencies']), flush=True)
    finally:
        if original.get('path'):
            open_scene(original['path'])
        report = {'roots': roots, 'nodes': nodes, 'files': files, 'errors': errors,
                  'note': 'AE queue-scoped; non-AE metadata may remain scene-wide. No production JSON changed.'}
        output = os.path.join(os.path.dirname(__file__), 'cytonics-sample-dependency-audit.json')
        with open(output, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
        write_report(report, os.path.splitext(output)[0] + '.md')
        print('Report:', output, 'publish versions:', len(nodes), 'path records:', len(files),
              'unresolved:', len(errors), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--report-only']:
        path = os.path.join(os.path.dirname(__file__), 'cytonics-sample-dependency-audit.json')
        with open(path, encoding='utf-8') as handle:
            write_report(json.load(handle), os.path.splitext(path)[0] + '.md')
    else:
        main()
