"""Verifica e inicializa la base de datos SQLite del SIA.

Uso:
    python seed_init.py                 # crea tablas/índices si faltan y muestra el estado
    python seed_init.py --crear-docente # además da de alta una cuenta docente (interactivo)

La app también ejecuta `init_db()` al arrancar, por lo que en Streamlit Community
Cloud no hace falta correr este script manualmente.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from core.database import DB_PATH, TABLAS, get_connection, init_db, leer_config, tablas_existentes


def verificar() -> bool:
    presentes = set(tablas_existentes())
    faltantes = [t for t in TABLAS if t not in presentes]
    print(f"Base de datos: {DB_PATH}")
    print(f"Versión de esquema: {leer_config('schema_version')}")
    with get_connection() as conn:
        for tabla in TABLAS:
            if tabla in presentes:
                total = conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
                print(f"  ✔ {tabla:<15} {total:>6} filas")
            else:
                print(f"  ✘ {tabla:<15} FALTA")
        integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"Integridad: {integridad}")
    return not faltantes and integridad == "ok"


def crear_docente() -> None:
    from models.persona import Docente, RepositorioPersonas

    print("\nAlta de docente")
    try:
        docente = Docente(
            input("DNI: "), input("Nombre: "), input("Apellido: "), input("Email: "),
            departamento=input("Departamento (opcional): "),
        )
        password = getpass.getpass("Contraseña: ")
        if password != getpass.getpass("Repetir contraseña: "):
            raise ValueError("Las contraseñas no coinciden.")
        docente.establecer_password(password)
        RepositorioPersonas.registrar(docente)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    print(f"Docente creado: {docente!r}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # consolas Windows (cp1252) y símbolos ✔/✘
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crear-docente", action="store_true", help="dar de alta una cuenta docente")
    args = parser.parse_args()

    nueva = not DB_PATH.exists()
    init_db()
    print("Base de datos creada." if nueva else "Base de datos existente verificada.")
    ok = verificar()
    if args.crear_docente:
        crear_docente()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
