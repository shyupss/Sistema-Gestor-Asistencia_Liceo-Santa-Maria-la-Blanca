"""Envío del correo de alertas: renderizar_correo, enviar_resumen y enviar_resumenes.

Backend de correo en memoria (el de los tests de Django) o BackendQueFalla.
Roles, estados y cursos con nombres arbitrarios.
"""
import datetime
import importlib
import logging
import re
import smtplib
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.mail.backends import locmem
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch
from django.utils import timezone

from alertas.models import Funcionario, Notificacion, NotificacionCurso, Rol
from alertas.test_resumen_alertas import ResumenBase

LOGGER = "alertas.services.envio_alertas"
SITIO = "https://asistencia.example.cl/"
REMITENTE = "alertas@example.cl"
CLAVE = "clave-secreta-de-prueba"


def _envio():
    return importlib.import_module("alertas.services.envio_alertas")


def _resumen(funcionario, **kwargs):
    return importlib.import_module("alertas.services.resumen_alertas").construir_resumen(
        funcionario, **kwargs,
    )


class BackendQueFalla(locmem.EmailBackend):
    """Falla con los correos de `fallan`; los demás llegan a mail.outbox."""

    fallan = set()

    def send_messages(self, messages):
        if any(set(mensaje.to) & self.fallan for mensaje in messages):
            raise smtplib.SMTPException("falla simulada del servidor")
        return super().send_messages(messages)


@override_settings(SITE_BASE_URL=SITIO, DEFAULT_FROM_EMAIL=REMITENTE, EMAIL_HOST_PASSWORD=CLAVE)
class EnvioBase(ResumenBase):
    """Ana ve 9 alumnos en 2 cursos; Otro no tiene contenido. Sin métodos de test."""

    def setUp(self):
        super().setUp()
        self.ana = self._funcionario(self._rol("Rol general", recibe_todos=True), nombre="Ana Funcionaria")
        self.otro = self._funcionario(
            self._rol("Rol asignado", estados=[self.leve, self.grave]), nombre="Otro Funcionario",
        )
        self.beto = self._caso(self.c1a, self.grave, Decimal("40.50"), "Beto")
        self.carla = self._caso(self.c1a, self.leve, None, "Carla")
        for indice in range(7):
            self._caso(self.c2a, self.leve, 50 + indice, f"Alumno {indice + 1}")
        BackendQueFalla.fallan = set()

    def _fecha(self):
        return self.hoy.strftime("%d/%m/%Y")


class RenderizarCorreoTests(EnvioBase):
    def test_asunto_en_plural_sin_nombres_ni_saltos_de_linea(self):
        asunto = _envio().renderizar_correo(_resumen(self.ana)).asunto
        self.assertEqual(asunto, "Alertas de asistencia: 9 alumnos en 2 cursos")
        self.assertNotRegex(asunto, r"[\r\n]")
        self.assertNotIn("Beto", asunto)

    def test_asunto_en_singular(self):
        solo_grave = self._funcionario(self._rol("Rol grave", Rol.ALCANCE_TODOS, estados=[self.grave]))
        asunto = _envio().renderizar_correo(_resumen(solo_grave)).asunto
        self.assertEqual(asunto, "Alertas de asistencia: 1 alumno en 1 curso")

    def test_texto_y_html_tienen_todo_el_contenido(self):
        correo = _envio().renderizar_correo(_resumen(self.ana))
        for formato, cuerpo in (("texto", correo.texto), ("html", correo.html)):
            with self.subTest(formato=formato):
                for esperado in (
                    "Ana Funcionaria", "9 alumnos", "2 cursos",
                    "I°A", "II°A", "7 alumnos",
                    "Beto", "Grave", "Crítico", "40,5 %",
                    "Carla", "Leve", "Atención", "sin datos",
                    "Alumno 5", "y 2 más", self._fecha(),
                    "https://asistencia.example.cl/alertas/",
                ):
                    self.assertIn(esperado, cuerpo)
                # Solo se listan los primeros ALUMNOS_POR_CURSO.
                self.assertNotIn("Alumno 6", cuerpo)
                self.assertNotIn("None", cuerpo)

    def test_html_autocontenido_con_estilos_en_linea(self):
        html = _envio().renderizar_correo(_resumen(self.ana)).html
        self.assertIn('href="https://asistencia.example.cl/alertas/"', html)
        self.assertIn('style="', html)
        for prohibido in ("<img", "<link", "<style", "<script", "url("):
            with self.subTest(prohibido=prohibido):
                self.assertNotIn(prohibido, html.lower())

    def test_sin_site_base_url_no_hay_link_ni_texto_roto(self):
        with self.settings(SITE_BASE_URL=""):
            correo = _envio().renderizar_correo(_resumen(self.ana))
        for formato, cuerpo in (("texto", correo.texto), ("html", correo.html)):
            with self.subTest(formato=formato):
                self.assertNotIn("http", cuerpo)
                self.assertNotIn("href", cuerpo)
                self.assertNotIn("revisarlas", cuerpo)
                self.assertNotIn("None", cuerpo)

    def test_sin_url_con_nombre_el_link_es_la_raiz(self):
        with mock.patch.object(_envio(), "reverse", side_effect=NoReverseMatch):
            correo = _envio().renderizar_correo(_resumen(self.ana))
        self.assertIn("https://asistencia.example.cl/\n", correo.texto + "\n")
        self.assertIn('href="https://asistencia.example.cl/"', correo.html)

    def test_nombres_con_html_quedan_escapados_en_html_y_sin_escapar_en_texto(self):
        malicioso = "<script>alert(1)</script> & Cía"
        alerta = self._caso(self.c1b, self.grave, 10, malicioso)
        self.ana.nombre = "Ana & <b>Co</b>"
        correo = _envio().renderizar_correo(_resumen(self.ana))
        self.assertIn(malicioso, correo.texto)
        self.assertIn("Ana & <b>Co</b>", correo.texto)
        self.assertNotIn("&lt;", correo.texto)
        self.assertNotIn("&amp;", correo.texto)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; Cía", correo.html)
        self.assertIn("Ana &amp; &lt;b&gt;Co&lt;/b&gt;", correo.html)
        self.assertNotIn("<script", correo.html)
        self.assertNotIn("<b>Co", correo.html)
        self.assertTrue(alerta.pk)


class EnviarResumenTests(EnvioBase):
    def test_exito_envia_y_registra(self):
        ahora = timezone.now() - datetime.timedelta(minutes=5)
        resumen = _resumen(self.ana)
        correo = _envio().renderizar_correo(resumen)

        self.assertEqual(_envio().enviar_resumen(resumen, ahora=ahora), _envio().ENVIADO)

        [mensaje] = mail.outbox
        self.assertEqual(mensaje.to, [self.ana.email])
        self.assertEqual(mensaje.from_email, REMITENTE)
        self.assertEqual(mensaje.subject, correo.asunto)
        self.assertEqual(mensaje.body, correo.texto)
        self.assertEqual([tuple(a) for a in mensaje.alternatives], [(correo.html, "text/html")])
        [notificacion] = Notificacion.objects.all()
        self.assertEqual(
            (notificacion.funcionario, notificacion.fecha_envio, notificacion.canal),
            (self.ana, ahora, "email"),
        )
        self.assertEqual(
            set(NotificacionCurso.objects.filter(notificacion=notificacion).values_list("curso_id", flat=True)),
            {self.c1a.pk, self.c2a.pk},
        )

    def test_sin_ahora_usa_la_hora_actual(self):
        antes = timezone.now()
        _envio().enviar_resumen(_resumen(self.ana))
        self.assertGreaterEqual(Notificacion.objects.get().fecha_envio, antes)

    def test_con_destino_va_a_esa_direccion_con_prefijo_y_sin_registro(self):
        resultado = _envio().enviar_resumen(_resumen(self.ana), destino="pruebas@example.cl")
        self.assertEqual(resultado, _envio().ENVIADO)
        [mensaje] = mail.outbox
        self.assertEqual(mensaje.to, ["pruebas@example.cl"])
        self.assertEqual(
            mensaje.subject,
            f"[PRUEBA para {self.ana.email}] Alertas de asistencia: 9 alumnos en 2 cursos",
        )
        self.assertFalse(Notificacion.objects.exists())

    def test_funcionario_sin_correo(self):
        resumen = _resumen(self.ana)
        resumen.funcionario.email = "   "
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.assertEqual(_envio().enviar_resumen(resumen), _envio().SIN_CORREO)
        self.assertEqual(len(logs.records), 1)
        self.assertIn(str(self.ana.pk), logs.records[0].getMessage())
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Notificacion.objects.exists())

    @override_settings(EMAIL_BACKEND="alertas.test_envio_alertas.BackendQueFalla")
    def test_fallo_del_backend(self):
        BackendQueFalla.fallan = {self.ana.email}
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            self.assertEqual(_envio().enviar_resumen(_resumen(self.ana)), _envio().FALLIDO)
        [registro] = logs.records
        self.assertIn(str(self.ana.pk), registro.getMessage())
        completo = registro.getMessage() + logging.Formatter().formatException(registro.exc_info)
        for prohibido in (CLAVE, "Beto", "Carla"):
            self.assertNotIn(prohibido, completo)
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Notificacion.objects.exists())

    def test_fallo_del_registro_tras_un_envio_exitoso(self):
        with mock.patch.object(
            NotificacionCurso.objects, "bulk_create", side_effect=RuntimeError("falla del registro"),
        ), self.assertLogs(LOGGER, level="ERROR") as logs:
            resultado = _envio().enviar_resumen(_resumen(self.ana))
        self.assertEqual(resultado, _envio().ENVIADO)
        self.assertEqual(len(mail.outbox), 1)
        [registro] = logs.records
        self.assertIn("no se pudo registrar", registro.getMessage())
        self.assertIn(str(self.ana.pk), registro.getMessage())
        # La transacción del registro se deshizo completa.
        self.assertFalse(Notificacion.objects.exists())


class EnviarResumenesTests(EnvioBase):
    def setUp(self):
        super().setUp()
        self.sin_correo = self._funcionario(self._rol("Rol general 2", recibe_todos=True))
        Funcionario.objects.filter(pk=self.sin_correo.pk).update(email="   ")
        self.sin_permiso = self._funcionario(
            self._rol("Rol general sin permiso", recibe_todos=True, con_permiso=False),
        )

    def test_contadores_y_detalle_por_funcionario(self):
        envio = _envio()
        with self.assertLogs(LOGGER, level="WARNING"):
            resultado = envio.enviar_resumenes()
        self.assertEqual(
            (resultado.enviados, resultado.fallidos, resultado.sin_correo, resultado.sin_contenido),
            (1, 0, 1, 1),
        )
        self.assertEqual(
            [(d.funcionario, d.resultado) for d in resultado.detalle],
            [(self.ana, envio.ENVIADO), (self.otro, envio.SIN_CONTENIDO),
             (self.sin_correo, envio.SIN_CORREO)],
        )
        # Solo los destinatarios con contenido y correo reciben algo.
        self.assertEqual([m.to for m in mail.outbox], [[self.ana.email]])
        self.assertEqual(list(Notificacion.objects.values_list("funcionario_id", flat=True)), [self.ana.pk])

    def test_respeta_el_parametro_funcionarios(self):
        envio = _envio()
        resultado = envio.enviar_resumenes([self.otro])
        self.assertEqual((resultado.enviados, resultado.sin_contenido), (0, 1))
        self.assertEqual(mail.outbox, [])
        resultado = envio.enviar_resumenes(Funcionario.objects.filter(pk=self.ana.pk))
        self.assertEqual([(d.funcionario, d.resultado) for d in resultado.detalle], [(self.ana, envio.ENVIADO)])

    def test_destino_en_todos_los_envios_sin_registro(self):
        resultado = _envio().enviar_resumenes(destino="pruebas@example.cl")
        # Con destino, el funcionario sin correo también recibe la prueba en esa dirección.
        self.assertEqual(resultado.enviados, 2)
        self.assertEqual([m.to for m in mail.outbox], [["pruebas@example.cl"]] * 2)
        self.assertTrue(mail.outbox[1].subject.startswith("[PRUEBA para sin correo] "))
        self.assertFalse(Notificacion.objects.exists())

    @override_settings(EMAIL_BACKEND="alertas.test_envio_alertas.BackendQueFalla")
    def test_un_fallo_no_detiene_a_los_demas(self):
        otra = self._funcionario(self._rol("Rol general 3", recibe_todos=True))
        BackendQueFalla.fallan = {self.ana.email}
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            resultado = _envio().enviar_resumenes([self.ana, otra])
        self.assertEqual((resultado.enviados, resultado.fallidos), (1, 1))
        self.assertEqual([m.to for m in mail.outbox], [[otra.email]])
        self.assertEqual(list(Notificacion.objects.values_list("funcionario_id", flat=True)), [otra.pk])
        self.assertEqual([r.levelname for r in logs.records], ["ERROR"])

    def test_sin_periodo_todos_sin_contenido(self):
        resultado = _envio().enviar_resumenes(hoy=datetime.date(1990, 6, 1))
        self.assertEqual((resultado.enviados, resultado.sin_contenido), (0, 3))
        self.assertEqual(mail.outbox, [])


class IndependenciaTests(TestCase):
    """Los módulos nuevos no importan de monitoreo ni de asistencia, ni nombran roles o estados."""

    MODULOS = (
        "services/formato.py",
        "services/envio_alertas.py",
        "management/commands/enviar_resumenes_alertas.py",
    )
    # Etiquetas de los dos niveles de gravedad del correo (las pide el formato), no
    # nombres de Estado: se excluye exactamente esa definición.
    ETIQUETAS_NIVEL = 'ETIQUETAS_NIVEL = {"critico": "Crítico", "atencion": "Atención"}'

    def _codigos(self):
        base = Path(importlib.import_module("alertas").__file__).resolve().parent
        codigos = {modulo: (base / modulo).read_text(encoding="utf-8") for modulo in self.MODULOS}
        self.assertIn(self.ETIQUETAS_NIVEL, codigos["services/formato.py"])
        codigos["services/formato.py"] = codigos["services/formato.py"].replace(self.ETIQUETAS_NIVEL, "")
        return codigos

    def test_no_importan_de_monitoreo_ni_asistencia(self):
        for modulo, codigo in self._codigos().items():
            for app in ("monitoreo", "asistencia"):
                with self.subTest(modulo=modulo, app=app):
                    self.assertIsNone(
                        re.search(rf"^\s*(from|import)\s+{app}\b", codigo, re.MULTILINE)
                    )

    def test_no_nombran_roles_ni_estados(self):
        for modulo, codigo in self._codigos().items():
            for nombre in (
                "asistente social", "rector", "inspector", "profesor jefe",
                "óptimo", "adecuado", "atención", "crítico",
            ):
                with self.subTest(modulo=modulo, nombre=nombre):
                    self.assertIsNone(re.search(rf"\b{re.escape(nombre)}\b", codigo.lower()))
