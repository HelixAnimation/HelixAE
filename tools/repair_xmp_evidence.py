"""One-off XMP-evidence repairs for the last unscoped AE render versions.

Each target movie embeds a creatorAtom:aeProjectLink (compositionID and
fullPath) that After Effects wrote at render time. That proves the
composition identity without enumerating the render queue - the step that
reliably crashed AE on SQ020-SH020_HighRes_v0040.aep. The dependency walk
then runs as ONE script round trip immediately after the project opens.

Publishing reuses the verified PUBLISH transaction from
repair_selected_render_dependencies (backup-first, atomic, field-preserving)
and records the result in the existing run journal so --verify-only covers it.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import audit_render_dependency_samples as audit
import helixae_protocol as protocol
import helixae_render_deps as deps
import repair_selected_render_dependencies as repair

JOURNAL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'cytonics-full-repair-20261019T182222Z.json')

MOVIES = {
    'x:/cytonics_cyt108/03_production/shots/sq020/sh020/renders/2drender/highres/v0011':
        'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Renders/2dRender/HighRes/v0011/SQ020-SH020_HighRes_v0011.mov',
    'x:/cytonics_cyt108/03_production/shots/sq020/sh010/renders/2drender/bg/v0005':
        'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH010/Renders/2dRender/BG/v0005/SQ020-SH010_BG_v0005.mov',
    'x:/cytonics_cyt108/03_production/shots/sq020/sh010/renders/2drender/bg/v0006':
        'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH010/Renders/2dRender/BG/v0006/SQ020-SH010_BG_v0006.mov',
}

NAME_HINTS = {
    'x:/cytonics_cyt108/03_production/shots/sq020/sh020/renders/2drender/highres/v0011': 'HighRes',
    'x:/cytonics_cyt108/03_production/shots/sq020/sh010/renders/2drender/bg/v0005': 'BG',
    'x:/cytonics_cyt108/03_production/shots/sq020/sh010/renders/2drender/bg/v0006': 'BG',
}

XMP_QUERY = r'''
import json,re,sys,hashlib
def local(p):
 p=p.replace('\\','/')
 return '/volume1/Renders/X/'+p[3:] if p.lower().startswith('x:/') else None
def moov(path):
 with open(path,'rb') as f:
  while True:
   h=f.read(8)
   if len(h)<8:return None
   size=int.from_bytes(h[:4],'big');kind=h[4:]
   if kind==b'moov':return f.read(size-8)
   if size==1:size=int.from_bytes(f.read(8),'big');f.seek(size-16,1)
   else:f.seek(size-8,1)
result={}
for version,movie in json.load(sys.stdin).items():
 d=local(version);f=local(movie)
 metadata=json.load(open(d+'/versioninfo.json',encoding='utf-8-sig'))
 raw=open(f,'rb').read()
 m=re.search(rb'<x:xmpmeta[\s\S]*?</x:xmpmeta>',moov(f))
 if not m:raise RuntimeError('Movie has no XMP: '+movie)
 xml=m.group(0).decode('utf-8',errors='replace')
 link=re.search(r'<creatorAtom:aeProjectLink[^>]*>',xml)
 if not link:raise RuntimeError('Movie has no aeProjectLink: '+movie)
 tag=link.group(0)
 def attr(name):
  hit=re.search(r'creatorAtom:'+name+r'="([^"]*)"',tag)
  if not hit:raise RuntimeError('Movie XMP missing '+name+': '+movie)
  return hit.group(1)
 result[version]={'movie':movie,'movie_sha256':hashlib.sha256(raw).hexdigest(),
                  'composition_id':attr('compositionID'),'full_path':attr('fullPath'),
                  'render_queue_item_id':attr('renderQueueItemID'),
                  'metadata':metadata}
print(json.dumps(result))
'''


def nas(code, payload=None):
    result = subprocess.run(['ssh', 'nassk', 'python3 -c ' + shlex.quote(code)],
                            input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, timeout=300, check=True)
    return json.loads(result.stdout)


def scan_script(comp_id, name_hint):
    """ONE round trip: identity check plus the full comp dependency walk."""
    walk = protocol.build_comp_dependency_script(comp_id).rstrip(';')
    body = (
        '        if (!app.project || !app.project.file) throw new Error("No saved project open");\n'
        '        var target = app.project.itemByID(%s);\n'
        '        if (!target || !(target instanceof CompItem)) throw new Error("Composition not found by ID");\n'
        '        if (target.name.indexOf(%s) < 0) throw new Error("Unexpected composition name: " + target.name);\n'
        '        var scan = JSON.parse(' + walk + ');\n'
        '        if (scan.result !== true) throw new Error(scan.details || "dependency scan failed");\n'
        '        return JSON.stringify({result:true, path:app.project.file.fsName, compName:target.name, scan:scan});\n'
    ) % (protocol._as_id(comp_id, 'composition id'), protocol.js_string(name_hint))
    return protocol._wrap(body)


def scan_with_evidence(evidence, name_hint):
    """Open the XMP scene and scan the linked composition without the queue."""
    scene = audit.norm(evidence['full_path'])
    audit.open_scene(scene)
    response = audit.ae(scan_script(evidence['composition_id'], name_hint))
    if audit.norm(response['path']).lower() != scene.lower():
        raise RuntimeError('Project changed during dependency scan')
    parsed, error = protocol.parse_comp_dependency_result(json.dumps(response['scan']))
    if error:
        raise RuntimeError(error)
    if parsed['composition']['id'] != str(evidence['composition_id']):
        raise RuntimeError('Composition identity mismatch')
    return parsed['composition'], sorted({r['path'] for r in parsed['footage']}), response['compName']


def check_evidence(version, evidence):
    """The render artifact and the publish metadata must name the same source."""
    metadata = evidence['metadata']
    source = audit.norm(metadata.get('sourceScene') or '')
    if source.lower() != audit.norm(evidence['full_path']).lower():
        raise RuntimeError('Movie XMP fullPath disagrees with versioninfo sourceScene')
    if int(evidence['composition_id']) <= 0:
        raise RuntimeError('Invalid composition id in movie XMP')
    return source


def repair_target(version, classifier, apply=True):
    key = version.lower()
    movie = MOVIES.get(key)
    if not movie:
        raise RuntimeError('No movie evidence mapping for ' + version)
    version = movie.rsplit('/', 1)[0]
    evidence = nas(XMP_QUERY, {version: movie})[version]
    source = check_evidence(version, evidence)
    name_hint = NAME_HINTS[key]
    composition, paths, comp_name = scan_with_evidence(evidence, name_hint)
    existence = audit.inspect(paths) if paths else []
    exists = {r['path']: r.get('exists') for r in existence}
    if any(value is None for value in exists.values()):
        raise RuntimeError('Cannot verify one or more dependency paths on NAS')
    block, missing = deps.build_render_dependencies_block(
        composition, [{'path': path} for path in paths],
        classifier, lambda path: exists.get(path) is True)
    node = {'version': version, 'source': source, 'method': 'movie XMP aeProjectLink + one-round-trip comp walk',
            'xmp_evidence': {k: evidence[k] for k in (
                'movie', 'composition_id', 'full_path', 'render_queue_item_id')},
            'composition_name': comp_name, 'input_paths': paths}
    if not apply:
        node.update(block=block, missing=missing, status='dry-run')
        return node, None
    write = nas(repair.PUBLISH, {'version': version, 'expected': evidence['metadata'],
                                 'block': block, 'run': 'xmp-' + evidence['render_queue_item_id']})
    node.update(block=block, missing=missing, write=write, status=write['status'])
    return node, write


def update_journal(journal_path, nodes):
    with open(journal_path, encoding='utf-8') as handle:
        report = json.load(handle)
    for key, node in nodes.items():
        report['nodes'][key] = node
        report['errors'] = [e for e in report['errors'] if e['version'].lower() != key]
    deps.write_json_atomic(journal_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--only-version', action='append', default=[],
                        help='Limit to these version directories (repeatable)')
    args = parser.parse_args()
    state = audit.state()
    if state['dirty']:
        raise RuntimeError('AE has unsaved changes; resolve them before running')
    classifier = repair.classify_folder()
    wanted = {v.lower() for v in args.only_version} or set(MOVIES)
    nodes = {}
    for version in sorted(MOVIES):
        if version.lower() not in wanted:
            continue
        print('Repairing:', version, flush=True)
        node, write = repair_target(version, classifier, apply=args.apply)
        nodes[node['version'].lower()] = node
        if write:
            print(json.dumps(write), flush=True)
        else:
            print(json.dumps({'status': node['status'],
                              'render_inputs': len(node['block']['dependencies']),
                              'external_inputs': len(node['block']['externalFiles']),
                              'missing': len(node['missing'])}), flush=True)
    if nodes and args.apply:
        update_journal(JOURNAL, nodes)
        repair.verify_journal(JOURNAL)
    elif nodes:
        deps.write_json_atomic(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'cytonics-xmp-repair-dry-run.json'), nodes)
        print('Dry run written; journal untouched', flush=True)


if __name__ == '__main__':
    main()
