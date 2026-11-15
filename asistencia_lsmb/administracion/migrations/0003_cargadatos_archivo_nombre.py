from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0002_cargadatos_progreso"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargadatos",
            name="archivo_nombre",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
