from __future__ import annotations

import unittest
from dataclasses import replace
from typing import cast

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

        with self.assertRaisesRegex(SchedulerError, "positive"):
            parallel_batch(graph, state, limit=True)

    def test_data_flow_requires_accepted_authoritative_output(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node(), validator_node()),
            edges=(
                EdgeDefinition(
                    "agent_to_validator",
                    EdgeKind.DATA_FLOW,
                    "agent",
                    "validator",
                    source_port="result",
                    target_port="candidate",
                ),
            ),
        )
        self.assertNotIn("validator", eligible_nodes(graph, with_states(graph)))
        accepted = with_states(graph, agent=NodeState.ACCEPTED)
        self.assertNotIn("validator", eligible_nodes(graph, accepted))
        with_output = replace(accepted, authoritative_outputs=(("agent", b"{}\n"),))
        self.assertIn("validator", eligible_nodes(graph, with_output))

    def test_evidence_and_recovery_edges_have_distinct_conditions(self) -> None:
        evidence_graph = GraphDefinition.create(
            nodes=(agent_node("source"), agent_node("target")),
            edges=(EdgeDefinition("evidence", EdgeKind.EVIDENCE, "source", "target"),),
        )
        accepted = with_states(evidence_graph, source=NodeState.ACCEPTED)
        self.assertNotIn("target", eligible_nodes(evidence_graph, accepted))
        evidenced = replace(accepted, evidence_nodes=("source",))
        self.assertIn("target", eligible_nodes(evidence_graph, evidenced))

        recovery_graph = GraphDefinition.create(
            nodes=(agent_node("source"), agent_node("target")),
            edges=(EdgeDefinition("recover", EdgeKind.RECOVERY, "source", "target"),),
        )
        self.assertNotIn("target", eligible_nodes(recovery_graph, with_states(recovery_graph)))
        failed = with_states(recovery_graph, source=NodeState.FAILED)
        self.assertIn("target", eligible_nodes(recovery_graph, failed))

    def test_inhibition_is_satisfied_until_source_is_accepted(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("inhibitor"), agent_node("target")),
            edges=(EdgeDefinition("inhibit", EdgeKind.INHIBITION, "inhibitor", "target"),),
        )
        self.assertIn("target", eligible_nodes(graph, with_states(graph)))

    def test_stale_invalidated_and_running_nodes_are_not_schedulable(self) -> None:
        graph = GraphDefinition.create(nodes=(agent_node(),), edges=())
        stale = replace(with_states(graph), graph_id="stale")
        with self.assertRaisesRegex(SchedulerError, "different graph"):
            eligible_nodes(graph, stale)
        invalidated = replace(with_states(graph), invalidated_nodes=("agent",))
        self.assertEqual(eligible_nodes(graph, invalidated), ())
        self.assertEqual(eligible_nodes(graph, with_states(graph, agent=NodeState.RUNNING)), ())

    def test_unknown_edge_kind_is_rejected(self) -> None:
        class UnknownKind:
            value = "unknown"

        graph = GraphDefinition.create(
            nodes=(agent_node("source"), agent_node("target")),
            edges=(
                EdgeDefinition(
                    "unknown_edge",
                    cast(EdgeKind, UnknownKind()),
                    "source",
                    "target",
                ),
            ),
        )
        with self.assertRaisesRegex(SchedulerError, "unsupported edge kind"):
            eligible_nodes(graph, with_states(graph))


if __name__ == "__main__":
    unittest.main()
