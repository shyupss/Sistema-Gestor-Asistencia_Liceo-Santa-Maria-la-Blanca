import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from alertas.models import ConfigGeneral


class MetaAsistenciaTests(TestCase):
    def test_migracion_deja_fila_unica_con_meta_75(self):
        # La migración 0006 siembra la fila id=1 y la 0009 agrega meta_asistencia=75.
        config = ConfigGeneral.objects.get()
        self.assertEqual(config.pk, 1)
        self.assertEqual(config.meta_asistencia, 75)

    def test_no_se_puede_crear_otra_fila(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfigGeneral.objects.create(pk=2)
        self.assertEqual(ConfigGeneral.objects.count(), 1)

    def test_meta_fuera_de_rango_falla_en_full_clean(self):
        config = ConfigGeneral.obtener()
        for valor in (101, 200):
            config.meta_asistencia = valor
            with self.assertRaises(ValidationError):
                config.full_clean()
        config.meta_asistencia = 0
        config.full_clean()
        config.meta_asistencia = 100
        config.full_clean()

    def test_constraint_rechaza_meta_mayor_a_100(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfigGeneral.objects.filter(pk=1).update(meta_asistencia=101)
        self.assertEqual(ConfigGeneral.obtener().meta_asistencia, 75)

    def test_meta_100_es_valida_en_bd(self):
        ConfigGeneral.objects.filter(pk=1).update(meta_asistencia=100)
        self.assertEqual(ConfigGeneral.obtener().meta_asistencia, 100)

    def test_str(self):
        self.assertEqual(str(ConfigGeneral.obtener()), "Configuración general")


class ModoYDiaMesTests(TestCase):
    """ConfigGeneral v2: modo de envío y día del mes (migración 0010)."""

    def test_la_fila_migrada_tiene_los_defaults_nuevos(self):
        # La 0006 siembra la fila y la 0010 le aplica los defaults de los campos nuevos.
        config = ConfigGeneral.objects.get()
        self.assertEqual(config.modo, ConfigGeneral.MODO_SEMANAL)
        self.assertEqual(config.dia_mes_envio, 1)
        self.assertEqual(config.dia_semana_envio, 5)
        self.assertEqual(config.hora_envio, datetime.time(16, 0))
        self.assertTrue(config.activa)
        self.assertEqual(config.meta_asistencia, 75)

    def test_defaults_de_una_fila_nueva(self):
        ConfigGeneral.objects.all().delete()
        config = ConfigGeneral.obtener()
        self.assertEqual(config.modo, "semanal")
        self.assertEqual(config.dia_mes_envio, 1)
        self.assertEqual(config.dia_semana_envio, 5)
        self.assertEqual(config.hora_envio, datetime.time(16, 0))
        self.assertTrue(config.activa)
        self.assertEqual(config.meta_asistencia, 75)

    def test_frecuencia_dias_ya_no_existe(self):
        nombres = {campo.name for campo in ConfigGeneral._meta.get_fields()}
        self.assertNotIn("frecuencia_dias", nombres)

    def test_constantes_y_choices_de_modo(self):
        self.assertEqual(ConfigGeneral.MODO_DIARIO, "diario")
        self.assertEqual(ConfigGeneral.MODO_SEMANAL, "semanal")
        self.assertEqual(ConfigGeneral.MODO_MENSUAL, "mensual")
        self.assertEqual(
            [valor for valor, _ in ConfigGeneral.MODOS], ["diario", "semanal", "mensual"],
        )
        self.assertEqual(ConfigGeneral._meta.get_field("modo").choices, ConfigGeneral.MODOS)
        self.assertEqual(ConfigGeneral._meta.get_field("modo").max_length, 10)

    def test_todos_los_modos_son_validos(self):
        config = ConfigGeneral.obtener()
        for valor, _ in ConfigGeneral.MODOS:
            with self.subTest(modo=valor):
                config.modo = valor
                config.full_clean()
                config.save()
                self.assertEqual(ConfigGeneral.obtener().modo, valor)

    def test_modo_invalido_falla_en_full_clean(self):
        config = ConfigGeneral.obtener()
        config.modo = "quincenal"
        with self.assertRaises(ValidationError):
            config.full_clean()

    def test_constraint_rechaza_modo_invalido(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfigGeneral.objects.filter(pk=1).update(modo="quincenal")
        self.assertEqual(ConfigGeneral.obtener().modo, "semanal")

    def test_dia_mes_0_y_32_fallan_en_full_clean(self):
        config = ConfigGeneral.obtener()
        for valor in (0, 32):
            with self.subTest(dia_mes_envio=valor):
                config.dia_mes_envio = valor
                with self.assertRaises(ValidationError):
                    config.full_clean()

    def test_dia_mes_1_y_31_son_validos(self):
        config = ConfigGeneral.obtener()
        for valor in (1, 31):
            with self.subTest(dia_mes_envio=valor):
                config.dia_mes_envio = valor
                config.full_clean()
                config.save()
                self.assertEqual(ConfigGeneral.obtener().dia_mes_envio, valor)

    def test_constraint_rechaza_dia_mes_fuera_de_rango(self):
        for valor in (0, 32):
            with self.subTest(dia_mes_envio=valor):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        ConfigGeneral.objects.filter(pk=1).update(dia_mes_envio=valor)
        self.assertEqual(ConfigGeneral.obtener().dia_mes_envio, 1)


class MigracionModoTests(TransactionTestCase):
    """La 0010 aplica los defaults en la fila existente, quita frecuencia_dias y es reversible."""

    ANTERIOR = ("alertas", "0009_config_general")
    NUEVA = ("alertas", "0010_config_general_modo")
    TABLA = "alertas_configgeneral"

    def _destino(self, nodo_alertas):
        grafo = MigrationExecutor(connection).loader.graph
        # Se deshacen las migraciones de alertas posteriores a nodo_alertas y
        # todo lo que depende de ellas, aunque sea de otra app (p. ej. reportes 0001).
        deshechas = {
            nodo
            for hijo in grafo.node_map[nodo_alertas].children
            if hijo[0] == "alertas"
            for nodo in grafo.backwards_plan(hijo)
        }
        otras = [n for n in grafo.leaf_nodes() if n[0] != "alertas" and n not in deshechas]
        return otras + [nodo_alertas]

    def _migrar(self, nodo_alertas):
        destino = self._destino(nodo_alertas)
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def _restaurar(self):
        # Deja la BD de test en el último estado de migraciones.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _columnas(self):
        with connection.cursor() as cursor:
            return {
                columna.name
                for columna in connection.introspection.get_table_description(cursor, self.TABLA)
            }

    def _constraints(self):
        with connection.cursor() as cursor:
            return set(connection.introspection.get_constraints(cursor, self.TABLA))

    def test_hacia_adelante_aplica_defaults_y_quita_frecuencia(self):
        self.addCleanup(self._restaurar)
        apps = self._migrar(self.ANTERIOR)
        Config = apps.get_model("alertas", "ConfigGeneral")
        Config.objects.update_or_create(pk=1, defaults={
            "activa": False, "frecuencia_dias": 14, "dia_semana_envio": 3,
            "hora_envio": datetime.time(9, 30), "meta_asistencia": 80,
        })

        apps = self._migrar(self.NUEVA)
        config = apps.get_model("alertas", "ConfigGeneral").objects.get(pk=1)
        self.assertEqual(config.modo, "semanal")
        self.assertEqual(config.dia_mes_envio, 1)
        # Lo demás se conserva.
        self.assertFalse(config.activa)
        self.assertEqual(config.dia_semana_envio, 3)
        self.assertEqual(config.hora_envio, datetime.time(9, 30))
        self.assertEqual(config.meta_asistencia, 80)

        columnas = self._columnas()
        self.assertNotIn("frecuencia_dias", columnas)
        self.assertLessEqual({"modo", "dia_mes_envio"}, columnas)
        constraints = self._constraints()
        self.assertNotIn("ck_config_general_frecuencia", constraints)
        self.assertLessEqual({"ck_config_general_modo", "ck_config_general_dia_mes"}, constraints)

    def test_hacia_atras_restaura_frecuencia_y_quita_los_campos_nuevos(self):
        self.addCleanup(self._restaurar)
        apps = self._migrar(self.NUEVA)
        Config = apps.get_model("alertas", "ConfigGeneral")
        Config.objects.update_or_create(pk=1, defaults={
            "modo": "mensual", "dia_mes_envio": 31, "dia_semana_envio": 2,
        })

        apps = self._migrar(self.ANTERIOR)
        Config = apps.get_model("alertas", "ConfigGeneral")
        config = Config.objects.get(pk=1)
        self.assertEqual(config.frecuencia_dias, 7)
        self.assertEqual(config.dia_semana_envio, 2)

        columnas = self._columnas()
        self.assertIn("frecuencia_dias", columnas)
        self.assertFalse({"modo", "dia_mes_envio"} & columnas)
        constraints = self._constraints()
        self.assertIn("ck_config_general_frecuencia", constraints)
        self.assertFalse({"ck_config_general_modo", "ck_config_general_dia_mes"} & constraints)
        # El constraint de frecuencia vuelve a funcionar.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Config.objects.filter(pk=1).update(frecuencia_dias=0)
