"""Pure reduction of execution events into immutable materialized state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from .canonical_json import JsonValue, loads_strict
from .events import EventKind, ExecutionEvent
from .model import GraphDefinition, GraphModelError, NodeState


class ReductionError(ValueError):
    """Raised when an event cannot legally update materialized state."""


_LEGAL_TRANSITIONS: dict[NodeState, frozenset[NodeState]] = {
    NodeState.DECLARED: frozenset(
        {NodeState.ELIGIBLE, NodeState.BLOCKED, NodeState.INHIBITED, NodeState.CANCELLED}
    ),
    NodeState.ELIGIBLE: frozenset(
        {NodeState.ACTIVATED, NodeState.BLOCKED, NodeState.INHIBITED, NodeState.CANCELLED}
    ),
    NodeState.ACTIVATED: frozenset(
        {NodeState.RUNNING, NodeState.BLOCKED, NodeState.INHIBITED, NodeState.CANCELLED}
    ),
    NodeState.RUNNING: frozenset(
        {NodeState.PRODUCED, NodeState.FAILED, NodeState.BLOCKED, NodeState.CANCELLED}
    ),
    NodeState.PRODUCED: frozenset(
        {NodeState.VALIDATING, NodeState.REJECTED, NodeState.FAILED}
    ),
    NodeState.VALIDATING: frozenset(
        {NodeState.ACCEPTED, NodeState.REJECTED, NodeState.FAILED}
    ),
    NodeState.REJECTED: frozenset({NodeState.RECOVERING, NodeState.EXHAUSTED}),
    NodeState.FAILED: frozenset({NodeState.RECOVERING, NodeState.EXHAUSTED}),
    NodeState.RECOVERING: frozenset({NodeState.ELIGIBLE, NodeState.EXHAUSTED}),
    NodeState.BLOCKED: frozenset(
        {NodeState.ELIGIBLE, NodeState.CANCELLED, NodeState.EXHAUSTED}
    ),
    NodeState.INHIBITED: frozenset({NodeState.ELIGIBLE, NodeState.CANCELLED}),
    NodeState.ACCEPTED: frozenset({NodeState.SUPERSEDED}),
    NodeState.SUPERSEDED: frozenset(),
    NodeState.CANCELLED: frozenset(),
    NodeState.EXHAUSTED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class MaterializedState:
    """Current execution state derived solely from a graph and its event chain."""

    execution_id: str
    graph_id: str
    next_sequence: int
    last_event_hash: str | None
    node_states: tuple[tuple[str, NodeState], ...]
    pending_outputs: tuple[tuple[str, bytes], ...] = ()
    authoritative_outputs: tuple[tuple[str, bytes], ...] = ()
    evidence_nodes: tuple[str, ...] = ()
    approvals: tuple[str, ...] = ()
    blocking_conflicts: tuple[str, ...] = ()
    side_effect_confirmations: tuple[str, ...] = ()
    invalidated_nodes: tuple[str, ...] = ()

    @classmethod
    def initial(cls, graph: GraphDefinition, execution_id: str) -> MaterializedState:
        if not execution_id:
            raise ReductionError("execution identifier must be non-empty")
        return cls(
            execution_id=execution_id,
            graph_id=graph.graph_id,
            next_sequence=1,
            last_event_hash=None,
            node_states=tuple((node.node_id, NodeState.DECLARED) for node in graph.nodes),
        )

    def node_state(self, node_id: str) -> NodeState:
        for candidate, state in self.node_states:
            if candidate == node_id:
                return state
        raise ReductionError(f"unknown node in materialized state: {node_id}")

    def pending_output(self, node_id: str) -> bytes:
        return _lookup_bytes(self.pending_outputs, node_id, "pending output")

    def authoritative_output(self, node_id: str) -> bytes:
        return _lookup_bytes(self.authoritative_outputs, node_id, "authoritative output")


def _lookup_bytes(values: tuple[tuple[str, bytes], ...], key: str, subject: str) -> bytes:
    for candidate, value in values:
        if candidate == key:
            return value
    raise ReductionError(f"missing {subject} for node: {key}")


def _set_pair[T](
    values: tuple[tuple[str, T], ...], key: str, value: T
) -> tuple[tuple[str, T], ...]:
    updated = dict(values)
    updated[key] = value
    return tuple(sorted(updated.items()))


def _remove_pair[T](values: tuple[tuple[str, T], ...], key: str) -> tuple[tuple[str, T], ...]:
    return tuple((candidate, item) for candidate, item in values if candidate != key)


def _payload_object(event: ExecutionEvent) -> dict[str, JsonValue]:
    payload = loads_strict(event.payload_bytes)
    if not isinstance(payload, dict):
        raise ReductionError(f"event payload must be an object: {event.kind.value}")
    return payload


def _required_node_id(graph: GraphDefinition, event: ExecutionEvent) -> str:
    if event.node_id is None:
        raise ReductionError(f"event requires a node identifier: {event.kind.value}")
    try:
        graph.node(event.node_id)
    except GraphModelError as exc:
        raise ReductionError(str(exc)) from None
    return event.node_id


def _validate_envelope(state: MaterializedState, event: ExecutionEvent) -> None:
    if event.expected_hash() != event.event_hash:
        raise ReductionError(f"event hash mismatch at sequence {event.sequence}")
    if event.execution_id != state.execution_id:
        raise ReductionError("event belongs to a different execution")
    if event.graph_id != state.graph_id:
        raise ReductionError("event references a stale graph")
    if event.sequence != state.next_sequence:
        raise ReductionError(
            f"expected event sequence {state.next_sequence}, received {event.sequence}"
        )
    if event.previous_event_hash != state.last_event_hash:
        raise ReductionError("event hash chain does not match materialized state")


def _transition(
    graph: GraphDefinition,
    state: MaterializedState,
    event: ExecutionEvent,
) -> MaterializedState:
    node_id = _required_node_id(graph, event)
    payload = _payload_object(event)
    target_value = payload.get("to")
    if not isinstance(target_value, str):
        raise ReductionError("node-transition event requires string field 'to'")
    try:
        target = NodeState(target_value)
    except ValueError:
        raise ReductionError(f"unknown node state: {target_value}") from None
    current = state.node_state(node_id)
    if target not in _LEGAL_TRANSITIONS[current]:
        raise ReductionError(f"illegal node transition for {node_id}: {current} -> {target}")
    pending = state.pending_outputs
    authoritative = state.authoritative_outputs
    if target is NodeState.ACCEPTED:
        pending_value = dict(pending).get(node_id)
        if pending_value is not None:
            authoritative = _set_pair(authoritative, node_id, pending_value)
    if target is NodeState.SUPERSEDED:
        authoritative = _remove_pair(authoritative, node_id)
    return replace(
        state,
        node_states=_set_pair(state.node_states, node_id, target),
        pending_outputs=pending,
        authoritative_outputs=authoritative,
    )


def _apply_payload_event(
    graph: GraphDefinition,
    state: MaterializedState,
    event: ExecutionEvent,
) -> MaterializedState:
    node_id = _required_node_id(graph, event)
    if event.kind is EventKind.OUTPUT_RECORDED:
        if state.node_state(node_id) is not NodeState.RUNNING:
            raise ReductionError("output may be recorded only while its node is running")
        return replace(
            state,
            pending_outputs=_set_pair(state.pending_outputs, node_id, event.payload_bytes),
        )
    if event.kind is EventKind.EVIDENCE_RECORDED:
        return replace(state, evidence_nodes=tuple(sorted(set(state.evidence_nodes) | {node_id})))
    if event.kind is EventKind.SIDE_EFFECT_CONFIRMED:
        return replace(
            state,
            side_effect_confirmations=tuple(
                sorted(set(state.side_effect_confirmations) | {node_id})
            ),
        )
    if event.kind is EventKind.APPROVAL_RECORDED:
        payload = _payload_object(event)
        approved = payload.get("approved")
        if not isinstance(approved, bool):
            raise ReductionError("approval event requires Boolean field 'approved'")
        approvals = set(state.approvals)
        approvals.discard(node_id)
        if approved:
            approvals.add(node_id)
        return replace(state, approvals=tuple(sorted(approvals)))
    if event.kind in {EventKind.CONFLICT_OPENED, EventKind.CONFLICT_RESOLVED}:
        payload = _payload_object(event)
        conflict_id = payload.get("conflict_id")
        if not isinstance(conflict_id, str) or not conflict_id:
            raise ReductionError("conflict event requires non-empty field 'conflict_id'")
        conflicts = set(state.blocking_conflicts)
        if event.kind is EventKind.CONFLICT_OPENED:
            conflicts.add(conflict_id)
        else:
            conflicts.discard(conflict_id)
        return replace(state, blocking_conflicts=tuple(sorted(conflicts)))
    if event.kind is EventKind.NODE_INVALIDATED:
        return replace(
            state,
            node_states=_set_pair(state.node_states, node_id, NodeState.SUPERSEDED),
            pending_outputs=_remove_pair(state.pending_outputs, node_id),
            authoritative_outputs=_remove_pair(state.authoritative_outputs, node_id),
            invalidated_nodes=tuple(sorted(set(state.invalidated_nodes) | {node_id})),
        )
    raise ReductionError(f"unsupported event kind: {event.kind.value}")


def reduce_event(
    graph: GraphDefinition,
    state: MaterializedState,
    event: ExecutionEvent,
) -> MaterializedState:
    """Apply one verified event without mutating its inputs."""

    _validate_envelope(state, event)
    if event.kind is EventKind.NODE_TRANSITION:
        updated = _transition(graph, state, event)
    else:
        updated = _apply_payload_event(graph, state, event)
    return replace(
        updated,
        next_sequence=state.next_sequence + 1,
        last_event_hash=event.event_hash,
    )


def reduce_events(
    graph: GraphDefinition,
    execution_id: str,
    events: Iterable[ExecutionEvent],
) -> MaterializedState:
    """Replay an ordered event chain from a fresh materialized state."""

    state = MaterializedState.initial(graph, execution_id)
    for event in events:
        state = reduce_event(graph, state, event)
    return state
