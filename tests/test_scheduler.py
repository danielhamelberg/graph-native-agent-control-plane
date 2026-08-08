from __future__ import annotations

import unittest
from dataclasses import replace

from graph_native_agent_control_plane.model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    NodeState,
)
from graph_native_agent_control_plane.reducer import MaterializedState
from graph_native_agent_control_plane.scheduler import (
    SchedulerError,
    eligible_nodes,
    parallel_batch,
)
from tests.test_model import agent_node, validator_node


def with_states(
    graph: GraphDefinition,
    **states: NodeState,
) -> MaterializedState:
    initial = MaterializedState.initial(graph, "execution_one")
    merged = dict(initial.node_states)
    merged.update(states)
    return replace(initial, node_states=tuple(sorted(merged.items())))


class SchedulerTests(unittest.TestCase):
    def test_dependency_target_is_eligible_only_after_source_acceptance(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node(), validator_node()),
            edges=(
                EdgeDefinition(
                    "agent_before_validator", EdgeKind.DEPENDENCY, "agent", "validator"
                ),
            ),
        )
        self.assertEqual(eligible_nodes(graph, with_states(graph)), ("agent",))
        accepted = with_states(graph, agent=NodeState.ACCEPTED)
        self.assertEqual(eligible_nodes(graph, accepted), ("validator",))

    def test_inhibition_edge_blocks_target_while_source_is_accepted(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("inhibitor"), agent_node("target")),
            edges=(EdgeDefinition("inhibit_target", EdgeKind.INHIBITION, "inhibitor", "target"),),
        )
        state = with_states(graph, inhibitor=NodeState.ACCEPTED)
        self.assertEqual(eligible_nodes(graph, state), ())

    def test_approval_edge_requires_recorded_approval(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("gate"), agent_node("action")),
            edges=(EdgeDefinition("approve_action", EdgeKind.APPROVAL, "gate", "action"),),
        )
        state = with_states(graph, gate=NodeState.ACCEPTED)
        self.assertEqual(eligible_nodes(graph, state), ())
        approved = replace(state, approvals=("gate",))
        self.assertEqual(eligible_nodes(graph, approved), ("action",))

    def test_failed_dependency_does_not_activate_target(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("source"), agent_node("target")),
            edges=(
                EdgeDefinition(
                    "source_before_target", EdgeKind.DEPENDENCY, "source", "target"
                ),
            ),
        )
        self.assertEqual(eligible_nodes(graph, with_states(graph, source=NodeState.FAILED)), ())

    def test_priority_descends_before_lexical_identifier_tie_break(self) -> None:
        graph = GraphDefinition.create(
            nodes=(
                agent_node("beta", priority=10),
                agent_node("alpha", priority=10),
                agent_node("low"),
            ),
            edges=(),
        )
        self.assertEqual(eligible_nodes(graph, with_states(graph)), ("alpha", "beta", "low"))

    def test_parallel_batch_is_bounded_and_deterministic(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("charlie"), agent_node("alpha"), agent_node("beta")),
            edges=(),
        )
        state = with_states(graph)
        self.assertEqual(parallel_batch(graph, state, limit=2), ("alpha", "beta"))
        with self.assertRaisesRegex(SchedulerError, "positive"):
            parallel_batch(graph, state, limit=0)


if __name__ == "__main__":
    unittest.main()
