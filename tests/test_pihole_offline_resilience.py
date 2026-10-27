"""Retain DNS service when the Pi is offline and WAN IPv4 is unavailable."""
from pathlib import Path
import unittest

import yaml
from jinja2 import Template


ROOT = Path(__file__).resolve().parents[1]


class PiholeOfflineResilienceTest(unittest.TestCase):
    def test_router_is_an_additional_upstream(self):
        source = (ROOT / 'roles/pihole/templates/offline-resilience.conf.j2').read_text()
        rendered = Template(source).render(pihole_dns_forward_max=1000,
                                           router_ip='192.168.50.1')
        lines = rendered.splitlines()
        self.assertIn('server=192.168.50.1', lines)
        self.assertIn('dns-forward-max=1000', lines)
        self.assertNotIn('192.168.50.4', rendered)

    def test_config_changes_restart_dns_not_just_clear_cache(self):
        handlers = yaml.safe_load((ROOT / 'roles/pihole/handlers/main.yml').read_text())
        handler = next(h for h in handlers if h['name'] == 'Reload pihole dns')
        self.assertEqual(handler['ansible.builtin.command'], 'docker restart pihole')


if __name__ == '__main__':
    unittest.main()
