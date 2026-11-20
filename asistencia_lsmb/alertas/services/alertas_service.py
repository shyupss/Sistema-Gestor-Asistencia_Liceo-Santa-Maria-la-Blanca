"""Motor de alertas: mantiene la alerta vigente de un alumno en un período al día con su estado.

Hay una alerta vigente (fecha_cierre nula) mientras el estado del alumno es no
ideal (Estado.es_no_ideal); el índice único uq_alerta_vigente_alumno_periodo
garantiza que no haya dos. No depende de nombres de estados.
"""
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from alertas.models import Alerta, EstadoAlumno
from alertas.queries.alcance_queries import (
    curso_del_alumno_en_periodo,
    cursos_en_alcance,
    tiene_permiso,
)
from alertas.queries.matricula_queries import matriculas_activas

CREADA = "creada"
CAMBIO_ESTADO = "cambio_estado"
RECUPERADA = "recuperada"
SIN_CAMBIO = "sin_cambio"

MOTIVO_RECUPERADO = "recuperado"
MOTIVO_CAMBIO_ESTADO = "cambio_estado"
MOTIVO_FIN_PERIODO = "fin_periodo"
MOTIVO_FIN_MATRICULA = "fin_matricula"
MOTIVOS_VALIDOS = {motivo for motivo, _ in Alerta.MOTIVOS_CIERRE}

PERMISO_REVISAR_ALERTAS = "revisar_alertas"
NOTA_MAXIMA = 1000


class AlertaError(Exception):
    """Base de los errores al revisar una alerta."""


class SinPermiso(AlertaError):
    """El funcionario no tiene acceso o su rol no tiene el permiso de revisar alertas."""


class FueraDeAlcance(AlertaError):
    """El curso del alumno no está entre los cursos que ve el funcionario."""


class NotaInvalida(AlertaError):
    """La nota no es texto o supera NOTA_MAXIMA caracteres (ya recortada)."""


class AlertaCerrada(AlertaError):
    """La alerta ya no está vigente."""


class AlertaYaRevisada(AlertaError):
    """La alerta ya fue revisada."""


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
    return matriculas_activas(hoy).filter(alumno=alumno, periodo=periodo).exists()


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
    matricula_activa = matriculas_activas(hoy).filter(
        alumno=OuterRef("alumno_id"), periodo=OuterRef("periodo_id"),
    )

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


def _normalizar_nota(nota):
    if nota is None:
        return None
    if not isinstance(nota, str):
        raise NotaInvalida("La nota debe ser texto.")
    nota = nota.strip()
    if len(nota) > NOTA_MAXIMA:
        raise NotaInvalida(f"La nota no puede superar {NOTA_MAXIMA} caracteres.")
    return nota or None


def marcar_revisada(alerta, funcionario, nota=None, ahora=None):
    """Marca la alerta como revisada por `funcionario` y devuelve la alerta actualizada.

    Verifica, en este orden: permiso (SinPermiso), que el curso del alumno en el
    período esté en el alcance del funcionario (FueraDeAlcance), la nota
    (NotaInvalida: se recorta y vacía queda en None) y, con la alerta bloqueada,
    que siga vigente (AlertaCerrada) y sin revisar (AlertaYaRevisada).
    `ahora` (por defecto timezone.now()) es la fecha de revisión y define "hoy".
    No cierra la alerta, no cambia EstadoAlumno ni toca otras alertas. Devuelve
    la alerta releída de la BD; la instancia recibida no se modifica.
    """
    ahora = ahora or timezone.now()
    hoy = timezone.localdate(ahora)
    if not tiene_permiso(funcionario, PERMISO_REVISAR_ALERTAS):
        raise SinPermiso("El funcionario no tiene permiso para revisar alertas.")
    curso = curso_del_alumno_en_periodo(alerta.alumno_id, alerta.periodo_id, hoy)
    if curso is None or not cursos_en_alcance(funcionario, alerta.periodo_id).filter(pk=curso.pk).exists():
        raise FueraDeAlcance("El curso del alumno no está en el alcance del funcionario.")
    nota = _normalizar_nota(nota)

    with transaction.atomic():
        actual = Alerta.objects.select_for_update().get(pk=alerta.pk)
        if actual.fecha_cierre is not None:
            raise AlertaCerrada("La alerta está cerrada.")
        if actual.revisada:
            raise AlertaYaRevisada("La alerta ya fue revisada.")
        actual.revisada = True
        actual.funcionario_revisa = funcionario
        actual.fecha_revision = ahora
        actual.nota = nota
        actual.save(update_fields=["revisada", "funcionario_revisa", "fecha_revision", "nota"])
    return actual
