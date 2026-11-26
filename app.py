"""SIA · Sistema de Asistencia Inteligente (SaaS multi-institución) — punto de entrada de Streamlit.

Ejecutar:  streamlit run app.py
Enlace por institución:  https://<app>/?i=<identificador>   (ej. ?i=ies11)
Invitación del personal:  https://<app>/?invitacion=<token de un solo uso>  (QR que genera Preceptoría)
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

    Al actualizar el repositorio, Streamlit Cloud vuelve a ejecutar app.py pero puede conservar en memoria las
    versiones anteriores de views/, models/, etc.; si el app.py nuevo pide un nombre que el módulo viejo no
    tiene, aparece un ImportError. Si cambió la fecha de modificación de algún .py, se descartan.
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

st.set_page_config(
    page_title="SIA · Sistema de Asistencia Inteligente",
    page_icon=str(_RAIZ / "static" / "icon-192.png") if (_RAIZ / "static" / "icon-192.png").exists() else None,
    layout="wide",
    initial_sidebar_state="auto",
)

from core.database import asegurar_esquema  # noqa: E402
from models.asistencia import RegistroAsistencia  # noqa: E402
from models.institucion import NOMBRES_ROL, mensaje_sistema  # noqa: E402
from models.materia import Materia  # noqa: E402
from views import alumno, auth, directivo, docente, preceptor, superadmin  # noqa: E402
from views.pwa import inyectar_pwa  # noqa: E402
from views.styles import footer, inyectar_css, marca_sidebar, selector_tema  # noqa: E402

PANELES = {"estudiante": alumno, "docente": docente, "preceptor": preceptor, "directivo": directivo,
           "superadmin": superadmin}


def _capturar_enlace_qr() -> None:
    """QR escaneado con la cámara nativa del celular: abre la app con ?asistencia= o ?inscribir=.

    El token de asistencia se valida AHORA (al abrir el enlace), así el alumno puede iniciar sesión con calma
    sin que expire la ventana de 30 s del QR dinámico.
    """
    parametros = st.query_params
    if "invitacion" in parametros:
        token = parametros["invitacion"]
        del st.query_params["invitacion"]
        auth.abrir_invitacion(token)
        return
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
    for clave in ("asistencia", "inscribir", "f"):
        if clave in st.query_params:
            del st.query_params[clave]


def _barra_lateral(persona) -> None:
    with st.sidebar:
        marca_sidebar()
        rol = st.session_state["usuario_rol"]
        st.markdown(f'<div class="sia-usuario"><b>{escape(persona.nombre_completo)}</b>'
                    f'<span>{escape(NOMBRES_ROL[rol])} · DNI {escape(persona.dni)}</span></div>', unsafe_allow_html=True)
        perfiles = [((i.id if i else None), r) for i, r in auth.perfiles_disponibles(persona)]
        actual = (st.session_state.get("institucion_id"), rol)
        if len(perfiles) > 1 and actual in perfiles:
            elegido = st.selectbox("Perfil", perfiles, index=perfiles.index(actual),
                                   format_func=lambda p: auth.etiqueta_perfil(*p), key="selector_perfil")
            if elegido != actual:
                auth.cambiar_perfil(*elegido)
                st.rerun()
        selector_tema()


def _pie_barra_lateral(persona) -> None:
    with st.sidebar:
        st.divider()
        auth.render_cambio_password(persona)
        if st.button("Cerrar sesión", width="stretch", key="btn_cerrar_sesion"):
            auth.cerrar_sesion("Cerraste sesión correctamente.")
            st.rerun()
        st.caption(f"La sesión se cierra tras {auth.MINUTOS_INACTIVIDAD} min sin actividad. "
                   "Recargar la página no la cierra.")


def main() -> None:
    try:
        asegurar_esquema()  # siempre antes de cualquier consulta (login, cookies, enlace ?i=)
    except Exception as exc:  # noqa: BLE001 - se informa en pantalla en lugar de caer con un traceback
        st.error("No se pudo preparar la base de datos. Reintentá en unos segundos; si persiste, "
                 "avisá a la administración del sistema.")
        st.caption(f"Detalle técnico: {type(exc).__name__}: {exc}")
        st.stop()
    _capturar_enlace_qr()
    persona = auth.usuario_actual()
    if persona is None:
        auth.render_acceso()  # aplica la identidad de la institución elegida
    elif auth.debe_cambiar_password(persona):
        inyectar_css()
        auth.render_cambio_obligatorio(persona)  # primer ingreso o clave restablecida: antes que cualquier panel
    else:
        inyectar_css()
        _barra_lateral(persona)
        aviso = mensaje_sistema()
        if aviso:
            st.info(aviso)
        rol = st.session_state["usuario_rol"]
        if rol != "estudiante" and st.session_state.pop("accion_pendiente", None):
            st.warning("Abriste un QR pensado para estudiantes. Para usarlo, ingresá con un perfil de estudiante.")
        PANELES[rol].render(persona)
        _pie_barra_lateral(persona)
    footer()
    auth.sincronizar_cookies()
    inyectar_pwa()


main()
