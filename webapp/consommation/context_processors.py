"""
Context processors for Auth0 user information.
"""
from .auth import get_user_from_session, is_authenticated


def auth0_user(request):
    """
    Add Auth0 user info to template context.

    Makes available in all templates:
        - user_info: dict with user data (email, name, picture) or None
        - is_authenticated: boolean indicating if user is logged in
    """
    user_info = get_user_from_session(request)
    return {
        'user_info': user_info,
        'is_authenticated': is_authenticated(request),
    }
