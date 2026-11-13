"""Temporary, explicit Cytonics batch repair. Uses the running Windows AE bridge.

Run with --apply to back up and patch reachable AE render version metadata.
Other DCC metadata is traversed without modification. Journals stay local.
"""
import argparse
import ast
import base64
import collections
import datetime
import gzip
import json
import os
import shlex
import subprocess
import uuid

import audit_render_dependency_samples as audit
import helixae_render_deps as deps


def cli_ae(script):
    """Temporary -r RPC, independent of panel timers lost on project changes."""
    token = 'helix-repair-' + uuid.uuid4().hex
    result_path = 'C:/Users/DimitarHelix/AppData/Local/Temp/' + token + '.json'
    body = audit.protocol.ensure_json_polyfill(
        'var answer=' + script.rstrip(';') + ';\n'
        'var destination=new File(' + audit.protocol.js_string(result_path) + ');\n'
        'destination.encoding="UTF-8";\n'
        'if(!destination.open("w"))throw new Error("Cannot write RPC response");\n'
        'destination.write(answer);destination.close();\n')
    blob = base64.b64encode(gzip.compress(body.encode('utf-8'))).decode('ascii')
    ps = """$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;
$folder='C:\\Users\\DimitarHelix\\AppData\\Local\\Temp';$stage=Join-Path $folder '%s.jsx';
$result=Join-Path $folder '%s.json';
$z=New-Object IO.MemoryStream(,[Convert]::FromBase64String('%s'));
$g=New-Object IO.Compression.GzipStream($z,[IO.Compression.CompressionMode]::Decompress);
$m=New-Object IO.MemoryStream;$g.CopyTo($m);[IO.File]::WriteAllBytes($stage,$m.ToArray());
$exe=(Get-Process AfterFX -ErrorAction Stop | Select-Object -First 1).Path;
$p=Start-Process -FilePath $exe -ArgumentList @('-r',('"'+$stage+'"')) -PassThru;
$deadline=[DateTime]::UtcNow.AddSeconds(45);
while([DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 250;
 if(Test-Path -LiteralPath $result){try{$raw=[IO.File]::ReadAllText($result);$null=$raw|ConvertFrom-Json;
 [Console]::WriteLine($raw);Remove-Item -LiteralPath $result,$stage;exit 0}catch{}}}
throw 'AE command-line request timed out'
""" % (token, token, blob)
    result = subprocess.run(['ssh', 'helix', 'powershell -NoProfile -NonInteractive -Command -'],
                            input=ps.replace('\n', ' ') + '\n', capture_output=True, text=True, timeout=210)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    data, error = audit.protocol.parse_json_response(result.stdout.lstrip('\ufeff'))
    if error or data.get('result') is not True:
        raise RuntimeError(error or data.get('details') or 'AE CLI query failed')
    return data


def mcp_ae(script):
    """Use the enabled MCP panel's file protocol, with per-request identity checks.

    Do not run other AE MCP requests concurrently: this bridge has one mailbox.
    """
    command_id = 'helix-repair-' + uuid.uuid4().hex
    request = {'command': 'executeScript', 'args': {
        'script': audit.protocol.ensure_json_polyfill('return ' + script.rstrip(';') + ';')},
        'commandId': command_id, 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'pending'}
    blob = base64.b64encode(gzip.compress(json.dumps(request).encode('utf-8'))).decode('ascii')
    ps = """$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;
$folder='C:\\Users\\DimitarHelix\\AppData\\Local\\ae-mcp-bridge';
$z=New-Object IO.MemoryStream(,[Convert]::FromBase64String('%s'));
$g=New-Object IO.Compression.GzipStream($z,[IO.Compression.CompressionMode]::Decompress);
$m=New-Object IO.MemoryStream;$g.CopyTo($m);
$stage=Join-Path $folder '%s.tmp';$command=Join-Path $folder 'ae_command.json';
[IO.File]::WriteAllBytes($stage,$m.ToArray());Move-Item -LiteralPath $stage -Destination $command -Force;
$deadline=[DateTime]::UtcNow.AddSeconds(45);
while([DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 250;
 try{$raw=[IO.File]::ReadAllText((Join-Path $folder 'ae_mcp_result.json'));$r=$raw|ConvertFrom-Json;
 if($r._commandId -eq '%s'){[Console]::WriteLine($raw);exit 0}}catch{}}
throw 'MCP request timed out'
""" % (blob, command_id, command_id)
    result = subprocess.run(['ssh', 'helix', 'powershell -NoProfile -NonInteractive -Command -'],
                            input=ps.replace('\n', ' ') + '\n', capture_output=True, text=True,
                            timeout=210)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)
    envelope, error = audit.protocol.parse_json_response(result.stdout.lstrip('\ufeff'))
    if error or envelope.get('_commandId') != command_id or envelope.get('status') != 'success':
        raise RuntimeError('MCP failed: ' + (error or json.dumps(envelope)))
    data, error = audit.protocol.parse_json_response(envelope.get('result'))
    if error or data.get('result') is not True:
        raise RuntimeError(error or data.get('details') or 'AE query failed')
    return data

def classify_folder():
    """Load the real stdlib-only classification method without importing Qt."""
    path = os.path.join(os.path.dirname(__file__), '..', 'Scripts', 'footage_tracker', 'utils.py')
    with open(path, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FootageUtils')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'detectFolderType')
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), path, 'exec'), namespace)
    return namespace['detectFolderType']


def nas(code, payload=None):
    result = subprocess.run(['ssh', 'nassk', 'python3 -c ' + shlex.quote(code)],
                            input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError('NAS operation failed: ' + result.stderr[-3000:])
    return json.loads(result.stdout)


def roots():
    return nas('''import json,os
base='/volume1/Renders/X/Cytonics_CYT108/03_Production/Shots/Edit/MAIN/Renders/2dRender/'
result=[]
for task,vs in [('HighRes',[19,16,15,12,11,5]),('LowRes',[7])]:
 for v in vs:
  d=base+task+'/v%04d'%v
  media=sorted(n for n in os.listdir(d) if n.lower().endswith(('.mov','.mp4','.avi')))
  if not media:raise RuntimeError('No output movie in '+d)
  primary='Edit-MAIN_'+task+'_v%04d'%v
  chosen=next((primary+ext for ext in ('.mov','.mp4','.avi') if primary+ext in media),media[0])
  result.append('X:/Cytonics_CYT108/03_Production/Shots/Edit/MAIN/Renders/2dRender/'+task+'/v%04d/'%v+chosen)
print(json.dumps(result))
''')


PUBLISH = r'''
import os,json,sys,hashlib,tempfile,stat
p=json.load(sys.stdin)
directory=p['version'].replace('\\','/')
prefix='X:/Cytonics_CYT108/'
if not directory.startswith(prefix) or '..' in directory.split('/'):
 raise ValueError('Unexpected target path')
target='/volume1/Renders/X/'+directory[3:]+'/versioninfo.json'
backup=target+'.before-render-deps.'+p['run']+'.bak'
def read(path):
 with open(path,'rb') as h:return h.read()
def digest(raw):return hashlib.sha256(raw).hexdigest()
original=read(target)
old=json.loads(original.decode('utf-8-sig'))
if old!=p['expected']:raise RuntimeError('Metadata changed since dependency scan')
block=p['block']
if not isinstance(block,dict) or any(not isinstance(block.get(k),list) for k in ('dependencies','externalFiles')):
 raise ValueError('Invalid dependency block')
if any(not isinstance(v,str) or not v.strip() for k in ('dependencies','externalFiles') for v in block[k]):
 raise ValueError('Invalid dependency path')
context=block.get('context',{})
if context.get('application')!='aftereffects' or context.get('type') not in ('composition','composition-set') or not context.get('identifier'):
 raise ValueError('Invalid composition context')
if old.get('renderDependencies')==block and not p.get('field_updates'):
 print(json.dumps({'status':'already-current','target':target,'sha256':digest(original)}));sys.exit(0)
updates=p.get('field_updates',{})
if not isinstance(updates,dict) or any(k!='sourceScene' for k in updates):
 raise ValueError('Unsupported metadata field correction')
if updates and (old.get('sourceScene') or not isinstance(updates['sourceScene'],str)
                or not updates['sourceScene'].startswith('X:/Cytonics_CYT108/')
                or not updates['sourceScene'].lower().endswith('.aep')):
 raise ValueError('Only an empty sourceScene can be filled with a confirmed project AEP path')
new=dict(old);new.update(updates);new['renderDependencies']=block
# Back up exact original bytes BEFORE writing the replacement stage.
with open(backup,'xb') as h:
 h.write(original);h.flush();os.fsync(h.fileno())
if read(backup)!=original:raise RuntimeError('Backup byte verification failed: '+backup)
stage=None
try:
 fd,stage=tempfile.mkstemp(prefix='.versioninfo.repair.',suffix='.tmp',dir=os.path.dirname(target))
 with os.fdopen(fd,'w',encoding='utf-8') as h:
  json.dump(new,h,indent=2,ensure_ascii=True,allow_nan=False);h.write('\n');h.flush();os.fsync(h.fileno())
 staged=read(stage);verified=json.loads(staged.decode('utf-8'))
 if verified!=new:raise RuntimeError('Staged JSON verification failed')
 rest=dict(verified);rest.pop('renderDependencies',None)
 old_rest=dict(old);old_rest.update(updates);old_rest.pop('renderDependencies',None)
 if rest!=old_rest:raise RuntimeError('Unrelated fields changed')
 os.chmod(stage,stat.S_IMODE(os.stat(target).st_mode))
 if read(target)!=original:raise RuntimeError('Original changed after backup')
 os.replace(stage,target);stage=None
 if read(target)!=staged or read(backup)!=original:raise RuntimeError('Final byte verification failed')
 print(json.dumps({'status':'updated','target':target,'backup':backup,'original_sha256':digest(original),
                   'backup_sha256':digest(read(backup)),'new_sha256':digest(staged)}))
finally:
 if stage and os.path.exists(stage):os.unlink(stage)
'''


def save(report, path):
    deps.write_json_atomic(path, report)


def verify_journal(path):
    """Re-read production files and retained backups independently of the writer."""
    with open(path, encoding='utf-8') as handle:
        report = json.load(handle)
    writes = [dict(node['write'], block=node['block'], field_updates=node.get('field_updates', {})) for node in report['nodes'].values()
              if node.get('write', {}).get('status') == 'updated']
    creations = [dict(record, kind='reconstruction') for record in report.get('reconstructions', [])]
    result = nas(r'''import json,sys,hashlib
records=json.load(sys.stdin);verified=[];created=[]
for r in records:
 with open(r['target'],'rb') as h:new_bytes=h.read()
 if r.get('kind')=='reconstruction':
  if hashlib.sha256(new_bytes).hexdigest()!=r['new_sha256'] or json.loads(new_bytes.decode('utf-8'))!=r['metadata']:
   raise RuntimeError('Reconstructed metadata mismatch: '+r['target'])
  created.append(r['target']);continue
 with open(r['backup'],'rb') as h:old_bytes=h.read()
 if hashlib.sha256(old_bytes).hexdigest()!=r['original_sha256'] or r['original_sha256']!=r['backup_sha256']:
  raise RuntimeError('Backup hash mismatch: '+r['target'])
 if hashlib.sha256(new_bytes).hexdigest()!=r['new_sha256']:
  raise RuntimeError('Installed hash mismatch: '+r['target'])
 old=json.loads(old_bytes.decode('utf-8-sig'));new=json.loads(new_bytes.decode('utf-8-sig'))
 if new.pop('renderDependencies')!=r['block']:raise RuntimeError('Block mismatch: '+r['target'])
 old.update(r.get('field_updates',{}));old.pop('renderDependencies',None)
 if new!=old:raise RuntimeError('Unrelated fields changed: '+r['target'])
 verified.append(r['target'])
print(json.dumps({'verified_count':len(verified),'verified_targets':verified,
                  'reconstructed_count':len(created),'reconstructed_targets':created}))
''', writes + creations)
    report['verification'] = result
    save(report, path)
    lines = ['# Cytonics full-chain render metadata repair', '',
             'Run: `' + report['run'] + '`', '',
             'Independent verification: **%d updated JSONs and original backups passed**.' % result['verified_count'], '',
             'renderDependencies was regenerated; any explicitly authorized sourceScene corrections are listed below.',
             'All other fields were compared against the backups.', '',
             '## Updated versions and verified backups', '']
    for node in report['nodes'].values():
        if node.get('write', {}).get('status') != 'updated':
            continue
        lines += ['### ' + node['version'], '', '- Source: `' + node['source'] + '`',
                  '- Backup: `' + node['write']['backup'] + '`',
                  '- Original/backup SHA-256: `' + node['write']['original_sha256'] + '`',
                  '- New SHA-256: `' + node['write']['new_sha256'] + '`',
                  '- Context: `' + node['block']['context']['name'] + '`',
                  '- Render inputs: %d; external inputs: %d; missing inputs excluded: %d.' % (
                      len(node['block']['dependencies']), len(node['block']['externalFiles']), len(node['missing'])), '']
        lines.extend('  - Missing/excluded: `' + p + '`' for p in node['missing'])
        if node.get('field_updates'):
            lines.append('- Authorized field correction: `' + json.dumps(node['field_updates']) + '`')
    lines += ['', '## Reconstructed missing publish metadata', '']
    for record in report.get('reconstructions', []):
        lines += ['### ' + record['version'], '',
                  '- Source: `' + record['source'] + '`',
                  '- New JSON SHA-256: `' + record['new_sha256'] + '`',
                  '- Original backup: none; no original JSON existed.',
                  '- Scope: ' + record['dependency_scope'],
                  '- Exporter attribution: ' + record['exporter_identity'],
                  '- Source scene SHA-256: `' + record['source_scene_sha256'] + '`',
                  '- Reconstructed: ' + record['reconstructed_utc'], '']
        if 'abc_size' in record:
            lines.append('- Alembic size: %d bytes; last 2 MiB SHA-256: `%s`.' % (record['abc_size'], record['abc_tail_sha256']))
        if 'movie_size' in record:
            lines += ['- Movie size: %d bytes; moov metadata SHA-256: `%s`.' % (record['movie_size'], record['movie_moov_sha256']),
                      '- Embedded AE project link: `' + json.dumps(record['movie_project_link']) + '`']
        if 'renderDependencies' in record['metadata']:
            block = record['metadata']['renderDependencies']
            lines += ['- Composition: `' + block['context']['name'] + '` (ID ' + block['context']['identifier'] + ')',
                      '- Scoped render inputs: %d; scoped external inputs: %d.' % (len(block['dependencies']), len(block['externalFiles']))]
        lines.extend('- Dependency: `' + p + '`' for p in record['metadata']['dependencies'])
    lines += ['', '## Unresolved versions — originals not replaced', '']
    for node in report['nodes'].values():
        if node['status'] == 'unresolved':
            lines.append('- `' + node['version'] + '` — ' + node['error'])
    if report.get('restore_error'):
        lines += ['', 'AE project restoration was blocked: ' + report['restore_error']]
    lines += ['', 'The run can be resumed using --apply --resume with the JSON journal.',
              'Existing successful updates are retained and traversed without rewriting their backups.',
              'Maya/Houdini metadata is followed recursively; explicitly reconstructed records are listed above.', '']
    output = os.path.splitext(path)[0] + '.md'
    with open(output, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines))
    print('VERIFIED', result['verified_count'], 'RECONSTRUCTED', result['reconstructed_count'], 'REPORT', output, flush=True)


def queue_matches(snapshot, node, movies):
    matches = {}
    for item in snapshot['queue']:
        if not item['done']:
            continue
        for output in item['outputs']:
            if not output:
                continue
            output = audit.norm(output).lower()
            if output.rsplit('/', 1)[0] != node['version'].lower():
                continue
            if movies and output not in movies:
                continue
            matches.setdefault(item['compId'], []).append(item)
    return matches


def scan_confirmed_comp(node, name):
    """Read the artist-confirmed comp as currently loaded, without save/open."""
    current = audit.state()
    if not current.get('path') or audit.norm(current['path']).lower() != node['source'].lower():
        raise RuntimeError('Open the sourceScene recorded in the target JSON before using --confirmed-comp')
    listing = audit.ae(audit.protocol.build_list_project_comps())
    comps = listing.get('comps')
    if not isinstance(comps, list):
        raise RuntimeError('Malformed composition listing')
    matches = [c for c in comps if isinstance(c, dict) and c.get('name') == name]
    if len(matches) != 1 or matches[0].get('id') is None:
        raise RuntimeError('Confirmed composition name must identify exactly one comp')
    comp_id = str(matches[0]['id'])
    script = audit.protocol.build_comp_dependency_script(comp_id).rstrip(';')
    result = audit.ae(audit.protocol._wrap(
        'var scan=JSON.parse(' + script + ');\n'
        'return JSON.stringify({result:true,path:app.project.file.fsName,scan:scan});\n'))
    if audit.norm(result['path']).lower() != node['source'].lower():
        raise RuntimeError('Project changed during confirmed-comp scan')
    parsed, error = audit.protocol.parse_comp_dependency_result(json.dumps(result['scan']))
    if error:
        raise RuntimeError(error)
    if parsed['composition'] != {'id': comp_id, 'name': name}:
        raise RuntimeError('Confirmed composition identity changed')
    node['compositions'] = [parsed['composition']]
    node['composition'] = parsed['composition']
    node['mapping_method'] = 'user-confirmed current composition; historical scene may have been overwritten'
    node['scanned_dirty_project'] = current['dirty']
    return sorted({record['path'] for record in parsed['footage']})


def scan_all_outputs(node):
    """A version JSON serves every output in that version, including variants."""
    source = node['source']
    audit.open_scene(source)
    snapshot = audit.ae(audit.QUEUE_SCRIPT)
    if audit.norm(snapshot['path']).lower() != source.lower():
        raise RuntimeError('Project changed during queue inspection')
    available = nas('''import json,os,sys
v=json.load(sys.stdin)
d='/volume1/Renders/X/'+v[3:]
print(json.dumps([v+'/'+n for n in os.listdir(d) if os.path.isfile(d+'/'+n)]))
''', node['version'])
    existing = {audit.norm(p).lower() for p in available}
    movies = {p for p in existing if p.endswith(('.mov', '.mp4', '.avi'))}
    matches = queue_matches(snapshot, node, movies)
    node['queue_evidence_scene'] = source
    if not matches:
        # Export saves the original scene BEFORE queueing. Later saves may carry
        # the completed queue item; use them for identity evidence only, then
        # return to the exact original source to collect dependencies.
        candidates = nas(r'''import json,os,re,sys
s=json.load(sys.stdin);directory,name=s.rsplit('/',1)
m=re.match(r'^(.*_v)(\d{4})\.aep$',name,re.I)
result=[]
if m:
 for n in sorted(os.listdir('/volume1/Renders/X/'+directory[3:])):
  hit=re.match(re.escape(m.group(1))+r'(\d{4})\.aep$',n,re.I)
  if hit and int(hit.group(1))>int(m.group(2)):result.append(directory+'/'+n)
print(json.dumps(result[:5]))
''', source)
        for candidate in candidates:
            audit.open_scene(candidate)
            later = audit.ae(audit.QUEUE_SCRIPT)
            if audit.norm(later['path']).lower() != candidate.lower():
                raise RuntimeError('Project changed during later-queue inspection')
            matches = queue_matches(later, node, movies)
            if matches:
                node['queue_evidence_scene'] = candidate
                break
        audit.open_scene(source)
    if not matches:
        raise RuntimeError('No completed render queue mapping for existing outputs')
    # One output filename mapping to conflicting comp identities is ambiguous.
    by_output = collections.defaultdict(set)
    for comp_id, items in matches.items():
        for item in items:
            for output in item['outputs']:
                if output and audit.norm(output).rsplit('/', 1)[0].lower() == node['version'].lower():
                    by_output[audit.norm(output).lower()].add(comp_id)
    if any(len(ids) > 1 for ids in by_output.values()):
        raise RuntimeError('The same output has completed queue mappings to different comps')
    compositions, paths = [], set()
    node['queue_matches'] = []
    for comp_id, items in sorted(matches.items()):
        script = audit.protocol.build_comp_dependency_script(comp_id).rstrip(';')
        result = audit.ae(audit.protocol._wrap(
            'var scan=JSON.parse(' + script + ');\n'
            'return JSON.stringify({result:true,path:app.project.file.fsName,scan:scan});\n'))
        if audit.norm(result['path']).lower() != source.lower():
            raise RuntimeError('Project changed during dependency scan')
        parsed, error = audit.protocol.parse_comp_dependency_result(json.dumps(result['scan']))
        if error:
            raise RuntimeError(error)
        if parsed['composition']['id'] != comp_id:
            raise RuntimeError('Composition identity mismatch')
        compositions.append(parsed['composition'])
        paths.update(record['path'] for record in parsed['footage'])
        node['queue_matches'].extend(items)
    node['compositions'] = compositions
    node['composition'] = compositions[0]
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resume', help='Resume an interrupted local run journal')
    parser.add_argument('--verify-only', help='Verify installed JSON/backup hashes from a run journal')
    parser.add_argument('--mcp', action='store_true', help='Use the enabled MCP bridge instead of CEP TCP')
    parser.add_argument('--cli', action='store_true', help='Use AE -r scripts without a panel timer')
    parser.add_argument('--skip-source', action='append', default=[], help='Defer a source known to freeze AE')
    parser.add_argument('--retry-mappings', action='store_true', help='Retry missing queue mappings using later saved queue evidence')
    parser.add_argument('--only-version', action='append', default=[], help='Limit AE writes to these version directories')
    parser.add_argument('--max-ae', type=int, default=0, help='Limit AE version attempts in one batch (0 = unlimited)')
    parser.add_argument('--confirmed-comp', help='Artist-confirmed comp in the currently open source; requires one --only-version')
    parser.add_argument('--confirmed-source', help='Explicitly authorized source path to fill an empty sourceScene; requires one --only-version')
    args = parser.parse_args()
    if args.confirmed_comp and len(args.only_version) != 1:
        parser.error('--confirmed-comp requires exactly one --only-version')
    if args.confirmed_source and len(args.only_version) != 1:
        parser.error('--confirmed-source requires exactly one --only-version')
    if args.verify_only:
        verify_journal(os.path.abspath(args.verify_only))
        return
    if args.mcp:
        audit.ae = mcp_ae
    if args.cli:
        audit.ae = cli_ae
    if args.resume:
        journal = os.path.abspath(args.resume)
        with open(journal, encoding='utf-8') as handle:
            report = json.load(handle)
        run, selected = report['run'], report['roots']
        if report['apply'] != args.apply:
            raise RuntimeError('Resume must retain the original --apply setting')
        report['errors'] = []
        report.pop('restore_error', None)
        report.pop('interrupted', None)
    else:
        run = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        journal = os.path.join(os.path.dirname(__file__), 'cytonics-full-repair-' + run + '.json')
        selected = roots()
        report = {'run': run, 'apply': args.apply, 'roots': selected, 'nodes': {}, 'errors': [], 'files': {}}
    original = audit.state()
    if original['dirty'] and not args.confirmed_comp:
        raise RuntimeError('AE has unsaved changes; resolve them before running')
    original_open = audit.open_scene
    def preserving_open(path):
        current = audit.state()
        if current['dirty']:
            recovery = ('C:/Users/DimitarHelix/AppData/Local/Temp/helix-render-repair-recovery-'
                        + uuid.uuid4().hex + '.aep')
            ack = audit.ae(audit.protocol.build_save_scene(recovery))
            if audit.norm(ack.get('path', '')).lower() != recovery.lower():
                raise RuntimeError('Temporary recovery copy was not confirmed')
            report.setdefault('recovery_scenes', []).append({'source': current['path'], 'recovery': recovery})
            save(report, journal)
        return original_open(path, restart_mcp=args.mcp)
    audit.open_scene = preserving_open
    classifier = classify_folder()
    pending = collections.deque(selected)
    seen_paths = set()
    visited_versions = set()
    ae_attempts = 0
    save(report, journal)
    print('JOURNAL', journal, flush=True)
    try:
        while pending:
            paths = sorted(set(pending) - seen_paths)
            pending.clear()
            if not paths:
                break
            seen_paths.update(paths)
            records = audit.inspect(paths)
            groups = collections.defaultdict(list)
            for record in records:
                report['files'][record['path']] = {k: v for k, v in record.items() if k != 'metadata'}
                if record.get('version'):
                    groups[record['version'].lower()].append(record)
            for key, items in sorted(groups.items()):
                if key in visited_versions:
                    continue
                visited_versions.add(key)
                previous = report['nodes'].get(key)
                if (previous and '/04_resources/' in key
                        and previous.get('error') == 'missing versioninfo.json'):
                    previous['status'] = 'loose resource'
                    previous.pop('error', None)
                if previous and previous['status'] in ('updated', 'already-current', 'non-AE metadata traversed', 'loose resource', 'reconstructed'):
                    pending.extend(audit.norm(p) for p in previous['dependencies'])
                    continue
                if previous and previous.get('error', '').startswith((
                        'No completed render queue mapping', 'missing sourceScene', 'missing versioninfo.json')):
                    confirmed_target = ((args.confirmed_comp or args.confirmed_source)
                                        and key == audit.norm(args.only_version[0]).lower())
                    if not confirmed_target and not (args.retry_mappings and previous['error'].startswith('No completed render queue mapping')):
                        report['errors'].append({'version': previous['version'], 'error': previous['error']})
                        continue
                first = items[0]
                metadata = first.get('metadata') or {}
                source = audit.norm(metadata.get('sourceScene') or '')
                field_updates = {}
                if (args.confirmed_source and key == audit.norm(args.only_version[0]).lower()):
                    proposed = audit.norm(args.confirmed_source)
                    if source and source.lower() != proposed.lower():
                        raise RuntimeError('Confirmed source conflicts with non-empty sourceScene')
                    if not source:
                        source = proposed
                        field_updates = {'sourceScene': source}
                if source.lower().endswith('.aep'):
                    if args.only_version and key not in {audit.norm(v).lower() for v in args.only_version}:
                        continue
                    if args.max_ae and ae_attempts >= args.max_ae:
                        continue
                    ae_attempts += 1
                node = {'version': first['version'], 'source': source,
                        'input_paths': [r['path'] for r in items], 'dependencies': []}
                if field_updates:
                    node['field_updates'] = field_updates
                report['nodes'][key] = node
                try:
                    if not first.get('metadata_exists') and '/04_resources/' in node['version'].lower():
                        node['status'] = 'loose resource'
                        save(report, journal)
                        continue
                    if not first.get('metadata_exists') or first.get('metadata_error'):
                        raise RuntimeError(first.get('metadata_error') or 'missing versioninfo.json')
                    if source.lower().endswith('.aep'):
                        if source.lower() in {audit.norm(p).lower() for p in args.skip_source}:
                            raise RuntimeError('Deferred source: previously froze AE')
                        paths = (scan_confirmed_comp(node, args.confirmed_comp)
                                 if args.confirmed_comp else scan_all_outputs(node))
                        existence = audit.inspect(paths) if paths else []
                        # Match the producer: exclude missing file-backed sources.
                        exists = {r['path']: r.get('exists') for r in existence}
                        if any(value is None for value in exists.values()):
                            raise RuntimeError('Cannot verify one or more dependency paths on NAS')
                        block, missing = deps.build_render_dependencies_block(
                            node['composition'], [{'path': path} for path in paths],
                            classifier, lambda path: exists.get(path) is True)
                        if len(node['compositions']) > 1:
                            block['context'] = {
                                'application': 'aftereffects', 'type': 'composition-set',
                                'identifier': ','.join(c['id'] for c in node['compositions']),
                                'name': ' + '.join(c['name'] for c in node['compositions']),
                                'compositions': node['compositions'],
                            }
                        node.update(block=block, missing=missing,
                                    dependencies=block['dependencies'] + block['externalFiles'])
                        # Store the intended patch before the remote write for recovery.
                        node['status'] = 'prepared'
                        save(report, journal)
                        if args.apply:
                            node['write'] = nas(PUBLISH, {'version': node['version'], 'expected': metadata,
                                                          'block': block, 'run': run,
                                                          'field_updates': node.get('field_updates', {})})
                            node['status'] = node['write']['status']
                        else:
                            node['status'] = 'dry-run'
                    elif not source:
                        raise RuntimeError('missing sourceScene; no composition mapping')
                    else:
                        block = metadata.get('renderDependencies')
                        if (isinstance(block, dict) and all(isinstance(block.get(k), list) for k in ('dependencies', 'externalFiles'))
                                and all(isinstance(p, str) and p.strip() for k in ('dependencies', 'externalFiles') for p in block[k])):
                            node['dependencies'] = block['dependencies'] + block['externalFiles']
                        else:
                            node['dependencies'] = [p for k in ('dependencies', 'externalFiles')
                                                    for p in metadata.get(k, []) if isinstance(p, str) and p.strip()]
                        node['status'] = 'non-AE metadata traversed'
                    pending.extend(audit.norm(p) for p in node['dependencies'])
                except Exception as error:
                    node['status'] = 'unresolved'
                    node['error'] = str(error)
                    report['errors'].append({'version': node['version'], 'error': str(error)})
                    if isinstance(error, (subprocess.CalledProcessError, subprocess.TimeoutExpired)):
                        report['interrupted'] = str(error)
                        save(report, journal)
                        raise RuntimeError('AE transport failed; resume this journal once the bridge is available') from error
                save(report, journal)
                if node['status'] != 'non-AE metadata traversed':
                    print(node['version'], node['status'], 'inputs', len(node['dependencies']), flush=True)
    finally:
        try:
            if original.get('path') and not args.confirmed_comp:
                audit.open_scene(original['path'])
        except Exception as error:
            report['restore_error'] = str(error)
        save(report, journal)
    print('SUMMARY', json.dumps(dict(collections.Counter(n['status'] for n in report['nodes'].values()))), flush=True)
    print('JOURNAL', journal, flush=True)


if __name__ == '__main__':
    main()
