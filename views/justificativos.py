"""Justificativos de inasistencia: bandeja de aprobación (Preceptoría / docente) y carga del alumno."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

from core.tiempo import hoy
from models import justificativo as jus
from models.materia import Materia
from views.styles import ESTADO, estado_html, mostrar_errores, tabla_html

COLOR_ESTADO = {"pendiente": ESTADO["advertencia"], "aprobado": ESTADO["bueno"], "rechazado": ESTADO["critico"]}


def _fecha(valor: str) -> str:
    return pd.to_datetime(valor).strftime("%d/%m/%Y")


def _periodo(fila) -> str:
    desde, hasta = _fecha(fila.fecha_desde), _fecha(fila.fecha_hasta)
    return desde if desde == hasta else f"{desde} al {hasta}"


def bandeja(institucion_id: int, usuario_id: int, docente_id: int | None = None, clave: str = "jus") -> None:
    """Pendientes de aprobación (con aprobación en lote) e historial de resueltos."""
    pendientes = jus.listar(institucion_id, "pendiente", docente_id=docente_id)
    st.markdown(f"#### Pendientes de revisión ({len(pendientes)})")
    if pendientes.empty:
        st.caption("No hay justificativos pendientes.")
    else:
        with st.form(f"{clave}_lote"):
            elegidos = []
            for fila in pendientes.itertuples():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1], vertical_alignment="center")
                    with c1:
                        st.markdown(f"**{fila.alumno}** · DNI {fila.dni}  \n{fila.materia} · {_periodo(fila)}")
                        st.caption(fila.motivo)
                    if c2.checkbox("Seleccionar", key=f"{clave}_sel_{fila.id}"):
                        elegidos.append(int(fila.id))
            observacion = st.text_input("Observación (opcional, la ve el alumno)", max_chars=300)
            a1, a2 = st.columns(2)
            aprobar = a1.form_submit_button("Aprobar seleccionados", type="primary", width="stretch")
            rechazar = a2.form_submit_button("Rechazar seleccionados", width="stretch")
        if (aprobar or rechazar) and not elegidos:
            st.error("Seleccioná al menos un justificativo.")
        elif aprobar or rechazar:
            clases = sum(jus.resolver(i, bool(aprobar), usuario_id, observacion) for i in elegidos)
            if aprobar:
                st.toast(f"{len(elegidos)} justificativo(s) aprobados · {clases} clase(s) justificadas")
            else:
                st.toast(f"{len(elegidos)} justificativo(s) rechazados")
            st.rerun()
        con_archivo = pendientes[pendientes["tiene_archivo"] == 1]
        if not con_archivo.empty:
            opciones = {int(f.id): f"{f.alumno} · {_periodo(f)}" for f in con_archivo.itertuples()}
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            elegido = c1.selectbox("Ver comprobante", list(opciones), format_func=opciones.get, key=f"{clave}_ver")
            archivo = jus.archivo(elegido)
            if archivo:
                c2.download_button("Descargar comprobante", archivo[1], file_name=archivo[0], mime=archivo[2],
                                   key=f"{clave}_dl", width="stretch", icon=":material/download:")

    with st.expander("Resueltos recientemente"):
        resueltos = pd.concat([jus.listar(institucion_id, e, docente_id=docente_id) for e in ("aprobado", "rechazado")])
        resueltos = resueltos.sort_values("resuelto_en", ascending=False).head(30)
        tabla_html(
            [{"alumno": f.alumno, "materia": f.materia, "periodo": _periodo(f),
              "estado": estado_html(f.estado.capitalize(), COLOR_ESTADO[f.estado]), "obs": f.observacion or None}
             for f in resueltos.itertuples()],
            {"alumno": "Alumno/a", "materia": "Materia", "periodo": "Período", "estado": "Estado", "obs": "Observación"},
            vacio="Todavía no se resolvió ningún justificativo.",
        )


def formulario_alumno(institucion_id: int, estudiante_id: int, materias: list[Materia]) -> None:
    """El alumno carga su justificativo y sigue su estado."""
    with st.form("form_justificativo", clear_on_submit=True):
        st.markdown("##### Presentar un justificativo")
        opciones = [None] + [m.id for m in materias]
        nombres = {m.id: m.nombre for m in materias}
        materia = st.selectbox("Materia", opciones, format_func=lambda i: "Todas mis materias" if i is None else nombres[i])
        c1, c2 = st.columns(2)
        desde = c1.date_input("Desde", value=hoy(), max_value=hoy(), min_value=hoy() - timedelta(days=90), format="DD/MM/YYYY")
        hasta = c2.date_input("Hasta", value=hoy(), max_value=hoy(), min_value=hoy() - timedelta(days=90), format="DD/MM/YYYY")
        motivo = st.text_area("Motivo", placeholder="Ej. Turno médico, certificado adjunto.", max_chars=400, height=80)
        archivo = st.file_uploader("Comprobante (PDF o imagen, opcional)", type=["pdf", "png", "jpg", "jpeg", "webp"])
        if st.form_submit_button("Enviar justificativo", type="primary"):
            try:
                adjunto = (archivo.name, archivo.getvalue(), archivo.type) if archivo else None
                jus.crear(estudiante_id, institucion_id, materia, desde, hasta, motivo, estudiante_id, adjunto)
            except ValueError as exc:
                mostrar_errores(str(exc).split("\n"))
            else:
                st.success("Justificativo enviado. Preceptoría o tu docente lo van a revisar.")
    mios = jus.listar(institucion_id, estudiante_id=estudiante_id)
    st.markdown("##### Mis justificativos")
    tabla_html(
        [{"materia": f.materia, "periodo": _periodo(f), "estado": estado_html(f.estado.capitalize(), COLOR_ESTADO[f.estado]),
          "obs": f.observacion or None} for f in mios.itertuples()],
        {"materia": "Materia", "periodo": "Período", "estado": "Estado", "obs": "Observación"},
        vacio="Todavía no presentaste justificativos.",
    )
