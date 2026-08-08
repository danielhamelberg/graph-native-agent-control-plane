# Limitations

## Evidence

The recorded 18/20 versus 16/20 comparison is narrow, local, and preliminary. It covers 20 task-runs
from two repetitions over one frozen 10-task sample. It is not enough to establish transfer,
statistical generality, or production impact.

The accepted research commit was not source-closed: imported runtime dependencies present in the
working tree were omitted from that commit. The extracted Selective Completeness Activation is
bound to the accepted adapter's hash, but this repository has not yet reproduced the benchmark
from a clean checkout. Until that happens, the result remains qualified.

## Mechanism scope

The preliminary benchmark evaluated a pre-inference transformation. It did not evaluate the
Completion Checkpoint, dynamic graph rewriting, the full runtime, multi-agent adjudication, or a
large routed protocol library. Those are separately testable hypotheses.

## Runtime scope

This release does not provide:

- durable or distributed event storage;
- process isolation or a security sandbox;
- distributed locking, consensus, or exactly-once delivery;
- model-provider integrations;
- a policy language for arbitrary activation conditions;
- automatic conflict adjudication or synthesis;
- an operational UI, telemetry backend, or deployment control plane;
- compatibility guarantees before `1.0.0`.

The in-memory runtime is suitable for examples and executable design validation. Operators must add
their own isolation, authentication, authorization, persistence, observability, and failure-domain
controls before consequential use.

## Determinism boundary

Graph construction, canonical serialization, event reduction, scheduling, completion, and checked-in
replay are deterministic for identical inputs. External agents, tools, validators, clocks, networks,
and storage systems can still be nondeterministic. The control plane records accepted results
without making those systems deterministic.

## Security boundary

Hash chaining exposes accidental or unauthorized record modification when hashes are independently
anchored and verified. It is not a digital signature and provides no actor authentication. Content
hashes also do not encrypt sensitive data.

## Correctness boundary

Passing the repository verifier establishes closed-world conformance to checked-in contracts. It
does not prove that a graph captures the user's true objective, that a validator is factually sound,
or that an external side effect occurred unless trustworthy confirmation evidence is supplied.
