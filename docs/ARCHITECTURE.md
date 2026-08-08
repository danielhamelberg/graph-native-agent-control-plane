# Architecture

## Functional core, imperative shell

The package separates deterministic decisions from effects.

```text
ports/adapters
     |
     v
runtime shell -----> append-only event store
     |                        |
     |                        v
     +--------------------> reducer
                                |
                   +------------+------------+
                   v                         v
              scheduler             completion authority
```

The graph, events, and materialized state are immutable values. Reduction, scheduling, completion,
and rewriting return new values. Agent, validation, authorization, and persistence effects live
behind typed ports.

## Graph definition

`GraphDefinition` contains sorted node and edge tuples plus declared completion nodes. Construction
checks identifier syntax, uniqueness, endpoints, terminal-node consistency, and data-port schema
compatibility. The graph identifier is the SHA-256 of canonical graph content, excluding the
identifier itself.

Nodes distinguish agents, tools, validators, approvals, joins, synthesizers, recovery, and terminal
outcomes. Edges distinguish dependency, control, data, activation, inhibition, approval, evidence,
recovery, and completion relationships.

## Event and state model

An `ExecutionEvent` binds an execution and graph version to a sequence number, actor, event kind,
optional node, canonical payload hash, prior event hash, and its own content hash. The reducer
checks the chain, sequence, graph binding, event shape, and lifecycle transition before producing a
new `MaterializedState`.

Outputs remain pending until the producing node is accepted. Rejected output never becomes
authoritative. Evidence, approvals, conflicts, confirmed side effects, and invalidations are
separate state dimensions rather than overloaded status strings.

## Scheduling

The scheduler considers only nodes whose graph conditions are satisfied. Required dependencies and
approvals must be accepted; active inhibition blocks eligibility. Candidate nodes are ordered by
descending declared priority and then lexical node identifier. Parallel batches are explicit and
bounded.

## Completion authority

Completion is evaluated from graph and materialized state, never from an agent's textual claim.
Authorization requires three conditions: every required nonterminal node is accepted and current;
all required approvals, evidence, and side-effect confirmations exist; and every blocking conflict
is resolved. The decision returns an authorization flag, a typed terminal or partial outcome, and a
lexically ordered blocker set.

## Graph rewriting

Rewriting creates a new content-addressed graph version with a parent identifier. Operations are
authorized and bounded. Executed nodes cannot be removed in place. Replacing a node invalidates
that node, downstream descendants, and affected approvals; historical graph values and events
remain unchanged.

## Separate benchmark primitive

`selective_completeness.py` is intentionally outside the graph runtime. It is the exact small
pre-inference mechanism tied to the preliminary benchmark evidence. Keeping it separate prevents a
result for an input transformation from being attributed to the Completion Checkpoint or to the
larger graph architecture.

## Trust boundaries

- JSON ingestion rejects duplicate members, BOMs, malformed UTF-8, trailing content, and non-finite
  numbers.
- Adapter output must be valid canonicalizable JSON before an output event is appended.
- A result for a stale graph version is rejected.
- Validators and authorization providers report through narrow typed contracts.
- Schemas close objects with `additionalProperties: false`.

The current implementation is an executable reference core, not a distributed consensus system or
a production orchestration service.
