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
            {'curso': 'I°A', 'porcentaje': 80}, {'curso': 'I°B', 'porcentaje': 54},
            {'curso': 'II°A', 'porcentaje': 73}, {'curso': 'II°B', 'porcentaje': 82},
            {'curso': 'III°A', 'porcentaje': 95}, {'curso': 'III°B', 'porcentaje': 71},
            {'curso': 'IV°A', 'porcentaje': 56}, {'curso': 'IV°B', 'porcentaje': 67},
        ],
        'cursos_disponibles': ['Asistencia General', '1°A', '1°B', '2°A', '2°B', '3°A', '3°B', '4°A', '4°B'],
        'cursos_pendientes': [
            {'nombre': 'IV° medio A', 'url': '#'},
            {'nombre': 'III° medio B', 'url': '#'},
            {'nombre': 'I° medio A', 'url': '#'},
            {'nombre': 'II° medio A', 'url': '#'},
        ],

        # ALERTAS
        'alertas_por_nivel': {
            'atencion': 25,
            'critico': 34,
            'total': 59,
            'pct_atencion': 42,
            'pct_critico': 58,
        },
        'alertas_por_curso': {
            'labels': ['IV°B', 'III°A', 'I°A', 'II°B'],
            'valores': [34, 22, 8, 11],
        },
        'tendencia_alertas': {
            'labels': ['Sep', 'Oct', 'Nov', 'Dic', 'Mar'],
            'valores': [12, 28, 19, 31, 14],
        },
        'ranking_alertas': [
            {
                'posicion': 1,
                'alumno': 'Alumno 1',
                'curso': 'IV° Medio B',
                'atencion': 0,
                'critico': 3,
                'url': '#',
            },
            {
                'posicion': 2,
                'alumno': 'Alumno 2',
                'curso': 'IV° Medio B',
                'atencion': 1,
                'critico': 1,
                'url': '#',
            },
            {
                'posicion': 3,
                'alumno': 'Alumno 3',
                'curso': 'IV° Medio B',
                'atencion': 1,
                'critico': 1,
                'url': '#',
            },
            {
                'posicion': 4,
                'alumno': 'Alumno 4',
                'curso': 'IV° Medio B',
                'atencion': 0,
                'critico': 3,
                'url': '#',
            },
            {
                'posicion': 5,
                'alumno': 'Alumno 5',
                'curso': 'IV° Medio B',
                'atencion': 0,
                'critico': 3,
                'url': '#',
            },
        ],
        'ranking_ver_todos_url': '#',
        'alertas_recientes': [
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 2h',
                'nivel': 'critico',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 5h',
                'nivel': 'atencion',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 6h',
                'nivel': 'critico',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 7h',
                'nivel': 'critico',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 9h',
                'nivel': 'atencion',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 13h',
                'nivel': 'atencion',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 22h',
                'nivel': 'critico',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 1d',
                'nivel': 'atencion',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 2d',
                'nivel': 'atencion',
            },
            {
                'alumno': 'Alumno x',
                'curso': 'IV° Medio B',
                'hace': 'hace 5d',
                'nivel': 'critico',
            },
            
        ],
    }
    return render(request, "monitoreo/base.html", contexto)