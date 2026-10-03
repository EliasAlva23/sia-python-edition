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


def errores_materia(nombre: str, curso: str, turno: str | None, dia_horario: str) -> list[str]:
    errores = requeridos({
        "Nombre de la materia": nombre,
        "Curso / Comisión": curso,
        "Turno": turno,
        "Día y horario": dia_horario,
    })
    errores += largo_maximo({
        "Nombre de la materia": (nombre, 120),
        "Curso / Comisión": (curso, 80),
        "Día y horario": (dia_horario, 120),
    })
    if turno and turno not in TURNOS:
        errores.append("El turno debe ser Mañana, Tarde o Noche.")
    return errores
