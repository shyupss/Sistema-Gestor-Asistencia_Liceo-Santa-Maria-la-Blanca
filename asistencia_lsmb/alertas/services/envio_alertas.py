"""Correo de alertas: arma el mensaje desde un ResumenDestinatario, lo envía y registra la Notificacion.

Todavía no hay programación automática ni protección contra envíos repetidos
(paso 4): cada llamada envía.
"""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from alertas.models import Funcionario, Notificacion, NotificacionCurso
from alertas.queries.destinatario_queries import funcionarios_con_permiso
from alertas.services.alertas_service import PERMISO_REVISAR_ALERTAS
from alertas.services.formato import formatear_nivel, formatear_porcentaje
from alertas.services.resumen_alertas import construir_resumenes

logger = logging.getLogger(__name__)

ENVIADO = "enviado"
FALLIDO = "fallido"
SIN_CORREO = "sin_correo"
SIN_CONTENIDO = "sin_contenido"

CANAL = "email"
# Pantalla donde se ven las alertas (alertas/urls.py). Si no existe, el link va a la raíz.
URL_ALERTAS = "alertas"
TEMPLATE_TEXTO = "alertas/correo/resumen.txt"
TEMPLATE_HTML = "alertas/correo/resumen.html"


@dataclass(frozen=True)
class CorreoRenderizado:
    asunto: str
    texto: str
    html: str


@dataclass(frozen=True)
class EnvioFuncionario:
    funcionario: Funcionario
    resultado: str  # ENVIADO, FALLIDO, SIN_CORREO o SIN_CONTENIDO


@dataclass(frozen=True)
class ResultadoEnvio:
    enviados: int
    fallidos: int
    sin_correo: int
    sin_contenido: int
    detalle: tuple[EnvioFuncionario, ...]


def _cantidad(numero, singular, plural):
    return f"{numero} {singular if numero == 1 else plural}"


def link_al_sistema():
    """SITE_BASE_URL (sin barra final) más la ruta de las alertas; "" si SITE_BASE_URL está vacío."""
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        return ""
    try:
        ruta = reverse(URL_ALERTAS)
    except NoReverseMatch:
        ruta = "/"
    return base + ruta


def _contexto(resumen, asunto):
    alumnos = _cantidad(resumen.total_alumnos, "alumno", "alumnos")
    cursos = _cantidad(resumen.total_cursos, "curso", "cursos")
    return {
        "asunto": asunto,
        "nombre": resumen.funcionario.nombre,
        "frase_total": f"Tienes {alumnos} con alertas sin revisar en {cursos}.",
        "cursos": [
            {
                "etiqueta": curso.nombre,
                "total": _cantidad(curso.total_alumnos, "alumno", "alumnos"),
                "alumnos": [
                    {
                        "nombre": alumno.nombre,
                        "estado": alumno.estado,
                        "nivel": formatear_nivel(alumno.nivel),
                        "critico": alumno.nivel == "critico",
                        "porcentaje": formatear_porcentaje(alumno.porcentaje),
                        "fecha": alumno.fecha_alerta.strftime("%d/%m/%Y"),
                    }
                    for alumno in curso.alumnos
                ],
                "restantes": curso.restantes,
            }
            for curso in resumen.cursos
        ],
        "link": link_al_sistema(),
    }


def renderizar_correo(resumen):
    """Asunto, texto plano y HTML del correo de un ResumenDestinatario.

    El asunto no lleva nombres de alumnos. El HTML se renderiza con autoescape;
    el texto plano, sin escapar.
    """
    asunto = (
        "Alertas de asistencia: "
        f"{_cantidad(resumen.total_alumnos, 'alumno', 'alumnos')} en "
        f"{_cantidad(resumen.total_cursos, 'curso', 'cursos')}"
    )
    contexto = _contexto(resumen, asunto)
    return CorreoRenderizado(
        asunto=asunto,
        texto=render_to_string(TEMPLATE_TEXTO, contexto),
        html=render_to_string(TEMPLATE_HTML, contexto),
    )


def _registrar(resumen, ahora):
    with transaction.atomic():
        notificacion = Notificacion.objects.create(
            funcionario=resumen.funcionario, canal=CANAL, fecha_envio=ahora,
        )
        NotificacionCurso.objects.bulk_create([
            NotificacionCurso(notificacion=notificacion, curso=curso.curso)
            for curso in resumen.cursos
        ])


def enviar_resumen(resumen, ahora=None, destino=None):
    """Envía el correo del resumen y, si sale bien y no hay `destino`, registra la Notificacion.

    Con `destino`, el correo va a esa dirección con el prefijo "[PRUEBA para
    <correo real>]" y no se registra nada. Devuelve ENVIADO, FALLIDO o SIN_CORREO.
    """
    funcionario = resumen.funcionario
    correo_real = (funcionario.email or "").strip()
    para = (destino or "").strip() or correo_real
    if not para:
        logger.warning("El funcionario %s no tiene correo: no se envía su resumen de alertas.", funcionario.pk)
        return SIN_CORREO

    correo = renderizar_correo(resumen)
    asunto = correo.asunto
    if destino:
        asunto = f"[PRUEBA para {correo_real or 'sin correo'}] {asunto}"
    mensaje = EmailMultiAlternatives(
        subject=asunto, body=correo.texto, from_email=settings.DEFAULT_FROM_EMAIL, to=[para],
    )
    mensaje.attach_alternative(correo.html, "text/html")
    try:
        mensaje.send(fail_silently=False)
    except Exception:
        logger.exception("Falló el envío del resumen de alertas al funcionario %s.", funcionario.pk)
        return FALLIDO

    if not destino:
        try:
            _registrar(resumen, ahora or timezone.now())
        except Exception:
            # El correo ya salió: no se reintenta.
            logger.exception(
                "El resumen de alertas se envió al funcionario %s, pero no se pudo registrar "
                "la notificación.", funcionario.pk,
            )
    return ENVIADO


def enviar_resumenes(funcionarios=None, hoy=None, ahora=None, destino=None):
    """Envía el resumen a cada destinatario con contenido y devuelve un ResultadoEnvio.

    `funcionarios` por defecto son los de funcionarios_con_permiso(PERMISO_REVISAR_ALERTAS);
    el detalle va ordenado por id. Un fallo con un destinatario no detiene a los demás.
    """
    hoy = hoy or timezone.localdate()
    if funcionarios is None:
        funcionarios = funcionarios_con_permiso(PERMISO_REVISAR_ALERTAS)
    funcionarios = sorted(funcionarios, key=lambda funcionario: funcionario.pk)
    resumenes = {resumen.funcionario.pk: resumen for resumen in construir_resumenes(funcionarios, hoy)}

    detalle = []
    for funcionario in funcionarios:
        resumen = resumenes.get(funcionario.pk)
        if resumen is None:
            resultado = SIN_CONTENIDO
        else:
            try:
                resultado = enviar_resumen(resumen, ahora, destino)
            except Exception:
                logger.exception("Falló el resumen de alertas del funcionario %s.", funcionario.pk)
                resultado = FALLIDO
        detalle.append(EnvioFuncionario(funcionario=funcionario, resultado=resultado))

    def contar(resultado):
        return sum(envio.resultado == resultado for envio in detalle)

    return ResultadoEnvio(
        enviados=contar(ENVIADO),
        fallidos=contar(FALLIDO),
        sin_correo=contar(SIN_CORREO),
        sin_contenido=contar(SIN_CONTENIDO),
        detalle=tuple(detalle),
    )
