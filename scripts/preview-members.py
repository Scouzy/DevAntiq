"""Local-only preview with public assets; never used by the production service."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent.parent
os.environ['DEVANTIQ_DEBUG'] = '1'
os.environ['DJANGO_SETTINGS_MODULE'] = 'portal.settings'
sys.path.insert(0, str(root / 'infrastructure/members/service'))
import django
django.setup()
from django.core.management import call_command
from django.urls import path, re_path
from django.views.static import serve
from portal.urls import urlpatterns
urlpatterns += [
    path('membres.html', serve, {'document_root': root, 'path': 'membres.html'}),
    path('index.html', serve, {'document_root': root, 'path': 'index.html'}),
    re_path(r'^(?P<path>(?:css|js|img)/.+)$', serve, {'document_root': root}),
]
call_command('migrate', interactive=False, verbosity=0)
call_command('runserver', '127.0.0.1:8088', use_reloader=False)
