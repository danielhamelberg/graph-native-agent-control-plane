# Contributing

Contributions are welcome when they preserve the project's deterministic, evidence-bounded design.

## Development setup

Install CPython 3.12 and uv 0.6.9 or a compatible locked version, then run:

```console
uv sync --frozen --all-groups
uv run python scripts/verify.py
```

The complete verifier must pass before review. It enforces unit and property tests, 100% package
branch coverage, Ruff, strict mypy, strict Pyright, schemas, deterministic replay, release-manifest
integrity, reproducible distribution builds, and private-material exclusion.

## Change discipline

1. Open an issue for semantic or public-API changes.
2. Add a failing test that captures the intended behavior.
3. Make the smallest implementation change that passes it.
4. Add negative and boundary cases for new control decisions.
5. Update schemas, examples, evidence, and limitations together when a contract changes.
6. Regenerate the manifest with `uv run python scripts/release_manifest.py --write`.
7. Run the full verifier from the repository root.

Do not weaken an evaluator, remove difficult cases, relax coverage, or broaden a public claim to make
a change appear successful. Proposed performance improvements require a frozen baseline, exact
change, held-out or external evaluation, regression and cost checks, and a reproducible ledger.

## Public boundary

Never contribute credentials, personal data, private protocol corpora, routing policies, held-out
tasks, raw model responses, benchmark payloads, research caches, or absolute local paths. Use small
synthetic fixtures whose licenses and provenance are clear.

## Style

- Preserve immutable values and pure decision functions in the core.
- Keep effects behind typed ports.
- Reject ambiguous or malformed input at boundaries.
- Use canonical UTF-8, LF endings, explicit schemas, and deterministic ordering.
- Avoid hidden clock, random, environment, filesystem-order, or dictionary-order dependencies.

By contributing, you agree that your contribution is licensed under Apache-2.0.
