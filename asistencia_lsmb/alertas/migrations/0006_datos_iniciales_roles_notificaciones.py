import datetime

from django.db import migrations


def crear_datos_iniciales(apps, schema_editor):
    """Idempotente: permiso 'revisar_alertas' y la fila única de ConfigNotificaciones."""
    Permiso = apps.get_model('alertas', 'Permiso')
    ConfigNotificaciones = apps.get_model('alertas', 'ConfigNotificaciones')
    Permiso.objects.get_or_create(
        codigo='revisar_alertas',
        defaults={
            'nombre': 'Revisar alertas',
            'descripcion': 'Permite revisar alertas y recibir notificaciones de alertas.',
        },
    )
    ConfigNotificaciones.objects.get_or_create(
        pk=1,
        defaults={
            'activa': True,
            'frecuencia_dias': 7,
            'dia_semana_envio': 5,
            'hora_envio': datetime.time(16, 0),
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0005_roles_cuentas_notificaciones'),
    ]

    operations = [
        migrations.RunPython(crear_datos_iniciales, migrations.RunPython.noop),
    ]
