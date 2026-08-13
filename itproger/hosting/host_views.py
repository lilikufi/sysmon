import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import DetailView

from .forms import CheckForm
from .models import Host
from .services.nagios import delete_host_configuration, sync_host_configuration
from .services.snmp import get_device_identity


MONITORING_CHECKS = (
    'cpu_5_min',
    'uptime',
    'mem_free',
    'mem_used',
    'mem_util',
    'bat_temp',
    'bat_time_work',
    'bat_vol',
    'run_reman',
    'stat_charge',
)


def _selected_checks(form):
    return [name for name in MONITORING_CHECKS if form.cleaned_data.get(name)]


def _refresh_snmp_identity(host, community):
    if not community:
        return
    try:
        os_version, hostname, available = get_device_identity(host.ipaddr, community)
    except (ValueError, RuntimeError):
        return
    host.SNMP = available
    if os_version:
        host.osver = os_version
    if hostname and not host.hostname:
        host.hostname = hostname


class HostDetailView(LoginRequiredMixin, DetailView):
    model = Host
    template_name = 'front/host_detail.html'
    context_object_name = 'host'




@login_required
def update_host(request, pk):
    monitored_host = get_object_or_404(Host, pk=pk)
    if request.method == 'GET':
        return render(
            request,
            'front/edit_host.html',
            {
                'form': CheckForm(instance=monitored_host),
                'host': monitored_host,
                'available_hosts': Host.objects.filter(nagios_flag=True).exclude(pk=pk),
            },
        )

    previous = (
        monitored_host.device_type,
        monitored_host.hostname or monitored_host.ipaddr,
    )
    form = CheckForm(request.POST, instance=monitored_host)
    if not form.is_valid():
        return render(
            request,
            'front/edit_host.html',
            {
                'form': form,
                'host': monitored_host,
                'available_hosts': Host.objects.filter(nagios_flag=True).exclude(pk=pk),
            },
            status=400,
        )

    monitored_host = form.save(commit=False)
    _refresh_snmp_identity(monitored_host, form.cleaned_data.get('com_str'))
    monitored_host.save()
    synced, message = sync_host_configuration(
        monitored_host,
        _selected_checks(form),
        previous=previous,
    )
    monitored_host.nagios_flag = synced
    monitored_host.save(update_fields=['nagios_flag'])
    if synced:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    return redirect('host-detail', pk=monitored_host.pk)


@login_required
@require_POST
def hide_host(request, pk):
    host = get_object_or_404(Host, pk=pk)
    host.hide_flag = True
    host.save(update_fields=['hide_flag'])

    return redirect('scan')


@login_required
@require_POST
def unhide_host(request):
    Host.objects.update(hide_flag=False)

    return redirect('scan')






@login_required
def create_host(request):
    if request.method == 'GET':
        return render(
            request,
            'front/create_host.html',
            {
                'form': CheckForm(),
                'error': '',
                'hosts': Host.objects.filter(nagios_flag=True).values_list('ipaddr', flat=True),
                'available_hosts': Host.objects.filter(nagios_flag=True),
            },
        )

    form = CheckForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            'front/create_host.html',
            {
                'form': form,
                'error': 'Форма была неверной',
                'hosts': Host.objects.filter(nagios_flag=True).values_list('ipaddr', flat=True),
                'available_hosts': Host.objects.filter(nagios_flag=True),
            },
            status=400,
        )

    existing = Host.objects.filter(ipaddr=form.cleaned_data['ipaddr']).first()
    if existing:
        messages.info(request, 'Хост с таким IP уже существует')
        return redirect('host-update', pk=existing.pk)

    monitored_host = form.save(commit=False)
    _refresh_snmp_identity(monitored_host, form.cleaned_data.get('com_str'))
    monitored_host.save()
    synced, message = sync_host_configuration(monitored_host, _selected_checks(form))
    monitored_host.nagios_flag = synced
    monitored_host.save(update_fields=['nagios_flag'])
    if synced:
        messages.success(request, message)
    else:
        messages.warning(request, message)
    return redirect('host-detail', pk=monitored_host.pk)




@login_required
@require_POST
def delete_host(request, pk):
    host = get_object_or_404(Host, pk=pk)

    if host.hostname is not None and host.hostname != 'None':
        status, message = delete_host_configuration(host.device_type, host.hostname)
        if status is True:
            host.delete()
            logging.info('Хост удален из Nagios и инвентаря: %s', message)
            messages.success(request, message)
        else:
            logging.error(message)
            messages.error(request, message)
    else:
        status, message = delete_host_configuration(host.device_type, host.ipaddr)
        if status is True:
            logging.info('Хост удален из Nagios и инвентаря: %s', host.ipaddr)
            host.delete()
            messages.success(request, message)
        else:
            logging.error(message)
            messages.error(request, message)
    return redirect('scan')
