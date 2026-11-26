"""Justificativos de inasistencia: carga (alumno o Preceptoría) y aprobación (Preceptoría o docente).

Al aprobarse, todas las clases del rango de fechas (de una materia o de todas las del alumno en la
institución) quedan registradas como «justificado». Si el alumno ya tenía presente o tarde, se respeta.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd

from core.database import get_connection
from core.tiempo import ahora_iso, hoy
from core.validaciones import limpiar

MAX_ARCHIVO = 5 * 1024 * 1024
MIME_PERMITIDOS = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


def _validar(fecha_desde: date, fecha_hasta: date, motivo: str) -> list[str]:
    errores = []
    if fecha_hasta < fecha_desde:
        errores.append("La fecha «hasta» no puede ser anterior a «desde».")
    if fecha_desde > hoy():
        errores.append("No se pueden justificar fechas futuras.")
    if (fecha_hasta - fecha_desde).days > 60:
        errores.append("El período no puede superar 60 días; cargá varios justificativos.")
    if len(limpiar(motivo)) < 5:
        errores.append("Contá brevemente el motivo (al menos 5 caracteres).")
    return errores


def crear(estudiante_id: int, institucion_id: int, materia_id: int | None, fecha_desde: date, fecha_hasta: date,
          motivo: str, creado_por: int, archivo: tuple[str, bytes, str] | None = None) -> int:
    errores = _validar(fecha_desde, fecha_hasta, motivo)
    if archivo:
        nombre, contenido, mime = archivo
        if mime not in MIME_PERMITIDOS:
            errores.append("El comprobante debe ser PDF o imagen (PNG, JPG, WEBP).")
        if len(contenido) > MAX_ARCHIVO:
            errores.append("El comprobante no puede superar 5 MB.")
    if errores:
        raise ValueError("\n".join(errores))
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO justificativos (estudiante_id, institucion_id, materia_id, fecha_desde, fecha_hasta, motivo,
                   archivo, archivo_nombre, archivo_mime, creado_por, creado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (estudiante_id, institucion_id, materia_id, fecha_desde.isoformat(), fecha_hasta.isoformat(),
             limpiar(motivo, 400), sqlite3.Binary(archivo[1]) if archivo else None,
             limpiar(archivo[0], 150) if archivo else None, archivo[2] if archivo else None, creado_por, ahora_iso()),
        )
    return cur.lastrowid


def _aplicar(conn: sqlite3.Connection, fila: sqlite3.Row, resuelto_por: int) -> int:
    """Marca como justificadas las clases del período; no pisa presentes ni tardes."""
    filtro_materia = "AND c.materia_id = ?" if fila["materia_id"] else ""
    parametros = [fila["estudiante_id"], fila["institucion_id"], fila["fecha_desde"], fila["fecha_hasta"]]
    if fila["materia_id"]:
        parametros.append(fila["materia_id"])
    clases = conn.execute(
        f"""SELECT c.id FROM clases c
            JOIN inscripciones i ON i.materia_id = c.materia_id AND i.estudiante_id = ?
            JOIN materias m ON m.id = c.materia_id AND m.institucion_id = ?
            WHERE c.fecha BETWEEN ? AND ? {filtro_materia}""",
        parametros,
    ).fetchall()
    afectadas = 0
    for clase in clases:
        cur = conn.execute(
            """INSERT INTO asistencias (clase_id, estudiante_id, estado, metodo, registrado_por, registrado_en)
               VALUES (?, ?, 'justificado', 'justificativo', ?, ?)
               ON CONFLICT (clase_id, estudiante_id) DO NOTHING""",
            (clase["id"], fila["estudiante_id"], resuelto_por, ahora_iso()),
        )
        afectadas += cur.rowcount
    return afectadas


def resolver(justificativo_id: int, aprobar: bool, resuelto_por: int, observacion: str = "") -> int:
    """Aprueba o rechaza; devuelve cuántas clases quedaron justificadas."""
    with get_connection() as conn:
        fila = conn.execute("SELECT * FROM justificativos WHERE id = ?", (justificativo_id,)).fetchone()
        if fila is None or fila["estado"] != "pendiente":
            return 0
        conn.execute(
            """UPDATE justificativos SET estado = ?, observacion = ?, resuelto_por = ?, resuelto_en = ?
               WHERE id = ?""",
            ("aprobado" if aprobar else "rechazado", limpiar(observacion, 300), resuelto_por, ahora_iso(),
             justificativo_id),
        )
        return _aplicar(conn, fila, resuelto_por) if aprobar else 0


def justificar_masivo(institucion_id: int, estudiante_ids: list[int], materia_id: int | None, fecha_desde: date,
                      fecha_hasta: date, motivo: str, resuelto_por: int) -> tuple[int, int]:
    """Preceptoría: crea y aprueba en un paso un justificativo por alumno. Devuelve (alumnos, clases)."""
    if not estudiante_ids:
        raise ValueError("Elegí al menos un alumno.")
    clases = 0
    for estudiante_id in estudiante_ids:
        nuevo = crear(estudiante_id, institucion_id, materia_id, fecha_desde, fecha_hasta, motivo, resuelto_por)
        clases += resolver(nuevo, True, resuelto_por, "Justificación masiva de Preceptoría")
    return len(estudiante_ids), clases


def listar(institucion_id: int, estado: str | None = None, estudiante_id: int | None = None,
           docente_id: int | None = None) -> pd.DataFrame:
    """Justificativos de la institución (o de un alumno, o los que involucran materias de un docente)."""
    condiciones, parametros = ["j.institucion_id = ?"], [institucion_id]
    if estado:
        condiciones.append("j.estado = ?")
        parametros.append(estado)
    if estudiante_id:
        condiciones.append("j.estudiante_id = ?")
        parametros.append(estudiante_id)
    if docente_id:
        condiciones.append("""(j.materia_id IN (SELECT id FROM materias WHERE docente_id = ?)
                               OR (j.materia_id IS NULL AND j.estudiante_id IN (
                                   SELECT i.estudiante_id FROM inscripciones i JOIN materias m ON m.id = i.materia_id
                                   WHERE m.docente_id = ?)))""")
        parametros += [docente_id, docente_id]
    with get_connection() as conn:
        filas = conn.execute(
            f"""SELECT j.id, j.estudiante_id, u.apellido || ', ' || u.nombre AS alumno, u.dni,
                       COALESCE(m.nombre, 'Todas sus materias') AS materia, j.materia_id, j.fecha_desde, j.fecha_hasta,
                       j.motivo, j.estado, j.observacion, j.archivo_nombre, j.creado_en, j.resuelto_en,
                       (j.archivo IS NOT NULL) AS tiene_archivo
                FROM justificativos j JOIN usuarios u ON u.id = j.estudiante_id
                LEFT JOIN materias m ON m.id = j.materia_id
                WHERE {' AND '.join(condiciones)} ORDER BY j.creado_en DESC""",
            parametros,
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas], columns=[
        "id", "estudiante_id", "alumno", "dni", "materia", "materia_id", "fecha_desde", "fecha_hasta", "motivo",
        "estado", "observacion", "archivo_nombre", "creado_en", "resuelto_en", "tiene_archivo"])


def archivo(justificativo_id: int) -> tuple[str, bytes, str] | None:
    with get_connection() as conn:
        fila = conn.execute("SELECT archivo_nombre, archivo, archivo_mime FROM justificativos WHERE id = ?",
                            (justificativo_id,)).fetchone()
    return (fila["archivo_nombre"], bytes(fila["archivo"]), fila["archivo_mime"]) if fila and fila["archivo"] else None
