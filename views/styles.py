"""Identidad visual del IES N° 11: paleta, tipografía, tema claro/oscuro, logos y componentes."""
from __future__ import annotations

import base64
import io
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
_EXTENSIONES = ("png", "webp", "jpg", "jpeg", "svg")
# Se usa el primero que exista (logo_ise.* se mantiene por compatibilidad con versiones anteriores).
_NOMBRES_LOGO_IES = tuple(f"{b}.{e}" for b in ("logo_ies", "logo_ies11", "logo_ise") for e in _EXTENSIONES)
_NOMBRES_LOGO_TECH = tuple(f"logo_tech.{e}" for e in _EXTENSIONES)
_MIME = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
CLAVE_TEMA = "modo_oscuro"

# Denominación oficial de la institución (usar siempre estas constantes)
INSTITUCION = "Instituto de Educación Superior N° 11"
INSTITUCION_CORTA = "IES N° 11"
TITULO_APP = f"SIA · {INSTITUCION_CORTA}"
EQUIPO = "Tech Innovation Team"

# Paleta institucional
LILA = "#B78FB6"      # acentos y destacados
LAVANDA = "#7979B1"   # elementos secundarios / hover
AZUL = "#346FB0"      # botones primarios y bordes
AZUL_OSCURO = "#02447B"  # tarjetas en modo oscuro
AZUL_NOCHE = "#003467"   # fondo principal en modo oscuro

TONOS = {
    "azul": AZUL,
    "lavanda": LAVANDA,
    "lila": LILA,
    "noche": AZUL_OSCURO,
    "verde": "#2E9E77",
    "ambar": "#D99A2B",
    "rojo": "#D9534F",
    "gris": "#6B7894",
    # alias usados en vistas anteriores
    "celeste": LAVANDA,
    "indigo": AZUL,
    "cian": LAVANDA,
}
COLORES_NIVEL = {"ALTO": "#D9534F", "MEDIO": "#D99A2B", "BAJO": "#2E9E77"}
EMOJI_NIVEL = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}
FUENTE = "'Plus Jakarta Sans', 'Inter', 'Nunito', system-ui, sans-serif"

_VARIABLES = {
    "claro": f"""
  --sia-bg: #F6F7FC;
  --sia-bg-grad: radial-gradient(1100px 480px at 0% -10%, rgba(183,143,182,.20) 0%, transparent 60%),
                 radial-gradient(900px 420px at 100% 0%, rgba(52,111,176,.12) 0%, transparent 60%);
  --sia-surface: #FFFFFF;
  --sia-surface-2: #EEF0FA;
  --sia-input: #FFFFFF;
  --sia-ink: #0E2747;
  --sia-muted: #56658A;
  --sia-border: rgba(121, 121, 177, 0.45);
  --sia-border-strong: {AZUL};
  --sia-primary: {AZUL};
  --sia-primary-2: {LAVANDA};
  --sia-accent: {LILA};
  --sia-primary-ink: #FFFFFF;
  --sia-accent-soft: #F3ECF4;
  --sia-tab-activa: linear-gradient(135deg, {AZUL} 0%, {LAVANDA} 100%);
  --sia-shadow: 0 1px 3px rgba(2,68,123,.08), 0 10px 26px rgba(52,111,176,.10);
  --sia-shadow-hover: 0 6px 14px rgba(52,111,176,.20), 0 16px 34px rgba(121,121,177,.18);
""",
    "oscuro": f"""
  --sia-bg: {AZUL_NOCHE};
  --sia-bg-grad: radial-gradient(1100px 480px at 0% -10%, rgba(183,143,182,.22) 0%, transparent 60%),
                 radial-gradient(900px 420px at 100% 0%, rgba(121,121,177,.20) 0%, transparent 60%);
  --sia-surface: {AZUL_OSCURO};
  --sia-surface-2: #0B4F8C;
  --sia-input: #002B57;
  --sia-ink: #F4F7FC;
  --sia-muted: #C9D4EA;
  --sia-border: rgba(121, 121, 177, 0.70);
  --sia-border-strong: {LAVANDA};
  --sia-primary: {AZUL};
  --sia-primary-2: {LAVANDA};
  --sia-accent: {LILA};
  --sia-primary-ink: #FFFFFF;
  --sia-accent-soft: rgba(183, 143, 182, 0.22);
  --sia-tab-activa: linear-gradient(135deg, {LILA} 0%, {LAVANDA} 100%);
  --sia-shadow: 0 1px 3px rgba(0,0,0,.35), 0 10px 26px rgba(0,20,45,.45);
  --sia-shadow-hover: 0 6px 16px rgba(183,143,182,.28), 0 16px 34px rgba(0,20,45,.55);
""",
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Nunito:wght@400;600;700;800&display=swap');
:root, .stApp {{ {variables} }}

/* ---------- Tipografía (sin tocar los íconos Material de Streamlit) ---------- */
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp td, .stApp th, .stApp small,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"], [role="tab"], [role="option"] {{
  font-family: {fuente} !important;
}}
h1, h2, h3, h4 {{ letter-spacing: -0.015em; font-weight: 800 !important; }}

/* ---------- Base ---------- */
.stApp, [data-testid="stAppViewContainer"] {{
  background: var(--sia-bg-grad), var(--sia-bg) !important; color: var(--sia-ink);
}}
/* ---------- Encabezado nativo oculto (menú ⋮, Share, GitHub, Deploy) ----------
   Se usa `visibility` y no `display: none` porque el botón que abre la barra lateral en celulares
   (stExpandSidebarButton) vive dentro de este encabezado: con display:none quedaría inaccesible y no se
   podría cerrar sesión ni cambiar el tema desde el teléfono. visibility:hidden oculta y desactiva todo,
   y el botón de la barra lateral se vuelve a mostrar explícitamente. */
header[data-testid="stHeader"] {{ visibility: hidden !important; background: transparent !important; box-shadow: none !important; }}
[data-testid="stToolbarActions"], [data-testid="stMainMenu"], #MainMenu, [data-testid="stAppDeployButton"],
.stDeployButton, [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display: none !important; }}
#MainMenu {{ visibility: hidden !important; }}
footer {{ visibility: hidden !important; }}
[data-testid="stExpandSidebarButton"] {{
  visibility: visible !important; color: #FFFFFF !important; border-radius: 14px !important;
  background: linear-gradient(135deg, var(--sia-primary), var(--sia-primary-2)) !important;
  box-shadow: var(--sia-shadow) !important;
}}
[data-testid="stExpandSidebarButton"] * {{ color: #FFFFFF !important; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1400px; }}
section[data-testid="stSidebar"] {{ background: var(--sia-surface) !important; border-right: 1px solid var(--sia-border); }}
section[data-testid="stSidebar"] * {{ color: var(--sia-ink); }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3, [data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5, [data-testid="stHeading"] *, [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label, .stRadio label p, .stCheckbox label p, [data-testid="stToggle"] p {{
  color: var(--sia-ink);
}}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--sia-muted) !important; }}
[data-testid="stMarkdownContainer"] a {{ color: var(--sia-primary); }}

/* ---------- Inputs ---------- */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputContainer"], [data-testid="stDateInputField"],
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
div:has(> input[role="combobox"]),
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{
  background: var(--sia-input) !important; border: 1px solid var(--sia-border) !important; border-radius: 12px !important;
}}
[data-testid="stTextInputRootElement"] input, [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stNumberInputContainer"] input, input[role="combobox"],
[data-testid="stSelectbox"] [role="group"] div, [data-testid="stMultiSelect"] [role="group"] div,
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="select"] div {{
  color: var(--sia-ink) !important; -webkit-text-fill-color: var(--sia-ink) !important; background-color: transparent !important;
  border: none !important;
}}
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg {{ fill: var(--sia-muted); color: var(--sia-muted); }}
[role="listbox"], [role="listbox"] [role="option"] {{ background: var(--sia-surface) !important; color: var(--sia-ink) !important; }}
[role="listbox"] [role="option"]:hover, [role="listbox"] [aria-selected="true"] {{ background: var(--sia-surface-2) !important; }}
[data-testid="stCheckbox"] label > div:first-child {{ background-color: var(--sia-input); border-color: var(--sia-border); }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stSelectbox"] [role="group"]:focus-within, [data-baseweb="input"]:focus-within {{
  border-color: var(--sia-border-strong) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--sia-accent) 35%, transparent) !important;
}}
input::placeholder, textarea::placeholder {{ color: var(--sia-muted) !important; -webkit-text-fill-color: var(--sia-muted) !important; opacity: .8; }}
[data-baseweb="tag"] {{ background: var(--sia-accent-soft) !important; border-radius: 10px !important; }}
[data-baseweb="tag"] span {{ color: var(--sia-ink) !important; }}

/* ---------- Botones ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, [data-testid="stPopoverButton"] {{
  border-radius: 14px !important; font-weight: 700 !important; padding: .55rem 1.15rem !important;
  box-shadow: var(--sia-shadow); transition: transform .15s ease, box-shadow .15s ease !important;
}}
button[kind^="primary"], button[data-testid^="stBaseButton-primary"] {{
  background: linear-gradient(135deg, var(--sia-primary) 0%, var(--sia-primary-2) 100%) !important;
  color: var(--sia-primary-ink) !important; border: none !important;
}}
button[kind^="primary"] p, button[data-testid^="stBaseButton-primary"] p {{ color: var(--sia-primary-ink) !important; }}
button[kind^="secondary"], button[data-testid^="stBaseButton-secondary"], [data-testid="stPopoverButton"] {{
  background: var(--sia-surface) !important; color: var(--sia-primary) !important;
  border: 1.5px solid var(--sia-border-strong) !important;
}}
button[kind^="secondary"] p, button[data-testid^="stBaseButton-secondary"] p, [data-testid="stPopoverButton"] p {{
  color: var(--sia-primary) !important;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover,
[data-testid="stPopoverButton"]:hover {{ transform: translateY(-2px); box-shadow: var(--sia-shadow-hover) !important; }}
button[kind^="primary"]:hover, button[data-testid^="stBaseButton-primary"]:hover {{
  background: linear-gradient(135deg, var(--sia-primary-2) 0%, var(--sia-accent) 100%) !important;
}}
button[kind^="secondary"]:hover, button[data-testid^="stBaseButton-secondary"]:hover, [data-testid="stPopoverButton"]:hover {{
  background: var(--sia-accent-soft) !important; border-color: var(--sia-primary-2) !important;
}}
button[data-testid="stBaseButton-elementToolbar"] {{ box-shadow: none !important; border: none !important; background: transparent !important; }}
.stButton > button:active, .stFormSubmitButton > button:active {{ transform: translateY(0); }}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {{ opacity: .55; transform: none; box-shadow: none !important; }}

/* ---------- Contenedores como tarjetas ---------- */
[data-testid="stForm"], [data-testid="stExpander"] details, div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stCameraInput"], [data-testid="stPopoverBody"], [data-testid="stMetric"] {{
  background: var(--sia-surface) !important; border: 1px solid var(--sia-border) !important;
  border-radius: 18px !important; box-shadow: var(--sia-shadow);
}}
[data-testid="stForm"] {{ padding: 1.2rem 1.3rem !important; }}
[data-testid="stMetric"] {{ padding: .85rem 1rem; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {{ color: var(--sia-ink) !important; }}
[data-testid="stMetricLabel"] p {{ color: var(--sia-muted) !important; }}
[data-testid="stExpander"] summary {{ background: var(--sia-surface) !important; border-radius: 18px; }}
[data-testid="stExpander"] details[open] > summary {{ border-radius: 18px 18px 0 0; }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span {{
  color: var(--sia-ink) !important;
}}
[data-testid="stExpander"] summary:hover {{ background: var(--sia-surface-2) !important; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--sia-primary-2) !important; }}
[data-testid="stAlert"], [data-testid="stAlertContainer"] {{ border-radius: 14px !important; }}
[data-testid="stCode"] pre, [data-testid="stCode"] code, .stCodeBlock pre {{
  background: var(--sia-surface-2) !important; color: var(--sia-ink) !important; border-radius: 12px !important;
}}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
  border-radius: 14px; overflow: hidden; border: 1px solid var(--sia-border);
}}
[data-testid="stImage"] img {{ border-radius: 14px; }}
hr {{ border-color: var(--sia-border) !important; }}

/* ---------- Pestañas tipo píldora ---------- */
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"] {{
  gap: .5rem; overflow-x: auto; scrollbar-width: thin; padding: .35rem; border-radius: 25px;
  background: var(--sia-surface); border: 1px solid var(--sia-border); box-shadow: var(--sia-shadow);
}}
.stTabs [role="tab"], .stTabs [data-baseweb="tab"] {{
  border-radius: 25px !important; padding: .5rem 1.1rem !important; white-space: nowrap; height: auto !important;
  background: transparent; border: 1px solid transparent !important; transition: background .15s ease, border-color .15s ease;
}}
.stTabs [role="tab"] p {{ color: var(--sia-ink); font-weight: 600; }}
.stTabs [role="tab"]:hover {{ background: var(--sia-accent-soft); border-color: var(--sia-border) !important; }}
.stTabs [role="tab"][aria-selected="true"] {{
  background: var(--sia-tab-activa) !important; box-shadow: 0 4px 14px color-mix(in srgb, var(--sia-primary) 35%, transparent);
}}
.stTabs [role="tab"][aria-selected="true"] p {{ color: #FFFFFF !important; font-weight: 800 !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

/* ---------- Componentes SIA ---------- */
.sia-hero {{
  display: flex; align-items: center; gap: 1.2rem;
  background: linear-gradient(120deg, {noche} 0%, {oscuro} 38%, {azul} 72%, {lavanda} 100%);
  color: #fff; border-radius: 22px; padding: 1.3rem 1.6rem; margin-bottom: 1.2rem;
  box-shadow: 0 14px 32px rgba(2,68,123,.30); border-bottom: 4px solid {lila};
}}
.sia-hero h1 {{ color: #fff !important; font-size: 1.65rem; margin: 0 0 .15rem 0; padding: 0; line-height: 1.2; }}
.sia-hero p {{ margin: 0; opacity: .95; color: #fff !important; }}
.sia-hero .sia-logo {{ flex: 0 0 auto; }}
.sia-hero a, .sia-hero [data-testid="stHeaderActionElements"] {{ display: none !important; }}
.sia-logo img {{
  display: block; width: 72px; height: 72px; object-fit: cover; border-radius: 50%;
  box-shadow: 0 0 0 3px rgba(255,255,255,.85), 0 6px 16px rgba(0,0,0,.25);
}}
.sia-logo-placeholder {{
  width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  background: #fff; color: {azul} !important; font-weight: 900; font-size: 1.25rem; letter-spacing: .04em;
  box-shadow: inset 0 0 0 4px {lavanda};
}}
.sia-brand {{ display: flex; align-items: center; gap: .75rem; margin-bottom: .6rem; }}
.sia-brand .sia-logo img, .sia-brand .sia-logo-placeholder {{ width: 52px; height: 52px; font-size: 1rem; }}
.sia-brand .sia-logo img {{ box-shadow: 0 0 0 2px var(--sia-border-strong); }}
.sia-brand b {{ font-size: 1.05rem; color: var(--sia-ink); }}
.sia-brand small {{ display: block; color: var(--sia-muted); font-size: .78rem; line-height: 1.25; }}

.sia-card {{
  background: var(--sia-surface); border: 1px solid var(--sia-border); border-radius: 18px;
  padding: 1.1rem 1.25rem; box-shadow: var(--sia-shadow); margin-bottom: .8rem; color: var(--sia-ink);
  overflow-wrap: anywhere; transition: box-shadow .2s ease, transform .2s ease;
}}
.sia-card:hover {{ box-shadow: var(--sia-shadow-hover); }}
.sia-card .muted, .sia-muted {{ color: var(--sia-muted); font-size: .88rem; }}
.sia-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .9rem; margin-bottom: 1rem; }}
.sia-grid .sia-card {{ margin-bottom: 0; }}
.sia-kpi {{ border-left: 6px solid var(--tono); }}
.sia-kpi .label {{ font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--sia-muted); }}
.sia-kpi .value {{ font-size: 2rem; font-weight: 800; color: var(--sia-ink); line-height: 1.15; margin-top: .2rem; }}
.sia-kpi .sub {{ font-size: .82rem; color: var(--sia-muted); margin-top: .15rem; }}

.sia-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .35rem 0 .6rem; }}
.sia-chip {{
  display: inline-flex; align-items: center; gap: .3rem; padding: .28rem .75rem; border-radius: 999px;
  background: var(--sia-accent-soft); color: var(--sia-ink); font-size: .82rem; font-weight: 600;
  border: 1px solid var(--sia-border);
}}
.sia-code {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace !important; font-size: 1.5rem; font-weight: 800;
  letter-spacing: .12em; color: var(--sia-primary); background: var(--sia-accent-soft); border-radius: 14px;
  padding: .4rem .9rem; display: inline-block; max-width: 100%; overflow-wrap: anywhere;
  border: 1px dashed var(--sia-border-strong);
}}
.sia-pin {{ font-size: 2.8rem; letter-spacing: .28em; }}
.sia-badge {{
  display: inline-block; padding: .2rem .7rem; border-radius: 999px; font-size: .78rem;
  font-weight: 700; color: #fff !important; background: var(--tono);
}}
.sia-alerta {{
  border-radius: 16px; padding: .8rem 1rem; margin-bottom: .55rem; border: 1px solid var(--sia-border);
  border-left: 6px solid var(--tono); background: var(--sia-surface); box-shadow: var(--sia-shadow);
  overflow-wrap: anywhere;
}}
.sia-alerta b {{ color: var(--sia-ink); }}
.sia-alerta span {{ color: var(--sia-muted); font-size: .88rem; }}
.sia-barra {{ height: 8px; border-radius: 999px; background: var(--sia-surface-2); overflow: hidden; margin-top: .55rem; }}
.sia-barra > div {{ height: 100%; border-radius: 999px; background: var(--tono); }}
.sia-aviso, .sia-aviso-camara {{
  background: var(--sia-accent-soft); color: var(--sia-ink); border: 1px solid var(--sia-border);
  border-left: 6px solid var(--sia-accent); border-radius: 14px; padding: .8rem 1rem; margin: .4rem 0 .8rem;
  font-size: .92rem; line-height: 1.5; overflow-wrap: anywhere;
}}
.sia-aviso b {{ color: var(--sia-ink); }}
[data-testid="stCameraInput"] {{ overflow: hidden; max-width: 100%; }}
[data-testid="stCameraInput"] video, [data-testid="stCameraInput"] img {{ max-width: 100%; height: auto; border-radius: 14px; }}

.sia-footer {{
  margin-top: 2.5rem; padding: 1rem; display: flex; align-items: center; justify-content: center; gap: .6rem;
  flex-wrap: wrap; text-align: center; color: var(--sia-muted); font-size: .86rem; border-top: 1px solid var(--sia-border);
}}
.sia-footer b {{ color: var(--sia-primary-2); }}
.sia-footer img {{
  width: 46px; height: 46px; object-fit: contain; background: #FFFFFF; border-radius: 12px; padding: 3px;
  box-shadow: var(--sia-shadow); border: 1px solid var(--sia-border); flex: 0 0 auto;
}}
.sia-tech-placeholder {{ width: 34px; height: 34px; border-radius: 50%; flex: 0 0 auto; }}
.sia-tech-placeholder {{
  display: inline-flex; align-items: center; justify-content: center; font-size: .7rem; font-weight: 800; color: #fff;
  background: linear-gradient(135deg, {azul}, {lila});
}}

/* ---------- Responsive ---------- */
@media (max-width: 900px) {{
  .sia-kpi .value {{ font-size: 1.6rem; }}
}}
@media (max-width: 768px) {{
  .block-container {{ padding: .9rem .8rem 3rem !important; }}
  .sia-hero {{ flex-direction: column; text-align: center; padding: 1.1rem 1rem; gap: .7rem; border-radius: 18px; }}
  .sia-hero h1 {{ font-size: 1.3rem; }}
  .sia-hero p {{ font-size: .9rem; }}
  .sia-logo img, .sia-logo-placeholder {{ width: 60px; height: 60px; }}
  .sia-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; }}
  .sia-card {{ padding: .9rem 1rem; }}
  .sia-kpi .value {{ font-size: 1.35rem; }}
  .sia-kpi .label {{ font-size: .68rem; }}
  .sia-code {{ font-size: 1.1rem; letter-spacing: .08em; }}
  .sia-pin {{ font-size: 2rem; letter-spacing: .18em; }}
  [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: .75rem !important; }}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
    width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important;
  }}
  .stTabs [role="tab"] {{ padding: .42rem .8rem !important; }}
  .stTabs [role="tab"] p {{ font-size: .85rem; }}
  [data-testid="stForm"] {{ padding: .9rem !important; }}
}}
@media (max-width: 340px) {{
  .sia-grid {{ grid-template-columns: 1fr; }}
}}
</style>
"""

# Reglas que solo se inyectan en modo oscuro (contraste reforzado sobre #003467 / #02447B).
_CSS_OSCURO = f"""
<style>
section[data-testid="stSidebar"] {{ background: {AZUL_NOCHE} !important; border-right-color: rgba(121,121,177,.55); }}
section[data-testid="stSidebar"] .sia-card {{ background: {AZUL_OSCURO}; border-color: rgba(121,121,177,.7); }}
button[kind^="secondary"], button[data-testid^="stBaseButton-secondary"], [data-testid="stPopoverButton"] {{
  color: #FFFFFF !important; background: rgba(52, 111, 176, 0.30) !important; border: 1px solid {LAVANDA} !important;
}}
button[kind^="secondary"] p, button[data-testid^="stBaseButton-secondary"] p, [data-testid="stPopoverButton"] p,
button[kind^="secondary"] span, [data-testid="stPopoverButton"] span {{ color: #FFFFFF !important; }}
button[kind^="secondary"]:hover, button[data-testid^="stBaseButton-secondary"]:hover, [data-testid="stPopoverButton"]:hover {{
  background: rgba(183, 143, 182, 0.30) !important; border-color: {LILA} !important;
}}
button[data-testid="stBaseButton-elementToolbar"] {{ background: transparent !important; border: none !important; }}
.sia-badge {{ color: #FFFFFF !important; border: 1px solid {LILA}; }}
.sia-code {{ color: #FFFFFF; }}

/* Tablas (st.dataframe / st.data_editor): se dibujan en <canvas> con los colores del tema base y el CSS no
   puede repintar sus celdas. 1) Un filtro invierte la luminosidad conservando los tonos (✅ ❌ siguen en color).
   2) Una capa en modo "screen" con #003467 tiñe de azul los fondos oscuros sin apagar el texto claro. */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
  filter: invert(0.92) hue-rotate(180deg) saturate(1.1);
  border-color: rgba(183, 143, 182, 0.7) !important;
}}
[data-testid="stFullScreenFrame"]:has(> [data-testid="stDataFrame"]),
[data-testid="stFullScreenFrame"]:has(> [data-testid="stDataEditor"]) {{ position: relative; }}
[data-testid="stFullScreenFrame"]:has(> [data-testid="stDataFrame"])::after,
[data-testid="stFullScreenFrame"]:has(> [data-testid="stDataEditor"])::after {{
  content: ""; position: absolute; inset: 0; border-radius: 14px; pointer-events: none;
  background: {AZUL_NOCHE}; mix-blend-mode: screen;
}}
[data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td {{
  background: {AZUL_OSCURO} !important; color: #F4F7FC !important; border-color: rgba(121,121,177,.5) !important;
}}

/* Cámara */
[data-testid="stCameraInput"] {{ background: {AZUL_OSCURO} !important; }}
[data-testid="stCameraInput"] * {{ color: #F4F7FC; }}
[data-testid="stCameraInput"] button {{ color: #FFFFFF !important; background: rgba(52,111,176,.4) !important; border: 1px solid {LAVANDA} !important; }}

/* Alertas legibles sobre fondo oscuro */
[data-testid="stAlertContainer"] {{ background: {AZUL_OSCURO} !important; border: 1px solid rgba(121,121,177,.6) !important; }}
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] li {{ color: #F4F7FC !important; }}
[data-testid="stCode"] pre, [data-testid="stCode"] code {{ background: {AZUL_NOCHE} !important; color: #F4F7FC !important; }}
</style>
"""


# ---------------------------------------------------------------- tema
def modo_oscuro() -> bool:
    return bool(st.session_state.get(CLAVE_TEMA, False))


def inyectar_css() -> None:
    oscuro = modo_oscuro()
    css = _CSS.format(
        variables=_VARIABLES["oscuro" if oscuro else "claro"], fuente=FUENTE,
        azul=AZUL, lavanda=LAVANDA, lila=LILA, oscuro=AZUL_OSCURO, noche=AZUL_NOCHE,
    )
    st.markdown(css + (_CSS_OSCURO if oscuro else ""), unsafe_allow_html=True)


def selector_tema() -> None:
    st.toggle("🌙 Modo oscuro", key=CLAVE_TEMA, help="Alterna entre modo claro y oscuro.")


# ---------------------------------------------------------------- logos
def _buscar(nombres: tuple[str, ...]) -> Path | None:
    return next((ASSETS / n for n in nombres if (ASSETS / n).exists()), None)


def ruta_logo() -> Path | None:
    """Logo del IES N° 11 (assets/logo_ies.png, logo_ies11.png o logo_ise.png)."""
    return _buscar(_NOMBRES_LOGO_IES)


def ruta_logo_tech() -> Path | None:
    return _buscar(_NOMBRES_LOGO_TECH)


@lru_cache(maxsize=8)
def _data_uri(ruta: str, lado: int, _mtime: float) -> str:
    """Imagen embebida y reducida (evita enviar el PNG original completo en cada recarga)."""
    archivo = Path(ruta)
    if archivo.suffix.lower() == ".svg":
        return f"data:image/svg+xml;base64,{base64.b64encode(archivo.read_bytes()).decode()}"
    from PIL import Image

    imagen = Image.open(archivo)
    imagen.thumbnail((lado, lado))
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG", optimize=True)
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def _img(ruta: Path | None, lado: int) -> str | None:
    return _data_uri(str(ruta), lado, ruta.stat().st_mtime) if ruta else None


def logo_html() -> str:
    uri = _img(ruta_logo(), 192)
    if uri:
        return f'<div class="sia-logo"><img src="{uri}" alt="Logo {INSTITUCION_CORTA}"></div>'
    return (f'<div class="sia-logo"><div class="sia-logo-placeholder" title="{INSTITUCION} — agregá '
            f'assets/logo_ies.png para mostrar el logo oficial">IES</div></div>')


def logo_tech_html() -> str:
    uri = _img(ruta_logo_tech(), 96)
    if uri:
        return f'<img src="{uri}" alt="Logo {EQUIPO}">'
    return f'<span class="sia-tech-placeholder" title="Agregá assets/logo_tech.png">TI</span>'


def marca_sidebar() -> None:
    st.markdown(
        f'<div class="sia-brand">{logo_html()}<div><b>{_html(TITULO_APP)}</b>'
        f"<small>Sistema de Asistencia Inteligente<br>{_html(INSTITUCION)}</small></div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- componentes
def _html(texto: str) -> str:
    """Escapa y evita que "N° 11" se parta en dos líneas."""
    return escape(texto).replace("N° ", "N°&nbsp;")


def hero(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f'<div class="sia-hero">{logo_html()}<div><h1>{_html(titulo)}</h1><p>{_html(subtitulo)}</p></div></div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        f'<div class="sia-footer">{logo_tech_html()}'
        f'<span>Desarrollado por <b>{EQUIPO}</b> — {_html(INSTITUCION_CORTA)}</span></div>',
        unsafe_allow_html=True,
    )


def aviso(html_seguro: str) -> None:
    """Caja destacada con acento lila (el contenido debe venir ya escapado)."""
    st.markdown(f'<div class="sia-aviso">{html_seguro}</div>', unsafe_allow_html=True)


def _kpi_html(label: str, valor, sub: str = "", tono: str = "azul") -> str:
    color = TONOS.get(tono, tono)
    return (
        f'<div class="sia-card sia-kpi" style="--tono:{color}">'
        f'<div class="label">{escape(label)}</div><div class="value">{escape(str(valor))}</div>'
        f'<div class="sub">{escape(sub)}</div></div>'
    )


def kpi(label: str, valor, sub: str = "", tono: str = "azul") -> None:
    st.markdown(_kpi_html(label, valor, sub, tono), unsafe_allow_html=True)


def kpi_grid(items: list[tuple]) -> None:
    """Fila de KPIs en grilla CSS: se reacomoda sola en celulares."""
    st.markdown(f'<div class="sia-grid">{"".join(_kpi_html(*i) for i in items)}</div>', unsafe_allow_html=True)


def tarjeta_progreso(titulo: str, valor: str, detalle: str, pct: float, tono: str) -> str:
    color = TONOS.get(tono, tono)
    return (
        f'<div class="sia-card sia-kpi" style="--tono:{color}"><div class="label">{escape(titulo)}</div>'
        f'<div class="value">{escape(valor)}</div><div class="sub">{escape(detalle)}</div>'
        f'<div class="sia-barra"><div style="width:{max(0, min(100, pct)):.0f}%"></div></div></div>'
    )


def chips(items: list[str]) -> str:
    return '<div class="sia-chips">' + "".join(f'<span class="sia-chip">{escape(i)}</span>' for i in items if i) + "</div>"


def badge(texto: str, tono: str = "azul") -> str:
    return f'<span class="sia-badge" style="--tono:{TONOS.get(tono, tono)}">{escape(texto)}</span>'


def alerta(titulo: str, detalle: str, color: str) -> None:
    st.markdown(
        f'<div class="sia-alerta" style="--tono:{color}"><b>{escape(titulo)}</b><br><span>{escape(detalle)}</span></div>',
        unsafe_allow_html=True,
    )


def codigo(texto: str, grande: bool = False) -> None:
    clase = "sia-code sia-pin" if grande else "sia-code"
    st.markdown(f'<div class="{clase}">{escape(texto)}</div>', unsafe_allow_html=True)


def aviso_camara(texto: str) -> None:
    """Ayuda en español sobre el permiso de cámara (el componente de Streamlit muestra textos en inglés)."""
    st.markdown(f'<div class="sia-aviso-camara">{escape(texto)}</div>', unsafe_allow_html=True)


def mostrar_errores(errores: list[str]) -> None:
    st.error("**Revisá el formulario:**\n" + "\n".join(f"- {e}" for e in errores), icon="⚠️")


def tono_porcentaje(pct: float, umbral: float) -> str:
    if pct < umbral:
        return "rojo"
    if pct < umbral + 10:
        return "ambar"
    return "verde"


def estilo_plotly(fig, alto: int = 360):
    oscuro = modo_oscuro()
    texto = "#E2E8F0" if oscuro else "#0E2747"
    grilla = "rgba(201,212,234,.20)" if oscuro else "rgba(121,121,177,.18)"
    linea = "rgba(201,212,234,.45)" if oscuro else "rgba(52,111,176,.35)"
    fig.update_layout(
        template="plotly_dark" if oscuro else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=alto,
        # Título arriba de todo y leyenda justo sobre el área del gráfico: quedan en alturas distintas y no
        # se pisan. La leyenda va alineada a la izquierda para que en celulares se parta en varias filas
        # dentro del ancho (alineada a la derecha se salía del gráfico por la izquierda).
        title=dict(x=0, xanchor="left", yref="container", y=0.97, yanchor="top"),
        margin=dict(l=10, r=10, t=82, b=40),
        font=dict(family="Plus Jakarta Sans, Inter, Nunito, sans-serif", size=13, color=texto),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    title_text="",  # sin título flotante ("Riesgo", "materia") que choque con el título
                    font=dict(color=texto), bgcolor="rgba(0,0,0,0)"),
        title_font=dict(size=15, color=texto),
        hoverlabel=dict(bgcolor=AZUL_OSCURO if oscuro else "#FFFFFF", font=dict(color=texto),
                        bordercolor=LAVANDA),
        # En oscuro se usan variantes más claras de la paleta para mantener el contraste sobre #003467.
        colorway=["#7FA9DE", "#D4B6D3", "#A9A9D6", "#5FC4A0", "#F0C36B", "#E8A0A0"] if oscuro
        else [AZUL, LILA, LAVANDA, AZUL_OSCURO, "#2E9E77", "#D99A2B"],
    )
    ejes = dict(gridcolor=grilla, zerolinecolor=grilla, linecolor=linea,
                tickfont=dict(color=texto), title_font=dict(color=texto))
    fig.update_xaxes(**ejes)
    fig.update_yaxes(**ejes)
    fig.update_annotations(font_color=texto)
    fig.update_coloraxes(colorbar_tickfont_color=texto, colorbar_title_font_color=texto)
    titulo = fig.layout.title.text
    if titulo and not titulo.startswith("<b>"):
        fig.update_layout(title_text=f"<b>{titulo}</b>")
    return fig
