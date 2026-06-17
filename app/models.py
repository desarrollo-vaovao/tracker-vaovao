from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Client(Base):
    """Configuración por cliente. El lead se enruta por page_id."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    # Página de Facebook del cliente. Es la llave de enrutamiento.
    page_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # Page Access Token de larga duración con permiso leads_retrieval.
    # NOTA: en producción cífralo en reposo (p. ej. con una KMS / Fernet).
    page_access_token: Mapped[str] = mapped_column(Text)

    # Destinos
    recipient_email: Mapped[str] = mapped_column(String(255))
    google_sheet_id: Mapped[str] = mapped_column(String(128))
    sheet_tab: Mapped[str] = mapped_column(String(128), default="Leads")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    leads: Mapped[list["ProcessedLead"]] = relationship(back_populates="client")


class ProcessedLead(Base):
    """Registro de leads ya procesados → evita duplicados y deja traza."""

    __tablename__ = "processed_leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    leadgen_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)

    # received → fetched → delivered  |  error
    status: Mapped[str] = mapped_column(String(32), default="received")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    client: Mapped["Client | None"] = relationship(back_populates="leads")
