from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.verify import result_bytes, scan_private_material


class VerifyScriptTests(unittest.TestCase):
    def test_private_material_scan_is_deterministic_and_ignores_build_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "safe.md").write_text("public mechanism", encoding="utf-8")
            marker = "{# " + "Model Get Context"
            (root / "leak.txt").write_text(f"{marker} 7", encoding="utf-8")
            ignored = root / ".git"
            ignored.mkdir()
            (ignored / "ignored.txt").write_text(f"{marker} 8", encoding="utf-8")

            self.assertEqual(
                scan_private_material(root),
                ("leak.txt: private context-block marker",),
            )

    def test_result_is_canonical_machine_readable_json(self) -> None:
        self.assertEqual(
            result_bytes(("unit", "types"), status="passed"),
            b'{"checks":["unit","types"],"kind":"graph_native_verification_v1",'
            b'"status":"passed","version":"0.1.0a1"}\n',
        )


if __name__ == "__main__":
    unittest.main()
