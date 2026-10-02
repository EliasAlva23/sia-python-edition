"""Panel del Alumno: credencial QR, auto-inscripción / presente y métricas personales."""
from __future__ import annotations

import hashlib

import pandas as pd
import plotly.express as px
import streamlit as st

from models.asistencia import RegistroAsistencia, ResultadoMarcado
from models.materia import Materia
from models.persona import Estudiante
from models.predictor_ia import PredictorRiesgoIA
from utils.qr import decodificar_qr, generar_qr_png
from views.styles import alerta, estilo_plotly, hero, kpi, tono_porcentaje, TONOS

ICONOS_ESTADO = {"presente": "✅ Presente", "tarde": "🕒 Tarde", "justificado": "📝 Justificado", "ausente": "❌ Ausente"}
METODOS = {"qr_credencial": "QR credencial", "qr_clase": "QR de clase", "pin": "PIN", "manual": "Manual"}


def render(estudiante: Estudiante) -> None:
    hero(f"Hola, {estudiante.nombre} 👋", "Tu credencial, tus materias y tu asistencia en un solo lugar")
    tabs = st.tabs(["🪪 Mi credencial QR", "📲 Inscribirme / Dar presente", "📈 Mis métricas"])
    with tabs[0]:
        _tab_credencial(estudiante)
    with tabs[1]:
        _tab_codigos(estudiante)
    with tabs[2]:
        _tab_metricas(estudiante)


# ---------------------------------------------------------------- Credencial
def _tab_credencial(estudiante: Estudiante) -> None:
    payload = estudiante.credencial_qr()
    col_qr, col_info = st.columns([1, 1.3])
    with col_qr:
        with st.container(border=True):
            st.image(generar_qr_png(payload, box_size=12), width="stretch")
    with col_info:
        st.markdown(
            f"""<div class="sia-card">
            <div style="font-size:.75rem;font-weight:700;letter-spacing:.08em;color:#64748B">CREDENCIAL ESTUDIANTIL · SIA</div>
            <div style="font-size:1.6rem;font-weight:800;margin:.3rem 0">{_esc(estudiante.nombre_completo)}</div>
            <div>DNI <b>{_esc(estudiante.dni)}</b>{' · Legajo <b>' + _esc(estudiante.legajo) + '</b>' if estudiante.legajo else ''}</div>
            <div style="color:#64748B">{_esc(estudiante.email)}</div></div>""",
            unsafe_allow_html=True,
        )
        st.markdown("Mostrá este QR al docente para registrar tu presente. "
                    "El código está **firmado digitalmente**: no puede falsificarse cambiando el DNI.")
        st.code(payload, language=None)
        st.download_button("⬇️ Descargar credencial (PNG)", generar_qr_png(payload, box_size=16),
                           file_name=f"credencial_sia_{estudiante.dni}.png", mime="image/png")


def _esc(texto: str | None) -> str:
    from html import escape
    return escape(texto or "")


# ---------------------------------------------------------------- Códigos
def procesar_entrada(texto: str, estudiante: Estudiante) -> ResultadoMarcado:
    """Interpreta lo escaneado/tipeado: QR dinámico de clase, PIN o código de inscripción."""
    texto = (texto or "").strip()
    if texto.upper().startswith("SIA:C:"):
        return RegistroAsistencia.procesar_token_clase(texto, estudiante)
    if len(texto) == 6 and texto.isdigit():
        return RegistroAsistencia.procesar_pin(texto, estudiante)
    if texto.upper().startswith("SIA:STUDENT:"):
        return ResultadoMarcado(False, "error", "Ese es un QR de credencial: se lo escanea el docente.")
    materia = Materia.por_codigo(texto)
    if materia is None:
        return ResultadoMarcado(False, "error", "Código no reconocido. Revisá que sea el código o QR vigente.")
    ok, mensaje = materia.inscribir(estudiante.id)
    return ResultadoMarcado(True, "registrado" if ok else "duplicado", mensaje)


def _mostrar(resultado: ResultadoMarcado) -> None:
    if resultado.estado == "registrado":
        st.success(f"✅ {resultado.mensaje}")
        st.balloons()
    elif resultado.estado == "duplicado":
        st.info(f"ℹ️ {resultado.mensaje}")
    else:
        st.error(f"⛔ {resultado.mensaje}")


def _tab_codigos(estudiante: Estudiante) -> None:
    st.markdown("#### Escaneá el QR proyectado por tu docente")
    st.caption("Sirve para **inscribirte** (QR / código de materia) y para **dar presente** (QR dinámico o PIN de 6 dígitos).")
    col_cam, col_lista = st.columns([1.3, 1])
    with col_cam:
        modo = st.radio("Modo", ["📷 Cámara", "⌨️ Ingresar código"], horizontal=True,
                        key="modo_alumno", label_visibility="collapsed")
        if modo.startswith("📷"):
            foto = st.camera_input("Apuntá la cámara al QR", key="cam_alumno")
            if foto is not None:
                huella = hashlib.sha256(foto.getvalue()).hexdigest()
                if st.session_state.get("ultima_foto_alumno") != huella:
                    st.session_state["ultima_foto_alumno"] = huella
                    textos = decodificar_qr(foto.getvalue())
                    st.session_state["resultado_alumno"] = (
                        procesar_entrada(textos[0], estudiante) if textos
                        else ResultadoMarcado(False, "error", "No se detectó un QR. Acercate y evitá reflejos.")
                    )
                    st.session_state["mostrar_resultado_alumno"] = True
        else:
            with st.form("form_codigo_alumno", clear_on_submit=True):
                entrada = st.text_input("Código de materia (SIA-XXXXXX) o PIN de 6 dígitos")
                if st.form_submit_button("Enviar", type="primary") and entrada.strip():
                    st.session_state["resultado_alumno"] = procesar_entrada(entrada, estudiante)
                    st.session_state["mostrar_resultado_alumno"] = True
        resultado = st.session_state.get("resultado_alumno")
        if resultado is not None:
            if st.session_state.pop("mostrar_resultado_alumno", False):
                _mostrar(resultado)
            else:
                st.caption(f"Último resultado: {resultado.mensaje}")
    with col_lista:
        st.markdown("##### 📚 Mis materias")
        materias = Materia.de_estudiante(estudiante.id)
        if not materias:
            st.caption("Todavía no estás inscripto/a en ninguna materia.")
        for materia in materias:
            clase = materia.clase_de_hoy()
            estado = "🟢 Clase abierta hoy" if clase and clase["abierta"] else "⚪ Sin clase abierta"
            st.markdown(f'<div class="sia-card"><b>{_esc(materia.nombre)}</b><br>'
                        f'<span style="color:#64748B;font-size:.85rem">{estado}</span></div>',
                        unsafe_allow_html=True)


# ---------------------------------------------------------------- Métricas
def _tab_metricas(estudiante: Estudiante) -> None:
    materias = Materia.de_estudiante(estudiante.id)
    if not materias:
        st.info("Inscribite en una materia para ver tus métricas.")
        return
    df = Materia.registros_df([m.id for m in materias], estudiante_id=estudiante.id)
    if df.empty:
        st.info("Todavía no se dictaron clases en tus materias.")
        return

    total, presentes = len(df), int(df["presente"].sum())
    general = 100 * presentes / total
    features = PredictorRiesgoIA.extraer_features(df.sort_values("fecha")["presente"].tolist())
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        kpi("Asistencia general", f"{general:.1f}%", f"{presentes} de {total} clases", tono_porcentaje(general, 75))
    with k2:
        kpi("Presentes", presentes, "incluye tardes y justificadas", "verde")
    with k3:
        kpi("Ausencias", total - presentes, f"Racha actual: {features['racha_actual']}",
            "rojo" if features["racha_actual"] >= 2 else "gris")
    with k4:
        kpi("Materias", len(materias), "inscripciones activas", "indigo")

    st.markdown("#### Situación por materia")
    columnas = st.columns(min(3, len(materias)))
    for i, materia in enumerate(materias):
        sub = df[df["materia_id"] == materia.id].sort_values("fecha")
        with columnas[i % len(columnas)]:
            if sub.empty:
                kpi(materia.nombre, "—", "Sin clases todavía", "gris")
                continue
            p, n = int(sub["presente"].sum()), len(sub)
            pct = 100 * p / n
            f = PredictorRiesgoIA.extraer_features(sub["presente"].tolist())
            kpi(materia.nombre, f"{pct:.0f}%", f"{p}/{n} clases · umbral {materia.umbral:.0f}%",
                tono_porcentaje(pct, materia.umbral))
            faltan = PredictorRiesgoIA.clases_para_recuperar(p, n, materia.umbral)
            if faltan:
                alerta("Estás por debajo del umbral",
                       f"Necesitás asistir a las próximas {faltan} clases seguidas para recuperar la regularidad.",
                       TONOS["rojo"])
            elif f["max_consecutivas"] >= 3 or f["racha_actual"] >= 2:
                alerta("Atención a las faltas seguidas",
                       f"Llevás {f['racha_actual']} ausencias consecutivas (máximo {f['max_consecutivas']}).",
                       TONOS["ambar"])

    serie = df.sort_values("fecha").copy()
    serie["acumulado"] = serie.groupby("materia")["presente"].transform(
        lambda s: s.expanding().mean() * 100)
    fig = px.line(serie, x="fecha", y="acumulado", color="materia", markers=True,
                  title="Evolución de tu asistencia acumulada (%)",
                  labels={"fecha": "Clase", "acumulado": "% acumulado", "materia": "Materia"})
    fig.add_hline(y=75, line_dash="dash", line_color="#DC2626", annotation_text="75%")
    fig.update_yaxes(range=[0, 105])
    st.plotly_chart(estilo_plotly(fig), width="stretch")

    st.markdown("#### Historial detallado")
    historial = df.sort_values("fecha", ascending=False).assign(
        Estado=lambda d: d["estado"].map(ICONOS_ESTADO),
        Método=lambda d: d["metodo"].map(METODOS).fillna("—"),
        Hora=lambda d: d["registrado_en"].fillna("").str[11:16].replace("", "—"),
    )
    st.dataframe(
        historial[["fecha", "materia", "tema", "Estado", "Método", "Hora"]].rename(
            columns={"fecha": "Fecha", "materia": "Materia", "tema": "Tema"}),
        hide_index=True, width="stretch",
    )
    st.download_button("⬇️ Descargar mi historial (CSV)",
                       historial[["fecha", "materia", "tema", "estado", "metodo", "registrado_en"]]
                       .to_csv(index=False).encode("utf-8"),
                       file_name=f"mi_asistencia_{estudiante.dni}.csv", mime="text/csv")
