"""Motor de alertas: sincronizar_alerta, cerrar_alerta y el enganche en recalcular_estado_alumno.

Las fechas son relativas a hoy: el período abarca hoy, así que los tests no
dependen de la fecha en que se corren.
"""
import datetime
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Alerta, Cargo, Estado, EstadoAlumno, Funcionario
from alertas.services import alertas_service
from alertas.services.alertas_service import cerrar_alerta, sincronizar_alerta
from asistencia.constantes import TIPO_AUSENTE, TIPO_PRESENTE
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia
from asistencia.services.asistencia_service import recalcular_estado_alumno

UN_DIA = datetime.timedelta(days=1)


class MotorAlertasBase(TestCase):
    def setUp(self):
        self.ahora = timezone.now()
        self.hoy = timezone.localdate(self.ahora)
        self.periodo = self._periodo(self.hoy.year)
        self.otro_periodo = self._periodo(self.hoy.year - 1)
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.otro_curso = Curso.objects.create(periodo=self.otro_periodo, nivel=1, grupo="A")
        self.alumno = Alumno.objects.create(nombre="Alumno Uno", rut="11111111-1")
        self.matricula = self._matricula(self.periodo, self.curso)
        # Los nombres no importan: el motor solo mira es_no_ideal.
        self.bien = Estado.objects.create(nombre="Bien", umbral_minimo=90, es_no_ideal=False)
        self.bajo = Estado.objects.create(nombre="Bajo", umbral_minimo=60, es_no_ideal=True)
        self.muy_bajo = Estado.objects.create(nombre="Muy bajo", umbral_minimo=0, es_no_ideal=True)

    def _periodo(self, anio):
        # Abarca hoy, sin importar el año en que corran los tests.
        return PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=self.hoy - 60 * UN_DIA, fecha_fin=self.hoy + 60 * UN_DIA,
        )

    def _matricula(self, periodo, curso, fecha_termino=None):
        return Matricula.objects.create(
            alumno=self.alumno, curso=curso, periodo=periodo,
            estado_matricula=EstadoMatricula.objects.get_or_create(nombre="vigente")[0],
            fecha_matricula=self.hoy - 30 * UN_DIA, fecha_termino=fecha_termino,
        )

    def _sincronizar(self, estado, periodo=None, ahora=None):
        return sincronizar_alerta(
            self.alumno, periodo or self.periodo, estado, ahora=ahora or self.ahora,
        )

    def _vigentes(self, periodo=None):
        return Alerta.objects.filter(
            alumno=self.alumno, periodo=periodo or self.periodo, fecha_cierre__isnull=True,
        )

    def _vigente(self, periodo=None):
        return self._vigentes(periodo).get()


class SincronizarAlertaTests(MotorAlertasBase):
    def test_entrar_a_no_ideal_crea_una_alerta(self):
        self.assertEqual(self._sincronizar(self.bajo), "creada")
        alerta = self._vigente()
        self.assertEqual(alerta.estado, self.bajo)
        self.assertEqual(alerta.periodo, self.periodo)
        self.assertFalse(alerta.revisada)
        self.assertIsNone(alerta.motivo_cierre)
        self.assertIsNotNone(alerta.fecha_creacion)

    def test_estado_ideal_sin_vigente_no_hace_nada(self):
        self.assertEqual(self._sincronizar(self.bien), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    def test_mismo_estado_dos_veces_deja_una_sola_alerta(self):
        self._sincronizar(self.bajo)
        self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertEqual(self._vigente().estado, self.bajo)

    def test_de_un_no_ideal_a_otro_cierra_y_crea_otra(self):
        self._sincronizar(self.bajo)
        anterior = self._vigente()
        despues = self.ahora + datetime.timedelta(hours=1)
        self.assertEqual(self._sincronizar(self.muy_bajo, ahora=despues), "cambio_estado")
        anterior.refresh_from_db()
        self.assertEqual(anterior.fecha_cierre, despues)
        self.assertEqual(anterior.motivo_cierre, "cambio_estado")
        nueva = self._vigente()
        self.assertNotEqual(nueva.pk, anterior.pk)
        self.assertEqual(nueva.estado, self.muy_bajo)
        self.assertFalse(nueva.revisada)
        self.assertEqual(Alerta.objects.count(), 2)

    def test_recuperarse_cierra_con_recuperado(self):
        self._sincronizar(self.bajo)
        alerta = self._vigente()
        despues = self.ahora + datetime.timedelta(hours=1)
        self.assertEqual(self._sincronizar(self.bien, ahora=despues), "recuperada")
        alerta.refresh_from_db()
        self.assertEqual(alerta.fecha_cierre, despues)
        self.assertEqual(alerta.motivo_cierre, "recuperado")
        self.assertFalse(self._vigentes().exists())

    def test_una_alerta_revisada_sigue_vigente_si_el_estado_no_cambia(self):
        self._sincronizar(self.bajo)
        Alerta.objects.update(revisada=True)
        self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
        alerta = self._vigente()
        self.assertTrue(alerta.revisada)
        self.assertIsNone(alerta.fecha_cierre)

    def test_una_alerta_revisada_tambien_se_cierra_al_recuperarse(self):
        self._sincronizar(self.bajo)
        Alerta.objects.update(revisada=True)
        self.assertEqual(self._sincronizar(self.bien), "recuperada")
        self.assertEqual(Alerta.objects.get().motivo_cierre, "recuperado")

    def test_revisada_y_luego_cambio_de_estado_la_nueva_nace_sin_revisar(self):
        self._sincronizar(self.bajo)
        anterior = self._vigente()
        Alerta.objects.update(revisada=True)
        self.assertEqual(self._sincronizar(self.muy_bajo), "cambio_estado")
        anterior.refresh_from_db()
        self.assertTrue(anterior.revisada)
        self.assertEqual(anterior.motivo_cierre, "cambio_estado")
        self.assertFalse(self._vigente().revisada)

    def test_la_alerta_guarda_el_periodo_pasado(self):
        self._matricula(self.otro_periodo, self.otro_curso)
        self._sincronizar(self.bajo, periodo=self.periodo)
        self.assertEqual(Alerta.objects.get().periodo, self.periodo)
        self.assertFalse(self._vigentes(self.otro_periodo).exists())
        # Cada período tiene su propia alerta vigente.
        self.assertEqual(self._sincronizar(self.muy_bajo, periodo=self.otro_periodo), "creada")
        self.assertEqual(self._vigente(self.otro_periodo).estado, self.muy_bajo)
        self.assertEqual(self._vigente(self.periodo).estado, self.bajo)

    # --- S1: condiciones para crear --------------------------------------------

    def test_periodo_que_termina_hoy_aun_crea(self):
        PeriodoAcademico.objects.filter(pk=self.periodo.pk).update(fecha_fin=self.hoy)
        self.periodo.refresh_from_db()
        self.assertEqual(self._sincronizar(self.bajo), "creada")

    def test_periodo_terminado_no_crea(self):
        PeriodoAcademico.objects.filter(pk=self.periodo.pk).update(fecha_fin=self.hoy - UN_DIA)
        self.periodo.refresh_from_db()
        self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    def test_sin_matricula_en_el_periodo_no_crea(self):
        self.matricula.delete()
        self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    def test_matricula_terminada_no_crea(self):
        for fecha_termino in (self.hoy, self.hoy - UN_DIA):
            with self.subTest(fecha_termino=fecha_termino):
                Matricula.objects.filter(pk=self.matricula.pk).update(fecha_termino=fecha_termino)
                self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
                self.assertFalse(Alerta.objects.exists())

    def test_matricula_que_termina_despues_de_hoy_cuenta_como_activa(self):
        Matricula.objects.filter(pk=self.matricula.pk).update(fecha_termino=self.hoy + UN_DIA)
        self.assertEqual(self._sincronizar(self.bajo), "creada")

    def test_una_matricula_activa_de_otro_periodo_no_basta(self):
        self.matricula.delete()
        self._matricula(self.otro_periodo, self.otro_curso)
        self.assertEqual(self._sincronizar(self.bajo), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    def test_cambio_de_estado_con_s1_incumplido_deja_la_vigente_sin_tocar(self):
        self._sincronizar(self.bajo)
        alerta = self._vigente()
        Matricula.objects.filter(pk=self.matricula.pk).update(fecha_termino=self.hoy)
        self.assertEqual(self._sincronizar(self.muy_bajo), "sin_cambio")
        vigente = self._vigente()
        self.assertEqual(vigente.pk, alerta.pk)
        self.assertEqual(vigente.estado, self.bajo)
        self.assertIsNone(vigente.motivo_cierre)
        self.assertEqual(Alerta.objects.count(), 1)

    def test_recuperarse_no_exige_s1(self):
        self._sincronizar(self.bajo)
        Matricula.objects.filter(pk=self.matricula.pk).update(fecha_termino=self.hoy)
        self.assertEqual(self._sincronizar(self.bien), "recuperada")
        self.assertEqual(Alerta.objects.get().motivo_cierre, "recuperado")

    # --- estado=None -------------------------------------------------------------

    def test_sin_estado_lee_estado_alumno(self):
        EstadoAlumno.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)
        self.assertEqual(sincronizar_alerta(self.alumno, self.periodo, ahora=self.ahora), "creada")
        self.assertEqual(self._vigente().estado, self.bajo)

    def test_sin_estado_ni_estado_alumno_no_hace_nada(self):
        self.assertEqual(sincronizar_alerta(self.alumno, self.periodo), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    def test_sin_estado_lee_el_estado_alumno_del_periodo_pasado(self):
        EstadoAlumno.objects.create(alumno=self.alumno, periodo=self.otro_periodo, estado=self.bajo)
        self.assertEqual(sincronizar_alerta(self.alumno, self.periodo), "sin_cambio")
        self.assertFalse(Alerta.objects.exists())

    # --- Carrera -----------------------------------------------------------------

    def _lectura_desactualizada(self, veces):
        """Las primeras `veces` lecturas de la vigente no la ven (otra transacción la creó)."""
        real = alertas_service._vigente_bloqueada
        llamadas = []

        def lectura(alumno, periodo):
            llamadas.append(1)
            return None if len(llamadas) <= veces else real(alumno, periodo)

        return mock.patch.object(alertas_service, "_vigente_bloqueada", side_effect=lectura), llamadas

    def test_carrera_relee_y_no_duplica(self):
        competidora = Alerta.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)
        parche, llamadas = self._lectura_desactualizada(veces=1)
        with parche:
            resultado = self._sincronizar(self.bajo)
        # El create chocó con el índice único, se releyó la vigente y se reevaluó.
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(resultado, "sin_cambio")
        self.assertEqual(Alerta.objects.count(), 1)
        self.assertEqual(self._vigente().pk, competidora.pk)

    def test_carrera_reevalua_con_la_vigente_releida(self):
        competidora = Alerta.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)
        parche, _ = self._lectura_desactualizada(veces=1)
        with parche:
            resultado = self._sincronizar(self.muy_bajo)
        self.assertEqual(resultado, "cambio_estado")
        competidora.refresh_from_db()
        self.assertEqual(competidora.motivo_cierre, "cambio_estado")
        self.assertEqual(self._vigente().estado, self.muy_bajo)
        self.assertEqual(Alerta.objects.count(), 2)

    def test_carrera_reevalua_una_sola_vez(self):
        Alerta.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)
        parche, llamadas = self._lectura_desactualizada(veces=2)
        with parche, self.assertRaises(IntegrityError):
            self._sincronizar(self.bajo)
        self.assertEqual(len(llamadas), 2)
        self.assertEqual(Alerta.objects.count(), 1)


class CerrarAlertaTests(MotorAlertasBase):
    def setUp(self):
        super().setUp()
        self.alerta = Alerta.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)

    def test_cierra_con_fecha_y_motivo(self):
        for motivo, _ in Alerta.MOTIVOS_CIERRE:
            with self.subTest(motivo=motivo):
                Alerta.objects.all().delete()
                alerta = Alerta.objects.create(alumno=self.alumno, periodo=self.periodo, estado=self.bajo)
                cerrar_alerta(alerta, motivo, ahora=self.ahora)
                alerta.refresh_from_db()
                self.assertEqual(alerta.fecha_cierre, self.ahora)
                self.assertEqual(alerta.motivo_cierre, motivo)

    def test_sin_ahora_usa_la_hora_actual(self):
        antes = timezone.now()
        cerrar_alerta(self.alerta, "recuperado")
        self.alerta.refresh_from_db()
        self.assertGreaterEqual(self.alerta.fecha_cierre, antes)

    def test_rechaza_un_motivo_invalido(self):
        with self.assertRaises(ValueError):
            cerrar_alerta(self.alerta, "porque_si", ahora=self.ahora)
        self.alerta.refresh_from_db()
        self.assertIsNone(self.alerta.fecha_cierre)
        self.assertIsNone(self.alerta.motivo_cierre)

    def test_rechaza_una_alerta_ya_cerrada(self):
        cerrar_alerta(self.alerta, "recuperado", ahora=self.ahora)
        with self.assertRaises(ValueError):
            cerrar_alerta(self.alerta, "cambio_estado", ahora=self.ahora + UN_DIA)
        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.motivo_cierre, "recuperado")
        self.assertEqual(self.alerta.fecha_cierre, self.ahora)

    def test_rechaza_una_alerta_cerrada_en_la_bd_aunque_la_instancia_no_lo_sepa(self):
        Alerta.objects.filter(pk=self.alerta.pk).update(
            fecha_cierre=self.ahora, motivo_cierre="recuperado",
        )
        with self.assertRaises(ValueError):
            cerrar_alerta(self.alerta, "cambio_estado", ahora=self.ahora + UN_DIA)
        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.motivo_cierre, "recuperado")


class EngancheRecalcularTests(MotorAlertasBase):
    """recalcular_estado_alumno sincroniza la alerta (hora real: el período abarca hoy)."""

    def setUp(self):
        super().setUp()
        cargo = Cargo.objects.create(nombre="Cargo de los tests del motor")
        self.funcionario = Funcionario.objects.create(
            cargo=cargo, rut="22222222-2", nombre="Funcionario", email="motor@liceo.cl",
        )
        self.presente = Tipos_Asistencia.objects.get_or_create(
            nombre=TIPO_PRESENTE, defaults={"cuenta_como_ausencia": False},
        )[0]
        self.ausente = Tipos_Asistencia.objects.get_or_create(
            nombre=TIPO_AUSENTE, defaults={"cuenta_como_ausencia": True},
        )[0]
        self._dia = 0

    def _registros(self, presentes, ausentes):
        for tipo, cantidad in ((self.presente, presentes), (self.ausente, ausentes)):
            for _ in range(cantidad):
                self._dia += 1
                paso = Paso_Lista.objects.create(
                    curso=self.curso, funcionario=self.funcionario,
                    fecha=self.periodo.fecha_inicio + self._dia * UN_DIA,
                )
                Asistencia_Alumnos.objects.create(
                    alumno=self.alumno, paso_lista=paso, tipo_asistencia=tipo,
                )

    def test_por_defecto_crea_la_alerta_de_punta_a_punta(self):
        self._registros(presentes=7, ausentes=3)  # 70 % -> Bajo (no ideal)
        estado_alumno = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(estado_alumno.estado, self.bajo)
        alerta = self._vigente()
        self.assertEqual(alerta.estado, self.bajo)
        self.assertEqual(alerta.periodo, self.periodo)
        self.assertFalse(alerta.revisada)

    def test_por_defecto_sigue_el_cambio_y_la_recuperacion(self):
        self._registros(presentes=7, ausentes=3)  # 70 % -> Bajo
        recalcular_estado_alumno(self.alumno, self.periodo)
        self._registros(presentes=0, ausentes=10)  # 35 % -> Muy bajo
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._vigente().estado, self.muy_bajo)
        self._registros(presentes=180, ausentes=0)  # 93 % -> Bien
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertFalse(self._vigentes().exists())
        self.assertEqual(
            list(Alerta.objects.order_by("pk").values_list("motivo_cierre", flat=True)),
            ["cambio_estado", "recuperado"],
        )

    def test_un_estado_que_deja_de_ser_no_ideal_cierra_con_recuperado(self):
        self._registros(presentes=7, ausentes=3)  # 70 % -> Bajo
        recalcular_estado_alumno(self.alumno, self.periodo)
        alerta = self._vigente()
        Estado.objects.filter(pk=self.bajo.pk).update(es_no_ideal=False)
        recalcular_estado_alumno(self.alumno, self.periodo)
        alerta.refresh_from_db()
        self.assertIsNotNone(alerta.fecha_cierre)
        self.assertEqual(alerta.motivo_cierre, "recuperado")
        self.assertFalse(self._vigentes().exists())

    def test_sin_sincronizar_no_toca_alerta(self):
        self._registros(presentes=7, ausentes=3)  # 70 % -> Bajo
        recalcular_estado_alumno(self.alumno, self.periodo, sincronizar_alertas=False)
        self.assertTrue(EstadoAlumno.objects.filter(alumno=self.alumno, estado=self.bajo).exists())
        self.assertFalse(Alerta.objects.exists())
        # Tampoco cierra una vigente.
        recalcular_estado_alumno(self.alumno, self.periodo)
        self._registros(presentes=180, ausentes=0)  # -> Bien
        recalcular_estado_alumno(self.alumno, self.periodo, sincronizar_alertas=False)
        self.assertEqual(self._vigente().estado, self.bajo)

    def test_la_firma_acepta_argumentos_por_nombre(self):
        self._registros(presentes=7, ausentes=3)
        recalcular_estado_alumno(alumno=self.alumno, periodo=self.periodo)
        self.assertTrue(self._vigentes().exists())
