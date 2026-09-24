from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('asistencia', '0002_justificaciones_adjuntos'),
    ]

    operations = [
        migrations.AddField(
            model_name='justificaciones',
            name='fecha_registro',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]