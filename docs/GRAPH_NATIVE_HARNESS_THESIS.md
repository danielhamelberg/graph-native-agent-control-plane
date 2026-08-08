# Graph-Native Harness Thesis

## Thesis

**Graph engineering is the next level in harness engineering when agent control decisions become
explicit, typed, replayable graph transitions instead of remaining implicit in prompts, callbacks,
and mutable orchestration code.**

This is an engineering thesis, not a benchmark conclusion.

The terminology is not claimed as original. Public projects were already using “graph engineering”
and “graph-native harness” for adjacent ideas before this release; see
[Terminology and Prior Art](PRIOR_ART.md).

## Why “graph-native” matters

Many systems visualize an execution trace as a graph after the fact. A graph-native harness goes
further: the graph is the authority that determines what may execute, what data may propagate, what
must be validated, which approval applies, what becomes authoritative, and whether completion is
admissible.

The practical shift is from:

```text
agent runs -> code decides ad hoc -> logs describe what happened
```

to:

```text
typed graph -> eligible transition -> recorded event -> reduced state -> validated next transition
```

## The engineering object

The object being engineered is not only a prompt or workflow. It is a versioned control graph with:

- typed execution, validation, approval, recovery, synthesis, and terminal nodes;
- dependency, data, activation, inhibition, evidence, and completion edges;
- explicit lifecycle and state-transition rules;
- schema-bound interfaces;
- deterministic scheduling and join semantics;
- immutable provenance and invalidation;
- graph-level completion predicates.

This creates inspectable control surfaces for interventions that are difficult to govern inside a
monolithic prompt.

## Selective intervention

The architecture does not imply activating every control for every task. The useful pattern is
sparse, conditional intervention: detect a task-state condition, activate the smallest relevant
control, measure its marginal effect, and retain it only if it passes an external evaluation gate.

The included Selective Completeness Activation is one preliminary example of that pattern. The
Completion Checkpoint is a different, post-execution mechanism awaiting external performance
evaluation.

## Falsifiable program

The thesis becomes credible through successive tests:

1. A single intervention beats a direct-agent baseline under frozen evaluation.
2. Routing activates that intervention more accurately than a fixed policy.
3. Other controls produce independent gains in their intended failure classes.
4. Composed controls outperform isolated controls without causing regressions or cost explosion.
5. An evidence-gated promotion loop improves the accepted harness on held-out and open-world tasks.

Changes that do not survive main-task, regression, adversarial, cost, safety, and reproducibility
checks should be rejected or quarantined. A large control library is a hypothesis space, not proof
of capability.

## What this repository contributes

This repository supplies a compact executable vocabulary for the thesis: content-addressed graphs,
typed hash-chained events, pure reduction, deterministic scheduling, versioned rewriting, and
graph-authorized completion. It also publishes one small benchmark-linked intervention with a
strictly bounded evidence claim.

The intended contribution is methodological: turn agent-control ideas into separately testable,
replayable mechanisms rather than asking a model to obey an ever-growing undifferentiated prompt.
