from django.urls import NoReverseMatch, reverse

from .models import SystemSetting
from .permissions import (
    can_backup,
    can_export,
    can_manage_customers,
    can_manage_market,
    can_manage_users,
    can_use_sales,
    can_view_monitoring,
    is_management,
    is_monitor,
    is_supervisor,
)


def _standard_back_url(request):
    """Return a deterministic parent page, never browser-history state."""
    match = getattr(request, 'resolver_match', None)
    if not match:
        return None
    name = match.url_name
    kwargs = match.kwargs or {}
    pk = kwargs.get('pk')
    parent = {
        'customer_list': ('dashboard', {}),
        'customer_create': ('customer_list', {}),
        'customer_detail': ('customer_list', {}),
        'customer_edit': ('customer_detail', {'pk': pk}),
        'product_list': ('dashboard', {}),
        'product_create': ('product_list', {}),
        'product_detail': ('product_list', {}),
        'product_edit': ('product_detail', {'pk': pk}),
        'sale_list': ('dashboard', {}),
        'sale_create': ('sale_list', {}),
        'sale_detail': ('sale_list', {}),
        'sale_edit': ('sale_detail', {'pk': pk}),
        'sale_void': ('sale_detail', {'pk': pk}),
        'reports': ('dashboard', {}),
        'monitoring_list': ('dashboard', {}),
        'monitoring_create': ('monitoring_list', {}),
        'monitoring_detail': ('monitoring_list', {}),
        'monitoring_edit': ('monitoring_detail', {'pk': pk}),
        'user_list': ('dashboard', {}),
        'user_create': ('user_list', {}),
        'user_detail': ('user_list', {}),
        'user_edit': ('user_detail', {'pk': pk}),
        'settings': ('dashboard', {}),
        'audit_list': ('dashboard', {}),
        'audit_detail': ('audit_list', {}),
        'backup_center': ('dashboard', {}),
        'backup_restore': ('backup_center', {}),
        'zone_list': ('dashboard', {}),
        'zone_create': ('zone_list', {}),
        'zone_detail': ('zone_list', {}),
        'zone_edit': ('zone_detail', {'pk': pk}),
        'role_list': ('dashboard', {}),
        'role_edit': ('role_list', {}),
        'profile': ('dashboard', {}),
        'profile_edit': ('profile', {}),
        'password_change': ('profile', {}),
        'help': ('dashboard', {}),
    }.get(name)
    if not parent:
        return None
    route, route_kwargs = parent
    try:
        return reverse(route, kwargs=route_kwargs or None)
    except (NoReverseMatch, TypeError):
        return reverse('dashboard')


def mms_context(request):
    try:
        settings = SystemSetting.get_solo()
    except Exception:
        settings = None
    user = request.user
    authenticated = user.is_authenticated
    return {
        'mms_settings': settings,
        'ui_can_backup': authenticated and can_backup(user),
        'ui_can_export': authenticated and can_export(user),
        'ui_can_manage_customers': authenticated and can_manage_customers(user),
        'ui_can_manage_market': authenticated and can_manage_market(user),
        'ui_can_manage_users': authenticated and can_manage_users(user),
        'ui_can_record_sales': authenticated and can_use_sales(user),
        'ui_can_view_monitoring': authenticated and can_view_monitoring(user),
        'ui_is_monitor': authenticated and is_monitor(user),
        'ui_can_view_zones': authenticated and (
            is_management(user) or is_supervisor(user) or is_monitor(user)
        ),
        'mms_back_url': _standard_back_url(request) if authenticated else None,
    }
