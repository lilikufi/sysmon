import ipaddress
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Host, LineSettings, NodePosition, Route
from .services.microsegmentation import evaluate_segments


def _validated_ip(value):
    if not value:
        raise ValueError('IP address is required')
    return str(ipaddress.ip_address(value))


def _validated_node_id(value):
    return _validated_ip(value)


@login_required
@require_POST
def delete_coordinates(request, host_name):
    try:
        target = _validated_ip(host_name)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    host = get_object_or_404(Host, ipaddr=target)
    host.latitude = 0.0
    host.longitude = 0.0
    host.save(update_fields=['latitude', 'longitude'])
    return JsonResponse({'success': True, 'message': 'Host parameters have been reset.'})


@login_required
@require_POST
def save_route(request):
    try:
        data = json.loads(request.body)
        parent = _validated_ip(data.get('parent'))
        child = _validated_ip(data.get('child'))
        waypoints = data.get('waypoints', [])
        if not isinstance(waypoints, list):
            raise ValueError('Waypoints must be a list')
        if parent == child:
            raise ValueError('A host cannot be connected to itself')

        parent_host = Host.objects.get(ipaddr=parent)
        child_host = Host.objects.get(ipaddr=child)
        route, created = Route.objects.update_or_create(
            parent=parent_host,
            child=child_host,
            defaults={'waypoints': waypoints},
        )
        if child_host.parents_id != parent_host.pk:
            child_host.parents = parent_host
            child_host.save(update_fields=['parents'])

        return JsonResponse({'success': True, 'created': created, 'route_id': route.pk})
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Host.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)


@login_required
@require_POST
def update_host_coordinates(request):
    try:
        ip_address = _validated_ip(request.POST.get('ip_address'))
        latitude = float(request.POST.get('latitude'))
        longitude = float(request.POST.get('longitude'))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError('Coordinates are outside the valid range')

        host = Host.objects.get(ipaddr=ip_address)
        host.latitude = latitude
        host.longitude = longitude
        host.save(update_fields=['latitude', 'longitude'])
        return JsonResponse({'success': True})
    except Host.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@login_required
@require_POST
def save_line_settings(request):
    line_id = request.POST.get('line_id')
    color = request.POST.get('color')
    line_type = request.POST.get('line_type')
    try:
        weight = int(request.POST.get('weight'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Invalid weight'}, status=400)

    if not line_id or not color or not line_type:
        return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)
    if len(color) != 7 or not color.startswith('#'):
        return JsonResponse({'status': 'error', 'message': 'Invalid color'}, status=400)
    try:
        int(color[1:], 16)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'Invalid color'}, status=400)
    if not 1 <= weight <= 10:
        return JsonResponse({'status': 'error', 'message': 'Invalid weight'}, status=400)
    if line_type not in dict(LineSettings.LINE_TYPES):
        return JsonResponse({'status': 'error', 'message': 'Invalid line type'}, status=400)

    LineSettings.objects.update_or_create(
        line_id=line_id,
        defaults={'color': color, 'weight': weight, 'line_type': line_type},
    )
    return JsonResponse({'status': 'success', 'message': 'Line settings saved successfully'})


def build_tree(hosts):
    tree = {}

    for host in hosts:
        services = list(host.services.all())
        service_statuses = {service.status for service in services}
        if 'CRITICAL' in service_statuses:
            status = 'critical'
        elif 'WARNING' in service_statuses:
            status = 'warning'
        else:
            status = 'ok'

        decision = None
        if host.parents_id:
            decision = evaluate_segments(host.parents.segment, host.segment)

        tree[host.ipaddr] = {
            'ipaddr': host.ipaddr,
            'hostname': None if host.hostname == 'None' else host.hostname,
            'status': host.online,
            'status_serv': status,
            'section': host.place or 'Unknown',
            'latitude': host.latitude or 0,
            'longitude': host.longitude or 0,
            'SNMP': host.SNMP,
            'Uptime': host.uptime,
            'device_type': None if host.device_type == 'False' else host.device_type,
            'is_gateway': False,
            'children': [],
            'services': [
                {
                    'name': service.description,
                    'status': service.status,
                    'status_information': service.status_information or 'N/A',
                    'last_checked': (
                        timezone.localtime(service.last_checked).strftime('%Y-%m-%d %H:%M:%S')
                        if service.last_checked
                        else 'Never'
                    ),
                }
                for service in services
            ],
            'services_count': len(services),
            'services_critical': sum(service.status == 'CRITICAL' for service in services),
            'services_warning': sum(service.status == 'WARNING' for service in services),
            'services_ok': sum(service.status == 'OK' for service in services),
            'segment': host.segment.name if host.segment else None,
            'segment_color': host.segment.color if host.segment else None,
            'segmentation_allowed': decision.allowed if decision else None,
            'segmentation_reason': decision.reason if decision else None,
        }

    for host in hosts:
        if host.parents_id and host.parents.ipaddr in tree and host.parents_id != host.pk:
            tree[host.parents.ipaddr]['children'].append(host.ipaddr)

    for node in tree.values():
        node['children'] = sorted(set(node['children']) - {node['ipaddr']})
    return list(tree.values())


@login_required
@require_POST
def add_host(request):
    try:
        ip_address = _validated_ip(request.POST.get('ip_address'))
        latitude = float(request.POST.get('latitude'))
        longitude = float(request.POST.get('longitude'))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError('Coordinates are outside the valid range')

        host, created = Host.objects.get_or_create(ipaddr=ip_address)
        host.latitude = latitude
        host.longitude = longitude
        host.save(update_fields=['latitude', 'longitude'])
        return JsonResponse({'success': True, 'host_id': host.pk, 'created': created})
    except ObjectDoesNotExist:
        return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)


@login_required
def legacy_map(request) -> HttpResponse:
    hosts = Host.objects.select_related('parents').prefetch_related('services')
    lines = LineSettings.objects.all()
    return render(
        request,
        'front/map.html',
        {
            'tree': json.dumps(build_tree(hosts)),
            'hosts': json.dumps(
                [
                    {
                        'ipaddr': host.ipaddr,
                        'hostname': host.hostname,
                        'latitude': host.latitude,
                        'longitude': host.longitude,
                        'status': host.online,
                        'section': host.place,
                        'parent': host.parents.ipaddr if host.parents else None,
                    }
                    for host in hosts
                ]
            ),
            'line_settings': json.dumps(
                [
                    {
                        'line_id': line.line_id,
                        'color': line.color,
                        'weight': line.weight,
                        'line_type': line.line_type,
                    }
                    for line in lines
                ]
            ),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def positions(request):
    if request.method == 'GET':
        return JsonResponse(
            {position.ipaddr: {'x': position.x, 'y': position.y} for position in NodePosition.objects.all()}
        )

    try:
        data = json.loads(request.body)
        ip_address = _validated_node_id(data.get('ipaddr'))
        x = float(data.get('x'))
        y = float(data.get('y'))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    position, created = NodePosition.objects.update_or_create(
        ipaddr=ip_address,
        defaults={'x': x, 'y': y},
    )
    return JsonResponse({'status': 'success', 'created': created, 'id': position.pk})


@login_required
@require_GET
def network_map(request) -> HttpResponse:
    hosts = list(
        Host.objects.exclude(device_type='computers')
        .select_related('parents__segment', 'segment')
        .prefetch_related('services')
    )
    return render(request, 'front/map3.html', {'tree': json.dumps(build_tree(hosts))})
