"""Envío de email pluggable. Implementación por defecto: SMTP (stdlib).

Para cambiar de proveedor (Resend, SendGrid, SES…), basta con crear otra
clase que herede de EmailSender y registrarla en get_email_sender().
"""
import html
import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

import httpx

from app.config import get_settings

logger = logging.getLogger("vaovao.email")
settings = get_settings()


class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, html_body: str) -> None: ...


class SmtpEmailSender(EmailSender):
    def send(self, to: str, subject: str, html_body: str) -> None:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content("Tu cliente de correo no soporta HTML.")
        msg.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("Email enviado a %s", to)


def _parse_from(raw: str) -> tuple[str, str]:
    """Separa 'Nombre <correo@dominio>' en (nombre, correo)."""
    if "<" in raw and ">" in raw:
        name = raw.split("<")[0].strip()
        addr = raw.split("<")[1].split(">")[0].strip()
        return name or "VaoVao Leads", addr
    return "VaoVao Leads", raw.strip()


class BrevoApiEmailSender(EmailSender):
    """Envía vía la API HTTP de Brevo (puerto 443, no lo bloquea Railway)."""

    def send(self, to: str, subject: str, html_body: str) -> None:
        api_key = os.environ.get("BREVO_API_KEY", "")
        if not api_key:
            raise ValueError("Falta BREVO_API_KEY")

        sender_name, sender_email = _parse_from(settings.smtp_from)
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html_body,
        }
        headers = {"api-key": api_key, "content-type": "application/json"}

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://api.brevo.com/v3/smtp/email", json=payload, headers=headers
            )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Brevo API {resp.status_code}: {resp.text}")
        logger.info("Email enviado a %s (Brevo API)", to)


def get_email_sender() -> EmailSender:
    provider = settings.email_provider.lower()
    if provider == "smtp":
        return SmtpEmailSender()
    if provider == "brevo_api":
        return BrevoApiEmailSender()
    raise ValueError(f"EMAIL_PROVIDER no soportado: {provider}")


def build_lead_email(client_name: str, fields: dict[str, str]) -> tuple[str, str]:
    """Devuelve (subject, html) para el correo del lead."""
    # Intenta un identificador legible para el asunto.
    headline = (
        fields.get("full_name")
        or fields.get("name")
        or fields.get("email")
        or fields.get("phone_number")
        or "sin nombre"
    )
    subject = f"Nuevo lead: {headline} — {client_name}"

    rows = "".join(
        f"<tr>"
        f'<td style="padding:6px 12px;border:1px solid #eee;font-weight:600;">{html.escape(k)}</td>'
        f'<td style="padding:6px 12px;border:1px solid #eee;">{html.escape(v)}</td>'
        f"</tr>"
        for k, v in fields.items()
    )
    body = f"""\
<div style="font-family:system-ui,Arial,sans-serif;max-width:560px;">
  <h2 style="margin:0 0 4px;">Nuevo lead de {html.escape(client_name)}</h2>
  <p style="color:#666;margin:0 0 16px;">Capturado por VaoVao Lead Tracker.</p>
  <table style="border-collapse:collapse;width:100%;font-size:14px;">{rows}</table>
</div>"""
    return subject, body