#!/bin/sh
set -eu
test "$(id -u)" = 0 || { echo 'Executer en root.'; exit 1; }
cd /opt/devantiq-members
docker compose version >/dev/null
nginx -t
umask 022
install -d -m 750 -o 10001 -g 10001 config data
install -d -m 755 -o 10001 -g 10001 static
python3 configure.py
# The signing key stays in the existing private config volume, never in a bundle.
if [ ! -f config/oidc-private.pem ]; then
    (umask 077; openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out config/oidc-private.pem 2>/dev/null)
fi
openssl pkey -in config/oidc-private.pem -check -noout >/dev/null
chown 10001:10001 config/oidc-private.pem
chmod 600 config/oidc-private.pem
docker compose build members
docker compose run --rm members python manage.py check --deploy --fail-level ERROR
docker compose run --rm members python manage.py migrate --noinput
docker compose run --rm members python manage.py collectstatic --noinput
if ! docker compose run --rm -T members python manage.py shell -c 'from django.contrib.auth.models import User; import sys; sys.exit(0 if User.objects.filter(is_superuser=True,is_active=True).exists() else 1)'; then
    echo 'Creation du premier administrateur : saisir identifiant, email et mot de passe.'
    docker compose run --rm members python manage.py createsuperuser
fi
docker compose up -d members
python3 - <<'PY'
import time, urllib.request, urllib.error
for attempt in range(15):
    req = urllib.request.Request('http://127.0.0.1:9092/api/member-session', headers={'Host':'devantiq.com','X-Forwarded-Proto':'https'})
    try:
        urllib.request.urlopen(req, timeout=3)
    except urllib.error.HTTPError as error:
        if error.code == 401:
            break
    except OSError:
        pass
    time.sleep(1)
else:
    raise SystemExit('Service membres indisponible. Aucun changement Nginx effectue.')
request = urllib.request.Request('http://127.0.0.1:9092/auth/oidc/.well-known/openid-configuration',
    headers={'Host':'devantiq.com','X-Forwarded-Proto':'https'})
import json
with urllib.request.urlopen(request, timeout=5) as response:
    metadata = json.load(response)
if metadata.get('issuer') != 'https://devantiq.com/auth/oidc':
    raise SystemExit('Decouverte OIDC inattendue. Aucun client SSO active.')
print('Fournisseur OIDC disponible ; raccordements applicatifs encore desactives.')
PY
mkdir -p public-stage
tar -xzf public.tar.gz -C public-stage --no-same-owner
python3 public-stage/publish-showcase.py install /opt/devantiq-members/public-stage
python3 nginx_portal.py
python3 verify_origins.py
python3 protect_apps.py
docker compose exec -T members python manage.py verify_gateway
echo 'Espace membres : https://devantiq.com/membres.html'
echo 'Administration : https://devantiq.com/auth/admin/'
echo 'Attribuez les applications aux membres depuis leur fiche administrateur.'
