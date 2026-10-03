"""Identidad visual ISE: tema claro/oscuro, tarjetas, botones, logo y componentes."""
from __future__ import annotations

import base64
from functools import lru_cache
from html import escape
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
_NOMBRES_LOGO = ("logo_ise.png", "logo_ise.svg", "logo_ise.webp", "logo_ise.jpg", "logo_ise.jpeg")
_MIME = {".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
CLAVE_TEMA = "modo_oscuro"

# Paleta corporativa ISE (azules y celestes)
TONOS = {
    "azul": "#0B5CAD",
    "celeste": "#1E9BD7",
    "verde": "#0E9F6E",
    "ambar": "#D98E04",
    "rojo": "#D93B3B",
    "gris": "#64748B",
    "indigo": "#0B5CAD",
    "cian": "#1E9BD7",
}
COLORES_NIVEL = {"ALTO": "#D93B3B", "MEDIO": "#D98E04", "BAJO": "#0E9F6E"}
EMOJI_NIVEL = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}

_VARIABLES = {
    "claro": """
  --sia-bg: #F2F6FB;
  --sia-bg-grad: radial-gradient(1200px 500px at 10% -10%, #DCEBFA 0%, transparent 60%);
  --sia-surface: #FFFFFF;
  --sia-surface-2: #EAF2FB;
  --sia-input: #FFFFFF;
  --sia-ink: #0B1F3A;
  --sia-muted: #5B6B82;
  --sia-border: rgba(11, 92, 173, 0.14);
  --sia-primary: #0B5CAD;
  --sia-primary-2: #1E9BD7;
  --sia-primary-ink: #FFFFFF;
  --sia-accent-soft: #E3F1FC;
  --sia-shadow: 0 1px 2px rgba(11,31,58,.06), 0 8px 24px rgba(11,31,58,.08);
  --sia-shadow-hover: 0 4px 10px rgba(11,92,173,.18), 0 14px 32px rgba(11,31,58,.12);
""",
    "oscuro": """
  --sia-bg: #0A1220;
  --sia-bg-grad: radial-gradient(1200px 500px at 10% -10%, #10294A 0%, transparent 60%);
  --sia-surface: #111C2F;
  --sia-surface-2: #172640;
  --sia-input: #0D1728;
  --sia-ink: #E6EEF8;
  --sia-muted: #9DB0C8;
  --sia-border: rgba(120, 175, 235, 0.18);
  --sia-primary: #3B9BFF;
  --sia-primary-2: #4FC3F7;
  --sia-primary-ink: #04121F;
  --sia-accent-soft: #12304F;
  --sia-shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
  --sia-shadow-hover: 0 4px 12px rgba(59,155,255,.25), 0 14px 32px rgba(0,0,0,.45);
""",
}

_CSS = """
<style>
:root, .stApp {{ {variables} }}

/* ---------- Base ---------- */
.stApp, [data-testid="stAppViewContainer"] {{
  background: var(--sia-bg-grad), var(--sia-bg) !important; color: var(--sia-ink);
}}
[data-testid="stHeader"] {{ background: transparent !important; }}
[data-testid="stToolbar"] button, [data-testid="stHeader"] button {{ color: var(--sia-ink) !important; }}
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
h1, h2, h3, h4 {{ letter-spacing: -0.01em; }}
[data-testid="stMarkdownContainer"] a {{ color: var(--sia-primary); }}

/* ---------- Inputs ---------- */
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"],
[data-testid="stNumberInputContainer"], [data-testid="stDateInputField"],
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"],
div:has(> input[role="combobox"]),
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div {{
  background: var(--sia-input) !important; border-color: var(--sia-border) !important; border-radius: 12px !important;
}}
[data-testid="stTextInputRootElement"] input, [data-testid="stTextAreaRootElement"] textarea,
[data-testid="stNumberInputContainer"] input, input[role="combobox"],
[data-testid="stSelectbox"] [role="group"] div, [data-testid="stMultiSelect"] [role="group"] div,
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea, [data-baseweb="select"] div {{
  color: var(--sia-ink) !important; -webkit-text-fill-color: var(--sia-ink) !important; background-color: transparent !important;
}}
[data-testid="stSelectbox"] svg, [data-testid="stMultiSelect"] svg {{ fill: var(--sia-muted); color: var(--sia-muted); }}
[role="listbox"], [role="listbox"] [role="option"] {{ background: var(--sia-surface) !important; color: var(--sia-ink) !important; }}
[role="listbox"] [role="option"]:hover, [role="listbox"] [aria-selected="true"] {{ background: var(--sia-surface-2) !important; }}
[data-testid="stCheckbox"] label > div:first-child {{ background-color: var(--sia-input); border-color: var(--sia-border); }}
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stSelectbox"] [role="group"]:focus-within {{
  border-color: var(--sia-primary) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--sia-primary) 25%, transparent) !important;
}}
input::placeholder, textarea::placeholder {{ color: var(--sia-muted) !important; -webkit-text-fill-color: var(--sia-muted) !important; }}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {{
  border-color: var(--sia-primary) !important; box-shadow: 0 0 0 3px color-mix(in srgb, var(--sia-primary) 25%, transparent) !important;
}}
[data-baseweb="popover"] ul, [data-baseweb="menu"], [data-baseweb="popover"] li {{
  background: var(--sia-surface) !important; color: var(--sia-ink) !important;
}}
[data-baseweb="popover"] li:hover {{ background: var(--sia-surface-2) !important; }}
[data-baseweb="tag"] {{ background: var(--sia-accent-soft) !important; border-radius: 8px !important; }}
[data-baseweb="tag"] span {{ color: var(--sia-ink) !important; }}

/* ---------- Botones ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button,
[data-testid="stPopover"] > div > button, [data-testid="stPopoverButton"] {{
  border-radius: 12px !important; font-weight: 600 !important; padding: .5rem 1.1rem !important;
  transition: transform .15s ease, box-shadow .15s ease !important;
}}
button[kind^="primary"], button[data-testid^="stBaseButton-primary"] {{
  background: linear-gradient(135deg, var(--sia-primary) 0%, var(--sia-primary-2) 100%) !important;
  color: var(--sia-primary-ink) !important; border: none !important; box-shadow: var(--sia-shadow);
}}
button[kind^="primary"] p, button[data-testid^="stBaseButton-primary"] p {{ color: var(--sia-primary-ink) !important; }}
button[kind^="secondary"], button[data-testid^="stBaseButton-secondary"], [data-testid="stPopoverButton"] {{
  background: var(--sia-surface) !important; color: var(--sia-primary) !important;
  border: 1.5px solid color-mix(in srgb, var(--sia-primary) 45%, transparent) !important;
}}
button[kind^="secondary"] p, button[data-testid^="stBaseButton-secondary"] p, [data-testid="stPopoverButton"] p {{
  color: var(--sia-primary) !important;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover,
[data-testid="stPopoverButton"]:hover {{
  transform: translateY(-2px); box-shadow: var(--sia-shadow-hover) !important;
}}
button[kind^="secondary"]:hover, button[data-testid^="stBaseButton-secondary"]:hover {{
  background: var(--sia-accent-soft) !important; border-color: var(--sia-primary) !important;
}}
.stButton > button:active, .stFormSubmitButton > button:active {{ transform: translateY(0); }}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {{ opacity: .55; transform: none; box-shadow: none !important; }}

/* ---------- Contenedores como tarjetas ---------- */
[data-testid="stForm"], [data-testid="stExpander"] details, div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stCameraInput"], [data-testid="stPopoverBody"], [data-testid="stMetric"] {{
  background: var(--sia-surface) !important; border: 1px solid var(--sia-border) !important;
  border-radius: 16px !important; box-shadow: var(--sia-shadow);
}}
[data-testid="stForm"] {{ padding: 1.2rem 1.3rem !important; }}
[data-testid="stMetric"] {{ padding: .85rem 1rem; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {{ color: var(--sia-ink) !important; }}
[data-testid="stMetricLabel"] p {{ color: var(--sia-muted) !important; }}
[data-testid="stExpander"] summary {{ background: var(--sia-surface) !important; border-radius: 16px; }}
[data-testid="stExpander"] details[open] > summary {{ border-radius: 16px 16px 0 0; }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span {{
  color: var(--sia-ink) !important;
}}
[data-testid="stExpander"] summary:hover {{ background: var(--sia-surface-2) !important; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--sia-primary) !important; }}
[data-testid="stAlert"], [data-testid="stAlertContainer"] {{ border-radius: 12px !important; }}
[data-testid="stCode"] pre, [data-testid="stCode"] code, .stCodeBlock pre {{
  background: var(--sia-surface-2) !important; color: var(--sia-ink) !important; border-radius: 12px !important;
}}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{ border-radius: 12px; overflow: hidden; border: 1px solid var(--sia-border); }}
[data-testid="stImage"] img {{ border-radius: 12px; }}
hr {{ border-color: var(--sia-border) !important; }}

/* ---------- Pestañas ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: .4rem; overflow-x: auto; scrollbar-width: thin; padding-bottom: 2px; }}
.stTabs [data-baseweb="tab"] {{
  background: var(--sia-surface-2); border-radius: 12px 12px 0 0; padding: .5rem 1rem; font-weight: 600;
  white-space: nowrap; color: var(--sia-ink);
}}
.stTabs [data-baseweb="tab"] p {{ color: var(--sia-ink); }}
.stTabs [aria-selected="true"] {{ background: linear-gradient(135deg, var(--sia-primary), var(--sia-primary-2)) !important; }}
.stTabs [aria-selected="true"] p {{ color: var(--sia-primary-ink) !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ---------- Componentes SIA ---------- */
.sia-hero {{
  display: flex; align-items: center; gap: 1.2rem;
  background: linear-gradient(120deg, #0B3D91 0%, #0B5CAD 45%, #1E9BD7 100%);
  color: #fff; border-radius: 20px; padding: 1.3rem 1.6rem; margin-bottom: 1.2rem;
  box-shadow: 0 12px 30px rgba(11,92,173,.28);
}}
.sia-hero h1 {{ color: #fff !important; font-size: 1.65rem; margin: 0 0 .15rem 0; padding: 0; line-height: 1.2; }}
.sia-hero p {{ margin: 0; opacity: .93; color: #fff !important; }}
.sia-hero .sia-logo {{ flex: 0 0 auto; }}
.sia-hero a, .sia-hero [data-testid="stHeaderActionElements"] {{ display: none !important; }}
.sia-logo img {{ display: block; height: 64px; width: auto; max-width: 160px; object-fit: contain;
  background: #fff; border-radius: 14px; padding: 6px; }}
.sia-logo-placeholder {{
  width: 64px; height: 64px; border-radius: 16px; display: flex; align-items: center; justify-content: center;
  background: #fff; color: #0B5CAD; font-weight: 900; font-size: 1.25rem; letter-spacing: .04em;
  box-shadow: inset 0 0 0 3px #1E9BD7;
}}
.sia-brand {{ display: flex; align-items: center; gap: .75rem; margin-bottom: .6rem; }}
.sia-brand .sia-logo img {{ height: 48px; }}
.sia-brand .sia-logo-placeholder {{ width: 48px; height: 48px; font-size: 1rem; border-radius: 12px; }}
.sia-brand b {{ font-size: 1.05rem; color: var(--sia-ink); }}
.sia-brand small {{ display: block; color: var(--sia-muted); font-size: .78rem; line-height: 1.25; }}

.sia-card {{
  background: var(--sia-surface); border: 1px solid var(--sia-border); border-radius: 16px;
  padding: 1.1rem 1.25rem; box-shadow: var(--sia-shadow); margin-bottom: .8rem; color: var(--sia-ink);
  overflow-wrap: anywhere; transition: box-shadow .2s ease, transform .2s ease;
}}
.sia-card:hover {{ box-shadow: var(--sia-shadow-hover); }}
.sia-card .muted, .sia-muted {{ color: var(--sia-muted); font-size: .88rem; }}
.sia-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: .9rem; margin-bottom: 1rem; }}
.sia-grid .sia-card {{ margin-bottom: 0; }}
.sia-kpi {{ border-left: 5px solid var(--tono); }}
.sia-kpi .label {{ font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--sia-muted); }}
.sia-kpi .value {{ font-size: 2rem; font-weight: 800; color: var(--sia-ink); line-height: 1.15; margin-top: .2rem; }}
.sia-kpi .sub {{ font-size: .82rem; color: var(--sia-muted); margin-top: .15rem; }}

.sia-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; margin: .35rem 0 .6rem; }}
.sia-chip {{
  display: inline-flex; align-items: center; gap: .3rem; padding: .25rem .7rem; border-radius: 999px;
  background: var(--sia-accent-soft); color: var(--sia-ink); font-size: .82rem; font-weight: 600;
  border: 1px solid var(--sia-border);
}}
.sia-code {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 1.5rem; font-weight: 800;
  letter-spacing: .12em; color: var(--sia-primary); background: var(--sia-accent-soft); border-radius: 12px;
  padding: .4rem .9rem; display: inline-block; max-width: 100%; overflow-wrap: anywhere;
}}
.sia-pin {{ font-size: 2.8rem; letter-spacing: .28em; }}
.sia-badge {{
  display: inline-block; padding: .18rem .65rem; border-radius: 999px; font-size: .78rem;
  font-weight: 700; color: #fff !important; background: var(--tono);
}}
.sia-alerta {{
  border-radius: 14px; padding: .8rem 1rem; margin-bottom: .55rem; border: 1px solid var(--sia-border);
  border-left: 6px solid var(--tono); background: var(--sia-surface); box-shadow: var(--sia-shadow);
  overflow-wrap: anywhere;
}}
.sia-alerta b {{ color: var(--sia-ink); }}
.sia-alerta span {{ color: var(--sia-muted); font-size: .88rem; }}
.sia-barra {{ height: 8px; border-radius: 999px; background: var(--sia-surface-2); overflow: hidden; margin-top: .55rem; }}
.sia-barra > div {{ height: 100%; border-radius: 999px; background: var(--tono); }}
.sia-footer {{
  margin-top: 2.5rem; padding: 1rem; text-align: center; color: var(--sia-muted); font-size: .85rem;
  border-top: 1px solid var(--sia-border);
}}
.sia-footer b {{ color: var(--sia-primary); }}

/* ---------- Responsive ---------- */
@media (max-width: 900px) {{
  .sia-kpi .value {{ font-size: 1.6rem; }}
}}
@media (max-width: 768px) {{
  .block-container {{ padding: .9rem .8rem 3rem !important; }}
  .sia-hero {{ flex-direction: column; text-align: center; padding: 1.1rem 1rem; gap: .7rem; border-radius: 16px; }}
  .sia-hero h1 {{ font-size: 1.3rem; }}
  .sia-hero p {{ font-size: .9rem; }}
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
  .stTabs [data-baseweb="tab"] {{ padding: .4rem .7rem; font-size: .85rem; }}
  [data-testid="stForm"] {{ padding: .9rem !important; }}
}}
@media (max-width: 340px) {{
  .sia-grid {{ grid-template-columns: 1fr; }}
}}
</style>
"""


# ---------------------------------------------------------------- tema
def modo_oscuro() -> bool:
    return bool(st.session_state.get(CLAVE_TEMA, False))


def inyectar_css() -> None:
    variables = _VARIABLES["oscuro" if modo_oscuro() else "claro"]
    st.markdown(_CSS.format(variables=variables), unsafe_allow_html=True)


def selector_tema() -> None:
    st.toggle("🌙 Modo oscuro", key=CLAVE_TEMA, help="Alterna entre modo claro y oscuro.")


# ---------------------------------------------------------------- logo
def ruta_logo() -> Path | None:
    for nombre in _NOMBRES_LOGO:
        ruta = ASSETS / nombre
        if ruta.exists():
            return ruta
    return None


@lru_cache(maxsize=1)
def _logo_data_uri() -> str | None:
    ruta = ruta_logo()
    if ruta is None:
        return None
    return f"data:{_MIME[ruta.suffix.lower()]};base64,{base64.b64encode(ruta.read_bytes()).decode()}"


def logo_html() -> str:
    uri = _logo_data_uri()
    if uri:
        return f'<div class="sia-logo"><img src="{uri}" alt="Logo ISE"></div>'
    return '<div class="sia-logo"><div class="sia-logo-placeholder" title="Agregá assets/logo_ise.png">ISE</div></div>'


def marca_sidebar() -> None:
    st.markdown(
        f'<div class="sia-brand">{logo_html()}<div><b>SIA · ISE</b>'
        f"<small>Sistema de Asistencia Inteligente</small></div></div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- componentes
def hero(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f'<div class="sia-hero">{logo_html()}<div><h1>{escape(titulo)}</h1><p>{escape(subtitulo)}</p></div></div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        '<div class="sia-footer">SIA · Instituto ISE — Desarrollado por <b>Tech Innovation Team</b></div>',
        unsafe_allow_html=True,
    )


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
    texto = "#E6EEF8" if oscuro else "#0B1F3A"
    grilla = "rgba(157,176,200,.18)" if oscuro else "rgba(11,31,58,.08)"
    fig.update_layout(
        template="plotly_dark" if oscuro else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=alto,
        margin=dict(l=10, r=10, t=48, b=10),
        font=dict(family="Inter, system-ui, sans-serif", size=13, color=texto),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        title_font=dict(size=15, color=texto),
        colorway=["#0B5CAD", "#1E9BD7", "#4FC3F7", "#0E9F6E", "#D98E04", "#7C8DB5"],
    )
    fig.update_xaxes(gridcolor=grilla, zerolinecolor=grilla)
    fig.update_yaxes(gridcolor=grilla, zerolinecolor=grilla)
    return fig
