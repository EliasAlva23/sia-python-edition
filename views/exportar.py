"""Botones de exportación: descarga CSV/Excel/PDF y envío a Google Drive."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.drive import drive_configurado, subir_archivo
from core.reportes import excel_bytes

_AYUDA_DRIVE = ("Para habilitarlo, quien administra la app debe cargar las credenciales de Google Drive en los "
                "Secrets (ver docs/ARQUITECTURA.md, sección Google Drive).")


def boton_drive(nombre: str, contenido: bytes, clave: str, etiqueta: str = "☁️ Enviar a Google Drive") -> None:
    if not drive_configurado():
        st.button(etiqueta, key=clave, disabled=True, width="stretch", help=_AYUDA_DRIVE)
        return
    if st.button(etiqueta, key=clave, width="stretch", help="Guarda una copia en la carpeta institucional de Drive."):
        with st.spinner("Enviando a Google Drive…"):
            resultado = subir_archivo(nombre, contenido)
        if resultado.ok:
            enlace = f" [Abrir en Drive]({resultado.enlace})" if resultado.enlace else ""
            st.success(f"☁️ {resultado.mensaje}{enlace}")
        else:
            st.error(f"⛔ {resultado.mensaje}")


def exportaciones(nombre_base: str, hojas: dict[str, pd.DataFrame], clave: str) -> None:
    """Fila de botones: CSV (primera hoja), Excel (todas las hojas) y envío del Excel a Drive."""
    primera = next(iter(hojas.values()))
    xlsx = excel_bytes(hojas)
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ CSV", primera.to_csv(index=False).encode("utf-8-sig"), file_name=f"{nombre_base}.csv",
                       mime="text/csv", key=f"{clave}_csv", width="stretch")
    c2.download_button("⬇️ Excel", xlsx, file_name=f"{nombre_base}.xlsx", key=f"{clave}_xlsx", width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with c3:
        boton_drive(f"{nombre_base}.xlsx", xlsx, f"{clave}_drive")
