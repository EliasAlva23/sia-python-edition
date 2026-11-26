"""Flujos completos de la app con streamlit.testing (sin navegador): acceso, invitación QR, alta de alumno desde
el QR de una clase, cambio obligatorio de contraseña y paneles por rol."""
from __future__ import annotations

import sys

import pytest
from conftest import RAIZ, crear_materia
from streamlit.testing.v1 import AppTest

PAQUETES = ("core", "models", "utils", "views")


@pytest.fixture
def app(db):
    # Evita que app.py descarte y reimporte los módulos del proyecto (lo hace al detectar código nuevo en Cloud):
    # así la app y las pruebas comparten la misma base temporal.
    archivos = [p for paquete in PAQUETES for p in (RAIZ / paquete).rglob("*.py")]
    sys._sia_firma_codigo = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in archivos if p.exists()))
    prueba = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=90)
    return prueba


def _textos(at) -> str:
    return "\n".join(m.value for m in at.markdown) + "\n".join(c.value for c in at.caption)


def _campo(at, etiqueta):
    return next(t for t in at.text_input if t.label == etiqueta)


def _boton(at, etiqueta):
    return next(b for b in at.button if b.label == etiqueta)


def _ingresar(at, usuario, clave):
    _campo(at, "Usuario").input(usuario)
    _campo(at, "Contraseña").input(clave)
    _boton(at, "Ingresar").click().run()


def test_login_sin_crear_cuenta(app):
    app.run()
    assert not app.exception
    assert all(t.label != "Crear cuenta" for t in app.tabs)
    assert "Iniciar sesión" in _textos(app)
    assert "Crear mi acceso de estudiante" not in [e.label for e in app.expander]
    etiquetas = [t.label for t in app.text_input]
    assert etiquetas == ["Usuario", "Contraseña"]
    assert any(c.label == "Recordarme en este dispositivo" for c in app.checkbox)


def test_login_con_clave_temporal_obliga_a_cambiarla(app, institucion):
    from models import cuentas

    alta = cuentas.crear_o_asignar(institucion.id, "docente", "30111222", "Laura", "Gómez", "laura@ejemplo.com")
    app.run()
    _ingresar(app, "30111222", alta.clave_temporal)
    assert not app.exception
    assert "Creá tu contraseña" in _textos(app)
    assert "Panel docente" not in _textos(app)
    # La misma clave temporal no se acepta como nueva
    _campo(app, "Nueva contraseña").input(alta.clave_temporal)
    _campo(app, "Repetir la nueva contraseña").input(alta.clave_temporal)
    _boton(app, "Guardar y entrar a mi panel").click().run()
    assert any("distinta de la temporal" in e.value for e in app.error)
    _campo(app, "Nueva contraseña").input("MiClaveNueva2026")
    _campo(app, "Repetir la nueva contraseña").input("MiClaveNueva2026")
    _boton(app, "Guardar y entrar a mi panel").click().run()
    assert not app.exception
    assert "Panel docente" in _textos(app)
    app.run()  # la sesión se mantiene en las siguientes ejecuciones
    assert "Panel docente" in _textos(app)


def test_qr_de_invitacion_lleva_directo_a_crear_contrasena(app, institucion):
    from models import cuentas
    from models.persona import RepositorioPersonas

    alta = cuentas.crear_o_asignar(institucion.id, "docente", "30111222", "Laura", "Gómez", "laura@ejemplo.com")
    app.query_params["invitacion"] = alta.invitacion
    app.run()
    assert not app.exception
    assert "Creá tu contraseña" in _textos(app)
    _campo(app, "Nueva contraseña").input("MiClaveNueva2026")
    _campo(app, "Repetir la nueva contraseña").input("MiClaveNueva2026")
    _boton(app, "Guardar y entrar a mi panel").click().run()
    assert "Panel docente" in _textos(app)
    assert not RepositorioPersonas.debe_cambiar_password(alta.persona.id)


def test_qr_de_invitacion_usado_muestra_aviso(app, institucion):
    from models import cuentas

    alta = cuentas.crear_o_asignar(institucion.id, "docente", "30111222", "Laura", "Gómez", "laura@ejemplo.com")
    cuentas.canjear_invitacion(alta.invitacion)
    app.query_params["invitacion"] = alta.invitacion
    app.run()
    assert not app.exception
    assert any("ya se usó" in w.value for w in app.warning)
    assert "Iniciar sesión" in _textos(app)


def test_alumno_sin_cuenta_crea_su_acceso_desde_el_qr_de_la_clase(app, institucion):
    from core.database import get_connection
    from models import cuentas
    from models.asistencia import RegistroAsistencia

    docente = cuentas.crear_o_asignar(institucion.id, "docente", "30111222", "Laura", "Gómez", "l@ejemplo.com").persona
    materia = crear_materia(docente.id, institucion.id)
    clase_id = materia.abrir_clase("Unidad 1")
    app.query_params["asistencia"] = RegistroAsistencia(clase_id).generar_token()
    app.run()
    assert not app.exception
    assert "Crear mi acceso de estudiante" in [e.label for e in app.expander]
    for etiqueta, valor in (("Nombre *", "Ana"), ("Apellido *", "Pérez"), ("DNI *", "45111222"),
                            ("Email *", "ana@ejemplo.com"), ("Contraseña *", "Clave2026x"),
                            ("Repetir contraseña *", "Clave2026x")):
        _campo(app, etiqueta).input(valor)
    _boton(app, "Crear acceso y continuar").click().run()
    assert not app.exception
    assert "Hola, Ana" in _textos(app)
    with get_connection() as conn:
        presentes = conn.execute("SELECT COUNT(*) FROM asistencias WHERE clase_id = ?", (clase_id,)).fetchone()[0]
        inscripto = conn.execute("SELECT COUNT(*) FROM inscripciones WHERE materia_id = ?", (materia.id,)).fetchone()[0]
    assert presentes == 1 and inscripto == 1


def test_preceptoria_da_de_alta_un_docente_con_qr(app, institucion):
    from core import sesiones
    from models import cuentas
    from models.institucion import tiene_rol
    from models.persona import RepositorioPersonas

    pre = cuentas.crear_o_asignar(institucion.id, "preceptor", "28111222", "Marta", "Díaz", "marta@ejemplo.com").persona
    RepositorioPersonas.guardar_password(pre, "Preceptoria2026")
    docente = cuentas.crear_o_asignar(institucion.id, "docente", "30888111", "Alex", "Téllez", "alex@ejemplo.com").persona
    sesiones.crear(docente.id, institucion.id, "docente")
    app.run()
    _ingresar(app, "28111222", "Preceptoria2026")
    assert not app.exception
    textos = _textos(app)
    assert "Panel de Preceptoría" in textos and "Docentes" in [t.label for t in app.tabs]
    _campo(app, "DNI *").input("30555666")
    _campo(app, "Nombre").input("Pablo")
    _campo(app, "Apellido").input("Ruiz")
    _campo(app, "Email").input("pablo@ejemplo.com")
    _boton(app, "Dar de alta y generar invitación").click().run()
    assert not app.exception
    nuevo = RepositorioPersonas.por_dni("30555666")
    assert nuevo is not None and tiene_rol(nuevo.id, institucion.id, "docente")
    assert RepositorioPersonas.debe_cambiar_password(nuevo.id)
    assert "Acceso creado: Pablo Ruiz" in _textos(app)
    assert "QR de invitación: un solo uso" in _textos(app)
    assert any(b.label == "Descargar QR" for b in app.get("download_button"))
    _campo(app, "Buscar docente por DNI o apellido").input("30555666").run()
    assert not app.exception
    assert "sin actividad registrada" in _textos(app)


@pytest.mark.parametrize("rol, titulo", [("directivo", "Panel de Rectoría · Dirección"), ("estudiante", "Hola, Ana")])
def test_paneles_cargan_sin_errores(app, institucion, rol, titulo):
    from models import cuentas
    from models.persona import RepositorioPersonas

    persona = cuentas.crear_o_asignar(institucion.id, rol, "33111222", "Ana", "Sosa", "ana.s@ejemplo.com").persona
    RepositorioPersonas.guardar_password(persona, "ClaveSegura2026")
    app.run()
    _ingresar(app, "33111222", "ClaveSegura2026")
    assert not app.exception
    assert titulo in _textos(app)


def test_superadmin_ingresa_con_dni_y_clave_inicial(app, monkeypatch):
    monkeypatch.setenv("SIA_SUPERADMINS", "20111222")
    monkeypatch.setenv("SIA_SUPERADMIN_CLAVE_INICIAL", "ClaveInicial2026")
    app.run()
    _ingresar(app, "20111222", "ClaveInicial2026")
    assert "Creá tu contraseña" in _textos(app)
    _campo(app, "Nueva contraseña").input("AdminPropia2026")
    _campo(app, "Repetir la nueva contraseña").input("AdminPropia2026")
    _boton(app, "Guardar y entrar a mi panel").click().run()
    assert not app.exception
    assert "Administración general" in _textos(app)
    assert {"Instituciones", "Usuarios y roles", "Sistema"} <= {t.label for t in app.tabs}
