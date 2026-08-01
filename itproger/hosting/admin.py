#
from .models import Host, HostGroup
from .models import *
from django.contrib import admin


# from .models import Hosting

# admin.site.register(Hosting)
class ServiceInline(admin.TabularInline):
    model = Service
    extra = 0
class HostAdmin(admin.ModelAdmin):
    list_display = ('ipaddr',
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
                    'place',
                    'longitude',
                    'latitude',


    )
    search_fields = ("ipaddr",)
    list_filter = ('cat','device_type')
    inlines = [ServiceInline]

class HostGroupAdmin(admin.ModelAdmin):
    list_display = ['name', ]

class ServiceAdmin(admin.ModelAdmin):
    list_display = ('host', 'description', 'status', 'last_checked','status_information')
    list_filter = ('status', 'host')
    search_fields = ('description', 'status')

admin.site.register(HostGroup, HostGroupAdmin)
admin.site.register(Host, HostAdmin)
admin.site.register(Service, ServiceAdmin)