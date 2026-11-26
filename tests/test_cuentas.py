"""Altas por invitación (QR), contraseña temporal, restablecimiento, baja y primer ingreso de la Administración."""
from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import crear_materia

from core import sesiones
from core.database import get_connection
from core.tiempo import ahora
from models import cuentas
from models.institucion import asignar_rol, roles_de, tiene_rol
from models.persona import RepositorioPersonas


def _alta_docente(institucion, dni="30111222"):
    return cuentas.crear_o_asignar(institucion.id, "docente", dni, "Laura", "Gómez", f"laura{dni}@ejemplo.com")


# ---------------------------------------------------------------- alta con clave temporal
def test_alta_docente_genera_usuario_clave_temporal_e_invitacion(institucion):
    alta = _alta_docente(institucion)
    assert alta.clave_temporal and alta.invitacion and alta.rol_nuevo
    assert tiene_rol(alta.persona.id, institucion.id, "docente")
    persona, _ = RepositorioPersonas.autenticar("30111222", alta.clave_temporal)
    assert persona is not None and persona.id == alta.persona.id
    assert RepositorioPersonas.debe_cambiar_password(alta.persona.id)


def test_alta_se_puede_reintentar_si_falla_la_invitacion(institucion, monkeypatch):
    with monkeypatch.context() as parche:
        def falla(*args, **kwargs):
            raise RuntimeError("Error al guardar la invitación")

        parche.setattr(cuentas, "crear_invitacion", falla)
        with pytest.raises(RuntimeError, match="invitar|invitación"):
            _alta_docente(institucion)
    assert RepositorioPersonas.por_dni("30111222") is None
    assert _alta_docente(institucion).invitacion


def test_clave_temporal_cumple_politica_y_es_distinta():
    claves = {cuentas.generar_clave_temporal() for _ in range(50)}
    assert len(claves) > 45
    from core.security import validar_fortaleza

    assert all(validar_fortaleza(c) is None for c in claves)


def test_alta_de_persona_existente_solo_asigna_rol(institucion, otra_institucion):
    alta = _alta_docente(institucion)
    otra = cuentas.crear_o_asignar(otra_institucion.id, "docente", "30111222")
    assert otra.persona.id == alta.persona.id
    assert otra.clave_temporal is None and otra.invitacion is None and otra.rol_nuevo
    assert {(i.id, r) for i, r in roles_de(alta.persona.id)} == {(institucion.id, "docente"),
                                                                 (otra_institucion.id, "docente")}


def test_cambio_de_clave_quita_la_obligacion(institucion):
    alta = _alta_docente(institucion)
    RepositorioPersonas.guardar_password(alta.persona, "MiClaveNueva2026")
    assert not RepositorioPersonas.debe_cambiar_password(alta.persona.id)
    assert RepositorioPersonas.autenticar("30111222", alta.clave_temporal)[0] is None
    assert RepositorioPersonas.autenticar("30111222", "MiClaveNueva2026")[0] is not None


# ---------------------------------------------------------------- invitación (QR de un solo uso)
def test_invitacion_se_canjea_una_sola_vez(institucion):
    alta = _alta_docente(institucion)
    datos, error = cuentas.canjear_invitacion(alta.invitacion)
    assert error is None
    assert datos == {"usuario_id": alta.persona.id, "institucion_id": institucion.id, "rol": "docente"}
    datos, error = cuentas.canjear_invitacion(alta.invitacion)
    assert datos is None and "ya se usó" in error


def test_invitacion_vencida_o_invalida(institucion):
    alta = _alta_docente(institucion)
    with get_connection() as conn:
        conn.execute("UPDATE invitaciones SET expira_en = ?", ((ahora() - timedelta(minutes=1)).isoformat(),))
    datos, error = cuentas.canjear_invitacion(alta.invitacion)
    assert datos is None and "venció" in error
    assert cuentas.canjear_invitacion("token-inventado")[0] is None
    assert cuentas.canjear_invitacion("")[0] is None


def test_invitacion_nueva_anula_la_anterior(institucion):
    alta = _alta_docente(institucion)
    nuevo = cuentas.crear_invitacion(alta.persona.id, institucion.id, "docente")
    assert cuentas.canjear_invitacion(alta.invitacion)[0] is None
    assert cuentas.canjear_invitacion(nuevo)[0] is not None


def test_en_la_base_solo_se_guarda_el_hash_del_token(institucion):
    alta = _alta_docente(institucion)
    with get_connection() as conn:
        guardados = [f["token_hash"] for f in conn.execute("SELECT token_hash FROM invitaciones")]
    assert alta.invitacion not in guardados and len(guardados[0]) == 64


def test_invitacion_pendiente_informa_vencimiento(institucion):
    alta = _alta_docente(institucion)
    assert cuentas.invitacion_pendiente(alta.persona.id, institucion.id) is not None
    cuentas.canjear_invitacion(alta.invitacion)
    assert cuentas.invitacion_pendiente(alta.persona.id, institucion.id) is None


# ---------------------------------------------------------------- restablecer y baja
def test_restablecer_clave_temporal(institucion):
    alta = _alta_docente(institucion)
    RepositorioPersonas.guardar_password(alta.persona, "MiClaveNueva2026")
    token_sesion = sesiones.crear(alta.persona.id, institucion.id, "docente")
    temporal, token = cuentas.restablecer_clave(alta.persona.id, institucion.id, "docente")
    assert RepositorioPersonas.debe_cambiar_password(alta.persona.id)
    assert RepositorioPersonas.autenticar("30111222", "MiClaveNueva2026")[0] is None
    assert RepositorioPersonas.autenticar("30111222", temporal)[0] is not None
    assert sesiones.validar(token_sesion) is None  # se cerraron sus sesiones
    assert cuentas.canjear_invitacion(alta.invitacion)[0] is None  # la invitación vieja quedó anulada
    assert cuentas.canjear_invitacion(token)[0] is not None


def test_preceptoria_solo_gestiona_claves_de_docentes_de_su_institucion(institucion, otra_institucion, monkeypatch):
    docente = _alta_docente(institucion).persona
    assert cuentas.puede_gestionar_clave(docente.id, institucion.id)
    assert not cuentas.puede_gestionar_clave(docente.id, otra_institucion.id)

    doble = _alta_docente(institucion, "30222333").persona
    asignar_rol(doble.id, institucion.id, "directivo")
    assert not cuentas.puede_gestionar_clave(doble.id, institucion.id)

    multi = _alta_docente(institucion, "30333444").persona
    asignar_rol(multi.id, otra_institucion.id, "docente")
    assert not cuentas.puede_gestionar_clave(multi.id, institucion.id)

    monkeypatch.setenv("SIA_SUPERADMINS", "30111222")
    assert not cuentas.puede_gestionar_clave(docente.id, institucion.id)


def test_baja_de_docente_quita_acceso_y_conserva_historial(institucion):
    alta = _alta_docente(institucion)
    materia = crear_materia(alta.persona.id, institucion.id)
    token_sesion = sesiones.crear(alta.persona.id, institucion.id, "docente")
    cuentas.dar_de_baja(alta.persona.id, institucion.id, "docente")
    assert not tiene_rol(alta.persona.id, institucion.id, "docente")
    assert sesiones.validar(token_sesion) is None
    datos, error = cuentas.canjear_invitacion(alta.invitacion)
    assert datos is None and error
    from models.materia import Materia

    assert Materia.obtener(materia.id) is not None  # materias e historial se conservan
    assert RepositorioPersonas.obtener(alta.persona.id) is not None  # la cuenta sigue existiendo


def test_baja_invalida_invitacion_aunque_la_cuenta_siga_en_otra_institucion(institucion, otra_institucion):
    alta = _alta_docente(institucion)
    asignar_rol(alta.persona.id, otra_institucion.id, "docente")
    cuentas.dar_de_baja(alta.persona.id, institucion.id)
    assert cuentas.canjear_invitacion(alta.invitacion)[0] is None
    assert tiene_rol(alta.persona.id, otra_institucion.id, "docente")


def test_personal_con_estado_marca_pendientes(institucion):
    a = _alta_docente(institucion).persona
    b = _alta_docente(institucion, "30999888").persona
    RepositorioPersonas.guardar_password(b, "OtraClave2026")
    crear_materia(a.id, institucion.id)
    df = cuentas.personal_con_estado(institucion, "docente").set_index("dni")
    assert bool(df.loc["30111222", "pendiente"]) and not bool(df.loc["30999888", "pendiente"])
    assert int(df.loc["30111222", "materias"]) == 1


# ---------------------------------------------------------------- estudiantes y sesiones
def test_registrar_estudiante_desde_clase(institucion):
    alumno = cuentas.registrar_estudiante(institucion.id, "45111222", "Ana", "Pérez", "ana@ejemplo.com", "Clave2026x")
    assert tiene_rol(alumno.id, institucion.id, "estudiante")
    assert not RepositorioPersonas.debe_cambiar_password(alumno.id)
    try:
        cuentas.registrar_estudiante(institucion.id, "45111222", "Ana", "Pérez", "otra@ejemplo.com", "Clave2026x")
    except ValueError as exc:
        assert "Ya existe" in str(exc)
    else:
        raise AssertionError("Se permitió un DNI duplicado")


def test_cerrar_todas_las_sesiones_salvo_la_actual(institucion):
    alta = _alta_docente(institucion)
    actual = sesiones.crear(alta.persona.id, institucion.id, "docente")
    otra = sesiones.crear(alta.persona.id, institucion.id, "docente")
    sesiones.cerrar_todas(alta.persona.id, excepto=actual)
    assert sesiones.validar(actual) is not None and sesiones.validar(otra) is None
    sesiones.cerrar_todas(alta.persona.id)
    assert sesiones.validar(actual) is None


# ---------------------------------------------------------------- Administración general
def test_primer_ingreso_de_superadmin(db, monkeypatch):
    assert cuentas.asegurar_superadmin("20111222", "ClaveInicial2026") is None  # sin Secrets: no hace nada
    monkeypatch.setenv("SIA_SUPERADMINS", "20111222")
    monkeypatch.setenv("SIA_SUPERADMIN_CLAVE_INICIAL", "ClaveInicial2026")
    assert cuentas.asegurar_superadmin("20111222", "otra-clave") is None
    assert cuentas.asegurar_superadmin("30999000", "ClaveInicial2026") is None  # DNI fuera de la lista
    admin = cuentas.asegurar_superadmin("20111222", "ClaveInicial2026")
    assert admin is not None and RepositorioPersonas.debe_cambiar_password(admin.id)
    assert roles_de(admin.id) == []  # su acceso surge solo de SIA_SUPERADMINS
    assert cuentas.asegurar_superadmin("20111222", "ClaveInicial2026") is None  # ya existe
    assert RepositorioPersonas.autenticar("20111222", "ClaveInicial2026")[0] is not None


def test_migracion_agrega_columna_a_bases_anteriores(db):
    import core.database as database

    with get_connection() as conn:
        conn.execute("ALTER TABLE usuarios DROP COLUMN debe_cambiar_password")
        conn.execute("DROP TABLE invitaciones")
        conn.execute("UPDATE config SET valor = '4' WHERE clave = 'schema_version'")
    assert not database.esquema_al_dia()
    database.asegurar_esquema()
    with get_connection() as conn:
        columnas = {c["name"] for c in conn.execute("PRAGMA table_info(usuarios)")}
        tablas = {t["name"] for t in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "debe_cambiar_password" in columnas and "invitaciones" in tablas


def test_enlace_de_invitacion():
    from urllib.parse import parse_qs, urlparse

    from utils.qr import contenido_invitacion

    enlace = contenido_invitacion("abc123")
    assert parse_qs(urlparse(enlace).query) == {"invitacion": ["abc123"]}
