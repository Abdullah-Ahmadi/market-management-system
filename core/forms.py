from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.forms import inlineformset_factory

from .models import (
    Customer,
    MonitorReport,
    MonitorVisit,
    Product,
    Role,
    Sale,
    SaleItem,
    SystemSetting,
    User,
    Zone,
)
from .permissions import (
    can_override_price,
    is_admin,
    is_management,
    is_manager,
    is_monitor,
    is_supervisor,
    visible_customers,
)


class BootstrapMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                css = 'form-check-input'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                css = 'form-select'
            else:
                css = 'form-control'
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {css}'.strip()


class ZoneForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Zone
        fields = ['code', 'name', 'supervisor', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supervisor'].queryset = User.objects.filter(
            role__code=Role.SUPERVISOR, is_active=True
        ).order_by('first_name', 'last_name', 'username')
        self.fields['supervisor'].empty_label = 'Select zone supervisor'
        self.apply_bootstrap()

    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper()
        if self.instance.pk and self.instance.customers.exists() and code != self.instance.code:
            raise forms.ValidationError(
                'Zone code cannot be changed after customer IDs have been issued for this zone.'
            )
        return code


class RoleForm(BootstrapMixin, forms.ModelForm):
    CORE_ADMIN_FIELDS = [
        'can_manage_users',
        'can_manage_market_data',
        'can_view_all_sales',
        'can_export',
        'can_backup',
        'can_edit_locked_sales',
    ]

    class Meta:
        model = Role
        fields = [
            'name',
            'level',
            'can_manage_users',
            'can_manage_market_data',
            'can_view_all_sales',
            'can_export',
            'can_backup',
            'can_edit_locked_sales',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.code == Role.ADMIN:
            self.fields['level'].disabled = True
            for name in self.CORE_ADMIN_FIELDS:
                self.fields[name].disabled = True
                self.fields[name].help_text = 'Required for the System Administrator role.'
        elif self.instance.pk:
            self.fields['can_backup'].disabled = True
            self.fields['can_backup'].help_text = 'Backup and restore are reserved for the System Administrator.'
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and self.instance.code == Role.ADMIN:
            cleaned['level'] = self.instance.level
            for name in self.CORE_ADMIN_FIELDS:
                cleaned[name] = True
        elif self.instance.pk:
            cleaned['can_backup'] = False
        return cleaned


class SelfProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone_number', 'profile_picture']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class CustomerForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['full_name', 'phone_number', 'address', 'zone', 'assigned_salesman', 'is_active']
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user and not is_management(user):
            if is_supervisor(user):
                self.fields['assigned_salesman'].queryset = user.subordinates.filter(
                    role__code=Role.SALESMAN, is_active=True
                )
                self.fields['zone'].queryset = Zone.objects.filter(supervisor=user, is_active=True)
            elif is_monitor(user):
                self.fields['assigned_salesman'].queryset = User.objects.filter(
                    role__code=Role.SALESMAN, zone_id=user.zone_id, is_active=True
                )
                self.fields['zone'].queryset = (
                    Zone.objects.filter(pk=user.zone_id, is_active=True)
                    if user.zone_id else Zone.objects.none()
                )
            else:
                self.fields['assigned_salesman'].queryset = User.objects.filter(pk=user.pk)
                self.fields['zone'].queryset = (
                    Zone.objects.filter(pk=user.zone_id) if user.zone_id else Zone.objects.none()
                )
        else:
            self.fields['assigned_salesman'].queryset = User.objects.filter(
                role__code=Role.SALESMAN, is_active=True
            ).select_related('zone')
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        user = self.user
        salesman = cleaned.get('assigned_salesman')
        zone = cleaned.get('zone')
        if salesman and zone and salesman.zone_id != zone.id:
            self.add_error('assigned_salesman', 'The salesman must belong to the selected zone.')
        if user and not is_management(user):
            if is_supervisor(user) and salesman and salesman.supervisor_id != user.id:
                self.add_error('assigned_salesman', 'Select one of your direct salesmen.')
            elif is_monitor(user):
                if zone and zone.id != user.zone_id:
                    self.add_error('zone', 'A monitor can manage customers only in the assigned zone.')
                if salesman and salesman.zone_id != user.zone_id:
                    self.add_error('assigned_salesman', 'Select a salesman from your assigned zone.')
                if user.zone_id:
                    cleaned['zone'] = user.zone
            elif not is_supervisor(user):
                cleaned['assigned_salesman'] = user
                if user.zone_id:
                    cleaned['zone'] = user.zone
        return cleaned


class ProductForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'size', 'unit', 'wholesale_price', 'retail_price', 'is_active']
        widgets = {
            'wholesale_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'retail_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class UserCreateForm(BootstrapMixin, UserCreationForm):
    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'employee_code',
            'role',
            'position',
            'phone_number',
            'zone',
            'supervisor',
            'manager',
            'profile_picture',
        ]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        if actor and not actor.is_superuser and actor.role:
            self.fields['role'].queryset = Role.objects.filter(level__lt=actor.role.level)
        self.fields['supervisor'].queryset = User.objects.filter(
            role__code=Role.SUPERVISOR, is_active=True
        )
        self.fields['manager'].queryset = User.objects.filter(
            role__code=Role.MANAGER, is_active=True
        )
        self.fields['supervisor'].help_text = 'Required for salesmen.'
        self.fields['manager'].help_text = 'Required for monitors.'
        self.fields['password1'].widget.attrs.update(
            {'data-password-primary': 'true', 'autocomplete': 'new-password'}
        )
        self.fields['password2'].widget.attrs.update(
            {'data-password-confirm': 'true', 'autocomplete': 'new-password'}
        )
        self.apply_bootstrap()


class UserEditForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'employee_code',
            'role',
            'position',
            'phone_number',
            'zone',
            'supervisor',
            'manager',
            'profile_picture',
            'is_active',
        ]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        if actor and not actor.is_superuser and actor.role:
            self.fields['role'].queryset = Role.objects.filter(level__lt=actor.role.level)
        self.fields['supervisor'].queryset = User.objects.filter(
            role__code=Role.SUPERVISOR, is_active=True
        ).exclude(pk=self.instance.pk)
        self.fields['manager'].queryset = User.objects.filter(
            role__code=Role.MANAGER, is_active=True
        ).exclude(pk=self.instance.pk)
        self.fields['supervisor'].help_text = 'Required for salesmen.'
        self.fields['manager'].help_text = 'Required for monitors.'
        if actor and self.instance.pk == actor.pk and (actor.is_superuser or actor.role_code() == Role.ADMIN):
            self.fields['role'].disabled = True
            self.fields['is_active'].disabled = True
            self.fields['role'].help_text = 'Your own System Administrator role cannot be reduced.'
            self.fields['is_active'].help_text = 'Your own administrator account cannot be disabled here.'
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        if self.actor and self.instance.pk == self.actor.pk and (self.actor.is_superuser or self.actor.role_code() == Role.ADMIN):
            cleaned['role'] = self.instance.role
            cleaned['is_active'] = True
        return cleaned


class SaleForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['sale_type', 'pricing_mode', 'customer', 'salesman', 'notes']
        widgets = {
            'customer': forms.HiddenInput(),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        from .permissions import visible_customers

        if user:
            self.fields['customer'].queryset = visible_customers(
                Customer.objects.filter(is_active=True), user
            )
            if is_management(user):
                self.fields['salesman'].queryset = User.objects.filter(
                    role__code=Role.SALESMAN, is_active=True
                )
            elif is_supervisor(user):
                self.fields['salesman'].queryset = user.subordinates.filter(
                    role__code=Role.SALESMAN, is_active=True
                )
            else:
                self.fields['salesman'].queryset = User.objects.filter(pk=user.pk)
                self.fields['salesman'].initial = user
                self.fields['salesman'].widget = forms.HiddenInput()

            settings = SystemSetting.get_solo()
            if not settings.allow_general_sales:
                self.fields['sale_type'].choices = [(Sale.CUSTOMER, 'Customer Sale')]
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        sale_type = cleaned.get('sale_type')
        customer = cleaned.get('customer')
        salesman = cleaned.get('salesman')
        user = self.user
        if sale_type == Sale.CUSTOMER and not customer:
            self.add_error('customer', 'A registered customer is required for a customer sale.')
        if sale_type == Sale.GENERAL:
            cleaned['customer'] = None
        if customer and salesman and customer.assigned_salesman_id != salesman.id:
            self.add_error('customer', 'This customer is not assigned to the selected salesman.')
        if user and not is_management(user) and not is_supervisor(user):
            cleaned['salesman'] = user
        return cleaned


class SaleItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price', 'discount']
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '1', 'min': '1', 'inputmode': 'numeric'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'discount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, user=None, pricing_mode=Sale.WHOLESALE, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.pricing_mode = pricing_mode or Sale.WHOLESALE
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        if user and not can_override_price(user):
            self.fields['unit_price'].required = False
            self.fields['unit_price'].widget.attrs.update(
                {
                    'readonly': 'readonly',
                    'tabindex': '-1',
                    'data-price-locked': 'true',
                    'title': 'Price is controlled by the product master price.',
                }
            )
            if not SystemSetting.get_solo().allow_salesman_discounts:
                self.fields['discount'].required = False
                self.fields['discount'].widget.attrs.update(
                    {'readonly': 'readonly', 'tabindex': '-1', 'value': '0'}
                )
        self.apply_bootstrap()

    def clean_unit_price(self):
        submitted = self.cleaned_data.get('unit_price')
        product = self.cleaned_data.get('product')
        if self.user and not can_override_price(self.user) and product:
            return product.price_for_mode(self.pricing_mode)
        return submitted

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and (
            quantity < 1 or quantity != quantity.to_integral_value()
        ):
            raise forms.ValidationError('Quantity must be a positive whole number of cases.')
        return quantity

    def clean_discount(self):
        discount = self.cleaned_data.get('discount') or 0
        if self.user and not can_override_price(self.user):
            settings = SystemSetting.get_solo()
            if not settings.allow_salesman_discounts:
                return 0
        return discount


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class MonitorReportForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MonitorReport
        fields = ['monitor', 'report_date', 'salesman', 'summary']
        widgets = {
            'report_date': forms.DateInput(attrs={'type': 'date'}),
            'summary': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Overall notes or route summary'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        monitors = User.objects.filter(role__code=Role.MONITOR, is_active=True).select_related('zone', 'manager')
        salesmen = User.objects.filter(role__code=Role.SALESMAN, is_active=True).select_related('zone')
        if user and is_monitor(user):
            monitors = monitors.filter(pk=user.pk)
            salesmen = salesmen.filter(zone_id=user.zone_id)
            self.fields['monitor'].initial = user
            self.fields['monitor'].widget = forms.HiddenInput()
        elif user and is_manager(user):
            monitors = monitors.filter(manager=user)
            salesmen = salesmen.filter(zone_id__in=monitors.values('zone_id'))
        elif user and not is_admin(user):
            monitors = monitors.none()
            salesmen = salesmen.none()
        self.fields['monitor'].queryset = monitors
        self.fields['salesman'].queryset = salesmen
        self.apply_bootstrap()

    def clean(self):
        cleaned = super().clean()
        monitor = cleaned.get('monitor')
        salesman = cleaned.get('salesman')
        if self.user and is_monitor(self.user):
            cleaned['monitor'] = self.user
            monitor = self.user
        if monitor and salesman and monitor.zone_id != salesman.zone_id:
            self.add_error('salesman', 'Select a salesman from the monitor\'s assigned zone.')
        if self.user and is_manager(self.user) and monitor and monitor.manager_id != self.user.id:
            self.add_error('monitor', 'Select one of the monitors who reports to you.')
        return cleaned


class MonitorVisitForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = MonitorVisit
        fields = [
            'customer',
            'shop_name',
            'has_company_chiller',
            'customer_comment',
            'shopkeeper_comment',
            'observations',
            'follow_up_required',
        ]
        widgets = {
            'customer_comment': forms.Textarea(attrs={'rows': 2}),
            'shopkeeper_comment': forms.Textarea(attrs={'rows': 2}),
            'observations': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = (
            visible_customers(
                Customer.objects.filter(is_active=True).select_related('zone', 'assigned_salesman'),
                user,
            ).order_by('customer_code')
            if user else Customer.objects.none()
        )
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = 'Select registered customer (optional)'
        self.apply_bootstrap()


MonitorVisitFormSet = inlineformset_factory(
    MonitorReport,
    MonitorVisit,
    form=MonitorVisitForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class SettingsForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = [
            'company_name',
            'company_short_name',
            'company_tagline',
            'company_logo',
            'currency',
            'salesman_edit_cutoff',
            'supervisor_extra_edit_hours',
            'allow_general_sales',
            'allow_salesman_discounts',
            'default_page_size',
            'default_report_range_days',
            'dashboard_trend_days',
            'customer_search_limit',
            'session_timeout_minutes',
            'support_phone',
            'support_email',
            'help_message',
        ]
        widgets = {
            'salesman_edit_cutoff': forms.TimeInput(attrs={'type': 'time'}),
            'help_message': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company_logo'].widget.attrs['accept'] = 'image/png,image/jpeg,image/webp'
        self.apply_bootstrap()


class BackupRestoreForm(BootstrapMixin, forms.Form):
    backup_file = forms.FileField(
        label='MMS backup file',
        help_text='Select a .mmsbackup package created by this system. Maximum upload size: 100 MB.',
    )
    confirmation = forms.CharField(
        label='Confirmation',
        help_text='Type RESTORE to confirm that current MMS business data will be replaced.',
        max_length=16,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()

    def clean_backup_file(self):
        f = self.cleaned_data['backup_file']
        if f.size > 100 * 1024 * 1024:
            raise forms.ValidationError('Backup file must be 100 MB or smaller.')
        if not f.name.lower().endswith('.mmsbackup'):
            raise forms.ValidationError('Select a valid .mmsbackup file.')
        return f

    def clean_confirmation(self):
        value = self.cleaned_data['confirmation'].strip().upper()
        if value != 'RESTORE':
            raise forms.ValidationError('Type RESTORE exactly to continue.')
        return value


class VoidSaleForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(max_length=255, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()
