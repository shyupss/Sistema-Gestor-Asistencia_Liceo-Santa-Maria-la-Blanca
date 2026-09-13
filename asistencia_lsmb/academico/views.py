from django.shortcuts import render
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Case, Count, ExpressionWrapper, F, FloatField, Prefetch, Q, Value, When
from datetime import timedelta
from .models import Alumno, Curso, Matricula #Importa modelos a cargar
from asistencia.models import Asistencia_Alumnos
from alertas.models import Estado
from babel.dates import format_date


def clasificar_asistencia(porcentaje, estados):
    return next(
        (estado for estado in estados if porcentaje >= estado.umbral_minimo),
        estados[-1] if estados else None,
    )


# Create your views here.
def pagina_alumnos(request):
    fecha_hoy = timezone.localdate()
    año_actual = fecha_hoy.year
    inicio_semana = fecha_hoy - timedelta(days=fecha_hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    inicio_año = fecha_hoy.replace(month=1, day=1)
    inicio_siguiente_año = inicio_año.replace(year=año_actual + 1)

    # Capturamos parámetros de búsqueda y paginación desde la URL
    search_query = request.GET.get('q', '')
    estado_filtro = request.GET.get('estado', '')
    try:
        per_page = int(request.GET.get('per_page', 12))
    except (TypeError, ValueError):
        per_page = 12
    if per_page not in {12, 24, 48}:
        per_page = 12
    orden = request.GET.get('orden', 'asc')
    if orden not in {'asc', 'desc'}:
        orden = 'asc'

    # Preparar consulta optimizada para traer solo matriculas vigentes
    # Incluye datos curso y periodo asociado (select_related)
    matriculas_activas = Prefetch(
        'matriculas',
        queryset=Matricula.objects.filter(
            fecha_termino__isnull=True,
            periodo__anio=año_actual
        ).select_related('curso', 'curso__periodo'),
        to_attr='matricula_activa_list'
    )
    # Consultamos todos los alumnos y le inyectamos la consulta de matriculas activas
    asistencia_del_año = Q(
        asistencia_alumnos__paso_lista__fecha__gte=inicio_año,
        asistencia_alumnos__paso_lista__fecha__lt=inicio_siguiente_año,
        asistencia_alumnos__paso_lista__curso__matriculas__alumno=F('pk'),
        asistencia_alumnos__paso_lista__curso__matriculas__periodo__anio=año_actual,
        asistencia_alumnos__paso_lista__curso__matriculas__fecha_termino__isnull=True,
    )
    alumnos_base = Alumno.objects.prefetch_related(matriculas_activas).annotate(
        total_asistencias=Count(
            'asistencia_alumnos',
            filter=asistencia_del_año,
            distinct=True,
        ),
        total_ausencias=Count(
            'asistencia_alumnos',
            filter=asistencia_del_año & Q(
                asistencia_alumnos__tipo_asistencia__cuenta_como_ausencia=True,
            ),
            distinct=True,
        ),
    ).annotate(
        porcentaje_asistencia=Case(
            When(
                total_asistencias__gt=0,
                then=ExpressionWrapper(
                    (F('total_asistencias') - F('total_ausencias'))
                    * Value(100.0) / F('total_asistencias'),
                    output_field=FloatField(),
                ),
            ),
            default=None,
            output_field=FloatField(),
        )
    )
    estados_asistencia = list(Estado.objects.order_by('-umbral_minimo'))

    alumnos_con_datos = []
    for alumno in alumnos_base:
        if alumno.total_asistencias:
            alumno.porcentaje_asistencia = round(
                (alumno.total_asistencias - alumno.total_ausencias)
                * 100
                / alumno.total_asistencias
            )
            estado = clasificar_asistencia(alumno.porcentaje_asistencia, estados_asistencia)
            alumno.estado_asistencia = estado.nombre if estado else 'Sin configurar'
            alumno.genera_alerta = estado.genera_alerta if estado else False
        else:
            alumno.porcentaje_asistencia = None
            alumno.estado_asistencia = 'Sin datos'
            alumno.genera_alerta = False
        alumnos_con_datos.append(alumno)

    alumnos_qs = alumnos_base

    # Si el usuario escribió algo en el buscador
    if search_query:
        alumnos_qs = alumnos_qs.filter(
            Q(nombre__icontains=search_query) |
            Q(rut__icontains=search_query) |
            Q(matriculas__curso__grupo__icontains=search_query)
        ).distinct()

    if estado_filtro:
        alumnos_qs = alumnos_qs.filter(
            pk__in=[
                alumno.pk for alumno in alumnos_con_datos
                if alumno.estado_asistencia == estado_filtro
            ]
        )

    alumnos_qs = alumnos_qs.order_by(
        F('porcentaje_asistencia').desc(nulls_last=True)
        if orden == 'desc'
        else F('porcentaje_asistencia').asc(nulls_last=True),
        'nombre',
    )

    # Paginación
    paginator = Paginator(alumnos_qs, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    alumnos_clasificados = {alumno.pk: alumno for alumno in alumnos_con_datos}

    for alumno in page_obj:
        clasificado = alumnos_clasificados[alumno.pk]
        alumno.porcentaje_asistencia = clasificado.porcentaje_asistencia
        alumno.estado_asistencia = clasificado.estado_asistencia
        alumno.genera_alerta = clasificado.genera_alerta

    conteo_estados = {estado.nombre: 0 for estado in estados_asistencia}
    conteo_estados.update({'Sin datos': 0, 'Sin configurar': 0})
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

    contexto = {
        'page_title': "Estudiantes",
        'page_obj': page_obj,
        'search_query': search_query,
        'estado_filtro': estado_filtro,
        'orden': orden,
        'per_page': per_page,
        'is_12': per_page == 12,
        'is_24': per_page == 24,
        'is_48': per_page == 48,
        'fecha_hoy': fecha_hoy,
        # 'inicio_semana': inicio_semana,
        # 'fin_semana': fin_semana,

        'inicio_semana': format_date(inicio_semana, format = "dd MMM", locale = "es"),
        'current_year': año_actual,
        'current_month': format_date(fecha_hoy, format = "MMMM", locale = "es").capitalize(),
        'fin_semana': format_date(fin_semana, format = "dd MMM", locale = "es"),
        'total': f"{len(alumnos_con_datos)} Estudiantes",
        'estudiante_alerta': estudiante_alerta,
        'porcentaje_general': porcentaje_general,
        'porcentaje_alertas': porcentaje_alertas,
        'pastillas': [
            (f"{len(alumnos_con_datos)} Estudiantes · Periodo actual", "azul"),
            (f"Estudiantes con alerta · {estudiante_alerta}", "amarillo")
        ],
        'alertas': conteo_estados,
    }

    return render (request, 'academico/base.html', contexto)


def pagina_cursos(request):
    fecha_hoy = timezone.localdate()
    año_actual = fecha_hoy.year
    inicio_semana = fecha_hoy - timedelta(days=fecha_hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    search_query = request.GET.get('q', '')
    estado_filtro = request.GET.get('estado', '')
    try:
        per_page = int(request.GET.get('per_page', 12))
    except (TypeError, ValueError):
        per_page = 12
    if per_page not in {12, 24, 48}:
        per_page = 12
    orden = request.GET.get('orden', 'curso')
    if orden not in {'curso', 'asc', 'desc'}:
        orden = 'curso'

    matriculas_activas = Prefetch(
        'matriculas',
        queryset=Matricula.objects.filter(
            periodo__anio=año_actual,
            fecha_termino__isnull=True,
        ).select_related('alumno'),
        to_attr='matriculas_activas',
    )

    cursos = Curso.objects.filter(
        periodo__anio=año_actual,
    ).order_by('nivel', 'grupo').prefetch_related(matriculas_activas).annotate(
        total_estudiantes=Count(
            'matriculas',
            filter=Q(
                matriculas__periodo__anio=año_actual,
                matriculas__fecha_termino__isnull=True,
            ),
            distinct=True,
        )
    )
    inicio_año = fecha_hoy.replace(month=1, day=1)
    inicio_siguiente_año = inicio_año.replace(year=año_actual + 1)
    for curso in cursos:
        asistencias = Asistencia_Alumnos.objects.filter(
            paso_lista__curso=curso,
            paso_lista__fecha__gte=inicio_año,
            paso_lista__fecha__lt=inicio_siguiente_año,
            alumno__matriculas__curso=curso,
            alumno__matriculas__periodo__anio=año_actual,
            alumno__matriculas__fecha_termino__isnull=True,
        )
        datos_asistencia = asistencias.aggregate(
            total=Count('pk', distinct=True),
            ausencias=Count(
                'pk',
                filter=Q(tipo_asistencia__cuenta_como_ausencia=True),
                distinct=True,
            ),
        )
        curso.total_registros = datos_asistencia['total']
        curso.total_ausencias = datos_asistencia['ausencias']
        curso.asistencia = round(
            (curso.total_registros - curso.total_ausencias) * 100
            / curso.total_registros
        ) if curso.total_registros else 0

    if orden in {'asc', 'desc'}:
        cursos = sorted(
            cursos,
            key=lambda curso: (
                curso.total_registros == 0,
                -curso.asistencia if orden == 'desc' else curso.asistencia,
            ),
        )

    estados_asistencia = list(Estado.objects.order_by('-umbral_minimo'))

    conteo_estados = {estado.nombre: 0 for estado in estados_asistencia}
    conteo_estados.update({'Sin datos': 0, 'Sin configurar': 0})

    for curso in cursos:
        if curso.total_registros:
            estado = clasificar_asistencia(curso.asistencia, estados_asistencia)
            curso.estado_asistencia = estado.nombre if estado else 'Sin configurar'
            curso.genera_alerta = estado.genera_alerta if estado else False
        else:
            curso.estado_asistencia = 'Sin datos'
            curso.genera_alerta = False
        conteo_estados[curso.estado_asistencia] += 1

    cursos_totales = list(cursos)
    cursos = [
        curso for curso in cursos
        if (not search_query or search_query.lower() in (
            f"{curso.nivel_romano} medio {curso.grupo} {curso.profesor_jefe}"
        ).lower())
        and (not estado_filtro or curso.estado_asistencia == estado_filtro)
    ]

    paginator = Paginator(cursos, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    total_registros = sum(curso.total_registros for curso in cursos_totales)
    total_ausencias = sum(curso.total_ausencias for curso in cursos_totales)
    porcentaje_general = round(
        (total_registros - total_ausencias) * 100 / total_registros
    ) if total_registros else 0

    total_cursos = len(cursos_totales)

    contexto = {
        'page_title': "Cursos",
        'page_obj': page_obj,
        'search_query': search_query,
        'estado_filtro': estado_filtro,
        'per_page': per_page,
        'is_12': per_page == 12,
        'is_24': per_page == 24,
        'is_48': per_page == 48,
        'orden': orden,
        'fecha_hoy': fecha_hoy,
        'current_year': año_actual,
        'current_month': format_date(fecha_hoy, format = "MMMM", locale = "es").capitalize(),
        'inicio_semana': format_date(inicio_semana, format = "dd MMM", locale = "es"),
        'fin_semana': format_date(fin_semana, format = "dd MMM", locale = "es"),
        'porcentaje_general': porcentaje_general,

        'total': f"{total_cursos} Cursos",
        'pastillas': [
            (f"{total_cursos} Cursos · Periodo actual", "azul"),
            (f"Cumplimiento meta · {93}%", "verde")
        ],
        'alertas': conteo_estados,
        'porcentaje_meta': 75, # META DESIGNADA POR EL INSTITUTO
    }
    
    return render (request, 'academico/base.html', contexto)