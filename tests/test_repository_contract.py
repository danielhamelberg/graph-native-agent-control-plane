from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryContractTests(unittest.TestCase):
    def test_open_source_operating_documents_exist(self) -> None:
        for relative in (
            "CITATION.cff",
            "CONTRIBUTING.md",
            "NOTICE",
            "SECURITY.md",
            "src/graph_native_agent_control_plane/py.typed",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_workflows_pin_actions_and_declare_least_privilege(self) -> None:
        workflows = tuple(sorted((ROOT / ".github" / "workflows").glob("*.yml")))
        self.assertGreaterEqual(len(workflows), 2)
        for path in workflows:
            content = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("permissions:", content)
                uses = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)$", content, flags=re.MULTILINE)
                self.assertGreater(len(uses), 0)
                for reference in uses:
                    self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_conformance_workflow_runs_the_public_verifier(self) -> None:
        content = (ROOT / ".github" / "workflows" / "conformance.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("uv sync --frozen --all-groups", content)
        self.assertIn("uv run python scripts/verify.py", content)
        self.assertIn("ubuntu-latest", content)
        self.assertIn("windows-latest", content)

    def test_dependency_updates_cover_python_and_actions(self) -> None:
        content = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "pip"', content)
        self.assertIn('package-ecosystem: "github-actions"', content)

    def test_security_and_citation_metadata_bind_the_public_repository(self) -> None:
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        repository = "https://github.com/danielhamelberg/graph-native-agent-control-plane"
        self.assertIn(f"{repository}/security/advisories/new", security)
        self.assertIn(f'repository-code: "{repository}"', citation)
        self.assertIn('version: "0.1.0-alpha.1"', citation)

    def test_prior_art_note_separates_exact_name_from_broader_concept(self) -> None:
        content = (ROOT / "docs" / "PRIOR_ART.md").read_text(encoding="utf-8")
        self.assertIn("zero indexed public-code matches", content)
        self.assertIn("does not establish coinage", content)
        self.assertIn("From Harness to Loop to Graph Engineering", content)
        self.assertIn("graph-native harness", content)
        self.assertIn("cannot credibly claim to have coined", content)


if __name__ == "__main__":
    unittest.main()
