# Graph-Native Agent Control Plane

[![Conformance](https://github.com/danielhamelberg/graph-native-agent-control-plane/actions/workflows/conformance.yml/badge.svg)](https://github.com/danielhamelberg/graph-native-agent-control-plane/actions/workflows/conformance.yml)
[![CodeQL](https://github.com/danielhamelberg/graph-native-agent-control-plane/actions/workflows/codeql.yml/badge.svg)](https://github.com/danielhamelberg/graph-native-agent-control-plane/actions/workflows/codeql.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

A small, typed reference implementation for making agent coordination, validation, recovery,
and completion explicit graph operations.

This repository is deliberately narrower than an agent framework. It provides deterministic
control-plane primitives that can sit around an existing agent runtime: immutable graph
definitions, typed ports and events, legal lifecycle reduction, deterministic scheduling,
versioned rewrites, and graph-authorized completion.

Status: `0.1.0a1` pre-release. The API may change.

## Why this exists

Most agent harnesses encode control flow in callbacks, prompts, and incidental runtime state.
That makes it difficult to answer basic operational questions: What was eligible? Which output
became authoritative? What blocked completion? Which graph version received approval?

This project treats those questions as graph state:

```text
objective -> agent work -> validation -> accepted output -> completion
                 |              |
                 +-- recovery <-+
```

Every accepted state change is represented by a typed, hash-chained event. A pure reducer
reconstructs execution state. The scheduler and completion authority read only the declared graph
and reduced state, making their decisions replayable.

## Two mechanisms—kept separate

**Selective Completeness Activation** is a pre-inference input transformation. It detects a frozen
set of literal completeness terms and conditionally adds an independently checkable coverage
instruction while preserving the original task verbatim.

**Completion Checkpoint** is a post-execution control-plane capability. It admits a terminal graph
transition only when required nodes, validation, evidence, approvals, conflicts, invalidations,
and side-effect confirmations permit it.

The benchmark below evaluated the first mechanism. It did not evaluate the second mechanism or
the entire control plane.

## Evidence boundary

On one frozen 10-task Terminal-Bench 2.0 sample, across two local repetitions, the research
candidate recorded 18/20 successful task-runs versus 16/20 for direct Codex. The ledger also
recorded two paired wins, zero paired losses, and lower measured token units per success.

This is **Class C, provenance-limited preliminary evidence**. It is not an independent replication.
The result supplies no evidence of statistical generality, and the clean repository has not yet
reproduced it. The original accepted commit omitted imported runtime files that existed only in its
working tree. The exact extracted transformation is hash-bound here; a source-closed rerun from a
clean checkout remains required. See [Evidence](docs/EVIDENCE.md) and
[Limitations](docs/LIMITATIONS.md).

## Install and verify

Requirements: CPython 3.12 and [uv](https://docs.astral.sh/uv/).

```console
uv sync --all-groups
uv run python scripts/verify.py
```

The verifier runs unit and property tests, 100% branch-coverage enforcement for the package,
Ruff, strict mypy, strict Pyright, schema/example validation, three-seed determinism checks, a
private-material scan, and package builds. It writes one deterministic JSON result to standard
output and detailed failure output to standard error.

## Minimal use

```python
from graph_native_agent_control_plane.selective_completeness import (
    activate_selective_completeness,
)

activation = activate_selective_completeness("Return exactly three supported findings.")
assert activation.activated
print(activation.objective)
```

For an end-to-end, hash-chained replay, see
[`examples/completeness-graph.json`](examples/completeness-graph.json) and
[`examples/replay.json`](examples/replay.json).

## Design commitments

- Immutable, content-addressed graph definitions.
- Closed node, edge, state, event, and outcome types.
- Schema-identified node ports and validated data-flow compatibility.
- Append-only, hash-chained execution events.
- Pure deterministic reduction, scheduling, and completion decisions.
- Explicit approval, evidence, conflict, invalidation, and side-effect state.
- Versioned, authorized, bounded graph rewriting with downstream invalidation.
- Fail-closed behavior at malformed JSON, stale graph, illegal transition, and adapter boundaries.

The architecture is documented in [Architecture](docs/ARCHITECTURE.md). The design thesis is in
[Graph-Native Harness Thesis](docs/GRAPH_NATIVE_HARNESS_THESIS.md), with terminology research in
[Prior Art](docs/PRIOR_ART.md).

## Public boundary

The repository publishes the control-plane mechanism, its contracts, deterministic examples, and
claim-scoped evidence metadata. It does not include private protocol corpora, routing policies,
held-out cases, raw benchmark payloads, credentials, or research-worktree caches.

## License

Apache-2.0. See [LICENSE](LICENSE).
