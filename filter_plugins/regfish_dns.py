"""Plan Regfish changes; HTTP and credentials stay in ansible.builtin.uri."""
from collections import Counter
from ipaddress import ip_address
import re

from ansible.errors import AnsibleFilterError


def fail(message):
    raise AnsibleFilterError(f'Regfish DNS: {message}')


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def fqdn(value):
    if not isinstance(value, str) or not value or len(value.rstrip('.')) > 253:
        fail('expected a DNS name')
    name = value.rstrip('.').lower()
    labels = name.split('.')
    if any(not re.fullmatch(r'[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?', label)
           for label in (labels[1:] if labels[0] == '*' else labels)):
        fail(f'invalid DNS name: {value}')
    return name + '.'


def regfish_dns_catalog(zones, services):
    """Expand relative zone names and opt-in services into validated API records."""
    if not isinstance(zones, dict) or not isinstance(services, dict):
        fail('zones and services must be mappings')
    catalog = {}
    for zone, records in zones.items():
        canonical = fqdn(zone).rstrip('.')
        if canonical != zone or '*' in zone or not isinstance(records, list):
            fail(f'{zone}: use a lowercase zone without trailing dot and a record list')
        if any(not isinstance(record, dict) for record in records):
            fail(f'{zone}: each record must be a mapping')
        catalog[zone] = [dict(record) for record in records]
    for service_id, service in services.items():
        if 'dns' not in service:
            continue
        dns = service['dns']
        if not isinstance(dns, dict) or 'name' in dns:
            fail(f'{service_id}: dns must be a record mapping; the name comes from domain')
        domain = fqdn(service.get('domain'))
        matches = [zone for zone in catalog
                   if domain == zone + '.' or domain.endswith('.' + zone + '.')]
        if not matches:
            fail(f'{service_id}: domain is not in a declared Regfish zone')
        catalog[max(matches, key=len)].append(dict(dns, name=domain))

    seen, ids = set(), set()
    for zone, records in catalog.items():
        for record in records:
            unknown = set(record) - {'name', 'type', 'data', 'ttl', 'priority', 'flags',
                                     'tag', 'annotation', 'id', 'state', 'auto', 'active'}
            if unknown or not {'name', 'type', 'data'} <= record.keys():
                fail(f'{zone}: unknown fields {sorted(unknown)} or missing name/type/data')
            name = record['name']
            if not isinstance(name, str) or not name:
                fail(f'{zone}: name must be a non-empty string')
            if name == '@':
                name = zone
            elif not name.endswith('.') and name != zone and not name.endswith('.' + zone):
                name += '.' + zone
            record['name'] = name = fqdn(name)
            if name != zone + '.' and not name.endswith('.' + zone + '.'):
                fail(f'{name}: outside zone {zone}')
            if '_acme-challenge' in name.split('.'):
                fail(f'{name}: ACME records belong to Caddy')
            kind = record['type']
            if kind not in {'A', 'AAAA', 'CNAME', 'ALIAS', 'MX', 'TXT', 'CAA'}:
                fail(f'{name}: unsupported record type {kind}')
            data = record['data']
            if not isinstance(data, str):
                fail(f'{name}: data must be a string (quote TXT values)')
            if kind in {'A', 'AAAA'}:
                try:
                    address = ip_address(data)
                except ValueError:
                    fail(f'{name}: invalid IP address')
                if address.version != (4 if kind == 'A' else 6):
                    fail(f'{name}: IP version does not match {kind}')
                record['data'] = str(address)
            elif kind in {'CNAME', 'ALIAS', 'MX'}:
                record['data'] = fqdn(data)
            record.setdefault('ttl', 600)
            if not integer(record['ttl']) or not 60 <= record['ttl'] <= 86400:
                fail(f'{name}: ttl must be an integer between 60 and 86400')
            if kind == 'MX':
                if not integer(record.get('priority')) or not 0 <= record['priority'] <= 65535:
                    fail(f'{name}: MX requires priority 0..65535')
            elif 'priority' in record:
                fail(f'{name}: priority only applies to MX')
            if kind == 'CAA':
                if (not integer(record.get('flags')) or not 0 <= record['flags'] <= 255
                        or not isinstance(record.get('tag'), str) or not record['tag']):
                    fail(f'{name}: CAA requires flags 0..255 and tag')
            elif 'flags' in record or 'tag' in record:
                fail(f'{name}: flags/tag only apply to CAA')
            if 'annotation' in record and not isinstance(record['annotation'], str):
                fail(f'{name}: annotation must be a string')
            state = record.setdefault('state', 'present')
            if state not in {'present', 'absent', 'observed'}:
                fail(f'{name}: state must be present, absent or observed')
            if state != 'observed' and ('auto' in record or 'active' in record):
                fail(f'{name}: auto/active are inventory-only fields; use state: observed')
            for field in ('auto', 'active'):
                if field in record and type(record[field]) is not bool:
                    fail(f'{name}: {field} must be boolean')
            if 'id' in record:
                if not integer(record['id']) or record['id'] <= 0 or record['id'] in ids:
                    fail(f'{name}: id must be a unique positive integer')
                ids.add(record['id'])
            identity = (name, kind, record['data'])
            if identity in seen:
                fail(f'{name}: duplicate {kind} value (including service records)')
            seen.add(identity)
        active = [r for r in records if r['state'] != 'absent' and r.get('active', True)]
        for record in active:
            if record['type'] == 'CNAME' and sum(r['name'] == record['name'] for r in active) > 1:
                fail(f'{record["name"]}: CNAME cannot coexist with other records')
    return catalog


def regfish_dns_plan(desired, current):
    """No purge: missing declarations become unmanaged; deletion is explicit."""
    changes, observed_drift, unmanaged = [], [], []
    ignored_acme = managed_count = observed_count = 0
    for zone, records in desired.items():
        if zone not in current or not isinstance(current[zone], list):
            fail(f'{zone}: missing or malformed API response')
        live = current[zone]
        consumed = set()
        group_sizes = Counter((r['name'], r['type']) for r in records)
        for record in records:
            name, kind, state = record['name'], record['type'], record['state']
            candidates = [r for r in live if r['name'] == name and r['type'] == kind]
            if 'id' in record:
                matches = [r for r in candidates if r['id'] == record['id']]
                if not matches and state != 'absent':
                    fail(f'{name}: id {record["id"]} missing or name/type changed; inspect before recreating')
            else:
                matches = [r for r in candidates if r['data'] == record['data']]
                if not matches and state == 'present' and group_sizes[(name, kind)] == 1:
                    matches = candidates
            if len(matches) > 1:
                fail(f'{name}: ambiguous {kind} record; specify its Regfish id')
            existing = matches[0] if matches else None
            if existing:
                if existing['id'] in consumed:
                    fail(f'{name}: multiple declarations target id {existing["id"]}')
                consumed.add(existing['id'])
            body = {key: value for key, value in record.items()
                    if key not in {'id', 'state', 'auto', 'active'}}
            label = f'{name} {kind}'
            if state == 'observed':
                observed_count += 1
                expected = {key: value for key, value in record.items() if key != 'state'}
                if not existing or any(existing.get(k) != v for k, v in expected.items()):
                    observed_drift.append({'record': label, 'expected': expected, 'actual': existing})
                continue
            managed_count += 1
            if existing and (existing.get('auto', False) or not existing.get('active', True)):
                fail(f'{label}: automatic/inactive record must use state: observed')
            if state == 'absent':
                if existing:
                    changes.append({'record': label, 'method': 'DELETE',
                                    'path': f'/dns/rr/{existing["id"]}', 'before': existing})
                continue
            # Reject CNAME collisions locally, before any part of the plan is applied.
            conflicts = [r for r in live if r['name'] == name and r.get('active', True)
                         and (not existing or r['id'] != existing['id'])
                         and (kind == 'CNAME' or r['type'] == 'CNAME')]
            if conflicts:
                fail(f'{name}: CNAME conflicts with an existing record; migrate explicitly')
            if not existing:
                changes.append({'record': label, 'method': 'POST', 'path': '/dns/rr', 'body': body})
            elif any(existing.get(key) != value for key, value in body.items()):
                changes.append({'record': label, 'method': 'PATCH',
                                'path': f'/dns/rr/{existing["id"]}', 'body': body, 'before': existing})
        for record in live:
            if '_acme-challenge' in record['name'].split('.'):
                ignored_acme += 1
            elif record['id'] not in consumed:
                unmanaged.append(record)
    return {'managed': managed_count, 'observed': observed_count,
            'ignored_acme': ignored_acme, 'changes': changes,
            'observed_drift': observed_drift, 'unmanaged': unmanaged}


class FilterModule:
    def filters(self):
        return {'regfish_dns_catalog': regfish_dns_catalog, 'regfish_dns_plan': regfish_dns_plan}
