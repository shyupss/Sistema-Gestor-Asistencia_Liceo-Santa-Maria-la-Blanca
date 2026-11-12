from django.test import SimpleTestCase

from alertas.models import Estado
from monitoreo.services.niveles import nivel_alerta


class NivelAlertaTests(SimpleTestCase):
    def test_codigo_critico_es_critico(self):
        self.assertEqual(nivel_alerta(Estado(nombre="X", codigo="critico")), "critico")

    def test_codigo_atencion_es_atencion(self):
        self.assertEqual(nivel_alerta(Estado(nombre="X", codigo="atencion")), "atencion")

    def test_sin_codigo_cae_en_atencion(self):
        self.assertEqual(nivel_alerta(Estado(nombre="Crítico")), "atencion")
