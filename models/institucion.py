"""Instituciones (clientes del SaaS), carreras, roles por institución y opciones del sistema."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

import pandas as pd

from core.database import ROLES, get_connection, guardar_config, leer_config
from core.security import config_valor
from core.tiempo import ahora_iso
from core.validaciones import limpiar

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
ROLES_PERSONAL = ("docente", "preceptor", "directivo")
NOMBRES_ROL = {"estudiante": "Estudiante", "docente": "Docente", "preceptor": "Preceptoría",
               "directivo": "Rectoría / Dirección", "superadmin": "Administración general"}


@dataclass
class Institucion:
    id: int
    slug: str
    nombre: str
    nombre_corto: str
    color_primario: str
    color_secundario: str
    umbral_regular: float
    umbral_promocion: float
    tolerancia_tarde: int
    codigo_docente: str
    activa: bool

    # ----- consultas -----
    @staticmethod
    def _desde_fila(f: sqlite3.Row) -> "Institucion":
        return Institucion(f["id"], f["slug"], f["nombre"], f["nombre_corto"], f["color_primario"],
                           f["color_secundario"], f["umbral_regular"], f["umbral_promocion"], f["tolerancia_tarde"],
                           f["codigo_docente"], bool(f["activa"]))

    _CAMPOS = ("id, slug, nombre, nombre_corto, color_primario, color_secundario, umbral_regular, umbral_promocion, "
               "tolerancia_tarde, codigo_docente, activa")

    @classmethod
    def obtener(cls, id: int | None) -> "Institucion | None":
        if id is None:
            return None
        with get_connection() as conn:
            fila = conn.execute(f"SELECT {cls._CAMPOS} FROM instituciones WHERE id = ?", (id,)).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def por_slug(cls, slug: str | None) -> "Institucion | None":
        if not slug:
            return None
        with get_connection() as conn:
            fila = conn.execute(f"SELECT {cls._CAMPOS} FROM instituciones WHERE slug = ? AND activa = 1",
                                (slug.strip().lower(),)).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def todas(cls, solo_activas: bool = True) -> list["Institucion"]:
        with get_connection() as conn:
            filas = conn.execute(
                f"SELECT {cls._CAMPOS} FROM instituciones {'WHERE activa = 1' if solo_activas else ''} ORDER BY nombre"
            ).fetchall()
        return [cls._desde_fila(f) for f in filas]

    def logo(self) -> tuple[bytes, str] | None:
        with get_connection() as conn:
            fila = conn.execute("SELECT logo, logo_mime FROM instituciones WHERE id = ?", (self.id,)).fetchone()
        return (bytes(fila["logo"]), fila["logo_mime"] or "image/png") if fila and fila["logo"] else None

    # ----- alta y edición (Administración general) -----
    @staticmethod
    def validar(datos: dict) -> list[str]:
        errores = []
        if not limpiar(datos.get("nombre")):
            errores.append("El nombre de la institución es obligatorio.")
        if not limpiar(datos.get("nombre_corto")):
            errores.append("El nombre corto es obligatorio (ej. «IS N° 5»).")
        if not _SLUG_RE.match(datos.get("slug", "")):
            errores.append("El identificador del enlace solo admite minúsculas, números y guiones (2 a 31 caracteres).")
        for campo in ("color_primario", "color_secundario"):
            if not _COLOR_RE.match(datos.get(campo, "")):
                errores.append("Los colores deben tener formato #RRGGBB.")
                break
        regular, promocion = float(datos.get("umbral_regular", 75)), float(datos.get("umbral_promocion", 80))
        if not (0 <= regular <= 100 and 0 <= promocion <= 100):
            errores.append("Los umbrales deben estar entre 0 y 100.")
        elif promocion < regular:
            errores.append("El umbral de promoción no puede ser menor que el de regularización.")
        if int(datos.get("tolerancia_tarde", 10)) % 10 != 0:
            errores.append("La tolerancia para «tarde» va en intervalos de 10 minutos.")
        return errores

    @classmethod
    def crear(cls, **datos) -> "Institucion":
        errores = cls.validar(datos)
        if errores:
            raise ValueError("\n".join(errores))
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    """INSERT INTO instituciones (slug, nombre, nombre_corto, color_primario, color_secundario,
                           umbral_regular, umbral_promocion, tolerancia_tarde, codigo_docente, creado_en)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (datos["slug"], limpiar(datos["nombre"], 150), limpiar(datos["nombre_corto"], 40),
                     datos["color_primario"].upper(), datos["color_secundario"].upper(), float(datos["umbral_regular"]),
                     float(datos["umbral_promocion"]), int(datos["tolerancia_tarde"]),
                     (datos.get("codigo_docente") or "").strip(), ahora_iso()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ya existe una institución con ese identificador de enlace.") from exc
        return cls.obtener(cur.lastrowid)

    def actualizar(self, **datos) -> None:
        completos = {**self.__dict__, **datos}
        errores = self.validar(completos)
        if errores:
            raise ValueError("\n".join(errores))
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE instituciones SET slug = ?, nombre = ?, nombre_corto = ?, color_primario = ?,
                           color_secundario = ?, umbral_regular = ?, umbral_promocion = ?, tolerancia_tarde = ?,
                           codigo_docente = ?, activa = ? WHERE id = ?""",
                    (completos["slug"], limpiar(completos["nombre"], 150), limpiar(completos["nombre_corto"], 40),
                     completos["color_primario"].upper(), completos["color_secundario"].upper(),
                     float(completos["umbral_regular"]), float(completos["umbral_promocion"]),
                     int(completos["tolerancia_tarde"]), (completos.get("codigo_docente") or "").strip(),
                     int(bool(completos["activa"])), self.id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ya existe una institución con ese identificador de enlace.") from exc
        self.__dict__.update(Institucion.obtener(self.id).__dict__)

    def guardar_logo(self, contenido: bytes, mime: str) -> None:
        if mime not in ("image/png", "image/jpeg", "image/webp"):
            raise ValueError("El logo debe ser PNG, JPG o WEBP.")
        if len(contenido) > 2 * 1024 * 1024:
            raise ValueError("El logo no puede superar 2 MB.")
        with get_connection() as conn:
            conn.execute("UPDATE instituciones SET logo = ?, logo_mime = ? WHERE id = ?",
                         (sqlite3.Binary(contenido), mime, self.id))

    def aplicar_umbrales_a_materias(self) -> int:
        """Lleva los umbrales institucionales a todas las materias activas."""
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE materias SET umbral = ?, umbral_promocion = ? WHERE institucion_id = ? AND activa = 1",
                (self.umbral_regular, self.umbral_promocion, self.id),
            )
        return cur.rowcount

    # ----- carreras -----
    def carreras(self, solo_activas: bool = True) -> pd.DataFrame:
        with get_connection() as conn:
            filas = conn.execute(
                f"""SELECT c.id, c.nombre, c.activa,
                          (SELECT COUNT(*) FROM docente_carreras dc WHERE dc.carrera_id = c.id) AS docentes,
                          (SELECT COUNT(*) FROM materias m WHERE m.carrera_id = c.id AND m.activa = 1) AS materias
                   FROM carreras c WHERE c.institucion_id = ? {'AND c.activa = 1' if solo_activas else ''}
                   ORDER BY c.nombre""",
                (self.id,),
            ).fetchall()
        return pd.DataFrame([dict(f) for f in filas], columns=["id", "nombre", "activa", "docentes", "materias"])

    def crear_carrera(self, nombre: str) -> None:
        nombre = limpiar(nombre, 120)
        if not nombre:
            raise ValueError("Ingresá el nombre de la carrera.")
        try:
            with get_connection() as conn:
                conn.execute("INSERT INTO carreras (institucion_id, nombre) VALUES (?, ?)", (self.id, nombre))
        except sqlite3.IntegrityError as exc:
            raise ValueError("Esa carrera ya existe en la institución.") from exc

    def editar_carrera(self, carrera_id: int, nombre: str, activa: bool) -> None:
        nombre = limpiar(nombre, 120)
        if not nombre:
            raise ValueError("Ingresá el nombre de la carrera.")
        with get_connection() as conn:
            conn.execute("UPDATE carreras SET nombre = ?, activa = ? WHERE id = ? AND institucion_id = ?",
                         (nombre, int(activa), carrera_id, self.id))

    def carreras_de_docente(self, usuario_id: int) -> list[tuple[int, str]]:
        with get_connection() as conn:
            filas = conn.execute(
                """SELECT c.id, c.nombre FROM carreras c JOIN docente_carreras dc ON dc.carrera_id = c.id
                   WHERE dc.usuario_id = ? AND c.institucion_id = ? AND c.activa = 1 ORDER BY c.nombre""",
                (usuario_id, self.id),
            ).fetchall()
        return [(f["id"], f["nombre"]) for f in filas]

    def asignar_carreras(self, usuario_id: int, carrera_ids: list[int]) -> None:
        """Reemplaza las carreras asignadas a un docente dentro de esta institución."""
        with get_connection() as conn:
            conn.execute(
                """DELETE FROM docente_carreras WHERE usuario_id = ?
                   AND carrera_id IN (SELECT id FROM carreras WHERE institucion_id = ?)""",
                (usuario_id, self.id),
            )
            conn.executemany("INSERT OR IGNORE INTO docente_carreras (usuario_id, carrera_id) VALUES (?, ?)",
                             [(usuario_id, c) for c in carrera_ids])

    # ----- personas y roles -----
    def personas(self, rol: str | None = None) -> pd.DataFrame:
        with get_connection() as conn:
            filas = conn.execute(
                f"""SELECT u.id, u.dni, u.apellido, u.nombre, u.email, m.rol
                    FROM membresias m JOIN usuarios u ON u.id = m.usuario_id
                    WHERE m.institucion_id = ? AND u.activo = 1 {'AND m.rol = ?' if rol else ''}
                    ORDER BY u.apellido, u.nombre""",
                (self.id, rol) if rol else (self.id,),
            ).fetchall()
        return pd.DataFrame([dict(f) for f in filas], columns=["id", "dni", "apellido", "nombre", "email", "rol"])


# ---------------------------------------------------------------- roles por institución
def roles_de(usuario_id: int) -> list[tuple[Institucion, str]]:
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT institucion_id, rol FROM membresias m JOIN instituciones i ON i.id = m.institucion_id
               WHERE m.usuario_id = ? AND i.activa = 1 ORDER BY i.nombre, m.rol""",
            (usuario_id,),
        ).fetchall()
    cache: dict[int, Institucion] = {}
    resultado = []
    for f in filas:
        inst = cache.setdefault(f["institucion_id"], Institucion.obtener(f["institucion_id"]))
        resultado.append((inst, f["rol"]))
    return resultado


def tiene_rol(usuario_id: int, institucion_id: int, rol: str) -> bool:
    with get_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = ?",
            (usuario_id, institucion_id, rol),
        ).fetchone() is not None


def asignar_rol(usuario_id: int, institucion_id: int, rol: str) -> bool:
    if rol not in ROLES:
        raise ValueError("Rol inválido.")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO membresias (usuario_id, institucion_id, rol, creado_en) VALUES (?, ?, ?, ?)",
            (usuario_id, institucion_id, rol, ahora_iso()),
        )
    return cur.rowcount > 0


def quitar_rol(usuario_id: int, institucion_id: int, rol: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM membresias WHERE usuario_id = ? AND institucion_id = ? AND rol = ?",
                     (usuario_id, institucion_id, rol))
        conn.execute("DELETE FROM sesiones WHERE usuario_id = ? AND institucion_id = ? AND rol = ?",
                     (usuario_id, institucion_id, rol))


def es_superadmin(dni: str) -> bool:
    """La administración general se asigna por Secrets (SIA_SUPERADMINS = "dni1,dni2"), nunca desde la app."""
    permitidos = {d.strip() for d in (config_valor("SIA_SUPERADMINS") or "").split(",") if d.strip()}
    return dni in permitidos


# ---------------------------------------------------------------- opciones del sistema
OPCIONES = {
    "registro_estudiantes": ("Permitir que los estudiantes creen su cuenta", True),
    "registro_docentes": ("Permitir que los docentes creen su cuenta (con el código de su institución)", True),
    "autoinscripcion_qr": ("Inscribir automáticamente al escanear el QR de asistencia", True),
    "prediccion_ia": ("Usar el modelo de IA para estimar el riesgo (si no, solo reglas de asistencia)", True),
    "justificativos_alumnos": ("Permitir que los estudiantes suban justificativos", True),
}


def opcion(clave: str) -> bool:
    valor = leer_config(f"opcion_{clave}")
    return OPCIONES[clave][1] if valor is None else valor == "1"


def guardar_opcion(clave: str, activa: bool) -> None:
    if clave not in OPCIONES:
        raise ValueError("Opción desconocida.")
    guardar_config(f"opcion_{clave}", "1" if activa else "0")


def mensaje_sistema() -> str:
    return leer_config("mensaje_sistema") or ""


def guardar_mensaje_sistema(texto: str) -> None:
    guardar_config("mensaje_sistema", limpiar(texto, 300))
