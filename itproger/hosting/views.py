"""Compatibility imports for code that still references ``hosting.views``.

New URL configuration imports domain-specific view modules directly.
"""

from .host_views import (
    HostDetailView,
    create_host,
    delete_host,
    hide_host,
    unhide_host,
    update_host,
)
from .monitoring_views import (
    check_snmp,
    get_snmp_info,
    hosting_create,
    range_ip,
)


__all__ = [
    'HostDetailView',
    'check_snmp',
    'create_host',
    'delete_host',
    'get_snmp_info',
    'hide_host',
    'hosting_create',
    'range_ip',
    'unhide_host',
    'update_host',
]
