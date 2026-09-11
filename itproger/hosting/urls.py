from django.urls import path

from . import (
    discovery_views,
    host_views,
    inventory_views,
    map_views,
    monitoring_views,
    terminal_views,
)


urlpatterns = [
    path('create', host_views.create_host, name='create_host'),
    path('hosting_create', monitoring_views.hosting_create, name='hosting_create'),
    path('front', inventory_views.monitoring_log, name='front'),
    path('range_ip/', monitoring_views.range_ip, name='range_ip'),
    path('hosts/', inventory_views.hosts, name='hosts'),
    path('', map_views.network_map, name='service'),
    path('scan/', inventory_views.scan, name='scan'),
    path('<int:pk>', host_views.HostDetailView.as_view(), name='host-detail'),
    path('<int:pk>/update', host_views.update_host, name='host-update'),
    path('<int:pk>/hide', host_views.hide_host, name='host-hide'),
    path('unhide', host_views.unhide_host, name='host-unhide'),
    path('<int:pk>/delete', host_views.delete_host, name='host-delete'),
    path('check_snmp', monitoring_views.check_snmp, name='check_snmp'),
    path('dev', inventory_views.in_developing, name='dev'),
    path('saper', inventory_views.saper, name='saper'),
    path('snake', inventory_views.snake, name='snake'),
    path('tower', inventory_views.tower, name='tower'),
    path('map', map_views.legacy_map, name='map'),
    path('mail', monitoring_views.get_snmp_info, name='mail'),
    path('ping/<str:host_name>/', inventory_views.ping_host, name='ping_host'),
    path('del_coord/<str:host_name>/', map_views.delete_coordinates, name='del_coord'),
    path('add_host_map', map_views.add_host, name='add_host_map'),
    path(
        'update_host_coordinates',
        map_views.update_host_coordinates,
        name='update_host_coordinates',
    ),
    path('save_line_settings/', map_views.save_line_settings, name='save_line_settings'),
    path('save_route/', map_views.save_route, name='save_route'),
    path('api/graph/positions/', map_views.positions, name='graph_positions'),
    path('discover/', discovery_views.discover_network, name='discover_network'),
    path(
        'api/discovery-status/',
        discovery_views.discovery_status,
        name='get_discovery_status',
    ),
    path('api/get-host-id/', terminal_views.get_host_id_by_ip, name='get_host_id_by_ip'),
    path('api/open-terminal/', terminal_views.open_terminal, name='open-terminal'),
]
handler404 = 'accounts.views.my_custom_404_view'
