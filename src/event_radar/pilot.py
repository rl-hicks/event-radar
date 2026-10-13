"""Explicit local-only pilot operations. No auth bypass, research or Telegram consumption."""

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from alembic import command
from event_radar.auth.config import auth_config
from event_radar.auth.identity import AuthenticatedUser
from event_radar.auth.verifier import get_verifier
from event_radar.db.curation_preflight import PricingReview, curation_preflight
from event_radar.db.session import build_engine
from event_radar.db.snapshot_import import import_public_snapshot
from event_radar.models.weekend_packet import CurationPolicy

LOCAL_URL = URL.create(
    "postgresql+psycopg",
    username="event_radar_e2_pilot",
    password="e2_local_synthetic_only",
    host="127.0.0.1",
    port=55434,
    database="event_radar_e2_pilot",
)


def local_engine() -> Engine:
    if any(key.startswith("PG") for key in os.environ):
        raise ValueError("Remove libpq overrides before local pilot operations.")
    engine = build_engine(LOCAL_URL)
    with engine.connect() as connection:
        if tuple(connection.execute(text("SELECT current_database(), current_user")).one()) != (
            "event_radar_e2_pilot",
            "event_radar_e2_pilot",
        ):
            raise ValueError("Local pilot database identity mismatch.")
    return engine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("init")
    imp = sub.add_parser("import-snapshot")
    imp.add_argument("--export", type=Path, required=True)
    imp.add_argument("--expected-sha256", required=True)
    for name in ("preflight", "curate"):
        item = sub.add_parser(name)
        item.add_argument("--snapshot-id", type=UUID, required=True)
        item.add_argument("--policy", type=Path, required=True)
        item.add_argument("--pricing-review", type=Path)
        if name == "curate":
            item.add_argument("--execute-approved", action="store_true")
    link = sub.add_parser("telegram-link")
    link.add_argument("--approve-private-development-link", action="store_true")
    delivery = sub.add_parser("deliver")
    delivery.add_argument("--packet-id", type=UUID, required=True)
    delivery.add_argument("--binding-id", type=UUID, required=True)
    delivery.add_argument("--approval", type=Path, required=True)
    delivery.add_argument("--execute-approved", action="store_true")
    args = parser.parse_args()
    engine = local_engine()
    try:
        if args.operation == "init":
            # Additive local migrations only, never downgrade and never inherit hosted DATABASE_URL.
            os.environ["DATABASE_URL"] = LOCAL_URL.render_as_string(hide_password=False)
            command.upgrade(Config("alembic.ini"), "0005_packet_delivery")
        elif args.operation == "import-snapshot":
            envelope = json.loads(args.export.read_text())
            if envelope.get("sha256") != args.expected_sha256:
                raise ValueError("Export does not match the reviewed envelope hash.")
            with Session(engine) as session, session.begin():
                print(import_public_snapshot(session, envelope))
        elif args.operation == "telegram-link":
            if not args.approve_private_development_link or not sys.stdout.isatty():
                raise ValueError("Explicit approval and a private interactive terminal required.")
            from event_radar.services.operator_telegram import request_operator_challenge

            token = getpass.getpass("Consenting ordinary account access token (hidden): ")
            with Session(engine) as session, session.begin():
                code = request_operator_challenge(session, token, approved=True)
            print("Private development only. Send to the operator-confirmed bot within 10 minutes:")
            print("/start " + code)
            print("Keep this one-use code private; do not record terminal output.")
        elif args.operation == "deliver":
            if not args.execute_approved:
                raise ValueError("Separate delivery execution approval required.")
            from event_radar.db.delivery import queue_delivery
            from event_radar.models.delivery_authority import PilotDeliveryAuthority
            from event_radar.services.packet_delivery import dispatch_delivery
            from event_radar.services.telegram_transport import TelegramHTTPTransport

            token = getpass.getpass("Ordinary account access token (hidden): ")
            uid, _ = get_verifier(auth_config()).verify(token)
            approval = PilotDeliveryAuthority.model_validate_json(args.approval.read_text())
            bot_token = getpass.getpass("Approved bot credential (hidden): ")
            with Session(engine) as session, session.begin():
                intent = queue_delivery(
                    session, uid, args.packet_id, args.binding_id, "telegram", approval=approval
                )
            outcome = dispatch_delivery(
                engine,
                intent,
                TelegramHTTPTransport(token=bot_token, authorized=True),
                approval=approval,
            )
            print(json.dumps({"intent_id": str(intent), "status": outcome}))
        else:
            # A normal signed user access token is required; no account UUID selector.
            token = getpass.getpass("Ordinary account access token (hidden): ")
            uid, email = get_verifier(auth_config()).verify(token)
            user = AuthenticatedUser(id=uid, email=email)
            policy = CurationPolicy.model_validate_json(args.policy.read_text())
            pricing = (
                PricingReview.model_validate_json(args.pricing_review.read_text())
                if args.pricing_review
                else None
            )
            key = None
            if args.operation == "curate" and args.execute_approved and policy.provider == "openai":
                key = getpass.getpass("Approved OpenAI API key (hidden): ")
            with Session(engine) as session:
                preflight = curation_preflight(
                    session,
                    user,
                    args.snapshot_id,
                    policy,
                    pricing=pricing,
                    credentials_ready=bool(key),
                )
            print(preflight.model_dump_json(indent=2))
            if args.operation == "curate":
                if not args.execute_approved or not preflight.ready:
                    raise ValueError("Explicit approval and successful preflight required.")
                from event_radar.models.token_usage import ModelTokenPricing
                from event_radar.services.curation_openai import OpenAIResponsesCurationProvider
                from event_radar.services.packet_generation import generate_packet
                from event_radar.services.personalized_curation import DeterministicCurationProvider

                provider = (
                    DeterministicCurationProvider()
                    if policy.provider == "deterministic"
                    else OpenAIResponsesCurationProvider(
                        authorized=True,
                        api_key=key,
                        pricing=ModelTokenPricing(
                            pricing.input_usd_per_million, None, pricing.output_usd_per_million
                        )
                        if pricing
                        else None,
                    )
                )
                result = asyncio.run(
                    generate_packet(
                        engine,
                        user.id,
                        args.snapshot_id,
                        policy,
                        provider,
                        expected_context_revision_id=preflight.context_revision_id,
                    )
                )
                print(
                    json.dumps(
                        {
                            "status": result.status,
                            "packet_id": str(result.packet_id) if result.packet_id else None,
                            "failure_code": result.failure_code,
                        }
                    )
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Pilot operation could not be completed; no raw credentials or provider data logged."
        ) from None
