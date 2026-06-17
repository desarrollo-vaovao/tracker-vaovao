
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("vaovao.meta")
settings = get_settings()

GRAPH_BASE = "https://graph.facebook.com"

LEAD_FIELDS = "id,created_time,form_id,ad_id,ad_name,campaign_id,campaign_name,field_data"


class MetaError(Exception):
    pass


def fetch_lead(leadgen_id: str, page_access_token: str) -> dict:
    """GET /{leadgen_id} -> dict crudo del lead. Lanza MetaError si falla."""
    url = f"{GRAPH_BASE}/{settings.graph_api_version}/{leadgen_id}"
    params = {"fields": LEAD_FIELDS, "access_token": page_access_token}

    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, params=params)

    if resp.status_code != 200:
        raise MetaError(f"Graph API {resp.status_code}: {resp.text}")

    return resp.json()


def parse_field_data(lead: dict) -> dict[str, str]:
    """Convierte el field_data de Meta en un dict {nombre_campo: valor}."""
    fields: dict[str, str] = {}
    for item in lead.get("field_data", []):
        name = item.get("name", "")
        values = item.get("values", [])
        fields[name] = ", ".join(str(v) for v in values)
    return fields
