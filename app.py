"""SIA Python Edition — punto de entrada de Streamlit.

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

from html import escape

import streamlit as st

st.set_page_config(
    page_title="SIA · Asistencia Inteligente",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

from core.database import init_db  # noqa: E402
from views import alumno, auth, docente  # noqa: E402
from views.styles import badge, inyectar_css  # noqa: E402


@st.cache_resource(show_spinner=False)
def _inicializar_db() -> bool:
    init_db()
    return True


def _sidebar(persona) -> None:
    with st.sidebar:
        st.markdown("## 🎓 SIA")
        st.caption("Sistema de Asistencia Inteligente · Python Edition")
        st.markdown(
            f'<div class="sia-card"><b>{escape(persona.nombre_completo)}</b><br>'
            f'<span style="color:#64748B;font-size:.85rem">DNI {persona.dni}</span><br><br>'
            f'{badge(persona.rol.capitalize(), "indigo" if persona.rol == "docente" else "cian")}</div>',
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


def main() -> None:
    _inicializar_db()
    inyectar_css()
    persona = auth.usuario_actual()
    if persona is None:
        auth.render_acceso()
        return
    _sidebar(persona)
    if persona.rol == "docente":
        docente.render(persona)
    else:
        alumno.render(persona)
    _sidebar_pie(persona)


main()
