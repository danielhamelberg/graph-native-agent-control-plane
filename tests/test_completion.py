from __future__ import annotations

import unittest
from dataclasses import replace

from graph_native_agent_control_plane.completion import (
    CompletionError,
    evaluate_completion,
)
from graph_native_agent_control_plane.model import (
    GraphDefinition,
    NodeDefinition,
    NodeKind,
    NodeState,
    TerminalOutcome,
)
from graph_native_agent_control_plane.reducer import MaterializedState
from tests.test_model import agent_node, terminal_node, validator_node


def completion_graph() -> GraphDefinition:
    return GraphDefinition.create(
        nodes=(agent_node(), validator_node("quality"), terminal_node()),
        edges=(),
        completion_node_ids=("complete",),
    )


def state_with(graph: GraphDefinition, **states: NodeState) -> MaterializedState:
    state = MaterializedState.initial(graph, "execution_one")
    merged = dict(state.node_states)
    merged.update(states)
    return replace(state, node_states=tuple(sorted(merged.items())))


class CompletionCheckpointTests(unittest.TestCase):
    def test_agent_self_declaration_cannot_authorize_completion(self) -> None:
        graph = completion_graph()
        state = state_with(graph, agent=NodeState.ACCEPTED)
        decision = evaluate_completion(graph, state)
        self.assertFalse(decision.authorized)
        self.assertIn("node:quality:state:declared", decision.blockers)

    def test_all_required_nodes_authorize_the_declared_terminal_outcome(self) -> None:
        graph = completion_graph()
        state = state_with(graph, agent=NodeState.ACCEPTED, quality=NodeState.ACCEPTED)
        decision = evaluate_completion(graph, state)
        self.assertTrue(decision.authorized)
        self.assertEqual(decision.outcome, TerminalOutcome.SUCCESS)
        self.assertEqual(decision.blockers, ())

    def test_evidence_approval_and_side_effect_obligations_are_explicit(self) -> None:
        evidence_agent = NodeDefinition(
            "evidence_agent",
            NodeKind.AGENT,
            0,
            True,
            evidence_required=True,
        )
        approval = NodeDefinition("approval_gate", NodeKind.APPROVAL, 0, True)
        tool = NodeDefinition(
            "external_tool",
            NodeKind.TOOL,
            0,
            True,
            side_effect_confirmation_required=True,
        )
        graph = GraphDefinition.create(
            nodes=(evidence_agent, approval, tool, terminal_node()),
            edges=(),
            completion_node_ids=("complete",),
        )
        accepted = state_with(
            graph,
            evidence_agent=NodeState.ACCEPTED,
            approval_gate=NodeState.ACCEPTED,
            external_tool=NodeState.ACCEPTED,
        )
        blocked = evaluate_completion(graph, accepted)
        self.assertEqual(
            blocked.blockers,
            (
                "approval:approval_gate:missing",
                "evidence:evidence_agent:missing",
                "side_effect:external_tool:unconfirmed",
            ),
        )
        satisfied = replace(
            accepted,
            approvals=("approval_gate",),
            evidence_nodes=("evidence_agent",),
            side_effect_confirmations=("external_tool",),
        )
        self.assertTrue(evaluate_completion(graph, satisfied).authorized)

    def test_blocking_conflict_and_invalidated_output_prevent_completion(self) -> None:
        graph = completion_graph()
        accepted = state_with(graph, agent=NodeState.ACCEPTED, quality=NodeState.ACCEPTED)
        state = replace(
            accepted,
            blocking_conflicts=("conflict_one",),
            invalidated_nodes=("agent",),
        )
        decision = evaluate_completion(graph, state)
        self.assertEqual(
            decision.blockers,
            ("conflict:conflict_one:unresolved", "node:agent:invalidated"),
        )

    def test_failure_states_produce_distinct_non_success_outcomes(self) -> None:
        graph = completion_graph()
        cases = {
            NodeState.BLOCKED: TerminalOutcome.BLOCKED,
            NodeState.CANCELLED: TerminalOutcome.CANCELLED,
            NodeState.EXHAUSTED: TerminalOutcome.EXHAUSTED,
            NodeState.FAILED: TerminalOutcome.FAILED,
        }
        for state_value, outcome in cases.items():
            with self.subTest(state=state_value):
                state = state_with(graph, agent=state_value, quality=NodeState.ACCEPTED)
                decision = evaluate_completion(graph, state)
                self.assertFalse(decision.authorized)
                self.assertEqual(decision.outcome, outcome)

    def test_state_for_another_graph_is_rejected(self) -> None:
        graph = completion_graph()
        state = replace(MaterializedState.initial(graph, "execution_one"), graph_id="stale")
        with self.assertRaisesRegex(CompletionError, "different graph"):
            evaluate_completion(graph, state)


if __name__ == "__main__":
    unittest.main()
