"""Motor de alertas: mantiene la alerta vigente de un alumno en un período al día con su estado.

Hay una alerta vigente (fecha_cierre nula) mientras el estado del alumno es no
ideal (Estado.es_no_ideal); el índice único uq_alerta_vigente_alumno_periodo
garantiza que no haya dos. No depende de nombres de estados.
"""
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from academico.models import Matricula
from alertas.models import Alerta, EstadoAlumno

CREADA = "creada"
CAMBIO_ESTADO = "cambio_estado"
RECUPERADA = "recuperada"
SIN_CAMBIO = "sin_cambio"

MOTIVO_RECUPERADO = "recuperado"
MOTIVO_CAMBIO_ESTADO = "cambio_estado"
MOTIVO_FIN_PERIODO = "fin_periodo"
MOTIVO_FIN_MATRICULA = "fin_matricula"
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


def barrido_cierres(ahora=None, periodo=None):
    """Cierra las alertas vigentes cuyo período terminó o cuyo alumno ya no está matriculado.

    1. fin_periodo: periodo.fecha_fin < hoy (un período que termina hoy aún no).
    2. fin_matricula: de las que quedan, el alumno no tiene matrícula activa en
       el período de la alerta (misma definición que S1: fecha_termino nula o
       posterior a hoy). Un cambio de curso dentro del período no la cierra.
    Si aplican ambos motivos gana fin_periodo. Cierra revisadas y no revisadas,
    con fecha_cierre = `ahora` (por defecto timezone.now()). `periodo` (instancia
    o id) limita el barrido. Idempotente.
    Devuelve {"fin_periodo": n, "fin_matricula": m}.
    """
    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    vigentes = Alerta.objects.filter(fecha_cierre__isnull=True)
    if periodo is not None:
        vigentes = vigentes.filter(periodo=periodo)
    matricula_activa = Matricula.objects.filter(
        alumno=OuterRef("alumno_id"), periodo=OuterRef("periodo_id"),
    ).filter(Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=hoy))

    with transaction.atomic():
        # Updates condicionados a fecha_cierre nula: lo que cierra el paso 1 (o
        # sincronizar_alerta en paralelo) ya no entra en el paso 2.
        fin_periodo = vigentes.filter(periodo__fecha_fin__lt=hoy).update(
            fecha_cierre=ahora, motivo_cierre=MOTIVO_FIN_PERIODO,
        )
        fin_matricula = (
            vigentes.filter(periodo__fecha_fin__gte=hoy)
            .filter(~Exists(matricula_activa))
            .update(fecha_cierre=ahora, motivo_cierre=MOTIVO_FIN_MATRICULA)
        )
    return {MOTIVO_FIN_PERIODO: fin_periodo, MOTIVO_FIN_MATRICULA: fin_matricula}


def reconciliar_alertas(periodo=None, ahora=None):
    """Sincroniza la alerta de cada EstadoAlumno de los períodos no terminados (fecha_fin >= hoy).

    Sirve de backfill (crea las alertas que faltan) y de red de seguridad (cierra
    las que ya no corresponden). `periodo` (instancia o id) la limita a ese
    período; si ya terminó, no hace nada. Recorre en orden de id y cada alumno
    se sincroniza en su propia transacción; una excepción se propaga.
    Idempotente. Devuelve {"creada": n, "cambio_estado": n, "recuperada": n, "sin_cambio": n}.
    """
    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    estados = EstadoAlumno.objects.filter(periodo__fecha_fin__gte=hoy)
    if periodo is not None:
        estados = estados.filter(periodo=periodo)
    conteo = dict.fromkeys((CREADA, CAMBIO_ESTADO, RECUPERADA, SIN_CAMBIO), 0)
    for estado_alumno in estados.select_related("alumno", "periodo").order_by("pk").iterator():
        resultado = sincronizar_alerta(estado_alumno.alumno, estado_alumno.periodo, ahora=ahora)
        conteo[resultado] += 1
    return conteo
