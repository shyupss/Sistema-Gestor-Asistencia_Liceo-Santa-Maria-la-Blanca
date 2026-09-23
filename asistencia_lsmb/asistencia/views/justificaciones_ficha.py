from django.shortcuts import render
from django.urls import reverse

from datetime import datetime

def pagina_justificaciones_ficha(request):
    id_justificacion = request.GET.get('id')

    volver_url = request.GET.get('next') or reverse('justificaciones')
    volver_label = volver_url.strip("/").split("/")[-1].lower() or "inicio" 

    contexto = {
        'page_title': 'Justificación',
        'volver_url': volver_url,
        'volver_label': volver_label,

        # TODO: Eliminar esta info hardcodeada
        'nombre': 'Eduardo Montecinos Gática',
        'rut': '12.345.678-9',
        'curso': 'IV° Medio B',
        'estado': 'pendiente',
        'tipo': 'justificacion',
        'pendiente': True,
        'periodo': '12 al 14 de sept 2026 · 3 días',
        'registro': '11 de sept 2026 · 12:31 hrs',
        'resumen': 'Cita al médico',
        'detalle': 'El estudiante justificó una ausencia de tres días por citas consecutivas al doctor en el horario matutino. Apoderado enfatiza la urgencia de las consultas e indica que requiere ser en la fecha dada a causa de un viaje de trabajo que tiene programado.',
        'documentos': [
            { 'nombre': 'certificado_medico.gif', 'url': 'https://static.wikia.nocookie.net/silly-cat/images/2/26/Tole_tole.gif/revision/latest?cb=20240521052830' },
        ],
        'bitacora': [
            { 'tipo': 'creacion', 'autor': 'Ana Torres Rivera', 'fecha': datetime(2026, 9, 11, 12, 31, 0) },
            { 'tipo': 'revision', 'autor': 'José Cristobal Silva', 'fecha': datetime(2026, 9, 11, 16, 24, 0) },
            { 'tipo': 'actual', 'estado': 'Esperando resolución' },
        ],
    }
    return render(request, 'justificaciones/ficha.html', contexto)