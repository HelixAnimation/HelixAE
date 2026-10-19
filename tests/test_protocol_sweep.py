"""Execute protocol mutations against a small AE DOM fixture, without Qt/Prism."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sweep_protocol', ROOT / 'Scripts/helixae_protocol.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

FIXTURE = r'''
const vm = require('vm'); let next = 10, all = [], undo = 0, commands = [];
class Base {
 constructor(name) { this.name=name; this.id=next++; this.label=2; all.push(this); }
 set parentFolder(p) { if(this.parent) this.parent.children=this.parent.children.filter(x=>x!==this); this.parent=p; if(p) p.children.push(this); }
 get parentFolder() { return this.parent; }
 remove() { this.parentFolder=null; all=all.filter(x=>x!==this); }
}
class FolderItem extends Base {
 constructor(name) { super(name); this.children=[]; this.items={addFolder:(n)=>{let f=new FolderItem(n);f.parentFolder=this;return f;}}; }
 get numItems(){return this.children.length;} item(i){return this.children[i-1];}
}
class FootageItem extends Base {}
class CompItem extends Base {
 constructor(name){super(name);this.frameRate=25;this.displayStartTime=40;this.duration=4;this.layers={add:(f)=>{if(f===bad)throw Error('bad source');let l={source:f};this.children.push(l);return l;}};this.children=[];}
 get numLayers(){return this.children.length;} layer(i){return this.children[i-1];}
 openInViewer(){this.opened=true;}
}
let root=new FolderItem('root'), source=new FootageItem("Client's éclair"), bad=new FootageItem('bad'), comp=new CompItem('Main');
source.parentFolder=root;bad.parentFolder=root;comp.parentFolder=root;
let project={rootFolder:root,activeItem:comp,itemByID:(id)=>all.find(x=>x.id===id),item:(i)=>all[i-1],get numItems(){return all.length;},importFile:(opts)=>{let f=new FootageItem('imported');f.parentFolder=root;return f;}};
class File {constructor(path){this.path=path;this.exists=!path.includes('missing');}}
class ImportOptions {constructor(file){this.file=file;}canImportAs(){return !this.file.path.includes('unsupported');}}
let ctx={JSON,Math,FolderItem,FootageItem,CompItem,File,ImportOptions,ImportAsType:{FOOTAGE:1},app:{project,beginUndoGroup:()=>undo++,endUndoGroup:()=>undo--,executeCommand:(id)=>commands.push(id)}};
function run(script){return JSON.parse(vm.runInNewContext(script,ctx));}
'''


class SweepTests(unittest.TestCase):
    def execute(self, script, setup='', inspect='({})'):
        code = FIXTURE + setup + '\nlet result=run(' + json.dumps(script) + ');console.log(JSON.stringify({result,state:' + inspect + ',undo}));'
        output = subprocess.run(['node', '-e', code], check=True, capture_output=True, text=True)
        return json.loads(output.stdout)

    def test_frame_count_and_start_preserved_on_fps_change(self):
        out = self.execute(p.build_set_comp_fps(13, 23.976), inspect='({start:comp.displayStartTime*comp.frameRate,frames:comp.duration*comp.frameRate})')
        self.assertTrue(out['result']['result'])
        self.assertAlmostEqual(out['state']['start'], 1000, places=3)
        self.assertAlmostEqual(out['state']['frames'], 100, places=3)
        self.assertEqual(out['undo'], 0)

    def test_add_layers_reports_partial_failure(self):
        out = self.execute(p.build_add_footage_to_comp(None, [11, 12, 999]))
        self.assertEqual(out['result']['addedCount'], 1)
        self.assertEqual(len(out['result']['failedItems']), 2)

    def test_rename_wrong_type_never_mutates(self):
        out = self.execute(p.build_rename_move_item(11, 'Renamed', 10, 'comp'), inspect='({name:source.name})')
        self.assertEqual(out['result']['reason'], 'wrong_type')
        self.assertEqual(out['state']['name'], "Client's éclair")

    def test_rename_preserves_unicode_and_delimiters(self):
        name = "Client's éclair || final"
        out = self.execute(p.build_rename_move_item(11, name, 10, 'footage'))
        self.assertEqual(out['result']['newName'], name)

    def test_delete_confirmed_and_missing_rejected(self):
        out = self.execute(p.build_delete_project_item(11, 'footage'), inspect='({exists:!!project.itemByID(11)})')
        self.assertTrue(out['result']['result'])
        self.assertFalse(out['state']['exists'])
        self.assertFalse(self.execute(p.build_delete_project_item(999, 'comp'))['result']['result'])

    def test_reveal_selects_requested_items_only(self):
        out = self.execute(p.build_reveal_items_in_project([11, 13]), inspect='({selected:all.filter(x=>x.selected).map(x=>x.id),commands})')
        self.assertEqual(out['state']['selected'], [11, 13])
        self.assertEqual(out['state']['commands'], [2523])

    def test_import_creates_task_folder_and_preserves_comment(self):
        script = p.build_import_to_shot_folder("Z:/Client's éclair/Beauty.1001.exr", '3D Renders', 'SQ01-SH010', 'Beauty', task_folder='Lighting', label_color=4, comment="Artist's pass")
        out = self.execute(script, inspect='({item:all[all.length-1].name,folder:all[all.length-1].parentFolder.name,label:all[all.length-1].label,comment:all[all.length-1].comment})')
        self.assertTrue(out['result']['result'])
        self.assertEqual(out['state'], dict(item='Beauty', folder='Lighting', label=4, comment="Artist's pass"))
        self.assertEqual(out['undo'], 0)

    def test_failed_import_removes_partial_folders(self):
        out = self.execute(p.build_import_to_shot_folder('unsupported.mov', '2D Renders', 'SH010', 'LowRes', sequence=False), inspect='({items:all.length})')
        self.assertFalse(out['result']['result'])
        self.assertEqual(out['state']['items'], 4)
        self.assertEqual(out['undo'], 0)

    def test_folder_creation_reuses_existing_path(self):
        script = p.build_create_folder_structure(0, "Client's éclair/Comps")
        setup = 'run(' + json.dumps(script) + ');'
        out = self.execute(script, setup, '({items:all.length})')
        self.assertTrue(out['result']['result'])
        self.assertEqual(out['state']['items'], 6)

    def test_empty_nested_folders_removed_without_footage(self):
        out = self.execute(p.build_remove_empty_folders(), "let a=root.items.addFolder('a');a.items.addFolder('b');", '({items:all.length})')
        self.assertEqual(out['result']['deletedCount'], 2)
        self.assertEqual(out['state']['items'], 4)

    def test_labels_and_comments_require_existing_item(self):
        out = self.execute(p.build_set_item_properties(11, label=4, comment="Client's pass"), inspect='({label:source.label,comment:source.comment})')
        self.assertEqual(out['state'], {'label': 4, 'comment': "Client's pass"})
        self.assertFalse(self.execute(p.build_set_item_properties(999, label=4))['result']['result'])

    def test_empty_response_never_success(self):
        for response in (None, '', b'', 'SUCCESS', 'SUCCESS|1|0'):
            data, error = p.parse_json_response(response)
            self.assertFalse(p.ack_result(data, error)[0])

    def test_validation_prevents_invalid_requests(self):
        calls = [lambda: p.build_add_footage_to_comp(None, []), lambda: p.build_set_item_properties(1), lambda: p.build_set_item_labels([1], 17), lambda: p.build_create_folder_structure(0, ''), lambda: p.build_import_to_shot_folder('x.mov', '', 'SH', 'LowRes')]
        for call in calls:
            with self.assertRaises((ValueError, TypeError)):
                call()

    def test_bypass_toggle_accepts_shared_set_storage(self):
        path = ROOT / 'Scripts/footage_tracker/tree_operations_core.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_handleCtrlClickBypass')
        node.decorator_list = []
        namespace = {'Qt': SimpleNamespace(UserRole=1)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), namespace)
        ignored = {'outdated': set()}
        saved = []
        warnings = SimpleNamespace(_getIgnoredItems=lambda: ignored, _saveIgnoredItems=lambda value: saved.append(value['outdated'].copy()))
        scroll = SimpleNamespace(value=lambda: 12, setValue=lambda value: None)
        tracker = SimpleNamespace(startup_warnings=warnings, tw_footage=SimpleNamespace(verticalScrollBar=lambda: scroll, columnAt=lambda x: 2), loadFootageData=lambda: None)
        obj = SimpleNamespace(tracker=tracker, _generateTreeItemKey=lambda item, data: 'footage_SH_LowRes')
        item = SimpleNamespace(data=lambda *args: {'type': 'footage'})
        pos = SimpleNamespace(x=lambda: 2)
        namespace['_handleCtrlClickBypass'](obj, item, pos)
        namespace['_handleCtrlClickBypass'](obj, item, pos)
        self.assertEqual(saved, [{'footage_SH_LowRes'}, set()])

    def test_current_scene_lookup_consumes_path_field(self):
        path = ROOT / 'Scripts/footage_tracker/import_shots.py'
        tree = ast.parse(path.read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'getCurrentAEFile')
        node.decorator_list = []
        namespace = {'helixae_protocol': p, 'os': SimpleNamespace(path=SimpleNamespace(exists=lambda path: True))}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(path), 'exec'), namespace)
        core = SimpleNamespace(executeAppleScript=lambda script: json.dumps({'result': True, 'path': "Z:\\Client's éclair\\scene.aep"}))
        obj = SimpleNamespace(main=SimpleNamespace(ae_core=core))
        self.assertEqual(namespace['getCurrentAEFile'](obj), "Z:/Client's éclair/scene.aep")


if __name__ == '__main__':
    unittest.main()
