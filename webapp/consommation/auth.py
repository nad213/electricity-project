"""
Generic OIDC client (Authlib + OpenID Connect discovery).

Provider-agnostic: all endpoints are read from the issuer's
``/.well-known/openid-configuration`` document, so any standards-compliant
OpenID Connect provider (Zitadel, Keycloak, Auth0, …) works by configuring
``OIDC_ISSUER`` / ``OIDC_CLIENT_ID`` / ``OIDC_CLIENT_SECRET`` only.
"""
import requests
from authlib.integrations.requests_client import OAuth2Session
from django.conf import settings
from urllib.parse import urlencode


# Cache the discovery document per issuer for the process lifetime — it is
# effectively static configuration and we don't want to fetch it on every login.
_oidc_config_cache: dict[str, dict] = {}

# Seconds to wait on network calls to the IdP before giving up.
_HTTP_TIMEOUT = 10


def get_oidc_config() -> dict:
    """
    Fetch (and cache) the OpenID Connect discovery document for the configured
    issuer.

    Returns:
        The parsed ``openid-configuration`` JSON (authorization_endpoint,
        token_endpoint, userinfo_endpoint, end_session_endpoint, …).
    """
    issuer = settings.OIDC_ISSUER.rstrip('/')
    if issuer not in _oidc_config_cache:
        url = f"{issuer}/.well-known/openid-configuration"
        resp = requests.get(url, timeout=_HTTP_TIMEOUT)
        resp.raise_for_status()
        _oidc_config_cache[issuer] = resp.json()
    return _oidc_config_cache[issuer]


def get_authorize_url(callback_url: str, state: str) -> str:
    """
    Generate the OIDC authorization URL for the login redirect.

    Args:
        callback_url: The URL the IdP will redirect to after login
        state: Random state string for CSRF protection

    Returns:
        The full authorization URL
    """
    params = {
        'response_type': 'code',
        'client_id': settings.OIDC_CLIENT_ID,
        'redirect_uri': callback_url,
        'scope': settings.OIDC_SCOPES,
        'state': state,
    }
    # Force the IdP login UI language (overrides the browser's Accept-Language).
    if settings.OIDC_UI_LOCALES:
        params['ui_locales'] = settings.OIDC_UI_LOCALES
    endpoint = get_oidc_config()['authorization_endpoint']
    return f"{endpoint}?{urlencode(params)}"


def exchange_code_for_token(code: str, callback_url: str) -> dict:
    """
    Exchange the authorization code for tokens.

    Args:
        code: Authorization code from the IdP callback
        callback_url: The callback URL (must match the one used in authorize)

    Returns:
        Token response containing access_token, id_token, etc.
    """
    session = OAuth2Session(
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
    )
    token_url = get_oidc_config()['token_endpoint']

    token = session.fetch_token(
        token_url,
        grant_type='authorization_code',
        code=code,
        redirect_uri=callback_url,
    )
    return token


def get_user_info(access_token: str) -> dict:
    """
    Fetch user info from the IdP using the access token.

    Args:
        access_token: Valid access token

    Returns:
        User info dict with sub, email, name, picture, etc.
    """
    session = OAuth2Session(token={'access_token': access_token, 'token_type': 'Bearer'})
    userinfo_url = get_oidc_config()['userinfo_endpoint']

    resp = session.get(userinfo_url)
    resp.raise_for_status()
    return resp.json()


def get_logout_url(return_to: str, id_token: str | None = None) -> str:
    """
    Generate the RP-initiated logout URL (OIDC ``end_session_endpoint``).

    Args:
        return_to: URL to redirect to after logout
        id_token: The id_token from login, used as ``id_token_hint`` when
            available (some providers require it alongside the redirect)

    Returns:
        The full logout URL
    """
    params = {
        'client_id': settings.OIDC_CLIENT_ID,
        'post_logout_redirect_uri': return_to,
    }
    if id_token:
        params['id_token_hint'] = id_token
    endpoint = get_oidc_config()['end_session_endpoint']
    return f"{endpoint}?{urlencode(params)}"


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
