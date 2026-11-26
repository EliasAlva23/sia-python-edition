"""Acceso: login, registro, selección de institución y de perfil, y sesión persistente (sobrevive a F5)."""
from __future__ import annotations

import hmac
import json
from html import escape

import streamlit as st

from core import sesiones
from core import validaciones as val
from core.security import config_valor
from models.institucion import (
    NOMBRES_ROL,
    Institucion,
    asignar_rol,
    es_superadmin,
    opcion,
    roles_de,
)
from models.persona import Docente, Estudiante, Persona, RepositorioPersonas
from views.styles import (
    CLAVE_TEMA,
    aviso,
    configurar_tema,
    mostrar_errores,
    panel_login,
    titulo_login,
)

MINUTOS_INACTIVIDAD = sesiones.MINUTOS_INACTIVIDAD
_CLAVES_PERSISTENTES = (CLAVE_TEMA, "accion_pendiente", "inst_login")
COOKIE_INSTITUCION = "sia_inst"


# ---------------------------------------------------------------- cookies (se escriben por JavaScript)
def _programar_cookie(nombre: str, valor: str | None, segundos: int) -> None:
    pendientes = st.session_state.setdefault("_cookies_pendientes", {})
    pendientes[nombre] = (valor, segundos)


def sincronizar_cookies() -> None:
    """Escribe en el navegador las cookies pendientes (se llama en cada ejecución, después de un posible rerun)."""
    pendientes = st.session_state.pop("_cookies_pendientes", None)
    if not pendientes:
        return
    instrucciones = []
    for nombre, (valor, segundos) in pendientes.items():
        contenido = f"{nombre}=" + (valor or "") + f"; path=/; max-age={segundos if valor else 0}; SameSite=Lax"
        instrucciones.append(f"document.cookie = {json.dumps(contenido)} + (location.protocol === 'https:' ? '; Secure' : '');")
    st.html("<script>" + "".join(instrucciones) + "</script>", unsafe_allow_javascript=True)


# ---------------------------------------------------------------- estado de sesión
def _limpiar_estado() -> None:
    for clave in list(st.session_state.keys()):
        if clave not in _CLAVES_PERSISTENTES and not str(clave).startswith("_cookies"):
            del st.session_state[clave]


def _abrir_contexto(usuario_id: int, institucion_id: int | None, rol: str, token: str) -> None:
    st.session_state.update(usuario_id=usuario_id, usuario_rol=rol, institucion_id=institucion_id, sesion_token=token)
    configurar_tema(Institucion.obtener(institucion_id))


def iniciar_sesion(persona: Persona, institucion_id: int | None, rol: str) -> None:
    pendientes = st.session_state.get("_cookies_pendientes")
    _limpiar_estado()  # evita mezclar datos entre usuarios
    if pendientes:
        st.session_state["_cookies_pendientes"] = pendientes
    token = sesiones.crear(persona.id, institucion_id, rol)
    _abrir_contexto(persona.id, institucion_id, rol, token)
    _programar_cookie(sesiones.NOMBRE_COOKIE, token, sesiones.HORAS_MAXIMAS * 3600)
    if institucion_id:
        inst = Institucion.obtener(institucion_id)
        _programar_cookie(COOKIE_INSTITUCION, inst.slug, 365 * 24 * 3600)


def cambiar_perfil(institucion_id: int | None, rol: str) -> None:
    token = st.session_state.get("sesion_token")
    if not token:
        return
    sesiones.cambiar_contexto(token, institucion_id, rol)
    usuario_id = st.session_state["usuario_id"]
    pendientes = st.session_state.get("_cookies_pendientes")
    _limpiar_estado()
    if pendientes:
        st.session_state["_cookies_pendientes"] = pendientes
    _abrir_contexto(usuario_id, institucion_id, rol, token)


def cerrar_sesion(motivo: str | None = None) -> None:
    sesiones.cerrar(st.session_state.get("sesion_token"))
    _limpiar_estado()
    st.session_state.pop("accion_pendiente", None)
    _programar_cookie(sesiones.NOMBRE_COOKIE, None, 0)
    if motivo:
        st.session_state["aviso_sesion"] = motivo


def registrar_actividad() -> None:
    sesiones.tocar(st.session_state.get("sesion_token"))


def perfiles_disponibles(persona: Persona) -> list[tuple[Institucion | None, str]]:
    perfiles: list[tuple[Institucion | None, str]] = list(roles_de(persona.id))
    if es_superadmin(persona.dni):
        perfiles.append((None, "superadmin"))
    return perfiles


def _perfil_valido(usuario_id: int, institucion_id: int | None, rol: str) -> bool:
    persona = RepositorioPersonas.obtener(usuario_id)
    return persona is not None and (institucion_id, rol) in [((i.id if i else None), r) for i, r in perfiles_disponibles(persona)]


def _cookie(nombre: str) -> str | None:
    """Valor de una cookie del navegador (solo texto: fuera de un navegador real puede no existir)."""
    try:
        valor = st.context.cookies.get(nombre)
    except Exception:
        return None
    return valor if isinstance(valor, str) and valor else None


def usuario_actual() -> Persona | None:
    """Sesión activa: la de memoria o, tras recargar la página, la que indica la cookie."""
    token = st.session_state.get("sesion_token")
    if token is None:
        token = _cookie(sesiones.NOMBRE_COOKIE)
        if not token:
            return None
        datos = sesiones.validar(token)
        if datos is None:
            _programar_cookie(sesiones.NOMBRE_COOKIE, None, 0)
            return None
        _abrir_contexto(datos["usuario_id"], datos["institucion_id"], datos["rol"], token)
    elif sesiones.validar(token) is None:
        cerrar_sesion(f"Tu sesión expiró tras {MINUTOS_INACTIVIDAD} minutos sin actividad. Volvé a ingresar.")
        return None
    usuario_id, rol, institucion_id = (st.session_state["usuario_id"], st.session_state["usuario_rol"],
                                       st.session_state.get("institucion_id"))
    if not _perfil_valido(usuario_id, institucion_id, rol):
        cerrar_sesion("Tu acceso a ese perfil ya no está disponible.")
        return None
    if "_tema" not in st.session_state or st.session_state["_tema"].get("id") != institucion_id:
        configurar_tema(Institucion.obtener(institucion_id))
    return RepositorioPersonas.obtener(usuario_id, rol)


# ---------------------------------------------------------------- institución de la pantalla de acceso
def institucion_de_acceso() -> Institucion | None:
    """Institución elegida para el login: ?i=slug en el enlace, cookie o selección previa."""
    slug = st.query_params.get("i")
    if slug:
        inst = Institucion.por_slug(slug)
        if inst:
            st.session_state["inst_login"] = inst.id
            _programar_cookie(COOKIE_INSTITUCION, inst.slug, 365 * 24 * 3600)
        del st.query_params["i"]
    if "inst_login" not in st.session_state:
        inst = Institucion.por_slug(_cookie(COOKIE_INSTITUCION))
        activas = Institucion.todas()
        if inst is None and len(activas) == 1:
            inst = activas[0]
        if inst:
            st.session_state["inst_login"] = inst.id
    return Institucion.obtener(st.session_state.get("inst_login"))


def render_acceso() -> None:
    institucion = institucion_de_acceso()
    configurar_tema(institucion)
    from views.styles import inyectar_css

    inyectar_css()  # recolorea la pantalla con la identidad de la institución elegida
    mensaje = st.session_state.pop("aviso_sesion", None)

    marca, formulario = st.columns([1, 1.05], gap="large", vertical_alignment="center")
    with marca:
        panel_login([
            "Asistencia por QR, PIN o registro de Preceptoría",
            "Historial y condición de cada alumno en tiempo real",
            "Alertas tempranas de riesgo de regularidad",
        ])
    with formulario:
        if mensaje:
            st.warning(mensaje)
        institucion = _selector_institucion(institucion)
        pendiente = st.session_state.get("accion_pendiente")
        if pendiente and pendiente.get("error"):
            st.session_state.pop("accion_pendiente", None)
            st.error(pendiente["error"])
        elif pendiente:
            accion = "registrar tu presente" if pendiente["tipo"] == "asistencia" else "inscribirte en la materia"
            aviso(f"<b>{escape(pendiente['descripcion'])}</b><br>Ingresá o creá tu cuenta de estudiante: al terminar "
                  f"vamos a {accion} automáticamente.")
        if st.session_state.get("_login_perfiles"):
            _elegir_perfil()
            return
        titulo_login("Te damos la bienvenida", "Ingresá con tu DNI o email. Si es tu primera vez, creá tu cuenta.")
        tab_login, tab_registro = st.tabs(["Ingresar", "Crear cuenta"])
        with tab_login:
            _form_login(institucion)
        with tab_registro:
            _form_registro(institucion)


def _selector_institucion(actual: Institucion | None) -> Institucion | None:
    activas = Institucion.todas()
    if len(activas) <= 1:
        return actual or (activas[0] if activas else None)
    por_id = {i.id: i for i in activas}
    indice = list(por_id).index(actual.id) if actual and actual.id in por_id else None
    elegida = st.selectbox("Institución", list(por_id), index=indice, format_func=lambda i: por_id[i].nombre,
                           placeholder="Elegí tu institución", key="selector_institucion_login")
    if elegida and elegida != st.session_state.get("inst_login"):
        st.session_state["inst_login"] = elegida
        _programar_cookie(COOKIE_INSTITUCION, por_id[elegida].slug, 365 * 24 * 3600)
        st.rerun()
    return por_id.get(elegida)


def _form_login(institucion: Institucion | None) -> None:
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
        st.error(mensaje)
        return
    perfiles = perfiles_disponibles(persona)
    if institucion and not any(i and i.id == institucion.id for i, _ in perfiles):
        # Un estudiante de otra institución puede vincularse; el personal lo asigna la dirección.
        if any(r == "estudiante" for _, r in perfiles) or persona.rol == "estudiante":
            asignar_rol(persona.id, institucion.id, "estudiante")
            perfiles = perfiles_disponibles(persona)
    if not perfiles:
        st.error("Tu cuenta no tiene acceso a ninguna institución activa. Consultá con la dirección.")
        return
    en_esta = [(i, r) for i, r in perfiles if institucion and i and i.id == institucion.id]
    candidatos = en_esta or perfiles
    if len(candidatos) == 1:
        inst, rol = candidatos[0]
        iniciar_sesion(persona, inst.id if inst else None, rol)
        st.rerun()
    st.session_state["_login_perfiles"] = {"usuario_id": persona.id,
                                          "perfiles": [((i.id if i else None), r) for i, r in perfiles]}
    st.rerun()


def _elegir_perfil() -> None:
    datos = st.session_state["_login_perfiles"]
    persona = RepositorioPersonas.obtener(datos["usuario_id"])
    opciones = [tuple(p) for p in datos["perfiles"]]
    st.markdown(f"### Hola, {escape(persona.nombre)}")
    st.caption("Tu cuenta tiene más de un perfil. Elegí con cuál querés ingresar; después podés cambiarlo desde la barra lateral.")
    elegido = st.radio("Ingresar como", opciones, format_func=lambda p: etiqueta_perfil(*p), key="perfil_login")
    c1, c2 = st.columns(2)
    if c1.button("Continuar", type="primary", width="stretch"):
        st.session_state.pop("_login_perfiles", None)
        iniciar_sesion(persona, elegido[0], elegido[1])
        st.rerun()
    if c2.button("Volver", width="stretch"):
        st.session_state.pop("_login_perfiles", None)
        st.rerun()


def etiqueta_perfil(institucion_id: int | None, rol: str) -> str:
    if institucion_id is None:
        return NOMBRES_ROL[rol]
    inst = Institucion.obtener(institucion_id)
    return f"{NOMBRES_ROL[rol]} · {inst.nombre_corto if inst else ''}"


def _form_registro(institucion: Institucion | None) -> None:
    if institucion is None:
        st.info("Elegí tu institución para crear la cuenta.")
        return
    tipos = [t for t, ok in (("Estudiante", opcion("registro_estudiantes")), ("Docente", opcion("registro_docentes"))) if ok]
    if not tipos:
        st.info("El registro está deshabilitado. Pedí el alta a la dirección de tu institución.")
        return
    rol = st.radio("Tipo de cuenta", tipos, horizontal=True, key="registro_rol")
    codigo_docente = institucion.codigo_docente or config_valor("SIA_DOCENTE_CODE")
    with st.form("form_registro", clear_on_submit=False):
        # Una fila por par de campos: en celulares el orden queda Nombre → Apellido → DNI → Email → …
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
        fila3 = st.columns(2)
        password = fila3[0].text_input("Contraseña *", type="password", help="Mínimo 8 caracteres con letras y números.")
        confirmar = fila3[1].text_input("Repetir contraseña *", type="password")
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
    errores += [e for e in (val.error_nombre(nombre, "Nombre"), val.error_nombre(apellido, "Apellido"),
                            val.error_dni(dni), val.error_email(email)) if e]
    errores += val.largo_maximo({"Nombre": (nombre, 80), "Apellido": (apellido, 80)})
    errores += val.errores_password(password, confirmar)
    if rol == "Docente" and codigo_docente and invitacion and not hmac.compare_digest(invitacion.strip(), codigo_docente):
        errores.append("Código de alta docente incorrecto.")
    if errores:
        mostrar_errores(errores)
        return
    try:
        datos = (dni, val.limpiar(nombre), val.limpiar(apellido), email.strip())
        persona: Persona = (Docente(*datos, departamento=val.limpiar(extra)) if rol == "Docente"
                            else Estudiante(*datos, legajo=val.limpiar(extra)))
        persona.establecer_password(password)
        RepositorioPersonas.registrar(persona)
    except ValueError as exc:
        mensaje = str(exc)
        if "Ya existe" in mensaje:
            mensaje += " Si ya tenés cuenta (por ejemplo, en otra institución), ingresá con tu contraseña."
        mostrar_errores([mensaje])
        return
    rol_clave = "docente" if rol == "Docente" else "estudiante"
    asignar_rol(persona.id, institucion.id, rol_clave)
    iniciar_sesion(persona, institucion.id, rol_clave)
    st.rerun()


def render_cambio_password(persona: Persona) -> None:
    with st.popover("Cambiar contraseña", width="stretch"):
        with st.form("form_cambio_pw", clear_on_submit=True):
            actual = st.text_input("Contraseña actual", type="password")
            nueva = st.text_input("Nueva contraseña", type="password")
            repetir = st.text_input("Repetir nueva", type="password")
            if st.form_submit_button("Actualizar", width="stretch"):
                errores = val.requeridos({"Contraseña actual": actual, "Nueva contraseña": nueva, "Repetir nueva": repetir})
                errores += val.errores_password(nueva, repetir)
                if errores:
                    mostrar_errores(errores)
                else:
                    try:
                        RepositorioPersonas.cambiar_password(persona, actual, nueva)
                        sesiones.cerrar_todas(persona.id)
                        st.session_state.pop("sesion_token", None)
                        st.success("Contraseña actualizada. Volvé a ingresar.")
                    except ValueError as exc:
                        st.error(str(exc))
