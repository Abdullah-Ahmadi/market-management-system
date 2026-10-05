import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import MonitorReportForm, MonitorVisitFormSet
from .models import MonitorReport, Role, User, Zone
from .permissions import (
    can_edit_monitor_report,
    can_view_monitoring,
    is_admin,
    is_manager,
    is_monitor,
    visible_monitor_reports,
)
from .services import audit


def _date_range(request):
    today = timezone.localdate()
    try:
        start = date.fromisoformat(request.GET.get('start')) if request.GET.get('start') else today - timedelta(days=29)
    except ValueError:
        start = today - timedelta(days=29)
    try:
        end = date.fromisoformat(request.GET.get('end')) if request.GET.get('end') else today
    except ValueError:
        end = today
    if start > end:
        start, end = end, start
    return start, end


def _allowed_monitors(user):
    qs = User.objects.filter(role__code=Role.MONITOR, is_active=True).select_related('zone', 'manager')
    if is_admin(user):
        return qs
    if is_manager(user):
        return qs.filter(manager=user)
    if is_monitor(user):
        return qs.filter(pk=user.pk)
    return qs.none()


def _allowed_salesmen(user):
    zones = _allowed_monitors(user).values('zone_id')
    return User.objects.filter(
        role__code=Role.SALESMAN,
        is_active=True,
        zone_id__in=zones,
    ).select_related('zone')


def _report_queryset(user):
    return visible_monitor_reports(
        MonitorReport.objects.select_related(
            'monitor', 'monitor__manager', 'salesman', 'zone'
        ).prefetch_related('visits__customer'),
        user,
    )


def _filtered_reports(request):
    start, end = _date_range(request)
    qs = _report_queryset(request.user).filter(report_date__range=(start, end))
    monitor_id = request.GET.get('monitor', '').strip()
    salesman_id = request.GET.get('salesman', '').strip()
    zone_id = request.GET.get('zone', '').strip()

    if monitor_id:
        if _allowed_monitors(request.user).filter(pk=monitor_id).exists():
            qs = qs.filter(monitor_id=monitor_id)
        else:
            qs = qs.none()
    if salesman_id:
        qs = qs.filter(salesman_id=salesman_id)
    if zone_id:
        qs = qs.filter(zone_id=zone_id)
    return qs, start, end, monitor_id, salesman_id, zone_id


def _visit_formset(request, report):
    return MonitorVisitFormSet(
        request.POST or None,
        instance=report,
        prefix='visits',
        form_kwargs={'user': request.user},
    )


def _validate_visit_salesman(formset, salesman):
    valid = True
    for form in formset.forms:
        cleaned = getattr(form, 'cleaned_data', None)
        if not cleaned or cleaned.get('DELETE'):
            continue
        customer = cleaned.get('customer')
        if customer and customer.assigned_salesman_id != salesman.id:
            form.add_error(
                'customer',
                'Select a customer assigned to the salesman being monitored.',
            )
            valid = False
    return valid


@login_required
def monitoring_list(request):
    if not can_view_monitoring(request.user):
        raise PermissionDenied

    qs, start, end, monitor_id, salesman_id, zone_id = _filtered_reports(request)
    qs = qs.annotate(
        shop_count=Count('visits', distinct=True),
        chiller_count=Count(
            'visits',
            filter=Q(visits__has_company_chiller=True),
            distinct=True,
        ),
        follow_up_count=Count(
            'visits',
            filter=Q(visits__follow_up_required=True),
            distinct=True,
        ),
    )

    totals = qs.aggregate(
        reports=Count('id', distinct=True),
        shops=Count('visits', distinct=True),
        chillers=Count(
            'visits',
            filter=Q(visits__has_company_chiller=True),
            distinct=True,
        ),
        follow_ups=Count(
            'visits',
            filter=Q(visits__follow_up_required=True),
            distinct=True,
        ),
    )
    totals['salesmen'] = qs.values('salesman_id').distinct().count()

    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    monitors = _allowed_monitors(request.user)
    salesmen = _allowed_salesmen(request.user)
    zones = Zone.objects.filter(
        pk__in=monitors.values('zone_id'),
        is_active=True,
    ).distinct()

    return render(
        request,
        'core/monitoring_list.html',
        {
            'reports': page,
            'page_obj': page,
            'totals': totals,
            'start': start,
            'end': end,
            'monitors': monitors,
            'salesmen': salesmen,
            'zones': zones,
            'monitor_id': monitor_id,
            'salesman_id': salesman_id,
            'zone_id': zone_id,
            'show_monitor_filter': not is_monitor(request.user),
        },
    )


@login_required
def monitoring_create(request):
    if not can_view_monitoring(request.user):
        raise PermissionDenied

    report = MonitorReport()
    form = MonitorReportForm(request.POST or None, instance=report, user=request.user)
    formset = _visit_formset(request, report)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        obj = form.save(commit=False)
        if is_monitor(request.user):
            obj.monitor = request.user

        if not obj.monitor.zone_id:
            form.add_error('monitor', 'The monitor must have an assigned zone.')
        else:
            obj.zone = obj.monitor.zone

        if not form.errors and _validate_visit_salesman(formset, obj.salesman):
            with transaction.atomic():
                obj.full_clean()
                obj.save()
                formset.instance = obj
                visits = formset.save(commit=False)
                for deleted in formset.deleted_objects:
                    deleted.delete()
                for visit in visits:
                    visit.report = obj
                    visit.full_clean()
                    visit.save()

                audit(
                    request,
                    'MONITOR_REPORT_CREATED',
                    obj,
                    new={
                        'date': obj.report_date.isoformat(),
                        'monitor_id': obj.monitor_id,
                        'salesman_id': obj.salesman_id,
                        'shops_visited': obj.visits.count(),
                    },
                )
            messages.success(request, 'Monitoring report saved.')
            return redirect('monitoring_detail', pk=obj.pk)

    return render(
        request,
        'core/monitoring_form.html',
        {'form': form, 'formset': formset, 'title': 'New Monitoring Report'},
    )


@login_required
def monitoring_detail(request, pk):
    if not can_view_monitoring(request.user):
        raise PermissionDenied

    obj = get_object_or_404(_report_queryset(request.user), pk=pk)
    visits = obj.visits.select_related('customer').all()

    return render(
        request,
        'core/monitoring_detail.html',
        {
            'report': obj,
            'visits': visits,
            'can_edit': can_edit_monitor_report(request.user, obj),
        },
    )


@login_required
def monitoring_edit(request, pk):
    if not can_view_monitoring(request.user):
        raise PermissionDenied

    obj = get_object_or_404(_report_queryset(request.user), pk=pk)
    if not can_edit_monitor_report(request.user, obj):
        raise PermissionDenied

    form = MonitorReportForm(request.POST or None, instance=obj, user=request.user)
    formset = _visit_formset(request, obj)

    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        updated = form.save(commit=False)
        if is_monitor(request.user):
            updated.monitor = request.user

        if not updated.monitor.zone_id:
            form.add_error('monitor', 'The monitor must have an assigned zone.')
        else:
            updated.zone = updated.monitor.zone

        if not form.errors and _validate_visit_salesman(formset, updated.salesman):
            with transaction.atomic():
                updated.full_clean()
                updated.save()
                formset.instance = updated
                visits = formset.save(commit=False)
                for deleted in formset.deleted_objects:
                    deleted.delete()
                for visit in visits:
                    visit.report = updated
                    visit.full_clean()
                    visit.save()

                audit(
                    request,
                    'MONITOR_REPORT_UPDATED',
                    updated,
                    new={
                        'date': updated.report_date.isoformat(),
                        'monitor_id': updated.monitor_id,
                        'salesman_id': updated.salesman_id,
                        'shops_visited': updated.visits.count(),
                    },
                )
            messages.success(request, 'Monitoring report updated.')
            return redirect('monitoring_detail', pk=updated.pk)

    return render(
        request,
        'core/monitoring_form.html',
        {'form': form, 'formset': formset, 'title': 'Edit Monitoring Report'},
    )


@login_required
def monitoring_csv(request):
    if not can_view_monitoring(request.user):
        raise PermissionDenied

    qs, start, end, _, _, _ = _filtered_reports(request)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="mms-monitoring-{start}-to-{end}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Monitor',
        'Manager',
        'Zone',
        'Salesman',
        'Shop',
        'Customer Code',
        'Company Chiller',
        'Customer Comment',
        'Shopkeeper Comment',
        'Observations',
        'Follow-up Required',
    ])

    for report in qs:
        for visit in report.visits.select_related('customer'):
            writer.writerow([
                report.report_date,
                report.monitor.display_name,
                report.monitor.manager.display_name if report.monitor.manager else '',
                report.zone.code,
                report.salesman.display_name,
                visit.display_shop,
                visit.customer.customer_code if visit.customer else '',
                'Yes' if visit.has_company_chiller else 'No',
                visit.customer_comment,
                visit.shopkeeper_comment,
                visit.observations,
                'Yes' if visit.follow_up_required else 'No',
            ])

    audit(request, 'MONITORING_CSV_EXPORTED', description=f'{start} to {end}')
    return response
