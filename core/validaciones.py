"""Sanitización y validación de formularios.

Todas las funciones devuelven mensajes de error legibles (en lugar de lanzar
excepciones) para poder mostrar juntos todos los problemas de un formulario.
"""
from __future__ import annotations

import re
import unicodedata

from core.security import validar_fortaleza

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
TURNOS = ("Mañana", "Tarde", "Noche")
CURSOS = ("1° Año", "2° Año", "3° Año", "4° Año")
COMISIONES = ("Comisión 1", "Comisión 2", "Comisión 3", "Comisión 4", "Comisión 5", "Comisión 6", "Comisión única")
DIAS_SEMANA = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado")
HORAS = tuple(f"{h:02d}:{m:02d}" for h in range(7, 24) for m in (0, 30))  # 07:00 … 23:30
MAX_PDF_BYTES = 8 * 1024 * 1024


def limpiar(valor: str | None, max_len: int | None = None) -> str:
    """Quita caracteres de control, colapsa espacios y recorta."""
    texto = "".join(c for c in str(valor or "") if unicodedata.category(c)[0] != "C" or c in "\n\t")
    texto = " ".join(texto.split())
    return texto[:max_len] if max_len else texto


def requeridos(campos: dict[str, str | None]) -> list[str]:
    """Campos vacíos o con solo espacios en blanco."""
    return [f"El campo «{nombre}» es obligatorio." for nombre, valor in campos.items() if not limpiar(valor)]


def largo_maximo(campos: dict[str, tuple[str | None, int]]) -> list[str]:
    return [
        f"El campo «{nombre}» admite hasta {maximo} caracteres."
        for nombre, (valor, maximo) in campos.items()
        if len(limpiar(valor)) > maximo
    ]


def error_dni(dni: str | None) -> str | None:
    limpio = re.sub(r"[.\s-]", "", dni or "")
    if not limpio:
        return None  # lo informa `requeridos`
    if not limpio.isdigit():
        return "El DNI debe contener solo números (sin letras ni símbolos)."
    if not 7 <= len(limpio) <= 9:
        return "El DNI debe tener entre 7 y 9 dígitos."
    return None


def error_email(email: str | None) -> str | None:
    email = (email or "").strip()
    if email and not EMAIL_RE.match(email):
        return "El email no tiene un formato válido (ej. nombre@dominio.com)."
    return None


def errores_password(password: str | None, confirmacion: str | None) -> list[str]:
    errores = []
    if password:
        if password != password.strip():
            errores.append("La contraseña no puede empezar ni terminar con espacios.")
        fortaleza = validar_fortaleza(password)
        if fortaleza:
            errores.append(fortaleza)
        if confirmacion is not None and password != confirmacion:
            errores.append("Las contraseñas no coinciden.")
    return errores


def error_nombre(valor: str | None, campo: str) -> str | None:
    valor = limpiar(valor)
    if valor and not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]+", valor):
        return f"El campo «{campo}» solo admite letras, espacios, apóstrofos y guiones."
    return None


def describir_horario(dias: list[str] | tuple[str, ...], hora_inicio: str, hora_fin: str) -> str:
    """Texto legible: «Lunes y Miércoles · 18:00 a 20:00 hs»."""
    dias = [d for d in DIAS_SEMANA if d in dias]  # orden de la semana
    if not dias or not hora_inicio or not hora_fin:
        return ""
    texto_dias = dias[0] if len(dias) == 1 else ", ".join(dias[:-1]) + " y " + dias[-1]
    return f"{texto_dias} · {hora_inicio} a {hora_fin} hs"


def errores_materia(
    nombre: str,
    curso: str | None,
    comision: str | None,
    turno: str | None,
    dias: list[str] | tuple[str, ...] | None,
    hora_inicio: str | None,
    hora_fin: str | None,
) -> list[str]:
    errores = requeridos({
        "Nombre de la materia": nombre,
        "Curso": curso,
        "Comisión": comision,
        "Turno": turno,
        "Hora de inicio": hora_inicio,
        "Hora de fin": hora_fin,
    })
    if not dias:
        errores.append("Elegí al menos un día de cursada.")
    errores += largo_maximo({"Nombre de la materia": (nombre, 120)})
    if curso and curso not in CURSOS:
        errores.append("El curso elegido no es válido.")
    if comision and comision not in COMISIONES:
        errores.append("La comisión elegida no es válida.")
    if turno and turno not in TURNOS:
        errores.append("El turno debe ser Mañana, Tarde o Noche.")
    if dias and any(d not in DIAS_SEMANA for d in dias):
        errores.append("Hay un día de cursada inválido.")
    if hora_inicio and hora_fin:
        if hora_inicio not in HORAS or hora_fin not in HORAS:
            errores.append("El horario elegido no es válido.")
        elif hora_fin <= hora_inicio:
            errores.append("La hora de fin debe ser posterior a la de inicio.")
    return errores


def error_pdf(nombre: str, contenido: bytes) -> str | None:
    """Valida el programa adjunto: PDF real (firma %PDF) y tamaño máximo."""
    if not nombre.lower().endswith(".pdf"):
        return "El programa debe ser un archivo PDF."
    if not contenido.startswith(b"%PDF"):
        return "El archivo no es un PDF válido."
    if len(contenido) > MAX_PDF_BYTES:
        return f"El PDF supera el máximo de {MAX_PDF_BYTES // (1024 * 1024)} MB."
    return None
