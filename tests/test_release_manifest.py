from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from graph_native_agent_control_plane.canonical_json import loads_strict
from scripts.release_manifest import ManifestError, build_manifest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseManifestTests(unittest.TestCase):
    def test_manifest_is_complete_sorted_and_content_addressed(self) -> None:
        manifest = build_manifest(ROOT)
        files = manifest["files"]
        assert isinstance(files, dict)
        self.assertEqual(tuple(files), tuple(sorted(files)))
        self.assertNotIn("evidence/release-manifest.json", files)
        readme = files["README.md"]
        assert isinstance(readme, dict)
        self.assertEqual(readme["bytes"], (ROOT / "README.md").stat().st_size)
        self.assertEqual(
            readme["sha256"],
            hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest(),
        )

    def test_manifest_rejects_noncanonical_public_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_bytes(b"bad\r\n")
            with self.assertRaisesRegex(ManifestError, "CRLF"):
                build_manifest(root)

    def test_checked_in_manifest_matches_the_repository(self) -> None:
        checked_in = loads_strict((ROOT / "evidence" / "release-manifest.json").read_bytes())
        self.assertEqual(checked_in, build_manifest(ROOT))


if __name__ == "__main__":
    unittest.main()
