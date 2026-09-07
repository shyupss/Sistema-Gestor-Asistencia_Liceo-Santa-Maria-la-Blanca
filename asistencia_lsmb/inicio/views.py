# Create your views here.
from django.shortcuts import render
import os

def pagina_principal(request):
    # Datos que queremos enviar desde Python al HTML
    print("TEST:", os.getenv('POSTGRES_USER', 'fallo')) 
    contexto = {
        'mensaje': '¡Hola equipo! Bienvenidos a nuestro primer proyecto.',
        'tecnologias': ['Django', 'PostgreSQL', 'TailwindCSS']
    }
    return render(request, 'inicio/index.html', contexto)

def pagina_segunda(request):
    return render (request, 'inicio/segunda.html')