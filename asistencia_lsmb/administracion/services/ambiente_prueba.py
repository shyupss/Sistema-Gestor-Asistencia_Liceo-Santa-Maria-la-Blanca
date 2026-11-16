"""Datos de prueba: roles, cargos, funcionarios y cuentas.

Idempotente: crea lo que falte y NUNCA modifica ni borra lo existente.
No crea alumnos, cursos, períodos, permisos nuevos ni FuncionarioCurso.
"""
import re
import unicodedata

from django.db import transaction

from alertas.models import Cargo, Cuenta, Funcionario, Permiso, Rol, RolPermiso

# Buzón de pruebas: los correos de los funcionarios usan subdirección "+"
# (asistencia+rector1@lsmb.cl) y todos llegan a este buzón.
CORREO_BASE = "asistencia@lsmb.cl"
FUNCIONARIOS_POR_ROL = 3
# RUT ficticios y reconocibles: 99000001-0, 99000002-0, ...
RUT_BASE = 99000000
RUT_DV = "0"
PERMISO_CODIGO = "revisar_alertas"

# nombre del rol (y del cargo), alcance, recibe_todos_los_cursos_marcados
ROLES = (
    ("Asistente social", Rol.ALCANCE_TODOS, True),
    ("Rector", Rol.ALCANCE_TODOS, False),
    ("Inspector general", Rol.ALCANCE_TODOS, False),
    ("Inspector", Rol.ALCANCE_SELECCIONADOS, False),
)


class AmbientePruebaError(Exception):
    """El ambiente no se puede preparar sin modificar datos existentes."""


def _slug(nombre):
    sin_tildes = unicodedata.normalize("NFD", nombre.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn"))


def correo_de_prueba(rol_nombre, numero):
    usuario, dominio = CORREO_BASE.split("@")
    return f"{usuario}+{_slug(rol_nombre)}{numero}@{dominio}"


@transaction.atomic
def preparar_ambiente_prueba():
    """Crea lo que falte y devuelve cuántos registros creó de cada tipo."""
    creados = {"roles": 0, "permisos_rol": 0, "cargos": 0, "funcionarios": 0, "cuentas": 0}

    permiso, _ = Permiso.objects.get_or_create(
        codigo=PERMISO_CODIGO,
        defaults={
            "nombre": "Revisar alertas",
            "descripcion": "Permite revisar alertas y recibir notificaciones de alertas.",
        },
    )

    consecutivo = 0
    for nombre, alcance, recibe_todos in ROLES:
        rol, rol_creado = Rol.objects.get_or_create(
            nombre__iexact=nombre,
            defaults={
                "nombre": nombre,
                "alcance": alcance,
                "recibe_todos_los_cursos_marcados": recibe_todos,
            },
        )
        if rol_creado:
            creados["roles"] += 1
            # A un rol ya existente no se le toca nada, tampoco sus permisos.
            _, permiso_creado = RolPermiso.objects.get_or_create(rol=rol, permiso=permiso)
            creados["permisos_rol"] += permiso_creado

        cargo, cargo_creado = Cargo.objects.get_or_create(
            nombre__iexact=nombre, defaults={"nombre": nombre},
        )
        creados["cargos"] += cargo_creado

        for numero in range(1, FUNCIONARIOS_POR_ROL + 1):
            consecutivo += 1
            correo = correo_de_prueba(nombre, numero)
            if Funcionario.objects.filter(email__iexact=correo).exists():
                continue  # ya existe: no se toca (ni se le crea cuenta)
            rut = f"{RUT_BASE + consecutivo}-{RUT_DV}"
            if Funcionario.objects.filter(rut=rut).exists():
                raise AmbientePruebaError(
                    f"El RUT de prueba {rut} ya lo usa otro funcionario (no es {correo}). "
                    "No se creó nada; revisa ese funcionario antes de reintentar."
                )
            funcionario = Funcionario.objects.create(
                cargo=cargo, rut=rut, nombre=f"{nombre} Prueba {numero}", email=correo,
            )
            Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=True)
            creados["funcionarios"] += 1
            creados["cuentas"] += 1

    return creados
