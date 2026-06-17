"""VaoVao Lead Tracker — servidor de webhooks de Facebook Lead Ads.

Endpoints:
  GET  /webhook   → verificación del webhook (hub.challenge)
  POST /webhook   → recepción de notificaciones de leads
  GET  /health    → healthcheck
"""
import hashlib
import hmac
import logging

from fastapi import BackgroundTasks, FastAPI, Query, Request, Response

from app.config import get_settings
from app.database import init_db
from app.processor import process_lead

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vaovao.web")

settings = get_settings()
app = FastAPI(title="VaoVao Lead Tracker")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
) -> Response:
    """Meta valida el webhook con un GET. Hay que devolver el challenge
    en TEXTO PLANO (sin comillas ni JSON) si el verify_token coincide."""
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("Webhook verificado por Meta")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("Verificación de webhook rechazada")
    return Response(content="Forbidden", status_code=403)


def _valid_signature(body: bytes, header: str | None) -> bool:
    """Valida X-Hub-Signature-256 con el App Secret (HMAC-SHA256)."""
    if not settings.meta_app_secret:
        # Sin app secret configurado no podemos validar; lo registramos.
        logger.warning("META_APP_SECRET vacío: firma no verificada")
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.meta_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, header.split("=", 1)[1])


@app.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks) -> Response:
    """Recibe la notificación, valida la firma, agenda el procesamiento y
    responde 200 de inmediato (Meta reintenta si tardamos demasiado)."""
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not _valid_signature(body, signature):
        logger.warning("Firma inválida en webhook")
        return Response(content="Invalid signature", status_code=403)

    payload = await request.json()

    if payload.get("object") != "page":
        return Response(content="ignored", status_code=200)

    count = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "leadgen":
                continue
            value = change.get("value", {})
            leadgen_id = value.get("leadgen_id")
            page_id = value.get("page_id") or entry.get("id")
            form_id = value.get("form_id")
            if not leadgen_id or not page_id:
                continue
            # Procesamiento en segundo plano → respuesta inmediata.
            background.add_task(process_lead, str(leadgen_id), str(page_id), form_id)
            count += 1

    logger.info("Webhook recibido: %d lead(s) en cola", count)
    return Response(content="EVENT_RECEIVED", status_code=200)
