import hashlib
import time
from datetime import datetime, timezone
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin
from .models import LoginWindow


class LoginThrottle(MiddlewareMixin):
    last_cleanup = 0

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != 'POST' or request.path not in ('/auth/', '/auth/reset/', '/auth/admin/login/'):
            return None
        # X-Real-IP is overwritten by the only public ingress, Nginx.
        ip = request.META.get('HTTP_X_REAL_IP', request.META.get('REMOTE_ADDR', 'unknown'))
        identity = request.POST.get('username', request.POST.get('email', '')).strip().casefold()
        now = int(time.time())
        if now - type(self).last_cleanup > 3600:
            LoginWindow.objects.filter(expires__lt=datetime.now(timezone.utc)).delete()
            type(self).last_cleanup = now
        buckets = [('ip:' + ip, 60, 15)]
        if identity:
            buckets.append(('account:' + identity, 900, 12))
        for value, seconds, limit in buckets:
            key = hashlib.sha256(f'{value}:{now // seconds}'.encode()).hexdigest()
            with transaction.atomic():
                window, _ = LoginWindow.objects.get_or_create(key=key, defaults={
                    'expires': datetime.fromtimestamp((now // seconds + 1) * seconds, timezone.utc)})
                LoginWindow.objects.filter(pk=key).update(count=F('count') + 1)
                window.refresh_from_db()
            if window.count > limit:
                response = HttpResponse('Trop de tentatives. Veuillez réessayer dans quelques minutes.', status=429)
                response['Retry-After'] = str(seconds - now % seconds)
                return response
