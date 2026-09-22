from django.shortcuts import render
from django.urls import reverse
from django.http import Http404

TIPOS_VALIDOS = { 'justificacion', 'retiro' }

def pagina_justificaciones_formulario(request):
    tipo = request.GET.get('tipo')

    if tipo not in TIPOS_VALIDOS:
        return Http404("Tipo de formulario no válido")

    volver_url = request.GET.get('next') or reverse('justificaciones')
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "inicio" 

    contexto = {
        'page_title': 'Nueva justificación' if tipo == 'justificacion' else 'Nuevo retiro' if tipo == 'retiro' else 'Nuevo registro',
        'tipo': tipo,
        'volver_url': volver_url,
        'volver_label': volver_label,
    }
    return render(request, 'justificaciones/formulario.html', contexto)