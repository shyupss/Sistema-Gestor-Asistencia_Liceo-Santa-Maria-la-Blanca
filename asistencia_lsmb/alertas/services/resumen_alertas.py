"""Qué recibe cada destinatario en el correo de alertas: cursos con alertas y una lista corta de alumnos.

Solo lectura: no envía nada ni escribe en la BD. Parte de las alertas sin revisar
de alertas_vigentes y aplica, por destinatario:
- rol con recibe_todos_los_cursos_marcados: todas, de cualquier curso y estado;
- si no: los cursos de cursos_en_alcance y los estados de EstadoNotificaRol del
  rol. Sin filas en EstadoNotificaRol no recibe nada.
"""
import datetime
from dataclasses import dataclass

from django.utils import timezone

from academico.models import Curso, PeriodoAcademico
from alertas.models import Funcionario
from alertas.queries.alcance_queries import cursos_en_alcance, tiene_permiso
from alertas.queries.alerta_queries import alertas_por_curso
from alertas.queries.destinatario_queries import (
    estados_que_notifica_el_rol,
    funcionarios_con_permiso,
)
from alertas.queries.periodo_queries import periodo_actual
from alertas.services.alertas_service import PERMISO_REVISAR_ALERTAS
from alertas.services.formato import etiqueta_curso

ALUMNOS_POR_CURSO = 5


@dataclass(frozen=True)
class AlumnoResumen:
    alerta_id: int
    nombre: str
    estado: str
    nivel: str  # "critico" o "atencion"
    porcentaje: float | None
    fecha_alerta: datetime.date  # fecha local de Alerta.fecha_creacion


@dataclass(frozen=True)
class CursoResumen:
    curso: Curso
    nombre: str
    total_alumnos: int
    alumnos: tuple[AlumnoResumen, ...]  # los primeros ALUMNOS_POR_CURSO
    restantes: int


@dataclass(frozen=True)
class ResumenDestinatario:
    funcionario: Funcionario
    periodo: PeriodoAcademico
    cursos: tuple[CursoResumen, ...]
    total_cursos: int
    total_alumnos: int


def _alumno(alerta):
    porcentaje = alerta.porcentaje_asistencia
    return AlumnoResumen(
        alerta_id=alerta.pk,
        nombre=alerta.alumno.nombre,
        estado=alerta.estado.nombre,
        nivel=alerta.nivel,
        porcentaje=None if porcentaje is None else float(porcentaje),
        fecha_alerta=timezone.localdate(alerta.fecha_creacion),
    )


def _curso(curso, alertas):
    listados = tuple(_alumno(alerta) for alerta in alertas[:ALUMNOS_POR_CURSO])
    return CursoResumen(
        curso=curso,
        nombre=etiqueta_curso(curso),
        total_alumnos=len(alertas),
        alumnos=listados,
        restantes=max(len(alertas) - len(listados), 0),
    )


def construir_resumen(funcionario, periodo=None, hoy=None):
    """ResumenDestinatario del funcionario, o None si no hay nada que enviarle.

    `periodo=None` usa periodo_actual(hoy); `hoy` por defecto es
    timezone.localdate(). Devuelve None si no hay período, si el funcionario no
    es destinatario (tiene_permiso con PERMISO_REVISAR_ALERTAS) o si no ve
    ningún curso con alertas sin revisar.
    """
    hoy = hoy or timezone.localdate()
    if periodo is None:
        periodo = periodo_actual(hoy)
    if periodo is None or not tiene_permiso(funcionario, PERMISO_REVISAR_ALERTAS):
        return None

    rol = funcionario.cuenta.rol
    if rol.recibe_todos_los_cursos_marcados:
        filtros = {}
    else:
        estados = estados_que_notifica_el_rol(rol)
        if not estados:
            return None
        filtros = {"cursos": cursos_en_alcance(funcionario, periodo), "estados": estados}

    # alertas_por_curso calcula el umbral del nivel una sola vez.
    grupos = alertas_por_curso(periodo, solo_sin_revisar=True, hoy=hoy, **filtros)
    if not grupos:
        return None
    cursos = tuple(_curso(curso, alertas) for curso, alertas in grupos)
    return ResumenDestinatario(
        funcionario=funcionario,
        periodo=periodo,
        cursos=cursos,
        total_cursos=len(cursos),
        total_alumnos=sum(curso.total_alumnos for curso in cursos),
    )


def construir_resumenes(funcionarios=None, hoy=None):
    """Resúmenes de los destinatarios con contenido, ordenados por id de funcionario.

    `funcionarios` por defecto son los de funcionarios_con_permiso(PERMISO_REVISAR_ALERTAS).
    El período se resuelve una sola vez; sin período devuelve [].
    """
    hoy = hoy or timezone.localdate()
    periodo = periodo_actual(hoy)
    if periodo is None:
        return []
    if funcionarios is None:
        funcionarios = funcionarios_con_permiso(PERMISO_REVISAR_ALERTAS)
    resumenes = (
        construir_resumen(funcionario, periodo, hoy)
        for funcionario in sorted(funcionarios, key=lambda funcionario: funcionario.pk)
    )
    return [resumen for resumen in resumenes if resumen is not None]
