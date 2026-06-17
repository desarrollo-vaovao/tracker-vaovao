# VaoVao Lead Tracker

Captura automática de leads de **Facebook Lead Ads**. Cuando alguien envía un
formulario de pauta, en menos de 60 segundos el lead llega a:

- el **Google Sheet** del cliente (una fila nueva, columnas autodetectadas), y
- el **correo** configurado para ese cliente.

Adiós a descargar el CSV a mano.

## Flujo

```
Lead Ad Form  →  Webhook de Meta  →  /webhook (FastAPI)
                                          │  responde 200 de inmediato
                                          ▼
                                   process_lead (background)
                                          │
                 ┌────────────────────────┼────────────────────────┐
                 ▼                         ▼                         ▼
          Graph API (Meta)          Google Sheet               Email (SMTP)
        trae el field_data         fila nueva + columnas      al correo del cliente
```

El enrutamiento es por `page_id`: cada lead se asigna al cliente cuya página de
Facebook lo generó.

## Estructura

```
app/
  main.py            # FastAPI: GET/POST /webhook, /health, firma HMAC
  config.py          # settings desde .env
  database.py        # SQLAlchemy engine + init_db
  models.py          # Client, ProcessedLead (dedup)
  crud.py            # enrutamiento y deduplicación
  processor.py       # pipeline de un lead (background task)
  services/
    meta.py          # Graph API: fetch_lead + parse_field_data
    sheets.py        # escritura en Sheet con columnas dinámicas
    email.py         # envío pluggable (SMTP por defecto)
scripts/
  seed_client.py     # alta de clientes en la BD
```

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # y completa los valores
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La URL del webhook debe ser **HTTPS pública**. En local usa un túnel
(p. ej. `cloudflared` o `ngrok`) apuntando a `:8000`.

## Configuración en Meta

1. Crea una app en *developers.facebook.com* y añade los productos
   **Webhooks** y **Facebook Login**.
2. Solicita los permisos `leads_retrieval`, `pages_show_list`,
   `pages_read_engagement`, `pages_manage_ads` y pásalos por **App Review**
   (necesario para leer leads de páginas de clientes).
3. En Webhooks, suscribe el objeto **Page** al campo **`leadgen`**, con:
   - Callback URL: `https://tu-dominio/webhook`
   - Verify Token: el mismo de `META_VERIFY_TOKEN`
4. Genera un **Page Access Token de larga duración** por cada página de cliente
   e instala la app en la página:
   ```
   POST /{page_id}/subscribed_apps?subscribed_fields=leadgen
   ```

> Prueba rápida: en el panel de la app, sección Webhooks, botón **Test** del
> campo `leadgen` → *Send to My Server*.

## Configuración de Google Sheets

1. Crea una **Service Account** en Google Cloud y descarga su JSON
   (apúntalo en `GOOGLE_SERVICE_ACCOUNT_FILE`).
2. Habilita la **Google Sheets API** en el proyecto.
3. Comparte el Sheet de **cada cliente** con el `client_email` del JSON, como
   **Editor**. Sin esto, la escritura falla con permiso denegado.

## Alta de un cliente

```bash
python -m scripts.seed_client \
  --name "<NOMBRE_CLIENTE>" \
  --page-id <PAGE_ID> \
  --token "<PAGE_ACCESS_TOKEN>" \
  --email <CORREO_DESTINO> \
  --sheet-id <GOOGLE_SHEET_ID> \
  --tab Leads
```

> **Seguridad:** el `<PAGE_ACCESS_TOKEN>` es una credencial sensible. No lo
> escribas en archivos versionados ni lo compartas. En producción se gestiona
> mediante variables de entorno o un panel de administración, no a mano.

## Notas técnicas

- **Respuesta inmediata + background.** El webhook responde `200` al instante y
  procesa aparte; si tardáramos, Meta reintenta.
- **Deduplicación.** Cada `leadgen_id` se guarda en `processed_leads`; reenvíos
  de Meta se ignoran.
- **Firma.** Se valida `X-Hub-Signature-256` con `META_APP_SECRET`.
- **Columnas dinámicas.** Si el formulario cambia, las columnas nuevas se crean
  solas en el Sheet.
- **Seguridad pendiente:** cifrar `page_access_token` en reposo.

### Camino a escala (muchos clientes)

Hoy el procesamiento usa `BackgroundTasks` (threadpool del proceso). Para alto
volumen, mueve `process_lead` a una **cola** (arq / Celery / RQ) con workers
dedicados —la lógica del pipeline no cambia— y usa **Postgres** en
`DATABASE_URL`. Un worker por Sheet evita carreras al ampliar encabezados.