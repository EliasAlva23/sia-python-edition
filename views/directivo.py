"""Panel de Rectoría / Dirección general: vista ejecutiva, carreras, personal y configuración institucional."""
from __future__ import annotations

import secrets
from datetime import timedelta
from html import escape

import pandas as pd
import streamlit as st

from core import validaciones as val
from core.database import get_connection
from core.tiempo import hoy
from models.institucion import (
    NOMBRES_ROL,
    ROLES_PERSONAL,
    Institucion,
    asignar_rol,
    quitar_rol,
)
from models.materia import Materia
from models.persona import Directivo, Docente, Persona, Preceptor, RepositorioPersonas
from models.predictor_ia import PredictorRiesgoIA
from views import graficos
from views.config_institucion import form_identidad, form_umbrales
from views.exportar import exportaciones
from views.styles import (
    COLORES_CONDICION,
    COLORES_NIVEL,
    encabezado,
    estado_html,
    kpi_grid,
    mini_barra,
    mostrar_errores,
    tabla_html,
    tono_porcentaje,
)

PERIODOS = {"Últimos 30 días": 30, "Últimos 90 días": 90, "Todo el ciclo": None}
CLASES_PERSONAL = {"docente": Docente, "preceptor": Preceptor, "directivo": Directivo}


def render(directivo: Persona) -> None:
    inst = Institucion.obtener(st.session_state["institucion_id"])
    encabezado("Rectoría · Dirección general", "Vista ejecutiva de asistencia, regularidad y promoción")
    tabs = st.tabs(["Resumen institucional", "Carreras y materias", "Personal", "Configuración"])
    with tabs[0]:
        _resumen(inst)
    with tabs[1]:
        _carreras(inst)
    with tabs[2]:
        _personal(inst, directivo)
    with tabs[3]:
        st.markdown("#### Regularidad, promoción y llegada tarde")
        form_umbrales(inst, "dir")
        st.markdown("#### Identidad visual")
        form_identidad(inst, "dir")


# ---------------------------------------------------------------- datos institucionales
def _docentes(ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    with get_connection() as conn:
        filas = conn.execute(f"SELECT id, apellido || ', ' || nombre AS n FROM usuarios WHERE id IN ({marcas})", ids).fetchall()
    return {f["id"]: f["n"] for f in filas}


def _datos(inst: Institucion, dias: int | None) -> tuple[pd.DataFrame, pd.DataFrame, list[Materia]]:
    """Registros (alumno x clase) y resumen por alumno-materia con condición y riesgo."""
    materias = Materia.de_institucion(inst.id)
    df = Materia.registros_df([m.id for m in materias])
    if dias and not df.empty:
        df = df[df["fecha"] >= (hoy() - timedelta(days=dias)).isoformat()]
    if df.empty:
        return df, pd.DataFrame(), materias
    meta = {m.id: m for m in materias}
    carreras = {int(r.id): r.nombre for r in inst.carreras(solo_activas=False).itertuples()}
    docentes = _docentes(sorted({m.docente_id for m in materias}))
    df = df.assign(carrera=df["materia_id"].map(lambda i: carreras.get(meta[i].carrera_id, "Sin carrera")),
                   docente=df["materia_id"].map(lambda i: docentes.get(meta[i].docente_id, "")))
    prediccion = PredictorRiesgoIA(umbral=inst.umbral_regular).predecir(df)
    prediccion["materia_id"] = prediccion["clave"].str.split("-").str[0].astype(int)
    prediccion["condicion"] = [meta[m].condicion(p) for m, p in zip(prediccion["materia_id"], prediccion["pct_asistencia"], strict=True)]
    prediccion["carrera"] = prediccion["materia_id"].map(lambda i: carreras.get(meta[i].carrera_id, "Sin carrera"))
    return df, prediccion, materias


# ---------------------------------------------------------------- resumen ejecutivo
def _resumen(inst: Institucion) -> None:
    periodo = st.radio("Período", list(PERIODOS), horizontal=True, key="dir_periodo", label_visibility="collapsed")
    df, alumnos, materias = _datos(inst, PERIODOS[periodo])
    personas = inst.personas()
    if df.empty:
        kpi_grid([("Materias activas", len(materias), "", "neutro"),
                  ("Docentes", int((personas["rol"] == "docente").sum()), "", "neutro"),
                  ("Estudiantes", int((personas["rol"] == "estudiante").sum()), "", "neutro")])
        st.info("Todavía no hay clases registradas en el período elegido.")
        return
    promedio = 100 * df["presente"].mean()
    total = len(alumnos)
    cond = alumnos["condicion"].value_counts()
    riesgo = int((alumnos["nivel"] == "ALTO").sum())
    kpi_grid([
        ("Asistencia promedio", f"{promedio:.1f}%", f"{df['clase_id'].nunique()} clases dictadas",
         tono_porcentaje(promedio, inst.umbral_regular)),
        ("Promocionan", f"{100 * cond.get('Promociona', 0) / total:.0f}%", f"{cond.get('Promociona', 0)} de {total} cursadas", "verde"),
        ("Regulares", f"{100 * cond.get('Regular', 0) / total:.0f}%", f"umbral {inst.umbral_regular:.0f}%", "neutro"),
        ("Libres", f"{100 * cond.get('Libre', 0) / total:.0f}%", f"{cond.get('Libre', 0)} cursadas", "rojo" if cond.get("Libre", 0) else "neutro"),
        ("En riesgo alto", riesgo, "alumno-materia", "rojo" if riesgo else "verde"),
        ("Materias activas", len(materias), f"{df['estudiante_id'].nunique()} estudiantes con clases", "neutro"),
    ])

    c1, c2 = st.columns(2)
    with c1:
        por_carrera = df.groupby("carrera")["presente"].mean().mul(100).reset_index(name="asistencia")
        graficos.barras(por_carrera, "carrera", "asistencia", "Asistencia por carrera", umbral=inst.umbral_regular,
                        horizontal=True)
    with c2:
        conteos = alumnos.groupby(["carrera", "condicion"]).size().unstack(fill_value=0).reset_index()
        graficos.condicion_apilada(conteos, "carrera", "Condición de las cursadas por carrera")
    semanal = (df.assign(semana=pd.to_datetime(df["fecha"]).dt.to_period("W-SUN").dt.start_time)
                 .groupby("semana")["presente"].mean().mul(100).reset_index(name="asistencia"))
    graficos.tendencia(semanal, "semana", "asistencia", umbral=inst.umbral_regular, titulo="Asistencia institucional por semana")

    por_materia = (df.groupby(["materia_id", "materia", "docente", "carrera"])
                     .agg(asistencia=("presente", "mean"), clases=("clase_id", "nunique")).reset_index())
    por_materia["asistencia"] *= 100
    libres = alumnos[alumnos["condicion"] == "Libre"].groupby("materia_id").size()
    inscriptos = alumnos.groupby("materia_id").size()
    por_materia = por_materia.assign(libres=por_materia["materia_id"].map(libres).fillna(0).astype(int),
                                     inscriptos=por_materia["materia_id"].map(inscriptos).fillna(0).astype(int))
    peores = por_materia.nsmallest(12, "asistencia")
    graficos.barras(peores, "materia", "asistencia", "Materias con menor asistencia", umbral=inst.umbral_regular,
                    horizontal=True)

    st.markdown("#### Detalle por materia")
    tabla_html(
        [{"materia": f.materia, "carrera": f.carrera, "docente": f.docente,
          "asistencia": mini_barra(f.asistencia, tono_porcentaje(f.asistencia, inst.umbral_regular)),
          "inscriptos": f.inscriptos, "libres": f.libres, "clases": f.clases}
         for f in por_materia.sort_values("asistencia").itertuples()],
        {"materia": "Materia", "carrera": "Carrera", "docente": "Docente", "asistencia": "Asistencia",
         "inscriptos": "Alumnos", "libres": "Libres", "clases": "Clases"},
    )
    st.markdown("#### Alumnos en riesgo alto")
    altos = alumnos[alumnos["nivel"] == "ALTO"].sort_values("pct_asistencia")
    tabla_html(
        [{"alumno": f.alumno, "dni": f.dni, "materia": f.materia, "carrera": f.carrera,
          "condicion": estado_html(f.condicion, COLORES_CONDICION[f.condicion]),
          "riesgo": estado_html(f"{f.pct_asistencia:.0f}% · {f.motivos}", COLORES_NIVEL["ALTO"])} for f in altos.head(40).itertuples()],
        {"alumno": "Alumno/a", "dni": "DNI", "materia": "Materia", "carrera": "Carrera", "condicion": "Condición", "riesgo": "Motivo"},
        vacio="No hay alumnos en riesgo alto en el período.",
    )

    st.markdown("#### Reporte institucional")
    resumen_materias = por_materia.drop(columns=["materia_id"]).round({"asistencia": 1})
    detalle = alumnos[["carrera", "materia", "alumno", "dni", "pct_asistencia", "condicion", "nivel", "motivos"]].round(
        {"pct_asistencia": 1})
    exportaciones(f"reporte_institucional_{inst.slug}_{hoy():%Y%m%d}",
                  {"Materias": resumen_materias, "Alumnos": detalle}, "dir_export")


# ---------------------------------------------------------------- carreras
def _carreras(inst: Institucion) -> None:
    carreras = inst.carreras(solo_activas=False)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.markdown("#### Carreras")
        tabla_html([{"nombre": f.nombre, "estado": "Activa" if f.activa else "Inactiva", "docentes": f.docentes,
                     "materias": f.materias} for f in carreras.itertuples()],
                   {"nombre": "Carrera", "estado": "Estado", "docentes": "Docentes", "materias": "Materias"},
                   vacio="Todavía no hay carreras cargadas.")
    with c2:
        with st.form("form_carrera", clear_on_submit=True):
            st.markdown("##### Nueva carrera")
            nombre = st.text_input("Nombre", placeholder="Profesorado de Educación Primaria", max_chars=120)
            if st.form_submit_button("Agregar carrera", type="primary"):
                try:
                    inst.crear_carrera(nombre)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
        if not carreras.empty:
            with st.popover("Editar una carrera", width="stretch"):
                por_id = {int(f.id): f for f in carreras.itertuples()}
                elegida = st.selectbox("Carrera", list(por_id), format_func=lambda i: por_id[i].nombre, key="dir_car_ed")
                nuevo = st.text_input("Nombre", value=por_id[elegida].nombre, key=f"dir_car_nom_{elegida}")
                activa = st.checkbox("Activa", value=bool(por_id[elegida].activa), key=f"dir_car_act_{elegida}")
                if st.button("Guardar", key="dir_car_guardar"):
                    try:
                        inst.editar_carrera(elegida, nuevo, activa)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.rerun()

    st.markdown("#### Carreras de cada docente")
    docentes = inst.personas("docente")
    activas = {int(f.id): f.nombre for f in carreras.itertuples() if f.activa}
    if docentes.empty or not activas:
        st.caption("Cargá carreras y docentes para asignarlas.")
    else:
        nombres = {int(f.id): f"{f.apellido}, {f.nombre}" for f in docentes.itertuples()}
        c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
        docente = c1.selectbox("Docente", list(nombres), format_func=nombres.get, key="dir_doc")
        actuales = [c for c, _ in inst.carreras_de_docente(docente)]
        with c2.form(f"form_doc_car_{docente}"):
            elegidas = st.multiselect("Carreras asignadas", list(activas), default=actuales, format_func=activas.get)
            if st.form_submit_button("Guardar asignación", type="primary"):
                inst.asignar_carreras(docente, elegidas)
                st.toast("Carreras asignadas")
                st.rerun()
        filas = [{"docente": nombres[int(f.id)], "carreras": ", ".join(n for _, n in inst.carreras_de_docente(int(f.id))) or None,
                  "materias": len(Materia.de_docente(int(f.id), inst.id))} for f in docentes.itertuples()]
        tabla_html(filas, {"docente": "Docente", "carreras": "Carreras", "materias": "Materias"})


# ---------------------------------------------------------------- personal
def _personal(inst: Institucion, directivo: Persona) -> None:
    personal = inst.personas()
    personal = personal[personal["rol"].isin(ROLES_PERSONAL)]
    st.markdown("#### Personal de la institución")
    tabla_html([{"nombre": f"{f.apellido}, {f.nombre}", "dni": f.dni, "email": f.email, "rol": NOMBRES_ROL[f.rol]}
                for f in personal.itertuples()],
               {"nombre": "Nombre", "dni": "DNI", "email": "Email", "rol": "Rol"}, vacio="Todavía no hay personal cargado.")
    c1, c2 = st.columns(2)
    with c1:
        _alta_personal(inst)
    with c2:
        if not personal.empty:
            with st.form("form_quitar_rol"):
                st.markdown("##### Quitar un rol")
                opciones = [(int(f.id), f.rol) for f in personal.itertuples()]
                nombres = {(int(f.id), f.rol): f"{f.apellido}, {f.nombre} · {NOMBRES_ROL[f.rol]}" for f in personal.itertuples()}
                elegido = st.selectbox("Persona y rol", opciones, format_func=nombres.get)
                if st.form_submit_button("Quitar rol"):
                    if elegido == (directivo.id, "directivo"):
                        st.error("No podés quitarte tu propio rol de dirección.")
                    else:
                        quitar_rol(elegido[0], inst.id, elegido[1])
                        st.toast("Rol quitado")
                        st.rerun()


def _alta_personal(inst: Institucion) -> None:
    with st.form("form_alta_personal", clear_on_submit=True):
        st.markdown("##### Asignar un rol")
        st.caption("Si la persona ya tiene cuenta (por ejemplo, en otra institución) alcanza con el DNI. Si no, "
                   "completá sus datos y se crea con una contraseña temporal.")
        f1 = st.columns(2)
        dni = f1[0].text_input("DNI *", max_chars=10)
        rol = f1[1].selectbox("Rol *", ROLES_PERSONAL, format_func=NOMBRES_ROL.get)
        f2 = st.columns(2)
        nombre = f2[0].text_input("Nombre (solo cuentas nuevas)")
        apellido = f2[1].text_input("Apellido (solo cuentas nuevas)")
        email = st.text_input("Email (solo cuentas nuevas)")
        enviar = st.form_submit_button("Asignar", type="primary")
    if not enviar:
        return
    error = val.error_dni(dni) or (None if dni.strip() else "El DNI es obligatorio.")
    if error:
        st.error(error)
        return
    persona = RepositorioPersonas.por_dni(dni)
    temporal = None
    if persona is None:
        errores = val.requeridos({"Nombre": nombre, "Apellido": apellido, "Email": email})
        errores += [e for e in (val.error_nombre(nombre, "Nombre"), val.error_nombre(apellido, "Apellido"),
                                val.error_email(email)) if e]
        if errores:
            mostrar_errores(["No hay una cuenta con ese DNI: completá nombre, apellido y email.", *errores])
            return
        temporal = f"Sia{secrets.randbelow(900000) + 100000}{secrets.choice('abcdefghjkmnpqrstuvwxyz')}"
        try:
            persona = CLASES_PERSONAL[rol](dni, val.limpiar(nombre), val.limpiar(apellido), email.strip())
            persona.establecer_password(temporal)
            RepositorioPersonas.registrar(persona)
        except ValueError as exc:
            mostrar_errores([str(exc)])
            return
    nuevo = asignar_rol(persona.id, inst.id, rol)
    mensaje = f"{escape(persona.nombre_completo)}: rol {NOMBRES_ROL[rol]} " + ("asignado." if nuevo else "ya estaba asignado.")
    if temporal:
        mensaje += f" Cuenta creada. Contraseña temporal (se muestra una sola vez): **{temporal}**."
    st.success(mensaje)
