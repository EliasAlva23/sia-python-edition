"""Materia: inscripciones, clases (sesiones) y consultas de asistencia."""
from __future__ import annotations

import re
import secrets
import sqlite3

import pandas as pd

from core import security
from core.database import get_connection
from core.tiempo import ahora_iso, hoy
from core.validaciones import errores_materia, limpiar

_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODIGO_RE = re.compile(r"^SIA-[A-Z0-9]{6}$")
PREFIJO_INSCRIPCION = "SIA:ENROLL:"
RESULTADOS = ("aprobado", "reprobado", "abandono")
ESTADOS_PRESENTE = ("presente", "tarde", "justificado")


class Materia:
    def __init__(
        self,
        id: int,
        nombre: str,
        descripcion: str,
        docente_id: int,
        codigo_clase: str,
        umbral: float = 75.0,
        activa: bool = True,
        curso: str = "",
        turno: str = "",
        dia_horario: str = "",
    ) -> None:
        self._id = id
        self._curso = curso
        self._turno = turno
        self._dia_horario = dia_horario
        self._nombre = nombre
        self._descripcion = descripcion
        self._docente_id = docente_id
        self._codigo_clase = codigo_clase
        self._umbral = float(umbral)
        self._activa = bool(activa)

    # ----- propiedades -----
    @property
    def id(self) -> int:
        return self._id

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def descripcion(self) -> str:
        return self._descripcion

    @property
    def docente_id(self) -> int:
        return self._docente_id

    @property
    def codigo_clase(self) -> str:
        return self._codigo_clase

    @property
    def umbral(self) -> float:
        return self._umbral

    @property
    def curso(self) -> str:
        return self._curso

    @property
    def turno(self) -> str:
        return self._turno

    @property
    def dia_horario(self) -> str:
        return self._dia_horario

    @property
    def payload_inscripcion(self) -> str:
        """SIA:ENROLL:<codigo>:<firma HMAC con SIA_SECRET>."""
        base = f"{PREFIJO_INSCRIPCION}{self._codigo_clase}"
        return f"{base}:{security.firmar(base, 12)}"

    @property
    def firma_inscripcion(self) -> str:
        return security.firmar(f"{PREFIJO_INSCRIPCION}{self._codigo_clase}", 12)

    @staticmethod
    def verificar_payload_inscripcion(codigo: str, firma: str) -> bool:
        codigo = (codigo or "").strip().upper()
        return bool(_CODIGO_RE.match(codigo)) and security.verificar_firma(
            f"{PREFIJO_INSCRIPCION}{codigo}", firma or "", 12
        )

    def __eq__(self, otro: object) -> bool:
        return isinstance(otro, Materia) and otro.id == self._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"Materia(id={self._id}, nombre={self._nombre!r})"

    # ----- fábricas / consultas -----
    @staticmethod
    def _desde_fila(fila: sqlite3.Row) -> "Materia":
        return Materia(
            fila["id"], fila["nombre"], fila["descripcion"], fila["docente_id"],
            fila["codigo_clase"], fila["umbral"], fila["activa"],
            fila["curso"], fila["turno"], fila["dia_horario"],
        )

    @staticmethod
    def _generar_codigo() -> str:
        while True:
            codigo = "".join(secrets.choice(_ALFABETO) for _ in range(6))
            if any(c.isalpha() for c in codigo):  # nunca 6 dígitos: no se confunde con un PIN
                return f"SIA-{codigo}"

    @staticmethod
    def normalizar_codigo(texto: str) -> str | None:
        t = (texto or "").strip().upper()
        if t.startswith(PREFIJO_INSCRIPCION):
            # Formato firmado SIA:ENROLL:<codigo>:<firma>: la firma debe ser válida.
            partes = t[len(PREFIJO_INSCRIPCION):].split(":")
            if len(partes) == 2 and not Materia.verificar_payload_inscripcion(partes[0], partes[1]):
                return None
            t = partes[0]
        if not t.startswith("SIA-"):
            t = f"SIA-{t}"
        return t if _CODIGO_RE.match(t) else None

    @staticmethod
    def _validar(nombre: str, curso: str, turno: str | None, dia_horario: str, umbral: float) -> None:
        errores = errores_materia(nombre, curso, turno, dia_horario)
        if not 0 <= umbral <= 100:
            errores.append("El umbral debe estar entre 0 y 100.")
        if errores:
            raise ValueError("\n".join(errores))

    @classmethod
    def crear(
        cls,
        nombre: str,
        descripcion: str,
        docente_id: int,
        umbral: float = 75.0,
        curso: str = "",
        turno: str = "",
        dia_horario: str = "",
    ) -> "Materia":
        cls._validar(nombre, curso, turno, dia_horario, umbral)
        nombre, curso, dia_horario = limpiar(nombre, 120), limpiar(curso, 80), limpiar(dia_horario, 120)
        descripcion = (descripcion or "").strip()[:500]
        for _ in range(10):
            codigo = cls._generar_codigo()
            try:
                with get_connection() as conn:
                    cur = conn.execute(
                        """INSERT INTO materias (nombre, descripcion, curso, turno, dia_horario,
                                                 docente_id, codigo_clase, umbral, creado_en)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (nombre, descripcion, curso, turno, dia_horario, docente_id, codigo, umbral, ahora_iso()),
                    )
                return cls(cur.lastrowid, nombre, descripcion, docente_id, codigo, umbral, True,
                           curso, turno, dia_horario)
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("No se pudo generar un código de clase único.")

    @classmethod
    def obtener(cls, id: int) -> "Materia | None":
        with get_connection() as conn:
            fila = conn.execute("SELECT * FROM materias WHERE id = ?", (id,)).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def por_codigo(cls, texto: str) -> "Materia | None":
        codigo = cls.normalizar_codigo(texto)
        if not codigo:
            return None
        with get_connection() as conn:
            fila = conn.execute(
                "SELECT * FROM materias WHERE codigo_clase = ? AND activa = 1", (codigo,)
            ).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def de_docente(cls, docente_id: int) -> list["Materia"]:
        with get_connection() as conn:
            filas = conn.execute(
                "SELECT * FROM materias WHERE docente_id = ? AND activa = 1 ORDER BY nombre", (docente_id,)
            ).fetchall()
        return [cls._desde_fila(f) for f in filas]

    @classmethod
    def de_estudiante(cls, estudiante_id: int) -> list["Materia"]:
        with get_connection() as conn:
            filas = conn.execute(
                """SELECT m.* FROM materias m JOIN inscripciones i ON i.materia_id = m.id
                   WHERE i.estudiante_id = ? AND m.activa = 1 ORDER BY m.nombre""",
                (estudiante_id,),
            ).fetchall()
        return [cls._desde_fila(f) for f in filas]

    # ----- gestión -----
    def actualizar(
        self, nombre: str, descripcion: str, umbral: float, curso: str, turno: str, dia_horario: str
    ) -> None:
        self._validar(nombre, curso, turno, dia_horario, umbral)
        nombre, curso, dia_horario = limpiar(nombre, 120), limpiar(curso, 80), limpiar(dia_horario, 120)
        descripcion = (descripcion or "").strip()[:500]
        with get_connection() as conn:
            conn.execute(
                """UPDATE materias SET nombre = ?, descripcion = ?, umbral = ?, curso = ?, turno = ?,
                                       dia_horario = ? WHERE id = ?""",
                (nombre, descripcion, umbral, curso, turno, dia_horario, self._id),
            )
        self._nombre, self._descripcion, self._umbral = nombre, descripcion, float(umbral)
        self._curso, self._turno, self._dia_horario = curso, turno, dia_horario

    def regenerar_codigo(self) -> str:
        for _ in range(10):
            codigo = self._generar_codigo()
            try:
                with get_connection() as conn:
                    conn.execute("UPDATE materias SET codigo_clase = ? WHERE id = ?", (codigo, self._id))
                self._codigo_clase = codigo
                return codigo
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("No se pudo regenerar el código.")

    def archivar(self) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE materias SET activa = 0 WHERE id = ?", (self._id,))
        self._activa = False

    # ----- inscripciones -----
    def inscribir(self, estudiante_id: int) -> tuple[bool, str]:
        """Idempotente: inscribir dos veces no duplica."""
        with get_connection() as conn:
            rol = conn.execute("SELECT rol FROM usuarios WHERE id = ?", (estudiante_id,)).fetchone()
            if not rol or rol["rol"] != "estudiante":
                return False, "Solo los estudiantes pueden inscribirse."
            cur = conn.execute(
                """INSERT INTO inscripciones (materia_id, estudiante_id, inscripto_en) VALUES (?, ?, ?)
                   ON CONFLICT (materia_id, estudiante_id) DO NOTHING""",
                (self._id, estudiante_id, ahora_iso()),
            )
        if cur.rowcount == 0:
            return False, f"Ya estabas inscripto/a en {self._nombre}."
        return True, f"¡Inscripción confirmada en {self._nombre}!"

    def desinscribir(self, estudiante_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM inscripciones WHERE materia_id = ? AND estudiante_id = ?",
                (self._id, estudiante_id),
            )

    def esta_inscripto(self, estudiante_id: int) -> bool:
        with get_connection() as conn:
            fila = conn.execute(
                "SELECT 1 FROM inscripciones WHERE materia_id = ? AND estudiante_id = ?",
                (self._id, estudiante_id),
            ).fetchone()
        return fila is not None

    def alumnos(self) -> pd.DataFrame:
        with get_connection() as conn:
            filas = conn.execute(
                """SELECT u.id, u.dni, u.apellido, u.nombre, u.email, u.legajo,
                          i.inscripto_en, i.resultado
                   FROM inscripciones i JOIN usuarios u ON u.id = i.estudiante_id
                   WHERE i.materia_id = ? ORDER BY u.apellido, u.nombre""",
                (self._id,),
            ).fetchall()
        return pd.DataFrame(
            [dict(f) for f in filas],
            columns=["id", "dni", "apellido", "nombre", "email", "legajo", "inscripto_en", "resultado"],
        )

    def establecer_resultado(self, estudiante_id: int, resultado: str | None) -> None:
        if resultado is not None and resultado not in RESULTADOS:
            raise ValueError("Resultado inválido.")
        with get_connection() as conn:
            conn.execute(
                "UPDATE inscripciones SET resultado = ? WHERE materia_id = ? AND estudiante_id = ?",
                (resultado, self._id, estudiante_id),
            )

    def resultados(self) -> dict[str, str]:
        """Resultados finales cargados por el docente, indexados por clave materia-estudiante."""
        with get_connection() as conn:
            filas = conn.execute(
                "SELECT estudiante_id, resultado FROM inscripciones WHERE materia_id = ? AND resultado IS NOT NULL",
                (self._id,),
            ).fetchall()
        return {f"{self._id}-{f['estudiante_id']}": f["resultado"] for f in filas}

    # ----- clases -----
    def abrir_clase(self, tema: str = "") -> int:
        """Abre (o reabre) la clase de hoy; idempotente por fecha."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO clases (materia_id, fecha, tema, abierta, creado_en) VALUES (?, ?, ?, 1, ?)
                   ON CONFLICT (materia_id, fecha) DO UPDATE SET
                       abierta = 1,
                       tema = CASE WHEN excluded.tema <> '' THEN excluded.tema ELSE clases.tema END""",
                (self._id, hoy().isoformat(), (tema or "").strip(), ahora_iso()),
            )
            fila = conn.execute(
                "SELECT id FROM clases WHERE materia_id = ? AND fecha = ?", (self._id, hoy().isoformat())
            ).fetchone()
        return fila["id"]

    def cerrar_clase(self, clase_id: int) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE clases SET abierta = 0 WHERE id = ? AND materia_id = ?", (clase_id, self._id))

    def clase_de_hoy(self) -> dict | None:
        with get_connection() as conn:
            fila = conn.execute(
                "SELECT * FROM clases WHERE materia_id = ? AND fecha = ?", (self._id, hoy().isoformat())
            ).fetchone()
        return dict(fila) if fila else None

    def clases(self) -> pd.DataFrame:
        with get_connection() as conn:
            filas = conn.execute(
                """SELECT c.id, c.fecha, c.tema, c.abierta,
                          (SELECT COUNT(*) FROM asistencias a WHERE a.clase_id = c.id) AS presentes
                   FROM clases c WHERE c.materia_id = ? ORDER BY c.fecha DESC""",
                (self._id,),
            ).fetchall()
        return pd.DataFrame([dict(f) for f in filas], columns=["id", "fecha", "tema", "abierta", "presentes"])

    # ----- ciencia de datos -----
    @staticmethod
    def registros_df(materia_ids: list[int], estudiante_id: int | None = None) -> pd.DataFrame:
        """Formato largo (una fila por alumno x clase), contando solo clases posteriores a la inscripción."""
        columnas = [
            "materia_id", "materia", "estudiante_id", "dni", "alumno", "clase_id", "fecha",
            "tema", "estado", "metodo", "registrado_en", "presente", "clave",
        ]
        if not materia_ids:
            return pd.DataFrame(columns=columnas)
        marcas = ",".join("?" * len(materia_ids))
        sql = f"""
            SELECT m.id AS materia_id, m.nombre AS materia, u.id AS estudiante_id, u.dni,
                   u.apellido || ', ' || u.nombre AS alumno,
                   c.id AS clase_id, c.fecha, c.tema,
                   COALESCE(a.estado, 'ausente') AS estado, a.metodo, a.registrado_en
            FROM inscripciones i
            JOIN materias m ON m.id = i.materia_id
            JOIN usuarios u ON u.id = i.estudiante_id
            JOIN clases c ON c.materia_id = i.materia_id AND c.fecha >= substr(i.inscripto_en, 1, 10)
            LEFT JOIN asistencias a ON a.clase_id = c.id AND a.estudiante_id = u.id
            WHERE i.materia_id IN ({marcas})
        """
        params: list = list(materia_ids)
        if estudiante_id is not None:
            sql += " AND u.id = ?"
            params.append(estudiante_id)
        sql += " ORDER BY c.fecha, alumno"
        with get_connection() as conn:
            filas = conn.execute(sql, params).fetchall()
        df = pd.DataFrame([dict(f) for f in filas], columns=columnas[:-2])
        df["presente"] = df["estado"].isin(ESTADOS_PRESENTE).astype(int)
        df["clave"] = df["materia_id"].astype(str) + "-" + df["estudiante_id"].astype(str)
        return df

    def matriz_asistencia(self) -> pd.DataFrame:
        df = self.registros_df([self._id])
        if df.empty:
            return pd.DataFrame()
        simbolos = {"presente": "✅", "tarde": "🕒", "justificado": "📝", "ausente": "❌"}
        df["marca"] = df["estado"].map(simbolos)
        matriz = df.pivot_table(index="alumno", columns="fecha", values="marca", aggfunc="first").fillna("—")
        porcentaje = df.groupby("alumno")["presente"].mean().mul(100).round(1)
        matriz.insert(0, "% asistencia", porcentaje)
        return matriz.sort_values("% asistencia")
