"""Authorized immutable graph rewriting with deterministic invalidation."""

from __future__ import annotations

from dataclasses import dataclass

from .model import (
    EdgeDefinition,
    EdgeKind,
    GraphDefinition,
    GraphModelError,
    NodeDefinition,
    NodeState,
)
from .reducer import MaterializedState


class RewriteError(ValueError):
    """Raised when a graph rewrite is unauthorized, unsafe, or structurally invalid."""


@dataclass(frozen=True, slots=True)
class AddNode:
    node: NodeDefinition


@dataclass(frozen=True, slots=True)
class AddEdge:
    edge: EdgeDefinition


@dataclass(frozen=True, slots=True)
class RemoveNode:
    node_id: str


@dataclass(frozen=True, slots=True)
class RemoveEdge:
    edge_id: str


@dataclass(frozen=True, slots=True)
class ReplaceNode:
    node: NodeDefinition


type RewriteOperation = AddNode | AddEdge | RemoveNode | RemoveEdge | ReplaceNode


@dataclass(frozen=True, slots=True)
class RewriteResult:
    graph: GraphDefinition
    invalidated_nodes: tuple[str, ...]
    invalidated_approvals: tuple[str, ...]


_UNEXECUTED_STATES = frozenset(
    {NodeState.DECLARED, NodeState.ELIGIBLE, NodeState.BLOCKED, NodeState.INHIBITED}
)
_ACYCLIC_EDGE_KINDS = frozenset(
    {
        EdgeKind.DEPENDENCY,
        EdgeKind.CONTROL_FLOW,
        EdgeKind.DATA_FLOW,
        EdgeKind.ACTIVATION,
        EdgeKind.APPROVAL,
        EdgeKind.EVIDENCE,
        EdgeKind.COMPLETION,
    }
)


def _descendants(
    roots: set[str],
    old_graph: GraphDefinition,
    new_graph: GraphDefinition,
) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for edge in (*old_graph.edges, *new_graph.edges):
        adjacency.setdefault(edge.source, set()).add(edge.target)
    affected = set(roots)
    frontier = sorted(roots, reverse=True)
    while frontier:
        source = frontier.pop()
        for target in sorted(adjacency.get(source, ())):
            if target not in affected:
                affected.add(target)
                frontier.append(target)
    return affected


def _reject_cycles(graph: GraphDefinition) -> None:
    adjacency: dict[str, list[str]] = {node.node_id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.kind in _ACYCLIC_EDGE_KINDS:
            adjacency[edge.source].append(edge.target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise RewriteError(f"rewrite introduces a directed cycle at node: {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in sorted(adjacency[node_id]):
            visit(target)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(adjacency):
        visit(node_id)


def apply_rewrite(
    graph: GraphDefinition,
    state: MaterializedState,
    *,
    operations: tuple[RewriteOperation, ...],
    authority: str,
    max_operations: int = 32,
) -> RewriteResult:
    """Apply bounded typed operations and return a new graph plus invalidations."""

    if not authority.strip():
        raise RewriteError("rewrite authority must be non-empty")
    if isinstance(max_operations, bool) or max_operations < 1:
        raise RewriteError("rewrite operation limit must be positive")
    if len(operations) > max_operations:
        raise RewriteError(
            f"rewrite operation limit exceeded: {len(operations)} > {max_operations}"
        )
    if not operations:
        raise RewriteError("rewrite requires at least one operation")
    if state.graph_id != graph.graph_id:
        raise RewriteError("materialized state references a different graph")

    nodes = {node.node_id: node for node in graph.nodes}
    edges = {edge.edge_id: edge for edge in graph.edges}
    completion_ids = set(graph.completion_node_ids)
    affected_roots: set[str] = set()

    for operation in operations:
        if isinstance(operation, AddNode):
            if operation.node.node_id in nodes:
                raise RewriteError(f"node already exists: {operation.node.node_id}")
            nodes[operation.node.node_id] = operation.node
        elif isinstance(operation, AddEdge):
            if operation.edge.edge_id in edges:
                raise RewriteError(f"edge already exists: {operation.edge.edge_id}")
            edges[operation.edge.edge_id] = operation.edge
            affected_roots.add(operation.edge.target)
        elif isinstance(operation, RemoveNode):
            if operation.node_id not in nodes:
                raise RewriteError(f"unknown node: {operation.node_id}")
            if operation.node_id in completion_ids:
                raise RewriteError(f"completion node cannot be removed: {operation.node_id}")
            if state.node_state(operation.node_id) not in _UNEXECUTED_STATES:
                raise RewriteError(f"executed node cannot be removed: {operation.node_id}")
            affected_roots.add(operation.node_id)
            del nodes[operation.node_id]
            edges = {
                edge_id: edge
                for edge_id, edge in edges.items()
                if edge.source != operation.node_id and edge.target != operation.node_id
            }
        elif isinstance(operation, RemoveEdge):
            edge = edges.get(operation.edge_id)
            if edge is None:
                raise RewriteError(f"unknown edge: {operation.edge_id}")
            affected_roots.add(edge.target)
            del edges[operation.edge_id]
        else:
            if operation.node.node_id not in nodes:
                raise RewriteError(f"unknown node: {operation.node.node_id}")
            nodes[operation.node.node_id] = operation.node
            affected_roots.add(operation.node.node_id)

    try:
        rewritten = GraphDefinition.create(
            nodes=nodes.values(),
            edges=edges.values(),
            completion_node_ids=completion_ids,
            version=graph.version + 1,
            parent_graph_id=graph.graph_id,
        )
    except GraphModelError as exc:
        raise RewriteError(str(exc)) from None
    _reject_cycles(rewritten)

    invalidated = _descendants(affected_roots, graph, rewritten)
    known_node_ids = {node_id for node_id, _ in state.node_states}
    invalidated &= known_node_ids
    approval_edges = {
        (edge.source, edge.target)
        for edge in (*graph.edges, *rewritten.edges)
        if edge.kind is EdgeKind.APPROVAL
    }
    invalidated_approvals = {
        source for source, target in approval_edges if target in invalidated
    }
    return RewriteResult(
        graph=rewritten,
        invalidated_nodes=tuple(sorted(invalidated)),
        invalidated_approvals=tuple(sorted(invalidated_approvals)),
    )
