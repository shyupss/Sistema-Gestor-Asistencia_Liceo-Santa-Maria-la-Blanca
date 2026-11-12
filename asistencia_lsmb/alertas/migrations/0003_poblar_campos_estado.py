import unicodedata

from django.db import migrations

CODIGOS = {
    "optimo": "optimo",
    "adecuado": "adecuado",
    "atencion": "atencion",
    "alerta": "atencion",
    "critico": "critico",
}

# Tono principal (DEFAULT) de static/js/tailwind.config.js
COLORES = {
    "optimo": "#2F9E58",    # verde
    "adecuado": "#1B5FA8",  # azul
    "atencion": "#E3A72E",  # amarillo
    "critico": "#D9453D",   # rojo
}


def _normalizar(nombre):
    sin_tildes = unicodedata.normalize("NFD", nombre.strip().lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def poblar_campos(apps, schema_editor):
    Estado = apps.get_model("alertas", "Estado")

    for estado in Estado.objects.all():
        estado.es_no_ideal = estado.genera_alerta
        codigo = CODIGOS.get(_normalizar(estado.nombre))
        # codigo es único: si otro estado ya lo tiene, este queda null.
        if codigo and (
            estado.codigo == codigo
            or not Estado.objects.filter(codigo=codigo).exclude(pk=estado.pk).exists()
        ):
            estado.codigo = codigo
            # Solo se asigna color si sigue el valor por defecto.
            if estado.color == "#9E9E9E":
                estado.color = COLORES[codigo]
        estado.save(update_fields=["es_no_ideal", "codigo", "color"])


class Migration(migrations.Migration):

    dependencies = [
        ("alertas", "0002_estado_campos_nuevos"),
    ]

    operations = [
        migrations.RunPython(poblar_campos, migrations.RunPython.noop),
    ]
