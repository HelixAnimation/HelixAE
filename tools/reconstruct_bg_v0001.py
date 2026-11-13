"""Create-only BG v0001 reconstruction from movie XMP and live AE comp 17.

Does not open, save, or switch AE projects. Local records retain the evidence.
"""
import argparse
import json
import os

import repair_selected_render_dependencies as repair

VERSION = 'X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Renders/2dRender/BG/v0001'
SOURCE = ('X:/Cytonics_CYT108/03_Production/Shots/SQ020/SH020/Scenefiles/LookDev/'
          'LowRes/SQ020-SH020_LowRes_v0007.aep')
MOVIE = VERSION + '/SQ020-SH020_BG_v0001.mov'
COMPOSITION_ID = '17'
COMPOSITION_NAME = 'SQ020-SH020_BG_v0001'
RECORD_FILE = 'cytonics-bg-v0001-reconstruction.json'

PREFLIGHT = r'''
import os,json,sys,struct,re,hashlib,xml.etree.ElementTree as ET
p=json.load(sys.stdin)
def local(path):
 if not path.startswith('X:/Cytonics_CYT108/') or '..' in path.split('/'):
  raise ValueError('Unsupported project path')
 return '/volume1/Renders/X/'+path[3:]
def read(path):
 with open(path,'rb') as f:return f.read()
target=local(p['version'])+'/versioninfo.json'
if os.path.lexists(target):raise RuntimeError('Target metadata already exists; refusing to overwrite')
movie=local(p['movie']);info=os.stat(movie);pos=0;moov=None
with open(movie,'rb') as f:
 while pos+8<=info.st_size:
  f.seek(pos);size,kind=struct.unpack('>I4s',f.read(8));header=8
  if size==1:size=struct.unpack('>Q',f.read(8))[0];header=16
  elif size==0:size=info.st_size-pos
  if size<header or pos+size>info.st_size:raise RuntimeError('Invalid movie atom')
  if kind==b'moov':
   if size>32*1024*1024:raise RuntimeError('Unexpectedly large movie metadata')
   moov=f.read(size-header);break
  pos+=size
if moov is None:raise RuntimeError('Movie has no moov metadata')
m=re.search(rb'<x:xmpmeta[\s\S]*?</x:xmpmeta>',moov)
if not m:raise RuntimeError('Movie has no embedded AE project link')
xml=ET.fromstring(m.group(0))
ns='http://ns.adobe.com/creatorAtom/1.0/'
links=list(xml.iter('{'+ns+'}aeProjectLink'))
if len(links)!=1:raise RuntimeError('Ambiguous movie project link')
link={key.split('}',1)[-1]:value for key,value in links[0].attrib.items()}
if (link.get('fullPath','').replace('\\','/').lower()!=p['source'].lower()
    or link.get('compositionID')!=p.get('composition_id','17')):
 raise RuntimeError('Movie source/comp differs from the intended reconstruction')
source=local(p['source']);raw=read(source)
stem=os.path.splitext(source)[0]
scene_metadata=json.loads(read(stem+'versioninfo.json').decode('utf-8-sig'))
archive=json.loads(read(stem+'_archiveinfo.json').decode('utf-8-sig'))
source_paths=archive.get('source_paths',{})
if not isinstance(source_paths,dict):raise RuntimeError('Malformed archive source_paths')
def paths(values):
 if not isinstance(values,list) or any(not isinstance(v,str) or not v.strip() for v in values):
  raise RuntimeError('Malformed scene dependency array')
 return sorted({v.replace('\\','/') for v in values})
scene_dependencies=paths(source_paths.get('3d_renders',[])+source_paths.get('2d_renders',[]))
scene_external=paths(source_paths.get('resources',[])+archive.get('external_paths',[]))
fps=[]
for element in xml.iter():
 value=element.attrib.get('{http://ns.adobe.com/xmp/1.0/DynamicMedia/}videoFrameRate')
 if value:fps.append(float(value))
if len(fps)!=1 or fps[0]<=0:raise RuntimeError('Movie frame rate is ambiguous')
print(json.dumps({'target':target,'source_scene_sha256':hashlib.sha256(raw).hexdigest(),
 'scene_size':len(raw),'scene_mtime_ns':os.stat(source).st_mtime_ns,
 'movie_size':info.st_size,'movie_mtime_ns':info.st_mtime_ns,
 'movie_moov_sha256':hashlib.sha256(moov).hexdigest(),'movie_project_link':link,
 'scene_metadata':scene_metadata,'scene_dependencies':scene_dependencies,
 'scene_external':scene_external,'fps':fps[0]}))
'''

CREATE = r'''
import os,json,sys,hashlib,tempfile,datetime
p=json.load(sys.stdin)
def local(path):
 if not path.startswith('X:/Cytonics_CYT108/') or '..' in path.split('/'):
  raise ValueError('Unsupported project path')
 return '/volume1/Renders/X/'+path[3:]
def read(path):
 with open(path,'rb') as f:return f.read()
target=local(p['version'])+'/versioninfo.json'
if os.path.lexists(target):raise RuntimeError('Refusing to overwrite existing metadata')
data=p['metadata'];evidence=p['evidence'];source=local(data['sourceScene'])
if hashlib.sha256(read(source)).hexdigest()!=evidence['source_scene_sha256']:
 raise RuntimeError('Source scene changed after preflight')
movie=os.stat(local(p['movie']))
if (movie.st_size,movie.st_mtime_ns)!=(evidence['movie_size'],evidence['movie_mtime_ns']):
 raise RuntimeError('Movie changed after preflight')
block=data['renderDependencies']
expected=p.get('expected_context',{'application':'aftereffects','type':'composition','identifier':'17','name':'SQ020-SH020_BG_v0001'})
if block['context']!=expected:
 raise RuntimeError('Unexpected composition identity')
for key in ('dependencies','externalFiles'):
 values=block[key]
 if not isinstance(values,list) or any(not isinstance(v,str) or not v for v in values):
  raise RuntimeError('Invalid composition dependency array')
 for path in values:
  if not os.path.isfile(local(path)):raise RuntimeError('Dependency no longer exists: '+path)
if any(k in data for k in ('user','username')):raise RuntimeError('Unknown render user must not be inferred')
raw=(json.dumps(data,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode('utf-8')
stage=None
try:
 fd,stage=tempfile.mkstemp(prefix='.versioninfo.reconstruction.',suffix='.tmp',dir=os.path.dirname(target))
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 if json.loads(read(stage).decode('utf-8'))!=data:raise RuntimeError('Staged JSON validation failed')
 os.chmod(stage,0o664)
 os.link(stage,target)
 if read(target)!=raw:raise RuntimeError('Installed JSON verification failed')
 print(json.dumps({'target':target,'new_sha256':hashlib.sha256(raw).hexdigest(),
                   'status':'reconstructed','reconstructed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
finally:
 if stage and os.path.exists(stage):os.unlink(stage)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    repair.audit.ae = repair.mcp_ae
    evidence = repair.nas(PREFLIGHT, {'version': VERSION, 'source': SOURCE, 'movie': MOVIE,
                                      'composition_id': COMPOSITION_ID})
    node = {'source': SOURCE}
    paths = repair.scan_confirmed_comp(node, COMPOSITION_NAME)
    if node['composition']['id'] != COMPOSITION_ID:
        raise RuntimeError('Live comp ID disagrees with movie project link')
    records = repair.audit.inspect(paths) if paths else []
    existence = {r['path']: r.get('exists') for r in records}
    if any(v is None for v in existence.values()):
        raise RuntimeError('One or more input files could not be verified')
    block, missing = repair.deps.build_render_dependencies_block(
        node['composition'], [{'path': path} for path in paths],
        repair.classify_folder(), lambda path: existence.get(path) is True)
    scene_metadata = evidence['scene_metadata']
    keys = ('project_path', 'sequence', 'shot', 'department', 'task', 'type', 'hierarchy', 'itemType', 'project_name')
    metadata = {k: scene_metadata[k] for k in keys if k in scene_metadata}
    metadata.update(version='v0001', identifier=VERSION.rsplit('/', 2)[-2], sourceScene=SOURCE, locations={'global': '.'},
                    fps=evidence['fps'], dependencies=evidence['scene_dependencies'],
                    externalFiles=evidence['scene_external'], renderDependencies=block)
    record = dict(evidence, status='prepared', version=VERSION, source=SOURCE, movie=MOVIE,
                  metadata=metadata, missing=missing,
                  dependency_scope='AE composition ' + COMPOSITION_ID + ' from the movie project link; scene-wide top-level fallback',
                  exporter_identity='unknown; scene artist is not asserted as render user',
                  backup=None, backup_reason='No original versioninfo.json existed')
    folder = os.path.dirname(__file__)
    output = os.path.join(folder, RECORD_FILE)
    if os.path.isfile(output):
        with open(output, encoding='utf-8') as handle:
            if json.load(handle).get('status') == 'reconstructed':
                raise RuntimeError('Completed reconstruction record exists; verify instead of overwriting')
    repair.deps.write_json_atomic(output, record)
    if args.apply:
        current = repair.audit.state()
        if repair.audit.norm(current.get('path') or '').lower() != SOURCE.lower():
            raise RuntimeError('Open AE project changed before publication')
        published = repair.nas(CREATE, {'version': VERSION, 'movie': MOVIE, 'metadata': metadata, 'evidence': evidence,
                                       'expected_context': {'application': 'aftereffects', 'type': 'composition',
                                                            'identifier': COMPOSITION_ID, 'name': COMPOSITION_NAME}})
        record.update(published)
        repair.deps.write_json_atomic(output, record)
        journal_path = os.path.join(folder, 'cytonics-full-repair-20261019T182222Z.json')
        with open(journal_path, encoding='utf-8') as handle:
            journal = json.load(handle)
        journal.setdefault('reconstructions', []).append(record)
        target_node = journal['nodes'][VERSION.lower()]
        target_node.update(status='reconstructed', source=SOURCE, block=block, missing=missing,
                           dependencies=block['dependencies']+block['externalFiles'],
                           method='reconstructed AE movie XMP + live composition scan',
                           reconstruction_record=os.path.basename(output))
        target_node.pop('error', None)
        journal['errors'] = [e for e in journal['errors'] if e['version'].lower() != VERSION.lower()]
        repair.deps.write_json_atomic(journal_path, journal)
    print(json.dumps({'status': record['status'], 'target': evidence['target'],
                      'render_inputs': len(block['dependencies']), 'external_inputs': len(block['externalFiles']),
                      'missing': missing, 'record': output}, indent=2))


if __name__ == '__main__':
    main()
