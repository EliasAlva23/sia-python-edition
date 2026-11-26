"""Justificativos de inasistencia: carga (alumno o Preceptoría) y aprobación (Preceptoría o docente).

Al aprobarse, todas las clases del rango de fechas (de una materia o de todas las del alumno en la
institución) quedan registradas como «justificado». Si el alumno ya tenía presente o tarde, se respeta.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from core.database import get_connection
from core.tiempo import ahora_iso, hoy
from core.validaciones import limpiar
from models.asistencia_docente import pertenece

MAX_ARCHIVO = 5 * 1024 * 1024
MIME_PERMITIDOS = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


def _validar(fecha_desde: date, fecha_hasta: date, motivo: str) -> list[str]:
    errores = []
    if fecha_hasta < fecha_desde:
        errores.append("La fecha «hasta» no puede ser anterior a «desde».")
    if fecha_hasta > hoy():
        errores.append("No se pueden justificar fechas futuras.")
    if (fecha_hasta - fecha_desde).days > 60:
        errores.append("El período no puede superar 60 días; cargá varios justificativos.")
    if len(limpiar(motivo)) < 5:
        errores.append("Contá brevemente el motivo (al menos 5 caracteres).")
    return errores


def crear(estudiante_id: int, institucion_id: int, materia_id: int | None, fecha_desde: date, fecha_hasta: date,
          motivo: str, creado_por: int, archivo: tuple[str, bytes, str] | None = None, *,
          rol: str = "estudiante") -> int:
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
        conn.execute("BEGIN IMMEDIATE")
        return _crear(conn, estudiante_id, institucion_id, materia_id, fecha_desde, fecha_hasta, motivo, creado_por,
                      archivo, rol)


def _crear(conn, persona_id, institucion_id, materia_id, desde, hasta, motivo, creado_por, archivo, rol) -> int:
    if rol == "docente":
        if not pertenece(conn, institucion_id, persona_id, materia_id):
            raise ValueError("Elegí una materia del docente en esta institución.")
        repetido = conn.execute(
            """SELECT 1 FROM justificativos
               WHERE institucion_id = ? AND estudiante_id = ? AND rol = 'docente'
                 AND fecha_desde <= ? AND fecha_hasta >= ?
                 AND (materia_id IS NULL OR ? IS NULL OR materia_id = ?)""",
            (institucion_id, persona_id, hasta.isoformat(), desde.isoformat(), materia_id, materia_id),
        ).fetchone()
        if repetido:
            raise ValueError("Ya hay un justificativo para ese período y materia.")
    elif rol == "estudiante":
        miembro = conn.execute(
            "SELECT 1 FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = 'estudiante'",
            (persona_id, institucion_id),
        ).fetchone()
        inscripto = materia_id is None or conn.execute(
            """SELECT 1 FROM inscripciones i JOIN materias m ON m.id = i.materia_id
               WHERE i.estudiante_id = ? AND m.id = ? AND m.institucion_id = ?""",
            (persona_id, materia_id, institucion_id),
        ).fetchone()
        if not miembro or not inscripto:
            raise ValueError("Elegí un alumno inscripto en la institución y en la materia indicada.")
    else:
        raise ValueError("Rol de justificativo inválido.")
    cur = conn.execute(
        """INSERT INTO justificativos (estudiante_id, institucion_id, materia_id, fecha_desde, fecha_hasta, motivo,
               archivo, archivo_nombre, archivo_mime, creado_por, creado_en, rol)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (persona_id, institucion_id, materia_id, desde.isoformat(), hasta.isoformat(), limpiar(motivo, 400),
         sqlite3.Binary(archivo[1]) if archivo else None, limpiar(archivo[0], 150) if archivo else None,
         archivo[2] if archivo else None, creado_por, ahora_iso(), rol),
    )
    return cur.lastrowid


def _aplicar(conn: sqlite3.Connection, fila: sqlite3.Row, resuelto_por: int) -> int:
    """Marca como justificadas las clases del período; no pisa presentes ni tardes."""
    if fila["rol"] == "docente":
        desde = date.fromisoformat(fila["fecha_desde"])
        hasta = date.fromisoformat(fila["fecha_hasta"])
        cur = conn.executemany(
            """INSERT INTO asistencia_docente
               (institucion_id, docente_id, materia_id, fecha, estado, registrado_por, registrado_en)
               VALUES (?, ?, ?, ?, 'justificado', ?, ?)
               ON CONFLICT DO UPDATE SET estado = excluded.estado, registrado_por = excluded.registrado_por,
                   registrado_en = excluded.registrado_en WHERE asistencia_docente.estado = 'ausente'""",
            [(fila["institucion_id"], fila["estudiante_id"], fila["materia_id"],
              (desde + timedelta(days=n)).isoformat(), resuelto_por, ahora_iso())
             for n in range((hasta - desde).days + 1)],
        )
        return cur.rowcount
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
               ON CONFLICT (clase_id, estudiante_id) DO UPDATE SET estado = excluded.estado, metodo = excluded.metodo,
                   registrado_por = excluded.registrado_por, registrado_en = excluded.registrado_en
               WHERE asistencias.estado = 'ausente'""",
            (clase["id"], fila["estudiante_id"], resuelto_por, ahora_iso()),
        )
        afectadas += cur.rowcount
    return afectadas


def resolver(justificativo_id: int, aprobar: bool, resuelto_por: int, observacion: str = "", *,
             docente_id: int | None = None) -> int:
    """Aprueba o rechaza; devuelve cuántos registros de asistencia quedaron justificados."""
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        fila = conn.execute("SELECT * FROM justificativos WHERE id = ?", (justificativo_id,)).fetchone()
        if fila is None or fila["estado"] != "pendiente":
            return 0
        roles = {r["rol"] for r in conn.execute(
            "SELECT rol FROM membresias WHERE usuario_id = ? AND institucion_id = ?",
            (resuelto_por, fila["institucion_id"]),
        )}
        if "preceptor" in roles and docente_id is None and (
            fila["rol"] != "docente" or fila["estudiante_id"] != resuelto_por
        ):
            return _resolver(conn, fila, aprobar, resuelto_por, observacion)
        if (fila["rol"] == "estudiante" and fila["materia_id"] and "docente" in roles
                and pertenece(conn, fila["institucion_id"], resuelto_por, fila["materia_id"])):
            return _resolver(conn, fila, aprobar, resuelto_por, observacion)
        raise ValueError("Este justificativo debe resolverlo Preceptoría o el docente a cargo de la materia.")


def _resolver(conn, fila, aprobar, resuelto_por, observacion) -> int:
    conn.execute(
        """UPDATE justificativos SET estado = ?, observacion = ?, resuelto_por = ?, resuelto_en = ?
           WHERE id = ?""",
        ("aprobado" if aprobar else "rechazado", limpiar(observacion, 300), resuelto_por, ahora_iso(), fila["id"]),
    )
    return _aplicar(conn, fila, resuelto_por) if aprobar else 0


def justificar_masivo(institucion_id: int, estudiante_ids: list[int], materia_id: int | None, fecha_desde: date,
                      fecha_hasta: date, motivo: str, resuelto_por: int, *,
                      docente_ids: list[int] | None = None) -> tuple[int, int]:
    """Crea y aprueba de forma transaccional un justificativo por persona y rol."""
    elegidos = [("estudiante", i) for i in dict.fromkeys(estudiante_ids)]
    elegidos += [("docente", i) for i in dict.fromkeys(docente_ids or [])]
    if not elegidos:
        raise ValueError("Elegí al menos un alumno o docente.")
    if resuelto_por in (docente_ids or []):
        raise ValueError("Tu justificativo docente debe revisarlo otro preceptor.")
    if errores := _validar(fecha_desde, fecha_hasta, motivo):
        raise ValueError("\n".join(errores))
    registros = 0
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute(
            "SELECT 1 FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = 'preceptor'",
            (resuelto_por, institucion_id),
        ).fetchone():
            raise ValueError("Solo Preceptoría puede hacer justificaciones masivas.")
        for rol, persona_id in elegidos:
            nuevo = _crear(conn, persona_id, institucion_id, materia_id, fecha_desde, fecha_hasta, motivo,
                           resuelto_por, None, rol)
            fila = conn.execute("SELECT * FROM justificativos WHERE id = ?", (nuevo,)).fetchone()
            registros += _resolver(conn, fila, True, resuelto_por, "Justificación masiva de Preceptoría")
    return len(elegidos), registros


def listar(institucion_id: int, estado: str | None = None, estudiante_id: int | None = None,
           docente_id: int | None = None, *, titular_docente: int | None = None,
           filtro_docente: int | None = None, filtro_alumno: int | None = None) -> pd.DataFrame:
    """Justificativos de la institución (o de un alumno, o los que involucran materias de un docente)."""
    condiciones, parametros = ["j.institucion_id = ?"], [institucion_id]
    if estado:
        condiciones.append("j.estado = ?")
        parametros.append(estado)
    if estudiante_id:
        condiciones.append("j.rol = 'estudiante' AND j.estudiante_id = ?")
        parametros.append(estudiante_id)
    if docente_id:
        condiciones.append("j.rol = 'estudiante' AND m.docente_id = ?")
        parametros.append(docente_id)
    if titular_docente:
        condiciones.append("j.rol = 'docente' AND j.estudiante_id = ?")
        parametros.append(titular_docente)
    if filtro_docente:
        condiciones.append("""((j.rol = 'docente' AND j.estudiante_id = ?)
            OR (j.rol = 'estudiante' AND (m.docente_id = ? OR (j.materia_id IS NULL AND EXISTS (
                SELECT 1 FROM inscripciones i JOIN materias mat ON mat.id = i.materia_id
                WHERE i.estudiante_id = j.estudiante_id AND mat.institucion_id = j.institucion_id
                  AND mat.docente_id = ?)))))""")
        parametros += [filtro_docente] * 3
    if filtro_alumno:
        condiciones.append("j.rol = 'estudiante' AND j.estudiante_id = ?")
        parametros.append(filtro_alumno)
    with get_connection() as conn:
        filas = conn.execute(
            f"""SELECT j.id, j.estudiante_id, j.rol, u.apellido || ', ' || u.nombre AS alumno, u.dni,
                       COALESCE(m.nombre, CASE j.rol WHEN 'docente' THEN 'General' ELSE 'Todas sus materias' END)
                           AS materia, j.materia_id, j.fecha_desde, j.fecha_hasta,
                       j.motivo, j.estado, j.observacion, j.archivo_nombre, j.creado_en, j.resuelto_en,
                       (j.archivo IS NOT NULL) AS tiene_archivo
                FROM justificativos j JOIN usuarios u ON u.id = j.estudiante_id
                LEFT JOIN materias m ON m.id = j.materia_id
                WHERE {' AND '.join(condiciones)} ORDER BY j.creado_en DESC""",
            parametros,
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas], columns=[
        "id", "estudiante_id", "rol", "alumno", "dni", "materia", "materia_id", "fecha_desde", "fecha_hasta", "motivo",
        "estado", "observacion", "archivo_nombre", "creado_en", "resuelto_en", "tiene_archivo"])


def archivo(justificativo_id: int) -> tuple[str, bytes, str] | None:
    with get_connection() as conn:
        fila = conn.execute("SELECT archivo_nombre, archivo, archivo_mime FROM justificativos WHERE id = ?",
                            (justificativo_id,)).fetchone()
    return (fila["archivo_nombre"], bytes(fila["archivo"]), fila["archivo_mime"]) if fila and fila["archivo"] else None
