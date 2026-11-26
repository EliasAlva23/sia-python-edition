"""Gráficos analíticos con un estilo único y sobrio (Plotly).

Reglas: una sola escala por gráfico; una serie -> el color institucional; varias series -> paleta categórica
validada en orden fijo y leyenda; colores de estado solo para riesgo y condición (siempre con leyenda o
etiqueta); umbrales como línea continua fina con su etiqueta; tooltips con formato propio.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from views.styles import (
    COLORES_CONDICION,
    COLORES_NIVEL,
    ESTADO,
    color_serie_unica,
    estilo_plotly,
    linea_referencia,
    modo_oscuro,
    series,
)

_CONFIG = {"displayModeBar": False, "responsive": True}
ORDEN_NIVEL = ["ALTO", "MEDIO", "BAJO"]
NOMBRE_NIVEL = {"ALTO": "Riesgo alto", "MEDIO": "Riesgo medio", "BAJO": "Sin riesgo"}
ORDEN_CONDICION = ["Promociona", "Regular", "Libre"]


def partir(texto, ancho: int = 20) -> str:
    """Parte etiquetas largas en renglones (<br>) para que los ejes no se corten en pantallas angostas."""
    renglones, actual = [], ""
    for palabra in str(texto).split():
        if actual and len(actual) + 1 + len(palabra) > ancho:
            renglones.append(actual)
            actual = palabra
        else:
            actual = f"{actual} {palabra}".strip()
    renglones.append(actual)
    return "<br>".join(renglones[:3]) + ("…" if len(renglones) > 3 else "")


def mostrar(fig, alto: int = 320, titulo: str | None = None) -> None:
    st.plotly_chart(estilo_plotly(fig, alto, titulo), width="stretch", config=_CONFIG)


def _separador() -> str:
    """Color de la superficie: separa segmentos apilados con un hueco de 2 px."""
    return "#0E1116" if modo_oscuro() else "#F6F7F9"


def tendencia(df: pd.DataFrame, x: str, y: str, serie: str | None = None, umbral: float | None = None,
              titulo: str = "", etiqueta_y: str = "% asistencia") -> None:
    """Evolución en el tiempo (líneas finas, marcadores, una sola escala 0-100)."""
    if df.empty:
        st.caption("Todavía no hay datos para este gráfico.")
        return
    fig = px.line(df, x=x, y=y, color=serie, markers=True,
                  color_discrete_sequence=series() if serie else [color_serie_unica()],
                  labels={x: "", y: etiqueta_y, **({serie: ""} if serie else {})})
    fig.update_traces(hovertemplate="%{x|%d/%m/%Y}<br><b>%{y:.0f}%</b><extra>%{fullData.name}</extra>")
    if umbral is not None:
        linea_referencia(fig, umbral, f"Regularidad {umbral:.0f}%")
    fig.update_yaxes(range=[0, 104], ticksuffix="%")
    mostrar(fig, titulo=titulo)


def barras(df: pd.DataFrame, x: str, y: str, titulo: str = "", sufijo: str = "%", umbral: float | None = None,
           horizontal: bool = False, alto: int | None = None) -> None:
    """Magnitud de una sola serie: todas las barras con el color institucional."""
    if df.empty:
        st.caption("Todavía no hay datos para este gráfico.")
        return
    if horizontal:
        df = df.sort_values(y).assign(**{x: lambda d: d[x].map(partir)})
        fig = px.bar(df, x=y, y=x, orientation="h", color_discrete_sequence=[color_serie_unica()],
                     labels={x: "", y: ""})
        fig.update_traces(hovertemplate=f"%{{y}}<br><b>%{{x:.0f}}{sufijo}</b><extra></extra>")
        fig.update_xaxes(ticksuffix=sufijo, range=[0, 104] if sufijo == "%" else None)
        if umbral is not None:
            linea_referencia(fig, umbral, f"{umbral:.0f}%", eje="x")
    else:
        fig = px.bar(df, x=x, y=y, color_discrete_sequence=[color_serie_unica()], labels={x: "", y: ""})
        fig.update_traces(hovertemplate=f"%{{x}}<br><b>%{{y:.0f}}{sufijo}</b><extra></extra>")
        fig.update_yaxes(ticksuffix=sufijo, range=[0, 104] if sufijo == "%" else None)
        if umbral is not None:
            linea_referencia(fig, umbral, f"{umbral:.0f}%")
    mostrar(fig, alto or (max(280, 30 * len(df) + 90) if horizontal else 300), titulo)


def ranking_riesgo(prediccion: pd.DataFrame, etiqueta: str, umbral: float, titulo: str = "") -> None:
    """Asistencia por alumno, coloreada por nivel de riesgo (estado + leyenda con nombre del nivel)."""
    if prediccion.empty:
        return
    datos = prediccion.assign(Nivel=prediccion["nivel"].map(NOMBRE_NIVEL)).sort_values("pct_asistencia")
    fig = px.bar(datos, x="pct_asistencia", y=etiqueta, orientation="h", color="Nivel",
                 color_discrete_map={NOMBRE_NIVEL[k]: v for k, v in COLORES_NIVEL.items()},
                 category_orders={"Nivel": [NOMBRE_NIVEL[n] for n in ORDEN_NIVEL]},
                 labels={"pct_asistencia": "", etiqueta: ""}, custom_data=["motivos"])
    fig.update_traces(hovertemplate="%{y}<br><b>%{x:.0f}%</b><br>%{customdata[0]}<extra>%{fullData.name}</extra>")
    fig.update_xaxes(ticksuffix="%", range=[0, 104])
    fig.update_yaxes(categoryorder="array", categoryarray=list(datos[etiqueta]))
    linea_referencia(fig, umbral, f"Regularidad {umbral:.0f}%", eje="x")
    mostrar(fig, max(300, 26 * len(datos) + 100), titulo)


def mapa_asistencia(df: pd.DataFrame, etiqueta: str, titulo: str = "") -> None:
    """Presencia por alumno y clase: presente en azul claro, ausente en rojo (con leyenda propia)."""
    if df.empty:
        return
    mapa = df.pivot_table(index=etiqueta, columns="fecha", values="presente", aggfunc="max")
    mapa = mapa.loc[mapa.mean(axis=1).sort_values(ascending=False).index]
    presente = "#86b6ef" if not modo_oscuro() else "#256abf"
    fig = go.Figure(go.Heatmap(
        z=mapa.values, x=[pd.to_datetime(c).strftime("%d/%m") for c in mapa.columns], y=list(mapa.index),
        colorscale=[[0, ESTADO["critico"]], [0.5, ESTADO["critico"]], [0.5, presente], [1, presente]],
        zmin=0, zmax=1, showscale=False, xgap=2, ygap=2,
        customdata=[[("Presente" if v == 1 else "Ausente" if v == 0 else "Sin inscripción") for v in fila] for fila in mapa.values],
        hovertemplate="%{y}<br>%{x}: <b>%{customdata}</b><extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, type="category")
    mostrar(fig, max(260, 24 * len(mapa) + 90), titulo)
    st.markdown('<div class="sia-leyenda"><span><span class="sia-marca presente">P</span>Presente (incluye tarde y '
                'justificado)</span><span><span class="sia-marca ausente">A</span>Ausente</span>'
                '<span>Vacío: sin inscripción en esa fecha</span></div>', unsafe_allow_html=True)


def condicion_apilada(conteos: pd.DataFrame, grupo: str, titulo: str = "") -> None:
    """Distribución de condición (Promociona / Regular / Libre) por grupo, en porcentaje (barras apiladas 100%)."""
    if conteos.empty:
        st.caption("Todavía no hay datos para este gráfico.")
        return
    largo = conteos.melt(id_vars=[grupo], value_vars=[c for c in ORDEN_CONDICION if c in conteos],
                         var_name="Condición", value_name="alumnos")
    totales = largo.groupby(grupo)["alumnos"].transform("sum").replace(0, 1)
    largo["pct"] = 100 * largo["alumnos"] / totales
    largo[grupo] = largo[grupo].map(partir)
    fig = px.bar(largo, x="pct", y=grupo, color="Condición", orientation="h", barmode="stack",
                 color_discrete_map=COLORES_CONDICION, category_orders={"Condición": ORDEN_CONDICION},
                 labels={"pct": "", grupo: ""}, custom_data=["alumnos"])
    fig.update_traces(marker_line_width=2, marker_line_color=_separador(),
                      hovertemplate="%{y}<br>%{fullData.name}: <b>%{x:.0f}%</b> (%{customdata[0]} alumnos)<extra></extra>")
    fig.update_xaxes(ticksuffix="%", range=[0, 100])
    mostrar(fig, max(240, 36 * conteos[grupo].nunique() + 110), titulo)


def importancias(df: pd.DataFrame, titulo: str = "Peso de cada factor en la predicción") -> None:
    if df.empty:
        return
    fig = px.bar(df, x="importancia", y="feature", orientation="h", color_discrete_sequence=[color_serie_unica()],
                 labels={"importancia": "", "feature": ""})
    fig.update_traces(hovertemplate="%{y}<br><b>%{x:.0%}</b><extra></extra>")
    fig.update_xaxes(tickformat=".0%")
    mostrar(fig, 280, titulo)
