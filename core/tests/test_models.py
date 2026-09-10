from datetime import datetime, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.models import Customer, Product, Role, Sale, SaleItem, SystemSetting, User, Zone
from core.permissions import can_edit_sale, can_override_price, visible_sales


class MMSModelTests(TestCase):
    def setUp(self):
        self.sales_role = Role.objects.create(code=Role.SALESMAN, name='Salesman')
        self.sup_role = Role.objects.create(code=Role.SUPERVISOR, name='Supervisor')
        self.mgr_role = Role.objects.create(code=Role.MANAGER, name='Manager', can_view_all_sales=True, can_edit_locked_sales=True)
        self.zone = Zone.objects.create(code='A', name='Zone A')
        self.sup = User.objects.create_user('sup', password='StrongTest!123', role=self.sup_role, zone=self.zone)
        self.zone.supervisor = self.sup
        self.zone.save(update_fields=['supervisor'])
        self.s1 = User.objects.create_user('s1', password='StrongTest!123', role=self.sales_role, zone=self.zone, supervisor=self.sup)
        self.s2 = User.objects.create_user('s2', password='StrongTest!123', role=self.sales_role, zone=self.zone, supervisor=self.sup)
        self.manager = User.objects.create_user('mgr', password='StrongTest!123', role=self.mgr_role)
        self.product = Product.objects.create(name='Pepsi', size='330 ml', unit='carton', wholesale_price=Decimal('100'), retail_price=Decimal('120'))
        self.setting = SystemSetting.get_solo()
        self.setting.salesman_edit_cutoff = time(19, 0)
        self.setting.supervisor_extra_edit_hours = 24
        self.setting.save()

    def test_customer_codes_are_zone_sequential(self):
        c1 = Customer.objects.create(full_name='One', address='X', zone=self.zone, assigned_salesman=self.s1, created_by=self.s1)
        c2 = Customer.objects.create(full_name='Two', address='Y', zone=self.zone, assigned_salesman=self.s1, created_by=self.s1)
        self.assertEqual(c1.customer_code, 'CUST-A00001')
        self.assertEqual(c2.customer_code, 'CUST-A00002')

    def test_product_codes_are_generated_and_sequential(self):
        p2 = Product.objects.create(name='Cristal Water', size='500 ml', unit='carton', wholesale_price=Decimal('50'), retail_price=Decimal('60'))
        self.assertEqual(self.product.product_code, 'PROD-00001')
        self.assertEqual(p2.product_code, 'PROD-00002')

    def test_product_retail_price_cannot_be_below_wholesale(self):
        p = Product(name='Invalid', size='1 L', unit='carton', wholesale_price=Decimal('100'), retail_price=Decimal('90'))
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_zone_daily_serial_is_shared_and_sales_sequence_is_per_zone_day(self):
        tz = timezone.get_current_timezone()
        tx = timezone.make_aware(datetime(2026, 9, 10, 10, 0), tz)
        self.assertEqual(self.zone.serial_number, 1)
        self.assertEqual(self.zone.daily_serial(tx.date()), '26091001')

        a1 = Sale.objects.create(salesman=self.s1, sale_type=Sale.GENERAL, created_by=self.s1, transaction_time=tx)
        a2 = Sale.objects.create(salesman=self.s2, sale_type=Sale.GENERAL, created_by=self.s2, transaction_time=tx)
        self.assertEqual(a1.dispatch_serial, '26091001')
        self.assertEqual(a2.dispatch_serial, '26091001')
        self.assertEqual(a1.sale_number, 'SALE-26091001-00001')
        self.assertEqual(a2.sale_number, 'SALE-26091001-00002')

        zone_b = Zone.objects.create(code='B', name='Zone B')
        sup_b = User.objects.create_user('supb', password='StrongTest!123', role=self.sup_role, zone=zone_b)
        zone_b.supervisor = sup_b
        zone_b.save(update_fields=['supervisor'])
        s3 = User.objects.create_user('s3', password='StrongTest!123', role=self.sales_role, zone=zone_b, supervisor=sup_b)
        b1 = Sale.objects.create(salesman=s3, sale_type=Sale.GENERAL, created_by=s3, transaction_time=tx)
        self.assertEqual(zone_b.serial_number, 2)
        self.assertEqual(b1.dispatch_serial, '26091002')
        self.assertEqual(b1.sale_number, 'SALE-26091002-00001')

    def test_sale_item_calculates_line_total(self):
        sale = Sale.objects.create(salesman=self.s1, sale_type=Sale.GENERAL, created_by=self.s1)
        item = SaleItem.objects.create(sale=sale, product=self.product, quantity=Decimal('3'), unit_price=Decimal('100'), discount=Decimal('25'))
        self.assertEqual(item.line_total, Decimal('275'))

    def test_scope_prevents_other_salesman_access(self):
        a = Sale.objects.create(salesman=self.s1, sale_type=Sale.GENERAL, created_by=self.s1)
        b = Sale.objects.create(salesman=self.s2, sale_type=Sale.GENERAL, created_by=self.s2)
        self.assertEqual(list(visible_sales(Sale.objects.all(), self.s1)), [a])
        self.assertEqual(set(visible_sales(Sale.objects.all(), self.sup)), {a, b})
        self.assertEqual(set(visible_sales(Sale.objects.all(), self.manager)), {a, b})

    def test_salesman_cannot_override_price_but_supervisor_can(self):
        self.assertFalse(can_override_price(self.s1))
        self.assertTrue(can_override_price(self.sup))
        self.assertTrue(can_override_price(self.manager))

    def test_cutoff_salesman_then_supervisor_window(self):
        tz = timezone.get_current_timezone()
        tx = timezone.make_aware(datetime(2026, 9, 6, 10, 0), tz)
        sale = Sale.objects.create(salesman=self.s1, sale_type=Sale.GENERAL, created_by=self.s1, transaction_time=tx)
        before = timezone.make_aware(datetime(2026, 9, 6, 18, 59), tz)
        after = timezone.make_aware(datetime(2026, 9, 6, 19, 1), tz)
        next_day = timezone.make_aware(datetime(2026, 9, 7, 18, 0), tz)
        too_late = timezone.make_aware(datetime(2026, 9, 7, 20, 1), tz)
        self.assertTrue(can_edit_sale(self.s1, sale, before))
        self.assertFalse(can_edit_sale(self.s1, sale, after))
        self.assertTrue(can_edit_sale(self.sup, sale, next_day))
        self.assertFalse(can_edit_sale(self.sup, sale, too_late))
        self.assertTrue(can_edit_sale(self.manager, sale, too_late))


class MMSRefinementModelTests(TestCase):
    def test_username_similar_password_is_warning_not_validation_error(self):
        from django.contrib.auth.password_validation import validate_password
        user = User(username='alphauser')
        # Meets mandatory complexity/length rules while deliberately resembling the username.
        validate_password('AlphaUser!92X', user=user)

    def test_backup_round_trip_restores_business_data(self):
        from io import BytesIO
        from tempfile import TemporaryDirectory
        from django.test import override_settings
        from core.backup import build_backup_bytes, restore_backup

        admin_role = Role.objects.create(
            code=Role.ADMIN,
            name='System Admin',
            level=100,
            can_manage_users=True,
            can_manage_market_data=True,
            can_view_all_sales=True,
            can_export=True,
            can_backup=True,
            can_edit_locked_sales=True,
        )
        User.objects.create_user(
            'restoreadmin',
            password='RestoreAdmin!92',
            role=admin_role,
            is_superuser=True,
            is_staff=True,
        )
        Product.objects.create(
            name='Cristal Water', size='500 ml', unit='case',
            wholesale_price=Decimal('25'), retail_price=Decimal('30')
        )
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            snapshot = build_backup_bytes()
            Product.objects.create(
                name='Temporary Product', size='1 L', unit='case',
                wholesale_price=Decimal('1'), retail_price=Decimal('2')
            )
            restore_backup(BytesIO(snapshot))
        self.assertTrue(Product.objects.filter(name='Cristal Water').exists())
        self.assertFalse(Product.objects.filter(name='Temporary Product').exists())

    def test_admin_role_core_permissions_cannot_be_reduced(self):
        role = Role.objects.create(
            code=Role.ADMIN,
            name='Protected Admin',
            level=1,
            can_manage_users=False,
            can_manage_market_data=False,
            can_view_all_sales=False,
            can_export=False,
            can_backup=False,
            can_edit_locked_sales=False,
        )
        role.refresh_from_db()
        self.assertGreaterEqual(role.level, 100)
        self.assertTrue(role.can_manage_users)
        self.assertTrue(role.can_manage_market_data)
        self.assertTrue(role.can_view_all_sales)
        self.assertTrue(role.can_export)
        self.assertTrue(role.can_backup)
        self.assertTrue(role.can_edit_locked_sales)
