"""Nombres fijos del catálogo de estados de matrícula (no cambia)."""

ESTADO_MATRICULA_VIGENTE = "vigente"
ESTADO_MATRICULA_RETIRADO = "retirado"
ESTADO_MATRICULA_EGRESADO = "egresado"

# nombre -> descripcion
ESTADOS_MATRICULA = {
    ESTADO_MATRICULA_VIGENTE: "Alumno con matrícula vigente",
    ESTADO_MATRICULA_RETIRADO: "Alumno que se retiró del liceo",
    ESTADO_MATRICULA_EGRESADO: "Alumno que egresó del liceo",
}
