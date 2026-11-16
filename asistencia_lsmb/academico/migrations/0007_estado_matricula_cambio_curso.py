from django.db import migrations

# Los valores se escriben aquí (no se importan de la app) para que la migración
# quede congelada.
NOMBRE = 'cambio_curso'
DESCRIPCION = 'Matrícula cerrada porque el alumno pasó a otro curso del liceo'


def sembrar_estado_cambio_curso(apps, schema_editor):
    """Idempotente. Crea 'cambio_curso' si falta, buscando por nombre sin distinguir mayúsculas.

    No modifica filas existentes (ni este estado ni los demás). Al revertir no se
    borra nada: puede haber matrículas apuntando a este estado.
    """
    EstadoMatricula = apps.get_model('academico', 'EstadoMatricula')
    EstadoMatricula.objects.get_or_create(
        nombre__iexact=NOMBRE,
        defaults={'nombre': NOMBRE, 'descripcion': DESCRIPCION},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('academico', '0006_estados_matricula_iniciales'),
    ]

    operations = [
        migrations.RunPython(sembrar_estado_cambio_curso, migrations.RunPython.noop),
    ]
