import os

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Role, SystemSetting, User


ROLE_DEFAULTS = {
    Role.ADMIN: dict(
        name='System Admin', level=100, can_manage_users=True,
        can_manage_market_data=True, can_view_all_sales=True, can_export=True,
        can_backup=True, can_edit_locked_sales=True,
    ),
    Role.MANAGER: dict(
        name='Manager', level=80, can_manage_users=False,
        can_manage_market_data=True, can_view_all_sales=True, can_export=True,
        can_backup=False, can_edit_locked_sales=True,
    ),
    Role.CLERK: dict(
        name='Sales Clerk', level=70, can_manage_users=False,
        can_manage_market_data=True, can_view_all_sales=True, can_export=True,
        can_backup=False, can_edit_locked_sales=False,
    ),
    Role.SUPERVISOR: dict(
        name='Supervisor', level=50, can_manage_users=False,
        can_manage_market_data=False, can_view_all_sales=False, can_export=True,
        can_backup=False, can_edit_locked_sales=False,
    ),
    Role.SALESMAN: dict(
        name='Salesman', level=20, can_manage_users=False,
        can_manage_market_data=False, can_view_all_sales=False, can_export=False,
        can_backup=False, can_edit_locked_sales=False,
    ),
}


class Command(BaseCommand):
    help = 'Ensure baseline roles/settings exist and create the first System Admin from environment variables.'

    @transaction.atomic
    def handle(self, *args, **options):
        roles = {}
        for code, defaults in ROLE_DEFAULTS.items():
            role, _ = Role.objects.get_or_create(code=code, defaults=defaults)
            roles[code] = role

        SystemSetting.get_solo()

        username = os.environ.get('MMS_ADMIN_USERNAME', '').strip()
        email = os.environ.get('MMS_ADMIN_EMAIL', '').strip()
        password = os.environ.get('MMS_ADMIN_PASSWORD', '')

        if not username or not password:
            self.stdout.write('Initial admin bootstrap skipped (MMS_ADMIN_USERNAME/PASSWORD not set).')
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': 'System',
                'last_name': 'Administrator',
                'employee_code': 'EMP-0001',
                'position': 'System Administrator',
                'role': roles[Role.ADMIN],
                'is_staff': True,
                'is_superuser': True,
            },
        )

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created initial System Admin: {username}'))
        else:
            self.stdout.write(f'Initial System Admin already exists: {username}')
