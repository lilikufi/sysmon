import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from .network_discovery import NetworkDiscovery
import json
import threading
# Добавьте эти импорты в начало вашего views.py, если их там нет


import ipaddress
import logging
import os
import re
import subprocess
import threading
import time
import timeit
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date,  timedelta
from random import random
from django.utils import timezone
import paramiko
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.generic import DetailView, UpdateView, DeleteView
from fabric.connection import Connection

from .forms import CheckForm, CheckForm1
from .models import Host, Service
from .models import Route, LineSettings

# from rest_framework import request


port = 22
from dotenv import load_dotenv
load_dotenv()
port = 22
host = os.getenv('NAG_SERVER')
usernamy = os.getenv('NAG_USERNAME')
passy = os.getenv('NAG_PASSWORD')
snmp_communities = [
    value.strip()
    for value in os.getenv('SYSMON_SNMP_COMMUNITIES', 'public').split(',')
    if value.strip()
]
lenovo_snmp_community = os.getenv('SYSMON_LENOVO_SNMP_COMMUNITY', 'private')


class LazyMonitoringConnection:
    """Create the external SSH connection only when an integration action needs it."""

    def __init__(self):
        self._connection = None

    def run(self, *args, **kwargs):
        if not host:
            raise RuntimeError('NAG_SERVER is not configured')
        if self._connection is None:
            self._connection = Connection(
                host,
                port=port,
                user=usernamy,
                connect_kwargs={'password': passy},
            )
        return self._connection.run(*args, **kwargs)


connector = LazyMonitoringConnection()

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
def ping_host(request, host_name):
    try:
        target = validated_ip(host_name)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    count_flag = '-n' if platform.system() == 'Windows' else '-c'
    response = subprocess.run(
        ['ping', count_flag, '4', target],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    output = response.stdout or response.stderr
    return JsonResponse({'output': output})


@login_required
@require_POST
def del_coord(request, host_name):
    target = validated_ip(host_name)
    monitored_host = get_object_or_404(Host, ipaddr=target)
    monitored_host.latitude = 0.0
    monitored_host.longitude = 0.0
    monitored_host.save(update_fields=['latitude', 'longitude'])
    return JsonResponse({'success': True, 'message': 'Параметры хоста обнулены.'})

def is_net_user(user):
    return user.is_authenticated and (
        user.groups.filter(name='networker').exists()
    )


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
@login_required
def in_developing(request):
    return render(request, 'front/in_dev.html', {'host': host})


@login_required
def hosting_home(request):
    host = Host.objects.all()
    return render(request, 'hosting/hosting_home.html', {'host': host})


@login_required
def hosting_fire(request):
    return render(request, 'hosting/loading.html')


@login_required
@require_POST
def save_route(request):
    try:
        data = json.loads(request.body)
        parent = validated_ip(data.get('parent'))
        child = validated_ip(data.get('child'))
        waypoints = data.get('waypoints', [])
        if not isinstance(waypoints, list):
            raise ValueError('Waypoints must be a list')
        Route.objects.create(
            parent=Host.objects.get(ipaddr=parent),
            child=Host.objects.get(ipaddr=child),
            waypoints=waypoints,
        )
        return JsonResponse({'success': True})
    except (json.JSONDecodeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Host.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)


@login_required
@require_POST
def update_host_coordinates(request):
    if request.method == 'POST':
        try:
            ip_address = validated_ip(request.POST.get('ip_address'))
            latitude = float(request.POST.get('latitude'))
            longitude = float(request.POST.get('longitude'))

            # Проверка на наличие необходимых данных
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError('Coordinates are outside the valid range')

            # Обновление координат хоста
            host = Host.objects.get(ipaddr=ip_address)
            host.latitude = latitude
            host.longitude = longitude
            host.save()

            return JsonResponse({'success': True})

        except ObjectDoesNotExist:
            return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)
        except (TypeError, ValueError) as exc:
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)


@login_required
@require_POST
def save_line_settings(request):
    if request.method == 'POST':
        # Получаем данные из POST-запроса
        line_id = request.POST.get('line_id')
        color = request.POST.get('color')
        weight = request.POST.get('weight')
        line_type = request.POST.get('line_type')  # Новое поле для типа линии

        # Проверяем, что все обязательные поля присутствуют
        if not all([line_id, color, weight, line_type]):
            return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)
        try:
            weight = int(weight)
        except (TypeError, ValueError):
            return JsonResponse({'status': 'error', 'message': 'Invalid weight'}, status=400)
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}', color):
            return JsonResponse({'status': 'error', 'message': 'Invalid color'}, status=400)
        if not 1 <= weight <= 10:
            return JsonResponse({'status': 'error', 'message': 'Invalid weight'}, status=400)
        if line_type not in dict(LineSettings.LINE_TYPES):
            return JsonResponse({'status': 'error', 'message': 'Invalid line type'}, status=400)

        # Сохраняем или обновляем настройки линии
        line_settings, created = LineSettings.objects.get_or_create(line_id=line_id)
        line_settings.color = color
        line_settings.weight = weight
        line_settings.line_type = line_type  # Сохраняем тип линии
        line_settings.save()

        # Возвращаем успешный ответ
        return JsonResponse({'status': 'success', 'message': 'Line settings saved successfully'})

    # Если метод не POST, возвращаем ошибку
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@login_required
# @staff_member_required
def front(request):
    # copy_stat_nagios()
    log_path = 'nagios_stat/nagios.log'

    try:
        with open('nagios_stat/nagios.log', 'r') as f:
            lines = f.readlines()[-1000:]  # последние 1000 строк

        # Обработка строк с преобразованием временных меток
        processed_lines = []
        for line in lines:
            # Проверяем, начинается ли строка с временной метки в формате [timestamp]
            if line.startswith('[') and ']' in line:
                # Извлекаем timestamp
                timestamp_end = line.find(']')
                timestamp_str = line[1:timestamp_end]

                try:
                    # Пробуем преобразовать timestamp в читаемый формат
                    timestamp_int = int(timestamp_str)
                    dt_object = datetime.datetime.fromtimestamp(timestamp_int)
                    formatted_date = dt_object.strftime('%Y-%m-%d %H:%M:%S')

                    # Заменяем timestamp в строке на отформатированную дату
                    processed_line = f"[{formatted_date}]{line[timestamp_end + 1:]}"
                    processed_lines.append(processed_line)
                except (ValueError, OSError):
                    # Если не удалось преобразовать, оставляем строку как есть
                    processed_lines.append(line)
            else:
                processed_lines.append(line)

        lines = processed_lines[::-1]
    except Exception as e:
        lines = [f'Ошибка чтения лога: {str(e)}']

    return render(request, 'front/log.html', {'log_content': lines})
def build_tree(hosts):

    tree = {}

    # Создаем узел для 'sysmon'
    tree['sysmon'] = {
        'ipaddr': 'sysmon',
        'status': True,
        'status_serv': 'ok',
        'section': 'B',
        'children': [],
        'services': []  # Добавляем пустой список сервисов
    }


    # Создаем узлы для каждого хоста
    for host in hosts:
        # print("***************************************")
        # Собираем информацию о сервисах
        services_list = []
        status_serv = 'ok'
        if host.services.exists():
            for service in host.services.all():
                services_list.append({
                    'name': service.description,  # ✅ Используем description вместо name
                    'status': service.status,
                    'status_information': service.status_information or 'N/A',
                    'last_checked': timezone.localtime(service.last_checked).strftime('%Y-%m-%d %H:%M:%S') if service.last_checked else 'Never',

                })
                # print("service.last_checked", service.last_checked)

                # print('---------------------------------------------------------',services_list)
            # Определяем общий статус сервисов
            critical_services = host.services.filter(status='CRITICAL')
            warning_services = host.services.filter(status='WARNING')

            if critical_services.exists():
                status_serv = 'critical'
            elif warning_services.exists():
                status_serv = 'warning'

        # Исправляем некорректные значения
        device_type = host.device_type
        if device_type == "False":
            device_type = None

        hostname = host.hostname
        if hostname == "None":
            hostname = None

        tree[host.ipaddr] = {
            'ipaddr': host.ipaddr,
            'hostname': hostname,
            'status': host.online,
            'status_serv': status_serv,
            'section': host.place or 'Unknown',
            'latitude': host.latitude or 0,
            'longitude': host.longitude or 0,
            'SNMP': host.SNMP,
            'Uptime': host.uptime,
            'device_type': device_type,
            'is_gateway': False,
            'children': [],
            'services': services_list,  # ✅ Добавляем список сервисов
            'services_count': len(services_list),  # ✅ Количество сервисов
            'services_critical': host.services.filter(status='CRITICAL').count() if host.services.exists() else 0,
            'services_warning': host.services.filter(status='WARNING').count() if host.services.exists() else 0,
            'services_ok': host.services.filter(status='OK').count() if host.services.exists() else 0,
        }
        # print(services_list)
    # ... остальной код остаётся без изменений ...

    # Настраиваем связи между родителями и детьми
    processed_links = set()

    for host in hosts:
        if host.parents:
            parent_id = host.parents.ipaddr
            child_id = host.ipaddr

            link_key = f"{parent_id}-{child_id}"
            if (parent_id in tree and
                    child_id in tree and
                    link_key not in processed_links and
                    parent_id != child_id):
                tree[parent_id]['children'].append(child_id)
                processed_links.add(link_key)
        else:
            if host.ipaddr in tree and host.ipaddr != 'sysmon':
                tree['sysmon']['children'].append(host.ipaddr)

    # Удаляем циклические ссылки
    for node in tree.values():
        if node['ipaddr'] in node['children']:
            node['children'].remove(node['ipaddr'])
        node['children'] = list(set(node['children']))

    result = []
    for node in tree.values():
        result.append(node)

    return result
@login_required
@require_POST
def add_host_map(request):
    print("map")
    try:
        ip_address = validated_ip(request.POST.get('ip_address'))
        latitude = float(request.POST.get('latitude'))
        longitude = float(request.POST.get('longitude'))
        print(ip_address, latitude, longitude)

        # Проверка на наличие необходимых данных
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError('Coordinates are outside the valid range')

        # Получение или создание хоста
        host, created = Host.objects.get_or_create(ipaddr=ip_address)

        # Обновление координат хоста
        host.latitude = latitude
        host.longitude = longitude
        host.save()

        return JsonResponse({'success': True, 'host_id': host.id, 'created': created})

    except ObjectDoesNotExist:
        return JsonResponse({'success': False, 'error': 'Host not found'}, status=404)
    except (TypeError, ValueError) as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except Exception as e:
        print(f"Error occurred: {e}")  # Вывод ошибки в консоль
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

BUILDING_COORDINATES = {
    1: {"latitude": 55.06856374830317, "longitude": 38.79369020462036},  # Координаты для здания 1
    2: {"latitude": 55.0795, "longitude": 38.8005},  # Координаты для здания 2
    4: {"latitude": 55.0800, "longitude": 38.8010},  # Координаты для здания 4
    6: {"latitude": 55.0805, "longitude": 38.8015},  # Координаты для здания 6
}

# Функция для добавления случайного смещения
def add_random_offset(base_lat, base_lon, offset_range=0.0005):
    """
    Добавляет случайное смещение к базовым координатам.
    offset_range определяет максимальное смещение в градусах.
    """
    offset_lat = random.uniform(-offset_range, offset_range)
    offset_lon = random.uniform(-offset_range, offset_range)
    return base_lat + offset_lat, base_lon + offset_lon

@login_required
def map(request) -> HttpResponse:
    # Получение всех хостов
    hosts = Host.objects.all()

    # Получение всех настроек линий
    line_settings = LineSettings.objects.all()

    # Построение дерева из хостов
    tree = build_tree(hosts)

    # Создание списка хостов с координатами и состоянием служб
    hosts_data = []
    for host in hosts:

        if host.latitude == 0.0 or host.longitude == 0.0:
            print(host.ipaddr, host.longitude, host.latitude)
            host.latitude == 0.0
            host.longitude == 0.0
            # Получаем базовые координаты для здания
            if host.place in BUILDING_COORDINATES:
                print(f"FFFFFFFFFFFFFFFF {host.ipaddr}")
                base_lat = BUILDING_COORDINATES[host.place]["latitude"]
                base_lon = BUILDING_COORDINATES[host.place]["longitude"]

                # Добавляем случайное смещение
                host.latitude, host.longitude = add_random_offset(base_lat, base_lon)

                # Сохраняем новые координаты в базу данных
                host.save()
                print(f"Обновлены координаты для хоста {host.ipaddr}: {host.latitude}, {host.longitude}")
            else:
                print(f"Неизвестное здание для хоста {host.ipaddr}: {host.place}")
        # host.latitude, host.longitude = get_coordinates_from_hostname(host.hostname)
        #
        host.save()  # Сохраняем новые координаты в базу данных

        status_color = '#14FF47FF'  # По умолчанию зеленый
        if not host.online:
            status_color = '#FF1460FF'
        else:
            for service in host.services.all():
                if service.status == 'CRITICAL':
                    status_color = '#FF1460FF'
                    break
                elif service.status == 'WARNING' and status_color != '#FF1460FF':
                    status_color = '#FFEC07FF'

        hosts_data.append({
            'ipaddr': host.ipaddr,
            'hostname': host.hostname,
            'latitude': host.latitude,
            'longitude': host.longitude,
            'status': host.online,
            'section': host.place,
            'status_color': status_color,
            'parent': host.parents.ipaddr if host.parents else None
        })

    # Преобразование настроек линий в JSON
    line_settings_data = [
        {
            'line_id': line.line_id,
            'color': line.color,
            'weight': line.weight,
            'line_type': line.line_type
        }
        for line in line_settings
    ]

    # Конвертация данных в JSON
    tree_json = json.dumps(tree)
    hosts_json = json.dumps(hosts_data)
    line_settings_json = json.dumps(line_settings_data)

    # Сохранение дерева в файл (опционально)
    file_path = './data.json'
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(tree_json)

    # Отображение страницы с данными дерева, хостами и настройками линий
    return render(request, 'front/map.html', {
        'tree': tree_json,
        'hosts': hosts_json,
        'line_settings': line_settings_json
    })


from typing import Tuple  # Добавляем импорт

def get_coordinates_from_hostname(hostname: str) -> Tuple[float, float]:
    print(hostname)
    """
    Определяет координаты хоста на основе первых двух цифр в его имени.
    Например:
    - Если первые две цифры 04, хост попадает в регион A.
    - Если первые две цифры 06, хост попадает в регион B.
    """
    # Извлекаем первые две цифры из имени хоста
    second_digit = hostname[1] \
    if len(hostname) > 1 and hostname[1].isdigit() \
    else None
    number = int(hostname[:2])
    print(number)
    # Определяем регион на основе первых двух цифр
    if number == 1:
        return 55.07, 38.80 # Координаты для региона A (например, Москва)
    elif number == 2:
        return 59.9343, 30.3351  # Координаты для региона B (например, Санкт-Петербург)
    elif number == 3:
        return 54.9833, 73.3667  # Координаты для региона C (например, Омск)
    elif number == 4:
        return 56.8333, 60.5833  # Координаты для региона D (например, Екатеринбург)
    elif number == 5:
        return 55.0415, 82.9346  # Координаты для региона E (например, Новосибирск)
    elif number == 6:
        return 48.7194, 44.5018  # Координаты для региона F (например, Волгоград)
    else:
        return 0.0, 0.0  # Координаты по умолчанию
@login_required
def hosts(request):
    search_query = request.GET.get('search', '')
    hosts_list = Host.objects.prefetch_related('services').order_by('-time_create')

    if search_query and 'reset' not in request.GET:
        hosts_list = hosts_list.filter(ipaddr__icontains=search_query) | hosts_list.filter(
            hostname__icontains=search_query)
    return render(request, 'front/hosts.html', {
        'host': hosts_list,
        'search_query': search_query,
    })

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

from .models import NodePosition

@require_http_methods(["GET", "POST"])
@login_required  # по желанию, можно ограничить только staff
def positions_view(request):
    """Обработчик для сохранения позиций узлов с защитой от блокировок"""
    if request.method == 'GET':
        try:
            positions = {
                pos.ipaddr: {"x": pos.x, "y": pos.y}
                for pos in NodePosition.objects.all()
            }
            return JsonResponse(positions)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            ip = data.get('ipaddr')
            x = data.get('x')
            y = data.get('y')

            if not all([ip, x is not None, y is not None]):
                return JsonResponse({"error": "Missing required fields"}, status=400)

            # Используем update_or_create с транзакцией
            obj, created = NodePosition.objects.update_or_create(
                ipaddr=ip,
                defaults={"x": float(x), "y": float(y)}
            )

            return JsonResponse({"status": "success", "created": created})

        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


@login_required
def service(request) -> HttpResponse:
    # hosts = Host.objects.all().prefetch_related('services')
    hosts = Host.objects.exclude(device_type='computers').prefetch_related('services')
    # hosts = Host.objects.prefetch_related('services').select_related('parents').all()
    tree = build_tree(hosts)
    # print("hosts")
    # Конвертация дерева в JSON
    tree_json = json.dumps(tree)

    # Отображение страницы с данными дерева
    return render(request, 'front/map3.html', {'tree': tree_json})


@login_required
def scan(request):
    error = ''
    search_query = request.GET.get('search', '')
    if request.method == "POST":
        form = CheckForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('scan')
        else:
            error = 'Форма была не верной'
    form = CheckForm()

    # Получение хостов создания на сегодняшний день
    today_hosts = Host.objects.filter(time_create__date=date.today())
    all_hosts = Host.objects.exclude(time_create__date=date.today())

    # Фильтрация хостов по запросу поиска
    if search_query:
        today_hosts = today_hosts.filter(ipaddr__icontains=search_query) | today_hosts.filter(
            hostname__icontains=search_query)
        all_hosts = all_hosts.filter(ipaddr__icontains=search_query) | all_hosts.filter(
            hostname__icontains=search_query)

    data = {
        'form': form,
        'error': error,
        'today_hosts': today_hosts,
        'all_hosts': all_hosts,
        'search_query': search_query,  # Передаем поисковый запрос в шаблон
    }

    host = Host.objects.all()
    return render(request, 'front/scan.html', {'host': host, **data})


@login_required
def add_host(request):
    if request.method == "POST":
        form = CheckForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponse(status=204)
    else:
        form = CheckForm()
    return render(request, 'front/hosts.html', {
        'form': form,
    })


def get_snmp_info(request):
    results = defaultdict(lambda: defaultdict(list))

    # Получаем все хосты из базы данных
    hosts = Host.objects.all()

    for host in hosts:
        ip = host.ipaddr
        com = host.com_str

        # Формируем команду для snmpget
        get_snmp_type = f"snmpget -v1 {ip} -c {com} .1.3.6.1.2.1.1.1.0"
        time.sleep(5)

        try:
            # Выполняем команду
            job_5 = subprocess.check_output(get_snmp_type, shell=True, stderr=subprocess.STDOUT).decode('utf-8')

            # Обрабатываем вывод, чтобы получить строку с именем хоста
            full_name = job_5.split('STRING: ')[1].strip()

            # Фильтруем по типам
            type_key = 'unknown'
            if 'QTECH' in full_name:
                type_key = 'qtech'
            elif 'Cisco' in full_name:
                type_key = 'cisco'
            elif 'Lenovo' in full_name:
                type_key = 'lenovo'
            # Добавьте дополнительные условия для других типов по мере необходимости

            # Добавляем в результат
            results[type_key][full_name].append(ip)

        except subprocess.CalledProcessError as e:
            print('pupupu')
            # Обработка ошибок, например, если команда вернула ошибку
            # results['errors'].append(f"Error with {ip}: {str(e)}")

    # Конвертация результатов в JSON и возврат ответа
    return JsonResponse(results, safe=False)


def get_snmp_info_and_save_to_file():
    print('get_snmp_info_and_save_to_file')
    results = defaultdict(lambda: defaultdict(list))

    # Получаем все хосты из базы данных
    hosts = Host.objects.all()

    for host in hosts:
        ip = host.ipaddr
        com = host.com_strg

        # Формируем команду для snmpget
        get_snmp_command = f"snmpget -v1 {ip} -c {com} sysName.0"

        try:
            # Выполняем команду и получаем результат
            output = subprocess.check_output(get_snmp_command, shell=True, text=True)
            results[ip]['sysDescr'].append(output.strip())
        except subprocess.CalledProcessError as e:
            results[ip]['sysDescr'].append(f"Error: {e.output.strip()}")

    # Определяем путь к файлу для сохранения результатов
    file_path = './nagios_stat/type.json'  # или другой желаемый путь

    # Записываем результаты в файл
    with open(file_path, 'w') as json_file:
        json.dump(results, json_file, indent=4)

    print(f"SNMP results saved to {file_path}")


def get_snmp(ip, com):
    # print(f"начало get имя {com}")
    try:
        print('start get_snmp ')
        host = Host.objects.get(ipaddr=ip)
        # host.online = True # проверка онлайн он или нет ##### проверка должна быть постоянной?????

        try:
            ping_result = subprocess.run(['ping', '-c', '1', ip], stdout=subprocess.PIPE).returncode
            try:
                print('start')
                if ping_result == 0:
                    host.online = True
                    host.save()
                    print(f'{ip} в сети')
                else:
                    print(f'{ip} не в сети')
            except Exception as e:
                print('')
            try:
                print('*_*')
                job_2_command = f"snmpget -v1 {ip} -c {com} sysName.0"
                job_2 = connector.run(job_2_command)
                host.SNMP = True
                # break
            except Exception as e:
                print(f"Ошибка при выполнении команды SNMP: {e}")
                host.SNMP = False
        except:
            print(f"Не в сети")
            host.online = False
        if host.SNMP:
            for row_2 in job_2.stdout.split('\n'):

                if "SNMPv2-MIB" in row_2:
                    print(f"SNMP на {ip} настроен")
                    get_snmp_type = f"snmpget -L n -v1 {ip} -c {com} .1.3.6.1.2.1.1.1.0"  # получаем стринг и имя хоста
                    job_5 = connector.run(get_snmp_type)
                    full_name = job_5.stdout.split('STRING: ')[1].replace('\n', '')  # полное имя коммутатора и его тип
                    print('job_5:', full_name)
                    try:
                        if 'Lenovo' in job_5.stdout.replace('\n', ''):
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'lenovosw'
                        elif 'QTECH' in job_5.stdout.replace('\n', ''):
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'qtechsw'
                        elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'dlinksw'
                        elif 'IOS' in job_5.stdout.replace('\n', ''):  ###### переделать это
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'nexus'
                        elif 'Cisco' in job_5.stdout.replace('\n', ''):
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'nexus'


                        elif 'UPS' in job_5.stdout.replace('\n', ''):
                            print('Тип и полное имя хоста', full_name)
                            host.osver = 'UPS'
                        elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                '\n', ''):

                            get_name_ups = f"snmpget -L n -v1 {ip} -c {com}  .1.3.6.1.2.1.33.1.1.5.0"
                            job_get_name_ups = connector.run(get_name_ups)
                            hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                               '')  # полное имя коммутатора и его тип
                            print('job_get_name_ups apc36CA32:', hostname111)
                            type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                       '')
                            print('type_osver_ups', type_osver_ups)
                            host.osver = type_osver_ups

                        elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                '\n', ''):

                            get_name_ups = f"snmpget -L n -v1 {ip} -c {com}  .1.3.6.1.2.1.33.1.1.5.0"
                            job_get_name_ups = connector.run(get_name_ups)
                            hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                               '')  # полное имя коммутатора и его тип
                            print('job_get_name_ups:', hostname111)
                            type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                       '')
                            print('type_osver_ups', type_osver_ups)
                            host.osver = type_osver_ups
                        else:
                            print('Пропуск:', ip)


                    except:

                        print('Пропуск:', ip)
                        continue
        print('host.osver get snmp:', host.osver)

        host.save()
        if host.SNMP == True:
            return True, host.osver
    except:
        return False


def is_valid_ip_address(ip_address):
    # Проверяем, соответствует ли IP-адрес формату IPv4
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip_address):
        # Разбиваем IP-адрес на октеты
        octets = ip_address.split(".")

        # Проверяем, что каждый октет находится в диапазоне от 0 до 255
        for octet in octets:
            if int(octet) < 0 or int(octet) > 255:
                return False

        return True

    # IP-адрес не соответствует формату IPv4
    else:
        return False


@login_required
def hosting_create(request):
    error = ''
    if request.method == "POST":
        form = CheckForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('/')
        else:
            error = 'Форма была не верной'
    form = CheckForm()
    data = {
        'form': form,
        'error': error,

    }
    return render(request, 'hosting/create_host.html', data)


def collect(request):
    req = request
    if req.POST:
        vendor = req.POST.get('Product_Name')
        sn = req.POST.get('Serial_Number')
        product = req.POST.get('Manufacturer')
        cpu_model = req.POST.get('Model_Name')
        cpu_num = req.POST.get('Cpu_Cores')
        cpu_vendor = req.POST.get('Vendor_Id')
        memory_part_number = req.POST.get('Part_Number')
        memory_manufacturer = req.POST.get('Manufacturer')
        memory_size = req.POST.get('Size')
        device_model = req.POST.get('Device_Model')
        device_version = req.POST.get('Firmware_Version')
        device_sn = req.POST.get('Serial_Number')
        device_size = req.POST.get('User_Capacity')
        osver = req.POST.get('os_version')
        hostname = req.POST.get('os_name')
        os_release = req.POST.get('os_release')
        ipaddrs = req.POST.get('Ipaddr')
        mac = req.POST.get('Device')
        link = req.POST.get('Link')
        mask = req.POST.get('Mask')
        device = req.POST.get('Device')
        host = Host()
        host.hostname = hostname
        host.product = product
        host.cpu_num = cpu_num
        host.cpu_model = cpu_model
        host.cpu_vendor = cpu_vendor
        host.memory_part_number = memory_part_number
        host.memory_manufacturer = memory_manufacturer
        host.memory_size = memory_size
        host.device_model = device_model
        host.device_version = device_version
        host.device_sn = device_sn
        host.device_size = device_size
        host.osver = osver
        host.os_release = os_release
        host.vendor = vendor
        host.sn = sn
        host.ipaddr = ipaddrs
        host.save()

        return HttpResponse('OK')
    else:
        return HttpResponse('no post data')


def process_host_data(item, community_string):
    print('Processing')
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
                        break  # Если нашли правильную строку сообщества, выходим из цикла
                except Exception as e:
                    print(f"Ошибка при выполнении команды SNMP: {e}")

            if host.SNMP:
                print(f"SNMP успешно настроен. Hostname: {host.hostname}, Community String: {host.com_str}")
            else:
                print("Не удалось настроить SNMP с данными строками сообщества.")

            if host.SNMP:
                for row_2 in job_2.stdout.split('\n'):
                    #
                    if "SNMPv2-MIB" in row_2:
                        print(f"SNMP на {ip} настроен")
                        get_snmp_type = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.1.1.0 "
                        time.sleep(5)  # получаем стринг и имя хоста
                        # time.sleep(5)
                        job_5 = connector.run(get_snmp_type)
                        full_name = job_5.stdout.split('STRING: ')[1].replace('\n',
                                                                              '')  # полное имя коммутатора и его тип
                        print('job_5:', full_name)
                        try:
                            if 'Lenovo' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'lenovosw'
                            elif 'QTECH' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'qtechsw'
                            elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'dlinksw'
                            elif 'IOS' in job_5.stdout.replace('\n', ''):  ###### переделать это
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'nexus'
                            elif 'Cisco' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'nexus'
                            elif 'UPS' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'UPS'
                            elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                    '\n', ''):

                                get_name_ups = f"snmpget -L n -v1{ip} -c {community_string} .1.3.6.1.2.1.33.1.1.5.0"
                                job_get_name_ups = connector.run(get_name_ups)
                                hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                   '')  # полное имя коммутатора и его тип
                                print('job_get_name_ups apc36CA32:', hostname111)
                                type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')
                                print('type_osver_ups', type_osver_ups)
                                host.osver = type_osver_ups

                            elif 'APC' in job_5.stdout.replace('\n', '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                    '\n', ''):

                                get_name_ups = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.33.1.1.5.0"
                                job_get_name_ups = connector.run(get_name_ups)
                                hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                   '')  # полное имя коммутатора и его тип
                                print('job_get_name_ups:', hostname111)
                                type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')
                                print('type_osver_ups', type_osver_ups)
                                host.osver = type_osver_ups


                        except:
                            print('Пропуск:', ip)
                            # continue
                        host.save()
        except Exception as e:
            print(f"Error getting SNMP data for {ip}: {str(e)}")
            return None

        host.save()
    # elif  Host.objects.filter(ipaddr=ip).exists():
    else:
        host = Host(ipaddr=ip)
        if community_string != host.com_str:
            print("different comstring *-*")


def check_remote_file_with_ip(ip1):
    print("check_remote_file_with_ip")

    server_path = fr"/usr/local/nagios/etc/objects/hosts/switches/"
    try:

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=usernamy, password=passy)
        # ssh.connect(host, port, usernamy, passy)
        job_3_command = f'grep -r  "{ip1}" {server_path}'
        time.sleep(5)
        print('job_3_command:', job_3_command)
        stdin, stdout, stderr = ssh.exec_command(job_3_command)
        result = stdout.read().decode()
        print('result:', result)
        error = stderr.read().decode()
        ssh.close()
        if error:
            print(f"Error occurred: {error}")
        else:
            if result:
                return True  # Файл существует
                # return f'File(s) containing the IP {ip} found on the remote server:\n{result}'
            else:
                return False  # Файл не существует

    except Exception as e:
        print(f"An error occurred: {str(e)}")


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


class HostDetailView(LoginRequiredMixin, DetailView):
    model = Host
    template_name = 'front/host_detail.html'
    context_object_name = 'host'


def get_osver_via_snmp(ip_addr, community_string):
    """Определяет osver устройства через SNMP"""
    osver = None
    hostname = None
    snmp_available = False

    try:
        # Проверяем доступность SNMP
        job_2_command = f"snmpget -v1 {ip_addr} -c {community_string} sysName.0"
        job_2 = connector.run(job_2_command)
        snmp_available = True

        for row_2 in job_2.stdout.split('\n'):
            if 'NMC' in row_2:
                print('NMC detected')
                # Это UPS с NMC
                get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} iso.3.6.1.2.1.33.1.1.5.0"
                job_get_name_ups = connector.run(get_name_ups)
                hostname = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n', '')

                type_osver_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} iso.3.6.1.2.1.33.1.1.2.0"
                job_type_osver_ups = connector.run(type_osver_ups)
                osver = job_type_osver_ups.stdout.split('STRING: ')[1].replace('\n', '')
                print(f'UPS osver: {osver}, hostname: {hostname}')

            elif "STRING: " in row_2:
                print('STRING detected')
                hostname = row_2.split('STRING: ')[1].replace('\n', '')

                # Получаем тип устройства
                get_snmp_type = f"snmpget -L n -v1 {ip_addr} -c {community_string} .1.3.6.1.2.1.1.1.0"
                time.sleep(2)
                job_5 = connector.run(get_snmp_type)

                try:
                    full_name = job_5.stdout.split('STRING: ')[1].replace('\n', '')
                    output = job_5.stdout.replace('\n', '')
                    print(f'Device full name: {full_name}')

                    if 'Lenovo' in output:
                        osver = 'lenovosw'
                    elif 'QTECH' in output:
                        osver = 'qtechsw'
                    elif 'DGS-1210-10' in output:
                        osver = 'dlinksw'
                    elif 'IOS' in output:
                        osver = 'nexus'
                    elif 'Cisco' in output:
                        osver = 'nexus'
                    elif 'UPS' in output:
                        get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} 1.3.6.1.2.1.33.1.1.5.0"
                        job_get_name_ups = connector.run(get_name_ups)
                        hostname = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n', '')

                        get_type_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} 1.3.6.1.2.1.33.1.1.2.0"
                        job_type_ups = connector.run(get_type_ups)
                        osver = job_type_ups.stdout.split('STRING: ')[1].replace('\n', '')

                    elif 'APC' in output and 'apc_hw05_aos_682' in output:
                        get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} .1.3.6.1.2.1.33.1.1.5.0"
                        job_get_name_ups = connector.run(get_name_ups)
                        hostname = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n', '')
                        osver = job_2.stdout.split('STRING: ')[1].replace('\n', '')

                    elif 'APC' in output and 'apc_hw05_aos_513' in output:
                        osver = 'apc_hw05_aos_513'

                    print(f'Detected osver: {osver}')

                except Exception as e:
                    print(f'Ошибка при парсинге SNMP ответа: {e}')

    except Exception as e:
        print(f"Ошибка при определении osver через SNMP: {e}")

    return osver, hostname, snmp_available

@login_required
def update_host(request, pk):
    parent_ip = None
    host = get_object_or_404(Host, pk=pk)
    host.save()
    parents_host = host.parents
    old_name = host.hostname
    old_ip = host.ipaddr
    old_device_type = host.device_type
    if request.method == 'POST':
        form = CheckForm(request.POST, instance=host)
        print("host.parents.33", host.parents)
        if form.is_valid():
            form.save()
            if host.parents:
                parent_ip = host.parents.ipaddr

            # Получение данных из формы
            ip_addr = form.cleaned_data['ipaddr']
            host_name = form.cleaned_data['hostname']
            parents_ff = form.cleaned_data['parents']
            print('parents', parents_ff, host.osver)

            if parents_ff is not None:
                parent_ip = parents_ff.ipaddr
                if parents_ff.hostname:
                    parent_ip = parents_ff.hostname
                else:
                    parent_ip = parents_ff.ipaddr
            # else:
            #     if host.parents is not None:
            #
            #         if host.parents.hostname:
            #             parent_ip = host.parents.hostname
            #         else:
            #             parent_ip = host.parents.ipaddr

            community_string = form.cleaned_data['com_str']

            if not old_name:
                old_name = ip_addr
            elif old_name == 'None':
                old_name = ip_addr

            cpu_5_min = form.cleaned_data.get('cpu_5_min', False)
            uptime = form.cleaned_data.get('uptime', False)
            mem_free = form.cleaned_data.get('mem_free', False)
            mem_used = form.cleaned_data.get('mem_used', False)
            mem_util = form.cleaned_data.get('mem_util', False)
            bat_temp = form.cleaned_data.get('bat_temp', False)
            bat_time_work = form.cleaned_data.get('bat_time_work', False)
            bat_vol = form.cleaned_data.get('bat_vol', False)
            run_reman = form.cleaned_data.get('run_reman', False)
            stat_charge = form.cleaned_data.get('stat_charge', False)

            device_type = form.cleaned_data['device_type']

            if host.device_type:
                print("*")
                print(device_type, old_device_type, old_name, old_ip)
                if device_type != old_device_type:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(hostname=host, username=usernamy, password=passy)
                    # ssh.connect(host, port, usernamy, passy)
                    remove_old_type_file = f'rm -f /usr/local/nagios/etc/objects/hosts/{old_device_type}/{old_name}.cfg'
                    # time.sleep(5)
                    ssh.exec_command(remove_old_type_file)
                    print('remove_old_type_file:', remove_old_type_file)
                    ssh.close()

            print('device_type', device_type)
            if device_type == 'switches':
                gen_group = "generic-switch"
            elif device_type == 'servers':
                gen_group = "generic-server"
            elif device_type == 'network-printers':
                gen_group = "generic-printer"
            elif device_type == 'UPS':
                gen_group = "generic-UPS"
            host.nagios_flag = True

            host.save()

            # get_snmp(ip_addr, community_string)
            # host = Host.objects.get(ipaddr=ip_addr)
            # print('host.hostname', host.hostname)
            host_name = host.hostname

            # print("host________name", host_name)
            if not host_name:
                host_name = host.hostname
                # print("host.hostname", host.hostname)

            selected_checks = [key for key in form.cleaned_data if
                               form.cleaned_data[key] and isinstance(form.cleaned_data[key], bool)]
            # генерация файла на основе данных из формы
            if not host_name:
                host_name = ip_addr
            elif host_name == 'None':
                host_name = ip_addr

            if host.osver == 'None' or host.osver == None:
                print("$$$$$$$$$$$$$$$$")
                detected_osver, detected_hostname, snmp_ok = get_osver_via_snmp(ip_addr, community_string)

                if detected_osver:
                    host.osver = detected_osver
                    print(f"osver определён: {detected_osver}")

                if detected_hostname and (not host.hostname or host.hostname == 'None'):
                    host.hostname = detected_hostname
                    host_name = detected_hostname  # обновляем локальную переменную
                    print(f"hostname определён: {detected_hostname}")

                if snmp_ok:
                    host.SNMP = True

                host.save()
            # print("hostname create0", host_name)
            file_name = host_name if host_name else ip_addr
            file_path = fr"/usr/local/nagios/etc/objects/hosts/{device_type}/{file_name}.cfg"
            print(file_path)
            print('host.ipaa222', host.ipaddr, host.parents, host.SNMP)

            with paramiko.SSHClient() as ssh_client:
                ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh_client.connect(hostname=host, username=usernamy, password=passy)
                # Запись данных в файл на удаленном сервере
                with ssh_client.open_sftp() as sftp:
                    with sftp.file(file_path, 'w') as config_file:
                        # Запись основных данных в файл
                        config_file.write('define host {\n')
                        config_file.write(f'\tuse\t\t{gen_group}\n')
                        config_file.write(f'\thost_name\t{host_name}\n')
                        config_file.write(f'\taddress\t\t{ip_addr}\n')
                        config_file.write(f'\thost_groups\t{device_type}\n')

                        # if parent_ip != 'None' and parent_ip is not None:
                        #     config_file.write(f'\tparents\t{parent_ip}\n')
                        #
                        if device_type == "servers":
                            config_file.write(f'\ticon_image\tserver-1.png\n')
                        config_file.write('}\n')
                        config_file.write('\n')
                        config_file.write('\n')
                        config_file.write('define service {\n')
                        config_file.write('\tuse\t\tping-service\n')
                        config_file.write(f'\thost_name\t{host_name}\n')
                        config_file.write('}\n')
                        config_file.write('\n')
                        config_file.write('\n')
                        print('host.ipaa', host.ipaddr, host.SNMP)
                        if host.SNMP and host.osver is not None and host.osver != 'None':
                            # Добавление сервисов согласно выбранным пунктам
                            for sdescription in selected_checks:
                                # host = Host.objects.get(ipaddr=ip_addr)
                                type_sw = host.osver
                                if community_string == lenovo_snmp_community and type_sw == "lenovosw":
                                    service = 'service-private'
                                else:
                                    service = 'service'
                                serv_dict = {
                                    # 'cpu_1_min': {'use_command': f'check_snmp_cpu_load_1_min_{type_sw}-service', 'description': 'CPU Load 1 Min' if cpu_1_min else ''},
                                    'cpu_5_min': {'use_command': f'check_snmp_cpu_{type_sw}-service-private',
                                                  'description': 'CPU 5 min load' if cpu_5_min else ''},
                                    'uptime': {'use_command': 'uptime-service',
                                               'description': 'Uptime' if uptime else ''},
                                    'mem_free': {'use_command': f'check_snmp_memory_free_{type_sw}-{service}',
                                                 'description': 'Memory Free' if mem_free else ''},
                                    'mem_used': {'use_command': f'check_snmp_memory_used_{type_sw}-{service}',
                                                 'description': 'Memory Used' if mem_used else ''},
                                    'mem_util': {'use_command': f'check_snmp_memory_utl_{type_sw}-{service}',
                                                 'description': 'Memory Utilization' if mem_util else ''},
                                    'bat_temp': {'use_command': 'upstemp',
                                                 'description': 'Battery Temperature' if bat_temp else ''},
                                    'bat_time_work': {'use_command': f'ups_time_work_on_battery',
                                                      'description': ' Battery Time Work' if bat_time_work else ''},
                                    'bat_vol': {'use_command': f'ups_volt',
                                                'description': 'Battery Voltage' if bat_vol else ''},
                                    'run_reman': {'use_command': f'ups_battery_run_time_remaining',
                                                  'description': 'Runtime Remaining' if run_reman else ''},
                                    'stat_charge': {'use_command': f'ups_bat_stat',
                                                    'description': 'State of Charge' if stat_charge else ''},

                                }
                                use_command = serv_dict[sdescription][
                                    'use_command']  # Получение нужного значения из словаря
                                description = serv_dict[sdescription][
                                    'description']  # Получение нужного значения из словаря

                                config_file.write('define service {\n')
                                config_file.write(f'\tuse\t\t\t{use_command}\n')
                                config_file.write(f'\tservice_description\t{description}\n')
                                config_file.write(f'\thost_name\t\t{host_name}\n')
                                config_file.write('}\n')
                                config_file.write('\n')
                                config_file.write('\n')
                        else:
                            error = "Не настроен SNMP для отслеживания служб"
                            print('error', error)
                try:

                    # logging.info(f"Ошибка: Хост удален везде: {file_path}")
                    reload_cm = 'sudo systemctl restart nagios'
                    reload = ssh_client.exec_command(reload_cm)
                    # reload = connector.run(reload_cm)

                    print("reload ", reload)
                    if "" in reload_cm:
                        print('в нагиос все ок')
                        messages.success(request, 'Хост успешно обновлен')
                    else:
                        remove_command = f'remove {file_path}'
                        ssh_client.exec_command(
                            f'mv  /usr/local/nagios/etc/objects/hosts/{device_type}/{host_name}.cfg /usr/local/nagios/etc/objects/bag/ ')
                        host.nagios_flag = False
                        # r_2 = ssh_client.exec_command(remove_command)
                        # output = r_2.stdout
                        # print('output', output)
                        messages.error(request, ' Ошибка в Nagios, хост  удален')
                        print(' Ошибка в Nagios, хост  удален')


                except TypeError as e:
                    if str(e) == "'NoneType' object is not iterable" or str(e) == "'int' object is not iterable":
                        print("object is not iterable")
                    else:
                        print("object is not iterable2")

                except Exception as e:
                    print(f'except {e}')
                    message = f"Ошибка: Хост  {file_path} except {e}"
                    # send_error_email(message, "except")
                    # # remove_command = f'remove {file_path}'
                    ssh_client.exec_command(
                        f'mv  "/usr/local/nagios/etc/objects/hosts/{device_type}/{host_name}.cfg" "/usr/local/nagios/etc/objects/bag/" ')
                    host.nagios_flag = False
                    # "/usr/local/nagios/etc/objects/bag/"
                    # print('remove_command:', remove_command)
                    ssh.close()
                    # print('проверка не удалась ')
                    # host.delete()
                    logging.error(f"Ошибка: Хост удален везде: {file_path}")
                    messages.error(request, ' Ошибка в Nagios, хост в Nagios удален, обратитесь к администратору')
                return redirect('/')
            ssh_client.close()

            return redirect('/')
            # return redirect(requests.Meta.get('HTTP_REFERER','default_url'))
    else:
        form = CheckForm(instance=host)

    available_hosts = Host.objects.filter(nagios_flag=True).exclude(id=host.id)
    data = {
        'form': form,
        'host': host,
        'available_hosts': available_hosts,
    }
    return render(request, 'front/edit_host.html', data)


@login_required
@require_POST
def hide_host(request, pk):
    host = get_object_or_404(Host, pk=pk)
    print('host {host}')
    host.hide_flag = True
    host.save()

    # return redirect('/')
    return redirect('scan')


@login_required
@require_POST
def unhide_host(request):
    Host.objects.update(hide_flag=False)

    # return redirect('/')
    return redirect('scan')


class HostUpdateView(LoginRequiredMixin, UpdateView):
    ''''Перестал отображаться ip'''
    model = Host
    template_name = 'front/edit_host.html'
    form_class = CheckForm1
    success_url = '/'


class HostDeleteView(LoginRequiredMixin, DeleteView):
    model = Host
    success_url = '/'
    template_name = 'front/host_delete.html'


@login_required
# @staff_member_required
def create_host(request):
    print('Create a new host in Nagios')
    error = ''
    available_hosts = Host.objects.filter(nagios_flag=True)

    hosts = Host.objects.filter(nagios_flag=True).values_list('ipaddr', flat=True)
    try:

        if request.method == "POST":
            form = CheckForm(request.POST)
            if form.is_valid():

                # Получение данных из формы
                ip_addr = form.cleaned_data['ipaddr']
                host_name = form.cleaned_data['hostname']
                community_string = form.cleaned_data['com_str']
                print(f"com {community_string}")

                parents = form.cleaned_data['parents']

                print('parents', parents)
                if parents is not None:
                    if parents.hostname:
                        parent_ip = parents.hostname
                    else:
                        parent_ip = parents.ipaddr
                # else:
                #     if parents is not None:
                #
                #         if parents.hostname:
                #             parent_ip = parents.hostname
                #         else:
                #             parent_ip = parents.ipaddr

                device_type = form.cleaned_data['device_type']
                print('device_type', device_type)
                if device_type == 'switches':
                    gen_group = "generic-switch"
                elif device_type == 'servers':
                    gen_group = "generic-server"
                elif device_type == 'network-printers':
                    gen_group = "generic-printer"
                elif device_type == 'UPS':
                    gen_group = "generic-UPS"

                cpu_5_min = form.cleaned_data.get('cpu_5_min', False)
                uptime = form.cleaned_data.get('uptime', False)
                mem_free = form.cleaned_data.get('mem_free', False)
                mem_used = form.cleaned_data.get('mem_used', False)
                mem_util = form.cleaned_data.get('mem_util', False)
                bat_temp = form.cleaned_data.get('bat_temp', False)
                bat_time_work = form.cleaned_data.get('bat_time_work', False)
                bat_vol = form.cleaned_data.get('bat_vol', False)
                run_reman = form.cleaned_data.get('run_reman', False)
                stat_charge = form.cleaned_data.get('stat_charge', False)

                if Host.objects.filter(ipaddr=ip_addr).exists():
                    host = Host.objects.get(ipaddr=ip_addr)
                    return redirect('host-update', host.id)
                    print('host already exists')
                    # error = f"Хост  {ip_addr} уже существует в базе данных, проверьте страницу scan"
                    # print('error', error)

                elif not Host.objects.filter(ipaddr=ip_addr).exists():
                    form.save()
                    host = Host.objects.get(ipaddr=ip_addr)
                    # host_name = host.hostname
                    host.parents = parents
                    try:
                        print('start get_snmp ')

                        # host.online = True # проверка онлайн он или нет ##### проверка должна быть постоянной?????

                        try:
                            ping_result = subprocess.run(['ping', '-c', '1', ip_addr],
                                                         stdout=subprocess.PIPE).returncode
                            try:
                                print('start')
                                if ping_result == 0:
                                    host.online = True
                                    host.save()
                                    print(f'{ip_addr} в сети')
                                else:
                                    print(f'{ip_addr} не в сети')
                            except Exception as e:
                                print('')
                            try:
                                print('*_*')
                                job_2_command = f"snmpget -v1 {ip_addr} -c {community_string} sysName.0"
                                job_2 = connector.run(job_2_command)
                                host.SNMP = True
                                # break
                            except Exception as e:
                                print(f"Ошибка при выполнении команды SNMP: {e}")
                                host.SNMP = False
                        except:
                            print(f"Не в сети")
                            host.online = False
                        if host.SNMP:
                            for row_2 in job_2.stdout.split('\n'):

                                if 'NMC' in row_2:
                                    print('nmc')

                                    get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string}  iso.3.6.1.2.1.33.1.1.5.0 "
                                    job_get_name_ups = connector.run(get_name_ups)
                                    hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                       '')  # полное имя коммутатора и его тип
                                    print('job_get_name_ups:', hostname111)

                                    type_osver_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string}  iso.3.6.1.2.1.33.1.1.2.0 "
                                    job_type_osver_ups = connector.run(get_name_ups)
                                    osver = job_type_osver_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                   '')  # полное имя коммутатора и его тип
                                    print('job_type_osver_ups:', osver)

                                elif "STRING: " in row_2:
                                    print('string')
                                    hostname111 = row_2.split('STRING: ')[1].replace('\n', '')
                                    get_snmp_type = f"snmpget -L n -v1 {ip_addr} -c {community_string} .1.3.6.1.2.1.1.1.0 "
                                    time.sleep(5)  # получаем стринг и имя хоста jhgbbnmnbhjbmnb
                                    # time.sleep(5)
                                    job_5 = connector.run(get_snmp_type)
                                    full_name = job_5.stdout.split('STRING: ')[1].replace('\n',
                                                                                          '')  # полное имя коммутатора и его тип
                                    print('job_5:', full_name)

                                    try:
                                        if 'Lenovo' in job_5.stdout.replace('\n', ''):
                                            print('Тип и полное имя хоста', full_name)
                                            host.osver = 'lenovosw'
                                        elif 'QTECH' in job_5.stdout.replace('\n', ''):
                                            print('Тип и полное имя хоста', full_name)
                                            host.osver = 'qtechsw'
                                        elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                            print('Тип и полное имя хоста', full_name)
                                            host.osver = 'dlinksw'
                                        elif 'IOS' in job_5.stdout.replace('\n', ''):  ###### переделать это
                                            print('Тип и полное имя хоста', full_name)
                                            host.osver = 'nexus'
                                        elif 'Cisco' in job_5.stdout.replace('\n', ''):
                                            print('Тип и полное имя хоста', full_name)
                                            host.osver = 'nexus'
                                        elif 'UPS' in job_5.stdout.replace('\n', ''):
                                            # host.osver = 'UPS'
                                            get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} 1.3.6.1.2.1.33.1.1.5.0 "
                                            job_get_name_ups = connector.run(get_name_ups)
                                            hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                               '')
                                            get_type_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} 1.3.6.1.2.1.33.1.1.2.0 "
                                            type_osver_ups = get_type_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                              '')
                                            print('type_osver_ups nmc', type_osver_ups, hostname111, )
                                            host.osver = type_osver_ups

                                        elif 'APC' in job_5.stdout.replace('\n',
                                                                           '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                            '\n', ''):

                                            get_name_ups = f"snmpget -L n -v1 {ip_addr} -c {community_string} .1.3.6.1.2.1.33.1.1.5.0"
                                            job_get_name_ups = connector.run(get_name_ups)
                                            hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                               '')  # полное имя коммутатора и его тип
                                            type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                                       '')
                                            host.osver = type_osver_ups

                                        elif 'APC' in job_5.stdout.replace('\n',
                                                                           '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                            '\n', ''):
                                            print('apc2')

                                            host.osver = 'apc_hw05_aos_513'

                                    except:

                                        print('Пропуск:', ip_addr)
                                        continue
                        print('host.osver get snmp:', host.osver)

                        host.save()

                    except:
                        return False
                        # host.save()
                    if not host_name:
                        host_name = host.hostname
                        print("host.hostname", host.hostname)

                    selected_checks = [key for key in form.cleaned_data if
                                       form.cleaned_data[key] and isinstance(form.cleaned_data[key], bool)]

                    # генерация файла на основе данных из формы
                    if not host_name:
                        host_name = ip_addr
                    elif host_name == 'None':
                        host_name = ip_addr
                    print("hostname create0ryruy6r", host_name)
                    file_name = host_name if host_name else ip_addr
                    file_path = fr"/usr/local/nagios/etc/objects/hosts/{device_type}/{file_name}.cfg"
                    print(file_path)

                    with paramiko.SSHClient() as ssh_client:
                        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        ssh_client.connect(hostname=host, username=usernamy, password=passy)

                        # Запись данных в файл на удаленном сервере
                        with ssh_client.open_sftp() as sftp:
                            with sftp.file(file_path, 'w') as config_file:
                                # Запись основных данных в файл
                                config_file.write('define host {\n')
                                config_file.write(f'\tuse\t\t{gen_group}\n')
                                config_file.write(f'\thost_name\t{host_name}\n')
                                config_file.write(f'\taddress\t\t{ip_addr}\n')
                                config_file.write(f'\thost_groups\t{device_type}\n')
                                config_file.write(f'\thost_groups\t{device_type}\n')
                                # if host.parents:
                                #     print('parents in cfg', host.parents.hostname, host.parents.ipaddr)
                                #     if host.parents.hostname:
                                #         config_file.write(f'\tparents\t{parents.hostname}\n')
                                #     else:
                                #         config_file.write(f'\tparents\t{parents.ipaddr}\n')
                                # if parents != 'None' and parents is not None:
                                #     config_file.write(f'\tparents\t{parents.ipaddr}\n')
                                if device_type == "servers":
                                    config_file.write(f'\ticon_image\tserver-1.png\n')
                                    # /usr/local/nagios/share/images/logos/server-1.png
                                config_file.write('}\n')
                                config_file.write('\n')
                                config_file.write('\n')
                                config_file.write('define service {\n')
                                config_file.write('\tuse\t\tping-service\n')
                                config_file.write(f'\thost_name\t{host_name}\n')
                                config_file.write('}\n')

                                config_file.write('\n')
                                config_file.write('\n')

                                if host.SNMP or host_name is not None:
                                    # Добавление сервисов согласно выбранным пунктам
                                    for sdescription in selected_checks:
                                        # host = Host.objects.get(ipaddr=ip_addr)
                                        type_sw = host.osver
                                        if community_string == lenovo_snmp_community and type_sw == "lenovosw":
                                            service = 'service-private'
                                        else:
                                            service = 'service'
                                        serv_dict = {
                                            # 'cpu_1_min': {'use_command': f'check_snmp_cpu_load_1_min_{type_sw}-service', 'description': 'CPU Load 1 Min' if cpu_1_min else ''},
                                            'cpu_5_min': {'use_command': f'check_snmp_cpu_{type_sw}-service-private',
                                                          'description': 'CPU 5 min load' if cpu_5_min else ''},
                                            'uptime': {'use_command': 'uptime-service',
                                                       'description': 'Uptime' if uptime else ''},
                                            'mem_free': {'use_command': f'check_snmp_memory_free_{type_sw}-{service}',
                                                         'description': 'Memory Free' if mem_free else ''},
                                            'mem_used': {'use_command': f'check_snmp_memory_used_{type_sw}-{service}',
                                                         'description': 'Memory Used' if mem_used else ''},
                                            'mem_util': {'use_command': f'check_snmp_memory_utl_{type_sw}-{service}',
                                                         'description': 'Memory Utilization' if mem_util else ''},

                                            'bat_temp': {'use_command': 'upstemp',
                                                         'description': 'Battery Temperature' if bat_temp else ''},
                                            'bat_time_work': {'use_command': f'ups_time_work_on_battery',
                                                              'description': ' Battery Time Work' if bat_time_work else ''},
                                            'bat_vol': {'use_command': f'ups_volt',
                                                        'description': 'Battery Voltage' if bat_vol else ''},
                                            'run_reman': {'use_command': f'ups_battery_run_time_remaining',
                                                          'description': 'Runtime Remaining' if run_reman else ''},
                                            'stat_charge': {'use_command': f'ups_bat_stat',
                                                            'description': 'State of Charge' if stat_charge else ''},

                                        }
                                        use_command = serv_dict[sdescription][
                                            'use_command']  # Получение нужного значения из словаря
                                        description = serv_dict[sdescription][
                                            'description']  # Получение нужного значения из словаря

                                        config_file.write('define service {\n')
                                        config_file.write(f'\tuse\t\t\t{use_command}\n')
                                        config_file.write(f'\tservice_description\t{description}\n')
                                        config_file.write(f'\thost_name\t\t{host_name}\n')
                                        config_file.write('}\n')
                                        config_file.write('\n')
                                        config_file.write('\n')
                                else:
                                    error = "Не настроен SNMP для отслеживания служб"
                                    print('error', error)
                                # Проверка наличия созданного файла
                            if sftp.stat(file_path):
                                host.nagios_flag = True
                                print(f"Файл успешно создан на удаленном сервере: {file_path}")
                                logging.info(f"Файл успешно создан на удаленном сервере: {file_path}")

                            else:
                                messages.error(request, ' Файл не был создан')
                                logging.error(f"Ошибка: Файл не был создан на удаленном сервере: {file_path}")
                                print(f"Ошибка: Файл не был создан на удаленном сервере: {file_path}")

                        ssh_client.close()
                    host.save()
                    ssh = paramiko.SSHClient()
                    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh_client.connect(hostname=host, username=usernamy, password=passy)
                    try:
                        reload_cm = 'sudo systemctl restart nagios'
                        reload = connector.run(reload_cm)
                        print("reload ", reload)
                        if "" in reload:
                            print('в нагиос все ок')
                            messages.success(request, 'Хост успешно создан')
                        else:
                            print('в нагиос все /////')
                            messages.error(request, ' Ошибка1 в Nagios, хост  удален')
                            remove_command = f'mv  "/usr/local/nagios/etc/objects/hosts/{device_type}/{host_name}.cfg" "/usr/local/nagios/etc/objects/bag/" '
                            r_2 = connector.run(remove_command)
                            output = r_2.stdout
                            print('output', output)
                            host.nagios_flag = False
                            messages.error(request, ' Ошибка в Nagios, хост  удален')
                            print(' Ошибка в Nagios, хост  удален')

                    except TypeError as e:
                        if str(e) == "'NoneType' object is not iterable" or str(e) == "'int' object is not iterable":
                            print("object is not iterable")
                        else:
                            print("object is not iterable2")

                    except Exception as e:
                        print(f'except {e}')
                        message = f"Ошибка: Хост  {file_path} except {e}"
                        # send_error_email(message, "except")
                        # # remove_command = f'remove {file_path}'
                        ssh_client.exec_command(
                            f'mv  "/usr/local/nagios/etc/objects/hosts/{device_type}/{host_name}.cfg" "/usr/local/nagios/etc/objects/bag/" ')
                        host.nagios_flag = False
                        # "/usr/local/nagios/etc/objects/bag/"
                        # print('remove_command:', remove_command)
                        ssh.close()
                        # print('проверка не удалась ')
                        # host.delete()
                        logging.error(f"Ошибка: Хост удален везде: {file_path}")
                        messages.error(request, ' Ошибка в Nagios, хост в Nagios удален, обратитесь к администратору')
                    return redirect('/')

            else:
                error = 'Форма была неверной'
        form = CheckForm()
        data = {
            'form': form,
            'error': error,
            'hosts': hosts,
            'available_hosts': available_hosts,

        }
        print(error, data)


    except MultipleObjectsReturned:
        error = f"Хост с {ip_addr} уже существует в базе данных, проверьте страницу scan"

    return render(request, 'front/create_host.html', data)


def delete_in_stroke_nagios(device_type, hostname):
    '''
    Удаление хоста и его записей в качестве родителя в других хостах
    '''
    with paramiko.SSHClient() as ssh_client:
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh_client.connect(hostname=host, username=usernamy, password=passy)
        try:
            print('big step rule for del')
            # print(    f'grep -rl "parents\t{hostname}" /usr/local/nagios/etc/objects/hosts/ | xargs sed -i "/parents\t{hostname}/d"')
            # удаляем упоминания о нем
            stdin, stdout, stderr = ssh_client.exec_command(
                f'grep -rl "parents\t{hostname}" /usr/local/nagios/etc/objects/hosts/ | xargs sed -i "/parents\t{hostname}/d"'
            )
            exit_code = stdout.channel.recv_exit_status()
            # print('exit_code', exit_code)
            if exit_code == 0:
                print("Команда выполнена успешно.")
                # удаляем файл хоста
                ssh_client.exec_command(
                    f'rm -f /usr/local/nagios/etc/objects/hosts/{device_type}/{hostname}.cfg')
                return True, "Хост удален"


            elif exit_code == 123:
                print("sed: отсутствуют входные файлы")
                # удаляем файл хоста
                ssh_client.exec_command(
                    f'rm -f /usr/local/nagios/etc/objects/hosts/{device_type}/{hostname}.cfg')
                return True, "Хост удален"

            else:
                print('little step rule for del')
                ssh_client.exec_command(
                    f'rm -f /usr/local/nagios/etc/objects/hosts/{device_type}/{hostname}.cfg')

                stdin, stdout, stderr = ssh_client.exec_command(
                    f'grep -rl "parents {hostname}" /usr/local/nagios/etc/objects/hosts/ | xargs sed -i "/parents {hostname}/d"'
                )
                exit_code2 = stdout.channel.recv_exit_status()
                print('exit_code2', exit_code2)
                if exit_code2 == 0:
                    print("Команда выполнена успешно.")
                    ssh_client.exec_command(
                        f'rm -f /usr/local/nagios/etc/objects/hosts/{device_type}/{hostname}.cfg')
                    return True, "Хост удален"
                elif exit_code == 123:
                    print("sed: отсутствуют входные файлы")
                    # удаляем файл хоста
                    ssh_client.exec_command(
                        f'rm -f /usr/local/nagios/etc/objects/hosts/{device_type}/{hostname}.cfg')
                    return True, "Хост удален"
                else:
                    print(' error ')
                    return False, "Ошибка при удалении"
        except Exception as e:
            return False, str(e)
        except:
            print('эххххх')
            return False

        ssh_client.close()
        # return messages


@login_required
@require_POST
def delete_host(request, pk):
    """ Вызов ф-ции удаления хоста"""
    error = ''
    status = ''
    message = ''
    host = get_object_or_404(Host, pk=pk)

    if host.hostname is not None and host.hostname != 'None':
        print(f'dellele')
        status, message = delete_in_stroke_nagios(host.device_type, host.hostname)
        if status is True:
            host.delete()
            logging.info(f"Ошибка: Хост удален везде: {message}")
            messages.success(request, message)
        else:
            logging.error(message)
            messages.error(request, message)
    else:
        status, message = delete_in_stroke_nagios(host.device_type, host.ipaddr)
        if status is True:
            logging.info(f"Ошибка: Хост удален везде: {host.ipaddr}")
            host.delete()
            messages.success(request, message)
        else:
            logging.error(message)
            messages.error(request, message)
    # return redirect('/')
    return redirect('scan')


@login_required
@require_GET
def check_snmp(request):
    global hostname111
    print('start check_snmp ')
    error_message = None
    osver = None
    if request.method == 'GET':
        try:
            ip = validated_ip(request.GET.get('ipaddr'))
            com = validated_community(request.GET.get('com_str'))
        except ValueError as exc:
            return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
        print(f'com: {com} ip {ip}')
        if Host.objects.filter(ipaddr=ip).exists():
            # host = Host.objects.get(ipaddr=ip)
            # return redirect('host-update', host.id)
            print(f'{ip} уже существуетc')
            message = f'уже существует'
        else:
            # print('Checking ip', ip)
            ping_result = subprocess.run(['ping', '-c', '1', ip], stdout=subprocess.PIPE).returncode

            # Проверяем результат команды
            try:
                # print('start')
                if ping_result == 0:
                    # print('*ddd**')
                    print(f'{ip} в сети')
                    try:

                        job_2_command = f"snmpget -v1 {ip} -c {com} sysName.0"
                        job_2 = connector.run(job_2_command)

                        output = job_2.stdout
                        time.sleep(5)
                        if 'NMC' in output:
                            print('nmc')

                            get_name_ups = f"snmpget -L n -v1 {ip} -c {com}  iso.3.6.1.2.1.33.1.1.5.0 "
                            job_get_name_ups = connector.run(get_name_ups)
                            hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                               '')  # полное имя коммутатора и его тип
                            print('job_get_name_ups:', hostname111)

                            type_osver_ups = f"snmpget -L n -v1 {ip} -c {com}  iso.3.6.1.2.1.33.1.1.2.0 "
                            job_type_osver_ups = connector.run(get_name_ups)
                            osver = job_type_osver_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')  # полное имя коммутатора и его тип
                            print('job_type_osver_ups:', osver)

                        elif "STRING: " in output:
                            print('string')
                            hostname111 = output.split('STRING: ')[1].replace('\n', '')
                            get_snmp_type = f"snmpget -L n -v1 {ip} -c {com} .1.3.6.1.2.1.1.1.0 "
                            time.sleep(5)  # получаем стринг и имя хоста jhgbbnmnbhjbmnb
                            # time.sleep(5)
                            job_5 = connector.run(get_snmp_type)
                            full_name = job_5.stdout.split('STRING: ')[1].replace('\n',
                                                                                  '')  # полное имя коммутатора и его тип
                            print('job_5:', full_name)

                            try:
                                print("начинаю  тry")

                                if 'Lenovo' in job_5.stdout.replace('\n', ''):
                                    print('Тип и полное имя хоста', full_name)
                                    osver = 'lenovosw'
                                elif 'QTECH' in job_5.stdout.replace('\n', ''):
                                    print('Тип и полное имя хоста', full_name)
                                    osver = 'qtechsw'
                                # elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                    print('Тип и полное имя хоста', full_name)
                                    osver = 'dlinksw'
                                elif 'IOS' in job_5.stdout.replace('\n', ''):  ###### переделать это
                                    print('Тип и полное имя хоста', full_name)
                                    osver = 'nexus'
                                elif 'Cisco' in job_5.stdout.replace('\n', ''):
                                    print('Тип и полное имя хоста', full_name)
                                    osver = 'nexus'

                                elif 'APC' in job_5.stdout.replace('\n',
                                                                   '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                        '\n', ''):
                                    print('apc')
                                    get_name_ups = f"snmpget -L n -v1 {ip} -c {com}  .1.3.6.1.2.1.33.1.1.5.0"
                                    job_get_name_ups = connector.run(get_name_ups)
                                    hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                       '')  # полное имя коммутатора и его тип
                                    print('job_get_name_ups apc36CA32:', hostname111)
                                    type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                               '')
                                    print('type_osver_ups', type_osver_ups)
                                    osver = type_osver_ups

                                elif 'APC' in job_5.stdout.replace('\n',
                                                                   '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                        '\n', ''):
                                    print('apc2')

                                    hostname111 = output.split('STRING: ')[1].replace('\n', '')

                                    osver = 'apc_hw05_aos_513'

                                else:
                                    print('Пропуск:', ip)


                            except:
                                print('Пропуск:', ip)
                        print('osver:', osver)
                        if osver == 'dlinksw':
                            message = (f'SNMP настроенd.мя хоста {hostname111} \n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )

                        elif osver == 'lenovosw':
                            message = (f'SNMP настроенl.Имя хоста {hostname111} \n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )

                        elif osver == 'qtechsw':
                            message = (f'SNMP настроенq.Имя хоста {hostname111} \n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )

                        elif osver == 'nexus':
                            message = (f'SNMP настроенn.Имя хоста {hostname111} \n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )

                        elif osver == 'APC':
                            message = (f'SNMP настроенAPC.Имя хоста {hostname111} \n'

                                       )

                        elif osver == 'apc36CA32':
                            message = (f'SNMP настроенapc36CA32.Имя хоста {hostname111} \n'

                                       )
                        elif osver == 'apc_hw05_aos_513':
                            message = (f'SNMP apc_hw05_aos_513.Имя хоста "{hostname111}" \n'

                                       )

                        elif osver == 'UPS':
                            message = (f'SNMP настроенAPC.Имя хоста "{hostname111}"\n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )
                        else:
                            message = (f'SNMP настроен.Имя хоста {hostname111} \n'
                                       f'Можно присвоить новое имя заполнив форму  "Имя хоста" \n'
                                       )
                    except Exception as e:
                        message = 'SNMP не настроен'
                        print(f"Ошибка при выполнении команды SNMP: {e}")



                else:
                    message = 'Хост не в сети. Выбор служб недоступен'
                    print(f'{ip} не в сети')

            except subprocess.TimeoutExpired as e:
                # Обработка исключения тайм-аута при выполнении команды
                print('Timeoutпропропро')
                # error_message =F'SNMP не настроен на {ip}. Службы созданны не будут!'
                error_message = F'SNMP не настроен'
                return HttpResponse(error_message, status=500)


            except subprocess.CalledProcessError:
                print('CalledProcessError')
                error_message = F'SNMP не настроен'
                print('message', message)
                return HttpResponse(error_message, status=500)

            except Exception as e:
                # Общая обработка других исключений
                print('Command execution timed out', e)
                error_message = F'SNMP не настроен'
                return HttpResponse(error_message, status=500)

            if ping_result == 0:
                print(f'{ip} в сети')
            else:
                print(f'{ip} не в сети')
                error_message = f'{ip} не в сети'

        # print(f"hostnn23r2 {hostname111}")
        print('message views', message)
        return HttpResponse(message)

    return HttpResponse('Ошибка при проверке SNMP')


def delete_passed_time():
    print("**")
    threshold_time = timezone.now() - timedelta(days=1)
    old_host = host.objects.filter(time_create__date=threshold_time)
    deleted_count, _ = old_host.delete()
    # return deleted_count


def process_host_data1(item, community_string):
    host = {}
    print('Processing')
    ip = item.get("ip")
    community_strings = snmp_communities
    host = Host(ipaddr=ip)
    host.online = True
    if check_remote_file_with_ip(ip):
        host.nagios_flag = True
        # host.save()
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
                    break  # Если нашли правильную строку сообщества, выходим из цикла
            except Exception as e:
                print(f"Ошибка при выполнении команды SNMP: {e}")

        if host.SNMP:
            print(f"SNMP успешно настроен. Hostname: {host.hostname}, Community String: {host.com_str}")
        else:
            print("Не удалось настроить SNMP с данными строками сообщества.")

        if host.SNMP:
            for row_2 in job_2.stdout.split('\n'):
                #
                if "SNMPv2-MIB" in row_2:
                    print(f"SNMP на {ip} настроен")
                    get_snmp_type = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.1.1.0 "
                    time.sleep(5)  # получаем стринг и имя хоста
                    # time.sleep(5)
                    job_5 = connector.run(get_snmp_type)
                    full_name = job_5.stdout.split('STRING: ')[1].replace('\n',
                                                                          '')  # полное имя коммутатора и его тип
                    print('job_5:', full_name)
                    if 'NMC' in row_2:
                        print('nmc')

                        get_name_ups = f"snmpget -L n -v1 {ip} -c {community_string}  iso.3.6.1.2.1.33.1.1.5.0 "
                        job_get_name_ups = connector.run(get_name_ups)
                        hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')  # полное имя коммутатора и его тип
                        print('job_get_name_ups:', hostname111)

                        type_osver_ups = f"snmpget -L n -v1 {ip} -c {community_string}  iso.3.6.1.2.1.33.1.1.2.0 "
                        job_type_osver_ups = connector.run(get_name_ups)
                        osver = job_type_osver_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                       '')  # полное имя коммутатора и его тип
                        print('job_type_osver_ups:', osver)

                    elif "STRING: " in row_2:
                        print('string')
                        hostname111 = row_2.split('STRING: ')[1].replace('\n', '')
                        get_snmp_type = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.1.1.0 "
                        time.sleep(5)  # получаем стринг и имя хоста jhgbbnmnbhjbmnb
                        # time.sleep(5)
                        job_5 = connector.run(get_snmp_type)
                        full_name = job_5.stdout.split('STRING: ')[1].replace('\n',
                                                                              '')  # полное имя коммутатора и его тип
                        print('job_5:', full_name)
                        try:
                            if 'Lenovo' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'lenovosw'
                            elif 'QTECH' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'qtechsw'
                            elif 'DGS-1210-10' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'dlinksw'
                            elif 'IOS' in job_5.stdout.replace('\n', ''):  ###### переделать это
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'nexus'
                            elif 'Cisco' in job_5.stdout.replace('\n', ''):
                                print('Тип и полное имя хоста', full_name)
                                host.osver = 'nexus'
                            elif 'UPS' in job_5.stdout.replace('\n', ''):
                                # host.osver = 'UPS'
                                get_name_ups = f"snmpget -L n -v1 {ip} -c {community_string} 1.3.6.1.2.1.33.1.1.5.0 "
                                job_get_name_ups = connector.run(get_name_ups)
                                hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                   '')
                                get_type_ups = f"snmpget -L n -v1 {ip} -c {community_string} 1.3.6.1.2.1.33.1.1.2.0 "
                                type_osver_ups = get_type_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                  '')
                                print('type_osver_ups nmc', type_osver_ups, hostname111, )
                                host.osver = type_osver_ups

                            elif 'APC' in job_5.stdout.replace('\n',
                                                               '') and 'apc_hw05_aos_682' in job_5.stdout.replace(
                                '\n', ''):

                                get_name_ups = f"snmpget -L n -v1 {ip} -c {community_string} .1.3.6.1.2.1.33.1.1.5.0"
                                job_get_name_ups = connector.run(get_name_ups)
                                hostname111 = job_get_name_ups.stdout.split('STRING: ')[1].replace('\n',
                                                                                                   '')  # полное имя коммутатора и его тип
                                type_osver_ups = job_2.stdout.split('STRING: ')[1].replace('\n',
                                                                                           '')
                                host.osver = type_osver_ups

                            elif 'APC' in job_5.stdout.replace('\n',
                                                               '') and 'apc_hw05_aos_513' in job_5.stdout.replace(
                                '\n', ''):
                                print('apc2')

                                host.osver = 'apc_hw05_aos_513'
                            file_path = './type.txt'
                            file_path1 = './type1.txt'

                            host[host.ipaddr] = {'ipaddr': host.ipaddr, 'osver': [host.osver]}
                            host = json.dumps(host)
                            # file_path = './data.json'  # укажите путь к файлу, в который вы хотите сохранить данные
                            with open(file_path, 'w', encoding='utf-8') as file:
                                file.write(host)
                            with (file_path1, 'w') as config_file:
                                # Запись основных данных в файл
                                config_file.write(f'{host.osver}\n')


                        except:
                            print('Пропуск:', ip)
                        # continue
                    # host.save()
    except Exception as e:
        print(f"Error getting SNMP data for {ip}: {str(e)}")
        return None


@login_required
@require_http_methods(['GET', 'POST'])
def discover_network_view(request):
    """View для запуска обнаружения сети"""
    if request.method == 'POST':
        try:
            start_ip = validated_ip(request.POST.get('start_ip'))
            community = validated_community(request.POST.get('community', 'public'))
            max_hops = int(request.POST.get('max_hops', 3))
            max_devices = int(request.POST.get('max_devices', 50))
            if not 1 <= max_hops <= 20:
                raise ValueError('max_hops must be between 1 and 20')
            if not 1 <= max_devices <= 1024:
                raise ValueError('max_devices must be between 1 and 1024')
        except (TypeError, ValueError) as exc:
            return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)

        # Запуск обнаружения в фоновом потоке
        def run_discovery():
            discovery = NetworkDiscovery(community=community)
            hosts, connections = discovery.discover_network(
                start_ip,
                max_hops=max_hops,
                max_devices=max_devices
            )
            discovery.save_to_database()

        thread = threading.Thread(target=run_discovery)
        thread.daemon = True
        thread.start()

        messages.success(request, f'Обнаружение сети запущено с IP {start_ip}')
        return redirect('service')

    return render(request, 'front/discover_form.html')


@login_required
@require_GET
def get_discovery_status(request):
    """API endpoint для получения статуса обнаружения"""
    # Здесь можно добавить логику для отслеживания прогресса
    hosts_count = Host.objects.filter(SNMP=True).count()
    return JsonResponse({
        'status': 'running',
        'hosts_discovered': hosts_count
    })


def service1(request):
    """View для отображения карты сети"""
    # Получение всех хостов с оптимизацией запросов
    hosts = Host.objects.filter(nagios_flag=True).prefetch_related('services', 'parent_routes', 'child_routes')

    # Построение дерева
    tree = build_network_tree(hosts)

    # Получение всех маршрутов для отрисовки связей
    routes = []
    for route in Route.objects.select_related('parent', 'child'):
        routes.append({
            'parent': route.parent.ipaddr,
            'child': route.child.ipaddr,
            'waypoints': route.waypoints
        })

    tree_json = json.dumps({
        'nodes': tree,
        'routes': routes
    })

    return render(request, 'front/map3.html', {'tree': tree_json})


def build_network_tree(hosts):
    """Построение дерева сети с учетом Route модели"""
    tree = {}

    # Создаем узел для 'sysmon'
    tree['sysmon'] = {
        'ipaddr': 'sysmon',
        'hostname': 'System Monitor',
        'status': True,
        'status_serv': 'ok',
        'device_type': 'servers',
        'section': 'Core',
        'children': [],
        'x': 400,  # Центральная позиция
        'y': 50
    }

    # Создаем узлы для каждого хоста
    for host in hosts:
        # Определяем статус сервисов
        status_serv = 'ok'
        if host.services.exists():
            critical_services = host.services.filter(status='CRITICAL')
            warning_services = host.services.filter(status='WARNING')

            if critical_services.exists():
                status_serv = 'critical'
            elif warning_services.exists():
                status_serv = 'warning'

        tree[host.ipaddr] = {
            'ipaddr': host.ipaddr,
            'hostname': host.hostname or host.ipaddr,
            'status': host.online,
            'status_serv': status_serv,
            'device_type': host.device_type or 'servers',
            'section': host.place or 'Unknown',
            'latitude': host.latitude,
            'longitude': host.longitude,
            'children': [],
            'vendor': host.vendor,
            'product': host.product
        }

    # Настраиваем связи на основе Route модели
    for host in hosts:
        # Получаем все дочерние устройства через Route
        child_routes = host.parent_routes.all()
        for route in child_routes:
            if route.child.ipaddr in tree:
                tree[host.ipaddr]['children'].append(route.child.ipaddr)

        # Если у устройства нет родителей и оно не является корневым
        if not host.child_routes.exists() and not host.parent_routes.exists():
            # Подключаем к sysmon
            tree['sysmon']['children'].append(host.ipaddr)

    # Автоматическое позиционирование узлов если координаты не заданы
    positioned_nodes = auto_layout(tree)

    # Преобразуем в список
    result = list(positioned_nodes.values())

    return result


def auto_layout(tree):
    """Автоматическое расположение узлов на карте"""
    import math

    # Начальные параметры
    center_x = 400
    center_y = 300
    level_height = 100

    def position_node(node_id, x, y, angle_start, angle_range, level=0):
        if node_id not in tree:
            return

        node = tree[node_id]

        # Если координаты не заданы, устанавливаем автоматически
        if node['latitude'] == 0 and node['longitude'] == 0:
            node['x'] = x
            node['y'] = y
        else:
            # Используем заданные координаты
            node['x'] = node['longitude'] * 10  # Масштабирование
            node['y'] = node['latitude'] * 10

        children = node['children']
        if children:
            # Радиус для размещения дочерних узлов
            radius = 150 + level * 50

            # Угол между дочерними узлами
            if len(children) > 1:
                angle_step = angle_range / (len(children) - 1)
            else:
                angle_step = 0

            for i, child_id in enumerate(children):
                angle = angle_start + i * angle_step
                child_x = x + radius * math.cos(math.radians(angle))
                child_y = y + radius * math.sin(math.radians(angle))

                # Рекурсивно позиционируем дочерние узлы
                child_angle_range = min(60, angle_range / max(1, len(children)))
                child_angle_start = angle - child_angle_range / 2

                position_node(child_id, child_x, child_y,
                              child_angle_start, child_angle_range, level + 1)

    # Начинаем с корневого узла
    position_node('sysmon', center_x, center_y, -90, 360, 0)

    return tree

from django.http import JsonResponse
from .models import Host # Замените на вашу модель хоста

@login_required
@require_GET
def get_host_id_by_ip(request):
    try:
        ip = validated_ip(request.GET.get('ip'))
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    if ip:
        try:
            # Ищем хост по IP. Если IP неуникальный, используйте .filter().first()
            host = Host.objects.get(ipaddr=ip)
            return JsonResponse({'id': host.id})
        except Host.DoesNotExist:
            return JsonResponse({'error': 'Host not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'No IP provided'}, status=400)


# views.py
import subprocess
import platform
import shutil
import json
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST


@login_required
@require_POST
@csrf_protect
def open_terminal(request):
    """
    API для открытия терминала (PuTTY на Windows, SSH на Linux)
    """
    try:
        data = json.loads(request.body)
        ip = validated_ip(data.get('ip'))
        protocol = data.get('protocol', 'ssh')  # ssh, telnet
        username = data.get('username', 'root')
        port = int(data.get('port', 22 if protocol == 'ssh' else 23))
        if protocol not in {'ssh', 'telnet'}:
            raise ValueError('Unsupported protocol')
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', username):
            raise ValueError('Invalid username')
        if not 1 <= port <= 65535:
            raise ValueError('Invalid port')

        system = platform.system()

        if system == 'Windows':
            result = open_windows_terminal(ip, protocol, username, port)
        elif system == 'Linux':
            result = open_linux_terminal(ip, protocol, username, port)
        elif system == 'Darwin':  # macOS
            result = open_macos_terminal(ip, protocol, username, port)
        else:
            return JsonResponse({
                'success': False,
                'message': f'Неподдерживаемая ОС: {system}'
            })

        return JsonResponse(result)

    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return JsonResponse({
            'success': False,
            'message': str(exc) or 'Неверный формат данных'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Ошибка: {str(e)}'
        }, status=500)


def open_windows_terminal(ip, protocol, username, port):
    """Открытие PuTTY на Windows"""

    # Список возможных путей к PuTTY
    putty_paths = [
        r'C:\Program Files\PuTTY\putty.exe',
        r'C:\Program Files (x86)\PuTTY\putty.exe',
        r'C:\PuTTY\putty.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\PuTTY\putty.exe'),
        'putty.exe',  # Если в PATH
    ]

    # Ищем PuTTY
    putty_path = None
    for path in putty_paths:
        if os.path.exists(path):
            putty_path = path
            break

    # Проверяем через shutil.which (если в PATH)
    if not putty_path:
        putty_path = shutil.which('putty')

    if not putty_path:
        # Пробуем запустить через plink (консольный SSH клиент из PuTTY)
        plink_path = shutil.which('plink')
        if plink_path:
            return open_with_plink(ip, protocol, username, port, plink_path)

        return {
            'success': False,
            'message': 'PuTTY не найден. Установите PuTTY и добавьте в PATH.',
            'fallback': 'copy_command'
        }

    try:
        if protocol == 'ssh':
            # PuTTY SSH подключение
            cmd = [
                putty_path,
                '-ssh',
                f'{username}@{ip}',
                '-P', str(port)
            ]
        elif protocol == 'telnet':
            # PuTTY Telnet подключение
            cmd = [
                putty_path,
                '-telnet',
                ip,
                '-P', str(port)
            ]
        else:
            cmd = [putty_path, ip]

        # Запускаем PuTTY как отдельный процесс
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            start_new_session=True
        )

        return {
            'success': True,
            'message': f'PuTTY открыт для {ip}'
        }

    except FileNotFoundError:
        return {
            'success': False,
            'message': 'Не удалось запустить PuTTY'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Ошибка запуска PuTTY: {str(e)}'
        }


def open_with_plink(ip, protocol, username, port, plink_path):
    """Открытие через plink в новом окне cmd"""
    try:
        if protocol == 'ssh':
            cmd = [plink_path, '-ssh', f'{username}@{ip}', '-P', str(port)]
        else:
            cmd = [plink_path, '-telnet', ip, '-P', str(port)]

        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS,
            start_new_session=True,
        )

        return {
            'success': True,
            'message': f'Plink открыт для {ip}'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Ошибка запуска plink: {str(e)}'
        }


def open_linux_terminal(ip, protocol, username, port):
    """Открытие терминала на Linux"""

    # Список терминалов в порядке приоритета
    terminals = [
        ('gnome-terminal', ['gnome-terminal', '--']),
        ('konsole', ['konsole', '-e']),
        ('xfce4-terminal', ['xfce4-terminal', '-e']),
        ('xterm', ['xterm', '-e']),
        ('mate-terminal', ['mate-terminal', '-e']),
        ('terminator', ['terminator', '-e']),
        ('tilix', ['tilix', '-e']),
        ('alacritty', ['alacritty', '-e']),
        ('kitty', ['kitty']),
    ]

    # Ищем доступный терминал
    terminal_cmd = None
    terminal_name = None

    for name, cmd in terminals:
        if shutil.which(name):
            terminal_cmd = cmd
            terminal_name = name
            break

    if not terminal_cmd:
        return {
            'success': False,
            'message': 'Терминал не найден. Установите gnome-terminal, konsole или xterm.',
            'fallback': 'copy_command'
        }

    try:
        if protocol == 'ssh':
            ssh_cmd = ['ssh', f'{username}@{ip}', '-p', str(port)]
        elif protocol == 'telnet':
            ssh_cmd = ['telnet', ip, str(port)]
        else:
            ssh_cmd = ['ssh', f'{username}@{ip}']

        # Специальная обработка для разных терминалов
        if terminal_name == 'gnome-terminal':
            full_cmd = terminal_cmd + ssh_cmd
        elif terminal_name in ['konsole', 'xfce4-terminal', 'mate-terminal']:
            full_cmd = terminal_cmd + [' '.join(ssh_cmd)]
        elif terminal_name == 'xterm':
            full_cmd = terminal_cmd + ssh_cmd
        elif terminal_name == 'kitty':
            full_cmd = terminal_cmd + ssh_cmd
        else:
            full_cmd = terminal_cmd + [' '.join(ssh_cmd)]

        subprocess.Popen(
            full_cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return {
            'success': True,
            'message': f'{terminal_name} открыт для {ip}'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Ошибка запуска терминала: {str(e)}'
        }


def open_macos_terminal(ip, protocol, username, port):
    """Открытие Terminal.app на macOS"""
    try:
        if protocol == 'ssh':
            cmd = f'ssh {username}@{ip} -p {port}'
        elif protocol == 'telnet':
            cmd = f'telnet {ip} {port}'
        else:
            cmd = f'ssh {username}@{ip}'

        # AppleScript для открытия Terminal.app
        apple_script = f'''
        tell application "Terminal"
            activate
            do script "{cmd}"
        end tell
        '''

        subprocess.Popen(
            ['osascript', '-e', apple_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return {
            'success': True,
            'message': f'Terminal.app открыт для {ip}'
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'Ошибка запуска Terminal: {str(e)}'
        }
