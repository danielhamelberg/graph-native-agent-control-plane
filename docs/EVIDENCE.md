# Evidence

## Claim under evaluation

The narrow research hypothesis was that conditionally adding an independent completeness check to
tasks containing explicit completeness language could improve successful task completion without
requiring greater measured token use per successful task.

## Recorded result

The frozen research ledger records:

| Measure | Candidate | Direct baseline |
|---|---:|---:|
| Successful task-runs | 18/20 | 16/20 |
| Paired outcomes | 2 wins, 0 losses | — |
| Repetitions | 2 local | 2 local |

The ledger also records lower token units per successful task for the candidate. This repository
does not restate a rounded percentage because the unit definition and complete raw evaluation
artifacts belong to the source-closure rerun.

## What was evaluated

The candidate's distinguishing public mechanism was **Selective Completeness Activation**: a
deterministic pre-inference transformation activated by twelve frozen lexical patterns. The exact
transformation is implemented in `selective_completeness.py` and linked to its source adapter by:

- accepted evidence commit: `a9b5a49fbb1f7030f3da9585726ed47fd5caecdc`;
- candidate adapter SHA-256:
  `ccc09e4dd0198aa919d99840aa8e52abba1e5e4775249449354d16a7bfb89309`;
- candidate adapter byte length: `44753`.

Machine-readable binding metadata is in `evidence/research-source-binding.json`.

## Claim class

This is **Class C, provenance-limited preliminary evidence**: an empirical result inside a bounded
local harness. It is not an independent replication and is not open-world evidence.

The accepted evidence commit omitted imported runtime dependencies that existed only in the working
tree. The numerical record is preserved, but the clean public repository cannot yet reconstruct the
entire accepted system from that commit alone.

## What the evidence does not support

It does not show that:

- the Completion Checkpoint caused the recorded difference;
- the graph-native runtime improves agent performance;
- a broader protocol library or router improves performance;
- the effect transfers to other tasks, models, providers, or environments;
- the observed difference exceeds sampling variation;
- the repository is production-ready.

## Graduation criteria

Narrowing the qualification requires a frozen, source-closed evaluation package run from a clean
checkout and independently adjudicated. A stronger claim additionally requires unseen tasks, more
repetitions, confidence intervals suited to the paired design, cost and latency data, regression and
adversarial suites, and preferably an external rerun.

Any new result should retain the old ledger rather than overwrite it, bind exact source and data
hashes, and state its evidence class explicitly.
