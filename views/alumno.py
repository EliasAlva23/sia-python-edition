"""Panel del Estudiante: dar presente (QR/PIN), unirse a materias, sábana personal y credencial."""
from __future__ import annotations

import hashlib
import time
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from models.asistencia import RegistroAsistencia, ResultadoMarcado
from models.materia import Materia
from models.persona import Estudiante
from models.predictor_ia import PredictorRiesgoIA
from utils.qr import decodificar_qr, generar_qr_png, interpretar_codigo
from views.styles import (
    TONOS, alerta, chips, estilo_plotly, hero, kpi_grid, tarjeta_progreso, tono_porcentaje,
)

ICONOS_ESTADO = {"presente": "✅ Presente", "tarde": "🕒 Tarde", "justificado": "📝 Justificado", "ausente": "❌ Ausente"}
SIMBOLOS = {"presente": "✅", "tarde": "🕒", "justificado": "📝", "ausente": "❌"}
METODOS = {"qr_credencial": "QR credencial", "qr_clase": "QR de clase", "pin": "PIN", "manual": "Manual"}
MINUTOS_ENLACE = 10


def render(estudiante: Estudiante) -> None:
    hero(f"Hola, {estudiante.nombre} 👋", "Panel del estudiante · tu asistencia, tus materias y tu credencial")
    _procesar_accion_pendiente(estudiante)
    _mostrar_resultado_guardado()

    materias = Materia.de_estudiante(estudiante.id)
    df = Materia.registros_df([m.id for m in materias], estudiante_id=estudiante.id)
    _resumen(materias, df)

    tabs = st.tabs(["📷 Dar presente", "➕ Unirme a una materia", "📋 Mi sábana", "🪪 Mi credencial"])
    with tabs[0]:
        _tab_presente(estudiante, materias)
    with tabs[1]:
        _tab_unirme(estudiante, materias)
    with tabs[2]:
        _tab_sabana(materias, df, estudiante)
    with tabs[3]:
        _tab_credencial(estudiante)


# ---------------------------------------------------------------- lógica de códigos
def procesar_entrada(texto: str, estudiante: Estudiante) -> ResultadoMarcado:
    """Interpreta lo escaneado/tipeado: QR dinámico de clase (o su URL), PIN o código de inscripción."""
    texto = interpretar_codigo(texto)
    if texto.upper().startswith("SIA:C:"):
        return RegistroAsistencia.procesar_token_clase(texto, estudiante)
    if len(texto) == 6 and texto.isdigit():
        return RegistroAsistencia.procesar_pin(texto, estudiante)
    if texto.upper().startswith("SIA:STUDENT:"):
        return ResultadoMarcado(False, "error", "Ese es un QR de credencial: lo escanea el docente.")
    if not texto:
        return ResultadoMarcado(False, "error", "Ingresá un código o PIN.")
    materia = Materia.por_codigo(texto)
    if materia is None:
        return ResultadoMarcado(False, "error", "Código no reconocido o inválido. Revisá que sea el código o QR vigente.")
    ok, mensaje = materia.inscribir(estudiante.id)
    return ResultadoMarcado(True, "registrado" if ok else "duplicado", mensaje)


def _procesar_accion_pendiente(estudiante: Estudiante) -> None:
    """Completa la acción de un QR escaneado con la cámara nativa del celular (enlace ?asistencia / ?inscribir)."""
    accion = st.session_state.pop("accion_pendiente", None)
    if not accion:
        return
    if accion.get("error"):
        resultado = ResultadoMarcado(False, "error", accion["error"])
    elif time.time() - accion["capturado"] > MINUTOS_ENLACE * 60:
        resultado = ResultadoMarcado(False, "error", "El enlace escaneado venció. Volvé a escanear el QR.")
    elif accion["tipo"] == "asistencia":
        resultado = RegistroAsistencia(accion["clase_id"]).marcar(estudiante.id, "qr_clase", estudiante.id)
    else:
        resultado = procesar_entrada(accion["codigo"], estudiante)
    _guardar_resultado(resultado)


def _guardar_resultado(resultado: ResultadoMarcado) -> None:
    st.session_state["resultado_alumno"] = resultado
    st.session_state["mostrar_resultado_alumno"] = True


def _mostrar_resultado_guardado() -> None:
    resultado = st.session_state.get("resultado_alumno")
    if resultado is None or not st.session_state.pop("mostrar_resultado_alumno", False):
        return
    if resultado.estado == "registrado":
        st.success(f"✅ {resultado.mensaje}")
        st.balloons()
    elif resultado.estado == "duplicado":
        st.info(f"ℹ️ {resultado.mensaje}")
    else:
        st.error(f"⛔ {resultado.mensaje}")


def _escaner(clave: str, etiqueta: str, estudiante: Estudiante) -> None:
    """Cámara bajo demanda (evita abrir varias cámaras a la vez en el celular)."""
    if not st.toggle("📷 Activar cámara", key=f"activar_{clave}"):
        st.caption("Activá la cámara y sacá una foto nítida del QR (en el celular podés cambiar a la cámara trasera).")
        return
    foto = st.camera_input(etiqueta, key=f"cam_{clave}")
    if foto is None:
        return
    huella = hashlib.sha256(foto.getvalue()).hexdigest()
    if st.session_state.get(f"huella_{clave}") == huella:
        return  # Streamlit reenvía la misma foto en cada rerun: solo procesamos fotos nuevas.
    st.session_state[f"huella_{clave}"] = huella
    textos = decodificar_qr(foto.getvalue())
    _guardar_resultado(
        procesar_entrada(textos[0], estudiante) if textos
        else ResultadoMarcado(False, "error", "No se detectó un QR. Acercate, evitá reflejos y volvé a intentar.")
    )
    st.rerun()


# ---------------------------------------------------------------- resumen
def _resumen(materias: list[Materia], df: pd.DataFrame) -> None:
    total = len(df)
    presentes = int(df["presente"].sum()) if total else 0
    general = 100 * presentes / total if total else 0.0
    racha = PredictorRiesgoIA.extraer_features(df.sort_values("fecha")["presente"].tolist())["racha_actual"] if total else 0
    kpi_grid([
        ("Asistencia general", f"{general:.0f}%" if total else "—",
         f"{presentes} de {total} clases" if total else "Sin clases todavía",
         tono_porcentaje(general, 75) if total else "gris"),
        ("Presentes", presentes, "incluye tardes y justificadas", "verde"),
        ("Ausencias", total - presentes, f"Racha actual: {racha}", "rojo" if racha >= 2 else "gris"),
        ("Materias", len(materias), "inscripciones activas", "azul"),
    ])


# ---------------------------------------------------------------- dar presente
def _tab_presente(estudiante: Estudiante, materias: list[Materia]) -> None:
    abiertas = [m for m in materias if (c := m.clase_de_hoy()) and c["abierta"]]
    if abiertas:
        st.markdown(chips([f"🟢 Clase abierta: {m.nombre}" for m in abiertas]), unsafe_allow_html=True)
    elif materias:
        st.caption("Ninguna de tus materias tiene una clase abierta en este momento.")
    col_cam, col_pin = st.columns([1.3, 1])
    with col_cam:
        with st.container(border=True):
            st.markdown("##### 📷 Escanear QR de la clase")
            st.caption("También podés escanearlo con la cámara del celular: abre la app y registra tu presente.")
            _escaner("presente", "Apuntá al QR que proyecta tu docente", estudiante)
    with col_pin:
        with st.form("form_pin", clear_on_submit=True):
            st.markdown("##### 🔢 ¿Falla la cámara? Ingresá el PIN")
            pin = st.text_input("PIN de 6 dígitos", max_chars=6, placeholder="000000")
            if st.form_submit_button("Dar presente", type="primary", width="stretch"):
                pin = pin.strip()
                if not pin:
                    st.error("Ingresá el PIN que se muestra debajo del QR.")
                elif not (pin.isdigit() and len(pin) == 6):
                    st.error("El PIN debe tener exactamente 6 números.")
                else:
                    _guardar_resultado(RegistroAsistencia.procesar_pin(pin, estudiante))
                    st.rerun()


# ---------------------------------------------------------------- unirme
def _tab_unirme(estudiante: Estudiante, materias: list[Materia]) -> None:
    col_form, col_lista = st.columns([1.2, 1])
    with col_form:
        with st.form("form_codigo_alumno", clear_on_submit=True):
            st.markdown("##### ➕ Unirme con código de clase")
            entrada = st.text_input("Código de la materia", placeholder="SIA-XXXXXX", max_chars=200)
            if st.form_submit_button("Unirme a la materia", type="primary", width="stretch"):
                if not entrada.strip():
                    st.error("Ingresá el código que te compartió tu docente.")
                else:
                    _guardar_resultado(procesar_entrada(entrada, estudiante))
                    st.rerun()
        with st.container(border=True):
            st.markdown("##### 📷 o escaneá el QR de inscripción")
            _escaner("unirme", "Apuntá al QR de inscripción", estudiante)
    with col_lista:
        st.markdown("##### 📚 Mis materias")
        if not materias:
            st.caption("Todavía no estás inscripto/a en ninguna materia.")
        for materia in materias:
            clase = materia.clase_de_hoy()
            estado = "🟢 Clase abierta hoy" if clase and clase["abierta"] else "⚪ Sin clase abierta"
            st.markdown(
                f'<div class="sia-card"><b>{escape(materia.nombre)}</b>'
                f'{chips([f"🎓 {materia.curso}", f"🕑 {materia.turno}", f"🗓️ {materia.dia_horario}"])}'
                f'<span class="muted">{estado}</span></div>',
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------- sábana personal
def _tab_sabana(materias: list[Materia], df: pd.DataFrame, estudiante: Estudiante) -> None:
    if not materias:
        st.info("Unite a una materia para ver tu sábana de asistencia.")
        return
    if df.empty:
        st.info("Todavía no se dictaron clases en tus materias.")
        return

    st.markdown("##### Porcentaje actual por materia")
    tarjetas = []
    avisos = []
    for materia in materias:
        sub = df[df["materia_id"] == materia.id].sort_values("fecha")
        if sub.empty:
            tarjetas.append(tarjeta_progreso(materia.nombre, "—", "Sin clases todavía", 0, "gris"))
            continue
        p, n = int(sub["presente"].sum()), len(sub)
        pct = 100 * p / n
        tarjetas.append(tarjeta_progreso(
            materia.nombre, f"{pct:.0f}%", f"{p}/{n} clases · umbral {materia.umbral:.0f}%",
            pct, tono_porcentaje(pct, materia.umbral),
        ))
        f = PredictorRiesgoIA.extraer_features(sub["presente"].tolist())
        faltan = PredictorRiesgoIA.clases_para_recuperar(p, n, materia.umbral)
        if faltan:
            avisos.append((f"{materia.nombre}: estás por debajo del umbral",
                           f"Necesitás asistir a las próximas {faltan} clases seguidas para recuperar la regularidad.",
                           TONOS["rojo"]))
        elif f["max_consecutivas"] >= 3 or f["racha_actual"] >= 2:
            avisos.append((f"{materia.nombre}: atención a las faltas seguidas",
                           f"Llevás {f['racha_actual']} ausencias consecutivas (máximo {f['max_consecutivas']}).",
                           TONOS["ambar"]))
    st.markdown(f'<div class="sia-grid">{"".join(tarjetas)}</div>', unsafe_allow_html=True)
    for aviso in avisos:
        alerta(*aviso)

    st.markdown("##### 📋 Sábana personal")
    st.caption("✅ presente · 🕒 tarde · 📝 justificado · ❌ ausente · — sin clase ese día")
    sabana = (df.assign(marca=df["estado"].map(SIMBOLOS))
                .pivot_table(index="materia", columns="fecha", values="marca", aggfunc="first")
                .fillna("—"))
    sabana.insert(0, "%", df.groupby("materia")["presente"].mean().mul(100).round(0))
    st.dataframe(sabana, width="stretch", column_config={
        "%": st.column_config.ProgressColumn("% asistencia", min_value=0, max_value=100, format="%.0f%%"),
    })

    serie = df.sort_values("fecha").copy()
    serie["acumulado"] = serie.groupby("materia")["presente"].transform(lambda s: s.expanding().mean() * 100)
    fig = px.line(serie, x="fecha", y="acumulado", color="materia", markers=True,
                  title="Evolución de tu asistencia acumulada (%)",
                  labels={"fecha": "Clase", "acumulado": "% acumulado", "materia": "Materia"})
    fig.add_hline(y=75, line_dash="dash", line_color=TONOS["rojo"], annotation_text="75%")
    fig.update_yaxes(range=[0, 105])
    st.plotly_chart(estilo_plotly(fig), width="stretch")

    with st.expander("🗂️ Historial detallado", expanded=False):
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
        st.download_button(
            "⬇️ Descargar mi historial (CSV)",
            historial[["fecha", "materia", "tema", "estado", "metodo", "registrado_en"]].to_csv(index=False).encode("utf-8"),
            file_name=f"mi_asistencia_{estudiante.dni}.csv", mime="text/csv",
        )


# ---------------------------------------------------------------- credencial
def _tab_credencial(estudiante: Estudiante) -> None:
    payload = estudiante.credencial_qr()
    col_qr, col_info = st.columns([1, 1.3])
    with col_qr:
        with st.container(border=True):
            st.image(generar_qr_png(payload, box_size=12), width="stretch")
    with col_info:
        legajo = f" · Legajo <b>{escape(estudiante.legajo)}</b>" if estudiante.legajo else ""
        st.markdown(
            f'<div class="sia-card"><div class="muted" style="font-weight:700;letter-spacing:.08em">'
            f'CREDENCIAL ESTUDIANTIL · ISE</div>'
            f'<div style="font-size:1.5rem;font-weight:800;margin:.3rem 0">{escape(estudiante.nombre_completo)}</div>'
            f'<div>DNI <b>{escape(estudiante.dni)}</b>{legajo}</div>'
            f'<div class="muted">{escape(estudiante.email)}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("Mostrá este QR al docente para registrar tu presente. "
                    "Está **firmado digitalmente**: no puede falsificarse cambiando el DNI.")
        st.code(payload, language=None, wrap_lines=True)
        st.download_button("⬇️ Descargar credencial (PNG)", generar_qr_png(payload, box_size=16),
                           file_name=f"credencial_sia_{estudiante.dni}.png", mime="image/png")
