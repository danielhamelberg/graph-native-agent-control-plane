"""Imperative shell that routes all accepted work through typed graph events."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_json import CanonicalJsonError, JsonValue, canonical_bytes
from .completion import CompletionDecision, evaluate_completion
from .events import EventKind, ExecutionEvent
from .model import GraphDefinition, NodeDefinition, NodeKind, NodeState
from .ports import AgentPort, AuthorizationPort, EventStore, ValidatorPort
from .reducer import MaterializedState, reduce_event, reduce_events
from .scheduler import eligible_nodes


class RuntimeExecutionError(RuntimeError):
    """Raised when the imperative runtime must fail closed."""


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Final state, completion decision, and immutable event view."""

    state: MaterializedState
    completion: CompletionDecision
    events: tuple[ExecutionEvent, ...]


class InMemoryEventStore:
    """Small append-only event store for deterministic examples and tests."""

    def __init__(self) -> None:
        self._events: dict[str, list[ExecutionEvent]] = {}

    def append(self, event: ExecutionEvent) -> None:
        events = self._events.setdefault(event.execution_id, [])
        expected_sequence = len(events) + 1
        if event.sequence != expected_sequence:
            raise RuntimeExecutionError(
                f"event store expected sequence {expected_sequence}, received {event.sequence}"
            )
        previous_hash = events[-1].event_hash if events else None
        if event.previous_event_hash != previous_hash:
            raise RuntimeExecutionError("event store rejected a broken hash chain")
        if event.event_hash != event.expected_hash():
            raise RuntimeExecutionError("event store rejected a tampered event")
        events.append(event)

    def read(self, execution_id: str) -> tuple[ExecutionEvent, ...]:
        return tuple(self._events.get(execution_id, ()))


class ControlPlaneRuntime:
    """Bounded orchestration shell over the pure graph core."""

    def __init__(
        self,
        *,
        graph: GraphDefinition,
        execution_id: str,
        event_store: EventStore,
        agent_port: AgentPort,
        validator_port: ValidatorPort,
        authorization_port: AuthorizationPort,
        max_steps: int = 64,
    ) -> None:
        if isinstance(max_steps, bool) or max_steps < 1:
            raise RuntimeExecutionError("execution step budget must be positive")
        self.graph = graph
        self.execution_id = execution_id
        self.event_store = event_store
        self.agent_port = agent_port
        self.validator_port = validator_port
        self.authorization_port = authorization_port
        self.max_steps = max_steps

    def _emit(
        self,
        state: MaterializedState,
        *,
        actor: str,
        kind: EventKind,
        node_id: str,
        payload: JsonValue,
    ) -> MaterializedState:
        event = ExecutionEvent.create(
            execution_id=state.execution_id,
            graph_id=state.graph_id,
            sequence=state.next_sequence,
            actor=actor,
            kind=kind,
            node_id=node_id,
            payload=payload,
            previous_event_hash=state.last_event_hash,
        )
        updated = reduce_event(self.graph, state, event)
        self.event_store.append(event)
        return updated

    def _transition(
        self,
        state: MaterializedState,
        node_id: str,
        target: NodeState,
    ) -> MaterializedState:
        return self._emit(
            state,
            actor="orchestrator",
            kind=EventKind.NODE_TRANSITION,
            node_id=node_id,
            payload={"to": target.value},
        )

    def _record_output(
        self,
        state: MaterializedState,
        node: NodeDefinition,
        output: JsonValue,
    ) -> MaterializedState:
        try:
            canonical_bytes(output)
        except CanonicalJsonError as exc:
            raise RuntimeExecutionError(f"adapter output is not valid JSON: {exc}") from None
        return self._emit(
            state,
            actor=node.node_id,
            kind=EventKind.OUTPUT_RECORDED,
            node_id=node.node_id,
            payload=output,
        )

    def execute_node(
        self,
        state: MaterializedState,
        node_id: str,
        objective: str,
        *,
        expected_graph_id: str,
    ) -> MaterializedState:
        """Execute one currently eligible node against an explicit graph version."""

        if expected_graph_id != self.graph.graph_id or state.graph_id != self.graph.graph_id:
            raise RuntimeExecutionError("refusing node execution against a stale graph")
        if node_id not in eligible_nodes(self.graph, state):
            raise RuntimeExecutionError(f"node is not eligible for execution: {node_id}")
        node = self.graph.node(node_id)
        if node.kind is NodeKind.TERMINAL:
            raise RuntimeExecutionError("terminal nodes require graph-level completion authority")

        for target in (NodeState.ELIGIBLE, NodeState.ACTIVATED, NodeState.RUNNING):
            state = self._transition(state, node_id, target)

        if node.kind is NodeKind.VALIDATOR:
            validation = self.validator_port.validate(node, state)
            output: JsonValue = {
                "findings": list(validation.findings),
                "passed": validation.passed,
            }
            state = self._record_output(state, node, output)
            state = self._transition(state, node_id, NodeState.PRODUCED)
            state = self._transition(state, node_id, NodeState.VALIDATING)
            terminal_state = NodeState.ACCEPTED if validation.passed else NodeState.REJECTED
            return self._transition(state, node_id, terminal_state)

        if node.kind is NodeKind.APPROVAL:
            approved = self.authorization_port.authorize(node, state)
            state = self._record_output(state, node, {"approved": approved})
            state = self._transition(state, node_id, NodeState.PRODUCED)
            state = self._transition(state, node_id, NodeState.VALIDATING)
            state = self._emit(
                state,
                actor=node.node_id,
                kind=EventKind.APPROVAL_RECORDED,
                node_id=node_id,
                payload={"approved": approved},
            )
            terminal_state = NodeState.ACCEPTED if approved else NodeState.REJECTED
            return self._transition(state, node_id, terminal_state)

        output = self.agent_port.invoke(node, objective)
        state = self._record_output(state, node, output)
        state = self._transition(state, node_id, NodeState.PRODUCED)
        state = self._transition(state, node_id, NodeState.VALIDATING)
        if node.side_effect_confirmation_required:
            if not isinstance(output, dict) or output.get("confirmed") is not True:
                return self._transition(state, node_id, NodeState.REJECTED)
            state = self._emit(
                state,
                actor=node.node_id,
                kind=EventKind.SIDE_EFFECT_CONFIRMED,
                node_id=node_id,
                payload={"confirmed": True},
            )
        return self._transition(state, node_id, NodeState.ACCEPTED)

    def run(self, objective: str) -> RuntimeResult:
        """Run eligible nodes until completion, quiescence, or the step budget."""

        existing = self.event_store.read(self.execution_id)
        state = reduce_events(self.graph, self.execution_id, existing)
        steps = 0
        while True:
            completion = evaluate_completion(self.graph, state)
            if completion.authorized:
                return RuntimeResult(state, completion, self.event_store.read(self.execution_id))
            candidates = tuple(
                node_id
                for node_id in eligible_nodes(self.graph, state)
                if self.graph.node(node_id).kind is not NodeKind.TERMINAL
            )
            if not candidates:
                return RuntimeResult(state, completion, self.event_store.read(self.execution_id))
            if steps >= self.max_steps:
                raise RuntimeExecutionError(
                    f"execution step budget exhausted after {self.max_steps} nodes"
                )
            state = self.execute_node(
                state,
                candidates[0],
                objective,
                expected_graph_id=self.graph.graph_id,
            )
            steps += 1
