"""Pipeline de procesamiento de un lead (corre en segundo plano).

Orquesta: dedup → buscar cliente → traer lead de Meta → escribir Sheet →
enviar email → marcar estado. Cada paso registra su resultado en la BD para
que un lead fallido pueda reintentarse o auditarse.

Nota de escala: hoy usa BackgroundTasks de FastAPI (corre en el threadpool
del proceso). Para muchos clientes / alto volumen, mueve process_lead a una
cola real (arq, Celery, RQ) sin cambiar la lógica de aquí.
"""
import logging
from datetime import datetime, timezone

from app import crud
from app.database import SessionLocal
from app.services import meta, sheets
from app.services.email import build_lead_email, get_email_sender

logger = logging.getLogger("vaovao.processor")


def process_lead(leadgen_id: str, page_id: str, form_id: str | None) -> None:
    db = SessionLocal()
    lead_row = None
    try:
        # 1) Deduplicación: Meta puede reenviar el mismo webhook.
        if crud.lead_seen(db, leadgen_id):
            logger.info("Lead %s ya procesado, se omite", leadgen_id)
            return

        # 2) Enrutar al cliente por page_id.
        client = crud.get_client_by_page_id(db, page_id)
        lead_row = crud.register_lead(db, leadgen_id, client.id if client else None)

        if client is None:
            crud.mark_status(db, lead_row, "error", f"Sin cliente para page_id {page_id}")
            logger.warning("No hay cliente configurado para page_id %s", page_id)
            return

        # 3) Traer los datos del lead desde la Graph API.
        raw = meta.fetch_lead(leadgen_id, client.page_access_token)
        fields = meta.parse_field_data(raw)
        crud.mark_status(db, lead_row, "fetched")

        # 4) Armar la fila (metadata + campos del formulario).
        row = {
            "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "leadgen_id": leadgen_id,
            "form_id": form_id or raw.get("form_id", ""),
            "campaign_name": raw.get("campaign_name", ""),
            "ad_name": raw.get("ad_name", ""),
            **fields,
        }

        # 5) Escribir en el Google Sheet del cliente.
        sheets.append_lead_row(client.google_sheet_id, client.sheet_tab, row)

        # 6) Enviar el email al correo del cliente (opcional en pruebas).
        try:
            subject, body = build_lead_email(client.name, fields)
            get_email_sender().send(client.recipient_email, subject, body)
        except Exception as email_error:
            logger.warning("Email no enviado (se continúa): %s", email_error)
        crud.mark_status(db, lead_row, "delivered")
        logger.info("Lead %s entregado para cliente %s", leadgen_id, client.name)

    except Exception as exc:  # noqa: BLE001 — registramos cualquier fallo
        logger.exception("Fallo procesando lead %s", leadgen_id)
        if lead_row is not None:
            crud.mark_status(db, lead_row, "error", str(exc))
    finally:
        db.close()
