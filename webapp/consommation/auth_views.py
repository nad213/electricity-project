"""
Authentication views for the OIDC integration.
"""
import secrets
from django.shortcuts import redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages

from .auth import (
    get_authorize_url,
    exchange_code_for_token,
    get_user_info,
    get_logout_url,
)


def login(request: HttpRequest) -> HttpResponse:
    """
    Redirect user to the IdP login page.
    """
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session['oidc_state'] = state

    # Build callback URL
    callback_url = request.build_absolute_uri('/callback/')

    # Redirect to the IdP
    auth_url = get_authorize_url(callback_url, state)
    return redirect(auth_url)


def callback(request: HttpRequest) -> HttpResponse:
    """
    Handle the IdP callback after successful login.
    """
    # Verify state to prevent CSRF
    state = request.GET.get('state')
    stored_state = request.session.pop('oidc_state', None)

    if not state or state != stored_state:
        messages.error(request, "Erreur d'authentification: state invalide.")
        return redirect('consommation:accueil')

    # Check for errors from the IdP
    error = request.GET.get('error')
    if error:
        error_description = request.GET.get('error_description', 'Erreur inconnue')
        messages.error(request, f"Erreur d'authentification: {error_description}")
        return redirect('consommation:accueil')

    # Get authorization code
    code = request.GET.get('code')
    if not code:
        messages.error(request, "Erreur d'authentification: code manquant.")
        return redirect('consommation:accueil')

    try:
        # Exchange code for tokens
        callback_url = request.build_absolute_uri('/callback/')
        token = exchange_code_for_token(code, callback_url)

        # Get user info
        user_info = get_user_info(token['access_token'])

        # Store user in session
        request.session['user'] = {
            'sub': user_info.get('sub'),
            'email': user_info.get('email'),
            'name': user_info.get('name', user_info.get('email', 'Utilisateur')),
            'picture': user_info.get('picture'),
        }
        # Keep the id_token for RP-initiated logout (id_token_hint).
        request.session['id_token'] = token.get('id_token')

        messages.success(request, f"Bienvenue, {request.session['user']['name']} !")

    except Exception as e:
        messages.error(request, f"Erreur lors de la connexion: {str(e)}")
        return redirect('consommation:accueil')

    # Redirect to home or stored next URL
    next_url = request.session.pop('next', None)
    return redirect(next_url if next_url else 'consommation:accueil')


def logout(request: HttpRequest) -> HttpResponse:
    """
    Log user out locally and redirect to the IdP logout endpoint.
    """
    # Clear session
    id_token = request.session.pop('id_token', None)
    request.session.pop('user', None)

    # Build return URL
    return_to = request.build_absolute_uri('/')

    # Redirect to the IdP logout
    logout_url = get_logout_url(return_to, id_token=id_token)
    return redirect(logout_url)
