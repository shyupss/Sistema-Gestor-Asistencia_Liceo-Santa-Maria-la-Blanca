import importlib

from django.apps import apps as apps_reales
from django.test import TestCase

from asistencia.models import Estados_Solicitud, Tipos_Asistencia


def _sembrar():
    modulo = importlib.import_module("asistencia.migrations.0005_catalogos_iniciales")
    modulo.sembrar_catalogos(apps_reales, None)


class CatalogosInicialesTests(TestCase):
    def setUp(self):
        # No se asume el contenido previo de la BD (los TransactionTestCase la vacían).
        Tipos_Asistencia.objects.all().delete()
        Estados_Solicitud.objects.all().delete()

    def test_siembra_los_cuatro_tipos_de_asistencia(self):
        _sembrar()
        self.assertEqual(
            dict(Tipos_Asistencia.objects.values_list("nombre", "cuenta_como_ausencia")),
            {"presente": False, "ausente": True, "atrasado": True, "justificado": False},
        )

    def test_siembra_los_estados_de_solicitud_con_sus_banderas(self):
        _sembrar()
        self.assertEqual(
            {
                e.nombre: (e.es_estado_final, e.cubre_ausencia, e.descripcion)
                for e in Estados_Solicitud.objects.all()
            },
            {
                "pendiente": (False, False, "Solicitud pendiente de revisión."),
                "aceptada": (True, True, "Solicitud aceptada; cubre la ausencia."),
                "rechazada": (True, False, "Solicitud rechazada; no cubre la ausencia."),
            },
        )

    def test_es_estado_final_pendiente_false_y_aceptada_rechazada_true(self):
        # justificaciones_ficha.py usa es_estado_final para decidir si una solicitud sigue pendiente.
        _sembrar()
        self.assertFalse(Estados_Solicitud.objects.get(nombre="pendiente").es_estado_final)
        self.assertTrue(Estados_Solicitud.objects.get(nombre="aceptada").es_estado_final)
        self.assertTrue(Estados_Solicitud.objects.get(nombre="rechazada").es_estado_final)

    def test_es_idempotente(self):
        _sembrar()
        _sembrar()
        self.assertEqual(Tipos_Asistencia.objects.count(), 4)
        self.assertEqual(Estados_Solicitud.objects.count(), 3)

    def test_no_pisa_valores_existentes(self):
        Tipos_Asistencia.objects.create(nombre="atrasado", cuenta_como_ausencia=False)
        Estados_Solicitud.objects.create(
            nombre="rechazada", es_estado_final=False, cubre_ausencia=True, descripcion="editada",
        )
        _sembrar()
        self.assertFalse(Tipos_Asistencia.objects.get(nombre="atrasado").cuenta_como_ausencia)
        rechazada = Estados_Solicitud.objects.get(nombre="rechazada")
        self.assertFalse(rechazada.es_estado_final)
        self.assertTrue(rechazada.cubre_ausencia)
        self.assertEqual(rechazada.descripcion, "editada")

    def test_la_busqueda_por_nombre_ignora_mayusculas(self):
        Tipos_Asistencia.objects.create(nombre="Presente", cuenta_como_ausencia=False)
        Estados_Solicitud.objects.create(nombre="Pendiente")
        _sembrar()
        self.assertEqual(Tipos_Asistencia.objects.filter(nombre__iexact="presente").count(), 1)
        self.assertEqual(Estados_Solicitud.objects.filter(nombre__iexact="pendiente").count(), 1)
        self.assertEqual(Tipos_Asistencia.objects.count(), 4)
        self.assertEqual(Estados_Solicitud.objects.count(), 3)

    def test_renombra_aprobada_a_aceptada_si_no_existe_aceptada(self):
        aprobada = Estados_Solicitud.objects.create(
            nombre="aprobada", es_estado_final=True, cubre_ausencia=True,
            descripcion="Solicitud aprobada; cubre la ausencia.",
        )
        _sembrar()
        aprobada.refresh_from_db()
        self.assertEqual(aprobada.nombre, "aceptada")
        self.assertEqual(aprobada.descripcion, "Solicitud aceptada; cubre la ausencia.")
        self.assertFalse(Estados_Solicitud.objects.filter(nombre__iexact="aprobada").exists())
        self.assertEqual(Estados_Solicitud.objects.count(), 3)

    def test_no_renombra_si_ya_existe_aceptada(self):
        Estados_Solicitud.objects.create(nombre="aprobada")
        Estados_Solicitud.objects.create(nombre="aceptada", es_estado_final=True, cubre_ausencia=True)
        _sembrar()
        self.assertTrue(Estados_Solicitud.objects.filter(nombre="aprobada").exists())
        self.assertEqual(Estados_Solicitud.objects.filter(nombre__iexact="aceptada").count(), 1)
