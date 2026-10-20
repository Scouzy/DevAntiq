from urllib.parse import urlsplit
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from .models import Application, Access, AccountLink, SSOClient, validate_login_path

APP_IDS = ('g1crm', 'g1profil', 'sentinet', 'livemonitor', 'umami', 'cloud', 'n8n', 'omniroute', 'zabbix')


@never_cache
@require_GET
def session(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    allowed = set(Access.objects.filter(user=request.user).values_list('application_id', flat=True))
    connected = set(AccountLink.objects.filter(access__user=request.user,
        application__ssoclient__enabled=True).exclude(application__ssoclient__login_path='')
        .values_list('application_id', flat=True))
    response = JsonResponse({'user': {'name': request.user.get_full_name() or request.user.username,
        'username': request.user.username, 'email': request.user.email, 'is_admin': request.user.is_staff},
        'csrf': get_token(request), 'applications': [
            {'id': app.pk, 'name': app.name, 'description': app.description,
             'allowed': app.pk in allowed, 'enabled': app.enabled,
             'sso_ready': app.pk in connected,
             'url': f'/auth/apps/{app.pk}/open/'}
            for app in Application.objects.all()]})
    response['X-DevAntiq-Session'] = 'authenticated'
    return response


@never_cache
@require_GET
def authorize(request):
    # This endpoint is reachable only by Nginx internal subrequests.
    # The URL is rebuilt by Nginx, never accepted from a public query string.
    try:
        url = urlsplit(request.headers.get('X-Original-URL', ''))
        admin_host = url.hostname == 'admin.livemonitor.devantiq.com'
        app = 'livemonitor' if admin_host else url.hostname.removesuffix('.devantiq.com') if url.hostname else ''
        valid = (Application.objects.filter(pk=app).exists() and (url.hostname == f'{app}.devantiq.com' or admin_host)
                 and url.scheme == 'https' and url.port in (None, 443) and not url.username and not url.password)
    except ValueError:
        valid = False
    if not valid:
        return HttpResponse(status=403)
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    if admin_host and not request.user.is_superuser:
        return HttpResponse(status=403)
    granted = Access.objects.filter(user=request.user, application_id=app, application__enabled=True).exists()
    return HttpResponse(status=204 if granted else 403)


@never_cache
@require_GET
@login_required
def open_application(request, slug):
    if not Access.objects.filter(user=request.user, application_id=slug, application__enabled=True).exists():
        return HttpResponse(status=403)
    binding = SSOClient.objects.filter(application_id=slug, enabled=True).first()
    path = '/'
    if binding and binding.login_path:
        if not AccountLink.objects.filter(access__user=request.user, access__application_id=slug,
                                          application_id=slug).exclude(external_id='').exists():
            return HttpResponse('Compte applicatif non encore associe. Contactez votre administrateur.', status=403)
        validate_login_path(binding.login_path)
        path = binding.login_path
    return HttpResponseRedirect(f'https://{slug}.devantiq.com{path}')


@never_cache
@require_GET
def application_session(request, slug):
    if not request.user.is_authenticated or not request.user.is_active:
        return JsonResponse({'error': 'authentication_required'}, status=401)
    link = AccountLink.objects.filter(access__user=request.user, access__application_id=slug,
        application_id=slug, application__enabled=True, application__ssoclient__enabled=True).exclude(external_id='').first()
    if not link:
        return JsonResponse({'error': 'access_denied'}, status=403)
    return JsonResponse({'sub': str(request.user.pk), 'external_account': link.external_id})


@never_cache
@login_required
def account(request):
    return render(request, 'registration/account.html')


def denied(request):
    return render(request, 'registration/denied.html', status=403)
