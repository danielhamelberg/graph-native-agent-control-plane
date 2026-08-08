"""Effect boundaries for the graph-native control plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .canonical_json import JsonValue
from .events import ExecutionEvent
from .model import NodeDefinition
from .reducer import MaterializedState


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Typed result returned by a validator adapter."""

    passed: bool
    findings: tuple[str, ...]


class EventStore(Protocol):
    """Append-only persistence for execution events."""

    def append(self, event: ExecutionEvent) -> None: ...

    def read(self, execution_id: str) -> tuple[ExecutionEvent, ...]: ...


class AgentPort(Protocol):
    """Boundary for agent, tool, synthesis, join, and recovery work."""

    def invoke(self, node: NodeDefinition, objective: str) -> JsonValue: ...


class ValidatorPort(Protocol):
    """Boundary for independent validation."""

    def validate(self, node: NodeDefinition, state: MaterializedState) -> ValidationResult: ...


class AuthorizationPort(Protocol):
    """Boundary for explicit approval decisions."""

    def authorize(self, node: NodeDefinition, state: MaterializedState) -> bool: ...
