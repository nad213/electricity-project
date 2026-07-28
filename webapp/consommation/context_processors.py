"""
Context processors for OIDC user information.
"""
from .auth import get_user_from_session, is_authenticated
from .idp_admin import is_account_deletion_enabled


def oidc_user(request):
    """
    Add OIDC user info to template context.

    Makes available in all templates:
        - user_info: dict with user data (email, name, picture) or None
        - is_authenticated: boolean indicating if user is logged in
        - account_deletion_enabled: whether the in-app account deletion is
          available (the entry lives in base.html's user dropdown, hence a
          context processor rather than per-view context)
    """
    user_info = get_user_from_session(request)
    return {
        'user_info': user_info,
        'is_authenticated': is_authenticated(request),
        'account_deletion_enabled': is_account_deletion_enabled(),
    }
