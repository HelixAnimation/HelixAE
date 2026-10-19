# -*- coding: utf-8 -*-
"""Regression tests for footage_tracker.xmp_payload (stdlib only).

Covers the canonical namespaced form plus BOTH legacy malformed variants
(``Tag">`` from hierarchy_builder and ``Tag>`` from the old
startup_warnings append path — the bug that made saved bypasses
unreadable).
"""

import importlib.util
import json
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_PATH = os.path.join(REPO_ROOT, "Scripts", "footage_tracker", "xmp_payload.py")


def _load():
    spec = importlib.util.spec_from_file_location("xmp_payload", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


xmp_payload = _load()

TAG = "BypassedItems"

# A realistic AE-style XMP packet with the legacy rdf:li block inside.
_LEGACY_PACKET_V1 = (
    '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '    <rdf:Description rdf:about="" xmlns:pdfx="http://ns.adobe.com/pdfx/1.0/">\n'
    '      <pdfx:UserDefined>\n'
    '        <rdf:Bag>\n'
    "          <rdf:li>PrismFootageTracker:BypassedItems\">"
    '{"outdated": ["footage_SH030_Lighting_beauty"]}</rdf:li>\n'
    "        </rdf:Bag>\n"
    "      </pdfx:UserDefined>\n"
    "    </rdf:Description>\n"
    "  </rdf:RDF>\n"
    "</x:xmpmeta>\n"
    '<?xpacket end="w"?>'
)

# Variant 2 (startup_warnings append bug): marker without the quote.
_LEGACY_PACKET_V2 = _LEGACY_PACKET_V1.replace(
    'PrismFootageTracker:BypassedItems">', "PrismFootageTracker:BypassedItems>"
)

# Packet with an RDF close but no payload for the tag.
_CLEAN_PACKET = (
    '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '    <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
    "      <dc:format>application/vnd.adobe.aftereffects.project</dc:format>\n"
    "    </rdf:Description>\n"
    "  </rdf:RDF>\n"
    "</x:xmpmeta>\n"
    '<?xpacket end="w"?>'
)


class TestExtractPayload(unittest.TestCase):
    def test_canonical_round_trip_with_special_characters(self):
        payload = json.dumps(
            {"note": "Client's <b>éclair</b> & \"stuff\"", "n": [1, 2]}
        )
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, payload)
        extracted, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(error)
        self.assertEqual(json.loads(extracted), json.loads(payload))

    def test_canonical_round_trip_plain(self):
        payload = '{"outdated": ["footage_SH030_Lighting_beauty"]}'
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, payload)
        extracted, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(error)
        self.assertEqual(extracted, payload)

    def test_legacy_variant1_read(self):
        extracted, error = xmp_payload.extract_payload(_LEGACY_PACKET_V1, TAG)
        self.assertIsNone(error)
        self.assertIn("footage_SH030_Lighting_beauty", extracted)
        self.assertEqual(
            json.loads(extracted),
            {"outdated": ["footage_SH030_Lighting_beauty"]},
        )

    def test_legacy_variant2_read_the_append_bug_format(self):
        extracted, error = xmp_payload.extract_payload(_LEGACY_PACKET_V2, TAG)
        self.assertIsNone(error)
        self.assertEqual(
            json.loads(extracted),
            {"outdated": ["footage_SH030_Lighting_beauty"]},
        )

    def test_full_legacy_name_also_matches(self):
        # Readers historically used the full marker; the short tag must
        # still locate legacy payloads because the payload position is
        # identical.
        extracted, error = xmp_payload.extract_payload(_LEGACY_PACKET_V1, TAG)
        self.assertIsNone(error)
        self.assertTrue(extracted.startswith("{"))

    def test_missing_tag(self):
        _, error = xmp_payload.extract_payload(_CLEAN_PACKET, TAG)
        self.assertIsNotNone(error)

    def test_empty_inputs(self):
        self.assertIsNotNone(xmp_payload.extract_payload("", TAG)[1])
        self.assertIsNotNone(xmp_payload.extract_payload(None, TAG)[1])
        self.assertIsNotNone(xmp_payload.extract_payload(_CLEAN_PACKET, "")[1])

    def test_unterminated_legacy_entry(self):
        packet = "<rdf:li>PrismFootageTracker:BypassedItems\">{json}"
        _, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNotNone(error)

    def test_empty_legacy_entry(self):
        packet = "xPrismFootageTracker:BypassedItems\"></rdf:li"
        _, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNotNone(error)


class TestUpsertPayload(unittest.TestCase):
    def test_insert_into_clean_packet_uses_namespace(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, "{}")
        self.assertIn("prismft:%s" % TAG, packet)
        self.assertIn(xmp_payload.NAMESPACE, packet)
        self.assertIn("</rdf:RDF>", packet)
        extracted, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(error)
        self.assertEqual(extracted, "{}")

    def test_replace_existing_canonical(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, '{"a": 1}')
        packet = xmp_payload.upsert_payload(packet, TAG, '{"a": 2}')
        extracted, _ = xmp_payload.extract_payload(packet, TAG)
        self.assertEqual(json.loads(extracted), {"a": 2})
        self.assertEqual(packet.count("prismft:%s" % TAG), 2)  # open + close only

    def test_legacy_block_replaced_by_canonical(self):
        packet = xmp_payload.upsert_payload(_LEGACY_PACKET_V1, TAG, '{"b": 2}')
        # Legacy artifact must be gone.
        self.assertNotIn('BypassedItems">', packet)
        extracted, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(error)
        self.assertEqual(json.loads(extracted), {"b": 2})

    def test_legacy_variant2_replaced_by_canonical(self):
        packet = xmp_payload.upsert_payload(_LEGACY_PACKET_V2, TAG, '{"b": 3}')
        extracted, error = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(error)
        self.assertEqual(json.loads(extracted), {"b": 3})

    def test_none_packet_builds_minimal(self):
        packet = xmp_payload.upsert_payload(None, TAG, "{}")
        self.assertIn("<x:xmpmeta", packet)
        self.assertIn("prismft:%s" % TAG, packet)

    def test_packet_without_rdf_or_meta(self):
        packet = xmp_payload.upsert_payload("just some junk", TAG, "{}")
        self.assertIn("<x:xmpmeta", packet)
        extracted, _ = xmp_payload.extract_payload(packet, TAG)
        self.assertEqual(extracted, "{}")

    def test_legacy_outside_structure_gets_wrapped(self):
        packet = "noise <rdf:li>PrismFootageTracker:BypassedItems\">{x}</rdf:li> end"
        result = xmp_payload.upsert_payload(packet, TAG, '{"ok": 1}')
        extracted, error = xmp_payload.extract_payload(result, TAG)
        self.assertIsNone(error)
        self.assertEqual(json.loads(extracted), {"ok": 1})

    def test_payload_is_xml_escaped(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, "<tag> & 'quote'")
        self.assertNotIn("<tag>", packet)
        extracted, _ = xmp_payload.extract_payload(packet, TAG)
        self.assertEqual(extracted, "<tag> & 'quote'")

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            xmp_payload.upsert_payload(_CLEAN_PACKET, "", "x")
        with self.assertRaises(TypeError):
            xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, {"not": "a string"})
        with self.assertRaises(TypeError):
            xmp_payload.upsert_payload(123, TAG, "x")

    def test_other_tags_untouched(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, "VersionCache", "{}")
        packet = xmp_payload.upsert_payload(packet, TAG, '{"final": 1}')
        vc, vc_err = xmp_payload.extract_payload(packet, "VersionCache")
        self.assertIsNone(vc_err)
        self.assertEqual(vc, "{}")
        bp, bp_err = xmp_payload.extract_payload(packet, TAG)
        self.assertIsNone(bp_err)
        self.assertEqual(json.loads(bp), {"final": 1})


class TestHasAndStripPayload(unittest.TestCase):
    def test_has_payload_canonical(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, "{}")
        self.assertTrue(xmp_payload.has_payload(packet, TAG))

    def test_has_payload_legacy_both_variants(self):
        self.assertTrue(xmp_payload.has_payload(_LEGACY_PACKET_V1, TAG))
        self.assertTrue(xmp_payload.has_payload(_LEGACY_PACKET_V2, TAG))

    def test_has_payload_false_for_clean(self):
        self.assertFalse(xmp_payload.has_payload(_CLEAN_PACKET, TAG))

    def test_has_payload_empty_packet(self):
        self.assertFalse(xmp_payload.has_payload("", TAG))
        self.assertFalse(xmp_payload.has_payload(None, TAG))

    def test_strip_removes_canonical(self):
        packet = xmp_payload.upsert_payload(_CLEAN_PACKET, TAG, "{}")
        stripped = xmp_payload.strip_payload(packet, TAG)
        self.assertFalse(xmp_payload.has_payload(stripped, TAG))

    def test_strip_removes_legacy(self):
        stripped = xmp_payload.strip_payload(_LEGACY_PACKET_V1, TAG)
        self.assertFalse(xmp_payload.has_payload(stripped, TAG))
        stripped2 = xmp_payload.strip_payload(_LEGACY_PACKET_V2, TAG)
        self.assertFalse(xmp_payload.has_payload(stripped2, TAG))

    def test_strip_empty_packet_passthrough(self):
        self.assertEqual(xmp_payload.strip_payload("", TAG), "")
        self.assertEqual(xmp_payload.strip_payload(None, TAG), "")

    def test_strip_keeps_other_content(self):
        stripped = xmp_payload.strip_payload(_LEGACY_PACKET_V1, TAG)
        self.assertIn("pdfx:UserDefined", stripped)
        self.assertIn("rdf:Bag", stripped)


if __name__ == "__main__":
    unittest.main()
