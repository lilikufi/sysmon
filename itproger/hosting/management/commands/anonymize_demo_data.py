import ipaddress
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from hosting.models import Host, NodePosition


PEOPLE = [
    ('Алексей', 'Воронов'),
    ('Михаил', 'Соколов'),
    ('Дмитрий', 'Лебедев'),
    ('Сергей', 'Морозов'),
    ('Андрей', 'Волков'),
    ('Павел', 'Орлов'),
    ('Илья', 'Зайцев'),
    ('Роман', 'Белов'),
    ('Никита', 'Тихонов'),
    ('Анна', 'Воронова'),
    ('Мария', 'Соколова'),
    ('Елена', 'Лебедева'),
    ('Ольга', 'Морозова'),
    ('Ирина', 'Волкова'),
    ('Дарья', 'Орлова'),
    ('София', 'Зайцева'),
    ('Алина', 'Белова'),
    ('Вера', 'Тихонова'),
]

ADJECTIVES = [
    'amber',
    'arctic',
    'azure',
    'bright',
    'calm',
    'coral',
    'crystal',
    'dawn',
    'delta',
    'emerald',
    'frost',
    'golden',
    'lunar',
    'misty',
    'north',
    'quiet',
    'silver',
    'solar',
    'swift',
    'violet',
]

NOUNS = [
    'atlas',
    'aurora',
    'cedar',
    'comet',
    'falcon',
    'harbor',
    'iris',
    'maple',
    'mercury',
    'nebula',
    'oasis',
    'onyx',
    'orion',
    'phoenix',
    'river',
    'summit',
    'titan',
    'vector',
    'willow',
    'zenith',
]

HOST_PREFIXES = {
    'servers': 'srv',
    'switches': 'sw',
    'routers': 'rtr',
    'computers': 'pc',
    'network-printers': 'prn',
    'UPS': 'ups',
}

DOCUMENTATION_NETWORKS = (
    '192.0.2.0/24',
    '198.51.100.0/24',
    '203.0.113.0/24',
)


class Command(BaseCommand):
    help = 'Replace local users, hosts and graph positions with safe demo data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed',
            type=int,
            help='Optional seed for reproducible demo data.',
        )

    def handle(self, *args, **options):
        seed = options['seed']
        rng = random.Random(seed) if seed is not None else random.SystemRandom()

        User = get_user_model()
        users = list(User.objects.order_by('-is_superuser', '-is_staff', 'pk'))
        hosts = list(Host.objects.order_by('pk'))
        positions = list(NodePosition.objects.order_by('pk'))

        if len(users) > len(PEOPLE):
            raise CommandError('Not enough generated identities for all users.')

        host_tokens = [(adjective, noun) for adjective in ADJECTIVES for noun in NOUNS]
        if len(hosts) > len(host_tokens):
            raise CommandError('Not enough generated names for all hosts.')

        ip_pool = [
            str(address)
            for network in DOCUMENTATION_NETWORKS
            for address in ipaddress.ip_network(network).hosts()
        ]
        host_ips = {host.ipaddr for host in hosts}
        required_ips = len(hosts) + sum(
            position.ipaddr not in host_ips for position in positions
        )
        if required_ips > len(ip_pool):
            raise CommandError('Not enough documentation IP addresses for demo data.')

        identities = rng.sample(PEOPLE, len(users))
        selected_tokens = rng.sample(host_tokens, len(hosts))
        selected_ips = iter(rng.sample(ip_pool, required_ips))

        with transaction.atomic():
            self._anonymize_users(users, identities)
            ip_mapping = self._anonymize_hosts(hosts, selected_tokens, selected_ips)
            self._anonymize_positions(positions, ip_mapping, selected_ips)

        self.stdout.write(
            self.style.SUCCESS(
                f'Anonymized {len(users)} users, {len(hosts)} hosts and '
                f'{len(positions)} graph positions. Admin login: admin01.'
            )
        )

    @staticmethod
    def _anonymize_users(users, identities):
        for index, user in enumerate(users, start=1):
            user.username = f'anonymizing-{user.pk}-{index}'
            user.save(update_fields=['username'])

        admin_number = 0
        regular_number = 0
        for user, (first_name, last_name) in zip(users, identities):
            if user.is_superuser:
                admin_number += 1
                username = f'admin{admin_number:02d}'
            else:
                regular_number += 1
                username = f'user{regular_number:02d}'

            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.email = ''
            user.save(update_fields=['username', 'first_name', 'last_name', 'email'])

    @staticmethod
    def _anonymize_hosts(hosts, selected_tokens, selected_ips):
        ip_mapping = {}
        for index, (host, token) in enumerate(zip(hosts, selected_tokens), start=1):
            old_ip = host.ipaddr
            adjective, noun = token
            prefix = HOST_PREFIXES.get(host.device_type, 'node')
            host.hostname = f'{prefix}-{adjective}-{noun}-{index:03d}'
            host.ipaddr = next(selected_ips)
            host.save(update_fields=['hostname', 'ipaddr'])
            ip_mapping[old_ip] = host.ipaddr
        return ip_mapping

    @staticmethod
    def _anonymize_positions(positions, ip_mapping, selected_ips):
        original_ips = [(position, position.ipaddr) for position in positions]

        for position, _old_ip in original_ips:
            position.ipaddr = f'anonymizing:{position.pk}'
            position.save(update_fields=['ipaddr'])

        for position, old_ip in original_ips:
            if old_ip in ip_mapping:
                position.ipaddr = ip_mapping[old_ip]
            else:
                position.ipaddr = next(selected_ips)
            position.save(update_fields=['ipaddr'])
