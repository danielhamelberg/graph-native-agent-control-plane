from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicClaimContractTests(unittest.TestCase):
    def test_readme_names_the_two_distinct_mechanisms(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Selective Completeness Activation", readme)
        self.assertIn("pre-inference", readme)
        self.assertIn("Completion Checkpoint", readme)
        self.assertIn("post-execution", readme)

    def test_readme_discloses_the_evidence_boundary(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for required in (
            "18/20",
            "16/20",
            "two local repetitions",
            "Class C",
            "provenance-limited preliminary evidence",
            "not an independent replication",
        ):
            with self.subTest(required=required):
                self.assertIn(required, readme)

    def test_readme_contains_no_inflated_claims(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").casefold()
        for prohibited in (
            "statistically significant",
            "independently replicated",
            "superhuman",
            "post-output checkpoint improved",
            "all 149 protocols improved",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, readme)


if __name__ == "__main__":
    unittest.main()
