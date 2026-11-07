import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from django.conf import settings
from django.core.cache import cache


class FeriadosError(RuntimeError):
    """Error al consultar los feriados del año solicitado."""


def obtener_feriados(anio):
    cache_key = f"feriados:CL:{anio}"
    feriados = cache.get(cache_key)
    if feriados is not None:
        return feriados

    url_base = getattr(
        settings,
        "FERIADOS_API_URL",
        "https://date.nager.at/api/v3/PublicHolidays",
    )
    try:
        with urlopen(f"{url_base}/{anio}/CL", timeout=5) as respuesta:
            datos = json.load(respuesta)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise FeriadosError(
            f"No fue posible consultar los feriados de {anio}. "
            "Intenta nuevamente más tarde."
        ) from exc

    if not isinstance(datos, list):
        raise FeriadosError("La API de feriados devolvió una respuesta inválida.")

    feriados = {
        item["date"]
        for item in datos
        if isinstance(item, dict)
        and isinstance(item.get("date"), str)
        and item["date"].startswith(f"{anio}-")
    }
    cache.set(cache_key, feriados, 60 * 60 * 24)
    return feriados


def obtener_feriado(fecha):
    fecha_iso = fecha.isoformat()
    return fecha_iso if fecha_iso in obtener_feriados(fecha.year) else None


def validar_dia_asistencia(fecha):
    if obtener_feriado(fecha):
        raise FeriadosError(
            f"El {fecha.strftime('%d/%m/%Y')} es feriado y no corresponde "
            "registrar asistencia."
        )
