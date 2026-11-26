"""Capa de persistencia SQLite (librería estándar `sqlite3`).

Cada operación abre una conexión corta mediante `get_connection()`, lo que la hace segura frente a los
múltiples hilos que usa Streamlit para atender sesiones.

Modelo multi-institución (SaaS): cada persona tiene UNA cuenta (DNI único) y roles por institución en
`membresias` (un docente puede trabajar en dos institutos con la misma cuenta).
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SIA_DB_PATH", BASE_DIR / "database.db"))
SCHEMA_VERSION = "4"
ROLES = ("estudiante", "docente", "preceptor", "directivo")

TABLAS = (
    "config", "instituciones", "carreras", "usuarios", "membresias", "docente_carreras", "materias",
    "inscripciones", "clases", "asistencias", "justificativos", "sesiones", "intentos_login",
    "materia_programas", "clase_reportes",
)

# Definiciones de las tablas que cambiaron su CHECK (se reconstruyen en bases existentes).
_USUARIOS = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dni           TEXT NOT NULL UNIQUE,
    nombre        TEXT NOT NULL,
    apellido      TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    rol           TEXT NOT NULL CHECK (rol IN ('docente', 'estudiante', 'preceptor', 'directivo')),
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    legajo        TEXT,
    departamento  TEXT,
    activo        INTEGER NOT NULL DEFAULT 1,
    creado_en     TEXT NOT NULL
)"""

_ASISTENCIAS = """
CREATE TABLE IF NOT EXISTS asistencias (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    clase_id       INTEGER NOT NULL REFERENCES clases(id) ON DELETE CASCADE,
    estudiante_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    estado         TEXT NOT NULL DEFAULT 'presente'
                   CHECK (estado IN ('presente', 'tarde', 'justificado')),
    metodo         TEXT NOT NULL
                   CHECK (metodo IN ('qr_credencial', 'qr_clase', 'pin', 'manual', 'preceptoria', 'justificativo')),
    registrado_por INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    registrado_en  TEXT NOT NULL,
    UNIQUE (clase_id, estudiante_id)
)"""

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS instituciones (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slug             TEXT NOT NULL UNIQUE,
    nombre           TEXT NOT NULL,
    nombre_corto     TEXT NOT NULL,
    color_primario   TEXT NOT NULL DEFAULT '#1F4E8C',
    color_secundario TEXT NOT NULL DEFAULT '#6B7A99',
    logo             BLOB,
    logo_mime        TEXT,
    umbral_regular   REAL NOT NULL DEFAULT 75 CHECK (umbral_regular BETWEEN 0 AND 100),
    umbral_promocion REAL NOT NULL DEFAULT 80 CHECK (umbral_promocion BETWEEN 0 AND 100),
    tolerancia_tarde INTEGER NOT NULL DEFAULT 10 CHECK (tolerancia_tarde BETWEEN 0 AND 120),
    codigo_docente   TEXT NOT NULL DEFAULT '',
    activa           INTEGER NOT NULL DEFAULT 1,
    creado_en        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS carreras (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    institucion_id INTEGER NOT NULL REFERENCES instituciones(id) ON DELETE CASCADE,
    nombre         TEXT NOT NULL,
    activa         INTEGER NOT NULL DEFAULT 1,
    UNIQUE (institucion_id, nombre)
);

{_USUARIOS};

CREATE TABLE IF NOT EXISTS membresias (
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    institucion_id INTEGER NOT NULL REFERENCES instituciones(id) ON DELETE CASCADE,
    rol            TEXT NOT NULL CHECK (rol IN ('estudiante', 'docente', 'preceptor', 'directivo')),
    creado_en      TEXT NOT NULL,
    PRIMARY KEY (usuario_id, institucion_id, rol)
);

CREATE TABLE IF NOT EXISTS docente_carreras (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    carrera_id INTEGER NOT NULL REFERENCES carreras(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, carrera_id)
);

CREATE TABLE IF NOT EXISTS materias (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre           TEXT NOT NULL,
    descripcion      TEXT NOT NULL DEFAULT '',
    curso            TEXT NOT NULL DEFAULT '',
    comision         TEXT NOT NULL DEFAULT '',
    turno            TEXT NOT NULL DEFAULT '',
    dias             TEXT NOT NULL DEFAULT '',
    hora_inicio      TEXT NOT NULL DEFAULT '',
    hora_fin         TEXT NOT NULL DEFAULT '',
    dia_horario      TEXT NOT NULL DEFAULT '',
    docente_id       INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    codigo_clase     TEXT NOT NULL UNIQUE,
    umbral           REAL NOT NULL DEFAULT 75 CHECK (umbral BETWEEN 0 AND 100),
    activa           INTEGER NOT NULL DEFAULT 1,
    creado_en        TEXT NOT NULL,
    institucion_id   INTEGER REFERENCES instituciones(id) ON DELETE CASCADE,
    carrera_id       INTEGER REFERENCES carreras(id) ON DELETE SET NULL,
    umbral_promocion REAL NOT NULL DEFAULT 80
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

{_ASISTENCIAS};

-- Justificativos de inasistencia: los carga el alumno (o Preceptoría) y los aprueba Preceptoría o el docente.
CREATE TABLE IF NOT EXISTS justificativos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    institucion_id INTEGER NOT NULL REFERENCES instituciones(id) ON DELETE CASCADE,
    materia_id     INTEGER REFERENCES materias(id) ON DELETE CASCADE,
    fecha_desde    TEXT NOT NULL,
    fecha_hasta    TEXT NOT NULL,
    motivo         TEXT NOT NULL,
    archivo        BLOB,
    archivo_nombre TEXT,
    archivo_mime   TEXT,
    estado         TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
    observacion    TEXT NOT NULL DEFAULT '',
    creado_por     INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    creado_en      TEXT NOT NULL,
    resuelto_por   INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    resuelto_en    TEXT
);

-- Sesiones persistentes: la cookie del navegador guarda el token; acá solo su hash.
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash     TEXT PRIMARY KEY,
    usuario_id     INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    institucion_id INTEGER REFERENCES instituciones(id) ON DELETE CASCADE,
    rol            TEXT NOT NULL,
    creada_en      TEXT NOT NULL,
    expira_en      TEXT NOT NULL,
    ultimo_uso     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intentos_login (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    identificador TEXT NOT NULL,
    exito         INTEGER NOT NULL,
    momento       TEXT NOT NULL
);

-- Programa de la materia (PDF opcional). Tabla aparte para no cargar el archivo al listar materias.
CREATE TABLE IF NOT EXISTS materia_programas (
    materia_id INTEGER PRIMARY KEY REFERENCES materias(id) ON DELETE CASCADE,
    nombre     TEXT NOT NULL,
    contenido  BLOB NOT NULL,
    subido_en  TEXT NOT NULL
);

-- Reporte PDF generado al cerrar cada clase (para Preceptoría).
CREATE TABLE IF NOT EXISTS clase_reportes (
    clase_id    INTEGER PRIMARY KEY REFERENCES clases(id) ON DELETE CASCADE,
    pdf         BLOB NOT NULL,
    generado_en TEXT NOT NULL
);
"""

# Índices: se crean después de las migraciones (algunos usan columnas que agregan las migraciones).
INDICES = """
CREATE INDEX IF NOT EXISTS idx_asist_estudiante ON asistencias(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_clases_materia   ON clases(materia_id, fecha);
CREATE INDEX IF NOT EXISTS idx_insc_estudiante  ON inscripciones(estudiante_id);
CREATE INDEX IF NOT EXISTS idx_login            ON intentos_login(identificador, momento);
CREATE INDEX IF NOT EXISTS idx_materias_inst    ON materias(institucion_id, activa);
CREATE INDEX IF NOT EXISTS idx_membresias_inst  ON membresias(institucion_id, rol);
CREATE INDEX IF NOT EXISTS idx_justif_inst      ON justificativos(institucion_id, estado);
CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario_id);
"""

# Columnas agregadas en versiones posteriores: se crean en bases existentes sin perder datos.
_MIGRACIONES = {
    "materias": {
        "curso": "TEXT NOT NULL DEFAULT ''",
        "comision": "TEXT NOT NULL DEFAULT ''",
        "turno": "TEXT NOT NULL DEFAULT ''",
        "dias": "TEXT NOT NULL DEFAULT ''",
        "hora_inicio": "TEXT NOT NULL DEFAULT ''",
        "hora_fin": "TEXT NOT NULL DEFAULT ''",
        "dia_horario": "TEXT NOT NULL DEFAULT ''",
        "institucion_id": "INTEGER REFERENCES instituciones(id) ON DELETE CASCADE",
        "carrera_id": "INTEGER REFERENCES carreras(id) ON DELETE SET NULL",
        "umbral_promocion": "REAL NOT NULL DEFAULT 80",
    },
}


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


def _ahora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _reconstruir(conn: sqlite3.Connection, tabla: str, definicion: str) -> None:
    """Cambia el CHECK de una tabla existente sin perder datos (procedimiento recomendado por SQLite)."""
    viejas = [c["name"] for c in conn.execute(f"PRAGMA table_info({tabla})")]
    conn.execute(definicion.replace(f"CREATE TABLE IF NOT EXISTS {tabla}", f"CREATE TABLE {tabla}__nueva"))
    nuevas = {c["name"] for c in conn.execute(f"PRAGMA table_info({tabla}__nueva)")}
    comunes = ", ".join(c for c in viejas if c in nuevas)
    conn.execute(f"INSERT INTO {tabla}__nueva ({comunes}) SELECT {comunes} FROM {tabla}")
    conn.execute(f"DROP TABLE {tabla}")
    conn.execute(f"ALTER TABLE {tabla}__nueva RENAME TO {tabla}")


def _migrar_checks() -> None:
    """Reconstruye usuarios/asistencias si su CHECK es de una versión anterior (requiere FK desactivadas)."""
    conn = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        sql = {f["name"]: f["sql"] or "" for f in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")}
        pendientes = []
        if "usuarios" in sql and "'preceptor'" not in sql["usuarios"]:
            pendientes.append(("usuarios", _USUARIOS))
        if "asistencias" in sql and "'preceptoria'" not in sql["asistencias"]:
            pendientes.append(("asistencias", _ASISTENCIAS))
        if not pendientes:
            return
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        for tabla, definicion in pendientes:
            _reconstruir(conn, tabla, definicion)
        problemas = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            conn.execute("ROLLBACK")
            raise RuntimeError(f"La migración dejaría referencias rotas: {[tuple(p) for p in problemas[:5]]}")
        conn.execute("COMMIT")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def _migrar_columnas(conn: sqlite3.Connection) -> None:
    for tabla, columnas in _MIGRACIONES.items():
        existentes = {f["name"] for f in conn.execute(f"PRAGMA table_info({tabla})")}
        for columna, definicion in columnas.items():
            if columna not in existentes:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def _institucion_inicial(conn: sqlite3.Connection) -> None:
    """Primera institución: la base de una instalación de una sola institución pasa a ser su primer cliente."""
    if conn.execute("SELECT 1 FROM instituciones LIMIT 1").fetchone() is None:
        logo = BASE_DIR / "assets" / "logo_ies11.png"
        conn.execute(
            """INSERT INTO instituciones (slug, nombre, nombre_corto, color_primario, color_secundario, logo, logo_mime,
                                          creado_en) VALUES ('ies11', 'Instituto de Educación Superior N° 11',
                                          'IES N° 11', '#346FB0', '#7979B1', ?, ?, ?)""",
            (logo.read_bytes() if logo.exists() else None, "image/png" if logo.exists() else None, _ahora()),
        )
    inicial = conn.execute("SELECT id FROM instituciones ORDER BY id LIMIT 1").fetchone()["id"]
    conn.execute("UPDATE materias SET institucion_id = ? WHERE institucion_id IS NULL", (inicial,))
    # Usuarios de la versión de una sola institución: su rol pasa a ser una membresía en la institución inicial.
    conn.execute(
        """INSERT OR IGNORE INTO membresias (usuario_id, institucion_id, rol, creado_en)
           SELECT u.id, ?, u.rol, u.creado_en FROM usuarios u
           WHERE NOT EXISTS (SELECT 1 FROM membresias m WHERE m.usuario_id = u.id)""",
        (inicial,),
    )


def init_db() -> None:
    """Crea las tablas, aplica migraciones e índices (idempotente)."""
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
    _migrar_checks()
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        _migrar_columnas(conn)
        conn.executescript(INDICES)
        _institucion_inicial(conn)
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


def guardar_config(clave: str, valor: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO config (clave, valor) VALUES (?, ?)
               ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor""",
            (clave, valor),
        )
