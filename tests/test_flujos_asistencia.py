from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from conftest import crear_materia

from core.tiempo import hoy
from models import asistencia_docente, cuentas, demo, justificativo
from models.asistencia import RegistroAsistencia
from models.institucion import asignar_rol, quitar_rol
from models.materia import Materia
from views.exportar import planilla_asistencia


def _crear_persona(institucion, rol, dni):
    return cuentas.crear_o_asignar(institucion.id, rol, dni, "Ana", "Benítez", f"{dni}@example.com").persona


def test_justificativo_docente_requiere_otra_persona_y_no_se_duplica(institucion):
    docente = _crear_persona(institucion, "docente", "31001001")
    preceptor = _crear_persona(institucion, "preceptor", "31001002")
    asignar_rol(docente.id, institucion.id, "preceptor")
    materia = crear_materia(docente.id, institucion.id)
    fecha = hoy()
    adjunto = ("certificado.pdf", b"%PDF-prueba", "application/pdf")
    id_jus = justificativo.crear(docente.id, institucion.id, materia.id, fecha, fecha, "Turno médico", docente.id,
                                 adjunto, rol="docente")
    with pytest.raises(ValueError, match="Ya hay un justificativo"):
        justificativo.crear(docente.id, institucion.id, None, fecha - timedelta(days=1), fecha,
                             "Turno médico", docente.id, rol="docente")
    assert justificativo.listar(institucion.id, docente_id=docente.id).empty
    assert justificativo.listar(institucion.id, filtro_docente=docente.id)["id"].tolist() == [id_jus]
    assert justificativo.archivo(id_jus) == adjunto
    with pytest.raises(ValueError, match="debe resolverlo"):
        justificativo.resolver(id_jus, True, docente.id)
    asistencia_docente.registrar(institucion.id, docente.id, materia.id, fecha, "ausente", preceptor.id)
    assert justificativo.resolver(id_jus, True, preceptor.id, "Comprobante revisado") == 1
    assert asistencia_docente.historial(institucion.id, docente.id)["estado"].tolist() == ["justificado"]
    assert justificativo.listar(institucion.id, titular_docente=docente.id)["estado"].tolist() == ["aprobado"]


def test_justificacion_masiva_mixta_y_planilla(institucion):
    docente = _crear_persona(institucion, "docente", "31001001")
    preceptor = _crear_persona(institucion, "preceptor", "31001002")
    alumno = _crear_persona(institucion, "estudiante", "41001001")
    materia = crear_materia(docente.id, institucion.id)
    materia.inscribir(alumno.id)
    materia.abrir_clase("Unidad 1")
    fecha = hoy()
    asistencia_docente.registrar(institucion.id, docente.id, materia.id, fecha, "tarde", preceptor.id)
    personas, registros = justificativo.justificar_masivo(
        institucion.id, [alumno.id], materia.id, fecha, fecha, "Actividad institucional", preceptor.id,
        docente_ids=[docente.id],
    )
    assert (personas, registros) == (2, 1)
    assert asistencia_docente.historial(institucion.id, docente.id)["estado"].tolist() == ["tarde"]
    df = Materia.registros_df([materia.id])
    planilla = planilla_asistencia(df, [fecha.isoformat()], {materia.id: materia.nombre})
    assert list(planilla.columns) == ["Materia", "Alumno", "DNI", fecha.isoformat()]
    assert planilla[fecha.isoformat()].tolist() == ["J"]
    assert planilla_asistencia(df.iloc[:0], [fecha.isoformat()], {}).empty


def test_preceptor_asignado_a_carreras_de_su_institucion(institucion, otra_institucion):
    preceptor = _crear_persona(institucion, "preceptor", "31001002")
    institucion.crear_carrera("Matemática")
    otra_institucion.crear_carrera("Física")
    propia = int(institucion.carreras().iloc[0]["id"])
    ajena = int(otra_institucion.carreras().iloc[0]["id"])
    institucion.asignar_carreras_preceptor(preceptor.id, [propia])
    with pytest.raises(ValueError, match="carreras activas"):
        institucion.asignar_carreras_preceptor(preceptor.id, [ajena])
    assert institucion.carreras_de_preceptor(preceptor.id) == [(propia, "Matemática")]
    quitar_rol(preceptor.id, institucion.id, "preceptor")
    assert not institucion.carreras_de_preceptor(preceptor.id)


def test_qr_y_pin_comparten_instante_al_cambiar_la_ventana(db, monkeypatch):
    from models import asistencia

    instantes = iter([59.99, 60.01])
    monkeypatch.setattr(asistencia, "time", SimpleNamespace(time=lambda: next(instantes)))
    registro = RegistroAsistencia(1)
    token, pin, segundos = registro.codigos_proyeccion()
    assert token == registro.generar_token(59.99)
    assert pin == registro.generar_pin(59.99)
    assert segundos == 0
    assert next(instantes) == 60.01


def test_alumno_demo_ve_asistencia_de_clases_historicas(db, monkeypatch):
    from models.persona import RepositorioPersonas

    monkeypatch.setenv("SIA_DEMO", "1")
    demo.asegurar_demo()
    alumno = RepositorioPersonas.por_dni(demo.ALUMNOS[0][0])
    materias = Materia.de_estudiante(alumno.id, demo.institucion().id)
    df = Materia.registros_df([m.id for m in materias], estudiante_id=alumno.id)
    assert not df.empty
    assert df["fecha"].max() < hoy().isoformat()
    assert 0 < df["presente"].mean() < 1
