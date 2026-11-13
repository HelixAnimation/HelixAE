/* Temporary Windows AE utility. Run via File > Scripts > Run Script File.
 * Choose the historical source project, composition and render version yourself.
 * Does not save the AE project, queue a render, or change other metadata fields.
 * A verified byte-for-byte .bak is retained beside versioninfo.json.
 */
(function () {
    // Local strict JSON codec: ExtendScript does not provide native JSON.
    // No eval, and no global JSON replacement.
    function parse(text) {
        var i = 0;
        function ws() { while (/\s/.test(text.charAt(i)) && i < text.length) i++; }
        function fail() { throw new Error("Invalid JSON at character " + i); }
        function string() {
            var out = "", c, hex, escapes = {'"':'"', '\\':'\\', '/':'/', b:'\b', f:'\f', n:'\n', r:'\r', t:'\t'};
            i++;
            while (i < text.length) {
                c = text.charAt(i++);
                if (c === '"') return out;
                if (c === '\\') {
                    c = text.charAt(i++);
                    if (c === 'u') {
                        hex = text.substr(i, 4);
                        if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail();
                        out += String.fromCharCode(parseInt(hex, 16)); i += 4;
                    } else if (escapes.hasOwnProperty(c)) out += escapes[c];
                    else fail();
                } else { if (c.charCodeAt(0) < 32) fail(); out += c; }
            }
            fail();
        }
        function value() {
            ws(); var c = text.charAt(i), out, key, m;
            if (c === '"') return string();
            if (c === '{') {
                out = {}; i++; ws();
                if (text.charAt(i) === '}') { i++; return out; }
                while (true) {
                    ws(); if (text.charAt(i) !== '"') fail(); key = string();
                    if (key === '__proto__' || Object.prototype.hasOwnProperty.call(out, key)) throw new Error("Unsupported or duplicate JSON key: " + key);
                    ws(); if (text.charAt(i++) !== ':') fail(); out[key] = value(); ws();
                    c = text.charAt(i++); if (c === '}') return out; if (c !== ',') fail();
                }
            }
            if (c === '[') {
                out = []; i++; ws(); if (text.charAt(i) === ']') { i++; return out; }
                while (true) { out.push(value()); ws(); c = text.charAt(i++); if (c === ']') return out; if (c !== ',') fail(); }
            }
            m = /^(true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(text.substr(i));
            if (!m) fail(); i += m[0].length;
            if (m[0] === 'true') return true;
            if (m[0] === 'false') return false;
            if (m[0] === 'null') return null;
            // Refuse values that could lose precision during rewriting.
            out = Number(m[0]);
            if (!isFinite(out) || Math.abs(out) > 9007199254740991) throw new Error("JSON number cannot be safely preserved");
            return out;
        }
        var result = value(); ws(); if (i !== text.length) fail(); return result;
    }
    function stringify(v) {
        var parts = [], k;
        if (v === null) return 'null';
        if (typeof v === 'string') return '"' + v.replace(/["\\\x00-\x1f]/g, function (c) {
            return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
        }) + '"';
        if (typeof v === 'number' || typeof v === 'boolean') return String(v);
        if (v instanceof Array) {
            for (k = 0; k < v.length; k++) parts.push(stringify(v[k]));
            return '[' + parts.join(',\n') + ']';
        }
        for (k in v) if (Object.prototype.hasOwnProperty.call(v, k)) parts.push(stringify(k) + ': ' + stringify(v[k]));
        return '{\n' + parts.join(',\n') + '\n}';
    }
    function read(file, encoding) {
        file.encoding = encoding;
        if (!file.open('r')) throw new Error("Cannot read " + file.fsName + ': ' + file.error);
        try { return file.read(); } finally { file.close(); }
    }
    function write(file, text, encoding) {
        file.encoding = encoding;
        if (!file.open('w')) throw new Error("Cannot stage " + file.fsName);
        try { if (!file.write(text)) throw new Error("Write failed: " + file.error); }
        finally { file.close(); }
    }
    function normalized(p) { return p.replace(/\\/g, '/'); }
    function identity(p) { return normalized(p).toLowerCase(); }
    // Mirrors FootageUtils.detectFolderType, including its precedence rules.
    function isRender(path) {
        var p = identity(path), parts = p.split('/'), j, part;
        if (p.indexOf('/renders/3drender/') >= 0 || p.indexOf('/renders/2drender/') >= 0 || p.indexOf('/playblasts/') >= 0) return true;
        if (p.indexOf('/04_resources/') >= 0 || p.indexOf('z:/') === 0) return false;
        for (j = 0; j < parts.length; j++) {
            part = parts[j];
            if (/^(3drenders?|2drenders?|playblasts?)$/.test(part)) return true;
            if (part === '04_resources' || part === 'resources' || part === 'stockfootage' ||
                    (part === 'library' && j > 0 && parts[j - 1].indexOf('z') === 0)) return false;
        }
        return /renders\/3d|3d\/render|renders3d|renders\/2d|2d\/render|renders2d|playblasts?\//.test(p);
    }
    function scan(comp) {
        var visited = {}, seen = {}, dependencies = [], external = [], missing = [];
        function walk(c) {
            var k = String(c.id), j, source, file, path;
            if (visited[k]) return; visited[k] = true;
            for (j = 1; j <= c.numLayers; j++) {
                // Fail closed on unreadable layers rather than publish a partial scan.
                source = c.layer(j).source;
                if (source instanceof CompItem) walk(source);
                else if (source instanceof FootageItem && source.mainSource instanceof FileSource) {
                    file = source.mainSource.file || source.file;
                    if (!file || !file.fsName) continue;
                    path = normalized(file.fsName);
                    if (seen['p:' + path]) continue; seen['p:' + path] = true;
                    if (!file.exists) missing.push(path);
                    else if (isRender(path)) dependencies.push(path);
                    else external.push(path);
                }
            }
        }
        walk(comp); dependencies.sort(); external.sort(); missing.sort();
        return {block: {context: {application: 'aftereffects', type: 'composition', identifier: String(comp.id), name: comp.name},
            dependencies: dependencies, externalFiles: external}, missing: missing};
    }
    function psQuote(s) { return "'" + s.replace(/'/g, "''") + "'"; }
    function encodedCommand(text) {
        var bytes = [], alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/', out = '', i, a, b, c;
        for (i = 0; i < text.length; i++) { a = text.charCodeAt(i); bytes.push(a & 255); bytes.push(a >> 8); }
        for (i = 0; i < bytes.length; i += 3) {
            a = bytes[i]; b = bytes[i + 1]; c = bytes[i + 2];
            out += alphabet.charAt(a >> 2) + alphabet.charAt(((a & 3) << 4) | ((b || 0) >> 4));
            out += i + 1 < bytes.length ? alphabet.charAt(((b & 15) << 2) | ((c || 0) >> 6)) : '=';
            out += i + 2 < bytes.length ? alphabet.charAt(c & 63) : '=';
        }
        return out;
    }
    var staged = null, expected = null;
    try {
        if ($.os.toLowerCase().indexOf('windows') < 0) throw new Error('This temporary utility requires Windows PowerShell.');
        if (!app.project || !app.project.file) throw new Error('Open the original saved AE source project first.');
        var project = app.project, scene = project.file.fsName, comps = [], i;
        var dialog = new Window('dialog', 'Repair Render Dependencies');
        dialog.orientation = 'column'; dialog.alignChildren = 'fill';
        dialog.add('statictext', undefined, 'Source: ' + scene);
        dialog.add('statictext', undefined, 'Choose the composition that produced the historical render:');
        var dropdown = dialog.add('dropdownlist'), entry;
        for (i = 1; i <= project.numItems; i++) {
            entry = project.item(i);
            if (entry instanceof CompItem) { comps.push(entry); dropdown.add('item', entry.name + ' (ID ' + entry.id + ')'); }
        }
        if (!comps.length) throw new Error('No compositions in this project.');
        // Explicit selection required; never infer from the active comp.
        var buttons = dialog.add('group');
        var choose = buttons.add('button', undefined, 'Choose versioninfo.json…'); choose.enabled = false;
        buttons.add('button', undefined, 'Cancel', {name:'cancel'});
        dropdown.onChange = function () { choose.enabled = dropdown.selection !== null; };
        choose.onClick = function () { dialog.close(1); };
        if (dialog.show() !== 1) return;
        var comp = comps[dropdown.selection.index];
        var target = File.openDialog('Select the EXISTING render versioninfo.json', '*.json', false);
        if (!target) return;
        if (target.name.toLowerCase() !== 'versioninfo.json') throw new Error('Select a render version directory\'s versioninfo.json.');
        var originalBytes = read(target, 'BINARY');
        var data = parse(read(target, 'UTF-8').replace(/^\uFEFF/, ''));
        if (!data || data instanceof Array || typeof data !== 'object') throw new Error('versioninfo must be a JSON object.');
        if (typeof data.sourceScene !== 'string' || identity(data.sourceScene) !== identity(scene)) {
            throw new Error('Source scene mismatch. Open the exact sourceScene recorded in this render metadata:\n' + (data.sourceScene || '(missing sourceScene)'));
        }
        var result = scan(comp);
        var review = new Window('dialog', 'Review Dependency Repair'); review.alignChildren = 'fill';
        var summary = 'Composition: ' + comp.name + ' (ID ' + comp.id + ')\nTarget: ' + target.fsName +
            '\nRecorded task: ' + data.identifier + '   Version: ' + data.version +
            '\nSource: ' + scene + '\n\nRender inputs: ' + result.block.dependencies.length +
            '\nExternal/resource inputs: ' + result.block.externalFiles.length + '\nMissing inputs (EXCLUDED): ' + result.missing.length +
            '\n\nAn empty successful scan is authoritative.\n\nDEPENDENCIES\n' + result.block.dependencies.join('\n') +
            '\n\nEXTERNAL FILES\n' + result.block.externalFiles.join('\n') + '\n\nMISSING\n' + result.missing.join('\n');
        review.add('edittext', undefined, summary, {multiline:true, scrolling:true, readonly:true}).preferredSize = [850, 480];
        var actions = review.add('group');
        actions.add('button', undefined, 'Back Up & Update', {name:'ok'});
        actions.add('button', undefined, 'Cancel', {name:'cancel'});
        if (review.show() !== 1) return;
        if (app.project !== project || identity(project.file.fsName) !== identity(scene)) throw new Error('The open project changed. Run the utility again.');
        data.renderDependencies = result.block;
        var token = String(new Date().getTime()) + '-' + Math.floor(Math.random() * 1000000);
        staged = new File(target.fsName + '.' + token + '.tmp');
        expected = new File(target.fsName + '.' + token + '.expected.tmp');
        var backup = target.fsName + '.before-render-deps-' + token + '.bak';
        write(staged, stringify(data) + '\n', 'UTF-8');
        if (stringify(parse(read(staged, 'UTF-8').replace(/^\uFEFF/, ''))) !== stringify(data)) throw new Error('Staged JSON failed validation.');
        write(expected, originalBytes, 'BINARY');
        if (read(expected, 'BINARY') !== originalBytes) throw new Error('Original-byte staging failed verification.');
        // .NET File.Replace atomically publishes the already validated stage.
        // If the filesystem does not support replacement, fail without delete/rename fallback.
        var command = "$ErrorActionPreference='Stop'; try { " +
            '$target=' + psQuote(target.fsName) + '; $stage=' + psQuote(staged.fsName) +
            '; $expected=' + psQuote(expected.fsName) + '; $backup=' + psQuote(backup) + '; ' +
            'function bytes($p) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($p)) }; ' +
            '$old=bytes $expected; if ((bytes $target) -cne $old) { throw "Original changed since review" }; ' +
            '[IO.File]::Copy($target,$backup,$false); if ((bytes $backup) -cne $old) { throw "Backup verification failed" }; ' +
            'if ((bytes $target) -cne $old) { throw "Original changed after backup" }; ' +
            '$new=bytes $stage; [IO.File]::Replace($stage,$target,$null); ' +
            'if ((bytes $target) -cne $new) { throw "Installed file verification failed; retain backup" }; ' +
            'Write-Output "HELIX_REPAIR_OK" } catch { Write-Output ("HELIX_REPAIR_ERROR: " + $_.Exception.Message) }';
        var output = system.callSystem('powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + encodedCommand(command));
        if (output.indexOf('HELIX_REPAIR_OK') < 0) throw new Error(output + '\nBackup, if created: ' + backup);
        if (stringify(parse(read(target, 'UTF-8').replace(/^\uFEFF/, ''))) !== stringify(data)) throw new Error('Final JSON validation failed. Backup: ' + backup);
        alert('Updated renderDependencies successfully.\n\n' + target.fsName + '\n\nVerified original backup:\n' + backup);
    } catch (e) {
        alert('Dependency repair failed:\n' + e.toString());
    } finally {
        if (staged && staged.exists) staged.remove();
        if (expected && expected.exists) expected.remove();
    }
})();
