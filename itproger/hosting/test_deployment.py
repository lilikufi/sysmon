import ipaddress
import json
import math
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from hosting.models import Host


FIXTURE_PATH = Path(__file__).resolve().parent / 'fixtures' / 'demo_hosts.json'
DOCUMENTATION_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')
)


class DeploymentSetupTests(TestCase):
    @patch('hosting.management.commands.setup_deployment.getpass.getpass')
    @patch('builtins.input')
    def test_interactive_setup_keeps_password_out_of_configuration(self, prompt, password):
        prompt.side_effect = ['interactive-admin', 'admin@example.test', 'yes']
        password.side_effect = ['Safe-River-824!', 'Safe-River-824!']

        call_command('setup_deployment', verbosity=0)

        user = get_user_model().objects.get(username='interactive-admin')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password('Safe-River-824!'))
        self.assertNotEqual(user.password, 'Safe-River-824!')
        self.assertEqual(Host.objects.count(), 163)


class DemoFixturePrivacyTests(TestCase):
    def test_fixture_contains_only_documentation_addresses_and_safe_names(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
        host_fields = [item['fields'] for item in fixture if item['model'] == 'hosting.host']
        self.assertEqual(len(host_fields), 163)
        self.assertTrue(
            all(
                any(ipaddress.ip_address(host['ipaddr']) in network for network in DOCUMENTATION_NETWORKS)
                for host in host_fields
            )
        )
        self.assertTrue(all('-demo-' in host['hostname'] for host in host_fields))

        text = FIXTURE_PATH.read_text(encoding='utf-8').lower()
        for forbidden in ('kbm', 'lvsro', 'lvs-ro', '192.168.', '"com_str": "'):
            self.assertNotIn(forbidden, text)

    def test_fixture_uses_grouped_core_distribution_topology(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
        hosts = {
            item['pk']: item['fields']
            for item in fixture
            if item['model'] == 'hosting.host'
        }
        positions = {
            item['fields']['ipaddr']: item['fields']
            for item in fixture
            if item['model'] == 'hosting.nodeposition'
        }

        roots = [pk for pk, host in hosts.items() if host['parents'] is None]
        self.assertEqual(len(roots), 1)
        root_pk = roots[0]
        branches = [pk for pk, host in hosts.items() if host['parents'] == root_pk]
        self.assertEqual(len(branches), 8)

        root_position = positions[hosts[root_pk]['ipaddr']]
        branch_positions = [positions[hosts[pk]['ipaddr']] for pk in branches]
        branch_distances = [
            math.hypot(
                position['x'] - root_position['x'],
                position['y'] - root_position['y'],
            )
            for position in branch_positions
        ]
        self.assertTrue(all(distance > 100 for distance in branch_distances))

        for pk, host in hosts.items():
            if pk == root_pk or pk in branches:
                continue
            self.assertIn(host['parents'], branches)
            child_position = positions[host['ipaddr']]
            parent_position = positions[hosts[host['parents']]['ipaddr']]
            child_distance = math.hypot(
                child_position['x'] - root_position['x'],
                child_position['y'] - root_position['y'],
            )
            parent_distance = math.hypot(
                parent_position['x'] - root_position['x'],
                parent_position['y'] - root_position['y'],
            )
            self.assertGreater(child_distance, parent_distance)

        self.assertTrue(all(170 <= position['x'] <= 1430 for position in positions.values()))
        self.assertTrue(all(130 <= position['y'] <= 750 for position in positions.values()))
