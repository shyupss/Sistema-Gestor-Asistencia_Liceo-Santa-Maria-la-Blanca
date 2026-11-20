"""Formato para mostrar cursos, porcentajes y niveles de alerta (comandos y correo).

No depende del idioma activo: los formatos se arman explícitamente.
"""
from decimal import ROUND_HALF_UP, Decimal

# Etiquetas de los dos niveles de gravedad de nivel_alerta para mostrar en el correo.
ETIQUETAS_NIVEL = {"critico": "Crítico", "atencion": "Atención"}


def etiqueta_curso(curso):
    """La etiqueta del curso que muestra monitoreo: nivel en romano, "°" y grupo ("I°A").

    Si el nivel no tiene romano (fuera de 1 a 4), usa el número, como Curso.nivel_romano.
    """
    return f"{curso.nivel_romano}°{curso.grupo}"


def formatear_porcentaje(valor):
    """Un decimal con coma y " %" ("40,5 %"); "sin datos" si es None.

    Redondea la mitad hacia arriba (40,05 -> 40,1), sin errores de coma flotante.
    """
    if valor is None:
        return "sin datos"
    redondeado = Decimal(str(valor)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{redondeado} %".replace(".", ",")


def formatear_nivel(nivel):
    """Etiqueta de un nivel de nivel_alerta ("critico" o "atencion")."""
    return ETIQUETAS_NIVEL[nivel]
