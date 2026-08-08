"""Immutable domain model for graph-native agent execution."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from .canonical_json import canonical_sha256


class GraphModelError(ValueError):
    """Raised when a graph definition violates a structural invariant."""


class NodeKind(StrEnum):
    AGENT = "agent"
    TOOL = "tool"
    VALIDATOR = "validator"
    APPROVAL = "approval"
    JOIN = "join"
    SYNTHESIZER = "synthesizer"
    RECOVERY = "recovery"
    TERMINAL = "terminal"


class EdgeKind(StrEnum):
    DEPENDENCY = "dependency"
    CONTROL_FLOW = "control_flow"
    DATA_FLOW = "data_flow"
    ACTIVATION = "activation"
    INHIBITION = "inhibition"
    APPROVAL = "approval"
    EVIDENCE = "evidence"
    RECOVERY = "recovery"
    COMPLETION = "completion"


class NodeState(StrEnum):
    DECLARED = "declared"
    ELIGIBLE = "eligible"
    ACTIVATED = "activated"
    RUNNING = "running"
    PRODUCED = "produced"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    INHIBITED = "inhibited"
    REJECTED = "rejected"
    FAILED = "failed"
    RECOVERING = "recovering"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    EXHAUSTED = "exhausted"


class TerminalOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    FAILED = "failed"
    REFUSED = "refused"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def _require_identifier(value: str, subject: str) -> None:
    if len(value) > 160 or _IDENTIFIER.fullmatch(value) is None:
        raise GraphModelError(f"invalid {subject} identifier: {value!r}")


@dataclass(frozen=True, slots=True, order=True)
class Port:
    """A named, schema-identified node interface."""

    name: str
    schema_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.name, "port")
        if not self.schema_id:
            raise GraphModelError("port schema identifier must be non-empty")

    def as_json(self) -> dict[str, object]:
        return {"name": self.name, "schema_id": self.schema_id}


@dataclass(frozen=True, slots=True)
class NodeDefinition:
    """A typed executable or control node."""

    node_id: str
    kind: NodeKind
    priority: int
    required: bool
    input_ports: tuple[Port, ...] = ()
    output_ports: tuple[Port, ...] = ()
    terminal_outcome: TerminalOutcome | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.node_id, "node")
        self._validate_ports(self.input_ports, "input")
        self._validate_ports(self.output_ports, "output")
        if self.kind is NodeKind.TERMINAL and self.terminal_outcome is None:
            raise GraphModelError("terminal node requires a terminal outcome")
        if self.kind is not NodeKind.TERMINAL and self.terminal_outcome is not None:
            raise GraphModelError("non-terminal node cannot declare a terminal outcome")

    @staticmethod
    def _validate_ports(ports: tuple[Port, ...], direction: str) -> None:
        names = [port.name for port in ports]
        if len(names) != len(set(names)):
            raise GraphModelError(f"duplicate {direction} port identifier")

    def input_port(self, name: str) -> Port | None:
        return next((port for port in self.input_ports if port.name == name), None)

    def output_port(self, name: str) -> Port | None:
        return next((port for port in self.output_ports if port.name == name), None)

    def as_json(self) -> dict[str, object]:
        return {
            "input_ports": [port.as_json() for port in sorted(self.input_ports)],
            "kind": self.kind.value,
            "node_id": self.node_id,
            "output_ports": [port.as_json() for port in sorted(self.output_ports)],
            "priority": self.priority,
            "required": self.required,
            "terminal_outcome": (
                self.terminal_outcome.value if self.terminal_outcome is not None else None
            ),
        }


@dataclass(frozen=True, slots=True)
class EdgeDefinition:
    """A typed relationship between graph nodes."""

    edge_id: str
    kind: EdgeKind
    source: str
    target: str
    source_port: str | None = None
    target_port: str | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        _require_identifier(self.edge_id, "edge")
        _require_identifier(self.source, "source node")
        _require_identifier(self.target, "target node")
        if self.source_port is not None:
            _require_identifier(self.source_port, "source port")
        if self.target_port is not None:
            _require_identifier(self.target_port, "target port")
        if self.kind is EdgeKind.DATA_FLOW:
            if self.source_port is None or self.target_port is None:
                raise GraphModelError("data-flow edge requires source and target ports")
        elif self.source_port is not None or self.target_port is not None:
            raise GraphModelError("only data-flow edges may declare ports")

    def as_json(self) -> dict[str, object]:
        return {
            "edge_id": self.edge_id,
            "kind": self.kind.value,
            "priority": self.priority,
            "source": self.source,
            "source_port": self.source_port,
            "target": self.target,
            "target_port": self.target_port,
        }


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    """An immutable, content-addressed execution graph."""

    HASH_PREFIX: ClassVar[str] = "sha256:"

    graph_id: str
    version: int
    parent_graph_id: str | None
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    completion_node_ids: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        nodes: Iterable[NodeDefinition],
        edges: Iterable[EdgeDefinition],
        completion_node_ids: Iterable[str] = (),
        version: int = 1,
        parent_graph_id: str | None = None,
    ) -> GraphDefinition:
        if version < 1:
            raise GraphModelError("graph version must be positive")
        canonical_nodes = tuple(sorted(nodes, key=lambda node: node.node_id))
        canonical_edges = tuple(sorted(edges, key=lambda edge: edge.edge_id))
        completion_ids = tuple(sorted(completion_node_ids))
        cls._reject_duplicates((node.node_id for node in canonical_nodes), "node")
        cls._reject_duplicates((edge.edge_id for edge in canonical_edges), "edge")
        cls._reject_duplicates(iter(completion_ids), "completion node")
        node_by_id = {node.node_id: node for node in canonical_nodes}
        for edge in canonical_edges:
            cls._validate_edge(edge, node_by_id)
        for node_id in completion_ids:
            node = node_by_id.get(node_id)
            if node is None:
                raise GraphModelError(f"unknown completion node: {node_id}")
            if node.kind is not NodeKind.TERMINAL:
                raise GraphModelError(f"completion node must be terminal: {node_id}")
        content: dict[str, object] = {
            "completion_node_ids": list(completion_ids),
            "edges": [edge.as_json() for edge in canonical_edges],
            "nodes": [node.as_json() for node in canonical_nodes],
            "parent_graph_id": parent_graph_id,
            "version": version,
        }
        return cls(
            graph_id=f"{cls.HASH_PREFIX}{canonical_sha256(content)}",
            version=version,
            parent_graph_id=parent_graph_id,
            nodes=canonical_nodes,
            edges=canonical_edges,
            completion_node_ids=completion_ids,
        )

    @staticmethod
    def _reject_duplicates(values: Iterable[str], subject: str) -> None:
        seen: set[str] = set()
        for value in values:
            if value in seen:
                raise GraphModelError(f"duplicate {subject} identifier: {value}")
            seen.add(value)

    @staticmethod
    def _validate_edge(
        edge: EdgeDefinition,
        node_by_id: dict[str, NodeDefinition],
    ) -> None:
        source = node_by_id.get(edge.source)
        if source is None:
            raise GraphModelError(f"unknown source node for edge {edge.edge_id}: {edge.source}")
        target = node_by_id.get(edge.target)
        if target is None:
            raise GraphModelError(f"unknown target node for edge {edge.edge_id}: {edge.target}")
        if edge.kind is not EdgeKind.DATA_FLOW:
            return
        assert edge.source_port is not None
        assert edge.target_port is not None
        source_port = source.output_port(edge.source_port)
        if source_port is None:
            raise GraphModelError(
                f"unknown source port for edge {edge.edge_id}: {edge.source_port}"
            )
        target_port = target.input_port(edge.target_port)
        if target_port is None:
            raise GraphModelError(
                f"unknown target port for edge {edge.edge_id}: {edge.target_port}"
            )
        if source_port.schema_id != target_port.schema_id:
            raise GraphModelError(
                f"incompatible port schemas for edge {edge.edge_id}: "
                f"{source_port.schema_id} != {target_port.schema_id}"
            )

    def node(self, node_id: str) -> NodeDefinition:
        node = next((item for item in self.nodes if item.node_id == node_id), None)
        if node is None:
            raise GraphModelError(f"unknown node: {node_id}")
        return node

    def as_json(self) -> dict[str, object]:
        return {
            "completion_node_ids": list(self.completion_node_ids),
            "edges": [edge.as_json() for edge in self.edges],
            "graph_id": self.graph_id,
            "nodes": [node.as_json() for node in self.nodes],
            "parent_graph_id": self.parent_graph_id,
            "version": self.version,
        }
