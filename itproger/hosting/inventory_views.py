import datetime
import ipaddress
import os
import platform
import subprocess
from datetime import date
from pathlib import Path

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .forms import CheckForm
from .models import Host


@login_required
@require_GET
def ping_host(request, host_name):
    try:
        target = str(ipaddress.ip_address(host_name))
        count_flag = '-n' if platform.system() == 'Windows' else '-c'
        response = subprocess.run(
            ['ping', count_flag, '4', target],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except FileNotFoundError:
        return JsonResponse({'error': 'ping command is not installed'}, status=503)
    except subprocess.TimeoutExpired:
        return JsonResponse({'error': 'ping command timed out'}, status=504)
    return JsonResponse({'output': response.stdout or response.stderr})


@login_required
def saper(request):
    return render(request, 'front/saper.html')


@login_required
def snake(request):
    return render(request, 'front/snake.html')


@login_required
def tower(request):
    return render(request, 'front/tower.html')


@staff_member_required
def in_developing(request):
    return render(request, 'front/in_dev.html', {'host': os.getenv('NAG_SERVER')})


@login_required
def monitoring_log(request):
    log_path = Path(os.getenv('NAGIOS_STATUS_DIR', 'nagios_stat')) / 'nagios.log'
    try:
        lines = log_path.read_text(encoding='utf-8', errors='replace').splitlines(True)[-1000:]
    except OSError as exc:
        lines = [f'Ошибка чтения лога: {exc}']
    else:
        processed = []
        for line in lines:
            if line.startswith('[') and ']' in line:
                timestamp, remainder = line[1:].split(']', 1)
                try:
                    formatted = datetime.datetime.fromtimestamp(int(timestamp)).strftime(
                        '%Y-%m-%d %H:%M:%S'
                    )
                except (ValueError, OSError):
                    pass
                else:
                    line = f'[{formatted}]{remainder}'
            processed.append(line)
        lines = processed[::-1]
    return render(request, 'front/log.html', {'log_content': lines})


@login_required
def hosts(request):
    search_query = request.GET.get('search', '').strip()
    hosts_list = Host.objects.prefetch_related('services').order_by('-time_create')
    if search_query and 'reset' not in request.GET:
        hosts_list = hosts_list.filter(
            Q(ipaddr__icontains=search_query) | Q(hostname__icontains=search_query)
        )
    return render(
        request,
        'front/hosts.html',
        {'host': hosts_list, 'search_query': search_query},
    )


@login_required
def scan(request):
    form = CheckForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('scan')

    search_query = request.GET.get('search', '').strip()
    today_hosts = Host.objects.filter(time_create__date=date.today())
    all_hosts = Host.objects.exclude(time_create__date=date.today())
    if search_query:
        query = Q(ipaddr__icontains=search_query) | Q(hostname__icontains=search_query)
        today_hosts = today_hosts.filter(query)
        all_hosts = all_hosts.filter(query)

    return render(
        request,
        'front/scan.html',
        {
            'form': form,
            'error': '' if form.is_valid() or not form.is_bound else 'Форма была не верной',
            'today_hosts': today_hosts,
            'all_hosts': all_hosts,
            'search_query': search_query,
            'host': Host.objects.all(),
        },
    )
