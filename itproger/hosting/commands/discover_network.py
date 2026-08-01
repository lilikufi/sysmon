# management/commands/discover_network.py

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
import sys
import os

# Добавляем путь к родительской директории для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Импортируем вашу модель и класс NetworkDiscovery
from hosting.models import Host, Route  # Замените myapp на имя вашего приложения
from hosting.network_discovery import NetworkDiscovery  # Замените myapp на имя вашего приложения


class Command(BaseCommand):
    help = 'Обнаружение топологии сети через SNMP'

    def add_arguments(self, parser):
        # Обязательный аргумент - начальный IP
        parser.add_argument(
            'start_ip',
            type=str,
            help='IP адрес, с которого начать обнаружение'
        )

        # Опциональные аргументы
        parser.add_argument(
            '--community',
            type=str,
            default='public',
            help='SNMP community string (по умолчанию: public)'
        )

        parser.add_argument(
            '--max-hops',
            type=int,
            default=3,
            help='Максимальная глубина обнаружения (по умолчанию: 3)'
        )

        parser.add_argument(
            '--max-devices',
            type=int,
            default=50,
            help='Максимальное количество устройств (по умолчанию: 50)'
        )

        parser.add_argument(
            '--timeout',
            type=int,
            default=2,
            help='SNMP timeout в секундах (по умолчанию: 2)'
        )

        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Подробный вывод'
        )

    def handle(self, *args, **options):
        start_ip = options['start_ip']
        community = options['community']
        max_hops = options['max_hops']
        max_devices = options['max_devices']
        timeout = options['timeout']
        verbose = options['verbose']

        self.stdout.write(
            self.style.WARNING(f'Начинаю обнаружение сети с IP: {start_ip}')
        )
        self.stdout.write(f'Параметры:')
        self.stdout.write(f'  - SNMP Community: {community}')
        self.stdout.write(f'  - Максимум переходов: {max_hops}')
        self.stdout.write(f'  - Максимум устройств: {max_devices}')
        self.stdout.write(f'  - Timeout: {timeout} сек.')

        try:
            # Создаем экземпляр класса для обнаружения
            discovery = NetworkDiscovery(
                community=community,
                timeout=timeout
            )

            # Запускаем обнаружение
            self.stdout.write('Сканирование сети...')
            hosts, connections = discovery.discover_network(
                start_ip,
                max_hops=max_hops,
                max_devices=max_devices
            )

            # Выводим результаты
            self.stdout.write(
                self.style.SUCCESS(f'Обнаружено устройств: {len(hosts)}')
            )
            self.stdout.write(
                self.style.SUCCESS(f'Обнаружено связей: {len(connections)}')
            )

            if verbose:
                self.stdout.write('\nОбнаруженные устройства:')
                for ip, info in hosts.items():
                    self.stdout.write(f'  - {ip}: {info.get("hostname", "Unknown")} '
                                      f'({info.get("device_type", "Unknown")})')

            # Сохраняем в базу данных
            self.stdout.write('\nСохранение в базу данных...')
            saved_count = discovery.save_to_database()

            self.stdout.write(
                self.style.SUCCESS(f'✓ Успешно сохранено {saved_count} устройств')
            )

        except Exception as e:
            raise CommandError(f'Ошибка при обнаружении сети: {str(e)}')