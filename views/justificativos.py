"""Carga, consulta y revisión de justificativos de inasistencia."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from core.tiempo import hoy
from models import justificativo as jus
from models.asistencia_docente import plantel_historico
from models.institucion import NOMBRES_ROL, Institucion
from models.materia import Materia
from views.personal import opciones_personas
from views.styles import ESTADO, estado_html, mostrar_errores, tabla_html

COLOR_ESTADO = {"pendiente": ESTADO["advertencia"], "aprobado": ESTADO["bueno"], "rechazado": ESTADO["critico"]}


def _periodo(fila) -> str:
    desde, hasta = (pd.to_datetime(fecha).strftime("%d/%m/%Y") for fecha in (fila.fecha_desde, fila.fecha_hasta))
    return desde if desde == hasta else f"{desde} al {hasta}"


def _detalle(filas, clave: str) -> None:
    if filas.empty:
        return
    opciones = {int(f.id): f"{f.alumno} · {f.materia} · {_periodo(f)}" for f in filas.itertuples()}
    with st.popover("Ver detalle", icon=":material/visibility:", key=f"{clave}_detalle",
                    on_change="rerun") as detalle:
        if not detalle.open:
            return
        elegido = st.selectbox("Justificativo", list(opciones), format_func=opciones.get, key=f"{clave}_ver")
        fila = filas.set_index("id").loc[elegido]
        st.caption(f"{NOMBRES_ROL[fila.rol]} · DNI {fila.dni} · {fila.estado.capitalize()}")
        st.text(fila.motivo)
        if fila.observacion:
            st.caption(f"Observación de revisión · {fila.observacion}")
        archivo = jus.archivo(elegido)
        if archivo is None:
            st.caption("Sin comprobante adjunto.")
            return
        nombre, contenido, mime = archivo
        if mime == "application/pdf" and contenido.startswith(b"%PDF-"):
            st.pdf(contenido, height=400, key=f"{clave}_pdf_{elegido}")
        elif mime.startswith("image/"):
            try:
                st.image(contenido, width="stretch")
            except (ValueError, OSError):
                st.warning("No se pudo mostrar la imagen.")
        st.download_button("Descargar comprobante", contenido, file_name=nombre, mime=mime,
                           key=f"{clave}_dl_{elegido}", icon=":material/download:")


def _tabla(filas, vacio: str) -> None:
    tabla_html(
        [{"persona": f.alumno, "rol": NOMBRES_ROL[f.rol], "materia": f.materia, "periodo": _periodo(f),
          "estado": estado_html(f.estado.capitalize(), COLOR_ESTADO[f.estado]), "obs": f.observacion or None}
         for f in filas.itertuples()],
        {"persona": "Persona", "rol": "Rol", "materia": "Materia", "periodo": "Período",
         "estado": "Estado", "obs": "Observación"},
        vacio=vacio,
    )


def bandeja(institucion: Institucion, usuario_id: int, docente_id: int | None = None, clave: str = "jus") -> None:
    filtros = {}
    if docente_id is None:
        c1, c2 = st.columns(2)
        docentes = opciones_personas(plantel_historico(institucion.id))
        alumnos = opciones_personas(institucion.personas("estudiante"))
        filtros["filtro_docente"] = c1.selectbox("Filtrar por docente", [None, *docentes], key=f"{clave}_doc",
                                                format_func=lambda i: docentes.get(i, "Todos"))
        filtros["filtro_alumno"] = c2.selectbox("Filtrar por alumno", [None, *alumnos], key=f"{clave}_alu",
                                               format_func=lambda i: alumnos.get(i, "Todos"))
    todos = jus.listar(institucion.id, docente_id=docente_id, **filtros)
    pendientes = todos[todos["estado"] == "pendiente"]
    st.markdown(f"#### Pendientes de revisión ({len(pendientes)})")
    _detalle(pendientes, f"{clave}_pend")
    if pendientes.empty:
        st.caption("No hay justificativos pendientes para esta selección.")
    else:
        opciones = {int(f.id): f"{f.alumno} · {NOMBRES_ROL[f.rol]} · {f.materia} · {_periodo(f)}"
                    for f in pendientes.itertuples()
                    if f.rol != "docente" or f.estudiante_id != usuario_id}
        if opciones:
            with st.form(f"{clave}_lote"):
                elegidos = st.multiselect("Justificativos a resolver", list(opciones), format_func=opciones.get)
                observacion = st.text_input("Observación para la persona (opcional)", max_chars=300)
                a1, a2 = st.columns(2)
                aprobar = a1.form_submit_button("Aprobar seleccionados", type="primary", width="stretch")
                rechazar = a2.form_submit_button("Rechazar seleccionados", width="stretch")
            if (aprobar or rechazar) and not elegidos:
                st.error("Seleccioná al menos un justificativo.")
            elif aprobar or rechazar:
                try:
                    registros = sum(jus.resolver(i, aprobar, usuario_id, observacion, docente_id=docente_id)
                                    for i in elegidos)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.toast(f"Justificativos resueltos · {registros} registros justificados" if aprobar
                             else "Justificativos rechazados")
                    st.rerun()
    with st.expander("Resueltos recientemente"):
        resueltos = todos[todos["estado"] != "pendiente"].sort_values("resuelto_en", ascending=False).head(30)
        _tabla(resueltos, "Todavía no hay justificativos resueltos para esta selección.")
        _detalle(resueltos, f"{clave}_res")


def formulario_personal(institucion_id: int, persona_id: int, materias: list[Materia], rol: str) -> None:
    docente = rol == "docente"
    with st.form(f"form_justificativo_{rol}", clear_on_submit=True):
        st.markdown("##### Presentar mi justificativo")
        nombres = {m.id: m.nombre for m in materias}
        general = "General" if docente else "Todas mis materias"
        materia = st.selectbox("Materia", [None, *nombres], format_func=lambda i: nombres.get(i, general))
        c1, c2 = st.columns(2)
        desde = c1.date_input("Desde", value=hoy(), max_value=hoy(), min_value=hoy() - timedelta(days=90),
                              format="DD/MM/YYYY")
        hasta = c2.date_input("Hasta", value=hoy(), max_value=hoy(), min_value=hoy() - timedelta(days=90),
                              format="DD/MM/YYYY")
        motivo = st.text_area("Motivo", placeholder="Ej. Turno médico, certificado adjunto.", max_chars=400, height=90)
        archivo = st.file_uploader("Comprobante (PDF o imagen, opcional)", type=["pdf", "png", "jpg", "jpeg", "webp"])
        if st.form_submit_button("Enviar justificativo", type="primary"):
            try:
                adjunto = (archivo.name, archivo.getvalue(), archivo.type) if archivo else None
                jus.crear(persona_id, institucion_id, materia, desde, hasta, motivo, persona_id, adjunto, rol=rol)
            except ValueError as exc:
                mostrar_errores(str(exc).split("\n"))
            else:
                revisor = "Preceptoría" if docente or materia is None else "Preceptoría o el docente de la materia"
                st.success(f"Justificativo enviado. Lo va a revisar {revisor}.")
    filtro = {"titular_docente": persona_id} if docente else {"estudiante_id": persona_id}
    mios = jus.listar(institucion_id, **filtro)
    st.markdown("##### Mis justificativos")
    _tabla(mios, "Todavía no presentaste justificativos.")
    _detalle(mios, f"{rol}_mios")
