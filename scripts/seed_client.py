"""Da de alta (o actualiza) un cliente en la base de datos.

Uso:
    python -m scripts.seed_client \
        --name "Cliente Demo" \
        --page-id 153125381509891 \
        --token "EAAB..." \
        --email leads@cliente.com \
        --sheet-id 1AbC...xyz \
        --tab Leads
"""
import argparse

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Client


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--page-id", required=True)
    p.add_argument("--token", required=True, help="Page Access Token (leads_retrieval)")
    p.add_argument("--email", required=True)
    p.add_argument("--sheet-id", required=True)
    p.add_argument("--tab", default="Leads")
    args = p.parse_args()

    init_db()
    db = SessionLocal()
    try:
        client = db.scalar(select(Client).where(Client.page_id == args.page_id))
        if client is None:
            client = Client(page_id=args.page_id)
            db.add(client)
        client.name = args.name
        client.page_access_token = args.token
        client.recipient_email = args.email
        client.google_sheet_id = args.sheet_id
        client.sheet_tab = args.tab
        client.active = True
        db.commit()
        print(f"Cliente '{args.name}' guardado (page_id={args.page_id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
