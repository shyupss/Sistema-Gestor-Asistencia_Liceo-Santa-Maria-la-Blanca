from alertas.models import Estado


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

        curso.pendiente = curso.registros_hoy < curso.total_estudiantes

    return cursos, {
        "alertas": contar_alertas(cursos),
    }


def contar_alertas(cursos):
    conteo = {}

    for curso in cursos:
        estado = curso.estado_asistencia
        conteo[estado] = conteo.get(estado, 0) + 1

    return conteo