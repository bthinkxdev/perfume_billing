from .permissions import get_permission_flags, get_user_role


def permissions_context(request):
    """
    Inject a lightweight permission/role snapshot for templates.
    Ensures templates can safely check perm.* keys even for anonymous users.
    """
    user = getattr(request, "user", None)
    return {
        "user_role": get_user_role(user) if user else None,
        "perm": get_permission_flags(user) if user else {},
    }

