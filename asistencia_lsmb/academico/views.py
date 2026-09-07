from django.shortcuts import render
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Prefetch
from datetime import timedelta
from .models import Alumno, Curso, Matricula #Importa modelos a cargar

# Create your views here.
def pagina_alumnos(request):
    fecha_hoy = timezone.localdate()
    año_actual = fecha_hoy.year
    inicio_semana = fecha_hoy - timedelta(days=fecha_hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    # Capturamos parámetros de búsqueda y paginación desde la URL
    search_query = request.GET.get('q', '')
    per_page = int(request.GET.get('per_page', 12)) # Por defecto 12 por página

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
    alumnos_qs = Alumno.objects.prefetch_related(matriculas_activas).all()

    # Si el usuario escribió algo en el buscador
    if search_query:
        alumnos_qs = alumnos_qs.filter(
            Q(nombre__icontains=search_query) |
            Q(rut__icontains=search_query) |
            Q(matriculas__curso__grupo__icontains=search_query)
        ).distinct()

    # Paginación
    paginator = Paginator(alumnos_qs, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    contexto = {
        'page_obj': page_obj,
        'search_query': search_query,
        'per_page': per_page,
        'is_12': per_page == 12,
        'is_24': per_page == 24,
        'is_48': per_page == 48,
        'fecha_hoy': fecha_hoy,
        'inicio_semana': inicio_semana,
        'fin_semana': fin_semana,
    }
    
    return render (request, 'academico/alumnos.html', contexto)


def pagina_cursos(request):
    # Busca los registros del modelo en la tabla
    cursos = Curso.objects.all()

    contexto = {
        'lista_cursos': cursos
    }
    
    return render (request, 'academico/cursos.html', contexto)