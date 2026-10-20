import uuid
from django.db import transaction
from .models import AccountLink, DedicatedIdentity

NATIVE_APPS = ('g1crm','g1profil','livemonitor','sentinet')


def associate_dedicated_account(access):
    if access.application_id not in NATIVE_APPS:
        raise ValueError('No dedicated-account adapter for this application')
    with transaction.atomic():
        current = AccountLink.objects.filter(access=access).first()
        if current:
            return current  # Never replace an explicit existing association.
        identity, _ = DedicatedIdentity.objects.get_or_create(user=access.user,
            application=access.application, defaults={'external_id':'dv-' + uuid.uuid4().hex})
        link, _ = AccountLink.objects.get_or_create(access=access,
            defaults={'application':access.application,'external_id':identity.external_id})
        link.full_clean()
        return link
