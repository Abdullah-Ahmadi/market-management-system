from datetime import datetime, timedelta

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from .models import Role, SystemSetting


def code(user):
    return user.role.code if user.is_authenticated and user.role else ''


def is_admin(user):
    return user.is_superuser or code(user) == Role.ADMIN


def is_manager(user):
    return code(user) == Role.MANAGER


def is_management(user):
    return is_admin(user) or code(user) in {Role.MANAGER, Role.CLERK}


def is_supervisor(user):
    return code(user) == Role.SUPERVISOR


def is_monitor(user):
    return code(user) == Role.MONITOR


def is_salesman(user):
    return code(user) == Role.SALESMAN


def direct_report_ids(user):
    return list(user.subordinates.filter(is_active=True).values_list('id', flat=True))


def visible_sales(qs, user):
    if is_monitor(user):
        return qs.none()
    if is_management(user) or (user.role and user.role.can_view_all_sales):
        return qs
    if is_supervisor(user):
        return qs.filter(salesman__supervisor=user)
    return qs.filter(salesman=user)


def visible_customers(qs, user):
    if is_management(user):
        return qs
    if is_supervisor(user):
        return qs.filter(assigned_salesman__supervisor=user)
    if is_monitor(user):
        return qs.filter(zone_id=user.zone_id) if user.zone_id else qs.none()
    return qs.filter(assigned_salesman=user)


def visible_monitor_reports(qs, user):
    if is_admin(user):
        return qs
    if is_manager(user):
        return qs.filter(monitor__manager=user)
    if is_monitor(user):
        return qs.filter(monitor=user)
    return qs.none()


def can_manage_users(user):
    return is_admin(user) or bool(user.role and user.role.can_manage_users)


def can_manage_market(user):
    return is_management(user) or bool(user.role and user.role.can_manage_market_data)


def can_manage_customers(user):
    return is_management(user) or is_supervisor(user) or is_monitor(user)


def can_use_sales(user):
    return not is_monitor(user)


def can_export(user):
    return is_management(user) or is_supervisor(user) or bool(user.role and user.role.can_export)


def can_backup(user):
    # Backup/restore is a technical recovery function reserved for System Admin.
    return is_admin(user)


def can_override_price(user):
    """Operational leadership may override a transaction price; salesmen cannot."""
    return is_admin(user) or is_management(user) or is_supervisor(user)


def can_view_monitoring(user):
    return is_admin(user) or is_manager(user) or is_monitor(user)


def can_edit_monitor_report(user, report):
    return is_admin(user) or is_manager(user) or (is_monitor(user) and report.monitor_id == user.id)


def can_view_audit(user):
    return is_admin(user)


def can_manage_settings(user):
    return is_admin(user)


def cutoff_datetime(sale):
    settings = SystemSetting.get_solo()
    local = timezone.localtime(sale.transaction_time)
    naive = datetime.combine(local.date(), settings.salesman_edit_cutoff)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def can_edit_sale(user, sale, now=None):
    if sale.status == sale.VOIDED:
        return False
    now = now or timezone.now()
    cutoff = cutoff_datetime(sale)
    if is_admin(user) or (user.role and user.role.can_edit_locked_sales):
        return True
    if is_supervisor(user) and sale.salesman.supervisor_id == user.id:
        hours = SystemSetting.get_solo().supervisor_extra_edit_hours
        return now <= cutoff + timedelta(hours=hours)
    return sale.salesman_id == user.id and now <= cutoff


def require(condition):
    if not condition:
        raise PermissionDenied
