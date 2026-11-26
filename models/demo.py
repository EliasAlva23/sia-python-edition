"""Datos de demostración: una institución de prueba con Preceptoría, Dirección, docentes, 14 alumnos, materias,
historial de asistencia y justificativos, para recorrer todos los paneles con movimiento real.

* Se crean solos al iniciar la app (idempotente: lo que ya existe no se duplica) y se vuelven a crear si el disco
  de Streamlit Cloud se reinicia. Se desactivan con `SIA_DEMO = "0"` en Secrets.
* Viven en una institución aparte («Instituto Demo SIA», enlace `?i=demo`): las cuentas de prueba no ven ni
  tocan datos de las instituciones reales, y no se las puede vincular a ellas.
* La clave de las cuentas de prueba es pública a propósito (se muestra en el acceso). Se puede cambiar con
  `SIA_DEMO_CLAVE` en Secrets. La Administración general NUNCA es una cuenta de prueba: sigue dependiendo de
  `SIA_SUPERADMINS` y `SIA_SUPERADMIN_CLAVE_INICIAL`.
"""
from __future__ import annotations

import random
import threading
from datetime import timedelta

from core import security
from core.database import get_connection
from core.security import config_valor
from core.tiempo import ahora_iso, hoy
from core.validaciones import DIAS_SEMANA

SLUG = "demo"
NOMBRE = "Instituto Demo SIA"
CLAVE_POR_DEFECTO = "Demo2026"  # solo da acceso a la institución de prueba (datos ficticios)

PRECEPTORIA = ("99000001", "Marta", "Díaz")
DIRECCION = ("99000002", "Jorge", "Paz")
DOCENTES = [("99000011", "Laura", "Gómez"), ("99000012", "Pablo", "Ruiz")]
ALUMNOS = [
    ("99100001", "Ana", "Pérez"), ("99100002", "Bruno", "Sosa"), ("99100003", "Camila", "Ríos"),
    ("99100004", "Diego", "Molina"), ("99100005", "Elena", "Vega"), ("99100006", "Facundo", "Ibarra"),
    ("99100007", "Gabriela", "Luna"), ("99100008", "Hernán", "Castro"), ("99100009", "Isabel", "Ortiz"),
    ("99100010", "Joaquín", "Navarro"), ("99100011", "Lucía", "Romero"), ("99100012", "Martín", "Acosta"),
    ("99100013", "Natalia", "Benítez"), ("99100014", "Óscar", "Medina"),
]
# Probabilidad de asistir de cada alumno (en orden): la mayoría regulares, algunos en riesgo y uno libre.
PERFILES = [0.97, 0.94, 0.92, 0.9, 0.88, 0.86, 0.84, 0.82, 0.8, 0.78, 0.74, 0.7, 0.62, 0.5]
CARRERAS = ["Profesorado de Educación Primaria", "Tecnicatura en Desarrollo de Software"]
MATERIAS = [  # (docente, carrera, nombre, curso, comisión, turno, días, inicio, fin)
    (0, 0, "Didáctica General", "1° Año", "Comisión 1", "Mañana", ["Lunes", "Miércoles"], "08:00", "10:00"),
    (0, 0, "Psicología Educacional", "2° Año", "Comisión 1", "Mañana", ["Martes", "Jueves"], "10:00", "12:00"),
    (0, 1, "Programación I", "1° Año", "Comisión 2", "Tarde", ["Lunes", "Viernes"], "14:00", "16:00"),
    (1, 1, "Base de Datos", "2° Año", "Comisión 2", "Noche", ["Martes", "Miércoles", "Jueves"], "19:00", "21:00"),
]
SEMANAS_HISTORIAL = 6

DNIS_DEMO = frozenset([PRECEPTORIA[0], DIRECCION[0], *(d for d, _, _ in DOCENTES), *(d for d, _, _ in ALUMNOS)])
_LOCK = threading.Lock()
_listo_para: set[str] = set()


def habilitada() -> bool:
    return (config_valor("SIA_DEMO", "1") or "1").strip().lower() not in ("0", "no", "false", "off")


def clave() -> str:
    return config_valor("SIA_DEMO_CLAVE") or CLAVE_POR_DEFECTO


def es_cuenta_demo(dni: str | None) -> bool:
    return (dni or "") in DNIS_DEMO


def institucion():
    from models.institucion import Institucion

    with get_connection() as conn:
        fila = conn.execute("SELECT id FROM instituciones WHERE slug = ?", (SLUG,)).fetchone()
    return Institucion.obtener(fila["id"]) if fila else None


def cuentas_de_prueba() -> list[tuple[str, str, str]]:
    """(perfil, usuario, nombre) para mostrar en el acceso."""
    return [("Preceptoría", PRECEPTORIA[0], f"{PRECEPTORIA[1]} {PRECEPTORIA[2]}"),
            ("Docente", DOCENTES[0][0], f"{DOCENTES[0][1]} {DOCENTES[0][2]}"),
            ("Estudiante", ALUMNOS[0][0], f"{ALUMNOS[0][1]} {ALUMNOS[0][2]}"),
            ("Dirección", DIRECCION[0], f"{DIRECCION[1]} {DIRECCION[2]}")]


# ---------------------------------------------------------------- creación idempotente
def asegurar_demo() -> None:
    """Crea lo que falte de la demostración. Una vez por proceso y por base (luego no cuesta nada)."""
    if not habilitada():
        return
    import core.database as database  # se lee en cada llamada: la ruta puede cambiar (pruebas)

    clave_base = str(database.DB_PATH)
    if clave_base in _listo_para:
        return
    with _LOCK:
        if clave_base in _listo_para:
            return
        _crear()
        _listo_para.add(clave_base)


def _crear() -> None:
    from models.institucion import Institucion, asignar_rol
    from models.persona import Directivo, Docente, Estudiante, Preceptor, RepositorioPersonas

    inst = institucion()
    if inst is None:
        inst = Institucion.crear(nombre=NOMBRE, nombre_corto="Demo SIA", slug=SLUG, color_primario="#2E5772",
                                 color_secundario="#3F7C70", umbral_regular=75, umbral_promocion=80, tolerancia_tarde=10)
    for nombre in CARRERAS:
        try:
            inst.crear_carrera(nombre)
        except ValueError:
            pass  # ya existe
    carreras = {f.nombre: int(f.id) for f in inst.carreras(solo_activas=False).itertuples()}

    credencial = None  # un solo hash para todas las cuentas de prueba (son públicas y ficticias)

    def persona(clase, rol, dni, nombre, apellido):
        nonlocal credencial
        existente = RepositorioPersonas.por_dni(dni)
        if existente is None:
            credencial = credencial or security.hash_password(clave())
            existente = clase(dni, nombre, apellido, f"demo{dni}@sia-demo.org", password_hash=credencial[0],
                              salt=credencial[1])
            RepositorioPersonas.registrar(existente)
        asignar_rol(existente.id, inst.id, rol)
        return existente

    persona(Preceptor, "preceptor", *PRECEPTORIA)
    persona(Directivo, "directivo", *DIRECCION)
    docentes = [persona(Docente, "docente", *d) for d in DOCENTES]
    alumnos = [persona(Estudiante, "estudiante", *a) for a in ALUMNOS]
    inst.asignar_carreras(docentes[0].id, list(carreras.values()))
    inst.asignar_carreras(docentes[1].id, [carreras[CARRERAS[1]]])
    materias = _materias(inst, docentes, carreras)
    for indice, materia in enumerate(materias):
        inscriptos = alumnos if indice < 3 else alumnos[:9]
        for alumno in inscriptos:
            materia.inscribir(alumno.id)
        _historial(materia, inscriptos, docentes[MATERIAS[indice][0]].id)
    _justificativos(inst, alumnos, materias)


def _materias(inst, docentes, carreras):
    from models.materia import Materia

    existentes = {m.nombre: m for m in Materia.de_institucion(inst.id)}
    resultado = []
    for docente, carrera, nombre, curso, comision, turno, dias, inicio, fin in MATERIAS:
        materia = existentes.get(nombre)
        if materia is None:
            materia = Materia.crear(docentes[docente].id, inst.id, nombre=nombre, curso=curso, comision=comision,
                                    turno=turno, dias=dias, hora_inicio=inicio, hora_fin=fin,
                                    carrera_id=carreras[CARRERAS[carrera]])
        resultado.append(materia)
    return resultado


def _historial(materia, alumnos, docente_id: int) -> None:
    """Clases cerradas de las últimas semanas con asistencia variada (determinística)."""
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM clases WHERE materia_id = ? LIMIT 1", (materia.id,)).fetchone():
            return
        dias = {DIAS_SEMANA.index(d) for d in materia.dias if d in DIAS_SEMANA}
        azar = random.Random(f"sia-demo-{materia.nombre}")
        inicio = hoy() - timedelta(weeks=SEMANAS_HISTORIAL)
        fechas = [inicio + timedelta(days=i) for i in range(SEMANAS_HISTORIAL * 7) if
                  (inicio + timedelta(days=i)).weekday() in dias and inicio + timedelta(days=i) < hoy()]
        posicion = {dni: i for i, (dni, _, _) in enumerate(ALUMNOS)}
        for numero, fecha in enumerate(fechas, 1):
            cur = conn.execute(
                "INSERT INTO clases (materia_id, fecha, tema, abierta, creado_en) VALUES (?, ?, ?, 0, ?)",
                (materia.id, fecha.isoformat(), f"Clase {numero}", ahora_iso()),
            )
            hora = f"{fecha.isoformat()}T{materia.hora_inicio or '08:00'}:00"
            for alumno in alumnos:
                if azar.random() > PERFILES[posicion.get(alumno.dni, 0)]:
                    continue  # ausente
                estado = "tarde" if azar.random() < 0.1 else "presente"
                metodo = azar.choice(("qr_clase", "qr_clase", "pin", "qr_credencial", "manual"))
                conn.execute(
                    """INSERT INTO asistencias (clase_id, estudiante_id, estado, metodo, registrado_por, registrado_en)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cur.lastrowid, alumno.id, estado, metodo, docente_id, hora),
                )


def _justificativos(inst, alumnos, materias) -> None:
    from models import justificativo as jus

    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM justificativos WHERE institucion_id = ? LIMIT 1", (inst.id,)).fetchone():
            return
    dia = hoy() - timedelta(days=3)
    preceptoria = next(iter(_ids([PRECEPTORIA[0]])), None)  # resuelve uno de los justificativos
    jus.crear(alumnos[12].id, inst.id, materias[0].id, dia, dia, "Turno médico (adjunta certificado en papel)",
              alumnos[12].id)
    jus.crear(alumnos[13].id, inst.id, None, dia - timedelta(days=1), dia, "Corte de transporte en mi barrio",
              alumnos[13].id)
    aprobado = jus.crear(alumnos[10].id, inst.id, materias[2].id, hoy() - timedelta(days=10),
                         hoy() - timedelta(days=9), "Mesa de examen en otra institución", alumnos[10].id)
    if preceptoria:
        jus.resolver(aprobado, True, preceptoria, "Constancia verificada por Preceptoría")


def _ids(dnis: list[str]) -> list[int]:
    marcas = ",".join("?" * len(dnis))
    with get_connection() as conn:
        return [f["id"] for f in conn.execute(f"SELECT id FROM usuarios WHERE dni IN ({marcas})", dnis)]
