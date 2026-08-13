import json
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from hosting.models import Host, LineSettings, Route
from hosting.consumers import SSHConsumer


def host_form_data(**overrides):
    data = {
        'ipaddr': '192.0.2.50',
        'hostname': 'srv-50',
        'com_str': 'public',
        'parents': '',
        'device_type': 'servers',
    }
    data.update(overrides)
    return data


class AuthenticationFlowTests(TestCase):
    def test_password_change_redirects_to_existing_page(self):
        user = get_user_model().objects.create_user(
            username='password-flow-user',
            password='old-password',
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse('password_change'),
            {
                'old_password': 'old-password',
                'new_password1': 'Violet-River-824!',
                'new_password2': 'Violet-River-824!',
            },
        )

        self.assertRedirects(response, reverse('service'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('Violet-River-824!'))


class HostCrudFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='host-flow-user',
            password='unused',
        )
        self.client.force_login(self.user)

    @patch('hosting.host_views.sync_host_configuration')
    @patch('hosting.host_views.get_device_identity')
    def test_add_host_saves_inventory_and_nagios_state(self, identity, sync):
        identity.return_value = ('nexus', 'detected-switch', True)
        sync.return_value = (True, 'Configuration updated')

        response = self.client.post(reverse('create_host'), host_form_data(hostname=''))

        host = Host.objects.get(ipaddr='192.0.2.50')
        self.assertRedirects(response, reverse('host-detail', args=[host.pk]))
        self.assertEqual(host.hostname, 'detected-switch')
        self.assertEqual(host.osver, 'nexus')
        self.assertTrue(host.SNMP)
        self.assertTrue(host.nagios_flag)
        sync.assert_called_once()

    @patch('hosting.host_views.sync_host_configuration')
    @patch('hosting.host_views.get_device_identity')
    def test_add_host_is_kept_when_nagios_is_unavailable(self, identity, sync):
        identity.return_value = (None, None, False)
        sync.return_value = (False, 'Nagios unavailable')

        response = self.client.post(reverse('create_host'), host_form_data())

        self.assertEqual(response.status_code, 302)
        host = Host.objects.get(ipaddr='192.0.2.50')
        self.assertFalse(host.nagios_flag)

    def test_invalid_add_host_does_not_write_database(self):
        response = self.client.post(
            reverse('create_host'),
            host_form_data(ipaddr='not-an-ip'),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Host.objects.exists())

    def test_simple_hosting_create_form_adds_host(self):
        response = self.client.post(reverse('hosting_create'), host_form_data())

        self.assertRedirects(response, reverse('service'))
        self.assertTrue(Host.objects.filter(ipaddr='192.0.2.50').exists())

    @patch('hosting.host_views.sync_host_configuration')
    @patch('hosting.host_views.get_device_identity')
    def test_edit_host_updates_fields_and_configuration(self, identity, sync):
        host = Host.objects.create(
            ipaddr='192.0.2.40',
            hostname='old-name',
            device_type='servers',
            com_str='public',
        )
        identity.return_value = ('nexus', 'ignored-name', True)
        sync.return_value = (True, 'Configuration updated')

        response = self.client.post(
            reverse('host-update', args=[host.pk]),
            host_form_data(ipaddr='192.0.2.41', hostname='new-name'),
        )

        host.refresh_from_db()
        self.assertRedirects(response, reverse('host-detail', args=[host.pk]))
        self.assertEqual(host.ipaddr, '192.0.2.41')
        self.assertEqual(host.hostname, 'new-name')
        self.assertTrue(host.nagios_flag)
        self.assertEqual(sync.call_args.kwargs['previous'], ('servers', 'old-name'))

    @patch('hosting.host_views.delete_host_configuration')
    def test_delete_host_removes_inventory_after_nagios_success(self, delete_config):
        host = Host.objects.create(
            ipaddr='192.0.2.60',
            hostname='srv-60',
            device_type='servers',
        )
        delete_config.return_value = (True, 'Deleted')

        response = self.client.post(reverse('host-delete', args=[host.pk]))

        self.assertRedirects(response, reverse('scan'))
        self.assertFalse(Host.objects.filter(pk=host.pk).exists())


class MapMutationFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='map-flow-user',
            password='unused',
        )
        self.client.force_login(self.user)
        self.parent = Host.objects.create(ipaddr='192.0.2.10', hostname='parent')
        self.child = Host.objects.create(ipaddr='192.0.2.11', hostname='child')

    def test_route_creation_updates_topology_relationship(self):
        response = self.client.post(
            reverse('save_route'),
            data=json.dumps(
                {
                    'parent': self.parent.ipaddr,
                    'child': self.child.ipaddr,
                    'waypoints': [[10, 20]],
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        route = Route.objects.get(parent=self.parent, child=self.child)
        self.assertEqual(route.waypoints, [[10, 20]])
        self.child.refresh_from_db()
        self.assertEqual(self.child.parents, self.parent)

    def test_coordinates_and_line_settings_are_saved(self):
        coordinates = self.client.post(
            reverse('update_host_coordinates'),
            {'ip_address': self.child.ipaddr, 'latitude': '55.1', 'longitude': '37.2'},
        )
        line = self.client.post(
            reverse('save_line_settings'),
            {'line_id': 'parent-child', 'color': '#00FF88', 'weight': '3', 'line_type': 'solid'},
        )

        self.assertEqual(coordinates.status_code, 200)
        self.assertEqual(line.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual((self.child.latitude, self.child.longitude), (55.1, 37.2))
        self.assertTrue(LineSettings.objects.filter(line_id='parent-child').exists())

    def test_add_host_reset_coordinates_and_read_positions(self):
        added = self.client.post(
            reverse('add_host_map'),
            {'ip_address': '192.0.2.99', 'latitude': '10', 'longitude': '20'},
        )
        reset = self.client.post(reverse('del_coord', args=['192.0.2.99']))
        self.client.post(
            reverse('graph_positions'),
            data=json.dumps({'ipaddr': '192.0.2.99', 'x': 100, 'y': 200}),
            content_type='application/json',
        )
        positions = self.client.get(reverse('graph_positions'))

        self.assertEqual(added.status_code, 200)
        self.assertEqual(reset.status_code, 200)
        host = Host.objects.get(ipaddr='192.0.2.99')
        self.assertEqual((host.latitude, host.longitude), (0.0, 0.0))
        self.assertJSONEqual(positions.content, {'192.0.2.99': {'x': 100.0, 'y': 200.0}})

    def test_legacy_map_renders(self):
        response = self.client.get(reverse('map'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'front/map.html')


class ExternalIntegrationFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='integration-flow-user',
            password='unused',
        )
        self.client.force_login(self.user)

    @patch('hosting.inventory_views.subprocess.run')
    def test_ping_returns_command_output(self, run):
        run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout='4 packets transmitted, 4 received',
            stderr='',
        )

        response = self.client.get(reverse('ping_host', args=['192.0.2.10']))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'output': '4 packets transmitted, 4 received'})
        self.assertIsInstance(run.call_args.args[0], list)

    @patch('hosting.terminal_views._open_linux_terminal')
    @patch('hosting.terminal_views.platform.system', return_value='Linux')
    def test_terminal_dispatches_validated_request(self, _system, open_linux):
        open_linux.return_value = {'success': True, 'message': 'opened'}

        response = self.client.post(
            reverse('open-terminal'),
            data=json.dumps(
                {
                    'ip': '192.0.2.10',
                    'protocol': 'ssh',
                    'username': 'admin',
                    'port': 22,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'success': True, 'message': 'opened'})
        open_linux.assert_called_once_with('192.0.2.10', 'ssh', 'admin', 22)

    def test_get_host_id_and_discovery_status(self):
        host = Host.objects.create(ipaddr='192.0.2.70', hostname='lookup-host', SNMP=True)

        host_id = self.client.get(reverse('get_host_id_by_ip'), {'ip': host.ipaddr})
        status = self.client.get(reverse('get_discovery_status'))

        self.assertJSONEqual(host_id.content, {'id': host.pk})
        self.assertEqual(status.status_code, 200)
        self.assertIn(status.json()['state'], {'idle', 'running', 'completed', 'failed'})

    @patch('hosting.monitoring_views.get_device_identity')
    def test_snmp_summary_returns_grouped_hosts(self, identity):
        Host.objects.create(
            ipaddr='192.0.2.71',
            hostname='summary-host',
            com_str='public',
        )
        identity.return_value = ('nexus', 'summary-host', True)

        response = self.client.get(reverse('mail'))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {'nexus': {'summary-host': ['192.0.2.71']}},
        )

    @patch('hosting.monitoring_views.process_host_data')
    @patch('hosting.monitoring_views.subprocess.run')
    def test_small_range_scan_processes_online_hosts(self, run, process):
        run.return_value = subprocess.CompletedProcess([], 0)

        response = self.client.post(
            reverse('range_ip'),
            {
                'start_ip': '192.0.2.80',
                'end_ip': '192.0.2.81',
                'community_string': 'public',
            },
        )

        self.assertRedirects(response, reverse('scan'))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(process.call_count, 2)

    @patch('hosting.discovery_views.threading.Thread')
    def test_discovery_request_starts_background_worker(self, thread):
        worker = Mock()
        thread.return_value = worker

        response = self.client.post(
            reverse('discover_network'),
            {
                'start_ip': '192.0.2.1',
                'community': 'public',
                'max_hops': '2',
                'max_devices': '20',
            },
        )

        self.assertRedirects(response, reverse('service'))
        worker.start.assert_called_once()
        args = thread.call_args.kwargs['args']
        self.assertEqual(args, ('192.0.2.1', 'public', 2, 20))


class SshConsumerTests(SimpleTestCase):
    async def test_anonymous_websocket_is_rejected(self):
        consumer = SSHConsumer()
        consumer.scope = {
            'user': SimpleNamespace(is_authenticated=False),
            'url_route': {'kwargs': {'session_id': 'test'}},
        }
        consumer.close = AsyncMock()

        await consumer.connect()

        consumer.close.assert_awaited_once_with(code=4401)

    async def test_authenticated_websocket_is_accepted(self):
        consumer = SSHConsumer()
        consumer.scope = {
            'user': SimpleNamespace(is_authenticated=True),
            'url_route': {'kwargs': {'session_id': 'test'}},
        }
        consumer.accept = AsyncMock()
        consumer.send = AsyncMock()

        await consumer.connect()

        consumer.accept.assert_awaited_once()
        payload = json.loads(consumer.send.await_args.args[0])
        self.assertEqual(payload['type'], 'status')

    async def test_invalid_ssh_target_is_rejected_before_connection(self):
        consumer = SSHConsumer()
        consumer.send = AsyncMock()
        consumer._create_ssh_connection = AsyncMock()

        await consumer.handle_ssh_connect(
            {
                'host': '192.0.2.1;whoami',
                'username': 'admin',
                'password': 'secret',
                'port': 22,
            }
        )

        consumer._create_ssh_connection.assert_not_awaited()
        payload = json.loads(consumer.send.await_args.args[0])
        self.assertEqual(payload['type'], 'error')
