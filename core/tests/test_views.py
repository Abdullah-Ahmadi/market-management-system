from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

from django.test import TestCase
from django.urls import reverse

from core.models import Customer, Product, Role, Sale, User, Zone


class MMSViewSecurityTests(TestCase):
    def setUp(self):
        self.sales_role = Role.objects.create(code=Role.SALESMAN, name='Salesman')
        self.sup_role = Role.objects.create(code=Role.SUPERVISOR, name='Supervisor')
        self.manager_role = Role.objects.create(code=Role.MANAGER, name='Manager', can_view_all_sales=True, can_manage_market_data=True, can_export=True)
        self.clerk_role = Role.objects.create(code=Role.CLERK, name='Sales Clerk', can_view_all_sales=True, can_manage_market_data=True, can_export=True)
        self.admin_role = Role.objects.create(code=Role.ADMIN, name='System Admin', can_view_all_sales=True, can_manage_market_data=True, can_manage_users=True, can_export=True, can_backup=True)
        self.zone = Zone.objects.create(code='A', name='A')
        self.sup = User.objects.create_user('sup', password='StrongTest!123', role=self.sup_role, zone=self.zone)
        self.zone.supervisor = self.sup
        self.zone.save(update_fields=['supervisor'])
        self.a = User.objects.create_user('a', password='StrongTest!123', role=self.sales_role, zone=self.zone, supervisor=self.sup)
        self.b = User.objects.create_user('b', password='StrongTest!123', role=self.sales_role, zone=self.zone, supervisor=self.sup)
        self.manager = User.objects.create_user('manager', password='StrongTest!123', role=self.manager_role)
        self.clerk = User.objects.create_user('clerk', password='StrongTest!123', role=self.clerk_role)
        self.admin = User.objects.create_user('admin', password='StrongTest!123', role=self.admin_role, is_superuser=True, is_staff=True)
        self.customer_a = Customer.objects.create(full_name='Alpha Shop', phone_number='0700', address='Market', zone=self.zone, assigned_salesman=self.a, created_by=self.a)
        self.customer_b = Customer.objects.create(full_name='Beta Shop', phone_number='0800', address='Market', zone=self.zone, assigned_salesman=self.b, created_by=self.b)
        self.sale = Sale.objects.create(salesman=self.a, sale_type=Sale.GENERAL, created_by=self.a)
        self.product = Product.objects.create(name='Pepsi', size='330 ml', unit='carton', wholesale_price=Decimal('10'), retail_price=Decimal('12'))

    def _sale_payload(self, salesman, sale_type='GENERAL', customer='', price='999'):
        return {
            'sale_type': sale_type,
            'customer': str(customer) if customer else '',
            'salesman': str(salesman.pk),
            'notes': 'test',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-product': str(self.product.pk),
            'items-0-quantity': '2',
            'items-0-unit_price': price,
            'items-0-discount': '1',
        }

    def test_login_required(self):
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)

    def test_salesman_cannot_open_other_salesman_sale(self):
        self.client.login(username='b', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('sale_detail', args=[self.sale.pk])).status_code, 404)

    def test_product_creation_forbidden_to_salesman(self):
        self.client.login(username='a', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('product_create')).status_code, 403)

    def test_salesman_posted_price_is_ignored_for_general_sale(self):
        self.client.login(username='a', password='StrongTest!123')
        response = self.client.post(reverse('sale_create'), self._sale_payload(self.a, price='999'))
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.exclude(pk=self.sale.pk).get()
        item = sale.items.get()
        self.assertEqual(item.unit_price, Decimal('12'))
        self.assertEqual(sale.total_amount, Decimal('23'))

    def test_salesman_customer_sale_uses_wholesale_price(self):
        self.client.login(username='a', password='StrongTest!123')
        response = self.client.post(reverse('sale_create'), self._sale_payload(self.a, 'CUSTOMER', self.customer_a.pk, '999'))
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.exclude(pk=self.sale.pk).get()
        self.assertEqual(sale.items.get().unit_price, Decimal('10'))

    def test_manager_can_override_unit_price(self):
        self.client.login(username='manager', password='StrongTest!123')
        response = self.client.post(reverse('sale_create'), self._sale_payload(self.a, price='99'))
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.exclude(pk=self.sale.pk).get()
        self.assertEqual(sale.items.get().unit_price, Decimal('99'))

    def test_customer_search_is_scoped_to_salesman(self):
        self.client.login(username='a', password='StrongTest!123')
        response = self.client.get(reverse('customer_search_api'), {'q': 'Shop'})
        ids = {r['id'] for r in response.json()['results']}
        self.assertIn(self.customer_a.id, ids)
        self.assertNotIn(self.customer_b.id, ids)

    def test_audit_log_is_admin_only(self):
        self.client.login(username='manager', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('audit_list')).status_code, 403)
        self.client.logout()
        self.client.login(username='admin', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('audit_list')).status_code, 200)

    def test_help_is_available_to_salesman(self):
        self.client.login(username='a', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('help')).status_code, 200)

    def test_excel_export_is_valid_zip_based_xlsx(self):
        self.client.login(username='manager', password='StrongTest!123')
        response = self.client.get(reverse('sales_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml.sheet', response['Content-Type'])
        with ZipFile(BytesIO(response.content)) as book:
            self.assertIn('xl/workbook.xml', book.namelist())
            self.assertIn('xl/worksheets/sheet1.xml', book.namelist())


class MMSRefinementViewTests(MMSViewSecurityTests):
    def test_reports_contain_cases_and_cash_analysis(self):
        from core.models import SaleItem
        SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            quantity=Decimal('4'),
            unit_price=Decimal('12'),
            discount=Decimal('0'),
        )
        self.sale.total_amount = Decimal('48')
        self.sale.save(update_fields=['total_amount'])
        self.client.login(username='manager', password='StrongTest!123')
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)
        chart_data = response.context['chart_data']
        self.assertIn('cases', chart_data)
        self.assertIn('cash', chart_data)
        self.assertIn('products', chart_data['cases'])
        self.assertIn('products', chart_data['cash'])

    def test_excel_export_contains_meaningful_analysis_sheets(self):
        self.client.login(username='manager', password='StrongTest!123')
        response = self.client.get(reverse('sales_excel'))
        with ZipFile(BytesIO(response.content)) as book:
            workbook = book.read('xl/workbook.xml').decode('utf-8')
            for sheet in ['Analysis', 'Daily Sales Report', 'Daily Trend', 'Salesmen', 'Products', 'Zones', 'Customers', 'Sale Mix', 'Transactions']:
                self.assertIn(f'name="{sheet}"', workbook)

    def test_daily_sales_report_sheet_is_available_to_admin_manager_and_clerk(self):
        for username in ['manager', 'clerk', 'admin']:
            self.client.logout()
            self.client.login(username=username, password='StrongTest!123')
            response = self.client.get(reverse('sales_excel'))
            self.assertEqual(response.status_code, 200)
            with ZipFile(BytesIO(response.content)) as book:
                workbook = book.read('xl/workbook.xml').decode('utf-8')
                self.assertIn('name="Daily Sales Report"', workbook)

    def test_daily_sales_report_contains_dispatch_and_product_columns(self):
        from core.models import SaleItem
        SaleItem.objects.create(
            sale=self.sale, product=self.product, quantity=Decimal('4'),
            unit_price=Decimal('12'), discount=Decimal('0')
        )
        self.client.login(username='manager', password='StrongTest!123')
        response = self.client.get(reverse('sales_excel'))
        with ZipFile(BytesIO(response.content)) as book:
            sheet = book.read('xl/worksheets/sheet2.xml').decode('utf-8')
            self.assertIn('Disp#', sheet)
            self.assertIn('Pepsi 330 ml', sheet)
            self.assertIn('Total Cases', sheet)

    def test_backup_is_admin_only_and_download_is_restorable_package(self):
        self.client.login(username='manager', password='StrongTest!123')
        self.assertEqual(self.client.get(reverse('backup_center')).status_code, 403)
        self.client.logout()
        self.client.login(username='admin', password='StrongTest!123')
        response = self.client.get(reverse('backup_export'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('.mmsbackup', response['Content-Disposition'])
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertIn('manifest.json', archive.namelist())
            self.assertIn('data.json', archive.namelist())

    def test_system_admin_cannot_demote_own_account(self):
        self.client.login(username='admin', password='StrongTest!123')
        payload = {
            'username': self.admin.username,
            'first_name': self.admin.first_name,
            'last_name': self.admin.last_name,
            'employee_code': self.admin.employee_code or '',
            'role': self.manager_role.pk,
            'position': self.admin.position,
            'phone_number': self.admin.phone_number,
            'zone': '',
            'supervisor': '',
            'is_active': '',
        }
        response = self.client.post(reverse('user_edit', args=[self.admin.pk]), payload)
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role_id, self.admin_role.pk)
        self.assertTrue(self.admin.is_active)
