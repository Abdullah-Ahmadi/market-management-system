from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import AuditLog, Sale, SaleItem, SystemSetting
from .permissions import can_override_price


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')) or None


def audit(request, action, obj=None, description='', old=None, new=None):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        entity_type=obj.__class__.__name__ if obj else '',
        entity_id=str(getattr(obj, 'pk', '')) if obj else '',
        description=description,
        old_value=old,
        new_value=new,
        ip_address=client_ip(request),
    )


def sale_snapshot(sale):
    return {
        'sale_number': sale.sale_number,
        'dispatch_serial': sale.dispatch_serial,
        'status': sale.status,
        'customer_id': sale.customer_id,
        'sale_type': sale.sale_type,
        'total_amount': str(sale.total_amount),
        'notes': sale.notes,
        'items': [
            {
                'product_id': i.product_id,
                'quantity': str(i.quantity),
                'unit_price': str(i.unit_price),
                'discount': str(i.discount),
                'line_total': str(i.line_total),
            }
            for i in sale.items.all()
        ],
    }


@transaction.atomic
def save_sale(*, sale, sale_form, item_formset, user):
    sale = sale_form.save(commit=False)
    if not sale.pk:
        sale.salesman = sale.salesman or user
        sale.created_by = user
    sale.updated_by = user
    sale.full_clean()
    sale.save()

    items = item_formset.save(commit=False)
    for deleted in item_formset.deleted_objects:
        deleted.delete()

    settings = SystemSetting.get_solo()
    for item in items:
        item.sale = sale
        # Defense in depth: never trust a browser-posted unit price from a salesman.
        if not can_override_price(user):
            old = None
            if item.pk:
                old = SaleItem.objects.filter(pk=item.pk).values('product_id', 'unit_price').first()
            if old and old['product_id'] == item.product_id:
                item.unit_price = old['unit_price']
            else:
                item.unit_price = item.product.standard_price(sale.sale_type)
            if not settings.allow_salesman_discounts:
                item.discount = Decimal('0')
        item.full_clean()
        item.save()

    total = sale.items.aggregate(v=Sum('line_total'))['v'] or Decimal('0')
    sale.total_amount = total
    sale.save(update_fields=['total_amount', 'updated_by', 'updated_at'])
    return sale


def update_expired_statuses(qs):
    """Bulk-lock submitted sales whose salesman correction day has closed."""
    now = timezone.now()
    local_now = timezone.localtime(now)
    setting = SystemSetting.get_solo()
    past = qs.filter(status=Sale.SUBMITTED, transaction_time__date__lt=local_now.date())
    past.update(status=Sale.LOCKED, locked_at=now)
    if local_now.time() >= setting.salesman_edit_cutoff:
        qs.filter(status=Sale.SUBMITTED, transaction_time__date=local_now.date()).update(
            status=Sale.LOCKED, locked_at=now
        )
