from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, Q

from alertas.models import Estado
from alertas.models import EstadoAlumno, HistorialEstadoAlumno
from asistencia.models import Asistencia_Alumnos


def clasificar_asistencia(porcentaje, estados):
    return next(
        (
            estado
            for estado in estados
            if porcentaje >= estado.umbral_minimo
        ),
        estados[-1] if estados else None,
    )


def preparar_cursos(cursos):
    estados = list(Estado.objects.order_by("-umbral_minimo"))

    for curso in cursos:
        curso.asistencia = (
            round(
                (curso.total_registros - curso.total_ausencias)
                * 100
                / curso.total_registros
            )
            if curso.total_registros
            else 0
        )

        estado = clasificar_asistencia(curso.asistencia, estados)

        if estado and curso.total_registros:
            curso.estado_asistencia = estado.nombre
            curso.genera_alerta = estado.genera_alerta
        else:
            curso.estado_asistencia = "Sin datos"
            curso.genera_alerta = False

        curso.pendiente = not curso.registrada_hoy

    return cursos, {
        "alertas": contar_alertas(cursos),
    }


def contar_alertas(cursos):
    conteo = {}

    for curso in cursos:
        estado = curso.estado_asistencia
        conteo[estado] = conteo.get(estado, 0) + 1

    return conteo


def recalcular_estado_alumno(alumno, periodo):
    resumen = Asistencia_Alumnos.objects.filter(
        alumno=alumno,
        paso_lista__curso__periodo=periodo,
    ).aggregate(
        total=Count("id"),
        ausencias=Count(
            "id",
            filter=Q(tipo_asistencia__cuenta_como_ausencia=True),
        ),
    )

    total = resumen["total"] or 0
    ausencias = resumen["ausencias"] or 0
    porcentaje = (
        (Decimal(total - ausencias) * Decimal("100") / Decimal(total))
        .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total
        else Decimal("0.00")
    )

    estado = clasificar_asistencia(
        porcentaje,
        list(Estado.objects.order_by("-umbral_minimo")),
    )
    if estado is None:
        return None

    estado_anterior = EstadoAlumno.objects.filter(
        alumno=alumno,
        periodo=periodo,
    ).first()
    estado_alumno, creado = EstadoAlumno.objects.update_or_create(
        alumno=alumno,
        periodo=periodo,
        defaults={
            "estado": estado,
            "porcentaje_asistencia": porcentaje,
        },
    )

    if creado or estado_anterior.estado_id != estado.id:
        HistorialEstadoAlumno.objects.create(
            alumno=alumno,
            periodo=periodo,
            estado_nuevo=estado,
            estado_anterior=estado_anterior.estado if estado_anterior else None,
        )

    return estado_alumno