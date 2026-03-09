from decimal import Decimal, InvalidOperation

from django import template
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

from ..configuration import format_currency
from ..models import get_config

register = template.Library()


@register.filter(name="currency")
def currency(value):
    """Format a numeric value using configured currency settings."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return format_currency(amount)


@register.filter(name="app_date")
def app_date(value, fmt=None):
    """Format dates using the configured global date format."""
    import datetime
    if not value:
        return ""
    config = get_config()
    format_str = fmt or config.date_format
    
    # If value is a date object (not datetime), use date-only format
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        # Strip time-related specifiers for date objects
        format_str = format_str.split()[0] if ' ' in format_str else format_str
        # Remove common time patterns
        for time_part in ['h:i A', 'H:i:s', 'h:i', 'H:i', 'g:i A', 'g:i a']:
            format_str = format_str.replace(time_part, '').strip()
        localized = value
    else:
        try:
            localized = timezone.localtime(value)
        except Exception:
            localized = value
    
    return date_filter(localized, format_str)


@register.filter(name="get_item")
def get_item(dictionary, key):
    """Safe dict lookup in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

