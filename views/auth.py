"""Login, registro y gestión de la sesión (st.session_state con expiración)."""
from __future__ import annotations

import hmac
import time

import streamlit as st

from core.security import config_valor
from models.persona import Docente, Estudiante, Persona, RepositorioPersonas
from views.styles import hero

MINUTOS_INACTIVIDAD = int(config_valor("SIA_SESSION_MINUTES", "30"))
HORAS_MAXIMAS = 8
_CLAVES_SESION = ("usuario_id", "usuario_rol", "login_ts", "ultima_actividad")


def iniciar_sesion(persona: Persona) -> None:
    # Limpiamos cualquier estado previo para no mezclar datos entre usuarios.
    for clave in list(st.session_state.keys()):
        del st.session_state[clave]
    ahora = time.time()
    st.session_state.update(
        usuario_id=persona.id, usuario_rol=persona.rol, login_ts=ahora, ultima_actividad=ahora
    )


def cerrar_sesion(motivo: str | None = None) -> None:
    for clave in list(st.session_state.keys()):
        del st.session_state[clave]
    if motivo:
        st.session_state["aviso_sesion"] = motivo


def registrar_actividad() -> None:
    if "usuario_id" in st.session_state:
        st.session_state["ultima_actividad"] = time.time()


def usuario_actual() -> Persona | None:
    """Valida la sesión (inactividad, duración máxima y existencia del usuario)."""
    if not all(k in st.session_state for k in _CLAVES_SESION):
        return None
    ahora = time.time()
    if ahora - st.session_state["ultima_actividad"] > MINUTOS_INACTIVIDAD * 60:
        cerrar_sesion("Tu sesión expiró por inactividad. Volvé a ingresar.")
        return None
    if ahora - st.session_state["login_ts"] > HORAS_MAXIMAS * 3600:
        cerrar_sesion("Tu sesión alcanzó la duración máxima. Volvé a ingresar.")
        return None
    persona = RepositorioPersonas.obtener(st.session_state["usuario_id"])
    if persona is None or persona.rol != st.session_state["usuario_rol"]:
        cerrar_sesion("Tu cuenta ya no está disponible.")
        return None
    registrar_actividad()
    return persona


def minutos_restantes() -> int:
    restante = MINUTOS_INACTIVIDAD * 60 - (time.time() - st.session_state.get("ultima_actividad", 0))
    return max(0, int(restante // 60))


def render_acceso() -> None:
    hero("SIA · Sistema de Asistencia Inteligente", "Python Edition — asistencia por QR, ciencia de datos e IA predictiva")
    aviso = st.session_state.pop("aviso_sesion", None)
    if aviso:
        st.warning(aviso)

    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        tab_login, tab_registro = st.tabs(["🔐 Ingresar", "📝 Crear cuenta"])
        with tab_login:
            _form_login()
        with tab_registro:
            _form_registro()


def _form_login() -> None:
    with st.form("form_login"):
        identificador = st.text_input("DNI o email")
        password = st.text_input("Contraseña", type="password")
        enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
    if enviar:
        persona, mensaje = RepositorioPersonas.autenticar(identificador, password)
        if persona is None:
            st.error(mensaje)
        else:
            iniciar_sesion(persona)
            st.rerun()


def _form_registro() -> None:
    rol = st.radio("Tipo de cuenta", ["Estudiante", "Docente"], horizontal=True, key="registro_rol")
    codigo_docente = config_valor("SIA_DOCENTE_CODE")
    with st.form("form_registro", clear_on_submit=False):
        c1, c2 = st.columns(2)
        nombre = c1.text_input("Nombre")
        apellido = c2.text_input("Apellido")
        dni = c1.text_input("DNI", help="Solo números, sin puntos.")
        email = c2.text_input("Email")
        if rol == "Estudiante":
            extra = st.text_input("Legajo (opcional)")
        else:
            extra = st.text_input("Departamento / Área (opcional)")
        p1, p2 = st.columns(2)
        password = p1.text_input("Contraseña", type="password", help="Mínimo 8 caracteres con letras y números.")
        confirmar = p2.text_input("Repetir contraseña", type="password")
        invitacion = ""
        if rol == "Docente" and codigo_docente:
            invitacion = st.text_input("Código de alta docente", type="password",
                                       help="Lo provee la institución.")
        enviar = st.form_submit_button("Crear cuenta", type="primary", width="stretch")

    if not enviar:
        return
    if password != confirmar:
        st.error("Las contraseñas no coinciden.")
        return
    if rol == "Docente" and codigo_docente and not hmac.compare_digest(invitacion, codigo_docente):
        st.error("Código de alta docente incorrecto.")
        return
    try:
        if rol == "Docente":
            persona: Persona = Docente(dni, nombre, apellido, email, departamento=extra)
        else:
            persona = Estudiante(dni, nombre, apellido, email, legajo=extra)
        persona.establecer_password(password)
        RepositorioPersonas.registrar(persona)
    except ValueError as exc:
        st.error(str(exc))
        return
    iniciar_sesion(persona)
    st.rerun()


def render_cambio_password(persona: Persona) -> None:
    with st.popover("🔑 Cambiar contraseña", width="stretch"):
        with st.form("form_cambio_pw", clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password")
            nueva = st.text_input("Nueva contraseña", type="password")
            repetir = st.text_input("Repetir nueva", type="password")
            if st.form_submit_button("Actualizar", width="stretch"):
                if nueva != repetir:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        RepositorioPersonas.cambiar_password(persona, actual, nueva)
                        st.success("Contraseña actualizada.")
                    except ValueError as exc:
                        st.error(str(exc))
