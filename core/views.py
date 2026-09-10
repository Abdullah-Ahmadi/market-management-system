import csv
from datetime import date, timedelta
from pathlib import Path
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .backup import build_backup_bytes, restore_backup, save_safety_backup
from .excel import build_xlsx
from .forms import (
    BackupRestoreForm,
    CustomerForm,
    ProductForm,
    RoleForm,
    SaleForm,
    SaleItemFormSet,
    SelfProfileForm,
    SettingsForm,
    UserCreateForm,
    UserEditForm,
    VoidSaleForm,
    ZoneForm,
)
from .models import AuditLog, Customer, Product, Role, Sale, SaleItem, SystemSetting, User, Zone
from .permissions import (
    can_backup,
    can_edit_sale,
    can_export,
    can_manage_market,
    can_manage_settings,
    can_manage_users,
    can_override_price,
    can_view_audit,
    is_admin,
    is_management,
    is_supervisor,
    visible_customers,
    visible_sales,
)
from .services import audit, sale_snapshot, save_sale, update_expired_statuses
from .validators import password_similar_to_username


def _paginate(request, qs, per_page=None):
    per_page = per_page or SystemSetting.get_solo().default_page_size
    return Paginator(qs, per_page).get_page(request.GET.get('page'))


def _page_range(request):
    settings = SystemSetting.get_solo()
    today = timezone.localdate()
    start = request.GET.get('start')
    end = request.GET.get('end')
    default_start = today - timedelta(days=max(0, settings.default_report_range_days - 1))
    try:
        start = date.fromisoformat(start) if start else default_start
    except ValueError:
        start = default_start
    try:
        end = date.fromisoformat(end) if end else today
    except ValueError:
        end = today
    if start > end:
        start, end = end, start
    return start, end


def _allowed_salesmen(user):
    qs = User.objects.filter(role__code=Role.SALESMAN, is_active=True).select_related('zone', 'supervisor')
    if is_supervisor(user):
        return qs.filter(supervisor=user)
    if not is_management(user):
        return qs.filter(pk=user.pk)
    return qs


def _selected_customer(request, form, sale=None):
    pk = request.POST.get('customer') if request.method == 'POST' else None
    if not pk and sale and sale.customer_id:
        pk = sale.customer_id
    if not pk:
        return None
    try:
        return visible_customers(Customer.objects.select_related('zone', 'assigned_salesman'), request.user).get(pk=pk)
    except (Customer.DoesNotExist, ValueError, TypeError):
        return None


def _report_qs(request):
    start, end = _page_range(request)
    qs = visible_sales(
        Sale.objects.exclude(status=Sale.VOIDED).select_related('salesman', 'customer', 'salesman__zone'),
        request.user,
    ).filter(transaction_time__date__range=(start, end))
    salesman_id = request.GET.get('salesman', '').strip()
    zone_id = request.GET.get('zone', '').strip()
    sale_type = request.GET.get('sale_type', '').strip()
    if salesman_id:
        qs = qs.filter(salesman_id=salesman_id)
    if zone_id:
        qs = qs.filter(salesman__zone_id=zone_id)
    if sale_type in {Sale.CUSTOMER, Sale.GENERAL}:
        qs = qs.filter(sale_type=sale_type)
    return qs, start, end, salesman_id, zone_id, sale_type


def _report_data(qs):
    totals = qs.aggregate(
        cash=Sum('total_amount'),
        transactions=Count('id'),
        average_cash=Avg('total_amount'),
        registered_customers=Count('customer', distinct=True),
    )
    totals = {k: (v or 0) for k, v in totals.items()}
    item_qs = SaleItem.objects.filter(sale__in=qs)
    total_cases = item_qs.aggregate(v=Sum('quantity'))['v'] or Decimal('0')
    totals['cases'] = total_cases
    totals['average_cases'] = (
        total_cases / totals['transactions'] if totals['transactions'] else Decimal('0')
    )

    salesman_sales = list(
        qs.values(
            'salesman__id', 'salesman__first_name', 'salesman__last_name', 'salesman__username'
        )
        .annotate(cash=Sum('total_amount'), transactions=Count('id'))
    )
    salesman_cases = {
        row['sale__salesman__id']: row['cases'] or 0
        for row in item_qs.values('sale__salesman__id').annotate(cases=Sum('quantity'))
    }
    for row in salesman_sales:
        row['cases'] = salesman_cases.get(row['salesman__id'], 0)
    by_salesman = sorted(salesman_sales, key=lambda r: (r['cases'] or 0, r['cash'] or 0), reverse=True)

    type_sales = list(
        qs.values('sale_type').annotate(cash=Sum('total_amount'), transactions=Count('id'))
    )
    type_cases = {
        row['sale__sale_type']: row['cases'] or 0
        for row in item_qs.values('sale__sale_type').annotate(cases=Sum('quantity'))
    }
    for row in type_sales:
        row['cases'] = type_cases.get(row['sale_type'], 0)
    by_type = sorted(type_sales, key=lambda r: r['cash'] or 0, reverse=True)

    by_product = list(
        item_qs.values('product__id', 'product__product_code', 'product__name', 'product__size')
        .annotate(cases=Sum('quantity'), cash=Sum('line_total'))
        .order_by('-cases', '-cash')
    )

    customer_sales = list(
        qs.filter(customer__isnull=False)
        .values('customer__id', 'customer__customer_code', 'customer__full_name')
        .annotate(cash=Sum('total_amount'), transactions=Count('id'))
    )
    customer_cases = {
        row['sale__customer__id']: row['cases'] or 0
        for row in item_qs.filter(sale__customer__isnull=False)
        .values('sale__customer__id')
        .annotate(cases=Sum('quantity'))
    }
    for row in customer_sales:
        row['cases'] = customer_cases.get(row['customer__id'], 0)
    by_customer = sorted(customer_sales, key=lambda r: (r['cases'] or 0, r['cash'] or 0), reverse=True)

    zone_sales = list(
        qs.values('salesman__zone__id', 'salesman__zone__code', 'salesman__zone__name')
        .annotate(cash=Sum('total_amount'), transactions=Count('id'))
    )
    zone_cases = {
        row['sale__salesman__zone__id']: row['cases'] or 0
        for row in item_qs.values('sale__salesman__zone__id').annotate(cases=Sum('quantity'))
    }
    for row in zone_sales:
        row['cases'] = zone_cases.get(row['salesman__zone__id'], 0)
    by_zone = sorted(zone_sales, key=lambda r: (r['cases'] or 0, r['cash'] or 0), reverse=True)

    daily_sales = list(
        qs.annotate(day=TruncDate('transaction_time'))
        .values('day')
        .annotate(cash=Sum('total_amount'), transactions=Count('id'))
        .order_by('day')
    )
    daily_cases = {
        row['day']: row['cases'] or 0
        for row in item_qs.annotate(day=TruncDate('sale__transaction_time'))
        .values('day')
        .annotate(cases=Sum('quantity'))
    }
    for row in daily_sales:
        row['cases'] = daily_cases.get(row['day'], 0)
    daily = daily_sales

    registered_cash = sum(Decimal(str(r['cash'] or 0)) for r in by_type if r['sale_type'] == Sale.CUSTOMER)
    general_cash = sum(Decimal(str(r['cash'] or 0)) for r in by_type if r['sale_type'] == Sale.GENERAL)
    registered_cases = sum(Decimal(str(r['cases'] or 0)) for r in by_type if r['sale_type'] == Sale.CUSTOMER)
    general_cases = sum(Decimal(str(r['cases'] or 0)) for r in by_type if r['sale_type'] == Sale.GENERAL)

    cash_salesmen = sorted(by_salesman, key=lambda r: r['cash'] or 0, reverse=True)
    cash_products = sorted(by_product, key=lambda r: r['cash'] or 0, reverse=True)
    cash_zones = sorted(by_zone, key=lambda r: r['cash'] or 0, reverse=True)
    return {
        'total': totals,
        'by_salesman': by_salesman,
        'by_type': by_type,
        'by_product': by_product,
        'by_customer': by_customer,
        'by_zone': by_zone,
        'daily': daily,
        'registered_sales_cash': registered_cash,
        'general_sales_cash': general_cash,
        'registered_sales_cases': registered_cases,
        'general_sales_cases': general_cases,
        'top_product_cases': by_product[0] if by_product else None,
        'top_product_cash': cash_products[0] if cash_products else None,
        'top_salesman_cases': by_salesman[0] if by_salesman else None,
        'top_salesman_cash': cash_salesmen[0] if cash_salesmen else None,
        'top_zone_cases': by_zone[0] if by_zone else None,
        'top_zone_cash': cash_zones[0] if cash_zones else None,
    }


def _daily_sales_matrix_rows(qs, start, end, user, salesman_id='', zone_id=''):
    """Build the operational daily salesman-by-product matrix used by management Excel exports."""
    settings = SystemSetting.get_solo()
    products = list(
        Product.objects.filter(Q(is_active=True) | Q(sale_items__sale__in=qs))
        .distinct()
        .order_by('product_code')
    )
    product_ids = [p.id for p in products]

    salesmen = _allowed_salesmen(user)
    if salesman_id:
        salesmen = salesmen.filter(pk=salesman_id)
    if zone_id:
        salesmen = salesmen.filter(zone_id=zone_id)
    salesmen = list(salesmen.select_related('zone', 'zone__supervisor', 'supervisor'))
    salesmen.sort(key=lambda u: ((u.zone.serial_number if u.zone else 999), u.display_name.lower()))

    dates = list(
        qs.annotate(report_day=TruncDate('transaction_time'))
        .values_list('report_day', flat=True)
        .distinct()
        .order_by('report_day')
    )
    if start == end and start not in dates:
        dates = [start]

    item_totals = {}
    for row in (
        SaleItem.objects.filter(sale__in=qs)
        .annotate(report_day=TruncDate('sale__transaction_time'))
        .values('report_day', 'sale__salesman_id', 'product_id')
        .annotate(cases=Sum('quantity'))
    ):
        item_totals[(row['report_day'], row['sale__salesman_id'], row['product_id'])] = row['cases'] or Decimal('0')

    sale_totals = {}
    for row in (
        qs.annotate(report_day=TruncDate('transaction_time'))
        .values('report_day', 'salesman_id')
        .annotate(cash=Sum('total_amount'), transactions=Count('id'))
    ):
        sale_totals[(row['report_day'], row['salesman_id'])] = {
            'cash': row['cash'] or Decimal('0'),
            'transactions': row['transactions'] or 0,
        }

    headers = [
        'Date', 'Disp#', 'Zone', 'Supervisor Name', 'Salesman',
        *[f'{p.name} {p.size}'.strip() for p in products],
        'Total Cases', f'Total Cash ({settings.currency})', 'Transactions',
    ]
    rows = [headers]
    product_grand = {pid: Decimal('0') for pid in product_ids}
    grand_cases = Decimal('0')
    grand_cash = Decimal('0')
    grand_transactions = 0

    for day in dates:
        for salesman in salesmen:
            if not salesman.zone_id or not salesman.zone:
                continue
            quantities = [item_totals.get((day, salesman.id, pid), Decimal('0')) for pid in product_ids]
            totals = sale_totals.get((day, salesman.id), {'cash': Decimal('0'), 'transactions': 0})
            row_cases = sum(quantities, Decimal('0'))
            # For a one-day operational report, include every permitted salesman as the reference PDF does.
            # Across longer ranges, suppress entirely empty rows so the workbook stays practical.
            if start != end and not row_cases and not totals['cash'] and not totals['transactions']:
                continue
            supervisor = salesman.zone.supervisor or salesman.supervisor
            rows.append([
                day.isoformat(),
                salesman.zone.daily_serial(day),
                salesman.zone.code,
                supervisor.display_name if supervisor else '',
                salesman.display_name,
                *quantities,
                row_cases,
                totals['cash'],
                totals['transactions'],
            ])
            for pid, qty in zip(product_ids, quantities):
                product_grand[pid] += qty
            grand_cases += row_cases
            grand_cash += Decimal(str(totals['cash'] or 0))
            grand_transactions += totals['transactions']

    rows.append([
        '', '', '', '', 'GRAND TOTAL',
        *[product_grand[pid] for pid in product_ids],
        grand_cases, grand_cash, grand_transactions,
    ])
    return rows


@login_required
def dashboard(request):
    qs = visible_sales(
        Sale.objects.select_related('salesman', 'customer', 'salesman__zone').prefetch_related('items__product'),
        request.user,
    )
    update_expired_statuses(qs)
    today = timezone.localdate()
    today_qs = qs.filter(transaction_time__date=today).exclude(status=Sale.VOIDED)
    month_qs = qs.filter(transaction_time__year=today.year, transaction_time__month=today.month).exclude(
        status=Sale.VOIDED
    )
    settings = SystemSetting.get_solo()
    trend_start = today - timedelta(days=settings.dashboard_trend_days - 1)
    trend_qs = qs.filter(transaction_time__date__range=(trend_start, today)).exclude(status=Sale.VOIDED)

    daily_cash = list(
        trend_qs.annotate(day=TruncDate('transaction_time'))
        .values('day')
        .annotate(value=Sum('total_amount'))
        .order_by('day')
    )
    daily_cases = list(
        SaleItem.objects.filter(sale__in=trend_qs)
        .annotate(day=TruncDate('sale__transaction_time'))
        .values('day')
        .annotate(value=Sum('quantity'))
        .order_by('day')
    )
    product_rows = list(
        SaleItem.objects.filter(sale__in=trend_qs)
        .values('product__name', 'product__size')
        .annotate(cases=Sum('quantity'), cash=Sum('line_total'))
    )
    products_cases = sorted(product_rows, key=lambda r: r['cases'] or 0, reverse=True)[:5]
    products_cash = sorted(product_rows, key=lambda r: r['cash'] or 0, reverse=True)[:5]

    cash_map = {r['day']: float(r['value'] or 0) for r in daily_cash}
    cases_map = {r['day']: float(r['value'] or 0) for r in daily_cases}
    labels = []
    cash_values = []
    case_values = []
    for i in range(settings.dashboard_trend_days):
        d = trend_start + timedelta(days=i)
        labels.append(d.strftime('%d %b'))
        cash_values.append(cash_map.get(d, 0))
        case_values.append(cases_map.get(d, 0))

    chart_data = {
        'cases': {
            'trend': {'labels': labels, 'values': case_values},
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in products_cases],
                'values': [float(r['cases'] or 0) for r in products_cases],
            },
        },
        'cash': {
            'trend': {'labels': labels, 'values': cash_values},
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in products_cash],
                'values': [float(r['cash'] or 0) for r in products_cash],
            },
        },
    }
    today_cases = SaleItem.objects.filter(sale__in=today_qs).aggregate(v=Sum('quantity'))['v'] or 0
    month_cases = SaleItem.objects.filter(sale__in=month_qs).aggregate(v=Sum('quantity'))['v'] or 0
    recent_sales = qs.annotate(case_count=Sum('items__quantity'))[:8]
    ctx = {
        'today_total': today_qs.aggregate(v=Sum('total_amount'))['v'] or 0,
        'today_cases': today_cases,
        'today_count': today_qs.count(),
        'month_total': month_qs.aggregate(v=Sum('total_amount'))['v'] or 0,
        'month_cases': month_cases,
        'customer_count': visible_customers(Customer.objects.filter(is_active=True), request.user).count(),
        'recent_sales': recent_sales,
        'team_count': request.user.subordinates.filter(is_active=True).count()
        if is_supervisor(request.user)
        else None,
        'chart_data': chart_data,
    }
    return render(request, 'core/dashboard.html', ctx)


@login_required
def customer_list(request):
    qs = visible_customers(
        Customer.objects.select_related('zone', 'assigned_salesman'), request.user
    )
    q = request.GET.get('q', '').strip()
    zone = request.GET.get('zone', '').strip()
    if q:
        qs = qs.filter(
            Q(customer_code__icontains=q)
            | Q(full_name__icontains=q)
            | Q(phone_number__icontains=q)
            | Q(address__icontains=q)
        )
    if zone:
        qs = qs.filter(zone_id=zone)
    page = _paginate(request, qs)
    zones = Zone.objects.filter(customers__in=visible_customers(Customer.objects.all(), request.user)).distinct()
    return render(
        request,
        'core/customer_list.html',
        {'customers': page, 'page_obj': page, 'q': q, 'zone_id': zone, 'zones': zones},
    )


@login_required
def customer_create(request):
    initial = {}
    if not is_management(request.user) and not is_supervisor(request.user):
        initial = {'zone': request.user.zone, 'assigned_salesman': request.user}
    form = CustomerForm(request.POST or None, user=request.user, initial=initial)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        if not is_management(request.user) and not is_supervisor(request.user):
            obj.assigned_salesman = request.user
            obj.zone = request.user.zone
        obj.full_clean()
        obj.save()
        audit(
            request,
            'CUSTOMER_CREATED',
            obj,
            new={'customer_code': obj.customer_code, 'name': obj.full_name},
        )
        messages.success(request, f'Customer {obj.customer_code} created.')
        return redirect('customer_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': 'Create Customer', 'submit_label': 'Create customer'},
    )


@login_required
def customer_detail(request, pk):
    obj = get_object_or_404(
        visible_customers(Customer.objects.select_related('zone', 'assigned_salesman'), request.user),
        pk=pk,
    )
    sales_qs = visible_sales(obj.sales.select_related('salesman'), request.user).exclude(status=Sale.VOIDED)
    summary = sales_qs.aggregate(total=Sum('total_amount'), transactions=Count('id'), average=Avg('total_amount'))
    return render(
        request,
        'core/customer_detail.html',
        {'customer': obj, 'sales': sales_qs[:20], 'summary': summary},
    )


@login_required
def customer_edit(request, pk):
    obj = get_object_or_404(visible_customers(Customer.objects.all(), request.user), pk=pk)
    form = CustomerForm(request.POST or None, instance=obj, user=request.user)
    if form.is_valid():
        old = {'name': obj.full_name, 'phone': obj.phone_number, 'address': obj.address}
        obj = form.save()
        audit(
            request,
            'CUSTOMER_UPDATED',
            obj,
            old=old,
            new={'name': obj.full_name, 'phone': obj.phone_number, 'address': obj.address},
        )
        messages.success(request, 'Customer updated.')
        return redirect('customer_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': f'Edit {obj.customer_code}', 'submit_label': 'Save changes'},
    )


@login_required
def customer_search_api(request):
    query = request.GET.get('q', '').strip()
    salesman = request.GET.get('salesman', '').strip()
    settings = SystemSetting.get_solo()
    qs = visible_customers(
        Customer.objects.filter(is_active=True).select_related('zone', 'assigned_salesman'), request.user
    )
    if salesman:
        allowed_ids = set(_allowed_salesmen(request.user).values_list('id', flat=True))
        try:
            sid = int(salesman)
        except ValueError:
            sid = 0
        if sid not in allowed_ids:
            return JsonResponse({'results': []})
        qs = qs.filter(assigned_salesman_id=sid)
    if query:
        qs = qs.filter(
            Q(customer_code__icontains=query)
            | Q(full_name__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(address__icontains=query)
        )
    else:
        qs = qs.none()
    data = [
        {
            'id': c.id,
            'code': c.customer_code,
            'name': c.full_name,
            'phone': c.phone_number,
            'address': c.address,
            'zone': c.zone.code,
        }
        for c in qs[: settings.customer_search_limit]
    ]
    return JsonResponse({'results': data})


@login_required
def product_list(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    qs = Product.objects.all()
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(product_code__icontains=q) | Q(size__icontains=q)
        )
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.filter(is_active=False)
    page = _paginate(request, qs)
    return render(
        request,
        'core/product_list.html',
        {'products': page, 'page_obj': page, 'q': q, 'status': status},
    )


@login_required
def product_create(request):
    if not can_manage_market(request.user):
        raise PermissionDenied
    form = ProductForm(request.POST or None)
    if form.is_valid():
        obj = form.save()
        audit(
            request,
            'PRODUCT_CREATED',
            obj,
            new={'code': obj.product_code, 'name': obj.name, 'size': obj.size},
        )
        messages.success(request, f'Product {obj.product_code} created.')
        return redirect('product_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {
            'form': form,
            'title': 'Create Product',
            'submit_label': 'Create product',
            'form_note': 'The product code is generated automatically after you save the product.',
        },
    )


@login_required
def product_detail(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    sales_scope = visible_sales(Sale.objects.exclude(status=Sale.VOIDED), request.user)
    items = SaleItem.objects.filter(product=obj, sale__in=sales_scope).select_related(
        'sale', 'sale__salesman', 'sale__customer'
    )
    summary = items.aggregate(quantity=Sum('quantity'), sales=Sum('line_total'), transactions=Count('sale', distinct=True))
    return render(
        request,
        'core/product_detail.html',
        {'product': obj, 'summary': summary, 'recent_items': items.order_by('-sale__transaction_time')[:20]},
    )


@login_required
def product_edit(request, pk):
    if not can_manage_market(request.user):
        raise PermissionDenied
    obj = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=obj)
    if form.is_valid():
        old = {
            'wholesale_price': str(obj.wholesale_price),
            'retail_price': str(obj.retail_price),
            'size': obj.size,
        }
        obj = form.save()
        audit(
            request,
            'PRODUCT_UPDATED',
            obj,
            old=old,
            new={
                'wholesale_price': str(obj.wholesale_price),
                'retail_price': str(obj.retail_price),
                'size': obj.size,
            },
        )
        messages.success(request, 'Product updated.')
        return redirect('product_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': f'Edit {obj.product_code}', 'submit_label': 'Save changes'},
    )


@login_required
def sale_list(request):
    qs = visible_sales(
        Sale.objects.select_related('salesman', 'customer').prefetch_related('items'), request.user
    )
    update_expired_statuses(qs)
    start, end = _page_range(request)
    qs = qs.filter(transaction_time__date__range=(start, end))
    status = request.GET.get('status', '').strip()
    q = request.GET.get('q', '').strip()
    salesman = request.GET.get('salesman', '').strip()
    if status:
        qs = qs.filter(status=status)
    if salesman:
        qs = qs.filter(salesman_id=salesman)
    if q:
        qs = qs.filter(
            Q(sale_number__icontains=q)
            | Q(customer__customer_code__icontains=q)
            | Q(customer__full_name__icontains=q)
            | Q(salesman__first_name__icontains=q)
            | Q(salesman__last_name__icontains=q)
        )
    page = _paginate(request, qs)
    return render(
        request,
        'core/sale_list.html',
        {
            'sales': page,
            'page_obj': page,
            'start': start,
            'end': end,
            'status': status,
            'q': q,
            'salesman_id': salesman,
            'salesmen': _allowed_salesmen(request.user),
            'statuses': Sale.STATUSES,
        },
    )


def _sale_formset(request, sale, sale_type):
    return SaleItemFormSet(
        request.POST or None,
        instance=sale,
        prefix='items',
        form_kwargs={'user': request.user, 'sale_type': sale_type},
    )


@login_required
def sale_create(request):
    sale = Sale(salesman=request.user, created_by=request.user)
    form = SaleForm(request.POST or None, instance=sale, user=request.user)
    sale_type = request.POST.get('sale_type') or Sale.CUSTOMER
    formset = _sale_formset(request, sale, sale_type)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            obj = save_sale(sale=sale, sale_form=form, item_formset=formset, user=request.user)
            audit(request, 'SALE_CREATED', obj, new=sale_snapshot(obj))
        messages.success(request, f'{obj.sale_number} recorded successfully.')
        return redirect('sale_detail', pk=obj.pk)
    selected_customer = _selected_customer(request, form, sale)
    return render(
        request,
        'core/sale_form.html',
        {
            'form': form,
            'formset': formset,
            'title': 'Record Sale',
            'selected_customer': selected_customer,
            'can_override_price': can_override_price(request.user),
        },
    )


@login_required
def sale_detail(request, pk):
    obj = get_object_or_404(
        visible_sales(
            Sale.objects.select_related('salesman', 'customer').prefetch_related('items__product'),
            request.user,
        ),
        pk=pk,
    )
    update_expired_statuses(Sale.objects.filter(pk=obj.pk))
    obj.refresh_from_db()
    return render(
        request,
        'core/sale_detail.html',
        {'sale': obj, 'can_edit': can_edit_sale(request.user, obj)},
    )


@login_required
def sale_edit(request, pk):
    obj = get_object_or_404(visible_sales(Sale.objects.all(), request.user), pk=pk)
    if not can_edit_sale(request.user, obj):
        raise PermissionDenied('This transaction is outside your permitted correction window.')
    old = sale_snapshot(obj)
    form = SaleForm(request.POST or None, instance=obj, user=request.user)
    sale_type = request.POST.get('sale_type') or obj.sale_type
    formset = _sale_formset(request, obj, sale_type)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            obj = save_sale(sale=obj, sale_form=form, item_formset=formset, user=request.user)
            obj.status = Sale.CORRECTED
            obj.save(update_fields=['status', 'updated_at'])
            audit(request, 'SALE_CORRECTED', obj, old=old, new=sale_snapshot(obj))
        messages.success(request, 'Sale corrected and audit history recorded.')
        return redirect('sale_detail', pk=obj.pk)
    return render(
        request,
        'core/sale_form.html',
        {
            'form': form,
            'formset': formset,
            'title': f'Correct {obj.sale_number}',
            'editing': True,
            'selected_customer': _selected_customer(request, form, obj),
            'can_override_price': can_override_price(request.user),
        },
    )


@login_required
def sale_void(request, pk):
    obj = get_object_or_404(visible_sales(Sale.objects.all(), request.user), pk=pk)
    if not can_edit_sale(request.user, obj):
        raise PermissionDenied
    form = VoidSaleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        old = sale_snapshot(obj)
        obj.status = Sale.VOIDED
        obj.void_reason = form.cleaned_data['reason']
        obj.updated_by = request.user
        obj.save(update_fields=['status', 'void_reason', 'updated_by', 'updated_at'])
        audit(
            request,
            'SALE_VOIDED',
            obj,
            description=obj.void_reason,
            old=old,
            new=sale_snapshot(obj),
        )
        messages.success(request, 'Sale voided; original record remains available for audit.')
        return redirect('sale_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': f'Void {obj.sale_number}', 'submit_label': 'Void sale', 'danger': True},
    )


@login_required
def product_price_api(request, pk):
    p = get_object_or_404(Product, pk=pk, is_active=True)
    sale_type = request.GET.get('sale_type', Sale.CUSTOMER)
    if sale_type not in {Sale.CUSTOMER, Sale.GENERAL}:
        sale_type = Sale.CUSTOMER
    return JsonResponse(
        {
            'id': p.pk,
            'wholesale_price': str(p.wholesale_price),
            'retail_price': str(p.retail_price),
            'price': str(p.standard_price(sale_type)),
            'unit': p.unit,
            'size': p.size,
            'price_locked': not can_override_price(request.user),
        }
    )


@login_required
def reports(request):
    qs, start, end, salesman_id, zone_id, sale_type = _report_qs(request)
    data = _report_data(qs)

    cash_salesmen = sorted(data['by_salesman'], key=lambda r: r['cash'] or 0, reverse=True)[:10]
    case_salesmen = sorted(data['by_salesman'], key=lambda r: r['cases'] or 0, reverse=True)[:10]
    cash_products = sorted(data['by_product'], key=lambda r: r['cash'] or 0, reverse=True)[:10]
    case_products = sorted(data['by_product'], key=lambda r: r['cases'] or 0, reverse=True)[:10]
    cash_zones = sorted(data['by_zone'], key=lambda r: r['cash'] or 0, reverse=True)
    case_zones = sorted(data['by_zone'], key=lambda r: r['cases'] or 0, reverse=True)

    salesman_label = lambda r: (
        f"{r['salesman__first_name']} {r['salesman__last_name']}".strip() or r['salesman__username']
    )
    type_labels = [
        'Registered customer' if r['sale_type'] == Sale.CUSTOMER else 'General / Walk-in'
        for r in data['by_type']
    ]
    chart_data = {
        'cases': {
            'daily': {
                'labels': [r['day'].strftime('%d %b') for r in data['daily']],
                'values': [float(r['cases'] or 0) for r in data['daily']],
            },
            'salesmen': {
                'labels': [salesman_label(r) for r in case_salesmen],
                'values': [float(r['cases'] or 0) for r in case_salesmen],
            },
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in case_products],
                'values': [float(r['cases'] or 0) for r in case_products],
            },
            'types': {
                'labels': type_labels,
                'values': [float(r['cases'] or 0) for r in data['by_type']],
            },
            'zones': {
                'labels': [r['salesman__zone__code'] or 'No zone' for r in case_zones],
                'values': [float(r['cases'] or 0) for r in case_zones],
            },
        },
        'cash': {
            'daily': {
                'labels': [r['day'].strftime('%d %b') for r in data['daily']],
                'values': [float(r['cash'] or 0) for r in data['daily']],
            },
            'salesmen': {
                'labels': [salesman_label(r) for r in cash_salesmen],
                'values': [float(r['cash'] or 0) for r in cash_salesmen],
            },
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in cash_products],
                'values': [float(r['cash'] or 0) for r in cash_products],
            },
            'types': {
                'labels': type_labels,
                'values': [float(r['cash'] or 0) for r in data['by_type']],
            },
            'zones': {
                'labels': [r['salesman__zone__code'] or 'No zone' for r in cash_zones],
                'values': [float(r['cash'] or 0) for r in cash_zones],
            },
        },
    }
    zones = Zone.objects.filter(is_active=True)
    if is_supervisor(request.user):
        zones = zones.filter(supervisor=request.user)
    elif not is_management(request.user):
        zones = zones.filter(pk=request.user.zone_id)
    return render(
        request,
        'core/reports.html',
        {
            **data,
            'start': start,
            'end': end,
            'salesmen': _allowed_salesmen(request.user),
            'salesman_id': salesman_id,
            'zones': zones,
            'zone_id': zone_id,
            'sale_type': sale_type,
            'chart_data': chart_data,
        },
    )


@login_required
def sales_csv(request):
    if not can_export(request.user):
        raise PermissionDenied
    qs, start, end, _, _, _ = _report_qs(request)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="mms-sales-{start}-to-{end}.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ['Sale #', 'Date/time', 'Status', 'Type', 'Salesman', 'Customer Code', 'Customer', 'Total']
    )
    for s in qs:
        writer.writerow(
            [
                s.sale_number,
                timezone.localtime(s.transaction_time).isoformat(sep=' ', timespec='minutes'),
                s.status,
                s.sale_type,
                s.salesman.display_name,
                s.customer.customer_code if s.customer else '',
                s.customer.full_name if s.customer else 'General / Walk-in',
                s.total_amount,
            ]
        )
    audit(request, 'SALES_CSV_EXPORTED', description=f'{start} to {end}')
    return response


@login_required
def sales_excel(request):
    if not can_export(request.user):
        raise PermissionDenied
    qs, start, end, salesman_id, zone_id, _ = _report_qs(request)
    data = _report_data(qs)
    settings = SystemSetting.get_solo()

    def person_name(row):
        return f"{row['salesman__first_name']} {row['salesman__last_name']}".strip() or row['salesman__username']

    top_salesman_cases = data['top_salesman_cases']
    top_salesman_cash = data['top_salesman_cash']
    top_product_cases = data['top_product_cases']
    top_product_cash = data['top_product_cash']
    top_zone_cases = data['top_zone_cases']
    top_zone_cash = data['top_zone_cash']

    analysis_rows = [
        ['MMS SALES ANALYSIS', ''],
        ['Company', settings.company_name],
        ['Period', f'{start} to {end}'],
        ['', ''],
        ['Core KPI', 'Value'],
        ['Total cases sold', data['total']['cases']],
        ['Total sales value', data['total']['cash']],
        ['Transactions', data['total']['transactions']],
        ['Average cases per transaction', data['total']['average_cases']],
        ['Average cash per transaction', data['total']['average_cash']],
        ['Registered customers served', data['total']['registered_customers']],
        ['Registered-customer cases', data['registered_sales_cases']],
        ['Registered-customer cash', data['registered_sales_cash']],
        ['General / walk-in cases', data['general_sales_cases']],
        ['General / walk-in cash', data['general_sales_cash']],
        ['', ''],
        ['Performance highlight', 'Result'],
        ['Top salesman by cases', person_name(top_salesman_cases) if top_salesman_cases else 'No data'],
        ['Top salesman cases', top_salesman_cases['cases'] if top_salesman_cases else 0],
        ['Top salesman by cash', person_name(top_salesman_cash) if top_salesman_cash else 'No data'],
        ['Top salesman cash', top_salesman_cash['cash'] if top_salesman_cash else 0],
        ['Top product by cases', f"{top_product_cases['product__name']} {top_product_cases['product__size']}" if top_product_cases else 'No data'],
        ['Top product cases', top_product_cases['cases'] if top_product_cases else 0],
        ['Top product by cash', f"{top_product_cash['product__name']} {top_product_cash['product__size']}" if top_product_cash else 'No data'],
        ['Top product cash', top_product_cash['cash'] if top_product_cash else 0],
        ['Top zone by cases', top_zone_cases['salesman__zone__code'] if top_zone_cases else 'No data'],
        ['Top zone cases', top_zone_cases['cases'] if top_zone_cases else 0],
        ['Top zone by cash', top_zone_cash['salesman__zone__code'] if top_zone_cash else 'No data'],
        ['Top zone cash', top_zone_cash['cash'] if top_zone_cash else 0],
    ]

    daily_rows = [['Date', 'Transactions', 'Cases', f'Cash ({settings.currency})']]
    for row in data['daily']:
        daily_rows.append([row['day'].isoformat(), row['transactions'], row['cases'], row['cash']])

    salesman_rows = [['Salesman', 'Transactions', 'Cases', f'Cash ({settings.currency})', 'Cases / Transaction', f'Cash / Transaction ({settings.currency})']]
    for r in data['by_salesman']:
        tx = r['transactions'] or 0
        salesman_rows.append([
            person_name(r),
            tx,
            r['cases'],
            r['cash'],
            (r['cases'] / tx) if tx else 0,
            (r['cash'] / tx) if tx else 0,
        ])

    product_rows = [['Product Code', 'Product', 'Size', 'Cases', f'Cash ({settings.currency})', f'Cash / Case ({settings.currency})']]
    for r in data['by_product']:
        cases = r['cases'] or 0
        product_rows.append([
            r['product__product_code'],
            r['product__name'],
            r['product__size'],
            cases,
            r['cash'],
            (r['cash'] / cases) if cases else 0,
        ])

    customer_rows = [['Customer Code', 'Customer', 'Transactions', 'Cases', f'Cash ({settings.currency})']]
    for r in data['by_customer']:
        customer_rows.append([
            r['customer__customer_code'],
            r['customer__full_name'],
            r['transactions'],
            r['cases'],
            r['cash'],
        ])

    zone_rows = [['Zone', 'Zone Name', 'Transactions', 'Cases', f'Cash ({settings.currency})']]
    for r in data['by_zone']:
        zone_rows.append([
            r['salesman__zone__code'] or '',
            r['salesman__zone__name'] or '',
            r['transactions'],
            r['cases'],
            r['cash'],
        ])

    type_rows = [['Sale Type', 'Transactions', 'Cases', f'Cash ({settings.currency})']]
    for r in data['by_type']:
        type_rows.append([
            'Registered customer' if r['sale_type'] == Sale.CUSTOMER else 'General / Walk-in',
            r['transactions'], r['cases'], r['cash'],
        ])

    sale_rows = [[
        'Sale #', 'Dispatch #', 'Date/time', 'Status', 'Type', 'Salesman', 'Zone',
        'Customer Code', 'Customer', 'Cases', f'Cash ({settings.currency})'
    ]]
    sales_for_export = qs.order_by('transaction_time').annotate(export_cases=Sum('items__quantity'))
    for sale in sales_for_export:
        sale_rows.append([
            sale.sale_number,
            sale.dispatch_serial,
            timezone.localtime(sale.transaction_time).strftime('%Y-%m-%d %H:%M'),
            sale.get_status_display(),
            sale.get_sale_type_display(),
            sale.salesman.display_name,
            sale.salesman.zone.code if sale.salesman.zone else '',
            sale.customer.customer_code if sale.customer else '',
            sale.customer.full_name if sale.customer else 'General / Walk-in',
            sale.export_cases or 0,
            sale.total_amount,
        ])

    sheets = [('Analysis', analysis_rows)]
    if is_management(request.user):
        sheets.append((
            'Daily Sales Report',
            _daily_sales_matrix_rows(qs, start, end, request.user, salesman_id, zone_id),
        ))
    sheets.extend([
        ('Daily Trend', daily_rows),
        ('Salesmen', salesman_rows),
        ('Products', product_rows),
        ('Zones', zone_rows),
        ('Customers', customer_rows),
        ('Sale Mix', type_rows),
        ('Transactions', sale_rows),
    ])
    content = build_xlsx(sheets)
    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="mms-analysis-{start}-to-{end}.xlsx"'
    audit(request, 'SALES_EXCEL_EXPORTED', description=f'Analysis {start} to {end}')
    return response


@login_required
def backup_center(request):
    if not can_backup(request.user):
        raise PermissionDenied
    backups_dir = Path(settings.BASE_DIR) / 'backups'
    safety_backups = []
    if backups_dir.exists():
        safety_backups = sorted(
            [p for p in backups_dir.glob('pre-restore-*.mmsbackup') if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
    return render(request, 'core/backup.html', {'safety_backups': safety_backups})


@login_required
def backup_export(request):
    if not can_backup(request.user):
        raise PermissionDenied
    content = build_backup_bytes()
    stamp = timezone.localtime().strftime('%Y-%m-%d-%H%M')
    response = HttpResponse(content, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="mms-{stamp}.mmsbackup"'
    audit(request, 'BACKUP_CREATED', description='Restorable MMS backup package created.')
    return response


@login_required
def backup_restore(request):
    if not can_backup(request.user):
        raise PermissionDenied
    form = BackupRestoreForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        safety_path = None
        try:
            safety_path = save_safety_backup()
            restore_backup(form.cleaned_data['backup_file'])
        except ValueError as exc:
            form.add_error('backup_file', str(exc))
        except Exception:
            form.add_error(
                'backup_file',
                'Restore could not be completed. MMS kept a pre-restore safety backup; check the server logs before trying again.',
            )
        else:
            # The restored snapshot may contain a different user/session state. Force a clean login.
            auth_logout(request)
            return redirect('/accounts/login/?restored=1')
    return render(request, 'core/backup_restore.html', {'form': form})


@login_required
def user_list(request):
    if not can_manage_users(request.user):
        raise PermissionDenied
    q = request.GET.get('q', '').strip()
    role = request.GET.get('role', '').strip()
    qs = User.objects.select_related('role', 'zone', 'supervisor').order_by('first_name', 'username')
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(employee_code__icontains=q)
            | Q(phone_number__icontains=q)
        )
    if role:
        qs = qs.filter(role__code=role)
    page = _paginate(request, qs)
    return render(
        request,
        'core/user_list.html',
        {'users': page, 'page_obj': page, 'q': q, 'role_code': role, 'roles': Role.objects.all()},
    )


@login_required
def user_detail(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    obj = get_object_or_404(User.objects.select_related('role', 'zone', 'supervisor'), pk=pk)
    sales = obj.sales.exclude(status=Sale.VOIDED)
    summary = sales.aggregate(total=Sum('total_amount'), transactions=Count('id'), average=Avg('total_amount'))
    return render(
        request,
        'core/user_detail.html',
        {'employee': obj, 'summary': summary, 'recent_sales': sales[:15]},
    )


@login_required
def user_create(request):
    if not can_manage_users(request.user):
        raise PermissionDenied
    form = UserCreateForm(request.POST or None, request.FILES or None, actor=request.user)
    if form.is_valid():
        obj = form.save()
        audit(request, 'USER_CREATED', obj, new={'username': obj.username, 'role': obj.role_code()})
        messages.success(request, 'User created.')
        if password_similar_to_username(form.cleaned_data.get('password1'), obj.username):
            messages.warning(request, 'The password is similar to the username. It is allowed, but a less predictable password is safer.')
        return redirect('user_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {
            'form': form,
            'title': 'Create User',
            'submit_label': 'Create user',
            'multipart': True,
            'show_password_rules': True,
        },
    )


@login_required
def user_edit(request, pk):
    if not can_manage_users(request.user):
        raise PermissionDenied
    obj = get_object_or_404(User, pk=pk)
    if not is_admin(request.user) and (
        obj == request.user
        or not obj.role
        or not request.user.role
        or obj.role.level >= request.user.role.level
    ):
        raise PermissionDenied
    form = UserEditForm(request.POST or None, request.FILES or None, instance=obj, actor=request.user)
    if form.is_valid():
        form.save()
        audit(request, 'USER_UPDATED', obj)
        messages.success(request, 'User updated.')
        return redirect('user_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': f'Edit {obj.username}', 'submit_label': 'Save changes', 'multipart': True},
    )


@login_required
def settings_view(request):
    if not can_manage_settings(request.user):
        raise PermissionDenied
    obj = SystemSetting.get_solo()
    form = SettingsForm(request.POST or None, request.FILES or None, instance=obj)
    if form.is_valid():
        form.save()
        audit(request, 'SETTINGS_UPDATED', obj)
        messages.success(request, 'System settings updated.')
        return redirect('settings')
    return render(
        request,
        'core/settings.html',
        {'form': form, 'title': 'System Settings', 'submit_label': 'Save settings', 'multipart': True},
    )


@login_required
def audit_list(request):
    if not can_view_audit(request.user):
        raise PermissionDenied
    q = request.GET.get('q', '').strip()
    action = request.GET.get('action', '').strip()
    logs = AuditLog.objects.select_related('user')
    if q:
        logs = logs.filter(
            Q(user__username__icontains=q)
            | Q(description__icontains=q)
            | Q(entity_type__icontains=q)
            | Q(entity_id__icontains=q)
            | Q(ip_address__icontains=q)
        )
    if action:
        logs = logs.filter(action=action)
    actions = AuditLog.objects.order_by('action').values_list('action', flat=True).distinct()
    page = _paginate(request, logs, 100)
    return render(
        request,
        'core/audit_list.html',
        {'logs': page, 'page_obj': page, 'q': q, 'action': action, 'actions': actions},
    )


@login_required
def audit_detail(request, pk):
    if not can_view_audit(request.user):
        raise PermissionDenied
    obj = get_object_or_404(AuditLog.objects.select_related('user'), pk=pk)
    return render(request, 'core/audit_detail.html', {'log': obj})


def _visible_zones(user):
    qs = Zone.objects.select_related('supervisor')
    if is_supervisor(user) and not is_management(user):
        return qs.filter(supervisor=user)
    if not is_management(user):
        return qs.filter(pk=user.zone_id)
    return qs


@login_required
def zone_list(request):
    if not (can_manage_market(request.user) or is_supervisor(request.user)):
        raise PermissionDenied
    q = request.GET.get('q', '').strip()
    qs = _visible_zones(request.user)
    if q:
        qs = qs.filter(
            Q(code__icontains=q)
            | Q(name__icontains=q)
            | Q(supervisor__first_name__icontains=q)
            | Q(supervisor__last_name__icontains=q)
        )
    qs = qs.annotate(
        customer_count=Count('customers', distinct=True),
        salesman_count=Count('employees', filter=Q(employees__role__code=Role.SALESMAN), distinct=True),
    )
    zones = list(qs)
    today = timezone.localdate()
    for zone in zones:
        zone.today_serial = zone.daily_serial(today)
    return render(request, 'core/zone_list.html', {'zones': zones, 'q': q})


@login_required
def zone_detail(request, pk):
    if not (can_manage_market(request.user) or is_supervisor(request.user)):
        raise PermissionDenied
    obj = get_object_or_404(_visible_zones(request.user), pk=pk)
    sales = Sale.objects.filter(salesman__zone=obj).exclude(status=Sale.VOIDED)
    if not is_management(request.user):
        sales = visible_sales(sales, request.user)
    today = timezone.localdate()
    month = sales.filter(transaction_time__year=today.year, transaction_time__month=today.month)
    last_30 = sales.filter(transaction_time__date__gte=today - timedelta(days=29))
    item_qs = SaleItem.objects.filter(sale__in=last_30)
    top_products = list(
        item_qs.values('product__name', 'product__size')
        .annotate(cash=Sum('line_total'), cases=Sum('quantity'))
    )
    top_products_cases = sorted(top_products, key=lambda r: r['cases'] or 0, reverse=True)[:10]
    top_products_cash = sorted(top_products, key=lambda r: r['cash'] or 0, reverse=True)[:10]
    daily_cash = list(
        last_30.annotate(day=TruncDate('transaction_time'))
        .values('day').annotate(value=Sum('total_amount')).order_by('day')
    )
    daily_cases = list(
        item_qs.annotate(day=TruncDate('sale__transaction_time'))
        .values('day').annotate(value=Sum('quantity')).order_by('day')
    )
    cash_map = {r['day']: float(r['value'] or 0) for r in daily_cash}
    cases_map = {r['day']: float(r['value'] or 0) for r in daily_cases}
    day_labels = []
    cash_values = []
    case_values = []
    start_day = today - timedelta(days=29)
    for i in range(30):
        d = start_day + timedelta(days=i)
        day_labels.append(d.strftime('%d %b'))
        cash_values.append(cash_map.get(d, 0))
        case_values.append(cases_map.get(d, 0))
    chart_data = {
        'cases': {
            'daily': {'labels': day_labels, 'values': case_values},
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in top_products_cases],
                'values': [float(r['cases'] or 0) for r in top_products_cases],
            },
        },
        'cash': {
            'daily': {'labels': day_labels, 'values': cash_values},
            'products': {
                'labels': [f"{r['product__size']} · {r['product__name']}" for r in top_products_cash],
                'values': [float(r['cash'] or 0) for r in top_products_cash],
            },
        },
    }
    month_cases = SaleItem.objects.filter(sale__in=month).aggregate(v=Sum('quantity'))['v'] or 0
    recent_sales = sales.select_related('salesman', 'customer').annotate(case_count=Sum('items__quantity'))[:15]
    ctx = {
        'zone': obj,
        'today_serial': obj.daily_serial(today),
        'salesmen': User.objects.filter(zone=obj, role__code=Role.SALESMAN, is_active=True),
        'customers': Customer.objects.filter(zone=obj, is_active=True).count(),
        'month_total': month.aggregate(v=Sum('total_amount'))['v'] or 0,
        'month_cases': month_cases,
        'month_transactions': month.count(),
        'recent_sales': recent_sales,
        'top_products': top_products_cases,
        'chart_data': chart_data,
    }
    return render(request, 'core/zone_detail.html', ctx)


@login_required
def zone_create(request):
    if not can_manage_market(request.user):
        raise PermissionDenied
    form = ZoneForm(request.POST or None)
    if form.is_valid():
        obj = form.save()
        audit(
            request,
            'ZONE_CREATED',
            obj,
            new={'code': obj.code, 'name': obj.name, 'supervisor': obj.supervisor_id},
        )
        messages.success(request, 'Zone created.')
        return redirect('zone_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': 'Create Zone', 'submit_label': 'Create zone'},
    )


@login_required
def zone_edit(request, pk):
    if not can_manage_market(request.user):
        raise PermissionDenied
    obj = get_object_or_404(Zone, pk=pk)
    form = ZoneForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        audit(request, 'ZONE_UPDATED', obj)
        messages.success(request, 'Zone updated.')
        return redirect('zone_detail', pk=obj.pk)
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': f'Edit Zone {obj.code}', 'submit_label': 'Save changes'},
    )


@login_required
def role_list(request):
    if not is_admin(request.user):
        raise PermissionDenied
    return render(request, 'core/role_list.html', {'roles': Role.objects.all().order_by('-level')})


@login_required
def role_edit(request, pk):
    if not is_admin(request.user):
        raise PermissionDenied
    obj = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=obj)
    if form.is_valid():
        form.save()
        audit(request, 'ROLE_UPDATED', obj, new={'code': obj.code, 'name': obj.name})
        messages.success(request, 'Role permissions updated.')
        return redirect('role_list')
    return render(
        request,
        'core/form.html',
        {
            'form': form,
            'title': f'Edit Role: {obj.name}',
            'submit_label': 'Save role permissions',
            'form_note': 'System Administrator core privileges are protected and cannot be reduced.' if obj.code == Role.ADMIN else '',
        },
    )


@login_required
def profile_edit(request):
    form = SelfProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if form.is_valid():
        obj = form.save()
        audit(request, 'PROFILE_UPDATED', obj)
        messages.success(request, 'Your profile was updated.')
        return redirect('profile')
    return render(
        request,
        'core/form.html',
        {'form': form, 'title': 'Edit My Profile', 'submit_label': 'Save profile', 'multipart': True},
    )


@login_required
def profile(request):
    return render(request, 'core/profile.html', {'profile_user': request.user})


class MMSPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = 'registration/password_change.html'
    success_url = '/'

    def form_valid(self, form):
        password = form.cleaned_data.get('new_password1')
        if password_similar_to_username(password, self.request.user.username):
            messages.warning(
                self.request,
                'Your new password is similar to your username. MMS allows it, but using a less predictable password is safer.',
            )
        else:
            messages.success(self.request, 'Password changed successfully.')
        return super().form_valid(form)


@login_required
def help_view(request):
    role = request.user.role_code()
    return render(request, 'core/help.html', {'role_code': role})
