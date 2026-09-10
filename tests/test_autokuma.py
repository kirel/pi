import unittest
from pathlib import Path
import yaml
from ansible.errors import AnsibleFilterError
from filter_plugins.autokuma import autokuma_labels


class AutoKumaLabelsTest(unittest.TestCase):
    def test_service_catalog_preserves_static_homepage_entries(self):
        catalog = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                  'group_vars/all/services.yml').read_text())['services']
        static = {key for key, value in catalog.items()
                  if (value.get('homepage') or {}).get('source') == 'static'}
        self.assertEqual(static, {'hermes-local', 'hermes-local-webui',
                                  'hermes-baremetal-daniel', 'syncthing-ailab'})
        for key, service in catalog.items():
            autokuma_labels(service, key, 'validation-only')

    def test_ailab_is_monitored_without_obsolete_wol(self):
        catalog = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                  'group_vars/all/services.yml').read_text())['services']
        for key in ['llama-swap', 'comfyui', 'wan2gp', 't3-code-ailab',
                    'hermes-local', 'hermes-local-webui', 'syncthing-ailab']:
            self.assertNotIn('wol', catalog[key])
            self.assertNotIn('try', catalog[key])
            self.assertTrue(catalog[key]['monitoring'])

    def test_unconfigured_and_disabled_services_are_not_discovered(self):
        self.assertEqual(autokuma_labels({}, 'app'), {})
        self.assertEqual(autokuma_labels({'monitoring': {'enabled': False, 'docker': True}}, 'app'), {})

    def test_http_uses_service_domain_and_does_not_accept_login_redirects(self):
        labels = autokuma_labels({'domain': 'app.example.org', 'name': 'App',
                                  'monitoring': {'http': {'path': '/health'}}}, 'app')
        self.assertEqual(labels['kuma.app-http.http.url'], 'https://app.example.org/health')
        self.assertEqual(labels['kuma.app-http.http.max_redirects'], '0')
        self.assertEqual(labels['kuma.app-http.http.accepted_statuscodes'], '["200-299"]')
        self.assertNotIn('kuma.app-container.docker.name', labels)

    def test_http_rejects_wol_and_auth_routes(self):
        for extra in ({'wol': 'aa:bb:cc:dd:ee:ff'}, {'auth': {'provider': 'pocket_id'}}):
            with self.assertRaises(AnsibleFilterError):
                autokuma_labels(dict(domain='app.example.org', monitoring={'http': {}}, **extra), 'app')

    def test_remote_docker_uses_explicit_host_and_requires_owner(self):
        service = {'monitoring': {'docker': True}}
        labels = autokuma_labels(service, 'app-remote', 'app', 'hetzner')
        self.assertEqual(labels['kuma.app-remote-container.docker.docker_host_name'], 'hetzner')
        with self.assertRaises(AnsibleFilterError):
            autokuma_labels(service, 'app-remote')

    def test_unknown_settings_and_secrets_fail_instead_of_silently_being_ignored(self):
        for config in ({'htpt': {}}, {'http': {'headers': 'secret'}}):
            with self.assertRaises(AnsibleFilterError):
                autokuma_labels({'monitoring': config}, 'app')


if __name__ == '__main__':
    unittest.main()
