import ipaddress
import json
import math
import re
from pathlib import Path


BLOCK_PATTERN = re.compile(r'(?P<kind>hoststatus|servicestatus)\s*\{(?P<body>.*?)\n\s*\}', re.S)
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
SCAN_DEVICE_PATTERN = re.compile(
    r"\[DEVICE\].*?(?P<ip>(?:\d{1,3}\.){3}\d{1,3}).*?-> '(?P<device>[^']+)'"
)

STATE_NAMES = {'0': 'OK', '1': 'WARNING', '2': 'CRITICAL', '3': 'UNKNOWN'}
DEVICE_PREFIXES = {
    'servers': 'srv',
    'switches': 'sw',
    'routers': 'rtr',
    'computers': 'pc',
    'network-printers': 'prn',
    'UPS': 'ups',
}
VALID_DEVICE_TYPES = set(DEVICE_PREFIXES)
DEMO_NETWORKS = ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')
FIXED_TIMESTAMP = '2026-01-01T00:00:00Z'
TOPOLOGY_CENTER_X = 800.0
TOPOLOGY_CENTER_Y = 440.0
TOPOLOGY_Y_SCALE = 0.48
BRANCH_RADIUS = 210.0
ENDPOINT_RADII = (360.0, 450.0, 540.0, 630.0)
ENDPOINTS_PER_ARC = 5
ENDPOINT_ARC_DEGREES = 32.0


def _parse_body(body):
    return dict(
        line.strip().split('=', 1)
        for line in body.splitlines()
        if '=' in line
    )


def parse_status_file(path):
    hosts = []
    services = []
    content = Path(path).read_text(encoding='utf-8', errors='replace')
    for match in BLOCK_PATTERN.finditer(content):
        record = _parse_body(match.group('body'))
        if match.group('kind') == 'hoststatus':
            hosts.append(record)
        else:
            services.append(record)
    return hosts, services


def parse_scan_device_types(path):
    if not path or not Path(path).exists():
        return {}
    result = {}
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        match = SCAN_DEVICE_PATTERN.search(line)
        if match and match.group('device') in VALID_DEVICE_TYPES:
            result[match.group('ip')] = match.group('device')
    return result


def _record_ip(record):
    candidates = [record.get('host_name', ''), record.get('plugin_output', '')]
    for candidate in candidates:
        for value in IP_PATTERN.findall(candidate):
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                continue
    return None


def _fallback_device_type(host_name, descriptions):
    text = f"{host_name} {' '.join(descriptions)}".lower()
    if 'printer' in text:
        return 'network-printers'
    if any(token in text for token in ('ups', 'battery')):
        return 'UPS'
    if any(token in text for token in ('switch', 'router')):
        return 'switches'
    if any(token in text for token in ('windows', 'nsclient', 'drive space', 'w3svc')):
        return 'computers'
    return 'servers'


def _documentation_ips(count):
    addresses = [
        str(address)
        for network in DEMO_NETWORKS
        for address in ipaddress.ip_network(network).hosts()
    ]
    if count > len(addresses):
        raise ValueError('Not enough documentation addresses for sample fixture')
    return addresses[:count]


def _assign_topology(hosts):
    """Arrange sample hosts as an elliptical core-and-branches topology."""
    root = next((host for host in hosts if host['device_type'] == 'routers'), None)
    root = root or next(
        (host for host in hosts if host['device_type'] == 'switches'),
        hosts[0],
    )
    branches = [
        host
        for host in hosts
        if host is not root and host['device_type'] == 'switches'
    ]
    endpoints = [host for host in hosts if host is not root and host not in branches]

    root['parents'] = None
    root['x'] = TOPOLOGY_CENTER_X
    root['y'] = TOPOLOGY_CENTER_Y

    if not branches:
        branches = [root]

    grouped_endpoints = [[] for _branch in branches]
    for index, endpoint in enumerate(endpoints):
        grouped_endpoints[index % len(branches)].append(endpoint)

    branch_count = len(branches)
    for branch_index, (branch, children) in enumerate(zip(branches, grouped_endpoints)):
        branch_angle = -math.pi / 2 + branch_index * 2 * math.pi / branch_count
        if branch is not root:
            branch['parents'] = root['pk']
            branch['x'] = TOPOLOGY_CENTER_X + BRANCH_RADIUS * math.cos(branch_angle)
            branch['y'] = (
                TOPOLOGY_CENTER_Y
                + BRANCH_RADIUS * TOPOLOGY_Y_SCALE * math.sin(branch_angle)
            )

        for child_index, child in enumerate(children):
            arc_index = child_index // ENDPOINTS_PER_ARC
            position_in_arc = child_index % ENDPOINTS_PER_ARC
            items_in_arc = min(
                ENDPOINTS_PER_ARC,
                len(children) - arc_index * ENDPOINTS_PER_ARC,
            )
            if items_in_arc == 1:
                angle_offset = 0.0
            else:
                angle_offset = math.radians(ENDPOINT_ARC_DEGREES) * (
                    position_in_arc / (items_in_arc - 1) - 0.5
                )
            radius = ENDPOINT_RADII[arc_index]
            child_angle = branch_angle + angle_offset
            child['parents'] = branch['pk']
            child['x'] = TOPOLOGY_CENTER_X + radius * math.cos(child_angle)
            child['y'] = (
                TOPOLOGY_CENTER_Y
                + radius * TOPOLOGY_Y_SCALE * math.sin(child_angle)
            )


def build_demo_fixture(status_path, scan_path=None):
    host_records, service_records = parse_status_file(status_path)
    if not host_records:
        raise ValueError('Nagios status file does not contain hoststatus blocks')

    device_types = parse_scan_device_types(scan_path)
    status_ips = {_record_ip(record) for record in host_records}
    for scan_ip in sorted(device_types, key=ipaddress.ip_address):
        if scan_ip not in status_ips:
            host_records.append(
                {
                    'host_name': f'scan-device-{scan_ip}',
                    'plugin_output': scan_ip,
                    'current_state': '0',
                }
            )
    services_by_host = {}
    for service in service_records:
        services_by_host.setdefault(service.get('host_name', ''), []).append(service)

    demo_ips = _documentation_ips(len(host_records))
    hosts = []
    original_to_pk = {}
    type_counters = {key: 0 for key in DEVICE_PREFIXES}

    for index, (record, demo_ip) in enumerate(zip(host_records, demo_ips), start=1):
        original_name = record.get('host_name', f'host-{index}')
        original_ip = _record_ip(record)
        descriptions = [
            service.get('service_description', '')
            for service in services_by_host.get(original_name, [])
        ]
        device_type = device_types.get(original_ip) or _fallback_device_type(
            original_name, descriptions
        )
        type_counters[device_type] += 1
        hostname = f'{DEVICE_PREFIXES[device_type]}-{type_counters[device_type]:03d}'
        original_to_pk[original_name] = index
        hosts.append(
            {
                'pk': index,
                'ipaddr': demo_ip,
                'hostname': hostname,
                'device_type': device_type,
                'online': record.get('current_state') == '0',
            }
        )

    _assign_topology(hosts)

    fixture = [
        {'model': 'hosting.category', 'pk': 1, 'fields': {'name': 'Infrastructure'}},
        {'model': 'hosting.category', 'pk': 2, 'fields': {'name': 'Workstations'}},
        {'model': 'hosting.category', 'pk': 3, 'fields': {'name': 'Peripherals'}},
    ]
    category_by_type = {
        'computers': 2,
        'network-printers': 3,
        'UPS': 3,
    }
    for index, host in enumerate(hosts):
        fixture.append(
            {
                'model': 'hosting.host',
                'pk': host['pk'],
                'fields': {
                    'ipaddr': host['ipaddr'],
                    'hostname': host['hostname'],
                    'cat': category_by_type.get(host['device_type'], 1),
                    'time_create': FIXED_TIMESTAMP,
                    'time_update': FIXED_TIMESTAMP,
                    'online': host['online'],
                    'SNMP': host['device_type'] in {'switches', 'routers', 'UPS'},
                    'com_str': None,
                    'place': f'Zone {chr(65 + index % 4)}',
                    'nagios_flag': True,
                    'hide_flag': False,
                    'parents': host['parents'],
                    'segment': None,
                    'device_type': host['device_type'],
                    'latitude': 0.0,
                    'longitude': 0.0,
                },
            }
        )
        fixture.append(
            {
                'model': 'hosting.nodeposition',
                'pk': host['pk'],
                'fields': {
                    'ipaddr': host['ipaddr'],
                    'x': host['x'],
                    'y': host['y'],
                    'updated_at': FIXED_TIMESTAMP,
                },
            }
        )

    for service_pk, record in enumerate(service_records, start=1):
        host_pk = original_to_pk.get(record.get('host_name', ''))
        if host_pk is None:
            continue
        status = STATE_NAMES.get(record.get('current_state'), 'UNKNOWN')
        description = record.get('service_description', 'Service')[:255]
        fixture.append(
            {
                'model': 'hosting.service',
                'pk': service_pk,
                'fields': {
                    'host': host_pk,
                    'description': description,
                    'status': status,
                    'last_checked': FIXED_TIMESTAMP,
                    'status_information': f'{description}: {status}',
                },
            }
        )
    return fixture


def write_demo_fixture(status_path, output_path, scan_path=None):
    fixture = build_demo_fixture(status_path, scan_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return fixture
