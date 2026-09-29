"""Run with: uv run python -m unittest discover -s tests -p test_regfish_dns.py"""
import unittest
from copy import deepcopy

from ansible.errors import AnsibleFilterError
from filter_plugins.regfish_dns import regfish_dns_catalog, regfish_dns_plan


class RegfishDnsTest(unittest.TestCase):
    def setUp(self):
        self.record = {'name': 'www.example.org.', 'type': 'A', 'data': '192.0.2.1', 'ttl': 600}
        self.live = dict(self.record, id=10, active=True, auto=False)

    def plan(self, records, live=None, services=None):
        desired = regfish_dns_catalog({'example.org': records}, services or {})
        return regfish_dns_plan(desired, {'example.org': [self.live] if live is None else live})

    def test_import_is_noop_and_input_is_not_modified(self):
        before = deepcopy(self.record)
        self.assertEqual(self.plan([self.record])['changes'], [])
        self.assertEqual(before, self.record)
        self.assertEqual(self.plan([dict(self.record, name='www')])['changes'], [])

    def test_create_update_delete_and_second_run(self):
        created = self.plan([self.record], [])['changes'][0]
        self.assertEqual((created['method'], created['path']), ('POST', '/dns/rr'))
        changed = dict(self.record, data='192.0.2.2', ttl=300)
        action = self.plan([changed])['changes'][0]
        self.assertEqual((action['method'], action['path']), ('PATCH', '/dns/rr/10'))
        after = dict(self.live, **action['body'])
        self.assertEqual(self.plan([changed], [after])['changes'], [])
        deleted = dict(self.record, state='absent')
        self.assertEqual(self.plan([deleted])['changes'][0]['method'], 'DELETE')
        self.assertEqual(self.plan([deleted], [])['changes'], [])
        # A missing declaration or a different data value never deletes a record.
        self.assertEqual(self.plan([])['changes'], [])
        self.assertEqual(self.plan([])['unmanaged'], [self.live])
        self.assertEqual(self.plan([dict(deleted, data='192.0.2.99')])['changes'], [])

    def test_multivalue_updates_require_unambiguous_identity(self):
        second = dict(self.live, id=11, data='192.0.2.2')
        live = [self.live, second]
        with self.assertRaises(AnsibleFilterError):
            self.plan([dict(self.record, data='192.0.2.3')], live)
        action = self.plan([dict(self.record, id=11, data='192.0.2.3')], live)['changes'][0]
        self.assertEqual(action['path'], '/dns/rr/11')
        self.assertEqual(self.plan([self.record, dict(self.record, data='192.0.2.2')], live)['changes'], [])
        with self.assertRaises(AnsibleFilterError):
            self.plan([dict(self.record, id=99)])

    def test_protected_and_acme_records_are_never_written(self):
        for flags in ({'auto': True}, {'active': False}):
            protected = dict(self.live, **flags)
            for state in ('present', 'absent'):
                with self.assertRaises(AnsibleFilterError):
                    self.plan([dict(self.record, state=state)], [protected])
            observed = dict(self.record, state='observed', **flags)
            self.assertEqual(self.plan([observed], [protected])['observed_drift'], [])
            drift = self.plan([observed], [])
            self.assertEqual(drift['changes'], [])
            self.assertEqual(len(drift['observed_drift']), 1)
        acme = dict(self.live, name='_acme-challenge.example.org.', type='TXT')
        result = self.plan([], [acme])
        self.assertEqual(result['ignored_acme'], 1)
        self.assertEqual(result['unmanaged'], [])
        with self.assertRaises(AnsibleFilterError):
            self.plan([dict(self.record, name='_acme-challenge')])

    def test_services_are_opt_in_and_independent_of_access_policy(self):
        services = {'internal': {'domain': 'internal.example.org'},
                    'public_only': {'domain': 'public.example.org', 'public': True},
                    'tailnet': {'domain': 'tailnet.example.org', 'public': False,
                                'dns': {'type': 'A', 'data': '100.82.91.51'}}}
        result = self.plan([], [], services)
        self.assertEqual(len(result['changes']), 1)
        self.assertEqual(result['changes'][0]['body']['name'], 'tailnet.example.org.')
        duplicate = {'www': {'domain': 'www.example.org', 'dns': {'type': 'A', 'data': '192.0.2.1'}}}
        with self.assertRaises(AnsibleFilterError):
            self.plan([self.record], [], duplicate)
        with self.assertRaises(AnsibleFilterError):
            self.plan([], [], {'bad': {'domain': 'outside.test', 'dns': {'type': 'A', 'data': '192.0.2.1'}}})

    def test_validation_and_cname_conflicts_fail_before_writes(self):
        for fields in ({'ttl': True}, {'ttl': 0}, {'data': '999.1.1.1'}, {'typo': 1},
                       {'name': 'outside.test.'}, {'active': False}, {'type': 'MX'},
                       {'name': ''}, {'name': 'bad/name'}, {'state': 'purge'}):
            with self.subTest(fields=fields), self.assertRaises(AnsibleFilterError):
                self.plan([dict(self.record, **fields)])
        cname = dict(self.record, type='CNAME', data='target.example.org.')
        with self.assertRaises(AnsibleFilterError):
            self.plan([cname])
        with self.assertRaises(AnsibleFilterError):
            self.plan([cname, self.record], [])
        with self.assertRaises(AnsibleFilterError):
            self.plan([self.record], [self.live, dict(self.live, id=11)])


if __name__ == '__main__':
    unittest.main()
