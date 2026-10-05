from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

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

from .forms import (
    AlumnoApoderadoForm,
    AlumnoForm,
    ApoderadoForm,
    CargoForm,
    CursoForm,
    FuncionarioForm,
    MatriculaForm,
    PeriodoForm,
)


# ─────────────────────────── Página principal ────────────────────────────────

def pagina_administracion(request):
    anio_actual = timezone.now().year

    # Garantizar que al menos exista el período del año actual
    PeriodoAcademico.objects.get_or_create(
        anio=anio_actual,
        defaults={
            "fecha_inicio": f"{anio_actual}-03-01",
            "fecha_fin": f"{anio_actual}-12-31",
        },
    )

    matriculas = (
        Matricula.objects.filter(fecha_termino__isnull=True)
        .select_related("alumno", "curso", "curso__periodo", "estado_matricula")
        .order_by("alumno__nombre")
    )
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

    return render(request, "administracion/base.html", {
        "page_title": "Administración",
        "matriculas": matriculas,
        "cursos": cursos,
        "funcionarios": funcionarios,
        "cargos": cargos,
        "periodos": periodos,
    })


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
        i = 0
        while f"apoderado_{i}_rut" in request.POST:
            apoderado_forms.append(ApoderadoForm(request.POST, prefix=f"apoderado_{i}"))
            relacion_forms.append(AlumnoApoderadoForm(request.POST, prefix=f"relacion_{i}"))
            i += 1

        all_valid = alumno_form.is_valid() and matricula_form.is_valid()
        apoderados_valid = all(f.is_valid() for f in apoderado_forms + relacion_forms)

        if all_valid and apoderados_valid:
            try:
                alumno = alumno_form.save()
                estado_activo, _ = EstadoMatricula.objects.get_or_create(nombre="activo")
                matricula = matricula_form.save(commit=False)
                matricula.alumno = alumno
                matricula.estado_matricula = estado_activo
                matricula.save()

                for ap_form, rel_form in zip(apoderado_forms, relacion_forms):
                    apoderado, _ = Apoderado.objects.get_or_create(
                        rut=ap_form.cleaned_data["rut"],
                        defaults={
                            "nombre": ap_form.cleaned_data["nombre"],
                            "telefono": ap_form.cleaned_data.get("telefono"),
                            "email": ap_form.cleaned_data.get("email"),
                        },
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
        i = 0
        while f"apoderado_{i}_rut" in request.POST:
            relacion_inst = list(relaciones_existentes)[i] if i < len(relaciones_existentes) else None
            apoderado_inst = relacion_inst.apoderado if relacion_inst else None
            apoderado_forms.append(
                ApoderadoForm(request.POST, prefix=f"apoderado_{i}", instance=apoderado_inst)
            )
            relacion_forms.append(
                AlumnoApoderadoForm(request.POST, prefix=f"relacion_{i}", instance=relacion_inst)
            )
            i += 1

        all_valid = alumno_form.is_valid() and matricula_form.is_valid()
        apoderados_valid = all(f.is_valid() for f in apoderado_forms + relacion_forms)

        if all_valid and apoderados_valid:
            alumno_form.save()
            matricula_form.save()

            relaciones_existentes.delete()
            for ap_form, rel_form in zip(apoderado_forms, relacion_forms):
                apoderado, _ = Apoderado.objects.get_or_create(
                    rut=ap_form.cleaned_data["rut"],
                    defaults={
                        "nombre": ap_form.cleaned_data["nombre"],
                        "telefono": ap_form.cleaned_data.get("telefono"),
                        "email": ap_form.cleaned_data.get("email"),
                    },
                )
                apoderado.nombre = ap_form.cleaned_data["nombre"]
                apoderado.telefono = ap_form.cleaned_data.get("telefono")
                apoderado.email = ap_form.cleaned_data.get("email")
                apoderado.save()

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
