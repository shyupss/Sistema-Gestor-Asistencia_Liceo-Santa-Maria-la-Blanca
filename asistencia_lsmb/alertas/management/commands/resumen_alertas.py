import argparse
import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from alertas.models import Funcionario
from alertas.queries.destinatario_queries import funcionarios_con_permiso
from alertas.queries.periodo_queries import periodo_actual
from alertas.services.alertas_service import PERMISO_REVISAR_ALERTAS
from alertas.services.formato import formatear_porcentaje
from alertas.services.resumen_alertas import construir_resumenes


# --- Selección de destinatarios: también la usa enviar_resumenes_alertas ---

def fecha_iso(valor):
    """Tipo de argparse para --hoy (AAAA-MM-DD)."""
    try:
        return datetime.date.fromisoformat(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Fecha inválida: {valor!r}. Usa AAAA-MM-DD.")


def agregar_argumentos_de_seleccion(parser):
    """Agrega --email y --hoy."""
    parser.add_argument(
        "--email", metavar="CORREO",
        help="Solo el destinatario con ese correo (sin distinguir mayúsculas).",
    )
    parser.add_argument(
        "--hoy", type=fecha_iso, metavar="AAAA-MM-DD",
        help="Fecha a usar como hoy (por defecto, la fecha local actual).",
    )


def seleccionar_destinatarios(correo=None):
    """Lista de destinatarios, o solo el del `correo`; CommandError si no existe o no es destinatario."""
    destinatarios = funcionarios_con_permiso(PERMISO_REVISAR_ALERTAS)
    if not correo:
        return list(destinatarios)
    correo = correo.strip()
    destinatarios = list(destinatarios.filter(email__iexact=correo))
    if destinatarios:
        return destinatarios
    if Funcionario.objects.filter(email__iexact=correo).exists():
        raise CommandError(
            f"{correo} no es destinatario: necesita estar activo, con cuenta activa "
            f"y un rol con el permiso {PERMISO_REVISAR_ALERTAS}."
        )
    raise CommandError(f"No existe ningún funcionario con el correo {correo}.")


class Command(BaseCommand):
    help = (
        "Muestra qué recibiría cada destinatario en el correo de alertas: cursos con "
        "alertas sin revisar y sus alumnos. Solo lectura: no envía nada ni escribe en la BD."
    )

    def add_arguments(self, parser):
        agregar_argumentos_de_seleccion(parser)

    def handle(self, *args, **options):
        hoy = options["hoy"] or timezone.localdate()
        destinatarios = seleccionar_destinatarios(options["email"])

        fecha = hoy.strftime("%d/%m/%Y")
        periodo = periodo_actual(hoy)
        if periodo is None:
            self.stdout.write(
                f"Resumen de alertas al {fecha}: no hay período académico para el año {hoy.year}."
            )
            resumenes = []
        else:
            self.stdout.write(
                f"Resumen de alertas al {fecha} (período {periodo.anio}). "
                "Solo lectura: no se envía nada."
            )
            resumenes = construir_resumenes(destinatarios, hoy)

        for resumen in resumenes:
            self._imprimir(resumen)
        self.stdout.write("")
        self.stdout.write(
            f"Destinatarios con contenido: {len(resumenes)}. "
            f"Sin contenido: {len(destinatarios) - len(resumenes)}."
        )

    def _imprimir(self, resumen):
        funcionario = resumen.funcionario
        self.stdout.write("")
        self.stdout.write(
            f"{funcionario.nombre} <{funcionario.email}> — rol: {funcionario.cuenta.rol.nombre}"
        )
        for curso in resumen.cursos:
            alumnos = "alumno" if curso.total_alumnos == 1 else "alumnos"
            self.stdout.write(f"  {curso.nombre}, {curso.total_alumnos} {alumnos}")
            for alumno in curso.alumnos:
                self.stdout.write(
                    f"    - {alumno.nombre} · {alumno.estado} · "
                    f"{formatear_porcentaje(alumno.porcentaje)} · "
                    f"alerta del {alumno.fecha_alerta:%d/%m/%Y}"
                )
            if curso.restantes:
                self.stdout.write(f"    ... y {curso.restantes} más")
