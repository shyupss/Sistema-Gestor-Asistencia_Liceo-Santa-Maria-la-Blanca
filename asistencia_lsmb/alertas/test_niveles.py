"""Niveles de alerta: el código vive en alertas.services.niveles y monitoreo solo lo reexporta.

Los nombres de los estados son arbitrarios: solo importan es_no_ideal y umbral_minimo.
"""
import importlib
import inspect
import re
from decimal import Decimal

from django.test import TestCase

from alertas.models import Estado


def _niveles():
    return importlib.import_module("alertas.services.niveles")


def _estado(nombre, umbral, es_no_ideal=True):
    return Estado.objects.create(nombre=nombre, umbral_minimo=umbral, es_no_ideal=es_no_ideal)


class NivelesEnAlertasTests(TestCase):
    def test_el_no_ideal_de_menor_umbral_es_critico_y_los_demas_atencion(self):
        niveles = _niveles()
        _estado("Ideal", 90, es_no_ideal=False)
        uno, dos, tres = _estado("Uno", 80), _estado("Dos", 50), _estado("Tres", 20)
        umbral = niveles.umbral_critico()
        self.assertEqual(umbral, Decimal("20"))
        self.assertEqual(niveles.nivel_alerta(tres, umbral), "critico")
        self.assertEqual(niveles.nivel_alerta(dos, umbral), "atencion")
        self.assertEqual(niveles.nivel_alerta(uno, umbral), "atencion")

    def test_un_unico_no_ideal_es_critico(self):
        niveles = _niveles()
        unico = _estado("Unico", 60)
        _estado("Ideal", 95, es_no_ideal=False)
        self.assertEqual(niveles.nivel_alerta(unico, niveles.umbral_critico()), "critico")

    def test_el_umbral_sale_del_catalogo_completo(self):
        niveles = _niveles()
        intermedio = _estado("Intermedio", 75)
        _estado("Mas bajo", 0)
        self.assertEqual(niveles.nivel_alerta(intermedio, niveles.umbral_critico()), "atencion")

    def test_sin_no_ideales_el_umbral_es_none_y_cae_en_atencion(self):
        niveles = _niveles()
        ideal = _estado("Ideal", 90, es_no_ideal=False)
        self.assertIsNone(niveles.umbral_critico())
        self.assertEqual(niveles.nivel_alerta(ideal, None), "atencion")


class ReenvioDesdeMonitoreoTests(TestCase):
    def test_monitoreo_expone_los_mismos_objetos(self):
        niveles = _niveles()
        reenvio = importlib.import_module("monitoreo.services.niveles")
        self.assertIs(reenvio.umbral_critico, niveles.umbral_critico)
        self.assertIs(reenvio.nivel_alerta, niveles.nivel_alerta)
        self.assertEqual(sorted(reenvio.__all__), ["nivel_alerta", "umbral_critico"])

    def test_el_codigo_vive_en_alertas_y_monitoreo_no_define_nada(self):
        niveles = _niveles()
        for funcion in (niveles.umbral_critico, niveles.nivel_alerta):
            with self.subTest(funcion=funcion.__name__):
                self.assertEqual(funcion.__module__, "alertas.services.niveles")
                self.assertTrue(funcion.__doc__)
        codigo = inspect.getsource(importlib.import_module("monitoreo.services.niveles"))
        self.assertIsNone(re.search(r"^\s*(def|class)\s", codigo, re.MULTILINE))
