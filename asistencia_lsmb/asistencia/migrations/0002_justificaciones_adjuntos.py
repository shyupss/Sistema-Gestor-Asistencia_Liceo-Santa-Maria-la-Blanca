from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('asistencia', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='justificaciones',
            name='tipo',
            field=models.CharField(
                choices=[('justificacion', 'Justificación'), ('retiro', 'Retiro')],
                default='justificacion',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='justificaciones',
            name='resumen',
            field=models.CharField(default='', max_length=120),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='Adjunto_Justificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('archivo', models.FileField(upload_to='justificaciones/%Y/%m/%d/')),
                ('nombre_original', models.CharField(max_length=255)),
                ('fecha_subida', models.DateTimeField(auto_now_add=True)),
                ('justificacion', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='adjuntos',
                    to='asistencia.justificaciones',
                )),
            ],
        ),
    ]