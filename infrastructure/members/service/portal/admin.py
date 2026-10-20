from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserChangeForm, AdminUserCreationForm, PasswordResetForm
from .models import Application, Access, AccountLink, SSOClient


class MemberForm(UserChangeForm):
    email = forms.EmailField(required=True, label='Adresse e-mail')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Cette adresse appartient déjà à un compte.')
        return email

    def clean(self):
        data = super().clean()
        if self.instance.is_superuser and (not data.get('is_active') or not data.get('is_superuser')):
            if not User.objects.filter(is_active=True, is_superuser=True).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Conservez au moins un administrateur actif.')
        return data


class AccessInline(admin.TabularInline):
    model = Access
    extra = 0
    verbose_name_plural = 'Applications attribuées à ce membre'


class MemberCreationForm(AdminUserCreationForm):
    email = forms.EmailField(required=True, label='Adresse e-mail')

    class Meta(AdminUserCreationForm.Meta):
        fields = ('username', 'email', 'first_name', 'last_name')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Cette adresse appartient déjà à un compte.')
        return email


@admin.action(description='Envoyer un lien de création / réinitialisation du mot de passe')
def send_reset(modeladmin, request, queryset):
    sent = 0
    for user in queryset.filter(is_active=True).exclude(email=''):
        if not user.has_usable_password():
            modeladmin.message_user(request, f'{user.username} : définissez d’abord un mot de passe dans la fiche.', messages.WARNING)
            continue
        form = PasswordResetForm({'email': user.email})
        if form.is_valid():
            try:
                form.save(use_https=True, domain_override='devantiq.com',
                          email_template_name='registration/reset_email.txt', subject_template_name='registration/reset_subject.txt')
                sent += 1
            except Exception:
                modeladmin.message_user(request, 'Envoi impossible. Vérifiez le service de messagerie.', messages.ERROR)
    modeladmin.message_user(request, f'{sent} demande(s) d’envoi traitée(s).')


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class MemberAdmin(UserAdmin):
    form = MemberForm
    add_form = MemberCreationForm
    add_fieldsets = ((None, {'classes': ('wide',), 'fields': (
        'username', 'email', 'first_name', 'last_name', 'password1', 'password2')}),)
    inlines = [AccessInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'last_login']
    actions = [send_reset]
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Profil', {'fields': ('first_name', 'last_name', 'email')}),
        ('Statut', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Historique', {'fields': ('last_login', 'date_joined')}),
    )
    readonly_fields = ['last_login', 'date_joined']

    def has_delete_permission(self, request, obj=None):
        return False  # Suspend accounts to retain the administration audit trail.

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['name', 'enabled']
    readonly_fields = ['slug']

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def get_readonly_fields(self, request, obj=None):
        return ['slug'] if obj else []

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = 'DevAntiq — Administration des membres'
admin.site.site_title = 'Administration DevAntiq'
admin.site.index_title = 'Comptes et applications'
admin.site.site_url = '/membres.html'


@admin.register(AccountLink)
class AccountLinkAdmin(admin.ModelAdmin):
    list_display = ['access', 'application', 'external_id']
    list_filter = ['application']

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(SSOClient)
class SSOClientAdmin(admin.ModelAdmin):
    list_display = ['application', 'enabled', 'login_path']
    readonly_fields = ['application', 'oauth_client', 'enabled', 'dedicated_accounts']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser
