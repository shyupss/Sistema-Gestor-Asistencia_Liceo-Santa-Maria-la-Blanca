import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0008_quitar_genera_alerta_y_configuracion'),
        # RenameModel inyecta RenameContentType; sin esta dependencia, al revertir
        # el estado aún tiene content_type.name y la operación falla en Postgres.
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='ConfigNotificaciones',
            new_name='ConfigGeneral',
        ),
        # Django no tiene RenameConstraint: se eliminan y se recrean con el nombre nuevo.
        migrations.RemoveConstraint(
            model_name='configgeneral',
            name='ck_config_notificaciones_singleton',
        ),
        migrations.RemoveConstraint(
            model_name='configgeneral',
            name='ck_config_notificaciones_frecuencia',
        ),
        migrations.RemoveConstraint(
            model_name='configgeneral',
            name='ck_config_notificaciones_dia_semana',
        ),
        migrations.AlterModelOptions(
            name='configgeneral',
            options={
                'verbose_name': 'Configuración general',
                'verbose_name_plural': 'Configuración general',
            },
        ),
        migrations.AddField(
            model_name='configgeneral',
            name='meta_asistencia',
            field=models.PositiveSmallIntegerField(
                default=75,
                validators=[
                    django.core.validators.MinValueValidator(0),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('id', 1)), name='ck_config_general_singleton',
            ),
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('frecuencia_dias__gte', 1)), name='ck_config_general_frecuencia',
            ),
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('dia_semana_envio__gte', 1), ('dia_semana_envio__lte', 7)),
                name='ck_config_general_dia_semana',
            ),
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('meta_asistencia__gte', 0), ('meta_asistencia__lte', 100)),
                name='ck_config_general_meta',
            ),
        ),
    ]
