"""Panel del Docente: materias, clase en vivo, lector QR, historial y estadísticas, justificativos."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from html import escape

import pandas as pd
import streamlit as st

from core.reportes import (
    clave_alfabetica,
    guardar_reporte_clase,
    nombre_reporte_clase,
    reporte_clase,
)
from core.validaciones import (
    COMISIONES,
    CURSOS,
    DIAS_SEMANA,
    HORAS,
    MAX_PDF_BYTES,
    TURNOS,
    error_pdf,
)
from models.asistencia import (
    VENTANA_SEGUNDOS,
    RegistroAsistencia,
    ResultadoMarcado,
    segundos_restantes,
)
from models.institucion import Institucion, opcion
from models.materia import RESULTADOS, Materia
from models.persona import Docente
from models.predictor_ia import ETIQUETAS_FEATURES, PredictorRiesgoIA
from utils.qr import (
    contenido_asistencia,
    contenido_inscripcion,
    decodificar_qr,
    generar_qr_png,
    url_publica,
)
from views import auth, graficos
from views.escaner import escaner_qr
from views.exportar import boton_drive, exportaciones
from views.justificativos import bandeja
from views.styles import (
    COLORES_CONDICION,
    COLORES_NIVEL,
    alerta,
    aviso_camara,
    banner_riesgo,
    chips,
    codigo,
    encabezado,
    estado_html,
    grilla_historial,
    guia_panel,
    kpi_grid,
    leyenda_historial,
    mini_barra,
    mostrar_errores,
    tabla_html,
    tono_porcentaje,
)

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
TAB_HISTORIAL = "Historial y estadísticas"
ESTADOS = {"presente": "Presente", "tarde": "Tarde", "justificado": "Justificado", "ausente": "Ausente"}
METODOS = {"qr_credencial": "QR credencial", "qr_clase": "QR de clase", "pin": "PIN", "manual": "Manual",
           "preceptoria": "Preceptoría", "justificativo": "Justificativo"}
AVISO_CAMARA = ("Si el navegador pide permiso, elegí «Permitir». Con varias cámaras, elegí la correcta en la lista. "
                "Si no funciona, usá «Manual / lector USB» e ingresá el DNI.")


def _institucion() -> Institucion:
    return Institucion.obtener(st.session_state["institucion_id"])


def render(docente: Docente) -> None:
    institucion = _institucion()
    carreras = institucion.carreras_de_docente(docente.id)
    encabezado("Panel docente", " · ".join(n for _, n in carreras) or "Tus materias, tus clases y la asistencia")
    materias = _filtrar_por_carrera(Materia.de_docente(docente.id, institucion.id), carreras)
    _banner_riesgo(materias)
    materia = _selector_materia(materias)
    guia_panel([
        ("Materias", "Tus materias con horario, alumnos y el QR para inscribirse."),
        ("Clase en vivo", "Abrí la clase de hoy: proyectá el QR y los alumnos dan el presente."),
        ("Lector QR", "Escaneá la credencial de un alumno o cargá su DNI."),
        (TAB_HISTORIAL, "Asistencia por clase y alumno, y quiénes están en riesgo."),
    ])

    tabs = st.tabs(["Materias", "Clase en vivo", "Lector QR", TAB_HISTORIAL, "Justificativos"])
    with tabs[0]:
        _tab_materias(docente, institucion, materias, carreras)
    with tabs[4]:
        bandeja(institucion.id, docente.id, docente_id=docente.id, clave="doc")
    if materia is None:
        for tab in tabs[1:4]:
            with tab:
                st.info("Creá tu primera materia en la pestaña **Materias** para comenzar.")
        return
    with tabs[1]:
        _tab_clase(docente, materia)
    with tabs[2]:
        _tab_lector(docente, materia)
    with tabs[3]:
        _tab_historial(materia, materias)


def _filtrar_por_carrera(materias: list[Materia], carreras: list[tuple[int, str]]) -> list[Materia]:
    if len(carreras) < 2:
        return materias
    opciones = [None] + [c for c, _ in carreras]
    nombres = dict(carreras)
    with st.sidebar:
        elegida = st.selectbox("Carrera", opciones, format_func=lambda c: "Todas mis carreras" if c is None else nombres[c],
                               key="filtro_carrera")
    return materias if elegida is None else [m for m in materias if m.carrera_id == elegida]


def _selector_materia(materias: list[Materia]) -> Materia | None:
    if not materias:
        return None
    por_id = {m.id: m for m in materias}
    if st.session_state.get("materia_activa") not in por_id:
        st.session_state["materia_activa"] = materias[0].id
    with st.sidebar:
        seleccion = st.selectbox(
            "Materia activa", list(por_id),
            format_func=lambda i: f"{por_id[i].nombre} · {por_id[i].curso_comision}".rstrip(" ·"), key="materia_activa",
        )
    return por_id[seleccion]


def _chips_materia(materia: Materia, carreras: dict[int, str] | None = None) -> str:
    return chips([
        (carreras or {}).get(materia.carrera_id, ""),
        materia.curso_comision, f"Turno {materia.turno}" if materia.turno else "", materia.dia_horario,
        f"Regulariza {materia.umbral:.0f}% · Promociona {materia.umbral_promocion:.0f}%",
    ])


# ---------------------------------------------------------------- Alerta de riesgo (automática)
def _riesgo_materia(materia: Materia) -> pd.DataFrame:
    df = Materia.registros_df([materia.id])
    if df.empty:
        return pd.DataFrame()
    prediccion = PredictorRiesgoIA(umbral=materia.umbral).predecir(df)
    return prediccion[prediccion["nivel"] == "ALTO"]


def _banner_riesgo(materias: list[Materia]) -> None:
    items = [f"{f.alumno} · {m.nombre}: {f.motivos}" for m in materias for f in _riesgo_materia(m).itertuples()]
    if items:
        visibles = items[:3] + ([f"…y {len(items) - 3} más (ver «{TAB_HISTORIAL}»)."] if len(items) > 3 else [])
        banner_riesgo(f"{len(items)} alumno(s) pueden perder la regularidad", visibles)


# ---------------------------------------------------------------- Materias
def _campos_materia(prefijo: str, institucion: Institucion, carreras: list[tuple[int, str]],
                    materia: Materia | None = None) -> tuple[dict, object]:
    def indice(opciones, valor):
        return list(opciones).index(valor) if valor in opciones else None

    todas = carreras or [(int(r.id), r.nombre) for r in institucion.carreras().itertuples()]
    nombres_carrera = dict(todas)
    c0, c1 = st.columns([2, 1])
    nombre = c0.text_input("Nombre de la materia *", value=materia.nombre if materia else "",
                           placeholder="Programación I", max_chars=120, key=f"{prefijo}_nombre")
    carrera = c1.selectbox("Carrera", list(nombres_carrera), index=indice(list(nombres_carrera), materia.carrera_id if materia else None),
                           format_func=nombres_carrera.get, placeholder="Sin carrera" if todas else "La dirección no cargó carreras",
                           key=f"{prefijo}_carrera", disabled=not todas)
    c2, c3, c4 = st.columns(3)
    curso = c2.selectbox("Curso *", CURSOS, index=indice(CURSOS, materia.curso if materia else None),
                         placeholder="Elegí el curso", key=f"{prefijo}_curso")
    comision = c3.selectbox("Comisión *", COMISIONES, index=indice(COMISIONES, materia.comision if materia else None),
                            placeholder="Elegí la comisión", key=f"{prefijo}_comision")
    turno = c4.selectbox("Turno *", TURNOS, index=indice(TURNOS, materia.turno if materia else None),
                         placeholder="Elegí el turno", key=f"{prefijo}_turno")
    dias = st.multiselect("Días de cursada *", DIAS_SEMANA, default=materia.dias if materia else [],
                          placeholder="Elegí uno o más días", key=f"{prefijo}_dias")
    h1, h2 = st.columns(2)
    hora_inicio = h1.selectbox("Desde *", HORAS, index=indice(HORAS, materia.hora_inicio if materia else None),
                               placeholder="Hora de inicio", key=f"{prefijo}_inicio", help="Intervalos de 10 minutos.")
    hora_fin = h2.selectbox("Hasta *", HORAS, index=indice(HORAS, materia.hora_fin if materia else None),
                            placeholder="Hora de fin", key=f"{prefijo}_fin")
    u1, u2 = st.columns(2)
    umbral = u1.slider("Asistencia para regularizar (%)", 50, 100,
                       int(materia.umbral if materia else institucion.umbral_regular), step=5, key=f"{prefijo}_umbral")
    promocion = u2.slider("Asistencia para promocionar (%)", 50, 100,
                          int(materia.umbral_promocion if materia else institucion.umbral_promocion), step=5,
                          key=f"{prefijo}_promocion")
    descripcion = st.text_area("Descripción (opcional)", value=materia.descripcion if materia else "",
                               placeholder="Aula, modalidad, observaciones…", height=80, max_chars=500, key=f"{prefijo}_desc")
    programa = st.file_uploader("Programa de la materia (PDF, opcional)", type=["pdf"], key=f"{prefijo}_pdf",
                                help=f"Máximo {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    return dict(nombre=nombre, curso=curso, comision=comision, turno=turno, dias=dias, hora_inicio=hora_inicio,
                hora_fin=hora_fin, umbral=umbral, umbral_promocion=promocion, descripcion=descripcion,
                carrera_id=carrera), programa


def _validar_programa(programa) -> tuple[bytes | None, str | None]:
    if programa is None:
        return None, None
    contenido = programa.getvalue()
    return contenido, error_pdf(programa.name, contenido)


def _tab_materias(docente: Docente, institucion: Institucion, materias: list[Materia],
                  carreras: list[tuple[int, str]]) -> None:
    with st.expander("Nueva materia", expanded=not materias, icon=":material/add:"):
        with st.form("form_materia", clear_on_submit=False):
            datos, programa = _campos_materia("nueva", institucion, carreras)
            enviar = st.form_submit_button("Crear materia", type="primary")
        if enviar:
            contenido, error = _validar_programa(programa)
            try:
                if error:
                    raise ValueError(error)
                nueva = Materia.crear(docente.id, institucion.id, **datos)
                if contenido:
                    nueva.guardar_programa(programa.name, contenido)
            except ValueError as exc:
                mostrar_errores(str(exc).split("\n"))
            else:
                for clave in [k for k in st.session_state if str(k).startswith("nueva_")]:
                    del st.session_state[clave]
                st.session_state["materia_activa"] = nueva.id
                st.toast(f"Materia creada · código {nueva.codigo_clase}")
                st.rerun()

    nombres_carrera = {int(r.id): r.nombre for r in institucion.carreras(solo_activas=False).itertuples()}
    for materia in materias:
        _tarjeta_materia(materia, institucion, carreras, nombres_carrera)


def _tarjeta_materia(materia: Materia, institucion: Institucion, carreras: list[tuple[int, str]],
                     nombres_carrera: dict[int, str]) -> None:
    with st.container(border=True):
        izquierda, derecha = st.columns([3, 1.2])
        alumnos = materia.alumnos()
        clases = materia.clases()
        en_riesgo = len(_riesgo_materia(materia))
        with izquierda:
            st.markdown(f"#### {escape(materia.nombre)}")
            st.markdown(_chips_materia(materia, nombres_carrera), unsafe_allow_html=True)
            if materia.descripcion:
                st.caption(materia.descripcion)
            st.markdown("Código para unirse:")
            codigo(materia.codigo_clase)
            kpi_grid([
                ("Alumnos", len(alumnos), "inscriptos", "neutro"),
                ("Clases", len(clases), "dictadas", "neutro"),
                ("En riesgo", en_riesgo, "pueden quedar libres", "rojo" if en_riesgo else "verde",
                 100 * en_riesgo / len(alumnos) if len(alumnos) else 0),
            ])
            b1, b2, b3 = st.columns(3)
            if b1.button("Regenerar código", key=f"regen_{materia.id}", width="stretch", icon=":material/refresh:",
                         help="Invalida el código y el QR anteriores para nuevas inscripciones."):
                materia.regenerar_codigo()
                st.rerun()
            with b2.popover("Editar materia", width="stretch", icon=":material/edit:"):
                _form_edicion(materia, institucion, carreras)
            programa = materia.programa()
            if programa:
                b3.download_button("Programa (PDF)", programa[1], file_name=programa[0], mime="application/pdf",
                                   key=f"prog_{materia.id}", width="stretch", icon=":material/description:")
            else:
                b3.button("Sin programa", key=f"prog_{materia.id}", disabled=True, width="stretch",
                          help="Podés adjuntarlo desde «Editar materia».")
        with derecha:
            contenido = contenido_inscripcion(materia.codigo_clase, materia.firma_inscripcion, materia.payload_inscripcion)
            st.image(generar_qr_png(contenido, box_size=8), caption="QR de inscripción", width="stretch")
            st.download_button("Descargar QR", generar_qr_png(contenido, box_size=14),
                               file_name=f"inscripcion_{materia.codigo_clase}.png", mime="image/png",
                               key=f"dl_qr_{materia.id}", width="stretch", icon=":material/download:")
        with st.expander(f"Alumnos inscriptos ({len(alumnos)})"):
            _editor_alumnos(materia, alumnos)


def _form_edicion(materia: Materia, institucion: Institucion, carreras: list[tuple[int, str]]) -> None:
    with st.form(f"edit_{materia.id}"):
        datos, programa = _campos_materia(f"edit_{materia.id}", institucion, carreras, materia)
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
        if st.form_submit_button("Guardar resultados"):
            for estudiante_id, resultado in elecciones.items():
                materia.establecer_resultado(estudiante_id, None if resultado == "en curso" else resultado)
            st.success("Resultados guardados.")
    with st.popover("Dar de baja a un alumno"):
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
            etiqueta = "Reabrir clase de hoy" if clase else "Iniciar clase de hoy"
            if st.form_submit_button(etiqueta, type="primary"):
                materia.abrir_clase(" ".join(tema.split()))
                st.session_state.pop("clase_recien_cerrada", None)
                st.rerun()
        _historial_clases(materia)
        return

    registro = RegistroAsistencia(clase["id"])
    st.markdown(f"#### Clase en curso · {escape(materia.nombre)} · {pd.to_datetime(clase['fecha']):%d/%m/%Y}"
                + (f" — {escape(clase['tema'])}" if clase["tema"] else ""))
    inst = _institucion()
    if materia.hora_inicio:
        st.caption(f"Se registra «tarde» a partir de las {_hora_tarde(materia.hora_inicio, inst.tolerancia_tarde)} "
                   f"(inicio {materia.hora_inicio} + {inst.tolerancia_tarde} min de tolerancia).")
    if url_publica() is None:
        st.caption("La app corre en local: el QR contiene un código SIA firmado que se lee con el escáner de la app. "
                   "Al publicarla, el QR pasa a ser un enlace que funciona con la cámara del celular.")
    col_qr, col_live = st.columns([1.1, 1])
    with col_qr:
        _qr_dinamico(registro.clase_id)
    with col_live:
        _panel_presentes(registro.clase_id, materia.id)
    st.divider()
    _marcado_manual(docente, materia, registro)
    st.divider()
    if st.button("Cerrar clase y generar reporte PDF", type="primary", icon=":material/lock:",
                 help="Cierra el registro de asistencia y genera el reporte para Preceptoría."):
        materia.cerrar_clase(registro.clase_id)
        guardar_reporte_clase(registro.clase_id)
        st.session_state["clase_recien_cerrada"] = {"clase_id": registro.clase_id, "materia_id": materia.id}
        st.rerun()


def _hora_tarde(hora_inicio: str, tolerancia: int) -> str:
    h, m = map(int, hora_inicio.split(":"))
    total = h * 60 + m + tolerancia
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def _panel_reporte(clase_id: int, recien_cerrada: bool = False) -> None:
    pdf = reporte_clase(clase_id) or guardar_reporte_clase(clase_id)
    nombre = nombre_reporte_clase(clase_id)
    with st.container(border=True):
        if recien_cerrada:
            st.success("Clase cerrada. El reporte de asistencia en PDF está listo para Preceptoría.")
        c1, c2 = st.columns(2)
        c1.download_button("Descargar reporte PDF", pdf, file_name=nombre, mime="application/pdf",
                           key=f"pdf_clase_{clase_id}", width="stretch", type="primary", icon=":material/download:")
        with c2:
            boton_drive(nombre, pdf, f"drive_clase_{clase_id}")


@st.fragment(run_every=timedelta(seconds=2))
def _qr_dinamico(clase_id: int) -> None:
    """QR y PIN se recalculan cada 2 s: el cambio de ventana (30 s) se refleja enseguida, sin desfase."""
    auth.registrar_actividad()  # proyectar el QR cuenta como actividad del docente
    registro = RegistroAsistencia(clase_id)
    with st.container(border=True):
        st.markdown("**QR de asistencia** — proyectalo para que los alumnos lo escaneen")
        st.caption("Quien todavía no tiene cuenta puede crear su acceso al escanearlo.")
        st.image(generar_qr_png(contenido_asistencia(registro.generar_token()), box_size=12), width="stretch")
        restante = segundos_restantes()
        st.progress(restante / VENTANA_SEGUNDOS, text=f"Código firmado · cambia en {restante} s")
        st.caption("PIN para quienes no pueden usar la cámara")
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
        ("Presentes", f"{len(presentes)}/{inscriptos}", "registrados hoy", "neutro", pct),
        ("Asistencia de hoy", f"{pct:.0f}%", "en tiempo real", tono_porcentaje(pct, materia.umbral if materia else 75)),
    ])
    tabla_html(_filas_presentes(presentes), {"hora": "Hora", "alumno": "Alumno/a", "estado": "Estado", "metodo": "Registro"},
               vacio="Esperando los primeros registros…")


def _marcado_manual(docente: Docente, materia: Materia, registro: RegistroAsistencia) -> None:
    st.markdown("##### Registro manual")
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
    estado = c2.selectbox("Estado", ["presente", "tarde", "justificado"], key=f"estado_{registro.clase_id}",
                          format_func=lambda e: ESTADOS[e])
    if c3.button("Registrar", type="primary", width="stretch", key=f"btn_manual_{registro.clase_id}"):
        if not elegidos:
            st.error("Elegí al menos un alumno para registrar.")
        else:
            for estudiante_id in elegidos:
                registro.marcar(estudiante_id, "manual", docente.id, estado=estado, docente_id=docente.id)
            st.rerun()
    if ids_presentes:
        with st.popover("Corregir o anular un registro"):
            elegido = st.selectbox("Alumno", sorted(ids_presentes), format_func=lambda i: opciones.get(i, str(i)),
                                   key=f"corr_{registro.clase_id}")
            nuevo = st.selectbox("Nuevo estado", ["presente", "tarde", "justificado", "ausente"],
                                 format_func=lambda e: "Anular (ausente)" if e == "ausente" else ESTADOS[e],
                                 key=f"corr_estado_{registro.clase_id}")
            if st.button("Aplicar", key=f"corr_btn_{registro.clase_id}"):
                if nuevo == "ausente":
                    registro.anular(elegido)
                else:
                    registro.actualizar_estado(elegido, nuevo)
                st.rerun()


def _historial_clases(materia: Materia) -> None:
    clases = materia.clases()
    if clases.empty:
        return
    st.markdown("##### Clases anteriores")
    tabla_html(
        [{"fecha": pd.to_datetime(f.fecha).strftime("%d/%m/%Y"), "tema": f.tema or None, "presentes": f.presentes,
          "estado": "Abierta" if f.abierta else "Cerrada"} for f in clases.itertuples()],
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
        c2.download_button("Descargar PDF", pdf, file_name=nombre_reporte_clase(elegida), mime="application/pdf",
                           key=f"dl_reporte_hist_{materia.id}", width="stretch", icon=":material/download:")


# ---------------------------------------------------------------- Lector QR
def _mostrar_resultado(resultado: ResultadoMarcado) -> None:
    if resultado.estado == "registrado":
        st.success(resultado.mensaje)
    elif resultado.estado == "duplicado":
        st.info(resultado.mensaje)
    else:
        st.error(resultado.mensaje)


def _tab_lector(docente: Docente, materia: Materia) -> None:
    clase = materia.clase_de_hoy()
    if clase is None or not clase["abierta"]:
        st.warning("Primero iniciá la clase de hoy en **Clase en vivo**.")
        return
    registro = RegistroAsistencia(clase["id"])
    clave_resultados = f"lector_resultados_{clase['id']}"
    st.markdown(f"#### Escanear credenciales · {escape(materia.nombre)}")
    col_cam, col_res = st.columns([1.2, 1])
    with col_cam:
        modo = st.radio("Modo", ["Cámara en vivo", "Foto", "Manual / lector USB"], horizontal=True,
                        key=f"modo_lector_{clase['id']}", label_visibility="collapsed")
        nuevos: list[ResultadoMarcado] = []
        if modo == "Cámara en vivo":
            aviso_camara(AVISO_CAMARA)
            texto = escaner_qr(f"docente_{clase['id']}", perfil="docente")
            if texto:
                nuevos.append(registro.procesar_credencial(texto, docente.id))
        elif modo == "Foto":
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
            st.session_state[clave_resultados] = (nuevos + st.session_state.get(clave_resultados, []))[:5]
        for resultado in st.session_state.get(clave_resultados, []):
            _mostrar_resultado(resultado)
    with col_res:
        presentes = registro.presentes()
        kpi_grid([("Presentes registrados", len(presentes), materia.nombre, "neutro")])
        tabla_html(_filas_presentes(presentes)[:15], {"hora": "Hora", "alumno": "Alumno/a", "metodo": "Registro"},
                   vacio="Todavía no hay registros.")


# ---------------------------------------------------------------- Historial y estadísticas
def _tab_historial(materia: Materia, materias: list[Materia]) -> None:
    alcance = st.radio("Alcance", ["Materia activa", "Todas mis materias"], horizontal=True, key="alcance_historial")
    seleccion = [materia] if alcance == "Materia activa" else materias
    ids = [m.id for m in seleccion]
    multi = len(seleccion) > 1
    df = Materia.registros_df(ids)
    if df.empty:
        st.info("Todavía no hay clases con alumnos inscriptos para analizar.")
        return
    por_id = {m.id: m for m in seleccion}
    resultados: dict[str, str] = {}
    for m in seleccion:
        resultados.update(m.resultados())
    predictor, info, prediccion = _ejecutar_ia(df, resultados, ids, materia.umbral)
    prediccion = prediccion.assign(condicion=[por_id[int(c.split("-")[0])].condicion(p)
                                              for c, p in zip(prediccion["clave"], prediccion["pct_asistencia"], strict=True)])

    promedio = df["presente"].mean() * 100
    condicion = prediccion["condicion"].value_counts()
    kpi_grid([
        ("Asistencia promedio", f"{promedio:.1f}%", f"{df['clase_id'].nunique()} clases dictadas",
         tono_porcentaje(promedio, materia.umbral)),
        ("Promocionan", int(condicion.get("Promociona", 0)), f"≥ {materia.umbral_promocion:.0f}% de asistencia", "verde",
         100 * condicion.get("Promociona", 0) / max(1, len(prediccion))),
        ("Regulares", int(condicion.get("Regular", 0)), f"≥ {materia.umbral:.0f}%", "neutro",
         100 * condicion.get("Regular", 0) / max(1, len(prediccion))),
        ("Libres", int(condicion.get("Libre", 0)), "debajo del umbral", "rojo" if condicion.get("Libre", 0) else "neutro",
         100 * condicion.get("Libre", 0) / max(1, len(prediccion))),
    ])

    if not multi:
        st.markdown(f"#### Historial de asistencia · {escape(materia.nombre)}")
        leyenda_historial()
        grupos = []
        for _clave, sub in sorted(df.groupby("clave"), key=lambda par: clave_alfabetica(par[1]["alumno"].iloc[0])):
            sub = sub.sort_values("fecha")
            pct = 100 * sub["presente"].mean()
            grupos.append((sub["alumno"].iloc[0], f"{materia.condicion(pct)} · {int(sub['presente'].sum())}/{len(sub)} clases",
                           pct, tono_porcentaje(pct, materia.umbral),
                           list(zip(sub["fecha"], sub["estado"], strict=True))))
        grilla_historial(grupos)

    st.markdown("#### Alerta de riesgo")
    _seccion_ia(predictor, info, prediccion)

    st.markdown("#### Estadísticas")
    df = df.copy()
    df["fecha_dt"] = pd.to_datetime(df["fecha"])
    df["semana"] = df["fecha_dt"].dt.to_period("W-SUN").dt.start_time
    c1, c2 = st.columns(2)
    with c1:
        semanal = (df.groupby(["semana", "materia"] if multi else ["semana"])["presente"].mean().mul(100)
                   .reset_index(name="asistencia"))
        graficos.tendencia(semanal, "semana", "asistencia", "materia" if multi else None, materia.umbral,
                           "Asistencia semanal")
    with c2:
        df["dia"] = df["fecha_dt"].dt.dayofweek
        por_dia = df.groupby("dia")["presente"].mean().mul(100).reindex(range(7)).dropna().reset_index()
        por_dia["dia"] = por_dia["dia"].map(lambda d: DIAS[int(d)])
        graficos.barras(por_dia, "dia", "presente", "Asistencia por día de la semana", umbral=materia.umbral)
    etiqueta = "alumno" if not multi else "alumno_materia"
    df["alumno_materia"] = df["alumno"] + " · " + df["materia"]
    graficos.mapa_asistencia(df, etiqueta, "Asistencia por clase")
    ranking = prediccion.assign(alumno_materia=prediccion["alumno"] + " · " + prediccion["materia"])
    graficos.ranking_riesgo(ranking, etiqueta, materia.umbral, "Asistencia por alumno y nivel de riesgo")

    st.markdown("#### Exportar reportes")
    st.caption("El Excel incluye el historial completo (una columna por clase), la condición y el riesgo de cada alumno.")
    registros = df.drop(columns=["fecha_dt", "semana", "dia", "clave", "alumno_materia"])
    matriz = (df.assign(estado=df["estado"].str.capitalize())
                .pivot_table(index=["materia", "alumno", "dni"], columns="fecha", values="estado", aggfunc="first")
                .reset_index())
    riesgo = prediccion[["nivel", "condicion", "alumno", "dni", "materia", "pct_asistencia", "prob_riesgo", "motivos"]].copy()
    riesgo["pct_asistencia"] = riesgo["pct_asistencia"].round(1)
    riesgo["prob_riesgo"] = (riesgo["prob_riesgo"] * 100).round(0)
    nombre = "historial_" + (materia.codigo_clase if not multi else "todas_mis_materias")
    exportaciones(nombre, {"Registros": registros, "Historial": matriz, "Condición y riesgo": riesgo}, f"export_{nombre}")


def _ejecutar_ia(df: pd.DataFrame, resultados: dict, ids: list[int], umbral: float):
    usar_ia = opcion("prediccion_ia")
    huella = (tuple(ids), umbral, usar_ia, tuple(sorted(resultados.items())),
              int(pd.util.hash_pandas_object(df[["clave", "fecha", "presente"]], index=False).sum()))
    cache = st.session_state.get("ia_cache")
    if cache is None or cache["huella"] != huella:
        predictor = PredictorRiesgoIA(umbral=umbral)
        if usar_ia:
            with st.spinner("Entrenando el modelo…"):
                info = predictor.entrenar(df, resultados)
        else:
            info = {"modo": "heuristico", "motivo": "La predicción con IA está desactivada por la administración. "
                                                    "El riesgo se calcula con reglas de asistencia."}
        cache = {"huella": huella, "predictor": predictor, "info": info, "prediccion": predictor.predecir(df)}
        st.session_state["ia_cache"] = cache
    return cache["predictor"], cache["info"], cache["prediccion"]


def _seccion_ia(predictor: PredictorRiesgoIA, info: dict, prediccion: pd.DataFrame) -> None:
    if info["modo"] == "random_forest":
        auc = (f" Precisión estimada (AUC, validación cruzada por alumno): **{info['auc_cv']:.2f}**." if "auc_cv" in info else "")
        st.caption(f"Predicción con IA (Random Forest) entrenada con {info['muestras']} registros de "
                   f"{info['alumnos']} trayectorias, {info['etiquetas_docente']} con resultado final cargado.{auc}")
    else:
        st.caption(f"Análisis por reglas de asistencia — {info.get('motivo', '')}")
    altos = prediccion[prediccion["nivel"] == "ALTO"]
    col_alertas, col_imp = st.columns([1.4, 1])
    with col_alertas:
        if altos.empty:
            st.markdown("No hay alumnos en riesgo alto.")
        for fila in altos.head(8).itertuples():
            alerta(f"{fila.alumno} · {fila.materia}", f"Riesgo {fila.prob_riesgo:.0%} — {fila.motivos}", COLORES_NIVEL["ALTO"])
        if len(altos) > 8:
            st.caption(f"…y {len(altos) - 8} alumnos más en riesgo alto (ver tabla).")
    with col_imp:
        graficos.importancias(predictor.importancias())
    nivel = {"ALTO": "Alto", "MEDIO": "Medio", "BAJO": "Bajo"}
    tono = {"ALTO": "rojo", "MEDIO": "ambar", "BAJO": "verde"}
    tabla_html(
        [{"nivel": estado_html(nivel[f.nivel], COLORES_NIVEL[f.nivel]), "alumno": f.alumno, "materia": f.materia,
          "condicion": estado_html(f.condicion, COLORES_CONDICION[f.condicion]),
          "asistencia": mini_barra(f.pct_asistencia, tono[f.nivel]), "riesgo": f"{f.prob_riesgo:.0%}",
          "consecutivas": f.max_consecutivas, "motivos": f.motivos} for f in prediccion.itertuples()],
        {"nivel": "Riesgo", "alumno": "Alumno/a", "materia": "Materia", "condicion": "Condición",
         "asistencia": "Asistencia", "riesgo": "Prob.", "consecutivas": ETIQUETAS_FEATURES["max_consecutivas"],
         "motivos": "Motivos"},
    )
