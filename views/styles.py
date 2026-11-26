"""Sistema visual de SIA: sobrio, corporativo y personalizable por institución (white-label).

Principios: superficies neutras, un único color de acento (el primario de cada institución), bordes finos,
sin degradés ni sombras marcadas, tipografía Inter. Los colores y el logo se toman de la institución
activa (`configurar_tema`); si no hay ninguna, se usan los valores por defecto de SIA.
"""
from __future__ import annotations

import base64
import colorsys
import hashlib
import io
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
CLAVE_TEMA = "modo_oscuro"
EQUIPO = "Tech & Innovation Team"
PRODUCTO = "SIA"
PRODUCTO_LARGO = "Sistema de Asistencia Inteligente"

# Valores por defecto (sin institución activa)
PRIMARIO_DEFECTO = "#1F4E8C"
SECUNDARIO_DEFECTO = "#6B7A99"

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


def _aclarar_para_oscuro(color: str) -> str:
    """En modo oscuro el acento se aclara hasta contrastar al menos 4.5:1 con la superficie."""
    h, luz, s = colorsys.rgb_to_hls(*_rgb(color))
    for _ in range(12):
        candidato = _hex(colorsys.hls_to_rgb(h, luz, s))
        if contraste(candidato, "#161A21") >= 4.5:
            return candidato
        luz = min(0.85, luz + 0.05)
    return _hex(colorsys.hls_to_rgb(h, luz, s))


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
    primario = t["primario"]
    if modo_oscuro():
        acento = _aclarar_para_oscuro(primario)
        return f"""
  --bg: #0E1116; --surface: #161A21; --surface-2: #1D222B; --border: #2A303A; --border-fuerte: #3A414D;
  --ink: #E8EAED; --ink-2: #C4C9D2; --muted: #9AA3AF;
  --primary: {acento}; --primary-ink: {tinta_sobre(acento)}; --primary-soft: {mezclar(acento, '#161A21', 0.82)};
  --primary-hover: {mezclar(acento, '#FFFFFF', 0.12)};
  --grid: #2c2c2a; --sombra: none;
"""
    return f"""
  --bg: #F6F7F9; --surface: #FFFFFF; --surface-2: #F1F3F6; --border: #E5E7EB; --border-fuerte: #D1D5DB;
  --ink: #111827; --ink-2: #374151; --muted: #6B7280;
  --primary: {primario}; --primary-ink: {tinta_sobre(primario)}; --primary-soft: {mezclar(primario, '#FFFFFF', 0.90)};
  --primary-hover: {mezclar(primario, '#000000', 0.12)};
  --grid: #e1e0d9; --sombra: 0 1px 2px rgba(17, 24, 39, .05);
"""


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root, .stApp {{ {variables}
  --critico: #d03b3b; --advertencia: #b7791f; --bueno: #0a7f0a; --radio: 8px; --radio-chico: 6px; }}

/* Tipografía (sin tocar los íconos Material de Streamlit) */
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp td, .stApp th, .stApp small,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"], [role="tab"], [role="option"] {{
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}}
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ font-weight: 600 !important; letter-spacing: -0.01em; }}
[data-testid="stMarkdownContainer"] h3 {{ font-size: 1.15rem; margin-top: .6rem; }}
[data-testid="stMarkdownContainer"] h4 {{ font-size: 1rem; }}
[data-testid="stMarkdownContainer"] h5 {{ font-size: .92rem; font-weight: 600; }}

/* Base */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--bg) !important; color: var(--ink); }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1280px; }}
section[data-testid="stSidebar"] {{ background: var(--surface) !important; border-right: 1px solid var(--border); }}
section[data-testid="stSidebar"] * {{ color: var(--ink); }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li, [data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3, [data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5, [data-testid="stHeading"] *, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label, .stRadio label p, .stCheckbox label p, [data-testid="stToggle"] p {{ color: var(--ink); }}
[data-testid="stWidgetLabel"] p {{ font-weight: 500; font-size: .875rem; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; }}
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
  background: var(--surface) !important; border: 1px solid var(--border-fuerte) !important; border-radius: var(--radio-chico) !important;
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
[role="listbox"], [role="listbox"] [role="option"] {{ background: var(--surface) !important; color: var(--ink) !important; }}
[role="listbox"] [role="option"]:hover, [role="listbox"] [aria-selected="true"] {{ background: var(--surface-2) !important; }}
[data-baseweb="tag"] {{ background: var(--surface-2) !important; border-radius: 4px !important; }}
[data-baseweb="tag"] span {{ color: var(--ink) !important; }}
[data-testid="stCheckbox"] label > div:first-child {{ background-color: var(--surface); border-color: var(--border-fuerte); }}

/* Botones: sólidos, sin degradés ni elevación */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, [data-testid="stPopoverButton"] {{
  border-radius: var(--radio-chico) !important; font-weight: 500 !important; min-height: 2.4rem;
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
  background: var(--surface) !important; color: var(--ink) !important; border: 1px solid var(--border-fuerte) !important;
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
.stTabs [role="tab"] p {{ color: var(--muted); font-weight: 500; font-size: .92rem; }}
.stTabs [role="tab"]:hover p {{ color: var(--ink); }}
.stTabs [role="tab"][aria-selected="true"] {{ border-bottom-color: var(--primary) !important; }}
.stTabs [role="tab"][aria-selected="true"] p {{ color: var(--ink) !important; font-weight: 600 !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs [data-testid="stTabScrollButton"] {{ display: none !important; }}

/* ---------- Componentes SIA ---------- */
.sia-logo {{ display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radio-chico);
  object-fit: contain; background: #fff; border: 1px solid var(--border); flex: 0 0 auto; }}
.sia-logo-iniciales {{ font-weight: 700; font-size: .8rem; letter-spacing: .02em; border: none; }}

.sia-encabezado {{ display: flex; align-items: center; gap: .9rem; padding: .2rem 0 1rem; margin-bottom: 1.1rem;
  border-bottom: 1px solid var(--border); }}
.sia-encabezado .textos {{ min-width: 0; }}
.sia-encabezado .institucion {{ color: var(--muted); font-size: .8rem; font-weight: 500; }}
.sia-encabezado h1 {{ font-size: 1.45rem !important; margin: .05rem 0 0 0 !important; padding: 0 !important; color: var(--ink) !important; line-height: 1.25; }}
.sia-encabezado p {{ margin: .15rem 0 0 0; color: var(--muted); font-size: .9rem; }}
.sia-encabezado a, .sia-encabezado [data-testid="stHeaderActionElements"] {{ display: none !important; }}

.sia-marca {{ display: flex; align-items: center; gap: .65rem; padding-bottom: .9rem; margin-bottom: .9rem;
  border-bottom: 1px solid var(--border); }}
.sia-marca b {{ display: block; font-size: .92rem; color: var(--ink); line-height: 1.25; }}
.sia-marca small {{ display: block; font-size: .75rem; color: var(--muted); }}

.sia-usuario {{ font-size: .88rem; line-height: 1.45; padding: .1rem 0 .4rem; }}
.sia-usuario b {{ display: block; color: var(--ink); }}
.sia-usuario span {{ color: var(--muted); }}

/* Login: panel institucional + formulario */
.sia-login-marca {{ background: var(--primary); color: var(--primary-ink); border-radius: var(--radio); padding: 2rem 1.8rem;
  min-height: 100%; display: flex; flex-direction: column; gap: 1.2rem; }}
.sia-login-marca .sia-logo {{ background: #fff; border: none; }}
.sia-login-marca h2 {{ color: var(--primary-ink) !important; font-size: 1.4rem !important; margin: 0 !important; padding: 0 !important; line-height: 1.3; }}
.sia-login-marca p, .sia-login-marca li {{ color: var(--primary-ink) !important; opacity: .92; font-size: .92rem; margin: 0; }}
.sia-login-marca ul {{ margin: 0; padding-left: 1.1rem; display: grid; gap: .35rem; }}
.sia-login-marca .pie {{ margin-top: auto; font-size: .78rem; opacity: .8; }}
.sia-login-marca a, .sia-login-marca [data-testid="stHeaderActionElements"] {{ display: none !important; }}

.sia-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radio); padding: 1rem 1.1rem;
  margin-bottom: .75rem; color: var(--ink); overflow-wrap: anywhere; box-shadow: var(--sombra); }}
.sia-card .muted, .sia-muted {{ color: var(--muted); font-size: .86rem; }}
.sia-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: .75rem; margin-bottom: 1rem; }}
.sia-grid .sia-card {{ margin-bottom: 0; }}
.sia-kpi {{ border-left: 3px solid var(--tono, var(--border)); }}
.sia-kpi .label {{ font-size: .75rem; font-weight: 500; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }}
.sia-kpi .value {{ font-size: 1.65rem; font-weight: 600; color: var(--ink); line-height: 1.2; margin-top: .25rem;
  font-variant-numeric: tabular-nums; }}
.sia-kpi .sub {{ font-size: .8rem; color: var(--muted); margin-top: .15rem; }}

.sia-chips {{ display: flex; flex-wrap: wrap; gap: .35rem; margin: .3rem 0 .6rem; }}
.sia-chip {{ display: inline-flex; align-items: center; padding: .15rem .55rem; border-radius: 4px; background: var(--surface-2);
  color: var(--ink-2); font-size: .78rem; font-weight: 500; border: 1px solid var(--border); }}
.sia-badge {{ display: inline-block; padding: .1rem .5rem; border-radius: 4px; font-size: .74rem; font-weight: 600;
  color: var(--primary) !important; background: var(--primary-soft); border: 1px solid color-mix(in srgb, var(--primary) 30%, transparent); }}
.sia-code {{ font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace !important; font-size: 1.2rem; font-weight: 600;
  letter-spacing: .1em; color: var(--ink); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radio-chico);
  padding: .3rem .7rem; display: inline-block; max-width: 100%; overflow-wrap: anywhere; }}
.sia-pin {{ font-size: 2.2rem; letter-spacing: .25em; }}

.sia-alerta, .sia-riesgo {{ border-radius: var(--radio); padding: .75rem .95rem; margin-bottom: .6rem; background: var(--surface);
  border: 1px solid var(--border); border-left: 3px solid var(--tono, var(--critico)); color: var(--ink); overflow-wrap: anywhere; }}
.sia-alerta b, .sia-riesgo b {{ color: var(--ink); font-weight: 600; }}
.sia-alerta span {{ color: var(--ink-2); font-size: .87rem; }}
.sia-riesgo .etiqueta {{ display: inline-block; font-size: .72rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--tono, var(--critico)); margin-bottom: .15rem; }}
.sia-riesgo ul {{ margin: .3rem 0 0 1rem; padding: 0; }}
.sia-riesgo li {{ margin: .1rem 0; color: var(--ink-2); font-size: .87rem; }}
.sia-aviso, .sia-aviso-camara {{ background: var(--surface-2); color: var(--ink-2); border: 1px solid var(--border);
  border-radius: var(--radio-chico); padding: .65rem .85rem; margin: .3rem 0 .7rem; font-size: .87rem; line-height: 1.5; }}
.sia-aviso b {{ color: var(--ink); }}
.sia-barra {{ height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; margin-top: .5rem; }}
.sia-barra > div {{ height: 100%; background: var(--tono); }}

/* Tablas responsivas (sin scroll horizontal) */
.sia-tabla {{ width: 100%; max-width: 100%; margin: .3rem 0 1rem; }}
.sia-tabla table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radio); overflow: hidden; font-size: .86rem; }}
.sia-tabla th {{ background: var(--surface-2); color: var(--muted); text-align: left; font-weight: 600; padding: .5rem .65rem;
  font-size: .74rem; text-transform: uppercase; letter-spacing: .04em; border-bottom: 1px solid var(--border); }}
.sia-tabla td {{ padding: .5rem .65rem; color: var(--ink); border-bottom: 1px solid var(--border); overflow-wrap: anywhere; vertical-align: top;
  font-variant-numeric: tabular-nums; }}
.sia-tabla tr:last-child td {{ border-bottom: none; }}
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
  .sia-tabla td::before {{ content: attr(data-label); flex: 0 0 38%; color: var(--muted); font-size: .72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: .03em; }}
}}

/* Historial: una marca por clase (letra + color, nunca color solo) */
.sia-hist {{ display: grid; gap: .5rem; margin: .4rem 0 1rem; }}
.sia-hist-fila {{ display: grid; grid-template-columns: minmax(150px, 220px) 1fr; gap: .4rem .9rem; align-items: center;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radio); padding: .55rem .75rem; }}
.sia-hist-nombre b {{ color: var(--ink); font-size: .9rem; font-weight: 600; overflow-wrap: anywhere; }}
.sia-hist-nombre small {{ display: block; color: var(--muted); font-size: .76rem; }}
.sia-hist-marcas {{ display: flex; flex-wrap: wrap; gap: .25rem; min-width: 0; }}
.sia-marca {{ display: inline-flex; flex-direction: column; align-items: center; min-width: 2.4rem; padding: .1rem .2rem .15rem;
  border-radius: 4px; font-size: .78rem; font-weight: 700; line-height: 1.15; border: 1px solid transparent; }}
.sia-marca small {{ font-size: .6rem; font-weight: 500; color: var(--muted); }}
.sia-marca.presente {{ background: color-mix(in srgb, var(--bueno) 12%, var(--surface)); color: var(--bueno); }}
.sia-marca.tarde {{ background: color-mix(in srgb, #fab219 18%, var(--surface)); color: var(--advertencia); }}
.sia-marca.justificado {{ background: color-mix(in srgb, #2a78d6 12%, var(--surface)); color: #2a78d6; }}
.sia-marca.ausente {{ background: color-mix(in srgb, var(--critico) 12%, var(--surface)); color: var(--critico); }}
.sia-leyenda {{ display: flex; flex-wrap: wrap; gap: .8rem; font-size: .8rem; color: var(--muted); margin: .2rem 0 .4rem; }}
.sia-leyenda .sia-marca {{ min-width: 1.6rem; display: inline-flex; flex-direction: row; margin-right: .25rem; }}
@media (max-width: 640px) {{ .sia-hist-fila {{ grid-template-columns: 1fr; }} }}

.sia-pie {{ margin-top: 2.5rem; padding-top: .9rem; border-top: 1px solid var(--border); display: flex; align-items: center;
  justify-content: center; gap: .5rem; flex-wrap: wrap; color: var(--muted); font-size: .8rem; }}
.sia-pie img {{ width: 28px; height: 28px; object-fit: contain; background: #fff; border-radius: 4px; border: 1px solid var(--border); }}

@media (max-width: 768px) {{
  .block-container {{ padding: .9rem .8rem 3rem !important; }}
  .sia-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .55rem; }}
  .sia-kpi .value {{ font-size: 1.3rem; }}
  .sia-encabezado h1 {{ font-size: 1.2rem !important; }}
  .sia-pin {{ font-size: 1.7rem; letter-spacing: .16em; }}
  .stTabs [role="tablist"] {{ gap: .2rem 1rem; }}
  [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: .7rem !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{ width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }}
  .sia-login-marca {{ padding: 1.4rem 1.2rem; }}
}}
@media (max-width: 340px) {{ .sia-grid {{ grid-template-columns: 1fr; }} }}
</style>
"""

# Modo oscuro: tablas nativas (canvas) se oscurecen con un filtro; el resto usa las variables.
_CSS_OSCURO = """
<style>
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { filter: invert(0.9) hue-rotate(180deg); }
[data-testid="stAlertContainer"] { background: var(--surface-2) !important; border: 1px solid var(--border) !important; }
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
    css = _CSS.format(variables=_variables()) + f"<style>{CSS_OCULTAR_CLOUD}</style>"
    st.markdown(css + (_CSS_OSCURO if modo_oscuro() else ""), unsafe_allow_html=True)


def selector_tema() -> None:
    st.toggle("Modo oscuro", key=CLAVE_TEMA)


# ---------------------------------------------------------------- componentes
def _html(texto: str) -> str:
    """Escapa y evita que "N° 11" se parta en dos líneas."""
    return escape(texto).replace("N° ", "N°&nbsp;").replace("Nº ", "Nº&nbsp;")


def encabezado(titulo: str, subtitulo: str = "") -> None:
    t = tema()
    st.markdown(
        f'<div class="sia-encabezado">{logo_html(44)}<div class="textos"><div class="institucion">{_html(t["nombre"])}</div>'
        f'<h1>{_html(titulo)}</h1>{f"<p>{_html(subtitulo)}</p>" if subtitulo else ""}</div></div>',
        unsafe_allow_html=True,
    )


hero = encabezado  # compatibilidad


def marca_sidebar() -> None:
    t = tema()
    st.markdown(f'<div class="sia-marca">{logo_html(36)}<div><b>{_html(t["corto"])}</b>'
                f'<small>{PRODUCTO} · {PRODUCTO_LARGO}</small></div></div>', unsafe_allow_html=True)


def panel_login(lineas: list[str]) -> None:
    t = tema()
    items = "".join(f"<li>{escape(x)}</li>" for x in lineas)
    st.markdown(
        f'<div class="sia-login-marca">{logo_html(56)}<div><h2>{_html(t["nombre"])}</h2>'
        f'<p>{PRODUCTO} · {PRODUCTO_LARGO}</p></div><ul>{items}</ul>'
        f'<div class="pie">Desarrollado por {EQUIPO}</div></div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    logo = _logo_tech()
    img = f'<img src="{logo}" alt="Logo {EQUIPO}">' if logo else ""
    st.markdown(f'<div class="sia-pie">{img}<span>{PRODUCTO} · Desarrollado por {EQUIPO}</span></div>',
                unsafe_allow_html=True)


def aviso(html_seguro: str) -> None:
    st.markdown(f'<div class="sia-aviso">{html_seguro}</div>', unsafe_allow_html=True)


def _kpi_html(label: str, valor, sub: str = "", tono: str = "neutro") -> str:
    estilo = f' style="--tono:{TONOS[tono]}"' if tono in ("rojo", "ambar", "verde") else ""
    return (f'<div class="sia-card sia-kpi"{estilo}><div class="label">{escape(label)}</div>'
            f'<div class="value">{escape(str(valor))}</div><div class="sub">{escape(sub)}</div></div>')


def kpi(label: str, valor, sub: str = "", tono: str = "neutro") -> None:
    st.markdown(_kpi_html(label, valor, sub, tono), unsafe_allow_html=True)


def kpi_grid(items: list[tuple]) -> None:
    st.markdown(f'<div class="sia-grid">{"".join(_kpi_html(*i) for i in items)}</div>', unsafe_allow_html=True)


def tarjeta_progreso(titulo: str, valor: str, detalle: str, pct: float, tono: str) -> str:
    color = TONOS.get(tono, tono)
    return (f'<div class="sia-card sia-kpi" style="--tono:{color}"><div class="label">{escape(titulo)}</div>'
            f'<div class="value">{escape(valor)}</div><div class="sub">{escape(detalle)}</div>'
            f'<div class="sia-barra"><div style="width:{max(0, min(100, pct)):.0f}%"></div></div></div>')


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
    tinta, secundaria, apagada = ("#f0efec", "#c3c2b7", "#898781") if oscuro else ("#0b0b0b", "#52514e", "#898781")
    grilla, base = ("#2c2c2a", "#383835") if oscuro else ("#e1e0d9", "#c3c2b7")
    if titulo is not None:
        fig.update_layout(title_text=titulo)
    fig.update_layout(
        template="plotly_dark" if oscuro else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=alto,
        margin=dict(l=8, r=12, t=56 if fig.layout.title.text else 16, b=8),
        font=dict(family="Inter, system-ui, -apple-system, 'Segoe UI', sans-serif", size=12, color=secundaria),
        title=dict(x=0, xanchor="left", y=0.97, yanchor="top", yref="container", font=dict(size=14, color=tinta)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text="",
                    font=dict(size=12, color=secundaria), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#1a1a19" if oscuro else "#ffffff", bordercolor=grilla,
                        font=dict(color=tinta, size=12, family="Inter, system-ui, sans-serif")),
        colorway=series(), bargap=0.35, hovermode="closest",
    )
    ejes = dict(gridcolor=grilla, gridwidth=1, zeroline=False, linecolor=base, showline=True, ticks="",
                tickfont=dict(color=apagada, size=11), title_font=dict(color=secundaria, size=12))
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    fig.update_traces(selector=dict(type="bar"), marker_line_width=0)
    try:
        fig.update_traces(selector=dict(type="bar"), marker_cornerradius=4)
    except (ValueError, TypeError):
        pass
    fig.update_traces(selector=dict(type="scatter"), line_width=2, marker_size=8)
    fig.update_annotations(font_color=secundaria, font_size=11)
    return fig


def linea_referencia(fig, valor: float, texto: str, eje: str = "y") -> None:
    """Umbral como línea fina continua (no punteada) con su etiqueta."""
    color = "#898781"
    if eje == "y":
        fig.add_hline(y=valor, line_width=1, line_color=color, annotation_text=texto, annotation_position="top left")
    else:
        fig.add_vline(x=valor, line_width=1, line_color=color, annotation_text=texto, annotation_position="top right")
