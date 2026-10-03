"""Generación y lectura de códigos QR.

Contenido de los QR:
  * Si la app tiene una URL pública (`SIA_PUBLIC_URL` o la URL detectada del navegador),
    el QR es un enlace real: escaneado con la cámara nativa del celular abre la app y
    ejecuta la acción (inscribirse / dar presente) tras iniciar sesión.
      - Inscripción: <url>/?inscribir=<codigo>&f=<firma HMAC>
      - Asistencia:  <url>/?asistencia=<token dinámico firmado>
  * En entornos locales (localhost) el QR contiene el payload `SIA:` firmado, que se lee
    con el escáner integrado en la app.
"""
from __future__ import annotations

import io
from urllib.parse import parse_qs, urlencode, urlparse

import numpy as np
import qrcode
from PIL import Image, ImageOps
from qrcode.constants import ERROR_CORRECT_M

from core.security import config_valor

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    from pyzbar import pyzbar
except Exception:  # pyzbar requiere la librería del sistema libzbar0
    pyzbar = None

_HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


# ---------------------------------------------------------------- URLs reales
def url_publica() -> str | None:
    """URL base de la app accesible desde un celular, o None si solo corre en local."""
    base = config_valor("SIA_PUBLIC_URL")
    if not base:
        try:
            import streamlit as st

            base = st.context.url
        except Exception:
            return None
    if not base:
        return None
    partes = urlparse(base)
    if not partes.scheme or not partes.hostname or partes.hostname in _HOSTS_LOCALES:
        return None
    return f"{partes.scheme}://{partes.netloc}{partes.path}".rstrip("/")


def contenido_inscripcion(codigo: str, firma: str, payload: str) -> str:
    base = url_publica()
    return f"{base}/?{urlencode({'inscribir': codigo, 'f': firma})}" if base else payload


def contenido_asistencia(token: str) -> str:
    base = url_publica()
    return f"{base}/?{urlencode({'asistencia': token})}" if base else token


def interpretar_codigo(texto: str) -> str:
    """Normaliza lo leído: convierte URLs de la app al payload `SIA:` equivalente."""
    texto = (texto or "").strip()
    if not texto.lower().startswith(("http://", "https://")):
        return texto
    parametros = parse_qs(urlparse(texto).query)
    if "asistencia" in parametros:
        return parametros["asistencia"][0]
    if "inscribir" in parametros:
        codigo = parametros["inscribir"][0]
        firma = parametros.get("f", [""])[0]
        return f"SIA:ENROLL:{codigo}:{firma}" if firma else codigo
    return texto


# ---------------------------------------------------------------- generación
def generar_qr_png(data: str, box_size: int = 10, color: str = "#0B3D91") -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=3)
    qr.add_data(data)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color=color, back_color="white").convert("RGB")
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------- lectura
def _con_opencv(gris: np.ndarray) -> list[str]:
    if cv2 is None:
        return []
    detector = cv2.QRCodeDetector()
    try:
        ok, textos, _, _ = detector.detectAndDecodeMulti(gris)
        if ok:
            encontrados = [t for t in textos if t]
            if encontrados:
                return encontrados
    except cv2.error:
        pass
    texto, _, _ = detector.detectAndDecode(gris)
    return [texto] if texto else []


def _con_pyzbar(gris: np.ndarray) -> list[str]:
    if pyzbar is None:
        return []
    return [r.data.decode("utf-8", errors="ignore") for r in pyzbar.decode(gris) if r.type == "QRCODE"]


def decodificar_qr(imagen_bytes: bytes) -> list[str]:
    """Textos de todos los QR detectados (OpenCV primero, pyzbar como respaldo), ya normalizados."""
    imagen = ImageOps.exif_transpose(Image.open(io.BytesIO(imagen_bytes))).convert("L")
    gris = np.array(imagen)
    variantes = [gris]
    if cv2 is not None:
        variantes.append(cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5))
        if max(gris.shape) < 900:
            variantes.append(cv2.resize(gris, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    for variante in variantes:
        for lector in (_con_opencv, _con_pyzbar):
            textos = lector(variante)
            if textos:
                return list(dict.fromkeys(interpretar_codigo(t) for t in textos))
    return []


def lectores_disponibles() -> list[str]:
    return [nombre for nombre, mod in (("OpenCV", cv2), ("pyzbar", pyzbar)) if mod is not None]
