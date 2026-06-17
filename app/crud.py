from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, ProcessedLead


def get_client_by_page_id(db: Session, page_id: str) -> Client | None:
    return db.scalar(
        select(Client).where(Client.page_id == page_id, Client.active.is_(True))
    )


def lead_seen(db: Session, leadgen_id: str) -> bool:
    """True si ya registramos este leadgen_id (deduplicación)."""
    return db.scalar(
        select(ProcessedLead.id).where(ProcessedLead.leadgen_id == leadgen_id)
    ) is not None


def register_lead(db: Session, leadgen_id: str, client_id: int | None) -> ProcessedLead:
    lead = ProcessedLead(leadgen_id=leadgen_id, client_id=client_id, status="received")
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def mark_status(
    db: Session, lead: ProcessedLead, status: str, error: str | None = None
) -> None:
    lead.status = status
    lead.error = error
    if status in ("delivered", "error"):
        lead.processed_at = datetime.now(timezone.utc)
    db.add(lead)
    db.commit()
