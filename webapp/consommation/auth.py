"""
Auth0 OAuth client configuration using Authlib.
"""
from authlib.integrations.requests_client import OAuth2Session
from django.conf import settings
from urllib.parse import urlencode


def get_auth0_authorize_url(callback_url: str, state: str) -> str:
    """
    Generate the Auth0 authorization URL for login redirect.

    Args:
        callback_url: The URL Auth0 will redirect to after login
        state: Random state string for CSRF protection

    Returns:
        The full Auth0 authorization URL
    """
    params = {
        'response_type': 'code',
        'client_id': settings.AUTH0_CLIENT_ID,
        'redirect_uri': callback_url,
        'scope': 'openid profile email',
        'state': state,
    }
    return f"https://{settings.AUTH0_DOMAIN}/authorize?{urlencode(params)}"


def exchange_code_for_token(code: str, callback_url: str) -> dict:
    """
    Exchange the authorization code for tokens.

    Args:
        code: Authorization code from Auth0 callback
        callback_url: The callback URL (must match the one used in authorize)

    Returns:
        Token response containing access_token, id_token, etc.
    """
    session = OAuth2Session(
        client_id=settings.AUTH0_CLIENT_ID,
        client_secret=settings.AUTH0_CLIENT_SECRET,
    )
    token_url = f"https://{settings.AUTH0_DOMAIN}/oauth/token"

    token = session.fetch_token(
        token_url,
        grant_type='authorization_code',
        code=code,
        redirect_uri=callback_url,
    )
    return token


def get_user_info(access_token: str) -> dict:
    """
    Fetch user info from Auth0 using the access token.

    Args:
        access_token: Valid Auth0 access token

    Returns:
        User info dict with email, name, picture, etc.
    """
    session = OAuth2Session(token={'access_token': access_token, 'token_type': 'Bearer'})
    userinfo_url = f"https://{settings.AUTH0_DOMAIN}/userinfo"

    resp = session.get(userinfo_url)
    resp.raise_for_status()
    return resp.json()


def get_logout_url(return_to: str) -> str:
    """
    Generate the Auth0 logout URL.

    Args:
        return_to: URL to redirect to after logout

    Returns:
        The full Auth0 logout URL
    """
    params = {
        'client_id': settings.AUTH0_CLIENT_ID,
        'returnTo': return_to,
    }
    return f"https://{settings.AUTH0_DOMAIN}/v2/logout?{urlencode(params)}"


def get_user_from_session(request) -> dict | None:
    """
    Get the current user info from the session.

    Args:
        request: Django request object

    Returns:
        User info dict if logged in, None otherwise
    """
    return request.session.get('user')


def is_authenticated(request) -> bool:
    """
    Check if the current request has an authenticated user.

    Args:
        request: Django request object

    Returns:
        True if user is logged in, False otherwise
    """
    return get_user_from_session(request) is not None
