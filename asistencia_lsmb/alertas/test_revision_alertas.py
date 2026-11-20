"""Revisión de alertas: marcar_revisada, curso_del_alumno_en_periodo, funcionario_actual y POST /alertas/<id>/revisar/.

Las fechas son relativas a hoy: los períodos abarcan hoy, así que los tests no
dependen del día en que se corren.
"""
import datetime
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas import views as alertas_views
from alertas.models import (
    Alerta, Cargo, Cuenta, Estado, EstadoAlumno, Funcionario, FuncionarioCurso, Permiso, Rol,
    RolPermiso,
)
from alertas.queries import alcance_queries
from alertas.services import alertas_service

UN_DIA = datetime.timedelta(days=1)
CORREO_REVISOR = "funcionario1@liceo.cl"


class RevisionBase(TestCase):
    def setUp(self):
        self.ahora = timezone.now()
        self.hoy = timezone.localdate(self.ahora)
        self.periodo = self._periodo(self.hoy.year)
        self.otro_periodo = self._periodo(self.hoy.year - 1)
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.otro_curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="B")
        # Los nombres no importan: solo se mira es_no_ideal.
        self.bajo = Estado.objects.create(nombre="Bajo", umbral_minimo=60, es_no_ideal=True)
        self.bien = Estado.objects.create(nombre="Bien", umbral_minimo=90, es_no_ideal=False)
        self.cargo = Cargo.objects.create(nombre="Cargo de los tests de revisión")

        permiso = Permiso.objects.get_or_create(
            codigo="revisar_alertas", defaults={"nombre": "Revisar alertas"},
        )[0]
        self.rol_seleccionados = self._rol("Rol seleccionados", Rol.ALCANCE_SELECCIONADOS, permiso)
        self.rol_todos = self._rol("Rol todos", Rol.ALCANCE_TODOS, permiso)
        self.rol_sin_permiso = self._rol("Rol sin permiso", Rol.ALCANCE_TODOS)

        # Revisor con alcance "seleccionados" y el curso del alumno asignado.
        self.revisor = self._funcionario(1, self.rol_seleccionados)
        FuncionarioCurso.objects.create(funcionario=self.revisor, curso=self.curso)

        self.alumno = self._alumno(1)
        self._matricula(self.alumno, self.curso)
        self.estado_alumno = EstadoAlumno.objects.create(
            alumno=self.alumno, periodo=self.periodo, estado=self.bajo, porcentaje_asistencia=70,
        )
        self.alerta = self._alerta(self.alumno)

    # --- datos ---

    def _periodo(self, anio):
        return PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=self.hoy - 60 * UN_DIA, fecha_fin=self.hoy + 60 * UN_DIA,
        )

    def _rol(self, nombre, alcance, permiso=None):
        rol = Rol.objects.create(nombre=nombre, alcance=alcance)
        if permiso is not None:
            RolPermiso.objects.create(rol=rol, permiso=permiso)
        return rol

    def _funcionario(self, numero, rol=None, activo=True, cuenta_activa=True):
        funcionario = Funcionario.objects.create(
            cargo=self.cargo, rut=f"{numero}2222222-{numero}", nombre=f"Funcionario {numero}",
            email=f"funcionario{numero}@liceo.cl", activo=activo,
        )
        if rol is not None:
            Cuenta.objects.create(funcionario=funcionario, rol=rol, activo=cuenta_activa)
        return funcionario

    def _alumno(self, numero):
        return Alumno.objects.create(nombre=f"Alumno {numero}", rut=f"{numero}111111-{numero}")

    def _matricula(self, alumno, curso, fecha_matricula=None, fecha_termino=None):
        return Matricula.objects.create(
            alumno=alumno, curso=curso, periodo=curso.periodo,
            estado_matricula=EstadoMatricula.objects.get_or_create(nombre="vigente")[0],
            fecha_matricula=fecha_matricula or self.hoy - 30 * UN_DIA,
            fecha_termino=fecha_termino,
        )

    def _alerta(self, alumno, periodo=None, **campos):
        return Alerta.objects.create(
            alumno=alumno, periodo=periodo or self.periodo, estado=self.bajo, **campos,
        )

    # --- utilidades ---

    def _revisar(self, alerta=None, funcionario=None, **kwargs):
        kwargs.setdefault("ahora", self.ahora)
        return alertas_service.marcar_revisada(
            alerta or self.alerta, funcionario or self.revisor, **kwargs,
        )

    def _foto(self, alerta=None):
        return Alerta.objects.values().get(pk=(alerta or self.alerta).pk)

    def _sin_revisar(self, alerta=None):
        Alerta.objects.filter(pk=(alerta or self.alerta).pk).update(
            revisada=False, funcionario_revisa=None, fecha_revision=None, nota=None,
        )


class MarcarRevisadaTests(RevisionBase):
    def test_exito_guarda_la_revision_sin_cerrar_ni_tocar_el_estado_del_alumno(self):
        estado_antes = EstadoAlumno.objects.values().get(pk=self.estado_alumno.pk)
        devuelta = self._revisar(nota="  Se llamó al apoderado.  ")

        self.assertEqual(devuelta.pk, self.alerta.pk)
        guardada = Alerta.objects.get(pk=self.alerta.pk)
        for alerta in (devuelta, guardada):
            with self.subTest(alerta="devuelta" if alerta is devuelta else "guardada"):
                self.assertTrue(alerta.revisada)
                self.assertEqual(alerta.funcionario_revisa, self.revisor)
                self.assertEqual(alerta.fecha_revision, self.ahora)
                self.assertEqual(alerta.nota, "Se llamó al apoderado.")
                self.assertIsNone(alerta.fecha_cierre)
                self.assertIsNone(alerta.motivo_cierre)
                self.assertEqual(alerta.estado, self.bajo)
        self.assertEqual(EstadoAlumno.objects.values().get(pk=self.estado_alumno.pk), estado_antes)

    def test_sin_ahora_usa_la_hora_actual(self):
        antes = timezone.now()
        alertas_service.marcar_revisada(self.alerta, self.revisor)
        self.alerta.refresh_from_db()
        self.assertGreaterEqual(self.alerta.fecha_revision, antes)
        self.assertLessEqual(self.alerta.fecha_revision, timezone.now())

    def test_nota_vacia_o_en_blanco_queda_en_null(self):
        for nota in (None, "", "   ", "\n\t "):
            with self.subTest(nota=nota):
                self._sin_revisar()
                self.assertIsNone(self._revisar(nota=nota).nota)
                self.assertIsNone(self._foto()["nota"])
                self.assertTrue(self._foto()["revisada"])

    def test_nota_de_1000_caracteres_pasa_aunque_traiga_espacios_alrededor(self):
        self._revisar(nota="  " + "x" * 1000 + "  ")
        self.assertEqual(self._foto()["nota"], "x" * 1000)

    def test_nota_de_1001_caracteres_da_nota_invalida_y_no_guarda_nada(self):
        antes = self._foto()
        with self.assertRaises(alertas_service.NotaInvalida):
            self._revisar(nota="x" * 1001)
        self.assertEqual(self._foto(), antes)

    def test_nota_que_no_es_texto_da_nota_invalida(self):
        antes = self._foto()
        for nota in (123, ["texto"], {"nota": "texto"}, b"texto", True):
            with self.subTest(nota=nota), self.assertRaises(alertas_service.NotaInvalida):
                self._revisar(nota=nota)
        self.assertEqual(self._foto(), antes)

    def test_sin_permiso(self):
        sin_cuenta = self._funcionario(2)
        casos = {
            "rol sin el permiso": self._funcionario(3, self.rol_sin_permiso),
            "cuenta inactiva": self._funcionario(4, self.rol_todos, cuenta_activa=False),
            "funcionario inactivo": self._funcionario(5, self.rol_todos, activo=False),
            "funcionario sin cuenta": sin_cuenta,
        }
        antes = self._foto()
        for caso, funcionario in casos.items():
            with self.subTest(caso=caso), self.assertRaises(alertas_service.SinPermiso):
                self._revisar(funcionario=funcionario)
        self.assertEqual(self._foto(), antes)

    def test_seleccionados_sin_el_curso_queda_fuera_de_alcance(self):
        otro = self._funcionario(2, self.rol_seleccionados)
        FuncionarioCurso.objects.create(funcionario=otro, curso=self.otro_curso)
        antes = self._foto()
        with self.assertRaises(alertas_service.FueraDeAlcance):
            self._revisar(funcionario=otro)
        self.assertEqual(self._foto(), antes)

    def test_seleccionados_con_la_jefatura_del_curso_puede_revisar(self):
        jefe = self._funcionario(2, self.rol_seleccionados)
        self.curso.profesor_jefe = jefe
        self.curso.save()
        self.assertEqual(self._revisar(funcionario=jefe).funcionario_revisa, jefe)

    def test_rol_todos_puede_revisar(self):
        todos = self._funcionario(2, self.rol_todos)
        self.assertEqual(self._revisar(funcionario=todos).funcionario_revisa, todos)

    def test_alumno_sin_matricula_en_el_periodo_queda_fuera_de_alcance(self):
        sin_matricula = self._alumno(2)
        # Tiene matrícula, pero en otro período.
        self._matricula(sin_matricula, Curso.objects.create(periodo=self.otro_periodo, nivel=1, grupo="A"))
        alerta = self._alerta(sin_matricula)
        todos = self._funcionario(2, self.rol_todos)
        with self.assertRaises(alertas_service.FueraDeAlcance):
            self._revisar(alerta=alerta, funcionario=todos)
        self.assertFalse(self._foto(alerta)["revisada"])

    def test_alerta_cerrada(self):
        Alerta.objects.filter(pk=self.alerta.pk).update(
            fecha_cierre=self.ahora - UN_DIA, motivo_cierre="recuperado",
        )
        antes = self._foto()
        with self.assertRaises(alertas_service.AlertaCerrada):
            self._revisar()
        self.assertEqual(self._foto(), antes)

    def test_ya_revisada_no_cambia_al_revisor_original(self):
        self._revisar(nota="Primera revisión")
        antes = self._foto()
        otro = self._funcionario(2, self.rol_todos)
        with self.assertRaises(alertas_service.AlertaYaRevisada):
            self._revisar(funcionario=otro, nota="Segunda", ahora=self.ahora + UN_DIA)
        self.assertEqual(self._foto(), antes)
        self.assertEqual(antes["funcionario_revisa_id"], self.revisor.pk)

    def test_revisa_el_estado_de_la_bd_y_no_el_de_la_instancia(self):
        # La instancia en memoria está desactualizada: en la BD ya se cerró.
        Alerta.objects.filter(pk=self.alerta.pk).update(fecha_cierre=self.ahora)
        with self.assertRaises(alertas_service.AlertaCerrada):
            self._revisar()

    def test_orden_permiso_antes_que_alerta_cerrada(self):
        Alerta.objects.filter(pk=self.alerta.pk).update(fecha_cierre=self.ahora)
        with self.assertRaises(alertas_service.SinPermiso):
            self._revisar(funcionario=self._funcionario(2, self.rol_sin_permiso))

    def test_orden_alcance_antes_que_ya_revisada(self):
        self._revisar()
        otro = self._funcionario(2, self.rol_seleccionados)
        with self.assertRaises(alertas_service.FueraDeAlcance):
            self._revisar(funcionario=otro)

    def test_orden_nota_antes_que_alerta_cerrada(self):
        Alerta.objects.filter(pk=self.alerta.pk).update(fecha_cierre=self.ahora)
        with self.assertRaises(alertas_service.NotaInvalida):
            self._revisar(nota="x" * 1001)

    def test_usa_el_curso_de_la_matricula_mas_reciente_si_el_barrido_esta_pendiente(self):
        alumno = self._alumno(2)
        self._matricula(
            alumno, self.otro_curso,
            fecha_matricula=self.hoy - 50 * UN_DIA, fecha_termino=self.hoy - 20 * UN_DIA,
        )
        self._matricula(
            alumno, self.curso,
            fecha_matricula=self.hoy - 20 * UN_DIA, fecha_termino=self.hoy - UN_DIA,
        )
        alerta = self._alerta(alumno)  # vigente: el barrido aún no la cerró
        self.assertTrue(self._revisar(alerta=alerta).revisada)

    def test_no_afecta_otras_alertas_y_la_sincronizacion_la_deja_revisada(self):
        otro_alumno = self._alumno(2)
        self._matricula(otro_alumno, self.curso)
        otra_del_periodo = self._alerta(otro_alumno)
        del_otro_periodo = self._alerta(self.alumno, self.otro_periodo)
        antes = [self._foto(otra_del_periodo), self._foto(del_otro_periodo)]

        self._revisar()

        self.assertEqual([self._foto(otra_del_periodo), self._foto(del_otro_periodo)], antes)
        resultado = alertas_service.sincronizar_alerta(
            self.alumno, self.periodo, self.bajo, ahora=self.ahora + UN_DIA,
        )
        self.assertEqual(resultado, "sin_cambio")
        foto = self._foto()
        self.assertIsNone(foto["fecha_cierre"])
        self.assertTrue(foto["revisada"])
        self.assertEqual(foto["funcionario_revisa_id"], self.revisor.pk)

    def test_las_excepciones_son_subclases_de_alerta_error(self):
        self.assertTrue(issubclass(alertas_service.AlertaError, Exception))
        for nombre in ("SinPermiso", "FueraDeAlcance", "NotaInvalida", "AlertaCerrada", "AlertaYaRevisada"):
            with self.subTest(excepcion=nombre):
                self.assertTrue(issubclass(getattr(alertas_service, nombre), alertas_service.AlertaError))

    def test_constante_del_permiso(self):
        self.assertEqual(alertas_service.PERMISO_REVISAR_ALERTAS, "revisar_alertas")


class CursoDelAlumnoTests(RevisionBase):
    def _curso_del_alumno(self, alumno):
        return alcance_queries.curso_del_alumno_en_periodo(alumno, self.periodo, self.hoy)

    def test_con_matricula_activa_usa_esa(self):
        alumno = self._alumno(2)
        self._matricula(alumno, self.curso, fecha_matricula=self.hoy - 50 * UN_DIA)
        # Una terminada más reciente no le gana a la activa.
        self._matricula(
            alumno, self.otro_curso,
            fecha_matricula=self.hoy - 10 * UN_DIA, fecha_termino=self.hoy - 5 * UN_DIA,
        )
        self.assertEqual(self._curso_del_alumno(alumno), self.curso)

    def test_una_que_termina_manana_es_activa(self):
        alumno = self._alumno(2)
        self._matricula(alumno, self.curso, fecha_matricula=self.hoy - 50 * UN_DIA,
                        fecha_termino=self.hoy + UN_DIA)
        self._matricula(alumno, self.otro_curso, fecha_matricula=self.hoy - 10 * UN_DIA,
                        fecha_termino=self.hoy)
        self.assertEqual(self._curso_del_alumno(alumno), self.curso)

    def test_con_matriculas_terminadas_usa_la_mas_reciente(self):
        alumno = self._alumno(2)
        self._matricula(alumno, self.otro_curso, fecha_matricula=self.hoy - 50 * UN_DIA,
                        fecha_termino=self.hoy - 20 * UN_DIA)
        # Termina hoy: ya no es activa, pero es la más reciente.
        self._matricula(alumno, self.curso, fecha_matricula=self.hoy - 20 * UN_DIA,
                        fecha_termino=self.hoy)
        self.assertEqual(self._curso_del_alumno(alumno), self.curso)

    def test_con_la_misma_fecha_de_matricula_desempata_por_id(self):
        alumno = self._alumno(2)
        fecha = self.hoy - 20 * UN_DIA
        self._matricula(alumno, self.curso, fecha_matricula=fecha, fecha_termino=self.hoy - UN_DIA)
        self._matricula(alumno, self.otro_curso, fecha_matricula=fecha, fecha_termino=self.hoy - UN_DIA)
        self.assertEqual(self._curso_del_alumno(alumno), self.otro_curso)

    def test_con_cambio_de_curso_en_el_mismo_periodo_usa_la_activa(self):
        alumno = self._alumno(2)
        self._matricula(alumno, self.curso, fecha_matricula=self.hoy - 50 * UN_DIA,
                        fecha_termino=self.hoy - 3 * UN_DIA)
        self._matricula(alumno, self.otro_curso, fecha_matricula=self.hoy - 3 * UN_DIA)
        self.assertEqual(self._curso_del_alumno(alumno), self.otro_curso)

    def test_sin_matricula_en_el_periodo_devuelve_none(self):
        alumno = self._alumno(2)
        self._matricula(alumno, Curso.objects.create(periodo=self.otro_periodo, nivel=1, grupo="A"))
        self.assertIsNone(self._curso_del_alumno(alumno))

    def test_acepta_el_id_del_periodo(self):
        self.assertEqual(
            alcance_queries.curso_del_alumno_en_periodo(self.alumno, self.periodo.pk, self.hoy),
            self.curso,
        )


class FuncionarioActualTests(RevisionBase):
    def _funcionario_actual(self):
        from alertas.services.identidad import funcionario_actual

        return funcionario_actual(RequestFactory().get("/"))

    def test_el_setting_existe_y_viene_recortado(self):
        valor = settings.FUNCIONARIO_REVISOR_PRUEBA_EMAIL
        self.assertIsInstance(valor, str)
        self.assertEqual(valor, valor.strip())

    def test_busca_el_correo_sin_distinguir_mayusculas(self):
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL="FUNCIONARIO1@Liceo.CL"):
            self.assertEqual(self._funcionario_actual(), self.revisor)

    def test_setting_vacio_da_none(self):
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL=""):
            self.assertIsNone(self._funcionario_actual())

    def test_correo_inexistente_da_none(self):
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL="nadie@liceo.cl"):
            self.assertIsNone(self._funcionario_actual())


@override_settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL=CORREO_REVISOR)
class RevisarEndpointTests(RevisionBase):
    def _url(self, alerta_id=None):
        return reverse("alerta_revisar", args=[alerta_id or self.alerta.pk])

    def _post_json(self, cuerpo, alerta_id=None):
        # CONTENT_TYPE explícito: con cuerpo vacío el cliente de test omite la cabecera.
        return self.client.post(
            self._url(alerta_id), data=cuerpo, content_type="application/json",
            CONTENT_TYPE="application/json",
        )

    def _assert_error(self, respuesta, estado, codigo):
        self.assertEqual(respuesta.status_code, estado)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        self.assertEqual(respuesta.json(), {"ok": False, "error": codigo})

    def _esperado(self, nota):
        alerta = Alerta.objects.get(pk=self.alerta.pk)
        return {"ok": True, "alerta": {
            "id": alerta.pk,
            "revisada": True,
            "fecha_revision": timezone.localtime(alerta.fecha_revision).isoformat(),
            "funcionario_revisa": self.revisor.nombre,
            "nota": nota,
        }}

    def test_ruta(self):
        self.assertEqual(self._url(), f"/alertas/{self.alerta.pk}/revisar/")

    def test_200_con_cuerpo_json(self):
        respuesta = self._post_json(json.dumps({"nota": "  Se llamó al apoderado.  "}))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/json")
        self.assertEqual(respuesta.json(), self._esperado("Se llamó al apoderado."))
        self.assertIsNotNone(datetime.datetime.fromisoformat(respuesta.json()["alerta"]["fecha_revision"]))

    def test_200_con_formulario(self):
        respuesta = self.client.post(self._url(), {"nota": "Desde el formulario"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), self._esperado("Desde el formulario"))

    def test_200_sin_nota(self):
        for nombre, enviar in (
            ("formulario vacío", lambda: self.client.post(self._url())),
            ("json sin nota", lambda: self._post_json("{}")),
        ):
            with self.subTest(nombre):
                self._sin_revisar()
                respuesta = enviar()
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.json(), self._esperado(None))

    def test_401_sin_funcionario(self):
        for correo in ("", "nadie@liceo.cl"):
            with self.subTest(correo=correo), self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL=correo):
                self._assert_error(self.client.post(self._url()), 401, "sin_funcionario")
        self.assertFalse(self._foto()["revisada"])

    def test_404_alerta_inexistente(self):
        inexistente = Alerta.objects.order_by("-pk").first().pk + 1000
        self._assert_error(self.client.post(self._url(inexistente)), 404, "no_encontrada")

    def test_403_sin_permiso(self):
        self._funcionario(2, self.rol_sin_permiso)
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL="funcionario2@liceo.cl"):
            self._assert_error(self.client.post(self._url()), 403, "sin_permiso")

    def test_403_fuera_de_alcance(self):
        otro = self._funcionario(2, self.rol_seleccionados)
        FuncionarioCurso.objects.create(funcionario=otro, curso=self.otro_curso)
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL="funcionario2@liceo.cl"):
            self._assert_error(self.client.post(self._url()), 403, "fuera_de_alcance")
        self.assertFalse(self._foto()["revisada"])

    def test_409_alerta_cerrada(self):
        Alerta.objects.filter(pk=self.alerta.pk).update(fecha_cierre=self.ahora)
        self._assert_error(self.client.post(self._url()), 409, "alerta_cerrada")

    def test_409_ya_revisada(self):
        self.assertEqual(self.client.post(self._url()).status_code, 200)
        self._assert_error(self.client.post(self._url()), 409, "ya_revisada")

    def test_400_nota_invalida(self):
        for nombre, enviar in (
            ("formulario, 1001 caracteres", lambda: self.client.post(self._url(), {"nota": "x" * 1001})),
            ("json, 1001 caracteres", lambda: self._post_json(json.dumps({"nota": "x" * 1001}))),
            ("json, número", lambda: self._post_json(json.dumps({"nota": 5}))),
        ):
            with self.subTest(nombre):
                self._assert_error(enviar(), 400, "nota_invalida")
        self.assertFalse(self._foto()["revisada"])

    def test_400_solicitud_invalida(self):
        for cuerpo in ('{"nota": ', "no es json", "", "[1, 2]", '"texto"'):
            with self.subTest(cuerpo=cuerpo):
                self._assert_error(self._post_json(cuerpo), 400, "solicitud_invalida")
        self.assertFalse(self._foto()["revisada"])

    def test_405_con_otros_metodos(self):
        for metodo in ("get", "put", "patch", "delete"):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(self._url())
                self._assert_error(respuesta, 405, "metodo_no_permitido")
                self.assertEqual(respuesta["Allow"], "POST")

    def test_orden_de_las_verificaciones(self):
        # Método antes que funcionario.
        with self.settings(FUNCIONARIO_REVISOR_PRUEBA_EMAIL=""):
            self._assert_error(self.client.get(self._url()), 405, "metodo_no_permitido")
            # Funcionario antes que existencia.
            self._assert_error(self.client.post(self._url(999999)), 401, "sin_funcionario")
        # Existencia antes que el cuerpo.
        self._assert_error(self._post_json("{mal", alerta_id=999999), 404, "no_encontrada")

    def test_el_middleware_csrf_esta_activo(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(cliente.post(self._url()).status_code, 403)
        self.assertFalse(self._foto()["revisada"])

    def test_la_pagina_de_alertas_sigue_respondiendo(self):
        self.assertEqual(self.client.get("/alertas/").status_code, 200)


class IndependenciaTests(TestCase):
    """Lo nuevo no importa de monitoreo ni de asistencia, ni nombra roles o estados."""

    def _codigos(self):
        servicios = Path(alertas_service.__file__).resolve().parent
        return {
            "identidad": (servicios / "identidad.py").read_text(encoding="utf-8"),
            "views": Path(alertas_views.__file__).read_text(encoding="utf-8"),
        }

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
                    self.assertNotIn(nombre, codigo.lower())
