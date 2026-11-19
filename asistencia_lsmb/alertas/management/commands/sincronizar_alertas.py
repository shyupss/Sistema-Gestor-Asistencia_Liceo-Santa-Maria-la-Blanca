from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academico.models import PeriodoAcademico
from alertas.services.alertas_service import (
    CAMBIO_ESTADO,
    CREADA,
    MOTIVO_FIN_MATRICULA,
    MOTIVO_FIN_PERIODO,
    RECUPERADA,
    SIN_CAMBIO,
    barrido_cierres,
    reconciliar_alertas,
)


class Command(BaseCommand):
    help = (
        "Cierra las alertas vigentes cuyo período terminó o cuyo alumno ya no está "
        "matriculado, y luego reconcilia las alertas con el estado de cada alumno "
        "(crea las que faltan y cierra las que ya no corresponden). Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--periodo", type=int, metavar="AAAA",
            help="Año del período (PeriodoAcademico.anio) al que se limitan el barrido y la reconciliación.",
        )
        parser.add_argument(
            "--solo-cierres", action="store_true",
            help="Solo el barrido de cierres; omite la reconciliación.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Ejecuta todo en una transacción que se revierte al final e informa lo que habría hecho.",
        )

    def handle(self, *args, **options):
        periodo = None
        if options["periodo"] is not None:
            periodo = PeriodoAcademico.objects.filter(anio=options["periodo"]).first()
            if periodo is None:
                raise CommandError(f"No existe el período {options['periodo']}.")

        if options["dry_run"]:
            with transaction.atomic():
                cierres, reconciliacion = self._sincronizar(periodo, options["solo_cierres"])
                transaction.set_rollback(True)
        else:
            cierres, reconciliacion = self._sincronizar(periodo, options["solo_cierres"])

        lineas = [
            f"Alcance: período {periodo.anio}" if periodo else "Alcance: todos los períodos",
            f"Cierres: fin de período {cierres[MOTIVO_FIN_PERIODO]}, "
            f"fin de matrícula {cierres[MOTIVO_FIN_MATRICULA]}.",
        ]
        if reconciliacion is None:
            lineas.append("Reconciliación: omitida (--solo-cierres).")
        else:
            lineas.append(
                f"Reconciliación: creadas {reconciliacion[CREADA]}, "
                f"cambio de estado {reconciliacion[CAMBIO_ESTADO]}, "
                f"recuperadas {reconciliacion[RECUPERADA]}, "
                f"sin cambio {reconciliacion[SIN_CAMBIO]}."
            )
        if options["dry_run"]:
            lineas.append("Se revirtieron todos los cambios.")

        prefijo = "[dry-run] " if options["dry_run"] else ""
        for linea in lineas:
            self.stdout.write(prefijo + linea)

    @staticmethod
    def _sincronizar(periodo, solo_cierres):
        # Un mismo "ahora" para las dos funciones: el mismo "hoy" en toda la corrida.
        ahora = timezone.now()
        cierres = barrido_cierres(ahora=ahora, periodo=periodo)
        if solo_cierres:
            return cierres, None
        return cierres, reconciliar_alertas(periodo=periodo, ahora=ahora)
