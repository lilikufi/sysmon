from django.contrib.auth import get_user_model
import json
import ipaddress

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import Host, Hosting, NodePosition, Ports, Service


class HostingSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='smoke-test-user',
            password='not-used-by-force-login',
        )
        self.host = Host.objects.create(ipaddr='192.0.2.10', hostname='test-switch')

    def test_home_requires_authentication(self):
        response = self.client.get(reverse('service'))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('service')}",
            fetch_redirect_response=False,
        )

    def test_authenticated_user_can_open_home(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('service'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'front/map3.html')

    def test_authenticated_inventory_pages_render(self):
        self.client.force_login(self.user)

        for url in [
            reverse('scan'),
            reverse('hosts'),
            reverse('host-detail', args=[self.host.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_sensitive_endpoints_require_authentication(self):
        endpoints = [
            ('post', reverse('host-hide', args=[self.host.pk])),
            ('post', reverse('host-unhide')),
            ('post', reverse('host-delete', args=[self.host.pk])),
            ('post', reverse('save_route')),
            ('post', reverse('update_host_coordinates')),
            ('post', reverse('save_line_settings')),
            ('post', reverse('add_host_map')),
            ('post', reverse('range_ip')),
            ('post', reverse('open-terminal')),
            ('get', reverse('check_snmp')),
            ('get', reverse('get_discovery_status')),
        ]

        for method, url in endpoints:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse('login')))

    def test_mutations_reject_get_requests(self):
        self.client.force_login(self.user)
        endpoints = [
            reverse('host-hide', args=[self.host.pk]),
            reverse('host-unhide'),
            reverse('host-delete', args=[self.host.pk]),
            reverse('save_route'),
            reverse('update_host_coordinates'),
            reverse('save_line_settings'),
            reverse('add_host_map'),
            reverse('range_ip'),
            reverse('open-terminal'),
        ]

        for url in endpoints:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_mutation_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(reverse('host-hide', args=[self.host.pk]))
        self.assertEqual(response.status_code, 403)
        self.host.refresh_from_db()
        self.assertFalse(self.host.hide_flag)

    def test_hide_host_uses_post(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('host-hide', args=[self.host.pk]))
        self.assertRedirects(response, reverse('scan'))
        self.host.refresh_from_db()
        self.assertTrue(self.host.hide_flag)

    def test_network_inputs_are_validated_before_running_commands(self):
        self.client.force_login(self.user)
        ping_response = self.client.get(reverse('ping_host', args=['not-an-ip']))
        snmp_response = self.client.get(
            reverse('check_snmp'),
            {'ipaddr': '192.0.2.1;whoami', 'com_str': 'public'},
        )
        terminal_response = self.client.post(
            reverse('open-terminal'),
            data=json.dumps({'ip': '192.0.2.1;whoami', 'protocol': 'ssh'}),
            content_type='application/json',
        )
        self.assertEqual(ping_response.status_code, 400)
        self.assertEqual(snmp_response.status_code, 400)
        self.assertEqual(terminal_response.status_code, 400)

    def test_scan_range_is_limited(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('range_ip'),
            {'start_ip': '192.0.2.1', 'end_ip': '192.0.6.2'},
        )
        self.assertEqual(response.status_code, 400)


class HostingModelTests(TestCase):
    def test_model_string_representations(self):
        host = Host.objects.create(ipaddr='192.0.2.20', hostname='router-1')
        hosting = Hosting.objects.create(title='Monitoring')
        service = Service.objects.create(host=host, description='PING', status='OK')
        port = Ports.objects.create(host=host, ifdescr='GigabitEthernet1', status='UP')

        self.assertEqual(str(host), 'router-1')
        self.assertEqual(str(hosting), 'Monitoring')
        self.assertEqual(str(service), 'PING on router-1')
        self.assertEqual(str(port), 'GigabitEthernet1 on router-1')


class AnonymizeDemoDataTests(TestCase):
    def test_command_replaces_identifying_data_and_preserves_passwords(self):
        User = get_user_model()
        admin = User.objects.create_superuser(
            username='real-admin',
            password='unchanged-password',
            email='admin@internal.example',
        )
        user = User.objects.create_user(
            username='real-user',
            password='unchanged-password',
            email='user@internal.example',
        )
        first_host = Host.objects.create(ipaddr='10.0.0.10', hostname='real-server')
        second_host = Host.objects.create(ipaddr='10.0.0.20', hostname='real-switch')
        NodePosition.objects.create(ipaddr=first_host.ipaddr, x=10, y=20)
        NodePosition.objects.create(ipaddr='10.0.0.99', x=30, y=40)

        call_command('anonymize_demo_data', seed=42, verbosity=0)

        admin.refresh_from_db()
        user.refresh_from_db()
        first_host.refresh_from_db()
        second_host.refresh_from_db()

        self.assertEqual(admin.username, 'admin01')
        self.assertEqual(user.username, 'user01')
        self.assertTrue(admin.check_password('unchanged-password'))
        self.assertTrue(user.check_password('unchanged-password'))
        self.assertTrue(admin.first_name and admin.last_name)
        self.assertTrue(user.first_name and user.last_name)
        self.assertEqual(admin.email, '')
        self.assertEqual(user.email, '')

        documentation_networks = [
            ipaddress.ip_network(network)
            for network in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')
        ]
        for address in [
            first_host.ipaddr,
            second_host.ipaddr,
            *NodePosition.objects.values_list('ipaddr', flat=True),
        ]:
            self.assertTrue(
                any(ipaddress.ip_address(address) in network for network in documentation_networks)
            )

        self.assertNotEqual(first_host.hostname, 'real-server')
        self.assertNotEqual(second_host.hostname, 'real-switch')
        self.assertEqual(
            NodePosition.objects.filter(
                ipaddr__in=[first_host.ipaddr, second_host.ipaddr]
            ).count(),
            1,
        )
