from __future__ import annotations

import hashlib
import unittest

from graph_native_agent_control_plane.canonical_json import (
    CanonicalJsonError,
    canonical_bytes,
    canonical_sha256,
    loads_strict,
)


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_member_is_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "duplicate object member: a"):
            loads_strict(b'{"a":1,"a":2}')

    def test_bom_is_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "BOM"):
            loads_strict(b"\xef\xbb\xbf{}")

    def test_malformed_utf8_is_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "UTF-8"):
            loads_strict(b'"\xff"')

    def test_trailing_data_is_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "trailing data"):
            loads_strict(b"{} []")

    def test_non_finite_constants_are_rejected(self) -> None:
        for constant in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(constant=constant), self.assertRaisesRegex(
                CanonicalJsonError, "non-finite"
            ):
                loads_strict(constant)

    def test_valid_json_allows_surrounding_whitespace(self) -> None:
        self.assertEqual(loads_strict(b" \r\n {\"a\": [true, null, 2]} \t"), {"a": [True, None, 2]})

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "invalid JSON"):
            loads_strict(b"{")


class CanonicalJsonTests(unittest.TestCase):
    def test_canonical_bytes_are_sorted_utf8_compact_and_lf_terminated(self) -> None:
        self.assertEqual(canonical_bytes({"z": 1, "a": "é"}), b'{"a":"\xc3\xa9","z":1}\n')

    def test_canonical_hash_is_sha256_of_canonical_bytes(self) -> None:
        value = {"nested": [3, 2, 1], "ok": True}
        expected = hashlib.sha256(canonical_bytes(value)).hexdigest()
        self.assertEqual(canonical_sha256(value), expected)

    def test_non_json_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "unsupported JSON value"):
            canonical_bytes({"bad": object()})

    def test_non_finite_floats_are_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "non-finite"):
            canonical_bytes({"bad": float("nan")})

    def test_finite_float_and_nested_containers_are_supported(self) -> None:
        self.assertEqual(canonical_bytes({"values": [1.5]}), b'{"values":[1.5]}\n')

    def test_non_string_object_names_are_rejected(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "names must be strings"):
            canonical_bytes({1: "invalid"})

    def test_unpaired_surrogate_is_rejected_at_utf8_boundary(self) -> None:
        with self.assertRaisesRegex(CanonicalJsonError, "serialized canonically"):
            canonical_bytes("\ud800")


if __name__ == "__main__":
    unittest.main()
