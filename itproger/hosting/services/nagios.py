import re
import shlex

from hosting.models import Host

from .monitoring_connection import connector


HOSTNAME_PATTERN = re.compile(r'^[A-Za-z0-9._-]{1,255}$')
NAGIOS_HOST_ROOT = '/usr/local/nagios/etc/objects/hosts'

GENERIC_HOST_TEMPLATES = {
    'switches': 'generic-switch',
    'servers': 'generic-server',
    'routers': 'generic-switch',
    'computers': 'generic-host',
    'network-printers': 'generic-printer',
    'UPS': 'generic-UPS',
}

SERVICE_TEMPLATES = {
    'cpu_5_min': ('check_snmp_cpu_{osver}-service-private', 'CPU 5 min load'),
    'uptime': ('uptime-service', 'Uptime'),
    'mem_free': ('check_snmp_memory_free_{osver}-{service}', 'Memory Free'),
    'mem_used': ('check_snmp_memory_used_{osver}-{service}', 'Memory Used'),
    'mem_util': ('check_snmp_memory_utl_{osver}-{service}', 'Memory Utilization'),
    'bat_temp': ('upstemp', 'Battery Temperature'),
    'bat_time_work': ('ups_time_work_on_battery', 'Battery Time Work'),
    'bat_vol': ('ups_volt', 'Battery Voltage'),
    'run_reman': ('ups_battery_run_time_remaining', 'Runtime Remaining'),
    'stat_charge': ('ups_bat_stat', 'State of Charge'),
}


def delete_host_configuration(device_type, hostname):
    """Remove a host configuration and parent references from Nagios."""
    valid_device_types = dict(Host.DEVICE_CHOICES)
    if device_type not in valid_device_types:
        return False, 'Invalid device type'
    if not hostname or not HOSTNAME_PATTERN.fullmatch(hostname):
        return False, 'Invalid host name'

    root = shlex.quote(NAGIOS_HOST_ROOT)
    pattern = shlex.quote(f'parents\t{hostname}')
    fallback_pattern = shlex.quote(f'parents {hostname}')
    config_path = shlex.quote(f'{NAGIOS_HOST_ROOT}/{device_type}/{hostname}.cfg')

    remove_references = connector.run(
        f'grep -rlF {pattern} {root} | xargs -r sed -i /{shlex.quote(hostname)}/d',
        hide=True,
        warn=True,
    )
    if not remove_references.ok:
        remove_references = connector.run(
            f'grep -rlF {fallback_pattern} {root} | xargs -r sed -i /{shlex.quote(hostname)}/d',
            hide=True,
            warn=True,
        )

    remove_file = connector.run(f'rm -f -- {config_path}', hide=True, warn=True)
    if remove_references.ok and remove_file.ok:
        return True, 'Host removed'
    return False, 'Error while deleting Nagios configuration'


def render_host_configuration(host, selected_checks=()):
    hostname = host.hostname or host.ipaddr
    if not HOSTNAME_PATTERN.fullmatch(hostname):
        raise ValueError('Invalid host name')
    template = GENERIC_HOST_TEMPLATES.get(host.device_type)
    if template is None:
        raise ValueError('Invalid device type')

    lines = [
        'define host {',
        f'\tuse\t\t{template}',
        f'\thost_name\t{hostname}',
        f'\taddress\t\t{host.ipaddr}',
        f'\thost_groups\t{host.device_type}',
    ]
    if host.parents:
        lines.append(f'\tparents\t{host.parents.hostname or host.parents.ipaddr}')
    if host.device_type == 'servers':
        lines.append('\ticon_image\tserver-1.png')
    lines.extend(['}', '', 'define service {', '\tuse\t\tping-service', f'\thost_name\t{hostname}', '}', ''])

    service_name = 'service-private' if host.osver == 'lenovosw' else 'service'
    for check in selected_checks:
        definition = SERVICE_TEMPLATES.get(check)
        if definition is None or not host.SNMP:
            continue
        command, description = definition
        command = command.format(osver=host.osver or 'generic', service=service_name)
        lines.extend(
            [
                'define service {',
                f'\tuse\t\t\t{command}',
                f'\tservice_description\t{description}',
                f'\thost_name\t\t{hostname}',
                '}',
                '',
            ]
        )
    return '\n'.join(lines)


def sync_host_configuration(host, selected_checks=(), previous=None):
    """Write a host config and restart Nagios, returning ``(ok, message)``."""
    hostname = host.hostname or host.ipaddr
    try:
        content = render_host_configuration(host, selected_checks)
        path = f'{NAGIOS_HOST_ROOT}/{host.device_type}/{hostname}.cfg'
        if previous and previous != (host.device_type, hostname):
            old_type, old_name = previous
            if old_type in GENERIC_HOST_TEMPLATES and HOSTNAME_PATTERN.fullmatch(old_name):
                old_path = shlex.quote(f'{NAGIOS_HOST_ROOT}/{old_type}/{old_name}.cfg')
                connector.run(f'rm -f -- {old_path}', hide=True, warn=True)
        with connector.sftp().file(path, 'w') as config_file:
            config_file.write(content)
        restart = connector.run('sudo systemctl restart nagios', hide=True, warn=True)
    except (OSError, RuntimeError, ValueError) as exc:
        return False, f'Host saved, but Nagios is unavailable: {exc}'

    if restart.ok:
        return True, 'Nagios configuration updated'
    return False, 'Host saved, but Nagios restart failed'
