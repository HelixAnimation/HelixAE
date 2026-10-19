# -*- coding: utf-8 -*-
"""Shared AE request/response protocol helpers (Phase 3).

Pure-stdlib module so every After Effects round trip can be unit tested
without Prism or Qt.  It is imported flat (``import helixae_protocol``)
because Prism puts the plugin's Scripts directory on ``sys.path``.

Responsibilities:

- ``js_string()``: the only supported way to embed a Python string into
  ExtendScript (paths, names, AOVs, templates).  Never interpolate user
  data into quoted literals with ``%`` or f-strings.
- ``ensure_json_polyfill()``: prepends the Crockford json2 polyfill when a
  script contains the literal ``JSON.``.  ExtendScript has no native JSON,
  so every JSON-returning script depends on this.  Both 9888 senders
  (``HelixAECore.executeAppleScript`` and ``HelixAE_Functions.sendCmd``)
  call it.
- Script builders returning ExtendScript that always answers with a
  ``JSON.stringify`` document (mutations confirm success explicitly and
  clean up partially created objects on failure).
- Strict response parsers: ``None``/empty/non-JSON/malformed responses are
  failures, never success (the ``err_catcher`` contract turns transport
  exceptions into ``None``).
"""

import json
import re

JSON2_POLYFILL = r"""
if(typeof JSON==='undefined'){JSON={};
(function(){'use strict';function f(n){return n<10?'0'+n:n;}
if(typeof Date.prototype.toJSON!=='function'){Date.prototype.toJSON=function(){return isFinite(this.valueOf())?this.getUTCFullYear()+'-'+f(this.getUTCMonth()+1)+'-'+f(this.getUTCDate())+'T'+f(this.getUTCHours())+':'+f(this.getUTCMinutes())+':'+f(this.getUTCSeconds())+'Z':null;};}
var cx=/[\u0000\u00ad\u0600-\u0604\u070f\u17b4\u17b5\u200c-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]/g,escapable=/[\\\"\x00-\x1f\x7f-\x9f\u00ad\u0600-\u0604\u070f\u17b4\u17b5\u200c-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]/g,gap,indent,meta={'\b':'\\b','\t':'\\t','\n':'\\n','\f':'\\f','\r':'\\r','"':'\\"','\\':'\\\\'},rep;
function quote(string){escapable.lastIndex=0;return escapable.test(string)?'"'+string.replace(escapable,function(a){var c=meta[a];return typeof c==='string'?c:'\\u'+('0000'+a.charCodeAt(0).toString(16)).slice(-4);})+'"':'"'+string+'"';}
function str(key,holder){var i,k,v,length,mind=gap,partial,value=holder[key];if(value&&typeof value==='object'&&typeof value.toJSON==='function'){value=value.toJSON(key);}
if(typeof rep==='function'){value=rep.call(holder,key,value);}
switch(typeof value){case'string':return quote(value);case'number':return isFinite(value)?String(value):'null';case'boolean':case'null':return String(value);case'object':if(!value){return 'null';}
gap+=indent;partial=[];if(Object.prototype.toString.apply(value)==='[object Array]'){length=value.length;for(i=0;i<length;i+=1){partial[i]=str(i,value)||'null';}
v=partial.length===0?'[]':gap?'[\n'+gap+partial.join(',\n'+gap)+'\n'+mind+']':'['+partial.join(',')+']';gap=mind;return v;}
if(rep&&typeof rep==='object'){length=rep.length;for(i=0;i<length;i+=1){if(typeof rep[i]==='string'){k=rep[i];v=str(k,value);if(v){partial.push(quote(k)+(gap?': ':':')+v);}}}}else{for(k in value){if(Object.prototype.hasOwnProperty.call(value,k)){v=str(k,value);if(v){partial.push(quote(k)+(gap?': ':':')+v);}}}}
v=partial.length===0?'{}':gap?'{\n'+gap+partial.join(',\n'+gap)+'\n'+mind+'}':'{'+partial.join(',')+'}';gap=mind;return v;}}
if(typeof JSON.stringify!=='function'){JSON.stringify=function(value,replacer,space){var i;gap='';indent='';if(typeof space==='number'){for(i=0;i<space;i+=1){indent+=' ';}}else if(typeof space==='string'){indent=space;}
rep=replacer;if(replacer&&typeof replacer!=='function'&&(typeof replacer!=='object'||typeof replacer.length!=='number')){throw new Error('JSON.stringify');}
return str('',{'':value});};}
if(typeof JSON.parse!=='function'){JSON.parse=function(text,reviver){var j;function walk(holder,key){var k,v,value=holder[key];if(value&&typeof value==='object'){for(k in value){if(Object.prototype.hasOwnProperty.call(value,k)){v=walk(holder,key,value);if(v!==undefined){value[k]=v;}else{delete value[k];}}}}
return reviver.call(holder,key,value);}
text=String(text);cx.lastIndex=0;if(cx.test(text)){text=text.replace(cx,function(a){return'\\u'+('0000'+a.charCodeAt(0).toString(16)).slice(-4);});}
if(/^[\],:{}\s]*$/.test(text.replace(/\\(?:["\\\/bfnrt]|u[0-9a-fA-F]{4})/g,'@').replace(/"[^"\\\n\r]*"|true|false|null|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?/g,']').replace(/(?:^|:|,)(?:\s*\[)+/g,''))){j=eval('('+text+')');return typeof reviver==='function'?walk({'':j},''):j;}
throw new SyntaxError('JSON.parse');};}
}());}
"""


def ensure_json_polyfill(script):
    """Prepend the json2 polyfill when the script uses ``JSON.``.

    ExtendScript has no native JSON object; without the polyfill every
    JSON-returning script throws.  The trigger is the literal ``JSON.``
    so already-polyfilled scripts are not double-wrapped.
    """
    if "JSON." not in script:
        return script
    if script.lstrip().startswith("if(typeof JSON==='undefined')"):
        return script
    return JSON2_POLYFILL + script


def js_string(value):
    """Embed a Python string as an ExtendScript string literal.

    Uses ASCII-only JSON escaping, which is valid ES3 string syntax and
    survives the UTF-8 bridge unchanged (including apostrophes, quotes,
    backslashes, Unicode, and newlines in paths and item names).
    """
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    elif not isinstance(value, str):
        raise TypeError("expected str, got %r" % type(value).__name__)
    return json.dumps(value, ensure_ascii=True)


def js_bool(value):
    return "true" if value else "false"


def _as_int(value, name):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("invalid %s: %r" % (name, value))
    return number


def _as_number(value, name):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError("invalid %s: %r" % (name, value))
    if number != number:  # NaN
        raise ValueError("invalid %s: %r" % (name, value))
    return number


def _validate_path(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty path")
    return value


def _wrap(body):
    """Wrap a script body in a try/catch IIFE that answers with JSON."""
    return (
        "(function () {\n"
        "    try {\n"
        + body
        + "    } catch (e) {\n"
        + '        return JSON.stringify({ result: false, details: "script error: " + e.toString() });\n'
        + "    }\n"
        + "})();"
    )


def decode_response(result):
    """Return ``(text, error)``; error is set for None/empty responses."""
    if result is None:
        return None, "empty response from After Effects"
    if isinstance(result, bytes):
        result = result.decode("utf-8", errors="replace")
    elif not isinstance(result, str):
        result = str(result)
    result = result.strip()
    if not result:
        return None, "empty response from After Effects"
    return result, None


def parse_json_response(result):
    """Strictly parse a JSON object response.

    Returns ``(data, error)``.  Failure modes (never successes):
    ``None``/empty input (transport failure or swallowed exception),
    non-UTF-8 text, invalid JSON, JSON that is not an object, and the
    literal ``"null"`` (script expression evaluated to null/undefined).
    """
    text, error = decode_response(result)
    if error:
        return None, error
    try:
        data = json.loads(text)
    except ValueError:
        return None, "invalid JSON response: %r" % text[:200]
    if not isinstance(data, dict):
        return None, "malformed response (not a JSON object)"
    return data, None


def parse_json_array(result):
    """Strictly parse a JSON array response.  Same contract as above."""
    text, error = decode_response(result)
    if error:
        return None, error
    try:
        data = json.loads(text)
    except ValueError:
        return None, "invalid JSON response: %r" % text[:200]
    if not isinstance(data, list):
        return None, "malformed response (not a JSON array)"
    return data, None


def ack_result(data, error):
    """Extract the boolean ``result`` field of an acknowledgement."""
    if error:
        return None, error
    if "result" not in data:
        return None, "malformed response (missing result)"
    return bool(data["result"]), None


# ---------------------------------------------------------------------------
# Read-only query builders
# ---------------------------------------------------------------------------


def build_has_active_comp():
    return _wrap(
        '        var item = (app.project && app.project.activeItem)\n'
        '            ? app.project.activeItem : null;\n'
        '        return JSON.stringify({ result: !!(item && item instanceof CompItem) });\n'
    )


def build_get_composition_names():
    return _wrap(
        "        var names = [];\n"
        "        if (app.project && app.project.items) {\n"
        "            for (var i = 1; i <= app.project.items.length; i++) {\n"
        "                var item = app.project.items[i];\n"
        "                if (item instanceof CompItem) { names.push(item.name); }\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, compositions: names });\n"
    )


def build_list_project_comps():
    """List all compositions as {id, name} pairs."""
    return _wrap(
        "        var comps = [];\n"
        "        if (app.project && app.project.items) {\n"
        "            for (var i = 1; i <= app.project.items.length; i++) {\n"
        "                var item = app.project.items[i];\n"
        "                if (item instanceof CompItem) { comps.push({ id: item.id, name: item.name }); }\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, comps: comps });\n"
    )


def build_get_frame_range():
    return _wrap(
        "        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {\n"
        "            var comp = app.project.activeItem;\n"
        "            var displayStart = comp.displayStartFrame;\n"
        "            var endFrame = displayStart + Math.round(comp.duration * comp.frameRate) - 1;\n"
        "            return JSON.stringify({ result: true, startFrame: displayStart, endFrame: endFrame });\n"
        "        }\n"
        '        return JSON.stringify({ result: false, details: "No active composition found." });\n'
    )


def build_set_frame_range(start_frame, end_frame):
    start = _as_int(start_frame, "start frame")
    end = _as_int(end_frame, "end frame")
    if end < start:
        raise ValueError("end frame before start frame")
    return _wrap(
        "        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {\n"
        "            var comp = app.project.activeItem;\n"
        "            comp.displayStartFrame = %d;\n"
        "            comp.duration = (%d - %d + 1) / comp.frameRate;\n"
        "            comp.workAreaStart = 0;\n"
        "            comp.workAreaDuration = comp.duration;\n"
        "            return JSON.stringify({ result: true });\n"
        "        }\n"
        '        return JSON.stringify({ result: false, details: "No active composition found." });\n'
        % (start, end, start)
    )


def build_get_fps():
    return _wrap(
        "        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {\n"
        "            return JSON.stringify({ result: true, frameRate: app.project.activeItem.frameRate });\n"
        "        }\n"
        '        return JSON.stringify({ result: false, details: "No active composition found." });\n'
    )


def build_set_fps(fps):
    rate = _as_number(fps, "frame rate")
    if rate <= 0:
        raise ValueError("frame rate must be positive")
    return _wrap(
        "        if (app.project && app.project.activeItem && app.project.activeItem instanceof CompItem) {\n"
        "            var comp = app.project.activeItem;\n"
        "            comp.frameRate = %s;\n"
        "            return JSON.stringify({ result: true, frameRate: comp.frameRate });\n"
        "        }\n"
        '        return JSON.stringify({ result: false, details: "No active composition found." });\n'
        % repr(rate)
    )


def build_get_app_version():
    return _wrap(
        "        if (app) { return JSON.stringify({ result: true, version: app.version }); }\n"
        '        return JSON.stringify({ result: false, details: "No app found." });\n'
    )


def build_get_current_file():
    return _wrap(
        "        if (app.project && app.project.file) {\n"
        "            return JSON.stringify({ result: true, path: app.project.file.fsName });\n"
        "        }\n"
        "        return JSON.stringify({ result: false });\n"
    )


def build_get_xmp_packet():
    """Read the project XMP packet as a JSON string response."""
    return _wrap(
        "        if (app.project) {\n"
        "            var packet = app.project.xmpPacket || '';\n"
        "            return JSON.stringify({ result: true, packet: packet });\n"
        "        }\n"
        "        return JSON.stringify({ result: false });\n"
    )


def build_set_xmp_packet(packet, required_marker=None):
    """Assign the project XMP packet and CONFIRM the assignment.

    After Effects may normalize or reject packets; success is only
    reported when re-reading ``app.project.xmpPacket`` contains
    ``required_marker`` (when given) or matches the assigned packet
    length otherwise.  The packet is embedded via ``js_string`` so
    quotes/newlines/backslashes in XML survive intact.
    """
    if not isinstance(packet, str) or not packet:
        raise ValueError("empty XMP packet")
    if required_marker is not None and (
        not isinstance(required_marker, str) or not required_marker
    ):
        raise ValueError("empty required marker")
    if required_marker:
        check = (
            "        var readback = app.project.xmpPacket || '';\n"
            "        var ok = (readback.indexOf(%s) !== -1);\n"
            "        if (!ok) {\n"
            '            return JSON.stringify({ result: false, details: "After Effects did not keep the XMP payload" });\n'
            "        }\n" % js_string(required_marker)
        )
    else:
        check = (
            "        var readback = app.project.xmpPacket || '';\n"
            "        var ok = (readback === packet);\n"
            "        if (!ok) {\n"
            '            return JSON.stringify({ result: false, details: "After Effects modified the XMP packet on assignment" });\n'
            "        }\n"
        )
    script = (
        "        if (!app.project) {\n"
        '            return JSON.stringify({ result: false, details: "No project found." });\n'
        "        }\n"
        "        var packet = %s;\n"
        "        app.project.xmpPacket = packet;\n"
        % js_string(packet)
    ) + check + '        return JSON.stringify({ result: true });\n'
    return _wrap(script)


def build_get_footage_from_project():
    """File-backed footage only: solids/placeholders have no usable file."""
    return _wrap(
        "        var items = [];\n"
        "        if (app.project && app.project.items) {\n"
        "            for (var i = 1; i <= app.project.items.length; i++) {\n"
        "                var item = null;\n"
        "                try { item = app.project.item(i); } catch (e) { continue; }\n"
        "                if (!item || !(item instanceof FootageItem)) { continue; }\n"
        "                if (!(item.mainSource instanceof FileSource)) { continue; }\n"
        "                if (!item.file || !item.file.fsName) { continue; }\n"
        "                items.push({ idx: i, path: item.file.fsName, name: item.name });\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify(items);\n"
    )


# ---------------------------------------------------------------------------
# Mutation builders (explicit, confirmed results)
# ---------------------------------------------------------------------------


def build_save_scene(filepath):
    """Save the project and confirm the on-disk result."""
    path = _validate_path(filepath)
    return _wrap(
        "        var target = new File(%s);\n"
        "        app.project.save(target);\n"
        "        var saved = (app.project && app.project.file) ? app.project.file.fsName : null;\n"
        "        var normalize = function (p) {\n"
        "            return p.split(String.fromCharCode(92)).join('/').toLowerCase();\n"
        "        };\n"
        "        if (!saved || normalize(saved) !== normalize(target.fsName)) {\n"
        '            return JSON.stringify({ result: false, details: "project was not saved to the requested path", path: saved });\n'
        "        }\n"
        "        return JSON.stringify({ result: true, path: saved });\n"
        % js_string(path)
    )


def build_open_scene(filepath):
    path = _validate_path(filepath)
    return _wrap(
        "        var target = new File(%s);\n"
        "        if (!target.exists) {\n"
        '            return JSON.stringify({ result: false, details: "file does not exist", path: target.fsName });\n'
        "        }\n"
        "        var project = app.open(target);\n"
        "        if (!project || !project.file) {\n"
        '            return JSON.stringify({ result: false, details: "After Effects did not open the project" });\n'
        "        }\n"
        "        return JSON.stringify({ result: true, path: project.file.fsName });\n"
        % js_string(path)
    )


def build_import_media(filepath, sequence=False, add_to_comp=False):
    path = _validate_path(filepath)
    return _wrap(
        "        if (!app.project) {\n"
        '            return JSON.stringify({ result: false, details: "No project found." });\n'
        "        }\n"
        "        var importOptions = new ImportOptions(new File(%s));\n"
        "        importOptions.sequence = %s;\n"
        "        if (importOptions.canImportAs(ImportAsType.FOOTAGE)) {\n"
        "            importOptions.importAs = ImportAsType.FOOTAGE;\n"
        "        }\n"
        "        var importedFile = app.project.importFile(importOptions);\n"
        "        if (!importedFile) {\n"
        '            return JSON.stringify({ result: false, details: "import returned no item" });\n'
        "        }\n"
        "        %s"
        "        return JSON.stringify({ result: true, fileName: importedFile.name });\n"
        % (
            js_string(path),
            js_bool(sequence),
            (
                "        if (app.project.activeItem instanceof CompItem) {\n"
                "            app.project.activeItem.layers.add(importedFile);\n"
                "        }\n"
                if add_to_comp
                else ""
            ),
        )
    )


def build_replace_active_item(filepath, sequence=False):
    path = _validate_path(filepath)
    replace_call = (
        "curItem.replaceWithSequence(new File(%s), false);" % js_string(path)
        if sequence
        else "curItem.replace(new File(%s));" % js_string(path)
    )
    return _wrap(
        "        if (app.project && app.project.activeItem && app.project.activeItem instanceof FootageItem) {\n"
        "            var curItem = app.project.activeItem;\n"
        "            %s\n"
        "            return JSON.stringify({ result: true, fileName: curItem.name });\n"
        "        }\n"
        '        return JSON.stringify({ result: false, details: "No active item found." });\n'
        % replace_call
    )


def build_replace_item(idx, filepath, sequence=False):
    index = _as_int(idx, "item index")
    if index <= 0:
        raise ValueError("invalid item index: %r" % (idx,))
    path = _validate_path(filepath)
    replace_call = (
        "curItem.replaceWithSequence(new File(%s), false);" % js_string(path)
        if sequence
        else "curItem.replace(new File(%s));" % js_string(path)
    )
    return _wrap(
        "        if (!app.project) {\n"
        '            return JSON.stringify({ result: false, details: "No project active." });\n'
        "        }\n"
        "        var curItem = null;\n"
        "        try { curItem = app.project.item(%d); } catch (e) { curItem = null; }\n"
        "        if (!curItem || !(curItem instanceof FootageItem)) {\n"
        '            return JSON.stringify({ result: false, details: "Item is not footage." });\n'
        "        }\n"
        "        %s\n"
        "        return JSON.stringify({ result: true, fileName: curItem.name });\n"
        % (index, replace_call)
    )


# ---------------------------------------------------------------------------
# Export / render queue builders
# ---------------------------------------------------------------------------


def build_get_output_module_templates():
    """List output-module templates via a temporary render-queue item."""
    return _wrap(
        "        var templates = null;\n"
        "        var renderQueue = app.project.renderQueue;\n"
        "        if (renderQueue.numItems > 0) {\n"
        "            templates = renderQueue.item(1).outputModule(1).templates;\n"
        "        } else if (app.project.activeItem && app.project.activeItem instanceof CompItem) {\n"
        "            var tempItem = renderQueue.items.add(app.project.activeItem);\n"
        "            try { templates = tempItem.outputModule(1).templates; }\n"
        "            finally { tempItem.remove(); }\n"
        "        }\n"
        "        if (!templates) {\n"
        '            return JSON.stringify({ result: false, details: "No render queue item and no active composition." });\n'
        "        }\n"
        "        var names = [];\n"
        "        for (var i = 0; i < templates.length; i++) { names.push(templates[i]); }\n"
        "        return JSON.stringify({ result: true, templates: names });\n"
    )


def build_get_active_comp_info():
    """Return the active composition's id and name as a JSON ack."""
    return _wrap(
        "        var comp = (app.project && app.project.activeItem) ? app.project.activeItem : null;\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, details: "No active composition found." });\n'
        "        }\n"
        "        return JSON.stringify({\n"
        "            result: true,\n"
        "            compId: String(comp.id),\n"
        "            compName: comp.name\n"
        "        });\n"
    )


def build_comp_dependency_script(comp_id):
    """Collect file-backed footage reachable from one composition.

    Every layer source is walked regardless of layer visibility or
    enabled state, and nested compositions are traversed recursively with
    a cycle guard.  Only ``FootageItem`` sources backed by a real file are
    returned.  The response is JSON::

        {result: true, composition: {id, name}, footage: [{id, name, path}]}
    """
    comp_id = _as_int(comp_id, "composition id")
    if comp_id <= 0:
        raise ValueError("invalid composition id: %r" % (comp_id,))
    return _wrap(
        "        if (!app.project || app.project.numItems <= 0) {\n"
        '            return JSON.stringify({ result: false, reason: "no_project", details: "No open project." });\n'
        "        }\n"
        "        var target = app.project.itemByID(%d);\n"
        "        if (!target) {\n"
        '            return JSON.stringify({ result: false, reason: "comp_not_found", details: "Composition not found." });\n'
        "        }\n"
        "        if (!(target instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "not_a_comp", details: "Item is not a composition." });\n'
        "        }\n"
        "        var footageById = {};\n"
        "        var visitedComps = {};\n"
        "        var walkComp = function (comp) {\n"
        "            var compKey = String(comp.id);\n"
        "            if (visitedComps[compKey]) { return; }\n"
        "            visitedComps[compKey] = true;\n"
        "            for (var i = 1; i <= comp.numLayers; i++) {\n"
        "                var layer = null;\n"
        "                try { layer = comp.layer(i); } catch (e) { continue; }\n"
        "                if (!layer || !layer.source) { continue; }\n"
        "                var src = layer.source;\n"
        "                if (src instanceof CompItem) {\n"
        "                    walkComp(src);\n"
        "                } else if (src instanceof FootageItem) {\n"
        "                    if (!(src.mainSource instanceof FileSource)) { continue; }\n"
        "                    var file = src.mainSource.file || src.file;\n"
        "                    if (!file || !file.fsName) { continue; }\n"
        "                    var footageKey = String(src.id);\n"
        "                    if (footageById[footageKey]) { continue; }\n"
        "                    footageById[footageKey] = {\n"
        "                        id: footageKey,\n"
        "                        name: src.name,\n"
        "                        path: file.fsName\n"
        "                    };\n"
        "                }\n"
        "            }\n"
        "        };\n"
        "        walkComp(target);\n"
        "        var footage = [];\n"
        "        for (var key in footageById) {\n"
        "            if (footageById.hasOwnProperty(key)) { footage.push(footageById[key]); }\n"
        "        }\n"
        "        return JSON.stringify({\n"
        "            result: true,\n"
        "            composition: { id: String(target.id), name: target.name },\n"
        "            footage: footage\n"
        "        });\n"
        % comp_id
    )


def build_add_to_render_queue(output_path, template_name, comp_id=None):
    """Add a composition to the render queue with full validation.

    When ``comp_id`` is omitted the active composition is queued (legacy
    behaviour); the render dialog passes an explicit id so the queued
    composition is exactly the one whose dependencies were collected.
    The queue item is only kept when the template applies and the output
    file is set; any failure removes the partially created item again and
    reports the reason.  On success the response includes the effective
    frame range, fps, and the queued composition identity.
    """
    path = _validate_path(output_path)
    if not isinstance(template_name, str) or not template_name.strip():
        raise ValueError("empty output module template name")
    if comp_id is None:
        comp_lookup = (
            "        var comp = (app.project && app.project.activeItem) ? app.project.activeItem : null;\n"
            "        if (!comp || !(comp instanceof CompItem)) {\n"
            '            return JSON.stringify({ result: false, details: "No active composition found." });\n'
            "        }\n"
        )
    else:
        comp_id = _as_int(comp_id, "composition id")
        if comp_id <= 0:
            raise ValueError("invalid composition id: %r" % (comp_id,))
        comp_lookup = (
            "        if (!app.project) {\n"
            '            return JSON.stringify({ result: false, details: "No open project." });\n'
            "        }\n"
            "        var comp = app.project.itemByID(%d);\n"
            "        if (!comp || !(comp instanceof CompItem)) {\n"
            '            return JSON.stringify({ result: false, details: "The selected composition no longer exists." });\n'
            "        }\n"
            % comp_id
        )
    return _wrap(
        comp_lookup
        + "        try { if (app.activeViewer) { app.activeViewer.setActive(); } } catch (e) {}\n"
        "        var renderQueueItem = app.project.renderQueue.items.add(comp);\n"
        "        var cleanup = function (details) {\n"
        "            try { renderQueueItem.remove(); } catch (e) {}\n"
        "            return JSON.stringify({ result: false, details: details });\n"
        "        };\n"
        "        var outputModule = renderQueueItem.outputModule(1);\n"
        "        try { outputModule.applyTemplate(%s); }\n"
        '        catch (e) { return cleanup("output module template could not be applied: " + e.toString()); }\n'
        "        try { outputModule.file = new File(%s); }\n"
        '        catch (e) { return cleanup("output file could not be set: " + e.toString()); }\n'
        "        if (!outputModule.file) {\n"
        '            return cleanup("output file was not set on the render queue item");\n'
        "        }\n"
        "        var fps = comp.frameRate;\n"
        "        var frameDuration = comp.frameDuration;\n"
        "        var displayStartFrame = Math.round(comp.displayStartTime / frameDuration);\n"
        "        var startFrame = Math.round(renderQueueItem.timeSpanStart / frameDuration) + displayStartFrame;\n"
        "        var endFrame = Math.round((renderQueueItem.timeSpanStart + renderQueueItem.timeSpanDuration) / frameDuration - 1) + displayStartFrame;\n"
        "        return JSON.stringify({\n"
        "            result: true,\n"
        "            queueItemId: renderQueueItem.id,\n"
        "            compId: String(comp.id),\n"
        "            compName: comp.name,\n"
        "            startFrame: startFrame,\n"
        "            endFrame: endFrame,\n"
        "            fps: fps\n"
        "        });\n"
        % (js_string(template_name), js_string(path))
    )


def build_render_with_template(template_name):
    """Queue the active comp with ``template_name`` and start rendering.

    The queue item is removed again when the template does not exist.
    NOTE: ``renderQueue.render()`` blocks until rendering finishes, so the
    caller must use a long response timeout, not the short command one.
    """
    if not isinstance(template_name, str) or not template_name.strip():
        raise ValueError("empty render template name")
    return _wrap(
        "        var comp = (app.project && app.project.activeItem) ? app.project.activeItem : null;\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, details: "No active composition found." });\n'
        "        }\n"
        "        var renderQueueItem = app.project.renderQueue.items.add(comp);\n"
        "        var outputModule = renderQueueItem.outputModule(1);\n"
        "        var templates = outputModule.templates;\n"
        "        var templateFound = false;\n"
        "        for (var i = 0; i < templates.length; i++) {\n"
        "            if (templates[i] === %s) {\n"
        "                outputModule.template = templates[i];\n"
        "                templateFound = true;\n"
        "                break;\n"
        "            }\n"
        "        }\n"
        "        if (!templateFound) {\n"
        "            try { renderQueueItem.remove(); } catch (e) {}\n"
        '            return JSON.stringify({ result: false, details: "Template not found: " + %s });\n'
        "        }\n"
        "        app.project.renderQueue.render();\n"
        "        return JSON.stringify({ result: true, template: %s });\n"
        % (js_string(template_name), js_string(template_name), js_string(template_name))
    )


# ---------------------------------------------------------------------------
# Footage-tracker data collection (JSON variants of the delimiter format)
# ---------------------------------------------------------------------------

_FOOTAGE_FRAME_LOGIC = """
                    var frameMatch = null;
                    try { frameMatch = item.mainSource.file.name.match(/[._](\\d{4,6})\\.[^.]+$/); } catch (e) {}
                    if (frameMatch) {
                        record.startFrame = parseInt(frameMatch[1], 10);
                        if (record.duration !== null && record.fps !== null) {
                            var frameCount = Math.round(record.duration * record.fps);
                            record.endFrame = record.startFrame + frameCount - 1;
                        }
                    }
"""


def build_collect_footage_records():
    """Collect file-backed footage metadata as a JSON array.

    Fields mirror the old ``id|||name|||path|||fps|||duration|||start|||end``
    archive format, including the frame-number inference from filenames.
    """
    return _wrap(
        "        var records = [];\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var item = null;\n"
        "            try { item = app.project.item(i); } catch (e) { continue; }\n"
        "            if (!item || !(item instanceof FootageItem)) { continue; }\n"
        "            if (!(item.mainSource instanceof FileSource)) { continue; }\n"
        "            if (!item.file || !item.file.fsName) { continue; }\n"
        "            var record = {\n"
        "                footageId: String(item.id),\n"
        "                name: item.name,\n"
        "                path: item.mainSource.file.fsName,\n"
        "                fps: null, duration: null, startFrame: null, endFrame: null\n"
        "            };\n"
        "            try {\n"
        "                var conformRate = item.mainSource.conformFrameRate;\n"
        "                record.fps = (conformRate > 0 ? conformRate : item.mainSource.nativeFrameRate);\n"
        "            } catch (e) {}\n"
        "            try { record.duration = item.duration; } catch (e) {}\n"
        + _FOOTAGE_FRAME_LOGIC
        + "            records.push(record);\n"
        "        }\n"
        "        return JSON.stringify(records);\n"
    )


def build_collect_tracker_footage():
    """Footage records for the tracker tree (adds width/height)."""
    return _wrap(
        "        var records = [];\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var item = null;\n"
        "            try { item = app.project.item(i); } catch (e) { continue; }\n"
        "            if (!item || !(item instanceof FootageItem)) { continue; }\n"
        "            if (!(item.mainSource instanceof FileSource)) { continue; }\n"
        "            if (!item.file || !item.file.fsName) { continue; }\n"
        "            var record = {\n"
        "                footageId: String(item.id),\n"
        "                name: item.name,\n"
        "                path: item.mainSource.file.fsName,\n"
        "                width: null, height: null,\n"
        "                fps: null, duration: null, startFrame: null, endFrame: null\n"
        "            };\n"
        "            try {\n"
        "                var conformRate = item.mainSource.conformFrameRate;\n"
        "                var rate = (conformRate > 0 ? conformRate : item.mainSource.nativeFrameRate);\n"
        "                record.fps = rate.toString();\n"
        "            } catch (e) {}\n"
        "            try { record.duration = item.duration.toString(); } catch (e) {}\n"
        "            try { record.width = item.width.toString(); } catch (e) {}\n"
        "            try { record.height = item.height.toString(); } catch (e) {}\n"
        "            if (record.fps !== null && record.duration !== null) {\n"
        "                var fpsFloat = parseFloat(record.fps);\n"
        "                var durationFloat = parseFloat(record.duration);\n"
        "                var frameCount = Math.round(durationFloat * fpsFloat);\n"
        "                var fileName = item.mainSource.file.name;\n"
        "                var isVideoFile = /\\.(mp4|mov|avi|mkv|flv|wmv|webm|m4v|m4p|mpg|mpeg|mp2)$/i.test(fileName);\n"
        "                if (isVideoFile) {\n"
        "                    record.startFrame = 0;\n"
        "                    record.endFrame = frameCount - 1;\n"
        "                } else {\n"
        "                    var startFrameNum = 0;\n"
        "                    var frameMatch = fileName.match(/(\\d{4,6})\\.\\w+$/);\n"
        "                    if (frameMatch) { startFrameNum = parseInt(frameMatch[1], 10); }\n"
        "                    record.startFrame = startFrameNum;\n"
        "                    record.endFrame = startFrameNum + frameCount - 1;\n"
        "                }\n"
        "            }\n"
        "            records.push(record);\n"
        "        }\n"
        "        return JSON.stringify(records);\n"
    )


def build_collect_comp_records():
    """Composition records for the tracker tree as a JSON array."""
    return _wrap(
        "        var records = [];\n"
        "        var parentsById = {};\n"
        "        var layerVisits = 0;\n"
        "        for (var p = 1; p <= app.project.numItems; p++) {\n"
        "            var parent = app.project.item(p);\n"
        "            if (!(parent instanceof CompItem)) { continue; }\n"
        "            var seenSources = {};\n"
        "            for (var l = 1; l <= parent.numLayers; l++) {\n"
        "                layerVisits++;\n"
        "                var source = parent.layer(l).source;\n"
        "                if (!(source instanceof CompItem)) { continue; }\n"
        "                var key = String(source.id);\n"
        "                if (seenSources[key]) { continue; }\n"
        "                seenSources[key] = true;\n"
        "                if (!parentsById[key]) { parentsById[key] = []; }\n"
        "                parentsById[key].push(parent.name);\n"
        "            }\n"
        "        }\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var item = null;\n"
        "            try { item = app.project.item(i); } catch (e) { continue; }\n"
        "            if (!item || !(item instanceof CompItem)) { continue; }\n"
        "            var parentComps = parentsById[String(item.id)] || [];\n"
        "            records.push({\n"
        "                compId: String(item.id),\n"
        "                name: item.name,\n"
        "                width: item.width,\n"
        "                height: item.height,\n"
        "                pixelAspect: item.pixelAspect,\n"
        "                duration: item.duration.toString(),\n"
        "                frameRate: item.frameRate.toString(),\n"
        "                frameDuration: item.frameDuration.toString(),\n"
        "                inPoint: item.displayStartTime.toString(),\n"
        "                outPoint: (item.displayStartTime + item.duration).toString(),\n"
        "                displayStartFrame: item.displayStartFrame,\n"
        "                workAreaStart: item.workAreaStart.toString(),\n"
        "                workAreaDuration: item.workAreaDuration.toString(),\n"
        "                startFrame: Math.round(item.displayStartTime / item.frameDuration),\n"
        "                endFrame: Math.round((item.displayStartTime + item.duration) / item.frameDuration - 1),\n"
        "                isPrecomp: parentComps.length > 0,\n"
        "                parentComps: parentComps.join(','),\n"
        "                numLayers: item.numLayers\n"
        "            });\n"
        "        }\n"
        "        return JSON.stringify(records);\n"
    )


def _tracker_identity_body():
    return (
        '        var path = app.project && app.project.file ? app.project.file.fsName : "";\n'
        '        var state = $.global.__helixTrackerScene;\n'
        '        var sameProject = false;\n'
        '        try { sameProject = !!state && state.project === app.project; } catch (invalidPreviousProject) {}\n'
        '        if (!sameProject || state.path !== path) {\n'
        '            state = {project: app.project, path: path, token: String(new Date().getTime()) + ":" + String(Math.random())};\n'
        '            $.global.__helixTrackerScene = state;\n'
        '        }\n'
        '        var scene = {path: path, token: state.token};\n'
    )


def build_get_tracker_identity():
    """Small scene/session probe; does not enumerate items or touch the filesystem."""
    return _wrap(_tracker_identity_body() + '        return JSON.stringify({result: true, scene: scene});\n')


def build_tracker_snapshot():
    """One round trip, one project enumeration and one visit per composition layer."""
    # The individual protocol queries remain available to existing consumers.
    # Share a captured item array instead of calling app.project.item repeatedly.
    footage = build_collect_tracker_footage().replace('app.project.item(i)', 'hxItems[i - 1]')
    comps = build_collect_comp_records().replace('app.project.item(i)', 'hxItems[i - 1]')
    comps = comps.replace('app.project.item(p)', 'hxItems[p - 1]')
    comps = comps.replace('return JSON.stringify(records);',
                          'return JSON.stringify({records: records, layerVisits: layerVisits});')
    return _wrap(
        _tracker_identity_body()
        + '        var started = new Date().getTime();\n'
        + '        var hxItems = [];\n'
        + '        for (var n = 1; n <= app.project.numItems; n++) { hxItems.push(app.project.item(n)); }\n'
        + '        var footage = JSON.parse(' + footage.rstrip(';') + ');\n'
        + '        var comps = JSON.parse(' + comps.rstrip(';') + ');\n'
        + '        if (!(footage instanceof Array)) { throw new Error(footage.details || "Footage snapshot failed"); }\n'
        + '        if (!(comps.records instanceof Array)) { throw new Error(comps.details || "Comp snapshot failed"); }\n'
        + '        return JSON.stringify({result: true, scene: scene, footage: footage, comps: comps.records, xmp: app.project.xmpPacket || "",\n'
        + '            itemCount: hxItems.length, layerVisits: comps.layerVisits, aeMilliseconds: new Date().getTime() - started});\n'
    )


def parse_tracker_identity(response):
    data, error = parse_json_response(response)
    if error:
        return None, error
    scene = data.get('scene')
    if (data.get('result') is not True or not isinstance(scene, dict)
            or not isinstance(scene.get('path'), str)
            or not isinstance(scene.get('token'), str) or not scene['token']):
        return None, 'Malformed scene identity'
    return scene, None


def parse_tracker_snapshot(response):
    data, error = parse_json_response(response)
    if error:
        return None, error
    if data.get('result') is not True:
        return None, data.get('details') or 'AE snapshot failed'
    scene, error = parse_tracker_identity(json.dumps(data))
    if error:
        return None, error
    footage, error = parse_footage_records(json.dumps(data.get('footage')))
    if error:
        return None, error
    comps, error = parse_comp_records(json.dumps(data.get('comps')))
    if error:
        return None, error
    for comp in comps:
        comp['displayStartTime'] = comp.get('inPoint', '0')
        comp['category'] = 'Pre-comps' if comp['isPrecomp'] else 'Main Comps'
    data.update(footage=footage, comps=comps)
    return data, None


def _coerce_record_fields(record, fields, none_value):
    coerced = {}
    for field in fields:
        value = record.get(field)
        if value is None:
            value = none_value
        elif not isinstance(value, bool) and not isinstance(value, str):
            value = str(value)
        coerced[field] = value
    return coerced


_FOOTAGE_FIELDS = (
    "footageId",
    "name",
    "path",
    "width",
    "height",
    "fps",
    "duration",
    "startFrame",
    "endFrame",
)

_COMP_FIELDS = (
    "compId",
    "name",
    "width",
    "height",
    "pixelAspect",
    "duration",
    "frameRate",
    "frameDuration",
    "inPoint",
    "outPoint",
    "displayStartFrame",
    "workAreaStart",
    "workAreaDuration",
    "startFrame",
    "endFrame",
    "parentComps",
    "numLayers",
)


def parse_footage_records(result):
    """Parse tracker footage records.  ``(records, error)``; str-coerced."""
    data, error = parse_json_array(result)
    if error:
        return [], error
    records = []
    for entry in data:
        if not isinstance(entry, dict):
            return [], "malformed footage record"
        record = _coerce_record_fields(entry, _FOOTAGE_FIELDS, "N/A")
        record["path"] = record["path"].replace("\\", "/")
        records.append(record)
    return records, None


def parse_comp_records(result):
    """Parse tracker composition records.  ``(records, error)``."""
    data, error = parse_json_array(result)
    if error:
        return [], error
    records = []
    for entry in data:
        if not isinstance(entry, dict):
            return [], "malformed comp record"
        record = _coerce_record_fields(entry, _COMP_FIELDS, "")
        record["isPrecomp"] = bool(entry.get("isPrecomp", False))
        records.append(record)
    return records, None


def parse_comp_dependency_result(result):
    """Parse the comp dependency walk.  ``(parsed, error)``.

    ``parsed`` contains ``composition`` (id/name) and ``footage`` records
    (id/name/path).  A missing project, missing composition, non-comp item,
    malformed payload, or empty response is an error; an empty footage
    list is a valid result.
    """
    text, error = decode_response(result)
    if error:
        return None, error
    try:
        data = json.loads(text)
    except ValueError:
        return None, "invalid JSON response: %r" % text[:200]
    if not isinstance(data, dict):
        return None, "malformed response (not an object)"
    if data.get("result") is not True:
        details = data.get("details") or data.get("reason") or "dependency scan failed"
        return None, "After Effects error: %s" % details

    composition = data.get("composition")
    if not isinstance(composition, dict):
        return None, "malformed response (missing composition)"
    comp_id = composition.get("id")
    comp_name = composition.get("name")
    if comp_id is None or not str(comp_id).strip():
        return None, "malformed response (missing composition id)"
    if not isinstance(comp_name, str):
        return None, "malformed response (invalid composition name)"

    footage = data.get("footage")
    if not isinstance(footage, list):
        return None, "malformed response (missing footage list)"
    records = []
    for entry in footage:
        if not isinstance(entry, dict):
            return None, "malformed footage record"
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            return None, "malformed footage record (missing path)"
        records.append({
            "id": str(entry.get("id", "")),
            "name": str(entry.get("name", "")),
            "path": path.replace("\\", "/"),
        })
    return {
        "composition": {"id": str(comp_id), "name": comp_name},
        "footage": records,
    }, None


# ---------------------------------------------------------------------------
# Structured footage import (footage tracker import dialog)
# ---------------------------------------------------------------------------


def build_import_footage_item(filepath, shot, identifier, aov, fps=None, sequence=True):
    """Import footage into the Prism folder structure with a JSON ack.

    ``filepath`` is imported (as a sequence when ``sequence`` is true),
    placed under ``Prism imports/<shot>/<identifier>``, renamed to the
    AOV, and optionally conformed to ``fps``.  All strings are embedded
    via ``js_string`` so apostrophes/Unicode in names and paths survive.
    """
    path = _validate_path(filepath)
    for name, value in (("shot", shot), ("identifier", identifier), ("aov", aov)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("empty %s" % name)
    fps_literal = "null"
    if fps is not None:
        rate = _as_number(fps, "fps")
        if rate <= 0:
            raise ValueError("fps must be positive")
        fps_literal = repr(rate)
    return _wrap(
        "        var file = new File(%s);\n"
        "        if (!file.exists) {\n"
        '            return JSON.stringify({ result: false, details: "File not found: " + file.fsName });\n'
        "        }\n"
        "        var findFolder = function (parent, name) {\n"
        "            for (var i = 1; i <= parent.numItems; i++) {\n"
        "                var child = parent.item(i);\n"
        "                if (child instanceof FolderItem && child.name === name) { return child; }\n"
        "            }\n"
        "            return parent.items.addFolder(name);\n"
        "        };\n"
        "        var prismFolder = findFolder(app.project.rootFolder, 'Prism imports');\n"
        "        var shotFolder = findFolder(prismFolder, %s);\n"
        "        var identifierFolder = findFolder(shotFolder, %s);\n"
        "        var importOptions = new ImportOptions(file);\n"
        "        importOptions.sequence = %s;\n"
        "        var footage = app.project.importFile(importOptions);\n"
        "        if (!footage) {\n"
        '            return JSON.stringify({ result: false, details: "import returned no item" });\n'
        "        }\n"
        "        if (%s !== null && footage.mainSource) {\n"
        "            try { footage.mainSource.conformFrameRate = %s; } catch (e) {}\n"
        "        }\n"
        "        footage.parentFolder = identifierFolder;\n"
        "        footage.name = %s;\n"
        "        return JSON.stringify({ result: true, itemId: footage.id });\n"
        % (
            js_string(path),
            js_string(shot),
            js_string(identifier),
            js_bool(sequence),
            fps_literal,
            fps_literal,
            js_string(aov),
        )
    )


# ---------------------------------------------------------------------------
# Footage/comp update builders (tracker operations)
# ---------------------------------------------------------------------------


def _as_id(value, name):
    if isinstance(value, bool):
        raise ValueError("invalid %s: %r" % (name, value))
    text = str(value).strip()
    if not text or not re.match(r"^\d+$", text):
        raise ValueError("invalid %s: %r" % (name, value))
    return text


def build_get_footage_properties(footage_id):
    """Query isStill + conformFrameRate of a footage item by AE item id."""
    item_id = _as_id(footage_id, "footage id")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item || !(item instanceof FootageItem) || !item.mainSource) {\n"
        '            return JSON.stringify({ result: false, details: "Footage item not found" });\n'
        "        }\n"
        "        var isStill = false;\n"
        "        try { isStill = item.mainSource.isStill; } catch (e) {}\n"
        "        var conformRate = null;\n"
        "        try { conformRate = item.mainSource.conformFrameRate; } catch (e) {}\n"
        "        return JSON.stringify({ result: true, isStill: !!isStill, conformFrameRate: conformRate });\n"
        % item_id
    )


def build_replace_footage_by_id(footage_id, filepath, sequence, conform_fps=None):
    """Replace a footage item's source by AE item id with a JSON ack.

    Keeps the original conform frame rate (or applies ``conform_fps``),
    disables alphabetic ordering for sequences, and fails explicitly
    when After Effects cannot see the file.
    """
    item_id = _as_id(footage_id, "footage id")
    path = _validate_path(filepath)
    fps_literal = "null"
    if conform_fps is not None:
        rate = _as_number(conform_fps, "fps")
        if rate <= 0:
            raise ValueError("fps must be positive")
        fps_literal = repr(rate)
    replace_call = (
        "item.replaceWithSequence(file, false);" if sequence else "item.replace(file);"
    )
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item || !(item instanceof FootageItem)) {\n"
        '            return JSON.stringify({ result: false, details: "Footage item not found" });\n'
        "        }\n"
        "        var file = new File(%s);\n"
        "        if (!file.exists) {\n"
        '            return JSON.stringify({ result: false, details: "File not found by After Effects: " + file.fsName });\n'
        "        }\n"
        "        var previousRate = null;\n"
        "        try { previousRate = item.mainSource.conformFrameRate; } catch (e) {}\n"
        "        var interpretation = {}, warnings = [];\n"
        '        var properties = ["alphaMode", "premulColor", "invertAlpha", "fieldSeparationType", "highQualityFieldSeparation", "removePulldown", "loop"];\n'
        "        for (var p = 0; p < properties.length; p++) {\n"
        "            try { interpretation[properties[p]] = item.mainSource[properties[p]]; } catch (e) {}\n"
        "        }\n"
        "        %s\n"
        "        %s\n"
        "        for (var p = 0; p < properties.length; p++) {\n"
        "            var key = properties[p];\n"
        "            if (typeof interpretation[key] === 'undefined') continue;\n"
        "            if (key === 'highQualityFieldSeparation' && typeof FieldSeparationType !== 'undefined' &&\n"
        "                    item.mainSource.fieldSeparationType === FieldSeparationType.OFF) continue;\n"
        "            try { item.mainSource[key] = interpretation[key]; }\n"
        '            catch (e) { warnings.push("Could not preserve " + key + ": " + e.toString()); }\n'
        "        }\n"
        "        var targetRate = (%s !== null) ? %s : previousRate;\n"
        "        if (targetRate !== null && targetRate >= 0 && !item.mainSource.isStill) {\n"
        "            try { item.mainSource.conformFrameRate = targetRate; }\n"
        '            catch (e) { warnings.push("Could not preserve conform frame rate: " + e.toString()); }\n'
        "        }\n"
        "        return JSON.stringify({ result: true, fileName: item.name, warnings: warnings });\n"
        % (
            item_id,
            js_string(path),
            replace_call,
            "try { item.mainSource.alphabeticOrder = false; } catch (e) {}" if sequence else "",
            fps_literal,
            fps_literal,
        )
    )


def build_set_footage_fps(footage_id, fps):
    item_id = _as_id(footage_id, "footage id")
    rate = _as_number(fps, "fps")
    if rate <= 0:
        raise ValueError("fps must be positive")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item || !(item instanceof FootageItem) || !item.mainSource) {\n"
        '            return JSON.stringify({ result: false, details: "Footage item not found" });\n'
        "        }\n"
        "        item.mainSource.conformFrameRate = %s;\n"
        "        return JSON.stringify({ result: true, conformFrameRate: item.mainSource.conformFrameRate });\n"
        % (item_id, repr(rate))
    )


def build_set_comp_fps(comp_id, fps):
    """Set comp frame rate while preserving the current frame count/range."""
    comp_id = _as_id(comp_id, "comp id")
    rate = _as_number(fps, "fps")
    if rate <= 0:
        raise ValueError("fps must be positive")
    return _wrap(
        "        var comp = null;\n"
        "        try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "comp_not_found" });\n'
        "        }\n"
        "        app.beginUndoGroup('HelixAE: Set comp fps');\n"
        "        try {\n"
        "            var startFrame = Math.floor(comp.displayStartTime * comp.frameRate);\n"
        "            var frameCount = Math.floor(comp.duration * comp.frameRate);\n"
        "            var epsilon = 0.000001;\n"
        "            comp.frameRate = %s;\n"
        "            comp.displayStartTime = startFrame / %s + epsilon;\n"
        "            comp.duration = frameCount / %s + epsilon;\n"
        "            app.endUndoGroup();\n"
        "        } catch (e) {\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString() });\n"
        "        }\n"
        "        return JSON.stringify({ result: true, frameRate: comp.frameRate });\n"
        % (comp_id, repr(rate), repr(rate), repr(rate))
    )


def build_set_comp_frame_range(comp_id, start_frame, end_frame, comp_fps):
    comp_id = _as_id(comp_id, "comp id")
    start = _as_int(start_frame, "start frame")
    end = _as_int(end_frame, "end frame")
    rate = _as_number(comp_fps, "comp fps")
    if rate <= 0:
        raise ValueError("fps must be positive")
    if end < start:
        raise ValueError("end frame before start frame")
    display_start = start / rate
    duration = (end + 1) / rate - display_start
    return _wrap(
        "        var comp = null;\n"
        "        try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, details: "Composition not found" });\n'
        "        }\n"
        "        comp.displayStartTime = %s;\n"
        "        comp.duration = %s;\n"
        "        return JSON.stringify({ result: true });\n"
        % (comp_id, repr(display_start), repr(duration))
    )


def build_set_comp_resolution(comp_id, width, height):
    comp_id = _as_id(comp_id, "comp id")
    w = _as_int(width, "width")
    h = _as_int(height, "height")
    if w <= 0 or h <= 0:
        raise ValueError("resolution must be positive")
    return _wrap(
        "        var comp = null;\n"
        "        try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, details: "Composition not found" });\n'
        "        }\n"
        "        comp.width = %d;\n"
        "        comp.height = %d;\n"
        "        return JSON.stringify({ result: true, width: comp.width, height: comp.height });\n"
        % (comp_id, w, h)
    )


def build_reveal_item_in_project(item_id):
    """Select an item in the AE Project panel and reveal it."""
    item_id = _as_id(item_id, "item id")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            try { app.project.item(i).selected = false; } catch (e) {}\n"
        "        }\n"
        "        item.selected = true;\n"
        "        try { app.executeCommand(2523); } catch (e) {}\n"
        "        return JSON.stringify({ result: true, itemName: item.name });\n"
        % item_id
    )


def build_find_comps_using_item(item_id):
    """List every composition that uses the given project item."""
    item_id = _as_id(item_id, "item id")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        var comps = [];\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var comp = app.project.item(i);\n"
        "            if (!(comp instanceof CompItem)) { continue; }\n"
        "            for (var j = 1; j <= comp.numLayers; j++) {\n"
        "                var layer = comp.layer(j);\n"
        "                if (layer && layer.source && layer.source.id == item.id) {\n"
        "                    comps.push({ id: comp.id, name: comp.name });\n"
        "                    break;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, comps: comps });\n"
        % item_id
    )


def build_open_comp_in_viewer(comp_id):
    """Open a composition in the AE comp viewer."""
    comp_id = _as_id(comp_id, "comp id")
    return _wrap(
        "        var comp = null;\n"
        "        try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        if (!comp) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        if (!(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "not_a_comp" });\n'
        "        }\n"
        "        comp.openInViewer();\n"
        "        return JSON.stringify({ result: true, compName: comp.name });\n"
        % comp_id
    )


def build_create_folder_structure(parent_folder_id, folder_path):
    """Create a '/'-separated folder structure under a parent folder (0 = project root)."""
    parent_id = 0 if parent_folder_id in (None, "", 0) else _as_id(parent_folder_id, "parent folder id")
    if not isinstance(folder_path, str) or not folder_path.strip():
        raise ValueError("folder path must be a non-empty string")
    segments = [seg.strip() for seg in folder_path.split("/") if seg.strip()]
    if not segments:
        raise ValueError("folder path contains no folder names")
    return _wrap(
        "        var parentFolder = %s;\n"
        "        if (parentFolder === null) {\n"
        "            try { parentFolder = app.project.itemByID(%s); } catch (e) { parentFolder = null; }\n"
        "        }\n"
        "        if (!parentFolder) {\n"
        '            return JSON.stringify({ result: false, reason: "parent_not_found" });\n'
        "        }\n"
        "        var segments = %s;\n"
        "        var current = parentFolder;\n"
        "        app.beginUndoGroup('HelixAE: Create folders');\n"
        "        try {\n"
        "            for (var i = 0; i < segments.length; i++) {\n"
        "                var name = segments[i];\n"
        "                var found = null;\n"
        "                for (var j = 1; j <= current.numItems; j++) {\n"
        "                    var child = current.item(j);\n"
        "                    if (child instanceof FolderItem && child.name === name) { found = child; break; }\n"
        "                }\n"
        "                if (!found) { found = current.items.addFolder(name); }\n"
        "                current = found;\n"
        "            }\n"
        "            app.endUndoGroup();\n"
        "        } catch (e) {\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString() });\n"
        "        }\n"
        "        return JSON.stringify({ result: true, folderId: current.id, folderName: current.name });\n"
        % (
            "app.project.rootFolder" if parent_id == 0 else "null",
            parent_id,
            json.dumps(segments),
        )
    )


def build_rename_move_item(item_id, new_name, target_folder_id, expected_type):
    """Rename a project item and move it into a target folder inside one undo group."""
    item_id = _as_id(item_id, "item id")
    target_id = _as_id(target_folder_id, "target folder id")
    if not isinstance(new_name, str) or not new_name.strip():
        raise ValueError("new name must be a non-empty string")
    if expected_type not in ("footage", "comp"):
        raise ValueError("expected_type must be 'footage' or 'comp'")
    return _wrap(
        "        var item = null, targetFolder = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        try { targetFolder = app.project.itemByID(%s); } catch (e) { targetFolder = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        if (!(item instanceof %s)) {\n"
        '            return JSON.stringify({ result: false, reason: "wrong_type" });\n'
        "        }\n"
        "        if (!targetFolder || !(targetFolder instanceof FolderItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "target_folder_not_found" });\n'
        "        }\n"
        "        app.beginUndoGroup('HelixAE: Rename/Move');\n"
        "        try {\n"
        "            item.name = %s;\n"
        "            item.parentFolder = targetFolder;\n"
        "            app.endUndoGroup();\n"
        "        } catch (e) {\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString() });\n"
        "        }\n"
        "        return JSON.stringify({ result: true, newId: item.id, newName: item.name });\n"
        % (
            item_id,
            target_id,
            "FootageItem" if expected_type == "footage" else "CompItem",
            js_string(new_name.strip()),
        )
    )


def build_delete_project_item(item_id, expected_type):
    """Delete a footage/comp project item inside one undo group."""
    item_id = _as_id(item_id, "item id")
    if expected_type not in ("footage", "comp"):
        raise ValueError("expected_type must be 'footage' or 'comp'")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        if (!(item instanceof %s)) {\n"
        '            return JSON.stringify({ result: false, reason: "wrong_type" });\n'
        "        }\n"
        "        var deletedName = item.name;\n"
        "        app.beginUndoGroup('HelixAE: Delete item');\n"
        "        try {\n"
        "            item.remove();\n"
        "            app.endUndoGroup();\n"
        "        } catch (e) {\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString() });\n"
        "        }\n"
        "        return JSON.stringify({ result: true, deletedName: deletedName });\n"
        % (item_id, "FootageItem" if expected_type == "footage" else "CompItem")
    )


def build_remove_empty_folders():
    """Remove every empty folder from the project inside one undo group."""
    return _wrap(
        "        var deletedCount = 0;\n"
        "        app.beginUndoGroup('HelixAE: Remove empty folders');\n"
        "        try {\n"
        "            var maxPasses = 100;\n"
        "            for (var pass = 0; pass < maxPasses; pass++) {\n"
        "                var deletedThisPass = 0;\n"
        "                function processFolder(folder) {\n"
        "                    for (var i = folder.numItems; i >= 1; i--) {\n"
        "                        var child = folder.item(i);\n"
        "                        if (child instanceof FolderItem) { processFolder(child); }\n"
        "                    }\n"
        "                    if (folder !== app.project.rootFolder && folder.numItems === 0) {\n"
        "                        folder.remove();\n"
        "                        deletedThisPass++;\n"
        "                    }\n"
        "                }\n"
        "                processFolder(app.project.rootFolder);\n"
        "                if (deletedThisPass === 0) { break; }\n"
        "                deletedCount += deletedThisPass;\n"
        "            }\n"
        "            app.endUndoGroup();\n"
        "        } catch (e) {\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString() });\n"
        "        }\n"
        "        return JSON.stringify({ result: true, deletedCount: deletedCount });\n"
    )


def _as_id_list(value, name):
    if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
        raise TypeError("%s must be a list of ids" % name)
    ids = [int(_as_id(entry, name)) for entry in value]
    return json.dumps(ids)


def build_add_footage_to_comp(comp_id, item_ids):
    """Add project items as layers to a comp (comp_id None/0 = active comp)."""
    use_active = comp_id in (None, "", 0)
    target_id = 0 if use_active else _as_id(comp_id, "comp id")
    ids_json = _as_id_list(item_ids, "item ids")
    if ids_json == "[]":
        raise ValueError("item ids must not be empty")
    return _wrap(
        "        var comp = %s;\n"
        "        if (comp === null) {\n"
        "            try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        }\n"
        "        if (comp === null || comp === undefined) {\n"
        '            return JSON.stringify({ result: false, reason: "no_active_comp" });\n'
        "        }\n"
        "        if (!(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "not_a_comp" });\n'
        "        }\n"
        "        var ids = %s;\n"
        "        var addedCount = 0, failedItems = [];\n"
        "        for (var i = 0; i < ids.length; i++) {\n"
        "            var footageItem = null;\n"
        "            try { footageItem = app.project.itemByID(ids[i]); } catch (e) { footageItem = null; }\n"
        "            if (!footageItem) {\n"
        '                failedItems.push(ids[i] + ": footage not found");\n'
        "                continue;\n"
        "            }\n"
        "            try {\n"
        "                var newLayer = comp.layers.add(footageItem);\n"
        "                newLayer.label = footageItem.label;\n"
        "                if (footageItem.parentFolder && footageItem.parentFolder.name) {\n"
        "                    newLayer.comment = footageItem.parentFolder.name;\n"
        "                }\n"
        "                addedCount++;\n"
        "            } catch (e) {\n"
        "                failedItems.push(ids[i] + ': ' + e.toString());\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, addedCount: addedCount, failedItems: failedItems });\n"
        % (
            "app.project.activeItem" if use_active else "null",
            target_id,
            ids_json,
        )
    )


def build_import_to_shot_folder(
    file_path,
    root_folder,
    shot_name,
    footage_name,
    sequence=True,
    task_folder=None,
    label_color=None,
    comment=None,
):
    """Import a file into root_folder/shot_name[/task_folder] with duplicate-count naming."""
    _validate_path(file_path)
    for label, value in (("root folder", root_folder), ("shot name", shot_name), ("footage name", footage_name)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s must be a non-empty string" % label)
    if task_folder is not None and (not isinstance(task_folder, str) or not task_folder.strip()):
        raise ValueError("task folder must be a non-empty string or None")
    if label_color is not None:
        label_color = _as_int(label_color, "label color")
        if not 0 <= label_color <= 16:
            raise ValueError("label color must be 0-16")
    if comment is not None and not isinstance(comment, str):
        raise TypeError("comment must be a string or None")
    task_segment = (
        json.dumps([seg.strip() for seg in task_folder.split("/") if seg.strip()])
        if task_folder
        else "null"
    )
    return _wrap(
        "        var importFile = new File(%s);\n"
        "        if (!importFile.exists) {\n"
        '            return JSON.stringify({ result: false, reason: "file_not_found" });\n'
        "        }\n"
        "        function findOrCreate(parent, name) {\n"
        "            for (var i = 1; i <= parent.numItems; i++) {\n"
        "                var child = parent.item(i);\n"
        "                if (child instanceof FolderItem && child.name === name) { return child; }\n"
        "            }\n"
        "            var folder = parent.items.addFolder(name); created.push(folder); return folder;\n"
        "        }\n"
        "        app.beginUndoGroup('HelixAE: Import');\n"
        "        var created = [], footage = null;\n"
        "        try {\n"
        "            var root = findOrCreate(app.project.rootFolder, %s);\n"
        "            var shot = findOrCreate(root, %s);\n"
        "            var target = shot;\n"
        "            var taskSegments = %s;\n"
        "            if (taskSegments) {\n"
        "                for (var i = 0; i < taskSegments.length; i++) { target = findOrCreate(target, taskSegments[i]); }\n"
        "            }\n"
        "            var baseName = %s;\n"
        "            var dupCount = 0;\n"
        "            for (var i = 1; i <= target.numItems; i++) {\n"
        "                var child = target.item(i);\n"
        "                if (child instanceof FootageItem &&\n"
        "                    (child.name === baseName || child.name.indexOf(baseName + ' (') === 0)) {\n"
        "                    dupCount++;\n"
        "                }\n"
        "            }\n"
        "            var finalName = dupCount > 0 ? baseName + ' (' + dupCount + ')' : baseName;\n"
        "            var importOptions = new ImportOptions(importFile);\n"
        "            if (!importOptions.canImportAs(ImportAsType.FOOTAGE)) {\n"
        "                throw new Error('cannot_import');\n"
        "            }\n"
        "            importOptions.importAs = ImportAsType.FOOTAGE;\n"
        "            importOptions.sequence = %s;\n"
        "            footage = app.project.importFile(importOptions);\n"
        "            footage.parentFolder = target;\n"
        "            footage.name = finalName;\n"
        "            if (%s) { footage.label = %s; }\n"
        "            if (%s) { footage.comment = %s; }\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: true, footageId: footage.id, footageName: footage.name });\n"
        "        } catch (e) {\n"
        "            var cleanupErrors = [];\n"
        "            if (footage) { try { footage.remove(); } catch (cleanup) { cleanupErrors.push(cleanup.toString()); } }\n"
        "            for (var c = created.length - 1; c >= 0; c--) { try { if (created[c].numItems === 0) { created[c].remove(); } } catch (cleanup) { cleanupErrors.push(cleanup.toString()); } }\n"
        "            app.endUndoGroup();\n"
        "            return JSON.stringify({ result: false, details: e.toString(), cleanupErrors: cleanupErrors });\n"
        "        }\n"
        % (
            js_string(file_path.replace("\\", "/")),
            js_string(root_folder.strip()),
            js_string(shot_name.strip()),
            task_segment,
            js_string(footage_name.strip()),
            "true" if sequence else "false",
            "true" if label_color is not None else "false",
            label_color if label_color is not None else 0,
            "true" if comment else "false",
            js_string(comment) if comment else '""',
        )
    )


def build_set_item_properties(item_id, label=None, comment=None):
    """Set label and/or comment on a project item."""
    item_id = _as_id(item_id, "item id")
    if label is None and comment is None:
        raise ValueError("at least one of label or comment is required")
    if label is not None:
        label = _as_int(label, "label")
        if not 0 <= label <= 16:
            raise ValueError("label must be 0-16")
    if comment is not None and not isinstance(comment, str):
        raise TypeError("comment must be a string or None")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        if (%s) { item.label = %s; }\n"
        "        if (%s) { item.comment = %s; }\n"
        "        return JSON.stringify({ result: true });\n"
        % (
            item_id,
            "true" if label is not None else "false",
            label if label is not None else 0,
            "true" if comment is not None else "false",
            js_string(comment) if comment is not None else '""',
        )
    )


def build_get_item_label(item_id):
    """Read the label color of a project item."""
    item_id = _as_id(item_id, "item id")
    return _wrap(
        "        var item = null;\n"
        "        try { item = app.project.itemByID(%s); } catch (e) { item = null; }\n"
        "        if (!item) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        return JSON.stringify({ result: true, label: item.label });\n"
        % item_id
    )


def build_find_task_folder_label(task_name, root_folder="3D Renders"):
    """Find the first used label color under root_folder/<any shot>/<task_name>."""
    if not isinstance(task_name, str) or not task_name.strip():
        raise ValueError("task name must be a non-empty string")
    if not isinstance(root_folder, str) or not root_folder.strip():
        raise ValueError("root folder must be a non-empty string")
    return _wrap(
        "        var rootName = %s;\n"
        "        var taskName = %s;\n"
        "        var rootFolder = null;\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var it = app.project.item(i);\n"
        "            if (it instanceof FolderItem && it.name === rootName) { rootFolder = it; break; }\n"
        "        }\n"
        "        var foundLabel = 0;\n"
        "        if (rootFolder) {\n"
        "            outer:\n"
        "            for (var i = 1; i <= rootFolder.numItems; i++) {\n"
        "                var shotFolder = rootFolder.item(i);\n"
        "                if (!(shotFolder instanceof FolderItem)) { continue; }\n"
        "                for (var j = 1; j <= shotFolder.numItems; j++) {\n"
        "                    var taskFolder = shotFolder.item(j);\n"
        "                    if (taskFolder instanceof FolderItem && taskFolder.name === taskName) {\n"
        "                        for (var k = 1; k <= taskFolder.numItems; k++) {\n"
        "                            var item = taskFolder.item(k);\n"
        "                            if (item instanceof FootageItem && item.label > 0) {\n"
        "                                foundLabel = item.label;\n"
        "                                break outer;\n"
        "                            }\n"
        "                        }\n"
        "                        break;\n"
        "                    }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, label: foundLabel });\n"
        % (js_string(root_folder), js_string(task_name))
    )


def build_list_task_folder_footage(root_folder="3D Renders"):
    """List footage items grouped by task folder: {result, tasks: [{name, itemIds}]}."""
    if not isinstance(root_folder, str) or not root_folder.strip():
        raise ValueError("root folder must be a non-empty string")
    return _wrap(
        "        var rootName = %s;\n"
        "        var rootFolder = null;\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var it = app.project.item(i);\n"
        "            if (it instanceof FolderItem && it.name === rootName) { rootFolder = it; break; }\n"
        "        }\n"
        "        var tasks = [];\n"
        "        if (rootFolder) {\n"
        "            for (var i = 1; i <= rootFolder.numItems; i++) {\n"
        "                var shotFolder = rootFolder.item(i);\n"
        "                if (!(shotFolder instanceof FolderItem)) { continue; }\n"
        "                for (var j = 1; j <= shotFolder.numItems; j++) {\n"
        "                    var taskFolder = shotFolder.item(j);\n"
        "                    if (!(taskFolder instanceof FolderItem)) { continue; }\n"
        "                    var ids = [];\n"
        "                    for (var k = 1; k <= taskFolder.numItems; k++) {\n"
        "                        var item = taskFolder.item(k);\n"
        "                        if (item instanceof FootageItem) { ids.push(item.id); }\n"
        "                    }\n"
        "                    if (ids.length > 0) { tasks.push({ name: taskFolder.name, itemIds: ids }); }\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, tasks: tasks });\n"
        % js_string(root_folder)
    )


def build_set_item_labels(item_ids, label_color):
    """Set the same label color on many project items."""
    ids_json = _as_id_list(item_ids, "item ids")
    if ids_json == "[]":
        raise ValueError("item ids must not be empty")
    label_color = _as_int(label_color, "label color")
    if not 0 <= label_color <= 16:
        raise ValueError("label color must be 0-16")
    return _wrap(
        "        var ids = %s;\n"
        "        var updatedCount = 0;\n"
        "        for (var i = 0; i < ids.length; i++) {\n"
        "            var item = null;\n"
        "            try { item = app.project.itemByID(ids[i]); } catch (e) { item = null; }\n"
        "            if (item) { item.label = %d; updatedCount++; }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, updatedCount: updatedCount });\n"
        % (ids_json, label_color)
    )


def build_update_layers_from_source():
    """Match layer label/comment in all comps to their 3D Renders source footage."""
    return _wrap(
        "        var totalComps = 0, totalLayers = 0, updatedLayers = 0;\n"
        "        for (var i = 1; i <= app.project.numItems; i++) {\n"
        "            var comp = app.project.item(i);\n"
        "            if (!(comp instanceof CompItem)) { continue; }\n"
        "            totalComps++;\n"
        "            for (var j = 1; j <= comp.numLayers; j++) {\n"
        "                totalLayers++;\n"
        "                var layer = comp.layer(j);\n"
        "                var source = layer ? layer.source : null;\n"
        "                if (!(source instanceof FootageItem) || source.label <= 0) { continue; }\n"
        "                var isFrom3DRender = false;\n"
        "                var parentFolder = source.parentFolder;\n"
        "                while (parentFolder) {\n"
        "                    if (parentFolder.name === '3D Renders') { isFrom3DRender = true; break; }\n"
        "                    parentFolder = parentFolder.parentFolder;\n"
        "                }\n"
        "                if (!isFrom3DRender) { continue; }\n"
        "                layer.label = source.label;\n"
        "                if (source.parentFolder && source.parentFolder.name) {\n"
        "                    layer.comment = source.parentFolder.name;\n"
        "                }\n"
        "                updatedLayers++;\n"
        "            }\n"
        "        }\n"
        "        return JSON.stringify({ result: true, totalComps: totalComps, totalLayers: totalLayers, updatedLayers: updatedLayers });\n"
    )


def build_get_comp_info(comp_id):
    """Read detailed composition info as JSON."""
    comp_id = _as_id(comp_id, "comp id")
    return _wrap(
        "        var comp = null;\n"
        "        try { comp = app.project.itemByID(%s); } catch (e) { comp = null; }\n"
        "        if (!comp || !(comp instanceof CompItem)) {\n"
        '            return JSON.stringify({ result: false, reason: "comp_not_found" });\n'
        "        }\n"
        "        var usedLayers = 0;\n"
        "        for (var i = 1; i <= comp.numLayers; i++) {\n"
        "            try { if (comp.layer(i).enabled) { usedLayers++; } } catch (e) {}\n"
        "        }\n"
        "        var startFrame = Math.round(comp.displayStartTime * comp.frameRate);\n"
        "        var endFrame = Math.round((comp.displayStartTime + comp.duration) * comp.frameRate) - 1;\n"
        "        return JSON.stringify({\n"
        "            result: true,\n"
        "            name: comp.name,\n"
        "            width: comp.width,\n"
        "            height: comp.height,\n"
        "            pixelAspect: comp.pixelAspect,\n"
        "            frameRate: comp.frameRate,\n"
        "            startFrame: startFrame,\n"
        "            endFrame: endFrame,\n"
        "            frameRange: startFrame + '-' + endFrame,\n"
        "            duration: comp.duration,\n"
        "            layerCount: comp.numLayers,\n"
        "            usedLayers: usedLayers,\n"
        "            frameDuration: comp.frameDuration,\n"
        "            startTime: comp.startTime,\n"
        "            displayStartTime: comp.displayStartTime,\n"
        "            displayStartFrame: comp.displayStartFrame,\n"
        "            workAreaStart: comp.workAreaStart,\n"
        "            workAreaDuration: comp.workAreaDuration\n"
        "        });\n"
        % comp_id
    )


def build_reveal_items_in_project(item_ids):
    """Select multiple project items and reveal the first one."""
    ids_json = _as_id_list(item_ids, "item ids")
    if ids_json == "[]":
        raise ValueError("item ids must not be empty")
    return _wrap(
        "        var ids = %s;\n"
        "        var found = [];\n"
        "        for (var i = 0; i < ids.length; i++) {\n"
        "            var item = null;\n"
        "            try { item = app.project.itemByID(ids[i]); } catch (e) { item = null; }\n"
        "            if (item) { found.push(item); }\n"
        "        }\n"
        "        if (found.length === 0) {\n"
        '            return JSON.stringify({ result: false, reason: "not_found" });\n'
        "        }\n"
        "        for (var j = 1; j <= app.project.numItems; j++) {\n"
        "            try { app.project.item(j).selected = false; } catch (e) {}\n"
        "        }\n"
        "        for (var k = 0; k < found.length; k++) {\n"
        "            found[k].selected = true;\n"
        "        }\n"
        "        try { app.executeCommand(2523); } catch (e) {}\n"
        "        return JSON.stringify({ result: true, revealedCount: found.length });\n"
        % ids_json
    )


__all__ = [
    "JSON2_POLYFILL",
    "ensure_json_polyfill",
    "js_string",
    "js_bool",
    "decode_response",
    "parse_json_response",
    "parse_json_array",
    "ack_result",
    "build_has_active_comp",
    "build_get_composition_names",
    "build_list_project_comps",
    "build_get_frame_range",
    "build_set_frame_range",
    "build_get_fps",
    "build_set_fps",
    "build_get_app_version",
    "build_get_current_file",
    "build_get_xmp_packet",
    "build_set_xmp_packet",
    "build_get_footage_from_project",
    "build_save_scene",
    "build_open_scene",
    "build_import_media",
    "build_replace_active_item",
    "build_replace_item",
    "build_get_output_module_templates",
    "build_get_active_comp_info",
    "build_comp_dependency_script",
    "build_add_to_render_queue",
    "build_render_with_template",
    "build_collect_footage_records",
    "build_collect_tracker_footage",
    "build_collect_comp_records",
    "build_get_tracker_identity",
    "build_tracker_snapshot",
    "parse_tracker_snapshot",
    "parse_tracker_identity",
    "parse_footage_records",
    "parse_comp_records",
    "parse_comp_dependency_result",
    "build_import_footage_item",
    "build_get_footage_properties",
    "build_replace_footage_by_id",
    "build_set_footage_fps",
    "build_set_comp_fps",
    "build_set_comp_frame_range",
    "build_set_comp_resolution",
    "build_reveal_item_in_project",
    "build_find_comps_using_item",
    "build_open_comp_in_viewer",
    "build_create_folder_structure",
    "build_rename_move_item",
    "build_delete_project_item",
    "build_remove_empty_folders",
    "build_add_footage_to_comp",
    "build_import_to_shot_folder",
    "build_set_item_properties",
    "build_get_item_label",
    "build_find_task_folder_label",
    "build_list_task_folder_footage",
    "build_set_item_labels",
    "build_update_layers_from_source",
    "build_get_comp_info",
    "build_reveal_items_in_project",
]
