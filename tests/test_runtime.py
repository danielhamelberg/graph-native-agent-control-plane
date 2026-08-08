from __future__ import annotations

import unittest

from graph_native_agent_control_plane.canonical_json import JsonValue
from graph_native_agent_control_plane.model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    NodeDefinition,
)
from graph_native_agent_control_plane.ports import ValidationResult
from graph_native_agent_control_plane.reducer import MaterializedState
from graph_native_agent_control_plane.runtime import (
    ControlPlaneRuntime,
    InMemoryEventStore,
    RuntimeExecutionError,
)
from tests.test_model import agent_node, terminal_node, validator_node


class EchoAgent:
    def invoke(self, node: NodeDefinition, objective: str) -> JsonValue:
        return {"node": node.node_id, "objective": objective}


class InvalidAgent:
    def invoke(self, node: NodeDefinition, objective: str) -> JsonValue:
        del node, objective
        return object()  # type: ignore[return-value]


class AcceptValidator:
    def validate(self, node: NodeDefinition, state: MaterializedState) -> ValidationResult:
        del node, state
        return ValidationResult(passed=True, findings=())


class AllowAuthorization:
    def authorize(self, node: NodeDefinition, state: MaterializedState) -> bool:
        del node, state
        return True


def runtime_graph() -> GraphDefinition:
    return GraphDefinition.create(
        nodes=(agent_node(), validator_node("quality"), terminal_node()),
        edges=(
            EdgeDefinition("agent_before_quality", EdgeKind.DEPENDENCY, "agent", "quality"),
            EdgeDefinition("quality_before_complete", EdgeKind.COMPLETION, "quality", "complete"),
        ),
        completion_node_ids=("complete",),
    )


class RuntimeTests(unittest.TestCase):
    def test_runtime_executes_through_ports_and_graph_authorizes_completion(self) -> None:
        store = InMemoryEventStore()
        runtime = ControlPlaneRuntime(
            graph=runtime_graph(),
            execution_id="execution_one",
            event_store=store,
            agent_port=EchoAgent(),
            validator_port=AcceptValidator(),
            authorization_port=AllowAuthorization(),
        )
        result = runtime.run("Return every valid result.")
        self.assertTrue(result.completion.authorized)
        self.assertEqual(
            result.state.authoritative_output("agent"),
            b'{"node":"agent","objective":"Return every valid result."}\n',
        )
        self.assertEqual(result.events, store.read("execution_one"))

    def test_off_graph_node_execution_is_rejected(self) -> None:
        runtime = ControlPlaneRuntime(
            graph=runtime_graph(),
            execution_id="execution_one",
            event_store=InMemoryEventStore(),
            agent_port=EchoAgent(),
            validator_port=AcceptValidator(),
            authorization_port=AllowAuthorization(),
        )
        state = MaterializedState.initial(runtime_graph(), "execution_one")
        with self.assertRaisesRegex(RuntimeExecutionError, "not eligible"):
            runtime.execute_node(
                state,
                "quality",
                "objective",
                expected_graph_id=runtime_graph().graph_id,
            )

    def test_stale_graph_result_is_rejected_before_adapter_execution(self) -> None:
        runtime = ControlPlaneRuntime(
            graph=runtime_graph(),
            execution_id="execution_one",
            event_store=InMemoryEventStore(),
            agent_port=EchoAgent(),
            validator_port=AcceptValidator(),
            authorization_port=AllowAuthorization(),
        )
        state = MaterializedState.initial(runtime_graph(), "execution_one")
        with self.assertRaisesRegex(RuntimeExecutionError, "stale graph"):
            runtime.execute_node(state, "agent", "objective", expected_graph_id="stale")

    def test_non_json_adapter_output_is_rejected_without_output_event(self) -> None:
        store = InMemoryEventStore()
        runtime = ControlPlaneRuntime(
            graph=runtime_graph(),
            execution_id="execution_one",
            event_store=store,
            agent_port=InvalidAgent(),
            validator_port=AcceptValidator(),
            authorization_port=AllowAuthorization(),
        )
        with self.assertRaisesRegex(RuntimeExecutionError, "adapter output"):
            runtime.run("objective")
        event_kinds = tuple(event.kind.value for event in store.read("execution_one"))
        self.assertNotIn("output_recorded", event_kinds)

    def test_execution_step_budget_is_fail_closed(self) -> None:
        graph = GraphDefinition.create(
            nodes=(agent_node("one"), agent_node("two"), terminal_node()),
            edges=(),
            completion_node_ids=("complete",),
        )
        runtime = ControlPlaneRuntime(
            graph=graph,
            execution_id="execution_one",
            event_store=InMemoryEventStore(),
            agent_port=EchoAgent(),
            validator_port=AcceptValidator(),
            authorization_port=AllowAuthorization(),
            max_steps=1,
        )
        with self.assertRaisesRegex(RuntimeExecutionError, "step budget"):
            runtime.run("objective")


if __name__ == "__main__":
    unittest.main()
