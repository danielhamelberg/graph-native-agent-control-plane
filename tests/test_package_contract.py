import unittest

from graph_native_agent_control_plane import __version__


class PackageContractTests(unittest.TestCase):
    def test_public_version_is_explicitly_pre_release(self) -> None:
        self.assertEqual(__version__, "0.1.0a1")
