from datetime import time
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.utils import timezone


def validate_profile_size(value):
    if value.size > 2 * 1024 * 1024:
        raise ValidationError('Profile picture must be 2 MB or smaller.')


def validate_company_logo_size(value):
    if value.size > 3 * 1024 * 1024:
        raise ValidationError('Company logo must be 3 MB or smaller.')


class Role(models.Model):
    ADMIN = 'ADMIN'
    MANAGER = 'MANAGER'
    CLERK = 'CLERK'
    SUPERVISOR = 'SUPERVISOR'
    MONITOR = 'MONITOR'
    SALESMAN = 'SALESMAN'
    CODE_CHOICES = [
        (ADMIN, 'System Admin'),
        (MANAGER, 'Manager'),
        (CLERK, 'Sales Clerk'),
        (SUPERVISOR, 'Supervisor'),
        (MONITOR, 'Monitor'),
        (SALESMAN, 'Salesman'),
    ]

    code = models.CharField(max_length=20, choices=CODE_CHOICES, unique=True)
    name = models.CharField(max_length=80)
    level = models.PositiveSmallIntegerField(default=10)
    can_manage_users = models.BooleanField(default=False)
    can_manage_market_data = models.BooleanField(default=False)
    can_view_all_sales = models.BooleanField(default=False)
    can_export = models.BooleanField(default=False)
    can_backup = models.BooleanField(default=False)
    can_edit_locked_sales = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # System Administrator is a protected role. Its core capabilities cannot
        # be reduced through the MMS UI, Django admin, or ordinary model saves.
        if self.code == self.ADMIN:
            self.level = max(self.level or 0, 100)
            self.can_manage_users = True
            self.can_manage_market_data = True
            self.can_view_all_sales = True
            self.can_export = True
            self.can_backup = True
            self.can_edit_locked_sales = True
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ZoneSequence(models.Model):
    # Internal counter used to assign each zone a stable two-digit serial slot.
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    value = models.PositiveSmallIntegerField(default=0)


class Zone(models.Model):
    code = models.CharField(
        max_length=12,
        unique=True,
        validators=[RegexValidator(r'^[A-Za-z0-9]+$', 'Zone code may contain letters and numbers only.')],
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    supervisor = models.ForeignKey(
        'User',
        on_delete=models.PROTECT,
        null=True,
        related_name='supervised_zones',
        limit_choices_to={'role__code': Role.SUPERVISOR},
    )
    is_active = models.BooleanField(default=True)
    serial_number = models.PositiveSmallIntegerField(
        unique=True,
        null=True,
        blank=True,
        editable=False,
        help_text='Stable zone number used in the daily dispatch serial (01-99).',
    )
    customer_sequence = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.name}'

    def clean(self):
        super().clean()
        if self.supervisor_id and (
            not self.supervisor.role or self.supervisor.role.code != Role.SUPERVISOR
        ):
            raise ValidationError({'supervisor': 'The selected user must have the Supervisor role.'})

    def save(self, *args, **kwargs):
        if not self.serial_number:
            with transaction.atomic():
                seq, _ = ZoneSequence.objects.select_for_update().get_or_create(singleton=1)
                used = set(
                    Zone.objects.select_for_update()
                    .exclude(pk=self.pk)
                    .exclude(serial_number__isnull=True)
                    .values_list('serial_number', flat=True)
                )
                code = (self.code or '').strip().upper()
                preferred = ord(code) - ord('A') + 1 if len(code) == 1 and 'A' <= code <= 'Z' else None
                if preferred and preferred <= 99 and preferred not in used:
                    number = preferred
                else:
                    number = max(seq.value, 0) + 1
                    while number in used and number <= 99:
                        number += 1
                if number > 99:
                    raise ValidationError('MMS supports a maximum of 99 zone serial numbers.')
                self.serial_number = number
                if number > seq.value:
                    seq.value = number
                    seq.save(update_fields=['value'])
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def daily_serial(self, on_date=None):
        on_date = on_date or timezone.localdate()
        if not self.serial_number:
            raise ValidationError('Zone serial number has not been assigned.')
        return f'{on_date:%y%m%d}{self.serial_number:02d}'


class User(AbstractUser):
    employee_code = models.CharField(max_length=30, unique=True, null=True, blank=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name='users')
    position = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    supervisor = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates'
    )
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='monitors',
        limit_choices_to={'role__code': Role.MANAGER},
    )
    profile_picture = models.FileField(
        upload_to='profiles/%Y/%m/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']), validate_profile_size],
    )

    def clean(self):
        super().clean()
        if self.supervisor_id and self.supervisor_id == self.id:
            raise ValidationError({'supervisor': 'A user cannot supervise himself or herself.'})
        if self.supervisor_id and (
            not self.supervisor.role or self.supervisor.role.code != Role.SUPERVISOR
        ):
            raise ValidationError({'supervisor': 'The selected supervisor must have the Supervisor role.'})
        if self.manager_id and (
            not self.manager.role or self.manager.role.code != Role.MANAGER
        ):
            raise ValidationError({'manager': 'The selected manager must have the Manager role.'})
        if self.role and self.role.code == Role.SALESMAN:
            if not self.zone_id:
                raise ValidationError({'zone': 'A salesman must be assigned to a zone.'})
            if not self.supervisor_id:
                raise ValidationError({'supervisor': 'A salesman must be assigned to a supervisor.'})
            if self.zone_id and self.zone.supervisor_id and self.supervisor_id != self.zone.supervisor_id:
                raise ValidationError(
                    {'supervisor': 'The salesman supervisor must match the supervisor assigned to the zone.'}
                )
        if self.role and self.role.code == Role.MONITOR:
            if self.supervisor_id:
                raise ValidationError({'supervisor': 'A monitor is independent of the supervisor hierarchy.'})
            if not self.zone_id:
                raise ValidationError({'zone': 'A monitor must be assigned to a zone.'})
            if not self.manager_id:
                raise ValidationError({'manager': 'A monitor must report to a manager.'})
        elif self.manager_id:
            raise ValidationError({'manager': 'Manager assignment is used only for Monitor accounts.'})

    def role_code(self):
        return self.role.code if self.role else ''

    @property
    def display_name(self):
        return self.get_full_name() or self.username


class Customer(models.Model):
    customer_code = models.CharField(max_length=32, unique=True, editable=False)
    full_name = models.CharField(max_length=160)
    phone_number = models.CharField(max_length=30, blank=True)
    address = models.TextField()
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='customers')
    assigned_salesman = models.ForeignKey(User, on_delete=models.PROTECT, related_name='assigned_customers')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_customers')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['customer_code']

    def __str__(self):
        return f'{self.customer_code} - {self.full_name}'

    def save(self, *args, **kwargs):
        if not self.customer_code:
            with transaction.atomic():
                zone = Zone.objects.select_for_update().get(pk=self.zone_id)
                zone.customer_sequence += 1
                zone.save(update_fields=['customer_sequence'])
                self.customer_code = f'CUST-{zone.code.upper()}{zone.customer_sequence:05d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)


class ProductSequence(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    value = models.PositiveIntegerField(default=0)


class Product(models.Model):
    product_code = models.CharField(max_length=30, unique=True, editable=False)
    name = models.CharField(max_length=160)
    size = models.CharField(max_length=80, help_text='Examples: 330 ml, 500 ml, 1.5 L')
    unit = models.CharField(max_length=40, default='carton')
    wholesale_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))]
    )
    retail_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'size']

    def __str__(self):
        return f'{self.product_code} - {self.name} ({self.size})'

    def clean(self):
        super().clean()
        if (
            self.wholesale_price is not None
            and self.retail_price is not None
            and self.retail_price < self.wholesale_price
        ):
            raise ValidationError({'retail_price': 'Retail price cannot be lower than wholesale price.'})

    def save(self, *args, **kwargs):
        if not self.product_code:
            with transaction.atomic():
                seq, _ = ProductSequence.objects.select_for_update().get_or_create(singleton=1)
                seq.value += 1
                seq.save(update_fields=['value'])
                self.product_code = f'PROD-{seq.value:05d}'
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    def standard_price(self, sale_type):
        return self.retail_price if sale_type == Sale.GENERAL else self.wholesale_price

    def price_for_mode(self, pricing_mode):
        return self.retail_price if pricing_mode == Sale.RETAIL else self.wholesale_price


class SaleSequence(models.Model):
    # Retained for backward compatibility with earlier MMS backups/migrations.
    date = models.DateField(unique=True)
    value = models.PositiveIntegerField(default=0)


class ZoneSaleSequence(models.Model):
    # Per-zone, per-day counter used after the shared daily zone serial.
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='daily_sale_sequences')
    date = models.DateField()
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['zone', 'date'], name='unique_zone_sale_sequence_day')
        ]
        ordering = ['-date', 'zone']


class Sale(models.Model):
    CUSTOMER = 'CUSTOMER'
    GENERAL = 'GENERAL'
    SALE_TYPES = [(CUSTOMER, 'Customer Sale'), (GENERAL, 'General / Walk-in Sale')]

    WHOLESALE = 'WHOLESALE'
    RETAIL = 'RETAIL'
    PRICE_MODES = [(WHOLESALE, 'Wholesale'), (RETAIL, 'Retail')]

    SUBMITTED = 'SUBMITTED'
    LOCKED = 'LOCKED'
    VOIDED = 'VOIDED'
    CORRECTED = 'CORRECTED'
    STATUSES = [
        (SUBMITTED, 'Submitted'),
        (LOCKED, 'Locked'),
        (VOIDED, 'Voided'),
        (CORRECTED, 'Corrected'),
    ]

    sale_number = models.CharField(max_length=40, unique=True, editable=False)
    dispatch_serial = models.CharField(
        max_length=16,
        blank=True,
        editable=False,
        db_index=True,
        help_text='Shared daily serial for all salesmen in the same zone.',
    )
    salesman = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales')
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True, related_name='sales'
    )
    sale_type = models.CharField(max_length=12, choices=SALE_TYPES)
    pricing_mode = models.CharField(max_length=12, choices=PRICE_MODES, default=WHOLESALE)
    transaction_time = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=12, choices=STATUSES, default=SUBMITTED, db_index=True)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='sales_created')
    updated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='sales_updated', null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-transaction_time', '-id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(sale_type='GENERAL', customer__isnull=True)
                    | models.Q(sale_type='CUSTOMER', customer__isnull=False)
                ),
                name='sale_type_customer_consistency',
            )
        ]

    def __str__(self):
        return self.sale_number

    def clean(self):
        if self.sale_type == self.CUSTOMER and not self.customer_id:
            raise ValidationError({'customer': 'Customer sale requires a registered customer.'})
        if self.sale_type == self.GENERAL and self.customer_id:
            raise ValidationError({'customer': 'General sale cannot be linked to a registered customer.'})
        if (
            self.customer_id
            and self.salesman_id
            and self.customer.assigned_salesman_id != self.salesman_id
        ):
            raise ValidationError({'customer': 'Customer must be assigned to the selected salesman.'})
        if self.salesman_id and not self.salesman.zone_id:
            raise ValidationError({'salesman': 'A sale requires a salesman assigned to a zone.'})

    def save(self, *args, **kwargs):
        d = (
            timezone.localdate(self.transaction_time)
            if timezone.is_aware(self.transaction_time)
            else self.transaction_time.date()
        )
        if not self.sale_number:
            if not self.salesman_id or not self.salesman.zone_id:
                raise ValidationError('A sale requires a salesman assigned to a zone.')
            with transaction.atomic():
                zone = Zone.objects.select_for_update().get(pk=self.salesman.zone_id)
                if not zone.serial_number:
                    zone.save()
                dispatch = zone.daily_serial(d)
                seq, _ = ZoneSaleSequence.objects.select_for_update().get_or_create(zone=zone, date=d)
                seq.value += 1
                seq.save(update_fields=['value'])
                self.dispatch_serial = dispatch
                self.sale_number = f'SALE-{dispatch}-{seq.value:05d}'
                return super().save(*args, **kwargs)
        if not self.dispatch_serial and self.salesman_id and self.salesman.zone_id:
            self.dispatch_serial = self.salesman.zone.daily_serial(d)
        return super().save(*args, **kwargs)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sale_items')
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('1'))]
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))]
    )
    discount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    line_total = models.DecimalField(max_digits=16, decimal_places=2, default=0, editable=False)

    def clean(self):
        if self.quantity is not None:
            if self.quantity < 1 or self.quantity != self.quantity.to_integral_value():
                raise ValidationError({'quantity': 'Quantity must be a positive whole number of cases.'})
        if (
            self.quantity is not None
            and self.unit_price is not None
            and self.discount is not None
            and self.discount > self.quantity * self.unit_price
        ):
            raise ValidationError({'discount': 'Discount cannot exceed the gross line amount.'})

    def save(self, *args, **kwargs):
        self.line_total = max(Decimal('0'), self.quantity * self.unit_price - self.discount)
        super().save(*args, **kwargs)


class MonitorReport(models.Model):
    monitor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='monitor_reports'
    )
    salesman = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='monitoring_reports'
    )
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='monitor_reports')
    report_date = models.DateField(default=timezone.localdate, db_index=True)
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-report_date', '-created_at']

    def clean(self):
        super().clean()
        if self.monitor_id:
            if not self.monitor.role or self.monitor.role.code != Role.MONITOR:
                raise ValidationError({'monitor': 'The selected employee must have the Monitor role.'})
            if not self.monitor.zone_id:
                raise ValidationError({'monitor': 'The selected monitor must have an assigned zone.'})
        if self.salesman_id and (
            not self.salesman.role or self.salesman.role.code != Role.SALESMAN
        ):
            raise ValidationError({'salesman': 'The selected employee must have the Salesman role.'})
        if self.monitor_id and self.salesman_id and self.monitor.zone_id != self.salesman.zone_id:
            raise ValidationError({'salesman': 'The salesman must belong to the monitor\'s assigned zone.'})
        if self.monitor_id and self.zone_id and self.monitor.zone_id != self.zone_id:
            raise ValidationError({'zone': 'The report zone must match the monitor\'s assigned zone.'})
        if self.salesman_id and self.zone_id and self.salesman.zone_id != self.zone_id:
            raise ValidationError({'zone': 'The report zone must match the salesman\'s zone.'})

    def __str__(self):
        return f'{self.report_date} - {self.monitor.display_name} / {self.salesman.display_name}'


class MonitorVisit(models.Model):
    report = models.ForeignKey(MonitorReport, on_delete=models.CASCADE, related_name='visits')
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, null=True, blank=True, related_name='monitor_visits'
    )
    shop_name = models.CharField(
        max_length=160,
        blank=True,
        help_text='Use this when the visited shop is not yet registered as a customer.',
    )
    has_company_chiller = models.BooleanField(default=False)
    customer_comment = models.TextField(blank=True)
    shopkeeper_comment = models.TextField(blank=True)
    observations = models.TextField(blank=True)
    follow_up_required = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if not self.customer_id and not (self.shop_name or '').strip():
            raise ValidationError({'shop_name': 'Select a customer or enter the shop name.'})
        if (
            self.customer_id
            and self.report_id
            and self.customer.assigned_salesman_id != self.report.salesman_id
        ):
            raise ValidationError(
                {'customer': 'The selected customer must be assigned to the monitored salesman.'}
            )

    @property
    def display_shop(self):
        return self.customer.full_name if self.customer_id else self.shop_name

    def __str__(self):
        return self.display_shop


class AuditLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_events'
    )
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']


class SystemSetting(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    company_name = models.CharField(max_length=160, default='My Company')
    company_short_name = models.CharField(max_length=40, default='MMS')
    company_tagline = models.CharField(max_length=180, blank=True, default='Market Management System')
    company_logo = models.FileField(
        upload_to='branding/',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']),
            validate_company_logo_size,
        ],
        help_text='PNG, JPG/JPEG or WebP; maximum 3 MB.',
    )
    currency = models.CharField(max_length=12, default='AFN')
    salesman_edit_cutoff = models.TimeField(default=time(19, 0))
    supervisor_extra_edit_hours = models.PositiveIntegerField(default=24)
    allow_general_sales = models.BooleanField(default=True)
    allow_salesman_discounts = models.BooleanField(default=True)
    default_page_size = models.PositiveSmallIntegerField(
        default=50, validators=[MinValueValidator(10), MaxValueValidator(200)]
    )
    default_report_range_days = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(1), MaxValueValidator(366)]
    )
    dashboard_trend_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(3), MaxValueValidator(31)]
    )
    customer_search_limit = models.PositiveSmallIntegerField(
        default=20, validators=[MinValueValidator(5), MaxValueValidator(100)]
    )
    session_timeout_minutes = models.PositiveSmallIntegerField(
        default=480, validators=[MinValueValidator(5), MaxValueValidator(1440)]
    )
    support_phone = models.CharField(max_length=40, blank=True)
    support_email = models.EmailField(blank=True)
    help_message = models.TextField(
        blank=True,
        default='If you need help that is not covered on this page, contact your supervisor or system administrator.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(singleton=1)
        return obj

    def __str__(self):
        return 'MMS Settings'
