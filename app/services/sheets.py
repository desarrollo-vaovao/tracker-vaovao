"""Escritura en el Google Sheet del cliente con detección automática de columnas.

Estrategia:
  1. Lee la fila de encabezados (fila 1).
  2. Si hay claves nuevas en el lead que no existen como columna, las agrega.
  3. Arma la fila alineada al orden de los encabezados y la añade al final.

Así, si un cliente cambia las preguntas del formulario, las columnas nuevas
aparecen solas sin tocar el código.
"""
import json
import logging
import os
import threading

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings

logger = logging.getLogger("vaovao.sheets")
settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Columnas de metadata que siempre van primero, en este orden.
META_COLUMNS = ["received_at", "leadgen_id", "form_id", "campaign_name", "ad_name"]

# Un lock por proceso evita que dos leads simultáneos pisen el encabezado
# del mismo Sheet. Para escala alta, un worker dedicado por Sheet es mejor.
_sheet_lock = threading.Lock()

_client: gspread.Client | None = None


def _get_client() -> gspread.Client:
    global _client
    if _client is None:
        # En producción (Railway): credenciales desde variable de entorno.
        # En local: desde el archivo apuntado por GOOGLE_SERVICE_ACCOUNT_FILE.
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if creds_json:
            info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                settings.google_service_account_file, scopes=SCOPES
            )
        _client = gspread.authorize(creds)
    return _client


def append_lead_row(sheet_id: str, tab: str, row: dict[str, str]) -> None:
    """Añade una fila al Sheet, creando columnas que no existan."""
    with _sheet_lock:
        gc = _get_client()
        sh = gc.open_by_key(sheet_id)

        try:
            ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab, rows=1000, cols=max(26, len(row) + 5))

        headers = ws.row_values(1)

        if not headers:
            # Hoja vacía: ordena metadata primero, luego el resto de campos.
            ordered = [c for c in META_COLUMNS if c in row]
            ordered += [k for k in row if k not in ordered]
            ws.update("A1", [ordered])
            headers = ordered
        else:
            # Detecta claves nuevas y amplía el encabezado.
            new_keys = [k for k in row if k not in headers]
            if new_keys:
                headers = headers + new_keys
                ws.update("A1", [headers])

        values = [row.get(col, "") for col in headers]
        ws.append_row(values, value_input_option="RAW")
        logger.info("Lead escrito en Sheet %s (tab %s)", sheet_id, tab)
        # deploy: credenciales desde variable de entorno