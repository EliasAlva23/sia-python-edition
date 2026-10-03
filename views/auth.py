"""Login, registro y gestión de la sesión (st.session_state con expiración)."""
from __future__ import annotations

import hmac
import time
from html import escape

import streamlit as st

from core import validaciones as val
from core.security import config_valor
from models.persona import Docente, Estudiante, Persona, RepositorioPersonas
from views.styles import CLAVE_TEMA, INSTITUCION, TITULO_APP, aviso, hero, mostrar_errores

MINUTOS_INACTIVIDAD = int(config_valor("SIA_SESSION_MINUTES", "30"))
HORAS_MAXIMAS = 8
_CLAVES_SESION = ("usuario_id", "usuario_rol", "login_ts", "ultima_actividad")
# Se conservan al entrar/salir: preferencia de tema y acción QR escaneada antes de iniciar sesión.
_CLAVES_PERSISTENTES = (CLAVE_TEMA, "accion_pendiente")


def _limpiar_estado() -> None:
    for clave in list(st.session_state.keys()):
        if clave not in _CLAVES_PERSISTENTES:
            del st.session_state[clave]


def iniciar_sesion(persona: Persona) -> None:
    _limpiar_estado()  # evita mezclar datos entre usuarios
    ahora = time.time()
    st.session_state.update(
        usuario_id=persona.id, usuario_rol=persona.rol, login_ts=ahora, ultima_actividad=ahora
    )


def cerrar_sesion(motivo: str | None = None) -> None:
    _limpiar_estado()
    st.session_state.pop("accion_pendiente", None)
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


def render_acceso() -> None:
    hero(f"{TITULO_APP} · Sistema de Asistencia Inteligente",
         f"{INSTITUCION} — asistencia por QR, sábana digital y analítica predictiva")
    mensaje_sesion = st.session_state.pop("aviso_sesion", None)
    if mensaje_sesion:
        st.warning(mensaje_sesion)
    pendiente = st.session_state.get("accion_pendiente")
    if pendiente and pendiente.get("error"):
        # QR vencido o adulterado: avisamos ya, sin hacer iniciar sesión para nada.
        st.session_state.pop("accion_pendiente", None)
        st.error(f"⛔ {pendiente['error']}")
        pendiente = None

    _, centro, _ = st.columns([1, 2.2, 1])
    with centro:
        if pendiente:
            accion = ("registrar tu presente" if pendiente["tipo"] == "asistencia"
                      else "inscribirte en la materia")
            aviso(
                f"<b>📲 {escape(pendiente['descripcion'])}</b><br>"
                f"• Si ya tenés cuenta, ingresá en <b>🔐 Ingresar</b>.<br>"
                f"• Si es tu primera vez, completá <b>📝 Crear cuenta</b> (cuenta de estudiante).<br>"
                f"Al terminar vamos a {accion} automáticamente: no hace falta volver a escanear."
            )
        tab_login, tab_registro = st.tabs(["🔐 Ingresar", "📝 Crear cuenta"])
        with tab_login:
            _form_login()
        with tab_registro:
            _form_registro()


def _form_login() -> None:
    with st.form("form_login"):
        identificador = st.text_input("DNI o email", placeholder="Ej. 40111222 o nombre@correo.com")
        password = st.text_input("Contraseña", type="password")
        enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
    if not enviar:
        return
    errores = val.requeridos({"DNI o email": identificador, "Contraseña": password})
    if not errores and "@" not in identificador and (e := val.error_dni(identificador)):
        errores.append(e)
    if errores:
        mostrar_errores(errores)
        return
    persona, mensaje = RepositorioPersonas.autenticar(val.limpiar(identificador), password)
    if persona is None:
        st.error(mensaje, icon="⛔")
    else:
        iniciar_sesion(persona)
        st.rerun()


def _form_registro() -> None:
    rol = st.radio("Tipo de cuenta", ["Estudiante", "Docente"], horizontal=True, key="registro_rol")
    codigo_docente = config_valor("SIA_DOCENTE_CODE")
    with st.form("form_registro", clear_on_submit=False):
        # Una fila por par de campos (no una columna por lado): en celulares las columnas se apilan y así
        # el orden queda Nombre → Apellido → DNI → Email → Departamento/Legajo → Contraseña → Repetir.
        fila1 = st.columns(2)
        nombre = fila1[0].text_input("Nombre *")
        apellido = fila1[1].text_input("Apellido *")
        fila2 = st.columns(2)
        dni = fila2[0].text_input("DNI *", help="Solo números, sin puntos.", max_chars=10)
        email = fila2[1].text_input("Email *", placeholder="nombre@dominio.com")
        if rol == "Estudiante":
            extra = st.text_input("Legajo (opcional)", max_chars=30)
        else:
            extra = st.text_input("Departamento / Área (opcional)", max_chars=80)
        p1, p2 = st.columns(2)
        password = p1.text_input("Contraseña *", type="password", help="Mínimo 8 caracteres con letras y números.")
        confirmar = p2.text_input("Repetir contraseña *", type="password")
        invitacion = ""
        if rol == "Docente" and codigo_docente:
            invitacion = st.text_input("Código de alta docente *", type="password", help="Lo provee la institución.")
        enviar = st.form_submit_button("Crear cuenta", type="primary", width="stretch")

    if not enviar:
        return
    obligatorios = {"Nombre": nombre, "Apellido": apellido, "DNI": dni, "Email": email,
                    "Contraseña": password, "Repetir contraseña": confirmar}
    if rol == "Docente" and codigo_docente:
        obligatorios["Código de alta docente"] = invitacion
    errores = val.requeridos(obligatorios)
    errores += [e for e in (
        val.error_nombre(nombre, "Nombre"),
        val.error_nombre(apellido, "Apellido"),
        val.error_dni(dni),
        val.error_email(email),
    ) if e]
    errores += val.largo_maximo({"Nombre": (nombre, 80), "Apellido": (apellido, 80)})
    errores += val.errores_password(password, confirmar)
    if (rol == "Docente" and codigo_docente and invitacion
            and not hmac.compare_digest(invitacion.strip(), codigo_docente)):
        errores.append("Código de alta docente incorrecto.")
    if errores:
        mostrar_errores(errores)
        return
    try:
        datos = (dni, val.limpiar(nombre), val.limpiar(apellido), email.strip())
        if rol == "Docente":
            persona: Persona = Docente(*datos, departamento=val.limpiar(extra))
        else:
            persona = Estudiante(*datos, legajo=val.limpiar(extra))
        persona.establecer_password(password)
        RepositorioPersonas.registrar(persona)
    except ValueError as exc:
        mostrar_errores([str(exc)])
        return
    iniciar_sesion(persona)
    st.rerun()


def render_cambio_password(persona: Persona) -> None:
    # Desplegable (no popover): se muestra dentro del menú ☰, y Streamlit no permite un popover dentro de otro.
    with st.expander("🔑 Cambiar contraseña"):
        with st.form("form_cambio_pw", clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password")
            nueva = st.text_input("Nueva contraseña", type="password")
            repetir = st.text_input("Repetir nueva", type="password")
            if st.form_submit_button("Actualizar", width="stretch"):
                errores = val.requeridos({"Contraseña actual": actual, "Nueva contraseña": nueva,
                                          "Repetir nueva": repetir})
                errores += val.errores_password(nueva, repetir)
                if errores:
                    mostrar_errores(errores)
                else:
                    try:
                        RepositorioPersonas.cambiar_password(persona, actual, nueva)
                        st.success("Contraseña actualizada.")
                    except ValueError as exc:
                        st.error(str(exc))
