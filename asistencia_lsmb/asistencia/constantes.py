"""Nombres fijos de los catálogos de asistencia.

Estos catálogos no cambian: no se agregan ni se quitan filas. Los valores deben
coincidir con los que siembra asistencia/migrations/0005_catalogos_iniciales.py
(un test lo verifica).
"""

TIPO_PRESENTE = "presente"
TIPO_AUSENTE = "ausente"
TIPO_ATRASADO = "atrasado"
TIPO_JUSTIFICADO = "justificado"

ESTADO_PENDIENTE = "pendiente"
ESTADO_ACEPTADA = "aceptada"
ESTADO_RECHAZADA = "rechazada"

# nombre -> cuenta_como_ausencia
TIPOS_ASISTENCIA = {
    TIPO_PRESENTE: False,
    TIPO_AUSENTE: True,
    TIPO_ATRASADO: True,
    TIPO_JUSTIFICADO: False,
}

# nombre -> (es_estado_final, cubre_ausencia, descripcion)
ESTADOS_SOLICITUD = {
    ESTADO_PENDIENTE: (False, False, "Solicitud pendiente de revisión."),
    ESTADO_ACEPTADA: (True, True, "Solicitud aceptada; cubre la ausencia."),
    ESTADO_RECHAZADA: (True, False, "Solicitud rechazada; no cubre la ausencia."),
}
