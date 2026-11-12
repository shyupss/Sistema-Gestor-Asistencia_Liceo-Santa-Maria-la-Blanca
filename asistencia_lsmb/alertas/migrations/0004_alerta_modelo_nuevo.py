import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0003_poblar_campos_estado'),
    ]

    operations = [
        migrations.RenameField(
            model_name='alerta',
            old_name='fecha',
            new_name='fecha_creacion',
        ),
        migrations.AddField(
            model_name='alerta',
            name='fecha_cierre',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='alerta',
            name='motivo_cierre',
            field=models.CharField(blank=True, choices=[('recuperado', 'Recuperado'), ('cambio_estado', 'Cambio de estado'), ('fin_matricula', 'Fin de matrícula'), ('fin_periodo', 'Fin de período')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='alerta',
            name='funcionario_revisa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='alertas_revisadas', to='alertas.funcionario'),
        ),
        migrations.AddField(
            model_name='alerta',
            name='nota',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.RemoveField(
            model_name='alerta',
            name='funcionario',
        ),
        migrations.AddConstraint(
            model_name='alerta',
            constraint=models.UniqueConstraint(condition=models.Q(('fecha_cierre__isnull', True)), fields=('alumno', 'periodo'), name='uq_alerta_vigente_alumno_periodo'),
        ),
    ]
