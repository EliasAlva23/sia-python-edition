"""Registro de asistencia por QR con control de idempotencia.

Tokens soportados:
  * Credencial del alumno (la escanea el docente):   SIA:STUDENT:<dni>:<firma>
  * QR dinámico de clase (lo escanea el alumno):     SIA:C:<clase_id>:<ventana>:<firma>
  * PIN rotativo de 6 dígitos (ingreso manual del alumno, misma ventana que el QR).

Los QR de clase rotan cada `VENTANA_SEGUNDOS` y se acepta también la ventana anterior,
por lo que una captura compartida deja de servir en menos de un minuto.
"""
from __future__ import annotations

import hmac
import time
from dataclasses import dataclass

import pandas as pd

from core import security
from core.database import get_connection
from core.tiempo import ahora_iso, hoy
from models.persona import Estudiante, Persona, RepositorioPersonas

VENTANA_SEGUNDOS = 30
ESTADOS = ("presente", "tarde", "justificado")
METODOS = ("qr_credencial", "qr_clase", "pin", "manual")


@dataclass(frozen=True)
class ResultadoMarcado:
    ok: bool
    estado: str  # 'registrado' | 'duplicado' | 'error'
    mensaje: str
    estudiante: str | None = None

    @property
    def es_duplicado(self) -> bool:
        return self.estado == "duplicado"


def _ventana(t: float | None = None) -> int:
    return int((t if t is not None else time.time()) // VENTANA_SEGUNDOS)


def segundos_restantes(t: float | None = None) -> int:
    t = t if t is not None else time.time()
    return int(VENTANA_SEGUNDOS - (t % VENTANA_SEGUNDOS))


class RegistroAsistencia:
    """Opera sobre una clase (sesión) concreta."""

    def __init__(self, clase_id: int) -> None:
        self._clase_id = int(clase_id)

    @property
    def clase_id(self) -> int:
        return self._clase_id

    def materia_id(self) -> int | None:
        with get_connection() as conn:
            fila = conn.execute("SELECT materia_id FROM clases WHERE id = ?", (self._clase_id,)).fetchone()
        return fila["materia_id"] if fila else None

    # ----- tokens dinámicos de clase -----
    def generar_token(self, t: float | None = None) -> str:
        base = f"SIA:C:{self._clase_id}:{_ventana(t)}"
        return f"{base}:{security.firmar(base, 12)}"

    def generar_pin(self, t: float | None = None, ventana: int | None = None) -> str:
        w = ventana if ventana is not None else _ventana(t)
        numero = int(security.firmar(f"SIA:PIN:{self._clase_id}:{w}", 12), 16)
        return f"{numero % 1_000_000:06d}"

    def _pin_valido(self, pin: str) -> bool:
        w = _ventana()
        return any(hmac.compare_digest(self.generar_pin(ventana=v), pin) for v in (w, w - 1))

    # ----- marcado (núcleo idempotente) -----
    def marcar(
        self,
        estudiante_id: int,
        metodo: str,
        registrado_por: int | None,
        estado: str = "presente",
        docente_id: int | None = None,
    ) -> ResultadoMarcado:
        if estado not in ESTADOS or metodo not in METODOS:
            return ResultadoMarcado(False, "error", "Estado o método inválido.")
        with get_connection() as conn:
            clase = conn.execute(
                """SELECT c.id, c.abierta, c.fecha, c.materia_id, m.docente_id, m.nombre
                   FROM clases c JOIN materias m ON m.id = c.materia_id WHERE c.id = ?""",
                (self._clase_id,),
            ).fetchone()
            if clase is None:
                return ResultadoMarcado(False, "error", "La clase no existe.")
            if docente_id is not None and clase["docente_id"] != docente_id:
                return ResultadoMarcado(False, "error", "No sos el docente de esta materia.")
            if not clase["abierta"] or clase["fecha"] != hoy().isoformat():
                return ResultadoMarcado(False, "error", "La clase no está abierta para registrar asistencia.")
            alumno = conn.execute(
                """SELECT u.id, u.nombre, u.apellido FROM usuarios u
                   JOIN inscripciones i ON i.estudiante_id = u.id
                   WHERE u.id = ? AND i.materia_id = ? AND u.rol = 'estudiante' AND u.activo = 1""",
                (estudiante_id, clase["materia_id"]),
            ).fetchone()
            if alumno is None:
                return ResultadoMarcado(False, "error", f"El alumno no está inscripto en {clase['nombre']}.")
            nombre = f"{alumno['nombre']} {alumno['apellido']}"
            cur = conn.execute(
                """INSERT INTO asistencias (clase_id, estudiante_id, estado, metodo, registrado_por, registrado_en)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (clase_id, estudiante_id) DO NOTHING""",
                (self._clase_id, estudiante_id, estado, metodo, registrado_por, ahora_iso()),
            )
            if cur.rowcount == 0:
                previo = conn.execute(
                    "SELECT registrado_en FROM asistencias WHERE clase_id = ? AND estudiante_id = ?",
                    (self._clase_id, estudiante_id),
                ).fetchone()
                hora = previo["registrado_en"][11:16] if previo else "--:--"
                return ResultadoMarcado(True, "duplicado", f"{nombre} ya tenía presente (registrado {hora}).", nombre)
        return ResultadoMarcado(True, "registrado", f"Presente registrado: {nombre}.", nombre)

    def actualizar_estado(self, estudiante_id: int, estado: str) -> None:
        if estado not in ESTADOS:
            raise ValueError("Estado inválido.")
        with get_connection() as conn:
            conn.execute(
                "UPDATE asistencias SET estado = ? WHERE clase_id = ? AND estudiante_id = ?",
                (estado, self._clase_id, estudiante_id),
            )

    def anular(self, estudiante_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM asistencias WHERE clase_id = ? AND estudiante_id = ?",
                (self._clase_id, estudiante_id),
            )

    # ----- flujos de entrada -----
    def procesar_credencial(self, payload: str, docente_id: int) -> ResultadoMarcado:
        """El docente escanea la credencial QR del alumno."""
        dni = Estudiante.verificar_credencial(payload)
        if dni is None:
            return ResultadoMarcado(False, "error", "Credencial inválida o adulterada.")
        return self.marcar_por_dni(dni, docente_id, metodo="qr_credencial")

    def marcar_por_dni(
        self, dni: str, docente_id: int, metodo: str = "manual", estado: str = "presente"
    ) -> ResultadoMarcado:
        persona = RepositorioPersonas.por_dni(dni)
        if persona is None or persona.rol != "estudiante":
            return ResultadoMarcado(False, "error", "No existe un estudiante con ese DNI.")
        return self.marcar(persona.id, metodo, docente_id, estado=estado, docente_id=docente_id)

    @staticmethod
    def validar_token_clase(token: str) -> tuple[int | None, str | None]:
        """Verifica firma HMAC y vigencia. Devuelve (clase_id, None) o (None, mensaje de error)."""
        partes = (token or "").strip().split(":")
        if len(partes) != 5 or partes[0].upper() != "SIA" or partes[1].upper() != "C":
            return None, "El código no es un QR de clase válido."
        try:
            clase_id, ventana = int(partes[2]), int(partes[3])
        except ValueError:
            return None, "QR de clase mal formado."
        if not security.verificar_firma(f"SIA:C:{clase_id}:{ventana}", partes[4], 12):
            return None, "QR de clase adulterado."
        if ventana not in (_ventana(), _ventana() - 1):
            return None, "El QR expiró. Escaneá el código que se proyecta ahora."
        return clase_id, None

    @staticmethod
    def procesar_token_clase(token: str, estudiante: Persona) -> ResultadoMarcado:
        """El alumno escanea el QR dinámico proyectado por el docente."""
        clase_id, error = RegistroAsistencia.validar_token_clase(token)
        if error:
            return ResultadoMarcado(False, "error", error)
        return RegistroAsistencia(clase_id).marcar(estudiante.id, "qr_clase", estudiante.id)

    @staticmethod
    def procesar_pin(pin: str, estudiante: Persona) -> ResultadoMarcado:
        """Busca entre las clases abiertas hoy de las materias del alumno la que coincide con el PIN."""
        pin = (pin or "").strip()
        if not (len(pin) == 6 and pin.isdigit()):
            return ResultadoMarcado(False, "error", "El PIN debe tener 6 dígitos.")
        with get_connection() as conn:
            clases = conn.execute(
                """SELECT c.id FROM clases c JOIN inscripciones i ON i.materia_id = c.materia_id
                   WHERE i.estudiante_id = ? AND c.fecha = ? AND c.abierta = 1""",
                (estudiante.id, hoy().isoformat()),
            ).fetchall()
        for fila in clases:
            registro = RegistroAsistencia(fila["id"])
            if registro._pin_valido(pin):
                return registro.marcar(estudiante.id, "pin", estudiante.id)
        return ResultadoMarcado(False, "error", "PIN incorrecto o expirado, o no hay clases abiertas en tus materias.")

    # ----- consultas -----
    def presentes(self) -> pd.DataFrame:
        with get_connection() as conn:
            filas = conn.execute(
                """SELECT u.id, u.dni, u.apellido || ', ' || u.nombre AS alumno, a.estado, a.metodo,
                          substr(a.registrado_en, 12, 5) AS hora
                   FROM asistencias a JOIN usuarios u ON u.id = a.estudiante_id
                   WHERE a.clase_id = ? ORDER BY a.registrado_en DESC""",
                (self._clase_id,),
            ).fetchall()
        return pd.DataFrame([dict(f) for f in filas], columns=["id", "dni", "alumno", "estado", "metodo", "hora"])
