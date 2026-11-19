"""cargar_asistencia sincroniza las alertas una vez por (alumno, período), al final de la carga.

Las fechas se construyen dentro del año en curso: el período va del 1 de enero
al 31 de diciembre de este año, así que hoy siempre cae dentro y los tests no
dependen del día en que se corren.
"""
import datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from administracion.services.carga_archivos import cargar_asistencia, limpiar_datos_cargas
from alertas.models import Alerta, Cargo, Estado, EstadoAlumno, Funcionario, HistorialEstadoAlumno
from alertas.services import alertas_service
from asistencia.models import Asistencia_Alumnos, Paso_Lista
from asistencia.services import asistencia_service

UN_DIA = datetime.timedelta(days=1)


class CargaAlertasTests(TestCase):
    def setUp(self):
        # La validación de feriados consulta una API externa.
        parche = mock.patch("asistencia.services.feriados.obtener_feriados", return_value=set())
        parche.start()
        self.addCleanup(parche.stop)

        anio = timezone.localdate().year
        self.periodo = PeriodoAcademico.objects.create(
            anio=anio, fecha_inicio=datetime.date(anio, 1, 1), fecha_fin=datetime.date(anio, 12, 31),
        )
        self.curso = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.primer_dia = datetime.date(anio, 1, 2)
        self.estado_matricula = EstadoMatricula.objects.get_or_create(nombre="vigente")[0]

        self.optimo = Estado.objects.create(nombre="Óptimo", umbral_minimo=95, es_no_ideal=False)
        self.adecuado = Estado.objects.create(nombre="Adecuado", umbral_minimo=85, es_no_ideal=False)
        self.atencion = Estado.objects.create(nombre="Atención", umbral_minimo=75, es_no_ideal=True)
        self.critico = Estado.objects.create(nombre="Crítico", umbral_minimo=0, es_no_ideal=True)

        Funcionario.objects.create(
            cargo=Cargo.objects.create(nombre="Cargo de los tests de carga"),
            rut="99999999-9", nombre="Funcionario de carga", email="carga@liceo.cl",
        )
        self.alumnos = [self._alumno(numero) for numero in (1, 2, 3)]

    def _alumno(self, numero, fecha_matricula=None):
        alumno = Alumno.objects.create(nombre=f"Alumno {numero}", rut=f"{numero}111111-{numero}")
        Matricula.objects.create(
            alumno=alumno, curso=self.curso, periodo=self.periodo,
            estado_matricula=self.estado_matricula,
            fecha_matricula=fecha_matricula or self.periodo.fecha_inicio,
        )
        return alumno

    def _registros(self, alumno, marcas, desde=0):
        """Una fila por día y alumno: marcas como "APPP" (día 1 = A, día 2 = P, ...)."""
        return [
            {
                "rut": alumno.rut, "nombre": alumno.nombre,
                "fecha": (self.primer_dia + (desde + indice) * UN_DIA).isoformat(),
                "estado": marca, "fila": alumno.pk,
            }
            for indice, marca in enumerate(marcas)
        ]

    def _alertas(self, alumno):
        return Alerta.objects.filter(alumno=alumno, periodo=self.periodo)

    def test_estado_no_ideal_intermedio_deja_una_sola_alerta_con_el_estado_final(self):
        alumno = self.alumnos[0]
        # 0 % -> 50 % -> 66,67 % (Crítico) -> 75 % (Atención)
        cargar_asistencia(self._registros(alumno, "APPP"))
        alerta = self._alertas(alumno).get()
        self.assertEqual(alerta.estado, self.atencion)
        self.assertIsNone(alerta.fecha_cierre)
        self.assertFalse(Alerta.objects.filter(fecha_cierre__isnull=False).exists())
        # El recálculo por fila conserva la transición intermedia en el historial.
        self.assertEqual(
            list(
                HistorialEstadoAlumno.objects.filter(alumno=alumno, periodo=self.periodo)
                .order_by("pk").values_list("estado_nuevo__nombre", flat=True)
            ),
            ["Crítico", "Atención"],
        )

    def test_alumno_que_termina_en_estado_ideal_no_tiene_alertas(self):
        alumno = self.alumnos[0]
        # Pasa por Crítico y termina en 90 % (Adecuado).
        cargar_asistencia(self._registros(alumno, "APPPPPPPPP"))
        self.assertEqual(EstadoAlumno.objects.get(alumno=alumno).estado, self.adecuado)
        self.assertFalse(Alerta.objects.exists())

    def test_sincroniza_una_vez_por_par_y_recalcula_por_fila_sin_sincronizar(self):
        uno, dos, _ = self.alumnos
        registros = self._registros(uno, "APPP") + self._registros(dos, "AA")
        with mock.patch.object(
            alertas_service, "sincronizar_alerta", wraps=alertas_service.sincronizar_alerta,
        ) as sincronizar, mock.patch(
            "administracion.services.carga_archivos.recalcular_estado_alumno",
            wraps=asistencia_service.recalcular_estado_alumno,
        ) as recalcular:
            cargar_asistencia(registros)

        self.assertEqual(sincronizar.call_count, 2)
        self.assertEqual(
            [(c.args, c.kwargs) for c in sincronizar.call_args_list],
            [((uno, self.periodo), {}), ((dos, self.periodo), {})],
        )
        self.assertEqual(recalcular.call_count, len(registros))
        for llamada in recalcular.call_args_list:
            self.assertIs(llamada.kwargs.get("sincronizar_alertas"), False)

    def test_si_falla_a_mitad_no_deja_alertas_ni_asistencias(self):
        uno, dos, _ = self.alumnos
        real = alertas_service.sincronizar_alerta
        llamadas = []

        def falla_en_el_segundo_par(alumno, periodo, *args, **kwargs):
            llamadas.append(alumno)
            if len(llamadas) == 2:
                raise RuntimeError("falla simulada")
            return real(alumno, periodo, *args, **kwargs)

        registros = self._registros(uno, "AAAA") + self._registros(dos, "AAAA")
        with mock.patch.object(
            alertas_service, "sincronizar_alerta", side_effect=falla_en_el_segundo_par,
        ), self.assertRaises(RuntimeError):
            cargar_asistencia(registros)

        self.assertEqual(llamadas, [uno, dos])
        self.assertFalse(Alerta.objects.exists())
        self.assertFalse(Asistencia_Alumnos.objects.exists())
        self.assertFalse(Paso_Lista.objects.exists())
        self.assertFalse(EstadoAlumno.objects.exists())
        self.assertFalse(HistorialEstadoAlumno.objects.exists())

    def test_el_conteo_no_cambia(self):
        uno, dos, _ = self.alumnos
        # Matriculado desde el día 3: sus dos primeras filas se omiten.
        tardio = self._alumno(4, fecha_matricula=self.primer_dia + 2 * UN_DIA)
        registros = (
            self._registros(uno, "APPP") + self._registros(dos, "PP") + self._registros(tardio, "AAPP")
        )
        self.assertEqual(cargar_asistencia(registros), {
            "pasos_creados": 4,
            "pasos_actualizados": 0,
            "asistencias_creadas": 8,
            "asistencias_actualizadas": 0,
            "registros_omitidos_sin_matricula": 2,
        })
        self.assertEqual(cargar_asistencia(registros), {
            "pasos_creados": 0,
            "pasos_actualizados": 4,
            "asistencias_creadas": 0,
            "asistencias_actualizadas": 8,
            "registros_omitidos_sin_matricula": 2,
        })

    def test_cargar_dos_veces_el_mismo_archivo_no_duplica_alertas(self):
        uno, dos, _ = self.alumnos
        registros = self._registros(uno, "APPP") + self._registros(dos, "AAAA")
        cargar_asistencia(registros)
        cargar_asistencia(registros)
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertFalse(Alerta.objects.filter(fecha_cierre__isnull=False).exists())
        self.assertEqual(self._alertas(uno).get().estado, self.atencion)
        self.assertEqual(self._alertas(dos).get().estado, self.critico)

    def test_varios_alumnos_quedan_cada_uno_con_su_alerta(self):
        atencion, critico, ideal = self.alumnos
        cargar_asistencia(
            self._registros(atencion, "APPP")  # 75 % -> Atención
            + self._registros(critico, "AAPP")  # 50 % -> Crítico
            + self._registros(ideal, "PPPP")  # 100 % -> Óptimo
        )
        self.assertEqual(self._alertas(atencion).get().estado, self.atencion)
        self.assertEqual(self._alertas(critico).get().estado, self.critico)
        self.assertFalse(self._alertas(ideal).exists())
        self.assertEqual(Alerta.objects.filter(fecha_cierre__isnull=True).count(), 2)

    def test_una_carga_posterior_actualiza_la_alerta_con_el_estado_final(self):
        alumno = self.alumnos[0]
        cargar_asistencia(self._registros(alumno, "AAAA"))  # Crítico
        primera = self._alertas(alumno).get()
        # 16 presentes más: 16/20 = 80 % -> Atención; pasa por Crítico en el camino.
        cargar_asistencia(self._registros(alumno, "P" * 16, desde=4))
        primera.refresh_from_db()
        self.assertEqual(primera.motivo_cierre, "cambio_estado")
        self.assertEqual(self._alertas(alumno).get(fecha_cierre__isnull=True).estado, self.atencion)
        self.assertEqual(self._alertas(alumno).count(), 2)

    def test_limpiar_datos_cargas_elimina_tambien_las_alertas(self):
        uno, dos, _ = self.alumnos
        cargar_asistencia(self._registros(uno, "AAAA") + self._registros(dos, "APPP"))
        self.assertEqual(Alerta.objects.count(), 2)
        conteo = limpiar_datos_cargas()
        self.assertEqual(conteo["alumnos"], 3)
        self.assertFalse(Alerta.objects.exists())
        self.assertFalse(Alumno.objects.exists())
        self.assertFalse(EstadoAlumno.objects.exists())
