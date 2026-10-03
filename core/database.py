"""Capa de persistencia SQLite (librería estándar `sqlite3`).

Cada operación abre una conexión corta mediante `get_connection()`, lo que la
hace segura frente a los múltiples hilos que usa Streamlit para atender sesiones.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SIA_DB_PATH", BASE_DIR / "database.db"))
SCHEMA_VERSION = "2"

TABLAS = (
    "config",
    "usuarios",
    "materias",
    "inscripciones",
    "clases",
    "asistencias",
    "intentos_login",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dni           TEXT NOT NULL UNIQUE,
    nombre        TEXT NOT NULL,
    apellido      TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    rol           TEXT NOT NULL CHECK (rol IN ('docente', 'estudiante')),
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    legajo        TEXT,
    departamento  TEXT,
    activo        INTEGER NOT NULL DEFAULT 1,
    creado_en     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materias (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT NOT NULL,
    descripcion  TEXT NOT NULL DEFAULT '',
    curso        TEXT NOT NULL DEFAULT '',
    turno        TEXT NOT NULL DEFAULT '',
    dia_horario  TEXT NOT NULL DEFAULT '',
    docente_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    codigo_clase TEXT NOT NULL UNIQUE,
    umbral       REAL NOT NULL DEFAULT 75 CHECK (umbral BETWEEN 0 AND 100),
    activa       INTEGER NOT NULL DEFAULT 1,
    creado_en    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inscripciones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    materia_id    INTEGER NOT NULL REFERENCES materias(id) ON DELETE CASCADE,
    estudiante_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    inscripto_en  TEXT NOT NULL,
    resultado     TEXT CHECK (resultado IN ('aprobado', 'reprobado', 'abandono')),
    UNIQUE (materia_id, estudiante_id)
);

CREATE TABLE IF NOT EXISTS clases (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    materia_id INTEGER NOT NULL REFERENCES materias(id) ON DELETE CASCADE,
    fecha      TEXT NOT NULL,
    tema       TEXT NOT NULL DEFAULT '',
    abierta    INTEGER NOT NULL DEFAULT 1,
    creado_en  TEXT NOT NULL,
    UNIQUE (materia_id, fecha)
);

CREATE TABLE IF NOT EXISTS asistencias (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    clase_id       INTEGER NOT NULL REFERENCES clases(id) ON DELETE CASCADE,
    estudiante_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    estado         TEXT NOT NULL DEFAULT 'presente'
                   CHECK (estado IN ('presente', 'tarde', 'justificado')),
    metodo         TEXT NOT NULL
                   CHECK (metodo IN ('qr_credencial', 'qr_clase', 'pin', 'manual')),
    registrado_por INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    registrado_en  TEXT NOT NULL,
    UNIQUE (clase_id, estudiante_id)
);

CREATE TABLE IF NOT EXISTS intentos_login (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    identificador TEXT NOT NULL,
    exito         INTEGER NOT NULL,
    momento       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_asist_estudiante ON asistencias(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_clases_materia   ON clases(materia_id, fecha);
CREATE INDEX IF NOT EXISTS idx_insc_estudiante  ON inscripciones(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_login            ON intentos_login(identificador, momento);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Conexión transaccional: commit al salir, rollback ante excepción."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Columnas agregadas en versiones posteriores: se crean en bases existentes sin perder datos.
_MIGRACIONES = {
    "materias": {
        "curso": "TEXT NOT NULL DEFAULT ''",
        "turno": "TEXT NOT NULL DEFAULT ''",
        "dia_horario": "TEXT NOT NULL DEFAULT ''",
    },
}


def _migrar(conn: sqlite3.Connection) -> None:
    for tabla, columnas in _MIGRACIONES.items():
        existentes = {f["name"] for f in conn.execute(f"PRAGMA table_info({tabla})")}
        for columna, definicion in columnas.items():
            if columna not in existentes:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def init_db() -> None:
    """Crea las tablas e índices si no existen y aplica migraciones (idempotente)."""
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrar(conn)
        conn.execute(
            """INSERT INTO config (clave, valor) VALUES ('schema_version', ?)
               ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor""",
            (SCHEMA_VERSION,),
        )


def tablas_existentes() -> list[str]:
    with get_connection() as conn:
        filas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return sorted(f["name"] for f in filas)


def leer_config(clave: str) -> str | None:
    with get_connection() as conn:
        fila = conn.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else None
