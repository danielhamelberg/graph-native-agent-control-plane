from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import TypeGuard

from jsonschema import Draft202012Validator, FormatChecker

from graph_native_agent_control_plane.canonical_json import (
    JsonValue,
    canonical_bytes,
    loads_strict,
)
from graph_native_agent_control_plane.completion import evaluate_completion
from graph_native_agent_control_plane.events import EventKind, ExecutionEvent
from graph_native_agent_control_plane.model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    NodeDefinition,
    NodeKind,
    Port,
    TerminalOutcome,
)
from graph_native_agent_control_plane.reducer import reduce_events

ROOT = Path(__file__).resolve().parents[1]


def load_object(path: Path) -> dict[str, JsonValue]:
    value = loads_strict(path.read_bytes())
    if not isinstance(value, dict):
        raise AssertionError(f"expected object: {path}")
    return value


def is_object(value: JsonValue) -> TypeGuard[dict[str, JsonValue]]:
    return isinstance(value, dict)


def require_object(value: JsonValue) -> dict[str, JsonValue]:
    if not is_object(value):
        raise AssertionError("expected object")
    return value


def require_list(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise AssertionError("expected list")
    return value


def require_str(value: JsonValue) -> str:
    if not isinstance(value, str):
        raise AssertionError("expected string")
    return value


def require_optional_str(value: JsonValue) -> str | None:
    if value is not None and not isinstance(value, str):
        raise AssertionError("expected string or null")
    return value


def require_int(value: JsonValue) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError("expected integer")
    return value


def require_bool(value: JsonValue) -> bool:
    if not isinstance(value, bool):
        raise AssertionError("expected boolean")
    return value


def require_ports(value: JsonValue) -> tuple[Port, ...]:
    ports: list[Port] = []
    for item in require_list(value):
        raw = require_object(item)
        ports.append(Port(require_str(raw["name"]), require_str(raw["schema_id"])))
    return tuple(ports)


def graph_from_example(value: dict[str, JsonValue]) -> GraphDefinition:
    raw_nodes = require_list(value["nodes"])
    raw_edges = require_list(value["edges"])
    raw_completion = require_list(value["completion_node_ids"])
    nodes: list[NodeDefinition] = []
    for raw in raw_nodes:
        node = require_object(raw)
        outcome = require_optional_str(node["terminal_outcome"])
        nodes.append(
            NodeDefinition(
                node_id=require_str(node["node_id"]),
                kind=NodeKind(require_str(node["kind"])),
                priority=require_int(node["priority"]),
                required=require_bool(node["required"]),
                input_ports=require_ports(node["input_ports"]),
                output_ports=require_ports(node["output_ports"]),
                terminal_outcome=TerminalOutcome(outcome) if outcome is not None else None,
                evidence_required=require_bool(node["evidence_required"]),
                side_effect_confirmation_required=require_bool(
                    node["side_effect_confirmation_required"]
                ),
            )
        )
    edges: list[EdgeDefinition] = []
    for raw in raw_edges:
        edge = require_object(raw)
        edges.append(
            EdgeDefinition(
                edge_id=require_str(edge["edge_id"]),
                kind=EdgeKind(require_str(edge["kind"])),
                source=require_str(edge["source"]),
                target=require_str(edge["target"]),
                source_port=require_optional_str(edge["source_port"]),
                target_port=require_optional_str(edge["target_port"]),
                priority=require_int(edge["priority"]),
            )
        )
    graph = GraphDefinition.create(
        nodes=nodes,
        edges=edges,
        completion_node_ids=(require_str(item) for item in raw_completion),
        version=require_int(value["version"]),
        parent_graph_id=require_optional_str(value["parent_graph_id"]),
    )
    assert graph.graph_id == require_str(value["graph_id"])
    return graph


def events_from_example(value: dict[str, JsonValue]) -> tuple[ExecutionEvent, ...]:
    raw_events = require_list(value["events"])
    events: list[ExecutionEvent] = []
    for raw in raw_events:
        event = require_object(raw)
        events.append(
            ExecutionEvent(
                execution_id=require_str(event["execution_id"]),
                graph_id=require_str(event["graph_id"]),
                sequence=require_int(event["sequence"]),
                actor=require_str(event["actor"]),
                kind=EventKind(require_str(event["kind"])),
                node_id=require_optional_str(event["node_id"]),
                payload_bytes=canonical_bytes(event["payload"]),
                previous_event_hash=require_optional_str(event["previous_event_hash"]),
                event_hash=require_str(event["event_hash"]),
            )
        )
    return tuple(events)


class SchemaAndReplayTests(unittest.TestCase):
    def test_schemas_are_valid_draft_2020_12_documents(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(path=path.name):
                Draft202012Validator.check_schema(load_object(path))

    def test_examples_validate_with_format_assertion(self) -> None:
        cases = (
            ("graph-definition.schema.json", "completeness-graph.json"),
            ("execution-record.schema.json", "replay.json"),
        )
        for schema_name, example_name in cases:
            with self.subTest(example=example_name):
                validator = Draft202012Validator(
                    load_object(ROOT / "schemas" / schema_name),
                    format_checker=FormatChecker(),
                )
                validator.validate(  # pyright: ignore[reportUnknownMemberType]
                    load_object(ROOT / "examples" / example_name)
                )

    def test_checked_in_event_record_replays_to_graph_authorized_completion(self) -> None:
        graph = graph_from_example(load_object(ROOT / "examples" / "completeness-graph.json"))
        record = load_object(ROOT / "examples" / "replay.json")
        events = events_from_example(record)
        state = reduce_events(graph, require_str(record["execution_id"]), events)
        decision = evaluate_completion(graph, state)
        self.assertTrue(decision.authorized)
        self.assertIsNotNone(decision.outcome)
        assert decision.outcome is not None
        completion = require_object(record["completion"])
        self.assertEqual(decision.outcome.value, require_str(completion["outcome"]))

    def test_example_hashes_are_stable_across_hash_seeds(self) -> None:
        code = (
            "import hashlib,pathlib;"
            "root=pathlib.Path('examples');"
            "print('|'.join(hashlib.sha256(p.read_bytes()).hexdigest() "
            "for p in sorted(root.glob('*.json'))))"
        )
        outputs: list[str] = []
        for seed in ("0", "1", "123"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            outputs.append(completed.stdout)
        self.assertEqual(len(set(outputs)), 1)


if __name__ == "__main__":
    unittest.main()
