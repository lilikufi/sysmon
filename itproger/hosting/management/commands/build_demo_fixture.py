from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from hosting.services.demo_fixture import write_demo_fixture


class Command(BaseCommand):
    help = 'Build an anonymized fixture from Nagios status and scan files.'

    def add_arguments(self, parser):
        parser.add_argument('source_dir', type=Path)
        parser.add_argument(
            '--output',
            type=Path,
            default=Path(__file__).resolve().parents[2] / 'fixtures' / 'demo_hosts.json',
        )

    def handle(self, *args, **options):
        source_dir = options['source_dir']
        status_path = source_dir / 'status.dat'
        scan_path = source_dir / 'scan-stat.txt'
        if not status_path.is_file():
            raise CommandError(f'Nagios status file not found: {status_path}')

        fixture = write_demo_fixture(
            status_path,
            options['output'],
            scan_path if scan_path.is_file() else None,
        )
        host_count = sum(item['model'] == 'hosting.host' for item in fixture)
        service_count = sum(item['model'] == 'hosting.service' for item in fixture)
        self.stdout.write(
            self.style.SUCCESS(
                f'Wrote {host_count} anonymized hosts and {service_count} services '
                f'to {options["output"]}.'
            )
        )
