import copy
import importlib

from django.contrib.auth import get_user_model
from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory, TestCase
from django.urls import reverse

from academico.constantes import (
    ESTADO_MATRICULA_CAMBIO_CURSO,
    ESTADO_MATRICULA_EGRESADO,
    ESTADO_MATRICULA_RETIRADO,
    ESTADO_MATRICULA_VIGENTE,
    ESTADOS_MATRICULA,
)
from academico.models import EstadoMatricula
from asistencia import constantes
from asistencia.models import Estados_Solicitud, Tipos_Asistencia

migracion = importlib.import_module("asistencia.migrations.0005_catalogos_iniciales")


def _diferencias(actual, esperado):
    """Devuelve las claves cuyo valor difiere o que faltan/sobran."""
    return {
        clave for clave in set(actual) | set(esperado)
        if actual.get(clave, object()) != esperado.get(clave, object())
    }


class ConstantesCoincidenConMigracionTests(TestCase):
    def test_tipos_asistencia_igual_a_la_migracion_0005(self):
        self.assertEqual(constantes.TIPOS_ASISTENCIA, migracion.TIPOS_ASISTENCIA)

    def test_estados_solicitud_igual_a_la_migracion_0005(self):
        # Compara banderas y descripciones.
        self.assertEqual(constantes.ESTADOS_SOLICITUD, migracion.ESTADOS_SOLICITUD)

    def test_constantes_sueltas_son_las_claves_de_los_dicts(self):
        self.assertEqual(
            {constantes.TIPO_PRESENTE, constantes.TIPO_AUSENTE,
             constantes.TIPO_ATRASADO, constantes.TIPO_JUSTIFICADO},
            set(migracion.TIPOS_ASISTENCIA),
        )
        self.assertEqual(
            {constantes.ESTADO_PENDIENTE, constantes.ESTADO_ACEPTADA, constantes.ESTADO_RECHAZADA},
            set(migracion.ESTADOS_SOLICITUD),
        )

    def test_nombres_en_minusculas_exactas(self):
        nombres = [
            *constantes.TIPOS_ASISTENCIA, *constantes.ESTADOS_SOLICITUD, *ESTADOS_MATRICULA,
        ]
        for nombre in nombres:
            self.assertEqual(nombre, nombre.lower().strip())
            self.assertTrue(nombre.isascii())

    def test_estados_matricula(self):
        self.assertEqual(ESTADOS_MATRICULA, {
            ESTADO_MATRICULA_VIGENTE: "Alumno con matrícula vigente",
            ESTADO_MATRICULA_CAMBIO_CURSO: "Matrícula cerrada porque el alumno pasó a otro curso del liceo",
            ESTADO_MATRICULA_RETIRADO: "Alumno que se retiró del liceo",
            ESTADO_MATRICULA_EGRESADO: "Alumno que egresó del liceo",
        })
        self.assertEqual(
            (
                ESTADO_MATRICULA_VIGENTE, ESTADO_MATRICULA_CAMBIO_CURSO,
                ESTADO_MATRICULA_RETIRADO, ESTADO_MATRICULA_EGRESADO,
            ),
            ("vigente", "cambio_curso", "retirado", "egresado"),
        )
        # "fin_matricula" es un motivo de cierre de alertas, no un estado de matrícula.
        self.assertNotIn("fin_matricula", ESTADOS_MATRICULA)

    # --- Demuestran que la comparación detecta desfases -------------------

    def test_detecta_bandera_distinta_en_tipos(self):
        copia = dict(constantes.TIPOS_ASISTENCIA)
        copia[constantes.TIPO_ATRASADO] = False
        self.assertNotEqual(copia, migracion.TIPOS_ASISTENCIA)
        self.assertEqual(_diferencias(copia, migracion.TIPOS_ASISTENCIA), {"atrasado"})

    def test_detecta_descripcion_distinta_en_estados(self):
        copia = copy.deepcopy(constantes.ESTADOS_SOLICITUD)
        final, cubre, _ = copia[constantes.ESTADO_RECHAZADA]
        copia[constantes.ESTADO_RECHAZADA] = (final, cubre, "otra descripción")
        self.assertNotEqual(copia, migracion.ESTADOS_SOLICITUD)
        self.assertEqual(_diferencias(copia, migracion.ESTADOS_SOLICITUD), {"rechazada"})

    def test_detecta_banderas_distintas_en_estados(self):
        copia = copy.deepcopy(constantes.ESTADOS_SOLICITUD)
        _, cubre, desc = copia[constantes.ESTADO_PENDIENTE]
        copia[constantes.ESTADO_PENDIENTE] = (True, cubre, desc)
        self.assertNotEqual(copia, migracion.ESTADOS_SOLICITUD)

    def test_detecta_fila_agregada_o_quitada(self):
        copia = dict(constantes.TIPOS_ASISTENCIA)
        copia["nuevo"] = False
        self.assertNotEqual(copia, migracion.TIPOS_ASISTENCIA)
        copia = dict(constantes.TIPOS_ASISTENCIA)
        del copia[constantes.TIPO_JUSTIFICADO]
        self.assertNotEqual(copia, migracion.TIPOS_ASISTENCIA)


class CatalogosSoloLecturaAdminTests(TestCase):
    MODELOS = (Tipos_Asistencia, Estados_Solicitud, EstadoMatricula)

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username="root", email="root@example.com", password="clave-segura-123",
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_permisos_del_modeladmin(self):
        request = RequestFactory().get("/")
        request.user = self.admin_user
        for modelo in self.MODELOS:
            with self.subTest(modelo=modelo.__name__):
                modeladmin = admin_site._registry[modelo]
                self.assertFalse(modeladmin.has_add_permission(request))
                self.assertFalse(modeladmin.has_change_permission(request))
                self.assertFalse(modeladmin.has_delete_permission(request))
                self.assertTrue(modeladmin.has_view_permission(request))

    def test_listado_visible_y_alta_prohibida(self):
        for modelo in self.MODELOS:
            meta = modelo._meta
            with self.subTest(modelo=modelo.__name__):
                listado = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
                alta = reverse(f"admin:{meta.app_label}_{meta.model_name}_add")
                self.assertEqual(self.client.get(listado).status_code, 200)
                self.assertEqual(self.client.get(alta).status_code, 403)
                self.assertEqual(
                    self.client.post(alta, {"nombre": "nuevo"}).status_code, 403,
                )
                self.assertFalse(modelo.objects.filter(nombre="nuevo").exists())

    def test_cambio_y_borrado_prohibidos(self):
        for modelo in self.MODELOS:
            meta = modelo._meta
            with self.subTest(modelo=modelo.__name__):
                objeto = modelo.objects.first() or modelo.objects.create(nombre="existente")
                base = f"admin:{meta.app_label}_{meta.model_name}"
                cambio = reverse(f"{base}_change", args=[objeto.pk])
                borrar = reverse(f"{base}_delete", args=[objeto.pk])
                # Con permiso de solo vista, la ficha se muestra pero no se guarda.
                self.assertEqual(self.client.get(cambio).status_code, 200)
                self.assertEqual(self.client.post(cambio, {"nombre": "x"}).status_code, 403)
                self.assertEqual(self.client.get(borrar).status_code, 403)
                self.assertEqual(self.client.post(borrar, {"post": "yes"}).status_code, 403)
                self.assertTrue(modelo.objects.filter(pk=objeto.pk).exists())
