"""Acceso: login (sin registro público), invitaciones, selección de institución y de perfil, cambio obligatorio
de contraseña y sesión persistente (sobrevive a F5)."""
from __future__ import annotations

import json
import time
from html import escape

import streamlit as st

from core import sesiones
from core import validaciones as val
from models import cuentas
from models.asistencia import RegistroAsistencia
from models.institucion import (
    NOMBRES_ROL,
    Institucion,
    asignar_rol,
    es_superadmin,
    opcion,
    roles_de,
)
from models.materia import Materia
from models.persona import Persona, RepositorioPersonas
from views.styles import (
    CLAVE_TEMA,
    aviso,
    configurar_tema,
    inyectar_css,
    logo_html,
    mostrar_errores,
    panel_login,
    selector_tema,
    titulo_login,
)

MINUTOS_INACTIVIDAD = sesiones.MINUTOS_INACTIVIDAD
MINUTOS_ENLACE = 10  # tiempo para ingresar (o crear el acceso) después de escanear el QR de una clase
_CLAVES_PERSISTENTES = (CLAVE_TEMA, "accion_pendiente", "inst_login")
COOKIE_INSTITUCION = "sia_inst"


# ---------------------------------------------------------------- cookies (se escriben por JavaScript)
def _programar_cookie(nombre: str, valor: str | None, segundos: int | None) -> None:
    """segundos=None: cookie de sesión del navegador (se borra al cerrarlo)."""
    pendientes = st.session_state.setdefault("_cookies_pendientes", {})
    pendientes[nombre] = (valor, segundos)


def sincronizar_cookies() -> None:
    """Escribe en el navegador las cookies pendientes (se llama en cada ejecución, después de un posible rerun)."""
    pendientes = st.session_state.pop("_cookies_pendientes", None)
    if not pendientes:
        return
    instrucciones = []
    for nombre, (valor, segundos) in pendientes.items():
        duracion = "" if valor and segundos is None else f"; max-age={segundos if valor else 0}"
        contenido = f"{nombre}=" + (valor or "") + f"; path=/{duracion}; SameSite=Lax"
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


def iniciar_sesion(persona: Persona, institucion_id: int | None, rol: str, recordar: bool = True) -> None:
    pendientes = st.session_state.get("_cookies_pendientes")
    _limpiar_estado()  # evita mezclar datos entre usuarios
    if pendientes:
        st.session_state["_cookies_pendientes"] = pendientes
    token = sesiones.crear(persona.id, institucion_id, rol)
    _abrir_contexto(persona.id, institucion_id, rol, token)
    _programar_cookie(sesiones.NOMBRE_COOKIE, token, sesiones.HORAS_MAXIMAS * 3600 if recordar else None)
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
    """Pantalla de acceso: panel de bienvenida a la izquierda y formulario de ingreso a la derecha.

    No hay registro público: el personal entra con la invitación que le da Preceptoría y los estudiantes crean su
    acceso desde el QR de una clase.
    """
    institucion = institucion_de_acceso()
    configurar_tema(institucion)
    inyectar_css()  # recolorea la pantalla con la identidad de la institución elegida
    mensaje = st.session_state.pop("aviso_sesion", None)

    with st.container(key="sia_login"):
        marca, formulario = st.columns([1.08, 1], gap="small")
        with marca:
            panel_login([
                ("Dar el presente", "con el QR de la clase o un PIN de 6 dígitos"),
                ("Seguir tu asistencia", "materia por materia y en tiempo real"),
                ("Recibir avisos a tiempo", "antes de quedar libre en una materia"),
            ])
        with formulario, st.container(key="sia_login_form"):
            selector_tema("login")
            if mensaje:
                st.warning(mensaje)
            institucion = _selector_institucion(institucion)
            pendiente = _accion_pendiente_vigente()
            if st.session_state.get("_login_perfiles"):
                _elegir_perfil()
                return
            titulo_login("Iniciar sesión", "Ingresá con tu DNI (o tu email) y tu contraseña.")
            if pendiente:
                accion = "registrar tu presente" if pendiente["tipo"] == "asistencia" else "inscribirte en la materia"
                aviso(f"<b>{escape(pendiente['descripcion'])}</b><br>Ingresá y vamos a {accion} automáticamente.")
            _form_login(institucion)
            st.markdown(
                '<p class="sia-login-ayuda">¿Olvidaste tu contraseña o todavía no tenés acceso? '
                "Pedíselo a <b>Preceptoría</b> de tu institución: te da una clave temporal o un QR de invitación.</p>",
                unsafe_allow_html=True,
            )
            if pendiente:
                _registro_desde_clase(pendiente)


def _accion_pendiente_vigente() -> dict | None:
    """QR de clase o de inscripción escaneado antes de ingresar (si sigue vigente)."""
    pendiente = st.session_state.get("accion_pendiente")
    if not pendiente:
        return None
    if pendiente.get("error"):
        st.session_state.pop("accion_pendiente", None)
        st.error(pendiente["error"])
        return None
    if time.time() - pendiente.get("capturado", 0) > MINUTOS_ENLACE * 60:
        st.session_state.pop("accion_pendiente", None)
        st.warning("El QR que escaneaste venció. Volvé a escanearlo desde el aula.")
        return None
    return pendiente


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
    with st.form("form_login", border=False):
        identificador = st.text_input("Usuario", placeholder="Tu DNI (sin puntos) o tu email",
                                      autocomplete="username")
        password = st.text_input("Contraseña", type="password", placeholder="Tu contraseña",
                                 autocomplete="current-password")
        recordar = st.checkbox("Recordarme en este dispositivo", value=True,
                               help="Si lo desmarcás, la sesión se cierra al cerrar el navegador.")
        enviar = st.form_submit_button("Ingresar", type="primary", width="stretch")
    if not enviar:
        return
    errores = val.requeridos({"Usuario": identificador, "Contraseña": password})
    if not errores and "@" not in identificador and (e := val.error_dni(identificador)):
        errores.append(e)
    if errores:
        mostrar_errores(errores)
        return
    identificador = val.limpiar(identificador)
    if "@" not in identificador:
        cuentas.asegurar_superadmin(identificador, password)  # primer ingreso de la Administración general
    persona, mensaje = RepositorioPersonas.autenticar(identificador, password)
    if persona is None:
        st.error(mensaje)
        return
    perfiles = perfiles_disponibles(persona)
    if institucion and not any(i and i.id == institucion.id for i, _ in perfiles):
        # Un estudiante de otra institución puede vincularse; el personal lo asigna Preceptoría o Dirección.
        if any(r == "estudiante" for _, r in perfiles) or persona.rol == "estudiante":
            asignar_rol(persona.id, institucion.id, "estudiante")
            perfiles = perfiles_disponibles(persona)
    if not perfiles:
        st.error("Tu cuenta no tiene acceso a ninguna institución activa. Consultá con Preceptoría o Dirección.")
        return
    st.session_state["_recordar"] = recordar
    en_esta = [(i, r) for i, r in perfiles if institucion and i and i.id == institucion.id]
    candidatos = en_esta or perfiles
    if len(candidatos) == 1:
        inst, rol = candidatos[0]
        iniciar_sesion(persona, inst.id if inst else None, rol, recordar)
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
        iniciar_sesion(persona, elegido[0], elegido[1], st.session_state.pop("_recordar", True))
        st.rerun()
    if c2.button("Volver", width="stretch"):
        st.session_state.pop("_login_perfiles", None)
        st.rerun()


def etiqueta_perfil(institucion_id: int | None, rol: str) -> str:
    if institucion_id is None:
        return NOMBRES_ROL[rol]
    inst = Institucion.obtener(institucion_id)
    return f"{NOMBRES_ROL[rol]} · {inst.nombre_corto if inst else ''}"


def institucion_de_invitacion(pendiente: dict) -> Institucion | None:
    """Institución de la clase (o materia) del QR escaneado."""
    if pendiente["tipo"] == "asistencia":
        materia = Materia.obtener(RegistroAsistencia(pendiente["clase_id"]).materia_id() or 0)
    else:
        materia = Materia.por_codigo(pendiente["codigo"])
    return Institucion.obtener(materia.institucion_id) if materia and materia.institucion_id else None


def _registro_desde_clase(pendiente: dict) -> None:
    """Alta de estudiante SOLO desde la invitación de una clase (QR del docente), nunca desde el login suelto."""
    if not opcion("registro_estudiantes"):
        return
    institucion = institucion_de_invitacion(pendiente)
    if institucion is None or not institucion.activa:
        return
    st.markdown('<div class="sia-login-separador"><span>¿Es tu primera vez?</span></div>', unsafe_allow_html=True)
    with st.expander("Crear mi acceso de estudiante", icon=":material/person_add:"):
        st.caption(f"Te vas a registrar en {institucion.nombre}. Usá tu DNI real: con él vas a ingresar siempre.")
        with st.form("form_registro_clase", border=False):
            fila1 = st.columns(2)
            nombre = fila1[0].text_input("Nombre *", autocomplete="given-name")
            apellido = fila1[1].text_input("Apellido *", autocomplete="family-name")
            fila2 = st.columns(2)
            dni = fila2[0].text_input("DNI *", help="Solo números, sin puntos.", max_chars=10)
            email = fila2[1].text_input("Email *", placeholder="nombre@correo.com", autocomplete="email")
            legajo = st.text_input("Legajo (opcional)", max_chars=30)
            fila3 = st.columns(2)
            password = fila3[0].text_input("Contraseña *", type="password", autocomplete="new-password",
                                           help="Mínimo 8 caracteres, con letras y números.")
            confirmar = fila3[1].text_input("Repetir contraseña *", type="password", autocomplete="new-password")
            enviar = st.form_submit_button("Crear acceso y continuar", type="primary", width="stretch")
    if not enviar:
        return
    errores = val.requeridos({"Nombre": nombre, "Apellido": apellido, "DNI": dni, "Email": email,
                              "Contraseña": password, "Repetir contraseña": confirmar})
    errores += [e for e in (val.error_nombre(nombre, "Nombre"), val.error_nombre(apellido, "Apellido"),
                            val.error_dni(dni), val.error_email(email)) if e]
    errores += val.largo_maximo({"Nombre": (nombre, 80), "Apellido": (apellido, 80)})
    errores += val.errores_password(password, confirmar)
    if errores:
        mostrar_errores(errores)
        return
    try:
        estudiante = cuentas.registrar_estudiante(institucion.id, dni, val.limpiar(nombre), val.limpiar(apellido),
                                                  email.strip(), password, val.limpiar(legajo))
    except ValueError as exc:
        texto = str(exc)
        if "Ya existe" in texto:
            texto += " Si ya tenés cuenta, ingresá arriba con tu DNI y tu contraseña."
        mostrar_errores([texto])
        return
    iniciar_sesion(estudiante, institucion.id, "estudiante")
    st.rerun()


# ---------------------------------------------------------------- invitaciones y cambio obligatorio
def abrir_invitacion(token: str) -> None:
    """QR de invitación del personal: abre sesión y lleva a «Creá tu contraseña» (un solo uso)."""
    datos, error = cuentas.canjear_invitacion(token)
    persona = RepositorioPersonas.obtener(datos["usuario_id"]) if datos else None
    if persona is None:
        st.session_state["aviso_sesion"] = error or "La invitación ya no está vigente."
        return
    RepositorioPersonas.marcar_cambio_obligatorio(persona.id)
    iniciar_sesion(persona, datos["institucion_id"], datos["rol"])


def debe_cambiar_password(persona: Persona) -> bool:
    return RepositorioPersonas.debe_cambiar_password(persona.id)


def render_cambio_obligatorio(persona: Persona) -> None:
    """Primer ingreso (o clave restablecida): hay que crear una contraseña propia antes de ver el panel."""
    rol = st.session_state.get("usuario_rol", "")
    with st.container(key="sia_cambio"):
        st.markdown(
            f'<div class="sia-cambio-cabecera">{logo_html(52)}<div><span class="eyebrow">Paso único · '
            f"{escape(NOMBRES_ROL.get(rol, ''))}</span><h2>Hola, {escape(persona.nombre)}. Creá tu contraseña</h2>"
            f"<p>Estás usando una clave temporal. Elegí una propia para proteger tu cuenta; tu usuario es tu DNI "
            f"<b>{escape(persona.dni)}</b>.</p></div></div>",
            unsafe_allow_html=True,
        )
        with st.form("form_cambio_obligatorio", border=False):
            nueva = st.text_input("Nueva contraseña", type="password", autocomplete="new-password",
                                  help="Mínimo 8 caracteres, con letras y números.")
            repetir = st.text_input("Repetir la nueva contraseña", type="password", autocomplete="new-password")
            guardar = st.form_submit_button("Guardar y entrar a mi panel", type="primary", width="stretch")
        if guardar:
            errores = val.requeridos({"Nueva contraseña": nueva, "Repetir la nueva contraseña": repetir})
            errores += val.errores_password(nueva, repetir)
            if not errores and persona.verificar_password(nueva):
                errores.append("La nueva contraseña tiene que ser distinta de la temporal.")
            if errores:
                mostrar_errores(errores)
            else:
                RepositorioPersonas.guardar_password(persona, nueva)
                sesiones.cerrar_todas(persona.id, excepto=st.session_state.get("sesion_token"))
                st.toast("Contraseña guardada. ¡Bienvenido/a!")
                st.rerun()
        if st.button("Salir sin cambiarla", key="btn_salir_cambio"):
            cerrar_sesion()
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
                        sesiones.cerrar_todas(persona.id, excepto=st.session_state.get("sesion_token"))
                        st.success("Contraseña actualizada. Cerramos tus sesiones en otros dispositivos.")
                    except ValueError as exc:
                        st.error(str(exc))

