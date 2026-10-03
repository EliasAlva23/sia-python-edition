"""SIA Python Edition (Instituto ISE) — punto de entrada de Streamlit.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import time
from html import escape

import streamlit as st

st.set_page_config(
    page_title="SIA · ISE · Asistencia Inteligente",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="auto",
)

from core.database import init_db  # noqa: E402
from models.asistencia import RegistroAsistencia  # noqa: E402
from models.materia import Materia  # noqa: E402
from views import alumno, auth, docente  # noqa: E402
from views.styles import badge, footer, inyectar_css, marca_sidebar, ruta_logo, selector_tema  # noqa: E402


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
        st.caption("Desarrollado por **Tech Innovation Team**")


def main() -> None:
    _inicializar_db()
    _capturar_enlace_qr()
    inyectar_css()
    logo = ruta_logo()
    if logo is not None and logo.suffix.lower() != ".svg":
        st.logo(str(logo), size="large")
    with st.sidebar:
        marca_sidebar()
        selector_tema()

    persona = auth.usuario_actual()
    if persona is None:
        auth.render_acceso()
    else:
        _sidebar(persona)
        if persona.rol == "docente":
            docente.render(persona)
        else:
            alumno.render(persona)
        _sidebar_pie(persona)
    footer()


main()
