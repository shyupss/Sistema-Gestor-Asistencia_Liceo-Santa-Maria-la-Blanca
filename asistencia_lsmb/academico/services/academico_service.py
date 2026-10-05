from academico.queries.academico_queries import obtener_asistencia_curso


def clasificar_asistencia(porcentaje, estados):
    return next(
        (estado for estado in estados if porcentaje >= estado.umbral_minimo),
        estados[-1] if estados else None,
    )


def porcentaje_asistencia(total, ausencias):
    return (
        round((total - ausencias) * 100 / total)
        if total
        else None
    )


def promedio_asistencia(alumnos):
    porcentajes = [
        porcentaje_asistencia(alumno["total"], alumno["ausencias"])
        for alumno in alumnos
        if alumno["total"]
    ]
    return round(sum(porcentajes) / len(porcentajes)) if porcentajes else None


def preparar_alumnos(alumnos, estados):
    alumnos_con_datos = []
    for alumno in alumnos:
        if alumno.estado_alumno_porcentaje is not None:
            alumno.porcentaje_asistencia = round(
                float(alumno.estado_alumno_porcentaje)
            )
            alumno.estado_asistencia = alumno.estado_alumno_nombre or "Sin configurar"
            alumno.genera_alerta = bool(alumno.estado_alumno_alerta)
        else:
            alumno.porcentaje_asistencia = None
            alumno.estado_asistencia = "Sin datos"
            alumno.genera_alerta = False
        alumnos_con_datos.append(alumno)

    conteo_estados = {estado.nombre: 0 for estado in estados}
    conteo_estados.update({"Sin datos": 0, "Sin configurar": 0})
    for alumno in alumnos_con_datos:
        conteo_estados[alumno.estado_asistencia] += 1

    total_registros = sum(alumno.total_asistencias for alumno in alumnos_con_datos)
    total_ausencias = sum(alumno.total_ausencias for alumno in alumnos_con_datos)
    porcentaje_general = round(
        (total_registros - total_ausencias) * 100 / total_registros
    ) if total_registros else 0
    estudiante_alerta = sum(
        alumno.genera_alerta for alumno in alumnos_con_datos
    )
    porcentaje_alertas = round(
        estudiante_alerta * 100 / len(alumnos_con_datos)
    ) if alumnos_con_datos else 0

    return alumnos_con_datos, {
        "alertas": conteo_estados,
        "total": len(alumnos_con_datos),
        "estudiante_alerta": estudiante_alerta,
        "porcentaje_general": porcentaje_general,
        "porcentaje_alertas": porcentaje_alertas,
    }


def preparar_cursos(cursos, fecha, estados):
    cursos = list(cursos)
    for curso in cursos:
        alumno_ids = [
            matricula.alumno_id
            for matricula in curso.matriculas_activas
        ]
        datos_asistencia = obtener_asistencia_curso(curso, fecha, alumno_ids)
        curso.total_registros = datos_asistencia["total"]
        curso.total_ausencias = datos_asistencia["ausencias"]
        curso.asistencia = promedio_asistencia(
            datos_asistencia["porcentajes_alumnos"]
        ) or 0

        if curso.total_registros:
            estado = clasificar_asistencia(curso.asistencia, estados)
            curso.estado_asistencia = estado.nombre if estado else "Sin configurar"
            curso.genera_alerta = estado.genera_alerta if estado else False
        else:
            curso.estado_asistencia = "Sin datos"
            curso.genera_alerta = False

    conteo_estados = {estado.nombre: 0 for estado in estados}
    conteo_estados.update({"Sin datos": 0, "Sin configurar": 0})
    for curso in cursos:
        conteo_estados[curso.estado_asistencia] += 1

    total_registros = sum(curso.total_registros for curso in cursos)
    total_ausencias = sum(curso.total_ausencias for curso in cursos)
    porcentaje_general = round(
        (total_registros - total_ausencias) * 100 / total_registros
    ) if total_registros else 0
    total_cursos = len(cursos)
    porcentaje_meta = 75
    cursos_sobre_meta = sum(
        curso.asistencia >= porcentaje_meta for curso in cursos
    )
    cumplimiento_meta = round(
        cursos_sobre_meta * 100 / total_cursos
    ) if total_cursos else 0

    return cursos, {
        "alertas": conteo_estados,
        "total": total_cursos,
        "porcentaje_general": porcentaje_general,
        "porcentaje_meta": porcentaje_meta,
        "cursos_sobre_meta": cursos_sobre_meta,
        "cumplimiento_meta": cumplimiento_meta,
    }
