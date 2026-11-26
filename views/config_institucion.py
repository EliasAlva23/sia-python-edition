"""Formularios de configuración de una institución (identidad visual y umbrales académicos)."""
from __future__ import annotations

from html import escape

import streamlit as st

from core.validaciones import TOLERANCIAS_TARDE
from models.institucion import Institucion
from views.styles import (
    PALETAS,
    configurar_tema,
    contraste,
    mostrar_errores,
    tinta_sobre,
)

ACTUALES = "Colores elegidos"


def form_identidad(inst: Institucion, clave: str, permitir_slug: bool = False) -> None:
    """Nombre, colores y logo (white-label). La vista previa muestra cómo se ven botón y encabezado."""
    with st.form(f"{clave}_identidad"):
        c1, c2 = st.columns([2, 1])
        nombre = c1.text_input("Nombre completo", value=inst.nombre, max_chars=150)
        corto = c2.text_input("Nombre corto", value=inst.nombre_corto, max_chars=40)
        slug = inst.slug
        if permitir_slug:
            slug = st.text_input("Identificador del enlace", value=inst.slug, max_chars=31,
                                 help="Minúsculas, números y guiones. El enlace queda …/?i=" + inst.slug)
        paleta = st.radio("Paleta", [ACTUALES, *PALETAS], horizontal=True,
                          help="Combinaciones de la paleta institucional de SIA. Con «Colores elegidos» se usan "
                               "los dos selectores de abajo.")
        p1, p2 = st.columns(2)
        primario = p1.color_picker("Color principal", value=inst.color_primario,
                                   help="Botones, pestaña activa, anillos de los indicadores y panel de acceso.")
        secundario = p2.color_picker("Color secundario", value=inst.color_secundario, help="Detalles y acentos menores.")
        logo = st.file_uploader("Logo (PNG, JPG o WEBP, hasta 2 MB)", type=["png", "jpg", "jpeg", "webp"], key=f"{clave}_logo")
        guardar = st.form_submit_button("Guardar identidad", type="primary")
    if paleta != ACTUALES:
        primario, secundario = PALETAS[paleta]
    ratio = contraste(primario, tinta_sobre(primario))
    st.markdown(
        f'<div class="sia-card" style="display:flex;gap:.8rem;align-items:center;flex-wrap:wrap">'
        f'<span style="background:{primario};color:{tinta_sobre(primario)};padding:.45rem .9rem;border-radius:6px;'
        f'font-weight:500">Botón principal</span><span style="border-bottom:2px solid {primario};padding:.2rem 0;'
        f'font-weight:600">Pestaña activa</span><span class="sia-muted">Contraste del texto sobre el color: '
        f'{ratio:.1f}:1 {"(correcto)" if ratio >= 4.5 else "(bajo: elegí un tono más oscuro o más claro)"}</span></div>',
        unsafe_allow_html=True,
    )
    if not guardar:
        return
    try:
        inst.actualizar(nombre=nombre, nombre_corto=corto, slug=slug.strip().lower(), color_primario=primario,
                        color_secundario=secundario)
        if logo is not None:
            inst.guardar_logo(logo.getvalue(), logo.type)
    except ValueError as exc:
        mostrar_errores(str(exc).split("\n"))
        return
    if st.session_state.get("institucion_id") == inst.id:
        configurar_tema(inst)
    st.toast(f"Identidad de {escape(inst.nombre_corto)} actualizada")
    st.rerun()


def form_umbrales(inst: Institucion, clave: str) -> None:
    """Porcentajes institucionales para regularizar y promocionar y tolerancia de llegada tarde.

    (El antiguo «código de alta docente» ya no se usa: los docentes los da de alta Preceptoría con un QR.)"""
    with st.form(f"{clave}_umbrales"):
        u1, u2 = st.columns(2)
        regular = u1.slider("Asistencia mínima para regularizar (%)", 50, 100, int(inst.umbral_regular), step=5)
        promocion = u2.slider("Asistencia mínima para promocionar (%)", 50, 100, int(inst.umbral_promocion), step=5)
        tolerancia = st.selectbox("Tolerancia para registrar «tarde»", TOLERANCIAS_TARDE,
                                  index=TOLERANCIAS_TARDE.index(inst.tolerancia_tarde) if inst.tolerancia_tarde in TOLERANCIAS_TARDE else 1,
                                  format_func=lambda m: "Sin tolerancia" if m == 0 else f"{m} minutos",
                                  help="Pasado el inicio de la materia más esta tolerancia, el presente por QR o PIN "
                                       "se registra como «tarde».")
        aplicar = st.checkbox("Aplicar también los umbrales a todas las materias activas",
                              help="Si no se marca, rigen solo para las materias nuevas.")
        guardar = st.form_submit_button("Guardar configuración académica", type="primary")
    if not guardar:
        return
    try:
        inst.actualizar(umbral_regular=regular, umbral_promocion=promocion, tolerancia_tarde=tolerancia)
    except ValueError as exc:
        mostrar_errores(str(exc).split("\n"))
        return
    cantidad = inst.aplicar_umbrales_a_materias() if aplicar else 0
    st.toast("Configuración guardada" + (f" · {cantidad} materias actualizadas" if aplicar else ""))
    st.rerun()
