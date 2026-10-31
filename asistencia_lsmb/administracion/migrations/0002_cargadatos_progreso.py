from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("administracion", "0001_cargadatos"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargadatos",
            name="progreso_actual",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cargadatos",
            name="progreso_porcentaje",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="cargadatos",
            name="etapa",
            field=models.CharField(default="preparando", max_length=20),
        ),
        migrations.AddField(
            model_name="cargadatos",
            name="mensaje_progreso",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
