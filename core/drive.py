"""Envío de reportes (CSV, Excel, PDF) a una carpeta institucional de Google Drive.

Se configura con Secrets de Streamlit (o variables de entorno). Hay dos modos; se usa el primero disponible:

1. Cuenta de servicio (recomendado si la institución tiene Google Workspace con Unidades compartidas):
     SIA_DRIVE_SERVICE_ACCOUNT = '''{ ...JSON de la cuenta de servicio... }'''
     SIA_DRIVE_FOLDER_ID       = "<id de la carpeta dentro de la Unidad compartida>"
   La carpeta debe compartirse con el email de la cuenta de servicio (rol Editor). Importante: las cuentas
   de servicio no tienen espacio propio, por eso la carpeta tiene que estar en una Unidad compartida.

2. Cuenta de Google autorizada una vez (sirve también para cuentas @gmail.com):
     SIA_DRIVE_CLIENT_ID, SIA_DRIVE_CLIENT_SECRET, SIA_DRIVE_REFRESH_TOKEN, SIA_DRIVE_FOLDER_ID
   El refresh token se obtiene con `python scripts/drive_autorizar.py` (ver docs/ARQUITECTURA.md).

Se usa el permiso mínimo `drive.file`: la app solo ve los archivos que ella misma crea.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from core.security import config_valor

ALCANCE = ["https://www.googleapis.com/auth/drive.file"]
_URL_SUBIDA = ("https://www.googleapis.com/upload/drive/v3/files"
               "?uploadType=multipart&supportsAllDrives=true&fields=id,name,webViewLink")
MIME = {
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True)
class ResultadoDrive:
    ok: bool
    mensaje: str
    enlace: str | None = None


def _credenciales():
    cuenta = config_valor("SIA_DRIVE_SERVICE_ACCOUNT")
    if cuenta:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_info(json.loads(cuenta), scopes=ALCANCE)
    token = config_valor("SIA_DRIVE_REFRESH_TOKEN")
    cliente, secreto = config_valor("SIA_DRIVE_CLIENT_ID"), config_valor("SIA_DRIVE_CLIENT_SECRET")
    if token and cliente and secreto:
        from google.oauth2.credentials import Credentials

        return Credentials(None, refresh_token=token, token_uri="https://oauth2.googleapis.com/token",
                           client_id=cliente, client_secret=secreto, scopes=ALCANCE)
    return None


def drive_configurado() -> bool:
    return bool(config_valor("SIA_DRIVE_FOLDER_ID")) and (
        bool(config_valor("SIA_DRIVE_SERVICE_ACCOUNT"))
        or all(config_valor(k) for k in ("SIA_DRIVE_CLIENT_ID", "SIA_DRIVE_CLIENT_SECRET", "SIA_DRIVE_REFRESH_TOKEN"))
    )


def _cuerpo_multipart(nombre: str, contenido: bytes, mime: str, carpeta: str) -> tuple[bytes, str]:
    limite = "sia_drive_limite_7f3a"
    metadatos = json.dumps({"name": nombre, "parents": [carpeta]}).encode("utf-8")
    cuerpo = (
        f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + metadatos
        + f"\r\n--{limite}\r\nContent-Type: {mime}\r\n\r\n".encode() + contenido
        + f"\r\n--{limite}--".encode()
    )
    return cuerpo, f"multipart/related; boundary={limite}"


def subir_archivo(nombre: str, contenido: bytes, mime: str | None = None) -> ResultadoDrive:
    """Sube el archivo a la carpeta configurada y devuelve el enlace para abrirlo."""
    if not drive_configurado():
        return ResultadoDrive(False, "Google Drive no está configurado. Pedile a quien administra la app que "
                                     "cargue las credenciales (ver docs/ARQUITECTURA.md).")
    extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    mime = mime or MIME.get(extension, "application/octet-stream")
    try:
        from google.auth.transport.requests import AuthorizedSession

        sesion = AuthorizedSession(_credenciales())
        cuerpo, tipo = _cuerpo_multipart(nombre, contenido, mime, config_valor("SIA_DRIVE_FOLDER_ID"))
        respuesta = sesion.post(_URL_SUBIDA, data=cuerpo, headers={"Content-Type": tipo}, timeout=60)
    except Exception as exc:  # credenciales mal formadas, red, token revocado…
        return ResultadoDrive(False, f"No se pudo conectar con Google Drive: {type(exc).__name__}.")
    if respuesta.status_code in (200, 201):
        datos = respuesta.json()
        return ResultadoDrive(True, f"«{datos.get('name', nombre)}» se guardó en Google Drive.", datos.get("webViewLink"))
    try:
        detalle = respuesta.json().get("error", {}).get("message", "")
    except ValueError:
        detalle = respuesta.text[:200]
    if respuesta.status_code == 403 and "storage" in detalle.lower():
        detalle = ("la cuenta de servicio no tiene espacio propio: usá una carpeta dentro de una Unidad "
                   "compartida o el modo con refresh token")
    elif respuesta.status_code == 404:
        detalle = "no se encontró la carpeta (revisá SIA_DRIVE_FOLDER_ID y que esté compartida con la app)"
    return ResultadoDrive(False, f"Google Drive rechazó el archivo ({respuesta.status_code}): {detalle}")
