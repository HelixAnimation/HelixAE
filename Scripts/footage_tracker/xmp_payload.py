# -*- coding: utf-8 -*-
"""XMP payload storage helpers (stdlib only).

The footage tracker persists two kinds of data in the After Effects
project XMP packet:

- ``PrismFootageTracker:VersionCache`` (legacy, disposable — now only
  read once for migration, see hierarchy_builder)
- ``PrismFootageTracker:BypassedItems`` (user data)

Historic writers emitted malformed entries like::

    <rdf:li>PrismFootageTracker:BypassedItems">{json}</rdf:li

(``">`` artifact, missing ``>`` on the closing tag, unescaped JSON
inside XML).  Depending on which path wrote the entry, the marker was
``Tag">`` or ``Tag>`` — and the reader only matched one of them, so
saved bypasses could become unreadable.  This module reads ALL legacy
variants and writes one canonical, namespace-aware form:

    <rdf:Description rdf:about="" xmlns:prismft="...">
      <prismft:Tag>xml-escaped-payload</prismft:Tag>
    </rdf:Description>
"""

import re
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import unescape as _xml_unescape

NAMESPACE = "http://prism-pipeline.com/FootageTracker/1.0/"
NAMESPACE_PREFIX = "prismft"

_DESCRIPTION_TEMPLATE = (
    '<rdf:Description rdf:about="" xmlns:%s="%s">\n'
    "        <%s:%s>%s</%s:%s>\n"
    "    </rdf:Description>"
)

_EMPTY_PACKET = (
    '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="HelixAE">\n'
    '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    "    %s\n"
    "  </rdf:RDF>\n"
    "</x:xmpmeta>\n"
    '<?xpacket end="w"?>'
)


def _canonical_property(tag, escaped_payload):
    return _DESCRIPTION_TEMPLATE % (
        NAMESPACE_PREFIX,
        NAMESPACE,
        NAMESPACE_PREFIX,
        tag,
        escaped_payload,
        NAMESPACE_PREFIX,
        tag,
    )


def _canonical_pattern(tag):
    return re.compile(
        r"<%s:%s>(.*?)</%s:%s>" % (NAMESPACE_PREFIX, tag, NAMESPACE_PREFIX, tag),
        re.DOTALL,
    )


def _legacy_pattern(tag):
    """Matches the malformed ``<rdf:li>...Tag("|>)payload</rdf:li`` blocks.

    The legacy writers stored the full property name
    (``PrismFootageTracker:Tag``) between the ``rdf:li`` opener and the
    payload, so the pattern allows any non-tag prefix on that line.
    """
    return re.compile(
        r"<rdf:li[^>]*>[^<]*%s(?:\"|>)>?.*?</rdf:li\s*>" % re.escape(tag),
        re.DOTALL,
    )


def extract_payload(packet, tag):
    """Return ``(payload, error)``.

    Tries the canonical namespaced property first, then both legacy
    marker variants (``Tag">`` written by hierarchy_builder and ``Tag>``
    written by startup_warnings).  Legacy payloads were stored unescaped
    and are returned verbatim; canonical payloads are XML-unescaped.
    """
    if not isinstance(packet, str) or not packet:
        return None, "empty XMP packet"
    if not isinstance(tag, str) or not tag:
        return None, "empty tag"

    match = _canonical_pattern(tag).search(packet)
    if match:
        payload = match.group(1).strip()
        return _xml_unescape(payload), None

    # Legacy variant 1: Tag">{payload}</rdf:li   (hierarchy_builder)
    start_marker = '%s">' % tag
    # Legacy variant 2: Tag>{payload}</rdf:li>   (startup_warnings append)
    start_marker_plain = "%s>" % tag
    end_marker = "</rdf:li"

    start_idx = packet.find(start_marker)
    offset = len(start_marker)
    if start_idx < 0:
        start_idx = packet.find(start_marker_plain)
        offset = len(start_marker_plain)
    if start_idx < 0:
        return None, "tag %r not found" % tag

    start_idx += offset
    end_idx = packet.find(end_marker, start_idx)
    if end_idx < 0:
        return None, "unterminated legacy entry for %r" % tag
    if end_idx <= start_idx:
        return None, "empty legacy entry for %r" % tag
    return packet[start_idx:end_idx].strip(), None


def upsert_payload(packet, tag, payload):
    """Insert or replace ``payload`` under ``tag``; returns the new packet.

    Replaces both canonical properties and any legacy ``rdf:li`` block
    for the tag with the canonical namespaced form.  Never leaves the
    legacy artifact behind.
    """
    if not isinstance(tag, str) or not tag:
        raise ValueError("empty tag")
    if not isinstance(payload, str):
        raise TypeError("payload must be a string")

    escaped = _xml_escape(payload)
    canonical = _canonical_property(tag, escaped)

    if packet is None:
        packet = ""
    if not isinstance(packet, str):
        raise TypeError("packet must be a string")

    # Replace an existing canonical property.
    pattern = _canonical_pattern(tag)
    if pattern.search(packet):
        return pattern.sub(canonical, packet, count=1)

    # Remove any legacy block for this tag, then insert the canonical form.
    legacy = _legacy_pattern(tag)
    had_legacy = bool(legacy.search(packet))
    packet = legacy.sub("", packet, count=1)

    if "</rdf:RDF>" in packet:
        insert_at = packet.rfind("</rdf:RDF>")
        return packet[:insert_at] + canonical + packet[insert_at:]
    if "</x:xmpmeta>" in packet:
        return packet.replace(
            "</x:xmpmeta>", "  <rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\n"
            "    " + canonical + "\n  </rdf:RDF>\n</x:xmpmeta>", 1)
    if had_legacy:
        # Legacy data existed outside a recognizable structure.
        return packet + "\n" + _EMPTY_PACKET % canonical
    return _EMPTY_PACKET % canonical


def strip_payload(packet, tag):
    """Remove every storage form of ``tag`` from the packet."""
    if not isinstance(packet, str) or not packet:
        return packet or ""
    packet = _canonical_pattern(tag).sub("", packet)
    return _legacy_pattern(tag).sub("", packet)


def has_payload(packet, tag):
    """True when any storage form of ``tag`` is present."""
    if not isinstance(packet, str) or not packet:
        return False
    if _canonical_pattern(tag).search(packet):
        return True
    return ('%s">' % tag) in packet or ("%s>" % tag) in packet


__all__ = [
    "NAMESPACE",
    "NAMESPACE_PREFIX",
    "extract_payload",
    "upsert_payload",
    "strip_payload",
    "has_payload",
]
