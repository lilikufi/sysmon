from django.core.management import BaseCommand
from django.db import transaction

from hosting.models import Host, Service


class Command(BaseCommand):
    help = 'Remove legacy labels from an existing sample inventory.'

    @transaction.atomic
    def handle(self, *args, **options):
        updated_hosts = 0
        for host in Host.objects.filter(hostname__icontains='-demo-'):
            host.hostname = host.hostname.replace('-demo-', '-')
            host.save(update_fields=['hostname'])
            updated_hosts += 1

        updated_places = 0
        for host in Host.objects.filter(place__istartswith='Demo zone '):
            host.place = f'Zone {host.place[len("Demo zone "):]}'
            host.save(update_fields=['place'])
            updated_places += 1

        suffix = ' (anonymized demo)'
        updated_services = 0
        for service in Service.objects.filter(status_information__icontains=suffix):
            service.status_information = service.status_information.replace(suffix, '')
            service.save(update_fields=['status_information'])
            updated_services += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Updated '
                f'{updated_hosts} host names, '
                f'{updated_places} locations and '
                f'{updated_services} service statuses.'
            )
        )
