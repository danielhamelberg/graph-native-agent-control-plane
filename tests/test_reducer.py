from __future__ import annotations

import unittest
from dataclasses import replace
from typing import cast

from graph_native_agent_control_plane.canonical_json import JsonValue
from graph_native_agent_control_plane.events import EventKind, ExecutionEvent
from graph_native_agent_control_plane.model import GraphDefinition, NodeState
from graph_native_agent_control_plane.reducer import (
    MaterializedState,
    ReductionError,
    reduce_event,
    reduce_events,
)
from tests.test_model import agent_node


def graph() -> GraphDefinition:
    return GraphDefinition.create(nodes=(agent_node(),), edges=())


def transition(
    current: MaterializedState,
    target: NodeState,
    *,
    sequence: int | None = None,
) -> ExecutionEvent:
    return ExecutionEvent.create(
        execution_id=current.execution_id,
        graph_id=current.graph_id,
        sequence=current.next_sequence if sequence is None else sequence,
        actor="orchestrator",
        kind=EventKind.NODE_TRANSITION,
        node_id="agent",
        payload={"to": target.value},
        previous_event_hash=current.last_event_hash,
    )


def advance(current: MaterializedState, *targets: NodeState) -> MaterializedState:
    for target in targets:
        current = reduce_event(graph(), current, transition(current, target))
    return current


def payload_event(
    current: MaterializedState,
    kind: EventKind,
    payload: JsonValue,
    *,
    node_id: str | None = "agent",
    execution_id: str | None = None,
    previous_event_hash: str | None = None,
) -> ExecutionEvent:
    return ExecutionEvent.create(
        execution_id=current.execution_id if execution_id is None else execution_id,
        graph_id=current.graph_id,
        sequence=current.next_sequence,
        actor="tester",
        kind=kind,
        node_id=node_id,
        payload=payload,
        previous_event_hash=(
            current.last_event_hash if previous_event_hash is None else previous_event_hash
        ),
    )


class ReducerTests(unittest.TestCase):
    def test_declared_lifecycle_reduces_without_mutating_prior_state(self) -> None:
        initial = MaterializedState.initial(graph(), "execution_one")
        eligible = reduce_event(graph(), initial, transition(initial, NodeState.ELIGIBLE))
        self.assertEqual(initial.node_state("agent"), NodeState.DECLARED)
        self.assertEqual(eligible.node_state("agent"), NodeState.ELIGIBLE)
        self.assertEqual(eligible.next_sequence, 2)

    def test_illegal_transition_is_rejected(self) -> None:
        initial = MaterializedState.initial(graph(), "execution_one")
        with self.assertRaisesRegex(ReductionError, "illegal node transition"):
            reduce_event(graph(), initial, transition(initial, NodeState.ACCEPTED))

    def test_stale_graph_and_sequence_gap_are_rejected(self) -> None:
        initial = MaterializedState.initial(graph(), "execution_one")
        stale = ExecutionEvent.create(
            execution_id="execution_one",
            graph_id="sha256:" + "0" * 64,
            sequence=1,
            actor="orchestrator",
            kind=EventKind.NODE_TRANSITION,
            node_id="agent",
            payload={"to": "eligible"},
            previous_event_hash=None,
        )
        with self.assertRaisesRegex(ReductionError, "stale graph"):
            reduce_event(graph(), initial, stale)
        with self.assertRaisesRegex(ReductionError, "expected event sequence 1"):
            reduce_event(graph(), initial, transition(initial, NodeState.ELIGIBLE, sequence=2))

    def test_event_hash_tampering_is_rejected(self) -> None:
        initial = MaterializedState.initial(graph(), "execution_one")
        event = transition(initial, NodeState.ELIGIBLE)
        tampered = replace(event, payload_bytes=b'{"to":"accepted"}\n')
        with self.assertRaisesRegex(ReductionError, "event hash mismatch"):
            reduce_event(graph(), initial, tampered)

    def test_rejected_output_never_becomes_authoritative(self) -> None:
        current = MaterializedState.initial(graph(), "execution_one")
        current = advance(current, NodeState.ELIGIBLE, NodeState.ACTIVATED, NodeState.RUNNING)
        output = ExecutionEvent.create(
            execution_id=current.execution_id,
            graph_id=current.graph_id,
            sequence=current.next_sequence,
            actor="agent",
            kind=EventKind.OUTPUT_RECORDED,
            node_id="agent",
            payload={"answer": 42},
            previous_event_hash=current.last_event_hash,
        )
        current = reduce_event(graph(), current, output)
        current = advance(current, NodeState.PRODUCED, NodeState.VALIDATING, NodeState.REJECTED)
        self.assertEqual(current.pending_output("agent"), b'{"answer":42}\n')
        self.assertEqual(current.authoritative_outputs, ())

    def test_accepted_output_becomes_authoritative(self) -> None:
        current = MaterializedState.initial(graph(), "execution_one")
        current = advance(current, NodeState.ELIGIBLE, NodeState.ACTIVATED, NodeState.RUNNING)
        output = ExecutionEvent.create(
            execution_id=current.execution_id,
            graph_id=current.graph_id,
            sequence=current.next_sequence,
            actor="agent",
            kind=EventKind.OUTPUT_RECORDED,
            node_id="agent",
            payload={"answer": 42},
            previous_event_hash=current.last_event_hash,
        )
        current = reduce_event(graph(), current, output)
        current = advance(current, NodeState.PRODUCED, NodeState.VALIDATING, NodeState.ACCEPTED)
        self.assertEqual(current.authoritative_output("agent"), b'{"answer":42}\n')

    def test_replay_is_deterministic(self) -> None:
        current = MaterializedState.initial(graph(), "execution_one")
        events: list[ExecutionEvent] = []
        for target in (NodeState.ELIGIBLE, NodeState.ACTIVATED, NodeState.RUNNING):
            event = transition(current, target)
            events.append(event)
            current = reduce_event(graph(), current, event)
        replayed = reduce_events(graph(), "execution_one", events)
        self.assertEqual(replayed, current)

    def test_initial_state_and_lookup_require_known_identifiers(self) -> None:
        with self.assertRaisesRegex(ReductionError, "execution identifier"):
            MaterializedState.initial(graph(), "")
        state = MaterializedState.initial(graph(), "execution_one")
        with self.assertRaisesRegex(ReductionError, "unknown node"):
            state.node_state("missing")
        with self.assertRaisesRegex(ReductionError, "missing pending output"):
            state.pending_output("agent")
        with self.assertRaisesRegex(ReductionError, "missing authoritative output"):
            state.authoritative_output("agent")
        multiple = replace(
            state,
            pending_outputs=(("alpha", b"1\n"), ("agent", b"2\n")),
        )
        self.assertEqual(multiple.pending_output("agent"), b"2\n")

    def test_event_envelope_rejects_execution_and_chain_mismatch(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        wrong_execution = payload_event(
            state,
            EventKind.NODE_TRANSITION,
            {"to": "eligible"},
            execution_id="execution_two",
        )
        with self.assertRaisesRegex(ReductionError, "different execution"):
            reduce_event(graph(), state, wrong_execution)

        state = reduce_event(graph(), state, transition(state, NodeState.ELIGIBLE))
        broken_chain = payload_event(
            state,
            EventKind.NODE_TRANSITION,
            {"to": "activated"},
            previous_event_hash="wrong",
        )
        with self.assertRaisesRegex(ReductionError, "hash chain"):
            reduce_event(graph(), state, broken_chain)

    def test_node_and_payload_shape_are_required(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        without_node = payload_event(
            state,
            EventKind.NODE_TRANSITION,
            {"to": "eligible"},
            node_id=None,
        )
        with self.assertRaisesRegex(ReductionError, "requires a node identifier"):
            reduce_event(graph(), state, without_node)

        unknown_node = payload_event(
            state,
            EventKind.NODE_TRANSITION,
            {"to": "eligible"},
            node_id="missing",
        )
        with self.assertRaisesRegex(ReductionError, "unknown node"):
            reduce_event(graph(), state, unknown_node)

        non_object = payload_event(state, EventKind.NODE_TRANSITION, ["eligible"])
        with self.assertRaisesRegex(ReductionError, "payload must be an object"):
            reduce_event(graph(), state, non_object)

    def test_transition_payload_requires_a_known_string_state(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        cases: tuple[tuple[JsonValue, str], ...] = (
            ({"to": 1}, "string field"),
            ({"to": "unknown"}, "unknown node state"),
        )
        for payload, message in cases:
            with self.subTest(payload=payload), self.assertRaisesRegex(ReductionError, message):
                reduce_event(
                    graph(),
                    state,
                    payload_event(state, EventKind.NODE_TRANSITION, payload),
                )

    def test_accept_without_output_and_supersession_are_legal(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        state = advance(
            state,
            NodeState.ELIGIBLE,
            NodeState.ACTIVATED,
            NodeState.RUNNING,
            NodeState.PRODUCED,
            NodeState.VALIDATING,
            NodeState.ACCEPTED,
        )
        self.assertEqual(state.authoritative_outputs, ())
        state = reduce_event(graph(), state, transition(state, NodeState.SUPERSEDED))
        self.assertEqual(state.node_state("agent"), NodeState.SUPERSEDED)

    def test_output_requires_running_state(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        event = payload_event(state, EventKind.OUTPUT_RECORDED, {"answer": 42})
        with self.assertRaisesRegex(ReductionError, "only while its node is running"):
            reduce_event(graph(), state, event)

    def test_payload_events_update_each_independent_state_dimension(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        state = reduce_event(
            graph(), state, payload_event(state, EventKind.EVIDENCE_RECORDED, {"source": "x"})
        )
        state = reduce_event(
            graph(), state, payload_event(state, EventKind.SIDE_EFFECT_CONFIRMED, {"ok": True})
        )
        state = reduce_event(
            graph(), state, payload_event(state, EventKind.APPROVAL_RECORDED, {"approved": True})
        )
        state = reduce_event(
            graph(), state, payload_event(state, EventKind.CONFLICT_OPENED, {"conflict_id": "c1"})
        )
        state = reduce_event(
            graph(),
            state,
            payload_event(state, EventKind.CONFLICT_RESOLVED, {"conflict_id": "c1"}),
        )
        self.assertEqual(state.evidence_nodes, ("agent",))
        self.assertEqual(state.side_effect_confirmations, ("agent",))
        self.assertEqual(state.approvals, ("agent",))
        self.assertEqual(state.blocking_conflicts, ())

        state = reduce_event(
            graph(), state, payload_event(state, EventKind.APPROVAL_RECORDED, {"approved": False})
        )
        state = reduce_event(
            graph(), state, payload_event(state, EventKind.NODE_INVALIDATED, {"reason": "rewrite"})
        )
        self.assertEqual(state.approvals, ())
        self.assertEqual(state.invalidated_nodes, ("agent",))
        self.assertEqual(state.node_state("agent"), NodeState.SUPERSEDED)

    def test_payload_event_fields_are_validated(self) -> None:
        state = MaterializedState.initial(graph(), "execution_one")
        invalid_cases: tuple[tuple[EventKind, JsonValue, str], ...] = (
            (EventKind.APPROVAL_RECORDED, {"approved": "yes"}, "Boolean"),
            (EventKind.CONFLICT_OPENED, {"conflict_id": ""}, "non-empty"),
        )
        for kind, payload, message in invalid_cases:
            with self.subTest(kind=kind), self.assertRaisesRegex(ReductionError, message):
                reduce_event(graph(), state, payload_event(state, kind, payload))

    def test_unknown_runtime_event_kind_is_rejected(self) -> None:
        class UnknownKind:
            value = "unknown"

        state = MaterializedState.initial(graph(), "execution_one")
        event = payload_event(state, EventKind.EVIDENCE_RECORDED, {})
        unknown = replace(event, kind=cast(EventKind, UnknownKind()), event_hash="")
        unknown = replace(unknown, event_hash=unknown.expected_hash())
        with self.assertRaisesRegex(ReductionError, "unsupported event kind"):
            reduce_event(graph(), state, unknown)

    def test_empty_replay_returns_initial_state(self) -> None:
        self.assertEqual(
            reduce_events(graph(), "execution_one", ()),
            MaterializedState.initial(graph(), "execution_one"),
        )


if __name__ == "__main__":
    unittest.main()
