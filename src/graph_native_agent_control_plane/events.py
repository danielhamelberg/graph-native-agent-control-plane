"""Typed, tamper-evident execution events."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from .canonical_json import JsonValue, canonical_bytes, canonical_sha256


class EventKind(StrEnum):
    NODE_TRANSITION = "node_transition"
    OUTPUT_RECORDED = "output_recorded"
    EVIDENCE_RECORDED = "evidence_recorded"
    APPROVAL_RECORDED = "approval_recorded"
    CONFLICT_OPENED = "conflict_opened"
    CONFLICT_RESOLVED = "conflict_resolved"
    SIDE_EFFECT_CONFIRMED = "side_effect_confirmed"
    NODE_INVALIDATED = "node_invalidated"


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """One immutable event in an execution's hash chain."""

    execution_id: str
    graph_id: str
    sequence: int
    actor: str
    kind: EventKind
    node_id: str | None
    payload_bytes: bytes
    previous_event_hash: str | None
    event_hash: str

    @classmethod
    def create(
        cls,
        *,
        execution_id: str,
        graph_id: str,
        sequence: int,
        actor: str,
        kind: EventKind,
        node_id: str | None,
        payload: JsonValue,
        previous_event_hash: str | None,
    ) -> ExecutionEvent:
        payload_bytes = canonical_bytes(payload)
        content = cls._hash_content(
            execution_id=execution_id,
            graph_id=graph_id,
            sequence=sequence,
            actor=actor,
            kind=kind,
            node_id=node_id,
            payload_bytes=payload_bytes,
            previous_event_hash=previous_event_hash,
        )
        return cls(
            execution_id=execution_id,
            graph_id=graph_id,
            sequence=sequence,
            actor=actor,
            kind=kind,
            node_id=node_id,
            payload_bytes=payload_bytes,
            previous_event_hash=previous_event_hash,
            event_hash=canonical_sha256(content),
        )

    @staticmethod
    def _hash_content(
        *,
        execution_id: str,
        graph_id: str,
        sequence: int,
        actor: str,
        kind: EventKind,
        node_id: str | None,
        payload_bytes: bytes,
        previous_event_hash: str | None,
    ) -> dict[str, object]:
        return {
            "actor": actor,
            "execution_id": execution_id,
            "graph_id": graph_id,
            "kind": kind.value,
            "node_id": node_id,
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "previous_event_hash": previous_event_hash,
            "sequence": sequence,
        }

    def expected_hash(self) -> str:
        """Recompute the event hash from the event's immutable fields."""

        return canonical_sha256(
            self._hash_content(
                execution_id=self.execution_id,
                graph_id=self.graph_id,
                sequence=self.sequence,
                actor=self.actor,
                kind=self.kind,
                node_id=self.node_id,
                payload_bytes=self.payload_bytes,
                previous_event_hash=self.previous_event_hash,
            )
        )
