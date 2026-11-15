import importlib

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

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
