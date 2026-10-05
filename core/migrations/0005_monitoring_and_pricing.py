from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def add_monitor_role_and_backfill_pricing(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    Sale = apps.get_model('core', 'Sale')
    Role.objects.update_or_create(
        code='MONITOR',
        defaults={
            'name': 'Monitor',
            'level': 40,
            'can_manage_users': False,
            'can_manage_market_data': False,
            'can_view_all_sales': False,
            'can_export': False,
            'can_backup': False,
            'can_edit_locked_sales': False,
        },
    )
    Sale.objects.filter(sale_type='GENERAL').update(pricing_mode='RETAIL')
    Sale.objects.filter(sale_type='CUSTOMER').update(pricing_mode='WHOLESALE')


class Migration(migrations.Migration):
    dependencies = [('core', '0004_zone_daily_serials')]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='code',
            field=models.CharField(
                choices=[
                    ('ADMIN', 'System Admin'),
                    ('MANAGER', 'Manager'),
                    ('CLERK', 'Sales Clerk'),
                    ('SUPERVISOR', 'Supervisor'),
                    ('MONITOR', 'Monitor'),
                    ('SALESMAN', 'Salesman'),
                ],
                max_length=20,
                unique=True,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={'role__code': 'MANAGER'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='monitors',
                to='core.user',
            ),
        ),
        migrations.AddField(
            model_name='sale',
            name='pricing_mode',
            field=models.CharField(
                choices=[('WHOLESALE', 'Wholesale'), ('RETAIL', 'Retail')],
                default='WHOLESALE',
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name='saleitem',
            name='quantity',
            field=models.DecimalField(
                decimal_places=2,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(Decimal('1'))],
            ),
        ),
        migrations.CreateModel(
            name='MonitorReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('report_date', models.DateField(db_index=True, default=timezone.localdate)),
                ('summary', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('monitor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='monitor_reports', to='core.user')),
                ('salesman', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='monitoring_reports', to='core.user')),
                ('zone', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='monitor_reports', to='core.zone')),
            ],
            options={'ordering': ['-report_date', '-created_at']},
        ),
        migrations.CreateModel(
            name='MonitorVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('shop_name', models.CharField(blank=True, help_text='Use this when the visited shop is not yet registered as a customer.', max_length=160)),
                ('has_company_chiller', models.BooleanField(default=False)),
                ('customer_comment', models.TextField(blank=True)),
                ('shopkeeper_comment', models.TextField(blank=True)),
                ('observations', models.TextField(blank=True)),
                ('follow_up_required', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='monitor_visits', to='core.customer')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visits', to='core.monitorreport')),
            ],
        ),
        migrations.RunPython(add_monitor_role_and_backfill_pricing, migrations.RunPython.noop),
    ]
