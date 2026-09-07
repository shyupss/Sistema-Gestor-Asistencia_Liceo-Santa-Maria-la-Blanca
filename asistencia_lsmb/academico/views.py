from django.shortcuts import render
from django.utils import timezone
from django.db.models import Prefetch
from .models import Alumno, Curso, Matricula #Importa modelos a cargar

# Create your views here.
def pagina_alumnos(request):
    año_actual = timezone.now().year
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
    alumnos = Alumno.objects.prefetch_related(matriculas_activas).all()

    contexto = {
        'lista_alumnos': alumnos
    }
    
    return render (request, 'academico/alumnos.html', contexto)


def pagina_cursos(request):
    # Busca los registros del modelo en la tabla
    cursos = Curso.objects.all()

    contexto = {
        'lista_cursos': cursos
    }
    
    return render (request, 'academico/cursos.html', contexto)