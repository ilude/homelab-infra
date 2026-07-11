from __future__ import annotations

import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
TASKS = REPO / "infra/ansible/roles/forgejo_bind_mount/tasks/main.yml"
PLAYBOOK = REPO / "infra/ansible/playbooks/forgejo.yml"
FORGEJO_TF = REPO / "infra/opentofu/forgejo.tf"
LXC_MAIN = REPO / "infra/opentofu/modules/debian-lxc/main.tf"
LXC_VARS = REPO / "infra/opentofu/modules/debian-lxc/variables.tf"


class ForgejoBindMountTests(unittest.TestCase):
    def test_forgejo_module_has_no_api_mount_point(self) -> None:
        self.assertNotIn("mount_points", FORGEJO_TF.read_text(encoding="utf-8"))
        self.assertNotIn('dynamic "mount_point"', LXC_MAIN.read_text(encoding="utf-8"))
        self.assertNotIn('variable "mount_points"', LXC_VARS.read_text(encoding="utf-8"))

    def test_shared_lxc_explicitly_ignores_external_mount_lifecycle(self) -> None:
        text = LXC_MAIN.read_text(encoding="utf-8")
        self.assertIn("mount_point,", text)
        self.assertIn("Proxmox-host lifecycle concern", text)

    def test_role_is_guarded_fail_closed_and_idempotent(self) -> None:
        tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
        text = TASKS.read_text(encoding="utf-8")
        names = [task["name"] for task in tasks]
        self.assertLess(names.index("Fail when PVE bind mount target is not authoritative"), names.index("Inspect Forgejo LXC configuration"))
        self.assertLess(names.index("Fail closed on Forgejo bind mount slot or path conflict"), names.index("Attach missing Forgejo bind mount"))
        self.assertIn("regex_escape", text)
        self.assertIn("not forgejo_bind_mount_exact", text)
        self.assertIn("notify: Reboot Forgejo LXC after bind mount attachment", text)
        self.assertIn("ansible.builtin.meta: flush_handlers", text)
        self.assertIn("refusing overwrite", text)
        self.assertNotIn("ansible.builtin.shell", text)

    def test_bind_mount_and_second_readiness_precede_direct_handoff(self) -> None:
        plays = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
        roles = plays[0]["roles"]
        self.assertEqual(roles[1]["role"], "forgejo_bind_mount")
        self.assertEqual(roles[2]["role"], "lxc_ready")
        self.assertIn("direct access handoff", plays[1]["name"].lower())


if __name__ == "__main__":
    unittest.main()
