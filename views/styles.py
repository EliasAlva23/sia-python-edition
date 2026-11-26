"""Sistema visual de SIA: sobrio, corporativo y personalizable por institución (white-label).

Principios: fondo claro suave (#EEF0EC), superficies apenas teñidas (nunca blanco puro), texto en azul marino
profundo (#142033), un color de acento (el primario de cada institución), bordes definidos, indicadores en tarjetas
circulares y tipografía Plus Jakarta Sans (con Inter y la fuente del sistema como respaldo). Las formas orgánicas en
degradé se reservan para la pantalla de acceso y, muy sutiles, para el encabezado de cada panel. Los colores y el logo se toman de la institución
activa (`configurar_tema`); si no hay ninguna, se usan los valores por defecto de SIA.
"""
from __future__ import annotations

import base64
import colorsys
import hashlib
import io
import re
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CLAVE_TEMA = "modo_oscuro"
EQUIPO = "Tech & Innovation Team"
PRODUCTO = "SIA"
PRODUCTO_LARGO = "Sistema de Asistencia Inteligente"

# Paleta base de SIA (también se ofrece como presets al configurar una institución)
MARINO = "#142033"      # azul marino profundo: texto, panel de acceso
ACERO = "#2E5772"       # azul acero: acento por defecto
VERDE_AZULADO = "#3F7C70"
OLIVA = "#70812B"
FONDO_CLARO = "#EEF0EC"
PALETAS = {
    "Acero y marino": (ACERO, MARINO),
    "Verde azulado": (VERDE_AZULADO, ACERO),
    "Oliva": (OLIVA, VERDE_AZULADO),
    "Marino profundo": (MARINO, ACERO),
}
PRIMARIO_DEFECTO = ACERO
SECUNDARIO_DEFECTO = VERDE_AZULADO
FUENTE = "'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

# Compatibilidad con módulos anteriores (constantes de la institución inicial)
INSTITUCION = "Instituto de Educación Superior N° 11"
INSTITUCION_CORTA = "IES N° 11"
TITULO_APP = "SIA · Sistema de Asistencia Inteligente"
AZUL_NOCHE = "#0E1116"

# Gráficos: paleta categórica validada (orden fijo, nunca cíclico) y estados reservados.
SERIES_CLARO = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SERIES_OSCURO = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
ESTADO = {"bueno": "#0ca30c", "advertencia": "#fab219", "serio": "#ec835a", "critico": "#d03b3b"}
COLORES_NIVEL = {"ALTO": ESTADO["critico"], "MEDIO": ESTADO["advertencia"], "BAJO": ESTADO["bueno"]}
COLORES_CONDICION = {"Promociona": ESTADO["bueno"], "Regular": "#2a78d6", "Libre": ESTADO["critico"]}
EMOJI_NIVEL = {"ALTO": "●", "MEDIO": "●", "BAJO": "●"}
TONOS = {
    "azul": "#2a78d6", "verde": ESTADO["bueno"], "ambar": ESTADO["advertencia"], "rojo": ESTADO["critico"],
    "gris": "#6B7280", "neutro": "#6B7280", "lavanda": "#6B7280", "lila": "#6B7280", "celeste": "#2a78d6",
    "indigo": "#2a78d6", "cian": "#2a78d6", "noche": "#6B7280",
}
AZUL, LAVANDA, LILA = "#2a78d6", "#6B7280", "#9CA3AF"


# ---------------------------------------------------------------- color
def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def mezclar(color: str, con: str, proporcion: float) -> str:
    """Mezcla lineal: proporcion=0 -> color, 1 -> con."""
    a, b = _rgb(color), _rgb(con)
    return _hex(tuple(x + (y - x) * proporcion for x, y in zip(a, b, strict=True)))


def _luminancia(color: str) -> float:
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tinta_sobre(fondo: str) -> str:
    """Texto blanco o casi negro, el que contraste más sobre el fondo."""
    return "#FFFFFF" if contraste(fondo, "#FFFFFF") >= contraste(fondo, "#111827") else "#111827"


SUPERFICIE_OSCURA = "#142033"


def _aclarar_para_oscuro(color: str) -> str:
    """En modo oscuro el acento se aclara hasta contrastar al menos 4.5:1 con la superficie."""
    h, luz, s = colorsys.rgb_to_hls(*_rgb(color))
    for _ in range(12):
        candidato = _hex(colorsys.hls_to_rgb(h, luz, s))
        if contraste(candidato, SUPERFICIE_OSCURA) >= 4.5:
            return candidato
        luz = min(0.85, luz + 0.05)
    return _hex(colorsys.hls_to_rgb(h, luz, s))


def fondo_marca(color: str) -> str:
    """Fondo del panel de acceso: el color institucional llevado hacia el marino hasta que el texto blanco
    contraste al menos 7:1 (nivel AAA), para que cualquier marca se lea bien."""
    for paso in range(11):
        candidato = mezclar(color, MARINO, min(1.0, 0.35 + paso * 0.065))
        if contraste(candidato, "#FFFFFF") >= 7:
            return candidato
    return MARINO


# ---------------------------------------------------------------- institución activa
def configurar_tema(institucion) -> None:
    """Guarda en la sesión la identidad visual de la institución activa (o la de SIA si es None)."""
    if institucion is None:
        st.session_state["_tema"] = {"primario": PRIMARIO_DEFECTO, "secundario": SECUNDARIO_DEFECTO,
                                     "nombre": PRODUCTO_LARGO, "corto": PRODUCTO, "logo": None, "id": None}
        return
    logo = institucion.logo()
    st.session_state["_tema"] = {
        "primario": institucion.color_primario, "secundario": institucion.color_secundario,
        "nombre": institucion.nombre, "corto": institucion.nombre_corto, "id": institucion.id,
        "logo": _data_uri_bytes(logo[0], logo[1]) if logo else None,
    }


def tema() -> dict:
    if "_tema" not in st.session_state:
        configurar_tema(None)
    return st.session_state["_tema"]


def modo_oscuro() -> bool:
    return bool(st.session_state.get(CLAVE_TEMA, False))


@lru_cache(maxsize=32)
def _data_uri_cache(huella: str, contenido: bytes, mime: str, lado: int) -> str:
    from PIL import Image

    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.thumbnail((lado, lado))
        salida = io.BytesIO()
        imagen.save(salida, format="PNG", optimize=True)
        return f"data:image/png;base64,{base64.b64encode(salida.getvalue()).decode()}"
    except Exception:
        return f"data:{mime};base64,{base64.b64encode(contenido).decode()}"


def _data_uri_bytes(contenido: bytes, mime: str, lado: int = 160) -> str:
    return _data_uri_cache(hashlib.sha1(contenido).hexdigest(), contenido, mime, lado)


def _iniciales(texto: str) -> str:
    palabras = [p for p in texto.replace("N°", "").replace("Nº", "").split() if p[:1].isalnum()]
    return "".join(p[0] for p in palabras[:3]).upper() or "SIA"


def logo_html(tamano: int = 40) -> str:
    t = tema()
    if t["logo"]:
        return f'<img class="sia-logo" src="{t["logo"]}" alt="Logo {escape(t["corto"])}" width="{tamano}" height="{tamano}">'
    return (f'<span class="sia-logo sia-logo-iniciales" style="width:{tamano}px;height:{tamano}px;'
            f'background:{t["primario"]};color:{tinta_sobre(t["primario"])}">{escape(_iniciales(t["corto"]))}</span>')


@lru_cache(maxsize=1)
def _logo_tech() -> str | None:
    ruta = ASSETS / "logo_tech.png"
    return _data_uri_bytes(ruta.read_bytes(), "image/png", 96) if ruta.exists() else None


def ruta_logo() -> Path | None:
    ruta = ASSETS / "logo_ies11.png"
    return ruta if ruta.exists() else None


# ---------------------------------------------------------------- CSS
def _variables() -> str:
    t = tema()
    primario, secundario = t["primario"], t["secundario"]
    if modo_oscuro():
        acento = _aclarar_para_oscuro(primario)
        return f"""
  --bg: #0C1420; --surface: #142033; --surface-2: #1B2A41; --campo: #101A2B; --border: #2A3B55;
  --border-fuerte: #3B4F6C; --ink: #EEF0EC; --ink-2: #D3D9E0; --muted: #A9B3C2; --track: #24354E;
  --primary: {acento}; --primary-ink: {tinta_sobre(acento)}; --primary-soft: {mezclar(acento, SUPERFICIE_OSCURA, 0.8)};
  --primary-hover: {mezclar(acento, '#FFFFFF', 0.12)}; --secondary: {_aclarar_para_oscuro(secundario)};
  --marca: {fondo_marca(primario)}; --grid: #26364F; --oliva: #A3B35A; --tinte-fondo: 12%;
  --sombra: 0 1px 0 rgba(255, 255, 255, .03) inset, 0 8px 24px -16px rgba(0, 0, 0, .6);
  --sombra-alta: 0 1px 0 rgba(255, 255, 255, .05) inset, 0 18px 34px -18px rgba(0, 0, 0, .8);
  --boton-a: {mezclar(_aclarar_para_oscuro(secundario), SUPERFICIE_OSCURA, 0.35)}; --boton-b: {mezclar(acento, SUPERFICIE_OSCURA, 0.3)};
"""
    return f"""
  --bg: #DCE7E1; --surface: #E6EBE1; --surface-2: #D5E2DC; --campo: #EEF0EC; --border: #ACBEB5;
  --border-fuerte: #869D92; --ink: {MARINO}; --ink-2: #26344A; --muted: #405365; --track: #B7CAC1;
  --primary: {primario}; --primary-ink: {tinta_sobre(primario)}; --primary-soft: {mezclar(primario, '#FFFFFF', 0.9)};
  --primary-hover: {mezclar(primario, MARINO, 0.25)}; --secondary: {secundario};
  --marca: {fondo_marca(primario)}; --grid: #BCD0C6; --oliva: {OLIVA}; --tinte-fondo: 25%;
  --sombra: 0 1px 2px rgba(20, 32, 51, .06), 0 10px 24px -18px rgba(20, 32, 51, .35);
  --sombra-alta: 0 2px 4px rgba(20, 32, 51, .07), 0 18px 32px -20px rgba(20, 32, 51, .5);
  --boton-a: {mezclar(secundario, MARINO, 0.12)}; --boton-b: {mezclar(primario, MARINO, 0.1)};
"""


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap');
:root, .stApp {{ {variables}
  --critico: #d03b3b; --advertencia: #b7791f; --bueno: #0a7f0a; --radio: 14px; --radio-chico: 10px; }}

/* Tipografía (sin tocar los íconos Material de Streamlit) */
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp td, .stApp th, .stApp small,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"], [role="tab"], [role="option"] {{
  font-family: {fuente} !important; -webkit-font-smoothing: antialiased;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-weight: 700 !important; letter-spacing: -0.015em; }}
.stApp p, .stApp li {{ line-height: 1.6; font-size: 1rem; }}
[data-testid="stMarkdownContainer"] h3 {{ font-size: 1.3rem; margin-top: .7rem; }}
[data-testid="stMarkdownContainer"] h4 {{ font-size: 1.12rem; margin-top: .5rem; }}
[data-testid="stMarkdownContainer"] h5 {{ font-size: 1rem; font-weight: 650; }}

/* Base */
.stApp, [data-testid="stAppViewContainer"] {{ color: var(--ink); background:
    radial-gradient(1100px 620px at 105% 0%, color-mix(in srgb, var(--secondary) var(--tinte-fondo), transparent), transparent 78%),
    radial-gradient(900px 590px at 0% 110%, color-mix(in srgb, var(--oliva) var(--tinte-fondo), transparent), transparent 75%),
    var(--bg) !important; background-attachment: fixed !important; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1280px; }}
section[data-testid="stSidebar"] {{ border-right: 1px solid var(--border-fuerte);
  background: linear-gradient(180deg, color-mix(in srgb, var(--secondary) 10%, var(--surface)) 0%, var(--surface) 42%,
    color-mix(in srgb, var(--oliva) 9%, var(--surface)) 100%) !important; }}
section[data-testid="stSidebar"] * {{ color: var(--ink); }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li, [data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3, [data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5, [data-testid="stHeading"] *, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label, .stRadio label p, .stCheckbox label p, [data-testid="stToggle"] p {{ color: var(--ink); }}
[data-testid="stWidgetLabel"] p {{ font-weight: 600; font-size: .95rem; color: var(--ink-2) !important; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; font-size: .93rem; }}
[data-testid="stMarkdownContainer"] a {{ color: var(--primary); }}
hr {{ border-color: var(--border) !important; }}

/* Encabezado nativo: oculto salvo el botón ">>" que abre la barra lateral en celulares */
header[data-testid="stHeader"] {{ visibility: hidden !important; background: transparent !important; box-shadow: none !important; }}
#MainMenu {{ visibility: hidden !important; }}
[data-testid="stExpandSidebarButton"] {{
  visibility: visible !important; color: var(--primary-ink) !important; background: var(--primary) !important;
  border-radius: var(--radio-chico) !important;
}}
[data-testid="stExpandSidebarButton"] * {{ color: var(--primary-ink) !important; }}
/* Contenedores invisibles (estilos y scripts) */
[data-testid="stElementContainer"]:has(> [data-testid="stHtml"]),
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) {{ display: none !important; }}

/* Campos */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"],
[data-testid="stDateInputField"], [data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
div:has(> input[role="combobox"]), [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {{
  background: var(--campo) !important; border: 1px solid var(--border-fuerte) !important; border-radius: var(--radio-chico) !important;
}}
[data-testid="stTextInputRootElement"] input, [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stNumberInputContainer"] input, input[role="combobox"], [data-testid="stSelectbox"] [role="group"] div,
[data-testid="stMultiSelect"] [role="group"] div, [data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] div {{
  color: var(--ink) !important; -webkit-text-fill-color: var(--ink) !important; background-color: transparent !important; border: none !important;
}}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stSelectbox"] [role="group"]:focus-within, [data-baseweb="input"]:focus-within {{
  border-color: var(--primary) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 22%, transparent) !important;
}}
input::placeholder, textarea::placeholder {{ color: var(--muted) !important; -webkit-text-fill-color: var(--muted) !important; }}
[role="listbox"], [role="listbox"] [role="option"] {{ background: var(--campo) !important; color: var(--ink) !important; }}
[role="listbox"] [role="option"]:hover, [role="listbox"] [aria-selected="true"] {{ background: var(--surface-2) !important; }}
[data-baseweb="tag"] {{ background: var(--surface-2) !important; border-radius: 4px !important; }}
[data-baseweb="tag"] span {{ color: var(--ink) !important; }}
[data-testid="stCheckbox"] label > div:first-child {{ background-color: var(--surface); border-color: var(--border-fuerte); }}

/* Botones: sólidos, sin degradés ni elevación */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, [data-testid="stPopoverButton"] {{
  border-radius: var(--radio-chico) !important; font-weight: 600 !important; min-height: 2.6rem;
  box-shadow: none !important; transition: background-color .12s ease, border-color .12s ease !important;
}}
button[kind^="primary"], button[data-testid^="stBaseButton-primary"] {{
  background: var(--primary) !important; color: var(--primary-ink) !important; border: 1px solid var(--primary) !important;
}}
button[kind^="primary"] p, button[data-testid^="stBaseButton-primary"] p {{ color: var(--primary-ink) !important; }}
button[kind^="primary"]:hover, button[data-testid^="stBaseButton-primary"]:hover {{
  background: var(--primary-hover) !important; border-color: var(--primary-hover) !important;
}}
button[kind^="secondary"], button[data-testid^="stBaseButton-secondary"], [data-testid="stPopoverButton"] {{
  background: var(--campo) !important; color: var(--ink) !important; border: 1px solid var(--border-fuerte) !important;
}}
button[kind^="secondary"] p, button[data-testid^="stBaseButton-secondary"] p, [data-testid="stPopoverButton"] p {{ color: var(--ink) !important; }}
button[kind^="secondary"]:hover, button[data-testid^="stBaseButton-secondary"]:hover, [data-testid="stPopoverButton"]:hover {{
  background: var(--surface-2) !important; border-color: var(--muted) !important;
}}
button[data-testid="stBaseButton-elementToolbar"] {{ border: none !important; background: transparent !important; }}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {{ opacity: .5; }}

/* Contenedores */
[data-testid="stForm"], [data-testid="stExpander"] details, div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stPopoverBody"], [data-testid="stMetric"], [data-testid="stCameraInput"] {{
  background: var(--surface) !important; border: 1px solid var(--border) !important; border-radius: var(--radio) !important;
  box-shadow: var(--sombra);
}}
[data-testid="stForm"] {{ padding: 1.1rem 1.2rem !important; }}
/* Micro-interacciones: transición corta, elevación leve solo en tarjetas (los formularios no se mueven) */
.sia-card, .sia-hist-fila, .sia-alerta, .sia-riesgo, .sia-encabezado, div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stExpander"] details, [data-testid="stForm"], .stButton > button, .stDownloadButton > button,
.stFormSubmitButton > button, [data-testid="stPopoverButton"], .stTabs [role="tab"] {{
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease, background-color .18s ease !important; }}
.sia-card:hover, .sia-hist-fila:hover, .sia-alerta:hover, .sia-riesgo:hover {{ transform: translateY(-2px);
  box-shadow: var(--sombra-alta); border-color: color-mix(in srgb, var(--primary) 38%, var(--border)) !important; }}
div[data-testid="stVerticalBlockBorderWrapper"]:hover, [data-testid="stExpander"] details:hover, [data-testid="stForm"]:hover {{
  box-shadow: var(--sombra-alta); border-color: color-mix(in srgb, var(--primary) 30%, var(--border)) !important; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{ transform: translateY(-1px); }}
.stTabs [role="tab"]:hover {{ border-bottom-color: color-mix(in srgb, var(--primary) 40%, transparent) !important; }}
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ transition: none !important; animation: none !important; }}
  .sia-card:hover, .sia-hist-fila:hover, .sia-alerta:hover, .sia-riesgo:hover, .stButton > button:hover,
  .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {{ transform: none !important; }}
}}
[data-testid="stExpander"] summary {{ background: var(--surface) !important; border-radius: var(--radio); }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span {{ color: var(--ink) !important; font-weight: 500; }}
[data-testid="stExpander"] summary:hover {{ background: var(--surface-2) !important; }}
[data-testid="stAlert"], [data-testid="stAlertContainer"] {{ border-radius: var(--radio) !important; }}
[data-testid="stCode"] pre, [data-testid="stCode"] code, .stCodeBlock pre {{
  background: var(--surface-2) !important; color: var(--ink) !important; border-radius: var(--radio-chico) !important;
}}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius: var(--radio); overflow: hidden; border: 1px solid var(--border); }}
[data-testid="stImage"] img {{ border-radius: var(--radio-chico); }}

/* Pestañas: subrayado, sin rellenos */
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{
  gap: 1.4rem; flex-wrap: wrap; overflow-x: visible !important; border-bottom: 1px solid var(--border); padding: 0;
}}
.stTabs [role="tab"], .stTabs [data-baseweb="tab"] {{
  background: transparent !important; border: none !important; border-bottom: 2px solid transparent !important;
  border-radius: 0 !important; padding: .55rem 0 !important; height: auto !important; margin-bottom: -1px;
}}
.stTabs [role="tab"] p {{ color: var(--muted); font-weight: 600; font-size: 1rem; }}
.stTabs [role="tab"]:hover p {{ color: var(--ink); }}
.stTabs [role="tab"][aria-selected="true"] {{ border-bottom: 3px solid var(--primary) !important; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: var(--ink) !important; font-weight: 600 !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs [data-testid="stTabScrollButton"] {{ display: none !important; }}

/* ---------- Componentes SIA ---------- */
.sia-logo {{ display: inline-flex; align-items: center; justify-content: center; border-radius: 50%;
  object-fit: contain; background: #fff; border: 1px solid var(--border); flex: 0 0 auto; }}
.sia-logo-iniciales {{ font-weight: 700; font-size: .8rem; letter-spacing: .02em; border: none; }}

.sia-encabezado {{ display: flex; align-items: center; gap: 1.1rem; padding: 1.15rem 1.35rem 1.15rem 1.6rem; margin-bottom: 1rem;
  border: 1px solid var(--border); border-radius: 18px; position: relative; overflow: hidden; box-shadow: var(--sombra);
  background:
    radial-gradient(240px 160px at 100% 0%, color-mix(in srgb, var(--secondary) 26%, transparent), transparent 70%),
    radial-gradient(200px 140px at 88% 120%, color-mix(in srgb, var(--oliva) 22%, transparent), transparent 70%),
    var(--surface); }}
.sia-encabezado::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px;
  background: linear-gradient(180deg, var(--primary), var(--secondary), var(--oliva)); }}
.sia-encabezado .textos {{ min-width: 0; }}
.sia-encabezado .institucion {{ color: var(--muted); font-size: .82rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .07em; }}
.sia-encabezado h1 {{ font-size: 1.75rem !important; margin: .1rem 0 0 0 !important; padding: 0 !important; color: var(--ink) !important; line-height: 1.2; }}
.sia-encabezado p {{ margin: .2rem 0 0 0; color: var(--ink-2); font-size: 1rem; }}
.sia-encabezado a, .sia-encabezado [data-testid="stHeaderActionElements"] {{ display: none !important; }}

.sia-marca-lateral {{ display: flex; align-items: center; gap: .65rem; padding-bottom: .9rem; margin-bottom: .9rem;
  border-bottom: 1px solid var(--border); }}
.sia-marca-lateral b {{ display: block; font-size: 1rem; color: var(--ink); line-height: 1.25; }}
.sia-marca-lateral small {{ display: block; font-size: .82rem; color: var(--muted); }}

.sia-usuario {{ font-size: .95rem; line-height: 1.45; padding: .5rem .7rem; margin-bottom: .6rem; background: var(--surface-2);
  border: 1px solid var(--border); border-radius: var(--radio-chico); }}
.sia-usuario b {{ display: block; color: var(--ink); }}
.sia-usuario span {{ color: var(--muted); }}

/* ---------- Acceso: tarjeta dividida (panel visual + formulario) ---------- */
.stApp:has(.st-key-sia_login), .stApp:has(.st-key-sia_cambio) {{ background:
    radial-gradient(900px 520px at -5% -10%, color-mix(in srgb, var(--secondary) 22%, transparent), transparent 62%),
    radial-gradient(760px 560px at 105% 110%, color-mix(in srgb, var(--oliva) 20%, transparent), transparent 60%),
    var(--bg) !important; }}
.st-key-sia_login {{ max-width: 1120px; margin: clamp(.4rem, 3vh, 2.2rem) auto 0; background: var(--surface);
  border: 1px solid var(--border); border-radius: 28px; overflow: hidden; gap: 0 !important;
  box-shadow: 0 1px 2px rgba(20, 32, 51, .08), 0 40px 80px -42px rgba(20, 32, 51, .55); }}
.st-key-sia_login [data-testid="stHorizontalBlock"]:has(.sia-login-marca) {{ gap: 0 !important; align-items: stretch; }}
.st-key-sia_login [data-testid="stColumn"]:has(.sia-login-marca) [data-testid="stVerticalBlock"],
.st-key-sia_login [data-testid="stColumn"]:has(.sia-login-marca) [data-testid="stElementContainer"],
.st-key-sia_login [data-testid="stColumn"]:has(.sia-login-marca) [data-testid="stMarkdown"],
.st-key-sia_login [data-testid="stColumn"]:has(.sia-login-marca) [data-testid="stMarkdownContainer"] {{ height: 100%; }}
.st-key-sia_login_form {{ padding: 2.2rem clamp(1.4rem, 4vw, 3.4rem) 2.4rem; gap: .75rem; }}

.sia-login-marca {{ position: relative; overflow: hidden; isolation: isolate; height: 100%; min-height: 640px; color: #fff;
  background: linear-gradient(160deg, var(--marca) 0%, color-mix(in srgb, var(--marca) 70%, var(--primary)) 55%,
    color-mix(in srgb, var(--marca) 55%, var(--secondary)) 100%);
  padding: 2.2rem 2.4rem; display: flex; flex-direction: column; gap: 1.2rem; }}
.sia-login-fondo {{ position: absolute; inset: 0; width: 100%; height: 100%; z-index: -2; }}
.sia-login-marca::after {{ content: ""; position: absolute; inset: 0; z-index: -1; pointer-events: none;
  background: linear-gradient(100deg, rgba(8, 14, 26, .66) 0%, rgba(8, 14, 26, .42) 55%, rgba(8, 14, 26, .14) 100%),
    linear-gradient(180deg, rgba(8, 14, 26, .25) 0%, transparent 22%, transparent 78%, rgba(8, 14, 26, .35) 100%); }}
.sia-login-marca .marca, .sia-login-marca .eyebrow, .sia-login-marca h2, .sia-login-marca p, .sia-login-marca li,
.sia-login-marca .pie {{ text-shadow: 0 1px 2px rgba(6, 10, 18, .6), 0 4px 18px rgba(6, 10, 18, .4); }}
.sia-login-marca .marca {{ display: flex; align-items: center; gap: .8rem; }}
.sia-login-marca .marca b {{ display: block; font-size: 1.02rem; font-weight: 700; color: #fff; line-height: 1.25; }}
.sia-login-marca .marca small {{ display: block; font-size: .82rem; color: rgba(255, 255, 255, .82); font-weight: 500; }}
.sia-login-marca .sia-logo {{ background: #fff; border: 3px solid rgba(255, 255, 255, .3); }}
.sia-login-marca .centro {{ margin: auto 0; display: grid; gap: 1.1rem; max-width: 31rem; padding: 1.5rem 1.6rem;
  border-radius: 22px; border: 1px solid rgba(255, 255, 255, .14);
  background: linear-gradient(140deg, rgba(10, 18, 32, .58), rgba(10, 18, 32, .34));
  -webkit-backdrop-filter: blur(7px) saturate(115%); backdrop-filter: blur(7px) saturate(115%); }}
.sia-login-marca .eyebrow {{ font-size: .8rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase;
  color: color-mix(in srgb, var(--oliva) 28%, #fff); }}
.sia-login-marca h2 {{ color: #fff !important; font-size: clamp(2rem, 3.4vw, 2.75rem) !important; font-weight: 800 !important;
  margin: 0 !important; padding: 0 !important; line-height: 1.08; letter-spacing: -.03em; }}
.sia-login-marca p {{ color: #fff !important; font-size: 1.06rem; margin: 0; line-height: 1.55; }}
.sia-login-marca ul {{ list-style: none; margin: .2rem 0 0; padding: 0; display: grid; gap: .8rem; }}
.sia-login-marca li {{ display: flex; gap: .75rem; align-items: flex-start; color: #fff; margin: 0; }}
.sia-login-marca li svg {{ flex: 0 0 auto; width: 26px; height: 26px; margin-top: .05rem; }}
.sia-login-marca li b {{ display: block; font-size: 1rem; font-weight: 700; color: #fff; }}
.sia-login-marca li span {{ display: block; font-size: .93rem; color: rgba(255, 255, 255, .92); line-height: 1.4; }}
.sia-login-marca .pie {{ font-size: .85rem; color: rgba(255, 255, 255, .9); }}
.sia-login-marca a, .sia-login-marca [data-testid="stHeaderActionElements"] {{ display: none !important; }}

.sia-login-titulo h3 {{ font-size: 2.05rem !important; font-weight: 800 !important; margin: .3rem 0 0 !important; padding: 0 !important;
  letter-spacing: -.025em; color: var(--ink) !important; }}
.sia-login-titulo p {{ color: var(--muted) !important; margin: .35rem 0 .4rem !important; font-size: 1.02rem !important; }}
.sia-login-titulo a, .sia-login-titulo [data-testid="stHeaderActionElements"] {{ display: none !important; }}
/* Campos subrayados (solo en el acceso y en el cambio de contraseña) */
.st-key-sia_login_form [data-testid="stTextInputRootElement"], .st-key-sia_cambio [data-testid="stTextInputRootElement"] {{
  background: transparent !important; border: none !important; border-bottom: 2px solid var(--border-fuerte) !important;
  border-radius: 0 !important; box-shadow: none !important; }}
.st-key-sia_login_form [data-testid="stTextInputRootElement"] *, .st-key-sia_cambio [data-testid="stTextInputRootElement"] * {{
  background: transparent !important; border: none !important; box-shadow: none !important; }}
.st-key-sia_login_form [data-testid="stTextInputRootElement"] input, .st-key-sia_cambio [data-testid="stTextInputRootElement"] input {{
  font-size: 1.05rem !important; padding-left: .1rem !important; }}
.st-key-sia_login_form [data-testid="stTextInputRootElement"]:focus-within,
.st-key-sia_cambio [data-testid="stTextInputRootElement"]:focus-within {{ border-bottom-color: var(--primary) !important; box-shadow: none !important; }}
.st-key-sia_login_form [data-testid="stForm"], .st-key-sia_cambio [data-testid="stForm"] {{
  background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }}
/* Botón principal redondeado en degradé (acceso y cambio de contraseña) */
.st-key-sia_login_form button[data-testid^="stBaseButton-primary"], .st-key-sia_cambio button[data-testid^="stBaseButton-primary"] {{
  border-radius: 999px !important; min-height: 3.1rem; border: none !important; margin-top: .35rem;
  background: linear-gradient(100deg, var(--boton-a), var(--boton-b)) !important;
  box-shadow: 0 12px 24px -14px color-mix(in srgb, var(--boton-b) 85%, transparent) !important; }}
.st-key-sia_login_form button[data-testid^="stBaseButton-primary"] p, .st-key-sia_cambio button[data-testid^="stBaseButton-primary"] p {{
  color: #fff !important; font-size: 1.05rem !important; font-weight: 700 !important; letter-spacing: .01em; }}
.st-key-sia_login_form button[data-testid^="stBaseButton-primary"]:hover, .st-key-sia_cambio button[data-testid^="stBaseButton-primary"]:hover {{
  filter: brightness(1.08); }}
.sia-login-ayuda {{ color: var(--muted) !important; font-size: .93rem !important; line-height: 1.5; margin: .2rem 0 0 !important; }}
.sia-login-ayuda b {{ color: var(--ink); }}
.sia-login-separador {{ display: flex; align-items: center; gap: .8rem; color: var(--muted); font-size: .9rem; font-weight: 600; margin: .4rem 0 0; }}
.sia-login-separador::before, .sia-login-separador::after {{ content: ""; flex: 1; height: 1px; background: var(--border-fuerte); }}
.st-key-sia_tema_login {{ align-items: flex-end; }}
.sia-demo {{ display: grid; gap: .45rem; font-size: .93rem; color: var(--ink-2); }}
.sia-demo .fila {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: .2rem .55rem; padding: .45rem .6rem;
  border-radius: var(--radio-chico); background: var(--surface-2); border: 1px solid var(--border); }}
.sia-demo .fila b {{ color: var(--ink); min-width: 7.5rem; }}
.sia-demo code {{ font-size: .9rem; padding: .05rem .35rem; border-radius: 6px; background: var(--campo); color: var(--ink);
  border: 1px solid var(--border); }}
.sia-demo p {{ margin: .2rem 0 0 !important; font-size: .9rem !important; color: var(--muted) !important; }}

/* Cambio obligatorio de contraseña */
.st-key-sia_cambio {{ max-width: 600px; margin: clamp(1rem, 7vh, 4rem) auto 0; background: var(--surface); border: 1px solid var(--border);
  border-radius: 24px; padding: 2rem clamp(1.2rem, 4vw, 2.4rem) 1.8rem; box-shadow: 0 40px 80px -46px rgba(20, 32, 51, .55); }}
.sia-cambio-cabecera {{ display: flex; gap: 1rem; align-items: flex-start; }}
.sia-cambio-cabecera .eyebrow {{ font-size: .8rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--primary); }}
.sia-cambio-cabecera h2 {{ font-size: 1.6rem !important; margin: .2rem 0 .3rem !important; padding: 0 !important; color: var(--ink) !important; }}
.sia-cambio-cabecera p {{ color: var(--ink-2) !important; margin: 0 !important; }}
.sia-cambio-cabecera a, .sia-cambio-cabecera [data-testid="stHeaderActionElements"] {{ display: none !important; }}

.sia-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radio); padding: 1rem 1.1rem;
  margin-bottom: .75rem; color: var(--ink); overflow-wrap: anywhere; box-shadow: var(--sombra); }}
.sia-card .muted, .sia-muted {{ color: var(--muted); font-size: .93rem; }}
.sia-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .85rem; margin-bottom: 1.2rem; }}
.sia-grid .sia-card {{ margin-bottom: 0; }}
/* Indicadores circulares: anillo proporcional al dato, valor al centro, etiqueta y contexto debajo */
.sia-kpi {{ display: flex; flex-direction: column; align-items: center; text-align: center; gap: .55rem; padding: 1.1rem .9rem 1rem;
  --acento-tarjeta: var(--primary);
  background: linear-gradient(155deg, color-mix(in srgb, var(--acento-tarjeta) 18%, var(--surface)), var(--surface) 76%) !important; }}
.sia-grid > .sia-kpi:nth-child(3n+2) {{ --acento-tarjeta: var(--secondary); }}
.sia-grid > .sia-kpi:nth-child(3n) {{ --acento-tarjeta: var(--oliva); }}
.sia-anillo {{ position: relative; width: var(--d, 112px); aspect-ratio: 1; flex: 0 0 auto;
  --arco: var(--tono, var(--acento-tarjeta, var(--primary)));
  transition: transform .2s ease; }}
.sia-anillo::before {{ content: ""; position: absolute; inset: 5%; border-radius: 50%;
  background: conic-gradient(var(--arco) var(--progreso), color-mix(in srgb, var(--arco) 24%, var(--track)) 0);
  mask-image: radial-gradient(farthest-side, transparent calc(100% - 8px), #000 calc(100% - 7px)); }}
.sia-anillo.sin-datos {{ --arco: color-mix(in srgb, var(--acento-tarjeta, var(--primary)) 70%, var(--surface)); }}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {{
  .sia-kpi:hover .sia-anillo {{ transform: scale(1.04); }}
}}
.sia-anillo .centro {{ position: absolute; inset: 14%; border-radius: 50%; display: flex; flex-direction: column;
  align-items: center; justify-content: center; line-height: 1.1; }}
.sia-kpi .value {{ font-size: var(--fs, 1.45rem); font-weight: 700; color: var(--ink); font-variant-numeric: tabular-nums;
  letter-spacing: -.02em; max-width: 100%; overflow-wrap: anywhere; }}
.sia-kpi .label {{ font-size: .95rem; font-weight: 700; color: var(--ink); line-height: 1.3; }}
.sia-kpi .sub {{ font-size: .86rem; color: var(--muted); line-height: 1.35; margin-top: -.3rem; }}
.sia-kpi.texto .value {{ font-size: 1.05rem; }}

.sia-chips {{ display: flex; flex-wrap: wrap; gap: .35rem; margin: .3rem 0 .6rem; }}
.sia-chip {{ display: inline-flex; align-items: center; padding: .2rem .6rem; border-radius: 999px; background: var(--surface-2);
  color: var(--ink-2); font-size: .86rem; font-weight: 600; border: 1px solid var(--border); }}
.sia-badge {{ display: inline-block; padding: .12rem .55rem; border-radius: 999px; font-size: .82rem; font-weight: 700;
  color: var(--primary) !important; background: var(--primary-soft); border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent); }}
.sia-code {{ font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace !important; font-size: 1.2rem; font-weight: 600;
  letter-spacing: .1em; color: var(--ink); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radio-chico);
  padding: .3rem .7rem; display: inline-block; max-width: 100%; overflow-wrap: anywhere; }}
.sia-pin {{ font-size: 2.2rem; letter-spacing: .25em; }}

.sia-alerta, .sia-riesgo {{ border-radius: var(--radio); padding: .75rem .95rem; margin-bottom: .6rem; background: var(--surface);
  border: 1px solid var(--border); border-left: 3px solid var(--tono, var(--critico)); color: var(--ink); overflow-wrap: anywhere; }}
.sia-alerta b, .sia-riesgo b {{ color: var(--ink); font-weight: 600; }}
.sia-alerta span {{ color: var(--ink-2); font-size: .95rem; }}
.sia-riesgo .etiqueta {{ display: inline-block; font-size: .8rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--tono, var(--critico)); margin-bottom: .15rem; }}
.sia-riesgo ul {{ margin: .3rem 0 0 1rem; padding: 0; }}
.sia-riesgo li {{ margin: .1rem 0; color: var(--ink-2); font-size: .95rem; }}
.sia-aviso, .sia-aviso-camara {{ background: var(--surface-2); color: var(--ink-2); border: 1px solid var(--border);
  border-left: 4px solid var(--primary); border-radius: var(--radio-chico); padding: .7rem .9rem; margin: .3rem 0 .7rem;
  font-size: .95rem; line-height: 1.5; }}
.sia-aviso b {{ color: var(--ink); }}
.sia-barra {{ height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; margin-top: .5rem; }}
.sia-barra > div {{ height: 100%; background: var(--tono); }}

/* Tablas responsivas (sin scroll horizontal) */
.sia-tabla {{ width: 100%; max-width: 100%; margin: .3rem 0 1rem; }}
.sia-tabla table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radio); overflow: hidden; font-size: .95rem; }}
.sia-tabla th {{ background: color-mix(in srgb, var(--primary) 9%, var(--surface-2)); color: var(--ink-2); text-align: left; font-weight: 700; padding: .6rem .75rem;
  font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; border-bottom: 1px solid var(--border-fuerte); }}
.sia-tabla td {{ padding: .6rem .75rem; color: var(--ink); border-bottom: 1px solid var(--border); overflow-wrap: break-word; vertical-align: top;
  font-variant-numeric: tabular-nums; }}
.sia-tabla tr:last-child td {{ border-bottom: none; }}
.sia-tabla tbody td {{ transition: background-color .15s ease; }}
.sia-tabla tbody tr:hover td {{ background: color-mix(in srgb, var(--primary) 7%, transparent); }}
.sia-tabla .sia-vacio {{ color: var(--muted); }}
.sia-mini-barra {{ height: 4px; border-radius: 2px; background: var(--surface-2); margin-top: .3rem; overflow: hidden; max-width: 140px; }}
.sia-mini-barra > div {{ height: 100%; background: var(--tono); }}
.sia-estado {{ display: inline-flex; align-items: center; gap: .35rem; font-weight: 500; }}
.sia-estado::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--tono); flex: 0 0 auto; }}
@media (max-width: 640px) {{
  .sia-tabla table, .sia-tabla tbody, .sia-tabla tr, .sia-tabla td {{ display: block; width: 100%; }}
  .sia-tabla table {{ border: none; background: transparent; }}
  .sia-tabla thead {{ display: none; }}
  .sia-tabla tr {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radio); margin-bottom: .5rem; padding: .3rem 0; }}
  .sia-tabla td {{ border: none; padding: .2rem .7rem; display: flex; gap: .6rem; }}
  .sia-tabla td::before {{ content: attr(data-label); flex: 0 0 38%; color: var(--muted); font-size: .8rem; font-weight: 700;
    text-transform: uppercase; letter-spacing: .03em; }}
}}

/* Historial: una marca por clase (letra + color, nunca color solo) */
.sia-hist {{ display: grid; gap: .5rem; margin: .4rem 0 1rem; }}
.sia-hist-fila {{ display: grid; grid-template-columns: minmax(150px, 220px) 1fr; gap: .4rem .9rem; align-items: center;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radio); padding: .55rem .75rem; }}
.sia-hist-nombre b {{ color: var(--ink); font-size: .98rem; font-weight: 700; overflow-wrap: anywhere; }}
.sia-hist-nombre small {{ display: block; color: var(--muted); font-size: .86rem; }}
.sia-hist-marcas {{ display: flex; flex-wrap: wrap; gap: .25rem; min-width: 0; }}
.sia-marca {{ display: inline-flex; flex-direction: column; align-items: center; min-width: 2.4rem; padding: .1rem .2rem .15rem;
  border-radius: 6px; font-size: .86rem; font-weight: 700; line-height: 1.15; border: 1px solid transparent; }}
.sia-marca small {{ font-size: .7rem; font-weight: 600; color: var(--muted); }}
.sia-marca.presente {{ background: color-mix(in srgb, var(--bueno) 12%, var(--surface)); color: var(--bueno); }}
.sia-marca.tarde {{ background: color-mix(in srgb, #fab219 18%, var(--surface)); color: var(--advertencia); }}
.sia-marca.justificado {{ background: color-mix(in srgb, #2a78d6 12%, var(--surface)); color: #2a78d6; }}
.sia-marca.ausente {{ background: color-mix(in srgb, var(--critico) 12%, var(--surface)); color: var(--critico); }}
.sia-leyenda {{ display: flex; flex-wrap: wrap; gap: .8rem; font-size: .9rem; color: var(--muted); margin: .2rem 0 .4rem; }}
.sia-leyenda .sia-marca {{ min-width: 1.6rem; display: inline-flex; flex-direction: row; margin-right: .25rem; }}
@media (max-width: 640px) {{ .sia-hist-fila {{ grid-template-columns: 1fr; }} }}

.sia-pie {{ margin-top: 2.5rem; padding-top: .9rem; border-top: 1px solid var(--border); display: flex; align-items: center;
  justify-content: center; gap: .5rem; flex-wrap: wrap; color: var(--muted); font-size: .86rem; }}
.sia-pie img {{ width: 28px; height: 28px; object-fit: contain; background: #fff; border-radius: 4px; border: 1px solid var(--border); }}

@media (max-width: 768px) {{
  .block-container {{ padding: 3.4rem .8rem 3rem !important; }}
  .sia-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }}
  .sia-kpi {{ padding: .9rem .5rem .8rem; }}
  .sia-anillo {{ --d: 92px; }}
  .sia-kpi .value {{ font-size: calc(var(--fs, 1.45rem) * .88); }}
  .st-key-sia_login {{ border-radius: 20px; margin-top: 0; }}
  .st-key-sia_login [data-testid="stHorizontalBlock"]:has(.sia-login-marca) {{ gap: 0 !important; }}
  .sia-login-marca {{ min-height: 0; padding: 1.4rem 1.3rem 1.6rem; gap: .9rem; }}
  .sia-login-marca .centro {{ margin: .4rem 0 0; gap: .6rem; padding: 1rem 1.05rem; border-radius: 16px; }}
  .sia-login-marca h2 {{ font-size: 1.75rem !important; }}
  .sia-login-marca p {{ font-size: .98rem; }}
  .sia-login-marca ul, .sia-login-marca .pie {{ display: none; }}
  .st-key-sia_login_form {{ padding: 1.4rem 1.15rem 1.6rem; }}
  .sia-login-titulo h3 {{ font-size: 1.65rem !important; }}
  .st-key-sia_cambio {{ border-radius: 18px; margin-top: .5rem; }}
  .sia-cambio-cabecera {{ flex-direction: column; gap: .6rem; }}
  .sia-cambio-cabecera h2 {{ font-size: 1.4rem !important; }}
  .sia-encabezado {{ padding: .9rem 1rem .9rem 1.25rem; gap: .8rem; }}
  .sia-encabezado h1 {{ font-size: 1.35rem !important; }}
  .sia-encabezado p {{ font-size: .93rem; }}
  .sia-pin {{ font-size: 1.7rem; letter-spacing: .16em; }}
  .stTabs [role="tablist"] {{ gap: .2rem 1rem; }}
  [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: .7rem !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }}
}}
@media (max-width: 340px) {{ .sia-grid {{ grid-template-columns: 1fr; }} }}
</style>
"""

# Modo oscuro: tablas nativas (canvas) se oscurecen con un filtro; el resto usa las variables.
_CSS_OSCURO = """
<style>
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { filter: invert(0.9) hue-rotate(180deg); }
[data-testid="stAlertContainer"] { background: var(--surface-2) !important; border: 1px solid var(--border-fuerte) !important; }
.sia-login-marca::after { background: linear-gradient(100deg, rgba(6, 10, 18, .72) 0%, rgba(6, 10, 18, .48) 55%, rgba(6, 10, 18, .18) 100%); }
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] li { color: var(--ink) !important; }
.sia-logo { background: #fff; }
</style>
"""

# Elementos flotantes de Streamlit / Streamlit Cloud. Se inyecta en la app y, mediante el script PWA, también en
# la página contenedora de Streamlit Cloud (mismo dominio). Ver docs/ARQUITECTURA.md.
CSS_OCULTAR_CLOUD = """
.stAppViewerFooter, footer, [data-testid="stStatusWidget"], [data-testid="stDecoration"], [data-testid="stToolbarActions"],
[data-testid="stToolbarActionButton"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="manage-app-button"], .stDeployButton, [class*="viewerBadge"], [class*="ViewerBadge"],
[class*="_profileContainer_"], [class*="_profilePreview_"], a[href^="https://streamlit.io/cloud"],
a[href*="share.streamlit.io/user/"], iframe[title="streamlit_badge"] {
  display: none !important; visibility: hidden !important; opacity: 0 !important; pointer-events: none !important;
}
/* stToolbar: oculto con visibility porque contiene el botón ">>" de la barra lateral en celulares. */
[data-testid="stToolbar"] { visibility: hidden !important; }
[data-testid="stExpandSidebarButton"] { visibility: visible !important; opacity: 1 !important; pointer-events: auto !important; }
"""

SELECTORES_FLOTANTES_CLOUD = ", ".join([
    '[class*="viewerBadge"]', '[class*="ViewerBadge"]', '[class*="_profileContainer_"]', '[class*="_profilePreview_"]',
    'a[href^="https://streamlit.io/cloud"]', 'a[href*="share.streamlit.io/user/"]', 'iframe[title="streamlit_badge"]',
    '.stAppViewerFooter', '[data-testid="manage-app-button"]',
])

# Solo en la página contenedora de Cloud; nunca oculta un contenedor que incluya la app.
CSS_SOLO_CONTENEDOR = """
div[style*="position: fixed"][style*="bottom"]:not(:has(iframe:not([title="streamlit_badge"]))) {
  display: none !important; visibility: hidden !important; opacity: 0 !important; pointer-events: none !important;
}
"""


def inyectar_css() -> None:
    css = _CSS.format(variables=_variables(), fuente=FUENTE) + f"<style>{CSS_OCULTAR_CLOUD}</style>"
    st.markdown(css + (_CSS_OSCURO if modo_oscuro() else ""), unsafe_allow_html=True)


def _sincronizar_tema(clave: str) -> None:
    st.session_state[CLAVE_TEMA] = bool(st.session_state.get(clave))


def selector_tema(lugar: str = "sidebar") -> None:
    """Interruptor claro/oscuro. La preferencia vive en CLAVE_TEMA (no en la clave del widget), así sobrevive al
    pasar del acceso al panel y a los cambios de perfil."""
    clave = f"_tg_tema_{lugar}"
    with st.container(key=f"sia_tema_{lugar}"):
        st.toggle("Modo oscuro", value=modo_oscuro(), key=clave, on_change=_sincronizar_tema, args=(clave,))


# ---------------------------------------------------------------- componentes
def _html(texto: str) -> str:
    """Escapa y evita que "N° 11" se parta en dos líneas."""
    return escape(texto).replace("N° ", "N°&nbsp;").replace("Nº ", "Nº&nbsp;")


def encabezado(titulo: str, subtitulo: str = "") -> None:
    """Encabezado de cada panel: institución, nombre del panel («dónde estoy») y para qué sirve."""
    t = tema()
    st.markdown(
        f'<div class="sia-encabezado">{logo_html(44)}<div class="textos"><div class="institucion">{_html(t["nombre"])}</div>'
        f'<h1>{_html(titulo)}</h1>{f"<p>{_html(subtitulo)}</p>" if subtitulo else ""}</div></div>',
        unsafe_allow_html=True,
    )


hero = encabezado  # compatibilidad


def marca_sidebar() -> None:
    t = tema()
    st.markdown(f'<div class="sia-marca-lateral">{logo_html(36)}<div><b>{_html(t["corto"])}</b>'
                f'<small>{PRODUCTO} · {PRODUCTO_LARGO}</small></div></div>', unsafe_allow_html=True)


_CHECK = ('<svg viewBox="0 0 26 26" aria-hidden="true"><circle cx="13" cy="13" r="12" fill="rgba(255,255,255,.14)" '
          'stroke="rgba(255,255,255,.55)"/><path d="M8 13.4l3.2 3.1L18 9.8" fill="none" stroke="#fff" stroke-width="2.2" '
          'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _fondo_organico(primario: str, secundario: str) -> str:
    """Formas orgánicas en degradé: colores de la institución + verde oliva y verde azulado de la paleta SIA."""
    claro = mezclar(secundario, "#FFFFFF", 0.38)
    oliva_claro = mezclar(OLIVA, "#FFFFFF", 0.3)
    return (
        '<svg class="sia-login-fondo" viewBox="0 0 600 760" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
        "<defs>"
        f'<linearGradient id="sia-g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{claro}"/>'
        f'<stop offset="1" stop-color="{secundario}"/></linearGradient>'
        f'<linearGradient id="sia-g2" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="{OLIVA}"/>'
        f'<stop offset="1" stop-color="{VERDE_AZULADO}"/></linearGradient>'
        f'<linearGradient id="sia-g3" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{oliva_claro}"/>'
        f'<stop offset="1" stop-color="{VERDE_AZULADO}"/></linearGradient>'
        f'<linearGradient id="sia-g4" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{oliva_claro}"/>'
        f'<stop offset="1" stop-color="{secundario}"/></linearGradient>'
        '<pattern id="sia-puntos" width="16" height="16" patternUnits="userSpaceOnUse">'
        '<circle cx="2" cy="2" r="1.5" fill="rgba(255,255,255,.38)"/></pattern>'
        "</defs>"
        '<path d="M430,-50 C560,-40 660,60 636,196 C614,316 512,342 444,298 C372,252 326,168 340,86 C352,16 366,-54 430,-50Z" '
        'fill="url(#sia-g1)" opacity=".92"/>'
        '<path d="M-70,548 C-16,468 124,456 198,530 C270,604 248,722 164,772 C82,820 -42,804 -86,722 C-118,662 -108,604 -70,548Z" '
        'fill="url(#sia-g2)" opacity=".95"/>'
        '<path d="M520,420 C596,410 648,476 636,560 C624,646 560,700 496,676 C434,654 414,590 436,516 C452,462 478,426 520,420Z" '
        'fill="url(#sia-g3)" opacity=".9"/>'
        '<path d="M78,96 C118,66 182,78 192,132 C202,186 158,214 114,204 C70,194 38,140 78,96Z" fill="url(#sia-g4)" opacity=".55"/>'
        '<path d="M318,686 C366,644 446,654 466,706 C486,758 434,800 372,790 C310,780 270,728 318,686Z" '
        'fill="url(#sia-g1)" opacity=".7"/>'
        '<path d="M640,250 C590,256 548,294 560,338 C572,380 612,388 640,372Z" fill="url(#sia-g2)" opacity=".75"/>'
        '<rect x="44" y="236" width="96" height="64" fill="url(#sia-puntos)"/>'
        '<rect x="430" y="598" width="128" height="80" fill="url(#sia-puntos)"/>'
        "</svg>"
    )


def panel_login(items: list[tuple[str, str]]) -> None:
    """Panel visual del acceso: bienvenida sobre formas orgánicas con la identidad de la institución."""
    t = tema()
    lista = "".join(f"<li>{_CHECK}<div><b>{escape(titulo)}</b><span>{escape(detalle)}</span></div></li>"
                    for titulo, detalle in items)
    st.markdown(
        f'<div class="sia-login-marca">{_fondo_organico(t["primario"], t["secundario"])}'
        f'<div class="marca">{logo_html(52)}<div><b>{_html(t["corto"])}</b><small>{_html(t["nombre"])}</small></div></div>'
        f'<div class="centro"><span class="eyebrow">{PRODUCTO} · {PRODUCTO_LARGO}</span>'
        f'<h2>¡Hola de nuevo!</h2><p>Ingresá para registrar y consultar la asistencia de {_html(t["corto"])}, '
        f"desde la compu o el celular.</p><ul>{lista}</ul></div>"
        f'<div class="pie">Desarrollado por {EQUIPO}</div></div>',
        unsafe_allow_html=True,
    )


def titulo_login(titulo: str, bajada: str) -> None:
    st.markdown(f'<div class="sia-login-titulo"><h3>{escape(titulo)}</h3><p>{escape(bajada)}</p></div>',
                unsafe_allow_html=True)


def footer() -> None:
    logo = _logo_tech()
    img = f'<img src="{logo}" alt="Logo {EQUIPO}">' if logo else ""
    st.markdown(f'<div class="sia-pie">{img}<span>{PRODUCTO} · Desarrollado por {EQUIPO}</span></div>',
                unsafe_allow_html=True)


def aviso(html_seguro: str) -> None:
    st.markdown(f'<div class="sia-aviso">{html_seguro}</div>', unsafe_allow_html=True)


def _pct_de(valor) -> float | None:
    """Extrae el porcentaje de un valor como «60.8%» (para dibujar el anillo)."""
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*%\s*", str(valor))
    return float(m.group(1).replace(",", ".")) if m else None


def anillo_html(valor, pct: float | None, color: str | None = None, diametro: int | None = None) -> str:
    """Dibuja la proporción o un anillo institucional para valores sin denominador."""
    texto = str(valor)
    fs = 1.45 if len(texto) <= 4 else 1.2 if len(texto) <= 6 else 1.0 if len(texto) <= 8 else .85
    progreso = 100.0 if pct is None else max(0.0, min(100.0, float(pct)))
    estilo = f"--fs:{fs}rem;--progreso:{progreso:.2f}%;"
    estilo += (f"--tono:{color};" if color else "") + (f"--d:{diametro}px;" if diametro else "")
    css = "sia-anillo sin-datos" if texto == "—" else "sia-anillo"
    etiqueta = texto if pct is None or _pct_de(texto) is not None else f"{texto}, {progreso:.1f}%"
    return (f'<div class="{css}" style="{estilo}" role="img" aria-label="{escape(etiqueta)}">'
            f'<div class="centro"><span class="value">{escape(texto)}</span></div></div>')


def _kpi_html(label: str, valor, sub: str = "", tono: str = "neutro", pct: float | None = None) -> str:
    """Tarjeta circular. pct: proporción a dibujar (si el valor es «NN%» se toma de ahí). tono: color de estado
    (rojo / ámbar / verde) o el color institucional para «neutro»."""
    color = TONOS[tono] if tono in ("rojo", "ambar", "verde") else None
    pct = _pct_de(valor) if pct is None else pct
    return (f'<div class="sia-card sia-kpi">{anillo_html(valor, pct, color)}'
            f'<div class="label">{escape(label)}</div>{f"<div class=sub>{escape(sub)}</div>" if sub else ""}</div>')


def kpi(label: str, valor, sub: str = "", tono: str = "neutro", pct: float | None = None) -> None:
    st.markdown(_kpi_html(label, valor, sub, tono, pct), unsafe_allow_html=True)


def kpi_grid(items: list[tuple]) -> None:
    """items: (etiqueta, valor, contexto, tono[, pct])."""
    st.markdown(f'<div class="sia-grid">{"".join(_kpi_html(*i) for i in items)}</div>', unsafe_allow_html=True)


def tarjeta_progreso(titulo: str, valor: str, detalle: str, pct: float, tono: str) -> str:
    """Tarjeta circular de una materia: el anillo muestra el porcentaje de asistencia."""
    color = TONOS.get(tono) if tono in ("rojo", "ambar", "verde") else None
    centro = f"{pct:.0f}%" if valor != "—" else "—"
    return (f'<div class="sia-card sia-kpi">{anillo_html(centro, pct if valor != "—" else None, color)}'
            f'<div class="label">{escape(titulo)}</div><div class="sub">{escape(valor if valor != "—" else detalle)}'
            f'{"<br>" + escape(detalle) if valor != "—" else ""}</div></div>')


def chips(items: list[str]) -> str:
    return '<div class="sia-chips">' + "".join(f'<span class="sia-chip">{escape(i)}</span>' for i in items if i) + "</div>"


def badge(texto: str, tono: str = "azul") -> str:
    return f'<span class="sia-badge">{escape(texto)}</span>'


def alerta(titulo: str, detalle: str, color: str) -> None:
    st.markdown(f'<div class="sia-alerta" style="--tono:{color}"><b>{escape(titulo)}</b><br><span>{escape(detalle)}</span></div>',
                unsafe_allow_html=True)


def codigo(texto: str, grande: bool = False) -> None:
    st.markdown(f'<div class="{"sia-code sia-pin" if grande else "sia-code"}">{escape(texto)}</div>', unsafe_allow_html=True)


def aviso_camara(texto: str) -> None:
    st.markdown(f'<div class="sia-aviso-camara">{escape(texto)}</div>', unsafe_allow_html=True)


def mostrar_errores(errores: list[str]) -> None:
    st.error("**Revisá el formulario:**\n" + "\n".join(f"- {e}" for e in errores))


class Html(str):
    """Fragmento HTML ya seguro para insertar sin escapar en `tabla_html`."""


def _celda(valor) -> str:
    if isinstance(valor, Html):
        return str(valor)
    if valor is None or (isinstance(valor, float) and valor != valor):
        return '<span class="sia-vacio">—</span>'
    return escape(str(valor))


def tabla_html(filas: list[dict], columnas: dict[str, str], vacio: str = "Sin datos.") -> None:
    """Tabla responsiva: en celulares cada fila es una tarjeta (nunca hay scroll horizontal)."""
    if not filas:
        st.markdown(f'<div class="sia-tabla"><span class="sia-vacio">{escape(vacio)}</span></div>', unsafe_allow_html=True)
        return
    cabecera = "".join(f"<th>{escape(t)}</th>" for t in columnas.values())
    cuerpo = "".join("<tr>" + "".join(f'<td data-label="{escape(t)}">{_celda(f.get(k))}</td>' for k, t in columnas.items())
                     + "</tr>" for f in filas)
    st.markdown(f'<div class="sia-tabla"><table><thead><tr>{cabecera}</tr></thead><tbody>{cuerpo}</tbody></table></div>',
                unsafe_allow_html=True)


def mini_barra(pct: float, tono: str) -> Html:
    return Html(f'{pct:.0f}%<div class="sia-mini-barra" style="--tono:{TONOS.get(tono, tono)}">'
                f'<div style="width:{max(0, min(100, pct)):.0f}%"></div></div>')


def estado_html(texto: str, color: str) -> Html:
    """Estado con punto de color + texto (el color nunca va solo)."""
    return Html(f'<span class="sia-estado" style="--tono:{color}">{escape(texto)}</span>')


LETRA_ESTADO = {"presente": "P", "tarde": "T", "justificado": "J", "ausente": "A"}
SIMBOLOS_ESTADO = LETRA_ESTADO


def leyenda_historial() -> None:
    items = "".join(f'<span><span class="sia-marca {e}">{LETRA_ESTADO[e]}</span>{e.capitalize()}</span>'
                    for e in ("presente", "tarde", "justificado", "ausente"))
    st.markdown(f'<div class="sia-leyenda">{items}</div>', unsafe_allow_html=True)


def grilla_historial(grupos: list[tuple[str, str, float, str, list[tuple[str, str]]]]) -> None:
    """Historial sin matriz ancha: (título, subtítulo, %, tono, [(fecha ISO, estado), ...])."""
    filas = []
    for titulo, subtitulo, pct, tono, marcas in grupos:
        celdas = "".join(
            f'<span class="sia-marca {escape(estado)}" title="{escape(fecha)} · {escape(estado)}">'
            f'{LETRA_ESTADO.get(estado, "·")}<small>{escape(fecha[8:10])}/{escape(fecha[5:7])}</small></span>'
            for fecha, estado in marcas)
        filas.append(f'<div class="sia-hist-fila"><div class="sia-hist-nombre"><b>{escape(titulo)}</b>'
                     f'<small>{escape(subtitulo)}</small>{mini_barra(pct, tono)}</div>'
                     f'<div class="sia-hist-marcas">{celdas}</div></div>')
    st.markdown(f'<div class="sia-hist">{"".join(filas)}</div>', unsafe_allow_html=True)


def banner_riesgo(titulo: str, items: list[str], nivel: str = "alto") -> None:
    color = ESTADO["critico"] if nivel == "alto" else ESTADO["advertencia"]
    etiqueta = "Riesgo de regularidad" if nivel == "alto" else "Atención"
    lista = "".join(f"<li>{escape(i)}</li>" for i in items)
    st.markdown(f'<div class="sia-riesgo" role="alert" style="--tono:{color}"><span class="etiqueta">{etiqueta}</span><br>'
                f'<b>{escape(titulo)}</b><ul>{lista}</ul></div>', unsafe_allow_html=True)


def tono_porcentaje(pct: float, umbral: float) -> str:
    if pct < umbral:
        return "rojo"
    return "ambar" if pct < umbral + 10 else "verde"


# ---------------------------------------------------------------- gráficos
def series() -> list[str]:
    return SERIES_OSCURO if modo_oscuro() else SERIES_CLARO


def color_serie_unica() -> str:
    """Una sola serie: el acento de la institución (aclarado en modo oscuro)."""
    primario = tema()["primario"]
    return _aclarar_para_oscuro(primario) if modo_oscuro() else primario


def estilo_plotly(fig, alto: int = 340, titulo: str | None = None):
    """Estilo analítico sobrio: grilla en líneas finas, ejes recesivos, sin títulos de leyenda, una sola escala."""
    oscuro = modo_oscuro()
    tinta, secundaria, apagada = ("#EEF0EC", "#D3D9E0", "#A9B3C2") if oscuro else (MARINO, "#26344A", "#4E596A")
    grilla, base = ("#2A3B55", "#3B4F6C") if oscuro else ("#DDE1D9", "#B4BCAF")
    if titulo is not None:
        fig.update_layout(title_text=titulo)
    leyenda = sum(1 for t in fig.data if t.showlegend is not False) > 1
    fig.update_layout(
        template="plotly_dark" if oscuro else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=alto,
        margin=dict(l=8, r=12, t=48 if fig.layout.title.text else 12, b=46 if leyenda else 8),
        font=dict(family=FUENTE.replace("'", ""), size=13, color=secundaria),
        title=dict(x=0, xanchor="left", y=0.97, yanchor="top", yref="container", font=dict(size=16, color=tinta)),
        legend=dict(orientation="h", yanchor="bottom", y=0, yref="container", xanchor="left", x=0, title_text="",
                    font=dict(size=13, color=secundaria), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=SUPERFICIE_OSCURA if oscuro else "#ffffff", bordercolor=grilla,
                        font=dict(color=tinta, size=13, family=FUENTE.replace("'", ""))),
        colorway=series(), bargap=0.35, hovermode="closest", separators=",.",
    )
    ejes = dict(gridcolor=grilla, gridwidth=1, zeroline=False, linecolor=base, showline=True, ticks="",
                tickfont=dict(color=apagada, size=12.5), title_font=dict(color=secundaria, size=13))
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    fig.update_traces(selector=dict(type="bar"), marker_line_width=0)
    try:
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=4)
    except (ValueError, TypeError):
        pass
    fig.update_traces(selector=dict(type="scatter"), line_width=2, marker_size=8)
    fig.update_annotations(font_color=secundaria, font_size=12.5)
    return fig


def linea_referencia(fig, valor: float, texto: str, eje: str = "y") -> None:
    """Umbral como línea fina continua (no punteada) con su etiqueta."""
    color = "#9FAABB" if modo_oscuro() else "#5A6475"
    if eje == "y":
        fig.add_hline(y=valor, line_width=1, line_color=color, annotation_text=texto, annotation_position="top left")
    else:
        fig.add_vline(x=valor, line_width=1, line_color=color, annotation_text=texto, annotation_position="top right")
