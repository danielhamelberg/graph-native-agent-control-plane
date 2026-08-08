"""Hash-bound pre-inference selective completeness activation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_POLICY: Final = "literal_completeness_quantifier_v1"
_PATTERNS: Final = (
    ("all", re.compile(r"\ball\b", flags=re.IGNORECASE)),
    ("at_least", re.compile(r"\bat\s+least\b", flags=re.IGNORECASE)),
    ("at_most", re.compile(r"\bat\s+most\b", flags=re.IGNORECASE)),
    ("both", re.compile(r"\bboth\b", flags=re.IGNORECASE)),
    ("complete_set", re.compile(r"\bcomplete\s+set\b", flags=re.IGNORECASE)),
    ("each", re.compile(r"\beach\b", flags=re.IGNORECASE)),
    ("every", re.compile(r"\bevery\b", flags=re.IGNORECASE)),
    ("exactly", re.compile(r"\bexactly\b", flags=re.IGNORECASE)),
    ("maximum", re.compile(r"\bmaximum\b", flags=re.IGNORECASE)),
    ("minimum", re.compile(r"\bminimum\b", flags=re.IGNORECASE)),
    ("multiple", re.compile(r"\bmultiple\b", flags=re.IGNORECASE)),
    ("optimal", re.compile(r"\boptimal\b", flags=re.IGNORECASE)),
)


class SelectiveCompletenessError(ValueError):
    """Raised when the activation boundary receives an invalid instruction."""


@dataclass(frozen=True, slots=True)
class SelectiveCompletenessActivation:
    """Deterministic activation decision and the resulting agent objective."""

    objective: str
    activated: bool
    matched_terms: tuple[str, ...]
    policy: str = _POLICY


def _transformed_objective(instruction: str, matched_terms: tuple[str, ...]) -> str:
    terms = ", ".join(matched_terms)
    return (
        "The original task contains explicit completeness language "
        f"({terms}). Execute the original task verbatim. For each such clause, enumerate the "
        "full candidate set supported by the task's domain evidence and make sure the delivered "
        "artifact contains every qualifying result. Use an independent source, algorithm, or "
        "mechanical derivation for this coverage check. Do not validate a value against itself, "
        "invent additional requirements, or alter exact syntax, casing, and bytes from source "
        "evidence. The original task remains authoritative.\n\n"
        "Original task (verbatim):\n"
        f"{instruction}"
    )


def activate_selective_completeness(instruction: object) -> SelectiveCompletenessActivation:
    """Conditionally transform an objective using the frozen benchmark policy."""

    if not isinstance(instruction, str):
        raise SelectiveCompletenessError("external task instruction must be a string")
    matched_terms = tuple(name for name, pattern in _PATTERNS if pattern.search(instruction))
    if not matched_terms:
        return SelectiveCompletenessActivation(
            objective=instruction,
            activated=False,
            matched_terms=(),
        )
    return SelectiveCompletenessActivation(
        objective=_transformed_objective(instruction, matched_terms),
        activated=True,
        matched_terms=matched_terms,
    )
