# -*- coding: utf-8 -*-
"""Deterministic Kitsu shot-key construction (Phase 6).

Pure-stdlib module so the collision rules are unit-testable without
Prism/Qt.  ``kitsu_integration`` imports it flat
(``from footage_tracker import kitsu_keys``).

Historic behavior stored kitsuShotData under the bare shot name AND a
``sequence-shot`` combined key.  Two sequences containing the same shot
name (SEQ01/SH010 and SEQ02/SH010) collided on the bare key and the last
writer silently won, handing the wrong frame range/fps to one of them.

Rules implemented here:

- The qualified key is always stored.  It is ``sequence-shotName`` when a
  sequence exists and the shot name has no ``-``; otherwise the shot name
  itself is already qualified.
- The bare shot name is stored ONLY while it is unambiguous, i.e. no
  other sequence claims the same bare name.  On conflict the bare key is
  dropped rather than decided by iteration order.
"""

from collections import defaultdict


def qualified_shot_key(shot_name, sequence):
    """Return the always-stored key for a shot."""
    if not isinstance(shot_name, str) or not shot_name:
        raise ValueError("empty shot name")
    if sequence and isinstance(sequence, str) and "-" not in shot_name:
        return "%s-%s" % (sequence, shot_name)
    return shot_name


def bare_shot_key(shot_name, sequence):
    """Return the ambiguous short key, or None when not applicable.

    The bare key only differs from the qualified key when a sequence
    prefix was added; without a sequence (or with ``-`` already in the
    name) the shot name is the qualified key itself.
    """
    if not isinstance(shot_name, str) or not shot_name:
        raise ValueError("empty shot name")
    if sequence and isinstance(sequence, str) and "-" not in shot_name:
        return shot_name
    return None


def get_effective_keys(shot_name, sequence):
    """Return ``(qualified_key, bare_key_or_None)`` for a shot."""
    return qualified_shot_key(shot_name, sequence), bare_shot_key(shot_name, sequence)


def build_shot_key_map(shots, make_entry):
    """Build a collision-free ``{key: entry}`` map from Kitsu shots.

    ``make_entry(shot)`` produces the stored value (dict) for one shot.
    The same entry object may end up under both the qualified and the
    bare key; consumers treat entries as read-only.

    Bare keys claimed by more than one distinct qualified key are left
    out entirely so no shot can silently receive another sequence's data.
    """
    if not hasattr(shots, "__iter__"):
        raise TypeError("shots must be iterable")
    if not callable(make_entry):
        raise TypeError("make_entry must be callable")

    entries = []
    bare_claims = defaultdict(set)

    for shot in shots:
        shot_name = shot.get("shot", "") if isinstance(shot, dict) else ""
        sequence = shot.get("sequence", "") if isinstance(shot, dict) else ""
        if not shot_name or not isinstance(shot_name, str):
            continue
        qualified = qualified_shot_key(shot_name, sequence)
        bare = bare_shot_key(shot_name, sequence)
        entries.append((qualified, bare, make_entry(shot)))
        bare_claims[shot_name].add(qualified)

    ambiguous = {bare for bare, owners in bare_claims.items() if len(owners) > 1}

    result = {}
    dropped = []
    for qualified, bare, entry in entries:
        if qualified not in ambiguous:
            result[qualified] = entry
        if bare is not None and bare not in ambiguous:
            result[bare] = entry
        elif bare is not None and bare in ambiguous:
            dropped.append(bare)

    return result, sorted(set(dropped))


__all__ = [
    "qualified_shot_key",
    "bare_shot_key",
    "get_effective_keys",
    "build_shot_key_map",
]
