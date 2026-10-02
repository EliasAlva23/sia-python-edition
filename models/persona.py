"""Jerarquía de personas del sistema: Persona (abstracta) -> Docente / Estudiante."""
from __future__ import annotations

import re
import sqlite3
from abc import ABC, abstractmethod
from datetime import timedelta

from core import security
from core.database import get_connection
from core.tiempo import ahora, ahora_iso

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PREFIJO_CREDENCIAL = "SIA:STUDENT"


class Persona(ABC):
    """Datos comunes y credenciales encapsuladas (el hash nunca sale de la clase)."""

    def __init__(
        self,
        dni: str,
        nombre: str,
        apellido: str,
        email: str,
        id: int | None = None,
        password_hash: str | None = None,
        salt: str | None = None,
    ) -> None:
        self._id = id
        self._dni = self.normalizar_dni(dni)
        self._nombre = self._validar_texto(nombre, "nombre")
        self._apellido = self._validar_texto(apellido, "apellido")
        self._email = self._validar_email(email)
        self.__password_hash = password_hash
        self.__salt = salt

    # ----- propiedades de solo lectura -----
    @property
    def id(self) -> int | None:
        return self._id

    @property
    def dni(self) -> str:
        return self._dni

    @property
    def nombre(self) -> str:
        return self._nombre

    @property
    def apellido(self) -> str:
        return self._apellido

    @property
    def email(self) -> str:
        return self._email

    @property
    def nombre_completo(self) -> str:
        return f"{self._nombre} {self._apellido}"

    @property
    @abstractmethod
    def rol(self) -> str: ...

    # ----- contraseña -----
    def establecer_password(self, password: str) -> None:
        error = security.validar_fortaleza(password)
        if error:
            raise ValueError(error)
        self.__password_hash, self.__salt = security.hash_password(password)

    def verificar_password(self, password: str) -> bool:
        if not self.__password_hash or not self.__salt:
            return False
        return security.verificar_password(password, self.__password_hash, self.__salt)

    def _credenciales(self) -> tuple[str, str]:
        """Uso exclusivo del repositorio para persistir el hash."""
        if not self.__password_hash or not self.__salt:
            raise ValueError("La persona no tiene contraseña establecida.")
        return self.__password_hash, self.__salt

    def _asignar_id(self, id: int) -> None:
        self._id = id

    # ----- validaciones -----
    @staticmethod
    def normalizar_dni(dni: str) -> str:
        limpio = re.sub(r"[.\s-]", "", str(dni))
        if not re.fullmatch(r"\d{7,9}", limpio):
            raise ValueError("El DNI debe tener entre 7 y 9 dígitos.")
        return limpio

    @staticmethod
    def _validar_texto(valor: str, campo: str) -> str:
        valor = (valor or "").strip()
        if not valor or len(valor) > 80:
            raise ValueError(f"El campo {campo} es obligatorio (máx. 80 caracteres).")
        return valor

    @staticmethod
    def _validar_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("El email no es válido.")
        return email

    def _campos_extra(self) -> dict:
        return {}

    def to_dict(self) -> dict:
        return {
            "id": self._id,
            "dni": self._dni,
            "nombre": self._nombre,
            "apellido": self._apellido,
            "email": self._email,
            "rol": self.rol,
            **self._campos_extra(),
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._id}, dni={self._dni!r}, nombre={self.nombre_completo!r})"


class Docente(Persona):
    def __init__(self, *args, departamento: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._departamento = (departamento or "").strip() or None

    @property
    def rol(self) -> str:
        return "docente"

    @property
    def departamento(self) -> str | None:
        return self._departamento

    def _campos_extra(self) -> dict:
        return {"departamento": self._departamento}


class Estudiante(Persona):
    def __init__(self, *args, legajo: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._legajo = (legajo or "").strip() or None

    @property
    def rol(self) -> str:
        return "estudiante"

    @property
    def legajo(self) -> str | None:
        return self._legajo

    def credencial_qr(self) -> str:
        """Código firmado único: SIA:STUDENT:<dni>:<firma HMAC>."""
        base = f"{_PREFIJO_CREDENCIAL}:{self._dni}"
        return f"{base}:{security.firmar(base)}"

    @staticmethod
    def verificar_credencial(payload: str) -> str | None:
        """Devuelve el DNI si la credencial es auténtica, None en caso contrario."""
        partes = (payload or "").strip().split(":")
        if len(partes) != 4 or ":".join(partes[:2]).upper() != _PREFIJO_CREDENCIAL:
            return None
        dni, firma = partes[2], partes[3]
        if not re.fullmatch(r"\d{7,9}", dni):
            return None
        return dni if security.verificar_firma(f"{_PREFIJO_CREDENCIAL}:{dni}", firma) else None

    def _campos_extra(self) -> dict:
        return {"legajo": self._legajo}


class RepositorioPersonas:
    """Persistencia y autenticación de personas en SQLite."""

    MAX_INTENTOS = 5
    BLOQUEO_MINUTOS = 15
    _HASH_SENUELO = security.hash_password("sia-senuelo-0000")

    @staticmethod
    def _desde_fila(fila: sqlite3.Row) -> Persona:
        comunes = dict(
            dni=fila["dni"],
            nombre=fila["nombre"],
            apellido=fila["apellido"],
            email=fila["email"],
            id=fila["id"],
            password_hash=fila["password_hash"],
            salt=fila["salt"],
        )
        if fila["rol"] == "docente":
            return Docente(**comunes, departamento=fila["departamento"])
        return Estudiante(**comunes, legajo=fila["legajo"])

    @classmethod
    def registrar(cls, persona: Persona) -> Persona:
        password_hash, salt = persona._credenciales()
        datos = persona.to_dict()
        try:
            with get_connection() as conn:
                cur = conn.execute(
                    """INSERT INTO usuarios
                       (dni, nombre, apellido, email, rol, password_hash, salt, legajo, departamento, creado_en)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        datos["dni"], datos["nombre"], datos["apellido"], datos["email"], datos["rol"],
                        password_hash, salt, datos.get("legajo"), datos.get("departamento"), ahora_iso(),
                    ),
                )
                persona._asignar_id(cur.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ya existe un usuario con ese DNI o email.") from exc
        return persona

    @classmethod
    def obtener(cls, id: int) -> Persona | None:
        with get_connection() as conn:
            fila = conn.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (id,)).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def por_dni(cls, dni: str) -> Persona | None:
        try:
            dni = Persona.normalizar_dni(dni)
        except ValueError:
            return None
        with get_connection() as conn:
            fila = conn.execute("SELECT * FROM usuarios WHERE dni = ? AND activo = 1", (dni,)).fetchone()
        return cls._desde_fila(fila) if fila else None

    @classmethod
    def por_identificador(cls, identificador: str) -> Persona | None:
        identificador = identificador.strip().lower()
        if "@" in identificador:
            with get_connection() as conn:
                fila = conn.execute(
                    "SELECT * FROM usuarios WHERE email = ? AND activo = 1", (identificador,)
                ).fetchone()
            return cls._desde_fila(fila) if fila else None
        return cls.por_dni(identificador)

    @classmethod
    def autenticar(cls, identificador: str, password: str) -> tuple[Persona | None, str]:
        clave = identificador.strip().lower()
        if not clave or not password:
            return None, "Completá usuario y contraseña."
        desde = (ahora() - timedelta(minutes=cls.BLOQUEO_MINUTOS)).isoformat()
        with get_connection() as conn:
            fallos = conn.execute(
                """SELECT COUNT(*) FROM intentos_login
                   WHERE identificador = ? AND exito = 0 AND momento >= ?
                     AND momento > COALESCE(
                         (SELECT MAX(momento) FROM intentos_login WHERE identificador = ? AND exito = 1), '')""",
                (clave, desde, clave),
            ).fetchone()[0]
        if fallos >= cls.MAX_INTENTOS:
            return None, f"Demasiados intentos fallidos. Esperá {cls.BLOQUEO_MINUTOS} minutos."

        persona = cls.por_identificador(clave)
        if persona is None:
            # Igualamos el tiempo de respuesta para no revelar qué usuarios existen.
            security.verificar_password(password, *cls._HASH_SENUELO)
            ok = False
        else:
            ok = persona.verificar_password(password)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO intentos_login (identificador, exito, momento) VALUES (?, ?, ?)",
                (clave, int(ok), ahora_iso()),
            )
        if not ok:
            return None, "Usuario o contraseña incorrectos."
        return persona, "Bienvenido/a."

    @classmethod
    def cambiar_password(cls, persona: Persona, actual: str, nueva: str) -> None:
        if not persona.verificar_password(actual):
            raise ValueError("La contraseña actual no es correcta.")
        persona.establecer_password(nueva)
        password_hash, salt = persona._credenciales()
        with get_connection() as conn:
            conn.execute(
                "UPDATE usuarios SET password_hash = ?, salt = ? WHERE id = ?",
                (password_hash, salt, persona.id),
            )
