from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "infra"
    / "ansible"
    / "roles"
    / "technitium_cluster"
    / "files"
    / "configure-technitium-cluster.py"
)
spec = importlib.util.spec_from_file_location("configure_technitium_cluster", SCRIPT)
assert spec and spec.loader
cluster = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cluster
spec.loader.exec_module(cluster)


class TechnitiumClusterTests(unittest.TestCase):
    def test_cluster_nodes_accepts_current_and_legacy_response_keys(self) -> None:
        current = {"clusterNodes": [{"state": "Self"}]}
        legacy = {"nodes": [{"state": "Self"}]}
        self.assertEqual(cluster.cluster_nodes(current), [{"state": "Self"}])
        self.assertEqual(cluster.cluster_nodes(legacy), [{"state": "Self"}])
        self.assertEqual(cluster.self_node(current), {"state": "Self"})

    def test_initialize_primary_is_idempotent_for_matching_address(self) -> None:
        state = {
            "clusterInitialized": True,
            "clusterDomain": "dns-cluster.example.internal",
            "clusterNodes": [
                {
                    "state": "Self",
                    "ipAddresses": ["192.0.2.54"],
                }
            ],
        }
        with mock.patch.object(cluster, "cluster_state", return_value=state), mock.patch.object(
            cluster, "api_call"
        ) as api_call:
            result, changed = cluster.initialize_primary(
                "http://192.0.2.54:5380/api",
                "token-placeholder",
                "dns-cluster.example.internal",
                "192.0.2.54",
            )
        self.assertEqual(result, state)
        self.assertFalse(changed)
        api_call.assert_not_called()

    def test_verify_cluster_accepts_connected_current_api_states(self) -> None:
        primary = {
            "clusterDomain": "dns-cluster.example.internal",
            "clusterNodes": [
                {"state": "Self"},
                {"state": "Connected"},
            ],
        }
        secondary = {
            "clusterDomain": "dns-cluster.example.internal",
            "clusterNodes": [
                {"state": "Connected"},
                {"state": "Self"},
            ],
        }
        with mock.patch.object(cluster, "cluster_state", side_effect=[primary, secondary]):
            cluster.verify_cluster(
                "http://192.0.2.54:5380/api",
                "http://127.0.0.1:5380/api",
                "token-placeholder",
                "dns-cluster.example.internal",
            )


if __name__ == "__main__":
    unittest.main()
