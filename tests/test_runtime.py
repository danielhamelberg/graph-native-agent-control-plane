from __future__ import annotations

import unittest
from dataclasses import replace

from graph_native_agent_control_plane.canonical_json import JsonValue
from graph_native_agent_control_plane.events import EventKind, ExecutionEvent
from graph_native_agent_control_plane.model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    NodeDefinition,
    NodeKind,
    NodeState,
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


class StaticAgent:
    def __init__(self, output: JsonValue) -> None:
        self.output = output

    def invoke(self, node: NodeDefinition, objective: str) -> JsonValue:
        del node, objective
        return self.output


class AcceptValidator:
    def validate(self, node: NodeDefinition, state: MaterializedState) -> ValidationResult:
        del node, state
        return ValidationResult(passed=True, findings=())


class RejectValidator:
    def validate(self, node: NodeDefinition, state: MaterializedState) -> ValidationResult:
        del node, state
        return ValidationResult(passed=False, findings=("rejected",))


class AllowAuthorization:
    def authorize(self, node: NodeDefinition, state: MaterializedState) -> bool:
        del node, state
        return True


class DenyAuthorization:
    def authorize(self, node: NodeDefinition, state: MaterializedState) -> bool:
        del node, state
        return False


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
    def make_runtime(
        self,
        graph: GraphDefinition,
        *,
        store: InMemoryEventStore | None = None,
        agent: EchoAgent | InvalidAgent | StaticAgent | None = None,
        validator: AcceptValidator | RejectValidator | None = None,
        authorization: AllowAuthorization | DenyAuthorization | None = None,
        max_steps: int = 64,
    ) -> ControlPlaneRuntime:
        return ControlPlaneRuntime(
            graph=graph,
            execution_id="execution_one",
            event_store=store if store is not None else InMemoryEventStore(),
            agent_port=agent if agent is not None else EchoAgent(),
            validator_port=validator if validator is not None else AcceptValidator(),
            authorization_port=(
                authorization if authorization is not None else AllowAuthorization()
            ),
            max_steps=max_steps,
        )

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

    def test_event_store_rejects_sequence_chain_and_hash_tampering(self) -> None:
        graph = runtime_graph()
        store = InMemoryEventStore()
        wrong_sequence = ExecutionEvent.create(
            execution_id="execution_one",
            graph_id=graph.graph_id,
            sequence=2,
            actor="tester",
            kind=EventKind.NODE_TRANSITION,
            node_id="agent",
            payload={"to": "eligible"},
            previous_event_hash=None,
        )
        with self.assertRaisesRegex(RuntimeExecutionError, "expected sequence"):
            store.append(wrong_sequence)

        broken_chain = ExecutionEvent.create(
            execution_id="execution_one",
            graph_id=graph.graph_id,
            sequence=1,
            actor="tester",
            kind=EventKind.NODE_TRANSITION,
            node_id="agent",
            payload={"to": "eligible"},
            previous_event_hash="wrong",
        )
        with self.assertRaisesRegex(RuntimeExecutionError, "broken hash chain"):
            store.append(broken_chain)

        valid = replace(broken_chain, previous_event_hash=None)
        valid = replace(valid, event_hash=valid.expected_hash())
        tampered = replace(valid, payload_bytes=b'{"to":"running"}\n')
        with self.assertRaisesRegex(RuntimeExecutionError, "tampered event"):
            store.append(tampered)
        self.assertEqual(store.read("missing"), ())

    def test_runtime_step_budget_must_be_positive_integer(self) -> None:
        for invalid in (0, True):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                RuntimeExecutionError, "budget must be positive"
            ):
                self.make_runtime(runtime_graph(), max_steps=invalid)

    def test_terminal_node_cannot_be_executed_as_work(self) -> None:
        graph = GraphDefinition.create(
            nodes=(terminal_node(),),
            edges=(),
            completion_node_ids=("complete",),
        )
        runtime = self.make_runtime(graph)
        state = MaterializedState.initial(graph, "execution_one")
        with self.assertRaisesRegex(RuntimeExecutionError, "completion authority"):
            runtime.execute_node(
                state,
                "complete",
                "objective",
                expected_graph_id=graph.graph_id,
            )

    def test_validator_rejection_is_recorded_without_completion(self) -> None:
        graph = GraphDefinition.create(
            nodes=(validator_node("quality"), terminal_node()),
            edges=(),
            completion_node_ids=("complete",),
        )
        result = self.make_runtime(graph, validator=RejectValidator()).run("objective")
        self.assertFalse(result.completion.authorized)
        self.assertEqual(result.state.node_state("quality"), NodeState.REJECTED)

    def test_approval_outcomes_are_explicit(self) -> None:
        approval = NodeDefinition("gate", NodeKind.APPROVAL, 0, True)
        graph = GraphDefinition.create(
            nodes=(approval, terminal_node()),
            edges=(),
            completion_node_ids=("complete",),
        )
        allowed = self.make_runtime(graph).run("objective")
        self.assertTrue(allowed.completion.authorized)
        self.assertEqual(allowed.state.approvals, ("gate",))

        denied = self.make_runtime(graph, authorization=DenyAuthorization()).run("objective")
        self.assertFalse(denied.completion.authorized)
        self.assertEqual(denied.state.node_state("gate"), NodeState.REJECTED)

    def test_side_effect_confirmation_is_required_and_recorded(self) -> None:
        tool = NodeDefinition(
            "tool",
            NodeKind.TOOL,
            0,
            True,
            side_effect_confirmation_required=True,
        )
        graph = GraphDefinition.create(
            nodes=(tool, terminal_node()),
            edges=(),
            completion_node_ids=("complete",),
        )
        outputs: tuple[JsonValue, ...] = ("not_an_object", {"confirmed": False})
        for output in outputs:
            with self.subTest(output=output):
                rejected = self.make_runtime(graph, agent=StaticAgent(output)).run("objective")
                self.assertEqual(rejected.state.node_state("tool"), NodeState.REJECTED)

        accepted = self.make_runtime(
            graph,
            agent=StaticAgent({"confirmed": True}),
        ).run("objective")
        self.assertTrue(accepted.completion.authorized)
        self.assertEqual(accepted.state.side_effect_confirmations, ("tool",))

    def test_run_returns_at_authorized_start_or_quiescence(self) -> None:
        complete_only = GraphDefinition.create(
            nodes=(terminal_node(),),
            edges=(),
            completion_node_ids=("complete",),
        )
        self.assertTrue(self.make_runtime(complete_only).run("objective").completion.authorized)

        blocked = GraphDefinition.create(
            nodes=(agent_node(), terminal_node()),
            edges=(
                EdgeDefinition(
                    "complete_before_agent",
                    EdgeKind.DEPENDENCY,
                    "complete",
                    "agent",
                ),
            ),
            completion_node_ids=("complete",),
        )
        quiescent = self.make_runtime(blocked).run("objective")
        self.assertFalse(quiescent.completion.authorized)
        self.assertEqual(quiescent.state.node_state("agent"), NodeState.DECLARED)


if __name__ == "__main__":
    unittest.main()
