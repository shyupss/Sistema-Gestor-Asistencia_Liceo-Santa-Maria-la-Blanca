import importlib

from django.apps import apps as apps_reales
from django.test import TestCase

from alertas.models import Permiso, Rol, RolPermiso

ESPERADOS = {
    "Asistente social": ("todos", True),
    "Rector": ("todos", False),
    "Inspector general": ("todos", False),
    "Inspector": ("seleccionados", False),
}


def _migracion():
    return importlib.import_module("alertas.migrations.0007_roles_iniciales")


class RolesInicialesTests(TestCase):
    def setUp(self):
        # No se asume el contenido previo de la BD (los TransactionTestCase la vacían).
        RolPermiso.objects.all().delete()
        Rol.objects.all().delete()
        self.permiso = Permiso.objects.get_or_create(
            codigo="revisar_alertas", defaults={"nombre": "Revisar alertas"}
        )[0]

    def test_crea_los_cuatro_roles_con_sus_valores_y_el_permiso(self):
        _migracion().crear_roles_iniciales(apps_reales, None)
        self.assertEqual(Rol.objects.count(), 4)
        for nombre, (alcance, recibe_todos) in ESPERADOS.items():
            with self.subTest(rol=nombre):
                rol = Rol.objects.get(nombre=nombre)
                self.assertEqual(rol.alcance, alcance)
                self.assertEqual(rol.recibe_todos_los_cursos_marcados, recibe_todos)
                self.assertTrue(
                    RolPermiso.objects.filter(rol=rol, permiso=self.permiso).exists()
                )

    def test_es_idempotente(self):
        _migracion().crear_roles_iniciales(apps_reales, None)
        _migracion().crear_roles_iniciales(apps_reales, None)
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(RolPermiso.objects.count(), 4)

    def test_no_toca_un_rol_existente_ni_le_agrega_el_permiso(self):
        existente = Rol.objects.create(
            nombre="Inspector", alcance="todos", recibe_todos_los_cursos_marcados=True,
            descripcion="editado",
        )
        _migracion().crear_roles_iniciales(apps_reales, None)
        existente.refresh_from_db()
        self.assertEqual(existente.alcance, "todos")
        self.assertTrue(existente.recibe_todos_los_cursos_marcados)
        self.assertEqual(existente.descripcion, "editado")
        self.assertFalse(RolPermiso.objects.filter(rol=existente).exists())
        # Los otros tres sí se crean, con su permiso.
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(RolPermiso.objects.count(), 3)

    def test_la_busqueda_por_nombre_ignora_mayusculas(self):
        Rol.objects.create(nombre="rector")
        _migracion().crear_roles_iniciales(apps_reales, None)
        self.assertEqual(Rol.objects.filter(nombre__iexact="rector").count(), 1)
        self.assertEqual(Rol.objects.count(), 4)

    def test_no_siembra_estado_notifica_rol(self):
        from alertas.models import EstadoNotificaRol
        _migracion().crear_roles_iniciales(apps_reales, None)
        self.assertEqual(EstadoNotificaRol.objects.count(), 0)
