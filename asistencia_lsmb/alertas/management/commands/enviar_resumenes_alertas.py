from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.utils import timezone

from alertas.management.commands.resumen_alertas import (
    agregar_argumentos_de_seleccion,
    seleccionar_destinatarios,
)
from alertas.queries.periodo_queries import periodo_actual
from alertas.services.envio_alertas import (
    ENVIADO,
    FALLIDO,
    SIN_CORREO,
    enviar_resumenes,
    renderizar_correo,
)
from alertas.services.resumen_alertas import construir_resumenes

ETIQUETAS_RESULTADO = {ENVIADO: "Enviado", FALLIDO: "Falló", SIN_CORREO: "Sin correo"}


class Command(BaseCommand):
    help = (
        "Envía a cada destinatario el correo con sus alertas sin revisar. Exige exactamente "
        "un modo: --dry-run (muestra los correos sin enviar ni registrar), --to CORREO "
        "(todo a esa dirección, sin registrar) o --enviar (envío real con registro en "
        "Notificacion). Aún no evita envíos repetidos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Muestra destinatario, asunto y texto de cada correo; no envía ni registra nada.",
        )
        parser.add_argument(
            "--to", metavar="CORREO",
            help="Envía todos los correos a esta dirección, con prefijo de prueba; no registra nada.",
        )
        parser.add_argument(
            "--enviar", action="store_true",
            help="Envío real a los correos de los destinatarios, con registro en Notificacion.",
        )
        agregar_argumentos_de_seleccion(parser)

    def handle(self, *args, **options):
        modos = [options["dry_run"], options["to"] is not None, options["enviar"]]
        if sum(modos) != 1:
            raise CommandError("Indica exactamente un modo: --dry-run, --to CORREO o --enviar.")
        destino = None
        if options["to"] is not None:
            destino = options["to"].strip()
            try:
                validate_email(destino)
            except ValidationError:
                raise CommandError(f"--to: {destino!r} no es un correo válido.")

        hoy = options["hoy"] or timezone.localdate()
        destinatarios = seleccionar_destinatarios(options["email"])
        if options["dry_run"]:
            modo = "simulación: no se envía ni se registra nada"
        elif destino:
            modo = f"prueba: todos los correos a {destino}, sin registrar"
        else:
            modo = "envío real, con registro"
        self.stdout.write(f"Resúmenes de alertas al {hoy:%d/%m/%Y} ({modo}).")
        if periodo_actual(hoy) is None:
            self.stdout.write(f"No hay período académico para el año {hoy.year}.")

        if options["dry_run"]:
            self._simular(destinatarios, hoy)
        else:
            self._enviar(destinatarios, hoy, destino)

    def _simular(self, destinatarios, hoy):
        resumenes = construir_resumenes(destinatarios, hoy)
        generados = sin_correo = 0
        for resumen in resumenes:
            funcionario = resumen.funcionario
            self.stdout.write("")
            correo_real = (funcionario.email or "").strip()
            if not correo_real:
                sin_correo += 1
                self.stdout.write(f"Para: {funcionario.nombre} (sin correo): no se enviaría.")
                continue
            generados += 1
            correo = renderizar_correo(resumen)
            self.stdout.write(f"Para: {funcionario.nombre} <{correo_real}>")
            self.stdout.write(f"Asunto: {correo.asunto}")
            self.stdout.write("")
            self.stdout.write(correo.texto.rstrip("\n"))
        self.stdout.write("")
        self.stdout.write(
            f"Generados: {generados}. Sin correo: {sin_correo}. "
            f"Sin contenido: {len(destinatarios) - len(resumenes)}."
        )

    def _enviar(self, destinatarios, hoy, destino):
        resultado = enviar_resumenes(destinatarios, hoy=hoy, destino=destino)
        for envio in resultado.detalle:
            etiqueta = ETIQUETAS_RESULTADO.get(envio.resultado)
            if etiqueta:
                funcionario = envio.funcionario
                self.stdout.write(f"{etiqueta}: {funcionario.nombre} <{funcionario.email}>")
        self.stdout.write("")
        self.stdout.write(
            f"Enviados: {resultado.enviados}. Fallidos: {resultado.fallidos}. "
            f"Sin correo: {resultado.sin_correo}. Sin contenido: {resultado.sin_contenido}."
        )
        if resultado.fallidos:
            raise CommandError(
                f"Hubo {resultado.fallidos} envío(s) fallido(s); el detalle está en el log."
            )
