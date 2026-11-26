"""Registro de asistencia del personal docente, general o por materia."""
from __future__ import annotations

from datetime import date

import pandas as pd

from core.database import get_connection
from core.tiempo import ahora_iso, hoy


def pertenece(conn, institucion_id: int, docente_id: int, materia_id: int | None) -> bool:
    miembro = conn.execute(
        "SELECT 1 FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = 'docente'",
        (docente_id, institucion_id),
    ).fetchone()
    if not miembro or materia_id is None:
        return bool(miembro)
    return conn.execute(
        "SELECT 1 FROM materias WHERE id = ? AND institucion_id = ? AND docente_id = ?",
        (materia_id, institucion_id, docente_id),
    ).fetchone() is not None


def registrar(institucion_id: int, docente_id: int, materia_id: int | None, fecha: date, estado: str,
              preceptor_id: int) -> None:
    if fecha > hoy() or estado not in {"presente", "tarde", "ausente", "justificado"}:
        raise ValueError("Elegí una fecha válida y un estado de asistencia.")
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not pertenece(conn, institucion_id, docente_id, materia_id) or not conn.execute(
            "SELECT 1 FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = 'preceptor'",
            (preceptor_id, institucion_id),
        ).fetchone():
            raise ValueError("El docente o la materia no pertenecen al registro de esta institución.")
        conn.execute(
            """INSERT INTO asistencia_docente
               (institucion_id, docente_id, materia_id, fecha, estado, registrado_por, registrado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT DO UPDATE SET estado = excluded.estado, registrado_por = excluded.registrado_por,
                   registrado_en = excluded.registrado_en""",
            (institucion_id, docente_id, materia_id, fecha.isoformat(), estado, preceptor_id, ahora_iso()),
        )


def historial(institucion_id: int, docente_id: int) -> pd.DataFrame:
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT a.fecha, a.materia_id, COALESCE(m.nombre, 'General') AS materia, a.estado, a.registrado_en
               FROM asistencia_docente a LEFT JOIN materias m ON m.id = a.materia_id
               WHERE a.institucion_id = ? AND a.docente_id = ?
               ORDER BY a.fecha DESC, materia""",
            (institucion_id, docente_id),
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas], columns=["fecha", "materia_id", "materia", "estado", "registrado_en"])


def plantel_historico(institucion_id: int) -> pd.DataFrame:
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT id, dni, apellido, nombre FROM usuarios WHERE id IN (
                   SELECT usuario_id FROM membresias WHERE institucion_id = ? AND rol = 'docente'
                   UNION SELECT docente_id FROM materias WHERE institucion_id = ?
                   UNION SELECT docente_id FROM asistencia_docente WHERE institucion_id = ?
                   UNION SELECT estudiante_id FROM justificativos WHERE institucion_id = ? AND rol = 'docente'
               ) ORDER BY apellido, nombre""",
            (institucion_id,) * 4,
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas], columns=["id", "dni", "apellido", "nombre"])
