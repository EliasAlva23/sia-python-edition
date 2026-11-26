"""Panel de Preceptoría: asistencia (registro manual y justificativos), docentes (alta con QR de invitación,
clave temporal y baja), vinculación de alumnos, clases del día y consulta."""
from __future__ import annotations

from datetime import timedelta
from html import escape

import streamlit as st

from core import validaciones as val
from core.reportes import (
    clave_alfabetica,
    guardar_reporte_clase,
    nombre_reporte_clase,
    reporte_clase,
)
from core.tiempo import hoy
from models import cuentas, demo
from models import justificativo as jus
from models.asistencia import RegistroAsistencia
from models.institucion import Institucion
from models.materia import Materia
from models.persona import Persona, RepositorioPersonas
from views import personal
from views.justificativos import bandeja
from views.styles import (
    COLORES_CONDICION,
    ESTADO,
    encabezado,
    estado_html,
    kpi_grid,
    mini_barra,
    mostrar_errores,
    tabla_html,
    tono_porcentaje,
)

ESTADOS = ["presente", "tarde", "justificado", "ausente"]
NOMBRE_ESTADO = {"presente": "Presente", "tarde": "Tarde", "justificado": "Justificado", "ausente": "Ausente"}


def render(preceptor: Persona) -> None:
    institucion = Institucion.obtener(st.session_state["institucion_id"])
    encabezado("Panel de Preceptoría", "Supervisás docentes y materias y cuidás la asistencia de la institución")
    materias = Materia.de_institucion(institucion.id)
    pendientes = len(jus.listar(institucion.id, "pendiente"))
    abiertas_hoy = sum(1 for m in materias if (c := m.clase_de_hoy()) and c["abierta"])
    docentes = cuentas.personal_con_estado(institucion, "docente")
    sin_activar = int(docentes["pendiente"].sum()) if not docentes.empty else 0
    kpi_grid([
        ("Materias activas", len(materias), institucion.nombre_corto, "neutro"),
        ("Clases abiertas hoy", abiertas_hoy, f"{hoy():%d/%m/%Y}", "neutro"),
        ("Docentes", len(docentes), f"{sin_activar} sin activar su acceso" if sin_activar else "todos con acceso activo",
         "ambar" if sin_activar else "neutro"),
        ("Justificativos pendientes", pendientes, "para revisar", "ambar" if pendientes else "neutro"),
    ])
    tabs = st.tabs(["Registro manual", "Docentes", "Justificativos", "Clases de hoy", "Vincular alumno",
                    "Consultar alumno"])
    with tabs[0]:
        _registro_manual(preceptor, institucion, materias)
    with tabs[1]:
        _docentes(preceptor, institucion, docentes)
    with tabs[2]:
        _justificativos(preceptor, institucion, materias)
    with tabs[3]:
        _clases_de_hoy(materias)
    with tabs[4]:
        _vincular(preceptor, institucion, materias)
    with tabs[5]:
        _consultar_alumno(institucion)


def _elegir_materia(materias: list[Materia], clave: str, institucion: Institucion) -> Materia | None:
    if not materias:
        st.info("La institución todavía no tiene materias activas.")
        return None
    carreras = {int(r.id): r.nombre for r in institucion.carreras().itertuples()}
    if carreras:
        filtro = st.selectbox("Carrera", [None, *carreras], format_func=lambda c: "Todas" if c is None else carreras[c],
                              key=f"{clave}_carrera")
        materias = [m for m in materias if filtro is None or m.carrera_id == filtro]
    por_id = {m.id: m for m in materias}
    if not por_id:
        st.caption("No hay materias en esa carrera.")
        return None
    elegida = st.selectbox("Materia", list(por_id), key=f"{clave}_materia",
                           format_func=lambda i: f"{por_id[i].nombre} · {por_id[i].curso_comision}".rstrip(" ·"))
    return por_id[elegida]


# ---------------------------------------------------------------- registro manual
def _registro_manual(preceptor: Persona, institucion: Institucion, materias: list[Materia]) -> None:
    st.caption("Para casos excepcionales: alumnos sin dispositivo, sin conexión o clases que el docente no pudo abrir. "
               "Queda registrado como «Preceptoría».")
    c1, c2 = st.columns([2, 1])
    with c1:
        materia = _elegir_materia(materias, "reg", institucion)
    if materia is None:
        return
    fecha = c2.date_input("Fecha de la clase", value=hoy(), max_value=hoy(), min_value=hoy() - timedelta(days=120),
                          format="DD/MM/YYYY", key="reg_fecha")
    clase = materia.clase_en_fecha(fecha)
    alumnos = materia.alumnos()
    if alumnos.empty:
        st.info("La materia no tiene alumnos inscriptos. Usá «Vincular alumno».")
        return
    if clase is None:
        st.info(f"No hay clase registrada el {fecha:%d/%m/%Y} para esta materia. Al guardar se crea el registro.")
        actuales: dict[int, str] = {}
    else:
        estado_clase = "abierta" if clase["abierta"] else "cerrada"
        st.caption(f"Clase del {fecha:%d/%m/%Y} ({estado_clase})" + (f" · {clase['tema']}" if clase["tema"] else ""))
        actuales = {int(f.id): f.estado for f in RegistroAsistencia(clase["id"]).presentes().itertuples()}
    alumnos = alumnos.sort_values("apellido", key=lambda s: s.map(clave_alfabetica))
    with st.form(f"form_registro_{materia.id}_{fecha}"):
        todos = st.selectbox("Marcar a todos como…", [None, *ESTADOS], format_func=lambda e: "— no cambiar —" if e is None else NOMBRE_ESTADO[e])
        elecciones = {}
        for fila in alumnos.itertuples():
            a, b = st.columns([2, 1], vertical_alignment="center")
            a.markdown(f"**{escape(fila.apellido)}, {escape(fila.nombre)}** · DNI {escape(fila.dni)}")
            actual = actuales.get(int(fila.id), "ausente")
            elecciones[int(fila.id)] = b.selectbox("Estado", ESTADOS, index=ESTADOS.index(actual), format_func=NOMBRE_ESTADO.get,
                                                   key=f"reg_{materia.id}_{fecha}_{fila.id}", label_visibility="collapsed")
        guardar = st.form_submit_button("Guardar asistencia", type="primary")
    if guardar:
        clase = materia.clase_en_fecha(fecha, crear=True)
        registro = RegistroAsistencia(clase["id"])
        cambios = 0
        try:
            for estudiante_id, estado in elecciones.items():
                nuevo = todos or estado
                if actuales.get(estudiante_id, "ausente") != nuevo:
                    registro.registrar_estado(estudiante_id, nuevo, preceptor.id, institucion.id)
                    cambios += 1
        except ValueError as exc:
            st.error(str(exc))
            return
        if not clase["abierta"]:
            guardar_reporte_clase(clase["id"])  # el PDF de la clase refleja la corrección
        st.toast(f"Asistencia guardada · {cambios} cambio(s)")
        st.rerun()


# ---------------------------------------------------------------- vincular alumno
def _vincular(preceptor: Persona, institucion: Institucion, materias: list[Materia]) -> None:
    st.caption("Para alumnos que no pudieron inscribirse solos. Si todavía no tienen cuenta, se crea con una clave "
               "temporal y un QR de invitación; al ingresar, el alumno crea su propia contraseña.")
    personal.tarjeta_credencial("pre_alumno")
    materia = _elegir_materia(materias, "vin", institucion)
    if materia is None:
        return
    dni = st.text_input("DNI del alumno", max_chars=10, key="vin_dni")
    if not dni.strip():
        return
    error = val.error_dni(dni)
    if error:
        st.error(error)
        return
    persona = RepositorioPersonas.por_dni(dni)
    if persona is not None:
        st.markdown(f"**{escape(persona.nombre_completo)}** · {escape(persona.email)}")
        inscripto = materia.esta_inscripto(persona.id)
        if inscripto:
            st.info(f"Ya está inscripto/a en {materia.nombre}.")
        elif st.button(f"Inscribir en {materia.nombre}", type="primary", key="vin_inscribir"):
            ok, mensaje = materia.inscribir(persona.id)
            (st.success if ok else st.error)(mensaje)
        return
    st.info("No hay una cuenta con ese DNI. Completá los datos para crearla e inscribir al alumno.")
    with st.form("form_alta_alumno"):
        f1 = st.columns(2)
        nombre = f1[0].text_input("Nombre *")
        apellido = f1[1].text_input("Apellido *")
        email = st.text_input("Email *", placeholder="nombre@dominio.com")
        crear = st.form_submit_button("Crear cuenta e inscribir", type="primary")
    if not crear:
        return
    errores = val.requeridos({"Nombre": nombre, "Apellido": apellido, "Email": email})
    errores += [e for e in (val.error_nombre(nombre, "Nombre"), val.error_nombre(apellido, "Apellido"),
                            val.error_email(email)) if e]
    if errores:
        mostrar_errores(errores)
        return
    try:
        alta = cuentas.crear_o_asignar(institucion.id, "estudiante", dni, val.limpiar(nombre), val.limpiar(apellido),
                                       email.strip(), creado_por=preceptor.id)
    except ValueError as exc:
        mostrar_errores([str(exc)])
        return
    materia.inscribir(alta.persona.id)
    personal.guardar_credencial("pre_alumno", alta.persona, "estudiante", alta.clave_temporal, alta.invitacion,
                                institucion)
    st.toast(f"Cuenta creada e inscripta en {materia.nombre}")
    st.rerun()


# ---------------------------------------------------------------- docentes
def _docentes(preceptor: Persona, institucion: Institucion, docentes) -> None:
    personal.tarjeta_credencial("pre_docente")
    st.markdown("#### Docentes de la institución")
    st.caption("«Pendiente de activar» significa que todavía no creó su contraseña: entregale la clave temporal o el "
               "QR de invitación. Si pierde el acceso, restablecelo desde «Supervisar o gestionar un docente».")
    tabla_html(
        [{"docente": f"{f.apellido}, {f.nombre}", "dni": f.dni, "materias": int(f.materias),
          "acceso": estado_html("Pendiente de activar", ESTADO["advertencia"]) if f.pendiente
          else estado_html("Activo", ESTADO["bueno"]),
          "ingreso": cuentas.momento_legible(f.ultimo_uso)} for f in docentes.itertuples()],
        {"docente": "Docente", "dni": "DNI", "materias": "Materias", "acceso": "Acceso", "ingreso": "Última actividad"},
        vacio="Todavía no hay docentes. Dalos de alta con el formulario de abajo.",
    )
    alta, gestion = st.columns([1, 1.15], gap="medium")
    with alta:
        personal.form_alta(institucion, ("docente",), "pre_docente", preceptor.id, titulo="Dar de alta un docente")
    with gestion:
        docente_id = _gestionar_docente(preceptor, institucion, docentes)
    if docente_id is not None:
        _materias_del_docente(docente_id, institucion)


def _materias_del_docente(docente_id: int, institucion: Institucion) -> None:
    st.markdown("##### Materias del docente elegido")
    filas = []
    for m in Materia.de_docente(docente_id, institucion.id):
        clase = m.clase_de_hoy()
        hoy_txt = "Sin abrir" if clase is None else ("Abierta" if clase["abierta"] else "Cerrada")
        filas.append({"materia": m.nombre, "curso": m.curso_comision or None, "horario": m.dia_horario or None,
                      "alumnos": len(m.alumnos()), "hoy": hoy_txt})
    tabla_html(filas, {"materia": "Materia", "curso": "Curso", "horario": "Horario", "alumnos": "Alumnos",
                       "hoy": "Clase de hoy"}, vacio="No tiene materias activas en la institución.")


def _gestionar_docente(preceptor: Persona, institucion: Institucion, docentes) -> int | None:
    with st.container(border=True):
        st.markdown("##### Supervisar o gestionar un docente")
        if docentes.empty:
            st.caption("Cuando des de alta docentes, vas a poder ver sus materias, restablecer su acceso o darlos de baja.")
            return None
        nombres = {int(f.id): f"{f.apellido}, {f.nombre} · DNI {f.dni}" for f in docentes.itertuples()}
        docente_id = st.selectbox("Docente", list(nombres), format_func=nombres.get, key="pre_doc_sel")
        st.caption("Sus materias se muestran debajo. Desde acá podés restablecer su acceso o darlo de baja.")
        if demo.es_cuenta_demo(docentes.set_index("id").loc[docente_id, "dni"]):
            st.caption("Es una cuenta de demostración: su acceso no se restablece ni se da de baja.")
            return docente_id
        c1, c2 = st.columns(2)
        if cuentas.puede_gestionar_clave(docente_id, institucion.id):
            if c1.button("Restablecer acceso", key=f"pre_reset_{docente_id}", icon=":material/key:", width="stretch",
                         help="Genera una clave temporal y un QR de invitación nuevos y cierra sus sesiones abiertas."):
                temporal, token = cuentas.restablecer_clave(docente_id, institucion.id, "docente", preceptor.id)
                persona = RepositorioPersonas.obtener(docente_id)
                personal.guardar_credencial("pre_docente", persona, "docente", temporal, token, institucion,
                                            motivo="restablecer")
                st.rerun()
        else:
            c1.caption("Su cuenta también se usa en otro rol o institución: el acceso lo restablece la "
                       "Administración general.")
        with c2.popover("Dar de baja", icon=":material/person_remove:", width="stretch"):
            st.markdown(f"**{escape(nombres[docente_id])}**")
            st.caption("Deja de tener acceso como docente en esta institución y se cierran sus sesiones. Sus materias "
                       "y el historial de asistencia se conservan para consulta.")
            confirmar = st.checkbox("Confirmo la baja", key=f"pre_baja_ok_{docente_id}")
            if st.button("Dar de baja", type="primary", disabled=not confirmar, key=f"pre_baja_{docente_id}"):
                cuentas.dar_de_baja(docente_id, institucion.id, "docente")
                st.toast("Docente dado de baja")
                st.rerun()
    return docente_id


# ---------------------------------------------------------------- justificativos
def _justificativos(preceptor: Persona, institucion: Institucion, materias: list[Materia]) -> None:
    bandeja(institucion.id, preceptor.id, clave="pre")
    st.divider()
    st.markdown("#### Justificación masiva")
    st.caption("Justifica en un solo paso a varios alumnos (por ejemplo, una salida educativa o un corte de transporte). "
               "No pisa presentes ni tardes ya registrados.")
    por_id = {m.id: m for m in materias}
    materia_id = st.selectbox("Materia", [None, *por_id], key="mas_materia",
                              format_func=lambda i: "Todas las materias de cada alumno" if i is None else por_id[i].nombre)
    if materia_id:
        alumnos = por_id[materia_id].alumnos()
    else:
        alumnos = institucion.personas("estudiante")
    opciones = {int(f.id): f"{f.apellido}, {f.nombre} ({f.dni})" for f in alumnos.itertuples()}
    with st.form("form_masivo"):
        elegidos = st.multiselect("Alumnos", list(opciones), format_func=opciones.get, placeholder="Elegí los alumnos")
        c1, c2 = st.columns(2)
        desde = c1.date_input("Desde", value=hoy(), max_value=hoy(), format="DD/MM/YYYY", key="mas_desde")
        hasta = c2.date_input("Hasta", value=hoy(), max_value=hoy(), format="DD/MM/YYYY", key="mas_hasta")
        motivo = st.text_input("Motivo", max_chars=300, placeholder="Ej. Salida educativa al museo")
        enviar = st.form_submit_button("Justificar", type="primary")
    if enviar:
        try:
            cantidad, clases = jus.justificar_masivo(institucion.id, elegidos, materia_id, desde, hasta, motivo, preceptor.id)
        except ValueError as exc:
            mostrar_errores(str(exc).split("\n"))
        else:
            st.success(f"{cantidad} alumno(s) justificados · {clases} clase(s) marcadas como «Justificado».")


# ---------------------------------------------------------------- clases de hoy
def _clases_de_hoy(materias: list[Materia]) -> None:
    filas, cerradas = [], {}
    for m in materias:
        clase = m.clase_de_hoy()
        if clase is None:
            estado, presentes = "Sin abrir", None
        else:
            estado = "Abierta" if clase["abierta"] else "Cerrada"
            presentes = len(RegistroAsistencia(clase["id"]).presentes())
            if not clase["abierta"]:
                cerradas[clase["id"]] = m.nombre
        filas.append({"materia": m.nombre, "curso": m.curso_comision, "horario": m.dia_horario or None,
                      "estado": estado, "presentes": presentes, "inscriptos": len(m.alumnos())})
    tabla_html(filas, {"materia": "Materia", "curso": "Curso", "horario": "Horario", "estado": "Estado",
                       "presentes": "Presentes", "inscriptos": "Inscriptos"}, vacio="No hay materias activas.")
    if cerradas:
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        elegida = c1.selectbox("Reporte PDF de una clase cerrada hoy", list(cerradas), format_func=cerradas.get, key="pre_pdf")
        pdf = reporte_clase(elegida) or guardar_reporte_clase(elegida)
        c2.download_button("Descargar PDF", pdf, file_name=nombre_reporte_clase(elegida), mime="application/pdf",
                           width="stretch", icon=":material/download:", key="pre_pdf_dl")


# ---------------------------------------------------------------- consultar alumno
def _consultar_alumno(institucion: Institucion) -> None:
    busqueda = st.text_input("Buscar por DNI o apellido", key="pre_buscar").strip().lower()
    if len(busqueda) < 3:
        st.caption("Escribí al menos 3 caracteres.")
        return
    alumnos = institucion.personas("estudiante")
    coincidencias = alumnos[alumnos["dni"].str.contains(busqueda) | alumnos["apellido"].str.lower().str.contains(busqueda)]
    if coincidencias.empty:
        st.info("No se encontraron alumnos.")
        return
    for alumno in coincidencias.head(10).itertuples():
        materias = Materia.de_estudiante(int(alumno.id), institucion.id)
        df = Materia.registros_df([m.id for m in materias], estudiante_id=int(alumno.id))
        with st.container(border=True):
            st.markdown(f"**{escape(alumno.apellido)}, {escape(alumno.nombre)}** · DNI {escape(alumno.dni)} · {escape(alumno.email)}")
            filas = []
            for m in materias:
                sub = df[df["materia_id"] == m.id]
                pct = 100 * sub["presente"].mean() if len(sub) else 0.0
                condicion = m.condicion(pct) if len(sub) else "Sin clases"
                filas.append({"materia": m.nombre, "asistencia": mini_barra(pct, tono_porcentaje(pct, m.umbral)) if len(sub) else None,
                              "clases": f"{int(sub['presente'].sum())}/{len(sub)}",
                              "condicion": estado_html(condicion, COLORES_CONDICION.get(condicion, "#6B7280"))})
            tabla_html(filas, {"materia": "Materia", "asistencia": "Asistencia", "clases": "Clases", "condicion": "Condición"},
                       vacio="No está inscripto/a en materias de la institución.")
    if len(coincidencias) > 10:
        st.caption(f"…y {len(coincidencias) - 10} más. Afiná la búsqueda.")
