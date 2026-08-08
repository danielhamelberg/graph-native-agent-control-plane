from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from graph_native_agent_control_plane.model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    GraphModelError,
    NodeDefinition,
    NodeKind,
    Port,
    TerminalOutcome,
)


def agent_node(node_id: str = "agent", *, priority: int = 0) -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        kind=NodeKind.AGENT,
        priority=priority,
        required=True,
        output_ports=(Port("result", "urn:schema:result"),),
    )


def validator_node(node_id: str = "validator") -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        kind=NodeKind.VALIDATOR,
        priority=0,
        required=True,
        input_ports=(Port("candidate", "urn:schema:result"),),
    )


def terminal_node(node_id: str = "complete") -> NodeDefinition:
    return NodeDefinition(
        node_id=node_id,
        kind=NodeKind.TERMINAL,
        priority=-100,
        required=True,
        terminal_outcome=TerminalOutcome.SUCCESS,
    )


def dependency_edge(
    edge_id: str = "agent_before_validator",
    *,
    source: str = "agent",
    target: str = "validator",
) -> EdgeDefinition:
    return EdgeDefinition(edge_id=edge_id, kind=EdgeKind.DEPENDENCY, source=source, target=target)


class GraphModelTests(unittest.TestCase):
    def test_graph_identity_depends_only_on_canonical_definition(self) -> None:
        nodes = (agent_node(), validator_node(), terminal_node())
        edges = (
            dependency_edge(),
            EdgeDefinition(
                "validator_before_complete", EdgeKind.COMPLETION, "validator", "complete"
            ),
        )
        first = GraphDefinition.create(nodes=nodes, edges=edges, completion_node_ids=("complete",))
        second = GraphDefinition.create(
            nodes=tuple(reversed(nodes)),
            edges=tuple(reversed(edges)),
            completion_node_ids=("complete",),
        )
        self.assertEqual(first, second)
        self.assertRegex(first.graph_id, r"^sha256:[0-9a-f]{64}$")

    def test_graph_is_immutable_and_isolated_from_caller_collections(self) -> None:
        nodes = [agent_node(), validator_node(), terminal_node()]
        graph = GraphDefinition.create(nodes=nodes, edges=(), completion_node_ids=("complete",))
        nodes.append(agent_node("late_mutation"))
        self.assertEqual(
            tuple(node.node_id for node in graph.nodes),
            ("agent", "complete", "validator"),
        )
        with self.assertRaises(FrozenInstanceError):
            graph.version = 2  # type: ignore[misc]

    def test_identifiers_must_use_canonical_snake_case(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "invalid node identifier"):
            agent_node("Bad-Node")

    def test_duplicate_node_and_edge_identifiers_are_rejected(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "duplicate node identifier"):
            GraphDefinition.create(nodes=(agent_node(), agent_node()), edges=())
        edge = dependency_edge()
        with self.assertRaisesRegex(GraphModelError, "duplicate edge identifier"):
            GraphDefinition.create(
                nodes=(agent_node(), validator_node()),
                edges=(edge, edge),
            )

    def test_unknown_edge_endpoint_is_rejected(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "unknown target node"):
            GraphDefinition.create(
                nodes=(agent_node(),),
                edges=(dependency_edge(target="missing"),),
            )

    def test_data_flow_ports_must_exist_and_have_matching_schemas(self) -> None:
        mismatched = NodeDefinition(
            node_id="consumer",
            kind=NodeKind.VALIDATOR,
            priority=0,
            required=True,
            input_ports=(Port("candidate", "urn:schema:different"),),
        )
        edge = EdgeDefinition(
            "agent_to_consumer",
            EdgeKind.DATA_FLOW,
            "agent",
            "consumer",
            source_port="result",
            target_port="candidate",
        )
        with self.assertRaisesRegex(GraphModelError, "incompatible port schemas"):
            GraphDefinition.create(nodes=(agent_node(), mismatched), edges=(edge,))

    def test_terminal_outcome_is_required_only_for_terminal_nodes(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "terminal node requires"):
            NodeDefinition("terminal", NodeKind.TERMINAL, 0, True)
        with self.assertRaisesRegex(GraphModelError, "non-terminal node cannot"):
            NodeDefinition(
                "agent",
                NodeKind.AGENT,
                0,
                True,
                terminal_outcome=TerminalOutcome.SUCCESS,
            )

    def test_completion_nodes_must_resolve_to_terminal_nodes(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "completion node must be terminal"):
            GraphDefinition.create(nodes=(agent_node(),), edges=(), completion_node_ids=("agent",))

        with self.assertRaisesRegex(GraphModelError, "unknown completion node"):
            GraphDefinition.create(
                nodes=(terminal_node(),),
                edges=(),
                completion_node_ids=("missing",),
            )

    def test_ports_and_side_effect_contracts_fail_closed(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "schema identifier"):
            Port("result", "")
        with self.assertRaisesRegex(GraphModelError, "side-effect confirmation"):
            NodeDefinition(
                "agent",
                NodeKind.AGENT,
                0,
                True,
                side_effect_confirmation_required=True,
            )
        duplicate = Port("result", "urn:schema:result")
        with self.assertRaisesRegex(GraphModelError, "duplicate output port"):
            NodeDefinition(
                "agent",
                NodeKind.AGENT,
                0,
                True,
                output_ports=(duplicate, duplicate),
            )

    def test_edge_port_declarations_match_edge_kind(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "requires source and target ports"):
            EdgeDefinition("flow", EdgeKind.DATA_FLOW, "agent", "validator")
        with self.assertRaisesRegex(GraphModelError, "only data-flow edges"):
            EdgeDefinition(
                "dependency",
                EdgeKind.DEPENDENCY,
                "agent",
                "validator",
                source_port="result",
            )

    def test_graph_version_and_lookup_are_validated(self) -> None:
        with self.assertRaisesRegex(GraphModelError, "version must be positive"):
            GraphDefinition.create(nodes=(), edges=(), version=0)
        graph = GraphDefinition.create(nodes=(agent_node(),), edges=())
        with self.assertRaisesRegex(GraphModelError, "unknown node"):
            graph.node("missing")
        self.assertEqual(graph.as_json()["graph_id"], graph.graph_id)

    def test_unknown_source_and_missing_data_ports_are_rejected(self) -> None:
        consumer = validator_node("consumer")
        with self.assertRaisesRegex(GraphModelError, "unknown source node"):
            GraphDefinition.create(
                nodes=(consumer,),
                edges=(dependency_edge(source="missing", target="consumer"),),
            )

        missing_source = EdgeDefinition(
            "missing_source_port",
            EdgeKind.DATA_FLOW,
            "agent",
            "consumer",
            source_port="missing",
            target_port="candidate",
        )
        with self.assertRaisesRegex(GraphModelError, "unknown source port"):
            GraphDefinition.create(nodes=(agent_node(), consumer), edges=(missing_source,))

        missing_target = EdgeDefinition(
            "missing_target_port",
            EdgeKind.DATA_FLOW,
            "agent",
            "consumer",
            source_port="result",
            target_port="missing",
        )
        with self.assertRaisesRegex(GraphModelError, "unknown target port"):
            GraphDefinition.create(nodes=(agent_node(), consumer), edges=(missing_target,))

    def test_valid_data_flow_and_serialization(self) -> None:
        edge = EdgeDefinition(
            "agent_to_validator",
            EdgeKind.DATA_FLOW,
            "agent",
            "validator",
            source_port="result",
            target_port="candidate",
        )
        graph = GraphDefinition.create(nodes=(agent_node(), validator_node()), edges=(edge,))
        self.assertEqual(graph.edges[0].as_json()["kind"], "data_flow")


if __name__ == "__main__":
    unittest.main()
