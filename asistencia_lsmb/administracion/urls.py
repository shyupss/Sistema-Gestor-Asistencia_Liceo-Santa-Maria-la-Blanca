from django.urls import path
from administracion import views

urlpatterns = [
    path("", views.pagina_administracion, name="administracion"),
    path("configuracion-asistencia/cargar/", views.cargar_configuracion_asistencia, name="cargar_configuracion_asistencia"),
    path("cargas/limpiar/", views.limpiar_datos_cargas_view, name="limpiar_datos_cargas"),
    path("cargas/<uuid:carga_id>/estado/", views.estado_carga_datos, name="estado_carga_datos"),
    path("cargas/<uuid:carga_id>/resultado/", views.resultado_carga_datos, name="resultado_carga_datos"),
    path("cargas/plantilla/<str:tipo>/", views.descargar_plantilla_carga, name="descargar_plantilla_carga"),
    path("alumnos/eliminar/", views.eliminar_alumnos, name="eliminar_alumnos"),
    path("matricular/", views.matricular_alumno, name="matricular_alumno"),
    path("matricula/<int:matricula_id>/editar/", views.editar_matricula, name="editar_matricula"),
    path("cursos/nuevo/", views.crear_curso, name="crear_curso_admin"),
    path("cursos/<int:curso_id>/editar/", views.editar_curso, name="editar_curso_admin"),
    path("funcionarios/nuevo/", views.crear_funcionario, name="crear_funcionario"),
    path("funcionarios/<int:funcionario_id>/editar/", views.editar_funcionario, name="editar_funcionario"),
    path("cargos/nuevo/", views.crear_cargo, name="crear_cargo"),
    path("periodos/nuevo/", views.crear_periodo, name="crear_periodo"),
    path("periodos/<int:periodo_id>/editar/", views.editar_periodo, name="editar_periodo"),
]
