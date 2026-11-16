from django.db import migrations

# nombre -> descripcion. Los valores se escriben aquí (no se importan de la app)
# para que la migración quede congelada.
ESTADOS_MATRICULA = {
    'vigente': 'Alumno con matrícula vigente',
    'retirado': 'Alumno que se retiró del liceo',
    'egresado': 'Alumno que egresó del liceo',
}


def sembrar_estados_matricula(apps, schema_editor):
    """Idempotente. Crea lo que falte, buscando por nombre sin distinguir mayúsculas.

    No modifica filas existentes. La vigencia de una matrícula depende de
    fecha_termino; el estado es solo una etiqueta.
    """
    EstadoMatricula = apps.get_model('academico', 'EstadoMatricula')
    for nombre, descripcion in ESTADOS_MATRICULA.items():
        EstadoMatricula.objects.get_or_create(
            nombre__iexact=nombre,
            defaults={'nombre': nombre, 'descripcion': descripcion},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('academico', '0005_merge_estado_y_curso'),
    ]

    operations = [
        migrations.RunPython(sembrar_estados_matricula, migrations.RunPython.noop),
    ]
