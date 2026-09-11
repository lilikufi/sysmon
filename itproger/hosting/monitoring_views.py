import ipaddress
import logging
import platform
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import paramiko
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .forms import CheckForm
from .models import Host
from .services.monitoring_connection import (
    connector,
    password as passy,
    server_host as host,
    snmp_communities,
    username as usernamy,
)
from .services.snmp import get_device_identity


logger = logging.getLogger(__name__)


def validated_ip(value):
    """Return a normalized IP address or raise ValueError."""
    if not value:
        raise ValueError('IP address is required')
    return str(ipaddress.ip_address(value))


def validated_community(value):
    """Allow community values that are safe to interpolate into remote commands."""
    if not value or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,64}', value):
        raise ValueError('Invalid SNMP community')
    return value


@login_required
@require_GET
def get_snmp_info(request):
    results = defaultdict(lambda: defaultdict(list))
    for monitored_host in Host.objects.exclude(com_str__isnull=True).exclude(com_str=''):
        try:
            os_version, hostname, available = get_device_identity(
                monitored_host.ipaddr,
                monitored_host.com_str,
            )
        except (ValueError, RuntimeError):
            continue
        if not available:
            continue
        results[os_version or 'unknown'][hostname or monitored_host.ipaddr].append(
            monitored_host.ipaddr
        )
    return JsonResponse(results, safe=False)








@login_required
def hosting_create(request):
    error = ''
    if request.method == "POST":
        form = CheckForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/')
        else:
            error = 'The form was invalid'
    form = CheckForm()
    data = {
        'form': form,
        'error': error,

    }
    return render(request, 'hosting/create_host.html', data)




def process_host_data(item, community_string):
    ip = item.get("ip")
    community_strings = snmp_communities
    if not Host.objects.filter(ipaddr=ip).exists():
        host = Host(ipaddr=ip)
        host.online = True
        host.save()
        if check_remote_file_with_ip(ip):
            host.nagios_flag = True
            host.save()
        try:
            for community_string in community_strings:
                try:
                    job_2_command = f"snmpget -v1 {ip} -c {community_string} sysName.0"
                    job_2 = connector.run(job_2_command)
                    output = job_2.stdout
                    if "STRING: " in output:
                        host.hostname = output.split('STRING: ')[1].replace('\n', '')
                        host.SNMP = True
                        host.com_str = community_string
                        break
                except Exception as exc:
                    logger.warning('SNMP query failed for %s: %s', ip, exc)

            if host.SNMP:
                for row_2 in job_2.stdout.split('\n'):
                    if "SNMPv2-MIB" in row_2:
                        get_snmp_type = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.1.1.0 "
                        time.sleep(5)
                        job_5 = connector.run(get_snmp_type)
                        try:
                            if 'Lenovo' in job_5.stdout.replace('\n', ''):
                                host.osver = 'lenovosw'
                            elif 'QTECH' in job_5.stdout.replace('\n', ''):
                                host.osver = 'qtechsw'
                            elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                host.osver = 'dlinksw'
                            elif 'IOS' in job_5.stdout.replace('\n', ''):
                                host.osver = 'nexus'
                            elif 'Cisco' in job_5.stdout.replace('\n', ''):
                                host.osver = 'nexus'
                            elif 'UPS' in job_5.stdout.replace('\n', ''):
                                host.osver = 'UPS'
                            elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                    '\n', ''):
                                type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')
                                host.osver = type_osver_ups

                            elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                    '\n', ''):
                                type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')
                                host.osver = type_osver_ups

                        except (AttributeError, IndexError):
                            logger.debug('Unable to determine SNMP device type for %s', ip)
                        host.save()
        except Exception as exc:
            logger.warning('Unable to process SNMP data for %s: %s', ip, exc)
            return None

        host.save()
    else:
        host = Host(ipaddr=ip)
        if community_string != host.com_str:
            logger.debug('Host %s already exists with another community', ip)


def check_remote_file_with_ip(ip1):
    server_path = r"/usr/local/nagios/etc/objects/hosts/switches/"
    try:

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=usernamy, password=passy)
        job_3_command = f'grep -r  "{ip1}" {server_path}'
        time.sleep(5)
        stdin, stdout, stderr = ssh.exec_command(job_3_command)
        result = stdout.read().decode()
        error = stderr.read().decode()
        ssh.close()
        if error:
            logger.warning('Nagios configuration lookup failed: %s', error)
            return False
        return bool(result)

    except Exception as exc:
        logger.warning('Nagios configuration lookup failed: %s', exc)
        return False


@login_required
@require_POST
def range_ip(request):
    try:
        start_ip = ipaddress.IPv4Address(request.POST.get('start_ip'))
        end_ip = ipaddress.IPv4Address(request.POST.get('end_ip'))
        if end_ip < start_ip:
            raise ValueError('End IP must not be lower than start IP')

        address_count = int(end_ip) - int(start_ip) + 1
        if address_count > 1024:
            raise ValueError('The scan range is limited to 1024 addresses')

        community = request.POST.get('community_string') or 'public'
        community = validated_community(community)
        addresses = [ipaddress.IPv4Address(int(start_ip) + offset) for offset in range(address_count)]
        scan_results = {}

        def ping(ip):
            count_flag = '-n' if platform.system() == 'Windows' else '-c'
            response = subprocess.run(
                ['ping', count_flag, '1', str(ip)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            if response.returncode == 0:
                scan_results[ip.exploded] = 'online'

        with ThreadPoolExecutor(max_workers=min(32, address_count)) as executor:
            executor.map(ping, addresses)

        with ThreadPoolExecutor(max_workers=10) as executor:
            for ip in scan_results:
                executor.submit(process_host_data, {'ip': ip}, community)

        return redirect(reverse('scan'))
    except (ipaddress.AddressValueError, ValueError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)


@login_required
@require_GET
def check_snmp(request):
    try:
        ip_address = validated_ip(request.GET.get('ipaddr'))
        community = validated_community(request.GET.get('com_str'))
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

    if Host.objects.filter(ipaddr=ip_address).exists():
        return HttpResponse('already exists')

    count_flag = '-n' if platform.system() == 'Windows' else '-c'
    try:
        ping_result = subprocess.run(
            ['ping', count_flag, '1', ip_address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return HttpResponse('The ping command is not installed', status=503)
    except subprocess.TimeoutExpired:
        return HttpResponse('Availability check timed out', status=504)

    if ping_result.returncode != 0:
        return HttpResponse(f'{ip_address} is offline')

    try:
        os_version, hostname, available = get_device_identity(ip_address, community)
    except (ValueError, RuntimeError):
        available = False
        os_version = None
        hostname = None

    if not available:
        return HttpResponse('SNMP is not configured')

    device_label = os_version or 'unknown type'
    return HttpResponse(
        f'SNMP is configured. Host name {hostname}; type {device_label}. '
        'You can assign a new name by filling in the "Host name" form.'
    )
