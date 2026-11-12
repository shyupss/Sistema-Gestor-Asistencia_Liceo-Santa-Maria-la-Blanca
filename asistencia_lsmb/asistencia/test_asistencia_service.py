"""Tests de caracterización de asistencia_service.

Fijan el comportamiento ACTUAL de recalcular_estado_alumno y
clasificar_asistencia, aunque no sea el ideal.
"""
import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase

from academico.models import Alumno, Curso, PeriodoAcademico
from alertas.models import (
    Cargo,
    Estado,
    EstadoAlumno,
    Funcionario,
    HistorialEstadoAlumno,
)
from asistencia.models import (
    Asistencia_Alumnos,
    Estados_Solicitud,
    Justificaciones,
    Paso_Lista,
    Tipos_Asistencia,
)
from asistencia.services.asistencia_service import (
    clasificar_asistencia,
    recalcular_estado_alumno,
)


class BaseServiceTests(TestCase):
    def setUp(self):
        self.periodo = PeriodoAcademico.objects.create(
            anio=2026,
            fecha_inicio=datetime.date(2026, 3, 1),
            fecha_fin=datetime.date(2026, 12, 31),
        )
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.alumno = Alumno.objects.create(nombre="Alumno Uno", rut="11111111-1")
        cargo = Cargo.objects.create(nombre="Inspector")
        self.funcionario = Funcionario.objects.create(
            cargo=cargo, rut="22222222-2", nombre="Inspector", email="i@example.com"
        )
        self.presente = Tipos_Asistencia.objects.create(nombre="Presente", cuenta_como_ausencia=False)
        self.ausente = Tipos_Asistencia.objects.create(nombre="Ausente", cuenta_como_ausencia=True)
        self.atrasado = Tipos_Asistencia.objects.create(nombre="Atrasado", cuenta_como_ausencia=True)

        self.critico = Estado.objects.create(nombre="Crítico", umbral_minimo=0, genera_alerta=True, es_no_ideal=True)
        self.atencion = Estado.objects.create(nombre="Atención", umbral_minimo=75, genera_alerta=True, es_no_ideal=True)
        self.normal = Estado.objects.create(nombre="Normal", umbral_minimo=90, genera_alerta=False, es_no_ideal=False)

        self.aprobada = Estados_Solicitud.objects.create(nombre="Aprobada", cubre_ausencia=True)
        self.pendiente = Estados_Solicitud.objects.create(nombre="Pendiente", cubre_ausencia=False)
        self.rechazada = Estados_Solicitud.objects.create(nombre="Rechazada", cubre_ausencia=False)

        self._dia = 0

    def _registro(self, tipo, alumno=None, curso=None, justificacion=None):
        """Crea un Paso_Lista (fecha única) y un registro de asistencia."""
        self._dia += 1
        curso = curso or self.curso
        fecha = datetime.date(2026, 3, 1) + datetime.timedelta(days=self._dia)
        paso = Paso_Lista.objects.create(
            curso=curso, funcionario=self.funcionario, fecha=fecha
        )
        return Asistencia_Alumnos.objects.create(
            alumno=alumno or self.alumno,
            paso_lista=paso,
            tipo_asistencia=tipo,
            justificacion=justificacion,
        )

    def _registros(self, presentes, ausentes, **kwargs):
        for _ in range(presentes):
            self._registro(self.presente, **kwargs)
        for _ in range(ausentes):
            self._registro(self.ausente, **kwargs)

    def _justificacion(self, estado, fecha=None):
        fecha = fecha or datetime.date(2026, 3, 2)
        return Justificaciones.objects.create(
            alumno=self.alumno,
            estado_solicitud=estado,
            fecha_inicio=fecha,
            fecha_fin=fecha,
            resumen="Justificación de prueba",
        )

    def _porcentaje(self):
        return EstadoAlumno.objects.get(alumno=self.alumno, periodo=self.periodo).porcentaje_asistencia


class CalculoPorcentajeTests(BaseServiceTests):
    def test_diez_registros_dos_ausencias_da_80_y_estado_segun_umbrales(self):
        # Fija: 8/10 presentes = 80,00 -> "Atención" (umbral 75 <= 80 < 90).
        self._registros(presentes=8, ausentes=2)
        resultado = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(resultado.porcentaje_asistencia, Decimal("80.00"))
        self.assertEqual(resultado.estado, self.atencion)

    def test_atrasado_cuenta_como_ausencia(self):
        # Fija: un tipo con cuenta_como_ausencia=True resta igual que "Ausente".
        self._registros(presentes=9, ausentes=0)
        self._registro(self.atrasado)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("90.00"))

    def test_ausencia_con_justificacion_que_cubre_no_cuenta_como_falta(self):
        # Fija: FK a justificación con cubre_ausencia=True neutraliza la ausencia.
        self._registros(presentes=9, ausentes=0)
        self._registro(self.ausente, justificacion=self._justificacion(self.aprobada))
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("100.00"))

    def test_ausencia_con_justificacion_que_no_cubre_si_cuenta(self):
        # Fija: FK a justificación pendiente/rechazada NO neutraliza la ausencia.
        for estado in (self.pendiente, self.rechazada):
            with self.subTest(estado=estado.nombre):
                Asistencia_Alumnos.objects.all().delete()
                self._registros(presentes=9, ausentes=0)
                self._registro(self.ausente, justificacion=self._justificacion(estado))
                recalcular_estado_alumno(self.alumno, self.periodo)
                self.assertEqual(self._porcentaje(), Decimal("90.00"))

    def test_ausencia_sin_fk_cuenta_aunque_exista_justificacion_que_cubre_la_fecha(self):
        # Fija: hoy solo importa la FK; una Justificaciones aprobada por fecha se ignora.
        self._registros(presentes=9, ausentes=0)
        registro = self._registro(self.ausente)
        self._justificacion(self.aprobada, fecha=registro.paso_lista.fecha)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("90.00"))

    def test_presente_con_justificacion_sigue_contando_como_presente(self):
        # Fija: la justificación no altera registros que no son ausencia.
        self._registros(presentes=9, ausentes=0)
        self._registro(self.presente, justificacion=self._justificacion(self.aprobada))
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("100.00"))

    def test_alumno_sin_registros_tiene_0_y_estado_de_menor_umbral(self):
        # Fija: sin registros el porcentaje es 0,00 y cae en el estado más bajo.
        # Posible bug de negocio: un alumno sin listas queda como "Crítico".
        resultado = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(resultado.porcentaje_asistencia, Decimal("0.00"))
        self.assertEqual(resultado.estado, self.critico)

    def test_redondeo_a_dos_decimales_dos_de_tres_es_66_67(self):
        # Fija: 2/3 = 66,666... se redondea a 66,67.
        self._registros(presentes=2, ausentes=1)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("66.67"))

    def test_redondeo_hacia_abajo_un_tercio_es_33_33(self):
        # Fija: 1/3 = 33,333... se redondea a 33,33.
        self._registros(presentes=1, ausentes=2)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("33.33"))

    def test_redondeo_half_up_en_la_mitad_exacta(self):
        # Fija: 1/800 = 0,125 exacto -> 0,13 (HALF_UP; el redondeo bancario daría 0,12).
        self._registros(presentes=1, ausentes=799)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("0.13"))

    def test_solo_cuentan_registros_del_periodo_indicado(self):
        # Fija: registros de otro período se ignoran por completo.
        otro_periodo = PeriodoAcademico.objects.create(
            anio=2025,
            fecha_inicio=datetime.date(2025, 3, 1),
            fecha_fin=datetime.date(2025, 12, 31),
        )
        curso_otro = Curso.objects.create(periodo=otro_periodo, nivel=1, grupo="A")
        self._registros(presentes=10, ausentes=0)
        self._registros(presentes=0, ausentes=10, curso=curso_otro)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("100.00"))

    def test_se_suman_registros_de_distintos_cursos_del_mismo_periodo(self):
        # Fija: el cálculo agrega todos los cursos del período.
        curso_b = Curso.objects.create(periodo=self.periodo, nivel=2, grupo="B")
        self._registros(presentes=5, ausentes=0)
        self._registros(presentes=0, ausentes=5, curso=curso_b)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("50.00"))


class ClasificarAsistenciaTests(TestCase):
    def setUp(self):
        self.critico = Estado.objects.create(nombre="Crítico", umbral_minimo=0)
        self.atencion = Estado.objects.create(nombre="Atención", umbral_minimo=75)
        self.normal = Estado.objects.create(nombre="Normal", umbral_minimo=90)
        # Orden que usa el servicio: de mayor a menor umbral.
        self.estados = [self.normal, self.atencion, self.critico]

    def test_elige_el_primer_estado_cuyo_umbral_se_alcanza(self):
        # Fija: recorre en orden y devuelve el primero con porcentaje >= umbral.
        self.assertEqual(clasificar_asistencia(Decimal("80"), self.estados), self.atencion)
        self.assertEqual(clasificar_asistencia(Decimal("95"), self.estados), self.normal)
        self.assertEqual(clasificar_asistencia(Decimal("10"), self.estados), self.critico)

    def test_borde_exacto_porcentaje_igual_al_umbral(self):
        # Fija: la comparación es >=, el umbral exacto SÍ alcanza el estado.
        self.assertEqual(clasificar_asistencia(Decimal("90.00"), self.estados), self.normal)
        self.assertEqual(clasificar_asistencia(Decimal("75.00"), self.estados), self.atencion)

    def test_justo_bajo_el_umbral_cae_al_estado_siguiente(self):
        # Fija: 89,99 no alcanza 90 y cae en "Atención".
        self.assertEqual(clasificar_asistencia(Decimal("89.99"), self.estados), self.atencion)

    def test_si_ninguno_aplica_devuelve_el_ultimo_de_la_lista(self):
        # Fija: sin coincidencia se devuelve estados[-1], no None.
        estados = [self.normal, self.atencion]
        self.assertEqual(clasificar_asistencia(Decimal("10"), estados), self.atencion)

    def test_lista_vacia_devuelve_none(self):
        # Fija: sin estados el resultado es None.
        self.assertIsNone(clasificar_asistencia(Decimal("50"), []))

    def test_no_depende_del_orden_de_entrada(self):
        # Fija: ordena internamente por -umbral_minimo; con entrada ascendente
        # devuelve igual el estado de mayor umbral alcanzado.
        ascendente = [self.critico, self.atencion, self.normal]
        self.assertEqual(clasificar_asistencia(Decimal("95"), ascendente), self.normal)

    def test_acepta_objetos_con_umbral_minimo(self):
        # Fija: solo usa el atributo umbral_minimo del estado (duck typing).
        bajo = SimpleNamespace(umbral_minimo=Decimal("0"))
        alto = SimpleNamespace(umbral_minimo=Decimal("50"))
        self.assertIs(clasificar_asistencia(Decimal("60"), [alto, bajo]), alto)


class EstadoEHistorialTests(BaseServiceTests):
    def test_primera_ejecucion_crea_estado_alumno_e_historial_sin_anterior(self):
        # Fija: se crea EstadoAlumno y un historial con estado_anterior=None.
        self._registros(presentes=10, ausentes=0)
        resultado = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(EstadoAlumno.objects.count(), 1)
        self.assertEqual(resultado.estado, self.normal)
        historial = HistorialEstadoAlumno.objects.get()
        self.assertIsNone(historial.estado_anterior)
        self.assertEqual(historial.estado_nuevo, self.normal)
        self.assertEqual(historial.alumno, self.alumno)
        self.assertEqual(historial.periodo, self.periodo)

    def test_segunda_ejecucion_mismo_estado_no_crea_otro_historial(self):
        # Fija: sin cambio de estado no se agrega historial ni se duplica EstadoAlumno.
        self._registros(presentes=10, ausentes=0)
        recalcular_estado_alumno(self.alumno, self.periodo)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(EstadoAlumno.objects.count(), 1)
        self.assertEqual(HistorialEstadoAlumno.objects.count(), 1)

    def test_mismo_estado_con_otro_porcentaje_actualiza_sin_historial(self):
        # Fija: el porcentaje se actualiza aunque el estado no cambie.
        self._registros(presentes=10, ausentes=0)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self._registro(self.ausente)  # 10/11 = 90,91 -> sigue "Normal"
        recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(self._porcentaje(), Decimal("90.91"))
        self.assertEqual(EstadoAlumno.objects.get().estado, self.normal)
        self.assertEqual(HistorialEstadoAlumno.objects.count(), 1)

    def test_cambio_de_estado_crea_historial_con_anterior_y_actualiza(self):
        # Fija: al cambiar de estado se registra anterior/nuevo y se actualiza la misma fila.
        self._registros(presentes=10, ausentes=0)
        recalcular_estado_alumno(self.alumno, self.periodo)
        self._registros(presentes=0, ausentes=3)  # 10/13 = 76,92 -> "Atención"
        resultado = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(EstadoAlumno.objects.count(), 1)
        self.assertEqual(resultado.estado, self.atencion)
        self.assertEqual(HistorialEstadoAlumno.objects.count(), 2)
        ultimo = HistorialEstadoAlumno.objects.order_by("-pk").first()
        self.assertEqual(ultimo.estado_anterior, self.normal)
        self.assertEqual(ultimo.estado_nuevo, self.atencion)

    def test_sin_estados_devuelve_none_y_no_crea_nada(self):
        # Fija: sin ningún Estado la función retorna None sin escribir en la BD.
        self._registros(presentes=5, ausentes=0)
        Estado.objects.all().delete()
        self.assertIsNone(recalcular_estado_alumno(self.alumno, self.periodo))
        self.assertEqual(EstadoAlumno.objects.count(), 0)
        self.assertEqual(HistorialEstadoAlumno.objects.count(), 0)

    def test_retorna_la_instancia_de_estado_alumno_persistida(self):
        # Fija: el valor de retorno es el EstadoAlumno guardado.
        self._registros(presentes=10, ausentes=0)
        resultado = recalcular_estado_alumno(self.alumno, self.periodo)
        self.assertEqual(resultado, EstadoAlumno.objects.get())

    def test_estados_de_distintos_alumnos_no_se_mezclan(self):
        # Fija: EstadoAlumno es por (alumno, período); otro alumno tiene su propia fila.
        otro = Alumno.objects.create(nombre="Alumno Dos", rut="33333333-3")
        self._registros(presentes=10, ausentes=0)
        self._registros(presentes=0, ausentes=10, alumno=otro)
        recalcular_estado_alumno(self.alumno, self.periodo)
        recalcular_estado_alumno(otro, self.periodo)
        self.assertEqual(EstadoAlumno.objects.count(), 2)
        self.assertEqual(EstadoAlumno.objects.get(alumno=self.alumno).estado, self.normal)
        self.assertEqual(EstadoAlumno.objects.get(alumno=otro).estado, self.critico)
