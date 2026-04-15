# webhook_server.py
"""
FastAPI webhook listener for Linear comments (Human-in-the-Loop).

When an SRE adds a comment to a Linear issue that was created by the ITSM Agent,
this server:
  1. Verifies the HMAC-SHA256 signature from Linear.
  2. Finds the linked ResolvedTicket node in Neo4j via its linear_issue_id.
  3. Appends the comment to human_notes (timestamped, with author name).
  4. Re-embeds the full solution (solution_text + human_notes) using Gemini.
  5. Writes the updated human_notes and solution_embedding back to Neo4j.

The updated solution embedding ensures future search_memory calls surface
the human annotation with highest priority.

Run with:  python start_webhook.py
"""

import os
import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, status
from neo4j import GraphDatabase
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NEO4J_URI      = os.getenv("NEO4J_URI",      "neo4j://127.0.0.1:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LINEAR_WEBHOOK_SECRET = os.getenv("LINEAR_WEBHOOK_SECRET", "")

# ---------------------------------------------------------------------------
# External clients
# ---------------------------------------------------------------------------

neo4j_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
)

_genai_client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embed_document(text: str) -> list:
    """Embeds text as a RETRIEVAL_DOCUMENT vector (768-dim, gemini-embedding-001)."""
    result = _genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return result.embeddings[0].values


def _verify_linear_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Validates the Linear-Signature header (HMAC-SHA256).
    If LINEAR_WEBHOOK_SECRET is not set, skips verification (dev-only fallback).
    """
    if not LINEAR_WEBHOOK_SECRET:
        # No secret configured — allow all requests (local dev only)
        print("⚠️  LINEAR_WEBHOOK_SECRET not set — skipping signature verification.")
        return True

    if not signature_header:
        return False

    expected = hmac.new(
        LINEAR_WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


def _find_ticket_by_linear_id(session, linear_issue_id: str) -> Optional[dict]:
    """Returns the ResolvedTicket node dict, or None if not found."""
    result = session.run(
        """
        MATCH (t:ResolvedTicket {linear_issue_id: $linear_issue_id})
        RETURN t.incident_id    AS incident_id,
               t.solution_text  AS solution_text,
               t.human_notes    AS human_notes
        """,
        {"linear_issue_id": linear_issue_id},
    )
    record = result.single()
    if not record:
        return None
    return {
        "incident_id":   record["incident_id"],
        "solution_text": record["solution_text"] or "",
        "human_notes":   record["human_notes"]   or "",
    }


def _append_note(existing_notes: str, author: str, body: str) -> str:
    """Formats and appends a single human note to the existing notes string."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_note = f"[{timestamp}] {author}: {body}"
    if existing_notes:
        return f"{existing_notes}\n{new_note}"
    return new_note


def _update_ticket_notes(
    session,
    linear_issue_id: str,
    human_notes: str,
    solution_embedding: list,
) -> None:
    """Writes updated human_notes and re-computed solution_embedding to Neo4j."""
    session.run(
        """
        MATCH (t:ResolvedTicket {linear_issue_id: $linear_issue_id})
        SET t.human_notes        = $human_notes,
            t.solution_embedding = $solution_embedding
        """,
        {
            "linear_issue_id":   linear_issue_id,
            "human_notes":       human_notes,
            "solution_embedding": solution_embedding,
        },
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ITSM Agent — Linear Webhook Server",
    description=(
        "Receives Linear comment webhooks and persists human annotations "
        "to Neo4j ResolvedTicket nodes."
    ),
    version="1.0.0",
)


@app.get("/health")
def health_check():
    """Simple liveness probe."""
    return {"status": "ok", "service": "itsm-webhook-server"}


@app.post("/webhook/linear", status_code=status.HTTP_200_OK)
async def linear_webhook(request: Request):
    """
    Receives POST events from Linear.
    Only processes Comment → create events.
    All other event types are silently acknowledged (200 OK).
    """
    # 1. Read raw body before any parsing (needed for HMAC)
    payload_bytes = await request.body()
    signature     = request.headers.get("Linear-Signature", "")

    # 2. Verify webhook signature
    if not _verify_linear_signature(payload_bytes, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Linear-Signature header.",
        )

    # 3. Parse JSON payload
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload is not valid JSON.",
        )

    action     = payload.get("action", "")
    event_type = payload.get("type", "")

    # 4. Only care about new comments
    if action != "create" or event_type != "Comment":
        return {
            "status": "ignored",
            "reason": f"event type='{event_type}' action='{action}' — not a new comment",
        }

    # 5. Extract fields from the comment payload
    data         = payload.get("data", {})
    comment_body = (data.get("body") or "").strip()
    author       = (data.get("user") or {}).get("name", "Unknown")
    issue        = (data.get("issue") or {})
    linear_issue_id  = issue.get("id", "")
    linear_identifier = issue.get("identifier", "")

    if not linear_issue_id or not comment_body:
        return {
            "status": "ignored",
            "reason": "Missing linear_issue_id or empty comment body.",
        }

    print(
        f"\n📩 Comment received on {linear_identifier} ({linear_issue_id})\n"
        f"   Author : {author}\n"
        f"   Body   : {comment_body[:120]}{'...' if len(comment_body) > 120 else ''}"
    )

    # 6. Look up the ResolvedTicket node in Neo4j
    with neo4j_driver.session() as session:
        ticket = _find_ticket_by_linear_id(session, linear_issue_id)

        if not ticket:
            print(
                f"   ℹ️  No ResolvedTicket found for linear_issue_id='{linear_issue_id}'. "
                f"Possibly a non-ITSM issue — ignoring."
            )
            return {
                "status": "ignored",
                "reason": f"No ResolvedTicket linked to linear_issue_id '{linear_issue_id}'.",
            }

        incident_id = ticket["incident_id"]
        print(f"   ✅ Matched ResolvedTicket: {incident_id}")

        # 7. Append note
        updated_notes = _append_note(
            existing_notes=ticket["human_notes"],
            author=author,
            body=comment_body,
        )

        # 8. Re-embed solution (solution_text + updated human_notes)
        full_solution = ticket["solution_text"]
        if updated_notes:
            full_solution = f"{full_solution}\n\nHuman notes: {updated_notes}"

        print("   🔄 Re-embedding solution vector...")
        new_embedding = _embed_document(full_solution)

        # 9. Write back to Neo4j
        _update_ticket_notes(
            session=session,
            linear_issue_id=linear_issue_id,
            human_notes=updated_notes,
            solution_embedding=new_embedding,
        )

        print(
            f"   💾 human_notes updated and solution_embedding re-computed "
            f"for {incident_id}."
        )

    return {
        "status":      "ok",
        "incident_id": incident_id,
        "message":     (
            f"Human note by '{author}' saved and solution re-embedded "
            f"for ResolvedTicket '{incident_id}'."
        ),
    }
