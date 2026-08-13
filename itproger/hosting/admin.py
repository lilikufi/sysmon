from django.contrib import admin

from .models import Host, HostGroup, NetworkSegment, SegmentPolicy, Service


class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0


class HostAdmin(admin.ModelAdmin):
    list_display = (
        'ipaddr',
        'hostname',
        'online',
        'SNMP',
        'com_str',
        'osver',
        'nagios_flag',
        'hide_flag',
        'parents',
        'time_create',
        'device_type',
        'segment',
        'place',
        'longitude',
        'latitude',
    )
    search_fields = ('ipaddr',)
    list_filter = ('cat', 'device_type', 'segment')
    inlines = [ServiceInline]


class HostGroupAdmin(admin.ModelAdmin):
    list_display = ['name']


class ServiceAdmin(admin.ModelAdmin):
    list_display = ('host', 'description', 'status', 'last_checked', 'status_information')
    list_filter = ('status', 'host')
    search_fields = ('description', 'status')


admin.site.register(HostGroup, HostGroupAdmin)
admin.site.register(Host, HostAdmin)
admin.site.register(Service, ServiceAdmin)


@admin.register(NetworkSegment)
class NetworkSegmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'default_action', 'color', 'host_count')
    search_fields = ('name', 'description')

    @admin.display(description='Hosts')
    def host_count(self, obj):
        return obj.hosts.count()


@admin.register(SegmentPolicy)
class SegmentPolicyAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'source',
        'destination',
        'action',
        'protocol',
        'port',
        'priority',
        'enabled',
    )
    list_filter = ('action', 'protocol', 'enabled', 'source', 'destination')
    search_fields = ('name',)
