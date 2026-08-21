import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import BaseCommand, CommandError, call_command
from django.core.validators import validate_email

from hosting.models import Category, Host, NodePosition, Service


class Command(BaseCommand):
    help = 'Interactively create an administrator and optionally load sample data.'

    def handle(self, *args, **options):
        self._create_admin()
        self._load_demo_data()

    def _create_admin(self):
        User = get_user_model()
        username = input('Administrator username [admin]: ').strip() or 'admin'
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User {username!r} already exists.')

        email = input('Administrator email (optional): ').strip()
        if email:
            try:
                validate_email(email)
            except ValidationError as exc:
                raise CommandError(exc.messages[0]) from exc

        password = self._read_password(username, email)
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        self.stdout.write(self.style.SUCCESS(f'Created administrator {username!r}.'))

    def _read_password(self, username, email):
        User = get_user_model()
        candidate_user = User(username=username, email=email)
        for _attempt in range(3):
            password = getpass.getpass('Administrator password: ')
            confirmation = getpass.getpass('Repeat password: ')
            if password != confirmation:
                self.stderr.write('Passwords do not match.')
                continue
            try:
                validate_password(password, user=candidate_user)
            except ValidationError as exc:
                self.stderr.write('\n'.join(exc.messages))
                continue
            return password
        raise CommandError('Administrator password was not accepted after three attempts.')

    def _load_demo_data(self):
        answer = input('Load sample inventory? [y/N]: ').strip().lower()
        if answer not in {'y', 'yes', 'd', 'da'}:
            self.stdout.write('Sample data was not requested.')
            return
        if any(model.objects.exists() for model in (Host, Service, NodePosition, Category)):
            raise CommandError('Inventory is not empty; sample data was not loaded.')
        call_command('loaddata', 'demo_hosts', verbosity=0)
        self.stdout.write(self.style.SUCCESS('Loaded sample inventory.'))
