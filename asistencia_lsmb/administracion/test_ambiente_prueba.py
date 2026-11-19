import datetime
import importlib
import os
from io import StringIO

from django.apps import apps as apps_reales
from django.conf import settings
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academico.models import Curso, PeriodoAcademico
from administracion.forms import CursoForm
from administracion.services.ambiente_prueba import (
    AVISO_SIN_ESTADOS,
    AmbientePruebaError,
    correo_de_prueba,
    preparar_ambiente_prueba,
)
from alertas.models import (
    Cargo,
    Cuenta,
    Estado,
    EstadoNotificaRol,
    Funcionario,
    FuncionarioCurso,
    Permiso,
    Rol,
    RolPermiso,
)

# Los 4 niveles por defecto (los mismos que crea sembrar_estados).
NIVELES_ESTADO = (
    ("Óptimo", 95, False, "verde"),
    ("Adecuado", 85, False, "azul"),
    ("Atención", 75, True, "amarillo"),
    ("Crítico", 0, True, "rojo"),
)

# rol -> (alcance, recibe_todos_los_cursos_marcados, cargo, funcionarios de prueba),
# en el orden en que se asignan los RUT.
ROLES = {
    "Asistente social": ("todos", True, "Asistente social", 3),
    "Rector": ("todos", False, "Rector", 3),
    "Inspector general": ("todos", False, "Inspector general", 3),
    "Inspector": ("seleccionados", False, "Inspector", 3),
    "Profesor jefe": ("seleccionados", False, "Profesor", 12),
    "Profesor": ("seleccionados", False, "Profesor", 3),
}

CODIGOS_PERMISOS = {
    "revisar_alertas", "ver_monitoreo", "gestionar_justificaciones", "cargar_datos",
    "configurar_umbrales",
}
PERMISOS_POR_ROL = {
    "Asistente social": {"revisar_alertas", "ver_monitoreo", "gestionar_justificaciones"},
    "Rector": {"revisar_alertas", "ver_monitoreo", "configurar_umbrales"},
    "Inspector general": {
        "revisar_alertas", "ver_monitoreo", "gestionar_justificaciones", "cargar_datos",
    },
    "Inspector": {"revisar_alertas", "ver_monitoreo", "gestionar_justificaciones"},
    "Profesor jefe": {"revisar_alertas", "ver_monitoreo"},
    "Profesor": {"ver_monitoreo"},
}
# Con los 4 niveles por defecto: más grave = Crítico; no ideales = Atención y Crítico.
ESTADOS_POR_ROL = {
    "Asistente social": set(),
    "Rector": {"Crítico"},
    "Inspector general": {"Crítico"},
    "Inspector": {"Atención", "Crítico"},
    "Profesor jefe": {"Atención", "Crítico"},
    "Profesor": set(),
}

# Posición N = índice + 1: 1°A es la 1 y 4°C la 12.
CURSOS = [(nivel, grupo) for nivel in (1, 2, 3, 4) for grupo in ("A", "B", "C")]

CORREO_INACTIVO = "asistencia+inspectorinactivo@lsmb.cl"
CORREO_CUENTA_INACTIVA = "asistencia+inspectorcuentainactiva@lsmb.cl"

PRIMERA_PULSACION = {
    "roles": 6, "permisos": 5, "permisos_rol": 16, "cargos": 5, "funcionarios": 29,
    "cuentas": 29, "periodos": 1, "cursos": 12, "profesores_jefe": 12,
    "funcionario_cursos": 14, "estados_rol": 6,
}
NADA = dict.fromkeys(PRIMERA_PULSACION, 0)


def _vaciar():
    """No se asume el contenido previo de la BD (las migraciones siembran revisar_alertas)."""
    FuncionarioCurso.objects.all().delete()
    PeriodoAcademico.objects.all().delete()  # y sus cursos
    Cuenta.objects.all().delete()
    Funcionario.objects.all().delete()
    RolPermiso.objects.all().delete()
    EstadoNotificaRol.objects.all().delete()
    Rol.objects.all().delete()
    Cargo.objects.all().delete()
    Permiso.objects.all().delete()


def _crear_niveles():
    for nombre, umbral, es_no_ideal, color in NIVELES_ESTADO:
        Estado.objects.create(
            nombre=nombre, umbral_minimo=umbral, es_no_ideal=es_no_ideal, color=color,
        )


def _anio():
    return timezone.localdate().year


def _curso(nivel, grupo):
    return Curso.objects.get(periodo__anio=_anio(), nivel=nivel, grupo=grupo)


def _funcionario(rol, numero):
    return Funcionario.objects.get(email=correo_de_prueba(rol, numero))


def _cursos_de(funcionario):
    return {
        (fc.curso.nivel, fc.curso.grupo)
        for fc in FuncionarioCurso.objects.filter(funcionario=funcionario).select_related("curso")
    }


def _codigos_de(rol_nombre):
    return set(
        RolPermiso.objects.filter(rol__nombre=rol_nombre).values_list("permiso__codigo", flat=True)
    )


def _estados_de(rol_nombre):
    return set(
        EstadoNotificaRol.objects.filter(rol__nombre=rol_nombre)
        .values_list("estado__nombre", flat=True)
    )


def _mensajes(respuesta):
    return [(m.level_tag, str(m)) for m in get_messages(respuesta.wsgi_request)]


class ServicioAmbientePruebaTests(TestCase):
    def setUp(self):
        _vaciar()
        _crear_niveles()

    def test_devuelve_lo_creado_como_enteros(self):
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados, PRIMERA_PULSACION)
        for clave, valor in creados.items():
            with self.subTest(clave=clave):
                self.assertIs(type(valor), int)

    def test_crea_los_cinco_permisos(self):
        preparar_ambiente_prueba()
        self.assertEqual(set(Permiso.objects.values_list("codigo", flat=True)), CODIGOS_PERMISOS)
        revisar = Permiso.objects.get(codigo="revisar_alertas")
        self.assertEqual(revisar.nombre, "Revisar alertas")
        self.assertEqual(
            revisar.descripcion, "Permite revisar alertas y recibir notificaciones de alertas.",
        )
        for permiso in Permiso.objects.exclude(codigo="revisar_alertas"):
            with self.subTest(codigo=permiso.codigo):
                self.assertEqual(permiso.descripcion, "(ficticio, sin efecto en el código)")

    def test_no_modifica_un_permiso_existente(self):
        Permiso.objects.create(codigo="revisar_alertas", nombre="Otro", descripcion="editado")
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados["permisos"], 4)
        permiso = Permiso.objects.get(codigo="revisar_alertas")
        self.assertEqual((permiso.nombre, permiso.descripcion), ("Otro", "editado"))

    def test_crea_el_periodo_del_anio_actual(self):
        preparar_ambiente_prueba()
        periodo = PeriodoAcademico.objects.get()
        anio = _anio()
        self.assertEqual(periodo.anio, anio)
        self.assertEqual(periodo.fecha_inicio, datetime.date(anio, 3, 1))
        self.assertEqual(periodo.fecha_fin, datetime.date(anio, 12, 31))

    def test_no_toca_un_periodo_existente(self):
        anio = _anio()
        PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=datetime.date(anio, 3, 4), fecha_fin=datetime.date(anio, 12, 20),
        )
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados["periodos"], 0)
        self.assertEqual(creados["cursos"], 12)
        periodo = PeriodoAcademico.objects.get()
        self.assertEqual(periodo.fecha_inicio, datetime.date(anio, 3, 4))
        self.assertEqual(periodo.fecha_fin, datetime.date(anio, 12, 20))
        self.assertEqual(periodo.cursos.count(), 12)

    def test_crea_los_doce_cursos_del_periodo(self):
        preparar_ambiente_prueba()
        self.assertEqual(Curso.objects.count(), 12)
        self.assertEqual(
            set(Curso.objects.filter(periodo__anio=_anio()).values_list("nivel", "grupo")),
            set(CURSOS),
        )

    def test_roles_cargos_funcionarios_y_cuentas(self):
        preparar_ambiente_prueba()
        self.assertEqual(Rol.objects.count(), 6)
        self.assertEqual(
            set(Cargo.objects.values_list("nombre", flat=True)),
            {"Asistente social", "Rector", "Inspector general", "Inspector", "Profesor"},
        )
        self.assertEqual(Funcionario.objects.count(), 29)
        self.assertEqual(Cuenta.objects.count(), 29)
        for nombre, (alcance, recibe_todos, cargo, cantidad) in ROLES.items():
            with self.subTest(rol=nombre):
                rol = Rol.objects.get(nombre=nombre)
                self.assertEqual(rol.alcance, alcance)
                self.assertEqual(rol.recibe_todos_los_cursos_marcados, recibe_todos)
                for numero in range(1, cantidad + 1):
                    funcionario = _funcionario(nombre, numero)
                    self.assertEqual(funcionario.nombre, f"{nombre} Prueba {numero}")
                    self.assertEqual(funcionario.cargo.nombre, cargo)
                    self.assertTrue(funcionario.activo)
                    self.assertEqual(funcionario.cuenta.rol, rol)
                    self.assertTrue(funcionario.cuenta.activo)
        # 3 Inspectores de prueba + 2 de contraste.
        self.assertEqual(Cuenta.objects.filter(rol__nombre="Inspector").count(), 5)

    def test_correos_de_prueba(self):
        preparar_ambiente_prueba()
        correos = set(Funcionario.objects.values_list("email", flat=True))
        for correo in (
            "asistencia+asistentesocial1@lsmb.cl", "asistencia+inspectorgeneral3@lsmb.cl",
            "asistencia+profesorjefe1@lsmb.cl", "asistencia+profesorjefe12@lsmb.cl",
            "asistencia+profesor3@lsmb.cl", CORREO_INACTIVO, CORREO_CUENTA_INACTIVA,
        ):
            with self.subTest(correo=correo):
                self.assertIn(correo, correos)

    def test_ruts_consecutivos_en_el_orden_de_los_roles(self):
        preparar_ambiente_prueba()
        consecutivo = 0
        for nombre, (_, _, _, cantidad) in ROLES.items():
            for numero in range(1, cantidad + 1):
                consecutivo += 1
                with self.subTest(rol=nombre, numero=numero):
                    self.assertEqual(_funcionario(nombre, numero).rut, f"{99000000 + consecutivo}-0")
        self.assertEqual(consecutivo, 27)
        self.assertEqual(Funcionario.objects.get(email=CORREO_INACTIVO).rut, "99000028-0")
        self.assertEqual(Funcionario.objects.get(email=CORREO_CUENTA_INACTIVA).rut, "99000029-0")

    def test_permisos_por_rol(self):
        preparar_ambiente_prueba()
        for nombre, codigos in PERMISOS_POR_ROL.items():
            with self.subTest(rol=nombre):
                self.assertEqual(_codigos_de(nombre), codigos)
        self.assertEqual(RolPermiso.objects.count(), 16)

    def test_estados_que_notifican_por_rol(self):
        preparar_ambiente_prueba()
        for nombre, estados in ESTADOS_POR_ROL.items():
            with self.subTest(rol=nombre):
                self.assertEqual(_estados_de(nombre), estados)
        self.assertEqual(EstadoNotificaRol.objects.count(), 6)

    def test_mas_grave_y_no_ideales_no_dependen_del_nombre(self):
        Estado.objects.all().delete()
        Estado.objects.create(nombre="Bien", umbral_minimo=90, es_no_ideal=False)
        Estado.objects.create(nombre="Bajo", umbral_minimo=60, es_no_ideal=True)
        Estado.objects.create(nombre="Muy bajo", umbral_minimo=30, es_no_ideal=True)
        preparar_ambiente_prueba()
        self.assertEqual(_estados_de("Rector"), {"Muy bajo"})
        self.assertEqual(_estados_de("Inspector general"), {"Muy bajo"})
        self.assertEqual(_estados_de("Inspector"), {"Bajo", "Muy bajo"})
        self.assertEqual(_estados_de("Profesor jefe"), {"Bajo", "Muy bajo"})
        self.assertEqual(_estados_de("Asistente social"), set())
        self.assertEqual(_estados_de("Profesor"), set())

    def test_cada_curso_tiene_su_profesor_jefe(self):
        preparar_ambiente_prueba()
        jefes = set()
        for posicion, (nivel, grupo) in enumerate(CURSOS, start=1):
            with self.subTest(curso=f"{nivel}{grupo}"):
                jefe = _curso(nivel, grupo).profesor_jefe
                self.assertEqual(jefe, _funcionario("Profesor jefe", posicion))
                self.assertEqual(jefe.cuenta.rol.nombre, "Profesor jefe")
                jefes.add(jefe.pk)
        self.assertEqual(len(jefes), 12)

    def test_cada_inspector_tiene_los_cursos_de_su_letra(self):
        preparar_ambiente_prueba()
        for numero, grupo in enumerate(("A", "B", "C"), start=1):
            with self.subTest(inspector=numero):
                self.assertEqual(
                    _cursos_de(_funcionario("Inspector", numero)),
                    {(nivel, grupo) for nivel in (1, 2, 3, 4)},
                )
        self.assertEqual(FuncionarioCurso.objects.count(), 14)

    def test_funcionarios_de_contraste(self):
        preparar_ambiente_prueba()
        inactivo = Funcionario.objects.get(email=CORREO_INACTIVO)
        self.assertEqual(inactivo.nombre, "Inspector Prueba inactivo")
        self.assertFalse(inactivo.activo)
        self.assertTrue(inactivo.cuenta.activo)

        cuenta_inactiva = Funcionario.objects.get(email=CORREO_CUENTA_INACTIVA)
        self.assertEqual(cuenta_inactiva.nombre, "Inspector Prueba cuenta inactiva")
        self.assertTrue(cuenta_inactiva.activo)
        self.assertFalse(cuenta_inactiva.cuenta.activo)

        for funcionario in (inactivo, cuenta_inactiva):
            with self.subTest(funcionario=funcionario.nombre):
                self.assertEqual(funcionario.cargo.nombre, "Inspector")
                self.assertEqual(funcionario.cuenta.rol.nombre, "Inspector")
                self.assertEqual(_cursos_de(funcionario), {(1, "A")})

    def test_el_formulario_de_curso_ofrece_a_los_profesores_jefe(self):
        preparar_ambiente_prueba()
        opciones = set(CursoForm().fields["profesor_jefe"].queryset)
        jefes = set(Funcionario.objects.filter(cuenta__rol__nombre="Profesor jefe"))
        self.assertEqual(len(jefes), 12)
        self.assertLessEqual(jefes, opciones)

    def test_es_idempotente(self):
        preparar_ambiente_prueba()
        self.assertEqual(preparar_ambiente_prueba(), NADA)
        self.assertEqual(Permiso.objects.count(), 5)
        self.assertEqual(PeriodoAcademico.objects.count(), 1)
        self.assertEqual(Curso.objects.count(), 12)
        self.assertEqual(Rol.objects.count(), 6)
        self.assertEqual(RolPermiso.objects.count(), 16)
        self.assertEqual(EstadoNotificaRol.objects.count(), 6)
        self.assertEqual(Cargo.objects.count(), 5)
        self.assertEqual(Funcionario.objects.count(), 29)
        self.assertEqual(Cuenta.objects.count(), 29)
        self.assertEqual(FuncionarioCurso.objects.count(), 14)
        self.assertEqual(Curso.objects.filter(profesor_jefe__isnull=False).count(), 12)

    def test_un_rol_existente_no_recibe_permisos_ni_estados(self):
        existente = Rol.objects.create(nombre="Rector", alcance="seleccionados", descripcion="editado")
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados["roles"], 5)
        self.assertEqual(creados["permisos_rol"], 13)
        self.assertEqual(creados["estados_rol"], 5)
        existente.refresh_from_db()
        self.assertEqual((existente.alcance, existente.descripcion), ("seleccionados", "editado"))
        self.assertFalse(RolPermiso.objects.filter(rol=existente).exists())
        self.assertFalse(EstadoNotificaRol.objects.filter(rol=existente).exists())
        # Sus funcionarios de prueba sí se crean, con cuenta en el rol existente.
        self.assertEqual(Cuenta.objects.filter(rol=existente).count(), 3)

    def test_no_pisa_lo_editado(self):
        preparar_ambiente_prueba()
        Rol.objects.filter(nombre="Rector").update(alcance="seleccionados", descripcion="editado")
        Funcionario.objects.filter(email="asistencia+rector1@lsmb.cl").update(nombre="Otro nombre")
        # Solo cambia la capitalización: un renombre completo haría que la segunda
        # pulsación no lo encontrara y creara un cargo "Rector" nuevo.
        Cargo.objects.filter(nombre="Rector").update(nombre="RECTOR")

        self.assertEqual(preparar_ambiente_prueba(), NADA)
        rector = Rol.objects.get(nombre="Rector")
        self.assertEqual((rector.alcance, rector.descripcion), ("seleccionados", "editado"))
        self.assertEqual(
            Funcionario.objects.get(email="asistencia+rector1@lsmb.cl").nombre, "Otro nombre",
        )
        self.assertTrue(Cargo.objects.filter(nombre="RECTOR").exists())
        self.assertFalse(Cargo.objects.filter(nombre="Rector").exists())
        self.assertEqual(Cargo.objects.count(), 5)
        self.assertEqual(Funcionario.objects.count(), 29)

    def test_la_busqueda_no_distingue_mayusculas(self):
        rol = Rol.objects.create(nombre="rector")
        cargo = Cargo.objects.create(nombre="RECTOR")
        funcionario = Funcionario.objects.create(
            cargo=cargo, rut="1-9", nombre="Previo", email="ASISTENCIA+RECTOR1@LSMB.CL",
        )
        creados = preparar_ambiente_prueba()
        self.assertEqual(Rol.objects.filter(nombre__iexact="rector").count(), 1)
        self.assertEqual(Cargo.objects.filter(nombre__iexact="rector").count(), 1)
        self.assertEqual(
            Funcionario.objects.filter(email__iexact="asistencia+rector1@lsmb.cl").count(), 1,
        )
        self.assertEqual((creados["roles"], creados["cargos"], creados["funcionarios"]), (5, 4, 28))
        self.assertEqual(Rol.objects.count(), 6)
        self.assertEqual(Cargo.objects.count(), 5)
        self.assertEqual(Funcionario.objects.count(), 29)
        # Los existentes no se tocan: el funcionario previo no recibe cuenta.
        rol.refresh_from_db()
        cargo.refresh_from_db()
        funcionario.refresh_from_db()
        self.assertEqual(rol.nombre, "rector")
        self.assertEqual(cargo.nombre, "RECTOR")
        self.assertEqual((funcionario.nombre, funcionario.email), ("Previo", "ASISTENCIA+RECTOR1@LSMB.CL"))
        self.assertFalse(Cuenta.objects.filter(funcionario=funcionario).exists())
        # Los demás Rector de prueba usan el rol y el cargo existentes.
        for numero in (2, 3):
            with self.subTest(numero=numero):
                nuevo = _funcionario("Rector", numero)
                self.assertEqual(nuevo.cargo, cargo)
                self.assertEqual(nuevo.cuenta.rol, rol)

    def test_un_curso_existente_no_recibe_profesor_jefe_ni_inspectores(self):
        anio = _anio()
        periodo = PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=datetime.date(anio, 3, 1), fecha_fin=datetime.date(anio, 12, 31),
        )
        Curso.objects.create(periodo=periodo, nivel=2, grupo="B")  # posición 5
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados["cursos"], 11)
        self.assertEqual(creados["profesores_jefe"], 11)
        self.assertEqual(creados["funcionario_cursos"], 13)
        existente = _curso(2, "B")
        self.assertIsNone(existente.profesor_jefe)
        self.assertFalse(FuncionarioCurso.objects.filter(curso=existente).exists())
        self.assertFalse(Curso.objects.filter(profesor_jefe=_funcionario("Profesor jefe", 5)).exists())
        self.assertEqual(
            _cursos_de(_funcionario("Inspector", 2)), {(1, "B"), (3, "B"), (4, "B")},
        )

    def test_no_asigna_un_jefe_que_ya_es_jefe_de_otro_curso_del_periodo(self):
        anio = _anio()
        periodo = PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=datetime.date(anio, 3, 1), fecha_fin=datetime.date(anio, 12, 31),
        )
        jefe_1 = Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Profesor"), rut="1-9", nombre="Previo",
            email=correo_de_prueba("Profesor jefe", 1),
        )
        Curso.objects.create(periodo=periodo, nivel=4, grupo="C", profesor_jefe=jefe_1)
        creados = preparar_ambiente_prueba()
        # 1°A le correspondía a Profesor jefe 1, que ya es jefe de 4°C.
        self.assertIsNone(_curso(1, "A").profesor_jefe)
        self.assertEqual(_curso(4, "C").profesor_jefe, jefe_1)
        self.assertEqual(creados["profesores_jefe"], 10)
        self.assertEqual(_curso(1, "B").profesor_jefe, _funcionario("Profesor jefe", 2))

    def test_rut_de_prueba_ocupado_cancela_todo(self):
        cargo = Cargo.objects.create(nombre="Otro")
        for rut in ("99000020-0", "99000029-0"):
            with self.subTest(rut=rut):
                ajeno = Funcionario.objects.create(
                    cargo=cargo, rut=rut, nombre="Ajeno", email="ajeno@example.com",
                )
                with self.assertRaises(AmbientePruebaError) as ctx:
                    preparar_ambiente_prueba()
                self.assertIn(rut, str(ctx.exception))
                self.assertEqual(Permiso.objects.count(), 0)
                self.assertEqual(PeriodoAcademico.objects.count(), 0)
                self.assertEqual(Curso.objects.count(), 0)
                self.assertEqual(Rol.objects.count(), 0)
                self.assertEqual(RolPermiso.objects.count(), 0)
                self.assertEqual(EstadoNotificaRol.objects.count(), 0)
                self.assertEqual(Cargo.objects.count(), 1)
                self.assertEqual(Funcionario.objects.count(), 1)
                self.assertEqual(Cuenta.objects.count(), 0)
                self.assertEqual(FuncionarioCurso.objects.count(), 0)
                ajeno.delete()


class SinEstadosNoIdealesTests(TestCase):
    def setUp(self):
        _vaciar()
        Estado.objects.all().delete()

    def test_sin_estados_no_falla(self):
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados, {**PRIMERA_PULSACION, "estados_rol": 0})
        self.assertEqual(EstadoNotificaRol.objects.count(), 0)

    def test_solo_con_estados_ideales_tampoco_asigna(self):
        Estado.objects.create(nombre="Óptimo", umbral_minimo=95, es_no_ideal=False)
        creados = preparar_ambiente_prueba()
        self.assertEqual(creados["estados_rol"], 0)
        self.assertEqual(EstadoNotificaRol.objects.count(), 0)


class HabilitacionAmbientePruebaTests(TestCase):
    def setUp(self):
        _vaciar()
        _crear_niveles()
        self.url = reverse("preparar_ambiente_prueba")

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=False)
    def test_vista_apagada_no_crea_nada(self):
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("administracion"), fetch_redirect_response=False)
        mensajes = _mensajes(respuesta)
        self.assertEqual([nivel for nivel, _ in mensajes], ["error"])
        self.assertIn("deshabilitado", mensajes[0][1])
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(Funcionario.objects.count(), 0)
        self.assertEqual(Curso.objects.count(), 0)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_vista_encendida_crea_y_avisa(self):
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("administracion"), fetch_redirect_response=False)
        mensajes = _mensajes(respuesta)
        self.assertEqual([nivel for nivel, _ in mensajes], ["success"])
        texto = mensajes[0][1]
        self.assertIn("Ambiente de prueba listo", texto)
        for fragmento in (
            "períodos: 1", "cursos: 12", "profesores jefe: 12", "roles: 6", "permisos: 5",
            "funcionarios: 29", "cuentas: 29",
        ):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, texto)
        self.assertNotIn(AVISO_SIN_ESTADOS, texto)
        self.assertEqual(Funcionario.objects.count(), 29)
        # Segunda vez: nada nuevo.
        respuesta = self.client.post(self.url)
        # Los mensajes sin mostrar se acumulan en la sesión: el nuevo es el último.
        self.assertIn("ya estaba preparado", _mensajes(respuesta)[-1][1])
        self.assertEqual(Funcionario.objects.count(), 29)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_vista_sin_estados_no_ideales_avisa(self):
        Estado.objects.all().delete()
        respuesta = self.client.post(self.url)
        mensajes = _mensajes(respuesta)
        self.assertEqual([nivel for nivel, _ in mensajes], ["success"])
        self.assertIn("Ambiente de prueba listo", mensajes[0][1])
        self.assertIn(AVISO_SIN_ESTADOS, mensajes[0][1])
        # Sin roles nuevos no hay nada que avisar.
        respuesta = self.client.post(self.url)
        self.assertNotIn(AVISO_SIN_ESTADOS, _mensajes(respuesta)[-1][1])

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_vista_muestra_rut_duplicado_como_mensaje_de_error(self):
        Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Otro"), rut="99000001-0",
            nombre="Ajeno", email="ajeno@example.com",
        )
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("administracion"), fetch_redirect_response=False)
        mensajes = _mensajes(respuesta)
        self.assertEqual(mensajes[0][0], "error")
        self.assertIn("99000001-0", mensajes[0][1])
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(PeriodoAcademico.objects.count(), 0)
        self.assertEqual(Curso.objects.count(), 0)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_vista_solo_acepta_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(Rol.objects.count(), 0)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=False)
    def test_comando_apagado_falla(self):
        with self.assertRaises(CommandError):
            call_command("preparar_ambiente_prueba", stdout=StringIO())
        self.assertEqual(Rol.objects.count(), 0)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_comando_encendido_crea_e_imprime_resumen(self):
        salida = StringIO()
        call_command("preparar_ambiente_prueba", stdout=salida)
        texto = salida.getvalue()
        self.assertIn("Ambiente de prueba listo", texto)
        for fragmento in (
            "periodos: 1", "cursos: 12", "profesores_jefe: 12", "funcionario_cursos: 14",
            "funcionarios: 29", "estados_rol: 6",
        ):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, texto)
        self.assertNotIn(AVISO_SIN_ESTADOS, texto)
        self.assertEqual(Funcionario.objects.count(), 29)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_comando_sin_estados_no_ideales_avisa(self):
        Estado.objects.all().delete()
        salida = StringIO()
        call_command("preparar_ambiente_prueba", stdout=salida)
        self.assertIn(AVISO_SIN_ESTADOS, salida.getvalue())
        salida = StringIO()
        call_command("preparar_ambiente_prueba", stdout=salida)
        self.assertNotIn(AVISO_SIN_ESTADOS, salida.getvalue())

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_comando_rut_duplicado_es_command_error(self):
        Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Otro"), rut="99000001-0",
            nombre="Ajeno", email="ajeno@example.com",
        )
        with self.assertRaises(CommandError):
            call_command("preparar_ambiente_prueba", stdout=StringIO())
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(Curso.objects.count(), 0)

    def test_el_setting_esta_apagado_por_defecto(self):
        if os.getenv("PERMITIR_AMBIENTE_PRUEBA", "").strip().lower() in {"1", "true", "yes"}:
            self.skipTest("El entorno habilita el ambiente de prueba.")
        self.assertIs(settings.PERMITIR_AMBIENTE_PRUEBA, False)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=False)
    def test_boton_oculto_si_esta_apagado(self):
        respuesta = self.client.get(reverse("administracion"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Preparar ambiente de prueba")
        self.assertNotContains(respuesta, self.url)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_boton_visible_si_esta_encendido(self):
        respuesta = self.client.get(reverse("administracion"))
        self.assertContains(respuesta, "Preparar ambiente de prueba")
        self.assertContains(respuesta, f'action="{self.url}"')
        self.assertContains(respuesta, 'method="post"')
        self.assertContains(respuesta, "csrfmiddlewaretoken")
        self.assertContains(respuesta, "12 cursos")
        self.assertContains(respuesta, "planilla")


class SeparacionDelAmbientePruebaTests(TestCase):
    """Los datos de prueba solo existen si alguien los pide."""

    def test_bd_recien_migrada_no_tiene_datos_de_prueba(self):
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(Cargo.objects.count(), 0)
        self.assertEqual(Funcionario.objects.count(), 0)
        self.assertEqual(Cuenta.objects.count(), 0)
        self.assertEqual(PeriodoAcademico.objects.count(), 0)
        self.assertEqual(Curso.objects.count(), 0)
        self.assertEqual(FuncionarioCurso.objects.count(), 0)

    def test_migracion_0007_ya_no_crea_roles(self):
        modulo = importlib.import_module("alertas.migrations.0007_roles_iniciales")
        _vaciar()
        modulo.crear_roles_iniciales(apps_reales, None)
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(RolPermiso.objects.count(), 0)

    def test_entrypoint_y_migraciones_no_llaman_al_ambiente_de_prueba(self):
        base = settings.BASE_DIR
        entrypoint = base / "entrypoint.sh"
        if not entrypoint.exists():
            self.skipTest("entrypoint.sh no existe en este entorno.")
        self.assertNotIn("preparar_ambiente_prueba", entrypoint.read_text(encoding="utf-8"))
        migraciones = list(base.glob("*/migrations/*.py"))
        self.assertTrue(migraciones)
        for archivo in migraciones:
            with self.subTest(archivo=str(archivo.relative_to(base))):
                self.assertNotIn("preparar_ambiente_prueba", archivo.read_text(encoding="utf-8"))
