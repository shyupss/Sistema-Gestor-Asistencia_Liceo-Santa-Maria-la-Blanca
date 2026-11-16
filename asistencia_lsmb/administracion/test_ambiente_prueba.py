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

from administracion.services.ambiente_prueba import (
    CORREO_BASE,
    AmbientePruebaError,
    preparar_ambiente_prueba,
)
from alertas.models import (
    Cargo,
    Cuenta,
    EstadoNotificaRol,
    Funcionario,
    FuncionarioCurso,
    Permiso,
    Rol,
    RolPermiso,
)

# nombre -> (alcance, recibe_todos_los_cursos_marcados)
ESPERADOS = {
    "Asistente social": ("todos", True),
    "Rector": ("todos", False),
    "Inspector general": ("todos", False),
    "Inspector": ("seleccionados", False),
}


def _vaciar():
    """No se asume el contenido previo de la BD (los TransactionTestCase la vacían)."""
    Cuenta.objects.all().delete()
    Funcionario.objects.all().delete()
    RolPermiso.objects.all().delete()
    EstadoNotificaRol.objects.all().delete()
    Rol.objects.all().delete()
    Cargo.objects.all().delete()


def _mensajes(respuesta):
    return [(m.level_tag, str(m)) for m in get_messages(respuesta.wsgi_request)]


class ServicioAmbientePruebaTests(TestCase):
    def setUp(self):
        _vaciar()

    def test_crea_roles_con_sus_valores_y_el_permiso(self):
        preparar_ambiente_prueba()
        self.assertEqual(Rol.objects.count(), 4)
        permiso = Permiso.objects.get(codigo="revisar_alertas")
        for nombre, (alcance, recibe_todos) in ESPERADOS.items():
            with self.subTest(rol=nombre):
                rol = Rol.objects.get(nombre=nombre)
                self.assertEqual(rol.alcance, alcance)
                self.assertEqual(rol.recibe_todos_los_cursos_marcados, recibe_todos)
                self.assertTrue(RolPermiso.objects.filter(rol=rol, permiso=permiso).exists())
        self.assertEqual(RolPermiso.objects.count(), 4)

    def test_crea_cargos_funcionarios_y_cuentas(self):
        creados = preparar_ambiente_prueba()
        self.assertEqual(
            creados,
            {"roles": 4, "permisos_rol": 4, "cargos": 4, "funcionarios": 12, "cuentas": 12},
        )
        self.assertEqual(Cargo.objects.count(), 4)
        self.assertEqual(Funcionario.objects.count(), 12)
        self.assertEqual(Cuenta.objects.count(), 12)
        for nombre in ESPERADOS:
            with self.subTest(rol=nombre):
                self.assertTrue(Cargo.objects.filter(nombre=nombre).exists())
                cuentas = Cuenta.objects.filter(rol__nombre=nombre)
                self.assertEqual(cuentas.count(), 3)
                for cuenta in cuentas:
                    self.assertTrue(cuenta.activo)
                    self.assertEqual(cuenta.funcionario.cargo.nombre, nombre)
        self.assertEqual(Funcionario.objects.filter(cuenta__isnull=True).count(), 0)

    def test_correos_unicos_con_subdireccion_del_buzon_de_pruebas(self):
        preparar_ambiente_prueba()
        usuario, dominio = CORREO_BASE.split("@")
        correos = list(Funcionario.objects.values_list("email", flat=True))
        self.assertEqual(len({c.lower() for c in correos}), 12)
        for correo in correos:
            self.assertRegex(correo, rf"^{usuario}\+[a-z0-9]+\d@{dominio}$")
        self.assertIn("asistencia+asistentesocial1@lsmb.cl", correos)
        self.assertIn("asistencia+rector2@lsmb.cl", correos)
        self.assertIn("asistencia+inspectorgeneral3@lsmb.cl", correos)
        self.assertIn("asistencia+inspector1@lsmb.cl", correos)

    def test_nombres_y_ruts_ficticios(self):
        preparar_ambiente_prueba()
        self.assertEqual(
            sorted(Funcionario.objects.values_list("rut", flat=True)),
            sorted(f"{99000000 + n}-0" for n in range(1, 13)),
        )
        self.assertTrue(Funcionario.objects.filter(nombre="Asistente social Prueba 1").exists())
        self.assertTrue(Funcionario.objects.filter(nombre="Inspector Prueba 3").exists())

    def test_no_crea_otros_permisos_ni_datos_academicos(self):
        from academico.models import Alumno, Curso, PeriodoAcademico
        codigos_antes = set(Permiso.objects.values_list("codigo", flat=True))
        preparar_ambiente_prueba()
        codigos = set(Permiso.objects.values_list("codigo", flat=True))
        self.assertLessEqual(codigos - codigos_antes, {"revisar_alertas"})
        self.assertEqual(Permiso.objects.filter(codigo="revisar_alertas").count(), 1)
        self.assertEqual(Alumno.objects.count(), 0)
        self.assertEqual(Curso.objects.count(), 0)
        self.assertEqual(PeriodoAcademico.objects.count(), 0)
        self.assertEqual(FuncionarioCurso.objects.count(), 0)

    def test_es_idempotente(self):
        preparar_ambiente_prueba()
        segunda = preparar_ambiente_prueba()
        self.assertEqual(
            segunda, {"roles": 0, "permisos_rol": 0, "cargos": 0, "funcionarios": 0, "cuentas": 0},
        )
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(RolPermiso.objects.count(), 4)
        self.assertEqual(Cargo.objects.count(), 4)
        self.assertEqual(Funcionario.objects.count(), 12)
        self.assertEqual(Cuenta.objects.count(), 12)

    def test_no_pisa_lo_editado(self):
        preparar_ambiente_prueba()
        Rol.objects.filter(nombre="Rector").update(alcance="seleccionados", descripcion="editado")
        Funcionario.objects.filter(email="asistencia+rector1@lsmb.cl").update(nombre="Otro nombre")
        preparar_ambiente_prueba()
        rector = Rol.objects.get(nombre="Rector")
        self.assertEqual((rector.alcance, rector.descripcion), ("seleccionados", "editado"))
        self.assertEqual(
            Funcionario.objects.get(email="asistencia+rector1@lsmb.cl").nombre, "Otro nombre",
        )
        self.assertEqual(Funcionario.objects.count(), 12)

    def test_no_toca_un_rol_existente_ni_le_agrega_el_permiso(self):
        existente = Rol.objects.create(
            nombre="Inspector", alcance="todos", recibe_todos_los_cursos_marcados=True,
            descripcion="editado",
        )
        preparar_ambiente_prueba()
        existente.refresh_from_db()
        self.assertEqual(existente.alcance, "todos")
        self.assertTrue(existente.recibe_todos_los_cursos_marcados)
        self.assertEqual(existente.descripcion, "editado")
        self.assertFalse(RolPermiso.objects.filter(rol=existente).exists())
        # Los otros tres roles sí se crean, con su permiso.
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(RolPermiso.objects.count(), 3)
        # Las cuentas de Inspector se ligan al rol existente.
        self.assertEqual(Cuenta.objects.filter(rol=existente).count(), 3)

    def test_la_busqueda_por_nombre_ignora_mayusculas(self):
        Rol.objects.create(nombre="rector")
        Cargo.objects.create(nombre="INSPECTOR")
        preparar_ambiente_prueba()
        self.assertEqual(Rol.objects.filter(nombre__iexact="rector").count(), 1)
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(Cargo.objects.filter(nombre__iexact="inspector").count(), 1)
        self.assertEqual(Cargo.objects.count(), 4)

    def test_el_correo_se_busca_sin_distinguir_mayusculas(self):
        cargo = Cargo.objects.create(nombre="Otro")
        Funcionario.objects.create(
            cargo=cargo, rut="1-9", nombre="Previo", email="ASISTENCIA+Rector1@LSMB.CL",
        )
        preparar_ambiente_prueba()
        # 11 nuevos + el previo, que no se toca ni recibe cuenta.
        self.assertEqual(Funcionario.objects.count(), 12)
        self.assertEqual(Funcionario.objects.get(rut="1-9").nombre, "Previo")
        self.assertFalse(Cuenta.objects.filter(funcionario__rut="1-9").exists())

    def test_no_siembra_estado_notifica_rol(self):
        preparar_ambiente_prueba()
        self.assertEqual(EstadoNotificaRol.objects.count(), 0)

    def test_rut_ocupado_por_otro_funcionario_falla_sin_crear_nada(self):
        cargo = Cargo.objects.create(nombre="Otro")
        Funcionario.objects.create(
            cargo=cargo, rut="99000003-0", nombre="Ajeno", email="ajeno@example.com",
        )
        with self.assertRaises(AmbientePruebaError) as ctx:
            preparar_ambiente_prueba()
        self.assertIn("99000003-0", str(ctx.exception))
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(Cuenta.objects.count(), 0)
        self.assertEqual(Funcionario.objects.count(), 1)


class HabilitacionAmbientePruebaTests(TestCase):
    def setUp(self):
        _vaciar()
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

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_vista_encendida_crea_y_avisa(self):
        respuesta = self.client.post(self.url)
        self.assertRedirects(respuesta, reverse("administracion"), fetch_redirect_response=False)
        mensajes = _mensajes(respuesta)
        self.assertEqual(mensajes[0][0], "success")
        self.assertIn("4 roles", mensajes[0][1])
        self.assertIn("12 funcionarios", mensajes[0][1])
        self.assertEqual(Funcionario.objects.count(), 12)
        # Segunda vez: nada nuevo.
        respuesta = self.client.post(self.url)
        # Los mensajes sin mostrar se acumulan en la sesión: el nuevo es el último.
        self.assertIn("ya estaba preparado", _mensajes(respuesta)[-1][1])
        self.assertEqual(Funcionario.objects.count(), 12)

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
        self.assertIn("funcionarios: 12", salida.getvalue())
        self.assertEqual(Funcionario.objects.count(), 12)

    @override_settings(PERMITIR_AMBIENTE_PRUEBA=True)
    def test_comando_rut_duplicado_es_command_error(self):
        Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Otro"), rut="99000001-0",
            nombre="Ajeno", email="ajeno@example.com",
        )
        with self.assertRaises(CommandError):
            call_command("preparar_ambiente_prueba", stdout=StringIO())
        self.assertEqual(Rol.objects.count(), 0)

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


class SeparacionDelAmbientePruebaTests(TestCase):
    """Los datos de prueba solo existen si alguien los pide."""

    def test_bd_recien_migrada_no_tiene_datos_de_prueba(self):
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(Cargo.objects.count(), 0)
        self.assertEqual(Funcionario.objects.count(), 0)
        self.assertEqual(Cuenta.objects.count(), 0)

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
