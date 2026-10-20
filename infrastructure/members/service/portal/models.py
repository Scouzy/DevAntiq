from django.conf import settings
from django.db import models
from django.core.validators import RegexValidator


def validate_login_path(value):
    import re
    from django.core.exceptions import ValidationError
    if value and not re.fullmatch(r'/(?:[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?/)*[A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)?/?', value):
        raise ValidationError('Chemin local requis, sans domaine, parametres ni fragment.')


class Application(models.Model):
    slug = models.SlugField(primary_key=True, validators=[RegexValidator(
        r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$', 'Sous-domaine DNS en minuscules requis.')])
    name = models.CharField('nom', max_length=80)
    description = models.CharField(max_length=180)
    enabled = models.BooleanField('accès activé', default=False,
        help_text='Activer seulement après installation et vérification du contrôle Nginx sur le sous-domaine et ses alias.')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = 'application'


class Access(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='membre')
    application = models.ForeignKey(Application, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'application'], name='one_access_per_member')]
        verbose_name = 'accès application'
        verbose_name_plural = 'accès applications'

    def __str__(self):
        return f'{self.user} — {self.application}'


class LoginWindow(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    count = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField(db_index=True)


class SSOClient(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE)
    oauth_client = models.OneToOneField('oauth2_provider.Application', on_delete=models.CASCADE)
    enabled = models.BooleanField('connexion unique activée', default=False)
    dedicated_accounts = models.BooleanField(default=False)
    login_path = models.CharField('chemin de connexion dans l’application', max_length=240,
        blank=True, default='', validators=[validate_login_path],
        help_text='Chemin de lancement SSO verifie, par exemple /api/auth/sso/login. Laisser vide avant recette.')

    def __str__(self):
        return str(self.application)


class AccountLink(models.Model):
    access = models.OneToOneField(Access, on_delete=models.CASCADE, verbose_name='accès attribué')
    application = models.ForeignKey(Application, on_delete=models.CASCADE)
    external_id = models.CharField('identifiant exact dans l’application', max_length=150,
        help_text='Association explicite validée par un administrateur ; jamais déduite de l’adresse e-mail.')

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.access_id and self.access.application_id != self.application_id:
            raise ValidationError('L’application doit correspondre à l’accès attribué.')
        if not self.external_id.strip() or self.external_id != self.external_id.strip():
            raise ValidationError('Saisissez un identifiant sans espaces en début ou fin.')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['application', 'external_id'], name='unique_external_account')]
        verbose_name = 'compte applicatif associé'
        verbose_name_plural = 'comptes applicatifs associés'


class DedicatedIdentity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    application = models.ForeignKey(Application, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=150, unique=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'application'], name='dedicated_identity_per_app')]
