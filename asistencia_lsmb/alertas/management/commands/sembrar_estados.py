from django.core.management.base import BaseCommand

from alertas.models import Estado

NIVELES = [
    # codigo, nombre, umbral_minimo, es_no_ideal, color (tailwind.config.js)
    ("optimo", "Óptimo", 95, False, "#2F9E58"),
    ("adecuado", "Adecuado", 85, False, "#1B5FA8"),
    ("atencion", "Atención", 75, True, "#E3A72E"),
    ("critico", "Crítico", 0, True, "#D9453D"),
]


class Command(BaseCommand):
    help = "Crea los niveles de Estado que falten (por codigo). No modifica los existentes."

    def handle(self, *args, **options):
        creados = 0
        for codigo, nombre, umbral, es_no_ideal, color in NIVELES:
            if Estado.objects.filter(codigo=codigo).exists():
                continue
            if Estado.objects.filter(nombre=nombre).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Se omite '{nombre}': existe un estado con ese nombre pero sin codigo '{codigo}'."
                    )
                )
                continue
            Estado.objects.create(
                codigo=codigo,
                nombre=nombre,
                umbral_minimo=umbral,
                es_no_ideal=es_no_ideal,
                genera_alerta=es_no_ideal,
                color=color,
            )
            creados += 1
        self.stdout.write(f"Estados creados: {creados}")
