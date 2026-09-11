import subprocess
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from hosting.models import Host, Route
from hosting.network_discovery import NetworkDiscovery


class NetworkDiscoveryCommandTests(SimpleTestCase):
    def test_snmp_get_uses_argument_list_without_shell(self):
        completed = subprocess.CompletedProcess([], 0, stdout="value\n", stderr="")

        with patch("hosting.network_discovery.subprocess.run", return_value=completed) as run:
            result = NetworkDiscovery(community="public").snmp_get(
                "192.0.2.10", "1.3.6.1.2.1.1.5.0"
            )

        self.assertEqual(result, "value")
        args, kwargs = run.call_args
        self.assertEqual(args[0][0], "snmpget")
        self.assertIn("192.0.2.10", args[0])
        self.assertNotIn("shell", kwargs)

    def test_invalid_network_inputs_are_rejected_before_execution(self):
        discovery = NetworkDiscovery()

        with patch("hosting.network_discovery.subprocess.run") as run:
            with self.assertRaises(ValueError):
                discovery.snmp_get("192.0.2.1;whoami", "1.3.6.1")
            with self.assertRaises(ValueError):
                discovery.snmp_get("192.0.2.1", "1.3.6;whoami")

        run.assert_not_called()

    def test_missing_network_binary_is_handled(self):
        with patch(
            "hosting.network_discovery.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = NetworkDiscovery().snmp_walk("192.0.2.1", "1.3.6.1")

        self.assertEqual(result, [])

    def test_discovery_limits_are_validated(self):
        discovery = NetworkDiscovery()

        with self.assertRaises(ValueError):
            discovery.discover_network("192.0.2.1", max_hops=0)
        with self.assertRaises(ValueError):
            discovery.discover_network("192.0.2.1", max_devices=1001)


class NetworkDiscoveryPersistenceTests(TestCase):
    def test_hosts_and_connections_are_saved_in_one_operation(self):
        discovery = NetworkDiscovery(community="test-community")
        discovery.discovered_hosts = {
            "192.0.2.1": {
                "hostname": "router",
                "device_type": "routers",
                "online": True,
                "SNMP": True,
            },
            "192.0.2.2": {
                "hostname": "server",
                "device_type": "servers",
                "online": True,
                "SNMP": True,
            },
        }
        discovery.connections = [("192.0.2.1", "192.0.2.2")]

        self.assertEqual(discovery.save_to_database(), 2)

        parent = Host.objects.get(ipaddr="192.0.2.1")
        child = Host.objects.get(ipaddr="192.0.2.2")
        self.assertEqual(child.parents, parent)
        self.assertTrue(Route.objects.filter(parent=parent, child=child).exists())
        self.assertEqual(parent.com_str, "test-community")
