"""Motor de alertas: mantiene la alerta vigente de un alumno en un período al día con su estado.

Hay una alerta vigente (fecha_cierre nula) mientras el estado del alumno es no
ideal (Estado.es_no_ideal); el índice único uq_alerta_vigente_alumno_periodo
garantiza que no haya dos. No depende de nombres de estados.
"""
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from academico.models import Matricula
from alertas.models import Alerta, EstadoAlumno

CREADA = "creada"
CAMBIO_ESTADO = "cambio_estado"
RECUPERADA = "recuperada"
SIN_CAMBIO = "sin_cambio"

MOTIVO_RECUPERADO = "recuperado"
MOTIVO_CAMBIO_ESTADO = "cambio_estado"
MOTIVOS_VALIDOS = {motivo for motivo, _ in Alerta.MOTIVOS_CIERRE}


def cerrar_alerta(alerta, motivo, ahora=None):
    """Cierra la alerta con `motivo` (uno de Alerta.MOTIVOS_CIERRE).

    ValueError si el motivo no es válido o si la alerta ya está cerrada (en la
    instancia o en la BD).
    """
    if motivo not in MOTIVOS_VALIDOS:
        raise ValueError(f"Motivo de cierre inválido: {motivo!r}.")
    if alerta.fecha_cierre is not None:
        raise ValueError("La alerta ya está cerrada.")
    fecha_cierre = ahora or timezone.now()
    actualizadas = Alerta.objects.filter(pk=alerta.pk, fecha_cierre__isnull=True).update(
        fecha_cierre=fecha_cierre, motivo_cierre=motivo,
    )
    if not actualizadas:
        raise ValueError("La alerta ya está cerrada.")
    alerta.fecha_cierre = fecha_cierre
    alerta.motivo_cierre = motivo


def _puede_crear(alumno, periodo, hoy):
    """S1: el período no terminó y el alumno tiene una matrícula activa hoy en ese período."""
    if hoy > periodo.fecha_fin:
        return False
    return Matricula.objects.filter(alumno=alumno, periodo=periodo).filter(
        Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=hoy),
    ).exists()


def _vigente_bloqueada(alumno, periodo):
    return (
        Alerta.objects.select_for_update()
        .filter(alumno=alumno, periodo=periodo, fecha_cierre__isnull=True)
        .first()
    )


def _crear(alumno, periodo, estado):
    Alerta.objects.create(alumno=alumno, periodo=periodo, estado=estado, revisada=False)


def _aplicar(alumno, periodo, estado, ahora):
    vigente = _vigente_bloqueada(alumno, periodo)
    hoy = timezone.localdate(ahora)

    if vigente is None:
        if estado.es_no_ideal and _puede_crear(alumno, periodo, hoy):
            _crear(alumno, periodo, estado)
            return CREADA
        return SIN_CAMBIO

    if not estado.es_no_ideal:
        # Incluye un Estado editado a ideal. Se cierra aunque esté revisada.
        cerrar_alerta(vigente, MOTIVO_RECUPERADO, ahora)
        return RECUPERADA

    if vigente.estado_id == estado.pk:
        return SIN_CAMBIO  # aunque esté revisada

    if not _puede_crear(alumno, periodo, hoy):
        return SIN_CAMBIO  # no se puede reemplazar: la vigente queda sin tocar
    cerrar_alerta(vigente, MOTIVO_CAMBIO_ESTADO, ahora)
    _crear(alumno, periodo, estado)
    return CAMBIO_ESTADO


def sincronizar_alerta(alumno, periodo, estado=None, ahora=None):
    """Ajusta la alerta vigente del alumno en el período a `estado`.

    Si `estado` es None se lee de EstadoAlumno; sin EstadoAlumno no hace nada.
    `ahora` (por defecto timezone.now()) define "hoy" y la fecha de cierre.
    Devuelve "creada", "cambio_estado", "recuperada" o "sin_cambio".
    """
    ahora = ahora or timezone.now()
    with transaction.atomic():
        if estado is None:
            estado_alumno = (
                EstadoAlumno.objects.select_related("estado")
                .filter(alumno=alumno, periodo=periodo)
                .first()
            )
            if estado_alumno is None:
                return SIN_CAMBIO
            estado = estado_alumno.estado
        try:
            # Savepoint: si el create choca con el índice único, se deshace solo lo de este intento.
            with transaction.atomic():
                return _aplicar(alumno, periodo, estado, ahora)
        except IntegrityError:
            # Otra transacción creó la vigente entre la lectura y el create:
            # se relee y se reevalúa una sola vez.
            return _aplicar(alumno, periodo, estado, ahora)
