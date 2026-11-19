import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    """ConfigGeneral v2: modo de envío (diario/semanal/mensual) y día del mes.

    Quita frecuencia_dias. Los AddField aplican sus defaults a la fila existente
    (modo='semanal', dia_mes_envio=1). Al revertir, frecuencia_dias vuelve con
    su default (7).
    """

    dependencies = [
        ('alertas', '0009_config_general'),
    ]

    operations = [
        migrations.AddField(
            model_name='configgeneral',
            name='modo',
            field=models.CharField(
                choices=[('diario', 'Diario'), ('semanal', 'Semanal'), ('mensual', 'Mensual')],
                default='semanal',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='configgeneral',
            name='dia_mes_envio',
            field=models.PositiveSmallIntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(31),
                ],
            ),
        ),
        # El constraint se quita antes que el campo al que se refiere.
        migrations.RemoveConstraint(
            model_name='configgeneral',
            name='ck_config_general_frecuencia',
        ),
        migrations.RemoveField(
            model_name='configgeneral',
            name='frecuencia_dias',
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('modo__in', ['diario', 'semanal', 'mensual'])),
                name='ck_config_general_modo',
            ),
        ),
        migrations.AddConstraint(
            model_name='configgeneral',
            constraint=models.CheckConstraint(
                condition=models.Q(('dia_mes_envio__gte', 1), ('dia_mes_envio__lte', 31)),
                name='ck_config_general_dia_mes',
            ),
        ),
    ]
