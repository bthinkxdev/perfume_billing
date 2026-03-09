from django.utils import timezone

from .configuration import get_current_timezone


class SystemTimezoneMiddleware:
    """
    Activate timezone per request based on configurable system setting.
    Falls back to Django's default timezone if configuration is missing/invalid.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = get_current_timezone()
        timezone.activate(tz)
        response = self.get_response(request)
        timezone.deactivate()
        return response

