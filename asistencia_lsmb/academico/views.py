from django.shortcuts import render

# Create your views here.
def pagina_alumnos(request):

    contexto = {}
    
    return render (request, 'academico/alumnos.html', contexto)