from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

def pagina_monitoreo(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Monitoreo",
        "fecha_hoy": fecha_hoy,

        ## -- INFO HARDCODEADA -- ##
        # TODO: pasar info real

        # ASISTENCIA
        'asistencia_general': {'porcentaje': 81, 'meta': 75, 'periodo': 'Sem 28 sep - 2 oct'},
        'evolucion_asistencia': {
            'labels': ['May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct'],
            'valores': [78, 82, 75, 88, 91, 85],
        },
        'asistencia_por_curso': [
            {'curso': '1°A', 'porcentaje': 80}, {'curso': '1°B', 'porcentaje': 54},
            {'curso': '2°A', 'porcentaje': 73}, {'curso': '2°B', 'porcentaje': 82},
            {'curso': '3°A', 'porcentaje': 95}, {'curso': '3°B', 'porcentaje': 71},
            {'curso': '4°A', 'porcentaje': 56}, {'curso': '4°B', 'porcentaje': 67},
        ],
        'calendario_asistencia': {
            'mes_label': 'Octubre 2026',
            'dias_semana': ['L', 'M', 'M', 'J', 'V', 'S', 'D'],
            'celdas': [None, None, None,
                {'numero': 1, 'porcentaje': 80}, {'numero': 2, 'porcentaje': 68}, {'numero': 3, 'porcentaje': None}, {'numero': 4, 'porcentaje': None},
                {'numero': 5, 'porcentaje': 76}, {'numero': 6, 'porcentaje': 67}, {'numero': 7, 'porcentaje': 51}, {'numero': 8, 'porcentaje': 73}, {'numero': 9, 'porcentaje': 92}, {'numero': 10, 'porcentaje': None}, {'numero': 11, 'porcentaje': None},
            ],
        },
        'cursos_disponibles': ['Asistencia General', '1°A', '1°B', '2°A', '2°B', '3°A', '3°B', '4°A', '4°B'],
        'cursos_pendientes': [
            {'nombre': 'IV° medio A', 'url': '#'},
            {'nombre': 'III° medio B', 'url': '#'},
            {'nombre': 'I° medio A', 'url': '#'},
            {'nombre': 'II° medio A', 'url': '#'},
        ],
    }
    return render(request, "monitoreo/base.html", contexto)