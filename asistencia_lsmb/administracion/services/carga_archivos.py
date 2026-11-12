import csv
import io
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.core.files.uploadedfile import UploadedFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from academico.models import (
    Alumno,
    AlumnoApoderado,
    Apoderado,
    Curso,
    EstadoMatricula,
    Matricula,
    PeriodoAcademico,
    normalizar_rut,
)
from alertas.models import Funcionario
from asistencia.models import Asistencia_Alumnos, Paso_Lista, Tipos_Asistencia
from asistencia.services.asistencia_service import (
    obtener_justificacion_aplicable,
    recalcular_estado_alumno,
)
from asistencia.services.feriados import FeriadosError, validar_dia_asistencia


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_PREVIEW_ROWS = 8

REQUIRED_HEADERS = {
    "Matrículas": {
        "rut": {"rut", "rut alumno", "run", "run alumno"},
        "nombre": {"nombre", "nombre alumno", "alumno", "nombre completo", "nombre_completo"},
        "curso": {"curso", "curso alumno"},
        "fecha_matricula": {
            "fecha matricula",
            "fecha de matricula",
            "inicio matricula",
            "fecha inicio matricula",
        },
        "apoderado_rut": {"rut apoderado", "run apoderado"},
        "apoderado_nombre": {"apoderado", "nombre apoderado", "nombre_apoderado"},
        "apoderado_telefono": {"telefono apoderado", "telefono_apoderado"},
        "apoderado_email": {"email apoderado", "email_apoderado", "correo apoderado"},
        "tipo_relacion": {"tipo relacion", "tipo_relacion", "relacion"},
    },
    "Asistencia": {
        "rut": {"rut", "rut alumno", "run", "run alumno"},
        "nombre": {"nombre", "nombre alumno", "nombre completo", "nombre_completo"},
    },
}

REQUIRED_MATRICULA_KEYS = {
    "rut",
    "nombre",
    "curso",
    "fecha_matricula",
    "apoderado_rut",
    "apoderado_nombre",
}

REQUIRED_HEADER_LABELS = {
    "Matrículas": [
        "RUT",
        "Nombre",
        "Curso",
        "Fecha matrícula",
        "RUT apoderado",
        "Apoderado",
        "Teléfono apoderado",
        "Email apoderado",
        "Tipo relación",
    ],
    "Asistencia": [
        "RUT",
        "Nombre",
        "Fecha (una columna por cada día)",
    ],
}


class ArchivoCargaError(ValueError):
    """Error de validación que puede mostrarse directamente al administrador."""


def _normalizar_encabezado(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().replace("_", " ").strip().split())


def _leer_filas_csv(uploaded_file):
    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ArchivoCargaError(
            "El CSV no está guardado en UTF-8. Exporta nuevamente el archivo como CSV UTF-8."
        ) from exc

    try:
        rows = list(csv.reader(io.StringIO(content)))
    except csv.Error as exc:
        raise ArchivoCargaError("El CSV tiene un formato inválido.") from exc
    return rows


def _leer_filas_xlsx(uploaded_file):
    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    except (InvalidFileException, OSError, ValueError) as exc:
        raise ArchivoCargaError(
            "El archivo XLSX no se puede leer. Verifica que no esté dañado."
        ) from exc

    try:
        worksheet = workbook.active
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _leer_filas(uploaded_file):
    # Selecciona el lector según la extensión y devuelve todas las filas.
    extension = Path(uploaded_file.name or "").suffix.casefold()
    if extension == ".csv":
        return _leer_filas_csv(uploaded_file)
    if extension == ".xlsx":
        return _leer_filas_xlsx(uploaded_file)
    raise ArchivoCargaError("Solo se aceptan archivos .xlsx o .csv.")


def _valor_fecha(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 0:
        return date(1899, 12, 30) + timedelta(days=int(value))
    text = str(value or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, formato).date()
        except ValueError:
            continue
    return None


def _normalizar_curso(value):
    # Acepta formatos habituales de Excel como "1º A", "1° A" y "I Medio A".
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().strip()
    text = re.sub(r"(?<=\d)[º°O]", "", text)
    text = " ".join(text.split())
    match = re.fullmatch(r"(I{1,3}V?|[1-4])\s*(?:MEDIO)?\s*([A-Z])", text)
    if not match:
        return None
    niveles = {"I": 1, "II": 2, "III": 3, "IV": 4}
    nivel_texto = match.group(1)
    nivel = int(nivel_texto) if nivel_texto.isdigit() else niveles.get(nivel_texto)
    return (nivel, match.group(2)) if nivel else None


def validar_archivo_carga(uploaded_file: UploadedFile, tipo):
    # Valida primero el archivo y sus columnas antes de interpretar los datos.
    if tipo not in REQUIRED_HEADERS:
        raise ArchivoCargaError("Selecciona si el archivo corresponde a Matrículas o Asistencia.")
    if not uploaded_file:
        raise ArchivoCargaError("Selecciona un archivo antes de continuar.")
    if uploaded_file.size > MAX_FILE_SIZE:
        raise ArchivoCargaError("El archivo supera el límite de 10 MB.")

    # Lectura común para XLSX y CSV.
    rows = _leer_filas(uploaded_file)
    if not rows:
        raise ArchivoCargaError("El archivo está vacío.")

    # Los encabezados se normalizan para aceptar mayúsculas, tildes y guiones bajos.
    headers = [_normalizar_encabezado(value) for value in rows[0]]
    if not any(headers):
        raise ArchivoCargaError("No se encontró una fila de encabezados.")

    required_keys = (
        REQUIRED_MATRICULA_KEYS if tipo == "Matrículas"
        else set(REQUIRED_HEADERS[tipo])
    )
    missing = [
        key
        for key in required_keys
        if not any(header in REQUIRED_HEADERS[tipo][key] for header in headers)
    ]
    if missing:
        labels = ", ".join(missing).replace("_", " ")
        raise ArchivoCargaError(
            f"El archivo no parece ser de {tipo.lower()}. Faltan columnas: {labels}."
        )

    # Se ignoran las filas completamente vacías del archivo.
    data_rows = [row for row in rows[1:] if any(value not in (None, "") for value in row)]
    if not data_rows:
        raise ArchivoCargaError("El archivo contiene encabezados, pero no tiene datos.")

    # Este resumen alimenta la vista previa sin guardar información todavía.
    result = {
        "tipo": tipo,
        "nombre": uploaded_file.name,
        "filas": len(data_rows),
        "encabezados": [str(value or "").strip() for value in rows[0]],
        "vista_previa": [
            ["" if value is None else str(value).strip() for value in row]
            for row in data_rows[:MAX_PREVIEW_ROWS]
        ],
        "filas_omitidas": max(0, len(data_rows) - MAX_PREVIEW_ROWS),
    }
    if tipo == "Matrículas":
        # Se relaciona cada nombre lógico con la posición de su columna.
        indices = {
            key: next(index for index, header in enumerate(headers) if header in accepted)
            for key, accepted in REQUIRED_HEADERS[tipo].items()
            if any(header in accepted for header in headers)
        }
        registros = []
        errores = []
        for numero, row in enumerate(data_rows, start=2):
            # Cada fila se valida completa; si falla, se informa su número de Excel.
            get = lambda key: (
                row[indices[key]] if key in indices and indices[key] < len(row) else ""
            )
            fecha = _valor_fecha(get("fecha_matricula"))
            curso = _normalizar_curso(get("curso"))
            rut = normalizar_rut(get("rut"))
            rut_apoderado = normalizar_rut(get("apoderado_rut"))
            fila_errores = []
            if not rut or len(rut) < 3:
                fila_errores.append("RUT del alumno inválido")
            if not str(get("nombre")).strip():
                fila_errores.append("falta el nombre del alumno")
            if not fecha:
                fila_errores.append("fecha de matrícula inválida")
            if not curso:
                fila_errores.append("curso inválido; usa, por ejemplo, 1º A")
            if not rut_apoderado or not str(get("apoderado_nombre")).strip():
                fila_errores.append("faltan los datos del apoderado")
            if fila_errores:
                errores.append({"fila": numero, "detalle": "; ".join(fila_errores)})
                continue
            registros.append({
                "rut": rut,
                "nombre": str(get("nombre")).strip(),
                "fecha_matricula": fecha.isoformat(),
                "nivel": curso[0],
                "grupo": curso[1],
                "apoderado_rut": rut_apoderado,
                "apoderado_nombre": str(get("apoderado_nombre")).strip(),
                "apoderado_telefono": str(get("apoderado_telefono") or "").strip(),
                "apoderado_email": str(get("apoderado_email") or "").strip(),
                "tipo_relacion": str(get("tipo_relacion") or "Apoderado").strip(),
            })
        # Solo los registros sin errores quedan disponibles para confirmar la carga.
        result["registros"] = registros
        result["errores"] = errores
    else:
        result.update(_preparar_asistencia(rows, data_rows, headers))
    return result


def _preparar_asistencia(rows, data_rows, headers):
    indices = {
        key: next(index for index, header in enumerate(headers) if header in accepted)
        for key, accepted in REQUIRED_HEADERS["Asistencia"].items()
    }
    columnas_fecha = []
    errores = []
    fechas_vistas = set()
    for index, value in enumerate(rows[0]):
        if index < 2:
            continue
        fecha = _valor_fecha(value)
        if not fecha:
            if value not in (None, ""):
                errores.append({"fila": 1, "detalle": f"fecha inválida en la columna {index + 1}"})
            continue
        if fecha in fechas_vistas:
            errores.append({"fila": 1, "detalle": f"la fecha {fecha:%d/%m/%Y} está repetida"})
            continue
        fechas_vistas.add(fecha)
        columnas_fecha.append((index, fecha))

    if not columnas_fecha:
        errores.append({"fila": 1, "detalle": "no se encontraron columnas con fechas válidas"})

    vistos = set()
    filas = []
    for numero, row in enumerate(data_rows, start=2):
        rut = normalizar_rut(row[indices["rut"]] if indices["rut"] < len(row) else "")
        if not rut:
            errores.append({"fila": numero, "detalle": "RUT del alumno inválido"})
            continue
        if rut in vistos:
            errores.append({"fila": numero, "detalle": f"el RUT {rut} está repetido"})
            continue
        vistos.add(rut)
        filas.append((numero, rut, row))

    marcas_por_fecha = {
        fecha: any(
            index < len(row) and str(row[index] or "").strip()
            for _, _, row in filas
            for index, fecha_actual in columnas_fecha
            if fecha_actual == fecha
        )
        for _, fecha in columnas_fecha
    }
    if not any(marcas_por_fecha.values()):
        errores.append({"fila": 1, "detalle": "no hay ningún día con marcas P o A"})
    registros = []
    for numero, rut, row in filas:
        for index, fecha in columnas_fecha:
            if not marcas_por_fecha[fecha]:
                continue
            valor = str(row[index] if index < len(row) and row[index] is not None else "").strip().upper()
            if valor and valor not in {"P", "A"}:
                errores.append({
                    "fila": numero,
                    "detalle": f"valor '{valor}' inválido para {fecha:%d/%m/%Y}; usa P o A",
                })
                continue
            if not valor:
                continue
            registros.append({
                "rut": rut,
                "fecha": fecha.isoformat(),
                "estado": valor,
                "fila": numero,
            })

    return {
        "registros": registros,
        "errores": errores,
        "dias_registrados": sum(marcas_por_fecha.values()),
    }


@transaction.atomic
def cargar_matriculas(registros, progress_callback=None):
    # Toda la carga se confirma o revierte completa si ocurre un error.
    estado_vigente, _ = EstadoMatricula.objects.get_or_create(nombre="vigente")
    # Estos contadores se muestran en el reporte final de la importación.
    conteo = {"alumnos_creados": 0, "alumnos_actualizados": 0,
              "apoderados_creados": 0, "apoderados_actualizados": 0,
              "matriculas_creadas": 0, "matriculas_actualizadas": 0,
              "cursos_creados": 0}
    for numero, registro in enumerate(registros, start=1):
        # El período se determina por el año de la fecha de matrícula.
        fecha = date.fromisoformat(registro["fecha_matricula"])
        periodo = PeriodoAcademico.objects.filter(anio=fecha.year).first()
        if not periodo:
            raise ArchivoCargaError(
                f"No existe el período académico {fecha.year}; créalo antes de cargar el archivo."
            )
        # El curso se reutiliza si existe; de lo contrario se crea automáticamente.
        curso, creado = Curso.objects.get_or_create(
            periodo=periodo,
            nivel=registro["nivel"],
            grupo=registro["grupo"],
        )
        conteo["cursos_creados"] += int(creado)
        # El RUT identifica al alumno; sus datos se actualizan en cargas posteriores.
        alumno, creado = Alumno.objects.get_or_create(
            rut=registro["rut"],
            defaults={"nombre": registro["nombre"]},
        )
        if creado:
            conteo["alumnos_creados"] += 1
        else:
            alumno.nombre = registro["nombre"]
            alumno.save(update_fields=["nombre"])
            conteo["alumnos_actualizados"] += 1
        # El RUT también identifica al apoderado y permite reutilizarlo con otros alumnos.
        apoderado, creado = Apoderado.objects.get_or_create(
            rut=registro["apoderado_rut"],
            defaults={
                "nombre": registro["apoderado_nombre"],
                "telefono": registro["apoderado_telefono"],
                "email": registro["apoderado_email"],
            },
        )
        if creado:
            conteo["apoderados_creados"] += 1
        else:
            apoderado.nombre = registro["apoderado_nombre"]
            apoderado.telefono = registro["apoderado_telefono"]
            apoderado.email = registro["apoderado_email"]
            apoderado.save(update_fields=["nombre", "telefono", "email"])
            conteo["apoderados_actualizados"] += 1
        # La relación permite varios apoderados por alumno y un apoderado para varios alumnos.
        AlumnoApoderado.objects.update_or_create(
            alumno=alumno,
            apoderado=apoderado,
            defaults={"tipo_relacion": registro["tipo_relacion"]},
        )
        matricula, creado = Matricula.objects.get_or_create(
            alumno=alumno,
            periodo=periodo,
            fecha_termino__isnull=True,
            defaults={
                "curso": curso,
                "estado_matricula": estado_vigente,
                "fecha_matricula": fecha,
            },
        )
        if creado:
            conteo["matriculas_creadas"] += 1
        else:
            matricula.curso = curso
            matricula.estado_matricula = estado_vigente
            matricula.fecha_matricula = fecha
            matricula.save(update_fields=["curso", "estado_matricula", "fecha_matricula"])
            conteo["matriculas_actualizadas"] += 1
        if progress_callback:
            progress_callback(
                "guardando",
                "Guardando matrículas en la base de datos...",
                numero,
            )
    return conteo


@transaction.atomic
def cargar_asistencia(registros, progress_callback=None):
    tipos = {
        tipo.nombre.casefold(): tipo
        for tipo in Tipos_Asistencia.objects.all()
    }
    tipo_presente = tipos.get("presente")
    tipo_ausente = tipos.get("ausente")
    if not tipo_presente or not tipo_ausente:
        raise ArchivoCargaError(
            "Debes cargar la configuración de asistencia con los tipos Presente y Ausente."
        )

    # La carga aún no tiene autenticación enlazada a Funcionario. Se prefiere
    # un administrador y, mientras tanto, se usa el primer funcionario activo.
    funcionario = (
        Funcionario.objects.filter(activo=True, cargo__nombre__icontains="admin")
        .order_by("id")
        .first()
    )
    if not funcionario:
        funcionario = Funcionario.objects.filter(activo=True).order_by("id").first()
    if not funcionario:
        raise ArchivoCargaError(
            "No existe ningún funcionario activo para registrar la carga. "
            "Crea o activa un funcionario desde Administración."
        )

    alumno_ids = {registro["rut"] for registro in registros}
    alumnos = {
        alumno.rut: alumno
        for alumno in Alumno.objects.filter(rut__in=alumno_ids)
    }
    errores_por_alumno = {}
    errores_por_feriado = {}
    matriculas = {}
    registros_omitidos_sin_matricula = 0
    for numero, registro in enumerate(registros, start=1):
        fecha = date.fromisoformat(registro["fecha"])
        try:
            validar_dia_asistencia(fecha)
        except FeriadosError as exc:
            errores_por_feriado.setdefault(str(exc), set()).add(fecha)
            if progress_callback:
                progress_callback(
                    "validando",
                    "Validando feriados y matrículas...",
                    numero,
                )
            continue
        alumno = alumnos.get(registro["rut"])
        if not alumno:
            errores_por_alumno.setdefault(
                ("no existe", registro["fila"], registro["rut"]), set()
            ).add(fecha)
            if progress_callback:
                progress_callback(
                    "validando",
                    "Validando alumnos y matrículas...",
                    numero,
                )
            continue
        matricula = (
            Matricula.objects.filter(
                alumno=alumno,
                periodo__anio=fecha.year,
                fecha_matricula__lte=fecha,
            )
            .filter(Q(fecha_termino__isnull=True) | Q(fecha_termino__gt=fecha))
            .select_related("curso")
            .first()
        )
        if not matricula:
            matricula_periodo = (
                Matricula.objects.filter(
                    alumno=alumno,
                    periodo__anio=fecha.year,
                )
                .order_by("fecha_matricula")
                .first()
            )
            if matricula_periodo and fecha < matricula_periodo.fecha_matricula:
                registros_omitidos_sin_matricula += 1
            else:
                errores_por_alumno.setdefault(
                    ("sin matrícula", registro["fila"], registro["rut"]), set()
                ).add(fecha)
            if progress_callback:
                progress_callback(
                    "validando",
                    "Validando alumnos y matrículas...",
                    numero,
                )
            continue
        matriculas[(registro["rut"], registro["fecha"])] = matricula
        if progress_callback:
            progress_callback(
                "validando",
                "Validando alumnos y matrículas...",
                numero,
            )
    if errores_por_alumno or errores_por_feriado:
        errores = []
        for mensaje, fechas in errores_por_feriado.items():
            fechas_texto = ", ".join(
                sorted(fecha.strftime("%d/%m/%Y") for fecha in fechas)
            )
            errores.append(f"{mensaje} Fechas: {fechas_texto}.")
        for (tipo, fila, rut), fechas in errores_por_alumno.items():
            fechas_texto = ", ".join(sorted(fecha.strftime("%d/%m/%Y") for fecha in fechas))
            if tipo == "no existe":
                errores.append(
                    f"Fila {fila} · RUT {rut}: el alumno no existe en el sistema."
                )
            else:
                errores.append(
                    f"Fila {fila} · RUT {rut}: no tiene matrícula vigente "
                    f"en las fechas: {fechas_texto}."
                )
        raise ArchivoCargaError("\n".join(errores))

    conteo = {
        "pasos_creados": 0,
        "pasos_actualizados": 0,
        "asistencias_creadas": 0,
        "asistencias_actualizadas": 0,
        "registros_omitidos_sin_matricula": registros_omitidos_sin_matricula,
    }
    agrupados = {}
    for registro in registros:
        clave_matricula = (registro["rut"], registro["fecha"])
        if clave_matricula not in matriculas:
            continue
        fecha = date.fromisoformat(registro["fecha"])
        alumno = alumnos[registro["rut"]]
        matricula = matriculas[clave_matricula]
        agrupados.setdefault((matricula.curso_id, fecha), []).append(
            (alumno, registro["estado"], matricula.curso)
        )

    guardado_actual = 0
    for (curso_id, fecha), filas in agrupados.items():
        curso = filas[0][2]
        paso, creado = Paso_Lista.objects.update_or_create(
            curso_id=curso_id,
            fecha=fecha,
            defaults={"funcionario": funcionario},
        )
        conteo["pasos_creados" if creado else "pasos_actualizados"] += 1
        for alumno, estado, _ in filas:
            asistencia, creada = Asistencia_Alumnos.objects.update_or_create(
                paso_lista=paso,
                alumno=alumno,
                defaults={
                    "tipo_asistencia": tipo_presente if estado == "P" else tipo_ausente,
                    "justificacion": (
                        obtener_justificacion_aplicable(alumno, fecha)
                        if estado == "A"
                        else None
                    ),
                },
            )
            conteo["asistencias_creadas" if creada else "asistencias_actualizadas"] += 1
            recalcular_estado_alumno(alumno=alumno, periodo=curso.periodo)
            if progress_callback:
                guardado_actual += 1
                progress_callback(
                    "guardando",
                    "Guardando asistencias en la base de datos...",
                    guardado_actual,
                )
    return conteo


@transaction.atomic
def limpiar_datos_cargas():
    asistencias = Asistencia_Alumnos.objects.all()
    pasos = Paso_Lista.objects.all()
    matriculas = Matricula.objects.all()
    alumno_ids = list(matriculas.values_list("alumno_id", flat=True).distinct())
    apoderado_ids = list(
        AlumnoApoderado.objects.filter(alumno_id__in=alumno_ids)
        .values_list("apoderado_id", flat=True)
        .distinct()
    )
    curso_ids = list(matriculas.values_list("curso_id", flat=True).distinct())
    alumnos = Alumno.objects.filter(pk__in=alumno_ids)
    apoderados = Apoderado.objects.filter(pk__in=apoderado_ids)
    cursos = Curso.objects.filter(pk__in=curso_ids)

    conteo = {
        "asistencias": asistencias.count(),
        "pasos": pasos.count(),
        "matriculas": matriculas.count(),
        "alumnos": alumnos.count(),
        "apoderados": apoderados.count(),
        "cursos": cursos.count(),
    }
    asistencias.delete()
    pasos.delete()
    matriculas.delete()
    alumnos.delete()
    apoderados.delete()
    cursos.delete()
    return conteo
