from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

ANTERIOR = [("alertas", "0007_roles_iniciales")]
MIGRACION = [("alertas", "0008_quitar_genera_alerta_y_configuracion")]


class MigracionQuitarGeneraAlertaTests(TransactionTestCase):
    """La migración 0008 aborta con un listado si genera_alerta difiere de es_no_ideal."""

    def _migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def _restaurar(self):
        # Limpia lo creado por el test y deja la BD de test en el último estado de migraciones.
        executor = MigrationExecutor(connection)
        executor.migrate(ANTERIOR)
        Estado = executor.loader.project_state(ANTERIOR).apps.get_model("alertas", "Estado")
        Estado.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _preparar(self, estados):
        self.addCleanup(self._restaurar)
        apps = self._migrar(ANTERIOR)
        Estado = apps.get_model("alertas", "Estado")
        Estado.objects.all().delete()
        for nombre, genera, no_ideal in estados:
            Estado.objects.create(
                nombre=nombre, umbral_minimo=0, genera_alerta=genera, es_no_ideal=no_ideal
            )
        return apps

    def _columnas(self, tabla):
        with connection.cursor() as cursor:
            return [c.name for c in connection.introspection.get_table_description(cursor, tabla)]

    def test_aborta_y_lista_los_estados_inconsistentes(self):
        self._preparar([("Bien", True, True), ("Mal uno", True, False), ("Mal dos", False, True)])
        with self.assertRaises(RuntimeError) as ctx:
            self._migrar(MIGRACION)
        mensaje = str(ctx.exception)
        self.assertIn("Mal uno", mensaje)
        self.assertIn("Mal dos", mensaje)
        self.assertNotIn("'Bien'", mensaje)
        # No se aplicó nada: el campo y la tabla siguen existiendo.
        self.assertIn("genera_alerta", self._columnas("alertas_estado"))
        self.assertIn("alertas_configuracionalerta", connection.introspection.table_names())

    def test_con_todo_consistente_elimina_el_campo_y_la_tabla(self):
        self._preparar([("A", True, True), ("B", False, False)])
        self._migrar(MIGRACION)
        self.assertNotIn("genera_alerta", self._columnas("alertas_estado"))
        self.assertNotIn("alertas_configuracionalerta", connection.introspection.table_names())

    def test_borra_configuracion_alerta_con_filas_sin_abortar(self):
        apps = self._preparar([("A", True, True)])
        Cargo = apps.get_model("alertas", "Cargo")
        Config = apps.get_model("alertas", "ConfiguracionAlerta")
        Estado = apps.get_model("alertas", "Estado")
        Config.objects.create(estado=Estado.objects.get(), cargo=Cargo.objects.create(nombre="X"))
        self._migrar(MIGRACION)
        self.assertNotIn("alertas_configuracionalerta", connection.introspection.table_names())

    def test_reverso_recrea_el_campo_con_default_false_y_la_tabla(self):
        self._preparar([("A", True, True)])
        self._migrar(MIGRACION)
        apps = self._migrar(ANTERIOR)
        self.assertIn("genera_alerta", self._columnas("alertas_estado"))
        self.assertIn("alertas_configuracionalerta", connection.introspection.table_names())
        self.assertFalse(apps.get_model("alertas", "Estado").objects.get().genera_alerta)
