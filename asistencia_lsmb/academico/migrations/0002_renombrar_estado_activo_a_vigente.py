from django.db import migrations


def renombrar_estado_activo(apps, schema_editor):
    EstadoMatricula = apps.get_model("academico", "EstadoMatricula")
    Matricula = apps.get_model("academico", "Matricula")

    estado_activo = EstadoMatricula.objects.filter(nombre="activo").first()
    if not estado_activo:
        return

    estado_vigente = EstadoMatricula.objects.filter(nombre="vigente").first()
    if estado_vigente:
        Matricula.objects.filter(estado_matricula=estado_activo).update(
            estado_matricula=estado_vigente
        )
        estado_activo.delete()
    else:
        estado_activo.nombre = "vigente"
        estado_activo.descripcion = estado_activo.descripcion or "Alumno con matrícula vigente"
        estado_activo.save(update_fields=["nombre", "descripcion"])


def revertir_estado_vigente(apps, schema_editor):
    EstadoMatricula = apps.get_model("academico", "EstadoMatricula")
    estado_vigente = EstadoMatricula.objects.filter(nombre="vigente").first()
    if estado_vigente:
        estado_vigente.nombre = "activo"
        estado_vigente.save(update_fields=["nombre"])


class Migration(migrations.Migration):

    dependencies = [
        ("academico", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(renombrar_estado_activo, revertir_estado_vigente),
    ]
