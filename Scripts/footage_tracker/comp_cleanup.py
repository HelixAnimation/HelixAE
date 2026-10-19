# -*- coding: utf-8 -*-
"""Protocol helpers for the composition cleanup ("Remove unused items").

Pure-stdlib module so the AE request/response handling can be unit tested
without Prism or Qt.  Scripts are evaluated by HelixAECore.executeAppleScript(),
which injects a JSON polyfill when the script contains "JSON.".  All responses
are JSON documents; item ids are normalized to strings on the Python side.
"""

import json

STATUS_OK = "ok"
STATUS_NO_PROJECT = "no_project"
STATUS_COMP_NOT_FOUND = "comp_not_found"
STATUS_NOT_A_COMP = "not_a_comp"

_REASON_STATUSES = (STATUS_NO_PROJECT, STATUS_COMP_NOT_FOUND, STATUS_NOT_A_COMP)

_WALK_FUNCTION = """
    function hxWalkComp(comp, usedFootage, usedComps) {
        if (usedComps[comp.id]) { return; }
        usedComps[comp.id] = comp.name;
        for (var i = 1; i <= comp.numLayers; i++) {
            var layer = null;
            try { layer = comp.layer(i); } catch (e) { continue; }
            if (!layer || !layer.source) { continue; }
            var src = layer.source;
            if (src instanceof FootageItem) {
                usedFootage[src.id] = src.name;
            } else if (src instanceof CompItem) {
                hxWalkComp(src, usedFootage, usedComps);
            }
        }
    }
"""

_QUERY_SCRIPT = (
    "(function () {"
    + _WALK_FUNCTION
    + """
    try {
        if (!app.project || app.project.numItems <= 0) {
            return JSON.stringify({ status: "no_project" });
        }
        var target = app.project.itemByID(__COMP_ID__);
        if (!target) {
            return JSON.stringify({ status: "comp_not_found" });
        }
        if (!(target instanceof CompItem)) {
            return JSON.stringify({ status: "not_a_comp" });
        }
        var usedFootage = {};
        var usedComps = {};
        hxWalkComp(target, usedFootage, usedComps);
        var unusedFootage = {};
        var unusedComps = {};
        for (var i = 1; i <= app.project.numItems; i++) {
            var item = null;
            try { item = app.project.item(i); } catch (e) { continue; }
            if (!item) { continue; }
            if (item instanceof FootageItem) {
                if (!usedFootage[item.id]) { unusedFootage[item.id] = item.name; }
            } else if (item instanceof CompItem) {
                if (!usedComps[item.id]) { unusedComps[item.id] = item.name; }
            }
        }
        return JSON.stringify({
            status: "ok",
            used: { footage: usedFootage, comps: usedComps },
            unused: { footage: unusedFootage, comps: unusedComps }
        });
    } catch (e) {
        return JSON.stringify({ status: "error", detail: e.toString() });
    }
})();
"""
)

_REMOVE_SCRIPT = (
    "(function () {"
    + _WALK_FUNCTION
    + """
    var payload = "";
    app.beginUndoGroup("HelixAE: Remove unused items");
    try {
        if (!app.project || app.project.numItems <= 0) {
            payload = JSON.stringify({ status: "error", detail: "no open project" });
        } else {
            var target = app.project.itemByID(__COMP_ID__);
            if (!target || !(target instanceof CompItem)) {
                payload = JSON.stringify({ status: "error", detail: "anchor composition is no longer available" });
            } else {
                var usedFootage = {};
                var usedComps = {};
                hxWalkComp(target, usedFootage, usedComps);
                var itemIds = __ITEM_IDS__;
                var results = {};
                for (var i = 0; i < itemIds.length; i++) {
                    var id = itemIds[i];
                    try {
                        if (usedFootage[id] || usedComps[id]) {
                            results[id] = "retained";
                            continue;
                        }
                        var item = app.project.itemByID(id);
                        if (!item) {
                            results[id] = "not_found";
                            continue;
                        }
                        if (!(item instanceof FootageItem) && !(item instanceof CompItem)) {
                            results[id] = "wrong_type";
                            continue;
                        }
                        item.remove();
                        results[id] = "removed";
                    } catch (e) {
                        results[id] = "error: " + e.toString();
                    }
                }
                payload = JSON.stringify({ status: "ok", results: results });
            }
        }
    } catch (e) {
        payload = JSON.stringify({ status: "error", detail: e.toString() });
    }
    app.endUndoGroup();
    return payload;
})();
"""
)


def normalize_comp_id(comp_id):
    comp_id = int(comp_id)
    if comp_id <= 0:
        raise ValueError("invalid composition id: %r" % (comp_id,))
    return comp_id


def normalize_item_ids(item_ids):
    ids = []
    for raw in item_ids:
        item_id = int(raw)
        if item_id <= 0:
            raise ValueError("invalid item id: %r" % (raw,))
        ids.append(item_id)
    if not ids:
        raise ValueError("no item ids provided")
    return ids


def build_unused_items_script(comp_id):
    comp_id = normalize_comp_id(comp_id)
    return _QUERY_SCRIPT.replace("__COMP_ID__", str(comp_id))


def build_remove_items_script(comp_id, item_ids):
    comp_id = normalize_comp_id(comp_id)
    ids = normalize_item_ids(item_ids)
    id_list = "[" + ",".join(str(i) for i in ids) + "]"
    return _REMOVE_SCRIPT.replace("__COMP_ID__", str(comp_id)).replace("__ITEM_IDS__", id_list)


def _decode_response(result):
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


def _empty_query_result():
    return {
        "ok": False,
        "error": None,
        "reason": None,
        "used": {"footage": {}, "comps": {}},
        "unused": {"footage": {}, "comps": {}},
    }


def parse_unused_items_result(result):
    parsed = _empty_query_result()
    text, error = _decode_response(result)
    if error:
        parsed["error"] = error
        return parsed
    try:
        data = json.loads(text)
    except ValueError:
        parsed["error"] = "invalid JSON response: %r" % text[:200]
        return parsed
    if not isinstance(data, dict) or "status" not in data:
        parsed["error"] = "malformed response (missing status)"
        return parsed
    status = data["status"]
    if status in _REASON_STATUSES:
        parsed["ok"] = True
        parsed["reason"] = status
        return parsed
    if status != STATUS_OK:
        parsed["error"] = "After Effects error: %s" % data.get("detail", status)
        return parsed
    for section in ("used", "unused"):
        for kind in ("footage", "comps"):
            mapping = data.get(section, {}).get(kind, {})
            if not isinstance(mapping, dict):
                parsed["error"] = "malformed response (%s.%s)" % (section, kind)
                return parsed
            parsed[section][kind] = {str(k): str(v) for k, v in mapping.items()}
    parsed["ok"] = True
    return parsed


def parse_remove_items_result(result):
    parsed = {"ok": False, "error": None, "results": {}}
    text, error = _decode_response(result)
    if error:
        parsed["error"] = error
        return parsed
    try:
        data = json.loads(text)
    except ValueError:
        parsed["error"] = "invalid JSON response: %r" % text[:200]
        return parsed
    if not isinstance(data, dict):
        parsed["error"] = "malformed response"
        return parsed
    if data.get("status") != STATUS_OK:
        parsed["error"] = "After Effects error: %s" % data.get("detail", data.get("status", "unknown"))
        return parsed
    results = data.get("results", {})
    if not isinstance(results, dict):
        parsed["error"] = "malformed response (results)"
        return parsed
    parsed["results"] = {str(k): str(v) for k, v in results.items()}
    parsed["ok"] = True
    return parsed


def summarize_removal_results(results):
    summary = {
        "removed": 0,
        "not_found": 0,
        "retained": 0,
        "wrong_type": 0,
        "failed": 0,
        "failed_details": [],
    }
    for item_id, status in results.items():
        if status == "removed":
            summary["removed"] += 1
        elif status == "not_found":
            summary["not_found"] += 1
        elif status == "retained":
            summary["retained"] += 1
        elif status == "wrong_type":
            summary["wrong_type"] += 1
        else:
            summary["failed"] += 1
            summary["failed_details"].append("%s: %s" % (item_id, status))
    return summary


__all__ = [
    "STATUS_OK",
    "STATUS_NO_PROJECT",
    "STATUS_COMP_NOT_FOUND",
    "STATUS_NOT_A_COMP",
    "normalize_comp_id",
    "normalize_item_ids",
    "build_unused_items_script",
    "build_remove_items_script",
    "parse_unused_items_result",
    "parse_remove_items_result",
    "summarize_removal_results",
]
