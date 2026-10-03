"""SIA Python Edition (Instituto de Educación Superior N° 11) — punto de entrada de Streamlit.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import sys
import time
from html import escape
from pathlib import Path

import streamlit as st

_RAIZ = Path(__file__).resolve().parent
_PAQUETES_PROPIOS = ("core", "models", "utils", "views")


def _descartar_modulos_desactualizados() -> None:
    """Fuerza a reimportar los módulos del proyecto cuando su código cambió.

    Al actualizar el repositorio, Streamlit Cloud vuelve a ejecutar app.py pero puede conservar en memoria
    las versiones anteriores de views/, models/, etc. Si app.py nuevo pide un nombre que el módulo viejo no
    tiene, aparece un ImportError (p. ej. `cannot import name 'TITULO_APP'`). Comparamos la fecha de
    modificación de los .py con la registrada en la ejecución anterior y, si cambió, los descartamos.
    """
    archivos = [p for paquete in _PAQUETES_PROPIOS for p in (_RAIZ / paquete).rglob("*.py")]
    firma = tuple(sorted((str(p), p.stat().st_mtime_ns) for p in archivos if p.exists()))
    if getattr(sys, "_sia_firma_codigo", None) != firma:
        for nombre, modulo in list(sys.modules.items()):
            archivo = getattr(modulo, "__file__", None) or ""
            if nombre.split(".")[0] in _PAQUETES_PROPIOS and archivo.startswith(str(_RAIZ)):
                del sys.modules[nombre]
        sys._sia_firma_codigo = firma


_descartar_modulos_desactualizados()

try:
    from views.styles import TITULO_APP
except ImportError:  # respaldo: la app arranca aunque el módulo de estilos esté desactualizado
    TITULO_APP = "SIA · IES N° 11"

st.set_page_config(
    page_title=f"{TITULO_APP} · Asistencia Inteligente",
    page_icon=str(_RAIZ / "static" / "icon-192.png") if (_RAIZ / "static" / "icon-192.png").exists() else "🎓",
    layout="wide",
    initial_sidebar_state="auto",
)

from core.database import init_db  # noqa: E402
from models.asistencia import RegistroAsistencia  # noqa: E402
from models.materia import Materia  # noqa: E402
from views import alumno, auth, docente  # noqa: E402
from views.pwa import inyectar_pwa  # noqa: E402
from views.styles import badge, footer, inyectar_css, marca_sidebar, selector_tema  # noqa: E402


@st.cache_resource(show_spinner=False)
def _inicializar_db() -> bool:
    init_db()
    return True


def _capturar_enlace_qr() -> None:
    """QR escaneado con la cámara nativa del celular: abre la app con ?asistencia= o ?inscribir=.

    El token de asistencia se valida AHORA (al abrir el enlace), así el alumno puede iniciar
    sesión con calma sin que expire la ventana de 30 s del QR dinámico.
    """
    parametros = st.query_params
    if "asistencia" in parametros:
        clase_id, error = RegistroAsistencia.validar_token_clase(parametros["asistencia"])
        accion = {"tipo": "asistencia", "clase_id": clase_id, "error": error,
                  "descripcion": "Escaneaste el QR de asistencia de una clase."}
    elif "inscribir" in parametros:
        codigo = parametros["inscribir"].strip().upper()
        valido = Materia.verificar_payload_inscripcion(codigo, parametros.get("f", ""))
        accion = {"tipo": "inscripcion", "codigo": codigo,
                  "error": None if valido else "El QR de inscripción no es válido o el código fue regenerado.",
                  "descripcion": "Escaneaste el QR de inscripción a una materia."}
    else:
        return
    accion["capturado"] = time.time()
    st.session_state["accion_pendiente"] = accion
    st.query_params.clear()


def _sidebar(persona) -> None:
    with st.sidebar:
        st.markdown(
            f'<div class="sia-card"><b>{escape(persona.nombre_completo)}</b><br>'
            f'<span class="sia-muted">DNI {escape(persona.dni)}</span><br><br>'
            f'{badge(persona.rol.capitalize(), "azul" if persona.rol == "docente" else "celeste")}</div>',
            unsafe_allow_html=True,
        )


def _sidebar_pie(persona) -> None:
    with st.sidebar:
        st.divider()
        auth.render_cambio_password(persona)
        if st.button("🚪 Cerrar sesión", width="stretch"):
            auth.cerrar_sesion("Cerraste sesión correctamente.")
            st.rerun()
        st.caption(f"La sesión expira tras {auth.MINUTOS_INACTIVIDAD} min de inactividad.")
        st.caption("Desarrollado por **Tech Innovation Team** — IES N° 11")


def main() -> None:
    _inicializar_db()
    _capturar_enlace_qr()
    inyectar_css()
    with st.sidebar:
        marca_sidebar()
        selector_tema()

    persona = auth.usuario_actual()
    if persona is None:
        auth.render_acceso()
    else:
        _sidebar(persona)
        if persona.rol == "docente":
            if st.session_state.pop("accion_pendiente", None):
                st.warning("📲 Abriste un QR pensado para estudiantes. Para usarlo, ingresá con una cuenta de estudiante.")
            docente.render(persona)
        else:
            alumno.render(persona)
        _sidebar_pie(persona)
    footer()
    inyectar_pwa()


main()
