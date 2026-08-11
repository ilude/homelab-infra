from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seaweedfs-state.py"
spec = importlib.util.spec_from_file_location("seaweedfs_state", SCRIPT)
assert spec and spec.loader
seaweedfs_state = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = seaweedfs_state
spec.loader.exec_module(seaweedfs_state)


class FakeBody:
    def read(self) -> bytes:
        return b"first"


class FakeS3:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.put_count = 0

    def head_bucket(self, **kwargs: object) -> None:
        self.calls.append(("head_bucket", kwargs))

    def put_bucket_versioning(self, **kwargs: object) -> None:
        self.calls.append(("put_bucket_versioning", kwargs))

    def put_bucket_lifecycle_configuration(self, **kwargs: object) -> None:
        self.calls.append(("put_bucket_lifecycle_configuration", kwargs))

    def get_bucket_versioning(self, **kwargs: object) -> dict[str, str]:
        return {"Status": "Enabled"}

    def get_bucket_lifecycle_configuration(self, **kwargs: object) -> dict[str, object]:
        lifecycle = next(
            value
            for name, value in self.calls
            if name == "put_bucket_lifecycle_configuration"
        )
        assert isinstance(lifecycle, dict)
        configuration = lifecycle["LifecycleConfiguration"]
        assert isinstance(configuration, dict)
        return {"Rules": configuration["Rules"]}

    def put_object(self, **kwargs: object) -> dict[str, str]:
        if "IfNoneMatch" in kwargs:
            error = {"Error": {"Code": "PreconditionFailed"}}
            raise seaweedfs_state.ClientError(error, "PutObject")
        self.put_count += 1
        return {"VersionId": f"version-{self.put_count}"}

    def get_object(self, **kwargs: object) -> dict[str, FakeBody]:
        return {"Body": FakeBody()}

    def list_object_versions(self, **kwargs: object) -> dict[str, list[dict[str, str]]]:
        key = str(kwargs["Prefix"])
        return {
            "Versions": [
                {"Key": key, "VersionId": "version-1"},
                {"Key": key, "VersionId": "version-2"},
            ],
            "DeleteMarkers": [],
        }

    def delete_object(self, **kwargs: object) -> None:
        self.calls.append(("delete_object", kwargs))


class SeaweedfsStateTests(unittest.TestCase):
    def test_lifecycle_keeps_state_longer_than_lock_history(self) -> None:
        rules = seaweedfs_state.lifecycle_rules("site.tfstate", 90, 1)
        by_id = {rule["ID"]: rule for rule in rules}
        state_days = by_id["retain-noncurrent-state"]["NoncurrentVersionExpiration"][
            "NoncurrentDays"
        ]
        lock_days = by_id["expire-noncurrent-locks"]["NoncurrentVersionExpiration"][
            "NoncurrentDays"
        ]
        self.assertGreater(state_days, lock_days)
        self.assertEqual(
            by_id["expire-noncurrent-locks"]["Filter"]["Prefix"],
            "site.tfstate.tflock",
        )
        self.assertTrue(
            by_id["expire-noncurrent-locks"]["Expiration"]["ExpiredObjectDeleteMarker"]
        )

    def test_ensure_configures_and_checks_versioned_bucket(self) -> None:
        client = FakeS3()
        args = mock.Mock(
            endpoint="https://state.example.internal",
            region="us-east-1",
            bucket="opentofu-state",
            state_key="homelab-infra.tfstate",
            state_noncurrent_days=90,
            lock_noncurrent_days=1,
        )
        with mock.patch.object(seaweedfs_state, "s3_client", return_value=client):
            seaweedfs_state.ensure(args)
        call_names = [name for name, _ in client.calls]
        self.assertIn("put_bucket_versioning", call_names)
        self.assertIn("put_bucket_lifecycle_configuration", call_names)
        self.assertEqual(client.put_count, 2)
        self.assertEqual(call_names.count("delete_object"), 2)

    def test_ensure_refuses_lock_retention_not_shorter_than_state(self) -> None:
        args = mock.Mock(state_noncurrent_days=1, lock_noncurrent_days=1)
        with self.assertRaisesRegex(
            seaweedfs_state.StateBucketError, "state history must outlive lock history"
        ):
            seaweedfs_state.ensure(args)


if __name__ == "__main__":
    unittest.main()
