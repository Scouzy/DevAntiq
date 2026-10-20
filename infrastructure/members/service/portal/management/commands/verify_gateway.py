from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from django.core.management.base import BaseCommand, CommandError
from portal.models import Application
from portal.views import APP_IDS


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def is_protected_redirect(code, destination, path):
    if code != 302:
        return False
    if destination == 'https://devantiq.com/auth/?next=/membres.html':
        return True
    # Existing Nginx restrictions may deny auxiliary routes before auth_request.
    # The application home must still lead to login, never to a blanket denial.
    return path != '/' and destination == 'https://devantiq.com/auth/denied/'


class Command(BaseCommand):
    help = 'Verify anonymous HTTP access is gated, then enable the nine applications.'

    def handle(self, *args, **options):
        opener = build_opener(NoRedirect)
        routes = {app: ['/'] for app in APP_IDS}
        routes['g1crm'] += ['/api/']
        routes['g1profil'] += ['/api/']
        routes['sentinet'] += ['/api/', '/ws']
        routes['livemonitor'] += ['/api/', '/ws', '/agent/']
        routes['zabbix'] += ['/index.php', '/metrics']
        failures = []
        for app, paths in routes.items():
            self.stdout.write('Verification : ' + app + '.devantiq.com')
            for path in paths:
                url = f'https://{app}.devantiq.com{path}'
                try:
                    response = opener.open(Request(url), timeout=10)
                    response.close()
                    failures.append(url + ' : contenu accessible sans session')
                except HTTPError as error:
                    destination = error.headers.get('Location', '')
                    if not is_protected_redirect(error.code, destination, path):
                        failures.append(url + f' : réponse inattendue ({error.code}), Location={destination!r}')
                except URLError:
                    failures.append(url + ' : connexion impossible')
        try:
            with opener.open('https://umami.devantiq.com/script.js', timeout=10) as response:
                if response.status != 200 or 'javascript' not in response.headers.get('Content-Type', ''):
                    failures.append('Script analytics Umami indisponible')
        except (HTTPError, URLError):
            failures.append('Script analytics Umami indisponible')
        if failures:
            raise CommandError('\n'.join(failures) + '\nApplications non activees : transmettre ce diagnostic.')
        Application.objects.filter(pk__in=APP_IDS).update(enabled=True)
        self.stdout.write(self.style.SUCCESS('Les 9 applications sont protegees et activables par attribution individuelle.'))
