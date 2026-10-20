"""OIDC issuance is limited to explicitly linked, currently authorized members."""
from django.http import HttpResponseForbidden
from django.urls import path, re_path
from oauth2_provider import views
from oauth2_provider.oauth2_validators import OAuth2Validator
from .models import AccountLink, SSOClient


def member_link(user, client):
    if not user or not user.is_authenticated or not user.is_active or not client:
        return None
    binding = SSOClient.objects.filter(oauth_client=client, enabled=True,
                                      application__enabled=True).first()
    if not binding:
        return None
    return AccountLink.objects.filter(access__user=user, application=binding.application,
                                     access__application=binding.application).exclude(external_id='').first()


class MemberAuthorizationView(views.AuthorizationView):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            # Client lookup never accepts a hostname or identity supplied by a browser.
            client_id = request.GET.get('client_id') or request.POST.get('client_id')
            binding = SSOClient.objects.select_related('oauth_client').filter(
                oauth_client__client_id=client_id).first()
            if not binding or not member_link(request.user, binding.oauth_client):
                return HttpResponseForbidden('Connexion unique non attribuée ou compte applicatif non associé.')
        return super().dispatch(request, *args, **kwargs)


class MemberOAuthValidator(OAuth2Validator):
    oidc_claim_scope = {**OAuth2Validator.oidc_claim_scope, 'external_account': 'profile'}

    def is_pkce_required(self, client_id, request):
        # OmniRoute 3.8.50's native confidential-code client has no PKCE support.
        # Keep PKCE mandatory everywhere else, including other confidential clients.
        if SSOClient.objects.filter(application_id='omniroute', enabled=True,
                oauth_client__client_id=client_id, oauth_client__client_type='confidential',
                oauth_client__authorization_grant_type='authorization-code',
                oauth_client__redirect_uris='https://omniroute.devantiq.com/api/auth/oidc/callback',
                login_path='/api/auth/oidc/login').exists():
            return False
        return super().is_pkce_required(client_id, request)

    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):
        return response_type == 'code' and super().validate_response_type(
            client_id, response_type, client, request, *args, **kwargs)

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        # Each login starts with the member session; no long-lived refresh tokens.
        return grant_type == 'authorization_code' and super().validate_grant_type(
            client_id, grant_type, client, request, *args, **kwargs)

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        return super().validate_code(client_id, code, client, request, *args, **kwargs) and bool(
            member_link(request.user, client))

    def validate_bearer_token(self, token, scopes, request):
        return super().validate_bearer_token(token, scopes, request) and bool(
            member_link(request.user, request.client))

    def validate_id_token(self, token, scopes, request):
        return super().validate_id_token(token, scopes, request) and bool(
            member_link(request.user, request.client))

    def get_additional_claims(self, request):
        link = member_link(request.user, request.client)
        if not link:
            return {}
        claims = {}
        if 'profile' in request.scopes:
            claims.update(name=request.user.get_full_name() or request.user.username,
                          preferred_username=link.external_id, external_account=link.external_id)
        if 'email' in request.scopes:
            claims.update(email=request.user.email, email_verified=False)
        return claims


# Deliberately omit client registration/management, password grants and device flows.
urlpatterns = [
    path('authorize/', MemberAuthorizationView.as_view(), name='authorize'),
    path('token/', views.TokenView.as_view(), name='token'),
    path('revoke_token/', views.RevokeTokenView.as_view(), name='revoke-token'),
    path('userinfo/', views.UserInfoView.as_view(), name='user-info'),
    re_path(r'^\.well-known/openid-configuration/?$', views.ConnectDiscoveryInfoView.as_view(), name='oidc-connect-discovery-info'),
    path('.well-known/jwks.json', views.JwksInfoView.as_view(), name='jwks-info'),
]
