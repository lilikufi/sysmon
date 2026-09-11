from django.core.management.base import BaseCommand, CommandError

from hosting.network_discovery import NetworkDiscovery


class Command(BaseCommand):
    help = "Discover network topology through SNMP"

    def add_arguments(self, parser):
        parser.add_argument("start_ip", help="IP address to start discovery from")
        parser.add_argument("--community", default="public", help="SNMP community")
        parser.add_argument("--max-hops", type=int, default=3)
        parser.add_argument("--max-devices", type=int, default=50)
        parser.add_argument("--timeout", type=int, default=2)
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **options):
        try:
            discovery = NetworkDiscovery(
                community=options["community"],
                timeout=options["timeout"],
            )
            hosts, connections = discovery.discover_network(
                options["start_ip"],
                max_hops=options["max_hops"],
                max_devices=options["max_devices"],
            )
            saved_count = discovery.save_to_database()
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Discovered devices: {len(hosts)}")
        self.stdout.write(f"Discovered connections: {len(connections)}")
        if options["verbose"]:
            for ip, info in sorted(hosts.items()):
                self.stdout.write(
                    f"  {ip}: {info.get('hostname') or 'Unknown'} "
                    f"({info.get('device_type') or 'Unknown'})"
                )
        self.stdout.write(self.style.SUCCESS(f"Saved devices: {saved_count}"))
