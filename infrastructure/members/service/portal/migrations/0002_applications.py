from django.db import migrations


def seed(apps, schema_editor):
    Application = apps.get_model('portal', 'Application')
    for slug, name, description in [
        ('g1crm', 'G1CRM', 'Relation client'), ('g1profil', 'G1Profil', 'Profils et parcours'),
        ('sentinet', 'SentiNet', 'Votre espace SentiNet'), ('livemonitor', 'LiveMonitor', 'Supervision en direct'),
        ('umami', 'Umami', 'Statistiques de fréquentation'), ('cloud', 'Cloud', 'Fichiers et collaboration'),
        ('n8n', 'n8n', 'Automatisation des workflows'), ('omniroute', 'OmniRoute', 'Votre espace OmniRoute'),
        ('zabbix', 'Zabbix', 'Supervision de l’infrastructure'),
    ]:
        Application.objects.get_or_create(slug=slug, defaults={'name': name, 'description': description})


class Migration(migrations.Migration):
    dependencies = [('portal', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
