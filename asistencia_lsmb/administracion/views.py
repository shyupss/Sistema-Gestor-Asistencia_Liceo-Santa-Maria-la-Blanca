import re

from django.contrib import messages
from django.core.exceptions import MultipleObjectsReturned
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from academico.models import (
    Alumno,
    AlumnoApoderado,
    Apoderado,
    Curso,
    EstadoMatricula,
    Matricula,
    PeriodoAcademico,
)
from alertas.models import Cargo, Funcionario

from .catalogos import cargar_catalogos_asistencia

from .forms import (
    AlumnoApoderadoForm,
    AlumnoForm,
    ApoderadoForm,
    CargoForm,
    CursoForm,
    EliminarAlumnosForm,
    FuncionarioForm,
    MatriculaForm,
    PeriodoForm,
)


def _indices_apoderados(post_data):
    indices = []
    for key in post_data:
        if not key.startswith("apoderado_"):
            continue
        if key.endswith("-rut"):
            suffix_length = len("-rut")
        elif key.endswith("_rut"):
            suffix_length = len("_rut")
        else:
            continue
        try:
            indices.append(int(key[len("apoderado_"):-suffix_length]))
        except ValueError:
            continue
    return sorted(set(indices))


def _guardar_apoderado(form, existing_id=None):
    if existing_id:
        apoderado = get_object_or_404(Apoderado, pk=existing_id)
    else:
        apoderado, _ = Apoderado.objects.get_or_create(
            rut=form.cleaned_data["rut"],
        )
    apoderado.nombre = form.cleaned_data["nombre"]
    apoderado.telefono = form.cleaned_data.get("telefono")
    apoderado.email = form.cleaned_data.get("email")
    apoderado.save()
    return apoderado


def _clave_orden_natural(texto):
    return [
        int(fragmento) if fragmento.isdigit() else fragmento.casefold()
        for fragmento in re.split(r"(\d+)", texto or "")
    ]


# ─────────────────────────── Página principal ────────────────────────────────

def pagina_administracion(request):
    fecha_actual = timezone.now()
    anio_actual = fecha_actual.year

    # Garantizar que al menos exista el período del año actual
    PeriodoAcademico.objects.get_or_create(
        anio=anio_actual,
        defaults={
            "fecha_inicio": f"{anio_actual}-03-01",
            "fecha_fin": f"{anio_actual}-12-31",
        },
    )

    matriculas = list(
        Matricula.objects.filter(fecha_termino__isnull=True)
        .select_related(
            "alumno",
            "curso",
            "curso__periodo",
            "estado_matricula",
        )
    )
    matriculas.sort(key=lambda matricula: _clave_orden_natural(matricula.alumno.nombre))

    cursos = (
        Curso.objects.select_related("periodo", "profesor_jefe")
        .order_by("-periodo__anio", "nivel", "grupo")
    )

    funcionarios = (
        Funcionario.objects.select_related("cargo")
        .order_by("nombre")
    )

    cargos = Cargo.objects.order_by("nombre")
    periodos = PeriodoAcademico.objects.order_by("-anio")

    return render(
        request,
        "administracion/base.html",
        {
            "page_title": "Administración",
            "fecha_actual": fecha_actual,
            "matriculas": matriculas,
            "cursos": cursos,
            "funcionarios": funcionarios,
            "cargos": cargos,
            "periodos": periodos,
        },
    )


@require_POST
def cargar_configuracion_asistencia(request):
    try:
        creados, actualizados = cargar_catalogos_asistencia()
    except MultipleObjectsReturned:
        messages.error(
            request,
            "Hay estados o tipos repetidos que solo se diferencian por mayúsculas. "
            "Revisa esos registros antes de cargar la configuración; no se guardaron cambios.",
        )
    else:
        messages.success(
            request,
            f"Configuración de asistencia lista: {creados} registros creados y "
            f"{actualizados} actualizados.",
        )
    return redirect("administracion")


# ─────────────────────────── Cargos y Periodos ───────────────────────────────

def crear_cargo(request):
    if request.method == "POST":
        form = CargoForm(request.POST)
        if form.is_valid():
            cargo = form.save()
            messages.success(request, f"Cargo '{cargo.nombre}' creado exitosamente.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                return redirect(next_url)
            return redirect("administracion")
    else:
        form = CargoForm()

    return render(request, "administracion/cargo_form.html", {
        "page_title": "Nuevo Cargo",
        "form": form,
        "next": request.GET.get("next", ""),
    })


def crear_periodo(request):
    if request.method == "POST":
        form = PeriodoForm(request.POST)
        if form.is_valid():
            periodo = form.save()
            messages.success(request, f"Período Académico {periodo.anio} creado exitosamente.")
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url:
                return redirect(next_url)
            return redirect("administracion")
    else:
        form = PeriodoForm()

    return render(request, "administracion/periodo_form.html", {
        "page_title": "Nuevo Período Académico",
        "form": form,
        "next": request.GET.get("next", ""),
    })


def editar_periodo(request, periodo_id):
    periodo = get_object_or_404(PeriodoAcademico, pk=periodo_id)
    if request.method == "POST":
        form = PeriodoForm(request.POST, instance=periodo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Período Académico {periodo.anio} actualizado exitosamente.")
            return redirect("administracion")
    else:
        form = PeriodoForm(instance=periodo)

    return render(request, "administracion/periodo_form.html", {
        "page_title": "Editar Período Académico",
        "form": form,
        "periodo": periodo,
    })


# ─────────────────────────── Matrículas ──────────────────────────────────────

@transaction.atomic
def matricular_alumno(request):
    if request.method == "POST":
        alumno_form = AlumnoForm(request.POST)
        matricula_form = MatriculaForm(request.POST)

        apoderado_forms = []
        relacion_forms = []
        for i in _indices_apoderados(request.POST):
            prefix = f"apoderado_{i}"
            existing_id = request.POST.get(f"{prefix}-existing_id")
            apoderado_instance = (
                Apoderado.objects.filter(pk=existing_id).first()
                if existing_id
                else None
            )
            apoderado_forms.append(
                ApoderadoForm(
                    request.POST,
                    prefix=prefix,
                    instance=apoderado_instance,
                )
            )
            relacion_forms.append(AlumnoApoderadoForm(request.POST, prefix=f"relacion_{i}"))

        all_valid = alumno_form.is_valid() and matricula_form.is_valid()
        apoderados_valid = all(f.is_valid() for f in apoderado_forms + relacion_forms)

        if all_valid and apoderados_valid:
            try:
                alumno = alumno_form.save()
                estado_vigente, _ = EstadoMatricula.objects.get_or_create(
                    nombre="vigente",
                    defaults={"descripcion": "Alumno con matrícula vigente"},
                )
                matricula = matricula_form.save(commit=False)
                matricula.alumno = alumno
                matricula.estado_matricula = estado_vigente
                matricula.save()

                for ap_form, rel_form in zip(apoderado_forms, relacion_forms):
                    apoderado = _guardar_apoderado(
                        ap_form,
                        request.POST.get(f"{ap_form.prefix}-existing_id"),
                    )
                    AlumnoApoderado.objects.create(
                        alumno=alumno,
                        apoderado=apoderado,
                        tipo_relacion=rel_form.cleaned_data["tipo_relacion"],
                        recibe_notificaciones=rel_form.cleaned_data["recibe_notificaciones"],
                    )

                messages.success(request, f"Alumno {alumno.nombre} matriculado exitosamente.")
                return redirect("administracion")

            except Exception as e:
                messages.error(request, f"Error al matricular: {e}")

        return render(request, "administracion/matricular.html", {
            "page_title": "Nueva Matrícula",
            "alumno_form": alumno_form,
            "matricula_form": matricula_form,
            "apoderado_forms": list(zip(apoderado_forms, relacion_forms)),
            "apoderado_count": len(apoderado_forms),
            "apoderados_disponibles": Apoderado.objects.order_by("nombre"),
        })

    # GET
    alumno_form = AlumnoForm()
    matricula_form = MatriculaForm()
    apoderado_forms = [ApoderadoForm(prefix="apoderado_0")]
    relacion_forms = [AlumnoApoderadoForm(prefix="relacion_0")]

    return render(request, "administracion/matricular.html", {
        "page_title": "Nueva Matrícula",
        "alumno_form": alumno_form,
        "matricula_form": matricula_form,
        "apoderado_forms": list(zip(apoderado_forms, relacion_forms)),
        "apoderado_count": 1,
        "apoderados_disponibles": Apoderado.objects.order_by("nombre"),
    })


@transaction.atomic
def editar_matricula(request, matricula_id):
    matricula = get_object_or_404(Matricula, pk=matricula_id, fecha_termino__isnull=True)
    alumno = matricula.alumno
    relaciones_existentes = AlumnoApoderado.objects.filter(alumno=alumno).select_related("apoderado")

    if request.method == "POST":
        alumno_form = AlumnoForm(request.POST, instance=alumno)
        matricula_form = MatriculaForm(request.POST, instance=matricula)

        apoderado_forms = []
        relacion_forms = []
        relaciones_existentes_lista = list(relaciones_existentes)
        for posicion, i in enumerate(_indices_apoderados(request.POST)):
            relacion_inst = (
                relaciones_existentes_lista[posicion]
                if posicion < len(relaciones_existentes_lista)
                else None
            )
            apoderado_inst = relacion_inst.apoderado if relacion_inst else None
            apoderado_forms.append(
                ApoderadoForm(request.POST, prefix=f"apoderado_{i}", instance=apoderado_inst)
            )
            relacion_forms.append(
                AlumnoApoderadoForm(request.POST, prefix=f"relacion_{i}", instance=relacion_inst)
            )

        all_valid = alumno_form.is_valid() and matricula_form.is_valid()
        apoderados_valid = all(f.is_valid() for f in apoderado_forms + relacion_forms)

        if all_valid and apoderados_valid:
            alumno_form.save()
            matricula_form.save()

            relaciones_existentes.delete()
            for ap_form, rel_form in zip(apoderado_forms, relacion_forms):
                apoderado = _guardar_apoderado(ap_form)

                AlumnoApoderado.objects.create(
                    alumno=alumno,
                    apoderado=apoderado,
                    tipo_relacion=rel_form.cleaned_data["tipo_relacion"],
                    recibe_notificaciones=rel_form.cleaned_data["recibe_notificaciones"],
                )

            messages.success(request, f"Matrícula de {alumno.nombre} actualizada exitosamente.")
            return redirect("administracion")

        return render(request, "administracion/editar_matricula.html", {
            "page_title": "Editar Matrícula",
            "alumno_form": alumno_form,
            "matricula_form": matricula_form,
            "apoderado_forms": list(zip(apoderado_forms, relacion_forms)),
            "apoderado_count": len(apoderado_forms),
            "matricula": matricula,
        })

    # GET
    alumno_form = AlumnoForm(instance=alumno)
    matricula_form = MatriculaForm(instance=matricula)
    apoderado_forms = []
    relacion_forms = []
    for i, rel in enumerate(relaciones_existentes):
        apoderado_forms.append(ApoderadoForm(prefix=f"apoderado_{i}", instance=rel.apoderado))
        relacion_forms.append(AlumnoApoderadoForm(prefix=f"relacion_{i}", instance=rel))

    if not apoderado_forms:
        apoderado_forms = [ApoderadoForm(prefix="apoderado_0")]
        relacion_forms = [AlumnoApoderadoForm(prefix="relacion_0")]

    return render(request, "administracion/editar_matricula.html", {
        "page_title": "Editar Matrícula",
        "alumno_form": alumno_form,
        "matricula_form": matricula_form,
        "apoderado_forms": list(zip(apoderado_forms, relacion_forms)),
        "apoderado_count": len(apoderado_forms),
        "matricula": matricula,
    })


@require_POST
@transaction.atomic
def eliminar_alumnos(request):
    form = EliminarAlumnosForm(request.POST)
    if not form.is_valid():
        for error in form.errors.get("alumnos", []):
            messages.error(request, error)
        return redirect("administracion")

    alumnos = list(form.cleaned_data["alumnos"].order_by("nombre", "pk"))
    if request.POST.get("confirmar") == "si":
        Alumno.objects.filter(pk__in=[alumno.pk for alumno in alumnos]).delete()
        messages.success(
            request,
            f"Se eliminaron permanentemente {len(alumnos)} alumno(s) y sus registros asociados.",
        )
        return redirect("administracion")

    return render(request, "administracion/eliminar_alumnos.html", {
        "page_title": "Confirmar eliminación de alumnos",
        "alumnos": alumnos,
    })


# ─────────────────────────── Cursos ──────────────────────────────────────────

def crear_curso(request):
    if request.method == "POST":
        form = CursoForm(request.POST)
        if form.is_valid():
            curso = form.save()
            messages.success(request, f"Curso {curso} creado exitosamente.")
            return redirect("administracion")
    else:
        form = CursoForm()

    return render(request, "administracion/curso_form.html", {
        "page_title": "Nuevo Curso",
        "form": form,
    })


def editar_curso(request, curso_id):
    curso = get_object_or_404(Curso, pk=curso_id)
    if request.method == "POST":
        form = CursoForm(request.POST, instance=curso)
        if form.is_valid():
            form.save()
            messages.success(request, f"Curso {curso} actualizado exitosamente.")
            return redirect("administracion")
    else:
        form = CursoForm(instance=curso)

    return render(request, "administracion/curso_form.html", {
        "page_title": "Editar Curso",
        "form": form,
        "curso": curso,
    })


# ─────────────────────────── Funcionarios ────────────────────────────────────

def crear_funcionario(request):
    if request.method == "POST":
        form = FuncionarioForm(request.POST)
        if form.is_valid():
            funcionario = form.save()
            messages.success(request, f"Funcionario {funcionario.nombre} creado exitosamente.")
            return redirect("administracion")
    else:
        form = FuncionarioForm()

    return render(request, "administracion/funcionario_form.html", {
        "page_title": "Nuevo Funcionario",
        "form": form,
    })


def editar_funcionario(request, funcionario_id):
    funcionario = get_object_or_404(Funcionario, pk=funcionario_id)
    if request.method == "POST":
        form = FuncionarioForm(request.POST, instance=funcionario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Funcionario {funcionario.nombre} actualizado exitosamente.")
            return redirect("administracion")
    else:
        form = FuncionarioForm(instance=funcionario)

    return render(request, "administracion/funcionario_form.html", {
        "page_title": "Editar Funcionario",
        "form": form,
        "funcionario": funcionario,
    })
