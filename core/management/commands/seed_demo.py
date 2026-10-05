from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Customer, Product, Role, SystemSetting, User, Zone


class Command(BaseCommand):
    help = 'Create MMS roles and optional demonstration data.'

    def add_arguments(self, parser):
        parser.add_argument('--with-demo-data', action='store_true', help='Also create sample zones, employees, customers and products.')

    @transaction.atomic
    def handle(self, *args, **options):
        role_defs = {
            Role.ADMIN: dict(name='System Admin', level=100, can_manage_users=True, can_manage_market_data=True, can_view_all_sales=True, can_export=True, can_backup=True, can_edit_locked_sales=True),
            Role.MANAGER: dict(name='Manager', level=80, can_manage_users=False, can_manage_market_data=True, can_view_all_sales=True, can_export=True, can_backup=False, can_edit_locked_sales=True),
            Role.CLERK: dict(name='Sales Clerk', level=70, can_manage_users=False, can_manage_market_data=True, can_view_all_sales=True, can_export=True, can_backup=False, can_edit_locked_sales=False),
            Role.SUPERVISOR: dict(name='Supervisor', level=50, can_manage_users=False, can_manage_market_data=False, can_view_all_sales=False, can_export=True, can_backup=False, can_edit_locked_sales=False),
            Role.MONITOR: dict(name='Monitor', level=40, can_manage_users=False, can_manage_market_data=False, can_view_all_sales=False, can_export=False, can_backup=False, can_edit_locked_sales=False),
            Role.SALESMAN: dict(name='Salesman', level=20, can_manage_users=False, can_manage_market_data=False, can_view_all_sales=False, can_export=False, can_backup=False, can_edit_locked_sales=False),
        }
        roles = {}
        for code, defaults in role_defs.items():
            roles[code], _ = Role.objects.update_or_create(code=code, defaults=defaults)

        settings = SystemSetting.get_solo()
        settings.company_short_name = settings.company_short_name or 'MMS'
        settings.save()
        self.stdout.write(self.style.SUCCESS('Roles and system settings are ready.'))
        if not options['with_demo_data']:
            return

        a, _ = Zone.objects.get_or_create(code='A', defaults={'name': 'Central Market'})
        b, _ = Zone.objects.get_or_create(code='B', defaults={'name': 'East Market'})

        admin, _ = User.objects.get_or_create(username='admin', defaults={'first_name': 'System', 'last_name': 'Administrator', 'employee_code': 'EMP-0001', 'role': roles[Role.ADMIN], 'position': 'System Administrator', 'is_staff': True, 'is_superuser': True})
        admin.role = roles[Role.ADMIN]; admin.is_staff = True; admin.is_superuser = True; admin.set_password('MmsDemo!2026'); admin.save()

        sup, _ = User.objects.get_or_create(username='supervisor', defaults={'first_name': 'Sara', 'last_name': 'Supervisor', 'employee_code': 'EMP-0100', 'role': roles[Role.SUPERVISOR], 'position': 'Sales Supervisor', 'zone': a})
        sup.role = roles[Role.SUPERVISOR]; sup.zone = a; sup.set_password('MmsDemo!2026'); sup.save()
        a.supervisor = sup; a.save(update_fields=['supervisor'])

        sup_b, _ = User.objects.get_or_create(username='supervisor2', defaults={'first_name': 'Omid', 'last_name': 'Supervisor', 'employee_code': 'EMP-0200', 'role': roles[Role.SUPERVISOR], 'position': 'Sales Supervisor', 'zone': b})
        sup_b.role = roles[Role.SUPERVISOR]; sup_b.zone = b; sup_b.set_password('MmsDemo!2026'); sup_b.save()
        b.supervisor = sup_b; b.save(update_fields=['supervisor'])

        sales1, _ = User.objects.get_or_create(username='sales1', defaults={'first_name': 'Ahmad', 'last_name': 'Rahimi', 'employee_code': 'EMP-0101', 'role': roles[Role.SALESMAN], 'position': 'Salesman', 'zone': a, 'supervisor': sup})
        sales1.role = roles[Role.SALESMAN]; sales1.zone = a; sales1.supervisor = sup; sales1.set_password('MmsDemo!2026'); sales1.save()
        sales2, _ = User.objects.get_or_create(username='sales2', defaults={'first_name': 'Farid', 'last_name': 'Karimi', 'employee_code': 'EMP-0102', 'role': roles[Role.SALESMAN], 'position': 'Salesman', 'zone': a, 'supervisor': sup})
        sales2.role = roles[Role.SALESMAN]; sales2.zone = a; sales2.supervisor = sup; sales2.set_password('MmsDemo!2026'); sales2.save()

        manager, _ = User.objects.get_or_create(username='manager', defaults={'first_name': 'Farid', 'last_name': 'Ahmadi', 'employee_code': 'EMP-0010', 'role': roles[Role.MANAGER], 'position': 'Sales Manager'})
        manager.role = roles[Role.MANAGER]; manager.set_password('MmsDemo!2026'); manager.save()
        monitor, _ = User.objects.get_or_create(username='monitor1', defaults={'first_name': 'Hamid', 'last_name': 'Rahimi', 'employee_code': 'EMP-0300', 'role': roles[Role.MONITOR], 'position': 'Market Monitor', 'zone': a, 'manager': manager})
        monitor.role = roles[Role.MONITOR]; monitor.zone = a; monitor.manager = manager; monitor.set_password('MmsDemo!2026'); monitor.save()
        clerk, _ = User.objects.get_or_create(username='clerk', defaults={'first_name': 'Sales', 'last_name': 'Clerk', 'employee_code': 'EMP-0011', 'role': roles[Role.CLERK], 'position': 'Sales Clerk'})
        clerk.role = roles[Role.CLERK]; clerk.set_password('MmsDemo!2026'); clerk.save()

        product_defs = [
            ('Pepsi', '330 ml', 'carton', '680', '720'),
            ('Cristal Water', '500 ml', 'carton', '240', '280'),
            ('7UP', '1.5 L', 'carton', '700', '750'),
        ]
        for name, size, unit, wholesale, retail in product_defs:
            if not Product.objects.filter(name=name, size=size).exists():
                Product.objects.create(name=name, size=size, unit=unit, wholesale_price=Decimal(wholesale), retail_price=Decimal(retail))

        if not Customer.objects.filter(full_name='Demo Grocery').exists():
            Customer.objects.create(full_name='Demo Grocery', phone_number='0700000000', address='Central Market', zone=a, assigned_salesman=sales1, created_by=sales1)

        self.stdout.write(self.style.WARNING('Demo password for admin/manager/clerk/supervisor/supervisor2/monitor1/sales1/sales2: MmsDemo!2026'))
        self.stdout.write(self.style.WARNING('Change every demo password before real use.'))
