from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st

from graph_native_agent_control_plane.canonical_json import canonical_bytes, loads_strict
from graph_native_agent_control_plane.model import GraphDefinition
from tests.test_model import agent_node


class DeterminismPropertyTests(unittest.TestCase):
    @settings(derandomize=True, max_examples=100)
    @given(
        st.dictionaries(
            keys=st.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True),
            values=st.integers(min_value=-(2**31), max_value=2**31 - 1),
            max_size=12,
        )
    )
    def test_canonical_json_round_trip_is_stable(self, value: dict[str, int]) -> None:
        encoded = canonical_bytes(value)
        self.assertEqual(loads_strict(encoded), value)
        self.assertEqual(canonical_bytes(loads_strict(encoded)), encoded)

    @settings(derandomize=True, max_examples=60)
    @given(
        st.lists(
            st.sampled_from(("alpha", "beta", "gamma", "delta", "epsilon")),
            unique=True,
            max_size=5,
        )
    )
    def test_graph_identity_is_permutation_invariant(self, node_ids: list[str]) -> None:
        nodes = tuple(agent_node(node_id) for node_id in node_ids)
        forward = GraphDefinition.create(nodes=nodes, edges=())
        reverse = GraphDefinition.create(nodes=reversed(nodes), edges=())
        self.assertEqual(forward.graph_id, reverse.graph_id)


if __name__ == "__main__":
    unittest.main()
