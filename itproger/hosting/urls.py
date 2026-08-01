from django.urls import path

from . import views
from django.urls import path
from .views import positions_view
urlpatterns = [
    # path('hosting_home', views.hosting_home, name='hosting_home'),
    # path('fire', views.hosting_fire, name='hosting_fire'),
    # path('monitoring', views.hosting_fire, name='hosting_fire'),
    # path('<int:pk>', views.HostDetailView.as_view(), name='hosting_detail'),
    path('create', views.create_host, name='create_host'),
    path('hosting_create', views.hosting_create, name='hosting_create'),
    path('front', views.front, name='front'),
    path('range_ip/', views.range_ip, name='range_ip'),
    path('hosts/', views.hosts, name='hosts'),
    path('', views.service, name='service'),
    path('scan/', views.scan, name='scan'),
    path('<int:pk>', views.HostDetailView.as_view(), name='host-detail'),
    path('<int:pk>/update', views.update_host, name='host-update'),
    path('<int:pk>/hide', views.hide_host, name='host-hide'),
    path('unhide', views.unhide_host, name='host-unhide'),
    path('<int:pk>/delete', views.delete_host, name='host-delete'),
    path('check_snmp', views.check_snmp, name='check_snmp'),
    path('dev', views.in_developing, name='dev'),
    path('saper', views.saper, name='saper'),
    path('snake', views.snake, name='snake'),
    path('tower', views.tower, name='tower'),
    path('map', views.map, name='map'),
    path('mail', views.get_snmp_info, name='mail'),
    # path('copy', views.copy_stat_nagios, name='copy'),
    # path('check_hosts_status', views.check_hosts_status, name='stat_all'),
    path('ping/<str:host_name>/', views.ping_host, name='ping_host'),
    path('del_coord/<str:host_name>/', views.del_coord, name='del_coord'),
    path('add_host_map', views.add_host_map, name='add_host_map'),
    path('update_host_coordinates', views.update_host_coordinates, name='update_host_coordinates'),
    path('save_line_settings/',views.save_line_settings, name='save_line_settings'),
    path('save_route/',views.save_route, name='save_route'),
    path('api/graph/positions/', positions_view, name='graph_positions'),
    path('discover/', views.discover_network_view, name='discover_network'),
    path('api/discovery-status/', views.get_discovery_status, name='get_discovery_status'),
    path('api/get-host-id/', views.get_host_id_by_ip, name='get_host_id_by_ip'),
    path('api/open-terminal/', views.open_terminal, name='open-terminal'),
    # path('discover/', views.discover_network_view, name='discover_network'),
    # path('network-scan/', views.network_scan_view, name='network_scan'),

]
handler404 = 'accounts.views.my_custom_404_view'
