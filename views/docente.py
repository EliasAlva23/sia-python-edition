"""Panel del Docente: materias, clase en vivo, lector QR y Sábana de Asistencia & Estadísticas."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from core.validaciones import TURNOS, errores_materia
from models.asistencia import VENTANA_SEGUNDOS, RegistroAsistencia, ResultadoMarcado, segundos_restantes
from models.materia import RESULTADOS, Materia
from models.persona import Docente
from models.predictor_ia import ETIQUETAS_FEATURES, PredictorRiesgoIA
from utils.qr import (
    contenido_asistencia, contenido_inscripcion, decodificar_qr, generar_qr_png, lectores_disponibles, url_publica,
)
from views import auth
from views.styles import (
    COLORES_NIVEL, EMOJI_NIVEL, TONOS, alerta, aviso_camara, chips, codigo, estilo_plotly, hero, kpi_grid, mostrar_errores,
    tono_porcentaje,
)

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
TAB_SABANA = "📊 Sábana de Asistencia & Estadísticas"


def render(docente: Docente) -> None:
    hero(f"Hola, {docente.nombre} 👋", "Panel docente · materias, asistencia por QR y sábana de asistencia")
    materias = Materia.de_docente(docente.id)
    materia = _selector_materia(materias)

    tabs = st.tabs(["📚 Materias", "📡 Clase en vivo", "📷 Lector QR", TAB_SABANA])
    with tabs[0]:
        _tab_materias(docente, materias)
    if materia is None:
        for tab in tabs[1:]:
            with tab:
                st.info("Creá tu primera materia en la pestaña **📚 Materias** para comenzar.")
        return
    with tabs[1]:
        _tab_clase(docente, materia)
    with tabs[2]:
        _tab_lector(docente, materia)
    with tabs[3]:
        _tab_sabana(materia, materias)


def _selector_materia(materias: list[Materia]) -> Materia | None:
    if not materias:
        return None
    por_id = {m.id: m for m in materias}
    if st.session_state.get("materia_activa") not in por_id:
        st.session_state["materia_activa"] = materias[0].id
    with st.sidebar:
        st.markdown("##### 🎯 Materia activa")
        seleccion = st.selectbox(
            "Materia activa", list(por_id), format_func=lambda i: f"{por_id[i].nombre} · {por_id[i].curso}".rstrip(" ·"),
            key="materia_activa", label_visibility="collapsed",
        )
    return por_id[seleccion]


def _chips_materia(materia: Materia) -> str:
    return chips([
        f"🎓 {materia.curso}" if materia.curso else "",
        f"🕑 Turno {materia.turno}" if materia.turno else "",
        f"🗓️ {materia.dia_horario}" if materia.dia_horario else "",
    ])


# ---------------------------------------------------------------- Materias
def _campos_materia(prefijo: str, materia: Materia | None = None) -> dict:
    c1, c2 = st.columns([2, 1])
    nombre = c1.text_input("Nombre de la materia *", value=materia.nombre if materia else "",
                           placeholder="Ciencia de Datos I", max_chars=120, key=f"{prefijo}_nombre")
    curso = c2.text_input("Curso / Comisión *", value=materia.curso if materia else "",
                          placeholder="1° Año - Comisión 2", max_chars=80, key=f"{prefijo}_curso")
    c3, c4, c5 = st.columns([1, 2, 1])
    turno_actual = TURNOS.index(materia.turno) if materia and materia.turno in TURNOS else None
    turno = c3.selectbox("Turno *", TURNOS, index=turno_actual, placeholder="Seleccioná…", key=f"{prefijo}_turno")
    dia_horario = c4.text_input("Día y horario *", value=materia.dia_horario if materia else "",
                                placeholder="Lunes y Miércoles 18:00 - 20:00 hs", max_chars=120,
                                key=f"{prefijo}_horario")
    umbral = c5.slider("Umbral (%)", 50, 100, int(materia.umbral) if materia else 75, step=5,
                       key=f"{prefijo}_umbral", help="Asistencia mínima para mantener la regularidad.")
    descripcion = st.text_area("Descripción (opcional)", value=materia.descripcion if materia else "",
                               placeholder="Aula, modalidad, observaciones…", height=80, max_chars=500,
                               key=f"{prefijo}_desc")
    return dict(nombre=nombre, curso=curso, turno=turno, dia_horario=dia_horario, umbral=umbral,
                descripcion=descripcion)


def _tab_materias(docente: Docente, materias: list[Materia]) -> None:
    with st.expander("➕ Nueva materia", expanded=not materias):
        with st.form("form_materia", clear_on_submit=False):
            datos = _campos_materia("nueva")
            enviar = st.form_submit_button("Crear materia", type="primary")
        if enviar:
            errores = errores_materia(datos["nombre"], datos["curso"], datos["turno"], datos["dia_horario"])
            if errores:
                mostrar_errores(errores)
            else:
                try:
                    nueva = Materia.crear(docente_id=docente.id, **datos)
                    for clave in [k for k in st.session_state if str(k).startswith("nueva_")]:
                        del st.session_state[clave]
                    st.session_state["materia_activa"] = nueva.id
                    st.toast(f"Materia creada · código {nueva.codigo_clase}", icon="✅")
                    st.rerun()
                except ValueError as exc:
                    mostrar_errores(str(exc).split("\n"))

    if not materias:
        return
    for materia in materias:
        _tarjeta_materia(materia)


def _tarjeta_materia(materia: Materia) -> None:
    with st.container(border=True):
        izquierda, derecha = st.columns([3, 1.3])
        alumnos = materia.alumnos()
        clases = materia.clases()
        with izquierda:
            st.markdown(f"### {escape(materia.nombre)}")
            st.markdown(_chips_materia(materia), unsafe_allow_html=True)
            if materia.descripcion:
                st.caption(materia.descripcion)
            st.markdown("**Código de clase** (para unirse):")
            codigo(materia.codigo_clase)
            kpi_grid([
                ("Alumnos", len(alumnos), "inscriptos", "azul"),
                ("Clases", len(clases), "dictadas", "celeste"),
                ("Umbral", f"{materia.umbral:.0f}%", "regularidad", "gris"),
            ])
            b1, b2, _ = st.columns([1, 1, 1.5])
            if b1.button("🔄 Regenerar código", key=f"regen_{materia.id}", width="stretch",
                         help="Invalida el código y el QR anteriores para nuevas inscripciones."):
                materia.regenerar_codigo()
                st.rerun()
            with b2.popover("⚙️ Editar materia", width="stretch"):
                _form_edicion(materia)
        with derecha:
            contenido = contenido_inscripcion(materia.codigo_clase, materia.firma_inscripcion, materia.payload_inscripcion)
            st.image(generar_qr_png(contenido, box_size=8), caption="QR de inscripción", width="stretch")
            st.download_button(
                "⬇️ Descargar QR", generar_qr_png(contenido, box_size=14),
                file_name=f"inscripcion_{materia.codigo_clase}.png", mime="image/png",
                key=f"dl_qr_{materia.id}", width="stretch",
            )
        with st.expander(f"👥 Alumnos inscriptos ({len(alumnos)})"):
            _editor_alumnos(materia, alumnos)


def _form_edicion(materia: Materia) -> None:
    with st.form(f"edit_{materia.id}"):
        datos = _campos_materia(f"edit_{materia.id}", materia)
        archivar = st.checkbox("Archivar materia (deja de mostrarse)")
        enviar = st.form_submit_button("Guardar cambios", type="primary")
    if not enviar:
        return
    if archivar:
        materia.archivar()
        st.rerun()
    errores = errores_materia(datos["nombre"], datos["curso"], datos["turno"], datos["dia_horario"])
    if errores:
        mostrar_errores(errores)
        return
    try:
        materia.actualizar(**datos)
    except ValueError as exc:
        mostrar_errores(str(exc).split("\n"))
        return
    st.rerun()


def _editor_alumnos(materia: Materia, alumnos: pd.DataFrame) -> None:
    if alumnos.empty:
        st.caption("Todavía no hay inscriptos. Compartí el código o el QR de inscripción.")
        return
    vista = alumnos[["id", "dni", "apellido", "nombre", "email", "legajo", "resultado"]].copy()
    vista["resultado"] = vista["resultado"].fillna("en curso")
    editado = st.data_editor(
        vista,
        key=f"editor_{materia.id}",
        hide_index=True,
        width="stretch",
        disabled=["id", "dni", "apellido", "nombre", "email", "legajo"],
        column_config={
            "id": None,
            "resultado": st.column_config.SelectboxColumn(
                "Resultado final", options=["en curso", *RESULTADOS],
                help="Los resultados cargados alimentan el entrenamiento del modelo de IA.",
            ),
        },
    )
    c1, c2 = st.columns([1, 2])
    if c1.button("💾 Guardar resultados", key=f"guardar_res_{materia.id}"):
        for fila in editado.itertuples():
            materia.establecer_resultado(int(fila.id), None if fila.resultado == "en curso" else fila.resultado)
        st.success("Resultados guardados.")
    with c2.popover("🗑️ Dar de baja a un alumno"):
        opciones = {int(f.id): f"{f.apellido}, {f.nombre} ({f.dni})" for f in alumnos.itertuples()}
        elegido = st.selectbox("Alumno", list(opciones), format_func=opciones.get, key=f"baja_{materia.id}")
        if st.button("Confirmar baja", key=f"conf_baja_{materia.id}", type="primary"):
            materia.desinscribir(elegido)
            st.rerun()


# ---------------------------------------------------------------- Clase en vivo
def _tab_clase(docente: Docente, materia: Materia) -> None:
    clase = materia.clase_de_hoy()
    if clase is None or not clase["abierta"]:
        st.markdown(f"#### {escape(materia.nombre)}")
        st.markdown(_chips_materia(materia), unsafe_allow_html=True)
        if clase is not None:
            st.info("La clase de hoy está **cerrada**. Podés reabrirla para seguir registrando asistencia.")
        with st.form(f"abrir_{materia.id}"):
            tema = st.text_input("Tema de la clase (opcional)", value=(clase or {}).get("tema", ""), max_chars=150)
            etiqueta = "▶️ Reabrir clase de hoy" if clase else "▶️ Iniciar clase de hoy"
            if st.form_submit_button(etiqueta, type="primary"):
                materia.abrir_clase(" ".join(tema.split()))
                st.rerun()
        _historial_clases(materia)
        return

    registro = RegistroAsistencia(clase["id"])
    st.markdown(f"#### 🟢 Clase en curso · {escape(materia.nombre)} · {clase['fecha']}"
                + (f" — {escape(clase['tema'])}" if clase["tema"] else ""))
    if url_publica() is None:
        st.caption("ℹ️ La app corre en local: el QR contiene un código SIA firmado que se lee con el escáner "
                   "de la app. Al publicarla (o definir SIA_PUBLIC_URL) el QR pasa a ser un enlace que "
                   "funciona con la cámara nativa del celular.")
    col_qr, col_live = st.columns([1.1, 1])
    with col_qr:
        _qr_dinamico(registro.clase_id)
    with col_live:
        _panel_presentes(registro.clase_id, materia.id)

    st.divider()
    _marcado_manual(docente, materia, registro)
    if st.button("⏹️ Cerrar clase", type="secondary"):
        materia.cerrar_clase(registro.clase_id)
        st.rerun()


@st.fragment(run_every=timedelta(seconds=3))
def _qr_dinamico(clase_id: int) -> None:
    auth.registrar_actividad()  # proyectar el QR cuenta como actividad del docente
    registro = RegistroAsistencia(clase_id)
    with st.container(border=True):
        st.markdown("**QR dinámico de asistencia** — proyectalo para que los alumnos lo escaneen")
        st.image(generar_qr_png(contenido_asistencia(registro.generar_token()), box_size=12), width="stretch")
        restante = segundos_restantes()
        st.progress(restante / VENTANA_SEGUNDOS, text=f"🔐 Firmado con SIA_SECRET · rota en {restante} s")
        st.markdown("PIN para quienes no pueden usar la cámara:")
        codigo(registro.generar_pin(), grande=True)


@st.fragment(run_every=timedelta(seconds=5))
def _panel_presentes(clase_id: int, materia_id: int) -> None:
    materia = Materia.obtener(materia_id)
    presentes = RegistroAsistencia(clase_id).presentes()
    inscriptos = len(materia.alumnos()) if materia else 0
    pct = 100 * len(presentes) / inscriptos if inscriptos else 0
    kpi_grid([
        ("Presentes", f"{len(presentes)} / {inscriptos}", "registrados hoy", "azul"),
        ("Asistencia de hoy", f"{pct:.0f}%", "en tiempo real", tono_porcentaje(pct, materia.umbral if materia else 75)),
    ])
    if presentes.empty:
        st.caption("Esperando los primeros registros…")
    else:
        st.dataframe(presentes[["hora", "alumno", "estado", "metodo"]], hide_index=True, width="stretch", height=300)


def _marcado_manual(docente: Docente, materia: Materia, registro: RegistroAsistencia) -> None:
    st.markdown("##### ✍️ Registro manual")
    alumnos = materia.alumnos()
    presentes = registro.presentes()
    if alumnos.empty:
        st.caption("No hay alumnos inscriptos.")
        return
    ids_presentes = set(presentes["id"].tolist())
    opciones = {int(f.id): f"{f.apellido}, {f.nombre} ({f.dni})" for f in alumnos.itertuples()}
    pendientes = [i for i in opciones if i not in ids_presentes]
    c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
    elegidos = c1.multiselect("Alumnos sin registro", pendientes, format_func=opciones.get,
                              key=f"manual_{registro.clase_id}", placeholder="Elegí uno o más alumnos")
    estado = c2.selectbox("Estado", ["presente", "tarde", "justificado"], key=f"estado_{registro.clase_id}")
    if c3.button("Registrar", type="primary", width="stretch", key=f"btn_manual_{registro.clase_id}"):
        if not elegidos:
            st.error("Elegí al menos un alumno para registrar.")
        else:
            for estudiante_id in elegidos:
                registro.marcar(estudiante_id, "manual", docente.id, estado=estado, docente_id=docente.id)
            st.rerun()
    if ids_presentes:
        with st.popover("↩️ Corregir o anular un registro"):
            elegido = st.selectbox("Alumno", sorted(ids_presentes), format_func=lambda i: opciones.get(i, str(i)),
                                   key=f"corr_{registro.clase_id}")
            nuevo = st.selectbox("Nuevo estado", ["presente", "tarde", "justificado", "anular (ausente)"],
                                 key=f"corr_estado_{registro.clase_id}")
            if st.button("Aplicar", key=f"corr_btn_{registro.clase_id}"):
                if nuevo.startswith("anular"):
                    registro.anular(elegido)
                else:
                    registro.actualizar_estado(elegido, nuevo)
                st.rerun()


def _historial_clases(materia: Materia) -> None:
    clases = materia.clases()
    if clases.empty:
        return
    st.markdown("##### 🗓️ Clases anteriores")
    clases["abierta"] = clases["abierta"].map({1: "Abierta", 0: "Cerrada"})
    st.dataframe(clases.drop(columns="id"), hide_index=True, width="stretch")


# ---------------------------------------------------------------- Lector QR
def _mostrar_resultado(resultado: ResultadoMarcado) -> None:
    if resultado.estado == "registrado":
        st.success(f"✅ {resultado.mensaje}")
    elif resultado.estado == "duplicado":
        st.info(f"ℹ️ {resultado.mensaje}")
    else:
        st.error(f"⛔ {resultado.mensaje}")


def _tab_lector(docente: Docente, materia: Materia) -> None:
    clase = materia.clase_de_hoy()
    if clase is None or not clase["abierta"]:
        st.warning("Primero iniciá la clase de hoy en **📡 Clase en vivo**.")
        return
    registro = RegistroAsistencia(clase["id"])
    clave_resultados = f"lector_resultados_{clase['id']}"
    st.markdown(f"#### 📷 Escanear credenciales · {escape(materia.nombre)}")
    st.caption("Lectores disponibles: " + (", ".join(lectores_disponibles()) or "ninguno"))

    col_cam, col_res = st.columns([1.2, 1])
    with col_cam:
        modo = st.radio("Modo", ["⌨️ Manual / lector USB", "📷 Cámara"], horizontal=True,
                        key=f"modo_lector_{clase['id']}", label_visibility="collapsed")
        if modo.startswith("📷"):
            aviso_camara("📌 Si tu navegador solicita permisos, haz clic en 'Permitir' para activar la cámara. "
                         "Si estás en iPhone/Android y no abre, usa el modo «Manual / lector USB» e ingresá el DNI.")
            foto = st.camera_input("Mostrá la credencial QR del alumno a la cámara", key=f"cam_doc_{clase['id']}")
            if foto is not None:
                huella = hashlib.sha256(foto.getvalue()).hexdigest()
                # Streamlit reenvía la misma foto en cada rerun: solo procesamos fotos nuevas.
                if st.session_state.get(f"ultima_foto_{clase['id']}") != huella:
                    st.session_state[f"ultima_foto_{clase['id']}"] = huella
                    textos = decodificar_qr(foto.getvalue())
                    if not textos:
                        resultados = [ResultadoMarcado(False, "error", "No se detectó ningún QR. Acercá la credencial y reintentá.")]
                    else:
                        resultados = [registro.procesar_credencial(t, docente.id) for t in textos]
                    st.session_state[clave_resultados] = resultados
        else:
            with st.form(f"form_manual_{clase['id']}", clear_on_submit=True):
                entrada = st.text_input("DNI del alumno o contenido de la credencial",
                                        help="Los lectores QR USB escriben el código y envían Enter.")
                if st.form_submit_button("Registrar", type="primary"):
                    entrada = entrada.strip()
                    if not entrada:
                        res = ResultadoMarcado(False, "error", "Ingresá un DNI o escaneá una credencial.")
                    elif entrada.upper().startswith("SIA:STUDENT:"):
                        res = registro.procesar_credencial(entrada, docente.id)
                    elif not entrada.replace(".", "").isdigit():
                        res = ResultadoMarcado(False, "error", "El DNI debe contener solo números.")
                    else:
                        res = registro.marcar_por_dni(entrada, docente.id)
                    st.session_state[clave_resultados] = [res]
        for resultado in st.session_state.get(clave_resultados, []):
            _mostrar_resultado(resultado)
    with col_res:
        presentes = registro.presentes()
        kpi_grid([("Presentes registrados", len(presentes), materia.nombre, "azul")])
        if not presentes.empty:
            st.dataframe(presentes[["hora", "alumno", "metodo"]], hide_index=True, width="stretch", height=380)


# ---------------------------------------------------------------- Sábana de asistencia & estadísticas
def _tab_sabana(materia: Materia, materias: list[Materia]) -> None:
    alcance = st.radio("Alcance", ["Materia activa", "Todas mis materias"], horizontal=True, key="alcance_sabana")
    seleccion = [materia] if alcance == "Materia activa" else materias
    ids = [m.id for m in seleccion]
    multi = len(seleccion) > 1
    df = Materia.registros_df(ids)
    if df.empty:
        st.info("Todavía no hay clases con alumnos inscriptos para analizar.")
        return

    resultados: dict[str, str] = {}
    for m in seleccion:
        resultados.update(m.resultados())
    predictor, info, prediccion = _ejecutar_ia(df, resultados, ids, materia.umbral)

    en_riesgo = int((prediccion["nivel"] == "ALTO").sum())
    promedio = df["presente"].mean() * 100
    kpi_grid([
        ("Alumnos", df["clave"].nunique() if multi else df["estudiante_id"].nunique(),
         f"{len(seleccion)} materia(s)", "azul"),
        ("Clases dictadas", df["clase_id"].nunique(), f"Última: {df['fecha'].max()}", "celeste"),
        ("Asistencia promedio", f"{promedio:.1f}%", f"Umbral {materia.umbral:.0f}%",
         tono_porcentaje(promedio, materia.umbral)),
        ("En riesgo alto", en_riesgo, f"{(prediccion['nivel'] == 'MEDIO').sum()} en riesgo medio",
         "rojo" if en_riesgo else "verde"),
    ])

    if not multi:
        st.markdown(f"### 🧮 Sábana de asistencia · {escape(materia.nombre)}")
        st.markdown(_chips_materia(materia), unsafe_allow_html=True)
        st.caption("✅ presente · 🕒 tarde · 📝 justificado · ❌ ausente · — no inscripto a esa fecha")
        matriz = materia.matriz_asistencia()
        st.dataframe(
            matriz, width="stretch",
            column_config={"% asistencia": st.column_config.ProgressColumn(
                "% asistencia", min_value=0, max_value=100, format="%.0f%%")},
        )
        st.download_button(
            "⬇️ Descargar sábana (CSV)", matriz.to_csv().encode("utf-8-sig"),
            file_name=f"sabana_{materia.codigo_clase}.csv", mime="text/csv",
        )

    st.markdown("### 🤖 Alertas de riesgo (IA)")
    _seccion_ia(predictor, info, prediccion)

    st.markdown("### 📈 Estadísticas")
    df = df.copy()
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df["semana"] = df["fecha_dt"].dt.to_period("W-SUN").dt.start_time
    c1, c2 = st.columns(2)
    with c1:
        semanal = (df.groupby(["semana", "materia"] if multi else ["semana"])["presente"]
                   .mean().mul(100).reset_index(name="asistencia"))
        fig = px.line(semanal, x="semana", y="asistencia", color="materia" if multi else None,
                      markers=True, title="Tendencia semanal de asistencia (%)",
                      labels={"semana": "Semana", "asistencia": "% asistencia"})
        fig.add_hline(y=materia.umbral, line_dash="dash", line_color=TONOS["rojo"],
                      annotation_text=f"Umbral {materia.umbral:.0f}%")
        fig.update_yaxes(range=[0, 105])
        st.plotly_chart(estilo_plotly(fig), width="stretch")
    with c2:
        df["dia"] = df["fecha_dt"].dt.dayofweek
        por_dia = df.groupby("dia")["presente"].mean().mul(100).reindex(range(7)).dropna().reset_index()
        por_dia["dia"] = por_dia["dia"].map(lambda d: DIAS[int(d)])
        fig = px.bar(por_dia, x="dia", y="presente", title="Asistencia por día de la semana (%)",
                     labels={"dia": "", "presente": "% asistencia"}, color="presente",
                     color_continuous_scale=["#9CC7EE", "#1E9BD7", "#0B5CAD"], range_color=[0, 100])
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(estilo_plotly(fig), width="stretch")

    etiqueta = df["alumno"] + (" · " + df["materia"] if multi else "")
    mapa = df.assign(etiqueta=etiqueta).pivot_table(index="etiqueta", columns="fecha", values="presente", aggfunc="max")
    mapa = mapa.loc[mapa.mean(axis=1).sort_values().index]
    fig = px.imshow(
        mapa, color_continuous_scale=[[0, "#F28B82"], [1, "#1E9BD7"]], zmin=0, zmax=1, aspect="auto",
        title="Mapa de calor (celeste = presente, rojo = ausente, vacío = no inscripto)",
        labels={"x": "Clase", "y": "", "color": "Presente"},
    )
    fig.update_coloraxes(showscale=False)
    fig.update_traces(xgap=2, ygap=2, hovertemplate="%{y}<br>%{x}: %{z}<extra></extra>")
    st.plotly_chart(estilo_plotly(fig, alto=max(320, 26 * len(mapa) + 120)), width="stretch")

    ranking = prediccion.sort_values("pct_asistencia", ascending=False)
    ranking = ranking.assign(etiqueta=ranking["alumno"] + (" · " + ranking["materia"] if multi else ""))
    fig = px.bar(
        ranking, x="pct_asistencia", y="etiqueta", color="nivel", color_discrete_map=COLORES_NIVEL,
        orientation="h", title="Asistencia por alumno y nivel de riesgo",
        labels={"pct_asistencia": "% asistencia", "etiqueta": "", "nivel": "Riesgo"},
    )
    fig.add_vline(x=materia.umbral, line_dash="dash", line_color=TONOS["rojo"])
    st.plotly_chart(estilo_plotly(fig, alto=max(320, 24 * len(prediccion) + 120)), width="stretch")

    st.download_button(
        "⬇️ Exportar registros completos (CSV)",
        df.drop(columns=["fecha_dt", "semana", "dia"]).to_csv(index=False).encode("utf-8-sig"),
        file_name="asistencia_sia.csv", mime="text/csv",
    )


def _ejecutar_ia(df: pd.DataFrame, resultados: dict, ids: list[int], umbral: float):
    huella = (
        tuple(ids), umbral, tuple(sorted(resultados.items())),
        int(pd.util.hash_pandas_object(df[["clave", "fecha", "presente"]], index=False).sum()),
    )
    cache = st.session_state.get("ia_cache")
    if cache is None or cache["huella"] != huella:
        with st.spinner("Entrenando modelo Random Forest…"):
            predictor = PredictorRiesgoIA(umbral=umbral)
            info = predictor.entrenar(df, resultados)
            prediccion = predictor.predecir(df)
        cache = {"huella": huella, "predictor": predictor, "info": info, "prediccion": prediccion}
        st.session_state["ia_cache"] = cache
    return cache["predictor"], cache["info"], cache["prediccion"]


def _seccion_ia(predictor: PredictorRiesgoIA, info: dict, prediccion: pd.DataFrame) -> None:
    if info["modo"] == "random_forest":
        auc = (f" · AUC validación cruzada: **{info['auc_cv']:.2f}** ({info['folds']} folds agrupados por alumno)"
               if "auc_cv" in info else "")
        st.success(f"Modelo **Random Forest** entrenado con {info['muestras']} instantáneas de "
                   f"{info['alumnos']} trayectorias ({info['etiquetas_docente']} con resultado final cargado){auc}.")
    else:
        st.info(f"🧪 Modo heurístico: {info.get('motivo', '')}")

    altos = prediccion[prediccion["nivel"] == "ALTO"]
    col_alertas, col_imp = st.columns([1.4, 1])
    with col_alertas:
        if altos.empty:
            st.markdown("🎉 No hay alumnos en riesgo alto.")
        for fila in altos.head(8).itertuples():
            alerta(f"🔴 {fila.alumno} · {fila.materia}", f"Riesgo {fila.prob_riesgo:.0%} — {fila.motivos}",
                   COLORES_NIVEL["ALTO"])
        if len(altos) > 8:
            st.caption(f"…y {len(altos) - 8} alumnos más en riesgo alto (ver tabla).")
    with col_imp:
        importancias = predictor.importancias()
        if not importancias.empty:
            fig = px.bar(importancias, x="importancia", y="feature", orientation="h",
                         title="Importancia de variables del modelo", labels={"feature": "", "importancia": ""},
                         color_discrete_sequence=[TONOS["azul"]])
            st.plotly_chart(estilo_plotly(fig, alto=300), width="stretch")

    tabla = prediccion.copy()
    tabla["nivel"] = tabla["nivel"].map(lambda n: f"{EMOJI_NIVEL[n]} {n}")
    tabla["prob_riesgo"] = tabla["prob_riesgo"] * 100
    st.dataframe(
        tabla[["nivel", "alumno", "dni", "materia", "pct_asistencia", "prob_riesgo",
               "max_consecutivas", "racha_actual", "ausencias_recientes", "n_clases", "motivos"]],
        hide_index=True, width="stretch",
        column_config={
            "nivel": "Nivel",
            "alumno": "Alumno",
            "dni": "DNI",
            "materia": "Materia",
            "pct_asistencia": st.column_config.ProgressColumn("% asistencia", min_value=0, max_value=100, format="%.0f%%"),
            "prob_riesgo": st.column_config.ProgressColumn("Prob. riesgo", min_value=0, max_value=100, format="%.0f%%"),
            "max_consecutivas": ETIQUETAS_FEATURES["max_consecutivas"],
            "racha_actual": ETIQUETAS_FEATURES["racha_actual"],
            "ausencias_recientes": ETIQUETAS_FEATURES["ausencias_recientes"],
            "n_clases": ETIQUETAS_FEATURES["n_clases"],
            "motivos": "Motivos",
        },
    )
