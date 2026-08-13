import ipaddress
import re
import shlex

from .monitoring_connection import connector


COMMUNITY_PATTERN = re.compile(r'^[A-Za-z0-9_.:@-]{1,64}$')


def validate_target(ip_address, community):
    ip_address = str(ipaddress.ip_address(ip_address))
    if not community or not COMMUNITY_PATTERN.fullmatch(community):
        raise ValueError('Invalid SNMP community')
    return ip_address, community


def _get(ip_address, community, oid):
    ip_address, community = validate_target(ip_address, community)
    command = ' '.join(
        [
            'snmpget',
            '-v1',
            '-c',
            shlex.quote(community),
            shlex.quote(ip_address),
            shlex.quote(oid),
        ]
    )
    result = connector.run(command, hide=True, warn=True)
    return result.stdout if result.ok else ''


def _string_value(output):
    if 'STRING:' not in output:
        return None
    return output.split('STRING:', 1)[1].strip().strip('"')


def classify_device(description):
    description_lower = description.lower()
    if 'lenovo' in description_lower:
        return 'lenovosw'
    if 'qtech' in description_lower:
        return 'qtechsw'
    if 'dgs-1210-10' in description_lower:
        return 'dlinksw'
    if 'cisco' in description_lower or 'ios' in description_lower:
        return 'nexus'
    if 'apc_hw05_aos_513' in description_lower:
        return 'apc_hw05_aos_513'
    if 'ups' in description_lower or 'apc' in description_lower:
        return 'UPS'
    return None


def get_device_identity(ip_address, community):
    """Return ``(os_version, hostname, available)`` for an SNMP target."""
    ip_address, community = validate_target(ip_address, community)
    name_output = _get(ip_address, community, '1.3.6.1.2.1.1.5.0')
    hostname = _string_value(name_output)
    if not hostname:
        return None, None, False

    description = _string_value(
        _get(ip_address, community, '1.3.6.1.2.1.1.1.0')
    ) or ''
    os_version = classify_device(description)

    if os_version == 'UPS':
        ups_name = _string_value(
            _get(ip_address, community, '1.3.6.1.2.1.33.1.1.5.0')
        )
        ups_model = _string_value(
            _get(ip_address, community, '1.3.6.1.2.1.33.1.1.2.0')
        )
        hostname = ups_name or hostname
        os_version = ups_model or os_version

    return os_version, hostname, True
