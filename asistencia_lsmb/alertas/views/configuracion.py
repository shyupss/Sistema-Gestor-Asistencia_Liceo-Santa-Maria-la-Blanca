from django.shortcuts import render
from django.utils import timezone

def pagina_configuracion(request):
    fecha_hoy = timezone.localdate()
    
    contexto = {
        "page_title": "Configuración de alertas",
        "fecha_hoy": fecha_hoy,
    }
    return render(request, 'alertas/configuracion.html', context = contexto)