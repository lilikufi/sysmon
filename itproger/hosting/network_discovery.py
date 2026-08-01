# network_discovery.py
import subprocess
import json
import ipaddress
from typing import Dict, List, Set, Tuple
from django.db import transaction
from hosting.models import Host, Route
import re
import concurrent.futures
import threading


class NetworkDiscovery:
    def __init__(self, community='public', timeout=2, retries=1):
        self.community = community
        self.timeout = timeout
        self.retries = retries
        self.discovered_hosts = {}
        self.connections = []
        self.lock = threading.Lock()

    def snmp_get(self, ip, oid):
        """Выполнить SNMP GET запрос"""
        try:
            cmd = f"snmpget -v 2c -c {self.community} -t {self.timeout} -r {self.retries} {ip} {oid}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            print(f"SNMP GET error for {ip}: {e}")
            return None

    def snmp_walk(self, ip, oid):
        """Выполнить SNMP WALK запрос"""
        try:
            cmd = f"snmpwalk -v 2c -c {self.community} -t {self.timeout} -r {self.retries} {ip} {oid}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip().split('\n')
            return []
        except Exception as e:
            print(f"SNMP WALK error for {ip}: {e}")
            return []

    def get_device_info(self, ip):
        """Получить базовую информацию об устройстве"""
        info = {
            'ipaddr': ip,
            'hostname': None,
            'device_type': 'servers',
            'vendor': None,
            'product': None,
            'online': False,
            'SNMP': False
        }

        # Проверка доступности через ping
        ping_result = subprocess.run(f"ping -c 1 -W 1 {ip}", shell=True, capture_output=True)
        info['online'] = ping_result.returncode == 0

        # Получение имени устройства
        sysname = self.snmp_get(ip, '1.3.6.1.2.1.1.5.0')
        if sysname:
            info['SNMP'] = True
            # Извлечение имени из ответа
            match = re.search(r'STRING:\s*"?([^"\n]+)"?', sysname)
            if match:
                info['hostname'] = match.group(1).strip()

        # Получение описания системы
        sysdescr = self.snmp_get(ip, '1.3.6.1.2.1.1.1.0')
        if sysdescr:
            sysdescr_lower = sysdescr.lower()
            # Определение типа устройства
            if 'cisco' in sysdescr_lower or 'ios' in sysdescr_lower:
                info['device_type'] = 'switches'
                info['vendor'] = 'Cisco'
            elif 'hp' in sysdescr_lower or 'procurve' in sysdescr_lower:
                info['device_type'] = 'switches'
                info['vendor'] = 'HP'
            elif 'mikrotik' in sysdescr_lower:
                info['device_type'] = 'switches'
                info['vendor'] = 'MikroTik'
            elif 'linux' in sysdescr_lower:
                info['device_type'] = 'servers'
                info['vendor'] = 'Linux'
            elif 'windows' in sysdescr_lower:
                info['device_type'] = 'servers'
                info['vendor'] = 'Microsoft'
            elif 'ups' in sysdescr_lower or 'apc' in sysdescr_lower:
                info['device_type'] = 'UPS'
                info['vendor'] = 'APC' if 'apc' in sysdescr_lower else 'UPS'
            elif 'printer' in sysdescr_lower:
                info['device_type'] = 'network-printers'

            # Извлечение модели
            match = re.search(r'(IOS|Software|Version)[^,]*,\s*([^,]+)', sysdescr)
            if match:
                info['product'] = match.group(2).strip()

        return info

    def get_neighbors_lldp(self, ip):
        """Получить соседей через LLDP"""
        neighbors = []

        # LLDP Remote Systems Data
        lldp_rem_table = self.snmp_walk(ip, '1.0.8802.1.1.2.1.4.1.1')

        for line in lldp_rem_table:
            # Попробуем извлечь IP адрес соседа
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if match:
                neighbors.append(match.group(1))

        return neighbors

    def get_neighbors_cdp(self, ip):
        """Получить соседей через CDP (Cisco Discovery Protocol)"""
        neighbors = []

        # CDP Neighbor Address Table
        cdp_table = self.snmp_walk(ip, '1.3.6.1.4.1.9.9.23.1.2.1.1.4')

        for line in cdp_table:
            # Извлечение IP адреса из hex-string
            if 'Hex-STRING:' in line:
                hex_data = line.split('Hex-STRING:')[1].strip()
                hex_bytes = hex_data.replace(' ', '').replace(':', '')
                if len(hex_bytes) >= 8:
                    try:
                        # Преобразование hex в IP
                        ip_bytes = bytes.fromhex(hex_bytes[-8:])
                        neighbor_ip = '.'.join(str(b) for b in ip_bytes)
                        if self.is_valid_ip(neighbor_ip):
                            neighbors.append(neighbor_ip)
                    except:
                        pass

        return neighbors

    def get_arp_table(self, ip):
        """Получить ARP таблицу устройства"""
        arp_entries = []

        # IP NetToMedia Table
        arp_table = self.snmp_walk(ip, '1.3.6.1.2.1.4.22.1.3')

        for line in arp_table:
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if match:
                arp_ip = match.group(1)
                if self.is_valid_ip(arp_ip) and not arp_ip.startswith('127.'):
                    arp_entries.append(arp_ip)

        return arp_entries

    def get_routing_table(self, ip):
        """Получить таблицу маршрутизации"""
        routes = []

        # ipRouteNextHop
        route_table = self.snmp_walk(ip, '1.3.6.1.2.1.4.21.1.7')

        for line in route_table:
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if match:
                next_hop = match.group(1)
                if self.is_valid_ip(next_hop) and next_hop != '0.0.0.0':
                    routes.append(next_hop)

        return routes

    def is_valid_ip(self, ip):
        """Проверить валидность IP адреса"""
        try:
            ipaddress.ip_address(ip)
            return True
        except:
            return False

    def discover_device(self, ip):
        """Обнаружить устройство и его соседей"""
        print(f"Discovering device: {ip}")

        # Получаем информацию об устройстве
        device_info = self.get_device_info(ip)

        if not device_info['SNMP']:
            print(f"Device {ip} doesn't support SNMP or is not accessible")
            return None

        with self.lock:
            self.discovered_hosts[ip] = device_info

        # Получаем соседей различными способами
        neighbors = set()

        # Через LLDP
        lldp_neighbors = self.get_neighbors_lldp(ip)
        neighbors.update(lldp_neighbors)

        # Через CDP (для Cisco)
        if device_info.get('vendor') == 'Cisco':
            cdp_neighbors = self.get_neighbors_cdp(ip)
            neighbors.update(cdp_neighbors)

        # Через ARP таблицу
        arp_neighbors = self.get_arp_table(ip)
        neighbors.update(arp_neighbors[:10])  # Ограничиваем количество

        # Через таблицу маршрутизации
        route_neighbors = self.get_routing_table(ip)
        neighbors.update(route_neighbors[:5])  # Ограничиваем количество

        # Удаляем сам IP устройства из списка соседей
        neighbors.discard(ip)

        # Сохраняем связи
        with self.lock:
            for neighbor in neighbors:
                if self.is_valid_ip(neighbor):
                    self.connections.append((ip, neighbor))

        print(f"Found {len(neighbors)} neighbors for {ip}")
        return neighbors

    def discover_network(self, start_ip, max_hops=3, max_devices=50):
        """Обнаружить сеть начиная с указанного IP"""
        to_discover = {start_ip}
        discovered = set()
        hop = 0

        while to_discover and hop < max_hops and len(discovered) < max_devices:
            print(f"\nHop {hop + 1}, discovering {len(to_discover)} devices...")

            current_batch = list(to_discover)
            to_discover = set()

            # Параллельное обнаружение устройств
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(self.discover_device, ip): ip
                           for ip in current_batch if ip not in discovered}

                for future in concurrent.futures.as_completed(futures):
                    ip = futures[future]
                    discovered.add(ip)

                    try:
                        neighbors = future.result()
                        if neighbors:
                            for neighbor in neighbors:
                                if neighbor not in discovered:
                                    to_discover.add(neighbor)
                    except Exception as e:
                        print(f"Error discovering {ip}: {e}")

            hop += 1

        print(f"\nDiscovery complete. Found {len(self.discovered_hosts)} devices")
        return self.discovered_hosts, self.connections

    def save_to_database(self):
        """Сохранить обнаруженные устройства в базу данных"""
        with transaction.atomic():
            for ip, info in self.discovered_hosts.items():
                host, created = Host.objects.update_or_create(
                    ipaddr=info['ipaddr'],
                    defaults={
                        'hostname': info.get('hostname', ''),
                        'vendor': info.get('vendor', ''),
                        'product': info.get('product', ''),
                        'device_type': info.get('device_type', 'servers'),
                        'online': info.get('online', False),
                        'SNMP': info.get('SNMP', False),
                        'com_str': self.community,
                        'nagios_flag': True,
                    }
                )
                if created:
                    print(f"Created new host: {ip}")
                else:
                    print(f"Updated host: {ip}")

            # Сохраняем связи
            for parent_ip, child_ip in self.connections:
                try:
                    parent = Host.objects.get(ipaddr=parent_ip)
                    child = Host.objects.get(ipaddr=child_ip)

                    # Создаем Route если не существует
                    Route.objects.get_or_create(
                        parent=parent,
                        child=child
                    )

                    # Также обновляем поле parents
                    if not child.parents:
                        child.parents = parent
                        child.save()

                except Host.DoesNotExist:
                    pass

        return len(self.discovered_hosts)