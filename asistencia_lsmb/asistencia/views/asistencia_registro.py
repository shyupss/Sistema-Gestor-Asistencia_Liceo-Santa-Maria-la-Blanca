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

    if curso_id:
        curso = get_object_or_404(cursos, pk=curso_id)
        alumnos = list(obtener_alumnos_curso(curso))
        paso_lista = obtener_paso_lista(curso, fecha, jornada)

    if request.method == "POST":
        funcionario_id = request.POST.get("funcionario")
        if not curso or not funcionario_id:
            messages.error(request, "Selecciona un curso y un funcionario.")
        else:
            funcionario = get_object_or_404(
                funcionarios,
                pk=funcionario_id,
            )
            tipos = {str(tipo.pk): tipo for tipo in tipos_asistencia}
            tipo_ausente = next(
                (tipo for tipo in tipos_asistencia if tipo.cuenta_como_ausencia),
                None,
            )

            presentes = set(request.POST.getlist("presentes"))
            tipo_presente = next(
                (tipo for tipo in tipos_asistencia if not tipo.cuenta_como_ausencia),
                None,
            )

            for matricula in alumnos:
                tipo_id = request.POST.get(f"alumno_{matricula.alumno_id}")
                if not tipo_id and str(matricula.alumno_id) in presentes:
                    tipo_id = str(tipo_presente.pk) if tipo_presente else None
                if tipo_id not in tipos:
                    tipo_id = str(tipo_ausente.pk) if tipo_ausente else None
                if tipo_id is None:
                    messages.error(request, "Configura al menos un tipo de asistencia ausente.")
                    break
            else:
                with transaction.atomic():
                    paso_lista, _ = Paso_Lista.objects.update_or_create(
                        curso=curso,
                        fecha=fecha,
                        jornada=jornada,
                        defaults={"funcionario": funcionario},
                    )
                    for matricula in alumnos:
                        tipo_id = request.POST.get(f"alumno_{matricula.alumno_id}")
                        if not tipo_id and str(matricula.alumno_id) in presentes and tipo_presente:
                            tipo_id = str(tipo_presente.pk)
                        if tipo_id not in tipos:
                            tipo_id = str(tipo_ausente.pk)
                        Asistencia_Alumnos.objects.update_or_create(
                            paso_lista=paso_lista,
                            alumno=matricula.alumno,
                            defaults={"tipo_asistencia_id": tipo_id},
                        )

                messages.success(request, "La asistencia fue guardada correctamente.")
                query = urlencode({
                    "curso": curso.pk,
                    "fecha": fecha.isoformat(),
                    "jornada": jornada,
                })
                return redirect(
                    f"{reverse('registrar_asistencia')}?{query}"
                )

    asistencias_guardadas = {}
    if paso_lista:
        asistencias_guardadas = obtener_asistencias(paso_lista)
        for matricula in alumnos:
            matricula.tipo_asistencia_id = asistencias_guardadas.get(
                matricula.alumno_id
            )

    total_alumnos = len(alumnos)
    progreso = round(len(asistencias_guardadas) * 100 / total_alumnos) if total_alumnos else 0

    return render(
        request,
        "asistencia/registrar.html",
        {
            "cursos": cursos,
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
        },
    )