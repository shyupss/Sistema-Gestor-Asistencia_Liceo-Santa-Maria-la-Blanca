import datetime
from django.test import TestCase
from django.utils import timezone
from academico.models import Alumno, Curso, EstadoMatricula, Matricula, PeriodoAcademico
from alertas.models import Alerta, Cargo, Estado, EstadoAlumno, Funcionario, HistorialEstadoAlumno
from asistencia.models import Estados_Solicitud, Justificaciones, Paso_Lista
from monitoreo.services.filtro_service import (
    calcular_actividad_reciente,
    calcular_alertas_por_nivel,
    calcular_evolucion_asistencia,
    calcular_justificaciones,
    calcular_tendencia_alertas,
    obtener_opciones_filtros,
    resolver_filtros_actividad_reciente,
    resolver_filtros_alertas_nivel,
    resolver_filtros_evolucion,
    resolver_filtros_justificaciones,
    resolver_filtros_tendencia_alertas,
)
from monitoreo.queries.filtro_queries import obtener_alumnos_ids_activos


class FiltrosDashboardTests(TestCase):
    def setUp(self):
        self.fecha = timezone.localdate()
        self.periodo = PeriodoAcademico.objects.create(
            anio=self.fecha.year,
            fecha_inicio=datetime.date(self.fecha.year, 3, 1),
            fecha_fin=datetime.date(self.fecha.year, 12, 31),
        )
        self.curso_1a = Curso.objects.create(periodo=self.periodo, nivel=1, grupo="A")
        self.curso_2b = Curso.objects.create(periodo=self.periodo, nivel=2, grupo="B")
        self.estado_mat = EstadoMatricula.objects.create(nombre="vigente")

        self.alumno_1 = Alumno.objects.create(nombre="Alumno Uno", rut="11111111-1")
        self.alumno_2 = Alumno.objects.create(nombre="Alumno Dos", rut="22222222-2")

        Matricula.objects.create(
            alumno=self.alumno_1,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_mat,
            fecha_matricula=self.periodo.fecha_inicio,
        )
        Matricula.objects.create(
            alumno=self.alumno_2,
            curso=self.curso_2b,
            periodo=self.periodo,
            estado_matricula=self.estado_mat,
            fecha_matricula=self.periodo.fecha_inicio,
        )

        self.estado_critico = Estado.objects.create(nombre="Crítico", umbral_minimo=0, genera_alerta=True)
        self.estado_atencion = Estado.objects.create(nombre="Atención", umbral_minimo=50, genera_alerta=True)

        # alumno 1 en 1°A: Crítico; alumno 2 en 2°B: Atención
        EstadoAlumno.objects.create(
            alumno=self.alumno_1, periodo=self.periodo,
            estado=self.estado_critico, porcentaje_asistencia=40,
        )
        EstadoAlumno.objects.create(
            alumno=self.alumno_2, periodo=self.periodo,
            estado=self.estado_atencion, porcentaje_asistencia=65,
        )

        # Historial: alumno_1 → Mayo; alumno_2 → Octubre
        h1 = HistorialEstadoAlumno.objects.create(
            alumno=self.alumno_1, periodo=self.periodo, estado_nuevo=self.estado_critico,
        )
        HistorialEstadoAlumno.objects.filter(pk=h1.pk).update(
            fecha_cambio=timezone.make_aware(datetime.datetime(self.fecha.year, 5, 10, 10, 0))
        )
        h2 = HistorialEstadoAlumno.objects.create(
            alumno=self.alumno_2, periodo=self.periodo, estado_nuevo=self.estado_atencion,
        )
        HistorialEstadoAlumno.objects.filter(pk=h2.pk).update(
            fecha_cambio=timezone.make_aware(datetime.datetime(self.fecha.year, 10, 1, 10, 0))
        )

        # Funcionarios
        cargo = Cargo.objects.create(nombre="Inspectoría")
        self.func_1 = Funcionario.objects.create(
            cargo=cargo, rut="10000000-1", nombre="Inspector Uno", email="f1@test.cl",
        )
        self.func_2 = Funcionario.objects.create(
            cargo=cargo, rut="20000000-2", nombre="Inspector Dos", email="f2@test.cl",
        )

        # Estados de solicitud para justificaciones
        self.estado_pendiente = Estados_Solicitud.objects.create(nombre="pendiente")
        self.estado_aceptada = Estados_Solicitud.objects.create(
            nombre="aceptada", es_estado_final=True, cubre_ausencia=True
        )

    # =========================================================
    # EVOLUCIÓN DE ASISTENCIA
    # =========================================================

    def test_resolver_filtros_evolucion_ignora_alumno(self):
        """El resolver de evolución no debe incluir la clave alumno (fue eliminada)."""
        params = {"evo_curso": "1", "evo_nivel": "2", "evo_mes": "10", "evo_alumno": "999"}
        filtros = resolver_filtros_evolucion(params)
        self.assertEqual(filtros["curso"], 1)
        self.assertEqual(filtros["nivel"], 2)
        self.assertEqual(filtros["mes"], 10)
        self.assertNotIn("alumno", filtros)

    def test_evolucion_mantiene_serie_mensual_y_adjunta_detalle_mes(self):
        filtros = {"curso": None, "nivel": None, "mes": 10}
        res = calcular_evolucion_asistencia(self.periodo, self.fecha, filtros)
        self.assertIn("Mar", res["labels"])
        self.assertIn("Oct", res["labels"])
        self.assertIsNotNone(res["detalle_mes"])
        self.assertEqual(res["detalle_mes"]["mes_numero"], 10)
        self.assertEqual(len(res["detalle_mes"]["labels"]), 31)

    # =========================================================
    # ALERTAS POR NIVEL
    # =========================================================

    def test_alertas_por_nivel_sin_filtro(self):
        datos = calcular_alertas_por_nivel(self.periodo, self.fecha, {"curso": None, "nivel": None})
        self.assertEqual(datos["total"], 2)
        self.assertEqual(datos["critico"], 1)
        self.assertEqual(datos["atencion"], 1)

    def test_alertas_por_nivel_filtrado_por_curso(self):
        datos = calcular_alertas_por_nivel(self.periodo, self.fecha, {"curso": self.curso_1a.pk, "nivel": None})
        self.assertEqual(datos["total"], 1)
        self.assertEqual(datos["critico"], 1)
        self.assertEqual(datos["atencion"], 0)

    def test_alertas_por_nivel_filtrado_por_nivel(self):
        datos = calcular_alertas_por_nivel(self.periodo, self.fecha, {"curso": None, "nivel": 2})
        self.assertEqual(datos["total"], 1)
        self.assertEqual(datos["critico"], 0)
        self.assertEqual(datos["atencion"], 1)

    # =========================================================
    # TENDENCIA DE ALERTAS
    # =========================================================

    def test_tendencia_alertas_filtrado_por_curso(self):
        res_1a = calcular_tendencia_alertas(self.periodo, self.fecha, {"curso": self.curso_1a.pk, "nivel": None})
        idx_mayo = res_1a["labels"].index("May")
        idx_oct = res_1a["labels"].index("Oct")
        self.assertEqual(res_1a["valores"][idx_mayo], 1)
        self.assertEqual(res_1a["valores"][idx_oct], 0)

        res_2b = calcular_tendencia_alertas(self.periodo, self.fecha, {"curso": self.curso_2b.pk, "nivel": None})
        self.assertEqual(res_2b["valores"][idx_mayo], 0)
        self.assertEqual(res_2b["valores"][idx_oct], 1)

    def test_tendencia_alertas_filtrado_por_nivel(self):
        res = calcular_tendencia_alertas(self.periodo, self.fecha, {"curso": None, "nivel": 1})
        idx_mayo = res["labels"].index("May")
        idx_oct = res["labels"].index("Oct")
        self.assertEqual(res["valores"][idx_mayo], 1)
        self.assertEqual(res["valores"][idx_oct], 0)

    # =========================================================
    # JUSTIFICACIONES PENDIENTES
    # =========================================================

    def test_resolver_filtros_justificaciones(self):
        params = {"just_curso": str(self.curso_1a.pk), "just_nivel": "2"}
        filtros = resolver_filtros_justificaciones(params)
        self.assertEqual(filtros["curso"], self.curso_1a.pk)
        self.assertEqual(filtros["nivel"], 2)

    def test_justificaciones_sin_filtro_muestra_todas(self):
        """Sin filtro, se deben ver las justificaciones pendientes de ambos alumnos."""
        Justificaciones.objects.create(
            alumno=self.alumno_1, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 1",
        )
        Justificaciones.objects.create(
            alumno=self.alumno_2, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 2",
        )
        datos = calcular_justificaciones(self.periodo, self.fecha, {"curso": None, "nivel": None})
        self.assertEqual(datos["pendientes_count"], 2)

    def test_justificaciones_filtrado_por_curso(self):
        """Al filtrar por 1°A solo debe aparecer la justificación del alumno 1."""
        Justificaciones.objects.create(
            alumno=self.alumno_1, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 1",
        )
        Justificaciones.objects.create(
            alumno=self.alumno_2, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 2",
        )
        datos = calcular_justificaciones(self.periodo, self.fecha, {"curso": self.curso_1a.pk, "nivel": None})
        self.assertEqual(datos["pendientes_count"], 1)
        self.assertEqual(datos["justificaciones_pendientes"][0]["alumno"], self.alumno_1.nombre)

    def test_justificaciones_filtrado_por_nivel(self):
        """Al filtrar por nivel 2 solo debe aparecer la justificación del alumno 2."""
        Justificaciones.objects.create(
            alumno=self.alumno_1, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 1",
        )
        Justificaciones.objects.create(
            alumno=self.alumno_2, estado_solicitud=self.estado_pendiente,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Just alumno 2",
        )
        datos = calcular_justificaciones(self.periodo, self.fecha, {"curso": None, "nivel": 2})
        self.assertEqual(datos["pendientes_count"], 1)
        self.assertEqual(datos["justificaciones_pendientes"][0]["alumno"], self.alumno_2.nombre)

    def test_justificaciones_promedio_resolucion_incluye_solo_filtradas(self):
        """El promedio de resolución debe calcularse sobre las resueltas del filtro activo."""
        ahora = timezone.now()
        resuelta_1a = Justificaciones.objects.create(
            alumno=self.alumno_1, estado_solicitud=self.estado_aceptada,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Resuelta 1A",
            funcionario_resuelve=self.func_1,
        )
        resuelta_1a.fecha_registro = ahora - datetime.timedelta(days=4)
        resuelta_1a.fecha_resolucion = ahora - datetime.timedelta(days=2)
        resuelta_1a.save(update_fields=["fecha_registro", "fecha_resolucion"])

        resuelta_2b = Justificaciones.objects.create(
            alumno=self.alumno_2, estado_solicitud=self.estado_aceptada,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Resuelta 2B",
            funcionario_resuelve=self.func_2,
        )
        resuelta_2b.fecha_registro = ahora - datetime.timedelta(days=10)
        resuelta_2b.fecha_resolucion = ahora - datetime.timedelta(days=0)
        resuelta_2b.save(update_fields=["fecha_registro", "fecha_resolucion"])

        datos_1a = calcular_justificaciones(self.periodo, self.fecha, {"curso": self.curso_1a.pk, "nivel": None})
        self.assertEqual(datos_1a["prom_resolucion"], "2.0 días")

        datos_sin_filtro = calcular_justificaciones(self.periodo, self.fecha, {"curso": None, "nivel": None})
        self.assertNotEqual(datos_sin_filtro["prom_resolucion"], datos_1a["prom_resolucion"])

    # =========================================================
    # ACTIVIDAD RECIENTE
    # =========================================================

    def test_resolver_filtros_actividad(self):
        from django.http import QueryDict
        qd = QueryDict(mutable=True)
        qd["act_curso"] = str(self.curso_1a.pk)
        qd.setlist("act_tipo", ["asistencia", "justificacion"])
        qd["act_actor"] = "funcionario"

        filtros = resolver_filtros_actividad_reciente(qd)
        self.assertEqual(filtros["curso"], self.curso_1a.pk)
        self.assertEqual(filtros["actor"], "funcionario")
        self.assertIn("asistencia", filtros["tipos"])
        self.assertIn("justificacion", filtros["tipos"])
        self.assertNotIn("alerta", filtros["tipos"])
        self.assertNotIn("nivel", filtros)
        self.assertNotIn("alumno", filtros)
        self.assertNotIn("funcionario", filtros)

    def test_resolver_actividad_acepta_mapping_y_tipos_separados_por_coma(self):
        filtros = resolver_filtros_actividad_reciente({
            "act_tipo": "asistencia,retiro",
        })

        self.assertEqual(sorted(filtros["tipos"]), ["asistencia", "retiro"])

    def test_matriculas_activas_respetan_inicio_y_termino(self):
        alumno_futuro = Alumno.objects.create(nombre="Alumno Futuro", rut="33333333-3")
        alumno_terminado = Alumno.objects.create(nombre="Alumno Terminado", rut="44444444-4")
        alumno_hoy = Alumno.objects.create(nombre="Alumno Hoy", rut="55555555-5")

        Matricula.objects.create(
            alumno=alumno_futuro,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_mat,
            fecha_matricula=self.fecha + datetime.timedelta(days=1),
        )
        Matricula.objects.create(
            alumno=alumno_terminado,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_mat,
            fecha_matricula=self.periodo.fecha_inicio,
            fecha_termino=self.fecha - datetime.timedelta(days=1),
        )
        Matricula.objects.create(
            alumno=alumno_hoy,
            curso=self.curso_1a,
            periodo=self.periodo,
            estado_matricula=self.estado_mat,
            fecha_matricula=self.periodo.fecha_inicio,
            fecha_termino=self.fecha,
        )

        ids = obtener_alumnos_ids_activos(self.periodo.pk, self.fecha, curso_id=self.curso_1a.pk)

        self.assertNotIn(alumno_futuro.pk, ids)
        self.assertNotIn(alumno_terminado.pk, ids)
        self.assertIn(alumno_hoy.pk, ids)

    def _crear_paso_lista(self, curso, funcionario):
        return Paso_Lista.objects.create(
            curso=curso,
            funcionario=funcionario,
            fecha=self.fecha,
        )

    def _crear_justificacion(self, alumno, estado, funcionario_resuelve=None, fecha_resolucion=None):
        j = Justificaciones.objects.create(
            alumno=alumno, estado_solicitud=estado,
            fecha_inicio=self.fecha, fecha_fin=self.fecha, resumen="Test just",
            funcionario_resuelve=funcionario_resuelve,
            fecha_resolucion=fecha_resolucion,
        )
        return j

    def test_actividad_filtrado_por_tipo_asistencia(self):
        """Con tipo=asistencia, los eventos de justificación no aparecen."""
        self._crear_paso_lista(self.curso_1a, self.func_1)
        self._crear_justificacion(self.alumno_1, self.estado_pendiente)

        from django.http import QueryDict
        qd = QueryDict(mutable=True)
        qd.setlist("act_tipo", ["asistencia"])
        filtros = resolver_filtros_actividad_reciente(qd)
        eventos = calcular_actividad_reciente(self.periodo, self.fecha, filtros)

        tipos = {e["tipo_categoria"] for e in eventos}
        self.assertIn("asistencia", tipos)
        self.assertNotIn("justificacion", tipos)

    def test_actividad_filtrado_por_curso(self):
        """Con filtro de curso 1°A, los eventos de 2°B no aparecen."""
        self._crear_paso_lista(self.curso_1a, self.func_1)
        self._crear_paso_lista(self.curso_2b, self.func_2)

        filtros = resolver_filtros_actividad_reciente({"act_curso": str(self.curso_1a.pk)})
        eventos = calcular_actividad_reciente(self.periodo, self.fecha, filtros)

        cursos_en_eventos = {e["curso"] for e in eventos if e["tipo_categoria"] == "asistencia"}
        self.assertIn("I° Medio A", cursos_en_eventos)
        self.assertNotIn("II° Medio B", cursos_en_eventos)

    def test_actividad_filtrado_por_actor_funcionario(self):
        """Actor funcionario muestra eventos de funcionarios, no registros del sistema."""
        self._crear_paso_lista(self.curso_1a, self.func_1)
        self._crear_justificacion(self.alumno_1, self.estado_pendiente)

        filtros = resolver_filtros_actividad_reciente({"act_actor": "funcionario"})
        eventos = calcular_actividad_reciente(self.periodo, self.fecha, filtros)

        tipos = {e["tipo_categoria"] for e in eventos}
        self.assertIn("asistencia", tipos)
        self.assertNotIn("justificacion", tipos)

    def test_actividad_actor_sistema_muestra_solo_registros_automaticos(self):
        """
        Actor=sistema debe mostrar solo justificaciones/retiros nuevos registrados automáticamente,
        no eventos de funcionarios (alertas ni pases de lista).
        """
        self._crear_paso_lista(self.curso_1a, self.func_1)
        self._crear_justificacion(self.alumno_1, self.estado_pendiente)
        Alerta.objects.create(
            alumno=self.alumno_1, periodo=self.periodo,
            estado=self.estado_critico, funcionario=self.func_1,
        )

        from django.http import QueryDict
        qd = QueryDict(mutable=True)
        qd["act_actor"] = "sistema"
        filtros = resolver_filtros_actividad_reciente(qd)
        eventos = calcular_actividad_reciente(self.periodo, self.fecha, filtros)

        tipos = {e["tipo_categoria"] for e in eventos}
        self.assertNotIn("asistencia", tipos)
        self.assertNotIn("alerta", tipos)
        # Las justificaciones nuevas son eventos de sistema
        self.assertIn("justificacion", tipos)

    # =========================================================
    # CATÁLOGOS (opciones_filtros)
    # =========================================================

    def test_opciones_filtros_incluye_todos_los_catalogos_nuevos(self):
        opciones = obtener_opciones_filtros(
            self.periodo.pk, self.fecha,
            filtros_just={"curso": self.curso_1a.pk, "nivel": None},
            filtros_act={"actor": "funcionario", "curso": None, "tipos": []},
        )
        # Catálogos presentes
        self.assertIn("tipos_actividad", opciones)
        self.assertIn("actores_actividad", opciones)

        # No existe el antiguo alumnos_evolucion
        self.assertNotIn("alumnos_evolucion", opciones)

        # Activos de los dos nuevos componentes
        self.assertIn("just", opciones["activos"])
        self.assertIn("act", opciones["activos"])
        self.assertEqual(opciones["activos"]["just"]["curso"], self.curso_1a.pk)
        self.assertEqual(opciones["activos"]["act"]["actor"], "funcionario")

        # Tipos de actividad
        valores_tipos = [t["valor"] for t in opciones["tipos_actividad"]]
        self.assertEqual(sorted(valores_tipos), ["alerta", "asistencia", "justificacion", "retiro"])
