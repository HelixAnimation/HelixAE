"""Temporary create-only reconstruction of the confirmed Maya Animation publish.

Reads the scene and Alembic metadata; never opens a DCC or modifies either file.
The local reconstruction record is retained separately from the publish JSON.
"""
import argparse
import json
import os

import repair_selected_render_dependencies as repair

VERSION = 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH021/Export/Animation/v0001'
SOURCE = ('X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH021/Scenefiles/Animation/'
          'Animation/SQ020-SH021_Animation_v0005.ma')
SCENE_HASH = '91627fca3ae8942ec431925ade00eaf1022d048675e1e4caf0be4132745bd015'
TAIL_HASH = '63ebf652b634a9f1cce9aafd0563b59c468687ffcc21689ebb70a57bbc7fda10'

TRANSACTION = r'''
import os,json,re,sys,hashlib,tempfile,datetime
p=json.load(sys.stdin)
def local(path):
 if not path.startswith('X:/Cytonics_CYT108/') or '..' in path.split('/'):
  raise ValueError('Unsupported project path: '+path)
 return '/volume1/Renders/X/'+path[3:]
def read(path):
 with open(path,'rb') as f:return f.read()
def digest(data):return hashlib.sha256(data).hexdigest()
version=p['version'];source=p['source'];target=local(version)+'/versioninfo.json'
if os.path.lexists(target):raise RuntimeError('Refusing to overwrite existing metadata: '+target)
scene=local(source);abc=local(version)+'/SQ020-SH021_Animation_v0001.abc'
original=read(scene)
if digest(original)!=p['scene_sha256']:raise RuntimeError('Source scene changed since inspection')
scene_stat=os.stat(scene);abc_stat=os.stat(abc)
with open(abc,'rb') as f:
 f.seek(-min(2*1024*1024,abc_stat.st_size),2);tail=f.read()
if digest(tail)!=p['tail_sha256']:raise RuntimeError('Alembic provenance changed since inspection')
provenance=[s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{8,}',tail)
            if ('Exported from: '+source).encode('ascii') in s]
if len(provenance)!=1 or 'Maya 2022 AbcExport' not in provenance[0]:
 raise RuntimeError('Alembic does not uniquely confirm the expected source')
text=original.decode('cp1252')
m=re.search(r'fileInfo\s+"PrismStates"\s+("(?:\\.|[^"\\])*")\s*;',text)
if not m:raise RuntimeError('Missing saved Prism export/import states')
states=json.loads(json.loads(m.group(1)))['states']
exports=[s for s in states if s.get('stateclass')=='Export' and s.get('productname')=='Animation'
         and s.get('lastexportpath','').replace('\\','/')==version+'/SQ020-SH021_Animation_v0001.abc']
if len(exports)!=1:raise RuntimeError('Saved export state does not confirm this output')
imports=sorted({s['filepath'].replace('\\','/') for s in states
                if s.get('stateclass')=='ImportFile' and isinstance(s.get('filepath'),str) and s['filepath']})
references=set()
for match in re.finditer(r'^file\s+[^;]*;',text,re.M):
 command=match.group(0)
 if re.search(r'\s-r(?:\s|$)|\s-rdi\s',command):
  tokens=re.findall(r'"(?:\\.|[^"\\])*"',command)
  if not tokens:raise RuntimeError('Unparseable Maya reference command')
  references.add(json.loads(tokens[-1]).replace('\\','/'))
if set(imports)!=references:raise RuntimeError('Maya references disagree with saved Prism imports')
absolute=set()
for token in re.findall(r'"(?:\\.|[^"\\])*"',text):
 try:value=json.loads(token).replace('\\','/')
 except ValueError:continue
 if re.match(r'^[A-Za-z]:/',value) and '\n' not in value and len(value)<2048:absolute.add(value)
if absolute!=references:raise RuntimeError('Additional absolute file paths require review')
if not imports:raise RuntimeError('Unexpected empty source dependency list')
inputs=[]
for path in imports:
 f=local(path)
 if not os.path.isfile(f):raise RuntimeError('Missing source dependency: '+path)
 info=os.stat(f);inputs.append({'path':path,'size':info.st_size,'mtime_ns':info.st_mtime_ns})
scene_metadata=json.loads(read(os.path.splitext(scene)[0]+'versioninfo.json').decode('utf-8-sig'))
keys=('project_path','sequence','shot','department','task','type','hierarchy','itemType','project_name')
data={k:scene_metadata[k] for k in keys if k in scene_metadata}
data.update(version='v0001',product='Animation',sourceScene=source,locations={'global':'.'},
            dependencies=imports,externalFiles=[])
# Film = 24 fps. Refuse unsupported scene units rather than borrow a later export's fps.
if not re.search(r'^currentUnit\s+[^;]*-t\s+film\s*;',text,re.M):
 raise RuntimeError('Unexpected Maya time unit; fps needs review')
data['fps']=24.0
# Do not assign scene-author identity to the unknown exporter, or add an AE render block.
raw=(json.dumps(data,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8')
if json.loads(raw.decode('utf-8'))!=data:raise RuntimeError('Candidate JSON validation failed')
record={'status':'prepared','target':target,'version':version,'source':source,'metadata':data,
        'new_sha256':digest(raw),'source_scene_sha256':digest(original),'abc_tail_sha256':digest(tail),
        'abc_size':abc_stat.st_size,'abc_mtime_ns':abc_stat.st_mtime_ns,
        'scene_size':scene_stat.st_size,'scene_mtime_ns':scene_stat.st_mtime_ns,
        'abc_provenance':provenance[0],'inputs':inputs,
        'dependency_scope':'conservative scene-wide saved references and Prism imports',
        'exporter_identity':'unknown; source-scene artist is not asserted as exporter',
        'reconstructed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'backup':None,'backup_reason':'No original versioninfo.json existed'}
if p.get('apply'):
 stage=None
 try:
  fd,stage=tempfile.mkstemp(prefix='.versioninfo.reconstruction.',suffix='.tmp',dir=os.path.dirname(target))
  with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  if read(stage)!=raw:raise RuntimeError('Stage byte verification failed')
  os.chmod(stage,0o664)
  if digest(read(scene))!=p['scene_sha256']:raise RuntimeError('Source changed during reconstruction')
  now=os.stat(abc)
  if (now.st_size,now.st_mtime_ns)!=(abc_stat.st_size,abc_stat.st_mtime_ns):
   raise RuntimeError('Alembic changed during reconstruction')
  # Atomic no-clobber publication. If another writer creates target, link fails.
  os.link(stage,target)
  if read(target)!=raw:raise RuntimeError('Installed JSON byte verification failed')
  record['status']='reconstructed'
 finally:
  if stage and os.path.exists(stage):os.unlink(stage)
print(json.dumps(record))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    payload = {'version': VERSION, 'source': SOURCE, 'scene_sha256': SCENE_HASH,
               'tail_sha256': TAIL_HASH, 'apply': args.apply}
    folder = os.path.dirname(__file__)
    path = os.path.join(folder, 'cytonics-animation-v0001-reconstruction.json')
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as handle:
            previous = json.load(handle)
        if previous.get('status') == 'reconstructed':
            raise RuntimeError('A completed reconstruction record already exists; verify it instead of overwriting it')
    # Persist the intended operation locally before any NAS metadata write.
    repair.deps.write_json_atomic(path, {'request': payload, 'status': 'requested'})
    record = repair.nas(TRANSACTION, payload)
    repair.deps.write_json_atomic(path, record)
    if args.apply:
        journal_path = os.path.join(folder, 'cytonics-full-repair-20261019T182222Z.json')
        with open(journal_path, encoding='utf-8') as handle:
            journal = json.load(handle)
        journal.setdefault('reconstructions', []).append(record)
        node = journal['nodes'][VERSION.lower()]
        node.update(status='reconstructed', source=SOURCE,
                    dependencies=record['metadata']['dependencies'],
                    method='reconstructed Maya scene-wide publish metadata',
                    reconstruction_record=os.path.basename(path))
        node.pop('error', None)
        journal['errors'] = [e for e in journal['errors'] if e['version'].lower() != VERSION.lower()]
        repair.deps.write_json_atomic(journal_path, journal)
    print(json.dumps({'status': record['status'], 'target': record['target'],
                      'dependencies': len(record['metadata']['dependencies']),
                      'sha256': record['new_sha256'], 'record': path}, indent=2))


if __name__ == '__main__':
    main()
