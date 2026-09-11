from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from hosting.models import SegmentPolicy
from hosting.services.microsegmentation import find_route_violations


class Command(BaseCommand):
    help = 'Audit topology routes against microsegmentation policies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fail-on-violations',
            action='store_true',
            help='Return a non-zero exit code when violations are found',
        )
        parser.add_argument(
            '--protocol',
            choices=SegmentPolicy.Protocol.values,
            default=SegmentPolicy.Protocol.ANY,
            help='Traffic protocol to audit (default: any)',
        )
        parser.add_argument('--port', type=int, help='TCP or UDP destination port')

    def handle(self, *args, **options):
        try:
            violations = find_route_violations(
                protocol=options['protocol'],
                port=options['port'],
            )
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        if not violations:
            self.stdout.write(self.style.SUCCESS('No segmentation violations found'))
            return

        self.stdout.write(self.style.WARNING(f'Violations found: {len(violations)}'))
        for violation in violations:
            route = violation.route
            self.stdout.write(
                f'  {route.parent.ipaddr} -> {route.child.ipaddr}: {violation.reason}'
            )

        if options['fail_on_violations']:
            raise CommandError('Microsegmentation policy violations detected')
