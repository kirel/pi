"""Dozzle's local healthcheck cannot detect a missing Docker endpoint."""
import unittest
from pathlib import Path

import yaml


class DozzleNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                   'roles/dozzle/tasks/main.yml').read_text())

    def test_network_repair_follows_compose_and_preserves_other_members(self):
        start = next(i for i, t in enumerate(self.tasks)
                     if t.get('name') == 'Start Dozzle agent')
        repair = next(i for i, t in enumerate(self.tasks)
                      if 'community.docker.docker_network' in t)
        self.assertGreater(repair, start)
        task = self.tasks[repair]
        self.assertEqual(task['community.docker.docker_network'], {
            'name': 'dozzle-agent_default', 'connected': ['dozzle-agent'],
            'appends': True, 'state': 'present',
        })
        self.assertEqual(task['when'], 'dozzle_agent_enabled | bool')

    def test_port_is_checked_from_ui_not_inside_agent(self):
        task = next(t for t in self.tasks if 'ansible.builtin.wait_for' in t)
        self.assertEqual(task['delegate_to'], '{{ dozzle_ui_host }}')
        self.assertEqual(task['ansible.builtin.wait_for']['port'],
                         '{{ dozzle_agent_port }}')
        self.assertEqual(task['ansible.builtin.wait_for']['host'],
                         '{{ dozzle_agent_advertise_address | default(ansible_host) }}')
        self.assertIn('dozzle_agent_enabled | bool', task['when'])
        self.assertIn('dozzle_ui_host in hostvars', task['when'])
        self.assertIn('not ansible_check_mode', task['when'])
        repair = next(i for i, t in enumerate(self.tasks)
                      if 'community.docker.docker_network' in t)
        self.assertGreater(self.tasks.index(task), repair)


if __name__ == '__main__':
    unittest.main()
