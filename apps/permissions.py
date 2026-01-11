"""
Lightweight role/permission helpers for differentiating admin vs staff users.

We keep the existing admin experience intact and gate a curated set of
operations for the Staff role. Staff membership is determined by belonging to
the "Staff" group (case-insensitive) or having is_staff=True without being a
superuser/Admin group member. Admins (superusers or users in the "Admin"
group) bypass all checks.
"""
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

ADMIN = "ADMIN"
STAFF = "STAFF"
ANON = "ANON"

# Explicit permission matrix for the Staff role. Admins always have access.
STAFF_PERMISSIONS = {
    # Billing
    "billing.create_invoice": True,
    "billing.confirm_invoice": True,
    "billing.view_invoice": True,
    "billing.print_invoice": True,
    "billing.cancel_invoice": False,
    "billing.delete_invoice": False,
    "billing.price_override": True,
    "billing.share_invoice": True,
    # Products
    "products.view": True,
    "products.manage": False,  # create/edit/delete/cost price
    # Inventory
    "inventory.view": True,
    "inventory.adjust": False,  # manual stock adjustments
    # Purchase orders / vendors
    "purchase_orders.access": False,
    # Payments
    "payments.create": True,
    "payments.view": True,
    # Reports
    "reports.view": True,
    # Customers
    "customers.manage": True,
    # System / admin
    "settings.manage": False,
    "company.edit": False,
    "users.manage": False,
    "audit.price_override_logs": False,
}


def get_user_role(user):
    """Return ADMIN or STAFF depending on the current user."""
    if not user or not getattr(user, "is_authenticated", False):
        return ANON

    # Admin overrides everything.
    if user.is_superuser or user.groups.filter(name__iexact="Admin").exists():
        return ADMIN

    # Explicit staff group or Django is_staff flag -> Staff role.
    if user.groups.filter(name__iexact="Staff").exists() or user.is_staff:
        return STAFF

    # Default to admin for backwards compatibility with existing users.
    return ADMIN


def user_can(user, permission_key: str) -> bool:
    """Check if user has a specific logical permission."""
    role = get_user_role(user)
    if role == ADMIN:
        return True
    if role == STAFF:
        return STAFF_PERMISSIONS.get(permission_key, False)
    return False


def permission_required(permission_key: str, as_json: bool = False):
    """
    Decorator to guard a view by logical permission.

    - Admin users always pass.
    - Staff users must be allowed by STAFF_PERMISSIONS.
    - Anonymous users are rejected.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if user_can(request.user, permission_key):
                return view_func(request, *args, **kwargs)

            wants_json = (
                as_json
                or request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
            )

            if wants_json:
                return JsonResponse(
                    {"success": False, "error": "Permission denied"},
                    status=403,
                )

            messages.error(request, "You do not have permission to perform this action.")
            return redirect("apps:dashboard")

        return _wrapped

    return decorator


def get_permission_flags(user):
    """
    Convenience booleans for templates/UI.

    Returns a dict always containing keys used in templates to avoid KeyError.
    """
    role = get_user_role(user)
    return {
        "role": role,
        "is_admin": role == ADMIN,
        "can_cancel_invoice": user_can(user, "billing.cancel_invoice"),
        "can_manage_products": user_can(user, "products.manage"),
        "can_adjust_stock": user_can(user, "inventory.adjust"),
        "can_manage_purchase_orders": user_can(user, "purchase_orders.access"),
        "can_manage_settings": user_can(user, "settings.manage"),
        "can_view_price_override_logs": user_can(user, "audit.price_override_logs"),
    }

