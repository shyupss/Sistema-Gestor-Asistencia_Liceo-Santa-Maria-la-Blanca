import re
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

class PeriodoAcademico(models.Model):
    anio = models.SmallIntegerField(unique=True, verbose_name="Año")
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    def __str__(self):
        return str(self.anio)

    class Meta:
        verbose_name_plural = "Periodos Académicos"


class Curso(models.Model):
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE, related_name='cursos')
    # Usamos string 'cuentas.Funcionario' por si el modelo está en otra app. (a futuro probablemente)
    # Usamos SET_NULL para que el curso no se borre si el profesor no existe/es despedido.
    '''
    profesor_jefe = models.ForeignKey(
        'cuentas.Funcionario', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )'''
    # Temporal mientras no hay app que maneje profesores/cuentas
    profesor_jefe = models.CharField(max_length=100)

    nivel = models.IntegerField()
    grupo = models.CharField(max_length=3)
    
    def __str__(self):
        return f"{self.nivel} {self.grupo} ({self.periodo.anio})"
    
    @property
    def nivel_romano(self):
        mapa_romanos = {
            1: 'I', 2: 'II', 3: 'III', 4: 'IV'
        }
        # Busca el número en el mapa. Si no lo encuentra, devuelve el número normal.
        return mapa_romanos.get(self.nivel, self.nivel)


class Apoderado(models.Model):
    rut = models.CharField(max_length=15, unique=True)
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} - {self.rut}"

def normalizar_rut(rut):
    # Elimina puntos y guiones, y convierte a mayúsculas
    if not rut:
        return ""
    rut_limpio = re.sub(r'[^0-9kK]', '', str((rut)).upper())
    if len(rut_limpio) > 1:
        return f"{rut_limpio[:-1]}-{rut_limpio[-1]}"
    return rut_limpio


class Alumno(models.Model):
    rut = models.CharField(max_length=15, unique=True)
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=100, null=True, blank=True)
    
    # Declaramos la relación N:M pasando por nuestra tabla intermedia
    apoderados = models.ManyToManyField(Apoderado, through='AlumnoApoderado')

    def clean(self):
        super().clean()
        # Normaliza el RUT antes de guardarlo
        self.rut = normalizar_rut(self.rut)

        # Verifica duplicidad
        queryset = Alumno.objects.filter(rut=self.rut)
        if self.pk:
            query = queryset.exclude(pk=self.pk)

        if query.exists():
            raise ValidationError({'rut': 'El RUT ya está registrado para otro alumno.'})

    def save(self, *args, **kwargs):
        self.full_clean()  # Llama a clean() antes de guardar
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} - {self.rut}"


class AlumnoApoderado(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE)
    apoderado = models.ForeignKey(Apoderado, on_delete=models.CASCADE)
    tipo_relacion = models.CharField(max_length=30) # padre, madre, tutor, etc.
    recibe_notificaciones = models.BooleanField(default=False)

    class Meta:
        # Esto reemplaza tu llave primaria compuesta
        unique_together = ('alumno', 'apoderado')
        verbose_name_plural = "Relaciones Alumno-Apoderado"

    def __str__(self):
        return f"{self.apoderado.nombre} ({self.tipo_relacion}) de {self.alumno.nombre}"


class EstadoMatricula(models.Model):
    nombre = models.CharField(max_length=30, unique=True) # activo, retirado, egresado
    descripcion = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.nombre


class Matricula(models.Model):
    alumno = models.ForeignKey(Alumno, on_delete=models.CASCADE, related_name='matriculas')
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE, related_name='matriculas')
    periodo = models.ForeignKey(PeriodoAcademico, on_delete=models.CASCADE)
    # Si se intenta borrar un estado ("activo"), PROTECT lo impedirá si hay alumnos usándolo
    estado_matricula = models.ForeignKey(EstadoMatricula, on_delete=models.PROTECT) 
    
    fecha_matricula = models.DateField()
    fecha_termino = models.DateField(null=True, blank=True)

    class Meta:
        # Aquí está la magia de tu índice único parcial
        constraints = [
            models.UniqueConstraint(
                fields=['alumno', 'periodo'],
                condition=Q(fecha_termino__isnull=True),
                name='uq_matricula_alumno_periodo_vigente'
            )
        ]

    def __str__(self):
        return f"Matrícula: {self.alumno.nombre} - {self.curso}"