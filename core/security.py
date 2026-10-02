"""Seguridad: hash de contraseñas (SHA-256 + salt) y firmas HMAC para los QR."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets

from core.database import get_connection

# PBKDF2-HMAC-SHA256: SHA-256 con salt único por usuario y múltiples iteraciones
# para encarecer ataques de fuerza bruta sobre la base de datos.
PBKDF2_ITERACIONES = 200_000
_secreto_cache: bytes | None = None


def config_valor(nombre: str, default: str | None = None) -> str | None:
    """Lee configuración de variables de entorno o de `st.secrets`."""
    valor = os.environ.get(nombre)
    if valor:
        return valor
    try:
        import streamlit as st

        if nombre in st.secrets:
            return str(st.secrets[nombre])
    except Exception:
        pass
    return default


def generar_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or generar_salt()
    derivada = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERACIONES
    )
    return derivada.hex(), salt


def verificar_password(password: str, hash_hex: str, salt: str) -> bool:
    calculado, _ = hash_password(password, salt)
    return hmac.compare_digest(calculado, hash_hex)


def validar_fortaleza(password: str) -> str | None:
    """Devuelve un mensaje de error o None si la contraseña es aceptable."""
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "La contraseña debe combinar letras y números."
    return None


def obtener_secreto() -> bytes:
    """Clave HMAC: `SIA_SECRET` si está configurada; si no, una generada y persistida en la DB."""
    global _secreto_cache
    if _secreto_cache is not None:
        return _secreto_cache
    configurado = config_valor("SIA_SECRET")
    if configurado:
        _secreto_cache = configurado.encode("utf-8")
        return _secreto_cache
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO config (clave, valor) VALUES ('hmac_secret', ?)",
            (secrets.token_hex(32),),
        )
        valor = conn.execute("SELECT valor FROM config WHERE clave = 'hmac_secret'").fetchone()["valor"]
    _secreto_cache = valor.encode("utf-8")
    return _secreto_cache


def firmar(mensaje: str, largo: int = 16) -> str:
    return hmac.new(obtener_secreto(), mensaje.encode("utf-8"), hashlib.sha256).hexdigest()[:largo]


def verificar_firma(mensaje: str, firma: str, largo: int = 16) -> bool:
    return hmac.compare_digest(firmar(mensaje, largo), firma.lower())
