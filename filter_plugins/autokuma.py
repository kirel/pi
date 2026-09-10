"""Render opt-in service monitoring as Docker labels, without secret fields."""
from ansible.errors import AnsibleFilterError


def autokuma_labels(service, service_id, container_name=None, docker_host='local'):
    config = service.get('monitoring', {})
    if not config or not config.get('enabled', True):
        return {}
    unknown = set(config) - {'enabled', 'http', 'docker', 'interval', 'max_retries'}
    if unknown:
        raise AnsibleFilterError(f'{service_id}: unknown monitoring settings: {sorted(unknown)}')
    labels = {}
    name = service.get('name', service_id)
    common = {'interval': config.get('interval', 60),
              'retry_interval': 30, 'max_retries': config.get('max_retries', 2)}

    def add(suffix, kind, settings):
        for key, value in dict(common, **settings).items():
            labels[f'kuma.{service_id}-{suffix}.{kind}.{key}'] = str(value)

    if 'http' in config:
        http = config['http']
        if set(http) - {'path'}:
            raise AnsibleFilterError(f'{service_id}: HTTP monitoring accepts only path')
        if service.get('wol') or service.get('auth'):
            raise AnsibleFilterError(f'{service_id}: proxy HTTP monitoring would wake the host or check SSO')
        path = http.get('path', '/')
        if not path.startswith('/') or path.startswith('//'):
            raise AnsibleFilterError(f'{service_id}: monitoring path must start with a single slash')
        add('http', 'http', {'name': f'{name} HTTP',
                           'url': f'https://{service["domain"]}{path}',
                           'timeout': 10, 'max_redirects': 0,
                           'accepted_statuscodes': '["200-299"]'})
    if config.get('docker'):
        if not container_name:
            raise AnsibleFilterError(f'{service_id}: Docker monitoring requires a container name')
        add('container', 'docker', {'name': f'{name} Container',
                                   'docker_container': container_name,
                                   'docker_host_name': docker_host})
    return labels


class FilterModule:
    def filters(self):
        return {'autokuma_labels': autokuma_labels}
