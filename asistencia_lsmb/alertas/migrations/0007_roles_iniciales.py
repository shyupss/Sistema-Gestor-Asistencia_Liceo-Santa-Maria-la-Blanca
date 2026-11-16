from django.db import migrations


def crear_roles_iniciales(apps, schema_editor):
    """No hace nada.

    Antes sembraba los roles Asistente social, Rector, Inspector general e
    Inspector. Los roles pasaron al ambiente de prueba (botón «Preparar ambiente
    de prueba» del módulo de administración), así que una BD recién migrada ya
    no los trae. Es una migración solo de datos: las BD que ya tenían los roles
    los conservan. El archivo y su lugar en la cadena de dependencias se
    mantienen para no romper el historial de migraciones.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('alertas', '0006_datos_iniciales_roles_notificaciones'),
    ]

    operations = [
        migrations.RunPython(crear_roles_iniciales, migrations.RunPython.noop),
    ]
