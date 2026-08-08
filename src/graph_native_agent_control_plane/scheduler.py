"""Deterministic graph eligibility and batch selection."""

from __future__ import annotations

from .model import EdgeDefinition, EdgeKind, GraphDefinition, NodeDefinition, NodeState
from .reducer import MaterializedState


class SchedulerError(ValueError):
    """Raised when scheduling inputs violate deterministic execution constraints."""


_SCHEDULABLE_STATES = frozenset(
    {NodeState.DECLARED, NodeState.BLOCKED, NodeState.INHIBITED}
)
_FAILURE_STATES = frozenset(
    {NodeState.REJECTED, NodeState.FAILED, NodeState.EXHAUSTED}
)


def _edge_satisfied(edge: EdgeDefinition, state: MaterializedState) -> bool:
    source_state = state.node_state(edge.source)
    if edge.kind in {
        EdgeKind.DEPENDENCY,
        EdgeKind.CONTROL_FLOW,
        EdgeKind.ACTIVATION,
        EdgeKind.COMPLETION,
    }:
        return source_state is NodeState.ACCEPTED
    if edge.kind is EdgeKind.DATA_FLOW:
        if source_state is not NodeState.ACCEPTED:
            return False
        return edge.source in dict(state.authoritative_outputs)
    if edge.kind is EdgeKind.APPROVAL:
        return source_state is NodeState.ACCEPTED and edge.source in state.approvals
    if edge.kind is EdgeKind.EVIDENCE:
        return source_state is NodeState.ACCEPTED and edge.source in state.evidence_nodes
    if edge.kind is EdgeKind.RECOVERY:
        return source_state in _FAILURE_STATES
    if edge.kind is EdgeKind.INHIBITION:
        return source_state is not NodeState.ACCEPTED
    raise SchedulerError(f"unsupported edge kind: {edge.kind.value}")


def eligible_nodes(graph: GraphDefinition, state: MaterializedState) -> tuple[str, ...]:
    """Return eligible node identifiers by descending priority then lexical ID."""

    if state.graph_id != graph.graph_id:
        raise SchedulerError("materialized state references a different graph")
    incoming: dict[str, list[EdgeDefinition]] = {node.node_id: [] for node in graph.nodes}
    for edge in graph.edges:
        incoming[edge.target].append(edge)

    eligible: list[NodeDefinition] = []
    for node in graph.nodes:
        if state.node_state(node.node_id) not in _SCHEDULABLE_STATES:
            continue
        if node.node_id in state.invalidated_nodes:
            continue
        if all(_edge_satisfied(edge, state) for edge in incoming[node.node_id]):
            eligible.append(node)
    ordered = sorted(eligible, key=lambda item: (-item.priority, item.node_id))
    return tuple(node.node_id for node in ordered)


def parallel_batch(
    graph: GraphDefinition,
    state: MaterializedState,
    *,
    limit: int,
) -> tuple[str, ...]:
    """Return the deterministic bounded prefix of currently eligible nodes."""

    if isinstance(limit, bool) or limit < 1:
        raise SchedulerError("parallel batch limit must be a positive integer")
    return eligible_nodes(graph, state)[:limit]
