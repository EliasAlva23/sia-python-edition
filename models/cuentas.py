"""Altas de cuentas sin registro público: contraseña temporal, invitaciones por QR y bajas.

Las cuentas ya no se crean desde la pantalla de acceso:
  * Personal (docentes, Preceptoría, Dirección): lo da de alta Preceptoría, Dirección o la Administración general.
    El sistema genera una contraseña temporal y un QR de invitación de UN solo uso (vence a las 72 h). Al abrirlo,
    la persona entra directo a «Creá tu contraseña»; el cambio es obligatorio antes de ver su panel.
  * Estudiantes: crean su acceso desde el QR de una clase (o de inscripción a una materia) que proyecta el docente,
    o Preceptoría los vincula a mano.
  * Administración general: DNI listado en Secrets (SIA_SUPERADMINS). Si todavía no tiene cuenta, el primer ingreso
    usa la clave inicial de Secrets (SIA_SUPERADMIN_CLAVE_INICIAL) y luego debe cambiarla.

En la base se guarda solo el hash SHA-256 de cada token de invitación (como en las sesiones).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from core import sesiones
from core.database import get_connection
from core.security import config_valor
from core.tiempo import ahora
from models.institucion import Institucion, asignar_rol, es_superadmin, quitar_rol
from models.persona import (
    Directivo,
    Docente,
    Estudiante,
    Persona,
    Preceptor,
    RepositorioPersonas,
)

HORAS_INVITACION = 72
CLASES_POR_ROL = {"docente": Docente, "preceptor": Preceptor, "directivo": Directivo, "estudiante": Estudiante}
_LETRAS = "abcdefghjkmnpqrstuvwxyz"  # sin i, l, o: evitan confusiones al dictar la clave


def generar_clave_temporal() -> str:
    """Clave fácil de dictar y que cumple la política (letras y números, 10 caracteres)."""
    return f"Sia{secrets.randbelow(900000) + 100000}{secrets.choice(_LETRAS)}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class AltaCuenta:
    persona: Persona
    clave_temporal: str | None  # None si la persona ya tenía cuenta
    invitacion: str | None      # token del QR (se muestra una sola vez)
    rol_nuevo: bool


# ---------------------------------------------------------------- altas
def crear_o_asignar(institucion_id: int, rol: str, dni: str, nombre: str = "", apellido: str = "", email: str = "",
                    creado_por: int | None = None, con_invitacion: bool = True) -> AltaCuenta:
    """Da de alta a una persona con un rol en la institución.

    Si ya tiene cuenta (por ejemplo, en otra institución) solo se le asigna el rol. Si no, se crea con una
    contraseña temporal de cambio obligatorio y, para el personal, un QR de invitación de un solo uso.
    """
    if rol not in CLASES_POR_ROL:
        raise ValueError("Rol inválido.")
    persona = RepositorioPersonas.por_dni(dni)
    temporal = None
    if persona is None:
        temporal = generar_clave_temporal()
        persona = CLASES_POR_ROL[rol](dni, nombre, apellido, email)
        persona.establecer_password(temporal)
        RepositorioPersonas.registrar(persona)
        RepositorioPersonas.marcar_cambio_obligatorio(persona.id)
    nuevo = asignar_rol(persona.id, institucion_id, rol)
    invitacion = None
    if temporal and con_invitacion:
        invitacion = crear_invitacion(persona.id, institucion_id, rol, creado_por)
    return AltaCuenta(persona, temporal, invitacion, nuevo)


def registrar_estudiante(institucion_id: int, dni: str, nombre: str, apellido: str, email: str, password: str,
                         legajo: str = "") -> Estudiante:
    """Acceso creado por el propio alumno desde la invitación de una clase (QR del docente)."""
    estudiante = Estudiante(dni, nombre, apellido, email, legajo=legajo)
    estudiante.establecer_password(password)
    RepositorioPersonas.registrar(estudiante)
    asignar_rol(estudiante.id, institucion_id, "estudiante")
    return estudiante


# ---------------------------------------------------------------- invitaciones (QR de un solo uso)
def crear_invitacion(usuario_id: int, institucion_id: int, rol: str, creado_por: int | None = None,
                     horas: int = HORAS_INVITACION) -> str:
    """Genera un token nuevo e invalida las invitaciones anteriores de esa persona en la institución."""
    token = secrets.token_urlsafe(24)
    momento = ahora()
    with get_connection() as conn:
        conn.execute("DELETE FROM invitaciones WHERE usuario_id = ? AND institucion_id = ?", (usuario_id, institucion_id))
        conn.execute(
            """INSERT INTO invitaciones (token_hash, usuario_id, institucion_id, rol, creado_por, creado_en, expira_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_hash(token), usuario_id, institucion_id, rol, creado_por, momento.isoformat(),
             (momento + timedelta(hours=horas)).isoformat()),
        )
    return token


def canjear_invitacion(token: str | None) -> tuple[dict | None, str | None]:
    """Valida y consume la invitación. Devuelve ({usuario_id, institucion_id, rol}, None) o (None, error)."""
    if not token or len(token) > 200:
        return None, "El QR de invitación no es válido."
    momento = ahora().isoformat()
    with get_connection() as conn:
        fila = conn.execute("SELECT * FROM invitaciones WHERE token_hash = ?", (_hash(token),)).fetchone()
        if fila is None:
            return None, "El QR de invitación no es válido o fue reemplazado por uno nuevo. Pedí uno nuevo a Preceptoría."
        if fila["usada_en"]:
            return None, "Ese QR de invitación ya se usó. Ingresá con tu DNI y tu contraseña."
        if fila["expira_en"] < momento:
            return None, "El QR de invitación venció. Pedí uno nuevo a Preceptoría."
        vigente = conn.execute(
            """SELECT 1 FROM membresias m JOIN usuarios u ON u.id = m.usuario_id
               JOIN instituciones i ON i.id = m.institucion_id
               WHERE m.usuario_id = ? AND m.institucion_id = ? AND m.rol = ? AND u.activo = 1 AND i.activa = 1""",
            (fila["usuario_id"], fila["institucion_id"], fila["rol"]),
        ).fetchone()
        if vigente is None:
            return None, "La invitación ya no está vigente: el acceso fue dado de baja."
        cur = conn.execute("UPDATE invitaciones SET usada_en = ? WHERE token_hash = ? AND usada_en IS NULL",
                           (momento, fila["token_hash"]))
        if cur.rowcount == 0:  # otro dispositivo la canjeó al mismo tiempo
            return None, "Ese QR de invitación ya se usó. Ingresá con tu DNI y tu contraseña."
    return {"usuario_id": fila["usuario_id"], "institucion_id": fila["institucion_id"], "rol": fila["rol"]}, None


def invitacion_pendiente(usuario_id: int, institucion_id: int) -> datetime | None:
    """Vencimiento de la invitación sin usar de esa persona, si existe."""
    with get_connection() as conn:
        fila = conn.execute(
            """SELECT expira_en FROM invitaciones WHERE usuario_id = ? AND institucion_id = ? AND usada_en IS NULL
               AND expira_en >= ? ORDER BY expira_en DESC LIMIT 1""",
            (usuario_id, institucion_id, ahora().isoformat()),
        ).fetchone()
    return datetime.fromisoformat(fila["expira_en"]) if fila else None


# ---------------------------------------------------------------- gestión del personal (Preceptoría)
def puede_gestionar_clave(usuario_id: int, institucion_id: int, roles_permitidos: tuple[str, ...] = ("docente",)) -> bool:
    """Preceptoría solo restablece claves de cuentas que pertenecen únicamente a su institución y con roles
    permitidos: así no puede tomar el control de un directivo, de otra institución ni de la Administración."""
    from models.demo import es_cuenta_demo

    persona = RepositorioPersonas.obtener(usuario_id)
    if persona is None or es_superadmin(persona.dni) or es_cuenta_demo(persona.dni):
        return False
    with get_connection() as conn:
        filas = conn.execute("SELECT institucion_id, rol FROM membresias WHERE usuario_id = ?", (usuario_id,)).fetchall()
    return bool(filas) and all(f["institucion_id"] == institucion_id and f["rol"] in roles_permitidos for f in filas)


def restablecer_clave(usuario_id: int, institucion_id: int | None, rol: str | None,
                      por: int | None = None) -> tuple[str, str | None]:
    """Nueva clave temporal (cambio obligatorio), cierra sus sesiones y, si hay institución y rol, genera un QR de
    invitación nuevo (los anteriores quedan anulados)."""
    persona = RepositorioPersonas.obtener(usuario_id)
    if persona is None:
        raise ValueError("La cuenta no existe o está inactiva.")
    temporal = generar_clave_temporal()
    RepositorioPersonas.guardar_password(persona, temporal, temporal=True)
    sesiones.cerrar_todas(usuario_id)
    token = crear_invitacion(usuario_id, institucion_id, rol, por) if institucion_id and rol else None
    return temporal, token


def dar_de_baja(usuario_id: int, institucion_id: int, rol: str = "docente") -> None:
    """Quita el rol en la institución, cierra sus sesiones con ese rol e invalida las invitaciones pendientes.

    La cuenta y el historial (materias, clases, asistencias) se conservan: la persona puede seguir activa en otra
    institución y los registros académicos no se pierden.
    """
    quitar_rol(usuario_id, institucion_id, rol)
    with get_connection() as conn:
        conn.execute("DELETE FROM invitaciones WHERE usuario_id = ? AND institucion_id = ?", (usuario_id, institucion_id))


def personal_con_estado(institucion: Institucion, rol: str = "docente") -> pd.DataFrame:
    """Personal con un rol, su estado de acceso y cuántas materias activas dicta."""
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT u.id, u.dni, u.apellido, u.nombre, u.email, u.debe_cambiar_password AS pendiente,
                      (SELECT COUNT(*) FROM materias m WHERE m.docente_id = u.id AND m.institucion_id = ?
                        AND m.activa = 1) AS materias,
                      (SELECT MAX(s.ultimo_uso) FROM sesiones s WHERE s.usuario_id = u.id) AS ultimo_uso
               FROM membresias mb JOIN usuarios u ON u.id = mb.usuario_id
               WHERE mb.institucion_id = ? AND mb.rol = ? AND u.activo = 1
               ORDER BY u.apellido, u.nombre""",
            (institucion.id, institucion.id, rol),
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas],
                        columns=["id", "dni", "apellido", "nombre", "email", "pendiente", "materias", "ultimo_uso"])


# ---------------------------------------------------------------- Administración general
def asegurar_superadmin(dni: str, clave: str) -> Persona | None:
    """Primer ingreso de la Administración general cuando su DNI (de Secrets) todavía no tiene cuenta.

    Solo funciona si la clave coincide con SIA_SUPERADMIN_CLAVE_INICIAL (definida en Secrets, nunca en el repo).
    La cuenta queda con cambio de contraseña obligatorio.
    """
    inicial = config_valor("SIA_SUPERADMIN_CLAVE_INICIAL")
    try:
        dni = Persona.normalizar_dni(dni)
    except ValueError:
        return None
    if not inicial or not es_superadmin(dni) or RepositorioPersonas.por_dni(dni) is not None:
        return None
    if not hmac.compare_digest(clave.encode("utf-8"), inicial.encode("utf-8")):
        return None
    # La columna heredada `usuarios.rol` no admite «superadmin»: se guarda como «directivo» sin membresías.
    # El acceso a la Administración general surge solo de SIA_SUPERADMINS.
    try:
        admin = Directivo(dni, "Administración", "General", f"admin{dni}@sia.local")
        admin.establecer_password(inicial)  # la clave inicial debe cumplir la política (8+, letras y números)
        RepositorioPersonas.registrar(admin)
    except ValueError:
        return None
    RepositorioPersonas.marcar_cambio_obligatorio(admin.id)
    return admin


def momento_legible(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except ValueError:
        return None

