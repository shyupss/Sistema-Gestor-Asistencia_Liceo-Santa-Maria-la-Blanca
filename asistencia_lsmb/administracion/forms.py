from django import forms
from django.utils import timezone

from academico.models import (
    Alumno,
    Apoderado,
    AlumnoApoderado,
    Matricula,
    Curso,
    PeriodoAcademico,
)
from alertas.models import Funcionario, Cargo

# Clases CSS reutilizables
INPUT_CLASS = (
    "w-full rounded-lg border border-gris-iconos py-2.5 px-3 text-sm "
    "text-negro-texto placeholder:text-gris-iconos focus:border-azul "
    "focus:outline-none focus:ring-1 focus:ring-azul"
)
SELECT_CLASS = (
    "w-full rounded-lg border border-gris-iconos py-2.5 px-3 text-sm "
    "text-negro-texto focus:border-azul focus:outline-none focus:ring-1 "
    "focus:ring-azul bg-white"
)
CHECKBOX_CLASS = "h-4 w-4 rounded border-gris-iconos text-azul focus:ring-azul"


class CargoForm(forms.ModelForm):
    class Meta:
        model = Cargo
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ej: Profesor, Inspector, Directivo"}),
        }
        labels = {
            "nombre": "Nombre del cargo",
        }


class PeriodoForm(forms.ModelForm):
    class Meta:
        model = PeriodoAcademico
        fields = ["anio", "fecha_inicio", "fecha_fin"]
        widgets = {
            "anio": forms.NumberInput(attrs={"class": INPUT_CLASS, "placeholder": "Ej: 2026"}),
            "fecha_inicio": forms.DateInput(attrs={"class": INPUT_CLASS + " datepicker", "placeholder": "dd/mm/aaaa"}),
            "fecha_fin": forms.DateInput(attrs={"class": INPUT_CLASS + " datepicker", "placeholder": "dd/mm/aaaa"}),
        }
        labels = {
            "anio": "Año académico",
            "fecha_inicio": "Fecha inicio",
            "fecha_fin": "Fecha término",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            anio_actual = timezone.now().year
            self.fields["anio"].initial = anio_actual
            self.fields["fecha_inicio"].initial = f"{anio_actual}-03-01"
            self.fields["fecha_fin"].initial = f"{anio_actual}-12-31"


class AlumnoForm(forms.ModelForm):
    class Meta:
        model = Alumno
        fields = ["rut", "nombre", "telefono", "email"]
        widgets = {
            "rut": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "12.345.678-9"}),
            "nombre": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nombre completo"}),
            "telefono": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "+56 9 1234 5678"}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "placeholder": "correo@ejemplo.cl"}),
        }
        labels = {
            "rut": "RUT",
            "nombre": "Nombre completo",
            "telefono": "Teléfono",
            "email": "Correo electrónico",
        }


class ApoderadoForm(forms.ModelForm):
    class Meta:
        model = Apoderado
        fields = ["rut", "nombre", "telefono", "email"]
        widgets = {
            "rut": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "12.345.678-9"}),
            "nombre": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nombre completo"}),
            "telefono": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "+56 9 1234 5678"}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "placeholder": "correo@ejemplo.cl"}),
        }
        labels = {
            "rut": "RUT",
            "nombre": "Nombre completo",
            "telefono": "Teléfono",
            "email": "Correo electrónico",
        }


class AlumnoApoderadoForm(forms.ModelForm):
    class Meta:
        model = AlumnoApoderado
        fields = ["tipo_relacion", "recibe_notificaciones"]
        widgets = {
            "tipo_relacion": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "Ej: Padre, Madre, Tutor"}
            ),
            "recibe_notificaciones": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
        }
        labels = {
            "tipo_relacion": "Relación con el alumno",
            "recibe_notificaciones": "Recibe notificaciones",
        }


class MatriculaForm(forms.ModelForm):
    class Meta:
        model = Matricula
        fields = ["curso", "periodo", "fecha_matricula"]
        widgets = {
            "curso": forms.Select(attrs={"class": SELECT_CLASS}),
            "periodo": forms.Select(attrs={"class": SELECT_CLASS}),
            "fecha_matricula": forms.DateInput(
                attrs={"class": INPUT_CLASS + " datepicker", "placeholder": "dd/mm/aaaa"},
                format="%Y-%m-%d",
            ),
        }
        labels = {
            "curso": "Curso",
            "periodo": "Periodo académico",
            "fecha_matricula": "Fecha de matrícula",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anio_actual = timezone.now().year
        # Asegurar que el periodo actual exista o preseleccionarlo
        periodo_actual, _ = PeriodoAcademico.objects.get_or_create(
            anio=anio_actual,
            defaults={
                "fecha_inicio": f"{anio_actual}-03-01",
                "fecha_fin": f"{anio_actual}-12-31",
            },
        )
        if not self.instance.pk:
            self.fields["periodo"].initial = periodo_actual.pk
            self.fields["fecha_matricula"].initial = timezone.now().date()


NIVEL_CHOICES = [
    (1, "I Medio"),
    (2, "II Medio"),
    (3, "III Medio"),
    (4, "IV Medio"),
]


class CursoForm(forms.ModelForm):
    nivel = forms.ChoiceField(
        choices=NIVEL_CHOICES,
        widget=forms.Select(attrs={"class": SELECT_CLASS}),
        label="Nivel",
    )

    class Meta:
        model = Curso
        fields = ["periodo", "nivel", "grupo", "profesor_jefe"]
        widgets = {
            "periodo": forms.Select(attrs={"class": SELECT_CLASS}),
            "grupo": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Ej: A, B, C"}),
            "profesor_jefe": forms.Select(attrs={"class": SELECT_CLASS}),
        }
        labels = {
            "periodo": "Periodo académico",
            "grupo": "Grupo",
            "profesor_jefe": "Profesor jefe",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        anio_actual = timezone.now().year
        periodo_actual, _ = PeriodoAcademico.objects.get_or_create(
            anio=anio_actual,
            defaults={
                "fecha_inicio": f"{anio_actual}-03-01",
                "fecha_fin": f"{anio_actual}-12-31",
            },
        )
        if not self.instance.pk:
            self.fields["periodo"].initial = periodo_actual.pk

        # Mostrar funcionarios que sean Profesores (si existen) o todos los funcionarios si no hay filtro estricto
        try:
            cargo_profesor = Cargo.objects.get(nombre__iexact="Profesor")
            self.fields["profesor_jefe"].queryset = Funcionario.objects.filter(
                cargo=cargo_profesor, activo=True
            ).order_by("nombre")
        except Cargo.DoesNotExist:
            self.fields["profesor_jefe"].queryset = Funcionario.objects.filter(activo=True).order_by("nombre")
            
        self.fields["profesor_jefe"].required = False
        self.fields["profesor_jefe"].empty_label = "— Sin asignar —"


class FuncionarioForm(forms.ModelForm):
    class Meta:
        model = Funcionario
        fields = ["cargo", "rut", "nombre", "email", "activo"]
        widgets = {
            "cargo": forms.Select(attrs={"class": SELECT_CLASS}),
            "rut": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "12.345.678-9"}),
            "nombre": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Nombre completo"}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS, "placeholder": "correo@liceo.cl"}),
            "activo": forms.CheckboxInput(attrs={"class": CHECKBOX_CLASS}),
        }
        labels = {
            "cargo": "Cargo",
            "rut": "RUT",
            "nombre": "Nombre completo",
            "email": "Correo electrónico",
            "activo": "Funcionario activo",
        }


class EliminarAlumnosForm(forms.Form):
    alumnos = forms.ModelMultipleChoiceField(
        queryset=Alumno.objects.filter(
            matriculas__fecha_termino__isnull=True,
            matriculas__isnull=False,
        ).distinct(),
        error_messages={
            "required": "Selecciona al menos un alumno para eliminar.",
            "invalid_choice": "La selección cambió o contiene alumnos sin matrícula vigente. Actualiza el listado.",
            "invalid_pk_value": "La selección de alumnos no es válida.",
        },
    )
