import unicodedata

from django.db import migrations

# Familia de color (paleta de Tailwind) según el nombre normalizado del estado.
COLORES = {
    "optimo": "verde",
    "adecuado": "azul",
    "atencion": "amarillo",
    "alerta": "amarillo",
    "critico": "rojo",
}


def _normalizar(nombre):
    sin_tildes = unicodedata.normalize("NFD", nombre.strip().lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def poblar_campos(apps, schema_editor):
    Estado = apps.get_model("alertas", "Estado")

    for estado in Estado.objects.all():
        estado.es_no_ideal = estado.genera_alerta
        color = COLORES.get(_normalizar(estado.nombre))
        # Solo se asigna color si sigue el valor por defecto.
        if color and estado.color == "gris":
            estado.color = color
        estado.save(update_fields=["es_no_ideal", "color"])


class Migration(migrations.Migration):

    dependencies = [
        ("alertas", "0002_estado_campos_nuevos"),
    ]

    operations = [
        migrations.RunPython(poblar_campos, migrations.RunPython.noop),
    ]
