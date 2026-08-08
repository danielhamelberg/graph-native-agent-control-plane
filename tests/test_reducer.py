from __future__ import annotations

import unittest
from dataclasses import replace

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


if __name__ == "__main__":
    unittest.main()
