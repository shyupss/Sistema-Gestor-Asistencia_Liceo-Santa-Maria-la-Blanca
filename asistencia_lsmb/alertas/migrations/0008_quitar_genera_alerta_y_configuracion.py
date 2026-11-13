from django.db import migrations


def verificar_genera_alerta(apps, schema_editor):
    """Solo lectura: aborta si algún estado tiene genera_alerta distinto de es_no_ideal."""
    Estado = apps.get_model("alertas", "Estado")
    inconsistentes = [
        e for e in Estado.objects.order_by("pk") if e.genera_alerta != e.es_no_ideal
    ]
    if inconsistentes:
        detalle = "; ".join(
            f"id={e.pk} '{e.nombre}' genera_alerta={e.genera_alerta} es_no_ideal={e.es_no_ideal}"
            for e in inconsistentes
        )
        raise RuntimeError(
            "No se puede quitar Estado.genera_alerta: hay estados donde difiere de "
            f"es_no_ideal ({detalle}). Corrígelos para que coincidan y vuelve a migrar."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("alertas", "0007_roles_iniciales"),
    ]

    operations = [
        migrations.RunPython(verificar_genera_alerta, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="estado",
            name="genera_alerta",
        ),
        migrations.DeleteModel(
            name="ConfiguracionAlerta",
        ),
    ]
