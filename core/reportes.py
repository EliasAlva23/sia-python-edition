"""Reportes exportables: PDF de cierre de clase (para Preceptoría) y planillas Excel.

Los PDF usan las fuentes base de PDF (Helvetica, codificación latin-1) para no depender de fuentes del
sistema: funcionan igual en Windows y en Streamlit Cloud (Linux). Los caracteres fuera de latin-1
(guiones largos, comillas tipográficas, emojis) se reemplazan por equivalentes simples.
"""
from __future__ import annotations

import io
import unicodedata
from pathlib import Path

import pandas as pd
from fpdf import FPDF
from fpdf.fonts import FontFace

from core.database import get_connection
from core.tiempo import ahora, ahora_iso

INSTITUCION = "Instituto de Educación Superior N° 11"
_RAIZ = Path(__file__).resolve().parent.parent
_LOGO = next((p for p in (_RAIZ / "static" / "icon-192.png", _RAIZ / "assets" / "logo_ies11.png") if p.exists()), None)
_REEMPLAZOS = {"—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "•": "-", "→": "->"}
_ESTADOS = {"presente": "Presente", "tarde": "Tarde", "justificado": "Justificado", "ausente": "Ausente"}
_METODOS = {"qr_credencial": "QR credencial", "qr_clase": "QR de clase", "pin": "PIN", "manual": "Manual"}
AZUL_NOCHE = (0, 52, 103)
AZUL = (52, 111, 176)
LAVANDA_SUAVE = (238, 240, 250)


def clave_alfabetica(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().casefold()


def texto_pdf(valor) -> str:
    """Texto seguro para las fuentes base de PDF (latin-1)."""
    texto = "" if valor is None else str(valor)
    for original, reemplazo in _REEMPLAZOS.items():
        texto = texto.replace(original, reemplazo)
    return texto.encode("latin-1", "replace").decode("latin-1")


class _PDF(FPDF):
    def __init__(self, titulo: str) -> None:
        super().__init__(format="A4")
        self._titulo = titulo
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(15, 15, 15)
        self.set_title(texto_pdf(titulo))
        self.set_author(texto_pdf(f"SIA - {INSTITUCION}"))

    def header(self) -> None:
        self.set_fill_color(*AZUL_NOCHE)
        self.rect(0, 0, self.w, 26, style="F")
        if _LOGO is not None:
            self.image(str(_LOGO), x=12, y=4, h=18)
        self.set_xy(34, 6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 7, texto_pdf(INSTITUCION), new_x="LMARGIN", new_y="NEXT")
        self.set_x(34)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, texto_pdf(self._titulo))
        self.set_text_color(14, 39, 71)
        self.set_y(32)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110, 120, 140)
        self.cell(0, 6, texto_pdf(f"Generado por SIA - {INSTITUCION} - {ahora():%d/%m/%Y %H:%M}"), align="L")
        self.cell(0, 6, f"Página {self.page_no()}/{{nb}}", align="R")


def _datos_clase(clase_id: int) -> tuple[dict, pd.DataFrame]:
    with get_connection() as conn:
        clase = conn.execute(
            """SELECT c.id, c.fecha, c.tema, c.materia_id, m.nombre AS materia, m.curso, m.comision, m.turno,
                      m.dia_horario, m.umbral, u.nombre || ' ' || u.apellido AS docente
               FROM clases c JOIN materias m ON m.id = c.materia_id JOIN usuarios u ON u.id = m.docente_id
               WHERE c.id = ?""",
            (clase_id,),
        ).fetchone()
        if clase is None:
            raise ValueError("La clase no existe.")
        filas = conn.execute(
            """SELECT u.apellido || ', ' || u.nombre AS alumno, u.dni,
                      COALESCE(a.estado, 'ausente') AS estado, a.metodo, a.registrado_en
               FROM inscripciones i JOIN usuarios u ON u.id = i.estudiante_id
               LEFT JOIN asistencias a ON a.clase_id = ? AND a.estudiante_id = u.id
               WHERE i.materia_id = ? AND substr(i.inscripto_en, 1, 10) <= ?
               ORDER BY u.apellido, u.nombre""",
            (clase_id, clase["materia_id"], clase["fecha"]),
        ).fetchall()
    alumnos = pd.DataFrame([dict(f) for f in filas], columns=["alumno", "dni", "estado", "metodo", "registrado_en"])
    # Orden alfabético ignorando tildes (SQLite ordena por bytes y deja "Álvarez" después de "Zárate").
    alumnos = alumnos.sort_values("alumno", key=lambda s: s.map(clave_alfabetica)).reset_index(drop=True)
    return dict(clase), alumnos


def pdf_reporte_clase(clase_id: int) -> bytes:
    """Reporte de asistencia de una clase, listo para archivar en Preceptoría."""
    clase, alumnos = _datos_clase(clase_id)
    pdf = _PDF("Reporte de asistencia de clase")
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, texto_pdf(clase["materia"]), new_x="LMARGIN", new_y="NEXT")
    fecha = pd.to_datetime(clase["fecha"]).strftime("%d/%m/%Y")
    datos = [
        ("Curso / Comisión", " - ".join(p for p in (clase["curso"], clase["comision"]) if p) or "-"),
        ("Turno", clase["turno"] or "-"),
        ("Días y horario", clase["dia_horario"] or "-"),
        ("Fecha de la clase", fecha),
        ("Tema", clase["tema"] or "-"),
        ("Docente", clase["docente"]),
    ]
    pdf.set_font("Helvetica", "", 10)
    for etiqueta, valor in datos:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(42, 6, texto_pdf(etiqueta + ":"))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, texto_pdf(valor), new_x="LMARGIN", new_y="NEXT")

    total = len(alumnos)
    conteo = alumnos["estado"].value_counts() if total else pd.Series(dtype=int)
    asistieron = int(sum(conteo.get(e, 0) for e in ("presente", "tarde", "justificado")))
    pct = 100 * asistieron / total if total else 0
    pdf.ln(3)
    resumen = [("Inscriptos", total), ("Presentes", int(conteo.get("presente", 0))),
               ("Tardes", int(conteo.get("tarde", 0))), ("Justificados", int(conteo.get("justificado", 0))),
               ("Ausentes", int(conteo.get("ausente", 0))), ("Asistencia", f"{pct:.0f}%")]
    ancho = (pdf.w - pdf.l_margin - pdf.r_margin) / len(resumen)
    pdf.set_fill_color(*LAVANDA_SUAVE)
    y = pdf.get_y()
    for i, (etiqueta, valor) in enumerate(resumen):
        pdf.set_xy(pdf.l_margin + i * ancho, y)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(ancho - 2, 9, texto_pdf(valor), align="C", fill=True, new_x="LEFT", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(ancho - 2, 5, texto_pdf(etiqueta), align="C", fill=True)
    pdf.set_y(y + 18)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Listado de asistencia", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    if total == 0:
        pdf.cell(0, 7, "No hay alumnos inscriptos en la materia.", new_x="LMARGIN", new_y="NEXT")
    else:
        encabezado = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=AZUL)
        with pdf.table(col_widths=(8, 62, 26, 26, 16, 32), headings_style=encabezado, line_height=6,
                       cell_fill_color=LAVANDA_SUAVE, cell_fill_mode="ROWS", text_align="LEFT") as tabla:
            fila = tabla.row()
            for titulo in ("#", "Alumno/a", "DNI", "Estado", "Hora", "Registro"):
                fila.cell(titulo)
            for n, a in enumerate(alumnos.itertuples(), start=1):
                fila = tabla.row()
                fila.cell(str(n))
                fila.cell(texto_pdf(a.alumno))
                fila.cell(texto_pdf(a.dni))
                fila.cell(_ESTADOS.get(a.estado, a.estado))
                fila.cell(texto_pdf(a.registrado_en[11:16]) if isinstance(a.registrado_en, str) else "-")
                fila.cell(texto_pdf(_METODOS.get(a.metodo, "-")) if isinstance(a.metodo, str) else "-")

    pdf.ln(18)
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    y = pdf.get_y()
    mitad = (pdf.w - pdf.l_margin - pdf.r_margin) / 2
    for i, rotulo in enumerate(("Firma y aclaración del docente", "Recibido por Preceptoría")):
        x = pdf.l_margin + i * mitad
        pdf.line(x + 5, y, x + mitad - 10, y)
        pdf.set_xy(x + 5, y + 1)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(mitad - 15, 5, texto_pdf(rotulo), align="C")
    return bytes(pdf.output())


def nombre_reporte_clase(clase_id: int) -> str:
    clase, _ = _datos_clase(clase_id)
    sin_tildes = unicodedata.normalize("NFKD", clase["materia"]).encode("ascii", "ignore").decode()
    materia = "".join(c if c.isalnum() else "_" for c in sin_tildes)[:40].strip("_")
    return f"Asistencia_{materia}_{clase['fecha']}.pdf"


def guardar_reporte_clase(clase_id: int) -> bytes:
    """Genera el PDF y lo guarda (reemplaza uno anterior si la clase se reabrió y volvió a cerrar)."""
    pdf = pdf_reporte_clase(clase_id)
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO clase_reportes (clase_id, pdf, generado_en) VALUES (?, ?, ?)
               ON CONFLICT (clase_id) DO UPDATE SET pdf = excluded.pdf, generado_en = excluded.generado_en""",
            (clase_id, pdf, ahora_iso()),
        )
    return pdf


def reporte_clase(clase_id: int) -> bytes | None:
    with get_connection() as conn:
        fila = conn.execute("SELECT pdf FROM clase_reportes WHERE clase_id = ?", (clase_id,)).fetchone()
    return bytes(fila["pdf"]) if fila else None


def excel_bytes(hojas: dict[str, pd.DataFrame]) -> bytes:
    """Planilla .xlsx con una hoja por DataFrame y columnas ajustadas al contenido."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        for nombre, df in hojas.items():
            hoja = nombre[:31]
            df.to_excel(escritor, sheet_name=hoja, index=False)
            ws = escritor.sheets[hoja]
            for i, columna in enumerate(df.columns, start=1):
                largo = max([len(str(columna))] + [len(str(v)) for v in df[columna].head(500)])
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(45, largo + 2)
            ws.freeze_panes = "A2"
    return buffer.getvalue()
