# Initial MMS schema. Compatible with Django 5.1/5.2.
from datetime import time
from decimal import Decimal
import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
import core.models
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

class Migration(migrations.Migration):
    initial = True
    dependencies = [('auth', '0012_alter_user_first_name_max_length')]
    operations = [
        migrations.CreateModel(name='Role', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('code', models.CharField(choices=[('ADMIN','System Admin'),('MANAGER','Manager'),('CLERK','Sales Clerk'),('SUPERVISOR','Supervisor'),('SALESMAN','Salesman')], max_length=20, unique=True)),
            ('name', models.CharField(max_length=80)), ('level', models.PositiveSmallIntegerField(default=10)),
            ('can_manage_users', models.BooleanField(default=False)), ('can_manage_market_data', models.BooleanField(default=False)), ('can_view_all_sales', models.BooleanField(default=False)), ('can_export', models.BooleanField(default=False)), ('can_backup', models.BooleanField(default=False)), ('can_edit_locked_sales', models.BooleanField(default=False)),
        ]),
        migrations.CreateModel(name='Zone', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('code', models.CharField(max_length=12, unique=True, validators=[django.core.validators.RegexValidator('^[A-Za-z0-9]+$', 'Zone code may contain letters and numbers only.')])), ('name', models.CharField(max_length=120)), ('description', models.TextField(blank=True)), ('is_active', models.BooleanField(default=True)), ('customer_sequence', models.PositiveIntegerField(default=0, editable=False)),
        ], options={'ordering':['code']}),
        migrations.CreateModel(name='Product', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('product_code', models.CharField(max_length=30, unique=True)), ('name', models.CharField(max_length=160)), ('unit', models.CharField(default='unit', max_length=40)), ('default_price', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))])), ('is_active', models.BooleanField(default=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
        ], options={'ordering':['name']}),
        migrations.CreateModel(name='SaleSequence', fields=[('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('date', models.DateField(unique=True)), ('value', models.PositiveIntegerField(default=0))]),
        migrations.CreateModel(name='SystemSetting', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('singleton', models.PositiveSmallIntegerField(default=1, editable=False, unique=True)), ('company_name', models.CharField(default='My Company', max_length=160)), ('currency', models.CharField(default='AFN', max_length=12)), ('salesman_edit_cutoff', models.TimeField(default=time(19,0))), ('supervisor_extra_edit_hours', models.PositiveIntegerField(default=24)), ('updated_at', models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name='User', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('password', models.CharField(max_length=128, verbose_name='password')), ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')), ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
            ('username', models.CharField(error_messages={'unique':'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
            ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')), ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')), ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')), ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')), ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')), ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
            ('employee_code', models.CharField(blank=True, max_length=30, null=True, unique=True)), ('position', models.CharField(blank=True, max_length=100)), ('phone_number', models.CharField(blank=True, max_length=30)), ('profile_picture', models.FileField(blank=True, null=True, upload_to='profiles/%Y/%m/', validators=[django.core.validators.FileExtensionValidator(['jpg','jpeg','png','webp']), core.models.validate_profile_size])),
            ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')), ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ('role', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='users', to='core.role')), ('zone', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employees', to='core.zone')), ('supervisor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subordinates', to='core.user')),
        ], options={'abstract':False}, managers=[('objects', django.contrib.auth.models.UserManager())]),
        migrations.CreateModel(name='Customer', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('customer_code', models.CharField(editable=False, max_length=32, unique=True)), ('full_name', models.CharField(max_length=160)), ('phone_number', models.CharField(blank=True, max_length=30)), ('address', models.TextField()), ('is_active', models.BooleanField(default=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
            ('zone', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='customers', to='core.zone')), ('assigned_salesman', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assigned_customers', to='core.user')), ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_customers', to='core.user')),
        ], options={'ordering':['customer_code']}),
        migrations.CreateModel(name='Sale', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('sale_number', models.CharField(editable=False, max_length=40, unique=True)), ('sale_type', models.CharField(choices=[('CUSTOMER','Customer Sale'),('GENERAL','General / Walk-in Sale')], max_length=12)), ('transaction_time', models.DateTimeField(db_index=True, default=django.utils.timezone.now)), ('status', models.CharField(choices=[('SUBMITTED','Submitted'),('LOCKED','Locked'),('VOIDED','Voided'),('CORRECTED','Corrected')], db_index=True, default='SUBMITTED', max_length=12)), ('total_amount', models.DecimalField(decimal_places=2, default=0, max_digits=16)), ('notes', models.TextField(blank=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)), ('locked_at', models.DateTimeField(blank=True, null=True)), ('void_reason', models.CharField(blank=True, max_length=255)),
            ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='core.customer')), ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sales_created', to='core.user')), ('salesman', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='core.user')), ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales_updated', to='core.user')),
        ], options={'ordering':['-transaction_time','-id']}),
        migrations.CreateModel(name='SaleItem', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('quantity', models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])), ('unit_price', models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))])), ('discount', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))])), ('line_total', models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=16)), ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sale_items', to='core.product')), ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.sale')),
        ]),
        migrations.CreateModel(name='AuditLog', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('action', models.CharField(db_index=True, max_length=80)), ('entity_type', models.CharField(blank=True, max_length=80)), ('entity_id', models.CharField(blank=True, max_length=80)), ('description', models.TextField(blank=True)), ('old_value', models.JSONField(blank=True, null=True)), ('new_value', models.JSONField(blank=True, null=True)), ('ip_address', models.GenericIPAddressField(blank=True, null=True)), ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)), ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_events', to='core.user')),
        ], options={'ordering':['-created_at']}),
        migrations.AddConstraint(model_name='sale', constraint=models.CheckConstraint(condition=(models.Q(sale_type='GENERAL',customer__isnull=True)|models.Q(sale_type='CUSTOMER',customer__isnull=False)), name='sale_type_customer_consistency')),
    ]
