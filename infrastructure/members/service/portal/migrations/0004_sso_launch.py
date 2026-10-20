from django.db import migrations, models
import django.core.validators
import portal.models


class Migration(migrations.Migration):
    dependencies = [('portal', '0003_ssoclient_accountlink')]
    operations = [
        migrations.AddField(model_name='ssoclient', name='login_path', field=models.CharField(
            'chemin de connexion dans l’application', max_length=240, blank=True, default='',
            validators=[portal.models.validate_login_path],
            help_text='Chemin de lancement SSO verifie, par exemple /api/auth/sso/login. Laisser vide avant recette.')),
        migrations.AlterField(model_name='application', name='slug', field=models.SlugField(primary_key=True,
            serialize=False, validators=[django.core.validators.RegexValidator(
                r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$', 'Sous-domaine DNS en minuscules requis.')]))]
