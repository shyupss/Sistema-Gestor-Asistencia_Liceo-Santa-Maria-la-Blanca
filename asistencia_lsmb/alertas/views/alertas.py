"""Vista de la lista de alertas (H8).

Contrato de parámetros GET (para el backend)
--------------------------------------------
Todos son opcionales. Un valor ausente o inválido se reemplaza por el valor
por defecto (sin error).

    nivel     "critico" | "atencion"            por defecto: "" (todos los niveles)
    curso     "todos" | "<n><grupo>" (ej. "4b")  por defecto: "todos"
              TODO: con datos reales debería ser el id del Curso.
    rango     "30d" | "7d" | "mes" | "semana"    por defecto: "30d"
              30d/7d   -> fecha >= hoy - N días
              mes      -> fecha >= día 1 del mes actual
              semana   -> fecha >= lunes de la semana actual
    orden     "recientes" | "antiguos"           por defecto: "recientes"
              Ordena por (fecha, id) para que el orden sea estable.
    per_page  9 | 18 | 27                        por defecto: 9
    page      entero >= 1                        por defecto: 1 (fuera de rango -> última página)

Al aplicar un filtro, `page` se descarta: el form es GET y `page` no es campo
del form; los chips de nivel lo quitan con `{% querystring page=None %}`.
"""
import json
from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse

from alertas.models import Alerta
from alertas.services.alertas_service import (
    AlertaCerrada,
    AlertaError,
    AlertaYaRevisada,
    FueraDeAlcance,
    NotaInvalida,
    SinPermiso,
    marcar_revisada,
)
from alertas.services.identidad import funcionario_actual


OPCIONES_POR_PAGINA = [9, 18, 27]

# --------------------------------------------------------------------
# BLOQUE DE PRUEBAS
# TODO: Cambiar por datos reales (eliminar todo este bloque de prueba)
# --------------------------------------------------------------------
CRITICO = {"slug": "critico", "nombre": "Crítico", "color": "rojo"}
ATENCION = {"slug": "atencion", "nombre": "Atención", "color": "amarillo"}

# (alumno_id, nombre, rut, nivel_romano, grupo, nivel, nivel_anterior, porcentaje, umbral)
_ALUMNOS_PRUEBA = [
    (1, "Eduardo Montecinos Gática", "12.345.678-9", "IV", "B", CRITICO, "Atención", 72, 75),
    (2, "Matías Soto Lomboy", "12.345.678-9", "IV", "A", CRITICO, "Atención", 68, 75),
    (3, "Diego Soto Vergara", "12.345.678-9", "III", "A", ATENCION, "Adecuado", 81, 85),
    (4, "Valentina Pérez Muñoz", "12.345.678-9", "II", "B", ATENCION, "Adecuado", 79, 85),
    (5, "Martina González Rojas", "12.345.678-9", "I", "C", CRITICO, "Atención", 71, 75),
    (6, "Tomás Muñoz Araya", "12.345.678-9", "II", "A", ATENCION, "Adecuado", 83, 85),
    (7, "Sofía Morales Díaz", "12.345.678-9", "III", "B", ATENCION, "Adecuado", 80, 85),
    (8, "Benjamín Torres Silva", "12.345.678-9", "I", "B", CRITICO, "Atención", 70, 75),
    (9, "Camila Rojas Vera", "12.345.678-9", "IV", "B", ATENCION, "Adecuado", 82, 85),
]
_CANTIDAD_ALERTAS_PRUEBA = 72  # 8 páginas con 9 por página: suficiente para ver la elisión
_DIAS_PRUEBA = 45              # las fechas se reparten entre hoy y hoy - 44 días


def _alertas_prueba(hoy):
    """Genera alertas de prueba con fechas relativas a `hoy`, para que los
    rangos ("Últimos 7 días", "Esta semana", ...) siempre tengan datos.
    Se calcula por request (no al importar) para no quedar desfasado si el
    servidor corre varios días."""
    alertas = []
    for i in range(_CANTIDAD_ALERTAS_PRUEBA):
        alumno_id, nombre, rut, nivel_romano, grupo, nivel, anterior, porcentaje, umbral = (
            _ALUMNOS_PRUEBA[i % len(_ALUMNOS_PRUEBA)]
        )
        alertas.append({
            "id": i + 1,
            "alumno": {"id": alumno_id, "nombre": nombre, "rut": rut},
            "curso": {"nivel_romano": nivel_romano, "grupo": grupo},
            "nivel": nivel,
            "nivel_anterior": anterior,
            "mensaje": f"La asistencia de {nombre.split()[0]} es {porcentaje}%, por debajo del {umbral}%.",
            "fecha": hoy - timedelta(days=i * _DIAS_PRUEBA // _CANTIDAD_ALERTAS_PRUEBA),
        })
    return alertas

# --------------------------------------------------------------------

# TODO: Con datos reales, los niveles vienen del backend (configuración de alertas)
NIVELES_FILTROS_PRUEBA = [CRITICO, ATENCION]
NIVELES_VALIDOS = {nivel["slug"] for nivel in NIVELES_FILTROS_PRUEBA}

# Opciones de los selectores: pares (valor que viaja en la URL, etiqueta visible).
# La primera opción de cada lista es el valor por defecto.
_ROMANOS = {"I": 1, "II": 2, "III": 3, "IV": 4}

# TODO: Con datos reales, los cursos vienen de la BD y el valor es el id del Curso.
OPCIONES_CURSO = [("todos", "Todos los cursos")] + [
    (f"{numero}{grupo.lower()}", f"{romano}° Medio {grupo}")
    for romano, numero in _ROMANOS.items() for grupo in ("A", "B", "C")
]
OPCIONES_RANGO = [
    ("30d", "Últimos 30 días"),
    ("7d", "Últimos 7 días"),
    ("mes", "Este mes"),
    ("semana", "Esta semana"),
]
OPCIONES_ORDEN = [
    ("recientes", "Recientes primero"),
    ("antiguos", "Antiguos primero"),
]


def _seleccion(request, parametro, opciones):
    """Devuelve el valor de `parametro` si es uno de los valores válidos; si no, el primero."""
    valor = request.GET.get(parametro)
    valores = [v for v, _ in opciones]
    return valor if valor in valores else valores[0]


def _por_pagina(request):
    """Lee `per_page` del GET; si no es un entero de OPCIONES_POR_PAGINA usa el primero."""
    try:
        valor = int(request.GET.get("per_page", ""))
    except ValueError:
        return OPCIONES_POR_PAGINA[0]
    return valor if valor in OPCIONES_POR_PAGINA else OPCIONES_POR_PAGINA[0]


def _slug_curso(curso):
    """{"nivel_romano": "IV", "grupo": "B"} -> "4b" (mismo formato que OPCIONES_CURSO)."""
    return f"{_ROMANOS[curso['nivel_romano']]}{curso['grupo'].lower()}"


def _fecha_desde(rango, hoy):
    if rango == "7d":
        return hoy - timedelta(days=7)
    if rango == "mes":
        return hoy.replace(day=1)
    if rango == "semana":
        return hoy - timedelta(days=hoy.weekday())  # lunes
    return hoy - timedelta(days=30)  # "30d"


def _filtrar_alertas(alertas, hoy, curso, rango, orden, nivel=""):
    """Filtra y ordena la lista de alertas. `nivel` vacío no filtra por nivel
    (se usa así para calcular las cuentas de los chips).

    TODO: En producción esto será un filter()/order_by() sobre el queryset en
    el backend, con los mismos parámetros (ver contrato GET al inicio del archivo).
    """
    desde = _fecha_desde(rango, hoy)
    filtradas = [
        a for a in alertas
        if a["fecha"] >= desde
        and (curso == "todos" or _slug_curso(a["curso"]) == curso)
        and (not nivel or a["nivel"]["slug"] == nivel)
    ]
    return sorted(filtradas, key=lambda a: (a["fecha"], a["id"]), reverse=(orden == "recientes"))


def _niveles_con_cuenta(alertas_sin_filtro_nivel):
    """Agrega `cuenta` a cada nivel de filtro. Se cuenta sobre las alertas
    filtradas por curso y rango, pero NO por nivel: así, con "Crítico" activo,
    el chip "Atención" sigue mostrando su cuenta y sirve para cambiar de nivel.

    TODO: En producción las cuentas deberían venir del backend (p. ej. un
    values("nivel").annotate(Count("id")) sobre el queryset sin filtro de nivel).
    """
    cuentas = {}
    for alerta in alertas_sin_filtro_nivel:
        slug = alerta["nivel"]["slug"]
        cuentas[slug] = cuentas.get(slug, 0) + 1
    return [{**nivel, "cuenta": cuentas.get(nivel["slug"], 0)} for nivel in NIVELES_FILTROS_PRUEBA]


def _paginas_visibles(paginator, page_obj):
    return [
        None if p == paginator.ELLIPSIS else p
        for p in paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)
    ]


def pagina_alertas(request):
    fecha_hoy = timezone.localdate()

    nivel_actual = request.GET.get("nivel", "")
    if nivel_actual not in NIVELES_VALIDOS:
        nivel_actual = ""
    curso_actual = _seleccion(request, "curso", OPCIONES_CURSO)
    rango_actual = _seleccion(request, "rango", OPCIONES_RANGO)
    orden_actual = _seleccion(request, "orden", OPCIONES_ORDEN)

    # TODO: En producción esto será el queryset de alertas del backend
    alertas_prueba = _alertas_prueba(fecha_hoy)
    filtros = {"curso": curso_actual, "rango": rango_actual, "orden": orden_actual}
    alertas = _filtrar_alertas(alertas_prueba, fecha_hoy, nivel=nivel_actual, **filtros)
    # Base para las cuentas de los chips: mismos filtros, sin el de nivel
    alertas_sin_nivel = _filtrar_alertas(alertas_prueba, fecha_hoy, **filtros)

    per_page = _por_pagina(request)
    paginator = Paginator(alertas, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "page_title": "Alertas",
        "fecha_hoy": fecha_hoy,
        "page_obj": page_obj,
        "paginas": _paginas_visibles(paginator, page_obj),
        "per_page": per_page,
        "opciones_por_pagina": OPCIONES_POR_PAGINA,
        "niveles_filtros": _niveles_con_cuenta(alertas_sin_nivel),
        # TODO: Manejar que se muestren una cierta cantidad de filtros; la cantidad
        # de niveles ocultos depende del backend (configuración de niveles).
        "niveles_extras": 0,
        "nivel_actual": nivel_actual,
        # Selectores
        "opciones_curso": OPCIONES_CURSO,
        "opciones_rango": OPCIONES_RANGO,
        "opciones_orden": OPCIONES_ORDEN,
        "curso_actual": curso_actual,
        "rango_actual": rango_actual,
        "orden_actual": orden_actual,
    }
    return render(request, "alertas/base.html", contexto)


# Error del servicio -> (status HTTP, código de error de la respuesta).
ERRORES_REVISION = [
    (SinPermiso, 403, "sin_permiso"),
    (FueraDeAlcance, 403, "fuera_de_alcance"),
    (AlertaCerrada, 409, "alerta_cerrada"),
    (AlertaYaRevisada, 409, "ya_revisada"),
    (NotaInvalida, 400, "nota_invalida"),
]


def _error(status, codigo):
    return JsonResponse({"ok": False, "error": codigo}, status=status)


def _leer_nota(request):
    """`nota` del cuerpo, en JSON (application/json) o formulario; None si no viene.

    ValueError si el JSON está mal formado o no es un objeto.
    """
    if request.content_type == "application/json":
        datos = json.loads(request.body)
        if not isinstance(datos, dict):
            raise ValueError("El cuerpo JSON debe ser un objeto.")
        return datos.get("nota")
    return request.POST.get("nota")


def revisar_alerta(request, alerta_id):
    """POST /alertas/<alerta_id>/revisar/: marca la alerta como revisada por el funcionario actual.

    Cuerpo en JSON (application/json) o como formulario, con `nota` opcional.
    Todas las respuestas son JSON:
    - 200 {"ok": true, "alerta": {"id", "revisada", "fecha_revision" (ISO),
      "funcionario_revisa" (nombre), "nota"}}
    - 405 "metodo_no_permitido" (solo se acepta POST)
    - 401 "sin_funcionario"
    - 404 "no_encontrada"
    - 403 "sin_permiso" o "fuera_de_alcance"
    - 409 "alerta_cerrada" o "ya_revisada"
    - 400 "nota_invalida", o "solicitud_invalida" si el JSON viene mal formado
    Las verificaciones van en ese orden: método, funcionario, alerta, cuerpo y servicio.

    CSRF: el middleware CSRF está activo, así que el fetch debe enviar la
    cabecera X-CSRFToken.
    Autenticación: hasta que exista el login, la vista no tiene autenticación.
    El funcionario sale de FUNCIONARIO_REVISOR_PRUEBA_EMAIL (ver
    alertas/services/identidad.py); con la variable vacía responde 401 a todos.
    """
    if request.method != "POST":
        respuesta = _error(405, "metodo_no_permitido")
        respuesta["Allow"] = "POST"
        return respuesta
    funcionario = funcionario_actual(request)
    if funcionario is None:
        return _error(401, "sin_funcionario")
    alerta = Alerta.objects.filter(pk=alerta_id).first()
    if alerta is None:
        return _error(404, "no_encontrada")
    try:
        nota = _leer_nota(request)
    except ValueError:
        return _error(400, "solicitud_invalida")
    try:
        alerta = marcar_revisada(alerta, funcionario, nota)
    except AlertaError as exc:
        for clase, status, codigo in ERRORES_REVISION:
            if isinstance(exc, clase):
                return _error(status, codigo)
        raise
    return JsonResponse({"ok": True, "alerta": {
        "id": alerta.pk,
        "revisada": alerta.revisada,
        "fecha_revision": timezone.localtime(alerta.fecha_revision).isoformat(),
        "funcionario_revisa": alerta.funcionario_revisa.nombre,
        "nota": alerta.nota,
    }})