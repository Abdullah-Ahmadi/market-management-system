from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, Customer, Product, Role, Sale, SaleItem, SystemSetting, User, Zone

admin.site.site_header = 'MMS System Administration'
admin.site.site_title = 'MMS Admin'
admin.site.index_title = 'System Administration'


@admin.register(User)
class MMSUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('MMS Profile', {'fields': ('employee_code', 'role', 'position', 'phone_number', 'zone', 'supervisor', 'profile_picture')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('MMS Profile', {'fields': ('employee_code', 'role', 'position', 'phone_number', 'zone', 'supervisor')}),
    )
    list_display = ('username', 'first_name', 'last_name', 'employee_code', 'role', 'zone', 'supervisor', 'is_active')
    list_filter = ('role', 'zone', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'employee_code', 'phone_number')


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'supervisor', 'is_active')
    search_fields = ('code', 'name', 'supervisor__first_name', 'supervisor__last_name')
    list_filter = ('is_active',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('customer_code', 'full_name', 'zone', 'assigned_salesman', 'is_active')
    search_fields = ('customer_code', 'full_name', 'phone_number', 'address')
    list_filter = ('zone', 'is_active')
    readonly_fields = ('customer_code',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('product_code', 'name', 'size', 'unit', 'wholesale_price', 'retail_price', 'is_active')
    search_fields = ('product_code', 'name', 'size')
    list_filter = ('is_active', 'unit')
    readonly_fields = ('product_code',)


admin.site.register(Role)
admin.site.register(SystemSetting)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('line_total',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ('sale_number', 'transaction_time', 'salesman', 'customer', 'sale_type', 'status', 'total_amount')
    list_filter = ('status', 'sale_type', 'salesman')
    search_fields = ('sale_number', 'customer__customer_code', 'customer__full_name')
    inlines = [SaleItemInline]
    readonly_fields = ('sale_number', 'total_amount', 'created_at', 'updated_at', 'locked_at')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'entity_type', 'entity_id', 'ip_address')
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    list_filter = ('action', 'entity_type')
    search_fields = ('description', 'entity_id', 'user__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
