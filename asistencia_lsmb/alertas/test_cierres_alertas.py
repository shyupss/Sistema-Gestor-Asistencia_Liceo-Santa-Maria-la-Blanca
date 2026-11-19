"""Cierres por barrido (fin de período / fin de matrícula), reconciliación y el comando sincronizar_alertas.

Las fechas son relativas a hoy, así que los tests no dependen del día en que se
corren. El año de cada período es solo una etiqueta (anio es único).
"""
import datetime
import re
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Alerta, Estado, EstadoAlumno
from alertas.services import alertas_service

UN_DIA = datetime.timedelta(days=1)

COMANDO = Path(alertas_service.__file__).resolve().parent.parent / (
    "management/commands/sincronizar_alertas.py"
)


class CierresBase(TestCase):
    def setUp(self):
        self.ahora = timezone.now()
        self.hoy = timezone.localdate(self.ahora)
        self.periodo = self._periodo(self.hoy.year, fin=self.hoy + 60 * UN_DIA)
        # Los nombres no importan: solo se mira es_no_ideal.
        self.bien = Estado.objects.create(nombre="Bien", umbral_minimo=90, es_no_ideal=False)
        self.bajo = Estado.objects.create(nombre="Bajo", umbral_minimo=60, es_no_ideal=True)
        self.muy_bajo = Estado.objects.create(nombre="Muy bajo", umbral_minimo=0, es_no_ideal=True)

    def _periodo(self, anio, fin):
        return PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=self.hoy - 100 * UN_DIA, fecha_fin=fin,
        )

    def _curso(self, periodo, grupo="A"):
        return Curso.objects.get_or_create(periodo=periodo, nivel=1, grupo=grupo)[0]

    def _alumno(self, numero):
        return Alumno.objects.create(nombre=f"Alumno {numero}", rut=f"{numero}111111-{numero}")

    def _matricula(self, alumno, periodo, fecha_termino=None, curso=None, fecha_matricula=None):
        return Matricula.objects.create(
            alumno=alumno, periodo=periodo, curso=curso or self._curso(periodo),
            estado_matricula=EstadoMatricula.objects.get_or_create(nombre="vigente")[0],
            fecha_matricula=fecha_matricula or self.hoy - 30 * UN_DIA,
            fecha_termino=fecha_termino,
        )

    def _alerta(self, alumno, periodo=None, estado=None, revisada=False):
        return Alerta.objects.create(
            alumno=alumno, periodo=periodo or self.periodo, estado=estado or self.bajo,
            revisada=revisada,
        )

    def _estado_alumno(self, alumno, estado, periodo=None):
        return EstadoAlumno.objects.create(
            alumno=alumno, periodo=periodo or self.periodo, estado=estado,
        )

    def _barrido(self, **kwargs):
        return alertas_service.barrido_cierres(ahora=self.ahora, **kwargs)

    def _reconciliar(self, **kwargs):
        return alertas_service.reconciliar_alertas(ahora=self.ahora, **kwargs)

    def _assert_cerrada(self, alerta, motivo):
        alerta.refresh_from_db()
        self.assertEqual(alerta.fecha_cierre, self.ahora)
        self.assertEqual(alerta.motivo_cierre, motivo)

    def _assert_vigente(self, alerta):
        alerta.refresh_from_db()
        self.assertIsNone(alerta.fecha_cierre)
        self.assertIsNone(alerta.motivo_cierre)


def _conteo_cierres(fin_periodo=0, fin_matricula=0):
    return {"fin_periodo": fin_periodo, "fin_matricula": fin_matricula}


def _conteo_reconciliacion(creada=0, cambio_estado=0, recuperada=0, sin_cambio=0):
    return {
        "creada": creada, "cambio_estado": cambio_estado,
        "recuperada": recuperada, "sin_cambio": sin_cambio,
    }


class BarridoCierresTests(CierresBase):
    def test_cierra_con_fin_matricula_si_la_matricula_termino(self):
        alumno = self._alumno(1)
        self._matricula(alumno, self.periodo, fecha_termino=self.hoy - 5 * UN_DIA)
        alerta = self._alerta(alumno)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_matricula=1))
        self._assert_cerrada(alerta, "fin_matricula")

    def test_una_matricula_que_termina_hoy_ya_no_es_activa_y_una_que_termina_manana_si(self):
        termina_hoy, termina_manana = self._alumno(1), self._alumno(2)
        self._matricula(termina_hoy, self.periodo, fecha_termino=self.hoy)
        self._matricula(termina_manana, self.periodo, fecha_termino=self.hoy + UN_DIA)
        alerta_hoy, alerta_manana = self._alerta(termina_hoy), self._alerta(termina_manana)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_matricula=1))
        self._assert_cerrada(alerta_hoy, "fin_matricula")
        self._assert_vigente(alerta_manana)

    def test_cierra_con_fin_periodo_si_el_periodo_termino_ayer(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        alumno = self._alumno(1)
        self._matricula(alumno, terminado)  # activa: solo aplica fin_periodo
        alerta = self._alerta(alumno, terminado)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_periodo=1))
        self._assert_cerrada(alerta, "fin_periodo")

    def test_un_periodo_que_termina_hoy_no_se_cierra(self):
        termina_hoy = self._periodo(self.hoy.year - 1, fin=self.hoy)
        alumno = self._alumno(1)
        self._matricula(alumno, termina_hoy)
        alerta = self._alerta(alumno, termina_hoy)
        self.assertEqual(self._barrido(), _conteo_cierres())
        self._assert_vigente(alerta)

    def test_un_cambio_de_curso_en_el_mismo_periodo_no_cierra_la_alerta(self):
        alumno = self._alumno(1)
        self._matricula(
            alumno, self.periodo, curso=self._curso(self.periodo, "A"), fecha_termino=self.hoy,
        )
        self._matricula(
            alumno, self.periodo, curso=self._curso(self.periodo, "B"), fecha_matricula=self.hoy,
        )
        alerta = self._alerta(alumno)
        self.assertEqual(self._barrido(), _conteo_cierres())
        self._assert_vigente(alerta)

    def test_una_matricula_activa_en_otro_periodo_no_basta(self):
        otro = self._periodo(self.hoy.year + 1, fin=self.hoy + 300 * UN_DIA)
        uno, dos = self._alumno(1), self._alumno(2)
        # Dos matrículas con fecha_termino nula, en períodos distintos.
        self._matricula(uno, self.periodo)
        self._matricula(dos, otro)
        uno_aqui = self._alerta(uno, self.periodo)
        uno_en_otro = self._alerta(uno, otro)  # uno no está matriculado en `otro`
        dos_en_otro = self._alerta(dos, otro)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_matricula=1))
        self._assert_cerrada(uno_en_otro, "fin_matricula")
        self._assert_vigente(uno_aqui)
        self._assert_vigente(dos_en_otro)

    def test_si_aplican_ambos_motivos_gana_fin_periodo(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        alumno = self._alumno(1)
        self._matricula(alumno, terminado, fecha_termino=self.hoy - 10 * UN_DIA)
        alerta = self._alerta(alumno, terminado)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_periodo=1))
        self._assert_cerrada(alerta, "fin_periodo")

    def test_cierra_revisadas_y_no_revisadas_e_ignora_las_ya_cerradas(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        uno, dos = self._alumno(1), self._alumno(2)  # sin matrícula en ningún período
        revisada = self._alerta(uno, revisada=True)
        no_revisada = self._alerta(dos)
        antes = self.ahora - 10 * UN_DIA
        cerradas = [
            Alerta.objects.create(
                alumno=uno, periodo=self.periodo, estado=self.muy_bajo,
                fecha_cierre=antes, motivo_cierre="cambio_estado",
            ),
            Alerta.objects.create(
                alumno=uno, periodo=terminado, estado=self.bajo,
                fecha_cierre=antes, motivo_cierre="recuperado",
            ),
        ]
        self.assertEqual(self._barrido(), _conteo_cierres(fin_matricula=2))
        self._assert_cerrada(revisada, "fin_matricula")
        self._assert_cerrada(no_revisada, "fin_matricula")
        self.assertTrue(revisada.revisada)
        for cerrada, motivo in zip(cerradas, ("cambio_estado", "recuperado")):
            cerrada.refresh_from_db()
            self.assertEqual(cerrada.fecha_cierre, antes)
            self.assertEqual(cerrada.motivo_cierre, motivo)

    def test_la_segunda_corrida_devuelve_ceros(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        uno, dos = self._alumno(1), self._alumno(2)
        self._matricula(uno, terminado)
        self._alerta(uno, terminado)
        self._alerta(dos)
        self.assertEqual(self._barrido(), _conteo_cierres(fin_periodo=1, fin_matricula=1))
        self.assertEqual(self._barrido(), _conteo_cierres())
        self.assertEqual(
            alertas_service.barrido_cierres(ahora=self.ahora + UN_DIA), _conteo_cierres(),
        )
        self.assertFalse(Alerta.objects.filter(fecha_cierre__isnull=True).exists())

    def test_el_parametro_periodo_limita_el_barrido(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        uno, dos = self._alumno(1), self._alumno(2)
        self._matricula(uno, terminado)
        en_terminado = self._alerta(uno, terminado)
        sin_matricula = self._alerta(dos)
        self.assertEqual(self._barrido(periodo=self.periodo), _conteo_cierres(fin_matricula=1))
        self._assert_cerrada(sin_matricula, "fin_matricula")
        self._assert_vigente(en_terminado)
        # También acepta el id del período.
        self.assertEqual(self._barrido(periodo=terminado.pk), _conteo_cierres(fin_periodo=1))
        self._assert_cerrada(en_terminado, "fin_periodo")

    def test_sin_ahora_usa_la_hora_actual(self):
        alerta = self._alerta(self._alumno(1))
        antes = timezone.now()
        self.assertEqual(alertas_service.barrido_cierres(), _conteo_cierres(fin_matricula=1))
        alerta.refresh_from_db()
        self.assertGreaterEqual(alerta.fecha_cierre, antes)
        self.assertLessEqual(alerta.fecha_cierre, timezone.now())


class ReconciliarAlertasTests(CierresBase):
    def test_crea_la_alerta_que_falta(self):
        alumno = self._alumno(1)
        self._matricula(alumno, self.periodo)
        self._estado_alumno(alumno, self.bajo)
        self.assertEqual(self._reconciliar(), _conteo_reconciliacion(creada=1))
        alerta = Alerta.objects.get(alumno=alumno, periodo=self.periodo, fecha_cierre__isnull=True)
        self.assertEqual(alerta.estado, self.bajo)
        self.assertFalse(alerta.revisada)

    def test_cierra_con_recuperado_si_el_estado_ya_es_ideal(self):
        alumno = self._alumno(1)
        self._matricula(alumno, self.periodo)
        self._estado_alumno(alumno, self.bien)
        alerta = self._alerta(alumno, revisada=True)
        self.assertEqual(self._reconciliar(), _conteo_reconciliacion(recuperada=1))
        self._assert_cerrada(alerta, "recuperado")

    def test_no_crea_alertas_en_periodos_terminados_ni_sin_matricula_activa(self):
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        en_terminado, sin_matricula = self._alumno(1), self._alumno(2)
        self._matricula(en_terminado, terminado)
        self._estado_alumno(en_terminado, self.bajo, terminado)
        self._matricula(sin_matricula, self.periodo, fecha_termino=self.hoy)
        self._estado_alumno(sin_matricula, self.bajo)
        # El período terminado ni siquiera se recorre: solo cuenta el otro alumno.
        self.assertEqual(self._reconciliar(), _conteo_reconciliacion(sin_cambio=1))
        self.assertFalse(Alerta.objects.exists())

    def test_la_segunda_corrida_es_todo_sin_cambio(self):
        crea, cambia, recupera, igual = (self._alumno(n) for n in (1, 2, 3, 4))
        for alumno in (crea, cambia, recupera, igual):
            self._matricula(alumno, self.periodo)
        self._estado_alumno(crea, self.bajo)
        self._estado_alumno(cambia, self.muy_bajo)
        self._alerta(cambia, estado=self.bajo)
        self._estado_alumno(recupera, self.bien)
        self._alerta(recupera, estado=self.bajo)
        self._estado_alumno(igual, self.bajo)
        self._alerta(igual, estado=self.bajo)

        self.assertEqual(
            self._reconciliar(),
            _conteo_reconciliacion(creada=1, cambio_estado=1, recuperada=1, sin_cambio=1),
        )
        self.assertEqual(self._reconciliar(), _conteo_reconciliacion(sin_cambio=4))
        self.assertEqual(Alerta.objects.count(), 5)
        self.assertEqual(
            {
                (alerta.alumno_id, alerta.estado_id)
                for alerta in Alerta.objects.filter(fecha_cierre__isnull=True)
            },
            {(crea.pk, self.bajo.pk), (cambia.pk, self.muy_bajo.pk), (igual.pk, self.bajo.pk)},
        )

    def test_el_parametro_periodo_limita_la_reconciliacion(self):
        otro = self._periodo(self.hoy.year + 1, fin=self.hoy + 300 * UN_DIA)
        terminado = self._periodo(self.hoy.year - 1, fin=self.hoy - UN_DIA)
        uno, dos, tres = self._alumno(1), self._alumno(2), self._alumno(3)
        for alumno, periodo in ((uno, self.periodo), (dos, otro), (tres, terminado)):
            self._matricula(alumno, periodo)
            self._estado_alumno(alumno, self.bajo, periodo)

        self.assertEqual(
            self._reconciliar(periodo=self.periodo), _conteo_reconciliacion(creada=1),
        )
        self.assertEqual(list(Alerta.objects.values_list("alumno_id", flat=True)), [uno.pk])
        # Un período terminado no se reconcilia, aunque se pida explícitamente.
        self.assertEqual(self._reconciliar(periodo=terminado), _conteo_reconciliacion())
        # También acepta el id del período.
        self.assertEqual(self._reconciliar(periodo=otro.pk), _conteo_reconciliacion(creada=1))
        self.assertEqual(
            set(Alerta.objects.values_list("alumno_id", flat=True)), {uno.pk, dos.pk},
        )

    def test_recorre_en_orden_de_id_y_pasa_ahora(self):
        alumnos = [self._alumno(n) for n in (1, 2, 3)]
        estados = []
        for alumno in alumnos:
            self._matricula(alumno, self.periodo)
            estados.append(self._estado_alumno(alumno, self.bajo))
        # Actualizar el primero lo deja físicamente al final de la tabla.
        estados[0].estado = self.muy_bajo
        estados[0].save()

        with mock.patch.object(
            alertas_service, "sincronizar_alerta", wraps=alertas_service.sincronizar_alerta,
        ) as sincronizar:
            self._reconciliar()

        self.assertEqual(
            [(c.args, c.kwargs) for c in sincronizar.call_args_list],
            [((alumno, self.periodo), {"ahora": self.ahora}) for alumno in alumnos],
        )

    def test_no_traga_excepciones(self):
        alumno = self._alumno(1)
        self._matricula(alumno, self.periodo)
        self._estado_alumno(alumno, self.bajo)
        with mock.patch.object(
            alertas_service, "sincronizar_alerta", side_effect=RuntimeError("falla simulada"),
        ), self.assertRaises(RuntimeError):
            self._reconciliar()


class ComandoSincronizarAlertasTests(CierresBase):
    """Escenario: una alerta por cerrar (fin de matrícula), una por crear y una por recuperar."""

    def setUp(self):
        super().setUp()
        self.termino, self.nuevo, self.recupera = self._alumno(1), self._alumno(2), self._alumno(3)
        self._matricula(self.termino, self.periodo, fecha_termino=self.hoy - 5 * UN_DIA)
        self._estado_alumno(self.termino, self.bajo)
        self.alerta_termino = self._alerta(self.termino)
        self._matricula(self.nuevo, self.periodo)
        self._estado_alumno(self.nuevo, self.bajo)
        self._matricula(self.recupera, self.periodo)
        self._estado_alumno(self.recupera, self.bien)
        self.alerta_recupera = self._alerta(self.recupera)

    def _comando(self, *args):
        salida = StringIO()
        call_command("sincronizar_alertas", *args, stdout=salida)
        return salida.getvalue().splitlines()

    def _foto(self):
        return list(Alerta.objects.order_by("pk").values())

    def _assert_cerrada_por_el_comando(self, alerta, motivo):
        # El comando usa su propio timezone.now(), posterior a self.ahora.
        alerta.refresh_from_db()
        self.assertGreaterEqual(alerta.fecha_cierre, self.ahora)
        self.assertEqual(alerta.motivo_cierre, motivo)

    def test_imprime_los_conteos_y_aplica_los_cambios(self):
        self.assertEqual(self._comando(), [
            "Alcance: todos los períodos",
            "Cierres: fin de período 0, fin de matrícula 1.",
            "Reconciliación: creadas 1, cambio de estado 0, recuperadas 1, sin cambio 1.",
        ])
        self._assert_cerrada_por_el_comando(self.alerta_termino, "fin_matricula")
        self._assert_cerrada_por_el_comando(self.alerta_recupera, "recuperado")
        self.assertEqual(
            Alerta.objects.get(alumno=self.nuevo, fecha_cierre__isnull=True).estado, self.bajo,
        )

    def test_dry_run_no_persiste_nada_pero_informa_lo_que_habria_hecho(self):
        antes = self._foto()
        self.assertEqual(self._comando("--dry-run"), [
            "[dry-run] Alcance: todos los períodos",
            "[dry-run] Cierres: fin de período 0, fin de matrícula 1.",
            "[dry-run] Reconciliación: creadas 1, cambio de estado 0, recuperadas 1, sin cambio 1.",
            "[dry-run] Se revirtieron todos los cambios.",
        ])
        self.assertEqual(self._foto(), antes)

    def test_solo_cierres_no_crea_ni_recupera(self):
        self.assertEqual(self._comando("--solo-cierres"), [
            "Alcance: todos los períodos",
            "Cierres: fin de período 0, fin de matrícula 1.",
            "Reconciliación: omitida (--solo-cierres).",
        ])
        self._assert_cerrada_por_el_comando(self.alerta_termino, "fin_matricula")
        self.assertFalse(Alerta.objects.filter(alumno=self.nuevo).exists())
        self.alerta_recupera.refresh_from_db()
        self.assertIsNone(self.alerta_recupera.fecha_cierre)

    def test_periodo_limita_las_dos_funciones(self):
        otro = self._periodo(self.hoy.year + 1, fin=self.hoy + 300 * UN_DIA)
        por_crear, sin_matricula = self._alumno(4), self._alumno(5)
        self._matricula(por_crear, otro)
        self._estado_alumno(por_crear, self.bajo, otro)
        alerta_sin_matricula = self._alerta(sin_matricula, otro)

        self.assertEqual(self._comando("--periodo", str(self.periodo.anio)), [
            f"Alcance: período {self.periodo.anio}",
            "Cierres: fin de período 0, fin de matrícula 1.",
            "Reconciliación: creadas 1, cambio de estado 0, recuperadas 1, sin cambio 1.",
        ])
        self.assertFalse(Alerta.objects.filter(alumno=por_crear).exists())
        self._assert_vigente(alerta_sin_matricula)

    def test_periodo_inexistente_da_command_error(self):
        antes = self._foto()
        with self.assertRaisesMessage(CommandError, "1990"):
            self._comando("--periodo", "1990")
        self.assertEqual(self._foto(), antes)


class IndependenciaTests(TestCase):
    """El servicio y el comando no importan de monitoreo ni de asistencia, ni nombran roles o estados."""

    def _codigos(self):
        return {
            "alertas_service": Path(alertas_service.__file__).read_text(encoding="utf-8"),
            "comando": COMANDO.read_text(encoding="utf-8"),
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
