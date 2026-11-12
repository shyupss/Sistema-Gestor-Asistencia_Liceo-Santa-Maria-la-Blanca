import datetime
import importlib

from django.apps import apps as apps_reales
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase

from academico.models import Curso, PeriodoAcademico
from administracion.forms import FuncionarioForm
from alertas.models import (
    Cargo,
    ConfigNotificaciones,
    Cuenta,
    Estado,
    EstadoNotificaRol,
    Funcionario,
    FuncionarioCurso,
    Notificacion,
    NotificacionCurso,
    Permiso,
    Rol,
    RolPermiso,
)


def _funcionario(email="a@liceo.cl", rut="11111111-1", cargo=None):
    cargo = cargo or Cargo.objects.get_or_create(nombre="Inspector")[0]
    return Funcionario.objects.create(cargo=cargo, rut=rut, nombre="Funcionario", email=email)


class UnicidadesTests(TestCase):
    def setUp(self):
        self.funcionario = _funcionario()
        periodo = PeriodoAcademico.objects.create(
            anio=2026, fecha_inicio=datetime.date(2026, 3, 1), fecha_fin=datetime.date(2026, 12, 31)
        )
        self.curso = Curso.objects.create(periodo=periodo, nivel=1, grupo="A")
        self.rol = Rol.objects.create(nombre="Inspector")
        self.permiso = Permiso.objects.get_or_create(
            codigo="revisar_alertas", defaults={"nombre": "Revisar alertas"}
        )[0]
        self.estado = Estado.objects.create(nombre="Crítico", umbral_minimo=0)

    def _duplicado(self, modelo, **campos):
        modelo.objects.create(**campos)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                modelo.objects.create(**campos)

    def test_rol_permiso_unico(self):
        self._duplicado(RolPermiso, rol=self.rol, permiso=self.permiso)

    def test_funcionario_curso_unico(self):
        self._duplicado(FuncionarioCurso, funcionario=self.funcionario, curso=self.curso)

    def test_estado_notifica_rol_unico(self):
        self._duplicado(EstadoNotificaRol, estado=self.estado, rol=self.rol)

    def test_notificacion_curso_unico(self):
        notificacion = Notificacion.objects.create(
            funcionario=self.funcionario, fecha_envio=datetime.datetime(2026, 5, 1, tzinfo=datetime.timezone.utc)
        )
        self._duplicado(NotificacionCurso, notificacion=notificacion, curso=self.curso)

    def test_rol_nombre_unico(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Rol.objects.create(nombre="Inspector")

    def test_permiso_codigo_unico(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Permiso.objects.create(codigo="revisar_alertas", nombre="Otro")


class DefaultsTests(TestCase):
    def test_rol(self):
        rol = Rol.objects.create(nombre="Docente")
        self.assertFalse(rol.recibe_todos_los_cursos_marcados)
        self.assertEqual(rol.alcance, "seleccionados")
        self.assertEqual(rol.descripcion, "")

    def test_alcance_rechaza_valores_fuera_de_las_opciones(self):
        with self.assertRaises(ValidationError):
            Rol(nombre="X", alcance="otro").full_clean()
        Rol(nombre="X", alcance="todos").full_clean()

    def test_notificacion_canal_por_defecto_es_email(self):
        notificacion = Notificacion.objects.create(
            funcionario=_funcionario(), fecha_envio=datetime.datetime(2026, 5, 1, tzinfo=datetime.timezone.utc)
        )
        self.assertEqual(notificacion.canal, "email")

    def test_cuenta(self):
        cuenta = Cuenta.objects.create(funcionario=_funcionario(), rol=Rol.objects.create(nombre="R"))
        self.assertTrue(cuenta.activo)
        self.assertIsNotNone(cuenta.fecha_creacion)

    def test_config_notificaciones(self):
        config = ConfigNotificaciones.obtener()
        self.assertEqual(config.pk, 1)
        self.assertTrue(config.activa)
        self.assertEqual(config.frecuencia_dias, 7)
        self.assertEqual(config.dia_semana_envio, 5)
        self.assertEqual(config.hora_envio, datetime.time(16, 0))


class ConfigNotificacionesSingletonTests(TestCase):
    def test_obtener_es_idempotente_y_no_crea_mas_de_una_fila(self):
        primera = ConfigNotificaciones.obtener()
        segunda = ConfigNotificaciones.obtener()
        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(ConfigNotificaciones.objects.count(), 1)

    def test_la_base_de_datos_rechaza_otro_id(self):
        ConfigNotificaciones.obtener()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfigNotificaciones.objects.create(pk=2)
        self.assertEqual(ConfigNotificaciones.objects.count(), 1)

    def test_validaciones_de_dia_y_frecuencia(self):
        config = ConfigNotificaciones.obtener()
        for campo, valor in (("dia_semana_envio", 0), ("dia_semana_envio", 8), ("frecuencia_dias", 0)):
            with self.subTest(campo=campo, valor=valor):
                setattr(config, campo, valor)
                with self.assertRaises(ValidationError):
                    config.full_clean()
                ConfigNotificaciones.obtener().refresh_from_db()
                config = ConfigNotificaciones.obtener()
        config.dia_semana_envio = 7
        config.full_clean()

    def test_la_base_de_datos_rechaza_dia_fuera_de_rango(self):
        config = ConfigNotificaciones.obtener()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfigNotificaciones.objects.filter(pk=config.pk).update(dia_semana_envio=8)


class EmailFuncionarioTests(TestCase):
    def test_email_unico_sin_distinguir_mayusculas(self):
        _funcionario(email="Persona@Liceo.cl", rut="11111111-1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _funcionario(email="persona@liceo.cl", rut="22222222-2")

    def test_email_vacio_rechazado_por_la_base_de_datos(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _funcionario(email="")

    def test_formulario_muestra_el_correo_duplicado_como_error_de_validacion(self):
        existente = _funcionario(email="Persona@Liceo.cl", rut="11111111-1")
        form = FuncionarioForm({
            "cargo": existente.cargo_id, "rut": "22222222-2", "nombre": "Otra Persona",
            "email": "persona@liceo.cl", "activo": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertTrue(form.errors, "El formulario debería reportar un error de validación")


class CuentaTests(TestCase):
    def test_un_funcionario_tiene_una_sola_cuenta(self):
        funcionario = _funcionario()
        rol = Rol.objects.create(nombre="R")
        Cuenta.objects.create(funcionario=funcionario, rol=rol)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cuenta.objects.create(funcionario=funcionario, rol=rol)

    def test_no_se_puede_borrar_funcionario_ni_rol_con_cuenta(self):
        funcionario = _funcionario()
        rol = Rol.objects.create(nombre="R")
        Cuenta.objects.create(funcionario=funcionario, rol=rol)
        with self.assertRaises(ProtectedError):
            funcionario.delete()
        with self.assertRaises(ProtectedError):
            rol.delete()


class DatosInicialesTests(TestCase):
    """La migración de datos crea el permiso y la configuración una sola vez."""

    def test_crea_una_sola_vez(self):
        modulo = importlib.import_module("alertas.migrations.0006_datos_iniciales_roles_notificaciones")
        Permiso.objects.filter(codigo="revisar_alertas").delete()
        ConfigNotificaciones.objects.all().delete()
        modulo.crear_datos_iniciales(apps_reales, None)
        modulo.crear_datos_iniciales(apps_reales, None)
        self.assertEqual(Permiso.objects.filter(codigo="revisar_alertas").count(), 1)
        self.assertEqual(ConfigNotificaciones.objects.count(), 1)
        self.assertEqual(ConfigNotificaciones.objects.get().pk, 1)
        self.assertEqual(Rol.objects.count(), 0)  # no crea roles

    def test_no_pisa_valores_existentes(self):
        modulo = importlib.import_module("alertas.migrations.0006_datos_iniciales_roles_notificaciones")
        config = ConfigNotificaciones.obtener()
        config.frecuencia_dias = 14
        config.save()
        modulo.crear_datos_iniciales(apps_reales, None)
        self.assertEqual(ConfigNotificaciones.obtener().frecuencia_dias, 14)


class MigracionCorreosTests(TransactionTestCase):
    """La migración 0005 aborta con mensaje claro si hay correos duplicados o vacíos."""

    def _destino_previo(self):
        hojas = MigrationExecutor(connection).loader.graph.leaf_nodes()
        return [n for n in hojas if n[0] != "alertas"] + [("alertas", "0004_alerta_modelo_nuevo")]

    def _migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def _restaurar(self):
        # Borra lo creado por el test y deja la BD de test en el último estado de migraciones.
        if getattr(self, "_funcionario_historico", None) is not None:
            self._funcionario_historico.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _preparar(self, emails):
        self.addCleanup(self._restaurar)
        apps = self._migrar(self._destino_previo())
        Cargo = apps.get_model("alertas", "Cargo")
        self._funcionario_historico = Funcionario_h = apps.get_model("alertas", "Funcionario")
        cargo = Cargo.objects.create(nombre="Inspector")
        for i, email in enumerate(emails, start=1):
            Funcionario_h.objects.create(cargo=cargo, rut=f"{i}0000000-{i}", nombre=f"F{i}", email=email)

    def test_aborta_con_correos_duplicados(self):
        self._preparar(["Persona@Liceo.cl", "persona@liceo.cl"])
        with self.assertRaises(RuntimeError) as ctx:
            self._migrar([("alertas", "0005_roles_cuentas_notificaciones")])
        self.assertIn("correos duplicados: persona@liceo.cl", str(ctx.exception))

    def test_aborta_con_correos_vacios(self):
        self._preparar(["", "ok@liceo.cl"])
        with self.assertRaises(RuntimeError) as ctx:
            self._migrar([("alertas", "0005_roles_cuentas_notificaciones")])
        self.assertIn("correo vacío", str(ctx.exception))
