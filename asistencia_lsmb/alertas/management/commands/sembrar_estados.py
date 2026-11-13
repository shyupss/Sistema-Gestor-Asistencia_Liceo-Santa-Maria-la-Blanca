from django.core.management.base import BaseCommand

from alertas.models import Estado

NIVELES = [
    # nombre, umbral_minimo, es_no_ideal, color (familia de Tailwind)
    ("Óptimo", 95, False, "verde"),
    ("Adecuado", 85, False, "azul"),
    ("Atención", 75, True, "amarillo"),
    ("Crítico", 0, True, "rojo"),
]


class Command(BaseCommand):
    help = (
        "Crea los 4 niveles de Estado por defecto solo si la tabla Estado está vacía. "
        "Si existe al menos un Estado, no crea ni modifica nada."
    )

    def handle(self, *args, **options):
        if Estado.objects.exists():
            self.stdout.write(
                "Ya existen estados: no se crea ni modifica nada. Estados creados: 0"
            )
            return

        for nombre, umbral, es_no_ideal, color in NIVELES:
            Estado.objects.create(
                nombre=nombre,
                umbral_minimo=umbral,
                es_no_ideal=es_no_ideal,
                color=color,
            )
        self.stdout.write(f"Estados creados: {len(NIVELES)}")
