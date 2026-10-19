# -*- coding: utf-8 -*-
"""Shared bypass-key builders (stdlib only).

One canonical key format for "ignore this issue" persistence, used by
both the tracker context menu (tree items) and the startup-warnings
dialog (data dictionaries).  The string format is unchanged from the
historic implementation so already-saved bypasses keep matching:

- 3D footage:  ``footage_{shot}_{identifier}_{aov}``
- 2D footage:  ``footage_{shot}_{identifier}`` (with duplicate suffix)
- fallback:    ``footage_{shot}_{name}`` / ``footage_{group}_{name}``
               / ``footage_{path}``
- comps:       ``comp_{comp_id}_{comp_name}``
"""

_2D_PREFIXES = ("[2D]", "[PB]")


def apply_2d_duplicate_suffix(identifier, display_text):
    """Fold a duplicate suffix from the tree label into the identifier.

    "[2D] LowRes (1)" with identifier "LowRes" → "LowRes (1)" so two
    same-named identifiers can be bypassed independently.
    """
    if not isinstance(identifier, str) or not isinstance(display_text, str):
        return identifier or ""
    stripped = display_text
    for prefix in _2D_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):].lstrip(" ")
            break
    if stripped == identifier:
        return identifier
    suffix = stripped.replace(identifier, "", 1).strip()
    if suffix:
        return "%s %s" % (identifier, suffix)
    return identifier


def footage_key(shot, identifier, aov=""):
    """Canonical footage bypass key."""
    if not isinstance(shot, str):
        shot = shot if isinstance(shot, str) else ""
    if not isinstance(identifier, str):
        identifier = ""
    if not isinstance(aov, str):
        aov = ""
    if shot and identifier and aov:
        return "footage_%s_%s_%s" % (shot, identifier, aov)
    if shot and identifier:
        return "footage_%s_%s" % (shot, identifier)
    return ""


def comp_key(comp_id, comp_name):
    """Canonical composition bypass key."""
    comp_id = "" if comp_id is None else str(comp_id)
    comp_name = "" if comp_name is None else str(comp_name)
    return "comp_%s_%s" % (comp_id, comp_name)


def key_from_item_data(item_data, issue_type=None):
    """Build a bypass key from a footage/comp data dictionary.

    Mirrors the historical ``startup_warnings._generateItemKey`` behavior
    (including the 2D duplicate-suffix handling) but without its debug
    output.  ``issue_type`` is accepted for signature compatibility and
    does not influence the key.
    """
    if not isinstance(item_data, dict):
        return None

    if item_data.get("group") == "Comps":
        comp_id = (
            item_data.get("compId") or item_data.get("id") or item_data.get("comp_id")
        )
        comp_name = (
            item_data.get("compName")
            or item_data.get("original_name")
            or item_data.get("name", "")
        )
        return comp_key(comp_id, comp_name)

    shot = item_data.get("shot", "") or ""
    identifier = item_data.get("identifier", "") or ""
    aov = item_data.get("aov", "") or ""
    original_name = item_data.get("original_name") or item_data.get("name", "")

    # Three-part key only when an AOV exists; a two-part key must go
    # through the 2D duplicate-suffix handling below so parity with the
    # historic format is kept.
    if shot and identifier and aov:
        return footage_key(shot, identifier, aov)

    if shot and identifier:
        # 2D render without AOV: keep duplicate suffixes distinct.
        text_for_suffix = item_data.get("tree_text") or original_name
        if isinstance(text_for_suffix, str) and text_for_suffix.startswith(_2D_PREFIXES):
            identifier = apply_2d_duplicate_suffix(identifier, text_for_suffix)
        return footage_key(shot, identifier)

    if shot and original_name:
        return "footage_%s_%s" % (shot, original_name)
    if original_name:
        group = item_data.get("group", "") or ""
        return "footage_%s_%s" % (group, original_name)

    path = item_data.get("path", "") or ""
    if path:
        return "footage_%s" % path
    return None


def key_from_tree_item(item_type, item_text, shot_name, identifier, comp_id=None, comp_name="", path=""):
    """Build a bypass key from tree-item state (context-menu variant).

    ``item_text`` is the QTreeWidgetItem label; for 3D renders it is the
    AOV name.  Callers resolve the shot name before calling this.
    """
    if item_type == "footage":
        if not isinstance(item_text, str):
            item_text = ""
        if not isinstance(identifier, str):
            identifier = ""
        is_2d = item_text.startswith(_2D_PREFIXES)
        is_3d = bool(identifier) and not is_2d and identifier != item_text

        if is_3d:
            return footage_key(shot_name, identifier, item_text)

        if identifier and is_2d:
            identifier = apply_2d_duplicate_suffix(identifier, item_text)
        elif not identifier:
            identifier = item_text
        key = footage_key(shot_name, identifier)
        if key:
            return key
        return "footage_%s" % (path or "")

    if item_type == "comp":
        return comp_key(comp_id, comp_name)

    return None


__all__ = [
    "apply_2d_duplicate_suffix",
    "footage_key",
    "comp_key",
    "key_from_item_data",
    "key_from_tree_item",
]
