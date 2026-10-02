"""Fechas en la zona horaria institucional (Streamlit Cloud corre en UTC)."""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("SIA_TZ", "America/Argentina/Buenos_Aires"))


def ahora() -> datetime:
    return datetime.now(TZ).replace(microsecond=0, tzinfo=None)


def ahora_iso() -> str:
    return ahora().isoformat()


def hoy() -> date:
    return ahora().date()
