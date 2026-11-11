"""Autoriza una cuenta de Google para que SIA suba reportes a Drive (modo refresh token).

Se ejecuta UNA vez, en una computadora con navegador:

    pip install google-auth-oauthlib
    python scripts/drive_autorizar.py ruta/al/client_secret.json

Antes, en Google Cloud Console:
  1. Crear un proyecto y habilitar "Google Drive API".
  2. Pantalla de consentimiento OAuth (tipo Externo o Interno) con el alcance .../auth/drive.file.
  3. Credenciales -> "ID de cliente de OAuth" -> tipo "App de escritorio" -> descargar el JSON.

El script abre el navegador, pedís permiso con la cuenta institucional y muestra los valores que hay que
pegar en Streamlit Cloud -> Settings -> Secrets (SIA_DRIVE_CLIENT_ID, SIA_DRIVE_CLIENT_SECRET,
SIA_DRIVE_REFRESH_TOKEN). Falta agregar SIA_DRIVE_FOLDER_ID: es la parte final de la URL de la carpeta.
"""
from __future__ import annotations

import json
import sys

ALCANCE = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Falta la dependencia: pip install google-auth-oauthlib")
        sys.exit(1)
    flujo = InstalledAppFlow.from_client_secrets_file(sys.argv[1], ALCANCE)
    credenciales = flujo.run_local_server(port=0, prompt="consent", access_type="offline")
    with open(sys.argv[1], encoding="utf-8") as archivo:
        cliente = next(iter(json.load(archivo).values()))
    print("\nPegá esto en Streamlit Cloud -> Settings -> Secrets:\n")
    print(f'SIA_DRIVE_CLIENT_ID = "{cliente["client_id"]}"')
    print(f'SIA_DRIVE_CLIENT_SECRET = "{cliente["client_secret"]}"')
    print(f'SIA_DRIVE_REFRESH_TOKEN = "{credenciales.refresh_token}"')
    print('SIA_DRIVE_FOLDER_ID = "<id de la carpeta de Drive>"')


if __name__ == "__main__":
    main()
