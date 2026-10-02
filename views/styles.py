"""CSS personalizado y componentes visuales reutilizables."""
from __future__ import annotations

from html import escape

import streamlit as st

TONOS = {
    "indigo": "#4F46E5",
    "verde": "#059669",
    "ambar": "#D97706",
    "rojo": "#DC2626",
    "gris": "#475569",
    "cian": "#0891B2",
}

COLORES_NIVEL = {"ALTO": "#DC2626", "MEDIO": "#D97706", "BAJO": "#059669"}
EMOJI_NIVEL = {"ALTO": "🔴", "MEDIO": "🟡", "BAJO": "🟢"}

_CSS = """
<style>
:root {
  --sia-surface: #FFFFFF;
  --sia-border: rgba(15, 23, 42, 0.08);
  --sia-muted: #64748B;
  --sia-ink: #0F172A;
  --sia-shadow: 0 1px 2px rgba(15,23,42,.05), 0 6px 18px rgba(15,23,42,.06);
}
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }
h1, h2, h3 { letter-spacing: -0.01em; }

.sia-hero {
  background: linear-gradient(120deg, #4F46E5 0%, #7C3AED 55%, #0891B2 100%);
  color: #fff; border-radius: 20px; padding: 1.4rem 1.8rem; margin-bottom: 1.2rem;
  box-shadow: 0 10px 30px rgba(79,70,229,.25);
}
.sia-hero h1 { color: #fff; font-size: 1.7rem; margin: 0 0 .2rem 0; padding: 0; }
.sia-hero p { margin: 0; opacity: .92; }

.sia-card {
  background: var(--sia-surface); border: 1px solid var(--sia-border); border-radius: 16px;
  padding: 1.1rem 1.3rem; box-shadow: var(--sia-shadow); margin-bottom: .8rem;
}
.sia-kpi { border-left: 5px solid var(--tono); }
.sia-kpi .label { font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--sia-muted); }
.sia-kpi .value { font-size: 2rem; font-weight: 800; color: var(--sia-ink); line-height: 1.15; margin-top: .15rem; }
.sia-kpi .sub { font-size: .82rem; color: var(--sia-muted); margin-top: .1rem; }

.sia-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 1.6rem; font-weight: 800;
  letter-spacing: .12em; color: #4F46E5; background: #EEF2FF; border-radius: 12px;
  padding: .4rem .9rem; display: inline-block;
}
.sia-pin { font-size: 3rem; letter-spacing: .3em; }

.sia-badge {
  display: inline-block; padding: .18rem .65rem; border-radius: 999px; font-size: .78rem;
  font-weight: 700; color: #fff; background: var(--tono);
}
.sia-alerta {
  border-radius: 14px; padding: .8rem 1rem; margin-bottom: .55rem; border: 1px solid var(--sia-border);
  border-left: 6px solid var(--tono); background: var(--sia-surface); box-shadow: var(--sia-shadow);
}
.sia-alerta b { color: var(--sia-ink); }
.sia-alerta span { color: var(--sia-muted); font-size: .88rem; }

div[data-testid="stMetric"] {
  background: var(--sia-surface); border: 1px solid var(--sia-border); border-radius: 14px;
  padding: .8rem 1rem; box-shadow: var(--sia-shadow);
}
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
.stTabs [data-baseweb="tab-list"] { gap: .4rem; }
.stTabs [data-baseweb="tab"] {
  background: #EEF2FF; border-radius: 10px 10px 0 0; padding: .45rem 1rem; font-weight: 600;
}
.stTabs [aria-selected="true"] { background: #4F46E5 !important; color: #fff !important; }
section[data-testid="stSidebar"] { border-right: 1px solid var(--sia-border); }
</style>
"""


def inyectar_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f'<div class="sia-hero"><h1>{escape(titulo)}</h1><p>{escape(subtitulo)}</p></div>',
        unsafe_allow_html=True,
    )


def kpi(label: str, valor: str, sub: str = "", tono: str = "indigo") -> None:
    color = TONOS.get(tono, tono)
    st.markdown(
        f'<div class="sia-card sia-kpi" style="--tono:{color}">'
        f'<div class="label">{escape(label)}</div><div class="value">{escape(str(valor))}</div>'
        f'<div class="sub">{escape(sub)}</div></div>',
        unsafe_allow_html=True,
    )


def badge(texto: str, tono: str = "indigo") -> str:
    return f'<span class="sia-badge" style="--tono:{TONOS.get(tono, tono)}">{escape(texto)}</span>'


def alerta(titulo: str, detalle: str, color: str) -> None:
    st.markdown(
        f'<div class="sia-alerta" style="--tono:{color}"><b>{escape(titulo)}</b><br><span>{escape(detalle)}</span></div>',
        unsafe_allow_html=True,
    )


def codigo(texto: str, grande: bool = False) -> None:
    clase = "sia-code sia-pin" if grande else "sia-code"
    st.markdown(f'<div class="{clase}">{escape(texto)}</div>', unsafe_allow_html=True)


def tono_porcentaje(pct: float, umbral: float) -> str:
    if pct < umbral:
        return "rojo"
    if pct < umbral + 10:
        return "ambar"
    return "verde"


def estilo_plotly(fig, alto: int = 360):
    fig.update_layout(
        template="plotly_white",
        height=alto,
        margin=dict(l=10, r=10, t=40, b=10),
        font=dict(family="Inter, system-ui, sans-serif", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        title_font=dict(size=15),
    )
    return fig
