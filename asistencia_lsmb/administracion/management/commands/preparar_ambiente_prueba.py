from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from administracion.services.ambiente_prueba import (
    AmbientePruebaError,
    aviso_sin_estados,
    preparar_ambiente_prueba,
)


class Command(BaseCommand):
    help = (
        "Prepara el ambiente de prueba: período del año actual, 12 cursos, roles con sus "
        "permisos, funcionarios de prueba con cuenta, profesor jefe de cada curso y cursos "
        "de los Inspectores (idempotente; no modifica lo existente). "
        "Requiere PERMITIR_AMBIENTE_PRUEBA=1."
    )

    def handle(self, *args, **options):
        if not settings.PERMITIR_AMBIENTE_PRUEBA:
            raise CommandError(
                "El ambiente de prueba está deshabilitado. "
                "Define PERMITIR_AMBIENTE_PRUEBA=1 en el entorno para usarlo."
            )
        try:
            creados = preparar_ambiente_prueba()
        except AmbientePruebaError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS("Ambiente de prueba listo. Registros creados:"))
        for tipo, cantidad in creados.items():
            self.stdout.write(f"  {tipo}: {cantidad}")
        aviso = aviso_sin_estados(creados)
        if aviso:
            self.stdout.write(self.style.WARNING(aviso))
