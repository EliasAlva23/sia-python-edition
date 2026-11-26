"""Cada prueba usa una base SQLite nueva en una carpeta temporal (nunca la database.db real)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@pytest.fixture
def db(tmp_path, monkeypatch):
    ruta = tmp_path / "sia_test.db"
    monkeypatch.setenv("SIA_DB_PATH", str(ruta))
    monkeypatch.setenv("SIA_SECRET", "clave-de-pruebas-no-usar-en-produccion")
    monkeypatch.setenv("SIA_DEMO", "0")  # cada prueba activa la demostración solo si la necesita
    monkeypatch.delenv("SIA_DEMO_CLAVE", raising=False)
    monkeypatch.delenv("SIA_SUPERADMINS", raising=False)
    monkeypatch.delenv("SIA_SUPERADMIN_CLAVE_INICIAL", raising=False)
    import core.database as database
    import core.security as security

    monkeypatch.setattr(database, "DB_PATH", ruta)
    monkeypatch.setattr(security, "_secreto_cache", None)
    database.init_db()
    return ruta


@pytest.fixture
def institucion(db):
    from models.institucion import Institucion

    return Institucion.todas()[0]


@pytest.fixture
def otra_institucion(db):
    from models.institucion import Institucion

    return Institucion.crear(nombre="Instituto Superior N° 5", nombre_corto="IS N° 5", slug="is5",
                             color_primario="#3F7C70", color_secundario="#2E5772", umbral_regular=75,
                             umbral_promocion=80, tolerancia_tarde=10)


def crear_materia(docente_id: int, institucion_id: int, nombre: str = "Didáctica General"):
    from models.materia import Materia

    return Materia.crear(docente_id, institucion_id, nombre=nombre, curso="1° Año", comision="Comisión 1",
                         turno="Mañana", dias=["Lunes"], hora_inicio="08:00", hora_fin="10:00")
