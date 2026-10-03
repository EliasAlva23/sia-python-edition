"""Soporte PWA básico: permite "Agregar a pantalla principal" en Android e iOS.

Streamlit no deja editar el <head> desde Python, así que un script pequeño agrega las etiquetas al cargar.
El manifiesto y los íconos se sirven desde ./static (requiere `server.enableStaticServing = true`).
En Streamlit Community Cloud la app corre dentro de un iframe del mismo dominio: las etiquetas se agregan
también en la página contenedora para que el navegador ofrezca la instalación.
"""
from __future__ import annotations

import json

import streamlit as st

from views.styles import AZUL_NOCHE

_SCRIPT = """
<script>
(function () {
  var datos = %(datos)s;
  function aplicar(doc, base) {
    if (!doc || !doc.head || doc.getElementById("sia-pwa-manifest")) return;
    var url = function (archivo) { return new URL(archivo, base).href; };
    var etiquetas = [
      ["link", {id: "sia-pwa-manifest", rel: "manifest", href: url("manifest.json")}],
      ["link", {rel: "apple-touch-icon", sizes: "180x180", href: url("apple-touch-icon.png")}],
      ["link", {rel: "icon", type: "image/png", sizes: "192x192", href: url("icon-192.png")}],
      ["meta", {name: "theme-color", content: datos.color}],
      ["meta", {name: "mobile-web-app-capable", content: "yes"}],
      ["meta", {name: "apple-mobile-web-app-capable", content: "yes"}],
      ["meta", {name: "apple-mobile-web-app-status-bar-style", content: "black-translucent"}],
      ["meta", {name: "apple-mobile-web-app-title", content: datos.titulo}],
      ["meta", {name: "application-name", content: datos.titulo}]
    ];
    etiquetas.forEach(function (e) {
      var el = doc.createElement(e[0]);
      Object.keys(e[1]).forEach(function (k) { el.setAttribute(k, e[1][k]); });
      doc.head.appendChild(el);
    });
    if (doc.documentElement) doc.documentElement.setAttribute("lang", "es");
  }
  // Documento de la app: el actual, o el padre si este script corre en el iframe de respaldo (srcdoc).
  var doc = document;
  try { if (location.protocol === "about:" && window.parent) doc = window.parent.document; } catch (e) {}
  // Los estáticos cuelgan de la ruta de la app (p. ej. /app/static/ o /~/+/app/static/ en Streamlit Cloud).
  var ruta = doc.location.origin + doc.location.pathname.replace(/[^\\/]*$/, "");
  var base = new URL("app/static/", ruta).href;
  aplicar(doc, base);
  try { if (window.top && window.top.document !== doc) aplicar(window.top.document, base); } catch (e) {}
})();
</script>
"""


def inyectar_pwa() -> None:
    script = _SCRIPT % {"datos": json.dumps({"color": AZUL_NOCHE, "titulo": "SIA IES 11"})}
    try:
        # Se ejecuta en la página principal (Streamlit 1.4x+).
        st.html(script, unsafe_allow_javascript=True)
    except TypeError:
        # Versiones anteriores: iframe del mismo origen que escribe en la página contenedora.
        import streamlit.components.v1 as components

        components.html(script, height=0)
