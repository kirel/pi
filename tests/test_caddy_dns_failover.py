"""Guard DNS fallback against Caddy's default 3-second upstream dial deadline."""
import unittest
from pathlib import Path

import yaml


class CaddyDnsFailoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tasks = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                'roles/caddy/tasks/main.yml').read_text())
        task = next(task for task in tasks if task.get('name') == 'Start caddy')
        cls.service = task['community.docker.docker_compose_v2']['definition']['services']['caddy']

    def test_both_internal_resolvers_with_local_first(self):
        self.assertEqual(self.service['dns'],
                         ['{{ homelab_nuc_ip }}', '{{ nameserver_pi_ip }}'])

    def test_dns_fallback_precedes_upstream_dial_deadline(self):
        options = dict(option.split(':', 1) for option in self.service['dns_opt'])
        self.assertGreater(int(options['timeout']), 0)
        self.assertLess(int(options['timeout']), 3)
        self.assertGreaterEqual(int(options['attempts']), 2)


if __name__ == '__main__':
    unittest.main()
