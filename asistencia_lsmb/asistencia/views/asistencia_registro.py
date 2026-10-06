from datetime import time

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode

from academico.models import Curso
from alertas.models import Funcionario
from asistencia.models import (
    Asistencia_Alumnos,
    Paso_Lista,
)
from asistencia.queries.asistencia_queries import (
    obtener_alumnos_curso,
    obtener_asistencias,
    obtener_paso_lista,
    obtener_tipos_asistencia,
)
from asistencia.services.asistencia_service import recalcular_estado_alumno


def pagina_registrar_asistencia(request):
    fecha = request.GET.get("fecha") or request.POST.get("fecha")
    try:
        fecha = timezone.datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else timezone.localdate()
    except ValueError:
        fecha = timezone.localdate()
    curso_id = request.GET.get("curso") or request.POST.get("curso")
    jornada = request.GET.get("jornada") or request.POST.get("jornada") or "unica"

    cursos = Curso.objects.filter(
        periodo__anio=fecha.year,
    ).order_by("nivel", "grupo")
    tipos_asistencia = list(obtener_tipos_asistencia())
    funcionarios = Funcionario.objects.filter(activo=True).order_by("nombre")

    curso = None
    alumnos = []
    paso_lista = None
    errores_registro = []

    if curso_id:
        curso = get_object_or_404(cursos, pk=curso_id)
        alumnos = list(obtener_alumnos_curso(curso, fecha))
        paso_lista = obtener_paso_lista(curso, fecha, jornada)

    if request.method == "POST":
        funcionario_id = request.POST.get("funcionario")
        if not curso or not funcionario_id:
            errores_registro.append("Selecciona un curso y un funcionario.")
        else:
            funcionario = get_object_or_404(
                funcionarios,
                pk=funcionario_id,
            )
            tipos = {tipo.nombre.casefold(): tipo for tipo in tipos_asistencia}
            tipo_presente = tipos.get("presente")
            tipo_ausente = tipos.get("ausente")
            tipo_atrasado = tipos.get("atrasado")
            presentes = set(request.POST.getlist("presentes"))
            error = None
            if not tipo_presente or not tipo_ausente:
                error = "Carga los tipos presente y ausente desde Administración."
            elif tipo_presente.cuenta_como_ausencia or not tipo_ausente.cuenta_como_ausencia:
                error = "Revisa las reglas de presente y ausente desde Administración."

            # Solo se admiten las dos opciones del paso de lista, incluso por POST.
            for matricula in alumnos:
                tipo_id = request.POST.get(f"alumno_{matricula.alumno_id}")
                if tipo_id:
                    if tipo_presente and tipo_id == str(tipo_presente.pk):
                        presentes.add(str(matricula.alumno_id))
                    elif tipo_ausente and tipo_id == str(tipo_ausente.pk):
                        presentes.discard(str(matricula.alumno_id))
                    else:
                        error = "Al pasar lista solo puedes marcar presente o ausente."
                        break

            despues_del_corte = timezone.localtime().time() > time(9, 30)
            tipos_por_id = {tipo.pk: tipo for tipo in tipos_asistencia}
            anteriores = obtener_asistencias(paso_lista) if paso_lista else {}
            asignaciones = {}
            if not error:
                for matricula in alumnos:
                    tipo = tipo_ausente
                    if str(matricula.alumno_id) in presentes:
                        anterior = tipos_por_id.get(anteriores.get(matricula.alumno_id))
                        if anterior and (not anterior.cuenta_como_ausencia or anterior.nombre.casefold() == "atrasado"):
                            # Guardar otra vez no cambia la llegada ya registrada.
                            tipo = anterior
                        elif despues_del_corte:
                            if not tipo_atrasado or not tipo_atrasado.cuenta_como_ausencia:
                                error = "Carga el tipo atrasado, que cuenta como ausencia, desde Administración."
                                break
                            tipo = tipo_atrasado
                        else:
                            tipo = tipo_presente
                    asignaciones[matricula.alumno_id] = tipo

            if error:
                errores_registro.append(error)
            else:
                with transaction.atomic():
                    paso_lista, _ = Paso_Lista.objects.update_or_create(
                        curso=curso,
                        fecha=fecha,
                        jornada=jornada,
                        defaults={"funcionario": funcionario},
                    )
                    for matricula in alumnos:
                        Asistencia_Alumnos.objects.update_or_create(
                            paso_lista=paso_lista,
                            alumno=matricula.alumno,
                            defaults={"tipo_asistencia": asignaciones[matricula.alumno_id]},
                        )
                        recalcular_estado_alumno(
                            alumno=matricula.alumno,
                            periodo=curso.periodo,
                        )

                messages.success(request, "La asistencia fue guardada correctamente.")
                query = urlencode({
                    "curso": curso.pk,
                    "fecha": fecha.isoformat(),
                    "jornada": jornada,
                    "guardado": 1,
                })
                return redirect(f"{reverse('registrar_asistencia')}?{query}")

    asistencias_guardadas = {}
    if paso_lista:
        asistencias_guardadas = obtener_asistencias(paso_lista)
        tipos_por_id = {tipo.pk: tipo for tipo in tipos_asistencia}
        alumnos_por_id = {matricula.alumno_id: matricula for matricula in alumnos}
        registro_presentes = []
        registro_ausentes = []
        registro_atrasados = []

        for alumno_id, tipo_id in asistencias_guardadas.items():
            matricula = alumnos_por_id.get(alumno_id)
            tipo = tipos_por_id.get(tipo_id)
            if not matricula or not tipo:
                continue
            if tipo.nombre.casefold() == "atrasado":
                registro_atrasados.append(matricula)
            elif tipo.cuenta_como_ausencia:
                registro_ausentes.append(matricula)
            else:
                registro_presentes.append(matricula)

        tipos_presentes = {
            tipo.pk for tipo in tipos_asistencia
            if not tipo.cuenta_como_ausencia or tipo.nombre.casefold() == "atrasado"
        }
        for matricula in alumnos:
            matricula.tipo_asistencia_id = asistencias_guardadas.get(
                matricula.alumno_id
            )
            tipo_guardado = tipos_por_id.get(matricula.tipo_asistencia_id)
            matricula.es_atrasado = bool(tipo_guardado and tipo_guardado.nombre.casefold() == "atrasado")
            matricula.es_presente = (
                matricula.tipo_asistencia_id in tipos_presentes
            )
    else:
        registro_presentes = []
        registro_ausentes = []
        registro_atrasados = []

    total_alumnos = len(alumnos)
    progreso = round(len(asistencias_guardadas) * 100 / total_alumnos) if total_alumnos else 0

    return render(
        request,
        "asistencia/registrar.html",
        {
            "cursos": cursos,
            "errores_registro": errores_registro,
            "curso": curso,
            "alumnos": alumnos,
            "tipos_asistencia": tipos_asistencia,
            "funcionarios": funcionarios,
            "fecha": fecha,
            "jornada": jornada,
            "asistencias_guardadas": asistencias_guardadas,
            "total_alumnos": total_alumnos,
            "asistencias_registradas": len(asistencias_guardadas),
            "progreso": progreso,
            "registro_presentes": registro_presentes,
            "registro_ausentes": registro_ausentes,
            "registro_atrasados": registro_atrasados,
        },
    )