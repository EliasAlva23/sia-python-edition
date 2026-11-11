"""Genera los PDF de docs/ a partir de los Markdown (Informe de Interfaces, PRD y Arquitectura).

Uso (desde la raíz del repositorio):
    pip install markdown fpdf2
    python docs/generar_pdfs.py

Usa una fuente TrueType del sistema si la encuentra (Arial en Windows, DejaVu en Linux) para mostrar tildes
y los caracteres del árbol de carpetas; si no, cae a las fuentes base de PDF.
"""
from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path

import markdown
from fpdf import FPDF
from fpdf.fonts import FontFace, TextStyle

DOCS = Path(__file__).resolve().parent
RAIZ = DOCS.parent
DOCUMENTOS = [
    ("INFORME_INTERFACES.md", "Informe de Interfaces"),
    ("PRD.md", "PRD - Documento de Requisitos del Producto"),
    ("ARQUITECTURA.md", "Arquitectura del Sistema"),
]
LOGO = RAIZ / "static" / "icon-192.png"
AZUL_NOCHE, AZUL, LILA = (0, 52, 103), (52, 111, 176), (183, 143, 182)
FUENTES = [
    {"regular": "C:/Windows/Fonts/arial.ttf", "B": "C:/Windows/Fonts/arialbd.ttf", "I": "C:/Windows/Fonts/ariali.ttf",
     "BI": "C:/Windows/Fonts/arialbi.ttf", "mono": "C:/Windows/Fonts/cour.ttf"},
    {"regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "B": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "I": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "BI": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
     "mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"},
]
_EMOJIS = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


class Documento(FPDF):
    def __init__(self, titulo: str) -> None:
        super().__init__(format="A4")
        self.titulo = titulo
        self.fuente, self.mono, self.unicode = "Helvetica", "Courier", False
        for juego in FUENTES:
            if all(Path(p).exists() for p in juego.values()):
                self.add_font("SIA", "", juego["regular"])
                for estilo in ("B", "I", "BI"):
                    self.add_font("SIA", estilo, juego[estilo])
                for estilo in ("", "B", "I", "BI"):
                    self.add_font("SIAMono", estilo, juego["mono"])
                self.fuente, self.mono, self.unicode = "SIA", "SIAMono", True
                break
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(16, 16, 16)
        self.set_title(titulo)
        self.set_author("Tech & Innovation Team - IES N° 11")

    def header(self) -> None:
        self.set_fill_color(*AZUL_NOCHE)
        self.rect(0, 0, self.w, 22, style="F")
        self.set_fill_color(*LILA)
        self.rect(0, 22, self.w, 1.2, style="F")
        if LOGO.exists():
            self.image(str(LOGO), x=12, y=3, h=16)
        self.set_xy(31, 5)
        self.set_text_color(255, 255, 255)
        self.set_font(self.fuente, "B", 12)
        self.cell(0, 6, "SIA · IES N° 11", new_x="LMARGIN", new_y="NEXT")
        self.set_x(31)
        self.set_font(self.fuente, "", 9)
        self.cell(0, 5, self.titulo)
        self.set_text_color(14, 39, 71)
        self.set_y(30)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.fuente, "", 8)
        self.set_text_color(110, 120, 140)
        self.cell(0, 6, "Instituto de Educación Superior N° 11 · Tech & Innovation Team", align="L")
        self.cell(0, 6, f"Página {self.page_no()}/{{nb}}", align="R")


def _preparar_html(texto: str, unicode_ok: bool) -> str:
    texto = _EMOJIS.sub("", texto)
    if not unicode_ok:  # fuentes base: solo latin-1
        for a, b in {"—": "-", "–": "-", "→": "->", "├": "+", "└": "+", "─": "-", "│": "|", "“": '"', "”": '"'}.items():
            texto = texto.replace(a, b)
    html = markdown.markdown(texto, extensions=["tables", "fenced_code"])
    html = re.sub(r"<hr\s*/?>", "", html)
    # fpdf2 no admite <code> en línea dentro de tablas: se muestra como texto común (los bloques <pre> se conservan)
    partes = re.split(r"(<pre>.*?</pre>)", html, flags=re.S)
    html = "".join(p if p.startswith("<pre>") else re.sub(r"</?code>", "", p) for p in partes)
    return html


def _texto_celda(html: str) -> str:
    """Texto plano de una celda (sin etiquetas, con entidades HTML resueltas)."""
    return unescape(re.sub(r"<[^>]+>", "", html)).strip()


def _tabla(pdf: Documento, html_tabla: str) -> None:
    """Dibuja una tabla con pdf.table(): estilos y anchos controlados (write_html arrastraba negritas)."""
    filas = [[_texto_celda(c) for c in re.findall(r"<t[dh](?:\s[^>]*)?>(.*?)</t[dh]>", fila, flags=re.S)]
             for fila in re.findall(r"<tr>(.*?)</tr>", html_tabla, flags=re.S)]
    filas = [f for f in filas if f]
    if not filas:
        return
    columnas = len(filas[0])
    anchos = {2: (28, 72), 3: (24, 38, 38)}.get(columnas)
    encabezado = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=AZUL)
    pdf.ln(1)
    pdf.set_font(pdf.fuente, size=9)
    with pdf.table(col_widths=anchos, headings_style=encabezado, line_height=5.2, text_align="LEFT",
                   cell_fill_color=(238, 240, 250), cell_fill_mode="ROWS", padding=1.6) as tabla:
        for fila in filas:
            renglon = tabla.row()
            for celda in fila + [""] * (columnas - len(fila)):
                renglon.cell(celda)
    pdf.ln(3)


def generar(md: Path, titulo: str) -> Path:
    pdf = Documento(titulo)
    pdf.alias_nb_pages()
    pdf.add_page()
    html = _preparar_html(md.read_text(encoding="utf-8"), pdf.unicode)
    estilos = {
        "h1": TextStyle(font_family=pdf.fuente, font_style="B", font_size_pt=18, color=AZUL_NOCHE, t_margin=2, b_margin=4),
        "h2": TextStyle(font_family=pdf.fuente, font_style="B", font_size_pt=14, color=AZUL, t_margin=6, b_margin=2),
        "h3": TextStyle(font_family=pdf.fuente, font_style="B", font_size_pt=12, color=AZUL_NOCHE, t_margin=4, b_margin=1),
        "pre": TextStyle(font_family=pdf.mono, font_size_pt=7.5, color=(14, 39, 71)),
        "code": TextStyle(font_family=pdf.mono, font_size_pt=8.5),
    }
    for parte in re.split(r"(<table>.*?</table>)", html, flags=re.S):
        if parte.startswith("<table>"):
            _tabla(pdf, parte)
        elif parte.strip():
            pdf.set_font(pdf.fuente, size=10)
            pdf.write_html(parte, font_family=pdf.fuente, tag_styles=estilos)
    destino = md.with_suffix(".pdf")
    pdf.output(str(destino))
    return destino


def main() -> None:
    for archivo, titulo in DOCUMENTOS:
        ruta = DOCS / archivo
        if not ruta.exists():
            sys.exit(f"Falta {ruta}")
        destino = generar(ruta, titulo)
        print(f"OK  {destino.relative_to(RAIZ)}  ({destino.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
