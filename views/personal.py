"""Altas del personal y credenciales temporales (compartido por Preceptoría, Dirección y Administración general).

Al dar de alta a alguien sin cuenta, el sistema genera:
  * Usuario: su DNI.
  * Clave temporal: se muestra una sola vez; al ingresar, el sistema obliga a cambiarla.
  * QR de invitación: un solo uso, vence a las 72 h. Escaneado con el celular abre directo «Creá tu contraseña».
"""
from __future__ import annotations

from html import escape

import streamlit as st

from core import validaciones as val
from models import cuentas
from models.institucion import NOMBRES_ROL, Institucion
from models.persona import Persona, RepositorioPersonas
from utils.qr import contenido_invitacion, generar_qr_png
from views.styles import aviso, mostrar_errores

_CLAVE_CREDENCIAL = "_credencial_{}"


def guardar_credencial(clave: str, persona: Persona, rol: str, temporal: str | None, token: str | None,
                       institucion: Institucion | None, motivo: str = "alta") -> None:
    """Deja la credencial visible hasta que quien la entrega confirme que ya la pasó (sobrevive a otros clics)."""
    st.session_state[_CLAVE_CREDENCIAL.format(clave)] = {
        "nombre": persona.nombre_completo, "dni": persona.dni, "rol": rol, "temporal": temporal, "token": token,
        "institucion": institucion.nombre_corto if institucion else "", "motivo": motivo,
    }


def tarjeta_credencial(clave: str) -> None:
    """Muestra usuario, clave temporal y QR de invitación de la última alta o restablecimiento."""
    datos = st.session_state.get(_CLAVE_CREDENCIAL.format(clave))
    if not datos:
        return
    with st.container(border=True, key=f"sia_credencial_{clave}"):
        titulo = "Acceso restablecido" if datos["motivo"] == "restablecer" else "Acceso creado"
        st.markdown(f"#### {titulo}: {escape(datos['nombre'])}")
        st.caption(f"{NOMBRES_ROL.get(datos['rol'], datos['rol'])} · {datos['institucion']}. Esta información se "
                   "muestra una sola vez: entregala ahora en persona o por un medio privado.")
        texto, qr = st.columns([1.3, 1], vertical_alignment="center")
        with texto:
            aviso(f"<b>Usuario:</b> {escape(datos['dni'])} (su DNI)<br>"
                  f"<b>Clave temporal:</b> <span class='sia-code'>{escape(datos['temporal'] or '—')}</span><br>"
                  "Al ingresar, el sistema le pide crear su propia contraseña.")
            if datos["token"]:
                enlace = contenido_invitacion(datos["token"])
                st.caption(f"QR de invitación: un solo uso, vence en {cuentas.HORAS_INVITACION} horas. "
                           "Al escanearlo con el celular entra directo a crear su contraseña.")
                st.code(enlace, language=None)
        if datos["token"]:
            with qr:
                png = generar_qr_png(contenido_invitacion(datos["token"]), box_size=7, color="#142033")
                st.image(png, caption="QR de invitación", width=220)
                st.download_button("Descargar QR", generar_qr_png(contenido_invitacion(datos["token"]), box_size=14,
                                                                 color="#142033"),
                                   file_name=f"invitacion_{datos['dni']}.png", mime="image/png",
                                   key=f"dl_inv_{clave}", icon=":material/download:", width="stretch")
        if st.button("Listo, ya lo entregué", key=f"cerrar_cred_{clave}", icon=":material/check:"):
            st.session_state.pop(_CLAVE_CREDENCIAL.format(clave), None)
            st.rerun()


def form_alta(institucion: Institucion, roles: tuple[str, ...], clave: str, creado_por: int | None,
              titulo: str = "Dar de alta", boton: str = "Dar de alta y generar invitación") -> None:
    """Alta con DNI. Si la persona ya tiene cuenta (por ejemplo, en otra institución) solo se le asigna el rol."""
    with st.form(f"form_alta_{clave}", clear_on_submit=True):
        st.markdown(f"##### {escape(titulo)}")
        st.caption("Si la persona ya tiene cuenta alcanza con el DNI. Si no, completá sus datos: el sistema crea "
                   "su usuario, una clave temporal y un QR de invitación.")
        f1 = st.columns(2)
        dni = f1[0].text_input("DNI *", max_chars=10, help="Solo números, sin puntos.")
        if len(roles) > 1:
            rol = f1[1].selectbox("Rol *", roles, format_func=NOMBRES_ROL.get)
        else:
            rol = roles[0]
            f1[1].text_input("Rol", value=NOMBRES_ROL[rol], disabled=True)
        f2 = st.columns(2)
        nombre = f2[0].text_input("Nombre")
        apellido = f2[1].text_input("Apellido")
        email = st.text_input("Email", placeholder="nombre@correo.com")
        enviar = st.form_submit_button(boton, type="primary", width="stretch")
    if not enviar:
        return
    errores = val.requeridos({"DNI": dni})
    if not errores and (e := val.error_dni(dni)):
        errores.append(e)
    if errores:
        mostrar_errores(errores)
        return
    if RepositorioPersonas.por_dni(dni) is None:
        errores = val.requeridos({"Nombre": nombre, "Apellido": apellido, "Email": email})
        errores += [e for e in (val.error_nombre(nombre, "Nombre"), val.error_nombre(apellido, "Apellido"),
                                val.error_email(email)) if e]
        if errores:
            mostrar_errores(["No hay una cuenta con ese DNI: completá nombre, apellido y email.", *errores])
            return
    try:
        alta = cuentas.crear_o_asignar(institucion.id, rol, dni, val.limpiar(nombre), val.limpiar(apellido),
                                       email.strip(), creado_por=creado_por)
    except ValueError as exc:
        mostrar_errores([str(exc)])
        return
    if alta.clave_temporal:
        guardar_credencial(clave, alta.persona, rol, alta.clave_temporal, alta.invitacion, institucion)
        st.rerun()
    elif alta.rol_nuevo:
        st.success(f"{alta.persona.nombre_completo} ya tenía cuenta: ahora también es {NOMBRES_ROL[rol]} en "
                   f"{institucion.nombre_corto}. Ingresa con su DNI y su contraseña de siempre.")
    else:
        st.info(f"{alta.persona.nombre_completo} ya era {NOMBRES_ROL[rol]} en {institucion.nombre_corto}.")
