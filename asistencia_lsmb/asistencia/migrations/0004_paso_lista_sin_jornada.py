from django.db import migrations, models
from django.db.models import Count


def verificar_sin_duplicados(apps, schema_editor):
    """Aborta con un mensaje claro si hay pasos de lista duplicados por (curso, fecha)."""
    Paso_Lista = apps.get_model("asistencia", "Paso_Lista")
    duplicados = (
        Paso_Lista.objects.values("curso_id", "fecha")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("curso_id", "fecha")
    )
    casos = []
    for dup in duplicados:
        jornadas = sorted(
            Paso_Lista.objects.filter(curso_id=dup["curso_id"], fecha=dup["fecha"])
            .values_list("jornada", flat=True)
        )
        casos.append(
            f"curso {dup['curso_id']} / {dup['fecha']} (jornadas: {', '.join(jornadas)})"
        )
    if casos:
        raise RuntimeError(
            f"No se puede eliminar 'jornada': hay {len(casos)} caso(s) de pasos de lista "
            f"duplicados por (curso, fecha): {'; '.join(casos)}. "
            "Resuélvelos manualmente y vuelve a migrar."
        )


class Migration(migrations.Migration):

    dependencies = [
        ('asistencia', '0003_justificaciones_fecha_registro'),
    ]

    operations = [
        migrations.RunPython(verificar_sin_duplicados, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='paso_lista',
            name='uq_paso_lista_curso_fecha_jornada',
        ),
        migrations.RemoveField(
            model_name='paso_lista',
            name='jornada',
        ),
        migrations.AddConstraint(
            model_name='paso_lista',
            constraint=models.UniqueConstraint(fields=('curso', 'fecha'), name='uq_paso_lista_curso_fecha'),
        ),
    ]
