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
from graph_native_agent_control_plane.rewriting import (
    AddEdge,
    AddNode,
    RemoveNode,
    ReplaceNode,
    RewriteError,
    apply_rewrite,
)
from tests.test_model import agent_node, terminal_node, validator_node


def rewrite_graph() -> GraphDefinition:
    return GraphDefinition.create(
        nodes=(agent_node(), validator_node(), terminal_node()),
        edges=(
            EdgeDefinition("agent_before_validator", EdgeKind.DEPENDENCY, "agent", "validator"),
            EdgeDefinition(
                "validator_before_complete", EdgeKind.COMPLETION, "validator", "complete"
            ),
        ),
        completion_node_ids=("complete",),
    )


class RewritingTests(unittest.TestCase):
    def test_rewrite_creates_new_content_addressed_version_without_mutating_parent(self) -> None:
        graph = rewrite_graph()
        state = MaterializedState.initial(graph, "execution_one")
        result = apply_rewrite(
            graph,
            state,
            operations=(AddNode(agent_node("reviewer")),),
            authority="orchestrator",
        )
        self.assertEqual(result.graph.parent_graph_id, graph.graph_id)
        self.assertEqual(result.graph.version, 2)
        self.assertNotEqual(result.graph.graph_id, graph.graph_id)
        self.assertEqual(
            tuple(node.node_id for node in graph.nodes),
            ("agent", "complete", "validator"),
        )
        self.assertEqual(
            tuple(node.node_id for node in result.graph.nodes),
            ("agent", "complete", "reviewer", "validator"),
        )

    def test_rewrite_requires_authority_and_obeys_operation_bound(self) -> None:
        graph = rewrite_graph()
        state = MaterializedState.initial(graph, "execution_one")
        with self.assertRaisesRegex(RewriteError, "authority"):
            apply_rewrite(graph, state, operations=(AddNode(agent_node("reviewer")),), authority="")
        with self.assertRaisesRegex(RewriteError, "operation limit"):
            apply_rewrite(
                graph,
                state,
                operations=(AddNode(agent_node("one")), AddNode(agent_node("two"))),
                authority="orchestrator",
                max_operations=1,
            )

    def test_executed_node_cannot_be_removed(self) -> None:
        graph = rewrite_graph()
        state = MaterializedState.initial(graph, "execution_one")
        states = dict(state.node_states)
        states["agent"] = NodeState.ACCEPTED
        state = replace(state, node_states=tuple(sorted(states.items())))
        with self.assertRaisesRegex(RewriteError, "executed node"):
            apply_rewrite(
                graph,
                state,
                operations=(RemoveNode("agent"),),
                authority="orchestrator",
            )

    def test_replacement_invalidates_accepted_node_and_all_descendants(self) -> None:
        graph = rewrite_graph()
        state = MaterializedState.initial(graph, "execution_one")
        state = replace(
            state,
            node_states=tuple((node.node_id, NodeState.ACCEPTED) for node in graph.nodes),
            authoritative_outputs=(("agent", b'{"answer":42}\n'),),
        )
        result = apply_rewrite(
            graph,
            state,
            operations=(ReplaceNode(agent_node(priority=100)),),
            authority="orchestrator",
        )
        self.assertEqual(result.invalidated_nodes, ("agent", "complete", "validator"))

    def test_new_dependency_cycle_is_rejected(self) -> None:
        graph = rewrite_graph()
        state = MaterializedState.initial(graph, "execution_one")
        operation = AddEdge(
            EdgeDefinition("validator_before_agent", EdgeKind.DEPENDENCY, "validator", "agent")
        )
        with self.assertRaisesRegex(RewriteError, "cycle"):
            apply_rewrite(graph, state, operations=(operation,), authority="orchestrator")


if __name__ == "__main__":
    unittest.main()
