"""Panel del Docente: materias, clase en vivo, lector QR e Historial de asistencia & estadísticas."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from core.reportes import clave_alfabetica, guardar_reporte_clase, nombre_reporte_clase, reporte_clase
from core.validaciones import COMISIONES, CURSOS, DIAS_SEMANA, HORAS, MAX_PDF_BYTES, TURNOS, error_pdf
from models.asistencia import VENTANA_SEGUNDOS, RegistroAsistencia, ResultadoMarcado, segundos_restantes
from models.materia import RESULTADOS, Materia
from models.persona import Docente
from models.predictor_ia import ETIQUETAS_FEATURES, PredictorRiesgoIA
from utils.qr import contenido_asistencia, contenido_inscripcion, decodificar_qr, generar_qr_png, url_publica
from views import auth
from views.escaner import escaner_qr
from views.exportar import boton_drive, exportaciones
from views.styles import (
    AZUL, COLORES_NIVEL, EMOJI_NIVEL, LAVANDA, LILA, TONOS, alerta, aviso_camara, banner_riesgo, chips, codigo,
    estilo_plotly, grilla_historial, hero, kpi_grid, mini_barra, mostrar_errores, tabla_html, tono_porcentaje,
)

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
TAB_HISTORIAL = "📋 Historial de asistencia"
ESTADOS = {"presente": "✅ Presente", "tarde": "🕒 Tarde", "justificado": "📝 Justificado", "ausente": "❌ Ausente"}
METODOS = {"qr_credencial": "QR credencial", "qr_clase": "QR de clase", "pin": "PIN", "manual": "Manual"}
AVISO_CAMARA = ("📌 Si tu navegador solicita permisos, haz clic en 'Permitir' para activar la cámara. Si tenés varias "
                "cámaras, elegí la correcta en la lista. Si no funciona, usá «Manual / lector USB» e ingresá el DNI.")


def render(docente: Docente) -> None:
    hero(f"Hola, {docente.nombre} 👋", "Panel docente · materias, asistencia por QR e historial de asistencia")
    materias = Materia.de_docente(docente.id)
    _banner_riesgo(materias)
    materia = _selector_materia(materias)

    tabs = st.tabs(["📚 Materias", "📡 Clase en vivo", "📷 Lector QR", TAB_HISTORIAL])
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
        _tab_historial(materia, materias)


def _selector_materia(materias: list[Materia]) -> Materia | None:
    if not materias:
        return None
    por_id = {m.id: m for m in materias}
    if st.session_state.get("materia_activa") not in por_id:
        st.session_state["materia_activa"] = materias[0].id
    with st.sidebar:
        st.markdown("##### 🎯 Materia activa")
        seleccion = st.selectbox(
            "Materia activa", list(por_id),
            format_func=lambda i: f"{por_id[i].nombre} · {por_id[i].curso_comision}".rstrip(" ·"),
            key="materia_activa", label_visibility="collapsed",
        )
    return por_id[seleccion]


def _chips_materia(materia: Materia) -> str:
    return chips([
        f"🎓 {materia.curso_comision}" if materia.curso_comision else "",
        f"🕑 Turno {materia.turno}" if materia.turno else "",
        f"🗓️ {materia.dia_horario}" if materia.dia_horario else "",
    ])


# ---------------------------------------------------------------- Alerta de riesgo (automática)
def _riesgo_materia(materia: Materia) -> pd.DataFrame:
    """Alumnos en riesgo según reglas de asistencia (rápido: no entrena el modelo)."""
    df = Materia.registros_df([materia.id])
    if df.empty:
        return pd.DataFrame()
    prediccion = PredictorRiesgoIA(umbral=materia.umbral).predecir(df)
    return prediccion[prediccion["nivel"] == "ALTO"]


def _banner_riesgo(materias: list[Materia]) -> None:
    items = []
    for materia in materias:
        for fila in _riesgo_materia(materia).itertuples():
            items.append(f"{fila.alumno} · {materia.nombre}: {fila.motivos}")
    if items:
        visibles = items[:3] + ([f"…y {len(items) - 3} más (ver «{TAB_HISTORIAL}»)."] if len(items) > 3 else [])
        banner_riesgo(f"Alerta de riesgo: {len(items)} alumno(s) pueden perder la regularidad", visibles)


# ---------------------------------------------------------------- Materias
def _campos_materia(prefijo: str, materia: Materia | None = None) -> dict:
    def indice(opciones, valor):
        return opciones.index(valor) if valor in opciones else None

    nombre = st.text_input("Nombre de la materia *", value=materia.nombre if materia else "",
                           placeholder="Programación I", max_chars=120, key=f"{prefijo}_nombre")
    c1, c2, c3 = st.columns(3)
    curso = c1.selectbox("Curso *", CURSOS, index=indice(CURSOS, materia.curso if materia else None),
                         placeholder="Elegí el curso", key=f"{prefijo}_curso")
    comision = c2.selectbox("Comisión *", COMISIONES, index=indice(COMISIONES, materia.comision if materia else None),
                            placeholder="Elegí la comisión", key=f"{prefijo}_comision")
    turno = c3.selectbox("Turno *", TURNOS, index=indice(TURNOS, materia.turno if materia else None),
                         placeholder="Elegí el turno", key=f"{prefijo}_turno")
    dias = st.multiselect("Días de cursada *", DIAS_SEMANA, default=materia.dias if materia else [],
                          placeholder="Elegí uno o más días", key=f"{prefijo}_dias")
    h1, h2, h3 = st.columns(3)
    hora_inicio = h1.selectbox("Desde *", HORAS, index=indice(HORAS, materia.hora_inicio if materia else None),
                               placeholder="Hora de inicio", key=f"{prefijo}_inicio")
    hora_fin = h2.selectbox("Hasta *", HORAS, index=indice(HORAS, materia.hora_fin if materia else None),
                            placeholder="Hora de fin", key=f"{prefijo}_fin")
    umbral = h3.slider("Umbral (%)", 50, 100, int(materia.umbral) if materia else 75, step=5,
                       key=f"{prefijo}_umbral", help="Asistencia mínima para mantener la regularidad.")
    descripcion = st.text_area("Descripción (opcional)", value=materia.descripcion if materia else "",
                               placeholder="Aula, modalidad, observaciones…", height=80, max_chars=500,
                               key=f"{prefijo}_desc")
    programa = st.file_uploader(
        "Programa de la materia (PDF, opcional)", type=["pdf"], key=f"{prefijo}_pdf",
        help=f"Currícula u observaciones. Máximo {MAX_PDF_BYTES // (1024 * 1024)} MB.",
    )
    return dict(nombre=nombre, curso=curso, comision=comision, turno=turno, dias=dias, hora_inicio=hora_inicio,
                hora_fin=hora_fin, umbral=umbral, descripcion=descripcion), programa


def _validar_programa(programa) -> tuple[bytes | None, str | None]:
    if programa is None:
        return None, None
    contenido = programa.getvalue()
    return contenido, error_pdf(programa.name, contenido)


def _tab_materias(docente: Docente, materias: list[Materia]) -> None:
    with st.expander("➕ Nueva materia", expanded=not materias):
        with st.form("form_materia", clear_on_submit=False):
            datos, programa = _campos_materia("nueva")
            enviar = st.form_submit_button("Crear materia", type="primary")
        if enviar:
            contenido, error = _validar_programa(programa)
            try:
                if error:
                    raise ValueError(error)
                nueva = Materia.crear(docente.id, **datos)
                if contenido:
                    nueva.guardar_programa(programa.name, contenido)
            except ValueError as exc:
                mostrar_errores(str(exc).split("\n"))
            else:
                for clave in [k for k in st.session_state if str(k).startswith("nueva_")]:
                    del st.session_state[clave]
                st.session_state["materia_activa"] = nueva.id
                st.toast(f"Materia creada · código {nueva.codigo_clase}", icon="✅")
                st.rerun()

    for materia in materias:
        _tarjeta_materia(materia)


def _tarjeta_materia(materia: Materia) -> None:
    with st.container(border=True):
        izquierda, derecha = st.columns([3, 1.3])
        alumnos = materia.alumnos()
        clases = materia.clases()
        en_riesgo = len(_riesgo_materia(materia))
        with izquierda:
            st.markdown(f"### {escape(materia.nombre)}")
            st.markdown(_chips_materia(materia), unsafe_allow_html=True)
            if materia.descripcion:
                st.caption(materia.descripcion)
            st.markdown("**Código de clase** (para unirse):")
            codigo(materia.codigo_clase)
            kpi_grid([
                ("Alumnos", len(alumnos), "inscriptos", "azul"),
                ("Clases", len(clases), "dictadas", "lavanda"),
                ("En riesgo", en_riesgo, f"umbral {materia.umbral:.0f}%", "rojo" if en_riesgo else "verde"),
            ])
            b1, b2, b3 = st.columns(3)
            if b1.button("🔄 Regenerar código", key=f"regen_{materia.id}", width="stretch",
                         help="Invalida el código y el QR anteriores para nuevas inscripciones."):
                materia.regenerar_codigo()
                st.rerun()
            with b2.popover("⚙️ Editar materia", width="stretch"):
                _form_edicion(materia)
            programa = materia.programa()
            if programa:
                b3.download_button("📄 Programa (PDF)", programa[1], file_name=programa[0], mime="application/pdf",
                                   key=f"prog_{materia.id}", width="stretch")
            else:
                b3.button("📄 Sin programa", key=f"prog_{materia.id}", disabled=True, width="stretch",
                          help="Podés adjuntarlo desde «Editar materia».")
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
        datos, programa = _campos_materia(f"edit_{materia.id}", materia)
        quitar_programa = materia.tiene_programa() and st.checkbox("Quitar el programa PDF actual")
        archivar = st.checkbox("Archivar materia (deja de mostrarse)")
        enviar = st.form_submit_button("Guardar cambios", type="primary")
    if not enviar:
        return
    if archivar:
        materia.archivar()
        st.rerun()
    contenido, error = _validar_programa(programa)
    try:
        if error:
            raise ValueError(error)
        materia.actualizar(**datos)
        if contenido:
            materia.guardar_programa(programa.name, contenido)
        elif quitar_programa:
            materia.borrar_programa()
    except ValueError as exc:
        mostrar_errores(str(exc).split("\n"))
        return
    st.rerun()


def _editor_alumnos(materia: Materia, alumnos: pd.DataFrame) -> None:
    """Resultados finales: una fila por alumno con su selector (se apila en celulares, sin scroll lateral)."""
    if alumnos.empty:
        st.caption("Todavía no hay inscriptos. Compartí el código o el QR de inscripción.")
        return
    alumnos = alumnos.sort_values("apellido", key=lambda s: s.map(clave_alfabetica))
    opciones = ["en curso", *RESULTADOS]
    with st.form(f"resultados_{materia.id}"):
        st.caption("Resultado final de cada alumno: alimenta el entrenamiento del modelo de IA.")
        elecciones = {}
        for fila in alumnos.itertuples():
            c1, c2 = st.columns([2, 1], vertical_alignment="center")
            c1.markdown(f"**{escape(fila.apellido)}, {escape(fila.nombre)}** · DNI {escape(fila.dni)}")
            actual = fila.resultado if isinstance(fila.resultado, str) else "en curso"
            elecciones[int(fila.id)] = c2.selectbox("Resultado", opciones, index=opciones.index(actual),
                                                    key=f"res_{materia.id}_{fila.id}", label_visibility="collapsed")
        if st.form_submit_button("💾 Guardar resultados"):
            for estudiante_id, resultado in elecciones.items():
                materia.establecer_resultado(estudiante_id, None if resultado == "en curso" else resultado)
            st.success("Resultados guardados.")
    with st.popover("🗑️ Dar de baja a un alumno"):
        nombres = {int(f.id): f"{f.apellido}, {f.nombre} ({f.dni})" for f in alumnos.itertuples()}
        elegido = st.selectbox("Alumno", list(nombres), format_func=nombres.get, key=f"baja_{materia.id}")
        if st.button("Confirmar baja", key=f"conf_baja_{materia.id}", type="primary"):
            materia.desinscribir(elegido)
            st.rerun()


# ---------------------------------------------------------------- Clase en vivo
def _tab_clase(docente: Docente, materia: Materia) -> None:
    clase = materia.clase_de_hoy()
    cerrada = st.session_state.get("clase_recien_cerrada")
    if cerrada and cerrada.get("materia_id") == materia.id:
        _panel_reporte(cerrada["clase_id"], recien_cerrada=True)
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
                st.session_state.pop("clase_recien_cerrada", None)
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
    st.divider()
    if st.button("⏹️ Cerrar clase y generar reporte PDF", type="primary",
                 help="Cierra el registro de asistencia y genera el reporte para Preceptoría."):
        materia.cerrar_clase(registro.clase_id)
        guardar_reporte_clase(registro.clase_id)
        st.session_state["clase_recien_cerrada"] = {"clase_id": registro.clase_id, "materia_id": materia.id}
        st.rerun()


def _panel_reporte(clase_id: int, recien_cerrada: bool = False) -> None:
    pdf = reporte_clase(clase_id) or guardar_reporte_clase(clase_id)
    nombre = nombre_reporte_clase(clase_id)
    with st.container(border=True):
        if recien_cerrada:
            st.success("✅ Clase cerrada. El reporte de asistencia en PDF está listo para Preceptoría.")
        c1, c2 = st.columns(2)
        c1.download_button("📄 Descargar reporte PDF", pdf, file_name=nombre, mime="application/pdf",
                           key=f"pdf_clase_{clase_id}", width="stretch", type="primary")
        with c2:
            boton_drive(nombre, pdf, f"drive_clase_{clase_id}")


@st.fragment(run_every=timedelta(seconds=2))
def _qr_dinamico(clase_id: int) -> None:
    """QR y PIN se recalculan cada 2 s: el cambio de ventana (30 s) se refleja enseguida, sin desfase."""
    auth.registrar_actividad()  # proyectar el QR cuenta como actividad del docente
    registro = RegistroAsistencia(clase_id)
    with st.container(border=True):
        st.markdown("**QR dinámico de asistencia** — proyectalo para que los alumnos lo escaneen")
        st.image(generar_qr_png(contenido_asistencia(registro.generar_token()), box_size=12), width="stretch")
        restante = segundos_restantes()
        st.progress(restante / VENTANA_SEGUNDOS, text=f"🔐 Firmado con SIA_SECRET · rota en {restante} s")
        st.markdown("PIN para quienes no pueden usar la cámara:")
        codigo(registro.generar_pin(), grande=True)


def _filas_presentes(presentes: pd.DataFrame) -> list[dict]:
    return [{"hora": f.hora, "alumno": f.alumno, "estado": ESTADOS.get(f.estado, f.estado),
             "metodo": METODOS.get(f.metodo, f.metodo)} for f in presentes.itertuples()]


@st.fragment(run_every=timedelta(seconds=4))
def _panel_presentes(clase_id: int, materia_id: int) -> None:
    materia = Materia.obtener(materia_id)
    presentes = RegistroAsistencia(clase_id).presentes()
    inscriptos = len(materia.alumnos()) if materia else 0
    pct = 100 * len(presentes) / inscriptos if inscriptos else 0
    kpi_grid([
        ("Presentes", f"{len(presentes)} / {inscriptos}", "registrados hoy", "azul"),
        ("Asistencia de hoy", f"{pct:.0f}%", "en tiempo real", tono_porcentaje(pct, materia.umbral if materia else 75)),
    ])
    tabla_html(_filas_presentes(presentes), {"hora": "Hora", "alumno": "Alumno/a", "estado": "Estado", "metodo": "Registro"},
               vacio="Esperando los primeros registros…")


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
    tabla_html(
        [{"fecha": pd.to_datetime(f.fecha).strftime("%d/%m/%Y"), "tema": f.tema or None,
          "presentes": f.presentes, "estado": "🟢 Abierta" if f.abierta else "Cerrada"} for f in clases.itertuples()],
        {"fecha": "Fecha", "tema": "Tema", "presentes": "Presentes", "estado": "Estado"},
    )
    cerradas = clases[clases["abierta"] == 0]
    if not cerradas.empty:
        opciones = {int(f.id): pd.to_datetime(f.fecha).strftime("%d/%m/%Y") + (f" · {f.tema}" if f.tema else "")
                    for f in cerradas.itertuples()}
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        elegida = c1.selectbox("Reporte PDF de una clase cerrada", list(opciones), format_func=opciones.get,
                               key=f"reporte_hist_{materia.id}")
        pdf = reporte_clase(elegida) or guardar_reporte_clase(elegida)
        c2.download_button("📄 Descargar PDF", pdf, file_name=nombre_reporte_clase(elegida), mime="application/pdf",
                           key=f"dl_reporte_hist_{materia.id}", width="stretch")


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

    col_cam, col_res = st.columns([1.2, 1])
    with col_cam:
        modo = st.radio("Modo", ["📷 Cámara en vivo", "📸 Foto", "⌨️ Manual / lector USB"], horizontal=True,
                        key=f"modo_lector_{clase['id']}", label_visibility="collapsed")
        nuevos: list[ResultadoMarcado] = []
        if modo.startswith("📷"):
            aviso_camara(AVISO_CAMARA)
            texto = escaner_qr(f"docente_{clase['id']}", perfil="docente")
            if texto:
                nuevos.append(registro.procesar_credencial(texto, docente.id))
        elif modo.startswith("📸"):
            st.caption("Alternativa para navegadores sin escaneo en vivo: sacá una foto nítida de la credencial.")
            foto = st.camera_input("Credencial QR del alumno", key=f"cam_doc_{clase['id']}")
            if foto is not None:
                huella = hashlib.sha256(foto.getvalue()).hexdigest()
                if st.session_state.get(f"ultima_foto_{clase['id']}") != huella:
                    st.session_state[f"ultima_foto_{clase['id']}"] = huella
                    textos = decodificar_qr(foto.getvalue())
                    nuevos = ([registro.procesar_credencial(t, docente.id) for t in textos] if textos else
                              [ResultadoMarcado(False, "error", "No se detectó ningún QR. Acercá la credencial y reintentá.")])
        else:
            with st.form(f"form_manual_{clase['id']}", clear_on_submit=True):
                entrada = st.text_input("DNI del alumno o contenido de la credencial",
                                        help="Los lectores QR USB escriben el código y envían Enter.")
                if st.form_submit_button("Registrar", type="primary"):
                    entrada = entrada.strip()
                    if not entrada:
                        nuevos = [ResultadoMarcado(False, "error", "Ingresá un DNI o escaneá una credencial.")]
                    elif entrada.upper().startswith("SIA:STUDENT:"):
                        nuevos = [registro.procesar_credencial(entrada, docente.id)]
                    elif not entrada.replace(".", "").isdigit():
                        nuevos = [ResultadoMarcado(False, "error", "El DNI debe contener solo números.")]
                    else:
                        nuevos = [registro.marcar_por_dni(entrada, docente.id)]
        if nuevos:
            # Historial de lecturas de esta sesión (las más nuevas arriba) para escanear varias seguidas.
            st.session_state[clave_resultados] = (nuevos + st.session_state.get(clave_resultados, []))[:5]
        for resultado in st.session_state.get(clave_resultados, []):
            _mostrar_resultado(resultado)
    with col_res:
        presentes = registro.presentes()
        kpi_grid([("Presentes registrados", len(presentes), materia.nombre, "azul")])
        tabla_html(_filas_presentes(presentes)[:15], {"hora": "Hora", "alumno": "Alumno/a", "metodo": "Registro"},
                   vacio="Todavía no hay registros.")


# ---------------------------------------------------------------- Historial de asistencia & estadísticas
def _tab_historial(materia: Materia, materias: list[Materia]) -> None:
    alcance = st.radio("Alcance", ["Materia activa", "Todas mis materias"], horizontal=True, key="alcance_historial")
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
        ("Clases dictadas", df["clase_id"].nunique(), f"Última: {df['fecha'].max()}", "lavanda"),
        ("Asistencia promedio", f"{promedio:.1f}%", f"Umbral {materia.umbral:.0f}%",
         tono_porcentaje(promedio, materia.umbral)),
        ("En riesgo alto", en_riesgo, f"{(prediccion['nivel'] == 'MEDIO').sum()} en riesgo medio",
         "rojo" if en_riesgo else "verde"),
    ])

    if not multi:
        st.markdown(f"### 🗂️ Historial de asistencia · {escape(materia.nombre)}")
        st.markdown(_chips_materia(materia), unsafe_allow_html=True)
        st.caption("✅ presente · 🕒 tarde · 📝 justificado · ❌ ausente — cada ícono es una clase con su fecha.")
        grupos = []
        for _clave, sub in sorted(df.groupby("clave"), key=lambda par: clave_alfabetica(par[1]["alumno"].iloc[0])):
            sub = sub.sort_values("fecha")
            pct = 100 * sub["presente"].mean()
            grupos.append((sub["alumno"].iloc[0], f"DNI {sub['dni'].iloc[0]} · {int(sub['presente'].sum())}/{len(sub)} clases",
                           pct, tono_porcentaje(pct, materia.umbral), list(zip(sub["fecha"], sub["estado"], strict=True))))
        grilla_historial(grupos)

    st.markdown("### 🤖 Alerta de riesgo (IA)")
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
                     color_continuous_scale=[LILA, LAVANDA, AZUL], range_color=[0, 100])
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(estilo_plotly(fig), width="stretch")

    etiqueta = df["alumno"] + (" · " + df["materia"] if multi else "")
    mapa = df.assign(etiqueta=etiqueta).pivot_table(index="etiqueta", columns="fecha", values="presente", aggfunc="max")
    mapa = mapa.loc[mapa.mean(axis=1).sort_values().index]
    fig = px.imshow(
        mapa, color_continuous_scale=[[0, "#E58FA0"], [1, AZUL]], zmin=0, zmax=1, aspect="auto",
        title="Mapa de calor de asistencia",
        labels={"x": "Clase", "y": "", "color": "Presente"},
    )
    fig.update_coloraxes(showscale=False)
    fig.update_traces(xgap=2, ygap=2, hovertemplate="%{y}<br>%{x}: %{z}<extra></extra>")
    st.plotly_chart(estilo_plotly(fig, alto=max(320, 26 * len(mapa) + 120)), width="stretch")
    st.caption("Azul = presente · rosa = ausente · vacío = todavía no inscripto en esa fecha.")

    ranking = prediccion.sort_values("pct_asistencia", ascending=False)
    ranking = ranking.assign(etiqueta=ranking["alumno"] + (" · " + ranking["materia"] if multi else ""))
    fig = px.bar(
        ranking, x="pct_asistencia", y="etiqueta", color="nivel", color_discrete_map=COLORES_NIVEL,
        orientation="h", title="Asistencia por alumno y nivel de riesgo",
        labels={"pct_asistencia": "% asistencia", "etiqueta": "", "nivel": "Riesgo"},
    )
    fig.add_vline(x=materia.umbral, line_dash="dash", line_color=TONOS["rojo"])
    st.plotly_chart(estilo_plotly(fig, alto=max(320, 24 * len(prediccion) + 120)), width="stretch")

    st.markdown("### 📤 Exportar reportes")
    st.caption("El Excel incluye el historial completo (una columna por clase) y el resumen de riesgo.")
    registros = df.drop(columns=["fecha_dt", "semana", "dia", "clave"])
    matriz = (df.assign(estado=df["estado"].str.capitalize())
                .pivot_table(index=["materia", "alumno", "dni"], columns="fecha", values="estado", aggfunc="first")
                .reset_index())
    riesgo = prediccion[["nivel", "alumno", "dni", "materia", "pct_asistencia", "prob_riesgo", "motivos"]].copy()
    riesgo["pct_asistencia"] = riesgo["pct_asistencia"].round(1)
    riesgo["prob_riesgo"] = (riesgo["prob_riesgo"] * 100).round(0)
    nombre = "historial_" + (materia.codigo_clase if not multi else "todas_mis_materias")
    exportaciones(nombre, {"Registros": registros, "Historial": matriz, "Riesgo": riesgo}, f"export_{nombre}")


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
        st.success(f"🤖 **Predicción con IA** (Random Forest) entrenada con {info['muestras']} instantáneas de "
                   f"{info['alumnos']} trayectorias ({info['etiquetas_docente']} con resultado final cargado){auc}.")
    else:
        st.info(f"📏 **Análisis por reglas de asistencia** — {info.get('motivo', '')}")

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

    tono_nivel = {"ALTO": "rojo", "MEDIO": "ambar", "BAJO": "verde"}
    tabla_html(
        [{"nivel": f"{EMOJI_NIVEL[f.nivel]} {f.nivel}", "alumno": f.alumno, "materia": f.materia,
          "asistencia": mini_barra(f.pct_asistencia, tono_nivel[f.nivel]),
          "riesgo": mini_barra(f.prob_riesgo * 100, tono_nivel[f.nivel]),
          "consecutivas": f.max_consecutivas, "motivos": f.motivos} for f in prediccion.itertuples()],
        {"nivel": "Nivel", "alumno": "Alumno/a", "materia": "Materia", "asistencia": "% asistencia",
         "riesgo": "Prob. riesgo", "consecutivas": ETIQUETAS_FEATURES["max_consecutivas"], "motivos": "Motivos"},
    )
