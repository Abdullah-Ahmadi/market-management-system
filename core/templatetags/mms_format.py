from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


def _clean(value, max_decimals=2):
    try:
        d = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    text = f'{d:,.{max_decimals}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text


@register.filter
def number(value):
    return _clean(value, 2)


@register.filter
def quantity(value):
    return _clean(value, 2)


@register.filter
def money(value):
    return _clean(value, 2)
