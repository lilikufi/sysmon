import subprocess
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from hosting.models import Host
from hosting.services.nagios import (
    delete_host_configuration,
    render_host_configuration,
    sync_host_configuration,
)
from hosting.services.snmp import get_device_identity


class SnmpServiceTests(SimpleTestCase):
    def test_device_identity_uses_validated_remote_commands(self):
        name = Mock(ok=True, stdout='SNMPv2-MIB::sysName.0 = STRING: core-switch\n')
        description = Mock(ok=True, stdout='SNMPv2-MIB::sysDescr.0 = STRING: Cisco IOS\n')

        with patch(
            'hosting.services.snmp.connector.run',
            side_effect=[name, description],
        ) as run:
            result = get_device_identity('192.0.2.10', 'public')

        self.assertEqual(result, ('nexus', 'core-switch', True))
        self.assertEqual(run.call_count, 2)
        self.assertIn('192.0.2.10', run.call_args_list[0].args[0])

    def test_invalid_community_is_rejected_before_remote_execution(self):
        with patch('hosting.services.snmp.connector.run') as run:
            with self.assertRaises(ValueError):
                get_device_identity('192.0.2.10', 'public;whoami')

        run.assert_not_called()


class NagiosServiceTests(SimpleTestCase):
    def test_invalid_hostname_is_rejected_before_remote_execution(self):
        with patch('hosting.services.nagios.connector.run') as run:
            status, _message = delete_host_configuration('servers', 'node;whoami')

        self.assertFalse(status)
        run.assert_not_called()

    def test_valid_host_removes_references_and_configuration(self):
        completed = Mock(ok=True)
        with patch(
            'hosting.services.nagios.connector.run',
            return_value=completed,
        ) as run:
            status, message = delete_host_configuration('servers', 'srv-01')

        self.assertTrue(status)
        self.assertEqual(message, 'Host removed')
        self.assertEqual(run.call_count, 2)

    def test_configuration_contains_host_parent_and_selected_service(self):
        parent = Host(ipaddr='192.0.2.1', hostname='core-01')
        parent.pk = 1
        host = Host(
            ipaddr='192.0.2.2',
            hostname='srv-02',
            device_type='servers',
            parents=parent,
            SNMP=True,
            osver='linux',
        )

        configuration = render_host_configuration(host, ['uptime'])

        self.assertIn('\thost_name\tsrv-02', configuration)
        self.assertIn('\tparents\tcore-01', configuration)
        self.assertIn('\tservice_description\tUptime', configuration)

    def test_sync_reports_unavailable_monitoring_server(self):
        host = Host(
            ipaddr='192.0.2.2',
            hostname='srv-02',
            device_type='servers',
        )
        with patch(
            'hosting.services.nagios.connector.sftp',
            side_effect=RuntimeError('not configured'),
        ):
            status, message = sync_host_configuration(host)

        self.assertFalse(status)
        self.assertIn('Nagios is unavailable', message)

    def test_sync_writes_file_and_restarts_nagios(self):
        host = Host(
            ipaddr='192.0.2.2',
            hostname='srv-02',
            device_type='servers',
        )
        remote_file = MagicMock()
        sftp = Mock()
        sftp.file.return_value = remote_file
        restart = Mock(ok=True)
        with (
            patch('hosting.services.nagios.connector.sftp', return_value=sftp),
            patch('hosting.services.nagios.connector.run', return_value=restart) as run,
        ):
            status, _message = sync_host_configuration(host)

        self.assertTrue(status)
        remote_file.__enter__.return_value.write.assert_called_once()
        run.assert_called_once_with('sudo systemctl restart nagios', hide=True, warn=True)


class CheckSnmpViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='snmp-view-user',
            password='unused',
        )
        self.client.force_login(self.user)

    @patch('hosting.monitoring_views.get_device_identity')
    @patch('hosting.monitoring_views.subprocess.run')
    def test_successful_check_returns_detected_identity(self, run, identity):
        run.return_value = subprocess.CompletedProcess([], 0)
        identity.return_value = ('nexus', 'core-switch', True)

        response = self.client.get(
            reverse('check_snmp'),
            {'ipaddr': '192.0.2.55', 'com_str': 'public'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'core-switch')
        self.assertContains(response, 'nexus')
