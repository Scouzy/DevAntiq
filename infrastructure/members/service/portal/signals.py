from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from oauth2_provider.models import AccessToken, Grant, IDToken, RefreshToken
from django.db.models.signals import post_save
from .models import Access, SSOClient, AccountLink
from .provisioning import NATIVE_APPS, associate_dedicated_account


@receiver(post_save, sender=Access)
def link_new_grant(sender, instance, created, raw=False, **kwargs):
    if not raw and created and instance.application_id == 'omniroute' and SSOClient.objects.filter(
            application_id='omniroute', enabled=True, login_path='/api/auth/oidc/login').exists():
        AccountLink.objects.get_or_create(access=instance, defaults={
            'application_id':'omniroute','external_id':'devantiq-'+str(instance.user_id)})
    if not raw and created and instance.application_id in NATIVE_APPS and SSOClient.objects.filter(
            application_id=instance.application_id, enabled=True, dedicated_accounts=True).exists():
        associate_dedicated_account(instance)


@receiver(user_logged_out)
def revoke_oidc_on_logout(sender, request, user, **kwargs):
    if user and user.pk:
        # Central logout also invalidates unredeemed codes and provider tokens.
        # Native application sessions remain subject to the Nginx member gateway.
        Grant.objects.filter(user=user).delete()
        RefreshToken.objects.filter(user=user).delete()
        AccessToken.objects.filter(user=user).delete()
        IDToken.objects.filter(user=user).delete()
