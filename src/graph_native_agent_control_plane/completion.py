"""Graph-level completion authority independent of agent self-declaration."""

from __future__ import annotations

from dataclasses import dataclass

from .model import GraphDefinition, NodeKind, NodeState, TerminalOutcome
from .reducer import MaterializedState


class CompletionError(ValueError):
    """Raised when a completion decision cannot be evaluated soundly."""


@dataclass(frozen=True, slots=True)
class CompletionDecision:
    """A deterministic authorization decision and its complete blocker set."""

    authorized: bool
    outcome: TerminalOutcome | None
    blockers: tuple[str, ...]


def _incomplete_outcome(
    graph: GraphDefinition,
    state: MaterializedState,
) -> TerminalOutcome | None:
    states = [
        state.node_state(node.node_id)
        for node in graph.nodes
        if node.required and node.kind is not NodeKind.TERMINAL
    ]
    if NodeState.EXHAUSTED in states:
        return TerminalOutcome.EXHAUSTED
    if NodeState.FAILED in states or NodeState.REJECTED in states:
        return TerminalOutcome.FAILED
    if NodeState.CANCELLED in states:
        return TerminalOutcome.CANCELLED
    if NodeState.BLOCKED in states or NodeState.INHIBITED in states:
        return TerminalOutcome.BLOCKED
    if NodeState.ACCEPTED in states:
        return TerminalOutcome.PARTIAL
    return None


def evaluate_completion(
    graph: GraphDefinition,
    state: MaterializedState,
) -> CompletionDecision:
    """Evaluate whether the graph, rather than an agent, authorizes termination."""

    if state.graph_id != graph.graph_id:
        raise CompletionError("materialized state references a different graph")
    if not graph.completion_node_ids:
        raise CompletionError("graph declares no completion node")

    blockers = [
        f"conflict:{conflict_id}:unresolved" for conflict_id in state.blocking_conflicts
    ]
    for node in graph.nodes:
        if not node.required or node.kind is NodeKind.TERMINAL:
            continue
        if node.node_id in state.invalidated_nodes:
            blockers.append(f"node:{node.node_id}:invalidated")
            continue
        node_state = state.node_state(node.node_id)
        if node_state is not NodeState.ACCEPTED:
            blockers.append(f"node:{node.node_id}:state:{node_state.value}")
            continue
        if node.kind is NodeKind.APPROVAL and node.node_id not in state.approvals:
            blockers.append(f"approval:{node.node_id}:missing")
        if node.evidence_required and node.node_id not in state.evidence_nodes:
            blockers.append(f"evidence:{node.node_id}:missing")
        if (
            node.side_effect_confirmation_required
            and node.node_id not in state.side_effect_confirmations
        ):
            blockers.append(f"side_effect:{node.node_id}:unconfirmed")

    ordered_blockers = tuple(sorted(blockers))
    if ordered_blockers:
        return CompletionDecision(
            authorized=False,
            outcome=_incomplete_outcome(graph, state),
            blockers=ordered_blockers,
        )
    terminal = graph.node(graph.completion_node_ids[0])
    assert terminal.terminal_outcome is not None
    return CompletionDecision(
        authorized=True,
        outcome=terminal.terminal_outcome,
        blockers=(),
    )
