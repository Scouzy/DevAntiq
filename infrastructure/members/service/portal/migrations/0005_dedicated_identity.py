from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('portal','0004_sso_launch'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='ssoclient', name='dedicated_accounts', field=models.BooleanField(default=False)),
        migrations.CreateModel(name='DedicatedIdentity', fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('external_id',models.CharField(max_length=150,unique=True)),
            ('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to=settings.AUTH_USER_MODEL)),
            ('application',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,to='portal.application')),
        ], options={'constraints':[models.UniqueConstraint(fields=('user','application'),name='dedicated_identity_per_app')]})]
