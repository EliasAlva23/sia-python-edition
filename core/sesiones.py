"""Sesiones persistentes: sobreviven a recargar la página (F5) o reabrir la app instalada.

Streamlit pierde `st.session_state` al recargar (cada recarga es una conexión nueva). Por eso, al iniciar
sesión se genera un token aleatorio que el navegador guarda en una cookie; en cada recarga la app lee la
cookie (`st.context.cookies`) y restaura la sesión. En la base se guarda solo el hash SHA-256 del token: si
alguien copiara la base, no podría usar las sesiones.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from core.database import get_connection
from core.security import config_valor
from core.tiempo import ahora

NOMBRE_COOKIE = "sia_sesion"
MINUTOS_INACTIVIDAD = int(config_valor("SIA_SESSION_MINUTES", "30") or 30)
HORAS_MAXIMAS = 12


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def crear(usuario_id: int, institucion_id: int | None, rol: str) -> str:
    token = secrets.token_urlsafe(32)
    momento = ahora()
    with get_connection() as conn:
        # Limpieza oportunista de sesiones vencidas.
        conn.execute("DELETE FROM sesiones WHERE expira_en < ?", (momento.isoformat(),))
        conn.execute(
            """INSERT INTO sesiones (token_hash, usuario_id, institucion_id, rol, creada_en, expira_en, ultimo_uso)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_hash(token), usuario_id, institucion_id, rol, momento.isoformat(),
             (momento + timedelta(hours=HORAS_MAXIMAS)).isoformat(), momento.isoformat()),
        )
    return token


def validar(token: str | None) -> dict | None:
    """Datos de la sesión si el token es válido y no venció; renueva la marca de actividad."""
    if not token or len(token) > 200:
        return None
    momento = ahora()
    with get_connection() as conn:
        fila = conn.execute("SELECT * FROM sesiones WHERE token_hash = ?", (_hash(token),)).fetchone()
        if fila is None:
            return None
        inactiva = momento - datetime.fromisoformat(fila["ultimo_uso"]) > timedelta(minutes=MINUTOS_INACTIVIDAD)
        if inactiva or fila["expira_en"] < momento.isoformat():
            conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (fila["token_hash"],))
            return None
        conn.execute("UPDATE sesiones SET ultimo_uso = ? WHERE token_hash = ?", (momento.isoformat(), fila["token_hash"]))
    return dict(fila)


def tocar(token: str | None) -> None:
    if token:
        with get_connection() as conn:
            conn.execute("UPDATE sesiones SET ultimo_uso = ? WHERE token_hash = ?", (ahora().isoformat(), _hash(token)))


def cambiar_contexto(token: str, institucion_id: int | None, rol: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE sesiones SET institucion_id = ?, rol = ? WHERE token_hash = ?",
                     (institucion_id, rol, _hash(token)))


def cerrar(token: str | None) -> None:
    if token:
        with get_connection() as conn:
            conn.execute("DELETE FROM sesiones WHERE token_hash = ?", (_hash(token),))


def cerrar_todas(usuario_id: int, excepto: str | None = None) -> None:
    """Cierra todas las sesiones de la persona (salvo, opcionalmente, la del dispositivo actual)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM sesiones WHERE usuario_id = ? AND token_hash <> ?",
                     (usuario_id, _hash(excepto) if excepto else ""))
