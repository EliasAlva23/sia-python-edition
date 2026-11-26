"""Administración general del SaaS: instituciones (identidad, enlace ?i=, activación), altas de Preceptoría,
Dirección y demás roles institucionales, acceso de cualquier cuenta y parámetros del sistema."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.database import SCHEMA_VERSION, get_connection
from core.validaciones import TOLERANCIAS_TARDE
from models import cuentas
from models.institucion import (
    NOMBRES_ROL,
    OPCIONES,
    Institucion,
    asignar_rol,
    guardar_mensaje_sistema,
    guardar_opcion,
    mensaje_sistema,
    opcion,
    quitar_rol,
)
from models.persona import Persona, RepositorioPersonas
from utils.qr import url_app
from views import personal
from views.config_institucion import form_identidad, form_umbrales
from views.styles import (
    ESTADO,
    PALETAS,
    encabezado,
    estado_html,
    kpi_grid,
    mostrar_errores,
    tabla_html,
)

PERSONALIZADA = "Personalizada"
ROLES_ASIGNABLES = ("estudiante", "docente", "preceptor", "directivo")


def render(admin: Persona) -> None:
    encabezado("Administración general", "Gestionás las instituciones, sus responsables y el sistema completo")
    todas = Institucion.todas(solo_activas=False)
    activas = sum(1 for i in todas if i.activa)
    with get_connection() as conn:
        usuarios = conn.execute("SELECT COUNT(*) FROM usuarios WHERE activo = 1").fetchone()[0]
        preceptoria = conn.execute("SELECT COUNT(*) FROM membresias WHERE rol = 'preceptor'").fetchone()[0]
    kpi_grid([
        ("Instituciones activas", activas, f"de {len(todas)} en total", "neutro", 100 * activas / len(todas) if todas else 0),
        ("Personas con cuenta", usuarios, "en todas las instituciones", "neutro"),
        ("Preceptoría", preceptoria, "personas asignadas", "neutro" if preceptoria else "ambar"),
    ])
    tabs = st.tabs(["Instituciones", "Usuarios y roles", "Sistema"])
    with tabs[0]:
        _instituciones()
    with tabs[1]:
        _usuarios(admin)
    with tabs[2]:
        _sistema()


# ---------------------------------------------------------------- instituciones
def _estadisticas() -> pd.DataFrame:
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT i.id,
                      (SELECT COUNT(*) FROM membresias m WHERE m.institucion_id = i.id AND m.rol = 'estudiante') AS estudiantes,
                      (SELECT COUNT(*) FROM membresias m WHERE m.institucion_id = i.id AND m.rol <> 'estudiante') AS personal,
                      (SELECT COUNT(*) FROM materias m WHERE m.institucion_id = i.id AND m.activa = 1) AS materias
               FROM instituciones i"""
        ).fetchall()
    return pd.DataFrame([dict(f) for f in filas], columns=["id", "estudiantes", "personal", "materias"]).set_index("id")


def _instituciones() -> None:
    todas = Institucion.todas(solo_activas=False)
    stats = _estadisticas()
    tabla_html(
        [{"nombre": i.nombre, "corto": i.nombre_corto, "enlace": f"{url_app()}/?i={i.slug}",
          "estado": estado_html("Activa" if i.activa else "Suspendida", ESTADO["bueno"] if i.activa else ESTADO["critico"]),
          "estudiantes": int(stats.loc[i.id, "estudiantes"]) if i.id in stats.index else 0,
          "personal": int(stats.loc[i.id, "personal"]) if i.id in stats.index else 0,
          "materias": int(stats.loc[i.id, "materias"]) if i.id in stats.index else 0} for i in todas],
        {"nombre": "Institución", "corto": "Nombre corto", "enlace": "Enlace de acceso", "estado": "Estado",
         "estudiantes": "Estudiantes", "personal": "Personal", "materias": "Materias"},
        vacio="Todavía no hay instituciones.",
    )
    st.caption("Cada institución tiene su enlace de acceso: la dirección de la app seguida de «?i=identificador». "
               "Quien ingresa por ese enlace ve el logo y los colores de su institución.")

    with st.expander("Dar de alta una institución", icon=":material/add_business:"):
        _alta_institucion()

    if not todas:
        return
    st.markdown("#### Editar una institución")
    por_id = {i.id: i for i in todas}
    elegida = st.selectbox("Institución", list(por_id), format_func=lambda i: por_id[i].nombre, key="sa_inst")
    inst = por_id[elegida]
    sub = st.tabs(["Identidad", "Configuración académica", "Estado"])
    with sub[0]:
        form_identidad(inst, f"sa_{inst.id}", permitir_slug=True)
    with sub[1]:
        form_umbrales(inst, f"sa_{inst.id}")
    with sub[2]:
        if inst.activa:
            st.write("Al suspenderla, nadie puede ingresar a esta institución y las sesiones abiertas se cierran.")
            if st.button("Suspender institución", key=f"sa_susp_{inst.id}"):
                inst.actualizar(activa=False)
                with get_connection() as conn:
                    conn.execute("DELETE FROM sesiones WHERE institucion_id = ?", (inst.id,))
                st.rerun()
        else:
            st.write("La institución está suspendida.")
            if st.button("Reactivar institución", type="primary", key=f"sa_act_{inst.id}"):
                inst.actualizar(activa=True)
                st.rerun()


def _alta_institucion() -> None:
    with st.form("sa_alta_inst", clear_on_submit=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        nombre = c1.text_input("Nombre completo *", placeholder="Instituto Superior N° 5", max_chars=150)
        corto = c2.text_input("Nombre corto *", placeholder="IS N° 5", max_chars=40)
        slug = c3.text_input("Identificador del enlace *", placeholder="is5", max_chars=31,
                             help="Queda como …/?i=is5: quien entra por ese enlace ve el logo y los colores.")
        p1, p2, p3 = st.columns(3)
        paleta = st.radio("Paleta", [*PALETAS, PERSONALIZADA], horizontal=True,
                          help="Combinaciones de la paleta institucional de SIA, o colores propios con «Personalizada».")
        primario = p1.color_picker("Color principal (personalizada)", "#2E5772")
        secundario = p2.color_picker("Color secundario (personalizada)", "#3F7C70")
        tolerancia = p3.selectbox("Tolerancia «tarde»", TOLERANCIAS_TARDE, index=1,
                                  format_func=lambda m: "Sin tolerancia" if m == 0 else f"{m} minutos")
        u1, u2 = st.columns(2)
        regular = u1.slider("Regularizar con (%)", 50, 100, 75, step=5)
        promocion = u2.slider("Promocionar con (%)", 50, 100, 80, step=5)
        director = st.text_input("DNI de la persona a cargo de Dirección (opcional, debe tener cuenta)", max_chars=10,
                                 help="Si todavía no tiene cuenta, dala de alta después desde «Usuarios y roles».")
        logo = st.file_uploader("Logo (opcional)", type=["png", "jpg", "jpeg", "webp"], key="sa_alta_logo")
        crear = st.form_submit_button("Crear institución", type="primary")
    if not crear:
        return
    if paleta != PERSONALIZADA:
        primario, secundario = PALETAS[paleta]
    try:
        inst = Institucion.crear(nombre=nombre, nombre_corto=corto, slug=slug.strip().lower(), color_primario=primario,
                                 color_secundario=secundario, umbral_regular=regular, umbral_promocion=promocion,
                                 tolerancia_tarde=tolerancia)
        if logo is not None:
            inst.guardar_logo(logo.getvalue(), logo.type)
    except ValueError as exc:
        mostrar_errores(str(exc).split("\n"))
        return
    aviso = ""
    if director.strip():
        persona = RepositorioPersonas.por_dni(director)
        if persona:
            asignar_rol(persona.id, inst.id, "directivo")
            aviso = f" {persona.nombre_completo} quedó a cargo de Dirección."
        else:
            aviso = " No se encontró una cuenta con ese DNI: asigná Dirección desde «Usuarios y roles»."
    st.success(f"Institución creada. Enlace de acceso: {url_app()}/?i={inst.slug}.{aviso}")


# ---------------------------------------------------------------- usuarios
def _usuarios(admin: Persona) -> None:
    activas = Institucion.todas()
    personal.tarjeta_credencial("sa_alta")
    if activas:
        with st.expander("Dar de alta Preceptoría, Dirección o docentes", icon=":material/person_add:"):
            por_id = {i.id: i for i in activas}
            elegida = st.selectbox("Institución", list(por_id), format_func=lambda i: por_id[i].nombre, key="sa_alta_inst")
            personal.form_alta(por_id[elegida], ("preceptor", "directivo", "docente"), "sa_alta", admin.id,
                               titulo=f"Alta en {por_id[elegida].nombre_corto}")
    st.markdown("#### Buscar una persona")
    dni = st.text_input("DNI", max_chars=10, key="sa_dni", placeholder="Ingresá el DNI y presioná Enter")
    if not dni.strip():
        st.caption("Las cuentas son personales (una por DNI) y pueden tener roles en varias instituciones. "
                   "La Administración general se otorga solo desde los Secrets del despliegue (SIA_SUPERADMINS).")
        return
    persona = RepositorioPersonas.por_dni(dni)
    if persona is None:
        st.warning("No hay una cuenta con ese DNI. Dala de alta con «Dar de alta Preceptoría, Dirección o docentes».")
        return
    with get_connection() as conn:
        filas = conn.execute(
            """SELECT m.institucion_id, i.nombre, m.rol, m.creado_en FROM membresias m
               JOIN instituciones i ON i.id = m.institucion_id WHERE m.usuario_id = ? ORDER BY i.nombre, m.rol""",
            (persona.id,),
        ).fetchall()
        sesiones = conn.execute("SELECT COUNT(*) FROM sesiones WHERE usuario_id = ?", (persona.id,)).fetchone()[0]
    st.markdown(f"**{persona.nombre_completo}** · DNI {persona.dni} · {persona.email}")
    kpi_grid([("Roles", len(filas), "en todas las instituciones", "neutro"),
              ("Sesiones abiertas", sesiones, "", "neutro")])
    tabla_html([{"inst": f["nombre"], "rol": NOMBRES_ROL[f["rol"]], "desde": (f["creado_en"] or "")[:10]} for f in filas],
               {"inst": "Institución", "rol": "Rol", "desde": "Desde"}, vacio="Sin roles asignados.")
    instituciones = {i.id: i.nombre for i in Institucion.todas(solo_activas=False)}
    c1, c2 = st.columns(2)
    with c1, st.form(f"sa_asignar_{persona.id}"):
        st.markdown("##### Asignar rol")
        inst = st.selectbox("Institución", list(instituciones), format_func=instituciones.get)
        rol = st.selectbox("Rol", ROLES_ASIGNABLES, format_func=NOMBRES_ROL.get)
        if st.form_submit_button("Asignar", type="primary"):
            st.toast("Rol asignado" if asignar_rol(persona.id, inst, rol) else "Ya tenía ese rol")
            st.rerun()
    with c2:
        if filas:
            with st.form(f"sa_quitar_{persona.id}"):
                st.markdown("##### Quitar rol")
                opciones = [(f["institucion_id"], f["rol"]) for f in filas]
                elegido = st.selectbox("Rol", opciones,
                                       format_func=lambda o: f"{instituciones.get(o[0], '')} · {NOMBRES_ROL[o[1]]}")
                if st.form_submit_button("Quitar"):
                    quitar_rol(persona.id, *elegido)
                    st.toast("Rol quitado")
                    st.rerun()
        if sesiones and st.button("Cerrar todas sus sesiones", key=f"sa_cerrar_{persona.id}"):
            with get_connection() as conn:
                conn.execute("DELETE FROM sesiones WHERE usuario_id = ?", (persona.id,))
            st.rerun()
        if persona.id != admin.id and st.button("Restablecer acceso (clave temporal)", key=f"sa_reset_{persona.id}",
                                                icon=":material/key:",
                     help="Genera una clave temporal de cambio obligatorio y cierra sus sesiones."):
            inst_id, rol = (filas[0]["institucion_id"], filas[0]["rol"]) if filas else (None, None)
            temporal, token = cuentas.restablecer_clave(persona.id, inst_id, rol, admin.id)
            personal.guardar_credencial("sa_alta", persona, rol or "superadmin", temporal, token,
                                        Institucion.obtener(inst_id), motivo="restablecer")
            st.rerun()


# ---------------------------------------------------------------- sistema
def _sistema() -> None:
    st.markdown("#### Funciones habilitadas")
    with st.form("sa_opciones"):
        valores = {clave: st.toggle(texto, value=opcion(clave), key=f"sa_op_{clave}")
                   for clave, (texto, _) in OPCIONES.items()}
        if st.form_submit_button("Guardar funciones", type="primary"):
            for clave, valor in valores.items():
                guardar_opcion(clave, valor)
            st.toast("Funciones actualizadas")
            st.rerun()

    st.markdown("#### Aviso para todos los usuarios")
    with st.form("sa_mensaje"):
        texto = st.text_area("Mensaje (se muestra arriba de cada panel; vacío para ocultarlo)", value=mensaje_sistema(),
                             max_chars=300, height=80)
        if st.form_submit_button("Publicar aviso"):
            guardar_mensaje_sistema(texto)
            st.rerun()

    st.markdown("#### Estado de la base de datos")
    with get_connection() as conn:
        conteos = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                   for t in ("instituciones", "usuarios", "membresias", "materias", "clases", "asistencias",
                             "justificativos", "sesiones")}
    kpi_grid([("Esquema", f"v{SCHEMA_VERSION}", "", "neutro"),
              ("Usuarios", conteos["usuarios"], f"{conteos['membresias']} roles", "neutro"),
              ("Clases", conteos["clases"], f"{conteos['asistencias']} asistencias", "neutro"),
              ("Sesiones abiertas", conteos["sesiones"], "", "neutro")])
    tabla_html([{"tabla": t, "filas": n} for t, n in conteos.items()], {"tabla": "Tabla", "filas": "Registros"})
