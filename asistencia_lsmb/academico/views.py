from django.shortcuts import render
from .models import Alumno, Curso #Importa modelos a cargar

# Create your views here.
def pagina_alumnos(request):
    # Busca los registros del modelo en la tabla
    alumnos = Alumno.objects.all()

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