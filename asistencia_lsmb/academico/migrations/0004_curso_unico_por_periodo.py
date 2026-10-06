from django.db import migrations, models
from django.db.models.functions import Trim, Upper


def normalizar_grupos(apps, schema_editor):
    Curso = apps.get_model("academico", "Curso")
    cursos = Curso.objects.using(schema_editor.connection.alias)
    duplicados = list(
        cursos.annotate(grupo_normalizado=Upper(Trim("grupo")))
        .values("periodo_id", "nivel", "grupo_normalizado")
        .annotate(cantidad=models.Count("pk"))
        .filter(cantidad__gt=1)
        .order_by("periodo_id", "nivel", "grupo_normalizado")
    )
    if duplicados:
        detalle = "; ".join(
            f"período ID {item['periodo_id']}, nivel {item['nivel']}, "
            f"grupo {item['grupo_normalizado']} ({item['cantidad']} cursos)"
            for item in duplicados
        )
        raise RuntimeError(
            "Existen cursos duplicados. Resolver sus relaciones antes de "
            f"volver a ejecutar la migración: {detalle}. No se eliminaron cursos."
        )
    cursos.update(grupo=Upper(Trim("grupo")))


class Migration(migrations.Migration):
    dependencies = [
        ("academico", "0003_curso_profesor_jefe_funcionario"),
    ]

    operations = [
        migrations.RunPython(normalizar_grupos, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="curso",
            constraint=models.UniqueConstraint(
                models.F("periodo"), models.F("nivel"), Upper(Trim("grupo")),
                name="uq_curso_periodo_nivel_grupo",
            ),
        ),
    ]
