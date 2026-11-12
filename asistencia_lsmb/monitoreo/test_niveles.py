from decimal import Decimal

from django.test import TestCase

from alertas.models import Estado
from monitoreo.services.niveles import nivel_alerta, umbral_critico


def _estado(nombre, umbral, es_no_ideal=True):
    return Estado.objects.create(
        nombre=nombre, umbral_minimo=umbral,
        es_no_ideal=es_no_ideal, genera_alerta=es_no_ideal,
    )


class NivelAlertaTests(TestCase):
    def test_menor_umbral_no_ideal_es_critico_y_mayor_es_atencion(self):
        _estado("Adecuado", 85, es_no_ideal=False)
        atencion = _estado("Atención", 75)
        critico = _estado("Crítico", 0)
        umbral = umbral_critico()
        self.assertEqual(umbral, Decimal("0"))
        self.assertEqual(nivel_alerta(critico, umbral), "critico")
        self.assertEqual(nivel_alerta(atencion, umbral), "atencion")

    def test_con_tercer_estado_no_ideal_solo_el_menor_es_critico(self):
        leve = _estado("Leve", 85)
        atencion = _estado("Atención", 75)
        critico = _estado("Crítico", 40)
        umbral = umbral_critico()
        self.assertEqual(nivel_alerta(critico, umbral), "critico")
        self.assertEqual(nivel_alerta(atencion, umbral), "atencion")
        self.assertEqual(nivel_alerta(leve, umbral), "atencion")

    def test_unico_estado_no_ideal_es_critico(self):
        unico = _estado("Alerta", 60)
        _estado("Óptimo", 95, es_no_ideal=False)
        self.assertEqual(nivel_alerta(unico, umbral_critico()), "critico")

    def test_umbral_critico_viene_del_catalogo_no_de_los_alumnos(self):
        # Aunque solo se clasifique el estado intermedio, sigue siendo "atencion"
        # porque el umbral crítico se calcula con todo el catálogo.
        atencion = _estado("Atención", 75)
        _estado("Crítico", 0)
        self.assertEqual(nivel_alerta(atencion, umbral_critico()), "atencion")

    def test_sin_estados_no_ideales_umbral_es_none_y_cae_en_atencion(self):
        normal = _estado("Normal", 90, es_no_ideal=False)
        self.assertIsNone(umbral_critico())
        self.assertEqual(nivel_alerta(normal, None), "atencion")
