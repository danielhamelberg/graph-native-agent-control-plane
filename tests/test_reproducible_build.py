from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.reproducible_build import BuildReproducibilityError, compare_artifact_directories


class ReproducibleBuildTests(unittest.TestCase):
    def test_identical_artifacts_return_stable_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "package.whl").write_bytes(b"wheel")
            (second / "package.whl").write_bytes(b"wheel")
            self.assertEqual(
                compare_artifact_directories(first, second),
                {"package.whl": "ba59926159d2aa256eb8739b8da7e2b574b960e1202c6d624cbe981cef996c91"},
            )

    def test_missing_or_different_artifacts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "package.whl").write_bytes(b"first")
            with self.assertRaisesRegex(BuildReproducibilityError, "artifact sets differ"):
                compare_artifact_directories(first, second)
            (second / "package.whl").write_bytes(b"second")
            with self.assertRaisesRegex(BuildReproducibilityError, "artifact bytes differ"):
                compare_artifact_directories(first, second)


if __name__ == "__main__":
    unittest.main()
