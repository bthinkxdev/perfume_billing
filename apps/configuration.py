from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings as django_settings
from django.utils import timezone

from .models import get_config


def format_currency(amount):
    config = get_config()
    symbol = config.currency_symbol
    position = config.currency_position
    value = f"{Decimal(amount):.2f}"
    return f"{symbol}{value}" if position == "before" else f"{value}{symbol}"


def get_current_timezone():
    config = get_config()
    try:
        return ZoneInfo(config.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(django_settings.TIME_ZONE)


def parse_decimal(value, field_name):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid decimal value for {field_name}.") from exc
