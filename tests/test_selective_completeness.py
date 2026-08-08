from __future__ import annotations

import unittest
from pathlib import Path

from graph_native_agent_control_plane.canonical_json import loads_strict
from graph_native_agent_control_plane.selective_completeness import (
    SelectiveCompletenessError,
    activate_selective_completeness,
)

ROOT = Path(__file__).resolve().parents[1]


class SelectiveCompletenessTests(unittest.TestCase):
    def test_every_frozen_term_activates_case_insensitively(self) -> None:
        cases = {
            "ALL": "all",
            "at LEAST": "at_least",
            "At Most": "at_most",
            "BOTH": "both",
            "complete SET": "complete_set",
            "Each": "each",
            "EVERY": "every",
            "Exactly": "exactly",
            "MAXIMUM": "maximum",
            "minimum": "minimum",
            "Multiple": "multiple",
            "OPTIMAL": "optimal",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                result = activate_selective_completeness(f"Return {source} result.")
                self.assertTrue(result.activated)
                self.assertEqual(result.matched_terms, (expected,))

    def test_word_boundaries_prevent_substring_activation(self) -> None:
        result = activate_selective_completeness("The smallest optimizer handles minimums.")
        self.assertFalse(result.activated)
        self.assertEqual(result.matched_terms, ())

    def test_matched_terms_use_lexical_policy_order(self) -> None:
        result = activate_selective_completeness("Exactly every item from all inputs.")
        self.assertEqual(result.matched_terms, ("all", "every", "exactly"))

    def test_non_string_instruction_is_rejected(self) -> None:
        with self.assertRaisesRegex(SelectiveCompletenessError, "must be a string"):
            activate_selective_completeness(7)

    def test_inactive_activation_preserves_objective_exactly(self) -> None:
        source = "Explain the scheduler.\nKeep this newline."
        result = activate_selective_completeness(source)
        self.assertFalse(result.activated)
        self.assertEqual(result.objective.encode(), source.encode())
        self.assertEqual(result.matched_terms, ())
        self.assertEqual(result.policy, "literal_completeness_quantifier_v1")

    def test_active_activation_matches_the_hash_bound_instruction(self) -> None:
        source = "Return every valid route."
        expected = (
            "The original task contains explicit completeness language (every). Execute the "
            "original task verbatim. For each such clause, enumerate the full candidate set "
            "supported by the task's domain evidence and make sure the delivered artifact "
            "contains every qualifying result. Use an independent source, algorithm, or "
            "mechanical derivation for this coverage check. Do not validate a value against "
            "itself, invent additional requirements, or alter exact syntax, casing, and bytes "
            "from source evidence. The original task remains authoritative.\n\n"
            "Original task (verbatim):\n"
            "Return every valid route."
        )
        result = activate_selective_completeness(source)
        self.assertEqual(result.objective, expected)

    def test_source_binding_discloses_the_original_source_closure_gap(self) -> None:
        payload = loads_strict((ROOT / "evidence" / "research-source-binding.json").read_bytes())
        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertEqual(
            payload["candidate_source_sha256"],
            "ccc09e4dd0198aa919d99840aa8e52abba1e5e4775249449354d16a7bfb89309",
        )
        self.assertEqual(payload["source_closed"], False)
        self.assertEqual(payload["claim_status"], "provenance_limited_preliminary")


if __name__ == "__main__":
    unittest.main()
