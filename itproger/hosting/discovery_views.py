import ipaddress
import logging
import re
import threading

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import Host
from .network_discovery import NetworkDiscovery


logger = logging.getLogger(__name__)
_status_lock = threading.Lock()
_status = {'state': 'idle', 'hosts_discovered': 0, 'error': None}


def _validated_ip(value):
    if not value:
        raise ValueError('IP address is required')
    return str(ipaddress.ip_address(value))


def _validated_community(value):
    if not value or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,64}', value):
        raise ValueError('Invalid SNMP community')
    return value


def _set_status(**values):
    with _status_lock:
        _status.update(values)


def _run_discovery(start_ip, community, max_hops, max_devices):
    _set_status(state='running', hosts_discovered=0, error=None)
    try:
        discovery = NetworkDiscovery(community=community)
        hosts, _connections = discovery.discover_network(
            start_ip,
            max_hops=max_hops,
            max_devices=max_devices,
        )
        discovery.save_to_database()
    except Exception as exc:
        logger.exception('Background network discovery failed')
        _set_status(state='failed', error=str(exc))
    else:
        _set_status(state='completed', hosts_discovered=len(hosts), error=None)


@login_required
@require_http_methods(['GET', 'POST'])
def discover_network(request):
    if request.method == 'GET':
        return render(request, 'front/discover_form.html')

    try:
        start_ip = _validated_ip(request.POST.get('start_ip'))
        community = _validated_community(request.POST.get('community', 'public'))
        max_hops = int(request.POST.get('max_hops', 3))
        max_devices = int(request.POST.get('max_devices', 50))
        if not 1 <= max_hops <= 20:
            raise ValueError('max_hops must be between 1 and 20')
        if not 1 <= max_devices <= 1000:
            raise ValueError('max_devices must be between 1 and 1000')
    except (TypeError, ValueError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    worker = threading.Thread(
        target=_run_discovery,
        args=(start_ip, community, max_hops, max_devices),
        daemon=True,
        name='network-discovery',
    )
    worker.start()
    messages.success(request, f'Network discovery started from IP {start_ip}')
    return redirect('service')


@login_required
@require_GET
def discovery_status(request):
    with _status_lock:
        status = dict(_status)
    if status['state'] == 'idle':
        status['hosts_discovered'] = Host.objects.filter(SNMP=True).count()
    return JsonResponse(status)
