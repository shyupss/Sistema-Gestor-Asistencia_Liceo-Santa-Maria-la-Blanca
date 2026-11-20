import json

from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from babel.dates import format_date

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

def pagina_alertas(request):
    fecha_hoy = timezone.localdate()

    contexto = {
        "page_title": "Alertas",
        "fecha_hoy": fecha_hoy
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
